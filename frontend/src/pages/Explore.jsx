import { useQuery } from '@tanstack/react-query'
import { useState, useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import { getPapers, getAnalyzed, getHiddenGems, getThemes } from '../api/client'
import { useStore } from '../store/appStore'

const actionColor = (a) => {
  if (!a) return 'var(--text3)'
  const l = a.toLowerCase()
  if (l.includes('adopt'))      return 'var(--sg-b)'
  if (l.includes('experiment')) return 'var(--amber)'
  if (l.includes('watch'))      return 'var(--text3)'
  return 'var(--red)'
}

const actionBadge = (a) => {
  if (!a) return 'badge-watch'
  const l = a.toLowerCase()
  if (l.includes('adopt'))      return 'badge-adopt'
  if (l.includes('experiment')) return 'badge-experiment'
  return 'badge-watch'
}

export default function Explore() {
  const navigate = useNavigate()
  const { setActivePaper, savedPapers, savePaper, unsavePaper, stack } = useStore()
  const [filter, setFilter] = useState('all')
  const [search, setSearch] = useState('')

  // ── FIX 1: Load ALL papers, not just 100 ──────────────────────────────────
  // DB has 249+ papers. With limit=100, landmark papers (seeded most recently
  // = oldest ingested_at) get cut off since API orders by ingested_at desc.
  const { data: papers = [], isLoading } = useQuery({
    queryKey: ['papers'],
    queryFn: () => getPapers(500),
    staleTime: 30_000,
  })
  const { data: analyzed = [] } = useQuery({
    queryKey: ['analyzed'],
    queryFn: () => getAnalyzed(500),
    staleTime: 30_000,
  })
  const { data: gems = [] }   = useQuery({ queryKey: ['gems'],   queryFn: getHiddenGems })
  const { data: themes = [] } = useQuery({ queryKey: ['themes'], queryFn: getThemes })

  // ── FIX 2: Merge papers + analysis into one list ──────────────────────────
  // analysisMap gives score, action, summary etc for papers that are analyzed.
  // Merge so every paper object has its analysis fields populated directly.
  const analysisMap = useMemo(
    () => Object.fromEntries(analyzed.map(a => [a.id, a])),
    [analyzed]
  )

  const allPapers = useMemo(() => {
    const seen = new Set()
    const merged = []
    for (const p of papers) {
      seen.add(p.id)
      merged.push({ ...p, ...analysisMap[p.id] })
    }
    // Also include analyzed papers not returned by getPapers (edge case)
    for (const a of analyzed) {
      if (!seen.has(a.id)) {
        seen.add(a.id)
        merged.push(a)
      }
    }
    return merged
  }, [papers, analyzed, analysisMap])

  const gemIds = useMemo(() => new Set(gems.map(g => g.id)), [gems])

  // ── FIX 3: Search title + abstract + summary + contributions ──────────────
  // Old code: p.title.toLowerCase().includes(q) only.
  // "Flash Attention" works now, "attention is all you need" matches abstract.
  const textFiltered = useMemo(() => {
    if (!search) return allPapers
    const q = search.toLowerCase()
    return allPapers.filter(p =>
      p.title?.toLowerCase().includes(q)         ||
      p.abstract?.toLowerCase().includes(q)      ||
      p.summary?.toLowerCase().includes(q)       ||
      p.contributions?.toLowerCase().includes(q)
    )
  }, [allPapers, search])

  const filtered = useMemo(() => {
    if (filter === 'adopt')
      return textFiltered.filter(p => p.action?.toLowerCase().includes('adopt'))
    if (filter === 'experiment')
      return textFiltered.filter(p => p.action?.toLowerCase().includes('experiment'))
    if (filter === 'watch')
      return textFiltered.filter(p => p.action === 'Watch')
    if (filter === 'gems')
      return textFiltered.filter(p => gemIds.has(p.id))
    if (filter === 'stack')
      return textFiltered.filter(p =>
        p.stack_fit && stack.some(s => p.stack_fit.toLowerCase().includes(s.toLowerCase()))
      )
    if (filter === 'new')
      return textFiltered.filter(p => !p.is_analyzed)
    return textFiltered
  }, [textFiltered, filter, gemIds, stack])

  const handleOpen = (paper) => { setActivePaper(paper); navigate('/app/read') }
  const toggleSave = (e, id) => {
    e.stopPropagation()
    savedPapers.includes(id) ? unsavePaper(id) : savePaper(id)
  }

  return (
    <div className="page-wide">
      <div style={{maxWidth:'var(--max-w)',margin:'0 auto',padding:'28px 32px 64px'}}>

        {/* Header */}
        <div style={{marginBottom:24}}>
          <div style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)',letterSpacing:'.16em',textTransform:'uppercase',marginBottom:6}}>Browse</div>
          <h1 style={{fontFamily:'var(--serif)',fontSize:'clamp(1.8rem,3.5vw,2.6rem)',fontWeight:600,color:'var(--text)',letterSpacing:'-.03em',lineHeight:1.1}}>
            Explore Papers
          </h1>
        </div>

        {/* Search + filters */}
        <div style={{position:'sticky',top:'var(--nav-h)',background:'var(--bg)',borderBottom:'1px solid var(--border)',padding:'12px 0 14px',marginBottom:24,zIndex:10}}>
          <input
            className="input"
            placeholder={`Search ${allPapers.length} papers by title, abstract, or summary...`}
            value={search}
            onChange={e => setSearch(e.target.value)}
            style={{marginBottom:10,maxWidth:600}}
          />
          <div className="chips">
            {[
              {id:'all',        label:'All'},
              {id:'adopt',      label:'Adopt'},
              {id:'experiment', label:'Experiment'},
              {id:'watch',      label:'Watch'},
              {id:'gems',       label:'💎 Gems'},
              {id:'stack',      label:'My stack'},
              {id:'new',        label:'Not scored'},
            ].map(c => (
              <div key={c.id} className={`chip${filter===c.id?' active':''}`} onClick={() => setFilter(c.id)}>
                {c.label}
              </div>
            ))}
            <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)',marginLeft:4}}>
              {filtered.length} papers
            </span>
          </div>
        </div>

        {/* Layout: papers grid + right rail */}
        <div style={{display:'grid',gridTemplateColumns:'1fr 260px',gap:24,alignItems:'start'}}>

          {/* Papers list */}
          <div>
            {isLoading ? (
              [...Array(6)].map((_,i) => <div key={i} className="skeleton" style={{height:120,marginBottom:10}}/>)
            ) : filtered.length === 0 ? (
              <div className="empty">
                <svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
                <div className="empty-title">No papers found</div>
                <div className="empty-sub">Try a different filter or search term</div>
              </div>
            ) : (
              filtered.map(paper => {
                const isGem   = gemIds.has(paper.id)
                const isSaved = savedPapers.includes(paper.id)
                const color   = actionColor(paper.action)
                return (
                  <div key={paper.id} className="card paper-card" style={{marginBottom:10}} onClick={() => handleOpen(paper)}>
                    <div style={{display:'flex',alignItems:'flex-start',gap:14,marginBottom:paper.overall_score?10:0}}>
                      <div style={{flex:1,minWidth:0}}>
                        <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)',lineHeight:1.45,marginBottom:6,
                          overflow:'hidden',textOverflow:'ellipsis',display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical'}}>
                          {isGem && '💎 '}{paper.title}
                        </div>
                        <div style={{display:'flex',alignItems:'center',gap:7,flexWrap:'wrap'}}>
                          {paper.cluster_theme && (
                            <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',background:'var(--surface2)',border:'1px solid var(--border)',padding:'1px 6px',borderRadius:3}}>
                              {paper.cluster_theme.split(' · ')[0]}
                            </span>
                          )}
                          {paper.github_url && (
                            <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text3)'}}>
                              ⭐ {paper.github_stars ?? 'Code'}
                            </span>
                          )}
                          {paper.hype_score != null && (
                            <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:paper.hype_score<=4?'var(--sg-b)':paper.hype_score>=7?'var(--red)':'var(--text3)'}}>
                              Hype {paper.hype_score}/10
                            </span>
                          )}
                        </div>
                      </div>
                      <div style={{textAlign:'center',flexShrink:0}}>
                        {paper.overall_score ? (
                          <>
                            <div style={{fontFamily:'var(--serif)',fontSize:28,fontWeight:600,color,lineHeight:1}}>{paper.overall_score.toFixed(1)}</div>
                            <span className={`badge ${actionBadge(paper.action)}`} style={{marginTop:4,display:'inline-flex'}}>{paper.action}</span>
                          </>
                        ) : (
                          <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',background:'var(--surface3)',border:'1px solid var(--border)',padding:'2px 7px',borderRadius:3}}>NEW</span>
                        )}
                      </div>
                    </div>

                    {(paper.summary || paper.abstract) && (
                      <div style={{fontSize:12,color:'var(--text2)',lineHeight:1.7,
                        display:'-webkit-box',WebkitLineClamp:2,WebkitBoxOrient:'vertical',overflow:'hidden',marginBottom:paper.overall_score?10:0}}>
                        {paper.summary || paper.abstract?.substring(0,200)}...
                      </div>
                    )}

                    {paper.overall_score && (
                      <div style={{display:'flex',gap:8,marginBottom:10}}>
                        {[['Repro',paper.reproducibility],['Compute',paper.compute_cost],['Latency',paper.latency_score],['Adoption',paper.adoption]].map(([label,val]) => (
                          <div key={label} style={{flex:1}}>
                            <div style={{fontFamily:'var(--mono)',fontSize:7.5,color:'var(--text4)',marginBottom:3}}>{label}</div>
                            <div className="dim-track"><div className="dim-fill" style={{width:`${(val||0)*10}%`,background:color,opacity:.5}}/></div>
                          </div>
                        ))}
                      </div>
                    )}

                    <div style={{display:'flex',alignItems:'center',gap:6}}>
                      <button className="btn btn-ghost btn-sm" onClick={e => { e.stopPropagation(); handleOpen(paper) }}
                        style={{color:paper.is_analyzed?'var(--gold)':'var(--text3)'}}>
                        {paper.is_analyzed ? '📖 Read & Chat' : '▶ Analyze + Read'}
                      </button>
                      <button className="btn btn-ghost btn-sm" onClick={e => toggleSave(e, paper.id)}>
                        {isSaved ? '🔖 Saved' : '🔖 Save'}
                      </button>
                      {paper.github_url && (
                        <a href={paper.github_url} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm" onClick={e => e.stopPropagation()}>
                          GitHub ↗
                        </a>
                      )}
                      <a href={`https://arxiv.org/abs/${paper.id}`} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm" onClick={e => e.stopPropagation()}>
                        ArXiv ↗
                      </a>
                    </div>
                  </div>
                )
              })
            )}
          </div>

          {/* Right rail */}
          <div style={{position:'sticky',top:`calc(var(--nav-h) + 80px)`,display:'flex',flexDirection:'column',gap:12}}>

            {/* Trending themes */}
            <div className="card" style={{padding:16}}>
              <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',letterSpacing:'.14em',textTransform:'uppercase',marginBottom:12}}>
                Trending themes
              </div>
              {themes.slice(0,8).map(t => (
                <div key={t.theme} style={{display:'flex',alignItems:'center',justifyContent:'space-between',padding:'5px 0',borderBottom:'1px solid var(--border)'}}>
                  <div style={{fontSize:12,color:'var(--text2)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1,marginRight:8}}>
                    {t.theme?.split(' · ')[0]}
                  </div>
                  <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)'}}>{t.count}</span>
                </div>
              ))}
            </div>

            {/* Stack match */}
            <div className="card" style={{padding:16}}>
              <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',letterSpacing:'.14em',textTransform:'uppercase',marginBottom:10}}>
                Your stack
              </div>
              <div style={{display:'flex',flexWrap:'wrap',gap:5,marginBottom:10}}>
                {stack.map(s => (
                  <span key={s} style={{fontFamily:'var(--mono)',fontSize:9,background:'var(--surface2)',border:'1px solid var(--border)',color:'var(--text3)',padding:'2px 7px',borderRadius:3}}>
                    {s}
                  </span>
                ))}
              </div>
              <div style={{fontSize:11.5,color:'var(--text3)'}}>
                {allPapers.filter(p => p.stack_fit && stack.some(s => p.stack_fit.toLowerCase().includes(s.toLowerCase()))).length} matching papers
              </div>
            </div>

            {/* DB stats */}
            <div className="card" style={{padding:16}}>
              <div style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--text4)',letterSpacing:'.14em',textTransform:'uppercase',marginBottom:10}}>
                Database
              </div>
              <div style={{display:'flex',flexDirection:'column',gap:6}}>
                {[
                  ['Total',    allPapers.length],
                  ['Analyzed', analyzed.length],
                  ['Pending',  Math.max(0, allPapers.length - analyzed.length)],
                ].map(([label, val]) => (
                  <div key={label} style={{display:'flex',justifyContent:'space-between',alignItems:'center'}}>
                    <span style={{fontSize:11.5,color:'var(--text3)'}}>{label}</span>
                    <span style={{fontFamily:'var(--mono)',fontSize:10,color:'var(--text2)'}}>{val}</span>
                  </div>
                ))}
              </div>
            </div>

          </div>
        </div>
      </div>
    </div>
  )
}