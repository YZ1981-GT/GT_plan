<script setup lang="ts">
/**
 * A15 持续经营 — 程序表 | 财务指标卡片 + A15-1 核对表
 *
 * 增强：A15-1 Tab 顶部显示从 TB 自动计算的关键财务指标。
 */
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import GtAProgramConsole from './GtAProgramConsole.vue'
import GtEmbeddedChecklist from './GtEmbeddedChecklist.vue'

defineProps<{
  wpId: string
  readonly?: boolean
}>()

const route = useRoute()
const active = ref('program')

// ─── 财务指标 ───
interface FinancialRatios {
  current_ratio: number | null
  quick_ratio: number | null
  debt_ratio: number | null
  net_assets: number
  retained_earnings: number
  current_assets: number
  current_liabilities: number
  total_assets: number
  total_liabilities: number
}

const ratios = ref<FinancialRatios | null>(null)
const riskLevel = ref<string>('undetermined')
const ratioLoading = ref(false)

async function loadRatios() {
  const projectId = route.params.projectId as string
  const year = route.params.year as string
  if (!projectId || !year) return
  ratioLoading.value = true
  try {
    const data = await api.get(`/api/projects/${projectId}/auto-data/a15_financial_ratios`, {
      params: { year },
      _silent: true,
    } as any) as any
    if (data && !data._error) {
      ratios.value = data.ratios
      riskLevel.value = data.risk_level || 'undetermined'
    }
  } catch {
    // silent — TB 可能未导入
  } finally {
    ratioLoading.value = false
  }
}

function riskColor(level: string): string {
  const map: Record<string, string> = {
    low: 'var(--el-color-success)',
    medium: 'var(--el-color-warning)',
    high: 'var(--el-color-danger)',
    undetermined: 'var(--el-color-info)',
  }
  return map[level] || map.undetermined
}

function riskLabel(level: string): string {
  const map: Record<string, string> = {
    low: '低风险',
    medium: '中等风险',
    high: '高风险',
    undetermined: '待评估',
  }
  return map[level] || '待评估'
}

function fmtRatio(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toFixed(2)
}

function fmtPercent(v: number | null | undefined): string {
  if (v == null) return '—'
  return (v * 100).toFixed(1) + '%'
}

function fmtAmount(v: number | null | undefined): string {
  if (v == null) return '—'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

onMounted(loadRatios)
</script>

<template>
  <div class="a15-bundle">
    <el-tabs v-model="active">
      <el-tab-pane label="审计程序" name="program">
        <GtAProgramConsole :wp-id="wpId" :embedded="true" />
      </el-tab-pane>
      <el-tab-pane label="A15-1 持续经营调查表" name="A15-1">
        <!-- 财务指标卡片 -->
        <div v-loading="ratioLoading" class="a15-ratio-panel">
          <div class="a15-ratio-header">
            <span class="a15-ratio-title">财务指标（自动取数）</span>
            <el-tag :color="riskColor(riskLevel)" effect="dark" size="small" style="border:none;color:#fff">
              {{ riskLabel(riskLevel) }}
            </el-tag>
          </div>
          <div v-if="ratios" class="a15-ratio-grid">
            <div class="a15-ratio-item">
              <span class="a15-ratio-label">流动比率</span>
              <span class="a15-ratio-value">{{ fmtRatio(ratios.current_ratio) }}</span>
            </div>
            <div class="a15-ratio-item">
              <span class="a15-ratio-label">速动比率</span>
              <span class="a15-ratio-value">{{ fmtRatio(ratios.quick_ratio) }}</span>
            </div>
            <div class="a15-ratio-item">
              <span class="a15-ratio-label">资产负债率</span>
              <span class="a15-ratio-value">{{ fmtPercent(ratios.debt_ratio) }}</span>
            </div>
            <div class="a15-ratio-item">
              <span class="a15-ratio-label">净资产</span>
              <span class="a15-ratio-value">{{ fmtAmount(ratios.net_assets) }}</span>
            </div>
            <div class="a15-ratio-item">
              <span class="a15-ratio-label">累计未分配利润</span>
              <span class="a15-ratio-value">{{ fmtAmount(ratios.retained_earnings) }}</span>
            </div>
          </div>
          <div v-else-if="!ratioLoading" class="a15-ratio-empty">
            试算表暂无数据，指标将在余额表导入后自动计算
          </div>
        </div>

        <!-- 核对表 -->
        <GtEmbeddedChecklist :wp-id="wpId" checklist-wp-code="A15-1" :readonly="readonly" />
      </el-tab-pane>
    </el-tabs>
  </div>
</template>

<style scoped>
.a15-ratio-panel {
  margin-bottom: 16px;
  padding: 12px 16px;
  background: var(--el-fill-color-lighter, #f5f7fa);
  border-radius: 8px;
  border: 1px solid var(--el-border-color-lighter, #e4e7ed);
}
.a15-ratio-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.a15-ratio-title {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.a15-ratio-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 12px;
}
.a15-ratio-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.a15-ratio-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.a15-ratio-value {
  font-size: 16px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  font-variant-numeric: tabular-nums;
}
.a15-ratio-empty {
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  text-align: center;
  padding: 8px 0;
}
</style>
