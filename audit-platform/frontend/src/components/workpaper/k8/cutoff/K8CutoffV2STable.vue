<template>
  <el-table :data="rows" border size="small" class="cutoff-v2s-table" :row-class-name="rowClass">
    <el-table-column type="index" label="#" width="42" align="center" fixed />

    <!-- 记账凭证组（源 B/C/D/E/F 列，K8-6 记账凭证在前） -->
    <el-table-column label="记账凭证" align="center">
      <el-table-column label="日期" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.bookDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => emit('update', row.rowKey, 'bookDate', v)" />
          <span v-else>{{ row.bookDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证编号" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.voucherNo" size="small" @change="(v: string) => emit('update', row.rowKey, 'voucherNo', v)" />
          <span v-else>{{ row.voucherNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="业务内容" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.businessContent" size="small" @change="(v: string) => emit('update', row.rowKey, 'businessContent', v)" />
          <span v-else>{{ row.businessContent || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="对方科目" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.offsetAccount" size="small" @change="(v: string) => emit('update', row.rowKey, 'offsetAccount', v)" />
          <span v-else>{{ row.offsetAccount || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false" :precision="2" style="width:100%" :class="{ 'mismatch-input': row.amountMismatch }" @change="(v: number | undefined) => emit('update', row.rowKey, 'amount', v ?? 0)" />
          <span v-else :class="{ 'mismatch-cell': row.amountMismatch }">{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>
    </el-table-column>

    <!-- 支出凭单组（源 G/H/I 列，K8-6 支出凭单在后） -->
    <el-table-column label="支出凭单/原始凭证" align="center">
      <el-table-column label="凭单编号" min-width="110">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.sourceVoucherNo" size="small" @change="(v: string) => emit('update', row.rowKey, 'sourceVoucherNo', v)" />
          <span v-else>{{ row.sourceVoucherNo || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭单日期" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.sourceDate" type="date" size="small" value-format="YYYY-MM-DD" style="width:100%" @change="(v: string) => emit('update', row.rowKey, 'sourceDate', v)" />
          <span v-else>{{ row.sourceDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.sourceAmount" size="small" :controls="false" :precision="2" style="width:100%" :class="{ 'mismatch-input': row.amountMismatch }" @change="(v: number | undefined) => emit('update', row.rowKey, 'sourceAmount', v ?? 0)" />
          <span v-else :class="{ 'mismatch-cell': row.amountMismatch }">{{ fmtAmt(row.sourceAmount) }}</span>
        </template>
      </el-table-column>
    </el-table-column>

    <el-table-column label="是否跨期" width="82" align="center">
      <template #default="{ row }">
        <el-tag :type="row.isCross ? 'danger' : 'success'" size="small">{{ row.isCross ? '跨期' : '正常' }}</el-tag>
      </template>
    </el-table-column>
    <el-table-column label="跨期金额" width="110" align="right">
      <template #default="{ row }">
        <span :class="{ 'mismatch-cell': row.crossAmount > 0 }">{{ row.crossAmount > 0 ? fmtAmt(row.crossAmount) : '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="结论" width="100">
      <template #default="{ row }">
        <el-select v-if="!isReadonly" :model-value="row.conclusion" size="small" @change="(v: string) => emit('update', row.rowKey, 'conclusion', v)">
          <el-option value="正常" label="正常" />
          <el-option value="跨期" label="跨期" />
          <el-option value="需调整" label="需调整" />
        </el-select>
        <span v-else>{{ row.conclusion || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column label="备注" min-width="100">
      <template #default="{ row }">
        <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => emit('update', row.rowKey, 'remark', v)" />
        <span v-else>{{ row.remark || '-' }}</span>
      </template>
    </el-table-column>
    <el-table-column v-if="!isReadonly" label="操作" width="52" align="center" fixed="right">
      <template #default="{ row }">
        <el-button link size="small" type="danger" @click="emit('remove', row.rowKey)">删</el-button>
      </template>
    </el-table-column>

    <template #empty>
      <span class="empty-hint">暂无样本，点击上方「新增/自动抽样/截止自动提取/抽凭」添加</span>
    </template>
  </el-table>
</template>

<script setup lang="ts">
/**
 * K8CutoffV2STable — K8-6 截止测试单段表格（记账凭证 → 支出凭单 双组列）
 * 供 K8TabCutoffV2S 的「资产负债表日前 / 日后」两段复用（记账凭证在前，与源模板 K8-6 一致）。
 */
import type { K8CutoffRow } from '@/components/workpaper/composables/useK8Cutoff'

defineProps<{
  rows: K8CutoffRow[]
  isReadonly: boolean
  fmtAmt: (v: number | null | undefined) => string
}>()

const emit = defineEmits<{
  (e: 'update', rowKey: string, field: string, value: any): void
  (e: 'remove', rowKey: string): void
}>()

function rowClass({ row }: { row: K8CutoffRow }): string {
  if (row.isCross) return 'cross-period-row'
  if (row.amountMismatch) return 'mismatch-row'
  return ''
}
</script>

<style scoped>
.cutoff-v2s-table { font-size: var(--wp-font-size, 13px); margin-bottom: 4px; }
.cutoff-v2s-table :deep(.cross-period-row td) { background-color: #fef2f2 !important; }
.cutoff-v2s-table :deep(.mismatch-row td) { background-color: #fff7ed !important; }
.mismatch-cell { color: #dc2626; font-weight: 600; }
.mismatch-input :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.empty-hint { font-size: 12px; color: var(--el-text-color-placeholder); }
</style>
