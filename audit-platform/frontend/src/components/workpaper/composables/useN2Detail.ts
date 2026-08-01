/**
 * useN2Detail — N2-2 明细表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 3.1-3.6
 *
 * 职责（源模板 16 数据列，唯一模型 useN2Detail16）：
 * - 项目 / 税率 / 未审(期初C·应交D·已交E·期末F) / 期初调整G /
 *   账项调整(应交I·已交J) / 重分类(应交K·已交L) / 审定(期初M·应交N·已交O·期末P) / 备注
 * - 公式：F=C+D−E ; M=C+G ; N=D+I+K ; O=E+J+L ; P=M+N−O（派生列不持久化，读时推导）
 * - 13 固定税种 + 可增删；seedFromN21() 无数据时从 N2-1 带入未审期初
 * - item_id: N2-2-detail-rows（只存录入列）
 *
 * 科目：2221 应交税费（贷方/负债类）
 * 注：原自造模型（计提/缴纳/申报表核对，item N2-2-rows）已删除，其字段与源模板无对应。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal } from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────


/** 统计摘要 */
export interface N2DetailSummary {
  /** 税种数 */
  taxTypeCount: number
  /** 计提合计 */
  accrualTotal: number
  /** 缴纳合计 */
  paymentTotal: number
  /** 期末合计 */
  endBalanceTotal: number
  /** 存在差异的行数 */
  diffRowCount: number
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function generateRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}


// ═══════════════════════════════════════════════════════════════════════════
// 16 列源模板对齐模型（N2-2 应交税费明细表）
//
// 源结构：项目 / 税率 /
//   未审(期初C / 应交D / 已交E / 期末F=C+D-E) /
//   期初调整G /
//   账项调整(应交I / 已交J) /
//   重分类(应交K / 已交L) /
//   审定(期初M=C+G / 应交N=D+I+K / 已交O=E+J+L / 期末P=M+N-O) /
//   备注
//
// item_id: N2-2-detail-rows
// 13 固定税种 + 可新增/删；seedFromN21() 无数据时从 N2-1 带入未审期初。
// 旧 useN2Detail 导出保留不动。
// ═══════════════════════════════════════════════════════════════════════════

/** 16 列明细表单行 */
export interface N2Detail16Row {
  id: string
  taxType: string
  taxRate: number
  /** 未审·期初 C */
  unadjBegin: number
  /** 未审·应交 D */
  unadjPayable: number
  /** 未审·已交 E */
  unadjPaid: number
  /** 未审·期末 F = C + D − E（auto） */
  unadjEnd: number
  /** 期初调整 G */
  beginAdjust: number
  /** 账项调整·应交 I */
  ajePayable: number
  /** 账项调整·已交 J */
  ajePaid: number
  /** 重分类·应交 K */
  rjePayable: number
  /** 重分类·已交 L */
  rjePaid: number
  /** 审定·期初 M = C + G（auto） */
  audBegin: number
  /** 审定·应交 N = D + I + K（auto） */
  audPayable: number
  /** 审定·已交 O = E + J + L（auto） */
  audPaid: number
  /** 审定·期末 P = M + N − O（auto） */
  audEnd: number
  /** 备注 */
  remark: string
}

/** 16 列合计行 */
export interface N2Detail16Total {
  unadjBegin: number
  unadjPayable: number
  unadjPaid: number
  unadjEnd: number
  beginAdjust: number
  ajePayable: number
  ajePaid: number
  rjePayable: number
  rjePaid: number
  audBegin: number
  audPayable: number
  audPaid: number
  audEnd: number
}

/** 13 固定税种 */
export const N2_DETAIL_FIXED_TYPES: string[] = [
  '增值税',
  '未交增值税',
  '消费税',
  '城市维护建设税',
  '教育费附加',
  '地方教育附加',
  '房产税',
  '城镇土地使用税',
  '印花税',
  '车船税',
  '企业所得税',
  '个人所得税',
  '其他',
]

/** 16 列可编辑字段 */
export type N2Detail16EditableField =
  | 'taxType'
  | 'taxRate'
  | 'unadjBegin'
  | 'unadjPayable'
  | 'unadjPaid'
  | 'beginAdjust'
  | 'ajePayable'
  | 'ajePaid'
  | 'rjePayable'
  | 'rjePaid'
  | 'remark'

function _map16(r: any): N2Detail16Row {
  const C = parseNum(r.unadjBegin)
  const D = parseNum(r.unadjPayable)
  const E = parseNum(r.unadjPaid)
  const G = parseNum(r.beginAdjust)
  const I = parseNum(r.ajePayable)
  const J = parseNum(r.ajePaid)
  const K = parseNum(r.rjePayable)
  const L = parseNum(r.rjePaid)
  const F = C + D - E
  const M = C + G
  const N = D + I + K
  const O = E + J + L
  const P = M + N - O
  return {
    id: r.id || generateRowId(),
    taxType: r.taxType || '',
    taxRate: parseNum(r.taxRate),
    unadjBegin: C,
    unadjPayable: D,
    unadjPaid: E,
    unadjEnd: F,
    beginAdjust: G,
    ajePayable: I,
    ajePaid: J,
    rjePayable: K,
    rjePaid: L,
    audBegin: M,
    audPayable: N,
    audPaid: O,
    audEnd: P,
    remark: r.remark || '',
  }
}

export interface UseN2Detail16Options {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN2Detail16(options: UseN2Detail16Options) {
  const { allResponses, saveField, getField } = options

  // ─── 行数据（公式列自动计算，无持久化时显示 13 固定税种） ─────────────────
  const rows: ComputedRef<N2Detail16Row[]> = computed(() => {
    const resp = allResponses.value.get('N2-2-detail-rows')
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }
    if (Array.isArray(raw) && raw.length > 0) return raw.map(_map16)
    // 默认 13 固定税种（display）
    return N2_DETAIL_FIXED_TYPES.map(t => _map16({ taxType: t }))
  })

  const total: ComputedRef<N2Detail16Total> = computed(() => {
    const r = rows.value
    return {
      unadjBegin: calcSubtotal(r.map(x => x.unadjBegin)),
      unadjPayable: calcSubtotal(r.map(x => x.unadjPayable)),
      unadjPaid: calcSubtotal(r.map(x => x.unadjPaid)),
      unadjEnd: calcSubtotal(r.map(x => x.unadjEnd)),
      beginAdjust: calcSubtotal(r.map(x => x.beginAdjust)),
      ajePayable: calcSubtotal(r.map(x => x.ajePayable)),
      ajePaid: calcSubtotal(r.map(x => x.ajePaid)),
      rjePayable: calcSubtotal(r.map(x => x.rjePayable)),
      rjePaid: calcSubtotal(r.map(x => x.rjePaid)),
      audBegin: calcSubtotal(r.map(x => x.audBegin)),
      audPayable: calcSubtotal(r.map(x => x.audPayable)),
      audPaid: calcSubtotal(r.map(x => x.audPaid)),
      audEnd: calcSubtotal(r.map(x => x.audEnd)),
    }
  })

  const summary: ComputedRef<N2DetailSummary> = computed(() => {
    const r = rows.value
    return {
      taxTypeCount: new Set(r.map(x => x.taxType).filter(Boolean)).size,
      accrualTotal: calcSubtotal(r.map(x => x.audPayable)),
      paymentTotal: calcSubtotal(r.map(x => x.audPaid)),
      endBalanceTotal: calcSubtotal(r.map(x => x.audEnd)),
      diffRowCount: 0,
    }
  })

  function _currentRaw(): any[] {
    const stored = getField('2', 'detail-rows')
    if (Array.isArray(stored) && stored.length > 0) {
      return stored.map((x: any) => ({ ...x }))
    }
    // 物化当前显示行（13 固定税种），首次编辑即持久化
    return rows.value.map(r => ({
      id: r.id,
      taxType: r.taxType,
      taxRate: r.taxRate,
      unadjBegin: r.unadjBegin,
      unadjPayable: r.unadjPayable,
      unadjPaid: r.unadjPaid,
      beginAdjust: r.beginAdjust,
      ajePayable: r.ajePayable,
      ajePaid: r.ajePaid,
      rjePayable: r.rjePayable,
      rjePaid: r.rjePaid,
      remark: r.remark,
    }))
  }

  async function addRow(taxType: string): Promise<void> {
    const raw = _currentRaw()
    raw.push({
      id: generateRowId(),
      taxType,
      taxRate: 0,
      unadjBegin: 0,
      unadjPayable: 0,
      unadjPaid: 0,
      beginAdjust: 0,
      ajePayable: 0,
      ajePaid: 0,
      rjePayable: 0,
      rjePaid: 0,
      remark: '',
    })
    await saveField('2', 'detail-rows', raw)
  }

  async function removeRow(rowId: string): Promise<void> {
    const raw = _currentRaw()
    await saveField('2', 'detail-rows', raw.filter(r => r.id !== rowId))
  }

  async function updateRow(rowId: string, field: N2Detail16EditableField, value: any): Promise<void> {
    const raw = _currentRaw()
    const idx = raw.findIndex(r => r.id === rowId)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
      await saveField('2', 'detail-rows', raw)
    }
  }

  /**
   * 预置源模板 13 类固定税种空行（幂等：已有持久化数据时直接返回，不覆盖已录内容）。
   *
   * rows 的 computed 在无数据时本就**显示** 13 固定税种，但那只是展示态、未落库；
   * 本函数把展示态物化进 `N2-2-detail-rows`，供用户显式点「预置常见税种」使用。
   */
  async function seedDefaultRows(): Promise<void> {
    const stored = getField('2', 'detail-rows')
    if (Array.isArray(stored) && stored.length > 0) return
    await saveField('2', 'detail-rows', N2_DETAIL_FIXED_TYPES.map(t => ({
      id: generateRowId(),
      taxType: t,
      taxRate: 0,
      unadjBegin: 0,
      unadjPayable: 0,
      unadjPaid: 0,
      beginAdjust: 0,
      ajePayable: 0,
      ajePaid: 0,
      rjePayable: 0,
      rjePaid: 0,
      remark: '',
    })))
  }

  /** 无数据时从 N2-1 审定表带入未审期初（13 固定税种） */
  async function seedFromN21(): Promise<void> {
    const n21 = allResponses.value.get('N2-1-adjudication-rows')
    let n21rows: any[] = []
    if (n21?.conclusion) {
      try { n21rows = JSON.parse(n21.conclusion) } catch { n21rows = [] }
    }
    const beginByType = new Map<string, number>()
    for (const x of Array.isArray(n21rows) ? n21rows : []) {
      beginByType.set(x.taxType, parseNum(x.beginUnadj ?? x.beginning))
    }
    const seeded = N2_DETAIL_FIXED_TYPES.map(t => ({
      id: generateRowId(),
      taxType: t,
      taxRate: 0,
      unadjBegin: beginByType.get(t) ?? 0,
      unadjPayable: 0,
      unadjPaid: 0,
      beginAdjust: 0,
      ajePayable: 0,
      ajePaid: 0,
      rjePayable: 0,
      rjePaid: 0,
      remark: '',
    }))
    await saveField('2', 'detail-rows', seeded)
  }

  return {
    rows,
    total,
    summary,
    addRow,
    removeRow,
    updateRow,
    seedDefaultRows,
    seedFromN21,
  }
}
