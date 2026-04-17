import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getAnalyzed, getHiddenGems, getHealth } from '../api/client'
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

function PaperRow({ paper, onClick }) {
  const color = actionColor(paper.action)
  return (
    <div onClick={onClick}
      style={{ padding:'12px 0', borderBottom:'1px solid var(--border)', cursor:'pointer', transition:'background .12s' }}
      onMouseEnter={e => e.currentTarget.style.background='var(--surface2)'}
      onMouseLeave={e => e.currentTarget.style.background='transparent'}
    >
      <div style={{ display:'flex', alignItems:'flex-start', gap:12, padding:'0 16px' }}>
        <div style={{ flex:1, minWidth:0 }}>
          <div style={{ fontSize:13, fontWeight:600, color:'var(--text)', lineHeight:1.45, marginBottom:4,
            overflow:'hidden', textOverflow:'ellipsis', display:'-webkit-box', WebkitLineClamp:2, WebkitBoxOrient:'vertical' }}>
            {paper.title}
          </div>
          <div style={{ display:'flex', alignItems:'center', gap:8, flexWrap:'wrap' }}>
            {paper.domain && (
              <span style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--text4)', background:'var(--surface3)', border:'1px solid var(--border)', padding:'1px 6px', borderRadius:3 }}>
                {paper.domain}
              </span>
            )}
            {paper.hype_score != null && (
              <span style={{ fontFamily:'var(--mono)', fontSize:8.5, color: paper.hype_score<=4?'var(--sg-b)':paper.hype_score>=7?'var(--red)':'var(--text3)' }}>
                {paper.hype_score<=4?'💎 ':''}Hype {paper.hype_score}/10
              </span>
            )}
            {paper.summary && (
              <span style={{ fontSize:11.5, color:'var(--text3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap', maxWidth:260 }}>
                {paper.summary?.substring(0, 80)}...
              </span>
            )}
          </div>
        </div>
        <div style={{ textAlign:'center', flexShrink:0 }}>
          <div style={{ fontFamily:'var(--serif)', fontSize:26, fontWeight:600, color, lineHeight:1 }}>
            {paper.overall_score?.toFixed(1)}
          </div>
          <span className={`badge ${actionBadge(paper.action)}`} style={{ marginTop:3, display:'inline-flex' }}>
            {paper.action || 'Watch'}
          </span>
        </div>
      </div>
    </div>
  )
}

export default function Today() {
  const navigate = useNavigate()
  const { setActivePaper } = useStore()
  const { data: analyzed = [], isLoading } = useQuery({ queryKey:['analyzed'], queryFn:() => getAnalyzed(100) })
  const { data: gems = [] }  = useQuery({ queryKey:['gems'],   queryFn: getHiddenGems })
  const { data: health }     = useQuery({ queryKey:['health'], queryFn: getHealth })

  const adopt      = analyzed.filter(p => p.action?.toLowerCase().includes('adopt'))
  const experiment = analyzed.filter(p => p.action?.toLowerCase().includes('experiment'))
  const watch      = analyzed.filter(p => p.action === 'Watch')
  const overhyped  = analyzed.filter(p => p.hype_score >= 7 && p.overall_score < 5)
  const avgScore   = analyzed.length
    ? (analyzed.reduce((a,p) => a + (p.overall_score||0), 0) / analyzed.length).toFixed(1)
    : '—'

  const handlePaper = (paper) => { setActivePaper(paper); navigate('/app/read') }

  if (isLoading) return (
    <div className="page">
      <div style={{ display:'grid', gridTemplateColumns:'repeat(4,1fr)', gap:12, marginBottom:20 }}>
        {[...Array(4)].map((_,i) => <div key={i} className="skeleton" style={{ height:90 }}/>)}
      </div>
      {[...Array(6)].map((_,i) => <div key={i} className="skeleton" style={{ height:80, marginBottom:8 }}/>)}
    </div>
  )

  return (
    <div style={{ maxWidth:'var(--max-w)', margin:'0 auto' }}>

      {/* Header */}
      <div style={{ padding:'28px clamp(16px,4vw,40px) 0', marginBottom:20 }}>
        <div style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', letterSpacing:'.16em', textTransform:'uppercase', marginBottom:6 }}>
          {new Date().toLocaleDateString('en-US',{ weekday:'long', month:'long', day:'numeric' })}
        </div>
        <h1 style={{ fontFamily:'var(--serif)', fontSize:'clamp(2rem,4vw,3rem)', fontWeight:600, color:'var(--text)', letterSpacing:'-.03em', lineHeight:1.1, marginBottom:8 }}>
          Today's Signal
        </h1>
        <p style={{ fontSize:14, color:'var(--text3)', lineHeight:1.7, maxWidth:520 }}>
          {analyzed.length} papers analyzed · {adopt.length} adopt-ready · {gems.length} hidden gems
        </p>
      </div>

      {/* Stats — fluid grid */}
      <div className="stats-bar" style={{ margin:'0 clamp(16px,4vw,40px) 20px' }}>
        {[
          { label:'Papers analyzed', value:analyzed.length,    sub:`of ${health?.papers_count ?? 0} total` },
          { label:'Adopt-ready',     value:adopt.length,       sub:'score ≥ 7.5', color:'var(--sg-b)' },
          { label:'Hidden gems',     value:gems.length,        sub:'high score · low hype', color:'var(--gold-l)' },
          { label:'Avg score',       value:avgScore,           sub:'production readiness' },
        ].map(({ label, value, sub, color }) => (
          <div key={label} className="stats-bar-cell">
            <div style={{ fontFamily:'var(--mono)', fontSize:8, color:'var(--text4)', letterSpacing:'.1em', textTransform:'uppercase', marginBottom:5 }}>{label}</div>
            <div style={{ fontFamily:'var(--serif)', fontSize:26, color:color||'var(--text)', lineHeight:1, marginBottom:3 }}>{value}</div>
            <div style={{ fontSize:11, color:'var(--text3)' }}>{sub}</div>
          </div>
        ))}
      </div>

      {/* Gem banner */}
      {gems.length > 0 && (
        <div style={{ margin:'0 clamp(16px,4vw,40px) 20px', background:'var(--gold-p)', border:'1px solid var(--gold-bd)', borderRadius:'var(--radius-lg)', padding:'11px 16px', display:'flex', alignItems:'center', gap:12 }}>
          <span style={{ fontSize:18 }}>💎</span>
          <div style={{ flex:1 }}>
            <span style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--gold-l)', letterSpacing:'.12em', textTransform:'uppercase', marginRight:10 }}>Sentinel found</span>
            <span style={{ fontSize:12.5, color:'var(--text2)' }}>
              {gems[0]?.title?.substring(0, 68)}... — Score {gems[0]?.overall_score?.toFixed(1)}, Hype {gems[0]?.hype_score}/10
            </span>
          </div>
          <button className="btn btn-ghost btn-sm" onClick={() => handlePaper(gems[0])}>Go deep →</button>
        </div>
      )}

      {/* Digest — fluid columns */}
      <div className="digest-grid" style={{ padding:'0 clamp(16px,4vw,40px) 56px' }}>
        {[
          { label:'🟢 Adopt Now',  items:adopt,      color:'var(--sg-b)'  },
          { label:'🟡 Experiment', items:experiment, color:'var(--amber)' },
          { label:'🔵 Watch',      items:watch,      color:'var(--text3)' },
          { label:'⚠️ Overhyped',  items:overhyped,  color:'var(--red)'   },
        ].map(({ label, items, color }) => (
          <div key={label} className="card" style={{ padding:0, overflow:'hidden' }}>
            <div style={{ padding:'13px 16px', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between' }}>
              <div style={{ fontFamily:'var(--mono)', fontSize:9, letterSpacing:'.12em', textTransform:'uppercase', color }}>{label}</div>
              <span style={{ fontFamily:'var(--mono)', fontSize:8.5, color:'var(--text4)' }}>{items.length}</span>
            </div>
            {items.length === 0 ? (
              <div style={{ padding:'22px 16px', fontSize:12, color:'var(--text4)' }}>No papers yet.</div>
            ) : (
              items.slice(0, 4).map(paper => <PaperRow key={paper.id} paper={paper} onClick={() => handlePaper(paper)}/>)
            )}
            {items.length > 4 && (
              <div style={{ padding:'9px 16px', fontSize:11.5, color:'var(--text4)', cursor:'pointer', borderTop:'1px solid var(--border)' }}
                onClick={() => navigate('/app/explore')}>
                +{items.length - 4} more → Explore
              </div>
            )}
          </div>
        ))}
      </div>

    </div>
  )
}