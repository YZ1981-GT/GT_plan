/**
 * useD2VcAuditSummary — D2-7 审计说明统计自动化 composable
 *
 * Spec: .kiro/specs/d2-7-voucher-check-enhancement/
 * Task: 4.1
 *
 * 职责：
 * - AuditSummaryStats 接口定义
 * - computeAuditSummary 纯函数：从双区行数据计算统计指标
 * - 从 trial_balance 获取 occurrenceAmount（科目 1122 本期发生额）
 * - watch 监听双区行数据变更，2 秒 debounce 后重新计算统计指标
 * - AI 生成审计说明（调用 /ai/generate-text，section='vc-audit-summary'）
 * - 持久化到 D2-vc-audit-summary item_id
 *
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
 */
import { ref, watch, inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { D2_SAVE_ITEMS_KEY } from './d2InjectionKeys'
import type { VoucherCheckRow } from './useD2VoucherCheckEnhanced'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface AuditSummaryStats {
  occurrenceAmount: number      // 本期发生额合计（from TB）
  checkedAmount: number         // 已检查金额合计
  coverageRatio: number         // 检查覆盖比例 (%)
  checkedCount: number          // 已检查笔数
  abnormalCount: number         // 异常笔数
  abnormalAmount: number        // 异常金额合计
  abnormalRate: number          // 异常率 (%)
}

export interface UseD2VcAuditSummaryOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  currentRows: Ref<VoucherCheckRow[]>
  postRows: Ref<VoucherCheckRow[]>
  allResponses: Ref<Map<string, any>>
  isReadonly: Ref<boolean>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const AUDIT_SUMMARY_KEY = 'D2-vc-audit-summary'

// ─── Pure Functions (exported for PBT) ───────────────────────────────────────

/**
 * 从双区行数据计算审计说明统计指标
 *
 * - checkedAmount = sum(debitAmount + creditAmount) 遍历两区所有行
 * - checkedCount = 两区总行数
 * - abnormalCount = isAbnormal 非空字符串的行数
 * - abnormalAmount = 异常行的 sum(debitAmount + creditAmount)
 * - abnormalRate = abnormalCount / checkedCount * 100 (无行时为 0)
 * - coverageRatio = checkedAmount / occurrenceAmount * 100 (occurrenceAmount 为 0 时为 0)
 */
export function computeAuditSummary(
  currentRows: VoucherCheckRow[],
  postRows: VoucherCheckRow[],
  occurrenceAmount: number
): AuditSummaryStats {
  const allRows = [...currentRows, ...postRows]
  const checkedCount = allRows.length

  let checkedAmount = 0
  let abnormalCount = 0
  let abnormalAmount = 0

  for (const row of allRows) {
    const rowAmount = (Number(row.debitAmount) || 0) + (Number(row.creditAmount) || 0)
    checkedAmount += rowAmount

    if (row.isAbnormal && row.isAbnormal.trim() !== '') {
      abnormalCount++
      abnormalAmount += rowAmount
    }
  }

  const abnormalRate = checkedCount > 0
    ? (abnormalCount / checkedCount) * 100
    : 0

  const coverageRatio = occurrenceAmount > 0
    ? (checkedAmount / occurrenceAmount) * 100
    : 0

  return {
    occurrenceAmount,
    checkedAmount,
    coverageRatio,
    checkedCount,
    abnormalCount,
    abnormalAmount,
    abnormalRate,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD2VcAuditSummary(options: UseD2VcAuditSummaryOptions) {
  const { wpId, projectId, currentRows, postRows, allResponses, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const stats = ref<AuditSummaryStats>({
    occurrenceAmount: 0,
    checkedAmount: 0,
    coverageRatio: 0,
    checkedCount: 0,
    abnormalCount: 0,
    abnormalAmount: 0,
    abnormalRate: 0,
  })

  const summaryText = ref<string>('')
  const isGenerating = ref(false)
  const isLoadingTb = ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // Inject save function from parent (provide/inject pattern)
  const saveItems = inject(D2_SAVE_ITEMS_KEY, null)

  // ─── Trial Balance Data ────────────────────────────────────────────────

  /**
   * 从试算表获取科目 1122 本期借方发生额 (occurrenceAmount)
   */
  async function loadOccurrenceAmount(): Promise<void> {
    if (!projectId.value) return
    isLoadingTb.value = true
    try {
      // 获取项目审计年度
      let year = new Date().getFullYear() - 1
      try {
        const projRes = await api.get(`/api/projects/${projectId.value}`)
        const proj = projRes?.data ?? projRes
        if (proj?.audit_year) year = Number(proj.audit_year)
      } catch { /* fallback to previous year */ }

      const tbRes = await api.get(`/api/projects/${projectId.value}/trial-balance`, {
        params: { year },
      })
      const tbData = Array.isArray(tbRes?.data) ? tbRes.data : (Array.isArray(tbRes) ? tbRes : [])
      const tbRow = tbData.find((r: any) => r.standard_account_code === '1122')

      if (tbRow) {
        const debitOccurrence = Number(tbRow.debit_occurrence ?? tbRow.debitOccurrence ?? 0)
        stats.value = {
          ...stats.value,
          occurrenceAmount: debitOccurrence,
        }
        // Recompute with new occurrenceAmount
        recompute()
      }
    } catch (err) {
      console.warn('[useD2VcAuditSummary] 试算表数据获取失败:', err)
    } finally {
      isLoadingTb.value = false
    }
  }

  // ─── Computation ───────────────────────────────────────────────────────

  /**
   * 重新计算统计指标
   */
  function recompute(): void {
    const result = computeAuditSummary(
      currentRows.value,
      postRows.value,
      stats.value.occurrenceAmount
    )
    stats.value = result
  }

  // ─── Watch with 2-second debounce ─────────────────────────────────────

  watch(
    [currentRows, postRows],
    () => {
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        debounceTimer = null
        recompute()
      }, 2000)
    },
    { deep: true }
  )

  // ─── AI Generation ─────────────────────────────────────────────────────

  /**
   * AI 生成审计说明
   * 调用 /api/workpapers/{wpId}/ai/generate-text
   * section='vc-audit-summary'
   * context 包含统计数据和异常明细
   */
  async function generateAuditSummary(): Promise<string | null> {
    if (!wpId.value) return null
    if (isGenerating.value) return null

    isGenerating.value = true
    try {
      // 构建异常明细
      const allRows = [...currentRows.value, ...postRows.value]
      const abnormalRows = allRows.filter(r => r.isAbnormal && r.isAbnormal.trim() !== '')
      const abnormalDetails = abnormalRows.map(r => ({
        voucherNo: r.voucherNo,
        customerName: r.customerName,
        amount: (Number(r.debitAmount) || 0) + (Number(r.creditAmount) || 0),
        abnormalType: r.isAbnormal,
        remark: r.remark,
      }))

      const context = {
        stats: stats.value,
        abnormalDetails,
        totalRows: allRows.length,
      }

      const res = await api.post(`/api/workpapers/${wpId.value}/ai/generate-text`, {
        section: 'vc-audit-summary',
        prompt: '请根据凭证检查统计数据和异常明细，生成审计说明文字',
        context: JSON.stringify(context),
        existingContent: summaryText.value || undefined,
      })

      const generated = res?.data?.content ?? res?.data ?? res?.content ?? ''
      if (generated) {
        summaryText.value = generated
        saveToResponses()
        return generated
      }
      return null
    } catch (err) {
      console.warn('[useD2VcAuditSummary] AI 生成审计说明失败:', err)
      ElMessage.warning('AI 服务暂不可用，请手动编写审计说明')
      return null
    } finally {
      isGenerating.value = false
    }
  }

  // ─── Persistence ───────────────────────────────────────────────────────

  /**
   * 从 allResponses 加载审计说明文字
   */
  function loadFromResponses(): void {
    const resp = allResponses.value.get(AUDIT_SUMMARY_KEY)
    if (resp?.remark) {
      summaryText.value = resp.remark
    }
  }

  /**
   * 保存审计说明文字到 allResponses
   */
  function saveToResponses(): void {
    if (isReadonly.value) return

    const item = {
      item_id: AUDIT_SUMMARY_KEY,
      conclusion: null,
      remark: summaryText.value,
    }

    // Update local allResponses map
    allResponses.value.set(AUDIT_SUMMARY_KEY, item)

    // Persist via inject'd save function
    if (saveItems) {
      saveItems([item])
    }
  }

  // ─── Init ──────────────────────────────────────────────────────────────

  // Load persisted data on mount
  watch(
    () => allResponses.value.get(AUDIT_SUMMARY_KEY)?.remark,
    () => {
      if (!summaryText.value) {
        loadFromResponses()
      }
    },
    { immediate: true }
  )

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    stats,
    summaryText,
    isGenerating,
    isLoadingTb,
    // Actions
    loadOccurrenceAmount,
    recompute,
    generateAuditSummary,
    // Persistence
    loadFromResponses,
    saveToResponses,
  }
}

export default useD2VcAuditSummary
