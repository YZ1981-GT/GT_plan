<template>
  <div
    class="dsh-panel"
    :class="[
      `dsh-panel--${layoutMode}`,
      { 'dsh-panel--open': modelValue },
    ]"
  >
    <!-- 折叠态：侧边触发按钮（语义 button） -->
    <button
      v-if="!modelValue"
      ref="triggerRef"
      class="dsh-panel-trigger"
      type="button"
      :aria-label="'打开 AI 助手'"
      :aria-expanded="false"
      aria-controls="dsh-panel-region"
      @click="handleOpen"
    >
      <span class="dsh-panel-trigger-icon" aria-hidden="true">
        <el-icon :size="20"><ChatDotSquare /></el-icon>
      </span>
      <span class="dsh-panel-trigger-text">AI</span>
    </button>

    <!-- 展开态 -->
    <template v-if="modelValue">
      <!-- 遮罩层（drawer/fullscreen 模式） -->
      <Transition name="dsh-backdrop">
        <div
          v-if="layoutMode !== 'column'"
          class="dsh-panel-backdrop"
          aria-hidden="true"
          @click="handleClose"
        />
      </Transition>

      <!-- 面板主体容器 -->
      <Transition name="dsh-slide">
        <div
          id="dsh-panel-region"
          ref="panelRef"
          class="dsh-panel-container"
          :class="`dsh-panel-container--${layoutMode}`"
          :style="containerStyle"
          role="complementary"
          :aria-label="'AI 审计助手面板'"
          aria-modal="false"
          @keydown="handlePanelKeydown"
        >
          <!-- 左侧拖拽手柄（column/drawer 模式，语义 button） -->
          <button
            v-if="layoutMode !== 'fullscreen'"
            class="dsh-panel-resizer"
            type="button"
            :aria-label="'调整面板宽度，使用左右方向键微调'"
            :aria-valuemin="320"
            :aria-valuemax="800"
            :aria-valuenow="panelWidth"
            role="separator"
            aria-orientation="vertical"
            @mousedown="startResize"
            @touchstart="startResize"
            @keydown="handleResizerKeydown"
          />

          <!-- 面板内容 -->
          <div class="dsh-panel-body">
            <div class="dsh-panel-header">
              <span class="dsh-panel-title" id="dsh-panel-title">
                <el-icon :size="16" aria-hidden="true"><ChatDotSquare /></el-icon>
                AI 审计助手
              </span>
              <div class="dsh-panel-actions">
                <el-tooltip content="在新窗口打开" placement="left">
                  <button
                    class="dsh-panel-action"
                    type="button"
                    aria-label="在新窗口打开 AI 助手"
                    @click="openInNewWindow"
                  >
                    <el-icon :size="16"><Link /></el-icon>
                  </button>
                </el-tooltip>
                <el-tooltip content="收起面板" placement="left">
                  <button
                    ref="closeButtonRef"
                    class="dsh-panel-action"
                    type="button"
                    aria-label="收起 AI 助手面板"
                    :aria-expanded="true"
                    aria-controls="dsh-panel-region"
                    @click="handleClose"
                  >
                    <el-icon :size="16"><DArrowRight /></el-icon>
                  </button>
                </el-tooltip>
              </div>
            </div>
            <div class="dsh-panel-content">
              <PlatformAiChatPanel :host="aiHost" :visible="modelValue" />
            </div>
          </div>
        </div>
      </Transition>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * DshPanel — AI 聊天面板布局壳（三档响应式）
 *
 * 布局策略：
 * - `>1400px`（column）：独立列嵌入布局流，可拖拽调整宽度
 * - `769–1400px`（drawer）：fixed drawer + 半透明遮罩
 * - `≤768px`（fullscreen）：全屏覆盖 + safe-area-inset
 *
 * 可访问性：
 * - 触发器/关闭/resizer 全部为语义 button
 * - Escape 关闭（drawer/fullscreen）
 * - Focus trap（drawer/fullscreen）
 * - 焦点恢复到触发器
 * - 背景滚动隔离（drawer/fullscreen）
 * - resizer 支持触摸拖拽和键盘方向键微调
 *
 * Feature: dsh-agent-panel-integration / Task 11
 * Validates: Requirements 1.2, 1.6, 1.7, 14.6
 * Property: 37
 */
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ChatDotSquare, Link, DArrowRight } from '@element-plus/icons-vue'
import { buildAmbientHost } from '@/composables/useAiHostContext'
import { useDshPanelLayout } from '@/composables/useDshPanelLayout'
import PlatformAiChatPanel from '@/components/ai/PlatformAiChatPanel.vue'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  modelValue: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: boolean): void
  (e: 'message-count', count: number): void
}>()

// ---------------------------------------------------------------------------
// 宿主上下文
// ---------------------------------------------------------------------------

const route = useRoute()
const aiHost = computed(() =>
  buildAmbientHost({
    projectId: route.params.projectId ?? route.query.project_id,
    wpId: route.params.wpId ?? route.query.wp_id,
  }),
)

// ---------------------------------------------------------------------------
// 响应式布局
// ---------------------------------------------------------------------------

const {
  layoutMode,
  panelWidth,
  startResize,
  keyboardResize,
} = useDshPanelLayout()

const containerStyle = computed(() => {
  if (layoutMode.value === 'fullscreen') return {}
  return { width: `${panelWidth.value}px` }
})

// ---------------------------------------------------------------------------
// DOM Refs
// ---------------------------------------------------------------------------

const triggerRef = ref<HTMLButtonElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const closeButtonRef = ref<HTMLButtonElement | null>(null)

// ---------------------------------------------------------------------------
// 面板开关（含焦点管理和滚动隔离）
// ---------------------------------------------------------------------------

function handleOpen() {
  emit('update:modelValue', true)
}

function handleClose() {
  emit('update:modelValue', false)
}

// 打开时：锁定背景滚动 + 聚焦面板内首个可交互元素
watch(() => props.modelValue, async (open) => {
  if (open) {
    emit('message-count', 0)

    // drawer/fullscreen 时锁定背景滚动
    if (layoutMode.value !== 'column') {
      document.body.style.overflow = 'hidden'
      // iOS safe-area 需要固定 body
      document.body.style.position = 'fixed'
      document.body.style.width = '100%'
      document.body.style.top = `-${window.scrollY}px`
    }

    // 等待 DOM 渲染后聚焦
    await nextTick()
    await nextTick() // Transition 需要两轮 tick
    if (closeButtonRef.value) {
      closeButtonRef.value.focus()
    }
  } else {
    // 恢复背景滚动
    const scrollY = document.body.style.top
    document.body.style.overflow = ''
    document.body.style.position = ''
    document.body.style.width = ''
    document.body.style.top = ''
    if (scrollY) {
      window.scrollTo(0, parseInt(scrollY || '0') * -1)
    }

    // 焦点恢复到触发器
    await nextTick()
    if (triggerRef.value) {
      triggerRef.value.focus()
    }
  }
})

// layoutMode 变化时，如面板打开需更新滚动隔离
watch(layoutMode, (mode) => {
  if (!props.modelValue) return
  if (mode === 'column') {
    // column 模式无需隔离
    document.body.style.overflow = ''
    document.body.style.position = ''
    document.body.style.width = ''
    document.body.style.top = ''
  } else {
    document.body.style.overflow = 'hidden'
    document.body.style.position = 'fixed'
    document.body.style.width = '100%'
    document.body.style.top = `-${window.scrollY}px`
  }
})

// ---------------------------------------------------------------------------
// 键盘处理
// ---------------------------------------------------------------------------

/** 面板级键盘：Escape 关闭（drawer/fullscreen）+ Tab focus trap */
function handlePanelKeydown(e: KeyboardEvent) {
  // Escape 关闭（仅 drawer/fullscreen 模式）
  if (e.key === 'Escape' && layoutMode.value !== 'column') {
    e.preventDefault()
    e.stopPropagation()
    handleClose()
    return
  }

  // Focus trap（drawer/fullscreen 模式）
  if (e.key === 'Tab' && layoutMode.value !== 'column') {
    trapFocus(e)
  }
}

/** Resizer 键盘微调 */
function handleResizerKeydown(e: KeyboardEvent) {
  if (e.key === 'ArrowLeft') {
    e.preventDefault()
    keyboardResize('wider') // 向左 = 面板加宽
  } else if (e.key === 'ArrowRight') {
    e.preventDefault()
    keyboardResize('narrower') // 向右 = 面板收窄
  }
}

// ---------------------------------------------------------------------------
// Focus Trap（drawer/fullscreen 模式）
// ---------------------------------------------------------------------------

function trapFocus(e: KeyboardEvent) {
  const panel = panelRef.value
  if (!panel) return

  const focusable = panel.querySelectorAll<HTMLElement>(
    'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])',
  )
  if (focusable.length === 0) return

  const first = focusable[0]
  const last = focusable[focusable.length - 1]

  if (e.shiftKey) {
    // Shift+Tab 从第一个元素跳到最后一个
    if (document.activeElement === first) {
      e.preventDefault()
      last.focus()
    }
  } else {
    // Tab 从最后一个元素跳到第一个
    if (document.activeElement === last) {
      e.preventDefault()
      first.focus()
    }
  }
}

// ---------------------------------------------------------------------------
// 其他
// ---------------------------------------------------------------------------

/**
 * 在独立窗口打开 AI 助手（路由 '/ai-chat'，见 router/index.ts）。
 *
 * 传**原始 route 值**而不是 `aiHost` 的派生结果：新窗口用同一个 `buildAmbientHost`
 * 自行推导宿主，宿主口径只有一处实现。不带参数会让新窗口无条件退回全局知识模式，
 * 丢掉用户当前正在看的项目/底稿上下文。
 */
function openInNewWindow() {
  const params = new URLSearchParams()
  const projectId = route.params.projectId ?? route.query.project_id
  const wpId = route.params.wpId ?? route.query.wp_id
  if (typeof projectId === 'string' && projectId) params.set('project_id', projectId)
  if (typeof wpId === 'string' && wpId) params.set('wp_id', wpId)
  const query = params.toString()
  window.open(`/ai-chat${query ? `?${query}` : ''}`, '_blank', 'width=1200,height=800')
}
</script>

<style scoped>
/* ══════════════════════════════════════════════════════════════════════════════
   DshPanel — 三档响应式布局
   ══════════════════════════════════════════════════════════════════════════════ */

.dsh-panel {
  position: relative;
  display: flex;
  flex-shrink: 0;
  height: 100%;
  z-index: 10;
}

/* ── 折叠态触发按钮 ── */
.dsh-panel-trigger {
  position: absolute;
  right: 0;
  top: 50%;
  transform: translateY(-50%);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  padding: 12px 6px;
  background: var(--el-color-primary, #4b2d77);
  color: #fff;
  border: none;
  border-radius: 8px 0 0 8px;
  cursor: pointer;
  box-shadow: -2px 0 8px rgba(0, 0, 0, 0.1);
  transition: padding 0.2s, background 0.2s;
  writing-mode: vertical-rl;
  user-select: none;
  font-family: inherit;
}

.dsh-panel-trigger:hover,
.dsh-panel-trigger:focus-visible {
  padding: 12px 10px;
  background: var(--el-color-primary-dark-2, #3d2460);
}

.dsh-panel-trigger-icon {
  display: flex;
}

.dsh-panel-trigger-text {
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 2px;
}

/* ── 遮罩层（drawer/fullscreen） ── */
.dsh-panel-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.3);
  z-index: 1000;
}

/* ── 面板容器 ── */
.dsh-panel-container {
  display: flex;
  height: 100%;
  background: var(--el-bg-color, #fff);
  border-left: 1px solid var(--el-border-color-lighter, #e4e7ed);
  outline: none;
}

/* Column 模式：嵌入布局流 */
.dsh-panel-container--column {
  position: relative;
  min-width: 320px;
  max-width: 800px;
}

/* Drawer 模式：fixed 从右侧 */
.dsh-panel-container--drawer {
  position: fixed;
  right: 0;
  top: 0;
  height: 100vh;
  height: 100dvh; /* dynamic viewport height */
  min-width: 320px;
  max-width: 800px;
  box-shadow: -4px 0 16px rgba(0, 0, 0, 0.15);
  z-index: 1001;
}

/* Fullscreen 模式：全屏覆盖 + safe-area */
.dsh-panel-container--fullscreen {
  position: fixed;
  inset: 0;
  width: 100% !important;
  height: 100vh;
  height: 100dvh;
  padding-top: env(safe-area-inset-top, 0);
  padding-bottom: env(safe-area-inset-bottom, 0);
  padding-left: env(safe-area-inset-left, 0);
  padding-right: env(safe-area-inset-right, 0);
  border-left: none;
  z-index: 1001;
}

/* ── 拖拽分隔线（语义 separator button） ── */
.dsh-panel-resizer {
  width: 6px;
  min-width: 6px;
  cursor: col-resize;
  background: transparent;
  border: none;
  padding: 0;
  transition: background 0.15s;
  flex-shrink: 0;
  touch-action: none; /* 阻止触摸滚动以支持拖拽 */
}

.dsh-panel-resizer:hover,
.dsh-panel-resizer:active {
  background: var(--el-color-primary-light-7, #c6b3e3);
}

.dsh-panel-resizer:focus-visible {
  background: var(--el-color-primary-light-5, #a88dd4);
  outline: 2px solid var(--gt-color-focus, #A06DFF);
  outline-offset: -2px;
}

/* ── 面板主体 ── */
.dsh-panel-body {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow: hidden;
}

.dsh-panel-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #e4e7ed);
  background: var(--el-fill-color-lighter, #f5f7fa);
  flex-shrink: 0;
}

.dsh-panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary, #303133);
}

.dsh-panel-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-left: auto;
}

/* ── Action buttons（语义 button 样式） ── */
.dsh-panel-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: none;
  border-radius: var(--el-border-radius-small, 4px);
  background: transparent;
  color: var(--el-text-color-secondary, #909399);
  cursor: pointer;
  transition: color 0.2s, background 0.2s;
}

.dsh-panel-action:hover {
  color: var(--el-color-primary, #4b2d77);
  background: var(--el-fill-color, #f0f2f5);
}

.dsh-panel-action:focus-visible {
  color: var(--el-color-primary, #4b2d77);
}

.dsh-panel-content {
  flex: 1;
  overflow: hidden;
  min-height: 0;
}

/* ══════════════════════════════════════════════════════════════════════════════
   过渡动画
   ══════════════════════════════════════════════════════════════════════════════ */

/* 遮罩淡入淡出 */
.dsh-backdrop-enter-active,
.dsh-backdrop-leave-active {
  transition: opacity 0.2s ease;
}

.dsh-backdrop-enter-from,
.dsh-backdrop-leave-to {
  opacity: 0;
}

/* 面板滑入滑出 */
.dsh-slide-enter-active,
.dsh-slide-leave-active {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}

.dsh-slide-enter-from,
.dsh-slide-leave-to {
  transform: translateX(100%);
}

/* Column 模式无滑动动画（直接出现） */
.dsh-panel--column .dsh-slide-enter-active,
.dsh-panel--column .dsh-slide-leave-active {
  transition: none;
}

.dsh-panel--column .dsh-slide-enter-from,
.dsh-panel--column .dsh-slide-leave-to {
  transform: none;
}

/* ══════════════════════════════════════════════════════════════════════════════
   prefers-reduced-motion：禁用滑动过渡
   ══════════════════════════════════════════════════════════════════════════════ */

@media (prefers-reduced-motion: reduce) {
  .dsh-backdrop-enter-active,
  .dsh-backdrop-leave-active,
  .dsh-slide-enter-active,
  .dsh-slide-leave-active {
    transition: none !important;
  }

  .dsh-panel-trigger {
    transition: none;
  }

  .dsh-panel-resizer {
    transition: none;
  }

  .dsh-panel-action {
    transition: none;
  }
}
</style>
