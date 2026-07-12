<template>
  <div class="h1-tab-dep-straight">
    <!-- 分支选择器 -->
    <div class="branch-selector">
      <el-segmented v-model="depBranch" :options="branchOptions" />
      <span class="branch-hint">当前: 不含减值-直线法（28列/62公式）</span>
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>CAS4直线法: 月折旧 = 原值 × (1 - 残值率) ÷ 使用年限 ÷ 12。逐项计算1~12月折旧→累计→与账面对比→输出差异。不含减值影响版本。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-12(A) 折旧测算-不含减值直线法</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('depreciation-summary')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-12-A')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="500" class="dep-table">
        <el-table-column type="index" width="35" fixed />
        <el-table-column prop="category" label="分类" width="80" fixed />
        <el-table-column prop="originalCost" label="原值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="salvageRate" label="残值率%" width="70" align="right" />
        <el-table-column prop="usefulLife" label="年限" width="50" align="right" />
        <el-table-column label="月折旧" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="月折旧=原值×(1-残值率)÷年限÷12">{{ fmtAmt(row.monthlyDep) }}</span>
          </template>
        </el-table-column>
        <!-- 12个月列 -->
        <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :title="`第${m}月折旧`">{{ fmtAmt(row.monthly?.[m-1] ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期合计" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="SUM(1~12月)">{{ fmtAmt(row.periodTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="accDepBegin" label="折旧期初" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.accDepBegin) }}</span></template>
        </el-table-column>
        <el-table-column label="折旧期末" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+本期合计">{{ fmtAmt(row.accDepEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookDepreciation" label="账面折旧" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookDepreciation) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]" title="差异=测算-账面">
              {{ fmtAmt(row.difference) }}
            </span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="totals-bar">
        <span>测算折旧合计: <b class="amount-cell">{{ fmtAmt(summary.calculatedTotal) }}</b></span>
        <span>账面折旧合计: <b class="amount-cell">{{ fmtAmt(summary.bookTotal) }}</b></span>
        <span>差异合计: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.totalDifference) > 0.01 }]">{{ fmtAmt(summary.totalDifference) }}</b></span>
      </div>
    </el-card>

    <!-- 审计说明/结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>折旧测算审计说明</span></template>
      <el-input v-model="depNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly"
        placeholder="说明测算差异原因及审计结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>直线法月折旧 = 原值 × (1-残值率) ÷ 使用年限 ÷ 12</li>
        <li>12月列为月度折旧(通常相等)，处置月后为0</li>
        <li>差异=测算折旧-账面折旧，差异>0.01红色高亮</li>
        <li>如有减值情况请切换到"含减值"或"多次减值"分支</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Depreciation, type DepreciationBranch } from '../../composables/useH1Depreciation'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const depNote = ref('')

const depBranch = ref<DepreciationBranch>('A')
const branchOptions = [
  { label: '不含减值-直线法', value: 'A' },
  { label: '含减值', value: 'B' },
  { label: '多次减值', value: 'C' },
]

const { rows, summary } = useH1Depreciation(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-dep-straight { padding: 16px; font-size: var(--wp-font-size, 13px); }
.branch-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.branch-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.dep-table { font-size: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
