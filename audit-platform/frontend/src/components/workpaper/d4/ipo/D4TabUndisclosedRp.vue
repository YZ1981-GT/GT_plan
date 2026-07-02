<script setup lang="ts">
/**
 * D4TabUndisclosedRp — D4-27 识别未披露的关联方
 *
 * 双区结构：
 * ①动态行检查表（每行一个姓名，多部门匹配列+总计自动汇总+Y/N判断+说明）
 * ②叙述式审计说明（带预设步骤的结构化文本）+ 审计结论
 * 18列对齐源模板 + 双模式 + AI + 导入导出
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
interface RpRow {
  id: string; name: string
  personalCustomer: number; customerLegalPerson: number; contractSignee: number; executiveRelative: number
  financeDept: number; managementDept: number; techDept: number; productionDept: number; salesDept: number; otherDept: number
  total: number  // 自动计算
  isMatch: string  // Y/N
  identity: string  // 公司股东/高管/亲属/员工
  annualSales: number | string
  note: string; indexRef: string
}

const rows = ref<RpRow[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function createRow(name: string): RpRow {
  return { id: `rp-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, name, personalCustomer: 0, customerLegalPerson: 0, contractSignee: 0, executiveRelative: 0, financeDept: 0, managementDept: 0, techDept: 0, productionDept: 0, salesDept: 0, otherDept: 0, total: 0, isMatch: '', identity: '', annualSales: '', note: '', indexRef: '' }
}

function calcTotal(row: RpRow): number {
  return (row.personalCustomer || 0) + (row.customerLegalPerson || 0) + (row.contractSignee || 0) + (row.executiveRelative || 0) + (row.financeDept || 0) + (row.managementDept || 0) + (row.techDept || 0) + (row.productionDept || 0) + (row.salesDept || 0) + (row.otherDept || 0)
}

// ─── Load ────────────────────────────────────────────────────────────
function loadData() { const r = props.allResponses.get('D4-27-rows'); if (r?.remark) { try { const p = JSON.parse(r.remark); if (Array.isArray(p)) { rows.value = p; return } } catch {} }; rows.value = [] }
function loadNote() { auditNote.value = props.allResponses.get('D4-27-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-27-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-27-rows')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-27-note')?.remark, loadNote, { immediate: true })

// ─── CRUD ────────────────────────────────────────────────────────────
async function handleAddRow() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入姓名', '添加比对人员', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { rows.value.push(createRow(value.trim())); persistAll() } } catch {} }
function removeRow(id: string) { if (props.isReadonly) return; rows.value = rows.value.filter(r => r.id !== id); persistAll() }
function updateCell(id: string, field: keyof RpRow, value: any) {
  if (props.isReadonly) return
  const row = rows.value.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value
  row.total = calcTotal(row)
  // 自动判断Y/N
  if (row.total > 0 && !row.isMatch) row.isMatch = 'Y'
  persistAll()
}

// ─── Persistence ─────────────────────────────────────────────────────
function persistAll() {
  props.allResponses.set('D4-27-rows', { item_id: 'D4-27-rows', conclusion: null, remark: JSON.stringify(rows.value) })
  props.allResponses.set('D4-27-note', { item_id: 'D4-27-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-27-conclusion', { item_id: 'D4-27-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-27-rows','D4-27-note','D4-27-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-27-rows','D4-27-note','D4-27-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

// ─── Stats ───────────────────────────────────────────────────────────
const matchCount = computed(() => rows.value.filter(r => r.isMatch === 'Y').length)
const totalSales = computed(() => rows.value.reduce((s, r) => s + (parseFloat(String(r.annualSales)) || 0), 0))

// ─── Mode / AI ───────────────────────────────────────────────────────
const editorMode = ref<string>('表格视图'); const modeOptions = ['表格视图', '在线编辑']
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)

async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于识别未披露关联方(D4-27)的比对结果生成审计说明', rowCount: rows.value.length, matchCount: matchCount.value, totalSales: totalSales.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于关联方识别结果生成审计结论', noteText: auditNote.value, matchCount: matchCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
function handleExportTemplate() { exportTemplate('D4-27') }
function handleExportData() { exportData('D4-27') }
async function handleImportFile(f: any) { await importData('D4-27', f.raw || f) }

function fmtAmount(v: number): string { return v ? v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : '—' }
function rowClassName({ row }: { row: RpRow }) { return row.isMatch === 'Y' ? 'row-match' : '' }
</script>

<template>
<div class="d4-undisclosed-rp">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-1" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-27-rp')">💬 复核</el-button></div></div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ rows.length }}<span class="stat-unit">人</span></div><div class="stat-label">比对人数</div></div>
    <div class="stat-card" :class="matchCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ matchCount }}<span class="stat-unit">人</span></div><div class="stat-label">重名匹配</div></div>
    <div class="stat-card stat-amount"><div class="stat-value">{{ fmtAmount(totalSales) }}</div><div class="stat-label">涉及销售额</div></div>
  </div>

  <template v-if="editorMode !== '在线编辑'">
    <!-- 方法论折叠（源模板红字审计过程） -->
    <details class="methodology-collapse">
      <summary class="methodology-summary">📖 审计目标与识别未披露关联方过程（点击展开）</summary>
      <div class="methodology-body">
        <p class="method-objective"><strong>一、审计目标：</strong>主要或异常客户是否与被审计单位存在关联方关系。</p>
        <p class="method-process"><strong>二、审计过程：</strong></p>
        <div class="method-steps">
          <p class="method-step"><span class="step-num">1</span>选择大额、异常的客户或交易。</p>
          <p class="method-step"><span class="step-num">2</span>查询客户工商、银行、税务信息资料，关注其地址、董事/监事/关键管理人员、联系方式等信息，并与其相关发票信息、网站信息进行核对，识别客户是否存在与被审计单位存在疑似关联关系的信息。</p>
          <p class="method-step"><span class="step-num">3</span>选取重要客户，获取关联方关系确认函。</p>
          <p class="method-step"><span class="step-num">4</span>取得发行人实际控制人、董高监及其密切家庭人员的对外投资清单，与重要客户的股东和关键经办人员进行比对，关注与发行人实际控制人、董事、监事、高级管理人员关系密切的家庭成员与发行人的客户是否存在关联方关系。</p>
          <p class="method-step"><span class="step-num">5</span>取得保荐机构及其关联方、PE投资机构及其关联方、PE投资机构的股东或实际控制人控制或投资的其他企业清单，将这些利益相关方清单和重要客户及其法人、股东和关键经办人员名单进行比对，关注其是否与发行人发生大额交易从而导致发行人在报告期内收入、利润出现较大幅度增长。</p>
          <p class="method-step"><span class="step-num">6</span>获取发行人主要股东、董事、监事、关键管理人员及上述利益相关方的确认函，确认除其本人在被审计单位领取薪酬或分得股利外，其本人及其关系密切的家庭成员未与被审计单位有任何形式的交易。</p>
        </div>
      </div>
    </details>

    <!-- 引导条 -->
    <div class="guide-strip"><span class="guide-strip-label">编制流程：</span>
      <el-tooltip content="选择大额、异常客户或交易" placement="bottom" :show-after="300"><span class="guide-chip">①选取客户</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="查询客户工商/银行/税务信息,识别疑似关联关系" placement="bottom" :show-after="300"><span class="guide-chip">②查询信息</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="获取发行人实控人/董高监/家属对外投资清单与客户比对" placement="bottom" :show-after="300"><span class="guide-chip">③穿透比对</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="获取身份证核对地址/身份证号是否重复" placement="bottom" :show-after="300"><span class="guide-chip">④身份核验</span></el-tooltip><span class="guide-arrow">→</span>
      <el-tooltip content="获取确认函并形成审计结论" placement="bottom" :show-after="300"><span class="guide-chip">⑤确认结论</span></el-tooltip>
    </div>

    <!-- ═══ 主表格：部门匹配矩阵 ═══ -->
    <el-table :data="rows" border stripe class="rp-table" :row-class-name="rowClassName">
      <el-table-column label="序号" width="50" align="center" fixed><template #default="{ $index }">{{ $index+1 }}</template></el-table-column>
      <el-table-column label="姓名" min-width="80" fixed><template #default="{ row }"><el-input v-model="row.name" size="small" :disabled="isReadonly" @change="updateCell(row.id,'name',row.name)" /></template></el-table-column>
      <!-- 匹配维度列 -->
      <el-table-column label="个人客户" width="65" align="center"><template #default="{ row }"><el-input-number v-model="row.personalCustomer" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'personalCustomer',row.personalCustomer)" /></template></el-table-column>
      <el-table-column label="客户法人" width="65" align="center"><template #default="{ row }"><el-input-number v-model="row.customerLegalPerson" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'customerLegalPerson',row.customerLegalPerson)" /></template></el-table-column>
      <el-table-column label="合同签订人" width="72" align="center"><template #default="{ row }"><el-input-number v-model="row.contractSignee" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'contractSignee',row.contractSignee)" /></template></el-table-column>
      <el-table-column label="高管亲属" width="65" align="center"><template #default="{ row }"><el-input-number v-model="row.executiveRelative" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'executiveRelative',row.executiveRelative)" /></template></el-table-column>
      <el-table-column label="财务部" width="55" align="center"><template #default="{ row }"><el-input-number v-model="row.financeDept" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'financeDept',row.financeDept)" /></template></el-table-column>
      <el-table-column label="管理部" width="55" align="center"><template #default="{ row }"><el-input-number v-model="row.managementDept" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'managementDept',row.managementDept)" /></template></el-table-column>
      <el-table-column label="技术部" width="55" align="center"><template #default="{ row }"><el-input-number v-model="row.techDept" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'techDept',row.techDept)" /></template></el-table-column>
      <el-table-column label="生产部" width="55" align="center"><template #default="{ row }"><el-input-number v-model="row.productionDept" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'productionDept',row.productionDept)" /></template></el-table-column>
      <el-table-column label="营销部" width="55" align="center"><template #default="{ row }"><el-input-number v-model="row.salesDept" size="small" :controls="false" :min="0" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'salesDept',row.salesDept)" /></template></el-table-column>
      <!-- 总计（自动） -->
      <el-table-column label="总计" width="55" align="center"><template #default="{ row }"><span class="auto-calc" title="自动汇总各维度匹配数">{{ row.total || '—' }}</span></template></el-table-column>
      <!-- 判断列 -->
      <el-table-column label="重名(Y/N)" width="72" align="center"><template #default="{ row }"><el-select v-model="row.isMatch" size="small" :disabled="isReadonly" placeholder="—" @change="updateCell(row.id,'isMatch',row.isMatch)"><el-option label="Y" value="Y" /><el-option label="N" value="N" /></el-select></template></el-table-column>
      <el-table-column label="身份" min-width="90"><template #default="{ row }"><el-input v-model="row.identity" size="small" :disabled="isReadonly" placeholder="股东/高管/员工" @change="updateCell(row.id,'identity',row.identity)" /></template></el-table-column>
      <el-table-column label="年度销售额" min-width="100" align="right"><template #default="{ row }"><el-input-number v-model="row.annualSales" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateCell(row.id,'annualSales',row.annualSales)" /></template></el-table-column>
      <el-table-column label="说明" min-width="130"><template #default="{ row }"><el-input v-model="row.note" size="small" :disabled="isReadonly" @change="updateCell(row.id,'note',row.note)" /></template></el-table-column>
      <el-table-column label="索引" width="70"><template #default="{ row }"><el-input v-model="row.indexRef" size="small" :disabled="isReadonly" @change="updateCell(row.id,'indexRef',row.indexRef)" /></template></el-table-column>
      <el-table-column label="操作" width="55" fixed="right" align="center"><template #default="{ row }"><el-popconfirm title="确认删除？" @confirm="removeRow(row.id)"><template #reference><el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button></template></el-popconfirm></template></el-table-column>
    </el-table>
    <div class="add-row-bar"><el-button :disabled="isReadonly" @click="handleAddRow"><el-icon :size="14"><Plus /></el-icon> 添加人员</el-button></div>

    <!-- ═══ 审计意见区 ═══ -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:4,maxRows:15}" :model-value="auditNote" :disabled="isReadonly" placeholder="1.公司主要股东、高管、家属、员工名单概况&#10;2.客户法人及关键管理人员概况&#10;3.比对结果（重复姓名数/涉及人数/客户数/销售额）&#10;4.身份证核对结果" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断是否识别出重要客户与公司存在关联方关系" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>

    <details class="tips-collapse"><summary class="tips-summary">📋 编制提示</summary><ol class="tips-list">
      <li>选择大额、异常的客户或交易进行关联方穿透比对。</li>
      <li>查询客户工商/银行/税务信息，关注地址、董监高、联系方式等信息。</li>
      <li>取得发行人实控人/董高监及密切家庭成员的对外投资清单与客户股东/经办人比对。</li>
      <li>取得保荐机构/PE等利益相关方清单与重要客户比对。</li>
      <li>获取确认函确认除薪酬/分红外无任何形式交易。</li>
      <li>表格中各部门列填写该姓名在对应部门出现的匹配次数。</li>
    </ol></details>
  </template>
  <template v-if="editorMode==='在线编辑'"><div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="识别未披露的关联方D4-27" :readonly="isReadonly" /></div></template>
</div>
</template>

<style scoped>
.d4-undisclosed-rp{padding:16px 20px;font-size:13px}.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:20px;padding:14px 18px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:10px 16px;min-width:110px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card:hover{box-shadow:0 2px 8px rgba(0,0,0,.08)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-card.stat-warn{border-left:3px solid #f56c6c}.stat-card.stat-ok{border-left:3px solid #67c23a}.stat-card.stat-amount{border-left:3px solid #e6a23c}.stat-value{font-size:18px;font-weight:700;color:#303133;font-variant-numeric:tabular-nums}.stat-unit{font-size:12px;font-weight:400;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.guide-strip{display:flex;align-items:center;gap:6px;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}.guide-strip-label{font-weight:600;color:#67c23a;font-size:12px}.guide-chip{background:#fff;border:1px solid #c2e7b0;border-radius:4px;padding:2px 8px;font-size:12px;color:#529b2e;cursor:help}.guide-arrow{color:#a8abb2;font-size:12px}
.methodology-collapse{margin-bottom:14px;border-radius:6px;border:1px solid #faecd8;border-left:3px solid #e6a23c;background:#fffbf0}.methodology-summary{cursor:pointer;padding:8px 14px;font-size:13px;font-weight:500;color:#b88230}.methodology-body{padding:8px 14px 12px;font-size:12px;color:#606266;line-height:1.8}.method-objective{margin-bottom:8px}.method-process{margin-bottom:4px}.method-steps{padding-left:4px}.method-step{margin-bottom:6px}.step-num{display:inline-block;background:#e6a23c;color:#fff;border-radius:3px;padding:1px 6px;font-size:11px;margin-right:6px;min-width:16px;text-align:center}
.rp-table{font-size:12px}.rp-table :deep(.el-table__cell){padding:4px 2px}.rp-table :deep(.row-match td){background-color:#fef0f0 !important}
.auto-calc{color:#409eff;font-weight:600;border-bottom:1px dashed #a0cfff;cursor:help}
.add-row-bar{margin:12px 0 24px;text-align:center}
.audit-opinion-card{margin-bottom:20px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.tips-collapse{margin-bottom:16px;border-radius:6px;border:1px solid #fde2e2;border-left:3px solid #f56c6c}.tips-summary{cursor:pointer;padding:8px 14px;font-size:13px;font-weight:500;color:#f56c6c}.tips-list{margin:8px 14px 12px;padding-left:18px;font-size:12px;color:#606266;line-height:2}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
