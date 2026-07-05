<script setup lang="ts">
/**
 * F4TabAdjudication — F4-1 审定表（贷方科目 2202 应付账款）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.1
 * 两级结构：按性质(货款/工程款/服务费/其他) + 按账龄(1年以内/1-2年/2-3年/3年以上)
 * 交叉校验：按性质小计 === 按账龄小计
 */
import { computed, inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF4Adjudication } from '../composables/useF4Adjudication'
import type { F4AdjudicationRow } from '../composables/useF4Adjudication'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  if (v < 0) return `(${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  natureDataRows,
  natureSubtotalRow,
  agingDataRows,
  agingSubtotalRow,
  totalRow,
  trialBalanceAmount,
  variance,
  crossCheckPassed,
  updateNatureCell,
  updateAgingCell,
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

// ─── 按性质表数据（含小计） ──────────────────────────────────────────────
const natureTableData = computed(() => [...natureDataRows.value, natureSubtotalRow.value])

// ─── 按账龄表数据（含小计） ──────────────────────────────────────────────
const agingTableData = computed(() => [...agingDataRows.value, agingSubtotalRow.value])

// ─── 差异判断 ────────────────────────────────────────────────────────────
const hasDifference = computed(() => Math.abs(variance.value) > 0.005)

// ─── 汇总行数据（合计/TB数/差异） ───────────────────────────────────────
const summaryTableData = computed(() => [
  { key: 'total', label: '合计（按性质小计）', amount: totalRow.value.closingAdjusted },
  { key: 'tb', label: '试算表数(2202)', amount: trialBalanceAmount.value },
  { key: 'variance', label: '差异', amount: variance.value },
])

// ─── 行样式 ──────────────────────────────────────────────────────────────
function getNatureRowClassName({ row }: { row: F4AdjudicationRow }): string {
  if (row.rowKey === 'nature-subtotal') {
    return crossCheckPassed.value ? 'subtotal-row-bg' : 'subtotal-row-bg cross-check-fail'
  }
  return ''
}

function getAgingRowClassName({ row }: { row: F4AdjudicationRow }): string {
  if (row.rowKey === 'aging-subtotal') {
    return crossCheckPassed.value ? 'subtotal-row-bg' : 'subtotal-row-bg cross-check-fail'
  }
  return ''
}

function getSummaryRowClassName({ row }: { row: { key: string; amount: number } }): string {
  if (row.key === 'total') return 'subtotal-row-bg'
  if (row.key === 'variance' && hasDifference.value) return 'variance-row'
  return ''
}

function confirmAdjudication() {
  publishAdjudicated()
  ElMessage.success('已确认审定并发布 EventBus(substantive:adjudicated)')
}
</script>

<template>
  <div class="f4-tab-adjudication">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 应付账款为贷方科目(2202)：期末未审 = 期初审定 + 贷方发生 - 借方发生。</p>
        <p>2. 审定 = 未审 + 账项调整(AJE) + 重分类(RJE)。</p>
        <p>3. 两级结构：按性质(货款/工程款/服务费/其他) + 按账龄(1年以内/1-2年/2-3年/3年以上)。</p>
        <p>4. 交叉校验：按性质小计 必须等于 按账龄小计（不等标红）。</p>
        <p>5. 差异≠0 时标红，确认审定后回写试算表。</p>
      </div>
    </details>

    <el-alert v-if="!crossCheckPassed" type="error" :closable="false" class="cross-alert">
      ⚠️ 交叉校验失败：按性质小计({{ fmtAmount(natureSubtotalRow.closingAdjusted) }}) ≠ 按账龄小计({{ fmtAmount(agingSubtotalRow.closingAdjusted) }})
    </el-alert>
    <el-alert v-if="hasDifference" type="error" :closable="false" class="cross-alert">
      审定合计与试算平衡表差异：{{ fmtAmount(variance) }}元
    </el-alert>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="confirmAdjudication">确认审定</el-button>
      </div>
      <div class="toolbar-right">
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-1-adjudication')"
        >复核</el-button>
      </div>
    </div>

    <!-- ─── 按性质分类表 ──────────────────────────────────────────────── -->
    <h4 class="table-title">一、按性质分类</h4>
    <el-table
      :data="natureTableData"
      border
      size="small"
      :row-class-name="getNatureRowClassName"
      style="width: 100%; font-size: 13px"
    >
      <el-table-column prop="label" label="项目" min-width="120" fixed />

      <el-table-column label="期初未审" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'openingUnadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'openingAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'openingRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初审定 = 期初未审 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.openingAdjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期贷方" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.periodCredit"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'periodCredit', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodCredit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期借方" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.periodDebit"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'periodDebit', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodDebit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末未审" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末未审 = 期初审定 + 贷方 - 借方" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.closingUnadjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期末AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.closingAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'closingAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.closingAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.closingRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateNatureCell(row.rowKey, 'closingRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.closingRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末审定 = 期末未审 + AJE + RJE" placement="top">
            <span class="formula-cell audited-cell">{{ fmtAmount(row.closingAdjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable && !isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateNatureCell(row.rowKey, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 按账龄分类表 ──────────────────────────────────────────────── -->
    <h4 class="table-title">二、按账龄分类</h4>
    <el-table
      :data="agingTableData"
      border
      size="small"
      :row-class-name="getAgingRowClassName"
      style="width: 100%; font-size: 13px"
    >
      <el-table-column prop="label" label="项目" min-width="120" fixed />

      <el-table-column label="期初未审" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingUnadjusted"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'openingUnadjusted', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingUnadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'openingAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.openingRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'openingRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.openingRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期初审定" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初审定 = 期初未审 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.openingAdjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="本期贷方" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.periodCredit"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'periodCredit', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodCredit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期借方" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.periodDebit"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'periodDebit', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.periodDebit) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末未审" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末未审 = 期初审定 + 贷方 - 借方" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.closingUnadjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期末AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.closingAje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'closingAje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.closingAje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.isEditable && !isReadonly"
            :model-value="row.closingRje"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateAgingCell(row.rowKey, 'closingRje', v ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.closingRje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="期末审定" min-width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期末审定 = 期末未审 + AJE + RJE" placement="top">
            <span class="formula-cell audited-cell">{{ fmtAmount(row.closingAdjusted) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="索引" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="row.isEditable && !isReadonly"
            :model-value="row.indexRef"
            size="small"
            @change="(v: string) => updateAgingCell(row.rowKey, 'indexRef', v)"
          />
          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 合计 / 试算表数 / 差异 ────────────────────────────────────── -->
    <h4 class="table-title">三、汇总</h4>
    <el-table
      :data="summaryTableData"
      border
      size="small"
      :row-class-name="getSummaryRowClassName"
      style="width: 100%; font-size: 13px"
    >
      <el-table-column prop="label" label="项目" min-width="140" fixed />
      <el-table-column label="期末审定" min-width="140" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="row.key === 'tb' && !isReadonly"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => updateTrialBalance(v ?? 0)"
          />
          <span v-else :class="{ 'formula-cell': row.key !== 'tb' }">{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ─── 审计说明 / 结论 ───────────────────────────────────────────── -->
    <el-card class="audit-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计说明 / 结论</span>
          <el-button
            v-if="openReviewDialog"
            size="small"
            @click="openReviewDialog('f4-1-note')"
          >复核</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="审计说明（对应付账款余额构成、变动及合理性的分析描述）"
      />
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly"
        placeholder="审计结论"
        style="margin-top: 8px"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-adjudication {
  font-size: 13px;
}
.guidance-details {
  margin-bottom: 12px;
  font-size: 13px;
}
.guidance-details .guidance-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.cross-alert {
  margin-bottom: 8px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
}
.toolbar-right {
  display: flex;
  gap: 8px;
}
.table-title {
  margin: 16px 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.table-title:first-of-type {
  margin-top: 8px;
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
.audited-cell {
  font-weight: 600;
  color: #409eff;
}
.subtotal-row-bg :deep(td) {
  font-weight: 600;
  background: #fafafa !important;
}
.cross-check-fail :deep(td) {
  background: #fef0f0 !important;
  color: #f56c6c;
  font-weight: 700;
}
.variance-row :deep(td) {
  color: #f56c6c;
  font-weight: 600;
}
.audit-card {
  margin-top: 16px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
</style>
