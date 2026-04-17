import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPapers, analyzePaper } from '../api/client'
import { useStore } from '../store/appStore'

const AGENTS = [
  { name: 'The Reasoner', desc: 'Domain · novelty · contributions', model: 'Llama-3.3-70b' },
  { name: 'The Thinker',  desc: '5-dimension production scoring',   model: 'DeepSeek-R1'   },
  { name: 'The Scribe',   desc: 'Brief · stack fit · action',       model: 'Llama-3.3-70b' },
  { name: 'The Sentinel', desc: 'GRPO hype detection',              model: 'Local GRPO'    },
]
const AGENT_TIMES      = [0, 12000, 24000, 36000]
const AGENT_DONE_TIMES = [11000, 23000, 35000, 47000]

const actionColor = (a) => {
  if (!a) return 'var(--text3)'
  const l = a.toLowerCase()
  if (l.includes('adopt'))      return 'var(--sg-b)'
  if (l.includes('experiment')) return 'var(--amber)'
  return 'var(--text3)'
}

export default function AnalyzeOverlay({ open, onClose }) {
  const navigate = useNavigate()
  const { setActivePaper } = useStore()
  const [input,  setInput]  = useState('')
  const [running, setRunning] = useState(false)
  const [agents,  setAgents]  = useState(AGENTS.map(() => 'idle'))
  const [result,  setResult]  = useState(null)
  const [error,   setError]   = useState('')
  const timers = []

  // Reset when closed
  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setInput(''); setRunning(false); setResult(null); setError('')
        setAgents(AGENTS.map(() => 'idle'))
      }, 300)
    }
  }, [open])

  const extractId = (v) => { const m = v.match(/(\d{4}\.\d{4,5})/); return m ? m[1] : null }

  const run = async () => {
    if (!input.trim()) return
    const id = extractId(input)
    if (!id) { setError('Enter a valid ArXiv URL or paper ID (e.g. 2407.08608)'); return }
    try {
      const papers = await getPapers(100)
      const paper = papers.find(p => p.id === id || p.id.startsWith(id))
      if (!paper) { setError(`Paper ${id} not in DB — run the scraper first`); return }
      setError(''); setResult(null); setRunning(true)
      setAgents(['idle','idle','idle','idle'])
      AGENT_TIMES.forEach((t, i) =>
        timers.push(setTimeout(() => setAgents(prev => prev.map((s, j) => j === i ? 'running' : s)), t))
      )
      AGENT_DONE_TIMES.forEach((t, i) =>
        timers.push(setTimeout(() => setAgents(prev => prev.map((s, j) => j === i ? 'done'    : s)), t))
      )
      const res = await analyzePaper(paper.id)
      setAgents(['done','done','done','done'])
      setResult({ ...res, ...paper })
      setRunning(false)
      setActivePaper({ ...paper, ...res })
    } catch (e) {
      setError(e.response?.data?.detail || 'Analysis failed — check server')
      setRunning(false)
      setAgents(['idle','idle','idle','idle'])
      timers.forEach(clearTimeout)
    }
  }

  const goRead = () => { onClose(); navigate('/app/read') }

  return (
    <>
      <div className={`overlay-backdrop${open ? ' open' : ''}`} onClick={onClose} />
      <div className={`overlay-panel${open ? ' open' : ''}`}>
        <div className="overlay-handle" />
        <div className="overlay-header">
          <div>
            <div className="overlay-title">Analyze a Paper</div>
            <div style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)',marginTop:2,letterSpacing:'.12em',textTransform:'uppercase'}}>
              4-Agent Pipeline · Reasoner → Thinker → Scribe → Sentinel
            </div>
          </div>
          <button className="overlay-close" onClick={onClose}>
            <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" fill="none" strokeWidth="2"/></svg>
          </button>
        </div>

        <div className="overlay-body" style={{padding:'20px 20px 28px'}}>
          {/* Input */}
          <div style={{marginBottom:20}}>
            <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',letterSpacing:'.1em',textTransform:'uppercase',marginBottom:7}}>
              ArXiv URL or Paper ID
            </div>
            <div style={{display:'flex',gap:8}}>
              <input
                className="input"
                placeholder="https://arxiv.org/abs/2407.08608  or  2407.08608"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && !running && run()}
              />
              <button className="btn btn-primary" onClick={run} disabled={running} style={{flexShrink:0}}>
                {running
                  ? <><div className="spinner" style={{width:12,height:12,marginRight:4}}/>Running</>
                  : <><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width:11,height:11}}><polygon points="5 3 19 12 5 21 5 3"/></svg>Run</>
                }
              </button>
            </div>
            {error && <div style={{fontSize:11.5,color:'var(--red)',marginTop:7}}>{error}</div>}
          </div>

          {/* Agent steps */}
          <div style={{marginBottom: result ? 20 : 0}}>
            {AGENTS.map((agent, i) => (
              <div key={i} className="agent-row">
                <div className={`agent-num ${agents[i]}`}>{i + 1}</div>
                <div style={{flex:1}}>
                  <div className="agent-name">{agent.name}</div>
                  <div className="agent-desc">{agent.desc}</div>
                </div>
                <div style={{textAlign:'right',flexShrink:0}}>
                  <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',marginBottom:2}}>{agent.model}</div>
                  <span className={`agent-status${agents[i] !== 'idle' ? ' '+agents[i] : ''}`}>
                    {agents[i] === 'idle' ? 'Waiting' : agents[i] === 'running' ? 'Running...' : '✓ Done'}
                  </span>
                </div>
              </div>
            ))}
          </div>

          {/* Result */}
          {result && (
            <div className="card" style={{padding:18,marginTop:4}}>
              {/* Header */}
              <div style={{display:'flex',gap:14,marginBottom:14}}>
                <div style={{flex:1}}>
                  <div style={{fontSize:14,fontWeight:600,color:'var(--text)',lineHeight:1.4,marginBottom:4}}>{result.title}</div>
                  <div style={{fontSize:11.5,color:'var(--text3)'}}>{result.domain} · {result.novelty}</div>
                </div>
                <div style={{textAlign:'center',flexShrink:0}}>
                  <div style={{fontFamily:'var(--serif)',fontSize:38,fontWeight:600,color:actionColor(result.action),lineHeight:1}}>
                    {result.overall_score?.toFixed(1)}
                  </div>
                  <span className={`badge badge-${result.action?.toLowerCase().includes('adopt')?'adopt':result.action?.toLowerCase().includes('experiment')?'experiment':'watch'}`} style={{marginTop:4}}>
                    {result.action}
                  </span>
                </div>
              </div>

              {/* 5 dimension scores */}
              <div style={{display:'grid',gridTemplateColumns:'repeat(5,1fr)',gap:6,marginBottom:14}}>
                {[['Repro', result.reproducibility],['Compute', result.compute_cost],['Latency', result.latency],['Adoption', result.adoption],['Hype', result.hype_score]].map(([label,val]) => (
                  <div key={label} style={{background:'var(--surface2)',border:'1px solid var(--border)',borderRadius:'var(--radius)',padding:'10px 8px',textAlign:'center'}}>
                    <div style={{fontFamily:'var(--serif)',fontSize:20,color:label==='Hype'?(val<=4?'var(--sg-b)':val>=7?'var(--red)':'var(--text)'):'var(--text)',marginBottom:2}}>
                      {val?.toFixed(1) ?? '—'}
                    </div>
                    <div style={{fontFamily:'var(--mono)',fontSize:7.5,color:'var(--text4)',textTransform:'uppercase',letterSpacing:'.07em'}}>{label}</div>
                  </div>
                ))}
              </div>

              {result.hype_score <= 4 && result.overall_score >= 7 && (
                <div style={{background:'var(--gold-p)',border:'1px solid var(--gold-bd)',borderRadius:'var(--radius)',padding:'8px 12px',marginBottom:12,fontSize:12,color:'var(--gold-l)'}}>
                  💎 The Sentinel flagged this as a <strong>hidden gem</strong> — high production value, low hype
                </div>
              )}

              <div style={{marginBottom:10}}>
                <div style={{fontFamily:'var(--mono)',fontSize:8,color:'var(--text4)',letterSpacing:'.1em',textTransform:'uppercase',marginBottom:5}}>Summary</div>
                <div style={{fontSize:12.5,color:'var(--text2)',lineHeight:1.75}}>{result.summary}</div>
              </div>

              <button className="btn btn-primary" onClick={goRead} style={{width:'100%',justifyContent:'center',marginTop:4}}>
                📖 Open in Read &amp; Chat →
              </button>
            </div>
          )}
        </div>
      </div>
    </>
  )
}