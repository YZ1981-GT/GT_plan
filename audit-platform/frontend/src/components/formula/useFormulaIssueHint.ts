/**
 * useFormulaIssueHint — logic_check 问题清单 + reasonability 提醒清单 数据源 composable
 *
 * Task 12.3（formula-management-library）：
 * - 消费后端 logic_check 执行端点（`GET /api/projects/{project_id}/formula/report-cross-check`，
 *   Task 4.1 已建）返回的 **Issue_List**（勾稽不通过项）+ 逐条 passed 结果（Req 6.2）。
 * - 管理 reasonability 类 **Hint_List**（提醒项，Req 7.2）。平台暂无统一的 reasonability
 *   执行端点，故 Hint_List 采取数据驱动：由上游注入（`setHints`）或经自定义 fetcher 加载
 *   （`loadHints`），保持前向兼容——后端 hint 端点就绪后仅需替换 fetcher，面板无需改动。
 *
 * logic_check / reasonability 语义：**绝不修改任何数据值**——本 composable 为只读消费。
 *
 * Requirements: 6.2, 7.2
 */
import { ref, type Ref } from 'vue'
import http from '@/utils/http'
// spec: formula-management-runtime-closure Task 14 — 端点收敛进 apiPaths（纯搬迁）
import { projectFormula } from '@/services/apiPaths/formula'

// ─── Types ──────────────────────────────────────────────────────────────────

/** logic_check 产出的单条问题项（与后端 IssueItem / _serialize 对齐）。 */
export interface FormulaIssueItem {
  formula_id: string
  addr_id: string | null
  description: string
  /** 后端以字符串序列化 Decimal，避免精度丢失 */
  left_value: string | null
  right_value: string | null
}

/** logic_check 逐条勾稽结果（含通过项，供面板展示全量校验概览）。 */
export interface FormulaCheckOutcome {
  formula_id: string
  description: string
  expression: string
  passed: boolean
}

/** reasonability 产出的单条提醒项（与 design.md HintItem 对齐）。 */
export interface FormulaHintItem {
  formula_id: string
  addr_id: string | null
  hint_text: string
}

/** report-cross-check 端点响应结构。 */
interface CrossCheckResponse {
  issue_list?: FormulaIssueItem[]
  results?: FormulaCheckOutcome[]
  last_computed_at?: string | null
}

export interface UseFormulaIssueHintReturn {
  // ── logic_check 问题清单 ──
  issues: Ref<FormulaIssueItem[]>
  issueOutcomes: Ref<FormulaCheckOutcome[]>
  issuesLoading: Ref<boolean>
  issuesLastComputedAt: Ref<string | null>
  /** 拉取报表勾稽 Issue_List（7 条 logic_check 公式执行结果） */
  loadIssues: (projectId: string, year: number) => Promise<void>

  // ── reasonability 提醒清单 ──
  hints: Ref<FormulaHintItem[]>
  hintsLoading: Ref<boolean>
  hintsLastComputedAt: Ref<string | null>
  /** 直接注入 Hint_List（上游已持有提醒数据时） */
  setHints: (items: FormulaHintItem[], lastComputedAt?: string | null) => void
  /** 经自定义 fetcher 加载 Hint_List（后端 hint 端点就绪后替换即可） */
  loadHints: (
    fetcher: () => Promise<{ hint_list: FormulaHintItem[]; last_computed_at?: string | null }>,
  ) => Promise<void>
}

// ─── Composable ─────────────────────────────────────────────────────────────

export function useFormulaIssueHint(): UseFormulaIssueHintReturn {
  const issues = ref<FormulaIssueItem[]>([])
  const issueOutcomes = ref<FormulaCheckOutcome[]>([])
  const issuesLoading = ref(false)
  const issuesLastComputedAt = ref<string | null>(null)

  const hints = ref<FormulaHintItem[]>([])
  const hintsLoading = ref(false)
  const hintsLastComputedAt = ref<string | null>(null)

  async function loadIssues(projectId: string, year: number): Promise<void> {
    if (!projectId || !year) return
    if (issuesLoading.value) return
    issuesLoading.value = true
    try {
      const { data } = await http.get<CrossCheckResponse>(
        projectFormula.reportCrossCheck(projectId),
        { params: { year } },
      )
      const payload: CrossCheckResponse = (data ?? {}) as CrossCheckResponse
      issues.value = Array.isArray(payload.issue_list) ? payload.issue_list : []
      issueOutcomes.value = Array.isArray(payload.results) ? payload.results : []
      issuesLastComputedAt.value = payload.last_computed_at ?? null
    } catch (e) {
      console.warn('[useFormulaIssueHint] loadIssues 失败', e)
      issues.value = []
      issueOutcomes.value = []
      issuesLastComputedAt.value = null
    } finally {
      issuesLoading.value = false
    }
  }

  function setHints(items: FormulaHintItem[], lastComputedAt: string | null = null): void {
    hints.value = Array.isArray(items) ? items : []
    hintsLastComputedAt.value = lastComputedAt
  }

  async function loadHints(
    fetcher: () => Promise<{ hint_list: FormulaHintItem[]; last_computed_at?: string | null }>,
  ): Promise<void> {
    if (hintsLoading.value) return
    hintsLoading.value = true
    try {
      const res = await fetcher()
      hints.value = Array.isArray(res?.hint_list) ? res.hint_list : []
      hintsLastComputedAt.value = res?.last_computed_at ?? null
    } catch (e) {
      console.warn('[useFormulaIssueHint] loadHints 失败', e)
      hints.value = []
      hintsLastComputedAt.value = null
    } finally {
      hintsLoading.value = false
    }
  }

  return {
    issues,
    issueOutcomes,
    issuesLoading,
    issuesLastComputedAt,
    loadIssues,
    hints,
    hintsLoading,
    hintsLastComputedAt,
    setHints,
    loadHints,
  }
}
