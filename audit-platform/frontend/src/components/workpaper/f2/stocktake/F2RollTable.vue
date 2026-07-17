<template>
  <el-table
    :data="rows"
    border
    size="small"
    max-height="420"
    :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''"
  >
    <el-table-column label="类别" width="80">
      <template #default="{ row }">
        <el-input :model-value="row.category" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { category: v })" />
      </template>
    </el-table-column>
    <el-table-column label="编码" width="90">
      <template #default="{ row }">
        <el-input :model-value="row.itemCode" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { itemCode: v })" />
      </template>
    </el-table-column>
    <el-table-column label="品名" min-width="100">
      <template #default="{ row }">
        <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { itemName: v })" />
      </template>
    </el-table-column>
    <el-table-column label="规格" width="80">
      <template #default="{ row }">
        <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { spec: v })" />
      </template>
    </el-table-column>
    <el-table-column label="单位" width="60">
      <template #default="{ row }">
        <el-input :model-value="row.unit" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { unit: v })" />
      </template>
    </el-table-column>
    <el-table-column label="单价" width="80">
      <template #default="{ row }">
        <el-input-number :model-value="row.unitPrice" size="small" :controls="false" :disabled="isReadonly"
          @update:model-value="(v: number | undefined) => emit('update', row.id, { unitPrice: v ?? 0 })" />
      </template>
    </el-table-column>
    <el-table-column label="仓库" width="80">
      <template #default="{ row }">
        <el-input :model-value="row.warehouse" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { warehouse: v })" />
      </template>
    </el-table-column>
    <el-table-column label="盘点日实存(A)" width="110">
      <template #default="{ row }">
        <el-input-number :model-value="row.countDayQty" size="small" :controls="false" :disabled="isReadonly"
          @update:model-value="(v: number | undefined) => emit('update', row.id, { countDayQty: v ?? 0 })" />
      </template>
    </el-table-column>
    <el-table-column :label="addLabel" width="110">
      <template #default="{ row }">
        <el-input-number
          :model-value="mode === 'after' ? row.outboundQty : row.inboundQty"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @update:model-value="(v: number | undefined) => onAdd(row.id, v)"
        />
      </template>
    </el-table-column>
    <el-table-column :label="lessLabel" width="110">
      <template #default="{ row }">
        <el-input-number
          :model-value="mode === 'after' ? row.inboundQty : row.outboundQty"
          size="small"
          :controls="false"
          :disabled="isReadonly"
          @update:model-value="(v: number | undefined) => onLess(row.id, v)"
        />
      </template>
    </el-table-column>
    <el-table-column label="截止日实存(D)" width="110" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <el-tooltip :content="formulaTip" placement="top">
          <span class="formula-cell">{{ row.calcBsQty.toLocaleString() }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="截止日账面(E)" width="110">
      <template #default="{ row }">
        <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
          @update:model-value="(v: number | undefined) => emit('update', row.id, { bookQty: v ?? 0 })" />
      </template>
    </el-table-column>
    <el-table-column label="数量差异(F)" width="100" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <el-tooltip content="F = D − E" placement="top">
          <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.qtyDiff.toLocaleString() }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="金额差异(G)" width="100" align="right" class-name="auto-calc-col">
      <template #default="{ row }">
        <el-tooltip content="G ≈ F × 单价" placement="top">
          <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.amtDiff.toLocaleString() }}</span>
        </el-tooltip>
      </template>
    </el-table-column>
    <el-table-column label="差异原因(H)" min-width="100">
      <template #default="{ row }">
        <el-input :model-value="row.varianceReason" size="small" :disabled="isReadonly"
          @update:model-value="(v: string) => emit('update', row.id, { varianceReason: v })" />
      </template>
    </el-table-column>
    <el-table-column label="是否调整(I)" width="100">
      <template #default="{ row }">
        <el-select
          :model-value="row.needAdjust || ''"
          size="small"
          clearable
          placeholder="—"
          :disabled="isReadonly"
          style="width: 100%"
          @update:model-value="(v: string) => emit('update', row.id, { needAdjust: v || '' })"
        >
          <el-option label="是" value="是" />
          <el-option label="否" value="否" />
        </el-select>
      </template>
    </el-table-column>
    <el-table-column width="44">
      <template #default="{ row }">
        <el-button v-if="!isReadonly" link type="danger" size="small" @click="emit('remove', row.id)">删</el-button>
      </template>
    </el-table-column>
    <el-table-column v-if="wpId && !isReadonly" label="OCR" width="50" align="center">
      <template #default="{ row }">
        <el-upload
          :show-file-list="false"
          :auto-upload="false"
          accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
          :disabled="ocrLoadingId === row.id"
          @change="(f: any) => emit('ocr', row.id, f?.raw)"
        >
          <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
        </el-upload>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StocktakeRollMode, StocktakeRollforwardRow } from './f2StocktakeConfigs'

export type F2RollEnrichedRow = StocktakeRollforwardRow & {
  calcBsQty: number
  qtyDiff: number
  amtDiff: number
  hasVariance: boolean
}

const props = defineProps<{
  mode: StocktakeRollMode
  rows: F2RollEnrichedRow[]
  isReadonly: boolean
  wpId?: string
  ocrLoadingId?: string | null
}>()

const emit = defineEmits<{
  update: [id: string, patch: Partial<StocktakeRollforwardRow>]
  remove: [id: string]
  ocr: [id: string, file?: File]
}>()

const addLabel = computed(() => (props.mode === 'after' ? '加:发出(B)' : '加:入库(B)'))
const lessLabel = computed(() => (props.mode === 'after' ? '减:入库(C)' : '减:发出(C)'))
const formulaTip = computed(() =>
  props.mode === 'after' ? 'D = A + 发出 − 入库' : 'D = A + 入库 − 发出',
)

function onAdd(id: string, v: number | undefined) {
  if (props.mode === 'after') emit('update', id, { outboundQty: v ?? 0 })
  else emit('update', id, { inboundQty: v ?? 0 })
}
function onLess(id: string, v: number | undefined) {
  if (props.mode === 'after') emit('update', id, { inboundQty: v ?? 0 })
  else emit('update', id, { outboundQty: v ?? 0 })
}
</script>

<style scoped>
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.formula-cell.diff-warn { color: #f56c6c; font-weight: 600; }
</style>
