<!--
  GtAProgramLinkedChips.vue — A 类程序表「关联底稿」chip 渲染（展示型子组件）

  从 GtAProgramConsole.vue 抽出（spec workpaper-frontend-large-component-split, Req 1
  复盘修正：template 体量大头）。承载 A16 seq2 / A17 seq5 / 正常 三分支 chip 渲染块。

  铁律（行为零变更）：
  - 纯展示：props 下行（row + 解析函数 + refs/maps）、emit 上行（chip-click / 折叠状态 v-model）。
  - 不 import 父组件、不重复 composable 状态；handleIndexChipClick 仍由父组件持有（保 jump-to-workpaper emit 契约）。
  - 模板 markup/class 与原内联块逐字一致，渲染 DOM/class/badge/禁用态完全相同。
-->
<template>
  <div v-if="row.linked_workpapers" class="gt-a-program-console__chips">
    <!-- A16 seq2 特殊渲染：推荐版本置顶 + badge + 其他版本折叠 -->
    <template v-if="isA16Seq2Row(row)">
      <!-- 推荐版本 chip（始终可见） -->
      <span
        v-if="a16RecommendedCode"
        class="gt-a-program-console__chip-wrap gt-a-program-console__chip-recommended"
      >
        <GtIndexChip
          :value="a16RecommendedCode"
          :validate="true"
          :prevent-navigate="inlinePopupWpCodes.has(a16RecommendedCode)"
          :disabled="isRowChipDisabled(row)"
          @click="emit('chip-click', $event)"
        />
        <span class="gt-a-program-console__recommend-badge">推荐</span>
        <span
          v-if="inlinePopupWpCodes.has(a16RecommendedCode) && popupCompletionStatus[a16RecommendedCode] === 'completed'"
          class="popup-badge popup-badge--done"
          title="已完成"
        >✓</span>
        <span
          v-else-if="inlinePopupWpCodes.has(a16RecommendedCode) && popupCompletionStatus[a16RecommendedCode] === 'in_progress'"
          class="popup-badge popup-badge--progress"
          title="进行中"
        >◐</span>
      </span>
      <!-- 其他版本折叠/展开 -->
      <span
        v-if="a16OtherVersions.length > 0"
        class="gt-a-program-console__other-versions-toggle"
        @click="emit('update:a16Expanded', !a16Expanded)"
      >
        {{ a16Expanded ? '收起 ▲' : '其他版本 ▼' }}
      </span>
      <!-- 展开后的其他版本 chips -->
      <template v-if="a16Expanded">
        <span
          v-for="(ref, idx) in a16OtherVersions"
          :key="'a16-other-' + idx"
          class="gt-a-program-console__chip-wrap"
        >
          <GtIndexChip
            :value="reviewChipDisplayValue(ref)"
            :validate="true"
            :prevent-navigate="inlinePopupWpCodes.has(reviewChipDisplayValue(ref))"
            :disabled="isRowChipDisabled(row) || isA17_5ChipDisabled(ref) || isReviewChipDisabled(ref)"
            @click="emit('chip-click', $event)"
          />
          <span
            v-if="a17_5Badge(ref)"
            class="gt-a-program-console__recommend-badge gt-a-program-console__a17-badge"
          >{{ a17_5Badge(ref) }}</span>
          <span
            v-else-if="reviewChipBadge(ref)"
            class="gt-a-program-console__recommend-badge gt-a-program-console__a17-badge"
          >{{ reviewChipBadge(ref) }}</span>
          <span
            v-if="inlinePopupWpCodes.has(reviewChipDisplayValue(ref)) && popupCompletionStatus[chipCompletionKey(ref)] === 'completed'"
            class="popup-badge popup-badge--done"
            title="已完成"
          >✓</span>
          <span
            v-else-if="inlinePopupWpCodes.has(reviewChipDisplayValue(ref)) && popupCompletionStatus[chipCompletionKey(ref)] === 'in_progress'"
            class="popup-badge popup-badge--progress"
            title="进行中"
          >◐</span>
        </span>
      </template>
    </template>
    <!-- A17 seq5：必做核对表置顶 + 不适用版本折叠 -->
    <template v-else-if="isA17Seq5Row(row)">
      <span
        v-for="(ref, idx) in a17ApplicableRefs(row)"
        :key="'a17-app-' + idx"
        class="gt-a-program-console__chip-wrap"
      >
        <GtIndexChip
          :value="ref"
          :validate="true"
          :prevent-navigate="inlinePopupWpCodes.has(ref)"
          :disabled="isRowChipDisabled(row)"
          @click="emit('chip-click', $event)"
        />
        <span
          v-if="a17_5Badge(ref)"
          class="gt-a-program-console__recommend-badge gt-a-program-console__a17-badge"
        >{{ a17_5Badge(ref) }}</span>
      </span>
      <span
        v-if="a17InapplicableRefs(row).length > 0"
        class="gt-a-program-console__other-versions-toggle"
        @click="emit('update:a17Expanded', !a17Expanded)"
      >
        {{ a17Expanded ? '收起 ▲' : '不适用版本 ▼' }}
      </span>
      <template v-if="a17Expanded">
        <span
          v-for="(ref, idx) in a17InapplicableRefs(row)"
          :key="'a17-na-' + idx"
          class="gt-a-program-console__chip-wrap"
        >
          <GtIndexChip
            :value="ref"
            :validate="true"
            :prevent-navigate="true"
            :disabled="true"
          />
        </span>
      </template>
    </template>
    <!-- 非 A16 seq2 / A17 seq5：正常渲染 -->
    <template v-else>
      <span
        v-for="(ref, idx) in parseLinkedWorkpapers(row.linked_workpapers)"
        :key="idx"
        class="gt-a-program-console__chip-wrap"
      >
        <GtIndexChip
          :value="reviewChipDisplayValue(ref)"
          :validate="true"
          :prevent-navigate="inlinePopupWpCodes.has(reviewChipDisplayValue(ref))"
          :disabled="isRowChipDisabled(row) || isA17_5ChipDisabled(ref) || isReviewChipDisabled(ref)"
          @click="emit('chip-click', $event)"
        />
        <span
          v-if="a17_5Badge(ref)"
          class="gt-a-program-console__recommend-badge gt-a-program-console__a17-badge"
        >{{ a17_5Badge(ref) }}</span>
        <span
          v-else-if="reviewChipBadge(ref)"
          class="gt-a-program-console__recommend-badge gt-a-program-console__a17-badge"
        >{{ reviewChipBadge(ref) }}</span>
        <span
          v-if="inlinePopupWpCodes.has(reviewChipDisplayValue(ref)) && popupCompletionStatus[chipCompletionKey(ref)] === 'completed'"
          class="popup-badge popup-badge--done"
          title="已完成"
        >✓</span>
        <span
          v-else-if="inlinePopupWpCodes.has(reviewChipDisplayValue(ref)) && popupCompletionStatus[chipCompletionKey(ref)] === 'in_progress'"
          class="popup-badge popup-badge--progress"
          title="进行中"
        >◐</span>
      </span>
    </template>
  </div>
</template>

<script setup lang="ts">
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { ResolvedIndexRef } from '@/utils/parseIndexRef'

/** chip 渲染所需的最小行字段（与父组件 ProgramRow 兼容） */
interface LinkedChipRow {
  linked_workpapers?: string
  status?: string
  [key: string]: any
}

defineProps<{
  /** 当前程序行 */
  row: LinkedChipRow
  /** 弹窗式子底稿 wp_code 集合（INLINE_POPUP_WP_CODES） */
  inlinePopupWpCodes: Set<string>
  /** 弹窗完成状态回显 map */
  popupCompletionStatus: Record<string, 'completed' | 'in_progress' | 'none'>
  /** A16 推荐版本 code */
  a16RecommendedCode: string
  /** A16 其他版本列表（排除推荐版本） */
  a16OtherVersions: string[]
  /** A16 其他版本折叠状态（v-model） */
  a16Expanded: boolean
  /** A17 不适用版本折叠状态（v-model） */
  a17Expanded: boolean
  // ─── 解析函数（父组件 composable 持有，传入复用，保行为一致）───
  // row 参数用 any：父组件以 ProgramRow 定义这些函数，子组件不约束行类型（避免逆变报错）
  isA16Seq2Row: (row: any) => boolean
  isRowChipDisabled: (row: any) => boolean
  isA17Seq5Row: (row: any) => boolean
  a17ApplicableRefs: (row: any) => string[]
  a17InapplicableRefs: (row: any) => string[]
  parseLinkedWorkpapers: (value: string) => string[]
  reviewChipDisplayValue: (ref: string) => string
  isA17_5ChipDisabled: (ref: string) => boolean
  isReviewChipDisabled: (ref: string) => boolean
  a17_5Badge: (ref: string) => string
  reviewChipBadge: (ref: string) => string
  chipCompletionKey: (ref: string) => string
}>()

const emit = defineEmits<{
  /** chip 点击：冒泡 ResolvedIndexRef，由父组件 handleIndexChipClick 处理（保 jump-to-workpaper 契约） */
  'chip-click': [resolved: ResolvedIndexRef]
  /** A16 其他版本折叠状态更新（v-model:a16Expanded） */
  'update:a16Expanded': [value: boolean]
  /** A17 不适用版本折叠状态更新（v-model:a17Expanded） */
  'update:a17Expanded': [value: boolean]
}>()
</script>

<style scoped>
.gt-a-program-console__chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}

.gt-a-program-console__chip-wrap {
  display: inline-flex;
  align-items: center;
}

.popup-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  font-size: 10px;
  border-radius: 50%;
  margin-left: 2px;
  vertical-align: middle;
}

.popup-badge--done {
  background: #e6f7e6;
  color: #2d8a2d;
  font-weight: 700;
}

.popup-badge--progress {
  background: #fff8e6;
  color: #b8860b;
}

/* A16 seq2 推荐版本 + 折叠 */
.gt-a-program-console__chip-recommended {
  display: inline-flex;
  align-items: center;
  gap: 2px;
}

.gt-a-program-console__recommend-badge {
  display: inline-flex;
  align-items: center;
  padding: 0 4px;
  height: 16px;
  font-size: 10px;
  font-weight: 600;
  color: #fff;
  background: var(--gt-purple, #4b2d77);
  border-radius: 3px;
  margin-left: 2px;
  white-space: nowrap;
}

.gt-a-program-console__other-versions-toggle {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
  color: var(--gt-purple, #4b2d77);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: background 0.2s;
  white-space: nowrap;
  user-select: none;
}

.gt-a-program-console__other-versions-toggle:hover {
  background: var(--gt-color-primary-bg, #f4f0fa);
}
</style>
