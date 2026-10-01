import {useState} from 'react'
import App from './App'
import AssemblyApp from './AssemblyApp'
export default function Workbench(){
  const [workspace,setWorkspace]=useState(()=>localStorage.getItem('pipe-cfd-workspace')||'pipe')
  return <div className="workbench"><nav className="workspace-tabs" role="tablist" aria-label="Workspace">{[['pipe','Straight-pipe benchmark'],['assembly','Geometry builder']].map(([id,label])=><button role="tab" aria-selected={workspace===id} key={id} onClick={()=>{setWorkspace(id);localStorage.setItem('pipe-cfd-workspace',id)}}>{label}</button>)}</nav>{workspace==='assembly'?<AssemblyApp/>:<App/>}</div>
}
