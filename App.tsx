import React, { useState } from 'react'
import { search, getInteraction, checkStack } from './api'

export default function App(){
  const [q,setQ]=useState('')
  const [results,setResults]=useState<any[]>([])
  const [pairData,setPairData]=useState<any|null>(null)
  const [stackText,setStackText]=useState('creatine, caffeine, magnesium')
  const [stack,setStack]=useState<any|null>(null)

  const doSearch=async()=>{ const data=await search(q); setResults(data.compounds||[]) }
  const openPair=async()=>{
    const a=(document.getElementById('a') as HTMLInputElement).value.trim()
    const b=(document.getElementById('b') as HTMLInputElement).value.trim()
    if(!a||!b) return
    const data=await getInteraction(a,b); setPairData(data)
  }
  const doStack=async()=>{
    const items=stackText.split(',').map(s=>s.trim()).filter(Boolean)
    const data=await checkStack(items); setStack(data)
  }

  return (<div style={{fontFamily:'Inter, system-ui, sans-serif', margin:'24px', maxWidth:960}}>
    <h1>Supplement Interaction Tracker</h1>

    <section style={{marginTop:16,padding:16,border:'1px solid #ccc',borderRadius:12}}>
      <h2>Search</h2>
      <input value={q} onChange={e=>setQ(e.target.value)} placeholder='search compound' style={{padding:8,width:'70%'}} />
      <button onClick={doSearch} style={{marginLeft:8,padding:'8px 12px'}}>Search</button>
      <div style={{display:'flex',gap:8,flexWrap:'wrap',marginTop:12}}>
        {results.map(r=>(<span key={r.id} style={{padding:'6px 10px',border:'1px solid #ddd',borderRadius:16}}>{r.name}</span>))}
      </div>
    </section>

    <section style={{marginTop:16,padding:16,border:'1px solid #ccc',borderRadius:12}}>
      <h2>Pair Checker</h2>
      <div style={{display:'flex',gap:8,alignItems:'center'}}>
        <input id='a' placeholder='compound A' style={{padding:8}}/>
        <span>×</span>
        <input id='b' placeholder='compound B' style={{padding:8}}/>
        <button onClick={openPair}>Check</button>
      </div>
      {pairData && (<div style={{marginTop:12,padding:12,border:'1px solid #eee',borderRadius:12}}>
        <h3>{pairData.pair.a} × {pairData.pair.b}</h3>
        <p><b>Severity:</b> {pairData.interaction.severity} | <b>Evidence:</b> {pairData.interaction.evidence_grade}</p>
        <p><b>Score:</b> {pairData.interaction.score} | <b>Bucket:</b> {pairData.interaction.bucket}</p>
        <p><b>Action:</b> {pairData.interaction.action_resolved}</p>
        <p><b>Why:</b> {pairData.interaction.effect_summary}</p>
        <details><summary>Sources</summary><ul>
          {(pairData.interaction.sources||[]).map((s:any)=>(<li key={s.id}>{s.citation} {s.identifier?`(${s.identifier})`:''} {s.date?`— ${s.date}`:''}</li>))}
        </ul></details>
      </div>)}
    </section>

    <section style={{marginTop:16,padding:16,border:'1px solid #ccc',borderRadius:12}}>
      <h2>Stack Checker</h2>
      <textarea value={stackText} onChange={e=>setStackText(e.target.value)} rows={3} style={{width:'100%',padding:8}} />
      <div style={{marginTop:8}}><button onClick={doStack}>Compute Matrix</button></div>
      {stack && (<div style={{marginTop:12}}>
        <table style={{borderCollapse:'collapse'}}>
          <thead><tr><th></th>{stack.items.map((it:string,i:number)=>(<th key={i} style={{border:'1px solid #ddd',padding:'4px 8px'}}>{it}</th>))}</tr></thead>
          <tbody>
            {stack.items.map((row:string,i:number)=>(<tr key={i}>
              <th style={{border:'1px solid #ddd',padding:'4px 8px',textAlign:'left'}}>{row}</th>
              {stack.matrix[i].map((cell:number|null,j:number)=>(<td key={j} style={{border:'1px solid #ddd',padding:'4px 8px',textAlign:'center'}}>{cell===null?'—':cell.toFixed(2)}</td>))}
            </tr>))}
          </tbody>
        </table>
      </div>)}
    </section>
  </div>)
}