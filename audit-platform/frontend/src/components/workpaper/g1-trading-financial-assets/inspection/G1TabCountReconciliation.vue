<template>
  <div class="g1-count-recon">
    <div class="section-head">
      <h3 class="sheet-title">G1-12 证券盘点倒轧表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="recon.addRow()">新增倒轧行</el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-11" /></span>
        <el-tag size="small" type="info">共 {{ recon.rows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G1-12-conclusion')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：将监盘日证券结存倒轧至报表日，核实报表日推算余额与账面余额一致，确认交易性金融资产期末存在性与完整性。"
      class="objective-alert"
    />

    <div class="stats-bar">
      倒轧证券：<b>{{ recon.rows.value.length }}</b> 项 ·
      差异项：<b :class="{ warn: recon.diffCount.value > 0 }">{{ recon.diffCount.value }}</b>
    </div>

    <el-segmented v-model="segment" :options="segmentOptions" size="small" class="segment-bar" />

    <el-table :data="recon.rows.value" border size="small" max-height="500"
      :row-class-name="rowClass">
      <el-table-column
        v-for="col in currentColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' ? 'right' : 'left'"
        :class-name="col.formula ? 'auto-calc-col' : ''"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row, $index }">
          <span v-if="col.prop === 'seq'">{{ $index + 1 }}</span>
          <span v-else-if="col.formula" class="formula-cell"
            :class="{ 'diff-warn': isDiffCol(col.prop) && recon.isDiffAbnormal(row) }"
            :title="formulaHint(col.prop)">
            {{ fmtNum(row[col.prop]) }}
          </span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="recon.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="recon.updateRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" size="small" type="danger" link @click="recon.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">合计</span>
        推算余额·金额 {{ fmtNum(recon.grandTotal.value.derivedAmount) }} ·
        账面余额·金额 {{ fmtNum(recon.grandTotal.value.bookAmount) }} ·
        差异·金额 {{ fmtNum(recon.grandTotal.value.diffAmount) }}
      </div>
    </div>

    <el-card class="conclusion-card" shadow="never">
      <template #header>审计结论</template>
      <el-input v-model="recon.auditConclusion.value" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        :disabled="isReadonly" placeholder="对证券盘点倒轧的复核结论..." />
    </el-card>

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>报表日推算余额 = 监盘日余额 + 盘点日至报表日增加 - 减少（数量与金额各算）。</li>
        <li>倒轧差异 = 推算余额 - 账面余额，差异不为 0 时橙色高亮。</li>
        <li>18列拆为2区段：监盘日数据 / 倒轧计算，切换 Tab 时行保持同步。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject } from 'vue'
import {
  useG1CountReconciliation,
  type G1ReconciliationRow,
} from '../../composables/useG1CountReconciliation'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const recon = useG1CountReconciliation({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

const segment = ref<'countday' | 'calc'>('countday')
const segmentOptions = [
  { label: '监盘日数据', value: 'countday' },
  { label: '倒轧计算', value: 'calc' },
]

const currentColumns = computed(() =>
  segment.value === 'countday' ? recon.countDayColumns : recon.calcColumns,
)

const FORMULA_HINTS: Partial<Record<keyof G1ReconciliationRow, string>> = {
  derivedQuantity: '推算余额·数量 = 监盘日数量 + 增加 - 减少',
  derivedAmount: '推算余额·金额 = 监盘日金额 + 增加 - 减少',
  diffQuantity: '差异·数量 = 推算余额 - 账面余额',
  diffAmount: '差异·金额 = 推算余额 - 账面余额',
}

function formulaHint(prop: keyof G1ReconciliationRow): string {
  return FORMULA_HINTS[prop] ?? ''
}

function isDiffCol(prop: keyof G1ReconciliationRow): boolean {
  return prop === 'diffQuantity' || prop === 'diffAmount'
}

function rowClass({ row }: { row: G1ReconciliationRow }): string {
  return recon.isDiffAbnormal(row) ? 'diff-row' : ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString() : String(v ?? '')
}
</script>

<style scoped>
.g1-count-recon { padding: 12px; font-size: 13px; }
.g1-count-recon :deep(.el-table) { --el-table-font-size: 13px; font-size: 13px; }
.g1-count-recon :deep(.el-table .cell) { font-size: 13px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }
.stats-bar { margin-bottom: 10px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #e6a23c; }
.segment-bar { margin-bottom: 12px; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa; }
.diff-warn { color: #e6a23c; font-weight: 600; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
.conclusion-card { margin-top: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; }
:deep(.diff-row) { background: #fdf6ec; }
</style>
