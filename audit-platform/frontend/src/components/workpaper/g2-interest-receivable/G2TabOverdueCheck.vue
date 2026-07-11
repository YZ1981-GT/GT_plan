<template>
  <div class="g2-overdue-check">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表识别长期未收回应收利息，评估其可收回性与减值阶段迁移信号。</p>
        <p>2. 逾期天数 = MAX(0, 当前日期 - 约定收回日)；灰色底纹列为自动计算列。</p>
        <p>3. 逾期 &gt; 180天：红色高亮，建议转入 Stage3（已发生信用减值）。</p>
        <p>4. 逾期 &gt; 90天：橙色高亮，建议转入 Stage2（信用风险显著增加）。</p>
        <p>5. 须关注债务方信用状况变化，评估实际可收回性。</p>
        <p>6. 依据：CAS 22《金融工具确认和计量》预期信用损失（ECL）阶段迁移。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：识别长期未收回应收利息，评估可收回性，为减值阶段迁移与坏账准备计提充分性提供依据。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-6 长期未收回检查</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="overdue.addRow()">新增行</el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-6" /></span>
        <el-tag size="small" type="info">共 {{ overdue.dataRows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G2-6-overdue')">💬复核</el-button>
      </div>
    </div>

    <el-table :data="overdue.dataRows.value" border size="small" max-height="500"
      :row-class-name="rowClassName">
      <el-table-column label="序号" prop="seq" width="55" align="center" fixed />
      <el-table-column label="投资标的" width="130" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investTarget" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'investTarget', v)" />
        </template>
      </el-table-column>
      <el-table-column label="应收金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.receivableAmount" size="small" :controls="false" :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => overdue.updateCell(row.id, 'receivableAmount', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="约定收回日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.agreedRecoveryDate" type="date" size="small" value-format="YYYY-MM-DD"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => overdue.updateCell(row.id, 'agreedRecoveryDate', v ?? '')" />
        </template>
      </el-table-column>
      <el-table-column label="逾期天数" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span :class="['formula-cell', overdueColorClass(row)]"
            title="逾期天数 = MAX(0, 当前日期 - 约定收回日)">
            {{ row.overdueDays }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="阶段建议" width="100">
        <template #default="{ row }">
          <el-tag v-if="overdue.getStageSuggestion(row) === 'stage3'" type="danger" size="small">→Stage3</el-tag>
          <el-tag v-else-if="overdue.getStageSuggestion(row) === 'stage2'" type="warning" size="small">→Stage2</el-tag>
          <span v-else class="no-suggestion">—</span>
        </template>
      </el-table-column>
      <el-table-column label="逾期原因" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.overdueReason" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'overdueReason', v)" />
        </template>
      </el-table-column>
      <el-table-column label="债务方信用" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.debtorCreditStatus" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'debtorCreditStatus', v)" />
        </template>
      </el-table-column>
      <el-table-column label="催收措施" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.collectionMeasures" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'collectionMeasures', v)" />
        </template>
      </el-table-column>
      <el-table-column label="可收回性" width="130">
        <template #default="{ row }">
          <el-select :model-value="row.recoverability" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'recoverability', v)">
            <el-option v-for="opt in recoverabilityOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="风险等级" width="100">
        <template #default="{ row }">
          <el-select :model-value="row.riskLevel" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'riskLevel', v)">
            <el-option v-for="opt in riskLevelOptions" :key="opt.value" :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="审计建议" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.auditSuggestion" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'auditSuggestion', v)" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="overdue.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">汇总</span>
        逾期笔数 {{ overdue.summary.value.overdueCount }} ·
        逾期总金额 {{ fmtNum(overdue.summary.value.overdueTotalAmount) }} ·
        高风险笔数 {{ overdue.summary.value.highRiskCount }}
      </div>
    </div>

  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import {
  useG2OverdueCheck,
  RECOVERABILITY_OPTIONS,
  RISK_LEVEL_OPTIONS,
  type OverdueCheckRow,
} from '../composables/useG2OverdueCheck'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const overdue = useG2OverdueCheck({
  wpId: ref(''),
  projectId: ref(''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const recoverabilityOptions = RECOVERABILITY_OPTIONS
const riskLevelOptions = RISK_LEVEL_OPTIONS

function overdueColorClass(row: OverdueCheckRow): string {
  const hl = overdue.getOverdueHighlight(row)
  if (hl === 'red') return 'overdue-red'
  if (hl === 'orange') return 'overdue-orange'
  return ''
}

function rowClassName({ row }: { row: OverdueCheckRow }): string {
  const hl = overdue.getOverdueHighlight(row)
  if (hl === 'red') return 'row-overdue-red'
  if (hl === 'orange') return 'row-overdue-orange'
  return ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g2-overdue-check { padding: 12px; font-size: 13px; }
.g2-overdue-check :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.g2-overdue-check :deep(.el-table .cell) { font-size: 13px !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.overdue-red { color: #f56c6c; font-weight: 600; }
.overdue-orange { color: #e6a23c; font-weight: 600; }
.no-suggestion { color: #c0c4cc; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
</style>

<style>
/* 非 scoped - el-table 行级样式需要穿透 */
.g2-overdue-check .row-overdue-red { background-color: #fef0f0 !important; }
.g2-overdue-check .row-overdue-orange { background-color: #fdf6ec !important; }
</style>
