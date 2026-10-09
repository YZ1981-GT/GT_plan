<script setup lang="ts">
/**
 * D4TabOverseas — D4-26 境外销售收入检查（两级表头，14 主 + 5 子）
 *
 * 5 个二级列为 checkbox，父组「核查程序执行情况」用嵌套 el-table-column 渲染
 * （DOM 可观测跨 5 列，Property 24/25）；差异 = 确认金额 − 本期金额（任一空→空）；
 * 占比 = 行值/合计；本期销售金额表间提取。
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
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { useIpoChecklistTab } from './useIpoChecklistTab'
import type { ChecklistColumnSpec } from './ipoChecklistSchema'
import { useD4SyncMode, D4_SYNC_ENTRY_ID } from '../composables/useD4SyncMode'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'imported'): void }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const {
  columns, rows, auditNote, auditConclusion,
  addRow, removeRow, updateCell, updateNote, updateConclusion, flushPendingSave, reloadHost,
  refreshInterSheet, fetching, fetchError, hasInterSheet,
} = useIpoChecklistTab({
  sheetCode: 'D4-26',
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// 两级表头分段：连续 group 相同的列聚为一组；group=null 的列各自独立。
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

// ─── D4-26 sync bridge（统一走 useD4SyncMode，见其文件头注释） ─────────
// 🔴 迁移前该文件完全没有健康检查（modeOptions disabled 只判 isReadonly/syncBusy）；
//    useD4SyncMode 内置 ooHealthy 门禁，迁移新增该保护（同 D4-25/27/28/29/12 系列裁定，
//    行为等价改进：OO 服务未就绪时不再无声尝试切换，而是 fail-visible）。
// 🔴 sheetKey 必须走具名常量（非内联字面量）：跨语言契约守卫
// test_d4_ipo_checklist_cross_lang_contract.py 靠正则抓这个常量声明反查后端 sheet_key
// 是否漂移，内联字面量会让该守卫失明（AssertionError 已验证复现）。
const D4_26_SHEET_KEY = 'd4-26-managed'
const { syncBridge, descriptor: syncOoDescriptor, editorMode, modeOptions, syncHostRef } = useD4SyncMode({
  sheetKey: D4_26_SHEET_KEY,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  views: ['表格视图'],
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_SYNC_ENTRY_ID })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_26_SHEET_KEY }
  },
  reloadHtml: async () => { await reloadHost() },
})
const syncFeedbackOk = computed(() => (syncBridge.feedback.value.kind === 'success' ? syncBridge.feedback.value.message : ''))
const syncFeedbackErr = computed(() => (syncBridge.feedback.value.kind === 'error' ? syncBridge.feedback.value.message : ''))

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
      relatedContext: { task: '基于境外销售收入检查(D4-26)结果生成审计说明', rowCount: rows.value.length },
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
      relatedContext: { task: '基于境外销售收入检查结果生成审计结论', noteText: auditNote.value },
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
/** 「刷新取数」：按客户名称从账面重取本期销售金额（覆盖当前值）。 */
async function handleRefreshInterSheet() {
  if (props.isReadonly) return
  const { filled, failed } = await refreshInterSheet({ overwrite: true })
  if (failed > 0) ElMessage.warning(`取数完成：回填 ${filled} 项，失败 ${failed} 项（失败项保留原值）`)
  else if (filled > 0) ElMessage.success(`已从账面回填 ${filled} 项`)
  else ElMessage.info('账面无匹配数据（已保持空值，未写入 0）')
}

function handleExportTemplate() { exportTemplate('D4-26') }
function handleExportData() { exportData('D4-26') }
async function handleImportClick() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx'
  input.onchange = async () => { const f = input.files?.[0]; if (f) await importData('D4-26', f) }
  input.click()
}
async function handleImportFile(f: any) {
  const ok = await importData('D4-26', f.raw || f)
  if (!ok) return
  await reloadHost()
  emit('imported')
}

function alignOf(col: ChecklistColumnSpec) {
  if (col.type === 'amount' || col.type === 'number' || col.type === 'percent') return 'right'
  if (col.type === 'checkbox' || col.type === 'select' || col.seqColumn) return 'center'
  return 'left'
}

defineExpose({ handleExportTemplate, handleExportData, handleImportClick })
</script>

<template>
<div class="d4-overseas">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-button
        v-if="hasInterSheet" size="small" :loading="fetching" :disabled="isReadonly"
        title="按客户名称从账面（辅助余额表）重取金额列；账面无匹配保持空值，不写 0"
        @click="handleRefreshInterSheet"
      >🔄 刷新取数</el-button>
      
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-26-overseas')">复核</el-button>
    </div>
  </div>

  <el-alert v-if="syncFeedbackErr" type="error" :closable="false" show-icon class="sync-alert" :title="'同步失败：' + syncFeedbackErr" />
  <el-alert v-else-if="syncFeedbackOk" type="success" :closable="false" show-icon class="sync-alert" :title="syncFeedbackOk" />
  <!-- 取数失败 fail-visible：不吞成静默，也绝不把失败写成 0 -->
  <el-alert v-if="fetchError" type="warning" :closable="false" show-icon class="sync-alert" :title="fetchError" />

  <template v-if="editorMode !== '在线编辑'">
    <div class="methodology-strip">
      <span class="methodology-label">编制说明：</span>
      境外销售须核查客户目的国/产品/业务模式/贸易条款，并勾选已执行的核查程序（实地走访/交易函证/海关函证/核对报关单/电子口岸数据查询）；差异 = 核查确认金额 − 本期金额自动计算。
    </div>

    <el-table :data="rows" border stripe class="overseas-table">
      <template v-for="seg in headerSegments" :key="seg.group || seg.cols[0].key">
        <el-table-column v-if="seg.group" :label="seg.group" align="center">
          <el-table-column v-for="col in seg.cols" :key="col.key" :label="col.label" :width="col.width || 80" align="center">
            <template #default="{ row }">
              <el-checkbox :model-value="!!row[col.key]" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-else :label="seg.cols[0].label" :min-width="seg.cols[0].width || 100" :align="alignOf(seg.cols[0])">
          <template #default="{ row, $index }">
            <span v-if="seg.cols[0].seqColumn">{{ $index + 1 }}</span>
            <span v-else-if="seg.cols[0].derived" class="derived-cell" title="该列为计算列">
              {{ seg.cols[0].type === 'percent' ? (row[seg.cols[0].key] == null ? '—' : (row[seg.cols[0].key] * 100).toFixed(2) + '%') : (row[seg.cols[0].key] == null ? '—' : row[seg.cols[0].key]) }}
            </span>
            <el-select v-else-if="seg.cols[0].type === 'select'" v-model="row[seg.cols[0].key]" size="small" :disabled="isReadonly" placeholder="—" clearable @change="(v) => updateCell(row.rowId, seg.cols[0].key, v)">
              <el-option v-for="opt in seg.cols[0].options" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <WpAmountInput v-else-if="seg.cols[0].type === 'amount'" v-model="row[seg.cols[0].key]" size="small" :disabled="isReadonly" style="width:100%" @change="(v) => updateCell(row.rowId, seg.cols[0].key, v)" />
            <el-input v-else v-model="row[seg.cols[0].key]" size="small" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, seg.cols[0].key, v)" />
          </template>
        </el-table-column>
      </template>
      <el-table-column label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="addRow"><el-icon :size="14"><Plus /></el-icon> 添加境外客户</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions">
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">AI辅助说明</el-button></el-tooltip>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">AI辅助结论</el-button></el-tooltip>
      </div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录境外销售检查中发现的异常情况" @input="(v) => updateNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断境外销售收入的真实性" @input="(v) => updateConclusion(v)" /></div>
      </div>
    </el-card>
  </template>

  <template v-else>
    <div class="oo-container">
      <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      <div v-else class="oo-loading">正在打开 D4-26 同步编辑器…</div>
    </div>
  </template>
</div>
</template>

<style scoped>
.d4-overseas{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}
.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sync-alert{margin-bottom:12px}
.methodology-strip{margin-bottom:14px;padding:10px 14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0;font-size:12px;color:#606266;line-height:1.7}
.methodology-label{font-weight:600;color:#b88230}
.overseas-table{font-size:12px}.overseas-table :deep(.el-table__cell){padding:4px 3px}
.derived-cell{color:#409eff;font-weight:600;border-bottom:1px dashed #a0cfff;cursor:help}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}
.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}
.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
.oo-loading{padding:40px;text-align:center;color:#909399}
</style>
