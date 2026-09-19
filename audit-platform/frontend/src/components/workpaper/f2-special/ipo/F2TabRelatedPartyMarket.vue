<template>
  <div class="f2-val-sheet f2-related-market f2-ipo-soft">
    <header class="uc-hero">
      <div>
        <div class="uc-title-row">
          <h3>关联方采购定价公允性核查（市场价）</h3>
          <span class="uc-code">F2-66</span>
        </div>
        <p class="uc-desc">关联方×产品分组逐月市场价区间比较</p>
      </div>
      <div class="uc-metrics">
        <div class="uc-metric">
          <span class="uc-metric-val">{{ market.filledGroupCount.value }}</span>
          <span class="uc-metric-label">已填分组</span>
        </div>
        <div class="uc-metric" :class="{ danger: market.abnormalCount.value > 0 }">
          <span class="uc-metric-val">{{ market.abnormalCount.value }}</span>
          <span class="uc-metric-label">异常月</span>
        </div>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按“关联方 + 产品”建立比较组，逐月填写关联方采购均价及同期市场（挂牌）价格的月初、月末均价。</p>
        <p>2. 市场价区间、偏离率及是否处于区间由系统自动判断；采购均价落在区间外自动标红并建议“否”。</p>
        <p>3. 市场价取数来源（公开挂牌价、行业报告、大宗商品行情等）应在备注中记录以备复核。</p>
        <p>4. 右侧可上传市场行情/挂牌价截图并 OCR；识别结果先预览二次编辑，确认后回写主表（默认仅填空字段）。</p>
        <p>5. 与询价函核查表（F2-65）交叉印证，关注利益输送或成本操纵风险。</p>
      </div>
    </details>
    <el-alert type="info" :closable="false" :title="objectiveText" class="objective-alert" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="market.addGroup()">+ 新增关联方产品组</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-66"
          :disabled="isReadonly"
          review-section="F2-66-market"
        />
        <GtIndexChip value="wp:F2-66" />
      </div>
    </div>

    <el-card
      v-for="(group, groupIndex) in market.groups.value"
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
              @update:model-value="(v: string) => market.updateGroup(group.id, { relatedParty: v })"
            />
            <strong v-else>{{ group.relatedParty || '未填写' }}</strong>
            <span>产品：</span>
            <el-input
              v-if="!isReadonly"
              :model-value="group.productName"
              size="small"
              class="product-input"
              placeholder="产品名称"
              @update:model-value="(v: string) => market.updateGroup(group.id, { productName: v })"
            />
            <strong v-else>{{ group.productName || '未填写' }}</strong>
            <el-tag v-if="group.abnormalCount" type="danger" size="small">{{ group.abnormalCount }} 月异常</el-tag>
          </div>
          <el-button
            size="small"
            type="danger"
            plain
            :disabled="isReadonly || market.groups.value.length <= 1"
            @click="market.removeGroup(group.id)"
          >删除本组</el-button>
        </div>
      </template>

      <div class="table-scroll">
        <table class="market-table">
          <thead>
            <tr>
              <th rowspan="2" class="col-month">月份</th>
              <th rowspan="2">采购均价</th>
              <th colspan="2">市场价格（挂牌价）均价</th>
              <th rowspan="2" class="calc-head">市场价区间</th>
              <th rowspan="2" class="calc-head">偏离区间中值</th>
              <th rowspan="2" class="col-judgment">采购价格是否处于市场价区间</th>
              <th rowspan="2" class="col-remark">备注（取价来源/差异原因）</th>
            </tr>
            <tr>
              <th>月初</th>
              <th>月末</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in group.rows" :key="row.id" :class="{ 'row-error': row.isAbnormal }">
              <td class="col-month">{{ row.month }}月</td>
              <td>
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.purchaseAvgPrice"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => market.updateRow(group.id, row.id, { purchaseAvgPrice: v ?? 0 })"
                />
                <span v-else class="num">{{ fmtPrice(row.purchaseAvgPrice) }}</span>
              </td>
              <td>
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.marketPriceStart"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => market.updateRow(group.id, row.id, { marketPriceStart: v ?? 0 })"
                />
                <span v-else class="num">{{ fmtPrice(row.marketPriceStart) }}</span>
              </td>
              <td>
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="row.marketPriceEnd"
                  size="small"
                  :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => market.updateRow(group.id, row.id, { marketPriceEnd: v ?? 0 })"
                />
                <span v-else class="num">{{ fmtPrice(row.marketPriceEnd) }}</span>
              </td>
              <td class="calc-cell">{{ fmtRange(row.marketLow, row.marketHigh) }}</td>
              <td class="calc-cell" :class="{ 'spread-warn': row.isAbnormal }">{{ fmtRate(row.deviationRate) }}</td>
              <td class="col-judgment">
                <el-select
                  v-if="!isReadonly"
                  :model-value="row.judgment || row.suggestedJudgment || undefined"
                  size="small"
                  clearable
                  placeholder="自动判断"
                  @change="(v: string) => market.updateRow(group.id, row.id, { judgment: (v || '') as any })"
                >
                  <el-option v-for="item in market.MARKET_JUDGMENTS" :key="item" :label="item" :value="item" />
                </el-select>
                <span v-else>{{ row.judgment || row.suggestedJudgment || '—' }}</span>
              </td>
              <td class="col-remark">
                <el-input
                  v-if="!isReadonly"
                  :model-value="row.remark"
                  size="small"
                  placeholder="取价来源/差异原因"
                  @update:model-value="(v: string) => market.updateRow(group.id, row.id, { remark: v })"
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
                @click="runAi('related-market-note')"
              >AI 填写审计说明</el-button>
            </div>
          </template>
          <el-input
            v-model="market.auditNote.value"
            type="textarea"
            :autosize="{ minRows: 4, maxRows: 10 }"
            :disabled="isReadonly"
            placeholder="说明市场价格取数来源、落在区间外月份的原因、管理层解释及审计核查结果……"
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
                @click="runAi('related-market-conclusion')"
              >AI 生成结论</el-button>
            </div>
          </template>
          <el-input
            :model-value="auditConclusion"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 8 }"
            :disabled="isReadonly"
            placeholder="A、关联方采购价格处于市场价区间，定价公允。B、除已识别事项外，其余未见异常。C、不可确认。"
            @update:model-value="saveConclusion"
          />
        </el-card>
      </div>

      <aside class="evidence-panel">
        <div class="evidence-head">
          <h4>市场行情附件 / OCR</h4>
          <p>上传挂牌价截图或行情 PDF → OCR → 预览编辑 → 确认回写</p>
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
              v-for="(group, index) in market.groups.value"
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
            :key="`F2-66-att-${attachmentRefresh}`"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F2-66"
            :item-index="1"
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
          <el-empty v-else description="缺少项目信息，无法管理附件" :image-size="56" />
        </div>
      </aside>
    </div>

    <div class="tips-box">
      <strong>提示：</strong>{{ tipText.replace('提示：', '') }} OCR 回写后仍可在主表二次编辑。
    </div>

    <el-dialog
      v-model="ocrPreviewVisible"
      title="OCR 结果预览 · 二次编辑 · 确认回写"
      width="640px"
      append-to-body
    >
      <el-alert
        type="warning"
        :closable="false"
        :title="`识别置信度 ${Math.round(ocrConfidence * 100)}%。请逐项核对后确认。`"
        style="margin-bottom: 12px"
      />
      <el-form label-width="140px">
        <el-form-item label="关联方名称"><el-input v-model="ocrDraft.relatedParty" /></el-form-item>
        <el-form-item label="采购产品名称"><el-input v-model="ocrDraft.productName" /></el-form-item>
        <el-form-item label="所属月份">
          <el-input-number v-model="ocrDraft.month" :min="1" :max="12" />
        </el-form-item>
        <el-form-item label="采购均价">
          <el-input-number v-model="ocrDraft.purchaseAvgPrice" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="市场价月初">
          <el-input-number v-model="ocrDraft.marketPriceStart" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="市场价月末">
          <el-input-number v-model="ocrDraft.marketPriceEnd" :controls="false" style="width:100%" />
        </el-form-item>
        <el-form-item label="是否在区间">
          <el-select v-model="ocrDraft.judgment" clearable style="width:100%">
            <el-option v-for="item in market.MARKET_JUDGMENTS" :key="item" :label="item" :value="item" />
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
import { useF2RelatedPartyMarket } from '../../composables/useF2RelatedPartyMarket'
import {
  F2_66_OBJECTIVE,
  F2_66_TIP,
  emptyMarketOcrDraft,
  type MarketQuoteOcrFields,
} from '../../composables/useF2RelatedPartyMarketFormulas'
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

const market = useF2RelatedPartyMarket({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
const objectiveText = F2_66_OBJECTIVE
const tipText = F2_66_TIP

function fmtPrice(value: number): string {
  if (!Number.isFinite(value) || value === 0) return '—'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function fmtRange(low: number | null, high: number | null): string {
  if (low === null || high === null) return '—'
  if (low === high) return fmtPrice(low)
  return `${fmtPrice(low)} ~ ${fmtPrice(high)}`
}

function fmtRate(value: number | null): string {
  return value === null ? '—' : `${(value * 100).toFixed(1)}%`
}

const CONCLUSION_KEY = 'F2-66-audit-conclusion'
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
  const legacy = props.allResponses.get('F2-66-audit-note')?.remark
  if (!market.auditNote.value && legacy) market.auditNote.value = legacy
})

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2SpecialAiGenerate(wpIdRef)

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-66',
    groupCount: market.filledGroupCount.value,
    abnormalCount: market.abnormalCount.value,
    groups: market.groups.value.slice(0, 20).map((group) => ({
      relatedParty: group.relatedParty,
      productName: group.productName,
      abnormalCount: group.abnormalCount,
      rows: group.rows.filter((row) =>
        row.purchaseAvgPrice || row.marketPriceStart || row.marketPriceEnd,
      ).map((row) => ({
        month: row.month,
        purchaseAvgPrice: row.purchaseAvgPrice,
        marketLow: row.marketLow,
        marketHigh: row.marketHigh,
        deviationRate: row.deviationRate,
        inRange: row.inRange,
        judgment: row.judgment || row.suggestedJudgment,
        remark: row.remark,
      })),
    })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'related-market-note'
  const text = await generateAndConfirm(
    section,
    isNote ? market.auditNote.value : auditConclusion.value,
    aiContext(),
    isNote ? 'AI 生成 · 市场价核查审计说明' : 'AI 生成 · 市场价核查审计结论',
  )
  if (!text) return
  if (isNote) market.auditNote.value = text
  else saveConclusion(text)
}

const targetGroupId = ref<string | undefined>()
const ocrUploading = ref(false)
const attachmentRefresh = ref(0)
const ocrPreviewVisible = ref(false)
const ocrConfidence = ref(0)
const overwriteExisting = ref(false)
const ocrDraft = reactive(emptyMarketOcrDraft())

function fillOcrDraft(fields: MarketQuoteOcrFields): void {
  const next = emptyMarketOcrDraft()
  next.relatedParty = String(fields.relatedParty || '')
  next.productName = String(fields.productName || '')
  next.judgment = String(fields.judgment || '')
  next.remark = String(fields.remark || '')
  const month = Number(fields.month)
  next.month = Number.isFinite(month) && month >= 1 && month <= 12 ? month : undefined
  for (const key of ['purchaseAvgPrice', 'marketPriceStart', 'marketPriceEnd'] as const) {
    const n = Number(fields[key])
    next[key] = Number.isFinite(n) && n !== 0 ? n : undefined
  }
  Object.assign(ocrDraft, next)
}

async function uploadAndRecognize(file: File): Promise<void> {
  if (!props.wpId || props.isReadonly) return
  ocrUploading.value = true
  let attachmentSaved = false
  try {
    if (props.projectId) {
      const objectId = `${props.wpId}:F2-66:1`
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
    ocrForm.append('document_type', 'market-quote')
    const response = await http.post(
      `/api/workpapers/${props.wpId}/f2-spe/contract-ocr`,
      ocrForm,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = response.data?.data ?? response.data
    fillOcrDraft((data?.extracted_fields || {}) as MarketQuoteOcrFields)
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
  market.applyOcrFields({ ...ocrDraft }, {
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
.f2-related-market { font-size: var(--wp-font-size, 13px); }
.group-card { margin: 14px 0; }
.group-card :deep(.el-card__header) { padding: 9px 12px; }
.group-card :deep(.el-card__body) { padding: 10px 12px 12px; }
.group-header,.group-identification { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.group-header { justify-content: space-between; }
.group-seq { display:inline-flex; width:23px; height:23px; border-radius:50%; align-items:center; justify-content:center; color:#fff; font-size:12px; }
.party-input,.product-input { width: 180px; }
.market-table { width:100%; min-width:1050px; font-size:11px; }
.market-table th,.market-table td { padding:4px; text-align:center; vertical-align:middle; background:#fff; }
.market-table thead th { position:sticky; top:0; z-index:2; font-weight:600; }
.col-month { width:54px; min-width:54px; font-weight:600; }
.col-judgment { width:135px; min-width:135px; }
.col-remark { width:190px; min-width:190px; text-align:left !important; }
.calc-cell { background:#eff6ff !important; color:#1d4ed8; text-align:right !important; white-space:nowrap; font-weight:500; }
.calc { color:#1d4ed8; font-weight:500; background:#eff6ff !important; }
.num { display:block; text-align:right; white-space:nowrap; }
.row-error td { background:#fef0f0 !important; }
.spread-warn { color:#c45656 !important; background:#fef0f0 !important; font-weight:700; }
:deep(.compact-num) { width:88px; }
:deep(.compact-num .el-input__inner) { text-align:right; padding:0 4px; font-size:11px; }
.opinion-card { margin-top: 0; }
.opinion-header { display:flex; align-items:center; justify-content:space-between; }
.opinion-title { font-weight:700; color:#1f2937; }
.tips-box { margin-top:14px; padding:10px 14px; background:#ecf5ff; border-left:3px solid #409eff; line-height:1.7; }
</style>
