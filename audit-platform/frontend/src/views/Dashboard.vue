<template>
  <div class="gt-dashboard gt-fade-in">
    <div class="dashboard-welcome">
      <h1 class="gt-page-title">
        <el-icon :size="26"><Odometer /></el-icon>
        仪表盘
      </h1>
      <p class="welcome-desc">欢迎使用致同审计作业平台</p>
    </div>

    <!-- 统计卡片 -->
    <div class="stat-grid gt-stagger">
      <div class="stat-card stat-card--primary">
        <div class="stat-icon-wrap">
          <el-icon :size="28"><FolderOpened /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">项目总数</span>
          <span class="stat-value gt-count-up">{{ stats.total }}</span>
        </div>
      </div>
      <div class="stat-card stat-card--teal">
        <div class="stat-icon-wrap">
          <el-icon :size="28"><Loading /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">进行中</span>
          <span class="stat-value gt-count-up">{{ stats.inProgress }}</span>
        </div>
      </div>
      <div class="stat-card stat-card--coral">
        <div class="stat-icon-wrap">
          <el-icon :size="28"><Warning /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">待复核</span>
          <span class="stat-value gt-count-up">{{ stats.pendingReview }}</span>
        </div>
      </div>
      <div class="stat-card stat-card--success">
        <div class="stat-icon-wrap">
          <el-icon :size="28"><CircleCheck /></el-icon>
        </div>
        <div class="stat-body">
          <span class="stat-label">已完成</span>
          <span class="stat-value gt-count-up">{{ stats.completed }}</span>
        </div>
      </div>
    </div>

    <!-- 快捷入口 -->
    <div class="quick-actions gt-scale-in">
      <h2 class="gt-section-title">快捷操作</h2>
      <div class="action-grid">
        <div class="action-card" @click="$router.push('/projects/new')">
          <div class="action-icon" style="background: var(--gt-color-primary-bg); color: var(--gt-color-primary)">
            <el-icon :size="24"><Plus /></el-icon>
          </div>
          <span class="action-label">新建项目</span>
        </div>
        <div class="action-card" @click="$router.push('/projects')">
          <div class="action-icon" style="background: var(--gt-color-teal-light); color: var(--gt-color-teal)">
            <el-icon :size="24"><FolderOpened /></el-icon>
          </div>
          <span class="action-label">项目列表</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, onMounted } from 'vue'
import http from '@/utils/http'
import {
  Odometer, FolderOpened, Loading, Warning, CircleCheck, Plus,
} from '@element-plus/icons-vue'

const stats = reactive({ total: 0, inProgress: 0, pendingReview: 0, completed: 0 })

onMounted(async () => {
  try {
    const { data } = await http.get('/api/projects')
    const list = data.data ?? data ?? []
    stats.total = list.length
    stats.inProgress = list.filter((p: any) => p.status === 'execution').length
    stats.pendingReview = list.filter((p: any) => p.status === 'planning').length
    stats.completed = list.filter((p: any) => p.status === 'completion').length
  } catch { /* ignore */ }
})
</script>

<style scoped>
.gt-dashboard {
  max-width: 1200px;
}

.dashboard-welcome {
  margin-bottom: var(--gt-space-6);
}

.welcome-desc {
  color: var(--gt-color-text-secondary);
  margin-top: var(--gt-space-1);
  font-size: var(--gt-font-size-md);
}

/* ── 统计卡片 ── */
.stat-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: var(--gt-space-4);
  margin-bottom: var(--gt-space-8);
}

.stat-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  display: flex;
  align-items: center;
  gap: var(--gt-space-4);
  box-shadow: var(--gt-shadow-sm);
  transition: all var(--gt-transition-base);
  cursor: default;
  position: relative;
  overflow: hidden;
}

.stat-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 4px;
  height: 100%;
  border-radius: 0 2px 2px 0;
}

.stat-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--gt-shadow-md);
}

.stat-card--primary::before { background: var(--gt-color-primary); }
.stat-card--teal::before { background: var(--gt-color-teal); }
.stat-card--coral::before { background: var(--gt-color-coral); }
.stat-card--success::before { background: var(--gt-color-success); }

.stat-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: var(--gt-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-card--primary .stat-icon-wrap { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); }
.stat-card--teal .stat-icon-wrap { background: var(--gt-color-teal-light); color: var(--gt-color-teal); }
.stat-card--coral .stat-icon-wrap { background: var(--gt-color-coral-light); color: var(--gt-color-coral); }
.stat-card--success .stat-icon-wrap { background: var(--gt-color-success-light); color: var(--gt-color-success); }

.stat-body {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
}

.stat-value {
  font-size: var(--gt-font-size-3xl);
  font-weight: 700;
  color: var(--gt-color-text);
  line-height: 1.2;
  margin-top: 2px;
}

/* ── 快捷操作 ── */
.action-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: var(--gt-space-4);
}

.action-card {
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-5);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--gt-space-3);
  cursor: pointer;
  box-shadow: var(--gt-shadow-xs);
  transition: all var(--gt-transition-base);
  border: 1px solid transparent;
}

.action-card:hover {
  border-color: var(--gt-color-primary-lighter);
  box-shadow: var(--gt-shadow-md);
  transform: translateY(-2px);
}

.action-icon {
  width: 48px;
  height: 48px;
  border-radius: var(--gt-radius-md);
  display: flex;
  align-items: center;
  justify-content: center;
}

.action-label {
  font-size: var(--gt-font-size-base);
  font-weight: 500;
  color: var(--gt-color-text);
}
</style>
