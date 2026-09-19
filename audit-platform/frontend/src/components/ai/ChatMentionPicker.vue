<template>
  <div
    v-show="pickerOpen"
    ref="pickerRef"
    class="chat-mention-picker"
    role="combobox"
    aria-haspopup="listbox"
    :aria-expanded="pickerOpen"
    aria-label="引用资源选择器"
  >
    <!-- 搜索输入 -->
    <div class="chat-mention-picker__search">
      <el-input
        ref="searchInputRef"
        v-model="searchQuery"
        size="small"
        placeholder="搜索底稿、附注、报表、知识库..."
        clearable
        :prefix-icon="Search"
        aria-label="搜索引用资源"
        :aria-activedescendant="activeDescendant"
        aria-autocomplete="list"
        aria-controls="mention-listbox"
        @keydown="handleKeydown"
      />
    </div>

    <!-- 类型过滤器标签 -->
    <div class="chat-mention-picker__filters" role="toolbar" aria-label="类型过滤">
      <el-tag
        :type="typeFilter === null ? 'primary' : 'info'"
        size="small"
        :effect="typeFilter === null ? 'dark' : 'plain'"
        class="chat-mention-picker__filter-tag"
        role="button"
        tabindex="0"
        aria-pressed="true"
        @click="setTypeFilter(null)"
        @keydown.enter="setTypeFilter(null)"
        @keydown.space.prevent="setTypeFilter(null)"
      >
        全部
      </el-tag>
      <el-tooltip
        v-for="ft in availableFilters"
        :key="ft.value"
        :content="ft.hint"
        :disabled="!ft.disabled"
        placement="top"
      >
        <el-tag
          :type="typeFilter === ft.value ? 'primary' : 'info'"
          size="small"
          :effect="typeFilter === ft.value ? 'dark' : 'plain'"
          class="chat-mention-picker__filter-tag"
          :class="{ 'is-disabled': ft.disabled }"
          role="button"
          :tabindex="ft.disabled ? -1 : 0"
          :aria-pressed="String(typeFilter === ft.value)"
          :aria-disabled="String(ft.disabled)"
          :data-testid="`mention-filter-${ft.value}`"
          @click="handleFilterClick(ft)"
          @keydown.enter="handleFilterClick(ft)"
          @keydown.space.prevent="handleFilterClick(ft)"
        >
          {{ ft.label }}
        </el-tag>
      </el-tooltip>
    </div>

    <!--
      部分类型失败的降级提示（Property 13）：搜到了一些结果，但某几类没搜成。
      与下方 error / unavailable 空态互补 —— 有结果时那些分支不渲染，
      若没有这一条，单类失败就会被完全吞掉（历史缺陷）。
    -->
    <div
      v-if="degradedHint && items.length > 0"
      class="chat-mention-picker__status chat-mention-picker__status--degraded"
      role="status"
      aria-live="polite"
      data-testid="mention-degraded-state"
    >
      <el-icon aria-hidden="true"><WarningFilled /></el-icon>
      <span>{{ degradedHint }}</span>
    </div>

    <!-- 搜索状态：加载中 -->
    <div
      v-if="isLoading"
      class="chat-mention-picker__status chat-mention-picker__status--loading"
      role="status"
      aria-live="polite"
    >
      <el-icon class="is-loading" aria-hidden="true"><Loading /></el-icon>
      <span>正在搜索...</span>
    </div>

    <!-- 搜索状态：错误（Property 13 — 与 empty 使用不同 DOM + 文案） -->
    <div
      v-else-if="isError"
      class="chat-mention-picker__status chat-mention-picker__status--error"
      role="alert"
      aria-live="assertive"
      data-testid="mention-error-state"
    >
      <el-icon aria-hidden="true"><WarningFilled /></el-icon>
      <span>{{ errorMessage }}</span>
    </div>

    <!-- 搜索状态：服务不可用（Property 13 — 能力不可用独立文案） -->
    <div
      v-else-if="isUnavailable"
      class="chat-mention-picker__status chat-mention-picker__status--unavailable"
      role="alert"
      aria-live="assertive"
      data-testid="mention-unavailable-state"
    >
      <el-icon aria-hidden="true"><CircleClose /></el-icon>
      <span>{{ errorMessage || '引用搜索能力暂不可用' }}</span>
    </div>

    <!-- 搜索状态：无结果（Property 13 — 成功但空，不同于 error） -->
    <div
      v-else-if="isEmpty"
      class="chat-mention-picker__status chat-mention-picker__status--empty"
      role="status"
      aria-live="polite"
      data-testid="mention-empty-state"
    >
      <span>{{ emptyReason }}</span>
    </div>

    <!-- 搜索结果列表 -->
    <ul
      v-else-if="items.length > 0"
      id="mention-listbox"
      class="chat-mention-picker__list"
      role="listbox"
      aria-label="引用资源候选列表"
      aria-multiselectable="true"
    >
      <li
        v-for="(item, idx) in items"
        :id="`mention-option-${idx}`"
        :key="`${item.type}:${item.id}`"
        class="chat-mention-picker__item"
        :class="{
          'is-active': activeIndex === idx,
          'is-selected': isSelected(item),
        }"
        role="option"
        :aria-selected="isSelected(item)"
        @click="handleSelect(item)"
        @mouseenter="activeIndex = idx"
      >
        <span class="chat-mention-picker__item-type" aria-hidden="true">
          {{ getTypeLabel(item.type) }}
        </span>
        <span class="chat-mention-picker__item-label">{{ item.label }}</span>
        <span v-if="item.sublabel" class="chat-mention-picker__item-sublabel">
          {{ item.sublabel }}
        </span>
        <el-icon
          v-if="isSelected(item)"
          class="chat-mention-picker__item-check"
          aria-hidden="true"
        >
          <Check />
        </el-icon>
      </li>
    </ul>

    <!-- 初始状态提示 -->
    <div
      v-else-if="searchStatus === 'idle'"
      class="chat-mention-picker__status chat-mention-picker__status--idle"
      role="status"
    >
      <span>输入关键词搜索可引用的资源</span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ChatMentionPicker — AI 面板 mention 选择器
 *
 * @-触发 → 搜索 → 多选 → tag 展示。
 * a11y：combobox / listbox 语义、键盘导航（↑↓/Enter/Escape）、focus trap。
 *
 * Feature: dsh-agent-panel-integration / Task 15
 * Validates: Requirements 5.1, 5.4
 * Properties: 12, 13
 */
import { ref, computed, watch, nextTick } from 'vue'
import { Search, Loading, WarningFilled, CircleClose, Check } from '@element-plus/icons-vue'
import {
  useAiMention,
  MENTION_TYPE_LABELS,
  PROJECT_REQUIRED_MENTION_TYPES,
  type MentionItem,
  type MentionType,
  type UseAiMentionOptions,
} from '@/composables/useAiMention'
import type { AiHostRef } from '@/composables/useAiHostContext'
import type { Ref } from 'vue'

// ---------------------------------------------------------------------------
// Props & Emits
// ---------------------------------------------------------------------------

const props = defineProps<{
  /** 当前宿主 HostRef */
  host: AiHostRef | null
  /** 面板是否打开（外部控制） */
  open: boolean
}>()

const emit = defineEmits<{
  /** 关闭选择器 */
  close: []
  /** 选择变更（传出最新已选列表） */
  change: [selected: MentionItem[]]
}>()

// ---------------------------------------------------------------------------
// Composable
// ---------------------------------------------------------------------------

const hostRef = computed(() => props.host) as Ref<AiHostRef | null>

const mentionOptions: UseAiMentionOptions = {
  host: hostRef,
  debounceMs: 300,
}

const {
  pickerOpen,
  searchQuery,
  typeFilter,
  items,
  searchStatus,
  errorMessage,
  selected,
  isEmpty,
  isError,
  isUnavailable,
  isLoading,
  degradedHint,
  projectBindingMissing,
  emptyReason,
  openPicker,
  closePicker,
  selectItem,
  removeItem,
  isSelected,
  setTypeFilter,
  dispose,
} = useAiMention(mentionOptions)

// ---------------------------------------------------------------------------
// Sync open prop ↔ internal state
// ---------------------------------------------------------------------------

watch(
  () => props.open,
  (val) => {
    if (val && !pickerOpen.value) {
      openPicker()
      nextTick(() => focusInput())
    } else if (!val && pickerOpen.value) {
      closePicker()
    }
  },
  { immediate: true },
)

watch(pickerOpen, (val) => {
  if (!val) emit('close')
})

// 已选变化时通知外部
watch(selected, (val) => {
  emit('change', [...val])
}, { deep: true })

// ---------------------------------------------------------------------------
// Keyboard navigation
// ---------------------------------------------------------------------------

const activeIndex = ref(-1)
const pickerRef = ref<HTMLElement | null>(null)
const searchInputRef = ref<InstanceType<any> | null>(null)

const activeDescendant = computed(() =>
  activeIndex.value >= 0 ? `mention-option-${activeIndex.value}` : undefined,
)

function handleKeydown(e: KeyboardEvent) {
  const len = items.value.length

  switch (e.key) {
    case 'ArrowDown':
      e.preventDefault()
      activeIndex.value = len > 0 ? (activeIndex.value + 1) % len : -1
      break
    case 'ArrowUp':
      e.preventDefault()
      activeIndex.value = len > 0 ? (activeIndex.value - 1 + len) % len : -1
      break
    case 'Enter':
      e.preventDefault()
      if (activeIndex.value >= 0 && activeIndex.value < len) {
        handleSelect(items.value[activeIndex.value])
      }
      break
    case 'Escape':
      e.preventDefault()
      closePicker()
      emit('close')
      break
  }
}

// Reset active index when items change
watch(items, () => {
  activeIndex.value = -1
})

// ---------------------------------------------------------------------------
// Selection
// ---------------------------------------------------------------------------

function handleSelect(item: MentionItem) {
  if (isSelected(item)) {
    removeItem(item)
  } else {
    selectItem(item)
  }
}

// ---------------------------------------------------------------------------
// Focus
// ---------------------------------------------------------------------------

function focusInput() {
  const inputEl = searchInputRef.value?.$el?.querySelector('input') as HTMLInputElement | null
  inputEl?.focus()
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * 可用的类型过滤选项。
 *
 * 无项目绑定（受限全局知识模式）时，需要项目的四类**置灰**并给出原因：
 * 此前它们可点，点完后端返回空集，界面显示"无匹配结果" ——
 * 用户会以为库里没有底稿/附注/报表，而真实原因是当前页面没有项目上下文。
 */
const availableFilters = computed(() => {
  const types: MentionType[] = [
    'workpaper', 'note', 'report', 'knowledge_doc', 'knowledge_folder', 'address',
  ]
  return types.map((t) => {
    const needsProject = PROJECT_REQUIRED_MENTION_TYPES.includes(t)
    const disabled = needsProject && projectBindingMissing.value
    return {
      value: t,
      label: MENTION_TYPE_LABELS[t],
      disabled,
      hint: disabled
        ? `${MENTION_TYPE_LABELS[t]}需要先绑定项目：请从某个项目的底稿或报表页打开 AI 对话`
        : '',
    }
  })
})

/** 点击类型 tab（置灰项不响应，避免发出注定为空的请求） */
function handleFilterClick(filter: { value: MentionType; disabled: boolean }) {
  if (filter.disabled) return
  setTypeFilter(filter.value)
}

function getTypeLabel(type: MentionType): string {
  return MENTION_TYPE_LABELS[type] ?? type
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

import { onBeforeUnmount } from 'vue'

onBeforeUnmount(() => {
  dispose()
})
</script>

<style scoped>
.chat-mention-picker {
  display: flex;
  flex-direction: column;
  max-height: 320px;
  border: 1px solid var(--el-border-color-light, #e4e7ed);
  border-radius: 6px;
  background: var(--el-bg-color, #fff);
  box-shadow: var(--el-box-shadow-light, 0 2px 12px rgba(0, 0, 0, 0.1));
  overflow: hidden;
}

.chat-mention-picker__search {
  padding: 8px;
  border-bottom: 1px solid var(--el-border-color-lighter, #ebeef5);
}

.chat-mention-picker__filters {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  padding: 6px 8px;
  border-bottom: 1px solid var(--el-border-color-extra-light, #f2f6fc);
}

.chat-mention-picker__filter-tag {
  cursor: pointer;
  user-select: none;
}

/* 无项目绑定时置灰：可见但不可点，配 tooltip 说明原因 */
.chat-mention-picker__filter-tag.is-disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.chat-mention-picker__status {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 16px 12px;
  font-size: 13px;
  color: var(--el-text-color-secondary, #909399);
  justify-content: center;
}

.chat-mention-picker__status--error {
  color: var(--el-color-danger, #f56c6c);
}

.chat-mention-picker__status--unavailable {
  color: var(--el-color-warning, #e6a23c);
}

.chat-mention-picker__status--empty {
  color: var(--el-text-color-placeholder, #a8abb2);
}

/* 降级提示：有结果但部分类型失败，用警示色但不占满高度 */
.chat-mention-picker__status--degraded {
  padding: 6px 12px;
  font-size: 12px;
  color: var(--el-color-warning-dark-2, #a77730);
  background: var(--el-color-warning-light-9, #fdf6ec);
  border-bottom: 1px solid var(--el-color-warning-light-7, #f8e3c5);
  justify-content: flex-start;
}

.chat-mention-picker__list {
  list-style: none;
  margin: 0;
  padding: 4px 0;
  overflow-y: auto;
  max-height: 200px;
}

.chat-mention-picker__item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  cursor: pointer;
  font-size: 13px;
  transition: background-color 0.15s;
}

.chat-mention-picker__item:hover,
.chat-mention-picker__item.is-active {
  background: var(--el-fill-color-light, #f2f6fc);
}

.chat-mention-picker__item.is-selected {
  background: var(--el-color-primary-light-9, #ecf5ff);
}

.chat-mention-picker__item-type {
  flex-shrink: 0;
  font-size: 11px;
  padding: 1px 6px;
  border-radius: 3px;
  background: var(--el-fill-color, #f0f2f5);
  color: var(--el-text-color-secondary, #909399);
}

.chat-mention-picker__item-label {
  font-weight: 500;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-mention-picker__item-sublabel {
  color: var(--el-text-color-placeholder, #a8abb2);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.chat-mention-picker__item-check {
  margin-left: auto;
  color: var(--el-color-primary, #409eff);
  flex-shrink: 0;
}
</style>
