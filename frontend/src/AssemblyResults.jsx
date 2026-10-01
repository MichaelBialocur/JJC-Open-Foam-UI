import {useEffect,useState} from 'react'
import AssemblyViewport from './AssemblyViewport'
import {api,fmt} from './uiApi'

function Metric({label,value,unit}){return <div className="metric"><span>{label}</span><strong>{fmt(value)}<small>{unit}</small></strong></div>}
function AssemblyFields({job}){
  const [region,setRegion]=useState('fluid'),[field,setField]=useState('speed'),[axis,setAxis]=useState(''),[fraction,setFraction]=useState(.5),[data,setData]=useState(null),[error,setError]=useState('')
  useEffect(()=>{
    const controller=new AbortController()
    const timer=setTimeout(()=>api(`/api/assembly/jobs/${job.id}/fields?region=${region}&field=${field}${axis?`&axis=${axis}&fraction=${fraction}`:''}`,undefined,controller.signal)
      .then(d=>{setData(d);setError('')}).catch(e=>{if(e.name!=='AbortError')setError(e.message)}),200)
    return()=>{clearTimeout(timer);controller.abort()}
  },[job.id,region,field,axis,fraction])
  return <section className="panel"><h2>Computed 3D results</h2><div className="field-toolbar">
    <label>Region<select value={region} onChange={e=>{setRegion(e.target.value);if(e.target.value==='solid')setField('temperature');setData(null)}}><option value="fluid">Fluid</option>{job.results.thermal&&<option value="solid">Solid wall</option>}</select></label>
    <label>Field<select value={field} onChange={e=>{setField(e.target.value);setData(null)}}>{region==='fluid'&&<><option value="speed">Speed</option><option value="pressure">Gauge pressure</option></>}{job.results.thermal&&<option value="temperature">Temperature</option>}</select></label>
    <label>Display<select value={axis} onChange={e=>{setAxis(e.target.value);setData(null)}}><option value="">Surface · adjacent cells</option>{['x','y','z'].map(a=><option key={a} value={a}>{a.toUpperCase()} slice</option>)}</select></label>
  </div>{axis&&<label>Slice position · {Math.round(fraction*100)}% of {axis.toUpperCase()} extent<input type="range" min="0.001" max="0.999" step="0.01" value={fraction} onChange={e=>{setFraction(Number(e.target.value))}}/></label>}
    {error&&<p className="error">{error}</p>}{data?<AssemblyViewport data={data} field/>:<p className="muted">Loading computed cells…</p>}
    <p className="muted">Finite-volume cell values from this saved run. Click a facet to probe its cell. An empty slice can lie in a gap between passages. Download the case for ParaView filters and streamlines.</p>
  </section>
}
export default function Results({job}){
  const r=job.results,t=r.thermal
  return <><div className="overview"><Metric label="Pressure drop" value={r.pressure_drop_pa} unit="Pa"/><Metric label="Actual flow" value={r.volumetric_flow_l_min} unit="L/min"/><Metric label="Flow balance error" value={r.mass_balance_error_percent} unit="%"/></div>
    <AssemblyFields key={job.id} job={job}/>
    {t&&<section className="panel"><h2>Heating & cooling balance</h2><div className="overview"><Metric label="Outlet mixing temperature" value={t.outlet_temperature_c} unit="°C"/><Metric label="Maximum solid cell temperature" value={t.maximum_solid_temperature_c} unit="°C"/><Metric label="Energy balance error" value={t.energy_balance_error_percent} unit="%"/></div>
      <p className="muted">Fluid heat gain {fmt(t.advective_heat_gain_w)} W · inlet conductive loss {fmt(t.inlet_conductive_loss_w)} W. Positive face power below leaves the solid; negative power heats it.</p>
      <div className="table-scroll"><table><thead><tr><th>Face</th><th>Boundary</th><th>Mean surface °C</th><th>Computed W</th><th>Specified W</th></tr></thead><tbody>{t.faces.map(f=><tr key={f.face}><td>{f.face}</td><td>{f.kind}</td><td>{fmt(f.mean_temperature_c)}</td><td>{fmt(f.computed_heat_leaving_w)}</td><td>{fmt(f.specified_boundary_heat_leaving_w)}</td></tr>)}</tbody></table></div></section>}
    <section className="panel"><h2>Numerical checks & reference comparison</h2><p className="notice warn">The new 3D solver has not yet met its pipe pressure-gradient accuracy target. Review the <a href={`https://github.com/MichaelBialocur/JJC-Open-Foam-UI/blob/main/docs/${job.inputs.geometry_type==='cad'?'CAD':'ASSEMBLY'}_BENCHMARKS.md`} target="_blank" rel="noreferrer">measured validation report</a> and compare refined meshes before using predictions.</p><div className="checks">{Object.entries(r.checks).map(([name,ok])=><span key={name} className={ok?'good':'warn'}>{ok?'✓':'!'} {name.replaceAll('_',' ')}</span>)}</div>
      <p className="muted">{r.fluid_cells.toLocaleString()} fluid cells{t?` · ${t.solid_cells.toLocaleString()} solid cells`:''}. Convergence and conservation do not establish mesh independence.</p>
      <p className="muted">{r.reference.note}</p>{r.reference.kind==='analytical'&&<p className="muted"><a href={r.reference.url} target="_blank" rel="noreferrer">{r.reference.title}</a>: {fmt(r.reference.error_percent)}% friction-factor deviation · {r.reference.applicable?'developed-flow checks passed':'comparison not qualified'}.</p>}
      <div className="exports"><a href={`/api/jobs/${job.id}/results.json`}>Results JSON</a><a href={`/api/jobs/${job.id}/case.zip`}>OpenFOAM case / ParaView</a></div>
    </section></>
}
