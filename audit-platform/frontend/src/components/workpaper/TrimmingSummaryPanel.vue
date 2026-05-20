<template>
  <div class="gt-trimming-summary">
    <h4 class="gt-trimming-summary-title">📊 裁剪汇总</h4>

    <!-- 按循环分组 -->
    <section class="gt-trimming-summary-section">
      <h5 class="gt-trimming-summary-subtitle">按循环分组</h5>
      <div v-if="summary.by_cycle.length === 0" class="gt-trimming-summary-empty">
        暂无数据
      </div>
      <div v-for="cycle in summary.by_cycle" :key="cycle.cycle" class="gt-trimming-summary-row">
        <span class="gt-trimming-summary-cycle">{{ cycle.cycle }}</span>
        <span class="gt-trimming-summary-count">{{ cycle.trimmed }}/{{ cycle.total }}</span>
        <span
          class="gt-trimming-summary-rate"
          :class="{ 'is-warning': cycle.warning }"
        >
          {{ cycle.rate.toFixed(1) }}%
          <span v-if="cycle.warning" class="gt-trimming-warning-icon">⚠️</span>
        </span>
      </div>
    </section>

    <!-- 按理由分组 -->
    <section class="gt-trimming-summary-section">
      <h5 class="gt-trimming-summary-subtitle">按理由分组</h5>
      <div v-if="summary.by_reason.length === 0" class="gt-trimming-summary-empty">
        暂无数据
      </div>
      <div v-for="reason in summary.by_reason" :key="reason.reason_code" class="gt-trimming-summary-row">
        <span class="gt-trimming-summary-reason">{{ getReasonLabel(reason.reason_code) }}</span>
        <span class="gt-trimming-summary-count">{{ reason.count }} 行</span>
      </div>
    </section>

    <!-- 裁剪率警告 -->
    <el-alert
      v-if="summary.warnings.length > 0"
      type="warning"
      show-icon
      :closable="false"
      style="margin: 10px 0"
    >
      <template #default>
        <div v-for="(w, idx) in summary.warnings" :key="idx" style="font-size: 12px">
          {{ w }}
        </div>
      </template>
    </el-alert>

    <!-- 操作历史 -->
    <section class="gt-trimming-summary-section">
      <h5 class="gt-trimming-summary-subtitle">
        操作历史
        <el-button text size="small" @click="loadHistory">刷新</el-button>
      </h5>

      <!-- 筛选 -->
      <div class="gt-trimming-history-filters">
        <el-select
          v-model="historyFilter.reason_code"
          placeholder="按理由"
          clearable
          size="small"
          style="width: 120px"
          @change="loadHistory"
        >
          <el-option label="无相关业务" value="no_related_business" />
          <el-option label="风险评估为低" value="low_risk_assessment" />
          <el-option label="控制测试有效" value="control_test_effective" />
          <el-option label="其他" value="other" />
        </el-select>
      </div>

      <!-- 历史列表 -->
      <div class="gt-trimming-history-list">
        <div
          v-for="entry in history"
          :key="entry.id"
          class="gt-trimming-history-item"
        >
          <div class="gt-trimming-history-header">
            <el-tag :type="entry.action === 'trim' ? 'warning' : 'success'" size="small">
              {{ entry.action === 'trim' ? '裁剪' : '恢复' }}
            </el-tag>
            <span class="gt-trimming-history-user">{{ entry.user_name || entry.user_id }}</span>
            <span class="gt-trimming-history-time">{{ formatTime(entry.created_at) }}</span>
          </div>
          <div class="gt-trimming-history-detail">
            <span>{{ entry.row_ids.join(', ') }}</span>
            <span v-if="entry.reason_code" class="gt-trimming-history-reason">
              — {{ getReasonLabel(entry.reason_code) }}
              <template v-if="entry.reason_text">: {{ entry.reason_text }}</template>
            </span>
          </div>
        </div>
        <div v-if="history.length === 0" class="gt-trimming-summary-empty">
          暂无操作记录
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
/**
 * TrimmingSummaryPanel — 裁剪汇总面板
 *
 * - 按循环分组裁剪数 / 按理由分组裁剪数 / 裁剪率
 * - 裁剪率 > 50% 循环标记黄色警告
 * - 展开查看每个被裁剪程序的详细理由和操作人
 * - 操作历史列表（时间倒序）+ 筛选
 * - 所有角色可见（只读）
 *
 * @see requirements.md Requirement 6.3, 6.4, 7.1, 7.2, 7.3, 8.4
 */
import { ref, reactive, onMounted } from 'vue'
import type { TrimSummary, TrimLogEntry, HistoryFilter } from '@/composables/useProcedureTrimming'

interface Props {
  /** fetchSummary function from useProcedureTrimming */
  fetchSummaryFn: () => Promise<TrimSummary>
  /** fetchHistory function from useProcedureTrimming */
  fetchHistoryFn: (filters?: HistoryFilter) => Promise<TrimLogEntry[]>
}

const props = defineProps<Props>()

const summary = ref<TrimSummary>({
  total_procedures: 0,
  trimmed_count: 0,
  trim_rate: 0,
  by_cycle: [],
  by_reason: [],
  warnings: [],
})

const history = ref<TrimLogEntry[]>([])
const historyFilter = reactive<HistoryFilter>({
  reason_code: undefined,
})

async function loadSummary() {
  summary.value = await props.fetchSummaryFn()
}

async function loadHistory() {
  const filters: HistoryFilter = {}
  if (historyFilter.reason_code) filters.reason_code = historyFilter.reason_code
  history.value = await props.fetchHistoryFn(filters)
}

function getReasonLabel(code?: string | null): string {
  const map: Record<string, string> = {
    no_related_business: '无相关业务',
    low_risk_assessment: '风险评估为低',
    control_test_effective: '控制测试有效',
    other: '其他',
  }
  return map[code || ''] || code || '—'
}

function formatTime(iso: string): string {
  if (!iso) return '—'
  try {
    const d = new Date(iso)
    return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' })
  } catch {
    return iso
  }
}

onMounted(() => {
  loadSummary()
  loadHistory()
})
</script>

<style scoped>
.gt-trimming-summary {
  padding: 8px 0;
}
.gt-trimming-summary-title {
  margin: 0 0 10px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.gt-trimming-summary-section {
  margin-bottom: 14px;
}
.gt-trimming-summary-subtitle {
  margin: 0 0 6px;
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-regular, #606266);
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.gt-trimming-summary-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 8px;
  font-size: 12px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}
.gt-trimming-summary-cycle,
.gt-trimming-summary-reason {
  flex: 1;
  color: var(--el-text-color-primary, #303133);
}
.gt-trimming-summary-count {
  color: var(--el-text-color-secondary, #909399);
  min-width: 50px;
  text-align: right;
}
.gt-trimming-summary-rate {
  min-width: 60px;
  text-align: right;
  font-weight: 600;
}
.gt-trimming-summary-rate.is-warning {
  color: var(--el-color-danger, #f56c6c);
}
.gt-trimming-warning-icon {
  font-size: 12px;
}
.gt-trimming-summary-empty {
  font-size: 12px;
  color: var(--el-text-color-secondary, #909399);
  text-align: center;
  padding: 8px;
}
.gt-trimming-history-filters {
  margin-bottom: 8px;
}
.gt-trimming-history-list {
  max-height: 240px;
  overflow-y: auto;
}
.gt-trimming-history-item {
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}
.gt-trimming-history-header {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 2px;
}
.gt-trimming-history-user {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}
.gt-trimming-history-time {
  font-size: 11px;
  color: var(--el-text-color-secondary, #909399);
  margin-left: auto;
}
.gt-trimming-history-detail {
  font-size: 11px;
  color: var(--el-text-color-regular, #606266);
  padding-left: 4px;
}
.gt-trimming-history-reason {
  color: var(--el-text-color-secondary, #909399);
}
</style>
