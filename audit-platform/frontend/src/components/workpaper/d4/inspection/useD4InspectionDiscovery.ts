/**
 * useD4InspectionDiscovery — D4-14/16 检查表发现→人工确认→A13 推送适配
 *
 * spec: d4-inspection-writeback-formula-io Task 4/5
 *
 * 复用 useD4InspectionWriteback 的核心逻辑（候选收集 + 人工确认 + emit），
 * 为 D4-14（穿行测试不一致事项）和 D4-16（出口口岸差异）提供 sheet-specific 适配。
 *
 * 🔴 确认前不得构造 A13 写入金额（Property 3）
 * 🔴 金额 0 的定性发现不自动变成错报
 */
import { computed, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD4InspectionWriteback, type D4Discovery } from '../../composables/useD4InspectionWriteback'
import { D4_MAIN_REVENUE_STANDARD } from '../../composables/d4AccountScope'

export interface InspectionDiscoveryOptions {
  wpCode: string
  projectId: Ref<string>
}

/**
 * D4-14 穿行测试：一致性分数低 + isAnomalous 的事项可能构成风险发现
 */
export function useD4_14_Discovery(options: InspectionDiscoveryOptions) {
  const { canConfirm, isPushed, pushConfirmed } = useD4InspectionWriteback({
    wpCode: options.wpCode,
    projectId: options.projectId,
    defaultAccountCode: D4_MAIN_REVENUE_STANDARD,
    defaultAccountName: '主营业务收入',
  })

  /**
   * 从穿行测试 transactions 中提取候选发现
   * 条件：isAnomalous 或 consistencyScore < 总维度数的 50%
   */
  function extractDiscoveries(transactions: any[]): D4Discovery[] {
    return transactions
      .filter(t => t.isAnomalous || (t.consistencyScore != null && t.consistencyScore < 4))
      .map(t => ({
        sourceId: t.id,
        description: `穿行测试不一致：${t.label || t.indexNo}（一致性分数 ${t.consistencyScore ?? 0}/7）`,
        direction: null as 'debit' | 'credit' | null,
        amount: t.voucher?.amount ?? 0,
        evidence: t.indexNo || '',
        accountCode: D4_MAIN_REVENUE_STANDARD,
        accountName: '主营业务收入',
      }))
  }

  const confirmDialogVisible = ref(false)
  const confirmDrafts = ref<Array<D4Discovery & { checked: boolean }>>([])

  function openConfirmDialog(transactions: any[]) {
    const discoveries = extractDiscoveries(transactions).filter(d => !isPushed(d.sourceId))
    if (!discoveries.length) {
      ElMessage.info('无未推送的穿行异常发现')
      return
    }
    confirmDrafts.value = discoveries.map(d => ({ ...d, checked: true }))
    confirmDialogVisible.value = true
  }

  function confirmAndPush() {
    const selected = confirmDrafts.value.filter(d => d.checked)
    const blocked = selected.filter(d => !canConfirm(d))
    if (blocked.length) {
      ElMessage.warning(`${blocked.length} 笔缺方向/金额/证据，未通过确认门`)
    }
    const n = pushConfirmed(selected)
    if (n > 0) {
      ElMessage.success(`已确认并推送 ${n} 笔穿行异常至 A13`)
      confirmDialogVisible.value = false
    } else if (!blocked.length) {
      ElMessage.info('无可推送的已确认发现')
    }
  }

  return {
    canConfirm,
    isPushed,
    extractDiscoveries,
    confirmDialogVisible,
    confirmDrafts,
    openConfirmDialog,
    confirmAndPush,
  }
}

/**
 * D4-16 出口口岸核对：差异金额 > 0 且无合理解释的行构成候选发现
 */
export function useD4_16_Discovery(options: InspectionDiscoveryOptions) {
  const { canConfirm, isPushed, pushConfirmed } = useD4InspectionWriteback({
    wpCode: options.wpCode,
    projectId: options.projectId,
    defaultAccountCode: D4_MAIN_REVENUE_STANDARD,
    defaultAccountName: '主营业务收入',
  })

  /**
   * 从口岸核对行中提取候选发现
   * 条件：portsDiff 或 taxDiff 的绝对值 > 0
   */
  function extractDiscoveries(rows: any[]): D4Discovery[] {
    const results: D4Discovery[] = []
    for (const r of rows) {
      const portsDiff = Math.abs(r.portsDiff ?? 0)
      const taxDiff = Math.abs(r.taxDiff ?? 0)
      if (portsDiff > 0) {
        results.push({
          sourceId: `${r.id}-ports`,
          description: `口岸结关差异：序号${r.indexNo}，账面=${r.bookAmount}，口岸=${r.portsAmount}，差异=${portsDiff}`,
          direction: null,
          amount: portsDiff,
          evidence: r.taxIndex || '',
          accountCode: D4_MAIN_REVENUE_STANDARD,
          accountName: '主营业务收入',
        })
      }
      if (taxDiff > 0) {
        results.push({
          sourceId: `${r.id}-tax`,
          description: `申报差异：序号${r.indexNo}，账面=${r.bookAmount}，申报=${r.taxReportAmount}，差异=${taxDiff}`,
          direction: null,
          amount: taxDiff,
          evidence: r.taxIndex || '',
          accountCode: D4_MAIN_REVENUE_STANDARD,
          accountName: '主营业务收入',
        })
      }
    }
    return results
  }

  const confirmDialogVisible = ref(false)
  const confirmDrafts = ref<Array<D4Discovery & { checked: boolean }>>([])

  function openConfirmDialog(rows: any[]) {
    const discoveries = extractDiscoveries(rows).filter(d => !isPushed(d.sourceId))
    if (!discoveries.length) {
      ElMessage.info('无未推送的差异发现')
      return
    }
    confirmDrafts.value = discoveries.map(d => ({ ...d, checked: true }))
    confirmDialogVisible.value = true
  }

  function confirmAndPush() {
    const selected = confirmDrafts.value.filter(d => d.checked)
    const blocked = selected.filter(d => !canConfirm(d))
    if (blocked.length) {
      ElMessage.warning(`${blocked.length} 笔缺方向/金额/证据，未通过确认门`)
    }
    const n = pushConfirmed(selected)
    if (n > 0) {
      ElMessage.success(`已确认并推送 ${n} 笔差异至 A13`)
      confirmDialogVisible.value = false
    } else if (!blocked.length) {
      ElMessage.info('无可推送的已确认发现')
    }
  }

  return {
    canConfirm,
    isPushed,
    extractDiscoveries,
    confirmDialogVisible,
    confirmDrafts,
    openConfirmDialog,
    confirmAndPush,
  }
}
