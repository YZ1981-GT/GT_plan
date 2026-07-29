<script setup lang="ts">
/**
 * GtAdjudicationSourcePanel — 审定表四表取数来源面板（共享版）
 *
 * 展示后端 adjudication_prefill 的来源科目+公式+金额，供审计师追溯取数逻辑。
 * 挂各循环审定表 Tab 顶部，el-collapse 默认收起。
 *
 * 损益类：借方发生额/贷方发生额/净发生额
 * 余额类：期初余额/期末余额
 */
import { computed } from 'vue'

interface SourceRow {
  name: string
  code?: string
  // 损益类
  unadjustedDebit?: number
  unadjustedCredit?: number
  // 余额类
  opening_balance?: number
  closing_balance?: number
}

const props = defineProps<{
  prefill: SourceRow[]
  /** 科目编码前缀（如 6602/2241） */
  accountPrefix: string
  /** 'income'=损益取发生额 / 'balance'=余额取期初期末 */
  mode: 'income' | 'balance'
  /** 方向 debit=借方科目(借-贷) / credit=贷方科目(贷-借) */
  direction?: 'debit' | 'credit'
}>()

const formula = computed(() => {
  if (props.mode === 'balance') return `ABS(TB('${props.accountPrefix}子科目','期末余额'))`
  if (props.direction === 'credit') return `TB('${props.accountPrefix}子科目','贷方发生额') − TB('${props.accountPrefix}子科目','借方发生额')`
  return `TB('${props.accountPrefix}子科目','借方发生额') − TB('${props.accountPrefix}子科目','贷方发生额')`
})

const total = computed(() => {
  if (!props.prefill?.length) return 0
  return props.prefill.reduce((s, r) => {
    if (props.mode === 'balance') return s + (r.closing_balance ?? 0)
    if (props.direction === 'credit') return s + ((r.unadjustedCredit ?? 0) - (r.unadjustedDebit ?? 0))
    return s + ((r.unadjustedDebit ?? 0) - (r.unadjustedCredit ?? 0))
  }, 0)
})

function fmt(v: number | undefined): string {
  if (v === undefined || v === null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <el-collapse v-if="prefill && prefill.length > 0" class="gt-source-panel">
    <el-collapse-item title="🔗 四表取数来源（公式管理）" name="source">
      <div class="source-meta">
        <span class="source-formula">{{ formula }}</span>
        <el-tag size="small" type="info">{{ prefill.length }} 个子科目</el-tag>
        <el-tag size="small" type="success">合计 {{ fmt(total) }}</el-tag>
      </div>
      <el-table :data="prefill" size="small" border max-height="200" class="source-table">
        <el-table-column prop="name" label="科目名称" min-width="160" />
        <el-table-column v-if="mode === 'income'" label="借方发生" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.unadjustedDebit) }}</template>
        </el-table-column>
        <el-table-column v-if="mode === 'income'" label="贷方发生" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.unadjustedCredit) }}</template>
        </el-table-column>
        <el-table-column v-if="mode === 'balance'" label="期初余额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column v-if="mode === 'balance'" label="期末余额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>
    </el-collapse-item>
  </el-collapse>
</template>

<style scoped>
.gt-source-panel { margin-bottom: 12px; }
.gt-source-panel :deep(.el-collapse-item__header) { font-size: 13px; color: #409eff; font-weight: 500; }
.gt-source-panel :deep(.el-collapse-item__content) { padding: 8px 0 0; }
.source-meta { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; font-size: 12px; }
.source-formula { font-family: 'Courier New', monospace; color: #606266; background: #f5f7fa; padding: 2px 8px; border-radius: 3px; }
.source-table { font-size: 12px; }
.source-table :deep(.el-table__cell) { padding: 2px 4px; }
</style>
