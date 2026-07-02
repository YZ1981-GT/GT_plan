<script setup lang="ts">
/**
 * D4TabCustomerDetail — D4-29 客户信息检查表
 *
 * 三模式：卡片视图(逐客户填写) / 矩阵视图(行=字段,列=客户只读对比) / 在线编辑
 * 31个检查字段 × N个客户，底部CAS18号舞弊风险提示折叠
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4CustomerDetail, CUSTOMER_FIELDS, FIELD_GROUPS } from '../../composables/useD4CustomerDetail'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus } from '@element-plus/icons-vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  customers, auditNote, auditConclusion,
  customerCount, relatedCount, completionRate,
  addCustomer, removeCustomer, updateField, updateCustomerName,
  updateAuditNote, updateAuditConclusion,
} = useD4CustomerDetail({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  isReadonly: computed(() => props.isReadonly),
})

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })

// ─── Mode ────────────────────────────────────────────────────────────
const editorMode = ref<string>('卡片视图')
const modeOptions = ['卡片视图', '矩阵视图', '在线编辑']
const activeCustomerIdx = ref(0)

// ─── AI ──────────────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() { try { const r = await http.get('/api/ai/health', { _silent: true } as any); aiAvailable.value = (r.data?.data?.status ?? r.data?.status) === 'healthy' || (r.data?.data?.status ?? r.data?.status) === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')
const aiNoteLoading = ref(false); const aiConclusionLoading = ref(false)

async function genNote() { if (props.isReadonly || !aiAvailable.value) return; aiNoteLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'analysis-note', existingContent: auditNote.value, relatedContext: { task: '基于客户信息检查(D4-29)结果生成审计说明', customerCount: customerCount.value, relatedCount: relatedCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditNote(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiNoteLoading.value = false } }
async function genConclusion() { if (props.isReadonly || !aiAvailable.value) return; aiConclusionLoading.value = true; try { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section: 'adj-conclusion', existingContent: auditConclusion.value, relatedContext: { task: '基于客户信息检查结果生成审计结论', noteText: auditNote.value, customerCount: customerCount.value, relatedCount: relatedCount.value } }, { _silent: true } as any); const t = res.data?.data?.content ?? res.data?.content ?? ''; if (!t) { ElMessage.warning('AI 未生成内容'); return }; await ElMessageBox.confirm(t, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } }); updateAuditConclusion(t) } catch (e: any) { if (e !== 'cancel') ElMessage.warning('AI 生成失败') } finally { aiConclusionLoading.value = false } }

async function handleAddCustomer() { if (props.isReadonly) return; try { const { value } = await ElMessageBox.prompt('请输入客户名称', '添加客户', { confirmButtonText: '确认', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '不能为空' }); if (value?.trim()) { addCustomer(value.trim()); activeCustomerIdx.value = customers.value.length - 1 } } catch {} }

function handleExportTemplate() { exportTemplate('D4-29') }
function handleExportData() { exportData('D4-29') }
async function handleImportFile(f: any) { await importData('D4-29', f.raw || f) }

// 当前卡片客户
const activeCustomer = computed(() => customers.value[activeCustomerIdx.value] || null)

// 字段按组分组
const fieldsByGroup = computed(() => FIELD_GROUPS.map(g => ({ ...g, fields: CUSTOMER_FIELDS.filter(f => f.group === g.key) })))
</script>

<template>
<div class="d4-customer-detail">
  <!-- 工具条 -->
  <div class="toolbar"><div class="toolbar-left"><el-segmented v-model="editorMode" :options="modeOptions" size="small" /></div><div class="toolbar-right"><el-dropdown trigger="click" size="small"><el-button size="small">导入导出 ▾</el-button><template #dropdown><el-dropdown-menu><el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item><el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item><el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="isReadonly||importing" @change="handleImportFile"><span>导入数据</span></el-upload></el-dropdown-item></el-dropdown-menu></template></el-dropdown><GtIndexChip value="wp:D4-28" :context-project-id="projectId" /><el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-29-detail')">💬 复核</el-button></div></div>

  <!-- 仪表板 -->
  <div class="stats-dashboard">
    <div class="stat-card stat-primary"><div class="stat-value">{{ customerCount }}<span class="stat-unit">家</span></div><div class="stat-label">检查客户</div></div>
    <div class="stat-card" :class="relatedCount > 0 ? 'stat-warn' : 'stat-ok'"><div class="stat-value">{{ relatedCount }}<span class="stat-unit">家</span></div><div class="stat-label">关联方</div></div>
    <div class="stat-card stat-progress"><div class="stat-value">{{ completionRate }}%</div><div class="stat-label">字段完成度</div></div>
  </div>

  <!-- ═══ 卡片视图 ═══ -->
  <template v-if="editorMode === '卡片视图'">
    <!-- 使用说明 -->
    <div class="usage-guide">
      <span class="usage-icon">💡</span>
      <span class="usage-text">点击下方"添加客户"按钮创建客户卡片，逐项填写工商信息、股东、管理层及风险判断。切换"矩阵视图"可横向对比多个客户信息。</span>
    </div>
    <!-- 客户标签页 -->
    <div class="customer-tabs">
      <el-tabs v-model="activeCustomerIdx" type="card" @tab-remove="(name: any) => removeCustomer(customers[Number(name)]?.id)">
        <el-tab-pane v-for="(cust, idx) in customers" :key="cust.id" :label="cust.name || `客户${idx+1}`" :name="idx" :closable="!isReadonly" />
      </el-tabs>
    </div>

    <!-- 卡片内容 -->
    <div v-if="activeCustomer" class="card-content">
      <div class="card-header">
        <el-input v-model="activeCustomer.name" size="default" :disabled="isReadonly" class="customer-name-input" @change="updateCustomerName(activeCustomer.id, activeCustomer.name)" />
      </div>
      <div v-for="group in fieldsByGroup" :key="group.key" class="field-group" :style="{ borderLeftColor: group.color }">
        <div class="group-title">{{ group.label }}</div>
        <div class="fields-grid">
          <div v-for="field in group.fields" :key="field.key" class="field-item">
            <label>{{ field.label }}</label>
            <el-select v-if="field.type === 'select'" :model-value="activeCustomer.fields[field.key] || ''" size="small" :disabled="isReadonly" placeholder="请选择" @change="(v: string) => updateField(activeCustomer.id, field.key, v)">
              <el-option v-for="opt in field.options" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-input v-else-if="field.type === 'textarea'" :model-value="activeCustomer.fields[field.key] || ''" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" size="small" :disabled="isReadonly" @input="(v: string) => updateField(activeCustomer.id, field.key, v)" />
            <el-input v-else :model-value="activeCustomer.fields[field.key] || ''" size="small" :disabled="isReadonly" @input="(v: string) => updateField(activeCustomer.id, field.key, v)" />
          </div>
        </div>
      </div>
    </div>
    <el-empty v-else description="请添加客户开始检查" :image-size="80">
      <el-button type="primary" :disabled="isReadonly" @click="handleAddCustomer"><el-icon :size="14"><Plus /></el-icon> 添加客户</el-button>
    </el-empty>
  </template>

  <!-- ═══ 矩阵视图 ═══ -->
  <template v-else-if="editorMode === '矩阵视图'">
    <el-table :data="CUSTOMER_FIELDS" border class="matrix-table" max-height="600">
      <el-table-column label="检查项目" min-width="150" fixed>
        <template #default="{ row }">{{ row.label }}</template>
      </el-table-column>
      <el-table-column v-for="cust in customers" :key="cust.id" :label="cust.name" min-width="130" align="center">
        <template #default="{ row }">
          <span :class="{ 'risk-yes': row.key === 'isRelated' && cust.fields[row.key] === '是' }">{{ cust.fields[row.key] || '—' }}</span>
        </template>
      </el-table-column>
    </el-table>
    <div v-if="!customers.length" class="empty-matrix"><el-empty description="暂无客户数据" /></div>
  </template>

  <!-- ═══ 在线编辑 ═══ -->
  <template v-else-if="editorMode === '在线编辑'">
    <div class="oo-container"><GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="客户信息检查表D4-29" :readonly="isReadonly" /></div>
  </template>

  <!-- 非OO模式共享区域 -->
  <template v-if="editorMode !== '在线编辑'">
    <!-- 审计意见区 -->
    <el-card class="audit-opinion-card" shadow="never"><template #header><div class="opinion-header"><span class="opinion-title">审计意见区</span><div class="opinion-actions"><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly||!aiAvailable" @click="genNote">🤖 AI辅助说明</el-button></el-tooltip><el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly||!aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button></el-tooltip></div></div></template><div class="opinion-body"><div class="opinion-field"><label>三、审计说明</label><el-input type="textarea" :autosize="{minRows:3,maxRows:12}" :model-value="auditNote" :disabled="isReadonly" placeholder="记录客户信息核查发现的异常情况" @input="(v:string)=>updateAuditNote(v)" /></div><div class="opinion-field"><label>四、审计结论</label><el-input type="textarea" :autosize="{minRows:2,maxRows:8}" :model-value="auditConclusion" :disabled="isReadonly" placeholder="综合判断客户信息是否真实、是否存在第三方配合舞弊迹象" @input="(v:string)=>updateAuditConclusion(v)" /></div></div></el-card>

    <!-- CAS18号舞弊风险提示（红字折叠） -->
    <details class="fraud-tips-collapse">
      <summary class="fraud-tips-summary">⚠️ CAS18号——第三方配合舞弊特征提示（点击展开）</summary>
      <div class="fraud-tips-body">
        <p class="fraud-tips-intro">根据《中国注册会计师审计准则问题解答第18号——识别和应对第三方配合实施财务舞弊》，配合实施财务舞弊的第三方可能具有以下特征：</p>
        <ol class="fraud-tips-list">
          <li>经营时间较短。</li>
          <li>缴纳社保人数较少。</li>
          <li>为个人或个体工商户。</li>
          <li>注册资本与交易规模不匹配。</li>
          <li>交易规模与第三方所处行业状况不匹配。</li>
          <li>经营范围与交易性质不匹配。</li>
          <li>注册地址与被审计单位地址较为接近。</li>
          <li>不同第三方的工商登记信息相同或相近（股东、董监高、注册地址、联系方式等）。</li>
          <li>既是客户又是供应商，或受同一实际控制人控制。</li>
          <li>对被审计单位存在重大依赖（如被审计单位是其主要客户）。</li>
          <li>被审计单位向其销售的规模与其需求不匹配。</li>
          <li>连续审计期间对审计程序配合度持续较高，均能提供正面审计证据。</li>
          <li>曾经配合其他方实施财务舞弊。</li>
          <li>法律意识淡薄，合规性较差（近三年受过行政处罚）。</li>
          <li>股东或关键管理人员与被审计单位或其相关人员存在特殊关系。</li>
          <li>存在实现特定目的的需求（如考核、行业排名等做大收入的需求）。</li>
        </ol>
      </div>
    </details>
  </template>
</div>
</template>

<style scoped>
.d4-customer-detail { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.stats-dashboard { display: flex; gap: 12px; margin-bottom: 20px; padding: 14px 18px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { padding: 10px 16px; min-width: 100px; border-radius: 8px; background: #fff; border: 1px solid #ebeef5; box-shadow: 0 1px 3px rgba(0,0,0,0.04); }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-left: 3px solid #f56c6c; }
.stat-card.stat-ok { border-left: 3px solid #67c23a; }
.stat-card.stat-progress { border-left: 3px solid #e6a23c; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; font-variant-numeric: tabular-nums; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 2px; }

/* 卡片视图 */
.usage-guide { display: flex; align-items: flex-start; gap: 8px; margin-bottom: 14px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.usage-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.usage-text { font-size: 12px; color: #529b2e; line-height: 1.6; }
.customer-tabs { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.customer-tabs :deep(.el-tabs) { flex: 1; }
.customer-tabs :deep(.el-tabs__header) { margin-bottom: 0; }
.add-btn { flex-shrink: 0; }
.card-content { border: 1px solid #ebeef5; border-radius: 8px; padding: 16px; background: #fafbfc; }
.card-header { margin-bottom: 16px; }
.customer-name-input { max-width: 300px; }
.customer-name-input :deep(.el-input__inner) { font-size: 15px; font-weight: 600; }
.field-group { border-left: 3px solid #e4e7ed; padding: 12px 16px; margin-bottom: 12px; border-radius: 0 6px 6px 0; background: #fff; }
.group-title { font-size: 13px; font-weight: 600; color: #303133; margin-bottom: 10px; }
.fields-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 20px; }
.field-item { display: flex; flex-direction: column; gap: 3px; }
.field-item label { font-size: 12px; color: #909399; }
:deep(.el-empty) { padding: 32px 0; }
:deep(.el-empty__description) { margin-top: 8px; }

/* 矩阵视图 */
.matrix-table { font-size: 13px; margin-bottom: 24px; }
.matrix-table :deep(.el-table__cell) { padding: 4px 6px; font-size: 13px; }
.risk-yes { color: #f56c6c; font-weight: 600; }
.empty-matrix { padding: 40px 0; }

/* 审计意见区 */
.audit-opinion-card { margin-top: 24px; margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; font-weight: 500; }

/* CAS18舞弊提示折叠 */
.fraud-tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; background: #fef0f0; }
.fraud-tips-summary { cursor: pointer; padding: 10px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.fraud-tips-body { padding: 8px 14px 14px; font-size: 12px; color: #606266; line-height: 1.9; }
.fraud-tips-intro { margin-bottom: 8px; font-weight: 500; }
.fraud-tips-list { margin: 0; padding-left: 18px; }
.fraud-tips-list li { margin-bottom: 2px; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>
