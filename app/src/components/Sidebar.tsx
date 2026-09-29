import { clsx } from 'clsx'
import {
  Mic2, Play, BookOpen, Cpu, History, Settings, Zap
} from 'lucide-react'
import { useAppStore } from '../store/useAppStore'

const TABS = [
  { id: 'voices',     label: 'Голоса',    icon: Mic2 },
  { id: 'synthesize', label: 'Синтез',    icon: Play },
  { id: 'book',       label: 'Книги',     icon: BookOpen },
  { id: 'models',     label: 'Модели',    icon: Cpu },
  { id: 'history',    label: 'История',   icon: History },
  { id: 'settings',  label: 'Настройки', icon: Settings },
] as const

export function Sidebar() {
  const { activeTab, setActiveTab, backendReady } = useAppStore()

  return (
    <aside className="w-16 flex flex-col bg-surface-1 border-r border-white/5 shrink-0">
      {/* Logo */}
      <div className="h-14 flex items-center justify-center border-b border-white/5">
        <Zap className="w-7 h-7 text-brand-400" />
      </div>

      {/* Nav */}
      <nav className="flex-1 flex flex-col gap-1 p-2 pt-3">
        {TABS.map(({ id, label, icon: Icon }) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            title={label}
            className={clsx(
              'w-12 h-12 rounded-xl flex flex-col items-center justify-center gap-0.5',
              'text-xs transition-all duration-150',
              activeTab === id
                ? 'bg-brand-600/30 text-brand-300'
                : 'text-white/40 hover:text-white/70 hover:bg-white/5'
            )}
          >
            <Icon className="w-5 h-5" />
          </button>
        ))}
      </nav>

      {/* Backend status dot */}
      <div className="h-14 flex items-center justify-center">
        <div
          title={backendReady ? 'Сервер запущен' : 'Сервер недоступен'}
          className={clsx(
            'w-2.5 h-2.5 rounded-full transition-colors',
            backendReady ? 'bg-green-400' : 'bg-red-400 animate-pulse'
          )}
        />
      </div>
    </aside>
  )
}
