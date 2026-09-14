/**
 * useH1Adjudication — H1-1 审定表 composable
 *
 * 对齐致同源模板「固定资产、累计折旧、减值准备审定表」：
 *   一、原值(1601) → 二、累计折旧(1602) → 三、减值准备(1603) → 四、净值
 * 保留数字化增强：三角勾稽、AJE/RJE、TB回写、H1-2交叉验证、变动额/率。
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Requirements: 2.1-2.12
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcNetValue,
  calcChangeRate,
} from './useH1FormulaEngine'
import {
  H1_FA_CATEGORIES,
  allocateH3AdjustmentsByAccount,
  normalizeFaCategory,
  type H1CategoryPrefillPayload,
} from './h1CategoryClassify'

export { H1_FA_CATEGORIES as DEFAULT_COST_CATEGORIES } from './h1CategoryClassify'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（原值 / 折旧 / 减值） */
export interface AdjudicationRow {
  rowId: string
  category: string
  beginBalance: number
  debit: number
  credit: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  isSubtotal?: boolean
  isEditable?: boolean
}

/** 净值行（按分类派生：原值−折旧−减值） */
export interface NetValueRow {
  rowId: string
  category: string
  beginNet: number
  endNet: number
  changeAmount: number
  changeRate: number | null
  /** 变动率绝对值 ≥30% 须说明（对齐源模板） */
  isSignificant: boolean
  /** 与 H1-6 变动分析共用说明（H1-6-change-explanations） */
  explanation: string
  isSubtotal?: boolean
}

export interface ReconciliationResult {
  layer: string
  difference: number
  isBalanced: boolean
}

export interface DifferenceRow {
  label: string
  audited: number
  tbAmount: number
  difference: number
}

/** 源模板审定表下方定性说明 */
export interface QualitativeNotes {
  /** (1) 净值重大变动原因（尤其变动率>30%） */
  fluctuation: string
  /** (2) 在建工程转入 */
  cipTransfer: string
  /** (3) 抵押、担保 */
  pledge: string
  /** (4) 出售、置换 */
  disposal: string
  /** (5) 租赁（融资租入/经营租出） */
  lease: string
}

export type AdjudicationBlock = 'cost' | 'dep' | 'impair'

// ─── Constants ───────────────────────────────────────────────────────────────

/** 对齐源模板分类 */
const DEFAULT_COST_CATEGORIES = H1_FA_CATEGORIES

const ITEM_PREFIX = 'H1-1'
/** 与 H1-6 共用：按分类变动说明双向联动 */
const CHANGE_EXPL_KEY = 'H1-6-change-explanations'
const CHANGE_RATE_THRESHOLD = 30

const EMPTY_NOTES: QualitativeNotes = {
  fluctuation: '',
  cipTransfer: '',
  pledge: '',
  disposal: '',
  lease: '',
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _blankRow(rowId: string, category: string, editable: boolean): AdjudicationRow {
  return {
    rowId,
    category,
    beginBalance: 0,
    debit: 0,
    credit: 0,
    endBalance: 0,
    unadjusted: 0,
    aje: 0,
    rje: 0,
    audited: 0,
    isSubtotal: false,
    isEditable: editable,
  }
}

function _sumRows(detail: AdjudicationRow[], category: string, rowId: string): AdjudicationRow {
  return {
    rowId,
    category,
    beginBalance: calcSubtotal(detail.map((r) => r.beginBalance)),
    debit: calcSubtotal(detail.map((r) => r.debit)),
    credit: calcSubtotal(detail.map((r) => r.credit)),
    endBalance: calcSubtotal(detail.map((r) => r.endBalance)),
    unadjusted: calcSubtotal(detail.map((r) => r.unadjusted)),
    aje: calcSubtotal(detail.map((r) => r.aje)),
    rje: calcSubtotal(detail.map((r) => r.rje)),
    audited: calcSubtotal(detail.map((r) => r.audited)),
    isSubtotal: true,
    isEditable: false,
  }
}

function _recalcRow(row: AdjudicationRow, isAsset: boolean): void {
  if (isAsset) {
    row.endBalance = calcAssetEndBalance(row.beginBalance, row.debit, row.credit)
  } else {
    row.endBalance = calcContraEndBalance(row.beginBalance, row.debit, row.credit)
  }
  row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
}

function _migrateCategory(name: string): string {
  return normalizeFaCategory(name)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    tbUnadjusted?: Ref<{ cost1601: number; dep1602: number; impair1603?: number }>
    crossSheetCostAudited?: Ref<number>
    crossSheetDepAudited?: Ref<number>
    crossSheetImpairAudited?: Ref<number>
    h3AjeTotal?: Ref<number>
    h3RjeTotal?: Ref<number>
    /** TB 子科目按分类预填（来自 render html_data） */
    categoryPrefill?: Ref<H1CategoryPrefillPayload | null | undefined>
    onSave?: (itemId: string, value: any) => void
    onWritebackTB?: (auditedCost: number, auditedDep: number, auditedImpair: number) => Promise<void>
    onPublishEvent?: (event: string, payload: any) => void
  },
) {
  const costRows = ref<AdjudicationRow[]>([])
  const depRows = ref<AdjudicationRow[]>([])
  const impairRows = ref<AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')
  const qualitativeNotes = ref<QualitativeNotes>({ ...EMPTY_NOTES })
  /** 按分类净值/原值变动说明（与 H1-6 共用键） */
  const changeExplanations = ref<Record<string, string>>({})
  const prefillApplied = ref(false)

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try {
      return JSON.parse(raw)
    } catch {
      return null
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any, prefix: string): AdjudicationRow {
    const category = _migrateCategory(raw.category ?? '')
    const row: AdjudicationRow = {
      rowId: raw.rowId ?? `row-${prefix}-${Math.random().toString(36).slice(2, 10)}`,
      category,
      beginBalance: Number(raw.beginBalance) || 0,
      debit: Number(raw.debit) || 0,
      credit: Number(raw.credit) || 0,
      endBalance: Number(raw.endBalance) || 0,
      unadjusted: Number(raw.unadjusted) || 0,
      aje: Number(raw.aje) || 0,
      rje: Number(raw.rje) || 0,
      audited: Number(raw.audited) || 0,
      isSubtotal: false,
      isEditable: raw.isEditable ?? true,
    }
    _recalcRow(row, prefix === 'c')
    return row
  }

  /** 明细行不含小计（小计由 computed 派生，避免双合计） */
  function _buildDefaultRows(prefix: string): AdjudicationRow[] {
    return DEFAULT_COST_CATEGORIES.map((cat) =>
      _blankRow(`row-${prefix}-${cat}`, cat, true),
    )
  }

  function _loadRows(): void {
    const costData = _getJson(`${ITEM_PREFIX}-cost-rows`)
    const depData = _getJson(`${ITEM_PREFIX}-dep-rows`)
    const impairData = _getJson(`${ITEM_PREFIX}-impair-rows`)

    if (Array.isArray(costData) && costData.length > 0) {
      costRows.value = costData.filter((r: any) => !r.isSubtotal).map((r: any) => _normalizeRow(r, 'c'))
    } else {
      costRows.value = _buildDefaultRows('c')
    }

    if (Array.isArray(depData) && depData.length > 0) {
      depRows.value = depData.filter((r: any) => !r.isSubtotal).map((r: any) => _normalizeRow(r, 'd'))
    } else {
      depRows.value = _buildDefaultRows('d')
    }

    if (Array.isArray(impairData) && impairData.length > 0) {
      impairRows.value = impairData.filter((r: any) => !r.isSubtotal).map((r: any) => _normalizeRow(r, 'i'))
    } else {
      impairRows.value = _buildDefaultRows('i')
    }

    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)

    const notesRaw = _getJson(`${ITEM_PREFIX}-qualitative-notes`)
    qualitativeNotes.value = {
      fluctuation: String(notesRaw?.fluctuation ?? ''),
      cipTransfer: String(notesRaw?.cipTransfer ?? ''),
      pledge: String(notesRaw?.pledge ?? ''),
      disposal: String(notesRaw?.disposal ?? ''),
      lease: String(notesRaw?.lease ?? ''),
    }

    // 与 H1-6 共用变动说明
    const expl = _getJson(CHANGE_EXPL_KEY)
    changeExplanations.value =
      expl && typeof expl === 'object' && !Array.isArray(expl)
        ? { ...(expl as Record<string, string>) }
        : {}
  }

  // ─── Subtotals ─────────────────────────────────────────────────────────────

  const costSubtotal = computed(() =>
    _sumRows(costRows.value.filter((r) => !r.isSubtotal), '固定资产-原值合计', 'row-c-subtotal'),
  )
  const depSubtotal = computed(() =>
    _sumRows(depRows.value.filter((r) => !r.isSubtotal), '累计折旧合计', 'row-d-subtotal'),
  )
  const impairSubtotal = computed(() =>
    _sumRows(impairRows.value.filter((r) => !r.isSubtotal), '减值准备合计', 'row-i-subtotal'),
  )

  /** 固定资产净值 = 原值审定 − 累计折旧审定 − 减值准备审定 */
  const netValueAudited = computed(() =>
    calcNetValue(costSubtotal.value.audited, depSubtotal.value.audited, impairSubtotal.value.audited),
  )

  const netValueBegin = computed(() =>
    calcNetValue(
      costSubtotal.value.beginBalance,
      depSubtotal.value.beginBalance,
      impairSubtotal.value.beginBalance,
    ),
  )

  /** 四、净值：按分类派生 + 变动额/率（对齐源模板） */
  const netRows = computed<NetValueRow[]>(() => {
    const byCat = (rows: AdjudicationRow[]) => {
      const m = new Map<string, AdjudicationRow>()
      for (const r of rows.filter((x) => !x.isSubtotal)) m.set(r.category, r)
      return m
    }
    const costs = byCat(costRows.value)
    const deps = byCat(depRows.value)
    const impairs = byCat(impairRows.value)
    const cats = [
      ...new Set([
        ...costs.keys(),
        ...deps.keys(),
        ...impairs.keys(),
        ...DEFAULT_COST_CATEGORIES,
      ]),
    ]

    const detail: NetValueRow[] = cats.map((cat) => {
      const c = costs.get(cat)
      const d = deps.get(cat)
      const i = impairs.get(cat)
      const beginNet = calcNetValue(c?.beginBalance ?? 0, d?.beginBalance ?? 0, i?.beginBalance ?? 0)
      const endNet = calcNetValue(c?.audited ?? 0, d?.audited ?? 0, i?.audited ?? 0)
      const changeAmount = endNet - beginNet
      const changeRate = calcChangeRate(endNet, beginNet)
      return {
        rowId: `row-n-${cat}`,
        category: cat,
        beginNet,
        endNet,
        changeAmount,
        changeRate,
        isSignificant: changeRate != null && Math.abs(changeRate) >= CHANGE_RATE_THRESHOLD,
        explanation: changeExplanations.value[cat] || '',
        isSubtotal: false,
      }
    })

    const beginNet = calcSubtotal(detail.map((r) => r.beginNet))
    const endNet = calcSubtotal(detail.map((r) => r.endNet))
    const changeAmount = endNet - beginNet
    const changeRate = calcChangeRate(endNet, beginNet)
    detail.push({
      rowId: 'row-n-subtotal',
      category: '净值合计',
      beginNet,
      endNet,
      changeAmount,
      changeRate,
      isSignificant: changeRate != null && Math.abs(changeRate) >= CHANGE_RATE_THRESHOLD,
      explanation: '',
      isSubtotal: true,
    })
    return detail
  })

  const significantNetChanges = computed(() =>
    netRows.value.filter((r) => !r.isSubtotal && r.isSignificant),
  )

  // ─── Triangular reconciliation ─────────────────────────────────────────────

  const reconciliationResults = computed<ReconciliationResult[]>(() => {
    const cs = costSubtotal.value
    const ds = depSubtotal.value
    const is_ = impairSubtotal.value
    const layers: Array<{ layer: string; begin: number; inc: number; dec: number; end: number }> = [
      { layer: '原值', begin: cs.beginBalance, inc: cs.debit, dec: cs.credit, end: cs.endBalance },
      // 备抵：期末=期初+贷方(增加)-借方(减少)
      { layer: '累计折旧', begin: ds.beginBalance, inc: ds.credit, dec: ds.debit, end: ds.endBalance },
      { layer: '减值准备', begin: is_.beginBalance, inc: is_.credit, dec: is_.debit, end: is_.endBalance },
    ]
    return layers.map(({ layer, begin, inc, dec, end }) => {
      const difference = calcTriangleReconciliation(begin, inc, dec, end)
      return { layer, difference, isBalanced: Math.abs(difference) < 0.01 }
    })
  })

  // ─── TB差异 / H1-2交叉 / H1-3调整勾稽 ──────────────────────────────────────

  const differenceRows = computed<DifferenceRow[]>(() => {
    const tb = options?.tbUnadjusted?.value ?? { cost1601: 0, dep1602: 0, impair1603: 0 }
    return [
      {
        label: '固定资产原值(1601)',
        audited: costSubtotal.value.audited,
        tbAmount: tb.cost1601,
        difference: costSubtotal.value.audited - tb.cost1601,
      },
      {
        label: '累计折旧(1602)',
        audited: depSubtotal.value.audited,
        tbAmount: tb.dep1602,
        difference: depSubtotal.value.audited - tb.dep1602,
      },
      {
        label: '减值准备(1603)',
        audited: impairSubtotal.value.audited,
        tbAmount: tb.impair1603 ?? 0,
        difference: impairSubtotal.value.audited - (tb.impair1603 ?? 0),
      },
      {
        label: '固定资产净值',
        audited: netValueAudited.value,
        tbAmount: tb.cost1601 - tb.dep1602 - (tb.impair1603 ?? 0),
        difference:
          netValueAudited.value - (tb.cost1601 - tb.dep1602 - (tb.impair1603 ?? 0)),
      },
    ]
  })

  const crossValidation = computed(() => {
    const costFromDetail = options?.crossSheetCostAudited?.value ?? 0
    const depFromDetail = options?.crossSheetDepAudited?.value ?? 0
    const impairFromDetail = options?.crossSheetImpairAudited?.value ?? 0
    const costDiff = costSubtotal.value.audited - costFromDetail
    const depDiff = depSubtotal.value.audited - depFromDetail
    const impairDiff = impairSubtotal.value.audited - impairFromDetail
    const hasDetail = costFromDetail !== 0 || depFromDetail !== 0 || impairFromDetail !== 0
    return {
      costDiff,
      depDiff,
      impairDiff,
      hasCostWarning: hasDetail && Math.abs(costDiff) > 0.01,
      hasDepWarning: hasDetail && Math.abs(depDiff) > 0.01,
      hasImpairWarning: hasDetail && Math.abs(impairDiff) > 0.01,
    }
  })

  /** H1-3 调整净额 vs 本表 AJE/RJE 合计 */
  const adjustmentCheck = computed(() => {
    const h3Aje = options?.h3AjeTotal?.value ?? 0
    const h3Rje = options?.h3RjeTotal?.value ?? 0
    const localAje = costSubtotal.value.aje + depSubtotal.value.aje + impairSubtotal.value.aje
    const localRje = costSubtotal.value.rje + depSubtotal.value.rje + impairSubtotal.value.rje
    return {
      h3Aje,
      h3Rje,
      localAje,
      localRje,
      ajeDiff: localAje - h3Aje,
      rjeDiff: localRje - h3Rje,
      hasAjeWarning: Math.abs(h3Aje) > 0.01 && Math.abs(localAje - h3Aje) > 0.01,
      hasRjeWarning: Math.abs(h3Rje) > 0.01 && Math.abs(localRje - h3Rje) > 0.01,
    }
  })

  // ─── Mutations ─────────────────────────────────────────────────────────────

  function _rowsOf(block: AdjudicationBlock): Ref<AdjudicationRow[]> {
    if (block === 'cost') return costRows
    if (block === 'dep') return depRows
    return impairRows
  }

  function updateCell(
    block: AdjudicationBlock,
    rowId: string,
    field: keyof AdjudicationRow,
    value: number,
  ): void {
    const rows = _rowsOf(block).value
    const row = rows.find((r) => r.rowId === rowId)
    if (!row || row.isSubtotal) return

    ;(row as any)[field] = value
    _recalcRow(row, block === 'cost')
    _persist()
  }

  /**
   * 将 H1-3 调整按科目码(1601/1602/1603)+名称关键词分摊到各分类 AJE/RJE。
   * 覆盖本表既有 AJE/RJE（以 H1-3 为权威来源）。
   */
  function syncAdjustmentsFromH3(): { applied: boolean; message: string } {
    const item = allResponses.value.get('H1-3-rows')
    let raw: any[] = []
    try {
      const r = item?.remark
      raw = typeof r === 'string' ? JSON.parse(r || '[]') : (r as any[]) || []
    } catch {
      raw = []
    }
    if (!Array.isArray(raw) || raw.length === 0) {
      return { applied: false, message: 'H1-3 暂无调整分录' }
    }

    const alloc = allocateH3AdjustmentsByAccount(raw)
    if (alloc.applied === 0) {
      return {
        applied: false,
        message: `H1-3 有 ${raw.length} 条分录，但无 1601/1602/1603 科目可分摊`,
      }
    }

    const applyBlock = (
      rows: AdjudicationRow[],
      map: Record<string, { aje: number; rje: number }>,
      isAsset: boolean,
    ) => {
      for (const row of rows) {
        if (row.isSubtotal) continue
        const hit = map[row.category] || { aje: 0, rje: 0 }
        row.aje = hit.aje
        row.rje = hit.rje
        _recalcRow(row, isAsset)
      }
    }
    applyBlock(costRows.value, alloc.cost, true)
    applyBlock(depRows.value, alloc.dep, false)
    applyBlock(impairRows.value, alloc.impair, false)
    _persist()

    return {
      applied: true,
      message: `已按科目码分摊 ${alloc.applied} 条至分类（跳过非固定资产科目 ${alloc.skipped} 条）`,
    }
  }

  /**
   * 从 TB 子科目预填各分类期初/发生/未审数。
   * @param force 为 true 时覆盖已有手工数；false 时仅填全 0 行
   */
  function applyCategoryPrefill(force = false): { applied: boolean; message: string } {
    const payload = options?.categoryPrefill?.value
    if (!payload?.categories?.length) {
      return { applied: false, message: '无 TB 子科目预填数据，请确认已导入科目余额表' }
    }

    const byCat = new Map(payload.categories.map((c) => [String(c.category), c]))
    let filled = 0

    const fill = (
      rows: AdjudicationRow[],
      pick: 'cost' | 'dep' | 'impair',
      isAsset: boolean,
    ) => {
      for (const row of rows) {
        if (row.isSubtotal) continue
        const catData = byCat.get(row.category)
        const src = catData?.[pick]
        if (!src) continue
        const hasData = src.begin || src.debit || src.credit || src.end || src.unadjusted
        if (!hasData) continue
        const rowEmpty =
          !row.beginBalance && !row.debit && !row.credit && !row.unadjusted && !row.aje && !row.rje
        if (!force && !rowEmpty) continue
        row.beginBalance = src.begin
        row.debit = src.debit
        row.credit = src.credit
        row.unadjusted = src.unadjusted || src.end
        // 后端标记需复核的分类（纯兜底启发式归入其他设备）
        if ((catData as any)?.needs_review || (catData as any)?.needsReview) {
          if (!(row as any).remark?.includes('请复核分类')) {
            ;(row as any).remark = [(row as any).remark, '⚠️请复核分类（启发式兜底）'].filter(Boolean).join('；')
          }
        }
        _recalcRow(row, isAsset)
        filled++
      }
    }

    fill(costRows.value, 'cost', true)
    fill(depRows.value, 'dep', false)
    fill(impairRows.value, 'impair', false)

    if (filled === 0) {
      return { applied: false, message: force ? '预填数据为空' : '各分类已有数据，未覆盖；可强制重新预填' }
    }
    _persist()
    prefillApplied.value = true
    return {
      applied: true,
      message: `已从 TB 子科目预填 ${filled} 个分类区块（原值/折旧/减值）`,
    }
  }

  /** 写入分类变动说明 → 同步 H1-6 */
  function setChangeExplanation(category: string, text: string): void {
    changeExplanations.value = { ...changeExplanations.value, [category]: text }
    options?.onSave?.(CHANGE_EXPL_KEY, { ...changeExplanations.value })
    // 重大变动汇总进 qualitativeNotes.fluctuation（若用户未手写长文）
    _syncFluctuationFromExplanations()
  }

  function _syncFluctuationFromExplanations(): void {
    const parts = significantNetChanges.value
      .map((r) => {
        const expl = changeExplanations.value[r.category]
        if (!expl) return null
        const rate = r.changeRate != null ? `${r.changeRate.toFixed(1)}%` : ''
        return `${r.category}（${rate}）：${expl}`
      })
      .filter(Boolean) as string[]
    if (!parts.length) return
    const auto = parts.join('；')
    const cur = qualitativeNotes.value.fluctuation || ''
    // 仅当空或此前由系统拼接时更新，避免覆盖用户自由叙述
    if (!cur || cur.includes('）：')) {
      qualitativeNotes.value = { ...qualitativeNotes.value, fluctuation: auto }
      options?.onSave?.(`${ITEM_PREFIX}-qualitative-notes`, { ...qualitativeNotes.value })
    }
  }

  async function publishAdjudicated(): Promise<void> {
    const auditedCost = costSubtotal.value.audited
    const auditedDep = depSubtotal.value.audited
    const auditedImpair = impairSubtotal.value.audited

    if (options?.onWritebackTB) {
      await options.onWritebackTB(auditedCost, auditedDep, auditedImpair)
    }

    if (options?.onPublishEvent) {
      options.onPublishEvent('substantive:adjudicated', {
        wp_code: 'H1',
        account_codes: ['1601', '1602', '1603'],
        cost_audited: auditedCost,
        dep_audited: auditedDep,
        impair_audited: auditedImpair,
        net_value: netValueAudited.value,
        net_value_begin: netValueBegin.value,
      })
    }
  }

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-cost-rows`, costRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-dep-rows`, depRows.value.filter((r) => !r.isSubtotal))
    save(`${ITEM_PREFIX}-impair-rows`, impairRows.value.filter((r) => !r.isSubtotal))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  function saveQualitativeNotes(patch?: Partial<QualitativeNotes>): void {
    if (patch) {
      qualitativeNotes.value = { ...qualitativeNotes.value, ...patch }
    }
    options?.onSave?.(`${ITEM_PREFIX}-qualitative-notes`, { ...qualitativeNotes.value })
  }

  watch(allResponses, () => _loadRows(), { immediate: true })

  watch(
    () => options?.categoryPrefill?.value,
    (payload) => {
      if (prefillApplied.value || !payload?.categories?.length) return
      const allZero = [...costRows.value, ...depRows.value, ...impairRows.value].every(
        (r) =>
          !r.beginBalance && !r.debit && !r.credit && !r.unadjusted && !r.aje && !r.rje,
      )
      if (allZero) applyCategoryPrefill(false)
    },
    { immediate: true },
  )

  return {
    costRows,
    depRows,
    impairRows,
    auditNote,
    auditConclusion,
    qualitativeNotes,
    changeExplanations,
    costSubtotal,
    depSubtotal,
    impairSubtotal,
    netValueAudited,
    netValueBegin,
    netRows,
    significantNetChanges,
    reconciliationResults,
    differenceRows,
    crossValidation,
    adjustmentCheck,
    updateCell,
    syncAdjustmentsFromH3,
    applyCategoryPrefill,
    setChangeExplanation,
    publishAdjudicated,
    saveNote,
    saveConclusion,
    saveQualitativeNotes,
    CHANGE_RATE_THRESHOLD,
    CHANGE_EXPL_KEY,
  }
}

export default useH1Adjudication
