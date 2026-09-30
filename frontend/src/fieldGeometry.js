import * as THREE from 'three'

const palette = [[68,1,84], [59,82,139], [33,145,140], [94,201,98], [253,231,37]]
export function fieldColor(value, min, max) {
  const t = Math.max(0, Math.min(1, (value - min) / (max - min || 1))) * (palette.length - 1)
  const index = Math.min(palette.length - 2, Math.floor(t)), weight = t - index
  return palette[index].map((v, i) => Math.round(v + weight * (palette[index + 1][i] - v)))
}

export function locateCell(edges, coordinate) {
  if (coordinate < edges[0] || coordinate > edges.at(-1)) return null
  let lo = 0, hi = edges.length - 2
  while (lo < hi) { const mid = Math.floor((lo + hi) / 2); if (coordinate >= edges[mid + 1]) lo = mid + 1; else hi = mid }
  return lo
}

export function pipeShell(length, inner, outer, cutaway = false) {
  const positions = [], start = cutaway ? Math.PI / 2 : 0, end = 2 * Math.PI, count = 64
  const point = (x, r, a) => [x, r * Math.cos(a), r * Math.sin(a)]
  const quad = (a, b, c, d) => positions.push(...a, ...b, ...c, ...a, ...c, ...d)
  for (let k = 0; k < count; k++) {
    const a = start + (end-start)*k/count, b = start + (end-start)*(k+1)/count
    for (const r of [inner, outer]) quad(point(-length/2,r,a), point(length/2,r,a), point(length/2,r,b), point(-length/2,r,b))
    for (const x of [-length/2,length/2]) quad(point(x,inner,a), point(x,outer,a), point(x,outer,b), point(x,inner,b))
  }
  if (cutaway) for (const a of [start,end]) quad(point(-length/2,inner,a), point(length/2,inner,a), point(length/2,outer,a), point(-length/2,outer,a))
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3)); geometry.computeVertexNormals()
  return geometry
}

export function resultSurface(data, key, mode, station, scale, radialScale, range, wire = false) {
  const values = data.fields[key].values, positions = [], colors = [], cellIds = [], lines = []
  const length = data.x_edges_m.at(-1), color = new THREE.Color()
  const point = (x, r, theta) => [(x - length/2) * scale, r * radialScale * Math.cos(theta), r * radialScale * Math.sin(theta)]
  function quad(corners, cell, outlines = true) {
    const [r,g,b] = fieldColor(values[cell], range.min, range.max)
    color.setRGB(r/255, g/255, b/255, THREE.SRGBColorSpace)
    for (const i of [0,1,2,0,2,3]) { positions.push(...corners[i]); colors.push(color.r, color.g, color.b) }
    cellIds.push(cell,cell)
    if (wire && outlines) for (let i=0;i<4;i++) lines.push(...corners[i],...corners[(i+1)%4])
  }
  if (mode === 'axial' || mode === 'cutaway') {
    const angles = mode === 'axial' ? [0, Math.PI] : [0, Math.PI/2]
    for (let i=0;i<data.nx;i++) for (let j=0;j<data.nr;j++) for (const angle of angles) {
      const x0=data.x_edges_m[i],x1=data.x_edges_m[i+1],r0=data.r_edges_m[j],r1=data.r_edges_m[j+1]
      quad([point(x0,r0,angle),point(x1,r0,angle),point(x1,r1,angle),point(x0,r1,angle)],i*data.nr+j)
    }
  }
  if (mode === 'cross' || mode === 'cutaway') {
    const i = mode === 'cross' ? station : data.nx-1
    const x = mode === 'cross' ? data.cell_x_m[i*data.nr] : length
    const start = mode === 'cross' ? 0 : Math.PI/2, count=64
    for (let j=0;j<data.nr;j++) for (let k=0;k<count;k++) {
      const a=start+(2*Math.PI-start)*k/count,b=start+(2*Math.PI-start)*(k+1)/count
      const r0=data.r_edges_m[j],r1=data.r_edges_m[j+1]
      quad([point(x,r0,a),point(x,r1,a),point(x,r1,b),point(x,r0,b)],i*data.nr+j,false)
      if(wire) lines.push(...point(x,r1,a),...point(x,r1,b))
    }
  }
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3))
  geometry.setAttribute('color',new THREE.Float32BufferAttribute(colors,3))
  geometry.userData.cellIds=cellIds
  const mesh = new THREE.Mesh(geometry,new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide}))
  const edges = new THREE.LineSegments(new THREE.BufferGeometry().setAttribute('position',new THREE.Float32BufferAttribute(lines,3)),
    new THREE.LineBasicMaterial({color:0xa9b9c8,transparent:true,opacity:.32,depthTest:false}))
  return {mesh,edges}
}
