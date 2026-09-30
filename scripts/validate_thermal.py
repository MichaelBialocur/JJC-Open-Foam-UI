"""Repeat the thermal mesh study on existing, converged Re=100 flow cases.

Example: .venv/bin/python scripts/validate_thermal.py <coarse-case> <medium-case> <fine-case>
For a completely fresh coupled workflow use scripts/validate.py --case heated_laminar.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.models import PRESETS, PipeDefinition
from backend.app.runner import foam_environment
from backend.app.thermal import prepare_thermal, analyse_thermal


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('flow_cases', nargs='+', type=Path)
    parser.add_argument('--output', type=Path, default=Path('validation-output/thermal'))
    args = parser.parse_args()
    env = foam_environment()
    args.output.mkdir(parents=True, exist_ok=True)
    rows = []
    for source in args.flow_cases:
        source = source.resolve()
        flow = json.loads((source / 'results.json').read_text())
        original = json.loads((source / 'manifest.json').read_text())['inputs']
        spec = PipeDefinition(**{**PRESETS['heated_laminar']['inputs'], 'mesh_level': original['mesh_level']})
        thermal_keys = {'applied_heat_w', 'thermal_iterations', 'specific_heat_j_kg_k', 'thermal_conductivity_w_m_k', 'turbulent_prandtl'}
        actual = PipeDefinition(**original).model_dump()
        if any(actual[key] != value for key, value in spec.model_dump().items() if key not in thermal_keys):
            raise ValueError(f'{source}: flow inputs do not match the thermal benchmark.')
        if not flow['convergence']['converged']:
            raise ValueError(f'{source}: flow is not converged.')
        target = (args.output / str(uuid4())).resolve()
        target.mkdir()
        for name in ('constant', 'system', '0', f"{flow['solution_iteration']:g}"):
            shutil.copytree(source / name, target / name)
        (target / 'flow-provenance.json').write_text(json.dumps({'source_case': str(source), 'inputs': original,
            'convergence': flow['convergence']}, indent=2))
        thermal = prepare_thermal(target, spec, flow['solution_iteration'])
        print(f'{spec.mesh_level}: solving temperature on {spec.mesh_shape} computed flow cells', flush=True)
        with (target / 'log.thermal').open('w') as log:
            subprocess.run(['foamRun', '-case', str(thermal)], env=env, stdout=log, stderr=subprocess.STDOUT, check=True, timeout=1800)
        result = analyse_thermal(target, spec, flow)
        (target / 'thermal-results.json').write_text(json.dumps(result, indent=2, allow_nan=False))
        row = {'mesh': spec.mesh_level, 'cells': spec.mesh_shape[0] * spec.mesh_shape[1], 'case': str(target),
               'flow_case_id': source.name, 'nusselt': result['developed_nusselt'],
               'nusselt_error_percent': result['validation']['nusselt_error_percent'],
               'energy_error_percent': result['energy_balance_error_percent'],
               'outlet_bulk_temperature_c': result['outlet_bulk_temperature_c'],
               'advected_heat_w': result['advected_heat_w'], 'inlet_conduction_loss_w': result['inlet_conduction_loss_w'],
               'nusselt_drift_percent': result['nusselt_drift_percent'],
               'convergence': result['convergence'], 'validation': result['validation']}
        rows.append(row)
        (args.output / 'summary.json').write_text(json.dumps({'openfoam': 'Foundation 14', 'results': rows}, indent=2, allow_nan=False))
        print(json.dumps({k:v for k,v in row.items() if k not in ('convergence','validation')}), flush=True)
    return int(any(row['validation']['status'] != 'within_project_target' for row in rows))


if __name__ == '__main__':
    raise SystemExit(main())
