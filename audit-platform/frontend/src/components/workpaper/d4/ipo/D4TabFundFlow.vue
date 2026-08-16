<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabFundFlow — D4-32 客户、供应商等资金流水检查
 *
 * 6组动态行表格（主要供应商/主要客户/控股股东/实际控制人/关键管理人员/其他关联方）
 * 每组共享9列：序号/单位名称/本期交易金额/占比/开户银行/账号/获取途径/是否异常/索引号
 * 异常行红色高亮 + AI辅助 + 双模式OO + 导入导出
 */
import { ref, computed, inject, watch, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Types ───────────────────────────────────────────────────────────
const GROUPS = [
  { key: 'supplier', label: '主要供应商', color: '#f0faf0' },
  { key: 'customer', label: '主要客户', color: '#f0f5ff' },
  { key: 'shareholder', label: '控股股东', color: '#faf5ff' },
  { key: 'controller', label: '实际控制人', color: '#fdf6ec' },
  { key: 'management', label: '关键管理人员', color: '#fef0f0' },
  { key: 'related', label: '其他关联方', color: '#f5f5f5' },
]

interface FlowRow {
  id: string; name: string; amount: number | string; ratio: string
  bank: string; account: string; method: string; hasAnomaly: string; indexRef: string
}
interface GroupData { key: string; rows: FlowRow[] }

const groups = ref<GroupData[]>(GROUPS.map(g => ({ key: g.key, rows: [] })))
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name?: string): FlowRow {
  return { id: `ff-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, name: name || '', amount: '', ratio: '', bank: '', account: '', method: '', hasAnomaly: '', indexRef: '' }
}

function loadData() {
  const r = props.allResponses.get('D4-32-groups')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p) && p.length === 6) { groups.value = p; return } } catch {} }
  groups.value = GROUPS.map(g => ({ key: g.key, rows: [] }))
}
function loadNote() { auditNote.value = props.allResponses.get('D4-32-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-32-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-32-groups')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-32-note')?.remark, loadNote, { immediate: true })

async function addRow(groupKey: string) {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入单位名称或姓名', '添加检查对象', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' })
    if (value?.trim()) { const g = groups.value.find(x => x.key === groupKey); if (g) { g.rows.push(createRow(value.trim())); persistAll() } }
  } catch {}
}
function removeRow(groupKey: string, rowId: string) { if (props.isReadonly) return; const g = groups.value.find(x => x.key === groupKey); if (g) { g.rows = g.rows.filter(r => r.id !== rowId); persistAll() } }
function updateCell(groupKey: string, rowId: string, field: keyof FlowRow, value: any) { if (props.isReadonly) return; const g = groups.value.find(x => x.key === groupKey); if (!g) return; const row = g.rows.find(r => r.id === rowId); if (row) { (row as any)[field] = value; persistAll() } }

function persistAll() {
  props.allResponses.set('D4-32-groups', { item_id: 'D4-32-groups', conclusion: null, remark: JSON.stringify(groups.value) })
  props.allResponses.set('D4-32-note', { item_id: 'D4-32-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-32-conclusion', { item_id: 'D4-32-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-32-groups','D4-32-note','D4-32-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-32-groups','D4-32-note','D4-32-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const totalRows = groups.value.reduce((s, g) => s + g.rows.length, 0); const anomalyCount = groups.value.reduce((s, g) => s + g.rows.filter(r => r.hasAnomaly === '是').length, 0); const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于资金流水检查(D4-32)结果生成审计说明', totalRows, anomalyCount } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于资金流水检查结果生成审计结论', noteText: auditNote.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// Stats
const totalRows = computed(() => groups.value.reduce((s, g) => s + g.rows.length, 0))
const anomalyCount = computed(() => groups.value.reduce((s, g) => s + g.rows.filter(r => r.hasAnomaly === '是').length, 0))

function rowClassName({ row }: { row: FlowRow }) { return row.hasAnomaly === '是' ? 'row-anomaly' : '' }
</script>

<template>
<div class="d4-fund-flow">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-32')">导出模板</el-dropdown-item><el-dropdown-item @click="exportData('D4-32')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-32',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:E1-31" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-32-fund')">💬 复核</el-button></div></div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ totalRows }}<span class="stat-unit">条</span></div><div class="stat-label">检查记录</div></div>
    <div class="stat-card" :class="anomalyCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ anomalyCount }}<span class="stat-unit">条</span></div><div class="stat-label">发现异常</div></div>
  </div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 方法论 -->
    <details class="methodology-collapse">
      <summary class="methodology-summary">📖 审计目标与资金流水检查过程（点击展开）</summary>
      <div class="methodology-body">
        <p><strong>审计目标：</strong>利润表中记录的营业收入已发生，且与被审计单位有关，已记录于恰当的账户。</p>
        <p><strong>审计过程：</strong></p>
        <p class="method-step"><span class="step-num">1</span>获取被审计单位主要供应商、客户资金流水，检查是否与被审计单位控股股东、实际控制人以及其他关联方存在大额资金往来，如有，应确定该等资金往来是否与被审计单位收入舞弊有关。</p>
        <p class="method-step"><span class="step-num">2</span>获取被审计单位控股股东、实际控制人、关键管理人员以及其他关联方银行账户资金流水，检查是否存在前述各方提供资金配合被审计单位虚构收入的情况。</p>
      </div>
    </details>

    <!-- ═══ 6组表格 ═══ -->
    <div v-for="(group, gIdx) in GROUPS" :key="group.key" class="group-section" :style="{ borderLeftColor: group.color }">
      <div class="group-header">
        <span class="group-title">{{ group.label }}</span>
        <el-button size="small" :disabled="isReadonly" @click="addRow(group.key)"><el-icon :size="12"><Plus /></el-icon> 添加</el-button>
      </div>
      <el-table v-if="groups[gIdx].rows.length" :data="groups[gIdx].rows" border stripe size="small" class="flow-table" :row-class-name="rowClassName">
        <el-table-column label="#" width="40" align="center"><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
        <el-table-column label="单位名称/姓名" min-width="110"><template #default="{ row }"><el-input v-model="row.name" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'name',row.name)" /></template></el-table-column>
        <el-table-column label="本期交易金额" min-width="110" align="right"><template #default="{ row }"><WpAmountInput v-model="row.amount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(group.key,row.id,'amount',row.amount)" /></template></el-table-column>
        <el-table-column label="占比" width="70"><template #default="{ row }"><el-input v-model="row.ratio" size="small" :disabled="isReadonly" placeholder="%" @change="updateCell(group.key,row.id,'ratio',row.ratio)" /></template></el-table-column>
        <el-table-column label="开户银行" min-width="100"><template #default="{ row }"><el-input v-model="row.bank" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'bank',row.bank)" /></template></el-table-column>
        <el-table-column label="账号" min-width="120"><template #default="{ row }"><el-input v-model="row.account" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'account',row.account)" /></template></el-table-column>
        <el-table-column label="获取途径" min-width="90"><template #default="{ row }"><el-input v-model="row.method" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'method',row.method)" /></template></el-table-column>
        <el-table-column label="异常" width="65" align="center"><template #default="{ row }"><el-select v-model="row.hasAnomaly" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(group.key,row.id,'hasAnomaly',row.hasAnomaly)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
        <el-table-column label="索引" width="65"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(group.key,row.id,'indexRef',row.indexRef)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeRow(group.key,row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
      </el-table>
      <div v-else class="group-empty">暂无记录，点击"添加"按钮新增检查对象</div>
    </div>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录资金流水检查中发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断是否存在资金配合虚构收入的情况" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="客户、供应商等资金流水检查D4-32" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-fund-flow{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:16px;padding:12px 16px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:8px 14px;min-width:100px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-card.stat-warn{border-left:3px solid #f56c6c}.stat-card.stat-ok{border-left:3px solid #67c23a}.stat-value{font-size:18px;font-weight:700;color:#303133}.stat-unit{font-size:12px;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-step{margin-bottom:6px}.step-num{display:inline-block;background:#e6a23c;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px}
.group-section{margin-bottom:16px;border-left:3px solid #e4e7ed;padding-left:12px;border-radius:0 6px 6px 0}
.group-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:8px}.group-title{font-size: var(--wp-font-size, 13px);font-weight:600;color:#303133}
.flow-table{font-size: var(--wp-font-size, 13px)}.flow-table :deep(.el-table__cell){padding:4px 3px}.flow-table :deep(.row-anomaly td){background-color:#fef0f0 !important}
.group-empty{padding:12px;text-align:center;font-size:12px;color:#c0c4cc;background:#fafbfc;border-radius:4px;border:1px dashed #e4e7ed}
.audit-opinion-card{margin-top:20px;margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
