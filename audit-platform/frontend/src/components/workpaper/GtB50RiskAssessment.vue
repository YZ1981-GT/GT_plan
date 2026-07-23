<script setup lang="ts">
/**
 * GtB50RiskAssessment — B50 重大错报风险评估汇总
 *
 * 4-Tab 统一界面：
 *   Tab 1: 风险因素识别
 *   Tab 2: 报表层面重大错报风险
 *   Tab 3: 认定层面风险矩阵（默认激活）
 *   Tab 4: 特别风险汇总
 *
 * Spec: .kiro/specs/b50-risk-assessment/
 * Tasks: 3.1 ~ 3.12, 4.1
 */
import { ref, computed, watch, toRef, onMounted, onUnmounted, nextTick, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useB50FormData, type ChecklistItem } from './composables/useB50FormData'
import { useB50RiskMatrix, RISK_COLOR_MAP, ASSERTIONS, CYCLE_OPTIONS, CONTROL_RELIANCE_OPTIONS, APPROACH_OPTIONS, CATEGORY_OPTIONS, type RiskLevel, type Assertion, type RiskLayer } from './composables/useB50RiskMatrix'
import { useB50DetailColumnPrefs } from './composables/useB50DetailColumnPrefs'
import { useB50Approval } from './composables/useB50Approval'
import { useB50OoSheetMap } from './composables/useB50OoSheetMap'
import { useWorkpaperEntryDualMode, type WorkpaperRenderMode } from './composables/useWorkpaperEntryDualMode'
import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'

const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))
const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const B50AccountRiskDialog = defineAsyncComponent(() => import('./B50AccountRiskDialog.vue'))

// ─── Props / Emits ───────────────────────────────────────────────────────────

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

// ─── Composables 初始化 ──────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly')

const {
  allResponses,
  loading,
  saving,
  loadAll,
  saveImmediate,
  saveDebouncedText,
  tab1Data,
  tab2Data,
  tab3Data,
  tab4Data,
  getField,
  setFieldImmediate,
} = useB50FormData(wpIdRef)

const {
  accounts,
  addAccount,
  importAccounts,
  removeAccount,
  setCellRisk,
  toggleSpecialRisk,
  setCycle,
  setPlanField,
  setScopeField,
  suggestedApproach,
  applyAccountPatch,
  ensurePresetCycleDefaults,
  matrixStats,
  incompleteAccounts,
  specialRiskCells,
  colorMap,
  isFraudPresumptionActive,
  filterLevel,
} = useB50RiskMatrix(tab3Data, saveImmediate)

// Tab3 元列显隐偏好（余额/类别/会计估计/循环/应对方案）
const columnPrefs = useB50DetailColumnPrefs()
const columnPopoverVisible = ref(false)

const CATEGORY_LABELS: Record<string, string> = {
  scot: 'SCOT+',
  amount_only: '仅金额重大',
  other: '其他',
  '': '—',
}
const APPROACH_LABEL: Record<string, string> = {
  substantive: '实质性方案',
  combined: '综合性方案',
}

function handleSetScopeField(account: string, field: 'balance' | 'category' | 'estimate', value: string | number | null) {
  if (isReadonly.value) return
  setScopeField(account, field, value)
  emit('save')
}

// 引导式录入弹窗
const guideDialogVisible = ref(false)
const guideRow = ref<any>(null)
function openGuideDialog(row: any) {
  if (isReadonly.value) return
  guideRow.value = row
  guideDialogVisible.value = true
}
function onGuideApply(account: string, patch: any) {
  applyAccountPatch(account, patch)
  emit('save')
}

const {
  isApproved,
  isReadonly,
  canApprove,
  pendingItems,
  approvalInfo,
  doApproval,
  startAmendment,
} = useB50Approval(
  wpIdRef,
  allResponses,
  incompleteAccounts,
  specialRiskCells,
  externalReadonly as any,
  saveImmediate
)

// ─── 版本链 + 复核对话（对齐 B60/B212 范式）───────────────────────────────────

const { versionTrailRef, scheduleAutoSnapshot, openVersionHistory } = useWorkpaperVersionToolbar({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId') as any,
})
const { openReview } = useWorkpaperReviewProvide({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId') as any,
})

// ─── Tab 状态 ────────────────────────────────────────────────────────────────

const activeTab = ref('tab3')

// ─── 双模式 HTML ↔ OnlyOffice（对齐 D4 范式，健康检查 gate）──────────────────

const dualMode = useWorkpaperEntryDualMode({
  reloadAllResponses: async () => { await loadAll() },
  resolveOoSheetName: () => ooSheetName.value,
})
const { ooSheetName, ooSourceWpId, refreshSourceWpId } = useB50OoSheetMap({
  projectId: toRef(props, 'projectId') as any,
  activeTab,
  selfWpId: toRef(props, 'wpId') as any,
})
const renderMode = computed<WorkpaperRenderMode>({
  get: () => dualMode.mode.value,
  set: (v) => { void dualMode.switchMode(v) },
})
const renderModeOptions = computed(() => [
  { label: '结构化', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const, disabled: !dualMode.ooAvailable.value },
])
// 切到 OnlyOffice 或切 Tab 时解析当前 Tab 对应源子底稿 wp_id
watch([() => dualMode.mode.value, activeTab], ([mode]) => {
  if (mode === 'onlyoffice') void refreshSourceWpId()
})

// 程序表索引跳转：B50-1→tab1 … B50-4→tab4
const PROGRAM_INDEX_TAB_MAP: Record<string, string> = {
  'B50-1': 'tab1', 'B50-2': 'tab2', 'B50-3': 'tab3', 'B50-4': 'tab4',
}
function onProgramIndexJump(indexRef: string) {
  const base = (indexRef || '').trim().toUpperCase()
  const target = PROGRAM_INDEX_TAB_MAP[base]
  if (target) activeTab.value = target
}

// Tab 完成状态
type TabStatus = 'empty' | 'partial' | 'complete'

const tab1Status = computed<TabStatus>(() => {
  const countItem = allResponses.value.get('B50-T1-count')
  const count = parseInt(countItem?.remark || '0', 10)
  if (count === 0) return 'empty'
  // Check if all factors have description + source
  for (let i = 0; i < count; i++) {
    const desc = allResponses.value.get(`B50-T1-factor-${i}-desc`)
    const src = allResponses.value.get(`B50-T1-factor-${i}-source`)
    if (!desc?.remark?.trim() || !src?.conclusion) return 'partial'
  }
  return 'complete'
})

const tab2Status = computed<TabStatus>(() => {
  const countItem = allResponses.value.get('B50-T2-count')
  const count = parseInt(countItem?.remark || '0', 10)
  if (count === 0) return 'empty'
  for (let i = 0; i < count; i++) {
    const level = allResponses.value.get(`B50-T2-fs-${i}-level`)
    const resp = allResponses.value.get(`B50-T2-fs-${i}-response`)
    if (!level?.conclusion || !resp?.remark?.trim()) return 'partial'
  }
  return 'complete'
})

const tab3Status = computed<TabStatus>(() => {
  if (accounts.value.length === 0) return 'empty'
  if (incompleteAccounts.value.length === 0) return 'complete'
  // Some cells filled?
  const hasAny = accounts.value.some(row =>
    ASSERTIONS.some(a => row.cells[a].combinedRisk !== null)
  )
  return hasAny ? 'partial' : 'empty'
})

const tab4Status = computed<TabStatus>(() => {
  if (specialRiskCells.value.length === 0) return 'empty'
  const allHaveResponse = specialRiskCells.value.every(sr => {
    const id = `B50-T4-sr-${sr.account}-${sr.assertion}-response`
    const item = allResponses.value.get(id)
    return !!item?.remark?.trim()
  })
  return allHaveResponse ? 'complete' : 'partial'
})

function tabStatusIcon(status: TabStatus): string {
  switch (status) {
    case 'complete': return '✅'
    case 'partial': return '🔶'
    case 'empty': return '⬜'
  }
}

const overallProgress = computed(() => {
  const statuses = [tab1Status.value, tab2Status.value, tab3Status.value, tab4Status.value]
  const done = statuses.filter(s => s === 'complete').length
  return `${done}/4`
})

// ─── Tab 1: 风险因素识别 ─────────────────────────────────────────────────────

const tab1Count = computed(() => {
  const item = allResponses.value.get('B50-T1-count')
  return parseInt(item?.remark || '0', 10)
})

const SOURCE_OPTIONS = [
  { value: 'B22A', label: 'B22A 内控了解' },
  { value: 'B23', label: 'B23 流程了解' },
  { value: 'industry', label: '行业分析' },
  { value: 'discussion', label: '项目组讨论' },
  { value: 'prior_audit', label: '前期审计经验' },
  { value: 'management_interview', label: '管理层访谈' },
  { value: 'b2_predecessor', label: 'B2 前任沟通' },
  { value: 'other', label: '其他' },
] as const

// 风险因素类型（源模板 B50-1：舞弊/错误/持续经营）
const FACTOR_TYPE_OPTIONS = [
  { value: 'fraud', label: '舞弊' },
  { value: 'error', label: '错误' },
  { value: 'going_concern', label: '持续经营' },
] as const

// 影响层次（源模板 B50-1：财务报表层次/认定层次）
const IMPACT_LAYER_OPTIONS = [
  { value: 'fs', label: '财务报表层次' },
  { value: 'assertion', label: '认定层次' },
  { value: 'both', label: '两者' },
] as const

function addFactorRow() {
  if (isReadonly.value) return
  const n = tab1Count.value
  const newCount: ChecklistItem = { item_id: 'B50-T1-count', conclusion: null, remark: String(n + 1), wp_ref: null }
  allResponses.value.set(newCount.item_id, newCount)
  saveImmediate([newCount])
}

async function deleteFactorRow(index: number) {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm(`确认删除第 ${index + 1} 行风险因素？`, '删除确认', { type: 'warning' })
  } catch { return }
  // Shift rows down
  const count = tab1Count.value
  const T1_SUFFIXES = ['desc', 'type', 'is_inherent', 'impact_layer', 'source', 'accounts', 'assertions', 'risk', 'transferred']
  for (let i = index; i < count - 1; i++) {
    for (const suffix of T1_SUFFIXES) {
      const nextItem = allResponses.value.get(`B50-T1-factor-${i + 1}-${suffix}`)
      const currentId = `B50-T1-factor-${i}-${suffix}`
      if (nextItem) {
        const shifted: ChecklistItem = { ...nextItem, item_id: currentId }
        allResponses.value.set(currentId, shifted)
      } else {
        allResponses.value.delete(currentId)
      }
    }
  }
  // Remove last row
  for (const suffix of T1_SUFFIXES) {
    allResponses.value.delete(`B50-T1-factor-${count - 1}-${suffix}`)
  }
  const newCount: ChecklistItem = { item_id: 'B50-T1-count', conclusion: null, remark: String(count - 1), wp_ref: null }
  allResponses.value.set(newCount.item_id, newCount)
  saveImmediate([newCount])
}

function updateFactorField(index: number, suffix: string, value: string, isConclusion = false) {
  if (isReadonly.value) return
  const itemId = `B50-T1-factor-${index}-${suffix}`
  const item: ChecklistItem = {
    item_id: itemId,
    conclusion: isConclusion ? value : null,
    remark: isConclusion ? null : value,
    wp_ref: null,
  }
  allResponses.value.set(itemId, item)
  if (isConclusion) {
    saveImmediate([item])
  } else {
    saveDebouncedText(item)
  }
}

// 风险因素一键分流：按影响层次转入报表层次(Tab2)/认定矩阵(Tab3)
function transferFactor(idx: number) {
  if (isReadonly.value) return
  const desc = allResponses.value.get(`B50-T1-factor-${idx}-desc`)?.remark?.trim() || ''
  const layer = allResponses.value.get(`B50-T1-factor-${idx}-impact_layer`)?.conclusion || ''
  const ftype = allResponses.value.get(`B50-T1-factor-${idx}-type`)?.conclusion || ''
  const accountsStr = allResponses.value.get(`B50-T1-factor-${idx}-accounts`)?.remark?.trim() || ''
  if (!desc) { ElMessage.warning('请先填写风险因素描述'); return }
  if (!layer) { ElMessage.warning('请先选择"影响层次"'); return }

  const msgs: string[] = []
  // 财务报表层次 → Tab2
  if (layer === 'fs' || layer === 'both') {
    const n = tab2Count.value
    const batch: ChecklistItem[] = [
      { item_id: `B50-T2-fs-${n}-desc`, conclusion: null, remark: desc, wp_ref: null },
      { item_id: `B50-T2-fs-${n}-special`, conclusion: ftype === 'fraud' ? 'Y' : 'N', remark: null, wp_ref: null },
      { item_id: `B50-T2-fs-${n}-refindex`, conclusion: null, remark: 'B50-1', wp_ref: null },
      { item_id: 'B50-T2-count', conclusion: null, remark: String(n + 1), wp_ref: null },
    ]
    for (const it of batch) allResponses.value.set(it.item_id, it)
    saveImmediate(batch)
    msgs.push('已转入报表层次风险(Tab2)')
  }
  // 认定层次 → Tab3 矩阵科目
  if (layer === 'assertion' || layer === 'both') {
    if (accountsStr) {
      const names = accountsStr.split(/[,，、;；\s]+/).filter(Boolean)
      const added = importAccounts(names.map(name => ({ name })))
      msgs.push(added ? `认定矩阵新增 ${added} 个科目(Tab3)` : '认定矩阵科目已存在')
    } else {
      msgs.push('未填写"影响科目/认定"，请手动在矩阵中添加')
    }
  }
  updateFactorField(idx, 'transferred', 'Y', true)
  ElMessage.success(msgs.join('；'))
}

// ─── Tab 2: 报表层面风险 ─────────────────────────────────────────────────────

const tab2Count = computed(() => {
  const item = allResponses.value.get('B50-T2-count')
  return parseInt(item?.remark || '0', 10)
})

const CATEGORY_OPTIONS = [
  { value: 'control_env', label: '内控环境' },
  { value: 'management_integrity', label: '管理层诚信' },
  { value: 'economic_env', label: '经济环境' },
  { value: 'industry_factor', label: '行业因素' },
  { value: 'other', label: '其他' },
] as const

const tab2Stats = computed(() => {
  let H = 0, M = 0, L = 0
  for (let i = 0; i < tab2Count.value; i++) {
    const level = allResponses.value.get(`B50-T2-fs-${i}-level`)?.conclusion
    if (level === 'H') H++
    else if (level === 'M') M++
    else if (level === 'L') L++
  }
  return { H, M, L }
})

function addFsRiskRow() {
  if (isReadonly.value) return
  const n = tab2Count.value
  const newCount: ChecklistItem = { item_id: 'B50-T2-count', conclusion: null, remark: String(n + 1), wp_ref: null }
  allResponses.value.set(newCount.item_id, newCount)
  saveImmediate([newCount])
}

async function deleteFsRiskRow(index: number) {
  if (isReadonly.value) return
  try {
    await ElMessageBox.confirm(`确认删除第 ${index + 1} 行报表层面风险？`, '删除确认', { type: 'warning' })
  } catch { return }
  const count = tab2Count.value
  const T2_SUFFIXES = ['desc', 'category', 'level', 'special', 'refindex', 'entity_response', 'response', 'b60ref']
  for (let i = index; i < count - 1; i++) {
    for (const suffix of T2_SUFFIXES) {
      const nextItem = allResponses.value.get(`B50-T2-fs-${i + 1}-${suffix}`)
      const currentId = `B50-T2-fs-${i}-${suffix}`
      if (nextItem) {
        allResponses.value.set(currentId, { ...nextItem, item_id: currentId })
      } else {
        allResponses.value.delete(currentId)
      }
    }
  }
  for (const suffix of T2_SUFFIXES) {
    allResponses.value.delete(`B50-T2-fs-${count - 1}-${suffix}`)
  }
  const newCount: ChecklistItem = { item_id: 'B50-T2-count', conclusion: null, remark: String(count - 1), wp_ref: null }
  allResponses.value.set(newCount.item_id, newCount)
  saveImmediate([newCount])
}

function updateFsField(index: number, suffix: string, value: string, isConclusion = false) {
  if (isReadonly.value) return
  const itemId = `B50-T2-fs-${index}-${suffix}`
  const item: ChecklistItem = {
    item_id: itemId,
    conclusion: isConclusion ? value : null,
    remark: isConclusion ? null : value,
    wp_ref: null,
  }
  allResponses.value.set(itemId, item)
  if (isConclusion) {
    saveImmediate([item])
  } else {
    saveDebouncedText(item)
  }
}

// ─── Tab 3: 风险矩阵 ─────────────────────────────────────────────────────────

const ASSERTION_LABELS: Record<Assertion, string> = {
  existence: '存在',
  completeness: '完整性',
  accuracy: '准确性',
  cutoff: '截止',
  classification: '分类',
  presentation: '列报',
}

// Popover 编辑状态
const popoverVisible = ref(false)
const editingCell = ref<{ account: string; assertion: Assertion } | null>(null)
const editIR = ref<RiskLevel | null>(null)
const editCR = ref<RiskLevel | null>(null)
const editRMM = ref<RiskLevel | null>(null)

function openCellPopover(account: string, assertion: Assertion) {
  if (isReadonly.value) return
  const row = accounts.value.find(a => a.name === account)
  if (!row) return
  const cell = row.cells[assertion]
  editingCell.value = { account, assertion }
  editIR.value = cell.inherentRisk
  editCR.value = cell.controlRisk
  editRMM.value = cell.combinedRisk
  popoverVisible.value = true
}

function saveCellEdit() {
  if (!editingCell.value) return
  const { account, assertion } = editingCell.value
  const oldRow = accounts.value.find(a => a.name === account)
  const oldCombined = oldRow?.cells[assertion].combinedRisk ?? null

  if (editIR.value) setCellRisk(account, assertion, 'inherent', editIR.value)
  if (editCR.value) setCellRisk(account, assertion, 'control', editCR.value)
  if (editRMM.value) {
    setCellRisk(account, assertion, 'combined', editRMM.value)
    // EventBus: risk:combined-changed (Task 3.11)
    if (editRMM.value !== oldCombined) {
      try {
        // TODO: Add 'risk:combined-changed' to eventBus Events type when ready
        (eventBus as any).emit('risk:combined-changed', {
          account,
          assertion,
          newLevel: editRMM.value,
          oldLevel: oldCombined,
        })
      } catch (e) {
        console.warn('[B50] EventBus emit failed:', e)
      }
    }
  }
  popoverVisible.value = false
  editingCell.value = null
  emit('save')
}

function cancelCellEdit() {
  popoverVisible.value = false
  editingCell.value = null
}

// 新增科目
const newAccountName = ref('')

function handleAddAccount() {
  if (isReadonly.value || !newAccountName.value.trim()) return
  addAccount(newAccountName.value.trim())
  newAccountName.value = ''
}

// 从试算表一键导入重要科目（B50-3 确定审计范围）
const importingScope = ref(false)

// ─── P3-8: B50×B15 重要性联动 ─────────────────────────────────────────────────
// 从 /api/materiality 读取三级重要性，展示在 Tab3 + 提供风险×重要性→TE建议
interface MaterialityInfo { pm: number; te: number; sat: number; perfRatio: number }
const materialityInfo = ref<MaterialityInfo | null>(null)

async function loadMateriality() {
  try {
    const res: any = await api.get('/api/materiality', { params: { project_id: props.projectId, year: props.year } })
    const d = res?.data ?? res
    if (d && d.overall_materiality) {
      materialityInfo.value = {
        pm: Number(d.overall_materiality) || 0,
        te: Number(d.performance_materiality) || 0,
        sat: Number(d.trivial_threshold) || 0,
        perfRatio: Number(d.performance_ratio) || 50,
      }
    }
  } catch { /* B15 尚未设置 */ }
}

// 风险×重要性→建议 TE 比例（CAS：高风险→降低 TE 加大测试范围）
function suggestedTeRatio(maxRisk: string | null): { ratio: string; hint: string } {
  if (!materialityInfo.value) return { ratio: '—', hint: '请先在 B15 设置重要性水平' }
  switch (maxRisk) {
    case 'H': return { ratio: '45-50%', hint: '高风险→较低执行重要性→扩大测试范围' }
    case 'M': return { ratio: '50-65%', hint: '中风险→适中执行重要性' }
    case 'L': return { ratio: '65-75%', hint: '低风险→较高执行重要性→可缩小范围' }
    default: return { ratio: '—', hint: '未评估风险等级' }
  }
}

async function handleImportScopeAccounts() {
  if (isReadonly.value) return
  importingScope.value = true
  try {
    const res: any = await api.get('/api/b50/scope-accounts', {
      params: { project_id: props.projectId, year: props.year },
    })
    const data = res?.data ?? res
    const list: { name: string; cycle?: string }[] = Array.isArray(data?.accounts) ? data.accounts : []
    if (!list.length) {
      ElMessage.info(data?.summary || '试算表暂无重要科目可导入')
      return
    }
    const added = importAccounts(list)
    if (added) {
      ElMessage.success(`已从试算表导入 ${added} 个重要报表项目（业务循环已按科目名预映射，请复核）`)
      // 触发下游循环缓存失效
      try { (eventBus as any).emit('risk:cycle-changed', { wpId: props.wpId }) } catch { /* noop */ }
    } else {
      ElMessage.info('试算表科目已全部在矩阵中，无需重复导入')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '请稍后重试'))
  } finally {
    importingScope.value = false
  }
}

function handleRemoveAccount(index: number) {
  if (isReadonly.value) return
  const row = accounts.value[index]
  if (row?.isPreset) {
    ElMessage.warning('此条目为 CAS 强制要求，不可删除')
    return
  }
  removeAccount(index)
}

// 特别风险切换
function handleToggleSpecialRisk(account: string, assertion: Assertion) {
  if (isReadonly.value) return
  const row = accounts.value.find(a => a.name === account)
  if (!row) return
  if (account === '管理层凌驾控制' && row.cells[assertion].isSpecialRisk) {
    ElMessage.warning('此条目为 CAS 强制要求，不可取消特别风险标记')
    return
  }
  toggleSpecialRisk(account, assertion)
  // EventBus: risk:special-risk-changed (Task 3.11)
  try {
    (eventBus as any).emit('risk:special-risk-changed', { account, assertion })
  } catch (e) {
    console.warn('[B50] EventBus emit failed:', e)
  }
}

// 业务循环 / 应对方案（行级，驱动 B50→D~N 路由）
function handleSetCycle(account: string, cycleCode: string) {
  if (isReadonly.value) return
  setCycle(account, cycleCode || null)
  // 通知下游循环程序表 auto_data_source 缓存失效
  try {
    (eventBus as any).emit('risk:cycle-changed', { wpId: props.wpId, account, cycle: cycleCode })
  } catch { /* noop */ }
  emit('save')
}

function handleSetPlanField(account: string, field: 'reliance' | 'subonly' | 'approach', value: string) {
  if (isReadonly.value) return
  setPlanField(account, field, value || null)
  emit('save')
}

// 筛选
const FILTER_OPTIONS: { value: RiskLevel | ''; label: string }[] = [
  { value: '', label: '全部' },
  { value: 'H', label: '高风险' },
  { value: 'M', label: '中风险' },
  { value: 'L', label: '低风险' },
]

function setFilter(val: string) {
  filterLevel.value = val ? (val as RiskLevel) : null
}

// 获取单元格颜色样式
function getCellStyle(account: string, assertion: Assertion) {
  const key = `${account}-${assertion}`
  const color = colorMap.value.get(key)
  const row = accounts.value.find(a => a.name === account)
  const cell = row?.cells[assertion]
  const isSpecial = cell?.isSpecialRisk
  return {
    backgroundColor: color?.bg || '#F9FAFB',
    color: color?.text || '#374151',
    border: isSpecial ? '2px solid #DC2626' : '1px solid #E5E7EB',
  }
}

// Tooltip 内容
function getCellTooltip(account: string, assertion: Assertion): string {
  const row = accounts.value.find(a => a.name === account)
  if (!row) return ''
  const cell = row.cells[assertion]
  const ir = cell.inherentRisk ? RISK_COLOR_MAP[cell.inherentRisk].label : '未设'
  const cr = cell.controlRisk ? RISK_COLOR_MAP[cell.controlRisk].label : '未设'
  const rmm = cell.combinedRisk ? RISK_COLOR_MAP[cell.combinedRisk].label : '未设'
  let tip = `固有风险: ${ir}\n控制风险: ${cr}\n综合风险: ${rmm}`
  if (cell.isSpecialRisk) tip += '\n⚠️ 特别风险'
  if (cell.remark) tip += `\n备注: ${cell.remark}`
  return tip
}

// 行最高综合风险（应对方案表用）
function rowMaxRisk(row: { cells: Record<Assertion, { combinedRisk: RiskLevel | null }> }): RiskLevel | null {
  const order: RiskLevel[] = ['H', 'M', 'L']
  for (const lvl of order) {
    if (ASSERTIONS.some(a => row.cells[a].combinedRisk === lvl)) return lvl
  }
  return null
}
function rowMaxRiskLabel(row: any): string {
  const r = rowMaxRisk(row)
  return r ? RISK_COLOR_MAP[r].label : '未评'
}
function rowMaxRiskColor(row: any): string {
  const r = rowMaxRisk(row)
  return r ? RISK_COLOR_MAP[r].text : '#9CA3AF'
}

// 是否被筛选隐藏
function isCellHidden(account: string, assertion: Assertion): boolean {
  if (!filterLevel.value) return false
  const row = accounts.value.find(a => a.name === account)
  return row?.cells[assertion].combinedRisk !== filterLevel.value
}

// ─── Tab 4: 特别风险汇总 ─────────────────────────────────────────────────────

function getSpecialRiskTag(account: string): string | null {
  if (account === '收入确认') return 'CAS推定'
  if (account === '管理层凌驾控制') return '强制特别风险'
  return null
}

function getResponseText(account: string, assertion: Assertion): string {
  const id = `B50-T4-sr-${account}-${assertion}-response`
  return allResponses.value.get(id)?.remark || ''
}

function updateResponseText(account: string, assertion: Assertion, value: string) {
  if (isReadonly.value) return
  const id = `B50-T4-sr-${account}-${assertion}-response`
  const item: ChecklistItem = { item_id: id, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(id, item)
  saveDebouncedText(item)
}

function getRefText(account: string, assertion: Assertion): string {
  const id = `B50-T4-sr-${account}-${assertion}-refs`
  return allResponses.value.get(id)?.remark || ''
}

function updateRefText(account: string, assertion: Assertion, value: string) {
  if (isReadonly.value) return
  const id = `B50-T4-sr-${account}-${assertion}-refs`
  const item: ChecklistItem = { item_id: id, conclusion: null, remark: value, wp_ref: null }
  allResponses.value.set(id, item)
  saveDebouncedText(item)
}

// 源模板 B50-4 补充列：是否舞弊导致 / 管理层应对或控制 / 向被审计单位报告事项
function getSrConclusion(account: string, assertion: Assertion, suffix: string): string {
  return allResponses.value.get(`B50-T4-sr-${account}-${assertion}-${suffix}`)?.conclusion || ''
}
function getSrRemark(account: string, assertion: Assertion, suffix: string): string {
  return allResponses.value.get(`B50-T4-sr-${account}-${assertion}-${suffix}`)?.remark || ''
}
function updateSrField(account: string, assertion: Assertion, suffix: string, value: string, isConclusion = false) {
  if (isReadonly.value) return
  const id = `B50-T4-sr-${account}-${assertion}-${suffix}`
  const item: ChecklistItem = {
    item_id: id,
    conclusion: isConclusion ? value : null,
    remark: isConclusion ? null : value,
    wp_ref: null,
  }
  allResponses.value.set(id, item)
  if (isConclusion) saveImmediate([item])
  else saveDebouncedText(item)
}
// 舞弊推定：收入确认/管理层凌驾控制默认由舞弊导致
function fraudPresumed(account: string): boolean {
  return account === '收入确认' || account === '管理层凌驾控制'
}

// 应对程序 soft validation (CAS: 不得仅含分析程序)
const DETAIL_TEST_KEYWORDS = ['细节测试', '函证', '检查', '观察', '询问', '重新执行', '监盘']
const ANALYTICAL_ONLY_KEYWORDS = ['分析程序', '分析性程序', '实质性分析程序', '趋势分析']

function isResponseInvalid(text: string): boolean {
  if (!text.trim()) return false // empty handled separately
  const hasAnalytical = ANALYTICAL_ONLY_KEYWORDS.some(kw => text.includes(kw))
  const hasDetail = DETAIL_TEST_KEYWORDS.some(kw => text.includes(kw))
  return hasAnalytical && !hasDetail
}

// ─── CAS 舞弊推定反驳弹窗 (Task 3.8) ────────────────────────────────────────

const fraudDialogVisible = ref(false)
const fraudRebuttalAccount = ref('')
const fraudRebuttalAssertion = ref<Assertion>('existence')
const fraudRebuttalReason = ref('')

function showFraudRebuttalDialog(account: string, assertion: Assertion) {
  fraudRebuttalAccount.value = account
  fraudRebuttalAssertion.value = assertion
  fraudRebuttalReason.value = ''
  fraudDialogVisible.value = true
}

async function submitFraudRebuttal() {
  if (!fraudRebuttalReason.value.trim()) {
    ElMessage.warning('请填写反驳理由')
    return
  }
  const account = fraudRebuttalAccount.value
  const assertion = fraudRebuttalAssertion.value
  // Save rebuttal reason
  const reasonItem: ChecklistItem = {
    item_id: `B50-rebuttal-${account}-${assertion}-reason`,
    conclusion: null,
    remark: fraudRebuttalReason.value.trim(),
    wp_ref: null,
  }
  // Save partner sign (placeholder — in real flow partner signs separately)
  const signItem: ChecklistItem = {
    item_id: `B50-rebuttal-${account}-${assertion}-sign`,
    conclusion: 'Y',
    remark: '当前用户',
    wp_ref: new Date().toISOString().slice(0, 10),
  }
  allResponses.value.set(reasonItem.item_id, reasonItem)
  allResponses.value.set(signItem.item_id, signItem)
  await saveImmediate([reasonItem, signItem])
  fraudDialogVisible.value = false
  ElMessage.success('舞弊推定反驳已记录')
}

// ─── 合伙人审批 (Task 3.9) ───────────────────────────────────────────────────

async function handleApproval() {
  if (!canApprove.value || isReadonly.value) return
  try {
    await ElMessageBox.confirm('确认签字审批？审批后全部内容将锁定为只读。', '合伙人审批', { type: 'info' })
  } catch { return }
  await doApproval()
  emit('save')
  emit('completed')
}

// ─── Amendment (Task 3.10) ───────────────────────────────────────────────────

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
    ElMessage.success('已重置审批，可继续编辑')
  } catch (e: any) {
    ElMessage.error(e.message || '操作失败')
  }
}

// ─── EventBus: Tab 2 → B60 同步 (Task 3.11) ─────────────────────────────────

function emitFsRiskChange() {
  try {
    (eventBus as any).emit('risk:fs-level-changed', {
      wpId: props.wpId,
      stats: tab2Stats.value,
    })
  } catch (e) {
    console.warn('[B50] EventBus fs-level emit failed:', e)
  }
}

// ─── B2 前任沟通发现 → 风险因素（Task 9 / R6.1） ───────────────────────────
// 监听 b2_predecessor 推送，向 Tab1 追加风险因素行（source=b2_predecessor）。
// 按描述去重，避免重复推送生成重复行。
function existingFactorDescs(): Set<string> {
  const set = new Set<string>()
  const count = tab1Count.value
  for (let i = 0; i < count; i++) {
    const d = allResponses.value.get(`B50-T1-factor-${i}-desc`)?.remark?.trim()
    if (d) set.add(d)
  }
  return set
}

/** 共享：把一批风险因素描述追加到 B50-T1 风险因素清单（按描述去重） */
function _appendFactorDescs(descs: string[], source: string): number {
  const clean = descs.map((d) => String(d || '').trim()).filter(Boolean)
  if (!clean.length) return 0
  const existing = existingFactorDescs()
  let idx = tab1Count.value
  const batch: ChecklistItem[] = []
  let added = 0
  for (const desc of clean) {
    if (existing.has(desc)) continue
    batch.push({ item_id: `B50-T1-factor-${idx}-desc`, conclusion: null, remark: desc, wp_ref: null })
    batch.push({ item_id: `B50-T1-factor-${idx}-source`, conclusion: source, remark: null, wp_ref: null })
    existing.add(desc)
    idx += 1
    added += 1
  }
  if (!added) return 0
  batch.push({ item_id: 'B50-T1-count', conclusion: null, remark: String(idx), wp_ref: null })
  for (const it of batch) allResponses.value.set(it.item_id, it)
  saveImmediate(batch)
  return added
}

function appendRiskFactorsFromB2(payload: any) {
  if (isReadonly.value) return
  const factors: string[] = Array.isArray(payload?.factors) ? payload.factors : []
  // 来源尊重推送方（B2 前任沟通默认 b2_predecessor；B23 业务层面控制传 'B23'，两者均在白名单）
  const rawSource = String(payload?.source || 'b2_predecessor')
  const source = SOURCE_OPTIONS.some((o) => o.value === rawSource) ? rawSource : 'b2_predecessor'
  const srcLabel = SOURCE_OPTIONS.find((o) => o.value === source)?.label || '关联底稿'
  const added = _appendFactorDescs(factors, source)
  if (added) ElMessage.success(`已从 ${srcLabel} 新增 ${added} 项风险因素`)
  else if (factors.length) ElMessage.info('该来源发现已在风险因素中，无需重复添加')
}

const B22A_ELEMENT_NAMES: Record<number, string> = {
  1: '控制环境', 2: '风险评估过程', 3: '信息系统与沟通', 4: '控制活动', 5: '监督',
}

/** B22A 企业层面控制结论变更 → 薄弱要素自动进入 B50 风险因素（控制风险输入） */
function onControlConclusionChanged(payload: any) {
  if (isReadonly.value) return
  const descs: string[] = []
  const scores = payload?.elementScores || {}
  for (const [tab, score] of Object.entries(scores)) {
    if (score === '无效' || score === '部分有效') {
      const name = B22A_ELEMENT_NAMES[Number(tab)] || `要素${tab}`
      descs.push(`企业层面控制薄弱：${name}设计有效性评价为「${score}」（来自 B22A）`)
    }
  }
  if (payload?.itgcConclusion === '无效' && payload?.itDependency === '高') {
    descs.push('IT 通用控制(ITGC)无效且 IT 依赖程度高，自动化控制与系统生成报告可靠性受影响（来自 B22A）')
  }
  const added = _appendFactorDescs(descs, 'b22a_control')
  if (added) ElMessage.success(`已从 B22A 内控了解新增 ${added} 项控制风险因素`)
}

/** B22A 控制环境薄弱事件 → B50 风险因素 */
function onControlEnvironmentWeak(payload: any) {
  if (isReadonly.value || !payload?.weak) return
  _appendFactorDescs(
    [`控制环境薄弱（管理层诚信/治理层独立性相关控制存在缺陷），建议提高整体重大错报风险评估（来自 B22A）`],
    'b22a_control',
  )
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  ensurePresetCycleDefaults()
  loadMateriality()
  eventBus.on('b50:push-risk-factor' as any, appendRiskFactorsFromB2)
  eventBus.on('control:conclusion-changed' as any, onControlConclusionChanged)
  eventBus.on('control:environment-weak' as any, onControlEnvironmentWeak)
})

onUnmounted(() => {
  eventBus.off('b50:push-risk-factor' as any, appendRiskFactorsFromB2)
  eventBus.off('control:conclusion-changed' as any, onControlConclusionChanged)
  eventBus.off('control:environment-weak' as any, onControlEnvironmentWeak)
})

// Watch isApproved → emit completed
watch(isApproved, (val) => {
  if (val) emit('completed')
})

// Watch saving → emit save on successful saves + 触发版本自动快照（debounced）
watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) {
    emit('save')
    try { scheduleAutoSnapshot?.() } catch { /* noop */ }
  }
})
</script>

<template>
  <div class="gt-b50-risk-assessment" :class="{ 'is-readonly': isReadonly }">
    <!-- 已审批横幅 (Task 3.9/3.10) -->
    <div v-if="isApproved" class="approval-banner">
      <span>✅ 已审批</span>
      <span v-if="approvalInfo">（{{ approvalInfo.signer }} / {{ approvalInfo.date }}）</span>
      <el-button v-if="!externalReadonly" size="small" type="warning" @click="showAmendmentDialog">
        修改（Amendment）
      </el-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-mask">加载中...</div>

    <!-- 顶部工具栏：版本历史 + 复核对话 + 双模式切换 -->
    <div class="b50-top-toolbar">
      <el-button size="small" @click="openVersionHistory">📜 版本历史</el-button>
      <el-button size="small" type="primary" plain @click="openReview({ sectionId: 'B50-risk-assessment', sectionLabel: 'B50 风险评估复核' })">
        💬 复核
      </el-button>
      <div class="b50-mode-toolbar">
        <el-segmented v-model="renderMode" :options="renderModeOptions" size="small" />
        <el-tag v-if="!dualMode.ooAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>
    </div>

    <!-- 审计目标（CAS 1211/1231） -->
    <el-alert
      class="b50-audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：识别、评估财务报表层次与认定层次的重大错报风险（含特别风险），并据此确定进一步审计程序的性质、时间与范围（CAS 1211 / 1231）。"
    />

    <!-- 进度指示 -->
    <div class="tab-progress">完成进度: {{ overallProgress }}</div>

    <!-- OnlyOffice 在线编辑模式：按当前 Tab 打开对应源子底稿 -->
    <template v-if="renderMode === 'onlyoffice'">
      <GtOnlyOfficeSheet
        v-if="ooSourceWpId"
        :key="`${ooSourceWpId}-${ooSheetName}`"
        :wp-id="ooSourceWpId"
        :sheet-name="ooSheetName"
        :project-id="props.projectId"
        :readonly="isReadonly"
        @fallback="() => dualMode.switchMode('html')"
      />
      <div v-else class="oo-not-instantiated">
        <el-empty description="该子表在本项目未实例化，请使用结构化模式编辑" />
      </div>
    </template>

    <!-- Tab 容器 (Task 3.2) -->
    <el-tabs v-else v-model="activeTab" type="border-card" class="b50-tabs">
      <!-- ═══ Tab 0: 汇总程序表 ═══ -->
      <el-tab-pane label="📋 汇总程序表" name="program">
        <div class="tab-content">
          <GtAProgramConsole
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :html-data="{}"
            :is-readonly="isReadonly"
            @jump-to-workpaper="onProgramIndexJump"
          />
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 1: 风险因素识别 ═══ -->
      <el-tab-pane :label="`${tabStatusIcon(tab1Status)} 风险因素识别`" name="tab1">
        <div class="tab-content">
          <div class="tab-header">
            <h3>风险因素识别</h3>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addFactorRow">
              + 新增因素
            </el-button>
          </div>

          <el-table :data="Array.from({ length: tab1Count }, (_, i) => i)" border size="small" class="factor-table">
            <el-table-column label="序号" width="60" align="center">
              <template #default="{ row: idx }">{{ idx + 1 }}</template>
            </el-table-column>
            <el-table-column label="风险因素描述" min-width="200">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-desc`)?.remark || ''"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="描述风险因素..."
                  @update:model-value="(v: string) => updateFactorField(idx, 'desc', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="类型" width="110">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-type`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="类型"
                  @update:model-value="(v: string) => updateFactorField(idx, 'type', v, true)"
                >
                  <el-option v-for="opt in FACTOR_TYPE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="是否固有风险因素" width="120" align="center">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-is_inherent`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="是/否"
                  @update:model-value="(v: string) => updateFactorField(idx, 'is_inherent', v, true)"
                >
                  <el-option label="是" value="Y" />
                  <el-option label="否" value="N" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="影响层次" width="130">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-impact_layer`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="层次"
                  @update:model-value="(v: string) => updateFactorField(idx, 'impact_layer', v, true)"
                >
                  <el-option v-for="opt in IMPACT_LAYER_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="来源类型" width="160">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-source`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="选择来源"
                  @update:model-value="(v: string) => updateFactorField(idx, 'source', v, true)"
                >
                  <el-option v-for="opt in SOURCE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
                <!-- ref_chip placeholder for B22A/B23 -->
                <span
                  v-if="['B22A', 'B23'].includes(allResponses.get(`B50-T1-factor-${idx}-source`)?.conclusion || '')"
                  class="ref-chip"
                >
                  📎 {{ allResponses.get(`B50-T1-factor-${idx}-source`)?.conclusion }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="影响科目/认定" min-width="140">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-accounts`)?.remark || ''"
                  :disabled="isReadonly"
                  placeholder="科目/认定"
                  @update:model-value="(v: string) => updateFactorField(idx, 'accounts', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="初步风险" width="100">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-risk`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="等级"
                  @update:model-value="(v: string) => updateFactorField(idx, 'risk', v, true)"
                >
                  <el-option label="高" value="H" />
                  <el-option label="中" value="M" />
                  <el-option label="低" value="L" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="已转入矩阵" width="90" align="center">
              <template #default="{ row: idx }">
                <el-checkbox
                  :model-value="allResponses.get(`B50-T1-factor-${idx}-transferred`)?.conclusion === 'Y'"
                  :disabled="isReadonly"
                  @update:model-value="(v: boolean) => updateFactorField(idx, 'transferred', v ? 'Y' : '', true)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" align="center">
              <template #default="{ row: idx }">
                <el-button
                  v-if="!isReadonly"
                  type="primary"
                  size="small"
                  link
                  title="按影响层次转入报表层次风险(Tab2)/认定矩阵(Tab3)"
                  @click="transferFactor(idx)"
                >
                  分流
                </el-button>
                <el-button v-if="!isReadonly" type="danger" size="small" link @click="deleteFactorRow(idx)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
          <p class="tab1-hint">💡 填写"影响层次"与"影响科目/认定"后，点"分流"可自动转入报表层次风险(Tab2)或认定层次矩阵(Tab3)。舞弊类因素分流时自动标记为特别风险。</p>
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 2: 报表层面重大错报风险 ═══ -->
      <el-tab-pane :label="`${tabStatusIcon(tab2Status)} 报表层面重大错报风险`" name="tab2">
        <div class="tab-content">
          <div class="tab-header">
            <h3>报表层面重大错报风险</h3>
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addFsRiskRow">
              + 新增风险
            </el-button>
          </div>

          <el-table :data="Array.from({ length: tab2Count }, (_, i) => i)" border size="small">
            <el-table-column label="序号" width="60" align="center">
              <template #default="{ row: idx }">{{ idx + 1 }}</template>
            </el-table-column>
            <el-table-column label="风险描述" min-width="200">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-desc`)?.remark || ''"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="描述报表层面风险..."
                  @update:model-value="(v: string) => updateFsField(idx, 'desc', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="风险类别" width="130">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-category`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="选择类别"
                  @update:model-value="(v: string) => { updateFsField(idx, 'category', v, true); emitFsRiskChange() }"
                >
                  <el-option v-for="opt in CATEGORY_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="是否特别风险" width="110" align="center">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-special`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="是/否"
                  @update:model-value="(v: string) => updateFsField(idx, 'special', v, true)"
                >
                  <el-option label="是" value="Y" />
                  <el-option label="否" value="N" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="相关索引号" width="120">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-refindex`)?.remark || ''"
                  :disabled="isReadonly"
                  placeholder="如 B22C/B19"
                  @update:model-value="(v: string) => updateFsField(idx, 'refindex', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="风险等级" width="110">
              <template #default="{ row: idx }">
                <el-select
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-level`)?.conclusion || ''"
                  :disabled="isReadonly"
                  placeholder="等级"
                  @update:model-value="(v: string) => { updateFsField(idx, 'level', v, true); emitFsRiskChange() }"
                >
                  <el-option label="高" value="H">
                    <span :style="{ color: RISK_COLOR_MAP.H.text }">● 高</span>
                  </el-option>
                  <el-option label="中" value="M">
                    <span :style="{ color: RISK_COLOR_MAP.M.text }">● 中</span>
                  </el-option>
                  <el-option label="低" value="L">
                    <span :style="{ color: RISK_COLOR_MAP.L.text }">● 低</span>
                  </el-option>
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="被审计单位应对措施" min-width="160">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-entity_response`)?.remark || ''"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="被审计单位的控制/应对..."
                  @update:model-value="(v: string) => updateFsField(idx, 'entity_response', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="审计项目组应对措施" min-width="200">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-response`)?.remark || ''"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="总体应对策略（CAS 1231）..."
                  @update:model-value="(v: string) => updateFsField(idx, 'response', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="应对记录索引号" width="130">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-b60ref`)?.remark || 'B60'"
                  :disabled="isReadonly"
                  placeholder="如 B60"
                  @update:model-value="(v: string) => updateFsField(idx, 'b60ref', v)"
                />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ row: idx }">
                <el-button v-if="!isReadonly" type="danger" size="small" link @click="deleteFsRiskRow(idx)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 底部统计 -->
          <div class="fs-stats">
            <span :style="{ color: RISK_COLOR_MAP.H.text }">高 {{ tab2Stats.H }} 项</span>
            <span :style="{ color: RISK_COLOR_MAP.M.text }">中 {{ tab2Stats.M }} 项</span>
            <span :style="{ color: RISK_COLOR_MAP.L.text }">低 {{ tab2Stats.L }} 项</span>
            <span v-if="tab2Stats.H > 0" class="high-risk-warning">
              ⚠️ 存在高风险，请关注对 B60 总体策略的影响
            </span>
          </div>
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 3: 认定层面风险矩阵 ═══ -->
      <el-tab-pane :label="`${tabStatusIcon(tab3Status)} 认定层面风险矩阵`" name="tab3">
        <div class="tab-content">
          <div class="tab-header">
            <h3>认定层面风险矩阵</h3>
            <div class="matrix-toolbar">
              <!-- 筛选 -->
              <el-select
                :model-value="filterLevel || ''"
                placeholder="筛选等级"
                size="small"
                clearable
                style="width: 120px"
                @update:model-value="setFilter"
              >
                <el-option v-for="opt in FILTER_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <!-- 从试算表导入重要科目（确定审计范围）-->
              <el-button
                v-if="!isReadonly"
                size="small"
                type="success"
                plain
                :loading="importingScope"
                @click="handleImportScopeAccounts"
              >
                从试算表导入重要科目
              </el-button>
              <!-- 添加科目 -->
              <div v-if="!isReadonly" class="add-account-row">
                <el-input v-model="newAccountName" size="small" placeholder="新增科目名称" style="width: 160px" />
                <el-button size="small" type="primary" @click="handleAddAccount">添加</el-button>
              </div>
            </div>
          </div>

          <!-- 方法论上下文（源 B50-3 编制逻辑）-->
          <details class="b50-methodology">
            <summary>编制方法（源 B50-3：确定审计范围 → 认定层次风险评估 → 风险应对）</summary>
            <div class="b50-methodology-body">
              <p>1. <strong>确定审计范围</strong>：从试算表带入重要报表项目，标注类别（SCOT+ 关键流程 / 仅金额重大 / 其他）与是否涉及会计估计。</p>
              <p>2. <strong>认定层次风险评估</strong>：逐科目在存在/完整性/准确性/截止/分类/列报各认定评估固有风险(IR)、控制风险(CR) 与综合重大错报风险(RMM)；固有风险达最高级或收入确认/管理层凌驾按 CAS 推定为特别风险。</p>
              <p>3. <strong>风险应对</strong>：确定业务循环（路由 D~N 循环程序表）、对控制的拟信赖程度、"仅实质性程序是否足够"及应对方案（实质性 / 综合性）；综合性方案须在 C 类实施控制测试。</p>
            </div>
          </details>

          <!-- 统计面板 (Task 3.5/3.6) -->
          <div class="matrix-stats-bar">
            <span>科目: {{ matrixStats.totalAccounts }}</span>
            <span :style="{ color: RISK_COLOR_MAP.H.text }">高: {{ matrixStats.highCount }}</span>
            <span :style="{ color: RISK_COLOR_MAP.M.text }">中: {{ matrixStats.mediumCount }}</span>
            <span :style="{ color: RISK_COLOR_MAP.L.text }">低: {{ matrixStats.lowCount }}</span>
            <span style="color: #6B7280">未评: {{ matrixStats.nullCount }}</span>
          </div>

          <!-- CSS Grid 矩阵 (Task 3.5/3.6) -->
          <div class="risk-matrix-wrapper">
            <div class="risk-matrix-grid">
              <!-- 表头行 -->
              <div class="matrix-header-corner">科目 \ 认定</div>
              <div v-for="a in ASSERTIONS" :key="a" class="matrix-header-col">
                {{ ASSERTION_LABELS[a] }}
              </div>
              <div class="matrix-header-col matrix-actions-col">操作</div>

              <!-- 数据行 -->
              <template v-for="(row, rowIdx) in accounts" :key="row.name">
                <div class="matrix-row-header" :class="{ 'incomplete-row': incompleteAccounts.includes(row.name) }">
                  <div class="row-header-name">
                    {{ row.name }}
                    <span v-if="row.isPreset" class="preset-badge">预置</span>
                    <span v-if="incompleteAccounts.includes(row.name)" class="incomplete-badge">未完成</span>
                  </div>
                  <el-select
                    :model-value="row.cycle || ''"
                    :disabled="isReadonly || row.name === '管理层凌驾控制'"
                    placeholder="业务循环"
                    size="small"
                    class="row-cycle-select"
                    @update:model-value="(v: string) => handleSetCycle(row.name, v)"
                  >
                    <el-option v-for="opt in CYCLE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </div>
                <div
                  v-for="a in ASSERTIONS"
                  :key="`${row.name}-${a}`"
                  class="matrix-cell"
                  :class="{ 'cell-hidden': isCellHidden(row.name, a), 'cell-special': row.cells[a].isSpecialRisk }"
                  :style="getCellStyle(row.name, a)"
                  :title="getCellTooltip(row.name, a)"
                  @click="openCellPopover(row.name, a)"
                >
                  <span v-if="row.cells[a].isSpecialRisk" class="special-icon">⚠️</span>
                  <span class="cell-level" v-if="row.cells[a].combinedRisk">
                    {{ RISK_COLOR_MAP[row.cells[a].combinedRisk!].label }}
                  </span>
                  <span v-else class="cell-empty">-</span>
                </div>
                <div class="matrix-cell matrix-actions-cell">
                  <el-button
                    v-if="!isReadonly && !row.isPreset"
                    type="danger"
                    size="small"
                    link
                    @click="handleRemoveAccount(rowIdx)"
                  >
                    删除
                  </el-button>
                </div>
              </template>
            </div>
          </div>

          <!-- B15 重要性水平联动面板 (P3-8) -->
          <div class="materiality-linkage-panel" v-if="materialityInfo">
            <div class="mat-panel-header">
              <h4>B15 重要性水平（联动）</h4>
              <el-button size="small" link @click="loadMateriality">🔄 刷新</el-button>
            </div>
            <div class="mat-panel-cards">
              <div class="mat-card mat-card--pm">
                <span class="mat-label">整体重要性(PM)</span>
                <span class="mat-value">¥{{ materialityInfo.pm.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}</span>
              </div>
              <div class="mat-card">
                <span class="mat-label">实际执行重要性(TE)</span>
                <span class="mat-value">¥{{ materialityInfo.te.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}</span>
                <span class="mat-sub">({{ materialityInfo.perfRatio }}% × PM)</span>
              </div>
              <div class="mat-card">
                <span class="mat-label">明显微小错报(SAT)</span>
                <span class="mat-value">¥{{ materialityInfo.sat.toLocaleString('zh-CN', { maximumFractionDigits: 0 }) }}</span>
              </div>
            </div>
            <div class="mat-panel-hint">
              CAS: 风险等级越高 → 实际执行重要性(TE)比例应越低 → 测试范围越广。
              下方计划矩阵的"建议TE比例"列依据各科目最高综合风险自动推荐。
            </div>
          </div>
          <div class="materiality-linkage-panel materiality-linkage-panel--empty" v-else>
            <span>B15 重要性水平尚未设置，</span>
            <el-button type="primary" link size="small" @click="$router.push({ path: '/materiality', query: { project_id: props.projectId, year: props.year } })">
              前往设置 →
            </el-button>
          </div>

          <!-- 认定层次应对方案（对齐源模板 B50-3 风险应对列，驱动 B50→D~N/C 类） -->
          <div class="response-plan-section">
            <div class="plan-section-header">
              <h4>认定层次风险应对方案（计划矩阵）</h4>
              <el-popover v-model:visible="columnPopoverVisible" placement="bottom-end" :width="300" trigger="click">
                <template #reference>
                  <el-button size="small" plain>⚙ 列设置（{{ columnPrefs.visibleCount.value }}/{{ columnPrefs.totalCount }}）</el-button>
                </template>
                <div class="col-prefs">
                  <div class="col-prefs-presets">
                    <el-button
                      v-for="p in columnPrefs.B50_T3_COLUMN_PRESETS"
                      :key="p.key" size="small" plain
                      @click="columnPrefs.applyPreset(p.key)"
                    >{{ p.label }}</el-button>
                    <el-button size="small" link @click="columnPrefs.resetToDefault()">重置</el-button>
                  </div>
                  <div v-for="grp in columnPrefs.B50_T3_COLUMN_GROUPS" :key="grp.label" class="col-prefs-group">
                    <div class="col-prefs-grp-label">{{ grp.label }}</div>
                    <el-checkbox
                      v-for="c in grp.columns" :key="c.key"
                      :model-value="columnPrefs.isVisible(c.key)"
                      size="small"
                      @update:model-value="() => columnPrefs.toggleColumn(c.key)"
                    >{{ c.label }}</el-checkbox>
                  </div>
                </div>
              </el-popover>
            </div>
            <p class="plan-hint">每个科目须指定业务循环（路由到对应 D~N 循环程序表）、对控制的拟信赖程度与应对方案（实质性/综合性）。综合性方案须在 C 类实施控制测试。类别与最高综合风险自动建议应对方案。</p>
            <el-table :data="accounts" border size="small" class="plan-table">
              <el-table-column label="科目" min-width="140">
                <template #default="{ row }">
                  {{ row.name }}
                  <span v-if="row.isPreset" class="preset-badge">预置</span>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('balance')" label="余额/金额" width="150" align="right">
                <template #default="{ row }">
                  <el-input-number
                    :model-value="row.balance"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    placeholder="—"
                    style="width: 130px"
                    @update:model-value="(v: number | undefined) => handleSetScopeField(row.name, 'balance', v ?? null)"
                  />
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('category')" label="类别" width="140">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.category || ''"
                    :disabled="isReadonly"
                    placeholder="类别"
                    size="small"
                    @update:model-value="(v: string) => handleSetScopeField(row.name, 'category', v)"
                  >
                    <el-option v-for="opt in CATEGORY_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('estimate')" label="会计估计" width="90" align="center">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.isEstimate || ''"
                    :disabled="isReadonly"
                    placeholder="是/否"
                    size="small"
                    @update:model-value="(v: string) => handleSetScopeField(row.name, 'estimate', v)"
                  >
                    <el-option label="是" value="Y" />
                    <el-option label="否" value="N" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('cycle')" label="业务循环" width="200">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.cycle || ''"
                    :disabled="isReadonly || row.name === '管理层凌驾控制'"
                    placeholder="选择循环"
                    size="small"
                    @update:model-value="(v: string) => handleSetCycle(row.name, v)"
                  >
                    <el-option v-for="opt in CYCLE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="最高综合风险" width="110" align="center">
                <template #default="{ row }">
                  <span :style="{ color: rowMaxRiskColor(row) }">{{ rowMaxRiskLabel(row) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="含特别风险" width="90" align="center">
                <template #default="{ row }">
                  <span v-if="ASSERTIONS.some((a: Assertion) => row.cells[a].isSpecialRisk)" style="color:#DC2626">⚠️ 是</span>
                  <span v-else style="color:#9CA3AF">否</span>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('reliance')" label="对控制的拟信赖程度" width="150">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.plannedReliance || ''"
                    :disabled="isReadonly"
                    placeholder="选择"
                    size="small"
                    @update:model-value="(v: string) => handleSetPlanField(row.name, 'reliance', v)"
                  >
                    <el-option v-for="opt in CONTROL_RELIANCE_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('subonly')" label="仅实质性程序是否足够" width="140" align="center">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.substantiveOnlySufficient || ''"
                    :disabled="isReadonly"
                    placeholder="是/否"
                    size="small"
                    @update:model-value="(v: string) => handleSetPlanField(row.name, 'subonly', v)"
                  >
                    <el-option label="是" value="Y" />
                    <el-option label="否" value="N" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column v-if="columnPrefs.isVisible('approach')" label="应对方案" width="160">
                <template #default="{ row }">
                  <el-select
                    :model-value="row.approach || ''"
                    :disabled="isReadonly"
                    placeholder="选择方案"
                    size="small"
                    @update:model-value="(v: string) => handleSetPlanField(row.name, 'approach', v)"
                  >
                    <el-option v-for="opt in APPROACH_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                  </el-select>
                  <span v-if="row.approach === 'combined'" class="combined-hint" title="综合性方案须在 C 类实施控制测试">→C</span>
                  <span
                    v-if="suggestedApproach(row.name) && row.approach !== suggestedApproach(row.name)"
                    class="approach-suggest"
                    :title="`按类别与最高综合风险，建议：${APPROACH_LABEL[suggestedApproach(row.name)]}`"
                  >建议：{{ APPROACH_LABEL[suggestedApproach(row.name)] }}</span>
                </template>
              </el-table-column>
              <el-table-column label="建议TE比例" width="130" v-if="materialityInfo">
                <template #default="{ row }">
                  <span class="te-suggestion" :title="suggestedTeRatio(rowMaxRisk(row)).hint">
                    {{ suggestedTeRatio(rowMaxRisk(row)).ratio }}
                  </span>
                </template>
              </el-table-column>
              <el-table-column label="操作" width="90" align="center" fixed="right">
                <template #default="{ row }">
                  <el-button v-if="!isReadonly" type="primary" size="small" link @click="openGuideDialog(row)">
                    引导录入
                  </el-button>
                </template>
              </el-table-column>
            </el-table>
          </div>

          <!-- 引导式科目风险录入弹窗 -->
          <B50AccountRiskDialog
            v-model:visible="guideDialogVisible"
            :row="guideRow"
            :readonly="isReadonly"
            @apply="onGuideApply"
          />

          <!-- Popover 编辑面板 (Task 3.5) -->
          <el-dialog
            v-model="popoverVisible"
            :title="`编辑风险 — ${editingCell?.account} / ${editingCell ? ASSERTION_LABELS[editingCell.assertion] : ''}`"
            width="400px"
            append-to-body
          >
            <div class="cell-edit-form">
              <div class="edit-row">
                <label>固有风险 (IR):</label>
                <el-select v-model="editIR" placeholder="选择" clearable>
                  <el-option label="高" value="H"><span :style="{ color: RISK_COLOR_MAP.H.text }">● 高</span></el-option>
                  <el-option label="中" value="M"><span :style="{ color: RISK_COLOR_MAP.M.text }">● 中</span></el-option>
                  <el-option label="低" value="L"><span :style="{ color: RISK_COLOR_MAP.L.text }">● 低</span></el-option>
                </el-select>
              </div>
              <div class="edit-row">
                <label>控制风险 (CR):</label>
                <el-select v-model="editCR" placeholder="选择" clearable>
                  <el-option label="高" value="H"><span :style="{ color: RISK_COLOR_MAP.H.text }">● 高</span></el-option>
                  <el-option label="中" value="M"><span :style="{ color: RISK_COLOR_MAP.M.text }">● 中</span></el-option>
                  <el-option label="低" value="L"><span :style="{ color: RISK_COLOR_MAP.L.text }">● 低</span></el-option>
                </el-select>
              </div>
              <div class="edit-row">
                <label>综合风险 (RMM):</label>
                <el-select v-model="editRMM" placeholder="选择" clearable>
                  <el-option label="高" value="H"><span :style="{ color: RISK_COLOR_MAP.H.text }">● 高</span></el-option>
                  <el-option label="中" value="M"><span :style="{ color: RISK_COLOR_MAP.M.text }">● 中</span></el-option>
                  <el-option label="低" value="L"><span :style="{ color: RISK_COLOR_MAP.L.text }">● 低</span></el-option>
                </el-select>
              </div>
              <div class="edit-row" v-if="editingCell">
                <label>特别风险:</label>
                <el-checkbox
                  :model-value="accounts.find(a => a.name === editingCell!.account)?.cells[editingCell!.assertion].isSpecialRisk || false"
                  @change="handleToggleSpecialRisk(editingCell!.account, editingCell!.assertion)"
                >
                  标记为特别风险
                </el-checkbox>
              </div>
              <!-- CAS 舞弊推定提示 -->
              <div v-if="editingCell?.account === '收入确认' && isFraudPresumptionActive(editingCell.account, editingCell.assertion)" class="cas-warning">
                ⚠️ CAS 舞弊推定：收入确认固有风险默认为"高"。如需降级，请
                <el-button type="warning" size="small" link @click="showFraudRebuttalDialog(editingCell.account, editingCell.assertion)">
                  提交反驳
                </el-button>
              </div>
            </div>
            <template #footer>
              <el-button @click="cancelCellEdit">取消</el-button>
              <el-button type="primary" @click="saveCellEdit">确定</el-button>
            </template>
          </el-dialog>

          <!-- 右侧统计面板 (Task 3.6) -->
          <div class="matrix-side-stats">
            <h4>风险分布</h4>
            <div class="stats-section">
              <strong>按科目:</strong>
              <div v-for="row in accounts" :key="row.name" class="stats-row">
                <span class="stats-label">{{ row.name }}:</span>
                <span :style="{ color: RISK_COLOR_MAP.H.text }">H{{ ASSERTIONS.filter(a => row.cells[a].combinedRisk === 'H').length }}</span>
                <span :style="{ color: RISK_COLOR_MAP.M.text }">M{{ ASSERTIONS.filter(a => row.cells[a].combinedRisk === 'M').length }}</span>
                <span :style="{ color: RISK_COLOR_MAP.L.text }">L{{ ASSERTIONS.filter(a => row.cells[a].combinedRisk === 'L').length }}</span>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ═══ Tab 4: 特别风险汇总 ═══ -->
      <el-tab-pane :label="`${tabStatusIcon(tab4Status)} 特别风险汇总`" name="tab4">
        <div class="tab-content">
          <div class="tab-header">
            <h3>特别风险汇总</h3>
            <span class="tab-subtitle">自动汇总 Tab 3 中标记为特别风险的单元格</span>
          </div>

          <div v-if="specialRiskCells.length === 0" class="empty-state">
            暂无特别风险条目。请在"认定层面风险矩阵"中标记特别风险。
          </div>

          <div v-else class="special-risk-list">
            <div
              v-for="(sr, idx) in specialRiskCells"
              :key="`${sr.account}-${sr.assertion}`"
              class="special-risk-card"
            >
              <div class="sr-header">
                <span class="sr-index">{{ idx + 1 }}.</span>
                <span class="sr-account">{{ sr.account }}</span>
                <span class="sr-assertion">— {{ ASSERTION_LABELS[sr.assertion] }}</span>
                <span v-if="getSpecialRiskTag(sr.account)" class="sr-tag" :class="{ 'tag-cas': sr.account === '收入确认', 'tag-mandatory': sr.account === '管理层凌驾控制' }">
                  {{ getSpecialRiskTag(sr.account) }}
                </span>
              </div>
              <div class="sr-body">
                <div class="sr-field sr-field-inline">
                  <label>是否由舞弊导致:</label>
                  <el-select
                    :model-value="getSrConclusion(sr.account, sr.assertion, 'fraud') || (fraudPresumed(sr.account) ? 'Y' : '')"
                    :disabled="isReadonly"
                    placeholder="是/否"
                    size="small"
                    style="width: 120px"
                    @update:model-value="(v: string) => updateSrField(sr.account, sr.assertion, 'fraud', v, true)"
                  >
                    <el-option label="是（舞弊）" value="Y" />
                    <el-option label="否（非舞弊）" value="N" />
                  </el-select>
                  <span v-if="fraudPresumed(sr.account)" class="fraud-presume-hint">CAS 推定舞弊</span>
                </div>
                <div class="sr-field">
                  <label>管理层应对或控制措施:</label>
                  <el-input
                    :model-value="getSrRemark(sr.account, sr.assertion, 'mgmt_response')"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    placeholder="管理层针对该特别风险的控制或应对，及项目组对其的评价..."
                    @update:model-value="(v: string) => updateSrField(sr.account, sr.assertion, 'mgmt_response', v)"
                  />
                </div>
                <div class="sr-field">
                  <label>审计措施（应对程序）:</label>
                  <el-input
                    :model-value="getResponseText(sr.account, sr.assertion)"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                    placeholder="描述应对程序（须包含细节测试）..."
                    @update:model-value="(v: string) => updateResponseText(sr.account, sr.assertion, v)"
                  />
                  <span v-if="!getResponseText(sr.account, sr.assertion).trim()" class="validation-warning">
                    ⚠️ 待补充应对
                  </span>
                  <span v-else-if="isResponseInvalid(getResponseText(sr.account, sr.assertion))" class="validation-warning soft">
                    ⚠️ 应对程序不得仅含分析程序，须包含细节测试
                  </span>
                </div>
                <div class="sr-field sr-field-inline">
                  <label>底稿引用:</label>
                  <el-input
                    :model-value="getRefText(sr.account, sr.assertion)"
                    :disabled="isReadonly"
                    placeholder="如: D2A-步骤5, F3-步骤3"
                    style="width: 220px"
                    @update:model-value="(v: string) => updateRefText(sr.account, sr.assertion, v)"
                  />
                  <span v-if="getRefText(sr.account, sr.assertion)" class="ref-chip">
                    📎 {{ getRefText(sr.account, sr.assertion) }}
                  </span>
                </div>
                <div class="sr-field">
                  <label>向被审计单位报告的事项:</label>
                  <el-input
                    :model-value="getSrRemark(sr.account, sr.assertion, 'report_item')"
                    :disabled="isReadonly"
                    placeholder="如与治理层沟通事项，或 [无]"
                    @update:model-value="(v: string) => updateSrField(sr.account, sr.assertion, 'report_item', v)"
                  />
                </div>
              </div>
            </div>
          </div>
        </div>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══ 合伙人审批区 (Task 3.9) ═══ -->
    <div class="approval-section">
      <h3>合伙人审批</h3>
      <div v-if="!isApproved">
        <!-- 待完成事项 -->
        <div v-if="pendingItems.length > 0" class="pending-items">
          <p class="pending-title">⚠️ 以下事项需完成后方可签字：</p>
          <ul>
            <li v-for="item in pendingItems" :key="item">{{ item }}</li>
          </ul>
        </div>
        <el-button
          type="primary"
          :disabled="!canApprove || isReadonly"
          @click="handleApproval"
        >
          合伙人签字审批
        </el-button>
      </div>
      <div v-else class="approved-info">
        <span>✅ 已完成审批</span>
        <span v-if="approvalInfo">— {{ approvalInfo.signer }} / {{ approvalInfo.date }}</span>
      </div>
    </div>

    <!-- ═══ 舞弊推定反驳弹窗 (Task 3.8) ═══ -->
    <el-dialog v-model="fraudDialogVisible" title="收入确认舞弊推定反驳" width="500px" append-to-body>
      <div class="fraud-rebuttal-form">
        <p>根据 CAS 1211，收入确认相关认定的固有风险默认为"高"（舞弊推定）。</p>
        <p>如需降低风险等级，请填写充分的反驳理由并经合伙人签字确认：</p>
        <el-input
          v-model="fraudRebuttalReason"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 6 }"
          placeholder="填写反驳理由..."
        />
        <p class="rebuttal-note">提交后将视为合伙人已确认签字。</p>
      </div>
      <template #footer>
        <el-button @click="fraudDialogVisible = false">取消</el-button>
        <el-button type="warning" @click="submitFraudRebuttal">确认反驳</el-button>
      </template>
    </el-dialog>

    <!-- ═══ Amendment 弹窗 (Task 3.10) ═══ -->
    <el-dialog v-model="amendmentDialogVisible" title="修改风险评估（Amendment）" width="500px" append-to-body>
      <div class="amendment-form">
        <p>已审批的风险评估需重新修改时，请填写修改原因：</p>
        <el-input
          v-model="amendmentReason"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 5 }"
          placeholder="填写修改原因..."
        />
        <p class="amendment-note">提交后审批状态将重置，修改完成后需重新合伙人签字。</p>
      </div>
      <template #footer>
        <el-button @click="amendmentDialogVisible = false">取消</el-button>
        <el-button type="warning" @click="submitAmendment">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- Saving indicator -->
    <div v-if="saving" class="saving-indicator">保存中...</div>

    <!-- 版本历史抽屉 + 复核对话 Host（对齐 B60/B212 范式）-->
    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    <GtWpReviewDialogHost />
  </div>
</template>

<style scoped>
/* ═══ 基础布局 (Task 3.12) ═══ */
.gt-b50-risk-assessment {
  position: relative;
  padding: 16px;
  min-width: 768px;
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

/* ═══ 审批横幅 (Task 3.9/3.10) ═══ */
.approval-banner {
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
.b50-tabs {
  margin-bottom: 16px;
}

.tab-progress {
  position: absolute;
  top: 8px;
  right: 16px;
  font-size: 12px;
  color: #6B7280;
}

.b50-top-toolbar {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  align-items: center;
}

.b50-mode-toolbar {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

.oo-not-instantiated {
  padding: 32px 0;
  text-align: center;
}

.plan-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.col-prefs-presets {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 8px;
}

.col-prefs-group {
  margin-bottom: 8px;
}

.col-prefs-grp-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
}

.approach-suggest {
  display: inline-block;
  margin-left: 6px;
  font-size: 11px;
  color: var(--el-color-warning);
  cursor: help;
}

.tab-content {
  padding: 12px 0;
}

/* 表格统一 13px */
.gt-b50-risk-assessment :deep(.el-table) {
  font-size: 13px;
}

.b50-audit-objective {
  margin-bottom: 10px;
}

.b50-methodology {
  margin: 8px 0 12px;
  border-left: 3px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  border-radius: 4px;
  padding: 6px 10px;
}

.b50-methodology > summary {
  cursor: pointer;
  font-size: 13px;
  color: var(--el-color-warning-dark-2);
  font-weight: 500;
}

.b50-methodology-body {
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
}

.b50-methodology-body p {
  margin: 4px 0;
}

.tab-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.tab-header h3 {
  margin: 0;
  font-size: 16px;
}

.tab-subtitle {
  color: #6B7280;
  font-size: 12px;
  margin-left: 8px;
}

/* ═══ Tab 1/2 表格 ═══ */
.ref-chip {
  display: inline-block;
  background: #EFF6FF;
  border: 1px solid #93C5FD;
  border-radius: 4px;
  padding: 2px 6px;
  font-size: 11px;
  color: #2563EB;
  margin-top: 4px;
  cursor: pointer;
}

.fs-stats {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  align-items: center;
  font-weight: 600;
}

.high-risk-warning {
  color: #DC2626;
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
}

.tab1-hint {
  margin-top: 10px;
  font-size: 12px;
  color: #6B7280;
  line-height: 1.5;
  background: #F0F9FF;
  border-left: 3px solid #3B82F6;
  padding: 6px 10px;
  border-radius: 3px;
}

/* ═══ Tab 3 矩阵 (Task 3.5/3.6) ═══ */
.matrix-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}

.add-account-row {
  display: flex;
  gap: 6px;
}

.matrix-stats-bar {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  padding: 8px 12px;
  background: #F9FAFB;
  border-radius: 4px;
}

.risk-matrix-wrapper {
  overflow-x: auto;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}

.risk-matrix-grid {
  display: grid;
  grid-template-columns: 160px repeat(6, 1fr) 60px;
  min-width: 800px;
}

.matrix-header-corner {
  position: sticky;
  left: 0;
  top: 0;
  z-index: 3;
  background: #F3F4F6;
  padding: 10px 8px;
  font-weight: 700;
  font-size: 12px;
  border-bottom: 2px solid #D1D5DB;
  border-right: 1px solid #E5E7EB;
}

.matrix-header-col {
  position: sticky;
  top: 0;
  z-index: 2;
  background: #F3F4F6;
  padding: 10px 6px;
  text-align: center;
  font-weight: 600;
  font-size: 12px;
  border-bottom: 2px solid #D1D5DB;
  border-right: 1px solid #E5E7EB;
}

.matrix-actions-col {
  border-right: none;
}

.matrix-row-header {
  position: sticky;
  left: 0;
  z-index: 1;
  background: #FFFFFF;
  padding: 8px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  border-bottom: 1px solid #E5E7EB;
  border-right: 1px solid #E5E7EB;
  display: flex;
  align-items: center;
  gap: 4px;
}

.matrix-row-header.incomplete-row {
  background: #FEF3C7;
}

.row-header-name {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: wrap;
}

.row-cycle-select {
  width: 100%;
  margin-top: 4px;
}

.response-plan-section {
  margin-top: 20px;
  padding: 12px;
  background: #F9FAFB;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
}

.response-plan-section h4 {
  margin: 0 0 6px;
  font-size: 14px;
}

.plan-hint {
  margin: 0 0 10px;
  font-size: 12px;
  color: #6B7280;
  line-height: 1.5;
}

.plan-table {
  font-size: var(--wp-font-size, 13px);
}

.combined-hint {
  display: inline-block;
  margin-left: 4px;
  font-size: 10px;
  color: #1D4ED8;
  font-weight: 700;
}

/* ═══ B15 重要性联动面板 (P3-8) ═══ */
.materiality-linkage-panel {
  margin-top: 16px;
  margin-bottom: 12px;
  padding: 12px 16px;
  background: linear-gradient(135deg, #EDE9FE 0%, #F5F3FF 100%);
  border: 1px solid #C4B5FD;
  border-radius: 8px;
}
.materiality-linkage-panel--empty {
  background: #F9FAFB;
  border-color: #E5E7EB;
  font-size: 13px;
  color: #6B7280;
  display: flex;
  align-items: center;
  gap: 4px;
}
.mat-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.mat-panel-header h4 {
  margin: 0;
  font-size: 13px;
  color: #5B21B6;
}
.mat-panel-cards {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.mat-card {
  background: white;
  border-radius: 6px;
  padding: 8px 14px;
  min-width: 140px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.06);
  text-align: center;
}
.mat-card--pm {
  border-left: 3px solid #7C3AED;
}
.mat-label {
  display: block;
  font-size: 11px;
  color: #6B7280;
  margin-bottom: 2px;
}
.mat-value {
  display: block;
  font-size: 16px;
  font-weight: 700;
  color: #1F2937;
}
.mat-sub {
  display: block;
  font-size: 10px;
  color: #9CA3AF;
}
.mat-panel-hint {
  margin-top: 8px;
  font-size: 11px;
  color: #6B21A8;
  line-height: 1.5;
}
.te-suggestion {
  font-size: 12px;
  font-weight: 600;
  color: #5B21B6;
  cursor: help;
  border-bottom: 1px dashed #C4B5FD;
}

.preset-badge {
  background: #DBEAFE;
  color: #2563EB;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
}

.incomplete-badge {
  background: #FEE2E2;
  color: #DC2626;
  font-size: 10px;
  padding: 1px 4px;
  border-radius: 3px;
}

.matrix-cell {
  padding: 8px 4px;
  text-align: center;
  font-size: 12px;
  cursor: pointer;
  border-bottom: 1px solid #E5E7EB;
  border-right: 1px solid #E5E7EB;
  transition: opacity 0.2s;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 2px;
  min-height: 36px;
}

.matrix-cell:hover {
  opacity: 0.8;
  box-shadow: inset 0 0 0 2px #3B82F6;
}

.matrix-cell.cell-hidden {
  opacity: 0.2;
  pointer-events: none;
}

.matrix-cell.cell-special {
  /* red border handled via inline style */
}

.matrix-actions-cell {
  cursor: default;
  border-right: none;
}

.matrix-actions-cell:hover {
  box-shadow: none;
  opacity: 1;
}

.special-icon {
  font-size: 11px;
}

.cell-level {
  font-weight: 700;
  font-size: var(--wp-font-size, 13px);
}

.cell-empty {
  color: #9CA3AF;
}

/* ═══ 编辑面板 ═══ */
.cell-edit-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.edit-row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.edit-row label {
  width: 100px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.cas-warning {
  background: #FEF3C7;
  border: 1px solid #D97706;
  border-radius: 4px;
  padding: 8px;
  font-size: 12px;
  color: #92400E;
}

/* ═══ 统计面板 (Task 3.6) ═══ */
.matrix-side-stats {
  margin-top: 16px;
  padding: 12px;
  background: #F9FAFB;
  border-radius: 6px;
  border: 1px solid #E5E7EB;
}

.matrix-side-stats h4 {
  margin: 0 0 8px;
  font-size: 14px;
}

.stats-section {
  font-size: 12px;
}

.stats-row {
  display: flex;
  gap: 8px;
  padding: 2px 0;
}

.stats-label {
  min-width: 100px;
}

/* ═══ Tab 4 特别风险 ═══ */
.empty-state {
  text-align: center;
  padding: 40px;
  color: #6B7280;
}

.special-risk-list {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.special-risk-card {
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  padding: 12px;
}

.sr-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.sr-index {
  font-weight: 700;
  color: #374151;
}

.sr-account {
  font-weight: 600;
}

.sr-assertion {
  color: #6B7280;
}

.sr-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.tag-cas {
  background: #FEE2E2;
  color: #DC2626;
}

.tag-mandatory {
  background: #DBEAFE;
  color: #1D4ED8;
}

.sr-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.sr-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sr-field label {
  font-size: 12px;
  font-weight: 600;
  color: #374151;
}

.sr-field-inline {
  flex-direction: row;
  align-items: center;
  gap: 8px;
}

.fraud-presume-hint {
  font-size: 11px;
  color: #DC2626;
  background: #FEE2E2;
  padding: 1px 6px;
  border-radius: 3px;
  font-weight: 600;
}

.validation-warning {
  font-size: 11px;
  color: #DC2626;
  font-weight: 600;
}

.validation-warning.soft {
  color: #D97706;
}

/* ═══ 合伙人审批区 (Task 3.9) ═══ */
.approval-section {
  margin-top: 16px;
  padding: 16px;
  border: 1px solid #E5E7EB;
  border-radius: 6px;
  background: #FAFAFA;
}

.approval-section h3 {
  margin: 0 0 12px;
  font-size: 15px;
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

.approved-info {
  color: #059669;
  font-weight: 600;
}

/* ═══ 弹窗 ═══ */
.fraud-rebuttal-form,
.amendment-form {
  font-size: var(--wp-font-size, 13px);
}

.fraud-rebuttal-form p,
.amendment-form p {
  margin: 8px 0;
}

.rebuttal-note,
.amendment-note {
  font-size: 12px;
  color: #6B7280;
  font-style: italic;
}

/* ═══ 只读模式 (Task 3.10) ═══ */
.is-readonly .matrix-cell {
  cursor: default;
}

.is-readonly .matrix-cell:hover {
  box-shadow: none;
  opacity: 1;
}

/* ═══ 响应式布局 (Task 3.12) ═══ */
@media (min-width: 1024px) {
  .risk-matrix-wrapper {
    overflow-x: visible;
  }
}

@media (max-width: 1023px) and (min-width: 768px) {
  .risk-matrix-wrapper {
    overflow-x: auto;
  }
  .risk-matrix-grid {
    min-width: 900px;
  }
}

/* ═══ 打印样式 (Task 4.1) ═══ */
@media print {
  .gt-b50-risk-assessment {
    padding: 0;
  }

  /* 隐藏交互控件 */
  .matrix-toolbar,
  .add-account-row,
  .matrix-actions-col,
  .matrix-actions-cell,
  .approval-section,
  .saving-indicator,
  .tab-header .el-button,
  .sr-field .el-input,
  .el-checkbox,
  .el-select,
  .el-button {
    display: none !important;
  }

  /* A4 横版 */
  @page {
    size: A4 landscape;
    margin: 10mm;
  }

  /* 保持颜色 */
  .matrix-cell,
  .matrix-header-corner,
  .matrix-header-col,
  .matrix-row-header,
  .approval-banner,
  .sr-tag {
    -webkit-print-color-adjust: exact !important;
    print-color-adjust: exact !important;
    color-adjust: exact !important;
  }

  /* 矩阵满宽 */
  .risk-matrix-wrapper {
    overflow: visible;
    border: 1px solid #000;
  }

  .risk-matrix-grid {
    min-width: unset;
    width: 100%;
  }

  /* 统计保留 */
  .matrix-stats-bar {
    border: 1px solid #ccc;
    margin-bottom: 8px;
  }

  /* 隐藏筛选后的 opacity */
  .matrix-cell.cell-hidden {
    opacity: 1;
    pointer-events: auto;
  }
}
</style>
