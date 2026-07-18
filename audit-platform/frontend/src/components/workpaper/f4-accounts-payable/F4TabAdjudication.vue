<script setup lang="ts">
/** F4TabAdjudication — F4-1 应付账款审定表（严格对齐源表双分类结构）。 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useF4Adjudication,
  type F4AdjudicationRow,
  type F4AdjudicationSection,
  type StoredF4AdjRow,
} from '../composables/useF4Adjudication'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import F4AdjudicationTable from './F4AdjudicationTable.vue'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)

const {
  natureDataRows,
  natureSubtotalRow,
  agingDataRows,
  agingSubtotalRow,
  detailAggregation,
  openingCrossCheckPassed,
  closingCrossCheckPassed,
  crossCheckPassed,
  trialBalance,
  openingVariance,
  closingVariance,
  significantChanges,
  updateCell,
  updateTrialBalance,
  auditNote,
  auditConclusion,
  publishAdjudicated,
} = useF4Adjudication({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const natureTableData = computed(() => [...natureDataRows.value, natureSubtotalRow.value])
const agingTableData = computed(() => [...agingDataRows.value, agingSubtotalRow.value])
const hasOpeningVariance = computed(() => Math.abs(openingVariance.value) >= 0.005)
const hasClosingVariance = computed(() => Math.abs(closingVariance.value) >= 0.005)
const totalChangeRate = computed(() => natureSubtotalRow.value.changeRate)

function amount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function rate(value: number): string {
  return `${(value * 100).toFixed(2)}%`
}

function handleUpdate(
  section: F4AdjudicationSection,
  rowKey: string,
  field: keyof StoredF4AdjRow,
  value: unknown,
): void {
  updateCell(section, rowKey, field, value)
}

function aiContext() {
  return {
    accountCode: '2202',
    natureRows: natureDataRows.value.map((row) => ({
      item: row.label,
      openingAudited: row.openingAdjusted,
      closingAudited: row.closingAdjusted,
      changeAmount: row.changeAmount,
      changeRate: rate(row.changeRate),
      reasonAnalysis: row.reasonAnalysis,
    })),
    agingRows: agingDataRows.value.map((row) => ({
      aging: row.label,
      openingAudited: row.openingAdjusted,
      closingAudited: row.closingAdjusted,
      changeAmount: row.changeAmount,
      changeRate: rate(row.changeRate),
      reasonAnalysis: row.reasonAnalysis,
    })),
    total: {
      openingAudited: natureSubtotalRow.value.openingAdjusted,
      closingAudited: natureSubtotalRow.value.closingAdjusted,
      changeAmount: natureSubtotalRow.value.changeAmount,
      changeRate: rate(natureSubtotalRow.value.changeRate),
    },
    reconciliation: {
      openingNatureVsAgingPassed: openingCrossCheckPassed.value,
      closingNatureVsAgingPassed: closingCrossCheckPassed.value,
      openingTrialBalance: trialBalance.value.opening,
      openingVariance: openingVariance.value,
      closingTrialBalance: trialBalance.value.closing,
      closingVariance: closingVariance.value,
    },
    significantChanges: significantChanges.value,
    closingDataSource: detailAggregation.value.hasData ? 'F4-2明细表自动汇总' : 'F4-1手工录入',
  }
}

async function generateReason(section: F4AdjudicationSection, row: F4AdjudicationRow): Promise<void> {
  const generated = await generateAndConfirm(
    'adjudication-reason',
    row.reasonAnalysis,
    {
      classification: section === 'nature' ? '按性质分类' : '按账龄分类',
      item: row.label,
      openingAudited: row.openingAdjusted,
      closingAudited: row.closingAdjusted,
      changeAmount: row.changeAmount,
      changeRate: rate(row.changeRate),
      totalChangeRate: rate(totalChangeRate.value),
    },
    `AI 生成 · ${row.label}变动原因`,
  )
  if (generated) updateCell(section, row.rowKey, 'reasonAnalysis', generated)
}

async function generateNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'adjudication-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-1审计说明',
  )
  if (generated) auditNote.value = generated
}

async function generateConclusion(): Promise<void> {
  const generated = await generateAndConfirm(
    'adjudication-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-1审计结论',
  )
  if (generated) auditConclusion.value = generated
}

function confirmAdjudication(): void {
  if (!crossCheckPassed.value || hasOpeningVariance.value || hasClosingVariance.value) {
    ElMessage.warning('存在分类口径差异或试算平衡表差异，请核对后再确认')
    return
  }
  publishAdjudicated()
  ElMessage.success('已确认审定并发布应付账款审定数')
}
</script>

<template>
  <div class="f4-tab-adjudication">
    <details class="guidance-details">
      <summary>📋 编制思路与公式逻辑</summary>
      <div class="guidance-content">
        <p>1. 本表不是发生额滚动表，而是期初与期末两个时点的余额审定桥接：审定数 = 未审数 + 账项调整 + 重分类调整。</p>
        <p>2. 同一应付账款余额分别按性质和账龄展示。两种分类口径的期初审定合计、期末审定合计必须分别一致。</p>
        <p>3. 期末数按原Excel公式逻辑从F4-2明细表自动汇总；未录入明细时允许在本表手工录入期末数据。</p>
        <p>4. 变动额 = 本期审定数 - 上期审定数；变动率 = 变动额 ÷ 上期审定数。变动率绝对值超过30%的项目必须说明主要原因。</p>
        <p>5. 按账龄的账项调整采用源表逻辑：审定账龄 - 未审账龄 - 重分类调整；无法合理分摊的余额归入“其他/未分类”。</p>
        <p>6. 期初、期末审定合计分别与试算平衡表2202科目核对，差异应为零。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：确认应付账款期初及期末余额完整、准确，调整和重分类恰当；性质及账龄分类一致；重大变动具有合理解释；审定数与试算平衡表一致。"
    />

    <div class="toolbar">
      <div>
        <el-button type="primary" size="small" :disabled="isReadonly" @click="confirmAdjudication">
          确认审定
        </el-button>
        <el-tag v-if="detailAggregation.hasData" type="success" size="small">期末已联动 F4-2</el-tag>
        <el-tag v-else type="warning" size="small">F4-2无有效明细，期末可手工录入</el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:F4-3" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-1-adjudication')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F4-1"
      label="审定表附件"
    />

    <el-alert v-if="!crossCheckPassed" type="error" :closable="false" class="warning-alert">
      分类口径不一致：
      <span v-if="!openingCrossCheckPassed">
        期初按性质 {{ amount(natureSubtotalRow.openingAdjusted) }}，按账龄 {{ amount(agingSubtotalRow.openingAdjusted) }}；
      </span>
      <span v-if="!closingCrossCheckPassed">
        期末按性质 {{ amount(natureSubtotalRow.closingAdjusted) }}，按账龄 {{ amount(agingSubtotalRow.closingAdjusted) }}。
      </span>
    </el-alert>

    <div class="section-heading">
      <h4>一、按照性质分类</h4>
      <F4ImportExportToolbar
        :wp-id="wpId"
        :project-id="projectId"
        sheet="F4-1-nature"
        :disabled="isReadonly"
        @imported="reloadWorkpaperData?.()"
      />
    </div>
    <F4AdjudicationTable
      section="nature"
      :rows="natureTableData"
      :readonly="isReadonly"
      :ai-available="aiAvailable"
      :ai-loading="aiLoading"
      @update="(rowKey, field, value) => handleUpdate('nature', rowKey, field, value)"
      @ai-reason="(row) => generateReason('nature', row)"
    />

    <div class="section-heading">
      <h4>二、按照账龄分类</h4>
      <F4ImportExportToolbar
        :wp-id="wpId"
        :project-id="projectId"
        sheet="F4-1-aging"
        :disabled="isReadonly"
        @imported="reloadWorkpaperData?.()"
      />
    </div>
    <F4AdjudicationTable
      section="aging"
      :rows="agingTableData"
      :readonly="isReadonly"
      :ai-available="aiAvailable"
      :ai-loading="aiLoading"
      @update="(rowKey, field, value) => handleUpdate('aging', rowKey, field, value)"
      @ai-reason="(row) => generateReason('aging', row)"
    />

    <section class="reconciliation">
      <h4>试算平衡表核对</h4>
      <div class="reconcile-grid">
        <div class="reconcile-label">项目</div>
        <div class="reconcile-label">期初数</div>
        <div class="reconcile-label">期末数</div>

        <div>审定表合计</div>
        <div class="number">{{ amount(natureSubtotalRow.openingAdjusted) }}</div>
        <div class="number">{{ amount(natureSubtotalRow.closingAdjusted) }}</div>

        <div>试算平衡表数（2202）</div>
        <el-input-number
          :model-value="trialBalance.opening"
          :controls="false"
          size="small"
          :disabled="isReadonly"
          @change="(value: number | undefined) => updateTrialBalance('opening', value ?? 0)"
        />
        <el-input-number
          :model-value="trialBalance.closing"
          :controls="false"
          size="small"
          :disabled="isReadonly"
          @change="(value: number | undefined) => updateTrialBalance('closing', value ?? 0)"
        />

        <div>差异数</div>
        <div class="number" :class="{ danger: hasOpeningVariance }">{{ amount(openingVariance) }}</div>
        <div class="number" :class="{ danger: hasClosingVariance }">{{ amount(closingVariance) }}</div>
      </div>
    </section>

    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <div>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-1-note')">💬</el-button>
          </div>
        </div>
      </template>
      <div class="change-summary">
        应付账款期末审定余额较期初
        <strong>{{ natureSubtotalRow.changeAmount >= 0 ? '增加' : '减少' }}</strong>
        {{ amount(Math.abs(natureSubtotalRow.changeAmount)) }}，变动率 {{ rate(totalChangeRate) }}。
        <span v-if="significantChanges.length">
          超过30%的项目：{{ significantChanges.map((item) => item.label).join('、') }}。
        </span>
      </div>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明余额总体变动、超过30%的主要项目及原因、长期账龄构成、分类与试算表勾稽结果。"
      />
    </el-card>

    <el-card shadow="never" class="opinion-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <div>
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateConclusion"
            >🤖 AI生成结论</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-1-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="评价应付账款余额、分类、调整重分类及列报是否恰当。"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #315a8a;
  border-radius: 4px;
  background: #eef4fa;
}
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .warning-alert { margin-bottom: 10px; }
.toolbar, .toolbar > div, .toolbar-right, .card-header {
  display: flex;
  align-items: center;
}
.toolbar, .card-header { justify-content: space-between; }
.toolbar { margin: 10px 0; }
.toolbar > div, .toolbar-right { gap: 7px; }
h4 { margin: 16px 0 8px; color: #303133; }
.section-heading { display: flex; align-items: center; justify-content: space-between; }
.reconciliation { max-width: 760px; margin-top: 16px; }
.reconcile-grid {
  display: grid;
  grid-template-columns: 1.4fr 1fr 1fr;
  border-top: 1px solid #dcdfe6;
  border-left: 1px solid #dcdfe6;
}
.reconcile-grid > * {
  min-height: 38px;
  padding: 7px 10px;
  border-right: 1px solid #dcdfe6;
  border-bottom: 1px solid #dcdfe6;
}
.reconcile-label { background: #f3f5f8; font-weight: 600; text-align: center; }
.number { text-align: right; }
.danger { color: #d03050; font-weight: 700; background: #fff1f1; }
.opinion-card { margin-top: 16px; }
.card-header { font-weight: 600; }
.change-summary {
  margin-bottom: 10px;
  padding: 9px 12px;
  border-radius: 4px;
  background: #f6f8fa;
  color: #606266;
}
</style>
