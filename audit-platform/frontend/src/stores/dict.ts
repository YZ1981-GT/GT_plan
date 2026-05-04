/**
 * useDictStore — 枚举字典 Store [R4.1]
 *
 * 后端 GET /api/system/dicts 返回所有枚举字典，
 * 前端启动时加载一次，sessionStorage 缓存，避免重复请求。
 *
 * 用法：
 * ```ts
 * const dictStore = useDictStore()
 * await dictStore.load()                          // App.vue onMounted 调用
 * dictStore.label('wp_status', 'draft')           // → '草稿'
 * dictStore.type('wp_status', 'draft')            // → 'info'
 * dictStore.options('wp_status')                  // → [{ value, label, color }, ...]
 * ```
 *
 * 与 statusMaps.ts + GtStatusTag 互补：
 * - statusMaps.ts 是前端硬编码的静态映射，零延迟
 * - dictStore 是服务端下发的字典，支持动态扩展
 * - 两者可共存，dictStore 优先级更高（服务端可覆盖前端默认值）
 */
import { defineStore } from 'pinia'
import { ref } from 'vue'
import http from '@/utils/http'

export interface DictEntry {
  value: string
  label: string
  /** Element Plus el-tag type: success | warning | danger | info | '' */
  color: string
}

export type DictData = Record<string, DictEntry[]>

const CACHE_KEY = 'gt_dict_cache'
const CACHE_VERSION_KEY = 'gt_dict_cache_v'
/** 缓存版本号，修改字典结构时递增 */
const CACHE_VERSION = '1'

export const useDictStore = defineStore('dict', () => {
  // ─── 状态 ───
  const data = ref<DictData>({})
  const loaded = ref(false)
  const loading = ref(false)

  // ─── 从 sessionStorage 恢复缓存 ───
  function _restoreFromCache(): boolean {
    try {
      const ver = sessionStorage.getItem(CACHE_VERSION_KEY)
      if (ver !== CACHE_VERSION) return false
      const raw = sessionStorage.getItem(CACHE_KEY)
      if (!raw) return false
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed === 'object') {
        data.value = parsed
        loaded.value = true
        return true
      }
    } catch { /* ignore corrupt cache */ }
    return false
  }

  // ─── 写入 sessionStorage 缓存 ───
  function _saveToCache() {
    try {
      sessionStorage.setItem(CACHE_KEY, JSON.stringify(data.value))
      sessionStorage.setItem(CACHE_VERSION_KEY, CACHE_VERSION)
    } catch { /* sessionStorage full or disabled */ }
  }

  // ─── 加载字典（启动时调用） ───
  async function load(force = false) {
    // 已加载且非强制刷新 → 跳过
    if (loaded.value && !force) return

    // 尝试从缓存恢复
    if (!force && _restoreFromCache()) return

    // 从后端加载
    if (loading.value) return
    loading.value = true
    try {
      const resp = await http.get('/api/system/dicts')
      const raw = resp.data?.data ?? resp.data ?? {}
      if (raw && typeof raw === 'object') {
        data.value = raw as DictData
        loaded.value = true
        _saveToCache()
      }
    } catch (e) {
      console.warn('[dictStore] 加载字典失败，使用空字典', e)
    } finally {
      loading.value = false
    }
  }

  // ─── 获取标签文本 ───
  function label(dictKey: string, value: string | undefined | null): string {
    if (!value) return '—'
    const entries = data.value[dictKey]
    if (!entries) return value
    const entry = entries.find((e) => e.value === value)
    return entry?.label ?? value
  }

  // ─── 获取 el-tag type ───
  function type(dictKey: string, value: string | undefined | null): string {
    if (!value) return 'info'
    const entries = data.value[dictKey]
    if (!entries) return 'info'
    const entry = entries.find((e) => e.value === value)
    return entry?.color ?? 'info'
  }

  // ─── 获取某个字典的全部选项 ───
  function options(dictKey: string): DictEntry[] {
    return data.value[dictKey] ?? []
  }

  // ─── 清除缓存（调试/登出时使用） ───
  function clearCache() {
    sessionStorage.removeItem(CACHE_KEY)
    sessionStorage.removeItem(CACHE_VERSION_KEY)
    data.value = {}
    loaded.value = false
  }

  return {
    // 状态
    data,
    loaded,
    loading,
    // 方法
    load,
    label,
    type,
    options,
    clearCache,
  }
})
