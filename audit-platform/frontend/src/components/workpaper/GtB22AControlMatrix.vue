<script setup lang="ts">
/**
 * GtB22AControlMatrix — B22A 内部控制了解程序表
 *
 * 6-Tab 统一界面：
 *   Tab 1: 控制环境
 *   Tab 2: 风险评估过程
 *   Tab 3: 信息系统与沟通
 *   Tab 4: 控制活动 + IT 子区
 *   Tab 5: 监督
 *   Tab 6: 控制矩阵汇总
 *
 * Spec: .kiro/specs/b22a-control-matrix/
 * Tasks: 3.1 ~ 3.13, 4.1
 */
import { ref, computed, watch, toRef, onMounted, provide } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useB22AFormData, type ChecklistItem } from './composables/useB22AFormData'
import {
  useB22AControlMatrix,
  CONCLUSIONS,
  UNDERSTANDING_METHODS,
  SCORE_COLOR_MAP,
  COSO_TABS,
  FRP_SUBPROCESSES,
  IT_ENV_DIMENSIONS,
  IT_ITGC_CATEGORIES,
  IT_COMPLEXITY_OPTIONS,
  IT_COMPLEX_FACTOR_OPTIONS,
  IT_SUMMARY_KIND_OPTIONS,
  IT_SYSTEM_DEPENDENCY_OPTIONS,
  IT_YESNO_OPTIONS,
  ITGC_CONCLUSION_OPTIONS,
  type TabNumber,
  type ElementScore,
  type ITSubPanel,
  type ITDependency,
  type Conclusion,
  type UnderstandingMethod,
  type FrpKey,
} from './composables/useB22AControlMatrix'
import GtIndexChip from './GtIndexChip.vue'
import { useB22AReview } from './composables/useB22AReview'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import GtWpVersionTrail from './version-trail/GtWpVersionTrail.vue'
import B22AControlItemDialog from './B22AControlItemDialog.vue'
import GtOnlyOfficeSheet from './GtOnlyOfficeSheet.vue'
import GtReviewTrigger from './GtReviewTrigger.vue'
import { useWorkpaperEntryDualMode } from './composables/useWorkpaperEntryDualMode'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import {
  ELEMENT_REFERENCES,
  MANAGEMENT_OVERRIDE_REFERENCE,
  CONTROL_FREQUENCY_OPTIONS,
  CONTROL_PERFORMER_OPTIONS,
  CONTROL_RISK_OPTIONS,
  CONTROL_NATURE_OPTIONS,
  CONTROL_TEST_METHOD_OPTIONS,
} from './composables/b22aReference'

// ─── Props / Emits (Task 3.1) ────────────────────────────────────────────────

interface Props {
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}

const props = defineProps<Props>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables 初始化 (Task 3.1) ──────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly')

const {
  allResponses,
  loading,
  saving,
  loadAll,
  loadPriorYear,
  saveImmediate,
  saveDebouncedText,
} = useB22AFormData(wpIdRef)

const {
  getCheckItems,
  addCheckItem,
  addPresetCheckItems,
  removeCheckItem,
  setConclusion,
  setUnderstandingMethod,
  setControlAttrs,
  getControlAttrs,
  overrideElementScore,
  isScoreOverridden,
  getEffectiveScore,
  itDependency,
  setITDependency,
  itgcConclusion,
  isITGCInvalid,
  deficiencyList,
  elementStats,
  overallConclusion,
  completedElementCount,
  tabStatus,
  priorYearData,
  markNoChange,
  controlEnvWeakWarning,
  itControlWeakWarning,
  controlMatrixRegister,
  initialize,
  // 管理层凌驾于控制之上
  getMoItems,
  addMoItem,
  addMoPresets,
  removeMoItem,
  setMoConclusion,
  setMoMethods,
  getMoKeyJudgment,
  setMoKeyJudgment,
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
} = useB22AControlMatrix(allResponses, saveImmediate, saveDebouncedText)

// ─── 方法论参考数据 + 一键套用示例 ───────────────────────────────────────────

function elementRef(tab: TabNumber) {
  return ELEMENT_REFERENCES[tab]
}

const moRef = MANAGEMENT_OVERRIDE_REFERENCE

function handleApplyExamples(tab: TabNumber) {
  if (isReadonly.value) return
  const ref = ELEMENT_REFERENCES[tab]
  if (!ref) return
  addPresetCheckItems(tab, ref.controlPointExamples)
  ElMessage.success(`已套用 ${ref.controlPointExamples.length} 条示例控制点，请逐项核实并评价`)
}

// ─── 引导式录入向导（弹窗）───────────────────────────────────────────────────

const itemDialogVisible = ref(false)
const itemDialogTab = ref<TabNumber>(1)
const itemDialogIndex = ref<number>(0) // 0 = 新增
const itemDialogTitle = ref('')
const EMPTY_ITEM = { controlPoint: '', description: '', methods: [] as any[], conclusion: null as any, reference: '' }
const itemDialogItem = ref<any>({ ...EMPTY_ITEM })
const itemDialogAttrs = ref<Record<string, any>>({})

function openNewItemDialog(tab: TabNumber) {
  if (isReadonly.value) return
  itemDialogTab.value = tab
  itemDialogIndex.value = 0
  itemDialogItem.value = { ...EMPTY_ITEM }
  itemDialogAttrs.value = {}
  itemDialogTitle.value = `${elementRef(tab).elementName} · 新增控制（引导录入）`
  itemDialogVisible.value = true
}

function openEditItemDialog(tab: TabNumber, index: number) {
  if (isReadonly.value) return
  const items = getCheckItems(tab)
  const it = items.find((x) => x.index === index)
  if (!it) return
  itemDialogTab.value = tab
  itemDialogIndex.value = index
  itemDialogItem.value = {
    controlPoint: it.controlPoint,
    description: it.description,
    methods: [...it.methods],
    conclusion: it.conclusion,
    reference: it.reference,
  }
  itemDialogAttrs.value = getControlAttrs(tab, index)
  itemDialogTitle.value = `${elementRef(tab).elementName} · 编辑控制 #${index}`
  itemDialogVisible.value = true
}

function _applyItem(tab: TabNumber, index: number, form: any, attrs: Record<string, any>) {
  // 弹窗确认为批量保存：全部走 saveImmediate 一次性提交，
  // 避免 debounce 文本保存被后续 immediate 保存 clearTimeout 取消（丢失 point/desc/ref）。
  const base = `B22A-T${tab}-item-${index}`
  const batch: ChecklistItem[] = [
    { item_id: `${base}-point`, conclusion: null, remark: form.controlPoint || null, wp_ref: null },
    { item_id: `${base}-desc`, conclusion: null, remark: form.description || null, wp_ref: null },
    { item_id: `${base}-ref`, conclusion: null, remark: form.reference || null, wp_ref: null },
    { item_id: `${base}-method`, conclusion: null, remark: (form.methods || []).join(','), wp_ref: null },
    { item_id: `${base}-conclusion`, conclusion: form.conclusion || null, remark: null, wp_ref: null },
    { item_id: `${base}-attrs`, conclusion: null, remark: JSON.stringify(attrs || {}), wp_ref: null },
  ]
  for (const it of batch) allResponses.value.set(it.item_id, it)
  saveImmediate(batch)
}

function onItemDialogSave(payload: { form: any; attrs: Record<string, any> }) {
  const tab = itemDialogTab.value
  let index = itemDialogIndex.value
  if (index === 0) {
    // 新增：先建行再写入
    addCheckItem(tab)
    index = getCheckItems(tab).length
  }
  _applyItem(tab, index, payload.form, payload.attrs)
  emitConclusionChange()
  emitDeficiencyChange()
  emitControlToTest()
  ElMessage.success('已保存')
}

// ─── 控制矩阵属性（B22B 登记册字段）展开行编辑 ──────────────────────────────

const CONTROL_FREQUENCY = CONTROL_FREQUENCY_OPTIONS
const CONTROL_PERFORMER = CONTROL_PERFORMER_OPTIONS
const CONTROL_RISK = CONTROL_RISK_OPTIONS
const CONTROL_NATURE = CONTROL_NATURE_OPTIONS
const CONTROL_TEST_METHOD = CONTROL_TEST_METHOD_OPTIONS

function attrsOf(tab: TabNumber, index: number, subPanel?: ITSubPanel): Record<string, any> {
  return getControlAttrs(tab, index, subPanel)
}

function handleAttrChange(tab: TabNumber, index: number, field: string, value: unknown, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  const attrs = { ...getControlAttrs(tab, index, subPanel), [field]: value }
  setControlAttrs(tab, index, attrs, subPanel)
  // 拟测试的控制 → 通知 C 类控制测试
  if (field === 'toTest') emitControlToTest()
}

function emitControlToTest() {
  try {
    const controls: any[] = []
    for (const cosoTab of COSO_TABS) {
      const items = getCheckItems(cosoTab.tab)
      for (const it of items) {
        const a = getControlAttrs(cosoTab.tab, it.index)
        if (a.toTest === 'Y') {
          controls.push({
            element: cosoTab.label,
            controlPoint: it.controlPoint,
            testMethod: a.testMethod || null,
            isAntiFraud: a.antiFraud === 'Y',
          })
        }
      }
    }
    ;(eventBus as any).emit('control:to-test-changed', { controls, total: controls.length })
    // 持久化拟测试控制清单，供 C1 企业层面控制测试跨会话拉取
    const summaryItem: ChecklistItem = {
      item_id: 'B22A-to-test-summary',
      conclusion: null,
      remark: JSON.stringify(controls),
      wp_ref: null,
    }
    allResponses.value.set(summaryItem.item_id, summaryItem)
    saveImmediate([summaryItem])
  } catch (e) {
    console.warn('[B22A] control:to-test-changed emit failed:', e)
  }
}

// ─── 控制矩阵登记册 导出（客户端 xlsx，对齐 B22B 源模板列）──────────────────

const REGISTER_COLUMNS: { key: string; label: string }[] = [
  { key: 'element', label: '要素/子类别' },
  { key: 'controlPoint', label: '控制名称/要点' },
  { key: 'description', label: '详细控制描述' },
  { key: 'antiFraud', label: '是否反舞弊控制' },
  { key: 'frequency', label: '控制频率' },
  { key: 'performer', label: '执行人' },
  { key: 'competence', label: '执行人知识经验技能' },
  { key: 'risk', label: '与控制相关的风险' },
  { key: 'nature', label: '自动/人工' },
  { key: 'itApp', label: 'IT应用名称' },
  { key: 'conclusion', label: '结论' },
  { key: 'toTest', label: '是否拟测试' },
  { key: 'testMethod', label: '控制测试方法' },
  { key: 'reference', label: '参考引用' },
]

async function exportControlMatrix() {
  const rows = controlMatrixRegister.value
  if (!rows.length) {
    ElMessage.warning('暂无控制可导出，请先填写检查项')
    return
  }
  try {
    const XLSX = await import('xlsx')
    const aoa = [
      REGISTER_COLUMNS.map((c) => c.label),
      ...rows.map((r: any) => REGISTER_COLUMNS.map((c) => r[c.key] ?? '')),
    ]
    const ws = XLSX.utils.aoa_to_sheet(aoa)
    ws['!cols'] = REGISTER_COLUMNS.map((c) => ({ wch: c.key === 'description' ? 40 : c.key === 'controlPoint' ? 24 : 14 }))
    const wb = XLSX.utils.book_new()
    XLSX.utils.book_append_sheet(wb, ws, '企业层面控制矩阵')
    XLSX.writeFile(wb, `B22B_企业层面控制矩阵_${props.year || ''}.xlsx`)
    ElMessage.success(`已导出 ${rows.length} 项控制`)
  } catch (e) {
    console.error('[B22A] 控制矩阵导出失败', e)
    ElMessage.error('导出失败')
  }
}

// ─── 管理层凌驾 → B50 / C23/C24 联动 ─────────────────────────────────────────

function handlePushMoToB50() {
  const moItems = getMoItems()
  const deficiencies = moItems.filter(it => it.conclusion === '设计无效' || it.conclusion === '未实施')
  const factors = deficiencies.map(it => it.controlPoint || '管理层凌驾于控制之上缺陷')
  if (factors.length === 0) {
    factors.push('管理层凌驾于控制之上（CAS 1141 特别风险，即使未识别设计缺陷仍须关注）')
  }
  try {
    ;(eventBus as any).emit('b50:push-risk-factor', { factors, source: 'b22a_management_override' })
    ElMessage.success(`已推送 ${factors.length} 项管理层凌驾发现至 B50 风险因素`)
  } catch {
    ElMessage.warning('推送失败')
  }
}

async function handleMoC23Hint() {
  const moItems = getMoItems()
  const hasDeficiency = moItems.some(it => it.conclusion === '设计无效' || it.conclusion === '未实施')
  const msg = hasDeficiency
    ? '已识别管理层凌驾于控制之上的设计缺陷，建议：\n1. 确认 C23 会计分录控制测试已覆盖管理层相关分录\n2. C24 会计分录测试须包含不可预见的测试项目\n3. 关注期末异常调整/关联方交易/收入确认'
    : '未识别管理层凌驾设计缺陷，但 CAS 1141 要求仍须执行：\n1. C24 不可预见会计分录测试\n2. 会计估计回顾性分析\n3. 重大异常交易检查'
  await ElMessageBox.alert(msg, '管理层凌驾 → C23/C24 联动提示', { confirmButtonText: '已知悉', type: 'info' })
}

// ─── AI 辅助生成 ─────────────────────────────────────────────────────────────

const aiLoading = ref<string | null>(null)

async function generateAi(section: string, existingContent: string, apply: (text: string) => void) {
  if (isReadonly.value) return
  aiLoading.value = section
  try {
    const res: any = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: '请根据企业层面内部控制了解的审计方法论，生成规范、简洁的审计说明文本。',
      section,
      existingContent: existingContent || '',
      context: {
        底稿: 'B22A 企业层面控制了解程序表',
        要素: section,
      },
    })
    const text = res?.data?.content ?? res?.content ?? res?.data ?? ''
    if (typeof text === 'string' && text.trim()) {
      apply(text.trim())
      ElMessage.success('AI 已生成，请复核')
    } else {
      ElMessage.warning('AI 未返回内容')
    }
  } catch {
    ElMessage.warning('AI 生成失败，请手动填写')
  } finally {
    aiLoading.value = null
  }
}

// ─── 管理层凌驾于控制之上（Tab2 专区） ───────────────────────────────────────

const moKeyAnswer = ref<string | null>(null)
const moKeyNote = ref('')

function loadMoKeyJudgment() {
  const j = getMoKeyJudgment()
  moKeyAnswer.value = j.answer
  moKeyNote.value = j.note
}

function handleMoKeyAnswerChange(val: string) {
  if (isReadonly.value) return
  moKeyAnswer.value = val
  setMoKeyJudgment(val, moKeyNote.value)
  emitConclusionChange()
}
function handleMoKeyNoteChange(val: string) {
  if (isReadonly.value) return
  moKeyNote.value = val
  setMoKeyJudgment(moKeyAnswer.value || '否', val)
}
function handleAddMoItem() {
  if (isReadonly.value) return
  addMoItem()
}
function handleApplyMoExamples() {
  if (isReadonly.value) return
  addMoPresets(moRef.controlPointExamples)
  ElMessage.success(`已套用 ${moRef.controlPointExamples.length} 条管理层凌驾控制示例`)
}
async function handleRemoveMoItem(index: number) {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm(`确认删除第 ${index} 行？`, '删除确认', { type: 'warning' })
  } catch { return }
  removeMoItem(index)
}
function handleMoConclusionChange(index: number, val: string) {
  if (isReadonly.value) return
  setMoConclusion(index, val as Conclusion)
  emitDeficiencyChange()
}
function handleMoMethodChange(index: number, vals: string[]) {
  if (isReadonly.value) return
  setMoMethods(index, vals as UnderstandingMethod[])
}
function handleMoTextChange(index: number, field: 'point' | 'desc' | 'ref', value: string) {
  if (isReadonly.value) return
  const itemId = `B22A-T2-IT-mo-${index}-${field}`
  const item: ChecklistItem = { item_id: itemId, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

const {
  isReviewed,
  isReadonly,
  canReview,
  pendingItems,
  reviewInfo,
  doReview,
  startAmendment,
} = useB22AReview(
  wpIdRef,
  allResponses,
  completedElementCount,
  overallConclusion,
  externalReadonly as any,
  saveImmediate
)

// ─── 版本链（Task P1-9） ─────────────────────────────────────────────────────

const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = useWorkpaperVersionToolbar(wpIdRef)

// ─── 双模式（HTML ↔ OnlyOffice，参照 D4 7月10日范式：健康检查拉取成功才允许切 OO）───
const dualMode = useWorkpaperEntryDualMode({
  reloadAllResponses: async () => { await loadAll(); initialize() },
  resolveOoSheetName: () => props.wpCode || 'B22A',
})
const renderMode = computed({
  get: () => dualMode.mode.value,
  set: (v: string) => { void dualMode.switchMode(v as 'html' | 'onlyoffice') },
})
const renderModeOptions = computed(() => [
  { label: '结构化视图', value: 'html' as const },
  { label: '在线编辑(OnlyOffice)', value: 'onlyoffice' as const, disabled: !dualMode.ooAvailable.value },
])
function onOoFallback(): void { void dualMode.switchMode('html') }

// ─── 复核对话蓝/红点（供后代 GtReviewTrigger inject；openReviewDialog 由 GtWpRenderer 运行时边界提供）───
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef as any)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── Tab 状态 (Task 3.2) ─────────────────────────────────────────────────────

const activeTab = ref('Tab_1')

function tabStatusIcon(tab: TabNumber): string {
  const status = tabStatus(tab)
  switch (status) {
    case 'complete': return '✅'
    case 'partial': return '🔶'
    case 'empty': return '⬜'
  }
}

const overallProgress = computed(() => `${completedElementCount.value}/5`)

// ─── Check Item 表格操作 (Task 3.3) ─────────────────────────────────────────

function handleAddCheckItem(tab: TabNumber, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  addCheckItem(tab, subPanel)
}

async function handleRemoveCheckItem(tab: TabNumber, index: number, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm(`确认删除第 ${index} 行检查项？`, '删除确认', { type: 'warning' })
  } catch { return }
  removeCheckItem(tab, index, subPanel)
}

function handleConclusionChange(tab: TabNumber, index: number, value: string, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  setConclusion(tab, index, value as Conclusion, subPanel)
  emitConclusionChange()
}

function handleMethodChange(tab: TabNumber, index: number, values: string[], subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  setUnderstandingMethod(tab, index, values as UnderstandingMethod[], subPanel)
}

function handleTextFieldChange(tab: TabNumber, index: number, field: 'point' | 'desc' | 'ref', value: string, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  const prefix = subPanel ? `B22A-T${tab}-IT-${subPanel}` : `B22A-T${tab}-item`
  const itemId = `${prefix}-${index}-${field}`
  const item: ChecklistItem = { item_id: itemId, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

// ─── Tab 4 IT 详细结构化 (Task 5) ────────────────────────────────────────────

const IT_REQUIRED_MAP: Record<ITDependency, { required: boolean; hint: string }> = {
  '高': { required: true, hint: '' },
  '中': { required: false, hint: '可选择性执行' },
  '低': { required: false, hint: '可简化执行' },
}

function handleITDependencyChange(level: string) {
  if (isReadonly.value) return
  setITDependency(level as ITDependency)
  emitITChange()
}

// IT 概要 / 系统清单 / 职责分离 行操作
function handleAddItSummary() { if (!isReadonly.value) addItSummaryRow() }
async function handleRemoveItSummary(index: number) {
  if (isReadonly.value) return
  try { await ElMessageBox.confirm(`确认删除第 ${index} 行？`, '删除确认', { type: 'warning' }) } catch { return }
  removeItSummaryRow(index)
}
function handleItSummaryField(index: number, field: string, value: string, debounce = false) {
  if (!isReadonly.value) setItSummaryField(index, field, value, debounce)
}

function handleAddItSystem() { if (!isReadonly.value) addItSystemRow() }
async function handleRemoveItSystem(index: number) {
  if (isReadonly.value) return
  try { await ElMessageBox.confirm(`确认删除第 ${index} 行？`, '删除确认', { type: 'warning' }) } catch { return }
  removeItSystemRow(index)
}
function handleItSystemField(index: number, field: string, value: string, debounce = false) {
  if (!isReadonly.value) setItSystemField(index, field, value, debounce)
}

function handleAddSod() { if (!isReadonly.value) addSodRow() }
async function handleRemoveSod(index: number) {
  if (isReadonly.value) return
  try { await ElMessageBox.confirm(`确认删除第 ${index} 行？`, '删除确认', { type: 'warning' }) } catch { return }
  removeSodRow(index)
}
function handleSodField(index: number, field: string, value: string, debounce = false) {
  if (!isReadonly.value) setSodField(index, field, value, debounce)
}

// IT 环境 4 维
function handleItEnvNote(dim: string, value: string) {
  if (!isReadonly.value) setItEnvNote(dim, value)
}

// ITGC 分类
function handleItgcNote(cat: string, value: string) {
  if (!isReadonly.value) setItgcNote(cat, value)
}
function handleItgcConclusion(cat: string, value: string) {
  if (isReadonly.value) return
  setItgcConclusion(cat, value)
  emitITChange()
  emitDeficiencyChange()
}

// ─── 财务报告过程（B22A-4-5，信息与沟通下）───────────────────────────────────

function frpOf(key: FrpKey) { return getFrp(key) }
function handleFrpNaChange(key: FrpKey, na: boolean) {
  if (!isReadonly.value) setFrpNa(key, na)
}
function handleFrpNoteChange(key: FrpKey, value: string) {
  if (!isReadonly.value) setFrpNote(key, value)
}

// ─── Summary Tab (Task 3.5) ──────────────────────────────────────────────────

const ELEMENT_SCORE_OPTIONS: ElementScore[] = ['有效', '部分有效', '无效']

function getScoreStyle(score: ElementScore | null) {
  if (!score) return { backgroundColor: '#F9FAFB', color: '#374151' }
  const c = SCORE_COLOR_MAP[score]
  return { backgroundColor: c.bg, color: c.text }
}

function handleOverallConclusionChange(value: string) {
  if (isReadonly.value) return
  overallConclusion.value = value as ElementScore
  const item: ChecklistItem = {
    item_id: 'B22A-SUM-overall',
    conclusion: value,
    remark: null,
    wp_ref: null,
  }
  allResponses.value.set(item.item_id, item)
  saveImmediate([item])
  emitConclusionChange()
}

function handleSummaryNoteChange(value: string) {
  if (isReadonly.value) return
  const item: ChecklistItem = { item_id: 'B22A-SUM-note', conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(item.item_id, item)
  saveDebouncedText(item)
}

const summaryNote = computed(() => allResponses.value.get('B22A-SUM-note')?.remark || '')

// ─── Element_Score 手动覆盖 (Task 3.7) ──────────────────────────────────────

const overrideDialogVisible = ref(false)
const overrideTab = ref<TabNumber>(1)
const overrideScore = ref<ElementScore>('有效')
const overrideReason = ref('')

function showOverrideDialog(tab: TabNumber) {
  if (isReadonly.value) return
  overrideTab.value = tab
  overrideScore.value = getEffectiveScore(tab) || '有效'
  overrideReason.value = ''
  overrideDialogVisible.value = true
}

function submitOverride() {
  if (!overrideReason.value.trim()) {
    ElMessage.warning('需填写调整理由')
    return
  }
  overrideElementScore(overrideTab.value, overrideScore.value, overrideReason.value)
  overrideDialogVisible.value = false
  emitConclusionChange()
}

// ─── Manager Review (Task 3.8) ───────────────────────────────────────────────

async function handleReview() {
  if (!canReview.value || isReadonly.value) return
  try {
    await ElMessageBox.confirm('确认签字复核？复核后全部内容将锁定为只读。', '现场经理复核', { type: 'info' })
  } catch { return }
  await doReview()
  emit('save')
  emit('completed')
}

// ─── Amendment (Task 3.9) ────────────────────────────────────────────────────

const amendmentDialogVisible = ref(false)
const amendmentReason = ref('')

function showAmendmentDialog() {
  amendmentReason.value = ''
  amendmentDialogVisible.value = true
}

async function submitAmendment() {
  if (!amendmentReason.value.trim()) {
    ElMessage.warning('请填写修改原因')
    return
  }
  try {
    await startAmendment(amendmentReason.value)
    amendmentDialogVisible.value = false
    ElMessage.success('已重置复核，可继续编辑')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  }
}

// ─── EventBus (Task 3.10) ────────────────────────────────────────────────────

function emitConclusionChange() {
  try {
    const elementScores: Record<number, ElementScore | null> = {}
    for (const t of COSO_TABS) {
      elementScores[t.tab] = getEffectiveScore(t.tab)
    }
    ;(eventBus as any).emit('control:conclusion-changed', {
      elementScores,
      itDependency: itDependency.value,
      itgcConclusion: itgcConclusion.value,
      overallConclusion: overallConclusion.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:conclusion-changed emit failed:', e)
  }
}

function emitITChange() {
  try {
    ;(eventBus as any).emit('control:it-conclusion-changed', {
      itDependency: itDependency.value,
      itgcConclusion: itgcConclusion.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:it-conclusion-changed emit failed:', e)
  }
}

function emitDeficiencyChange() {
  try {
    ;(eventBus as any).emit('control:deficiency-changed', {
      total: deficiencyList.value.length,
      deficiencies: deficiencyList.value,
    })
  } catch (e) {
    console.warn('[B22A] EventBus control:deficiency-changed emit failed:', e)
  }
}

// ─── Prior Year (Task 3.11) ──────────────────────────────────────────────────
// 注：跨年度续审继承（从真实上年底稿加载）属 v3.0 规划，当前平台尚未提供上年底稿解析，
// 原 `${wpId}-prior` 为占位实现（该 wp 不存在），已移除误导性"加载上年数据"按钮。
// loadPriorYear / priorYearData / markNoChange 保留，待续审能力就绪后按项目上年 wp_id 接入。

function handleMarkNoChange(tab: TabNumber, index: number, subPanel?: ITSubPanel) {
  if (isReadonly.value) return
  markNoChange(tab, index, '当前用户', subPanel)
}

// ─── Element note (per tab) ──────────────────────────────────────────────────

function getTabNote(tab: TabNumber): string {
  return allResponses.value.get(`B22A-T${tab}-note`)?.remark || ''
}

function handleTabNoteChange(tab: TabNumber, value: string) {
  if (isReadonly.value) return
  const item: ChecklistItem = { item_id: `B22A-T${tab}-note`, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(item.item_id, item)
  saveDebouncedText(item)
}

// ─── Lifecycle (Task 3.1) ────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  initialize()
  loadMoKeyJudgment()
  // 旧 IT 通用检查项 → 新结构化子区迁移（幂等，仅在新结构为空且未迁移时执行）
  if (!isReadonly.value) migrateLegacyItData()
})

// 控制环境薄弱 → 通知 B50 提高整体风险评估（真实事件，非仅 UI chip）
watch(controlEnvWeakWarning, (weak) => {
  try {
    ;(eventBus as any).emit('control:environment-weak', {
      weak,
      tab1Score: getEffectiveScore(1),
      source: 'B22A',
    })
  } catch (e) {
    console.warn('[B22A] control:environment-weak emit failed:', e)
  }
})

// Watch isReviewed → emit completed
watch(isReviewed, (val) => {
  if (val) emit('completed')
})

// Watch saving → emit save + version snapshot
watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) {
    emit('save')
    scheduleAutoSnapshot?.()
  }
})

// Watch deficiency list → emit change
watch(deficiencyList, () => {
  emitDeficiencyChange()
}, { deep: true })
</script>

<template>
  <div class="gt-b22a-control-matrix" :class="{ 'is-readonly': isReadonly }">
    <!-- 控制环境薄弱警告横幅 (Task 3.12) -->
    <div v-if="controlEnvWeakWarning" class="warning-banner warning-banner--red">
      ⚠️ 控制环境薄弱——建议提高整体风险评估
      <span class="ref-chip">📎 跳转 B50</span>
    </div>

    <!-- IT 控制薄弱警告 (Task 3.12) -->
    <div v-if="itControlWeakWarning" class="warning-banner warning-banner--orange">
      ⚠️ IT通用控制(ITGC)无效——IT依赖程度高，IT应用控制可靠性受影响
    </div>

    <!-- 已复核横幅 (Task 3.8) -->
    <div v-if="isReviewed" class="review-banner">
      <span>✅ 已复核</span>
      <span v-if="reviewInfo">（{{ reviewInfo.reviewer }} / {{ reviewInfo.date }}）</span>
      <el-button v-if="!externalReadonly" size="small" type="warning" @click="showAmendmentDialog">
        修改（Amendment）
      </el-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-mask">加载中...</div>

    <!-- 版本历史 -->
    <GtWpVersionTrail ref="versionTrailRef" :wp-id="wpId" />

    <!-- 双模式工具栏（参照 D4：健康检查拉取成功才允许切 OnlyOffice） -->
    <div class="b22-mode-toolbar">
      <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
      <el-tag v-if="dualMode.checking.value" size="small" type="info">OnlyOffice 检测中…</el-tag>
      <el-tag v-else-if="dualMode.ooAvailable.value" size="small" type="success">OnlyOffice 就绪（拉取成功）</el-tag>
      <el-tag v-else size="small" type="warning">OnlyOffice 不可用（健康检查未通过）</el-tag>
    </div>

    <!-- OnlyOffice 整册视图 -->
    <GtOnlyOfficeSheet
      v-if="renderMode === 'onlyoffice'"
      :key="wpCode"
      :wp-id="props.wpId"
      :sheet-name="props.wpCode || 'B22A'"
      :project-id="props.projectId"
      :whole-workbook="true"
      :readonly="isReadonly"
      @fallback="onOoFallback"
    />

    <!-- 6-Tab 容器 (Task 3.2) -->
    <el-tabs v-else v-model="activeTab" type="border-card" class="b22a-tabs">
      <!-- 进度指示 -->
      <div class="tab-progress">完成进度: {{ overallProgress }}</div>

      <!-- ═══ Tab 1~5: COSO 五要素 ═══ -->
      <el-tab-pane
        v-for="cosoTab in COSO_TABS"
        :key="cosoTab.tab"
        :label="`${tabStatusIcon(cosoTab.tab)} ${cosoTab.label}`"
        :name="`Tab_${cosoTab.tab}`"
      >
        <div class="tab-content">
          <div class="tab-header">
            <h3>{{ cosoTab.label }}</h3>
            <div class="tab-header-progress">
              <el-tag size="small" :type="tabStatus(cosoTab.tab) === 'complete' ? 'success' : tabStatus(cosoTab.tab) === 'partial' ? 'warning' : 'info'">
                {{ (elementStats[cosoTab.tab]?.effective ?? 0) + (elementStats[cosoTab.tab]?.deficient ?? 0) + (elementStats[cosoTab.tab]?.notApplicable ?? 0) }}/{{ elementStats[cosoTab.tab]?.total ?? 0 }} 已评价
              </el-tag>
            </div>
            <div class="tab-header-actions">
              <el-button v-if="!isReadonly" size="small" @click="handleApplyExamples(cosoTab.tab)">
                套用示例控制点
              </el-button>
              <el-button v-if="!isReadonly" size="small" @click="handleAddCheckItem(cosoTab.tab)">
                + 快速加行
              </el-button>
              <el-button v-if="!isReadonly" type="primary" size="small" @click="openNewItemDialog(cosoTab.tab)">
                ✏️ 引导录入
              </el-button>
            </div>
          </div>

          <!-- 审计目标 -->
          <el-alert :closable="false" type="info" show-icon class="b22a-objective">
            <template #title>
              <strong>审计目标：</strong>{{ elementRef(cosoTab.tab).auditObjective }}
            </template>
          </el-alert>

          <!-- 方法论上下文：COSO 原则 + 关注点 + PRC 对照（琥珀块，可折叠） -->
          <details class="b22a-methodology">
            <summary>方法论参考：COSO 原则与《企业内部控制基本规范》对照（编制引导）</summary>
            <div class="methodology-body">
              <div class="coso-principles">
                <div v-for="p in elementRef(cosoTab.tab).principles" :key="p.no" class="coso-principle">
                  <div class="coso-principle-title">原则 {{ p.no }}：{{ p.title }}</div>
                  <div class="coso-pof">
                    <span v-for="(pf, i) in p.pointsOfFocus" :key="i" class="pof-chip">{{ pf }}</span>
                  </div>
                </div>
              </div>
              <div class="prc-mapping">
                <div class="prc-title">《企业内部控制基本规范》对照：</div>
                <div v-for="(m, i) in elementRef(cosoTab.tab).prcMapping" :key="i" class="prc-item">
                  <span class="prc-clause">{{ m.clause }}</span> {{ m.text }}
                </div>
              </div>
            </div>
          </details>

          <!-- 编制提示 -->
          <details class="b22a-tips">
            <summary>编制提示（CAS 依据与方法要点）</summary>
            <ul>
              <li v-for="(t, i) in elementRef(cosoTab.tab).preparationTips" :key="i">{{ t }}</li>
            </ul>
          </details>

          <!-- 检查项表格 (Task 3.3) -->
          <el-table :data="getCheckItems(cosoTab.tab)" border size="small" class="check-item-table">
            <el-table-column type="expand">
              <template #default="{ row }">
                <div class="control-attrs">
                  <div class="control-attrs-title">控制矩阵登记（B22B 属性）</div>
                  <div class="control-attrs-grid">
                    <div class="attr-item">
                      <label>是否反舞弊控制</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).antiFraud || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'antiFraud', v)">
                        <el-option label="是" value="Y" /><el-option label="否" value="N" />
                      </el-select>
                    </div>
                    <div class="attr-item">
                      <label>控制频率</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).frequency || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'frequency', v)">
                        <el-option v-for="f in CONTROL_FREQUENCY" :key="f" :label="f" :value="f" />
                      </el-select>
                    </div>
                    <div class="attr-item">
                      <label>执行人</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).performer || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'performer', v)">
                        <el-option v-for="p in CONTROL_PERFORMER" :key="p" :label="p" :value="p" />
                      </el-select>
                    </div>
                    <div class="attr-item">
                      <label>执行人胜任能力</label>
                      <el-input :model-value="attrsOf(cosoTab.tab, row.index).competence || ''" :disabled="isReadonly" size="small" placeholder="知识/经验/技能" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'competence', v)" />
                    </div>
                    <div class="attr-item">
                      <label>与控制相关的风险</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).risk || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'risk', v)">
                        <el-option v-for="r in CONTROL_RISK" :key="r" :label="r" :value="r" />
                      </el-select>
                    </div>
                    <div class="attr-item">
                      <label>自动/人工</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).nature || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'nature', v)">
                        <el-option v-for="n in CONTROL_NATURE" :key="n" :label="n" :value="n" />
                      </el-select>
                    </div>
                    <div class="attr-item">
                      <label>IT 应用名称</label>
                      <el-input :model-value="attrsOf(cosoTab.tab, row.index).itApp || ''" :disabled="isReadonly" size="small" placeholder="如适用" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'itApp', v)" />
                    </div>
                    <div class="attr-item">
                      <label>是否拟测试（→C类）</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).toTest || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'toTest', v)">
                        <el-option label="是" value="Y" /><el-option label="否" value="N" />
                      </el-select>
                    </div>
                    <div class="attr-item" v-if="attrsOf(cosoTab.tab, row.index).toTest === 'Y'">
                      <label>控制测试方法</label>
                      <el-select :model-value="attrsOf(cosoTab.tab, row.index).testMethod || ''" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleAttrChange(cosoTab.tab, row.index, 'testMethod', v)">
                        <el-option v-for="tm in CONTROL_TEST_METHOD" :key="tm" :label="tm" :value="tm" />
                      </el-select>
                    </div>
                  </div>
                </div>
              </template>
            </el-table-column>
            <el-table-column label="序号" width="60" align="center">
              <template #default="{ row }">{{ row.index }}</template>
            </el-table-column>
            <el-table-column label="控制要点" min-width="160">
              <template #default="{ row }">
                <el-input
                  :model-value="row.controlPoint"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="控制要点..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'point', v)"
                />
                <!-- 上年结论灰色提示 (Task 3.11) -->
                <span v-if="row.priorYearConclusion" class="prior-year-hint">
                  上年: {{ row.priorYearConclusion }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="控制活动描述" min-width="180">
              <template #default="{ row }">
                <el-input
                  :model-value="row.description"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="描述控制活动..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'desc', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="了解方法" width="200">
              <template #default="{ row }">
                <el-checkbox-group
                  :model-value="row.methods"
                  :disabled="isReadonly"
                  @update:model-value="(v: string[]) => handleMethodChange(cosoTab.tab, row.index, v)"
                >
                  <el-checkbox v-for="m in UNDERSTANDING_METHODS" :key="m" :label="m" :value="m" />
                </el-checkbox-group>
              </template>
            </el-table-column>
            <el-table-column label="结论" width="130">
              <template #default="{ row }">
                <el-select
                  :model-value="row.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="选择结论"
                  :class="{ 'deficiency-select': row.isDeficiency }"
                  @update:model-value="(v: string) => handleConclusionChange(cosoTab.tab, row.index, v)"
                >
                  <el-option v-for="c in CONCLUSIONS" :key="c" :label="c" :value="c" />
                </el-select>
                <span v-if="row.isDeficiency" class="deficiency-badge">缺陷</span>
              </template>
            </el-table-column>
            <el-table-column label="参考引用" width="120">
              <template #default="{ row }">
                <el-input
                  :model-value="row.reference"
                  :disabled="isReadonly"
                  placeholder="索引..."
                  @update:model-value="(v: string) => handleTextFieldChange(cosoTab.tab, row.index, 'ref', v)"
                />
              </template>
            </el-table-column>

            <el-table-column label="操作" width="150" align="center">
              <template #default="{ row }">
                <el-button
                  type="primary"
                  size="small"
                  link
                  @click="openEditItemDialog(cosoTab.tab, row.index)"
                >
                  {{ isReadonly ? '查看' : '编辑' }}
                </el-button>
                <!-- 本年无变化 (Task 3.11) -->
                <el-button
                  v-if="!isReadonly && row.priorYearConclusion && !row.noChangeConfirmed"
                  size="small"
                  link
                  @click="handleMarkNoChange(cosoTab.tab, row.index)"
                >
                  本年无变化
                </el-button>
                <span v-if="row.noChangeConfirmed" class="no-change-tag">
                  ✓ 无变化 ({{ row.noChangeConfirmer }})
                </span>
                <el-button
                  v-if="!isReadonly && !row.isPreset"
                  type="danger"
                  size="small"
                  link
                  @click="handleRemoveCheckItem(cosoTab.tab, row.index)"
                >
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- ═══ Tab 4 IT 详细结构化子区（B22A-4-1 ~ 4-4-2）═══ -->
          <div v-if="cosoTab.tab === 4" class="it-subsection">
            <div class="it-header">
              <h4>IT 详细了解（B22A-4）</h4>
              <div class="it-dependency-selector">
                <span>IT依赖程度：</span>
                <el-select
                  :model-value="itDependency"
                  :disabled="isReadonly"
                  size="small"
                  style="width: 100px"
                  @update:model-value="handleITDependencyChange"
                >
                  <el-option label="高" value="高" />
                  <el-option label="中" value="中" />
                  <el-option label="低" value="低" />
                </el-select>
                <span v-if="IT_REQUIRED_MAP[itDependency].hint" class="it-hint">
                  {{ IT_REQUIRED_MAP[itDependency].hint }}
                </span>
              </div>
            </div>

            <!-- ITGC 无效警告 -->
            <div v-if="isITGCInvalid" class="warning-banner warning-banner--orange" style="margin: 8px 0">
              ⚠️ ITGC 结论为无效——IT应用控制可靠性受到影响
            </div>

            <!-- B22A-4-1 IT 概要（复杂度判断）-->
            <div class="it-block">
              <div class="it-block-header">
                <h5>一、IT 概要（B22A-4-1，复杂度判断）</h5>
                <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddItSummary">+ 新增应用/基础设施</el-button>
              </div>
              <el-table :data="getItSummaryRows()" border size="small" class="it-table">
                <el-table-column label="序号" width="56" align="center">
                  <template #default="{ row }">{{ row.index }}</template>
                </el-table-column>
                <el-table-column label="类别" width="130">
                  <template #default="{ row }">
                    <el-select :model-value="row.kind" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleItSummaryField(row.index, 'kind', v)">
                      <el-option v-for="k in IT_SUMMARY_KIND_OPTIONS" :key="k" :label="k" :value="k" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="应用程序/基础设施描述" min-width="200">
                  <template #default="{ row }">
                    <el-input :model-value="row.appDesc" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" placeholder="名称与功能范围..." @update:model-value="(v: string) => handleItSummaryField(row.index, 'appDesc', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="复杂因素" min-width="180">
                  <template #default="{ row }">
                    <el-select :model-value="row.complexFactor" :disabled="isReadonly" size="small" placeholder="选择复杂因素类别" style="width:100%" @update:model-value="(v: string) => handleItSummaryField(row.index, 'complexFactor', v)">
                      <el-option v-for="f in IT_COMPLEX_FACTOR_OPTIONS" :key="f" :label="f" :value="f" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="复杂性" width="120">
                  <template #default="{ row }">
                    <el-select :model-value="row.complexity" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleItSummaryField(row.index, 'complexity', v)">
                      <el-option v-for="c in IT_COMPLEXITY_OPTIONS" :key="c" :label="c" :value="c" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="70" align="center">
                  <template #default="{ row }">
                    <el-button v-if="!isReadonly" type="danger" size="small" link @click="handleRemoveItSummary(row.index)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- B22A-4-2 系统清单 -->
            <div class="it-block">
              <div class="it-block-header">
                <h5>二、系统清单（B22A-4-2）</h5>
                <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddItSystem">+ 新增系统</el-button>
              </div>
              <el-table :data="getItSystemRows()" border size="small" class="it-table">
                <el-table-column label="序号" width="56" align="center">
                  <template #default="{ row }">{{ row.index }}</template>
                </el-table-column>
                <el-table-column label="重大业务流程" min-width="130">
                  <template #default="{ row }">
                    <el-input :model-value="row.process" :disabled="isReadonly" size="small" placeholder="业务流程..." @update:model-value="(v: string) => handleItSystemField(row.index, 'process', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="涉及的信息系统" min-width="130">
                  <template #default="{ row }">
                    <el-input :model-value="row.system" :disabled="isReadonly" size="small" placeholder="信息系统..." @update:model-value="(v: string) => handleItSystemField(row.index, 'system', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="关键系统模块" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.keyModule" :disabled="isReadonly" size="small" placeholder="模块..." @update:model-value="(v: string) => handleItSystemField(row.index, 'keyModule', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="索引号" width="90">
                  <template #default="{ row }">
                    <el-input :model-value="row.indexNo" :disabled="isReadonly" size="small" placeholder="索引" @update:model-value="(v: string) => handleItSystemField(row.index, 'indexNo', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="依赖程度" width="100">
                  <template #default="{ row }">
                    <el-select :model-value="row.dependency" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleItSystemField(row.index, 'dependency', v)">
                      <el-option v-for="d in IT_SYSTEM_DEPENDENCY_OPTIONS" :key="d" :label="d" :value="d" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="纳入测试范围" width="110">
                  <template #default="{ row }">
                    <el-select :model-value="row.inScope" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleItSystemField(row.index, 'inScope', v)">
                      <el-option v-for="y in IT_YESNO_OPTIONS" :key="y" :label="y" :value="y" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="备注" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.remark" :disabled="isReadonly" size="small" placeholder="备注..." @update:model-value="(v: string) => handleItSystemField(row.index, 'remark', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="70" align="center">
                  <template #default="{ row }">
                    <el-button v-if="!isReadonly" type="danger" size="small" link @click="handleRemoveItSystem(row.index)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- B22A-4-3 IT 环境 4 维 -->
            <div class="it-block">
              <div class="it-block-header">
                <h5>三、IT 环境（B22A-4-3）</h5>
              </div>
              <div class="it-env-grid">
                <div v-for="dim in IT_ENV_DIMENSIONS" :key="dim.key" class="it-env-item">
                  <div class="it-env-label">{{ dim.label }}</div>
                  <div class="it-env-hint">{{ dim.hint }}</div>
                  <el-input
                    :model-value="getItEnvNote(dim.key)"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                    placeholder="了解记录..."
                    @update:model-value="(v: string) => handleItEnvNote(dim.key, v)"
                  />
                </div>
              </div>
            </div>

            <!-- B22A-4-4-1 IT 一般控制 ITGC -->
            <div class="it-block">
              <div class="it-block-header">
                <h5>四、IT 一般控制 ITGC（B22A-4-4-1）</h5>
                <GtIndexChip value="wp:C22" :context-project-id="projectId" />
              </div>
              <el-alert :closable="false" type="info" show-icon class="it-scope-note">
                <template #title>
                  IT 一般控制的设计/运行有效性测试记录在 <strong>C22 ITGC 底稿</strong>，本区仅作了解。
                </template>
              </el-alert>
              <div v-for="cat in IT_ITGC_CATEGORIES" :key="cat.key" class="itgc-cat">
                <div class="itgc-cat-head">
                  <span class="itgc-cat-label">{{ cat.label }}</span>
                  <div class="itgc-cat-conclusion">
                    <span>结论：</span>
                    <el-select
                      :model-value="getItgcCategory(cat.key).conclusion || ''"
                      :disabled="isReadonly"
                      size="small"
                      placeholder="选择"
                      style="width: 110px"
                      @update:model-value="(v: string) => handleItgcConclusion(cat.key, v)"
                    >
                      <el-option v-for="c in ITGC_CONCLUSION_OPTIONS" :key="c" :label="c" :value="c" />
                    </el-select>
                  </div>
                </div>
                <div class="itgc-cat-hint">{{ cat.hint }}</div>
                <el-input
                  :model-value="getItgcCategory(cat.key).note"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 2, maxRows: 5 }"
                  placeholder="了解记录..."
                  @update:model-value="(v: string) => handleItgcNote(cat.key, v)"
                />
              </div>
            </div>

            <!-- B22A-4-4-2 IT 职责分离 SoD -->
            <div class="it-block">
              <div class="it-block-header">
                <h5>五、IT 职责分离 SoD（B22A-4-4-2）</h5>
                <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddSod">+ 新增人员</el-button>
              </div>
              <el-table :data="getSodRows()" border size="small" class="it-table">
                <el-table-column label="序号" width="56" align="center">
                  <template #default="{ row }">{{ row.index }}</template>
                </el-table-column>
                <el-table-column label="人员(角色)" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.person" :disabled="isReadonly" size="small" placeholder="人员/角色..." @update:model-value="(v: string) => handleSodField(row.index, 'person', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="授权和批准" min-width="110">
                  <template #default="{ row }">
                    <el-input :model-value="row.authApprove" :disabled="isReadonly" size="small" placeholder="职责..." @update:model-value="(v: string) => handleSodField(row.index, 'authApprove', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="进程访问请求" min-width="110">
                  <template #default="{ row }">
                    <el-input :model-value="row.accessRequest" :disabled="isReadonly" size="small" placeholder="职责..." @update:model-value="(v: string) => handleSodField(row.index, 'accessRequest', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="监督" min-width="100">
                  <template #default="{ row }">
                    <el-input :model-value="row.supervision" :disabled="isReadonly" size="small" placeholder="职责..." @update:model-value="(v: string) => handleSodField(row.index, 'supervision', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="业务/财报流程" min-width="120">
                  <template #default="{ row }">
                    <el-input :model-value="row.businessProcess" :disabled="isReadonly" size="small" placeholder="流程..." @update:model-value="(v: string) => handleSodField(row.index, 'businessProcess', v, true)" />
                  </template>
                </el-table-column>
                <el-table-column label="存在职责分离问题" width="120">
                  <template #default="{ row }">
                    <el-select :model-value="row.hasSodIssue" :disabled="isReadonly" size="small" placeholder="选择" @update:model-value="(v: string) => handleSodField(row.index, 'hasSodIssue', v)">
                      <el-option v-for="y in IT_YESNO_OPTIONS" :key="y" :label="y" :value="y" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="识别出缺陷" width="110">
                  <template #default="{ row }">
                    <el-select :model-value="row.hasDeficiency" :disabled="isReadonly" size="small" placeholder="选择" :class="{ 'deficiency-select': row.hasDeficiency === '是' }" @update:model-value="(v: string) => handleSodField(row.index, 'hasDeficiency', v)">
                      <el-option v-for="y in IT_YESNO_OPTIONS" :key="y" :label="y" :value="y" />
                    </el-select>
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="70" align="center">
                  <template #default="{ row }">
                    <el-button v-if="!isReadonly" type="danger" size="small" link @click="handleRemoveSod(row.index)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </div>

          <!-- ═══ 财务报告过程（B22A-4-5，信息与沟通下 4 个子过程）═══ -->
          <div v-if="cosoTab.tab === 3" class="frp-subsection">
            <div class="frp-header">
              <h4>财务报告过程（B22A-4-5）</h4>
              <el-tag v-if="frpApplicableGapCount > 0" size="small" type="warning">{{ frpApplicableGapCount }} 个适用子过程待记录</el-tag>
              <el-tag v-else size="small" type="success">已记录</el-tag>
            </div>
            <el-alert :closable="false" type="info" show-icon class="frp-note">
              <template #title>
                致同源模板「财务报告过程」= 信息与沟通下 4 个子过程。勾选「不适用」的子过程不计入完成度告警。
              </template>
            </el-alert>
            <div v-for="sp in FRP_SUBPROCESSES" :key="sp.key" class="frp-item" :class="{ 'frp-item--na': frpOf(sp.key).na }">
              <div class="frp-item-head">
                <span class="frp-item-title">{{ sp.label }}</span>
                <el-checkbox
                  :model-value="frpOf(sp.key).na"
                  :disabled="isReadonly"
                  @update:model-value="(v: any) => handleFrpNaChange(sp.key, !!v)"
                >不适用</el-checkbox>
              </div>
              <div class="frp-item-hint">{{ sp.hint }}</div>
              <el-input
                :model-value="frpOf(sp.key).note"
                :disabled="isReadonly || frpOf(sp.key).na"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="了解记录..."
                @update:model-value="(v: string) => handleFrpNoteChange(sp.key, v)"
              />
            </div>
          </div>

          <!-- ═══ 管理层凌驾于控制之上专区（B22A-2，CAS 1141 强制反舞弊）═══ -->
          <div v-if="cosoTab.tab === 2" class="mo-subsection">
            <div class="mo-header">
              <h4>管理层凌驾于控制之上（针对性控制）</h4>
              <div class="mo-header-actions">
                <el-button v-if="!isReadonly" size="small" @click="handleApplyMoExamples">套用示例控制</el-button>
                <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddMoItem">+ 新增控制</el-button>
              </div>
            </div>
            <el-alert :closable="false" type="warning" show-icon class="mo-objective">
              <template #title>{{ moRef.auditObjective }}</template>
            </el-alert>

            <!-- 管理层凌驾控制检查项 -->
            <el-table :data="getMoItems()" border size="small" class="check-item-table">
              <el-table-column label="序号" width="60" align="center">
                <template #default="{ row }">{{ row.index }}</template>
              </el-table-column>
              <el-table-column label="针对凌驾风险设计的控制" min-width="180">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.controlPoint"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 3 }"
                    placeholder="如：独立董事季度查阅关联方资金往来 / 举报热线..."
                    @update:model-value="(v: string) => handleMoTextChange(row.index, 'point', v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="信息来源及控制如何执行" min-width="180">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.description"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 3 }"
                    placeholder="描述信息来源及控制执行情况..."
                    @update:model-value="(v: string) => handleMoTextChange(row.index, 'desc', v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="了解方法" width="200">
                <template #default="{ row }">
                  <el-checkbox-group
                    :model-value="row.methods"
                    :disabled="isReadonly"
                    @update:model-value="(v: string[]) => handleMoMethodChange(row.index, v)"
                  >
                    <el-checkbox v-for="m in UNDERSTANDING_METHODS" :key="m" :label="m" :value="m" />
                  </el-checkbox-group>
                </template>
              </el-table-column>
              <el-table-column label="结论" width="130">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.conclusion || ''"
                    :disabled="isReadonly"
                    placeholder="选择结论"
                    :class="{ 'deficiency-select': row.isDeficiency }"
                    @update:model-value="(v: string) => handleMoConclusionChange(row.index, v)"
                  >
                    <el-option v-for="c in CONCLUSIONS" :key="c" :label="c" :value="c" />
                  </el-select>
                  <span v-if="row.isDeficiency" class="deficiency-badge">缺陷</span>
                </template>
              </el-table-column>
              <el-table-column label="参考引用" width="110">
                <template #default="{ row }">
                  <el-input
                    :model-value="row.reference"
                    :disabled="isReadonly"
                    placeholder="如 C23/C24"
                    @update:model-value="(v: string) => handleMoTextChange(row.index, 'ref', v)"
                  />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="80" align="center">
                <template #default="{ row }">
                  <el-button v-if="!isReadonly" type="danger" size="small" link @click="handleRemoveMoItem(row.index)">删除</el-button>
                </template>
              </el-table-column>
            </el-table>

            <!-- 关键判断：管理层是否未能识别应识别的重大错报风险 -->
            <div class="mo-key-judgment">
              <div class="mo-kj-row">
                <label>{{ moRef.keyJudgment }}</label>
                <el-radio-group :model-value="moKeyAnswer" :disabled="isReadonly" @update:model-value="(v: any) => handleMoKeyAnswerChange(String(v))">
                  <el-radio value="是">是</el-radio>
                  <el-radio value="否">否</el-radio>
                </el-radio-group>
              </div>
              <el-input
                v-if="moKeyAnswer === '是'"
                :model-value="moKeyNote"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 4 }"
                placeholder="描述管理层未能识别的重大错报风险及原因..."
                @update:model-value="handleMoKeyNoteChange"
              />
            </div>

            <div class="mo-link-hint">
              📎 管理层凌驾控制应与 <span class="ref-chip">C23/C24 会计分录测试</span> 及 <span class="ref-chip">B50 舞弊风险</span> 交叉索引；即使控制设计存在，仍须执行不可预见的会计分录测试。
            </div>
            <div v-if="!isReadonly" class="mo-push-actions">
              <el-button size="small" type="warning" @click="handlePushMoToB50">
                推送管理层凌驾发现至 B50
              </el-button>
              <el-button size="small" @click="handleMoC23Hint">
                提示 C23/C24 测试范围
              </el-button>
            </div>
          </div>

          <!-- 底部：审计说明 + 要素整体结论 (Task 3.3) -->
          <div class="tab-footer">
            <div class="tab-note-section">
              <div class="note-label-row">
                <label>审计说明：</label>
                <GtReviewTrigger :section-id="`B22A-T${cosoTab.tab}-note`" label="💬 复核" />
                <el-button
                  v-if="!isReadonly"
                  size="small"
                  text
                  type="primary"
                  :loading="aiLoading === `T${cosoTab.tab}-note`"
                  @click="generateAi(`${elementRef(cosoTab.tab).elementName}审计说明`, getTabNote(cosoTab.tab), (t) => handleTabNoteChange(cosoTab.tab, t))"
                >
                  🤖 AI 辅助
                </el-button>
              </div>
              <el-input
                :model-value="getTabNote(cosoTab.tab)"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="审计说明..."
                @update:model-value="(v: string) => handleTabNoteChange(cosoTab.tab, v)"
              />
            </div>
            <div class="tab-score-section">
              <label>要素整体结论：</label>
              <span
                class="score-display"
                :style="getScoreStyle(getEffectiveScore(cosoTab.tab))"
              >
                {{ getEffectiveScore(cosoTab.tab) || '未计算' }}
              </span>
              <span v-if="isScoreOverridden(cosoTab.tab)" class="override-badge">已手动调整</span>
              <el-button
                v-if="!isReadonly"
                size="small"
                link
                @click="showOverrideDialog(cosoTab.tab)"
              >
                手动调整
              </el-button>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ═══ Summary Tab: 控制矩阵汇总 (Task 3.5) ═══ -->
      <el-tab-pane label="📊 控制矩阵汇总" name="Tab_Summary">
        <div class="tab-content summary-tab">
          <!-- 控制环境薄弱横幅 (Task 3.12) -->
          <div v-if="controlEnvWeakWarning" class="warning-banner warning-banner--red" style="margin-bottom: 12px">
            ⚠️ 控制环境薄弱——建议提高整体风险评估
            <span class="ref-chip">📎 跳转 B50</span>
          </div>

          <!-- IT 控制薄弱警告 (Task 3.12) -->
          <div v-if="itControlWeakWarning" class="warning-banner warning-banner--orange" style="margin-bottom: 12px">
            ⚠️ IT通用控制(ITGC)无效——IT依赖程度高，应用控制可靠性受影响
          </div>

          <h3>交叉汇总矩阵</h3>

          <!-- 交叉矩阵 (Task 3.5) -->
          <div class="summary-matrix">
            <table class="matrix-table">
              <thead>
                <tr>
                  <th>检查维度</th>
                  <th v-for="t in COSO_TABS" :key="t.tab">{{ t.label }}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td class="dim-label">要素评价</td>
                  <td
                    v-for="t in COSO_TABS"
                    :key="t.tab"
                    :style="getScoreStyle(getEffectiveScore(t.tab))"
                    class="score-cell"
                  >
                    {{ getEffectiveScore(t.tab) || '—' }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">有效项</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.effective ?? 0 }}</td>
                </tr>
                <tr>
                  <td class="dim-label">缺陷项</td>
                  <td v-for="t in COSO_TABS" :key="t.tab" :class="{ 'has-deficiency': (elementStats[t.tab]?.deficient ?? 0) > 0 }">
                    {{ elementStats[t.tab]?.deficient ?? 0 }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">不适用</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.notApplicable ?? 0 }}</td>
                </tr>
                <tr>
                  <td class="dim-label">未完成</td>
                  <td v-for="t in COSO_TABS" :key="t.tab" :class="{ 'has-incomplete': (elementStats[t.tab]?.incomplete ?? 0) > 0 }">
                    {{ elementStats[t.tab]?.incomplete ?? 0 }}
                  </td>
                </tr>
                <tr>
                  <td class="dim-label">总计</td>
                  <td v-for="t in COSO_TABS" :key="t.tab">{{ elementStats[t.tab]?.total ?? 0 }}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <!-- 任一要素无效警告 (Task 3.5) -->
          <div
            v-if="COSO_TABS.some(t => getEffectiveScore(t.tab) === '无效')"
            class="warning-banner warning-banner--red"
            style="margin-top: 12px"
          >
            ⚠️ 存在要素评价为"无效"——请关注对整体控制风险的影响
          </div>

          <!-- 缺陷清单 (Task 3.6) -->
          <div class="deficiency-section">
            <h4>控制缺陷汇总 ({{ deficiencyList.length }} 项)</h4>
            <div v-if="deficiencyList.length === 0" class="empty-state">
              暂无控制缺陷
            </div>
            <el-table v-else :data="deficiencyList" border size="small">
              <el-table-column label="序号" width="60" align="center">
                <template #default="{ $index }">{{ $index + 1 }}</template>
              </el-table-column>
              <el-table-column label="来源要素" width="160" prop="elementName" />
              <el-table-column label="控制要点" min-width="200" prop="controlPoint" />
              <el-table-column label="缺陷类型" width="100">
                <template #default="{ row }">
                  <span class="deficiency-type-tag" :class="row.deficiencyType === '设计无效' ? 'tag-design' : 'tag-implement'">
                    {{ row.deficiencyType }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="引用" width="80" align="center">
                <template #default="{ row }">
                  <span class="ref-chip">📎 B22B</span>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 控制矩阵登记册（B22B）：全部控制 + 属性汇总 -->
          <div class="control-register-section">
            <div class="register-header">
              <h4>企业层面控制矩阵（源模板 B22B，{{ controlMatrixRegister.length }} 项）</h4>
              <el-button size="small" :disabled="controlMatrixRegister.length === 0" @click="exportControlMatrix">
                导出控制矩阵 (xlsx)
              </el-button>
            </div>
            <div class="register-source-note">
              本区即致同源模板 <strong>B22B 控制矩阵</strong>（12 列控制登记册）。数据由各要素检查项自动汇总——
              在检查项<strong>展开行</strong>录入控制属性（编号/频率/执行人/反舞弊/自动人工/IT应用/拟测试等），此处即时生成登记册。
            </div>
            <div v-if="controlMatrixRegister.length === 0" class="empty-state">
              暂无控制。请在各要素检查项中填写控制要点，并展开行录入控制属性（频率/执行人/反舞弊/拟测试等）。
            </div>
            <el-table v-else :data="controlMatrixRegister" border size="small" class="register-table" max-height="360">
              <el-table-column label="要素/子类别" width="150" prop="element" show-overflow-tooltip />
              <el-table-column label="控制名称/要点" min-width="160" prop="controlPoint" show-overflow-tooltip />
              <el-table-column label="反舞弊" width="70" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.antiFraud === '是'" size="small" type="danger">是</el-tag>
                  <span v-else>{{ row.antiFraud || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="频率" width="90" prop="frequency" />
              <el-table-column label="执行人" width="110" prop="performer" show-overflow-tooltip />
              <el-table-column label="风险" width="70" prop="risk" />
              <el-table-column label="自动/人工" width="120" prop="nature" show-overflow-tooltip />
              <el-table-column label="结论" width="100" prop="conclusion" />
              <el-table-column label="拟测试" width="70" align="center">
                <template #default="{ row }">
                  <el-tag v-if="row.toTest === '是'" size="small" type="success">是</el-tag>
                  <span v-else>{{ row.toTest || '—' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="测试方法" width="100" prop="testMethod" show-overflow-tooltip />
              <el-table-column label="引用" width="90" prop="reference" show-overflow-tooltip />
            </el-table>
            <div class="register-hint">
              「拟测试」为"是"的控制将通过 <span class="ref-chip">control:to-test-changed</span> 联动至 C1 企业层面控制测试。
            </div>
          </div>

          <!-- 整体结论 (Task 3.5) -->
          <div class="overall-conclusion-section">
            <h4>企业层面控制整体结论</h4>
            <div class="overall-row">
              <el-select
                :model-value="overallConclusion || ''"
                :disabled="isReadonly"
                placeholder="选择整体结论"
                @update:model-value="handleOverallConclusionChange"
              >
                <el-option v-for="s in ELEMENT_SCORE_OPTIONS" :key="s" :label="s" :value="s" />
              </el-select>
              <span
                v-if="overallConclusion"
                class="score-display"
                :style="getScoreStyle(overallConclusion)"
              >
                {{ overallConclusion }}
              </span>
            </div>
            <div class="overall-note">
              <div class="note-label-row">
                <label>整体说明：</label>
                <el-button
                  v-if="!isReadonly"
                  size="small"
                  text
                  type="primary"
                  :loading="aiLoading === 'summary-note'"
                  @click="generateAi('企业层面控制整体结论', summaryNote, handleSummaryNoteChange)"
                >
                  🤖 AI 辅助
                </el-button>
              </div>
              <el-input
                :model-value="summaryNote"
                :disabled="isReadonly"
                type="textarea"
                :autosize="{ minRows: 2, maxRows: 5 }"
                placeholder="整体结论说明..."
                @update:model-value="handleSummaryNoteChange"
              />
            </div>
          </div>

          <!-- 现场经理复核区 (Task 3.8) -->
          <div class="review-section">
            <h4>现场经理复核</h4>
            <div v-if="!isReviewed">
              <!-- 待完成事项 -->
              <div v-if="pendingItems.length > 0" class="pending-items">
                <p class="pending-title">⚠️ 以下事项需完成后方可签字：</p>
                <ul>
                  <li v-for="item in pendingItems" :key="item">{{ item }}</li>
                </ul>
              </div>
              <el-button
                type="primary"
                :disabled="!canReview || isReadonly"
                @click="handleReview"
              >
                现场经理签字复核
              </el-button>
            </div>
            <div v-else class="reviewed-info">
              <span>✅ 已完成复核</span>
              <span v-if="reviewInfo">— {{ reviewInfo.reviewer }} / {{ reviewInfo.date }}</span>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══ Element_Score 手动覆盖对话框 (Task 3.7) ═══ -->
    <el-dialog v-model="overrideDialogVisible" title="手动调整要素评价" width="450px" append-to-body>
      <div class="override-form">
        <p>自动计算结果将被覆盖，需填写调整理由。</p>
        <div class="override-field">
          <label>调整后评价：</label>
          <el-select v-model="overrideScore">
            <el-option v-for="s in ELEMENT_SCORE_OPTIONS" :key="s" :label="s" :value="s" />
          </el-select>
        </div>
        <div class="override-field">
          <label>调整理由：</label>
          <el-input
            v-model="overrideReason"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            placeholder="填写调整理由（必填）..."
          />
        </div>
      </div>
      <template #footer>
        <el-button @click="overrideDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="submitOverride">确认调整</el-button>
      </template>
    </el-dialog>

    <!-- ═══ Amendment 对话框 (Task 3.9) ═══ -->
    <el-dialog v-model="amendmentDialogVisible" title="修改内控评价（Amendment）" width="500px" append-to-body>
      <div class="amendment-form">
        <p>已复核的内控评价需重新修改时，请填写修改原因：</p>
        <el-input
          v-model="amendmentReason"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="填写修改原因..."
        />
        <p class="amendment-note">提交后复核状态将重置，修改完成后需重新现场经理签字。</p>
      </div>
      <template #footer>
        <el-button @click="amendmentDialogVisible = false">取消</el-button>
        <el-button type="warning" @click="submitAmendment">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- 引导式录入向导（弹窗）-->
    <B22AControlItemDialog
      v-model:visible="itemDialogVisible"
      :title="itemDialogTitle"
      :element-ref="elementRef(itemDialogTab)"
      :item="itemDialogItem"
      :attrs="itemDialogAttrs"
      :is-readonly="isReadonly"
      @save="onItemDialogSave"
    />

    <!-- Saving indicator -->
    <div v-if="saving" class="saving-indicator">保存中...</div>
  </div>
</template>

<style scoped>
/* ═══ 双模式工具栏 ═══ */
.b22-mode-toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 6px;
}

/* ═══ 基础布局 (Task 3.13) ═══ */
.gt-b22a-control-matrix {
  position: relative;
  padding: 16px;
  min-width: 768px;
  font-size: 13px;
  color: #303133;
}

/* 全局字号归一：表格 / 表单 / 页签 / 下拉统一 13px */
.gt-b22a-control-matrix :deep(.el-table),
.gt-b22a-control-matrix :deep(.el-table .cell),
.gt-b22a-control-matrix :deep(.el-form-item__label),
.gt-b22a-control-matrix :deep(.el-tabs__item),
.gt-b22a-control-matrix :deep(.el-input__inner),
.gt-b22a-control-matrix :deep(.el-textarea__inner),
.gt-b22a-control-matrix :deep(.el-select),
.gt-b22a-control-matrix :deep(.el-checkbox__label),
.gt-b22a-control-matrix :deep(.el-radio__label) {
  font-size: 13px;
}

/* 统一区块标题：左侧主色强调条 */
.gt-b22a-control-matrix .tab-content h3,
.gt-b22a-control-matrix .tab-content h4 {
  border-left: 3px solid var(--el-color-primary, #3B82F6);
  padding-left: 8px;
  line-height: 1.3;
}

.loading-mask {
  text-align: center;
  padding: 40px;
  color: #6B7280;
}

.saving-indicator {
  position: fixed;
  bottom: 16px;
  right: 16px;
  background: #3B82F6;
  color: white;
  padding: 6px 12px;
  border-radius: 4px;
  font-size: 12px;
  z-index: 1000;
}

/* ═══ 警告横幅 (Task 3.12) ═══ */
.warning-banner {
  border-radius: 6px;
  padding: 10px 16px;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  gap: 12px;
}

.warning-banner--red {
  background: #FEF2F2;
  border: 1px solid #FECACA;
  border-left: 3px solid #DC2626;
  color: #B91C1C;
}

.warning-banner--orange {
  background: #FFFBEB;
  border: 1px solid #FDE68A;
  border-left: 3px solid #D97706;
  color: #92400E;
}

/* ═══ 已复核横幅 (Task 3.8) ═══ */
.review-banner {
  background: #D1FAE5;
  border: 1px solid #059669;
  border-radius: 6px;
  padding: 10px 16px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 12px;
  color: #059669;
  font-weight: 600;
}

/* ═══ Tabs ═══ */
.b22a-tabs {
  margin-bottom: 16px;
}

.tab-progress {
  position: absolute;
  top: 8px;
  right: 16px;
  font-size: 12px;
  color: #6B7280;
}

.tab-content {
  padding: 12px 0;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-header h3 {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
}

/* ═══ 审计目标 / 方法论 / 编制提示 ═══ */
.b22a-objective {
  margin-bottom: 10px;
}
.b22a-methodology,
.b22a-tips {
  margin-bottom: 10px;
  font-size: var(--wp-font-size, 13px);
}
.b22a-methodology > summary,
.b22a-tips > summary {
  cursor: pointer;
  color: #92400E;
  font-weight: 600;
  padding: 6px 10px;
  background: #FEF9EC;
  border-left: 3px solid #D97706;
  border-radius: 3px;
}
.b22a-tips > summary {
  color: #1D4ED8;
  background: #EFF6FF;
  border-left-color: #3B82F6;
}
.methodology-body {
  padding: 10px;
  background: #FEFCF5;
  border: 1px solid #FDE9C8;
  border-radius: 0 0 4px 4px;
}
.coso-principle {
  margin-bottom: 8px;
}
.coso-principle-title {
  font-weight: 600;
  color: #374151;
  margin-bottom: 4px;
}
.coso-pof {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.pof-chip {
  background: #FEF3C7;
  color: #92400E;
  border-radius: 10px;
  padding: 1px 8px;
  font-size: 12px;
}
.prc-mapping {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #FDE9C8;
}
.prc-title {
  font-weight: 600;
  color: #374151;
  margin-bottom: 4px;
}
.prc-item {
  color: #6B7280;
  line-height: 1.6;
}
.prc-clause {
  color: #B45309;
  font-weight: 600;
}
.b22a-tips ul {
  margin: 6px 0 0 0;
  padding: 8px 10px 8px 26px;
  background: #EFF6FF;
  border: 1px solid #DBEAFE;
  border-radius: 0 0 4px 4px;
  line-height: 1.6;
}
.note-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

/* ═══ 管理层凌驾于控制之上专区 ═══ */
.mo-subsection {
  margin-top: 16px;
  padding: 12px;
  border: 1px solid #FCA5A5;
  border-radius: 6px;
  background: #FEF2F2;
}
.mo-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.mo-header h4 {
  margin: 0;
  color: #B91C1C;
  font-size: 14px;
}
.mo-objective {
  margin-bottom: 10px;
}
.mo-key-judgment {
  margin-top: 12px;
  padding: 10px;
  background: #fff;
  border: 1px solid #FECACA;
  border-radius: 4px;
}
.mo-kj-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
}
.mo-link-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #6B7280;
}
.mo-push-actions {
  margin-top: 8px;
  display: flex;
  gap: 8px;
}
.ref-chip {
  display: inline-block;
  background: #E0E7FF;
  color: #3730A3;
  border-radius: 3px;
  padding: 0 6px;
  font-size: 12px;
}

/* ═══ 控制矩阵登记册 ═══ */
.control-register-section {
  margin-top: 16px;
}
.register-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.register-header h4 {
  margin: 0;
  font-size: 14px;
}
.register-table {
  font-size: var(--wp-font-size, 13px);
}
.register-hint {
  margin-top: 6px;
  font-size: 12px;
  color: #6B7280;
}
.register-source-note {
  margin-bottom: 8px;
  padding: 8px 10px;
  font-size: 12px;
  line-height: 1.6;
  color: #3730A3;
  background: #EEF2FF;
  border-left: 3px solid #6366F1;
  border-radius: 0 4px 4px 0;
}

/* ═══ 控制矩阵属性展开行 ═══ */
.control-attrs {
  padding: 10px 16px;
  background: #F9FAFB;
}
.control-attrs-title {
  font-weight: 600;
  color: #374151;
  margin-bottom: 8px;
  font-size: var(--wp-font-size, 13px);
}
.control-attrs-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 10px 16px;
}
.attr-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.attr-item label {
  font-size: 12px;
  color: #6B7280;
}

.tab-header-actions {
  display: flex;
  gap: 8px;
}

.tab-header-progress {
  margin-left: 12px;
}

/* ═══ 检查项表格 (Task 3.3) ═══ */
.check-item-table {
  margin-bottom: 12px;
}

.deficiency-select :deep(.el-input__wrapper) {
  border-color: #DC2626 !important;
  box-shadow: 0 0 0 1px #DC2626 inset !important;
}

.deficiency-badge {
  display: inline-block;
  background: #FEE2E2;
  color: #DC2626;
  font-size: 10px;
  font-weight: 700;
  padding: 1px 4px;
  border-radius: 3px;
  margin-top: 2px;
}

.prior-year-hint {
  display: block;
  font-size: 11px;
  color: #9CA3AF;
  font-style: italic;
  margin-top: 2px;
}

.no-change-tag {
  font-size: 11px;
  color: #059669;
  display: block;
  margin-bottom: 4px;
}

.ref-chip {
  display: inline-block;
  background: #EFF6FF;
  border: 1px solid #93C5FD;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: #2563EB;
  cursor: pointer;
}

/* ═══ Tab 4 IT 详细结构化子区 (Task 5) ═══ */
.it-subsection {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 2px solid #E5E7EB;
}

.it-scope-note {
  margin-bottom: 12px;
}

.it-block {
  margin-top: 16px;
  padding: 12px;
  background: #FAFBFC;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}
.it-block-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}
.it-block-header h5 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  border-left: 3px solid var(--el-color-primary, #3B82F6);
  padding-left: 8px;
  line-height: 1.3;
}
.it-table {
  margin-bottom: 4px;
}
.it-env-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.it-env-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.it-env-label {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.it-env-hint,
.itgc-cat-hint {
  font-size: 11px;
  color: #9CA3AF;
  margin-bottom: 2px;
}
.itgc-cat {
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px dashed #E5E7EB;
}
.itgc-cat-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 2px;
}
.itgc-cat-label {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.itgc-cat-conclusion {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: #6B7280;
}

/* ═══ 财务报告过程 (B22A-4-5) ═══ */
.frp-subsection {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 2px solid #E5E7EB;
}
.frp-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 8px;
}
.frp-header h4 {
  margin: 0;
}
.frp-note {
  margin-bottom: 12px;
}
.frp-item {
  margin-top: 10px;
  padding: 10px 12px;
  background: #FAFBFC;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}
.frp-item--na {
  opacity: 0.55;
  background: #F3F4F6;
}
.frp-item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 2px;
}
.frp-item-title {
  font-size: 13px;
  font-weight: 600;
  color: #374151;
}
.frp-item-hint {
  font-size: 11px;
  color: #9CA3AF;
  margin-bottom: 4px;
}

.it-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.it-header h4 {
  margin: 0;
  font-size: 14px;
}

.it-dependency-selector {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
}

.it-hint {
  color: #D97706;
  font-size: 12px;
  font-weight: 600;
}

.it-panel-content {
  padding: 8px 0;
}

.it-panel-toolbar {
  margin-bottom: 8px;
}

/* ═══ Tab 底部区域 (Task 3.3) ═══ */
.tab-footer {
  margin-top: 16px;
  padding-top: 16px;
  border-top: 1px solid #E5E7EB;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.tab-note-section {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tab-note-section label,
.tab-score-section label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #374151;
}

.tab-score-section {
  display: flex;
  align-items: center;
  gap: 12px;
}

.score-display {
  display: inline-block;
  padding: 4px 12px;
  border-radius: 4px;
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
}

.override-badge {
  background: #DBEAFE;
  color: #1D4ED8;
  font-size: 10px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

/* ═══ Summary Tab (Task 3.5) ═══ */
.summary-tab h3,
.summary-tab h4 {
  margin: 16px 0 8px;
  font-size: 14px;
}

.summary-matrix {
  overflow-x: auto;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}

.matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
}

.matrix-table th,
.matrix-table td {
  padding: 10px 12px;
  border: 1px solid #E5E7EB;
  text-align: center;
}

.matrix-table th {
  background: #F3F4F6;
  font-weight: 700;
  font-size: 12px;
}

.matrix-table .dim-label {
  text-align: left;
  font-weight: 600;
  background: #F9FAFB;
  min-width: 80px;
}

.score-cell {
  font-weight: 700;
}

.has-deficiency {
  color: #DC2626;
  font-weight: 700;
}

.has-incomplete {
  color: #D97706;
  font-weight: 700;
}

/* ═══ 缺陷清单 (Task 3.6) ═══ */
.deficiency-section {
  margin-top: 20px;
}

.deficiency-type-tag {
  display: inline-block;
  padding: 2px 6px;
  border-radius: 3px;
  font-size: 11px;
  font-weight: 600;
}

.tag-design {
  background: #FEE2E2;
  color: #DC2626;
}

.tag-implement {
  background: #FEF3C7;
  color: #D97706;
}

.empty-state {
  text-align: center;
  padding: 24px;
  color: #6B7280;
}

/* ═══ 整体结论 (Task 3.5) ═══ */
.overall-conclusion-section {
  margin-top: 20px;
  padding: 16px;
  background: #F9FAFB;
  border-radius: 6px;
  border: 1px solid #E5E7EB;
}

.overall-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;
}

.overall-note {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.overall-note label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #374151;
}

/* ═══ 复核区 (Task 3.8) ═══ */
.review-section {
  margin-top: 20px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  background: #FAFAFA;
}

.review-section h4 {
  margin: 0 0 12px;
  font-size: 14px;
}

.pending-items {
  margin-bottom: 12px;
}

.pending-title {
  color: #D97706;
  font-weight: 600;
  margin-bottom: 4px;
}

.pending-items ul {
  margin: 0;
  padding-left: 20px;
  font-size: var(--wp-font-size, 13px);
  color: #6B7280;
}

.reviewed-info {
  color: #059669;
  font-weight: 600;
}

/* ═══ 对话框 (Task 3.7 / 3.9) ═══ */
.override-form,
.amendment-form {
  font-size: var(--wp-font-size, 13px);
}

.override-form p,
.amendment-form p {
  margin: 8px 0;
}

.override-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 12px;
}

.override-field label {
  font-size: 12px;
  font-weight: 600;
}

.amendment-note {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}

/* ═══ 只读模式 (Task 3.9) ═══ */
.is-readonly .check-item-table :deep(.el-input__wrapper),
.is-readonly .check-item-table :deep(.el-textarea__inner) {
  cursor: default;
}

/* ═══ 响应式布局 (Task 3.13) ═══ */
@media (min-width: 1024px) {
  .summary-matrix {
    overflow-x: visible;
  }
}

@media (max-width: 1023px) and (min-width: 768px) {
  .gt-b22a-control-matrix {
    overflow-x: auto;
  }
  .summary-matrix {
    overflow-x: auto;
  }
  .matrix-table {
    min-width: 700px;
  }
}

/* ═══ 打印样式 (Task 4.1) ═══ */
@media print {
  .gt-b22a-control-matrix {
    padding: 0;
  }

  /* 隐藏交互控件 */
  .tab-header-actions,
  .it-panel-toolbar,
  .it-dependency-selector,
  .review-section .el-button,
  .saving-indicator,
  .warning-banner .ref-chip,
  .tab-progress,
  .el-button,
  .el-select,
  .el-checkbox,
  .el-input,
  .el-textarea {
    display: none !important;
  }

  /* A4 横版 */
  @page {
    size: A4 landscape;
    margin: 10mm;
  }

  /* 保持颜色 */
  .score-display,
  .score-cell,
  .deficiency-badge,
  .deficiency-type-tag,
  .review-banner,
  .warning-banner,
  .matrix-table th,
  .matrix-table td {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }

  /* 矩阵满宽 */
  .summary-matrix {
    overflow: visible;
    border: 1px solid #000;
  }

  .matrix-table {
    min-width: unset;
    width: 100%;
  }

  /* 显示数据文本替代输入框 */
  .check-item-table :deep(.el-input__inner),
  .check-item-table :deep(.el-textarea__inner) {
    border: none !important;
    box-shadow: none !important;
    padding: 0 !important;
    background: transparent !important;
  }
}
</style>
