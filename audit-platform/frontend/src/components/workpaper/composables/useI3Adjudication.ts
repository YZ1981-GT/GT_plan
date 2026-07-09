/**
 * useI3Adjudication — I3 商誉审定表 composable（商誉不摊销！）
 *
 * 列结构（13列）：
 *   被投资单位 | 初始确认 | 期初余额 | 本期增加(新并购) | 本期减少(减值)
 *   | 期末余额 | 未审数 | AJE | RJE | 审定数 | 减值准备 | 净额
 *
 * 核心公式：
 *   - 期末 = 期初 + 新并购(通常0) - 减值  (商誉不摊销！)
 *   - 审定 = 未审 + AJE + RJE
 *   - 净额 = 商誉原值(初始确认) - 累计减值
 *   - 商誉减值不可转回！
 *   - "本期增加"仅来自新并购（正常为0），非零时黄色提示
 *
 * TB回写：科目1711商誉（借方/资产类）
 *
 * Spec: .kiro/specs/i3-goodwill/
 * Task: 3.3
 * Requirements: 2.1-2.8
 */
import { ref, computed, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import {
  calcAuditedAmount,
  calcGoodwillEndBalance,
  calcGoodwillNetValue,
  calcSubtotal,
} from './useI3FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表行（每行对应一个被投资单位） */
export interface I3AdjudicationRow {
  rowId: string
  /** 被投资单位名称 */
  investee: string
  /** 初始确认金额（商誉原值） */
  initialRecognition: number
  /** 期初余额 */
  beginBalance: number
  /** 本期增加（仅新并购） */
  newAcquisition: number
  /** 本期减少（仅减值，不可转回） */
  impairment: number
  /** 期末余额（公式列：期初 + 新并购 - 减值） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE重分类 */
  rje: number
  /** 审定数（公式列：未审 + AJE + RJE） */
  audited: number
  /** 累计减值准备 */
  accImpairment: number
  /** 净额（公式列：初始确认 - 累计减值） */
  netValue: number
  /** 可编辑标记 */
  isEditable?: boolean
}

/** 警告消息 */
export interface I3Warning {
  rowId: string
  investee: string
  type: 'newAcquisition' | 'impairmentReversal'
  message: string
}

/** TB差异行 */
export interface I3DifferenceRow {
  label: string
  accountCode: string
  audited: number
  tbAmount: number
  difference: number
}

/** ChecklistItem 类型（与 useI3FormData 对齐） */
export interface I3ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX = 'I3-adj'
const ACCOUNT_CODE_1711 = '1711'

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3Adjudication(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, I3ChecklistItem>>,
  options?: {
    /** TB未审数据 */
    tbUnadjusted1711?: Ref<number>
    /** TB审定数据 */
    tbAudited1711?: Ref<number>
    /** 跨sheet减值联动（来自I3-6） */
    crossSheetImpairment?: Ref<number>
    /** 保存回调 */
    onSave?: (itemId: string, value: any) => void
  },
) {
  // ─── State ─────────────────────────────────────────────────────────────────

  /** 审定表数据行（动态，每个被投资单位一行） */
  const rows = ref<I3AdjudicationRow[]>([])
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
      rows.value = []
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

  function _normalizeRow(raw: any): I3AdjudicationRow {
    const beginBalance = Number(raw.beginBalance) || 0
    const newAcquisition = Number(raw.newAcquisition) || 0
    const impairment = Number(raw.impairment) || 0
    const initialRecognition = Number(raw.initialRecognition) || 0
    const accImpairment = Number(raw.accImpairment) || 0
    const unadjusted = Number(raw.unadjusted) || 0
    const aje = Number(raw.aje) || 0
    const rje = Number(raw.rje) || 0

    return {
      rowId: raw.rowId ?? `row-${Math.random().toString(36).slice(2, 10)}`,
      investee: raw.investee ?? '',
      initialRecognition,
      beginBalance,
      newAcquisition,
      impairment,
      endBalance: calcGoodwillEndBalance(beginBalance, newAcquisition, impairment),
      unadjusted,
      aje,
      rje,
      audited: calcAuditedAmount(unadjusted, aje, rje),
      accImpairment,
      netValue: calcGoodwillNetValue(initialRecognition, accImpairment),
      isEditable: raw.isEditable ?? true,
    }
  }

  // ─── Computed: 合计行 ──────────────────────────────────────────────────────

  const subtotals = computed<I3AdjudicationRow>(() => {
    const detail = rows.value
    return {
      rowId: 'row-subtotal',
      investee: '合计',
      initialRecognition: calcSubtotal(detail.map(r => r.initialRecognition)),
      beginBalance: calcSubtotal(detail.map(r => r.beginBalance)),
      newAcquisition: calcSubtotal(detail.map(r => r.newAcquisition)),
      impairment: calcSubtotal(detail.map(r => r.impairment)),
      endBalance: calcSubtotal(detail.map(r => r.endBalance)),
      unadjusted: calcSubtotal(detail.map(r => r.unadjusted)),
      aje: calcSubtotal(detail.map(r => r.aje)),
      rje: calcSubtotal(detail.map(r => r.rje)),
      audited: calcSubtotal(detail.map(r => r.audited)),
      accImpairment: calcSubtotal(detail.map(r => r.accImpairment)),
      netValue: calcSubtotal(detail.map(r => r.netValue)),
      isEditable: false,
    }
  })

  // ─── Computed: 警告 ────────────────────────────────────────────────────────

  /**
   * 获取警告列表：
   * - "本期增加"非零 → 黄色提示（正常年份商誉无新增，除非新并购）
   * - "本期减少"为负（尝试转回） → 红色阻止
   */
  const warnings = computed<I3Warning[]>(() => {
    const result: I3Warning[] = []
    for (const row of rows.value) {
      if (row.newAcquisition !== 0) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 'newAcquisition',
          message: `${row.investee || '未命名'}：本期增加非零（${row.newAcquisition}），请确认是否有新并购交易`,
        })
      }
      if (row.impairment < 0) {
        result.push({
          rowId: row.rowId,
          investee: row.investee,
          type: 'impairmentReversal',
          message: `${row.investee || '未命名'}：商誉减值不可转回！本期减少不能为负数`,
        })
      }
    }
    return result
  })

  /** 便捷方法：获取警告消息数组（兼容模板直接使用） */
  function getWarnings(): I3Warning[] {
    return warnings.value
  }

  // ─── Computed: TB差异 ──────────────────────────────────────────────────────

  const tbRow = computed(() => ({
    unadjusted: options?.tbUnadjusted1711?.value ?? 0,
    audited: options?.tbAudited1711?.value ?? 0,
  }))

  const differenceRows = computed<I3DifferenceRow[]>(() => {
    const tbUnadj = options?.tbUnadjusted1711?.value ?? 0
    const auditedTotal = subtotals.value.audited
    return [
      {
        label: '商誉(1711)',
        accountCode: ACCOUNT_CODE_1711,
        audited: auditedTotal,
        tbAmount: tbUnadj,
        difference: auditedTotal - tbUnadj,
      },
    ]
  })

  // ─── Actions: 动态行 ──────────────────────────────────────────────────────

  /**
   * 新增行：弹 ElMessageBox 输入被投资单位名称后创建
   * 商誉审定表是动态行（按被投资单位维度）
   */
  async function addRow(): Promise<void> {
    try {
      const { value: investeeName } = await ElMessageBox.prompt(
        '请输入被投资单位名称',
        '新增商誉项目',
        {
          confirmButtonText: '确定',
          cancelButtonText: '取消',
          inputPattern: /\S+/,
          inputErrorMessage: '被投资单位名称不能为空',
        },
      )
      if (!investeeName) return

      const newRow: I3AdjudicationRow = {
        rowId: `row-${Date.now().toString(36)}`,
        investee: investeeName.trim(),
        initialRecognition: 0,
        beginBalance: 0,
        newAcquisition: 0,
        impairment: 0,
        endBalance: 0,
        unadjusted: 0,
        aje: 0,
        rje: 0,
        audited: 0,
        accImpairment: 0,
        netValue: 0,
        isEditable: true,
      }
      rows.value.push(newRow)
      _persist()
      ElMessage.success(`已添加：${investeeName}`)
    } catch {
      // 用户取消
    }
  }

  /**
   * 删除行（按rowId移除）
   */
  function removeRow(rowId: string): void {
    const idx = rows.value.findIndex(r => r.rowId === rowId)
    if (idx >= 0) {
      const removed = rows.value.splice(idx, 1)[0]
      _persist()
      ElMessage.info(`已删除：${removed.investee}`)
    }
  }

  // ─── Actions: 更新单元格 ──────────────────────────────────────────────────

  /**
   * 更新审定表某行某列值，自动重算公式列。
   * 公式列自动计算：endBalance / audited / netValue
   */
  function updateCell(
    rowId: string,
    field: keyof I3AdjudicationRow,
    value: number,
  ): void {
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row || !row.isEditable) return

    // 商誉减值不可转回：阻止负数减值
    if (field === 'impairment' && value < 0) {
      ElMessage.error('商誉减值不可转回！本期减少不能为负数')
      return
    }

    ;(row as any)[field] = value

    // 自动重算公式列
    row.endBalance = calcGoodwillEndBalance(row.beginBalance, row.newAcquisition, row.impairment)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
    row.netValue = calcGoodwillNetValue(row.initialRecognition, row.accImpairment)

    _persist()
  }

  // ─── Actions: TB取数接入 ──────────────────────────────────────────────────

  /**
   * 接收TB未审数据，写入行的 unadjusted 字段
   * 通常由 useI3FormData 在 selfLoad 后调用
   */
  function applyTbData(tbUnadjustedTotal: number): void {
    // TB未审总额写入合计行逻辑：
    // 如果只有1行，直接写入该行
    // 如果多行，按期末余额比例分配（或用户手动分配）
    if (rows.value.length === 1) {
      rows.value[0].unadjusted = tbUnadjustedTotal
      rows.value[0].audited = calcAuditedAmount(
        rows.value[0].unadjusted,
        rows.value[0].aje,
        rows.value[0].rje,
      )
    } else if (rows.value.length > 1) {
      // 多行时按期初余额比例分配
      const totalBegin = calcSubtotal(rows.value.map(r => r.beginBalance))
      if (totalBegin > 0) {
        for (const row of rows.value) {
          const ratio = row.beginBalance / totalBegin
          row.unadjusted = Math.round(ratio * tbUnadjustedTotal * 100) / 100
          row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
        }
      }
    }
    _persist()
  }

  /**
   * 接收 AJE/RJE 调整（来自 I3-3 调整分录表）
   * 按被投资单位匹配写入对应行
   */
  function applyAdjustments(adjustments: { investee: string; aje: number; rje: number }[]): void {
    for (const adj of adjustments) {
      const row = rows.value.find(r => r.investee === adj.investee)
      if (row) {
        row.aje = adj.aje
        row.rje = adj.rje
        row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
      }
    }
    _persist()
  }

  // ─── Actions: 保存审定 + TB回写 + EventBus ─────────────────────────────────

  /**
   * 保存审定表并回写TB（Req 2.7）：
   * 1. 持久化行数据到 checklist_responses
   * 2. 持久化审定合计到独立 item_id（render策略回读seed）
   * 3. writebackTrialBalance（科目1711）
   * 4. 发布 'substantive:adjudicated' EventBus事件
   */
  async function saveAdjudication(): Promise<void> {
    _persist()

    const auditedTotal = subtotals.value.audited

    // 持久化审定合计（独立item_id，供render策略回读seed + 跨session持久化）
    options?.onSave?.(`${ITEM_PREFIX}-audited-total`, auditedTotal)
    options?.onSave?.(`${ITEM_PREFIX}-audited-net`, subtotals.value.netValue)

    // TB回写（科目1711）
    if (projectId.value) {
      try {
        await api.put(`/api/projects/${projectId.value}/trial-balance/writeback`, {
          account_code: ACCOUNT_CODE_1711,
          audited_amount: auditedTotal,
        })
      } catch {
        ElMessage.warning('审定数回写试算表失败，请手动确认')
      }
    }

    // 发布 'substantive:adjudicated' EventBus 事件
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: {
        wpCode: 'I3',
        accountCodes: [ACCOUNT_CODE_1711],
        auditedTotal,
        netValue: subtotals.value.netValue,
      },
    }))

    ElMessage.success('审定表已保存')
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _persist(): void {
    const save = options?.onSave
    if (!save) return
    save(`${ITEM_PREFIX}-rows`, rows.value)
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
    rows,
    auditNote,
    auditConclusion,
    // Computed
    subtotals,
    warnings,
    // Computed — TB差异
    tbRow,
    differenceRows,
    // Actions — 动态行
    addRow,
    removeRow,
    // Actions — 数据接入
    updateCell,
    applyTbData,
    applyAdjustments,
    // Actions — 保存
    saveAdjudication,
    saveNote,
    saveConclusion,
    // Convenience
    getWarnings,
  }
}

export default useI3Adjudication
