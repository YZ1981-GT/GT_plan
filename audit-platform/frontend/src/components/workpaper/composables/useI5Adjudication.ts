/**
 * useI5Adjudication — I5-1 其他非流动资产审定表 composable（89行11列61公式）
 *
 * 列结构（11列）：
 *   项目 | 期初 | 本期增加 | 本期减少 | 期末 | 未审 | AJE | RJE | 审定数 | 变动率 | 备注
 *
 * 核心公式：
 *   - 期末 = 期初 + 增加 - 减少（资产类借方科目1911）
 *   - 审定 = 未审 + AJE + RJE
 *   - 三角勾稽差额 = (期初 + 增加 - 减少) - 期末 → 非0红色高亮
 *   - 变动率 = (审定数 - 期初) / 期初 → 期初为0时null
 *
 * TB回写：科目1911其他非流动资产（借方/资产类）
 * 虚拟滚动：89行数据准备
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 3.3
 * Requirements: 2.1-2.7
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from './useI5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（每行对应一个其他非流动资产项目） */
export interface I5AdjudicationRow {
  rowId: string
  /** 项目名称 */
  项目: string
  /** 期初余额 */
  期初: number
  /** 本期增加 */
  增加: number
  /** 本期减少 */
  减少: number
  /** 期末余额（公式列：期初 + 增加 - 减少） */
  期末: number
  /** 未审数 */
  未审: number
  /** AJE调整 */
  AJE: number
  /** RJE重分类 */
  RJE: number
  /** 审定数（公式列：未审 + AJE + RJE） */
  审定: number
  /** 变动率（公式列：(审定-期初)/期初） */
  变动率: number | null
  /** 备注 */
  备注: string
  /** 三角勾稽差额 */
  差额: number
  /** 是否存在勾稽差异（红色高亮标记） */
  hasError: boolean
  /** 可编辑标记 */
  isEditable?: boolean
  /** 小计行标记 */
  isSubtotal?: boolean
}

/** TB差异行 */
export interface I5DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

/** ChecklistItem 类型 */
export interface I5ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'I5-adj'
const ACCOUNT_CODE_1911 = '1911'

/** 默认其他非流动资产分类（89行中的典型项目） */
const DEFAULT_CATEGORIES = [
  '预付购房款',
  '预付设备款',
  '待抵扣进项税额',
  '合同资产-非流动',
  '其他',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, I5ChecklistItem>>,
  options?: {
    /** TB未审数据（科目1911） */
    tbUnadjusted1911?: Ref<number>
    /** TB审定数据（科目1911） */
    tbAudited1911?: Ref<number>
    /** 跨sheet明细联动（来自I5-2明细表合计） */
    crossSheetDetailTotal?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 审定表数据行（动态，每个其他非流动资产项目一行） */
  const rows = ref<I5AdjudicationRow[]>([])
  /** 审计说明 */
  const auditNote = ref('')
  /** 审计结论 */
  const auditConclusion = ref('')

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadRows(): void {
    const data = _getJson(`${ITEM_PREFIX}-rows`)
    if (Array.isArray(data) && data.length > 0) {
      rows.value = data.map(_normalizeRow)
    } else {
      rows.value = _buildDefaultRows()
    }
    auditNote.value = _getString(`${ITEM_PREFIX}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX}-audit-conclusion`)
  }

  function _getJson(itemId: string): any {
    const item = allResponses.value.get(itemId)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (!raw) return null
    try { return JSON.parse(raw) } catch { return null }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeRow(raw: any): I5AdjudicationRow {
    const 期初 = Number(raw.期初) || 0
    const 增加 = Number(raw.增加) || 0
    const 减少 = Number(raw.减少) || 0
    const 期末 = calcAssetEndBalance(期初, 增加, 减少)
    const 未审 = Number(raw.未审) || 0
    const AJE = Number(raw.AJE) || 0
    const RJE = Number(raw.RJE) || 0
    const 审定 = calcAuditedAmount(未审, AJE, RJE)
    const 差额 = calcTriangleReconciliation(期初, 增加, 减少, 期末)
    const 变动率 = calcChangeRate(审定, 期初)

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      项目: raw.项目 ?? '',
      期初,
      增加,
      减少,
      期末,
      未审,
      AJE,
      RJE,
      审定,
      变动率,
      备注: raw.备注 ?? '',
      差额,
      hasError: Math.abs(差额) > 0.01,
      isEditable: raw.isEditable ?? true,
      isSubtotal: raw.isSubtotal ?? false,
    }
  }

  function _buildDefaultRows(): I5AdjudicationRow[] {
    return DEFAULT_CATEGORIES.map((cat) => ({
      rowId: `row-${cat}`,
      项目: cat,
      期初: 0,
      增加: 0,
      减少: 0,
      期末: 0,
      未审: 0,
      AJE: 0,
      RJE: 0,
      审定: 0,
      变动率: null,
      备注: '',
      差额: 0,
      hasError: false,
      isEditable: true,
      isSubtotal: false,
    }))
  }

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotals = computed<I5AdjudicationRow>(() => {
    const detail = rows.value.filter((r) => !r.isSubtotal)
    const 期初 = calcSubtotal(detail.map((r) => r.期初))
    const 增加 = calcSubtotal(detail.map((r) => r.增加))
    const 减少 = calcSubtotal(detail.map((r) => r.减少))
    const 期末 = calcAssetEndBalance(期初, 增加, 减少)
    const 未审 = calcSubtotal(detail.map((r) => r.未审))
    const AJE = calcSubtotal(detail.map((r) => r.AJE))
    const RJE = calcSubtotal(detail.map((r) => r.RJE))
    const 审定 = calcAuditedAmount(未审, AJE, RJE)
    const 差额 = calcTriangleReconciliation(期初, 增加, 减少, 期末)
    const 变动率 = calcChangeRate(审定, 期初)

    return {
      rowId: 'row-subtotal',
      项目: '合计',
      期初,
      增加,
      减少,
      期末,
      未审,
      AJE,
      RJE,
      审定,
      变动率,
      备注: '',
      差额,
      hasError: Math.abs(差额) > 0.01,
      isEditable: false,
      isSubtotal: true,
    }
  })

  // ─── Computed: 带公式列的完整行 ───────────────────────────────────────────

  const computedRows: ComputedRef<I5AdjudicationRow[]> = computed(() => {
    return rows.value.map((row) => {
      const 期末 = calcAssetEndBalance(row.期初, row.增加, row.减少)
      const 审定 = calcAuditedAmount(row.未审, row.AJE, row.RJE)
      const 差额 = calcTriangleReconciliation(row.期初, row.增加, row.减少, 期末)
      const 变动率 = calcChangeRate(审定, row.期初)
      return {
        ...row,
        期末,
        审定,
        变动率,
        差额,
        hasError: Math.abs(差额) > 0.01,
      }
    })
  })

  /** 三角勾稽全局状态：balanced | mismatch */
  const reconciliationStatus: ComputedRef<'balanced' | 'mismatch'> = computed(() => {
    const allRows = computedRows.value
    const hasAnyError = allRows.some((r) => r.hasError)
    return hasAnyError ? 'mismatch' : 'balanced'
  })

  // ─── Computed: TB取数 + 差异 ──────────────────────────────────────────────

  /** TB未审数据（科目1911） */
  const tbUnadjusted: ComputedRef<number> = computed(() => {
    return options?.tbUnadjusted1911?.value ?? 0
  })

  /** TB差异 = 审定合计 - TB未审 */
  const tbDifference: ComputedRef<number> = computed(() => {
    return subtotals.value.审定 - tbUnadjusted.value
  })

  /** 差异行（展示用） */
  const differenceRows = computed<I5DifferenceRow[]>(() => {
    const tbAmount = options?.tbUnadjusted1911?.value ?? 0
    const auditedTotal = subtotals.value.审定
    return [
      {
        label: '其他非流动资产(1911)',
        accountCode: ACCOUNT_CODE_1911,
        audited: auditedTotal,
        tbAmount,
        difference: auditedTotal - tbAmount,
      },
    ]
  })

  // ─── Computed: 虚拟滚动数据准备（89行）────────────────────────────────────

  /** 包含合计行的完整列表（供虚拟滚动渲染） */
  const virtualScrollData: ComputedRef<I5AdjudicationRow[]> = computed(() => {
    return [...computedRows.value, subtotals.value]
  })

  // ─── Actions: 动态行 ──────────────────────────────────────────────────────

  /**
   * 新增行：弹 ElMessageBox 输入项目名称后创建
   */
  async function addRow(): Promise<void> {
    try {
      const { value: projectName } = await ElMessageBox.prompt(
        '请输入其他非流动资产项目名称',
        '新增项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '项目名称不能为空',
        },
      )
      if (!projectName) return

      const newRow: I5AdjudicationRow = {
        rowId: `row-${Date.now().toString(36)}`,
        项目: projectName.trim(),
        期初: 0,
        增加: 0,
        减少: 0,
        期末: 0,
        未审: 0,
        AJE: 0,
        RJE: 0,
        审定: 0,
        变动率: null,
        备注: '',
        差额: 0,
        hasError: false,
        isEditable: true,
        isSubtotal: false,
      }
      rows.value.push(newRow)
      _persist()
      ElMessage.success(`已添加：${projectName}`)
    } catch {
      // 用户取消
    }
  }

  /**
   * 删除行（按rowId移除）
   */
  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      const removed = rows.value.splice(idx, 1)[0]
      _persist()
      ElMessage.info(`已删除：${removed.项目}`)
    }
  }

  // ─── Actions: 更新单元格 ──────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列（期末、审定、变动率、差额、hasError）
   */
  function updateCell(
    rowId: string,
    field: keyof I5AdjudicationRow,
    value: number | string,
  ): void {
    const row = rows.value.find((r) => r.rowId === rowId)
    if (!row || !row.isEditable) return

    ;(row as any)[field] = value

    // 自动重算公式列
    row.期末 = calcAssetEndBalance(row.期初, row.增加, row.减少)
    row.审定 = calcAuditedAmount(row.未审, row.AJE, row.RJE)
    row.差额 = calcTriangleReconciliation(row.期初, row.增加, row.减少, row.期末)
    row.变动率 = calcChangeRate(row.审定, row.期初)
    row.hasError = Math.abs(row.差额) > 0.01

    _persist()
  }

  // ─── Actions: TB取数接入 ──────────────────────────────────────────────────

  /**
   * 接收TB未审数据，写入行的 未审 字段
   * 如果只有1行，直接写入该行；多行按期初余额比例分配
   */
  function applyTbData(tbUnadjustedTotal: number): void {
    if (rows.value.length === 1) {
      rows.value[0].未审 = tbUnadjustedTotal
      rows.value[0].审定 = calcAuditedAmount(rows.value[0].未审, rows.value[0].AJE, rows.value[0].RJE)
      rows.value[0].变动率 = calcChangeRate(rows.value[0].审定, rows.value[0].期初)
    } else if (rows.value.length > 1) {
      const totalBegin = calcSubtotal(rows.value.map((r) => r.期初))
      if (totalBegin > 0) {
        for (const row of rows.value) {
          const ratio = row.期初 / totalBegin
          row.未审 = Math.round(ratio * tbUnadjustedTotal * 100) / 100
          row.审定 = calcAuditedAmount(row.未审, row.AJE, row.RJE)
          row.变动率 = calcChangeRate(row.审定, row.期初)
        }
      }
    }
    _persist()
  }

  /**
   * 接收 AJE/RJE 调整（来自 I5-3 调整分录表）
   * 按项目名称匹配写入对应行
   */
  function applyAdjustments(adjustments: { 项目: string; AJE: number; RJE: number }[]): void {
    for (const adj of adjustments) {
      const row = rows.value.find((r) => r.项目 === adj.项目)
      if (row) {
        row.AJE = adj.AJE
        row.RJE = adj.RJE
        row.审定 = calcAuditedAmount(row.未审, row.AJE, row.RJE)
        row.变动率 = calcChangeRate(row.审定, row.期初)
      }
    }
    _persist()
  }

  // ─── Actions: TB回写（writebackTB 1911） ──────────────────────────────────

  /**
   * 回写审定数到 trial_balance（科目1911）
   * 1. 持久化行数据到 checklist_responses
   * 2. writebackTrialBalance（科目1911）
   * 3. 发布 'substantive:adjudicated' EventBus事件
   */
  async function writeback(): Promise<void> {
    _persist()

    const auditedTotal = subtotals.value.审定

    // 持久化审定合计（独立item_id，供render策略回读seed + 跨session持久化）
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)

    // TB回写（科目1911）
    if (projectId.value) {
      try {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_1911,
          audited_amount: auditedTotal,
        })
        ElMessage.success('审定数已回写试算表(1911)')
      } catch {
        ElMessage.warning('审定数回写试算表失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus 事件
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I5',
        accountCodes: [ACCOUNT_CODE_1911],
        auditedTotal,
      },
    }))
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-rows`, rows.value.filter((r) => !r.isSubtotal))
  }

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX}-audit-conclusion`, conclusion)
  }

  // ─── Init ──────────────────────────────────────────────────────────────────

  watch(allResponses, () => _loadRows(), { immediate: true })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // State
    rows: computedRows,
    auditNote,
    auditConclusion,
    // Computed — 合计
    subtotals,
    // Computed — TB
    tbUnadjusted,
    tbDifference,
    // Computed — 勾稽状态
    reconciliationStatus,
    // Computed — 差异行
    differenceRows,
    // Computed — 虚拟滚动
    virtualScrollData,
    // Actions — 动态行
    addRow,
    removeRow,
    // Actions — 数据接入
    updateCell,
    applyTbData,
    applyAdjustments,
    // Actions — TB回写
    writeback,
    // Actions — 保存
    saveNote,
    saveConclusion,
  }
}

export default useI5Adjudication
