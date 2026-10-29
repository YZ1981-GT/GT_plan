<template>
  <section v-if="appendReport || voucherDiff" class="append-result">
    <el-alert
      v-if="appendReport"
      :type="appendReport.no_base ? 'info' : 'success'"
      :closable="false"
      show-icon
    >
      <template #title>
        {{ appendReport.no_base ? '这是首次导入，没有上一版本需要继承' : '增量追加已在新版本内完成' }}
      </template>
      <div v-if="!appendReport.no_base" class="append-lines">
        <div>策略：{{ appendReport.strategy === 'overwrite' ? '文件月份覆盖' : '重叠月份保留上一版本' }}</div>
        <div>文件月份：{{ monthList(appendReport.file_months) }}</div>
        <div>继承月份：{{ monthList(appendReport.inherited_months) }}</div>
        <div v-if="appendReport.skipped_months?.length">跳过文件月份：{{ monthList(appendReport.skipped_months) }}</div>
        <div v-if="appendReport.overwritten_months?.length">由文件替代的月份：{{ monthList(appendReport.overwritten_months) }}</div>
        <div v-if="snapshotTables.length">沿用上一版本：{{ snapshotTables.join('、') }}</div>
      </div>
    </el-alert>

    <el-alert
      v-if="appendReport?.balance_confirmation_required"
      class="balance-warning"
      type="warning"
      :closable="false"
      show-icon
      title="余额表未随新增月份更新，试算表仍为上一版本口径；本次已按用户确认留痕。"
    />

    <el-alert
      v-if="voucherDiff?.status === VOUCHER_DIFF_STATUS.FAILED"
      class="diff-block"
      type="warning"
      :closable="false"
      show-icon
      :title="`与上一版本的凭证差异报告未生成：${voucherDiff.reason || '未知原因'}`"
    />
    <div v-else-if="voucherDiff?.status === VOUCHER_DIFF_STATUS.OK" class="diff-block">
      <div class="diff-title">与上一版本的凭证差异</div>
      <div class="diff-grid">
        <div v-for="item in diffEntries" :key="item.key" class="diff-card">
          <strong>{{ item.label }}</strong>
          <span>{{ item.count.toLocaleString() }} 张</span>
          <span>涉及金额 {{ item.amount }}</span>
          <span>净变动 {{ item.netAmountChange }}</span>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import {
  carriedSnapshotTables,
  monthList,
  VOUCHER_DIFF_STATUS,
  voucherDiffEntries,
  type LedgerAppendReport,
  type VoucherDiffReport,
} from './ledgerAppendResult'

const props = defineProps<{
  appendReport?: LedgerAppendReport | null
  voucherDiff?: VoucherDiffReport | null
}>()

const snapshotTables = computed(() => carriedSnapshotTables(props.appendReport))
const diffEntries = computed(() => voucherDiffEntries(props.voucherDiff))
</script>

<style scoped>
.append-result {
  margin-top: var(--gt-space-4);
  text-align: left;
}

.append-lines {
  display: grid;
  gap: var(--gt-space-1);
  margin-top: var(--gt-space-2);
  font-size: var(--gt-font-size-sm);
  line-height: 1.7;
}

.balance-warning,
.diff-block {
  margin-top: var(--gt-space-3);
}

.diff-title {
  margin-bottom: var(--gt-space-2);
  color: var(--gt-color-text-primary);
  font-weight: 600;
}

.diff-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--gt-space-2);
}

.diff-card {
  display: grid;
  gap: var(--gt-space-1);
  padding: var(--gt-space-3);
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-md);
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
}

.diff-card strong {
  color: var(--gt-color-text-primary);
}
</style>
