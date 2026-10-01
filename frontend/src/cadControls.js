import * as THREE from 'three'
import { TrackballControls } from 'three/addons/controls/TrackballControls.js'

// Free rotation through both poles; animate damping, render only on change.
export function attachCadControls(camera, element, render) {
  const controls = new TrackballControls(camera, element)
  controls.rotateSpeed = 1.5
  controls.zoomSpeed = 1.1
  controls.panSpeed = .65
  controls.staticMoving = false
  controls.dynamicDampingFactor = .25
  controls.minDistance = .015
  controls.maxDistance = 500
  controls.mouseButtons = { LEFT: THREE.MOUSE.ROTATE, MIDDLE: THREE.MOUSE.PAN, RIGHT: THREE.MOUSE.PAN }
  const resize = () => controls.handleResize()
  element.addEventListener('pointerdown', resize, true)
  window.addEventListener('scroll', resize, true)
  let dirty = true
  const changed = () => { dirty = true }
  controls.addEventListener('change', changed)
  const quaternion = camera.quaternion.clone()
  let frame
  const animate = () => {
    controls.update()
    // TrackballControls emits change for position, but a pure roll can rotate
    // the camera without moving it. Include orientation in the render check.
    if (dirty || quaternion.angleTo(camera.quaternion) > 1e-7) {
      render(); quaternion.copy(camera.quaternion); dirty = false
    }
    frame = requestAnimationFrame(animate)
  }
  frame = requestAnimationFrame(animate)
  return { controls, resize, dispose() {
    cancelAnimationFrame(frame)
    element.removeEventListener('pointerdown', resize, true)
    window.removeEventListener('scroll', resize, true)
    controls.removeEventListener('change', changed)
    controls.dispose()
  } }
}

export function fitCamera(camera, target, corners, direction, up) {
  camera.up.copy(up)
  const forward = direction.clone().normalize()
  const right = new THREE.Vector3().crossVectors(up, forward).normalize()
  const vertical = new THREE.Vector3().crossVectors(forward, right).normalize()
  const tangent = Math.tan(camera.fov * Math.PI / 360)
  let distance = .1
  for (const point of corners) {
    const relative = point.clone().sub(target), depth = relative.dot(forward)
    distance = Math.max(distance, depth + Math.abs(relative.dot(right)) / (tangent * camera.aspect) * 1.15,
      depth + Math.abs(relative.dot(vertical)) / tangent * 1.15)
  }
  camera.position.copy(target).addScaledVector(forward, distance)
  camera.lookAt(target)
  camera.updateProjectionMatrix()
}

// Navigation is never a face selection, even when a drag returns to its origin.
export function attachClickPicker(element, pick) {
  let gesture = null
  const pointers = new Set()
  const down = e => {
    pointers.add(e.pointerId)
    if (pointers.size > 1) { if (gesture) gesture.moved = true; return }
    if (e.button === 0) gesture = { id: e.pointerId, x: e.clientX, y: e.clientY, moved: false }
  }
  const move = e => { if (gesture && Math.hypot(e.clientX-gesture.x, e.clientY-gesture.y) > 4) gesture.moved = true }
  const up = e => {
    pointers.delete(e.pointerId)
    if (gesture?.id !== e.pointerId) return
    const shouldPick = !gesture.moved && Math.hypot(e.clientX-gesture.x, e.clientY-gesture.y) <= 4
    gesture = null
    if (shouldPick) pick(e)
  }
  const cancel = e => { pointers.delete(e.pointerId); gesture = null }
  const handlers = { pointerdown: down, pointermove: move, pointerup: up, pointercancel: cancel }
  for (const [name, fn] of Object.entries(handlers)) element.addEventListener(name, fn)
  const root = element.ownerDocument
  // Track movement beyond the viewport as well as pointer-captured movement.
  if (root && root !== element) { root.addEventListener('pointermove', move); root.addEventListener('pointerup', up); root.addEventListener('pointercancel', cancel) }
  return () => {
    for (const [name, fn] of Object.entries(handlers)) element.removeEventListener(name, fn)
    if (root && root !== element) { root.removeEventListener('pointermove', move); root.removeEventListener('pointerup', up); root.removeEventListener('pointercancel', cancel) }
  }
}
