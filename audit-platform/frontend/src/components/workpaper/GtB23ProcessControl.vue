<script setup lang="ts">
/**
 * GtB23ProcessControl — B23 业务层面控制底稿（14 循环重做）
 * Spec: .kiro/specs/b23-business-control-rework/ | Tasks: 4.1~4.12
 *
 * 聚合专属组件（唯一渲染入口）：仪表盘 + 循环目录 + 循环卡片 + 循环详情
 * （整体控制汇总/控制矩阵21列/穿行测试/控制测试/缺陷/联动）+ 复核 + 附件。
 */
import { ref, computed, toRef, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { getWpIndex, type WpIndexItem } from '@/services/workpaperApi'
import { eventBus } from '@/utils/eventBus'
import { useB23FormData } from './composables/useB23FormData'
import {
  useB23ProcessControl, PROCESS_CONCLUSION_COLOR_MAP,
  ASSERTION_OPTIONS, FREQUENCY_OPTIONS, PREVENT_DETECT_OPTIONS, CTRL_TYPE_L1_OPTIONS,
  YES_NO_OPTIONS, CONTROL_TEST_RESULT_OPTIONS, DEFICIENCY_TYPE_OPTIONS,
  DEFICIENCY_SEVERITY_OPTIONS, CYCLE_CONCLUSION_OPTIONS,
  type CycleConclusion, type B23ControlPoint,
} from './composables/useB23ProcessControl'
import { useB23Review } from './composables/useB23Review'
import { useB23ImportExport } from './composables/useB23ImportExport'
import { B23_CYCLES, attachmentEntries } from './composables/b23CycleConfig'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useWorkpaperReviewProvide } from './composables/useWorkpaperReviewProvide'

const GtWpRendererLazy = defineAsyncComponent(() => import('./GtWpRenderer.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('./GtWpReviewDialogHost.vue'))
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const B23ControlPointDialog = defineAsyncComponent(() => import('./B23ControlPointDialog.vue'))
import http from '@/utils/http'

interface Props { wpId: string; projectId: string; wpCode: string; year: number; readonly?: boolean }
const props = defineProps<Props>()
const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void }>()

const wpIdRef = toRef(props, 'wpId')
const externalReadonly = toRef(props, 'readonly') as any

const { allResponses, loading, loadAll, saveImmediate, flushPendingSave, getField, setFieldImmediate } = useB23FormData(wpIdRef)
const pc = useB23ProcessControl(allResponses, saveImmediate)
const {
  expandedCycles, selectedCycle, selectCycle, expandAll, collapseAll,
  setApplicability, addControlPoint, removeControlPoint, setControlPointField, setControlPointFields, importControlPoints,
  setWalkthroughField, setControlTestField,
  addDeficiency, removeDeficiency, setDeficiencyField,
  suggestConclusion, setConclusion, getControlPoints, getApplicability,
  cycles, dashboardStats, linkageInfo, entityLevelContext, onControlConclusionChanged,
} = pc
const { isReviewed, isReadonly, canReview, pendingItems, reviewInfo, doReview, startAmendment } =
  useB23Review(wpIdRef, allResponses, cycles, externalReadonly, saveImmediate)

const { versionTrailRef, scheduleAutoSnapshot, openVersionHistory } = useWorkpaperVersionToolbar({
  wpId: wpIdRef, projectId: toRef(props, 'projectId') as any,
})
const { openReview } = useWorkpaperReviewProvide({
  wpId: wpIdRef, projectId: toRef(props, 'projectId') as any,
})

const ie = useB23ImportExport({
  getControlPoints: (code) => getControlPoints(code),
  getApplicability: (code) => getApplicability(code),
  applyImportedControlPoints: (code, points, mode) => importControlPoints(code, points, mode),
})

// ─── 当前选中循环 ─────────────────────────────────────────────────────────
const currentCard = computed(() => cycles.value.find((c) => c.code === selectedCycle.value) || null)

// ─── 编制进度（适用循环中已有结论数 / 适用循环数） ────────────────────────
const progress = computed(() => {
  const applicable = cycles.value.filter((c) => c.applicable)
  const done = applicable.filter((c) => !!c.conclusion).length
  return { done, total: applicable.length }
})

// ─── 控制矩阵列配置（21 列） ───────────────────────────────────────────────
type MatrixCol = { field: string; label: string; kind: 'text' | 'enum' | 'multi'; options?: readonly string[]; w: number }
const MATRIX_COLS: MatrixCol[] = [
  { field: 'subProcess', label: '子流程', kind: 'text', w: 110 },
  { field: 'ctrlNo', label: '控制编号', kind: 'text', w: 90 },
  { field: 'ctrlName', label: '控制名称', kind: 'text', w: 160 },
  { field: 'ctrlDesc', label: '详细控制描述', kind: 'text', w: 220 },
  { field: 'affectedItems', label: '受影响交易/账户/披露', kind: 'text', w: 160 },
  { field: 'assertion', label: '认定', kind: 'multi', options: ASSERTION_OPTIONS, w: 160 },
  { field: 'wcgwRef', label: 'WCGW', kind: 'text', w: 90 },
  { field: 'wcgwDetail', label: 'WCGW详细记录', kind: 'text', w: 180 },
  { field: 'ctrlAttr', label: '控制属性', kind: 'text', w: 110 },
  { field: 'frequency', label: '控制频率', kind: 'enum', options: FREQUENCY_OPTIONS, w: 100 },
  { field: 'itApp', label: 'IT应用名称', kind: 'text', w: 110 },
  { field: 'preventDetect', label: '预防性/检查性', kind: 'enum', options: PREVENT_DETECT_OPTIONS, w: 110 },
  { field: 'designEffective', label: '控制设计是否有效', kind: 'enum', options: YES_NO_OPTIONS, w: 110 },
  { field: 'ctrlTypeL1', label: '控制类型一级', kind: 'enum', options: CTRL_TYPE_L1_OPTIONS, w: 130 },
  { field: 'ctrlTypeL2', label: '控制类型二级', kind: 'text', w: 130 },
  { field: 'executor', label: '执行人', kind: 'text', w: 110 },
  { field: 'executorOrg', label: '执行人名称/服务机构', kind: 'text', w: 140 },
  { field: 'hasDoc', label: '是否有文件记录', kind: 'enum', options: YES_NO_OPTIONS, w: 100 },
  { field: 'isKeyControl', label: '是否关键控制点', kind: 'enum', options: YES_NO_OPTIONS, w: 100 },
  { field: 'doControlTest', label: '是否执行控制测试', kind: 'enum', options: YES_NO_OPTIONS, w: 110 },
]
// ⚙ 列显隐（>15 列宽表，默认隐藏部分次要列）
const hiddenCols = ref<Set<string>>(new Set(['ctrlAttr', 'itApp', 'executorOrg', 'ctrlTypeL2']))
const visibleCols = computed(() => MATRIX_COLS.filter((c) => !hiddenCols.value.has(c.field)))
function toggleCol(field: string) {
  const s = new Set(hiddenCols.value)
  s.has(field) ? s.delete(field) : s.add(field)
  hiddenCols.value = s
}

const METHOD_OPTIONS = ['询问', '观察', '检查文件', '重新执行'] as const

// ─── 循环级文本字段（受影响交易账户 / 审计说明），走 checklist_responses ────
function cycleTextId(code: string, key: string): string { return `B23-${code}-${key}` }
function getCycleText(code: string, key: string): string { return getField(cycleTextId(code, key)).remark || '' }
function setCycleText(code: string, key: string, val: string): void {
  setFieldImmediate(cycleTextId(code, key), { remark: val })
}

// ─── 结构化子表（JSON 存 remark，conclusion=null；WCGW 识别表 + 整体控制汇总各表） ──
function getCycleJson<T>(code: string, key: string, fallback: T): T {
  const raw = getField(cycleTextId(code, key)).remark
  if (!raw) return fallback
  try { return JSON.parse(raw) as T } catch { return fallback }
}
function setCycleJson(code: string, key: string, val: any): void {
  setFieldImmediate(cycleTextId(code, key), { remark: JSON.stringify(val) })
}

type SubCol = { field: string; label: string; w?: number }
interface SubTableDef { key: string; title: string; refChip?: string; cols: SubCol[] }
// 整体控制汇总（B23-N-1）源模板结构化表
const SUMMARY_TABLES: SubTableDef[] = [
  { key: 'dept', title: '涉及的主要部门及人员', cols: [
    { field: 'dept', label: '部门', w: 120 }, { field: 'name', label: '姓名', w: 100 },
    { field: 'title', label: '职务', w: 110 }, { field: 'duty', label: '职责及权限', w: 200 }, { field: 'remark', label: '备注', w: 120 } ] },
  { key: 'segregation', title: '有关职责分工的政策和程序', refChip: 'wp:B23-XX-5', cols: [
    { field: 'position', label: '职责分离岗位', w: 150 }, { field: 'personDuty', label: '人员及职责', w: 220 }, { field: 'note', label: '说明', w: 180 } ] },
  { key: 'special-risk', title: '针对特别风险的控制', refChip: 'wp:B50-4', cols: [
    { field: 'risk', label: '特别风险', w: 140 }, { field: 'account', label: '相关交易/账户/披露', w: 160 },
    { field: 'assertion', label: '相关认定', w: 110 }, { field: 'ctrlDesc', label: '详细控制描述', w: 220 } ] },
  { key: 'app-system', title: '涉及的应用软件系统', refChip: 'wp:B22A-4-3', cols: [
    { field: 'sysName', label: '应用软件系统名称', w: 160 }, { field: 'changes', label: '本年度重大修改/开发/维护', w: 220 }, { field: 'remark', label: '备注', w: 140 } ] },
  { key: 'service-org', title: '对使用服务机构的考虑', refChip: 'wp:B14', cols: [
    { field: 'orgName', label: '服务机构名称', w: 150 }, { field: 'activities', label: '执行的主要业务活动', w: 200 }, { field: 'control', label: '对其控制活动的了解和测试', w: 200 } ] },
]
// WCGW（容易出错领域）与控制点识别表（B23-N-2 核心，矩阵 WCGW 引用于此）
const WCGW_COLS: SubCol[] = [
  { field: 'wcgwNo', label: 'WCGW编号', w: 100 }, { field: 'subProcess', label: '子流程', w: 120 },
  { field: 'wcgwDesc', label: '容易出错领域详细描述', w: 240 }, { field: 'ctrlDesc', label: '对应控制描述', w: 240 },
]
type SubRow = Record<string, string>
function getSubRows(code: string, key: string): SubRow[] { return getCycleJson<SubRow[]>(code, key, []) }
function addSubRow(code: string, key: string, cols: SubCol[]): void {
  const rows = getSubRows(code, key).slice()
  const blank: SubRow = {}; cols.forEach((c) => { blank[c.field] = '' })
  rows.push(blank); setCycleJson(code, key, rows)
}
function removeSubRow(code: string, key: string, idx: number): void {
  const rows = getSubRows(code, key).slice(); rows.splice(idx, 1); setCycleJson(code, key, rows)
}
function setSubCell(code: string, key: string, idx: number, field: string, val: string): void {
  const rows = getSubRows(code, key).slice(); if (!rows[idx]) return
  rows[idx] = { ...rows[idx], [field]: val }; setCycleJson(code, key, rows)
}
/** WCGW 编号选项（供控制矩阵 wcgwRef 下拉引用，从本循环 WCGW 识别表派生） */
function wcgwRefOptions(code: string): string[] {
  return getSubRows(code, 'wcgw').map((r) => r.wcgwNo).filter(Boolean)
}

// ─── 双模式（结构化视图 / OnlyOffice 在线编辑，参照 D4：拉取成功才启用） ──────
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
// 当前循环对应的子底稿 wp_id（每循环独立 xlsx，OnlyOffice 按其加载整册）
const currentCardWpId = computed<string>(() => {
  const card = currentCard.value
  if (!card) return ''
  return attachmentWpIdMap.value[card.wpCode] || ''
})
// 切换循环时回落结构化视图，避免残留他循环的 OnlyOffice 实例
function selectCycleAndReset(code: string) {
  selectCycle(code)
  editorMode.value = 'structured'
}

// ─── 联动/交叉引用 ────────────────────────────────────────────────────────
const CROSS_REFS = [
  { value: 'wp:B22A-4', label: 'B22A-4 IT控制' },
  { value: 'wp:B18', label: 'B18 内部审计' },
  { value: 'wp:B14', label: 'B14 外包/SOC' },
  { value: 'wp:B50-4', label: 'B50-4 特别风险' },
  { value: 'wp:A14-4', label: 'A14-4 缺陷评价' },
  { value: 'wp:C26', label: 'C26 信息处理控制' },
  { value: 'wp:A27-1', label: 'A27-1 IT审计备忘' },
]
const currentLinkage = computed(() => linkageInfo.value.find((l) => l.code === selectedCycle.value) || null)

// ─── 色彩 ─────────────────────────────────────────────────────────────────
function concColor(c: CycleConclusion | null): string { return c ? (PROCESS_CONCLUSION_COLOR_MAP[c]?.color || '#1890ff') : '#1890ff' }
function concLabel(c: CycleConclusion | null): string { return c ? (PROCESS_CONCLUSION_COLOR_MAP[c]?.label || '待测试') : '待测试' }

// ─── 结论设置（含手动覆盖理由） ───────────────────────────────────────────
async function onSetConclusion(code: string, val: CycleConclusion) {
  const suggested = suggestConclusion(code)
  if (suggested && val !== suggested) {
    try {
      const { value } = await ElMessageBox.prompt(
        `系统建议结论为「${suggested}」，你选择「${val}」。请填写覆盖理由：`, '手动调整结论',
        { inputType: 'textarea', inputValidator: (v: string) => (v && v.trim() ? true : '覆盖理由不能为空') },
      )
      setConclusion(code, val, value)
    } catch { /* 取消 */ }
  } else {
    setConclusion(code, val)
  }
  pushControlRiskToB50(code, val)
  scheduleAutoSnapshot()
  emit('save')
}

// ─── 控制结论 → B50 风险因素（控制不可依赖时推送，复用 b50:push-risk-factor，source=B23） ──
const B23_RISK_IMPACT: Record<string, string> = {
  '设计无效': '控制风险评估为高，仅实施实质性程序可能不足以应对认定层次重大错报风险，建议扩大实质性程序的范围和样本量',
  '设计有效但未有效实施': '控制风险评估为中，控制未有效运行，建议加强相关认定的实质性程序',
}
function pushControlRiskToB50(code: string, conclusion: CycleConclusion) {
  const impact = B23_RISK_IMPACT[conclusion]
  if (!impact) return
  const def = cycles.value.find((c) => c.code === code)
  const name = def?.name || code
  try {
    eventBus.emit('b50:push-risk-factor' as any, {
      source: 'B23',
      factors: [`${name}业务层面控制${conclusion}——${impact}（来自 B23）`],
    })
  } catch { /* B50 未挂载时忽略 */ }
}

// ─── 缺陷提示（设计无效/穿行未按设计执行 → 提示，即使缺陷数为0） ───────────
const deficiencyHintList = computed(() => {
  const card = currentCard.value
  if (!card) return [] as string[]
  const hints: string[] = []
  card.controlPoints.forEach((cp) => {
    if (cp.designEffective === '否') hints.push(`控制点 ${cp.ctrlNo || cp.index}：设计无效，需识别缺陷`)
    if (card.walkthroughs[cp.index - 1]?.asDesigned === '否') hints.push(`控制点 ${cp.ctrlNo || cp.index}：穿行未按设计执行，需识别缺陷`)
  })
  return hints
})

// ─── 控制点删除确认 ───────────────────────────────────────────────────────
async function onRemoveControlPoint(code: string, index: number) {
  try {
    await ElMessageBox.confirm(`确认删除控制点 ${index}？`, '删除确认', { type: 'warning' })
    removeControlPoint(code, index)
    emit('save')
  } catch { /* 取消 */ }
}

// ─── 新增动态行需命名（子流程） ──────────────────────────────────────────
async function onAddControlPoint(code: string) {
  addControlPoint(code)
  emit('save')
}

// ─── 控制点引导式录入弹窗 ─────────────────────────────────────────────────
const cpDialogVisible = ref(false)
const cpDialogRow = ref<B23ControlPoint | null>(null)
const cpDialogWalkthrough = computed(() => {
  const card = currentCard.value; const row = cpDialogRow.value
  if (!card || !row) return null
  return card.walkthroughs[row.index - 1] || null
})
function openControlPointDialog(row: B23ControlPoint) {
  cpDialogRow.value = row
  cpDialogVisible.value = true
}
function openNewControlPointDialog(code: string) {
  addControlPoint(code)
  // 新增后取末行进入弹窗（cycles 为 computed，下一 tick 读取）
  requestAnimationFrame(() => {
    const pts = getControlPoints(code)
    if (pts.length) openControlPointDialog(pts[pts.length - 1])
    emit('save')
  })
}
function onControlPointDialogSave(patch: Partial<B23ControlPoint>) {
  const card = currentCard.value; const row = cpDialogRow.value
  if (!card || !row) return
  setControlPointFields(card.code, row.index, patch)
  scheduleAutoSnapshot()
  emit('save')
}

// ─── AI 辅助（审计说明） ──────────────────────────────────────────────────
const aiLoading = ref(false)
async function onAiNote(code: string) {
  const card = currentCard.value
  if (!card) return
  aiLoading.value = true
  try {
    const ctx: Record<string, string> = {
      循环: card.name,
      控制点数: String(card.controlPoints.length),
      关键控制点数: String(card.keyControlCount),
      缺陷数: String(card.deficiencyCount),
      循环结论: card.conclusion || '未定',
    }
    const res: any = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      prompt: `为 B23 ${card.name} 业务层面控制生成审计说明，概述控制了解、穿行与控制测试结果及对实质性程序的影响。`,
      context: ctx, section: 'b23-audit-note', existingContent: getCycleText(code, 'audit-note'),
    })
    const text = res?.content ?? res?.data?.content ?? ''
    if (text) setCycleText(code, 'audit-note', text)
  } catch { ElMessage.warning('AI 生成失败，可手动填写') }
  finally { aiLoading.value = false }
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────
const importInput = ref<HTMLInputElement | null>(null)
function onImportClick() { importInput.value?.click() }
async function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await ie.importData(file, 'overwrite')
  ;(e.target as HTMLInputElement).value = ''
  emit('save')
}
function onExportData() { ie.exportData(props.wpCode || 'B23') }
function onExportTemplate() { ie.exportTemplate() }

// ─── 复核 ─────────────────────────────────────────────────────────────────
async function onDoReview() {
  if (!canReview.value) return
  await doReview()
  emit('completed')
}
async function onAmendment() {
  try {
    const { value } = await ElMessageBox.prompt('请填写修改原因（复核锁定后修订需重新复核）：', '修订', {
      inputType: 'textarea', inputValidator: (v: string) => (v && v.trim() ? true : '修改原因不能为空'),
    })
    await startAmendment(value)
  } catch { /* 取消 */ }
}

// ─── 附件底稿 Tab（同源，覆盖 14+2，标签正确） ─────────────────────────────
const attachmentWpIndex = ref<WpIndexItem[]>([])
const attachmentExpanded = ref(false)
const attachmentActive = ref('')
const ATTACH_ENTRIES = attachmentEntries()

const attachmentWpIdMap = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const item of attachmentWpIndex.value) {
    // B23 全部子底稿共享 wp_code=B23；按 wp_code 精确匹配子底稿编码
    if (item.wp_code && /^B23(-\d+|-XX-5)?$/.test(item.wp_code)) map[item.wp_code] = item.id
  }
  return map
})
const attachmentTabs = computed(() =>
  ATTACH_ENTRIES
    .filter((e) => !!attachmentWpIdMap.value[e.wpCode])
    .map((e) => ({ id: e.code, label: `${e.wpCode} ${e.label}`, wpId: attachmentWpIdMap.value[e.wpCode] })),
)

// ─── EventBus：接收 B22A control:conclusion-changed ────────────────────────
function onB22AConclusion(evt: any) {
  const d = evt?.detail || evt
  if (d) onControlConclusionChanged(d)
}

onMounted(async () => {
  await loadAll()
  checkOoHealth()
  window.addEventListener('control:conclusion-changed', onB22AConclusion as any)
  try {
    if (props.projectId) attachmentWpIndex.value = await getWpIndex(props.projectId)
  } catch { attachmentWpIndex.value = [] }
})
onBeforeUnmount(() => {
  flushPendingSave()
  window.removeEventListener('control:conclusion-changed', onB22AConclusion as any)
})
</script>

<template>
  <div class="gt-b23" :class="{ 'is-readonly': isReadonly }">
    <div v-if="loading" class="loading-mask">加载中...</div>

    <!-- 已复核横幅 -->
    <el-alert v-if="isReviewed" type="success" :closable="false" show-icon class="reviewed-banner">
      已复核 · 复核人 {{ reviewInfo?.reviewer }} · {{ reviewInfo?.date }}
      <el-button v-if="!externalReadonly" link type="primary" size="small" @click="onAmendment">发起修订</el-button>
    </el-alert>

    <!-- 顶部：审计目标 + 进度 + 工具栏 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>审计目标（CAS 1231）</template>
      了解被审计单位各业务循环与财务报告相关的内部控制，评价控制设计与执行的有效性，
      执行穿行测试与控制测试，识别控制缺陷并评估对实质性程序性质、时间安排和范围的影响。
    </el-alert>

    <div class="toolbar">
      <div class="toolbar-left">
        <span class="progress-chip">编制进度 {{ progress.done }} / {{ progress.total }}</span>
        <el-button size="small" @click="expandAll" :disabled="isReadonly">全部展开</el-button>
        <el-button size="small" @click="collapseAll">全部收起</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onExportTemplate">导出空白模板</el-dropdown-item>
              <el-dropdown-item @click="onExportData">导出数据</el-dropdown-item>
              <el-dropdown-item :disabled="isReadonly" @click="onImportClick">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openVersionHistory">版本历史</el-button>
        <input ref="importInput" type="file" accept=".xlsx" style="display:none" @change="onImportFile" />
      </div>
    </div>

    <!-- Status Dashboard -->
    <section class="dashboard">
      <div class="stat-grid">
        <div class="stat-card"><div class="stat-num">{{ dashboardStats.applicableCount }}</div><div class="stat-lbl">适用循环</div></div>
        <div class="stat-card"><div class="stat-num">{{ dashboardStats.completedCount }}</div><div class="stat-lbl">已完成结论</div></div>
        <div class="stat-card"><div class="stat-num">{{ dashboardStats.totalControlPoints }}</div><div class="stat-lbl">控制点</div></div>
        <div class="stat-card"><div class="stat-num">{{ dashboardStats.totalKeyControls }}</div><div class="stat-lbl">关键控制点</div></div>
        <div class="stat-card"><div class="stat-num" style="color:#faad14">{{ dashboardStats.pendingWalkthroughCount }}</div><div class="stat-lbl">待穿行</div></div>
        <div class="stat-card"><div class="stat-num" style="color:#faad14">{{ dashboardStats.pendingControlTestCount }}</div><div class="stat-lbl">待控制测试</div></div>
        <div class="stat-card"><div class="stat-num" style="color:#ff4d4f">{{ dashboardStats.totalDeficiencies }}</div><div class="stat-lbl">缺陷</div></div>
      </div>

      <!-- Entity Level Context（B22A 只读） -->
      <div class="entity-context">
        <div class="ec-head">
          <span>实体层面控制上下文（B22A）</span>
          <GtIndexChip value="wp:B22A" />
        </div>
        <div v-if="!entityLevelContext || !entityLevelContext.completed" class="ec-empty">B22A 未完成，实体层面结论待定</div>
        <div v-else class="ec-body">
          <el-tag v-for="(v, k) in entityLevelContext.elementScores" :key="k"
            :type="v === '无效' ? 'danger' : v === '部分有效' ? 'warning' : 'success'" size="small">
            要素{{ k }}：{{ v || '—' }}
          </el-tag>
          <div class="ec-overall">整体结论：{{ entityLevelContext.overallConclusion }}</div>
          <el-alert v-if="entityLevelContext.elementScores[1] === '无效'" type="error" :closable="false"
            title="实体层面控制环境薄弱，流程控制有效性可能受限" show-icon />
        </div>
      </div>
    </section>

    <!-- 审计链路流程图 -->
    <section class="flow-diagram">
      <div class="flow-node"><GtIndexChip value="wp:B22A" /><span>企业层面</span></div>
      <span class="flow-arrow">→</span>
      <div class="flow-node active"><strong>B23 业务层面</strong></div>
      <span class="flow-arrow">→</span>
      <div class="flow-node"><GtIndexChip value="wp:B50" /><span>控制风险</span></div>
      <span class="flow-arrow">→</span>
      <div class="flow-node"><span>C 类控制测试 → D~N 实质性程序</span></div>
    </section>

    <div class="main-layout">
      <!-- 循环目录 -->
      <aside class="cycle-directory">
        <div class="dir-title">循环目录</div>
        <div v-for="c in cycles" :key="c.code" class="dir-item"
          :class="{ active: c.code === selectedCycle, na: !c.applicable }" @click="selectCycleAndReset(c.code)">
          <span class="dir-dot" :style="{ background: c.applicable ? concColor(c.conclusion) : '#d9d9d9' }" />
          <span class="dir-name">{{ c.name }}</span>
          <span class="dir-code">{{ c.wpCode }}</span>
        </div>
      </aside>

      <!-- 循环卡片 + 详情 -->
      <div class="cycle-main">
        <!-- 循环卡片网格 -->
        <div class="cycle-cards">
          <div v-for="c in cycles" :key="c.code" class="cycle-card"
            :class="{ selected: c.code === selectedCycle, na: !c.applicable }"
            :style="{ borderLeftColor: c.applicable ? concColor(c.conclusion) : '#d9d9d9' }"
            @click="selectCycleAndReset(c.code)">
            <div class="cc-head">
              <span class="cc-name">{{ c.name }}</span>
              <GtIndexChip :value="`wp:${c.wpCode}`" />
            </div>
            <div class="cc-meta">
              <el-tag size="small" :style="{ color: concColor(c.conclusion), borderColor: concColor(c.conclusion) }" effect="plain">
                {{ concLabel(c.conclusion) }}
              </el-tag>
              <span class="cc-ratio">控制点 {{ c.controlPoints.length }} · 关键 {{ c.keyControlCount }}</span>
            </div>
            <div class="cc-foot">
              <el-switch :model-value="c.applicable" :disabled="isReadonly" size="small"
                active-text="适用" inactive-text="不适用" inline-prompt
                @update:model-value="(v: any) => setApplicability(c.code, !!v)" @click.stop />
            </div>
          </div>
        </div>

        <!-- 循环详情（选中后展开，默认隐藏） -->
        <section v-if="currentCard && currentCard.applicable" class="cycle-detail">
          <div class="cd-titlebar">
            <h3 class="cd-title">{{ currentCard.name }}（{{ currentCard.wpCode }}）</h3>
            <div class="cd-mode">
              <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
              <el-tooltip :content="ooHealthy ? 'OnlyOffice 服务就绪，可在线编辑源底稿' : 'OnlyOffice 服务未就绪，已锁定在线编辑'" placement="top">
                <el-tag :type="ooHealthy ? 'success' : 'info'" size="small" effect="plain">
                  {{ ooHealthy ? '在线编辑就绪' : '在线编辑未就绪' }}
                </el-tag>
              </el-tooltip>
            </div>
          </div>

          <!-- ═══ 结构化视图 ═══ -->
          <template v-if="editorMode === 'structured'">
          <!-- 整体控制汇总（B23-N-1） -->
          <el-card shadow="never" class="cd-block">
            <template #header>整体控制汇总</template>
            <div class="field-row">
              <label>受影响的交易/账户/披露</label>
              <el-input :model-value="getCycleText(currentCard.code, 'affected-accounts')" :disabled="isReadonly"
                type="textarea" :autosize="{ minRows: 2 }"
                @update:model-value="(v: string) => setCycleText(currentCard!.code, 'affected-accounts', v)" />
            </div>
            <!-- 源模板结构化子表：部门人员 / 职责分离 / 特别风险控制 / 应用系统 / 服务机构 -->
            <div v-for="t in SUMMARY_TABLES" :key="t.key" class="sub-table">
              <div class="sub-head">
                <span class="sub-title">{{ t.title }}</span>
                <span class="sub-actions">
                  <GtIndexChip v-if="t.refChip" :value="t.refChip" />
                  <el-button link size="small" :disabled="isReadonly" @click="addSubRow(currentCard!.code, t.key, t.cols)">+ 新增行</el-button>
                </span>
              </div>
              <el-table :data="getSubRows(currentCard.code, t.key)" border size="small">
                <el-table-column type="index" label="#" width="40" />
                <el-table-column v-for="col in t.cols" :key="col.field" :label="col.label" :min-width="col.w || 120">
                  <template #default="{ $index }">
                    <el-input :model-value="getSubRows(currentCard!.code, t.key)[$index]?.[col.field] || ''" :disabled="isReadonly" size="small"
                      @update:model-value="(v: string) => setSubCell(currentCard!.code, t.key, $index, col.field, v)" />
                  </template>
                </el-table-column>
                <el-table-column label="操作" width="50" fixed="right">
                  <template #default="{ $index }">
                    <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeSubRow(currentCard!.code, t.key, $index)">删</el-button>
                  </template>
                </el-table-column>
              </el-table>
            </div>
          </el-card>

          <!-- 流程与 WCGW 识别表（B23-N-2，矩阵 WCGW 引用于此） -->
          <el-card shadow="never" class="cd-block">
            <template #header>
              <div class="block-head">
                <span>流程与 WCGW（容易出错领域）识别</span>
                <el-button link size="small" :disabled="isReadonly" @click="addSubRow(currentCard.code, 'wcgw', WCGW_COLS)">+ 新增 WCGW</el-button>
              </div>
            </template>
            <div class="wcgw-tip">先叙述子流程并标注容易出错领域（WCGW），再在下方控制矩阵将「WCGW」列下拉引用到此处编号，形成 WCGW → 关键控制点 → 穿行/控制测试的追溯链。</div>
            <div class="field-row">
              <label>子流程叙述（按源模板默认子流程展开，可增补）</label>
              <el-input :model-value="getCycleText(currentCard.code, 'process-narrative')" :disabled="isReadonly"
                type="textarea" :autosize="{ minRows: 3 }" placeholder="逐子流程描述业务活动与控制点，标注容易出错的领域（WCGW）"
                @update:model-value="(v: string) => setCycleText(currentCard!.code, 'process-narrative', v)" />
            </div>
            <el-table :data="getSubRows(currentCard.code, 'wcgw')" border size="small">
              <el-table-column type="index" label="#" width="40" />
              <el-table-column v-for="col in WCGW_COLS" :key="col.field" :label="col.label" :min-width="col.w || 120">
                <template #default="{ $index }">
                  <el-input :model-value="getSubRows(currentCard!.code, 'wcgw')[$index]?.[col.field] || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setSubCell(currentCard!.code, 'wcgw', $index, col.field, v)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="50" fixed="right">
                <template #default="{ $index }">
                  <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeSubRow(currentCard!.code, 'wcgw', $index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 控制矩阵 -->
          <el-card shadow="never" class="cd-block">
            <template #header>
              <div class="block-head">
                <span>控制矩阵（{{ currentCard.controlPoints.length }} 个控制点）</span>
                <div>
                  <el-popover trigger="click" width="260">
                    <template #reference><el-button link size="small">⚙ 列设置</el-button></template>
                    <el-checkbox v-for="col in MATRIX_COLS" :key="col.field"
                      :model-value="!hiddenCols.has(col.field)" @update:model-value="() => toggleCol(col.field)"
                      style="display:block">{{ col.label }}</el-checkbox>
                  </el-popover>
                  <el-button link type="primary" size="small" :disabled="isReadonly" @click="openNewControlPointDialog(currentCard.code)">✏️ 引导录入</el-button>
                  <el-button link size="small" :disabled="isReadonly" @click="onAddControlPoint(currentCard.code)">+ 快速加行</el-button>
                  <el-button link size="small" @click="openReview({ sectionId: `b23-${currentCard.code}-matrix`, sectionLabel: `${currentCard.name} 控制矩阵` })">💬 复核</el-button>
                </div>
              </div>
            </template>
            <el-table :data="currentCard.controlPoints" border size="small" class="matrix-table">
              <el-table-column type="index" label="#" width="40" fixed />
              <el-table-column v-for="col in visibleCols" :key="col.field" :label="col.label" :min-width="col.w">
                <template #default="{ row }">
                  <el-select v-if="col.field === 'wcgwRef'" :model-value="(row as any).wcgwRef" :disabled="isReadonly"
                    clearable filterable allow-create size="small" placeholder="引用WCGW"
                    @update:model-value="(v: any) => setControlPointField(currentCard!.code, row.index, 'wcgwRef', v)">
                    <el-option v-for="w in wcgwRefOptions(currentCard!.code)" :key="w" :label="w" :value="w" />
                  </el-select>
                  <el-select v-else-if="col.kind === 'enum'" :model-value="(row as any)[col.field]" :disabled="isReadonly"
                    clearable size="small" placeholder="—"
                    @update:model-value="(v: any) => setControlPointField(currentCard!.code, row.index, col.field, v)">
                    <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                  </el-select>
                  <el-select v-else-if="col.kind === 'multi'" :model-value="(row as any)[col.field]" :disabled="isReadonly"
                    multiple collapse-tags size="small" placeholder="—"
                    @update:model-value="(v: any) => setControlPointField(currentCard!.code, row.index, col.field, v)">
                    <el-option v-for="o in col.options" :key="o" :label="o" :value="o" />
                  </el-select>
                  <el-input v-else :model-value="(row as any)[col.field]" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setControlPointField(currentCard!.code, row.index, col.field, v)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="90" fixed="right">
                <template #default="{ row }">
                  <el-button link type="primary" size="small" @click="openControlPointDialog(row)">编辑</el-button>
                  <el-button link type="danger" size="small" :disabled="isReadonly" @click="onRemoveControlPoint(currentCard!.code, row.index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 穿行测试（验设计） -->
          <el-card shadow="never" class="cd-block">
            <template #header>穿行测试（验证控制设计是否得到执行）</template>
            <el-table :data="currentCard.controlPoints" border size="small">
              <el-table-column label="控制编号" width="90"><template #default="{ row }">{{ row.ctrlNo || row.index }}</template></el-table-column>
              <el-table-column label="测试方法" min-width="150">
                <template #default="{ row }">
                  <el-select :model-value="currentCard!.walkthroughs[row.index - 1]?.method || []" :disabled="isReadonly"
                    multiple collapse-tags size="small"
                    @update:model-value="(v: any) => setWalkthroughField(currentCard!.code, row.index, 'method', v)">
                    <el-option v-for="o in METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="实施程序" min-width="160">
                <template #default="{ row }">
                  <el-input :model-value="currentCard!.walkthroughs[row.index - 1]?.procedure || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setWalkthroughField(currentCard!.code, row.index, 'procedure', v)" />
                </template>
              </el-table-column>
              <el-table-column label="检查证据" min-width="140">
                <template #default="{ row }">
                  <el-input :model-value="currentCard!.walkthroughs[row.index - 1]?.evidence || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setWalkthroughField(currentCard!.code, row.index, 'evidence', v)" />
                </template>
              </el-table-column>
              <el-table-column label="是否按设计执行" width="120">
                <template #default="{ row }">
                  <el-select :model-value="currentCard!.walkthroughs[row.index - 1]?.asDesigned" :disabled="isReadonly"
                    clearable size="small" placeholder="—"
                    @update:model-value="(v: any) => setWalkthroughField(currentCard!.code, row.index, 'asDesigned', v)">
                    <el-option v-for="o in YES_NO_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 控制测试（验运行） -->
          <el-card shadow="never" class="cd-block">
            <template #header>控制测试（验证控制运行有效性，走 C 类底稿）</template>
            <el-table :data="currentCard.controlPoints.filter(cp => cp.doControlTest === '是')" border size="small">
              <el-table-column label="控制编号" width="90"><template #default="{ row }">{{ row.ctrlNo || row.index }}</template></el-table-column>
              <el-table-column label="测试性质" min-width="120">
                <template #default="{ row }">
                  <el-input :model-value="currentCard!.controlTests[row.index - 1]?.testNature || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setControlTestField(currentCard!.code, row.index, 'testNature', v)" />
                </template>
              </el-table-column>
              <el-table-column label="测试范围/样本" min-width="120">
                <template #default="{ row }">
                  <el-input :model-value="currentCard!.controlTests[row.index - 1]?.testScope || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setControlTestField(currentCard!.code, row.index, 'testScope', v)" />
                </template>
              </el-table-column>
              <el-table-column label="运行有效性" width="110">
                <template #default="{ row }">
                  <el-select :model-value="currentCard!.controlTests[row.index - 1]?.operatingEffective" :disabled="isReadonly"
                    clearable size="small" placeholder="—"
                    @update:model-value="(v: any) => setControlTestField(currentCard!.code, row.index, 'operatingEffective', v)">
                    <el-option v-for="o in CONTROL_TEST_RESULT_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="对实质性程序的影响" min-width="160">
                <template #default="{ row }">
                  <el-input :model-value="currentCard!.controlTests[row.index - 1]?.substantiveImpact || ''" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setControlTestField(currentCard!.code, row.index, 'substantiveImpact', v)" />
                </template>
              </el-table-column>
            </el-table>
            <el-empty v-if="!currentCard.controlPoints.some(cp => cp.doControlTest === '是')" description="暂无拟测试控制（在控制矩阵将「是否执行控制测试」设为「是」）" :image-size="60" />
          </el-card>

          <!-- 缺陷汇总（A14-4 分级） -->
          <el-card shadow="never" class="cd-block">
            <template #header>
              <div class="block-head">
                <span>控制缺陷汇总（按 A14-4 分级）</span>
                <div>
                  <GtIndexChip value="wp:A14-4" />
                  <el-button link size="small" :disabled="isReadonly" @click="addDeficiency(currentCard.code)">+ 新增缺陷</el-button>
                </div>
              </div>
            </template>
            <el-alert v-for="(h, i) in deficiencyHintList" :key="i" type="warning" :closable="false" show-icon :title="h" class="def-hint" />
            <el-table :data="currentCard.deficiencies" border size="small">
              <el-table-column type="index" label="#" width="40" />
              <el-table-column label="子流程" min-width="110">
                <template #default="{ row }">
                  <el-input :model-value="row.subProcess" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setDeficiencyField(currentCard!.code, row.index, 'subProcess', v)" />
                </template>
              </el-table-column>
              <el-table-column label="缺陷描述" min-width="200">
                <template #default="{ row }">
                  <el-input :model-value="row.description" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setDeficiencyField(currentCard!.code, row.index, 'description', v)" />
                </template>
              </el-table-column>
              <el-table-column label="缺陷类型" width="130">
                <template #default="{ row }">
                  <el-select :model-value="row.deficiencyType" :disabled="isReadonly" clearable size="small" placeholder="—"
                    @update:model-value="(v: any) => setDeficiencyField(currentCard!.code, row.index, 'deficiencyType', v)">
                    <el-option v-for="o in DEFICIENCY_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="严重程度" width="120">
                <template #default="{ row }">
                  <el-select :model-value="row.severity" :disabled="isReadonly" clearable size="small" placeholder="—"
                    @update:model-value="(v: any) => setDeficiencyField(currentCard!.code, row.index, 'severity', v)">
                    <el-option v-for="o in DEFICIENCY_SEVERITY_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </template>
              </el-table-column>
              <el-table-column label="影响" min-width="150">
                <template #default="{ row }">
                  <el-input :model-value="row.impact" :disabled="isReadonly" size="small"
                    @update:model-value="(v: string) => setDeficiencyField(currentCard!.code, row.index, 'impact', v)" />
                </template>
              </el-table-column>
              <el-table-column label="操作" width="50" fixed="right">
                <template #default="{ row }">
                  <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeDeficiency(currentCard!.code, row.index)">删</el-button>
                </template>
              </el-table-column>
            </el-table>
          </el-card>

          <!-- 联动面板 + 交叉引用 -->
          <el-card shadow="never" class="cd-block">
            <template #header>跨底稿联动</template>
            <div v-if="currentLinkage" class="linkage">
              <div class="lk-row"><span>B50 控制风险影响：</span><strong>{{ currentLinkage.b50Impact || '待定' }}</strong></div>
              <div class="lk-row"><span>关联 C 类控制测试：</span>
                <GtIndexChip v-for="c in currentLinkage.cTests" :key="c" :value="`wp:${c}`" />
                <span v-if="!currentLinkage.cTests.length">—</span>
              </div>
              <el-alert v-if="currentLinkage.needsExtendedProcedures" type="warning" :closable="false" show-icon
                title="控制不可依赖——建议扩大实质性程序范围和样本量（仅建议，需审计师复核决定）" />
            </div>
            <div class="cross-refs">
              <span class="cr-label">相关底稿：</span>
              <GtIndexChip v-for="r in CROSS_REFS" :key="r.value" :value="r.value" />
            </div>
          </el-card>

          <!-- 循环结论 + 审计说明 -->
          <el-card shadow="never" class="cd-block">
            <template #header>
              <div class="block-head">
                <span>循环控制结论</span>
                <el-button link size="small" @click="openReview({ sectionId: `b23-${currentCard.code}-conclusion`, sectionLabel: `${currentCard.name} 结论` })">💬 复核</el-button>
              </div>
            </template>
            <div class="conc-row">
              <span>系统建议：<strong>{{ suggestConclusion(currentCard.code) || '待评估' }}</strong></span>
              <el-select :model-value="currentCard.conclusion" :disabled="isReadonly" placeholder="选择结论" style="width:220px"
                @update:model-value="(v: any) => onSetConclusion(currentCard!.code, v)">
                <el-option v-for="o in CYCLE_CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
              <el-tag v-if="currentCard.conclusionOverridden" type="warning" size="small">已手动调整</el-tag>
            </div>
            <div v-if="currentCard.conclusionOverridden" class="override-reason">覆盖理由：{{ currentCard.overrideReason }}</div>
            <div class="field-row">
              <label>
                审计说明
                <el-button link type="primary" size="small" :loading="aiLoading" :disabled="isReadonly" @click="onAiNote(currentCard.code)">🤖 AI 辅助</el-button>
              </label>
              <el-input :model-value="getCycleText(currentCard.code, 'audit-note')" :disabled="isReadonly"
                type="textarea" :autosize="{ minRows: 4 }"
                @update:model-value="(v: string) => setCycleText(currentCard!.code, 'audit-note', v)" />
            </div>
          </el-card>
          </template>

          <!-- ═══ OnlyOffice 在线编辑（拉取成功才启用；按循环加载各自源底稿整册） ═══ -->
          <template v-else>
            <div v-if="currentCardWpId" class="oo-container">
              <GtOnlyOfficeSheet :wp-id="currentCardWpId" :project-id="projectId"
                :sheet-name="currentCard.name" :whole-workbook="true" :readonly="isReadonly" />
            </div>
            <el-empty v-else description="未找到该循环对应的源底稿（在线编辑不可用），请使用结构化视图" :image-size="80" />
          </template>
        </section>
        <el-empty v-else-if="!currentCard" description="请从上方选择一个业务循环开始编制" :image-size="80" />
      </div>
    </div>

    <!-- 现场经理复核区 -->
    <section class="review-section">
      <div class="rv-head">现场经理复核</div>
      <div v-if="pendingItems.length" class="rv-pending">
        <div class="rv-pending-title">待完成事项（{{ pendingItems.length }}）：</div>
        <ul><li v-for="(p, i) in pendingItems" :key="i">{{ p }}</li></ul>
      </div>
      <el-button type="primary" :disabled="!canReview || isReviewed" @click="onDoReview">
        {{ isReviewed ? '已复核' : '复核签字' }}
      </el-button>
    </section>

    <!-- 附件底稿 Tab -->
    <section v-if="attachmentTabs.length" class="attachment-section">
      <div class="attach-head" @click="attachmentExpanded = !attachmentExpanded">
        <span>📎 附件底稿（{{ attachmentTabs.length }}）</span><span>{{ attachmentExpanded ? '−' : '+' }}</span>
      </div>
      <div v-show="attachmentExpanded">
        <el-tabs v-model="attachmentActive" type="border-card">
          <el-tab-pane v-for="t in attachmentTabs" :key="t.id" :label="t.label" :name="t.id" lazy>
            <GtWpRendererLazy :wp-id="t.wpId" :readonly="isReadonly" />
          </el-tab-pane>
        </el-tabs>
      </div>
    </section>

    <B23ControlPointDialog v-model="cpDialogVisible" :cycle-name="currentCard?.name || ''"
      :control-point="cpDialogRow" :walkthrough="cpDialogWalkthrough"
      :wcgw-options="currentCard ? wcgwRefOptions(currentCard.code) : []" :readonly="isReadonly"
      @save="onControlPointDialogSave" />

    <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    <GtWpReviewDialogHost />
  </div>
</template>

<style scoped lang="scss">
.gt-b23 {
  padding: 16px; font-size: 13px;
  &.is-readonly { .el-input, .el-select, .el-switch, .el-button { pointer-events: none; opacity: 0.75; } }
  .loading-mask { text-align: center; padding: 40px; color: #999; }
  .reviewed-banner { margin-bottom: 12px; }
  .audit-objective { margin-bottom: 12px; }

  .toolbar {
    display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px;
    .toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
    .progress-chip { font-weight: 600; color: #531dab; }
  }

  .dashboard {
    display: flex; gap: 16px; margin-bottom: 16px; flex-wrap: wrap;
    .stat-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 8px; flex: 1; min-width: 520px; }
    .stat-card { background: #fafafa; border: 1px solid #eee; border-radius: 8px; padding: 10px; text-align: center;
      .stat-num { font-size: 20px; font-weight: 700; color: #1890ff; }
      .stat-lbl { font-size: 12px; color: #888; margin-top: 2px; } }
    .entity-context { min-width: 280px; border: 1px solid #efdbff; border-radius: 8px; padding: 10px; background: #f9f0ff;
      .ec-head { display: flex; justify-content: space-between; align-items: center; font-weight: 600; color: #531dab; margin-bottom: 6px; }
      .ec-empty { color: #999; font-size: 12px; }
      .ec-body { display: flex; flex-wrap: wrap; gap: 4px; .ec-overall { width: 100%; margin: 4px 0; font-size: 12px; } } }
  }

  .flow-diagram {
    display: flex; align-items: center; gap: 8px; padding: 10px 12px; background: #f6ffed;
    border: 1px solid #d9f7be; border-radius: 8px; margin-bottom: 16px; flex-wrap: wrap;
    .flow-node { display: flex; align-items: center; gap: 4px; padding: 4px 10px; background: #fff; border: 1px solid #eee; border-radius: 6px;
      &.active { border-color: #531dab; color: #531dab; } }
    .flow-arrow { color: #bbb; }
  }

  .main-layout { display: flex; gap: 16px; align-items: flex-start; }
  .cycle-directory {
    width: 180px; flex-shrink: 0; border: 1px solid #eee; border-radius: 8px; padding: 8px; position: sticky; top: 8px;
    .dir-title { font-weight: 600; margin-bottom: 6px; color: #531dab; }
    .dir-item { display: flex; align-items: center; gap: 6px; padding: 5px 6px; border-radius: 6px; cursor: pointer; font-size: 12px;
      &:hover { background: #f5f5f5; } &.active { background: #efdbff; }
      &.na { opacity: 0.5; }
      .dir-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
      .dir-name { flex: 1; } .dir-code { color: #aaa; } }
  }
  .cycle-main { flex: 1; min-width: 0; }

  .cycle-cards { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px; margin-bottom: 16px; }
  .cycle-card {
    border: 1px solid #eee; border-left: 4px solid #1890ff; border-radius: 8px; padding: 10px; cursor: pointer; background: #fff;
    &:hover { box-shadow: 0 2px 8px rgba(0,0,0,.08); } &.selected { box-shadow: 0 0 0 2px #d3adf7; } &.na { opacity: 0.55; }
    .cc-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px; .cc-name { font-weight: 600; } }
    .cc-meta { display: flex; align-items: center; gap: 8px; font-size: 12px; color: #888; margin-bottom: 6px; }
  }

  .cycle-detail { border: 1px solid #eee; border-radius: 10px; padding: 12px; background: #fcfcfc;
    .cd-titlebar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
    .cd-mode { display: flex; align-items: center; gap: 8px; }
    .cd-title { margin: 0; color: #531dab; }
    .cd-block { margin-bottom: 12px; }
    :deep(.el-card__header) { padding: 8px 12px; font-weight: 600; border-left: 3px solid #722ed1; background: linear-gradient(90deg,#f9f0ff,#fff); }
    :deep(.el-card__body) { padding: 12px; }
    .sub-table { margin-top: 12px;
      .sub-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;
        .sub-title { font-size: 12px; font-weight: 600; color: #555; }
        .sub-actions { display: flex; align-items: center; gap: 6px; } } }
    .wcgw-tip { font-size: 12px; color: #ad6800; background: #fffbe6; border-left: 3px solid #ffe58f; padding: 6px 10px; border-radius: 4px; margin-bottom: 8px; }
    .oo-container { min-height: 480px; border: 1px solid #eee; border-radius: 8px; overflow: hidden; }
    .block-head { display: flex; justify-content: space-between; align-items: center; }
    .field-row { margin-bottom: 8px; label { display: block; font-size: 12px; color: #666; margin-bottom: 4px; } }
    .matrix-table :deep(.el-table__cell) { padding: 2px 4px; }
    .def-hint { margin-bottom: 6px; }
    .linkage .lk-row { margin-bottom: 6px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
    .cross-refs { margin-top: 8px; display: flex; align-items: center; gap: 6px; flex-wrap: wrap; .cr-label { color: #666; } }
    .conc-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
    .override-reason { font-size: 12px; color: #faad14; margin-bottom: 8px; }
  }

  .review-section { margin-top: 16px; border: 1px solid #eee; border-radius: 8px; padding: 12px;
    .rv-head { font-weight: 600; margin-bottom: 8px; }
    .rv-pending { background: #fffbe6; border: 1px solid #ffe58f; border-radius: 6px; padding: 8px; margin-bottom: 10px; font-size: 12px;
      .rv-pending-title { font-weight: 600; margin-bottom: 4px; } ul { margin: 0; padding-left: 18px; } } }

  .attachment-section { margin-top: 16px; border: 1px solid #d8b8ee; border-radius: 12px; overflow: hidden;
    .attach-head { display: flex; justify-content: space-between; padding: 12px 16px; background: linear-gradient(135deg,#f9f0ff,#efdbff);
      cursor: pointer; font-weight: 500; color: #531dab; } }
}

@media print {
  .gt-b23 {
    .toolbar, .cycle-directory, .attachment-section, .review-section .el-button { display: none !important; }
    .cycle-card, .stat-card { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
  }
}
</style>
