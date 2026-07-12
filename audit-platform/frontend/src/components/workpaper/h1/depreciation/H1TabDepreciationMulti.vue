<template>
  <div class="h1-tab-dep-multi">
    <div class="branch-selector">
      <el-segmented v-model="depBranch" :options="branchOptions" />
      <span class="branch-hint">当前: 多次减值（94公式）— 多个减值时点/各段剩余年限</span>
    </div>

    <div class="methodology-context">
      <p>多次减值折旧: 资产在使用期间发生多次减值，每次减值后均以新基数和新剩余年限重新计算月折旧。每段折旧独立累计。</p>
    </div>

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-12(C) 折旧测算-多次减值</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('depreciation-summary')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-12-C')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="rows" border stripe size="small" max-height="420" class="dep-table">
        <el-table-column type="index" width="35" fixed />
        <el-table-column prop="category" label="分类" width="80" fixed />
        <el-table-column prop="originalCost" label="原值" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="usefulLife" label="原年限" width="55" align="right" />
        <el-table-column label="减值次数" width="70" align="center">
          <template #default="{ row }"><span>{{ row.impairmentEvents?.length ?? 0 }}</span></template>
        </el-table-column>
        <el-table-column label="累计减值" width="100" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(totalImpairment(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当前月折旧" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="最近一次减值后的月折旧">{{ fmtAmt(row.monthlyDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="m in 12" :key="m" :label="`${m}月`" width="75" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.monthly?.[m-1] ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期合计" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.periodTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookDepreciation" label="账面" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookDepreciation) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 减值事件时间线（展开区） -->
      <div class="impairment-timeline" v-if="selectedRow">
        <h4>{{ selectedRow.category }} 减值事件时间线</h4>
        <el-timeline>
          <el-timeline-item v-for="(evt, idx) in selectedRow.impairmentEvents" :key="idx" :timestamp="evt.eventDate" placement="top">
            <el-card shadow="never" class="timeline-card">
              <p>减值金额: <b>{{ fmtAmt(evt.amount) }}</b> | 剩余年限: {{ evt.remainingLife }}年 | 新月折旧: <b class="formula-cell">{{ fmtAmt(evt.newMonthlyDep) }}</b></p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
      </div>

      <div class="totals-bar">
        <span>测算合计: <b class="amount-cell">{{ fmtAmt(summary.calculatedTotal) }}</b></span>
        <span>差异合计: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.totalDifference) > 0.01 }]">{{ fmtAmt(summary.totalDifference) }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>审计说明</span></template>
      <el-input v-model="depNote" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>每次减值后重新计算：新基数=(原值-累计折旧-累计减值)×(1-残值率)÷剩余年限÷12</li>
        <li>点击行可查看减值事件时间线</li>
        <li>固定资产减值一经计提不得转回(CAS8)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Depreciation, type DepreciationBranch, type DepreciationRow } from '../../composables/useH1Depreciation'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const depNote = ref('')
const selectedRow = ref<DepreciationRow | null>(null)
const depBranch = ref<DepreciationBranch>('C')
const branchOptions = [
  { label: '不含减值-直线法', value: 'A' },
  { label: '含减值', value: 'B' },
  { label: '多次减值', value: 'C' },
]
const { rows, summary } = useH1Depreciation(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

function totalImpairment(row: DepreciationRow): number {
  return (row.impairmentEvents ?? []).reduce((sum, e) => sum + (e.amount || 0), 0)
}
function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-dep-multi { padding: 16px; font-size: var(--wp-font-size, 13px); }
.branch-selector { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.branch-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.dep-table { font-size: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.impairment-timeline { margin-top: 16px; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.impairment-timeline h4 { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.timeline-card { font-size: 12px; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
