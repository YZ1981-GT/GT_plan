/**
 * useB22AControlMatrix — B22A 检查项CRUD/结论评估/Element_Score自动计算/缺陷追踪/IT依赖/续审继承/业务规则警告
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Task: 2.2
 *
 * 职责：
 * - 检查项 CRUD（per tab / per IT subPanel）
 * - Conclusion 设置含即时保存 + 缺陷标记
 * - Understanding_Method 多选存储（remark 逗号分隔）
 * - Element_Score 自动计算（有效/部分有效/无效规则）
 * - 手动覆盖 Element_Score（需理由）
 * - IT_Dependency 依赖程度控制
 * - ITGC 结论传递 + 警告
 * - 缺陷清单自动收集
 * - 汇总统计 + Tab完成状态
 * - 续审继承（priorYearData / markNoChange）
 * - 业务规则警告（控制环境薄弱 / IT控制薄弱）
 */
import { ref, computed, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useB22AFormData'
// BC-53 稳定行身份改造：行数组存储层（含 legacy 自动迁移）
import { useB22ARowStore } from './useB22ARowStore'
import {
  B22A_ROW_FIELDS,
  makeRowId,
  migrateLegacyPrefixedRows,
  parseRows,
  prefixedLegacyCountItemId,
  prefixedRowsItemId,
  prefixScope,
  resequence,
  serializeRows,
  type B22ARow,
} from './b22aRowIdentity'

// ─── Types ───────────────────────────────────────────────────────────────────

export type TabNumber = 1 | 2 | 3 | 4 | 5
export type Conclusion = '设计有效' | '设计无效' | '已实施' | '未实施' | '不适用'
export type UnderstandingMethod = '询问' | '观察' | '检查文件' | '穿行测试'
export type ElementScore = '有效' | '部分有效' | '无效'
export type ITDependency = '高' | '中' | '低'
export type ITSubPanel = 'env' | 'itgc' | 'app' | 'change' | 'access' | 'sod'
export type TabStatus = 'empty' | 'partial' | 'complete'

export interface CheckItem {
  index: number
  controlPoint: string
  description: string
  methods: UnderstandingMethod[]
  conclusion: Conclusion | null
  reference: string
  isPreset: boolean
  isDeficiency: boolean
  priorYearConclusion: Conclusion | null
  noChangeConfirmed: boolean
  noChangeConfirmer: string | null
  noChangeDate: string | null
}

export interface ElementStat {
  total: number
  effective: number
  deficient: number
  notApplicable: number
  incomplete: number
}

export interface DeficiencyItem {
  tab: TabNumber
  subPanel: ITSubPanel | null
  index: number
  controlPoint: string
  deficiencyType: '设计无效' | '未实施'
  elementName: string
}

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

// ─── Constants (exported for tests and components) ───────────────────────────

export const CONCLUSIONS: Conclusion[] = ['设计有效', '设计无效', '已实施', '未实施', '不适用']

export const UNDERSTANDING_METHODS: UnderstandingMethod[] = ['询问', '观察', '检查文件', '穿行测试']

export const SCORE_COLOR_MAP: Record<ElementScore | '不适用', { bg: string; text: string }> = {
  '有效':     { bg: '#D1FAE5', text: '#059669' },
  '部分有效': { bg: '#FEF3C7', text: '#D97706' },
  '无效':     { bg: '#FEE2E2', text: '#DC2626' },
  '不适用':   { bg: '#F3F4F6', text: '#6B7280' },
}

export const IT_SUB_PANELS: { key: ITSubPanel; label: string }[] = [
  { key: 'env', label: 'IT环境了解' },
  { key: 'itgc', label: 'IT通用控制(ITGC)' },
  { key: 'app', label: 'IT应用控制' },
  { key: 'change', label: '变更管理' },
  { key: 'access', label: '访问安全' },
  { key: 'sod', label: '职责分离' },
]

// 标签对齐致同 B22A 源模板 sheet（控制环境/风险评估/信息与沟通/监督 + IT）。
// 源模板企业层面无独立「控制活动」sheet（控制活动记录在业务层面 B23），
// 故 Tab4 命名为「控制活动与IT」以如实反映其内容（整体框架指引 + IT 一般控制了解）。
export const COSO_TABS: { tab: TabNumber; label: string; code: string }[] = [
  { tab: 1, label: '控制环境', code: 'T1' },
  { tab: 2, label: '风险评估过程', code: 'T2' },
  { tab: 3, label: '信息与沟通', code: 'T3' },
  { tab: 4, label: '控制活动与IT', code: 'T4' },
  { tab: 5, label: '监督', code: 'T5' },
]

// ─── 财务报告过程（B22A-4-5，信息与沟通下 4 个子过程）─────────────────────────

export type FrpKey = 'closing' | 'consolidation' | 'groupControl' | 'preparation'

export const FRP_SUBPROCESSES: { key: FrpKey; label: string; hint: string }[] = [
  { key: 'closing', label: '财务报表（期末）结账过程', hint: '期末计提、摊销、待摊、暂估、汇兑、结转损益等结账程序的了解。' },
  { key: 'consolidation', label: '合并过程', hint: '合并范围确定、内部交易与往来抵销、合并抵销分录编制与复核的了解。' },
  { key: 'groupControl', label: '集团层面控制', hint: '集团对成员单位的财务报告控制、集团政策统一、报表包审阅等的了解。' },
  { key: 'preparation', label: '财务报表编制过程', hint: '试算平衡→报表项目归集、附注编制、列报与披露完整性的了解。' },
]

// ─── IT 详细结构化（B22A-4-1 ~ 4-4-2 重建）───────────────────────────────────

/** IT 概要（B22A-4-1，复杂度判断）行字段 */
export const IT_SUMMARY_FIELDS = ['kind', 'appDesc', 'complexFactor', 'complexity'] as const
/** 系统清单（B22A-4-2）行字段 */
export const IT_SYSTEM_FIELDS = ['process', 'system', 'keyModule', 'indexNo', 'dependency', 'inScope', 'remark'] as const
/** IT 职责分离 SoD（B22A-4-4-2）行字段 */
export const IT_SOD_FIELDS = ['person', 'authApprove', 'accessRequest', 'supervision', 'businessProcess', 'hasSodIssue', 'hasDeficiency'] as const

/** IT 环境 4 维（B22A-4-3） */
export const IT_ENV_DIMENSIONS: { key: string; label: string; hint: string }[] = [
  { key: 'app', label: '应用程序', hint: '与财务报告相关的 IT 应用程序（ERP/业务系统/报表工具）及其功能范围。' },
  { key: 'infra', label: '基础设施', hint: '支持应用程序运行的数据库、操作系统、网络及硬件环境。' },
  { key: 'process', label: '流程', hint: '与 IT 相关的管理流程（变更、访问、运维、备份恢复等）。' },
  { key: 'infoProcessing', label: '信息处理', hint: '数据的产生、录入、处理、存储与报告方式，自动化控制与接口。' },
]

/** IT 一般控制 ITGC 分类（B22A-4-4-1） */
export const IT_ITGC_CATEGORIES: { key: string; label: string; hint: string }[] = [
  { key: 'security', label: '安全管理', hint: '逻辑访问、身份认证、权限授予与回收、特权账户管理。' },
  { key: 'techMaintenance', label: '技术引进开发与维护（技术维护）', hint: '程序变更管理、开发测试与生产分离、上线审批。' },
  { key: 'jobScheduling', label: '作业调度', hint: '批处理作业调度、异常监控与处理、任务失败重跑。' },
  { key: 'interface', label: '接口', hint: '系统间数据接口的完整性、准确性及异常处理。' },
]

export const IT_COMPLEXITY_OPTIONS = ['复杂', '不复杂'] as const
export const IT_COMPLEX_FACTOR_OPTIONS = [
  '与自动化和数据使用相关',
  '与IT应用程序和基础设施相关',
  '与IT流程相关',
] as const
export const IT_SUMMARY_KIND_OPTIONS = ['IT应用程序', 'IT基础设施'] as const
export const IT_SYSTEM_DEPENDENCY_OPTIONS = ['高', '中', '低'] as const
export const IT_YESNO_OPTIONS = ['是', '否'] as const
export const ITGC_CONCLUSION_OPTIONS = ['有效', '无效', '不适用'] as const

export interface ItRow { index: number; [field: string]: string | number }
export interface ItgcCategoryState { note: string; conclusion: string | null }
export interface FrpState { na: boolean; note: string }

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** Generate item_id for regular check items */
export function generateItemId(
  tab: TabNumber,
  index: number,
  field: 'point' | 'desc' | 'method' | 'conclusion' | 'ref' | 'nochange',
  subPanel?: ITSubPanel
): string {
  if (subPanel) {
    return `B22A-T${tab}-IT-${subPanel}-${index}-${field}`
  }
  return `B22A-T${tab}-item-${index}-${field}`
}

// 🔴 BC-53 改造后 count 键不再作为行数真源（行数组长度即行数），原 countItemId()
//    已无调用方故删除。legacy count 键仅在 useB22ARowStore 迁移路径回读一次
//    （见 b22aRowIdentity.legacyCountItemId）。

/** Generate score item_id */
function scoreItemId(tab: TabNumber): string {
  return `B22A-T${tab}-score`
}

/** Compute auto element score from check items */
export function computeAutoScore(items: CheckItem[]): ElementScore {
  const applicable = items.filter(i => i.conclusion && i.conclusion !== '不适用')
  if (applicable.length === 0) return '有效'

  const deficient = applicable.filter(
    i => i.conclusion === '设计无效' || i.conclusion === '未实施'
  )

  if (deficient.length === 0) return '有效'
  if (deficient.length / applicable.length <= 0.2) return '部分有效'
  return '无效'
}

/** Compute tab status from check items */
export function computeTabStatus(items: CheckItem[]): TabStatus {
  if (items.length === 0) return 'empty'
  const withConclusion = items.filter(i => i.conclusion !== null)
  if (withConclusion.length === 0) return 'empty'
  if (withConclusion.length === items.length) return 'complete'
  return 'partial'
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useB22AControlMatrix(
  allResponses: Ref<Map<string, ChecklistResponse>>,
  saveImmediate: SaveFn,
  saveDebouncedText?: (item: ChecklistItem) => void
) {
  const priorYearData = ref<Map<string, ChecklistResponse>>(new Map())
  const itDependency = ref<ITDependency>('中')

  /**
   * 稳定行身份存储层（BC-53 改造）。
   *
   * 🔴 对外 API 仍用 `index`（显示序号），内部解析为 rowId 后落进行数组。
   *    组件层 2661 行的 `row.index` 调用**零改动**。
   */
  const rowStore = useB22ARowStore({
    allResponses: allResponses as any,
    saveImmediate: saveImmediate as any,
  })
  const overallConclusion = ref<ElementScore | null>(null)

  /** 文本类字段保存：优先 debounce（若提供），否则退回即时保存 */
  function _saveText(item: ChecklistItem): void {
    allResponses.value.set(item.item_id, item)
    if (saveDebouncedText) saveDebouncedText(item)
    else void saveImmediate([item])
  }

  // ─── Internal helpers ──────────────────────────────────────────────────

  function getResponseValue(itemId: string): ChecklistResponse | undefined {
    return allResponses.value.get(itemId)
  }

  /**
   * 行数（BC-53 改造后取自行数组实际长度，不再读 count 键）。
   *
   * 🔴 legacy count 键与实际行数可能脱钩（静默丢行，BC-54）；行数组形态下
   *    长度即行数，不可能不一致。
   */
  function getCount(tab: TabNumber, subPanel?: ITSubPanel): number {
    return rowStore.rowCount(tab, subPanel)
  }

  /** 把行对象转成组件层消费的 CheckItem（index = 显示序号）。 */
  function rowToCheckItem(
    row: B22ARow,
    index: number,
    tab: TabNumber,
    subPanel?: ITSubPanel,
  ): CheckItem {
    const conclusion = (row.conclusion as Conclusion | null) || null
    const rawMethods = typeof row.method === 'string' ? row.method : ''
    const methods: UnderstandingMethod[] = rawMethods
      ? (rawMethods
          .split(',')
          .filter((m) =>
            UNDERSTANDING_METHODS.includes(m as UnderstandingMethod),
          ) as UnderstandingMethod[])
      : []

    // 上年结论仍按 legacy 键读（上年数据是历史快照，不迁移）
    const priorItem = priorYearData.value.get(
      generateItemId(tab, index, 'conclusion', subPanel),
    )
    const priorYearConclusion =
      (priorItem?.conclusion as Conclusion | null) || null

    return {
      index,
      controlPoint: typeof row.point === 'string' ? row.point : '',
      description: typeof row.desc === 'string' ? row.desc : '',
      methods,
      conclusion,
      reference: typeof row.ref === 'string' ? row.ref : '',
      isPreset: false, // preset detection handled by component layer
      isDeficiency: conclusion === '设计无效' || conclusion === '未实施',
      priorYearConclusion,
      noChangeConfirmed: row.nochange === 'Y',
      noChangeConfirmer:
        typeof row.nochangeConfirmer === 'string' ? row.nochangeConfirmer : null,
      noChangeDate:
        typeof row.nochangeDate === 'string' ? row.nochangeDate : null,
    }
  }

  function buildCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel): CheckItem {
    const row = rowStore.rowAt(tab, index, subPanel)
    if (!row) {
      return {
        index,
        controlPoint: '',
        description: '',
        methods: [],
        conclusion: null,
        reference: '',
        isPreset: false,
        isDeficiency: false,
        priorYearConclusion: null,
        noChangeConfirmed: false,
        noChangeConfirmer: null,
        noChangeDate: null,
      }
    }
    return rowToCheckItem(row, index, tab, subPanel)
  }

  // ─── Check Items CRUD ──────────────────────────────────────────────────

  function getCheckItems(tab: TabNumber, subPanel?: ITSubPanel): CheckItem[] {
    const rows = rowStore.readRows(tab, subPanel)
    return rows.map((row, i) => rowToCheckItem(row, i + 1, tab, subPanel))
  }

  function addCheckItem(tab: TabNumber, subPanel?: ITSubPanel): void {
    rowStore.appendRow(tab, subPanel)
  }

  /**
   * 批量套用示例控制点（源模板"控制点示例"一键预填）。
   * 在现有检查项后追加 examples 条，各自写入控制要点 remark；不覆盖已有行。
   */
  function addPresetCheckItems(tab: TabNumber, examples: string[], subPanel?: ITSubPanel): void {
    if (!examples || examples.length === 0) return
    // 每条示例一行，控制要点写 point；不覆盖已有行（追加语义与 legacy 一致）
    rowStore.appendRows(
      tab,
      examples.map((text) => ({ point: text })),
      subPanel,
    )
  }

  /**
   * 设置检查项的控制矩阵属性（B22B 登记册字段：反舞弊/频率/执行人/胜任能力/风险/自动人工/IT应用/拟测试/测试方法）。
   * 存于 -attrs 字段的 remark（JSON），不占用 conclusion 白名单。
   */
  function setControlAttrs(
    tab: TabNumber,
    index: number,
    attrs: Record<string, unknown>,
    subPanel?: ITSubPanel
  ): void {
    rowStore.patchRowAt(tab, index, { attrs }, subPanel)
  }

  function getControlAttrs(tab: TabNumber, index: number, subPanel?: ITSubPanel): Record<string, any> {
    const row = rowStore.rowAt(tab, index, subPanel)
    const attrs = row?.attrs
    if (attrs && typeof attrs === 'object') return attrs as Record<string, any>
    return {}
  }

  // ─── 管理层凌驾于控制之上（B22A-2，反舞弊特别风险 CAS 1141） ───────────────
  // 复用 subPanel 机制：tab=2 + subPanel='mo' → item_id `B22A-T2-IT-mo-{i}-{field}`

  const MO_TAB: TabNumber = 2
  const MO_SUBPANEL = 'mo' as unknown as ITSubPanel

  function getMoItems(): CheckItem[] {
    return getCheckItems(MO_TAB, MO_SUBPANEL)
  }
  function addMoItem(): void {
    addCheckItem(MO_TAB, MO_SUBPANEL)
  }
  function addMoPresets(examples: string[]): void {
    addPresetCheckItems(MO_TAB, examples, MO_SUBPANEL)
  }
  function removeMoItem(index: number): void {
    removeCheckItem(MO_TAB, index, MO_SUBPANEL)
  }
  function setMoConclusion(index: number, conclusion: Conclusion): void {
    setConclusion(MO_TAB, index, conclusion, MO_SUBPANEL)
  }
  function setMoMethods(index: number, methods: UnderstandingMethod[]): void {
    setUnderstandingMethod(MO_TAB, index, methods, MO_SUBPANEL)
  }

  /** 管理层凌驾关键判断：管理层是否未能识别应识别的重大错报风险（是/否 + 说明） */
  function getMoKeyJudgment(): { answer: string | null; note: string } {
    const ans = getResponseValue('B22A-MO-key-judgment')
    const note = getResponseValue('B22A-MO-key-judgment-desc')
    return { answer: ans?.conclusion ?? null, note: note?.remark ?? '' }
  }
  function setMoKeyJudgment(answer: string, note: string): void {
    const ansItem: ChecklistItem = { item_id: 'B22A-MO-key-judgment', conclusion: answer, remark: null, wp_ref: null }
    const noteItem: ChecklistItem = { item_id: 'B22A-MO-key-judgment-desc', conclusion: null, remark: note, wp_ref: null }
    allResponses.value.set(ansItem.item_id, ansItem)
    allResponses.value.set(noteItem.item_id, noteItem)
    saveImmediate([ansItem, noteItem])
  }

  /**
   * 删行（BC-53 改造：摘除行对象，**不搬迁任何字段值**）。
   *
   * ═══ 改造前的缺陷（已删除的实现）═══════════════════════════════════════
   *
   * 旧实现是「整块 shift 搬迁」：删第 3 行时把第 4..N 行的每个字段值逐个往前挪
   * 一格、再清空末行。两类真缺陷：
   *   ① OO 侧插/删行不走这套 shift ⇒ 两侧行号立刻脱钩，双向回写必错位
   *   ② 行身份是下标 ⇒ 指向「第 n 行」的外部引用（B22B 带入的控制点、复核线程
   *      锚点）删行后指向**别人的内容**而非失效 —— 静默错配
   *
   * 现在行身份是行对象内的稳定 `rowId`，删行只从数组摘除该对象，剩余行的
   * 身份 ↔ 内容绑定关系完全不变。
   */
  function removeCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel): void {
    rowStore.removeRowAt(tab, index, subPanel)
  }

  // ─── Conclusion ────────────────────────────────────────────────────────

  function setConclusion(tab: TabNumber, index: number, conclusion: Conclusion, subPanel?: ITSubPanel): void {
    rowStore.patchRowAt(tab, index, { conclusion }, subPanel)
  }

  // ─── Understanding Method ──────────────────────────────────────────────

  function setUnderstandingMethod(tab: TabNumber, index: number, methods: UnderstandingMethod[], subPanel?: ITSubPanel): void {
    rowStore.patchRowAt(tab, index, { method: methods.join(',') }, subPanel)
  }

  // ─── Element Score ─────────────────────────────────────────────────────

  function computeElementScore(tab: TabNumber): ElementScore {
    const items = getCheckItems(tab)
    return computeAutoScore(items)
  }

  function overrideElementScore(tab: TabNumber, score: ElementScore, reason: string): void {
    if (!reason.trim()) return // require reason

    const scoreId = scoreItemId(tab)
    const overrideId = `B22A-T${tab}-score-override`

    const scoreItem: ChecklistItem = {
      item_id: scoreId,
      conclusion: score,
      remark: null,
      wp_ref: null,
    }
    const overrideItem: ChecklistItem = {
      item_id: overrideId,
      conclusion: 'Y',
      remark: reason.trim(),
      wp_ref: null,
    }

    allResponses.value.set(scoreId, scoreItem)
    allResponses.value.set(overrideId, overrideItem)
    saveImmediate([scoreItem, overrideItem])
  }

  function isScoreOverridden(tab: TabNumber): boolean {
    const overrideId = `B22A-T${tab}-score-override`
    const item = getResponseValue(overrideId)
    return item?.conclusion === 'Y'
  }

  function getEffectiveScore(tab: TabNumber): ElementScore | null {
    const scoreId = scoreItemId(tab)
    const item = getResponseValue(scoreId)
    if (item?.conclusion) return item.conclusion as ElementScore
    // Auto-compute
    const items = getCheckItems(tab)
    if (items.length === 0) return null
    return computeAutoScore(items)
  }

  // ─── IT Dependency ─────────────────────────────────────────────────────

  function initITDependency(): void {
    const item = getResponseValue('B22A-T4-IT-dependency')
    if (item?.conclusion) {
      itDependency.value = item.conclusion as ITDependency
    }
  }

  function setITDependency(level: ITDependency): void {
    itDependency.value = level
    const item: ChecklistItem = {
      item_id: 'B22A-T4-IT-dependency',
      conclusion: level,
      remark: null,
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  // ─── ITGC Conclusion ──────────────────────────────────────────────────

  const itgcConclusion: ComputedRef<ElementScore | null> = computed(() => {
    // 优先：新结构 ITGC 分类结论（B22A-4-4-1 重建，读取键 B22A-it-itgc-{cat}-conclusion）
    const catValues = IT_ITGC_CATEGORIES
      .map((c) => getResponseValue(`B22A-it-itgc-${c.key}-conclusion`)?.conclusion)
      .filter((v): v is string => !!v)
    const applicable = catValues.filter((v) => v !== '不适用')
    if (applicable.length > 0) {
      // 任一分类无效 → ITGC 无效（保证 itControlWeakWarning 不失效）
      return applicable.some((v) => v === '无效') ? '无效' : '有效'
    }
    // 回退：旧结构（迁移前 / 向后兼容）
    const item = getResponseValue('B22A-T4-IT-itgc-score')
    if (item?.conclusion) return item.conclusion as ElementScore
    // Auto-compute from legacy itgc check items
    const items = getCheckItems(4, 'itgc')
    if (items.length === 0) return null
    return computeAutoScore(items)
  })

  const isITGCInvalid: ComputedRef<boolean> = computed(() => {
    return itgcConclusion.value === '无效'
  })

  // ─── Deficiency List ───────────────────────────────────────────────────

  const deficiencyList: ComputedRef<DeficiencyItem[]> = computed(() => {
    const deficiencies: DeficiencyItem[] = []

    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab
      const items = getCheckItems(tab)
      for (const item of items) {
        if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
          deficiencies.push({
            tab,
            subPanel: null,
            index: item.index,
            controlPoint: item.controlPoint,
            deficiencyType: item.conclusion as '设计无效' | '未实施',
            elementName: cosoTab.label,
          })
        }
      }

      // IT sub-panels (Tab 4 only)
      if (tab === 4) {
        for (const panel of IT_SUB_PANELS) {
          const itItems = getCheckItems(4, panel.key)
          for (const item of itItems) {
            if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
              deficiencies.push({
                tab: 4,
                subPanel: panel.key,
                index: item.index,
                controlPoint: item.controlPoint,
                deficiencyType: item.conclusion as '设计无效' | '未实施',
                elementName: `${cosoTab.label} - ${panel.label}`,
              })
            }
          }
        }
      }
    }

    // 管理层凌驾于控制之上（Tab2 子区 'mo'）缺陷并入清单（归风险评估区，非 ITGC）
    const moItems = getCheckItems(MO_TAB, MO_SUBPANEL)
    for (const item of moItems) {
      if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
        deficiencies.push({
          tab: MO_TAB,
          subPanel: MO_SUBPANEL,
          index: item.index,
          controlPoint: item.controlPoint,
          deficiencyType: item.conclusion as '设计无效' | '未实施',
          elementName: '风险评估过程 - 管理层凌驾于控制之上',
        })
      }
    }

    // 新 IT 结构缺陷：ITGC 分类结论「无效」
    for (const cat of IT_ITGC_CATEGORIES) {
      const c = getResponseValue(`B22A-it-itgc-${cat.key}-conclusion`)?.conclusion
      if (c === '无效') {
        deficiencies.push({
          tab: 4,
          subPanel: 'itgc',
          index: 0,
          controlPoint: `IT一般控制（${cat.label}）`,
          deficiencyType: '设计无效',
          elementName: `控制活动与IT - IT一般控制(ITGC) - ${cat.label}`,
        })
      }
    }
    // 新 IT 结构缺陷：职责分离矩阵「识别出缺陷=是」
    const sodCount = parseInt(getResponseValue('B22A-it-sod-count')?.remark || '0', 10) || 0
    for (let i = 1; i <= sodCount; i++) {
      if (getResponseValue(`B22A-it-sod-${i}-hasDeficiency`)?.remark === '是') {
        const person = getResponseValue(`B22A-it-sod-${i}-person`)?.remark || `职责分离行${i}`
        deficiencies.push({
          tab: 4,
          subPanel: 'sod',
          index: i,
          controlPoint: `职责分离缺陷：${person}`,
          deficiencyType: '设计无效',
          elementName: '控制活动与IT - IT职责分离',
        })
      }
    }

    return deficiencies
  })

  // ─── Element Stats ─────────────────────────────────────────────────────

  const elementStats: ComputedRef<Record<TabNumber, ElementStat>> = computed(() => {
    const stats = {} as Record<TabNumber, ElementStat>

    for (const cosoTab of COSO_TABS) {
      const tab = cosoTab.tab
      const items = getCheckItems(tab)

      let effective = 0
      let deficient = 0
      let notApplicable = 0
      let incomplete = 0

      for (const item of items) {
        if (item.conclusion === null) {
          incomplete++
        } else if (item.conclusion === '不适用') {
          notApplicable++
        } else if (item.conclusion === '设计无效' || item.conclusion === '未实施') {
          deficient++
        } else {
          effective++
        }
      }

      stats[tab] = {
        total: items.length,
        effective,
        deficient,
        notApplicable,
        incomplete,
      }
    }

    return stats
  })

  // ─── Overall Conclusion ────────────────────────────────────────────────

  function initOverallConclusion(): void {
    const item = getResponseValue('B22A-SUM-overall')
    if (item?.conclusion) {
      overallConclusion.value = item.conclusion as ElementScore
    }
  }

  // ─── Tab Status ────────────────────────────────────────────────────────

  function tabStatus(tab: TabNumber): TabStatus {
    const items = getCheckItems(tab)
    return computeTabStatus(items)
  }

  // ─── Completed Element Count ───────────────────────────────────────────

  const completedElementCount: ComputedRef<number> = computed(() => {
    let count = 0
    for (const cosoTab of COSO_TABS) {
      const score = getEffectiveScore(cosoTab.tab)
      if (score !== null) count++
    }
    return count
  })

  // ─── Prior Year: markNoChange ──────────────────────────────────────────

  function markNoChange(tab: TabNumber, index: number, confirmer: string, subPanel?: ITSubPanel): void {
    const today = new Date()
    const dateStr = [
      today.getFullYear(),
      String(today.getMonth() + 1).padStart(2, '0'),
      String(today.getDate()).padStart(2, '0'),
    ].join('-')

    // BC-53 改造：写进行数组（legacy 写 `-nochange` 单条记录，读路径已不再看它）
    const patch: Partial<B22ARow> = {
      nochange: 'Y',
      nochangeConfirmer: confirmer,
      nochangeDate: dateStr,
    }

    // 沿用上年结论：本年该行结论为空时才带入（不覆盖已填）
    const priorConclusionItem = priorYearData.value.get(
      generateItemId(tab, index, 'conclusion', subPanel),
    )
    const current = rowStore.rowAt(tab, index, subPanel)
    if (priorConclusionItem?.conclusion && !current?.conclusion) {
      patch.conclusion = priorConclusionItem.conclusion
    }

    rowStore.patchRowAt(tab, index, patch, subPanel)
  }

  // ─── 控制矩阵登记册（B22B 源模板：全部控制 + 属性汇总）──────────────────

  interface ControlMatrixRow {
    element: string
    controlPoint: string
    description: string
    conclusion: string
    antiFraud: string
    frequency: string
    performer: string
    competence: string
    risk: string
    nature: string
    itApp: string
    toTest: string
    testMethod: string
    reference: string
  }

  function collectRegisterRows(tab: TabNumber, elementLabel: string, subPanel?: ITSubPanel): ControlMatrixRow[] {
    const items = getCheckItems(tab, subPanel)
    return items
      .filter((it) => it.controlPoint || it.conclusion) // 跳过完全空行
      .map((it) => {
        const a = getControlAttrs(tab, it.index, subPanel)
        const antiFraudMap: Record<string, string> = { Y: '是', N: '否' }
        const toTestMap: Record<string, string> = { Y: '是', N: '否' }
        return {
          element: elementLabel,
          controlPoint: it.controlPoint,
          description: it.description,
          conclusion: it.conclusion || '',
          antiFraud: antiFraudMap[a.antiFraud] || '',
          frequency: a.frequency || '',
          performer: a.performer || '',
          competence: a.competence || '',
          risk: a.risk || '',
          nature: a.nature || '',
          itApp: a.itApp || '',
          toTest: toTestMap[a.toTest] || '',
          testMethod: a.testMethod || '',
          reference: it.reference || '',
        }
      })
  }

  const controlMatrixRegister: ComputedRef<ControlMatrixRow[]> = computed(() => {
    const rows: ControlMatrixRow[] = []
    for (const cosoTab of COSO_TABS) {
      rows.push(...collectRegisterRows(cosoTab.tab, cosoTab.label))
      if (cosoTab.tab === 4) {
        for (const panel of IT_SUB_PANELS) {
          rows.push(...collectRegisterRows(4, `${cosoTab.label} - ${panel.label}`, panel.key))
        }
      }
      if (cosoTab.tab === 2) {
        rows.push(...collectRegisterRows(MO_TAB, '风险评估过程 - 管理层凌驾于控制之上', MO_SUBPANEL))
      }
    }
    return rows
  })

  // ─── Business Rule Warnings ────────────────────────────────────────────

  const controlEnvWeakWarning: ComputedRef<boolean> = computed(() => {
    const tab1Score = getEffectiveScore(1)
    if (tab1Score !== '无效' && tab1Score !== '部分有效') return false

    // Check if critical items (management integrity / governance independence) are deficient
    const items = getCheckItems(1)
    const hasCriticalDeficiency = items.some(
      item => item.conclusion === '设计无效' &&
        (item.controlPoint.includes('诚信') || item.controlPoint.includes('独立性') || item.controlPoint.includes('治理'))
    )
    return hasCriticalDeficiency
  })

  const itControlWeakWarning: ComputedRef<boolean> = computed(() => {
    return itDependency.value === '高' && itgcConclusion.value === '无效'
  })

  // ─── 财务报告过程（B22A-4-5）────────────────────────────────────────────

  function getFrp(key: FrpKey): FrpState {
    return {
      na: getResponseValue(`B22A-frp-${key}-na`)?.conclusion === 'Y',
      note: getResponseValue(`B22A-frp-${key}-note`)?.remark || '',
    }
  }

  function setFrpNa(key: FrpKey, na: boolean): void {
    const item: ChecklistItem = { item_id: `B22A-frp-${key}-na`, conclusion: na ? 'Y' : 'N', remark: null, wp_ref: null }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function setFrpNote(key: FrpKey, note: string): void {
    _saveText({ item_id: `B22A-frp-${key}-note`, conclusion: null, remark: note, wp_ref: null })
  }

  /** 财务报告过程完成度缺口（不适用的子过程不计入） */
  const frpApplicableGapCount: ComputedRef<number> = computed(() => {
    let gap = 0
    for (const sp of FRP_SUBPROCESSES) {
      const f = getFrp(sp.key)
      if (!f.na && !f.note.trim()) gap++
    }
    return gap
  })

  // ─── IT 详细结构化：通用键控动态行表 ────────────────────────────────────

  // 🔴 BC-53 同型改造：IT 子区三表（-it-summary / -it-system / -it-sod）原用
  //    `{prefix}-{index}-{field}` 下标键 + shift 搬迁删行，与 COSO tab 同型缺陷。
  //    现统一走行数组 + 稳定 rowId（含 legacy 自动迁移，幂等）。

  /** 已迁移的前缀集合（防重复迁移）。 */
  const _migratedPrefixes = new Set<string>()

  function _readPrefixRows(prefix: string, fields: readonly string[]): B22ARow[] {
    const rowsId = prefixedRowsItemId(prefix)
    const scope = prefixScope(prefix)
    const rec = getResponseValue(rowsId)
    if (rec?.remark) return parseRows(rec.remark, scope)

    if (!_migratedPrefixes.has(prefix)) {
      _migratedPrefixes.add(prefix)
      const reader = {
        getCount: (p: string) => {
          const n = parseInt(
            getResponseValue(prefixedLegacyCountItemId(p))?.remark || '0', 10,
          )
          return Number.isNaN(n) ? 0 : n
        },
        getField: (id: string) => getResponseValue(id),
      }
      if (reader.getCount(prefix) > 0) {
        const migrated = migrateLegacyPrefixedRows(reader, prefix, fields)
        if (migrated.length > 0) {
          _writePrefixRows(prefix, migrated)
          return migrated
        }
      }
    }
    return []
  }

  function _writePrefixRows(prefix: string, rows: readonly B22ARow[]): void {
    const item: ChecklistItem = {
      item_id: prefixedRowsItemId(prefix),
      conclusion: null,
      remark: serializeRows(resequence(rows)),
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  function _rowCount(prefix: string, fields: readonly string[] = []): number {
    return _readPrefixRows(prefix, fields).length
  }

  function _getRows(prefix: string, fields: readonly string[]): ItRow[] {
    return _readPrefixRows(prefix, fields).map((row, i) => {
      const out: ItRow = { index: i + 1 }
      for (const f of fields) {
        out[f] = typeof row[f] === 'string' ? (row[f] as string) : ''
      }
      return out
    })
  }

  function _addRow(prefix: string, fields: readonly string[] = []): void {
    const rows = _readPrefixRows(prefix, fields)
    const row: B22ARow = {
      rowId: makeRowId(prefixScope(prefix)),
      seq: rows.length + 1,
    }
    _writePrefixRows(prefix, [...rows, row])
  }

  /** 删行：摘除行对象，**不搬迁任何字段值**（剩余行身份 ↔ 内容绑定不变）。 */
  function _removeRow(prefix: string, index: number, fields: readonly string[]): void {
    const rows = _readPrefixRows(prefix, fields)
    if (index < 1 || index > rows.length) return
    _writePrefixRows(prefix, rows.filter((_, i) => i !== index - 1))
  }

  function _setRowField(prefix: string, index: number, field: string, value: string, debounce = false): void {
    if (index < 1) return
    const rows = _readPrefixRows(prefix, [field])
    const next = [...rows]
    while (next.length < index) {
      next.push({ rowId: makeRowId(prefixScope(prefix)), seq: next.length + 1 })
    }
    next[index - 1] = { ...next[index - 1], [field]: value }
    const item: ChecklistItem = {
      item_id: prefixedRowsItemId(prefix),
      conclusion: null,
      remark: serializeRows(resequence(next)),
      wp_ref: null,
    }
    allResponses.value.set(item.item_id, item)
    if (debounce) _saveText(item)
    else saveImmediate([item])
  }

  const IT_SUMMARY_PREFIX = 'B22A-it-summary'
  const IT_SYSTEM_PREFIX = 'B22A-it-system'
  const IT_SOD_PREFIX = 'B22A-it-sod'

  // IT 概要（B22A-4-1）
  function getItSummaryRows(): ItRow[] { return _getRows(IT_SUMMARY_PREFIX, IT_SUMMARY_FIELDS) }
  function addItSummaryRow(): void { _addRow(IT_SUMMARY_PREFIX) }
  function removeItSummaryRow(index: number): void { _removeRow(IT_SUMMARY_PREFIX, index, IT_SUMMARY_FIELDS) }
  function setItSummaryField(index: number, field: string, value: string, debounce = false): void {
    _setRowField(IT_SUMMARY_PREFIX, index, field, value, debounce)
  }

  // 系统清单（B22A-4-2）
  function getItSystemRows(): ItRow[] { return _getRows(IT_SYSTEM_PREFIX, IT_SYSTEM_FIELDS) }
  function addItSystemRow(): void { _addRow(IT_SYSTEM_PREFIX) }
  function removeItSystemRow(index: number): void { _removeRow(IT_SYSTEM_PREFIX, index, IT_SYSTEM_FIELDS) }
  function setItSystemField(index: number, field: string, value: string, debounce = false): void {
    _setRowField(IT_SYSTEM_PREFIX, index, field, value, debounce)
  }

  // IT 职责分离 SoD（B22A-4-4-2）
  function getSodRows(): ItRow[] { return _getRows(IT_SOD_PREFIX, IT_SOD_FIELDS) }
  function addSodRow(): void { _addRow(IT_SOD_PREFIX) }
  function removeSodRow(index: number): void { _removeRow(IT_SOD_PREFIX, index, IT_SOD_FIELDS) }
  function setSodField(index: number, field: string, value: string, debounce = false): void {
    _setRowField(IT_SOD_PREFIX, index, field, value, debounce)
  }

  // IT 环境 4 维（B22A-4-3）
  function getItEnvNote(dim: string): string {
    return getResponseValue(`B22A-it-env-${dim}-note`)?.remark || ''
  }
  function setItEnvNote(dim: string, text: string): void {
    _saveText({ item_id: `B22A-it-env-${dim}-note`, conclusion: null, remark: text, wp_ref: null })
  }

  // IT 一般控制 ITGC（B22A-4-4-1）
  function getItgcCategory(cat: string): ItgcCategoryState {
    return {
      note: getResponseValue(`B22A-it-itgc-${cat}-note`)?.remark || '',
      conclusion: getResponseValue(`B22A-it-itgc-${cat}-conclusion`)?.conclusion ?? null,
    }
  }
  function setItgcNote(cat: string, text: string): void {
    _saveText({ item_id: `B22A-it-itgc-${cat}-note`, conclusion: null, remark: text, wp_ref: null })
  }
  function setItgcConclusion(cat: string, val: string): void {
    const item: ChecklistItem = { item_id: `B22A-it-itgc-${cat}-conclusion`, conclusion: val, remark: null, wp_ref: null }
    allResponses.value.set(item.item_id, item)
    saveImmediate([item])
  }

  // ─── 旧 IT 数据迁移（P9，绝不静默丢弃）───────────────────────────────────
  // 读取旧 `B22A-T4-IT-{sub}-*`（env/itgc/app/change/access/sod 通用检查项）→ 落入新结构。
  // 仅在新结构为空且未迁移过时执行一次（幂等，避免覆盖新编辑）。

  function _legacyLines(subPanel: ITSubPanel): string[] {
    return getCheckItems(4, subPanel)
      .filter((it) => it.controlPoint || it.description || it.conclusion)
      .map((it) => {
        const parts: string[] = []
        if (it.controlPoint) parts.push(it.controlPoint)
        if (it.description) parts.push(`（${it.description}）`)
        if (it.conclusion) parts.push(`[结论：${it.conclusion}]`)
        return parts.join(' ')
      })
  }
  function _legacyHasDeficiency(subPanel: ITSubPanel): boolean {
    return getCheckItems(4, subPanel).some((it) => it.conclusion === '设计无效' || it.conclusion === '未实施')
  }

  /** 新 IT 结构是否为空（无任何 B22A-it-* 内容，排除迁移标记） */
  function isItStructureEmpty(): boolean {
    for (const [k, v] of allResponses.value) {
      if (k.startsWith('B22A-it-') && k !== 'B22A-it-migrated') {
        if (v.remark || v.conclusion) return false
      }
    }
    return true
  }

  function migrateLegacyItData(): void {
    // 已迁移过 → 跳过（幂等）
    if (getResponseValue('B22A-it-migrated')?.conclusion === 'Y') return
    // 新结构已有内容（用户已编辑新结构）→ 仅打标记，不覆盖
    if (!isItStructureEmpty()) {
      const marker: ChecklistItem = { item_id: 'B22A-it-migrated', conclusion: 'Y', remark: null, wp_ref: null }
      allResponses.value.set(marker.item_id, marker)
      saveImmediate([marker])
      return
    }

    const batch: ChecklistItem[] = []
    const put = (id: string, remark: string | null, conclusion: string | null = null) => {
      const it: ChecklistItem = { item_id: id, conclusion, remark, wp_ref: null }
      allResponses.value.set(id, it)
      batch.push(it)
    }

    // env（IT环境了解）→ IT环境 应用程序 dim
    const envLines = _legacyLines('env')
    // app（IT应用控制）→ IT环境 应用程序 dim（无法明确映射到新专区，标注待复核）
    const appLines = _legacyLines('app')
    const envAppParts: string[] = []
    if (envLines.length) envAppParts.push('【迁移·IT环境了解】\n' + envLines.join('\n'))
    if (appLines.length) envAppParts.push('【待复核-旧数据·IT应用控制】\n' + appLines.join('\n'))
    if (envAppParts.length) put('B22A-it-env-app-note', envAppParts.join('\n\n'))

    // itgc（IT通用控制）+ access（访问安全）→ ITGC 安全管理
    const itgcLines = _legacyLines('itgc')
    const accessLines = _legacyLines('access')
    const secParts: string[] = []
    if (itgcLines.length) secParts.push('【迁移·IT通用控制】\n' + itgcLines.join('\n'))
    if (accessLines.length) secParts.push('【迁移·访问安全】\n' + accessLines.join('\n'))
    if (secParts.length) {
      put('B22A-it-itgc-security-note', secParts.join('\n\n'))
      const deficient = _legacyHasDeficiency('itgc') || _legacyHasDeficiency('access')
      put('B22A-it-itgc-security-conclusion', null, deficient ? '无效' : '有效')
    }

    // change（变更管理）→ ITGC 技术维护
    const changeLines = _legacyLines('change')
    if (changeLines.length) {
      put('B22A-it-itgc-techMaintenance-note', '【迁移·变更管理】\n' + changeLines.join('\n'))
      put('B22A-it-itgc-techMaintenance-conclusion', null, _legacyHasDeficiency('change') ? '无效' : '有效')
    }

    // sod（职责分离）→ SoD 矩阵行（保留结构 + 缺陷信号，标注待复核）
    const sodItems = getCheckItems(4, 'sod').filter((it) => it.controlPoint || it.description || it.conclusion)
    if (sodItems.length) {
      put('B22A-it-sod-count', String(sodItems.length))
      sodItems.forEach((it, idx) => {
        const n = idx + 1
        put(`${IT_SOD_PREFIX}-${n}-person`, '【待复核-旧数据】' + (it.controlPoint || '(未命名)'))
        if (it.description) put(`${IT_SOD_PREFIX}-${n}-businessProcess`, it.description)
        if (it.conclusion === '设计无效' || it.conclusion === '未实施') {
          put(`${IT_SOD_PREFIX}-${n}-hasDeficiency`, '是')
          put(`${IT_SOD_PREFIX}-${n}-hasSodIssue`, '是')
        }
      })
    }

    // 清空旧通用面板 count（隐藏旧面板，原始字段数据保留于 allResponses 不删除）
    for (const p of ['env', 'itgc', 'app', 'change', 'access', 'sod'] as ITSubPanel[]) {
      if (getResponseValue(`B22A-T4-IT-${p}-count`)) put(`B22A-T4-IT-${p}-count`, '0')
    }

    // 迁移标记
    put('B22A-it-migrated', null, 'Y')

    if (batch.length) saveImmediate(batch)
  }

  // ─── Initialization ────────────────────────────────────────────────────

  function initialize(): void {
    initITDependency()
    initOverallConclusion()
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // Check items CRUD
    getCheckItems,
    addCheckItem,
    addPresetCheckItems,
    removeCheckItem,
    setConclusion,
    setUnderstandingMethod,
    setControlAttrs,
    getControlAttrs,
    // 管理层凌驾于控制之上
    getMoItems,
    addMoItem,
    addMoPresets,
    removeMoItem,
    setMoConclusion,
    setMoMethods,
    getMoKeyJudgment,
    setMoKeyJudgment,
    // Element Score
    computeElementScore,
    overrideElementScore,
    isScoreOverridden,
    getEffectiveScore,
    // IT dependency
    itDependency,
    setITDependency,
    itgcConclusion,
    isITGCInvalid,
    // Deficiency
    deficiencyList,
    // Stats
    elementStats,
    overallConclusion,
    completedElementCount,
    // Tab status
    tabStatus,
    // Prior year
    priorYearData,
    markNoChange,
    // Business warnings
    controlEnvWeakWarning,
    itControlWeakWarning,
    // 控制矩阵登记册
    controlMatrixRegister,
    // 财务报告过程（B22A-4-5）
    getFrp,
    setFrpNa,
    setFrpNote,
    frpApplicableGapCount,
    // IT 详细结构化（B22A-4-1 ~ 4-4-2）
    getItSummaryRows,
    addItSummaryRow,
    removeItSummaryRow,
    setItSummaryField,
    getItSystemRows,
    addItSystemRow,
    removeItSystemRow,
    setItSystemField,
    getItEnvNote,
    setItEnvNote,
    getItgcCategory,
    setItgcNote,
    setItgcConclusion,
    getSodRows,
    addSodRow,
    removeSodRow,
    setSodField,
    migrateLegacyItData,
    // Init
    initialize,
  }
}

export default useB22AControlMatrix
