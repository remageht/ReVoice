import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Download, CheckCircle, Circle, Cpu, Loader2 } from 'lucide-react'
import { toast } from 'sonner'
import { clsx } from 'clsx'
import { apiModels } from '../../api/client'

export function ModelsTab() {
  const qc = useQueryClient()

  const { data: engines = [], isLoading } = useQuery({
    queryKey: ['models'],
    queryFn: apiModels.list,
    refetchInterval: 10000,
  })

  const loadMutation = useMutation({
    mutationFn: ({ id, variant }: { id: string; variant?: string }) =>
      apiModels.load(id, variant),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['models'] }); toast.success('Модель загружена') },
    onError: (e: any) => toast.error(e.response?.data?.detail || 'Ошибка загрузки'),
  })

  const unloadMutation = useMutation({
    mutationFn: (id: string) => apiModels.unload(id),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['models'] }); toast.success('Модель выгружена') },
  })

  if (isLoading) {
    return <div className="flex items-center justify-center h-full"><Loader2 className="animate-spin text-brand-400" /></div>
  }

  return (
    <div className="p-6">
      <h2 className="text-2xl font-bold mb-6">Движки и модели</h2>
      <div className="grid gap-4">
        {engines.map(engine => (
          <div key={engine.engine_id} className="rounded-xl border border-white/10 bg-surface-1 p-5">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-brand-600/20 flex items-center justify-center">
                  <Cpu className="w-5 h-5 text-brand-400" />
                </div>
                <div>
                  <h3 className="font-semibold">{engine.display_name}</h3>
                  <p className="text-sm text-white/50">{engine.hf_repo_id}</p>
                </div>
              </div>
              <div className="flex items-center gap-2">
                {engine.is_loaded ? (
                  <>
                    <span className="text-xs bg-green-500/20 text-green-400 px-2 py-1 rounded-full">Загружена</span>
                    <button
                      onClick={() => unloadMutation.mutate(engine.engine_id)}
                      className="text-xs text-white/40 hover:text-red-400 transition-colors"
                    >
                      Выгрузить
                    </button>
                  </>
                ) : (
                  <button
                    onClick={() => loadMutation.mutate({ id: engine.engine_id })}
                    disabled={loadMutation.isPending}
                    className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-brand-600 hover:bg-brand-500
                               text-sm font-medium transition-colors disabled:opacity-50"
                  >
                    {loadMutation.isPending ? <Loader2 className="w-3 h-3 animate-spin" /> : <Download className="w-3 h-3" />}
                    Загрузить
                  </button>
                )}
              </div>
            </div>
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="text-xs bg-white/5 text-white/50 px-2 py-1 rounded">{engine.size_mb} МБ</span>
              <span className="text-xs bg-white/5 text-white/50 px-2 py-1 rounded">{engine.license}</span>
              {engine.languages.map(l => (
                <span key={l} className="text-xs bg-brand-600/20 text-brand-300 px-2 py-1 rounded">{l}</span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}
