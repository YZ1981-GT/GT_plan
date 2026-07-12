<script setup lang="ts">
/**
 * D4TabInterviewSummary — D4-30 客户访谈记录汇总表
 *
 * 转置表：行=17个访谈维度，列=N个客户
 * 三模式：卡片视图(逐客户填写) / 矩阵视图(对比) / 在线编辑
 * 底部10条红字访谈核对提示
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

// ─── 访谈维度定义 ─────────────────────────────────────────────────────
const INTERVIEW_FIELDS = [
  { key: 'time', label: '访谈时间' },
  { key: 'reason', label: '访谈原因', placeholder: '发行人第X大客户/本期新增客户/采购价格异常客户' },
  { key: 'method', label: '访谈方式', placeholder: '实地走访/视频访谈/电话访谈' },
  { key: 'regAddress', label: '被访谈公司注册地址' },
  { key: 'visitAddress', label: '实地走访公司地址' },
  { key: 'interviewee', label: '接受访谈人员及身份', placeholder: '身份信息、职务信息、具体负责的工作等' },
  { key: 'auditor', label: '参与访谈的审计人员' },
  { key: 'others', label: '参与访谈的其他人员' },
  { key: 'travelInfo', label: '访谈人员行程信息', placeholder: '车票/机票/住宿发票复印件或照片' },
  { key: 'onSiteConfirm', label: '是否现场函证' },
  { key: 'keyPoints', label: '访谈关注要点' },
  { key: 'contractCheck', label: '合同执行核对情况' },
  { key: 'amountMatch', label: '交易金额核对是否一致' },
  { key: 'balanceMatch', label: '往来余额核对是否一致' },
  { key: 'conclusion', label: '访谈结论' },
  { key: 'indexRef', label: '访谈表索引' },
]

interface InterviewCustomer { id: string; name: string; fields: Record<string, string> }

// 自定义维度（用户可添加额外检查项，对应源模板中"……"行）
const customDimensions = ref<{ key: string; label: string }[]>([])

const customers = ref<InterviewCustomer[]>([])
const auditNote = ref(''); const auditConclusion = ref('')
let debounceTimer: ReturnType<typeof setTimeout> | null = null

function loadData() {
  const r = props.allResponses.get('D4-30-customers')
  if (r?.remark) {
    try {
      const p = JSON.parse(r.remark)
      if (p && typeof p === 'object' && !Array.isArray(p)) {
        // 新格式: { customers: [...], customDimensions: [...] }
        customers.value = p.customers || []
        customDimensions.value = p.customDimensions || []
        return
      }
      if (Array.isArray(p)) { customers.value = p; customDimensions.value = []; return }
    } catch {}
  }
  customers.value = []; customDimensions.value = []
}
function loadNote() { auditNote.value = props.allResponses.get('D4-30-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-30-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-30-customers')?.remark, loadData, { immediate: true })
watch(() => props.allResponses.get('D4-30-note')?.remark, loadNote, { immediate: true })

async function handleAddCustomer() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入客户名称', '添加访谈客户', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { customers.value.push({ id: `iv-${Date.now().toString(36)}-${Math.random().toString(36).slice(2,6)}`, name: value.trim(), fields: {} }); activeIdx.value = customers.value.length - 1; persistAll() } } catch {} }
function removeCustomer(id: string) { if (props.isReadonly) return; customers.value = customers.value.filter(c => c.id !== id); persistAll() }
function updateField(custId: string, fieldKey: string, value: string) { if (props.isReadonly) return; const c = customers.value.find(x => x.id === custId); if (c) { c.fields[fieldKey] = value; persistAll() } }
function updateName(id: string, name: string) { if (props.isReadonly) return; const c = customers.value.find(x => x.id === id); if (c) { c.name = name; persistAll() } }

async function addCustomDimension() {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入自定义检查项名称', '添加检查维度', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' })
    if (value?.trim()) {
      const key = `custom_${Date.now().toString(36)}`
      customDimensions.value.push({ key, label: value.trim() })
      persistAll()
    }
  } catch {}
}
function removeCustomDimension(key: string) { if (props.isReadonly) return; customDimensions.value = customDimensions.value.filter(d => d.key !== key); persistAll() }

// 合并固定维度 + 自定义维度
const allFields = computed(() => [...INTERVIEW_FIELDS, ...customDimensions.value.map(d => ({ key: d.key, label: d.label, placeholder: '' }))])

function persistAll() {
  props.allResponses.set('D4-30-customers', { item_id: 'D4-30-customers', conclusion: null, remark: JSON.stringify({ customers: customers.value, customDimensions: customDimensions.value }) })
  props.allResponses.set('D4-30-note', { item_id: 'D4-30-note', conclusion: null, remark: auditNote.value })
  props.allResponses.set('D4-30-conclusion', { item_id: 'D4-30-conclusion', conclusion: null, remark: auditConclusion.value })
  if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; const keys = ['D4-30-customers','D4-30-note','D4-30-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) }, 2000)
}
function updateAuditNote(v: string) { if (props.isReadonly) return; auditNote.value = v; persistAll() }
function updateAuditConclusion(v: string) { if (props.isReadonly) return; auditConclusion.value = v; persistAll() }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); const keys = ['D4-30-customers','D4-30-note','D4-30-conclusion']; window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: keys.map(k => props.allResponses.get(k)).filter(Boolean) } })) } })

const editorMode = ref<string>('卡片视图'); const modeOptions = ['卡片视图', '矩阵视图', '在线编辑']
const activeIdx = ref(0)
const activeCustomer = computed(() => customers.value[activeIdx.value] || null)

const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)
async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于客户访谈汇总(D4-30)结果生成审计说明', customerCount: customers.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于访谈汇总结果生成审计结论', noteText: auditNote.value, customerCount: customers.value.length } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
</script>

<template>
<div class="d4-interview-summary">
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="exportTemplate('D4-30')">导出模板</el-dropdown-item><el-dropdown-item @click="exportData('D4-30')">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="(f:any)=>importData('D4-30',f.raw||f)"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-31" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-30-interview')">💬 复核</el-button></div></div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ customers.length }}<span class="stat-unit">家</span></div><div class="stat-label">已访谈客户</div></div>
  </div>

  <!-- ═══ 卡片视图 ═══ -->
  <template v-if="editorMode === '卡片视图'">
    <!-- 使用说明 -->
    <div class="usage-guide">
      <span class="usage-icon">💡</span>
      <span class="usage-text">点击下方"添加客户"创建访谈记录卡片，逐项填写访谈时间、方式、关注要点等信息。可添加自定义检查项。切换"矩阵视图"横向对比多个客户的访谈情况。</span>
    </div>
    <div class="customer-tabs">
      <el-tabs v-model="activeIdx" type="card" @tab-remove="(name:any) => removeCustomer(customers[Number(name)]?.id)">
        <el-tab-pane v-for="(cust, idx) in customers" :key="cust.id" :label="cust.name||`客户${idx+1}`" :name="idx" :closable="!isReadonly" />
      </el-tabs>
    </div>
    <div v-if="activeCustomer" class="card-content">
      <div class="card-header"><el-input v-model="activeCustomer.name" size="default" :disabled="isReadonly" class="customer-name-input" @change="updateName(activeCustomer.id, activeCustomer.name)" /></div>
      <div v-for="field in allFields" :key="field.key" class="field-row">
        <label>{{ field.label }}</label>
        <el-input :model-value="activeCustomer.fields[field.key]||''" size="small" :disabled="isReadonly" :placeholder="field.placeholder||''" @input="(v:string)=>updateField(activeCustomer.id, field.key, v)" />
        <el-button v-if="customDimensions.some(d => d.key === field.key)" link type="danger" size="small" :disabled="isReadonly" @click="removeCustomDimension(field.key)" title="删除此自定义项">×</el-button>
      </div>
      <div class="add-dimension-bar">
        <el-button size="small" text :disabled="isReadonly" @click="addCustomDimension">+ 添加自定义检查项</el-button>
      </div>
    </div>
    <el-empty v-else description="请添加客户开始记录访谈" :image-size="80">
      <el-button type="primary" :disabled="isReadonly" @click="handleAddCustomer"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button>
    </el-empty>
  </template>

  <!-- ═══ 矩阵视图 ═══ -->
  <template v-else-if="editorMode === '矩阵视图'">
    <el-table :data="allFields" border class="matrix-table" max-height="550">
      <el-table-column label="项目" min-width="140" fixed><template #default="{ row }">{{ row.label }}</template></el-table-column>
      <el-table-column v-for="cust in customers" :key="cust.id" :label="cust.name" min-width="130" align="center"><template #default="{ row }"><span>{{ cust.fields[row.key] || '—' }}</span></template></el-table-column>
    </el-table>
    <div v-if="!customers.length" style="padding:20px 0;text-align:center;"><el-empty description="暂无访谈数据" :image-size="60" /></div>
  </template>

  <!-- ═══ 在线编辑 ═══ -->
  <template v-else-if="editorMode === '在线编辑'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="客户访谈记录汇总表D4-30" :readonly="isReadonly" /></div>
  </template>

  <!-- 非OO共享区 -->
  <template v-if="editorMode !== '在线编辑'">
    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录访谈发现" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>

    <!-- 红字提示（访谈核对和注意事项） -->
    <details class="tips-collapse">
      <summary class="tips-summary">⚠️ 访谈核对和注意事项（提示）</summary>
      <div class="tips-body">
        <p class="tips-intro">提示1：走访的范围——主要客户（如前十名客户）；新增的主要客户；存在疑虑的重要客户。</p>
        <p class="tips-intro">提示2：访谈需核对和注意事项：</p>
        <ol class="tips-list">
          <li>走访地址与注册地址是否一致？不一致的原因是否合理？公司基本情况是否与工商信息查询一致？走访公司地址是否与百度地图等查询走访地址一致？</li>
          <li>交易内容是否与走访公司实际业务范围一致？</li>
          <li>交易金额是否与走访公司规模（注册资本、人数、设备数量等）匹配？</li>
          <li>交易价格是否与同行业类似交易一致？</li>
          <li>是否核实走访对象身份？</li>
          <li>是否根据走访公司及访谈对象具体情况修改访谈问卷？</li>
          <li>是否现场取得盖公章的函证回函（交易、往来、关联方关系确认）？</li>
          <li>是否同为客户和供应商？理由是否合理？</li>
          <li>是否存在异常情况（如地址与被审计单位关联方相同或相近、已处于停产状态、产能利用率异常、无法证明相关产品来自被审计单位）？</li>
          <li>保留访谈对象身份证复印件、名片/工牌复印件、与访谈对象合影（厂区门口、仓库、车间等地）、走访公司工作现场照片。</li>
        </ol>
      </div>
    </details>
  </template>
</div>
</template>

<style scoped>
.d4-interview-summary{padding:16px 20px;font-size: var(--wp-font-size, 13px)}
.toolbar{display:flex;justify-content:space-between;align-items:center;margin-bottom:20px;flex-wrap:wrap;gap:8px}.toolbar-left{display:flex;align-items:center}.toolbar-right{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.stats-dashboard{display:flex;gap:12px;margin-bottom:16px;padding:12px 16px;background:linear-gradient(135deg,#f8f9fe 0%,#f0f4ff 100%);border-radius:10px;border:1px solid #e4e7ed}.stat-card{padding:8px 14px;min-width:100px;border-radius:8px;background:#fff;border:1px solid #ebeef5;box-shadow:0 1px 3px rgba(0,0,0,.04)}.stat-card.stat-primary{border-left:3px solid #409eff}.stat-value{font-size:18px;font-weight:700;color:#303133}.stat-unit{font-size:12px;color:#909399;margin-left:2px}.stat-label{font-size:12px;color:#909399;margin-top:2px}
.customer-tabs{display:flex;align-items:center;gap:8px;margin-bottom:12px}.customer-tabs :deep(.el-tabs){flex:1}.customer-tabs :deep(.el-tabs__header){margin-bottom:0}
.usage-guide{display:flex;align-items:flex-start;gap:8px;margin-bottom:14px;padding:10px 14px;background:#f0f9eb;border-radius:6px;border:1px solid #e1f3d8}.usage-icon{font-size:16px;flex-shrink:0;margin-top:1px}.usage-text{font-size:12px;color:#529b2e;line-height:1.6}
.card-content{border:1px solid #ebeef5;border-radius:8px;padding:16px;background:#fafbfc}.card-header{margin-bottom:12px}.customer-name-input{max-width:280px}.customer-name-input :deep(.el-input__inner){font-size:15px;font-weight:600}
.field-row{display:flex;align-items:center;gap:12px;margin-bottom:8px}.field-row label{min-width:140px;font-size:12px;color:#606266;flex-shrink:0}.field-row :deep(.el-input){flex:1}
.add-dimension-bar{margin-top:12px;padding-top:8px;border-top:1px dashed #e4e7ed}
.matrix-table{font-size: var(--wp-font-size, 13px);margin-bottom:20px}.matrix-table :deep(.el-table__cell){padding:5px 6px;font-size: var(--wp-font-size, 13px)}
:deep(.el-empty){padding:32px 0}
.audit-opinion-card{margin-top:20px;margin-bottom:16px}.opinion-header{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.opinion-title{font-size:14px;font-weight:600;color:#303133}.opinion-actions{margin-left:auto;display:flex;gap:8px}.opinion-body{display:flex;flex-direction:column;gap:14px}.opinion-field label{display:block;font-size:12px;color:#909399;margin-bottom:4px;font-weight:500}
.tips-collapse{margin-bottom:16px;border-radius:6px;border:1px solid #fde2e2;border-left:3px solid #f56c6c;background:#fef0f0}.tips-summary{cursor:pointer;padding:10px 14px;font-size: var(--wp-font-size, 13px);font-weight:500;color:#f56c6c}.tips-body{padding:8px 14px 14px;font-size:12px;color:#606266;line-height:1.9}.tips-intro{margin-bottom:6px;font-weight:500}.tips-list{margin:0;padding-left:18px}.tips-list li{margin-bottom:3px}
.oo-container{min-height:600px;height:calc(100vh - 280px);border-radius:8px;overflow:hidden}
</style>
