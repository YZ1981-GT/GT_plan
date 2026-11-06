/**
 * 当前运行记录、过期判定、历史与证据列表（AQF §8.1 useQueryRunEvidence）。
 *
 * - 单飞判定（同一宿主同时最多一个检查请求）
 * - 页面可见且距上次判定 ≥ 60 秒时自动判定
 * - 代际号丢弃过时响应
 */
import { ref, readonly, onMounted, onBeforeUnmount } from 'vue'
import { customQuery } from '@/services/apiPaths/system'
import { apiProxy } from '@/services/apiProxy'
import { downloadFile } from '@/utils/http'

export interface RunInfo {
  id?: string
  recorded: boolean
  reason?: string
  execution_count?: number
}

export interface FreshnessResult {
  status: 'current' | 'stale' | 'unknown'
  changes?: Array<{ key: string; label: string; reason: string }>
  weak?: boolean
  checked_at?: string
}

export interface VersionComponent {
  key: string
  label: string
  basis: string
  rows?: number
  digest?: string
  latest_update?: string
  weak?: boolean
  error?: string
}

export interface VersionInfo {
  components?: VersionComponent[]
  vector_hash?: string
  weak?: boolean
}

/** entry = 'business' | 'builder' */
export function useQueryRunEvidence(entry: 'business' | 'builder') {
  const runInfo = ref<RunInfo | null>(null)
  const version = ref<VersionInfo | null>(null)
  const freshness = ref<FreshnessResult | null>(null)
  const checking = ref(false)
  const checkError = ref<string | null>(null)
  const runs = ref<unknown[]>([])
  const artifacts = ref<unknown[]>([])
  const drawerVisible = ref(false)

  let _generation = 0
  let _lastCheckedAt = 0
  let _visibilityHandler: (() => void) | null = null

  /** 从 execute 响应中设置当前运行信息与版本向量 */
  function setFromExecuteResult(result: Record<string, unknown>) {
    runInfo.value = (result.run as RunInfo) ?? null
    version.value = (result.version as VersionInfo) ?? null
    freshness.value = null
    checkError.value = null
    _lastCheckedAt = 0
  }

  /** 手动或自动检查时效 */
  async function checkFreshness() {
    const id = runInfo.value?.id
    if (!id || checking.value) return
    const gen = ++_generation
    checking.value = true
    checkError.value = null
    try {
      const res = await apiProxy.get(customQuery.runFreshness(id), {}, { _silent: true })
      if (gen !== _generation) return // 丢弃过时响应
      freshness.value = res as FreshnessResult
      _lastCheckedAt = Date.now()
    } catch (e: unknown) {
      if (gen !== _generation) return
      checkError.value = (e as { message?: string })?.message ?? '检查失败'
    } finally {
      if (gen === _generation) checking.value = false
    }
  }

  /** 页面重新可见且距上次判定 ≥ 60 秒时自动触发 */
  function _setupAutoCheck() {
    _visibilityHandler = () => {
      if (document.visibilityState === 'visible') {
        const elapsed = Date.now() - _lastCheckedAt
        if (elapsed >= 60_000 && runInfo.value?.id) {
          checkFreshness()
        }
      }
    }
    document.addEventListener('visibilitychange', _visibilityHandler)
  }

  onMounted(() => { _setupAutoCheck() })
  onBeforeUnmount(() => {
    if (_visibilityHandler) document.removeEventListener('visibilitychange', _visibilityHandler)
  })

  /** 加载运行历史列表 */
  async function loadRuns(projectId?: string) {
    const params: Record<string, string> = { entry, limit: '20' }
    if (projectId) params.project_id = projectId
    try {
      const res = await apiProxy.get(customQuery.runs, params, { _silent: true })
      runs.value = (res as { runs: unknown[] })?.runs ?? []
    } catch { runs.value = [] }
  }

  /** 加载证据列表 */
  async function loadArtifacts(projectId?: string) {
    const params: Record<string, string> = { entry, limit: '20' }
    if (projectId) params.project_id = projectId
    try {
      const res = await apiProxy.get(customQuery.artifacts, params, { _silent: true })
      artifacts.value = (res as { artifacts: unknown[] })?.artifacts ?? []
    } catch { artifacts.value = [] }
  }

  /** 隐藏单条运行记录 */
  async function hideRun(id: string) {
    try {
      await apiProxy.delete(`${customQuery.runs}/${id}`, { _silent: true })
      await loadRuns()
    } catch { /* ignore */ }
  }

  /** 清空全部运行历史 */
  async function clearRuns() {
    try {
      await apiProxy.post(customQuery.runsClear, {}, { _silent: true })
      runs.value = []
    } catch { /* ignore */ }
  }

  /** 下载证据文件 */
  async function downloadArtifact(id: string) {
    await downloadFile(customQuery.artifactDownload(id))
  }

  /** 获取清单 JSON */
  async function fetchManifest(id: string): Promise<unknown> {
    return apiProxy.get(customQuery.artifactManifest(id), {}, { _silent: true })
  }

  return {
    runInfo: readonly(runInfo),
    version: readonly(version),
    freshness: readonly(freshness),
    checking: readonly(checking),
    checkError: readonly(checkError),
    runs: readonly(runs),
    artifacts: readonly(artifacts),
    drawerVisible,
    setFromExecuteResult,
    checkFreshness,
    loadRuns,
    loadArtifacts,
    hideRun,
    clearRuns,
    downloadArtifact,
    fetchManifest,
  }
}
