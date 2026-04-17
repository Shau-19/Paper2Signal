import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getSessions, getHealth } from '../api/client'
import { useStore } from '../store/appStore'
import { useState } from 'react'

export default function Profile() {
  const navigate = useNavigate()
  const { stack, setStack, savedPapers, buildSnippets, removeSnippet } = useStore()
  const [stackInput, setStackInput] = useState('')
  const [editingStack, setEditingStack] = useState(false)
  const [localStack, setLocalStack] = useState(stack)

  const { data: sessions = [] } = useQuery({ queryKey: ['sessions'], queryFn: getSessions })
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth })

  const paperSessions  = sessions.filter(s => s.session_type === 'paper')
  const globalSessions = sessions.filter(s => s.session_type === 'global')

  const addStackItem = () => {
    if (!stackInput.trim()) return
    setLocalStack(prev => [...prev, stackInput.trim()])
    setStackInput('')
  }
  const saveStack = () => { setStack(localStack); setEditingStack(false) }

  const timeAgo = (ts) => {
    if (!ts) return '—'
    const diff = Date.now() - new Date(ts).getTime()
    const m = Math.floor(diff / 60000)
    if (m < 1) return 'just now'
    if (m < 60) return `${m}m ago`
    const h = Math.floor(m / 60)
    if (h < 24) return `${h}h ago`
    return `${Math.floor(h / 24)}d ago`
  }

  return (
    <div className="page">

      {/* ── Hero ── */}
      <div className="card" style={{padding:24,marginBottom:20,display:'flex',alignItems:'center',gap:20}}>
        <div style={{width:54,height:54,borderRadius:'50%',background:'var(--gold)',display:'flex',alignItems:'center',justifyContent:'center',fontFamily:'var(--mono)',fontSize:18,fontWeight:600,color:'#0d0d0f',flexShrink:0}}>
          PS
        </div>
        <div style={{flex:1}}>
          <div style={{fontFamily:'var(--serif)',fontSize:22,color:'var(--text)',marginBottom:3}}>My Research Dashboard</div>
          <div style={{fontFamily:'var(--mono)',fontSize:9.5,color:'var(--text4)',marginBottom:14}}>Paper2Signal · Sessions saved locally</div>
          <div style={{display:'flex',gap:24,flexWrap:'wrap'}}>
            {[
              {val:health?.papers_count??'—', label:'Papers indexed'},
              {val:health?.analyzed_count??'—', label:'Analyzed'},
              {val:paperSessions.length+globalSessions.length, label:'Chat sessions'},
              {val:savedPapers.length, label:'Saved papers'},
              {val:buildSnippets.length, label:'Build snippets'},
            ].map(({val,label}) => (
              <div key={label} style={{textAlign:'center'}}>
                <div style={{fontFamily:'var(--serif)',fontSize:22,color:'var(--text)',lineHeight:1}}>{val}</div>
                <div style={{fontFamily:'var(--mono)',fontSize:8,color:'var(--text4)',textTransform:'uppercase',letterSpacing:'.08em',marginTop:2}}>{label}</div>
              </div>
            ))}
          </div>
        </div>
        <div style={{display:'flex',flexDirection:'column',gap:8,flexShrink:0}}>
          <button className="btn btn-primary btn-sm" onClick={() => navigate('/app')}>View digest</button>
          <button className="btn btn-ghost btn-sm" onClick={() => navigate('/app/explore')}>Browse papers</button>
        </div>
      </div>

      {/* ── 2-col grid ── */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>

        {/* Paper sessions */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Paper Chat Sessions</div>
            <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text3)'}}>{paperSessions.length}</span>
          </div>
          {paperSessions.length === 0 ? (
            <div style={{fontSize:12,color:'var(--text4)',padding:'8px 0'}}>No paper chats yet — open a paper in Read &amp; Chat.</div>
          ) : paperSessions.map(s => (
            <div key={s.id} style={{display:'flex',alignItems:'center',gap:9,padding:'8px 0',borderBottom:'1px solid var(--border)',cursor:'pointer'}}
              onClick={() => navigate('/app/read')}>
              <div style={{width:28,height:28,borderRadius:6,background:'var(--sg-p)',border:'1px solid var(--sg-bd)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,flexShrink:0}}>📄</div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,fontWeight:500,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginBottom:2}}>
                  {(s.paper_title||s.title||'Paper chat').substring(0,44)}...
                </div>
                <div style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)'}}>{s.message_count} messages · {timeAgo(s.last_used)}</div>
              </div>
              {s.page_index_built && (
                <span style={{fontFamily:'var(--mono)',fontSize:8,color:'var(--gold-l)',background:'var(--gold-p)',border:'1px solid var(--gold-bd)',padding:'1px 5px',borderRadius:3,flexShrink:0}}>Deep</span>
              )}
            </div>
          ))}
        </div>

        {/* Global sessions */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Global Chat Sessions</div>
            <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text3)'}}>{globalSessions.length}</span>
          </div>
          {globalSessions.length === 0 ? (
            <div style={{fontSize:12,color:'var(--text4)',padding:'8px 0'}}>No global chats yet — use Global Chat to start.</div>
          ) : globalSessions.map(s => (
            <div key={s.id} style={{display:'flex',alignItems:'center',gap:9,padding:'8px 0',borderBottom:'1px solid var(--border)',cursor:'pointer'}}
              onClick={() => navigate('/app')}>
              <div style={{width:28,height:28,borderRadius:6,background:'var(--surface3)',border:'1px solid var(--border2)',display:'flex',alignItems:'center',justifyContent:'center',fontSize:12,flexShrink:0}}>💬</div>
              <div style={{flex:1,minWidth:0}}>
                <div style={{fontSize:12,fontWeight:500,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',marginBottom:2}}>
                  {(s.title||'Global chat').substring(0,45)}
                </div>
                <div style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text4)'}}>{s.message_count} messages · {timeAgo(s.last_used)}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Build snippets */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>My Build</div>
            <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text3)'}}>{buildSnippets.length} snippets</span>
          </div>
          {buildSnippets.length === 0 ? (
            <div style={{fontSize:12,color:'var(--text4)',padding:'8px 0'}}>
              No snippets yet — click "+ Build" on any code block in chat.
            </div>
          ) : buildSnippets.map(s => (
            <div key={s.id} style={{padding:'8px 0',borderBottom:'1px solid var(--border)'}}>
              <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:4}}>
                <span style={{fontFamily:'var(--mono)',fontSize:8.5,color:'var(--gold-l)',background:'var(--gold-p)',border:'1px solid var(--gold-bd)',padding:'1px 6px',borderRadius:3}}>
                  {s.lang}
                </span>
                <div style={{display:'flex',gap:5}}>
                  <button className="btn btn-ghost btn-sm" style={{fontSize:9,padding:'2px 6px'}} onClick={() => navigator.clipboard.writeText(s.code)}>Copy</button>
                  <button className="btn btn-ghost btn-sm" style={{fontSize:9,padding:'2px 6px',color:'var(--red)'}} onClick={() => removeSnippet(s.id)}>Remove</button>
                </div>
              </div>
              <div style={{fontSize:11,color:'var(--text3)',fontFamily:'var(--mono)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                {s.code?.substring(0,64)}...
              </div>
            </div>
          ))}
        </div>

        {/* Tech stack */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Tech Stack</div>
            <button className="btn btn-ghost btn-sm" onClick={() => { setEditingStack(!editingStack); setLocalStack(stack) }}>
              {editingStack ? 'Cancel' : 'Edit'}
            </button>
          </div>
          {!editingStack ? (
            <div style={{display:'flex',flexWrap:'wrap',gap:6}}>
              {stack.map(s => (
                <span key={s} style={{fontFamily:'var(--mono)',fontSize:10,background:'var(--surface2)',border:'1px solid var(--border)',color:'var(--text2)',padding:'3px 9px',borderRadius:4}}>
                  {s}
                </span>
              ))}
              {stack.length === 0 && <div style={{fontSize:12,color:'var(--text4)'}}>No stack set — click Edit to add technologies.</div>}
            </div>
          ) : (
            <>
              <div style={{display:'flex',flexWrap:'wrap',gap:5,marginBottom:12}}>
                {localStack.map((s,i) => (
                  <span key={i} style={{fontFamily:'var(--mono)',fontSize:10,background:'var(--surface2)',border:'1px solid var(--border)',color:'var(--text2)',padding:'3px 9px',borderRadius:4,display:'flex',alignItems:'center',gap:5}}>
                    {s}
                    <span style={{cursor:'pointer',color:'var(--red)',fontSize:13,lineHeight:1}} onClick={() => setLocalStack(prev => prev.filter((_,j) => j!==i))}>×</span>
                  </span>
                ))}
              </div>
              <div style={{display:'flex',gap:6,marginBottom:10}}>
                <input className="input" style={{fontSize:12}} placeholder="Add technology..."
                  value={stackInput} onChange={e => setStackInput(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && addStackItem()} />
                <button className="btn btn-ghost btn-sm" onClick={addStackItem}>Add</button>
              </div>
              <button className="btn btn-primary btn-sm" style={{width:'100%',justifyContent:'center'}} onClick={saveStack}>
                Save Stack
              </button>
            </>
          )}
        </div>
      </div>

      {/* Sentinel info */}
      <div className="card" style={{padding:18,display:'flex',alignItems:'center',gap:16}}>
        <div style={{fontSize:20}}>🛡️</div>
        <div style={{flex:1}}>
          <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)',marginBottom:3}}>The Sentinel · GRPO Fine-tuned Model</div>
          <div style={{fontSize:12,color:'var(--text3)',lineHeight:1.65}}>
            shau1905/papersignal-hype-detector · Qwen2.5-1.5B + LoRA · Trained with GitHub stars as reward signal · Zero human labels
          </div>
        </div>
        <a href="https://huggingface.co/shau1905/papersignal-hype-detector" target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">
          View on HF ↗
        </a>
      </div>

    </div>
  )
}