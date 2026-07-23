/**
 * useI6Adjudication — I6-1 研发费用审定表 composable（损益类！27行×11列，73公式）
 *
 * 列结构（11列 A-K）：
 *   A: 类别（from 明细表I6-2）
 *   B: 上期未审 | C: 上期AJE | D: 上期RJE | E: 上期审定（=B+C+D）
 *   F: 本期未审 | G: 本期AJE | H: 本期RJE | I: 本期审定（=F+G+H）
 *   J: 变动额（=I-E，本期审定-上期审定）
 *   K: 变动率（IF(E=0 AND J=0, 0, IF(E=0 AND J>0, 1, J/E))）
 *
 * 核心特征：
 *   - **损益类科目6602！取发生额非余额（与H10同款）**
 *   - 审定 = 未审 + AJE + RJE（上期&本期各一组）
 *   - 变动额 = 本期审定 - 上期审定
 *   - 变动率 = IF(E=0 AND J=0, 0, IF(E=0 AND J>0, 1, J/E))
 *   - 合计行 = 各列SUM
 *   - I2联动面板：费用化(I6) + 资本化(I2) = 研发总额（VR-I6-01）
 *   - TB回写：发生额（科目6602）
 *
 * Spec: .kiro/specs/i6-research-development-expense/
 * Task: 3.3
 * Requirements: 2.1-2.8, 4.4, 4.7
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import {
  buildI6AdjudicationAuditNoteDraft,
  pickI6HighChangeRateRows,
} from './i6AdjudicationNoteDraft'
import { api } from '@/services/apiProxy'
import {
  parseNum,
  calcAuditedAmount,
  calcSubtotal,
  calcMonthlyTotal,
  calcResearchTotal,
  validateVRI601,
} from './useI6FormulaEngine'
import { applyAjeFromI63 } from './i6AdjustmentModel'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（27行，每行对应一个研发费用类别） */
export interface I6AdjudicationRow {
  rowId: string
  /** A列：类别名称 */
  类别: string
  /** B列：上期未审 */
  上期未审: number
  /** C列：上期AJE */
  上期AJE: number
  /** D列：上期RJE */
  上期RJE: number
  /** E列：上期审定（公式：B+C+D） */
  上期审定: number
  /** F列：本期未审 */
  本期未审: number
  /** G列：本期AJE */
  本期AJE: number
  /** H列：本期RJE */
  本期RJE: number
  /** I列：本期审定（公式：F+G+H） */
  本期审定: number
  /** J列：变动额（公式：I-E） */
  变动额: number
  /** K列：变动率（公式：见calcI6ChangeRate） */
  变动率: number | null
  /** 备注 */
  备注: string
  /** 变动率超阈值高亮 */
  changeRateHighlight: boolean
  /** 可编辑标记 */
  isEditable?: boolean
  /** 合计行标记 */
  isTotal?: boolean
}

/** I2联动面板数据 */
export interface I6LinkagePanel {
  /** 费用化金额（来自审定表合计-本期审定） */
  expenseI6: number
  /** 资本化金额（来自I2 EventBus） */
  capitalizedI2: number
  /** 研发总额（expenseI6 + capitalizedI2） */
  researchTotal: number
  /** VR-I6-01校验结果 */
  vrI601Status: {
    isValid: boolean
    difference: number
  }
  /** I2数据是否可用 */
  i2DataReady: boolean
}

/** ChecklistItem 类型 */
export interface I6ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 跨sheet接口类型（useI6CrossSheet的返回值子集） */
export interface I6CrossSheetData {
  detailMonthlyTotals: ComputedRef<number[]>
  i2LinkageStatus: ComputedRef<{ capitalized: number; total: number; isBalanced: boolean }>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ROWS = 'I6-1-rows'
const ITEM_PREFIX = 'I6-adj'
const ACCOUNT_CODE_6602 = '6602'
/** 变动率超阈值(±30%)高亮 */
const CHANGE_RATE_THRESHOLD = 30

/** 默认研发费用类别（27行中的典型项目） */
const DEFAULT_CATEGORIES = [
  '人员人工费用',
  '直接投入费用',
  '折旧费用与长期待摊费用',
  '无形资产摊销费用',
  '设计费用',
  '装备调试费用与试验费用',
  '委托外部研究开发费用',
  '其他费用',
]

// ─── Helper: I6变动率计算 ────────────────────────────────────────────────────

/**
 * I6审定表变动率计算（与通用calcChangeRate不同的特殊规则）
 * K列 = IF(E=0 AND J=0, 0, IF(E=0 AND J>0, 1, J/E))
 * - 上期审定=0且变动额=0 → 0
 * - 上期审定=0且变动额>0 → 1 (100%)
 * - 其他 → 变动额/上期审定
 */
function calcI6ChangeRate(priorAudited: number, changeAmount: number): number | null {
  const e = parseNum(priorAudited)
  const j = parseNum(changeAmount)
  if (e === 0 && j === 0) return 0
  if (e === 0 && j > 0) return 1
  if (e === 0) return null
  return j / e
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6Adjudication(options: {
  allResponses: Ref<Map<string, any>>
  tbData: Ref<{ unadjusted6602: number; audited6602: number }>
  crossSheet?: I6CrossSheetData
  wpId?: Ref<string>
  projectId?: Ref<string>
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
  onSave?: (itemId: string, value: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 审定表数据行 */
  const rows = ref<I6AdjudicationRow[]>([])
  /** 审计说明 */
  const auditNote = ref('')
  /** 审计结论 */
  const auditConclusion = ref('')
  /** I2资本化金额（来自EventBus） */
  const capitalizedI2 = ref(0)
  /** I2数据是否已收到 */
  const i2DataReady = ref(false)
  /** 研发总额预期值（手工/外部输入） */
  const expectedResearchTotal = ref(0)
  /** 脏标记 */
  const isChanged = ref(false)

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const data = _getJson(ITEM_ROWS) ?? _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = _buildDefaultRows()
    }
    auditNote.value = _getString('I6-1-note') || _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString('I6-1-conclusion') || _getString(`${ITEM_PREFIX}-audit-conclusion`)
    // I2资本化
    const i2Val = _getJson(`${ITEM_PREFIX}-capitalized-i2`)
    if (i2Val != null) {
      capitalizedI2.value = parseNum(i2Val)
      i2DataReady.value = true
    }
    // 研发总额预期
    const totalVal = _getJson(`${ITEM_PREFIX}-expected-total`)
    if (totalVal != null) expectedResearchTotal.value = parseNum(totalVal)
  }

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return raw }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): I6AdjudicationRow {
    const 上期未审 = parseNum(raw.上期未审 ?? raw.priorUnadj)
    const 上期AJE = parseNum(raw.上期AJE)
    const 上期RJE = parseNum(raw.上期RJE)
    const 上期审定 = calcAuditedAmount(上期未审, 上期AJE, 上期RJE)
    const 本期未审 = parseNum(raw.本期未审)
    const 本期AJE = parseNum(raw.本期AJE)
    const 本期RJE = parseNum(raw.本期RJE)
    const 本期审定 = calcAuditedAmount(本期未审, 本期AJE, 本期RJE)
    const 变动额 = 本期审定 - 上期审定
    const 变动率 = calcI6ChangeRate(上期审定, 变动额)

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      类别: raw.类别 ?? raw.项目 ?? raw.category ?? '',
      上期未审,
      上期AJE,
      上期RJE,
      上期审定,
      本期未审,
      本期AJE,
      本期RJE,
      本期审定,
      变动额,
      变动率,
      备注: raw.备注 ?? '',
      changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      isEditable: raw.isEditable ?? true,
      isTotal: raw.isTotal ?? false,
    }
  }

  function _buildDefaultRows(): I6AdjudicationRow[] {
    return DEFAULT_CATEGORIES.map((cat) => ({
      rowId: `row-${cat}`,
      类别: cat,
      上期未审: 0,
      上期AJE: 0,
      上期RJE: 0,
      上期审定: 0,
      本期未审: 0,
      本期AJE: 0,
      本期RJE: 0,
      本期审定: 0,
      变动额: 0,
      变动率: null,
      备注: '',
      changeRateHighlight: false,
      isEditable: true,
      isTotal: false,
    }))
  }

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<I6AdjudicationRow[]> = computed(() => {
    return rows.value.map((row) => {
      const 上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
      const 本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
      const 变动额 = 本期审定 - 上期审定
      const 变动率 = calcI6ChangeRate(上期审定, 变动额)
      return {
        ...row,
        上期审定,
        本期审定,
        变动额,
        变动率,
        changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      }
    })
  })

  // ─── Computed: 合计行（totalRow）─────────────────────────────────────────

  const totalRow: ComputedRef<I6AdjudicationRow> = computed(() => {
    const detail = computedRows.value.filter((r) => !r.isTotal)
    const 上期未审 = calcSubtotal(detail.map((r) => r.上期未审))
    const 上期AJE = calcSubtotal(detail.map((r) => r.上期AJE))
    const 上期RJE = calcSubtotal(detail.map((r) => r.上期RJE))
    const 上期审定 = calcAuditedAmount(上期未审, 上期AJE, 上期RJE)
    const 本期未审 = calcSubtotal(detail.map((r) => r.本期未审))
    const 本期AJE = calcSubtotal(detail.map((r) => r.本期AJE))
    const 本期RJE = calcSubtotal(detail.map((r) => r.本期RJE))
    const 本期审定 = calcAuditedAmount(本期未审, 本期AJE, 本期RJE)
    const 变动额 = 本期审定 - 上期审定
    const 变动率 = calcI6ChangeRate(上期审定, 变动额)

    return {
      rowId: 'row-total',
      类别: '合  计',
      上期未审,
      上期AJE,
      上期RJE,
      上期审定,
      本期未审,
      本期AJE,
      本期RJE,
      本期审定,
      变动额,
      变动率,
      备注: '',
      changeRateHighlight: 变动率 !== null && Math.abs(变动率 * 100) > CHANGE_RATE_THRESHOLD,
      isEditable: false,
      isTotal: true,
    }
  })

  // ─── Computed: I2联动面板 ──────────────────────────────────────────────────

  const linkagePanel: ComputedRef<I6LinkagePanel> = computed(() => {
    const expenseI6 = totalRow.value.本期审定
    const cap = capitalizedI2.value
    const total = calcResearchTotal(expenseI6, cap)
    const expected = expectedResearchTotal.value || total
    const vr = validateVRI601(expenseI6, cap, expected)

    return {
      expenseI6,
      capitalizedI2: cap,
      researchTotal: total,
      vrI601Status: vr,
      i2DataReady: i2DataReady.value,
    }
  })

  // ─── Computed: TB差异 ─────────────────────────────────────────────────────

  /** TB未审发生额（科目6602） */
  const tbUnadjusted: ComputedRef<number> = computed(() => {
    return options.tbData.value.unadjusted6602
  })

  /** TB差异 = 审定合计(本期) - TB未审 */
  const tbDifference: ComputedRef<number> = computed(() => {
    return totalRow.value.本期审定 - tbUnadjusted.value
  })

  const highChangeRateRows = computed(() =>
    pickI6HighChangeRateRows(computedRows.value.filter((r) => r.isEditable !== false && !r.isTotal)),
  )

  const needsAuditNoteDraft = computed(() => highChangeRateRows.value.length > 0)

  function buildAuditNoteDraft(): string {
    return buildI6AdjudicationAuditNoteDraft(
      computedRows.value.filter((r) => !r.isTotal),
      { existingNote: auditNote.value },
    )
  }

  function applyAuditNoteDraft(): boolean {
    const draft = buildAuditNoteDraft()
    if (!draft) return false
    saveNote(draft)
    return true
  }

  /** 与明细表月度合计的交叉校验 */
  const detailCrossValidation: ComputedRef<string | null> = computed(() => {
    if (!options.crossSheet) return null
    const monthlyTotals = options.crossSheet.detailMonthlyTotals.value
    if (!monthlyTotals || monthlyTotals.length === 0) return null
    const detailTotal = calcSubtotal(monthlyTotals)
    const adjTotal = totalRow.value.本期审定
    if (Math.abs(detailTotal - adjTotal) > 0.01) {
      return `审定表合计 ${adjTotal.toFixed(2)} 与明细表月度合计 ${detailTotal.toFixed(2)} 不一致`
    }
    return null
  })

  // ─── Actions: 更新单元格 ──────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列（上期审定/本期审定/变动额/变动率）
   */
  function updateCell(
    rowId: string,
    field: keyof I6AdjudicationRow,
    value: number | string,
  ): void {
    if (options.isReadonly?.value) return
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || !row.isEditable) return

    ;(row as any)[field] = value

    // 自动重算公式列
    row.上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
    row.本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
    row.变动额 = row.本期审定 - row.上期审定
    row.变动率 = calcI6ChangeRate(row.上期审定, row.变动额)
    row.changeRateHighlight = row.变动率 !== null && Math.abs(row.变动率 * 100) > CHANGE_RATE_THRESHOLD

    isChanged.value = true
    _persist()
  }

  function _readDetailRows(): any[] {
    const raw = _getJson('I6-2-detail-rows')
    return Array.isArray(raw) ? raw : []
  }

  /** 从 I6-2 明细表按类别聚合写入审定行（对齐 Excel 引用明细表） */
  function syncFromDetail(force = false): void {
    if (options.isReadonly?.value) return
    const detailRows = _readDetailRows()
    if (!detailRows.length) {
      ElMessage.warning('I6-2 明细表暂无数据，请先编制明细')
      return
    }

    const categoryMap = new Map<string, {
      上期未审: number; 上期AJE: number; 上期RJE: number
      本期未审: number; 本期AJE: number; 本期RJE: number
    }>()

    for (const raw of detailRows) {
      const cat = String(raw?.category ?? raw?.项目 ?? '').trim()
      if (!cat || cat === '合计') continue

      const months = Array.isArray(raw?.months) ? raw.months : []
      const unadj = months.length ? calcMonthlyTotal(months) : parseNum(raw?.unadjTotal)
      const existing = categoryMap.get(cat) || {
        上期未审: 0, 上期AJE: 0, 上期RJE: 0,
        本期未审: 0, 本期AJE: 0, 本期RJE: 0,
      }
      existing.上期未审 += parseNum(raw?.priorUnadj)
      existing.上期AJE += parseNum(raw?.priorAje)
      existing.上期RJE += parseNum(raw?.priorRje)
      existing.本期未审 += unadj
      existing.本期AJE += parseNum(raw?.aje)
      existing.本期RJE += parseNum(raw?.rje)
      categoryMap.set(cat, existing)
    }

    const aggregated = Array.from(categoryMap.entries()).map(([类别, vals]) => ({
      rowId: `row-${类别}`,
      类别,
      ...vals,
      上期审定: 0, 本期审定: 0, 变动额: 0, 变动率: null as number | null,
      备注: '', changeRateHighlight: false, isEditable: true, isTotal: false,
    }))

    if (force || !rows.value.some((r) => r.isEditable && (r.本期未审 || r.上期未审))) {
      rows.value = aggregated.map(_normalizeRow)
    } else {
      for (const agg of aggregated) {
        const row = rows.value.find((r) => r.类别 === agg.类别)
        if (row) {
          Object.assign(row, {
            上期未审: agg.上期未审, 上期AJE: agg.上期AJE, 上期RJE: agg.上期RJE,
            本期未审: agg.本期未审, 本期AJE: agg.本期AJE, 本期RJE: agg.本期RJE,
          })
          _recalcRow(row)
        } else {
          rows.value.push(_normalizeRow(agg))
        }
      }
    }

    isChanged.value = true
    _persist()
    ElMessage.success(`已从 I6-2 同步 ${categoryMap.size} 个类别`)
  }

  // ─── Actions: TB取数接入 ──────────────────────────────────────────────────

  /**
   * 接收TB未审发生额数据，写入行的 本期未审 字段
   * 如果只有1行，直接写入该行；多行按上期审定比例分配
   */
  function applyTbData(tbUnadjustedTotal: number): void {
    if (options.isReadonly?.value) return
    if (rows.value.length === 1) {
      rows.value[0].本期未审 = tbUnadjustedTotal
      _recalcRow(rows.value[0])
    } else if (rows.value.length > 1) {
      const totalPrior = calcSubtotal(rows.value.map((r) => r.上期审定))
      if (totalPrior > 0) {
        for (const row of rows.value) {
          const ratio = row.上期审定 / totalPrior
          row.本期未审 = Math.round(ratio * tbUnadjustedTotal * 100) / 100
          _recalcRow(row)
        }
      } else {
        // 上期全为0时平均分配
        const avg = tbUnadjustedTotal / rows.value.length
        for (const row of rows.value) {
          row.本期未审 = Math.round(avg * 100) / 100
          _recalcRow(row)
        }
      }
    }
    isChanged.value = true
    _persist()
  }

  /**
   * 接收 AJE/RJE 调整（来自 I6-3 调整分录表）
   * 按类别名称匹配写入对应行
   */
  function applyAdjustments(adjustments: { 类别: string; AJE: number; RJE: number }[]): void {
    if (options.isReadonly?.value) return
    for (const adj of adjustments) {
      const row = rows.value.find((r) => r.类别 === adj.类别)
      if (row) {
        row.本期AJE = adj.AJE
        row.本期RJE = adj.RJE
        _recalcRow(row)
      }
    }
    isChanged.value = true
    _persist()
  }

  /** 重算行公式列 */
  function _recalcRow(row: I6AdjudicationRow): void {
    row.上期审定 = calcAuditedAmount(row.上期未审, row.上期AJE, row.上期RJE)
    row.本期审定 = calcAuditedAmount(row.本期未审, row.本期AJE, row.本期RJE)
    row.变动额 = row.本期审定 - row.上期审定
    row.变动率 = calcI6ChangeRate(row.上期审定, row.变动额)
    row.changeRateHighlight = row.变动率 !== null && Math.abs(row.变动率 * 100) > CHANGE_RATE_THRESHOLD
  }

  // ─── Actions: I2 EventBus 联动 ────────────────────────────────────────────

  /**
   * 接收I2资本化金额更新（EventBus: development:capitalized-updated）
   */
  function onI2CapitalizedUpdate(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (detail && typeof detail.capitalizedAmount === 'number') {
      capitalizedI2.value = detail.capitalizedAmount
      i2DataReady.value = true
      _persistI2Data()
    }
  }

  function _persistI2Data(): void {
    options.onSave?.(`${ITEM_PREFIX}-capitalized-i2`, capitalizedI2.value)
  }

  // ─── Actions: TB回写（writebackTB **发生额** 6602）────────────────────────

  /**
   * 回写审定发生额到 trial_balance（科目6602）
   * 1. 持久化行数据到 checklist_responses
   * 2. writebackTrialBalance（科目6602，**发生额**！）
   * 3. 发布 'substantive:adjudicated' EventBus事件
   * 4. 发布 'research:expense-updated' EventBus事件（I6→I2联动）
   */
  async function writeback(): Promise<void> {
    _persist()

    const auditedTotal = totalRow.value.本期审定

    // 持久化审定合计（独立item_id，供render策略回读seed + 跨session持久化）
    options.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // TB回写（科目6602，**发生额！**）
    if (options.projectId?.value) {
      try {
        await api.put(`/api/projects/${options.projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_6602,
          audited_amount: auditedTotal,
          is_occurrence: true, // 标记为发生额回写（非余额）
        })
        ElMessage.success('审定发生额已回写试算表(6602)')
      } catch {
        ElMessage.warning('审定发生额回写试算表失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus 事件
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I6',
        accountCodes: [ACCOUNT_CODE_6602],
        auditedTotal,
        isOccurrence: true, // 损益类标记
      },
    }))

    // 发布 'research:expense-updated' EventBus 事件（I6→I2联动）
    window.dispatchEvent(new CustomEvent('research:expense-updated', {
      detail: {
        expenseAmount: auditedTotal,
        source: 'I6-adjudication',
      },
    }))

    isChanged.value = false
  }

  // ─── Actions: 全量重算 ────────────────────────────────────────────────────

  /**
   * 全量重算所有行的公式列（外部触发用，如明细表数据回写后）
   */
  function computeAll(): void {
    for (const row of rows.value) {
      _recalcRow(row)
    }
    _persist()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options.onSave
    if (!save) return
    save(ITEM_ROWS, rows.value.filter((r) => !r.isTotal))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.('I6-1-note', note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.('I6-1-conclusion', conclusion)
  }

  function setExpectedTotal(total: number): void {
    expectedResearchTotal.value = total
    options.onSave?.(`${ITEM_PREFIX}-expected-total`, total)
  }

  // ─── Lifecycle: EventBus subscribe/unsubscribe ─────────────────────────────

  onMounted(() => {
    // 订阅 I2 资本化金额更新
    window.addEventListener('development:capitalized-updated', onI2CapitalizedUpdate)
    // 订阅 I6-3 调整分录回写
    window.addEventListener('i6:adjustment-writeback', onAdjustmentWriteback)
  })

  onBeforeUnmount(() => {
    window.removeEventListener('development:capitalized-updated', onI2CapitalizedUpdate)
    window.removeEventListener('i6:adjustment-writeback', onAdjustmentWriteback)
  })

  /** 处理I6-3调整分录回写事件 */
  function onAdjustmentWriteback(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail) return
    if (Array.isArray(detail.adjustments)) {
      applyAdjustments(detail.adjustments)
      return
    }
    const entries = detail.entries ?? detail.rows
    if (Array.isArray(entries) && entries.length) {
      syncFromI63(entries)
    }
  }

  /** 从 I6-3 分录汇总 6602 净额并写入审定行 AJE/RJE */
  function syncFromI63(adjRows?: any[]): void {
    if (options.isReadonly?.value) return
    const source = adjRows?.length
      ? adjRows
      : (() => {
          const raw = _getJson('I6-3-rows')
          return Array.isArray(raw) ? raw : []
        })()
    if (!source.length) {
      ElMessage.info('I6-3 无 6602 相关调整可同步')
      return
    }
    const dataRows = rows.value.filter((r) => r.类别 !== '合  计')
    const result = applyAjeFromI63(dataRows, source)
    for (const updated of result.rows) {
      const row = rows.value.find((r) => r.类别 === updated.类别)
      if (row) {
        row.本期AJE = updated.本期AJE
        row.本期RJE = updated.本期RJE
        _recalcRow(row)
      }
    }
    isChanged.value = true
    _persist()
    if (!result.applied && Math.abs(result.totalAje) < 0.005 && Math.abs(result.totalRje) < 0.005) {
      ElMessage.info('I6-3 无 6602 相关调整可同步')
      return
    }
    ElMessage.success(
      result.approx
        ? `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}（含按未审占比近似分摊，请复核）`
        : `已同步 AJE ${result.totalAje} / RJE ${result.totalRje}`,
    )
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(options.allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows: computedRows,
    auditNote,
    auditConclusion,
    isChanged,
    // Computed — 合计行
    totalRow,
    // Computed — I2联动面板
    linkagePanel,
    // Computed — TB
    tbUnadjusted,
    tbDifference,
    // Computed — 交叉校验
    detailCrossValidation,
    highChangeRateRows,
    needsAuditNoteDraft,
    buildAuditNoteDraft,
    applyAuditNoteDraft,
    // Actions — 数据接入
    updateCell,
    applyTbData,
    applyAdjustments,
    syncFromI63,
    syncFromDetail,
    // Actions — 全量重算
    computeAll,
    // Actions — TB回写+EventBus
    writeback,
    // Actions — 保存
    saveNote,
    saveConclusion,
    setExpectedTotal,
  }
}

export default useI6Adjudication
