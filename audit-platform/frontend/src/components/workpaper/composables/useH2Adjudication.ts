/**
 * useH2Adjudication — H2-1 审定表 composable
 *
 * 审定表结构（以xlsx为准，12列分组）：
 * 项目 | 期初数{未审数, 账项调整, 审定数} | 期末数{未审数, 账项调整, 审定数}
 * | 本期未审比较{变动额, 变动率} | 本期审定比较{变动额, 变动率}
 *
 * 功能：
 * - 固定行（各工程项目+小计+合计）
 * - 审定=未审+账项调整（期初/期末各一组）
 * - 三角勾稽校验通过H2-2跨sheet数据：期末=期初+增加-减少-转固
 * - TB取数行 + 差异行
 * - 交叉验证H2-2明细合计 + H2-5转固合计
 * - updateCell + publishAdjudicated（EventBus → TB回写）
 *
 * 冲突解决（h2_conflict_resolution.md）：
 * - H2-1按xlsx 12列结构，不含"增加/减少/转固"列
 * - 三角勾稽在H2-2上实施，H2-1仅通过crossSheet展示差异警告
 * - "账项调整"保持单列展示（内部可拆分AJE/RJE录入后合计）
 *
 * Spec: .kiro/specs/h2-construction-in-progress/
 * Task: 3.3
 * Requirements: 2.1-2.12
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import {
  calcSubtotal,
  calcTriangleWithTransfer,
} from './useH2FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/**
 * H2-1 审定表行（按xlsx 12列分组结构）
 *
 * 期初数组：未审数、账项调整、审定数
 * 期末数组：未审数、账项调整、审定数
 * 同期比较：变动额、变动率（未审/审定各一组）
 */
export interface H2AdjudicationRow {
  rowId: string
  /** 项目名称（工程名称） */
  name: string
  /** 期初-未审数 */
  beginUnadjusted: number
  /** 期初-账项调整（=AJE+RJE合并列） */
  beginAdjustment: number
  /** 期初-审定数（公式列：=未审+调整） */
  beginAudited: number
  /** 期末-未审数 */
  endUnadjusted: number
  /** 期末-账项调整（=AJE+RJE合并列） */
  endAdjustment: number
  /** 期末-审定数（公式列：=未审+调整） */
  endAudited: number
  /** 本期未审变动额（公式列：=期末未审-期初未审） */
  unadjustedChange: number
  /** 本期未审变动率（公式列） */
  unadjustedChangeRate: number | null
  /** 本期审定变动额（公式列：=期末审定-期初审定） */
  auditedChange: number
  /** 本期审定变动率（公式列） */
  auditedChangeRate: number | null
  /** 行类型标记 */
  isSubtotal?: boolean
  isTotal?: boolean
  isEditable?: boolean
}

/** TB取数对比行 */
export interface TbComparisonRow {
  /** TB科目1604未审数 */
  tbUnadjusted: number
  /** TB科目1604审定数 */
  tbAudited: number
}

/** 差异行 */
export interface DiffRow {
  /** 审定数合计 - TB审定数 */
  amount: number
  /** 差异是否为零 */
  isZero: boolean
}

/** 三角勾稽校验错误（来自H2-2跨sheet数据） */
export interface TriangleError {
  rowId: string
  name: string
  diff: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'H2-1'
const ROWS_KEY = 'H2-1-rows'
const NOTE_KEY = 'H2-1-audit-note'
const CONCLUSION_KEY = 'H2-1-audit-conclusion'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2Adjudication(options: {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
  /** TB取数数据（科目1604） */
  tbData?: Ref<{ unadjusted_amount: number; audited_amount: number }>
  /** H2-2明细合计（从useH2CrossSheet.detailTotals取） */
  detailTotals?: ComputedRef<{ cipEnd: number; increase: number; decrease: number; transfer: number }>
  /** H2-5转固合计（从useH2CrossSheet.transferSummary取） */
  transferSummary?: ComputedRef<{ totalTransfer: number; items: Array<{ name: string; amount: number }> }>
  /** 保存回调（调用useH2FormData.setValue） */
  onSave?: (itemId: string, value: any) => void
  /** TB回写回调（调用useH2FormData.writebackTrialBalance） */
  onWritebackTB?: (auditedAmount: number) => Promise<void>
  /** EventBus发布回调 */
  onPublishEvent?: (event: string, payload: any) => void
}) {
  // ─── State ─────────────────────────────────────────────────────────────────

  const rows = ref<H2AdjudicationRow[]>([])
  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Helpers ───────────────────────────────────────────────────────────────

  function _getJson(itemId: string): any {
    const item = options.allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = options.allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _calcChangeRate(current: number, previous: number): number | null {
    if (previous === 0 && current === 0) return 0
    if (previous === 0 && current !== 0) return null // 无穷大，不展示
    return ((current - previous) / Math.abs(previous)) * 100
  }

  /** 规范化行数据（从持久化JSON加载） */
  function _normalizeRow(raw: any): H2AdjudicationRow {
    const beginUnadj = Number(raw.beginUnadjusted) || 0
    const beginAdj = Number(raw.beginAdjustment) || 0
    const endUnadj = Number(raw.endUnadjusted) || 0
    const endAdj = Number(raw.endAdjustment) || 0

    const beginAudited = beginUnadj + beginAdj
    const endAudited = endUnadj + endAdj

    const unadjChange = endUnadj - beginUnadj
    const auditedChange = endAudited - beginAudited

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      name: raw.name ?? '',
      beginUnadjusted: beginUnadj,
      beginAdjustment: beginAdj,
      beginAudited,
      endUnadjusted: endUnadj,
      endAdjustment: endAdj,
      endAudited,
      unadjustedChange: unadjChange,
      unadjustedChangeRate: _calcChangeRate(endUnadj, beginUnadj),
      auditedChange,
      auditedChangeRate: _calcChangeRate(endAudited, beginAudited),
      isSubtotal: raw.isSubtotal ?? false,
      isTotal: raw.isTotal ?? false,
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Init / Load ───────────────────────────────────────────────────────────

  function initFromAllResponses(): void {
    const data = _getJson(ROWS_KEY)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      // 默认空白（用户通过添加工程项目填充）
      rows.value = []
    }
    auditNote.value = _getString(NOTE_KEY)
    auditConclusion.value = _getString(CONCLUSION_KEY)
  }

  // Watch allResponses for reloads（如selfLoad完成后触发重新加载）
  watch(options.allResponses, () => initFromAllResponses(), { immediate: true })

  // ─── Computed: 合计行（含所有工程项目行SUM） ───────────────────────────────

  /** 明细行（排除小计/合计标记行） */
  const detailRows = computed<H2AdjudicationRow[]>(() =>
    rows.value.filter(r => !r.isSubtotal && !r.isTotal),
  )

  /** 合计行（自动SUM所有工程项目行各金额列） */
  const totalRow: ComputedRef<H2AdjudicationRow> = computed(() => {
    const dr = detailRows.value
    const beginUnadj = calcSubtotal(dr.map(r => r.beginUnadjusted))
    const beginAdj = calcSubtotal(dr.map(r => r.beginAdjustment))
    const endUnadj = calcSubtotal(dr.map(r => r.endUnadjusted))
    const endAdj = calcSubtotal(dr.map(r => r.endAdjustment))

    const beginAudited = beginUnadj + beginAdj
    const endAudited = endUnadj + endAdj
    const unadjChange = endUnadj - beginUnadj
    const auditedChange = endAudited - beginAudited

    return {
      rowId: 'row-total',
      name: '合计',
      beginUnadjusted: beginUnadj,
      beginAdjustment: beginAdj,
      beginAudited,
      endUnadjusted: endUnadj,
      endAdjustment: endAdj,
      endAudited,
      unadjustedChange: unadjChange,
      unadjustedChangeRate: _calcChangeRate(endUnadj, beginUnadj),
      auditedChange,
      auditedChangeRate: _calcChangeRate(endAudited, beginAudited),
      isSubtotal: false,
      isTotal: true,
      isEditable: false,
    }
  })

  // ─── Computed: TB取数行 ────────────────────────────────────────────────────

  /** TB科目1604取数行 */
  const tbRow: ComputedRef<TbComparisonRow> = computed(() => {
    const tb = options.tbData?.value
    return {
      tbUnadjusted: tb?.unadjusted_amount ?? 0,
      tbAudited: tb?.audited_amount ?? 0,
    }
  })

  // ─── Computed: 差异行 ──────────────────────────────────────────────────────

  /** 差异 = 期末审定数合计 - TB审定数 */
  const diffRow: ComputedRef<DiffRow> = computed(() => {
    const auditedTotal = totalRow.value.endAudited
    const tbAudited = tbRow.value.tbAudited
    const amount = auditedTotal - tbAudited
    return {
      amount,
      isZero: Math.abs(amount) < 0.01,
    }
  })

  // ─── Computed: 交叉验证H2-2（审定数合计 vs 明细合计期末余额）──────────────

  /**
   * Req 2.8: 审定数合计与H2-2合计行不一致时显示黄色警告
   * detailDiff = 期末审定合计 - H2-2期末余额合计
   */
  const detailDiff: ComputedRef<number> = computed(() => {
    const auditedTotal = totalRow.value.endAudited
    const h2_2_cipEnd = options.detailTotals?.value?.cipEnd ?? 0
    return auditedTotal - h2_2_cipEnd
  })

  // ─── Computed: 交叉验证H2-5（转固合计）────────────────────────────────────

  /**
   * Req 2.9: "本期转固"合计与H2-5转固合计不一致时显示黄色警告
   * 注：H2-1本身不显示转固列（xlsx实际结构），但从H2-2的转固数据与H2-5交叉验证
   * transferDiff = H2-2转固合计 - H2-5转固合计
   */
  const transferDiff: ComputedRef<number> = computed(() => {
    const h2_2_transfer = options.detailTotals?.value?.transfer ?? 0
    const h2_5_transfer = options.transferSummary?.value?.totalTransfer ?? 0
    return h2_2_transfer - h2_5_transfer
  })

  // ─── Computed: 三角勾稽校验（从H2-2跨sheet数据驱动） ──────────────────────

  /**
   * Req 2.6: 三角勾稽校验 (期末=期初+增加-减少-转固)
   * 冲突解决：三角勾稽在H2-2上实施，H2-1通过crossSheet展示per-project差异。
   * 此处读取H2-2的各工程项目行数据计算三角勾稽错误列表。
   */
  const triangleErrors: ComputedRef<TriangleError[]> = computed(() => {
    // 从 allResponses 读取 H2-2 行数据
    const resp = options.allResponses.value.get('H2-2-rows')
    const raw = resp?.remark ?? resp?.conclusion
    if (!raw) return []

    let h2Rows: any[]
    try {
      h2Rows = JSON.parse(raw)
      if (!Array.isArray(h2Rows)) return []
    } catch {
      return []
    }

    const errors: TriangleError[] = []
    for (const row of h2Rows) {
      const begin = Number(row.cipBegin) || 0
      const increaseTotal = Number(row.increaseTotal) ||
        ((Number(row.increaseMaterial) || 0) + (Number(row.increaseLabor) || 0) +
         (Number(row.increaseMachinery) || 0) + (Number(row.increaseInterest) || 0) +
         (Number(row.increaseOther) || 0))
      const decrease = Number(row.decrease) || 0
      const transfer = Number(row.transferAmount) || 0
      const end = Number(row.cipEnd) || 0

      const diff = calcTriangleWithTransfer(begin, increaseTotal, decrease, transfer, end)
      if (Math.abs(diff) > 0.01) {
        errors.push({
          rowId: row.rowId ?? '',
          name: row.name ?? '未命名工程',
          diff,
        })
      }
    }
    return errors
  })

  // ─── Actions: updateCell ───────────────────────────────────────────────────

  /**
   * 更新指定行的指定字段值。
   * 自动重算公式列（审定数=未审+调整，变动额/变动率）。
   * Req 2.3: 编辑未审数/账项调整时自动计算审定数
   */
  function updateCell(rowId: string, field: string, value: any): void {
    if (options.isReadonly.value) return

    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || row.isTotal) return

    const numVal = Number(value) || 0

    // 设置字段值
    switch (field) {
      case 'name':
        row.name = String(value ?? '')
        break
      case 'beginUnadjusted':
        row.beginUnadjusted = numVal
        break
      case 'beginAdjustment':
        row.beginAdjustment = numVal
        break
      case 'endUnadjusted':
        row.endUnadjusted = numVal
        break
      case 'endAdjustment':
        row.endAdjustment = numVal
        break
      default:
        return // 不支持直接修改公式列
    }

    // 重算公式列
    row.beginAudited = row.beginUnadjusted + row.beginAdjustment
    row.endAudited = row.endUnadjusted + row.endAdjustment
    row.unadjustedChange = row.endUnadjusted - row.beginUnadjusted
    row.unadjustedChangeRate = _calcChangeRate(row.endUnadjusted, row.beginUnadjusted)
    row.auditedChange = row.endAudited - row.beginAudited
    row.auditedChangeRate = _calcChangeRate(row.endAudited, row.beginAudited)

    _persist()
  }

  // ─── Actions: addProjectRow ────────────────────────────────────────────────

  /**
   * 新增工程项目行。
   * Req 2.1: 按工程项目分行（行数动态）
   * 交互：需先弹ElMessageBox.prompt输入名称（由Vue组件层处理）
   */
  function addProjectRow(name: string): void {
    if (options.isReadonly.value) return
    if (!name || !name.trim()) return

    const newRow: H2AdjudicationRow = {
      rowId: `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
      name: name.trim(),
      beginUnadjusted: 0,
      beginAdjustment: 0,
      beginAudited: 0,
      endUnadjusted: 0,
      endAdjustment: 0,
      endAudited: 0,
      unadjustedChange: 0,
      unadjustedChangeRate: 0,
      auditedChange: 0,
      auditedChangeRate: 0,
      isSubtotal: false,
      isTotal: false,
      isEditable: true,
    }

    rows.value.push(newRow)
    _persist()
  }

  // ─── Actions: removeProjectRow ─────────────────────────────────────────────

  /**
   * 删除指定工程项目行。
   * 合计/小计行不可删除。
   */
  function removeProjectRow(rowId: string): void {
    if (options.isReadonly.value) return

    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = rows.value[idx]
    if (row.isTotal || row.isSubtotal) return

    rows.value.splice(idx, 1)
    _persist()
  }

  // ─── Actions: publishAdjudicated (EventBus + TB回写) ───────────────────────

  /**
   * Req 2.11: 审定数变化时回写TB并发布EventBus事件。
   * 调用 useH2FormData.writebackTrialBalance + 发布 'substantive:adjudicated'
   */
  async function publishAdjudicated(): Promise<void> {
    const auditedTotal = totalRow.value.endAudited

    // TB回写（科目1604在建工程）
    if (options.onWritebackTB) {
      await options.onWritebackTB(auditedTotal)
    }

    // EventBus发布
    if (options.onPublishEvent) {
      options.onPublishEvent('substantive:adjudicated', {
        wp_code: 'H2',
        account_codes: ['1604'],
        audited_amount: auditedTotal,
        begin_audited: totalRow.value.beginAudited,
        end_audited: auditedTotal,
      })
    }
  }

  // ─── Actions: saveNote / saveConclusion ────────────────────────────────────

  function saveNote(note: string): void {
    auditNote.value = note
    options.onSave?.(NOTE_KEY, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options.onSave?.(CONCLUSION_KEY, conclusion)
  }

  // ─── Persist (rows → allResponses) ─────────────────────────────────────────

  function _persist(): void {
    if (!options.onSave) return
    // 仅持久化明细行（排除合计行——运行时computed动态计算）
    const toPersist = rows.value
      .filter(r => !r.isTotal)
      .map(r => ({
        rowId: r.rowId,
        name: r.name,
        beginUnadjusted: r.beginUnadjusted,
        beginAdjustment: r.beginAdjustment,
        endUnadjusted: r.endUnadjusted,
        endAdjustment: r.endAdjustment,
        isSubtotal: r.isSubtotal || undefined,
        isEditable: r.isEditable,
      }))
    options.onSave(ROWS_KEY, toPersist)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows,
    auditNote,
    auditConclusion,

    // Computed — 明细行（排除标记行）
    detailRows,

    // Computed — 合计行
    totalRow,

    // Computed — TB取数行
    tbRow,

    // Computed — 差异行
    diffRow,

    // Computed — 交叉验证
    detailDiff,       // 审定数合计 vs H2-2明细合计（Req 2.8）
    transferDiff,     // H2-2转固合计 vs H2-5转固合计（Req 2.9）
    triangleErrors,   // 三角勾稽校验错误列表（来自H2-2 per-project，Req 2.6）

    // Actions
    updateCell,
    addProjectRow,
    removeProjectRow,
    publishAdjudicated,
    saveNote,
    saveConclusion,

    // Init (外部可显式调用)
    initFromAllResponses,
  }
}

export default useH2Adjudication
