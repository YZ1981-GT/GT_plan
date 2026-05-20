<!--
  UniverSheetNav.vue — Univer 底稿 sheet 左侧导航树

  痛点：底部 Univer 默认 sheet bar 横向滚动，23+ sheet 名称被截断难以选择
  设计：
    - 紧凑左栏（默认 200px / 折叠 32px）
    - 按 sheet 名称模式分类（审定表/明细/盘点/分析/截止测试...）
    - 类别图标 + 颜色编码 + sheet 数量徽章
    - 当前 sheet 紫色高亮 + 3px 左边框
    - 搜索框模糊匹配
-->
<template>
  <div class="gt-usn" :class="{ 'gt-usn--collapsed': collapsed }">
    <!-- 折叠/展开切换 -->
    <div class="gt-usn__head">
      <span v-if="!collapsed" class="gt-usn__title">
        Sheet <span class="gt-amt">{{ totalCount }}</span>
      </span>
      <el-button
        text
        size="small"
        :icon="collapsed ? 'ArrowRight' : 'ArrowLeft'"
        @click="$emit('toggle-collapsed')"
        class="gt-usn__toggle"
        :title="collapsed ? '展开 Sheet 导航' : '折叠'"
      >{{ collapsed ? '▶' : '◀' }}</el-button>
    </div>

    <!-- 搜索框（折叠时隐藏） -->
    <div v-if="!collapsed" class="gt-usn__search">
      <el-input
        v-model="search"
        size="small"
        placeholder="搜索 sheet"
        clearable
      />
    </div>

    <!-- 分类树 -->
    <div v-if="!collapsed" class="gt-usn__body">
      <div
        v-for="group in sortedFilteredGroups"
        :key="group.category"
        class="gt-usn__group"
      >
        <div class="gt-usn__group-head" @click="toggleGroup(group.category)">
          <span class="gt-usn__group-icon" :style="{ color: group.color }">{{ group.icon }}</span>
          <span class="gt-usn__group-label">{{ group.category }}</span>
          <span class="gt-usn__group-count">{{ group.sheets.length }}</span>
          <span class="gt-usn__group-arrow">{{ expandedGroups.has(group.category) ? '▾' : '▸' }}</span>
        </div>
        <div v-if="expandedGroups.has(group.category)" class="gt-usn__sheets">
          <div
            v-for="sheet in group.sheets"
            :key="sheet.id"
            class="gt-usn__sheet"
            :class="{
              'gt-usn__sheet--active': sheet.id === activeSheetId,
              'gt-usn__sheet--readonly': sheet.readonly,
            }"
            :title="sheet.readonly ? `${sheet.name}（只读）` : sheet.name"
            @click="$emit('switch', sheet.id)"
          >
            <span class="gt-usn__sheet-name">{{ sheet.name }}</span>
            <span v-if="sheet.readonly" class="gt-usn__sheet-badge" title="只读">🔒</span>
          </div>
        </div>
      </div>
      <div v-if="sortedFilteredGroups.length === 0" class="gt-usn__empty">
        无匹配的 sheet
      </div>
    </div>

    <!-- 折叠态：纯图标列 -->
    <div v-else class="gt-usn__body-collapsed">
      <div
        v-for="group in sortedGroups"
        :key="group.category"
        class="gt-usn__icon-only"
        :title="`${group.category} (${group.sheets.length})`"
        :style="{ color: group.color }"
        @click="$emit('toggle-collapsed')"
      >
        <span class="gt-usn__icon-emoji">{{ group.icon }}</span>
        <span class="gt-usn__icon-count">{{ group.sheets.length }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { SheetGroup } from '@/composables/useUniverSheetNav'

interface Props {
  groups: SheetGroup[]
  activeSheetId: string
  totalCount: number
  collapsed?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  collapsed: false,
})

defineEmits<{
  (e: 'switch', sheetId: string): void
  (e: 'toggle-collapsed'): void
}>()

const search = ref('')
const expandedGroups = ref(new Set<string>())

// 默认全部展开（首次或新加载时）
watch(
  () => props.groups,
  (newGroups) => {
    if (expandedGroups.value.size === 0 && newGroups.length > 0) {
      newGroups.forEach((g) => expandedGroups.value.add(g.category))
    }
  },
  { immediate: true },
)

// 自动展开包含当前 sheet 的分组
watch(
  () => props.activeSheetId,
  (newId) => {
    if (!newId) return
    const containingGroup = props.groups.find((g) => g.sheets.some((s) => s.id === newId))
    if (containingGroup && !expandedGroups.value.has(containingGroup.category)) {
      expandedGroups.value.add(containingGroup.category)
    }
  },
)

function toggleGroup(category: string) {
  if (expandedGroups.value.has(category)) {
    expandedGroups.value.delete(category)
  } else {
    expandedGroups.value.add(category)
  }
}

/**
 * task 2.7：按 priority 升序排序的 groups。
 * 当任一 group 含 priority 字段时启用排序（D 循环），否则保持原顺序（E 循环向后兼容）。
 */
const sortedGroups = computed(() => {
  const hasPriority = props.groups.some((g) => typeof g.priority === 'number')
  if (!hasPriority) return props.groups
  return [...props.groups].sort((a, b) => (a.priority ?? 999) - (b.priority ?? 999))
})

/** 排序后再做搜索过滤（template 用此 computed） */
const sortedFilteredGroups = computed(() => {
  const q = search.value.trim().toLowerCase()
  const base = sortedGroups.value
  if (!q) return base
  return base
    .map((g) => ({
      ...g,
      sheets: g.sheets.filter((s) => s.name.toLowerCase().includes(q)),
    }))
    .filter((g) => g.sheets.length > 0)
})
</script>

<style scoped>
.gt-usn {
  display: flex;
  flex-direction: column;
  width: 220px;
  min-width: 220px;
  height: 100%;
  background: var(--gt-color-bg-white);
  border-right: 1px solid var(--gt-color-border-lighter);
  overflow: hidden;
  transition: width 0.2s, min-width 0.2s;
}
.gt-usn--collapsed {
  width: 36px;
  min-width: 36px;
}

/* 头部 */
.gt-usn__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 10px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
  background: var(--gt-color-primary-bg);
  height: 32px;
  flex-shrink: 0;
}
.gt-usn__title {
  font-size: var(--gt-font-size-sm);
  font-weight: 600;
  color: var(--gt-color-primary);
}
.gt-amt {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  margin-left: 2px;
}
.gt-usn__toggle {
  padding: 0 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary);
  min-height: 20px;
}

/* 搜索 */
.gt-usn__search {
  padding: 6px 8px;
  border-bottom: 1px solid var(--gt-color-border-lighter);
}

/* 分类树 */
.gt-usn__body {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
}
.gt-usn__group {
  margin-bottom: 1px;
}
.gt-usn__group-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  cursor: pointer;
  font-size: var(--gt-font-size-xs);
  font-weight: 600;
  color: var(--gt-color-text-regular);
  user-select: none;
  transition: background 0.15s;
}
.gt-usn__group-head:hover {
  background: var(--gt-color-bg);
}
.gt-usn__group-icon {
  font-size: 14px;
  flex-shrink: 0;
}
.gt-usn__group-label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-usn__group-count {
  font-size: 11px;
  color: var(--gt-color-text-tertiary);
  background: var(--gt-color-bg);
  padding: 0 6px;
  border-radius: 8px;
  min-width: 18px;
  text-align: center;
}
.gt-usn__group-arrow {
  font-size: 10px;
  color: var(--gt-color-text-tertiary);
  width: 10px;
  text-align: center;
}

/* sheet 列表 */
.gt-usn__sheets {
  padding: 0 0 2px 0;
}
.gt-usn__sheet {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 30px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  border-left: 3px solid transparent;
  transition: background 0.15s, border-left-color 0.15s;
}
.gt-usn__sheet:hover {
  background: var(--gt-color-bg);
}
.gt-usn__sheet--active {
  background: rgba(75, 45, 119, 0.14);
  color: var(--gt-color-primary);
  font-weight: 600;
  border-left-color: var(--gt-color-primary);
}
.gt-usn__sheet--readonly {
  font-style: italic;
  color: var(--gt-color-text-tertiary);
}
.gt-usn__sheet--readonly.gt-usn__sheet--active {
  /* 只读 + 激活：保留紫色高亮，去掉斜体的弱化色 */
  color: var(--gt-color-primary);
}
.gt-usn__sheet-name {
  flex: 1;
  display: block;
  overflow: hidden;
  text-overflow: ellipsis;
}
.gt-usn__sheet-badge {
  font-size: 10px;
  margin-left: 4px;
  flex-shrink: 0;
  line-height: 1;
}

.gt-usn__empty {
  text-align: center;
  padding: 20px 10px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}

/* 折叠态 */
.gt-usn__body-collapsed {
  flex: 1;
  overflow-y: auto;
  padding: 8px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
}
.gt-usn__icon-only {
  display: flex;
  flex-direction: column;
  align-items: center;
  cursor: pointer;
  font-size: 14px;
  position: relative;
}
.gt-usn__icon-emoji {
  font-size: 16px;
}
.gt-usn__icon-count {
  font-size: 9px;
  color: var(--gt-color-text-tertiary);
  margin-top: -2px;
}
</style>
