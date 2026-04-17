import { useState, useRef, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { deepPaperChat, buildPaperIndex, getPaperSession } from '../api/client'
import { useStore } from '../store/appStore'
import ModelSelector from '../pages/ModelSelector'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'

const INDEXING_STEPS = [
  'Fetching paper PDF from ArXiv...',
  'Extracting paragraphs and equations...',
  'Embedding chunks into local index...',
  'Research session ready',
]

const INTENT_LABELS = {
  implement: { label: 'Code',    color: 'var(--gold-l)',  bg: 'var(--gold-p)',          border: 'var(--gold-bd)' },
  math:      { label: 'Math',    color: 'var(--blue)',    bg: 'rgba(91,155,213,.08)',    border: 'rgba(91,155,213,.2)' },
  explain:   { label: 'Explain', color: 'var(--sg-b)',    bg: 'var(--sg-p)',             border: 'var(--sg-bd)' },
  results:   { label: 'Results', color: 'var(--text3)',   bg: 'var(--surface3)',         border: 'var(--border2)' },
  compare:   { label: 'Compare', color: 'var(--amber)',   bg: 'var(--amber-p)',          border: 'var(--amber-bd)' },
  discuss:   { label: 'Discuss', color: 'var(--text4)',   bg: 'var(--surface2)',         border: 'var(--border)' },
}

// ── Indexing Loader ───────────────────────────────────────────────────────────
function IndexingLoader({ paper, onDone, onError }) {
  const [step, setStep]         = useState(0)
  const [progress, setProgress] = useState(0)

  useEffect(() => {
    const timers = [0, 8000, 22000, 38000].map((t, i) =>
      setTimeout(() => { setStep(i); setProgress((i + 1) * 25) }, t)
    )
    buildPaperIndex(paper.id)
      .then(data => { timers.forEach(clearTimeout); setStep(3); setProgress(100); setTimeout(() => onDone(data), 700) })
      .catch(e => { timers.forEach(clearTimeout); onError(e.response?.data?.detail || 'PDF index failed') })
    return () => timers.forEach(clearTimeout)
  }, [])

  return (
    <div className="indexing-loader">
      <div className="loader-logo">Paper2Signal</div>
      <div style={{ fontFamily:'var(--mono)', fontSize:11, color:'var(--text3)', marginBottom:6 }}>
        Building research session for
      </div>
      <div style={{ fontFamily:'var(--serif)', fontSize:16, color:'var(--text)', maxWidth:360, textAlign:'center', lineHeight:1.4, marginBottom:20 }}>
        {paper?.title?.substring(0, 70)}...
      </div>
      <div className="loader-steps">
        {INDEXING_STEPS.map((s, i) => (
          <div key={i} className={`loader-step ${i < step ? 'done' : i === step ? 'active' : ''}`}>
            <div className="loader-step-dot"/> {s}
          </div>
        ))}
      </div>
      <div className="loader-bar" style={{ marginTop:20 }}>
        <div className="loader-bar-fill" style={{ width:`${progress}%` }}/>
      </div>
      <div style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', marginTop:10, letterSpacing:'.1em' }}>
        Free · Local · Permanent
      </div>
    </div>
  )
}

// ── Code Block ────────────────────────────────────────────────────────────────
function CodeBlock({ children, className, theme, addSnippet, paperTitle }) {
  const lang = /language-(\w+)/.exec(className || '')?.[1] || 'text'
  const code = String(children).replace(/\n$/, '')
  const [copied, setCopied] = useState(false)
  return (
    <div className="code-block-wrapper">
      <SyntaxHighlighter language={lang} style={theme === 'dark' ? oneDark : oneLight}
        customStyle={{ margin:0, borderRadius:'var(--radius)', fontSize:12 }}>
        {code}
      </SyntaxHighlighter>
      <div className="code-block-actions">
        <button className="code-action-btn"
          onClick={() => { navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 2000) }}>
          {copied ? '✓' : 'Copy'}
        </button>
        <button className="code-action-btn add-to-build"
          onClick={() => addSnippet({ code, lang, source: paperTitle || 'paper', addedAt: new Date().toISOString() })}>
          + Build
        </button>
      </div>
    </div>
  )
}

// ── Main ──────────────────────────────────────────────────────────────────────
export default function ReadChat() {
  const navigate = useNavigate()
  const { activePaper, theme, stack, addSnippet } = useStore()
  const [chatMsgs,   setChatMsgs]   = useState([])
  const [input,      setInput]      = useState('')
  const [loading,    setLoading]    = useState(false)
  const [history,    setHistory]    = useState([])
  const [indexed,    setIndexed]    = useState(false)
  const [indexing,   setIndexing]   = useState(false)
  const [indexError, setIndexError] = useState('')
  const [sessionInfo, setSessionInfo] = useState(null)
  const [modelPref,  setModelPref]  = useState('auto')
  const bottomRef = useRef(null)
  const paper = activePaper

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: 'smooth' }) }, [chatMsgs])

  useEffect(() => {
    if (!paper?.id) return
    getPaperSession(paper.id)
      .then(data => {
        const isIndexed = data.indexed && data.doc_id
        setIndexed(isIndexed)
        setSessionInfo(data)
        if (data.messages?.length) {
          const clean = data.messages.filter(m => m.role !== 'system')
          setHistory(clean)
          setChatMsgs(clean.map(m => ({ role: m.role === 'assistant' ? 'ai' : 'user', content: m.content })))
        } else if (isIndexed) {
          setChatMsgs([{ role:'ai', content:`**Session restored** · ${data.sections} sections · ${data.pages} pages\n\nAsk me anything about this paper — methodology, math, code, comparisons.` }])
        } else {
          setChatMsgs([{ role:'ai', content:`I have the abstract and analysis for **${paper.title?.split(':')[0]}**.\n\nFor section-level answers, exact equations, and full code generation, click **Index PDF**.` }])
        }
      })
      .catch(() => setChatMsgs([{ role:'ai', content:`Ready. Ask me about **${paper?.title?.split(':')[0] || 'this paper'}**.` }]))
  }, [paper?.id])

  const send = async () => {
    if (!input.trim() || !paper || loading) return
    const msg = input.trim()
    setInput('')
    setChatMsgs(prev => [...prev, { role:'user', content:msg }])
    setLoading(true)
    const newHistory = [...history, { role:'user', content:msg }]
    try {
      const cleanHistory = history.slice(-8).filter(m => ['user','assistant'].includes(m.role))
      const res = await deepPaperChat(paper.id, msg, cleanHistory, null, modelPref)
      setChatMsgs(prev => [...prev, { role:'ai', content:res.answer, citations:res.citations, intent:res.intent, model:res.model }])
      setHistory([...newHistory, { role:'assistant', content:res.answer }])
    } catch (e) {
      setChatMsgs(prev => [...prev, { role:'ai', content: e.response?.data?.detail ? `Error: ${e.response.data.detail}` : 'Backend offline.' }])
    }
    setLoading(false)
  }

  const components = {
    code({ inline, className, children }) {
      if (inline) return <code style={{ fontFamily:'var(--mono)', fontSize:12, background:'var(--surface2)', padding:'1px 4px', borderRadius:3 }}>{children}</code>
      return <CodeBlock className={className} theme={theme} addSnippet={addSnippet} paperTitle={paper?.title}>{children}</CodeBlock>
    }
  }

  if (!paper) return (
    <div className="page-full" style={{ alignItems:'center', justifyContent:'center' }}>
      <div className="empty">
        <svg viewBox="0 0 24 24"><path d="M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z"/><path d="M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z"/></svg>
        <div className="empty-title">No paper selected</div>
        <div className="empty-sub">Open a paper from Today or Explore</div>
        <button className="btn btn-primary" onClick={() => navigate('/app')}>Go to Today →</button>
      </div>
    </div>
  )

  if (indexing) return <IndexingLoader paper={paper} onDone={data => { setIndexing(false); setIndexed(true); setSessionInfo(data); setHistory([]); setChatMsgs([{ role:'ai', content:`**Research session ready** · ${data.sections} sections · ${data.pages} pages\n\nI've read the full paper. Ask about methodology, equations, code, or how to integrate this with your stack (${stack.slice(0,3).join(', ')}).` }]) }} onError={err => { setIndexing(false); setIndexError(err); setChatMsgs(prev => [...prev, { role:'ai', content:`⚠️ PDF index failed: ${err}\n\nContinuing with abstract context.` }]) }} />

  return (
    <div className="page-full">
      <div style={{ display:'grid', gridTemplateColumns:'1fr 380px', height:'100%', overflow:'hidden' }}>

        {/* PDF */}
        <div style={{ borderRight:'1px solid var(--border)', display:'flex', flexDirection:'column', background:'var(--surface2)', overflow:'hidden' }}>
          <div style={{ padding:'9px 14px', background:'var(--surface)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', gap:9, flexShrink:0 }}>
            <button className="btn btn-ghost btn-sm" onClick={() => navigate(-1)}>← Back</button>
            <div style={{ flex:1, fontSize:12, fontWeight:600, color:'var(--text)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>{paper.title}</div>
            {paper.overall_score && (
              <span style={{ fontFamily:'var(--mono)', fontSize:10, padding:'2px 8px', background:'var(--sg-p)', border:'1px solid var(--sg-bd)', color:'var(--sg-b)', borderRadius:3, flexShrink:0 }}>
                {paper.overall_score?.toFixed(1)} · {paper.action}
              </span>
            )}
            <a href={`https://arxiv.org/abs/${paper.id}`} target="_blank" rel="noreferrer" className="btn btn-ghost btn-sm">ArXiv ↗</a>
          </div>
          <iframe src={`https://arxiv.org/pdf/${paper.id}`} style={{ flex:1, border:'none' }} title={paper.title}/>
        </div>

        {/* Chat */}
        <div style={{ display:'flex', flexDirection:'column', background:'var(--surface)', overflow:'hidden' }}>

          {/* Header */}
          <div style={{ padding:'10px 14px', borderBottom:'1px solid var(--border)', flexShrink:0 }}>
            <div style={{ display:'flex', alignItems:'center', gap:8, marginBottom:4 }}>
              <div style={{ fontSize:12.5, fontWeight:600, color:'var(--text)', flex:1 }}>
                {indexed ? '🔍 Deep Chat' : '📄 Paper Chat'}
              </div>
              <span style={{ fontFamily:'var(--mono)', fontSize:8, padding:'1px 6px', background: indexed ? 'var(--gold-p)' : 'var(--surface2)', border:`1px solid ${indexed ? 'var(--gold-bd)' : 'var(--border)'}`, color: indexed ? 'var(--gold-l)' : 'var(--text4)', borderRadius:3 }}>
                {indexed ? `PDF · ${sessionInfo?.sections ?? '?'} sections` : 'Abstract'}
              </span>
              <ModelSelector value={modelPref} onChange={setModelPref}/>
            </div>
            <div style={{ fontSize:10.5, color:'var(--text3)', overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}>
              {paper.title?.substring(0, 55)}...
            </div>
          </div>

          {/* Index PDF banner */}
          {!indexed && !indexError && (
            <div style={{ padding:'7px 14px', background:'var(--surface2)', borderBottom:'1px solid var(--border)', display:'flex', alignItems:'center', justifyContent:'space-between', flexShrink:0 }}>
              <div style={{ fontSize:11, color:'var(--text3)' }}>Full PDF · exact equations · code generation</div>
              <button className="btn btn-primary btn-sm" onClick={() => setIndexing(true)}>🔍 Index PDF</button>
            </div>
          )}

          {indexError && (
            <div style={{ padding:'6px 14px', background:'var(--red-p)', borderBottom:'1px solid var(--red-bd)', fontSize:11, color:'var(--red)', flexShrink:0 }}>{indexError}</div>
          )}

          {/* Messages */}
          <div style={{ flex:1, overflowY:'auto', padding:'12px 14px', display:'flex', flexDirection:'column', gap:10 }}>
            {chatMsgs.map((m, i) => (
              <div key={i} className={`chat-msg ${m.role}`}>
                <div className={`chat-avatar ${m.role}`} style={{ width:22, height:22, fontSize:8 }}>{m.role === 'user' ? 'U' : 'PS'}</div>
                <div className="chat-bubble" style={{ fontSize:12.5, maxWidth:'90%' }}>
                  {m.role === 'ai' && m.intent && INTENT_LABELS[m.intent] && (
                    <div style={{ marginBottom:6, display:'flex', alignItems:'center', gap:6 }}>
                      <span style={{ fontFamily:'var(--mono)', fontSize:7.5, padding:'1px 6px', background:INTENT_LABELS[m.intent].bg, border:`1px solid ${INTENT_LABELS[m.intent].border}`, color:INTENT_LABELS[m.intent].color, borderRadius:3 }}>
                        {INTENT_LABELS[m.intent].label}
                      </span>
                      {m.model && m.model !== 'auto' && (
                        <span style={{ fontFamily:'var(--mono)', fontSize:7.5, color:'var(--text4)' }}>
                          {m.model === 'openai' ? '🧠' : '🚀'}
                        </span>
                      )}
                    </div>
                  )}
                  <ReactMarkdown components={components}>{m.content}</ReactMarkdown>
                  {m.citations?.length > 0 && (
                    <div style={{ marginTop:6, display:'flex', flexWrap:'wrap', gap:3 }}>
                      {m.citations.map((c, ci) => (
                        <span key={ci} style={{ fontFamily:'var(--mono)', fontSize:8.5, color: c.type==='page' ? 'var(--blue)' : 'var(--gold-l)', background: c.type==='page' ? 'rgba(91,155,213,.08)' : 'var(--gold-p)', border:`1px solid ${c.type==='page' ? 'rgba(91,155,213,.2)' : 'var(--gold-bd)'}`, padding:'1px 5px', borderRadius:3 }}>
                          {c.type === 'page' ? `p.${c.value}` : `§ ${c.value}`}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
            {loading && (
              <div className="chat-msg ai">
                <div className="chat-avatar ai" style={{ width:22, height:22, fontSize:8 }}>PS</div>
                <div className="chat-bubble"><div className="thinking"><div className="tdot"/><div className="tdot"/><div className="tdot"/></div></div>
              </div>
            )}
            <div ref={bottomRef}/>
          </div>

          {/* Suggestions */}
          <div style={{ padding:'6px 12px', display:'flex', gap:5, flexWrap:'wrap', borderTop:'1px solid var(--border)' }}>
            {(indexed ? [
              'Give me the core algorithm',
              'Show implementation code',
              'Explain the key equation',
              'Compare to similar work',
            ] : [
              'What makes this novel?',
              'Key implementation steps',
              'Stack fit for my setup',
              'Compare to alternatives',
            ]).map(s => (
              <div key={s} className="chip" style={{ fontSize:10.5 }} onClick={() => setInput(s)}>{s}</div>
            ))}
          </div>

          {/* Input */}
          <div style={{ padding:'10px 12px', borderTop:'1px solid var(--border)', display:'flex', gap:7, flexShrink:0 }}>
            <input className="input" value={input} onChange={e => setInput(e.target.value)}
              onKeyDown={e => e.key === 'Enter' && send()}
              placeholder={indexed ? 'Ask about any section, equation, or request code...' : 'Ask about this paper...'}
              style={{ fontSize:12 }}/>
            <button className="btn btn-primary btn-sm" onClick={send} disabled={loading} style={{ flexShrink:0, padding:'8px 12px' }}>
              <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" width={11} height={11}>
                <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}