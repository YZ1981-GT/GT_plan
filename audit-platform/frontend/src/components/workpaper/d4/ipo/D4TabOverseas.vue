<script setup lang="ts">
/**
 * D4TabOverseas — D4-26 境外销售收入检查
 *
 * 动态行：每行一个境外客户，多级表头
 * 基本信息(A~I) + 第三方回款(J~K) + 核查金额(L~N) + 相关程序索引(O~S 5子列)
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

interface OverseasRow {
  id: string; customerName: string; country: string; product: string; bizModel: string
  salesAmount: number | string; proportion: string; tradeMode: string; tradeTerms: string
  settlementMode: string; hasThirdParty: string; thirdPartyReason: string
  verifiedAmount: number | string; diff: number | string; diffReason: string
  idxVisit: string; idxConfirm: string; idxCustoms: string; idxDeclaration: string; idxEport: string
}

const rows = ref<OverseasRow[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name: string): OverseasRow {
  return { id: `os-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, customerName: name, country: '', product: '', bizModel: '', salesAmount: '', proportion: '', tradeMode: '', tradeTerms: '', settlementMode: '', hasThirdParty: '', thirdPartyReason: '', verifiedAmount: '', diff: '', diffReason: '', idxVisit: '', idxConfirm: '', idxCustoms: '', idxDeclaration: '', idxEport: '' }
}

function loadData() { const r = props.allResponses.get('D4-26-rows'); if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; return } } catch {} }; rows.value = [] }
function loadNote() { auditNote.value = props.allResponses.get('D4-26-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-26-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-26-rows')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-26-note')?.remark, loadNote, { immediate: true })

async function handleAddRow() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入客户名称', '添加境外客户', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { rows.value.push(createRow(value.trim())); persistAll() } } catch {} }
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function updateCell(id: string, field: keyof OverseasRow, value: any) { if (props.isReadonly) return; const row = rows.value.find(r => r.id === id); if (row) { (row as any)[field] = value; persistAll() } }

function persistAll() {
  props.allResponses.set('D4-26-rows', { item_id: 'D4-26-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-26-note', { item_id: 'D4-26-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-26-conclusion', { item_id: 'D4-26-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-26-rows','D4-26-note','D4-26-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-26-rows','D4-26-note','D4-26-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于境外销售收入检查(D4-26)结果生成审计说明', rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于境外销售检查结果生成审计结论', noteText: auditNote.value, rowCount: rows.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate('D4-26') }
function handleExportData() { exportData('D4-26') }
async function handleImportFile(f: any) { await importData('D4-26', f.raw || f) }
</script>

<template>
<div class="d4-overseas">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-1" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-26-overseas')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <div class="guide-strip"><span class="guide-strip-label">编制流程：</span><el-tooltip content="对主要海外客户、目的国、贸易条款进行分析记录" placement="bottom" :show-after="300"><span class="guide-chip">①分析客户</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="记录已执行的海关查询、函证等程序" placement="bottom" :show-after="300"><span class="guide-chip">②记录程序</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="核对核查金额与账面差异" placement="bottom" :show-after="300"><span class="guide-chip">③核对差异</span></el-tooltip><span class="guide-arrow">→</span><el-tooltip content="形成审计说明与结论" placement="bottom" :show-after="300"><span class="guide-chip">④审计结论</span></el-tooltip></div>

    <el-table :data="rows" border stripe class="overseas-table">
      <el-table-column label="客户名称" min-width="110" fixed><template #default="{ row }"><el-input v-model="row.customerName" size="small" :disabled="isReadonly" @change="updateCell(row.id,'customerName',row.customerName)" /></template></el-table-column>
      <el-table-column label="所在国家/地区" min-width="100"><template #default="{ row }"><el-input v-model="row.country" size="small" :disabled="isReadonly" @change="updateCell(row.id,'country',row.country)" /></template></el-table-column>
      <el-table-column label="产品种类" min-width="90"><template #default="{ row }"><el-input v-model="row.product" size="small" :disabled="isReadonly" @change="updateCell(row.id,'product',row.product)" /></template></el-table-column>
      <el-table-column label="业务模式" min-width="90"><template #default="{ row }"><el-input v-model="row.bizModel" size="small" :disabled="isReadonly" placeholder="直销/经销" @change="updateCell(row.id,'bizModel',row.bizModel)" /></template></el-table-column>
      <el-table-column label="本期销售金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.salesAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'salesAmount',row.salesAmount)" /></template></el-table-column>
      <el-table-column label="占比" min-width="70"><template #default="{ row }"><el-input v-model="row.proportion" size="small" :disabled="isReadonly" @change="updateCell(row.id,'proportion',row.proportion)" /></template></el-table-column>
      <el-table-column label="贸易模式" min-width="80"><template #default="{ row }"><el-input v-model="row.tradeMode" size="small" :disabled="isReadonly" placeholder="EXW/FOB/CIF" @change="updateCell(row.id,'tradeMode',row.tradeMode)" /></template></el-table-column>
      <el-table-column label="贸易条款" min-width="110"><template #default="{ row }"><el-input v-model="row.tradeTerms" size="small" :disabled="isReadonly" @change="updateCell(row.id,'tradeTerms',row.tradeTerms)" /></template></el-table-column>
      <el-table-column label="结算模式" min-width="90"><template #default="{ row }"><el-input v-model="row.settlementMode" size="small" :disabled="isReadonly" placeholder="汇款/信用证" @change="updateCell(row.id,'settlementMode',row.settlementMode)" /></template></el-table-column>
      <el-table-column label="第三方回款" width="75" align="center"><template #default="{ row }"><el-select v-model="row.hasThirdParty" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id,'hasThirdParty',row.hasThirdParty)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
      <el-table-column label="第三方回款原因" min-width="110"><template #default="{ row }"><el-input v-model="row.thirdPartyReason" size="small" :disabled="isReadonly" @change="updateCell(row.id,'thirdPartyReason',row.thirdPartyReason)" /></template></el-table-column>
      <el-table-column label="核查确认金额" min-width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.verifiedAmount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'verifiedAmount',row.verifiedAmount)" /></template></el-table-column>
      <el-table-column label="差异" min-width="100" align="right"><template #default="{ row }"><el-input v-model="row.diff" size="small" :disabled="isReadonly" @change="updateCell(row.id,'diff',row.diff)" /></template></el-table-column>
      <el-table-column label="差异原因" min-width="110"><template #default="{ row }"><el-input v-model="row.diffReason" size="small" :disabled="isReadonly" @change="updateCell(row.id,'diffReason',row.diffReason)" /></template></el-table-column>
      <!-- 相关程序索引（5子列） -->
      <el-table-column label="相关程序索引" align="center">
        <el-table-column label="实地走访" width="70"><template #default="{ row }"><el-input v-model="row.idxVisit" size="small" :disabled="isReadonly" @change="updateCell(row.id,'idxVisit',row.idxVisit)" /></template></el-table-column>
        <el-table-column label="交易函证" width="70"><template #default="{ row }"><el-input v-model="row.idxConfirm" size="small" :disabled="isReadonly" @change="updateCell(row.id,'idxConfirm',row.idxConfirm)" /></template></el-table-column>
        <el-table-column label="海关函证" width="70"><template #default="{ row }"><el-input v-model="row.idxCustoms" size="small" :disabled="isReadonly" @change="updateCell(row.id,'idxCustoms',row.idxCustoms)" /></template></el-table-column>
        <el-table-column label="核对报关单" width="75"><template #default="{ row }"><el-input v-model="row.idxDeclaration" size="small" :disabled="isReadonly" @change="updateCell(row.id,'idxDeclaration',row.idxDeclaration)" /></template></el-table-column>
        <el-table-column label="电子口岸" width="70"><template #default="{ row }"><el-input v-model="row.idxEport" size="small" :disabled="isReadonly" @change="updateCell(row.id,'idxEport',row.idxEport)" /></template></el-table-column>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right" align="center"><template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button></div>

    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录发现的差异或异常交易安排的迹象，以及所执行的应对措施" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断境外销售收入的真实性和交易实质" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="境外销售收入检查D4-26" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-overseas{padding:16px 20px;font-size:13px}.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.guide-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}.guide-strip-label{font-weight:600;color:#67c23a;font-size:12px}.guide-chip{background:#fff;border:1px solid #c2e7b0;border-radius:4px;padding:2px 8px;font-size:12px;color:#529b2e;cursor:help}.guide-arrow{color:#a8abb2;font-size:12px}.overseas-table{font-size:13px}.overseas-table :deep(.el-table__cell){padding:5px 3px}.add-row-bar{margin:12px 0 24px;text-align:center}.audit-opinion-card{margin-bottom:20px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
