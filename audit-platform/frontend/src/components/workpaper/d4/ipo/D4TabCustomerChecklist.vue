<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabCustomerChecklist — D4-28 客户信息核查清单
 *
 * 动态行：每行一个客户，15列含多级表头
 * 基本信息(序号/客户/原因/销售额/占比/应收余额/占比/合同负债/占比) + 核查方式5子列(√) + 索引号
 * 双模式 + AI + 导入导出
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

interface ChecklistRow {
  id: string; customerName: string; reason: string
  salesAmount: number | string; salesRatio: string
  arBalance: number | string; arRatio: string
  contractLiability: number | string; clRatio: string
  checkBiz: boolean; checkInternet: boolean; checkConfirm: boolean; checkCall: boolean; checkVisit: boolean
  indexRef: string
}

const rows = ref<ChecklistRow[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name: string): ChecklistRow {
  return { id: `cl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, customerName: name, reason: '', salesAmount: '', salesRatio: '', arBalance: '', arRatio: '', contractLiability: '', clRatio: '', checkBiz: false, checkInternet: false, checkConfirm: false, checkCall: false, checkVisit: false, indexRef: '' }
}

function loadData() { const r = props.allResponses.get('D4-28-rows'); if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; return } } catch {} }; rows.value = [] }
function loadNote() { auditNote.value = props.allResponses.get('D4-28-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-28-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-28-rows')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-28-note')?.remark, loadNote, { immediate: true })

async function handleAddRow() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入客户名称', '添加核查客户', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { rows.value.push(createRow(value.trim())); persistAll() } } catch {} }
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function updateCell(id: string, field: keyof ChecklistRow, value: any) { if (props.isReadonly) return; const row = rows.value.find(r => r.id === id); if (row) { (row as any)[field] = value; persistAll() } }

function persistAll() {
  props.allResponses.set('D4-28-rows', { item_id: 'D4-28-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-28-note', { item_id: 'D4-28-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-28-conclusion', { item_id: 'D4-28-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-28-rows','D4-28-note','D4-28-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-28-rows','D4-28-note','D4-28-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)

async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于客户信息核查清单(D4-28)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于客户核查清单结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate('D4-28') }
function handleExportData() { exportData('D4-28') }
async function handleImportFile(f: any) { await importData('D4-28', f.raw || f) }

// Stats
const checkedCount = computed(() => rows.value.filter(r => r.checkBiz || r.checkInternet || r.checkConfirm || r.checkCall || r.checkVisit).length)
</script>

<template>
<div class="d4-customer-checklist">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-29" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-28-checklist')">💬 复核</el-button></div></div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ rows.length }}<span class="stat-unit">家</span></div><div class="stat-label">抽取客户</div></div>
    <div class="stat-card stat-ok"><div class="stat-value">{{ checkedCount }}<span class="stat-unit">家</span></div><div class="stat-label">已执行核查</div></div>
  </div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 方法论 -->
    <details class="methodology-collapse">
      <summary class="methodology-summary">📖 审计目标与核查过程（点击展开）</summary>
      <div class="methodology-body">
        <p><strong>审计目标：</strong>利润表中记录的营业收入已发生，且与被审计单位有关，已记录于恰当的账户。</p>
        <p><strong>审计过程：</strong></p>
        <p class="method-step"><span class="step-num">1</span>核查主要客户及交易真实性，包括调查交易对手背景和商业目的等。</p>
        <p class="method-step"><span class="step-num">2</span>对比历年主要客户清单，找出报告期新增的主要客户、原有主要客户交易额大幅减少或合作关系取消的情况，重点关注变化原因。项目组根据客户集中度和风险情况抽取客户/项目，考虑实施查询工商资料、互联网查询、电话访谈关键经办人员、实地走访客户等程序。</p>
      </div>
    </details>

    <!-- 主表格 -->
    <el-table :data="rows" border stripe class="checklist-table">
      <el-table-column label="序号" width="50" align="center" fixed><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
      <el-table-column label="客户名称" min-width="110"><template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.id,'customerName',row.customerName)" /></template></el-table-column>
      <el-table-column label="选取原因" min-width="110"><template #default="{ row }"><el-input v-model="row.reason" size="small" :disabled="isReadonly" placeholder="如：新增主要客户" @change="updateCell(row.id,'reason',row.reason)" /></template></el-table-column>
      <el-table-column label="销售金额" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.salesAmount" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'salesAmount',row.salesAmount)" /></template></el-table-column>
      <el-table-column min-width="60"><template #header><el-tooltip content="占总交易比重" placement="top"><span>占比</span></el-tooltip></template><template #default="{ row }"><el-input v-model="row.salesRatio" size="small" :disabled="isReadonly" placeholder="%" @change="updateCell(row.id,'salesRatio',row.salesRatio)" /></template></el-table-column>
      <el-table-column label="应收余额" min-width="100" align="right"><template #default="{ row }"><WpAmountInput v-model="row.arBalance" size="small" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'arBalance',row.arBalance)" /></template></el-table-column>
      <el-table-column min-width="60"><template #header><el-tooltip content="占期末余额比重" placement="top"><span>占比</span></el-tooltip></template><template #default="{ row }"><el-input v-model="row.arRatio" size="small" :disabled="isReadonly" placeholder="%" @change="updateCell(row.id,'arRatio',row.arRatio)" /></template></el-table-column>
      <el-table-column label="合同负债" min-width="100" align="right"><template #default="{ row }"><el-input-number v-model="row.contractLiability" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'contractLiability',row.contractLiability)" /></template></el-table-column>
      <el-table-column min-width="60"><template #header><el-tooltip content="占期末余额比重" placement="top"><span>占比</span></el-tooltip></template><template #default="{ row }"><el-input v-model="row.clRatio" size="small" :disabled="isReadonly" placeholder="%" @change="updateCell(row.id,'clRatio',row.clRatio)" /></template></el-table-column>
      <!-- 核查方式5子列 -->
      <el-table-column label="核查方式（√）" align="center" class-name="col-check">
        <el-table-column width="45" align="center"><template #header><el-tooltip content="工商资料查询" placement="top"><span>工商</span></el-tooltip></template><template #default="{ row }"><el-checkbox v-model="row.checkBiz" :disabled="isReadonly" @change="updateCell(row.id,'checkBiz',row.checkBiz)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #header><el-tooltip content="互联网信息查询" placement="top"><span>网查</span></el-tooltip></template><template #default="{ row }"><el-checkbox v-model="row.checkInternet" :disabled="isReadonly" @change="updateCell(row.id,'checkInternet',row.checkInternet)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #header><el-tooltip content="函证" placement="top"><span>函证</span></el-tooltip></template><template #default="{ row }"><el-checkbox v-model="row.checkConfirm" :disabled="isReadonly" @change="updateCell(row.id,'checkConfirm',row.checkConfirm)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #header><el-tooltip content="视频/电话访谈" placement="top"><span>电话</span></el-tooltip></template><template #default="{ row }"><el-checkbox v-model="row.checkCall" :disabled="isReadonly" @change="updateCell(row.id,'checkCall',row.checkCall)" /></template></el-table-column>
        <el-table-column width="45" align="center"><template #header><el-tooltip content="实地走访客户" placement="top"><span>走访</span></el-tooltip></template><template #default="{ row }"><el-checkbox v-model="row.checkVisit" :disabled="isReadonly" @change="updateCell(row.id,'checkVisit',row.checkVisit)" /></template></el-table-column>
      </el-table-column>
      <el-table-column label="索引" width="70"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(row.id,'indexRef',row.indexRef)" /></template></el-table-column>
      <el-table-column label="操作" width="55" fixed="right" align="center"><template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button></div>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录核查发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断客户交易真实性" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="客户信息核查清单D4-28" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-customer-checklist{padding:16px 20px;font-size: var(--wp-font-size, 13px)}.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:20px;padding:14px 18px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:10px 16px;min-width:100px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.08)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-card.stat-ok{border-left:3px solid #67c23a}.stat-value{font-size:18px;font-weight:700;color:#303133;font-variant-numeric:tabular-nums}.stat-unit{font-size:12px;font-weight:400;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-step{margin-bottom:6px}.step-num{display:inline-block;background:#e6a23c;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px}
.checklist-table{font-size: var(--wp-font-size, 13px)}.checklist-table :deep(.el-table__cell){padding:5px 3px}.checklist-table :deep(.col-check .el-table__cell){background-color:#f0f9eb !important}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
