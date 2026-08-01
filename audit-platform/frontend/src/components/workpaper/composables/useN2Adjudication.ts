/**
 * useN2Adjudication — N2-1 审定表 composable
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 3.4
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 多税种分行数据管理（增值税/城建税/教育费附加/地方教育附加/房产税/土地使用税/印花税/所得税/其他）
 * - 每行：税种|期初|本期贷方(计提)|本期借方(缴纳)|期末|未审|AJE|RJE|审定数
 * - 85公式（审定=未审+AJE+RJE, 期末=期初+贷-借）
 * - TB回写触发(via useN2FormData.writebackTB)
 * - Row validation + subtotal
 *
 * 科目：2221 应交税费（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, watch, type ComputedRef, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useN2FormulaEngine'
import type { ChecklistResponse } from './useN2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * 税种枚举（对齐致同源模板 N2-1 审定表 13 类税种 + 保留常见子科目向后兼容）
 * 源模板顺序：企业所得税/增值税/消费税/资源税/土地增值税/城市维护建设税/车船牌照税/
 *            房产税/土地使用税/教育费附加/矿产资源补偿费/代扣代缴外国企业所得税/代扣代缴个人所得税
 */
export type N2TaxType =
  // ── 源模板 N2-1 固定 13 类 ──
  | '企业所得税'
  | '增值税'
  | '消费税'
  | '资源税'
  | '土地增值税'
  | '城市维护建设税'
  | '车船牌照税'
  | '房产税'
  | '土地使用税'
  | '教育费附加'
  | '矿产资源补偿费'
  | '代扣代缴外国企业所得税'
  | '代扣代缴个人所得税'
  // ── 常见子科目（向后兼容旧数据） ──
  | '未交增值税'
  | '城建税'
  | '地方教育附加'
  | '印花税'
  | '所得税'
  | '其他'

/** 审定表单行数据 */
export interface N2AdjudicationRow {
  /** 税种 */
  taxType: N2TaxType
  /** 期初余额 */
  beginning: number
  /** 本期贷方发生额（计提/增加） */
  creditAmount: number
  /** 本期借方发生额（缴纳/减少） */
  debitAmount: number
  /** 期末余额（公式：期初+贷方-借方，负债类） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE调整 */
  rje: number
  /** 审定数（公式：未审+AJE+RJE） */
  audited: number
}

/** 合计行 */
export interface N2AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 行级校验结果 */
export interface N2AdjRowValidation {
  taxType: N2TaxType
  /** 期末余额 vs 审定数差异（应一致） */
  endVsAuditedDiff: number
  isValid: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认税种行（对齐致同源模板 N2-1 审定表固定 13 类税种 + 其他） */
export const DEFAULT_TAX_TYPES: N2TaxType[] = [
  '企业所得税',
  '增值税',
  '消费税',
  '资源税',
  '土地增值税',
  '城市维护建设税',
  '车船牌照税',
  '房产税',
  '土地使用税',
  '教育费附加',
  '矿产资源补偿费',
  '代扣代缴外国企业所得税',
  '代扣代缴个人所得税',
  '其他',
]

const MATCH_THRESHOLD = 0.01

// ─── Helpers ─────────────────────────────────────────────────────────────────

function parseNum(v: any): number {
  if (v == null) return 0
  if (typeof v === 'string') {
    try { v = JSON.parse(v) } catch { /* noop */ }
  }
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function getFieldFromResponses(
  allResponses: Map<string, ChecklistResponse>,
  sheet: string,
  field: string,
): any {
  const itemId = `N2-${sheet}-${field}`
  const resp = allResponses.get(itemId)
  if (!resp?.conclusion) return null
  try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN2AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
  writebackTB: (auditedAmount: number) => Promise<void>
}

export function useN2Adjudication(options: UseN2AdjudicationOptions) {
  const { allResponses, saveField, getField, writebackTB } = options

  // ─── 1. 从 allResponses 提取审定表行数据 ─────────────────────────────────

  /** 审定表各税种行（公式列自动计算） */
  const rows: ComputedRef<N2AdjudicationRow[]> = computed(() => {
    const stored = getFieldFromResponses(allResponses.value, '1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? stored : []

    // 如果已有存储数据，使用存储数据；否则返回默认空行
    if (raw.length > 0) {
      return raw.map((r: any) => {
        const beginning = parseNum(r.beginning)
        const creditAmount = parseNum(r.creditAmount)
        const debitAmount = parseNum(r.debitAmount)
        const unadjusted = parseNum(r.unadjusted)
        const aje = parseNum(r.aje)
        const rje = parseNum(r.rje)
        return {
          taxType: r.taxType || '其他',
          beginning,
          creditAmount,
          debitAmount,
          endBalance: calcLiabilityEndBalance(beginning, creditAmount, debitAmount),
          unadjusted,
          aje,
          rje,
          audited: calcAuditedAmount(unadjusted, aje, rje),
        }
      })
    }

    // 默认空行
    return DEFAULT_TAX_TYPES.map(taxType => ({
      taxType,
      beginning: 0,
      creditAmount: 0,
      debitAmount: 0,
      endBalance: 0,
      unadjusted: 0,
      aje: 0,
      rje: 0,
      audited: 0,
    }))
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────────

  const total: ComputedRef<N2AdjudicationTotal> = computed(() => {
    const r = rows.value
    return {
      beginning: calcSubtotal(r.map(x => x.beginning)),
      credit: calcSubtotal(r.map(x => x.creditAmount)),
      debit: calcSubtotal(r.map(x => x.debitAmount)),
      endBalance: calcSubtotal(r.map(x => x.endBalance)),
      unadjusted: calcSubtotal(r.map(x => x.unadjusted)),
      aje: calcSubtotal(r.map(x => x.aje)),
      rje: calcSubtotal(r.map(x => x.rje)),
      audited: calcSubtotal(r.map(x => x.audited)),
    }
  })

  // ─── 3. 行级校验 ──────────────────────────────────────────────────────────

  /** 每行期末余额应等于审定数（审定表合一逻辑：审定数=期末余额） */
  const rowValidations: ComputedRef<N2AdjRowValidation[]> = computed(() => {
    return rows.value.map(row => {
      const diff = row.endBalance - row.audited
      return {
        taxType: row.taxType,
        endVsAuditedDiff: parseFloat(diff.toFixed(2)),
        isValid: Math.abs(diff) <= MATCH_THRESHOLD,
      }
    })
  })

  // ─── 4. 行更新 ────────────────────────────────────────────────────────────

  /**
   * 更新指定税种行的可编辑字段
   * 公式列(endBalance/audited)自动由computed刷新
   */
  async function updateRow(
    taxType: N2TaxType,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): Promise<void> {
    // 获取当前行数据并修改
    const stored = getField('1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? [...stored] : DEFAULT_TAX_TYPES.map(t => ({ taxType: t }))

    const idx = raw.findIndex(r => r.taxType === taxType)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
    }

    await saveField('1', 'adjudication-rows', raw)
  }

  // ─── 5. 审定数变化 → TB回写 ───────────────────────────────────────────────

  /**
   * 触发TB回写（审定合计→trial_balance 2221期末余额）
   */
  async function triggerWriteback(): Promise<void> {
    await writebackTB(total.value.audited)
  }

  // ─── 6. 保存审定表 + 同步各税种审定数到独立字段 ─────────────────────────────

  /**
   * 保存审定表数据并同步各税种审定数到独立item_id
   * 供 useN2CrossSheet 交叉验证使用
   */
  async function saveAndSync(): Promise<void> {
    // 保存整体rows
    const raw = rows.value.map(r => ({
      taxType: r.taxType,
      beginning: r.beginning,
      creditAmount: r.creditAmount,
      debitAmount: r.debitAmount,
      unadjusted: r.unadjusted,
      aje: r.aje,
      rje: r.rje,
    }))
    await saveField('1', 'adjudication-rows', raw)

    // 同步期末合计
    await saveField('1', 'end-balance-total', total.value.endBalance)

    // TB回写
    await triggerWriteback()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    total,
    rowValidations,
    updateRow,
    triggerWriteback,
    saveAndSync,
  }
}

export default useN2Adjudication

// ═══════════════════════════════════════════════════════════════════════════
// 14 列源模板对齐模型（N2-1 应交税费审定表）
//
// 源结构：项目 + 期初数(未审/账项调整/重分类/审定auto) + 期末数(同4列)
//         + 变动(未审变动额/率 + 审定变动额/率) + 原因分析
//
// beginAudited = beginUnadj + beginAje + beginRje
// endAudited   = endUnadj   + endAje   + endRje
// unadjChange  = endUnadj   - beginUnadj ; unadjRate = change / |beginUnadj|
// auditedChange= endAudited - beginAudited ; auditedRate = change / |beginAudited|
//
// 向后兼容旧字段名 beginning/creditAmount/debitAmount/unadjusted/aje/rje。
// 旧 useN2Adjudication 导出保留不动（PBT 测试用 useN2FormulaEngine，安全）。
// ═══════════════════════════════════════════════════════════════════════════

/** 14 列审定表单行 */
export interface N2Adj14Row {
  taxType: string
  /** 期初·未审 */
  beginUnadj: number
  /** 期初·账项调整 */
  beginAje: number
  /** 期初·重分类 */
  beginRje: number
  /** 期初·审定（auto = beginUnadj + beginAje + beginRje） */
  beginAudited: number
  /** 期末·未审 */
  endUnadj: number
  /** 期末·账项调整 */
  endAje: number
  /** 期末·重分类 */
  endRje: number
  /** 期末·审定（auto = endUnadj + endAje + endRje） */
  endAudited: number
  /** 未审变动额（auto = endUnadj − beginUnadj） */
  unadjChange: number
  /** 未审变动率（auto = unadjChange / |beginUnadj|） */
  unadjRate: number
  /** 审定变动额（auto = endAudited − beginAudited） */
  auditedChange: number
  /** 审定变动率（auto = auditedChange / |beginAudited|） */
  auditedRate: number
  /** 原因分析 */
  reason: string
}

/** 14 列合计行 */
export interface N2Adj14Total {
  beginUnadj: number
  beginAje: number
  beginRje: number
  beginAudited: number
  endUnadj: number
  endAje: number
  endRje: number
  endAudited: number
  unadjChange: number
  unadjRate: number
  auditedChange: number
  auditedRate: number
}

/** 14 列可编辑字段 */
export type N2Adj14EditableField =
  | 'taxType'
  | 'beginUnadj'
  | 'beginAje'
  | 'beginRje'
  | 'endUnadj'
  | 'endAje'
  | 'endRje'
  | 'reason'

function _rate(change: number, base: number): number {
  return base !== 0 ? change / Math.abs(base) : 0
}

function _map14(r: any): N2Adj14Row {
  const beginUnadj = parseNum(r.beginUnadj ?? r.beginning)
  const beginAje = parseNum(r.beginAje)
  const beginRje = parseNum(r.beginRje)
  const endUnadj = parseNum(r.endUnadj ?? r.unadjusted)
  const endAje = parseNum(r.endAje ?? r.aje)
  const endRje = parseNum(r.endRje ?? r.rje)
  const beginAudited = calcAuditedAmount(beginUnadj, beginAje, beginRje)
  const endAudited = calcAuditedAmount(endUnadj, endAje, endRje)
  const unadjChange = endUnadj - beginUnadj
  const auditedChange = endAudited - beginAudited
  return {
    taxType: r.taxType || '其他',
    beginUnadj,
    beginAje,
    beginRje,
    beginAudited,
    endUnadj,
    endAje,
    endRje,
    endAudited,
    unadjChange,
    unadjRate: _rate(unadjChange, beginUnadj),
    auditedChange,
    auditedRate: _rate(auditedChange, beginAudited),
    reason: r.reason || '',
  }
}

export interface UseN2Adjudication14Options {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
  writebackTB: (auditedAmount: number) => Promise<void>
  /** 后端 render htmlData.adjudication_prefill（无持久化行时用于种子未审期初/期末） */
  prefill?: Ref<any[] | null | undefined>
}

export function useN2Adjudication14(options: UseN2Adjudication14Options) {
  const { allResponses, saveField, getField, writebackTB, prefill } = options

  // ─── 行数据（公式列自动计算） ─────────────────────────────────────────────
  const rows: ComputedRef<N2Adj14Row[]> = computed(() => {
    const stored = getFieldFromResponses(allResponses.value, '1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? stored : []
    if (raw.length > 0) return raw.map(_map14)

    // 无持久化 → 用 prefill 种子（仅 begin/end 未审）
    const pf = prefill?.value
    if (Array.isArray(pf) && pf.length > 0) {
      return pf.map((p: any) =>
        _map14({
          taxType: p.tax_type ?? p.taxType ?? '其他',
          beginUnadj: p.begin_unadj ?? p.beginUnadj ?? 0,
          endUnadj: p.end_unadj ?? p.endUnadj ?? 0,
        }),
      )
    }

    // 默认空行
    return DEFAULT_TAX_TYPES.map(taxType => _map14({ taxType }))
  })

  // ─── 合计行 ────────────────────────────────────────────────────────────────
  const total: ComputedRef<N2Adj14Total> = computed(() => {
    const r = rows.value
    const beginUnadj = calcSubtotal(r.map(x => x.beginUnadj))
    const beginAje = calcSubtotal(r.map(x => x.beginAje))
    const beginRje = calcSubtotal(r.map(x => x.beginRje))
    const beginAudited = calcSubtotal(r.map(x => x.beginAudited))
    const endUnadj = calcSubtotal(r.map(x => x.endUnadj))
    const endAje = calcSubtotal(r.map(x => x.endAje))
    const endRje = calcSubtotal(r.map(x => x.endRje))
    const endAudited = calcSubtotal(r.map(x => x.endAudited))
    const unadjChange = endUnadj - beginUnadj
    const auditedChange = endAudited - beginAudited
    return {
      beginUnadj,
      beginAje,
      beginRje,
      beginAudited,
      endUnadj,
      endAje,
      endRje,
      endAudited,
      unadjChange,
      unadjRate: _rate(unadjChange, beginUnadj),
      auditedChange,
      auditedRate: _rate(auditedChange, beginAudited),
    }
  })

  // ─── 当前原始行（含 prefill/默认种子物化，首次编辑即持久化种子） ───────────
  function _currentRaw(): any[] {
    const stored = getField('1', 'adjudication-rows')
    if (Array.isArray(stored) && stored.length > 0) {
      return stored.map((x: any) => ({ ...x }))
    }
    return rows.value.map(r => ({
      taxType: r.taxType,
      beginUnadj: r.beginUnadj,
      beginAje: r.beginAje,
      beginRje: r.beginRje,
      endUnadj: r.endUnadj,
      endAje: r.endAje,
      endRje: r.endRje,
      reason: r.reason,
    }))
  }

  async function updateRow(index: number, field: N2Adj14EditableField, value: any): Promise<void> {
    const raw = _currentRaw()
    if (index >= 0 && index < raw.length) {
      raw[index] = { ...raw[index], [field]: value }
      await saveField('1', 'adjudication-rows', raw)
    }
  }

  async function addRow(taxType: string): Promise<void> {
    const raw = _currentRaw()
    raw.push({
      taxType,
      beginUnadj: 0,
      beginAje: 0,
      beginRje: 0,
      endUnadj: 0,
      endAje: 0,
      endRje: 0,
      reason: '',
    })
    await saveField('1', 'adjudication-rows', raw)
  }

  async function removeRow(index: number): Promise<void> {
    const raw = _currentRaw()
    if (index >= 0 && index < raw.length) {
      raw.splice(index, 1)
      await saveField('1', 'adjudication-rows', raw)
    }
  }

  async function saveAndSync(): Promise<void> {
    const raw = _currentRaw()
    await saveField('1', 'adjudication-rows', raw)
    await saveField('1', 'end-audited-total', total.value.endAudited)
    await writebackTB(total.value.endAudited)
  }

  return {
    rows,
    total,
    updateRow,
    addRow,
    removeRow,
    saveAndSync,
  }
}
