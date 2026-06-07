<template>
  <div class="gt-wp-list gt-fade-in">
    <!-- 页面横幅 -->
    <GtPageHeader :title="projectName ? `${projectName} — 底稿管理` : '底稿管理'" @back="$router.push('/projects')" variant="default">
      <template #actions>
        <GtToolbar :show-import="true" import-label="Excel导入" @import="showWpImport = true">
          <template #left>
            <div v-if="hasData" class="gt-wp-view-toggle">
              <el-radio-group v-model="viewMode" size="small">
                <el-radio-button v-for="tab in visibleTabs" :key="tab.value" :value="tab.value">
                  {{ tab.label }}
                </el-radio-button>
              </el-radio-group>
            </div>
          </template>
          <template #right>
            <el-button @click="fetchWpIndex" :loading="loading" size="small">刷新</el-button>
            <el-button type="success" size="small" @click="onGenerateWorkpapers" :loading="generateLoading">
              生成底稿
            </el-button>
            <el-button type="primary" size="small" @click="onBatchDownload" :loading="downloadLoading">
              批量下载 ({{ selectedWpIds.length || '全部' }})
            </el-button>
            <el-button type="warning" size="small" :disabled="selectedWpIds.length === 0" @click="showBatchAssign = true">
              批量委派 ({{ selectedWpIds.length }})
            </el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 归档横幅 -->
    <ArchivedBanner />
    <ConsolLockedBanner />

    <!-- 批量状态变更操作栏 -->
    <BatchActionBar
      v-if="selectedWpIds.length > 0"
      :selected-count="selectedWpIds.length"
      :selected-ids="selectedWpIds"
      @batch-action="onBatchStatusChange"
    />

    <!-- 筛选栏：仅列表视图显示 -->
    <div v-if="viewMode === 'list' && hasData" class="gt-wp-filter-bar">
      <el-input
        v-model="searchKeyword"
        placeholder="搜索底稿..."
        clearable
        size="default"
        style="width: 180px"
      />
      <el-select v-model="filterCycle" placeholder="审计循环" clearable size="default" style="width: 140px">
        <el-option v-for="c in cycleOptions" :key="c.value" :label="c.label" :value="c.value" />
      </el-select>
      <el-select v-model="filterStatus" placeholder="状态" clearable size="default" style="width: 110px">
        <el-option v-for="s in statusOptions" :key="s.value" :label="s.label" :value="s.value" />
      </el-select>
      <el-select v-model="filterAssignee" placeholder="编制人" clearable size="default" style="width: 110px">
        <el-option label="全部" value="" />
        <el-option v-for="u in userOptions" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
      </el-select>
    </div>

    <!-- 进度指示器 -->
    <div v-if="wpList.length > 0 && viewMode === 'list'" class="gt-wp-progress-bar">
      <span>总体进度：{{ totalProgress.completed }}/{{ totalProgress.total }}</span>
      <el-progress :percentage="totalProgress.percent" :stroke-width="10" style="width: 200px; display: inline-block" />
      <span>{{ totalProgress.percent }}%</span>
    </div>

    <!-- 子 SFC 渲染区 -->
    <keep-alive :include="visitedViews" :max="5">
      <component
        :is="currentViewComponent"
        :key="currentViewKey"
        :project-id="projectId"
        :year="currentYear"
        @navigate="onNavigate"
        @refresh="fetchWpIndex"
        @mutate="onMutate"
      />
    </keep-alive>

    <!-- 批量委派弹窗 -->
    <BatchAssignDialog
      v-model="showBatchAssign"
      :project-id="projectId"
      :wp-ids="selectedWpIds"
      :wp-list="batchAssignWpList"
      @assigned="onBatchAssigned"
    />

    <!-- 导入弹窗 -->
    <UnifiedImportDialog
      v-if="showWpImport"
      v-model="showWpImport"
      import-type="workpaper"
      :project-id="projectId"
      @imported="fetchWpIndex"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * WorkpaperList — Shell 容器（底稿管理页面入口）
 *
 * 职责：
 * 1. provide(WP_LIST_CONTEXT_KEY) 共享 context 注入
 * 2. el-radio-group Tab 切换 + 角色可见性
 * 3. keep-alive + defineAsyncComponent lazy import 5 子 SFC
 * 4. onMutate 统一 service 调用
 * 5. viewMode watch + router.replace
 *
 * Requirements: 1.1-1.8, 4.1-4.5, 5.1-5.6
 */
import { ref, computed, provide, watch, onMounted, defineAsyncComponent, h } from 'vue'
import type { Component } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  WP_LIST_CONTEXT_KEY,
  type WpListContext,
  type MutatePayload,
  type ProgressInfo,
} from '@/composables/useWorkpaperListContext'
import type { WpIndexItem, WorkpaperDetail } from '@/services/workpaperApi'
import { listWorkpapers, getWpIndex, downloadWorkpaperPack } from '@/services/workpaperApi'
import { listUsers } from '@/services/commonApi'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { useAuthStore } from '@/stores/auth'
import { useAuditContext } from '@/composables/useAuditContext'
import { useProjectStore } from '@/stores/project'
import { useDictStore } from '@/stores/dict'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import BatchActionBar from '@/components/workpaper/BatchActionBar.vue'
import BatchAssignDialog from '@/components/assignment/BatchAssignDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'

defineOptions({ name: 'WorkpaperList' })

// ─── 路由 & 基础 ─────────────────────────────────────────────────────────────
const route = useRoute()
const router = useRouter()
const authStore = useAuthStore()
const { onContextChange } = useAuditContext()

// ─── P0-6.2: ProjectContext + PermissionMatrix facade ────────────────────────
const projectStore = useProjectStore()
const projectContext = computed(() => projectStore.currentProjectContext)
const { can: canOp, whyCannot } = usePermissionMatrix()
// DEPRECATED: 旧 authStore.user?.role 直接判断仍保留，后续逐步替换为 canOp()

const projectId = computed(() => route.params.projectId as string)
const currentYear = computed(() => Number(route.query.year) || new Date().getFullYear())
const projectName = ref('')

// ─── 核心数据 ─────────────────────────────────────────────────────────────────
const wpList = ref<WorkpaperDetail[]>([])
const wpIndex = ref<WpIndexItem[]>([])
const loading = ref(false)
const viewMode = ref('workbench')
const searchKeyword = ref('')
const filterCycle = ref('')
const filterStatus = ref('')
const filterAssignee = ref('')
const selectedWpId = ref('')
const selectedWpIds = ref<string[]>([])
const userOptions = ref<any[]>([])
const showWpImport = ref(false)
const showBatchAssign = ref(false)
const downloadLoading = ref(false)
const generateLoading = ref(false)

const hasData = computed(() => wpIndex.value.length > 0 || wpList.value.length > 0)

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])
const totalProgress = computed<ProgressInfo>(() => {
  const total = wpList.value.length
  const completed = wpList.value.filter((w) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

// ─── Tab 可见性（角色控制） ─────────────────────────────────────────────────────
interface TabDef { value: string; label: string; hidden?: boolean }

const ALL_TABS: TabDef[] = [
  { value: 'lifecycle', label: '生命周期' },
  { value: 'matrix', label: '委派矩阵' },
  { value: 'list', label: '列表' },
  { value: 'workbench', label: '工作台' },
  { value: 'kanban', label: '看板' },
  { value: 'graph', label: '依赖图' },
  { value: 'guide', label: '手册' },
]

const visibleTabs = computed(() => {
  const role = authStore.user?.role
  // auditor / qc 隐藏 DelegationMatrix
  if (role === 'auditor' || role === 'qc') {
    return ALL_TABS.filter(t => t.value !== 'matrix')
  }
  return ALL_TABS
})

// ─── viewMode → 子 SFC 路由表 ─────────────────────────────────────────────────
const WorkbenchView = defineAsyncComponent(() => import('./workpaper-list/WorkpaperWorkbenchView.vue'))
const BoardView = defineAsyncComponent(() => import('./workpaper-list/WorkpaperBoardView.vue'))
const LifecycleView = defineAsyncComponent(() => import('./workpaper-list/WorkpaperLifecycleView.vue'))
const DependencyGraphView = defineAsyncComponent(() => import('./workpaper-list/WorkpaperDependencyGraph.vue'))
const DelegationMatrixView = defineAsyncComponent(() => import('./workpaper-list/WorkpaperDelegationMatrix.vue'))

const VIEW_MODE_WHITELIST = new Set(['list', 'workbench', 'guide', 'kanban', 'lifecycle', 'graph', 'matrix'])

const VIEW_TO_COMPONENT: Record<string, Component> = {
  list: WorkbenchView,
  workbench: WorkbenchView,
  guide: WorkbenchView,
  kanban: BoardView,
  lifecycle: LifecycleView,
  graph: DependencyGraphView,
  matrix: DelegationMatrixView,
}

const currentViewComponent = computed(() => {
  if (!VIEW_MODE_WHITELIST.has(viewMode.value)) {
    console.warn(`[WorkpaperList] 非法 viewMode: "${viewMode.value}"，回退到 workbench`)
    viewMode.value = 'workbench'
  }
  return VIEW_TO_COMPONENT[viewMode.value] || WorkbenchView
})

/** keep-alive :key — list/workbench/guide 共享同一 key（同一 SFC 实例） */
const currentViewKey = computed(() => {
  const mode = viewMode.value
  if (mode === 'list' || mode === 'workbench' || mode === 'guide') return 'workbench'
  return mode
})

// ─── keep-alive 已访问视图追踪 ─────────────────────────────────────────────────
const visitedViews = ref<string[]>(['WorkpaperWorkbenchView'])

watch(viewMode, (mode) => {
  const componentNames: Record<string, string> = {
    list: 'WorkpaperWorkbenchView',
    workbench: 'WorkpaperWorkbenchView',
    guide: 'WorkpaperWorkbenchView',
    kanban: 'WorkpaperBoardView',
    lifecycle: 'WorkpaperLifecycleView',
    graph: 'WorkpaperDependencyGraph',
    matrix: 'WorkpaperDelegationMatrix',
  }
  const name = componentNames[mode]
  if (name && !visitedViews.value.includes(name)) {
    visitedViews.value.push(name)
  }
})

// ─── viewMode watch → router.replace ─────────────────────────────────────────
watch(viewMode, (newMode) => {
  if (!VIEW_MODE_WHITELIST.has(newMode)) {
    console.warn(`[WorkpaperList] 非法 viewMode: "${newMode}"，回退到 workbench`)
    viewMode.value = 'workbench'
    return
  }
  const currentQuery = { ...route.query }
  if (currentQuery.view !== newMode) {
    router.replace({ query: { ...currentQuery, view: newMode } })
  }
}, { flush: 'post' })

// ─── 数据获取 ─────────────────────────────────────────────────────────────────
async function fetchWpIndex() {
  if (loading.value) return
  loading.value = true
  try {
    const [wps, idx] = await Promise.all([
      listWorkpapers(projectId.value, {
        audit_cycle: filterCycle.value || undefined,
        status: filterStatus.value || undefined,
        assigned_to: filterAssignee.value || undefined,
      }),
      getWpIndex(projectId.value),
    ])
    wpList.value = wps
    wpIndex.value = idx.map((item) => {
      const matchedWorkpaper = wps.find((wp) => wp.wp_index_id === item.id)
      return {
        ...item,
        assigned_to: matchedWorkpaper?.assigned_to ?? item.assigned_to,
        reviewer: matchedWorkpaper?.reviewer ?? item.reviewer,
      }
    })
  } finally {
    loading.value = false
  }
}

async function refreshAfterMutate() {
  await fetchWpIndex()
}

// ─── provide context ─────────────────────────────────────────────────────────
const showTrimmedFilter = computed<'active' | 'all'>(() => 'active')
const roleViewPreset = computed(() => 'assistant' as const)
const roleViewWpList = computed(() => wpList.value)
const treeData = ref<any[]>([])

const ctx: WpListContext = {
  wpIndex,
  wpList,
  treeData,
  loading,
  projectId,
  currentYear,
  projectName,
  viewMode,
  searchKeyword,
  filterCycle,
  filterStatus,
  filterAssignee,
  showTrimmedFilter,
  selectedWpId,
  totalProgress,
  roleViewPreset,
  roleViewWpList,
  fetchWpIndex,
  refreshAfterMutate,
}

provide(WP_LIST_CONTEXT_KEY, ctx)

// ─── 子 SFC 事件处理 ─────────────────────────────────────────────────────────
function onNavigate(wpId: string) {
  router.push({ name: 'WorkpaperEditor', params: { projectId: projectId.value, wpId } })
}

async function onMutate(payload: MutatePayload) {
  try {
    switch (payload.action) {
      case 'batchAssign': {
        const { wp_ids, member_id } = payload.data as { wp_ids: string[]; member_id: string }
        await api.post(`/api/projects/${projectId.value}/working-papers/batch-assign`, {
          wp_ids, assigned_to: member_id,
        })
        ElMessage.success('批量委派成功')
        break
      }
      case 'assign': {
        const { wp_id } = payload.data as { wp_id: string }
        selectedWpIds.value = [wp_id]
        showBatchAssign.value = true
        return // 不刷新，等弹窗完成后刷新
      }
      case 'delegate': {
        const { wp_ids, member_id } = payload.data as { wp_ids: string[]; member_id: string }
        await api.post(`/api/projects/${projectId.value}/working-papers/batch-assign`, {
          wp_ids, assigned_to: member_id,
        })
        ElMessage.success('委派成功')
        break
      }
      case 'updateStatus': {
        const { wp_id, status } = payload.data as { wp_id: string; status: string }
        await api.put(`/api/projects/${projectId.value}/working-papers/${wp_id}/status`, { status })
        ElMessage.success('状态更新成功')
        break
      }
      case 'reorder':
        // 暂不实现
        break
    }
    await refreshAfterMutate()
  } catch (e: any) {
    handleApiError(e, '操作失败')
  }
}

// ─── 批量操作 ─────────────────────────────────────────────────────────────────
const batchAssignWpList = computed(() => {
  return wpList.value.map((w: WorkpaperDetail) => {
    const idx = wpIndex.value.find((i: WpIndexItem) => i.id === w.wp_index_id)
    return {
      id: w.id,
      wp_code: w.wp_code || idx?.wp_code || '',
      wp_name: w.wp_name || idx?.wp_name || '',
      audit_cycle: w.audit_cycle || idx?.audit_cycle || '',
    }
  })
})

function onBatchAssigned() {
  fetchWpIndex()
}

async function onGenerateWorkpapers() {
  generateLoading.value = true
  try {
    // 0. 确保模板集编码是最新的（幂等 seed，会自动更新旧的占位编码）
    try { await api.post('/api/template-sets/seed') } catch { /* ignore */ }
    // 1. 获取模板集列表
    const { listTemplateSets } = await import('@/services/workpaperApi')
    let sets = await listTemplateSets()
    if (!sets || sets.length === 0) {
      // 尝试自动初始化内置模板集（国企版+上市版）
      try {
        await api.post('/api/template-sets/seed')
        sets = await listTemplateSets()
      } catch { /* ignore */ }
      if (!sets || sets.length === 0) {
        ElMessage.warning('暂无可用模板集，请在「模板库」中创建')
        return
      }
    }
    // 2. 过滤：只显示"标准年审" + 用户自建模板集（去掉 IPO/上市/附注/精简等内置占位）
    const SHOW_BUILTIN = new Set(['标准年审'])
    const filteredSets = sets.filter(s =>
      SHOW_BUILTIN.has(s.set_name) || !['IPO', '上市公司', '上市附注', '国企附注', '精简版'].includes(s.set_name)
    )
    if (filteredSets.length === 0) {
      ElMessage.warning('暂无可用模板集')
      return
    }
    // 3. 弹窗让用户选择模板集
    const options = filteredSets.map(s => ({ label: s.set_name, value: s.id }))
    const selectedSetId = await new Promise<string>((resolve, reject) => {
      ElMessageBox({
        title: '选择底稿模板集',
        message: () => {
          return h('div', { style: 'padding: 8px 0' }, [
            h('p', { style: 'margin: 0 0 12px; color: var(--gt-color-text-secondary); font-size: 13px' },
              `共 ${filteredSets.length} 个模板集可选（标准年审 + 项目组自定义）`),
            h('select', {
              id: '__wp_tpl_select',
              style: 'width: 100%; padding: 8px 12px; border: 1px solid var(--gt-color-border-purple-light, #d8b8ee); border-radius: 6px; font-size: 14px; outline: none;',
            }, options.map(o => h('option', { value: o.value }, o.label))),
          ])
        },
        confirmButtonText: '生成',
        cancelButtonText: '取消',
        showCancelButton: true,
        beforeClose: (action, instance, done) => {
          if (action === 'confirm') {
            const el = document.getElementById('__wp_tpl_select') as HTMLSelectElement | null
            const val = el?.value || options[0]?.value
            if (val) { resolve(val); done() }
          } else {
            reject('cancel'); done()
          }
        },
      }).catch(() => reject('cancel'))
    })
    // 3. 调用生成 API
    let result: any
    try {
      // 优先走 generate（模板集路径），500 时降级到 generate-from-codes
      result = await api.post(
        `/api/projects/${projectId.value}/working-papers/generate`,
        { template_set_id: selectedSetId, year: currentYear.value },
      )
    } catch (genErr: any) {
      // generate 500 时降级：取模板集编码走 generate-from-codes
      if (genErr?.response?.status >= 500) {
        try {
          const { getTemplateSet } = await import('@/services/workpaperApi')
          const selectedSet = await getTemplateSet(selectedSetId)
          const wpCodes = selectedSet?.template_codes || []
          if (wpCodes.length > 0) {
            result = await api.post(
              `/api/projects/${projectId.value}/working-papers/generate-from-codes`,
              { wp_codes: wpCodes, year: currentYear.value },
            )
          } else {
            throw genErr
          }
        } catch {
          throw genErr
        }
      } else {
        throw genErr
      }
    }
    const created = (result as any)?.created || (result as any)?.count || 0
    ElMessage.success(`底稿生成完成，共创建 ${created} 份底稿`)
    // 4. 刷新列表
    await fetchWpIndex()
  } catch (e: any) {
    if (String(e).includes('cancel')) return
    handleApiError(e, '生成底稿')
  } finally {
    generateLoading.value = false
  }
}

async function onBatchDownload() {
  downloadLoading.value = true
  try {
    await downloadWorkpaperPack(projectId.value, selectedWpIds.value.length > 0 ? selectedWpIds.value : undefined)
  } catch (e: any) {
    handleApiError(e, '批量下载')
  } finally {
    downloadLoading.value = false
  }
}

async function onBatchStatusChange(payload: { action: string; ids: string[] }) {
  const actionLabels: Record<string, string> = {
    submit_review: '提交复核',
    return_to_draft: '退回修改',
    mark_complete: '标记完成',
  }
  const label = actionLabels[payload.action] || payload.action
  try {
    await ElMessageBox.confirm(
      `确定将 ${payload.ids.length} 个底稿${label}？`,
      '批量操作确认',
      { type: 'warning' }
    )
  } catch { return }

  try {
    const data = await api.post(
      `/api/projects/${projectId.value}/working-papers/batch-status`,
      { wp_ids: payload.ids, action: payload.action }
    ) as any
    ElMessage.success(data?.message || `成功${label}`)
    if (data?.skipped?.length > 0) {
      ElMessage.warning(`${data.skipped.length} 个底稿被跳过（状态不允许）`)
    }
    fetchWpIndex()
  } catch (e: any) {
    handleApiError(e, `批量${label}`)
  }
}

// ─── 筛选选项 ─────────────────────────────────────────────────────────────────
const cycleOptions = [
  { value: 'B', label: 'B类 计划阶段' },
  { value: 'C', label: 'C类 控制测试' },
  { value: 'D', label: 'D类 收入循环' },
  { value: 'E', label: 'E类 货币资金' },
  { value: 'F', label: 'F类 采购存货' },
  { value: 'G', label: 'G类 投资' },
  { value: 'H', label: 'H类 固定资产' },
  { value: 'I', label: 'I类 无形资产' },
  { value: 'J', label: 'J类 职工薪酬' },
  { value: 'K', label: 'K类 管理费用' },
  { value: 'L', label: 'L类 筹资' },
  { value: 'M', label: 'M类 股东权益' },
  { value: 'N', label: 'N类 税费' },
  { value: 'S', label: 'S类 专项程序' },
]

const statusOptions = computed(() => {
  const dictStore = useDictStore()
  const dictOptions = dictStore.options('wp_status')
  if (dictOptions.length > 0) {
    return dictOptions.map(e => ({ value: e.value, label: e.label }))
  }
  // fallback 硬编码（字典未加载时）
  return [
    { value: 'draft', label: '待编' },
    { value: 'in_progress', label: '编制中' },
    { value: 'edit_complete', label: '已完成' },
    { value: 'pending_review', label: '待复核' },
    { value: 'reviewed', label: '已复核' },
    { value: 'approved', label: '已通过' },
  ]
})

// ─── 生命周期 ─────────────────────────────────────────────────────────────────
watch([filterCycle, filterStatus, filterAssignee], () => fetchWpIndex())

onMounted(async () => {
  // 从 URL query 读取视图模式
  const queryView = route.query.view as string
  if (queryView && VIEW_MODE_WHITELIST.has(queryView)) {
    viewMode.value = queryView
  }
  await fetchWpIndex()
  // 加载项目名称
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.get(`/api/projects/${projectId.value}`)
    const proj = resp.data
    projectName.value = proj?.name || proj?.project_name || ''
  } catch { /* 静默 */ }
  // 加载用户列表
  try {
    const users = await listUsers()
    userOptions.value = users
  } catch { /* 静默 */ }
})

// V3 Req 5.1：上下文变化时自动重载
onContextChange(async () => {
  await fetchWpIndex()
})
</script>

<style scoped>
.gt-wp-list {
  padding: var(--gt-space-4);
  height: 100%;
  display: flex;
  flex-direction: column;
}
.gt-wp-filter-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--gt-space-3);
  padding: 8px 12px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  box-shadow: var(--gt-shadow-sm);
  flex-wrap: nowrap;
  overflow-x: auto;
}
.gt-wp-view-toggle {
  margin: 0 12px;
}
.gt-wp-progress-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--gt-space-3);
  padding: 6px 12px;
  background: var(--gt-color-bg-white);
  border-radius: var(--gt-radius-md);
  font-size: 13px;
}
</style>
