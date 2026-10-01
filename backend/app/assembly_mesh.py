"""Read actual ASCII polyMesh topology; support arbitrary first-order cells."""
from functools import lru_cache
import re

import numpy as np


def list_body(path):
    text=re.sub(r'//[^\n]*|/\*.*?\*/','',path.read_text(),flags=re.S)
    match=re.search(r'\bFoamFile\s*\{[^{}]*\}',text,re.S)
    text=text[match.end():] if match else text
    match=re.search(r'\b(\d+)\s*\(',text)
    if not match: raise ValueError(f'No ASCII list found in {path}')
    return int(match[1]),text[match.end():text.rfind(')')]


def patches(path):
    _,body=list_body(path)
    result={}
    for name,block in re.findall(r'([A-Za-z_]\w*)\s*\{([^{}]*)\}',body,re.S):
        count=re.search(r'\bnFaces\s+(\d+)',block);start=re.search(r'\bstartFace\s+(\d+)',block)
        if count and start:
            result[name]={'count':int(count[1]),'start':int(start[1]),
                'type':re.search(r'\btype\s+(\w+)',block)[1]}
    return result


def read_mesh(folder):
    count,body=list_body(folder/'points')
    points=np.fromstring(body.replace('(',' ').replace(')',' '),sep=' ').reshape(-1,3)
    if len(points)!=count: raise ValueError('Unexpected mesh point count.')
    count,body=list_body(folder/'faces')
    faces=[np.fromstring(values,sep=' ',dtype=int) for _,values in re.findall(r'(\d+)\s*\(([^()]*)\)',body)]
    if len(faces)!=count: raise ValueError('Unexpected mesh face count.')
    _,body=list_body(folder/'owner');owner=np.fromstring(body,sep=' ',dtype=int)
    _,body=list_body(folder/'neighbour');neighbour=np.fromstring(body,sep=' ',dtype=int)
    sf=[];cf=[]
    for face in faces:
        p=points[face];vectors=np.cross(p[1:-1]-p[0],p[2:]-p[0])/2
        weights=np.linalg.norm(vectors,axis=1)
        if weights.sum()<=0: raise ValueError('Degenerate mesh face.')
        sf.append(vectors.sum(axis=0));cf.append(np.average((p[0]+p[1:-1]+p[2:])/3,axis=0,weights=weights))
    sf=np.array(sf);area=np.linalg.norm(sf,axis=1)
    return {'points':points,'faces':faces,'owner':owner,'neighbour':neighbour,'sf':sf,'area':area,
        'cf':np.array(cf),'patches':patches(folder/'boundary'),'cell_count':int(max(owner.max(),neighbour.max())+1)}


def patch_indices(mesh,name):
    p=mesh['patches'][name]
    return np.arange(p['start'],p['start']+p['count'])


def wall_boundary(path):
    """Detach the fluid mesh for the hydraulic solve, preserving face order."""
    text=path.read_text()
    text=re.sub(r'\btype\s+mappedWall\s*;','type wall;',text)
    text=re.sub(r'\bneighbour(?:Region|Patch)\s+[^;]+;','',text)
    path.write_text(text)


def cad_wall_patches(path):
    """Gmsh surface groups default to patch; unassigned CAD fluid faces are walls.

    Preserve mappedWall coupling and the explicitly named inlet/outlet patches.
    Wall-function turbulence fields require an actual wall polyPatch.
    """
    text=path.read_text()
    def replace(match):
        body=re.sub(r'\btype\s+patch\s*;', 'type wall;', match[2])
        return match[1]+'{'+body+'}'
    path.write_text(re.sub(r'(\bf_cad_\d+\s*)\{([^{}]*)\}', replace, text))


@lru_cache(maxsize=6)
def cached_mesh(path):
    from pathlib import Path
    return read_mesh(Path(path))
