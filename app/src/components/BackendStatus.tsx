import { Loader2, AlertCircle } from 'lucide-react'

export function BackendStatus() {
  return (
    <div className="text-center space-y-4">
      <Loader2 className="w-10 h-10 text-brand-400 animate-spin mx-auto" />
      <div>
        <p className="text-white font-semibold text-lg">Запускаем движок...</p>
        <p className="text-white/50 text-sm mt-1">
          Python-бэкенд стартует, подождите
        </p>
      </div>
    </div>
  )
}
