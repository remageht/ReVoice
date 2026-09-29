import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { Play, Loader2, Volume2, Sparkles } from 'lucide-react'
import { toast } from 'sonner'

import { apiSynth, apiProfiles } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'

export function SynthesizeTab() {
  const { activeProfileId, setActiveProfileId, activeEngine, setActiveEngine } = useAppStore()
  const [text, setText] = useState('Привет! Это тестовая проверка клонирования голоса в студии ReVoice.')
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
      toast.success(`Синтез завершён: ${data.duration_sec?.toFixed(1)} сек`)
    },
    onError: (e: any) => {
      const msg = e.response?.data?.detail || e.message || 'Ошибка синтеза'
      toast.error(msg)
    },
  })

  const profile = profiles.find(p => p.id === activeProfileId)

  return (
    <div className="p-6 max-w-2xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <Play className="w-6 h-6 text-brand-400" />
          Синтез речи
        </h2>
        <p className="text-sm text-white/50 mt-1">
          Генерация речи выбранным голосом с использованием нейросетевых движков Qwen или Fish Speech.
        </p>
      </div>

      {/* Панель выбора голоса и движка */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Голос */}
        <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-2">
          <label className="block text-xs font-semibold uppercase tracking-wider text-white/60">
            Голосовой профиль
          </label>
          <select
            value={activeProfileId || ''}
            onChange={(e) => setActiveProfileId(e.target.value || null)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
          >
            <option value="">-- Выберите голос --</option>
            {profiles.map(p => (
              <option key={p.id} value={p.id}>
                {p.name} ({p.sample_count} сэмпл.)
              </option>
            ))}
          </select>
          {profile ? (
            <p className="text-xs text-brand-300">
              Выбран: {profile.name} ({profile.language.toUpperCase()})
            </p>
          ) : (
            <p className="text-xs text-amber-400/80">
              Создайте профиль и добавьте эталон во вкладке «Голоса»
            </p>
          )}
        </div>

        {/* Движок */}
        <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-2">
          <label className="block text-xs font-semibold uppercase tracking-wider text-white/60">
            Движок синтеза
          </label>
          <select
            value={activeEngine}
            onChange={(e) => setActiveEngine(e.target.value)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
          >
            <option value="qwen">Qwen3-TTS (0.6B / 1.7B, 24 кГц)</option>
            <option value="fish">Fish Speech 1.5 (DualAR, 44.1 кГц)</option>
          </select>
          <p className="text-xs text-white/40">
            {activeEngine === 'qwen'
              ? 'Qwen3-TTS: быстрая генерация с точной передачей акцента'
              : 'Fish Speech 1.5: студийное качество 44.1 кГц'}
          </p>
        </div>
      </div>

      {/* Текст для озвучки */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="block text-sm font-medium text-white/80">
            Текст для озвучки
          </label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => setText('Привет! Это тестовая проверка клонирования голоса в студии ReVoice.')}
              className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
            >
              Приветствие
            </button>
            <span className="text-white/20 text-xs">|</span>
            <button
              type="button"
              onClick={() => setText('В чащах юга жил-был цитрус — да, но фальшивый экземпляр! Съешь ещё этих мягких французских булок, да выпей чаю.')}
              className="text-xs text-brand-400 hover:text-brand-300 transition-colors"
            >
              Панграмма
            </button>
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Введите текст для озвучки..."
          rows={5}
          className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-3
                     text-white placeholder:text-white/30 resize-none
                     focus:outline-none focus:border-brand-500 transition-colors text-sm leading-relaxed"
        />
        <p className="text-xs text-white/30">{text.length} символов</p>
      </div>

      {/* Кнопка запуска */}
      <button
        onClick={() => synthesize()}
        disabled={isPending || !text.trim() || !activeProfileId}
        className="w-full h-12 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40
                   disabled:cursor-not-allowed flex items-center justify-center gap-2
                   font-semibold transition-all shadow-lg shadow-brand-600/20"
      >
        {isPending ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Синтезирую речь...
          </>
        ) : (
          <>
            <Play className="w-5 h-5" />
            Синтезировать голос
          </>
        )}
      </button>

      {/* Результат синтеза */}
      {lastResult && (
        <div className="rounded-xl border border-green-500/30 bg-green-950/20 p-5 space-y-3">
          <div className="flex items-center gap-2">
            <Volume2 className="w-5 h-5 text-green-400" />
            <p className="text-green-400 font-semibold text-sm">Синтез успешно завершён!</p>
          </div>
          <div className="text-xs text-white/70 space-y-1 font-mono">
            <p><span className="text-white/40">Длительность:</span> {lastResult.duration_sec?.toFixed(1)} сек</p>
            <p><span className="text-white/40">Движок:</span> {lastResult.engine}</p>
            <p><span className="text-white/40">Файл:</span> {lastResult.audio_path}</p>
          </div>
        </div>
      )}
    </div>
  )
}
