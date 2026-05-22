/**
 * 枚举字典 sessionStorage 版本控制 (DT-1)
 *
 * 在应用启动时检查后端字典版本，与本地缓存版本对比：
 * - 版本不一致：清除缓存并重新获取
 * - 版本一致：直接使用缓存数据
 *
 * 使用方式：
 *   在 App.vue 的 onMounted 或 router.beforeEach 中调用：
 *   import { checkDictVersion } from '@/utils/dictVersionCheck'
 *   await checkDictVersion()
 */
import http from '@/utils/http'

const DICT_VERSION_KEY = 'dict_version'
const DICT_DATA_KEY = 'dict_data'

interface DictVersionResponse {
  version: string
}

interface DictDataResponse {
  version?: string
  data: Record<string, Array<{ label: string; value: string | number }>>
}

/**
 * 获取后端字典版本号
 */
async function fetchDictVersion(): Promise<string | null> {
  try {
    const res = await http.get<DictVersionResponse>('/api/system/dicts/version')
    return res.data?.version ?? null
  } catch {
    // 如果版本接口不存在，降级为始终刷新
    return null
  }
}

/**
 * 获取完整字典数据
 */
async function fetchDictData(): Promise<DictDataResponse | null> {
  try {
    const res = await http.get<DictDataResponse>('/api/system/dicts')
    return res.data ?? null
  } catch {
    return null
  }
}

/**
 * 获取缓存的字典数据
 */
export function getCachedDicts(): Record<string, Array<{ label: string; value: string | number }>> | null {
  const raw = sessionStorage.getItem(DICT_DATA_KEY)
  if (!raw) return null
  try {
    return JSON.parse(raw)
  } catch {
    return null
  }
}

/**
 * 清除字典缓存
 */
export function clearDictCache(): void {
  sessionStorage.removeItem(DICT_VERSION_KEY)
  sessionStorage.removeItem(DICT_DATA_KEY)
}

/**
 * 检查字典版本并按需刷新缓存
 * 返回最新的字典数据
 */
export async function checkDictVersion(): Promise<Record<string, Array<{ label: string; value: string | number }>> | null> {
  const remoteVersion = await fetchDictVersion()

  // 如果无法获取远程版本，降级为清除缓存重新获取
  if (remoteVersion === null) {
    clearDictCache()
    const freshData = await fetchDictData()
    if (freshData) {
      if (freshData.version) {
        sessionStorage.setItem(DICT_VERSION_KEY, freshData.version)
      }
      sessionStorage.setItem(DICT_DATA_KEY, JSON.stringify(freshData.data))
      return freshData.data
    }
    return null
  }

  const localVersion = sessionStorage.getItem(DICT_VERSION_KEY)

  // 版本一致，使用缓存
  if (localVersion === remoteVersion) {
    const cached = getCachedDicts()
    if (cached) return cached
  }

  // 版本不一致或缓存丢失，重新获取
  clearDictCache()
  const freshData = await fetchDictData()
  if (freshData) {
    sessionStorage.setItem(DICT_VERSION_KEY, remoteVersion)
    sessionStorage.setItem(DICT_DATA_KEY, JSON.stringify(freshData.data))
    return freshData.data
  }

  return null
}
