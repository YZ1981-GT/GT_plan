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
import { ref, computed, watch, toRef, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useB50FormData, type ChecklistItem } from './composables/useB50FormData'
import { useB50RiskMatrix, RISK_COLOR_MAP, ASSERTIONS, type RiskLevel, type Assertion, type RiskLayer } from './composables/useB50RiskMatrix'
import { useB50Approval } from './composables/useB50Approval'
import { eventBus } from '@/utils/eventBus'

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
  removeAccount,
  setCellRisk,
  toggleSpecialRisk,
  matrixStats,
  incompleteAccounts,
  specialRiskCells,
  colorMap,
  isFraudPresumptionActive,
  filterLevel,
} = useB50RiskMatrix(tab3Data, saveImmediate)

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

// ─── Tab 状态 ────────────────────────────────────────────────────────────────

const activeTab = ref('tab3')

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
  { value: 'other', label: '其他' },
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
  for (let i = index; i < count - 1; i++) {
    for (const suffix of ['desc', 'source', 'accounts', 'assertions', 'risk', 'transferred']) {
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
  for (const suffix of ['desc', 'source', 'accounts', 'assertions', 'risk', 'transferred']) {
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
  for (let i = index; i < count - 1; i++) {
    for (const suffix of ['desc', 'category', 'level', 'response']) {
      const nextItem = allResponses.value.get(`B50-T2-fs-${i + 1}-${suffix}`)
      const currentId = `B50-T2-fs-${i}-${suffix}`
      if (nextItem) {
        allResponses.value.set(currentId, { ...nextItem, item_id: currentId })
      } else {
        allResponses.value.delete(currentId)
      }
    }
  }
  for (const suffix of ['desc', 'category', 'level', 'response']) {
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

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
})

// Watch isApproved → emit completed
watch(isApproved, (val) => {
  if (val) emit('completed')
})

// Watch saving → emit save on successful saves
watch(saving, (isSaving, wasSaving) => {
  if (wasSaving && !isSaving) {
    emit('save')
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

    <!-- Tab 容器 (Task 3.2) -->
    <el-tabs v-model="activeTab" type="border-card" class="b50-tabs">
      <template #default>
        <!-- 进度指示 -->
        <div class="tab-progress">完成进度: {{ overallProgress }}</div>
      </template>

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
            <el-table-column label="操作" width="60" align="center">
              <template #default="{ row: idx }">
                <el-button v-if="!isReadonly" type="danger" size="small" link @click="deleteFactorRow(idx)">
                  删除
                </el-button>
              </template>
            </el-table-column>
          </el-table>
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
            <el-table-column label="总体应对措施" min-width="200">
              <template #default="{ row: idx }">
                <el-input
                  :model-value="allResponses.get(`B50-T2-fs-${idx}-response`)?.remark || ''"
                  :disabled="isReadonly"
                  type="textarea"
                  :autosize="{ minRows: 1, maxRows: 3 }"
                  placeholder="应对措施..."
                  @update:model-value="(v: string) => updateFsField(idx, 'response', v)"
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
              <!-- 添加科目 -->
              <div v-if="!isReadonly" class="add-account-row">
                <el-input v-model="newAccountName" size="small" placeholder="新增科目名称" style="width: 160px" />
                <el-button size="small" type="primary" @click="handleAddAccount">添加</el-button>
              </div>
            </div>
          </div>

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
                  {{ row.name }}
                  <span v-if="row.isPreset" class="preset-badge">预置</span>
                  <span v-if="incompleteAccounts.includes(row.name)" class="incomplete-badge">未完成</span>
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
                <div class="sr-field">
                  <label>应对程序:</label>
                  <el-input
                    :model-value="getResponseText(sr.account, sr.assertion)"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 2, maxRows: 5 }"
                    placeholder="描述应对程序（须包含细节测试）..."
                    @update:model-value="(v: string) => updateResponseText(sr.account, sr.assertion, v)"
                  />
                  <!-- soft validation warning -->
                  <span v-if="!getResponseText(sr.account, sr.assertion).trim()" class="validation-warning">
                    ⚠️ 待补充应对
                  </span>
                  <span v-else-if="isResponseInvalid(getResponseText(sr.account, sr.assertion))" class="validation-warning soft">
                    ⚠️ 应对程序不得仅含分析程序，须包含细节测试
                  </span>
                </div>
                <div class="sr-field">
                  <label>底稿引用:</label>
                  <el-input
                    :model-value="getRefText(sr.account, sr.assertion)"
                    :disabled="isReadonly"
                    placeholder="如: D2A-步骤5, F3-步骤3"
                    @update:model-value="(v: string) => updateRefText(sr.account, sr.assertion, v)"
                  />
                  <span v-if="getRefText(sr.account, sr.assertion)" class="ref-chip">
                    📎 {{ getRefText(sr.account, sr.assertion) }}
                  </span>
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
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
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
  font-size: 13px;
  color: #6B7280;
}

.approved-info {
  color: #059669;
  font-weight: 600;
}

/* ═══ 弹窗 ═══ */
.fraud-rebuttal-form,
.amendment-form {
  font-size: 13px;
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
