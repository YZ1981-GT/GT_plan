<template>
  <div class="g1-derivative-check" data-testid="g1-derivative-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-14 衍生金融工具核查表</h3>
        <p class="sheet-sub">识别衍生 / 嵌入衍生 → 结论 → 抽查会计处理 → 专家工作</p>
      </div>
      <div class="head-actions tab-toolbar">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-14"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <el-button v-if="!isReadonly" size="small" plain @click="dc.applyEmbeddedDemo()">
          填入嵌入衍生示例
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-9" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-13" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:S12" /></span>
        <el-button size="small" @click="openReviewDialog('G1-14-conclusion')">💬复核</el-button>
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示与逻辑</summary>
      <div class="guidance-content">
        <p><strong>审计目标：</strong>确定衍生金融工具投资的确认、计量是否准确。</p>
        <p>1. 审阅贷款、投资、存款等协议，识别是否含衍生或嵌入衍生条款。</p>
        <p>2. <strong>B 问卷：</strong>合同价值是否受下列变量影响。逻辑已修正为「<em>全部为否</em> → 无衍生，可跳过后续；<em>任一为是</em> → 继续 C」。</p>
        <p>3. <strong>C 问卷：</strong>判断是否嵌入衍生；若否，则单独核算。</p>
        <p>4. 若主合同属 CAS22 金融资产，嵌入衍生通常整体计量不分拆；抽查凭证并在必要时复核估值专家工作。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：确定衍生金融工具投资的确认、计量是否准确；识别单独衍生与嵌入衍生，评价会计处理与披露恰当性。"
    />

    <!-- 工具名称 -->
    <div class="meta-row">
      <label class="field-label">工具名称</label>
      <el-input
        :model-value="dc.instrumentName.value"
        size="small"
        placeholder="填写拟核查的合同 / 工具名称"
        :disabled="isReadonly"
        style="max-width: 420px"
        @change="(v: string) => dc.setInstrumentName(v)"
      />
    </div>

    <!-- B 变量识别 -->
    <el-divider content-position="left">
      <span class="divider-title">B. 协议是否包含下列影响合同价值的变量（是/否）</span>
    </el-divider>
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      class="logic-alert"
      title="逻辑说明：若 B 项全部为「否」，则未识别衍生特征，无需继续回答 C 及后续抽查（可仍填写专家区）。任一为「是」则继续 C。"
    />

    <!-- 合同 OCR 智能识别 -->
    <div v-if="!isReadonly && wpId" class="ocr-row">
      <el-upload
        :show-file-list="false"
        :before-upload="onContractOcrUpload"
        accept=".pdf,.png,.jpg,.jpeg"
        :disabled="ocrLoading"
      >
        <el-button size="small" type="primary" plain :loading="ocrLoading">
          📎 上传合同智能识别变量
        </el-button>
      </el-upload>
      <span class="ocr-hint">上传贷款/投资/存款协议，自动识别利率/汇率/商品价格等挂钩条款并勾选 B 问卷（需人工复核）</span>
    </div>

    <div class="questionnaire-list">
      <div v-for="item in dc.bQuestions.value" :key="item.id" class="questionnaire-item">
        <div class="question-row">
          <span class="question-seq">{{ item.seq }}.</span>
          <span class="question-text">{{ item.label }}</span>
          <el-radio-group
            :model-value="item.answer"
            :disabled="isReadonly"
            size="small"
            @update:model-value="(v: boolean | string | number | undefined) => dc.setBAnswer(item.id, v as boolean | null)"
          >
            <el-radio :value="true">是</el-radio>
            <el-radio :value="false">否</el-radio>
          </el-radio-group>
        </div>
        <el-input
          :model-value="item.remark"
          size="small"
          placeholder="说明（选填）"
          :disabled="isReadonly"
          class="explain-input"
          @change="(v: string) => dc.setBRemark(item.id, v)"
        />
      </div>
    </div>

    <el-alert
      v-if="dc.skipFurther.value"
      type="success"
      :closable="false"
      title="B 项全部为否：未识别出衍生工具特征，后续嵌入判断与会计抽查可简化填写。"
      class="gate-alert"
    />

    <!-- C 嵌入衍生 -->
    <template v-if="dc.showEmbeddedSection.value">
      <el-divider content-position="left">
        <span class="divider-title">C. 嵌入衍生工具判断</span>
      </el-divider>
      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="logic-alert"
        title="B 存在「是」：协议可能含衍生或嵌入衍生，请回答下列问题。若判定非嵌入，应单独核算衍生工具。"
      />
      <div class="questionnaire-list">
        <div v-for="item in dc.cQuestions.value" :key="item.id" class="questionnaire-item">
          <div class="question-row">
            <span class="question-seq">{{ item.seq }}.</span>
            <span class="question-text">{{ item.question }}</span>
            <el-radio-group
              :model-value="item.answer"
              :disabled="isReadonly"
              size="small"
              @update:model-value="(v: boolean | string | number | undefined) => dc.setCAnswer(item.id, v as boolean | null)"
            >
              <el-radio :value="true">是</el-radio>
              <el-radio :value="false">否</el-radio>
            </el-radio-group>
          </div>
          <el-input
            :model-value="item.explanation"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="说明（选填）"
            :disabled="isReadonly"
            class="explain-input"
            @change="(v: string) => dc.setCExplanation(item.id, v)"
          />
        </div>
      </div>
    </template>

    <!-- 结论区 -->
    <el-divider content-position="left">
      <span class="divider-title">识别结论</span>
    </el-divider>
    <div class="conclusion-area">
      <span class="conclusion-label">结论：</span>
      <el-tag
        :color="dc.idChip.value.color"
        :type="dc.idChip.value.type"
        size="large"
        effect="dark"
        round
      >
        {{ dc.idChip.value.label }}
      </el-tag>
    </div>
    <el-alert
      v-if="dc.cas22Hint.value"
      :title="dc.cas22Hint.value"
      type="warning"
      show-icon
      :closable="false"
      class="gate-alert"
    />

    <div class="meta-grid">
      <div class="meta-field">
        <label class="field-label">衍生工具性质说明</label>
        <el-input
          :model-value="dc.natureDesc.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="说明衍生 / 嵌入衍生的条款性质…"
          @change="(v: string) => dc.setMetaField('natureDesc', v)"
        />
      </div>
      <div class="meta-field">
        <label class="field-label">科目编码</label>
        <el-input
          :model-value="dc.accountCode.value"
          size="small"
          :disabled="isReadonly"
          placeholder="如 1501"
          @change="(v: string) => dc.setMetaField('accountCode', v)"
        />
      </div>
      <div class="meta-field">
        <label class="field-label">会计政策 / 处理</label>
        <el-input
          :model-value="dc.accountingPolicy.value"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 4 }"
          :disabled="isReadonly"
          placeholder="整体 FVTPL / 单独核算 / 套期等"
          @change="(v: string) => dc.setMetaField('accountingPolicy', v)"
        />
      </div>
      <div class="meta-field row-check">
        <el-checkbox
          :model-value="dc.cas22HybridNoted.value"
          :disabled="isReadonly"
          @change="(v: boolean | string | number) => dc.setCas22HybridNoted(!!v)"
        >
          已考虑 CAS22：主合同为金融资产时嵌入衍生通常不分拆、整体计量
        </el-checkbox>
      </div>
    </div>

    <!-- 抽查会计处理 -->
    <el-divider content-position="left">
      <span class="divider-title">抽查衍生工具的会计处理</span>
    </el-divider>
    <div class="section-actions">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="dc.addVoucher()">增行</el-button>
      <el-button size="small" :disabled="isReadonly" @click="onSyncFromG113">从 G1-13 带入</el-button>
    </div>

    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1501，与 G1-13 同源引擎）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1501"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          @filled="onSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>
    <el-table :data="dc.vouchers.value" border size="small" max-height="320" empty-text="暂无抽查记录">
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.date"
            size="small"
            :disabled="isReadonly"
            placeholder="YYYY-MM-DD"
            @change="(v: string) => dc.updateVoucher(row.id, { date: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="110">
        <template #default="{ row }">
          <el-input
            :model-value="row.voucherNo"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateVoucher(row.id, { voucherNo: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="业务内容" min-width="140">
        <template #default="{ row }">
          <el-input
            :model-value="row.businessContent"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateVoucher(row.id, { businessContent: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="明细科目" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.detailAccount"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateVoucher(row.id, { detailAccount: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="对方科目" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.counterAccount"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateVoucher(row.id, { counterAccount: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="借方" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            :model-value="row.debitAmount"
            size="small"
            style="width: 100%"
            :disabled="isReadonly"
            @update:model-value="(v: number) => dc.updateVoucher(row.id, { debitAmount: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="贷方" width="100" align="right">
        <template #default="{ row }">
          <WpAmountInput
            :model-value="row.creditAmount"
            size="small"
            style="width: 100%"
            :disabled="isReadonly"
            @update:model-value="(v: number) => dc.updateVoucher(row.id, { creditAmount: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.conclusion"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateVoucher(row.id, { conclusion: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly"
            size="small"
            type="danger"
            link
            @click="dc.removeVoucher(row.id)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 专家 -->
    <el-divider content-position="left">
      <span class="divider-title">专家资质及利用估值专家的工作</span>
    </el-divider>
    <el-table :data="dc.experts.value" border size="small">
      <el-table-column label="序号" width="60">
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>
      <el-table-column label="项目" min-width="240">
        <template #default="{ row }">{{ row.item }}</template>
      </el-table-column>
      <el-table-column label="索引号" width="160">
        <template #default="{ row }">
          <div class="expert-index">
            <el-input
              :model-value="row.indexRef"
              size="small"
              :disabled="isReadonly"
              placeholder="S12 / wp:S12"
              @change="(v: string) => dc.updateExpert(row.id, { indexRef: normalizeExpertIndex(v) })"
            />
            <span v-if="expertChipValue(row.indexRef)" class="chip-wrap">
              <GtIndexChip :value="expertChipValue(row.indexRef)!" />
            </span>
          </div>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="160">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateExpert(row.id, { remark: v })"
          />
        </template>
      </el-table-column>
    </el-table>

    <!-- 旧版清单兼容 -->
    <details v-if="dc.legacyRows.value.length" class="legacy-block">
      <summary>📂 历史工具登记清单（旧版数据，只读参考）</summary>
      <el-table :data="dc.legacyRows.value" border size="small" max-height="240" class="legacy-table">
        <el-table-column prop="instrumentName" label="工具名称" min-width="120" />
        <el-table-column prop="instrumentType" label="类型" width="90" />
        <el-table-column prop="notionalAmount" label="名义金额" width="110" align="right" />
        <el-table-column prop="counterparty" label="对手方" width="120" />
        <el-table-column prop="complianceConclusion" label="合规结论" min-width="120" />
      </el-table>
    </details>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="dc.auditConclusion.value"
      @update:conclusion="dc.setAuditConclusion"
      note-ai-section="derivative-note"
      conclusion-ai-section="derivative-conclusion"
      note-placeholder="说明协议审阅范围、B/C 识别结果、会计处理抽查及专家工作利用情况。"
      note-hint="覆盖衍生识别、嵌入判断、凭证抽查与估值专家。"
      conclusion-hint="明确是否存在衍生/嵌入衍生，会计处理是否恰当。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, toRef, computed, inject, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useG1DerivativeCheck } from '../../composables/useG1DerivativeCheck'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()
const wpId = computed(() => props.wpId ?? '')
const projectId = computed(() => props.projectId ?? '')
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const dc = useG1DerivativeCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const AUDIT_NOTE_KEY = 'G1-14-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

function normalizeExpertIndex(v: string): string {
  const t = String(v || '').trim()
  if (!t) return ''
  if (/^wp:/i.test(t)) return t
  if (/^S12\b/i.test(t)) return `wp:${t}`
  return t
}

function expertChipValue(raw: string): string | null {
  const t = String(raw || '').trim()
  if (!t) return null
  if (/^wp:/i.test(t)) return t
  if (/^S12/i.test(t)) return `wp:${t}`
  return null
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G1',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => props.debouncedSave(itemId, { remark, conclusion: null }),
  isReadonly: computed(() => props.isReadonly === true),
})

function onSamplingFilled(payload: {
  samples: SampledVoucher[]
  fillMode?: FillMode
}) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  const mode = payload.fillMode === 'replace' ? 'replace' : 'append'
  const n = dc.applySamplingResults(payload.samples || [], mode)
  if (n > 0) ElMessage.success(`已从抽凭引擎填入 ${n} 行`)
  else ElMessage.info('无样本可填入')
}

function onSyncFromG113() {
  const n = dc.syncVouchersFromG113()
  if (n > 0) ElMessage.success(`已从 G1-13 带入 ${n} 行凭证`)
  else ElMessage.info('G1-13 暂无可带入的凭证行')
}

const ocrLoading = ref(false)

async function onContractOcrUpload(file: File): Promise<boolean> {
  if (!wpId.value) return false
  ocrLoading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const res: any = await api.post(
      `/api/workpapers/${wpId.value}/g1/contract-ocr`,
      form,
      { headers: { 'Content-Type': 'multipart/form-data' } } as any,
    )
    const data = res?.data ?? res
    const fields = data?.extracted_fields ?? {}
    const hitKeys = Object.keys(fields).filter(
      (k) => k.startsWith('b') && fields[k] === true,
    )
    if (!hitKeys.length) {
      ElMessage.info('未识别到影响合同价值的变量条款，请人工核对')
      return false
    }
    await ElMessageBox.confirm(
      `识别到 ${hitKeys.length} 项影响变量，是否自动勾选 B 问卷对应项为「是」？（仍需人工复核）`,
      '合同 OCR 识别结果',
      { confirmButtonText: '应用', cancelButtonText: '取消', type: 'info' },
    )
    const applied = dc.applyContractOcrToB(fields)
    if (applied > 0) ElMessage.success(`已自动勾选 ${applied} 项 B 变量，请人工复核`)
    else ElMessage.info('识别项已勾选，无新增变更')
  } catch (e: any) {
    if (e !== 'cancel') ElMessage.warning('OCR 识别失败或已取消')
  } finally {
    ocrLoading.value = false
  }
  return false
}
</script>

<style scoped>
.g1-derivative-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 12px; margin-bottom: 12px; flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.guidance-details { margin-bottom: 10px; font-size: 12px; color: #606266; }
.guidance-details summary { cursor: pointer; color: #4b2d77; font-weight: 500; }
.guidance-content { margin-top: 8px; }
.guidance-content p { margin: 4px 0; }
.objective-alert, .logic-alert, .gate-alert { margin-bottom: 10px; }
.ocr-row { display: flex; align-items: center; gap: 12px; margin: 8px 0 12px; flex-wrap: wrap; }
.ocr-hint { font-size: 12px; color: #909399; }
.divider-title { font-weight: 600; color: #303133; }
.meta-row { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
.field-label { font-weight: 600; color: #606266; font-size: 13px; margin-bottom: 4px; display: block; }
.questionnaire-list { display: flex; flex-direction: column; gap: 10px; margin-bottom: 12px; }
.question-row { display: flex; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.question-seq { font-weight: 600; color: #606266; min-width: 36px; }
.question-text { flex: 1; min-width: 180px; line-height: 1.5; }
.explain-input { margin-left: 36px; margin-top: 4px; max-width: 640px; }
.conclusion-area {
  display: flex; align-items: center; gap: 10px; margin: 8px 0 12px;
  padding: 10px 14px; background: #f8f9fb; border-radius: 6px; border: 1px solid #ebeef5;
}
.conclusion-label { font-weight: 600; }
.meta-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 12px; }
.meta-field.row-check { grid-column: 1 / -1; display: flex; align-items: center; }
.section-actions { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.sampling-collapse { margin-bottom: 12px; }
.expert-index { display: flex; flex-direction: column; gap: 4px; }
.legacy-block { margin: 16px 0; font-size: 12px; color: #909399; }
.legacy-block summary { cursor: pointer; }
.legacy-table { margin-top: 8px; }
@media (max-width: 900px) {
  .meta-grid { grid-template-columns: 1fr; }
}
</style>
