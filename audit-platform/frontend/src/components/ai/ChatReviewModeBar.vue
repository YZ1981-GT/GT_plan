<template>
  <div
    class="chat-review-mode-bar"
    :class="{
      'chat-review-mode-bar--active': isActive,
      'chat-review-mode-bar--disabled': !canEnable,
      'chat-review-mode-bar--base': isBase,
    }"
    role="region"
    aria-label="复核模式"
  >
    <!-- 切换区 -->
    <div class="chat-review-mode-bar__toggle">
      <el-switch
        v-model="reviewEnabled"
        :disabled="!canEnable"
        size="small"
        active-text="复核模式"
        aria-label="启用或关闭复核模式"
        @change="handleToggle"
      />
      <span v-if="!canEnable" class="chat-review-mode-bar__reason">
        {{ disabledReason }}
      </span>
      <span v-else-if="isBase" class="chat-review-mode-bar__base-hint">
        当前使用通用复核模板
      </span>
    </div>

    <!-- 复核预览详情（激活且加载完成时展开） -->
    <transition name="review-detail">
      <div
        v-if="isActive && preview"
        class="chat-review-mode-bar__detail"
      >
        <!-- source_level + version -->
        <div class="chat-review-mode-bar__meta">
          <el-tag size="small" :type="sourceLevelTagType" effect="plain">
            {{ sourceLevelLabel }}
          </el-tag>
          <span v-if="preview.version" class="chat-review-mode-bar__version">
            v{{ preview.version }}
          </span>
        </div>

        <!-- tips -->
        <details v-if="preview.tips && preview.tips.length > 0" class="chat-review-mode-bar__section">
          <summary class="chat-review-mode-bar__section-title">
            复核提示 ({{ preview.tips.length }})
          </summary>
          <ul class="chat-review-mode-bar__list">
            <li v-for="(tip, idx) in preview.tips" :key="idx">{{ tip }}</li>
          </ul>
        </details>

        <!-- checklist -->
        <details v-if="preview.checklist && preview.checklist.length > 0" class="chat-review-mode-bar__section">
          <summary class="chat-review-mode-bar__section-title">
            检查要点 ({{ preview.checklist.length }})
          </summary>
          <ul class="chat-review-mode-bar__list">
            <li v-for="(item, idx) in preview.checklist" :key="idx">{{ item }}</li>
          </ul>
        </details>

        <!-- risk_areas -->
        <details v-if="preview.risk_areas && preview.risk_areas.length > 0" class="chat-review-mode-bar__section">
          <summary class="chat-review-mode-bar__section-title">
            风险领域 ({{ preview.risk_areas.length }})
          </summary>
          <ul class="chat-review-mode-bar__list chat-review-mode-bar__list--risk">
            <li v-for="(area, idx) in preview.risk_areas" :key="idx">
              <el-tag
                :type="riskLevelType(area.level)"
                size="small"
                effect="light"
                class="chat-review-mode-bar__risk-tag"
              >
                {{ area.level }}
              </el-tag>
              <span>{{ area.text }}</span>
            </li>
          </ul>
        </details>
      </div>
    </transition>

    <!-- 加载状态 -->
    <div
      v-if="isActive && loadingPreview"
      class="chat-review-mode-bar__loading"
      aria-live="polite"
    >
      <el-icon class="is-loading" aria-hidden="true"><Loading /></el-icon>
      <span>加载复核配置...</span>
    </div>

    <!-- 加载失败 -->
    <div
      v-if="isActive && loadError"
      class="chat-review-mode-bar__error"
      role="alert"
    >
      <span>{{ loadError }}</span>
      <el-button size="small" text type="primary" @click="fetchPreview">
        重试
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ChatReviewModeBar — 复核模式条
 *
 * 按 host capability 显示/禁用并提供中文原因。
 * 展示 source_level / tips / checklist / risk_areas / version。
 * base 时明确"当前使用通用复核模板"。
 * 模式从 server session 恢复，不写 localStorage。
 *
 * Feature: dsh-agent-panel-integration / Task 21
 * Validates: Requirements 9.1, 9.4, 9.5
 * Properties: 23, 24
 */
import { ref, computed, watch } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { useAuthStore } from '@/stores/auth'
import type { AiHostRequest, AiHostRef } from '@/composables/useAiHostContext'

// ---------------------------------------------------------------------------
// Types（mirror backend ReviewPromptPreviewResponse）
// ---------------------------------------------------------------------------

export interface ReviewPromptPreview {
  enabled: boolean
  source_level: string
  tips: string[]
  checklist: string[]
  risk_areas: Array<{ level: string; text: string }>
  version: string
  wp_code: string
  sheet_name: string
}

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  /** 宿主上下文请求 */
  host: AiHostRequest
  /** 当前 sheet 名（底稿内部可指定 sheet） */
  sheetName?: string
  /** 是否从 server session 恢复的复核模式初始值 */
  initialReviewMode?: boolean
}>()

const emit = defineEmits<{
  /** 复核模式切换时通知父组件 */
  'update:reviewMode': [enabled: boolean]
}>()

// ---------------------------------------------------------------------------
// State
// ---------------------------------------------------------------------------

const reviewEnabled = ref(props.initialReviewMode ?? false)
const preview = ref<ReviewPromptPreview | null>(null)
const loadingPreview = ref(false)
const loadError = ref<string | null>(null)

// ---------------------------------------------------------------------------
// Computed: Capability gating（Req 9.1）
// ---------------------------------------------------------------------------

/**
 * 复核模式仅在 HostContext 为 workpaper 且宿主可用时可启用。
 * Property 23: 复核模式只在已授权 workpaper HostContext 可用。
 */
const canEnable = computed<boolean>(() => {
  if (!props.host.available || !props.host.host) return false
  return props.host.host.type === 'workpaper'
})

/** 不可用时的中文原因（Req 9.1, Property 24） */
const disabledReason = computed<string>(() => {
  if (!props.host.available) {
    return props.host.unavailableReason ?? '当前页面不可用'
  }
  if (!props.host.host) {
    return '当前页面无法解析文档上下文'
  }
  const hostType = props.host.host.type
  switch (hostType) {
    case 'note':
      return '仅在底稿页面可用，当前为附注编辑'
    case 'report':
      return '仅在底稿页面可用，当前为报表视图'
    case 'knowledge_doc':
    case 'knowledge_folder':
      return '仅在底稿页面可用，当前为知识库'
    case 'global_knowledge':
      return '仅在底稿页面可用，当前为全局知识模式'
    default:
      return '仅在底稿页面可用'
  }
})

/** 是否使用 base 通用模板（Req 9.4） */
const isBase = computed<boolean>(() => {
  return reviewEnabled.value && !!preview.value && preview.value.source_level === 'base'
})

/** 复核模式实际激活状态 */
const isActive = computed<boolean>(() => {
  return reviewEnabled.value && canEnable.value
})

/** source_level 中文标签 */
const sourceLevelLabel = computed<string>(() => {
  if (!preview.value) return ''
  switch (preview.value.source_level) {
    case 'sheet':
      return 'Sheet 级'
    case 'subject':
      return '科目级'
    case 'base':
      return '通用模板'
    default:
      return preview.value.source_level
  }
})

/** source_level tag 类型 */
const sourceLevelTagType = computed<'' | 'success' | 'info' | 'warning'>(() => {
  if (!preview.value) return 'info'
  switch (preview.value.source_level) {
    case 'sheet':
      return 'success'
    case 'subject':
      return ''
    case 'base':
      return 'warning'
    default:
      return 'info'
  }
})

// ---------------------------------------------------------------------------
// API: Fetch review prompt preview
// ---------------------------------------------------------------------------

function getToken(): string {
  try {
    const authStore = useAuthStore()
    return authStore.token || ''
  } catch {
    return ''
  }
}

async function fetchPreview(): Promise<void> {
  const host = props.host.host
  if (!host || host.type !== 'workpaper') return

  loadingPreview.value = true
  loadError.value = null

  try {
    const params = new URLSearchParams({
      host_type: host.type,
      host_id: host.id || '',
    })
    if (host.projectId) params.set('project_id', host.projectId)
    if (host.year) params.set('year', String(host.year))
    if (props.sheetName) params.set('sheet_name', props.sheetName)

    const res = await fetch(`/api/ai-chat/review-prompt?${params.toString()}`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })

    if (!res.ok) {
      const body = await res.json().catch(() => ({}))
      const detail = body?.detail
      const message = typeof detail === 'object' ? detail?.message : detail
      loadError.value = message || `加载失败 (${res.status})`
      preview.value = null
      return
    }

    const body = await res.json()
    const data = body?.data ?? body
    preview.value = data as ReviewPromptPreview
  } catch (e: any) {
    loadError.value = '网络异常，无法加载复核配置'
    preview.value = null
  } finally {
    loadingPreview.value = false
  }
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

function handleToggle(val: boolean | string | number) {
  const enabled = Boolean(val)
  reviewEnabled.value = enabled
  emit('update:reviewMode', enabled)

  if (enabled && canEnable.value) {
    fetchPreview()
  } else {
    preview.value = null
    loadError.value = null
  }
}

// ---------------------------------------------------------------------------
// Watchers
// ---------------------------------------------------------------------------

// 当宿主变化时（切换底稿）重置并重新加载
watch(
  () => props.host.host?.id,
  () => {
    if (reviewEnabled.value && canEnable.value) {
      fetchPreview()
    } else {
      preview.value = null
    }
  },
)

// 当 sheet 变化时重新加载
watch(
  () => props.sheetName,
  () => {
    if (reviewEnabled.value && canEnable.value) {
      fetchPreview()
    }
  },
)

// 从 server session 恢复时自动加载预览
watch(
  () => props.initialReviewMode,
  (val) => {
    if (val && !reviewEnabled.value) {
      reviewEnabled.value = true
      emit('update:reviewMode', true)
      if (canEnable.value) fetchPreview()
    }
  },
)

// 不可用时自动关闭（切换页面使得宿主不再是 workpaper）
watch(canEnable, (val) => {
  if (!val && reviewEnabled.value) {
    reviewEnabled.value = false
    emit('update:reviewMode', false)
    preview.value = null
    loadError.value = null
  }
})

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function riskLevelType(level: string): '' | 'danger' | 'warning' | 'info' {
  switch (level?.toLowerCase()) {
    case 'high':
    case '高':
      return 'danger'
    case 'medium':
    case '中':
      return 'warning'
    case 'low':
    case '低':
      return 'info'
    default:
      return ''
  }
}
</script>

<style scoped>
.chat-review-mode-bar {
  padding: 6px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter, #e4e7ed);
  background: var(--el-bg-color, #fff);
  font-size: 12px;
  flex-shrink: 0;
  transition: background-color 0.2s;
}

.chat-review-mode-bar--active {
  background: var(--el-color-primary-light-9, #ecf5ff);
  border-bottom-color: var(--el-color-primary-light-7, #c6e2ff);
}

.chat-review-mode-bar--disabled {
  opacity: 0.85;
}

.chat-review-mode-bar--base.chat-review-mode-bar--active {
  background: var(--el-color-warning-light-9, #fdf6ec);
  border-bottom-color: var(--el-color-warning-light-7, #faecd8);
}

/* Toggle row */
.chat-review-mode-bar__toggle {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 24px;
}

.chat-review-mode-bar__reason {
  color: var(--el-text-color-secondary, #909399);
  font-size: 11px;
}

.chat-review-mode-bar__base-hint {
  color: var(--el-color-warning-dark-2, #a77730);
  font-size: 11px;
  font-weight: 500;
}

/* Detail section */
.chat-review-mode-bar__detail {
  margin-top: 6px;
  padding-top: 6px;
  border-top: 1px dashed var(--el-border-color-extra-light, #f2f6fc);
}

.chat-review-mode-bar__meta {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 4px;
}

.chat-review-mode-bar__version {
  color: var(--el-text-color-secondary, #909399);
  font-size: 11px;
}

/* Sections (details/summary) */
.chat-review-mode-bar__section {
  margin-top: 4px;
}

.chat-review-mode-bar__section-title {
  cursor: pointer;
  color: var(--el-text-color-regular, #606266);
  font-size: 11px;
  font-weight: 500;
  user-select: none;
  padding: 2px 0;
}

.chat-review-mode-bar__section-title:hover {
  color: var(--el-color-primary, #409eff);
}

.chat-review-mode-bar__list {
  margin: 2px 0 4px 16px;
  padding: 0;
  font-size: 11px;
  color: var(--el-text-color-regular, #606266);
  line-height: 1.6;
}

.chat-review-mode-bar__list li {
  margin-bottom: 2px;
}

.chat-review-mode-bar__list--risk li {
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.chat-review-mode-bar__risk-tag {
  flex-shrink: 0;
  margin-top: 2px;
}

/* Loading */
.chat-review-mode-bar__loading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  color: var(--el-text-color-secondary, #909399);
  font-size: 11px;
}

/* Error */
.chat-review-mode-bar__error {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  color: var(--el-color-danger, #f56c6c);
  font-size: 11px;
}

/* Transition */
.review-detail-enter-active,
.review-detail-leave-active {
  transition: all 0.2s ease;
}

.review-detail-enter-from,
.review-detail-leave-to {
  opacity: 0;
  max-height: 0;
  overflow: hidden;
}

.review-detail-enter-to,
.review-detail-leave-from {
  opacity: 1;
  max-height: 400px;
}

/* reduced-motion */
@media (prefers-reduced-motion: reduce) {
  .review-detail-enter-active,
  .review-detail-leave-active {
    transition: none;
  }
  .chat-review-mode-bar {
    transition: none;
  }
}
</style>
