import test from 'node:test'
import assert from 'node:assert/strict'
import { combinedTemperature, resultSurface, locateCell } from '../src/fieldGeometry.js'

test('combined temperature view preserves actual fluid and annular solid cell values',()=>{
  const data={nx:2,nr:2,x_edges_m:[0,1,2],r_edges_m:[0,1,2],cell_x_m:[.5,.5,1.5,1.5],cell_r_m:[.5,1.5,.5,1.5],
    fields:{temperature:{values:[1,2,3,4],min:1,max:4}},
    solid:{nx:2,nr:1,x_edges_m:[0,1,2],r_edges_m:[2,3],cell_x_m:[.5,1.5],cell_r_m:[2.5,2.5],
      fields:{temperature:{values:[5,6],min:5,max:6}}}}
  const merged=combinedTemperature(data)
  assert.deepEqual(merged.fields.temperature.values,[1,2,5,3,4,6])
  assert.deepEqual(merged.r_edges_m,[0,1,2,3])
  assert.equal(merged.interface_radius_m,2)
  assert.equal(locateCell(data.solid.r_edges_m,1.9),null,'No solid cell inside the fluid')
  const surface=resultSurface(data.solid,'temperature','cross',1,1,1,{min:1,max:6})
  assert.ok(surface.mesh.geometry.userData.cellIds.every(id=>id===1))
  surface.mesh.geometry.dispose();surface.mesh.material.dispose();surface.edges.geometry.dispose();surface.edges.material.dispose()
  assert.throws(()=>combinedTemperature({...data,solid:{...data.solid,r_edges_m:[2.1,3]}}),/interface/)
})
