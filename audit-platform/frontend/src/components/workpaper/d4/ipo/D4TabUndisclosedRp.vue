<script setup lang="ts">
/**
 * D4TabUndisclosedRp — D4-27 识别未披露的关联方（单级表头，18 列）
 *
 * 10 个身份属性列为 checkbox；总计列 = SUM(10 列勾选数) 为派生列（源模板 M15=SUM(C15:L15)）；
 * 年度销售额表间提取；双模式回写走平台桥。源模板示例行（陈XX/李YY）不作默认种子。
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
  refreshInterSheet, fetching, fetchError, hasInterSheet,
} = useIpoChecklistTab({
  sheetCode: 'D4-27',
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const matchCount = computed(() => rows.value.filter((r) => r.isDuplicateName === 'Y').length)
const totalSales = computed(() => rows.value.reduce((s, r) => s + (Number(r.annualSales) || 0), 0))

// ─── D4-27 专用 sync bridge ──────────────────────────────────────────
const D4_27_ENTRY = 'xlsx/gt-d4-operating-revenue'
const D4_27_SHEET_KEY = 'd4-27-managed'
const syncSwitching = ref(false)
const syncHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)
const entryId = ref(D4_27_ENTRY)
const sheetKey = ref(D4_27_SHEET_KEY)
const syncBridge = useWorkpaperSyncBridge({
  entryId,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  sheetKey,
  capability: capabilityForEntry(D4_27_ENTRY),
  flushHtml: async () => {
    flushPendingSave()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_27_ENTRY })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_27_SHEET_KEY }
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
      relatedContext: { task: '基于识别未披露关联方(D4-27)的比对结果生成审计说明', rowCount: rows.value.length, matchCount: matchCount.value },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateNote(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false }
}
async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion', existingContent: auditConclusion.value,
      relatedContext: { task: '基于关联方识别结果生成审计结论', noteText: auditNote.value, matchCount: matchCount.value },
    }, { _silent: true } as any)
    const t = res.data?.data?.content ?? res.data?.content ?? ''
    if (!t) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(t, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateConclusion(t)
  } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId), projectId: computed(() => props.projectId),
})
/** 「刷新取数」：按姓名从账面重取年度销售额（覆盖当前值）。 */
async function handleRefreshInterSheet() {
  if (props.isReadonly) return
  const { filled, failed } = await refreshInterSheet({ overwrite: true })
  if (failed > 0) ElMessage.warning(`取数完成：回填 ${filled} 项，失败 ${failed} 项（失败项保留原值）`)
  else if (filled > 0) ElMessage.success(`已从账面回填 ${filled} 项`)
  else ElMessage.info('账面无匹配数据（已保持空值，未写入 0）')
}

function handleExportTemplate() { exportTemplate('D4-27') }
function handleExportData() { exportData('D4-27') }
async function handleImportFile(f: any) {
  const ok = await importData('D4-27', f.raw || f)
  if (!ok) return
  await reloadHost()
  emit('imported')
}

function rowClassName({ row }: { row: any }) { return row.isDuplicateName === 'Y' ? 'row-match' : '' }
</script>

<template>
<div class="d4-undisclosed-rp">
  <div class="toolbar">
    <div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div>
    <div class="toolbar-right">
      <el-button
        v-if="hasInterSheet" size="small" :loading="fetching" :disabled="isReadonly"
        title="按姓名从账面（辅助余额表）重取年度销售额；账面无匹配保持空值，不写 0"
        @click="handleRefreshInterSheet"
      >🔄 刷新取数</el-button>
      <el-dropdown trigger="click" size="small">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown><el-dropdown-menu>
          <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
          <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
          <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item>
        </el-dropdown-menu></template>
      </el-dropdown>
      <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
      <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-27-rp')">复核</el-button>
    </div>
  </div>

  <el-alert v-if="syncFeedbackErr" type="error" :closable="false" show-icon class="sync-alert" :title="'同步失败：' + syncFeedbackErr" />
  <el-alert v-else-if="syncFeedbackOk" type="success" :closable="false" show-icon class="sync-alert" :title="syncFeedbackOk" />
  <!-- 取数失败 fail-visible：不吞成静默，也绝不把失败写成 0 -->
  <el-alert v-if="fetchError" type="warning" :closable="false" show-icon class="sync-alert" :title="fetchError" />

  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ rows.length }}<span class="stat-unit">人</span></div><div class="stat-label">比对人数</div></div>
    <div class="stat-card" :class="matchCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ matchCount }}<span class="stat-unit">人</span></div><div class="stat-label">重名匹配</div></div>
    <div class="stat-card stat-amount"><div class="stat-value">{{ displayPrefs.fmtAmount(totalSales) }}</div><div class="stat-label">涉及销售额</div></div>
  </div>

  <template v-if="editorMode !== 'onlyoffice'">
    <details class="methodology-collapse">
      <summary class="methodology-summary">审计目标与识别未披露关联方过程（点击展开）</summary>
      <div class="methodology-body">
        <p><strong>一、审计目标：</strong>主要或异常客户是否与被审计单位存在关联方关系。</p>
        <p><strong>二、审计过程：</strong></p>
        <p class="method-step"><span class="step-num">1</span>选择大额、异常的客户或交易。</p>
        <p class="method-step"><span class="step-num">2</span>查询客户工商、银行、税务信息，关注地址、董监高、联系方式，与发票/网站信息核对识别疑似关联关系。</p>
        <p class="method-step"><span class="step-num">3</span>选取重要客户，获取关联方关系确认函。</p>
        <p class="method-step"><span class="step-num">4</span>取得实控人/董高监及密切家庭成员对外投资清单，与重要客户股东/关键经办人比对。</p>
        <p class="method-step"><span class="step-num">5</span>取得保荐机构/PE等利益相关方清单与重要客户比对。</p>
        <p class="method-step"><span class="step-num">6</span>获取主要股东/董监高/利益相关方确认函，确认除薪酬/分红外无任何形式交易。</p>
      </div>
    </details>

    <el-table :data="rows" border stripe class="rp-table" :row-class-name="rowClassName">
      <el-table-column v-for="col in columns" :key="col.key" :label="col.label" :min-width="col.width || 80"
        :align="col.type === 'amount' || col.type === 'number' || col.type === 'percent' ? 'right' : (col.type === 'checkbox' || col.type === 'select' || col.seqColumn ? 'center' : 'left')"
        :class-name="col.type === 'checkbox' ? 'col-check' : ''">
        <template #default="{ row, $index }">
          <span v-if="col.seqColumn">{{ $index + 1 }}</span>
          <span v-else-if="col.derived" class="derived-cell" title="该列为计算列（总计=各身份属性勾选数之和）">{{ row[col.key] == null ? '—' : row[col.key] }}</span>
          <el-select v-else-if="col.type === 'select'" v-model="row[col.key]" size="small" :disabled="isReadonly" placeholder="—" clearable @change="(v) => updateCell(row.rowId, col.key, v)">
            <el-option v-for="opt in col.options" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-checkbox v-else-if="col.type === 'checkbox'" :model-value="!!row[col.key]" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
          <WpAmountInput v-else-if="col.type === 'amount'" v-model="row[col.key]" size="small" :disabled="isReadonly" style="width:100%" @change="(v) => updateCell(row.rowId, col.key, v)" />
          <el-input v-else v-model="row[col.key]" size="small" :disabled="isReadonly" @change="(v) => updateCell(row.rowId, col.key, v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55" fixed="right" align="center">
        <template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.rowId)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template>
      </el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="addRow"><el-icon :size="14"><Plus /></el-icon> 添加人员</el-button></div>

    <el-card class="audit-opinion-card" shadow="never">
      <template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions">
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">AI辅助说明</el-button></el-tooltip>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">AI辅助结论</el-button></el-tooltip>
      </div></div></template>
      <div class="opinion-body">
        <div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:4,maxRows:15}" :model-value="auditNote" :disabled="isReadonly" placeholder="1.公司主要股东/高管/家属/员工名单 2.客户法人及关键管理人员 3.比对结果 4.身份核对结果" @input="(v) => updateNote(v)" /></div>
        <div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断是否识别出重要客户与公司存在关联方关系" @input="(v) => updateConclusion(v)" /></div>
      </div>
    </el-card>
  </template>

  <template v-else>
    <div class="oo-container">
      <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
      <div v-else class="oo-loading">正在打开 D4-27 同步编辑器…</div>
    </div>
  </template>
</div>
</template>

<style scoped>
.d4-undisclosed-rp{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}
.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sync-alert{margin-bottom:12px}
.stats-dashboard{display:flex;gap:12px;margin-bottom:20px;padding:14px 18px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}
.stat-card{padding:10px 16px;min-width:110px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}
.stat-card.stat-primary{border-left:3px solid #409eff}.stat-card.stat-warn{border-left:3px solid #f56c6c}.stat-card.stat-ok{border-left:3px solid #67c23a}.stat-card.stat-amount{border-left:3px solid #e6a23c}
.stat-value{font-size:18px;font-weight:700;color:#303133;font-variant-numeric:tabular-nums}.stat-unit{font-size:12px;font-weight:400;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}
.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}
.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}
.method-step{margin-bottom:6px}.step-num{display:inline-block;background:#e6a23c;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px;min-width:16px;text-align:center}
.rp-table{font-size:12px}.rp-table :deep(.el-table__cell){padding:4px 2px}.rp-table :deep(.row-match td){background-color:#fef0f0 !important}
.rp-table :deep(.col-check .el-table__cell){background-color:#f0f9eb !important}
.derived-cell{color:#409eff;font-weight:600;border-bottom:1px dashed #a0cfff;cursor:help}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}
.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}
.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
.oo-loading{padding:40px;text-align:center;color:#909399}
</style>
