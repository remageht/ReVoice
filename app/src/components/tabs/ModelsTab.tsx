import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Download,
  FolderOpen,
  FolderSymlink,
  Cpu,
  Loader2,
  CheckCircle,
  AlertTriangle,
  XCircle,
  HardDrive,
  RefreshCw,
  FolderEdit,
  X,
} from 'lucide-react'
import { toast } from 'sonner'
import { clsx } from 'clsx'
import { apiModels, ModelItem, getLastTransport, formatWithTransport } from '../../api/client'

export function ModelsTab() {
  const qc = useQueryClient()
  const [selectedModelForPath, setSelectedModelForPath] = useState<ModelItem | null>(null)
  const [customPathInput, setCustomPathInput] = useState('')
  const [validationError, setValidationError] = useState<string | null>(null)
  const [showDirModal, setShowDirModal] = useState(false)
  const [newDirInput, setNewDirInput] = useState('')
  const [moveFilesCheck, setMoveFilesCheck] = useState(true)

  // 1. Models list query
  const { data: models = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: apiModels.list,
    refetchInterval: 3000,
  })

  // 2. Directory query
  const { data: dirInfo } = useQuery({
    queryKey: ['models-dir'],
    queryFn: apiModels.getDir,
  })

  // Mutations
  const downloadMutation = useMutation({
    mutationFn: (id: string) => apiModels.download(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['models'] })
      toast.success(`Скачивание запущено (с поддержкой докачки) [${getLastTransport()}]`)
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка запуска скачивания'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  const loadMutation = useMutation({
    mutationFn: (id: string) => apiModels.load(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['models'] })
      toast.success(`Модель загружена в VRAM (предыдущие выгружены) [${getLastTransport()}]`)
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка загрузки'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  const unloadMutation = useMutation({
    mutationFn: (id: string) => apiModels.unload(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['models'] })
      toast.success(`Модель выгружена, VRAM освобождён [${getLastTransport()}]`)
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка выгрузки'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  const openFolderMutation = useMutation({
    mutationFn: (id: string) => apiModels.openFolder(id),
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Не удалось открыть папку'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  const setPathMutation = useMutation({
    mutationFn: ({ id, path }: { id: string; path: string }) => apiModels.setPath(id, path),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['models'] })
      if (data.warning) {
        toast.warning(data.warning)
      } else {
        toast.success(`Путь успешно привязан [${getLastTransport()}]`)
      }
      setSelectedModelForPath(null)
      setCustomPathInput('')
      setValidationError(null)
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка валидации папки'
      setValidationError(formatWithTransport(detail, e.transport || getLastTransport()))
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  const migrateDirMutation = useMutation({
    mutationFn: ({ newDir, moveFiles }: { newDir: string; moveFiles: boolean }) =>
      apiModels.migrateDir(newDir, moveFiles),
    onSuccess: (data) => {
      qc.invalidateQueries({ queryKey: ['models-dir'] })
      qc.invalidateQueries({ queryKey: ['models'] })
      toast.success(`Папка обновлена (перенесено файлов: ${data.migrated_count}) [${getLastTransport()}]`)
      setShowDirModal(false)
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail || e.message || 'Ошибка переноса папки'
      toast.error(formatWithTransport(detail, e.transport || getLastTransport()))
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <Loader2 className="animate-spin text-brand-400 w-8 h-8" />
      </div>
    )
  }

  return (
    <div className="p-6 max-w-6xl mx-auto space-y-6">
      {/* Header & Models Directory Setting */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 bg-surface-1 border border-white/10 rounded-2xl p-5">
        <div>
          <div className="flex items-center gap-2">
            <HardDrive className="w-5 h-5 text-brand-400" />
            <h2 className="text-lg font-bold">Папка моделей</h2>
            {dirInfo?.is_env_overridden && (
              <span className="text-xs bg-amber-500/20 text-amber-300 px-2 py-0.5 rounded font-mono">
                REVOICE_MODELS_DIR
              </span>
            )}
          </div>
          <p className="text-xs text-white/50 font-mono mt-1 truncate max-w-xl">
            {dirInfo?.models_dir || 'Загрузка...'}
          </p>
        </div>
        <button
          onClick={() => {
            setNewDirInput(dirInfo?.models_dir || '')
            setShowDirModal(true)
          }}
          className="flex items-center gap-2 px-4 py-2 rounded-xl bg-surface-2 hover:bg-surface-3 border border-white/10 text-sm font-medium transition-colors"
        >
          <FolderEdit className="w-4 h-4 text-brand-400" />
          Изменить папку
        </button>
      </div>

      {/* Models Table */}
      <div className="bg-surface-1 border border-white/10 rounded-2xl overflow-hidden shadow-xl">
        <div className="p-4 border-b border-white/5 flex items-center justify-between">
          <div>
            <h3 className="font-bold text-base">Каталог моделей</h3>
            <p className="text-xs text-white/40 mt-0.5">
              Модели не встроены в бандл. Загружаются на диск по запросу или подключаются вручную.
            </p>
          </div>
          <span className="text-xs text-white/30">Лимит VRAM: 1 активная модель</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="bg-surface-2/50 text-white/50 text-xs uppercase tracking-wider border-b border-white/5">
              <tr>
                <th className="py-3 px-4">Модель</th>
                <th className="py-3 px-4">Тип</th>
                <th className="py-3 px-4">Размер</th>
                <th className="py-3 px-4">Статус на диске</th>
                <th className="py-3 px-4">Память (VRAM)</th>
                <th className="py-3 px-4 text-right">Действия</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {models.map((m) => {
                const isDownloading = m.download?.status === 'downloading'
                return (
                  <tr key={m.id} className="hover:bg-white/[0.02] transition-colors">
                    {/* Model info */}
                    <td className="py-4 px-4 max-w-xs">
                      <div className="flex items-start gap-2.5">
                        <div className="w-8 h-8 rounded-lg bg-brand-600/20 flex items-center justify-center shrink-0 mt-0.5">
                          <Cpu className="w-4 h-4 text-brand-400" />
                        </div>
                        <div>
                          <p className="font-semibold text-white truncate">{m.name}</p>
                          <p className="text-xs text-white/40 line-clamp-1">{m.description}</p>
                          {m.is_custom_path && (
                            <span className="inline-block mt-1 text-[10px] bg-blue-500/20 text-blue-300 px-1.5 py-0.2 rounded font-mono truncate max-w-[200px]" title={m.local_path}>
                              Пользовательский путь
                            </span>
                          )}
                          {m.validation_warning && (
                            <p className="text-[10px] text-amber-400 flex items-center gap-1 mt-0.5">
                              <AlertTriangle className="w-3 h-3 shrink-0" />
                              {m.validation_warning}
                            </p>
                          )}
                        </div>
                      </div>
                    </td>

                    {/* Type badge */}
                    <td className="py-4 px-4">
                      <span className={clsx(
                        'text-xs px-2 py-0.5 rounded font-mono font-medium',
                        m.type === 'TTS' && 'bg-purple-500/20 text-purple-300',
                        m.type === 'STT' && 'bg-cyan-500/20 text-cyan-300',
                        m.type === 'LLM' && 'bg-emerald-500/20 text-emerald-300',
                      )}>
                        {m.type}
                      </span>
                    </td>

                    {/* Size */}
                    <td className="py-4 px-4 text-white/70 font-mono text-xs">
                      {m.size_mb} МБ
                    </td>

                    {/* Disk Status */}
                    <td className="py-4 px-4">
                      {isDownloading ? (
                        <div className="space-y-1">
                          <div className="flex items-center gap-1.5 text-xs text-brand-300 font-medium">
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            Скачивание...
                          </div>
                          <div className="w-24 h-1.5 bg-surface-3 rounded-full overflow-hidden">
                            <div className="h-full bg-brand-500 animate-pulse w-full" />
                          </div>
                        </div>
                      ) : m.disk_status === 'downloaded' ? (
                        <span className="inline-flex items-center gap-1 text-xs text-green-400 bg-green-500/10 px-2 py-0.5 rounded">
                          <CheckCircle className="w-3.5 h-3.5" />
                          Готова
                        </span>
                      ) : m.disk_status === 'partial' ? (
                        <span className="inline-flex items-center gap-1 text-xs text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded">
                          <AlertTriangle className="w-3.5 h-3.5" />
                          Частично
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-xs text-white/40 bg-white/5 px-2 py-0.5 rounded">
                          <XCircle className="w-3.5 h-3.5" />
                          Не скачана
                        </span>
                      )}
                    </td>

                    {/* VRAM status */}
                    <td className="py-4 px-4">
                      {m.is_loaded ? (
                        <span className="inline-flex items-center gap-1 text-xs text-green-300 bg-green-500/20 px-2 py-0.5 rounded font-medium animate-pulse">
                          В VRAM ⚡
                        </span>
                      ) : (
                        <span className="text-xs text-white/30">—</span>
                      )}
                    </td>

                    {/* Actions */}
                    <td className="py-4 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        {/* Download button */}
                        {m.size_mb > 0 && m.disk_status !== 'downloaded' && (
                          <button
                            onClick={() => downloadMutation.mutate(m.id)}
                            disabled={isDownloading || downloadMutation.isPending}
                            title="Скачать с HuggingFace (с поддержкой докачки)"
                            className="px-2.5 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500 text-xs font-medium flex items-center gap-1 transition-colors disabled:opacity-50"
                          >
                            <Download className="w-3.5 h-3.5" />
                            {m.disk_status === 'partial' ? 'Докачать' : 'Скачать'}
                          </button>
                        )}

                        {/* Set custom path button */}
                        {m.size_mb > 0 && (
                          <button
                            onClick={() => {
                              setSelectedModelForPath(m)
                              setCustomPathInput(m.local_path || '')
                              setValidationError(null)
                            }}
                            title="Указать путь к существующей папке модели"
                            className="px-2.5 py-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 border border-white/10 text-xs font-medium flex items-center gap-1 text-white/80 transition-colors"
                          >
                            <FolderSymlink className="w-3.5 h-3.5" />
                            Указать путь
                          </button>
                        )}

                        {/* Open folder button */}
                        <button
                          onClick={() => openFolderMutation.mutate(m.id)}
                          title="Открыть папку модели в Проводнике"
                          className="p-1.5 rounded-lg bg-surface-2 hover:bg-surface-3 border border-white/10 text-white/60 hover:text-white transition-colors"
                        >
                          <FolderOpen className="w-3.5 h-3.5" />
                        </button>

                        {/* Load / Unload button */}
                        {m.is_loaded ? (
                          <button
                            onClick={() => unloadMutation.mutate(m.id)}
                            disabled={unloadMutation.isPending}
                            title="Выгрузить из VRAM"
                            className="px-2.5 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 text-xs font-medium transition-colors"
                          >
                            Выгрузить
                          </button>
                        ) : m.disk_status === 'downloaded' ? (
                          <button
                            onClick={() => loadMutation.mutate(m.id)}
                            disabled={loadMutation.isPending}
                            title="Загрузить в VRAM (выгружает другие модели)"
                            className="px-2.5 py-1.5 rounded-lg bg-green-600/30 hover:bg-green-600/50 text-green-300 text-xs font-medium transition-colors"
                          >
                            Загрузить
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* Modal: «Указать путь» */}
      {selectedModelForPath && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface-1 border border-white/10 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="font-bold text-base">Указать путь к папке</h3>
                <p className="text-xs text-white/50">{selectedModelForPath.name}</p>
              </div>
              <button
                onClick={() => setSelectedModelForPath(null)}
                className="text-white/40 hover:text-white"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-white/60">
              Укажите абсолютный путь к папке снапшота модели. Папка должна содержать конфигурацию (`config.json`), веса (`model.safetensors` или `model.bin`) и токенизатор.
            </p>

            <div>
              <label className="block text-xs text-white/60 mb-1.5">Путь к папке</label>
              <input
                value={customPathInput}
                onChange={(e) => {
                  setCustomPathInput(e.target.value)
                  setValidationError(null)
                }}
                placeholder="C:\models\qwen-1.7b"
                className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-brand-500"
              />
            </div>

            {/* Error display with missing files */}
            {validationError && (
              <div className="rounded-xl border border-red-500/30 bg-red-950/40 p-3 text-xs text-red-300 flex items-start gap-2">
                <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                <div className="whitespace-pre-line">{validationError}</div>
              </div>
            )}

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setSelectedModelForPath(null)}
                className="px-4 py-2 rounded-xl border border-white/10 text-sm text-white/60 hover:text-white"
              >
                Отмена
              </button>
              <button
                onClick={() =>
                  setPathMutation.mutate({
                    id: selectedModelForPath.id,
                    path: customPathInput.trim(),
                  })
                }
                disabled={!customPathInput.trim() || setPathMutation.isPending}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-sm font-semibold disabled:opacity-40 transition-colors"
              >
                {setPathMutation.isPending ? 'Проверка...' : 'Привязать'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal: «Изменить папку моделей» */}
      {showDirModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-surface-1 border border-white/10 rounded-2xl p-6 w-full max-w-lg shadow-2xl space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-base">Изменить папку для хранения моделей</h3>
              <button onClick={() => setShowDirModal(false)} className="text-white/40 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <div>
              <label className="block text-xs text-white/60 mb-1.5">Новая директория</label>
              <input
                value={newDirInput}
                onChange={(e) => setNewDirInput(e.target.value)}
                placeholder="D:\AI\Models"
                className="w-full bg-surface-2 border border-white/10 rounded-xl px-4 py-2.5 text-sm font-mono text-white placeholder:text-white/20 focus:outline-none focus:border-brand-500"
              />
            </div>

            <label className="flex items-center gap-2.5 text-sm cursor-pointer select-none text-white/80">
              <input
                type="checkbox"
                checked={moveFilesCheck}
                onChange={(e) => setMoveFilesCheck(e.target.checked)}
                className="rounded border-white/20 bg-surface-2 text-brand-600 focus:ring-0"
              />
              Скопировать уже скачанные модели в новую папку
            </label>

            <div className="flex justify-end gap-3 pt-2">
              <button
                onClick={() => setShowDirModal(false)}
                className="px-4 py-2 rounded-xl border border-white/10 text-sm text-white/60 hover:text-white"
              >
                Отмена
              </button>
              <button
                onClick={() =>
                  migrateDirMutation.mutate({
                    newDir: newDirInput.trim(),
                    moveFiles: moveFilesCheck,
                  })
                }
                disabled={!newDirInput.trim() || migrateDirMutation.isPending}
                className="px-4 py-2 rounded-xl bg-brand-600 hover:bg-brand-500 text-sm font-semibold disabled:opacity-40 transition-colors"
              >
                {migrateDirMutation.isPending ? 'Перенос...' : 'Применить'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
