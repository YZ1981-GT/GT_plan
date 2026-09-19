/**
 * useReviewPanel — 复核面板状态管理 + API 调用封装
 *
 * Feature: review-prompt-sheet-level-split
 * Requirements: 6.1, 6.4
 */
import { ref, reactive } from 'vue'
import http from '@/utils/http'
import { downloadFile } from '@/utils/http'
import { ElMessage } from 'element-plus'

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
  passStatus: 'pass' | 'fail' | 'pending' | 'review_error' | 'manual_review_required'
  findingCount: number
  riskDistribution: { high: number; medium: number; low: number }
  findings: ReviewFinding[]
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
  overall_pass: boolean
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
    promptSource: r.prompt_source as SheetReviewCard['promptSource'],
  }
}

function mapSingleToCard(
  wpId: string,
  sheetName: string,
  data: SingleReviewResult,
): SheetReviewCard {
  const passStatus = data.overall_pass
    ? 'pass'
    : 'fail'
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

export function useReviewPanel(projectId: string, wpCodePrefix: string, year: number) {
  const sheets = ref<SheetReviewCard[]>([])
  const isReviewing = ref(false)
  const progress = reactive<ReviewProgress>({
    current: 0,
    total: 0,
    currentSheet: '',
  })
  const expandedSheet = ref<string | null>(null)

  /**
   * 触发批量复核
   */
  async function startBatchReview(): Promise<BatchReviewResult | null> {
    if (isReviewing.value) {
      ElMessage.warning('复核正在进行中，请稍候')
      return null
    }

    isReviewing.value = true
    progress.current = 0
    progress.total = 0
    progress.currentSheet = '准备中...'

    let progressTimer: ReturnType<typeof setInterval> | null = null
    const sessionIdForProgress = crypto.randomUUID?.() || `${Date.now()}`

    progressTimer = setInterval(async () => {
      try {
        const { data: prog } = await http.get(
          `/api/projects/${projectId}/batch-review-progress`,
          { params: { session_id: sessionIdForProgress } },
        )
        if (prog && prog.status === 'running') {
          progress.current = prog.current
          progress.total = prog.total
          progress.currentSheet = prog.current_sheet || ''
        }
      } catch {
        // 轮询失败不阻断
      }
    }, 1500)

    try {
      const { data } = await http.post<BatchReviewResult>(
        `/api/projects/${projectId}/batch-review`,
        {
          wp_code_prefix: wpCodePrefix,
          year,
          progress_session_id: sessionIdForProgress,
        },
      )

      if (data) {
        sheets.value = data.results.map(mapResultToCard)
        progress.current = data.statistics.total_sheets
        progress.total = data.statistics.total_sheets
        progress.currentSheet = '完成'
        ElMessage.success(`批量复核完成：${data.statistics.passed_count} 通过 / ${data.statistics.failed_count} 未通过`)
      }

      return data
    } catch (err: any) {
      ElMessage.error(err?.response?.data?.detail || '批量复核失败，请稍后重试')
      return null
    } finally {
      if (progressTimer) {
        clearInterval(progressTimer)
        progressTimer = null
      }
      isReviewing.value = false
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
        ElMessage.success(`本页复核完成（${srcLabel}）：${data.overall_pass ? '通过' : '未通过'}`)
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
          params: { wp_code_prefix: wpCodePrefix },
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

  return {
    sheets,
    isReviewing,
    progress,
    expandedSheet,
    startBatchReview,
    reviewSingleSheet,
    reviewCurrentSheet,
    exportReviewExcel,
    toggleSheet,
    updateFindingStatus,
  }
}
