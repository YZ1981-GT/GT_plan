/**
 * 表间审核用户规则（加载 / 保存 / CRUD / 执行）—— 从 FormulaManagerDialog 拆出。
 *
 * spec formula-global-settings-sync Phase 4 / R10.2：用户规则存 formula_setting，
 * 全局 + 本项目两层，差量写入与 CAS（缺令牌 428、过期 409）；保存后弹应用范围（changed_slot_keys）。
 */
import { computed, ref, type Ref } from 'vue'
import type { CROSS_CHECK_NODE_KEYS as _Keys } from '../crossCheckKey'
import { emptyIssueRun, failedIssueRun, issueHintFromRun, type FormulaIssueRun } from '../formulaIssueHint'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'

export interface CrossCheckDeps {
  projectId: Ref<string>
  year: Ref<number | string | undefined>
  selectedNodeKey: Ref<string>
  currentProjectCacheKey: Ref<string>
  cacheKeyMatches: (a: string | null, b: string) => boolean
  shouldApplyResponse: (req: string, current: string) => boolean
  api: any
  projectFormula: { reportCrossCheck: (pid: string) => string; crossCheckRules: (pid: string) => string }
  P_rc: { executeFormulasBatch: string }
  guardFormulaMutation: () => boolean
  showFormulaError: (e: any, fallback: string) => void
  askApplyScope: (domain: string, slotKeys: string[]) => void
  CROSS_CHECK_NODE_KEYS: typeof _Keys
}

// 原先这里有一组写死的「示例规则」（DEFAULT_SEEDS）作为规则表的初值：读接口返回「从未保存过 = 空集」时不覆盖
// ⇒ 它们冒充本项目规则显示（面板的「尚无自定义规则」空态永远出不来），用户第一次保存任何规则时被整组写进库。
// 而它们本身取不到数：NOTE 第一参写的是标题（应为章节编号，且国企 / 上市编号不同，写死不了）、CONSOL 不是可执行函数、
// REPORT('BS-资本公积') 不是行次（spec formula-fetch-followup-defect-closure 7.2）。规则以服务端为准，空就是空。

export function useCrossCheckRules(deps: CrossCheckDeps) {
  // ── 执行结果（7 条内置 logic_check 勾稽 + 用户规则执行结果） ──
  const execItems = ref<Record<string, any[]>>({ report_note: [], report_wp: [], note_wp: [] })
  const execLoaded = ref(false)
  const execCacheKey = ref<string | null>(null)
  const execEmpty = ref(false)
  // 同一次响应里的问题清单 / 提醒 / 计算时间（spec formula-governance-coverage-closure R4）
  const execRun = ref<FormulaIssueRun>(emptyIssueRun())
  const execLoading = ref(false)
  let execSeq = 0

  // ── 用户可编辑规则（按树节点 key 分组） ──
  const rulesMap = ref<Record<string, any[]>>({})
  const tokens = ref<Record<string, string>>({})

  const isCrossCheckMode = computed(() => deps.selectedNodeKey.value.startsWith('cross_'))
  const rulesForCurrent = computed(() => rulesMap.value[deps.selectedNodeKey.value] || [])

  // ── 加载执行结果（7 条 logic_check + 用户规则的 passed/描述） ──
  async function loadExecItems() {
    if ((execLoaded.value && deps.cacheKeyMatches(execCacheKey.value, deps.currentProjectCacheKey.value))
        || !deps.projectId.value) return
    if (!(await fetchExecRun())) return
    await loadUserRules()
  }

  /** 重新执行内置勾稽（问题清单「刷新」）；只刷新勾稽结论，不重载用户规则（免得冲掉规则的执行结果）。 */
  async function refreshExec() {
    if (!deps.projectId.value) return
    await fetchExecRun()
  }

  /**
   * 调一次 report-cross-check：树上的 ✅/❌、问题清单、提醒都取自这一次响应。
   * 失败如实记为失败（原先 `validateStatus < 600` 把 403 / 500 也当成「无结果」）。
   * 返回 false = 响应已过期（换了项目 / 年度），调用方不再继续。
   */
  async function fetchExecRun(): Promise<boolean> {
    const reqKey = deps.currentProjectCacheKey.value
    const seq = ++execSeq
    // 换了项目 / 年度：先清掉上一个项目的结论，加载期间不显示别人的问题清单
    if (!deps.cacheKeyMatches(execCacheKey.value, reqKey)) execRun.value = emptyIssueRun()
    let run: FormulaIssueRun = emptyIssueRun()
    let results: any[] = []
    if (deps.year.value != null) {
      execLoading.value = true
      try {
        const data = await deps.api.get(deps.projectFormula.reportCrossCheck(deps.projectId.value), {
          params: { year: Number(deps.year.value) }, _silent: true,
        } as any)
        if (!deps.shouldApplyResponse(reqKey, deps.currentProjectCacheKey.value)) return false
        run = issueHintFromRun(data)
        results = Array.isArray(data?.results) ? data.results
          : (Array.isArray(data?.data?.results) ? data.data.results : [])
      } catch (e: any) {
        if (!deps.shouldApplyResponse(reqKey, deps.currentProjectCacheKey.value)) return false
        run = failedIssueRun(formulaErrorText(e, '报表勾稽执行失败'))
      } finally {
        if (seq === execSeq) execLoading.value = false
      }
    }
    if (!deps.shouldApplyResponse(reqKey, deps.currentProjectCacheKey.value)) return false
    execRun.value = run
    // 「无结果」只指真没有结论；请求失败另由 execRun.failed 呈现
    execEmpty.value = !results.length && !run.failed
    execItems.value = {
      report_note: results.map((o: any) => ({
        key: `cross_exec_${o.formula_id}`, label: o.description || o.formula_id,
        icon: o.passed === true ? '✅' : o.passed === false ? '❌' : '📌',
        _formulaId: o.formula_id, _passed: o.passed,
      })),
      report_wp: [], note_wp: [],
    }
    execLoaded.value = true
    execCacheKey.value = reqKey
    return true
  }

  async function loadUserRules() {
    if (!deps.projectId.value) return
    try {
      const data: any = await deps.api.get(deps.projectFormula.crossCheckRules(deps.projectId.value), {
        _silent: true, validateStatus: (s: number) => s < 600,
      } as any)
      applyRulesData(data)
    } catch { /* 读失败：保留已加载的规则（首次进入即为空，不再拿写死的示例冒充） */ }
  }

  function applyRulesData(data: any) {
    const rules = data?.rules ?? data?.data?.rules ?? null
    if (!rules || typeof rules !== 'object') return
    tokens.value = data?.loaded ?? data?.data?.loaded ?? {}
    // 读接口 / 保存接口返回的都是本项目生效的**全部**规则 ⇒ 整体替换；响应里没有的节点就是没有规则
    const next: Record<string, any[]> = {}
    for (const [nodeKey, nodeRules] of Object.entries(rules)) {
      if (!Array.isArray(nodeRules)) continue
      next[nodeKey] = (nodeRules as any[]).map((r) => ({
        rule_id: r.rule_id || undefined, label: r.label || '', left_ref: r.left_ref || '',
        operator: r.operator || '=', right_ref: r.right_ref || '', description: r.description || '',
        layer: r.layer, pending: r.pending, _editing: false,
      }))
    }
    rulesMap.value = next
  }

  async function persist() {
    if (!deps.guardFormulaMutation()) return
    if (!deps.projectId.value) return
    const payload: Record<string, any[]> = {}
    for (const [nodeKey, nodeRules] of Object.entries(rulesMap.value)) {
      payload[nodeKey] = (nodeRules || []).map((r) => ({
        rule_id: r.rule_id || undefined, label: r.label || '', left_ref: r.left_ref || '',
        operator: r.operator || '=', right_ref: r.right_ref || '', description: r.description || '',
      }))
    }
    try {
      const ccRes: any = await deps.api.put(deps.projectFormula.crossCheckRules(deps.projectId.value),
        { rules: payload, loaded: tokens.value })
      applyRulesData(ccRes)
      deps.askApplyScope('cross_check', ccRes?.changed_slot_keys || [])
    } catch (e: any) {
      deps.showFormulaError(e, '表间审核规则保存失败')
    }
  }

  // ── 弹窗编辑 ──
  const showDialog = ref(false)
  const dialogTitle = ref('新增规则')
  const editIndex = ref(-1)
  const form = ref({ label: '', left_ref: '', operator: '=', right_ref: '', description: '' })

  function onAdd() {
    dialogTitle.value = '新增表间审核规则'
    editIndex.value = -1
    form.value = { label: '', left_ref: '', operator: '=', right_ref: '', description: '' }
    showDialog.value = true
  }

  function onEdit(row: any, index: number) {
    dialogTitle.value = '编辑表间审核规则'
    editIndex.value = index
    form.value = { label: row.label || '', left_ref: row.left_ref || '', operator: row.operator || '=',
                   right_ref: row.right_ref || '', description: row.description || '' }
    showDialog.value = true
  }

  function onSave() {
    if (!deps.guardFormulaMutation()) return
    const key = deps.selectedNodeKey.value
    if (!rulesMap.value[key]) rulesMap.value[key] = []
    const data = { ...form.value, _editing: false }
    if (editIndex.value >= 0) Object.assign(rulesMap.value[key][editIndex.value], data)
    else rulesMap.value[key].push(data)
    showDialog.value = false
    void persist()
  }

  function onRemove(index: number) {
    if (!deps.guardFormulaMutation()) return
    const key = deps.selectedNodeKey.value
    rulesMap.value[key]?.splice(index, 1)
    void persist()
  }

  // ── 执行校验 ──
  const running = ref(false)

  async function run() {
    const rules = rulesForCurrent.value
    if (!rules.length || !deps.projectId.value || !deps.year.value) return
    running.value = true
    try {
      const allFormulas: { row_code: string; formula: string }[] = []
      for (let i = 0; i < rules.length; i++) {
        if (rules[i].left_ref) allFormulas.push({ row_code: `_ccL${i}`, formula: rules[i].left_ref })
        if (rules[i].right_ref) allFormulas.push({ row_code: `_ccR${i}`, formula: rules[i].right_ref })
      }
      const data = await deps.api.post(deps.P_rc.executeFormulasBatch, {
        project_id: deps.projectId.value, year: deps.year.value, formulas: allFormulas,
      }, { validateStatus: (s: number) => s < 600 })
      const resultMap = new Map<string, number>()
      for (const r of (data?.results || [])) {
        if (r.row_code && r.value != null && r.error == null) resultMap.set(r.row_code, Number(r.value))
      }
      let passCount = 0, failCount = 0
      for (let i = 0; i < rules.length; i++) {
        const leftVal = resultMap.get(`_ccL${i}`) ?? null
        const rightVal = resultMap.get(`_ccR${i}`) ?? null
        rules[i]._leftVal = leftVal; rules[i]._rightVal = rightVal
        rules[i]._checked = leftVal != null && rightVal != null
        if (rules[i]._checked) {
          const diff = (leftVal ?? 0) - (rightVal ?? 0)
          rules[i]._diff = diff
          const op = rules[i].operator || '='
          rules[i]._pass = op === '=' ? Math.abs(diff) < 0.01 : op === '<=' ? diff <= 0.01 : op === '>=' ? diff >= -0.01 : Math.abs(diff) < 0.01
          if (rules[i]._pass) passCount++; else failCount++
        }
      }
      return { passCount, failCount }
    } finally { running.value = false }
  }

  function resetCache() {
    execLoaded.value = false; execCacheKey.value = null; execEmpty.value = false
    execRun.value = emptyIssueRun()
  }

  return {
    execItems, execLoaded, execEmpty, execRun, execLoading, isCrossCheckMode,
    rulesMap, rulesForCurrent, tokens,
    loadExecItems, refreshExec, loadUserRules, applyRulesData, persist, resetCache,
    showDialog, dialogTitle, editIndex, form, onAdd, onEdit, onSave, onRemove,
    running, run,
  }
}
