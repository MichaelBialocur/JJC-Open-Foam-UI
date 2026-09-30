import test from 'node:test'
import assert from 'node:assert/strict'
import { niceScale, logScale, tickLabel } from '../src/axes.js'

test('positive pressure and velocity keep a visible zero baseline',()=>{
  assert.deepEqual(niceScale(0,745,{includeZero:true}).ticks,[0,200,400,600,800])
  assert.deepEqual(niceScale(.01,1.15,{includeZero:true}).ticks,[0,.5,1,1.5])
  assert.equal(niceScale(0,0,{includeZero:true}).min,0)
  assert.deepEqual(niceScale(0,100).ticks,[0,20,40,60,80,100])
  assert.equal(tickLabel(-0),'0')
})
test('signed physical data are retained and zero is labelled',()=>{
  const scale=niceScale(-3,19,{includeZero:true})
  assert.ok(scale.min<=-3 && scale.max>=19 && scale.ticks.includes(0))
  assert.deepEqual(scale.ticks,[-5,0,5,10,15,20])
})
test('temperature can retain detail and logarithmic ticks are integer powers',()=>{
  assert.deepEqual(niceScale(20.1,24.8).ticks,[20,21,22,23,24,25])
  const scale=logScale(3e-11,.95)
  assert.ok(scale.min<=Math.log10(3e-11) && scale.max>=Math.log10(.95))
  assert.ok(scale.ticks.every(v=>Math.abs(Math.log10(v)-Math.round(Math.log10(v)))<1e-12))
})
