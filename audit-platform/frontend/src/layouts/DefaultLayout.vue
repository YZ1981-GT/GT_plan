<template>
  <ThreeColumnLayout
    :hide-middle="hideMiddle"
    :catalog-title="catalogTitle"
    @nav-change="onNavChange"
    @view-change="onViewChange"
  >
    <template #middle>
      <!-- 项目浏览模式 -->
      <MiddleProjectList v-if="activeModule === 'projects' || activeModule === 'dashboard'" @select="onProjectSelect" />
      <!-- 其他模块占位 -->
      <MiddlePlaceholder v-else :module="activeModule" />
    </template>

    <template #catalog>
      <!-- 四栏模式：功能目录 -->
      <FourColumnCatalog
        v-if="selectedProject"
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
        <router-view />
      </div>
    </template>
  </ThreeColumnLayout>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useRoute } from 'vue-router'
import ThreeColumnLayout from './ThreeColumnLayout.vue'
import MiddleProjectList from '@/components/layout/MiddleProjectList.vue'
import MiddlePlaceholder from '@/components/layout/MiddlePlaceholder.vue'
import DetailProjectPanel from '@/components/layout/DetailProjectPanel.vue'
import FourColumnCatalog from '@/components/layout/FourColumnCatalog.vue'
import FourColumnContent from '@/components/layout/FourColumnContent.vue'

const route = useRoute()
const selectedProject = ref<any>(null)
const activeModule = ref('projects')
const fourCol = ref(false)
const activeCatalog = ref('reports')
const selectedCatalogItem = ref<any>(null)

const catalogTitle = computed(() => {
  if (!fourCol.value) return ''
  const titles: Record<string, string> = {
    reports: '报表', notes: '附注', workpapers: '底稿',
    adjustments: '调整分录', trial_balance: '试算表',
  }
  return titles[activeCatalog.value] || '功能目录'
})

// 浏览模式：首页/项目列表/其他一级模块（非具体项目子页面和新建向导）
const isBrowseMode = computed(() => {
  const p = route.path
  if (p === '/projects/new' || p.startsWith('/extension/') || p.startsWith('/settings/') || p === '/recycle-bin' || p === '/forum' || p === '/private-storage') return false
  return p === '/' || p === '/projects' || !p.match(/^\/projects\/[^/]+\//)
})

// 隐藏中间栏：在具体项目子页面、新建向导、扩展页面、设置页面、回收站、论坛、私人库时
const hideMiddle = computed(() => {
  const p = route.path
  if (p === '/projects/new' || p.startsWith('/extension/') || p.startsWith('/settings/') || p === '/recycle-bin' || p === '/forum' || p === '/private-storage') return true
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
