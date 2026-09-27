/**
 * useG10Detail — G10-2 明细表（对齐 Excel：类别/项目 + 期初·变动·期末三段 roll-forward）
 *
 * 编制逻辑：
 * 1. 期初/期末均分解为 (一)初始确认 + (二)累计公允价值变动 = (三)公允价值；审定 = 公允价值 + 调整
 * 2. 本期变动：初始确认、公允价值变动、计入财务费用利息、减少（清偿/终止）
 * 3. 期末余额 roll-forward = 期初审定 + 变动 − 减少；与 (一)+(二) 分解勾稽
 * 4. 可按负债类型汇总回写 G10-1 各分项未审数
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  G10_LIABILITY_TYPE_OPTIONS,
  G10_LIABILITY_CATEGORY_OPTIONS,
  G10_FV_LEVEL_OPTIONS,
  G10_VALUATION_METHOD_OPTIONS,
  G10_CONFIRMATION_OPTIONS,
} from './g10Constants'
import {
  pushG10DetailToAdjudication,
  calcBookSectionTotal,
  G10_ADJ_ROWS_KEY,
  fetchG10AuxLiabilitySeeds,
  seedG10DetailRowFromAux,
} from './g10CrossHelpers'
import {
  isG10DerivativeDetailRow,
  parseG10DerivativeDetailLinks,
  G10_DERIVATIVE_DETAIL_LINKS_KEY,
} from './g10DerivativeCross'
import {
  buildG10DetailProcedureSummary,
  G10A_DETAIL_MARK_KEY,
  G10A_DETAIL_PROGRAM_NOS,
  markG10AProcedureSteps,
} from './g10FvCrossHelpers'
import { parseG10AdjStore } from './g10AdjStorage'
import { offerG10DisclosurePull } from './g10DisclosureSync'
import { pullG10DetailFromAdjudicationResponses } from './g10DetailFromAdjudication'
import { matchG10LiabilityKey } from './g10AccountMatch'
import { useWorkpaperAuditYear } from './workpaperAuditYear'
import {
  parseNum,
  calcAdjustedAmount,
  calcSubtotal,
  calcBookFromParts,
  calcG10DetailClosingBalance,
} from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import { G10_ITEM_IDS } from './g10StorageContract'

/**
 * G10-2 明细行 —— 字段顺序与模板列序 A..S **逐列对应**。
 *
 * spec `g-cycle-single-region-detail-lanes` C-7；列模型依据
 * `evidence/task8-c6-remaining-eight-template-logic.md` §2。
 *
 * ═══ 模板编制思路（负债侧「三分量 × 三阶段」）═══
 *
 * 与 G9（资产侧四阶段）的三处结构差异，照抄 G9 会错：
 * 1. **调整与审定都是单列**（F/G 与 N/O），不拆成本与公允价值变动两分量 ——
 *    负债侧的账项调整不区分分量。
 * 2. **`L = D + I + J`**（期末累计公允价值变动含利息 J）。交易性金融负债的利息
 *    计入财务费用**同时增加负债账面价值** ⇒ 利息必须进累计公允价值变动。
 *    改造前前端算的是 `D + I`（漏 J），与模板不符。
 * 3. **本期变动是净额列**（表头逐字「增加"+"/减少"—"」）⇒ **没有**「本期减少」列。
 *    改造前的 `currentDecrease` 是自研列，且被喂进一个走**审定线**的
 *    `closingBalance`（`=期初审定+变动−减少`）—— 模板 `K = C + H` 走**未审线**。
 *
 * `【公式】` 标记的字段由 `enrichG10DetailRow` 按模板公式重算，UI 只读。
 */
export interface G10DetailRow {
  /** 行身份（受管 `row_identity_key`）。生成器带随机后缀，见 `genId`。 */
  rowId: string
  /** 显示序号（不受管、不是身份） */
  seq: number

  /** A 类别（指定类 / 交易类） */
  liabilityCategory: string
  /** B 项目【按明细项目列示，如债券名称】 */
  liabilityName: string

  /** C 期初余额 / 初始确认金额 */
  openingInitialAmount: number
  /** D 期初余额 / 累计公允价值变动 */
  openingFvAccum: number
  /** E 期初余额 / 公允价值　**【公式】** `=C+D` */
  openingFairValue: number
  /** F 期初调整数 */
  openingAdjustment: number
  /** G 期初审定数　**【公式】** `=E+F` */
  openingAdjusted: number

  /** H 本期变动（增加"+"/减少"—"）/ 初始确认金额 —— **净额列** */
  movementInitialAmount: number
  /** I 本期变动 / 本期公允价值变动 */
  movementFvChange: number
  /** J 本期变动 / 计入财务费用的利息 */
  interestExpense: number

  /** K 期末余额 / 初始确认金额　**【公式】** `=C+H`（未审线） */
  closingInitialAmount: number
  /** L 期末余额 / 累计公允价值变动　**【公式】** `=D+I+J`（🔴 含利息） */
  closingFvAccum: number
  /** M 期末余额 / 公允价值　**【公式】** `=K+L` */
  closingFairValue: number
  /** N 调整数 */
  closingAdjustment: number
  /** O 审定数　**【公式】** `=M+N` */
  closingAdjusted: number

  /** P 到期日 */
  maturityDate: string
  /** Q 票面利率 */
  couponRate: string
  /** R 期末应付利息 */
  accruedInterest: number
  /** S 发行文件索引 */
  issuanceDocIndex: string
}

/**
 * 改造前存在、**已从受管行模型移除**的字段（C-7）。
 *
 * 逐条给出归属而不是笼统「模板没有」—— 指不出归属的才是真冗余。
 */
export const DROPPED_LEGACY_G10_FIELDS: readonly { field: string; reason: string }[] = [
  { field: 'initialAmount', reason: 'legacy 单值残留，与模板 C/K 重复' },
  { field: 'openingBalance', reason: 'legacy 单值残留，与模板 E 重复' },
  { field: 'currentIncrease', reason: 'legacy 单值残留，与模板 H 重复' },
  { field: 'closingBalance', reason: 'legacy 走审定线的旧口径，与模板 M（=K+L，未审线）重复且口径错' },
  { field: 'currentDecrease', reason: '模板 H 是净额列（增加"+"/减少"—"），拆增减会与 H 双源' },
  { field: 'profitLossAmount', reason: 'legacy 别名，与模板 I 重复' },
  { field: 'fairValueLevel', reason: '权威源是 公允价值测试表G10-5 / 第三层次公允价值计量的调节表G10-6' },
  { field: 'valuationMethod', reason: '权威源同上（G10-5）' },
  { field: 'isDerivative', reason: '权威源是 衍生金融工具核查表G10-8' },
  { field: 'hostContractDesc', reason: '权威源同上（G10-8）' },
  { field: 'embeddedDerivativeJudgment', reason: '权威源同上（G10-8）' },
  { field: 'liabilityType', reason: '模板无此列；类别走 A 列，细分走 B 列文本' },
  { field: 'counterparty', reason: '模板无此列，也无「自行添加」授权' },
  { field: 'contractDate', reason: '模板无此列（到期日走 P 列）' },
  { field: 'confirmationStatus', reason: 'G10 是**负债**不对外发函（G9 的 AB「发函情况」是资产侧函证）' },
  { field: 'remark', reason: '模板无此列；索引走 S 列' },
] as const

/**
 * `enrichG10DetailRow` 的入参：受管列的 `Partial` + **显式列出**的四个 legacy 单值键。
 *
 * 🔴 不用 `& Record<string, unknown>` 兜底：那样任何拼错的字段名都能通过编译
 * （本轮实测 `Record<string, unknown>` 让 `G10DetailRow` 自身都不再可赋值给它，
 * 反而把正常调用点判红）。只放真实存在过的四个 legacy 键，读完即弃、不回写。
 */
export type G10DetailRowInput = Partial<G10DetailRow> & {
  rowId: string
  /** legacy：与模板 C/K 重复 */
  initialAmount?: number | string | null
  /** legacy：与模板 E 重复 */
  openingBalance?: number | string | null
  /** legacy：与模板 H 重复 */
  currentIncrease?: number | string | null
  /** legacy：与模板 I 重复 */
  profitLossAmount?: number | string | null
}

export interface G10DetailRowIssue {
  rowId: string
  liabilityName: string
  field: string
  message: string
  variance?: number
}

const ITEM_ID_ROWS = G10_ITEM_IDS.G10_DETAIL_ROWS
const DIFF_TOLERANCE = 0.01

function genId(): string {
  return `g10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`
}

/**
 * 按模板 6 条公式重算派生列。
 *
 * | 列 | 公式 | 说明 |
 * |---|---|---|
 * | E | `=C+D` | 期初公允价值 |
 * | G | `=E+F` | 期初审定数（单列调整） |
 * | K | `=C+H` | 期末初始确认金额（🔴 **未审线**，不是从 G 推） |
 * | L | `=D+I+J` | 期末累计公允价值变动（🔴 **含利息 J**） |
 * | M | `=K+L` | 期末公允价值 |
 * | O | `=M+N` | 期末审定数（单列调整） |
 *
 * 🔴 兼容读：旧载荷可能只有 `initialAmount`/`openingBalance`/`currentIncrease`/
 * `profitLossAmount` 这些 legacy 单值键。G10 真库是 **2 B 空数组**（无真实行数据），
 * 所以这里只做**读取兼容**，不做迁移统计与回写 —— 那套只有 G9（605 B 真载荷）需要。
 */
export function enrichG10DetailRow(raw: G10DetailRowInput, seq: number): G10DetailRow {
  const openingInitialAmount = parseNum(raw.openingInitialAmount ?? raw.initialAmount)
  const openingBalanceLegacy = parseNum(raw.openingBalance)
  let openingFvAccum: number
  if (raw.openingFvAccum != null && String(raw.openingFvAccum).trim() !== '') {
    openingFvAccum = parseNum(raw.openingFvAccum)
  } else if (raw.openingBalance != null && String(raw.openingBalance).trim() !== '') {
    openingFvAccum = openingBalanceLegacy - openingInitialAmount
  } else {
    openingFvAccum = 0
  }
  // E = C + D
  const openingFairValue = calcBookFromParts(openingInitialAmount, openingFvAccum)
  const openingAdjustment = parseNum(raw.openingAdjustment)
  // G = E + F
  const openingAdjusted = calcAdjustedAmount(openingFairValue, openingAdjustment)

  const movementInitialAmount = parseNum(raw.movementInitialAmount ?? raw.currentIncrease)
  const movementFvChange = parseNum(raw.movementFvChange ?? raw.profitLossAmount)
  const interestExpense = parseNum(raw.interestExpense)

  // K = C + H（未审线）
  const closingInitialAmount = openingInitialAmount + movementInitialAmount
  // L = D + I + J（🔴 含利息）
  const closingFvAccum = openingFvAccum + movementFvChange + interestExpense
  // M = K + L
  const closingFairValue = calcBookFromParts(closingInitialAmount, closingFvAccum)
  const closingAdjustment = parseNum(raw.closingAdjustment)
  // O = M + N
  const closingAdjusted = calcAdjustedAmount(closingFairValue, closingAdjustment)

  return {
    rowId: raw.rowId,
    seq,
    liabilityCategory: raw.liabilityCategory ?? G10_LIABILITY_CATEGORY_OPTIONS[0],
    liabilityName: raw.liabilityName ?? '',
    openingInitialAmount,
    openingFvAccum,
    openingFairValue,
    openingAdjustment,
    openingAdjusted,
    movementInitialAmount,
    movementFvChange,
    interestExpense,
    closingInitialAmount,
    closingFvAccum,
    closingFairValue,
    closingAdjustment,
    closingAdjusted,
    maturityDate: raw.maturityDate ?? '',
    couponRate: raw.couponRate ?? '',
    accruedInterest: parseNum(raw.accruedInterest),
    issuanceDocIndex: raw.issuanceDocIndex ?? '',
  }
}

export function scanG10DetailIntegrity(rows: G10DetailRow[]): G10DetailRowIssue[] {
  const issues: G10DetailRowIssue[] = []
  for (const r of rows) {
    const name = r.liabilityName?.trim() || `第${r.seq}行`
    if (!r.liabilityName?.trim() && Math.abs(r.closingAdjusted) > DIFF_TOLERANCE) {
      issues.push({ rowId: r.rowId, liabilityName: name, field: 'liabilityName', message: '有审定余额但项目名称为空' })
    }
    // 🔴 C-7 移除「Level3 须填估值方法」：公允价值层次与估值方法的权威源是
    //    公允价值测试表G10-5 / 第三层次调节表G10-6，G10-2 按模板重构后没有这两列。
    //    该校验已在 useG10L3Reconciliation（以 G10-5/G10-6 为主表）承担。
    const openDecompDiff = r.openingFairValue - calcBookFromParts(r.openingInitialAmount, r.openingFvAccum)
    if (Math.abs(openDecompDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'openingFairValue',
        message: '期初 (一)+(二) ≠ (三)公允价值',
        variance: openDecompDiff,
      })
    }
    const closeDecompDiff = r.closingFairValue - calcBookFromParts(r.closingInitialAmount, r.closingFvAccum)
    if (Math.abs(closeDecompDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'closingFairValue',
        message: '期末 (一)+(二) ≠ (三)公允价值',
        variance: closeDecompDiff,
      })
    }
    // 🔴 C-7 新增：未审线校验（K=C+H / L=D+I+J）。改造前这里校验的是走**审定线**的
    //    legacy `closingBalance`，那个口径本身就与模板不符 ⇒ 校验对象换成模板列。
    const unauditedCostDiff =
      r.closingInitialAmount - (r.openingInitialAmount + r.movementInitialAmount)
    if (Math.abs(unauditedCostDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'closingInitialAmount',
        message: '期末初始确认金额应等于「期初 + 本期变动」（未审线 K=C+H）',
        variance: unauditedCostDiff,
      })
    }
    const unauditedFvDiff =
      r.closingFvAccum - (r.openingFvAccum + r.movementFvChange + r.interestExpense)
    if (Math.abs(unauditedFvDiff) > DIFF_TOLERANCE) {
      issues.push({
        rowId: r.rowId,
        liabilityName: name,
        field: 'closingFvAccum',
        message: '期末累计公允价值变动应等于「期初 + 本期变动 + 计入财务费用的利息」（L=D+I+J）',
        variance: unauditedFvDiff,
      })
    }
  }
  return issues
}

function parseRows(json: string | null | undefined): G10DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) => enrichG10DetailRow({ ...r, rowId: r.rowId || r.id || genId() }, i + 1))
  } catch {
    return []
  }
}

export function useG10Detail(opts: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (id: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
  projectId?: Ref<string> | ComputedRef<string>
}) {
  const auditYearRef = useWorkpaperAuditYear()
  const rows = ref<G10DetailRow[]>([])
  /**
   * 表格分组视图。
   *
   * 🔴 C-7 从三段改四段：模板两级表头是四个一级分组（期初余额 C-E+F/G ·
   * 本期变动 H-J · 期末余额 K-M+N/O · 单列补充 A/B/P-S），原先把「期初 + 变动」挤在
   * 一个 tab 里，列宽被压到看不清分量归属。
   */
  const activeTab = ref<'basic' | 'opening' | 'movement' | 'closing'>('basic')
  const activeRowIndex = ref(0)
  const auxLoading = ref(false)
  const procedureMarking = ref(false)

  const FV_ROWS_KEY = 'G10-fv-test-rows'

  watch(
    () => opts.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseRows(json) },
    { immediate: true },
  )

  const currentRowKey = computed(() => rows.value[activeRowIndex.value]?.rowId ?? '')

  const totals = computed(() => ({
    openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
    movementInitialAmount: calcSubtotal(rows.value.map((r) => r.movementInitialAmount)),
    movementFvChange: calcSubtotal(rows.value.map((r) => r.movementFvChange)),
    interestExpense: calcSubtotal(rows.value.map((r) => r.interestExpense)),
    closingFairValue: calcSubtotal(rows.value.map((r) => r.closingFairValue)),
    closingAdjusted: calcSubtotal(rows.value.map((r) => r.closingAdjusted)),
  }))

  /**
   * 按 **A 列「类别」** 分组小计（改造前按已删除的 `liabilityType` 分组）。
   *
   * 模板只有 A 列一个分类维度（指定类 / 交易类），`liabilityType`（债券/理财/衍生…）
   * 是自研的第二维度，已随 C-7 一并移除。
   */
  const categorySubtotals = computed(() => {
    const result: Record<string, number> = {}
    for (const c of G10_LIABILITY_CATEGORY_OPTIONS) {
      result[c] = calcSubtotal(
        rows.value.filter((r) => r.liabilityCategory === c).map((r) => r.closingAdjusted),
      )
    }
    result['总计'] = totals.value.closingAdjusted
    return result
  })

  const adjudicationClosingTotal = computed(() => {
    const store = parseG10AdjStore(opts.allResponses.value.get(G10_ADJ_ROWS_KEY)?.remark)
    const total = calcBookSectionTotal(store)
    return total > 0.005 || Object.keys(store).length > 0 ? total : null
  })

  const adjCrossVariance = computed(() => {
    if (adjudicationClosingTotal.value == null || !rows.value.length) return null
    return totals.value.closingAdjusted - adjudicationClosingTotal.value
  })

  const hasAdjCrossMismatch = computed(() =>
    adjCrossVariance.value != null && Math.abs(adjCrossVariance.value) > DIFF_TOLERANCE,
  )

  const integrityIssues = computed(() => scanG10DetailIntegrity(rows.value))

  /**
   * 🔴 C-7 恒 0：「Level3 缺估值方法」的校验随层次列一起迁到 G10-5/G10-6
   * （`useG10L3Reconciliation`）。保留导出以免打断调用方。
   */
  const level3MissingMethodCount = computed(() => 0)

  /** G10-2 行 → G10-5 匹配（按项目名称） */
  const fvLinkByRowId = computed(() => {
    const map = new Map<string, { fvRowId: string; variance: number }>()
    let fvRows: any[] = []
    try {
      const json = opts.allResponses.value.get(FV_ROWS_KEY)?.remark
      if (json) fvRows = JSON.parse(json)
    } catch { /* silent */ }
    if (!Array.isArray(fvRows)) return map
    const fvByKey = new Map(
      fvRows
        .filter((r) => String(r.liabilityName ?? '').trim())
        .map((r) => [matchG10LiabilityKey(String(r.liabilityName)), r]),
    )
    for (const row of rows.value) {
      const fv = fvByKey.get(matchG10LiabilityKey(row.liabilityName))
      if (!fv) continue
      map.set(row.rowId, {
        fvRowId: String(fv.rowId ?? ''),
        variance: row.closingAdjusted - parseNum(fv.closingAuditedFV),
      })
    }
    return map
  })

  const unmatchedFvDetailCount = computed(() =>
    rows.value.filter((r) => r.liabilityName.trim() && !fvLinkByRowId.value.has(r.rowId)).length,
  )

  /** G10-2 衍生行 → G10-8 链接（链接清单或备注含 G10-8） */
  const derivativeLinkByRowId = computed(() => {
    const map = new Map<string, { linked: boolean; viaG108: boolean }>()
    const links = parseG10DerivativeDetailLinks(
      opts.allResponses.value.get(G10_DERIVATIVE_DETAIL_LINKS_KEY)?.remark,
    )
    const linkedIds = new Set(links.map((l) => l.detailRowId))
    for (const row of rows.value) {
      if (!isG10DerivativeDetailRow(row)) continue
      // 🔴 C-7：只认 G10-8 的链接清单。改造前还会回退读 G10-2 自己的
      //    `embeddedDerivativeJudgment` / `remark` 是否含 "G10-8" —— 那两列已随
      //    权威模板重构移除（权威源是 G10-8），回退读等于让 G10-2 自证已核查。
      const viaG108 = linkedIds.has(row.rowId)
      map.set(row.rowId, { linked: viaG108, viaG108 })
    }
    return map
  })

  const derivativeDetailCount = computed(() =>
    rows.value.filter((r) => isG10DerivativeDetailRow(r)).length,
  )

  const unmatchedDerivativeDetailCount = computed(() =>
    rows.value.filter((r) =>
      isG10DerivativeDetailRow(r) && !derivativeLinkByRowId.value.get(r.rowId)?.linked,
    ).length,
  )

  const procedureMarked = computed(() =>
    !!opts.allResponses.value.get(G10A_DETAIL_MARK_KEY)?.remark
    || opts.allResponses.value.get(G10A_DETAIL_MARK_KEY)?.conclusion === 'completed',
  )

  function persist(): void {
    opts.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(rows.value) })
    try {
      window.dispatchEvent(new CustomEvent('g10:detail-updated'))
    } catch { /* silent */ }
  }

  function updateRow(rowId: string, patch: Partial<G10DetailRow>): void {
    if (opts.isReadonly.value) return
    rows.value = rows.value.map((r, i) =>
      r.rowId === rowId ? enrichG10DetailRow({ ...r, ...patch, rowId }, i + 1) : r,
    )
    persist()
  }

  async function addRow(): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入负债项目名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：短期融资券',
      })
      if (!value?.trim()) return
      rows.value = [
        ...rows.value,
        enrichG10DetailRow({ rowId: genId(), liabilityName: value.trim() }, rows.value.length + 1),
      ]
      persist()
    } catch { /* cancelled */ }
  }

  async function removeRow(rowId: string): Promise<void> {
    if (opts.isReadonly.value) return
    try {
      await ElMessageBox.confirm('确认删除该明细行？', '删除确认', {
        type: 'warning',
        confirmButtonText: '删除',
        cancelButtonText: '取消',
      })
      rows.value = rows.value
        .filter((r) => r.rowId !== rowId)
        .map((r, i) => enrichG10DetailRow(r, i + 1))
      if (activeRowIndex.value >= rows.value.length) {
        activeRowIndex.value = Math.max(0, rows.value.length - 1)
      }
      persist()
    } catch { /* cancelled */ }
  }

  function reloadFromStore(): void {
    rows.value = parseRows(opts.allResponses.value.get(ITEM_ID_ROWS)?.remark)
  }

  function setActiveRowIndex(index: number): void {
    activeRowIndex.value = index
  }

  const totalRow = computed(() => totals.value)

  function pushTotalsToAdjudication(): void {
    if (opts.isReadonly.value || !rows.value.length) return
    void (async () => {
      const n = pushG10DetailToAdjudication(
        opts.allResponses.value,
        opts.debouncedSave,
        rows.value,
      )
      if (n <= 0) {
        ElMessage.warning('无可回写的明细合计')
        return
      }
      ElMessage.success(`已按分项回写 G10-1 ${n} 组（(一)(二)(三)）`)
      await offerG10DisclosurePull(
        opts.allResponses.value,
        opts.debouncedSave,
        auditYearRef.value,
        'G10-1 审定表已更新。是否同步更新附注披露（上市/国企）分项金额？',
      )
    })()
  }

  async function pullFromAdjudication(): Promise<void> {
    if (opts.isReadonly.value) return
    let mode: 'fill-empty' | 'overwrite' = 'fill-empty'
    const hasExisting = rows.value.some(
      (r) => r.liabilityName.trim() && Math.abs(r.closingFairValue) > 0.005,
    )
    if (hasExisting) {
      try {
        await ElMessageBox.confirm(
          '已有明细数据。选择「覆盖同类别」将按 G10-1 分项更新匹配行的期初/期末分解；「仅填空行」保留已有项目金额。',
          '从 G10-1 带入',
          {
            type: 'info',
            confirmButtonText: '覆盖同类别',
            cancelButtonText: '仅填空行',
            distinguishCancelAndClose: true,
          },
        )
        mode = 'overwrite'
      } catch (action) {
        if (action !== 'cancel') return
      }
    }

    const result = pullG10DetailFromAdjudicationResponses(
      opts.allResponses.value,
      rows.value,
      genId,
      mode,
    )
    if (result.filled <= 0) {
      ElMessage.warning('G10-1 无可带入的分项金额（请先编制审定表 (三) 账面余额分项）')
      return
    }
    rows.value = result.rows
    persist()
    ElMessage.success(
      `已从 G10-1 带入 ${result.filled} 个分项（新增 ${result.added} 行，更新 ${result.updated} 行）`,
    )
  }

  async function seedAuxAndPushToAdjudication(): Promise<void> {
    if (opts.isReadonly.value) return
    const r = await seedFromAuxBalance()
    if (r.error || (r.added === 0 && r.updated === 0)) return
    if (!rows.value.length) {
      ElMessage.warning('取数后仍无明细行，无法回写 G10-1')
      return
    }
    pushTotalsToAdjudication()
  }

  async function seedFromAuxBalance(): Promise<{ added: number; updated: number; dimType: string; error?: string }> {
    if (opts.isReadonly.value) return { added: 0, updated: 0, dimType: '', error: '只读' }
    const projectId = opts.projectId?.value ?? ''
    if (!projectId) return { added: 0, updated: 0, dimType: '', error: '缺少项目 ID' }
    auxLoading.value = true
    try {
      const { seeds, dimType, error } = await fetchG10AuxLiabilitySeeds(projectId)
      if (error || !seeds.length) {
        ElMessage.warning(error || '无辅助核算数据')
        return { added: 0, updated: 0, dimType, error: error || '无数据' }
      }
      const byName = new Map(
        rows.value.filter((r) => r.liabilityName.trim()).map((r) => [matchG10LiabilityKey(r.liabilityName), r]),
      )
      let added = 0
      let updated = 0
      const next: G10DetailRow[] = []
      let seq = 1
      for (const seed of seeds) {
        const key = matchG10LiabilityKey(seed.liabilityName)
        const prev = byName.get(key)
        if (prev) {
          updated += 1
          next.push(seedG10DetailRowFromAux(seed, seq++, prev))
          byName.delete(key)
        } else {
          added += 1
          next.push(seedG10DetailRowFromAux(seed, seq++))
        }
      }
      for (const r of rows.value) {
        if (!byName.has(matchG10LiabilityKey(r.liabilityName))) continue
        next.push(enrichG10DetailRow(r, seq++))
      }
      rows.value = next
      persist()
      ElMessage.success(`辅助核算取数完成：新增 ${added} 行，更新 ${updated} 行（维度：${dimType}）`)
      return { added, updated, dimType }
    } finally {
      auxLoading.value = false
    }
  }

  async function markProcedureComplete(): Promise<number> {
    if (opts.isReadonly.value) return -1
    const pid = opts.projectId?.value || ''
    if (!pid) {
      ElMessage.warning('缺少项目 ID，无法回填 G10A')
      return -1
    }
    if (!rows.value.length) {
      ElMessage.warning('请先编制 G10-2 明细表')
      return -1
    }
    if (integrityIssues.value.length) {
      try {
        await ElMessageBox.confirm(
          `仍有 ${integrityIssues.value.length} 项校验未通过，是否仍标记 G10A 明细程序为已完成？`,
          '回填 G10A',
          { type: 'warning', confirmButtonText: '仍标记完成', cancelButtonText: '取消' },
        )
      } catch {
        return -1
      }
    }

    procedureMarking.value = true
    try {
      const summary = buildG10DetailProcedureSummary({
        rowCount: rows.value.length,
        closingAdjustedTotal: totals.value.closingAdjusted,
        integrityErrors: integrityIssues.value.length,
        derivativeCount: derivativeDetailCount.value,
        linkedG10A: !hasAdjCrossMismatch.value && adjudicationClosingTotal.value != null,
      })
      const n = await markG10AProcedureSteps({
        projectId: pid,
        programNos: [...G10A_DETAIL_PROGRAM_NOS],
        status: 'completed',
        linkedWorkpapers: 'G10-2/G10-1',
        executionSummary: summary,
      })
      opts.debouncedSave(G10A_DETAIL_MARK_KEY, {
        conclusion: 'completed',
        remark: JSON.stringify({
          at: new Date().toISOString(),
          summary,
          programNos: [...G10A_DETAIL_PROGRAM_NOS],
        }),
      })
      ElMessage.success(
        n > 0
          ? `已回填 G10A 程序步骤 ${[...G10A_DETAIL_PROGRAM_NOS].join('/')}（明细编制）为已完成`
          : '已记录完成标记（程序表字段写入可能需刷新 G10A 查看）',
      )
      return Math.max(n, 1)
    } finally {
      procedureMarking.value = false
    }
  }

  return {
    rows,
    activeTab,
    activeRowIndex,
    currentRowKey,
    totalRow,
    totals,
    categorySubtotals,
    adjudicationClosingTotal,
    adjCrossVariance,
    hasAdjCrossMismatch,
    integrityIssues,
    level3MissingMethodCount,
    fvLinkByRowId,
    unmatchedFvDetailCount,
    derivativeLinkByRowId,
    derivativeDetailCount,
    unmatchedDerivativeDetailCount,
    auxLoading,
    procedureMarking,
    procedureMarked,
    G10_LIABILITY_TYPE_OPTIONS,
    G10_LIABILITY_CATEGORY_OPTIONS,
    G10_FV_LEVEL_OPTIONS,
    G10_VALUATION_METHOD_OPTIONS,
    G10_CONFIRMATION_OPTIONS,
    updateRow,
    addRow,
    removeRow,
    reloadFromStore,
    setActiveRowIndex,
    pushTotalsToAdjudication,
    pullFromAdjudication,
    seedFromAuxBalance,
    seedAuxAndPushToAdjudication,
    markProcedureComplete,
    ITEM_ID_ROWS,
  }
}
