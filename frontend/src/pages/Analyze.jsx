import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPapers, ingestPaper, analyzeAsync } from '../api/client'
import { useStore } from '../store/appStore'

const AGENTS = [
  { name: 'The Reasoner', desc: 'Domain · novelty · contributions', model: 'Llama-3.3-70b' },
  { name: 'The Thinker',  desc: '5-dimension production scoring',   model: 'DeepSeek-R1'   },
  { name: 'The Scribe',   desc: 'Brief · stack fit · action',       model: 'Llama-3.3-70b' },
  { name: 'The Sentinel', desc: 'GRPO hype detection',              model: 'Local GRPO'    },
]

export default function AnalyzeOverlay({ open, onClose }) {
  const navigate = useNavigate()
  const { addJob, addNotification } = useStore()
  const [input,    setInput]    = useState('')
  const [phase,    setPhase]    = useState('idle') // idle | ingesting | submitting | queued | error
  const [error,    setError]    = useState('')
  const [infoMsg,  setInfoMsg]  = useState('')

  useEffect(() => {
    if (!open) {
      setTimeout(() => {
        setInput(''); setPhase('idle'); setError(''); setInfoMsg('')
      }, 300)
    }
  }, [open])

  const extractId = (v) => {
    const m = v.match(/(\d{4}\.\d{4,5})/)
    return m ? m[1] : null
  }

  const run = async () => {
    if (!input.trim() || phase !== 'idle') return
    const id = extractId(input)
    if (!id) {
      setError('Enter a valid ArXiv URL or paper ID (e.g. 2407.08608)')
      return
    }

    setError('')
    let paperId = id
    let paperTitle = id

    // Step 1 — check DB, auto-ingest if missing
    try {
      const papers = await getPapers(500)
      const existing = papers.find(p => p.id === id || p.id.startsWith(id))

      if (!existing) {
        setPhase('ingesting')
        setInfoMsg(`Paper not in DB — fetching from ArXiv...`)
        const ingested = await ingestPaper(id)
        paperId    = ingested.paper_id
        paperTitle = ingested.title
        setInfoMsg(`Ingested: ${paperTitle.substring(0, 50)}...`)
      } else {
        paperId    = existing.id
        paperTitle = existing.title
      }
    } catch (e) {
      setPhase('error')
      setError(e.response?.data?.detail || 'Failed to fetch paper from ArXiv')
      return
    }

    // Step 2 — submit async analysis job
    try {
      setPhase('submitting')
      setInfoMsg('Queuing analysis pipeline...')
      const job = await analyzeAsync(paperId)

      // Register job in store — persists across navigation
      addJob({
        job_id:   job.job_id,
        paper_id: paperId,
        title:    paperTitle,
        status:   'pending',
      })

      addNotification({
        type:    'job_started',
        title:   paperTitle,
        paper_id: paperId,
        job_id:  job.job_id,
        message: 'Analysis queued — we\'ll notify you when done',
      })

      setPhase('queued')
      setInfoMsg(paperTitle)

    } catch (e) {
      setPhase('error')
      setError(e.response?.data?.detail || 'Failed to queue analysis')
    }
  }

  const handleDone = () => {
    onClose()
    navigate('/app/jobs')
  }

  return (
    <>
      <div className={`overlay-backdrop${open ? ' open' : ''}`} onClick={phase === 'queued' ? undefined : onClose} />
      <div className={`overlay-panel${open ? ' open' : ''}`}>
        <div className="overlay-handle" />
        <div className="overlay-header">
          <div>
            <div className="overlay-title">Analyze a Paper</div>
            <div style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)',marginTop:2,letterSpacing:'.12em',textTransform:'uppercase'}}>
              4-Agent Pipeline · Async · Runs in Background
            </div>
          </div>
          <button className="overlay-close" onClick={onClose}>
            <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" fill="none" strokeWidth="2"/></svg>
          </button>
        </div>

        <div className="overlay-body" style={{padding:'20px 20px 28px'}}>

          {/* Input */}
          {phase === 'idle' || phase === 'error' ? (
            <div style={{marginBottom:20}}>
              <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',letterSpacing:'.1em',textTransform:'uppercase',marginBottom:7}}>
                ArXiv URL or Paper ID
              </div>
              <div style={{display:'flex',gap:8}}>
                <input
                  className="input"
                  placeholder="https://arxiv.org/abs/2407.08608  or  2407.08608"
                  value={input}
                  onChange={e => { setInput(e.target.value); setError('') }}
                  onKeyDown={e => e.key === 'Enter' && run()}
                  autoFocus
                />
                <button className="btn btn-primary" onClick={run} style={{flexShrink:0}}>
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{width:11,height:11}}>
                    <polygon points="5 3 19 12 5 21 5 3"/>
                  </svg>
                  Run
                </button>
              </div>
              {error && <div style={{fontSize:11.5,color:'var(--red)',marginTop:7}}>{error}</div>}
              <div style={{fontSize:11,color:'var(--text4)',marginTop:8,lineHeight:1.6}}>
                Papers not in DB are automatically fetched from ArXiv.
              </div>
            </div>
          ) : null}

          {/* Progress states */}
          {(phase === 'ingesting' || phase === 'submitting') && (
            <div style={{padding:'28px 0',textAlign:'center'}}>
              <div className="spinner" style={{width:24,height:24,margin:'0 auto 16px'}}/>
              <div style={{fontSize:13,color:'var(--text2)',marginBottom:6}}>
                {phase === 'ingesting' ? 'Fetching from ArXiv...' : 'Queuing pipeline...'}
              </div>
              <div style={{fontSize:11,color:'var(--text4)',fontFamily:'var(--mono)'}}>{infoMsg}</div>
            </div>
          )}

          {/* Queued success state */}
          {phase === 'queued' && (
            <div style={{padding:'8px 0'}}>
              <div style={{
                background:'var(--sg-p)',border:'1px solid var(--sg-bd)',
                borderRadius:'var(--radius-lg)',padding:'16px',marginBottom:16
              }}>
                <div style={{display:'flex',alignItems:'center',gap:10,marginBottom:10}}>
                  <div style={{
                    width:32,height:32,borderRadius:'50%',
                    background:'var(--sg-b)',display:'flex',alignItems:'center',
                    justifyContent:'center',fontSize:14,flexShrink:0
                  }}>✓</div>
                  <div>
                    <div style={{fontSize:13,fontWeight:600,color:'var(--sg-b)'}}>Analysis Queued</div>
                    <div style={{fontSize:11,color:'var(--text3)',marginTop:2}}>Running in background — browse freely</div>
                  </div>
                </div>
                <div style={{fontSize:12,color:'var(--text2)',lineHeight:1.5,padding:'8px 0',borderTop:'1px solid var(--sg-bd)'}}>
                  {infoMsg}
                </div>
              </div>

              {/* Agent pipeline — all show as queued */}
              <div style={{marginBottom:16}}>
                {AGENTS.map((agent, i) => (
                  <div key={i} className="agent-row">
                    <div className="agent-num" style={{
                      background:'var(--surface3)',color:'var(--text4)',
                      border:'1px solid var(--border)'
                    }}>{i + 1}</div>
                    <div style={{flex:1}}>
                      <div className="agent-name">{agent.name}</div>
                      <div className="agent-desc">{agent.desc}</div>
                    </div>
                    <div style={{textAlign:'right',flexShrink:0}}>
                      <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',marginBottom:2}}>{agent.model}</div>
                      <span className="agent-status" style={{color:'var(--text4)'}}>Queued</span>
                    </div>
                  </div>
                ))}
              </div>

              <div style={{display:'flex',gap:8}}>
                <button className="btn btn-primary" onClick={handleDone} style={{flex:1,justifyContent:'center'}}>
                  View Job Queue →
                </button>
                <button className="btn btn-ghost" onClick={onClose} style={{flex:1,justifyContent:'center'}}>
                  Continue Browsing
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </>
  )
}