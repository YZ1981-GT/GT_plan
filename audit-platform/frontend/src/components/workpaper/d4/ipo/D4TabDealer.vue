<script setup lang="ts">
/**
 * D4TabDealer — D4-25 经销商检查（单级表头，13 列）
 *
 * 列规格驱动渲染（ipoChecklistSchema.SHEET_SPECS['D4-25']）；双模式回写走平台
 * useWorkpaperSyncBridge + WorkpaperSyncEditorHost（参照 D4-5 canary）；
 * 表间提取（本期销售金额/期末应收账款余额）+ 表内计算（占同类交易比例）走公式真源。
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

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'imported'): void }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const {
  columns, rows, auditNote, auditConclusion,
  addRow, removeRow, updateCell, updateNote, updateConclusion, flushPendingSave, reloadHost,
} = useIpoChecklistTab({
  sheetCode: 'D4-25',
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── D4-25 专用 sync bridge（复用父级 D4 workbook 的 bidirectional 入口）──────
const D4_25_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_25_SHEET_KEY = 'd4-25-managed'
const syncSwitching = ref(false)
const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const entryId = ref(D4_25_ENTRY)
const sheetKey = ref(D4_25_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey,
  capability: capabilityForEntry(D4_25_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: D4_25_ENTRY,
    })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_25_SHEET_KEY }
  },
  reloadHtml: async () => { await reloadHost() },
})
const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(
  () =>
    syncSwitching.value
    || (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncFeedbackOk = computed(() =>
  syncBridge.feedback.value.kind === 'success' ? syncBridge.feedback.value.message : '',
)
const syncFeedbackErr = computed(() =>
  syncBridge.feedback.value.kind === 'error' ? syncBridge.feedback.value.message : '',
)

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
    if (target === 'onlyoffice') {
      if (props.isReadonly) return
      await syncBridge.switchToOnlyOffice()
    } else {
      await syncBridge.switchToHtml()
    }
  } catch {
    // 失败已由桥写入 feedback（syncFeedbackErr 展示真实原因）；请求被去重层取消
    // （切页签竞态）时桥已内部退回 html_idle。这里一律吞掉，避免 rethrow 变成
    // 未捕获 Promise rejection（控制台红字 CanceledError）。
  } finally {
    syncSwitching.value = false
  }
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
      relatedContext: { task: '基于经销商检查(D4-25)结果生成审计说明', rowCount: rows.value.length },
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
      relatedContext: { task: '基于经销商检查结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}

// ─── 导入导出（导入成功后 reload 宿主 allResponses，AC 4.2）──────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId), projectId: computed(() => props.projectId),
})
function handleExportTemplate() { exportTemplate('D4-25') }
function handleExportData() { exportData('D4-25') }
async function handleImportFile(f: any) {
  const ok = await importData('D4-25', f.raw || f)
  if (!ok) return
  await reloadHost()
  emit('imported')
}
</script>

<template>
<div class="d4-dealer">
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
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-25-dealer')">复核</el-button>
    </div>
  </div>

  <el-alert v-if="syncFeedbackErr" type="error" :closable="false" show-icon class="sync-alert" :title="'同步失败：' + syncFeedbackErr" />
  <el-alert v-else-if="syncFeedbackOk" type="success" :closable="false" show-icon class="sync-alert" :title="syncFeedbackOk" />

  <template v-if="editorMode !== 'onlyoffice'">
    <div class="guide-strip"><span class="guide-strip-label">编制流程：</span>
      <el-tooltip content="关注经销商基本情况是否与销售规模匹配" placement="bottom" :show-after="300"><span class="guide-chip">①客户匹配</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="记录经销商情况(关联方/法人类型/费用承担/返利)" placement="bottom" :show-after="300"><span class="guide-chip">②记录信息</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="比对终端销售金额与经销商采购金额" placement="bottom" :show-after="300"><span class="guide-chip">③终端核对</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="分析合理性，形成审计结论" placement="bottom" :show-after="300"><span class="guide-chip">④分析结论</span></el-tooltip>
    </div>

    <el-table :data="rows" border stripe class="dealer-table">
      <el-table-column v-for="col in columns" :key="col.key" :label="col.label" :min-width="col.width || 100"
        :align="col.type === 'amount' || col.type === 'number' || col.type === 'percent' ? 'right' : (col.type === 'checkbox' || col.type === 'select' || col.seqColumn ? 'center' : 'left')">
        <template #default="{ row, $index }">
          <span v-if="col.seqColumn">{{ $index + 1 }}</span>
          <span v-else-if="col.derived" class="derived-cell" title="该列为计算列（自动汇总）">
            {{ col.type === 'percent' ? (row[col.key] == null ? '—' : (row[col.key] * 100).toFixed(2) + '%') : (row[col.key] == null ? '—' : row[col.key]) }}
          </span>
          <el-select v-else-if="col.type === 'select'" v-model="row[col.key]" size="small" :disabled="isReadonly" placeholder="—" clearable @change="(v) => updateCell(row.rowId, col.key, v)">
            <el-option v-for="opt in col.options" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-checkbox v-else-if="col.type === 'checkbox'" :model-value="!!row[col.key]" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
          <WpAmountInput v-else-if="col.type === 'amount'" v-model="row[col.key]" size="small" :disabled="isReadonly" style="width:100%" @change="(v) => updateCell(row.rowId, col.key, v)" />
          <el-input v-else v-model="row[col.key]" size="small" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right" align="center">
        <template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="addRow"><el-icon :size="14"><Plus /></el-icon> 添加经销商</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions">
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">AI辅助说明</el-button></el-tooltip>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">AI辅助结论</el-button></el-tooltip>
      </div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录经销商销售检查中发现的异常情况" @input="(v) => updateNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断经销商销售收入的真实性" @input="(v) => updateConclusion(v)" /></div>
      </div>
    </el-card>
  </template>

  <template v-else>
    <div class="oo-container">
      <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      <div v-else class="oo-loading">正在打开 D4-25 同步编辑器…</div>
    </div>
  </template>
</div>
</template>

<style scoped>
.d4-dealer{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}
.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sync-alert{margin-bottom:12px}
.guide-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}
.guide-strip-label{font-weight:600;color:#67c23a;font-size:12px}
.guide-chip{background:#fff;border:1px solid #c2e7b0;border-radius:4px;padding:2px 8px;font-size:12px;color:#529b2e;cursor:help}
.guide-arrow{color:#a8abb2;font-size:12px}
.dealer-table{font-size: var(--wp-font-size, 13px)}.dealer-table :deep(.el-table__cell){padding:5px 4px}
.derived-cell{color:#409eff;font-weight:600;border-bottom:1px dashed #a0cfff;cursor:help}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}
.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}
.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
.oo-loading{padding:40px;text-align:center;color:#909399}
</style>
