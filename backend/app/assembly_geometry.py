"""OpenCASCADE geometry and conforming Gmsh meshes. Run in an isolated process.

All construction dimensions are mm. The final mesh is scaled to SI metres.
Solid pieces retain their part identity; shared solid/fluid faces are imprinted.
"""
import argparse
import json
from math import pi, sin, cos, ceil, radians
from pathlib import Path

import numpy as np

from .assembly_models import AssemblyGeometry


def build(geometry, folder, mesh_size_mm=2, volume_mesh=False):
    import gmsh
    gmsh.initialize(['assembly'],readConfigFiles=False)
    try:
        gmsh.option.setNumber('General.NumThreads',1)
        gmsh.option.setNumber('Mesh.MaxNumThreads1D',1)
        gmsh.option.setNumber('Mesh.MaxNumThreads2D',1)
        gmsh.option.setNumber('Mesh.MaxNumThreads3D',1)
        gmsh.option.setNumber('Geometry.Tolerance',1e-7)
        gmsh.model.add('assembly')
        occ=gmsh.model.occ
        layout=geometry.layout()

        def wire(center,t,n,shape,dimensions,segmented=False):
            b=np.cross(t,n)
            if shape=='round':
                if segmented:
                    c=occ.addPoint(*center)
                    points=[occ.addPoint(*(center+dimensions[0]*(cos(a)*n+sin(a)*b))) for a in (-3*pi/4,-pi/4,pi/4,3*pi/4)]
                    return occ.addWire([occ.addCircleArc(points[i],c,points[(i+1)%4]) for i in range(4)])
                return occ.addWire([occ.addCircle(*center,dimensions[0],zAxis=t.tolist(),xAxis=n.tolist())])
            w,h=dimensions
            points=[occ.addPoint(*(center+x*w/2*n+y*h/2*b)) for x,y in [(-1,-1),(1,-1),(1,1),(-1,1)]]
            return occ.addWire([occ.addLine(points[i],points[(i+1)%4]) for i in range(4)])

        def section_dims(section,outer,part,channel=None):
            if section.shape=='round':
                return [section.diameter_mm/2+(section.wall_mm if outer else 0)],0
            if outer:
                return [section.width_mm,section.height_mm],0
            if channel is None:
                return [section.width_mm-2*section.wall_mm,section.height_mm-2*section.wall_mm],0
            w=(section.width_mm-2*section.wall_mm-(part.channels-1)*part.web_mm)/part.channels
            offset=-section.width_mm/2+section.wall_mm+w/2+channel*(w+part.web_mm)
            return [w,section.height_mm-2*section.wall_mm],offset

        def body(part,row,outer,channel=None):
            p=np.array(row['start_mm']);t=np.array(row['tangent']);n=np.array(row['normal'])
            bend_n=np.array(row['bend_normal']);axis=np.cross(t,bend_n)
            d0,o0=section_dims(part.start,outer,part,channel)
            d1,o1=section_dims(part.end,outer,part,channel)
            segmented=part.start.shape!=part.end.shape
            start=wire(p+o0*n,t,n,part.start.shape,d0,segmented)
            # Exact toroidal/rectangular bend for a constant section.
            if part.kind=='bend' and part.start.shape==part.end.shape and np.allclose(d0,d1,rtol=0,atol=1e-10):
                surface=occ.addPlaneSurface([start])
                c=p+part.radius_mm*bend_n
                return [tag for dim,tag in occ.revolve([(2,surface)],*c,*axis,radians(part.angle_deg)) if dim==3]
            wires=[start]
            fractions=np.linspace(0,1,max(2,ceil(part.angle_deg/15)+1)) if part.kind=='bend' else [0,1]
            for f in fractions[1:]:
                if part.kind=='bend':
                    a=radians(part.angle_deg)*f
                    center=p+part.radius_mm*(sin(a)*t+(1-cos(a))*bend_n)
                    tangent=cos(a)*t+sin(a)*bend_n
                    normal=cos(a)*n+sin(a)*np.cross(axis,n)+(1-cos(a))*np.dot(axis,n)*axis
                    dims=(np.array(d0)*(1-f)+np.array(d1)*f).tolist()
                else:
                    center=p+part.length_mm*f*t;tangent=t;normal=n;dims=d1
                wires.append(wire(center+((1-f)*o0+f*o1)*normal,tangent,normal,part.end.shape,dims,segmented))
            return [tag for dim,tag in occ.addThruSections(wires,makeSolid=True,makeRuled=part.kind!='bend') if dim==3]

        outer_parts=[];fluid_parts=[]
        for part,row in zip(geometry.parts,layout):
            outer_parts.append(body(part,row,True))
            fluid_parts.extend(body(part,row,False,i) for i in (range(part.channels) if part.kind=='multiport' else [None]))
        for i,volumes in enumerate(outer_parts):
            for other in outer_parts[i+1:]:
                for a in volumes:
                    for b in other:
                        aa=np.array(occ.getBoundingBox(3,a));bb=np.array(occ.getBoundingBox(3,b))
                        if np.any(np.minimum(aa[3:],bb[3:])-np.maximum(aa[:3],bb[:3])<1e-5): continue
                        overlap=occ.intersect(occ.copy([(3,a)]),occ.copy([(3,b)]))[0]
                        volume=sum(occ.getMass(dim,tag) for dim,tag in overlap if dim==3)
                        if overlap: occ.remove(overlap,recursive=True)
                        if volume>1e-5: raise ValueError('Assembly parts overlap away from their connection. Change a length, bend radius or bend plane.')
        fluid=[(3,v) for part in fluid_parts for v in part]
        if len(fluid)>1:
            fluid=occ.fuse(fluid[:1],fluid[1:])[0]
        solid=[]; owners=[]
        for part,volumes in zip(geometry.parts,outer_parts):
            cut=occ.cut([(3,v) for v in volumes],fluid,removeTool=False)[0]
            for item in cut:
                if item[0]==3: solid.append(item);owners.append(part.id)
        if not solid or not fluid:
            raise ValueError('Construction did not produce both fluid and solid volumes.')
        result,maps=occ.fragment(solid,fluid)
        owner_by_volume={v:owner for owner,mapping in zip(owners,maps[:len(solid)]) for dim,v in mapping if dim==3}
        fluid_volumes={v for mapping in maps[len(solid):] for dim,v in mapping if dim==3}
        if fluid_volumes.intersection(owner_by_volume):
            raise ValueError('Solid and fluid volumes overlap after construction.')
        if {v for dim,v in result if dim==3}!=fluid_volumes|set(owner_by_volume):
            raise ValueError('An unclassified geometry volume remains.')
        occ.synchronize()
        # A shared volume between two non-adjacent solid parts indicates a collision.
        for i,mapping in enumerate(maps[:len(solid)]):
            for j in range(i+1,len(solid)):
                if owners[i]!=owners[j] and set(mapping)&set(maps[j]):
                    raise ValueError(f'Parts {owners[i]} and {owners[j]} overlap. Change their path or bend radius.')
        surfaces={s for v in fluid_volumes|set(owner_by_volume) for dim,s in gmsh.model.getBoundary([(3,v)],oriented=False) if dim==2}
        per_part={p.id:[] for p in geometry.parts};interface=[];inlet=[];outlet=[]
        start=np.array(layout[0]['start_mm']);t0=np.array(layout[0]['tangent'])
        end=np.array(layout[-1]['end_mm']);te=np.array(layout[-1]['end_tangent'])
        for tag in surfaces:
            adjacent=set(map(int,gmsh.model.getAdjacencies(2,tag)[0]))
            fs=adjacent&fluid_volumes;ss=adjacent&set(owner_by_volume)
            center=np.array(occ.getCenterOfMass(2,tag))
            if fs and ss: interface.append(tag)
            elif fs and len(adjacent)==1:
                planar=gmsh.model.getType(2,tag)=='Plane'
                if planar and abs(np.dot(center-start,t0))<1e-5: inlet.append(tag)
                elif planar and abs(np.dot(center-end,te))<1e-5: outlet.append(tag)
                else: raise ValueError('An unintended opening exists in the fluid domain. Check connected section dimensions.')
            elif ss and len(adjacent)==1:
                per_part[owner_by_volume[next(iter(ss))]].append(tag)
        if not inlet or not outlet or not interface:
            raise ValueError('The geometry needs open inlet/outlet faces and a closed fluid–solid interface.')
        face_rows=[]
        for part,row in zip(geometry.parts,layout):
            p=np.array(row['start_mm']);t=np.array(row['tangent']);n=np.array(row['normal']);b=np.cross(t,n)
            tags=sorted(per_part[part.id],key=lambda s:tuple(np.round(np.array(occ.getCenterOfMass(2,s))-p,7)))
            for i,tag in enumerate(tags):
                label='Outer wall'
                if gmsh.model.getType(2,tag)=='Plane':
                    bounds=gmsh.model.getParametrizationBounds(2,tag)
                    normal=np.array(gmsh.model.getNormal(tag,(np.array(bounds[0])+np.array(bounds[1]))/2))
                    center=np.array(occ.getCenterOfMass(2,tag));offset=center-(p+np.array(row['end_mm']))/2
                    scores=np.abs([normal@t,normal@n,normal@b]);axis=int(np.argmax(scores))
                    if scores[axis]>.95:
                        label=[('Start end','End end'),('Left side','Right side'),('Bottom','Top')][axis][int(offset@[t,n,b][axis]>0)]
                face_rows.append({'id':f'f_{part.id}_{i}','label':f'{part.name} · {label} {i+1}',
                    'part_id':part.id,'area_mm2':occ.getMass(2,tag),'tag':tag,'selectable':True,'region':'solid'})
        for name,tags in [('inlet',inlet),('outlet',outlet),('interface',interface)]:
            for i,tag in enumerate(sorted(tags)):
                face_rows.append({'id':f'{name}_{i}','label':name,'part_id':None,'area_mm2':occ.getMass(2,tag),
                    'tag':tag,'selectable':False,'region':'fluid'})
        volume_fluid=sum(occ.getMass(3,v) for v in fluid_volumes)
        volume_solid=sum(occ.getMass(3,v) for v in owner_by_volume)
        for name,tags in [('fluid',sorted(fluid_volumes)),('solid',sorted(owner_by_volume))]:
            gmsh.model.addPhysicalGroup(3,tags,name=name)
        gmsh.model.addPhysicalGroup(2,inlet,name='inlet');gmsh.model.addPhysicalGroup(2,outlet,name='outlet')
        for face in face_rows:
            if face['selectable']: gmsh.model.addPhysicalGroup(2,[face['tag']],name=face['id'])
        gmsh.option.setNumber('Mesh.MeshSizeMax',mesh_size_mm)
        gmsh.option.setNumber('Mesh.MeshSizeMin',mesh_size_mm/8)
        gmsh.option.setNumber('Mesh.MeshSizeFromCurvature',20)
        gmsh.option.setNumber('Mesh.ElementOrder',1)
        gmsh.option.setNumber('Mesh.Algorithm',6)
        gmsh.option.setNumber('Mesh.Algorithm3D',1)
        gmsh.option.setNumber('Mesh.MshFileVersion',2.2)
        gmsh.option.setNumber('Mesh.ScalingFactor',.001)
        gmsh.model.mesh.generate(3 if volume_mesh else 2)
        if volume_mesh:
            count=sum(len(a) for a in gmsh.model.mesh.getElements(3)[1])
            if count>600000: raise ValueError(f'The mesh has {count:,} cells; increase target cell size to stay below 600,000.')
            gmsh.model.mesh.optimize('Netgen')
            count=sum(len(a) for a in gmsh.model.mesh.getElements(3)[1])
            if count>600000: raise ValueError(f'The optimized mesh has {count:,} cells; increase target cell size.')
            gmsh.write(str(folder/'assembly.msh'))
        nodes,coords,_=gmsh.model.mesh.getNodes()
        node_map={int(tag):xyz for tag,xyz in zip(nodes,np.asarray(coords).reshape(-1,3))}
        used={};vertices=[]
        for face in face_rows:
            face['triangles']=[]
            kinds,_,connectivity=gmsh.model.mesh.getElements(2,face.pop('tag'))
            for kind,conn in zip(kinds,connectivity):
                if kind!=2: raise ValueError('Expected first-order triangular surface elements.')
                for tri in np.asarray(conn).reshape(-1,3):
                    indices=[]
                    for node in tri:
                        node=int(node)
                        if node not in used: used[node]=len(vertices);vertices.append(node_map[node].tolist())
                        indices.append(used[node])
                    face['triangles'].append(indices)
        area,perimeter=geometry.parts[0].section_flow()
        payload={'geometry_key':geometry.key,'vertices_mm':vertices,'faces':face_rows,'layout':layout,
            'inlet_area_m2':area*1e-6,'hydraulic_diameter_mm':4*area/perimeter,
            'fluid_volume_mm3':volume_fluid,'solid_volume_mm3':volume_solid,
            'cells':count if volume_mesh else None,'engine':'Gmsh 4.15.2 / OpenCASCADE'}
        (folder/'geometry.json').write_text(json.dumps(payload,separators=(',',':'),allow_nan=False))
        return payload
    finally:
        gmsh.finalize()


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('input');parser.add_argument('output')
    parser.add_argument('--size',type=float,default=2);parser.add_argument('--mesh',action='store_true')
    args=parser.parse_args();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True)
    geometry=AssemblyGeometry.model_validate_json(Path(args.input).read_text())
    build(geometry,folder,args.size,args.mesh)
