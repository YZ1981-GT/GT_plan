<script setup lang="ts">
/**
 * VoucherKeyCandidates.vue — 凭证穿透命中多张凭证时的候选清单（spec voucher-identity-writeback-and-audit-phase 需求 2.1）
 *
 * 凭证号单独不唯一，同日同号也不唯一（四川物流 2025-01-07 的 FY-0003 与 ZZ-0003 是两张凭证）。
 * 后端遇到这种情况回 409 + 候选，不合并分录；这里列出候选，用户选一张再穿透。
 */
import { fmtAmount } from '@/utils/formatters'
import type { VoucherKeyCandidate } from '@/utils/voucherIdentity'

defineProps<{
  candidates: VoucherKeyCandidate[]
  message?: string
  truncated?: boolean
}>()

const emit = defineEmits<{ (e: 'pick', candidate: VoucherKeyCandidate): void }>()
</script>

<template>
  <section class="gt-voucher-candidates" aria-label="同号凭证候选">
    <el-alert
      type="warning"
      :closable="false"
      show-icon
      :title="message || '该凭证号对应多张凭证，请选择一张查看'"
      :description="truncated ? `只列出了前 ${candidates.length} 张，可回到明细账双击具体分录定位。` : ''"
    />
    <el-table :data="candidates" border size="small" class="gt-voucher-candidates__table">
      <el-table-column prop="voucher_date" label="凭证日期" width="110" />
      <el-table-column label="凭证字" width="90">
        <template #default="{ row }">{{ row.voucher_type || '（空）' }}</template>
      </el-table-column>
      <el-table-column prop="voucher_no" label="凭证号" width="100" />
      <el-table-column prop="company_code" label="主体" min-width="160" show-overflow-tooltip />
      <el-table-column prop="line_count" label="分录数" width="80" align="right" />
      <el-table-column label="借方合计" width="140" align="right">
        <template #default="{ row }">{{ fmtAmount(row.debit_total, 2, true) }}</template>
      </el-table-column>
      <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
      <el-table-column label="操作" width="80" fixed="right">
        <template #default="{ row }">
          <el-button
            size="small"
            link
            type="primary"
            :aria-label="`查看 ${row.voucher_date} ${row.voucher_type || ''}${row.voucher_no} 号凭证`"
            @click="emit('pick', row)"
          >查看</el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<style scoped>
.gt-voucher-candidates {
  margin-bottom: 12px;
}
.gt-voucher-candidates__table {
  width: 100%;
  margin-top: 8px;
}
</style>
