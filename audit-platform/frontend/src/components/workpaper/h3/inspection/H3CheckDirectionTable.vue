<template>
  <div class="check-direction-table">
    <el-empty
      v-if="!rows.length"
      :description="emptyText"
      :image-size="64"
    />
    <el-table
      v-else
      :data="enriched"
      border
      size="small"
      max-height="420"
      class="check-table"
      :row-class-name="rowClassName"
    >
      <el-table-column label="名称/类别" min-width="110" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.assetName"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { assetName: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="资产编号" width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.assetNo"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { assetNo: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="坐落" min-width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.location"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { location: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="面积(㎡)" width="80" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.area"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @update:model-value="(v: number | undefined) => emit('update', row.rowId, { area: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="单位" width="52">
        <template #default="{ row }">
          <el-input
            :model-value="row.unit"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { unit: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="账面数量" width="80">
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
      <el-table-column label="企业盘点" width="80">
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
      <el-table-column label="抽盘数量" width="80">
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
      <el-table-column label="抽盘−账面" width="84" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="抽盘数量 − 账面数量（+盈 −亏）" placement="top">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsBook) > 0.001 }">
              {{ fmtQty(row.sampleVsBook) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="抽盘−企业" width="84" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="抽盘数量 − 企业盘点数量" placement="top">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsClient) > 0.001 }">
              {{ fmtQty(row.sampleVsClient) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="企业−账面" width="84" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <el-tooltip content="企业盘点 − 账面数量" placement="top">
            <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.clientVsBook) > 0.001 }">
              {{ fmtQty(row.clientVsBook) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="用途" width="90">
        <template #default="{ row }">
          <el-select
            :model-value="row.purpose || undefined"
            size="small"
            clearable
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => emit('update', row.rowId, { purpose: v || '' })"
          >
            <el-option v-for="p in PURPOSE_OPTS" :key="p" :label="p" :value="p" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="租赁状态" width="95">
        <template #default="{ row }">
          <el-select
            :model-value="row.leaseStatus || undefined"
            size="small"
            clearable
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => emit('update', row.rowId, { leaseStatus: v || '' })"
          >
            <el-option v-for="s in LEASE_STATUS_OPTS" :key="s" :label="s" :value="s" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="租户" min-width="90">
        <template #default="{ row }">
          <el-input
            :model-value="row.tenant"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { tenant: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="产权证号" min-width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.titleCertNo"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { titleCertNo: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="品质状况" width="96">
        <template #default="{ row }">
          <el-select
            :model-value="row.qualityStatus || undefined"
            size="small"
            clearable
            allow-create
            filterable
            placeholder="选择"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => emit('update', row.rowId, { qualityStatus: v || '' })"
          >
            <el-option v-for="q in QUALITY_OPTS" :key="q" :label="q" :value="q" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="差异原因" min-width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.diffReason"
            size="small"
            :disabled="isReadonly"
            @update:model-value="(v: string) => emit('update', row.rowId, { diffReason: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结果" width="88" align="center">
        <template #default="{ row }">
          <span class="result-tag" :class="row.result === '账实相符' ? 'ok' : row.result ? 'bad' : ''">
            {{ row.result || '—' }}
          </span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" width="44" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="emit('remove', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
/**
 * H3CheckDirectionTable — H3-9 单向抽盘明细表（账面→实物 或 实物→账面）
 */
import { computed } from 'vue'
import {
  QUALITY_OPTS,
  LEASE_STATUS_OPTS,
  PURPOSE_OPTS,
  calcRowDiffs,
  type H3StocktakeCheckRow,
} from '../../composables/h3StocktakeCheckModel'

const props = withDefaults(defineProps<{
  rows: H3StocktakeCheckRow[]
  isReadonly: boolean
  emptyText?: string
}>(), {
  emptyText: '暂无明细',
})

const emit = defineEmits<{
  (e: 'update', rowId: string, patch: Partial<H3StocktakeCheckRow>): void
  (e: 'remove', rowId: string): void
}>()

const enriched = computed(() =>
  props.rows.map((r) => ({ ...r, ...calcRowDiffs(r) })),
)

function rowClassName({ row }: { row: H3StocktakeCheckRow & { hasVariance?: boolean } }): string {
  const parts: string[] = []
  if (row.hasVariance) parts.push('warn-row')
  if (row.leaseStatus === '空置') parts.push('vacant-row')
  return parts.join(' ')
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
:deep(.vacant-row) { --el-table-tr-bg-color: #fef9e7; }
:deep(.warn-row.vacant-row) { --el-table-tr-bg-color: var(--el-color-danger-light-9); }
:deep(.check-table) { font-size: var(--wp-font-size, 13px); }
</style>
