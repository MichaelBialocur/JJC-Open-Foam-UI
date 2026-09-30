import test from 'node:test'
import assert from 'node:assert/strict'
import { fieldColor, locateCell, pipeShell, resultSurface } from '../src/fieldGeometry.js'

test('cell picking honours graded radial edges and exact endpoints',()=>{
  assert.equal(locateCell([0,.5,.9,1],.95),2)
  assert.equal(locateCell([0,.5,.9,1],1),2)
  assert.equal(locateCell([0,.5,.9,1],-.1),null)
  assert.equal(locateCell([0,.5,.9,1],.5),1)
  assert.notDeepEqual(fieldColor(0,0,1),fieldColor(1,0,1))
})
test('3D sections preserve cell indices instead of substituting analytical fields',()=>{
  const data={nx:2,nr:2,x_edges_m:[0,1,2],r_edges_m:[0,.4,1],cell_x_m:[.5,.5,1.5,1.5],fields:{pressure:{values:[1,7,20,35]}}}
  const cross=resultSurface(data,'pressure','cross',1,2,3,{min:0,max:40})
  assert.deepEqual([...new Set(cross.mesh.geometry.userData.cellIds)],[2,3])
  const axial=resultSurface(data,'pressure','axial',0,2,3,{min:0,max:40},true)
  assert.deepEqual([...new Set(axial.mesh.geometry.userData.cellIds)],[0,1,2,3])
  assert.ok(axial.edges.geometry.getAttribute('position').count>0)
  for(const surface of [cross,axial])for(const object of [surface.mesh,surface.edges]){object.geometry.dispose();object.material.dispose()}
})
test('pipe geometry has real wall thickness and the requested length',()=>{
  const geometry=pipeShell(4,.5,.7,true);geometry.computeBoundingBox()
  assert.equal(geometry.boundingBox.min.x,-2);assert.equal(geometry.boundingBox.max.x,2)
  assert.ok(Math.abs(geometry.boundingBox.max.y-.7)<1e-5)
  geometry.dispose()
})
