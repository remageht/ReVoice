import axios from 'axios'

const BASE_URL = 'http://127.0.0.1:7851'

export const api = axios.create({
  baseURL: BASE_URL,
  timeout: 120000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Types
export interface Profile {
  id: string
  name: string
  description?: string
  language: string
  default_engine?: string
  effects_chain?: string
  sample_count: number
  generation_count: number
  created_at: string
  updated_at: string
  samples: Sample[]
}

export interface Sample {
  id: string
  audio_path: string
  reference_text: string
  duration_sec?: number
  rms_median?: number
  is_valid: boolean
  rejection_reason?: string
}

export interface EngineInfo {
  engine_id: string
  display_name: string
  hf_repo_id: string
  license: string
  size_mb: number
  languages: string[]
  supports_cloning: boolean
  requires_gpu: boolean
  model_variants: string[]
  is_loaded: boolean
}

export interface HealthInfo {
  status: string
  version: string
  uptime_sec: number
  platform: string
  python_version: string
  gpu: {
    available: boolean
    name?: string
    vram_total_mb?: number
    vram_free_mb?: number
  }
  loaded_engines: string[]
  data_dir: string
}

export interface Generation {
  generation_id: string
  status: string
  audio_path?: string
  duration_sec?: number
  engine: string
}

// API functions
export const apiProfiles = {
  list: () => api.get<Profile[]>('/api/profiles').then(r => r.data),
  get: (id: string) => api.get<Profile>(`/api/profiles/${id}`).then(r => r.data),
  create: (data: { name: string; description?: string; language: string; default_engine?: string }) =>
    api.post<Profile>('/api/profiles', data).then(r => r.data),
  update: (id: string, data: Partial<Profile>) =>
    api.patch<Profile>(`/api/profiles/${id}`, data).then(r => r.data),
  delete: (id: string) => api.delete(`/api/profiles/${id}`),
  addSample: (profileId: string, file: File, referenceText: string) => {
    const form = new FormData()
    form.append('audio', file)
    form.append('reference_text', referenceText)
    return api.post<Sample>(`/api/profiles/${profileId}/samples`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then(r => r.data)
  },
  deleteSample: (profileId: string, sampleId: string) =>
    api.delete(`/api/profiles/${profileId}/samples/${sampleId}`),
}

export interface ModelItem {
  id: string
  name: string
  type: 'TTS' | 'STT' | 'LLM'
  engine_id: string
  variant: string
  size_mb: number
  license: string
  description: string
  disk_status: 'downloaded' | 'partial' | 'not_downloaded'
  is_loaded: boolean
  is_custom_path: boolean
  local_path: string
  download?: {
    status?: string
    progress_percent?: number
    error?: string
  }
  validation_warning?: string
}

export const apiModels = {
  list: () => api.get<ModelItem[]>('/api/models').then(r => r.data),
  getDir: () => api.get<{ models_dir: string; is_env_overridden: boolean }>('/api/models/dir').then(r => r.data),
  migrateDir: (newDir: string, moveFiles: boolean = true) =>
    api.post('/api/models/dir/migrate', { new_dir: newDir, move_files: moveFiles }).then(r => r.data),
  download: (id: string) => api.post(`/api/models/${id}/download`).then(r => r.data),
  setPath: (id: string, path: string) => api.post(`/api/models/${id}/set-path`, { path }).then(r => r.data),
  load: (id: string) => api.post(`/api/models/${id}/load`, { device: 'cuda' }).then(r => r.data),
  unload: (id: string) => api.post(`/api/models/${id}/unload`).then(r => r.data),
  openFolder: (id: string) => api.post(`/api/models/${id}/open-folder`).then(r => r.data),
}

export const apiSynth = {
  synthesize: (data: {
    profile_id: string
    text: string
    engine?: string
    language?: string
    seed?: number
    max_chunk_chars?: number
    normalize?: boolean
  }) => api.post<Generation>('/api/synthesize', data).then(r => r.data),
  history: (profileId?: string, limit?: number) =>
    api.get<any[]>('/api/history', { params: { profile_id: profileId, limit } }).then(r => r.data),
}

export const apiHealth = {
  check: () => api.get<HealthInfo>('/api/health').then(r => r.data),
}
