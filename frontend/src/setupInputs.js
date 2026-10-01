// Unit factors and material values come from the same catalog as the backend.
export const fluidProperties = [
  ['density_kg_m3','Density','kg/m³',30000],
  ['dynamic_viscosity_pa_s','Dynamic viscosity','Pa·s',100],
  ['specific_heat_j_kg_k','Specific heat capacity','J/kg·K',100000],
  ['thermal_conductivity_w_m_k','Thermal conductivity','W/m·K',10000],
]
export const solidProperties = [
  ['solid_conductivity_w_m_k','Thermal conductivity','W/m·K',10000],
  ['solid_density_kg_m3','Density','kg/m³',30000],
  ['solid_specific_heat_j_kg_k','Specific heat capacity','J/kg·K',100000],
]

export function boundaryOf(form) {
  return form.inlet ?? {kind:'velocity',value:form.inlet_velocity_m_s,unit:'m/s'}
}

export function inletVelocity(form, catalog) {
  const inlet=boundaryOf(form),factor=catalog.inlet_units[inlet.kind].units.find(u=>u.id===inlet.unit)?.factor_to_si
  const area=Math.PI*(Number(form.inner_diameter_mm)/1000)**2/4,density=Number(form.density_kg_m3)
  if(!(Number(inlet.value)>0&&area>0&&density>0&&factor>0))return null
  const si=Number(inlet.value)*factor
  return inlet.kind==='velocity'?si:inlet.kind==='volumetric_flow'?si/area:si/(density*area)
}

export function changeBoundary(form, catalog, kind, unit=catalog.inlet_units[kind].default_unit) {
  const velocity=inletVelocity(form,catalog),area=Math.PI*(Number(form.inner_diameter_mm)/1000)**2/4
  const factor=catalog.inlet_units[kind].units.find(u=>u.id===unit)?.factor_to_si
  const si=kind==='velocity'?velocity:kind==='volumetric_flow'?velocity*area:velocity*area*Number(form.density_kg_m3)
  const value=velocity===null||!Number.isFinite(si/factor)?'':Number((si/factor).toPrecision(12))
  return {...form,inlet:{kind,value,unit}}
}

export function chooseFluid(form, catalog, fluid) {
  return {...form,fluid,...(catalog.fluids[fluid]?.values ?? {})}
}

export function chooseMaterial(form, catalog, material) {
  return {...form,material,...catalog.materials[material].values}
}

export function isEdited(form, preset) {
  return preset && Object.entries(preset.values).some(([key,value])=>form[key]!=null&&Number(form[key])!==value)
}

export function inputsDiffer(form, saved) {
  // A structured boundary owns the velocity; the backend stores its derived
  // SI value while the form can still carry a legacy cached velocity.
  return Object.keys(form).some(key => !(key==='inlet_velocity_m_s'&&form.inlet)
    && JSON.stringify(form[key])!==JSON.stringify(saved[key]))
}
