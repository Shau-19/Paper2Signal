import { useState, useRef, useEffect } from 'react'
import { globalChat } from '../api/client'
import ModelSelector from '../pages/ModelSelector'
import ReactMarkdown from 'react-markdown'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { oneDark, oneLight } from 'react-syntax-highlighter/dist/esm/styles/prism'
import { useStore } from '../store/appStore'

const SUGGESTIONS = [
  'Best papers for reducing LLM inference cost?',
  'What hidden gems did The Sentinel find?',
  'Compare LoRA vs QLoRA approaches',
  'Best papers for RAG improvement?',
  "What's overhyped this week?",
]

function CodeBlock({ children, className, theme, addSnippet }) {
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
          onClick={() => addSnippet({ code, lang, source: 'global-chat' })}>
          + Build
        </button>
      </div>
    </div>
  )
}

export default function ChatOverlay({ open, onClose }) {
  const { theme, addSnippet } = useStore()
  const [msgs,      setMsgs]      = useState([{
    role: 'ai',
    content: 'Hi! I have access to the full paper database. Ask me about comparisons, production readiness, hidden gems, or what\'s worth reading this week.\n\n*RAG across all papers · ChromaDB*'
  }])
  const [input,     setInput]     = useState('')
  const [loading,   setLoading]   = useState(false)
  const [history,   setHistory]   = useState([])
  const [modelPref, setModelPref] = useState('auto')
  const bottomRef = useRef(null)

  useEffect(() => {
    if (open) bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [msgs, open])

  const send = async (msg) => {
    if (!msg.trim() || loading) return
    const userMsg = msg.trim()
    setInput('')
    setMsgs(prev => [...prev, { role:'user', content:userMsg }])
    setLoading(true)
    try {
      const res = await globalChat(userMsg, history.slice(-6), 5, modelPref)
      setMsgs(prev => [...prev, { role:'ai', content:res.answer, citations:res.citations }])
      setHistory(prev => [...prev, { role:'user', content:userMsg }, { role:'assistant', content:res.answer }])
    } catch {
      setMsgs(prev => [...prev, { role:'ai', content:'Backend offline — check FastAPI server.' }])
    }
    setLoading(false)
  }

  const components = {
    code({ inline, className, children }) {
      if (inline) return <code style={{ fontFamily:'var(--mono)', fontSize:12, background:'var(--surface2)', padding:'1px 4px', borderRadius:3 }}>{children}</code>
      return <CodeBlock className={className} theme={theme} addSnippet={addSnippet}>{children}</CodeBlock>
    }
  }

  return (
    <>
      <div className={`overlay-backdrop${open ? ' open' : ''}`} onClick={onClose}/>
      <div className={`overlay-panel${open ? ' open' : ''}`} style={{ maxHeight:'82vh' }}>
        <div className="overlay-handle"/>
        <div className="overlay-header">
          <div style={{ flex:1 }}>
            <div className="overlay-title">Global Chat</div>
            <div style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--text4)', marginTop:2, letterSpacing:'.12em', textTransform:'uppercase' }}>
              RAG across all papers · ChromaDB
            </div>
          </div>
          <ModelSelector value={modelPref} onChange={setModelPref}/>
          <button className="overlay-close" onClick={onClose}>
            <svg viewBox="0 0 24 24"><path d="M18 6L6 18M6 6l12 12" stroke="currentColor" fill="none" strokeWidth="2"/></svg>
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex:1, overflowY:'auto', padding:'16px 20px', display:'flex', flexDirection:'column', gap:12 }}>
          {msgs.map((m, i) => (
            <div key={i} className={`chat-msg ${m.role}`}>
              <div className={`chat-avatar ${m.role}`} style={{ width:26, height:26, fontSize:8 }}>{m.role==='user'?'U':'PS'}</div>
              <div className="chat-bubble">
                <ReactMarkdown components={components}>{m.content}</ReactMarkdown>
                {m.citations?.length > 0 && (
                  <div style={{ marginTop:8, display:'flex', flexWrap:'wrap', gap:4 }}>
                    {m.citations.slice(0, 4).map((c, ci) => (
                      <a key={ci} href={c.url||`https://arxiv.org/abs/${c.id}`} target="_blank" rel="noreferrer"
                        style={{ fontFamily:'var(--mono)', fontSize:9, color:'var(--blue)', background:'rgba(91,155,213,.07)', border:'1px solid rgba(91,155,213,.18)', padding:'1px 6px', borderRadius:3, textDecoration:'none' }}>
                        📄 {c.id} {c.score ? `· ${c.score}/10` : ''}
                      </a>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          {loading && (
            <div className="chat-msg ai">
              <div className="chat-avatar ai" style={{ width:26, height:26, fontSize:8 }}>PS</div>
              <div className="chat-bubble"><div className="thinking"><div className="tdot"/><div className="tdot"/><div className="tdot"/></div></div>
            </div>
          )}
          <div ref={bottomRef}/>
        </div>

        {/* Suggestions */}
        <div style={{ padding:'8px 20px 0', display:'flex', gap:5, flexWrap:'wrap', borderTop:'1px solid var(--border)' }}>
          {SUGGESTIONS.map(s => (
            <button key={s} className="chip" style={{ fontSize:11 }} onClick={() => send(s)}>{s}</button>
          ))}
        </div>

        {/* Input */}
        <div style={{ padding:'10px 16px 14px', display:'flex', gap:8 }}>
          <input className="input" value={input} onChange={e => setInput(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && send(input)}
            placeholder="Ask about any paper or technique..."
            style={{ fontSize:13 }}/>
          <button className="btn btn-primary" onClick={() => send(input)} disabled={loading} style={{ flexShrink:0 }}>
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ width:11, height:11 }}>
              <line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/>
            </svg>
          </button>
        </div>
      </div>
    </>
  )
}