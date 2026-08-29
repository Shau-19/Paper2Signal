import { BrowserRouter, Routes, Route, NavLink, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { useEffect, useState, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useStore } from './store/appStore'
import { getHealth, getJob } from './api/client'
import './styles/global.css'

import Landing  from './pages/Landing'
import Today    from './pages/Today'
import Explore  from './pages/Explore'
import ReadChat from './pages/ReadChat'
import Profile  from './pages/Profile'
import JobsPage from './pages/Jobs'
import AnalyzeOverlay from './pages/Analyze'
import ChatOverlay    from './pages/Chat'

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30000 } }
})

const ICONS = {
  today:    "M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01",
  explore:  "M3 3h7v7H3zM14 3h7v7h-7zM14 14h7v7h-7zM3 14h7v7H3z",
  read:     "M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z",
  read2:    "M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z",
  analyze:  "M11 3a8 8 0 100 16 8 8 0 000-16z",
  analyze2: "m21 21-4.35-4.35",
  chat:     "M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z",
  profile:  "M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2",
  profile2: "M12 3a4 4 0 100 8 4 4 0 000-8z",
  bell:     "M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9M13.73 21a2 2 0 01-3.46 0",
  jobs:     "M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2",
  sun:      "M12 7a5 5 0 100 10 5 5 0 000-10zM12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42",
  moon:     "M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z",
}

function Icon({ d, d2, size = 13 }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"
      style={{ width: size, height: size, flexShrink: 0 }}>
      <path d={d} />{d2 && <path d={d2} />}
    </svg>
  )
}

// ── Global Job Poller (runs app-wide) ─────────────────────────────────────────
function JobPoller() {
  const { activeJobs, updateJob, addNotification, setActivePaper } = useStore()
  const pollRef = useRef(null)

  useEffect(() => {
    const poll = async () => {
      const running = activeJobs.filter(j => j.status === 'pending' || j.status === 'running')
      for (const job of running) {
        try {
          const data = await getJob(job.job_id)
          if (data.status !== job.status) {
            updateJob(job.job_id, { status: data.status, result: data.result, error: data.error })
            if (data.status === 'done') {
              addNotification({
                type:     'job_done',
                title:    job.title,
                paper_id: job.paper_id,
                job_id:   job.job_id,
                result:   data.result,
                message:  'Analysis complete',
              })
            } else if (data.status === 'failed') {
              addNotification({
                type:    'job_failed',
                title:   job.title,
                job_id:  job.job_id,
                message: data.error || 'Analysis failed',
              })
            }
          }
        } catch (e) { /* silent */ }
      }
    }

    if (activeJobs.some(j => j.status === 'pending' || j.status === 'running')) {
      poll()
      pollRef.current = setInterval(poll, 3000)
    }
    return () => clearInterval(pollRef.current)
  }, [activeJobs])

  return null
}

// ── Notification Bell ─────────────────────────────────────────────────────────
function NotificationBell() {
  const navigate  = useNavigate()
  const { notifications, activeJobs, markNotificationRead, setActivePaper } = useStore()
  const [open, setOpen] = useState(false)

  const unread  = notifications.filter(n => !n.read)
  const running = activeJobs.filter(j => j.status === 'pending' || j.status === 'running')

  const handleNotif = (n) => {
    markNotificationRead(n.id)
    if (n.type === 'job_done' && n.result) {
      setActivePaper({ id: n.paper_id, ...n.result })
      navigate('/app/read')
      setOpen(false)
    } else {
      navigate('/app/jobs')
      setOpen(false)
    }
  }

  return (
    <div style={{position:'relative'}}>
      <button
        className="btn-icon"
        onClick={() => setOpen(o => !o)}
        style={{position:'relative'}}
      >
        <Icon d={ICONS.bell} size={14} />
        {/* Badge — unread count */}
        {unread.length > 0 && (
          <span style={{
            position:'absolute',top:0,right:0,
            width:14,height:14,borderRadius:'50%',
            background:'var(--red)',color:'#fff',
            fontSize:8,fontFamily:'var(--mono)',fontWeight:700,
            display:'flex',alignItems:'center',justifyContent:'center',
            transform:'translate(30%,-30%)',
          }}>
            {unread.length > 9 ? '9+' : unread.length}
          </span>
        )}
        {/* Pulse when jobs running */}
        {running.length > 0 && unread.length === 0 && (
          <span style={{
            position:'absolute',top:2,right:2,
            width:6,height:6,borderRadius:'50%',
            background:'var(--amber)',
            animation:'bell-pulse 1.5s ease-in-out infinite',
          }}/>
        )}
      </button>

      {open && (
        <>
          <div style={{position:'fixed',inset:0,zIndex:99}} onClick={() => setOpen(false)}/>
          <div style={{
            position:'absolute',right:0,top:'calc(100% + 8px)',
            width:300,maxHeight:360,overflowY:'auto',
            background:'var(--surface)',border:'1px solid var(--border2)',
            borderRadius:'var(--radius-lg)',boxShadow:'0 8px 32px rgba(0,0,0,.4)',
            zIndex:100,
          }}>
            <div style={{padding:'10px 14px',borderBottom:'1px solid var(--border)',display:'flex',justifyContent:'space-between',alignItems:'center'}}>
              <span style={{fontSize:12,fontWeight:600,color:'var(--text)'}}>Notifications</span>
              <button
                style={{fontSize:10,color:'var(--text4)',background:'none',border:'none',cursor:'pointer'}}
                onClick={() => { navigate('/app/jobs'); setOpen(false) }}
              >
                View all jobs →
              </button>
            </div>

            {running.length > 0 && (
              <div style={{padding:'8px 14px',borderBottom:'1px solid var(--border)',background:'rgba(245,158,11,.06)'}}>
                <div style={{display:'flex',alignItems:'center',gap:6}}>
                  <div style={{width:6,height:6,borderRadius:'50%',background:'var(--amber)',animation:'bell-pulse 1.5s ease-in-out infinite'}}/>
                  <span style={{fontSize:11,color:'var(--amber)',fontFamily:'var(--mono)'}}>
                    {running.length} job{running.length > 1 ? 's' : ''} running
                  </span>
                </div>
                {running.map(j => (
                  <div key={j.job_id} style={{fontSize:11,color:'var(--text3)',marginTop:4,paddingLeft:12,overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap'}}>
                    {j.title?.substring(0, 40)}...
                  </div>
                ))}
              </div>
            )}

            {notifications.length === 0 && running.length === 0 && (
              <div style={{padding:'24px 14px',textAlign:'center',fontSize:12,color:'var(--text4)'}}>
                No notifications yet
              </div>
            )}

            {notifications.slice(0, 8).map(n => (
              <div
                key={n.id}
                onClick={() => handleNotif(n)}
                style={{
                  padding:'10px 14px',borderBottom:'1px solid var(--border)',
                  cursor:'pointer',background: n.read ? 'transparent' : 'rgba(91,155,213,.05)',
                  transition:'background .15s',
                }}
                onMouseEnter={e => e.currentTarget.style.background = 'var(--surface2)'}
                onMouseLeave={e => e.currentTarget.style.background = n.read ? 'transparent' : 'rgba(91,155,213,.05)'}
              >
                <div style={{display:'flex',alignItems:'center',gap:6,marginBottom:3}}>
                  <span style={{fontSize:12}}>
                    {n.type === 'job_done' ? '✅' : n.type === 'job_failed' ? '❌' : '🔄'}
                  </span>
                  <span style={{fontSize:12,fontWeight:500,color:'var(--text)',overflow:'hidden',textOverflow:'ellipsis',whiteSpace:'nowrap',flex:1}}>
                    {n.title?.substring(0, 35)}...
                  </span>
                  {!n.read && <div style={{width:6,height:6,borderRadius:'50%',background:'var(--blue)',flexShrink:0}}/>}
                </div>
                <div style={{fontSize:11,color:'var(--text4)',paddingLeft:18}}>{n.message}</div>
              </div>
            ))}
          </div>
        </>
      )}

      <style>{`@keyframes bell-pulse { 0%,100%{opacity:1} 50%{opacity:.3} }`}</style>
    </div>
  )
}

// ── Top Nav ───────────────────────────────────────────────────────────────────
function TopNav({ onAnalyze, onChat, paperCount }) {
  const { theme, toggleTheme, activeJobs } = useStore()
  const navigate  = useNavigate()
  const location  = useLocation()
  if (location.pathname === '/') return null

  const runningJobs = activeJobs.filter(j => j.status === 'pending' || j.status === 'running')

  return (
    <nav className="topnav">
      <a href="/app" className="topnav-brand" onClick={e => { e.preventDefault(); navigate('/app') }}>
        <div className="topnav-mark">
          <svg viewBox="0 0 24 24">
            <path d="M12 2L2 7l10 5 10-5-10-5z" stroke="currentColor" fill="none" strokeWidth="2"/>
            <path d="M2 17l10 5 10-5" stroke="currentColor" fill="none" strokeWidth="2"/>
            <path d="M2 12l10 5 10-5" stroke="currentColor" fill="none" strokeWidth="2"/>
          </svg>
        </div>
        <span className="topnav-name">Paper2Signal</span>
      </a>

      <div className="topnav-links">
        <NavLink to="/app" end className={({isActive}) => `topnav-link${isActive?' active':''}`}>
          <Icon d={ICONS.today} /> Today
          {paperCount > 0 && (
            <span style={{fontFamily:'var(--mono)',fontSize:8,background:'var(--sg-p)',border:'1px solid var(--sg-bd)',color:'var(--sg-b)',padding:'1px 5px',borderRadius:3}}>
              {paperCount}
            </span>
          )}
        </NavLink>
        <NavLink to="/app/explore" className={({isActive}) => `topnav-link${isActive?' active':''}`}>
          <Icon d={ICONS.explore} /> Explore
        </NavLink>
        <NavLink to="/app/read" className={({isActive}) => `topnav-link${isActive?' active':''}`}>
          <Icon d={ICONS.read} d2={ICONS.read2} /> Read &amp; Chat
        </NavLink>
        {/* Jobs link — shows when there are active jobs */}
        <NavLink to="/app/jobs" className={({isActive}) => `topnav-link${isActive?' active':''}`}>
          <Icon d={ICONS.jobs} />
          Jobs
          {runningJobs.length > 0 && (
            <span style={{
              fontFamily:'var(--mono)',fontSize:8,
              background:'rgba(245,158,11,.15)',border:'1px solid rgba(245,158,11,.3)',
              color:'var(--amber)',padding:'1px 5px',borderRadius:3,
              animation:'bell-pulse 1.5s ease-in-out infinite',
            }}>
              {runningJobs.length}
            </span>
          )}
        </NavLink>
      </div>

      <div className="topnav-right">
        <button className="topnav-link" onClick={onAnalyze}>
          <Icon d={ICONS.analyze} d2={ICONS.analyze2} /> Analyze
        </button>
        <button className="topnav-link" onClick={onChat}>
          <Icon d={ICONS.chat} /> Global Chat
        </button>
        <NotificationBell />
        <button className="btn-icon" onClick={toggleTheme}>
          <Icon d={theme === 'dark' ? ICONS.sun : ICONS.moon} size={14} />
        </button>
        <NavLink to="/app/profile" className={({isActive}) => `topnav-link${isActive?' active':''}`} style={{padding:'6px 9px'}}>
          <Icon d={ICONS.profile} d2={ICONS.profile2} />
        </NavLink>
      </div>
    </nav>
  )
}

// ── App Shell ─────────────────────────────────────────────────────────────────
function AppShell() {
  const { theme } = useStore()
  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const [chatOpen,    setChatOpen]    = useState(false)
  const location = useLocation()
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 60000 })

  // Support opening analyze from navigation state (e.g. from Jobs page)
  useEffect(() => {
    if (location.state?.openAnalyze) {
      setAnalyzeOpen(true)
      window.history.replaceState({}, '')
    }
  }, [location.state])

  useEffect(() => {
    document.documentElement.setAttribute('data-theme', theme)
  }, [theme])

  useEffect(() => {
    const h = (e) => {
      if (e.key === 'Escape') { setAnalyzeOpen(false); setChatOpen(false) }
    }
    window.addEventListener('keydown', h)
    return () => window.removeEventListener('keydown', h)
  }, [])

  return (
    <>
      <JobPoller />
      <TopNav
        onAnalyze={() => { setChatOpen(false); setAnalyzeOpen(true) }}
        onChat={() => { setAnalyzeOpen(false); setChatOpen(true) }}
        paperCount={health?.papers_count}
      />
      <div className="app-root">
        <Routes>
          <Route index          element={<Today />} />
          <Route path="explore" element={<Explore />} />
          <Route path="read"    element={<ReadChat />} />
          <Route path="profile" element={<Profile />} />
          <Route path="jobs"    element={<JobsPage />} />
          <Route path="*"       element={<Navigate to="/app" replace />} />
        </Routes>
      </div>
      <AnalyzeOverlay open={analyzeOpen} onClose={() => setAnalyzeOpen(false)} />
      <ChatOverlay    open={chatOpen}    onClose={() => setChatOpen(false)} />
    </>
  )
}

function LandingWrapper() {
  const { theme } = useStore()
  useEffect(() => {
    document.documentElement.setAttribute('data-theme', 'dark')
    return () => document.documentElement.setAttribute('data-theme', theme)
  }, [theme])
  return <Landing />
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/"      element={<LandingWrapper />} />
          <Route path="/app/*" element={<AppShell />} />
          <Route path="*"      element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  )
}