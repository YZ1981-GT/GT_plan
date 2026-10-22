<!--
  项目级公式健康度面板（spec: formula-management-deep-optimization · R2）。
  六维度卡片 + 按循环下钻。嵌入 FormulaDashboardDialog 的「📊 项目健康度」Tab。
-->
<template>
  <div v-loading="loading" class="gt-fh-panel">
    <el-alert v-if="error" :title="error" type="error" :closable="false" show-icon />

    <!-- 健康度总分 -->
    <div class="gt-fh-score">
      <span class="gt-fh-score-value" :style="{ color: scoreColor }">{{ overallScore }}%</span>
      <span class="gt-fh-score-label">公式健康度</span>
    </div>

    <!-- 六维度卡片 -->
    <div class="gt-fh-cards">
      <!-- 1. 推送覆盖率 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">📤 推送覆盖率</div>
        <div class="gt-fh-card-value" :style="{ color: pctColor(pushCovPct) }">{{ pushCovPct }}%</div>
        <div class="gt-fh-card-desc">{{ pushCovDesc }}</div>
      </div>

      <!-- 2. 推送成功率 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">⚡ 推送成功率</div>
        <div class="gt-fh-card-value" :style="{ color: pctColor(pushSuccPct) }">
          {{ data?.push_success_rate?.has_run ? pushSuccPct + '%' : '—' }}
        </div>
        <div class="gt-fh-card-desc">{{ pushSuccDesc }}</div>
      </div>

      <!-- 3. 公式配置率 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">📐 报表公式配置率</div>
        <div class="gt-fh-card-value" :style="{ color: pctColor(configPct) }">{{ configPct }}%</div>
        <div class="gt-fh-card-desc">{{ configDesc }}</div>
      </div>

      <!-- 4. 冲突待确认 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">⚠️ 冲突待确认</div>
        <div class="gt-fh-card-value" :style="{ color: pendingCount > 0 ? 'var(--gt-color-danger)' : 'var(--gt-color-success)' }">
          {{ pendingCount }}
        </div>
        <div class="gt-fh-card-desc">{{ pendingCount > 0 ? '需要处理' : '暂无冲突' }}</div>
      </div>

      <!-- 5. 表间审核通过率 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">🔍 表间审核通过率</div>
        <div class="gt-fh-card-value" :style="{ color: pctColor(crossCheckPct) }">
          {{ data?.cross_check_pass_rate?.has_results ? crossCheckPct + '%' : '—' }}
        </div>
        <div class="gt-fh-card-desc">{{ crossCheckDesc }}</div>
      </div>

      <!-- 6. 过期占比 -->
      <div class="gt-fh-card">
        <div class="gt-fh-card-title">🔄 报表过期率</div>
        <div class="gt-fh-card-value" :style="{ color: stalePct > 20 ? 'var(--gt-color-danger)' : stalePct > 5 ? 'var(--gt-color-wheat)' : 'var(--gt-color-success)' }">
          {{ stalePct }}%
        </div>
        <div class="gt-fh-card-desc">{{ staleDesc }}</div>
      </div>
    </div>

    <!-- 推送覆盖率按循环下钻 -->
    <div v-if="cycles.length" class="gt-fh-drill">
      <div class="gt-fh-drill-title">推送覆盖率（按循环）</div>
      <el-table :data="cycles" size="small" border max-height="300">
        <el-table-column prop="label" label="循环" width="160" />
        <el-table-column label="接入率" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="row.not_needed ? 'info' : row.percentage >= 80 ? 'success' : row.percentage >= 50 ? 'warning' : 'danger'" size="small">
              {{ row.not_needed ? '不需推送' : row.percentage + '%' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="已接入/总数" width="120" align="center">
          <template #default="{ row }">
            {{ row.not_needed ? '—' : `${row.connected}/${row.total}` }}
          </template>
        </el-table-column>
        <el-table-column label="未接入编码" min-width="200">
          <template #default="{ row }">
            <span v-if="row.missing?.length" style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs);">
              {{ row.missing.join('、') }}
            </span>
            <span v-else-if="!row.not_needed" style="color: var(--gt-color-success);">全部接入 ✓</span>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { formulaHealth } from '@/services/apiPaths/formula'
import { handleApiError } from '@/utils/errorHandler'

const props = defineProps<{
  projectId: string
  year: number
}>()

const data = ref<any>(null)
const loading = ref(false)
const error = ref('')

async function load() {
  if (!props.projectId || !props.year) return
  loading.value = true
  error.value = ''
  try {
    data.value = await api.get(formulaHealth.get(props.projectId, props.year))
  } catch (e: any) {
    error.value = handleApiError(e, { silent: true }) || '加载失败'
  } finally {
    loading.value = false
  }
}

watch(() => [props.projectId, props.year], load, { immediate: true })

// ── 计算属性 ──

const pushCovPct = computed(() => data.value?.push_coverage?.percentage ?? 0)
const pushCovDesc = computed(() => {
  const c = data.value?.push_coverage
  return c ? `${c.total_registered}/${c.total_codes} 个编码已接入` : ''
})

const pushSuccPct = computed(() => data.value?.push_success_rate?.success_rate ?? 0)
const pushSuccDesc = computed(() => {
  const r = data.value?.push_success_rate
  if (!r?.has_run) return '尚未推送'
  return `写入 ${r.written} / 跳过 ${r.skipped} / 保留 ${r.kept}`
})

const configPct = computed(() => data.value?.formula_config_rate?.coverage_rate ?? 0)
const configDesc = computed(() => {
  const c = data.value?.formula_config_rate
  return c ? `${c.with_formula}/${c.total_rows} 行已配置公式` : ''
})

const pendingCount = computed(() => data.value?.pending_conflicts?.pending ?? 0)

const crossCheckPct = computed(() => data.value?.cross_check_pass_rate?.pass_rate ?? 0)
const crossCheckDesc = computed(() => {
  const c = data.value?.cross_check_pass_rate
  if (!c?.has_results) return '尚未执行审核'
  return `通过 ${c.passed} / 失败 ${c.failed}`
})

const stalePct = computed(() => data.value?.stale_ratio?.report_stale_rate ?? 0)
const staleDesc = computed(() => {
  const s = data.value?.stale_ratio
  return s ? `${s.report_stale}/${s.report_total} 个报表行过期` : ''
})

const cycles = computed(() => data.value?.push_coverage?.cycles ?? [])

const overallScore = computed(() => {
  // 综合评分 = 六维度加权平均
  const w = [
    { v: pushCovPct.value, w: 0.2 },
    { v: pushSuccPct.value, w: 0.2 },
    { v: configPct.value, w: 0.2 },
    { v: pendingCount.value === 0 ? 100 : Math.max(0, 100 - pendingCount.value * 10), w: 0.1 },
    { v: crossCheckPct.value || 100, w: 0.15 },
    { v: 100 - stalePct.value, w: 0.15 },
  ]
  return Math.round(w.reduce((sum, i) => sum + i.v * i.w, 0))
})

const scoreColor = computed(() => {
  const s = overallScore.value
  if (s >= 80) return 'var(--gt-color-success)'
  if (s >= 50) return 'var(--gt-color-wheat)'
  return 'var(--gt-color-danger)'
})

function pctColor(pct: number) {
  if (pct >= 80) return 'var(--gt-color-success)'
  if (pct >= 50) return 'var(--gt-color-wheat)'
  return 'var(--gt-color-danger)'
}
</script>

<style scoped>
.gt-fh-panel { padding: 12px 0; }
.gt-fh-score { text-align: center; margin-bottom: 16px; }
.gt-fh-score-value { font-size: 48px; font-weight: 700; }
.gt-fh-score-label { display: block; font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary); }
.gt-fh-cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 16px; }
.gt-fh-card { background: var(--gt-bg-overlay); border: 1px solid var(--gt-color-border-light); border-radius: 8px; padding: 12px; text-align: center; }
.gt-fh-card-title { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-bottom: 4px; }
.gt-fh-card-value { font-size: 24px; font-weight: 600; }
.gt-fh-card-desc { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-top: 2px; }
.gt-fh-drill { margin-top: 8px; }
.gt-fh-drill-title { font-size: var(--gt-font-size-sm); font-weight: 600; margin-bottom: 8px; }
</style>
