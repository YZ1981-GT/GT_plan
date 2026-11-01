/**
 * useReviewPanel — 复核面板状态管理 + API 调用封装
 *
 * Feature: review-prompt-sheet-level-split
 * Requirements: 6.1, 6.4
 */
import { ref, reactive, onScopeDispose } from 'vue'
import http from '@/utils/http'
import { downloadFile } from '@/utils/http'
import { ElMessage } from 'element-plus'
import { MISSING_AUDIT_YEAR_MESSAGE } from '@/composables/useProjectAuditYear'
import {
  cancelAiTaskJob,
  createOrResumeAiTaskJob,
  isAiTaskTerminal,
  waitForAiTaskJob,
  type AiTaskItem,
  type AiTaskJobSnapshot,
} from '@/services/aiTaskJobs'

export interface ReviewFinding {
  id: string
  description: string
  risk_level: 'high' | 'medium' | 'low' | 'unknown'
  pass_status: boolean
  category: string
  sheet_location: string | null
  suggestion: string | null
}

export interface SheetReviewCard {
  sheetName: string
  wpId: string
  passStatus: 'pass' | 'fail' | 'pending' | 'review_error' | 'manual_review_required' | 'ai_no_new_findings' | 'ai_findings_present' | 'deterministic_failure'
  findingCount: number
  riskDistribution: { high: number; medium: number; low: number }
  findings: ReviewFinding[]
  systemChecks: Array<{
    code: string
    passed: boolean | null
    message: string
    severity: string
    check_type: string
  }>
  promptSource?: 'sheet' | 'subject' | 'base'
}

export interface ReviewProgress {
  current: number
  total: number
  currentSheet: string
}

export interface ReviewPanelState {
  sheets: SheetReviewCard[]
  isReviewing: boolean
  progress: ReviewProgress
  expandedSheet: string | null
}

export interface BatchReviewResult {
  session_id: string
  wp_code_prefix: string
  project_id: string
  results: Array<{
    wp_id: string
    sheet_name: string
    wp_code: string
    pass_status: string
    findings: ReviewFinding[]
    risk_summary: Record<string, number>
    reviewed_at: string
    model_used: string
    prompt_source: string
    error_message: string | null
    deterministic_checks?: SheetReviewCard['systemChecks']
  }>
  statistics: {
    total_sheets: number
    passed_count: number
    failed_count: number
    error_count: number
    total_findings: number
    findings_by_risk: Record<string, number>
  }
  execution: {
    start_time: string
    end_time: string
    duration_seconds: number
    model_used: string
  }
}

export interface SingleReviewResult {
  findings: ReviewFinding[]
  deterministic_checks?: SheetReviewCard['systemChecks']
  overall_pass: boolean
  review_status: 'manual_review_required' | 'ai_no_new_findings' | 'ai_findings_present' | 'deterministic_failure'
  risk_summary: Record<string, number>
  sheet_info: {
    wp_id: string
    wp_code: string
    sheet_name: string | null
    prompt_source: 'sheet' | 'subject' | 'base'
  }
}

function mapResultToCard(
  r: BatchReviewResult['results'][number],
): SheetReviewCard {
  return {
    sheetName: r.sheet_name,
    wpId: r.wp_id,
    passStatus: r.pass_status as SheetReviewCard['passStatus'],
    findingCount: r.findings.length,
    riskDistribution: {
      high: r.risk_summary?.high ?? 0,
      medium: r.risk_summary?.medium ?? 0,
      low: r.risk_summary?.low ?? 0,
    },
    findings: r.findings,
    systemChecks: r.deterministic_checks ?? [],
    promptSource: r.prompt_source as SheetReviewCard['promptSource'],
  }
}

function mapJobItemToCard(item: AiTaskItem): SheetReviewCard | null {
  const r = item.result
  if (!r) return null
  const sheetName = String(r.sheet_name || item.target_key || '底稿')
  const findings = Array.isArray(r.findings) ? r.findings as ReviewFinding[] : []
  return {
    sheetName,
    wpId: String(r.wp_id || item.target_id),
    passStatus: String(r.review_status || 'manual_review_required') as SheetReviewCard['passStatus'],
    findingCount: findings.length,
    riskDistribution: {
      high: Number(r.risk_summary?.high || 0),
      medium: Number(r.risk_summary?.medium || 0),
      low: Number(r.risk_summary?.low || 0),
    },
    findings,
    systemChecks: Array.isArray(r.deterministic_checks)
      ? r.deterministic_checks as SheetReviewCard['systemChecks']
      : [],
    promptSource: r.prompt_source as SheetReviewCard['promptSource'],
  }
}

function mapSingleToCard(
  wpId: string,
  sheetName: string,
  data: SingleReviewResult,
): SheetReviewCard {
  const passStatus = data.review_status || 'manual_review_required'
  return {
    sheetName: sheetName,
    wpId: wpId,
    passStatus,
    findingCount: data.findings.length,
    riskDistribution: {
      high: data.risk_summary?.high ?? 0,
      medium: data.risk_summary?.medium ?? 0,
      low: data.risk_summary?.low ?? 0,
    },
    findings: data.findings,
    systemChecks: data.deterministic_checks ?? [],
    promptSource: data.sheet_info.prompt_source,
  }
}

function upsertSheetCard(cards: SheetReviewCard[], card: SheetReviewCard): void {
  const idx = cards.findIndex((s) => s.sheetName === card.sheetName)
  if (idx >= 0) {
    cards[idx] = card
  } else {
    cards.unshift(card)
  }
}

/** year：审计年度；项目没填为 null ⇒ 批量复核提示去填年度、不发请求（不按今年兜底） */
export function useReviewPanel(projectId: string, wpCodePrefix: string, year: number | null) {
  const sheets = ref<SheetReviewCard[]>([])
  const isReviewing = ref(false)
  const progress = reactive<ReviewProgress>({
    current: 0,
    total: 0,
    currentSheet: '',
  })
  const expandedSheet = ref<string | null>(null)
  const batchJob = ref<AiTaskJobSnapshot | null>(null)
  let batchController: AbortController | null = null

  function applyBatchSnapshot(snapshot: AiTaskJobSnapshot): void {
    batchJob.value = snapshot
    progress.current = snapshot.progress_done
    progress.total = snapshot.progress_total
    const active = snapshot.items.find((item) =>
      item.status === 'running' || item.status === 'retry_wait' || item.status === 'queued',
    )
    progress.currentSheet = active?.target_key || (isAiTaskTerminal(snapshot.status) ? '完成' : '准备中...')
    sheets.value = snapshot.items
      .map(mapJobItemToCard)
      .filter((card): card is SheetReviewCard => card !== null)
  }

  /**
   * 触发批量复核
   */
  async function startBatchReview(): Promise<AiTaskJobSnapshot | null> {
    if (isReviewing.value) {
      ElMessage.warning('复核正在进行中，请稍候')
      return null
    }
    if (year == null) {
      ElMessage.warning(MISSING_AUDIT_YEAR_MESSAGE)
      return null
    }

    isReviewing.value = true
    progress.current = 0
    progress.total = 0
    progress.currentSheet = '准备中...'
    try {
      const snapshot = await createOrResumeAiTaskJob(
        projectId,
        `${year}:${wpCodePrefix}:batch-review`,
        {
          task_kind: 'workpaper_batch_review',
          year,
          wp_code_prefix: wpCodePrefix,
        },
      )
      applyBatchSnapshot(snapshot)
      batchController?.abort()
      batchController = new AbortController()
      const final = await waitForAiTaskJob(
        projectId,
        snapshot,
        applyBatchSnapshot,
        batchController.signal,
      )
      applyBatchSnapshot(final)
      const findingSheets = final.items.filter((item) =>
        item.result?.review_status === 'ai_findings_present'
        || item.result?.review_status === 'deterministic_failure',
      ).length
      if (final.status === 'succeeded') {
        ElMessage.success(`批量 AI 复核完成：${findingSheets} 张有待核实疑点；全部仍待人工复核`)
      } else if (final.status !== 'cancelled') {
        ElMessage.warning(`批量复核已结束：${final.failed_count} 张需人工处理`)
      }
      return final
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || '批量复核启动或恢复失败，请稍后重试')
      return null
    } finally {
      isReviewing.value = false
    }
  }

  async function cancelBatchReview(): Promise<void> {
    const job = batchJob.value
    if (!job || isAiTaskTerminal(job.status)) return
    try {
      applyBatchSnapshot(await cancelAiTaskJob(projectId, job.job_id))
      batchController?.abort()
      isReviewing.value = false
      ElMessage.success('已取消未完成的批量复核')
    } catch {
      ElMessage.error('取消批量复核失败')
    }
  }

  /**
   * 单底稿复核（API 调用）
   */
  async function reviewSingleSheet(wpId: string, sheetName: string): Promise<SingleReviewResult | null> {
    try {
      const { data } = await http.post<SingleReviewResult>(`/api/workpapers/${wpId}/review`, {
        sheet_name: sheetName,
      })
      return data
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || '复核失败')
      return null
    }
  }

  /**
   * 复核当前页并更新面板卡片
   */
  async function reviewCurrentSheet(wpId: string, sheetName: string): Promise<SingleReviewResult | null> {
    if (isReviewing.value) {
      ElMessage.warning('复核正在进行中，请稍候')
      return null
    }
    if (!sheetName) {
      ElMessage.warning('当前页无有效 sheet 名称')
      return null
    }

    isReviewing.value = true
    progress.currentSheet = sheetName
    try {
      const data = await reviewSingleSheet(wpId, sheetName)
      if (data) {
        const card = mapSingleToCard(wpId, sheetName, data)
        upsertSheetCard(sheets.value, card)
        expandedSheet.value = sheetName
        const srcLabel = data.sheet_info.prompt_source === 'sheet'
          ? '底稿级'
          : data.sheet_info.prompt_source === 'subject'
            ? '科目级(降级)'
            : '通用模板(降级)'
        const statusLabel = data.review_status === 'ai_no_new_findings'
          ? 'AI 未发现新增疑点，待人工复核'
          : data.review_status === 'ai_findings_present'
            ? 'AI 提出待核实疑点'
            : data.review_status === 'deterministic_failure'
              ? '系统检查未通过'
              : '需人工复核'
        ElMessage.success(`本页 AI 复核完成（${srcLabel}）：${statusLabel}`)
      }
      return data
    } finally {
      isReviewing.value = false
      progress.currentSheet = ''
    }
  }

  /**
   * 导出复核结果 Excel
   */
  async function exportReviewExcel() {
    try {
      await downloadFile(
        `/api/projects/${projectId}/review-export`,
        {
          params: {
            wp_code_prefix: wpCodePrefix,
            ...(batchJob.value?.job_id ? { session_id: batchJob.value.job_id } : {}),
          },
          fileName: `${wpCodePrefix}复核报告.xlsx`,
        },
      )
      ElMessage.success('导出成功')
    } catch {
      ElMessage.error('导出失败，请稍后重试')
    }
  }

  /**
   * 展开/收起某张底稿的 finding 列表
   */
  function toggleSheet(sheetName: string) {
    expandedSheet.value = expandedSheet.value === sheetName ? null : sheetName
  }

  /**
   * 更新单条 Finding 的状态
   */
  type FindingStatus = 'pending' | 'resolved' | 'ignored' | 'not_applicable'

  async function updateFindingStatus(findingId: string, status: FindingStatus) {
    try {
      await http.patch(`/api/review-findings/${findingId}/status`, { status })
      for (const sheet of sheets.value) {
        const finding = sheet.findings.find(f => f.id === findingId)
        if (finding) {
          (finding as any).status = status
          break
        }
      }
      ElMessage.success('状态已更新')
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || '状态更新失败')
    }
  }

  onScopeDispose(() => batchController?.abort())

  return {
    sheets,
    isReviewing,
    progress,
    expandedSheet,
    batchJob,
    startBatchReview,
    cancelBatchReview,
    reviewSingleSheet,
    reviewCurrentSheet,
    exportReviewExcel,
    toggleSheet,
    updateFindingStatus,
  }
}
