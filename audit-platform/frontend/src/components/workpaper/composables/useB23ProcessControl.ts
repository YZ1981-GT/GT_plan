/**
 * useB23ProcessControl — B23 业务层面控制主 composable（14 循环重做）
 *
 * Spec: .kiro/specs/b23-business-control-rework/ | Task: 2.1
 *
 * 职责：
 * - 14 循环卡片管理（展开/收起/适用性）
 * - 21 列控制矩阵 CRUD（per cycle）
 * - 穿行测试（验设计）/ 控制测试（验运行）分层 CRUD（wt-* 与 ct-* 独立命名空间）
 * - 缺陷 CRUD（A14-4 分级）
 * - 循环级结论自动建议
 * - 仪表盘统计 / 联动信息 / EventBus / Entity_Level_Context
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB23FormData'
import { B23_CYCLES, type B23CycleDef } from './b23CycleConfig'

// ─── 常量（导出供测试/组件） ──────────────────────────────────────────────

export const PROCESS_CONCLUSION_COLOR_MAP: Record<string, { color: string; bg: string; label: string }> = {
  '设计有效且已实施':     { color: '#52c41a', bg: '#f6ffed', label: '有效' },
  '设计有效但未有效实施': { color: '#faad14', bg: '#fffbe6', label: '部分有效' },
  '设计无效':            { color: '#ff4d4f', bg: '#fff2f0', label: '无效' },
  '不适用':              { color: '#bfbfbf', bg: '#fafafa', label: '不适用' },
  '待测试':              { color: '#1890ff', bg: '#e6f7ff', label: '待测试' },
}

export const CONCLUSION_TO_B50_IMPACT: Record<string, string> = {
  '设计有效且已实施':     '控制风险=低',
  '设计有效但未有效实施': '控制风险=中',
  '设计无效':            '控制风险=高',
  '不适用':              '不影响控制风险评估',
}

/** 枚举选项（供组件下拉/多选） */
export const ASSERTION_OPTIONS = ['存在', '发生', '完整性', '准确性', '计价分摊', '权利义务', '列报'] as const
export const FREQUENCY_OPTIONS = ['每笔', '每日', '每周', '每月', '每季', '每年', '不定期', '定期'] as const
export const PREVENT_DETECT_OPTIONS = ['预防性', '检查性'] as const
export const CTRL_TYPE_L1_OPTIONS = ['授权和审批', '监督控制', '信息处理', '实物控制', '职责分离', '绩效评价复核'] as const
export const YES_NO_OPTIONS = ['是', '否'] as const
export const WT_AS_DESIGNED_OPTIONS = ['是', '否'] as const
export const CONTROL_TEST_RESULT_OPTIONS = ['有效', '无效'] as const
export const DEFICIENCY_TYPE_OPTIONS = ['缺乏控制', '设计不合理', '未执行'] as const
export const DEFICIENCY_SEVERITY_OPTIONS = ['重大缺陷', '重要缺陷', '一般缺陷'] as const
export const CYCLE_CONCLUSION_OPTIONS = ['设计有效且已实施', '设计有效但未有效实施', '设计无效', '不适用'] as const

// ─── 类型 ────────────────────────────────────────────────────────────────────

export type CycleConclusion = '设计有效且已实施' | '设计有效但未有效实施' | '设计无效' | '不适用'
export type ControlFrequency = typeof FREQUENCY_OPTIONS[number]
export type YesNo = '是' | '否'

/** 21 列控制点 */
export interface B23ControlPoint {
  index: number
  subProcess: string
  ctrlNo: string
  ctrlName: string
  ctrlDesc: string
  affectedItems: string
  assertion: string[]           // 多选
  wcgwRef: string
  wcgwDetail: string
  ctrlAttr: string
  frequency: ControlFrequency | null
  itApp: string
  preventDetect: '预防性' | '检查性' | null
  designEffective: YesNo | null
  ctrlTypeL1: string | null
  ctrlTypeL2: string | null
  executor: string
  executorOrg: string
  hasDoc: YesNo | null
  isKeyControl: YesNo | null
  doControlTest: YesNo | null
}

/** 穿行测试记录（验设计） */
export interface B23WalkthroughTest {
  ctrlIndex: number
  method: string[]              // 多选
  interviewee: string
  procedure: string
  evidence: string
  result: string
  asDesigned: YesNo | null
  deficiencyFound: string
}

/** 控制测试记录（验运行） */
export interface B23ControlTest {
  ctrlIndex: number
  riskJudgment: string
  testNature: string
  testTiming: string
  testScope: string
  operatingEffective: '有效' | '无效' | null
  deviation: string
  substantiveImpact: string
}

/** 缺陷记录（A14-4 分级） */
export interface B23Deficiency {
  index: number
  subProcess: string
  description: string
  deficiencyType: '缺乏控制' | '设计不合理' | '未执行' | null
  severity: '重大缺陷' | '重要缺陷' | '一般缺陷' | null
  impact: string
}

/** 循环卡片 */
export interface B23CycleCard {
  code: string
  wpCode: string
  name: string
  subjectCycle: string
  isSpecial: boolean
  applicable: boolean
  conclusion: CycleConclusion | null
  suggestedConclusion: CycleConclusion | null
  conclusionOverridden: boolean
  overrideReason: string
  controlPoints: B23ControlPoint[]
  walkthroughs: B23WalkthroughTest[]
  controlTests: B23ControlTest[]
  deficiencies: B23Deficiency[]
  keyControlCount: number
  walkthroughComplete: boolean
  controlTestComplete: boolean
  deficiencyCount: number
  completionRatio: string
}

/** 仪表盘统计 */
export interface DashboardStats {
  applicableCount: number
  completedCount: number
  totalControlPoints: number
  totalKeyControls: number
  pendingWalkthroughCount: number
  pendingControlTestCount: number
  totalDeficiencies: number
  effectivenessDistribution: { effective: number; partiallyEffective: number; ineffective: number; notApplicable: number }
}

/** Entity_Level_Context（B22A 只读） */
export interface EntityLevelContext {
  elementScores: Record<number, string | null>
  overallConclusion: string | null
  completed: boolean
}

export interface ControlConclusionPayload {
  elementScores: Record<number, string | null>
  itDependency: string
  itgcConclusion: string | null
  overallConclusion: string | null
}

/** 联动信息 */
export interface LinkageInfo {
  code: string
  name: string
  conclusion: CycleConclusion | null
  b50Impact: string
  cTests: string[]
  substantiveCycles: string[]
  needsExtendedProcedures: boolean
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

type IdType =
  | 'applicability' | 'cycle-conclusion' | 'conclusion-override'
  | 'ctrl-count' | 'ctrl'
  | 'wt' | 'ct'
  | 'def-count' | 'def'
  | 'subproc'

// ─── 纯函数（导出供 PBT） ─────────────────────────────────────────────────────

/**
 * 生成 item_id（cycle-keyed，前缀 B23-{code}-）
 */
export function generateItemId(
  cycleCode: string,
  type: IdType,
  a?: number,
  b?: number,
  field?: string,
): string {
  const p = `B23-${cycleCode}`
  switch (type) {
    case 'applicability':        return `${p}-applicability`
    case 'cycle-conclusion':     return `${p}-cycle-conclusion`
    case 'conclusion-override':  return `${p}-conclusion-override`
    case 'ctrl-count':           return `${p}-ctrl-count`
    case 'ctrl':                 return `${p}-ctrl-${a}-${field}`
    case 'wt':                   return `${p}-wt-${a}-${field}`
    case 'ct':                   return `${p}-ct-${a}-${field}`
    case 'def-count':            return `${p}-def-count`
    case 'def':                  return `${p}-def-${a}-${field}`
    case 'subproc':              return `${p}-subproc-${a}-name`
  }
}

/** 循环级结论自动建议（基于控制测试运行有效性 + 缺陷分布，30% 阈值） */
export function suggestCycleConclusion(
  controlTests: B23ControlTest[],
  deficiencies: B23Deficiency[],
): CycleConclusion | null {
  const evaluated = controlTests.filter((ct) => ct.operatingEffective !== null)
  if (evaluated.length === 0) {
    // 无控制测试结论时，看是否已识别重大/重要缺陷
    if (deficiencies.some((d) => d.severity === '重大缺陷' || d.severity === '重要缺陷')) return '设计无效'
    return null
  }
  const ineffective = evaluated.filter((ct) => ct.operatingEffective === '无效')
  if (ineffective.length === 0) return '设计有效且已实施'
  const ratio = ineffective.length / evaluated.length
  if (ratio <= 0.3) return '设计有效但未有效实施'
  return '设计无效'
}

/** 控制点是否可进入测试对象集合（仅关键控制点） */
export function eligibleForTest(cp: B23ControlPoint): boolean {
  return cp.isKeyControl === '是'
}

/** 是否建议执行控制测试（关键控制 ∧ 穿行按设计执行） */
export function suggestControlTest(cp: B23ControlPoint, wt: B23WalkthroughTest | undefined): boolean {
  return eligibleForTest(cp) && wt?.asDesigned === '是'
}

/** 缺陷提示（设计无效 或 穿行未按设计执行 → 必有提示） */
export function deficiencyHints(cp: B23ControlPoint, wt: B23WalkthroughTest | undefined): string[] {
  const hints: string[] = []
  if (cp.designEffective === '否') {
    hints.push(`控制点 ${cp.ctrlNo || cp.index}（${cp.ctrlName || ''}）：控制设计无效，需识别缺陷`)
  }
  if (wt?.asDesigned === '否') {
    hints.push(`控制点 ${cp.ctrlNo || cp.index}（${cp.ctrlName || ''}）：穿行测试未按设计执行，需识别缺陷并评估对实质性程序范围的影响`)
  }
  return hints
}

/** 适用性过滤（幂等）：返回适用循环子集 */
export function applicableCycles<T extends { applicable: boolean }>(cycles: T[]): T[] {
  return cycles.filter((c) => c.applicable)
}

// ─── 主 composable ─────────────────────────────────────────────────────────

export function useB23ProcessControl(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn,
) {
  // ─── 展开/收起 ───────────────────────────────────────────────────────────
  const expandedCycles = ref<Set<string>>(new Set())
  const selectedCycle = ref<string>('')

  function selectCycle(code: string): void {
    selectedCycle.value = code
    const s = new Set(expandedCycles.value)
    s.add(code)
    expandedCycles.value = s
  }
  function toggleCycle(code: string): void {
    const s = new Set(expandedCycles.value)
    if (s.has(code)) s.delete(code)
    else s.add(code)
    expandedCycles.value = s
  }
  function expandAll(): void { expandedCycles.value = new Set(B23_CYCLES.map((c) => c.code)) }
  function collapseAll(): void { expandedCycles.value = new Set(); selectedCycle.value = '' }

  // ─── 读写辅助 ─────────────────────────────────────────────────────────────
  function getResp(itemId: string): ChecklistResponse {
    return allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null, wp_ref: null }
  }
  function setLocal(itemId: string, conclusion: string | null, remark: string | null = null, wpRef: string | null = null): ChecklistItem {
    const item: ChecklistItem = { item_id: itemId, conclusion, remark, wp_ref: wpRef }
    allResponses.value.set(itemId, item)
    return item
  }

  // ─── 适用性 ───────────────────────────────────────────────────────────────
  function getApplicability(code: string): boolean {
    return getResp(generateItemId(code, 'applicability')).conclusion !== 'N'
  }
  function setApplicability(code: string, applicable: boolean): void {
    const items: ChecklistItem[] = [setLocal(generateItemId(code, 'applicability'), applicable ? 'Y' : 'N')]
    if (!applicable) {
      items.push(setLocal(generateItemId(code, 'cycle-conclusion'), '不适用'))
      const s = new Set(expandedCycles.value); s.delete(code); expandedCycles.value = s
    } else {
      // 恢复适用 → 清除自动"不适用"结论
      if (getResp(generateItemId(code, 'cycle-conclusion')).conclusion === '不适用') {
        items.push(setLocal(generateItemId(code, 'cycle-conclusion'), null))
      }
    }
    saveImmediate(items)
  }

  // ─── 控制点 CRUD ──────────────────────────────────────────────────────────
  const CTRL_TEXT_FIELDS = ['subProcess', 'ctrlNo', 'ctrlName', 'ctrlDesc', 'affectedItems', 'wcgwRef', 'wcgwDetail', 'ctrlAttr', 'itApp', 'executor', 'executorOrg'] as const
  const CTRL_ENUM_FIELDS = ['frequency', 'preventDetect', 'designEffective', 'ctrlTypeL1', 'ctrlTypeL2', 'hasDoc', 'isKeyControl', 'doControlTest'] as const

  function getCtrlCount(code: string): number {
    const n = parseInt(getResp(generateItemId(code, 'ctrl-count')).remark || '0', 10)
    return isNaN(n) ? 0 : n
  }
  function readControlPoint(code: string, m: number): B23ControlPoint {
    const t = (f: string) => getResp(generateItemId(code, 'ctrl', m, undefined, f)).remark || ''
    const e = (f: string) => getResp(generateItemId(code, 'ctrl', m, undefined, f)).conclusion
    const assertRaw = t('assertion')
    return {
      index: m,
      subProcess: t('subProcess'), ctrlNo: t('ctrlNo'), ctrlName: t('ctrlName'), ctrlDesc: t('ctrlDesc'),
      affectedItems: t('affectedItems'),
      assertion: assertRaw ? assertRaw.split(',').filter(Boolean) : [],
      wcgwRef: t('wcgwRef'), wcgwDetail: t('wcgwDetail'), ctrlAttr: t('ctrlAttr'), itApp: t('itApp'),
      executor: t('executor'), executorOrg: t('executorOrg'),
      frequency: e('frequency') as ControlFrequency | null,
      preventDetect: e('preventDetect') as '预防性' | '检查性' | null,
      designEffective: e('designEffective') as YesNo | null,
      ctrlTypeL1: e('ctrlTypeL1'), ctrlTypeL2: e('ctrlTypeL2'),
      hasDoc: e('hasDoc') as YesNo | null,
      isKeyControl: e('isKeyControl') as YesNo | null,
      doControlTest: e('doControlTest') as YesNo | null,
    }
  }
  function getControlPoints(code: string): B23ControlPoint[] {
    const count = getCtrlCount(code)
    const arr: B23ControlPoint[] = []
    for (let m = 1; m <= count; m++) arr.push(readControlPoint(code, m))
    return arr
  }
  function addControlPoint(code: string): void {
    const c = getCtrlCount(code)
    if (c >= 30) return
    saveImmediate([setLocal(generateItemId(code, 'ctrl-count'), null, String(c + 1))])
  }
  function removeControlPoint(code: string, index: number): void {
    const count = getCtrlCount(code)
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const allFields = [...CTRL_TEXT_FIELDS, 'assertion', ...CTRL_ENUM_FIELDS]
    for (let m = index; m < count; m++) {
      for (const f of allFields) {
        const src = getResp(generateItemId(code, 'ctrl', m + 1, undefined, f))
        items.push(setLocal(generateItemId(code, 'ctrl', m, undefined, f), src.conclusion, src.remark))
      }
      // 同步 wt/ct 记录下移
      for (const f of WT_FIELDS) {
        const src = getResp(generateItemId(code, 'wt', m + 1, undefined, f))
        items.push(setLocal(generateItemId(code, 'wt', m, undefined, f), src.conclusion, src.remark))
      }
      for (const f of CT_FIELDS) {
        const src = getResp(generateItemId(code, 'ct', m + 1, undefined, f))
        items.push(setLocal(generateItemId(code, 'ct', m, undefined, f), src.conclusion, src.remark))
      }
    }
    for (const f of allFields) items.push(setLocal(generateItemId(code, 'ctrl', count, undefined, f), null, null))
    for (const f of WT_FIELDS) items.push(setLocal(generateItemId(code, 'wt', count, undefined, f), null, null))
    for (const f of CT_FIELDS) items.push(setLocal(generateItemId(code, 'ct', count, undefined, f), null, null))
    items.push(setLocal(generateItemId(code, 'ctrl-count'), null, String(count - 1)))
    saveImmediate(items)
  }
  function buildCtrlFieldItem(code: string, index: number, field: string, value: any): ChecklistItem {
    const itemId = generateItemId(code, 'ctrl', index, undefined, field)
    if ((CTRL_ENUM_FIELDS as readonly string[]).includes(field)) {
      return setLocal(itemId, value as string | null)
    } else if (field === 'assertion') {
      return setLocal(itemId, null, (Array.isArray(value) ? value : []).join(','))
    }
    return setLocal(itemId, null, value == null ? '' : String(value))
  }
  function setControlPointField(code: string, index: number, field: string, value: any): void {
    saveImmediate([buildCtrlFieldItem(code, index, field, value)])
  }

  /** 批量写单个控制点的多个字段（引导式弹窗一次性提交，避免逐字段多次 PUT） */
  function setControlPointFields(code: string, index: number, partial: Partial<B23ControlPoint>): void {
    const items: ChecklistItem[] = []
    for (const [field, value] of Object.entries(partial)) {
      if (field === 'index') continue
      items.push(buildCtrlFieldItem(code, index, field, value))
    }
    if (items.length) saveImmediate(items)
  }

  /** 批量导入控制点（供 useB23ImportExport 回写；mode=skip 时仅填空锚点） */
  function importControlPoints(code: string, points: B23ControlPoint[], mode: 'overwrite' | 'skip'): void {
    const items: ChecklistItem[] = []
    const existing = mode === 'skip' ? getControlPoints(code) : []
    const newCount = mode === 'skip' ? Math.max(getCtrlCount(code), points.length) : points.length
    const writeField = (m: number, field: string, isEnum: boolean, value: string) => {
      if (mode === 'skip') {
        const cur = existing[m - 1] as any
        const curVal = cur ? (field === 'assertion' ? (cur.assertion || []).join(',') : (cur[field] ?? '')) : ''
        if (curVal) return // 已有值 → 跳过
      }
      const itemId = generateItemId(code, 'ctrl', m, undefined, field)
      items.push(isEnum ? setLocal(itemId, value || null) : setLocal(itemId, null, value))
    }
    points.forEach((cp, i) => {
      const m = i + 1
      for (const f of CTRL_TEXT_FIELDS) writeField(m, f, false, (cp as any)[f] ?? '')
      writeField(m, 'assertion', false, cp.assertion.join(','))
      for (const f of CTRL_ENUM_FIELDS) writeField(m, f, true, ((cp as any)[f] ?? '') as string)
    })
    items.push(setLocal(generateItemId(code, 'ctrl-count'), null, String(newCount)))
    saveImmediate(items)
  }

  // ─── 穿行测试（验设计） ──────────────────────────────────────────────────
  const WT_TEXT_FIELDS = ['interviewee', 'procedure', 'evidence', 'result', 'deficiencyFound'] as const
  const WT_FIELDS = ['method', ...WT_TEXT_FIELDS, 'asDesigned'] as const

  function readWalkthrough(code: string, m: number): B23WalkthroughTest {
    const t = (f: string) => getResp(generateItemId(code, 'wt', m, undefined, f)).remark || ''
    const methodRaw = t('method')
    return {
      ctrlIndex: m,
      method: methodRaw ? methodRaw.split(',').filter(Boolean) : [],
      interviewee: t('interviewee'), procedure: t('procedure'), evidence: t('evidence'),
      result: t('result'), deficiencyFound: t('deficiencyFound'),
      asDesigned: getResp(generateItemId(code, 'wt', m, undefined, 'asDesigned')).conclusion as YesNo | null,
    }
  }
  function getWalkthroughs(code: string): B23WalkthroughTest[] {
    return getControlPoints(code).map((cp) => readWalkthrough(code, cp.index))
  }
  function setWalkthroughField(code: string, ctrlIndex: number, field: string, value: any): void {
    const itemId = generateItemId(code, 'wt', ctrlIndex, undefined, field)
    let item: ChecklistItem
    if (field === 'asDesigned') item = setLocal(itemId, value as string | null)
    else if (field === 'method') item = setLocal(itemId, null, (value as string[]).join(','))
    else item = setLocal(itemId, null, value as string)
    saveImmediate([item])
  }

  // ─── 控制测试（验运行） ──────────────────────────────────────────────────
  const CT_TEXT_FIELDS = ['riskJudgment', 'testNature', 'testTiming', 'testScope', 'deviation', 'substantiveImpact'] as const
  const CT_FIELDS = [...CT_TEXT_FIELDS, 'operatingEffective'] as const

  function readControlTest(code: string, m: number): B23ControlTest {
    const t = (f: string) => getResp(generateItemId(code, 'ct', m, undefined, f)).remark || ''
    return {
      ctrlIndex: m,
      riskJudgment: t('riskJudgment'), testNature: t('testNature'), testTiming: t('testTiming'),
      testScope: t('testScope'), deviation: t('deviation'), substantiveImpact: t('substantiveImpact'),
      operatingEffective: getResp(generateItemId(code, 'ct', m, undefined, 'operatingEffective')).conclusion as '有效' | '无效' | null,
    }
  }
  function getControlTests(code: string): B23ControlTest[] {
    return getControlPoints(code).map((cp) => readControlTest(code, cp.index))
  }
  function setControlTestField(code: string, ctrlIndex: number, field: string, value: any): void {
    const itemId = generateItemId(code, 'ct', ctrlIndex, undefined, field)
    const item = field === 'operatingEffective'
      ? setLocal(itemId, value as string | null)
      : setLocal(itemId, null, value as string)
    saveImmediate([item])
    // 控制测试结论变化 → 发布控制风险事件供 B50
    if (field === 'operatingEffective') publishControlRiskChanged(code)
  }

  // ─── 缺陷 CRUD ────────────────────────────────────────────────────────────
  const DEF_TEXT_FIELDS = ['subProcess', 'description', 'impact'] as const
  const DEF_ENUM_FIELDS = ['deficiencyType', 'severity'] as const

  function getDefCount(code: string): number {
    const n = parseInt(getResp(generateItemId(code, 'def-count')).remark || '0', 10)
    return isNaN(n) ? 0 : n
  }
  function readDeficiency(code: string, d: number): B23Deficiency {
    const t = (f: string) => getResp(generateItemId(code, 'def', d, undefined, f)).remark || ''
    const e = (f: string) => getResp(generateItemId(code, 'def', d, undefined, f)).conclusion
    return {
      index: d, subProcess: t('subProcess'), description: t('description'), impact: t('impact'),
      deficiencyType: e('deficiencyType') as B23Deficiency['deficiencyType'],
      severity: e('severity') as B23Deficiency['severity'],
    }
  }
  function getDeficiencies(code: string): B23Deficiency[] {
    const count = getDefCount(code)
    const arr: B23Deficiency[] = []
    for (let d = 1; d <= count; d++) arr.push(readDeficiency(code, d))
    return arr
  }
  function addDeficiency(code: string): void {
    const c = getDefCount(code)
    if (c >= 50) return
    saveImmediate([setLocal(generateItemId(code, 'def-count'), null, String(c + 1))])
  }
  function removeDeficiency(code: string, index: number): void {
    const count = getDefCount(code)
    if (index < 1 || index > count) return
    const items: ChecklistItem[] = []
    const fields = [...DEF_TEXT_FIELDS, ...DEF_ENUM_FIELDS]
    for (let d = index; d < count; d++) {
      for (const f of fields) {
        const src = getResp(generateItemId(code, 'def', d + 1, undefined, f))
        items.push(setLocal(generateItemId(code, 'def', d, undefined, f), src.conclusion, src.remark))
      }
    }
    for (const f of fields) items.push(setLocal(generateItemId(code, 'def', count, undefined, f), null, null))
    items.push(setLocal(generateItemId(code, 'def-count'), null, String(count - 1)))
    saveImmediate(items)
  }
  function setDeficiencyField(code: string, index: number, field: string, value: any): void {
    const itemId = generateItemId(code, 'def', index, undefined, field)
    const item = (DEF_ENUM_FIELDS as readonly string[]).includes(field)
      ? setLocal(itemId, value as string | null)
      : setLocal(itemId, null, value as string)
    saveImmediate([item])
  }

  // ─── 循环结论 ─────────────────────────────────────────────────────────────
  function getConclusion(code: string): CycleConclusion | null {
    return (getResp(generateItemId(code, 'cycle-conclusion')).conclusion as CycleConclusion | null) || null
  }
  function suggestConclusion(code: string): CycleConclusion | null {
    return suggestCycleConclusion(getControlTests(code), getDeficiencies(code))
  }
  function isConclusionOverridden(code: string): boolean {
    return getResp(generateItemId(code, 'conclusion-override')).conclusion === 'Y'
  }
  function getOverrideReason(code: string): string {
    return getResp(generateItemId(code, 'conclusion-override')).remark || ''
  }
  function setConclusion(code: string, conclusion: CycleConclusion, overrideReason?: string): void {
    const oldC = getConclusion(code)
    const suggested = suggestConclusion(code)
    const isOverride = suggested !== null && conclusion !== suggested
    const items: ChecklistItem[] = [setLocal(generateItemId(code, 'cycle-conclusion'), conclusion)]
    if (isOverride && overrideReason) items.push(setLocal(generateItemId(code, 'conclusion-override'), 'Y', overrideReason))
    else if (!isOverride) items.push(setLocal(generateItemId(code, 'conclusion-override'), null, null))
    saveImmediate(items)
    if (oldC !== conclusion) publishProcessConcluded(code, oldC, conclusion)
  }

  // ─── 子流程骨架 ───────────────────────────────────────────────────────────
  function getSubProcesses(code: string): string[] {
    const def = B23_CYCLES.find((c) => c.code === code)
    const stored: string[] = []
    let i = 1
    while (true) {
      const v = getResp(generateItemId(code, 'subproc', i)).remark
      if (v === null || v === undefined) break
      stored.push(v)
      i++
      if (i > 30) break
    }
    return stored.length > 0 ? stored : (def?.defaultSubProcesses ?? [])
  }

  // ─── 卡片列表 ─────────────────────────────────────────────────────────────
  const cycles: ComputedRef<B23CycleCard[]> = computed(() => {
    return B23_CYCLES.map((def: B23CycleDef): B23CycleCard => {
      const code = def.code
      const applicable = getApplicability(code)
      const controlPoints = getControlPoints(code)
      const walkthroughs = getWalkthroughs(code)
      const controlTests = getControlTests(code)
      const deficiencies = getDeficiencies(code)
      const keyControls = controlPoints.filter((cp) => cp.isKeyControl === '是')
      // 穿行完成：所有关键控制点均有 asDesigned 结论
      const wtNeeded = keyControls
      const walkthroughComplete = wtNeeded.length === 0 || wtNeeded.every((cp) => walkthroughs[cp.index - 1]?.asDesigned !== null)
      // 控制测试完成：doControlTest='是' 的控制点均有 operatingEffective
      const ctNeeded = controlPoints.filter((cp) => cp.doControlTest === '是')
      const controlTestComplete = ctNeeded.length === 0 || ctNeeded.every((cp) => controlTests[cp.index - 1]?.operatingEffective !== null)
      const withConc = controlTests.filter((ct) => ct.operatingEffective !== null).length
      return {
        code, wpCode: def.wpCode, name: def.name, subjectCycle: def.subjectCycle, isSpecial: !!def.isSpecial,
        applicable,
        conclusion: getConclusion(code),
        suggestedConclusion: suggestConclusion(code),
        conclusionOverridden: isConclusionOverridden(code),
        overrideReason: getOverrideReason(code),
        controlPoints, walkthroughs, controlTests, deficiencies,
        keyControlCount: keyControls.length,
        walkthroughComplete, controlTestComplete,
        deficiencyCount: deficiencies.length,
        completionRatio: `${withConc}/${ctNeeded.length || controlPoints.length}`,
      }
    })
  })

  // ─── 仪表盘 ───────────────────────────────────────────────────────────────
  const dashboardStats: ComputedRef<DashboardStats> = computed(() => {
    const cards = cycles.value
    let applicableCount = 0, completedCount = 0, totalControlPoints = 0, totalKeyControls = 0
    let pendingWalkthroughCount = 0, pendingControlTestCount = 0, totalDeficiencies = 0
    let effective = 0, partiallyEffective = 0, ineffective = 0, notApplicable = 0
    for (const c of cards) {
      totalControlPoints += c.controlPoints.length
      totalKeyControls += c.keyControlCount
      totalDeficiencies += c.deficiencyCount
      if (!c.applicable) { notApplicable++; continue }
      applicableCount++
      if (c.conclusion) completedCount++
      switch (c.conclusion) {
        case '设计有效且已实施': effective++; break
        case '设计有效但未有效实施': partiallyEffective++; break
        case '设计无效': ineffective++; break
      }
      c.controlPoints.forEach((cp) => {
        if (cp.isKeyControl === '是' && c.walkthroughs[cp.index - 1]?.asDesigned === null) pendingWalkthroughCount++
        if (cp.doControlTest === '是' && c.controlTests[cp.index - 1]?.operatingEffective === null) pendingControlTestCount++
      })
    }
    return {
      applicableCount, completedCount, totalControlPoints, totalKeyControls,
      pendingWalkthroughCount, pendingControlTestCount, totalDeficiencies,
      effectivenessDistribution: { effective, partiallyEffective, ineffective, notApplicable },
    }
  })

  // ─── 联动 ─────────────────────────────────────────────────────────────────
  const linkageInfo: ComputedRef<LinkageInfo[]> = computed(() => {
    return B23_CYCLES.map((def) => {
      const conclusion = getConclusion(def.code)
      return {
        code: def.code, name: def.name, conclusion,
        b50Impact: conclusion ? (CONCLUSION_TO_B50_IMPACT[conclusion] || '') : '',
        cTests: def.cTests, substantiveCycles: def.substantiveCycles,
        needsExtendedProcedures: conclusion === '设计无效' || conclusion === '设计有效但未有效实施',
      }
    })
  })

  // ─── Entity_Level_Context ────────────────────────────────────────────────
  const entityLevelContext = ref<EntityLevelContext | null>(null)
  function onControlConclusionChanged(payload: ControlConclusionPayload): void {
    entityLevelContext.value = {
      elementScores: { ...payload.elementScores },
      overallConclusion: payload.overallConclusion,
      completed: payload.overallConclusion !== null,
    }
  }

  // ─── EventBus ─────────────────────────────────────────────────────────────
  function publishProcessConcluded(code: string, oldC: CycleConclusion | null, newC: CycleConclusion): void {
    if (oldC === newC) return
    const def = B23_CYCLES.find((c) => c.code === code)
    try {
      window.dispatchEvent(new CustomEvent('process:control-concluded', {
        detail: { cycleCode: code, cycleName: def?.name, oldConclusion: oldC, newConclusion: newC },
      }))
    } catch { console.warn('[B23] publish process:control-concluded failed') }
  }
  function publishWalkthroughCompleted(code: string): void {
    const def = B23_CYCLES.find((c) => c.code === code)
    const wts = getWalkthroughs(code).filter((w) => w.asDesigned !== null)
    const effective = wts.filter((w) => w.asDesigned === '是').length
    try {
      window.dispatchEvent(new CustomEvent('process:walkthrough-completed', {
        detail: { cycleCode: code, cycleName: def?.name, controlPointCount: wts.length, effectiveRate: wts.length ? effective / wts.length : 1 },
      }))
    } catch { console.warn('[B23] publish process:walkthrough-completed failed') }
  }
  function publishControlRiskChanged(code: string): void {
    const def = B23_CYCLES.find((c) => c.code === code)
    try {
      window.dispatchEvent(new CustomEvent('process:control-risk-changed', {
        detail: { cycleCode: code, cycleName: def?.name, conclusion: getConclusion(code) },
      }))
    } catch { console.warn('[B23] publish process:control-risk-changed failed') }
  }

  return {
    // 展开/选择
    expandedCycles, selectedCycle, selectCycle, toggleCycle, expandAll, collapseAll,
    // 适用性
    getApplicability, setApplicability,
    // 控制点
    getControlPoints, addControlPoint, removeControlPoint, setControlPointField, setControlPointFields, importControlPoints,
    // 穿行/控制测试
    getWalkthroughs, setWalkthroughField, getControlTests, setControlTestField,
    // 缺陷
    getDeficiencies, addDeficiency, removeDeficiency, setDeficiencyField,
    // 结论
    getConclusion, suggestConclusion, setConclusion, isConclusionOverridden, getOverrideReason,
    // 子流程
    getSubProcesses,
    // 视图
    cycles, dashboardStats, linkageInfo,
    // Entity context
    entityLevelContext, onControlConclusionChanged,
    // EventBus
    publishProcessConcluded, publishWalkthroughCompleted, publishControlRiskChanged,
  }
}

export default useB23ProcessControl
