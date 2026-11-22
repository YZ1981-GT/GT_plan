import { computed, ref, watch, type Ref } from 'vue'
import { classifyDatasetUnit } from '@/composables/classifyDatasetUnit'
import { useDatasetUnitPresentation } from '@/composables/useDatasetUnitPresentation'
import { getActiveLedgerDataset } from '@/services/ledgerImportApi'

export interface TrialBalanceDataSummary {
  year: number
  balance_count: number
  ledger_count: number
  amount_unit: string
  source_summary: Record<string, unknown> | null
}

/**
 * 试算表页的数据集单位三态 presenter。
 *
 * `summary` 是「导入弹窗打开时」才填充的摘要；给出 `projectId` + `year` 时
 * **本 composable 自己加载 active 数据集**，让主页面（而非只在弹窗里）
 * 也能显示 `normalized_v1` 的存储单位与因子（R8 / AC-14）。
 *
 * 两个来源合并规则：弹窗摘要优先（它带科目数等额外信息），否则用自加载结果。
 * 自加载失败**不清空**已有值，也不抛错 —— 单位标签缺失不能影响试算表主流程。
 */
export function useTrialBalanceDatasetUnit(
  summary: Ref<TrialBalanceDataSummary | null | undefined>,
  projectId?: Ref<string | null | undefined>,
  year?: Ref<number | null | undefined>,
) {
  const selfLoaded = ref<Record<string, unknown> | null>(null)

  if (projectId && year) {
    watch(
      [projectId, year],
      async ([pid, y]) => {
        selfLoaded.value = null
        if (!pid || y == null) return
        try {
          const ds = await getActiveLedgerDataset(pid, y)
          selfLoaded.value = (ds?.source_summary as Record<string, unknown> | null) ?? null
        } catch {
          /* 单位标签缺失不影响主流程；保持 null */
        }
      },
      { immediate: true },
    )
  }

  const sourceSummary = computed(
    () => summary.value?.source_summary ?? selfLoaded.value ?? null,
  )
  const classification = computed(() => classifyDatasetUnit(sourceSummary.value))
  return useDatasetUnitPresentation(classification, sourceSummary)
}
