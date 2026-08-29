import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { getSessions, getHealth, getProfile, updateProfile, getActivity } from '../api/client'
import { useStore } from '../store/appStore'
import { useState, useEffect } from 'react'

/* ─────────────────────────────────────────────────────────────────────────────
   ORIGINAL PROFILE COMPONENT (Commented out as per instructions)
   ─────────────────────────────────────────────────────────────────────────────
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
      ... (original content) ...
    </div>
  )
}
───────────────────────────────────────────────────────────────────────────── */


// ── NEW PERSISTENT USER & ACTIVITY PROFILE ─────────────────────────────────────

export default function Profile() {
  const navigate = useNavigate()
  const { userProfile, setUserProfile, savedPapers, buildSnippets, removeSnippet } = useStore()
  
  const [editingProfile, setEditingProfile] = useState(false)
  const [formData, setFormData] = useState({
    name: userProfile?.name || 'Shaurya',
    email: userProfile?.email || 'shaurya@papersignal.ai',
    role: userProfile?.role || 'Lead ML Engineer',
    model_pref: userProfile?.preferences?.model_pref || 'auto'
  })

  // Queries
  const { data: sessions = [] } = useQuery({ queryKey: ['sessions'], queryFn: getSessions })
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth })
  
  const { data: dbProfile, refetch: refetchProfile } = useQuery({ 
    queryKey: ['profile'], 
    queryFn: getProfile 
  })
  
  const { data: activities = [], refetch: refetchActivity } = useQuery({ 
    queryKey: ['activity'], 
    queryFn: getActivity,
    refetchInterval: 8000 // Automatically refresh the activity log timeline every 8s
  })

  // Sync state with DB when loaded
  useEffect(() => {
    if (dbProfile) {
      setFormData({
        name: dbProfile.name,
        email: dbProfile.email,
        role: dbProfile.role,
        model_pref: dbProfile.preferences?.model_pref || 'auto'
      })
      setUserProfile(dbProfile)
    }
  }, [dbProfile, setUserProfile])

  const paperSessions  = sessions.filter(s => s.session_type === 'deep')
  const globalSessions = sessions.filter(s => s.session_type === 'global')

  const handleSaveProfile = async () => {
    try {
      const updated = await updateProfile({
        name: formData.name,
        email: formData.email,
        role: formData.role,
        preferences: { model_pref: formData.model_pref }
      })
      if (updated.status === 'success') {
        refetchProfile()
        refetchActivity()
        setEditingProfile(false)
      }
    } catch (e) {
      console.error("Failed to update profile", e)
    }
  }

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

  const getActivityIcon = (type) => {
    switch (type) {
      case 'ingest':  return '📥'
      case 'analyze': return '⚡'
      case 'chat':    return '💬'
      case 'index':   return '📁'
      case 'profile': return '⚙️'
      default:        return '📝'
    }
  }

  const getActivityColor = (type) => {
    switch (type) {
      case 'ingest':  return 'var(--sg-b)'
      case 'analyze': return 'var(--gold)'
      case 'chat':    return 'var(--amber)'
      case 'index':   return 'var(--text2)'
      default:        return 'var(--text3)'
    }
  }

  return (
    <div className="page">

      {/* ── Hero ── */}
      <div className="card" style={{padding:24,marginBottom:20,display:'flex',alignItems:'center',gap:20}}>
        <div style={{width:54,height:54,borderRadius:'50%',background:'var(--gold)',display:'flex',alignItems:'center',justifyContent:'center',fontFamily:'var(--mono)',fontSize:18,fontWeight:600,color:'#0d0d0f',flexShrink:0}}>
          {formData.name.substring(0, 2).toUpperCase()}
        </div>
        <div style={{flex:1}}>
          <div style={{fontFamily:'var(--serif)',fontSize:22,color:'var(--text)',marginBottom:3}}>{formData.name}</div>
          <div style={{fontFamily:'var(--mono)',fontSize:9.5,color:'var(--text4)',marginBottom:14}}>{formData.role} · {formData.email}</div>
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
            </div>
          ))}
        </div>

        {/* Account / Preferences Settings */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Account Settings</div>
            <button className="btn btn-ghost btn-sm" onClick={() => { setEditingProfile(!editingProfile) }}>
              {editingProfile ? 'Cancel' : 'Edit'}
            </button>
          </div>
          {!editingProfile ? (
            <div style={{display:'flex',flexDirection:'column',gap:12}}>
              <div>
                <span style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase'}}>Name</span>
                <div style={{fontSize:13,color:'var(--text2)',marginTop:2}}>{formData.name}</div>
              </div>
              <div>
                <span style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase'}}>Role</span>
                <div style={{fontSize:13,color:'var(--text2)',marginTop:2}}>{formData.role}</div>
              </div>
              <div>
                <span style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase'}}>Preferred Model</span>
                <div style={{fontSize:13,color:'var(--text2)',marginTop:2,fontFamily:'var(--mono)'}}>{formData.model_pref.toUpperCase()}</div>
              </div>
            </div>
          ) : (
            <div style={{display:'flex',flexDirection:'column',gap:10}}>
              <div>
                <label style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase',display:'block',marginBottom:4}}>Name</label>
                <input className="input" style={{fontSize:12,width:'100%'}} value={formData.name} onChange={e => setFormData({...formData, name: e.target.value})} />
              </div>
              <div>
                <label style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase',display:'block',marginBottom:4}}>Email</label>
                <input className="input" style={{fontSize:12,width:'100%'}} value={formData.email} onChange={e => setFormData({...formData, email: e.target.value})} />
              </div>
              <div>
                <label style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase',display:'block',marginBottom:4}}>Role</label>
                <input className="input" style={{fontSize:12,width:'100%'}} value={formData.role} onChange={e => setFormData({...formData, role: e.target.value})} />
              </div>
              <div>
                <label style={{fontSize:10,fontFamily:'var(--mono)',color:'var(--text4)',textTransform:'uppercase',display:'block',marginBottom:4}}>Model Preference</label>
                <select className="input" style={{fontSize:12,width:'100%',background:'var(--surface2)',color:'var(--text)'}} value={formData.model_pref} onChange={e => setFormData({...formData, model_pref: e.target.value})}>
                  <option value="auto">Auto (OpenAI + Groq)</option>
                  <option value="groq">Groq Llama-3.3-70B</option>
                  <option value="openai">OpenAI GPT-4o-mini</option>
                </select>
              </div>
              <button className="btn btn-primary btn-sm" style={{width:'100%',justifyContent:'center',marginTop:6}} onClick={handleSaveProfile}>
                Save Settings
              </button>
            </div>
          )}
        </div>
      </div>

      {/* ── Activity Timeline & Snippets col grid ── */}
      <div style={{display:'grid',gridTemplateColumns:'1fr 1fr',gap:16,marginBottom:16}}>
        
        {/* Recent Activity Timeline */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Recent Activity</div>
            <span style={{fontFamily:'var(--mono)',fontSize:9,color:'var(--text3)'}}>Live Log</span>
          </div>
          {activities.length === 0 ? (
            <div style={{fontSize:12,color:'var(--text4)',padding:'8px 0'}}>No activity logged yet. Start exploring papers!</div>
          ) : (
            <div style={{display:'flex',flexDirection:'column',gap:12,maxHeight:300,overflowY:'auto',paddingRight:5}}>
              {activities.map(a => (
                <div key={a.id} style={{display:'flex',alignItems:'flex-start',gap:10,paddingBottom:10,borderBottom:'1px solid var(--border)'}}>
                  <div style={{fontSize:14,padding:'2px 6px',background:'var(--surface2)',borderRadius:5}}>{getActivityIcon(a.action_type)}</div>
                  <div style={{flex:1,minWidth:0}}>
                    <div style={{fontSize:12,color:'var(--text2)',lineHeight:1.35}}>{a.details}</div>
                    <div style={{fontSize:9.5,fontFamily:'var(--mono)',color:'var(--text4)',marginTop:2}}>{timeAgo(a.timestamp)}</div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Build Snippets */}
        <div className="card" style={{padding:18}}>
          <div style={{display:'flex',alignItems:'center',justifyContent:'space-between',marginBottom:14}}>
            <div style={{fontSize:13.5,fontWeight:600,color:'var(--text)'}}>Saved Build Snippets</div>
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