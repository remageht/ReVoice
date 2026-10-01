import { useEffect, useState } from 'react'
import { listen } from '@tauri-apps/api/event'
import { Loader2, CheckCircle, AlertCircle, Download } from 'lucide-react'

interface BootstrapProgress {
  step: string
  pct: number
  message: string
}

interface BackendStatusProps {
  error?: string | null
  diag?: string | null
}

export function BackendStatus({ error, diag }: BackendStatusProps) {
  const [progress, setProgress] = useState<BootstrapProgress | null>(null)
  const [isBootstrapping, setIsBootstrapping] = useState(false)
  const [spinnerSeconds, setSpinnerSeconds] = useState(0)

  useEffect(() => {
    const timer = setInterval(() => {
      setSpinnerSeconds((s) => s + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    const unlisten1 = listen<BootstrapProgress>('bootstrap-progress', (e) => {
      setProgress(e.payload)
      setIsBootstrapping(true)
    })
    const unlisten2 = listen('bootstrap-start', () => {
      setIsBootstrapping(true)
    })
    return () => {
      unlisten1.then(f => f())
      unlisten2.then(f => f())
    }
  }, [])

  if (error) {
    return (
      <div className="text-center space-y-4 max-w-md p-6">
        <AlertCircle className="w-12 h-12 text-red-400 mx-auto" />
        <div>
          <p className="text-white font-semibold text-lg">Бэкенд не запустился</p>
          <p className="text-white/60 text-sm mt-2 font-mono break-all">{error}</p>
        </div>
        <p className="text-white/40 text-xs">
          Попробуйте перезапустить приложение. Если ошибка повторяется — удалите папку
          <span className="font-mono mx-1">%APPDATA%\Revoice\runtime</span>
          и запустите снова.
        </p>
      </div>
    )
  }

  if (isBootstrapping && progress) {
    const isDone = progress.pct >= 100
    return (
      <div className="text-center space-y-6 max-w-sm p-6">
        {isDone
          ? <CheckCircle className="w-10 h-10 text-green-400 mx-auto" />
          : <Download className="w-10 h-10 text-brand-400 animate-pulse mx-auto" />
        }
        <div>
          <p className="text-white font-semibold text-lg">
            {isDone ? 'Окружение готово!' : 'Первый запуск'}
          </p>
          <p className="text-white/60 text-sm mt-1">{progress.message}</p>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-white/10 rounded-full h-2 overflow-hidden">
          <div
            className="h-2 rounded-full bg-brand-400 transition-all duration-300"
            style={{ width: `${progress.pct}%` }}
          />
        </div>
        <p className="text-white/40 text-xs">{progress.pct}%</p>

        {!isDone && (
          <p className="text-white/30 text-xs">
            Это займёт несколько минут только один раз.
          </p>
        )}
      </div>
    )
  }

  // Default: just loading spinner + live diagnostics line
  return (
    <div className="text-center space-y-4">
      <Loader2 className="w-10 h-10 text-brand-400 animate-spin mx-auto" />
      <div>
        <p className="text-white font-semibold text-lg">Запускаем бэкенд...</p>
        <p className="text-white/50 text-sm mt-1">
          Python-сервер стартует, подождите{spinnerSeconds >= 5 ? ` (${spinnerSeconds}с)` : ''}
        </p>
        {(spinnerSeconds >= 15 || diag?.startsWith('ошибка')) && (
          <p className="text-white/40 text-xs mt-3 font-mono break-all">
            {diag || `ожидание отклика ${spinnerSeconds}с...`}
          </p>
        )}
      </div>
    </div>
  )
}
