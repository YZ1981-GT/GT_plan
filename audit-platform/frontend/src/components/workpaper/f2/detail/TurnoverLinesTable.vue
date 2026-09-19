<template>
  <div class="lines-wrap">
    <el-table
      :data="rows"
      border
      size="small"
      max-height="360"
      class="lines-table"
      :row-class-name="rowClass"
    >
      <el-table-column label="存货编码" width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.itemCode"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', { id: row.id, patch: { itemCode: v } })"
          />
        </template>
      </el-table-column>
      <el-table-column label="名称及规格" min-width="160">
        <template #default="{ row }">
          <el-input
            :model-value="row.itemName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', { id: row.id, patch: { itemName: v } })"
          />
        </template>
      </el-table-column>
      <el-table-column label="单位" width="72">
        <template #default="{ row }">
          <el-input
            :model-value="row.unit"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => emit('update', { id: row.id, patch: { unit: v } })"
          />
        </template>
      </el-table-column>

      <template v-if="showMove">
        <el-table-column label="期初库存" align="center">
          <el-table-column label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openingQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { openingQty: v ?? 0 } })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.openingUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.openingAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { openingAmt: v ?? 0 } })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期增加" align="center">
          <el-table-column label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.increaseQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { increaseQty: v ?? 0 } })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.increaseUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.increaseAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { increaseAmt: v ?? 0 } })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期减少" align="center">
          <el-table-column label="数量" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decreaseQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { decreaseQty: v ?? 0 } })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.decreaseUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.decreaseAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('update', { id: row.id, patch: { decreaseAmt: v ?? 0 } })"
              />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末结存" align="center">
          <el-table-column label="数量" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.closingQty }}</span></template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.unitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closingAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
      </template>

      <template v-if="showAging">
        <el-table-column label="账龄" align="center">
          <el-table-column
            v-for="seg in segments"
            :key="seg.key"
            :label="seg.label"
            width="100"
          >
            <template #default="{ row }">
              <el-input-number
                :model-value="Number(row.aging?.[seg.key] ?? 0)"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => emit('aging', { id: row.id, key: seg.key, value: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="库龄合计" width="100" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="Math.abs(row.agingTotal - row.closingAmt) > 0.01 ? 'bad' : 'formula'">
              {{ fmtAmt(row.agingTotal) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!showMove" label="期末金额" width="110" class-name="auto-calc-col">
          <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closingAmt) }}</span></template>
        </el-table-column>
        <el-table-column label="品质状况" width="100">
          <template #default="{ row }">
            <el-select
              :model-value="row.qualityStatus"
              size="small"
              clearable
              :disabled="isReadonly"
              @change="(v: string) => emit('update', { id: row.id, patch: { qualityStatus: v || '' } })"
            >
              <el-option v-for="o in QUALITY" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="emit('remove', row.id)">
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed } from 'vue'
import type { AgingSegment } from '@/composables/useAgingConfig'
import type { F2TurnoverRow, F2TurnoverView } from '../../composables/useF2DetailTurnover'

/** 与源模板提示一致：正常、残次、霉变、滞销等 */
const QUALITY = ['正常', '残次', '霉变', '毁损', '滞销', '积压']

const props = defineProps<{
  rows: F2TurnoverRow[]
  view: F2TurnoverView
  segments: AgingSegment[]
  isReadonly: boolean
}>()

const emit = defineEmits<{
  update: [payload: { id: string; patch: Partial<F2TurnoverRow> }]
  aging: [payload: { id: string; key: string; value: number }]
  remove: [id: string]
}>()

const showMove = computed(() => props.view === 'movement' || props.view === 'full')
const showAging = computed(() => props.view === 'aging' || props.view === 'full')

function fmtAmt(n: number): string {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPrice(v: number | ''): string {
  if (v === '' || v == null) return '—'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

function rowClass({ row }: { row: F2TurnoverRow }): string {
  return Math.abs(row.agingTotal - row.closingAmt) > 0.01 ? 'warn-row' : ''
}
</script>

<style scoped>
.lines-wrap { padding: 0 10px 8px; }
.lines-table { width: 100%; }
:deep(.auto-calc-col) { background: #faf8fc; }
.formula { color: #5b2c83; font-variant-numeric: tabular-nums; }
.bad { color: #c45656; font-weight: 600; }
:deep(.warn-row) { --el-table-tr-bg-color: #fff7e8; }
</style>
