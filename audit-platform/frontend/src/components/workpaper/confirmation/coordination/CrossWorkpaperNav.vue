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
 * CrossWorkpaperNav.vue — 跨表导航条（七枢纽共享：D0/E0/F0/G0/H0/K0/L0）
 *
 * 选中 confirm_index 后展示"本笔函证相关底稿"横向导航，按状态点亮
 * （有数据=蓝色可点击 / 无数据=灰色）+ 跳转定位。
 *
 * spec: g0-confirmation-source-alignment，Task 11（Requirement 5.1/5.2/5.3/5.6, 11.6）
 *
 * 🔴 改造前这里写死了 D0-* 八项 → 挂在 E0/F0/G0/H0/K0/L0 上会显示别的循环的清单，
 *    而 `buildCrossWorkpaperNavDefs()` 早已按循环解析却是零消费方。现改为按 `wpCode`
 *    解析（`cycleConfirmationMeta` 是唯一真源），槽位不存在的循环不生成入口。
 *
 * 🔴 两条跳转路径（G0 是单 `wp_code` 多 sheet 工作簿，不能一律按 wp_code 跳）：
 *    - 同工作簿（有真实 tab 名真源且与展示编码不同，即 G0）→ emit `navigate-sheet`，
 *      宿主走 `?sheet=<sheetName>` + `utils/normalizeSheetName.resolveSheetNameByDeepLink`
 *    - 其余（六枢纽的派生值、组合替代程序 `X0-5/X0-6`）→ emit 既有 `navigate`（按 wp_code）
 *    ⚠️ `sheetName` 为 null **不是**「不生成入口」，而是回退按 `wpCode` 跳转；
 *       只有「槽位本身不存在（meta 里是 null）」才不生成入口 —— 否则六枢纽入口会被全部干掉。
 */
import { computed } from 'vue'

import { locatorOf } from './crossWorkpaperNavLocator'
import {
  buildCrossWorkpaperNavDefs,
  isSameWorkbookNavTarget,
} from './cycleConfirmationMeta'

export interface NavItem {
  /** 显示文字（底稿目录索引号） */
  label: string
  /** 底稿编码（跨工作簿跳转用） */
  wpCode: string
  /** 同工作簿定位值（源模板真实 tab 名）；null = 无 tab 名真源，回退按 wpCode 跳 */
  sheetName: string | null
  /** 是否走同工作簿 `?sheet=` 切页 */
  sameWorkbook: boolean
  /** 是否存在该函证的数据 */
  exists: boolean
  /** 悬停提示 */
  tooltip: string
}

const props = defineProps<{
  /** 当前选中的函证索引号 */
  confirmIndex: string
  /** 当前底稿/工作簿编码（决定按哪个循环解析导航项；缺省回退 currentWpCode） */
  wpCode?: string
  /** 当前底稿编码（高亮当前） */
  currentWpCode?: string
  /** 各底稿是否存在该函证数据（wpCode → boolean） */
  existsMap?: Record<string, boolean>
}>()

const emit = defineEmits<{
  /**
   * 🔴 保留声明但内部不再触发（Task 5 / Requirement 1.3）：
   *    宿主 `GtWpRenderer` 只监听 `@navigate-sheet`，函证域内 `navigate` 落地即静默丢弃；
   *    但声明留着以免破坏潜在的外部监听方，删掉属于破坏性变更。
   */
  (e: 'navigate', wpCode: string, confirmIndex: string): void
  (e: 'navigate-sheet', locator: string, confirmIndex: string): void
}>()

// ─── 导航项（按循环解析，顺序由 buildCrossWorkpaperNavDefs 固定） ─────────────

const navItems = computed<NavItem[]>(() => {
  const defs = buildCrossWorkpaperNavDefs(props.wpCode || props.currentWpCode)
  return defs.map(def => ({
    label: def.label,
    wpCode: def.wpCode,
    sheetName: def.sheetName,
    sameWorkbook: isSameWorkbookNavTarget(def),
    exists: props.existsMap?.[def.wpCode] ?? false,
    // 灰态现在也可点（Task 5）→ tooltip 必须说明「灰=暂无数据」，
    // 否则「灰着却能点」会被当成样式 bug。
    tooltip: (props.existsMap?.[def.wpCode] ?? false)
      ? def.tooltip
      : `${def.tooltip}（本笔暂无数据，点击可前往编制）`,
  }))
})

/**
 * 定位值由同目录纯函数 `locatorOf` 给出（见 `crossWorkpaperNavLocator.ts`，
 * 那里记录了「为什么统一 emit navigate-sheet」「为什么 wp_code 也能当定位值」
 * 「为什么要取斜杠首段」三条依据）。
 * 抽出去的原因：`<script setup>` 不允许运行时 `export`，而守卫要把它当纯函数直接断言。
 */

/**
 * 🔴 去掉 `!item.exists` 早退（Task 5 / Requirement 1.5）：
 *    `existsMap` 由调用方按「该底稿有无该函证的数据」填充，缺省 `{}` → `exists` 恒 false
 *    → **整条导航条一个都点不动**（本 spec 立项前它零渲染，故此缺陷从未被用户碰到）。
 *    `exists` 的正确职责只是视觉提示（蓝色可点 / 灰色无数据），
 *    「目标底稿还没数据」不是禁止跳转的理由 —— 审计师正是要跳过去编制它。
 */
function handleNavigate(item: NavItem) {
  if (item.wpCode === props.currentWpCode) return
  emit('navigate-sheet', locatorOf(item), props.confirmIndex)
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
  font-size: var(--wp-font-size, 13px);
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

/*
 * 🔴 语义修正（spec confirmation-orphan-and-amount-format-closure，Task 5）：
 *    本类名保留为 `--disabled` 只为避免无谓的类名 churn，其**语义已由
 *    「不可点击」改为「该底稿尚无数据」** —— 灰色仅表示未编制，仍可点击前往编制
 *    （改造前 `handleNavigate` 在 `!item.exists` 时早退，导致"想去编制却点不动"）。
 *    故此处必须给 `cursor: pointer`，否则视觉语义与行为矛盾。
 */
.cross-workpaper-nav__chip--disabled {
  background: #f4f4f5;
  color: #c0c4cc;
  cursor: pointer;
}

.cross-workpaper-nav__chip--disabled:hover {
  background: #ebeef5;
  color: #909399;
}
</style>
