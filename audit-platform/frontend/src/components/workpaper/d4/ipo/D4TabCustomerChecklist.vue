<script setup lang="ts">
/**
 * D4TabCustomerChecklist — D4-28 客户信息核查清单（两级表头，9 主 + 5 子 + 索引号）
 *
 * 5 个二级列为 checkbox，父组「核查方式（√）」嵌套 el-table-column 渲染（DOM 跨 5 列，
 * Property 32）；三个占比列表内计算（各自分母 0 留空）；销售/应收/合同负债表间提取。
 */
import { ref, computed, inject, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  useWorkpaperSyncBridge,
  WP_BRIDGE_IN_FLIGHT_STATES,
} from '../../sync/useWorkpaperSyncBridge'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import { capabilityForEntry } from '../../sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { useIpoChecklistTab } from './useIpoChecklistTab'
import type { ChecklistColumnSpec } from './ipoChecklistSchema'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'imported'): void }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const {
  columns, rows, auditNote, auditConclusion,
  addRow, removeRow, updateCell, updateNote, updateConclusion, flushPendingSave, reloadHost,
} = useIpoChecklistTab({
  sheetCode: 'D4-28',
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

interface RenderSegment { group: string | null; cols: ChecklistColumnSpec[] }
const headerSegments = computed<RenderSegment[]>(() => {
  const segs: RenderSegment[] = []
  for (const col of columns.value) {
    const last = segs[segs.length - 1]
    if (col.group && last && last.group === col.group) last.cols.push(col)
    else segs.push({ group: col.group, cols: [col] })
  }
  return segs
})

// ─── D4-28 专用 sync bridge ──────────────────────────────────────────
const D4_28_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_28_SHEET_KEY = 'd4-28-managed'
const syncSwitching = ref(false)
const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const entryId = ref(D4_28_ENTRY)
const sheetKey = ref(D4_28_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey,
  capability: capabilityForEntry(D4_28_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_28_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_28_SHEET_KEY }
  },
  reloadHtml: async () => { await reloadHost() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () => syncSwitching.value || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncFeedbackOk = computed(() => (syncBridge.feedback.value.kind === 'success' ? syncBridge.feedback.value.message : ''))
const syncFeedbackErr = computed(() => (syncBridge.feedback.value.kind === 'error' ? syncBridge.feedback.value.message : ''))

const editorMode = computed({
  get: (): 'structured' | 'onlyoffice' => (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'structured'),
  set: (v: 'structured' | 'onlyoffice') => { void switchMode(v) },
})
const modeOptions = computed(() => [
  { label: '表格视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: props.isReadonly || syncBusy.value },
])
async function switchMode(target: 'structured' | 'onlyoffice'): Promise<void> {
  if (target === editorMode.value) return
  syncSwitching.value = true
  try {
    if (target === 'onlyoffice') { if (props.isReadonly) return; await syncBridge.switchToOnlyOffice() }
    else await syncBridge.switchToHtml()
  } catch {
    // 失败已由桥写入 feedback（syncFeedbackErr 展示真实原因）；请求被去重层取消
    // （切页签竞态）时桥已内部退回 html_idle。这里一律吞掉，避免 rethrow 变成
    // 未捕获 Promise rejection（控制台红字 CanceledError）。
  } finally { syncSwitching.value = false }
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const r = await http.get('/api/ai/health', { _silent: true } as any)
    const s = r.data?.data?.status ?? r.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()
const aiTip = computed(() => (aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用'))
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)
async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'analysis-note', existingContent: auditNote.value,
      relatedContext: { task: '基于客户信息核查清单(D4-28)结果生成审计说明', rowCount: rows.value.length },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateNote(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false }
}
async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion', existingContent: auditConclusion.value,
      relatedContext: { task: '基于客户信息核查结果生成审计结论', noteText: auditNote.value },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId), projectId: computed(() => props.projectId),
})
function handleExportTemplate() { exportTemplate('D4-28') }
function handleExportData() { exportData('D4-28') }
async function handleImportFile(f: any) {
  const ok = await importData('D4-28', f.raw || f)
  if (!ok) return
  await reloadHost()
  emit('imported')
}

function alignOf(col: ChecklistColumnSpec) {
  if (col.type === 'amount' || col.type === 'number' || col.type === 'percent') return 'right'
  if (col.type === 'checkbox' || col.type === 'select' || col.seqColumn) return 'center'
  return 'left'
}
function pctText(v: unknown): string {
  return v == null ? '—' : (Number(v) * 100).toFixed(2) + '%'
}
</script>

<template>
<div class="d4-customer-checklist">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-dropdown trigger="click" size="small">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown><el-dropdown-menu>
          <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
          <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
          <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item>
        </el-dropdown-menu></template>
      </el-dropdown>
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-28-customer-checklist')">复核</el-button>
    </div>
  </div>

  <el-alert v-if="syncFeedbackErr" type="error" :closable="false" show-icon class="sync-alert" :title="'同步失败：' + syncFeedbackErr" />
  <el-alert v-else-if="syncFeedbackOk" type="success" :closable="false" show-icon class="sync-alert" :title="syncFeedbackOk" />

  <template v-if="editorMode !== 'onlyoffice'">
    <div class="methodology-strip">
      <span class="methodology-label">编制说明：</span>
      登记客户名称与选取原因，录入销售金额/应收账款期末余额/合同负债期末余额及各自占比（占比自动计算，分母为 0 留空），并勾选核查方式（工商资料查询/互联网信息查询/函证/视频、电话访谈/实地走访）。
    </div>

    <el-table :data="rows" border stripe class="checklist-table">
      <template v-for="seg in headerSegments" :key="seg.group || seg.cols[0].key">
        <el-table-column v-if="seg.group" :label="seg.group" align="center">
          <el-table-column v-for="col in seg.cols" :key="col.key" :label="col.label" :width="col.width || 90" align="center" class-name="col-check">
            <template #default="{ row }">
              <el-checkbox :model-value="!!row[col.key]" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-else :label="seg.cols[0].label" :min-width="seg.cols[0].width || 100" :align="alignOf(seg.cols[0])">
          <template #default="{ row, $index }">
            <span v-if="seg.cols[0].seqColumn">{{ $index + 1 }}</span>
            <span v-else-if="seg.cols[0].derived" class="derived-cell" title="该列为计算列">{{ pctText(row[seg.cols[0].key]) }}</span>
            <WpAmountInput v-else-if="seg.cols[0].type === 'amount'" v-model="row[seg.cols[0].key]" size="small" :disabled="isReadonly" style="width:100%" @change="(v) => updateCell(row.rowId, seg.cols[0].key, v)" />
            <el-input v-else v-model="row[seg.cols[0].key]" size="small" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, seg.cols[0].key, v)" />
          </template>
        </el-table-column>
      </template>
      <el-table-column label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="addRow"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions">
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">AI辅助说明</el-button></el-tooltip>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">AI辅助结论</el-button></el-tooltip>
      </div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录客户信息核查中发现的异常情况" @input="(v) => updateNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断客户信息核查结论" @input="(v) => updateConclusion(v)" /></div>
      </div>
    </el-card>
  </template>

  <template v-else>
    <div class="oo-container">
      <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      <div v-else class="oo-loading">正在打开 D4-28 同步编辑器…</div>
    </div>
  </template>
</div>
</template>

<style scoped>
.d4-customer-checklist{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}
.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sync-alert{margin-bottom:12px}
.methodology-strip{margin-bottom:14px;padding:10px 14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0;font-size:12px;color:#606266;line-height:1.7}
.methodology-label{font-weight:600;color:#b88230}
.checklist-table{font-size:12px}.checklist-table :deep(.el-table__cell){padding:4px 3px}
.checklist-table :deep(.col-check .el-table__cell){background-color:#f0f9eb !important}
.derived-cell{color:#409eff;font-weight:600;border-bottom:1px dashed #a0cfff;cursor:help}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}
.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}
.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
.oo-loading{padding:40px;text-align:center;color:#909399}
</style>
