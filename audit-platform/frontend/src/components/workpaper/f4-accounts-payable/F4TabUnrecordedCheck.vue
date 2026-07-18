<script setup lang="ts">
/** F4TabUnrecordedCheck — F4-7 未入账应付账款五段检查 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import {
  SECTION_CONFIGS,
  useF4UnrecordedCheck,
  type F4UnrecordedOcrFields,
  type F4UnrecordedRow,
  type UnrecordedColumnConfig,
  type UnrecordedSection,
  type UnrecordedSectionConfig,
} from '../composables/useF4UnrecordedCheck'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import ItemAttachment from '../ItemAttachment.vue'
import GtIndexChip from '../GtIndexChip.vue'

const f4UnrecordedNav = [
  { id: 'f4-7-payment-window', label: '付款天数' },
  { id: 'f4-7-estimated-inbound', label: '暂估入库' },
  { id: 'f4-7-unprocessed-invoice', label: '未处理发票' },
  { id: 'f4-7-subsequent-payment', label: '期后付款' },
  { id: 'f4-7-subsequent-increase', label: '期后增加' },
  { id: 'f4-7-note', label: '说明' },
  { id: 'f4-7-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f4UnrecordedNav)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  overallSummary,
  auditNote,
  auditConclusion,
  loadSection,
  getRows,
  getSubtotal,
  addRow,
  removeRow,
  updateCell,
  mergeOcrFields,
  distributeCutoffSamples,
  saveAuditNote,
  saveAuditConclusion,
  rowClassName,
} = useF4UnrecordedCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

function fmtAmount(value: number): string {
  if (!Number.isFinite(value) || Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function cellValue(row: F4UnrecordedRow, prop: string): any {
  return (row as any)[prop]
}

function formulaValue(row: F4UnrecordedRow, prop: string): string {
  if (prop === 'averagePaymentDays') {
    return row.averagePaymentDays == null ? '无法计算' : `${row.averagePaymentDays.toFixed(2)} 天`
  }
  return fmtAmount(Number(cellValue(row, prop)))
}

function sectionTableWidth(config: UnrecordedSectionConfig): number {
  return config.columns.reduce((sum, column) => sum + (column.width || column.minWidth || 130), 230)
}

function subtotalText(section: UnrecordedSection): string {
  const subtotal = getSubtotal(section)
  if (section === 'payment-window') {
    return `期末余额 ${fmtAmount(subtotal.primaryTotal)} ｜期后付款 ${fmtAmount(subtotal.comparisonTotal)} ｜风险 ${subtotal.flaggedCount} 项`
  }
  if (section === 'estimated-inbound') {
    return `暂估金额 ${fmtAmount(subtotal.primaryTotal)} ｜凭证金额 ${fmtAmount(subtotal.comparisonTotal)} ｜建议调整 ${fmtAmount(subtotal.adjustmentTotal)}`
  }
  return `检查金额 ${fmtAmount(subtotal.primaryTotal)} ｜应计入报告期 ${fmtAmount(subtotal.reportPeriodTotal)} ｜风险 ${subtotal.flaggedCount} 项`
}

async function onImported(section: UnrecordedSection): Promise<void> {
  if (reloadWorkpaperData) await reloadWorkpaperData()
  loadSection(section)
}

// ─── 截止自动提取：仅分配至期后付款和期后增加额 ────────────────────────────────
const cutoffLoading = ref(false)
async function handleCutoffExtract(): Promise<void> {
  cutoffLoading.value = true
  try {
    const response = await http.post(`/api/workpapers/${props.wpId}/cutoff-auto-sampling`, {
      accountCode: '2202',
      dayRange: 30,
    })
    const vouchers = response.data?.data?.vouchers ?? response.data?.vouchers ?? []
    if (!vouchers.length) {
      ElMessage.warning('序时账中未提取到期后应付账款借贷发生')
      return
    }
    const result = distributeCutoffSamples(vouchers)
    ElMessage.success(`已提取：期后付款 ${result.payments} 笔，期后增加 ${result.increases} 笔`)
  } catch {
    ElMessage.error('截止自动提取失败')
  } finally {
    cutoffLoading.value = false
  }
}

// ─── 附件、OCR预览编辑、确认回写 ──────────────────────────────────────────────
const evidenceDialogVisible = ref(false)
const activeSection = ref<UnrecordedSection>('payment-window')
const activeRowId = ref('')
const evidenceUploading = ref(false)
const attachmentRefresh = ref(0)
const ocrPreviewVisible = ref(false)
const ocrDraft = ref<Record<string, any>>({})
const overwriteExisting = ref(false)
const ocrConfidence = ref(0)

const activeConfig = computed(() =>
  SECTION_CONFIGS.find((config) => config.key === activeSection.value)!,
)
const activeRow = computed(() =>
  getRows(activeSection.value).find((row) => row.rowId === activeRowId.value) || null,
)
const editablePreviewColumns = computed(() =>
  activeConfig.value.columns.filter((column) => column.inputType !== 'formula'),
)

function openEvidenceDialog(section: UnrecordedSection, row: F4UnrecordedRow): void {
  activeSection.value = section
  activeRowId.value = row.rowId
  evidenceDialogVisible.value = true
}

async function uploadAndRecognize(file: File): Promise<void> {
  const row = activeRow.value
  if (!row || props.isReadonly) return
  evidenceUploading.value = true
  let attachmentSaved = false
  try {
    const objectId = `${props.wpId}:${activeConfig.value.sheet}:${row.attSlot}`
    const attachmentForm = new FormData()
    attachmentForm.append('file', file)
    attachmentForm.append('attachment_type', 'workpaper_item')
    attachmentForm.append('reference_type', 'workpaper_item')
    attachmentForm.append('title', objectId)
    attachmentForm.append('document_type', objectId)
    await api.post(`/api/projects/${props.projectId}/attachments/upload`, attachmentForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    attachmentSaved = true
    attachmentRefresh.value += 1

    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('document_type', activeConfig.value.ocrDocumentType)
    const response = await http.post(
      `/api/workpapers/${props.wpId}/f4/contract-ocr`,
      ocrForm,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any,
    )
    const data = response.data?.data ?? response.data
    const fields = (data?.extracted_fields || {}) as F4UnrecordedOcrFields
    ocrDraft.value = Object.fromEntries(
      editablePreviewColumns.value.map((column) => [
        String(column.prop),
        (fields as any)[column.prop] ?? '',
      ]),
    )
    ocrConfidence.value = Number(data?.confidence || 0)
    overwriteExisting.value = false
    ocrPreviewVisible.value = true
  } catch {
    if (attachmentSaved) ElMessage.warning('附件已关联，但OCR识别失败，可在主表二次编辑')
    else ElMessage.error('附件上传失败')
  } finally {
    evidenceUploading.value = false
  }
}

function confirmOcrWriteback(): void {
  if (!activeRow.value) return
  mergeOcrFields(
    activeSection.value,
    activeRow.value.rowId,
    ocrDraft.value,
    overwriteExisting.value,
  )
  ocrPreviewVisible.value = false
  ElMessage.success('识别结果已确认回写，仍可在主表继续编辑')
}

// ─── AI说明与结论 ────────────────────────────────────────────────────────────
function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-7',
    summary: overallSummary.value,
    sections: SECTION_CONFIGS.map((config) => ({
      section: config.key,
      title: config.title,
      subtotal: getSubtotal(config.key),
      rows: getRows(config.key)
        .filter((row) => getSubtotal(config.key).filledCount && row.riskFlags.length)
        .map((row) => ({
          supplierName: row.supplierName,
          amount: row.amount,
          estimatedAmount: row.estimatedAmount,
          voucherAmount: row.voucherAmount,
          closingBalance: row.closingBalance,
          postPaymentAmount: row.postPaymentAmount,
          shouldAdjust: row.shouldAdjust,
          shouldIncludeReportPeriod: row.shouldIncludeReportPeriod,
          reportPeriodAmount: row.reportPeriodAmount,
          riskFlags: row.riskFlags,
        })),
    })),
  }
}

async function generateAuditNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'unrecorded-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-7审计说明',
  )
  if (generated) saveAuditNote(generated)
}

async function generateAuditConclusion(): Promise<void> {
  const generated = await generateAndConfirm(
    'unrecorded-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-7审计结论',
  )
  if (generated) saveAuditConclusion(generated)
}
</script>

<template>
  <div class="f4-tab-unrecorded">
    <details class="guidance-details">
      <summary>📋 编制思路、时段划分与单据核对链条</summary>
      <div class="guidance-content">
        <p>1. 本表用于验证应付账款完整性，核心是从账外或期后资料反向追查报告期负债，而非仅抽查账内记录。</p>
        <p>2. 平均付款期：以供应商期初、借方、贷方计算期末余额及平均付款天数，再与期后付款金额和付款时点比较。</p>
        <p>3. 暂估入库：核对“入库单数量 × 合同不含税单价＝暂估金额”，并与暂估记账凭证日期、编号和金额匹配。</p>
        <p>4. 未处理发票：从现场截止日未处理发票清单反查货物/服务归属期；期后付款：凭证与银行付款单核对；期后增加：凭证与购货发票核对。</p>
        <p>5. 每行可关联多份附件。OCR结果先进入可编辑预览，确认后回写；主表字段仍可二次编辑。是否计入报告期必须基于权责发生时点及证据人工判断。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：所有应记录的应付账款均已记录，所有应当包括在财务报表中的相关披露均已包括。"
    />

    <div class="top-toolbar">
      <div>
        <el-button
          type="primary"
          size="small"
          :loading="cutoffLoading"
          :disabled="isReadonly"
          @click="handleCutoffExtract"
        >从序时账提取期后借贷发生</el-button>
        <span class="toolbar-hint">未处理发票和料到单未到项目须从账外清单及业务单据取得，不能由账内自动推断。</span>
      </div>
      <div class="toolbar-links">
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:F4-8" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-7-unrecorded')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-7" label="未入账检查附件" />

    <nav class="st-sec-nav" aria-label="F4-7 分区导航">
      <button
        v-for="item in f4UnrecordedNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <section
      v-for="config in SECTION_CONFIGS"
      :id="`f4-7-${config.key}`"
      :key="config.key"
      class="check-section"
    >
      <div class="section-heading">
        <div>
          <h3>{{ config.title }}</h3>
          <p>{{ config.purpose }}</p>
        </div>
        <div class="section-actions">
          <F4ImportExportToolbar
            :wp-id="wpId"
            :project-id="projectId"
            :sheet="config.sheet"
            :disabled="isReadonly"
            @imported="onImported(config.key)"
          />
          <el-button size="small" :disabled="isReadonly" @click="addRow(config.key)">+ 新增行</el-button>
        </div>
      </div>

      <div class="table-scroll-wrap">
        <el-table
          :data="getRows(config.key)"
          border
          size="small"
          :row-class-name="rowClassName"
          max-height="460"
          :style="{ minWidth: `${sectionTableWidth(config)}px` }"
        >
          <el-table-column type="index" label="序号" width="58" fixed="left" />
          <el-table-column
            v-for="column in config.columns"
            :key="String(column.prop)"
            :label="column.label"
            :width="column.width"
            :min-width="column.minWidth"
            :align="column.inputType === 'number' || column.inputType === 'formula' ? 'right' : 'left'"
          >
            <template #default="{ row }">
              <el-tooltip
                v-if="column.inputType === 'formula'"
                :content="column.tooltip || '自动计算'"
                placement="top"
              >
                <span class="formula-value">{{ formulaValue(row, String(column.prop)) }}</span>
              </el-tooltip>
              <el-input-number
                v-else-if="column.inputType === 'number' && !isReadonly"
                :model-value="Number(cellValue(row, String(column.prop)))"
                :controls="false"
                size="small"
                style="width:100%"
                @change="(value: number | undefined) => updateCell(config.key, row.rowId, String(column.prop), value ?? 0)"
              />
              <el-date-picker
                v-else-if="column.inputType === 'date' && !isReadonly"
                :model-value="String(cellValue(row, String(column.prop)) || '')"
                type="date"
                value-format="YYYY-MM-DD"
                format="YYYY-MM-DD"
                size="small"
                style="width:100%"
                @update:model-value="(value: string) => updateCell(config.key, row.rowId, String(column.prop), value)"
              />
              <el-select
                v-else-if="column.inputType === 'select' && !isReadonly"
                :model-value="String(cellValue(row, String(column.prop)) || '')"
                size="small"
                clearable
                @change="(value: string) => updateCell(config.key, row.rowId, String(column.prop), value)"
              >
                <el-option v-for="option in column.options" :key="option" :label="option" :value="option" />
              </el-select>
              <el-input
                v-else-if="!isReadonly"
                :model-value="String(cellValue(row, String(column.prop)) || '')"
                :type="column.inputType === 'textarea' ? 'textarea' : 'text'"
                :autosize="column.inputType === 'textarea' ? { minRows: 1, maxRows: 3 } : undefined"
                size="small"
                @change="(value: string) => updateCell(config.key, row.rowId, String(column.prop), value)"
              />
              <span v-else-if="column.inputType === 'number'">
                {{ fmtAmount(Number(cellValue(row, String(column.prop)))) }}
              </span>
              <span v-else>{{ cellValue(row, String(column.prop)) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="风险提示" width="185">
            <template #default="{ row }">
              <div class="risk-flags">
                <el-tag
                  v-for="flag in row.riskFlags"
                  :key="flag"
                  size="small"
                  :type="row.riskLevel === 'danger' ? 'danger' : 'warning'"
                >{{ flag }}</el-tag>
                <span v-if="!row.riskFlags.length">—</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="附件/操作" width="145" fixed="right">
            <template #default="{ row }">
              <el-button link type="primary" size="small" @click="openEvidenceDialog(config.key, row)">附件识别</el-button>
              <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(config.key, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="section-subtotal">{{ subtotalText(config.key) }}</div>
    </section>

    <div class="overall-summary">
      <span>已检查 {{ overallSummary.testedCount }} 项</span>
      <span>风险 {{ overallSummary.riskCount }} 项</span>
      <span>应计入报告期 {{ fmtAmount(overallSummary.reportPeriodAmount) }}</span>
      <span class="adjustment">未去重候选调整 {{ fmtAmount(overallSummary.candidateAdjustment) }}</span>
      <span v-if="overallSummary.duplicateRiskCount" class="adjustment">
        疑似跨区重复 {{ overallSummary.duplicateRiskCount }} 项，调整前须去重
      </span>
    </div>

    <el-card id="f4-7-note" shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">三、审计说明</div>
            <div class="card-hint">分别记录五类程序的样本来源、跨时段判断、多单据核对和异常处理。</div>
          </div>
          <div class="card-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAuditNote">🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-7-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="说明期后时段选取、账外清单来源、单据核对结果、应计入报告期项目及建议调整。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card id="f4-7-conclusion" shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">四、审计结论</div>
            <div class="card-hint">评价应付账款完整性、采购与付款截止以及相关披露是否恰当。</div>
          </div>
          <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAuditConclusion">🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合五类检查结果，评价是否存在重大未入账负债或截止性错报。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog v-model="evidenceDialogVisible" :title="`${activeConfig.title} · 附件与OCR`" width="780px">
      <template v-if="activeRow">
        <el-alert type="info" :closable="false" :title="activeConfig.evidenceHint" />
        <section class="evidence-section">
          <h4>上传并识别</h4>
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            :disabled="isReadonly || evidenceUploading"
            @change="(upload: any) => uploadAndRecognize(upload.raw || upload)"
          >
            <el-button type="primary" :loading="evidenceUploading" :disabled="isReadonly">
              上传附件并OCR
            </el-button>
          </el-upload>
          <span class="upload-hint">同一检查项可连续上传多张单据；每次识别均先预览编辑，再确认回写。</span>
        </section>
        <section class="evidence-section">
          <h4>已关联附件 / 补充上传</h4>
          <ItemAttachment
            :key="`${activeConfig.sheet}-${activeRow.attSlot}-${attachmentRefresh}`"
            :project-id="projectId"
            :wp-id="wpId"
            :sheet-key="activeConfig.sheet"
            :item-index="activeRow.attSlot"
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
        </section>
      </template>
      <template #footer><el-button @click="evidenceDialogVisible = false">关闭</el-button></template>
    </el-dialog>

    <el-dialog v-model="ocrPreviewVisible" title="OCR结果预览、二次编辑与确认回写" width="720px" append-to-body>
      <el-alert
        type="warning"
        :closable="false"
        :title="`识别置信度 ${Math.round(ocrConfidence * 100)}%。请逐项核对，识别结果不构成审计判断。`"
      />
      <el-form label-width="170px" class="ocr-form">
        <el-form-item v-for="column in editablePreviewColumns" :key="String(column.prop)" :label="column.label">
          <el-input-number
            v-if="column.inputType === 'number'"
            v-model="ocrDraft[String(column.prop)]"
            :controls="false"
            style="width:100%"
          />
          <el-select
            v-else-if="column.inputType === 'select'"
            v-model="ocrDraft[String(column.prop)]"
            clearable
            style="width:100%"
          >
            <el-option v-for="option in column.options" :key="option" :label="option" :value="option" />
          </el-select>
          <el-date-picker
            v-else-if="column.inputType === 'date'"
            v-model="ocrDraft[String(column.prop)]"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY-MM-DD"
            style="width:100%"
          />
          <el-input
            v-else
            v-model="ocrDraft[String(column.prop)]"
            :type="column.inputType === 'textarea' ? 'textarea' : 'text'"
            :autosize="column.inputType === 'textarea' ? { minRows: 2, maxRows: 4 } : undefined"
          />
        </el-form-item>
        <el-form-item label="回写方式">
          <el-checkbox v-model="overwriteExisting">覆盖主表已有值（默认仅填空字段）</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ocrPreviewVisible = false">取消回写</el-button>
        <el-button type="primary" @click="confirmOcrWriteback">确认回写</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f4-tab-unrecorded { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #315a8a; border-radius: 4px; background: #eef4fa; }
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.audit-objective { margin-bottom: 12px; }
.top-toolbar, .section-heading, .card-header { display: flex; align-items: center; justify-content: space-between; gap: 14px; }
.top-toolbar { margin-bottom: 14px; }
.toolbar-hint { margin-left: 10px; color: #909399; font-size: 12px; }
.toolbar-links, .section-actions, .card-actions { display: flex; align-items: center; gap: 8px; }
.check-section { margin: 0 0 22px; padding: 12px; border: 1px solid #dfe5ec; border-radius: 8px; background: #fff; }
.section-heading { margin-bottom: 8px; }
.section-heading h3 { margin: 0; color: #263a52; font-size: 14px; }
.section-heading p { margin: 4px 0 0; color: #7a8491; font-size: 12px; }
.table-scroll-wrap { width: 100%; overflow-x: auto; }
.table-scroll-wrap :deep(.el-select), .table-scroll-wrap :deep(.el-input-number) { width: 100%; }
.formula-value { border-bottom: 1px dashed #9ca3af; cursor: help; color: #315a8a; font-weight: 600; }
.risk-flags { display: flex; flex-wrap: wrap; gap: 3px; }
:deep(.unrecorded-risk-warning td) { background: #fdf6ec !important; }
:deep(.unrecorded-risk-danger td) { background: #fef0f0 !important; }
.section-subtotal { padding: 7px 12px; border: 1px solid #dcdfe6; border-top: none; background: #f5f7fa; text-align: right; font-weight: 600; }
.overall-summary { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 12px 26px; padding: 12px 16px; border-radius: 6px; background: #eef4fa; font-weight: 700; }
.overall-summary .adjustment { color: #d03050; }
.text-card { margin-top: 16px; border-radius: 8px; }
.text-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.card-title { color: #303133; font-weight: 600; }
.card-hint { margin-top: 3px; color: #909399; font-size: 12px; }
.evidence-section { margin-top: 16px; }
.evidence-section h4 { margin: 0 0 8px; }
.upload-hint { margin-left: 10px; color: #909399; font-size: 12px; }
.ocr-form { margin-top: 16px; max-height: 58vh; overflow-y: auto; padding-right: 8px; }
</style>

<style src="../f2/stocktake/f2StocktakeSoftNav.css"></style>
