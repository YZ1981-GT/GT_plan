<template>
  <div class="role-workbench-shell">
    <div class="workbench-header">
      <h2 class="workbench-title">{{ roleTitle }}</h2>
      <el-tag :type="roleTagType" size="large">{{ roleName }}</el-tag>
    </div>

    <div v-if="loading" class="workbench-loading">
      <el-skeleton :rows="6" animated />
    </div>

    <div v-else-if="error" class="workbench-error">
      <el-empty description="作业台数据加载失败">
        <template #image>
          <el-icon :size="64" color="var(--gt-color-primary)"><Warning /></el-icon>
        </template>
        <el-button type="primary" @click="fetchWorkbench">重试</el-button>
      </el-empty>
    </div>

    <div v-else class="workbench-sections">
      <div
        v-for="section in sections"
        :key="section.id"
        class="workbench-section"
      >
        <h3 class="section-title">{{ section.title }}</h3>
        <div v-if="section.items.length === 0" class="section-empty">
          暂无数据
        </div>
        <div v-else class="section-items">
          <div
            v-for="item in section.items"
            :key="item.id"
            class="workbench-item"
            :class="[`priority-${item.priority}`]"
            @click="handleItemClick(item)"
          >
            <div class="item-content">
              <span class="item-label">{{ item.label }}</span>
              <el-tag
                v-if="item.priority === 'critical'"
                type="danger"
                size="small"
              >
                紧急
              </el-tag>
              <el-tag
                v-else-if="item.priority === 'high'"
                type="warning"
                size="small"
              >
                高
              </el-tag>
            </div>
            <div class="item-meta">
              <span v-if="item.due_date" class="item-due">
                截止: {{ formatDate(item.due_date) }}
              </span>
              <span v-if="item.missing_reason" class="item-missing">
                {{ formatMissingReason(item.missing_reason) }}
              </span>
              <el-icon v-if="item.route" class="item-arrow"><ArrowRight /></el-icon>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * RoleWorkbenchShell.vue — 角色作业台外壳组件
 *
 * 根据当前用户系统角色调用后端 API 获取对应的 sections，
 * 接入 ProjectContext 和 PermissionMatrix。
 */
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useProjectStore } from '@/stores/project'
import { useAuthStore } from '@/stores/auth'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { api } from '@/services/apiProxy'
import { Warning, ArrowRight } from '@element-plus/icons-vue'

// ─── Types ────────────────────────────────────────────────────────────────────

interface WorkbenchItem {
  id: string
  label: string
  priority: string
  route?: string
  missing_reason?: string
  due_date?: string
  source?: string
  metric?: Record<string, unknown>
}

interface WorkbenchSection {
  id: string
  title: string
  items: WorkbenchItem[]
}

// ─── State ────────────────────────────────────────────────────────────────────

const router = useRouter()
const route = useRoute()
const projectStore = useProjectStore()
const authStore = useAuthStore()
const { currentRole } = usePermissionMatrix()

const loading = ref(false)
const error = ref(false)
const sections = ref<WorkbenchSection[]>([])

// ─── Computed ─────────────────────────────────────────────────────────────────

const projectId = computed(() => route.params.projectId as string || projectStore.projectId)

const effectiveRole = computed(() => {
  const role = currentRole.value
  // 映射到 facade 支持的三类角色
  if (role === 'admin' || role === 'partner') return 'partner'
  if (role === 'manager') return 'manager'
  return 'auditor' // auditor, qc 等默认走 auditor
})

const roleTitle = computed(() => {
  const titles: Record<string, string> = {
    auditor: '审计助理作业台',
    manager: '项目经理驾驶舱',
    partner: '合伙人风险雷达',
  }
  return titles[effectiveRole.value] || '角色作业台'
})

const roleName = computed(() => {
  const names: Record<string, string> = {
    auditor: '助理',
    manager: '经理',
    partner: '合伙人',
  }
  return names[effectiveRole.value] || currentRole.value
})

const roleTagType = computed(() => {
  const types: Record<string, string> = {
    auditor: '',
    manager: 'warning',
    partner: 'danger',
  }
  return types[effectiveRole.value] || ''
})

// ─── Methods ──────────────────────────────────────────────────────────────────

async function fetchWorkbench() {
  if (!projectId.value) return

  loading.value = true
  error.value = false

  try {
    const data = await api.get(
      `/api/projects/${projectId.value}/role-workbench`,
      { params: { role: effectiveRole.value } }
    )
    sections.value = data.sections || []
  } catch (e) {
    console.error('[RoleWorkbench] fetch failed:', e)
    error.value = true
    sections.value = []
  } finally {
    loading.value = false
  }
}

function handleItemClick(item: WorkbenchItem) {
  if (item.route) {
    router.push(item.route)
  }
}

function formatDate(isoDate: string): string {
  try {
    const d = new Date(isoDate)
    return `${d.getMonth() + 1}/${d.getDate()}`
  } catch {
    return isoDate
  }
}

function formatMissingReason(reason: string): string {
  const reasonMap: Record<string, string> = {
    budget_hours_field_missing: '预算数据暂缺',
    material_not_received: '资料未回收',
    route_not_available: '跳转不可用',
    pbc_service_unavailable: '资料服务暂不可用',
    ai_gate_unavailable: 'AI 状态暂不可用',
    workhour_service_error: '工时服务异常',
    risk_service_error: '风险服务异常',
    adjustment_service_error: '调整服务异常',
    no_workhour_data: '暂无工时数据',
  }
  return reasonMap[reason] || reason
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(() => {
  fetchWorkbench()
})

watch(projectId, () => {
  fetchWorkbench()
})
</script>

<style scoped>
.role-workbench-shell {
  max-width: 1200px;
  margin: 0 auto;
}

.workbench-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 24px;
}

.workbench-title {
  margin: 0;
  font-size: 20px;
  color: var(--gt-color-text-primary, #303133);
}

.workbench-loading {
  padding: 40px 0;
}

.workbench-sections {
  display: grid;
  gap: 20px;
}

.workbench-section {
  background: #fff;
  border-radius: 8px;
  padding: 20px;
  border: 1px solid var(--gt-color-border-purple-light, #d8b8ee);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.04);
}

.section-title {
  margin: 0 0 12px 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
}

.section-empty {
  color: var(--el-text-color-secondary);
  font-size: 13px;
  padding: 8px 0;
}

.section-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.workbench-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.2s;
  border: 1px solid transparent;
}

.workbench-item:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
  border-color: var(--gt-color-border-purple-light, #d8b8ee);
}

.workbench-item.priority-critical {
  border-left: 3px solid var(--el-color-danger);
}

.workbench-item.priority-high {
  border-left: 3px solid var(--el-color-warning);
}

.item-content {
  display: flex;
  align-items: center;
  gap: 8px;
}

.item-label {
  font-size: 14px;
  color: var(--gt-color-text-primary, #303133);
}

.item-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.item-due {
  color: var(--el-color-warning);
}

.item-missing {
  color: var(--el-text-color-placeholder);
  font-style: italic;
}

.item-arrow {
  color: var(--gt-color-primary, #4b2d77);
}
</style>
