import axios from 'axios'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
  timeout: 120000,
})

// ── Papers ────────────────────────────────────────────────────────────────────
export const getPapers     = (limit = 100) => api.get(`/papers?limit=${limit}`).then(r => r.data)
export const getPaper      = (id)          => api.get(`/papers/${id}`).then(r => r.data)
export const getPaperBrief = (id)          => api.get(`/papers/${id}/brief`).then(r => r.data)
export const analyzePaper  = (id)          => api.post(`/papers/${id}/analyze`).then(r => r.data)
// export const getAnalyzed   = (limit = 100) => api.get(`/analyzed?limit=${limit}`).then(r => r.data)
export const getAnalyzed   = (limit = 100, recent = false) => api.get(`/analyzed?limit=${limit}&recent=${recent}`).then(r => r.data)

// ── Ingest + Async Analyze ────────────────────────────────────────────────────
export const ingestPaper       = (id) => api.post(`/papers/${id}/ingest`).then(r => r.data)
export const analyzeAsync      = (id) => api.post(`/papers/${id}/analyze/async`).then(r => r.data)
export const getJob            = (job_id) => api.get(`/jobs/${job_id}`).then(r => r.data)
export const listJobs          = () => api.get('/jobs').then(r => r.data)

// ── Discovery ─────────────────────────────────────────────────────────────────
export const getHiddenGems  = ()          => api.get('/hidden-gems').then(r => r.data)
export const getThemes      = ()          => api.get('/themes').then(r => r.data)
export const semanticSearch = (q, n = 10) => api.get(`/search?q=${encodeURIComponent(q)}&n=${n}`).then(r => r.data)
export const getHealth      = ()          => api.get('/health').then(r => r.data)

// ── Chat ──────────────────────────────────────────────────────────────────────
export const globalChat = (message, history = [], n_papers = 5, model_pref = 'auto') =>
  api.post('/chat', { message, history, n_papers, model_pref }).then(r => r.data)

export const deepPaperChat = (id, message, history = [], session_id = null, model_pref = 'auto') =>
  api.post(`/papers/${id}/chat/deep`, { message, history, session_id, model_pref }).then(r => r.data)

// ── PDF Index ─────────────────────────────────────────────────────────────────
export const buildPaperIndex = (id) =>
  api.post(`/papers/${id}/index`, {}, { timeout: 180000 }).then(r => r.data)

export const getPaperSession = (id) =>
  api.get(`/papers/${id}/session`).then(r => r.data)

// ── Sessions ──────────────────────────────────────────────────────────────────
export const getSessions = ()    => api.get('/sessions').then(r => r.data)
export const getSession  = (id)  => api.get(`/sessions/${id}`).then(r => r.data)

// ── User Profile & Activity ───────────────────────────────────────────────────
export const getProfile    = ()     => api.get('/user/profile').then(r => r.data)
export const updateProfile = (data) => api.post('/user/profile', data).then(r => r.data)
export const getActivity   = ()     => api.get('/user/activity').then(r => r.data)

export default api