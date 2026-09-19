import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { getReport } from '@/services/auditPlatformApi'
import http from '@/utils/http'
import { useAddressRegistry } from '@/stores/addressRegistry'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface CrossCheckItem {
  description: string
  leftValue: number | null
  rightValue: number | null
  diff: number | null
  passed: boolean
}

/** 勾稽结果来源：`backend`=消费后端 logic_check 端点；`fallback`=纯函数降级（Req 23.2/23.3）。 */
export type CrossCheckSource = 'backend' | 'fallback'

/** 后端 logic_check 执行端点响应（信封已由 http 拦截器解包为内层 data）。 */
interface BackendCrossCheckPayload {
  issue_list?: Array<{
    formula_id: string
    addr_id?: string | null
    description: string
    left_value?: string | null
    right_value?: string | null
  }>
  results?: Array<{
    formula_id: string
    description: string
    expression?: string
    passed: boolean
  }>
  last_computed_at?: string | null
}

// ─── Interfaces ─────────────────────────────────────────────────────────────

export interface UseReportCrossCheckOptions {
  projectId: ComputedRef<string>
  year: ComputedRef<number>
  activeTab: Ref<string>
  currentApplicableStandard: ComputedRef<string>
}

export interface UseReportCrossCheckReturn {
  crossCheckData: Ref<Record<string, any>>
  crossCheckLoading: Ref<boolean>
  crossCheckResults: ComputedRef<CrossCheckItem[]>
  /** 当前勾稽结果来源（backend 主路径 / fallback 纯函数降级），供 UI 标注与测试断言。 */
  crossCheckSource: Ref<CrossCheckSource>
  loadCrossCheckData: () => Promise<void>
}

// ─── 后端 logic_check 端点消费（Req 23.1）──────────────────────────────────────

/**
 * 把后端 logic_check 执行端点返回的逐条勾稽结果（results）+ Issue_List 映射为
 * 前端 `CrossCheckItem[]`（Req 23.1）。
 *
 * - 逐条 `passed` + `description` 由后端 `results` 驱动（收编后的 7 条 logic_check 公式）。
 * - `leftValue` / `rightValue` 尽力从 `issue_list`（不通过项）按 `formula_id` 关联回填，
 *   `diff` 据此计算；通过项无 Issue → 左右值为 null（与纯函数对通过项展示一致）。
 *
 * 收编不改变勾稽语义（Req 23.5）：后端 7 条 logic_check 的 passed 判定逐条移植自
 * 原 `computeCrossCheckResults`，故逐条判定与纯函数一致。
 */
function mapBackendCrossCheck(payload: BackendCrossCheckPayload): CrossCheckItem[] {
  const results = Array.isArray(payload?.results) ? payload.results : []
  const issueByFormula = new Map<string, { left: number | null; right: number | null }>()
  for (const issue of payload?.issue_list ?? []) {
    if (!issue || !issue.formula_id) continue
    const left = issue.left_value != null ? Number(issue.left_value) : null
    const right = issue.right_value != null ? Number(issue.right_value) : null
    issueByFormula.set(issue.formula_id, {
      left: left != null && !Number.isNaN(left) ? left : null,
      right: right != null && !Number.isNaN(right) ? right : null,
    })
  }
  return results.map((r) => {
    const iss = issueByFormula.get(r.formula_id)
    const left = iss?.left ?? null
    const right = iss?.right ?? null
    const diff = left != null && right != null ? Math.round((left - right) * 100) / 100 : null
    return {
      description: r.description,
      leftValue: left,
      rightValue: right,
      diff: diff || null,
      passed: !!r.passed,
    }
  })
}

// ─── Composable ─────────────────────────────────────────────────────────────

/**
 * 经 ACNR REPORT 域 / store `reportAddresses` 提供的 canonical `row_code → row_name`
 * 注册表，把语义键（中文名或候选码）精确解析为权威 `row_code`，再对值表做精确取值。
 *
 * 相比"扫描值表 key 做子串模糊匹配"，此路径以真源注册表为准，抗报表标签漂移（Req 19.2）。
 * registry 缺失（reportCodeMap 为 undefined）时返回 null，由调用方回退现有模糊匹配（Req 19.7）。
 */
function resolveViaReportRegistry(
  map: Record<string, number>,
  reportCodeMap: Record<string, string> | undefined,
  keys: string[],
): number | null {
  if (!reportCodeMap) return null
  const entries = Object.entries(reportCodeMap)
  // pass 1: key 本身就是 canonical row_code → 直接精确取值
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(reportCodeMap, key)) {
      const v = map[key]
      if (v != null && v !== 0) return v
    }
  }
  // pass 2: key 与注册表 row_name 精确相等 → 用其 canonical row_code 精确取值
  for (const key of keys) {
    for (const [code, name] of entries) {
      if (name && name === key) {
        const v = map[code]
        if (v != null && v !== 0) return v
      }
    }
  }
  // pass 3: 注册表 row_name 与 key 互为子串（仍以权威名为锚，比扫描值表 key 更精确）
  for (const key of keys) {
    for (const [code, name] of entries) {
      if (name && (name.includes(key) || key.includes(name))) {
        const v = map[code]
        if (v != null && v !== 0) return v
      }
    }
  }
  return null
}

/**
 * Standalone cross-check computation — pure function, no Vue reactivity needed.
 * Extracts balance sheet / income statement values and runs 7 equation checks.
 *
 * 取值优先级：① 值表精确匹配（row_code/row_name）→ ② canonical row_code 精确解析
 * （经 ACNR REPORT 域注册表 `reportCodeMap`，Req 19.2）→ ③ 中文名模糊匹配（miss 回退，Req 19.7）。
 * 当 `crossCheckData.reportCodeMap` 缺省时，②不生效，行为与迁移前逐字节一致（向后兼容）。
 */
export function computeCrossCheckResults(crossCheckData: Record<string, any>): CrossCheckItem[] {
  const { bsMap = {}, isMap = {}, reportCodeMap } = crossCheckData
  // 精确匹配 → canonical row_code 精确解析 → 模糊匹配（包含关键词）
  const get = (map: Record<string, number>, ...keys: string[]) => {
    // ① 先精确匹配值表 key（row_code / row_name）
    for (const k of keys) { if (map[k] != null && map[k] !== 0) return map[k] }
    // ② canonical row_code 精确解析（ACNR REPORT 域真源，Req 19.2）
    const canonical = resolveViaReportRegistry(map, reportCodeMap, keys)
    if (canonical != null) return canonical
    // ③ miss 回退：中文名模糊匹配（原有行为，逻辑不变，Req 19.7）
    for (const k of keys) {
      for (const [mk, mv] of Object.entries(map)) {
        if (mv !== 0 && mk.includes(k)) return mv
      }
    }
    return 0
  }
  const totalAssets = get(bsMap, 'assets_total', '资产总计', '资产合计')
  const totalLiabilities = get(bsMap, 'liabilities_total', '负债合计', '负债总计')
  const totalEquity = get(bsMap, 'equity_total', '所有者权益合计', '股东权益合计', '权益合计')
  const netProfit = get(isMap, 'IS-019', '净利润')
  const revenue = get(isMap, 'IS-001', '营业收入')
  const cost = get(isMap, 'IS-002', '营业成本')
  const profitBeforeTax = get(isMap, 'IS-017', '利润总额')
  const incomeTax = get(isMap, 'IS-018', '所得税费用', '所得税')
  const cash = get(bsMap, 'BS-001', '货币资金')

  function check(desc: string, left: number, right: number, tolerance = 0): CrossCheckItem {
    const diff = Math.round((left - right) * 100) / 100
    const passed = tolerance > 0 ? Math.abs(diff) <= tolerance : Math.abs(diff) < 0.01
    return { description: desc, leftValue: left || null, rightValue: right || null, diff: diff || null, passed }
  }

  return [
    check('资产合计 = 负债合计 + 所有者权益合计', totalAssets, totalLiabilities + totalEquity, 1),
    check('营业收入 − 营业成本 = 毛利', revenue - cost, revenue - cost),
    check('利润总额 − 所得税 = 净利润', profitBeforeTax - incomeTax, netProfit, 1),
    check('资产 − 负债 = 权益', totalAssets - totalLiabilities, totalEquity, 1),
    check('所有者权益变动表期末 = 资产负债表权益', totalEquity, totalEquity),
    check('有效税率 ≈ 25%', incomeTax, profitBeforeTax > 0 ? profitBeforeTax * 0.25 : 0, profitBeforeTax * 0.05),
    check('货币资金 ≥ 0（负值异常）', cash, 0, Math.abs(cash)),
  ]
}

export function useReportCrossCheck(options: UseReportCrossCheckOptions): UseReportCrossCheckReturn {
  const { projectId, year, activeTab, currentApplicableStandard } = options

  // State
  const crossCheckData = ref<Record<string, any>>({})
  const crossCheckLoading = ref(false)
  // 后端 logic_check 端点返回的逐条勾稽结果（主路径，Req 23.1）；null=未取到/降级。
  const backendResults = ref<CrossCheckItem[] | null>(null)
  // 当前结果来源：默认 fallback（纯函数），成功消费后端后置为 backend。
  const crossCheckSource = ref<CrossCheckSource>('fallback')

  // ACNR-backed 地址注册表 store（Req 16 facade）——REPORT 域 canonical row_code→row_name 真源。
  // 在 setup 上下文获取实例；无活跃 Pinia（如纯函数单测环境）时降级为 null → 回退模糊匹配。
  let addrStore: ReturnType<typeof useAddressRegistry> | null = null
  try {
    addrStore = useAddressRegistry()
  } catch {
    addrStore = null
  }

  /**
   * 从 store `reportAddresses` 构建 canonical `row_code → row_name` 映射（Req 19.2）。
   * 无 report 域条目时返回 undefined，调用方据此回退现有模糊匹配（Req 19.5/19.7）。
   */
  function buildReportCodeMap(): Record<string, string> | undefined {
    if (!addrStore) return undefined
    try {
      const entries = (addrStore.reportAddresses as Array<{ row_code?: string; label?: string }>) || []
      const map: Record<string, string> = {}
      for (const e of entries) {
        if (e && e.row_code && e.label && map[e.row_code] == null) {
          map[e.row_code] = e.label
        }
      }
      return Object.keys(map).length > 0 ? map : undefined
    } catch {
      return undefined
    }
  }

  /**
   * 消费后端 logic_check 执行端点获取逐条勾稽判定（Req 23.1）。
   *
   * 端点：`GET /api/projects/{projectId}/formula/report-cross-check?year=`（http 拦截器
   * 自带 Authorization + 信封解包，`resp.data` 已为内层 `{issue_list, results, ...}`）。
   * 成功且 `results` 非空 → 返回映射后的 `CrossCheckItem[]`；否则抛错交由调用方降级。
   */
  async function fetchBackendCrossCheck(): Promise<CrossCheckItem[]> {
    const resp = await http.get(
      `/api/projects/${projectId.value}/formula/report-cross-check`,
      { params: { year: year.value } },
    )
    // 信封已解包：resp.data === {issue_list, results, last_computed_at}；
    // 兼容未解包场景（data?.data??data，防个别环境双层信封）。
    const raw = resp?.data
    const payload: BackendCrossCheckPayload = (raw?.results || raw?.issue_list) ? raw : (raw?.data ?? raw)
    const mapped = mapBackendCrossCheck(payload)
    if (mapped.length === 0) {
      throw new Error('backend cross-check returned empty results')
    }
    return mapped
  }

  async function loadCrossCheckData() {
    if (crossCheckLoading.value) return
    crossCheckLoading.value = true
    try {
      const std = currentApplicableStandard.value
      const [bs, is] = await Promise.all([
        getReport(projectId.value, year.value, 'balance_sheet', false, std).catch(() => []),
        getReport(projectId.value, year.value, 'income_statement', false, std).catch(() => []),
      ])
      // 按 row_code 和 row_name 建索引（合计行优先覆盖同名非合计行）
      const buildMap = (rows: any[]) => {
        const map: Record<string, number> = {}
        // 先填非合计行
        for (const row of (rows || [])) {
          const amt = parseFloat(row.current_period_amount) || 0
          if (!row.is_total_row) {
            if (row.row_code && !map[row.row_code]) map[row.row_code] = amt
            if (row.row_name && !map[row.row_name]) map[row.row_name] = amt
          }
        }
        // 再填合计行（覆盖同名）
        for (const row of (rows || [])) {
          const amt = parseFloat(row.current_period_amount) || 0
          if (row.is_total_row) {
            if (row.row_code) map[row.row_code] = amt
            if (row.row_name) map[row.row_name] = amt
          }
        }
        return map
      }
      // 经 ACNR REPORT 域 / store reportAddresses 取 canonical row_code→row_name（Req 19.2）。
      // store 尚未加载报表地址时尽力刷新一次（best-effort，失败不阻断勾稽计算）。
      let reportCodeMap = buildReportCodeMap()
      if (!reportCodeMap && addrStore) {
        try {
          await addrStore.refresh(projectId.value, year.value)
          reportCodeMap = buildReportCodeMap()
        } catch { /* registry 不可用 → 回退模糊匹配（Req 19.5/19.7） */ }
      }
      crossCheckData.value = {
        bsMap: buildMap(bs as any[]),
        isMap: buildMap(is as any[]),
        reportCodeMap,
      }
      // 主路径（Req 23.1）：调后端 logic_check 端点获取逐条勾稽判定驱动展示。
      // 降级（Req 23.2/23.3）：后端不可用（超时/5xx/网络错）→ try/catch 回退纯函数，
      // 不阻断报表页面渲染（fail-open）——crossCheckData 已就绪，crossCheckResults 会
      // 落到 computeCrossCheckResults 分支。
      try {
        backendResults.value = await fetchBackendCrossCheck()
        crossCheckSource.value = 'backend'
      } catch {
        backendResults.value = null
        crossCheckSource.value = 'fallback'
      }
    } catch { /* ignore */ }
    finally { crossCheckLoading.value = false }
  }

  const crossCheckResults = computed<CrossCheckItem[]>(() => {
    // 主路径：后端 logic_check 端点结果优先（Req 23.1）。
    if (backendResults.value) return backendResults.value
    // 降级路径：纯函数勾稽（Req 23.2/23.3），语义与在线一致（Req 23.5）。
    return computeCrossCheckResults(crossCheckData.value)
  })

  // 切换到跨表核对 Tab 时自动加载数据
  watch(activeTab, (tab) => {
    if (tab === 'cross_check' && !crossCheckData.value.bsMap) {
      loadCrossCheckData()
    }
  })

  return {
    crossCheckData,
    crossCheckLoading,
    crossCheckResults,
    crossCheckSource,
    loadCrossCheckData,
  }
}
