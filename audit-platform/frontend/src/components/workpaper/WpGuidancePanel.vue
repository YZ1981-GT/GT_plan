<script setup lang="ts">
/**
 * WpGuidancePanel — 底稿编制说明 right-rail。
 *
 * 面板只同步结构化 context；自动请求所有权全部在 guidance store。
 * AI 对话由平台统一 AI 面板承载，本组件不再挂载第二套聊天状态。
 */
import {
  defineAsyncComponent,
  onBeforeUnmount,
  onErrorCaptured,
  ref,
  watch,
} from 'vue'
import { ArrowRight, Document, Loading, RefreshRight } from '@element-plus/icons-vue'
import {
  buildGuidanceContextIdentity,
  useGuidancePanelStore,
  type GuidanceHost,
  type WpContext,
} from '@/stores/guidancePanelStore'

const GuidanceTabContent = defineAsyncComponent(() =>
  import('./guidance/GuidanceTabContent.vue'),
)

const props = withDefaults(defineProps<{
  wpId: string
  wpCode: string
  wpName: string
  componentType: string
  projectId: string
  year: number
  sheetCode?: string | null
  sheetName?: string
  sheetUid?: string | null
  sheetUidNullReason?: string | null
  host?: GuidanceHost
  wholeWorkbook?: boolean
  ownerEpoch?: number
  contextRevision?: number
  /** When true, trigger DOM is owned by WorkpaperCapabilityShell (G-RAIL / F-SHELL). */
  shellOwned?: boolean
}>(), {
  sheetCode: null,
  sheetName: '',
  sheetUid: null,
  sheetUidNullReason: null,
  host: 'html',
  wholeWorkbook: false,
  ownerEpoch: 0,
  contextRevision: 0,
  shellOwned: false,
})

const store = useGuidancePanelStore()
const panelError = ref<Error | null>(null)
const showSkeleton = ref(false)
let skeletonTimer: ReturnType<typeof setTimeout> | null = null
let ownedContextIdentity = ''

onErrorCaptured((error) => {
  panelError.value = error instanceof Error ? error : new Error(String(error))
  return false
})

watch(() => store.guidanceLoading, (loading) => {
  if (skeletonTimer) {
    clearTimeout(skeletonTimer)
    skeletonTimer = null
  }
  if (loading) {
    skeletonTimer = setTimeout(() => {
      showSkeleton.value = true
    }, 3000)
  } else {
    showSkeleton.value = false
  }
})

function syncContext(): void {
  const context: WpContext = {
    wpId: props.wpId,
    wpCode: props.wpCode,
    wpName: props.wpName,
    componentType: props.componentType,
    projectId: props.projectId,
    year: props.year,
    sheetCode: props.sheetCode,
    sheetName: props.sheetName,
    sheetUid: props.sheetUid,
    sheetUidNullReason: props.sheetUidNullReason,
    host: props.host,
    wholeWorkbook: props.wholeWorkbook,
    ownerEpoch: props.ownerEpoch,
    contextRevision: props.contextRevision,
  }
  ownedContextIdentity = buildGuidanceContextIdentity(context)
  store.setWpContext(context)
}

watch(
  () => [
    props.wpId,
    props.projectId,
    props.wpCode,
    props.sheetCode,
    props.sheetName,
    props.sheetUid,
    props.host,
    props.wholeWorkbook,
    props.ownerEpoch,
    props.contextRevision,
  ] as const,
  () => {
    panelError.value = null
    syncContext()
  },
  { immediate: true },
)

onBeforeUnmount(() => {
  if (skeletonTimer) clearTimeout(skeletonTimer)
  store.clearWpContext(ownedContextIdentity)
})
</script>

<template>
  <button
    v-if="!shellOwned && !store.isOpen"
    class="gt-guidance-trigger"
    type="button"
    title="展开编制说明"
    aria-label="展开编制说明"
    @click="store.open()"
  >
    <el-icon :size="16"><Document /></el-icon>
    <span class="gt-guidance-trigger__text">编制说明</span>
  </button>

  <transition name="gt-panel-slide">
    <aside
      v-if="shellOwned || store.isOpen"
      class="gt-guidance-panel"
      aria-label="底稿编制说明"
      :data-shell-owned="shellOwned ? '1' : '0'"
    >
      <header class="gt-guidance-panel__header">
        <div class="gt-guidance-panel__heading">
          <span class="gt-guidance-panel__title">编制说明</span>
          <span v-if="sheetName" class="gt-guidance-panel__sheet" :title="sheetName">
            {{ sheetName }}
          </span>
        </div>
        <button
          class="gt-guidance-panel__fold-btn"
          type="button"
          title="折叠编制说明"
          aria-label="折叠编制说明"
          @click="store.close()"
        >
          <el-icon :size="18"><ArrowRight /></el-icon>
        </button>
      </header>

      <div class="gt-guidance-panel__content">
        <div v-if="panelError" class="gt-guidance-panel__error">
          <p class="gt-guidance-panel__error-title">面板渲染异常</p>
          <p class="gt-guidance-panel__error-msg">{{ panelError.message }}</p>
          <el-button size="small" @click="panelError = null">重新渲染</el-button>
        </div>

        <div v-else-if="store.guidanceError" class="gt-guidance-panel__error">
          <p class="gt-guidance-panel__error-title">编制说明加载失败</p>
          <p class="gt-guidance-panel__error-msg">{{ store.guidanceError }}</p>
          <el-button size="small" :icon="RefreshRight" @click="store.refreshGuidance()">
            重试
          </el-button>
        </div>

        <div v-else-if="store.guidanceLoading && showSkeleton" class="gt-guidance-panel__skeleton">
          <el-skeleton :rows="6" animated />
        </div>

        <div v-else-if="store.guidanceLoading" class="gt-guidance-panel__loading-placeholder">
          <el-icon class="is-loading" :size="20"><Loading /></el-icon>
          <span>加载编制说明…</span>
        </div>

        <GuidanceTabContent
          v-else-if="store.guidanceData"
          :guidance-data="store.guidanceData"
        />

        <div v-else class="gt-guidance-panel__empty">
          <p>暂无编制说明数据</p>
        </div>

      </div>

      <footer v-if="store.aiEnabled" class="gt-guidance-panel__footer">
        需要辅助分析时，请使用页面顶部的「AI 审计助手」。
      </footer>
    </aside>
  </transition>
</template>

<style scoped>
.gt-guidance-trigger {
  position: relative;
  align-self: center;
  flex: 0 0 auto;
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
  color: var(--gt-primary, #4b2d77);
  font-size: 12px;
  font-weight: 500;
  transition: background 0.2s;
}

.gt-guidance-trigger:hover {
  background: var(--gt-border-light, #d8b8ee);
}

.gt-guidance-trigger__text {
  letter-spacing: 2px;
}

.gt-guidance-panel {
  width: 380px;
  min-width: 320px;
  height: 100%;
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  background: #fff;
  border-left: 1px solid var(--gt-border-light, #d8b8ee);
  overflow: hidden;
}

.gt-guidance-panel__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 16px;
  background: var(--gt-bg-light, #f4f0fa);
  border-bottom: 1px solid var(--gt-border-light, #d8b8ee);
  flex-shrink: 0;
}

.gt-guidance-panel__heading {
  min-width: 0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.gt-guidance-panel__title {
  flex: 0 0 auto;
  font-size: 14px;
  font-weight: 600;
  color: var(--gt-primary, #4b2d77);
}

.gt-guidance-panel__sheet {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 11px;
  color: #777;
}

.gt-guidance-panel__fold-btn {
  flex: 0 0 auto;
  display: inline-flex;
  align-items: center;
  padding: 2px;
  border: 0;
  background: transparent;
  cursor: pointer;
  color: var(--gt-primary, #4b2d77);
  transition: transform 0.2s;
}

.gt-guidance-panel__fold-btn:hover {
  transform: translateX(2px);
}

.gt-guidance-panel__content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 12px 14px;
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
  font-size: var(--wp-font-size, 13px);
}

.gt-guidance-panel__empty {
  padding: 24px 0;
  text-align: center;
  color: #999;
  font-size: var(--wp-font-size, 13px);
}

.gt-guidance-panel__error {
  padding: 24px 16px;
  text-align: center;
}

.gt-guidance-panel__error-title {
  margin: 0 0 8px;
  font-size: 14px;
  font-weight: 600;
  color: #f56c6c;
}

.gt-guidance-panel__error-msg {
  margin: 0 0 12px;
  font-size: 12px;
  color: #777;
  word-break: break-word;
}

.gt-guidance-panel__footer {
  flex: 0 0 auto;
  padding: 8px 14px;
  border-top: 1px solid #eee;
  background: #fafafa;
  color: #777;
  font-size: 11px;
  line-height: 1.5;
}

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
