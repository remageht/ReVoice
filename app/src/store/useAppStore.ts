import { create } from 'zustand'
import type { Profile } from '../api/client'

interface AppStore {
  // Active profile
  activeProfileId: string | null
  setActiveProfileId: (id: string | null) => void

  // Active engine
  activeEngine: string
  setActiveEngine: (engine: string) => void

  // Active engine variant
  activeVariant: string
  setActiveVariant: (variant: string) => void

  // UI state
  activeTab: string
  setActiveTab: (tab: string) => void

  // Backend status
  backendReady: boolean
  setBackendReady: (ready: boolean) => void

  // Synthesis state
  isSynthesizing: boolean
  setIsSynthesizing: (v: boolean) => void
  lastGenerationPath: string | null
  setLastGenerationPath: (path: string | null) => void
}

export const useAppStore = create<AppStore>((set) => ({
  activeProfileId: null,
  setActiveProfileId: (id) => set({ activeProfileId: id }),

  activeEngine: 'qwen',
  setActiveEngine: (engine) => set({ activeEngine: engine }),

  activeVariant: 'default',
  setActiveVariant: (variant) => set({ activeVariant: variant }),

  activeTab: 'voices',
  setActiveTab: (tab) => set({ activeTab: tab }),

  backendReady: false,
  setBackendReady: (ready) => set({ backendReady: ready }),

  isSynthesizing: false,
  setIsSynthesizing: (v) => set({ isSynthesizing: v }),

  lastGenerationPath: null,
  setLastGenerationPath: (path) => set({ lastGenerationPath: path }),
}))
