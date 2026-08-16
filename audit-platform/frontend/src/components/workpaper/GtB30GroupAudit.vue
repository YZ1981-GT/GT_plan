<script setup lang="ts">
import WpAmountInput from './shared/WpAmountInput.vue'
/**
 * GtB30GroupAudit — B30 集团审计范围确定底稿
 * Spec: .kiro/specs/b30-group-audit/ | Tasks: 3.1~3.15, 4.1
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, watch, nextTick, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { useB30FormData } from './composables/useB30FormData'
import {
  useB30GroupAudit,
  CLASSIFICATION_COLORS, SCOPE_COLORS, HEATMAP_COLORS,
  COVERAGE_WARNING_THRESHOLD, COVERAGE_PROGRESS_THRESHOLDS,
  COVERAGE_WEIGHTS, MATERIALITY_ALLOCATION_COEFFICIENT,
  MATERIALITY_UPPER_BOUND, MATERIALITY_LOWER_BOUND,
  suggestClassification as suggestClassificationFn,
  suggestScopeType as suggestScopeTypeFn,
  suggestAllocatedMateriality as suggestAllocatedMaterialityFn,
  validateMaterialityBounds as validateMaterialityBoundsFn,
  getCoverageColorLevel,
  type ComponentClassification, type ScopeType, type ComponentType,
  type IndependenceConfirmation, type CompetenceAssessment, type ClassificationFilter,
  type ComponentEntity, type NewComponentInput, type MaterialityPayload,
  type TreeNode, type CoverageCell,
} from './composables/useB30GroupAudit'
import { useB30Review } from './composables/useB30Review'
import { createExcelJsWorkbook, loadExcelJsWorkbook } from '@/composables/useExcelIO'

// ─── Props / Emits ───────────────────────────────────────────────────────────

interface Props { wpId: string; projectId: string; wpCode: string; year: number; readonly?: boolean }
const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()

// ─── Composables ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly')

const { allResponses, loading, saving, loadAll, saveImmediate, saveDebouncedText, flushPendingSave } = useB30FormData(wpIdRef)
const {
  treeData, treeNodeCount, treeMaxDepth,
  addComponent, removeComponent, moveComponent, updateComponent,
  components, groupTotals, filteredComponents,
  setClassification, getClassification,
  groupMateriality, setAllocatedMateriality,
  setScopeType, getScopeType, allScopeDetermined,
  setAuditorInfo, getAuditorInfo, clearAuditorInfo,
  coverageMatrix, coverageTotals, coverageWarnings,
  dashboardStats, linkageInfo,
  publishScopeDetermined, onMaterialityDetermined,
} = useB30GroupAudit(allResponses, saveImmediate)
const { isReviewed, isReadonly, canReview, pendingItems, reviewInfo, doReview, startAmendment } = useB30Review(wpIdRef, allResponses, components, externalReadonly, saveImmediate)

// ─── 附件底稿 Lazy Components ─────────────────────────────────────────────────
const GtWpRendererLazy = defineAsyncComponent(() => import('./GtWpRenderer.vue'))

// ─── Local State ─────────────────────────────────────────────────────────────

const classificationFilter = ref<ClassificationFilter>('all')
const addNodeDialogVisible = ref(false)
const addNodeParentId = ref<string | null>(null)
const newNodeName = ref('')
const newNodeType = ref<ComponentType>('子公司')
const newNodeShareholding = ref<number | null>(null)

const overrideDialogVisible = ref(false)
const overrideTarget = ref<{ id: string; field: 'classification' | 'scopeType'; value: string }>({ id: '', field: 'classification', value: '' })
const overrideReason = ref('')

const amendmentDialogVisible = ref(false)
const amendmentReason = ref('')

const importConflictVisible = ref(false)
const importConflictStrategy = ref<'overwrite' | 'skip'>('overwrite')
const importFileInput = ref<HTMLInputElement | null>(null)
const pendingImportData = ref<any[]>([])

const treeRef = ref<any>(null)

// ─── 附件底稿 State ──────────────────────────────────────────────────────────
const attachmentWpIndex = ref<WpIndexItem[]>([])
const attachmentExpanded = ref(true)
const attachmentActive = ref('')

const B30_ATTACHMENT_CODES: { code: string; label: string }[] = [
  { code: 'B30-1-2-1', label: '集团特定审计程序' },
  { code: 'B30-2A', label: '组成部分财务数据A' },
  { code: 'B30-2B', label: '组成部分财务数据B' },
  { code: 'B30-8', label: '了解组成部分审计师' },
  { code: 'B30-12', label: '已识别错报汇总' },
  { code: 'B30-13-1', label: '财务报告文件包' },
  { code: 'B30-15', label: '组成部分预算与实际收费' },
]

const attachmentWpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of attachmentWpIndex.value) {
    if (item.wp_code && /^B30-(1-2-1|2A|2B|8|12|13-1|15)$/.test(item.wp_code)) {
      map[item.wp_code] = item.id
    }
  }
  return map
})

const attachmentTabs = computed(() =>
  B30_ATTACHMENT_CODES
    .filter(c => !!attachmentWpIdMap.value[c.code])
    .map(c => ({ id: c.code, label: c.label, wpId: attachmentWpIdMap.value[c.code] }))
)

// ─── Constants ───────────────────────────────────────────────────────────────

const COMPONENT_TYPE_OPTIONS: ComponentType[] = ['子公司', '分公司', '合营企业', '联营企业', '分部']
const CLASSIFICATION_OPTIONS: ComponentClassification[] = ['重要组成部分', '非重要组成部分', '不重要组成部分']
const SCOPE_OPTIONS: ScopeType[] = ['全面审计', '特定项目审计', '分析性程序', '不执行程序']
const INDEPENDENCE_OPTIONS: IndependenceConfirmation[] = ['已确认', '未确认', '不适用']
const COMPETENCE_OPTIONS: CompetenceAssessment[] = ['充分', '需补充', '不充分']
const FILTER_OPTIONS: { label: string; value: ClassificationFilter }[] = [
  { label: '全部', value: 'all' },
  { label: '仅重要', value: 'significant' },
  { label: '仅非重要', value: 'non-significant' },
  { label: '仅不重要', value: 'insignificant' },
]
const SCOPE_SHORT_LABELS: Record<ScopeType, string> = { '全面审计': '全面', '特定项目审计': '特定', '分析性程序': '分析', '不执行程序': '无' }
const INDICATOR_LABELS: Record<string, string> = { totalAssets: '总资产', revenue: '营业收入', profit: '利润' }

// ─── Computed ────────────────────────────────────────────────────────────────

const displayedComponents = computed(() => {
  if (classificationFilter.value === 'all') return components.value
  return filteredComponents(classificationFilter.value).value
})

const stats = computed(() => dashboardStats.value)
const link = computed(() => linkageInfo.value)

function getCoverageProgressColor(rate: number): string {
  if (rate >= COVERAGE_PROGRESS_THRESHOLDS.GREEN) return '#52c41a'
  if (rate >= COVERAGE_PROGRESS_THRESHOLDS.YELLOW) return '#faad14'
  return '#ff4d4f'
}

function formatAmount(val: number | null): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function formatPercent(val: number): string {
  return (val * 100).toFixed(2) + '%'
}

// ─── Tree Handlers ───────────────────────────────────────────────────────────

function handleAddNode(parentId: string | null) {
  if (isReadonly.value) return
  addNodeParentId.value = parentId
  newNodeName.value = ''
  newNodeType.value = '子公司'
  newNodeShareholding.value = null
  addNodeDialogVisible.value = true
}

function confirmAddNode() {
  if (!newNodeName.value.trim()) { ElMessage.warning('请输入名称'); return }
  const input: NewComponentInput = { name: newNodeName.value.trim(), type: newNodeType.value, shareholding: newNodeShareholding.value }
  addComponent(addNodeParentId.value, input)
  addNodeDialogVisible.value = false
  emit('save')
}

function handleRemoveNode(nodeId: string) {
  if (isReadonly.value) return
  const count = components.value.length
  const hasChildren = components.value.some(c => c.parentId === nodeId)
  if (hasChildren) { ElMessage.warning('请先删除或移动子节点'); return }
  ElMessageBox.confirm('确认删除该组成部分？', '确认').then(() => {
    removeComponent(nodeId)
    emit('save')
  }).catch(() => {})
}

function handleTreeDrop(draggingNode: any, dropNode: any, dropType: string) {
  if (isReadonly.value) return
  const dragId = draggingNode.data.id
  let newParentId: string | null = null
  if (dropType === 'inner') { newParentId = dropNode.data.id }
  else { newParentId = dropNode.data.parentId || null }
  // Find parentId from the tree if needed
  const parentComp = components.value.find(c => c.id === dropNode.data.id)
  if (dropType !== 'inner' && parentComp) { newParentId = parentComp.parentId }
  moveComponent(dragId, newParentId || '')
  emit('save')
}

function allowDrop(draggingNode: any, dropNode: any, type: string): boolean {
  if (isReadonly.value) return false
  // Max 5 levels
  if (type === 'inner') {
    let depth = 1
    let current = dropNode
    while (current.parent && current.parent.data && current.parent.data.id) { depth++; current = current.parent }
    return depth < 5
  }
  return true
}

// ─── Classification / Scope Handlers ─────────────────────────────────────────

function handleClassificationChange(comp: ComponentEntity, val: ComponentClassification) {
  if (isReadonly.value) return
  const suggested = comp.suggestedClassification
  if (suggested && val !== suggested) {
    overrideTarget.value = { id: comp.id, field: 'classification', value: val }
    overrideReason.value = ''
    overrideDialogVisible.value = true
  } else {
    setClassification(comp.id, val)
    emit('save')
  }
}

function handleScopeChange(comp: ComponentEntity, val: ScopeType) {
  if (isReadonly.value) return
  const suggested = suggestScopeTypeFn(comp.classification)
  if (suggested && val !== suggested) {
    overrideTarget.value = { id: comp.id, field: 'scopeType', value: val }
    overrideReason.value = ''
    overrideDialogVisible.value = true
  } else {
    setScopeType(comp.id, val)
    emit('save')
    checkPublishScope()
  }
}

function confirmOverride() {
  if (!overrideReason.value.trim()) { ElMessage.warning('需填写调整理由'); return }
  const { id, field, value } = overrideTarget.value
  if (field === 'classification') {
    setClassification(id, value as ComponentClassification, overrideReason.value.trim())
  } else {
    setScopeType(id, value as ScopeType, overrideReason.value.trim())
  }
  overrideDialogVisible.value = false
  emit('save')
  checkPublishScope()
}

function checkPublishScope() {
  nextTick(() => { if (allScopeDetermined.value) publishScopeDetermined() })
}

// ─── Materiality Handlers ────────────────────────────────────────────────────

function handleMaterialityInput(comp: ComponentEntity, val: number | null) {
  if (isReadonly.value || val == null) return
  setAllocatedMateriality(comp.id, val)
  emit('save')
}

// ─── Auditor Handlers ────────────────────────────────────────────────────────

function handleAuditorChange(comp: ComponentEntity, field: string, val: any) {
  if (isReadonly.value) return
  setAuditorInfo(comp.id, { [field]: val })
  emit('save')
}

// ─── Review Handlers ─────────────────────────────────────────────────────────

async function handleReview() {
  if (!canReview.value) return
  await doReview()
  emit('save')
  emit('completed')
}

function handleStartAmendment() {
  amendmentReason.value = ''
  amendmentDialogVisible.value = true
}

async function confirmAmendment() {
  if (!amendmentReason.value.trim()) { ElMessage.warning('修改原因不能为空'); return }
  try {
    await startAmendment(amendmentReason.value.trim())
    amendmentDialogVisible.value = false
    emit('save')
  } catch (e: any) { ElMessage.error(e.message || '操作失败') }
}

// ─── Import / Export ─────────────────────────────────────────────────────────

async function exportTemplate() {
  // 走 useExcelIO 单一入口（B5 批）。仍是 ExcelJS 引擎，建表逻辑逐行不变。
  const { wb, toBuffer } = await createExcelJsWorkbook()
  const ws1 = wb.addWorksheet('集团结构')
  ws1.addRow(['名称', '类型', '持股比例(%)', '父节点名称'])
  const ws2 = wb.addWorksheet('组成部分明细')
  ws2.addRow(['名称', '总资产', '营业收入', '利润', '分类', '审计范围', '分配重要性', '审计师', '独立性确认', '胜任能力评估'])
  const buf = await toBuffer()
  downloadBuffer(buf, 'B30_集团审计范围_模板.xlsx')
}

async function exportData() {
  const { wb, toBuffer } = await createExcelJsWorkbook()
  const ws1 = wb.addWorksheet('集团结构')
  ws1.addRow(['名称', '类型', '持股比例(%)', '父节点名称'])
  for (const comp of components.value) {
    const parentName = comp.parentId ? (components.value.find(c => c.id === comp.parentId)?.name || '') : ''
    ws1.addRow([comp.name, comp.type || '', comp.shareholding ?? '', parentName])
  }
  const ws2 = wb.addWorksheet('组成部分明细')
  ws2.addRow(['名称', '总资产', '营业收入', '利润', '分类', '审计范围', '分配重要性', '审计师', '独立性确认', '胜任能力评估'])
  for (const comp of components.value) {
    ws2.addRow([comp.name, comp.totalAssets || '', comp.revenue || '', comp.profit || '', comp.classification || '', comp.scopeType || '', comp.allocatedMateriality ?? '', comp.auditorName, comp.independence || '', comp.competence || ''])
  }
  const buf = await toBuffer()
  downloadBuffer(buf, `B30_集团审计范围_数据_${props.year}.xlsx`)
}

function downloadBuffer(buf: any, filename: string) {
  const blob = new Blob([buf], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

function triggerImport() { importFileInput.value?.click() }

async function handleImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const wb = await loadExcelJsWorkbook(file)
    const ws = wb.getWorksheet('组成部分明细')
    if (!ws) { ElMessage.error('格式不符：缺少"组成部分明细"工作表'); return }
    const rows: any[] = []
    ws.eachRow((row, idx) => { if (idx > 1) rows.push(row.values) })
    if (rows.length === 0) { ElMessage.warning('无数据可导入'); return }
    // Check conflicts
    const existingNames = new Set(components.value.map(c => c.name))
    const hasConflict = rows.some(r => existingNames.has(r[1]))
    if (hasConflict) {
      pendingImportData.value = rows
      importConflictVisible.value = true
    } else {
      doImport(rows, 'overwrite')
    }
  } catch { ElMessage.error('文件解析失败，请检查格式') }
  finally { if (importFileInput.value) importFileInput.value.value = '' }
}

function confirmImport() {
  doImport(pendingImportData.value, importConflictStrategy.value)
  importConflictVisible.value = false
}

function doImport(rows: any[], strategy: 'overwrite' | 'skip') {
  for (const row of rows) {
    const name = row[1]
    if (!name) continue
    const existing = components.value.find(c => c.name === name)
    if (existing && strategy === 'skip') continue
    if (!existing) {
      addComponent(null, { name, type: (row[2] as ComponentType) || '子公司', shareholding: null })
    }
    // Update financial data for last added or existing
    nextTick(() => {
      const target = components.value.find(c => c.name === name)
      if (!target) return
      if (row[2]) updateComponent(target.id, 'totalAssets', row[2] || null)
      if (row[3]) updateComponent(target.id, 'revenue', row[3] || null)
      if (row[4]) updateComponent(target.id, 'profit', row[4] || null)
    })
  }
  ElMessage.success('导入完成')
  emit('save')
}

// ─── Table Summary ───────────────────────────────────────────────────────────

function getTableSummary({ columns }: { columns: any[] }) {
  const totals = groupTotals.value
  const sums: string[] = columns.map((col: any, idx: number) => {
    if (idx === 0) return ''
    if (idx === 1) return '合计'
    switch (col.property) {
      case 'totalAssets': return formatAmount(totals.totalAssets)
      case 'revenue': return formatAmount(totals.revenue)
      case 'profit': return formatAmount(totals.profit)
      default: return ''
    }
  })
  return sums
}

// ─── Heatmap Helpers ─────────────────────────────────────────────────────────

function getHeatmapCell(compId: string, indicator: string): CoverageCell | null {
  return coverageMatrix.value.cells.get(`${compId}-${indicator}`) || null
}

function getHeatmapBg(cell: CoverageCell | null): string {
  if (!cell) return HEATMAP_COLORS.none
  return HEATMAP_COLORS[cell.colorLevel]
}

function getHeatmapTooltip(cell: CoverageCell | null): string {
  if (!cell) return ''
  return `${cell.componentName}\n${INDICATOR_LABELS[cell.indicator]}：${formatAmount(cell.amount)}\n占比：${formatPercent(cell.ratio)}\n范围：${cell.scopeType || '未确定'}\n加权贡献：${formatPercent(cell.contribution)}`
}

// ─── EventBus Integration ────────────────────────────────────────────────────

function handleMaterialityEvent(e: Event) {
  const detail = (e as CustomEvent<MaterialityPayload>).detail
  if (detail?.groupMateriality) onMaterialityDetermined(detail)
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  window.addEventListener('materiality:determined', handleMaterialityEvent)
  // Load attachment sub-workpaper index
  try {
    if (props.projectId) {
      attachmentWpIndex.value = await getWpIndex(props.projectId)
      if (attachmentTabs.value.length > 0 && !attachmentActive.value) {
        attachmentActive.value = attachmentTabs.value[0].id
      }
    }
  } catch { attachmentWpIndex.value = [] }
})

onBeforeUnmount(() => {
  flushPendingSave()
  window.removeEventListener('materiality:determined', handleMaterialityEvent)
})

// Watch allScopeDetermined to auto-publish
watch(allScopeDetermined, (val) => { if (val) publishScopeDetermined() })
</script>

<template>
  <div class="gt-b30-group-audit" :class="{ 'is-readonly': isReadonly }">
    <!-- 已复核横幅 -->
    <div v-if="isReviewed" class="reviewed-banner no-print">
      <el-tag type="success" size="large">✅ 已复核 — {{ reviewInfo?.reviewer }} {{ reviewInfo?.date }}</el-tag>
      <el-button v-if="!externalReadonly" size="small" @click="handleStartAmendment">修改(Amendment)</el-button>
    </div>

    <!-- Loading -->
    <div v-if="loading" class="loading-mask"><el-icon class="is-loading"><i class="el-icon-loading" /></el-icon> 加载中...</div>

    <!-- ═══════ Scope_Dashboard ═══════ -->
    <section class="scope-dashboard">
      <h3>范围仪表盘</h3>
      <div class="dashboard-grid">
        <!-- 分类分布 -->
        <div class="dashboard-card">
          <div class="card-title">分类分布</div>
          <div class="distribution-row">
            <span class="dist-item" :style="{ color: CLASSIFICATION_COLORS['重要组成部分'].color }">重要 {{ stats.classificationDistribution.significant }}</span>
            <span class="dist-item" :style="{ color: CLASSIFICATION_COLORS['非重要组成部分'].color }">非重要 {{ stats.classificationDistribution.nonSignificant }}</span>
            <span class="dist-item" :style="{ color: CLASSIFICATION_COLORS['不重要组成部分'].color }">不重要 {{ stats.classificationDistribution.insignificant }}</span>
            <span class="dist-item" style="color:#999">未分类 {{ stats.classificationDistribution.unclassified }}</span>
          </div>
        </div>
        <!-- 范围分布 -->
        <div class="dashboard-card">
          <div class="card-title">范围分布</div>
          <div class="distribution-row">
            <span class="dist-item" :style="{ color: SCOPE_COLORS['全面审计'].color }">全面 {{ stats.scopeDistribution.fullAudit }}</span>
            <span class="dist-item" :style="{ color: SCOPE_COLORS['特定项目审计'].color }">特定 {{ stats.scopeDistribution.specificItems }}</span>
            <span class="dist-item" :style="{ color: SCOPE_COLORS['分析性程序'].color }">分析 {{ stats.scopeDistribution.analyticalProcedures }}</span>
            <span class="dist-item" :style="{ color: SCOPE_COLORS['不执行程序'].color }">不执行 {{ stats.scopeDistribution.noWork }}</span>
            <span class="dist-item" style="color:#999">未确定 {{ stats.scopeDistribution.undetermined }}</span>
          </div>
        </div>
        <!-- 覆盖率进度条 -->
        <div class="dashboard-card">
          <div class="card-title">覆盖率</div>
          <div class="coverage-bars">
            <div class="bar-row"><span class="bar-label">总资产</span><el-progress :percentage="Math.round(stats.coverageTotals.totalAssets * 100)" :color="getCoverageProgressColor(stats.coverageTotals.totalAssets)" :stroke-width="14" /></div>
            <div class="bar-row"><span class="bar-label">营业收入</span><el-progress :percentage="Math.round(stats.coverageTotals.revenue * 100)" :color="getCoverageProgressColor(stats.coverageTotals.revenue)" :stroke-width="14" /></div>
            <div class="bar-row"><span class="bar-label">利润</span><el-progress :percentage="Math.round(stats.coverageTotals.profit * 100)" :color="getCoverageProgressColor(stats.coverageTotals.profit)" :stroke-width="14" /></div>
          </div>
        </div>
        <!-- 待确认 + 重要性 -->
        <div class="dashboard-card">
          <div class="card-title">状态概览</div>
          <div class="status-items">
            <div>组成部分：{{ stats.componentCount }} 个 | 层级：{{ stats.treeMaxDepth }}</div>
            <div>待确认事项：<span :class="{ 'text-danger': stats.pendingCount > 0 }">{{ stats.pendingCount }}</span></div>
            <div>集团重要性：<strong>{{ stats.groupMateriality ? formatAmount(stats.groupMateriality) + ' 元' : '待定' }}</strong></div>
            <div>已分配重要性：{{ stats.allocatedCount }} 个组成部分</div>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════ Group_Structure_Tree ═══════ -->
    <section class="group-structure-section">
      <div class="section-header">
        <h3>集团结构树</h3>
        <el-button v-if="!isReadonly" size="small" type="primary" class="no-print" @click="handleAddNode(null)">+ 新增组成部分</el-button>
      </div>
      <el-tree
        ref="treeRef"
        :data="treeData"
        node-key="id"
        default-expand-all
        :draggable="!isReadonly"
        :allow-drop="allowDrop"
        @node-drop="handleTreeDrop"
        class="b30-tree"
      >
        <template #default="{ node, data }">
          <div class="tree-node-content" :style="{ borderLeft: data.classification ? `4px solid ${CLASSIFICATION_COLORS[data.classification as ComponentClassification]?.color || '#ddd'}` : '4px solid #ddd' }">
            <span class="node-label">{{ data.label }}</span>
            <el-tag v-if="data.scopeType" size="small" :color="SCOPE_COLORS[data.scopeType as ScopeType]?.bg" :style="{ color: SCOPE_COLORS[data.scopeType as ScopeType]?.color, borderColor: SCOPE_COLORS[data.scopeType as ScopeType]?.color }">
              {{ SCOPE_SHORT_LABELS[data.scopeType as ScopeType] }}
            </el-tag>
            <span class="tree-actions no-print" v-if="!isReadonly">
              <el-button link size="small" @click.stop="handleAddNode(data.id)">+</el-button>
              <el-button link size="small" type="danger" @click.stop="handleRemoveNode(data.id)">×</el-button>
            </span>
          </div>
        </template>
      </el-tree>
    </section>

    <!-- ═══════ Component Detail Table ═══════ -->
    <section class="component-table-section">
      <div class="section-header">
        <h3>组成部分明细表</h3>
        <div class="table-filter no-print">
          <el-radio-group v-model="classificationFilter" size="small">
            <el-radio-button v-for="opt in FILTER_OPTIONS" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio-button>
          </el-radio-group>
        </div>
      </div>
      <div class="table-wrapper">
        <el-table :data="displayedComponents" border stripe size="small" show-summary :summary-method="getTableSummary">
          <el-table-column type="index" label="#" width="45" />
          <el-table-column prop="name" label="名称" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="(v: string) => { updateComponent(row.id, 'name', v); emit('save') }" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="type" label="类型" width="100">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" :model-value="row.type" size="small" placeholder="选择" @change="(v: ComponentType) => { updateComponent(row.id, 'type', v); emit('save') }">
                <el-option v-for="t in COMPONENT_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
              </el-select>
              <span v-else>{{ row.type || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="shareholding" label="持股%" width="80">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.shareholding" size="small" :min="0" :max="100" :controls="false" @change="(v: number|null) => { updateComponent(row.id, 'shareholding', v); emit('save') }" />
              <span v-else>{{ row.shareholding != null ? row.shareholding + '%' : '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="totalAssets" label="总资产" width="120">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.totalAssets" size="small" :controls="false" @change="(v: number|null) => { updateComponent(row.id, 'totalAssets', v); emit('save') }" />
              <span v-else>{{ formatAmount(row.totalAssets) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="revenue" label="营业收入" width="120">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.revenue" size="small" @change="(v: number|null) => { updateComponent(row.id, 'revenue', v); emit('save') }" />
              <span v-else>{{ formatAmount(row.revenue) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="profit" label="利润" width="120">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.profit" size="small" :controls="false" @change="(v: number|null) => { updateComponent(row.id, 'profit', v); emit('save') }" />
              <span v-else>{{ formatAmount(row.profit) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="资产占比" width="80"><template #default="{ row }">{{ formatPercent(row.assetRatio) }}</template></el-table-column>
          <el-table-column label="营收占比" width="80"><template #default="{ row }">{{ formatPercent(row.revenueRatio) }}</template></el-table-column>
          <el-table-column label="利润占比" width="80"><template #default="{ row }">{{ formatPercent(row.profitRatio) }}</template></el-table-column>
          <el-table-column prop="classification" label="分类" width="140">
            <template #default="{ row }">
              <div class="classification-cell">
                <el-select v-if="!isReadonly" :model-value="row.classification" size="small" placeholder="选择分类" @change="(v: ComponentClassification) => handleClassificationChange(row, v)">
                  <el-option v-for="c in CLASSIFICATION_OPTIONS" :key="c" :label="c" :value="c" />
                </el-select>
                <span v-else-if="row.classification">
                  <el-tag size="small" :color="CLASSIFICATION_COLORS[row.classification as ComponentClassification]?.bg" :style="{ color: CLASSIFICATION_COLORS[row.classification as ComponentClassification]?.color }">{{ CLASSIFICATION_COLORS[row.classification as ComponentClassification]?.label }}</el-tag>
                </span>
                <span v-else>-</span>
                <span v-if="row.classificationOverridden" class="override-badge" title="已手动调整">⚡</span>
                <div v-if="row.suggestedClassification && !row.classification" class="suggestion-hint">建议：{{ row.suggestedClassification }}</div>
              </div>
            </template>
          </el-table-column>
          <el-table-column prop="remark" label="备注" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="(v: string) => { updateComponent(row.id, 'remark', v); emit('save') }" />
              <span v-else>{{ row.remark || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- ═══════ Materiality Allocation ═══════ -->
    <section class="materiality-section">
      <h3>重要性分配</h3>
      <div class="materiality-header">
        <span>集团重要性：<strong>{{ groupMateriality ? formatAmount(groupMateriality) + ' 元' : '' }}</strong></span>
        <span v-if="!groupMateriality" class="b15-incomplete">B15 未完成，集团重要性待定</span>
      </div>
      <div class="materiality-list">
        <div v-for="comp in components" :key="comp.id" class="materiality-row">
          <span class="mat-name">{{ comp.name }}</span>
          <template v-if="comp.classification === '重要组成部分'">
            <el-input-number
              v-if="!isReadonly && groupMateriality"
              :model-value="comp.allocatedMateriality"
              size="small"
              :controls="false"
              placeholder="分配重要性"
              @change="(v: number|null) => handleMaterialityInput(comp, v)"
            />
            <span v-else-if="comp.allocatedMateriality != null">{{ formatAmount(comp.allocatedMateriality) }} 元</span>
            <span v-else class="suggestion-hint">建议：{{ comp.suggestedMateriality ? formatAmount(comp.suggestedMateriality) + ' 元' : '-' }}</span>
            <span v-if="comp.materialityWarning" class="mat-warning">⚠ {{ comp.materialityWarning }}</span>
          </template>
          <span v-else class="mat-na">不分配</span>
        </div>
      </div>
    </section>

    <!-- ═══════ Scope Determination ═══════ -->
    <section class="scope-section">
      <h3>审计范围确定</h3>
      <div class="scope-list">
        <div v-for="comp in components" :key="comp.id" class="scope-row">
          <span class="scope-name">{{ comp.name }}</span>
          <el-select v-if="!isReadonly" :model-value="comp.scopeType" size="small" placeholder="选择范围" @change="(v: ScopeType) => handleScopeChange(comp, v)">
            <el-option v-for="s in SCOPE_OPTIONS" :key="s" :label="s" :value="s" />
          </el-select>
          <span v-else>
            <el-tag v-if="comp.scopeType" size="small" :color="SCOPE_COLORS[comp.scopeType]?.bg" :style="{ color: SCOPE_COLORS[comp.scopeType]?.color }">{{ comp.scopeType }}</el-tag>
            <span v-else>-</span>
          </span>
          <span v-if="comp.suggestedScopeType && !comp.scopeType" class="suggestion-hint">建议：{{ comp.suggestedScopeType }}</span>
          <span v-if="comp.scopeOverridden" class="override-badge" title="已手动调整">⚡</span>
          <span v-if="comp.classification === '重要组成部分' && comp.scopeType && comp.scopeType !== '全面审计'" class="scope-warning">⚠ 重要组成部分通常应执行全面审计</span>
          <!-- 特定项目说明 -->
          <div v-if="comp.scopeType === '特定项目审计'" class="scope-desc-area">
            <el-input
              v-if="!isReadonly"
              type="textarea"
              :model-value="comp.scopeDescription"
              placeholder="请填写特定项目说明"
              :rows="2"
              @change="(v: string) => { updateComponent(comp.id, 'scopeDescription', v); emit('save') }"
            />
            <span v-else>{{ comp.scopeDescription || '-' }}</span>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══════ Component Auditors ═══════ -->
    <section class="auditor-section">
      <h3>组成部分审计师</h3>
      <div class="auditor-list">
        <div v-for="comp in components" :key="comp.id" class="auditor-row">
          <span class="auditor-name-label">{{ comp.name }}</span>
          <template v-if="comp.scopeType && comp.scopeType !== '不执行程序'">
            <el-input v-if="!isReadonly" v-model="comp.auditorName" size="small" placeholder="审计师/事务所" @change="(v: string) => handleAuditorChange(comp, 'name', v)" />
            <span v-else>{{ comp.auditorName || '-' }}</span>
            <el-select v-if="!isReadonly" :model-value="comp.independence" size="small" placeholder="独立性" @change="(v: IndependenceConfirmation) => handleAuditorChange(comp, 'independence', v)">
              <el-option v-for="o in INDEPENDENCE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ comp.independence || '-' }}</span>
            <el-select v-if="!isReadonly" :model-value="comp.competence" size="small" placeholder="胜任能力" @change="(v: CompetenceAssessment) => handleAuditorChange(comp, 'competence', v)">
              <el-option v-for="o in COMPETENCE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ comp.competence || '-' }}</span>
            <span v-if="comp.independence === '未确认'" class="auditor-warning">🔴 独立性未确认</span>
            <span v-if="comp.competence === '不充分'" class="auditor-warning">🔴 胜任能力不充分，需采取额外措施或变更组成部分审计师</span>
          </template>
          <span v-else-if="comp.scopeType === '不执行程序'" class="mat-na">无需指派</span>
          <span v-else class="mat-na">待确定范围</span>
        </div>
      </div>
    </section>

    <!-- ═══════ Coverage Heatmap ═══════ -->
    <section class="heatmap-section">
      <h3>覆盖率热力图</h3>
      <div class="heatmap-warnings" v-if="coverageWarnings.length > 0">
        <div v-for="w in coverageWarnings" :key="w.indicator" class="heatmap-warning-item">
          🔴 {{ w.indicatorLabel }}覆盖率 {{ formatPercent(w.coverageRate) }} — {{ w.message }}
        </div>
      </div>
      <div class="heatmap-table-wrapper">
        <table class="heatmap-table">
          <thead>
            <tr><th>组成部分</th><th>总资产</th><th>营业收入</th><th>利润</th></tr>
          </thead>
          <tbody>
            <tr v-for="comp in components" :key="comp.id">
              <td>{{ comp.name }}</td>
              <td v-for="ind in (['totalAssets', 'revenue', 'profit'] as const)" :key="ind"
                :style="{ backgroundColor: getHeatmapBg(getHeatmapCell(comp.id, ind)) }"
                :title="getHeatmapTooltip(getHeatmapCell(comp.id, ind))"
                class="heatmap-cell">
                {{ getHeatmapCell(comp.id, ind) ? formatPercent(getHeatmapCell(comp.id, ind)!.contribution) : '-' }}
              </td>
            </tr>
          </tbody>
          <tfoot>
            <tr class="heatmap-totals">
              <td><strong>合计覆盖率</strong></td>
              <td :class="{ 'text-danger': coverageTotals.totalAssets < COVERAGE_WARNING_THRESHOLD }">{{ formatPercent(coverageTotals.totalAssets) }}</td>
              <td :class="{ 'text-danger': coverageTotals.revenue < COVERAGE_WARNING_THRESHOLD }">{{ formatPercent(coverageTotals.revenue) }}</td>
              <td :class="{ 'text-danger': coverageTotals.profit < COVERAGE_WARNING_THRESHOLD }">{{ formatPercent(coverageTotals.profit) }}</td>
            </tr>
          </tfoot>
        </table>
      </div>
    </section>

    <!-- ═══════ Linkage Panel ═══════ -->
    <section class="linkage-section">
      <h3>联动面板</h3>
      <div class="linkage-grid">
        <div class="linkage-item">
          <span class="linkage-label">B15 重要性：</span>
          <el-tag :type="link.b15Status === 'completed' ? 'success' : 'warning'" size="small">{{ link.b15Status === 'completed' ? '已完成' : '未完成' }}</el-tag>
          <span v-if="link.b15Materiality"> {{ formatAmount(link.b15Materiality) }} 元</span>
        </div>
        <div class="linkage-item">
          <span class="linkage-label">B50 风险评估：</span>
          <el-tag :type="link.b50Status === 'received' ? 'success' : 'info'" size="small">{{ link.b50Status === 'received' ? '已接收' : '未接收' }}</el-tag>
        </div>
        <div class="linkage-item">
          <span class="linkage-label">审计链路：</span>
          <span class="chain-summary">B15(重要性) → <strong>B30(范围)</strong> → B50(风险)</span>
        </div>
        <div class="linkage-item" v-if="link.significantComponents.length > 0">
          <span class="linkage-label">重要组成部分：</span>
          <el-tag v-for="sc in link.significantComponents" :key="sc.id" size="small" class="ref-chip">{{ sc.name }}({{ SCOPE_SHORT_LABELS[sc.scopeType] }})</el-tag>
        </div>
      </div>
    </section>

    <!-- ═══════ Manager Review ═══════ -->
    <section class="review-section">
      <h3>现场经理复核</h3>
      <div v-if="!isReviewed">
        <div v-if="pendingItems.length > 0" class="pending-list">
          <div class="pending-title">待完成事项（{{ pendingItems.length }}）：</div>
          <ul><li v-for="(item, idx) in pendingItems" :key="idx">{{ item }}</li></ul>
        </div>
        <el-button type="primary" :disabled="!canReview || isReadonly" class="no-print" @click="handleReview">
          {{ canReview ? '签字确认' : '前置条件未满足' }}
        </el-button>
      </div>
    </section>

    <!-- ═══════ Toolbar (Import/Export) ═══════ -->
    <section class="toolbar-section no-print">
      <el-button size="small" @click="exportTemplate">导出模板</el-button>
      <el-button size="small" @click="exportData">导出数据</el-button>
      <el-button size="small" @click="triggerImport" :disabled="isReadonly">导入</el-button>
      <input ref="importFileInput" type="file" accept=".xlsx,.xls" style="display:none" @change="handleImportFile" />
    </section>

    <!-- ═══════ Dialogs ═══════ -->
    <!-- Add Node Dialog -->
    <el-dialog v-model="addNodeDialogVisible" title="新增组成部分" width="420px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="名称"><el-input v-model="newNodeName" placeholder="组成部分名称" /></el-form-item>
        <el-form-item label="类型">
          <el-select v-model="newNodeType">
            <el-option v-for="t in COMPONENT_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
          </el-select>
        </el-form-item>
        <el-form-item label="持股比例"><el-input-number v-model="newNodeShareholding" :min="0" :max="100" :controls="false" placeholder="%" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="addNodeDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAddNode">确认添加</el-button>
      </template>
    </el-dialog>

    <!-- Override Reason Dialog -->
    <el-dialog v-model="overrideDialogVisible" title="调整理由" width="400px" append-to-body>
      <p>您正在手动覆盖{{ overrideTarget.field === 'classification' ? '分类' : '审计范围' }}建议，请填写调整理由：</p>
      <el-input v-model="overrideReason" type="textarea" :rows="3" placeholder="请输入调整理由" />
      <template #footer>
        <el-button @click="overrideDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOverride">确认</el-button>
      </template>
    </el-dialog>

    <!-- Amendment Dialog -->
    <el-dialog v-model="amendmentDialogVisible" title="修改(Amendment)" width="400px" append-to-body>
      <p>请填写修改原因以解锁编辑：</p>
      <el-input v-model="amendmentReason" type="textarea" :rows="3" placeholder="修改原因" />
      <template #footer>
        <el-button @click="amendmentDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmAmendment">确认修改</el-button>
      </template>
    </el-dialog>

    <!-- Import Conflict Dialog -->
    <el-dialog v-model="importConflictVisible" title="导入冲突" width="400px" append-to-body>
      <p>检测到同名组成部分已存在，请选择处理策略：</p>
      <el-radio-group v-model="importConflictStrategy">
        <el-radio value="overwrite">覆盖</el-radio>
        <el-radio value="skip">跳过</el-radio>
      </el-radio-group>
      <template #footer>
        <el-button @click="importConflictVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmImport">确认导入</el-button>
      </template>
    </el-dialog>

    <!-- ═══════ 附件底稿 Tab 区域 ═══════ -->
    <section v-if="attachmentTabs.length > 0" class="b30-attachment-section">
      <div class="attachment-header" @click="attachmentExpanded = !attachmentExpanded">
        <span>📎 附件底稿（{{ attachmentTabs.length }}）</span>
        <span>{{ attachmentExpanded ? '−' : '+' }}</span>
      </div>
      <div v-show="attachmentExpanded">
        <el-tabs v-model="attachmentActive" type="border-card">
          <el-tab-pane v-for="t in attachmentTabs" :key="t.id" :label="t.label" :name="t.id" lazy>
            <GtWpRendererLazy :wp-id="t.wpId" :readonly="isReadonly" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </section>
  </div>
</template>

<style scoped lang="scss">
.gt-b30-group-audit {
  padding: 16px;
  font-size: 14px;

  &.is-readonly {
    .el-input, .el-select, .el-input-number { pointer-events: none; opacity: 0.75; }
  }

  h3 { margin: 0 0 12px; font-size: 16px; font-weight: 600; }

  section { margin-bottom: 24px; padding: 16px; background: #fff; border-radius: 6px; border: 1px solid #ebeef5; }

  .section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }

  // ─── Reviewed Banner ───
  .reviewed-banner { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; padding: 12px; background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 6px; }

  .loading-mask { text-align: center; padding: 40px; color: #999; }

  // ─── Scope Dashboard ───
  .scope-dashboard {
    .dashboard-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; }
    .dashboard-card { padding: 12px; border: 1px solid #f0f0f0; border-radius: 4px; background: #fafafa; }
    .card-title { font-weight: 500; margin-bottom: 8px; color: #333; }
    .distribution-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .dist-item { font-weight: 500; font-size: var(--wp-font-size, 13px); }
    .coverage-bars { display: flex; flex-direction: column; gap: 6px; }
    .bar-row { display: flex; align-items: center; gap: 8px; }
    .bar-label { width: 60px; font-size: 12px; color: #666; flex-shrink: 0; }
    .status-items { display: flex; flex-direction: column; gap: 4px; font-size: var(--wp-font-size, 13px); }
  }

  // ─── Tree ───
  .group-structure-section {
    .b30-tree { border: 1px solid #ebeef5; border-radius: 4px; padding: 8px; }
    .tree-node-content {
      display: flex; align-items: center; gap: 8px; padding: 4px 8px; width: 100%;
      .node-label { flex: 1; }
      .tree-actions { opacity: 0; transition: opacity 0.2s; }
      &:hover .tree-actions { opacity: 1; }
    }
  }

  // ─── Table ───
  .component-table-section {
    .table-wrapper { overflow-x: auto; }
    .table-filter { display: flex; gap: 8px; }
    .classification-cell { display: flex; align-items: center; gap: 4px; flex-wrap: wrap; }
    .override-badge { color: #faad14; font-size: 12px; cursor: help; }
    .suggestion-hint { font-size: 11px; color: #999; font-style: italic; }
  }

  // ─── Materiality ───
  .materiality-section {
    .materiality-header { margin-bottom: 12px; font-size: 14px; }
    .b15-incomplete { color: #999; font-style: italic; }
    .materiality-list { display: flex; flex-direction: column; gap: 8px; }
    .materiality-row { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f5f5f5; }
    .mat-name { width: 140px; font-weight: 500; flex-shrink: 0; }
    .mat-warning { color: #faad14; font-size: 12px; }
    .mat-na { color: #999; font-size: 12px; }
  }

  // ─── Scope ───
  .scope-section {
    .scope-list { display: flex; flex-direction: column; gap: 8px; }
    .scope-row { display: flex; align-items: flex-start; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f5f5f5; flex-wrap: wrap; }
    .scope-name { width: 140px; font-weight: 500; flex-shrink: 0; padding-top: 4px; }
    .scope-warning { color: #fa8c16; font-size: 12px; }
    .scope-desc-area { width: 100%; margin-top: 4px; padding-left: 152px; }
  }

  // ─── Auditors ───
  .auditor-section {
    .auditor-list { display: flex; flex-direction: column; gap: 8px; }
    .auditor-row { display: flex; align-items: center; gap: 12px; padding: 6px 0; border-bottom: 1px solid #f5f5f5; flex-wrap: wrap; }
    .auditor-name-label { width: 140px; font-weight: 500; flex-shrink: 0; }
    .auditor-warning { color: #ff4d4f; font-size: 12px; font-weight: 500; }
  }

  // ─── Heatmap ───
  .heatmap-section {
    .heatmap-warnings { margin-bottom: 12px; }
    .heatmap-warning-item { color: #ff4d4f; font-size: var(--wp-font-size, 13px); margin-bottom: 4px; }
    .heatmap-table-wrapper { overflow-x: auto; }
    .heatmap-table {
      width: 100%; border-collapse: collapse; font-size: var(--wp-font-size, 13px);
      th, td { border: 1px solid #e8e8e8; padding: 8px 12px; text-align: center; }
      th { background: #fafafa; font-weight: 500; }
      .heatmap-cell { min-width: 80px; transition: background-color 0.2s; }
      .heatmap-totals td { font-weight: 600; background: #fafafa; }
    }
  }

  // ─── Linkage ───
  .linkage-section {
    .linkage-grid { display: flex; flex-direction: column; gap: 8px; }
    .linkage-item { display: flex; align-items: center; gap: 8px; }
    .linkage-label { font-weight: 500; color: #333; }
    .chain-summary { font-size: var(--wp-font-size, 13px); color: #666; }
    .ref-chip { margin-right: 4px; }
  }

  // ─── Review ───
  .review-section {
    .pending-list { margin-bottom: 12px; }
    .pending-title { font-weight: 500; margin-bottom: 4px; }
    ul { margin: 0; padding-left: 20px; }
    li { font-size: var(--wp-font-size, 13px); color: #666; margin-bottom: 2px; }
  }

  // ─── Toolbar ───
  .toolbar-section { display: flex; gap: 8px; padding: 12px; background: #fafafa; border-radius: 6px; border: 1px solid #ebeef5; }

  // ─── 附件底稿 Tab 区域 ───
  .b30-attachment-section {
    margin-top: 24px;
    border: 1px solid #d8b8ee;
    border-radius: 12px;
    overflow: hidden;

    .attachment-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 12px 16px;
      background: linear-gradient(135deg, #f9f0ff 0%, #efdbff 100%);
      cursor: pointer;
      user-select: none;
      font-weight: 500;
      font-size: 14px;
      color: #531dab;
    }

    :deep(.el-tabs--border-card) {
      border: none;
      border-top: 1px solid #d8b8ee;
      border-radius: 0;
    }
  }

  // ─── Shared ───
  .text-danger { color: #ff4d4f !important; font-weight: 600; }
}

// ─── Print Styles (Task 4.1) ───
@media print {
  .gt-b30-group-audit {
    .no-print { display: none !important; }
    .tree-actions { display: none !important; }
    .table-filter { display: none !important; }
    .toolbar-section { display: none !important; }
    .reviewed-banner .el-button { display: none !important; }

    // Expand tree
    .el-tree-node__content { padding-left: 0 !important; }
    .el-tree-node { display: block !important; }
    .el-tree-node__children { display: block !important; }

    // Heatmap: A4 landscape
    .heatmap-section {
      page-break-before: always;
      @page { size: A4 landscape; }
    }

    // Table: A4 portrait
    .component-table-section {
      page-break-before: always;
      @page { size: A4 portrait; }
      .table-wrapper { overflow: visible; }
    }

    // Preserve colors
    * {
      -webkit-print-color-adjust: exact !important;
      print-color-adjust: exact !important;
      color-adjust: exact !important;
    }

    // Tree node borders visible
    .tree-node-content { border-left-width: 4px !important; border-left-style: solid !important; }

    section { border: none; box-shadow: none; page-break-inside: avoid; }
  }
}

// ─── Responsive (Task 3.13) ───
@media (max-width: 1024px) and (min-width: 768px) {
  .gt-b30-group-audit {
    .component-table-section .table-wrapper { overflow-x: auto; }
    .dashboard-grid { grid-template-columns: 1fr 1fr !important; }
  }
}

@media (max-width: 767px) {
  .gt-b30-group-audit {
    .dashboard-grid { grid-template-columns: 1fr !important; }
    .scope-row, .auditor-row, .materiality-row { flex-direction: column; align-items: flex-start; }
  }
}
</style>
