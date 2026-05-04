<template>
  <div class="gt-t-account">
    <div class="gt-t-header">
      <span class="gt-t-name">{{ accountName || '科目名称' }}</span>
      <el-tag size="small" v-if="accountCode">{{ accountCode }}</el-tag>
    </div>

    <!-- T型账户可视化 -->
    <div class="gt-t-shape">
      <!-- 期初余额 -->
      <div class="gt-t-opening">
        <span class="gt-t-label">期初余额</span>
        <span class="gt-t-amount">{{ fmtAmt(openingBalance) }}</span>
      </div>

      <!-- T型主体 -->
      <div class="gt-t-body">
        <div class="gt-t-left">
          <div class="gt-t-side-header">借方</div>
          <div class="gt-t-entries">
            <div v-for="(entry, i) in debitEntries" :key="i" class="gt-t-entry">
              <span class="gt-t-entry-desc">{{ entry.description }}</span>
              <span class="gt-t-entry-amt">{{ fmtAmt(entry.amount) }}</span>
            </div>
          </div>
          <div class="gt-t-subtotal">
            <span>借方合计</span>
            <span>{{ fmtAmt(debitTotal) }}</span>
          </div>
        </div>
        <div class="gt-t-divider" />
        <div class="gt-t-right">
          <div class="gt-t-side-header">贷方</div>
          <div class="gt-t-entries">
            <div v-for="(entry, i) in creditEntries" :key="i" class="gt-t-entry">
              <span class="gt-t-entry-desc">{{ entry.description }}</span>
              <span class="gt-t-entry-amt">{{ fmtAmt(entry.amount) }}</span>
            </div>
          </div>
          <div class="gt-t-subtotal">
            <span>贷方合计</span>
            <span>{{ fmtAmt(creditTotal) }}</span>
          </div>
        </div>
      </div>

      <!-- 净变动 -->
      <div class="gt-t-net">
        <span class="gt-t-label">净变动</span>
        <span class="gt-t-amount" :class="{ 'gt-t-negative': netChange < 0 }">{{ fmtAmt(netChange) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { fmtAmount } from '@/utils/formatters'

interface TEntry {
  side: 'debit' | 'credit'
  amount: number
  description: string
  counterpart_account?: string
}

const props = withDefaults(defineProps<{
  accountName?: string
  accountCode?: string
  openingBalance?: number
  entries?: TEntry[]
}>(), {
  openingBalance: 0,
  entries: () => [],
})

const debitEntries = computed(() => props.entries.filter(e => e.side === 'debit'))
const creditEntries = computed(() => props.entries.filter(e => e.side === 'credit'))
const debitTotal = computed(() => debitEntries.value.reduce((s, e) => s + (e.amount || 0), 0))
const creditTotal = computed(() => creditEntries.value.reduce((s, e) => s + (e.amount || 0), 0))
const netChange = computed(() => debitTotal.value - creditTotal.value)

const fmtAmt = fmtAmount
</script>

<style scoped>
.gt-t-account {
  border: 1px solid var(--gt-color-border);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-4);
  background: var(--gt-color-bg-white);
}
.gt-t-header {
  display: flex; align-items: center; gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-3); padding-bottom: var(--gt-space-2);
  border-bottom: 2px solid var(--gt-color-primary);
}
.gt-t-name { font-weight: 600; font-size: var(--gt-font-size-lg); }
.gt-t-opening, .gt-t-net {
  display: flex; justify-content: space-between; align-items: center;
  padding: var(--gt-space-2) var(--gt-space-3);
  background: var(--gt-color-bg);
  border-radius: var(--gt-radius-sm);
  margin-bottom: var(--gt-space-2);
}
.gt-t-label { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); }
.gt-t-amount { font-weight: 600; font-size: var(--gt-font-size-base); }
.gt-t-negative { color: var(--gt-color-coral); }
.gt-t-body {
  display: grid; grid-template-columns: 1fr auto 1fr;
  min-height: 120px; margin: var(--gt-space-2) 0;
}
.gt-t-divider {
  width: 2px; background: var(--gt-color-primary);
  margin: 0 var(--gt-space-1);
}
.gt-t-left, .gt-t-right { display: flex; flex-direction: column; }
.gt-t-side-header {
  text-align: center; font-weight: 600; font-size: var(--gt-font-size-sm);
  padding: var(--gt-space-1); border-bottom: 1px solid var(--gt-color-border-light);
  color: var(--gt-color-primary);
}
.gt-t-entries { flex: 1; padding: var(--gt-space-2); }
.gt-t-entry {
  display: flex; justify-content: space-between; gap: var(--gt-space-2);
  padding: 2px 0; font-size: var(--gt-font-size-sm);
}
.gt-t-entry-desc { color: var(--gt-color-text-secondary); flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-t-entry-amt { font-variant-numeric: tabular-nums; white-space: nowrap; }
.gt-t-subtotal {
  display: flex; justify-content: space-between;
  padding: var(--gt-space-1) var(--gt-space-2);
  border-top: 1px solid var(--gt-color-border-light);
  font-size: var(--gt-font-size-sm); font-weight: 600;
}
</style>
