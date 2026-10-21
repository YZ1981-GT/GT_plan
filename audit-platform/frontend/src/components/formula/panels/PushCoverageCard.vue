<!-- 推送覆盖率卡片（从 FormulaManagerDialog 提取；spec formula-settings-wiring-closure T11）。
     优化建议 #7：增加缺口明细展开、最近推送概要、状态分布。 -->
<template>
  <div v-if="coverage" class="gt-fm-coverage-section" style="margin-bottom: 12px; padding: 12px; background: var(--gt-bg-page, #fafafa); border-radius: 6px;">
    <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 8px;">
      <span style="font-size: 13px; font-weight: 600;">📤 推送覆盖率</span>
      <span :style="{ fontSize: '18px', fontWeight: 700, color: coverage.percentage >= 80 ? 'var(--gt-color-success)' : 'var(--gt-color-warning)' }">
        {{ coverage.percentage }}%
      </span>
      <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary);">
        （{{ coverage.total_registered }} / {{ coverage.total_codes }} 个底稿编码已接入）
      </span>
    </div>
    <el-progress :percentage="coverage.percentage" :stroke-width="8" :status="coverage.percentage >= 95 ? 'success' : ''" style="margin-bottom: 8px;" />

    <!-- 逐循环覆盖 -->
    <div style="display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px;">
      <div v-for="cy in coverage.cycles" :key="cy.cycle"
        style="display: flex; align-items: center; gap: 4px; font-size: 11px; padding: 2px 6px; border-radius: 4px; cursor: pointer;"
        :style="{ background: cy.not_needed ? '#f5f5f5' : cy.percentage >= 100 ? '#f6ffed' : '#fffbe6' }"
        @click="toggleCycle(cy.cycle)">
        <span style="font-weight: 600; min-width: 14px;">{{ cy.cycle }}</span>
        <template v-if="cy.not_needed">
          <span style="color: var(--gt-color-text-tertiary);">不需推送</span>
          <el-tooltip :content="cy.reason" placement="top">
            <span style="cursor: help;">ℹ️</span>
          </el-tooltip>
        </template>
        <template v-else>
          <span :style="{ color: cy.percentage >= 100 ? 'var(--gt-color-success)' : 'var(--gt-color-warning)' }">
            {{ cy.connected }}/{{ cy.total }}
          </span>
          <span v-if="cy.missing?.length" style="color: var(--gt-color-warning);">⚠</span>
        </template>
      </div>
    </div>

    <!-- 展开的缺口明细 -->
    <div v-if="expandedCycle" class="gt-cov-detail" style="margin-bottom: 8px; padding: 8px; background: #fff; border: 1px solid #e4e7ed; border-radius: 4px;">
      <div style="font-size: 12px; font-weight: 600; margin-bottom: 4px;">
        {{ expandedCycleData?.label }} — 缺口明细
        <el-button size="small" link @click="expandedCycle = ''">关闭</el-button>
      </div>
      <template v-if="expandedCycleData?.not_needed">
        <span style="font-size: 11px; color: var(--gt-color-text-tertiary);">{{ expandedCycleData.reason }}</span>
      </template>
      <template v-else-if="expandedCycleData?.missing?.length">
        <div style="font-size: 11px; color: var(--gt-color-text-secondary); margin-bottom: 4px;">
          以下 {{ expandedCycleData.missing.length }} 个编码尚未接入推送：
        </div>
        <div style="display: flex; flex-wrap: wrap; gap: 4px;">
          <el-tag v-for="code in expandedCycleData.missing" :key="code" size="small" type="warning" effect="plain">{{ code }}</el-tag>
        </div>
      </template>
      <template v-else>
        <span style="font-size: 11px; color: var(--gt-color-success);">✅ 该循环已全部接入</span>
      </template>
    </div>

    <!-- 最近推送概要（需要 projectId 和 year） -->
    <div v-if="latestRun" class="gt-cov-latest" style="margin-bottom: 6px; padding: 6px 8px; background: #fff; border: 1px solid #e4e7ed; border-radius: 4px; font-size: 11px;">
      <div style="display: flex; align-items: center; gap: 8px; flex-wrap: wrap;">
        <span style="font-weight: 600;">最近推送</span>
        <span style="color: var(--gt-color-text-tertiary);">{{ latestRun.finished_at || '—' }}</span>
        <el-tag size="small" :type="latestRun.status === 'completed' ? 'success' : latestRun.status === 'partial' ? 'warning' : 'info'" effect="plain">
          {{ latestRun.status === 'completed' ? '成功' : latestRun.status === 'partial' ? '部分成功' : latestRun.status }}
        </el-tag>
        <span>写入 <b style="color: var(--gt-color-success);">{{ latestRun.written || 0 }}</b></span>
        <span>保留 <b style="color: var(--gt-color-warning);">{{ latestRun.kept || 0 }}</b></span>
        <span>跳过 <b style="color: var(--gt-color-text-tertiary);">{{ latestRun.skipped || 0 }}</b></span>
      </div>
      <!-- 状态分布条 -->
      <div v-if="stateCounts && stateTotal > 0" style="margin-top: 6px;">
        <div style="display: flex; height: 6px; border-radius: 3px; overflow: hidden; background: #eee;">
          <div v-if="stateCounts.auto" :style="{ width: pct(stateCounts.auto) + '%', background: 'var(--gt-color-success, #67c23a)' }" :title="`自动 ${stateCounts.auto}`" />
          <div v-if="stateCounts.manual" :style="{ width: pct(stateCounts.manual) + '%', background: 'var(--gt-color-warning, #e6a23c)' }" :title="`人工 ${stateCounts.manual}`" />
          <div v-if="stateCounts.locked" :style="{ width: pct(stateCounts.locked) + '%', background: 'var(--gt-color-danger, #f56c6c)' }" :title="`锁定 ${stateCounts.locked}`" />
          <div v-if="stateCounts.pending_confirm" :style="{ width: pct(stateCounts.pending_confirm) + '%', background: '#909399' }" :title="`待确认 ${stateCounts.pending_confirm}`" />
        </div>
        <div style="display: flex; gap: 10px; margin-top: 3px; font-size: 10px; color: var(--gt-color-text-tertiary);">
          <span v-if="stateCounts.auto">🟢 自动 {{ stateCounts.auto }}</span>
          <span v-if="stateCounts.manual">🟡 人工 {{ stateCounts.manual }}</span>
          <span v-if="stateCounts.locked">🔴 锁定 {{ stateCounts.locked }}</span>
          <span v-if="stateCounts.pending_confirm">⚪ 待确认 {{ stateCounts.pending_confirm }}</span>
        </div>
      </div>
    </div>

    <div v-if="coverage.excluded?.length" style="font-size: 11px; color: var(--gt-color-text-tertiary);">
      不适用：{{ coverage.excluded.join('、') }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import api from '@/services/apiProxy'

const props = defineProps<{
  show: boolean
  projectId?: string
  year?: number
}>()

const coverage = ref<any>(null)
const expandedCycle = ref('')
const latestRun = ref<any>(null)
const stateCounts = ref<Record<string, number> | null>(null)

const expandedCycleData = computed(() =>
  coverage.value?.cycles?.find((c: any) => c.cycle === expandedCycle.value) || null,
)

const stateTotal = computed(() =>
  Object.values(stateCounts.value || {}).reduce((a, b) => a + (b as number), 0),
)

function pct(n: number): number {
  return stateTotal.value > 0 ? Math.round((n / stateTotal.value) * 100) : 0
}

function toggleCycle(cycle: string) {
  expandedCycle.value = expandedCycle.value === cycle ? '' : cycle
}

watch(() => props.show, async (v) => {
  if (!v) return
  // 覆盖率（全局静态数据）
  if (!coverage.value) {
    try { coverage.value = await api.get('/api/formula-push/coverage') as any } catch { /* 不阻断 */ }
  }
  // 最近推送运行 + 状态分布（需要项目上下文）
  if (props.projectId && props.year && !latestRun.value) {
    try {
      const data = await api.get(`/api/projects/${props.projectId}/formula-push/latest`, {
        params: { year: props.year },
      }) as any
      latestRun.value = data?.run || null
      stateCounts.value = data?.state_counts || null
    } catch { /* 项目可能没有推送记录，不阻断 */ }
  }
}, { immediate: true })
</script>
