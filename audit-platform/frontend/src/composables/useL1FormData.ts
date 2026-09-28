/**
 * useL1FormData — L1 短期借款数据加载/保存/TB回写 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.1
 * Requirements: 1.9, 1.10, 2.6
 *
 * 职责：
 * - selfLoad(): 从 render-config 或 checklist_responses 加载数据
 * - checklist_responses 持久化: GET/PUT /api/workpapers/:wpId/checklist-responses
 * - item_id 命名: 前缀 L1-{sheet}-{field}
 * - writebackTB(2001): 审定数回写 trial_balance 科目 2001 短期借款
 * - debounce/即时保存: 文本字段 debounce 2s，枚举/结论即时保存
 * - readonly guard: readonly=true 时跳过所有保存
 * - reactive state: 审定表/明细表/利息测算/征信/逾期/抵质押各sheet数据
 */
import { ref, onScopeDispose, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
// 🔴 复用既有值化行身份工厂，不新造第 6 个同型模块
// （该文件头已登记平台上 5 个同型模块与「是否收敛」的技术债）。
import { newRowIdentity } from '@/components/workpaper/composables/shared/rowIdentity'

/** 审定表 sheet 名（含子码 L1-1，供后端 extract_determination_wp_code 解出） */
const DETERMINATION_SHEET_NAME = '审定表L1-1'
const ACCOUNT_CODE = '2001' // 短期借款（贷方/负债类）

// ─── Types ───────────────────────────────────────────────────────────────────

/** checklist_responses 单条 item */
export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
  wp_ref?: string | null
}

/**
 * 审定表分类行（对齐致同源模板「审定表L1-1」双期结构）
 *
 * 源模板：期初数(未审/账项调整/重分类/审定) + 期末数(未审/账项调整/重分类/审定)
 *        + 本期未审vs上期审定(变动额/率) + 本期审定vs上期审定(变动额/率) + 原因分析
 * 仅存储可编辑字段；审定数/变动额/变动率为派生列，由 useL1Adjudication computed 计算。
 */
export interface AdjudicationCategory {
  name: string            // 借款分类（信用/抵押/保证/质押）
  // 期初数
  beginUnadjusted: number // 期初未审数
  beginAje: number        // 期初账项调整
  beginRje: number        // 期初重分类调整
  // 期末数
  endUnadjusted: number   // 期末未审数
  endAje: number          // 期末账项调整
  endRje: number          // 期末重分类调整
  // 原因分析
  reason: string
}

/** 审定表状态 */
export interface AdjudicationState {
  categories: AdjudicationCategory[]
}

/**
 * 明细表行（`明细表L1-2`）—— 逐字段对齐模板 28 列。
 *
 * spec: l-cycle-true-adapter-registration · Task 5b
 *
 * 🔴 `rowId` 是**稳定行身份**，取代原先的位置化 `L1-det-{rowIndex+1}-{field}`：
 * 后者在 `removeRow()` 后靠 `_triggerSaveAll()` 重建整个序列，删中间行会让后续行的
 * item_id 全部错位、用户填的值静默跟错行。契约 schema 的
 * `FORBIDDEN_ROW_IDENTITY_KINDS` 也明含 `index`/`ordinal`/`position`/`array_index`。
 *
 * 🔴 字段顺序即 Excel 列序（A→AB）。`endBalance` / `auditedPrior` / `auditedIncrease` /
 * `auditedDecrease` / `auditedEnd` 五个在模板里**是公式**（K/R/S/T/U），受契约
 * `formula_mask` 保护，OO 侧不得被值覆盖；前端仍保留派生值用于展示与交叉校验。
 *
 * 🔴 `amount` / `currency` 模板**无对应列**，是 HTML-only 字段（契约
 * `review.html_store.html_only_keys` 已登记），不参与 OO 往返。
 */
export interface DetailRow {
  /** 稳定行身份（值化，不随位置漂移）。 */
  rowId: string
  seqNo: number               // A 序号
  loanType: string            // B 借款种类
  bank: string                // C 贷款单位
  startDate: string           // D 起始日期
  endDate: string             // E 讫止日期
  rate: number                // F 年利率
  rateKind: string            // G 固定/浮动利率
  beginning: number           // H 未审-期初余额
  creditAmount: number        // I 未审-本期增加
  debitAmount: number         // J 未审-本期减少
  endBalance: number          // K 未审-期末余额（模板公式 =H+I-J）
  priorAje: number            // L 期初调整-账项调整
  priorRje: number            // M 期初调整-重分类调整
  ajeIncrease: number         // N 账项调整-本期增加
  ajeDecrease: number         // O 账项调整-本期减少
  rjeIncrease: number         // P 重分类调整-本期增加
  rjeDecrease: number         // Q 重分类调整-本期减少
  auditedPrior: number        // R 审定-期初余额（模板公式 =H+L+M）
  auditedIncrease: number     // S 审定-本期增加（模板公式 =I+N+P）
  auditedDecrease: number     // T 审定-本期减少（模板公式 =J+O+Q）
  auditedEnd: number          // U 审定-期末余额（模板公式 =R+S-T）
  purpose: string             // V 借款用途
  guarantee: string           // W 保证人/抵押物/质押物
  contractNo: string          // X 借款合同（索引）
  isOverdue: string           // Y 是否逾期
  confirmationRef: string     // Z 询证函（索引）
  creditReportChecked: string // AA 与征信报告核对
  remark: string              // AB 备注
  /** ↓ HTML-only：模板无对应列，不入契约、不参与 OO 往返。 */
  amount: number
  currency: string
}

/** 明细表的 store item（整表一条，载荷是 `DetailRow[]` 的 JSON）。 */
export const DETAIL_ROWS_ITEM_ID = 'L1-2-rows'

/** 新建一行明细（字段齐全 + 稳定身份）。 */
export function createEmptyDetailRow(): DetailRow {
  return {
    rowId: newRowIdentity('l12'),
    seqNo: 0,
    loanType: '',
    bank: '',
    startDate: '',
    endDate: '',
    rate: 0,
    rateKind: '',
    beginning: 0,
    creditAmount: 0,
    debitAmount: 0,
    endBalance: 0,
    priorAje: 0,
    priorRje: 0,
    ajeIncrease: 0,
    ajeDecrease: 0,
    rjeIncrease: 0,
    rjeDecrease: 0,
    auditedPrior: 0,
    auditedIncrease: 0,
    auditedDecrease: 0,
    auditedEnd: 0,
    purpose: '',
    guarantee: '',
    contractNo: '',
    isOverdue: '',
    confirmationRef: '',
    creditReportChecked: '',
    remark: '',
    amount: 0,
    currency: 'CNY',
  }
}

/** 利息测算行 */
export interface InterestCalcRow {
  bank: string
  contractNo: string
  loanStart: string
  loanEnd: string
  startDate: string
  endDate: string
  rate: number
  principal: number
  days: number
  calculatedInterest: number
  bookedInterest: number
  diff: number
}

/** 征信核对行 */
export interface CreditCheckRow {
  bank: string
  creditLimit: number
  usedLimit: number
  creditBalance: number
  bookBalance: number
  diff: number
  diffExplanation: string
}

/** 逾期检查行 */
export interface OverdueCheckRow {
  contractNo: string
  dueDate: string
  reportDate: string
  overdueDays: number
  overdueAmount: number
  isExtended: string
  riskEvaluation: string
}

/** 抵质押检查行 */
export interface PledgeCheckRow {
  assetName: string
  bookValue: number
  guaranteedLoan: number
  pledgeRatio: number
  ownershipVerified: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const DEBOUNCE_MS = 2000

/** 默认审定表分类（对齐源模板 A7~A10 顺序：信用/抵押/保证/质押） */
const DEFAULT_CATEGORIES = ['信用借款', '抵押借款', '保证借款', '质押借款']

function createEmptyCategory(name: string): AdjudicationCategory {
  return {
    name,
    beginUnadjusted: 0, beginAje: 0, beginRje: 0,
    endUnadjusted: 0, endAje: 0, endRje: 0,
    reason: '',
  }
}

function createEmptyAdjudicationState(): AdjudicationState {
  return {
    categories: DEFAULT_CATEGORIES.map(createEmptyCategory),
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useL1FormData(
  wpId: Ref<string>,
  projectId: Ref<string>,
  isReadonly: Ref<boolean>,
) {
  // ─── Reactive state ────────────────────────────────────────────────────────
  const isLoading = ref(false)
  const adjudicationData = ref<AdjudicationState>(createEmptyAdjudicationState())
  const detailRows = ref<DetailRow[]>([])
  const interestCalcRows = ref<InterestCalcRow[]>([])
  const creditCheckRows = ref<CreditCheckRow[]>([])
  const overdueCheckRows = ref<OverdueCheckRow[]>([])
  const pledgeCheckRows = ref<PledgeCheckRow[]>([])

  // Internal: all raw responses for re-parsing
  const _allResponses = ref<Map<string, ChecklistItem>>(new Map())

  // Per-item debounce timers
  const _debounceTimers = new Map<string, ReturnType<typeof setTimeout>>()
  // Track pending items for flush
  const _pendingItems = new Set<string>()

  // ─── selfLoad ──────────────────────────────────────────────────────────────

  /**
   * 从 checklist_responses 加载 L1 数据，解析到结构化 state。
   * 当 htmlData 为空时（bundle内嵌场景），也可从 render-config 获取上下文。
   */
  async function selfLoad(): Promise<void> {
    if (!wpId.value) return
    isLoading.value = true

    try {
      const res = await api.get(`/api/workpapers/${wpId.value}/checklist-responses`)
      const responses: ChecklistItem[] = Array.isArray(res) ? res : (res?.data ?? [])

      // 存储原始 responses
      const map = new Map<string, ChecklistItem>()
      for (const r of responses) {
        if (r.item_id?.startsWith('L1-')) {
          map.set(r.item_id, r)
        }
      }
      _allResponses.value = map

      // 解析到各 sheet state
      _parseAdjudication(map)
      _parseDetailRows(map)
      _parseInterestCalcRows(map)
      _parseCreditCheckRows(map)
      _parseOverdueCheckRows(map)
      _parsePledgeCheckRows(map)
    } catch {
      ElMessage.warning('L1数据加载失败，可手动填写')
    } finally {
      isLoading.value = false
    }
  }

  // ─── Parse helpers ─────────────────────────────────────────────────────────

  /** 审定表双期字段（仅可编辑列，派生列由 composable 计算） */
  const ADJ_NUM_FIELDS = [
    'beginUnadjusted', 'beginAje', 'beginRje',
    'endUnadjusted', 'endAje', 'endRje',
  ] as const

  function _parseAdjudication(map: Map<string, ChecklistItem>): void {
    // item_id: L1-adj-{categoryIndex}-{field}
    const categories: AdjudicationCategory[] = []
    const catPattern = /^L1-adj-(\d+)-(\w+)$/

    for (const [id, item] of map) {
      const match = id.match(catPattern)
      if (!match) continue
      const idx = parseInt(match[1], 10)
      const field = match[2]

      while (categories.length < idx) {
        categories.push(createEmptyCategory(DEFAULT_CATEGORIES[categories.length] || ''))
      }
      const cat = categories[idx - 1] as any
      const val = item.remark || item.conclusion || ''
      if (field === 'name') cat.name = val
      else if (field === 'reason') cat.reason = val
      else if ((ADJ_NUM_FIELDS as readonly string[]).includes(field)) cat[field] = parseFloat(val) || 0
    }

    if (categories.length === 0) {
      adjudicationData.value = createEmptyAdjudicationState()
    } else {
      adjudicationData.value = { categories }
    }
  }

  function _parseDynamicRows<T>(
    map: Map<string, ChecklistItem>,
    prefix: string,
    fields: string[],
    factory: () => T,
  ): T[] {
    // item_id: L1-{prefix}-{rowIndex}-{field}
    const pattern = new RegExp(`^L1-${prefix}-(\\d+)-(\\w+)$`)
    const rows: T[] = []

    for (const [id, item] of map) {
      const match = id.match(pattern)
      if (!match) continue
      const idx = parseInt(match[1], 10)
      const field = match[2]

      while (rows.length < idx) rows.push(factory())
      const row = rows[idx - 1] as any
      const val = item.remark || item.conclusion || ''
      if (fields.includes(field)) {
        // Attempt numeric parse for known numeric fields
        const numVal = parseFloat(val)
        row[field] = isNaN(numVal) ? val : numVal
      }
    }
    return rows
  }

  // 🔴 `DETAIL_FIELDS` 已删（spec: l-cycle-true-adapter-registration Task 5b）：
  //    明细表改走单条 `L1-2-rows` JSON 载荷，不再按字段名逐个拼位置化 item_id。
  //    其余四表的 *_FIELDS 保留 —— 它们仍走 `_parseDynamicRows` / `_serializeRows`。

  const INTEREST_FIELDS = [
    'bank', 'contractNo', 'loanStart', 'loanEnd', 'startDate', 'endDate',
    'rate', 'principal', 'days', 'calculatedInterest', 'bookedInterest', 'diff',
  ]

  const CREDIT_FIELDS = [
    'bank', 'creditLimit', 'usedLimit', 'creditBalance',
    'bookBalance', 'diff', 'diffExplanation',
  ]

  const OVERDUE_FIELDS = [
    'contractNo', 'dueDate', 'reportDate', 'overdueDays',
    'overdueAmount', 'isExtended', 'riskEvaluation',
  ]

  const PLEDGE_FIELDS = [
    'assetName', 'bookValue', 'guaranteedLoan',
    'pledgeRatio', 'ownershipVerified',
  ]

  /**
   * 明细表：整表一条 item（`L1-2-rows`）+ 稳定 `rowId`。
   *
   * spec: l-cycle-true-adapter-registration · Task 5b
   *
   * 🔴 **不再走 `_parseDynamicRows`**（那是位置化 `L1-det-{n}-{field}` 通道）。
   * 真库 `L1-det-*` 现算 0 行 ⇒ 切换零迁移负担，故不保留回落读取
   * （留回落等于留一条永不执行的死路径）。
   * 🔴 其余四表（int / cred / ovd / plg）**仍走 `_parseDynamicRows`**，本 spec 不动 ——
   * `int` 被 `h2L1LoanPull.ts` 跨循环消费（`L1-int-{n}-{field}`），改它会连带 H2。
   */
  function _parseDetailRows(map: Map<string, ChecklistItem>): void {
    const raw = map.get(DETAIL_ROWS_ITEM_ID)?.remark
    if (!raw) {
      detailRows.value = []
      return
    }
    let parsed: unknown
    try {
      parsed = JSON.parse(raw)
    } catch {
      // 载荷坏了宁可给空表，不猜、不半解析（半解析会让用户以为数据只丢了一部分）
      detailRows.value = []
      return
    }
    if (!Array.isArray(parsed)) {
      detailRows.value = []
      return
    }
    detailRows.value = parsed.map((row) => ({
      ...createEmptyDetailRow(),
      ...(row as Partial<DetailRow>),
      // 🔴 缺 rowId 的历史行当场补铸：身份缺失时按位置兜底会把位置化又带回来
      rowId: (row as Partial<DetailRow>)?.rowId || newRowIdentity('l12'),
    }))
  }

  function _parseInterestCalcRows(map: Map<string, ChecklistItem>): void {
    interestCalcRows.value = _parseDynamicRows(map, 'int', INTEREST_FIELDS, () => ({
      bank: '', contractNo: '', loanStart: '', loanEnd: '',
      startDate: '', endDate: '', rate: 0, principal: 0,
      days: 0, calculatedInterest: 0, bookedInterest: 0, diff: 0,
    }))
  }

  function _parseCreditCheckRows(map: Map<string, ChecklistItem>): void {
    creditCheckRows.value = _parseDynamicRows(map, 'cred', CREDIT_FIELDS, () => ({
      bank: '', creditLimit: 0, usedLimit: 0,
      creditBalance: 0, bookBalance: 0, diff: 0, diffExplanation: '',
    }))
  }

  function _parseOverdueCheckRows(map: Map<string, ChecklistItem>): void {
    overdueCheckRows.value = _parseDynamicRows(map, 'ovd', OVERDUE_FIELDS, () => ({
      contractNo: '', dueDate: '', reportDate: '',
      overdueDays: 0, overdueAmount: 0, isExtended: '', riskEvaluation: '',
    }))
  }

  function _parsePledgeCheckRows(map: Map<string, ChecklistItem>): void {
    pledgeCheckRows.value = _parseDynamicRows(map, 'plg', PLEDGE_FIELDS, () => ({
      assetName: '', bookValue: 0, guaranteedLoan: 0,
      pledgeRatio: 0, ownershipVerified: '',
    }))
  }

  // ─── Save: core ────────────────────────────────────────────────────────────

  async function _doSave(items: ChecklistItem[]): Promise<void> {
    if (!wpId.value || items.length === 0) return
    try {
      await api.put(`/api/workpapers/${wpId.value}/checklist-responses`, {
        project_id: projectId.value,
        items: items.map(item => ({
          item_id: item.item_id,
          conclusion: item.conclusion || null,
          remark: item.remark || null,
          wp_ref: item.wp_ref || null,
        })),
      })
    } catch (err: any) {
      const msg = err?.message || ''
      if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
        ElMessage.error('保存失败，请稍后重试')
      }
    }
  }

  // ─── saveImmediate (枚举/结论即时保存) ─────────────────────────────────────

  /**
   * 立即保存指定 items（用于枚举/结论/选择类字段）。
   * readonly guard: readonly=true 时跳过。
   */
  async function saveImmediate(items: ChecklistItem[]): Promise<void> {
    if (isReadonly.value) return
    if (items.length === 0) return

    // 取消相关 items 的 debounce 定时器
    for (const item of items) {
      const timer = _debounceTimers.get(item.item_id)
      if (timer) {
        clearTimeout(timer)
        _debounceTimers.delete(item.item_id)
      }
      _pendingItems.delete(item.item_id)
      _allResponses.value.set(item.item_id, item)
    }

    await _doSave(items)
  }

  // ─── debounceSave (文本字段 debounce 2s) ───────────────────────────────────

  /**
   * 文本字段变更后 debounce 2s 保存。
   * Per-item 独立计时器，避免快速编辑多字段时相互覆盖。
   * readonly guard: readonly=true 时跳过。
   */
  function debounceSave(items: ChecklistItem[]): void {
    if (isReadonly.value) return
    if (items.length === 0) return

    for (const item of items) {
      _allResponses.value.set(item.item_id, item)
      _pendingItems.add(item.item_id)

      // 重置该 item 的定时器
      const prevTimer = _debounceTimers.get(item.item_id)
      if (prevTimer) clearTimeout(prevTimer)

      const timer = setTimeout(() => {
        _debounceTimers.delete(item.item_id)
        _pendingItems.delete(item.item_id)
        _doSave([item])
      }, DEBOUNCE_MS)
      _debounceTimers.set(item.item_id, timer)
    }
  }

  // ─── writebackTB (显式发布审定数到 trial_balance 2001) ─────────────────────

  /**
   * 发布审定数到 trial_balance（科目 2001 短期借款，贷方/负债类）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 4 / Req 1,2,8。
   * 此前直调旧端点 `PUT /projects/{pid}/trial-balance/writeback`（无二次确认/无
   * publish_confirmed/无幂等），且由 useL1Adjudication 的 watcher 在数据变化时**自动**
   * 触发（违反 Req 1：普通保存/数据变化绝不写 TB）。现改为显式发布门：仅在用户显式
   * 确认（useL1Adjudication.publishToTb 的二次确认）后调用本函数 →
   * `POST /workpapers/{wpId}/audit-determination/publish-to-tb`（携审定表 sheet 名 +
   * writeback_rows 预算行），后端校验发布权限、发 publish_confirmed=True + token →
   * 回写 handler 幂等回写 trial_balance。成功后 emit substantive:adjudicated（附注刷新）。
   */
  async function writebackTB(auditedAmount: number): Promise<void> {
    if (isReadonly.value) return
    if (!wpId.value) return
    await api.post(`/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`, {
      // sheet 名固定含审定表子码 L1-1，后端 extract_determination_wp_code 据此解出 L1-1
      sheet_name: DETERMINATION_SHEET_NAME,
      writeback_rows: [
        { account_code: ACCOUNT_CODE, audited_amount: auditedAmount, amount_kind: 'balance' },
      ],
    })
    // 发布 EventBus 通知审定数变更（附注等组件订阅刷新）
    eventBus.emit('substantive:adjudicated', {
      accountCode: ACCOUNT_CODE,
      auditedAmount,
      wpCode: 'L1',
      timestamp: Date.now(),
    })
  }

  // ─── serializeAll ──────────────────────────────────────────────────────────

  /**
   * 序列化全部 state 为 ChecklistItem[]，用于批量保存。
   * item_id 命名: L1-{sheet}-{field} 或 L1-{sheet}-{rowIndex}-{field}
   */
  function serializeAll(): ChecklistItem[] {
    const items: ChecklistItem[] = []

    // ─── Adjudication: L1-adj-{n}-{field}（双期结构） ───
    for (let i = 0; i < adjudicationData.value.categories.length; i++) {
      const cat = adjudicationData.value.categories[i] as any
      const n = i + 1
      items.push({ item_id: `L1-adj-${n}-name`, conclusion: null, remark: cat.name || null })
      items.push({ item_id: `L1-adj-${n}-reason`, conclusion: null, remark: cat.reason || null })
      for (const field of ADJ_NUM_FIELDS) {
        const value = cat[field]
        items.push({
          item_id: `L1-adj-${n}-${field}`,
          conclusion: null,
          remark: value !== 0 ? String(value) : null,
        })
      }
    }

    // ─── Detail rows：整表一条 item（spec: l-cycle-true-adapter-registration Task 5b）───
    // 🔴 从 `L1-det-{rowIndex+1}-{field}` 位置化多条 item 换成单条 `L1-2-rows` JSON 数组。
    //    真库旧键现算 0 行 ⇒ 不写迁移、不留双写（双写会让两份载荷谁是真源说不清）。
    items.push({
      item_id: DETAIL_ROWS_ITEM_ID,
      conclusion: null,
      remark: detailRows.value.length ? JSON.stringify(detailRows.value) : null,
    })

    // ─── Interest calc: L1-int-{n}-{field} ───
    _serializeRows(items, 'int', interestCalcRows.value, INTEREST_FIELDS)

    // ─── Credit check: L1-cred-{n}-{field} ───
    _serializeRows(items, 'cred', creditCheckRows.value, CREDIT_FIELDS)

    // ─── Overdue check: L1-ovd-{n}-{field} ───
    _serializeRows(items, 'ovd', overdueCheckRows.value, OVERDUE_FIELDS)

    // ─── Pledge check: L1-plg-{n}-{field} ───
    _serializeRows(items, 'plg', pledgeCheckRows.value, PLEDGE_FIELDS)

    return items
  }

  function _serializeRows(
    items: ChecklistItem[],
    prefix: string,
    rows: any[],
    fields: string[],
  ): void {
    for (let i = 0; i < rows.length; i++) {
      const row = rows[i]
      const n = i + 1
      for (const field of fields) {
        const val = row[field]
        const strVal = val != null && val !== '' && val !== 0 ? String(val) : null
        items.push({
          item_id: `L1-${prefix}-${n}-${field}`,
          conclusion: null,
          remark: strVal,
        })
      }
    }
  }

  // ─── Flush (组件卸载时确保无数据丢失) ──────────────────────────────────────

  function _flushPending(): void {
    for (const timer of _debounceTimers.values()) {
      clearTimeout(timer)
    }
    _debounceTimers.clear()

    if (_pendingItems.size > 0) {
      const items: ChecklistItem[] = []
      for (const itemId of _pendingItems) {
        const resp = _allResponses.value.get(itemId)
        if (resp) items.push(resp)
      }
      _pendingItems.clear()
      if (items.length > 0) {
        _doSave(items)
      }
    }
  }

  // ─── Lifecycle ─────────────────────────────────────────────────────────────

  onScopeDispose(() => {
    _flushPending()
  })

  // ─── getItemValue (按 item_id 取 remark 值) ─────────────────────────────────

  /**
   * 根据 item_id 获取已缓存的 remark 值。
   * 用于附注/调整等子组件从 formData 中恢复存储的字段值。
   */
  function getItemValue(itemId: string): string | null {
    const item = _allResponses.value.get(itemId)
    return item?.remark ?? null
  }

  // ─── getItemsByPrefix (按前缀取全部已加载 items) ─────────────────────────────

  /**
   * 返回全部 item_id 以 prefix 开头的已加载 ChecklistItem。
   * 用于检查表/合同检查等「自持久化」子组件按 item_id 前缀恢复动态行，
   * 避免误用 serializeAll()（仅含 adj/det/int/cred/ovd/plg 结构化字段，
   * 不含 L1-chk 前缀 / L1-con 前缀等自定义 item_id → 刷新后数据丢失）。
   */
  function getItemsByPrefix(prefix: string): ChecklistItem[] {
    const out: ChecklistItem[] = []
    for (const [id, item] of _allResponses.value) {
      if (id.startsWith(prefix)) out.push(item)
    }
    return out
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    isLoading,
    adjudicationData,
    detailRows,
    interestCalcRows,
    creditCheckRows,
    overdueCheckRows,
    pledgeCheckRows,
    // Actions
    selfLoad,
    saveImmediate,
    debounceSave,
    writebackTB,
    serializeAll,
    getItemValue,
    getItemsByPrefix,
  }
}

export default useL1FormData
