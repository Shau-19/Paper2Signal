import { BrowserRouter, Routes, Route, NavLink, useLocation, Navigate, useNavigate } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useStore } from './store/appStore'
import { getHealth } from './api/client'
import './styles/global.css'

import Landing from './pages/Landing'
import Today from './pages/Today'
import Explore from './pages/Explore'
import ReadChat from './pages/ReadChat'
import Profile from './pages/Profile'
import AnalyzeOverlay from './pages/Analyze'
import ChatOverlay from './pages/Chat'

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

function TopNav({ onAnalyze, onChat, paperCount }) {
  const { theme, toggleTheme } = useStore()
  const navigate = useNavigate()
  const location = useLocation()
  if (location.pathname === '/') return null

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
      </div>

      <div className="topnav-right">
        <button className="topnav-link" onClick={onAnalyze}>
          <Icon d={ICONS.analyze} d2={ICONS.analyze2} /> Analyze
        </button>
        <button className="topnav-link" onClick={onChat}>
          <Icon d={ICONS.chat} /> Global Chat
        </button>
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

function AppShell() {
  const { theme } = useStore()
  const [analyzeOpen, setAnalyzeOpen] = useState(false)
  const [chatOpen, setChatOpen] = useState(false)
  const { data: health } = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 60000 })

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