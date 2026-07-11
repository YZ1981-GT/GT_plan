import { ref, computed, watch, type ComputedRef, type Ref } from 'vue'
import { getReport } from '@/services/auditPlatformApi'
import { useAddressRegistry } from '@/stores/addressRegistry'

// ─── Types ──────────────────────────────────────────────────────────────────

export interface CrossCheckItem {
  description: string
  leftValue: number | null
  rightValue: number | null
  diff: number | null
  passed: boolean
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
  loadCrossCheckData: () => Promise<void>
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
    } catch { /* ignore */ }
    finally { crossCheckLoading.value = false }
  }

  const crossCheckResults = computed<CrossCheckItem[]>(() => {
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
    loadCrossCheckData,
  }
}
