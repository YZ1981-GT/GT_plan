<template>
  <div class="program-requirements-sidebar" :class="{ collapsed: isCollapsed }">
    <!-- 折叠切换按钮 -->
    <div class="sidebar-toggle" @click="toggleCollapse">
      <span v-if="!isCollapsed">◀</span>
      <span v-else>▶</span>
    </div>

    <!-- 侧栏内容 -->
    <div v-show="!isCollapsed" class="sidebar-content">
      <div class="sidebar-header">
        <h3 class="sidebar-title">📋 程序要求</h3>
        <el-button link size="small" @click="refreshData" :loading="loading">
          <el-icon><Refresh /></el-icon>
        </el-button>
      </div>

      <el-skeleton :loading="loading" :rows="6" animated>
        <template #default>
          <!-- 操作手册 -->
          <el-collapse v-model="activeNames">
            <el-collapse-item title="📖 底稿操作手册" name="manual" v-if="data.manual">
              <div class="manual-content">{{ data.manual }}</div>
            </el-collapse-item>

            <!-- 审计程序列表 -->
            <el-collapse-item name="procedures">
              <template #title>
                <span>📝 审计程序</span>
                <el-tag size="small" style="margin-left: 8px" v-if="data.procedures.length">
                  {{ completedCount }}/{{ data.procedures.length }}
                </el-tag>
              </template>
              <div v-if="!data.procedures.length" class="empty-hint">
                暂无关联的审计程序
              </div>
              <div
                v-for="proc in data.procedures"
                :key="proc.id"
                class="procedure-item"
                :class="{
                  highlighted: proc.procedure_code === highlightedProcedure,
                  completed: proc.execution_status === 'completed',
                }"
              >
                <div class="proc-header">
                  <span class="proc-code">{{ proc.procedure_code }}</span>
                  <el-tag
                    size="small"
                    :type="statusTagType(proc.execution_status)"
                  >
                    {{ statusLabel(proc.execution_status) }}
                  </el-tag>
                </div>
                <div class="proc-name">{{ proc.procedure_name }}</div>
                <div class="proc-actions">
                  <el-button
                    v-if="proc.execution_status !== 'completed'"
                    size="small"
                    type="success"
                    plain
                    :loading="proc._marking"
                    @click="markAsCompleted(proc)"
                  >
                    ✓ 标记为已完成
                  </el-button>
                  <el-tag
                    v-else
                    size="small"
                    type="success"
                    effect="light"
                  >
                    ✓ 已完成
                  </el-tag>
                </div>
              </div>
            </el-collapse-item>

            <!-- 上年结论摘要 -->
            <el-collapse-item title="📜 上年结论摘要" name="prior_year" v-if="data.prior_year_summary">
              <div class="prior-year-card">
                <div class="prior-year-meta">
                  <span class="meta-label">底稿编号：</span>
                  <span>{{ data.prior_year_summary.wp_code }}</span>
                </div>
                <div class="prior-year-meta">
                  <span class="meta-label">底稿名称：</span>
                  <span>{{ data.prior_year_summary.wp_name }}</span>
                </div>
                <div class="prior-year-meta">
                  <span class="meta-label">状态：</span>
                  <el-tag size="small">{{ data.prior_year_summary.status || '—' }}</el-tag>
                </div>
                <div class="prior-year-conclusion" v-if="data.prior_year_summary.conclusion">
                  <div class="meta-label">结论：</div>
                  <div class="conclusion-text">{{ data.prior_year_summary.conclusion }}</div>
                </div>
                <div v-else class="empty-hint">上年底稿无结论记录</div>
              </div>
            </el-collapse-item>
          </el-collapse>

          <!-- 无数据提示 -->
          <el-empty
            v-if="!data.manual && !data.procedures.length && !data.prior_year_summary"
            description="暂无程序要求数据"
            :image-size="60"
          />
        </template>
      </el-skeleton>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { updateProcedureTrim } from '@/services/commonApi'

// ─── Props ───
const props = defineProps<{
  projectId: string
  wpId: string
}>()

// ─── State ───
const route = useRoute()
const loading = ref(false)
const STORAGE_KEY = 'wp_sidebar_collapsed'

const isCollapsed = ref(false)
const activeNames = ref<string[]>(['procedures', 'manual', 'prior_year'])

interface ProcedureItem {
  id: string
  procedure_code: string
  procedure_name: string
  status: string
  execution_status: string
  sort_order: number
  assigned_to: string | null
  _marking?: boolean
}

interface PriorYearSummary {
  wp_id: string
  wp_code: string
  wp_name: string
  conclusion: string | null
  status: string | null
}

interface RequirementsData {
  manual: string | null
  procedures: ProcedureItem[]
  prior_year_summary: PriorYearSummary | null
}

const data = ref<RequirementsData>({
  manual: null,
  procedures: [],
  prior_year_summary: null,
})

// ─── Computed ───
const highlightedProcedure = computed(() => {
  return (route.query.from_procedure as string) || ''
})

const completedCount = computed(() => {
  return data.value.procedures.filter(p => p.execution_status === 'completed').length
})

// ─── Methods ───
function toggleCollapse() {
  isCollapsed.value = !isCollapsed.value
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(isCollapsed.value))
  } catch { /* localStorage 不可用时静默 */ }
}

function loadCollapseState() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored !== null) {
      isCollapsed.value = JSON.parse(stored)
    }
  } catch { /* 静默 */ }
}

function statusTagType(status: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  switch (status) {
    case 'completed': return 'success'
    case 'in_progress': return 'warning'
    case 'not_started': return 'info'
    default: return 'primary'
  }
}

function statusLabel(status: string): string {
  switch (status) {
    case 'completed': return '已完成'
    case 'in_progress': return '进行中'
    case 'not_started': return '未开始'
    default: return status || '未开始'
  }
}

async function fetchRequirements() {
  if (!props.projectId || !props.wpId) return
  loading.value = true
  try {
    const { data: result } = await http.get(
      `/api/projects/${props.projectId}/workpapers/${props.wpId}/requirements`
    )
    data.value = {
      manual: result.manual || null,
      procedures: (result.procedures || []).map((p: any) => ({ ...p, _marking: false })),
      prior_year_summary: result.prior_year_summary || null,
    }
  } catch (e: any) {
    // 静默处理，侧栏数据加载失败不阻断主流程
    console.warn('[ProgramRequirementsSidebar] 加载失败:', e?.message)
  } finally {
    loading.value = false
  }
}

async function refreshData() {
  await fetchRequirements()
}

async function markAsCompleted(proc: ProcedureItem) {
  if (!props.projectId) return
  proc._marking = true
  try {
    // 从 procedure_code 推断 audit_cycle（编号首字母）
    const cycle = proc.procedure_code?.charAt(0)?.toUpperCase() || ''
    if (!cycle) {
      ElMessage.warning('无法确定程序所属循环')
      return
    }
    await updateProcedureTrim(props.projectId, cycle, [
      { id: proc.id, status: proc.status || 'execute', execution_status: 'completed' },
    ])
    proc.execution_status = 'completed'
    ElMessage.success(`${proc.procedure_code} 已标记为完成`)
  } catch (e: any) {
    ElMessage.error('标记失败：' + (e?.message || '未知错误'))
  } finally {
    proc._marking = false
  }
}

// ─── Lifecycle ───
onMounted(() => {
  loadCollapseState()
  fetchRequirements()
})

// 当 wpId 变化时重新加载
watch(() => props.wpId, (newVal) => {
  if (newVal) fetchRequirements()
})
</script>

<style scoped>
.program-requirements-sidebar {
  position: relative;
  width: 280px;
  min-width: 280px;
  border-right: 1px solid var(--el-border-color-lighter, #ebeef5);
  background: var(--el-bg-color, #fff);
  display: flex;
  flex-direction: column;
  transition: width 0.2s ease, min-width 0.2s ease;
  overflow: hidden;
}

.program-requirements-sidebar.collapsed {
  width: 28px;
  min-width: 28px;
}

.sidebar-toggle {
  position: absolute;
  top: 12px;
  right: 4px;
  z-index: 10;
  width: 20px;
  height: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  border-radius: 4px;
  font-size: 12px;
  color: #909399;
  transition: background 0.2s;
}

.sidebar-toggle:hover {
  background: var(--el-fill-color-light, #f5f7fa);
  color: var(--el-color-primary, #409eff);
}

.sidebar-content {
  flex: 1;
  overflow-y: auto;
  padding: 12px;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding-right: 20px;
}

.sidebar-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

/* 操作手册 */
.manual-content {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular, #606266);
  white-space: pre-wrap;
  max-height: 200px;
  overflow-y: auto;
}

/* 程序条目 */
.procedure-item {
  padding: 8px 10px;
  margin-bottom: 6px;
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter, #ebeef5);
  transition: all 0.2s;
}

.procedure-item:hover {
  border-color: var(--el-color-primary-light-5, #a0cfff);
}

.procedure-item.highlighted {
  border-color: var(--el-color-primary, #409eff);
  background: var(--el-color-primary-light-9, #ecf5ff);
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.15);
}

.procedure-item.completed {
  opacity: 0.7;
  background: var(--el-color-success-light-9, #f0f9eb);
}

.proc-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 4px;
}

.proc-code {
  font-size: 12px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.proc-name {
  font-size: 12px;
  color: var(--el-text-color-regular, #606266);
  margin-bottom: 6px;
  line-height: 1.4;
}

.proc-actions {
  display: flex;
  justify-content: flex-end;
}

/* 上年结论 */
.prior-year-card {
  font-size: 12px;
}

.prior-year-meta {
  margin-bottom: 6px;
  display: flex;
  align-items: center;
  gap: 4px;
}

.meta-label {
  color: #909399;
  font-size: 12px;
  flex-shrink: 0;
}

.prior-year-conclusion {
  margin-top: 8px;
}

.conclusion-text {
  margin-top: 4px;
  padding: 8px;
  background: var(--el-fill-color-lighter, #fafafa);
  border-radius: 4px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--el-text-color-regular, #606266);
  max-height: 150px;
  overflow-y: auto;
}

.empty-hint {
  font-size: 12px;
  color: #c0c4cc;
  text-align: center;
  padding: 12px 0;
}

/* Element Plus Collapse 样式覆盖 */
:deep(.el-collapse) {
  border: none;
}

:deep(.el-collapse-item__header) {
  font-size: 13px;
  font-weight: 500;
  height: 36px;
  line-height: 36px;
  padding: 0 4px;
}

:deep(.el-collapse-item__content) {
  padding-bottom: 8px;
}

:deep(.el-collapse-item__wrap) {
  border-bottom: none;
}
</style>
