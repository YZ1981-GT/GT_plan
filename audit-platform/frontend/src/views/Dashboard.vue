<template>
  <div class="dashboard-container">
    <!-- Top-left: Project Progress Cards -->
    <div class="panel project-panel">
      <div class="panel-header">
        <h3>项目进度</h3>
        <el-button size="small" link @click="refreshProjects">刷新</el-button>
      </div>
      <div class="project-list" v-if="projects.length > 0">
        <div v-for="project in projects" :key="project.id" class="project-card">
          <div class="project-card-header">
            <span class="project-name">{{ project.name }}</span>
            <el-tag :type="getStatusType(project.status)" size="small">{{ project.status }}</el-tag>
          </div>
          <el-progress :percentage="project.progress" :stroke-width="6" :show-text="false" />
          <div class="project-card-footer">
            <span class="deadline">截止: {{ project.deadline }}</span>
            <span class="progress-text">{{ project.progress }}%</span>
          </div>
        </div>
      </div>
      <div v-else class="placeholder">
        <el-empty description="暂无项目数据" :image-size="60" />
      </div>
    </div>

    <!-- Top-right: Risk Alert List -->
    <div class="panel risk-panel">
      <div class="panel-header">
        <h3>风险预警</h3>
        <el-badge :value="riskAlerts.filter(a => a.severity === 'HIGH').length" type="danger">
          <el-icon><Warning /></el-icon>
        </el-badge>
      </div>
      <div class="alert-list" v-if="riskAlerts.length > 0">
        <div v-for="(alert, index) in riskAlerts" :key="index" class="alert-item">
          <div class="alert-item-header">
            <span class="alert-type">{{ alert.type }}</span>
            <el-tag :type="getSeverityType(alert.severity)" size="small">{{ alert.severity }}</el-tag>
          </div>
          <p class="alert-desc">{{ alert.description }}</p>
        </div>
      </div>
      <div v-else class="placeholder">
        <el-empty description="暂无预警信息" :image-size="60" />
      </div>
    </div>

    <!-- Bottom-left: Staff Work Hours Bar Chart -->
    <div class="panel workhours-panel">
      <div class="panel-header">
        <h3>工时统计</h3>
        <el-select v-model="workHoursMonth" size="small" style="width: 120px" @change="fetchWorkHours">
          <el-option v-for="m in monthOptions" :key="m.value" :label="m.label" :value="m.value" />
        </el-select>
      </div>
      <div class="bar-chart" v-if="workHoursData.length > 0">
        <div v-for="item in workHoursData" :key="item.staff" class="bar-row">
          <span class="bar-label">{{ item.staff }}</span>
          <div class="bar-track">
            <div
              class="bar-fill"
              :style="{ width: getBarWidth(item.hours) + '%' }"
              :class="{ 'bar-warning': item.hours > 160, 'bar-normal': item.hours <= 160 }"
            ></div>
          </div>
          <span class="bar-value">{{ item.hours }}h</span>
        </div>
      </div>
      <div v-else class="placeholder">
        <el-empty description="暂无工时数据" :image-size="60" />
      </div>
    </div>

    <!-- Bottom-right: Report Status Pie Chart -->
    <div class="panel report-panel">
      <div class="panel-header">
        <h3>报告状态</h3>
        <el-button size="small" link @click="fetchReportStatus">刷新</el-button>
      </div>
      <div class="report-chart" v-if="reportStatusData.length > 0">
        <div class="pie-container">
          <div class="pie-legend">
            <div v-for="item in reportStatusData" :key="item.label" class="legend-item">
              <span class="legend-dot" :style="{ background: item.color }"></span>
              <span class="legend-label">{{ item.label }}</span>
              <span class="legend-value">{{ item.count }}</span>
            </div>
          </div>
          <div class="pie-visual">
            <div
              v-for="(item, index) in reportStatusData"
              :key="index"
              class="pie-slice"
              :style="getPieStyle(item, index)"
            ></div>
          </div>
        </div>
      </div>
      <div v-else class="placeholder">
        <el-empty description="暂无报告数据" :image-size="60" />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Warning } from '@element-plus/icons-vue'
import { projectMgmtApi } from '@/services/collaborationApi'

// Placeholder project ID
const projectId = 'current-project-id'

// ── Project Progress ────────────────────────────────────────────
const projects = ref<any[]>([
  { id: '1', name: 'ABC公司2024年度审计', status: '进行中', progress: 65, deadline: '2025-04-30' },
  { id: '2', name: 'XYZ集团年报审计', status: '待启动', progress: 0, deadline: '2025-06-30' },
  { id: '3', name: 'DEF公司IPO审计', status: '已完成', progress: 100, deadline: '2025-03-31' },
])

function getStatusType(status: string) {
  const map: Record<string, string> = {
    '进行中': 'primary',
    '待启动': 'info',
    '已完成': 'success',
    '暂停': 'warning',
  }
  return (map[status] ?? 'info') as any
}

function refreshProjects() {
  // Placeholder refresh
}

// ── Risk Alerts ──────────────────────────────────────────────────
const riskAlerts = ref<any[]>([
  { type: '进度超期', description: 'ABC公司审计项目进度滞后超过15天', severity: 'HIGH' },
  { type: 'PBC缺失', description: 'XYZ集团银行询证函尚未收回', severity: 'MEDIUM' },
  { type: '调整未确认', description: '有3笔重大调整分录待项目经理确认', severity: 'LOW' },
  { type: '复核超时', description: '收入循环工作底稿复核超时5天', severity: 'MEDIUM' },
])

function getSeverityType(severity: string) {
  const map: Record<string, string> = {
    'HIGH': 'danger',
    'MEDIUM': 'warning',
    'LOW': 'info',
  }
  return (map[severity] ?? 'info') as any
}

// ── Work Hours ───────────────────────────────────────────────────
const workHoursMonth = ref('2025-01')
const monthOptions = [
  { label: '2025-01', value: '2025-01' },
  { label: '2025-02', value: '2025-02' },
  { label: '2025-03', value: '2025-03' },
]
const workHoursData = ref<any[]>([
  { staff: '张三', hours: 145 },
  { staff: '李四', hours: 168 },
  { staff: '王五', hours: 120 },
  { staff: '赵六', hours: 152 },
  { staff: '孙七', hours: 80 },
])

const maxHours = computed(() => Math.max(...workHoursData.value.map(d => d.hours), 200))

function getBarWidth(hours: number) {
  return Math.min((hours / maxHours.value) * 100, 100)
}

function fetchWorkHours() {
  // Placeholder: call projectMgmtApi.getWorkHours(projectId)
}

// ── Report Status ────────────────────────────────────────────────
const reportStatusData = ref<any[]>([
  { label: '已完成', count: 5, color: '#67c23a' },
  { label: '进行中', count: 8, color: '#409eff' },
  { label: '待复核', count: 3, color: '#e6a23c' },
  { label: '未开始', count: 2, color: '#909399' },
])

const totalReport = computed(() => reportStatusData.value.reduce((s, d) => s + d.count, 0))

function getPieStyle(item: any, index: number) {
  const total = totalReport.value
  if (total === 0) return {}
  const startPercent = reportStatusData.value.slice(0, index).reduce((s, d) => s + (d.count / total) * 100, 0)
  const endPercent = startPercent + (item.count / total) * 100
  return {
    background: item.color,
    clipPath: `polygon(50% 50%, 50% 0%, ${getConicGradientPoint(endPercent)} 0%, ${getConicGradientPoint(endPercent)} 100%, ${getConicGradientPoint(startPercent)} 100%, ${getConicGradientPoint(startPercent)} 0%)`,
  }
}

function getConicGradientPoint(percent: number) {
  const angle = (percent / 100) * 360
  const rad = (angle - 90) * (Math.PI / 180)
  const x = 50 + 50 * Math.cos(rad)
  const y = 50 + 50 * Math.sin(rad)
  return `${x}% ${y}%`
}

function fetchReportStatus() {
  // Placeholder: call projectMgmtApi.getReportStatus(projectId)
}

onMounted(() => {
  // Attempt to load real data
  projectMgmtApi.getTimeline(projectId).catch(() => {
    // Use mock data if API not ready
  })
})
</script>

<style scoped>
.dashboard-container {
  display: grid;
  grid-template-columns: 1fr 1fr;
  grid-template-rows: 1fr 1fr;
  gap: 16px;
  height: calc(100vh - 120px);
  padding: 16px;
}

.panel {
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.08);
  padding: 16px;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-shrink: 0;
}

.panel-header h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

/* Project Cards */
.project-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  flex: 1;
}

.project-card {
  border: 1px solid #ebeef5;
  border-radius: 6px;
  padding: 10px 12px;
  background: #fafafa;
}

.project-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}

.project-name {
  font-size: 13px;
  font-weight: 500;
  color: #303133;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  margin-right: 8px;
}

.project-card-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: 4px;
}

.deadline,
.progress-text {
  font-size: 11px;
  color: #909399;
}

/* Alert List */
.alert-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}

.alert-item {
  border-left: 3px solid #e6a23c;
  padding: 6px 10px;
  background: #fdf6ec;
  border-radius: 0 4px 4px 0;
}

.alert-item-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 2px;
}

.alert-type {
  font-size: 12px;
  font-weight: 600;
  color: #303133;
}

.alert-desc {
  font-size: 12px;
  color: #606266;
  margin: 0;
  line-height: 1.4;
}

/* Work Hours Bar Chart */
.bar-chart {
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow-y: auto;
  flex: 1;
}

.bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.bar-label {
  width: 50px;
  font-size: 12px;
  color: #606266;
  flex-shrink: 0;
  text-align: right;
}

.bar-track {
  flex: 1;
  height: 16px;
  background: #f0f2f5;
  border-radius: 8px;
  overflow: hidden;
}

.bar-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.3s ease;
}

.bar-normal {
  background: #409eff;
}

.bar-warning {
  background: #e6a23c;
}

.bar-value {
  width: 36px;
  font-size: 11px;
  color: #909399;
  flex-shrink: 0;
}

/* Report Status */
.report-chart {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.pie-container {
  display: flex;
  align-items: center;
  gap: 24px;
}

.pie-visual {
  width: 140px;
  height: 140px;
  border-radius: 50%;
  background: conic-gradient(
    #67c23a 0deg 67.5deg,
    #409eff 67.5deg 175.5deg,
    #e6a23c 175.5deg 216deg,
    #909399 216deg 360deg
  );
  position: relative;
}

.pie-visual::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  width: 70px;
  height: 70px;
  border-radius: 50%;
  background: #fff;
}

.pie-slice {
  display: none;
}

.pie-legend {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend-label {
  color: #606266;
}

.legend-value {
  font-weight: 600;
  color: #303133;
  margin-left: 4px;
}

/* Placeholder */
.placeholder {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
</style>
