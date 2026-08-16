<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * D4TabOtherCheck — D4-35 其他业务收入检查表（抽凭）
 *
 * 抽样参数区 + 动态行检查表(17列含6子列核对内容√/×)
 * 合计/本期发生额/检查比例自动计算
 * 行级附件+OCR + AI + 双模式 + 导入导出
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
interface SamplingParams { testPopulation: string; specificItems: string; samplingPopulation: string; sampleSize: string; samplingMethod: string; samplingProcess: string }
interface CheckRow {
  id: string; date: string; voucherNo: string; content: string; counterAccount: string; detailAccount: string
  amount: number | string; supportDoc: string
  check1: string; check2: string; check3: string; check4: string; check5: string; check6: string
  indexRef: string; isAnomalous: string; remark: string
}

const CHECK_LABELS = ['原始凭证是否齐全', '记账凭证与原始凭证是否相符', '账务处理是否正确', '是否记录于恰当的会计期间', '（自定义5）', '（自定义6）']

const sampling = ref<SamplingParams>({ testPopulation: '', specificItems: '', samplingPopulation: '', sampleSize: '', samplingMethod: '', samplingProcess: '' })
const rows = ref<CheckRow[]>([])
const periodAmount = ref<number | string>('')  // 本期发生额
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function pn(v: any): number { if (!v || v === '') return 0; const n = parseFloat(String(v)); return isNaN(n) ? 0 : n }
function createRow(): CheckRow { return { id: `ck-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, date: '', voucherNo: '', content: '', counterAccount: '', detailAccount: '', amount: '', supportDoc: '', check1: '', check2: '', check3: '', check4: '', check5: '', check6: '', indexRef: '', isAnomalous: '', remark: '' } }

function loadData() {
  const r = props.allResponses.get('D4-35-data')
  if (r?.remark) { try { const p = JSON.parse(r.remark); if (p) { rows.value = p.rows || []; sampling.value = { ...sampling.value, ...p.sampling }; periodAmount.value = p.periodAmount || ''; return } } catch {} }
  rows.value = []; sampling.value = { testPopulation: '', specificItems: '', samplingPopulation: '', sampleSize: '', samplingMethod: '', samplingProcess: '' }
}
function loadNote() { auditNote.value = props.allResponses.get('D4-35-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-35-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-35-data')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-35-note')?.remark, loadNote, { immediate: true })

function addRow() { if (props.isReadonly) return; rows.value.push(createRow()); persistAll() }
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function updateRow(id: string, field: keyof CheckRow, value: any) { if (props.isReadonly) return; const row = rows.value.find(r => r.id === id); if (row) { (row as any)[field] = value; persistAll() } }
function updateSampling(field: keyof SamplingParams, value: string) { if (props.isReadonly) return; sampling.value[field] = value; persistAll() }

// Stats
const totalChecked = computed(() => rows.value.reduce((s, r) => s + pn(r.amount), 0))
const checkRatio = computed(() => { const pa = pn(periodAmount.value); return pa > 0 ? ((totalChecked.value / pa) * 100).toFixed(2) + '%' : '—' })
const anomalyCount = computed(() => rows.value.filter(r => r.isAnomalous === '是').length)

function persistAll() {
  props.allResponses.set('D4-35-data', { item_id: 'D4-35-data', conclusion: null, remark: JSON.stringify({ rows: rows.value, sampling: sampling.value, periodAmount: periodAmount.value }) })
  props.allResponses.set('D4-35-note', { item_id: 'D4-35-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-35-conclusion', { item_id: 'D4-35-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-35-data','D4-35-note','D4-35-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-35-data','D4-35-note','D4-35-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

// OCR
async function handleOcrUpload(rowId: string, file: File) {
  if (!file) return
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }
    const row = rows.value.find(r => r.id === rowId)
    if (!row) return
    if (fields.date) row.date = String(fields.date)
    if (fields.voucherNo || fields.number) row.voucherNo = String(fields.voucherNo || fields.number)
    if (fields.content || fields.summary) row.content = String(fields.content || fields.summary)
    if (fields.amount) row.amount = parseFloat(fields.amount) || ''
    if (fields.counterAccount) row.counterAccount = String(fields.counterAccount)
    persistAll()
    ElMessage.success('OCR结果已填入')
  } catch { ElMessage.warning('OCR识别失败') }
}

const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于其他业务收入检查表(D4-35)抽凭结果生成审计说明', rowCount: rows.value.length, totalChecked: totalChecked.value, checkRatio: checkRatio.value, anomalyCount: anomalyCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于抽凭检查结果生成审计结论', noteText: auditNote.value, anomalyCount: anomalyCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function fmtAmt(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }
function rowClassName({ row }: { row: CheckRow }) { return row.isAnomalous === '是' ? 'row-anomaly' : '' }
</script>

<template>
<div class="d4-other-check">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-35')">导出模板</el-dropdown-item><el-dropdown-item @click="exportData('D4-35')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-35',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-34" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-35-check')">💬 复核</el-button></div></div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 审计目标 -->
    <details class="methodology-collapse" open>
      <summary class="methodology-summary">📖 审计目标与测试内容说明</summary>
      <div class="methodology-body">
        <p><strong>一、审计目标：</strong></p>
        <ol class="method-list">
          <li>利润表中记录的其他业务收入已发生，且与被审计单位有关，已记录于恰当的账户。</li>
          <li>与其他业务收入有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述。</li>
        </ol>
        <p class="method-red">测试内容说明：1.原始凭证是否齐全；2.记账凭证与原始凭证是否相符；3.账务处理是否正确；4.是否记录于恰当的会计期间；5.……</p>
      </div>
    </details>

    <!-- 抽样参数区 -->
    <div class="sampling-params">
      <div class="param-row"><label>测试总体：</label><el-input :model-value="sampling.testPopulation" size="small" :disabled="isReadonly" placeholder="如借方发生额所有凭证共XX笔金额XX" @input="(v:string)=>updateSampling('testPopulation',v)" /></div>
      <div class="param-row"><label>特定样本：</label><el-input :model-value="sampling.specificItems" size="small" :disabled="isReadonly" placeholder="XX金额以上（大额）、关联方、异常款项，共XX笔" @input="(v:string)=>updateSampling('specificItems',v)" /></div>
      <div class="param-row"><label>抽样总体：</label><el-input :model-value="sampling.samplingPopulation" size="small" :disabled="isReadonly" placeholder="测试总体扣除特定样本以外的样本，共XX笔" @input="(v:string)=>updateSampling('samplingPopulation',v)" /></div>
      <div class="param-row"><label>抽样样本量：</label><el-input :model-value="sampling.sampleSize" size="small" :disabled="isReadonly" placeholder="抽取XX笔" @input="(v:string)=>updateSampling('sampleSize',v)" /></div>
      <div class="param-row"><label>抽样方法：</label><el-input :model-value="sampling.samplingMethod" size="small" :disabled="isReadonly" placeholder="随机选样/系统选样/货币单元抽样" @input="(v:string)=>updateSampling('samplingMethod',v)" /></div>
      <div class="param-row"><label>抽样过程：</label><el-input :model-value="sampling.samplingProcess" size="small" :disabled="isReadonly" placeholder="使用IDEA等工具选择样本" @input="(v:string)=>updateSampling('samplingProcess',v)" /></div>
      <div class="param-row"><label>本期发生额：</label><el-input-number :model-value="pn(periodAmount)" size="small" :controls="false" :disabled="isReadonly" style="width:200px" @change="(v:any)=>{periodAmount=v??'';persistAll()}" /></div>
    </div>

    <!-- 统计横幅 -->
    <div class="stats-bar">
      <span class="stat-item">检查金额：<strong>{{ fmtAmt(totalChecked) }}</strong></span>
      <span class="stat-item">检查比例：<strong>{{ checkRatio }}</strong></span>
      <span class="stat-item" :class="{ warn: anomalyCount > 0 }">异常：<strong>{{ anomalyCount }}笔</strong></span>
      <span class="stat-item">样本数：<strong>{{ rows.length }}笔</strong></span>
    </div>

    <!-- 测试内容说明 -->
    <div class="test-hint">
      <span class="test-hint-label">核对内容：</span>
      <span v-for="(lbl, idx) in CHECK_LABELS" :key="idx" class="test-hint-chip">{{ idx+1 }}.{{ lbl }}</span>
    </div>

    <!-- 主表格 -->
    <el-table :data="rows" border stripe size="small" class="check-table" :row-class-name="rowClassName">
      <el-table-column label="日期" min-width="90"><template #default="{ row }"><el-input v-model="row.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateRow(row.id,'date',row.date)" /></template></el-table-column>
      <el-table-column label="凭证编号" min-width="85"><template #default="{ row }"><el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="updateRow(row.id,'voucherNo',row.voucherNo)" /></template></el-table-column>
      <el-table-column label="业务内容" min-width="100"><template #default="{ row }"><el-input v-model="row.content" size="small" :disabled="isReadonly" @change="updateRow(row.id,'content',row.content)" /></template></el-table-column>
      <el-table-column label="对方科目" min-width="80"><template #default="{ row }"><el-input v-model="row.counterAccount" size="small" :disabled="isReadonly" @change="updateRow(row.id,'counterAccount',row.counterAccount)" /></template></el-table-column>
      <el-table-column label="明细科目" min-width="80"><template #default="{ row }"><el-input v-model="row.detailAccount" size="small" :disabled="isReadonly" @change="updateRow(row.id,'detailAccount',row.detailAccount)" /></template></el-table-column>
      <el-table-column label="金额" min-width="90" align="right"><template #default="{ row }"><WpAmountInput v-model="row.amount" size="small" :disabled="isReadonly" style="width:100%" @change="updateRow(row.id,'amount',row.amount)" /></template></el-table-column>
      <el-table-column label="支持性文件" min-width="90"><template #default="{ row }"><el-input v-model="row.supportDoc" size="small" :disabled="isReadonly" @change="updateRow(row.id,'supportDoc',row.supportDoc)" /></template></el-table-column>
      <!-- 核对内容6子列 -->
      <el-table-column label="核对内容" align="center" class-name="col-check">
        <el-table-column v-for="i in 6" :key="i" :label="String(i)" width="35" align="center"><template #default="{ row }"><el-checkbox :model-value="(row as any)['check'+i]==='√'" :disabled="isReadonly" @change="(v:boolean)=>updateRow(row.id,('check'+i) as any,v?'√':'')">&#8203;</el-checkbox></template></el-table-column>
      </el-table-column>
      <el-table-column label="索引" width="60"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateRow(row.id,'indexRef',row.indexRef)" /></template></el-table-column>
      <el-table-column label="异常" width="55" align="center"><template #default="{ row }"><el-select v-model="row.isAnomalous" size="small" :disabled="isReadonly" placeholder="—" @change="updateRow(row.id,'isAnomalous',row.isAnomalous)"><el-option label="是" value="是" /><el-option label="否" value="否" /></el-select></template></el-table-column>
      <el-table-column label="备注" min-width="90"><template #default="{ row }"><el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="updateRow(row.id,'remark',row.remark)" /></template></el-table-column>
      <!-- 附件+OCR -->
      <el-table-column label="📎" width="45" align="center"><template #default="{ row }"><el-dropdown trigger="click" size="small"><el-button link size="small" :disabled="isReadonly">📎</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any)=>handleOcrUpload(row.id,f.raw||f)"><span>上传文件</span></el-upload></el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" :auto-upload="false" multiple :disabled="isReadonly" @change="(f:any)=>handleOcrUpload(row.id,f.raw||f)"><span>上传文件夹</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown></template></el-table-column>
      <el-table-column width="35" align="center"><template #default="{ row }"><el-popconfirm title="删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">×</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="addRow"><el-icon :size="14"><Plus /></el-icon> 添加凭证</el-button></div>

    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>四、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录抽凭检查中发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>五、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断其他业务收入是否真实、完整、准确" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="其他业务收入检查表D4-35" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-other-check{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.sampling-params{margin-bottom:16px;padding:12px 16px;background:#f5f7fa;border-radius:8px;border:1px solid #ebeef5}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-list{margin:4px 0 8px 16px;padding:0}.method-list li{margin-bottom:2px}.method-red{color:#f56c6c;font-style:italic;padding:4px 8px;background:#fef0f0;border-radius:3px;margin-top:8px}
.param-row{display:flex;align-items:center;gap:8px;margin-bottom:6px}.param-row:last-child{margin-bottom:0}.param-row label{min-width:80px;font-size:12px;color:#606266;font-weight:500;flex-shrink:0}.param-row :deep(.el-input){flex:1}
.stats-bar{display:flex;gap:20px;margin-bottom:12px;padding:8px 14px;background:linear-gradient(135deg,#f8f9fe,#f0f4ff);border-radius:6px;border:1px solid #e4e7ed;font-size: var(--wp-font-size, 13px);color:#606266}.stat-item strong{color:#303133;margin-left:4px}.stat-item.warn{color:#f56c6c}.stat-item.warn strong{color:#f56c6c}
.test-hint{margin-bottom:12px;padding:6px 12px;background:#fffbf0;border-radius:4px;border:1px solid #faecd8;display:flex;align-items:center;gap:6px;flex-wrap:wrap}.test-hint-label{font-size:12px;color:#e6a23c;font-weight:500}.test-hint-chip{font-size:11px;color:#606266;background:#fff;border:1px solid #ebeef5;border-radius:3px;padding:1px 6px}
.check-table{font-size: var(--wp-font-size, 13px)}.check-table :deep(.el-table__cell){padding:4px 3px}.check-table :deep(.col-check .el-table__cell){background-color:#f0f9eb !important}.check-table :deep(.row-anomaly td){background-color:#fef0f0 !important}
.add-row-bar{margin:12px 0 20px;text-align:center}
.audit-opinion-card{margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
