"""Import closed OpenCASCADE bodies and mesh explicitly assigned CFD domains.

STEP/IGES declared length units are converted to mm by OpenCASCADE. BREP has
no unit declaration and is interpreted as mm. Mesh export alone converts to m.
Runs in a subprocess: Gmsh's global model is never shared between API requests.
"""
import argparse
import json
from pathlib import Path

import numpy as np

from .cad_models import CadGeometry


def build(source, folder, geometry=None, mesh_size_mm=None, inlet_faces=(), outlet_faces=()):
    import gmsh
    folder.mkdir(parents=True, exist_ok=True)
    gmsh.initialize(['cad-import'], readConfigFiles=False)
    try:
        for option in ('General.NumThreads', 'Mesh.MaxNumThreads1D', 'Mesh.MaxNumThreads2D', 'Mesh.MaxNumThreads3D'):
            gmsh.option.setNumber(option, 1)
        gmsh.option.setString('Geometry.OCCTargetUnit', 'MM')
        # The import scale preserves analytic planes/circles. OCC's general
        # dilation converts them to B-splines and can alter mass integration.
        gmsh.option.setNumber('Geometry.OCCScaling', geometry.scale if geometry else 1)
        gmsh.option.setNumber('Geometry.Tolerance', 1e-7)
        gmsh.model.add('imported-cad')
        occ = gmsh.model.occ
        occ.importShapes(str(source))
        volumes = occ.getEntities(3)
        if not volumes:
            # IGES often describes a closed shell rather than a solid. Sew only;
            # do not delete small engineering features or fill arbitrary holes.
            occ.healShapes(tolerance=1e-7, fixDegenerated=False, fixSmallEdges=False,
                           fixSmallFaces=False, sewFaces=True, makeSolids=True)
            volumes = occ.getEntities(3)
        if not volumes:
            raise ValueError('No closed volume was found. Export watertight solid bodies, including the fluid volume. Open surface sheets cannot be simulated.')
        if any(occ.getMass(3, tag) <= 1e-12 for _, tag in volumes):
            raise ValueError('The file contains a zero-volume or invalid body. Repair it in CAD and export again.')
        occ.synchronize()
        if any(not len(gmsh.model.getAdjacencies(2, tag)[0]) for _, tag in gmsh.model.getEntities(2)):
            raise ValueError('The file contains open surface sheets alongside solids. Export closed bodies only, or repair the sheets in CAD.')
        bodies = [{'id': f'v_{tag}', 'name': gmsh.model.getEntityName(3, tag) or f'Body {i+1}',
                   'volume_mm3': occ.getMass(3, tag), 'bounds_mm': list(occ.getBoundingBox(3, tag))}
                  for i, (_, tag) in enumerate(sorted(volumes))]
        valid = {b['id'] for b in bodies}
        fluid, solid = set(), set()
        if geometry:
            if not set(geometry.fluid_bodies + geometry.solid_bodies) <= valid:
                raise ValueError('A selected body does not exist in this CAD file. Import it again and assign its bodies.')
            chosen = set(geometry.fluid_bodies + geometry.solid_bodies)
            occ.remove([(3, tag) for _, tag in volumes if f'v_{tag}' not in chosen], recursive=True)
            volumes = occ.getEntities(3)
            # Match the canonical cache key: selection order must not change
            # boolean topology or the face IDs replayed during volume meshing.
            fv = [(3, int(v[2:])) for v in sorted(geometry.fluid_bodies)]
            sv = [(3, int(v[2:])) for v in sorted(geometry.solid_bodies)]
            if len(fv) > 1:
                fv = [p for p in occ.fuse(fv[:1], fv[1:])[0] if p[0] == 3]
            if len(fv) != 1:
                raise ValueError('Selected fluid bodies are disconnected. Include connecting manifolds, or simulate each separate fluid circuit independently.')
            if sv:
                result, maps = occ.fragment(sv, fv)
                solid = {v for mapping in maps[:len(sv)] for dim, v in mapping if dim == 3}
                fluid = {v for mapping in maps[len(sv):] for dim, v in mapping if dim == 3}
                if solid & fluid:
                    raise ValueError('Fluid and solid bodies overlap. Export the actual fluid cavity, excluding the metal.')
                for i, mapping in enumerate(maps[:len(sv)]):
                    if any(set(mapping) & set(other) for other in maps[i+1:len(sv)]):
                        raise ValueError('Solid bodies overlap. Remove the overlapping material in CAD before importing.')
                if {v for dim, v in result if dim == 3} != solid | fluid:
                    raise ValueError('An unassigned volume remains after CAD imprinting.')
            else:
                fluid = {v for _, v in fv}
            occ.synchronize()
        active = fluid | solid if geometry else {v for _, v in volumes}
        surfaces = {s for v in active for dim, s in gmsh.model.getBoundary([(3, v)], oriented=False) if dim == 2}
        rows = []
        for tag in sorted(surfaces):
            adjacent = set(map(int, gmsh.model.getAdjacencies(2, tag)[0])) & active
            fs, ss = adjacent & fluid, adjacent & solid
            if geometry and len(adjacent) > 1 and not (fs and ss):
                continue  # Internal same-material faces.
            interface = bool(fs and ss)
            region = 'interface' if interface else 'fluid' if fs else 'solid'
            curves = {str(c): occ.getMass(1, c) for dim, c in gmsh.model.getBoundary([(2, tag)], oriented=False) if dim == 1}
            rows.append({'id': f'f_cad_{tag}', 'tag': tag, 'label': f'Face {tag} · {gmsh.model.getType(2, tag)}',
                'body_ids': [f'v_{v}' for v in sorted(adjacent)], 'area_mm2': occ.getMass(2, tag),
                'center_mm': list(occ.getCenterOfMass(2, tag)), 'curves_mm': curves,
                'planar': gmsh.model.getType(2, tag) == 'Plane', 'region': region,
                'selectable': not interface, 'thermal_selectable': bool(ss) and not interface,
                'port_selectable': bool(fs) and not interface})
        if geometry and solid and not any(f['region'] == 'interface' for f in rows):
            raise ValueError('The fluid and solid bodies do not touch. Check the CAD placement, gaps, and fluid-volume definition.')
        if geometry and solid:
            connected = set(fluid)
            changed = True
            while changed:
                before = len(connected)
                for tag in surfaces:
                    neighbours = set(map(int, gmsh.model.getAdjacencies(2, tag)[0])) & active
                    if neighbours & connected:
                        connected |= neighbours
                changed = len(connected) != before
            if connected != active:
                raise ValueError('A selected solid body is disconnected from the fluid and other solids. Ignore that body or repair the CAD contact.')
        bounds = np.array([occ.getBoundingBox(3, v) for v in active])
        low, high = bounds[:, :3].min(axis=0), bounds[:, 3:].max(axis=0)
        extent = float(np.max(high-low))
        size = mesh_size_mm if mesh_size_mm is not None else max(extent/30, .01)
        for option, value in {'Mesh.MeshSizeMax': size, 'Mesh.MeshSizeMin': size/8,
            'Mesh.MeshSizeFromCurvature': 24, 'Mesh.ElementOrder': 1, 'Mesh.Algorithm': 6,
            'Mesh.Algorithm3D': 1, 'Mesh.MshFileVersion': 2.2, 'Mesh.ScalingFactor': .001}.items():
            gmsh.option.setNumber(option, value)
        if geometry:
            gmsh.model.addPhysicalGroup(3, sorted(fluid), name='fluid')
            if solid:
                gmsh.model.addPhysicalGroup(3, sorted(solid), name='solid')
            if mesh_size_mm is not None:
                ports = set(inlet_faces) | set(outlet_faces)
                eligible = {f['id'] for f in rows if f['port_selectable'] and f['planar']}
                if not inlet_faces or not outlet_faces or not ports <= eligible or set(inlet_faces) & set(outlet_faces):
                    raise ValueError('Select separate planar fluid inlet and outlet faces before meshing.')
                for name, selection in [('inlet', inlet_faces), ('outlet', outlet_faces)]:
                    gmsh.model.addPhysicalGroup(2, [f['tag'] for f in rows if f['id'] in selection], name=name)
            else:
                ports = set()
            for face in rows:
                if face['selectable'] and face['id'] not in ports:
                    gmsh.model.addPhysicalGroup(2, [face['tag']], name=face['id'])
        gmsh.model.mesh.generate(3 if mesh_size_mm is not None else 2)
        count = None
        if mesh_size_mm is not None:
            gmsh.model.mesh.optimize('Netgen')
            count = sum(len(a) for a in gmsh.model.mesh.getElements(3)[1])
            print(f'Imported CAD mesh: {count:,} cells. No application cell-count cap.', flush=True)
            gmsh.write(str(folder/'assembly.msh'))
        nodes, xyz, _ = gmsh.model.mesh.getNodes()
        coordinates = dict(zip(map(int, nodes), np.asarray(xyz).reshape(-1, 3)))
        used, vertices = {}, []
        for face in rows:
            tag = face.pop('tag')
            face['triangles'] = []
            kinds, _, connectivity = gmsh.model.mesh.getElements(2, tag)
            for kind, conn in zip(kinds, connectivity):
                if kind != 2:
                    raise ValueError('Expected first-order triangular CAD surfaces.')
                for tri in np.asarray(conn).reshape(-1, 3):
                    indices = []
                    for node in map(int, tri):
                        if node not in used:
                            used[node] = len(vertices)
                            vertices.append(coordinates[node].tolist())
                        indices.append(used[node])
                    face['triangles'].append(indices)
            if face['port_selectable'] and face['planar'] and face['triangles']:
                point = np.mean([vertices[i] for i in face['triangles'][0]], axis=0)
                uv = gmsh.model.getParametrization(2, tag, point.tolist())
                normal = np.array(gmsh.model.getNormal(tag, uv))
                fv = next(iter(set(map(int, gmsh.model.getAdjacencies(2, tag)[0])) & fluid))
                epsilon = max(min(np.sqrt(face['area_mm2']), extent)*1e-5, 1e-8)
                plus = gmsh.model.isInside(3, fv, (point+epsilon*normal).tolist())
                minus = gmsh.model.isInside(3, fv, (point-epsilon*normal).tolist())
                if bool(plus) == bool(minus):
                    raise ValueError('Could not establish the interior of a fluid port. Repair the CAD body or increase its geometric scale.')
                face['outward_normal'] = ((-1 if plus else 1)*normal).tolist()
        payload = {'geometry_key': geometry.key if geometry else None, 'vertices_mm': vertices, 'faces': rows,
            'bodies': bodies, 'bounds_mm': [low.tolist(), high.tolist()], 'cells': count,
            'fluid_volume_mm3': sum(occ.getMass(3, v) for v in fluid),
            'solid_volume_mm3': sum(occ.getMass(3, v) for v in solid),
            'engine': 'Gmsh 4.15.2 / OpenCASCADE', 'source_kind': 'cad',
            'unit_note': 'STEP/IGES declared units converted to mm; BREP coordinates interpreted as mm. Explicit scale applied when preparing bodies.'}
        folder.mkdir(parents=True, exist_ok=True)
        (folder/'geometry.json').write_text(json.dumps(payload, separators=(',', ':'), allow_nan=False))
        return payload
    finally:
        gmsh.finalize()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('source'); parser.add_argument('output'); parser.add_argument('--spec')
    parser.add_argument('--size', type=float)
    args = parser.parse_args()
    data = json.loads(Path(args.spec).read_text()) if args.spec else None
    geometry = CadGeometry.model_validate(data.get('geometry', data)) if data else None
    build(Path(args.source), Path(args.output), geometry, args.size,
          data.get('inlet_faces', []) if data else [], data.get('outlet_faces', []) if data else [])
