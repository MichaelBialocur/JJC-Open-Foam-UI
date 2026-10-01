import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { SVGRenderer } from 'three/addons/renderers/SVGRenderer.js'
import { fieldColor } from './fieldGeometry'
import { niceScale, tickLabel } from './axes'

const empty=[]

export default function AssemblyViewport({data,selected=empty,groups=empty,onPick,field=false}){
  const host=useRef(null),cameraState=useRef(null),pick=useRef(onPick)
  const [view,setView]=useState('isometric'),[reset,setReset]=useState(0),[passages,setPassages]=useState(false),[wire,setWire]=useState(false)
  const [probe,setProbe]=useState(null),[fallback,setFallback]=useState(false)
  useEffect(()=>{pick.current=onPick},[onPick])
  useEffect(()=>{
    if(!data?.vertices_mm.length)return
    const container=host.current,scene=new THREE.Scene(),camera=new THREE.PerspectiveCamera(40,1,.001,100)
    const vertices=data.vertices_mm,box=new THREE.Box3().setFromPoints((data.bounds_mm??vertices).map(p=>new THREE.Vector3(...p)))
    const center=box.getCenter(new THREE.Vector3()),extent=box.getSize(new THREE.Vector3()),scale=4/Math.max(extent.x,extent.y,extent.z,.001)
    const geometryKey=data.geometry_key??`${field}/${data.cell_count}/${extent.toArray()}`
    let renderer,isSvg=false
    try{
      const canvas=document.createElement('canvas'),context=canvas.getContext('webgl2',{antialias:true})
      if(!context)throw new Error('No WebGL')
      renderer=new THREE.WebGLRenderer({canvas,context,antialias:true});renderer.setPixelRatio(Math.min(devicePixelRatio||1,2))
    }catch{renderer=new SVGRenderer();isSvg=true}
    queueMicrotask(()=>setFallback(isSvg))
    renderer.setClearColor(0x0b1622,1);renderer.domElement.setAttribute('role','img')
    renderer.domElement.setAttribute('aria-label',field?'Computed 3D finite-volume field':'3D assembly. Click an exterior face to select it.')
    renderer.domElement.style.touchAction='none';container.appendChild(renderer.domElement)
    const controls=new OrbitControls(camera,renderer.domElement);controls.minDistance=.1;controls.maxDistance=50
    scene.add(new THREE.AmbientLight(0xffffff,.8));const light=new THREE.DirectionalLight(0xffffff,1.3);light.position.set(2,4,6);scene.add(light)
    const assigned=Object.fromEntries(groups.flatMap(g=>g.faces.map(id=>[id,g.kind]))),meshes=[]
    const range=field?niceScale(data.range[0],data.range[1],{includeZero:data.unit!=='°C'}):null
    for(const face of data.faces){
      if(!field&&(passages?face.region!=='fluid':face.region!=='solid'))continue
      const positions=[],colours=[]
      for(const [i,tri] of face.triangles.entries()){
        const colour=field?fieldColor(face.values[i],range.min,range.max).map(v=>v/255):null
        for(const index of tri){const point=new THREE.Vector3(...vertices[index]).sub(center).multiplyScalar(scale);positions.push(...point.toArray());if(colour)colours.push(...colour)}
      }
      if(!positions.length)continue
      const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));geometry.computeVertexNormals()
      if(field)geometry.setAttribute('color',new THREE.Float32BufferAttribute(colours,3))
      const colour=selected.includes(face.id)?0xb899ff:assigned[face.id]==='heat'?0xf29c58:assigned[face.id]==='convection'?0x55cde3:face.region==='fluid'?0x59b9fa:0x8298ad
      const material=field?new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide,wireframe:wire}):new THREE.MeshPhongMaterial({color:colour,side:THREE.DoubleSide,shininess:45,wireframe:wire})
      const mesh=new THREE.Mesh(geometry,material);mesh.userData=face;scene.add(mesh);meshes.push(mesh)
    }
    const axis=new THREE.AxesHelper(.45);axis.position.set(-2.2,-.8,-.5);scene.add(axis)
    const key=`${geometryKey}/${view}/${reset}`,saved=cameraState.current
    if(saved?.key===key){camera.position.fromArray(saved.position);controls.target.fromArray(saved.target)}
    else camera.position.set(...(view==='top'?[0,0,7]:view==='end'?[7,0,0]:[4,-4,5]))
    camera.up.set(0,0,1)
    if(view==='top')camera.up.set(0,1,0)
    function render(){renderer.render(scene,camera)}
    function resize(){const w=container.clientWidth||850,h=container.clientHeight||450;renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();controls.update();render()}
    const observer=new ResizeObserver(resize);observer.observe(container);controls.addEventListener('change',render);resize()
    const down={x:0,y:0},ray=new THREE.Raycaster()
    function pointerDown(e){down.x=e.clientX;down.y=e.clientY}
    function pointerUp(e){
      if(Math.hypot(e.clientX-down.x,e.clientY-down.y)>4)return
      const rect=renderer.domElement.getBoundingClientRect();ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera)
      const hit=ray.intersectObjects(meshes)[0]
      if(!hit)return
      const face=hit.object.userData
      if(field)setProbe({cell:face.cell_ids[hit.faceIndex],value:face.values[hit.faceIndex]})
      else if(face.selectable)pick.current?.(face.id)
    }
    renderer.domElement.addEventListener('pointerdown',pointerDown);renderer.domElement.addEventListener('pointerup',pointerUp)
    return()=>{
      cameraState.current={key,position:camera.position.toArray(),target:controls.target.toArray()}
      observer.disconnect();controls.dispose();renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',pointerUp)
      scene.traverse(o=>{o.geometry?.dispose();o.material?.dispose?.()});renderer.dispose?.();container.replaceChildren()
    }
  },[data,field,selected,groups,view,reset,passages,wire])
  const scale=field&&data?niceScale(data.range[0],data.range[1],{includeZero:data.unit!=='°C'}):null
  return <div className="assembly-view">
    <div className="viewport assembly-viewport" ref={host}/>
    {field&&data&&!data.vertices_mm.length&&<p className="notice">This plane does not intersect any cells in the selected region. Move the slice or change its direction.</p>}
    <div className="view-tools"><span>Drag to orbit · wheel to zoom · click to {field?'probe a cell':'select a face'}</span><div className="view-buttons">
      {['isometric','top','end'].map(v=><button className="secondary" key={v} onClick={()=>{setView(v);setReset(x=>x+1)}}>{v==='isometric'?'Isometric':v==='top'?'Along Z':'Along X'}</button>)}
      <button className="secondary" onClick={()=>setReset(x=>x+1)}>Reset view</button></div></div>
    <div className="view-tools">{!field&&<label className="check-label"><input type="checkbox" checked={passages} onChange={e=>setPassages(e.target.checked)}/>Show fluid passages</label>}
      <label className="check-label"><input type="checkbox" checked={wire} onChange={e=>setWire(e.target.checked)}/>Surface triangles</label>
      {fallback&&<span>SVG rendering · face selection also available in the list</span>}</div>
    {!field&&<p className="muted">True proportions · dimensions in mm · purple: selected · orange: heating · cyan: convection · grey: insulated</p>}
    {scale&&<div className="colour-scale"><b>{data.label} · {data.unit}</b><div className="colour-gradient"/><div className="colour-ticks">{scale.ticks.map(t=><span key={t}>{tickLabel(t)}</span>)}</div></div>}
    {field&&probe&&<p className="probe">Cell {probe.cell}: {probe.value.toPrecision(6)} {data.unit}</p>}
  </div>
}
