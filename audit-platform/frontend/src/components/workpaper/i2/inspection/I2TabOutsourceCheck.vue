<template>
  <div class="i2-outsource-check">
    <div class="section-header">
      <span class="section-title">I2-11 委外研发检查表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title>一、审计目标</template>
      <ol class="obj-list">
        <li>确认利润表中记录的委外研发费用已发生，与被审计单位有关，且已记录于恰当的账户（发生、权利和义务、分类）。</li>
        <li>确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、列报）。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        <b>编制逻辑：</b>
        先勾选测试原因并界定总体 → 再按「合同/受托方 ↔ 记账凭证 ↔ 验收单」逐项核对 →
        检查比例＝样本记账金额合计 ÷ 本期委外发生额（总体为 0 时显示 N/A，避免 #DIV/0!）。
        重点关注受托方资质、知识产权归属、验收交付物及关联方委外。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2" :context-project-id="props.projectId" />
        <GtIndexChip value="wp:I2-7" :context-project-id="props.projectId" />
        <el-tag size="small" type="info">样本 {{ summary.sampleCount }} 项</el-tag>
        <el-tag v-if="summary.anomalyCount > 0" size="small" type="danger">异常 {{ summary.anomalyCount }}</el-tag>
        <el-tag v-if="summary.amountMismatchCount > 0" size="small" type="warning">金额不符 {{ summary.amountMismatchCount }}</el-tag>
        <el-tag v-if="summary.missingAcceptanceCount > 0" size="small" type="warning">缺验收 {{ summary.missingAcceptanceCount }}</el-tag>
        <el-tag size="small" :type="coverageTagType">检查比例 {{ coverageLabel }}</el-tag>
        <el-button
          v-if="summary.anomalyCount > 0 || summary.amountMismatchCount > 0"
          size="small"
          type="danger"
          plain
          :disabled="isReadonly"
          @click="handleAnomalyToI23"
        >
          异常→I2-3
        </el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-10')">← I2-10</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'I2-12')">I2-12 →</el-button>
      </div>
    </div>

    <el-alert
      v-if="superDeductionTip"
      type="info"
      :closable="false"
      show-icon
      class="check-alert"
      :title="superDeductionTip"
    />

    <el-alert
      v-if="coverageLow"
      type="warning"
      :closable="false"
      show-icon
      class="check-alert"
      title="检查比例偏低：请扩大样本量，或在四、审计说明中解释原因。"
    />
    <el-alert
      v-if="populationStale"
      type="error"
      :closable="false"
      show-icon
      class="check-alert"
      title="抽样总体已过期：I2-7 委外费已变化，请点击「从 I2-7 带入」刷新，或确认手工总体仍适用。"
    />

    <!-- 二、审计过程 / 样本选取 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>二、审计过程 — 样本选取标准与依据</span>
          <div class="title-actions">
            <el-button
              size="small"
              :disabled="isReadonly || !(linkedOutsourceTotal.amount > 0)"
              @click="syncPopulationFromI27"
            >
              从 {{ linkedOutsourceTotal.source || 'I2-7' }} 带入本期委外费
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSampling">
              抽凭引擎
            </el-button>
          </div>
        </div>
      </template>

      <div class="reason-row">
        <span class="reason-label">测试原因：</span>
        <el-checkbox-group
          v-model="sampleMeta.testReasons"
          :disabled="isReadonly"
          class="reason-group"
        >
          <el-checkbox v-for="r in I2_OUTSOURCE_TEST_REASONS" :key="r" :label="r" :value="r">{{ r }}</el-checkbox>
        </el-checkbox-group>
        <el-input
          v-if="sampleMeta.testReasons.includes('其他')"
          v-model="sampleMeta.testReasonOther"
          size="small"
          placeholder="其他原因说明"
          style="width:200px"
          :disabled="isReadonly"
        />
      </div>

      <div class="test-content-hint">
        <p>测试内容说明：</p>
        <ol>
          <li v-for="(item, i) in I2_OUTSOURCE_TEST_CONTENT" :key="i">{{ item }}</li>
        </ol>
        <p class="hint-note">【检查要素可根据实际情况自行增减】</p>
      </div>

      <el-descriptions :column="2" border size="small" class="sample-desc">
        <el-descriptions-item label="测试总体">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.populationDesc"
            size="small"
            placeholder="账面委外研发借方发生额总体"
          />
          <span v-else>{{ sampleMeta.populationDesc }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="本期发生额（总体）">
          <div class="pop-cell">
            <el-input-number
              v-if="!isReadonly"
              :model-value="sampleMeta.populationAmount"
              :controls="false"
              size="small"
              :precision="2"
              @change="(v: number | undefined) => setPopulationAmount(v ?? 0, true)"
            />
            <span v-else class="amt">{{ fmtNum(sampleMeta.populationAmount) }}</span>
            <el-tag v-if="linkedOutsourceTotal.source" size="small" type="info">
              源 {{ linkedOutsourceTotal.source }}: {{ fmtNum(linkedOutsourceTotal.amount) }}
            </el-tag>
            <el-tag v-if="sampleMeta.populationManual" size="small" type="warning">手工</el-tag>
            <el-tag v-if="populationStale" size="small" type="danger">I2-7已变·总体过期</el-tag>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="特定样本">
          <el-input
            v-if="!isReadonly"
            v-model="sampleMeta.specificSample"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
          />
          <span v-else>{{ sampleMeta.specificSample }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="抽样方法 / 过程">
          <div class="method-cell">
            <el-select
              v-if="!isReadonly"
              v-model="sampleMeta.sampleMethod"
              size="small"
              filterable
              allow-create
              style="width: 140px"
            >
              <el-option v-for="m in I2_OUTSOURCE_SAMPLE_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ sampleMeta.sampleMethod }}</span>
            <el-input
              v-if="!isReadonly"
              v-model="sampleMeta.sampleProcess"
              size="small"
              placeholder="如：按金额分层 / 关联方全覆盖…"
              style="flex:1"
            />
            <span v-else>{{ sampleMeta.sampleProcess || '—' }}</span>
          </div>
        </el-descriptions-item>
        <el-descriptions-item label="检查合计（样本）">
          <span class="amt">{{ fmtNum(summary.checkedTotal) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="检查比例 / 告警阈值">
          <span :class="{ 'warn-coverage': coverageLow }">{{ coverageLabel }}</span>
          <span class="sep">/</span>
          <el-input-number
            v-if="!isReadonly"
            v-model="sampleMeta.coverageThreshold"
            :min="1"
            :max="100"
            :controls="false"
            size="small"
            style="width:72px"
          />
          <span v-else>{{ sampleMeta.coverageThreshold }}%</span>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 三、测试表 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="block-title">
          <span>三、测试 — 合同 / 受托方 / 凭证 / 验收核对</span>
          <div class="title-actions">
            <el-segmented
              v-model="columnViewMode"
              :options="[
                { label: '精简', value: 'compact' },
                { label: '完整', value: 'full' },
              ]"
              size="small"
            />
            <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleAddRow">+ 新增行</el-button>
            <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="focus-tip"
        title="核对重点：合同与凭证金额是否一致；受托方资质与参保规模是否匹配；验收金额与记账金额是否勾稽；知识产权归属是否清晰。"
      />

      <el-table
        :data="rows"
        border
        size="small"
        class="check-table"
        max-height="520"
        :row-class-name="rowClassName"
        show-summary
        :summary-method="getSummary"
      >
        <el-table-column type="index" label="#" width="40" fixed align="center" />

        <el-table-column prop="projectName" label="研发项目" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectName" size="small" />
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="columnViewMode === 'full'" prop="outsourceReason" label="委外原因" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.outsourceReason" size="small" />
            <span v-else>{{ row.outsourceReason || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="委外合同" align="center" class-name="col-contract">
          <el-table-column v-if="columnViewMode === 'full'" prop="contractDate" label="日期" min-width="120">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.contractDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" />
              <span v-else>{{ row.contractDate || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="contractNo" label="合同号" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.contractNo" size="small" />
              <span v-else>{{ row.contractNo || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="entrustedParty" label="受托方" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.entrustedParty" size="small" placeholder="供应商" />
              <span v-else>{{ row.entrustedParty || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="rdContent" label="研发内容" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.rdContent" size="small" />
              <span v-else>{{ row.rdContent || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="ipOwnership" label="IP归属" min-width="100">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                v-model="row.ipOwnership"
                size="small"
                placeholder="委托方/共有…"
                @change="onRowChange(row)"
              />
              <span v-else>{{ row.ipOwnership || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="columnViewMode === 'full'" label="受托方信息" align="center" class-name="col-party">
          <el-table-column prop="qualification" label="资质" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.qualification" size="small" @change="onRowChange(row)" />
              <span v-else>{{ row.qualification || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="registeredCapital" label="注册资本" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.registeredCapital" size="small" />
              <span v-else>{{ row.registeredCapital || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="insuredCount" label="参保人数" min-width="90">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.insuredCount" size="small" />
              <span v-else>{{ row.insuredCount || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="记账凭证" align="center" class-name="col-voucher">
          <el-table-column v-if="columnViewMode === 'full'" prop="voucherDate" label="日期" min-width="120">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.voucherDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" />
              <span v-else>{{ row.voucherDate || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="voucherNo" label="编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="businessDesc" label="业务内容" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessDesc" size="small" />
              <span v-else>{{ row.businessDesc || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="amount" label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.amount"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                @change="onRowChange(row)"
              />
              <span v-else class="amt">{{ fmtNum(row.amount) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="验收单据" align="center" class-name="col-accept">
          <el-table-column prop="acceptanceDate" label="日期" min-width="120">
            <template #default="{ row }">
              <el-date-picker
                v-if="!isReadonly"
                v-model="row.acceptanceDate"
                type="date"
                size="small"
                value-format="YYYY-MM-DD"
                style="width:100%"
                @change="onRowChange(row)"
              />
              <span v-else>{{ row.acceptanceDate || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="acceptanceAmount" label="金额" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                v-model="row.acceptanceAmount"
                size="small"
                :controls="false"
                :precision="2"
                style="width:100%"
                :class="{ 'mismatch-input': hasAmountMismatch(row) }"
                @change="onRowChange(row)"
              />
              <span v-else :class="{ 'mismatch-text': hasAmountMismatch(row) }">{{ fmtNum(row.acceptanceAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="columnViewMode === 'full'" prop="acceptanceResult" label="交付物/结论" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.acceptanceResult" size="small" @change="onRowChange(row)" />
              <span v-else>{{ row.acceptanceResult || '—' }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column prop="isAbnormal" label="是否异常" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.isAbnormal"
              size="small"
              clearable
              filterable
              allow-create
              style="width:100%"
              :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }"
            >
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="金额不符" value="金额不符" />
              <el-option label="缺验收" value="缺验收" />
              <el-option label="资质未核" value="资质未核" />
              <el-option label="关联方未披露" value="关联方未披露" />
              <el-option label="IP归属不清" value="IP归属不清" />
              <el-option label="其他" value="其他" />
            </el-select>
            <span v-else :class="{ 'abnormal-cell': isAbnormalFlag(row.isAbnormal) }">{{ row.isAbnormal || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="indexRef" label="索引号" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" text @click="handleOcr($index)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column prop="conclusion" label="审核结论" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" placeholder="结论" style="width:100%">
              <el-option label="相符" value="相符" />
              <el-option label="不符" value="不符" />
              <el-option label="验收通过" value="验收通过" />
              <el-option label="验收不通过" value="验收不通过" />
              <el-option label="待查" value="待查" />
            </el-select>
            <span v-else>{{ row.conclusion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="summary-bar">
        <span>合计（样本）：<b>{{ fmtNum(summary.checkedTotal) }}</b></span>
        <span>本期发生额：<b>{{ fmtNum(summary.periodTotal) }}</b></span>
        <span :class="{ 'warn-coverage': coverageLow }">
          检查比例：<b>{{ coverageLabel }}</b>
        </span>
      </div>
    </el-card>

    <!-- 四、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="记录测试原因、样本选取、合同/资质/验收核对发现及处理；检查比例偏低时说明原因…"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="基于检查结果，对委外研发支出的发生、准确性与归集恰当性给出结论…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 开发支出(1717) 委外研发检查" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible && props.wpId && props.projectId"
        account-code="1717"
        phase="final"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="samplingYear"
        @filled="onSamplesFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, inject, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI2OutsourceCheck,
  I2_OUTSOURCE_TEST_CONTENT,
  I2_OUTSOURCE_TEST_REASONS,
  I2_OUTSOURCE_SAMPLE_METHODS,
  hasAmountMismatch,
  type I2OutsourceCheckRow,
} from '../../composables/useI2OutsourceCheck'
import {
  appendI23DraftAje,
  buildOutsourceSuperDeductionTip,
  pickOcrField,
  runWorkpaperOcr,
  writeSheetCompletionMarker,
} from '../../composables/i2EnhancementHelpers'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'),
)

const props = defineProps<{
  sheetName: string
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const columnViewMode = ref<'compact' | 'full'>('compact')
const samplingVisible = ref(false)
const samplingYear = computed(() => props.year || new Date().getFullYear())

const {
  rows,
  sampleMeta,
  auditNote,
  auditConclusion,
  summary,
  linkedOutsourceTotal,
  coverageLow,
  coverageLabel,
  coverageTagType,
  populationStale,
  addRow,
  removeRow,
  applySuggestAbnormal,
  syncPopulationFromI27,
  setPopulationAmount,
  persistAll,
  saveAuditNote,
  saveAuditConclusion,
} = useI2OutsourceCheck(toRef(props, 'allResponses'), { saveResponse: props.saveResponse })

const superDeductionTip = computed(() =>
  buildOutsourceSuperDeductionTip(Number(sampleMeta.value.populationAmount) || 0),
)

function onRowChange(row: I2OutsourceCheckRow) {
  applySuggestAbnormal(row)
}

function handleAddRow() {
  addRow()
}

async function handleSave() {
  await persistAll()
  const rate = summary.value.coverageRate
  const progress = rate == null
    ? (summary.value.sampleCount > 0 ? 40 : 10)
    : Math.max(10, Math.min(100, Math.round(rate)))
  await writeSheetCompletionMarker({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    sheetCode: 'I2-11',
    progress,
    ok: !coverageLow.value && summary.value.sampleCount > 0 && summary.value.anomalyCount === 0,
    detail: {
      sampleCount: summary.value.sampleCount,
      coverageRate: rate,
      amountMismatchCount: summary.value.amountMismatchCount,
    },
  })
  emit('save')
  ElMessage.success('委外研发检查表已保存')
}

function handleSampling() {
  if (!props.wpId || !props.projectId) {
    ElMessage.warning('缺少工作底稿或项目上下文，无法打开抽凭引擎')
    return
  }
  samplingVisible.value = true
}

function onSamplesFilled(payload: { samples?: any[] }) {
  const samples = payload?.samples ?? []
  let n = 0
  for (const s of samples) {
    const amount = Number(s?.debitAmount) || Number(s?.creditAmount) || Number(s?.amount) || 0
    addRow({
      entrustedParty: String(s?.counterpart ?? s?.counterparty ?? s?.counterpartAccount ?? ''),
      amount,
      voucherNo: String(s?.voucherNo ?? ''),
      voucherDate: String(s?.voucherDate ?? ''),
      businessDesc: String(s?.summary ?? ''),
      projectName: String(s?.projectName ?? s?.accountName ?? ''),
    })
    n++
  }
  samplingVisible.value = false
  ElMessage[n > 0 ? 'success' : 'info'](n > 0 ? `已回填 ${n} 笔抽样凭证` : '未回填新凭证')
}

async function handleOcr(idx: number) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.jpg,.jpeg,.png,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    try {
      const fields = await runWorkpaperOcr(props.wpId, file)
      const contractNo = pickOcrField(fields, 'contractNo', 'contract_no', 'number', 'docNo')
      const contractDate = pickOcrField(fields, 'contractDate', 'date', 'signDate')
      const party = pickOcrField(fields, 'counterparty', 'counterpart', 'party', 'supplier')
      const amount = pickOcrField(fields, 'amount', 'contractAmount', 'acceptanceAmount')
      const acceptanceDate = pickOcrField(fields, 'acceptanceDate', 'acceptDate')
      await ElMessageBox.confirm(
        `OCR 识别结果：\n合同号: ${contractNo || '-'}\n日期: ${contractDate || '-'}\n受托方: ${party || '-'}\n金额: ${amount || '-'}\n验收日: ${acceptanceDate || '-'}\n\n确认填入第 ${idx + 1} 行？`,
        'OCR 识别结果确认',
        { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
      )
      const row = rows.value[idx]
      if (!row) return
      if (contractNo) row.contractNo = contractNo
      if (contractDate) row.contractDate = contractDate
      if (party) row.entrustedParty = party
      if (amount) {
        const n = Number(String(amount).replace(/,/g, ''))
        if (Number.isFinite(n)) {
          if (!(row.amount > 0)) row.amount = n
          if (!(row.acceptanceAmount > 0)) row.acceptanceAmount = n
        }
      }
      if (acceptanceDate) row.acceptanceDate = acceptanceDate
      onRowChange(row)
      ElMessage.success('OCR 结果已填入合同/验收字段')
    } catch (e: any) {
      if (e !== 'cancel') ElMessage.error(e?.message || 'OCR 识别失败')
    }
  }
  input.click()
}

async function handleAnomalyToI23() {
  const mismatched = rows.value.filter((r) => hasAmountMismatch(r) || isAbnormalFlag(r.isAbnormal))
  if (!mismatched.length) {
    ElMessage.info('当前无金额不符/异常样本')
    return
  }
  const amount = mismatched.reduce((s, r) => s + Math.abs((Number(r.amount) || 0) - (Number(r.acceptanceAmount) || 0)), 0)
  await appendI23DraftAje({
    allResponses: props.allResponses,
    saveResponse: props.saveResponse,
    draft: {
      description: `I2-11 委外研发检查异常/金额不符 ${mismatched.length} 笔，差额合计 ${amount}`,
      debitAmount: amount > 0 ? amount : 0,
      indexRef: 'I2-11',
      remark: '来源:委外研发检查异常一键生成',
    },
  })
  ElMessage.success(`已向 I2-3 生成调整草稿（${mismatched.length} 笔）`)
  emit('navigate-sheet', 'I2-3')
}

function handleReview() {
  openReviewDialog('I2-11-委外研发检查')
}

function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否'
}

function rowClassName({ row }: { row: I2OutsourceCheckRow }) {
  return isAbnormalFlag(row.isAbnormal) ? 'abnormal-row' : ''
}

function fmtNum(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getSummary({ columns }: { columns: any[] }) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.property === 'amount') return fmtNum(summary.value.checkedTotal)
    if (col.property === 'acceptanceAmount') {
      const t = rows.value.reduce((s, r) => s + (Number(r.acceptanceAmount) || 0), 0)
      return fmtNum(t)
    }
    return ''
  })
}
</script>

<style scoped>
.i2-outsource-check { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.7; font-size: 12px; }
.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  margin-bottom: 12px; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.6;
}
.tab-toolbar { display: flex; justify-content: flex-end; margin-bottom: 10px; }
.toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.check-alert { margin-bottom: 12px; }
.block-card { margin-bottom: 14px; }
.block-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.block-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; font-weight: 600; }
.title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.reason-row { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-bottom: 10px; }
.reason-label { font-size: 12px; color: #374151; font-weight: 600; }
.reason-group { display: flex; flex-wrap: wrap; gap: 4px 12px; }
.test-content-hint { font-size: 12px; color: #4b5563; margin-bottom: 12px; line-height: 1.7; }
.test-content-hint ol { margin: 4px 0 0; padding-left: 18px; }
.hint-note { color: #2563eb; margin: 6px 0 0; }
.sample-desc { margin-top: 4px; }
.pop-cell, .method-cell { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.amt { font-variant-numeric: tabular-nums; }
.sep { margin: 0 6px; color: #9ca3af; }
.warn-coverage { color: #dc2626; font-weight: 600; }
.focus-tip { margin-bottom: 10px; }
.check-table { font-size: var(--wp-font-size, 13px); }
.check-table :deep(.col-contract .el-table__cell) { background-color: #f0faf0 !important; }
.check-table :deep(.col-party .el-table__cell) { background-color: #fff7ed !important; }
.check-table :deep(.col-voucher .el-table__cell) { background-color: #f0f5ff !important; }
.check-table :deep(.col-accept .el-table__cell) { background-color: #fdf4ff !important; }
.mismatch-text, .mismatch-input { color: #dc2626; }
.abnormal-cell { color: #dc2626; font-weight: 600; }
:deep(.abnormal-row) { background-color: #fef2f2 !important; }
.summary-bar {
  display: flex; gap: 24px; flex-wrap: wrap; margin-top: 10px; padding: 10px 12px;
  background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 6px; font-size: 12px;
}
.audit-note-card, .audit-conclusion-card { margin-top: 14px; }
</style>
