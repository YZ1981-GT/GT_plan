<template>
  <ThreeColumnLayout
    :hide-middle="hideMiddle"
    :catalog-title="catalogTitle"
    @nav-change="onNavChange"
    @view-change="onViewChange"
  >
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
        <ErrorBoundary>
          <router-view v-slot="{ Component }">
            <Transition name="gt-page" mode="out-in">
              <component :is="Component" />
            </Transition>
          </router-view>
        </ErrorBoundary>
      </div>
    </template>
  </ThreeColumnLayout>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute } from 'vue-router'
import ThreeColumnLayout from './ThreeColumnLayout.vue'
import MiddleProjectList from '@/components/layout/MiddleProjectList.vue'
import MiddlePlaceholder from '@/components/layout/MiddlePlaceholder.vue'
import DetailProjectPanel from '@/components/layout/DetailProjectPanel.vue'
import FourColumnCatalog from '@/components/layout/FourColumnCatalog.vue'
import FourColumnContent from '@/components/layout/FourColumnContent.vue'
import ErrorBoundary from '@/components/ErrorBoundary.vue'
import ConsolMiddleNav from '@/components/consolidation/ConsolMiddleNav.vue'
import ConsolCatalog from '@/components/consolidation/ConsolCatalog.vue'
import { useRoleContextStore } from '@/stores/roleContext'
import { useProjectStore } from '@/stores/project'

const route = useRoute()
const roleStore = useRoleContextStore()
const projectStore = useProjectStore()
const selectedProject = ref<any>(null)
const activeModule = ref('projects')
const fourCol = ref(false)
const activeCatalog = ref('reports')
const selectedCatalogItem = ref<any>(null)

// 初始化角色上下文
onMounted(async () => {
  if (!roleStore.loaded) {
    await roleStore.initialize()
  }
})

// 进入项目子页面时加载项目角色
watch(() => route.params.projectId, async (pid) => {
  if (pid && typeof pid === 'string') {
    await roleStore.loadProjectRole(pid)
  } else {
    roleStore.currentProjectRole = null
  }
}, { immediate: true })

// 路由变化时自动同步项目上下文到 projectStore
watch(
  () => [route.params.projectId, route.query.year],
  () => { projectStore.syncFromRoute(route) },
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
const FULLWIDTH_PREFIXES = ['/extension/', '/settings', '/dashboard/']

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
    // 从项目列表中找到目标项目并切换
    import('@/services/auditPlatformApi').then(({ getProject }) => {
      getProject(item.project_id).then((proj: any) => {
        if (proj) {
          selectedProject.value = proj
        }
      }).catch(() => {})
    })
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
</style>
