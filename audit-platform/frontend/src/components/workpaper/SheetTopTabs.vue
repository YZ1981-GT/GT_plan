<!--
  SheetTopTabs.vue — Univer 底稿顶部水平 sheet 切换栏

  痛点：Univer 默认 sheet bar 在最底部，长 sheet 内容下滚到底才能切换
  设计：
    - 紧凑横向滚动条（高 32px）
    - 当前 sheet 紫色高亮 + 下边框
    - 鼠标滚轮横向滚动支持
    - 折叠左侧导航时可显示 + 不折叠时也显示
-->
<template>
  <div class="gt-stt" v-if="sheets.length">
    <div class="gt-stt__scroll" @wheel.prevent="onWheel" ref="scrollRef">
      <div
        v-for="s in sheets"
        :key="s.id"
        class="gt-stt__tab"
        :class="{ 'is-active': s.id === activeSheetId }"
        :title="s.name"
        @click="$emit('switch', s.id)"
      >
        {{ s.name }}
      </div>
    </div>
    <div class="gt-stt__count">{{ sheets.length }} sheet</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  sheets: Array<{ id: string; name: string }>
  activeSheetId: string
}>()

defineEmits<{
  switch: [id: string]
}>()

const scrollRef = ref<HTMLElement | null>(null)

function onWheel(e: WheelEvent) {
  if (scrollRef.value) {
    scrollRef.value.scrollLeft += e.deltaY
  }
}
</script>

<style scoped>
.gt-stt {
  display: flex; align-items: center; gap: 8px;
  height: 36px; padding: 0 12px;
  background: var(--gt-color-bg-white);
  border-bottom: 1px solid var(--gt-color-border-light, #f0f0f0);
  flex-shrink: 0;
}
.gt-stt__scroll {
  flex: 1; display: flex; gap: 2px; overflow-x: auto; overflow-y: hidden;
  scrollbar-width: thin; scroll-behavior: smooth;
}
.gt-stt__scroll::-webkit-scrollbar { height: 4px; }
.gt-stt__scroll::-webkit-scrollbar-thumb { background: var(--gt-color-border, #ddd); border-radius: 2px; }
.gt-stt__tab {
  flex-shrink: 0; padding: 4px 12px; font-size: 12px;
  color: var(--gt-color-text-secondary); cursor: pointer; border-radius: 4px;
  white-space: nowrap; max-width: 200px; overflow: hidden; text-overflow: ellipsis;
  transition: all 0.15s; line-height: 24px;
}
.gt-stt__tab:hover {
  background: var(--gt-color-bg, #fafafa);
  color: var(--gt-color-text-primary);
}
.gt-stt__tab.is-active {
  background: var(--gt-color-primary-bg, #f0ebff);
  color: var(--gt-color-primary);
  font-weight: 600;
  box-shadow: inset 0 -2px 0 var(--gt-color-primary);
}
.gt-stt__count {
  font-size: 11px; color: var(--gt-color-text-tertiary); flex-shrink: 0;
  padding-left: 8px; border-left: 1px solid var(--gt-color-border-light, #f0f0f0);
}
</style>
