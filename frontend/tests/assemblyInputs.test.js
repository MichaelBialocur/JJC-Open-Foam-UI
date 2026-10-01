import test from 'node:test'
import assert from 'node:assert/strict'
import {appendPart,editPart,inletGeometry,movePart,newPart,thermalTotals} from '../src/assemblyInputs.js'
import {changeBoundary} from '../src/setupInputs.js'
import {readFileSync} from 'node:fs'
const catalog=JSON.parse(readFileSync(new URL('../../backend/app/material-catalog.json',import.meta.url)))
test('adding a cold plate after piping inserts a matching manifold',()=>{
  const parts=appendPart([newPart('straight')],'multiport')
  assert.deepEqual(parts.map(p=>p.kind),['straight','manifold','multiport'])
  assert.deepEqual(parts[1].start,parts[0].end);assert.deepEqual(parts[1].end,parts[2].start)
  const downstream=appendPart(parts,'manifold');assert.equal(downstream.at(-1).end.shape,'round')
})
test('end edits keep shared sections joined without mutating the old draft',()=>{
  const parts=appendPart([newPart('straight')],'bend'),end={...parts[0].end,diameter_mm:8}
  const next=editPart(parts,0,'end',end)
  assert.equal(parts[1].start.diameter_mm,10);assert.deepEqual(next[1].start,end)
  assert.deepEqual(movePart(next,1,-1)[1].start,next[1].end)
})
test('rectangular inlet units use open channel area excluding webs',()=>{
  const part=appendPart([],'multiport').at(-1),geometry={parts:[part]},area=inletGeometry(geometry)
  assert.equal(area.inlet_area_m2,.000096)
  const form={...area,density_kg_m3:1000,inlet:{kind:'velocity',value:.1,unit:'m/s'}}
  const volume=changeBoundary(form,catalog,'volumetric_flow','L/min');assert.ok(Math.abs(volume.inlet.value-.576)<1e-12)
  const mass=changeBoundary(volume,catalog,'mass_flow','kg/h');assert.ok(Math.abs(mass.inlet.value-34.56)<1e-10)
})
test('a multi-face group adds its total power once',()=>{
  assert.deepEqual(thermalTotals([{kind:'heat',power_w:10,faces:['top','bottom']},{kind:'convection',faces:['left','right']}]),{heat_w:10,faces:4})
})
