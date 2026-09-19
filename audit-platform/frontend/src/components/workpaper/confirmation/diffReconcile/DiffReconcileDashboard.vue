<template>
  <div class="diff-reconcile-dashboard">
    <el-collapse v-model="expanded">
      <el-collapse-item title="差异调节概览" name="overview">
        <!-- 指标卡片 -->
        <div class="diff-reconcile-dashboard__cards">
          <div class="diff-reconcile-dashboard__card">
            <div class="diff-reconcile-dashboard__card-value">{{ metrics.total_count }}</div>
            <div class="diff-reconcile-dashboard__card-label">总笔数</div>
          </div>
          <div class="diff-reconcile-dashboard__card">
            <div class="diff-reconcile-dashboard__card-value">{{ formatAmount(metrics.difference_net_total) }}</div>
            <div class="diff-reconcile-dashboard__card-label">差异净额合计</div>
          </div>
          <div class="diff-reconcile-dashboard__card">
            <div class="diff-reconcile-dashboard__card-value">{{ formatAmount(metrics.difference_abs_total) }}</div>
            <div class="diff-reconcile-dashboard__card-label">差异绝对值合计</div>
          </div>
          <div class="diff-reconcile-dashboard__card">
            <div
              class="diff-reconcile-dashboard__card-value"
              :class="{ 'diff-reconcile-dashboard__card-value--warn': metrics.analyzed_rate < 100 }"
            >
              {{ metrics.analyzed_rate }}%
            </div>
            <div class="diff-reconcile-dashboard__card-label">已分析率</div>
          </div>
          <div class="diff-reconcile-dashboard__card">
            <div class="diff-reconcile-dashboard__card-value">
              {{ metrics.adjustment_count }}
              <span class="diff-reconcile-dashboard__card-sub">/ {{ formatAmount(metrics.adjustment_amount) }}</span>
            </div>
            <div class="diff-reconcile-dashboard__card-label">需调整（笔/金额）</div>
          </div>
          <div
            v-if="metrics.over_materiality_count > 0"
            class="diff-reconcile-dashboard__card diff-reconcile-dashboard__card--danger"
          >
            <div class="diff-reconcile-dashboard__card-value">{{ metrics.over_materiality_count }}</div>
            <div class="diff-reconcile-dashboard__card-label">超重要性</div>
          </div>
        </div>

        <!-- 科目分组汇总 -->
        <div v-if="subjectSummary.length" class="diff-reconcile-dashboard__subject-table">
          <h4 class="diff-reconcile-dashboard__section-title">按科目汇总</h4>
          <el-table :data="subjectSummary" size="small" border stripe table-layout="auto" class="diff-reconcile-dashboard__table">
            <el-table-column label="科目" prop="subject" min-width="90" />
            <el-table-column label="笔数" prop="count" min-width="50" align="center" />
            <el-table-column label="发函合计" prop="sent_total" min-width="90" align="right">
              <template #default="{ row }">{{ formatAmount(row.sent_total) }}</template>
            </el-table-column>
            <el-table-column label="回函合计" prop="reply_total" min-width="90" align="right">
              <template #default="{ row }">{{ formatAmount(row.reply_total) }}</template>
            </el-table-column>
            <el-table-column label="差异净额" prop="difference_total" min-width="90" align="right">
              <template #default="{ row }">
                <span :class="{ 'diff-reconcile-dashboard__negative': row.difference_total < 0 }">
                  {{ formatAmount(row.difference_total) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="已分析" prop="analyzed_count" min-width="55" align="center" />
            <el-table-column label="需调整" prop="adjustment_count" min-width="55" align="center" />
          </el-table>
        </div>
      </el-collapse-item>
    </el-collapse>

    <!-- 质量警示 -->
    <div v-if="alerts.length" class="diff-reconcile-dashboard__alerts">
      <el-alert
        v-for="(alert, idx) in alerts"
        :key="idx"
        :title="alert.title"
        :type="alert.type"
        :closable="false"
        show-icon
        class="diff-reconcile-dashboard__alert-item"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { DiffReconcileMetrics, DiffSummaryBySubject } from './diffReconcileTypes'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  metrics: DiffReconcileMetrics
  subjectSummary: DiffSummaryBySubject[]
  unclassifiedCount: number
  hasMaterialityConfig: boolean
}>()

const expanded = ref<string[]>(['overview'])

// ─── 质量警示 ────────────────────────────────────────────────────────────────

interface AlertItem {
  title: string
  type: 'warning' | 'error' | 'info'
}

const alerts = computed<AlertItem[]>(() => {
  const list: AlertItem[] = []

  if (props.unclassifiedCount > 0) {
    list.push({
      title: `${props.unclassifiedCount} 笔差异尚未分类（差异类型未填）`,
      type: 'warning',
    })
  }

  if (props.metrics.over_materiality_count > 0 && props.hasMaterialityConfig) {
    list.push({
      title: `${props.metrics.over_materiality_count} 笔差异超过实际执行重要性，请重点关注`,
      type: 'error',
    })
  }

  if (props.metrics.adjustment_count > 0) {
    const noRef = props.metrics.adjustment_count // simplified; in practice check adj_ref_index
    if (noRef > 0) {
      list.push({
        title: `${noRef} 笔标记"需调整"，请确认已关联调整分录索引`,
        type: 'info',
      })
    }
  }

  return list
})

// ─── 格式化 ──────────────────────────────────────────────────────────────────

const prefs = useDisplayPrefsStore()

function formatAmount(val?: number): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}
</script>

<style scoped>
.diff-reconcile-dashboard__cards {
  display: flex;
  flex-wrap: wrap;
  gap: 12px;
  margin-bottom: 16px;
}

.diff-reconcile-dashboard__card {
  flex: 1;
  min-width: 120px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  text-align: center;
}

.diff-reconcile-dashboard__card--danger {
  background: var(--el-color-danger-light-9);
  border: 1px solid var(--el-color-danger-light-5);
}

.diff-reconcile-dashboard__card-value {
  font-size: 20px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
  color: var(--el-text-color-primary);
}

.diff-reconcile-dashboard__card-value--warn {
  color: var(--el-color-warning);
}

.diff-reconcile-dashboard__card-sub {
  font-size: var(--wp-font-size, 13px);
  font-weight: 400;
  color: var(--el-text-color-secondary);
}

.diff-reconcile-dashboard__card-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-top: 4px;
}

.diff-reconcile-dashboard__section-title {
  font-size: 14px;
  font-weight: 500;
  margin: 12px 0 8px;
}

/* 表头折行 */
.diff-reconcile-dashboard__table :deep(.el-table__header th .cell) {
  white-space: normal;
  word-break: break-all;
  line-height: 1.3;
  font-size: 12px;
}

.diff-reconcile-dashboard__table :deep(.el-table__body td .cell) {
  font-size: 12px;
}

.diff-reconcile-dashboard__negative {
  color: var(--el-color-danger);
}

.diff-reconcile-dashboard__alerts {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.diff-reconcile-dashboard__alert-item {
  margin: 0;
}
</style>
