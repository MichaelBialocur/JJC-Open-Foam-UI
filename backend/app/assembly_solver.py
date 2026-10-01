"""Full 3D flow followed by native coupled fluid/solid energy transport."""
import json
from math import sqrt
from pathlib import Path
import shutil
import sys

import numpy as np

from .cases import header
from .conjugate import mass_flux
from .assembly_mesh import patches, read_mesh, patch_indices, wall_boundary, cad_wall_patches


def put(root,name,text):
    p=root/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)


def field(name,dimensions,initial,conditions,vector=False):
    return header(name,'volVectorField' if vector else 'volScalarField')+f'dimensions {dimensions};\ninternalField uniform {initial};\nboundaryField\n{{\n'+''.join(f'{n} {{ {v} }}\n' for n,v in conditions.items())+'}\n'


def flow_dictionaries(case,spec,mesh):
    p=spec.operating;patch_names=mesh['patches'];u=p.inlet_velocity_m_s
    direction=np.array(spec.metrics.inlet_direction if spec.geometry_type=='cad' else spec.geometry.layout()[0]['tangent'])
    uv='('+' '.join(f'{v*u:.14g}' for v in direction)+')'
    inlet=f'type fixedValue; value uniform {uv};'
    if spec.geometry_type=='cad' or (p.inlet and p.inlet.kind!='velocity'):
        inlet=f'type flowRateInletVelocity; volumetricFlowRate constant {u*p.inlet_area_m2:.14g}; value uniform {uv};'
    def conditions(a,b,c): return {n:a if n=='inlet' else b if n=='outlet' else c for n in patch_names}
    put(case,'0/U',field('U','[0 1 -1 0 0 0 0]',uv,conditions(inlet,'type zeroGradient;','type noSlip;'),True))
    put(case,'0/p',field('p','[0 2 -2 0 0 0 0]','0',conditions('type zeroGradient;','type fixedValue; value uniform 0;','type zeroGradient;')))
    put(case,'constant/physicalProperties',header('physicalProperties')+f'viscosityModel constant; nu {p.nu:.14g};\n')
    turbulent=p.selected_model=='kOmegaSST'
    put(case,'constant/momentumTransport',header('momentumTransport')+('simulationType RAS; RAS { model kOmegaSST; turbulence on; viscosityModel Newtonian; }\n' if turbulent else 'simulationType laminar; laminar { model Stokes; viscosityModel Newtonian; }\n'))
    if turbulent:
        k=1.5*(u*p.turbulence_intensity)**2;omega=sqrt(k)/(.09**.25*.07*p.diameter_m)
        for name,dim,value,wall in [('k','[0 2 -2 0 0 0 0]',k,'type fixedValue; value uniform 1e-12;'),
            ('omega','[0 0 -1 0 0 0 0]',omega,f'type omegaWallFunction; value uniform {omega:.14g};'),
            ('nut','[0 2 -1 0 0 0 0]',0,'type nutLowReWallFunction; value uniform 0;')]:
            put(case,'0/'+name,field(name,dim,f'{value:.14g}',conditions(f'type {"calculated" if name=="nut" else "fixedValue"}; value uniform {value:.14g};','type zeroGradient;' if name!='nut' else 'type calculated; value uniform 0;',wall)))
    put(case,'system/controlDict',header('controlDict')+f'''application foamRun; solver incompressibleFluid;
startFrom startTime; startTime 0; stopAt endTime; endTime {p.max_iterations}; deltaT 1;
writeControl timeStep; writeInterval 100; purgeWrite 2; writeFormat ascii; writePrecision 12;
writeCompression off; runTimeModifiable false;
''')
    put(case,'system/fvSchemes',header('fvSchemes')+'''ddtSchemes { default steadyState; }
gradSchemes { default leastSquares; }
divSchemes { default none; div(phi,U) bounded Gauss linearUpwind grad(U);
div(phi,k) bounded Gauss limitedLinear 1; div(phi,omega) bounded Gauss limitedLinear 1;
div((nuEff*dev2(T(grad(U))))) Gauss linear; div(nonlinearStress) Gauss linear; }
laplacianSchemes { default Gauss linear corrected; }
interpolationSchemes { default linear; } snGradSchemes { default corrected; }
wallDist { method meshWave; }
''')
    put(case,'system/fvSolution',header('fvSolution')+f'''solvers {{
p {{ solver GAMG; tolerance 1e-14; relTol 0.01; smoother GaussSeidel; }}
pcorr {{ solver GAMG; tolerance 1e-14; relTol 0; smoother GaussSeidel; }}
"(U|k|omega)" {{ solver smoothSolver; smoother symGaussSeidel; tolerance 1e-14; relTol 0.01; }} }}
SIMPLE {{ nNonOrthogonalCorrectors 2; consistent no;
residualControl {{ p {p.residual_tolerance}; U {p.residual_tolerance}; "(k|omega)" {p.residual_tolerance}; }} }}
relaxationFactors {{ fields {{ p 0.3; }} equations {{ U 0.7; k 0.7; omega 0.7; }} }}
''')
    (case/'assembly.foam').touch()


def thermal_dictionaries(case,spec,iteration):
    p=spec.operating;thermal=case/'thermal';thermal.mkdir()
    source=case/'meshing/constant'
    for region in ('fluid','solid'):
        shutil.copytree(source/region/'polyMesh',thermal/'constant'/region/'polyMesh')
    fluid=read_mesh(thermal/'constant/fluid/polyMesh');solid=read_mesh(thermal/'constant/solid/polyMesh')
    fp=fluid['patches'];sp=solid['patches'];tin=p.inlet_temperature_c+273.15
    for name in ('U','phi','k','omega','nut'):
        path=case/str(iteration)/name
        if path.exists():
            text=path.read_text()
            # The hydraulic mass/volume boundary has already been solved.
            # Preserve its written U values in the frozen thermal calculation.
            if name=='U':
                import re
                text=re.sub(r'type\s+flowRateInletVelocity\s*;','type fixedValue;',text)
            put(thermal,'0/fluid/'+name,mass_flux(text,p.density_kg_m3) if name=='phi' else text)
    cond={n:f'type fixedValue; value uniform {tin:.14g};' if n=='inlet' else 'type zeroGradient;' if n=='outlet' else f'type coupledTemperature; value uniform {tin:.14g};' if v['type']=='mappedWall' else 'type zeroGradient;' for n,v in fp.items()}
    put(thermal,'0/fluid/T',field('T','[0 0 0 1 0 0 0]',f'{tin:.14g}',cond))
    put(thermal,'0/fluid/p',field('p','[1 -1 -2 0 0 0 0]','100000',{n:'type fixedValue; value uniform 100000;' if n=='outlet' else 'type zeroGradient;' for n in fp}))
    put(thermal,'constant/fluid/physicalProperties',header('physicalProperties')+f'''thermoType {{ type heRhoThermo; mixture pureMixture; transport const; thermo hConst;
equationOfState rhoConst; specie specie; energy sensibleEnthalpy; }}
mixture {{ specie {{ molWeight 18; }} equationOfState {{ rho {p.density_kg_m3:.14g}; }}
thermodynamics {{ Cp {p.specific_heat_j_kg_k:.14g}; Hf 0; }}
transport {{ mu {p.dynamic_viscosity_pa_s:.14g}; Pr {p.prandtl:.14g}; }} }}
''')
    put(thermal,'constant/fluid/momentumTransport',(case/'constant/momentumTransport').read_text())
    if p.selected_model=='kOmegaSST':
        put(thermal,'constant/fluid/thermophysicalTransport',header('thermophysicalTransport')+f'RAS {{ model eddyDiffusivity; Prt {p.turbulent_prandtl}; }}\n')
        put(thermal,'0/fluid/alphat',field('alphat','[1 -1 -1 0 0 0 0]','0',{n:'type fixedValue; value uniform 0;' if v['type']=='mappedWall' else 'type calculated; value uniform 0;' for n,v in fp.items()}))
    put(thermal,'constant/solid/physicalProperties',header('physicalProperties')+f'''thermoType constSolidThermo;
rho {{ type uniform; value {p.solid_density}; }} Cv {{ type uniform; value {p.solid_specific_heat}; }}
kappa {{ type uniform; value {p.solid_conductivity}; }}
''')
    solid_conditions={n:f'type coupledTemperature; value uniform {tin};' if v['type']=='mappedWall' else 'type zeroGradient;' for n,v in sp.items()}
    assigned={}
    for group in spec.boundaries:
        for face in group.faces:
            if face not in sp or not sp[face]['count'] or not face.startswith('f_'):
                raise ValueError(f'Thermal face {face} is not an exterior solid face in this mesh.')
        area=sum(solid['area'][patch_indices(solid,f)].sum() for f in group.faces)
        for face in group.faces:
            a=float(solid['area'][patch_indices(solid,face)].sum())
            power=group.power_w*a/area
            bc=f'Q constant {power:.14g};' if group.kind=='heat' else f'h uniform {group.h_w_m2_k:.14g}; Ta constant {group.ambient_c+273.15:.14g};'
            solid_conditions[face]=f'type externalTemperature; {bc} value uniform {tin:.14g};'
            assigned[face]={'group_id':group.id,'kind':group.kind,'mesh_area_m2':a,
                'power_w':power if group.kind=='heat' else None,'h_w_m2_k':group.h_w_m2_k,'ambient_c':group.ambient_c}
    put(thermal,'0/solid/T',field('T','[0 0 0 1 0 0 0]',f'{tin:.14g}',solid_conditions))
    put(thermal,'system/controlDict',header('controlDict')+f'''application foamMultiRun;
regionSolvers {{ fluid fluid; solid solid; }} startFrom startTime; startTime 0; stopAt endTime;
endTime {p.thermal_iterations}; deltaT 1; writeControl timeStep; writeInterval 50; purgeWrite 2;
writeFormat ascii; writePrecision 12; writeCompression off; runTimeModifiable false;
''')
    put(thermal,'system/fvSolution',header('fvSolution')+'PIMPLE { nOuterCorrectors 1; nEnergyCorrectors 1; }\n')
    for region in ('fluid','solid'):
        put(thermal,f'system/{region}/fvSchemes',header('fvSchemes')+'''ddtSchemes { default steadyState; }
gradSchemes { default Gauss linear; } divSchemes { default none; div(phi,h) Gauss upwind; div(phi,K) Gauss upwind; }
laplacianSchemes { default Gauss linear corrected; } interpolationSchemes { default linear; }
snGradSchemes { default corrected; } wallDist { method meshWave; }
''')
        solver='PBiCGStab; preconditioner DILU' if region=='fluid' else 'PCG; preconditioner DIC'
        put(thermal,f'system/{region}/fvSolution',header('fvSolution')+f'''solvers {{ "(h|hFinal|e|eFinal)" {{ solver {solver}; tolerance 1e-11; relTol 0; }} }}
PIMPLE {{ flow false; models false; thermophysics true; nNonOrthogonalCorrectors 2; }}
''')
    put(thermal,'boundary-allocation.json',json.dumps(assigned,indent=2))
    (thermal/'conjugate.foam').touch()
    return thermal


def run_assembly(manager,job_id,spec,env):
    from .assembly_results import analyse_assembly
    case=manager.root/job_id;meshcase=case/'meshing'
    manager.update(job_id,status='generating',openfoam_version=env['WM_PROJECT_VERSION'])
    put(case,'geometry-input.json',spec.geometry.model_dump_json())
    imported=spec.geometry_type=='cad'
    put(case,'manifest.json',json.dumps({'schema_version':1,'generator':'cad-occ-v1' if imported else 'assembly-occ-v1','inputs':spec.model_dump(),
        'resolved_physics':spec.operating.model_dump()},indent=2))
    put(meshcase,'system/controlDict',header('controlDict')+'application gmshToFoam; startFrom startTime; startTime 0; stopAt endTime; endTime 1; deltaT 1; writeControl timeStep; writeInterval 1; writeFormat ascii;\n')
    args=[sys.executable,'-m','backend.app.assembly_geometry',str(case/'geometry-input.json'),str(meshcase),'--mesh','--size',str(spec.mesh_size_mm)]
    if imported:
        from .cad_api import source_file
        source,metadata=source_file(manager.root,spec.geometry.source_id)
        target=case/('source'+metadata['suffix'])
        shutil.copy2(source,target)
        put(case,'cad-source.json',json.dumps(metadata))
        put(case,'cad-input.json',spec.model_dump_json())
        args=[sys.executable,'-m','backend.app.cad_geometry',str(target),str(meshcase),
              '--spec',str(case/'cad-input.json'),'--size',str(spec.mesh_size_mm)]
    cad_env={**env,'PYTHONPATH':str(Path(__file__).resolve().parents[2])}
    # Large meshes must not inherit the prototype's short wall-clock cutoffs.
    # Every stage remains cancellable, and both regions still pass checkMesh.
    manager._command(job_id,'cadMesh',args,cad_env,timeout=None)
    shutil.copy2(meshcase/'geometry.json',case/'geometry.json')
    manager.update(job_id,status='meshing')
    manager._command(job_id,'gmshToFoam',['gmshToFoam','-case',str(meshcase),str(meshcase/'assembly.msh')],env,timeout=None)
    if imported and not spec.geometry.solid_bodies:
        # Foundation 14's splitMeshRegions does nothing for a single region.
        # Keep the same explicit fluid directory used by checks and exports.
        shutil.copytree(meshcase/'constant/polyMesh',meshcase/'constant/fluid/polyMesh')
    else:
        manager._command(job_id,'splitRegions',['splitMeshRegions','-case',str(meshcase),'-cellZones','all','-noFields'],env,timeout=None)
    if imported:
        cad_wall_patches(meshcase/'constant/fluid/polyMesh/boundary')
    for region in (('fluid',) if imported and not spec.geometry.solid_bodies else ('fluid','solid')):
        args=['-case',str(meshcase),'-region',region]
        manager._command(job_id,region+'Check',['checkMesh',*args],env,timeout=None)
        if 'Mesh OK.' not in (case/f'log.{region}Check').read_text():
            raise ValueError(f'{region} mesh quality checks did not pass. Increase bend radius or adjust target cell size.')
    shutil.copytree(meshcase/'constant/fluid/polyMesh',case/'constant/polyMesh')
    wall_boundary(case/'constant/polyMesh/boundary')
    mesh=read_mesh(case/'constant/polyMesh');flow_dictionaries(case,spec,mesh)
    manager._command(job_id,'centres',['foamPostProcess','-func','writeCellCentres','-time','0'],env,timeout=None)
    manager._command(job_id,'volumes',['foamPostProcess','-func','writeCellVolumes','-time','0'],env,timeout=None)
    manager.update(job_id,status='solving')
    manager._command(job_id,'foamRun',['foamRun'],env,timeout=None)
    times=sorted(int(p.name) for p in case.iterdir() if p.is_dir() and p.name.isdigit() and int(p.name)>0)
    if not times: raise ValueError('Flow solver did not write a solution.')
    if spec.boundaries:
        thermal=thermal_dictionaries(case,spec,times[-1])
        manager.update(job_id,status='heating')
        manager._command(job_id,'solidCentres',['foamPostProcess','-case',str(thermal),'-region','solid','-func','writeCellCentres','-time','0'],env,timeout=None)
        manager._command(job_id,'thermal',['foamMultiRun','-case',str(thermal)],env,timeout=None)
    manager.update(job_id,status='processing')
    result=analyse_assembly(case,spec)
    put(case,'results.json',json.dumps(result,indent=2,allow_nan=False))
    manager.update(job_id,status='completed' if result['checks']['flow_converged'] and result['checks'].get('thermal_converged',True) else 'not_converged')
