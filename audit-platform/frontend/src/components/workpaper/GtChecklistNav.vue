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
  /** A17-5: 审计目标→程序筛选（当前选中的目标编号） */
  activeObjective?: number | null
  /** A17-5: 是否显示目标筛选 */
  showObjectives?: boolean
}>()

const emit = defineEmits<{
  (e: 'select', sectionId: string): void
  (e: 'select-objective', objIdx: number | null): void
}>()
</script>

<template>
  <!-- 左侧目录导航 -->
  <div class="gt-checklist-table__nav">
    <div class="gt-checklist-table__nav-title">目录导航</div>
    <div class="gt-checklist-table__nav-list">
      <template v-for="item in navItems" :key="item.id">
        <!-- 审计目标 section → 可点击进入目标追溯面板 + 目标筛选tag -->
        <div
          v-if="item.title.includes('审计目标')"
          class="gt-checklist-table__nav-item is-objective-header"
          :class="{ 'is-active': activeSection === item.id }"
          @click="emit('select', item.id)"
        >
          <span class="nav-item__icon">🎯</span>
          <span class="nav-item__title">{{ item.title }}</span>
        </div>
        <div v-if="item.title.includes('审计目标') && showObjectives" class="nav-objectives">
          <span
            v-for="idx in 6"
            :key="idx"
            class="nav-obj-tag"
            :class="{ 'is-active': activeObjective === idx }"
            @click="emit('select-objective', activeObjective === idx ? null : idx)"
          >{{ idx }}</span>
        </div>
        <!-- 普通导航项 -->
        <div
          v-else-if="!item.title.includes('审计目标')"
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
      </template>
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

.gt-checklist-table__nav-item.is-header {
  cursor: default;
  font-weight: 600;
  font-size: 12px;
  color: var(--gt-color-text-tertiary);
  padding: 6px 16px;
  border-bottom: 1px solid var(--gt-color-border-light);
}
.gt-checklist-table__nav-item.is-header:hover {
  background: transparent;
}

/* 审计目标导航项（可点击） */
.gt-checklist-table__nav-item.is-objective-header {
  font-weight: 600;
  font-size: 13px;
  color: var(--gt-color-primary, #409eff);
  padding: 8px 16px;
  border-bottom: 1px solid var(--gt-color-border-light);
  cursor: pointer;
}
.gt-checklist-table__nav-item.is-objective-header:hover {
  background: var(--gt-color-primary-bg, #ecf5ff);
}
.gt-checklist-table__nav-item.is-objective-header.is-active {
  background: var(--gt-color-primary-bg, #ecf5ff);
  border-left: 3px solid var(--gt-color-primary, #409eff);
}

.nav-item__icon {
  margin-right: 4px;
  flex-shrink: 0;
}

/* 目标筛选tag */
.nav-objectives {
  display: flex;
  gap: 4px;
  padding: 4px 16px 8px;
  flex-wrap: wrap;
}
.nav-obj-tag {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  background: var(--gt-color-border-light, #e4e7ed);
  color: var(--gt-color-text-secondary, #606266);
  transition: all 0.15s;
}
.nav-obj-tag:hover {
  background: var(--gt-color-primary-bg, #ecf5ff);
  color: var(--gt-color-primary, #409eff);
}
.nav-obj-tag.is-active {
  background: var(--gt-color-primary, #409eff);
  color: #fff;
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
