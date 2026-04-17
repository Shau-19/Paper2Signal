import { useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'

export default function Landing() {
  const navigate = useNavigate()
  const introRef = useRef(null)
  const mainRef = useRef(null)
  const introSkippedRef = useRef(false)

  useEffect(() => {
    // ── Intro sequence ──────────────────────────────────────────
    const QUOTES = [
      { t: "The good thing about science is that it's true whether or not you believe in it.", a: "Neil deGrasse Tyson" },
      { t: "In theory there is no difference between theory and practice. In practice there is.", a: "Yogi Berra" },
      { t: "A paper that cannot be reproduced is not a result — it's a rumour.", a: "Reproducibility Crisis, 2016" },
      { t: "The most damaging phrase in the language is 'we've always done it this way.'", a: "Grace Hopper" },
    ]
    const q = QUOTES[Math.floor(Math.random() * QUOTES.length)]
    document.getElementById('lp-qText').textContent = q.t
    document.getElementById('lp-qAttr').textContent = '— ' + q.a

    const bar = document.getElementById('lp-introBar')

    function sleep(ms) { return new Promise(r => setTimeout(r, ms)) }

    function finishIntro() {
      introSkippedRef.current = true
      const intro = document.getElementById('lp-intro')
      if (intro) intro.style.opacity = '0'
      setTimeout(() => {
        if (intro) intro.style.display = 'none'
        const main = document.getElementById('lp-main')
        if (main) main.style.opacity = '1'
        animateDimBars()
        setTimeout(startReveal, 100)
      }, 950)
    }

    async function runIntro() {
      bar.style.transitionDuration = '0s'
      bar.style.width = '0%'
      await sleep(50)
      bar.style.transitionDuration = '2.8s'
      bar.style.width = '40%'

      await sleep(300)
      document.getElementById('lp-stage-quote').classList.add('show')
      await sleep(2900)
      if (introSkippedRef.current) return
      document.getElementById('lp-stage-quote').classList.remove('show')
      await sleep(700)
      if (introSkippedRef.current) return

      bar.style.transitionDuration = '1.8s'
      bar.style.width = '80%'
      document.getElementById('lp-stage-logo').classList.add('show')
      await sleep(450)
      document.getElementById('lp-introWord').classList.add('shine')
      await sleep(1600)
      if (introSkippedRef.current) return

      bar.style.transitionDuration = '.4s'
      bar.style.width = '100%'
      await sleep(500)
      finishIntro()
    }

    function animateDimBars() {
      setTimeout(() => {
        document.getElementById('lp-df1').style.width = '90%'
        document.getElementById('lp-df2').style.width = '80%'
        document.getElementById('lp-df3').style.width = '85%'
        document.getElementById('lp-df4').style.width = '70%'
      }, 400)
    }

    function startReveal() {
      const obs = new IntersectionObserver(entries => {
        entries.forEach(e => {
          if (e.isIntersecting) { e.target.classList.add('in'); obs.unobserve(e.target) }
        })
      }, { threshold: 0.1, rootMargin: '0px 0px -36px 0px' })
      document.querySelectorAll('.lp-reveal').forEach(el => obs.observe(el))
    }

    // Demo card rotation
    const demos = [
      { title: 'FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision', score: '8.5', vc: 'lp-vb-adopt', vl: 'Adopt', vt: 'Drop-in for HuggingFace + vLLM. 1.2k stars. Use in production this week.', dims: ['90%', '80%', '85%', '70%'], color: '#3dba72' },
      { title: 'SpinQuant: LLM Quantization with Learned Rotations for 4-bit Inference', score: '7.8', vc: 'lp-vb-adopt', vl: 'Adopt · 💎 Gem', vt: '3.7× memory reduction. The Sentinel flagged as hidden gem — low hype, high value.', dims: ['85%', '90%', '88%', '65%'], color: '#b8955a' },
      { title: 'ColPali: Document Retrieval with Vision Language Models', score: '6.5', vc: 'lp-vb-expt', vl: 'Experiment', vt: 'Worth 2-3 days of engineering time. Promising but not production-ready yet.', dims: ['75%', '55%', '60%', '40%'], color: '#c8a96e' },
    ]
    let di = 0
    const demoInterval = setInterval(() => {
      if (!document.getElementById('lp-main')?.style.opacity === '1') return
      di = (di + 1) % demos.length
      const d = demos[di]
      const dTitle = document.getElementById('lp-dTitle')
      if (!dTitle) return
      dTitle.textContent = d.title
      document.getElementById('lp-dScore').textContent = d.score
      const verdict = document.getElementById('lp-dVerdict')
      verdict.textContent = d.vl
      verdict.className = 'lp-vbadge ' + d.vc
      document.getElementById('lp-dVText').textContent = d.vt
      ;['lp-df1', 'lp-df2', 'lp-df3', 'lp-df4'].forEach((id, i) => {
        const el = document.getElementById(id)
        el.style.width = '0%'; el.style.background = d.color
        setTimeout(() => el.style.width = d.dims[i], 120)
      })
    }, 8000)

    // Smooth scroll for anchor links
    document.querySelectorAll('a[href^="#"]').forEach(a => {
      a.addEventListener('click', e => {
        const target = document.querySelector(a.getAttribute('href'))
        if (target) { e.preventDefault(); target.scrollIntoView({ behavior: 'smooth' }) }
      })
    })

    runIntro()

    return () => {
      clearInterval(demoInterval)
      // Clean up body overflow when leaving landing
      document.body.style.overflow = ''
    }
  }, [])

  const handleSkip = () => {
    if (introSkippedRef.current) return
    const intro = document.getElementById('lp-intro')
    if (intro) intro.style.opacity = '0'
    setTimeout(() => {
      if (intro) intro.style.display = 'none'
      const main = document.getElementById('lp-main')
      if (main) main.style.opacity = '1'
      setTimeout(() => {
        document.querySelectorAll('.lp-reveal').forEach(el => el.classList.add('in'))
      }, 100)
    }, 950)
    introSkippedRef.current = true
  }

  const handleOpenApp = (e) => {
    e.preventDefault()
    navigate('/app')
  }

  const toggleTag = (e) => {
    e.currentTarget.classList.toggle('lp-on')
    const sel = [...document.querySelectorAll('.lp-sp-t.lp-on')].map(t => t.textContent)
    localStorage.setItem('ps-stack', JSON.stringify(sel))
  }

  return (
    <>
      <style>{`
        /* ── Landing page scoped styles (prefixed lp-) ── */
        .lp-body { font-family: 'Syne', sans-serif; background: #09090a; color: #f8f5ef; overflow-x: hidden; }

        /* Noise overlay */
        .lp-noise { position: fixed; inset: 0; background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='.85' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='.035'/%3E%3C/svg%3E"); pointer-events: none; z-index: 9999; opacity: .5; }

        /* INTRO */
        #lp-intro { position: fixed; inset: 0; z-index: 8000; background: #09090a; display: flex; flex-direction: column; align-items: center; justify-content: center; cursor: pointer; transition: opacity .9s ease; overflow: hidden; }
        #lp-intro::before { content: ''; position: absolute; inset: 0; background: repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(255,255,255,.012) 2px,rgba(255,255,255,.012) 3px); pointer-events: none; z-index: 1; }
        #lp-intro::after { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse at center,transparent 30%,rgba(0,0,0,.75) 100%); pointer-events: none; z-index: 1; }
        .lp-intro-glow { position: absolute; width: 600px; height: 600px; background: radial-gradient(circle,rgba(184,149,90,.07) 0%,transparent 70%); border-radius: 50%; pointer-events: none; animation: lp-glowPulse 4s ease-in-out infinite; }
        @keyframes lp-glowPulse { 0%,100%{transform:scale(1);opacity:.6}50%{transform:scale(1.15);opacity:1} }

        #lp-stage-quote { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; padding: 3rem; z-index: 2; opacity: 0; transition: opacity .8s ease; text-align: center; }
        #lp-stage-quote.show { opacity: 1; }
        .lp-q-mark { font-family: 'Playfair Display', serif; font-size: 60px; color: rgba(255,255,255,.06); line-height: 1; margin-bottom: 20px; }
        .lp-q-text { font-family: 'Playfair Display', serif; font-size: clamp(1.1rem,2.4vw,1.55rem); font-style: italic; color: rgba(248,245,239,.65); max-width: 580px; line-height: 1.8; margin-bottom: 18px; letter-spacing: .01em; }
        .lp-q-attr { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: rgba(248,245,239,.2); }

        #lp-stage-logo { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; z-index: 2; opacity: 0; transition: opacity .8s ease; }
        #lp-stage-logo.show { opacity: 1; }
        .lp-intro-wordmark { font-family: 'Playfair Display', serif; font-size: clamp(3.5rem,9vw,7.5rem); font-weight: 400; color: #fff; letter-spacing: -.025em; position: relative; overflow: hidden; line-height: 1; }
        .lp-intro-wordmark::after { content: ''; position: absolute; inset: 0; background: linear-gradient(105deg,transparent 20%,rgba(255,255,255,.5) 50%,transparent 80%); transform: translateX(-120%); transition: transform 1.1s ease; }
        .lp-intro-wordmark.shine::after { transform: translateX(120%); }
        .lp-intro-tagline { font-family: 'JetBrains Mono', monospace; font-size: 10px; letter-spacing: .28em; text-transform: uppercase; color: rgba(255,255,255,.2); margin-top: 18px; }
        .lp-intro-models { display: flex; align-items: center; gap: 18px; margin-top: 32px; opacity: 0; transition: opacity .6s ease .3s; }
        #lp-stage-logo.show .lp-intro-models { opacity: 1; }
        .lp-im-item { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.18); display: flex; align-items: center; gap: 7px; }
        .lp-im-dot { width: 4px; height: 4px; border-radius: 50%; background: rgba(184,149,90,.4); }
        .lp-intro-skip { position: absolute; bottom: 28px; right: 36px; z-index: 3; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: rgba(255,255,255,.18); transition: color .2s; }
        #lp-intro:hover .lp-intro-skip { color: rgba(255,255,255,.4); }
        .lp-intro-bar { position: absolute; bottom: 0; left: 0; height: 1px; background: #b8955a; width: 0%; transition: width linear; z-index: 3; opacity: .4; }

        /* MAIN */
        #lp-main { opacity: 0; transition: opacity .8s ease; }

        /* NAV */
        .lp-nav { position: fixed; top: 0; left: 0; right: 0; z-index: 700; padding: 18px 52px; display: flex; align-items: center; justify-content: space-between; background: rgba(9,9,10,.82); backdrop-filter: blur(20px); border-bottom: 1px solid rgba(255,255,255,.05); }
        .lp-logo { display: flex; align-items: center; gap: 10px; text-decoration: none; }
        .lp-logo-mark { width: 30px; height: 30px; border: 1.5px solid #b8955a; display: flex; align-items: center; justify-content: center; }
        .lp-logo-mark svg { width: 13px; height: 13px; stroke: #b8955a; fill: none; stroke-width: 2; }
        .lp-logo-name { font-family: 'Playfair Display', serif; font-size: 16px; color: #f8f5ef; }
        .lp-nav-r { display: flex; align-items: center; gap: 28px; }
        .lp-nav-a { font-size: 11px; font-weight: 500; letter-spacing: .1em; text-transform: uppercase; color: #7a7870; text-decoration: none; transition: color .2s; }
        .lp-nav-a:hover { color: #f8f5ef; }
        .lp-nav-btn { padding: 9px 22px; border: 1.5px solid rgba(184,149,90,.45); color: #b8955a; font-family: 'Syne', sans-serif; font-size: 10px; font-weight: 700; letter-spacing: .14em; text-transform: uppercase; text-decoration: none; transition: all .2s; background: transparent; cursor: pointer; }
        .lp-nav-btn:hover { background: #b8955a; color: #09090a; }

        /* HERO */
        .lp-hero { min-height: 100vh; display: flex; flex-direction: column; justify-content: center; padding: 140px 52px 100px; position: relative; overflow: hidden; }
        .lp-hero-bg { position: absolute; inset: 0; background: radial-gradient(ellipse 70% 60% at 20% 50%,rgba(184,149,90,.065) 0%,transparent 60%),radial-gradient(ellipse 50% 55% at 85% 75%,rgba(46,158,96,.04) 0%,transparent 55%); pointer-events: none; }
        .lp-hero-gl { position: absolute; inset: 0; background-image: linear-gradient(rgba(255,255,255,.018) 1px,transparent 1px),linear-gradient(90deg,rgba(255,255,255,.018) 1px,transparent 1px); background-size: 72px 72px; mask-image: radial-gradient(ellipse at 30% 50%,black 10%,transparent 68%); pointer-events: none; }
        .lp-hero-badge { display: inline-flex; align-items: center; gap: 9px; padding: 6px 14px; border: 1px solid rgba(46,158,96,.3); background: rgba(46,158,96,.07); margin-bottom: 28px; opacity: 0; animation: lp-slideUp .7s ease .1s both; }
        .lp-bdot { width: 5px; height: 5px; border-radius: 50%; background: #3dba72; animation: lp-pulse 2s ease infinite; }
        @keyframes lp-pulse { 0%,100%{opacity:1}50%{opacity:.3} }
        .lp-btxt { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .18em; text-transform: uppercase; color: #3dba72; }
        .lp-hero-h1 { font-family: 'Playfair Display', serif; font-size: clamp(3rem,6vw,5.5rem); font-weight: 600; line-height: 1.06; letter-spacing: -.03em; margin-bottom: 26px; opacity: 0; animation: lp-slideUp .8s ease .25s both; }
        .lp-hero-h1 em { font-style: italic; color: #d4b07a; }
        .lp-hero-p { font-size: 16px; line-height: 2; color: rgba(248,245,239,.55); max-width: 640px; margin-bottom: 42px; opacity: 0; animation: lp-slideUp .8s ease .4s both; }
        .lp-hero-p strong { color: #f8f5ef; font-weight: 600; }
        .lp-hero-actions { display: flex; align-items: center; gap: 14px; flex-wrap: wrap; opacity: 0; animation: lp-slideUp .8s ease .52s both; }
        .lp-btn-hero { padding: 13px 30px; background: #b8955a; color: #09090a; font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; border: none; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 8px; transition: all .22s; }
        .lp-btn-hero:hover { background: #d4b07a; transform: translateY(-2px); box-shadow: 0 8px 24px rgba(184,149,90,.25); }
        .lp-btn-hero svg { width: 12px; height: 12px; stroke: currentColor; fill: none; stroke-width: 2.5; }
        .lp-btn-ghost { padding: 13px 24px; background: transparent; color: rgba(248,245,239,.5); font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 500; letter-spacing: .1em; text-transform: uppercase; border: 1px solid rgba(255,255,255,.1); cursor: pointer; text-decoration: none; transition: all .2s; }
        .lp-btn-ghost:hover { color: #f8f5ef; border-color: rgba(255,255,255,.22); }
        .lp-hero-trust { margin-top: 36px; display: flex; align-items: center; gap: 16px; flex-wrap: wrap; opacity: 0; animation: lp-slideUp .8s ease .66s both; }
        .lp-ts { width: 1px; height: 22px; background: rgba(255,255,255,.08); }
        .lp-ti { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: .1em; text-transform: uppercase; color: #7a7870; }
        .lp-ti strong { color: rgba(248,245,239,.45); font-weight: 500; }
        @keyframes lp-slideUp { from{opacity:0;transform:translateY(20px)}to{opacity:1;transform:translateY(0)} }

        /* DARK→LIGHT transition */
        .lp-dark-to-light { background: linear-gradient(to bottom,#09090a 0%,#f8f5ef 100%); height: 140px; }

        /* SPLIT */
        .lp-split-sec { background: #f8f5ef; padding: 0 52px 100px; }
        .lp-split-label-row { padding: 56px 0 40px; display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 16px; border-bottom: 1px solid #e5e0d5; }
        .lp-split-headline { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,3.5vw,3.2rem); font-weight: 600; color: #09090a; letter-spacing: -.03em; line-height: 1.1; max-width: 640px; }
        .lp-split-headline em { font-style: italic; color: #b8955a; }
        .lp-split-sub { font-size: 13px; color: #55544f; line-height: 1.8; max-width: 340px; text-align: right; }
        .lp-split-frame { display: grid; grid-template-columns: 1fr 400px; height: 580px; border: 1px solid #e5e0d5; border-top: none; overflow: hidden; }
        .lp-split-pdf { border-right: 1px solid #e5e0d5; background: #f0ece3; display: flex; flex-direction: column; overflow: hidden; }
        .lp-split-pdf-bar { padding: 10px 16px; background: #f8f5ef; border-bottom: 1px solid #e5e0d5; display: flex; align-items: center; gap: 10px; flex-shrink: 0; }
        .lp-spb-dots { display: flex; gap: 5px; }
        .lp-spb-dot { width: 9px; height: 9px; border-radius: 50%; }
        .lp-spb-dot.r { background: #ff6058; } .lp-spb-dot.y { background: #febc2e; } .lp-spb-dot.g { background: #28c840; }
        .lp-spb-title { font-family: 'JetBrains Mono', monospace; font-size: 9.5px; color: #55544f; letter-spacing: .06em; flex: 1; text-align: center; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .lp-spb-score { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 2px 8px; background: rgba(46,158,96,.1); border: 1px solid rgba(46,158,96,.2); color: #2e9e60; flex-shrink: 0; }
        .lp-pdf-mock { flex: 1; overflow: hidden; padding: 28px 32px; display: flex; flex-direction: column; gap: 14px; }
        .lp-pm-authors { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #55544f; letter-spacing: .06em; text-align: center; }
        .lp-pm-title-big { font-family: 'Playfair Display', serif; font-size: 16px; font-weight: 600; color: #09090a; text-align: center; line-height: 1.4; margin-bottom: 4px; }
        .lp-pm-divider { height: 1px; background: #e5e0d5; margin: 6px 0; }
        .lp-pm-section-lbl { font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 600; letter-spacing: .14em; text-transform: uppercase; color: #09090a; margin-bottom: 6px; }
        .lp-pm-body { display: flex; flex-direction: column; gap: 5px; }
        .lp-pm-line { height: 8px; background: #e5e0d5; border-radius: 2px; }
        .lp-pm-line.short { width: 70%; } .lp-pm-line.med { width: 85%; } .lp-pm-line.full { width: 100%; } .lp-pm-line.half { width: 50%; }
        .lp-pm-highlight { background: rgba(184,149,90,.12); border: 1px solid rgba(184,149,90,.2); padding: 8px 12px; margin: 6px 0; }
        .lp-pm-highlight-line { height: 8px; background: rgba(184,149,90,.25); border-radius: 2px; margin-bottom: 4px; }
        .lp-pm-highlight-line:last-child { width: 60%; margin-bottom: 0; }
        .lp-pm-formula { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #55544f; text-align: center; padding: 8px; background: #f8f5ef; border: 1px solid #e5e0d5; }
        .lp-pdf-page-bar { padding: 8px 16px; background: #f8f5ef; border-top: 1px solid #e5e0d5; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
        .lp-ppb-nav { display: flex; align-items: center; gap: 8px; font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #55544f; }
        .lp-ppb-btn { width: 18px; height: 18px; border: 1px solid #e5e0d5; display: flex; align-items: center; justify-content: center; cursor: default; }
        .lp-ppb-btn svg { width: 9px; height: 9px; stroke: #55544f; fill: none; stroke-width: 2; }
        .lp-ppb-arxiv { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #b8955a; letter-spacing: .08em; }
        .lp-split-chat { display: flex; flex-direction: column; background: #f8f5ef; }
        .lp-split-chat-head { padding: 12px 16px; background: #f8f5ef; border-bottom: 1px solid #e5e0d5; flex-shrink: 0; }
        .lp-sch-top { display: flex; align-items: center; gap: 8px; margin-bottom: 3px; }
        .lp-sch-icon { width: 20px; height: 20px; background: rgba(46,158,96,.1); border: 1px solid rgba(46,158,96,.2); display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .lp-sch-icon svg { width: 9px; height: 9px; stroke: #2e9e60; fill: none; stroke-width: 2; }
        .lp-sch-label { font-size: 11.5px; font-weight: 600; color: #09090a; }
        .lp-sch-model { font-family: 'JetBrains Mono', monospace; font-size: 8px; color: #55544f; letter-spacing: .1em; }
        .lp-split-chat-msgs { flex: 1; overflow-y: auto; padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; }
        .lp-scm { display: flex; gap: 8px; align-items: flex-start; }
        .lp-scm.u { flex-direction: row-reverse; }
        .lp-scm-av { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 600; flex-shrink: 0; }
        .lp-scm-av.ai { background: #09090a; color: #f8f5ef; }
        .lp-scm-av.u { background: #e5e0d5; color: #55544f; }
        .lp-scm-bbl { padding: 9px 12px; font-size: 12px; line-height: 1.65; max-width: 90%; }
        .lp-scm.ai .lp-scm-bbl { background: #f0ece3; border: 1px solid #e5e0d5; color: #55544f; }
        .lp-scm.u .lp-scm-bbl { background: rgba(46,158,96,.07); border: 1px solid rgba(46,158,96,.18); color: #09090a; }
        .lp-scm-bbl strong { color: #09090a; font-weight: 600; }
        .lp-split-chat-inp { padding: 11px 14px; border-top: 1px solid #e5e0d5; display: flex; gap: 8px; flex-shrink: 0; background: #f8f5ef; }
        .lp-sci { flex: 1; background: #f0ece3; border: 1px solid #e5e0d5; padding: 9px 12px; font-family: 'Syne', sans-serif; font-size: 12px; color: #55544f; }
        .lp-sci-btn { width: 36px; height: 36px; background: #09090a; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .lp-sci-btn svg { width: 12px; height: 12px; stroke: #f8f5ef; fill: none; stroke-width: 2; }
        .lp-split-suggestions { padding: 0 14px 10px; display: flex; gap: 6px; flex-wrap: wrap; }
        .lp-ssugg { padding: 4px 10px; font-size: 10.5px; font-family: 'Syne', sans-serif; border: 1px solid #e5e0d5; background: #f0ece3; color: #55544f; cursor: default; transition: all .15s; }
        .lp-ssugg:hover { border-color: #cdc9bd; color: #09090a; }

        /* SCORE CARD */
        .lp-scorecard-sec { background: #111113; padding: 80px 52px; position: relative; overflow: hidden; }
        .lp-scorecard-sec::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 55% 60% at 75% 50%,rgba(184,149,90,.05) 0%,transparent 65%); pointer-events: none; }
        .lp-sc-inner { max-width: 1100px; margin: 0 auto; display: grid; grid-template-columns: 1fr 380px; gap: 64px; align-items: start; }
        .lp-sc-copy-h { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,3.5vw,3.2rem); font-weight: 600; color: #f8f5ef; letter-spacing: -.03em; line-height: 1.1; margin-bottom: 18px; }
        .lp-sc-copy-h em { font-style: italic; color: #d4b07a; }
        .lp-sc-copy-p { font-size: 14px; color: #7a7870; line-height: 1.85; margin-bottom: 28px; }
        .lp-sc-dims-explain { display: flex; flex-direction: column; gap: 10px; }
        .lp-scd { display: flex; align-items: flex-start; gap: 12px; }
        .lp-scd-num { font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #b8955a; width: 18px; flex-shrink: 0; margin-top: 1px; }
        .lp-scd-text { font-size: 13px; color: #7a7870; line-height: 1.65; }
        .lp-scd-text strong { color: rgba(248,245,239,.65); font-weight: 600; }
        .lp-score-demo { width: 100%; max-width: 400px; background: rgba(255,255,255,.032); border: 1px solid rgba(255,255,255,.08); overflow: hidden; }
        .lp-sd-bar { height: 2px; background: linear-gradient(90deg,#b8955a,#3dba72); opacity: .35; }
        .lp-sd-head { padding: 16px 20px; border-bottom: 1px solid rgba(255,255,255,.06); display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; }
        .lp-sd-title { font-size: 12px; font-weight: 500; color: #f8f5ef; line-height: 1.4; flex: 1; }
        .lp-sd-score-box { flex-shrink: 0; text-align: center; }
        .lp-sd-num { font-family: 'Playfair Display', serif; font-size: 34px; font-weight: 600; color: #3dba72; line-height: 1; }
        .lp-sd-slbl { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: #2e9e60; margin-top: 2px; }
        .lp-sd-verdict { padding: 10px 20px; border-bottom: 1px solid rgba(255,255,255,.06); display: flex; align-items: center; gap: 10px; }
        .lp-vbadge { padding: 4px 10px; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .08em; text-transform: uppercase; flex-shrink: 0; }
        .lp-vb-adopt { background: rgba(46,158,96,.12); border: 1px solid rgba(46,158,96,.28); color: #3dba72; }
        .lp-vb-expt { background: rgba(192,120,32,.1); border: 1px solid rgba(192,120,32,.28); color: #e09535; }
        .lp-vb-watch { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.1); color: #7a7870; }
        .lp-vtext { font-size: 11px; color: rgba(248,245,239,.48); line-height: 1.55; flex: 1; }
        .lp-sd-dims { padding: 14px 20px; display: flex; flex-direction: column; gap: 8px; border-bottom: 1px solid rgba(255,255,255,.06); }
        .lp-dr { display: flex; align-items: center; gap: 10px; }
        .lp-dl { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #7a7870; width: 90px; flex-shrink: 0; }
        .lp-dt { flex: 1; height: 2px; background: rgba(255,255,255,.07); }
        .lp-df { height: 2px; transition: width 1.1s cubic-bezier(.4,0,.2,1); }
        .lp-dv { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #7a7870; width: 20px; text-align: right; flex-shrink: 0; }
        .lp-sd-chat { padding: 14px 20px; display: flex; flex-direction: column; gap: 8px; }
        .lp-sc-lbl { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .14em; text-transform: uppercase; color: #3a3936; margin-bottom: 2px; }
        .lp-sc-msg { padding: 8px 11px; font-size: 11px; line-height: 1.6; border: 1px solid rgba(255,255,255,.06); }
        .lp-sc-msg.ai { background: rgba(255,255,255,.025); color: rgba(248,245,239,.6); display: flex; align-items: center; justify-content: space-between; }

        /* SHARED SECTION */
        .lp-sec-lbl { font-family: 'JetBrains Mono', monospace; font-size: 11px; letter-spacing: .18em; text-transform: uppercase; color: #b8955a; margin-bottom: 18px; display: flex; align-items: center; gap: 12px; }
        .lp-sec-lbl::before { content: ''; flex: 0 0 28px; height: 1px; background: #b8955a; opacity: .4; }
        .lp-sec-lbl.light { color: #55544f; }
        .lp-sec-lbl.light::before { background: #e5e0d5; }
        .lp-section-w { max-width: 1100px; margin: 0 auto; }

        /* WHO IT'S FOR */
        .lp-for-sec { background: #f8f5ef; padding: 100px 52px; }
        .lp-for-h { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,4vw,3.6rem); font-weight: 600; color: #09090a; line-height: 1.1; letter-spacing: -.03em; max-width: 700px; margin-bottom: 56px; }
        .lp-persona-grid { display: grid; grid-template-columns: repeat(3,1fr); gap: 2px; background: #e5e0d5; }
        .lp-persona { background: #f8f5ef; padding: 38px 32px; transition: background .2s; }
        .lp-persona:hover { background: #f0ece3; }
        .lp-p-icon { width: 36px; height: 36px; background: #f0ece3; border: 1px solid #e5e0d5; display: flex; align-items: center; justify-content: center; margin-bottom: 20px; }
        .lp-p-icon svg { width: 15px; height: 15px; stroke: #55544f; fill: none; stroke-width: 1.8; }
        .lp-p-who { font-family: 'JetBrains Mono', monospace; font-size: 8.5px; letter-spacing: .14em; text-transform: uppercase; color: #b8955a; margin-bottom: 10px; }
        .lp-p-title { font-family: 'Playfair Display', serif; font-size: 19px; font-weight: 600; color: #09090a; margin-bottom: 12px; line-height: 1.3; }
        .lp-p-desc { font-size: 13px; color: #55544f; line-height: 1.85; }
        .lp-p-desc strong { color: #09090a; font-weight: 600; }

        /* MODELS */
        .lp-models-sec { background: #111113; padding: 100px 52px; position: relative; overflow: hidden; }
        .lp-models-sec::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 50% 60% at 85% 40%,rgba(184,149,90,.05) 0%,transparent 65%); pointer-events: none; }
        .lp-models-h { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,3.5vw,3.4rem); font-weight: 600; color: #f8f5ef; letter-spacing: -.03em; line-height: 1.1; margin-bottom: 10px; }
        .lp-models-sub { font-size: 15px; color: #7a7870; max-width: 560px; line-height: 1.8; margin-bottom: 64px; }
        .lp-pipeline-wrap { position: relative; }
        .lp-pipe-line { position: absolute; top: 26px; left: calc(12.5% + 12px); right: calc(12.5% + 12px); height: 1px; background: linear-gradient(90deg,rgba(184,149,90,.15),rgba(46,158,96,.2),rgba(184,149,90,.15)); z-index: 0; }
        .lp-pipeline { display: grid; grid-template-columns: repeat(4,1fr); gap: 0; position: relative; z-index: 1; }
        .lp-pstep { padding: 0 20px 36px; }
        .lp-pstep-num { width: 28px; height: 28px; display: flex; align-items: center; justify-content: center; font-family: 'JetBrains Mono', monospace; font-size: 10px; font-weight: 500; margin-bottom: 20px; border: 1px solid rgba(255,255,255,.1); color: #7a7870; background: #111113; }
        .lp-pstep.featured .lp-pstep-num { background: #2e9e60; border-color: #2e9e60; color: #fff; }
        .lp-pstep.hype .lp-pstep-num { background: #c07820; border-color: #c07820; color: #fff; }
        .lp-pstep-model-name { font-family: 'Playfair Display', serif; font-size: 15px; font-weight: 600; color: #f8f5ef; margin-bottom: 4px; line-height: 1.3; }
        .lp-pstep-model-sub { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .1em; text-transform: uppercase; color: #b8955a; margin-bottom: 10px; }
        .lp-pstep-desc { font-size: 12px; color: #7a7870; line-height: 1.75; }
        .lp-pstep-outs { margin-top: 12px; display: flex; flex-direction: column; gap: 4px; }
        .lp-po { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: rgba(122,120,112,.7); display: flex; align-items: center; gap: 5px; }
        .lp-po::before { content: '→'; color: rgba(255,255,255,.1); }
        .lp-model-badge-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 48px; padding-top: 40px; border-top: 1px solid rgba(255,255,255,.06); }
        .lp-model-badge { padding: 10px 18px; border: 1px solid rgba(255,255,255,.08); background: rgba(255,255,255,.025); display: flex; flex-direction: column; gap: 4px; }
        .lp-mb-name { font-family: 'Playfair Display', serif; font-size: 14px; font-weight: 600; color: #f8f5ef; letter-spacing: .01em; }
        .lp-mb-role { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .12em; text-transform: uppercase; color: #3a3936; }
        .lp-mb-desc { font-size: 11px; color: #7a7870; margin-top: 2px; line-height: 1.5; }
        .lp-mb-tag { display: inline-block; margin-top: 6px; padding: 2px 8px; font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .1em; text-transform: uppercase; }
        .lp-mbt-gold { background: rgba(184,149,90,.12); border: 1px solid rgba(184,149,90,.25); color: #d4b07a; }
        .lp-mbt-green { background: rgba(46,158,96,.1); border: 1px solid rgba(46,158,96,.2); color: #3dba72; }

        /* CHAT */
        .lp-chat-sec { background: #f8f5ef; padding: 100px 52px; border-top: 1px solid #e5e0d5; }
        .lp-chat-inner { display: grid; grid-template-columns: 1fr 1fr; gap: 64px; align-items: center; }
        .lp-chat-h { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,3.5vw,3.2rem); font-weight: 600; color: #09090a; letter-spacing: -.03em; line-height: 1.1; margin-bottom: 18px; }
        .lp-chat-h em { font-style: italic; color: #b8955a; }
        .lp-chat-p { font-size: 15px; color: #55544f; line-height: 1.85; margin-bottom: 28px; }
        .lp-chat-bullets { display: flex; flex-direction: column; gap: 13px; }
        .lp-cb { display: flex; align-items: flex-start; gap: 12px; font-size: 13px; color: #55544f; line-height: 1.7; }
        .lp-cbdot { width: 18px; height: 18px; background: rgba(46,158,96,.08); border: 1px solid rgba(46,158,96,.2); display: flex; align-items: center; justify-content: center; flex-shrink: 0; margin-top: 1px; }
        .lp-cbdot svg { width: 8px; height: 8px; stroke: #2e9e60; fill: none; stroke-width: 2.5; }
        .lp-cb strong { color: #09090a; font-weight: 600; }
        .lp-chat-mock { background: #f0ece3; border: 1px solid #e5e0d5; overflow: hidden; }
        .lp-cm-head { padding: 12px 16px; background: #f8f5ef; border-bottom: 1px solid #e5e0d5; display: flex; align-items: center; gap: 9px; }
        .lp-cm-pico { width: 22px; height: 22px; background: rgba(46,158,96,.1); border: 1px solid rgba(46,158,96,.2); display: flex; align-items: center; justify-content: center; }
        .lp-cm-pico svg { width: 10px; height: 10px; stroke: #2e9e60; fill: none; stroke-width: 2; }
        .lp-cm-pname { font-size: 11px; font-weight: 500; color: #09090a; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
        .lp-cm-sbadge { font-family: 'JetBrains Mono', monospace; font-size: 8px; padding: 2px 7px; background: rgba(46,158,96,.08); border: 1px solid rgba(46,158,96,.18); color: #2e9e60; }
        .lp-cm-msgs { padding: 14px 16px; display: flex; flex-direction: column; gap: 10px; min-height: 220px; }
        .lp-cm-msg { display: flex; gap: 8px; align-items: flex-start; }
        .lp-cm-msg.u { flex-direction: row-reverse; }
        .lp-cm-av { width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-family: 'JetBrains Mono', monospace; font-size: 8px; font-weight: 600; flex-shrink: 0; }
        .lp-cm-av.ai { background: #09090a; color: #f8f5ef; }
        .lp-cm-av.u { background: #e5e0d5; color: #55544f; }
        .lp-cm-bbl { padding: 8px 11px; font-size: 11.5px; line-height: 1.65; max-width: 88%; }
        .lp-cm-msg.ai .lp-cm-bbl { background: #f8f5ef; border: 1px solid #e5e0d5; color: #55544f; }
        .lp-cm-msg.u .lp-cm-bbl { background: rgba(46,158,96,.08); border: 1px solid rgba(46,158,96,.18); color: #09090a; }
        .lp-cm-bbl strong { color: #09090a; font-weight: 600; }
        .lp-cm-inp-row { padding: 12px 16px; border-top: 1px solid #e5e0d5; display: flex; gap: 8px; background: #f8f5ef; }
        .lp-cm-inp { flex: 1; background: #f0ece3; border: 1px solid #e5e0d5; padding: 8px 12px; font-family: 'Syne', sans-serif; font-size: 12px; color: #55544f; }
        .lp-cm-send { width: 34px; height: 34px; background: #09090a; display: flex; align-items: center; justify-content: center; flex-shrink: 0; }
        .lp-cm-send svg { width: 12px; height: 12px; stroke: #f8f5ef; fill: none; stroke-width: 2; }

        /* LIVE PAPERS */
        .lp-papers-sec { background: #111113; padding: 100px 52px; position: relative; overflow: hidden; }
        .lp-papers-sec::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 45% 55% at 80% 50%,rgba(184,149,90,.045) 0%,transparent 65%); pointer-events: none; }
        .lp-papers-h { font-family: 'Playfair Display', serif; font-size: clamp(2.2rem,3.5vw,3.2rem); font-weight: 600; color: #f8f5ef; letter-spacing: -.03em; line-height: 1.1; margin-bottom: 10px; }
        .lp-papers-sub { font-size: 15px; color: #7a7870; max-width: 500px; line-height: 1.75; margin-bottom: 52px; }
        .lp-pcards { display: grid; grid-template-columns: repeat(3,1fr); gap: 1px; background: rgba(255,255,255,.05); }
        .lp-pcard { background: #111113; padding: 28px 24px; transition: background .2s; cursor: default; }
        .lp-pcard:hover { background: #1c1c1f; }
        .lp-pct { display: flex; align-items: center; gap: 7px; margin-bottom: 14px; }
        .lp-pct-d { width: 5px; height: 5px; border-radius: 50%; }
        .lp-pcard.adopt .lp-pct-d { background: #3dba72; }
        .lp-pcard.gem .lp-pct-d { background: #d4b07a; }
        .lp-pcard.skip .lp-pct-d { background: #d06060; }
        .lp-pct-l { font-family: 'JetBrains Mono', monospace; font-size: 8px; letter-spacing: .16em; text-transform: uppercase; }
        .lp-pcard.adopt .lp-pct-l { color: #3dba72; }
        .lp-pcard.gem .lp-pct-l { color: #d4b07a; }
        .lp-pcard.skip .lp-pct-l { color: #d06060; }
        .lp-pc-title { font-family: 'Playfair Display', serif; font-size: 14.5px; font-weight: 600; color: #f8f5ef; line-height: 1.45; margin-bottom: 8px; }
        .lp-pc-desc { font-size: 11.5px; color: #7a7870; line-height: 1.7; margin-bottom: 16px; }
        .lp-pc-foot { display: flex; align-items: center; justify-content: space-between; }
        .lp-pc-score { font-family: 'JetBrains Mono', monospace; font-size: 24px; font-weight: 500; color: #f8f5ef; }
        .lp-pc-dims { display: flex; flex-direction: column; gap: 3px; flex: 1; margin: 0 14px; max-width: 90px; }
        .lp-pcd { height: 2px; background: rgba(255,255,255,.06); }
        .lp-pcd-f { height: 2px; }
        .lp-pcard.adopt .lp-pcd-f { background: #2e9e60; }
        .lp-pcard.gem .lp-pcd-f { background: #b8955a; }
        .lp-pcard.skip .lp-pcd-f { background: #b03838; }
        .lp-pc-hype { font-family: 'JetBrains Mono', monospace; font-size: 9px; padding: 2px 7px; }
        .lp-ph-lo { background: rgba(46,158,96,.1); border: 1px solid rgba(46,158,96,.2); color: #3dba72; }
        .lp-ph-hi { background: rgba(176,56,56,.1); border: 1px solid rgba(176,56,56,.2); color: #d06060; }
        .lp-ph-mid { background: rgba(255,255,255,.04); border: 1px solid rgba(255,255,255,.08); color: #7a7870; }

        /* STATS */
        .lp-stats-sec { background: #f8f5ef; padding: 80px 52px; border-top: 1px solid #e5e0d5; }
        .lp-stats-row { display: grid; grid-template-columns: repeat(4,1fr); gap: 2px; background: #e5e0d5; margin-bottom: 52px; }
        .lp-sc-stat { background: #f8f5ef; padding: 40px 32px; }
        .lp-sn { font-family: 'Playfair Display', serif; font-size: 52px; font-weight: 900; color: #09090a; line-height: 1; letter-spacing: -.04em; margin-bottom: 6px; }
        .lp-sn em { font-size: 30px; font-style: normal; color: #b8955a; }
        .lp-sl { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: #55544f; }
        .lp-tech-row { display: flex; align-items: center; flex-wrap: wrap; border: 1px solid #e5e0d5; }
        .lp-tech-p { padding: 13px 22px; border-right: 1px solid #e5e0d5; font-family: 'JetBrains Mono', monospace; font-size: 9.5px; letter-spacing: .09em; text-transform: uppercase; color: #55544f; display: flex; align-items: center; gap: 7px; }
        .lp-tech-p:last-child { border-right: none; }
        .lp-tech-p svg { width: 11px; height: 11px; stroke: currentColor; fill: none; stroke-width: 1.8; flex-shrink: 0; }

        /* CTA */
        .lp-cta-sec { background: #09090a; padding: 120px 52px; text-align: center; position: relative; overflow: hidden; }
        .lp-cta-sec::before { content: ''; position: absolute; inset: 0; background: radial-gradient(ellipse 55% 70% at 50% 50%,rgba(184,149,90,.055) 0%,transparent 65%); pointer-events: none; }
        .lp-cta-rel { position: relative; }
        .lp-cta-ey { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .22em; text-transform: uppercase; color: #3a3936; margin-bottom: 18px; }
        .lp-cta-h { font-family: 'Playfair Display', serif; font-size: clamp(2rem,5vw,4.2rem); font-weight: 600; color: #f8f5ef; line-height: 1.1; letter-spacing: -.025em; max-width: 680px; margin: 0 auto 18px; }
        .lp-cta-h em { font-style: italic; color: #d4b07a; }
        .lp-cta-sub { font-size: 15px; color: rgba(248,245,239,.45); line-height: 1.8; max-width: 420px; margin: 0 auto 48px; }
        .lp-sp-row { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 7px; margin-bottom: 36px; }
        .lp-sp-lbl { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .14em; text-transform: uppercase; color: #3a3936; margin-right: 4px; }
        .lp-sp-t { padding: 7px 14px; border: 1px solid rgba(255,255,255,.1); font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #7a7870; cursor: pointer; transition: all .15s; user-select: none; }
        .lp-sp-t:hover, .lp-sp-t.lp-on { border-color: #b8955a; color: #b8955a; }
        .lp-cta-btns { display: flex; align-items: center; justify-content: center; gap: 14px; flex-wrap: wrap; }
        .lp-btn-cta { padding: 15px 38px; background: #b8955a; color: #09090a; font-family: 'Syne', sans-serif; font-size: 11px; font-weight: 700; letter-spacing: .12em; text-transform: uppercase; border: none; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 9px; transition: all .22s; }
        .lp-btn-cta:hover { background: #d4b07a; transform: translateY(-2px); box-shadow: 0 10px 28px rgba(184,149,90,.2); }
        .lp-btn-cta svg { width: 12px; height: 12px; stroke: currentColor; fill: none; stroke-width: 2.5; }
        .lp-cta-note { margin-top: 20px; font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: #3a3936; }

        /* FOOTER */
        .lp-footer { background: #111113; padding: 32px 52px; border-top: 1px solid rgba(255,255,255,.05); display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 16px; }
        .lp-foot-logo { font-family: 'Playfair Display', serif; font-size: 14px; color: #3a3936; }
        .lp-foot-links { display: flex; gap: 28px; }
        .lp-foot-link { font-family: 'JetBrains Mono', monospace; font-size: 9px; letter-spacing: .12em; text-transform: uppercase; color: #3a3936; text-decoration: none; transition: color .15s; }
        .lp-foot-link:hover { color: #f8f5ef; }
        .lp-foot-copy { font-family: 'JetBrains Mono', monospace; font-size: 9px; color: #3a3936; letter-spacing: .06em; }

        /* SCROLL REVEAL */
        .lp-reveal { opacity: 0; transform: translateY(22px); transition: opacity .7s ease, transform .7s ease; }
        .lp-reveal.in { opacity: 1; transform: translateY(0); }
        .lp-d1 { transition-delay: .08s; } .lp-d2 { transition-delay: .18s; } .lp-d3 { transition-delay: .28s; } .lp-d4 { transition-delay: .38s; }

        @media(max-width:960px) {
          .lp-nav { padding: 16px 24px; }
          .lp-hero { padding: 100px 24px 64px; }
          .lp-split-sec { padding: 0 24px 64px; }
          .lp-split-label-row { padding: 40px 0 28px; }
          .lp-split-sub { text-align: left; }
          .lp-split-frame { grid-template-columns: 1fr; height: auto; }
          .lp-split-pdf { height: 360px; }
          .lp-sc-inner { grid-template-columns: 1fr; gap: 36px; }
          .lp-for-sec, .lp-models-sec, .lp-chat-sec, .lp-papers-sec, .lp-stats-sec, .lp-cta-sec { padding: 64px 24px; }
          .lp-persona-grid { grid-template-columns: 1fr; }
          .lp-pipeline { grid-template-columns: 1fr 1fr; }
          .lp-pipe-line { display: none; }
          .lp-model-badge-row { flex-direction: column; }
          .lp-chat-inner { grid-template-columns: 1fr; gap: 36px; }
          .lp-pcards { grid-template-columns: 1fr; }
          .lp-stats-row { grid-template-columns: 1fr 1fr; }
          .lp-footer { flex-direction: column; text-align: center; }
          .lp-scorecard-sec { padding: 64px 24px; }
        }
      `}</style>

      <div className="lp-noise" />

      {/* INTRO */}
      <div id="lp-intro" onClick={handleSkip}>
        <div className="lp-intro-glow" />
        <div id="lp-stage-quote">
          <div className="lp-q-mark">❝</div>
          <div className="lp-q-text" id="lp-qText" />
          <div className="lp-q-attr" id="lp-qAttr" />
        </div>
        <div id="lp-stage-logo">
          <div className="lp-intro-wordmark" id="lp-introWord">Paper2Signal</div>
          <div className="lp-intro-tagline">Research Intelligence · Production Radar</div>
          <div className="lp-intro-models">
            {['The Reasoner','The Thinker','The Scribe','The Sentinel'].map(m => (
              <div className="lp-im-item" key={m}><div className="lp-im-dot" />{m}</div>
            ))}
          </div>
        </div>
        <div className="lp-intro-bar" id="lp-introBar" />
        <div className="lp-intro-skip">Click to enter →</div>
      </div>

      {/* MAIN */}
      <div id="lp-main">
        {/* NAV */}
        <nav className="lp-nav">
          <a href="#" className="lp-logo">
            <div className="lp-logo-mark">
              <svg viewBox="0 0 24 24"><path d="M12 2L2 7l10 5 10-5-10-5z"/><path d="M2 17l10 5 10-5"/><path d="M2 12l10 5 10-5"/></svg>
            </div>
            <span className="lp-logo-name">Paper2Signal</span>
          </a>
          <div className="lp-nav-r">
            <a href="#lp-for-who" className="lp-nav-a">Who it's for</a>
            <a href="#lp-models" className="lp-nav-a">Models</a>
            <a href="#lp-papers" className="lp-nav-a">Live papers</a>
            <button className="lp-nav-btn" onClick={handleOpenApp}>Open app →</button>
          </div>
        </nav>

        {/* HERO */}
        <section className="lp-hero">
          <div className="lp-hero-bg" /><div className="lp-hero-gl" />
          <div>
            <div className="lp-hero-badge"><div className="lp-bdot" /><span className="lp-btxt">247 papers scored today · pipeline live</span></div>
            <h1 className="lp-hero-h1">47 new papers.<br />20 minutes.<br /><span>We already <em>read them all.</em></span></h1>
            <p className="lp-hero-p">
              It's Monday morning. There are 47 new papers on ArXiv tagged to your field.<br />You have 20 minutes.<br /><br />
              Paper2Signal has already read all 47. It knows which three are worth your time, which one the community is hyping but won't run in production, and which quiet paper — 18 stars, no Twitter thread — would cut your inference cost in half if you shipped it this sprint.<br /><br />
              Open any paper. Ask it anything. Not a summary — a conversation.<br />
              <strong>Why does the math work? Does it beat GPTQ on my setup? What are the exact steps to try it today?</strong><br /><br />
              That's Paper2Signal. Four agents, one verdict, zero wasted sprints.
            </p>
            <div className="lp-hero-actions">
              <button className="lp-btn-hero" onClick={handleOpenApp}>
                See what it found today <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
              <a href="#lp-split" className="lp-btn-ghost">Watch it work ↓</a>
            </div>
            <div className="lp-hero-trust">
              {[['Open source','GitHub'],['Model published','HuggingFace'],['Powered by','DeepSeek-R1'],['No account','required'],['GRPO trained','zero human labels']].map(([l,s]) => (
                <div key={l} style={{display:'flex',alignItems:'center',gap:16}}>
                  <div className="lp-ti">{l}<br /><strong>{s}</strong></div>
                  <div className="lp-ts" />
                </div>
              ))}
            </div>
          </div>
        </section>

        <div className="lp-dark-to-light" />

        {/* SPLIT */}
        <section className="lp-split-sec" id="lp-split">
          <div className="lp-section-w">
            <div className="lp-split-label-row lp-reveal">
              <div>
                <div className="lp-sec-lbl" style={{marginBottom:10}}>The Scribe · Read &amp; Chat</div>
                <h2 className="lp-split-headline">Read the paper.<br /><em>Ask it anything.</em> Then build.</h2>
              </div>
              <p className="lp-split-sub">Every paper has a full chat interface. Not a summary — a conversation with the actual content.</p>
            </div>
            <div className="lp-split-frame lp-reveal">
              <div className="lp-split-pdf">
                <div className="lp-split-pdf-bar">
                  <div className="lp-spb-dots"><div className="lp-spb-dot r"/><div className="lp-spb-dot y"/><div className="lp-spb-dot g"/></div>
                  <div className="lp-spb-title">SpinQuant: LLM Quantization with Learned Rotations for 4-bit Inference</div>
                  <div className="lp-spb-score">7.8 · Adopt</div>
                </div>
                <div className="lp-pdf-mock">
                  <div className="lp-pm-title-big">SpinQuant: LLM Quantization with<br />Learned Rotations for 4-bit Inference</div>
                  <div className="lp-pm-authors">Zhuang Liu, Barlas Oguz, Changsheng Zhao et al. · Meta AI · 2024</div>
                  <div className="lp-pm-divider" />
                  <div className="lp-pm-section-lbl">Abstract</div>
                  <div className="lp-pm-body">
                    <div className="lp-pm-line full"/><div className="lp-pm-line full"/><div className="lp-pm-line med"/>
                    <div className="lp-pm-highlight"><div className="lp-pm-highlight-line"/><div className="lp-pm-highlight-line"/><div className="lp-pm-highlight-line"/></div>
                    <div className="lp-pm-line full"/><div className="lp-pm-line short"/>
                  </div>
                  <div className="lp-pm-divider" />
                  <div className="lp-pm-section-lbl">1. Introduction</div>
                  <div className="lp-pm-body">
                    <div className="lp-pm-line full"/><div className="lp-pm-line full"/><div className="lp-pm-line med"/>
                    <div className="lp-pm-formula">W̃ = R^T · W · R &nbsp;|&nbsp; Minimize E[‖Wx − W̃x‖²]</div>
                    <div className="lp-pm-line full"/><div className="lp-pm-line half"/>
                  </div>
                </div>
                <div className="lp-pdf-page-bar">
                  <div className="lp-ppb-nav">
                    <div className="lp-ppb-btn"><svg viewBox="0 0 24 24"><polyline points="15 18 9 12 15 6"/></svg></div>
                    <span>1 / 12</span>
                    <div className="lp-ppb-btn"><svg viewBox="0 0 24 24"><polyline points="9 18 15 12 9 6"/></svg></div>
                  </div>
                  <div className="lp-ppb-arxiv">arxiv.org/abs/2405.16406 ↗</div>
                </div>
              </div>
              <div className="lp-split-chat">
                <div className="lp-split-chat-head">
                  <div className="lp-sch-top">
                    <div className="lp-sch-icon"><svg viewBox="0 0 24 24"><path d="M21 15a2 2 0 01-2 2H7l-4 4V5a2 2 0 012-2h14a2 2 0 012 2z"/></svg></div>
                    <div className="lp-sch-label">Paper Chat</div>
                  </div>
                  <div className="lp-sch-model">The Scribe · RAG over full paper content</div>
                </div>
                <div className="lp-split-chat-msgs">
                  {[
                    {role:'ai', text: "I've read SpinQuant in full. It applies learned rotation matrices to weight tensors before quantization, reducing rounding error. The result: <strong>3.7× memory reduction</strong> with near-zero accuracy loss at 4-bit."},
                    {role:'u', text: 'How is this different from GPTQ?'},
                    {role:'ai', text: 'GPTQ uses second-order information to minimize layer-wise quantization error. SpinQuant instead <strong>rotates the weight space</strong> so the distribution is more quantization-friendly before you apply any standard quantizer. On Llama 3 at 4-bit, SpinQuant beats GPTQ by ~0.4 perplexity points. And it\'s a <strong>drop-in</strong> — no changes to your inference code.'},
                    {role:'u', text: 'Give me the implementation steps'},
                    {role:'ai', text: 'From Section 4.2 of the paper: <strong>1.</strong> Install the HuggingFace integration via pip. <strong>2.</strong> Load your model with <em>load_in_4bit=True, quantization_config=SpinQuantConfig()</em>. <strong>3.</strong> Run inference — no fine-tuning needed. The rotation matrices are precomputed per model family.'},
                  ].map((m,i) => (
                    <div key={i} className={`lp-scm ${m.role}`}>
                      <div className={`lp-scm-av ${m.role}`}>{m.role === 'ai' ? 'PS' : 'U'}</div>
                      <div className="lp-scm-bbl" dangerouslySetInnerHTML={{__html: m.text}} />
                    </div>
                  ))}
                </div>
                <div className="lp-split-suggestions">
                  {['Does this work with vLLM?','Explain the rotation math','Compare to AWQ'].map(s => <div key={s} className="lp-ssugg">{s}</div>)}
                </div>
                <div className="lp-split-chat-inp">
                  <div className="lp-sci">Ask anything about this paper...</div>
                  <div className="lp-sci-btn"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* SCORE CARD */}
        <section className="lp-scorecard-sec">
          <div className="lp-sc-inner lp-reveal">
            <div>
              <div className="lp-sec-lbl light" style={{marginBottom:18}}>The Thinker · Production Score</div>
              <h2 className="lp-sc-copy-h">Not just "does code exist?" — <em>is it worth your time?</em></h2>
              <p className="lp-sc-copy-p">Most paper tools tell you what a paper says. Paper2Signal tells you whether it's production-ready for your stack. Every score is the output of DeepSeek-R1 chain-of-thought reasoning — not a keyword match.</p>
              <div className="lp-sc-dims-explain">
                {[['01','Reproducibility','Can you actually run this? Does the code exist, is it maintained, do the benchmarks reproduce?'],['02','Compute cost','What does it cost to run at your scale? Is it H100-only or does it work on a single A100?'],['03','Latency','Does it actually make inference faster, or is the speedup only in training?'],['04','Adoption trajectory','Is the community actually using it, or just citing it?'],['05','Hype score','Separately scored by The Sentinel, our GRPO-trained model. High hype + low score = skip.']].map(([n,title,desc]) => (
                  <div key={n} className="lp-scd"><span className="lp-scd-num">{n}</span><div className="lp-scd-text"><strong>{title}</strong> — {desc}</div></div>
                ))}
              </div>
            </div>
            <div className="lp-score-demo lp-reveal lp-d2">
              <div className="lp-sd-bar" />
              <div className="lp-sd-head">
                <div className="lp-sd-title" id="lp-dTitle">FlashAttention-3: Fast and Accurate Attention with Asynchrony and Low-precision</div>
                <div className="lp-sd-score-box"><div className="lp-sd-num" id="lp-dScore">8.5</div><div className="lp-sd-slbl">Prod. score</div></div>
              </div>
              <div className="lp-sd-verdict">
                <div className="lp-vbadge lp-vb-adopt" id="lp-dVerdict">Adopt</div>
                <div className="lp-vtext" id="lp-dVText">Drop-in for HuggingFace + vLLM. 1.2k stars. Use in production this week.</div>
              </div>
              <div className="lp-sd-dims">
                {[['Reproducibility','lp-df1','9.0'],['Compute cost','lp-df2','8.0'],['Latency','lp-df3','8.5'],['Adoption','lp-df4','7.0']].map(([label,id,val]) => (
                  <div key={id} className="lp-dr">
                    <span className="lp-dl">{label}</span>
                    <div className="lp-dt"><div className="lp-df" id={id} style={{width:'0%',background:'#3dba72'}} /></div>
                    <span className="lp-dv">{val}</span>
                  </div>
                ))}
              </div>
              <div className="lp-sd-chat">
                <div className="lp-sc-lbl">The Sentinel · Hype detection</div>
                <div className="lp-sc-msg ai"><span>Hype score</span><span style={{fontFamily:'JetBrains Mono,monospace',fontSize:18,color:'#7a7870'}}>8 / 10</span></div>
                <div className="lp-sc-msg ai"><span>Hidden gem?</span><span style={{fontFamily:'JetBrains Mono,monospace',fontSize:10,color:'#7a7870'}}>No — well known</span></div>
              </div>
            </div>
          </div>
        </section>

        {/* WHO IT'S FOR */}
        <section className="lp-for-sec" id="lp-for-who">
          <div className="lp-section-w">
            <div className="lp-sec-lbl lp-reveal">Who it's for</div>
            <h2 className="lp-for-h lp-reveal">One platform. Three kinds of people. All saving time on research.</h2>
            <div className="lp-persona-grid">
              {[
                {who:'For students',title:'Just discovered a paper and don\'t know where to start',desc:'Chat with the paper directly. Ask what the equations mean, how the method compares to what you already know, and whether there\'s a simpler way to implement it.',strong:'Learn while you read — at your own pace.',d:'M2 3h6a4 4 0 014 4v14a3 3 0 00-3-3H2z',d2:'M22 3h-6a4 4 0 00-4 4v14a3 3 0 013-3h7z'},
                {who:'For researchers',title:'Staying current without drowning in abstracts',desc:'Paper2Signal surfaces what\'s genuinely novel versus incremental. Get a scored digest every day and spend your deep reading time only on papers that earned it.',strong:'Know the field without reading every paper.',d:'M12 2a10 10 0 100 20A10 10 0 0012 2z',d2:'M2 12h20'},
                {who:'For ML engineers',title:'Deciding what\'s worth integrating this sprint',desc:'Every paper is scored across 5 production dimensions. Not "does code exist?" but',strong:'is it useful for your specific stack, at your scale, right now?',d:'M22 12h-4l-3 9L9 3l-3 9H2'},
              ].map((p,i) => (
                <div key={i} className={`lp-persona lp-reveal lp-d${i+1}`}>
                  <div className="lp-p-icon"><svg viewBox="0 0 24 24"><path d={p.d}/>{p.d2 && <path d={p.d2}/>}</svg></div>
                  <div className="lp-p-who">{p.who}</div>
                  <div className="lp-p-title">{p.title}</div>
                  <div className="lp-p-desc">{p.desc} <strong>{p.strong}</strong></div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* MODELS */}
        <section className="lp-models-sec" id="lp-models">
          <div className="lp-section-w">
            <div className="lp-sec-lbl light lp-reveal">The intelligence layer</div>
            <h2 className="lp-models-h lp-reveal">Three purpose-built models.<br />Each one does one thing exceptionally well.</h2>
            <p className="lp-models-sub lp-reveal">Paper2Signal doesn't use a single general-purpose LLM. Each stage of the pipeline uses a model fine-tuned or orchestrated specifically for that job.</p>
            <div className="lp-pipeline-wrap">
              <div className="lp-pipe-line" />
              <div className="lp-pipeline">
                {[
                  {n:'1',name:'The Reasoner',sub:'Classifier · Llama-3.3-70b via Groq',desc:'The first mind to read each paper. Maps it to the research landscape — domain, novelty level, core contributions — and asks the first hard question: does working code actually exist?',outs:['Domain + category','Novelty assessment','Code availability'],cls:''},
                  {n:'2',name:'The Thinker',sub:'Production Scorer · DeepSeek-R1 via HF',desc:"Uses DeepSeek-R1's chain-of-thought reasoning to score each paper across five production dimensions — reproducibility, compute cost, latency, adoption trajectory, and real-world usefulness.",outs:['5-dimension score 0–10','Full reasoning trace','Overall readiness'],cls:'featured'},
                  {n:'3',name:'The Scribe',sub:'Brief Writer + Chat · Llama-3.3-70b + ChromaDB',desc:'Translates complex analysis into plain engineering language. Writes your Adopt/Experiment/Watch verdict and powers the live paper chat — grounding every answer in the actual paper content.',outs:['Adopt / Experiment / Watch','Stack fit analysis','Live paper chat'],cls:''},
                  {n:'4',name:'The Sentinel',sub:'Hype Detector · GRPO fine-tuned · Local',desc:'The watchdog. The only model we trained ourselves — using GRPO reinforcement learning with GitHub stars as reward signal. Zero human labels.',outs:['Hype score 1–10','Hidden gem detection','Overhype alert'],cls:'hype'},
                ].map(p => (
                  <div key={p.n} className={`lp-pstep lp-reveal lp-d${p.n} ${p.cls}`}>
                    <div className="lp-pstep-num">{p.n}</div>
                    <div className="lp-pstep-model-name">{p.name}</div>
                    <div className="lp-pstep-model-sub">{p.sub}</div>
                    <div className="lp-pstep-desc">{p.desc}</div>
                    <div className="lp-pstep-outs">{p.outs.map(o => <div key={o} className="lp-po">{o}</div>)}</div>
                  </div>
                ))}
              </div>
              <div className="lp-model-badge-row lp-reveal">
                {[
                  {name:'The Reasoner',role:'Classifier · Agent 1',desc:'First to read. Maps every paper to the research landscape.',tag:'Llama-3.3-70b · Groq',cls:'lp-mbt-gold'},
                  {name:'The Thinker',role:'Production Scorer · Agent 2',desc:'Deepest reasoner. Scores across 5 production dimensions.',tag:'DeepSeek-R1 · HF Router',cls:'lp-mbt-gold'},
                  {name:'The Scribe',role:'Brief Writer + Chat · Agent 3',desc:'Translates analysis to plain language. Powers paper chat.',tag:'Llama-3.3-70b · ChromaDB RAG',cls:'lp-mbt-gold'},
                  {name:'The Sentinel',role:'Hype Detector · Agent 4',desc:'Trained by us. GRPO. Zero human labels. Published on HuggingFace.',tag:'paper2signal-sentinel · HuggingFace',cls:'lp-mbt-green'},
                ].map(b => (
                  <div key={b.name} className="lp-model-badge">
                    <div className="lp-mb-name">{b.name}</div>
                    <div className="lp-mb-role">{b.role}</div>
                    <div className="lp-mb-desc">{b.desc}</div>
                    <span className={`lp-mb-tag ${b.cls}`}>{b.tag}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </section>

        {/* CHAT */}
        <section className="lp-chat-sec">
          <div className="lp-section-w">
            <div className="lp-chat-inner">
              <div className="lp-reveal">
                <div className="lp-sec-lbl">The Scribe · The killer feature</div>
                <h2 className="lp-chat-h">Read the paper.<br /><em>Ask it anything.</em><br />Then build.</h2>
                <p className="lp-chat-p">Every paper has a full chat interface powered by The Scribe — retrieval-augmented generation over the actual paper content. You're not asking an LLM that guessed from training data. You're asking a model that read the paper.</p>
                <div className="lp-chat-bullets">
                  {[['Students','Explain the attention mechanism on page 4 in plain English'],['Researchers','How does this compare to the Mamba approach from 2023?'],['Engineers','Will this integrate with my FastAPI + PyTorch 2.0 setup?'],['Everyone','Give me the exact steps to implement this today']].map(([who, q]) => (
                    <div key={who} className="lp-cb">
                      <div className="lp-cbdot"><svg viewBox="0 0 24 24"><polyline points="20 6 9 17 4 12"/></svg></div>
                      <div><strong>{who}:</strong> "{q}"</div>
                    </div>
                  ))}
                </div>
              </div>
              <div className="lp-chat-mock lp-reveal lp-d2">
                <div className="lp-cm-head">
                  <div className="lp-cm-pico"><svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg></div>
                  <div className="lp-cm-pname">SpinQuant: LLM Quantization with Learned Rotations</div>
                  <div className="lp-cm-sbadge">7.8 · Adopt</div>
                </div>
                <div className="lp-cm-msgs">
                  {[
                    {role:'ai',text:"I've read SpinQuant in full. It uses learned rotation matrices to reduce quantization error — <strong>3.7× memory reduction</strong> with near-zero accuracy loss."},
                    {role:'u',text:'Is this better than GPTQ for Llama 3?'},
                    {role:'ai',text:'For Llama 3 at 4-bit, SpinQuant beats GPTQ on perplexity by <strong>~0.4 points</strong>. The HuggingFace integration is a drop-in — no changes to your inference code needed.'},
                  ].map((m,i) => (
                    <div key={i} className={`lp-cm-msg ${m.role}`}>
                      <div className={`lp-cm-av ${m.role}`}>{m.role==='ai'?'PS':'U'}</div>
                      <div className="lp-cm-bbl" dangerouslySetInnerHTML={{__html:m.text}}/>
                    </div>
                  ))}
                </div>
                <div className="lp-cm-inp-row">
                  <div className="lp-cm-inp">Ask anything about this paper...</div>
                  <div className="lp-cm-send"><svg viewBox="0 0 24 24"><line x1="22" y1="2" x2="11" y2="13"/><polygon points="22 2 15 22 11 13 2 9 22 2"/></svg></div>
                </div>
              </div>
            </div>
          </div>
        </section>

        {/* LIVE PAPERS */}
        <section className="lp-papers-sec" id="lp-papers">
          <div className="lp-section-w">
            <div className="lp-sec-lbl light lp-reveal">Today's verdict</div>
            <h2 className="lp-papers-h lp-reveal">What the pipeline found today</h2>
            <p className="lp-papers-sub lp-reveal">Every number below is the output of all four models. Not a summary. A judgment.</p>
            <div className="lp-pcards">
              {[
                {cls:'adopt',label:'Adopt · Production ready',title:'FlashAttention-3: Fast and Accurate Attention with Asynchrony',desc:'1.5–2× faster than FA2 on H100. Drop-in replacement. Zero code changes on HuggingFace or vLLM.',score:'8.5',dims:['90%','80%','85%','70%'],hype:'Hype 8/10',hcls:'lp-ph-mid',d:'lp-d1'},
                {cls:'gem',label:'💎 The Sentinel found · Hidden gem',title:'SpinQuant: LLM Quantization with Learned Rotations',desc:'3.7× memory reduction, near-zero accuracy loss. Community sleeping on this. HuggingFace-ready right now.',score:'7.8',dims:['85%','90%','88%','65%'],hype:'Hype 4/10',hcls:'lp-ph-lo',d:'lp-d2'},
                {cls:'skip',label:'⚠ The Sentinel flagged · Overhyped',title:'Linear Attention via Diagonal State Spaces',desc:"Interesting theory. No implementation. Benchmarks on synthetic data only. Don't spend engineering time here yet.",score:'2.4',dims:['18%','30%','22%','10%'],hype:'Hype 8/10',hcls:'lp-ph-hi',d:'lp-d3',scoreColor:'#d06060'},
              ].map(c => (
                <div key={c.cls} className={`lp-pcard ${c.cls} lp-reveal ${c.d}`}>
                  <div className="lp-pct"><div className="lp-pct-d"/><div className="lp-pct-l">{c.label}</div></div>
                  <div className="lp-pc-title">{c.title}</div>
                  <div className="lp-pc-desc">{c.desc}</div>
                  <div className="lp-pc-foot">
                    <div className="lp-pc-score" style={c.scoreColor?{color:c.scoreColor}:{}}>{c.score}</div>
                    <div className="lp-pc-dims">{c.dims.map((w,i) => <div key={i} className="lp-pcd"><div className="lp-pcd-f" style={{width:w}}/></div>)}</div>
                    <div className={`lp-pc-hype ${c.hcls}`}>{c.hype}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* STATS */}
        <section className="lp-stats-sec">
          <div className="lp-section-w">
            <div className="lp-stats-row">
              {[['247+','Papers scored today'],['0','Human labels in The Sentinel'],['4','Purpose-built models'],['6h','Auto-refresh cycle']].map(([n,l],i) => (
                <div key={l} className={`lp-sc-stat lp-reveal lp-d${i}`}>
                  <div className="lp-sn" dangerouslySetInnerHTML={{__html: n.replace(/([^0-9])/g, '<em>$1</em>')}} />
                  <div className="lp-sl">{l}</div>
                </div>
              ))}
            </div>
            <div className="lp-tech-row lp-reveal">
              {['ArXiv pipeline','LangGraph agents','ChromaDB · The Scribe','The Sentinel · RLVR','FastAPI + SQLite','Open source · GitHub'].map(t => (
                <div key={t} className="lp-tech-p"><svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"/></svg>{t}</div>
              ))}
            </div>
          </div>
        </section>

        {/* CTA */}
        <section className="lp-cta-sec">
          <div className="lp-cta-rel">
            <div className="lp-cta-ey lp-reveal">No account required · Start now</div>
            <h2 className="lp-cta-h lp-reveal">Today's papers,<br /><em>already understood.</em></h2>
            <p className="lp-cta-sub lp-reveal">Tell us what you're working with. The four agents will show you exactly what's worth your time — and how to use it.</p>
            <div className="lp-sp-row lp-reveal">
              <span className="lp-sp-lbl">I work with:</span>
              {['PyTorch','HuggingFace','FastAPI','vLLM','LangChain','JAX','TensorFlow'].map((t,i) => (
                <div key={t} className={`lp-sp-t${i===0?' lp-on':''}`} onClick={toggleTag}>{t}</div>
              ))}
            </div>
            <div className="lp-cta-btns lp-reveal">
              <button className="lp-btn-cta" onClick={handleOpenApp}>
                Open Paper2Signal <svg viewBox="0 0 24 24"><line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
            <div className="lp-cta-note lp-reveal">Free · No signup · Stack saved locally · The Sentinel published on HuggingFace</div>
          </div>
        </section>

        {/* FOOTER */}
        <footer className="lp-footer">
          <div className="lp-foot-logo">Paper2Signal</div>
          <div className="lp-foot-links">
            <a href="#lp-models" className="lp-foot-link">Models</a>
            <a href="https://github.com/shau1905/papersignal" target="_blank" rel="noreferrer" className="lp-foot-link">GitHub</a>
            <a href="https://huggingface.co/paper2signal-sentinel" target="_blank" rel="noreferrer" className="lp-foot-link">The Sentinel on HF</a>
            <button className="lp-foot-link" onClick={handleOpenApp} style={{background:'none',border:'none',cursor:'pointer'}}>Open app</button>
          </div>
          <div className="lp-foot-copy">© 2026 Paper2Signal</div>
        </footer>
      </div>
    </>
  )
}