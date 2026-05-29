<!--
  AiContentBadge — AI 待确认计数小红点徽章（spec global-refinement-v3 Task 6.5）
  =========================================================================
  用于底稿列表 / 5 视图状态列：
    - count > 0：显示带数字徽章 + 紫色 🤖 待确认 标签
    - count = 0：不渲染（避免空徽章占位）

  特点：
    - 复用 el-badge 标准展示（max=99，超过显示 99+）
    - 颜色与 AiContentTag.vue 保持一致（紫色品牌色）
    - 支持点击触发 click 事件，父组件可弹出明细面板

  用法：
    <AiContentBadge :count="row.ai_pending_count ?? 0" @click="showDetails(row)" />

  Props:
    count: number  必需，pending 数量；为 0 / 负数 时不渲染
    label?: string  可选标签文本，默认 "AI 待确认"
    clickable?: boolean  可选，true 时显示 cursor pointer + emit click 事件

  Emits:
    (e: 'click'): void  仅 clickable=true 时触发
-->
<template>
  <el-badge
    v-if="visibleCount > 0"
    :value="visibleCount"
    :max="99"
    type="warning"
    class="gt-ai-badge"
    :class="{ 'gt-ai-badge--clickable': clickable }"
    @click="onClick"
  >
    <span class="gt-ai-badge__tag">
      <span class="gt-ai-badge__icon">🤖</span>
      <span class="gt-ai-badge__text">{{ label || 'AI 待确认' }}</span>
    </span>
  </el-badge>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  count: number | null | undefined
  label?: string
  clickable?: boolean
}>()

const emit = defineEmits<{
  (e: 'click'): void
}>()

const visibleCount = computed(() => {
  const n = Number(props.count ?? 0)
  return Number.isFinite(n) && n > 0 ? Math.floor(n) : 0
})

function onClick() {
  if (props.clickable) {
    emit('click')
  }
}
</script>

<style scoped>
.gt-ai-badge {
  display: inline-flex;
  align-items: center;
}

.gt-ai-badge__tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  font-size: 12px;
  line-height: 1.4;
  color: var(--gt-color-primary, #6b3fa0);
  background: var(--gt-color-primary-bg, rgba(107, 63, 160, 0.08));
  border: 1px dashed var(--gt-color-primary, #6b3fa0);
  border-radius: 10px;
  user-select: none;
}

.gt-ai-badge__icon {
  font-size: 12px;
  line-height: 1;
}

.gt-ai-badge--clickable {
  cursor: pointer;
}

.gt-ai-badge--clickable:hover .gt-ai-badge__tag {
  background: var(--gt-color-primary-bg-hover, rgba(107, 63, 160, 0.16));
}
</style>
