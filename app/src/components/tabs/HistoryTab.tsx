import { useQuery } from '@tanstack/react-query'
import { Clock, Volume2 } from 'lucide-react'
import { apiSynth } from '../../api/client'

export function HistoryTab() {
  const { data: history = [] } = useQuery({
    queryKey: ['history'],
    queryFn: () => apiSynth.history(undefined, 50),
    refetchInterval: 5000,
  })

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-6">История генераций</h2>
      {history.length === 0 ? (
        <div className="text-center py-16">
          <Clock className="w-10 h-10 text-white/20 mx-auto mb-3" />
          <p className="text-white/30">История пуста — синтезируйте первую запись</p>
        </div>
      ) : (
        <div className="space-y-2">
          {history.map((item: any) => (
            <div key={item.id} className="rounded-xl bg-surface-1 border border-white/5 px-4 py-3 flex items-center gap-4">
              <Volume2 className="w-4 h-4 text-brand-400 shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm truncate">{item.text}</p>
                <p className="text-xs text-white/30">{item.engine} · {item.language} · {item.duration_sec?.toFixed(1)}с</p>
              </div>
              <span className="text-xs text-white/30 shrink-0">
                {new Date(item.created_at).toLocaleString('ru')}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
