/**
 * 报表勾稽（内置 logic_check）一次执行的产出：问题清单 / 逐条结论 / 提醒。
 *
 * spec formula-governance-coverage-closure R4：公式管理中心打开时已调过一次
 * `GET /api/projects/{pid}/formula/report-cross-check`（`useCrossCheckRules.loadExecItems`），
 * 原先只取 `results` 画 ✅/❌，`issue_list` 与 `hints` 被丢弃。这里把**同一次响应**整理成
 * 问题清单面板能直接用的形状 —— 不再另调一次（该接口每调一次就落一次运行记录）。
 *
 * 取代原 `useFormulaIssueHint.ts`（自己再调一次接口、且提醒项按对象形状收，而接口给的是字符串）。
 */

/** 勾稽不通过项（与后端 `formula_logic_check._serialize` 的 issue_list 对齐；金额按字符串传，防精度丢失）。 */
export interface FormulaIssueItem {
  formula_id: string
  addr_id: string | null
  description: string
  left_value: string | null
  right_value: string | null
}

/** 逐条勾稽结论（含通过项）。 */
export interface FormulaCheckOutcome {
  formula_id: string
  description: string
  expression: string
  passed: boolean
}

export interface FormulaIssueRun {
  /** 真跑出了逐条结论（本年度有报表数据）；false 时不画问题清单，免得把「没跑」显示成「全部通过」 */
  executed: boolean
  /** 请求失败（网络 / 权限 / 服务异常），原因见 error */
  failed: boolean
  error: string
  issues: FormulaIssueItem[]
  outcomes: FormulaCheckOutcome[]
  /** 执行器产出的提醒文案（内置勾稽目前不产出；非空才展示） */
  hints: string[]
  lastComputedAt: string | null
  runId: string | null
}

export function emptyIssueRun(): FormulaIssueRun {
  return {
    executed: false, failed: false, error: '', issues: [], outcomes: [],
    hints: [], lastComputedAt: null, runId: null,
  }
}

export function failedIssueRun(error: string): FormulaIssueRun {
  return { ...emptyIssueRun(), failed: true, error }
}

const isObj = (v: unknown): v is Record<string, any> => !!v && typeof v === 'object' && !Array.isArray(v)
const strOrNull = (v: unknown): string | null => (v == null || v === '' ? null : String(v))

/** 接口响应 → FormulaIssueRun（兼容已解包与未解包信封两种形状）。 */
export function issueHintFromRun(data: unknown): FormulaIssueRun {
  const body: Record<string, any> = isObj(data) && ('results' in data || 'issue_list' in data || 'status' in data)
    ? data
    : (isObj(data) && isObj(data.data) ? data.data : {})
  const outcomes: FormulaCheckOutcome[] = (Array.isArray(body.results) ? body.results : [])
    .filter(isObj)
    .map((o: Record<string, any>) => ({
      formula_id: String(o.formula_id ?? ''),
      description: String(o.description ?? ''),
      expression: String(o.expression ?? ''),
      // 只认明确的 true；缺字段按「不通过」显示，宁可多一条待查也不冒充通过
      passed: o.passed === true,
    }))
  const issues: FormulaIssueItem[] = (Array.isArray(body.issue_list) ? body.issue_list : [])
    .filter(isObj)
    .map((i: Record<string, any>) => ({
      formula_id: String(i.formula_id ?? ''),
      addr_id: strOrNull(i.addr_id),
      description: String(i.description ?? ''),
      left_value: strOrNull(i.left_value),
      right_value: strOrNull(i.right_value),
    }))
  const hints = (Array.isArray(body.hints) ? body.hints : [])
    .map((h: unknown) => (isObj(h) ? h.hint_text : h))
    .filter((h: unknown): h is string => typeof h === 'string' && h.trim() !== '')
  return {
    executed: body.no_result !== true && outcomes.length > 0,
    failed: false,
    error: '',
    issues,
    outcomes,
    hints,
    lastComputedAt: strOrNull(body.last_computed_at),
    runId: strOrNull(body.run_id),
  }
}

/** 内置勾稽在表间审核树里挂在「报表 ↔ 附注」下：该分组节点看全部，单条勾稽节点只看自己。 */
export const ISSUE_RUN_ROOT_KEYS: readonly string[] = ['cross_report_note']
export const ISSUE_RUN_ITEM_PREFIX = 'cross_exec_'

/** 当前树节点该显示的勾稽产出；与内置勾稽无关的节点返回 null（不显示）。 */
export function issueRunForNode(run: FormulaIssueRun, nodeKey: string): FormulaIssueRun | null {
  if (ISSUE_RUN_ROOT_KEYS.includes(nodeKey)) return run
  if (!nodeKey.startsWith(ISSUE_RUN_ITEM_PREFIX)) return null
  const fid = nodeKey.slice(ISSUE_RUN_ITEM_PREFIX.length)
  const outcomes = run.outcomes.filter((o) => o.formula_id === fid)
  return {
    ...run,
    executed: run.executed && outcomes.length > 0,
    outcomes,
    issues: run.issues.filter((i) => i.formula_id === fid),
  }
}
