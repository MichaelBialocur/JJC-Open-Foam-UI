import { useEffect, useRef, useState } from 'react'

export default function PropertyEditor({ title, properties, form, preset, solid, onApply, onClose }) {
  const [draft,setDraft]=useState(()=>Object.fromEntries(properties.map(([key])=>[key,form[key]??preset?.values[key]??''])))
  const dialog=useRef(null)
  useEffect(()=>{
    const previous=document.activeElement
    dialog.current.querySelector('input')?.focus()
    return()=>previous?.focus()
  },[])
  function keyDown(event){
    if(event.key==='Escape'){event.preventDefault();onClose()}
    if(event.key==='Tab'){
      const focusable=[...dialog.current.querySelectorAll('input,button,a[href]')],first=focusable[0],last=focusable.at(-1)
      if(event.shiftKey&&document.activeElement===first){event.preventDefault();last.focus()}
      else if(!event.shiftKey&&document.activeElement===last){event.preventDefault();first.focus()}
    }
  }
  function apply(event){
    event.preventDefault()
    onApply(Object.fromEntries(Object.entries(draft).map(([key,value])=>[key,Number(value)])))
  }
  return <div className="editor-backdrop"><div ref={dialog} className="property-editor" role="dialog" aria-modal="true" aria-labelledby="property-editor-title" onKeyDown={keyDown}>
    <h2 id="property-editor-title">{title}</h2>
    <p className="muted">{preset?`${preset.label} · preset values at ${preset.temperature_c} °C${preset.pressure_pa?' and 1 atm':''}.`:'Custom / benchmark properties.'} Values stay constant during a run.</p>
    <form onSubmit={apply}>
      <div className="property-grid">{properties.map(([key,label,unit,max])=><label key={key}>{label}<div><input name={key} type="number" required min="1e-15" max={max} step="any" value={draft[key]} onChange={e=>setDraft(old=>({...old,[key]:e.target.value}))}/><span>{unit}</span></div></label>)}</div>
      {solid&&<p className="muted">Steady wall conduction depends on thermal conductivity. Density and heat capacity define the material but do not add transient heating.</p>}
      {preset&&<details><summary>Preset source and assumptions</summary><p className="muted"><a href={preset.source.url} target="_blank" rel="noreferrer">{preset.source.label}</a>. {preset.note}</p></details>}
      <div className="editor-actions">{preset&&<button type="button" className="secondary" onClick={()=>setDraft({...preset.values})}>Reset to preset</button>}<button type="button" className="secondary" onClick={onClose}>Cancel</button><button type="submit">Apply properties</button></div>
    </form>
  </div></div>
}
