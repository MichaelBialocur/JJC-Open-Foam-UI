"""Conservation checks and displays derived only from written 3D CFD fields."""
import json
from pathlib import Path

import numpy as np

from .results import read_internal, read_patch, convergence
from .assembly_mesh import read_mesh, cached_mesh, patch_indices


def times(folder):
    return sorted((p for p in folder.iterdir() if p.is_dir() and p.name.isdigit() and int(p.name)>0),key=lambda p:int(p.name))


def boundary_temperature(path,name,mesh,temperature,tin):
    ids=patch_indices(mesh,name)
    if not len(ids): return np.array([])
    if name=='inlet': return np.full(len(ids),tin)
    if name=='outlet': return temperature[mesh['owner'][ids]]
    return read_patch(path,name,len(ids))


def conduction(mesh,centres,temperature,name,boundary,k):
    ids=patch_indices(mesh,name);owners=mesh['owner'][ids]
    distance=np.einsum('ij,ij->i',mesh['sf'][ids]/mesh['area'][ids,None],mesh['cf'][ids]-centres[owners])
    if np.any(distance<=0): raise ValueError('A boundary face has a non-positive normal cell distance.')
    # Foundation 14 sets non-orthogonal correction vectors to zero on these
    # non-coupled poly patches; mappedWall temperature coupling uses mixed BCs.
    return np.asarray(k)*(temperature[owners]-boundary)/distance


def analyse_assembly(case,spec):
    p=spec.operating;mesh=read_mesh(case/'constant/polyMesh');n=mesh['cell_count']
    folders=times(case);latest=folders[-1]
    centres=read_internal(case/'0/C',3,n);volumes=read_internal(case/'0/Vc',count=n)
    u=read_internal(latest/'U',3,n);pressure=read_internal(latest/'p',count=n)*p.density_kg_m3
    inlet=patch_indices(mesh,'inlet');outlet=patch_indices(mesh,'outlet')
    phi_in=read_patch(latest/'phi','inlet',len(inlet));phi_out=read_patch(latest/'phi','outlet',len(outlet))
    qin=-float(phi_in.sum());qout=float(phi_out.sum())
    if qin<=0 or qout<=0: raise ValueError('No positive through-flow was found.')
    mass_error=100*abs(qout-qin)/qin
    conv=convergence((case/'log.foamRun').read_text())
    stationarity=None
    if len(folders)>1:
        old_u=read_internal(folders[-2]/'U',3,n);old_p=read_internal(folders[-2]/'p',count=n)*p.density_kg_m3
        stationarity=max(float(np.max(np.linalg.norm(u-old_u,axis=1)))/max(p.inlet_velocity_m_s,1e-12),
            float(np.max(np.abs(pressure-old_p)))/max(float(np.ptp(pressure)),p.density_kg_m3*p.inlet_velocity_m_s**2,1e-12))
    required=['p','Ux','Uy','Uz']+(['k','omega'] if p.selected_model=='kOmegaSST' else [])
    residual_ok=all(conv['residuals'].get(k,1)>-1 and conv['residuals'].get(k,1)<=p.residual_tolerance for k in required)
    converged=int(latest.name)==conv['iteration'] and (conv['solver_converged'] or (residual_ok and stationarity is not None and stationarity<=p.residual_tolerance))
    pin=float(np.average(pressure[mesh['owner'][inlet]],weights=mesh['area'][inlet]))
    result={'geometry_type':'assembly','solution_iteration':int(latest.name),'fluid_cells':n,
        'volumetric_flow_l_min':qin*60000,'mass_flow_kg_s':qin*p.density_kg_m3,
        'inlet_mesh_area_m2':float(mesh['area'][inlet].sum()),'inlet_cad_area_m2':p.inlet_area_m2,
        'inlet_mean_velocity_m_s':qin/float(mesh['area'][inlet].sum()),
        'pressure_drop_pa':pin,'pressure_measurement':'Area-weighted inlet zero-gradient patch pressure minus the 0 Pa outlet patch.',
        'mass_balance_error_percent':mass_error,'minimum_pressure_pa':float(pressure.min()),'maximum_speed_m_s':float(np.linalg.norm(u,axis=1).max()),
        'convergence':{**conv,'converged':converged,'relative_saved_field_change':stationarity},
        'checks':{'flow_converged':converged,'mass_balance_below_0_5_percent':mass_error<.5},
        'reference':{'applicable':False,'kind':'none','note':'No experimental validation is claimed for this assembly. Check mesh sensitivity and suitable geometry-specific research data.'}}
    parts=spec.geometry.parts
    if len(parts)==1 and parts[0].kind=='straight' and parts[0].start.shape=='round' and parts[0].start==parts[0].end and p.selected_model=='laminar':
        row=spec.geometry.layout()[0];direction=np.array(row['tangent']);x=(centres-np.array(row['start_mm'])/1000)@direction
        length=row['length_mm']/1000;mask=(x>.60*length)&(x<.85*length)
        if mask.sum()>10:
            slope=np.polyfit(x[mask],pressure[mask],1,w=np.sqrt(volumes[mask]))[0]
            bulk=qin/p.inlet_area_m2;re=bulk*p.diameter_m/p.nu
            darcy=-slope*p.diameter_m/(.5*p.density_kg_m3*bulk**2)
            slopes=[]
            for lo,hi in ((.60,.725),(.725,.85)):
                station=(x>lo*length)&(x<hi*length)
                slopes.append(float(np.polyfit(x[station],pressure[station],1,w=np.sqrt(volumes[station]))[0]) if station.sum()>5 else float('nan'))
            drift=100*abs(slopes[1]-slopes[0])/max(abs(slope),1e-20)
            relative=centres-np.array(row['start_mm'])/1000
            radius=np.linalg.norm(relative-x[:,None]*direction,axis=1)
            analytical=2*bulk*(1-(radius/(p.diameter_m/2))**2)
            profile_error=100*float(np.sqrt(np.average((u[mask]@direction-analytical[mask])**2,weights=volumes[mask])))/bulk
            developed=bool(np.isfinite(drift) and drift<5 and .6*length>max(1,.05*re)*p.diameter_m)
            error=float(100*(darcy/(64/re)-1))
            result['checks']['analytical_reference_within_5_percent']=bool(developed and abs(error)<5 and profile_error<5)
            result['reference']={'applicable':developed,'kind':'analytical','title':'Hagen–Poiseuille developed pressure gradient',
                'url':'https://archive.nptel.ac.in/content/storage2/courses/112104118/lecture-26/26-3_hag_poiseuille.htm',
                'reynolds':re,'computed_darcy_f':float(darcy),'analytical_darcy_f':64/re,
                'error_percent':error,'profile_rmse_percent_of_bulk':profile_error,'gradient_drift_percent':float(drift) if np.isfinite(drift) else None,
                'note':'Fit over 60–85% of length. Applicability screens entrance length and <5% downstream gradient drift; it is not proof of development. The verification target is <5% friction error and velocity-profile RMSE. Analytical verification, not an experiment.'}
    if not spec.boundaries: return result
    thermal=case/'thermal';tfolders=times(thermal);tlast=tfolders[-1];tprev=tfolders[-2] if len(tfolders)>1 else None
    solid=read_mesh(thermal/'constant/solid/polyMesh');ns=solid['cell_count']
    sc=read_internal(thermal/'0/solid/C',3,ns)
    ft=read_internal(tlast/'fluid/T',count=n);st=read_internal(tlast/'solid/T',count=ns);tin=p.inlet_temperature_c+273.15
    tconv=convergence((case/'log.thermal').read_text())
    tchange=None
    if tprev:
        tchange=max(float(np.max(np.abs(ft-read_internal(tprev/'fluid/T',count=n)))),
                    float(np.max(np.abs(st-read_internal(tprev/'solid/T',count=ns)))))/max(float(np.max(abs(ft-tin))),float(np.max(abs(st-tin))),1)
    tconverged=int(tlast.name)==tconv['iteration'] and all(tconv['residuals'].get(k,1)<=p.residual_tolerance for k in ['h','e']) and tchange is not None and tchange<=p.residual_tolerance
    outlet_t=ft[mesh['owner'][outlet]]
    advective=float(p.density_kg_m3*p.specific_heat_j_kg_k*np.dot(phi_out,outlet_t-tin))
    inlet_k=p.thermal_conductivity_w_m_k
    if p.selected_model=='kOmegaSST':
        inlet_k=inlet_k+p.density_kg_m3*p.specific_heat_j_kg_k*read_patch(latest/'nut','inlet',len(inlet))/p.turbulent_prandtl
    inlet_cond=float(np.dot(conduction(mesh,centres,ft,'inlet',np.full(len(inlet),tin),inlet_k),mesh['area'][inlet]))
    inlet_speed=qin/mesh['area'][inlet].sum()
    kinetic=float(p.density_kg_m3*(np.dot(phi_out,np.sum(u[mesh['owner'][outlet]]**2,axis=1)/2)+phi_in.sum()*inlet_speed**2/2))
    allocations=json.loads((thermal/'boundary-allocation.json').read_text());face_rows=[];external=0
    for face,allocation in allocations.items():
        ids=patch_indices(solid,face);tb=read_patch(tlast/'solid/T',face,len(ids))
        flux=conduction(solid,sc,st,face,tb,p.solid_conductivity)
        power=float(np.dot(flux,solid['area'][ids]));external+=power
        expected=-allocation['power_w'] if allocation['kind']=='heat' else float(np.dot(allocation['h_w_m2_k']*(tb-allocation['ambient_c']-273.15),solid['area'][ids]))
        face_rows.append({'face':face,**allocation,'mean_temperature_c':float(np.average(tb,weights=solid['area'][ids])-273.15),
            'computed_heat_leaving_w':power,'specified_boundary_heat_leaving_w':expected})
    qscale=max(sum(g.power_w for g in spec.boundaries if g.kind=='heat'),sum(abs(f['computed_heat_leaving_w']) for f in face_rows),abs(advective),1e-8)
    energy_error=100*abs(advective+inlet_cond+kinetic+external)/qscale
    # Match the two independent meshes by their conformal face centroids.
    solid_interface={}
    for name,patch in solid['patches'].items():
        if patch['type']!='mappedWall' or not patch['count']: continue
        ids=patch_indices(solid,name);tb=read_patch(tlast/'solid/T',name,len(ids));flux=conduction(solid,sc,st,name,tb,p.solid_conductivity)
        for i,temp,q in zip(ids,tb,flux): solid_interface[tuple(np.round(solid['cf'][i],11))]=(temp,q)
    temp_jumps=[];flux_jumps=[];interface_area=0;fluid_interface_out=0
    for name,patch in mesh['patches'].items():
        if name in ('inlet','outlet') or not patch['count']: continue
        ids=patch_indices(mesh,name);tb=read_patch(tlast/'fluid/T',name,len(ids));flux=conduction(mesh,centres,ft,name,tb,p.thermal_conductivity_w_m_k)
        interface_area+=float(mesh['area'][ids].sum());fluid_interface_out+=float(np.dot(flux,mesh['area'][ids]))
        for i,temp,q in zip(ids,tb,flux):
            other=solid_interface[tuple(np.round(mesh['cf'][i],11))]
            temp_jumps.append(abs(temp-other[0]));flux_jumps.append(abs(q+other[1]))
    jump_t=max(temp_jumps,default=0);jump_q=100*max(flux_jumps,default=0)/(qscale/max(interface_area,1e-20))
    checks={'thermal_converged':tconverged,'energy_balance_below_0_5_percent':energy_error<.5,
        'boundary_power_agreement_below_0_5_percent':max((100*abs(f['computed_heat_leaving_w']-f['specified_boundary_heat_leaving_w'])/qscale for f in face_rows),default=0)<.5,
        'interface_flux_mismatch_below_0_5_percent':jump_q<.5,'interface_temperature_continuity':jump_t<max(float(np.ptp(st)),float(np.ptp(ft)),1)*p.residual_tolerance}
    result['checks'].update({key:bool(value) for key,value in checks.items()})
    result['thermal']={'solution_iteration':int(tlast.name),'solid_cells':ns,
        'outlet_temperature_c':float(np.dot(phi_out,outlet_t)/qout-273.15),'maximum_solid_temperature_c':float(st.max()-273.15),
        'minimum_solid_temperature_c':float(st.min()-273.15),'advective_heat_gain_w':advective,
        'inlet_conductive_loss_w':inlet_cond,'kinetic_energy_transport_w':kinetic,
        'external_heat_leaving_w':external,'fluid_interface_heat_leaving_w':fluid_interface_out,
        'energy_balance_error_percent':energy_error,'maximum_interface_temperature_jump_k':jump_t,
        'maximum_interface_flux_mismatch_percent':jump_q,'faces':face_rows,
        'convergence':{**tconv,'converged':tconverged,'relative_saved_field_change':tchange}}
    return result


def field_surface(case,region,field,axis=None,fraction=.5):
    result=json.loads((case/'results.json').read_text())
    path=case/'constant/polyMesh' if region=='fluid' else case/'thermal/constant/solid/polyMesh'
    mesh=cached_mesh(str(path));n=mesh['cell_count']
    if field=='temperature':
        if 'thermal' not in result: raise ValueError('This run has no computed temperature fields.')
        values=read_internal(case/'thermal'/str(result['thermal']['solution_iteration'])/region/'T',count=n)-273.15
        label,unit='Cell temperature','°C'
    elif region!='fluid': raise ValueError('Pressure and speed are fluid fields.')
    elif field=='pressure':
        manifest=json.loads((case/'manifest.json').read_text())
        values=read_internal(case/str(result['solution_iteration'])/'p',count=n)*manifest['resolved_physics']['density_kg_m3'];label,unit='Cell pressure','Pa'
    else:
        values=np.linalg.norm(read_internal(case/str(result['solution_iteration'])/'U',3,n),axis=1);label,unit='Cell speed','m/s'
    vertices=[];triangles=[];cell_ids=[];colours=[]
    if axis is None:
        vertices=(mesh['points']*1000).tolist()
        for patch in mesh['patches'].values():
            for i in range(patch['start'],patch['start']+patch['count']):
                face=mesh['faces'][i];owner=int(mesh['owner'][i])
                for j in range(1,len(face)-1):
                    triangles.append([int(face[0]),int(face[j]),int(face[j+1])]);cell_ids.append(owner);colours.append(float(values[owner]))
    else:
        ax='xyz'.index(axis);points=mesh['points'];position=float(points[:,ax].min()+fraction*np.ptp(points[:,ax]));cuts={}
        for i,face in enumerate(mesh['faces']):
            xyz=points[face];d=xyz[:,ax]-position
            if np.all(d>0) or np.all(d<0): continue
            intersections=[]
            for a,b,da,db in zip(xyz,np.roll(xyz,-1,axis=0),d,np.roll(d,-1)):
                if abs(da)<1e-12: intersections.append(a)
                if da*db<0: intersections.append(a+(b-a)*da/(da-db))
            for owner in [int(mesh['owner'][i])]+([int(mesh['neighbour'][i])] if i<len(mesh['neighbour']) else []):
                cuts.setdefault(owner,[]).extend(intersections)
        others=[i for i in range(3) if i!=ax]
        for cell,points_in_cell in cuts.items():
            if len(points_in_cell)<3: continue
            xyz=np.unique(np.round(points_in_cell,12),axis=0)
            if len(xyz)<3: continue
            relative=xyz-xyz.mean(axis=0);order=np.argsort(np.arctan2(relative[:,others[1]],relative[:,others[0]]));xyz=xyz[order]
            start=len(vertices);vertices.extend((xyz*1000).tolist())
            for j in range(1,len(xyz)-1):
                triangles.append([start,start+j,start+j+1]);cell_ids.append(cell);colours.append(float(values[cell]))
    return {'vertices_mm':vertices,'bounds_mm':[(mesh['points'].min(axis=0)*1000).tolist(),(mesh['points'].max(axis=0)*1000).tolist()],
        'geometry_key':case.name,'faces':[{'id':'field','triangles':triangles,'values':colours,'cell_ids':cell_ids,'region':region,'selectable':False}],
        'label':label,'unit':unit,'range':[float(values.min()),float(values.max())],'cell_count':n,
        'description':'Computed finite-volume cell values. Surface facets use the adjacent cell; slices intersect actual cells.'}
