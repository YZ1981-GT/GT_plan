<template>
  <div class="c24-trial-balance">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <div class="methodology-bar" />
      <p>C24-2 完整性测试 — 分录&余额表对比：按科目汇总分录借贷金额，与试算平衡表核对，识别差异科目。</p>
    </div>

    <!-- 对比结果表 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">科目余额对比</span>
        <span class="unit-label">单位：元</span>
      </div>
      <el-table :data="comparisons" border size="small" class="c24-table" max-height="500" empty-text="暂无对比数据（需先导入分录+试算表）">
        <el-table-column label="科目编码" prop="account" width="100" />
        <el-table-column label="科目名称" prop="accountName" min-width="120" />
        <el-table-column label="分录借方汇总" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：按科目Σ借">{{ fmtAmount(row.jeDebitSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分录贷方汇总" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：按科目Σ贷">{{ fmtAmount(row.jeCreditSum) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分录净额" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="来源：借-贷">{{ fmtAmount(row.jeNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="余额表借方" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="来源：试算表取数">{{ fmtAmount(row.tbDebit) }}</span></template>
        </el-table-column>
        <el-table-column label="余额表贷方" min-width="110" align="right">
          <template #default="{ row }"><span class="formula-cell" title="来源：试算表取数">{{ fmtAmount(row.tbCredit) }}</span></template>
        </el-table-column>
        <el-table-column label="余额表净额" min-width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="来源：TB借-贷">{{ fmtAmount(row.tbNet) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'text-danger': Math.abs(row.diff) > 0.01 }" title="来源：分录净额 - 余额表净额">
              {{ fmtAmountWithZero(row.diff) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </section>

    <!-- 测试结论 -->
    <section class="c24-section">
      <div class="section-header">
        <span class="section-title">测试结论</span>
        <el-button v-if="!isReadonly" size="small" @click="$emit('ai-suggest', 'C24-2-conclusion')">AI 辅助</el-button>
      </div>
      <el-input
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        :model-value="conclusion"
        :disabled="isReadonly"
        placeholder="请填写分录余额对比测试结论"
        @input="$emit('update:conclusion', $event)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import type { TrialBalanceComparison } from '@/composables/useC24AnalyticsEngine'
import { fmtAmount, fmtAmountWithZero } from '@/utils/formatters'

defineProps<{
  comparisons: TrialBalanceComparison[]
  conclusion: string
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'update:conclusion', val: string): void
  (e: 'ai-suggest', fieldId: string): void
}>()
</script>

<style scoped>
.c24-trial-balance { font-size: var(--wp-font-size, 13px); }
.methodology-context { display: flex; gap: 10px; align-items: flex-start; padding: 10px 12px; margin-bottom: 16px; background: #fffbf0; border-radius: 4px; }
.methodology-bar { width: 3px; min-height: 20px; align-self: stretch; background: #e6a23c; border-radius: 2px; flex-shrink: 0; }
.methodology-context p { margin: 0; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.c24-section { margin-bottom: 20px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.section-title { font-weight: 600; font-size: 14px; color: #303133; }
.c24-table { font-size: var(--wp-font-size, 13px); }
.c24-table :deep(.el-table__header th),
.c24-table :deep(.el-table__body td),
.c24-table :deep(.cell) { font-size: var(--wp-font-size, 13px); }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #409eff; }
.text-danger { color: #f56c6c !important; }
.unit-label { font-size: 12px; color: #909399; font-weight: normal; }
</style>
