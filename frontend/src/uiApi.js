export const fmt=(v,n=4)=>Number.isFinite(v)?Number(v.toPrecision(n)).toLocaleString('en',{maximumSignificantDigits:n}):'—'
export async function api(path,body,signal){
  const response=await fetch(path,body===undefined?{signal}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal})
  const data=await response.json()
  if(!response.ok)throw Object.assign(new Error(typeof data.detail==='string'?data.detail:data.detail?.map(d=>`${d.loc?.slice(1).join('.')}: ${d.msg}`).join('; ')||`Server error ${response.status}`),{status:response.status})
  return data
}
