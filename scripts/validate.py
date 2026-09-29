"""Run actual OpenFOAM cases and record errors; never generate substitute CFD data."""
import argparse
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.app.models import PRESETS, PipeDefinition
from backend.app.runner import ACTIVE, JobManager, health


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--case', choices=['laminar', 'superpipe', 'all'], default='laminar')
    parser.add_argument('--meshes', nargs='+', choices=['coarse', 'medium', 'fine'], default=['coarse', 'medium', 'fine'])
    parser.add_argument('--output', default='validation-output')
    args = parser.parse_args()
    status = health()
    if not status['available']:
        print(status['error'], file=sys.stderr)
        return 2
    root = Path(args.output).resolve()
    manager = JobManager(root / 'cases')
    rows = []
    failed = False
    try:
        for name in (['laminar','superpipe'] if args.case == 'all' else [args.case]):
            previous_f = None
            for mesh in args.meshes:
                spec = PipeDefinition(**{**PRESETS[name]['inputs'], 'mesh_level': mesh})
                run = manager.submit(spec)
                print(f'{name}/{mesh}: {run["id"]}', flush=True)
                while True:
                    snapshot = manager.snapshot(run['id'])
                    if snapshot['status'] not in ACTIVE:
                        break
                    time.sleep(.5)
                result = snapshot.get('results')
                if not result:
                    print(snapshot.get('error') or snapshot['status'], file=sys.stderr)
                    rows.append({'case': name, 'mesh': mesh, 'status': snapshot['status'], 'error': snapshot.get('error')})
                    failed = True
                    continue
                f = result['darcy_friction_factor']
                row = {'case':name, 'mesh':mesh, 'run_id':run['id'], 'cells':spec.mesh_shape[0]*spec.mesh_shape[1],
                       'status':snapshot['status'], 'reynolds':spec.reynolds, 'darcy_f':f,
                       'friction_error_percent':result['validation']['friction_error_percent'],
                       'profile_rmse_percent':result['validation']['profile_rmse_percent_of_bulk'],
                       'profile_comparison_points':result['validation']['profile_comparison_points'],
                       'mass_balance_error_percent':result['mass_balance_error_percent'],
                       'y_plus_estimate':result['estimated_y_plus'], 'validation_status':result['validation']['status'],
                       'checks':result['validation']['checks'],
                       'change_from_previous_mesh_percent':None if previous_f is None else 100*abs(f-previous_f)/abs(f),
                       'convergence_basis':result['convergence']['convergence_basis']}
                rows.append(row); previous_f = f
                print(json.dumps(row), flush=True)
                # Verification must pass; experiments may expose model error, which is reported.
                failed |= snapshot['status'] != 'completed'
                if name == 'laminar':
                    failed |= result['validation']['status'] != 'within_project_target'
                (root/'summary.json').write_text(json.dumps({'openfoam':status,'results':rows},indent=2))
    except KeyboardInterrupt:
        print('Cancelling validation runs…', file=sys.stderr)
        return 130
    finally:
        manager.close()
    (root/'summary.json').write_text(json.dumps({'openfoam':status,'results':rows},indent=2))
    return 1 if failed else 0


if __name__ == '__main__':
    raise SystemExit(main())
