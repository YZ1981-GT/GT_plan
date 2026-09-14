<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * D1TabSamplingVouching.vue — D1-13 应收票据抽样凭证核对 HTML渲染
 *
 * Spec: .kiro/specs/d1-inspection-check/
 * Task: 12.1
 *
 * 渲染（HTML 模式）：
 * - el-segmented 双模式切换（结构化视图 | 在线编辑）
 * - 审计目标区域（只读静态文本）
 * - 抽样总体定义区（textarea + 笔数 + 金额 + 样本量 + 抽取笔数 + GtIndexChip）
 * - 特定样本区域（动态行: 描述|金额|原因）
 * - 分隔线 + "凭证核对明细"标题
 * - 凭证核对明细 el-table 12列：
 *   序号|票据类型|号码|出票人|承兑人|金额|到期日|存在性验证|准确性验证|记录恰当性|备注|索引号
 * - 验证结果颜色编码：已核实/金额一致/恰当=绿色；未核实/金额不一致/不恰当=红色
 * - 例外项行浅红色背景
 * - "添加核查项"按钮
 * - 核对结果区（G32核查笔数 | H32核查金额合计）
 * - 例外汇总区 E48-G50（3行×3列: 类别|笔数|金额|占比）
 * - 例外占比超标：红色高亮 + "例外率超标，请考虑扩大样本量"
 * - 测试结论（el-select）
 * - 审计说明/结论 + 编制提示（CAS 1314/抽样方法/例外追查/推断方法）
 * - GtOnlyOfficeSheet v-if isOOMode
 *
 * Requirements: 10.1-10.4, 11.1-11.4, 12.1-12.6, 13.1-13.5, 14.1-14.5, 18.1-18.4, 18.7
 */
import { ref, inject, toRef, computed, defineAsyncComponent, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useD1SamplingVouching } from '../composables/useD1SamplingVouching'
import {
  NOTE_TYPE_OPTIONS,
  EXISTENCE_OPTIONS,
  ACCURACY_OPTIONS,
  APPROPRIATENESS_OPTIONS,
  TEST_CONCLUSION_OPTIONS,
  formatNegativeAmount,
  type VouchingRow,
} from '../composables/d1InspectionFormulas'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD1FormData'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewDot from '../GtReviewDot.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useWorkpaperWideTable } from '../composables/useWorkpaperWideTable'
import { useWorkpaperBrowseMode } from '../composables/useWorkpaperBrowseMode'
import { virtualTextCol, virtualNumCol } from '../composables/virtualColumnHelpers'
import { useD1AiGenerate } from '../composables/useD1AiGenerate'
import type { VirtualColumn } from '@/composables/useVirtualTable'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
  displayPrefs: any
  sheetName?: string
  year?: number
}>()

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

// ─── Inject ──────────────────────────────────────────────────────────────────

const injectedDisplayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// 复核对话
const openReviewDialog = inject<any>('openReviewDialog', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  population,
  updatePopulation,
  specificSamples,
  addSpecificSample,
  removeSpecificSample,
  updateSpecificSample,
  vouchingRows,
  addVouchingRow,
  removeVouchingRow,
  updateVouchingRow,
  fillFromSampledVouchers,
  checkedCount,
  checkedAmountTotal,
  vouchingAmountTotal,
  exceptionSummary,
  hasExceedingException,
  tolerableErrorRate,
  updateTolerableErrorRate,
  testConclusion,
  updateTestConclusion,
  auditNote,
  auditConclusion,
  saveAuditNote,
  saveAuditConclusion,
  exportTemplate,
  exportData,
  importData,
} = useD1SamplingVouching({
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, ChecklistResponse>>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  saveImmediate: async (items: ChecklistItem[]) => {
    try {
      await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    } catch { ElMessage.warning('保存失败，请重试') }
  },
  saveDebouncedText: (item: ChecklistItem) => {
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items: [item] })
      .catch(() => { /* silent */ })
  },
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const columnCount = ref(13)
const vouchingRowCount = computed(() => vouchingRows.value.length)
const browseRows = computed(() => vouchingRows.value)
const browseRowCount = computed(() => browseRows.value.length)
const wpIdRef = toRef(props, 'wpId')
const { generateAndConfirm, aiAvailable } = useD1AiGenerate(wpIdRef)
const aiLoadingNote = ref(false)
const aiLoadingConclusion = ref(false)
const aiLoadingSamplingBasis = ref(false)
const ocrExtracted = ref<Map<string, Record<string, any>>>(new Map())

// ─── 抽凭引擎（P0-4 联动）───────────────────────────────────────────────────
const samplingYear = computed(() => props.year ?? new Date().getFullYear())
const samplingVisible = ref(false)
function openSampling(): void {
  if (props.isReadonly) return
  samplingVisible.value = true
}
function onSamplesFilled(payload: { samples?: any[] }): void {
  const samples = payload?.samples ?? []
  const added = fillFromSampledVouchers(samples)
  samplingVisible.value = false
  if (added > 0) {
    ElMessage.success(`已从抽凭引擎回填 ${added} 笔样本到凭证核对明细`)
  } else {
    ElMessage.info('未新增样本（可能已存在或未选取）')
  }
}

const virtualColumns = computed<VirtualColumn[]>(() => [
  virtualTextCol('noteType', '票据类型', 130),
  virtualTextCol('noteNo', '票据号码', 140),
  virtualTextCol('drawer', '出票人', 100),
  virtualTextCol('acceptor', '承兑人', 100),
  virtualNumCol('amount', '金额', 110, injectedDisplayPrefs.fmtAmount),
  virtualTextCol('maturityDate', '到期日', 120),
  virtualTextCol('existenceCheck', '存在性验证', 120),
  virtualTextCol('accuracyCheck', '准确性验证', 130),
])

const {
  browseMode,
  useVirtualScroll,
  rowEventHandlers,
  tableWidth,
  tableHeight,
  toggleBrowseMode,
} = useWorkpaperBrowseMode({
  rows: browseRows,
  virtualColumns,
  tableWidth: 1400,
})

const { tableMaxHeight } = useWorkpaperWideTable({ rowCount: vouchingRowCount, columnCount })

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0) return '-'
  if (val < 0) {
    const formatted = formatNegativeAmount(val)
    return `<span class="negative-amount">${formatted}</span>`
  }
  return injectedDisplayPrefs.fmtAmount(val)
}

function fmtPercent(val: number): string {
  return (val * 100).toFixed(2) + '%'
}

// ─── Row Class for Exception ──────────────────────────────────────────────────

function getVouchingRowClass({ row }: { row: VouchingRow }): string {
  const isException = row.existenceCheck === '未核实'
    || row.accuracyCheck === '金额不一致'
    || row.appropriatenessCheck === '不恰当'
  return isException ? 'exception-row' : ''
}

// ─── Validation color helper ─────────────────────────────────────────────────

function getCheckClass(val: string): string {
  if (val === '已核实' || val === '金额一致' || val === '恰当') return 'check-positive'
  if (val === '未核实' || val === '金额不一致' || val === '不恰当') return 'check-negative'
  return ''
}

// ─── Review ────────────────────────────────────────────────────────────────────

function onReview(sectionId: string) {
  if (openReviewDialog) openReviewDialog({ sectionId })
}

function buildSamplingAiContext(extra = ''): Record<string, unknown> {
  const rows = vouchingRows.value
  const exceptionRows = rows.filter((r) =>
    r.existenceCheck === '未核实'
    || r.accuracyCheck === '金额不一致'
    || r.appropriatenessCheck === '不恰当',
  )
  return {
    sheet: 'D1-13',
    population: population.value,
    sampleCount: rows.length,
    checkedCount: checkedCount.value,
    checkedAmountTotal: checkedAmountTotal.value,
    vouchingAmountTotal: vouchingAmountTotal.value,
    exceptionSummary: exceptionSummary.value,
    hasExceedingException: hasExceedingException.value,
    testConclusion: testConclusion.value,
    sampledBasis: specificSamples.value.map((s) => `${s.description}/${s.reason}`).join('；'),
    sampleDetail: exceptionRows.slice(0, 10).map((r) => ({
      seq: r.seq,
      noteNo: r.noteNo,
      amount: r.amount,
      existenceCheck: r.existenceCheck,
      accuracyCheck: r.accuracyCheck,
      appropriatenessCheck: r.appropriatenessCheck,
      attachmentName: r.attachmentName,
    })),
    guidance: extra,
  }
}

async function generateAuditNoteWithAI() {
  if (props.isReadonly) return
  aiLoadingNote.value = true
  try {
    const text = await generateAndConfirm(
      'sampling-audit-note',
      auditNote.value,
      buildSamplingAiContext('基于D1-13抽样依据、核查结果和例外统计，生成审计说明。'),
      'AI · 审计说明',
    )
    if (text) saveAuditNote(text)
  } finally {
    aiLoadingNote.value = false
  }
}

async function generateSamplingBasisWithAI() {
  if (props.isReadonly) return
  aiLoadingSamplingBasis.value = true
  try {
    const text = await generateAndConfirm(
      'sampling-audit-note',
      [
        `测试总体：${population.value.testPopulation || ''}`,
        `特定样本范围：${population.value.specificItemScope || ''}`,
        `抽样总体：${population.value.populationDesc || ''}`,
        `抽样方法：${population.value.samplingMethod || ''}`,
      ].join('\n'),
      {
        sheet: 'D1-13',
        task: '生成抽样总体定义区建议文本，覆盖测试总体、特定样本范围、抽样总体、抽样方法。',
        totalCount: population.value.totalCount,
        totalAmount: population.value.totalAmount,
        sampleSize: population.value.sampleSize,
        actualDrawn: population.value.actualDrawn,
      },
      'AI · 抽样依据建议',
    )
    if (!text) return
    const lines = text.split('\n').map((s) => s.trim()).filter(Boolean)
    const pick = (label: string) => lines.find((l) => l.startsWith(label))?.replace(label, '').trim() || ''
    const nextTestPopulation = pick('测试总体：')
    const nextSpecificScope = pick('特定样本范围：')
    const nextPopulation = pick('抽样总体：')
    const nextMethod = pick('抽样方法：')
    if (nextTestPopulation) updatePopulation('testPopulation', nextTestPopulation)
    if (nextSpecificScope) updatePopulation('specificItemScope', nextSpecificScope)
    if (nextPopulation) updatePopulation('populationDesc', nextPopulation)
    if (nextMethod) updatePopulation('samplingMethod', nextMethod)
    ElMessage.success('已按AI建议回填抽样依据字段')
  } finally {
    aiLoadingSamplingBasis.value = false
  }
}

async function generateAuditConclusionWithAI() {
  if (props.isReadonly) return
  aiLoadingConclusion.value = true
  try {
    const text = await generateAndConfirm(
      'sampling-audit-conclusion',
      auditConclusion.value,
      buildSamplingAiContext(`审计说明：${auditNote.value || '未填写'}`),
      'AI · 审计结论',
    )
    if (text) saveAuditConclusion(text)
  } finally {
    aiLoadingConclusion.value = false
  }
}

function mapOcrToVouchingFields(extracted: Record<string, any>, row: VouchingRow): Partial<VouchingRow> {
  const patch: Partial<VouchingRow> = {}
  const noteNo = String(extracted.contractNo || extracted.voucherNo || '').trim()
  const drawer = String(extracted.counterparty || extracted.drawer || '').trim()
  const acceptor = String(extracted.acceptor || '').trim()
  const maturityDate = String(extracted.settlementTime || extracted.maturityDate || '').trim()
  const amount = Number(extracted.contractAmount || extracted.amount || 0)
  const bizSummary = String(extracted.serviceContent || extracted.specialTerms || '').trim()
  if (noteNo) patch.noteNo = noteNo
  if (drawer) patch.drawer = drawer
  if (acceptor) patch.acceptor = acceptor
  if (maturityDate) patch.maturityDate = maturityDate
  if (amount > 0) patch.amount = amount
  if (bizSummary) patch.remark = row.remark ? `${row.remark}\nOCR:${bizSummary}` : `OCR:${bizSummary}`
  return patch
}

async function onUploadOcr(row: VouchingRow, file: File) {
  if (props.isReadonly) return
  updateVouchingRow(row.id, 'ocrStatus', 'processing')
  updateVouchingRow(row.id, 'attachmentName', file.name)
  const fd = new FormData()
  fd.append('file', file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      fd,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data ?? {}
    const extracted = (data.extracted_fields || {}) as Record<string, any>
    ocrExtracted.value.set(row.id, extracted)
    updateVouchingRow(row.id, 'attachmentId', String(data.attachment_id || ''))
    updateVouchingRow(row.id, 'attachmentName', file.name)
    updateVouchingRow(row.id, 'ocrStatus', 'done')
    ElMessage.success('OCR识别完成，可回填到当前抽查样本行')
  } catch {
    updateVouchingRow(row.id, 'ocrStatus', 'failed')
    ElMessage.warning('OCR识别失败，请稍后重试')
  }
}

async function onApplyOcr(row: VouchingRow, mode: 'empty-only' | 'override-all') {
  const extracted = ocrExtracted.value.get(row.id)
  if (!extracted) {
    ElMessage.info('暂无OCR结果，请先上传附件')
    return
  }
  if (mode === 'override-all') {
    try {
      await ElMessageBox.confirm('将使用OCR识别结果覆盖可映射字段，是否继续？', '覆盖回填确认', {
        confirmButtonText: '继续覆盖',
        cancelButtonText: '取消',
        type: 'warning',
      })
    } catch {
      return
    }
  }
  const patch = mapOcrToVouchingFields(extracted, row)
  let applied = 0
  ;(Object.keys(patch) as Array<keyof VouchingRow>).forEach((k) => {
    const nextVal = patch[k]
    if (nextVal === undefined || nextVal === null || nextVal === '') return
    const currVal = row[k] as any
    if (mode === 'empty-only' && currVal) return
    updateVouchingRow(row.id, k, nextVal as any)
    applied++
  })
  ElMessage.success(applied > 0 ? `已回填 ${applied} 个字段` : '没有可回填字段')
}

function onRemoveAttachment(row: VouchingRow) {
  if (props.isReadonly) return
  updateVouchingRow(row.id, 'attachmentId', '')
  updateVouchingRow(row.id, 'attachmentName', '')
  updateVouchingRow(row.id, 'ocrStatus', 'none')
  ocrExtracted.value.delete(row.id)
}

function getOcrStatusLabel(status: string): string {
  if (status === 'processing') return '识别中'
  if (status === 'done') return '已识别'
  if (status === 'failed') return '识别失败'
  return '未识别'
}

async function handleImportUpload(uploadFile: any) {
  const file = uploadFile?.raw || uploadFile
  if (!file) return
  const result = await importData(file)
  if (result.success) {
    ElMessage.success(`导入成功：${result.rowCount} 行`)
  } else {
    ElMessage.warning(result.errors?.[0] || '导入失败')
  }
}

// ─── 编制提示 ────────────────────────────────────────────────────────────────────

const GUIDANCE_TEXTS = [
  'CAS 1314审计抽样准则关于实质性细节测试的要求：设计样本时应考虑测试目标、总体特征、容忍和预期错报。',
  '抽样方法选择说明：根据总体特征选择随机抽样、系统抽样或货币单位抽样方法，并记录选择依据。',
  '例外项追查和评价程序：对每一例外项逐笔追查原因，区分异常偏差和总体偏差，评估是否反映系统性错误。',
  '样本结果推断总体的方法：根据样本中发现的错报推断总体错报，评估总体错报是否超过重要性水平。',
]

const SAMPLING_METHOD_TEXTS = [
  {
    key: '测试总体',
    value: '如应收票据借方发生额所有凭证共XX笔、贷方发生额所有凭证共XX笔等。',
    tone: 'normal',
  },
  {
    key: '特定样本',
    value: 'XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔。',
    tone: 'warn',
  },
  {
    key: '抽样总体',
    value: '测试总体扣除特定样本以外的样本，共XX笔、金额XX。',
    tone: 'normal',
  },
  {
    key: '确定的抽样样本量',
    value: '如XX笔（如果使用了样本计算器计算样本量，样本量计算过程记录见XX底稿）。',
    tone: 'normal',
  },
  {
    key: '抽样方法',
    value: '随机选样/系统选样/货币单元抽样/随意选样（非统计抽样适用）。使用IDEA（XX抽样工具）选样XX数量、金额XX的样本进行测试，抽样工具中的样本追踪过程和结果见XX底稿。',
    tone: 'info',
  },
]
</script>

<template>
  <div class="d1-tab-sampling-vouching">
      <div class="tab-header">
        <h4>抽样凭证 D1-13</h4>
        <GtReviewTrigger section-id="D1-sampling-header" />
      </div>
      <!-- 审计目标 -->
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="审计目标"
        class="audit-objective"
      >
        <template #default>
          <p>通过审计抽样选取样本，对抽样票据逐笔核查存在性、准确性和记录恰当性，以获取充分适当的审计证据。</p>
        </template>
      </el-alert>

      <!-- ═══════════════════ 抽样总体定义区 ═══════════════════ -->
      <div class="section-title">抽样总体定义</div>
      <details class="methodology-collapse" open>
        <summary class="methodology-summary">📖 样本选取标准与规模说明（点击展开/收起）</summary>
        <div class="methodology-body">
          <div v-for="(item, idx) in SAMPLING_METHOD_TEXTS" :key="`sampling-method-${idx}`" class="method-row">
            <span class="method-key">{{ item.key }}：</span>
            <span :class="item.tone === 'warn' ? 'method-text-warn' : item.tone === 'info' ? 'method-text-info' : 'method-text'">
              {{ item.value }}
            </span>
          </div>
        </div>
      </details>
      <div class="population-area">
        <div class="population-field full-width">
          <label>测试总体</label>
          <el-input
            :model-value="population.testPopulation"
            placeholder="如：应收票据借方/贷方发生额所有凭证"
            :disabled="isReadonly"
            @change="(v: string) => updatePopulation('testPopulation', v || '')"
          />
        </div>

        <div class="population-field full-width">
          <label>特定样本范围</label>
          <el-input
            :model-value="population.specificItemScope"
            placeholder="如：大额、关联方/关联交易、异常款项等"
            :disabled="isReadonly"
            @change="(v: string) => updatePopulation('specificItemScope', v || '')"
          />
        </div>

        <!-- 抽样总体描述 -->
        <div class="population-field full-width">
          <label>抽样总体</label>
          <el-input
            type="textarea"
            :rows="2"
            :model-value="population.populationDesc"
            placeholder="描述抽样总体范围..."
            :disabled="isReadonly"
            @change="(v: string) => updatePopulation('populationDesc', v || '')"
          />
        </div>

        <!-- 数量字段行 -->
        <div class="population-numbers">
          <div class="population-field">
            <label>总体笔数</label>
            <el-input-number
              :model-value="population.totalCount"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('totalCount', v || 0)"
            />
          </div>
          <div class="population-field">
            <label>总体金额</label>
            <el-input-number
              :model-value="population.totalAmount"
              size="small"
              :controls="false"
              :precision="2"
              :disabled="isReadonly"
              style="width: 150px"
              @change="(v: number) => updatePopulation('totalAmount', v || 0)"
            />
            <span class="field-hint" v-if="population.totalAmount > 0" v-html="fmtAmount(population.totalAmount)" />
          </div>
          <div class="population-field">
            <label>确定的抽样样本量</label>
            <el-input-number
              :model-value="population.sampleSize"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('sampleSize', v || 0)"
            />
          </div>
          <div class="population-field">
            <label>抽样方法</label>
            <div class="sampling-method-input">
              <el-input
                :model-value="population.samplingMethod"
                size="small"
                placeholder="随机选样/系统选样/货币单元抽样/随意选样"
                :disabled="isReadonly"
                style="width: 220px"
                @change="(v: string) => updatePopulation('samplingMethod', v || '')"
              />
              <el-tooltip :content="aiAvailable ? 'AI生成抽样依据建议并回填' : 'AI服务暂不可用'" placement="top">
                <el-button
                  size="small"
                  :loading="aiLoadingSamplingBasis"
                  :disabled="isReadonly || !aiAvailable"
                  @click="generateSamplingBasisWithAI"
                >
                  🤖 AI依据
                </el-button>
              </el-tooltip>
            </div>
          </div>
          <div class="population-field">
            <label>实际抽取笔数</label>
            <el-input-number
              :model-value="population.actualDrawn"
              size="small"
              :controls="false"
              :min="0"
              :disabled="isReadonly"
              style="width: 120px"
              @change="(v: number) => updatePopulation('actualDrawn', v || 0)"
            />
            <GtIndexChip
              v-if="population.sampleCalcRef"
              :value="population.sampleCalcRef"
              :context-project-id="projectId"
            />
          </div>
        </div>
        <div class="sampling-summary">
          <span class="sampling-summary-title">抽样依据摘要：</span>
          测试总体为“{{ population.testPopulation || '未填写' }}”；特定样本范围“{{ population.specificItemScope || '未填写' }}”；
          抽样总体“{{ population.populationDesc || '未填写' }}”；样本量 {{ population.sampleSize || 0 }} 笔，实际抽取 {{ population.actualDrawn || 0 }} 笔；
          抽样方法“{{ population.samplingMethod || '未填写' }}”。
        </div>
      </div>

      <!-- ═══════════════════ 特定样本区域 ═══════════════════ -->
      <div class="section-title">特定样本</div>
      <div class="specific-samples-area">
        <div
          v-for="sample in specificSamples"
          :key="sample.id"
          class="specific-sample-row"
        >
          <el-input
            :model-value="sample.description"
            size="small"
            placeholder="项目描述"
            :disabled="isReadonly"
            style="flex: 2"
            @change="(v: string) => updateSpecificSample(sample.id, 'description', v || '')"
          />
          <el-input-number
            :model-value="sample.amount"
            size="small"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            style="width: 130px"
            @change="(v: number) => updateSpecificSample(sample.id, 'amount', v || 0)"
          />
          <el-input
            :model-value="sample.reason"
            size="small"
            placeholder="抽出原因"
            :disabled="isReadonly"
            style="flex: 1"
            @change="(v: string) => updateSpecificSample(sample.id, 'reason', v || '')"
          />
          <el-button
            v-if="!isReadonly"
            type="danger"
            size="small"
            text
            class="delete-btn"
            @click="removeSpecificSample(sample.id)"
          >
            ✕
          </el-button>
        </div>
        <el-button
          size="small"
          :disabled="isReadonly"
          @click="addSpecificSample"
        >
          + 添加特定样本
        </el-button>
      </div>

      <!-- ═══════════════════ 分隔线 + 凭证核对明细 ═══════════════════ -->
      <el-divider />
      <div class="section-title">凭证核对明细</div>

      <!-- Toolbar -->
      <div class="table-toolbar">
        <el-button-group size="small">
          <el-button @click="() => exportTemplate()">导出模板</el-button>
          <el-button @click="() => exportData()">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :before-upload="(file) => { void handleImportUpload(file); return false }"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="openSampling">
          ⚡ 抽凭引擎
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addVouchingRow">
          + 添加核查项
        </el-button>
      </div>

      <!-- ═══ 抽凭引擎 Dialog（P0-4 联动，科目 1121 应收票据）═══ -->
      <el-dialog
        v-model="samplingVisible"
        title="⚡ 抽凭引擎（科目 1121 应收票据）"
        width="90%"
        top="5vh"
        :close-on-click-modal="false"
        destroy-on-close
      >
        <GtVoucherSamplingEngine
          v-if="samplingVisible && wpId && projectId"
          account-code="1121"
          phase="final"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="samplingYear"
          @filled="onSamplesFilled"
        />
      </el-dialog>

      <!-- 凭证核对明细 el-table 12列 -->
      <div v-if="useVirtualScroll" class="virtual-toolbar">
        <el-alert type="info" :closable="false" class="virtual-hint">
          行数较多（{{ browseRowCount }} 行）· {{ browseMode ? '虚拟滚动速览' : '表格编辑' }}模式 · 双击行可切换编辑
        </el-alert>
        <el-button size="small" @click="toggleBrowseMode">
          {{ browseMode ? '切换表格编辑' : '切换虚拟速览' }}
        </el-button>
      </div>
      <el-table-v2
        v-if="useVirtualScroll && browseMode"
        :columns="virtualColumns"
        :data="browseRows"
        :width="tableWidth"
        :height="tableHeight"
        :row-height="36"
        :header-height="40"
        :row-event-handlers="rowEventHandlers"
        fixed
        class="virtual-table"
      />
      <el-table
        v-if="!useVirtualScroll || !browseMode"
        :data="vouchingRows"
        border
        size="small"
        :row-class-name="getVouchingRowClass"
        :max-height="tableMaxHeight"
        class="vouching-table"
        style="width: 100%"
      >
        <!-- 序号（只读自动编号） -->
        <el-table-column label="序号" width="55" align="center">
          <template #default="{ row }: { row: VouchingRow }">
            <span>{{ row.seq }}</span>
          </template>
        </el-table-column>

        <!-- 票据类型 -->
        <el-table-column label="票据类型" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <el-select
              :model-value="row.noteType"
              placeholder="选择类型"
              size="small"
              clearable
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateVouchingRow(row.id, 'noteType', v || '')"
            >
              <el-option v-for="o in NOTE_TYPE_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <GtReviewDot row-prefix="D1-sampling" :row-key="row.id" />
          </template>
        </el-table-column>

        <!-- 票据号码 -->
        <el-table-column label="票据号码" min-width="140">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.noteNo"
              size="small"
              placeholder="票据号码"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'noteNo', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 出票人 -->
        <el-table-column label="出票人" min-width="100">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.drawer"
              size="small"
              placeholder="出票人"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'drawer', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 承兑人 -->
        <el-table-column label="承兑人" min-width="100">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.acceptor"
              size="small"
              placeholder="承兑人"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'acceptor', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 金额 -->
        <el-table-column label="金额" width="110" align="right">
          <template #default="{ row }: { row: VouchingRow }">
            <WpAmountInput
              :model-value="row.amount"
              size="small"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: number) => updateVouchingRow(row.id, 'amount', v || 0)"
            />
          </template>
        </el-table-column>

        <!-- 到期日 -->
        <el-table-column label="到期日" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-date-picker
              :model-value="row.maturityDate"
              type="date"
              format="YYYY-MM-DD"
              value-format="YYYY-MM-DD"
              size="small"
              placeholder="到期日"
              :disabled="isReadonly"
              style="width: 100%"
              @change="(v: string) => updateVouchingRow(row.id, 'maturityDate', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 存在性验证 -->
        <el-table-column label="存在性验证" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据实物是否存在" placement="top">
              <el-select
                :model-value="row.existenceCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.existenceCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'existenceCheck', v || '')"
              >
                <el-option v-for="o in EXISTENCE_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 准确性验证 -->
        <el-table-column label="准确性验证" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据金额与账面记录是否一致" placement="top">
              <el-select
                :model-value="row.accuracyCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.accuracyCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'accuracyCheck', v || '')"
              >
                <el-option v-for="o in ACCURACY_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 记录恰当性 -->
        <el-table-column label="记录恰当性" width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-tooltip content="验证票据账务处理是否恰当" placement="top">
              <el-select
                :model-value="row.appropriatenessCheck"
                placeholder="—"
                size="small"
                clearable
                :disabled="isReadonly"
                :class="getCheckClass(row.appropriatenessCheck)"
                style="width: 100%"
                @change="(v: string) => updateVouchingRow(row.id, 'appropriatenessCheck', v || '')"
              >
                <el-option v-for="o in APPROPRIATENESS_OPTIONS" :key="o" :label="o" :value="o" />
              </el-select>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 支持性文件（附件+OCR+回写） -->
        <el-table-column label="支持性文件" min-width="220">
          <template #default="{ row }: { row: VouchingRow }">
            <div class="attach-cell">
              <el-upload
                :show-file-list="false"
                :auto-upload="false"
                :disabled="isReadonly"
                @change="(f: any) => onUploadOcr(row, f.raw || f)"
              >
                <el-button size="small" text :disabled="isReadonly">📎 上传/OCR</el-button>
              </el-upload>
              <el-tag size="small" :type="row.ocrStatus === 'failed' ? 'danger' : row.ocrStatus === 'done' ? 'success' : 'info'">
                {{ getOcrStatusLabel(row.ocrStatus) }}
              </el-tag>
              <span class="attach-name" :title="row.attachmentName || ''">{{ row.attachmentName || '未上传附件' }}</span>
              <div class="attach-actions">
                <el-button size="small" text :disabled="isReadonly || row.ocrStatus !== 'done'" @click="onApplyOcr(row, 'empty-only')">回填空字段</el-button>
                <el-button size="small" text :disabled="isReadonly || row.ocrStatus !== 'done'" @click="onApplyOcr(row, 'override-all')">覆盖回填</el-button>
                <el-button size="small" text type="danger" :disabled="isReadonly || !row.attachmentName" @click="onRemoveAttachment(row)">移除</el-button>
              </div>
            </div>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }: { row: VouchingRow }">
            <el-input
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              :disabled="isReadonly"
              @change="(v: string) => updateVouchingRow(row.id, 'remark', v || '')"
            />
          </template>
        </el-table-column>

        <!-- 索引号 -->
        <el-table-column label="索引号" width="130">
          <template #default="{ row }: { row: VouchingRow }">
            <div class="index-cell">
              <el-input
                :model-value="row.indexRef"
                size="small"
                placeholder="索引号"
                :disabled="isReadonly"
                @change="(v: string) => updateVouchingRow(row.id, 'indexRef', v || '')"
              />
              <GtIndexChip
                v-if="row.indexRef"
                :value="row.indexRef"
                :context-project-id="projectId"
              />
            </div>
          </template>
        </el-table-column>

        <!-- 操作列：删除 -->
        <el-table-column label="" width="50" fixed="right">
          <template #default="{ row }: { row: VouchingRow }">
            <el-popconfirm
              title="确定删除该行？"
              confirm-button-text="删除"
              cancel-button-text="取消"
              @confirm="removeVouchingRow(row.id)"
            >
              <template #reference>
                <el-button
                  v-if="!isReadonly"
                  type="danger"
                  size="small"
                  text
                  class="delete-btn"
                >
                  ✕
                </el-button>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══════════════════ 核对结果区 ═══════════════════ -->
      <div class="summary-row">
        <span class="summary-label">核查笔数 (G32)：</span>
        <span class="summary-value">{{ checkedCount }}</span>
        <span class="summary-separator">|</span>
        <span class="summary-label">核查金额合计 (H32)：</span>
        <span class="summary-value" v-html="fmtAmount(checkedAmountTotal)" />
      </div>

      <!-- ═══════════════════ 例外汇总区 E48-G50 ═══════════════════ -->
      <div class="section-title">例外汇总</div>
      <table class="recon-table">
        <thead>
          <tr>
            <th>例外类别</th>
            <th>例外笔数</th>
            <th>例外金额</th>
            <th>占比</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="(row, idx) in exceptionSummary"
            :key="'exc-' + idx"
            :class="{ 'exception-rate-exceed': row.rate > tolerableErrorRate }"
          >
            <td>{{ row.category }}</td>
            <td class="recon-num">{{ row.count }}</td>
            <td class="recon-num" v-html="fmtAmount(row.amount)" />
            <td
              class="recon-num"
              :class="{ 'rate-exceed': row.rate > tolerableErrorRate }"
            >
              {{ fmtPercent(row.rate) }}
            </td>
          </tr>
        </tbody>
      </table>

      <!-- 例外超标预警 -->
      <el-tag
        v-if="hasExceedingException"
        type="danger"
        size="large"
        effect="light"
        class="exception-warning-tag"
      >
        ⚠️ 例外率超标，请考虑扩大样本量
      </el-tag>

      <!-- 可容忍误差率设置 -->
      <div class="tolerable-rate-area">
        <label>可容忍误差率：</label>
        <el-input-number
          :model-value="tolerableErrorRate * 100"
          size="small"
          :controls="true"
          :min="0"
          :max="100"
          :precision="1"
          :step="1"
          :disabled="isReadonly"
          style="width: 110px"
          @change="(v: number) => updateTolerableErrorRate((v || 5) / 100)"
        />
        <span class="field-hint">%</span>
      </div>

      <!-- ═══════════════════ 测试结论 ═══════════════════ -->
      <div class="section-title">测试结论</div>
      <el-select
        :model-value="testConclusion"
        placeholder="选择测试结论"
        size="default"
        clearable
        :disabled="isReadonly"
        style="width: 300px; margin-bottom: 16px"
        @change="(v: string) => updateTestConclusion(v || '')"
      >
        <el-option v-for="o in TEST_CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
      </el-select>

      <!-- ═══════════════════ 审计说明 ═══════════════════ -->
      <div class="section-title">审计说明</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditNote"
          placeholder="请输入审计说明..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditNote(v || '')"
        />
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计说明' : 'AI服务暂不可用'" placement="top">
            <el-button size="small" :loading="aiLoadingNote" :disabled="isReadonly || !aiAvailable" @click="generateAuditNoteWithAI">🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-sampling-note')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- ═══════════════════ 审计结论 ═══════════════════ -->
      <div class="section-title">审计结论</div>
      <div class="note-section">
        <el-input
          type="textarea"
          :rows="4"
          :model-value="auditConclusion"
          placeholder="请输入审计结论..."
          :disabled="isReadonly"
          @change="(v: string) => saveAuditConclusion(v || '')"
        />
        <div class="note-actions">
          <el-tooltip :content="aiAvailable ? 'AI辅助生成审计结论' : 'AI服务暂不可用'" placement="top">
            <el-button size="small" :loading="aiLoadingConclusion" :disabled="isReadonly || !aiAvailable" @click="generateAuditConclusionWithAI">🤖 AI</el-button>
          </el-tooltip>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="onReview('D1-sampling-conclusion')"
          >
            💬 复核
          </el-button>
        </div>
      </div>

      <!-- ═══════════════════ 编制提示 ═══════════════════ -->
      <details class="guidance-fold">
        <summary>📋 编制提示</summary>
        <p v-for="(t, i) in GUIDANCE_TEXTS" :key="'g-' + i">{{ t }}</p>
      </details>
  </div>
</template>

<style scoped>
.d1-tab-sampling-vouching {
  padding: 12px;
}

.tab-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.tab-header h4 {
  margin: 0;
  font-size: 15px;
}

.mode-switcher {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.oo-disabled-hint {
  cursor: help;
  font-size: 14px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective p {
  margin: 0 0 4px;
  font-size: var(--wp-font-size, 13px);
  line-height: 1.6;
}

.methodology-collapse {
  margin-bottom: 12px;
  border-radius: 6px;
  border: 1px solid #faecd8;
  border-left: 3px solid #e6a23c;
  background: #fffbf0;
}

.methodology-summary {
  cursor: pointer;
  padding: 8px 14px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #b88230;
}

.methodology-body {
  padding: 8px 14px 12px;
}

.method-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 6px;
  font-size: 12px;
  line-height: 1.7;
}

.method-row:last-child {
  margin-bottom: 0;
}

.method-key {
  color: #866736;
  font-weight: 600;
  white-space: nowrap;
}

.method-text {
  color: #8c6d3f;
}

.method-text-warn {
  color: #c45656;
}

.method-text-info {
  color: #409eff;
}

/* ─── 抽样总体定义区 ─── */
.population-area {
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 14px;
  margin-bottom: 16px;
}

.population-field {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}

.population-field.full-width {
  flex-direction: column;
  align-items: flex-start;
}

.population-field label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #606266;
  white-space: nowrap;
  min-width: 110px;
}

.population-field.full-width label {
  min-width: auto;
  margin-bottom: 4px;
}

.population-field.full-width .el-textarea {
  width: 100%;
}

.population-numbers {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: flex-end;
}

.field-hint {
  font-size: 12px;
  color: #909399;
}

.sampling-summary {
  margin-top: 4px;
  padding: 8px 10px;
  background: #fff;
  border: 1px dashed #dcdfe6;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}

.sampling-summary-title {
  font-weight: 600;
  color: #303133;
}

.sampling-method-input {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 特定样本区域 ─── */
.specific-samples-area {
  margin-bottom: 16px;
}

.specific-sample-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

/* ─── 工具栏 ─── */
.table-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.virtual-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 8px; flex-wrap: wrap; }
.virtual-hint { margin-bottom: 0; flex: 1; }
.virtual-table { margin-bottom: 8px; }

/* ─── 凭证核对明细表 ─── */
.vouching-table {
  margin-bottom: 12px;
}

/* 例外项行浅红色背景 */
:deep(.el-table .exception-row td) {
  background-color: #fef0f0 !important;
}

/* 负数红色括号 */
:deep(.negative-amount) {
  color: #f56c6c;
}

/* 验证结果颜色编码 */
:deep(.check-positive .el-input__inner),
:deep(.check-positive .el-select__placeholder) {
  color: #67c23a !important;
}

:deep(.check-negative .el-input__inner),
:deep(.check-negative .el-select__placeholder) {
  color: #f56c6c !important;
}

/* ─── 合计行/核对结果区 ─── */
.summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  margin-bottom: 16px;
}

.summary-label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
}

.summary-value {
  font-size: 14px;
  font-weight: 700;
  color: #303133;
}

.summary-separator {
  color: #c0c4cc;
  margin: 0 8px;
}

/* ─── 段落标题 ─── */
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 18px 0 10px;
}

/* ─── 例外汇总表格 ─── */
.recon-table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 16px;
}

.recon-table th,
.recon-table td {
  border: 1px solid #ebeef5;
  padding: 8px 10px;
  vertical-align: middle;
}

.recon-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
  text-align: center;
}

.recon-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

/* 例外率超标行 */
.exception-rate-exceed {
  background-color: #fef0f0;
}

.rate-exceed {
  color: #f56c6c !important;
  font-weight: 600;
}

/* 例外超标预警标签 */
.exception-warning-tag {
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── 可容忍误差率 ─── */
.tolerable-rate-area {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.tolerable-rate-area label {
  font-weight: 500;
}

/* ─── 索引号单元格 ─── */
.index-cell {
  display: flex;
  align-items: center;
  gap: 6px;
}

.index-cell .el-input {
  flex: 1;
}

.attach-cell {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.attach-name {
  font-size: 12px;
  color: #606266;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.attach-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

/* ─── 删除按钮 ─── */
.delete-btn {
  padding: 2px 4px;
  min-height: auto;
}

/* ─── 审计说明/结论 ─── */
.note-section {
  margin-bottom: 8px;
}

.note-actions {
  margin-top: 6px;
  display: flex;
  gap: 8px;
}

/* ─── 编制提示折叠区 ─── */
.guidance-fold {
  margin: 16px 0;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  padding: 10px 14px;
  border-radius: 0 4px 4px 0;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.guidance-fold summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}

.guidance-fold p {
  margin: 6px 0;
  line-height: 1.6;
}
</style>
