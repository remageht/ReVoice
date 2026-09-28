import { useEffect } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { listen } from '@tauri-apps/api/event'

import { apiHealth } from './api/client'
import { useAppStore } from './store/useAppStore'
import { Sidebar } from './components/Sidebar'
import { VoicesTab } from './components/tabs/VoicesTab'
import { SynthesizeTab } from './components/tabs/SynthesizeTab'
import { ModelsTab } from './components/tabs/ModelsTab'
import { HistoryTab } from './components/tabs/HistoryTab'
import { SettingsTab } from './components/tabs/SettingsTab'
import { BackendStatus } from './components/BackendStatus'

export default function App() {
  const { activeTab, setBackendReady, backendReady, setActiveProfileId } = useAppStore()

  // Poll backend health
  const { data: health, isSuccess } = useQuery({
    queryKey: ['health'],
    queryFn: apiHealth.check,
    refetchInterval: 5000,
    retry: false,
  })

  useEffect(() => {
    setBackendReady(isSuccess && health?.status === 'ok')
  }, [isSuccess, health, setBackendReady])

  // Listen for Tauri sidecar events
  useEffect(() => {
    const unlisten1 = listen('sidecar-ready', () => setBackendReady(true))
    const unlisten2 = listen('sidecar-error', (e: any) => {
      console.error('Sidecar error:', e.payload)
    })
    return () => {
      unlisten1.then(f => f())
      unlisten2.then(f => f())
    }
  }, [])

  const renderTab = () => {
    switch (activeTab) {
      case 'voices': return <VoicesTab />
      case 'synthesize': return <SynthesizeTab />
      case 'models': return <ModelsTab />
      case 'history': return <HistoryTab />
      case 'settings': return <SettingsTab />
      default: return <VoicesTab />
    }
  }

  return (
    <div className="flex h-screen w-screen bg-surface text-white overflow-hidden">
      <Sidebar />
      <main className="flex-1 overflow-hidden relative">
        {!backendReady && (
          <div className="absolute inset-0 bg-surface/80 backdrop-blur-sm z-50 flex items-center justify-center">
            <BackendStatus />
          </div>
        )}
        <div className="h-full overflow-y-auto">
          {renderTab()}
        </div>
      </main>
      <Toaster theme="dark" position="bottom-right" />
    </div>
  )
}
