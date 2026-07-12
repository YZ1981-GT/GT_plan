<script setup lang="ts">
/**
 * D4TabProductPrice — D4-11 产品销售价格分析
 *
 * 对齐源模板（openpyxl实读 "产品销售价格分析D4-11"）：
 * 一、审计目标
 * 二、审计过程
 * 主表15列：序号/客户名称/品种规格/销售单价/销售数量/开票日期/销售订单(凭证)/订单日期
 *          /商品销售价格表所列单价/与定价政策差异(=D-I)/I/同期市场价格/与市价差异(=D-K)/K
 *          /差异原因分析/同期市场价格来源(索引号)/备注
 * 三、审计说明  四、审计结论
 */
import { ref, computed, inject, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// 双模式（结构化视图 / 在线编辑）
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get(`/api/workpapers/onlyoffice/health`, { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

const auditObjective = '利润表中记录的营业收入已发生，且与被审计单位有关。'

// ─── 审计过程 ─────────────────────────────────────────────────────────
const auditProcess = ref('')
function loadAuditProcess() { auditProcess.value = props.allResponses.get('D4-11-audit-process')?.remark || '' }
watch(() => props.allResponses.get('D4-11-audit-process')?.remark, () => loadAuditProcess(), { immediate: true })
function updateAuditProcess(val: string) { if (props.isReadonly) return; auditProcess.value = val; persist('D4-11-audit-process', val) }

// ─── 数据 ────────────────────────────────────────────────────────────
interface PriceRow {
  customer: string       // 客户名称
  product: string        // 品种/规格
  unitPrice: number      // 销售单价 D
  quantity: number       // 销售数量 E
  invoiceDate: string    // 开票日期 F
  orderNo: string        // 销售订单(凭证) G
  orderDate: string      // 订单日期 H
  listPrice: number      // 商品销售价格表所列单价 I
  marketPrice: number    // 同期市场价格 K
  reason: string         // 差异原因分析 M
  priceSource: string    // 同期市场价格来源(索引号) N
  remark: string         // 备注 O
}

const rows = ref<PriceRow[]>([])

function loadData() {
  const resp = props.allResponses.get('D4-11-data')
  if (resp?.remark) {
    try { const d = JSON.parse(resp.remark); if (Array.isArray(d)) { rows.value = d; return } } catch {}
  }
  rows.value = []
}
watch(() => props.allResponses.get('D4-11-data')?.remark, () => loadData(), { immediate: true })

// 计算列
interface ComputedRow extends PriceRow {
  policyDiff: number | null  // J=(D-I)/I
  marketDiff: number | null  // L=(D-K)/K
}
const computedRows = computed<ComputedRow[]>(() => rows.value.map(r => ({
  ...r,
  policyDiff: r.listPrice === 0 ? (r.unitPrice === 0 ? null : 1) : (r.unitPrice - r.listPrice) / r.listPrice,
  marketDiff: r.marketPrice === 0 ? (r.unitPrice === 0 ? null : 1) : (r.unitPrice - r.marketPrice) / r.marketPrice,
})))

function addRow() {
  if (props.isReadonly) return
  rows.value.push({ customer: '', product: '', unitPrice: 0, quantity: 0, invoiceDate: '', orderNo: '', orderDate: '', listPrice: 0, marketPrice: 0, reason: '', priceSource: '', remark: '' })
  persistData()
}
function removeRow(idx: number) { if (props.isReadonly) return; rows.value.splice(idx, 1); persistData() }
function updateData() { if (props.isReadonly) return; persistData() }
function persistData() {
  props.allResponses.set('D4-11-data', { item_id: 'D4-11-data', conclusion: null, remark: JSON.stringify(rows.value) })
  debounceSave()
}

// ─── 审计说明/结论 ────────────────────────────────────────────────────
const auditNote = ref('')
const auditConclusion = ref('')
function loadNoteConclusion() { auditNote.value = props.allResponses.get('D4-11-note')?.remark || ''; auditConclusion.value = props.allResponses.get('D4-11-conclusion')?.remark || '' }
watch(() => props.allResponses.get('D4-11-note')?.remark, () => loadNoteConclusion(), { immediate: true })
function updateNote(val: string) { if (props.isReadonly) return; auditNote.value = val; persist('D4-11-note', val) }
function updateConclusion(val: string) { if (props.isReadonly) return; auditConclusion.value = val; persist('D4-11-conclusion', val) }

// ─── 格式化 ──────────────────────────────────────────────────────────
function fmtPercent(val: number | null): string { if (val == null) return '-'; return (val * 100).toFixed(2) + '%' }

// ─── AI辅助 ──────────────────────────────────────────────────────────
const aiAvailable = ref(false)
const aiLoadingKey = ref<string | null>(null)
async function checkAiHealth() { try { const res = await http.get('/api/ai/health', { _silent: true } as any); const s = res.data?.data?.status ?? res.data?.status; aiAvailable.value = s === 'healthy' || s === 'degraded' } catch { aiAvailable.value = false } }
checkAiHealth()
async function callD4Ai(section: string, existing: string): Promise<string> { const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, { section, existingContent: existing, relatedContext: {} }, { _silent: true } as any); return res.data?.data?.content ?? res.data?.content ?? '' }
const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

async function generateNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'note'
  try {
    const abnormals = computedRows.value.filter(r => (r.policyDiff != null && Math.abs(r.policyDiff) > 0.1) || (r.marketDiff != null && Math.abs(r.marketDiff) > 0.1))
    const ctx = `异常定价产品：${abnormals.length ? abnormals.map(r => `${r.customer}-${r.product}(定价差${fmtPercent(r.policyDiff)},市价差${fmtPercent(r.marketDiff)})`).join('、') : '无'}\n总行数：${rows.value.length}`
    const text = await callD4Ai('analysis-note', ctx)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}
async function generateConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiLoadingKey.value = 'conclusion'
  try {
    const text = await callD4Ai('adj-conclusion', `审计说明：${auditNote.value || '（未填写）'}`)
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text.length > 300 ? text.slice(0, 300) + '…' : text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' })
    updateConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiLoadingKey.value = null }
}

// ─── 导入导出 ────────────────────────────────────────────────────────
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({ wpId: toRef(props, 'wpId') as Ref<string>, projectId: toRef(props, 'projectId') as Ref<string> })
function handleExportTemplate() { exportTemplate('D4-11' as any) }
function handleExportData() { exportData('D4-11' as any) }
function handleImportUpload(file: File): boolean { importData('D4-11' as any, file).then(r => { if (r && r.rowCount > 0) loadData() }); return false }

// ─── 持久化 ──────────────────────────────────────────────────────────
let debounceTimer: ReturnType<typeof setTimeout> | null = null
function persist(itemId: string, value: string) { props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value }); debounceSave() }
function debounceSave() { if (debounceTimer) clearTimeout(debounceTimer); debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000) }
function flushSave() { const keys = ['D4-11-audit-process', 'D4-11-data', 'D4-11-note', 'D4-11-conclusion']; const items = keys.map(k => props.allResponses.get(k)).filter(Boolean); window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } })) }
onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); flushSave() } })
</script>


<template>
  <div class="d4-product-price">

    <!-- 双模式切换 -->
    <div class="mode-bar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">    <!-- 一、审计目标 -->
    <section class="sec">
      <h4 class="sec-title">一、审计目标</h4>
      <div class="objective-list"><p class="objective-item">{{ auditObjective }}</p></div>
    </section>

    <!-- 二、审计过程 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">二、审计过程</h4>
        <el-tooltip :content="aiTip" placement="top">
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable">🤖 AI辅助</el-button>
        </el-tooltip>
      </div>
      <el-input type="textarea" :rows="2" :model-value="auditProcess" :disabled="isReadonly"
        placeholder="1.选取定价有较大或异常变化的产品进行测试，检查售价变动是否符合定价政策，价格变动是否合理。"
        @input="(v: string) => updateAuditProcess(v)" />
    </section>

    <!-- 主表 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">产品销售价格分析</h4>
        <div class="sec-actions">
          <el-dropdown size="small" trigger="click" :disabled="isReadonly">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
                <el-dropdown-item><el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImportUpload" :disabled="importing"><span>{{ importing ? '导入中...' : '导入数据' }}</span></el-upload></el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-tooltip content="批量数据建议：先导出模板在Excel中填写后导入" placement="top" :show-after="300">
            <el-button size="small" :disabled="isReadonly" @click="addRow">+ 增行</el-button>
          </el-tooltip>
          <GtIndexChip value="wp:D4-10" :context-project-id="projectId" />
        </div>
      </div>

      <el-table :data="computedRows" border class="price-table" max-height="520"
        :header-cell-style="{ fontSize: '13px', fontWeight: '600', background: '#f5f7fa', textAlign: 'center' }">
        <el-table-column label="序号" width="50" align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>
        <el-table-column label="客户名称" min-width="110">
          <template #default="{ $index }"><el-input v-model="rows[$index].customer" size="small" :disabled="isReadonly" placeholder="客户" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="品种/规格" min-width="100">
          <template #default="{ $index }"><el-input v-model="rows[$index].product" size="small" :disabled="isReadonly" placeholder="品种" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售单价" width="90" align="right">
          <template #default="{ $index }"><el-input-number v-model="rows[$index].unitPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售数量" width="80" align="right">
          <template #default="{ $index }"><el-input-number v-model="rows[$index].quantity" :controls="false" size="small" :disabled="isReadonly" class="num-cell" @change="updateData" /></template>
        </el-table-column>
        <el-table-column label="开票日期" width="105">
          <template #default="{ $index }"><el-input v-model="rows[$index].invoiceDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="销售订单" min-width="90">
          <template #default="{ $index }"><el-input v-model="rows[$index].orderNo" size="small" :disabled="isReadonly" placeholder="" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="订单日期" width="105">
          <template #default="{ $index }"><el-input v-model="rows[$index].orderDate" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="定价表单价" width="95" align="right">
          <template #default="{ $index }">
            <el-tooltip content="商品销售价格表所列单价（定价政策基准）" placement="top" :show-after="200">
              <el-input-number v-model="rows[$index].listPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" />
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="与定价差异" width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: (销售单价-定价表单价)/定价表单价" placement="top" :show-after="200">
              <span :class="['has-formula', { 'val-exceed': row.policyDiff != null && Math.abs(row.policyDiff) > 0.1 }]">{{ fmtPercent(row.policyDiff) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="市场价格" width="90" align="right">
          <template #default="{ $index }"><el-input-number v-model="rows[$index].marketPrice" :controls="false" size="small" :disabled="isReadonly" :precision="2" class="num-cell" @change="updateData" /></template>
        </el-table-column>
        <el-table-column label="与市价差异" width="90" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式: (销售单价-市场价格)/市场价格" placement="top" :show-after="200">
              <span :class="['has-formula', { 'val-exceed': row.marketDiff != null && Math.abs(row.marketDiff) > 0.1 }]">{{ fmtPercent(row.marketDiff) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="120">
          <template #default="{ $index }"><el-input v-model="rows[$index].reason" size="small" :disabled="isReadonly" placeholder="" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="价格来源" min-width="90">
          <template #default="{ $index }"><el-input v-model="rows[$index].priceSource" size="small" :disabled="isReadonly" placeholder="索引号" @input="updateData" /></template>
        </el-table-column>
        <el-table-column label="备注" min-width="80">
          <template #default="{ $index }"><el-input v-model="rows[$index].remark" size="small" :disabled="isReadonly" @input="updateData" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="40" fixed="right">
          <template #default="{ $index }"><el-button size="small" type="danger" text @click="removeRow($index)">✕</el-button></template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 三、审计说明 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">三、审计说明</h4>
        <div class="sec-actions">
          <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiLoadingKey === 'note'" :disabled="isReadonly || !aiAvailable" @click="generateNote">🤖 AI辅助</el-button></el-tooltip>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-11-note')">💬</el-button>
        </div>
      </div>
      <el-input type="textarea" :rows="4" :model-value="auditNote" :disabled="isReadonly" placeholder="请输入产品销售价格分析审计说明..." @input="(v: string) => updateNote(v)" />
    </section>

    <!-- 四、审计结论 -->
    <section class="sec">
      <div class="sec-header">
        <h4 class="sec-title">四、审计结论</h4>
        <el-tooltip :content="aiTip" placement="top"><el-button size="small" type="primary" plain :loading="aiLoadingKey === 'conclusion'" :disabled="isReadonly || !aiAvailable" @click="generateConclusion">🤖 AI辅助</el-button></el-tooltip>
      </div>
      <el-input type="textarea" :rows="3" :model-value="auditConclusion" :disabled="isReadonly" placeholder="请输入审计结论..." @input="(v: string) => updateConclusion(v)" />
    </section>
  
    </template>

    <!-- OnlyOffice 在线编辑 -->
    <template v-else>
      <div style="min-height: 600px; height: calc(100vh - 280px);">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="产品销售价格分析D4-11"
          :readonly="isReadonly"
        />
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-product-price { padding: 16px; }
.sec { margin-bottom: 20px; }
.sec-title { font-size: 14px; font-weight: 600; color: #303133; margin: 0 0 8px; }
.sec-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.sec-actions { display: flex; gap: 8px; align-items: center; }
.objective-list { padding: 10px 14px; background: #f5f7fa; border-radius: 6px; }
.objective-item { margin: 0; font-size: var(--wp-font-size, 13px); color: #303133; line-height: 1.7; }
.price-table { font-size: var(--wp-font-size, 13px); }
.price-table :deep(.el-table__cell) { font-size: var(--wp-font-size, 13px); padding: 4px 0; }
.num-cell { width: 100%; }
.num-cell :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.has-formula { border-bottom: 1px dashed #909399; cursor: help; }
.val-exceed { color: #f56c6c; font-weight: 600; }

.mode-bar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
</style>
