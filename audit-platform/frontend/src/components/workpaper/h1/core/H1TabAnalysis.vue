<template>
  <div class="h1-tab-analysis">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>分析性程序：对固定资产结构占比及期间变动进行量化分析，识别异常波动项目并追踪原因。重点关注变动率超过阈值(±20%)的分类。</p>
    </div>

    <!-- 区域1: 结构分析 -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>一、结构分析（各类占比）</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('analysis-change')">
              <el-icon><MagicStick /></el-icon> AI分析
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-6-struct')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="structureRows" border stripe size="small">
        <el-table-column prop="category" label="资产分类" min-width="120" />
        <el-table-column prop="costEnd" label="原值期末" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.costEnd) }}</span></template>
        </el-table-column>
        <el-table-column label="占比%" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="占比=本项原值÷原值合计×100%">{{ row.proportion != null ? row.proportion.toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.netValue) }}</span></template>
        </el-table-column>
        <el-table-column label="成新率%" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="成新率=净值÷原值×100%">{{ row.newRate != null ? row.newRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 区域2: 变动分析 -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>二、变动分析（期间增减）</span>
        </div>
      </template>
      <el-table :data="changeRows" border stripe size="small">
        <el-table-column prop="category" label="资产分类" min-width="120" />
        <el-table-column prop="priorEnd" label="上期期末" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.priorEnd) }}</span></template>
        </el-table-column>
        <el-table-column prop="currentEnd" label="本期期末" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.currentEnd) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="变动率%" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isAbnormal(row.changeRate) }]" title="变动率=(本期-上期)÷上期×100%">
              {{ row.changeRate != null ? row.changeRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="explanation" label="变动原因" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.explanation" size="small" placeholder="变动原因说明..." @change="onExplanationChange(row)" />
            <span v-else>{{ row.explanation }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="hasAbnormal" type="warning" :closable="false" show-icon class="alert-abnormal">
        存在变动率超过±20%的异常项，请补充变动原因说明
      </el-alert>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>分析性程序结论</span></template>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" :disabled="isReadonly" placeholder="分析性程序总体结论..." />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>结构分析：各分类占比（公式自动），关注占比>50%的重大项目</li>
        <li>成新率 = 净值 ÷ 原值，反映资产新旧程度</li>
        <li>变动分析：超±20%标红提示，需补充说明</li>
        <li>数据自动从H1-2明细表交叉取数</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Analysis } from '../../composables/useH1Analysis'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const conclusion = ref('')

const { structureRows, changeRows } = useH1Analysis(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
)

const hasAbnormal = computed(() => changeRows.value.some((r: any) => isAbnormal(r.changeRate)))

function isAbnormal(rate: number | null): boolean {
  return rate != null && Math.abs(rate) > 20
}

function onExplanationChange(_row: any) { /* debounce save */ }
function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context {
  border-left: 3px solid var(--el-color-warning); background: #fffbe6;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px;
}
.analysis-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.alert-abnormal { margin-top: 12px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
