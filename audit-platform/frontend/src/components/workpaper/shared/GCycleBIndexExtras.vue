<script setup lang="ts">
/**
 * G12/G13/G14 底稿目录 Tab — 保留 GtBIndex 底稿架构 + 本循环跨底稿网格（D4 式清单下方）
 */
import { computed, inject } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GtBArchitectureTree from '../GtBArchitectureTree.vue'
import {
  buildCycleArchitectureHtmlData,
  type CycleArchitectureSheet,
} from '../composables/gCycleIndexRouting'

interface CycleWorkpaper {
  wp_code: string
  wp_name: string
  wp_id: string | null
  status: string
  is_current: boolean
}

const props = defineProps<{
  wpId: string
  projectId: string
  sheetName?: string
  wpCode?: string
  htmlData?: Record<string, unknown>
  availableSheets?: CycleArchitectureSheet[]
  showArchitecture?: boolean
}>()

const showArchitecture = computed(() => props.showArchitecture !== false)
const route = useRoute()
const router = useRouter()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const projectId = computed(() => props.projectId || (route.params.projectId as string) || '')

const architectureHtmlData = computed(() =>
  buildCycleArchitectureHtmlData(props.htmlData, props.availableSheets, props.wpCode),
)

const cycleWorkpapers = computed<CycleWorkpaper[]>(() => {
  const list = props.htmlData?.cycle_workpapers
  return Array.isArray(list) ? (list as CycleWorkpaper[]) : []
})

function handleNavigate(sheetName: string) {
  if (jumpToSection) {
    jumpToSection(sheetName)
  }
}

function onCycleCardClick(wp: CycleWorkpaper) {
  if (!wp.wp_id || wp.is_current) return
  const pid = projectId.value
  if (!pid) return
  router.push({
    name: 'WorkpaperEditor',
    params: { projectId: pid, wpId: wp.wp_id },
  })
}
</script>

<template>
  <div class="g-cycle-b-index-extras" data-testid="g-cycle-b-index-extras">
    <div v-if="showArchitecture" class="g-cycle-b-index-extras__navigation">
      <div class="g-cycle-b-index-extras__navigation-header">
        <h4 class="g-cycle-b-index-extras__navigation-title">底稿架构</h4>
        <span class="g-cycle-b-index-extras__navigation-hint">点击程序卡片可跳转至对应底稿</span>
      </div>
      <GtBArchitectureTree
        :wp-id="wpId"
        :project-id="projectId"
        :active-sheet="sheetName"
        :html-data="architectureHtmlData"
        @navigate="handleNavigate"
      />
    </div>

    <div v-if="cycleWorkpapers.length > 0" class="g-cycle-b-index-extras__cycle">
      <div class="g-cycle-b-index-extras__cycle-header">
        <h4 class="g-cycle-b-index-extras__cycle-title">本循环底稿目录</h4>
        <span class="g-cycle-b-index-extras__cycle-hint">点击可跳转至同循环其他底稿（灰色表示尚未生成）</span>
      </div>
      <div class="g-cycle-b-index-extras__cycle-grid">
        <div
          v-for="wp in cycleWorkpapers"
          :key="wp.wp_code"
          class="g-cycle-b-index-extras__cycle-card"
          :class="{
            'is-current': wp.is_current,
            'is-disabled': !wp.wp_id,
          }"
          @click="onCycleCardClick(wp)"
        >
          <div class="g-cycle-b-index-extras__cycle-card-top">
            <span class="g-cycle-b-index-extras__cycle-code">{{ wp.wp_code }}</span>
            <el-tag
              v-if="wp.is_current"
              size="small"
              effect="plain"
              class="g-cycle-b-index-extras__cycle-current-tag"
            >当前</el-tag>
          </div>
          <span class="g-cycle-b-index-extras__cycle-name" :title="wp.wp_name">{{ wp.wp_name }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.g-cycle-b-index-extras {
  padding: 0 12px 16px;
  font-size: var(--wp-font-size, 13px);
}

.g-cycle-b-index-extras__navigation {
  margin-top: 8px;
  padding-top: 20px;
  border-top: 1px solid var(--gt-color-border-purple-light, #e8e4f0);
}

.g-cycle-b-index-extras__navigation-header,
.g-cycle-b-index-extras__cycle-header {
  display: flex;
  align-items: baseline;
  gap: 12px;
  margin-bottom: 12px;
}

.g-cycle-b-index-extras__navigation-title,
.g-cycle-b-index-extras__cycle-title {
  margin: 0;
  font-size: 16px;
  font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}

.g-cycle-b-index-extras__navigation-hint,
.g-cycle-b-index-extras__cycle-hint {
  font-size: 12px;
  color: var(--gt-color-text-tertiary, #909399);
}

.g-cycle-b-index-extras__cycle {
  margin-top: 28px;
}

.g-cycle-b-index-extras__cycle-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px;
}

.g-cycle-b-index-extras__cycle-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 10px 12px;
  border: 1px solid var(--gt-color-border-purple, #e8e4f0);
  border-radius: 8px;
  background: var(--gt-color-bg-white, #fff);
  cursor: pointer;
  transition: all 0.2s;
}

.g-cycle-b-index-extras__cycle-card:hover {
  border-color: var(--gt-color-primary, #4b2d77);
  box-shadow: 0 2px 8px rgba(75, 45, 119, 0.12);
  transform: translateY(-2px);
}

.g-cycle-b-index-extras__cycle-card.is-current {
  border-color: var(--gt-color-primary, #4b2d77);
  background: var(--gt-color-primary-bg, #f4f0fa);
  box-shadow: 0 0 0 1px var(--gt-color-primary, #4b2d77);
  cursor: default;
}

.g-cycle-b-index-extras__cycle-card.is-disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.g-cycle-b-index-extras__cycle-card.is-disabled:hover {
  border-color: var(--gt-color-border-purple, #e8e4f0);
  box-shadow: none;
  transform: none;
}

.g-cycle-b-index-extras__cycle-card-top {
  display: flex;
  align-items: center;
  gap: 6px;
}

.g-cycle-b-index-extras__cycle-code {
  font-size: var(--wp-font-size, 13px);
  font-weight: 700;
  color: var(--gt-color-primary, #4b2d77);
}

.g-cycle-b-index-extras__cycle-current-tag {
  margin-left: auto;
}

.g-cycle-b-index-extras__cycle-name {
  font-size: var(--wp-font-size, 13px);
  line-height: 1.4;
  color: var(--gt-color-text-primary, #303133);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
