<script setup lang="ts">
/**
 * GtChecklistNav — 核对表左侧目录导航（展示型子组件）
 *
 * 从 GtChecklistTable.vue 抽出（spec workpaper-frontend-large-component-split, Req 2）：
 * 左侧「目录导航」整块展示 DOM 与样式。markup/class 逐字不变。
 *
 * 铁律：行为零变更；props 下行（navItems + activeSection）、emit 上行（select）；主组件 wiring 不变。
 */

interface NavItem {
  id: string
  title: string
  applicable: boolean
  progress: { filled: number; total: number }
  completed: boolean
}

defineProps<{
  navItems: NavItem[]
  activeSection: string
}>()

const emit = defineEmits<{
  (e: 'select', sectionId: string): void
}>()
</script>

<template>
  <!-- 左侧目录导航 -->
  <div class="gt-checklist-table__nav">
    <div class="gt-checklist-table__nav-title">目录导航</div>
    <div class="gt-checklist-table__nav-list">
      <div
        v-for="item in navItems"
        :key="item.id"
        class="gt-checklist-table__nav-item"
        :class="{
          'is-active': activeSection === item.id,
          'is-completed': item.completed,
          'is-inapplicable': !item.applicable,
        }"
        @click="emit('select', item.id)"
      >
        <span class="nav-item__title">{{ item.title }}</span>
        <span v-if="item.completed" class="nav-item__check">✓</span>
        <span v-else-if="item.progress.total > 0" class="nav-item__count">
          {{ item.progress.filled }}/{{ item.progress.total }}
        </span>
        <span v-if="!item.applicable" class="nav-item__na">不适用</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* ─── Nav sidebar ─── */
.gt-checklist-table__nav {
  width: 260px;
  min-width: 260px;
  border-right: 1px solid var(--gt-color-border);
  display: flex;
  flex-direction: column;
  background: var(--gt-color-bg-elevated);
}

.gt-checklist-table__nav-title {
  padding: 12px 16px;
  font-weight: 600;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-secondary);
  border-bottom: 1px solid var(--gt-color-border-light);
}

.gt-checklist-table__nav-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}

.gt-checklist-table__nav-item {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  cursor: pointer;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text);
  transition: background var(--gt-transition-fast);
  gap: 6px;
}

.gt-checklist-table__nav-item:hover {
  background: var(--gt-color-primary-bg);
}

.gt-checklist-table__nav-item.is-active {
  background: var(--gt-color-primary-bg);
  border-left: 3px solid var(--gt-color-primary);
  font-weight: 500;
}

.gt-checklist-table__nav-item.is-completed .nav-item__title {
  color: var(--gt-color-success);
}

.gt-checklist-table__nav-item.is-inapplicable {
  opacity: 0.5;
}

.nav-item__title {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.nav-item__check {
  color: var(--gt-color-success);
  font-weight: 700;
}

.nav-item__count {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}

.nav-item__na {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
  background: var(--gt-color-border-light);
  padding: 1px 4px;
  border-radius: var(--gt-radius-xs);
}
</style>
