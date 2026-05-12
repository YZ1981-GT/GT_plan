<template>
  <div class="ch-page gt-fade-in">
    <!-- 顶部横幅 -->
    <div class="ch-banner">
      <div class="ch-banner-bg" />
      <div class="ch-banner-content">
        <div class="ch-banner-icon">
          <el-icon :size="36"><Connection /></el-icon>
        </div>
        <div>
          <h1 class="ch-banner-title">集团合并报表</h1>
          <p class="ch-banner-desc">选择合并项目，进入合并工作底稿、抵消分录、差额表、合并报表与附注</p>
        </div>
      </div>
    </div>

    <!-- 统计概览 -->
    <div class="ch-stats" v-if="!loading && projects.length > 0">
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ projects.length }}</span>
        <span class="ch-stat-label">合并项目</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ totalSubs }}</span>
        <span class="ch-stat-label">子公司</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ executingCount }}</span>
        <span class="ch-stat-label">执行中</span>
      </div>
      <div class="ch-stat-item">
        <span class="ch-stat-num">{{ completedCount }}</span>
        <span class="ch-stat-label">已完成</span>
      </div>
    </div>

    <!-- 项目卡片 -->
    <div v-loading="loading" class="ch-body">
      <el-empty v-if="!loading && projects.length === 0" description="暂无合并项目" :image-size="120">
        <template #description>
          <p style="color:#999;font-size:14px">还没有合并报表项目</p>
          <p style="color:#bbb;font-size:12px">请先在项目管理中创建报表范围为"合并"的项目</p>
        </template>
        <el-button type="primary" @click="$router.push('/projects/new')">
          <el-icon style="margin-right:4px"><Plus /></el-icon>新建合并项目
        </el-button>
      </el-empty>

      <div v-else class="ch-grid" :class="gridDensityClass">
        <div v-for="p in projects" :key="p.id" class="ch-card"
          @click="$router.push(`/projects/${p.id}/consolidation`)">
          <!-- 卡片顶部色条 -->
          <div class="ch-card-stripe" :class="'ch-stripe--' + (p.status || 'created')" />
          <div class="ch-card-body">
            <div class="ch-card-header">
              <div class="ch-card-avatar">
                <span>{{ (p.client_name || p.name || '?').charAt(0) }}</span>
              </div>
              <el-tag :type="(statusType(p.status)) || undefined" size="small" effect="light" round>
                {{ statusLabel(p.status) }}
              </el-tag>
            </div>
            <h3 class="ch-card-name">{{ p.client_name || p.name }}</h3>
            <div class="ch-card-info">
              <div class="ch-card-info-item">
                <el-icon :size="14"><Calendar /></el-icon>
                <span>{{ p.audit_year || '--' }} 年度</span>
              </div>
              <div class="ch-card-info-item" v-if="p.consol_level">
                <el-icon :size="14"><OfficeBuilding /></el-icon>
                <span>{{ p.consol_level }} 级架构</span>
              </div>
              <div class="ch-card-info-item" v-if="p.child_count">
                <el-icon :size="14"><Connection /></el-icon>
                <span>{{ p.child_count }} 个子公司</span>
              </div>
            </div>
            <!-- 进度条 -->
            <div class="ch-card-progress" v-if="p.status === 'execution'">
              <div class="ch-card-progress-bar">
                <div class="ch-card-progress-fill" :style="{ width: (p.progress || 30) + '%' }" />
              </div>
              <span class="ch-card-progress-text">{{ p.progress || 30 }}%</span>
            </div>
            <div class="ch-card-footer">
              <span class="ch-card-enter">进入合并 →</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Connection, Calendar, OfficeBuilding, Plus } from '@element-plus/icons-vue'
import { listProjects } from '@/services/commonApi'

const loading = ref(false)
const projects = ref<any[]>([])

const totalSubs = computed(() => projects.value.reduce((s, p) => s + (p.child_count || 0), 0))
const executingCount = computed(() => projects.value.filter(p => p.status === 'execution').length)
const completedCount = computed(() => projects.value.filter(p => p.status === 'completion').length)

// 根据项目数量动态调整网格密度
const gridDensityClass = computed(() => {
  const n = projects.value.length
  if (n <= 2) return 'ch-grid--sparse'    // 1-2个：大卡片，最多2列
  if (n <= 6) return 'ch-grid--normal'    // 3-6个：标准卡片，自适应
  if (n <= 15) return 'ch-grid--compact'  // 7-15个：紧凑卡片，更多列
  return 'ch-grid--dense'                  // 16+：密集列表式
})

function statusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  return ({ created: 'info', planning: '', execution: 'warning', completion: 'success', archived: 'info' } as Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'>)[s] || 'info'
}
function statusLabel(s: string) {
  return ({ created: '已创建', planning: '计划中', execution: '执行中', completion: '已完成', archived: '已归档' } as Record<string, string>)[s] || s
}

onMounted(async () => {
  loading.value = true
  try {
    const all = await listProjects()
    projects.value = all.filter((p: any) =>
      p.report_scope === 'consolidated' || (p.parent_project_id === null && p.consol_level > 0)
    )
  } catch { projects.value = [] }
  finally { loading.value = false }
})
</script>

<style scoped>
.ch-page { padding: 0; }

/* ── 横幅 ── */
.ch-banner {
  position: relative; padding: 32px 32px 24px; overflow: hidden;
  border-radius: 0 0 16px 16px;
}
.ch-banner-bg {
  position: absolute; inset: 0;
  background: linear-gradient(135deg, #4b2d77 0%, #7c5caa 50%, #a78bcc 100%);
  opacity: 0.95;
}
.ch-banner-content {
  position: relative; z-index: 1; display: flex; align-items: center; gap: 20px;
}
.ch-banner-icon {
  width: 64px; height: 64px; border-radius: 16px;
  background: rgba(255,255,255,0.15); backdrop-filter: blur(8px);
  display: flex; align-items: center; justify-content: center; color: #fff;
  flex-shrink: 0;
}
.ch-banner-title { margin: 0; font-size: 24px; font-weight: 700; color: #fff; }
.ch-banner-desc { margin: 6px 0 0; font-size: 14px; color: rgba(255,255,255,0.8); }

/* ── 统计 ── */
.ch-stats {
  display: flex; gap: 0; margin: -20px 32px 0; position: relative; z-index: 2;
  background: #fff; border-radius: 12px; box-shadow: 0 4px 20px rgba(75,45,119,0.08);
  overflow: hidden;
}
.ch-stat-item {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  padding: 16px 12px; border-right: 1px solid #f0edf5;
}
.ch-stat-item:last-child { border-right: none; }
.ch-stat-num { font-size: 28px; font-weight: 700; color: #4b2d77; line-height: 1.2; }
.ch-stat-label { font-size: 12px; color: #999; margin-top: 4px; }

/* ── 主体 ── */
.ch-body { padding: 24px 32px 32px; }

/* ── 卡片网格（密度自适应） ── */
.ch-grid {
  display: grid; gap: 20px;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
}
/* 1-2个项目：大卡片，最多2列 */
.ch-grid--sparse {
  grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 20px;
}
.ch-grid--sparse .ch-card-body { padding: 20px; }
.ch-grid--sparse .ch-card-name { font-size: 16px; }
.ch-grid--sparse .ch-card-avatar { width: 42px; height: 42px; font-size: 18px; border-radius: 10px; }
.ch-grid--sparse .ch-card-info-item { font-size: 13px; }
.ch-grid--sparse .ch-card-enter { font-size: 13px; }

/* 3-6个项目：标准 */
.ch-grid--normal {
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 18px;
}

/* 7-15个项目：紧凑 */
.ch-grid--compact {
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr)); gap: 14px;
}
.ch-grid--compact .ch-card-body { padding: 14px; }
.ch-grid--compact .ch-card-name { font-size: 15px; margin-bottom: 8px; }
.ch-grid--compact .ch-card-avatar { width: 32px; height: 32px; font-size: 14px; border-radius: 8px; }
.ch-grid--compact .ch-card-header { margin-bottom: 8px; }
.ch-grid--compact .ch-card-info { gap: 4px; margin-bottom: 10px; }
.ch-grid--compact .ch-card-info-item { font-size: 12px; }
.ch-grid--compact .ch-card-footer { padding-top: 8px; }
.ch-grid--compact .ch-card-enter { font-size: 12px; }

/* 16+个项目：密集列表式 */
.ch-grid--dense {
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 10px;
}
.ch-grid--dense .ch-card { border-radius: 8px; }
.ch-grid--dense .ch-card-stripe { height: 3px; }
.ch-grid--dense .ch-card-body { padding: 10px 12px; }
.ch-grid--dense .ch-card-header { margin-bottom: 6px; }
.ch-grid--dense .ch-card-avatar { width: 28px; height: 28px; font-size: 12px; border-radius: 6px; }
.ch-grid--dense .ch-card-name { font-size: 13px; margin-bottom: 6px; line-height: 1.3; }
.ch-grid--dense .ch-card-info { gap: 2px; margin-bottom: 6px; }
.ch-grid--dense .ch-card-info-item { font-size: 11px; }
.ch-grid--dense .ch-card-progress { margin-bottom: 6px; }
.ch-grid--dense .ch-card-progress-bar { height: 4px; }
.ch-grid--dense .ch-card-footer { padding-top: 6px; }
.ch-grid--dense .ch-card-enter { font-size: 11px; }

.ch-card {
  background: #fff; border-radius: 12px; overflow: hidden; cursor: pointer;
  border: 1px solid #f0edf5; transition: all 0.2s ease;
  box-shadow: 0 2px 8px rgba(0,0,0,0.03);
}
.ch-card:hover {
  border-color: #4b2d77; box-shadow: 0 8px 24px rgba(75,45,119,0.12);
  transform: translateY(-3px);
}

/* 顶部色条 */
.ch-card-stripe { height: 4px; }
.ch-stripe--created { background: linear-gradient(90deg, #909399, #c0c4cc); }
.ch-stripe--planning { background: linear-gradient(90deg, #409eff, #79bbff); }
.ch-stripe--execution { background: linear-gradient(90deg, #e6a23c, #f0c78a); }
.ch-stripe--completion { background: linear-gradient(90deg, #67c23a, #95d475); }
.ch-stripe--archived { background: linear-gradient(90deg, #909399, #c0c4cc); }

.ch-card-body { padding: 20px; }

.ch-card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.ch-card-avatar {
  width: 40px; height: 40px; border-radius: 10px;
  background: linear-gradient(135deg, #4b2d77, #7c5caa);
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 18px; font-weight: 700;
}

.ch-card-name {
  margin: 0 0 10px; font-size: 15px; font-weight: 600; color: #1a1a2e;
  line-height: 1.4;
}

.ch-card-info { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; }
.ch-card-info-item {
  display: flex; align-items: center; gap: 6px;
  font-size: 13px; color: #666;
}
.ch-card-info-item .el-icon { color: #999; }

/* 进度条 */
.ch-card-progress { display: flex; align-items: center; gap: 8px; margin-bottom: 14px; }
.ch-card-progress-bar {
  flex: 1; height: 6px; background: #f0edf5; border-radius: 3px; overflow: hidden;
}
.ch-card-progress-fill {
  height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, #4b2d77, #7c5caa);
  transition: width 0.3s ease;
}
.ch-card-progress-text { font-size: 12px; color: #4b2d77; font-weight: 600; min-width: 32px; }

.ch-card-footer {
  padding-top: 12px; border-top: 1px solid #f5f3f8;
}
.ch-card-enter {
  font-size: 13px; color: #4b2d77; font-weight: 500;
  opacity: 0.6; transition: opacity 0.15s;
}
.ch-card:hover .ch-card-enter { opacity: 1; }

/* ── 响应式 ── */
@media (max-width: 768px) {
  .ch-banner { padding: 20px 16px 16px; }
  .ch-stats { margin: -16px 16px 0; }
  .ch-body { padding: 16px; }
  .ch-grid { grid-template-columns: 1fr; }
}
</style>
