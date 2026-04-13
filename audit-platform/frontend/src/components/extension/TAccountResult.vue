<template>
  <el-card shadow="never" class="gt-t-result">
    <template #header><span class="gt-result-title">计算结果</span></template>
    <el-descriptions :column="2" size="small" border>
      <el-descriptions-item label="借方合计">{{ fmtAmt(result.debit_total) }}</el-descriptions-item>
      <el-descriptions-item label="贷方合计">{{ fmtAmt(result.credit_total) }}</el-descriptions-item>
      <el-descriptions-item label="净变动">
        <span :class="{ 'gt-negative': result.net_change < 0 }">{{ fmtAmt(result.net_change) }}</span>
      </el-descriptions-item>
      <el-descriptions-item label="期末余额">{{ fmtAmt(result.closing_balance) }}</el-descriptions-item>
    </el-descriptions>

    <div class="gt-reconciliation" v-if="result.reconciliation !== undefined">
      <div class="gt-recon-status" :class="result.reconciliation ? 'gt-recon-pass' : 'gt-recon-fail'">
        <el-icon :size="20">
          <CircleCheckFilled v-if="result.reconciliation" />
          <CircleCloseFilled v-else />
        </el-icon>
        <span>{{ result.reconciliation ? '资产负债表勾稽一致' : '资产负债表勾稽不一致' }}</span>
      </div>
      <div v-if="result.difference !== undefined && result.difference !== 0" class="gt-recon-diff">
        差异金额: {{ fmtAmt(result.difference) }}
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'

defineProps<{
  result: {
    debit_total: number
    credit_total: number
    net_change: number
    closing_balance: number
    reconciliation?: boolean
    difference?: number
  }
}>()

function fmtAmt(v: number | undefined): string {
  if (v === undefined || v === null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.gt-t-result { border-radius: var(--gt-radius-md); margin-top: var(--gt-space-3); }
.gt-result-title { font-weight: 600; }
.gt-negative { color: var(--gt-color-coral); }
.gt-reconciliation { margin-top: var(--gt-space-3); }
.gt-recon-status {
  display: flex; align-items: center; gap: var(--gt-space-2);
  padding: var(--gt-space-2) var(--gt-space-3);
  border-radius: var(--gt-radius-sm);
  font-weight: 600;
}
.gt-recon-pass { background: var(--gt-color-success-light); color: var(--gt-color-success); }
.gt-recon-fail { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.gt-recon-diff { margin-top: var(--gt-space-1); font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); padding-left: var(--gt-space-3); }
</style>
