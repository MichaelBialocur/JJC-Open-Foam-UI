import { useEffect, useState } from 'react'
import Chart from './Chart'
import Viewport from './Viewport'
import FieldViewer from './FieldViewer'
import './App.css'

const defaults = { geometry_type: 'pipe', length_mm: 500, inner_diameter_mm: 10, wall_thickness_mm: 2,
  material: 'aluminium', inlet_velocity_m_s: 1, inlet_temperature_c: 20, applied_heat_w: 0,
  density_kg_m3: 998, dynamic_viscosity_pa_s: 0.001002, flow_model: 'auto', mesh_level: 'medium',
  max_iterations: 2500, residual_tolerance: 0.000001, turbulence_intensity: 0.05, reference: 'auto',
  specific_heat_j_kg_k: 4182, thermal_conductivity_w_m_k: .6, turbulent_prandtl: .85, thermal_iterations: 200 }
const activeStates = ['queued', 'generating', 'meshing', 'checking', 'solving', 'heating', 'processing']
const fmt = (x, digits = 3) => x == null || !Number.isFinite(x) ? '—' : Number(x.toPrecision(digits)).toLocaleString('en', { maximumSignificantDigits: digits })
const statusText = s => ({ not_converged: 'Iteration limit reached', completed: 'Convergence checks passed', not_qualified: 'Checks need attention', within_project_target: 'Within screening target', outside_project_target: 'Outside screening target' }[s] || s?.replaceAll('_', ' '))
async function api(path, body, signal) {
  const response = await fetch(path, body === undefined ? { signal } : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal })
  const data = await response.json()
  if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : data.detail?.map(d => `${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ') || `Server error ${response.status}`)
  return data
}
function Metric({ label, value, unit, detail }) {
  return <div className="metric"><span>{label}</span><strong>{value}<small>{unit}</small></strong>{detail && <p>{detail}</p>}</div>
}
function App() {
  const [form, setForm] = useState(defaults), [preview, setPreview] = useState(null)
  const [health, setHealth] = useState(null), [presets, setPresets] = useState({})
  const [jobs, setJobs] = useState([]), [selected, setSelected] = useState(null), [job, setJob] = useState(null)
  const [error, setError] = useState(''), [previewError, setPreviewError] = useState(''), [busy, setBusy] = useState(false)
  const [study, setStudy] = useState([])
  useEffect(() => {
    const controller = new AbortController()
    Promise.all([api('/api/health', undefined, controller.signal), api('/api/presets', undefined, controller.signal)])
      .then(([h, p]) => { setHealth(h); setPresets(p) }).catch(e => { if (e.name !== 'AbortError') setError(`Backend unavailable: ${e.message}`) })
    return () => controller.abort()
  }, [])
  useEffect(() => {
    const controller = new AbortController()
    const timer = setTimeout(() => api('/api/pipe/preview', form, controller.signal)
      .then(data => { setPreview(data); setPreviewError('') }).catch(e => { if (e.name !== 'AbortError') { setPreview(null); setPreviewError(e.message) } }), 250)
    return () => { clearTimeout(timer); controller.abort() }
  }, [form])
  useEffect(() => {
    let stopped = false, timer
    const controller = new AbortController()
    async function refresh() {
      try {
        const recent = await api('/api/jobs', undefined, controller.signal)
        if (stopped) return
        setJobs(recent)
        if (selected) {
          const current = await api(`/api/jobs/${selected}`, undefined, controller.signal)
          if (stopped) return
          setJob(current)
          if (current.study_id) {
            const members = await Promise.all(recent.filter(j => j.study_id === current.study_id).map(j => api(`/api/jobs/${j.id}`, undefined, controller.signal)))
            if (!stopped) setStudy(members)
          } else setStudy([])
        }
      } catch (e) { if (!stopped && e.name !== 'AbortError') setError(e.message) }
      if (!stopped) timer = setTimeout(refresh, 1500)
    }
    refresh()
    return () => { stopped = true; clearTimeout(timer); controller.abort() }
  }, [selected])
  function update(event) {
    const { name, value, type } = event.target
    setForm(old => ({ ...old, [name]: type === 'number' ? (value === '' ? '' : Number(value)) : value }))
  }
  async function submit(meshStudy = false) {
    setBusy(true); setError('')
    try {
      const data = await api(meshStudy ? '/api/mesh-studies' : '/api/jobs', form)
      const chosen = meshStudy ? data.jobs[2] : data
      setSelected(chosen.id); setJob(chosen)
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function cancel() {
    try { setJob(await api(`/api/jobs/${selected}/cancel`, {})) } catch (e) { setError(e.message) }
  }
  const number = (name, label, unit, step = 'any') => <label key={name}>{label}<div><input name={name} type="number" step={step} value={form[name]} onChange={update} /><span>{unit}</span></div></label>
  const results = job?.results, validation = results?.validation, thermal = results?.thermal
  const active = activeStates.includes(job?.status)
  const disabled = busy || !preview || preview.run_errors.length > 0 || !health?.openfoam?.available
  const shownSpec = job?.inputs || form
  const changed = job && Object.keys(defaults).some(k => job.inputs[k] !== form[k])
  const residuals = results?.convergence?.history || job?.progress?.history || []
  const studyRows = [...study].sort((a,b) => ['coarse','medium','fine'].indexOf(a.inputs.mesh_level) - ['coarse','medium','fine'].indexOf(b.inputs.mesh_level))
  const heatedStudy = studyRows.some(s=>s.inputs.applied_heat_w>0)

  return <div className="app">
    <header><div><h1>Pipe CFD <span className="version">0.3</span></h1><p>OpenFOAM · flow, heating & computed field views</p></div>
      <div className="header-actions"><span className={`badge ${health?.openfoam?.available ? 'good' : 'warn'}`}>{health?.openfoam?.available ? 'OpenFOAM 14 ready' : 'OpenFOAM unavailable'}</span>
        <button disabled={disabled} onClick={() => submit()}>Run simulation</button></div></header>
    <main><aside className="controls">
      <section><h2>Reference cases</h2><div className="preset-buttons">{Object.entries(presets).map(([key, p]) => <button className="secondary" key={key} title={p.description} onClick={() => { setForm(p.inputs); setError('') }}>{p.name}</button>)}</div></section>
      <section><h2>Pipe geometry</h2>{number('length_mm','Length','mm')}{number('inner_diameter_mm','Inner diameter','mm')}
        <details><summary>Wall geometry</summary>{number('wall_thickness_mm','Wall thickness','mm')}
          <label>Material<select name="material" value={form.material} onChange={update}><option value="aluminium">Aluminium</option><option value="copper">Copper</option></select></label>
          <p className="muted">Shown in 3D. Wall conduction is not solved; material and thickness do not affect the fluid-only heating model.</p></details></section>
      <section><h2>Fluid & flow</h2>{number('inlet_velocity_m_s','Mean inlet velocity','m/s')}{number('density_kg_m3','Density','kg/m³')}
        {number('dynamic_viscosity_pa_s','Dynamic viscosity','Pa·s')}
        <p className="muted">Default properties: water near 20 °C. Enter properties for your temperature/fluid; values stay constant during a run.</p>
        <label>Flow model<select name="flow_model" value={form.flow_model} onChange={update}><option value="auto">Automatic by Reynolds number</option><option value="laminar">Laminar</option><option value="kOmegaSST">Turbulent · k–ω SST</option></select></label></section>
      <section><h2>Fluid heating</h2>{number('applied_heat_w','Heat input through inner wall','W')}{number('inlet_temperature_c','Inlet temperature','°C')}
        {number('specific_heat_j_kg_k','Specific heat capacity','J/kg·K')}{number('thermal_conductivity_w_m_k','Fluid thermal conductivity','W/m·K')}
        <p className="muted">0 W runs flow only. Positive heat runs a fluid energy solve with uniform wall heat flux. Constant properties; no buoyancy, phase change or solid conduction.</p>
        {preview?.thermal.enabled&&<p className="muted">Energy-balance estimate: +{fmt(preview.thermal.ideal_temperature_rise_k)} K if all heat leaves with the fluid. Pr = {fmt(preview.thermal.prandtl)}.</p>}
        <details><summary>Thermal solver settings</summary>{number('turbulent_prandtl','Turbulent Prandtl number','')}{number('thermal_iterations','Temperature iterations','steps',50)}</details></section>
      <section><h2>Mesh & convergence</h2><label>Mesh refinement<select name="mesh_level" value={form.mesh_level} onChange={update}><option value="coarse">Coarse · 1,920 cells</option><option value="medium">Medium · 7,680 cells</option><option value="fine">Fine · 30,720 cells</option></select></label>
        {number('max_iterations','Maximum iterations','steps',100)}<details><summary>Advanced solver settings</summary>{number('residual_tolerance','Residual tolerance','')}{number('turbulence_intensity','Inlet turbulence intensity','fraction')}</details>
        <button className="secondary full" disabled={disabled} onClick={() => submit(true)}>Run three-mesh study</button><p className="muted">Runs coarse, medium, then fine in a queue. One solver runs at a time.</p></section>
    </aside>
    <div className="workspace">
      {(error || previewError) && <div className="error" role="alert">{error || previewError}</div>}
      {health && !health.openfoam.available && <div className="notice warn">{health.openfoam.error}</div>}
      {preview?.run_errors.map(message => <div className="notice warn" key={message}>{message}</div>)}
      <div className="overview"><Metric label="Reynolds number" value={fmt(preview?.flow.reynolds_number,5)} detail={preview?.flow.model === 'laminar' ? 'Laminar flow' : 'Turbulent RANS · k–ω SST'} />
        <Metric label="Volumetric flow" value={fmt(preview?.flow.flow_rate_l_min)} unit="L/min" detail="Calculated from the current inputs" />
        <Metric label="Mesh" value={preview?.mesh.cells.toLocaleString() || '—'} unit="cells" detail="5° axisymmetric wedge" /></div>
      <section className="panel"><div className="panel-heading"><h2>{job ? 'Saved run · 3D geometry' : '3D geometry preview'}</h2><span className="muted">L {fmt(shownSpec.length_mm)} mm · ID {fmt(shownSpec.inner_diameter_mm)} mm · wall {fmt(shownSpec.wall_thickness_mm)} mm</span></div><Viewport spec={shownSpec} />
        {changed && <p className="notice">Results and geometry below belong to the selected saved run. Inputs on the left have changed; run again to compare.</p>}</section>
      <section className="panel"><div className="panel-heading"><h2>Simulation runs</h2><span className="muted">Stored locally across restarts</span></div>
        {!jobs.length ? <p className="muted">Choose a reference preset or enter your pipe dimensions, then run a simulation.</p> : <div className="run-list">{jobs.slice(0,12).map(j => <button key={j.id} className={`run-item ${selected===j.id?'selected':''}`} onClick={() => { setSelected(j.id); setJob(null); setError('') }}>
          <span>{new Date(j.created_at*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · {j.inputs.mesh_level}</span>
          <span>Re {fmt(j.inputs.density_kg_m3*j.inputs.inlet_velocity_m_s*j.inputs.inner_diameter_mm/1000/j.inputs.dynamic_viscosity_pa_s,5)}</span>
          <span className={`badge ${j.status==='completed'?'good':j.status==='failed'?'bad':''}`}>{statusText(j.status)}</span></button>)}</div>}
        {job && <div className="run-status"><strong>{statusText(job.status)}</strong><span>{job.status==='heating'?`Temperature iteration ${job.thermal_progress?.iteration || 0} / ${job.inputs.thermal_iterations || 200}`:`Flow iteration ${job.progress?.iteration || 0} / ${job.inputs.max_iterations}`}</span>
          {active && <button className="danger" onClick={cancel}>Cancel this run</button>}{!active && <a className="button secondary" href={`/api/jobs/${selected}/case.zip`}>Download OpenFOAM case</a>}</div>}
        {job?.error && <p className="error">{job.error}</p>}
        {job && <details><summary>Solver log</summary><pre>{job.log || 'Waiting for the solver…'}</pre></details>}
      </section>
      {results && <>
        <FieldViewer key={selected} jobId={selected} spec={shownSpec}/>
        <div className="overview"><Metric label="Sampled pressure drop" value={fmt(results.pressure_drop_pa)} unit="Pa" detail={`Between x = ${fmt(results.pressure_drop_stations_m[0])} and ${fmt(results.pressure_drop_stations_m[1])} m; includes entrance development.`} />
          <Metric label="Developed pressure gradient" value={fmt(results.developed_pressure_gradient_pa_m)} unit="Pa/m" detail={`Fit over x = ${results.fit_stations_m.map(x=>fmt(x)).join('–')} m`} />
          <Metric label="Darcy friction factor" value={fmt(results.darcy_friction_factor,5)} detail="From the computed pressure gradient" /></div>
        <section className="panel"><div className="panel-heading"><h2>Reference comparison</h2><span className={`badge ${validation.status==='within_project_target'?'good':'warn'}`}>{statusText(validation.status)}</span></div>
          <p><a href={validation.reference.url} target="_blank" rel="noreferrer">{validation.reference.title}</a> <span className="badge">{validation.reference.kind}</span></p>
          {!validation.reference.applicable && <p className="notice warn">No matching experiment at this Reynolds number. Use the Princeton preset for the supplied experimental comparison.</p>}
          <div className="overview"><Metric label="Friction-factor deviation" value={fmt(validation.friction_error_percent)} unit="%" detail="Signed difference from the reference" /><Metric label="Velocity-profile RMSE" value={fmt(validation.profile_rmse_percent_of_bulk)} unit="% of Ū" detail="Normalized profile; common sampled radii only" /><Metric label="Flow conservation error" value={fmt(results.mass_balance_error_percent)} unit="%" /></div>
          <div className="checks">{Object.entries(validation.checks).map(([key,ok]) => <span className={ok?'good':'warn'} key={key}>{ok?'✓':'!'} {key.replaceAll('_',' ')}</span>)}</div>
          <p className="muted">Gradient drift {fmt(results.gradient_drift_percent)}%; profile drift {fmt(results.profile_drift_percent)}%; estimated near-wall y⁺ {fmt(results.estimated_y_plus)} (pressure-gradient estimate).</p>
          <p className="muted">{results.convergence.convergence_basis}. {validation.note} Screening target: {validation.project_target_percent}% for friction factor and profile RMSE. {validation.reference.caveat}</p>
          <div className="exports"><a href={`/api/jobs/${selected}/results.json`}>Export results JSON</a><a href={`/api/jobs/${selected}/profile.csv`}>Export velocity CSV</a></div>
        </section>
        <div className="chart-grid"><Chart title={`Velocity at x = ${fmt(results.profile_station_m)} m`} xLabel="r / R · centre → wall" xDomain={[0,1]} yLabel="U / Ū" series={[
          {name:'CFD',color:'#59b9fa',points:results.velocity_profile.map(p=>({x:p.r_over_R,y:p.u_over_bulk}))},
          {name:validation.reference.kind==='analytical'?'Analytical':'Experiment',color:'#f3b85c',dashed:true,points:results.reference_profile.map(p=>({x:p.r_over_R,y:p.u_over_bulk}))}]} />
          <Chart title="Axial pressure" xLabel="Axial position (mm)" xDomain={[0,shownSpec.length_mm]} yLabel="Gauge pressure (Pa)" series={[{name:'CFD · area-weighted section mean',color:'#62d5aa',points:results.pressure_profile.map(p=>({x:p.x_m*1000,y:p.pressure_pa}))}]} /></div>
        {thermal&&<>
          <section className="panel"><div className="panel-heading"><h2>Heating & thermal verification</h2><span className={`badge ${thermal.validation.status==='within_project_target'?'good':'warn'}`}>{statusText(thermal.validation.status)}</span></div>
            <div className="overview"><Metric label="Outlet mixing temperature" value={fmt(thermal.outlet_bulk_temperature_c,5)} unit="°C" detail={`Inlet ${fmt(thermal.inlet_temperature_c)} °C · mass-flow-weighted outlet`} />
              <Metric label="Heat carried by fluid" value={fmt(thermal.advected_heat_w,5)} unit="W" detail={`${fmt(thermal.inlet_conduction_loss_w)} W also leaves by inlet conduction`} />
              <Metric label="Energy balance error" value={fmt(thermal.energy_balance_error_percent)} unit="%" detail="Heat input compared with outlet advection + inlet conduction" /></div>
            <p><a href={thermal.validation.reference.url} target="_blank" rel="noreferrer">{thermal.validation.reference.title}</a> <span className="badge">Analytical verification</span></p>
            <p>Developed Nu: <b>{fmt(thermal.developed_nusselt,5)}</b>{thermal.validation.reference.applicable?` · Reference ${fmt(thermal.validation.reference.nusselt,5)} · Deviation ${fmt(thermal.validation.nusselt_error_percent)}%`:' · This laminar reference does not apply to turbulent flow.'}</p>
            <div className="checks">{Object.entries(thermal.validation.checks).map(([key,ok])=><span key={key} className={ok?'good':'warn'}>{ok?'✓':'!'} {key.replaceAll('_',' ')}</span>)}</div>
            <p className="muted">{thermal.limitations} {thermal.validation.reference.caveat}</p>
            <div className="exports"><a href={`/api/jobs/${selected}/thermal.csv`}>Export temperatures & Nu CSV</a></div>
          </section>
          <div className="chart-grid"><Chart title="Fluid heating along the pipe" xLabel="Axial position (mm)" xDomain={[0,shownSpec.length_mm]} yLabel="Temperature (°C)" zeroBaseline={false} series={[
            {name:'Mixing temperature',color:'#59b9fa',points:thermal.profile.map(p=>({x:p.x_m*1000,y:p.bulk_temperature_c}))},
            {name:'Inner wall / fluid interface',color:'#f3b85c',points:thermal.profile.map(p=>({x:p.x_m*1000,y:p.wall_temperature_c}))}]} />
            <Chart title="Local heat transfer" xLabel="Axial position (mm)" xDomain={[0,shownSpec.length_mm]} yLabel="Nusselt number" series={[
              {name:'Computed Nu',color:'#62d5aa',points:thermal.profile.map(p=>({x:p.x_m*1000,y:p.nusselt}))},
              {name:'Fully developed laminar limit',color:'#f3b85c',dashed:true,points:thermal.validation.reference.applicable?[{x:0,y:48/11},{x:shownSpec.length_mm,y:48/11}]:[]}]} /></div>
        </>}
      </>}
      {!!residuals.length && <Chart title="Convergence · initial equation residuals" xLabel="Solver iteration" yLabel="Residual (log scale)" logarithmic series={['p','Ux','Uy','Uz','k','omega'].map((key,i)=>({name:key,color:['#59b9fa','#62d5aa','#cc9bff','#f3b85c','#f78190','#b6d07b'][i],points:residuals.map(r=>({x:r.iteration,y:r[key]}))}))} />}
      {!!(thermal?.convergence?.history || job?.thermal_progress?.history)?.length&&<Chart title="Temperature convergence · frozen flow" xLabel="Temperature iteration" yLabel="Residual (log scale)" logarithmic series={[{name:'T',color:'#f3b85c',points:(thermal?.convergence?.history || job.thermal_progress.history).map(r=>({x:r.iteration,y:r.T}))}]} />}
      {!!studyRows.length && <section className="panel"><h2>Mesh refinement comparison</h2><div className="table-scroll"><table><thead><tr><th>Mesh</th><th>Status</th><th>Darcy f</th><th>Flow reference error</th><th>Δf from coarser</th>{heatedStudy&&<><th>Developed Nu</th><th>Nu reference error</th><th>ΔNu from coarser</th></>}</tr></thead><tbody>{studyRows.map((s,i)=>{
        const f=s.results?.darcy_friction_factor, prev=studyRows[i-1]?.results?.darcy_friction_factor
        const nu=s.results?.thermal?.developed_nusselt, previousNu=studyRows[i-1]?.results?.thermal?.developed_nusselt
        return <tr key={s.id}><td>{s.inputs.mesh_level}</td><td>{statusText(s.status)}</td><td>{fmt(f,6)}</td><td>{fmt(s.results?.validation.friction_error_percent)}%</td><td>{prev && f ? `${fmt(100*Math.abs(f-prev)/Math.abs(f))}%`:'—'}</td>{heatedStudy&&<><td>{fmt(nu,6)}</td><td>{fmt(s.results?.thermal?.validation.nusselt_error_percent)}%</td><td>{previousNu&&nu?`${fmt(100*Math.abs(nu-previousNu)/Math.abs(nu))}%`:'—'}</td></>}</tr>
      })}</tbody></table></div><p className="muted">Inspect convergence and reference checks for every mesh. A small mesh-to-mesh change alone is not proof of model accuracy.</p></section>}
      <footer>Pipe CFD 0.3 · Actual OpenFOAM flow and fluid temperature fields · Axisymmetric pipe model · CAD, full 3D flow and conjugate solid/fluid heat transfer are future stages.</footer>
    </div></main>
  </div>
}
export default App
