import { useQuery } from '@tanstack/react-query'
import { apiHealth } from '../../api/client'

export function SettingsTab() {
  const { data: health } = useQuery({
    queryKey: ['health'],
    queryFn: apiHealth.check,
    refetchInterval: 5000,
  })

  return (
    <div className="p-6 max-w-xl">
      <h2 className="text-2xl font-bold mb-6">Настройки</h2>

      <div className="space-y-4">
        <div className="rounded-xl border border-white/10 bg-surface-1 p-5">
          <h3 className="font-semibold mb-3 text-white/70 text-sm uppercase tracking-wider">Статус сервера</h3>
          {health ? (
            <div className="space-y-2 text-sm">
              <Row label="Версия" value={health.version} />
              <Row label="Платформа" value={health.platform} />
              <Row label="Python" value={health.python_version} />
              <Row label="Данные" value={health.data_dir} mono />
              <Row
                label="GPU"
                value={health.gpu.available
                  ? `${health.gpu.name} (${health.gpu.vram_free_mb}/${health.gpu.vram_total_mb} МБ свободно)`
                  : 'Недоступен (CPU-режим)'}
              />
              <Row label="Аптайм" value={`${health.uptime_sec.toFixed(0)}с`} />
            </div>
          ) : (
            <p className="text-white/30 text-sm">Нет связи с сервером</p>
          )}
        </div>

        <div className="rounded-xl border border-white/10 bg-surface-1 p-5">
          <h3 className="font-semibold mb-2 text-white/70 text-sm uppercase tracking-wider">Хоткей</h3>
          <p className="text-sm text-white/60"><kbd className="bg-surface-3 px-2 py-0.5 rounded text-xs font-mono">Ctrl+Shift+V</kbd> — синтез текста из буфера обмена</p>
        </div>
      </div>
    </div>
  )
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex justify-between gap-4">
      <span className="text-white/40">{label}</span>
      <span className={`text-right truncate ${mono ? 'font-mono text-xs' : ''}`}>{value}</span>
    </div>
  )
}
