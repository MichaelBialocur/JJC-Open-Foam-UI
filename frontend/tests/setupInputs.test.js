import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { boundaryOf, inletVelocity, changeBoundary, chooseFluid, chooseMaterial, isEdited, inputsDiffer } from '../src/setupInputs.js'

const catalog=JSON.parse(readFileSync(new URL('../../backend/app/material-catalog.json',import.meta.url),'utf8'))
const base=chooseFluid({inner_diameter_mm:10,inlet_velocity_m_s:1},catalog,'water')
const close=(actual,expected)=>assert.ok(Math.abs(actual-expected)<=Math.abs(expected)*1e-10,`${actual} ≠ ${expected}`)

test('all unit/type switches preserve physical flow including legacy velocity inputs',()=>{
  assert.deepEqual(boundaryOf(base),{kind:'velocity',value:1,unit:'m/s'})
  let form=base
  for(const [kind,group] of Object.entries(catalog.inlet_units)){
    for(const unit of group.units){
      form=changeBoundary(form,catalog,kind,unit.id)
      close(inletVelocity(form,catalog),1)
    }
  }
  close(changeBoundary(form,catalog,'volumetric_flow','CFM').inlet.value, Math.PI*.005**2/.0004719474432)
})

test('mass flow stays fixed while density and geometry determine velocity',()=>{
  const mass=changeBoundary(base,catalog,'mass_flow','kg/h')
  const air=chooseFluid(mass,catalog,'air')
  assert.deepEqual(air.inlet,mass.inlet)
  close(inletVelocity(air,catalog),base.density_kg_m3/air.density_kg_m3)
  close(inletVelocity({...mass,inner_diameter_mm:20},catalog),.25)
  const volume=changeBoundary(base,catalog,'volumetric_flow')
  close(inletVelocity(chooseFluid(volume,catalog,'air'),catalog),1)
})

test('blank entry remains blank when choosing another unit',()=>{
  const blank={...base,inlet:{kind:'volumetric_flow',value:'',unit:'L/min'}}
  assert.equal(changeBoundary(blank,catalog,'mass_flow').inlet.value,'')
  assert.equal(inletVelocity(blank,catalog),null)
})

test('fluid and solid presets replace edited properties without changing the inlet',()=>{
  const form=chooseFluid({...base,density_kg_m3:123},catalog,'water_pg50')
  assert.equal(isEdited(form,catalog.fluids.water_pg50),false)
  assert.equal(isEdited({...form,density_kg_m3:123},catalog.fluids.water_pg50),true)
  const custom=chooseFluid(form,catalog,'custom')
  assert.equal(custom.density_kg_m3,form.density_kg_m3)
  const copper=chooseMaterial({...form,solid_conductivity_w_m_k:15},catalog,'copper')
  assert.equal(copper.solid_conductivity_w_m_k,391.1)
  assert.equal(copper.solid_density_kg_m3,8910)
  assert.equal(copper.inlet,form.inlet)
})

test('a derived backend velocity does not falsely mark the current run as changed',()=>{
  const form={...base,inlet:{kind:'mass_flow',value:6,unit:'kg/h'}}
  const saved={...form,inlet_velocity_m_s:inletVelocity(form,catalog)}
  assert.equal(inputsDiffer(form,saved),false)
  assert.equal(inputsDiffer({...form,inner_diameter_mm:20},saved),true)
  assert.equal(inputsDiffer({...form,inlet:{...form.inlet,value:7}},saved),true)
  assert.equal(inputsDiffer(base,{...base,inlet_velocity_m_s:2}),true)
})
