import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Mic2, Trash2, ChevronRight } from 'lucide-react'
import { toast } from 'sonner'
import { clsx } from 'clsx'

import { apiProfiles, Profile } from '../../api/client'
import { useAppStore } from '../../store/useAppStore'
import { ProfileDetail } from '../ProfileDetail'
import { CreateProfileModal } from '../CreateProfileModal'

export function VoicesTab() {
  const qc = useQueryClient()
  const { activeProfileId, setActiveProfileId } = useAppStore()
  const [showCreate, setShowCreate] = useState(false)

  const { data: profiles = [], isLoading } = useQuery({
    queryKey: ['profiles'],
    queryFn: apiProfiles.list,
  })

  const deleteMutation = useMutation({
    mutationFn: (id: string) => apiProfiles.delete(id),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['profiles'] })
      if (activeProfileId === id) setActiveProfileId(null)
      toast.success('Профиль удалён')
    },
  })

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-full">
        <p className="text-white/40">Загрузка профилей...</p>
      </div>
    )
  }

  return (
    <div className="flex h-full">
      {/* Profile list */}
      <div className="w-64 shrink-0 border-r border-white/5 flex flex-col h-full">
        <div className="p-4 border-b border-white/5 flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white/70 uppercase tracking-wider">Голоса</h2>
          <button
            onClick={() => setShowCreate(true)}
            className="w-7 h-7 rounded-lg bg-brand-600 hover:bg-brand-500 flex items-center justify-center transition-colors"
          >
            <Plus className="w-4 h-4" />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-2 space-y-1">
          {profiles.length === 0 ? (
            <div className="text-center py-8">
              <Mic2 className="w-8 h-8 text-white/20 mx-auto mb-2" />
              <p className="text-white/30 text-sm">Нет голосов</p>
              <button
                onClick={() => setShowCreate(true)}
                className="mt-3 text-brand-400 text-sm hover:text-brand-300"
              >
                Создать первый
              </button>
            </div>
          ) : (
            profiles.map(profile => (
              <button
                key={profile.id}
                onClick={() => setActiveProfileId(profile.id)}
                className={clsx(
                  'w-full text-left px-3 py-2.5 rounded-lg flex items-center gap-3 transition-all group',
                  activeProfileId === profile.id
                    ? 'bg-brand-600/25 text-white'
                    : 'text-white/60 hover:bg-white/5 hover:text-white'
                )}
              >
                <div className="w-8 h-8 rounded-lg bg-brand-600/30 flex items-center justify-center shrink-0">
                  <Mic2 className="w-4 h-4 text-brand-400" />
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-medium truncate">{profile.name}</p>
                  <p className="text-xs text-white/30">{profile.sample_count} сэмпл.</p>
                </div>
                <ChevronRight className={clsx(
                  'w-4 h-4 shrink-0 transition-opacity',
                  activeProfileId === profile.id ? 'opacity-100 text-brand-400' : 'opacity-0'
                )} />
              </button>
            ))
          )}
        </div>
      </div>

      {/* Profile detail */}
      <div className="flex-1 overflow-y-auto">
        {activeProfileId ? (
          <ProfileDetail profileId={activeProfileId} />
        ) : (
          <div className="flex items-center justify-center h-full">
            <div className="text-center">
              <Mic2 className="w-12 h-12 text-white/10 mx-auto mb-3" />
              <p className="text-white/30">Выберите голос или создайте новый</p>
            </div>
          </div>
        )}
      </div>

      {showCreate && (
        <CreateProfileModal onClose={() => setShowCreate(false)} />
      )}
    </div>
  )
}
