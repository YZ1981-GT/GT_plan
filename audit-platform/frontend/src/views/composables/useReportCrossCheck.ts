import { ref, computed, watch, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import http from '@/utils/http'

// ─── Types ──────────────────────────────────────────────────────────────────

/** 表间审核严重度（ADR-CCN-05）：缺省 warning = 只提示，不计入失败。 */
export type CrossCheckSeverity = 'blocking' | 'warning' | 'info'

/** 五态检查状态（与后端 CheckStatus 对齐）。 */
export type CrossCheckCheckStatus = 'passed' | 'failed' | 'not_executed' | 'not_applicable' | 'error'

export interface CrossCheckItem {
  description: string
  leftValue: number | null
  rightValue: number | null
  diff: number | null
  passed: boolean
  /** 五态检查状态（后端权威；fallback 按 passed bool 推导）。 */
  status: CrossCheckCheckStatus
  /** 未通过或缺数原因。 */
  reason: string
  severity: CrossCheckSeverity
  source?: 'backend' | 'fallback'
}

/** 界面状态：通过 / 提示（未通过但 warning 级）/ 未通过。 */
export type CrossCheckStatus = 'passed' | 'hint' | 'failed'

/** 未通过项按严重度分成「提示」与「未通过」；通过的项为 passed。 */
export function crossCheckStatusOf(item: Pick<CrossCheckItem, 'passed' | 'severity'>): CrossCheckStatus {
  if (item.passed) return 'passed'
  return item.severity === 'blocking' ? 'failed' : 'hint'
}

/** 勾稽结果来源。 */
export type CrossCheckSource = 'backend' | 'fallback' | 'none'

/** 后端 logic_check 执行端点响应（信封已由 http 拦截器解包为内层 data）。 */
export interface BackendCrossCheckPayload {
  issue_list?: Array<{
    formula_id: string
    addr_id?: string | null
    description: string
    left_value?: string | null
    right_value?: string | null
    severity?: string | null
    reason?: string | null
  }>
  results?: Array<{
    formula_id: string
    description: string
    expression?: string
    passed: boolean
    severity?: string | null
    status?: string | null
    reason?: string | null
  }>
  last_computed_at?: string | null
  /** run 端点扩展字段 */
  run_id?: string | null
  status?: string | null
  executed_count?: number | null
  no_result?: boolean
}

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportCrossCheckOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number | null>
  activeTab: Ref<string>
  currentApplicableStandard: ComputedRef<string>
}

export interface UseReportCrossCheckReturn {
  crossCheckData: Ref<Record<string, any>>
  crossCheckLoading: Ref<boolean>
  crossCheckResults: ComputedRef<CrossCheckItem[]>
  crossCheckSource: Ref<CrossCheckSource>
  crossCheckError: Ref<string>
  loadCrossCheckData: () => Promise<void>
}

// ─── Helpers ────────────────────────────────────────────────────────────────

function parseNumber(value: unknown): number | null {
  if (value == null) return null
  const n = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(n) ? n : null
}

function parseSeverity(value: unknown): CrossCheckSeverity {
  if (value === 'blocking' || value === 'info') return value
  return 'warning'
}

function parseCheckStatus(value: unknown, passed: boolean): CrossCheckCheckStatus {
  const valid: CrossCheckCheckStatus[] = ['passed', 'failed', 'not_executed', 'not_applicable', 'error']
  if (typeof value === 'string' && valid.includes(value as CrossCheckCheckStatus)) return value as CrossCheckCheckStatus
  return passed ? 'passed' : 'failed'
}

// ─── 后端 logic_check 端点消费 ──────────────────────────────────────────────

/**
 * 把后端 logic_check 执行端点返回的逐条勾稽结果（results）+ Issue_List 映射为
 * 前端 `CrossCheckItem[]`。保留五态 status、reason、severity，diff 保真零。
 */
export function mapBackendCrossCheck(payload: BackendCrossCheckPayload): CrossCheckItem[] {
  const results = Array.isArray(payload?.results) ? payload.results : []
  if (results.length === 0) return []
  const issueByFormula = new Map<string, { left: number | null; right: number | null; reason: string; severity: string | null }>()
  for (const issue of payload?.issue_list ?? []) {
    if (!issue?.formula_id) continue
    issueByFormula.set(issue.formula_id, {
      left: parseNumber(issue.left_value),
      right: parseNumber(issue.right_value),
      reason: issue.reason || issue.description || '',
      severity: issue.severity ?? null,
    })
  }
  return results.map((r) => {
    const iss = issueByFormula.get(r.formula_id)
    const left = iss?.left ?? null
    const right = iss?.right ?? null
    // diff 保真零：left-right 可能为 0，不能 `|| null` 丢掉
    const diff = left !== null && right !== null ? Math.round((left - right) * 100) / 100 : null
    const severity = parseSeverity(r.severity ?? iss?.severity)
    const passed = !!r.passed
    const status = parseCheckStatus(r.status, passed)
    const reason = r.reason || iss?.reason || ''
    return { description: r.description, leftValue: left, rightValue: right, diff, passed, status, reason, severity, source: 'backend' as const }
  })
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useReportCrossCheck(options: UseReportCrossCheckOptions): UseReportCrossCheckReturn {
  const { projectId, year, activeTab, currentApplicableStandard } = options

  const crossCheckData = ref<Record<string, any>>({})
  const crossCheckLoading = ref(false)
  const crossCheckError = ref('')
  const crossCheckSource = ref<CrossCheckSource>('none')
  const results = ref<CrossCheckItem[]>([])

  // ── 上下文围栏：ABA 防串 + scope dispose ──
  let generation = 0
  let alive = true

  async function loadCrossCheckData() {
    const pid = projectId.value
    const auditYear = year.value
    const standard = currentApplicableStandard.value
    const token = ++generation

    results.value = []
    crossCheckError.value = ''
    crossCheckSource.value = 'none'

    if (!pid || auditYear == null) {
      crossCheckLoading.value = false
      return
    }

    const current = () =>
      alive && token === generation &&
      pid === projectId.value && auditYear === year.value &&
      standard === currentApplicableStandard.value

    crossCheckLoading.value = true
    try {
      // 后端唯一结果（不再前端本地计算 bsMap/isMap + computeCrossCheckResults）
      const response = await http.get(
        `/api/projects/${pid}/formula/report-cross-check`,
        { params: { year: auditYear } },
      )
      if (!current()) return
      const raw = response?.data
      // 兼容信封双层
      const payload: BackendCrossCheckPayload = (raw?.results || raw?.issue_list) ? raw : (raw?.data ?? raw)
      results.value = mapBackendCrossCheck(payload)
      crossCheckSource.value = results.value.length > 0 ? 'backend' : 'none'
      if (results.value.length === 0 && payload?.no_result) {
        crossCheckError.value = '本年度暂无报表数据，无法执行勾稽'
      }
    } catch (error) {
      if (!current()) return
      crossCheckError.value = error instanceof Error ? error.message : '校对执行失败，请重试'
      results.value = []
    } finally {
      if (current()) crossCheckLoading.value = false
    }
  }

  // 上下文变化立即清空旧结果（flush:sync，不等 nextTick）
  watch([projectId, year, currentApplicableStandard], () => {
    ++generation
    results.value = []
    crossCheckData.value = {}
    crossCheckError.value = ''
    crossCheckSource.value = 'none'
    crossCheckLoading.value = false
    if (activeTab.value === 'cross_check') void loadCrossCheckData()
  }, { flush: 'sync' })

  // 切换到跨表核对 Tab 时自动加载
  watch(activeTab, (tab) => {
    if (tab === 'cross_check') void loadCrossCheckData()
  }, { immediate: true })

  // scope 销毁后不再接收迟到响应
  onScopeDispose(() => {
    alive = false
    ++generation
  })

  return {
    crossCheckData,
    crossCheckLoading,
    crossCheckResults: computed(() => results.value),
    crossCheckSource,
    crossCheckError,
    loadCrossCheckData,
  }
}
