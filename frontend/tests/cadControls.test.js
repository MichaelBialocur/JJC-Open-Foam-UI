import test from 'node:test'
import assert from 'node:assert/strict'
import {PerspectiveCamera,Vector3} from 'three'
import {attachCadControls,attachClickPicker,fitCamera} from '../src/cadControls.js'

class Surface extends EventTarget {
  constructor(){super();this.style={};this.ownerDocument=new EventTarget();this.ownerDocument.documentElement={clientLeft:0,clientTop:0}}
  getBoundingClientRect(){return {left:0,top:0,width:800,height:500}}
  setPointerCapture(){}
  releasePointerCapture(){}
}
function pointer(element,type,x,y,button=0,id=1){
  const e=new Event(type,{cancelable:true})
  Object.assign(e,{clientX:x,clientY:y,pageX:x,pageY:y,button,pointerId:id,pointerType:'mouse'})
  element.dispatchEvent(e)
}

test('fit shows every corner in both wide and narrow panes',()=>{
  const corners=[]
  for(const x of [-2,2])for(const y of [-.3,.3])for(const z of [-.4,.4])corners.push(new Vector3(x,y,z))
  for(const aspect of [.5,2])for(const direction of [new Vector3(1,-1,1),new Vector3(1,0,0)]){
    const camera=new PerspectiveCamera(40,aspect,.001,1000)
    fitCamera(camera,new Vector3(),corners,direction,new Vector3(0,0,1));camera.updateMatrixWorld()
    for(const corner of corners){const p=corner.clone().project(camera);assert.ok(Math.abs(p.x)<1&&Math.abs(p.y)<1&&p.z>-1&&p.z<1)}
  }
})

test('only a primary click selects; drag-return, pan, cancel and multitouch do not',()=>{
  const element=new Surface();let picks=0
  const dispose=attachClickPicker(element,()=>picks++)
  pointer(element,'pointerdown',20,20);pointer(element,'pointerup',21,20);assert.equal(picks,1)
  pointer(element,'pointerdown',20,20);pointer(element,'pointermove',70,20);pointer(element,'pointerup',20,20)
  for(const button of [1,2]){pointer(element,'pointerdown',20,20,button);pointer(element,'pointerup',20,20,button)}
  pointer(element,'pointerdown',20,20);pointer(element,'pointercancel',20,20);pointer(element,'pointerup',20,20)
  pointer(element,'pointerdown',20,20,0,1);pointer(element,'pointerdown',40,20,0,2);pointer(element,'pointerup',40,20,0,2);pointer(element,'pointerup',20,20,0,1)
  assert.equal(picks,1);dispose();pointer(element,'pointerdown',20,20);pointer(element,'pointerup',20,20);assert.equal(picks,1)
})

test('trackball follows drag, crosses poles, damps motion and renders a roll',()=>{
  const previous={window:globalThis.window,requestAnimationFrame:globalThis.requestAnimationFrame,cancelAnimationFrame:globalThis.cancelAnimationFrame}
  const frames=new Map();let counter=0,renders=0
  globalThis.window=new EventTarget();window.pageXOffset=0;window.pageYOffset=0
  globalThis.requestAnimationFrame=fn=>{frames.set(++counter,fn);return counter}
  globalThis.cancelAnimationFrame=id=>frames.delete(id)
  const frame=()=>{const batch=[...frames.values()];frames.clear();batch.forEach(f=>f())}
  const camera=new PerspectiveCamera(40,1,.001,2000);camera.position.set(0,0,7)
  const element=new Surface(),navigation=attachCadControls(camera,element,()=>renders++)
  try{
    frame()
    pointer(element,'pointerdown',400,250);pointer(element.ownerDocument,'pointermove',470,250);frame()
    assert.ok(camera.position.x<0,'drag right turns the front of the model to the right')
    pointer(element.ownerDocument,'pointerup',470,250)
    const released=camera.position.clone();for(let i=0;i<10;i++)frame()
    assert.ok(camera.position.distanceTo(released)>0,'motion decays after release')
    for(let i=0;i<100;i++)frame()
    const settled=camera.position.clone();for(let i=0;i<30;i++)frame()
    assert.ok(camera.position.distanceTo(settled)<.001,'inertia settles')
    // Repeated vertical drags cross the original world-up pole without a clamp.
    let inverted=false
    for(let i=0;i<12;i++){
      pointer(element,'pointerdown',400,250);pointer(element.ownerDocument,'pointermove',400,350);frame();pointer(element.ownerDocument,'pointerup',400,350)
      if(camera.up.y<0)inverted=true
    }
    assert.ok(inverted,'free trackball can rotate upside down')
    for(let i=0;i<100;i++)frame()
    const oldRenders=renders;camera.up.applyAxisAngle(camera.position.clone().sub(navigation.controls.target).normalize(),.2);frame()
    assert.ok(renders>oldRenders,'pure roll is rendered even if position is unchanged')
  }finally{navigation.dispose();assert.equal(frames.size,0);Object.assign(globalThis,previous)}
})
