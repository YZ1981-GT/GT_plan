<script setup lang="ts">
/**
 * D1-1 审定表单元格的「已人工覆盖」标记 + 恢复取数入口。
 *
 * spec: d1-sync-row-table-engine-and-d1-coverage · Task 33（需求 6.3 / 6.4）
 *
 * ═══ 为什么需要它 ═══
 *
 * 修前：cross-sheet（D1-2 原值 / D1-4 坏账小计）一有值就整行覆盖手工值，且该行被置为只读
 * ⇒ 审计师录的数**既看不见也改不了**，凭空消失且无任何提示（静默丢数据）。
 *
 * 修后覆盖由逐格四态表达（`row.cellStates[field]`）：
 *   S1 纯派生（跟随上游，无标记）· S2 人工覆盖·上游未变 · S3 无覆盖·上游已变（自动跟随）
 *   S4 人工覆盖 且 上游已变
 * 本组件只在 **S2 / S4** 显示标记 —— 让「这格不是上游值、是人工改过的」这件事在界面上可见，
 * 并给出一键退回上游取数。
 *
 * 🔴 S4 的**双值展示**（同时显示覆盖值与当前上游值）尚未做 —— 需要把逐格 derived 也暴露到行上。
 *    已在 spec 里登记，本组件的 tooltip 先用文字点明「上游已变化」。
 */
import { computed } from 'vue'
import { RefreshLeft } from '@element-plus/icons-vue'

import type { AdjudicationDetailRow } from '../composables/useD1Adjudication'

const props = defineProps<{
  row: AdjudicationDetailRow
  /** per-cell 字段后缀，如 `prior-unadj` / `current-aje`。 */
  field: string
  readonly?: boolean
}>()

const emit = defineEmits<{ restore: [rowKey: string, field: string] }>()

const state = computed(() => props.row.cellStates?.[props.field])
/** 只有 S2/S4 才是「人工覆盖」态。 */
const isOverridden = computed(() => state.value === 'S2' || state.value === 'S4')
/** S4 = 覆盖 且 上游已变，提示语要区别于 S2。 */
const upstreamChanged = computed(() => state.value === 'S4')

const tip = computed(() =>
  upstreamChanged.value
    ? '本格为人工录入值，且上游明细已发生变化。点击可恢复为上游取数值。'
    : '本格为人工录入值，未跟随上游明细。点击可恢复为上游取数值。',
)
</script>

<template>
  <span v-if="isOverridden" class="d1-cell-override">
    <el-tooltip :content="tip" placement="top">
      <el-tag
        size="small"
        :type="upstreamChanged ? 'warning' : 'info'"
        effect="plain"
        class="d1-cell-override__tag"
      >
        {{ upstreamChanged ? '已覆盖·上游已变' : '已人工覆盖' }}
      </el-tag>
    </el-tooltip>
    <el-button
      v-if="!readonly"
      :icon="RefreshLeft"
      link
      size="small"
      class="d1-cell-override__restore"
      title="恢复为上游取数值"
      @click="emit('restore', row.rowKey, field)"
    />
  </span>
</template>

<style scoped>
.d1-cell-override {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  margin-left: 4px;
  vertical-align: middle;
}

.d1-cell-override__tag {
  transform: scale(0.85);
  transform-origin: left center;
}

.d1-cell-override__restore {
  padding: 0;
  height: auto;
}
</style>
