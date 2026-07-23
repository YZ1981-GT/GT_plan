<template>
  <div class="f5-major-adj">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><b>编制思路：</b>本表是销售成本审定表（F5-1）的附表，用于审查主营业务成本账户中重大调整事项的理由是否充分。</p>
        <p>1. 逐笔登记调整日期、凭证号、事项内容、借贷方金额与调整理由，评价「理由是否充分」。</p>
        <p>2. 检查现金返利、实物返利是否冲减或调整存货，或冲减购货当期的主营业务成本。</p>
        <p>3. 可与 F5-4 调整分录、F5-7 倒轧中的调整相互印证；可用抽凭引擎按 6401 抽取样本填入。</p>
        <p>4. 金额超重要性水平、或理由为「不充分/待补充/空白」的行自动标黄。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实营业成本的发生、完整、准确、截止与列报；重点核查重大调整事项的真实性、理由充分性及对列报的影响。"
    />

    <el-alert
      v-if="adj.inadequateCount.value > 0"
      type="warning"
      :closable="false"
      class="change-alert"
      :title="`有 ${adj.inadequateCount.value} 笔调整理由不充分或待补充，请补齐评价后再出结论`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="toolbar-hint">科目 6401 · 重大调整核查</span>
        <GtVoucherSamplingEngine
          :project-id="projectId"
          :workpaper-id="wpId"
          account-code="6401"
          phase="final"
          :year="year ?? new Date().getFullYear()"
          @filled="handleSamplingFilled"
        />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="adj.addRow">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          v-if="ieCtx"
          :wp-id="wpId"
          :api-prefix="ieCtx.apiPrefix"
          :sheet="ieCtx.sheet"
          :disabled="isReadonly"
          @imported="$emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F5-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">有效 {{ adj.filledCount.value }} / {{ adj.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-8"
      label="重大调整附件"
    />

    <el-table
      :data="adj.rows.value"
      size="small"
      border
      stripe
      :row-class-name="rowClass"
      max-height="520"
    >
      <el-table-column label="日期" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.date"
            size="small"
            placeholder="YYYY-MM-DD"
            @change="(v: string) => adj.updateCell(row.id, 'date', v)"
          />
          <span v-else>{{ row.date }}</span>
        </template>
      </el-table-column>

      <el-table-column label="凭证号" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherNo"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'voucherNo', v)"
          />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>

      <el-table-column label="重大调整事项内容" min-width="180">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.itemContent"
            size="small"
            @change="(v: string) => adj.updateCell(row.id, 'itemContent', v)"
          />
          <span v-else>{{ row.itemContent }}</span>
        </template>
      </el-table-column>

      <el-table-column label="调整金额" align="center">
        <el-table-column label="借方" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.debitAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.id, 'debitAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.creditAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => adj.updateCell(row.id, 'creditAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="调整理由" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.adjustmentReason"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            @change="(v: string) => adj.updateCell(row.id, 'adjustmentReason', v)"
          />
          <span v-else>{{ row.adjustmentReason }}</span>
        </template>
      </el-table-column>

      <el-table-column label="理由是否充分" width="130">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            :model-value="row.reasonAdequate || undefined"
            size="small"
            clearable
            placeholder="请选择"
            style="width:100%"
            @change="(v: string) => adj.updateCell(row.id, 'reasonAdequate', v ?? '')"
          >
            <el-option v-for="o in adequacyOptions" :key="o" :label="o" :value="o" />
          </el-select>
          <span v-else :class="{ 'is-warn': isInadequate(row.reasonAdequate) }">
            {{ row.reasonAdequate || '—' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="64" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="adj.removeRow(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <div class="f5-ma-summary">
      <span>有效笔数：<b>{{ adj.filledCount.value }}</b></span>
      <span>借方合计：<b>{{ fmt(adj.totalDebit.value) }}</b></span>
      <span>贷方合计：<b>{{ fmt(adj.totalCredit.value) }}</b></span>
      <span>理由待补：<b class="is-warn">{{ adj.inadequateCount.value }}</b></span>
      <span>超重要性：<b class="is-warn">{{ adj.exceedCount.value }}</b></span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">三、审计说明</span>
          <div class="opinion-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAiNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReview">复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="adj.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明重大调整事项的性质、返利处理、理由充分性核查情况及对营业成本的影响…"
        @change="adj.saveAuditNote"
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
            @click="generateAiConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="adj.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价重大调整事项理由是否充分、列报是否恰当（A/B/C口径）…"
        @change="adj.saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabMajorAdjustment — F5-8 主营业务成本账户中重大调整事项核查表
 * 源表：日期/凭证号/事项/借贷方/理由/是否充分 + 抽凭 + AI + F5-1/4/7 交叉引用
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useF5MajorAdjustment,
  F5_MAJOR_ADJ_ADEQUACY_OPTIONS,
} from '../composables/useF5MajorAdjustment'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { SampledVoucher, FillMode } from '../composables/useSamplingAlgorithms'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly: boolean
  materiality?: number
  /** 审计年度（供抽凭引擎按年度查询序时账），由父入口从 project_context 派生 */
  year?: number
}>(), {
  materiality: 0,
  year: undefined,
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const adj = useF5MajorAdjustment({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
  materiality: computed(() => props.materiality ?? 0) as unknown as Ref<number>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const adequacyOptions = F5_MAJOR_ADJ_ADEQUACY_OPTIONS
const ieCtx = computed(() =>
  isImportExportSheet('f5', 'F5-8') ? resolveImportExportSheet('f5', 'F5-8') : null,
)

function rowClass({ row }: { row: any }): string {
  return adj.isRowHighlighted(row) ? 'f5-row-warn' : ''
}

function isInadequate(v: string): boolean {
  return !v || v === '不充分' || v === '待补充'
}

function handleSamplingFilled(payload: { samples: SampledVoucher[]; fillMode?: FillMode }) {
  const n = adj.mergeSamplingRows((payload?.samples ?? []) as any[])
  if (n > 0) ElMessage.success(`已填入 ${n} 笔抽凭样本`)
}

function fmt(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function openReview() {
  openReviewDialog?.('F5-8-conclusion')
}

function aiContext(): Record<string, unknown> {
  const filled = adj.rows.value.filter(
    (r) => r.itemContent.trim() || r.debitAmount || r.creditAmount,
  )
  return {
    sheet: 'F5-8',
    role: 'F5-1销售成本审定表的附表',
    tip: '检查现金返利、实物返利是否冲减或调整存货或购货当期主营业务成本',
    summary: {
      filledCount: adj.filledCount.value,
      totalDebit: adj.totalDebit.value,
      totalCredit: adj.totalCredit.value,
      inadequateCount: adj.inadequateCount.value,
      exceedCount: adj.exceedCount.value,
    },
    items: filled.map((r) => ({
      date: r.date,
      voucherNo: r.voucherNo,
      itemContent: r.itemContent,
      debitAmount: r.debitAmount,
      creditAmount: r.creditAmount,
      netAmount: r.netAmount,
      adjustmentReason: r.adjustmentReason,
      reasonAdequate: r.reasonAdequate,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adjustment-note',
    adj.auditNote.value,
    aiContext(),
    'AI 生成 · F5-8审计说明',
  )
  if (text) adj.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'adjustment-evaluation',
    adj.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-8审计结论',
  )
  if (text) adj.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-major-adj { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-major-adj :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-major-adj :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #315a8a;
  background: #eef4fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 600; color: #315a8a; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert, .change-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-hint { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }

.f5-ma-summary {
  display: flex;
  gap: 20px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  flex-wrap: wrap;
}
.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.f5-row-warn) { background: #fdf6ec !important; }

.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.opinion-actions { display: flex; gap: 6px; align-items: center; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
