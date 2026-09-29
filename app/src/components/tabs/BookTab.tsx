import { useState } from 'react'
import { useMutation, useQuery } from '@tanstack/react-query'
import { BookOpen, Sparkles, Play, Loader2, CheckCircle2, FileText, Upload } from 'lucide-react'
import { toast } from 'sonner'
import { clsx } from 'clsx'

import { apiBook, apiProfiles, apiModels } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'

export function BookTab() {
  const { activeProfileId, setActiveProfileId, activeEngine, setActiveEngine } = useAppStore()
  const [bookTitle, setBookTitle] = useState('Моя книга')
  const [author, setAuthor] = useState('ReVoice')
  const [chapterTitle, setChapterTitle] = useState('Глава 1')
  const [text, setText] = useState('')
  const [intensity, setIntensity] = useState<'subtle' | 'moderate' | 'dramatic'>('moderate')
  const [result, setResult] = useState<{
    output_path: string
    total_duration_sec: number
    chapters_count: number
  } | null>(null)

  const { data: profiles = [] } = useQuery({
    queryKey: ['profiles'],
    queryFn: apiProfiles.list,
  })

  const { data: models = [] } = useQuery({
    queryKey: ['models'],
    queryFn: apiModels.list,
  })

  // Авторазметка эмоций и пауз
  const markupMutation = useMutation({
    mutationFn: () => apiBook.markup(text, intensity),
    onSuccess: (data) => {
      setText(data.marked_up)
      toast.success('Текст размечен под выразительное чтение!')
    },
    onError: (e: any) => {
      toast.error(e.response?.data?.detail || 'Не удалось разметить текст')
    },
  })

  // Синтез книги в M4B
  const synthMutation = useMutation({
    mutationFn: () => apiBook.synthesizeBook({
      profile_id: activeProfileId!,
      chapters: [{ title: chapterTitle || 'Глава 1', text }],
      engine: activeEngine,
      language: 'ru',
      book_title: bookTitle || 'Моя книга',
      author: author || 'ReVoice',
    }),
    onSuccess: (data) => {
      setResult(data)
      toast.success(`Аудиокнига M4B готова! (${data.total_duration_sec} сек)`)
    },
    onError: (e: any) => {
      toast.error(e.response?.data?.detail || 'Ошибка синтеза аудиокниги')
    },
  })

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = (event) => {
      const content = event.target?.result as string
      if (content) {
        setText(content)
        const nameWithoutExt = file.name.replace(/\.[^/.]+$/, '')
        setChapterTitle(nameWithoutExt)
        toast.success(`Загружен файл: ${file.name}`)
      }
    }
    reader.readAsText(file, 'utf-8')
  }

  const activeProfile = profiles.find(p => p.id === activeProfileId)
  const ttsModels = models.filter(m => m.type === 'TTS')

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <div>
        <h2 className="text-2xl font-bold flex items-center gap-2">
          <BookOpen className="w-6 h-6 text-brand-400" />
          Озвучка книг (M4B)
        </h2>
        <p className="text-sm text-white/50 mt-1">
          Создание аудиокниг с оглавлением, разметкой пауз и эмоций для плееров Apple Books, Smart AudioBook и других.
        </p>
      </div>

      {/* Параметры книги и голос */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* Выбор голоса */}
        <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-2">
          <label className="block text-xs font-semibold uppercase tracking-wider text-white/60">
            Голос диктора
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
          {activeProfile && (
            <p className="text-xs text-brand-300">
              Выбран: {activeProfile.name} ({activeProfile.language.toUpperCase()})
            </p>
          )}
        </div>

        {/* Выбор движка */}
        <div className="rounded-xl border border-white/10 bg-surface-1 p-4 space-y-2">
          <label className="block text-xs font-semibold uppercase tracking-wider text-white/60">
            Движок синтеза
          </label>
          <select
            value={activeEngine}
            onChange={(e) => setActiveEngine(e.target.value)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
          >
            <option value="qwen">Qwen3-TTS (0.6B / 1.7B)</option>
            <option value="fish">Fish Speech 1.5 (44.1 кГц)</option>
          </select>
          <p className="text-xs text-white/40">
            {activeEngine === 'qwen'
              ? 'Qwen3-TTS: быстрая генерация с точной передачей акцента'
              : 'Fish Speech 1.5: студийное качество 44.1 кГц'}
          </p>
        </div>
      </div>

      {/* Метаданные книги */}
      <div className="rounded-xl border border-white/10 bg-surface-1 p-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <div>
          <label className="block text-xs text-white/50 mb-1">Название книги</label>
          <input
            type="text"
            value={bookTitle}
            onChange={(e) => setBookTitle(e.target.value)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
            placeholder="Название аудиокниги"
          />
        </div>
        <div>
          <label className="block text-xs text-white/50 mb-1">Автор</label>
          <input
            type="text"
            value={author}
            onChange={(e) => setAuthor(e.target.value)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
            placeholder="Имя автора"
          />
        </div>
        <div>
          <label className="block text-xs text-white/50 mb-1">Название главы</label>
          <input
            type="text"
            value={chapterTitle}
            onChange={(e) => setChapterTitle(e.target.value)}
            className="w-full bg-surface-2 border border-white/10 rounded-lg px-3 py-2 text-sm text-white focus:outline-none focus:border-brand-500"
            placeholder="Глава 1: Вступление"
          />
        </div>
      </div>

      {/* Текст главы */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label className="text-sm font-medium text-white/80">
            Текст главы для озвучки
          </label>
          <div className="flex items-center gap-2">
            <label className="cursor-pointer text-xs text-brand-300 hover:text-brand-200 flex items-center gap-1">
              <Upload className="w-3.5 h-3.5" />
              Загрузить TXT / MD
              <input
                type="file"
                accept=".txt,.md,.markdown"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
            <span className="text-xs text-white/30">|</span>
            <span className="text-xs text-white/40">{text.length} символов</span>
          </div>
        </div>

        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="Вставьте текст главы или книги..."
          rows={8}
          className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-3 text-white placeholder:text-white/20 resize-none focus:outline-none focus:border-brand-500 transition-colors font-sans text-sm leading-relaxed"
        />

        {/* Панель авторазметки */}
        <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-xl bg-surface-1 border border-white/5">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <span className="text-xs text-white/70 font-medium">Авторазметка:</span>
            <select
              value={intensity}
              onChange={(e) => setIntensity(e.target.value as any)}
              className="bg-surface-2 border border-white/10 rounded px-2 py-1 text-xs text-white"
            >
              <option value="subtle">Сдержанная (документалистика)</option>
              <option value="moderate">Умеренная (художественная)</option>
              <option value="dramatic">Драматическая (эмоциональная)</option>
            </select>
          </div>
          <button
            onClick={() => markupMutation.mutate()}
            disabled={markupMutation.isPending || !text.trim()}
            className="px-3 py-1.5 rounded-lg bg-white/5 hover:bg-white/10 text-xs font-medium text-amber-300 border border-amber-500/20 disabled:opacity-40 flex items-center gap-1.5 transition-colors"
          >
            {markupMutation.isPending ? (
              <Loader2 className="w-3 h-3 animate-spin" />
            ) : (
              <Sparkles className="w-3 h-3" />
            )}
            Расставить паузы и интонации
          </button>
        </div>
      </div>

      {/* Кнопка синтеза */}
      <button
        onClick={() => synthMutation.mutate()}
        disabled={synthMutation.isPending || !text.trim() || !activeProfileId}
        className="w-full h-12 rounded-xl bg-brand-600 hover:bg-brand-500 disabled:opacity-40 disabled:cursor-not-allowed flex items-center justify-center gap-2 font-semibold transition-all shadow-lg shadow-brand-600/20"
      >
        {synthMutation.isPending ? (
          <>
            <Loader2 className="w-5 h-5 animate-spin" />
            Синтез аудиокниги и сборка M4B...
          </>
        ) : (
          <>
            <Play className="w-5 h-5" />
            Озвучить главу и собрать M4B
          </>
        )}
      </button>

      {/* Результат */}
      {result && (
        <div className="rounded-xl border border-green-500/30 bg-green-950/20 p-5 space-y-3">
          <div className="flex items-center gap-2 text-green-400 font-semibold text-sm">
            <CheckCircle2 className="w-5 h-5" />
            Аудиокнига успешно собрана в формате M4B!
          </div>
          <div className="text-xs text-white/70 space-y-1 font-mono">
            <p><span className="text-white/40">Файл:</span> {result.output_path}</p>
            <p><span className="text-white/40">Длительность:</span> {result.total_duration_sec} сек</p>
            <p><span className="text-white/40">Глав:</span> {result.chapters_count}</p>
          </div>
        </div>
      )}
    </div>
  )
}
