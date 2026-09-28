import { useState, useCallback } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Upload,
  Trash2,
  CheckCircle,
  XCircle,
  Activity,
  Volume2,
  AlertTriangle,
} from 'lucide-react'
import { useDropzone } from 'react-dropzone'
import { toast } from 'sonner'
import { clsx } from 'clsx'

import { apiProfiles, Sample } from '../api/client'

interface Props {
  profileId: string
}

export function ProfileDetail({ profileId }: Props) {
  const qc = useQueryClient()
  const [refText, setRefText] = useState('')
  const [uploading, setUploading] = useState(false)
  const [selectedSample, setSelectedSample] = useState<Sample | null>(null)

  const { data: profile } = useQuery({
    queryKey: ['profiles', profileId],
    queryFn: () => apiProfiles.get(profileId),
  })

  const deleteSampleMutation = useMutation({
    mutationFn: (sampleId: string) => apiProfiles.deleteSample(profileId, sampleId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['profiles'] })
      toast.success('Сэмпл удалён')
      setSelectedSample(null)
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
        toast.success(`Эталон принят: ${sample.verdict || 'Годен к синтезу'}`)
      } else {
        toast.error(`Сэмпл отклонён: ${sample.rejection_reason}`)
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
    <div className="p-6 max-w-4xl space-y-6">
      <div>
        <h2 className="text-2xl font-bold text-white">{profile.name}</h2>
        <p className="text-white/40 text-sm mt-0.5">
          {profile.language.toUpperCase()} · {profile.sample_count} эталонных сэмплов · {profile.generation_count} генераций
        </p>
      </div>

      {/* Add sample section */}
      <div className="bg-surface-1 border border-white/10 rounded-2xl p-5 space-y-3">
        <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wider">
          Добавить эталонный сэмпл (3–30 сек)
        </h3>
        <textarea
          value={refText}
          onChange={e => setRefText(e.target.value)}
          placeholder="Дословный текст аудиозаписи (до буквы совпадает с речью в аудио)..."
          rows={2}
          className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-3 text-sm
                     placeholder:text-white/20 resize-none focus:outline-none focus:border-brand-500"
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
          <p className="text-sm text-white/60">
            {isDragActive ? 'Отпустите аудиофайл...' : 'Перетащите аудио сюда или нажмите для выбора'}
          </p>
          <p className="text-xs text-white/30 mt-1">WAV, MP3, FLAC, OGG · Автоматическая проверка качества</p>
        </div>
      </div>

      {/* Diagnostics / Samples Section */}
      {profile.samples.length > 0 && (
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <h3 className="text-xs font-semibold text-white/60 uppercase tracking-wider flex items-center gap-2">
              <Activity className="w-4 h-4 text-brand-400" />
              Экран диагностики эталонов
            </h3>
            <span className="text-xs text-white/40">
              Валидация: длительность ≥ 3с, RMS ≥ 0.02, SR ≥ 16 кГц
            </span>
          </div>

          <div className="grid gap-3">
            {profile.samples.map(sample => (
              <div
                key={sample.id}
                className={clsx(
                  'rounded-2xl border p-4 transition-all bg-surface-1',
                  sample.is_valid
                    ? 'border-green-500/20 hover:border-green-500/40'
                    : 'border-red-500/20 bg-red-950/10'
                )}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex items-start gap-3 flex-1 min-w-0">
                    {sample.is_valid ? (
                      <CheckCircle className="w-5 h-5 text-green-400 shrink-0 mt-0.5" />
                    ) : (
                      <XCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
                    )}
                    <div className="flex-1 min-w-0">
                      <p className="text-sm text-white font-medium italic">«{sample.reference_text}»</p>
                      
                      {/* Verdict */}
                      <p className={clsx(
                        'text-xs mt-1.5 font-medium flex items-center gap-1.5',
                        sample.is_valid ? 'text-green-300' : 'text-red-400'
                      )}>
                        {sample.is_valid ? (
                          <>
                            <span className="w-2 h-2 rounded-full bg-green-400 shrink-0" />
                            Вердикт: {sample.verdict || 'Годен к синтезу'}
                          </>
                        ) : (
                          <>
                            <AlertTriangle className="w-3.5 h-3.5 shrink-0" />
                            {sample.rejection_reason}
                          </>
                        )}
                      </p>

                      {/* RMS Profile waveform visualization */}
                      {sample.rms_profile && sample.rms_profile.length > 0 && (
                        <div className="mt-3 bg-surface-2/60 rounded-xl p-2.5">
                          <p className="text-[10px] text-white/40 uppercase tracking-wider mb-1 font-mono">
                            RMS-профиль громкости во времени
                          </p>
                          <div className="h-8 flex items-end gap-0.5 w-full">
                            {sample.rms_profile.map((val, idx) => {
                              const heightPct = Math.min(100, Math.max(8, (val / 0.15) * 100))
                              return (
                                <div
                                  key={idx}
                                  className="flex-1 rounded-t-sm transition-all bg-brand-500/60 hover:bg-brand-400"
                                  style={{ height: `${heightPct}%` }}
                                  title={`t=${idx}: RMS ${val.toFixed(3)}`}
                                />
                              )
                            })}
                          </div>
                        </div>
                      )}

                      {/* Diagnostic badges */}
                      <div className="flex flex-wrap gap-2 mt-3 text-xs">
                        <span className="bg-surface-2 px-2.5 py-1 rounded-lg text-white/70 font-mono">
                          {sample.duration_sec?.toFixed(2)} сек
                        </span>
                        <span className="bg-surface-2 px-2.5 py-1 rounded-lg text-white/70 font-mono">
                          RMS: {sample.rms_median?.toFixed(3)}
                        </span>
                        {sample.peak !== undefined && (
                          <span className="bg-surface-2 px-2.5 py-1 rounded-lg text-white/70 font-mono">
                            Пик: {sample.peak?.toFixed(2)}
                          </span>
                        )}
                        {sample.sample_rate && (
                          <span className="bg-surface-2 px-2.5 py-1 rounded-lg text-white/70 font-mono">
                            {sample.sample_rate} Гц
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  <button
                    onClick={() => deleteSampleMutation.mutate(sample.id)}
                    title="Удалить сэмпл"
                    className="p-2 rounded-lg text-white/20 hover:text-red-400 hover:bg-white/5 transition-colors"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}
