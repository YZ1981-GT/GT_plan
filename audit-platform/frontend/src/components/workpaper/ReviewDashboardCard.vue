<script setup lang="ts">
/**
 * ReviewDashboardCard.vue — A1 五级复核状态看板卡片
 *
 * 消费 review_dashboard_status resolver 数据，渲染 5 个级别的复核状态。
 * Validates: Requirements 4.1, 4.2, 4.3, 4.4, 4.5
 */
import { computed } from 'vue'
import { CircleCheck, Warning, QuestionFilled } from '@element-plus/icons-vue'

interface LevelStatus {
  wp_code: string
  level_label: string
  reviewer_name: string | null
  sign_status: 'pass' | 'reject' | 'in_progress' | 'not_started'
  signed_at: string | null
  progress: { completed: number; total: number }
}

interface DashboardData {
  levels?: LevelStatus[]
}

const props = defineProps<{
  data?: DashboardData
}>()

const levels = computed<LevelStatus[]>(() => props.data?.levels ?? [])

function formatDate(iso: string | null): string {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString('zh-CN')
  } catch {
    return iso
  }
}

function progressPct(level: LevelStatus): number {
  const { completed, total } = level.progress || { completed: 0, total: 0 }
  return total > 0 ? Math.round((completed / total) * 100) : 0
}
</script>

<template>
  <div class="review-dashboard-card">
    <div class="review-dashboard-card__title">
      五级复核状态
      <el-tooltip placement="top" :show-after="300">
        <template #content>
          <div style="max-width: 320px; line-height: 1.6;">
            <p style="margin: 0 0 6px; font-weight: 600;">五级复核是审计质量控制的核心机制：</p>
            <p style="margin: 0 0 4px;">① 现场负责人 — 底稿编制完成后首次复核</p>
            <p style="margin: 0 0 4px;">② 经理 — 项目管理层面复核</p>
            <p style="margin: 0 0 4px;">③ 合伙人 — 重大事项判断与签发</p>
            <p style="margin: 0 0 4px;">④ 质控 — 独立质量复核（IRP）</p>
            <p style="margin: 0 0 8px;">⑤ EQCR — 项目质量控制复核</p>
            <p style="margin: 0; color: #a0a0a0; font-size: 12px;">各级复核在「复核检查表」模块中执行，完成后此处自动更新状态。</p>
          </div>
        </template>
        <el-icon :size="14" style="margin-left: 6px; color: #909399; cursor: help; vertical-align: middle;">
          <QuestionFilled />
        </el-icon>
      </el-tooltip>
    </div>
    <div v-if="!levels.length" class="review-dashboard-card__empty">
      <p style="margin: 0 0 8px;">暂无复核数据</p>
      <p class="review-dashboard-card__hint">
        当项目分配了复核人员并创建复核检查表（A21~A25）后，各级复核进度将在此自动展示。
        请在「人员档案 → 项目分配」中设置复核角色。
      </p>
    </div>
    <div v-else class="review-dashboard-card__levels">
      <div
        v-for="level in levels"
        :key="level.wp_code"
        class="level-card"
        :class="`level-card--${level.sign_status}`"
      >
        <div class="level-card__header">
          <span class="level-card__label">{{ level.level_label }}</span>
          <span class="level-card__code">{{ level.wp_code }}</span>
        </div>
        <div class="level-card__reviewer">
          {{ level.reviewer_name || '未分配' }}
        </div>
        <div class="level-card__status">
          <!-- pass: 绿色 CircleCheck -->
          <template v-if="level.sign_status === 'pass'">
            <el-icon color="#67C23A" :size="16"><CircleCheck /></el-icon>
            <span class="status-text status-text--pass">
              已通过 · {{ level.reviewer_name }} · {{ formatDate(level.signed_at) }}
            </span>
          </template>
          <!-- reject: 橙色 Warning -->
          <template v-else-if="level.sign_status === 'reject'">
            <el-icon color="#E6A23C" :size="16"><Warning /></el-icon>
            <span class="status-text status-text--reject">已退回</span>
          </template>
          <!-- not_started: 灰色 -->
          <template v-else-if="level.sign_status === 'not_started'">
            <span class="status-text status-text--not-started">未开始</span>
          </template>
          <!-- in_progress: 蓝色进度条 -->
          <template v-else>
            <el-progress
              :percentage="progressPct(level)"
              :stroke-width="6"
              :show-text="true"
              style="flex: 1; max-width: 160px;"
            />
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.review-dashboard-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 8px;
  padding: 16px;
  background: #fff;
}
.review-dashboard-card__title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #303133;
}
.review-dashboard-card__empty {
  color: var(--el-text-color-secondary);
  font-size: var(--wp-font-size, 13px);
  text-align: center;
  padding: 20px 0;
}
.review-dashboard-card__hint {
  margin: 0;
  font-size: 12px;
  color: #a0a0a0;
  line-height: 1.6;
}
.review-dashboard-card__levels {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.level-card {
  padding: 10px 12px;
  border-radius: 6px;
  border: 1px solid #e8e8ec;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.level-card--pass { border-left: 3px solid #67C23A; }
.level-card--reject { border-left: 3px solid #E6A23C; }
.level-card--in_progress { border-left: 3px solid #409EFF; }
.level-card--not_started { border-left: 3px solid #c0c4cc; }

.level-card__header {
  display: flex;
  align-items: center;
  gap: 8px;
}
.level-card__label {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  color: #303133;
}
.level-card__code {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.level-card__reviewer {
  font-size: 12px;
  color: var(--el-text-color-regular);
}
.level-card__status {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 2px;
}
.status-text {
  font-size: 12px;
}
.status-text--pass { color: #67C23A; }
.status-text--reject { color: #E6A23C; }
.status-text--not-started { color: #909399; }
</style>
