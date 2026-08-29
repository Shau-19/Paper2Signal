import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { getJob } from '../api/client'
import { useStore } from '../store/appStore'

const actionColor = (a) => {
  if (!a) return 'var(--text3)'
  const l = a.toLowerCase()
  if (l.includes('adopt'))      return 'var(--sg-b)'
  if (l.includes('experiment')) return 'var(--amber)'
  return 'var(--text3)'
}

const actionBadge = (a) => {
  if (!a) return 'badge-watch'
  const l = a.toLowerCase()
  if (l.includes('adopt'))      return 'badge-adopt'
  if (l.includes('experiment')) return 'badge-experiment'
  return 'badge-watch'
}

const timeAgo = (ts) => {
  if (!ts) return ''
  const diff = Math.floor((Date.now() - new Date(ts).getTime()) / 1000)
  if (diff < 60)   return `${diff}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

function PulsingDot({ color }) {
  return (
    <div style={{ position:'relative', width:8, height:8, flexShrink:0 }}>
      <div style={{ position:'absolute', inset:0, borderRadius:'50%', background:color }}/>
      <div style={{ position:'absolute', inset:0, borderRadius:'50%', background:color, opacity:.4, animation:'dot-ring 1.5s ease-in-out infinite' }}/>
      <style>{`@keyframes dot-ring{0%{transform:scale(1);opacity:.4}100%{transform:scale(2.8);opacity:0}}`}</style>
    </div>
  )
}

function ScoreBar({ label, value }) {
  const pct   = value != null ? (value / 10) * 100 : 0
  const color = value == null ? 'var(--border)' : value >= 7 ? 'var(--sg-b)' : value >= 4 ? 'var(--amber)' : 'var(--red)'
  return (
    <div style={{ marginBottom:8 }}>
      <div style={{ display:'flex', justifyContent:'space-between', marginBottom:4 }}>
        <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', textTransform:'uppercase', letterSpacing:'.08em' }}>{label}</span>
        <span style={{ fontFamily:'var(--mono)', fontSize:10, color, fontWeight:600 }}>{value?.toFixed(1) ?? '—'}</span>
      </div>
      <div style={{ height:3, background:'var(--border)', borderRadius:2, overflow:'hidden' }}>
        <div style={{ height:'100%', width:`${pct}%`, background:color, borderRadius:2, transition:'width .6s ease' }}/>
      </div>
    </div>
  )
}

function AnalysisCard({ job, onView, onRemove }) {
  const result = job.result || {}
  const score  = result.overall_score
  const color  = actionColor(result.action)
  const scoringFailed = score === 0 && result.score_reasoning === 'scoring_failed'

  return (
    <div style={{ background:'var(--surface)', border:'1px solid var(--border2)', borderRadius:'var(--radius-lg)', overflow:'hidden', marginBottom:16 }}>

      {/* Header strip */}
      <div style={{ background:'var(--surface2)', borderBottom:'1px solid var(--border)', padding:'12px 20px', display:'flex', alignItems:'center', gap:10 }}>
        <div style={{ width:7, height:7, borderRadius:'50%', background:'var(--sg-b)', flexShrink:0 }}/>
        <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--sg-b)', letterSpacing:'.12em', textTransform:'uppercase' }}>Analysis Complete</span>
        <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', marginLeft:'auto' }}>{timeAgo(job.started_at)}</span>
      </div>

      <div style={{ padding:20 }}>

        {/* Title + big score */}
        <div style={{ display:'flex', gap:16, marginBottom:16, alignItems:'flex-start' }}>
          <div style={{ flex:1 }}>
            <div style={{ fontSize:14, fontWeight:600, color:'var(--text)', lineHeight:1.4, marginBottom:6 }}>{job.title}</div>
            <div style={{ display:'flex', gap:7, flexWrap:'wrap', alignItems:'center' }}>
              {result.domain && (
                <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', background:'var(--surface3)', border:'1px solid var(--border)', padding:'2px 7px', borderRadius:3 }}>
                  {result.domain}
                </span>
              )}
              {result.novelty && (
                <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text3)' }}>{result.novelty}</span>
              )}
              {result.has_code && (
                <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--sg-b)', background:'var(--sg-p)', border:'1px solid var(--sg-bd)', padding:'2px 7px', borderRadius:3 }}>
                  Code ✓
                </span>
              )}
            </div>
          </div>
          <div style={{ textAlign:'center', flexShrink:0 }}>
            <div style={{ fontFamily:'var(--serif)', fontSize:42, fontWeight:600, color: scoringFailed ? 'var(--text4)' : color, lineHeight:1 }}>
              {score != null ? score.toFixed(1) : '—'}
            </div>
            <span className={`badge ${actionBadge(result.action)}`} style={{ marginTop:5, display:'inline-flex' }}>
              {result.action || 'Unknown'}
            </span>
          </div>
        </div>

        {/* Warnings */}
        {result.hype_score <= 4 && score >= 7 && !scoringFailed && (
          <div style={{ background:'var(--gold-p)', border:'1px solid var(--gold-bd)', borderRadius:'var(--radius)', padding:'8px 12px', marginBottom:14, fontSize:12, color:'var(--gold-l)', display:'flex', alignItems:'center', gap:8 }}>
            💎 <strong>Hidden Gem</strong> — high production value, low hype
          </div>
        )}
        {scoringFailed && (
          <div style={{ background:'rgba(239,68,68,.08)', border:'1px solid rgba(239,68,68,.25)', borderRadius:'var(--radius)', padding:'8px 12px', marginBottom:14, fontSize:12, color:'var(--red)' }}>
            ⚠️ Scoring failed (LLM parse error). Re-analyze to get accurate scores. Check your DeepSeek / HF API key.
          </div>
        )}

        {/* 5 dimension score bars */}
        <div style={{ padding:14, background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:'var(--radius)', marginBottom:14, display:'grid', gridTemplateColumns:'1fr 1fr', gap:'0 24px' }}>
          <ScoreBar label="Reproducibility" value={result.reproducibility} />
          <ScoreBar label="Compute"         value={result.compute_cost} />
          <ScoreBar label="Latency"         value={result.latency} />
          <ScoreBar label="Adoption"        value={result.adoption} />
          <div style={{ gridColumn:'1/-1' }}>
            <ScoreBar label="Hype (Sentinel)" value={result.hype_score} />
          </div>
        </div>

        {/* Summary */}
        {result.summary && (
          <div style={{ marginBottom:14 }}>
            <div style={{ fontFamily:'var(--mono)', fontSize:8, color:'var(--text4)', letterSpacing:'.1em', textTransform:'uppercase', marginBottom:5 }}>Summary</div>
            <div style={{ fontSize:12.5, color:'var(--text2)', lineHeight:1.75 }}>{result.summary}</div>
          </div>
        )}

        {/* Stack fit */}
        {result.stack_fit && (
          <div style={{ marginBottom:14 }}>
            <div style={{ fontFamily:'var(--mono)', fontSize:8, color:'var(--text4)', letterSpacing:'.1em', textTransform:'uppercase', marginBottom:5 }}>Stack Fit</div>
            <div style={{ fontSize:12, color:'var(--text3)', lineHeight:1.65 }}>{result.stack_fit}</div>
          </div>
        )}

        {/* Thinker reasoning */}
        {result.score_reasoning && !scoringFailed && (
          <div style={{ padding:'10px 12px', background:'var(--surface2)', border:'1px solid var(--border)', borderRadius:'var(--radius)', marginBottom:14 }}>
            <div style={{ fontFamily:'var(--mono)', fontSize:8, color:'var(--text4)', letterSpacing:'.1em', textTransform:'uppercase', marginBottom:5 }}>Thinker Reasoning</div>
            <div style={{ fontSize:11.5, color:'var(--text3)', lineHeight:1.65 }}>{result.score_reasoning}</div>
          </div>
        )}

        {/* Actions */}
        <div style={{ display:'flex', gap:8 }}>
          <button className="btn btn-primary" onClick={onView} style={{ flex:1, justifyContent:'center' }}>
            📖 Open in Read &amp; Chat →
          </button>
          <button className="btn btn-ghost" onClick={onRemove}>Dismiss</button>
        </div>
      </div>
    </div>
  )
}

function PendingCard({ job }) {
  const isRunning = job.status === 'running'
  return (
    <div style={{
      background:'var(--surface)', border:`1px solid ${isRunning ? 'rgba(245,158,11,.3)' : 'var(--border)'}`,
      borderRadius:'var(--radius-lg)', padding:'14px 18px', marginBottom:10,
    }}>
      <div style={{ display:'flex', alignItems:'center', gap:12 }}>
        <PulsingDot color={isRunning ? 'var(--amber)' : 'var(--text4)'} />
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--text)', marginBottom:3, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
            {job.title || job.paper_id}
          </div>
          <div style={{ display:'flex', gap:10 }}>
            <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)' }}>{job.paper_id}</span>
            <span style={{ fontFamily:'var(--mono)', fontSize:9, color: isRunning ? 'var(--amber)' : 'var(--text4)' }}>
              {isRunning ? '4-agent pipeline running...' : 'Queued'}
            </span>
            <span style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)' }}>{timeAgo(job.started_at)}</span>
          </div>
        </div>
      </div>
      <div style={{ marginTop:10, height:2, background:'var(--border)', borderRadius:2, overflow:'hidden' }}>
        <div style={{ height:'100%', background: isRunning ? 'var(--amber)' : 'var(--border2)', borderRadius:2, animation: isRunning ? 'sweep 2s ease-in-out infinite' : 'none', width:'40%' }}/>
      </div>
      <style>{`@keyframes sweep{0%{transform:translateX(-250%)}100%{transform:translateX(350%)}}`}</style>
    </div>
  )
}

function FailedCard({ job, onRemove }) {
  return (
    <div style={{ background:'rgba(239,68,68,.05)', border:'1px solid rgba(239,68,68,.2)', borderRadius:'var(--radius-lg)', padding:'12px 16px', marginBottom:10, display:'flex', alignItems:'center', gap:12 }}>
      <div style={{ width:7, height:7, borderRadius:'50%', background:'var(--red)', flexShrink:0 }}/>
      <div style={{ flex:1, minWidth:0 }}>
        <div style={{ fontSize:12, fontWeight:500, color:'var(--text)', marginBottom:2 }}>{job.title?.substring(0,60)}...</div>
        <div style={{ fontSize:11, color:'var(--red)', opacity:.8 }}>{job.error?.substring(0,100) || 'Analysis failed'}</div>
      </div>
      <button className="btn btn-ghost btn-sm" onClick={onRemove} style={{ color:'var(--text4)', flexShrink:0 }}>Dismiss</button>
    </div>
  )
}

export default function JobsPage() {
  const navigate = useNavigate()
  const { activeJobs, updateJob, removeJob, addNotification, setActivePaper } = useStore()
  const pollRef  = useRef(null)

  useEffect(() => {
    const poll = async () => {
      const running = activeJobs.filter(j => j.status === 'pending' || j.status === 'running')
      for (const job of running) {
        try {
          const data = await getJob(job.job_id)
          if (data.status !== job.status) {
            updateJob(job.job_id, { status:data.status, result:data.result, error:data.error })
            if (data.status === 'done') {
              addNotification({ type:'job_done', title:job.title, paper_id:job.paper_id, job_id:job.job_id, result:data.result, message:'Analysis complete' })
            }
          }
        } catch(e) { /* silent */ }
      }
    }
    poll()
    pollRef.current = setInterval(poll, 3000)
    return () => clearInterval(pollRef.current)
  }, [activeJobs])

  const handleView = (job) => {
    if (job.result) { setActivePaper({ id:job.paper_id, ...job.result }); navigate('/app/read') }
  }

  const pending = activeJobs.filter(j => j.status === 'pending' || j.status === 'running')
  const done    = activeJobs.filter(j => j.status === 'done')
  const failed  = activeJobs.filter(j => j.status === 'failed')

  return (
    <div style={{ maxWidth:760, margin:'0 auto', padding:'0 20px' }}>

      {/* Header */}
      <div style={{ padding:'28px 0 24px' }}>
        <div style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', letterSpacing:'.16em', textTransform:'uppercase', marginBottom:6 }}>Analysis Queue</div>
        <div style={{ display:'flex', alignItems:'center', justifyContent:'space-between', flexWrap:'wrap', gap:12 }}>
          <div>
            <h1 style={{ fontFamily:'var(--serif)', fontSize:'clamp(1.8rem,3vw,2.4rem)', fontWeight:600, color:'var(--text)', letterSpacing:'-.03em', marginBottom:4 }}>
              Background Jobs
            </h1>
            {activeJobs.length > 0 && (
              <div style={{ display:'flex', gap:14, fontFamily:'var(--mono)', fontSize:10 }}>
                {pending.length > 0 && <span style={{ color:'var(--amber)' }}>● {pending.length} running</span>}
                {done.length    > 0 && <span style={{ color:'var(--sg-b)'  }}>✓ {done.length} complete</span>}
                {failed.length  > 0 && <span style={{ color:'var(--red)'   }}>✗ {failed.length} failed</span>}
              </div>
            )}
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/app', { state:{ openAnalyze:true } })}>+ Analyze Paper</button>
        </div>
      </div>

      {/* Empty */}
      {activeJobs.length === 0 && (
        <div className="card" style={{ padding:'48px 32px', textAlign:'center' }}>
          <div style={{ fontSize:32, marginBottom:14 }}>🔬</div>
          <div style={{ fontFamily:'var(--serif)', fontSize:18, color:'var(--text)', marginBottom:8 }}>No jobs yet</div>
          <div style={{ fontSize:13, color:'var(--text4)', lineHeight:1.7, maxWidth:360, margin:'0 auto 24px' }}>
            Analyze any ArXiv paper — the 4-agent pipeline runs in the background while you browse.
          </div>
          <button className="btn btn-primary" onClick={() => navigate('/app', { state:{ openAnalyze:true } })}>Analyze a Paper →</button>
        </div>
      )}

      {/* Running */}
      {pending.length > 0 && (
        <section style={{ marginBottom:28 }}>
          <div style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--amber)', letterSpacing:'.12em', textTransform:'uppercase', marginBottom:12, display:'flex', alignItems:'center', gap:8 }}>
            <PulsingDot color="var(--amber)"/> In Progress
          </div>
          {pending.map(j => <PendingCard key={j.job_id} job={j}/>)}
        </section>
      )}

      {/* Completed */}
      {done.length > 0 && (
        <section style={{ marginBottom:28 }}>
          <div style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--sg-b)', letterSpacing:'.12em', textTransform:'uppercase', marginBottom:12 }}>
            ✓ Completed · {done.length}
          </div>
          {done.map(j => <AnalysisCard key={j.job_id} job={j} onView={() => handleView(j)} onRemove={() => removeJob(j.job_id)}/>)}
        </section>
      )}

      {/* Failed */}
      {failed.length > 0 && (
        <section style={{ marginBottom:28 }}>
          <div style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--red)', letterSpacing:'.12em', textTransform:'uppercase', marginBottom:12 }}>
            ✗ Failed · {failed.length}
          </div>
          {failed.map(j => <FailedCard key={j.job_id} job={j} onRemove={() => removeJob(j.job_id)}/>)}
        </section>
      )}
    </div>
  )
}