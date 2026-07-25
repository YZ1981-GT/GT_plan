/**
 * useAdjudicationBringIn — 审定表(X-1)「从集中登记带入调整」通用装配（损益/科目类审定表复用）
 *
 * spec: adjustment-collaboration-and-propagation（审定表带入增强，K12 试点 → 全循环铺开）
 *
 * 封装:按科目拉取集中调整(useAdjudicationAdjustmentPull) + 弹窗可见态 + 目标行选项 +
 * 带入应用(逐笔累加到目标行 AJE/RJE + emit substantive:adjudicated 联动披露/附注)。
 * 各审定表只需传入自身 rows/updateCell/totalAudited + 科目参数即可复用。
 *
 * 带入后不强制 TB 回写(保持"回写TB"为显式步骤)，仅发 substantive:adjudicated 使披露表/附注刷新。
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useAdjudicationAdjustmentPull } from './useAdjudicationAdjustmentPull'
import type { AdjudicationAllocation } from '@/components/adjustment/AdjudicationBringInDialog.vue'

interface AdjudicationRowLike {
  rowKey: string
  name: string
  aje: number
  rje: number
}

export interface UseAdjudicationBringInOptions {
  projectId: Ref<string> | (() => string) | string
  year: Ref<number> | (() => number) | number
  /** 科目码前缀（拉取集中调整命中范围） */
  subjectPrefix: string | string[]
  /** 净发生额方向：损益贷方/负债/权益→'credit'；资产/损益借方→'debit' */
  direction?: 'credit' | 'debit'
  /** substantive:adjudicated 事件的科目码（供披露/附注 handler 匹配） */
  subjectCode: string
  /** 底稿编码（事件 wpCode，披露 handler 兜底匹配） */
  wpCode: string
  /** 提示文案用科目标签（如 '营业外收入(6301)'） */
  subjectLabel: string
  /** 审定表行（含 rowKey/name/aje/rje） */
  rows: ComputedRef<AdjudicationRowLike[]> | Ref<AdjudicationRowLike[]>
  /** 审定表单元格更新（rowKey, 'aje'|'rje', 累加后的值） */
  updateCell: (rowKey: string, field: any, value: number) => void
  /** 取当前审定合计（事件 auditedAmount） */
  totalAudited: () => number
}

export function useAdjudicationBringIn(opts: UseAdjudicationBringInOptions) {
  const adjPull = useAdjudicationAdjustmentPull({
    projectId: opts.projectId,
    year: opts.year,
    subjectPrefix: opts.subjectPrefix,
    direction: opts.direction,
  })
  const visible = ref(false)
  const rowOptions = computed(() =>
    (opts.rows.value as AdjudicationRowLike[]).map((r) => ({ rowKey: r.rowKey, name: r.name })),
  )

  async function open(): Promise<void> {
    await adjPull.load()
    if (!adjPull.matches.value.length) {
      ElMessage.info(`未找到命中${opts.subjectLabel}的调整分录`)
      return
    }
    visible.value = true
  }

  function apply(payload: { allocations: AdjudicationAllocation[] }): void {
    const rowsNow = opts.rows.value as AdjudicationRowLike[]
    for (const a of payload.allocations) {
      const row = rowsNow.find((r) => r.rowKey === a.rowKey)
      if (!row) continue
      if (a.aje) opts.updateCell(a.rowKey, 'aje', Math.round((row.aje + a.aje) * 100) / 100)
      if (a.rje) opts.updateCell(a.rowKey, 'rje', Math.round((row.rje + a.rje) * 100) / 100)
    }
    // 带入后发 substantive:adjudicated → 披露表 applyAutoFill 自动取新审定数 → 附注联动
    eventBus.emit('substantive:adjudicated' as any, {
      accountCode: opts.subjectCode,
      wpCode: opts.wpCode,
      auditedAmount: opts.totalAudited(),
      timestamp: Date.now(),
    })
    ElMessage.success('已带入调整分录，审定数已更新并联动披露/附注')
  }

  return { adjPull, visible, rowOptions, open, apply }
}

export default useAdjudicationBringIn
