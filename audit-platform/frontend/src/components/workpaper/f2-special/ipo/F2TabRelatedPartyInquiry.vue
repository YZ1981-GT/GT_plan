<template>
  <div class="f2-val-sheet f2-related-inquiry f2-ipo-soft">
    <header class="sheet-header">
      <div>
        <h3>关联方采购定价公允性核查（询价函）</h3>
        <span class="code">F2-65 · 关联方×产品分组逐月询价比较</span>
      </div>
      <div class="stat-row">
        <span class="stat">已填分组 {{ inquiry.filledGroupCount.value }}</span>
        <el-tag v-if="inquiry.abnormalCount.value" type="danger" size="small">
          异常 {{ inquiry.abnormalCount.value }} 月
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按“关联方 + 产品”建立询价组，逐月填写产品规格、关联方采购价格及最多4家独立询价单位的可比采购价格。</p>
        <p>2. 可比均价及价差率由系统自动计算；价差率 =（关联方采购价 − 可比均价）÷ 可比均价，绝对值超过10%自动标红。</p>
        <p>3. 右侧可上传询价函/回函附件并 OCR；识别结果先预览二次编辑，确认后回写主表（默认仅填空字段）。</p>
        <p>4. 对异常价差须结合采购合同、规格质量、运输条款、采购量及市场行情说明原因并形成合理性判断。</p>
      </div>
    </details>
    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="inquiry.addGroup()">+ 新增关联方产品组</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-65"
          :disabled="isReadonly"
          review-section="F2-65-inquiry"
        />
        <GtIndexChip value="wp:F2-65" />
      </div>
    </div>

    <el-card
      v-for="(group, groupIndex) in inquiry.groups.value"
      :key="group.id"
      shadow="never"
      class="group-card"
    >
      <template #header>
        <div class="group-header">
          <div class="group-identification">
            <span class="group-seq">{{ groupIndex + 1 }}</span>
            <span>关联方：</span>
            <el-input
              v-if="!isReadonly"
              :model-value="group.relatedParty"
              size="small"
              class="party-input"
              placeholder="关联方名称"
              @update:model-value="(v: string) => inquiry.updateGroup(group.id, { relatedParty: v })"
            />
            <strong v-else>{{ group.relatedParty || '未填写' }}</strong>
            <span>产品：</span>
            <el-input
              v-if="!isReadonly"
              :model-value="group.productName"
              size="small"
              class="product-input"
              placeholder="产品名称"
              @update:model-value="(v: string) => inquiry.updateGroup(group.id, { productName: v })"
            />
            <strong v-else>{{ group.productName || '未填写' }}</strong>
            <el-tag v-if="group.abnormalCount" type="danger" size="small">{{ group.abnormalCount }} 月异常</el-tag>
          </div>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="isReadonly || inquiry.groups.value.length <= 1"
            @click="inquiry.removeGroup(group.id)"
          >删除本组</el-button>
        </div>
      </template>

      <div class="supplier-row">
        <span>可比询价单位：</span>
        <el-input
          v-for="(_, supplierIndex) in group.comparableSuppliers"
          :key="supplierIndex"
          :model-value="group.comparableSuppliers[supplierIndex]"
          size="small"
          :disabled="isReadonly"
          @update:model-value="(v: string) => updateSupplier(group.id, supplierIndex, v)"
        />
      </div>

      <div class="table-scroll">
        <table class="inquiry-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-month">月份</th>
              <th rowspan="2" class="col-spec">产品规格</th>
              <th rowspan="2">关联方采购价格</th>
              <th colspan="4">可比采购价格</th>
              <th rowspan="2" class="calc-head">可比均价</th>
              <th rowspan="2" class="calc-head">价差率</th>
              <th rowspan="2" class="col-judgment">采购价格是否合理</th>
              <th rowspan="2" class="col-remark">备注</th>
            </tr>
            <tr>
              <th v-for="name in group.comparableSuppliers" :key="name">{{ name }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in group.rows" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
              <td class="col-month">{{ row.month }}月</td>
              <td class="col-spec">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.productSpec"
                  size="small"
                  placeholder="规格/型号"
                  @update:model-value="(v: string) => inquiry.updateRow(group.id, row.id, { productSpec: v })"
                />
                <span v-else>{{ row.productSpec || '—' }}</span>
              </td>
              <td>
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.relatedPrice"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => inquiry.updateRow(group.id, row.id, { relatedPrice: v ?? 0 })"
                />
                <span v-else class="num">{{ fmtPrice(row.relatedPrice) }}</span>
              </td>
              <td v-for="(price, priceIndex) in row.comparablePrices" :key="priceIndex">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="price"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => inquiry.updateComparablePrice(group.id, row.id, priceIndex, v ?? 0)"
                />
                <span v-else class="num">{{ fmtPrice(price) }}</span>
              </td>
              <td class="calc-cell">{{ fmtPrice(row.comparableAverage) }}</td>
              <td class="calc-cell" :class="{ 'spread-warn': row.isAbnormal }">{{ fmtRate(row.spreadRate) }}</td>
              <td class="col-judgment">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row.judgment || row.suggestedJudgment || undefined"
                  size="small"
                  clearable
                  placeholder="请选择"
                  @change="(v: string) => inquiry.updateRow(group.id, row.id, { judgment: (v || '') as any })"
                >
                  <el-option v-for="item in inquiry.PRICING_JUDGMENTS" :key="item" :label="item" :value="item" />
                </el-select>
                <span v-else>{{ row.judgment || row.suggestedJudgment || '—' }}</span>
              </td>
              <td class="col-remark">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.remark"
                  size="small"
                  placeholder="差异原因"
                  @update:model-value="(v: string) => inquiry.updateRow(group.id, row.id, { remark: v })"
                />
                <span v-else>{{ row.remark || '—' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </el-card>

    <div class="bottom-grid">
      <div class="bottom-left">
        <el-card class="opinion-card" shadow="never">
          <template #header>
            <div class="opinion-header">
              <span class="opinion-title">三、审计说明</span>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="runAi('related-inquiry-note')"
              >AI 填写审计说明</el-button>
            </div>
          </template>
          <el-input
            v-model="inquiry.auditNote.value"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="概述询价对象选择、回函情况、价差异常月份及管理层解释和审计核查结果……"
          />
        </el-card>

        <el-card class="opinion-card" shadow="never">
          <template #header>
            <div class="opinion-header">
              <span class="opinion-title">四、审计结论</span>
              <el-button
                size="small"
                type="primary"
                plain
                :disabled="isReadonly || !aiAvailable"
                :loading="aiLoading"
                @click="runAi('related-inquiry-conclusion')"
              >AI 生成结论</el-button>
            </div>
          </template>
          <el-input
            :model-value="auditConclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            placeholder="A、关联方采购定价公允，未见异常。B、除已识别事项外，其余未见异常。C、不可确认。"
            @update:model-value="saveConclusion"
          />
        </el-card>
      </div>

      <aside class="evidence-panel">
        <div class="evidence-head">
          <h4>询价函附件 / OCR</h4>
          <p>上传询价函或回函 → OCR 识别 → 预览编辑 → 确认回写主表</p>
        </div>

        <label class="evidence-field">
          <span>回写目标组</span>
          <el-select
            v-model="targetGroupId"
            size="small"
            clearable
            placeholder="自动匹配关联方+产品"
            :disabled="isReadonly"
          >
            <el-option
              v-for="(group, index) in inquiry.groups.value"
              :key="group.id"
              :label="`${index + 1}. ${group.relatedParty || '未填关联方'} / ${group.productName || '未填产品'}`"
              :value="group.id"
            />
          </el-select>
        </label>

        <div class="evidence-actions">
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            :disabled="isReadonly || ocrUploading || !wpId"
            @change="(upload: any) => uploadAndRecognize(upload.raw || upload)"
          >
            <el-button type="primary" size="small" :loading="ocrUploading" :disabled="isReadonly || !wpId">
              上传并 OCR
            </el-button>
          </el-upload>
          <span class="upload-hint">支持 PDF / JPG / PNG</span>
        </div>

        <div class="evidence-attachments">
          <div class="evidence-subhead">已关联附件</div>
          <ItemAttachment
            v-if="projectId && wpId"
            :key="`F2-65-att-${attachmentRefresh}`"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F2-65"
            :item-index="1"
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
          <el-empty v-else description="缺少项目信息，无法管理附件" :image-size="56" />
        </div>
      </aside>
    </div>

    <div class="tips-box">
      <strong>提示：</strong>该底稿适用于非关联方之间长期交易的价格公允性测试，也可与F2-66市场价格核查交叉印证。OCR 回写后仍可在主表二次编辑。
    </div>

    <el-dialog
      v-model="ocrPreviewVisible"
      title="OCR 结果预览 · 二次编辑 · 确认回写"
      width="720px"
      append-to-body
    >
      <el-alert
        type="warning"
        :closable="false"
        :title="`识别置信度 ${Math.round(ocrConfidence * 100)}%。请逐项核对后确认；识别结果不构成审计判断。`"
        class="ocr-alert"
      />
      <el-form label-width="140px" class="ocr-form">
        <el-form-item label="关联方名称">
          <el-input v-model="ocrDraft.relatedParty" />
        </el-form-item>
        <el-form-item label="采购产品名称">
          <el-input v-model="ocrDraft.productName" />
        </el-form-item>
        <el-form-item label="所属月份">
          <el-input-number v-model="ocrDraft.month" :min="1" :max="12" :controls="true" />
        </el-form-item>
        <el-form-item label="产品规格">
          <el-input v-model="ocrDraft.productSpec" />
        </el-form-item>
        <el-form-item label="关联方采购价格">
          <el-input-number v-model="ocrDraft.relatedPrice" :controls="false" style="width: 100%" />
        </el-form-item>
        <el-form-item
          v-for="item in supplierDraftFields"
          :key="item.key"
          :label="item.label"
        >
          <div class="ocr-pair">
            <el-input v-model="ocrDraft[item.nameKey]" placeholder="单位名称" />
            <el-input-number
              v-model="ocrDraft[item.priceKey]"
              :controls="false"
              placeholder="报价"
              style="width: 100%"
            />
          </div>
        </el-form-item>
        <el-form-item label="是否合理">
          <el-select v-model="ocrDraft.judgment" clearable style="width: 100%">
            <el-option v-for="item in inquiry.PRICING_JUDGMENTS" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="备注">
          <el-input v-model="ocrDraft.remark" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
        </el-form-item>
        <el-form-item label="回写方式">
          <el-checkbox v-model="overwriteExisting">覆盖主表已有值（默认仅填空字段）</el-checkbox>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ocrPreviewVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrWriteback">确认回写</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { useF2RelatedPartyInquiry } from '../../composables/useF2RelatedPartyInquiry'
import {
  F2_65_OBJECTIVE,
  emptyInquiryOcrDraft,
  type InquiryLetterOcrFields,
} from '../../composables/useF2RelatedPartyInquiryFormulas'
import { useF2SpecialAiGenerate, type F2SpeAiSection } from '../../composables/useF2SpecialAiGenerate'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const inquiry = useF2RelatedPartyInquiry({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
const objectiveText = F2_65_OBJECTIVE

function updateSupplier(groupId: string, index: number, value: string): void {
  const source = inquiry.sheet.value.groups.find((group) => group.id === groupId)
  if (!source) return
  const suppliers = [...source.comparableSuppliers] as typeof source.comparableSuppliers
  suppliers[index] = value
  inquiry.updateGroup(groupId, { comparableSuppliers: suppliers })
}

function fmtPrice(value: number | null): string {
  if (value === null || !Number.isFinite(value) || value === 0) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtRate(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

const CONCLUSION_KEY = 'F2-65-audit-conclusion'
const auditConclusion = ref('')

function saveConclusion(value: string): void {
  if (props.isReadonly) return
  auditConclusion.value = value
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: value }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
  const legacy = props.allResponses.get('F2-65-audit-note')?.remark
  if (!inquiry.auditNote.value && legacy) inquiry.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-65',
    groupCount: inquiry.filledGroupCount.value,
    abnormalCount: inquiry.abnormalCount.value,
    groups: inquiry.groups.value.slice(0, 20).map((group) => ({
      relatedParty: group.relatedParty,
      productName: group.productName,
      comparableSuppliers: group.comparableSuppliers,
      abnormalCount: group.abnormalCount,
      rows: group.rows.filter((row) =>
        row.relatedPrice || row.comparablePrices.some((price) => price > 0),
      ).map((row) => ({
        month: row.month,
        productSpec: row.productSpec,
        relatedPrice: row.relatedPrice,
        comparableAverage: row.comparableAverage,
        spreadRate: row.spreadRate,
        judgment: row.judgment || row.suggestedJudgment,
        remark: row.remark,
      })),
    })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'related-inquiry-note'
  const text = await generateAndConfirm(
    section,
    isNote ? inquiry.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 关联方询价审计说明' : 'AI 生成 · 关联方询价审计结论',
  )
  if (!text) return
  if (isNote) inquiry.auditNote.value = text
  else saveConclusion(text)
}

// ─── 附件 + OCR 预览确认回写 ───────────────────────────────────────────────
const targetGroupId = ref<string | undefined>()
const ocrUploading = ref(false)
const attachmentRefresh = ref(0)
const ocrPreviewVisible = ref(false)
const ocrConfidence = ref(0)
const overwriteExisting = ref(false)
const ocrDraft = reactive(emptyInquiryOcrDraft())
const supplierDraftFields = [
  { key: 1, label: '询价单位1', nameKey: 'supplier1' as const, priceKey: 'price1' as const },
  { key: 2, label: '询价单位2', nameKey: 'supplier2' as const, priceKey: 'price2' as const },
  { key: 3, label: '询价单位3', nameKey: 'supplier3' as const, priceKey: 'price3' as const },
  { key: 4, label: '询价单位4', nameKey: 'supplier4' as const, priceKey: 'price4' as const },
]

function fillOcrDraft(fields: InquiryLetterOcrFields): void {
  const next = emptyInquiryOcrDraft()
  next.relatedParty = String(fields.relatedParty || '')
  next.productName = String(fields.productName || '')
  next.productSpec = String(fields.productSpec || '')
  next.supplier1 = String(fields.supplier1 || '')
  next.supplier2 = String(fields.supplier2 || '')
  next.supplier3 = String(fields.supplier3 || '')
  next.supplier4 = String(fields.supplier4 || '')
  next.judgment = String(fields.judgment || '')
  next.remark = String(fields.remark || '')
  const month = Number(fields.month)
  next.month = Number.isFinite(month) && month >= 1 && month <= 12 ? month : undefined
  const relatedPrice = Number(fields.relatedPrice)
  next.relatedPrice = Number.isFinite(relatedPrice) && relatedPrice !== 0 ? relatedPrice : undefined
  for (const idx of [1, 2, 3, 4] as const) {
    const price = Number(fields[`price${idx}`])
    next[`price${idx}`] = Number.isFinite(price) && price !== 0 ? price : undefined
  }
  Object.assign(ocrDraft, next)
}

async function uploadAndRecognize(file: File): Promise<void> {
  if (!props.wpId || props.isReadonly) return
  ocrUploading.value = true
  let attachmentSaved = false
  try {
    if (props.projectId) {
      const objectId = `${props.wpId}:F2-65:1`
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
    }

    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('document_type', 'inquiry-letter')
    const response = await http.post(
      `/api/workpapers/${props.wpId}/f2-spe/contract-ocr`,
      ocrForm,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any,
    )
    const data = response.data?.data ?? response.data
    fillOcrDraft((data?.extracted_fields || {}) as InquiryLetterOcrFields)
    ocrConfidence.value = Number(data?.confidence || 0)
    overwriteExisting.value = false
    ocrPreviewVisible.value = true
  } catch {
    if (attachmentSaved) ElMessage.warning('附件已关联，但 OCR 识别失败，可手工填写或重新识别')
    else ElMessage.error('附件上传或 OCR 失败')
  } finally {
    ocrUploading.value = false
  }
}

function confirmOcrWriteback(): void {
  inquiry.applyOcrFields({ ...ocrDraft }, {
    overwrite: overwriteExisting.value,
    targetGroupId: targetGroupId.value,
  })
  ocrPreviewVisible.value = false
  ElMessage.success('识别结果已确认回写，仍可在主表继续二次编辑')
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2IpoSoftStyles.css"></style>
<style scoped>
.f2-related-inquiry { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; font-size: var(--wp-font-size, 13px); }
.group-card { margin: 14px 0; border-color: #d8cce5; }
.group-card :deep(.el-card__header) { padding: 9px 12px; background: #faf8fc; }
.group-card :deep(.el-card__body) { padding: 10px 12px 12px; }
.group-header,.group-identification,.supplier-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.group-header { justify-content: space-between; }
.group-seq { display:inline-flex; width:23px; height:23px; border-radius:50%; align-items:center; justify-content:center; background:var(--gt-purple); color:#fff; font-size:12px; }
.party-input,.product-input { width: 180px; }
.supplier-row { margin-bottom: 8px; color:#55347f; font-weight:600; }
.supplier-row :deep(.el-input) { width: 150px; }
.table-scroll { overflow-x: auto; max-width: 100%; }
.inquiry-table { width:100%; min-width:1250px; border-collapse:separate; border-spacing:0; font-size:11px; }
.inquiry-table th,.inquiry-table td { border:1px solid #d4c8e0; padding:4px; text-align:center; vertical-align:middle; background:#fff; }
.inquiry-table thead th { position:sticky; top:0; z-index:2; background:var(--gt-purple); color:#fff; font-weight:600; }
.inquiry-table thead th.calc-head { background:#6b4d8f; }
.col-month { width:54px; min-width:54px; font-weight:600; }
.col-spec { width:120px; min-width:120px; text-align:left !important; }
.col-judgment { width:125px; min-width:125px; }
.col-remark { width:150px; min-width:150px; text-align:left !important; }
.calc-cell { background:#f4eff8 !important; color:#4b2d77; text-align:right !important; white-space:nowrap; font-weight:500; }
.num { display:block; text-align:right; white-space:nowrap; }
.row-error td { background:#fef0f0 !important; }
.spread-warn { color:#c45656 !important; background:#fef0f0 !important; font-weight:700; }
:deep(.compact-num) { width:82px; }
:deep(.compact-num .el-input__inner) { text-align:right; padding:0 4px; font-size:11px; }

.bottom-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 0.8fr);
  gap: 14px;
  align-items: start;
  margin-top: 16px;
}
.bottom-left { display: flex; flex-direction: column; gap: 12px; min-width: 0; }
.opinion-card { margin-top: 0; }
.opinion-header { display:flex; align-items:center; justify-content:space-between; }
.opinion-title { font-weight:700; color:#3f2465; }

.evidence-panel {
  border: 1px solid #d8cce5;
  border-radius: 10px;
  background: linear-gradient(180deg, #faf8fc 0%, #fff 48px);
  padding: 14px;
  min-height: 280px;
}
.evidence-head h4 { margin: 0; color: #3f2465; font-size: 14px; }
.evidence-head p { margin: 6px 0 0; color: #8c7b9d; font-size: 12px; line-height: 1.5; }
.evidence-field { display: flex; flex-direction: column; gap: 4px; margin: 14px 0 10px; }
.evidence-field > span { font-size: 12px; color: #6b5a7d; }
.evidence-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
.upload-hint { font-size: 12px; color: #909399; }
.evidence-subhead { font-size: 12px; font-weight: 600; color: #55347f; margin-bottom: 6px; }
.evidence-attachments {
  border: 1px dashed #d4c8e0;
  border-radius: 8px;
  padding: 10px;
  background: #fff;
}

.tips-box { margin-top:14px; padding:10px 14px; background:#ecf5ff; border-left:3px solid #409eff; line-height:1.7; }
.ocr-alert { margin-bottom: 12px; }
.ocr-form { max-height: 58vh; overflow-y: auto; padding-right: 6px; }
.ocr-pair { display: grid; grid-template-columns: 1.4fr 1fr; gap: 8px; width: 100%; }

@media (max-width: 1100px) {
  .bottom-grid { grid-template-columns: 1fr; }
}
</style>
