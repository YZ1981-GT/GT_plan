<template>
  <ThreeColumnLayout :hide-middle="hideMiddle" @nav-change="onNavChange">
    <template #middle>
      <!-- 项目浏览模式 -->
      <MiddleProjectList v-if="activeModule === 'projects' || activeModule === 'dashboard'" @select="onProjectSelect" />
      <!-- 其他模块占位 -->
      <MiddlePlaceholder v-else :module="activeModule" />
    </template>

    <template #detail>
      <!-- 三栏浏览模式：右侧显示项目详情 -->
      <DetailProjectPanel v-if="isBrowseMode" :project="selectedProject" />
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

const route = useRoute()
const selectedProject = ref<any>(null)
const activeModule = ref('projects')

// 浏览模式：首页/项目列表/其他一级模块（非具体项目子页面和新建向导）
const isBrowseMode = computed(() => {
  const p = route.path
  if (p === '/projects/new' || p.startsWith('/extension/')) return false
  return p === '/' || p === '/projects' || !p.match(/^\/projects\/[^/]+\//)
})

// 隐藏中间栏：在具体项目子页面、新建向导、扩展页面时
const hideMiddle = computed(() => {
  const p = route.path
  if (p === '/projects/new' || p.startsWith('/extension/')) return true
  return !!p.match(/^\/projects\/[^/]+\//)
})

function onProjectSelect(project: any) {
  selectedProject.value = project
}

function onNavChange(navKey: string) {
  activeModule.value = navKey
}
</script>

<style scoped>
.gt-detail-content {
  height: 100%;
  overflow-y: auto;
  padding: var(--gt-space-4);
}
</style>
