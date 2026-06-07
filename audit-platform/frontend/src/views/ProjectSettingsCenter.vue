<!--
  ProjectSettingsCenter — 项目设置中心 [P1-2]
  [platform-context-permission-foundation P1-2]

  聚合项目配置的集中管理入口，通过 el-tabs 分 6 个 Tab：
  1. 基本信息 — 项目名称、客户、负责人
  2. 年度准则 — 审计年度、适用准则、审计范围
  3. 成员职责 — 项目团队成员与职责分配
  4. 权限 — 权限矩阵查看（仅 manager/partner/admin 可见）
  5. 模板 — 底稿模板选择与管理
  6. 锁定策略 — 归档/签发/只读/紧急解锁

  权限控制：
  - 审计助理不可见"权限"Tab（Requirements 4.1 UAT）
  - 只有 manager/partner/admin 可调整成员职责
  - signed/archived 状态下大部分设置只读
-->
<template>
  <GtPageShell :header-props="{ title: '项目设置中心', showBack: true, backMode: 'history' }">
    <template #context>
      <ProjectContextBar :show-year-switcher="false" />
    </template>

    <div class="project-settings-center">
      <el-tabs v-model="activeTab" type="border-card" class="project-settings-center__tabs">
        <!-- Tab 1: 基本信息 -->
        <el-tab-pane label="基本信息" name="basic">
          <div class="settings-panel">
            <h3 class="settings-panel__title">项目基本信息</h3>
            <el-form label-width="100px" :disabled="isReadonly">
              <el-form-item label="项目名称">
                <el-input v-model="basicInfo.projectName" placeholder="项目名称" />
              </el-form-item>
              <el-form-item label="客户名称">
                <el-input v-model="basicInfo.clientName" placeholder="客户名称" />
              </el-form-item>
              <el-form-item label="项目负责人">
                <el-input v-model="basicInfo.manager" placeholder="项目负责人" disabled />
              </el-form-item>
              <el-form-item label="创建时间">
                <el-input v-model="basicInfo.createdAt" disabled />
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- Tab 2: 年度准则 -->
        <el-tab-pane label="年度准则" name="standard">
          <div class="settings-panel">
            <h3 class="settings-panel__title">年度与准则设置</h3>
            <el-form label-width="100px" :disabled="isReadonly">
              <el-form-item label="审计年度">
                <el-select v-model="standardInfo.year" placeholder="选择年度">
                  <el-option
                    v-for="y in yearOptions"
                    :key="y"
                    :label="`${y} 年度`"
                    :value="y"
                  />
                </el-select>
              </el-form-item>
              <el-form-item label="适用准则">
                <el-select v-model="standardInfo.standard" placeholder="选择准则">
                  <el-option label="国企准则" value="soe" />
                  <el-option label="上市公司准则" value="listed" />
                  <el-option label="民营准则" value="private" />
                </el-select>
              </el-form-item>
              <el-form-item label="审计范围">
                <el-radio-group v-model="standardInfo.scope">
                  <el-radio value="standalone">单体审计</el-radio>
                  <el-radio value="consolidated">合并审计</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>

        <!-- Tab 3: 成员职责 -->
        <el-tab-pane label="成员职责" name="members">
          <div class="settings-panel">
            <h3 class="settings-panel__title">项目团队成员</h3>
            <div class="settings-panel__toolbar" v-if="canManageMembers">
              <el-button type="primary" size="small" @click="onAddMember">
                添加成员
              </el-button>
            </div>
            <el-table :data="members" stripe border size="small" class="settings-panel__table">
              <el-table-column prop="name" label="姓名" width="120" />
              <el-table-column prop="role" label="项目职责" width="140">
                <template #default="{ row }">
                  <el-select
                    v-if="canManageMembers"
                    v-model="row.role"
                    size="small"
                    @change="onRoleChange(row)"
                  >
                    <el-option label="编制人" value="auditor" />
                    <el-option label="复核人" value="reviewer" />
                    <el-option label="项目经理" value="manager" />
                    <el-option label="签字合伙人" value="signing_partner" />
                    <el-option label="独立复核" value="eqcr" />
                    <el-option label="质控" value="qc" />
                  </el-select>
                  <span v-else>{{ roleLabel(row.role) }}</span>
                </template>
              </el-table-column>
              <el-table-column prop="systemRole" label="系统角色" width="120" />
              <el-table-column prop="email" label="邮箱" />
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Tab 4: 权限（仅 manager/partner/admin 可见） -->
        <el-tab-pane
          v-if="canViewPermissions"
          label="权限"
          name="permissions"
        >
          <div class="settings-panel">
            <h3 class="settings-panel__title">权限矩阵</h3>
            <p class="settings-panel__desc">
              权限基于系统角色与项目职责自动计算。如需临时授权请联系项目经理。
            </p>
            <el-table :data="permissionRows" stripe border size="small">
              <el-table-column prop="operation" label="操作" width="200" />
              <el-table-column prop="allowed" label="是否允许" width="100">
                <template #default="{ row }">
                  <el-tag :type="row.allowed ? 'success' : 'danger'" size="small">
                    {{ row.allowed ? '允许' : '拒绝' }}
                  </el-tag>
                </template>
              </el-table-column>
              <el-table-column prop="reason" label="说明" />
            </el-table>
          </div>
        </el-tab-pane>

        <!-- Tab 5: 模板 -->
        <el-tab-pane label="模板" name="templates">
          <div class="settings-panel">
            <h3 class="settings-panel__title">底稿模板</h3>
            <p class="settings-panel__desc">
              项目使用的底稿模板版本。模板变更需项目经理确认。
            </p>
            <el-empty description="模板管理功能开发中" />
          </div>
        </el-tab-pane>

        <!-- Tab 6: 锁定策略 -->
        <el-tab-pane label="锁定策略" name="locking">
          <div class="settings-panel">
            <h3 class="settings-panel__title">锁定与归档策略</h3>
            <el-form label-width="120px" :disabled="!canManageMembers">
              <el-form-item label="项目状态">
                <el-tag :type="statusType" size="default">{{ statusLabel }}</el-tag>
              </el-form-item>
              <el-form-item label="只读模式">
                <el-switch
                  v-model="lockingInfo.readonlyMode"
                  active-text="启用"
                  inactive-text="关闭"
                  :disabled="isReadonly"
                />
              </el-form-item>
              <el-form-item label="说明">
                <span class="settings-panel__desc">
                  签发或归档后项目自动进入只读模式，底稿/报表/附注不可编辑。
                  如需紧急解锁请使用临时授权功能。
                </span>
              </el-form-item>
            </el-form>
          </div>
        </el-tab-pane>
      </el-tabs>
    </div>
  </GtPageShell>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import GtPageShell from '@/components/common/GtPageShell.vue'
import ProjectContextBar from '@/components/common/ProjectContextBar.vue'
import { useProjectStore } from '@/stores/project'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { api } from '@/services/apiProxy'

defineOptions({ name: 'ProjectSettingsCenter' })

const route = useRoute()
const projectStore = useProjectStore()
const { can, whyCannot, currentRole } = usePermissionMatrix()

const projectId = computed(() => route.params.projectId as string)
const ctx = computed(() => projectStore.currentProjectContext)
const yearOptions = computed(() => projectStore.yearOptions)

const activeTab = ref('basic')

// ─── 权限判断 ───
const canViewPermissions = computed(() => {
  return ['admin', 'partner', 'manager'].includes(currentRole.value)
})

const canManageMembers = computed(() => {
  return ['admin', 'partner', 'manager'].includes(currentRole.value)
})

const isReadonly = computed(() => {
  return ['signed', 'archived'].includes(ctx.value.projectStatus)
})

// ─── Tab 1: 基本信息 ───
const basicInfo = ref({
  projectName: '',
  clientName: '',
  manager: '',
  createdAt: '',
})

// ─── Tab 2: 年度准则 ───
const standardInfo = ref({
  year: 0,
  standard: 'soe',
  scope: 'standalone' as 'standalone' | 'consolidated',
})

// ─── Tab 3: 成员职责 ───
const members = ref<Array<{
  id: string
  name: string
  role: string
  systemRole: string
  email: string
}>>([])

function roleLabel(role: string): string {
  const map: Record<string, string> = {
    auditor: '编制人',
    reviewer: '复核人',
    manager: '项目经理',
    signing_partner: '签字合伙人',
    eqcr: '独立复核',
    qc: '质控',
    readonly: '只读',
  }
  return map[role] || role
}

function onAddMember() {
  // 后续实现：打开添加成员弹窗
}

function onRoleChange(row: any) {
  // 调用后端 API 更新成员职责
  updateMemberRole(row.id, row.role)
}

async function updateMemberRole(staffId: string, role: string) {
  try {
    await api.put(`/api/projects/${projectId.value}/assignments/${staffId}`, { role })
  } catch {
    // 静默处理
  }
}

// ─── Tab 4: 权限矩阵展示 ───
const OPERATION_LABELS: Record<string, string> = {
  'project:view': '查看项目',
  'wp:edit': '编辑底稿',
  'wp:review': '复核底稿',
  'report:edit': '编辑报表',
  'report:sign': '签发报表',
  'note:edit': '编辑附注',
  'archive:manage': '归档管理',
}

const permissionRows = computed(() => {
  return Object.entries(OPERATION_LABELS).map(([code, label]) => ({
    operation: label,
    allowed: can(code),
    reason: whyCannot(code) || '当前角色允许此操作',
  }))
})

// ─── Tab 6: 锁定策略 ───
const lockingInfo = ref({
  readonlyMode: false,
})

const statusLabel = computed(() => {
  const map: Record<string, string> = {
    draft: '草稿', created: '已创建', planning: '计划中',
    active: '执行中', execution: '执行中', signed: '已签发',
    archived: '已归档', completion: '已完成', reporting: '报告',
  }
  return map[ctx.value.projectStatus] || ctx.value.projectStatus || '—'
})

const statusType = computed(() => {
  const map: Record<string, string> = {
    draft: 'info', created: 'info', planning: 'warning',
    active: '', execution: '', signed: 'success',
    archived: 'info', completion: 'success', reporting: '',
  }
  return (map[ctx.value.projectStatus] || 'info') as any
})

// ─── 初始化加载 ───
onMounted(async () => {
  if (!projectId.value) return

  // 确保项目上下文已加载
  if (!ctx.value.projectId) {
    await projectStore.loadProjectContext(projectId.value)
  }

  // 填充基本信息
  basicInfo.value = {
    projectName: ctx.value.projectName || '',
    clientName: ctx.value.projectName || '',
    manager: '',
    createdAt: '',
  }

  standardInfo.value = {
    year: ctx.value.year,
    standard: ctx.value.applicableStandard || 'soe',
    scope: ctx.value.auditScope || 'standalone',
  }

  lockingInfo.value.readonlyMode = isReadonly.value

  // 加载成员列表
  await loadMembers()
})

async function loadMembers() {
  try {
    const data = await api.get(`/api/projects/${projectId.value}/staff`, {
      validateStatus: (s: number) => s < 600,
    })
    const items = (data as any)?.items ?? data ?? []
    members.value = (Array.isArray(items) ? items : []).map((m: any) => ({
      id: m.id || m.staff_id || '',
      name: m.name || m.staff_name || '',
      role: m.role || m.project_role || '',
      systemRole: m.system_role || '',
      email: m.email || '',
    }))
  } catch {
    members.value = []
  }
}
</script>

<style scoped>
.project-settings-center {
  max-width: 960px;
  margin: 0 auto;
}

.project-settings-center__tabs {
  border-radius: var(--gt-radius-lg, 8px);
  overflow: hidden;
}

.project-settings-center__tabs :deep(.el-tabs__header) {
  background: var(--gt-color-primary-bg, #f4f0fa);
}

.project-settings-center__tabs :deep(.el-tabs__item.is-active) {
  color: var(--gt-color-primary, #4b2d77);
  border-bottom-color: var(--gt-color-primary, #4b2d77);
}

.settings-panel {
  padding: 16px 0;
}

.settings-panel__title {
  font-size: var(--gt-font-size-lg, 16px);
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
  margin: 0 0 16px 0;
}

.settings-panel__desc {
  color: var(--gt-color-text-secondary, #606266);
  font-size: var(--gt-font-size-sm, 13px);
  margin-bottom: 16px;
  display: block;
}

.settings-panel__toolbar {
  margin-bottom: 12px;
}

.settings-panel__table {
  width: 100%;
}
</style>
