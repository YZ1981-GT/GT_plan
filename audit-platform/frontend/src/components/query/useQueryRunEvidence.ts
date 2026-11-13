/**
 * 当前运行记录、过期判定、历史与证据列表（AQF §8.1 useQueryRunEvidence）。
 *
 * - 单飞判定（同一宿主同时最多一个检查请求）
 * - 页面可见且距上次判定 ≥ 60 秒时自动判定
 * - 代际号丢弃过时响应
 */
import { ref, readonly, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { customQuery } from '@/services/apiPaths/system'
import { apiProxy } from '@/services/apiProxy'
import { downloadFile, isRequestCancelled } from '@/utils/http'
import { describeQueryError, queryErrorToast } from './queryErrorText'

export interface RunInfo {
  id?: string
  recorded: boolean
  reason?: string
  execution_count?: number
}

export interface FreshnessResult {
  status: 'current' | 'stale' | 'unknown'
  changes?: ReadonlyArray<{ key: string; label: string; reason: string }>
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
  const runsError = ref<string | null>(null)
  const artifacts = ref<unknown[]>([])
  const artifactsError = ref<string | null>(null)
  const drawerVisible = ref(false)

  let _generation = 0
  let _runsGeneration = 0
  let _artifactsGeneration = 0
  let _freshnessRequest: AbortController | null = null
  let _runsRequest: AbortController | null = null
  let _artifactsRequest: AbortController | null = null
  let _listProjectId: string | undefined
  let _hasListContext = false
  let _mutationGeneration = 0
  let _disposed = false
  let _lastCheckedAt = 0
  let _visibilityHandler: (() => void) | null = null

  function invalidateFreshness() {
    ++_generation
    _freshnessRequest?.abort()
    _freshnessRequest = null
    checking.value = false
  }

  function invalidateRuns() {
    const generation = ++_runsGeneration
    _runsRequest?.abort()
    _runsRequest = null
    return generation
  }

  function invalidateArtifacts() {
    const generation = ++_artifactsGeneration
    _artifactsRequest?.abort()
    _artifactsRequest = null
    return generation
  }

  function setListContext(projectId?: string) {
    if (!_hasListContext) {
      _hasListContext = true
      _listProjectId = projectId
      return
    }
    if (_listProjectId === projectId) return
    _listProjectId = projectId
    ++_mutationGeneration
    invalidateRuns()
    invalidateArtifacts()
    runs.value = []
    artifacts.value = []
    runsError.value = null
    artifactsError.value = null
  }

  /** 从 execute 响应中设置当前运行信息与版本向量 */
  function setFromExecuteResult(result: Record<string, unknown>) {
    if (_disposed) return
    invalidateFreshness()
    invalidateRuns()
    invalidateArtifacts()
    runInfo.value = (result.run as RunInfo) ?? null
    version.value = (result.version as VersionInfo) ?? null
    freshness.value = null
    checkError.value = null
    _lastCheckedAt = 0
  }

  /** 手动或自动检查时效 */
  async function checkFreshness() {
    const id = runInfo.value?.id
    if (_disposed || !id || _freshnessRequest) return
    const gen = ++_generation
    const controller = new AbortController()
    _freshnessRequest = controller
    checking.value = true
    checkError.value = null
    try {
      const res = await apiProxy.get(customQuery.runFreshness(id), { _silent: true, _dedupe: false, signal: controller.signal })
      if (_disposed || gen !== _generation || controller !== _freshnessRequest) return
      freshness.value = res as FreshnessResult
      _lastCheckedAt = Date.now()
    } catch (e: unknown) {
      if (_disposed || gen !== _generation || controller !== _freshnessRequest || isRequestCancelled(e)) return
      checkError.value = describeQueryError(e).message
    } finally {
      if (gen === _generation && controller === _freshnessRequest) {
        _freshnessRequest = null
        checking.value = false
      }
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
    _disposed = true
    ++_mutationGeneration
    invalidateFreshness()
    invalidateRuns()
    invalidateArtifacts()
    if (_visibilityHandler) document.removeEventListener('visibilitychange', _visibilityHandler)
  })

  /** 加载运行历史列表 */
  async function loadRuns(projectId?: string) {
    if (_disposed) return
    setListContext(projectId)
    const gen = invalidateRuns()
    const controller = new AbortController()
    _runsRequest = controller
    runsError.value = null
    const params: Record<string, string> = { entry, limit: '20' }
    if (projectId) params.project_id = projectId
    try {
      const res = await apiProxy.get(customQuery.runs, { params, _silent: true, _dedupe: false, signal: controller.signal })
      if (_disposed || gen !== _runsGeneration) return
      if (!Array.isArray((res as { runs?: unknown[] })?.runs)) {
        runsError.value = '运行历史返回格式异常，请稍后重试'
        ElMessage.warning(runsError.value)
        return
      }
      runs.value = res.runs
    } catch (e: unknown) {
      if (_disposed || gen !== _runsGeneration || isRequestCancelled(e)) return
      runsError.value = queryErrorToast('加载查询历史', describeQueryError(e))
      ElMessage.warning(runsError.value)
    } finally {
      if (controller === _runsRequest) _runsRequest = null
    }
  }

  /** 加载证据列表 */
  async function loadArtifacts(projectId?: string) {
    if (_disposed) return
    setListContext(projectId)
    const gen = invalidateArtifacts()
    const controller = new AbortController()
    _artifactsRequest = controller
    artifactsError.value = null
    const params: Record<string, string> = { entry, limit: '20' }
    if (projectId) params.project_id = projectId
    try {
      const res = await apiProxy.get(customQuery.artifacts, { params, _silent: true, _dedupe: false, signal: controller.signal })
      if (_disposed || gen !== _artifactsGeneration) return
      if (!Array.isArray((res as { artifacts?: unknown[] })?.artifacts)) {
        artifactsError.value = '证据列表返回格式异常，请稍后重试'
        ElMessage.warning(artifactsError.value)
        return
      }
      artifacts.value = res.artifacts
    } catch (e: unknown) {
      if (_disposed || gen !== _artifactsGeneration || isRequestCancelled(e)) return
      artifactsError.value = queryErrorToast('加载证据列表', describeQueryError(e))
      ElMessage.warning(artifactsError.value)
    } finally {
      if (controller === _artifactsRequest) _artifactsRequest = null
    }
  }

  /** 隐藏单条运行记录 */
  async function hideRun(id: string) {
    if (_disposed) return
    const projectId = _listProjectId
    const mutation = ++_mutationGeneration
    const runsGeneration = invalidateRuns()
    try {
      await apiProxy.delete(`${customQuery.runs}/${id}`, { _silent: true } as Record<string, unknown>)
      if (!_disposed && mutation === _mutationGeneration) await loadRuns(projectId)
    } catch (e: unknown) {
      if (_disposed || mutation !== _mutationGeneration || runsGeneration !== _runsGeneration || isRequestCancelled(e)) return
      runsError.value = queryErrorToast('移除查询历史', describeQueryError(e))
      ElMessage.warning(runsError.value)
    }
  }

  /** 清空本入口的运行历史 */
  async function clearRuns() {
    if (_disposed) return
    const mutation = ++_mutationGeneration
    const runsGeneration = invalidateRuns()
    try {
      await apiProxy.post(customQuery.runsClear, {}, { params: { entry }, _silent: true } as Record<string, unknown>)
      if (_disposed || mutation !== _mutationGeneration) return
      invalidateRuns()
      runs.value = []
      runsError.value = null
    } catch (e: unknown) {
      if (_disposed || mutation !== _mutationGeneration || runsGeneration !== _runsGeneration || isRequestCancelled(e)) return
      runsError.value = queryErrorToast('清空查询历史', describeQueryError(e))
      ElMessage.warning(runsError.value)
    }
  }

  /** 下载证据文件 */
  async function downloadArtifact(id: string) {
    await downloadFile(customQuery.artifactDownload(id))
  }

  /** 获取清单 JSON */
  async function fetchManifest(id: string): Promise<unknown> {
    if (_disposed) return Promise.reject(new Error('disposed'))
    return apiProxy.get(customQuery.artifactManifest(id), { _silent: true })
  }

  /** 获取完整运行定义；抽屉只在该请求成功后才允许回放。 */
  async function fetchRunDetail(id: string): Promise<unknown> {
    if (_disposed) return Promise.reject(new Error('disposed'))
    return apiProxy.get(customQuery.runDetail(id), { _silent: true })
  }

  return {
    runInfo: readonly(runInfo),
    version: readonly(version),
    freshness: readonly(freshness),
    checking: readonly(checking),
    checkError: readonly(checkError),
    runs: readonly(runs),
    runsError: readonly(runsError),
    artifacts: readonly(artifacts),
    artifactsError: readonly(artifactsError),
    drawerVisible,
    setFromExecuteResult,
    checkFreshness,
    loadRuns,
    loadArtifacts,
    hideRun,
    clearRuns,
    downloadArtifact,
    fetchManifest,
    fetchRunDetail,
  }
}
