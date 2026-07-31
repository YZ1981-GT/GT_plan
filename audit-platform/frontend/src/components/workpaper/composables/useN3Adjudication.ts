/**
 * useN3Adjudication — N3-1 审定表 composable
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 3.3
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 管理24×14审定表数据（按应纳税暂时性差异项目分行）
 * - 固定行：固定资产折旧差异/公允价值变动/一次性税前扣除/长期股权投资/其他 + 期初/本期变动/期末
 * - 每行：项目|期初余额|本期贷方|本期借方|未审数|AJE|RJE|审定数
 * - 78公式（审定=未审+AJE+RJE, 负债类期末=期初+贷-借）
 * - SUMIF等价：从N3-2明细表按分类汇总
 * - TB回写触发(via useN3FormData.writebackTB)
 * - Row validation + subtotal
 * - 与N3-2明细合计交叉验证
 *
 * 科目：2901 递延所得税负债（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcChange,
  calcChangeRate,
} from './useN3FormulaEngine'
import type { ChecklistResponse } from './useN3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 应纳税暂时性差异项目分类 */
/**
 * 应纳税暂时性差异项目分类（对齐致同源模板 N3-1 审定表 A7~A11 固定 5 类）
 * 源模板顺序：评估增值/公允价值变动/使用权资产/购入摊销年限大于税法规定的资产/其他
 */
export type N3DiffCategory =
  // ── 源模板 N3-1 固定 5 类 ──
  | '评估增值'
  | '公允价值变动'
  | '使用权资产'
  | '购入摊销年限大于税法规定的资产'
  | '其他'
  // ── 向后兼容旧数据 ──
  | '固定资产折旧差异'
  | '一次性税前扣除'
  | '长期股权投资'
  | '投资性房地产'
  | '无形资产'

/** 审定表单行数据 */
export interface N3AdjudicationRow {
  /** 应纳税暂时性差异项目分类 */
  category: N3DiffCategory
  /** 期初余额（贷方余额） */
  beginning: number
  /** 本期贷方发生额（确认/增加递延税负债） */
  creditAmount: number
  /** 本期借方发生额（转回/减少递延税负债） */
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
  /** 变动额（期末-期初） */
  change: number
  /** 变动率 */
  changeRate: number
}

/** 合计行 */
export interface N3AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  change: number
}

/** 行级校验结果 */
export interface N3AdjRowValidation {
  category: N3DiffCategory
  /** 期末余额 vs 审定数差异（应一致） */
  endVsAuditedDiff: number
  isValid: boolean
}

/** 与N3-2明细表交叉验证结果 */
export interface N3CrossValidation {
  /** 审定表合计 */
  adjudicationTotal: number
  /** 明细表合计 */
  detailTotal: number
  /** 差异 */
  diff: number
  /** 是否匹配 */
  isMatch: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认应纳税暂时性差异项目分类行（对齐致同源模板 N3-1 审定表固定 5 类） */
export const DEFAULT_CATEGORIES: N3DiffCategory[] = [
  '评估增值',
  '公允价值变动',
  '使用权资产',
  '购入摊销年限大于税法规定的资产',
  '其他',
]

/**
 * 后端语义槽 → N3-1 分类行（单一真源）。
 *
 * 语义槽由 `backend/app/services/deferred_tax_shared.LIABILITY_SLOTS` 下发
 * （与 N1 披露表负债段共用同一套分类逻辑，不新造第 2 套）。
 *
 * 🔴 `afs_fv` 与 `investment_property_fv` **都落到「公允价值变动」** ——
 * N1 披露表把公允价值变动细分为「可供出售金融资产」与「投资性房地产」两行，
 * 而 N3-1 审定表源模板只有一行「公允价值变动」→ 两槽聚合。
 * 🔴 「评估增值」**无对应语义槽**（非暂时性差异的科目分类维度）→ 不预填，宁缺勿造。
 */
export const N3_SLOT_TO_CATEGORY: Readonly<Record<string, N3DiffCategory>> = {
  depreciation: '购入摊销年限大于税法规定的资产',
  afs_fv: '公允价值变动',
  investment_property_fv: '公允价值变动',
  lease: '使用权资产',
  other: '其他',
}

/** 阈值：差异容忍度 */
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
  const itemId = `N3-${sheet}-${field}`
  const resp = allResponses.get(itemId)
  if (!resp?.conclusion) return null
  try { return JSON.parse(resp.conclusion) } catch { return resp.conclusion }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN3AdjudicationOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
  writebackTB: (auditedAmount: number) => Promise<void>
  /**
   * 四表分类预填（后端 `adjudication_prefill`：2901 叶子子科目 → 五语义槽）。
   * 无子科目时为空 dict → 回退「其他」行总额 seed。
   */
  adjudicationPrefill?: Ref<Record<string, { opening: number; closing: number }>>
}

export function useN3Adjudication(options: UseN3AdjudicationOptions) {
  const { allResponses, saveField, getField, writebackTB } = options
  const slotPrefill = computed<Record<string, { opening: number; closing: number }>>(
    () => options.adjudicationPrefill?.value ?? {},
  )

  // ─── 1. 从 allResponses 提取审定表行数据 ─────────────────────────────────

  /** 审定表各项目行（公式列自动计算） */
  const rows: ComputedRef<N3AdjudicationRow[]> = computed(() => {
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
        const endBalance = calcLiabilityEndBalance(beginning, creditAmount, debitAmount)
        const change = calcChange(endBalance, beginning)
        return {
          category: r.category || '其他',
          beginning,
          creditAmount,
          debitAmount,
          endBalance,
          unadjusted,
          aje,
          rje,
          audited: calcAuditedAmount(unadjusted, aje, rje),
          change,
          changeRate: calcChangeRate(beginning, change),
        }
      })
    }

    // 默认空行 —— 四表 seed 两级优先级：
    // ① `adjudicationPrefill`（后端按 2901 **叶子子科目**归五语义槽）→ 落到对应分类行
    // ② 无子科目时回退 `N3-1-tb-prefill` 总额 → 落「其他」行（原有行为）
    // 🔴 原实现**只有 ②**，客户按子科目挂账时分类信息全丢（都堆在「其他」）。
    const slots = slotPrefill.value
    const bySlot = new Map<string, { opening: number; closing: number }>()
    for (const [slot, v] of Object.entries(slots)) {
      const cat = N3_SLOT_TO_CATEGORY[slot]
      if (!cat) continue
      const cell = bySlot.get(cat) || { opening: 0, closing: 0 }
      cell.opening += parseNum(v?.opening)
      cell.closing += parseNum(v?.closing)
      bySlot.set(cat, cell)
    }
    const hasSlots = bySlot.size > 0

    const prefill = getFieldFromResponses(allResponses.value, '1', 'tb-prefill')
    const seedBeginning = prefill ? parseNum(prefill.beginning) : 0
    const seedCredit = prefill ? parseNum(prefill.creditAmount) : 0
    const seedDebit = prefill ? parseNum(prefill.debitAmount) : 0
    const seedUnadjusted = prefill ? parseNum(prefill.unadjusted) : 0

    return DEFAULT_CATEGORIES.map(category => {
      const slot = hasSlots ? bySlot.get(category) : undefined
      const isOtherRow = !hasSlots && category === '其他'
      const beginning = slot ? Math.round(slot.opening * 100) / 100 : (isOtherRow ? seedBeginning : 0)
      const creditAmount = isOtherRow ? seedCredit : 0
      const debitAmount = isOtherRow ? seedDebit : 0
      const unadjusted = slot
        ? Math.round(slot.closing * 100) / 100
        : (isOtherRow ? seedUnadjusted : 0)
      const endBalance = slot
        ? Math.round(slot.closing * 100) / 100
        : calcLiabilityEndBalance(beginning, creditAmount, debitAmount)
      const change = calcChange(endBalance, beginning)
      return {
        category,
        beginning,
        creditAmount,
        debitAmount,
        endBalance,
        unadjusted,
        aje: 0,
        rje: 0,
        audited: calcAuditedAmount(unadjusted, 0, 0),
        change,
        changeRate: calcChangeRate(beginning, change),
      }
    })
  })

  // ─── 2. 合计行 ────────────────────────────────────────────────────────────

  const total: ComputedRef<N3AdjudicationTotal> = computed(() => {
    const r = rows.value
    const beginningTotal = calcSubtotal(r.map(x => x.beginning))
    const endBalanceTotal = calcSubtotal(r.map(x => x.endBalance))
    return {
      beginning: beginningTotal,
      credit: calcSubtotal(r.map(x => x.creditAmount)),
      debit: calcSubtotal(r.map(x => x.debitAmount)),
      endBalance: endBalanceTotal,
      unadjusted: calcSubtotal(r.map(x => x.unadjusted)),
      aje: calcSubtotal(r.map(x => x.aje)),
      rje: calcSubtotal(r.map(x => x.rje)),
      audited: calcSubtotal(r.map(x => x.audited)),
      change: calcChange(endBalanceTotal, beginningTotal),
    }
  })

  // ─── 3. 行级校验（期末 vs 审定数） ────────────────────────────────────────

  /** 每行期末余额应等于审定数（审定表合一逻辑） */
  const rowValidations: ComputedRef<N3AdjRowValidation[]> = computed(() => {
    return rows.value.map(row => {
      const diff = row.endBalance - row.audited
      return {
        category: row.category,
        endVsAuditedDiff: parseFloat(diff.toFixed(2)),
        isValid: Math.abs(diff) <= MATCH_THRESHOLD,
      }
    })
  })

  // ─── 4. 与N3-2明细表交叉验证 ──────────────────────────────────────────────

  /**
   * SUMIF等价：从N3-2明细表按分类汇总与审定表合计对比
   * 依赖 N3-2 的期末递延税负债合计存储在 allResponses
   */
  const crossValidation: ComputedRef<N3CrossValidation> = computed(() => {
    const adjTotal = total.value.audited
    const detailTotal = parseNum(
      getFieldFromResponses(allResponses.value, '2', 'end-dtl-total'),
    )
    const diff = adjTotal - detailTotal
    return {
      adjudicationTotal: adjTotal,
      detailTotal,
      diff: parseFloat(diff.toFixed(2)),
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 5. 行更新 ────────────────────────────────────────────────────────────

  /**
   * 更新指定分类行的可编辑字段
   * 公式列(endBalance/audited/change/changeRate)自动由computed刷新
   */
  async function updateRow(
    category: N3DiffCategory,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): Promise<void> {
    // 获取当前行数据并修改
    const stored = getField('1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) ? [...stored] : DEFAULT_CATEGORIES.map(c => ({ category: c }))

    const idx = raw.findIndex(r => r.category === category)
    if (idx >= 0) {
      raw[idx] = { ...raw[idx], [field]: value }
    }

    await saveField('1', 'adjudication-rows', raw)
  }

  // ─── 5b. 从四表库带入未审数（按语义槽落分类行）─────────────────────────────

  /**
   * 从四表库带入期初/未审数（后端 `adjudication_prefill` 按 2901 叶子子科目归语义槽）。
   *
   * 🔴 只填空不覆盖：目标行的 `beginning` / `unadjusted` 已非 0 时保留（手工优先）。
   * 🔴 无子科目（`prefill` 为空）→ 回退把 `N3-1-tb-prefill` 的总额落「其他」行
   *    （即原有行为），并由调用方提示需人工按分类拆分。
   *
   * @returns `{ filled, total, bySlot }`
   */
  async function pullFromTB(
    prefill?: Record<string, { opening: number; closing: number }> | null,
  ): Promise<{ filled: number; total: number; bySlot: boolean }> {
    const slots = prefill && Object.keys(prefill).length > 0 ? prefill : null

    const stored = getField('1', 'adjudication-rows')
    const raw: any[] = Array.isArray(stored) && stored.length > 0
      ? stored.map((r: any) => ({ ...r }))
      : DEFAULT_CATEGORIES.map((c) => ({ category: c }))

    let filled = 0
    let total = 0

    if (slots) {
      // 语义槽 → 分类行聚合（两个公允价值槽合并到同一行）
      const byCategory = new Map<string, { opening: number; closing: number }>()
      for (const [slot, v] of Object.entries(slots)) {
        const cat = N3_SLOT_TO_CATEGORY[slot]
        if (!cat) continue
        const cell = byCategory.get(cat) || { opening: 0, closing: 0 }
        cell.opening += parseNum(v?.opening)
        cell.closing += parseNum(v?.closing)
        byCategory.set(cat, cell)
      }
      for (const [cat, v] of byCategory) {
        total += v.closing
        const idx = raw.findIndex((r) => r.category === cat)
        if (idx < 0) continue
        const row = raw[idx]
        if (parseNum(row.beginning) !== 0 || parseNum(row.unadjusted) !== 0) continue
        raw[idx] = {
          ...row,
          beginning: Math.round(v.opening * 100) / 100,
          unadjusted: Math.round(v.closing * 100) / 100,
        }
        filled += 1
      }
    } else {
      // 回退：总额落「其他」行（原有行为）
      const seed = getFieldFromResponses(allResponses.value, '1', 'tb-prefill')
      const opening = parseNum(seed?.beginning)
      const closing = parseNum(seed?.unadjusted)
      total = closing
      const idx = raw.findIndex((r) => r.category === '其他')
      if (idx >= 0 && (opening !== 0 || closing !== 0)
          && parseNum(raw[idx].beginning) === 0 && parseNum(raw[idx].unadjusted) === 0) {
        raw[idx] = { ...raw[idx], beginning: opening, unadjusted: closing }
        filled = 1
      }
    }

    if (filled > 0) await saveField('1', 'adjudication-rows', raw)
    return { filled, total: Math.round(total * 100) / 100, bySlot: Boolean(slots) }
  }

  // ─── 6. 审定数变化 → TB回写 ───────────────────────────────────────────────

  /**
   * 触发TB回写（审定合计→trial_balance 2901期末余额）
   */
  async function triggerWriteback(): Promise<void> {
    await writebackTB(total.value.audited)
  }

  // ─── 7. 保存审定表 + 同步合计 ─────────────────────────────────────────────

  /**
   * 保存审定表数据并同步合计到独立字段
   * 供 useN3CrossSheet 和 N5 联动使用
   */
  async function saveAndSync(): Promise<void> {
    // 保存整体rows（只存可编辑字段，公式列由computed计算）
    const raw = rows.value.map(r => ({
      category: r.category,
      beginning: r.beginning,
      creditAmount: r.creditAmount,
      debitAmount: r.debitAmount,
      unadjusted: r.unadjusted,
      aje: r.aje,
      rje: r.rje,
    }))
    await saveField('1', 'adjudication-rows', raw)

    // 同步期末合计（供交叉验证+N5核对使用）
    await saveField('1', 'end-balance-total', total.value.endBalance)
    await saveField('1', 'audited-total', total.value.audited)
    await saveField('1', 'change-total', total.value.change)

    // TB回写
    await triggerWriteback()
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    rows,
    total,
    rowValidations,
    crossValidation,
    updateRow,
    pullFromTB,
    triggerWriteback,
    saveAndSync,
  }
}

export default useN3Adjudication
