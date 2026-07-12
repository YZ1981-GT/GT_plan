<script setup lang="ts">
/**
 * D4TabDealer — D4-25 经销商检查
 *
 * 动态行：每行一个经销商客户，13列对齐源模板
 * 序号/客户名称/经销商/本期销售数量/本期销售金额/占同类比例/期末应收/是否关联方/个人企业/销售费用承担/补贴返利/终端销售金额/备注
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

interface DealerRow {
  id: string; customerName: string; dealer: string; salesQty: number | string; salesAmount: number | string
  proportion: number | string; arBalance: number | string; isRelated: string; entityType: string
  expenseBearer: string; subsidy: string; terminalSalesAmount: number | string; remark: string
}

const rows = ref<DealerRow[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name: string): DealerRow {
  return { id: `dl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, customerName: name, dealer: '', salesQty: '', salesAmount: '', proportion: '', arBalance: '', isRelated: '', entityType: '', expenseBearer: '', subsidy: '', terminalSalesAmount: '', remark: '' }
}

function loadData() { const r = props.allResponses.get('D4-25-rows'); if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; return } } catch {} }; rows.value = [] }
function loadNote() { auditNote.value = props.allResponses.get('D4-25-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-25-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-25-rows')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-25-note')?.remark, loadNote, { immediate: true })

async function handleAddRow() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入客户名称', '添加经销商记录', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { rows.value.push(createRow(value.trim())); persistAll() } } catch {} }
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function updateCell(id: string, field: keyof DealerRow, value: any) { if (props.isReadonly) return; const row = rows.value.find(r => r.id === id); if (row) { (row as any)[field] = value; persistAll() } }

function persistAll() {
  props.allResponses.set('D4-25-rows', { item_id: 'D4-25-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-25-note', { item_id: 'D4-25-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-25-conclusion', { item_id: 'D4-25-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-25-rows','D4-25-note','D4-25-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-25-rows','D4-25-note','D4-25-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)

async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于经销商检查(D4-25)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于经销商检查结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate('D4-25') }
function handleExportData() { exportData('D4-25') }
async function handleImportFile(f: any) { await importData('D4-25', f.raw || f) }
</script>

<template>
<div class="d4-dealer">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-1" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-25-dealer')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <div class="guide-strip"><span class="guide-strip-label">编制流程：</span><el-tooltip content="关注经销商基本情况是否与销售规模匹配" placement="bottom" :show-after="300"><span class="guide-chip">①客户匹配</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="记录经销商情况(关联方/法人类型/费用承担/返利)" placement="bottom" :show-after="300"><span class="guide-chip">②记录信息</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="比对终端销售金额与经销商采购金额" placement="bottom" :show-after="300"><span class="guide-chip">③终端核对</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="分析合理性，形成审计结论" placement="bottom" :show-after="300"><span class="guide-chip">④分析结论</span></el-tooltip></div>

    <el-table :data="rows" border stripe class="dealer-table">
      <el-table-column label="序号" width="55" align="center" fixed><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
      <el-table-column label="客户名称" min-width="120"><template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.id,'customerName',row.customerName)" /></template></el-table-column>
      <el-table-column label="经销商" min-width="100"><template #default="{ row }"><el-input v-model="row.dealer" size="small" :disabled="isReadonly" @change="updateCell(row.id,'dealer',row.dealer)" /></template></el-table-column>
      <el-table-column label="本期销售数量" min-width="100" align="right"><template #default="{ row }"><el-input-number v-model="row.salesQty" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'salesQty',row.salesQty)" /></template></el-table-column>
      <el-table-column label="本期销售金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.salesAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'salesAmount',row.salesAmount)" /></template></el-table-column>
      <el-table-column label="占同类交易比例" min-width="100"><template #default="{ row }"><el-input v-model="row.proportion" size="small" :disabled="isReadonly" placeholder="如5%" @change="updateCell(row.id,'proportion',row.proportion)" /></template></el-table-column>
      <el-table-column label="期末应收余额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.arBalance" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'arBalance',row.arBalance)" /></template></el-table-column>
      <el-table-column label="是否关联方" width="85" align="center"><template #default="{ row }"><el-select v-model="row.isRelated" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id,'isRelated',row.isRelated)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
      <el-table-column label="个人/企业" width="85" align="center"><template #default="{ row }"><el-select v-model="row.entityType" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id,'entityType',row.entityType)"><el-option label="企业" value="企业" /><el-option label="个人" value="个人" /></el-select></template></el-table-column>
      <el-table-column label="销售费用承担" min-width="100"><template #default="{ row }"><el-input v-model="row.expenseBearer" size="small" :disabled="isReadonly" @change="updateCell(row.id,'expenseBearer',row.expenseBearer)" /></template></el-table-column>
      <el-table-column label="补贴或返利" min-width="100"><template #default="{ row }"><el-input v-model="row.subsidy" size="small" :disabled="isReadonly" @change="updateCell(row.id,'subsidy',row.subsidy)" /></template></el-table-column>
      <el-table-column label="终端销售金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.terminalSalesAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'terminalSalesAmount',row.terminalSalesAmount)" /></template></el-table-column>
      <el-table-column label="备注" min-width="100"><template #default="{ row }"><el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="updateCell(row.id,'remark',row.remark)" /></template></el-table-column>
      <el-table-column label="操作" width="60" fixed="right" align="center"><template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加经销商</el-button></div>

    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录经销商销售检查中发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断经销商销售收入的真实性" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="经销商检查D4-25" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-dealer{padding:16px 20px;font-size: var(--wp-font-size, 13px)}.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.guide-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}.guide-strip-label{font-weight:600;color:#67c23a;font-size:12px}.guide-chip{background:#fff;border:1px solid #c2e7b0;border-radius:4px;padding:2px 8px;font-size:12px;color:#529b2e;cursor:help}.guide-arrow{color:#a8abb2;font-size:12px}.dealer-table{font-size: var(--wp-font-size, 13px)}.dealer-table :deep(.el-table__cell){padding:5px 4px}.add-row-bar{margin:12px 0 24px;text-align:center}.audit-opinion-card{margin-bottom:20px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
