import { boundaryOf, changeBoundary } from './setupInputs'

export default function InletControls({ form, catalog, setForm, flow }) {
  const inlet=boundaryOf(form)
  return <div className="inlet-controls">
    <label>Inlet boundary<select name="inlet_kind" value={inlet.kind} onChange={e=>setForm(old=>changeBoundary(old,catalog,e.target.value))}>
      {Object.entries(catalog.inlet_units).map(([key,group])=><option key={key} value={key}>{group.label}</option>)}</select></label>
    <label>{catalog.inlet_units[inlet.kind].label}<div className="value-unit">
      <input name="inlet_value" type="number" step="any" min="1e-15" value={inlet.value} onChange={e=>setForm(old=>({...old,inlet:{...boundaryOf(old),value:e.target.value===''?'':Number(e.target.value)}}))}/>
      <select name="inlet_unit" aria-label="Inlet unit" value={inlet.unit} onChange={e=>setForm(old=>changeBoundary(old,catalog,boundaryOf(old).kind,e.target.value))}>
        {catalog.inlet_units[inlet.kind].units.map(unit=><option value={unit.id} key={unit.id}>{unit.label}</option>)}</select></div></label>
    {inlet.unit==='CFM'&&<p className="muted">CFM = actual ft³/min at the selected fluid conditions, not SCFM.</p>}
    {inlet.kind==='mass_flow'&&<p className="muted">Velocity uses the selected fluid density.</p>}
    {flow&&<p className="muted inlet-equivalents">{Number(flow.velocity_m_s.toPrecision(5))} m/s · {Number(flow.flow_rate_l_min.toPrecision(5))} L/min · {Number(flow.mass_flow_kg_h.toPrecision(5))} kg/h</p>}
  </div>
}
