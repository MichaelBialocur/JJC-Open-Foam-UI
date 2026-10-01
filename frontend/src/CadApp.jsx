import {useEffect,useMemo,useRef,useState} from 'react'
import AssemblyViewport from './AssemblyViewport'
import Results from './AssemblyResults'
import InletControls from './InletControls'
import PropertyEditor from './PropertyEditor'
import RunHistory from './RunHistory'
import {api,fmt} from './uiApi'
import {newId,physicsDefaults} from './assemblyInputs'
import {chooseFluid,chooseMaterial,fluidProperties,solidProperties} from './setupInputs'
import './AssemblyApp.css'

const active=['queued','generating','meshing','checking','solving','heating','processing']
function NumberInput({label,value,onChange,unit='',min,step='any'}){
  return <label>{label}<div><input type="number" value={value} min={min} step={step} onChange={e=>onChange(e.target.value===''?'':Number(e.target.value))}/><span>{unit}</span></div></label>
}
const cleanFaces={inlet_faces:[],outlet_faces:[],boundaries:[],boundary_geometry_key:null,metrics:null}
function isSetup(data){
  const strings=value=>Array.isArray(value)&&value.every(v=>typeof v==='string')
  return data?.geometry_type==='cad'&&typeof data.name==='string'&&/^[a-f0-9]{64}$/.test(data.geometry?.source_id??'')
    &&strings(data.geometry.fluid_bodies)&&strings(data.geometry.solid_bodies)&&Number.isFinite(data.geometry.scale)&&data.geometry.scale>0
    &&strings(data.inlet_faces)&&strings(data.outlet_faces)&&data.physics&&typeof data.physics==='object'
    &&Array.isArray(data.boundaries)&&data.boundaries.every(b=>b&&typeof b.id==='string'&&['heat','convection'].includes(b.kind)&&strings(b.faces))
}

export default function CadApp(){
  const [catalog,setCatalog]=useState(null),[health,setHealth]=useState(null),[draft,setDraft]=useState(null)
  const [source,setSource]=useState(null),[built,setBuilt]=useState(null),[selection,setSelection]=useState([])
  const [busy,setBusy]=useState(''),[error,setError]=useState(''),[notice,setNotice]=useState(''),[editor,setEditor]=useState(null)
  const [kind,setKind]=useState('inlet'),[operating,setOperating]=useState(null),[operatingError,setOperatingError]=useState('')
  const [jobs,setJobs]=useState([]),[job,setJob]=useState(null),[selectedJob,setSelectedJob]=useState(null),[deleting,setDeleting]=useState(false)
  const uploadInput=useRef(null),setupInput=useRef(null),revision=useRef(0),deletedIds=useRef(new Set())
  useEffect(()=>{
    const controller=new AbortController()
    Promise.all([api('/api/materials',undefined,controller.signal),api('/api/assembly/health',undefined,controller.signal)]).then(async([c,h])=>{
      setCatalog(c);setHealth(h)
      let saved=null;try{saved=JSON.parse(localStorage.getItem('pipe-cfd-cad-v1'))}catch{/* Empty draft. */}
      if(isSetup(saved)){
        setDraft(saved)
        const imported=await api(`/api/cad/sources/${encodeURIComponent(saved.geometry.source_id)}`,undefined,controller.signal)
        setSource(imported)
        if(saved.geometry.fluid_bodies.length)setBuilt(await api('/api/cad/preview',saved.geometry,controller.signal))
      }
    }).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return()=>controller.abort()
  },[])
  useEffect(()=>{if(draft){try{localStorage.setItem('pipe-cfd-cad-v1',JSON.stringify(draft))}catch{/* Saved runs retain inputs. */}}},[draft])
  useEffect(()=>{
    const controller=new AbortController()
    const timer=setTimeout(()=>{
      if(!built||!draft?.inlet_faces.length||!draft.outlet_faces.length){setOperating(null);setOperatingError('');return}
      api('/api/cad/operating',draft,controller.signal).then(d=>{setOperating(d);setOperatingError('')})
        .catch(e=>{if(e.name!=='AbortError'){setOperating(null);setOperatingError(e.message)}})
    },250)
    return()=>{clearTimeout(timer);controller.abort()}
  },[draft,built])
  useEffect(()=>{
    if(deleting)return
    let live=true,timer
    const controller=new AbortController()
    async function poll(){
      try{
        const list=(await api('/api/cad/jobs',undefined,controller.signal)).filter(j=>!deletedIds.current.has(j.id))
        if(!live)return
        setJobs(list)
        if(selectedJob&&!list.some(j=>j.id===selectedJob)){setSelectedJob(null);setJob(null)}
        else if(selectedJob){const j=await api(`/api/jobs/${selectedJob}`,undefined,controller.signal);if(live&&!deletedIds.current.has(j.id))setJob(j)}
      }catch(e){if(live&&e.name!=='AbortError'){if(e.status===404){setSelectedJob(null);setJob(null)}else setError(e.message)}}
      if(live)timer=setTimeout(poll,2500)
    }
    poll();return()=>{live=false;clearTimeout(timer);controller.abort()}
  },[selectedJob,deleting])
  const faces=built?.faces.filter(f=>f.selectable)??[]
  const inletArea=faces.filter(f=>draft?.inlet_faces.includes(f.id)).reduce((n,f)=>n+f.area_mm2*1e-6,0)
  const groups=useMemo(()=>draft?[{kind:'inlet',faces:draft.inlet_faces},{kind:'outlet',faces:draft.outlet_faces},...draft.boundaries]:[],[draft])
  const assigned=Object.fromEntries(groups.flatMap(g=>g.faces.map(f=>[f,g.name??g.kind])))
  function changeGeometry(geometry){
    revision.current++;setBuilt(null);setSelection([]);setOperating(null)
    setDraft(old=>({...old,geometry,...cleanFaces}));setNotice('Body roles or scale changed. Prepare the bodies, then assign their faces again.')
  }
  function role(id,value){
    const geometry={...draft.geometry,fluid_bodies:draft.geometry.fluid_bodies.filter(v=>v!==id),solid_bodies:draft.geometry.solid_bodies.filter(v=>v!==id)}
    if(value!=='ignore')geometry[`${value}_bodies`].push(id)
    changeGeometry(geometry)
  }
  const updatePhysics=change=>setDraft(old=>({...old,physics:typeof change==='function'?change({...old.physics,inlet_area_m2:inletArea}):{...old.physics,...change}}))
  async function upload(file){
    if(!file)return
    setBusy('Importing CAD…');setError('');revision.current++
    try{
      const response=await fetch(`/api/cad/sources?filename=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'Content-Type':'application/octet-stream'},body:file})
      const data=await response.json();if(!response.ok)throw new Error(typeof data.detail==='string'?data.detail:'The CAD file could not be imported.')
      setSource(data);setBuilt(null);setSelection([]);setOperating(null)
      setDraft({geometry_type:'cad',name:file.name.replace(/\.[^.]+$/,'').slice(0,80),geometry:{source_id:data.source_id,scale:1,fluid_bodies:[],solid_bodies:[]},
        physics:chooseFluid({...physicsDefaults},catalog,'water'),mesh_size_mm:2,...cleanFaces})
      setNotice('CAD imported. Identify the closed fluid body and any surrounding solid bodies below, then prepare them.')
    }catch(e){setError(e.message)}finally{setBusy('')}
  }
  async function prepare(){
    const at=revision.current;setBusy('Preparing bodies…');setError('')
    try{const data=await api('/api/cad/preview',draft.geometry);if(at===revision.current){setBuilt(data);setSelection([]);setNotice('Select fluid inlet/outlet faces and exterior solid faces for heating or cooling.')}}
    catch(e){setError(e.message)}finally{setBusy('')}
  }
  function pick(id){
    if(!built){const face=source?.preview.faces.find(f=>f.id===id);if(face)setSelection(source.preview.faces.filter(f=>f.body_ids.some(v=>face.body_ids.includes(v))).map(f=>f.id));return}
    setSelection(old=>old.includes(id)?old.filter(x=>x!==id):[...old,id])
  }
  function assign(){
    const selected=faces.filter(f=>selection.includes(f.id))
    if(!selected.length){setError('Select one or more faces first.');return}
    if(selected.some(f=>assigned[f.id])){setError('Remove the previous assignment before reassigning a face.');return}
    const port=kind==='inlet'||kind==='outlet'
    if(selected.some(f=>port?(!f.port_selectable||!f.planar):!f.thermal_selectable)){
      setError(port?'Inlets and outlets must be planar exterior fluid faces. Use Fluid passages to see the flow volume.':'Heating and cooling require exterior solid faces. Use Solid bodies to select them.');return
    }
    setDraft(old=>({...old,boundary_geometry_key:built.geometry_key,...(port?{[`${kind}_faces`]:[...old[`${kind}_faces`],...selection]}:
      {boundaries:[...old.boundaries,{id:newId('g'),name:kind==='heat'?'Heating':'Convection cooling',kind,faces:selection,power_w:10,h_w_m2_k:100,ambient_c:20}]})}))
    setSelection([]);setError('')
  }
  function editGroup(index,key,value){setDraft(old=>({...old,boundaries:old.boundaries.map((g,i)=>i===index?{...g,[key]:value}:g)}))}
  async function run(){
    setBusy('Submitting run…');setError('')
    try{const j=await api('/api/cad/jobs',draft);setSelectedJob(j.id);setJob(j)}catch(e){setError(e.message)}finally{setBusy('')}
  }
  async function restore(data){
    if(!isSetup(data))throw new Error('Choose a valid CAD setup JSON saved by this app.')
    revision.current++;setBusy('Loading setup…');setError('')
    try{
      const imported=await api(`/api/cad/sources/${encodeURIComponent(data.geometry.source_id)}`)
      const prepared=data.geometry.fluid_bodies.length?await api('/api/cad/preview',data.geometry):null
      setSource(imported);setDraft(data);setBuilt(prepared);setSelection([]);setOperating(null);setNotice('CAD setup restored. The editable setup is separate from saved results.')
    }finally{setBusy('')}
  }
  async function loadSetup(file){try{if(!file)return;if(file.size>2000000)throw new Error('The setup JSON is too large.');await restore(JSON.parse(await file.text()))}catch(e){setError(e.message)}}
  function saveSetup(){const url=URL.createObjectURL(new Blob([JSON.stringify(draft,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download='cad-setup.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}
  function deleted(ids){ids.forEach(id=>deletedIds.current.add(id));setJobs(old=>old.filter(j=>!deletedIds.current.has(j.id)));if(ids.includes(selectedJob)){setJob(null);setSelectedJob(null)}}
  const disabled=!!busy||!built||!operating||!!operatingError||operating.run_errors.length>0||!health?.openfoam.available
  return <div className="assembly-app"><header><div><h1>CAD import <span className="version">0.7.0</span></h1><p>Closed fluid and solid bodies · selectable flow and thermal boundaries</p></div><div className="header-actions"><button className="secondary" disabled={!!busy||!catalog} onClick={()=>uploadInput.current.click()}>Import CAD</button><button disabled={disabled} onClick={run}>Mesh & run simulation</button></div></header>
    <input ref={uploadInput} className="hidden" type="file" accept=".step,.stp,.iges,.igs,.brep" onChange={e=>{upload(e.target.files[0]);e.target.value=''}}/>
    <input ref={setupInput} className="hidden" type="file" accept=".json" onChange={e=>{loadSetup(e.target.files[0]);e.target.value=''}}/>
    <main className="assembly-layout"><aside className="controls" tabIndex={0} aria-label="CAD controls">
      <section><h2>1 · Import & prepare</h2><p className="muted">STEP is recommended. IGES and BREP are accepted when they contain closed bodies. Export the fluid cavity as its own body; include metal bodies for heat transfer.</p>
        <button className="secondary full" disabled={!!busy||!catalog} onClick={()=>uploadInput.current.click()}>Choose CAD file</button>
        <button className="secondary full" disabled={!!busy} onClick={()=>setupInput.current.click()}>Load saved setup</button>
        {source&&draft&&<><p className="cad-filename">{source.filename}</p><label>Design name<input value={draft.name} maxLength={80} onChange={e=>setDraft(old=>({...old,name:e.target.value}))}/></label>
          <p className="muted">Click a body in the view or use Highlight. Assign each body below.</p><div className="cad-bodies">{source.preview.bodies.map((b,i)=><div className="cad-body" key={b.id}>
            <label title={b.name}>Body {i+1}<select aria-label={`Body ${i+1} role`} disabled={!!busy} value={draft.geometry.fluid_bodies.includes(b.id)?'fluid':draft.geometry.solid_bodies.includes(b.id)?'solid':'ignore'} onChange={e=>role(b.id,e.target.value)}><option value="ignore">Ignore</option><option value="fluid">Fluid volume</option><option value="solid">Solid material</option></select></label>
            <small>{fmt(b.volume_mm3*draft.geometry.scale**3)} mm³</small><button className="secondary" disabled={!!built} onClick={()=>setSelection(source.preview.faces.filter(f=>f.body_ids.includes(b.id)).map(f=>f.id))}>Highlight</button>
          </div>)}</div>
          <NumberInput label="Geometry scale multiplier" value={draft.geometry.scale} min={.000001} onChange={v=>changeGeometry({...draft.geometry,scale:v})}/>
          <p className="muted">STEP/IGES file units are converted to mm. BREP assumes mm. Check the displayed dimensions; use scale 1000 for a BREP drawn in metres.</p>
          <button className="full" disabled={!!busy||!draft.geometry.fluid_bodies.length} onClick={prepare}>Prepare selected bodies</button>
          <div className="builder-actions"><button className="secondary" onClick={saveSetup}>Save setup</button><a href={`/api/cad/sources/${draft.geometry.source_id}/file`}>Original CAD</a></div>
        </>}
      </section>
      {draft&&catalog&&<><section><h2>2 · Fluid & inlet</h2><label>Fluid<select value={draft.physics.fluid} onChange={e=>updatePhysics(old=>chooseFluid(old,catalog,e.target.value))}>{Object.entries(catalog.fluids).map(([id,f])=><option key={id} value={id}>{f.label}</option>)}</select></label><button className="secondary" onClick={()=>setEditor('fluid')}>Edit fluid properties</button>
        {inletArea>0?<InletControls form={{...draft.physics,inlet_area_m2:inletArea}} catalog={catalog} setForm={updatePhysics} flow={operating?.flow}/>:<p className="muted">Assign an inlet face to enable flow-rate conversion.</p>}
        <NumberInput label="Inlet temperature" value={draft.physics.inlet_temperature_c} unit="°C" onChange={v=>updatePhysics({inlet_temperature_c:v})}/>
        <label>Flow model<select value={draft.physics.flow_model} onChange={e=>updatePhysics({flow_model:e.target.value})}><option value="auto">Automatic from inlet Reynolds number</option><option value="laminar">Laminar</option><option value="kOmegaSST">k–ω SST</option></select></label>
      </section><section><h2>Solid material</h2><label>Material<select value={draft.physics.material} onChange={e=>updatePhysics(old=>chooseMaterial(old,catalog,e.target.value))}>{Object.entries(catalog.materials).map(([id,m])=><option key={id} value={id}>{m.label}</option>)}</select></label><button className="secondary" onClick={()=>setEditor('solid')}>Edit material properties</button><p className="muted">The selected solid bodies share this material and have perfect thermal contact where they touch.</p></section>
      <section><h2>Mesh & solver</h2><NumberInput label="Target cell size" value={draft.mesh_size_mm} min={.05} unit="mm" onChange={v=>setDraft(old=>({...old,mesh_size_mm:v}))}/><NumberInput label="Flow iterations" value={draft.physics.max_iterations} min={100} step={100} onChange={v=>updatePhysics({max_iterations:v})}/><NumberInput label="Thermal iterations" value={draft.physics.thermal_iterations} min={100} step={50} onChange={v=>updatePhysics({thermal_iterations:v})}/><p className="muted">No fixed cell-count or solver elapsed-time cap. Runs share the local queue. Check mesh refinement and conservation before relying on a prediction.</p></section></>}
    </aside><div className="workspace" tabIndex={0} role="region" aria-label="CAD geometry and results">
      {busy&&<p className="notice" role="status">{busy}</p>}{error&&<p className="error" role="alert">{error}</p>}{notice&&<p className="notice">{notice}</p>}{operatingError&&<p className="notice warn">{operatingError}</p>}
      {health&&Object.values(health).filter(h=>!h.available).map(h=><p className="error" key={h.error}>{h.error}</p>)}{operating?.run_errors.map(e=><p className="notice warn" key={e}>{e}</p>)}
      <section className="panel"><h2>{built?'Prepared CAD · assign faces':'Imported CAD · identify bodies'}</h2>
        {source?<AssemblyViewport data={built??source.preview} selected={selection} groups={built?groups:[]} onPick={pick}/>:<div className="build-placeholder"><b>Import your fluid and solid geometry</b><p>STEP / STP · IGES / IGS · BREP</p><button disabled={!!busy||!catalog} onClick={()=>uploadInput.current.click()}>Choose CAD file</button></div>}
        {source&&<p className="muted">Bounding dimensions: {(built??source.preview).bounds_mm[1].map((v,i)=>fmt(v-(built??source.preview).bounds_mm[0][i])).join(' × ')} mm</p>}
      </section>
      {built&&draft&&<section className="panel"><h2>3 · Inlet, outlet, heating & cooling</h2><p className="muted">Click faces or tick the list. Unassigned fluid faces are no-slip walls; unassigned exterior solid faces are insulated. Fluid–solid contact faces couple automatically.</p>
        <div className="boundary-actions"><label>Assign selection as<select value={kind} onChange={e=>setKind(e.target.value)}><option value="inlet">Inlet · fluid face</option><option value="outlet">Outlet · 0 Pa gauge</option><option value="heat">Heating · total power</option><option value="convection">Cooling · convection to ambient</option></select></label><button disabled={!selection.length||!!busy} onClick={assign}>Assign {selection.length} selected</button><button className="secondary" onClick={()=>setSelection([])}>Clear selection</button></div>
        <details open><summary>Boundary faces ({faces.length})</summary><div className="face-list">{faces.map(f=><label className="check-label" key={f.id}><input type="checkbox" checked={selection.includes(f.id)} onChange={()=>pick(f.id)}/><span>{f.label} · {f.region} · {fmt(f.area_mm2)} mm²{assigned[f.id]?` · ${assigned[f.id]}`:''}</span></label>)}</div></details>
        <div className="cad-ports">{['inlet','outlet'].map(port=><div key={port}><b>{port==='inlet'?'Inlet':'Outlet'}</b><span>{draft[`${port}_faces`].length} faces</span><button className="secondary" onClick={()=>setSelection(draft[`${port}_faces`])}>Highlight</button><button className="danger" onClick={()=>{setOperating(null);setDraft(old=>({...old,[`${port}_faces`]:[]}))}}>Clear</button></div>)}</div>
        {operating&&<p className="notice">Inlet area {fmt(operating.metrics.inlet_area_m2*1e6)} mm² · hydraulic diameter {fmt(operating.metrics.hydraulic_diameter_mm)} mm · inlet Re {fmt(operating.flow.reynolds_number)}</p>}
        <div className="boundary-groups">{draft.boundaries.map((g,i)=><div className={`boundary-card ${g.kind}`} key={g.id}><label>Boundary name<input value={g.name} maxLength={60} onChange={e=>editGroup(i,'name',e.target.value)}/></label><p className="muted">{g.faces.length} selected faces</p>
          {g.kind==='heat'?<NumberInput label="Total group power" value={g.power_w} unit="W" min={0} onChange={v=>editGroup(i,'power_w',v)}/>:<><NumberInput label="Heat-transfer coefficient" value={g.h_w_m2_k} unit="W/m²·K" min={.0001} onChange={v=>editGroup(i,'h_w_m2_k',v)}/><NumberInput label="Ambient temperature" value={g.ambient_c} unit="°C" onChange={v=>editGroup(i,'ambient_c',v)}/></>}
          <p className="muted">{g.kind==='heat'?'Total power is distributed by face area.':'Convection removes heat when the wall is hotter than ambient; it warms a colder wall.'}</p><div className="builder-actions"><button className="secondary" onClick={()=>setSelection(g.faces)}>Highlight</button><button className="danger" onClick={()=>setDraft(old=>({...old,boundaries:old.boundaries.filter((_,n)=>n!==i)}))}>Remove boundary</button></div>
        </div>)}</div>
      </section>}
      <section className="panel"><h2>Saved CAD runs</h2><RunHistory jobs={jobs} selectedId={selectedJob} onSelect={id=>{setSelectedJob(id);setJob(null)}} onDeleted={deleted} onDeletingChange={setDeleting}>{j=><><span>{j.inputs.name} · {j.inputs.mesh_size_mm} mm</span><span className="badge">{j.status.replaceAll('_',' ')}</span></>}</RunHistory>
        {job&&<><div className="run-status"><b>{job.status.replaceAll('_',' ')}</b><span>Flow {job.progress?.iteration??0} · thermal {job.thermal_progress?.iteration??0}</span>{active.includes(job.status)?<button className="danger" onClick={()=>api(`/api/jobs/${job.id}/cancel`,{}).then(setJob).catch(e=>setError(e.message))}>Cancel run</button>:<button className="secondary" disabled={!!busy} onClick={()=>restore(structuredClone(job.inputs)).catch(e=>setError(e.message))}>Load this CAD setup</button>}</div>{job.error&&<p className="error">{job.error}</p>}<details><summary>Run log</summary><pre>{job.log||'Queued…'}</pre></details><p className="muted">Saved results belong to “{job.inputs.name}”. Editing the setup above does not change them.</p></>}
      </section>{job?.results&&<Results job={job}/>}
      <footer>Closed CAD bodies required. A metal part alone does not define the fluid volume. No automatic cavity extraction, native CAD feature editing, or STL/OBJ volume import. Constant properties and frozen-flow coupled heat transfer.</footer>
    </div></main>
    {editor&&draft&&catalog&&<PropertyEditor title={editor==='solid'?'Edit solid material':'Edit fluid properties'} properties={editor==='solid'?solidProperties:fluidProperties} form={draft.physics} preset={editor==='solid'?catalog.materials[draft.physics.material]:catalog.fluids[draft.physics.fluid]} solid={editor==='solid'} onClose={()=>setEditor(null)} onApply={values=>{updatePhysics(values);setEditor(null)}}/>}
  </div>
}
