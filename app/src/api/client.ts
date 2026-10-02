import axios from 'axios'
import { invoke } from '@tauri-apps/api/core'

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
  sample_rate?: number
  peak?: number
  verdict?: string
  rms_profile?: number[]
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

export type TransportType = 'axios' | 'rust'
export let lastUsedTransport: TransportType = 'axios'

export function getLastTransport(): TransportType {
  return lastUsedTransport
}

export function formatWithTransport(msg: string, transport: TransportType = lastUsedTransport): string {
  if (msg.endsWith('[axios]') || msg.endsWith('[rust]')) {
    return msg
  }
  return `${msg} [${transport}]`
}

function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const res = reader.result as string
      const base64 = res.includes(',') ? res.split(',')[1] : res
      resolve(base64)
    }
    reader.onerror = (e) => reject(e)
    reader.readAsDataURL(file)
  })
}

export async function viaBackend<T = any>(
  method: string,
  path: string,
  body?: any
): Promise<T> {
  let fullPath = path
  const methodUpper = method.toUpperCase()
  if (methodUpper === 'GET' && body && typeof body === 'object') {
    const query = new URLSearchParams()
    for (const [k, v] of Object.entries(body)) {
      if (v !== undefined && v !== null) {
        query.append(k, String(v))
      }
    }
    const qStr = query.toString()
    if (qStr) {
      fullPath = fullPath.includes('?') ? `${fullPath}&${qStr}` : `${fullPath}?${qStr}`
    }
  }

  const axiosTimeout = fullPath.startsWith('/api/health') ? 3000 : 120000

  // 1. Попытка через axios
  try {
    let res: any
    if (methodUpper === 'GET') {
      res = await api.get<T>(fullPath, { timeout: axiosTimeout })
    } else if (methodUpper === 'POST') {
      res = await api.post<T>(fullPath, body, { timeout: axiosTimeout })
    } else if (methodUpper === 'PATCH') {
      res = await api.patch<T>(fullPath, body, { timeout: axiosTimeout })
    } else if (methodUpper === 'PUT') {
      res = await api.put<T>(fullPath, body, { timeout: axiosTimeout })
    } else if (methodUpper === 'DELETE') {
      res = await api.delete<T>(fullPath, { data: body, timeout: axiosTimeout })
    } else {
      throw new Error(`Неподдерживаемый метод ${method}`)
    }
    lastUsedTransport = 'axios'
    return res.data
  } catch (axiosErr: any) {
    const msg = axiosErr?.message || String(axiosErr)
    const isNetworkError =
      msg.includes('Network Error') ||
      axiosErr?.code === 'ERR_NETWORK' ||
      axiosErr?.code === 'ECONNABORTED' ||
      !axiosErr.response

    if (isNetworkError) {
      // 2. Фолбэк через Rust backend_request
      try {
        const data = await invoke<T>('backend_request', {
          method: methodUpper,
          path: fullPath,
          body: body !== undefined && methodUpper !== 'GET' ? body : null,
        })
        lastUsedTransport = 'rust'
        return data
      } catch (rustErr: any) {
        lastUsedTransport = 'rust'
        const rustMsg = typeof rustErr === 'string' ? rustErr : (rustErr?.message || String(rustErr))
        const tagged = formatWithTransport(rustMsg, 'rust')
        const err: any = new Error(tagged)
        err.transport = 'rust'
        err.response = { data: { detail: tagged } }
        throw err
      }
    }

    // Axios дошёл до сервера, но сервер вернул HTTP ошибку (4xx/5xx)
    lastUsedTransport = 'axios'
    const detail = axiosErr?.response?.data?.detail || axiosErr?.message || 'Ошибка сервера'
    const tagged = formatWithTransport(detail, 'axios')
    axiosErr.transport = 'axios'
    if (axiosErr.response) {
      if (!axiosErr.response.data) axiosErr.response.data = {}
      axiosErr.response.data.detail = tagged
    }
    axiosErr.message = tagged
    throw axiosErr
  }
}

// API functions
export const apiProfiles = {
  list: () => viaBackend<Profile[]>('GET', '/api/profiles'),
  get: (id: string) => viaBackend<Profile>('GET', `/api/profiles/${id}`),
  create: (data: { name: string; description?: string; language: string; default_engine?: string }) =>
    viaBackend<Profile>('POST', '/api/profiles', data),
  update: (id: string, data: Partial<Profile>) =>
    viaBackend<Profile>('PATCH', `/api/profiles/${id}`, data),
  delete: (id: string) => viaBackend<void>('DELETE', `/api/profiles/${id}`),
  addSample: async (profileId: string, file: File, referenceText: string): Promise<Sample> => {
    const form = new FormData()
    form.append('audio', file)
    form.append('reference_text', referenceText)
    try {
      const res = await api.post<Sample>(`/api/profiles/${profileId}/samples`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      lastUsedTransport = 'axios'
      return res.data
    } catch (axiosErr: any) {
      const msg = axiosErr?.message || String(axiosErr)
      const isNetworkError =
        msg.includes('Network Error') ||
        axiosErr?.code === 'ERR_NETWORK' ||
        axiosErr?.code === 'ECONNABORTED' ||
        !axiosErr.response

      if (isNetworkError) {
        const base64Data = await fileToBase64(file)
        const payload = {
          _multipart: true,
          reference_text: referenceText,
          file_name: file.name,
          file_base64: base64Data,
        }
        try {
          const data = await invoke<Sample>('backend_request', {
            method: 'POST',
            path: `/api/profiles/${profileId}/samples`,
            body: payload,
          })
          lastUsedTransport = 'rust'
          return data
        } catch (rustErr: any) {
          lastUsedTransport = 'rust'
          const rustMsg = typeof rustErr === 'string' ? rustErr : (rustErr?.message || String(rustErr))
          const tagged = formatWithTransport(rustMsg, 'rust')
          const err: any = new Error(tagged)
          err.transport = 'rust'
          err.response = { data: { detail: tagged } }
          throw err
        }
      }

      lastUsedTransport = 'axios'
      const detail = axiosErr?.response?.data?.detail || axiosErr?.message || 'Ошибка загрузки сэмпла'
      const tagged = formatWithTransport(detail, 'axios')
      axiosErr.transport = 'axios'
      if (axiosErr.response) {
        if (!axiosErr.response.data) axiosErr.response.data = {}
        axiosErr.response.data.detail = tagged
      }
      axiosErr.message = tagged
      throw axiosErr
    }
  },
  deleteSample: (profileId: string, sampleId: string) =>
    viaBackend<void>('DELETE', `/api/profiles/${profileId}/samples/${sampleId}`),
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
  list: () => viaBackend<ModelItem[]>('GET', '/api/models'),
  getDir: () => viaBackend<{ models_dir: string; is_env_overridden: boolean }>('GET', '/api/models/dir'),
  migrateDir: (newDir: string, moveFiles: boolean = true) =>
    viaBackend('POST', '/api/models/dir/migrate', { new_dir: newDir, move_files: moveFiles }),
  download: (id: string) => viaBackend('POST', `/api/models/${id}/download`),
  setPath: (id: string, path: string) => viaBackend('POST', `/api/models/${id}/set-path`, { path }),
  load: (id: string) => viaBackend('POST', `/api/models/${id}/load`, { device: 'cuda' }),
  unload: (id: string) => viaBackend('POST', `/api/models/${id}/unload`),
  openFolder: (id: string) => viaBackend('POST', `/api/models/${id}/open-folder`),
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
  }) => viaBackend<Generation>('POST', '/api/synthesize', data),
  history: (profileId?: string, limit?: number) =>
    viaBackend<any[]>('GET', '/api/history', { profile_id: profileId, limit }),
}

export const apiHealth = {
  check: () => viaBackend<HealthInfo>('GET', '/api/health'),
  restartBackend: () => invoke<void>('restart_sidecar'),
}

export interface BookChapter {
  index: number
  title: string
  char_count: number
  preview: string
}

export interface ParseBookResponse {
  id: string
  title: string
  author: string
  chapter_count: number
  chapters: BookChapter[]
}

export const apiBook = {
  parse: (text: string, title?: string, author?: string) =>
    viaBackend<ParseBookResponse>('POST', '/api/book/parse', { text, title, author }),
  markup: (text: string, intensity: 'subtle' | 'moderate' | 'dramatic' = 'moderate') =>
    viaBackend<{ original: string; marked_up: string }>('POST', '/api/book/markup', { text, intensity }),
  synthesizeBook: (data: {
    profile_id: string
    chapters: Array<{ title: string; text: string }>
    engine?: string
    language?: string
    book_title?: string
    author?: string
  }) => viaBackend<{
    status: string
    output_path: string
    total_duration_sec: number
    chapters_count: number
  }>('POST', '/api/book/synthesize-book', data),
}
