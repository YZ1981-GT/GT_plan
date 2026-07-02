<script setup lang="ts">
/**
 * D4TabCompleteness — D4-15 营业收入完整性检查表
 *
 * 三维度交叉核对：发货单 × 发票 × 记账凭证
 * 双模式：表格视图 / 在线编辑
 * 支持行级OCR、自动一致性校验、AI辅助
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import useD4CompletenessCheck, { checkConsistency, mapOcrToCompleteness } from '../../composables/useD4CompletenessCheck'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'
import { Plus, Download } from '@element-plus/icons-vue'

// ─── Props ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── Composables ─────────────────────────────────────────────────────
const {
  items,
  auditNote,
  auditConclusion,
  itemCount,
  totalAmount,
  consistentCount,
  inconsistentCount,
  addItem,
  removeItem,
  updateField,
  updateAuditNote,
  updateAuditConclusion,
} = useD4CompletenessCheck({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  allResponses: computed(() => props.allResponses),
  isReadonly: computed(() => props.isReadonly),
})

const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Mode switching ──────────────────────────────────────────────────
const editorMode = ref<string>('表格视图')
const modeOptions = ['表格视图', '在线编辑']
// ─── AI / OO health ──────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()
// ─── Add row ─────────────────────────────────────────────────────────
function handleAddRow() {
  if (props.isReadonly) return
  addItem()
}
// ─── Remove row ──────────────────────────────────────────────────────
function handleRemoveRow(id: string) {
  if (props.isReadonly) return
  removeItem(id)
}

// ─── OCR handling ────────────────────────────────────────────────────
const ocrTargetId = ref('')
const ocrDimension = ref<'delivery' | 'invoice' | 'voucher'>('delivery')
const ocrDialogVisible = ref(false)
const ocrResult = ref<Record<string, any>>({})

async function handleOcrUpload(itemId: string, file: File) {
  ocrTargetId.value = itemId
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/contract-ocr`, formData, { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
    const fields = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }
    ocrResult.value = fields
    ocrDimension.value = 'delivery'
    ocrDialogVisible.value = true
  } catch { ElMessage.warning('OCR识别失败') }
}

function confirmOcrFill() {
  const mapped = mapOcrToCompleteness(ocrResult.value, ocrDimension.value)
  for (const [field, val] of Object.entries(mapped)) { updateField(ocrTargetId.value, ocrDimension.value, field, val) }
  ocrDialogVisible.value = false
  ElMessage.success('OCR结果已填入')
}

// ─── AI opinion ──────────────────────────────────────────────────────
const aiNoteLoading = ref(false)
const aiConclusionLoading = ref(false)

async function genNote() {
  if (props.isReadonly || !aiAvailable.value) return
  aiNoteLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-note', existingContent: auditNote.value || '',
      relatedContext: { task: '基于完整性检查已核对事项的一致性情况，生成审计说明', totalItems: itemCount.value, consistentCount: consistentCount.value, inconsistentCount: inconsistentCount.value, totalAmount: totalAmount.value },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计说明', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditNote(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiNoteLoading.value = false }
}

async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/d4/ai-generate`, {
      section: 'adj-conclusion', existingContent: auditConclusion.value || '',
      relatedContext: { task: '基于完整性检查结果，生成审计结论', noteText: auditNote.value || '', totalItems: itemCount.value, consistentCount: consistentCount.value, inconsistentCount: inconsistentCount.value },
    }, { _silent: true } as any)
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 审计结论', { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info', customStyle: { maxWidth: '600px' } })
    updateAuditConclusion(text)
  } catch (e: any) { if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败') }
  finally { aiConclusionLoading.value = false }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── Import/Export ───────────────────────────────────────────────────
function handleExportTemplate() { exportTemplate('D4-15') }
function handleExportData() { exportData('D4-15') }
async function handleImportFile(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  await importData('D4-15', file)
}

// ─── Consistency rate ────────────────────────────────────────────────
const consistencyRate = computed(() => {
  if (!itemCount.value) return 0
  return Math.round((consistentCount.value / itemCount.value) * 100)
})

// ─── Row class for inconsistent highlight ────────────────────────────
function rowClassName({ row }: { row: any }) {
  return row.isConsistent === false ? 'row-inconsistent' : ''
}
</script>

<template>
  <div class="d4-completeness">
    <!-- ═══ 顶部工具条 ═══ -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      </div>
      <div class="toolbar-right">
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false"
                  :disabled="isReadonly || importing" @change="handleImportFile">
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-14" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-15-completeness')">
          💬 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 统计仪表板 ═══ -->
    <div class="stats-dashboard">
      <div class="stat-card stat-primary">
        <div class="stat-value">{{ itemCount }}<span class="stat-unit">项</span></div>
        <div class="stat-label">检查事项数</div>
      </div>
      <div class="stat-card" :class="{ 'stat-warn': consistencyRate < 80 }">
        <div class="stat-value">{{ consistencyRate }}%</div>
        <div class="stat-label">一致率</div>
      </div>
      <div class="stat-card stat-amount">
        <div class="stat-value">{{ totalAmount ? (totalAmount / 10000).toFixed(2) : '—' }}<span class="stat-unit">万元</span></div>
        <div class="stat-label">检查金额</div>
      </div>
    </div>

    <!-- ═══ 非OO内容区 ═══ -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 方法论说明（默认折叠） -->
      <details class="methodology-collapse">
        <summary class="methodology-summary">📖 审计目标与完整性检查过程（点击展开）</summary>
        <div class="methodology-body">
          <p class="method-objective"><strong>审计目标：</strong>营业收入完整性认定——已发生的销售交易均已记录入账。</p>
          <div class="method-steps">
            <p class="method-step"><span class="step-num">步骤一</span>选取一定期间的发货单（或出库单），与对应发票、记账凭证核对。</p>
            <p class="method-step"><span class="step-num">步骤二</span>检查发货单所列品名、数量、金额是否与发票一致。</p>
            <p class="method-step"><span class="step-num">步骤三</span>检查发票信息是否与记账凭证一致，确认交易已完整入账。</p>
          </div>
        </div>
      </details>

      <!-- 引导条 -->
      <div class="guide-strip">
        <span class="guide-strip-label">编制流程：</span>
        <el-tooltip content="从发货单/出库单中选取样本作为检查起点" placement="bottom" :show-after="300">
          <span class="guide-chip">①选取发货单样本</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="根据发货单追查对应的销售发票，核对品名、数量、金额" placement="bottom" :show-after="300">
          <span class="guide-chip">②追查发票</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="根据发票追查记账凭证，确认交易已记录入账" placement="bottom" :show-after="300">
          <span class="guide-chip">③追查记账凭证</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="系统自动对比三个维度的金额、品名、数量是否一致" placement="bottom" :show-after="300">
          <span class="guide-chip">④核对一致性</span>
        </el-tooltip>
        <span class="guide-arrow">→</span>
        <el-tooltip content="填写审计说明与结论（可AI辅助生成）" placement="bottom" :show-after="300">
          <span class="guide-chip">⑤填审计意见</span>
        </el-tooltip>
      </div>

      <!-- ═══ 主表格 ═══ -->
      <el-table :data="items" border stripe class="completeness-table" :row-class-name="rowClassName">
        <!-- 固定列：序号 -->
        <el-table-column label="序号" width="60" fixed align="center">
          <template #default="{ $index }">{{ $index + 1 }}</template>
        </el-table-column>

        <!-- 发货单分组 -->
        <el-table-column label="发货单" align="center" class-name="col-delivery">
          <el-table-column label="日期" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.delivery.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateField(row.id, 'delivery', 'date', row.delivery.date)" />
            </template>
          </el-table-column>
          <el-table-column label="编号" min-width="110">
            <template #default="{ row }">
              <el-input v-model="row.delivery.number" size="small" :disabled="isReadonly" @change="updateField(row.id, 'delivery', 'number', row.delivery.number)" />
            </template>
          </el-table-column>
          <el-table-column label="品名" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.delivery.productName" size="small" :disabled="isReadonly" @change="updateField(row.id, 'delivery', 'productName', row.delivery.productName)" />
            </template>
          </el-table-column>
          <el-table-column label="数量" min-width="80">
            <template #default="{ row }">
              <el-input v-model="row.delivery.quantity" size="small" :disabled="isReadonly" @change="updateField(row.id, 'delivery', 'quantity', row.delivery.quantity)" />
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.delivery.amount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateField(row.id, 'delivery', 'amount', row.delivery.amount)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 发票分组 -->
        <el-table-column label="发票" align="center" class-name="col-invoice">
          <el-table-column label="日期" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.invoice.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateField(row.id, 'invoice', 'date', row.invoice.date)" />
            </template>
          </el-table-column>
          <el-table-column label="编号" min-width="110">
            <template #default="{ row }">
              <el-input v-model="row.invoice.number" size="small" :disabled="isReadonly" @change="updateField(row.id, 'invoice', 'number', row.invoice.number)" />
            </template>
          </el-table-column>
          <el-table-column label="品名" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.invoice.productName" size="small" :disabled="isReadonly" @change="updateField(row.id, 'invoice', 'productName', row.invoice.productName)" />
            </template>
          </el-table-column>
          <el-table-column label="数量" min-width="80">
            <template #default="{ row }">
              <el-input v-model="row.invoice.quantity" size="small" :disabled="isReadonly" @change="updateField(row.id, 'invoice', 'quantity', row.invoice.quantity)" />
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.invoice.amount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateField(row.id, 'invoice', 'amount', row.invoice.amount)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 记账凭证分组 -->
        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column label="日期" min-width="100">
            <template #default="{ row }">
              <el-input v-model="row.voucher.date" size="small" :disabled="isReadonly" placeholder="YYYY-MM-DD" @change="updateField(row.id, 'voucher', 'date', row.voucher.date)" />
            </template>
          </el-table-column>
          <el-table-column label="编号" min-width="110">
            <template #default="{ row }">
              <el-input v-model="row.voucher.number" size="small" :disabled="isReadonly" @change="updateField(row.id, 'voucher', 'number', row.voucher.number)" />
            </template>
          </el-table-column>
          <el-table-column label="品名" min-width="120">
            <template #default="{ row }">
              <el-input v-model="row.voucher.productName" size="small" :disabled="isReadonly" @change="updateField(row.id, 'voucher', 'productName', row.voucher.productName)" />
            </template>
          </el-table-column>
          <el-table-column label="数量" min-width="80">
            <template #default="{ row }">
              <el-input v-model="row.voucher.quantity" size="small" :disabled="isReadonly" @change="updateField(row.id, 'voucher', 'quantity', row.voucher.quantity)" />
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-model="row.voucher.amount" size="small" :controls="false" :disabled="isReadonly" style="width:100%" @change="updateField(row.id, 'voucher', 'amount', row.voucher.amount)" />
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 一致性列 -->
        <el-table-column label="一致" width="60" align="center">
          <template #default="{ row }">
            <span v-if="row.isConsistent === true" class="consistency-yes">√</span>
            <span v-else-if="row.isConsistent === false" class="consistency-no">×</span>
            <span v-else class="consistency-na">—</span>
          </template>
        </el-table-column>

        <!-- 备注列 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly"
              @change="updateField(row.id, 'remark', '', row.remark)" />
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column label="操作" width="80" fixed="right" align="center">
          <template #default="{ row }">
            <el-popconfirm title="确认删除此行？" @confirm="handleRemoveRow(row.id)">
              <template #reference>
                <el-button link type="danger" size="small" :disabled="isReadonly">删除</el-button>
              </template>
            </el-popconfirm>
            <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly"
              @change="(f: any) => handleOcrUpload(row.id, f.raw || f)" style="display:inline-block;">
              <el-button link size="small" :disabled="isReadonly">📎</el-button>
            </el-upload>
          </template>
        </el-table-column>
      </el-table>

      <!-- 添加行按钮 -->
      <div class="add-row-bar">
        <el-button :disabled="isReadonly" @click="handleAddRow">
          <el-icon :size="16" style="margin-right:4px;"><Plus /></el-icon>添加行
        </el-button>
      </div>

      <!-- ═══ 审计意见区 ═══ -->
      <el-card class="audit-opinion-card" shadow="never">
        <template #header>
          <div class="opinion-header">
            <span class="opinion-title">审计意见区</span>
            <div class="opinion-chips"><GtIndexChip value="wp:D4-14" :context-project-id="projectId" /></div>
            <div class="opinion-actions">
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiNoteLoading" :disabled="isReadonly || !aiAvailable" @click="genNote">🤖 AI辅助说明</el-button>
              </el-tooltip>
              <el-tooltip :content="aiTip" placement="top">
                <el-button size="small" type="primary" plain :loading="aiConclusionLoading" :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助结论</el-button>
              </el-tooltip>
            </div>
          </div>
        </template>
        <div class="opinion-body">
          <div class="opinion-field">
            <label>审计说明</label>
            <el-input type="textarea" :autosize="{ minRows: 3, maxRows: 12 }" :model-value="auditNote" :disabled="isReadonly" placeholder="记录完整性检查范围、选样依据、核查过程中发现的问题及处理方式" @input="(v: string) => updateAuditNote(v)" />
          </div>
          <div class="opinion-field">
            <label>审计结论</label>
            <el-input type="textarea" :autosize="{ minRows: 2, maxRows: 8 }" :model-value="auditConclusion" :disabled="isReadonly" placeholder="基于完整性检查结果，判断营业收入完整性认定是否满足审计目标" @input="(v: string) => updateAuditConclusion(v)" />
          </div>
        </div>
      </el-card>

      <!-- 编制提示 -->
      <details class="tips-collapse">
        <summary class="tips-summary">📋 编制提示</summary>
        <div class="tips-body">
          <ol class="tips-list">
            <li>完整性检查应从发货单（出库单）出发，正向追查至发票、记账凭证，确认交易已入账。</li>
            <li>选取样本应覆盖不同月份、不同产品类别，确保代表性。</li>
            <li>如发现发货单有对应但未入账的情况，应追查原因并评估对营业收入完整性的影响。</li>
            <li>一致性校验关注金额、品名、数量三要素是否吻合。</li>
            <li>对不一致项应逐笔记录原因并在备注中说明。</li>
          </ol>
        </div>
      </details>
    </template>

    <!-- ═══ OnlyOffice 模式 ═══ -->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId"
          sheet-name="营业收入完整性检查表D4-15" :readonly="isReadonly" />
      </div>
    </template>

    <!-- OCR 维度选择弹窗 -->
    <el-dialog v-model="ocrDialogVisible" title="OCR结果填入" width="400px" destroy-on-close>
      <p style="margin-bottom:12px;">请选择将OCR结果填入哪个维度：</p>
      <el-radio-group v-model="ocrDimension">
        <el-radio value="delivery">发货单</el-radio>
        <el-radio value="invoice">发票</el-radio>
        <el-radio value="voucher">记账凭证</el-radio>
      </el-radio-group>
      <div style="margin-top:16px;padding:10px;background:#f5f7fa;border-radius:4px;font-size:12px;">
        <div v-for="(val, key) in ocrResult" :key="key">{{ key }}: {{ val }}</div>
      </div>
      <template #footer>
        <el-button @click="ocrDialogVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrFill">确认填入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.d4-completeness { padding: 16px 20px; font-size: 13px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.stats-dashboard { display: flex; align-items: stretch; gap: 12px; margin-bottom: 24px; padding: 16px 20px; background: linear-gradient(135deg, #f8f9fe 0%, #f0f4ff 100%); border-radius: 10px; border: 1px solid #e4e7ed; }
.stat-card { display: flex; flex-direction: column; justify-content: center; padding: 10px 16px; min-width: 110px; border-radius: 8px; background: #fff; box-shadow: 0 1px 3px rgba(0,0,0,0.04); border: 1px solid #ebeef5; }
.stat-card:hover { box-shadow: 0 2px 8px rgba(0,0,0,0.08); }
.stat-card.stat-primary { border-color: #409eff; border-left: 3px solid #409eff; }
.stat-card.stat-warn { border-color: #f56c6c; border-left: 3px solid #f56c6c; }
.stat-card.stat-amount { border-color: #67c23a; border-left: 3px solid #67c23a; }
.stat-value { font-size: 20px; font-weight: 700; color: #303133; line-height: 1.2; }
.stat-unit { font-size: 12px; font-weight: 400; color: #909399; margin-left: 2px; }
.stat-label { font-size: 12px; color: #909399; margin-top: 4px; }
.methodology-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #faecd8; border-left: 3px solid #e6a23c; background: #fffbf0; }
.methodology-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #b88230; }
.methodology-body { padding: 8px 14px 12px; font-size: 12px; color: #606266; line-height: 1.8; }
.method-objective { margin-bottom: 8px; }
.method-steps { padding-left: 4px; }
.method-step { margin-bottom: 4px; }
.step-num { display: inline-block; background: #e6a23c; color: #fff; border-radius: 3px; padding: 1px 6px; font-size: 11px; margin-right: 6px; }
.guide-strip { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; margin-bottom: 16px; padding: 10px 14px; background: #f0f9eb; border-radius: 6px; border: 1px solid #e1f3d8; }
.guide-strip-label { font-weight: 600; color: #67c23a; font-size: 12px; }
.guide-chip { background: #fff; border: 1px solid #c2e7b0; border-radius: 4px; padding: 2px 8px; font-size: 12px; color: #529b2e; cursor: help; }
.guide-arrow { color: #a8abb2; font-size: 12px; }
.completeness-table { font-size: 13px; }
.completeness-table :deep(.el-table__cell) { padding: 6px 0; }
.completeness-table :deep(.col-delivery .el-table__cell) { background-color: #f0faf0 !important; }
.completeness-table :deep(.col-invoice .el-table__cell) { background-color: #f0f5ff !important; }
.completeness-table :deep(.col-voucher .el-table__cell) { background-color: #f8f0ff !important; }
.completeness-table :deep(.row-inconsistent td) { border-left: 3px solid #f56c6c; }
.consistency-yes { color: #67c23a; font-weight: 700; font-size: 16px; }
.consistency-no { color: #f56c6c; font-weight: 700; font-size: 16px; }
.consistency-na { color: #c0c4cc; font-size: 14px; }
.add-row-bar { margin: 12px 0 24px; text-align: center; }
.audit-opinion-card { margin-bottom: 20px; }
.opinion-header { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
.opinion-chips { display: flex; gap: 6px; }
.opinion-actions { margin-left: auto; display: flex; gap: 8px; }
.opinion-body { display: flex; flex-direction: column; gap: 14px; }
.opinion-field label { display: block; font-size: 12px; color: #909399; margin-bottom: 4px; }
.tips-collapse { margin-bottom: 16px; border-radius: 6px; border: 1px solid #fde2e2; border-left: 3px solid #f56c6c; }
.tips-summary { cursor: pointer; padding: 8px 14px; font-size: 13px; font-weight: 500; color: #f56c6c; }
.tips-body { padding: 8px 14px 12px; }
.tips-list { margin: 0; padding-left: 18px; font-size: 12px; color: #606266; line-height: 2; }
.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
</style>