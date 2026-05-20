<template>
  <div class="partner-project-dashboard">
    <!-- Page Header: 项目名称 + 审计年度 + 最后更新时间 + 刷新按钮 -->
    <div class="dashboard-header">
      <div class="header-info">
        <h2 class="project-title">{{ data?.project_name ?? '加载中...' }}</h2>
        <div class="header-meta">
          <el-tag v-if="data?.audit_year" type="info" size="small">
            {{ data.audit_year }} 年度
          </el-tag>
          <span v-if="lastUpdated" class="last-updated">
            最后更新：{{ formatTime(lastUpdated) }}
          </span>
        </div>
      </div>
      <div class="header-actions">
        <el-button :loading="loading" @click="refresh" :icon="RefreshIcon" size="default">
          刷新
        </el-button>
      </div>
    </div>

    <!-- Skeleton screen: loading 时显示 el-skeleton 占位 -->
    <template v-if="loading && !data">
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="12">
          <el-skeleton :rows="6" animated />
        </el-col>
        <el-col :span="12">
          <el-skeleton :rows="6" animated />
        </el-col>
      </el-row>
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="14">
          <el-skeleton :rows="5" animated />
        </el-col>
        <el-col :span="10">
          <el-skeleton :rows="5" animated />
        </el-col>
      </el-row>
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="14">
          <el-skeleton :rows="4" animated />
        </el-col>
        <el-col :span="10">
          <el-skeleton :rows="4" animated />
        </el-col>
      </el-row>
    </template>

    <!-- 数据加载完成后的响应式网格布局 -->
    <template v-else>
      <!-- Row 1: CycleProgressRing (12) + VRSummaryCard (12) -->
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="12" v-if="showModule('cycleProgress')">
          <!-- CycleProgressRing placeholder -->
          <div class="module-card">
            <div class="module-card__header">全循环进度</div>
            <div class="module-card__body">
              <!-- TODO: CycleProgressRing.vue 组件（Task 3.3） -->
              <div class="module-placeholder">CycleProgressRing</div>
            </div>
          </div>
        </el-col>
        <el-col :span="12" v-if="showModule('vrSummary')">
          <!-- VRSummaryCard placeholder -->
          <div class="module-card">
            <div class="module-card__header">Blocking VR 汇总</div>
            <div class="module-card__body">
              <!-- TODO: VRSummaryCard.vue 组件（Task 3.4） -->
              <div class="module-placeholder">VRSummaryCard</div>
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- Row 2: ReviewOpinionList (14) + QuickEntryPanel (10) -->
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="14" v-if="showModule('reviewOpinion')">
          <!-- ReviewOpinionList placeholder -->
          <div class="module-card">
            <div class="module-card__header">未解决复核意见</div>
            <div class="module-card__body">
              <!-- TODO: ReviewOpinionList.vue 组件（Task 3.5） -->
              <div class="module-placeholder">ReviewOpinionList</div>
            </div>
          </div>
        </el-col>
        <el-col :span="10" v-if="showModule('quickEntry')">
          <div class="module-card">
            <div class="module-card__header">关键判断点入口</div>
            <div class="module-card__body">
              <QuickEntryPanel />
            </div>
          </div>
        </el-col>
      </el-row>

      <!-- Row 3: ProjectTimeline (14) + TrimmingOverview (10) -->
      <el-row :gutter="16" class="dashboard-row">
        <el-col :span="14" v-if="showModule('timeline')">
          <!-- ProjectTimeline placeholder -->
          <div class="module-card">
            <div class="module-card__header">项目时间线</div>
            <div class="module-card__body">
              <!-- TODO: ProjectTimeline.vue 组件（Task 3.7） -->
              <div class="module-placeholder">ProjectTimeline</div>
            </div>
          </div>
        </el-col>
        <el-col :span="10" v-if="showModule('trimming')">
          <div class="module-card">
            <div class="module-card__header">裁剪汇总</div>
            <div class="module-card__body module-card__body--top">
              <TrimmingOverview :trimming-overview="trimmingOverview" />
            </div>
          </div>
        </el-col>
      </el-row>
    </template>

    <!-- 错误提示 -->
    <div v-if="error" class="dashboard-error">
      <el-alert :title="error" type="error" show-icon :closable="false">
        <template #default>
          <el-button size="small" type="primary" @click="refresh">重试</el-button>
        </template>
      </el-alert>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import { Refresh as RefreshIcon } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import { useDashboardData } from '@/composables/useDashboardData'
import QuickEntryPanel from '@/components/dashboard/QuickEntryPanel.vue'
import TrimmingOverview from '@/components/dashboard/TrimmingOverview.vue'

const route = useRoute()
const authStore = useAuthStore()

const projectId = computed(() => route.params.projectId as string)

// 使用 useDashboardData composable 获取仪表盘数据
const {
  data,
  loading,
  error,
  lastUpdated,
  refresh,
  trimmingOverview,
} = useDashboardData(projectId)

// 当前用户角色
const currentRole = computed(() => authStore.user?.role ?? '')

/**
 * RBAC 模块显隐逻辑
 * - partner/admin: 显示全部 6 个模块
 * - manager: 显示除 trimming 外的全部模块
 * - assistant: 仅显示 cycleProgress + timeline + quickEntry
 */
type ModuleName = 'cycleProgress' | 'vrSummary' | 'reviewOpinion' | 'quickEntry' | 'timeline' | 'trimming'

const MODULE_VISIBILITY: Record<string, ModuleName[]> = {
  partner: ['cycleProgress', 'vrSummary', 'reviewOpinion', 'quickEntry', 'timeline', 'trimming'],
  admin: ['cycleProgress', 'vrSummary', 'reviewOpinion', 'quickEntry', 'timeline', 'trimming'],
  manager: ['cycleProgress', 'vrSummary', 'reviewOpinion', 'quickEntry', 'timeline'],
  assistant: ['cycleProgress', 'timeline', 'quickEntry'],
}

function showModule(moduleName: ModuleName): boolean {
  const role = currentRole.value
  const visibleModules = MODULE_VISIBILITY[role] ?? MODULE_VISIBILITY['assistant']
  return visibleModules.includes(moduleName)
}

// 格式化时间
function formatTime(isoStr: string): string {
  try {
    const d = new Date(isoStr)
    return d.toLocaleString('zh-CN', {
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return isoStr
  }
}
</script>

<style scoped>
.partner-project-dashboard {
  padding: 20px 24px;
}

.dashboard-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding: 16px 20px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
}

.header-info {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.project-title {
  margin: 0;
  font-size: var(--gt-font-size-xl, 20px);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
}

.header-meta {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: var(--gt-font-size-sm, 13px);
  color: var(--gt-color-text-secondary, #909399);
}

.last-updated {
  color: var(--gt-color-text-tertiary, #c0c4cc);
}

.header-actions {
  flex-shrink: 0;
}

.dashboard-row {
  margin-bottom: 16px;
}

.module-card {
  background: var(--gt-color-bg-white, #fff);
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.06);
  overflow: hidden;
  height: 100%;
}

.module-card__header {
  padding: 12px 16px;
  font-size: var(--gt-font-size-base, 14px);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  border-bottom: 1px solid var(--gt-color-border-lighter, #f0f0f0);
}

.module-card__body {
  padding: 16px;
  min-height: 160px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.module-card__body--top {
  align-items: flex-start;
  justify-content: flex-start;
}

.module-placeholder {
  color: var(--gt-color-text-placeholder, #c0c4cc);
  font-size: var(--gt-font-size-sm, 13px);
  font-style: italic;
}

.dashboard-error {
  margin-top: 16px;
}
</style>
