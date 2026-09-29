import { useEffect, useState } from 'react'
import Chart from './Chart'
import './App.css'

const defaults = { geometry_type: 'pipe', length_mm: 500, inner_diameter_mm: 10, wall_thickness_mm: 2,
  material: 'aluminium', inlet_velocity_m_s: 1, inlet_temperature_c: 20, applied_heat_w: 0,
  density_kg_m3: 998, dynamic_viscosity_pa_s: 0.001002, flow_model: 'auto', mesh_level: 'medium',
  max_iterations: 2500, residual_tolerance: 0.000001, turbulence_intensity: 0.05, reference: 'auto' }
const activeStates = ['queued', 'generating', 'meshing', 'checking', 'solving', 'processing']
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
function PipeView({ spec }) {
  const radius = Math.max(20, Math.min(48, spec.inner_diameter_mm * 2))
  return <svg className="pipe-geometry" viewBox="0 0 760 190" role="img" aria-label="Pipe geometry schematic with inlet, wall, and outlet">
    <defs><linearGradient id="steel" x2="0" y2="1"><stop stopColor="#738395" /><stop offset=".4" stopColor="#253444" /><stop offset="1" stopColor="#586677" /></linearGradient></defs>
    <path d={`M150 ${95-radius} H610 A18 ${radius} 0 0 1 610 ${95+radius} H150 Z`} fill="url(#steel)" stroke="#8292a2" />
    <ellipse cx="150" cy="95" rx="18" ry={radius} fill="#142332" stroke="#9cabb8" />
    <ellipse cx="150" cy="95" rx="13" ry={radius - 7} fill="#0a1825" stroke="#5585a5" />
    <path d="M40 95H120M108 89L120 95L108 101" stroke="#59b9fa" fill="none" strokeWidth="2" />
    <path d="M641 95H714M702 89L714 95L702 101" stroke="#62d5aa" fill="none" strokeWidth="2" />
    <text x="44" y="73" fill="#59b9fa">Inlet</text><text x="657" y="73" fill="#62d5aa">Outlet</text>
    <text x="380" y="29" textAnchor="middle" fill="#abbac9">{fmt(spec.length_mm)} mm · ID {fmt(spec.inner_diameter_mm)} mm</text>
    <text x="380" y="173" textAnchor="middle" fill="#91a4b6">Smooth no-slip wall · axisymmetric flow · schematic, not to scale</text>
  </svg>
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
  const results = job?.results, validation = results?.validation
  const active = activeStates.includes(job?.status)
  const disabled = busy || !preview || preview.run_errors.length > 0 || !health?.openfoam?.available
  const shownSpec = job?.inputs || form
  const changed = job && Object.keys(defaults).some(k => job.inputs[k] !== form[k])
  const residuals = results?.convergence?.history || job?.progress?.history || []
  const studyRows = [...study].sort((a,b) => ['coarse','medium','fine'].indexOf(a.inputs.mesh_level) - ['coarse','medium','fine'].indexOf(b.inputs.mesh_level))

  return <div className="app">
    <header><div><h1>Pipe CFD <span className="version">0.2</span></h1><p>OpenFOAM · flow simulation & reference checks</p></div>
      <div className="header-actions"><span className={`badge ${health?.openfoam?.available ? 'good' : 'warn'}`}>{health?.openfoam?.available ? 'OpenFOAM 14 ready' : 'OpenFOAM unavailable'}</span>
        <button disabled={disabled} onClick={() => submit()}>Run simulation</button></div></header>
    <main><aside className="controls">
      <section><h2>Reference cases</h2><div className="preset-buttons">{Object.entries(presets).map(([key, p]) => <button className="secondary" key={key} title={p.description} onClick={() => { setForm(p.inputs); setError('') }}>{p.name}</button>)}</div></section>
      <section><h2>Pipe geometry</h2>{number('length_mm','Length','mm')}{number('inner_diameter_mm','Inner diameter','mm')}
        <details><summary>Wall metadata · thermal stage later</summary>{number('wall_thickness_mm','Wall thickness','mm')}
          <label>Material<select name="material" value={form.material} onChange={update}><option value="aluminium">Aluminium</option><option value="copper">Copper</option></select></label>
          {number('applied_heat_w','Applied heat','W')}<p className="muted">Set heat to 0 W for this isothermal release.</p></details></section>
      <section><h2>Fluid & flow</h2>{number('inlet_velocity_m_s','Mean inlet velocity','m/s')}{number('density_kg_m3','Density','kg/m³')}
        {number('dynamic_viscosity_pa_s','Dynamic viscosity','Pa·s')}{number('inlet_temperature_c','Reference temperature','°C')}
        <p className="muted">Default properties: water near 20 °C. Enter properties for your temperature/fluid; values stay constant during a run.</p>
        <label>Flow model<select name="flow_model" value={form.flow_model} onChange={update}><option value="auto">Automatic by Reynolds number</option><option value="laminar">Laminar</option><option value="kOmegaSST">Turbulent · k–ω SST</option></select></label></section>
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
      <section className="panel"><div className="panel-heading"><h2>{job ? 'Saved run geometry' : 'Geometry preview'}</h2><span className="muted">Isothermal · smooth circular pipe</span></div><PipeView spec={shownSpec} />
        {changed && <p className="notice">Results and geometry below belong to the selected saved run. Inputs on the left have changed; run again to compare.</p>}</section>
      <section className="panel"><div className="panel-heading"><h2>Simulation runs</h2><span className="muted">Stored locally across restarts</span></div>
        {!jobs.length ? <p className="muted">Choose a reference preset or enter your pipe dimensions, then run a simulation.</p> : <div className="run-list">{jobs.slice(0,12).map(j => <button key={j.id} className={`run-item ${selected===j.id?'selected':''}`} onClick={() => { setSelected(j.id); setJob(null); setError('') }}>
          <span>{new Date(j.created_at*1000).toLocaleString([], {month:'short',day:'numeric',hour:'2-digit',minute:'2-digit'})} · {j.inputs.mesh_level}</span>
          <span>Re {fmt(j.inputs.density_kg_m3*j.inputs.inlet_velocity_m_s*j.inputs.inner_diameter_mm/1000/j.inputs.dynamic_viscosity_pa_s,5)}</span>
          <span className={`badge ${j.status==='completed'?'good':j.status==='failed'?'bad':''}`}>{statusText(j.status)}</span></button>)}</div>}
        {job && <div className="run-status"><strong>{statusText(job.status)}</strong><span>Iteration {job.progress?.iteration || 0} / {job.inputs.max_iterations}</span>
          {active && <button className="danger" onClick={cancel}>Cancel this run</button>}{!active && <a className="button secondary" href={`/api/jobs/${selected}/case.zip`}>Download OpenFOAM case</a>}</div>}
        {job?.error && <p className="error">{job.error}</p>}
        {job && <details><summary>Solver log</summary><pre>{job.log || 'Waiting for the solver…'}</pre></details>}
      </section>
      {results && <>
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
        <div className="chart-grid"><Chart title={`Velocity at x = ${fmt(results.profile_station_m)} m`} xLabel="r / R · centre → wall" yLabel="U / Ū" series={[
          {name:'CFD',color:'#59b9fa',points:results.velocity_profile.map(p=>({x:p.r_over_R,y:p.u_over_bulk}))},
          {name:validation.reference.kind==='analytical'?'Analytical':'Experiment',color:'#f3b85c',dashed:true,points:results.reference_profile.map(p=>({x:p.r_over_R,y:p.u_over_bulk}))}]} />
          <Chart title="Axial pressure" xLabel="Axial position (m)" yLabel="Gauge pressure (Pa)" series={[{name:'CFD · area-weighted section mean',color:'#62d5aa',points:results.pressure_profile.map(p=>({x:p.x_m,y:p.pressure_pa}))}]} /></div>
      </>}
      {!!residuals.length && <Chart title="Convergence · initial equation residuals" xLabel="Solver iteration" yLabel="Residual (log scale)" logarithmic series={['p','Ux','Uy','Uz','k','omega'].map((key,i)=>({name:key,color:['#59b9fa','#62d5aa','#cc9bff','#f3b85c','#f78190','#b6d07b'][i],points:residuals.map(r=>({x:r.iteration,y:r[key]}))}))} />}
      {!!studyRows.length && <section className="panel"><h2>Mesh refinement comparison</h2><div className="table-scroll"><table><thead><tr><th>Mesh</th><th>Status</th><th>Darcy f</th><th>Reference error</th><th>Change from coarser</th></tr></thead><tbody>{studyRows.map((s,i)=>{
        const f=s.results?.darcy_friction_factor, prev=studyRows[i-1]?.results?.darcy_friction_factor
        return <tr key={s.id}><td>{s.inputs.mesh_level}</td><td>{statusText(s.status)}</td><td>{fmt(f,6)}</td><td>{fmt(s.results?.validation.friction_error_percent)}%</td><td>{prev && f ? `${fmt(100*Math.abs(f-prev)/Math.abs(f))}%`:'—'}</td></tr>
      })}</tbody></table></div><p className="muted">Inspect convergence and reference checks for every mesh. A small mesh-to-mesh change alone is not proof of model accuracy.</p></section>}
      <footer>Pipe CFD 0.2 · Actual OpenFOAM fields · Thermal conduction and heat exchange are not solved in this release.</footer>
    </div></main>
  </div>
}
export default App
