import { useEffect, useRef, useState } from 'react'
import * as THREE from 'three'
import { OrbitControls } from 'three/addons/controls/OrbitControls.js'
import { SVGRenderer } from 'three/addons/renderers/SVGRenderer.js'
import { pipeShell, resultSurface } from './fieldGeometry'

export default function Viewport({ spec, data, field, mode = 'cutaway', station = 0, range, wire = false, onPick }) {
  const host = useRef(null), note = useRef(null), savedCamera = useRef(null)
  const [expanded, setExpanded] = useState(true), [reset, setReset] = useState(0)
  const [angle, setAngle] = useState('isometric')
  const length = Number(spec.length_mm) / 1000, radius = Number(spec.inner_diameter_mm) / 2000
  const wall = Number(spec.wall_thickness_mm) / 1000
  const factor = expanded ? Math.max(1, Math.min(100, length / (radius * 16))) : 1
  useEffect(() => {
    if (!(length > 0 && radius > 0 && wall > 0)) return
    const container = host.current, scene = new THREE.Scene()
    const camera = new THREE.PerspectiveCamera(38, 1, .001, 1000)
    let renderer, svg = false
    try {
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('webgl2', { antialias:true })
      if (!context) throw new Error('WebGL unavailable')
      renderer = new THREE.WebGLRenderer({ canvas, context, antialias:true })
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
    } catch {
      renderer = new SVGRenderer(); svg = true
    }
    renderer.setClearColor(0x0b1622, 1)
    renderer.domElement.setAttribute('aria-label', data ? `${data.fields[field].label}: interactive ${svg ? 'cross-section' : mode} view` : 'Interactive 3D pipe with inlet, outlet and wall')
    renderer.domElement.setAttribute('role','img')
    renderer.domElement.style.touchAction='none'
    container.appendChild(renderer.domElement)
    note.current.textContent = svg && data ? 'Cross-section rendering is active in this browser. The complete axial field is shown below.' : ''
    const controls = new OrbitControls(camera, renderer.domElement)
    controls.enableDamping = false; controls.minDistance=.05; controls.maxDistance=200
    const scale=4/length, radialScale=scale*factor, r=radius*radialScale, outer=(radius+wall)*radialScale
    const geometryKey=`${length}/${radius}/${wall}/${factor}`
    const restore=savedCamera.current?.reset===reset && savedCamera.current?.geometryKey===geometryKey
    controls.target.set(0,0,0)
    if(restore) { camera.position.fromArray(savedCamera.current.position); controls.target.fromArray(savedCamera.current.target) }
    const shell = new THREE.Mesh(pipeShell(4,r,outer,!data),new THREE.MeshPhongMaterial({color:0x748da8,side:THREE.DoubleSide,
      transparent:!!data,opacity: data ? .08 : 1,depthWrite:!data,shininess:70}))
    scene.add(shell)
    scene.add(new THREE.AmbientLight(0xffffff,.65))
    const light=new THREE.DirectionalLight(0xffffff,1);light.position.set(-2,4,5);scene.add(light)
    // End rings remain legible in a long pipe and identify the flow direction.
    for(const [x,c] of [[-2,0x59b9fa],[2,0x62d5aa]]) {
      const points=Array.from({length:65},(_,i)=>new THREE.Vector3(x,r*Math.cos(i*Math.PI/32),r*Math.sin(i*Math.PI/32)))
      scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(points),new THREE.LineBasicMaterial({color:c})))
    }
    const arrow=new THREE.ArrowHelper(new THREE.Vector3(1,0,0),new THREE.Vector3(-2.7,0,0),.55,0x59b9fa,.14,.08);scene.add(arrow)
    let pickMesh
    if(data) {
      const surfaces=resultSurface(data,field,svg?'cross':mode,station,scale,radialScale,range,wire)
      scene.add(surfaces.mesh,surfaces.edges);pickMesh=surfaces.mesh
    }
    function render() { renderer.render(scene,camera) }
    let firstResize=true
    function resize() {
      const width=container.clientWidth || 720,height=container.clientHeight || 330
      renderer.setSize(width,height);camera.aspect=width/height;camera.updateProjectionMatrix()
      if(firstResize&&!restore){
        const direction=new THREE.Vector3(...(angle==='end'?[1,0,0]:[.35,.24,1])).normalize()
        const right=new THREE.Vector3().crossVectors(new THREE.Vector3(0,1,0),direction).normalize()
        const up=new THREE.Vector3().crossVectors(direction,right).normalize(),tan=Math.tan(camera.fov*Math.PI/360)
        let distance=0
        for(const x of [-2.8,2.1])for(const y of [-outer,outer])for(const z of [-outer,outer]){
          const corner=new THREE.Vector3(x,y,z),depth=corner.dot(direction)
          distance=Math.max(distance,depth+Math.abs(corner.dot(right))/(tan*camera.aspect)*1.18,depth+Math.abs(corner.dot(up))/tan*1.18)
        }
        camera.position.copy(direction.multiplyScalar(distance));controls.update()
      }
      firstResize=false;render()
    }
    const observer=new ResizeObserver(resize);observer.observe(container)
    controls.addEventListener('change',render);controls.update();resize()
    const down={x:0,y:0}, ray=new THREE.Raycaster()
    function pointerDown(e){down.x=e.clientX;down.y=e.clientY}
    function pointerUp(e){
      if(!pickMesh || Math.hypot(e.clientX-down.x,e.clientY-down.y)>4) return
      const rect=renderer.domElement.getBoundingClientRect()
      ray.setFromCamera(new THREE.Vector2((e.clientX-rect.left)/rect.width*2-1,1-(e.clientY-rect.top)/rect.height*2),camera)
      const hit=ray.intersectObject(pickMesh)[0]
      if(hit) onPick?.(pickMesh.geometry.userData.cellIds[hit.faceIndex])
    }
    renderer.domElement.addEventListener('pointerdown',pointerDown)
    renderer.domElement.addEventListener('pointerup',pointerUp)
    return () => {
      savedCamera.current={position:camera.position.toArray(),target:controls.target.toArray(),reset,geometryKey}
      observer.disconnect();controls.dispose()
      renderer.domElement.removeEventListener('pointerdown',pointerDown);renderer.domElement.removeEventListener('pointerup',pointerUp)
      scene.traverse(object=>{object.geometry?.dispose();if(Array.isArray(object.material))object.material.forEach(m=>m.dispose());else object.material?.dispose()})
      renderer.dispose?.();renderer.domElement.remove()
    }
  },[length,radius,wall,factor,data,field,mode,station,range,wire,onPick,reset,angle])
  return <div className="viewport-wrap">
    <div ref={host} className="viewport" />
    <div className="view-caption"><span><b className="inlet">● Inlet</b> → <b className="outlet">● Outlet</b></span><span>Drag to orbit · scroll to zoom · right-drag to pan</span></div>
    <div className="view-tools"><label className="check-label"><input type="checkbox" checked={expanded} onChange={e=>setExpanded(e.target.checked)}/> Enlarge diameter for viewing</label>
      <span className="muted">{factor===1?'True dimensional proportions':`Diameter shown ×${Number(factor.toPrecision(3))}; length unchanged`}</span>
      <button className="secondary" onClick={()=>{setAngle('end');setReset(r=>r+1)}}>End view</button>
      <button className="secondary" onClick={()=>{setAngle('isometric');setReset(r=>r+1)}}>Reset view</button></div>
    <p className="muted viewport-note" ref={note}/>
  </div>
}
