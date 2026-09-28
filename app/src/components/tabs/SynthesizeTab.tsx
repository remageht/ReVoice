import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Play, Loader2, Volume2 } from 'lucide-react'
import { toast } from 'sonner'

import { apiSynth, apiProfiles } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'

export function SynthesizeTab() {
  const { activeProfileId, activeEngine } = useAppStore()
  const [text, setText] = useState('')
  const [lastResult, setLastResult] = useState<any>(null)

  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: apiProfiles.list,
  })

  const { mutate: synthesize, isPending } = useMutation({
    mutationFn: () => apiSynth.synthesize({
      profile_id: activeProfileId!,
      text,
      engine: activeEngine,
      language: 'ru',
    }),
    onSuccess: (data) => {
      setLastResult(data)
      toast.success(`Готово: ${data.duration_sec?.toFixed(1)}с`)
    },
    onError: (e: any) => {
      toast.error(e.response?.data?.detail || 'Ошибка синтеза')
    },
  })

  const profile = profiles.find(p => p.id === activeProfileId)

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h2 className="text-2xl font-bold mb-6">Синтез речи</h2>

      {!activeProfileId ? (
        <div className="rounded-xl border border-white/10 bg-surface-1 p-6 text-center">
          <p className="text-white/50">Выберите голосовой профиль во вкладке «Голоса»</p>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="rounded-xl border border-white/10 bg-surface-1 p-4">
            <p className="text-sm text-white/50 mb-1">Активный голос</p>
            <p className="font-medium">{profile?.name}</p>
          </div>

          <div>
            <label className="block text-sm text-white/60 mb-2">Текст для синтеза</label>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Введите текст для озвучки..."
              rows={6}
              className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-3
                         text-white placeholder:text-white/30 resize-none
                         focus:outline-none focus:border-brand-500 transition-colors"
            />
            <p className="text-xs text-white/30 mt-1">{text.length} символов</p>
          </div>

          <button
            onClick={() => synthesize()}
            disabled={isPending || !text.trim()}
            className="w-full h-12 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40
                       disabled:cursor-not-allowed flex items-center justify-center gap-2
                       font-semibold transition-all"
          >
            {isPending ? (
              <><Loader2 className="w-5 h-5 animate-spin" /> Синтез...</>
            ) : (
              <><Play className="w-5 h-5" /> Синтезировать</>  
            )}
          </button>

          {lastResult && (
            <div className="rounded-xl border border-green-500/30 bg-green-900/10 p-4">
              <div className="flex items-center gap-2 mb-2">
                <Volume2 className="w-4 h-4 text-green-400" />
                <p className="text-green-400 font-medium text-sm">Синтез завершён</p>
              </div>
              <p className="text-sm text-white/60">Длительность: {lastResult.duration_sec?.toFixed(1)}с</p>
              <p className="text-sm text-white/60">Путь: {lastResult.audio_path}</p>
            </div>
          )}
        </div>
      )}
    </div>
  )
}
