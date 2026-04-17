import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export const useStore = create(
  persist(
    (set, get) => ({
      // ── Stack ──────────────────────────────────────────
      stack: ['PyTorch', 'HuggingFace', 'FastAPI'],
      setStack: (stack) => set({ stack }),

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

      // ── Build snippets (Add to my build) ──────────────
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

      // ── Onboarded ─────────────────────────────────────
      onboarded: false,
      setOnboarded: () => set({ onboarded: true }),
    }),
    {
      name: 'paper2signal',
      partialize: (s) => ({
        stack: s.stack,
        theme: s.theme,
        savedPapers: s.savedPapers,
        buildSnippets: s.buildSnippets,
        onboarded: s.onboarded,
      })
    }
  )
)