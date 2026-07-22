<template>
  <div class="h2-check-direction-table">
    <el-empty v-if="!rows.length" :description="emptyText" :image-size="64" />
    <el-table
      v-else
      :data="enriched"
      border
      size="small"
      max-height="420"
      class="check-table"
      :row-class-name="rowClass"
    >
      <el-table-column label="在建工程名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.name"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { name: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="工程编号" width="88">
        <template #default="{ row }">
          <el-input
            :model-value="row.assetNo"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { assetNo: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="单价" width="80">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.unitPrice"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { unitPrice: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="账面数量" width="84">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.bookQty"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { bookQty: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="账面金额" width="100">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.bookAmount"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { bookAmount: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="企业盘点" width="84">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.clientCountQty"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { clientCountQty: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="抽盘数量" width="84">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.sampleQty"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { sampleQty: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="抽盘−账面" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="抽盘数量 − 账面数量（+盈 −亏）" placement="top">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsBook) > 0.001 }">
              {{ fmtQty(row.sampleVsBook) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="抽盘−企业" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsClient) > 0.001 }">
            {{ fmtQty(row.sampleVsClient) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="企业−账面" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.clientVsBook) > 0.001 }">
            {{ fmtQty(row.clientVsBook) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="进度状况" min-width="110">
        <template #default="{ row }">
          <el-input
            :model-value="row.progressDesc"
            size="small"
            :disabled="isReadonly"
            placeholder="形象进度/施工状态"
            @update:model-value="(v: string) => emit('update', row.rowId, { progressDesc: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="达可使用" width="88">
        <template #default="{ row }">
          <el-select
            :model-value="row.readyForUse || undefined"
            size="small"
            clearable
            placeholder="—"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => emit('update', row.rowId, { readyForUse: (v || '') as any })"
          >
            <el-option v-for="o in READY_FOR_USE_OPTS" :key="o" :label="o" :value="o" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="已停工时间" width="96">
        <template #default="{ row }">
          <el-input
            :model-value="row.stopDuration"
            size="small"
            :disabled="isReadonly"
            placeholder="如6个月"
            @update:model-value="(v: string) => emit('update', row.rowId, { stopDuration: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="停工原因" min-width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.stopReason"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { stopReason: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="施工状态" width="92">
        <template #default="{ row }">
          <el-select
            :model-value="row.constructionStatus || undefined"
            size="small"
            clearable
            placeholder="—"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => emit('update', row.rowId, { constructionStatus: (v || '') as any })"
          >
            <el-option v-for="o in CONSTRUCTION_STATUS_OPTS" :key="o" :label="o" :value="o" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="结果" width="84" align="center">
        <template #default="{ row }">
          <span class="result-tag" :class="row.result === '账实相符' ? 'ok' : row.result ? 'bad' : ''">
            {{ row.result || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="差异原因" min-width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.diffReason"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { diffReason: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { remark: v })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" width="44">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="emit('remove', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  READY_FOR_USE_OPTS,
  CONSTRUCTION_STATUS_OPTS,
  calcRowDiffs,
  isStoppedCheckRow,
  type H2StocktakeCheckRow,
} from '../../composables/h2StocktakeCheckModel'

const props = withDefaults(defineProps<{
  rows: H2StocktakeCheckRow[]
  isReadonly: boolean
  emptyText?: string
}>(), {
  emptyText: '暂无明细',
})

const emit = defineEmits<{
  (e: 'update', rowId: string, patch: Partial<H2StocktakeCheckRow>): void
  (e: 'remove', rowId: string): void
}>()

const enriched = computed(() =>
  props.rows.map((r) => ({ ...r, ...calcRowDiffs(r) })),
)

function rowClass({ row }: { row: H2StocktakeCheckRow & ReturnType<typeof calcRowDiffs> }) {
  if (isStoppedCheckRow(row)) return 'stop-row'
  if (row.hasVariance) return 'warn-row'
  if (row.readyForUse === '是') return 'ready-row'
  return ''
}

function fmtQty(val: number): string {
  if (Math.abs(val) < 0.001) return '0'
  return val.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}
</script>

<style scoped>
.formula-cell {
  font-variant-numeric: tabular-nums;
  font-family: ui-monospace, monospace;
}
.diff-warn { color: var(--el-color-danger); font-weight: 600; }
.result-tag.ok { color: var(--el-color-success); }
.result-tag.bad { color: var(--el-color-danger); }
:deep(.warn-row) { --el-table-tr-bg-color: var(--el-color-danger-light-9); }
:deep(.stop-row) { --el-table-tr-bg-color: #fef0f0; }
:deep(.ready-row) { --el-table-tr-bg-color: var(--el-color-warning-light-9); }
:deep(.check-table) { font-size: var(--wp-font-size, 13px); }
</style>
