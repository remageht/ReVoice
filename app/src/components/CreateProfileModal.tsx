import { useState } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X } from 'lucide-react'
import { toast } from 'sonner'
import { apiProfiles, getLastTransport, formatWithTransport } from '../api/client'
import { useAppStore } from '../store/useAppStore'

const LANGUAGES = [
  { code: 'ru', label: 'Русский' },
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
  { code: 'de', label: 'Deutsch' },
  { code: 'fr', label: 'Français' },
]

interface Props {
  onClose: () => void
}

export function CreateProfileModal({ onClose }: Props) {
  const qc = useQueryClient()
  const { setActiveProfileId } = useAppStore()
  const [name, setName] = useState('')
  const [desc, setDesc] = useState('')
  const [lang, setLang] = useState('ru')

  const { mutate, isPending } = useMutation({
    mutationFn: () => apiProfiles.create({ name, description: desc, language: lang }),
    onSuccess: (profile) => {
      qc.invalidateQueries({ queryKey: ['profiles'] })
      setActiveProfileId(profile.id)
      toast.success(`Профиль создан [${getLastTransport()}]`)
      onClose()
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка создания профиля'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  return (
    <div className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-surface-1 border border-white/10 rounded-2xl p-6 w-full max-w-md shadow-2xl">
        <div className="flex items-center justify-between mb-5">
          <h2 className="text-lg font-bold">Новый голос</h2>
          <button onClick={onClose} className="text-white/40 hover:text-white transition-colors">
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="space-y-4">
          <div>
            <label className="block text-sm text-white/60 mb-1.5">Название</label>
            <input
              value={name}
              onChange={e => setName(e.target.value)}
              placeholder="Мой голос"
              className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-2.5 text-sm
                         placeholder:text-white/20 focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-1.5">Описание (опционально)</label>
            <input
              value={desc}
              onChange={e => setDesc(e.target.value)}
              placeholder="Для чего этот голос?"
              className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-2.5 text-sm
                         placeholder:text-white/20 focus:outline-none focus:border-brand-500"
            />
          </div>
          <div>
            <label className="block text-sm text-white/60 mb-1.5">Язык</label>
            <select
              value={lang}
              onChange={e => setLang(e.target.value)}
              className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-2.5 text-sm
                         focus:outline-none focus:border-brand-500"
            >
              {LANGUAGES.map(l => (
                <option key={l.code} value={l.code}>{l.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div className="flex gap-3 mt-6">
          <button
            onClick={onClose}
            className="flex-1 h-10 rounded-xl border border-white/10 text-white/60 hover:text-white
                       hover:border-white/20 text-sm transition-all"
          >
            Отмена
          </button>
          <button
            onClick={() => mutate()}
            disabled={isPending || !name.trim()}
            className="flex-1 h-10 rounded-xl bg-brand-600 hover:bg-brand-500 text-sm font-semibold
                       disabled:opacity-40 disabled:cursor-not-allowed transition-all"
          >
            {isPending ? 'Создание...' : 'Создать'}
          </button>
        </div>
      </div>
    </div>
  )
}
