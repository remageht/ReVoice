import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Upload, Trash2, CheckCircle, XCircle, Mic2 } from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { toast } from 'sonner'
import { clsx } from 'clsx'

import { apiProfiles } from '../api/client'

interface Props {
  profileId: string
}

export function ProfileDetail({ profileId }: Props) {
  const qc = useQueryClient()
  const [refText, setRefText] = useState('')
  const [uploading, setUploading] = useState(false)

  const { data: profile } = useQuery({
    queryKey: ['profiles', profileId],
    queryFn: () => apiProfiles.get(profileId),
  })

  const deleteSampleMutation = useMutation({
    mutationFn: (sampleId: string) => apiProfiles.deleteSample(profileId, sampleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] })
      toast.success('Сэмпл удалён')
    },
  })

  const onDrop = useCallback(async (files: File[]) => {
    if (!refText.trim()) {
      toast.error('Введите дословный текст сэмпла перед загрузкой')
      return
    }
    const file = files[0]
    if (!file) return

    setUploading(true)
    try {
      const sample = await apiProfiles.addSample(profileId, file, refText)
      qc.invalidateQueries({ queryKey: ['profiles'] })
      if (sample.is_valid) {
        toast.success('Сэмпл добавлен ✓')
      } else {
        toast.warning(`Сэмпл отклонён: ${sample.rejection_reason}`)
      }
      setRefText('')
    } catch (e: any) {
      toast.error(e.response?.data?.detail || 'Ошибка загрузки')
    } finally {
      setUploading(false)
    }
  }, [profileId, refText, qc])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { 'audio/*': ['.wav', '.mp3', '.ogg', '.flac', '.m4a'] },
    maxFiles: 1,
    disabled: uploading,
  })

  if (!profile) return null

  return (
    <div className="p-6 max-w-2xl">
      <h2 className="text-2xl font-bold mb-1">{profile.name}</h2>
      <p className="text-white/40 text-sm mb-6">{profile.language.toUpperCase()} · {profile.sample_count} сэмпл.</p>

      {/* Add sample */}
      <div className="mb-6">
        <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Добавить эталон</h3>
        <textarea
          value={refText}
          onChange={e => setRefText(e.target.value)}
          placeholder="Дословный текст аудиозаписи (обязательно)..."
          rows={2}
          className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-3 text-sm
                     placeholder:text-white/20 resize-none focus:outline-none focus:border-brand-500 mb-3"
        />
        <div
          {...getRootProps()}
          className={clsx(
            'border-2 border-dashed rounded-xl p-6 text-center cursor-pointer transition-all',
            isDragActive ? 'border-brand-400 bg-brand-600/10' : 'border-white/10 hover:border-white/20'
          )}
        >
          <input {...getInputProps()} />
          <Upload className="w-6 h-6 text-white/30 mx-auto mb-2" />
          <p className="text-sm text-white/40">
            {isDragActive ? 'Отпустите файл...' : 'Перетащите аудио или нажмите'}
          </p>
          <p className="text-xs text-white/20 mt-1">WAV, MP3, FLAC, OGG · 3–30 сек</p>
        </div>
      </div>

      {/* Samples list */}
      {profile.samples.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-white/60 uppercase tracking-wider mb-3">Сэмплы</h3>
          <div className="space-y-2">
            {profile.samples.map(sample => (
              <div key={sample.id} className="flex items-start gap-3 p-3 rounded-xl bg-surface-1 border border-white/5">
                {sample.is_valid
                  ? <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
                  : <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />}
                <div className="flex-1 min-w-0">
                  <p className="text-sm truncate">{sample.reference_text}</p>
                  <p className="text-xs text-white/30">
                    {sample.duration_sec?.toFixed(1)}с · RMS {sample.rms_median?.toFixed(3)}
                  </p>
                  {!sample.is_valid && (
                    <p className="text-xs text-red-400 mt-0.5">{sample.rejection_reason}</p>
                  )}
                </div>
                <button
                  onClick={() => deleteSampleMutation.mutate(sample.id)}
                  className="text-white/20 hover:text-red-400 transition-colors shrink-0"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
