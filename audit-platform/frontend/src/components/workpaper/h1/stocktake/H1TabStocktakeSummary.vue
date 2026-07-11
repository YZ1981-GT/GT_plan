<template>
  <div class="h1-tab-stocktake-summary">
    <!-- 仪表板 -->
    <el-card shadow="never" class="dashboard-card">
      <template #header>
        <div class="section-title">
          <span>H1-11 监盘小结</span>
          <div class="title-actions">
            <el-button size="small" type="primary" link @click="handleAiGenerate('stocktake-summary')">
              <el-icon><MagicStick /></el-icon> AI总结
            </el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-11')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-row :gutter="16">
        <el-col :span="6">
          <div class="stat-box"><div class="stat-label">盘点总数</div><div class="stat-value">{{ stats.totalCount }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box success"><div class="stat-label">账实相符</div><div class="stat-value">{{ stats.matchCount }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box warning"><div class="stat-label">盘盈</div><div class="stat-value">{{ stats.surplusCount }}</div></div>
        </el-col>
        <el-col :span="6">
          <div class="stat-box danger"><div class="stat-label">盘亏</div><div class="stat-value">{{ stats.shortageCount }}</div></div>
        </el-col>
      </el-row>
      <div class="match-rate-bar">
        <span>账实相符率: </span>
        <el-progress :percentage="stats.matchRate" :stroke-width="14" :format="() => stats.matchRate + '%'" style="flex:1" />
      </div>
    </el-card>

    <!-- 盘盈表 -->
    <el-card shadow="never" v-if="surplusRows.length" class="detail-card">
      <template #header><span>盘盈明细（{{ surplusRows.length }} 项）</span></template>
      <el-table :data="surplusRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="name" label="资产名称" min-width="120" />
        <el-table-column prop="diffAmount" label="盘盈金额" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.diffAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="diffReason" label="原因" min-width="180" />
        <el-table-column prop="suggestion" label="处理建议" min-width="150" />
      </el-table>
    </el-card>

    <!-- 盘亏表 -->
    <el-card shadow="never" v-if="shortageRows.length" class="detail-card">
      <template #header><span>盘亏明细（{{ shortageRows.length }} 项）</span></template>
      <el-table :data="shortageRows" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="name" label="资产名称" min-width="120" />
        <el-table-column prop="diffAmount" label="盘亏金额" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell error-amount">{{ fmtAmt(row.diffAmount) }}</span></template>
        </el-table-column>
        <el-table-column prop="diffReason" label="原因" min-width="180" />
        <el-table-column prop="suggestion" label="处理建议" min-width="150" />
      </el-table>
    </el-card>

    <!-- 监盘结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>监盘总结与审计结论</span></template>
      <el-input v-model="summaryConclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly"
        placeholder="总结盘点结果、异常情况及审计结论..." />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>仪表板数据自动从H1-10汇总</li>
        <li>盘亏需评估是否影响固定资产余额的真实性</li>
        <li>账实相符率低于95%需进一步追查原因</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { useH1Stocktake } from '../../composables/useH1Stocktake'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const summaryConclusion = ref('')
const state = useH1Stocktake(toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any)

const stats = computed(() => ({
  totalCount: state.statistics.value.totalChecked,
  matchCount: state.statistics.value.matchCount,
  surplusCount: state.statistics.value.surplusCount,
  shortageCount: state.statistics.value.deficitCount,
  matchRate: Math.round(state.statistics.value.matchRate),
}))

const surplusRows = computed(() => state.surplusRows.value)
const shortageRows = computed(() => state.deficitRows.value)

function handleAiGenerate(section: string) { console.log('AI:', section) }
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-stocktake-summary { padding: 16px; font-size: 13px; }
.dashboard-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.title-actions { display: flex; gap: 8px; }
.stat-box { text-align: center; padding: 12px; border-radius: 6px; background: var(--el-fill-color-light); }
.stat-box.success { background: var(--el-color-success-light-9); }
.stat-box.warning { background: var(--el-color-warning-light-9); }
.stat-box.danger { background: var(--el-color-danger-light-9); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value { font-size: 24px; font-weight: 700; margin-top: 4px; }
.match-rate-bar { display: flex; align-items: center; gap: 12px; margin-top: 16px; }
.detail-card { margin-bottom: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
