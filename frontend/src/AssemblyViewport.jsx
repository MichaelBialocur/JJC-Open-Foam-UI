import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { SVGRenderer } from 'three/addons/renderers/SVGRenderer.js'
import { fieldColor } from './fieldGeometry'
import { niceScale, tickLabel } from './axes'
import { attachCadControls, attachClickPicker, fitCamera } from './cadControls'

const empty = []
export default function AssemblyViewport({ data, selected=empty, groups=empty, onPick, field=false }) {
  const host=useRef(null), cameraState=useRef(null), pick=useRef(onPick), live=useRef(null), appearance=useRef(null)
  const [view,setView]=useState('isometric'), [reset,setReset]=useState(0), [display,setDisplay]=useState('all'), [wire,setWire]=useState(false)
  const [probe,setProbe]=useState(null), [fallback,setFallback]=useState(false)
  useEffect(()=>{ pick.current=onPick },[onPick])
  useEffect(()=>{
    appearance.current={selected,groups,display,wire}
    live.current?.updateAppearance()
  },[selected,groups,display,wire])
  useEffect(()=>{
    if (!data?.vertices_mm.length) return
    const container=host.current, scene=new THREE.Scene(), camera=new THREE.PerspectiveCamera(40,1,.001,2000)
    const vertices=data.vertices_mm, box=new THREE.Box3().setFromPoints((data.bounds_mm??vertices).map(p=>new THREE.Vector3(...p)))
    const center=box.getCenter(new THREE.Vector3()), extent=box.getSize(new THREE.Vector3()), scale=4/Math.max(extent.x,extent.y,extent.z,.001)
    const geometryKey=data.geometry_key??`${field}/${data.cell_count}/${extent.toArray()}`
    const key=`${geometryKey}/${view}/${reset}`, saved=cameraState.current
    camera.up.set(0,0,1); camera.position.set(4,-4,5)
    let renderer, isSvg=false
    try {
      const canvas=document.createElement('canvas'), context=canvas.getContext('webgl2',{antialias:true})
      if (!context) throw new Error('No WebGL')
      renderer=new THREE.WebGLRenderer({canvas,context,antialias:true});renderer.setPixelRatio(Math.min(window.devicePixelRatio||1,2))
    } catch { renderer=new SVGRenderer(); isSvg=true }
    queueMicrotask(()=>{setFallback(isSvg);setProbe(null)})
    renderer.setClearColor(0x0b1622,1); renderer.domElement.setAttribute('role','img')
    renderer.domElement.setAttribute('aria-label',field?'Computed 3D finite-volume field':'3D geometry. Click a face to select it.')
    renderer.domElement.style.touchAction='none'; container.appendChild(renderer.domElement)
    function render(){ renderer.render(scene,camera) }
    const navigation=attachCadControls(camera,renderer.domElement,render), controls=navigation.controls
    // SVGRenderer ignores ambient intensity and does not tone-map HDR colours.
    const ambient=new THREE.AmbientLight(0xffffff,.9)
    if(isSvg)ambient.color.multiplyScalar(.45)
    scene.add(ambient)
    const light=new THREE.DirectionalLight(0xffffff,isSvg?.5:1.5); camera.add(light); scene.add(camera)
    const meshes=[], range=field?niceScale(data.range[0],data.range[1],{includeZero:data.unit!=='°C'}):null
    for (const face of data.faces) {
      const positions=[], colours=[], indices=[], local=new Map()
      for (const [i,tri] of face.triangles.entries()) {
        const colour=field?fieldColor(face.values[i],range.min,range.max).map(v=>v/255):null
        for (const index of tri) {
          if (!field && local.has(index)) { indices.push(local.get(index)); continue }
          const point=new THREE.Vector3(...vertices[index]).sub(center).multiplyScalar(scale)
          if (!field) { local.set(index,positions.length/3); indices.push(positions.length/3) }
          positions.push(...point.toArray()); if (colour) colours.push(...colour)
        }
      }
      if (!positions.length) continue
      const geometry=new THREE.BufferGeometry(); geometry.setAttribute('position',new THREE.Float32BufferAttribute(positions,3))
      if (!field) geometry.setIndex(indices)
      geometry.computeVertexNormals()
      if (field) geometry.setAttribute('color',new THREE.Float32BufferAttribute(colours,3))
      const material=field?new THREE.MeshBasicMaterial({vertexColors:true,side:THREE.DoubleSide}):new THREE.MeshPhongMaterial({color:0x8298ad,side:THREE.DoubleSide,shininess:45})
      const mesh=new THREE.Mesh(geometry,material); mesh.userData=face; scene.add(mesh); meshes.push(mesh)
    }
    const axis=new THREE.AxesHelper(.45); axis.position.set(-2.2,-.8,-.5); scene.add(axis)
    function updateAppearance(){
      const {selected=[],groups=[],display='all',wire=false}=appearance.current??{}
      const assigned=Object.fromEntries(groups.flatMap(g=>g.faces.map(id=>[id,g.kind])))
      for (const mesh of meshes) {
        const face=mesh.userData, fluid=face.region==='fluid'||face.region==='interface'
        mesh.visible=field||(display==='all'?face.region!=='interface':display==='fluid'?fluid:!fluid)
        mesh.material.wireframe=wire
        if (!field) mesh.material.color.setHex(selected.includes(face.id)?0xb899ff:
          ({heat:0xf29c58,convection:0x55cde3,inlet:0x43a9ff,outlet:0x63d5a0})[assigned[face.id]]??(fluid?0x59b9fa:0x8298ad))
      }
      render()
    }
    live.current={updateAppearance}
    let first=true
    const restore=saved?.key===key
    if (restore) { camera.position.fromArray(saved.position); camera.up.fromArray(saved.up); controls.target.fromArray(saved.target) }
    function resize(){
      const w=container.clientWidth||850,h=container.clientHeight||450
      renderer.setSize(w,h);camera.aspect=w/h;camera.updateProjectionMatrix();navigation.resize()
      if (first&&!restore) {
        const corners=[]
        for(const x of [box.min.x,box.max.x])for(const y of [box.min.y,box.max.y])for(const z of [box.min.z,box.max.z])corners.push(new THREE.Vector3(x,y,z).sub(center).multiplyScalar(scale))
        fitCamera(camera,controls.target,corners,new THREE.Vector3(...(view==='top'?[0,0,1]:view==='end'?[1,0,0]:[1,-1,1])),new THREE.Vector3(...(view==='top'?[0,1,0]:[0,0,1])))
      }
      first=false;controls.update();render()
    }
    const observer=new ResizeObserver(resize);observer.observe(container);resize();updateAppearance()
    const ray=new THREE.Raycaster()
    const unpick=attachClickPicker(renderer.domElement,e=>{
      const rect=renderer.domElement.getBoundingClientRect()
      ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera)
      const hit=ray.intersectObjects(meshes.filter(m=>m.visible))[0]
      if (!hit) return
      const face=hit.object.userData
      if (field) setProbe({cell:face.cell_ids[hit.faceIndex],value:face.values[hit.faceIndex]})
      else if (face.selectable) pick.current?.(face.id)
    })
    return()=>{
      cameraState.current={key,position:camera.position.toArray(),up:camera.up.toArray(),target:controls.target.toArray()}
      live.current=null;observer.disconnect();navigation.dispose();unpick()
      scene.traverse(o=>{o.geometry?.dispose();o.material?.dispose?.()});renderer.dispose?.();renderer.domElement.remove()
    }
  },[data,field,view,reset])
  const colourScale=field&&data?niceScale(data.range[0],data.range[1],{includeZero:data.unit!=='°C'}):null
  return <div className="assembly-view">
    <div className="viewport assembly-viewport" ref={host}/>
    {field&&data&&!data.vertices_mm.length&&<p className="notice">This plane does not intersect any cells. Move the slice or change its direction.</p>}
    <div className="view-tools"><span>Left-drag: free orbit · middle/right-drag: pan · wheel/pinch: zoom · click: {field?'probe':'select'}</span><div className="view-buttons">
      {['isometric','top','end'].map(v=><button className="secondary" key={v} onClick={()=>{setView(v);setReset(x=>x+1)}}>{v==='isometric'?'Isometric':v==='top'?'Along Z':'Along X'}</button>)}
      <button className="secondary" onClick={()=>setReset(x=>x+1)}>Fit / reset view</button></div></div>
    <div className="view-tools">{!field&&<label>Visible bodies<select aria-label="Visible bodies" value={display} onChange={e=>setDisplay(e.target.value)}><option value="all">All exterior faces</option><option value="solid">Solid bodies</option><option value="fluid">Fluid passages</option></select></label>}
      <label className="check-label"><input type="checkbox" checked={wire} onChange={e=>setWire(e.target.checked)}/>Surface triangles</label>
      {fallback&&<span>WebGL unavailable · reduced-performance SVG view</span>}</div>
    {!field&&<p className="muted">True proportions · mm · purple: selected · blue: inlet · green: outlet · orange: heating · cyan: convection</p>}
    {colourScale&&<div className="colour-scale"><b>{data.label} · {data.unit}</b><div className="colour-gradient"/><div className="colour-ticks">{colourScale.ticks.map(t=><span key={t}>{tickLabel(t)}</span>)}</div></div>}
    {field&&probe&&<p className="probe">Cell {probe.cell}: {probe.value.toPrecision(6)} {data.unit}</p>}
  </div>
}
