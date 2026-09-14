<template>
  <div class="f2-val-sheet f2-contract-check f2-soft-matrix">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <header class="sheet-header">
      <div>
        <h3>合同履约成本检查表</h3>
        <span class="code">F2-56</span>
      </div>
      <div class="stat-row">
        <span class="stat">测试金额 {{ fmt(chk.stats.value.testedAmount) }}</span>
        <span class="stat sub">不正确 {{ fmt(chk.stats.value.incorrectAmount) }}</span>
        <span class="stat sub">差错率 {{ fmtPct(chk.stats.value.errorRate) }}</span>
        <span class="stat-text" :class="{ warn: chk.isCoverageLow.value }">
          覆盖率 {{ chk.coverageRatio.value.toFixed(1) }}%
        </span>
        <el-tag v-if="chk.issueCount.value" type="danger" size="small">
          异常 {{ chk.issueCount.value }} 笔
        </el-tag>
      </div>
    </header>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p v-for="(tip, i) in tips" :key="i">{{ i + 1 }}. {{ tip }}</p>
      </div>
    </details>

    <F2ContractCostTestExampleRef />

    <div class="section-block">
      <div class="section-label">一、审计目标</div>
      <ol class="objective-list">
        <li v-for="(obj, i) in objectives" :key="i">{{ obj }}</li>
      </ol>
    </div>

    <div class="section-block">
      <div class="section-label">二、样本选取标准与范围</div>
      <div class="params-grid">
        <label class="wide">样本总体
          <el-input v-if="!isReadonly" :model-value="chk.params.value.populationDesc" size="small"
            @update:model-value="(v: string) => chk.updateParams({ populationDesc: v })" />
          <span v-else>{{ chk.params.value.populationDesc }}</span>
        </label>
        <label class="wide">选取方法
          <el-input v-if="!isReadonly" :model-value="chk.params.value.method" size="small"
            @update:model-value="(v: string) => chk.updateParams({ method: v })" />
          <span v-else>{{ chk.params.value.method }}</span>
        </label>
        <label class="full">选取过程
          <el-input v-if="!isReadonly" :model-value="chk.params.value.process" type="textarea" :rows="2"
            @update:model-value="(v: string) => chk.updateParams({ process: v })" />
          <span v-else>{{ chk.params.value.process || '—' }}</span>
        </label>
        <label>总体金额
          <el-input-number :model-value="chk.params.value.populationAmount" size="small" :controls="false"
            :disabled="isReadonly" class="compact-num wide"
            @change="(v: number | undefined) => chk.updateParams({ populationAmount: v ?? 0 })" />
        </label>
        <label>重要性
          <el-input-number :model-value="chk.params.value.materiality" size="small" :controls="false"
            :disabled="isReadonly" class="compact-num wide"
            @change="(v: number | undefined) => chk.updateParams({ materiality: v ?? 0 })" />
        </label>
        <label>可容忍错报
          <el-input-number :model-value="chk.params.value.tolerableMisstatement" size="small" :controls="false"
            :disabled="isReadonly" class="compact-num wide"
            @change="(v: number | undefined) => chk.updateParams({ tolerableMisstatement: v ?? 0 })" />
        </label>
        <label>预期错报
          <el-input-number :model-value="chk.params.value.expectedMisstatement" size="small" :controls="false"
            :disabled="isReadonly" class="compact-num wide"
            @change="(v: number | undefined) => chk.updateParams({ expectedMisstatement: v ?? 0 })" />
        </label>
        <label>样本量
          <el-input-number :model-value="chk.params.value.sampleSize" size="small" :controls="false"
            :disabled="isReadonly" class="compact-num"
            @change="(v: number | undefined) => chk.updateParams({ sampleSize: v ?? 0 })" />
        </label>
      </div>
    </div>

    <el-collapse v-if="wpId && projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1410 合同履约成本）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1410"
          phase="final"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addAndOpenSample">+ 新增样本</el-button>
      </div>
      <div class="toolbar-right">
        <F2SheetToolbar
          :wp-id="wpId"
          api-prefix="f2-spe"
          sheet="F2-56"
          :disabled="isReadonly"
          review-section="F2-56-note"
        />
        <GtIndexChip value="wp:F2-56" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ filledCount }} 笔样本</el-tag>
      </div>
    </div>

    <div v-if="projectId && wpId" class="evidence-panel">
      <h4>检查样本附件</h4>
      <p>上传合同、验收单、物流单等；行内仍可对单笔样本做 OCR 确认回填。</p>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="F2-56"
        :item-index="1"
        accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
      />
    </div>

    <div class="section-block">
      <div class="section-label">三、测试表</div>
      <div class="test-checks">
        <span class="test-checks-title">测试内容说明：</span>
        <span v-for="(c, i) in testChecks" :key="i" class="test-check-item">{{ c }}</span>
      </div>

      <div class="table-scroll">
        <table class="matrix-table">
          <thead>
            <tr>
              <th rowspan="2" class="sticky col-project">项目名称</th>
              <th rowspan="2" class="sticky col-account">合同履约成本<br>科目/明细</th>
              <th colspan="5" class="grp grp-voucher">记账凭证</th>
              <th colspan="2" class="grp grp-contract">合同/协议</th>
              <th colspan="2" class="grp grp-receipt">到货验收单</th>
              <th colspan="4" class="grp grp-logistics">物流单/运输单</th>
              <th colspan="4" class="grp grp-alloc">费用分配表/计算表</th>
              <th rowspan="2" class="col-idx">索引号</th>
              <th rowspan="2" class="col-flag">是否<br>异常</th>
              <th rowspan="2" class="col-issue">异常说明</th>
              <th rowspan="2" class="col-act" />
            </tr>
            <tr>
              <th class="sub">凭证号</th>
              <th class="sub">业务内容</th>
              <th class="sub">对方科目</th>
              <th class="sub">对方项目</th>
              <th class="sub">金额</th>
              <th class="sub">日期/编号</th>
              <th class="sub">主要条款</th>
              <th class="sub">产品名称</th>
              <th class="sub">金额</th>
              <th class="sub">数量</th>
              <th class="sub">日期/编号</th>
              <th class="sub">产品名称</th>
              <th class="sub">物流商</th>
              <th class="sub">数量</th>
              <th class="sub">月份</th>
              <th class="sub">金额</th>
              <th class="sub">分配依据</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="row in chk.enrichedSamples.value"
              :key="row.id"
              :class="{ 'row-warn': row.hasIssue }"
            >
              <td class="sticky col-project">
                <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { projectName: v })" />
                <span v-else>{{ row.projectName || '—' }}</span>
              </td>
              <td class="sticky col-account">
                <el-input v-if="!isReadonly" :model-value="row.accountDetail" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { accountDetail: v })" />
                <span v-else>{{ row.accountDetail || '—' }}</span>
              </td>

              <td>
                <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { voucherNo: v })" />
                <span v-else>{{ row.voucherNo || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { businessContent: v })" />
                <span v-else class="text-left">{{ row.businessContent || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.offsetAccount" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { offsetAccount: v })" />
                <span v-else>{{ row.offsetAccount || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.offsetProject" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { offsetProject: v })" />
                <span v-else>{{ row.offsetProject || '—' }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.voucherAmount" size="small" :controls="false"
                  class="compact-num wide"
                  @change="(v: number | undefined) => chk.updateSample(row.id, { voucherAmount: v ?? 0 })" />
                <span v-else class="auto">{{ fmt(row.voucherAmount) }}</span>
              </td>

              <td>
                <el-input v-if="!isReadonly" :model-value="row.contractDateNo" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { contractDateNo: v })" />
                <span v-else>{{ row.contractDateNo || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.contractTerms" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { contractTerms: v })" />
                <span v-else class="text-left">{{ row.contractTerms || '—' }}</span>
              </td>

              <td>
                <el-input v-if="!isReadonly" :model-value="row.receiptProductName" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { receiptProductName: v })" />
                <span v-else>{{ row.receiptProductName || '—' }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.receiptAmount" size="small" :controls="false"
                  class="compact-num wide"
                  @change="(v: number | undefined) => chk.updateSample(row.id, { receiptAmount: v ?? 0 })" />
                <span v-else class="auto">{{ fmt(row.receiptAmount) }}</span>
              </td>

              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.logisticsQty" size="small" :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => chk.updateSample(row.id, { logisticsQty: v ?? 0 })" />
                <span v-else class="auto">{{ row.logisticsQty || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.logisticsDateNo" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { logisticsDateNo: v })" />
                <span v-else>{{ row.logisticsDateNo || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.logisticsProductName" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { logisticsProductName: v })" />
                <span v-else>{{ row.logisticsProductName || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.logisticsProvider" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { logisticsProvider: v })" />
                <span v-else>{{ row.logisticsProvider || '—' }}</span>
              </td>

              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.allocQty" size="small" :controls="false"
                  class="compact-num"
                  @change="(v: number | undefined) => chk.updateSample(row.id, { allocQty: v ?? 0 })" />
                <span v-else class="auto">{{ row.allocQty || '—' }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.allocMonth" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { allocMonth: v })" />
                <span v-else>{{ row.allocMonth || '—' }}</span>
              </td>
              <td>
                <el-input-number v-if="!isReadonly" :model-value="row.allocAmount" size="small" :controls="false"
                  class="compact-num wide"
                  @change="(v: number | undefined) => chk.updateSample(row.id, { allocAmount: v ?? 0 })" />
                <span v-else class="auto">{{ fmt(row.allocAmount) }}</span>
              </td>
              <td>
                <el-input v-if="!isReadonly" :model-value="row.allocBasis" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { allocBasis: v })" />
                <span v-else class="text-left">{{ row.allocBasis || '—' }}</span>
              </td>

              <td>
                <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { indexRef: v })" />
                <span v-else>{{ row.indexRef || '—' }}</span>
              </td>
              <td class="col-flag">
                <el-select v-if="!isReadonly" :model-value="row.isAbnormal || undefined" size="small" clearable
                  @update:model-value="(v: string) => chk.updateSample(row.id, { isAbnormal: (v as '是'|'否'|'') || '' })">
                  <el-option label="是" value="是" /><el-option label="否" value="否" />
                </el-select>
                <span v-else :class="{ 'abn-yes': row.isAbnormal === '是' }">{{ row.isAbnormal || '—' }}</span>
              </td>
              <td class="col-issue">
                <el-input v-if="!isReadonly" :model-value="row.issueDesc" size="small"
                  @update:model-value="(v: string) => chk.updateSample(row.id, { issueDesc: v })" />
                <span v-else class="text-left">{{ row.issueDesc || '—' }}</span>
              </td>
              <td class="col-act">
                <el-button link type="primary" size="small" @click="openCheckDialog(row)">核对</el-button>
                <el-button v-if="!isReadonly" link type="danger" size="small" @click="chk.removeSample(row.id)">删</el-button>
              </td>
            </tr>

            <tr class="row-total">
              <td colspan="2" class="sticky col-project">合计（测试金额）</td>
              <td colspan="4" />
              <td class="auto calc">{{ fmt(chk.stats.value.testedAmount) }}</td>
              <td colspan="14" />
              <td class="auto calc abn-yes">{{ fmt(chk.stats.value.incorrectAmount) }}</td>
              <td />
            </tr>
          </tbody>
        </table>
      </div>
    </div>

    <div class="section-block">
      <div class="section-label">四、统计说明</div>
      <table class="stat-table">
        <thead>
          <tr>
            <th>测试金额</th>
            <th>不正确金额</th>
            <th>差错率</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td class="auto calc">{{ fmt(chk.stats.value.testedAmount) }}</td>
            <td class="auto calc abn-yes">{{ fmt(chk.stats.value.incorrectAmount) }}</td>
            <td class="auto calc">{{ fmtPct(chk.stats.value.errorRate) }}</td>
          </tr>
        </tbody>
      </table>
      <el-input
        class="stat-note"
        :model-value="chk.sheet.value.statNote"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 5 }"
        placeholder="补充统计说明、扩大样本理由等…"
        :disabled="isReadonly"
        @update:model-value="(v: string) => chk.setStatNote(v)"
      />
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、审计说明</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('contract-check-note')">AI 填写审计说明</el-button>
        </div>
      </template>
      <el-input v-model="chk.auditNote.value" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="说明抽样检查结果、证据勾稽情况及异常处理…" :disabled="isReadonly" />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">六、审计结论</span>
          <el-button size="small" type="primary" plain
            :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
            @click="runAi('contract-check-conclusion')">AI 生成结论</el-button>
        </div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="A、未见异常。B、除上述应调整事项外，其余未见异常。C、不可确认。"
        :disabled="isReadonly" @update:model-value="saveAuditConclusion" />
    </el-card>

    <F2ContractCostCheckDialog
      v-model="checkDialogVisible"
      :row="checkDialogRow"
      :wp-id="wpId"
      :readonly="isReadonly"
      @save="saveCheckedSample"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { useF2ContractCostCheck } from '../../composables/useF2ContractCostCheck'
import {
  useF2SpecialAiGenerate,
  type F2SpeAiSection,
} from '../../composables/useF2SpecialAiGenerate'
import {
  F2_56_OBJECTIVES,
  F2_56_TEST_CHECKS,
  F2_56_TIPS,
  isBlankContractCostCheckSample,
  type ContractCostCheckSample,
} from '../../composables/useF2ContractCostCheckFormulas'
import type { ChecklistResponse } from '../../composables/useF2SpecialFormData'
import type { SampledVoucher, FillMode } from '../../composables/useSamplingAlgorithms'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import F2SheetToolbar from '../../f2/shared/F2SheetToolbar.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import F2ContractCostTestExampleRef from './F2ContractCostTestExampleRef.vue'
import F2ContractCostCheckDialog from './F2ContractCostCheckDialog.vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const props = defineProps<{
  wpId?: string
  projectId?: string
  auditYear?: number
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const chk = useF2ContractCostCheck({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectives = F2_56_OBJECTIVES
const testChecks = F2_56_TEST_CHECKS
const tips = F2_56_TIPS
const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const {
  aiAvailable,
  loading: aiLoading,
  generateAndConfirm,
} = useF2SpecialAiGenerate(wpIdRef)
const filledCount = computed(() =>
  chk.sheet.value.samples.filter((row) => !isBlankContractCostCheckSample(row)).length,
)
const checkDialogVisible = ref(false)
const checkDialogRow = ref<ContractCostCheckSample | null>(null)

const CONCLUSION_KEY = 'F2-56-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
}

function openCheckDialog(row: ContractCostCheckSample): void {
  checkDialogRow.value = row
  checkDialogVisible.value = true
}

function addAndOpenSample(): void {
  const reusable = chk.sheet.value.samples.find(isBlankContractCostCheckSample)
  if (reusable) {
    openCheckDialog(reusable)
    return
  }
  chk.addSample()
  const row = chk.sheet.value.samples[chk.sheet.value.samples.length - 1]
  if (row) openCheckDialog(row)
}

function saveCheckedSample(row: ContractCostCheckSample): void {
  chk.updateSample(row.id, row)
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F2-56',
    populationDescription: chk.params.value.populationDesc,
    samplingMethod: chk.params.value.method,
    samplingProcess: chk.params.value.process,
    populationAmount: chk.params.value.populationAmount,
    materiality: chk.params.value.materiality,
    tolerableMisstatement: chk.params.value.tolerableMisstatement,
    sampleCount: filledCount.value,
    testedAmount: chk.stats.value.testedAmount,
    incorrectAmount: chk.stats.value.incorrectAmount,
    errorRate: chk.stats.value.errorRate,
    coverageRatio: chk.coverageRatio.value,
    abnormalCount: chk.issueCount.value,
    samples: chk.enrichedSamples.value
      .filter((row) => !isBlankContractCostCheckSample(row))
      .slice(0, 30)
      .map((row) => ({
        projectName: row.projectName,
        voucherNo: row.voucherNo,
        voucherAmount: row.voucherAmount,
        contractDateNo: row.contractDateNo,
        receiptAmount: row.receiptAmount,
        logisticsDateNo: row.logisticsDateNo,
        allocationAmount: row.allocAmount,
        isAbnormal: row.isAbnormal,
        issueDescription: row.issueDesc,
      })),
  }
}

async function runAi(section: F2SpeAiSection): Promise<void> {
  const isNote = section === 'contract-check-note'
  const existing = isNote ? chk.auditNote.value : auditConclusion.value
  const title = isNote
    ? 'AI 生成 · 合同履约成本检查说明'
    : 'AI 生成 · 合同履约成本检查结论'
  const text = await generateAndConfirm(section, existing || '', aiContext(), title)
  if (!text) return
  if (isNote) chk.auditNote.value = text
  else saveAuditConclusion(text)
}
onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const auditYear = computed(() => props.auditYear ?? new Date().getFullYear() - 1)

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'F2',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => {
    const item = { item_id: itemId, conclusion: null, remark }
    props.allResponses.set(itemId, item as never)
    window.dispatchEvent(new CustomEvent('f2-spe:save-items', { detail: { items: [item] } }))
  },
  isReadonly: computed(() => props.isReadonly),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode: FillMode }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  chk.fillFromSampling(payload.samples, payload.fillMode)
}

function fmt(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number): string {
  if (!Number.isFinite(v) || v === 0) return '—'
  return `${(v * 100).toFixed(2)}%`
}
</script>

<style scoped src="../../f2/valuation/f2ValSheetStyles.css"></style>
<style scoped src="./f2SoftMatrixStyles.css"></style>
<style scoped>
.f2-contract-check { --gt-purple: #4b2d77; --gt-purple-soft: #f3eef8; }
.section-block { margin-bottom: 14px; }
.section-label {
  font-size: 13px;
  font-weight: 600;
  color: var(--gt-purple);
  margin-bottom: 8px;
  padding-left: 8px;
  border-left: 3px solid var(--gt-purple);
}
.objective-list { margin: 0; padding-left: 1.4em; font-size: 13px; line-height: 1.7; color: #303133; }
.params-grid { display: flex; flex-wrap: wrap; gap: 10px 14px; }
.params-grid label { display: flex; flex-direction: column; gap: 4px; font-size: 12px; color: #606266; }
.params-grid label.wide { min-width: 160px; }
.params-grid label.full { flex: 1 1 100%; }
.sampling-collapse { margin-bottom: 10px; }
.warn { color: #e6a23c; font-weight: 600; }
.stat-text { font-size: 12px; color: #606266; }

.test-checks {
  margin-bottom: 8px;
  padding: 8px 10px;
  background: #fef0f0;
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.8;
}
.test-checks-title { color: #c45656; font-weight: 600; margin-right: 6px; }
.test-check-item { color: #c45656; margin-right: 10px; }

.table-scroll { overflow-x: auto; margin-bottom: 12px; }
.matrix-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 10px;
  min-width: 2800px;
}
.matrix-table th,
.matrix-table td {
  border: 1px solid #d4c8e0;
  padding: 2px 2px;
  text-align: center;
  vertical-align: middle;
  background: #fff;
}
.matrix-table thead th {
  background: var(--gt-purple-soft);
  color: #3d2a55;
  font-weight: 600;
  position: sticky;
  top: 0;
  z-index: 2;
}
.matrix-table th.sub { font-weight: 500; font-size: 9px; white-space: nowrap; }
.grp-voucher { background: #f8f6fa !important; }
.grp-contract { background: #eef5fc !important; }
.grp-receipt { background: #fdf6ec !important; }
.grp-logistics { background: #f0f9eb !important; }
.grp-alloc { background: #fef0f0 !important; }

.sticky { position: sticky; z-index: 3; background: #faf8fc !important; }
.matrix-table thead th.sticky { background: var(--gt-purple) !important; color: #fff; z-index: 4; }
.col-project { left: 0; min-width: 88px; text-align: left !important; padding-left: 4px !important; }
.col-account {
  left: 88px;
  min-width: 96px;
  box-shadow: 2px 0 4px rgba(75, 45, 119, 0.08);
  text-align: left !important;
  padding-left: 4px !important;
}
.col-idx { min-width: 56px; }
.col-flag { min-width: 52px; }
.col-issue { min-width: 80px; }
.col-act { min-width: 76px; position: sticky; right: 0; z-index: 3; background: #fff !important; white-space: nowrap; }

.row-total td { background: #f0ebf5 !important; font-weight: 600; }
.row-warn td { background: #fdf6ec !important; }
.auto { text-align: right; padding-right: 2px; white-space: nowrap; color: #606266; }
span.auto { display: block; }
.calc { color: #4b2d77; font-weight: 500; }
.text-left { display: block; text-align: left; padding-left: 2px; font-size: 10px; }
.abn-yes { color: #c45656; font-weight: 600; }

.stat-table {
  width: 360px;
  border-collapse: collapse;
  font-size: 12px;
  margin-bottom: 8px;
}
.stat-table th,
.stat-table td {
  border: 1px solid #d4c8e0;
  padding: 6px 10px;
  text-align: center;
}
.stat-table th { background: var(--gt-purple-soft); color: #3d2a55; }
.stat-note { margin-top: 4px; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }

:deep(.compact-num) { width: 62px; }
:deep(.compact-num.wide) { width: 80px; }
:deep(.compact-num .el-input__inner) { text-align: right; padding: 0 2px; font-size: 10px; }
</style>
