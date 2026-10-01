import {useEffect,useRef,useState} from 'react'
import AssemblyViewport from './AssemblyViewport'
import InletControls from './InletControls'
import PropertyEditor from './PropertyEditor'
import RunHistory from './RunHistory'
import {appendPart,editPart,movePart,newId,inletGeometry,physicsDefaults,thermalTotals} from './assemblyInputs'
import {chooseFluid,chooseMaterial,fluidProperties,solidProperties,isEdited} from './setupInputs'
import './AssemblyApp.css'

const activeStates=['queued','generating','meshing','checking','solving','heating','processing']
const fmt=(v,n=4)=>Number.isFinite(v)?Number(v.toPrecision(n)).toLocaleString('en',{maximumSignificantDigits:n}):'—'
async function api(path,body,signal){
  const response=await fetch(path,body===undefined?{signal}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal})
  const data=await response.json()
  if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:data.detail?.map(d=>`${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')||`Server error ${response.status}`),{status:response.status})
  return data
}
function NumberInput({label,value,onChange,unit='',min,max,step='any'}){
  return <label>{label}<div><input type="number" value={value} onChange={e=>onChange(e.target.value===''?'':Number(e.target.value))} min={min} max={max} step={step}/><span>{unit}</span></div></label>
}
function SectionEditor({label,section,onChange,allowShape}){
  const update=(key,value)=>onChange({...section,[key]:value})
  return <fieldset><legend>{label}</legend>
    {allowShape&&<label>Section<select value={section.shape} onChange={e=>update('shape',e.target.value)}><option value="round">Round</option><option value="rectangle">Rectangular</option></select></label>}
    {section.shape==='round'?<NumberInput label="Internal diameter" value={section.diameter_mm} onChange={v=>update('diameter_mm',v)} unit="mm" min={.2}/>:
      <><NumberInput label="Outside width" value={section.width_mm} onChange={v=>update('width_mm',v)} unit="mm" min={.2}/><NumberInput label="Outside height" value={section.height_mm} onChange={v=>update('height_mm',v)} unit="mm" min={.2}/></>}
    <NumberInput label="Wall thickness" value={section.wall_mm} onChange={v=>update('wall_mm',v)} unit="mm" min={.05}/>
  </fieldset>
}
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
function Results({job}){
  const r=job.results,t=r.thermal
  return <><div className="overview"><Metric label="Pressure drop" value={r.pressure_drop_pa} unit="Pa"/><Metric label="Actual flow" value={r.volumetric_flow_l_min} unit="L/min"/><Metric label="Flow balance error" value={r.mass_balance_error_percent} unit="%"/></div>
    <AssemblyFields key={job.id} job={job}/>
    {t&&<section className="panel"><h2>Heating & cooling balance</h2><div className="overview"><Metric label="Outlet mixing temperature" value={t.outlet_temperature_c} unit="°C"/><Metric label="Maximum solid cell temperature" value={t.maximum_solid_temperature_c} unit="°C"/><Metric label="Energy balance error" value={t.energy_balance_error_percent} unit="%"/></div>
      <p className="muted">Fluid heat gain {fmt(t.advective_heat_gain_w)} W · inlet conductive loss {fmt(t.inlet_conductive_loss_w)} W. Positive face power below leaves the solid; negative power heats it.</p>
      <div className="table-scroll"><table><thead><tr><th>Face</th><th>Boundary</th><th>Mean surface °C</th><th>Computed W</th><th>Specified W</th></tr></thead><tbody>{t.faces.map(f=><tr key={f.face}><td>{f.face}</td><td>{f.kind}</td><td>{fmt(f.mean_temperature_c)}</td><td>{fmt(f.computed_heat_leaving_w)}</td><td>{fmt(f.specified_boundary_heat_leaving_w)}</td></tr>)}</tbody></table></div></section>}
    <section className="panel"><h2>Numerical checks & reference comparison</h2><p className="notice warn">The new 3D solver has not yet met its pipe pressure-gradient accuracy target. Review the <a href="https://github.com/MichaelBialocur/JJC-Open-Foam-UI/blob/main/docs/ASSEMBLY_BENCHMARKS.md" target="_blank" rel="noreferrer">measured validation report</a> and compare refined meshes before using predictions.</p><div className="checks">{Object.entries(r.checks).map(([name,ok])=><span key={name} className={ok?'good':'warn'}>{ok?'✓':'!'} {name.replaceAll('_',' ')}</span>)}</div>
      <p className="muted">{r.fluid_cells.toLocaleString()} fluid cells{t?` · ${t.solid_cells.toLocaleString()} solid cells`:''}. Convergence and conservation do not establish mesh independence.</p>
      <p className="muted">{r.reference.note}</p>{r.reference.kind==='analytical'&&<p className="muted"><a href={r.reference.url} target="_blank" rel="noreferrer">{r.reference.title}</a>: {fmt(r.reference.error_percent)}% friction-factor deviation · {r.reference.applicable?'developed-flow checks passed':'comparison not qualified'}.</p>}
      <div className="exports"><a href={`/api/jobs/${job.id}/results.json`}>Results JSON</a><a href={`/api/jobs/${job.id}/case.zip`}>OpenFOAM case / ParaView</a></div>
    </section></>
}

export default function AssemblyApp(){
  const [catalog,setCatalog]=useState(null),[presets,setPresets]=useState({}),[health,setHealth]=useState(null)
  const [draft,setDraft]=useState(null),[built,setBuilt]=useState(null),[busy,setBusy]=useState(false),[error,setError]=useState(''),[notice,setNotice]=useState('')
  const [partIndex,setPartIndex]=useState(0),[selection,setSelection]=useState([]),[groupKind,setGroupKind]=useState('heat'),[editor,setEditor]=useState(null)
  const [operating,setOperating]=useState(null),[operatingError,setOperatingError]=useState(''),[jobs,setJobs]=useState([]),[selectedJob,setSelectedJob]=useState(null),[job,setJob]=useState(null)
  const [deletingRuns,setDeletingRuns]=useState(false)
  const revision=useRef(0),fileInput=useRef(null),deletedIds=useRef(new Set())
  useEffect(()=>{
    const controller=new AbortController()
    Promise.all([api('/api/materials',undefined,controller.signal),api('/api/assembly/presets',undefined,controller.signal),api('/api/assembly/health',undefined,controller.signal)]).then(([c,p,h])=>{
      setCatalog(c);setPresets(p);setHealth(h)
      let saved=null;try{saved=JSON.parse(localStorage.getItem('pipe-cfd-assembly-v1'))}catch{/* A fresh draft remains available if local storage is disabled. */}
      const initial={geometry_type:'assembly',name:'My cold plate',geometry:p.coldplate.geometry,physics:chooseFluid({...physicsDefaults},c,'water'),mesh_size_mm:2,boundaries:[],boundary_geometry_key:null}
      setDraft(saved?.geometry?.parts?.length?{...initial,...saved}:initial)
    }).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return()=>controller.abort()
  },[])
  useEffect(()=>{if(draft){try{localStorage.setItem('pipe-cfd-assembly-v1',JSON.stringify(draft))}catch{/* Download design is also available. */}}},[draft])
  useEffect(()=>{
    if(!draft)return
    const controller=new AbortController(),timer=setTimeout(()=>api('/api/assembly/operating',draft,controller.signal).then(d=>{setOperating(d);setOperatingError('')}).catch(e=>{if(e.name!=='AbortError'){setOperating(null);setOperatingError(e.message)}}),300)
    return()=>{controller.abort();clearTimeout(timer)}
  },[draft])
  useEffect(()=>{
    if(deletingRuns)return
    let live=true,timer
    const controller=new AbortController()
    async function poll(){
      try{
        const list=(await api('/api/assembly/jobs',undefined,controller.signal)).filter(j=>!deletedIds.current.has(j.id))
        if(!live)return
        setJobs(list)
        if(selectedJob&&!list.some(j=>j.id===selectedJob)){setSelectedJob(null);setJob(null)}
        else if(selectedJob&&!deletedIds.current.has(selectedJob)){
          const j=await api(`/api/jobs/${selectedJob}`,undefined,controller.signal)
          if(live&&!deletedIds.current.has(selectedJob))setJob(j)
        }
      }catch(e){if(live&&!deletedIds.current.has(selectedJob)&&e.name!=='AbortError'){
        if(e.status===404&&selectedJob){setSelectedJob(null);setJob(null)}else setError(e.message)
      }}
      if(live)timer=setTimeout(poll,2500)
    }
    poll();return()=>{live=false;clearTimeout(timer);controller.abort()}
  },[selectedJob,deletingRuns])
  function runsDeleted(ids){
    ids.forEach(id=>deletedIds.current.add(id));setJobs(old=>old.filter(j=>!deletedIds.current.has(j.id)))
    if(ids.includes(selectedJob)){setSelectedJob(null);setJob(null)}
  }
  const updatePhysics=change=>setDraft(old=>({...old,physics:typeof change==='function'?change({...old.physics,...inletGeometry(old.geometry)}):{...old.physics,...change}}))
  function changeGeometry(geometry){revision.current++;setDraft(old=>({...old,geometry,boundaries:[],boundary_geometry_key:null}));setBuilt(null);setSelection([]);setNotice('Geometry edited. Build it again, then assign heating and cooling faces. Previous face assignments were cleared.')}
  function loadPreset(key){changeGeometry(structuredClone(presets[key].geometry));setPartIndex(0)}
  async function build(){
    const atRevision=revision.current;setBusy(true);setError('')
    try{const data=await api('/api/assembly/preview',draft.geometry);if(atRevision===revision.current){setBuilt(data);setNotice('Geometry built. Select any exterior faces in the view or the face list.');if(draft.boundaries.length&&draft.boundary_geometry_key!==data.geometry_key)setDraft(old=>({...old,boundaries:[],boundary_geometry_key:null}))}}
    catch(e){setError(e.message)}finally{setBusy(false)}
  }
  function pick(id){setSelection(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id])}
  function addGroup(){
    const assigned=new Set(draft.boundaries.flatMap(g=>g.faces)),available=selection.filter(id=>!assigned.has(id))
    if(!available.length){setError('Select unassigned exterior faces first. Remove an existing boundary to reassign its faces.');return}
    setDraft(old=>({...old,boundary_geometry_key:built.geometry_key,boundaries:[...old.boundaries,{id:newId('g'),name:groupKind==='heat'?'Heating':'Convection cooling',kind:groupKind,faces:available,power_w:10,h_w_m2_k:100,ambient_c:20}]}));setSelection([]);setError('')
  }
  function editGroup(index,key,value){setDraft(old=>({...old,boundaries:old.boundaries.map((g,i)=>i===index?{...g,[key]:value}:g)}))}
  async function run(){setError('');try{const j=await api('/api/assembly/jobs',draft);setSelectedJob(j.id);setJob(j)}catch(e){setError(e.message)}}
  function download(){const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='cold-plate-design.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  async function loadFile(file){
    if(!file)return
    try{if(file.size>1000000)throw new Error('Design file is too large.');const data=JSON.parse(await file.text());await api('/api/assembly/operating',data);revision.current++;setDraft(data);setBuilt(null);setSelection([]);setPartIndex(0);setNotice('Design loaded. Build geometry to restore and inspect its faces.');setError('')}catch(e){setError(`Could not load design: ${e.message}`)}
  }
  if(!draft)return <div className="workspace"><h1>Geometry builder</h1><p>{error||'Loading…'}</p></div>
  const part=draft.geometry.parts[partIndex]??draft.geometry.parts[0],index=draft.geometry.parts.indexOf(part)
  const changePart=(key,value)=>changeGeometry({...draft.geometry,parts:editPart(draft.geometry.parts,index,key,value)})
  const totals=thermalTotals(draft.boundaries),faces=built?.faces.filter(f=>f.selectable)??[],assigned=Object.fromEntries(draft.boundaries.flatMap(g=>g.faces.map(f=>[f,g.name])))
  const disabled=busy||!built||!operating||operating.run_errors.length>0||!health?.mesher.available||!health?.openfoam.available
  return <div className="assembly-app"><header><div><h1>Geometry builder <span className="version">0.6.2</span></h1><p>Connected piping, manifolds and multi-port cold plates</p></div><div className="header-actions"><button className="secondary" onClick={build} disabled={busy}>{busy?'Building…':'Build geometry'}</button><button onClick={run} disabled={disabled}>Mesh & run simulation</button></div></header>
    <main className="assembly-layout"><aside className="controls" tabIndex={0} aria-label="Geometry controls">
      <section><h2>Design</h2><label>Design name<input value={draft.name} maxLength={80} onChange={e=>setDraft(old=>({...old,name:e.target.value}))}/></label>
        <label>Start from<select value="" onChange={e=>loadPreset(e.target.value)}><option value="" disabled>Choose a template…</option>{Object.entries(presets).map(([id,p])=><option value={id} key={id}>{p.name}</option>)}</select></label>
        <div className="builder-actions"><button className="secondary" onClick={download}>Save design</button><button className="secondary" onClick={()=>fileInput.current.click()}>Load design</button><input ref={fileInput} className="hidden" type="file" accept=".json" onChange={e=>{loadFile(e.target.files[0]);e.target.value=''}}/></div>
      </section>
      <section><h2>Connected parts</h2><ol className="part-list">{draft.geometry.parts.map((p,i)=><li key={p.id}><button className={index===i?'selected':'secondary'} onClick={()=>setPartIndex(i)}>{i+1}. {p.name}<small>{p.kind==='bend'?`${p.angle_deg}° · R ${p.radius_mm} mm`:`${p.length_mm} mm · ${p.kind}`}</small></button></li>)}</ol>
        <label>Add at outlet<select value="" onChange={e=>{const parts=appendPart(draft.geometry.parts,e.target.value);changeGeometry({...draft.geometry,parts});setPartIndex(parts.length-1)}}><option value="" disabled>Choose a part…</option><option value="straight">Straight / tapered tube</option><option value="bend">Bend</option><option value="manifold">Transition / manifold</option><option value="multiport">Multi-port tube</option></select></label>
        <p className="muted">A multi-port tube added after round piping automatically gets an inlet manifold. Add another manifold to return to round piping.</p>
      </section>
      <section><h2>{index+1}. Part dimensions</h2><label>Part name<input value={part.name} maxLength={60} onChange={e=>changePart('name',e.target.value)}/></label>
        <div className="builder-actions"><button className="secondary" disabled={index===0} onClick={()=>{changeGeometry({...draft.geometry,parts:movePart(draft.geometry.parts,index,-1)});setPartIndex(index-1)}}>Move up</button><button className="secondary" disabled={index===draft.geometry.parts.length-1} onClick={()=>{changeGeometry({...draft.geometry,parts:movePart(draft.geometry.parts,index,1)});setPartIndex(index+1)}}>Move down</button><button className="danger" disabled={draft.geometry.parts.length===1} onClick={()=>{const parts=draft.geometry.parts.filter((_,i)=>i!==index).map((p,i,all)=>i?{...p,start:{...all[i-1].end}}:p);changeGeometry({...draft.geometry,parts});setPartIndex(Math.max(0,index-1))}}>Remove</button></div>
        {part.kind==='bend'?<><NumberInput label="Centreline bend radius" value={part.radius_mm} onChange={v=>changePart('radius_mm',v)} unit="mm"/><NumberInput label="Turn angle" value={part.angle_deg} onChange={v=>changePart('angle_deg',v)} unit="°" min={1} max={270}/><NumberInput label="Bend plane rotation" value={part.roll_deg} onChange={v=>changePart('roll_deg',v)} unit="°" min={-360} max={360}/><p className="muted">0° turns toward local width; 90° turns toward local height. Orientation carries through to the next part.</p></>:
          <NumberInput label="Length" value={part.length_mm} onChange={v=>changePart('length_mm',v)} unit="mm" min={.2}/>}
        <SectionEditor label="Start section" section={part.start} onChange={s=>changePart('start',s)} allowShape={part.kind==='manifold'}/>
        <SectionEditor label="End section" section={part.end} onChange={s=>changePart('end',s)} allowShape={part.kind==='manifold'}/>
        <button className="secondary full" onClick={()=>changePart('end',{...part.start})}>Make end match start</button>
        {part.kind==='multiport'&&<><NumberInput label="Parallel channels" value={part.channels} onChange={v=>changePart('channels',v)} min={1} max={64} step={1}/><NumberInput label="Internal web thickness" value={part.web_mm} onChange={v=>changePart('web_mm',v)} unit="mm" min={.05}/></>}
        <p className="muted">Connected ends share their dimensions. Editing one also updates its neighbour. Rectangular sizes are outside dimensions; round diameter is internal.</p>
        <details><summary>Assembly position & orientation</summary>{['X','Y','Z'].map((a,i)=><NumberInput key={a} label={`Start ${a}`} unit="mm" value={(draft.geometry.origin_mm??[0,0,0])[i]} onChange={v=>{const origin=[...(draft.geometry.origin_mm??[0,0,0])];origin[i]=v;changeGeometry({...draft.geometry,origin_mm:origin})}}/>)}{['yaw','pitch'].map(a=><NumberInput key={a} label={`${a} angle`} unit="°" value={draft.geometry[`${a}_deg`]??0} onChange={v=>changeGeometry({...draft.geometry,[`${a}_deg`]:v})}/>)}</details>
      </section>
      <section><h2>Fluid & inlet</h2>{catalog&&<><label>Fluid</label><div className="preset-picker"><select aria-label="Builder fluid" value={draft.physics.fluid} onChange={e=>updatePhysics(old=>chooseFluid(old,catalog,e.target.value))}>{Object.entries(catalog.fluids).map(([id,p])=><option key={id} value={id}>{p.label}</option>)}</select><button className="secondary" onClick={()=>setEditor('fluid')}>Edit</button></div><p className="muted">{isEdited(draft.physics,catalog.fluids[draft.physics.fluid])?'Edited properties':'Preset properties'} · constant during the run</p><InletControls form={{...draft.physics,...inletGeometry(draft.geometry)}} catalog={catalog} setForm={updatePhysics} flow={operating?.flow}/></>}
        <NumberInput label="Inlet temperature" value={draft.physics.inlet_temperature_c} onChange={v=>updatePhysics({inlet_temperature_c:v})} unit="°C"/>
        <details><summary>Flow model</summary><label>Model<select value={draft.physics.flow_model} onChange={e=>updatePhysics({flow_model:e.target.value})}><option value="auto">Automatic, from inlet Reynolds number</option><option value="laminar">Laminar</option><option value="kOmegaSST">k–ω SST</option></select></label><p className="muted">Inlet-based regime selection is a screening rule. Local channel and manifold flow can differ. Full 3D turbulence needs wall-resolution and mesh-sensitivity checks.</p></details>
      </section>
      <section><h2>Solid wall material</h2>{catalog&&<><div className="preset-picker"><select aria-label="Builder wall material" value={draft.physics.material} onChange={e=>updatePhysics(old=>chooseMaterial(old,catalog,e.target.value))}>{Object.entries(catalog.materials).map(([id,p])=><option key={id} value={id}>{p.label}</option>)}</select><button className="secondary" onClick={()=>setEditor('solid')}>Edit</button></div><p className="muted">One material for the whole connected solid, including internal webs.</p></>}</section>
      <section><h2>Mesh & convergence</h2><NumberInput label="Target cell size" value={draft.mesh_size_mm} onChange={v=>setDraft(old=>({...old,mesh_size_mm:v}))} unit="mm" min={.05}/><NumberInput label="Flow iterations" value={draft.physics.max_iterations} onChange={v=>updatePhysics({max_iterations:v})} step={100}/><NumberInput label="Thermal iterations" value={draft.physics.thermal_iterations} onChange={v=>updatePhysics({thermal_iterations:v})} step={100}/><p className="muted">Conforming tetrahedra in fluid and solid. Repeat with smaller cells to check pressure and temperature sensitivity. No fixed cell-count or elapsed-time cap. Larger meshes need more RAM, disk space and runtime. Runs queue one at a time and can be cancelled.</p></section>
    </aside><div className="workspace" tabIndex={0} role="region" aria-label="Geometry and results">
      {error&&<p className="error" role="alert">{error}</p>}{operatingError&&<p className="notice warn">{operatingError}</p>}{notice&&<p className="notice">{notice}</p>}
      {health&&Object.values(health).filter(h=>!h.available).map(h=><p className="error" key={h.error}>{h.error}</p>)}{operating?.run_errors.map(e=><p className="notice warn" key={e}>{e}</p>)}
      <div className="overview"><Metric label="Inlet Reynolds number" value={operating?.flow.reynolds_number}/><Metric label="Specified heat input" value={totals.heat_w} unit="W"/><Metric label="Thermal faces assigned" value={totals.faces}/></div>
      <section className="panel"><div className="panel-heading"><h2>Current design · 3D geometry</h2><span className="muted">{draft.geometry.parts.length} parts · {operating?.flow.model}</span></div>
        {built?<AssemblyViewport data={built} selected={selection} groups={draft.boundaries} onPick={pick}/>:<div className="build-placeholder"><b>Build your connected geometry</b><p>Edit the parts, then click Build geometry to generate the solid and fluid passages.</p><button onClick={build} disabled={busy}>{busy?'Building geometry…':'Build geometry'}</button></div>}
        {built&&<details><summary>Start & end coordinates (mm)</summary><div className="table-scroll"><table><thead><tr><th>Part</th><th>Start X / Y / Z</th><th>End X / Y / Z</th></tr></thead><tbody>{built.layout.map(p=><tr key={p.id}><td>{p.name}</td><td>{p.start_mm.map(v=>fmt(v)).join(' / ')}</td><td>{p.end_mm.map(v=>fmt(v)).join(' / ')}</td></tr>)}</tbody></table></div><p className="muted">Endpoints follow the connected centreline; lengths, bend radii and angles determine them.</p></details>}
      </section>
      <section className="panel"><h2>Face heating & cooling</h2><p className="muted">Select as many exterior faces as needed. Each face belongs to one boundary group. Unassigned faces are insulated. Separate groups can use different power or convection settings.</p>
        {built&&<><div className="boundary-actions"><label>New boundary<select value={groupKind} onChange={e=>setGroupKind(e.target.value)}><option value="heat">Heating · total power</option><option value="convection">Convection · h and ambient temperature</option></select></label><button disabled={!selection.length} onClick={addGroup}>Assign {selection.length} selected face{selection.length===1?'':'s'}</button><button className="secondary" onClick={()=>setSelection([])}>Clear selection</button><button className="secondary" onClick={()=>setSelection(faces.filter(f=>!assigned[f.id]).map(f=>f.id))}>Select all unassigned</button></div>
          <details open><summary>Exterior face list ({faces.length})</summary><div className="face-list">{faces.map(f=><label className="check-label" key={f.id}><input type="checkbox" checked={selection.includes(f.id)} onChange={()=>pick(f.id)}/><span>{f.label} · {fmt(f.area_mm2)} mm²{assigned[f.id]?` · ${assigned[f.id]}`:''}</span></label>)}</div></details></>}
        <div className="boundary-groups">{draft.boundaries.map((g,i)=><div className={`boundary-card ${g.kind}`} key={g.id}><label>Boundary name<input value={g.name} onChange={e=>editGroup(i,'name',e.target.value)}/></label><p className="muted">{g.faces.length} faces · {g.kind==='heat'?'Total group power is distributed in proportion to face area.':'Heat leaves when the wall is hotter than ambient; convection can also warm a colder wall.'}</p>
          {g.kind==='heat'?<NumberInput label="Total power across these faces" value={g.power_w} onChange={v=>editGroup(i,'power_w',v)} unit="W" min={0}/>:<><NumberInput label="Heat-transfer coefficient" value={g.h_w_m2_k} onChange={v=>editGroup(i,'h_w_m2_k',v)} unit="W/m²·K" min={.0001}/><NumberInput label="Ambient temperature" value={g.ambient_c} onChange={v=>editGroup(i,'ambient_c',v)} unit="°C"/></>}
          <div className="builder-actions"><button className="secondary" disabled={!built} onClick={()=>setSelection(g.faces)}>Highlight faces</button><button className="danger" onClick={()=>setDraft(old=>({...old,boundaries:old.boundaries.filter((_,n)=>n!==i)}))}>Remove boundary</button></div></div>)}</div>
        {!draft.boundaries.length&&<p className="muted">No thermal boundaries: the next run solves flow only.</p>}
      </section>
      <section className="panel"><h2>Saved assembly runs</h2><RunHistory jobs={jobs} selectedId={selectedJob} onSelect={id=>{setSelectedJob(id);setJob(null);setError('')}} onDeleted={runsDeleted} onDeletingChange={setDeletingRuns}>{j=><><span>{j.inputs.name} · {j.inputs.mesh_size_mm} mm</span><span className="badge">{j.status.replaceAll('_',' ')}</span></>}</RunHistory>
        {job&&<><div className="run-status"><b>{job.status.replaceAll('_',' ')}</b><span>Flow {job.progress?.iteration??0} · thermal {job.thermal_progress?.iteration??0}</span>{activeStates.includes(job.status)?<button className="danger" onClick={()=>api(`/api/jobs/${job.id}/cancel`,{}).then(setJob).catch(e=>setError(e.message))}>Cancel run</button>:<button className="secondary" onClick={()=>{revision.current++;setDraft(structuredClone(job.inputs));setBuilt(null);setSelection([]);setPartIndex(0);setNotice('Saved design loaded. Build geometry to inspect its assigned faces.')}}>Load this design</button>}</div><p className="muted">Results below belong to “{job.inputs.name}”, saved with {job.inputs.geometry.parts.length} parts and a {job.inputs.mesh_size_mm} mm mesh target. The editable design above is independent.</p>{job.error&&<p className="error">{job.error}</p>}<details><summary>Run log</summary><pre>{job.log||'Queued…'}</pre></details></>}
      </section>{job?.results&&<Results job={job}/>}
      <footer>Full 3D incompressible flow and frozen-flow, coupled fluid/solid heating. Constant properties; no buoyancy, radiation, phase change or contact resistance. Inline manifolds feed parallel channels. CAD import and general branched networks remain future work.</footer>
    </div></main>
    {editor&&<PropertyEditor title={editor==='solid'?'Edit wall material':'Edit fluid properties'} properties={editor==='solid'?solidProperties:fluidProperties} form={draft.physics} preset={editor==='solid'?catalog.materials[draft.physics.material]:catalog.fluids[draft.physics.fluid]} solid={editor==='solid'} onClose={()=>setEditor(null)} onApply={values=>{updatePhysics(values);setEditor(null)}}/>}
  </div>
}
