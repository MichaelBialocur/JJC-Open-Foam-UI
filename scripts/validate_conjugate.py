"""Solve conjugate heating on existing converged flow cases, recording provenance.

Pass coarse/medium/fine cases from scripts/validate.py --case laminar.
Use --material copper or --wall-mm 4 for independent material/thickness checks.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.models import PipeDefinition, PRESETS
from backend.app.runner import foam_environment
from backend.app.thermal import prepare_thermal, analyse_thermal
from backend.app.fields import build_fields, meridional_vtk


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flow_cases', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, default=Path('validation-output/conjugate'))
    parser.add_argument('--material', choices=['aluminium','copper'], default='aluminium')
    parser.add_argument('--wall-mm', type=float, default=2)
    parser.add_argument('--power', type=float, default=10)
    parser.add_argument('--iterations', type=int, default=2000)
    parser.add_argument('--fluid-cp', type=float)
    parser.add_argument('--fluid-k', type=float)
    args = parser.parse_args()
    env = foam_environment()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in args.flow_cases:
        source = source.resolve()
        flow = json.loads((source / 'results.json').read_text())
        original = json.loads((source / 'manifest.json').read_text())['inputs']
        # v0.2 flow manifests predate thermal properties. Use the documented air
        # values for its named Superpipe preset, or explicit overrides.
        thermal_defaults = PRESETS['superpipe' if original.get('reference')=='superpipe_41727' else 'heated_wall']['inputs']
        properties = {key:original.get(key,thermal_defaults[key]) for key in ('specific_heat_j_kg_k','thermal_conductivity_w_m_k')}
        if args.fluid_cp is not None: properties['specific_heat_j_kg_k']=args.fluid_cp
        if args.fluid_k is not None: properties['thermal_conductivity_w_m_k']=args.fluid_k
        spec = PipeDefinition(**{**original, **properties, 'thermal_mode':'conjugate', 'applied_heat_w':args.power,
            'thermal_iterations':args.iterations, 'material':args.material, 'wall_thickness_mm':args.wall_mm})
        if not flow['convergence']['converged']:
            raise ValueError(f'{source}: flow is not converged.')
        target = (args.output / str(uuid4())).resolve()
        target.mkdir()
        for name in ('constant','system','0',f"{flow['solution_iteration']:g}"):
            shutil.copytree(source / name, target / name)
        (target / 'flow-provenance.json').write_text(json.dumps({'source_case':str(source),'inputs':original,
            'note':'Only wall and thermal inputs changed; flow geometry/BCs/properties and computed U/phi/nut are reused.',
            'convergence':flow['convergence']},indent=2))
        thermal = prepare_thermal(target, spec, flow['solution_iteration'])
        commands = [('solidMesh',['blockMesh','-region','solid']),('solidCheck',['checkMesh','-region','solid']),
                    ('solidCentres',['foamPostProcess','-region','solid','-func','writeCellCentres','-time','0']),
                    ('thermal',['foamMultiRun'])]
        print(f'{spec.mesh_level} {args.material}, wall {args.wall_mm} mm: {target.name}',flush=True)
        for name, command in commands:
            with (target / f'log.{name}').open('w') as log:
                subprocess.run([*command,'-case',str(thermal)],env=env,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1800)
        if 'Mesh OK.' not in (target/'log.solidCheck').read_text():
            raise ValueError('Solid mesh check failed.')
        result = analyse_thermal(target,spec,flow)
        flow.update(thermal=result,thermal_solved=True)
        (target/'results.json').write_text(json.dumps(flow,indent=2,allow_nan=False))
        (target/'job.json').write_text(json.dumps({'inputs':spec.model_dump()}))
        fields = build_fields(target,spec,flow)
        (target/'fields.json').write_text(json.dumps(fields,allow_nan=False))
        (target/'solid-section.vtk').write_text(meridional_vtk(fields['solid']))
        row = {'mesh':spec.mesh_level,'case':str(target),'flow_case_id':source.name,'inputs':spec.model_dump(),
               'thermal':result}
        rows.append(row)
        (args.output/'summary.json').write_text(json.dumps({'openfoam':'Foundation 14','results':rows},indent=2,allow_nan=False))
        print(json.dumps({'status':result['validation']['status'],'converged':result['convergence']['converged'],
            'energy_error_percent':result['energy_balance_error_percent'],**result['solid']}),flush=True)
    return int(any(row['thermal']['validation']['status']!='within_project_target' for row in rows))


if __name__=='__main__':
    raise SystemExit(main())
