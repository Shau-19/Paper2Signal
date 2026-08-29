import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useStore = create(
  persist(
    (set, get) => ({
      // ── Stack (Commented out) ──────────────────────────
      // stack: ['PyTorch', 'HuggingFace', 'FastAPI'],
      // setStack: (stack) => set({ stack }),

      // ── User Profile ──────────────────────────────────
      userProfile: {
        name: 'Shaurya',
        email: 'shaurya@papersignal.ai',
        role: 'Lead ML Engineer',
        preferences: { theme: 'dark', model_pref: 'auto', alert_threshold: 7.5 }
      },
      setUserProfile: (profile) => set({ userProfile: profile }),

      // ── Active paper (for Read & Chat) ────────────────
      activePaper: null,
      setActivePaper: (paper) => set({ activePaper: paper }),

      // ── Sidebar ───────────────────────────────────────
      sidebarCollapsed: false,
      toggleSidebar: () => set(s => ({ sidebarCollapsed: !s.sidebarCollapsed })),

      // ── Theme ─────────────────────────────────────────
      theme: 'dark',
      toggleTheme: () => set(s => ({ theme: s.theme === 'dark' ? 'light' : 'dark' })),

      // ── Saved papers ──────────────────────────────────
      savedPapers: [],
      savePaper: (id) => set(s => ({
        savedPapers: s.savedPapers.includes(id)
          ? s.savedPapers
          : [...s.savedPapers, id]
      })),
      unsavePaper: (id) => set(s => ({
        savedPapers: s.savedPapers.filter(p => p !== id)
      })),

      // ── Build snippets ─────────────────────────────────
      buildSnippets: [],
      addSnippet: (snippet) => set(s => ({
        buildSnippets: [...s.buildSnippets, {
          ...snippet,
          id: Date.now(),
          addedAt: new Date().toISOString()
        }]
      })),
      removeSnippet: (id) => set(s => ({
        buildSnippets: s.buildSnippets.filter(s => s.id !== id)
      })),

      // ── Async Analysis Jobs ────────────────────────────
      // Persisted so jobs survive navigation
      activeJobs: [],
      addJob: (job) => set(s => ({
        activeJobs: [...s.activeJobs, {
          job_id:     job.job_id,
          paper_id:   job.paper_id,
          title:      job.title,
          status:     'pending',
          started_at: new Date().toISOString(),
        }]
      })),
      updateJob: (job_id, updates) => set(s => ({
        activeJobs: s.activeJobs.map(j =>
          j.job_id === job_id ? { ...j, ...updates } : j
        )
      })),
      removeJob: (job_id) => set(s => ({
        activeJobs: s.activeJobs.filter(j => j.job_id !== job_id)
      })),
      clearDoneJobs: () => set(s => ({
        activeJobs: s.activeJobs.filter(j => j.status !== 'done' && j.status !== 'failed')
      })),

      // ── Notifications ──────────────────────────────────
      notifications: [],
      addNotification: (n) => set(s => ({
        notifications: [{ ...n, id: Date.now(), read: false }, ...s.notifications].slice(0, 20)
      })),
      markNotificationRead: (id) => set(s => ({
        notifications: s.notifications.map(n => n.id === id ? { ...n, read: true } : n)
      })),
      clearNotifications: () => set({ notifications: [] }),

      // ── Onboarded ─────────────────────────────────────
      onboarded: false,
      setOnboarded: () => set({ onboarded: true }),
    }),
    {
      name: 'paper2signal',
      partialize: (s) => ({
        // stack:         s.stack,
        userProfile:   s.userProfile,
        theme:         s.theme,
        savedPapers:   s.savedPapers,
        buildSnippets: s.buildSnippets,
        onboarded:     s.onboarded,
        activeJobs:    s.activeJobs.filter(j => j.status === 'pending' || j.status === 'running'),
        notifications: s.notifications,
      })
    }
  )
)