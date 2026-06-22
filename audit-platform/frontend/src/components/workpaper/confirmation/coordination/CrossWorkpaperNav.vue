<template>
  <div v-if="confirmIndex" class="cross-workpaper-nav">
    <span class="cross-workpaper-nav__label">本笔相关底稿：</span>
    <div class="cross-workpaper-nav__items">
      <span
        v-for="item in navItems"
        :key="item.wpCode"
        class="cross-workpaper-nav__chip"
        :class="{
          'cross-workpaper-nav__chip--active': item.exists,
          'cross-workpaper-nav__chip--current': item.wpCode === currentWpCode,
          'cross-workpaper-nav__chip--disabled': !item.exists,
        }"
        :title="item.tooltip"
        @click="handleNavigate(item)"
      >
        {{ item.label }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * CrossWorkpaperNav.vue — 跨表导航条
 *
 * 选中 confirm_index 后展示"本笔函证相关底稿"横向导航：
 * D0-2 | D0-1 | D0-3 | D0-7 | D0-4 | D0-4b | D0-5/6 | D0-8
 * 按状态点亮（有数据=蓝色可点击 / 无数据=灰色）+ 跳转定位
 *
 * Sprint 3 Task 3.3
 */
import { computed } from 'vue'

export interface NavItem {
  /** 显示文字 */
  label: string
  /** 底稿编码 */
  wpCode: string
  /** 是否存在该函证的数据 */
  exists: boolean
  /** 悬停提示 */
  tooltip: string
}

const props = defineProps<{
  /** 当前选中的函证索引号 */
  confirmIndex: string
  /** 当前底稿编码（高亮当前） */
  currentWpCode?: string
  /** 各底稿是否存在该函证数据（wpCode → boolean） */
  existsMap?: Record<string, boolean>
}>()

const emit = defineEmits<{
  (e: 'navigate', wpCode: string, confirmIndex: string): void
}>()

// ─── 导航项定义（固定顺序） ──────────────────────────────────────────────────

const NAV_DEFINITIONS = [
  { wpCode: 'D0-2', label: 'D0-2', tooltip: '核实被函证单位' },
  { wpCode: 'D0-1', label: 'D0-1', tooltip: '函证汇总表' },
  { wpCode: 'D0-3', label: 'D0-3', tooltip: '跟函过程控制' },
  { wpCode: 'D0-7', label: 'D0-7', tooltip: '回函可靠性验证' },
  { wpCode: 'D0-4', label: 'D0-4', tooltip: '差异调节表' },
  { wpCode: 'D0-4b', label: 'D0-4b', tooltip: '差异检查表' },
  { wpCode: 'D0-5/6', label: 'D0-5/6', tooltip: '替代程序' },
  { wpCode: 'D0-8', label: 'D0-8', tooltip: '舞弊风险评价' },
] as const

const navItems = computed<NavItem[]>(() => {
  return NAV_DEFINITIONS.map(def => ({
    label: def.label,
    wpCode: def.wpCode,
    exists: props.existsMap?.[def.wpCode] ?? false,
    tooltip: def.tooltip,
  }))
})

function handleNavigate(item: NavItem) {
  if (!item.exists || item.wpCode === props.currentWpCode) return
  emit('navigate', item.wpCode, props.confirmIndex)
}
</script>

<style scoped>
.cross-workpaper-nav {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
}

.cross-workpaper-nav__label {
  color: #606266;
  white-space: nowrap;
  font-weight: 500;
}

.cross-workpaper-nav__items {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
}

.cross-workpaper-nav__chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 3px;
  font-size: 12px;
  cursor: default;
  transition: all 0.2s;
  border: 1px solid transparent;
}

.cross-workpaper-nav__chip--active {
  background: #ecf5ff;
  color: #409eff;
  border-color: #b3d8ff;
  cursor: pointer;
}

.cross-workpaper-nav__chip--active:hover {
  background: #d9ecff;
}

.cross-workpaper-nav__chip--current {
  background: #409eff;
  color: #fff;
  border-color: #409eff;
  cursor: default;
  font-weight: 600;
}

.cross-workpaper-nav__chip--disabled {
  background: #f4f4f5;
  color: #c0c4cc;
}
</style>
