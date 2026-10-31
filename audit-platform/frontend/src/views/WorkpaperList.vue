<template>
  <div class="gt-wp-list gt-fade-in">
    <!-- 页面横幅 -->
    <GtPageHeader :title="projectName ? `${projectName} — 底稿管理` : '底稿管理'" @back="$router.push('/projects')" variant="default">
      <template #actions>
        <GtToolbar :show-import="false">
          <template #left>
            <div v-if="hasData" class="gt-wp-view-toggle">
              <el-radio-group v-model="viewMode" size="small">
                <el-radio-button v-for="tab in visibleTabs" :key="tab.value" :value="tab.value">
                  {{ tab.label }}
                </el-radio-button>
              </el-radio-group>
              <!-- 更多视图下拉 -->
              <el-dropdown trigger="click" @command="(cmd: string) => { viewMode = cmd }" style="margin-left: 4px">
                <el-button size="small" :type="isMoreTabActive ? 'primary' : ''" plain>
                  {{ isMoreTabActive ? moreTabActiveLabel : '更多视图' }}
                  <el-icon class="el-icon--right"><ArrowDown /></el-icon>
                </el-button>
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="tab in moreTabOptions"
                      :key="tab.value"
                      :command="tab.value"
                      :class="{ 'is-active-item': viewMode === tab.value }"
                    >
                      {{ tab.label }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </div>
          </template>
          <template #right>
            <!-- 常用操作（所有角色可见） -->
            <el-tooltip content="重新加载底稿列表数据" placement="bottom">
              <el-button @click="fetchWpIndex" :loading="loading" size="small">
                🔄 刷新
              </el-button>
            </el-tooltip>
            <el-tooltip content="对所有已接入底稿执行公式推送（审定表/明细表/附注），不打开底稿即可刷新全部公式计算结果" placement="bottom">
              <el-button @click="onFormulaRefreshAll" :loading="formulaRefreshLoading" size="small">
                ⚡ 刷新全部公式
              </el-button>
            </el-tooltip>
            <el-tooltip content="按循环决定哪些底稿执行、填写裁剪理由并指定底稿主编" placement="bottom">
              <el-button size="small" @click="goProcedureTrim()">✂️ 程序裁剪</el-button>
            </el-tooltip>
            <el-tooltip v-if="canCreateWp" content="按程序裁剪结果生成本项目底稿：选模板集，按循环确认生成范围" placement="bottom">
              <el-button type="success" size="small" @click="onGenerateWorkpapers">
                ⬇️ 生成底稿
              </el-button>
            </el-tooltip>

            <!-- 📥 导入导出 收敛为一个下拉 -->
            <!-- 🔴 文案与真实能力对齐（2026-08-09）：改造前 tooltip 写「含模板、数据包、
                 ZIP下载」，让人以为「批量下载 ZIP」导出的包能原样从「Excel 导入 /
                 增强导入」传回来 —— 那两个入口只收**单份** .xlsx/.docx，传 zip 必被拒。
                 能收 ZIP 数据包的只有「Tab 数据包」。此处只改描述，不动 command。 -->
            <el-tooltip content="底稿的批量导出与导入。导出：ZIP 整包 / 元数据快照；导入：单份 Excel（xlsx·docx）或 Tab 数据包（zip）" placement="bottom">
              <el-dropdown trigger="click" @command="onImportExportCommand">
              <el-button size="small">
                📥 导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="excel-import">
                    <span style="display:flex;align-items:center;gap:6px">
                      📄 Excel 导入
                      <span style="color:var(--el-text-color-secondary);font-size:11px">单份 xlsx，覆盖该底稿</span>
                    </span>
                  </el-dropdown-item>
                  <el-dropdown-item command="enhanced-import">
                    <span style="display:flex;align-items:center;gap:6px">
                      📋 增强导入
                      <span style="color:var(--el-text-color-secondary);font-size:11px">单份 xlsx/docx，带校验与冲突处理</span>
                    </span>
                  </el-dropdown-item>
                  <el-dropdown-item divided command="batch-download">
                    <span style="display:flex;align-items:center;gap:6px">
                      📦 批量下载 ZIP
                      <span style="color:var(--el-text-color-secondary);font-size:11px">{{ selectedWpIds.length ? `已选 ${selectedWpIds.length} 份 · 仅下载` : '全部底稿 · 仅下载' }}</span>
                    </span>
                  </el-dropdown-item>
                  <el-dropdown-item command="batch-export-meta">
                    <span style="display:flex;align-items:center;gap:6px">
                      📊 元数据导出
                      <span style="color:var(--el-text-color-secondary);font-size:11px">按循环筛选 · 含 manifest</span>
                    </span>
                  </el-dropdown-item>
                  <el-dropdown-item command="bulk-tab">
                    <span style="display:flex;align-items:center;gap:6px">
                      🗂️ Tab 数据包
                      <span style="color:var(--el-text-color-secondary);font-size:11px">唯一支持 zip 导入的入口</span>
                    </span>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            </el-tooltip>

            <!-- 管理操作（仅 manager/partner/admin 可见） -->
            <template v-if="canManageWp">
              <el-tooltip content="从其他项目复制底稿模板配置" placement="bottom">
                <el-button size="small" @click="showTemplateCopy = true">📋 模板复制</el-button>
              </el-tooltip>
              <el-tooltip v-if="canCreateWp" content="粘贴清单或上传 Excel，一次创建多份自定义底稿" placement="bottom">
                <el-button size="small" @click="showCustomBatch = true">➕ 批量自定义底稿</el-button>
              </el-tooltip>
              <el-tooltip content="将选中底稿批量委派给项目组成员" placement="bottom">
                <el-button type="warning" size="small" :disabled="selectedWpIds.length === 0" @click="showBatchAssign = true">
                  👥 批量委派 ({{ selectedWpIds.length }})
                </el-button>
              </el-tooltip>
            </template>
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
        <el-option label="未分配" :value="UNASSIGNED_FILTER" />
        <el-option v-for="u in userOptions" :key="u.id" :label="u.full_name || u.username" :value="u.id" />
      </el-select>
      <!-- 联动状态横条「查看详情」跳转 ?filter=stale 落到这里 -->
      <el-tooltip
        content="仅显示上游数据变更后预填待重算的底稿；重算不覆盖已保存的底稿正文，需打开底稿刷新后重新保存"
        placement="top"
        :show-after="300"
      >
        <el-checkbox v-model="filterStale" size="default" class="gt-wp-filter-bar__stale">
          仅看待重算<span v-if="staleCount > 0" class="gt-wp-filter-bar__stale-count">{{ staleCount }}</span>
        </el-checkbox>
      </el-tooltip>
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
        @wp-selection-change="onChildSelectionChange"
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

    <!-- 底稿统一导入导出（workpaper-unified-import-export） -->
    <WpImportDialog
      v-model="showWpImportEnhanced"
      :project-id="projectId"
      @imported="fetchWpIndex"
    />
    <WpBatchExportDialog
      v-model="showBatchExportEnhanced"
      :project-id="projectId"
    />
    <!-- 项目级底稿批量 Tab 导入导出（结构化数据包，与整份文件导出并列） -->
    <WpBulkDialog
      v-model="showBulkTab"
      :project-id="projectId"
      @imported="fetchWpIndex"
    />
    <WpTemplateCopyDialog
      v-model="showTemplateCopy"
      :project-id="projectId"
      @copied="fetchWpIndex"
    />

    <!-- 批量新建自定义底稿（粘贴清单 / 上传 Excel） -->
    <GtCustomWpBatchDialog
      v-model="showCustomBatch"
      :project-id="projectId"
      @created="fetchWpIndex"
    />

    <!-- 按程序裁剪结果生成底稿（spec trim-generation-plan-linkage；与程序裁剪页共用） -->
    <GenerationPlanDialog
      v-model="showGenerateDialog"
      :project-id="projectId"
      :year="currentYear"
      :can-submit="canCreateWp"
      disabled-reason="项目已归档或你已失去本项目编辑权限，不能生成底稿"
      @generated="fetchWpIndex"
      @navigate-cycle="goProcedureTrim"
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
import { ref, shallowRef, computed, provide, watch, onMounted, defineAsyncComponent } from 'vue'
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
import { listWorkpapers, getWpIndex, downloadWorkpaperPack, getWpMappingByAccount } from '@/services/workpaperApi'
import { listUsers } from '@/services/commonApi'
import { UNASSIGNED_FILTER, readListEntryQuery } from './workpaper-list/workpaperListEntryQuery'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { resolveEffectiveAuditYear } from '@/utils/resolveAuditYear'
import { indexFirstBy } from '@/utils/indexFirstBy'
import { useAuthStore } from '@/stores/auth'
import { useAuditContext } from '@/composables/useAuditContext'
import { useProjectStore } from '@/stores/project'
import { useRoleContextStore } from '@/stores/roleContext'
import { useDictStore } from '@/stores/dict'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import { ArrowDown } from '@element-plus/icons-vue'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import ArchivedBanner from '@/components/common/ArchivedBanner.vue'
import ConsolLockedBanner from '@/components/common/ConsolLockedBanner.vue'
import BatchActionBar from '@/components/workpaper/BatchActionBar.vue'
import BatchAssignDialog from '@/components/assignment/BatchAssignDialog.vue'
import UnifiedImportDialog from '@/components/import/UnifiedImportDialog.vue'
import WpImportDialog from '@/components/workpaper/WpImportDialog.vue'
import WpBatchExportDialog from '@/components/workpaper/WpBatchExportDialog.vue'
import WpBulkDialog from '@/components/workpaper/bulk-tab/WpBulkDialog.vue'
import WpTemplateCopyDialog from '@/components/workpaper/WpTemplateCopyDialog.vue'
import GenerationPlanDialog from '@/components/workpaper/generation/GenerationPlanDialog.vue'
import GtCustomWpBatchDialog from '@/components/workpaper/custom/GtCustomWpBatchDialog.vue'

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
// 审计年度单一来源：路由 ?year= > ProjectContextGate 已解析的 projectStore.year > null；
// 本页自己的项目名称 GET 失败不能把「读取失败」误报成「项目未设置年度」。
const currentYear = computed<number | null>(() => resolveEffectiveAuditYear({ routeYear: route.query.year, storeAuditYear: projectStore.year }))
const projectName = computed(() => projectStore.currentProjectContext?.projectName || projectStore.clientName || '')

// ─── 核心数据 ─────────────────────────────────────────────────────────────────
// 浅层响应式：两张清单一直整体替换（fetchWpIndex），没有人改元素；深层 ref 让 929 × 2 个对象每次读字段都走代理
// 与依赖收集（spec platform-perf-hotspots R7）
const wpList = shallowRef<WorkpaperDetail[]>([])
const wpIndex = shallowRef<WpIndexItem[]>([])
/** wp_index.id → 索引项（同 id 取第一个，与原先 find 一致） */
const wpIndexById = computed(() => indexFirstBy(wpIndex.value, (i) => i.id))
const loading = ref(false)
const viewMode = ref('workbench')
const searchKeyword = ref('')
const filterCycle = ref('')
const filterStatus = ref('')
/** 仅看「预填待重算」底稿（?filter=stale 或筛选栏勾选） */
const filterStale = ref(false)
const filterAssignee = ref('')
const selectedWpId = ref('')
/** 入口定位（?highlight= / ?wp_code= / ?search=）：列表视图按 seq 只执行一次 */
const locateTarget = ref<{ code: string; seq: number } | null>(null)
const listLoaded = ref(false)
/** 首次取数结束（成功、取消、失败都算）：?account= 要按本项目已生成的底稿筛映射编码 */
let markFirstLoad: () => void = () => {}
const firstLoad = new Promise<void>((done) => { markFirstLoad = done })
const selectedWpIds = ref<string[]>([])
const userOptions = ref<any[]>([])
const showWpImport = ref(false)
const showWpImportEnhanced = ref(false)
const showBatchExportEnhanced = ref(false)
const showBulkTab = ref(false)
const showTemplateCopy = ref(false)
/** 批量新建自定义底稿弹窗（custom-workpaper-dual-mode-formula-and-batch Task 21） */
const showCustomBatch = ref(false)
const showBatchAssign = ref(false)
const downloadLoading = ref(false)
const formulaRefreshLoading = ref(false)
const showGenerateDialog = ref(false)

const hasData = computed(() => wpIndex.value.length > 0 || wpList.value.length > 0)

// ─── 角色门控（管理操作按钮可见性） ────────────────────────────────────────────
const MANAGE_ROLES = new Set(['admin', 'partner', 'signing_partner', 'manager'])
const canManageWp = computed(() => {
  const role = authStore.user?.role
  return role ? MANAGE_ROLES.has(role) : false
})
// 生成底稿 / 新建自定义底稿的后端门禁是本项目编辑权限（归档项目 423）：没有就不显示入口，不给点了必被拒的按钮
// （spec formula-fetch-followup-defect-closure R4.2；与 GtRefreshScopeDialog 同一口径）
const roleContext = useRoleContextStore()
const canCreateWp = computed(() => roleContext.canEditInProject && projectStore.projectStatus !== 'archived')

// ─── 导入导出下拉命令分派 ─────────────────────────────────────────────────────
function onImportExportCommand(command: string) {
  switch (command) {
    case 'excel-import':
      showWpImport.value = true
      break
    case 'enhanced-import':
      showWpImportEnhanced.value = true
      break
    case 'batch-download':
      onBatchDownload()
      break
    case 'batch-export-meta':
      showBatchExportEnhanced.value = true
      break
    case 'bulk-tab':
      showBulkTab.value = true
      break
  }
}

// ─── 进度计算 ─────────────────────────────────────────────────────────────────
const COMPLETED_STATUSES = new Set(['review_passed', 'archived'])
const totalProgress = computed<ProgressInfo>(() => {
  const total = wpList.value.length
  const completed = wpList.value.filter((w) => COMPLETED_STATUSES.has(w.status)).length
  const percent = total > 0 ? Math.round((completed / total) * 100) : 0
  return { total, completed, percent }
})

/** 待重算底稿数（筛选栏「仅看待重算」角标；与联动状态横条计数同源字段 prefill_stale） */
const staleCount = computed(() => wpList.value.filter((w) => w.prefill_stale === true).length)

// ─── Tab 可见性（角色控制） ─────────────────────────────────────────────────────
interface TabDef { value: string; label: string; hidden?: boolean }

// 核心视图（所有角色直接显示）
const PRIMARY_TABS: TabDef[] = [
  { value: 'lifecycle', label: '生命周期' },
  { value: 'workbench', label: '工作台' },
  { value: 'list', label: '列表' },
  { value: 'guide', label: '手册' },
]

// 更多视图（收进下拉，按角色过滤）
const MORE_TABS: TabDef[] = [
  { value: 'matrix', label: '委派矩阵' },
  { value: 'kanban', label: '看板' },
  { value: 'graph', label: '依赖图' },
]

const ALL_TABS: TabDef[] = [...PRIMARY_TABS, ...MORE_TABS]

const visibleTabs = computed(() => {
  // 核心 Tab 直接显示在 radio-group
  return PRIMARY_TABS
})

const moreTabOptions = computed(() => {
  const role = authStore.user?.role
  // auditor / qc 隐藏 DelegationMatrix
  if (role === 'auditor' || role === 'qc') {
    return MORE_TABS.filter(t => t.value !== 'matrix')
  }
  return MORE_TABS
})

/** 当前是否选中了"更多视图"中的某个 */
const isMoreTabActive = computed(() => MORE_TABS.some(t => t.value === viewMode.value))
const moreTabActiveLabel = computed(() => MORE_TABS.find(t => t.value === viewMode.value)?.label || '更多视图')

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
        assigned_to: filterAssignee.value && filterAssignee.value !== UNASSIGNED_FILTER ? filterAssignee.value : undefined,
      }),
      getWpIndex(projectId.value),
    ])
    wpList.value = wps
    listLoaded.value = true
    const wpByIndexId = indexFirstBy(wps, (wp) => wp.wp_index_id)
    wpIndex.value = idx.map((item) => {
      const matchedWorkpaper = wpByIndexId.get(item.id)
      return {
        ...item,
        assigned_to: matchedWorkpaper?.assigned_to ?? item.assigned_to,
        reviewer: matchedWorkpaper?.reviewer ?? item.reviewer,
      }
    })
  } catch (err: any) {
    // 请求被取消不是错误：同 URL 的 GET 后发会让 http.ts 去重 abort 在飞的这一发（换 ?year= 重挂本页、
    // 别处同时取同一清单）。此处吞掉，否则 CanceledError 冒泡到 ErrorBoundary。
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError') return
    throw err
  } finally {
    loading.value = false
    markFirstLoad()
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
  filterStale,
  showTrimmedFilter,
  selectedWpId,
  locateTarget,
  listLoaded,
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

function onChildSelectionChange(wpIds: string[]) {
  selectedWpIds.value = wpIds
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
    const idx = wpIndexById.value.get(w.wp_index_id)
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

/** 刷新全部公式：调 formula-push/run 全量推送（不打开底稿也能刷新审定表/明细表/附注） */
async function onFormulaRefreshAll() {
  if (currentYear.value == null) {
    ElMessage.warning('未设置审计年度，请先在项目基本信息中填写')
    return
  }
  formulaRefreshLoading.value = true
  try {
    const res: any = await api.post(
      `/api/projects/${projectId.value}/formula-push/run`,
      { year: currentYear.value, dry_run: false },
    )
    const written = res?.written_count ?? 0
    const kept = res?.kept_count ?? 0
    const skipped = res?.skipped_count ?? 0
    ElMessage.success(`公式推送完成：写入 ${written} 项，保留 ${kept} 项，跳过 ${skipped} 项`)
  } catch (e: any) {
    handleApiError(e, '刷新全部公式')
  } finally {
    formulaRefreshLoading.value = false
  }
}

/** 打开生成计划弹窗（选模板集、按循环确认；逐个底稿的排除走程序裁剪页） */
function onGenerateWorkpapers() {
  if (currentYear.value == null) {
    ElMessage.warning('未设置审计年度，请先在项目基本信息中填写')
    return
  }
  showGenerateDialog.value = true
}

/** 去程序裁剪页（从生成弹窗点「去程序裁剪」时直接打开对应循环） */
function goProcedureTrim(cycle?: string) {
  router.push({
    name: 'ProcedureTrimming',
    params: { projectId: projectId.value },
    query: cycle ? { cycle, from: 'generate' } : {},
  })
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
  { value: 'A', label: 'A类 完成阶段' },
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

/**
 * 地址栏 → 状态（挂载时与同页 query 变化共用一条规则）：
 * `?filter=stale`（联动状态横条「查看详情」）⇒ 开启待重算过滤并强制列表视图（筛选栏只在 list 视图渲染，
 * 落到工作台视图会让用户看不到自己被过滤了）；否则 `?view=` 在白名单内取它，不在取工作台。
 * 本页按路径复用（路由 meta.reuseOnQueryChange，spec platform-perf-hotspots R6）：同页内只改 query
 * （浏览器前进后退、站内跳到 `?view=list&filter=stale`）不再整页重挂重取，靠这里同步。
 * 与「状态 → 地址栏」的两个监听互为幂等：状态与地址一致时什么都不改，不会来回触发。
 * 待重算强制列表而状态本来就是列表时，那个监听不会触发 ⇒ 这里把地址栏的 view 改成 list：否则地址栏留着
 * `view=workbench`，之后一取消勾选就按它跳回工作台（原先整页重挂，挂载时总会写回 view=list）。
 * 入口参数（`highlight` / `wp_code` / `search` 定位、`cycle` 按循环筛选、`upload` 打开导入，spec wp-deeplink-locate-residual-closure
 * 需求 2）只在**到达时**（签名变化）处理一次：定位与筛选强制列表视图；签名没变时视图照旧按 `?view=`（否则带着 highlight 就切不出列表）。
 */
let appliedEntry = ''
let locateSeq = 0
function applyRouteQuery(query: Record<string, unknown>) {
  const stale = query.filter === 'stale'
  if (filterStale.value !== stale) filterStale.value = stale
  const entry = readListEntryQuery(query)
  const fresh = entry.signature !== appliedEntry
  appliedEntry = entry.signature
  if (fresh && entry.cycle && filterCycle.value !== entry.cycle) filterCycle.value = entry.cycle
  const assignee = entry.assigned === 'me' ? String(authStore.user?.id || '') : entry.assigned === 'unassigned' ? UNASSIGNED_FILTER : ''
  if (fresh && assignee && filterAssignee.value !== assignee) filterAssignee.value = assignee
  if (fresh && entry.code) locateTarget.value = { code: entry.code, seq: ++locateSeq }
  if (fresh && entry.account && !entry.code) void locateAccount(entry.account)
  if (fresh && entry.upload) {
    showWpImportEnhanced.value = true
    const rest = { ...route.query }
    delete rest.upload
    router.replace({ query: rest }) // 打开一次即可：去掉后刷新 / 后退不再弹（路由变化会再进本函数，届时已无 upload）
    return
  }
  const view = query.view
  const fromQuery = typeof view === 'string' && VIEW_MODE_WHITELIST.has(view) ? view : 'workbench'
  const wanted = stale || (fresh && (entry.code || entry.account || entry.cycle || entry.assigned)) ? 'list' : fromQuery
  if (viewMode.value !== wanted) viewMode.value = wanted // 「状态 → 地址栏」监听随后写回 view
  else if (wanted !== fromQuery) router.replace({ query: { ...route.query, view: wanted } })
}
watch(() => [route.query.view, route.query.filter, route.query.highlight, route.query.wp_code, route.query.search,
  route.query.account, route.query.cycle, route.query.assigned, route.query.upload] as const, () => applyRouteQuery(route.query))

/**
 * ?account=：按科目取关联底稿（与试算表「查看关联底稿」同一映射）。映射里还有表级编码（D2-2）和本项目没有的底稿，
 * 等首次取数后只认本项目已生成的：定位第一张，多张时点名；一张都没生成时按映射第一张定位（列表按原因提示）；映射为空时提示。
 */
async function locateAccount(account: string) {
  try {
    const mapped = [...new Set((await getWpMappingByAccount(projectId.value, account)).map((m) => m.wp_code).filter(Boolean))]
    if (!mapped.length) {
      ElMessage.warning(`科目 ${account} 没有关联的底稿`)
      return
    }
    await firstLoad
    const generated = new Set(wpList.value.map((w) => wpIndexById.value.get(w.wp_index_id)?.wp_code))
    const codes = mapped.filter((c) => generated.has(c))
    const first = codes[0] ?? mapped[0]
    locateTarget.value = { code: first, seq: ++locateSeq }
    if (codes.length > 1) ElMessage.info(`科目 ${account} 关联底稿 ${codes.join('、')}，已定位到 ${first}`)
  } catch (e: any) {
    handleApiError(e, '查询科目关联底稿')
  }
}

// filterStale 纯前端过滤（prefill_stale 已在列表响应里），无需重拉；仅同步 URL 便于分享/刷新保留
watch(filterStale, (on) => {
  const q = { ...route.query }
  if (on) {
    if (q.filter === 'stale') return
    q.filter = 'stale'
  } else {
    if (q.filter !== 'stale') return
    delete q.filter
  }
  router.replace({ query: q })
}, { flush: 'post' })

onMounted(async () => {
  // 预热 OnlyOffice api.js（仅 preload 不初始化 DocsAPI）
  const baseUrl = import.meta.env.VITE_ONLYOFFICE_URL || ''
  if (baseUrl) {
    const preloadHref = `${baseUrl.replace(/\/$/, '')}/web-apps/apps/api/documents/api.js`
    // 避免重复插入
    if (!document.head.querySelector(`link[rel="preload"][href="${preloadHref}"]`)) {
      const link = document.createElement('link')
      link.rel = 'preload'
      link.setAttribute('as', 'script')
      link.href = preloadHref
      document.head.appendChild(link)
    }
  }

  // 从 URL query 读取视图模式 / 待重算过滤 / 入口参数（规则见 applyRouteQuery）
  applyRouteQuery(route.query)
  await fetchWpIndex()
  // 项目标题与年度均由外层 ProjectContextGate / projectStore 提供，不在本页重复请求项目详情。
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
.gt-wp-filter-bar__stale {
  flex-shrink: 0;
  white-space: nowrap;
}
.gt-wp-filter-bar__stale-count {
  display: inline-block;
  margin-left: 4px;
  padding: 0 6px;
  border-radius: 9px;
  background: var(--el-color-warning-light-8, #faecd8);
  color: var(--el-color-warning, #e6a23c);
  font-size: 12px;
  font-weight: 600;
}
.gt-wp-view-toggle {
  margin: 0 12px;
  display: flex;
  align-items: center;
  gap: 4px;
}
.gt-wp-view-toggle :deep(.is-active-item) {
  color: var(--el-color-primary);
  font-weight: 600;
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
