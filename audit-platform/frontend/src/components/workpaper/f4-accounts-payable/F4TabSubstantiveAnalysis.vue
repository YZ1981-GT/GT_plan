<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * F4TabSubstantiveAnalysis — F4-4 应付账款实质性分析
 * 源表结构：付款期分析 + 期末前十名债权人动态分析 + 分区审计说明 + 审计结论。
 */
import { inject, toRef, type Ref } from 'vue'
import {
  useF4SubstantiveAnalysis,
  type F4TurnoverInputKey,
  type F4TurnoverRowKey,
} from '../composables/useF4SubstantiveAnalysis'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import GtIndexChip from '../GtIndexChip.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  turnoverRows,
  topCreditors,
  creditorSubtotal,
  summary,
  turnoverNote,
  creditorNote,
  auditConclusion,
  updateTurnoverInput,
  updateTurnoverRemark,
  updateCreditorReason,
  saveTurnoverNote,
  saveCreditorNote,
  saveConclusion,
} = useF4SubstantiveAnalysis({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

function fmtAmount(value: number | null): string {
  if (value == null) return '—'
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function fmtRate(value: number | 'N/A'): string {
  if (value === 'N/A') return 'N/A'
  return `${value.toFixed(2)}%`
}

function fmtTurnoverMetric(
  rowKey: F4TurnoverRowKey,
  value: number | null,
): string {
  if (value == null) return '无法计算'
  if (rowKey === 'turnoverRate' || rowKey === 'industryTurnover' || rowKey === 'industryDifference') {
    return value.toFixed(4)
  }
  if (rowKey === 'paymentDays') return `${value.toFixed(2)} 天`
  return fmtAmount(value)
}

function turnoverAiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-4',
    section: 'payable-turnover',
    rows: turnoverRows.value.map((row) => ({
      item: row.item,
      current: row.currentAmount,
      prior: row.priorAmount,
      remark: row.remark,
      formula: row.formula,
    })),
  }
}

function creditorAiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-4',
    section: 'top-creditors',
    creditorCount: summary.value.creditorCount,
    highChangeCount: summary.value.highChangeCount,
    subtotal: creditorSubtotal.value,
    creditors: topCreditors.value.map((row) => ({
      creditor: row.creditor,
      currentBalance: row.currentBalance,
      priorBalance: row.priorBalance,
      changeAmount: row.changeAmount,
      changeRate: row.changeRate,
      reason: row.reason,
    })),
  }
}

async function generateTurnoverNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'substantive-turnover-note',
    turnoverNote.value,
    turnoverAiContext(),
    'AI 生成 · 应付账款付款期分析说明',
  )
  if (generated) saveTurnoverNote(generated)
}

async function generateCreditorNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'substantive-creditor-note',
    creditorNote.value,
    creditorAiContext(),
    'AI 生成 · 前十名债权人分析说明',
  )
  if (generated) saveCreditorNote(generated)
}

async function generateConclusion(): Promise<void> {
  const generated = await generateAndConfirm(
    'substantive-conclusion',
    auditConclusion.value,
    {
      ...turnoverAiContext(),
      ...creditorAiContext(),
      turnoverNote: turnoverNote.value,
      creditorNote: creditorNote.value,
    },
    'AI 生成 · F4-4审计结论',
  )
  if (generated) saveConclusion(generated)
}
</script>

<template>
  <div class="f4-tab-substantive">
    <details class="guidance-details">
      <summary>📋 编制思路与取数逻辑</summary>
      <div class="guidance-content">
        <p>1. 付款期分析：以“主营业务成本＋存货期末－存货期初”估算本期采购额，再除以平均应付账款，评价供应商付款周期及其同比、行业差异。</p>
        <p>2. 本期期初、期末应付账款自动取自F4-1期初/期末审定数；上期期末等于本期期初。上期期初、成本、存货和行业数据据实录入。</p>
        <p>3. 前十名债权人不是固定占位行：系统从F4-2按实际债权人名称归集，按期末审定数绝对值降序动态展示，实际有几名就显示几名（最多10名）。</p>
        <p>4. 前十名的期末余额取F4-2期末审定数，期初余额取F4-2期初审定余额；发生原因默认带入款项性质，可结合合同、采购及结算情况补充。</p>
        <p>5. 变动比例绝对值超过20%的债权人橙色提示；上期余额为0时显示“N/A”，不得以除零结果判断异常。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：通过付款周期趋势、同行业比较及期末前十名债权人变动分析，识别应付账款异常波动、集中度变化、长期占款和未记录负债风险。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <span class="section-label">一、应付账款周转率（支付期）分析</span>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-1" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-turnover')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F4-4"
      label="分析程序附件"
    />

    <el-table :data="turnoverRows" border size="small" class="analysis-table">
      <el-table-column prop="item" label="项目" min-width="230">
        <template #default="{ row }">
          <el-tooltip v-if="row.formula" :content="row.formula" placement="top">
            <span class="formula-label">{{ row.item }}</span>
          </el-tooltip>
          <span v-else>{{ row.item }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期金额" min-width="155" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="row.currentInput && !isReadonly"
            :model-value="row.currentAmount"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateTurnoverInput(row.currentInput as F4TurnoverInputKey, value ?? 0)"
          />
          <el-tooltip
            v-else-if="row.rowKey === 'openingPayable' || row.rowKey === 'closingPayable'"
            content="自动联动F4-1审定表"
          >
            <span class="linked-value">🔗 {{ fmtTurnoverMetric(row.rowKey, row.currentAmount) }}</span>
          </el-tooltip>
          <span v-else class="formula-value">{{ fmtTurnoverMetric(row.rowKey, row.currentAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="上期金额" min-width="155" align="right">
        <template #default="{ row }">
          <WpAmountInput
            v-if="row.priorInput && !isReadonly"
            :model-value="row.priorAmount"
            size="small"
            style="width:100%"
            @change="(value: number | undefined) => updateTurnoverInput(row.priorInput as F4TurnoverInputKey, value ?? 0)"
          />
          <el-tooltip
            v-else-if="row.rowKey === 'closingPayable'"
            content="上期期末余额等于本期期初审定余额"
          >
            <span class="linked-value">🔗 {{ fmtTurnoverMetric(row.rowKey, row.priorAmount) }}</span>
          </el-tooltip>
          <span v-else class="formula-value">{{ fmtTurnoverMetric(row.rowKey, row.priorAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="250">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.remark"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            placeholder="数据来源、口径或异常说明"
            @change="(value: string) => updateTurnoverRemark(row.rowKey, value)"
          />
          <span v-else>{{ row.remark }}</span>
        </template>
      </el-table-column>
    </el-table>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">付款期分析审计说明</div>
            <div class="card-hint">说明采购成本口径、周转率及支付天数同比变化、行业差异和可能原因。</div>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateTurnoverNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-turnover-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="turnoverNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="结合本期与上期周转率、平均支付天数和同行业差异，分析付款政策、采购规模、结算节奏变化及异常原因。"
        @change="saveTurnoverNote"
      />
    </el-card>

    <div class="section-toolbar second-section">
      <div class="toolbar-left">
        <span class="section-label">二、期末应付账款前十名（审定数）分析</span>
        <el-tag size="small" type="info">自动取F4-2 · 实际 {{ topCreditors.length }} 名</el-tag>
        <el-tag v-if="summary.highChangeCount" size="small" type="warning">
          大幅变动 {{ summary.highChangeCount }} 名
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-creditors')">复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="topCreditors.length === 0"
      type="warning"
      :closable="false"
      class="empty-alert"
      title="F4-2尚无有效债权人明细。请先据实填写F4-2，本表将自动生成实际债权人名称，不使用“债权人1/2/3”占位行。"
    />

    <el-table
      v-else
      :data="topCreditors"
      border
      size="small"
      class="analysis-table"
      :row-class-name="({ row }: any) => row.isHighChange ? 'high-change-row' : ''"
    >
      <el-table-column type="index" label="排名" width="65" align="center" />
      <el-table-column prop="creditor" label="债权人名称" min-width="180" fixed="left">
        <template #default="{ row }">
          <span class="linked-creditor">🔗 {{ row.creditor }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="145" align="right">
        <template #default="{ row }"><span class="linked-value">{{ fmtAmount(row.currentBalance) }}</span></template>
      </el-table-column>
      <el-table-column label="上年年末余额" width="145" align="right">
        <template #default="{ row }">{{ fmtAmount(row.priorBalance) }}</template>
      </el-table-column>
      <el-table-column label="变动金额" width="135" align="right">
        <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.changeAmount) }}</span></template>
      </el-table-column>
      <el-table-column label="变动比例" width="115" align="right">
        <template #default="{ row }">
          <span class="formula-value" :class="{ 'high-rate': row.isHighChange }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="发生原因（款项性质）" min-width="260">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reason"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            :placeholder="row.sourcePaymentNature ? `默认款项性质：${row.sourcePaymentNature}` : '据实填写发生原因或款项性质'"
            @change="(value: string) => updateCreditorReason(row.rowId, value)"
          />
          <span v-else>{{ row.reason }}</span>
        </template>
      </el-table-column>
    </el-table>

    <div v-if="topCreditors.length" class="subtotal-bar">
      <span>小计</span>
      <span>期末 {{ fmtAmount(creditorSubtotal.currentBalance) }}</span>
      <span>上年末 {{ fmtAmount(creditorSubtotal.priorBalance) }}</span>
      <span>变动 {{ fmtAmount(creditorSubtotal.changeAmount) }}</span>
      <span>比例 {{ fmtRate(creditorSubtotal.changeRate) }}</span>
    </div>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">前十名债权人分析审计说明</div>
            <div class="card-hint">说明集中度、重大增减、关联方或异常债权人及进一步核查事项。</div>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable || !topCreditors.length"
              :loading="aiLoading"
              @click="generateCreditorNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-4-creditor-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="creditorNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="分析前十名债权人的余额集中度、重大增减及发生原因，说明需结合合同、采购、付款、函证或期后事项进一步核查的项目。"
        @change="saveCreditorNote"
      />
    </el-card>

    <el-card shadow="never" class="text-card conclusion-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">三、审计结论</div>
            <div class="card-hint">综合付款期趋势、行业比较与前十名债权人变动形成结论。</div>
          </div>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="评价应付账款周转与支付周期、前十名集中度及重大余额变动是否合理，是否存在需进一步核查或调整事项。"
        @change="saveConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-substantive { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.audit-objective, .empty-alert { margin-bottom: 10px; }
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin: 12px 0 8px;
}
.second-section { margin-top: 22px; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.section-label { color: #303133; font-size: 14px; font-weight: 600; }
.analysis-table { width: 100%; }
.analysis-table :deep(.el-input-number) { width: 100%; }
.formula-label, .formula-value { border-bottom: 1px dashed #b7bcc5; cursor: help; }
.formula-value { color: #315a8a; font-weight: 600; }
.linked-value, .linked-creditor { color: #7b4ba3; font-weight: 600; }
.high-rate { color: #d97706; }
:deep(.high-change-row td) { background: #fdf6ec !important; }
.subtotal-bar {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px 28px;
  padding: 9px 12px;
  border: 1px solid #dcdfe6;
  border-top: none;
  background: #f3f5f8;
  font-weight: 700;
}
.text-card { margin-top: 14px; border-radius: 8px; }
.text-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.conclusion-card { margin-top: 18px; }
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
}
.card-title { color: #303133; font-weight: 600; }
.card-hint { margin-top: 3px; color: #909399; font-size: 12px; }
.card-actions { display: flex; gap: 6px; }
</style>
