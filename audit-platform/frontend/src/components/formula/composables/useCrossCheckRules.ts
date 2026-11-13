/** 用户规则保存保留 CAS 与应用范围；执行只消费同次服务端结论，不在前端另算。 */
import { computed, ref, watch, onScopeDispose, type Ref } from 'vue'
import type { CROSS_CHECK_NODE_KEYS as _Keys } from '../crossCheckKey'
import { emptyIssueRun, failedIssueRun, issueHintFromRun, formulaCheckNumber, formulaCheckSeverity, type FormulaIssueRun } from '../formulaIssueHint'
import { formulaErrorText } from '@/composables/formula/useFormulaSettings'
export interface CrossCheckDeps {
  projectId: Ref<string>; year: Ref<number | string | undefined>; selectedNodeKey: Ref<string>; currentProjectCacheKey: Ref<string>
  cacheKeyMatches: (a: string | null, b: string) => boolean; shouldApplyResponse: (req: string, current: string) => boolean
  api: any; projectFormula: { reportCrossCheck: (pid: string) => string; crossCheckRules: (pid: string) => string }; P_rc: { executeFormulasBatch: string }
  guardFormulaMutation: () => boolean; showFormulaError: (e: any, fallback: string) => void; askApplyScope: (domain: string, slotKeys: string[]) => void; CROSS_CHECK_NODE_KEYS: typeof _Keys
}
export function useCrossCheckRules(deps: CrossCheckDeps) {
  const execItems = ref<Record<string, any[]>>({ report_note: [], report_wp: [], note_wp: [] }), execLoaded = ref(false), execCacheKey = ref<string | null>(null), execEmpty = ref(false), execRun = ref<FormulaIssueRun>(emptyIssueRun()), execLoading = ref(false)
  const rulesMap = ref<Record<string, any[]>>({}), tokens = ref<Record<string, string | null>>({}), running = ref(false)
  let loadedRules: Array<{ node: string; slot: string | undefined; ruleId: unknown; definition: string }> = []
  const own = (value: object, key: string) => Object.prototype.hasOwnProperty.call(value, key)
  const record = (value: unknown): value is Record<string, any> => value !== null && typeof value === 'object' && !Array.isArray(value)
  const ruleFields = (r: any) => ({ label: r.label || '', left_ref: r.left_ref || '', operator: r.operator || '=', right_ref: r.right_ref || '', description: r.description || '', tolerance: r.tolerance, severity: formulaCheckSeverity(r.severity) })
  function readRulesData(data: any, requireLoaded = false) {
    const body = record(data) && own(data, 'rules') ? data : data?.data
    if (!record(body) || !record(body.rules) || !Object.values(body.rules).every(rows => Array.isArray(rows) && rows.every(record))) throw new Error('响应未返回有效规则集合，请重试')
    if ((requireLoaded || own(body, 'loaded')) && (!record(body.loaded) || !Object.values(body.loaded).every(token => token === null || typeof token === 'string'))) throw new Error('响应未返回有效载入令牌，请重新读取规则后重试')
    return { rules: body.rules as Record<string, any[]>, loaded: (body.loaded ?? {}) as Record<string, string | null>, changed_slot_keys: Array.isArray(body.changed_slot_keys) ? body.changed_slot_keys.filter((key: unknown): key is string => typeof key === 'string') : [] }
  }
  function validateLoadedChanges() {
    const matched: Record<string, Set<number>> = {}
    for (const original of loadedRules) {
      const used = matched[original.node] ||= new Set<number>()
      const unchanged = (rulesMap.value[original.node] || []).findIndex((r, index) => !used.has(index) && (r.slot_key ?? undefined) === original.slot && r.rule_id === original.ruleId && JSON.stringify(ruleFields(r)) === original.definition)
      if (unchanged >= 0) { used.add(unchanged); continue }
      // 检查原集合中的改写/删除槽；新增不在快照中，明确的 null 版本仍原样回传。
      if (original.slot == null || !own(tokens.value, original.slot)) throw new Error('既有规则缺少载入令牌，请重新读取规则后重试')
    }
  }
  const saving = ref(false), unsaved = ref(false)
  let pendingSave: Promise<boolean> | null = null
  const isCrossCheckMode = computed(() => deps.selectedNodeKey.value.startsWith('cross_')), rulesForCurrent = computed(() => rulesMap.value[deps.selectedNodeKey.value] || [])
  let epoch = 0, execSeq = 0, loadSeq = 0, saveSeq = 0, runSeq = 0, revision = 0, alive = true
  const snapshot = () => ({ pid: deps.projectId.value, year: deps.year.value, key: deps.currentProjectCacheKey.value, epoch })
  const current = (s: ReturnType<typeof snapshot>) => alive && s.epoch === epoch && s.pid === deps.projectId.value && s.year === deps.year.value && deps.shouldApplyResponse(s.key, deps.currentProjectCacheKey.value)
  const expression = (r: any) => `${r.left_ref || ''} ${r.operator || '='} ${r.right_ref || ''}`.trim()
  function clearRuleResults() {
    for (const rows of Object.values(rulesMap.value)) for (const r of rows) {
      r._checked = false; r._pass = false; r._status = undefined; r._reason = ''; r._severity = undefined; r._leftVal = null; r._rightVal = null; r._diff = null
    }
  }
  function applyOutcomes(run: FormulaIssueRun) {
    const all = Object.values(rulesMap.value).flat()
    for (const r of all) {
      // 旧执行接口仅有哈希 ID 与完整表达式：只接受全规则集唯一精确表达式，不按序号猜。
      const expr = expression(r), matches = run.outcomes.filter((o) => o.formula_id.startsWith('user:') && o.expression === expr)
      const o = all.filter((other) => expression(other) === expr).length === 1 && matches.length === 1 ? matches[0] : undefined
      const issue = o && run.issues.find((i) => i.formula_id === o.formula_id)
      r._status = run.failed ? 'error' : o?.status ?? 'not_executed'; r._reason = run.failed ? run.error : o?.reason || issue?.reason || (o ? '' : '本次后端未返回可唯一匹配的规则结论')
      r._checked = !!o; r._pass = r._status === 'passed'; r._severity = formulaCheckSeverity(o?.severity ?? issue?.severity ?? r.severity)
      r._leftVal = formulaCheckNumber(o?.left_value !== undefined ? o.left_value : issue?.left_value); r._rightVal = formulaCheckNumber(o?.right_value !== undefined ? o.right_value : issue?.right_value)
      r._diff = o?.diff !== undefined ? formulaCheckNumber(o.diff) : r._leftVal !== null && r._rightVal !== null ? r._leftVal - r._rightVal : null
    }
  }
  async function fetchExecRun(): Promise<boolean> {
    const start = snapshot()
    if (pendingSave) await pendingSave
    if (!current(start) || unsaved.value) {
      if (current(start)) { clearRuleResults(); for (const rows of Object.values(rulesMap.value)) for (const r of rows) { r._status = 'not_executed'; r._reason = '规则尚未保存成功，请先重试保存'; r._severity = formulaCheckSeverity(r.severity) } }
      return false
    }
    const s = snapshot(), seq = ++execSeq, rev = revision
    const valid = () => current(s) && seq === execSeq && rev === revision
    execRun.value = emptyIssueRun(); execItems.value = { report_note: [], report_wp: [], note_wp: [] }; execEmpty.value = false; clearRuleResults()
    if (!s.pid || s.year == null) { execLoading.value = false; return false }
    execLoading.value = true
    let run = emptyIssueRun()
    try {
      const data = await deps.api.get(deps.projectFormula.reportCrossCheck(s.pid), { params: { year: Number(s.year) }, _silent: true })
      if (!valid()) return false
      run = issueHintFromRun(data)
    } catch (e: any) {
      if (!valid()) return false
      const detail = e?.response?.data?.detail ?? e?.data?.detail
      // 面板已有操作标题；原因字段保留后端原文，其他形状仍走统一中文兜底。
      run = failedIssueRun(typeof detail === 'string' && detail.trim() ? detail : formulaErrorText(e, '报表勾稽执行失败'))
    }
    finally { if (valid()) execLoading.value = false }
    if (!valid()) return false
    execRun.value = run; execEmpty.value = !run.executed && !run.failed; execLoaded.value = !run.failed; execCacheKey.value = s.key
    const icons: Record<string, string> = { passed: '✅', failed: '❌', not_executed: '⏸', not_applicable: '➖', error: '⚠️' }
    execItems.value = { report_note: run.outcomes.map((o) => ({ key: `cross_exec_${o.formula_id}`, label: o.description || o.formula_id, icon: icons[o.status!] || '⚠️', _formulaId: o.formula_id, _passed: o.passed, _status: o.status, _reason: o.reason, _severity: o.severity })), report_wp: [], note_wp: [] }
    applyOutcomes(run)
    return true
  }
  async function loadExecItems() {
    if ((execLoaded.value && deps.cacheKeyMatches(execCacheKey.value, deps.currentProjectCacheKey.value)) || !deps.projectId.value) return
    const s = snapshot()
    if (!await loadUserRules() || !current(s)) return
    await fetchExecRun()
  }
  async function refreshExec() { if (deps.projectId.value) await fetchExecRun() }
  async function loadUserRules(): Promise<boolean> {
    const s = snapshot(), seq = ++loadSeq, rev = revision
    if (!s.pid || saving.value || unsaved.value) return false
    try {
      const data = await deps.api.get(deps.projectFormula.crossCheckRules(s.pid), { _silent: true })
      if (!current(s) || seq !== loadSeq || rev !== revision || saving.value || unsaved.value) return false
      applyRulesData(data); return true
    } catch (e) { if (current(s) && seq === loadSeq) deps.showFormulaError(e, '表间审核规则读取失败'); return false }
  }
  function invalidateResults() {
    ++revision; ++execSeq; execLoaded.value = false; execRun.value = emptyIssueRun(); execItems.value = { report_note: [], report_wp: [], note_wp: [] }; execLoading.value = false; clearRuleResults()
  }
  function applyRulesData(data: any) {
    const body = readRulesData(data), next: Record<string, any[]> = {}
    for (const [key, rows] of Object.entries(body.rules)) next[key] = rows.map(r => ({ ...r, ...ruleFields(r), _editing: false }))
    tokens.value = { ...body.loaded }
    loadedRules = Object.entries(next).flatMap(([node, rows]) => rows.map(r => ({ node, slot: typeof r.slot_key === 'string' ? r.slot_key : undefined, ruleId: r.rule_id, definition: JSON.stringify(ruleFields(r)) })))
    rulesMap.value = next; invalidateResults()
  }
  function persist(): Promise<boolean> {
    if (!deps.guardFormulaMutation() || !deps.projectId.value) return Promise.resolve(false)
    if (pendingSave) return pendingSave
    const s = snapshot(), seq = ++saveSeq
    saving.value = true; unsaved.value = true; ++loadSeq; invalidateResults()
    const valid = () => current(s) && seq === saveSeq
    try { validateLoadedChanges() }
    catch (e) { saving.value = false; deps.showFormulaError(e, '表间审核规则保存失败'); return Promise.resolve(false) }
    const pending = (async () => {
      try {
        const rev = revision, payload: Record<string, any[]> = {}
        for (const [key, rows] of Object.entries(rulesMap.value)) payload[key] = rows.map((r) => ({ rule_id: r.rule_id || undefined, slot_key: r.slot_key, version_token: r.version_token, ...ruleFields(r) }))
        const data = await deps.api.put(deps.projectFormula.crossCheckRules(s.pid), { rules: payload, loaded: { ...tokens.value } })
        if (!valid()) return false
        const body = readRulesData(data, true)
        // UI 保存期间拒绝编辑；若外部仍替换了规则，不猜测新规则身份、不自动重发。
        if (rev !== revision) throw new Error('保存期间规则已变化，请重新读取规则后重试')
        applyRulesData(body); unsaved.value = false
        deps.askApplyScope('cross_check', body.changed_slot_keys || [])
        return true
      } catch (e) { if (valid()) deps.showFormulaError(e, '表间审核规则保存失败'); return false }
      finally { if (valid()) saving.value = false }
    })()
    pendingSave = pending
    void pending.then(() => { if (pendingSave === pending) pendingSave = null })
    return pending
  }
  const showDialog = ref(false), dialogTitle = ref('新增规则'), editIndex = ref(-1)
  const blankForm = () => ({ label: '', left_ref: '', operator: '=', right_ref: '', description: '', tolerance: null as number | string | null | undefined, severity: 'warning' as 'blocking' | 'warning' | 'info' })
  const form = ref(blankForm())
  let editNode = ''
  function canEdit() { if (!saving.value) return true; deps.showFormulaError(new Error('规则正在保存，请稍后重试'), '规则正在保存'); return false }
  function onAdd() { if (!canEdit()) return; editNode = deps.selectedNodeKey.value; dialogTitle.value = '新增表间审核规则'; editIndex.value = -1; form.value = blankForm(); showDialog.value = true }
  function onEdit(row: any, index: number) {
    if (!canEdit()) return
    editNode = deps.selectedNodeKey.value; dialogTitle.value = '编辑表间审核规则'; editIndex.value = index
    form.value = { label: row.label || '', left_ref: row.left_ref || '', operator: row.operator || '=', right_ref: row.right_ref || '', description: row.description || '', tolerance: row.tolerance, severity: formulaCheckSeverity(row.severity) }; showDialog.value = true
  }
  function onSave() {
    if (!canEdit() || !deps.guardFormulaMutation() || editNode !== deps.selectedNodeKey.value) return
    const rows = rulesMap.value[editNode] ||= [], patch = { ...form.value, _editing: false }
    if (editIndex.value >= 0) { if (!rows[editIndex.value]) return; Object.assign(rows[editIndex.value], patch) } else rows.push(patch)
    unsaved.value = true; invalidateResults(); showDialog.value = false; void persist()
  }
  function onRemove(index: number) { if (!canEdit() || !deps.guardFormulaMutation()) return; rulesForCurrent.value.splice(index, 1); unsaved.value = true; invalidateResults(); void persist() }
  async function run() {
    if (!rulesForCurrent.value.length || !deps.projectId.value || deps.year.value == null) return
    const seq = ++runSeq, s = snapshot(), node = deps.selectedNodeKey.value
    running.value = true
    try {
      if (!await fetchExecRun() || !current(s) || seq !== runSeq || node !== deps.selectedNodeKey.value) return
      const rows = rulesMap.value[node] || []
      return { passCount: rows.filter((r) => r._status === 'passed').length, failCount: rows.filter((r) => r._status === 'failed').length }
    } finally { if (current(s) && seq === runSeq) running.value = false }
  }
  function resetCache() {
    ++epoch; ++execSeq; ++loadSeq; ++saveSeq; ++runSeq; ++revision
    execLoaded.value = false; execCacheKey.value = null; execEmpty.value = false; execRun.value = emptyIssueRun(); execItems.value = { report_note: [], report_wp: [], note_wp: [] }
    execLoading.value = false; running.value = false; saving.value = false; unsaved.value = false; pendingSave = null; rulesMap.value = {}; tokens.value = {}; loadedRules = []; showDialog.value = false
  }
  watch([deps.projectId, deps.year, deps.currentProjectCacheKey], resetCache, { flush: 'sync' })
  watch(deps.selectedNodeKey, () => { ++execSeq; ++runSeq; execLoading.value = false; running.value = false; showDialog.value = false }, { flush: 'sync' })
  onScopeDispose(() => { alive = false; resetCache() })
  return { execItems, execLoaded, execEmpty, execRun, execLoading, isCrossCheckMode, rulesMap, rulesForCurrent, tokens, loadExecItems, refreshExec, loadUserRules, applyRulesData, persist, resetCache, showDialog, dialogTitle, editIndex, form, onAdd, onEdit, onSave, onRemove, saving, unsaved, running, run }
}
