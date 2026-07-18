<template>
  <div class="f5-monthly">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示主营业务成本各品种 1~12 月结转明细；品种行可增删，亦可导入月度明细账。</p>
        <p>2. 灰色列为公式列：本期未审=各月合计；本期/上期审定=未审+账项调整+重分类；变动比例=(本期−上期)/上期。</p>
        <p>3. 合计行纵向汇总；比例行=各月合计÷本期未审合计。变动比例绝对值≥30% 标黄。</p>
        <p>4. 品种全年未审/上期未审可同步至 F5-1 审定表主营业务成本区。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实主营业务成本各品种月度结转的存在、完整与准确，识别异常波动，验证与生产经营节奏匹配。"
      class="objective-alert"
    />

    <el-alert
      v-if="detail.significantChanges.value.length"
      type="warning"
      :closable="false"
      class="change-alert"
      :title="`未审/审定变动比例绝对值≥${threshold}% 的品种：${detail.significantChanges.value.map((r) => r.product).join('、')}`"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="promptAddRow">+ 品种</el-button>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          v-if="importExportCtx"
          :wp-id="wpId"
          :api-prefix="importExportCtx.apiPrefix"
          :sheet="importExportCtx.sheet"
          :disabled="isReadonly"
          @imported="$emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:F5-1" :context-project-id="projectIdStr" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <F5SheetAttachments
      v-if="projectId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F5-2"
      label="月度明细附件"
    />

    <el-table
      :data="tableData"
      size="small"
      border
      stripe
      :row-class-name="rowClass"
      max-height="520"
      class="monthly-table"
    >
      <el-table-column label="项目/月份" width="130" fixed>
        <template #default="{ row }">
          <template v-if="row.__type === 'data'">
            <el-input
              v-if="!isReadonly"
              :model-value="row.product"
              size="small"
              @change="(v: string) => detail.updateCell(row.id, 'product', v)"
            />
            <span v-else>{{ row.product }}</span>
          </template>
          <strong v-else-if="row.__type === 'total'">合计</strong>
          <strong v-else>比例</strong>
        </template>
      </el-table-column>

      <el-table-column label="主营业务成本月度小计" align="center">
        <el-table-column
          v-for="(label, mi) in monthLabels"
          :key="label"
          :label="label"
          width="88"
          align="right"
        >
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.months[mi]"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => detail.updateMonth(row.id, mi, v ?? 0)"
            />
            <span v-else-if="row.__type === 'ratio'" class="f5-formula" title="该月合计 / 本期未审合计">
              {{ pct(row.months[mi]) }}
            </span>
            <span v-else class="f5-formula">{{ fmt(row.months[mi]) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期未审数" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.__type === 'ratio'" class="f5-formula">{{ pct(row.currentUnaudited) }}</span>
          <span v-else class="f5-formula" title="Σ(1~12月)">{{ fmt(row.currentUnaudited) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="本期审计调整" align="center">
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => detail.updateCell(row.id, 'currentAje', v ?? 0)"
            />
            <span v-else-if="row.__type !== 'ratio'">{{ fmt(row.currentAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.currentRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => detail.updateCell(row.id, 'currentRje', v ?? 0)"
            />
            <span v-else-if="row.__type !== 'ratio'">{{ fmt(row.currentRje) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="本期审定数" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.__type !== 'ratio'" class="f5-formula" title="未审 + 账项 + 重分类">
            {{ fmt(row.currentAudited) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="上期未审数" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.__type === 'data' && !isReadonly"
            :model-value="row.priorUnaudited"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number | undefined) => detail.updateCell(row.id, 'priorUnaudited', v ?? 0)"
          />
          <span v-else-if="row.__type !== 'ratio'">{{ fmt(row.priorUnaudited) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="上期审计调整" align="center">
        <el-table-column label="账项调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorAje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => detail.updateCell(row.id, 'priorAje', v ?? 0)"
            />
            <span v-else-if="row.__type !== 'ratio'">{{ fmt(row.priorAje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="重分类调整" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.__type === 'data' && !isReadonly"
              :model-value="row.priorRje"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => detail.updateCell(row.id, 'priorRje', v ?? 0)"
            />
            <span v-else-if="row.__type !== 'ratio'">{{ fmt(row.priorRje) }}</span>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="上期审定数" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span v-if="row.__type !== 'ratio'" class="f5-formula" title="上期未审 + 账项 + 重分类">
            {{ fmt(row.priorAudited) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="未审变动比例" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span
            v-if="row.__type !== 'ratio'"
            class="f5-formula"
            :class="{ 'is-warn': isRateWarn(row.unauditedChangeRate) }"
            title="(本期未审 − 上期未审) / 上期未审"
          >{{ pct(row.unauditedChangeRate) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="审定变动比例" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span
            v-if="row.__type !== 'ratio'"
            class="f5-formula"
            :class="{ 'is-warn': isRateWarn(row.auditedChangeRate) }"
            title="(本期审定 − 上期审定) / 上期审定"
          >{{ pct(row.auditedChangeRate) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="120">
        <template #default="{ row }">
          <el-input
            v-if="row.__type === 'data' && !isReadonly"
            :model-value="row.remark"
            size="small"
            @change="(v: string) => detail.updateCell(row.id, 'remark', v)"
          />
          <span v-else-if="row.__type === 'data'">{{ row.remark }}</span>
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="64" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="row.__type === 'data'" title="确认删除？" @confirm="detail.removeRow(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删除</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

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
        :model-value="detail.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明各品种月度结转情况、异常波动原因、与生产经营节奏匹配情况等…"
        @change="detail.saveAuditNote"
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
        :model-value="detail.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价主营业务成本月度明细是否公允反映结转情况…"
        @change="detail.saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * F5TabMonthlyDetail — F5-2 主营业务成本月度明细表
 * 源表：品种动态行 × 1~12月 + 本期/上期未审·调整·审定 + 变动比例 + 合计/比例行 + AI说明结论
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import {
  useF5MonthlyDetail,
  MONTH_LABELS,
  F5_MONTHLY_CHANGE_RATE_THRESHOLD,
} from '../composables/useF5MonthlyDetail'
import { useF5AiGenerate } from '../composables/useF5AiGenerate'
import { resolveImportExportSheet, isImportExportSheet } from '../shared/cycleImportExportRegistry'
import CycleImportExportDropdown from '../shared/CycleImportExportDropdown.vue'
import F5SheetAttachments from './F5SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

defineEmits<{ imported: [] }>()

const props = withDefaults(defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
}>(), {
  projectId: '',
})

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const detail = useF5MonthlyDetail({
  allResponses: allResponsesRef,
  isReadonly: computed(() => props.isReadonly) as unknown as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF5AiGenerate(wpIdRef)

const monthLabels = MONTH_LABELS
const threshold = F5_MONTHLY_CHANGE_RATE_THRESHOLD
const projectIdStr = computed(() => props.projectId)

const importExportCtx = computed(() =>
  isImportExportSheet('f5', 'F5-2') ? resolveImportExportSheet('f5', 'F5-2') : null,
)

const tableData = computed(() => {
  const rows: any[] = detail.rows.value.map((r) => ({ __type: 'data', ...r }))
  const total = detail.totalRow.value
  const ratio = detail.ratioRow.value
  rows.push({
    __type: 'total',
    id: '__total',
    product: '合计',
    months: total.months,
    currentUnaudited: total.currentUnaudited,
    currentAje: total.currentAje,
    currentRje: total.currentRje,
    currentAudited: total.currentAudited,
    priorUnaudited: total.priorUnaudited,
    priorAje: total.priorAje,
    priorRje: total.priorRje,
    priorAudited: total.priorAudited,
    unauditedChangeRate: total.unauditedChangeRate,
    auditedChangeRate: total.auditedChangeRate,
    remark: '',
  })
  rows.push({
    __type: 'ratio',
    id: '__ratio',
    product: '比例',
    months: ratio.months,
    currentUnaudited: ratio.currentUnaudited,
    remark: '',
  })
  return rows
})

function rowClass({ row }: { row: any }): string {
  if (row.__type === 'total' || row.__type === 'ratio') return 'f5-row-total'
  if (detail.isRowHighlighted(row)) return 'f5-row-warn'
  return ''
}

function isRateWarn(rate: number | 'N/A' | null | undefined): boolean {
  return typeof rate === 'number' && Math.abs(rate) >= threshold
}

async function promptAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入品种名称', '新增品种', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '品种名称不能为空',
    })
    if (value) detail.addRow(value.trim())
  } catch { /* 取消 */ }
}

function fmt(v: number | null | undefined): string {
  if (v == null) return '-'
  if (Math.abs(v) < 0.005) return '-'
  const formatted = Math.abs(v).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return v < 0 ? `(${formatted})` : formatted
}

function pct(v: number | 'N/A' | null | undefined): string {
  if (v == null || v === 'N/A') return 'N/A'
  return `${Number(v).toFixed(2)}%`
}

function openReview() {
  openReviewDialog?.('F5-2-conclusion')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F5-2',
    accountCode: '6401',
    threshold,
    significantChanges: detail.significantChanges.value.map((r) => ({
      product: r.product,
      currentUnaudited: r.currentUnaudited,
      currentAudited: r.currentAudited,
      priorUnaudited: r.priorUnaudited,
      priorAudited: r.priorAudited,
      unauditedChangeRate: r.unauditedChangeRate,
      auditedChangeRate: r.auditedChangeRate,
    })),
    total: detail.totalRow.value,
    ratio: detail.ratioRow.value,
    products: detail.rows.value.map((r) => ({
      product: r.product,
      months: r.months,
      currentUnaudited: r.currentUnaudited,
      currentAudited: r.currentAudited,
      priorUnaudited: r.priorUnaudited,
      priorAudited: r.priorAudited,
      unauditedChangeRate: r.unauditedChangeRate,
      auditedChangeRate: r.auditedChangeRate,
      remark: r.remark,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'monthly-detail-note',
    detail.auditNote.value,
    aiContext(),
    'AI 生成 · F5-2审计说明',
  )
  if (text) detail.saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'monthly-detail-conclusion',
    detail.auditConclusion.value,
    aiContext(),
    'AI 生成 · F5-2审计结论',
  )
  if (text) detail.saveAuditConclusion(text)
}
</script>

<style scoped>
.f5-monthly { padding: 12px; font-size: var(--wp-font-size, 13px); }
.f5-monthly :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.f5-monthly :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }

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
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

.f5-formula { border-bottom: 1px dashed #909399; cursor: help; }
.f5-formula.is-warn { color: #e6a23c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.f5-row-total) { background: #f0f5fa !important; font-weight: 600; }
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
