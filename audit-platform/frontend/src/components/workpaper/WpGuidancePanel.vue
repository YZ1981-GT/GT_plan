<script setup lang="ts">
/**
 * WpGuidancePanel — 底稿编制指导浮动面板（全量覆盖版）
 *
 * 右侧固定面板，包含「编制说明」+「AI 对话」双 Tab。
 * 编制说明从后端 GET /api/workpapers/{wpId}/guidance 提取。
 * AI 对话为 P1 预留，当 aiEnabled=false 时隐藏。
 * 面板展开/折叠带 CSS transition，主编辑区宽度自适应收缩。
 *
 * 性能优化：
 * - 懒加载子组件（defineAsyncComponent）
 * - Vue onErrorCaptured 隔离面板异常（不影响底稿主体）
 * - sessionStorage 缓存 guidance（按 wp_code）
 * - 超 3s skeleton 占位
 *
 * Requirements: 1.1~1.8, 8.4, 8.5, 8.6, 10.1~10.4
 */
import { computed, watch, onMounted, ref, defineAsyncComponent, onErrorCaptured } from 'vue'
import { useGuidancePanelStore, type WpContext } from '@/stores/guidancePanelStore'

// ─── Lazy-loaded components ─────────────────────────────────────────────────

const GuidanceTabContent = defineAsyncComponent(() =>
  import('./guidance/GuidanceTabContent.vue'),
)
const AiChatTab = defineAsyncComponent(() =>
  import('./guidance/AiChatTab.vue'),
)

// ─── Props ──────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  wpCode: string
  wpName: string
  componentType: string
  projectId: string
  year: number
}>()

// ─── Store ──────────────────────────────────────────────────────────────────

const store = useGuidancePanelStore()

// ─── Error boundary ─────────────────────────────────────────────────────────

const panelError = ref<Error | null>(null)

onErrorCaptured((err) => {
  panelError.value = err instanceof Error ? err : new Error(String(err))
  return false // prevent propagation to main editor
})

// ─── Skeleton delay ─────────────────────────────────────────────────────────

const showSkeleton = ref(false)
let skeletonTimer: ReturnType<typeof setTimeout> | null = null

watch(() => store.guidanceLoading, (loading) => {
  if (loading) {
    // 超过 3s 才显示 skeleton
    skeletonTimer = setTimeout(() => { showSkeleton.value = true }, 3000)
  } else {
    if (skeletonTimer) { clearTimeout(skeletonTimer); skeletonTimer = null }
    showSkeleton.value = false
  }
})

// ─── Context sync ───────────────────────────────────────────────────────────

function syncContext() {
  const ctx: WpContext = {
    wpId: props.wpId,
    wpCode: props.wpCode,
    wpName: props.wpName,
    componentType: props.componentType,
    projectId: props.projectId,
    year: props.year,
  }
  store.setWpContext(ctx)
  // 如果没有缓存数据，发起请求
  if (!store.guidanceData) {
    store.fetchGuidance()
  }
}

// 监听 props 变化（底稿切换）
watch(
  () => props.wpId,
  () => {
    panelError.value = null // 切换底稿时清除错误
    syncContext()
  },
  { immediate: false },
)

onMounted(() => syncContext())

// ─── Tab ────────────────────────────────────────────────────────────────────

const tabValue = computed({
  get: () => store.activeTab,
  set: (v) => store.setActiveTab(v as 'guidance' | 'ai'),
})
</script>

<template>
  <!-- 折叠态：右侧触发按钮 -->
  <div
    v-if="!store.isOpen"
    class="gt-guidance-trigger"
    @click="store.open()"
    title="展开编制指导面板"
  >
    <el-icon :size="16"><Document /></el-icon>
    <span class="gt-guidance-trigger__text">编制指导</span>
  </div>

  <!-- 展开态：面板主体 -->
  <transition name="gt-panel-slide">
    <div v-if="store.isOpen" class="gt-guidance-panel">
      <!-- Header -->
      <div class="gt-guidance-panel__header">
        <span class="gt-guidance-panel__title">编制指导</span>
        <el-icon
          class="gt-guidance-panel__fold-btn"
          :size="18"
          @click="store.close()"
          title="折叠面板"
        >
          <ArrowRight />
        </el-icon>
      </div>

      <!-- Error boundary fallback -->
      <div v-if="panelError" class="gt-guidance-panel__error">
        <p class="gt-guidance-panel__error-title">面板加载异常</p>
        <p class="gt-guidance-panel__error-msg">{{ panelError.message }}</p>
        <el-button size="small" @click="panelError = null">重试</el-button>
      </div>

      <!-- Tabs -->
      <el-tabs v-else v-model="tabValue" class="gt-guidance-panel__tabs">
        <el-tab-pane label="编制说明" name="guidance">
          <!-- Loading skeleton -->
          <div v-if="store.guidanceLoading && showSkeleton" class="gt-guidance-panel__skeleton">
            <el-skeleton :rows="6" animated />
          </div>
          <!-- Loading but < 3s: 空白占位 -->
          <div v-else-if="store.guidanceLoading" class="gt-guidance-panel__loading-placeholder">
            <el-icon class="is-loading" :size="20"><Loading /></el-icon>
            <span>加载编制说明…</span>
          </div>
          <!-- Content -->
          <GuidanceTabContent
            v-else-if="store.guidanceData"
            :guidance-data="store.guidanceData"
          />
          <!-- No data fallback -->
          <div v-else class="gt-guidance-panel__empty">
            <p>暂无编制说明数据</p>
          </div>
        </el-tab-pane>

        <el-tab-pane
          v-if="store.aiEnabled"
          label="AI 对话"
          name="ai"
        >
          <AiChatTab
            :wp-id="props.wpId"
            :wp-code="props.wpCode"
            :wp-name="props.wpName"
            :project-id="props.projectId"
            :recommended-questions="store.guidanceData?.recommended_questions || []"
            :ai-available="store.aiEnabled"
          />
        </el-tab-pane>
      </el-tabs>
    </div>
  </transition>
</template>

<script lang="ts">
import { Document, ArrowRight, Loading } from '@element-plus/icons-vue'

export default {
  components: { Document, ArrowRight, Loading },
}
</script>

<style scoped>
.gt-guidance-trigger {
  position: fixed;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  writing-mode: vertical-rl;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 12px 6px;
  background: var(--gt-bg-light, #f4f0fa);
  border: 1px solid var(--gt-border-light, #d8b8ee);
  border-right: none;
  border-radius: 8px 0 0 8px;
  cursor: pointer;
  z-index: 100;
  transition: background 0.2s;
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  font-weight: 500;
}
.gt-guidance-trigger:hover {
  background: var(--gt-border-light, #d8b8ee);
}
.gt-guidance-trigger__text {
  letter-spacing: 2px;
}

.gt-guidance-panel {
  width: 380px;
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-left: 1px solid var(--gt-border-light, #d8b8ee);
  overflow: hidden;
  flex-shrink: 0;
}

.gt-guidance-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 16px;
  background: var(--gt-bg-light, #f4f0fa);
  border-bottom: 1px solid var(--gt-border-light, #d8b8ee);
  flex-shrink: 0;
}

.gt-guidance-panel__title {
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
}

.gt-guidance-panel__fold-btn {
  cursor: pointer;
  color: var(--gt-primary, #4b2d77);
  transition: transform 0.2s;
}
.gt-guidance-panel__fold-btn:hover {
  transform: translateX(2px);
}

.gt-guidance-panel__tabs {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.gt-guidance-panel__tabs :deep(.el-tabs__header) {
  margin: 0;
  padding: 0 16px;
  border-bottom: 1px solid var(--gt-border-light, #d8b8ee);
}

.gt-guidance-panel__tabs :deep(.el-tabs__content) {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.gt-guidance-panel__tabs :deep(.el-tab-pane) {
  height: 100%;
}

.gt-guidance-panel__tabs :deep(#pane-ai) {
  overflow: hidden;
  padding: 0;
}

.gt-guidance-panel__tabs :deep(.el-tabs__item.is-active) {
  color: var(--gt-primary, #4b2d77);
}

.gt-guidance-panel__tabs :deep(.el-tabs__active-bar) {
  background-color: var(--gt-primary, #4b2d77);
}

.gt-guidance-panel__skeleton {
  padding: 8px 0;
}

.gt-guidance-panel__loading-placeholder {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 24px 0;
  color: var(--gt-primary, #4b2d77);
  font-size: 13px;
}

.gt-guidance-panel__empty {
  padding: 24px 0;
  text-align: center;
  color: #999;
  font-size: 13px;
}

/* Error boundary */
.gt-guidance-panel__error {
  padding: 24px 16px;
  text-align: center;
}

.gt-guidance-panel__error-title {
  font-size: 14px;
  font-weight: 600;
  color: #f56c6c;
  margin-bottom: 8px;
}

.gt-guidance-panel__error-msg {
  font-size: 12px;
  color: #999;
  margin-bottom: 12px;
  word-break: break-all;
}

/* Slide transition */
.gt-panel-slide-enter-active,
.gt-panel-slide-leave-active {
  transition: all 0.3s ease;
}
.gt-panel-slide-enter-from,
.gt-panel-slide-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
</style>
