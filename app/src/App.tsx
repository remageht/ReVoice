import { useEffect, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Toaster } from 'sonner'
import { listen } from '@tauri-apps/api/event'

import { apiHealth } from './api/client'
import { useAppStore } from './store/useAppStore'
import { Sidebar } from './components/Sidebar'
import { VoicesTab } from './components/tabs/VoicesTab'
import { SynthesizeTab } from './components/tabs/SynthesizeTab'
import { BookTab } from './components/tabs/BookTab'
import { ModelsTab } from './components/tabs/ModelsTab'
import { HistoryTab } from './components/tabs/HistoryTab'
import { SettingsTab } from './components/tabs/SettingsTab'
import { BackendStatus } from './components/BackendStatus'

export default function App() {
  const { activeTab, setBackendReady, backendReady } = useAppStore()
  const [sidecarError, setSidecarError] = useState<string | null>(null)
  // Видимая диагностика health-опроса (иначе вечный спиннер без причины).
  const [healthNote, setHealthNote] = useState<string>('опрос не запускался')
  const [healthFails, setHealthFails] = useState<number>(0)

  // Poll backend health
  const { data: health, isSuccess, isError, error, dataUpdatedAt } = useQuery({
    queryKey: ['health'],
    queryFn: apiHealth.check,
    refetchInterval: 5000,
    retry: false,
  })

  useEffect(() => {
    const t = new Date().toLocaleTimeString('ru-RU')
    if (isSuccess && health?.status === 'ok') {
      setHealthNote(`ок ${t}`)
    } else if (isError) {
      const msg = error instanceof Error ? error.message : String(error)
      setHealthFails((n) => n + 1)
      setHealthNote(`ошибка ${t}: ${msg}`)
    } else {
      setHealthNote(`ожидание... ${t}`)
    }
  }, [isSuccess, isError, error, health, dataUpdatedAt])

  useEffect(() => {
    setBackendReady(isSuccess && health?.status === 'ok')
    if (isSuccess && health?.status === 'ok') {
      setSidecarError(null)
    }
  }, [isSuccess, health, setBackendReady])

  // Listen for Tauri sidecar events
  useEffect(() => {
    const unlisten1 = listen('sidecar-ready', () => {
      setBackendReady(true)
      setSidecarError(null)
    })
    const unlisten2 = listen<{ message: string }>('sidecar-error', (e) => {
      setSidecarError(e.payload.message)
    })
    return () => {
      unlisten1.then(f => f())
      unlisten2.then(f => f())
    }
  }, [setBackendReady])

  const renderTab = () => {
    switch (activeTab) {
      case 'voices': return <VoicesTab />
      case 'synthesize': return <SynthesizeTab />
      case 'book': return <BookTab />
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
            <BackendStatus error={sidecarError} diag={`${healthNote} (фейлов: ${healthFails})`} />
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
