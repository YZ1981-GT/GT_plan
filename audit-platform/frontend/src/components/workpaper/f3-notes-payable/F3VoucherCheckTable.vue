<script setup lang="ts">
/** F3VoucherCheckTable — F3-7 借/贷检查区表格（>50 行启用固定表头滚动） */
import { computed } from 'vue'
import type { F3VoucherCheckRow } from '../composables/useF3VoucherCheck'

const SCROLL_THRESHOLD = 50
const TABLE_MAX_HEIGHT = 480

const props = defineProps<{
  side: 'credit' | 'debit'
  rows: F3VoucherCheckRow[]
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'update-cell', rowId: string, field: string, value: unknown): void
  (e: 'remove-row', rowId: string): void
}>()

const useScroll = computed(() => props.rows.length > SCROLL_THRESHOLD)

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function onUpdate(field: string, rowId: string, value: unknown): void {
  emit('update-cell', rowId, field, value)
}
</script>

<template>
  <div class="f3-voucher-table-wrap">
    <div v-if="useScroll" class="scroll-hint">共 {{ rows.length }} 行 · 固定表头滚动</div>
    <el-table
      :data="rows"
      border
      size="small"
      style="font-size:13px"
      :max-height="useScroll ? TABLE_MAX_HEIGHT : undefined"
    >
      <el-table-column prop="seq" label="序号" width="55" fixed />
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-tooltip v-if="row.sampleSource" :content="`来自${row.sampleSource}`" placement="top">
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              @change="(v: string) => onUpdate('summary', row.rowId, v)"
            />
            <span v-else>{{ row.summary }}</span>
          </el-tooltip>
          <template v-else>
            <el-input
              v-if="!isReadonly"
              :model-value="row.summary"
              size="small"
              @change="(v: string) => onUpdate('summary', row.rowId, v)"
            />
            <span v-else>{{ row.summary }}</span>
          </template>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.counterAccount"
            size="small"
            @change="(v: string) => onUpdate('counterAccount', row.rowId, v)"
          />
          <span v-else>{{ row.counterAccount }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width:100%"
            @change="(v: number) => onUpdate('amount', row.rowId, v ?? 0)"
          />
          <span v-else>{{ fmt(row.amount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证日期" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherDate"
            size="small"
            @change="(v: string) => onUpdate('voucherDate', row.rowId, v)"
          />
          <span v-else>{{ row.voucherDate }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证号" width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.voucherNo"
            size="small"
            @change="(v: string) => onUpdate('voucherNo', row.rowId, v)"
          />
          <span v-else>{{ row.voucherNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审计结论" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.auditConclusion"
            size="small"
            @change="(v: string) => onUpdate('auditConclusion', row.rowId, v)"
          />
          <span v-else>{{ row.auditConclusion }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="emit('remove-row', row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.f3-voucher-table-wrap { margin-bottom: 8px; }
.f3-voucher-table-wrap :deep(.el-table) {
  --el-table-font-size: 13px;
  font-size: 13px;
}
.f3-voucher-table-wrap :deep(.el-table .cell) {
  font-size: 13px !important;
}
.scroll-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-bottom: 4px;
  text-align: right;
}
</style>
