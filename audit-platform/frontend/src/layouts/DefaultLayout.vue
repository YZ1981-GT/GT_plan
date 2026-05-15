<template>
  <ThreeColumnLayout
    :hide-middle="hideMiddle"
    :catalog-title="catalogTitle"
    @nav-change="onNavChange"
    @view-change="onViewChange"
  >
    <template #nav-review-inbox>
      <router-link
        v-if="isReviewRole"
        to="/review-inbox"
        class="gt-topbar-action-link"
        style="text-decoration: none;"
      >
        <el-tooltip content="待复核底稿收件箱" placement="bottom">
          <el-badge :value="pendingReviewCount" :hidden="pendingReviewCount === 0" type="danger">
            <span class="gt-topbar-action-btn">📋 复核收件箱</span>
          </el-badge>
        </el-tooltip>
      </router-link>
    </template>

    <template #nav-notifications>
      <NotificationCenter />
    </template>

    <template #nav-eqcr>
      <router-link
        v-if="isEqcrEligible"
        to="/eqcr/workbench"
        class="gt-topbar-action-link"
        style="text-decoration: none;"
      >
        <el-tooltip content="EQCR 独立复核工作台" placement="bottom">
          <span class="gt-topbar-action-btn">🛡️ 独立复核</span>
        </el-tooltip>
      </router-link>
      <router-link
        v-if="isEqcrEligible"
        to="/eqcr/metrics"
        class="gt-topbar-action-link"
        style="text-decoration: none; margin-left: 2px;"
      >
        <el-tooltip content="EQCR 指标仪表盘" placement="bottom">
          <span class="gt-topbar-action-btn">📊 EQCR 指标</span>
        </el-tooltip>
      </router-link>
    </template>

    <template #middle>
      <!-- 合并模块：独立树形导航 -->
      <ConsolMiddleNav v-if="isConsolRoute" />
      <!-- 项目浏览模式 -->
      <MiddleProjectList v-else-if="activeModule === 'projects' || activeModule === 'dashboard'" @select="onProjectSelect" />
      <!-- 其他模块占位 -->
      <MiddlePlaceholder v-else :module="activeModule" />
    </template>

    <template #catalog>
      <!-- 合并模块：报表+附注目录 -->
      <ConsolCatalog v-if="isConsolRoute" />
      <!-- 四栏模式：功能目录 -->
      <FourColumnCatalog
        v-else-if="selectedProject"
        :project="selectedProject"
        :active-catalog="activeCatalog"
        @select="onCatalogSelect"
        @tab-change="(tab: string) => activeCatalog = tab"
      />
    </template>

    <template #detail>
      <!-- 三栏浏览模式：右侧显示项目详情 -->
      <DetailProjectPanel v-if="isBrowseMode && !fourCol" :project="selectedProject" />
      <!-- 四栏浏览模式：右侧显示选中目录项的内容 -->
      <FourColumnContent
        v-else-if="isBrowseMode && fourCol"
        :project="selectedProject"
        :catalog-item="selectedCatalogItem"
      />
      <!-- 具体子页面：右侧全宽显示路由内容 -->
      <div v-else class="gt-detail-content">
        <!-- R7-S3-10：联动状态横条 -->
        <LinkageStatusBar
          v-if="staleCount > 0"
          :stale-count="staleCount"
          @recalc="onRecalcStale"
          @detail="$router.push(`/projects/${route.params.projectId}/workpapers?filter=stale`)"
        />
        <router-view v-slot="{ Component, route: viewRoute }">
          <ErrorBoundary :key="viewRoute.fullPath">
            <Transition name="gt-page" mode="out-in">
              <component :is="Component" :key="viewRoute.fullPath" />
            </Transition>
          </ErrorBoundary>
        </router-view>
      </div>
    </template>
  </ThreeColumnLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ThreeColumnLayout from './ThreeColumnLayout.vue'
import MiddleProjectList from '@/components/layout/MiddleProjectList.vue'
import MiddlePlaceholder from '@/components/layout/MiddlePlaceholder.vue'
import DetailProjectPanel from '@/components/layout/DetailProjectPanel.vue'
import FourColumnCatalog from '@/components/layout/FourColumnCatalog.vue'
import FourColumnContent from '@/components/layout/FourColumnContent.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import LinkageStatusBar from '@/components/common/LinkageStatusBar.vue'
import ConsolMiddleNav from '@/components/consolidation/ConsolMiddleNav.vue'
import ConsolCatalog from '@/components/consolidation/ConsolCatalog.vue'
import NotificationCenter from '@/components/collaboration/NotificationCenter.vue'
import { initGlobalBackspace } from '@/composables/useNavigationStack'
import { useRoleContextStore } from '@/stores/roleContext'
import { useProjectStore } from '@/stores/project'
import { getProject } from '@/services/auditPlatformApi'
import { getGlobalReviewInbox } from '@/services/pmApi'

const route = useRoute()
const router = useRouter()
initGlobalBackspace(router)
const roleStore = useRoleContextStore()
const projectStore = useProjectStore()
const selectedProject = ref<any>(null)
const activeModule = ref('projects')
const fourCol = ref(false)
const activeCatalog = ref('reports')
const selectedCatalogItem = ref<any>(null)

// 复核收件箱 badge
const pendingReviewCount = ref(0)
let badgeTimer: ReturnType<typeof setInterval> | null = null

// R7-S3-10：联动状态横条
const staleCount = ref(0)

async function loadStaleCount() {
  const pid = route.params.projectId as string
  if (!pid) { staleCount.value = 0; return }
  try {
    const data = await import('@/services/apiProxy').then(m => m.api.get(`/api/projects/${pid}/stale-summary`))
    staleCount.value = (data as any)?.stale_count || 0
  } catch { staleCount.value = 0 }
}

async function onRecalcStale() {
  const pid = route.params.projectId as string
  if (!pid) return
  try {
    await import('@/services/apiProxy').then(m => m.api.post(`/api/projects/${pid}/trial-balance/recalc`))
    staleCount.value = 0
  } catch { /* ignore */ }
}

// 是否有复核权限（reviewer/partner/admin）
const isReviewRole = computed(() => {
  const role = roleStore.effectiveRole
  return ['reviewer', 'partner', 'admin', 'manager'].includes(role) || roleStore.isPartner || roleStore.isManager
})

// EQCR 独立复核入口可见性：
//   业务约束为 role in ('partner','admin')，具体项目级 EQCR 资格由
//   后端 `GET /api/eqcr/projects` 按 ProjectAssignment.role='eqcr' 过滤；
//   非 EQCR 用户进入工作台会看到空态，不影响合伙人/管理员的巡视能力。
const isEqcrEligible = computed(() => {
  const role = roleStore.effectiveRole
  return ['partner', 'admin', 'eqcr'].includes(role) || roleStore.isPartner
})

async function loadPendingReviewCount() {
  if (!isReviewRole.value) return
  try {
    const res = await getGlobalReviewInbox(1, 1)
    pendingReviewCount.value = res.total || 0
  } catch { /* 静默失败 */ }
}

// 初始化角色上下文
onMounted(async () => {
  if (!roleStore.loaded) {
    await roleStore.initialize()
  }
  loadPendingReviewCount()
  badgeTimer = setInterval(loadPendingReviewCount, 5 * 60 * 1000)
})

onBeforeUnmount(() => {
  if (badgeTimer) clearInterval(badgeTimer)
})

// 进入项目子页面时加载项目角色
watch(() => route.params.projectId, async (pid) => {
  if (pid && typeof pid === 'string') {
    await roleStore.loadProjectRole(pid)
    loadStaleCount()
  } else {
    roleStore.currentProjectRole = null
    staleCount.value = 0
  }
}, { immediate: true })

// 路由变化时自动同步项目上下文到 projectStore
watch(
  () => [route.params.projectId, route.query.year],
  async () => { await projectStore.syncFromRoute(route) },
  { immediate: true }
)

const catalogTitle = computed(() => {
  if (!fourCol.value) return ''
  if (isConsolRoute.value) return '报表附注'
  const titles: Record<string, string> = {
    reports: '报表', notes: '附注', workpapers: '底稿',
    adjustments: '调整分录', trial_balance: '试算表',
  }
  return titles[activeCatalog.value] || '功能目录'
})

// 浏览模式：首页/项目列表/其他一级模块（非具体项目子页面和新建向导）
// 全宽模式路径（不显示中间栏项目列表）
const FULLWIDTH_PATHS = [
  '/', '/projects/new', '/recycle-bin', '/forum', '/private-storage',
  '/knowledge', '/consolidation', '/attachments', '/confirmation',
  '/archive', '/work-hours',
]
const FULLWIDTH_PREFIXES = ['/extension/', '/settings', '/dashboard/', '/eqcr/']

function isFullWidthPath(p: string): boolean {
  if (FULLWIDTH_PATHS.includes(p)) return true
  return FULLWIDTH_PREFIXES.some(prefix => p.startsWith(prefix))
}

// 合并模块路由判断
const isConsolRoute = computed(() => {
  return !!route.path.match(/^\/projects\/[^/]+\/consolidation/)
})

const isBrowseMode = computed(() => {
  const p = route.path
  if (isFullWidthPath(p)) return false
  return p === '/projects' || !p.match(/^\/projects\/[^/]+\//)
})

// 隐藏中间栏（合并模块除外，它有自己的中间栏）
const hideMiddle = computed(() => {
  const p = route.path
  if (isConsolRoute.value) return false  // 合并模块显示中间栏
  if (isFullWidthPath(p)) return true
  return !!p.match(/^\/projects\/[^/]+\//)
})

function onProjectSelect(project: any) {
  selectedProject.value = project
}

function onNavChange(navKey: string) {
  activeModule.value = navKey
}

function onViewChange(mode: 'three' | 'four') {
  fourCol.value = mode === 'four'
}

function onCatalogSelect(item: any) {
  // 处理项目切换
  if (item?.type === 'switch_project' && item.project_id) {
    // 从项目列表中找到目标项目并切换（静态导入，避免动态 import 无意义开销）
    getProject(item.project_id).then((proj: any) => {
      if (proj) {
        selectedProject.value = proj
      }
    }).catch(() => {})
    return
  }
  selectedCatalogItem.value = item
}
</script>

<style scoped>
.gt-detail-content {
  height: 100%;
  overflow-y: auto;
  padding: var(--gt-space-4);
}

/* 顶栏操作按钮（白色文字，深紫背景上清晰可见） */
.gt-topbar-action-link {
  display: inline-flex;
  align-items: center;
}
.gt-topbar-action-btn {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 500;
  color: #fff;
  white-space: nowrap;
  cursor: pointer;
  transition: background 0.15s;
}
.gt-topbar-action-btn:hover {
  background: rgba(255, 255, 255, 0.12);
}
</style>
