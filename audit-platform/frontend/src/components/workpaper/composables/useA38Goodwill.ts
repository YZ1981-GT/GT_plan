/**
 * useA38Goodwill — A3-8 商誉减值测试公式引擎 + 状态管理
 *
 * 公式（CAS 8 资产减值 / CAPM-WACC / DCF）：
 *  - total = A + B1 + B2
 *  - diff  = total - recoverable
 *  - impairment = max(diff, 0)
 *  - WACC: Ke = Rf + β(Rm-Rf);  WACC = E/(D+E)·Ke + D/(D+E)·Kd·(1-tax)
 *  - DCF: pv(n) = cf(n)/(1+r)^n;  终值 = base·(1+g)/(r-g)
 *  - 可收回金额 = max(公允价值净额合计, DCF现值合计)
 *  - 减值损失分摊：第一分配全冲商誉，剩余按其他资产账面比例第二分配
 *
 * 计算字段均为前端派生，不持久化；仅原始录入字段经 field-overrides 保存。
 */
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'

export interface A38ImpairmentRow {
  id: string
  name: string
  carrying_a: number | null
  goodwill_b1: number | null
  minority_b2: number | null
  recoverable: number | null
  reason: string
  remark: string
}

export interface A38AllocationRow {
  id: string
  asset_type: string
  carrying: number | null
  minority: number | null
  recoverable: number | null
}

export interface A38RecoverableData {
  fair_value_rows: { id: string; name: string; fair_value: number | null; disposal_cost: number | null }[]
  dcf: {
    cash_flows: (number | null)[]
    base_cash_flow: number | null
    perpetual_growth: number | null
    discount_rate: number | null
  }
  wacc: {
    tax_rate: number | null
    debt_d: number | null
    equity_e: number | null
    cost_debt_kd: number | null
    rf: number | null
    beta: number | null
    rm: number | null
  }
}

export interface A38Responses {
  impairment_rows: A38ImpairmentRow[]
  allocation_rows: A38AllocationRow[]
  recoverable: A38RecoverableData
  header: Record<string, any>
}

const n = (v: number | null | undefined): number => (v == null || isNaN(v as number) ? 0 : Number(v))

// ─── 纯函数公式（导出供 PBT 测试） ───────────────────────────────────────────

/** 合计 = A + B1 + B2 */
export function calcTotal(row: Pick<A38ImpairmentRow, 'carrying_a' | 'goodwill_b1' | 'minority_b2'>): number {
  return n(row.carrying_a) + n(row.goodwill_b1) + n(row.minority_b2)
}

/** 差额 = 合计 - 可收回金额 */
export function calcDiff(row: A38ImpairmentRow): number {
  return calcTotal(row) - n(row.recoverable)
}

/** 减值准备 = max(差额, 0)（非负） */
export function calcImpairment(row: A38ImpairmentRow): number {
  return Math.max(calcDiff(row), 0)
}

/** WACC（税后）；D+E=0 或参数缺失 → null */
export function calcWacc(w: A38RecoverableData['wacc']): number | null {
  const D = n(w.debt_d)
  const E = n(w.equity_e)
  if (D + E === 0) return null
  const ke = n(w.rf) + n(w.beta) * (n(w.rm) - n(w.rf)) // CAPM
  const kd = n(w.cost_debt_kd)
  const tax = n(w.tax_rate)
  return (E / (D + E)) * ke + (D / (D + E)) * kd * (1 - tax)
}

/** CAPM 权益成本 Ke = Rf + β(Rm-Rf) */
export function calcKe(w: A38RecoverableData['wacc']): number {
  return n(w.rf) + n(w.beta) * (n(w.rm) - n(w.rf))
}

/** 折现系数 1/(1+r)^year；r 缺失或 <=-1 → null */
export function discountFactor(rate: number | null, year: number): number | null {
  if (rate == null || rate <= -1) return null
  return 1 / Math.pow(1 + rate, year)
}

/** DCF 预测期现值合计（前 cash_flows.length 年） */
export function calcDcfPv(dcf: A38RecoverableData['dcf']): number | null {
  if (dcf.discount_rate == null) return null
  let sum = 0
  dcf.cash_flows.forEach((cf, i) => {
    const f = discountFactor(dcf.discount_rate, i + 1)
    if (f != null) sum += n(cf) * f
  })
  return sum
}

/** 终值现值 = base·(1+g)/(r-g) 折现到末年；r<=g 或缺失 → null */
export function calcTerminalPv(dcf: A38RecoverableData['dcf']): number | null {
  const r = dcf.discount_rate
  const g = dcf.perpetual_growth
  if (r == null || g == null || r <= g) return null
  const lastYear = dcf.cash_flows.length || 5
  const terminal = (n(dcf.base_cash_flow) * (1 + g)) / (r - g)
  const f = discountFactor(r, lastYear)
  return f == null ? null : terminal * f
}

/** 公允价值净额合计 = Σ(公允价值 - 处置费用) */
export function calcFairValueNet(rows: A38RecoverableData['fair_value_rows']): number {
  return rows.reduce((s, r) => s + (n(r.fair_value) - n(r.disposal_cost)), 0)
}

/** 可收回金额 = max(公允价值净额, DCF现值合计+终值现值)；返回 {value, path} */
export function calcRecoverableAmount(rec: A38RecoverableData): { value: number | null; path: string } {
  const fv = calcFairValueNet(rec.fair_value_rows)
  const dcfPv = calcDcfPv(rec.dcf)
  const terminal = calcTerminalPv(rec.dcf)
  const dcfTotal = dcfPv == null ? null : dcfPv + n(terminal)
  if (dcfTotal == null) return { value: fv, path: 'fair_value' }
  if (fv >= dcfTotal) return { value: fv, path: 'fair_value' }
  return { value: dcfTotal, path: 'dcf' }
}

/**
 * 减值损失二次分摊：第一分配全冲商誉，剩余按其他资产账面比例第二分配。
 * 返回每行 {alloc_first, alloc_second, adjusted}。守恒：Σ(alloc_first+alloc_second)=loss。
 */
export function allocateImpairment(
  rows: A38AllocationRow[],
  loss: number,
): { id: string; alloc_first: number; alloc_second: number }[] {
  const goodwill = rows.find((r) => r.asset_type === '商誉' || r.asset_type === 'goodwill')
  const others = rows.filter((r) => r !== goodwill)
  const result = rows.map((r) => ({ id: r.id, alloc_first: 0, alloc_second: 0 }))
  if (loss <= 0) return result

  // 第一分配：全额冲减商誉（不超过商誉账面）
  let remaining = loss
  if (goodwill) {
    const gwCarry = n(goodwill.carrying)
    const first = Math.min(remaining, gwCarry)
    const g = result.find((x) => x.id === goodwill.id)!
    g.alloc_first = first
    remaining -= first
  }

  // 第二分配：剩余按其他资产账面价值比例分摊
  if (remaining > 0) {
    const totalCarry = others.reduce((s, r) => s + n(r.carrying), 0)
    if (totalCarry > 0) {
      others.forEach((r) => {
        const share = (n(r.carrying) / totalCarry) * remaining
        const res = result.find((x) => x.id === r.id)!
        res.alloc_second = share
      })
    }
  }
  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useA38Goodwill(wpId: () => string, projectId: () => string, year: () => number, readonly: () => boolean) {
  const impairmentRows = ref<A38ImpairmentRow[]>([])
  const allocationRows = ref<A38AllocationRow[]>([])
  const recoverable = ref<A38RecoverableData>({
    fair_value_rows: [],
    dcf: { cash_flows: [null, null, null, null, null], base_cash_flow: null, perpetual_growth: null, discount_rate: null },
    wacc: { tax_rate: null, debt_d: null, equity_e: null, cost_debt_kd: null, rf: null, beta: null, rm: null },
  })
  const guidance = ref<any>(null)
  const loading = ref(false)
  const saving = ref(false)
  let isInitialLoad = true

  // ── 派生计算（合计行） ──
  const impairmentTotals = computed(() => ({
    carrying_a: impairmentRows.value.reduce((s, r) => s + n(r.carrying_a), 0),
    goodwill_b1: impairmentRows.value.reduce((s, r) => s + n(r.goodwill_b1), 0),
    minority_b2: impairmentRows.value.reduce((s, r) => s + n(r.minority_b2), 0),
    total: impairmentRows.value.reduce((s, r) => s + calcTotal(r), 0),
    recoverable: impairmentRows.value.reduce((s, r) => s + n(r.recoverable), 0),
    impairment: impairmentRows.value.reduce((s, r) => s + calcImpairment(r), 0),
  }))

  const waccResult = computed(() => calcWacc(recoverable.value.wacc))
  const keResult = computed(() => calcKe(recoverable.value.wacc))
  const recoverableResult = computed(() => calcRecoverableAmount(recoverable.value))

  async function load() {
    loading.value = true
    isInitialLoad = true
    try {
      const res = await api.get<any>(`/api/workpapers/${wpId()}/render-config?force_component_type=a3-8-goodwill-impairment`)
      const html = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
      const imp = html?.impairmentData ?? {}
      const rec = html?.recoverableData ?? {}
      const resp = html?.responses ?? {}
      // responses 优先，否则用骨架
      impairmentRows.value = resp.impairment_rows?.length ? resp.impairment_rows : (imp.impairment_rows ?? [])
      allocationRows.value = resp.allocation_rows?.length ? resp.allocation_rows : (imp.allocation_rows ?? [])
      recoverable.value = Object.keys(resp.recoverable ?? {}).length ? resp.recoverable : (rec ?? recoverable.value)
      guidance.value = imp.guidance ?? null
    } catch (e) {
      console.error('[useA38Goodwill] load failed:', e)
    } finally {
      loading.value = false
      setTimeout(() => { isInitialLoad = false }, 0)
    }
  }

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  async function persist(retry = 0): Promise<void> {
    if (readonly() || !projectId() || !wpId()) return
    const scope = `a3_8_goodwill:${wpId()}`
    const calls = [
      { item_key: 'impairment_rows', value: impairmentRows.value },
      { item_key: 'allocation_rows', value: allocationRows.value },
      { item_key: 'recoverable', value: recoverable.value },
    ].map((p) =>
      api.post('/api/workpapers/field-overrides', {
        project_id: projectId(), year: year(), scope, item_key: p.item_key, field: 'value', value: p.value,
      }),
    )
    saving.value = true
    try {
      await Promise.all(calls)
    } catch (e) {
      if (retry < 2) { await persist(retry + 1); return }
      const { ElMessage } = await import('element-plus')
      ElMessage.warning('自动保存失败，请稍后重试')
    } finally {
      saving.value = false
    }
  }

  function scheduleSave() {
    if (readonly()) return
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => { saveTimer = null; persist() }, 2000)
  }

  function flushSave() {
    if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; persist() }
  }

  watch([impairmentRows, allocationRows, recoverable], () => {
    if (isInitialLoad) return
    scheduleSave()
  }, { deep: true })

  // ── 行操作 ──
  function addImpairmentRow() {
    impairmentRows.value.push({
      id: `ag-${Date.now()}`, name: '', carrying_a: null, goodwill_b1: null,
      minority_b2: null, recoverable: null, reason: '', remark: '',
    })
  }
  function removeImpairmentRow(id: string) {
    impairmentRows.value = impairmentRows.value.filter((r) => r.id !== id)
  }
  function addAllocationRow() {
    allocationRows.value.push({ id: `al-${Date.now()}`, asset_type: '', carrying: null, minority: null, recoverable: null })
  }
  function removeAllocationRow(id: string) {
    allocationRows.value = allocationRows.value.filter((r) => r.id !== id)
  }
  function addFairValueRow() {
    recoverable.value.fair_value_rows.push({ id: `fv-${Date.now()}`, name: '', fair_value: null, disposal_cost: null })
  }
  function removeFairValueRow(id: string) {
    recoverable.value.fair_value_rows = recoverable.value.fair_value_rows.filter((r) => r.id !== id)
  }

  return {
    impairmentRows, allocationRows, recoverable, guidance, loading, saving,
    impairmentTotals, waccResult, keResult, recoverableResult,
    load, flushSave,
    addImpairmentRow, removeImpairmentRow, addAllocationRow, removeAllocationRow,
    addFairValueRow, removeFairValueRow,
    // 暴露纯函数供模板
    calcTotal, calcDiff, calcImpairment,
  }
}
