/**
 * 表间审核用户规则（加载 / 保存 / CRUD / 执行）—— 从 FormulaManagerDialog 拆出。
 *
 * spec formula-global-settings-sync Phase 4 / R10.2：用户规则存 formula_setting，
 * 全局 + 本项目两层，差量写入与 CAS（缺令牌 428、过期 409）；保存后弹应用范围（changed_slot_keys）。
 */
import { computed, ref, type Ref } from 'vue'
import type { CROSS_CHECK_NODE_KEYS as _Keys } from '../crossCheckKey'

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

const DEFAULT_SEEDS: Record<string, any[]> = {
  cross_report_note: [
    { label: 'BS货币资金 = 附注货币资金合计', left_ref: "REPORT('BS-002','期末')", right_ref: "NOTE('货币资金','合计','期末')", _editing: false },
    { label: 'BS应收账款 = 附注应收账款合计', left_ref: "REPORT('BS-008','期末')", right_ref: "NOTE('应收账款','合计','期末')", _editing: false },
    { label: 'IS营业收入 = 附注营业收入合计', left_ref: "REPORT('IS-002','本期')", right_ref: "NOTE('营业收入','合计','本期')", _editing: false },
  ],
  cross_report_wp: [
    { label: 'BS货币资金 = E1-1审定数', left_ref: "REPORT('BS-002','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
    { label: 'BS应收账款 = D2-1审定数', left_ref: "REPORT('BS-008','期末')", right_ref: "WP('D2-1','审定数')", _editing: false },
  ],
  cross_note_wp: [
    { label: '附注货币资金 = E1-1审定数', left_ref: "NOTE('货币资金','合计','期末')", right_ref: "WP('E1-1','审定数')", _editing: false },
  ],
  cross_consol: [
    { label: '合并抵消分录借贷平衡', left_ref: "CONSOL('抵消分录','借方合计')", right_ref: "CONSOL('抵消分录','贷方合计')", _editing: false },
    { label: '模拟权益法长投 = 净资产×持股比例', left_ref: "CONSOL('模拟权益法','期末长投小计')", right_ref: "CONSOL('净资产表','期末净资产') × 持股比例", _editing: false },
    { label: '资本公积变动期末 = 合并报表期末', left_ref: "CONSOL('资本公积变动','期末金额')", right_ref: "REPORT('BS-资本公积','期末')", _editing: false },
  ],
}

export function useCrossCheckRules(deps: CrossCheckDeps) {
  // ── 执行结果（7 条内置 logic_check 勾稽 + 用户规则执行结果） ──
  const execItems = ref<Record<string, any[]>>({ report_note: [], report_wp: [], note_wp: [] })
  const execLoaded = ref(false)
  const execCacheKey = ref<string | null>(null)
  const execEmpty = ref(false)

  // ── 用户可编辑规则（按树节点 key 分组） ──
  const rulesMap = ref<Record<string, any[]>>(
    Object.fromEntries(Object.entries(DEFAULT_SEEDS).map(([k, v]) => [k, v.map(r => ({ ...r }))]))
  )
  const tokens = ref<Record<string, string>>({})

  const isCrossCheckMode = computed(() => deps.selectedNodeKey.value.startsWith('cross_'))
  const rulesForCurrent = computed(() => rulesMap.value[deps.selectedNodeKey.value] || [])

  // ── 加载执行结果（7 条 logic_check + 用户规则的 passed/描述） ──
  async function loadExecItems() {
    if ((execLoaded.value && deps.cacheKeyMatches(execCacheKey.value, deps.currentProjectCacheKey.value))
        || !deps.projectId.value) return
    const reqKey = deps.currentProjectCacheKey.value
    if (deps.year.value != null) {
      try {
        const data = await deps.api.get(deps.projectFormula.reportCrossCheck(deps.projectId.value), {
          params: { year: Number(deps.year.value) },
          _silent: true, validateStatus: (s: number) => s < 600,
        } as any)
        if (!deps.shouldApplyResponse(reqKey, deps.currentProjectCacheKey.value)) return
        const results: any[] = Array.isArray(data?.results) ? data.results
          : (Array.isArray(data?.data?.results) ? data.data.results : [])
        if (results.length) {
          execEmpty.value = false
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
          await loadUserRules()
          return
        }
      } catch { /* 落到「无结果」 */ }
    }
    if (!deps.shouldApplyResponse(reqKey, deps.currentProjectCacheKey.value)) return
    execEmpty.value = true
    execItems.value = { report_note: [], report_wp: [], note_wp: [] }
    execLoaded.value = true
    execCacheKey.value = reqKey
    await loadUserRules()
  }

  async function loadUserRules() {
    if (!deps.projectId.value) return
    try {
      const data: any = await deps.api.get(deps.projectFormula.crossCheckRules(deps.projectId.value), {
        _silent: true, validateStatus: (s: number) => s < 600,
      } as any)
      applyRulesData(data)
    } catch { /* 读失败保留内存默认 */ }
  }

  function applyRulesData(data: any) {
    const rules = data?.rules ?? data?.data?.rules ?? null
    if (!rules || typeof rules !== 'object') return
    tokens.value = data?.loaded ?? data?.data?.loaded ?? {}
    for (const [nodeKey, nodeRules] of Object.entries(rules)) {
      if (!Array.isArray(nodeRules)) continue
      rulesMap.value[nodeKey] = (nodeRules as any[]).map((r) => ({
        rule_id: r.rule_id || undefined, label: r.label || '', left_ref: r.left_ref || '',
        operator: r.operator || '=', right_ref: r.right_ref || '', description: r.description || '',
        layer: r.layer, pending: r.pending, _editing: false,
      }))
    }
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
  }

  return {
    execItems, execLoaded, execEmpty, isCrossCheckMode,
    rulesMap, rulesForCurrent, tokens,
    loadExecItems, loadUserRules, applyRulesData, persist, resetCache,
    showDialog, dialogTitle, editIndex, form, onAdd, onEdit, onSave, onRemove,
    running, run,
  }
}
