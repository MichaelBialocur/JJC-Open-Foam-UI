export const sectionDefaults={shape:'round',diameter_mm:10,width_mm:30,height_mm:6,wall_mm:1}
export const physicsDefaults={fluid:'water',inlet:{kind:'velocity',value:.05,unit:'m/s'},inlet_velocity_m_s:.05,
  inlet_temperature_c:20,material:'aluminium',solid_conductivity_w_m_k:null,solid_density_kg_m3:null,solid_specific_heat_j_kg_k:null,
  density_kg_m3:998,dynamic_viscosity_pa_s:.001002,specific_heat_j_kg_k:4182,thermal_conductivity_w_m_k:.6,
  flow_model:'auto',max_iterations:2500,thermal_iterations:2000,residual_tolerance:1e-6,turbulence_intensity:.05,turbulent_prandtl:.85}
export const newId=prefix=>prefix+crypto.randomUUID().replaceAll('-','').slice(0,12)
export function newPart(kind,section={...sectionDefaults}){
  return {id:newId('p'),name:({straight:'Straight tube',bend:'Bend',manifold:'Manifold',multiport:'Multi-port tube'})[kind],kind,
    length_mm:40,radius_mm:Math.max(20,section.shape==='round'?section.diameter_mm+2*section.wall_mm:section.width_mm),angle_deg:90,roll_deg:0,
    start:{...section},end:{...section},channels:5,web_mm:1}
}
export function appendPart(parts,kind){
  const added=[...parts],previous=parts.at(-1)?.end??{...sectionDefaults}
  if(kind==='multiport'&&previous.shape==='round'){
    const header=newPart('manifold',previous);header.end={...sectionDefaults,shape:'rectangle'};header.name='Inlet manifold';header.length_mm=20
    added.push(header,newPart(kind,header.end))
  }else{
    const next=newPart(kind,previous)
    if(kind==='manifold')next.end={...sectionDefaults,shape:previous.shape==='round'?'rectangle':'round'}
    added.push(next)
  }
  return added
}
export function editPart(parts,index,key,value){
  const next=structuredClone(parts);next[index][key]=value
  if(key==='start'&&index>0)next[index-1].end={...value}
  if(key==='end'&&index+1<next.length)next[index+1].start={...value}
  return next
}
export function movePart(parts,index,delta){
  const next=structuredClone(parts),[part]=next.splice(index,1);next.splice(index+delta,0,part)
  return next.map((p,i)=>i?{...p,start:{...next[i-1].end}}:p)
}
export function inletGeometry(geometry){
  const p=geometry.parts[0],s=p.start
  const width=s.width_mm-2*s.wall_mm-(p.kind==='multiport'?(p.channels-1)*p.web_mm:0)
  const area=s.shape==='round'?Math.PI*s.diameter_mm**2/4:width*(s.height_mm-2*s.wall_mm)
  return {inlet_area_m2:area*1e-6,inner_diameter_mm:Math.sqrt(4*area/Math.PI)}
}
export function thermalTotals(groups){return {heat_w:groups.filter(g=>g.kind==='heat').reduce((v,g)=>v+Number(g.power_w),0),faces:groups.reduce((v,g)=>v+g.faces.length,0)}}
