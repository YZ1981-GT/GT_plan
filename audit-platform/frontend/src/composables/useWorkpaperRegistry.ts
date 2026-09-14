/**
 * useWorkpaperRegistry — 底稿类型注册表 composable
 *
 * 从后端加载 workpaper_render_registry，提供 lookup / listByType 查询。
 * 进程内缓存，多组件共享同一份数据。
 */
import { ref, readonly } from 'vue'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RegistryEntry {
  name: string
  render_type: string
  module?: string
  data_source?: string
  role?: string
  categories: string[]
  upstream: string[]
  downstream: string[]
}

interface RegistryData {
  render_types: string[]
  entries: Record<string, RegistryEntry>
}

// ─── Module-level cache ──────────────────────────────────────────────────────

const _cache = ref<RegistryData | null>(null)
const _loading = ref(false)

async function _ensureLoaded(): Promise<RegistryData> {
  if (_cache.value) return _cache.value
  if (_loading.value) {
    // 等待并发加载完成
    await new Promise<void>((resolve) => {
      const check = setInterval(() => {
        if (_cache.value) {
          clearInterval(check)
          resolve()
        }
      }, 50)
    })
    return _cache.value!
  }
  _loading.value = true
  try {
    const data = await api.get<RegistryData>('/api/workpapers/render-registry')
    _cache.value = data
    return data
  } finally {
    _loading.value = false
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWorkpaperRegistry() {
  const loaded = ref(false)

  /** 确保注册表已加载 */
  async function load() {
    await _ensureLoaded()
    loaded.value = true
  }

  /** 按 wp_code 查找条目 */
  function lookup(wpCode: string): RegistryEntry | null {
    return _cache.value?.entries[wpCode] ?? null
  }

  /** 获取所有 entries */
  function getAll(): Record<string, RegistryEntry> {
    return _cache.value?.entries ?? {}
  }

  /** 按 render_type 过滤 */
  function listByType(renderType: string): Record<string, RegistryEntry> {
    const entries = _cache.value?.entries ?? {}
    const result: Record<string, RegistryEntry> = {}
    for (const [code, entry] of Object.entries(entries)) {
      if (entry.render_type === renderType) {
        result[code] = entry
      }
    }
    return result
  }

  /** 按 module 过滤 */
  function listByModule(module: string): Record<string, RegistryEntry> {
    const entries = _cache.value?.entries ?? {}
    const result: Record<string, RegistryEntry> = {}
    for (const [code, entry] of Object.entries(entries)) {
      if (entry.module === module) {
        result[code] = entry
      }
    }
    return result
  }

  /** 获取合法 render_type 列表 */
  function getRenderTypes(): string[] {
    return _cache.value?.render_types ?? []
  }

  /** 清除缓存（测试/热更新用） */
  function invalidate() {
    _cache.value = null
    loaded.value = false
  }

  return {
    loaded: readonly(loaded),
    load,
    lookup,
    getAll,
    listByType,
    listByModule,
    getRenderTypes,
    invalidate,
  }
}
