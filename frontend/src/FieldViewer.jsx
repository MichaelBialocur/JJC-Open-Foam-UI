import { useEffect, useMemo, useRef, useState } from 'react'
import Viewport from './Viewport'
import Chart from './Chart'
import { niceScale, tickLabel } from './axes'
import { fieldColor, locateCell } from './fieldGeometry'

function FieldMap({ data, field, range, station, onPick }) {
  const canvas = useRef(null)
  useEffect(()=>{
    const element=canvas.current,ctx=element.getContext('2d')
    if(!ctx) return
    const width=1000,height=220
    element.width=width;element.height=height
    const length=data.x_edges_m.at(-1),radius=data.r_edges_m.at(-1)
    for(let i=0;i<data.nx;i++) for(let j=0;j<data.nr;j++){
      ctx.fillStyle=`rgb(${fieldColor(data.fields[field].values[i*data.nr+j],range.min,range.max).join(',')})`
      const x0=data.x_edges_m[i]/length*width,x1=data.x_edges_m[i+1]/length*width
      const r0=data.r_edges_m[j]/radius*height/2,r1=data.r_edges_m[j+1]/radius*height/2
      ctx.fillRect(x0,height/2-r1,Math.max(.5,x1-x0),Math.max(.5,r1-r0))
      ctx.fillRect(x0,height/2+r0,Math.max(.5,x1-x0),Math.max(.5,r1-r0))
    }
    const x=data.cell_x_m[station*data.nr]/length*width
    ctx.strokeStyle='#fff';ctx.lineWidth=2;ctx.setLineDash([6,4]);ctx.beginPath();ctx.moveTo(x,0);ctx.lineTo(x,height);ctx.stroke()
    ctx.setLineDash([2,6]);ctx.strokeStyle='#ffffff88';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(0,height/2);ctx.lineTo(width,height/2);ctx.stroke()
  },[data,field,range,station])
  function pick(event){
    const rect=canvas.current.getBoundingClientRect(),length=data.x_edges_m.at(-1),radius=data.r_edges_m.at(-1)
    const x=(event.clientX-rect.left)/rect.width*length,r=Math.abs((event.clientY-rect.top)/rect.height*2-1)*radius
    const i=locateCell(data.x_edges_m,x),j=locateCell(data.r_edges_m,r)
    if(i!==null&&j!==null)onPick(i*data.nr+j)
  }
  return <div className="field-map"><canvas ref={canvas} onPointerDown={pick} role="img" aria-label={`${data.fields[field].label}: full axial section. Click a cell to inspect its computed value.`}/>
    <div className="map-axis"><span>Inlet · x = 0 m</span><span>Centreline · r = 0</span><span>Outlet · x = {tickLabel(data.x_edges_m.at(-1))} m</span></div>
    <p className="muted">Axial section · diameter expanded to fill this panel · dashed line marks the selected station. Click to probe a cell.</p></div>
}

export default function FieldViewer({ jobId, spec }) {
  const [data,setData]=useState(null),[error,setError]=useState('')
  const [field,setField]=useState('speed'),[mode,setMode]=useState('cutaway'),[fraction,setFraction]=useState(.8)
  const [wire,setWire]=useState(false),[picked,setPicked]=useState(null)
  useEffect(()=>{
    const controller=new AbortController()
    fetch(`/api/jobs/${jobId}/fields.json`,{signal:controller.signal}).then(async response=>{
      const body=await response.json();if(!response.ok)throw new Error(body.detail || 'Field data unavailable');return body
    }).then(setData).catch(e=>{if(e.name!=='AbortError')setError(e.message)})
    return()=>controller.abort()
  },[jobId])
  const range=useMemo(()=>data?niceScale(data.fields[field].min,data.fields[field].max,{includeZero:field!=='temperature',intervals:4}):null,[data,field])
  if(error)return <section className="panel"><h2>Computed field viewer</h2><p className="notice warn">{error}</p></section>
  if(!data)return <section className="panel"><h2>Computed field viewer</h2><p className="muted">Loading saved mesh and cell fields…</p></section>
  const station=Math.round(fraction*(data.nx-1)), item=data.fields[field]
  const selected=picked!==null&&picked<data.nx*data.nr?picked:station*data.nr
  const profile=Array.from({length:data.nr},(_,j)=>({x:data.cell_r_m[station*data.nr+j]/data.r_edges_m.at(-1),y:item.values[station*data.nr+j]}))
  return <section className="panel field-viewer">
    <div className="panel-heading"><h2>Computed field viewer</h2><span className="badge">{(data.nx*data.nr).toLocaleString()} computed cells</span></div>
    <div className="field-toolbar">
      <label>Colour by<select value={field} onChange={e=>setField(e.target.value)}>{Object.entries(data.fields).map(([key,f])=><option key={key} value={key}>{f.label} ({f.unit})</option>)}</select></label>
      <label>3D view<select value={mode} onChange={e=>setMode(e.target.value)}><option value="cutaway">Cutaway</option><option value="cross">Cross-section</option><option value="axial">Axial section</option></select></label>
      <label className="check-label"><input type="checkbox" checked={wire} onChange={e=>setWire(e.target.checked)}/> Cell outlines</label>
    </div>
    {(!data.flow_converged || data.thermal_converged===false)&&<p className="notice warn">These fields have not passed all convergence checks. Inspect them as an unfinished solution.</p>}
    <Viewport spec={spec} data={data} field={field} mode={mode} station={station} range={range} wire={wire} onPick={setPicked}/>
    <div className="colour-scale"><span>{item.label} ({item.unit})</span><div className="colour-gradient"/><div className="colour-ticks">{range.ticks.map(value=><span key={value}>{tickLabel(value)}</span>)}</div></div>
    <label className="slice-control">Section position · x = {Number(data.cell_x_m[station*data.nr].toPrecision(5))} m · station {station+1}/{data.nx}
      <input type="range" min="0" max="1" step={1/(data.nx-1)} value={fraction} onChange={e=>setFraction(Number(e.target.value))}/></label>
    <FieldMap data={data} field={field} range={range} station={station} onPick={setPicked}/>
    <div className="probe" aria-live="polite"><b>Cell probe</b><span>x {Number(data.cell_x_m[selected].toPrecision(5))} m</span><span>r {Number((data.cell_r_m[selected]*1000).toPrecision(5))} mm</span>
      {Object.entries(data.fields).map(([key,f])=><span key={key}>{f.label}: <b>{Number(f.values[selected].toPrecision(6))} {f.unit}</b></span>)}</div>
    <details><summary>Plot the selected cross-section</summary><Chart title={`${item.label} at x = ${Number(data.cell_x_m[station*data.nr].toPrecision(4))} m`} xLabel="r / R · centre → wall" yLabel={`${item.label} (${item.unit})`} xDomain={[0,1]} zeroBaseline={field!=='temperature'} series={[{name:'Computed cell values',color:'#59b9fa',points:profile}]}/></details>
    <p className="muted">{data.representation}. Colours show cell values without smoothing. Section positions snap to computed cell centres; the solid wall is an uncoloured geometry outline.</p>
    <div className="exports"><a href={`/api/jobs/${jobId}/section.vtk`}>Export section to ParaView (.vtk)</a><a href={`/api/jobs/${jobId}/case.zip`}>Download full OpenFOAM case</a></div>
  </section>
}
