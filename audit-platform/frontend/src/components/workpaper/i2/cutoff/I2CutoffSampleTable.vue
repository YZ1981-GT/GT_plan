<template>
  <el-table :data="rows" border size="small" class="cutoff-table" max-height="360" :row-class-name="rowClassName">
    <el-table-column type="index" label="序号" width="50" fixed />

    <!-- 单据→账：支出凭单在前 -->
    <template v-if="direction === 'backward'">
      <el-table-column label="支出凭单" align="center" class-name="col-doc">
        <el-table-column label="凭单编号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.documentNo" size="small" placeholder="编号" @update:model-value="(v: string) => emit('update', row, 'documentNo', v)" />
            <span v-else>{{ row.documentNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭单日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.documentDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="单据日期" style="width:100%" @update:model-value="(v: string) => emit('update', row, 'documentDate', v)" />
            <span v-else>{{ row.documentDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.documentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => emit('update', row, 'documentAmount', v)" />
            <span v-else>{{ fmtAmount(row.documentAmount) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="记账凭证" align="center" class-name="col-voucher">
        <el-table-column label="日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.recordDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="记账日期" style="width:100%" @update:model-value="(v: string) => emit('update', row, 'recordDate', v)" />
            <span v-else>{{ row.recordDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号" @update:model-value="(v: string) => emit('update', row, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => emit('update', row, 'amount', v)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="摘要" @update:model-value="(v: string) => emit('update', row, 'description', v)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </template>

    <!-- 账→单据：记账凭证在前 -->
    <template v-else>
      <el-table-column label="记账凭证" align="center" class-name="col-voucher">
        <el-table-column label="日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.recordDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="记账日期" style="width:100%" @update:model-value="(v: string) => emit('update', row, 'recordDate', v)" />
            <span v-else>{{ row.recordDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" placeholder="凭证号" @update:model-value="(v: string) => emit('update', row, 'voucherNo', v)" />
            <span v-else>{{ row.voucherNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => emit('update', row, 'amount', v)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.description" size="small" placeholder="摘要" @update:model-value="(v: string) => emit('update', row, 'description', v)" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="支出凭单" align="center" class-name="col-doc">
        <el-table-column label="凭单编号" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.documentNo" size="small" placeholder="编号" @update:model-value="(v: string) => emit('update', row, 'documentNo', v)" />
            <span v-else>{{ row.documentNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭单日期" min-width="130">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" :model-value="row.documentDate" type="date" size="small" value-format="YYYY-MM-DD" placeholder="单据日期" style="width:100%" @update:model-value="(v: string) => emit('update', row, 'documentDate', v)" />
            <span v-else>{{ row.documentDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.documentAmount" size="small" :controls="false" :precision="2" style="width:100%" @change="(v: number | undefined) => emit('update', row, 'documentAmount', v)" />
            <span v-else>{{ fmtAmount(row.documentAmount) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
    </template>

    <el-table-column label="是否跨期" width="100" align="center">
      <template #default="{ row }">
        <el-tag :type="row.isCrossPeriod ? 'danger' : 'success'" size="small">
          {{ row.conclusion || (row.isCrossPeriod ? '跨期' : '正常') }}
        </el-tag>
      </template>
    </el-table-column>
    <el-table-column label="跨期金额" min-width="110" align="right">
      <template #default="{ row }">
        <span :class="{ 'text-danger': row.isCrossPeriod }">{{ fmtAmount(row.crossPeriodAmount) }}</span>
      </template>
    </el-table-column>
    <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
      <template #default="{ row }">
        <el-button size="small" type="danger" text @click="emit('remove', row)">删</el-button>
      </template>
    </el-table-column>
  </el-table>
</template>

<script setup lang="ts">
import type { CutoffRow, CutoffDirection } from '../../composables/useI2Cutoff'

defineProps<{
  rows: CutoffRow[]
  direction: CutoffDirection
  isReadonly?: boolean
}>()

const emit = defineEmits<{
  update: [row: CutoffRow, field: string, value: any]
  remove: [row: CutoffRow]
}>()

function rowClassName({ row }: { row: CutoffRow }) {
  return row.isCrossPeriod ? 'cross-period-row' : ''
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.cutoff-table { font-size: var(--wp-font-size, 13px); }
.cutoff-table :deep(.col-doc .el-table__cell) { background-color: #f0faf0 !important; }
.cutoff-table :deep(.col-voucher .el-table__cell) { background-color: #f0f5ff !important; }
.text-danger { color: #dc2626; font-weight: 600; }
:deep(.cross-period-row) { background-color: #fef2f2 !important; }
:deep(.cross-period-row:hover > td) { background-color: #fee2e2 !important; }
</style>
