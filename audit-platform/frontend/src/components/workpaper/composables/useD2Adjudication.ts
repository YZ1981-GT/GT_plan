/**
 * useD2Adjudication — 审定表D2-1核心逻辑 composable
 *
 * Spec: .kiro/specs/d2-accounts-receivable-refactor/
 * Task: 3.1
 *
 * 职责：
 * - 审定表固定行结构（单项计提/账龄组合/客户类型组合/合计）
 * - SUMIF聚合：从D2-2明细表按"信用风险组合方式"聚合到审定表各行
 * - 公式引擎：审定数/变动额/变动率自动计算
 * - EventBus：发布 substantive:adjudicated / 监听 adjustment:created
 * - publishToTb：显式确认（二次确认）→ 走 publish-to-tb 显式发布端点回写
 *   trial_balance.audited_amount（科目1122）；普通保存/数据变化不再自动写 TB
 *   （spec: tb-writeback-explicit-publish-gate Task 2 / Req 1,2,8）
 *
 * Requirements: 1.1-1.10, 21.1, 21.2, 21.5, 21.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  parseNum,
  getAuditedAmount,
  getChangeRate,
  sumif,
} from './useD2FormulaEngine'
import { resolveTbAmountWithSeed } from './dCycleTbSeed'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistItem, ChecklistResponse } from './useD2FormData'

const BALANCE_TOLERANCE = 0.01

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseD2BaseOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  bsDate?: Ref<string>
  /**
   * 试算平衡表数（应收账款净额）的 render 种子 —— 由 `project_context.tb_amount`
   * 经 `dCycleTbSeed.pickDTbAmount` 取得。
   *
   * 🔴 **只读回退**：仅在审计师未手工保存 `D2-adj-tb-amount` 时生效（手工优先）。
   * 改造前该键只从 `allResponses` 读 ⇒ render 下发的 `tb_amount` 是 dead output，
   * 「四表入库后审定表看不到 TB 核对数」的直接原因。
   *
   * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 16 / R4.4
   */
  tbSeedAmount?: Ref<number | null>
}

export interface AdjudicationRow {
  rowKey: string              // 'individual' | 'aging' | 'customer-type' | 'total'
  label: string               // '单项计提' | '账龄组合' | '客户类型组合' | '合计'
  // 期初
  priorUnadjusted: number
  priorAje: number
  priorRje: number
  priorAudited: number        // = 未审 + AJE + RJE
  // 期末
  currentUnadjusted: number   // SUMIF从D2-2取得
  currentAje: number
  currentRje: number
  currentAudited: number      // = 未审 + AJE + RJE
  // 变动
  change: number              // = 期末审定 - 期初审定
  changeRate: number | ''     // = (期末-期初)/期初
  reasonAnalysis: string
  /**
   * 取数来源（归一自旧 isFromSumif 布尔标记 —— spec d2-sync-coverage Q9）。
   * - 'tb'     = SUMIF 从 D2-2 明细表按 creditRiskClassification 分类派生
   * - 'manual' = 人工录入（SUMIF 无匹配或合计行）
   * 与 shared/dynamicAdjudicationRows.DynamicRowSource 同域，接四态覆盖状态机。
   */
  source: 'tb' | 'manual'
  isEditable: boolean         // 合计行=false
}

export interface DetailRowForSumif {
  creditRiskClassification: string  // AI列: 单项计提/账龄组合/客户类型组合
  currentUnadjusted: number         // S列: 期末未审余额
  currentAje: number                // Z列: 账项调整
  currentRje: number                // AA列: 重分类调整
  priorAudited: number              // 期初审定余额
}

export interface SubstantiveAdjudicatedPayload {
  wpCode: string
  accountCode: string
  auditedAmount: number
  priorAmount: number
  changeRate: number | null
}

export interface AdjustmentCreatedPayload {
  wpCode: string
  entryType: 'AJE' | 'RJE'
  debitAccount: string
  creditAccount: string
  amount: number
  description: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 审定表固定行配置 */
export const ADJUDICATION_ROW_CONFIG: Array<{
  rowKey: string
  label: string
  classification: string
  isEditable: boolean
}> = [
  { rowKey: 'individual', label: '应收账款-单项计提', classification: '单项计提', isEditable: true },
  { rowKey: 'aging', label: '应收账款-账龄组合', classification: '账龄组合', isEditable: true },
  { rowKey: 'customer-type', label: '应收账款-客户类型组合', classification: '客户类型组合', isEditable: true },
  { rowKey: 'total', label: '合计', classification: '', isEditable: false },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2Adjudication(options: UseD2BaseOptions) {
  const { wpId, projectId, allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  // ─── State ─────────────────────────────────────────────────────────────

  const sumifStatus = ref<'loaded' | 'computing' | 'error'>('loaded')
  const publishing = ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  let previousAuditedAmount: number | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Helpers ───────────────────────────────────────────────────────────

  function getVal(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  }

  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── SUMIF: Read D2-detail-rows from allResponses ──────────────────────

  /**
   * 从 allResponses 中解析 D2-2 明细表行数据
   * D2-2 明细表的数据存储格式：D2-detail-rows (JSON数组)
   * 或者逐行存储：D2-detail-{n}-{field}
   */
  const detailRows = computed<DetailRowForSumif[]>(() => {
    // 方式1: 尝试从 JSON remark 中读取完整行数据
    const jsonData = getVal('D2-detail-rows').remark
    if (jsonData) {
      try {
        const parsed = JSON.parse(jsonData)
        if (Array.isArray(parsed)) {
          return parsed.map((row: any) => ({
            creditRiskClassification: row.creditRiskClassification || row.AI || '',
            currentUnadjusted: parseNum(row.currentUnadjusted ?? row.S),
            currentAje: parseNum(row.currentAje ?? row.Z),
            currentRje: parseNum(row.currentRje ?? row.AA),
            priorAudited: parseNum(row.priorAudited),
          }))
        }
      } catch { /* 主路径解析失败 → 返回空，不再退回死降级路径 */ }
    }

    // 🔴 spec d2-sync-coverage Task 15：删死降级路径（裁决 E4 / Requirement 4.3）。
    // 原「方式2」逐行读 D2-detail-{n}-{field} + D2-detail-count 已删 —— useD2Detail **只写**
    // D2-detail-rows（JSON 数组），这两类键全仓零写入方、恒返 0，是从未生效的死代码。
    // 主路径（读 D2-detail-rows JSON）是唯一权威；解析失败或无数据均返回空数组。
    return []
  })

  // ─── SUMIF Aggregation ─────────────────────────────────────────────────

  /**
   * SUMIF聚合：按信用风险组合方式分类聚合D2-2明细表各值列
   */
  const sumifAggregation = computed(() => {
    const rows = detailRows.value
    if (rows.length === 0) return null

    sumifStatus.value = 'computing'
    try {
      const result = {
        individual: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '单项计提', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '单项计提', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '单项计提', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '单项计提', 'priorAudited'),
        },
        aging: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '账龄组合', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '账龄组合', 'priorAudited'),
        },
        customerType: {
          currentUnadjusted: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentUnadjusted'),
          currentAje: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentAje'),
          currentRje: sumif(rows, 'creditRiskClassification', '客户类型组合', 'currentRje'),
          priorAudited: sumif(rows, 'creditRiskClassification', '客户类型组合', 'priorAudited'),
        },
      }
      sumifStatus.value = 'loaded'
      return result
    } catch {
      sumifStatus.value = 'error'
      return null
    }
  })

  // ─── Adjudication Rows Computed ────────────────────────────────────────

  /**
   * 审定表各行数据（3分类行 + 合计行）
   *
   * 数据来源优先级：
   * 1. SUMIF聚合值（从D2-2明细表自动计算）
   * 2. 手工录入值（D2-adj-{rowKey}-{period}-{type} 存储）
   */
  const adjudicationRows: ComputedRef<AdjudicationRow[]> = computed(() => {
    const agg = sumifAggregation.value
    const classificationRows = ADJUDICATION_ROW_CONFIG.filter(r => r.rowKey !== 'total')

    const dataRows: AdjudicationRow[] = classificationRows.map(cfg => {
      const { rowKey, label, classification, isEditable } = cfg

      // 期初数据
      const priorUnadjusted = getSumifOrManual(agg, rowKey, 'priorAudited', `D2-adj-${rowKey}-prior-unadjusted`)
      const priorAje = parseNum(getVal(`D2-adj-${rowKey}-prior-aje`).remark)
      const priorRje = parseNum(getVal(`D2-adj-${rowKey}-prior-rje`).remark)
      const priorAudited = getAuditedAmount(priorUnadjusted, priorAje, priorRje)

      // 期末数据 - SUMIF优先
      const currentUnadjusted = getSumifOrManual(agg, rowKey, 'currentUnadjusted', `D2-adj-${rowKey}-current-unadjusted`)
      const currentAje = getSumifOrManual(agg, rowKey, 'currentAje', `D2-adj-${rowKey}-current-aje`)
      const currentRje = getSumifOrManual(agg, rowKey, 'currentRje', `D2-adj-${rowKey}-current-rje`)
      const currentAudited = getAuditedAmount(currentUnadjusted, currentAje, currentRje)

      // 变动
      const change = currentAudited - priorAudited
      const changeRate = getChangeRate(priorAudited, currentAudited)

      // 原因分析
      const reasonAnalysis = getVal(`D2-adj-${rowKey}-reason`).remark || ''

      // 取数来源（归一自旧 isFromSumif：SUMIF 派生 → 'tb'，否则人工 → 'manual'）
      const source: 'tb' | 'manual' =
        agg !== null && classification !== '' ? 'tb' : 'manual'

      return {
        rowKey,
        label,
        priorUnadjusted,
        priorAje,
        priorRje,
        priorAudited,
        currentUnadjusted,
        currentAje,
        currentRje,
        currentAudited,
        change,
        changeRate,
        reasonAnalysis,
        source,
        isEditable,
      }
    })

    // 合计行 = SUM三分类行
    const totalRow = buildTotalRow(dataRows)
    return [...dataRows, totalRow]
  })

  /**
   * 从SUMIF聚合或手工值获取数据
   */
  function getSumifOrManual(
    agg: typeof sumifAggregation.value,
    rowKey: string,
    sumifField: string,
    manualItemId: string
  ): number {
    if (agg) {
      const aggKey = rowKey === 'customer-type' ? 'customerType' : rowKey
      const aggGroup = (agg as any)[aggKey]
      if (aggGroup && aggGroup[sumifField] !== undefined) {
        const sumifVal = aggGroup[sumifField]
        if (sumifVal !== 0) return sumifVal
      }
    }
    return parseNum(getVal(manualItemId).remark)
  }

  /**
   * 构建合计行
   */
  function buildTotalRow(dataRows: AdjudicationRow[]): AdjudicationRow {
    const priorUnadjusted = dataRows.reduce((s, r) => s + r.priorUnadjusted, 0)
    const priorAje = dataRows.reduce((s, r) => s + r.priorAje, 0)
    const priorRje = dataRows.reduce((s, r) => s + r.priorRje, 0)
    const priorAudited = dataRows.reduce((s, r) => s + r.priorAudited, 0)
    const currentUnadjusted = dataRows.reduce((s, r) => s + r.currentUnadjusted, 0)
    const currentAje = dataRows.reduce((s, r) => s + r.currentAje, 0)
    const currentRje = dataRows.reduce((s, r) => s + r.currentRje, 0)
    const currentAudited = dataRows.reduce((s, r) => s + r.currentAudited, 0)
    const change = currentAudited - priorAudited
    const changeRate = getChangeRate(priorAudited, currentAudited)

    return {
      rowKey: 'total',
      label: '合计',
      priorUnadjusted,
      priorAje,
      priorRje,
      priorAudited,
      currentUnadjusted,
      currentAje,
      currentRje,
      currentAudited,
      change,
      changeRate,
      reasonAnalysis: '',
      source: 'manual',
      isEditable: false,
    }
  }

  // ─── Total Row (convenience accessor) ──────────────────────────────────

  const totalRow: ComputedRef<AdjudicationRow> = computed(() => {
    const rows = adjudicationRows.value
    return rows.find(r => r.rowKey === 'total') || buildTotalRow([])
  })

  // ─── Trial Balance Diff ────────────────────────────────────────────────

  /**
   * 试算平衡表数（手工优先，其次 render 下发的四表口径）。
   *
   * 🔴 改造前只读 `D2-adj-tb-amount`，而 render 的 `project_context.tb_amount`
   * （`seed_tb_amount_scalars` 按 BS-006 报表行解析后的叶子口径）**零消费方** =
   * dead output ⇒ 未手工录入时该行恒 0、差异行显示为整额假差异。
   * 现按平台既有范式（D1 `tbSeedAmount` / D7 `tbSeedAmount`）加只读回退。
   *
   * spec: d-cycle-four-table-extraction-and-disclosure-completion Task 16
   */
  const trialBalanceAmount: ComputedRef<number> = computed(() =>
    resolveTbAmountWithSeed(getVal('D2-adj-tb-amount').remark, options.tbSeedAmount?.value),
  )

  /** 试算平衡表差异 = 审定数 - 试算表数 */
  const trialBalanceDiff: ComputedRef<{ amount: number; isZero: boolean }> = computed(() => {
    const auditedTotal = totalRow.value.currentAudited
    const diff = auditedTotal - trialBalanceAmount.value
    return { amount: diff, isZero: Math.abs(diff) < 0.005 }
  })

  // ─── Update Cell ───────────────────────────────────────────────────────

  /**
   * 编辑单元格 → 公式重算 → debounce保存
   *
   * @param rowKey - 行标识 (individual/aging/customer-type)
   * @param field - 字段名 (prior-unadjusted/prior-aje/prior-rje/current-unadjusted/current-aje/current-rje/reason)
   * @param value - 新值
   */
  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    if (rowKey === 'total') return // 合计行不可编辑

    const itemId = `D2-adj-${rowKey}-${field}`

    if (field === 'reason') {
      // 文本字段 → debounce保存
      setLocal(itemId, null, String(value))
      debounceSave()
    } else {
      // 金额字段 → 立即保存（触发公式重算）
      setLocal(itemId, null, String(value))
      immediateSave(itemId)
    }
  }

  // ─── Save Logic ────────────────────────────────────────────────────────

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function immediateSave(itemId: string): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    const item = getVal(itemId)
    dispatchSaveEvent([item])
  }

  function flushSave(): void {
    // Collect all D2-adj-* items and dispatch save
    const items: ChecklistItem[] = []
    for (const [key, val] of allResponses.value.entries()) {
      if (key.startsWith('D2-adj-')) {
        items.push(val)
      }
    }
    if (items.length > 0) {
      dispatchSaveEvent(items)
    }
  }

  /**
   * 触发保存事件（通过 CustomEvent，由父组件 useD2FormData 监听处理）
   */
  function dispatchSaveEvent(items: ChecklistItem[]): void {
    try {
      window.dispatchEvent(new CustomEvent('d2:save-items', { detail: { items } }))
    } catch {
      // silent
    }
  }

  // ─── EventBus: Publish Adjudicated ─────────────────────────────────────

  /**
   * 发布 'substantive:adjudicated' 事件
   * payload: wpCode='D2' / accountCode='1122' / auditedAmount / priorAmount / changeRate
   */
  function publishAdjudicated(): void {
    const total = totalRow.value
    const payload: SubstantiveAdjudicatedPayload = {
      wpCode: 'D2',
      accountCode: '1122',
      auditedAmount: total.currentAudited,
      priorAmount: total.priorAudited,
      changeRate: typeof total.changeRate === 'number' ? total.changeRate : null,
    }
    try {
      // 统一走 eventBus（crossWpEventBridge 会带再入守卫转发到 window，旧 window 监听者不受影响）
      eventBus.emit('substantive:adjudicated', payload as any)
    } catch {
      console.warn('[useD2Adjudication] EventBus publish substantive:adjudicated failed')
    }
  }

  // ─── EventBus: Watch audited amount changes → auto publish ─────────────

  // 审定数变化 → 仅发布 substantive:adjudicated（附注/检查表刷新），
  // **不再**自动回写 trial_balance —— TB 回写收敛为用户显式确认动作（publishToTb）。
  // spec: tb-writeback-explicit-publish-gate Req 1（普通保存/数据变化绝不写 TB）。
  watch(
    () => totalRow.value.currentAudited,
    (current) => {
      if (previousAuditedAmount !== null && previousAuditedAmount !== current) {
        publishAdjudicated()
      }
      previousAuditedAmount = current
    }
  )

  // ─── EventBus: Listen 'adjustment:created' ─────────────────────────────

  /**
   * 监听 adjustment:created 事件
   * AJE/RJE → 累计到审定表合计行对应列
   */
  function onAdjustmentCreated(e: Event): void {
    const detail = (e as CustomEvent<AdjustmentCreatedPayload>).detail
    if (!detail || detail.wpCode !== 'D2') return

    // 将AJE/RJE金额累加到合计行
    if (detail.entryType === 'AJE') {
      const current = parseNum(getVal('D2-adj-total-aje').remark)
      setLocal('D2-adj-total-aje', null, String(current + detail.amount))
    } else if (detail.entryType === 'RJE') {
      const current = parseNum(getVal('D2-adj-total-rje').remark)
      setLocal('D2-adj-total-rje', null, String(current + detail.amount))
    }

    debounceSave()
  }

  // ─── EventBus: Listen 'confirmation:completed' ─────────────────────────

  /**
   * 监听 confirmation:completed 事件（D0函证完成 → 更新函证汇总）
   */
  function onConfirmationCompleted(e: Event): void {
    const detail = (e as CustomEvent).detail
    if (!detail) return

    // 存储函证汇总到 allResponses
    setLocal('D2-adj-confirm-summary', null, JSON.stringify({
      sentCount: detail.sentCount,
      receivedCount: detail.receivedCount,
      responseRate: detail.responseRate,
      confirmedAmount: detail.confirmedAmount,
      differenceAmount: detail.differenceAmount,
    }))
  }

  // ─── Publish to Trial Balance（显式发布门，复刻 D4-1 范式） ──────────────

  /**
   * 确认发布审定数到试算表（科目 1122 应收账款）。
   *
   * spec: tb-writeback-explicit-publish-gate Task 2 / Req 2。
   * 此前 D2 靠 totalRow.currentAudited watcher 自动 dispatch
   * `d2:writeback-trial-balance` → 旧端点 `PUT /projects/{pid}/trial-balance/writeback`
   * 直写 audited_amount，**绕过**显式确认门（无二次确认/无幂等/无 publish_confirmed）。
   * 现改为与 D4-1 同范式：二次确认（中文）→ `POST /workpapers/{wpId}/audit-determination/publish-to-tb`
   * （携带审定表 sheet 名 + writeback_rows 预算行），后端校验发布权限、发
   * `publish_confirmed=True` + token → 回写 handler 幂等回写 trial_balance。
   * 普通保存/数据变化对 TB 仍是 no-op（watcher 只 emit substantive:adjudicated）。
   */
  async function publishToTb(): Promise<void> {
    if (readonly.value || publishing.value) return

    // 二次确认（中文，危险操作提示）
    try {
      await ElMessageBox.confirm(
        '发布后将把应收账款审定数（科目 1122）写入试算表（trial_balance），'
        + '并触发报表/错报评价等下游重算。确认发布？',
        '发布到试算表确认',
        {
          confirmButtonText: '确认发布',
          cancelButtonText: '取消',
          type: 'warning',
        },
      )
    } catch {
      return // 用户取消 → 无任何副作用（不写 TB、不 emit）
    }

    if (!wpId.value) {
      ElMessage.error('缺少底稿标识，无法发布')
      return
    }

    // 审定数取合计行 currentAudited（前端已算最终值 → 走 writeback_rows 预算行）
    const auditedAmount = totalRow.value.currentAudited

    publishing.value = true
    try {
      const { api } = await import('@/services/apiProxy')
      const resp: any = await api.post(
        `/api/workpapers/${wpId.value}/audit-determination/publish-to-tb`,
        {
          // sheet 名固定含审定表子码 D2-1，后端 extract_determination_wp_code 据此解出 D2-1
          sheet_name: '审定表D2-1',
          writeback_rows: [
            { account_code: '1122', audited_amount: auditedAmount, amount_kind: 'balance' },
          ],
        },
      )
      ElMessage.success(resp?.message || '已发布到试算表')

      // 发布成功 → 通知下游附注/检查表刷新（TB 回写已由后端确认门完成）
      publishAdjudicated()
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || err?.message || '发布失败，请重试')
    } finally {
      publishing.value = false
    }
  }

  // ─── Change Rate Highlight ─────────────────────────────────────────────

  /**
   * 判断变动率是否超过阈值需高亮
   */
  function isChangeRateWarning(changeRate: number | ''): boolean {
    if (changeRate === '') return false
    return Math.abs(changeRate) > 0.3
  }

  /** D2-2 明细合计 vs D2-1 原值三分类审定合计 */
  const detailCrossValidation = computed((): string | null => {
    const rows = detailRows.value
    if (!rows.length) return null
    const d2_2_total = rows.reduce((s, r) => s + parseNum(r.currentAudited), 0)
    const grossRows = adjudicationRows.value.filter(r => r.rowKey !== 'total')
    const d2_1_total = grossRows.reduce((s, r) => s + r.currentAudited, 0)
    const diff = d2_1_total - d2_2_total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D2-1原值合计(${d2_1_total.toFixed(2)}) 与 D2-2明细合计(${d2_2_total.toFixed(2)}) 差异 ${diff.toFixed(2)}`
    }
    return null
  })

  /** D2-3 坏账准备 vs D2-9 ECL 应计提合计 */
  const eclCrossValidation = computed((): string | null => {
    let bdTotal = 0
    for (const key of ['D2-bd-individual-rows', 'D2-bd-aging-rows', 'D2-bd-customer-rows']) {
      const rows = safeParseRows<{ isFixed?: boolean; currentAudited?: number }>(
        allResponses.value.get(key)?.remark,
      )
      const fixed = rows.find(r => r.isFixed)
      if (fixed) bdTotal += parseNum(fixed.currentAudited)
    }
    if (bdTotal === 0) return null
    const eclRows = safeParseRows<{ shouldProvision?: number }>(
      allResponses.value.get('D2-ecl-single-rows')?.remark,
    )
    if (!eclRows.length) return null
    const eclTotal = eclRows.reduce((s, r) => s + parseNum(r.shouldProvision), 0)
    const diff = bdTotal - eclTotal
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `D2-3坏账准备合计(${bdTotal.toFixed(2)}) 与 D2-9应计提合计(${eclTotal.toFixed(2)}) 差异 ${diff.toFixed(2)}`
    }
    return null
  })

  // ─── EventBus Registration ─────────────────────────────────────────────

  function registerEventListeners(): void {
    const adjustmentHandler = (e: Event) => onAdjustmentCreated(e)
    const confirmHandler = (e: Event) => onConfirmationCompleted(e)

    window.addEventListener('adjustment:created', adjustmentHandler)
    window.addEventListener('confirmation:completed', confirmHandler)

    eventListeners.push(
      { event: 'adjustment:created', handler: adjustmentHandler },
      { event: 'confirmation:completed', handler: confirmHandler },
    )
  }

  function unregisterEventListeners(): void {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
    eventListeners.length = 0
  }

  // Initialize
  registerEventListeners()

  onBeforeUnmount(() => {
    // Flush pending saves
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
    unregisterEventListeners()
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 审定表行数据
    adjudicationRows,
    totalRow,
    trialBalanceAmount,
    trialBalanceDiff,

    // 操作
    updateCell,
    publishAdjudicated,
    publishToTb,
    publishing,
    isChangeRateWarning,
    detailCrossValidation,
    eclCrossValidation,

    // SUMIF状态
    sumifStatus,

    // 明细数据（供其他composable跨sheet引用）
    detailRows,
    sumifAggregation,
  }
}

export default useD2Adjudication
