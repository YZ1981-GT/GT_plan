<!--
  DerivedCellOverrideBadge —— 派生格逐格覆盖态徽标 + 「恢复取数」入口（D5-1 / D6-1 / D7-1 共用）

  spec: d567-sync-coverage-via-row-table-engine · Task 20 · Requirements 4.4 / 4.5 / 4.6

  🔴 为什么做成共享组件：D1 用专有 `D1CellOverrideBadge.vue`、D4 把同样的
     tooltip+tag+按钮**内联**在 Tab 里（约 25 行 × 每个派生列）。D5/D6/D7 合计有
     1 + 4 + 4 = 9 个派生列位，内联会复制九份、必漂移。本组件只依赖行对象上的
     `cellOverrides[field]` 契约（三家 composable 同形），不关心区块/行键语义。

  语义（四态状态机，与 `shared/dynamicAdjudicationRows.ts` 同源）：
    * S1/S3 —— 行对象上**不产生** `cellOverrides` 条目 ⇒ 本组件整体不渲染（纯派生跟随上游）
    * S2    —— 已人工覆盖、上游未变 ⇒ 黄色「已人工覆盖」
    * S4    —— 已人工覆盖、**上游已变** ⇒ 红色「覆盖·上游已变」，tooltip 里三值并列
                （覆盖值 / 原派生值 / 现派生值），**系统不自动二选一**，由人决定
-->
<template>
  <span v-if="cell" class="derived-override">
    <el-tooltip :show-after="120" placement="top" effect="light">
      <template #content>
        <div class="derived-override__tip">
          <div>该格已人工覆盖（不再随上游自动变化）</div>
          <div>覆盖值：{{ fmt(cell.stored) }}</div>
          <template v-if="cell.state === 'S4'">
            <div>原派生值：{{ fmt(cell.snap) }}</div>
            <div class="derived-override__conflict">
              现派生值：{{ fmt(cell.derived) }}（上游已变）
            </div>
          </template>
        </div>
      </template>
      <el-tag
        :type="cell.state === 'S4' ? 'danger' : 'warning'"
        size="small"
        effect="plain"
        class="derived-override__tag"
      >{{ cell.state === 'S4' ? '覆盖·上游已变' : '已人工覆盖' }}</el-tag>
    </el-tooltip>
    <el-button
      v-if="!readonly"
      link
      type="primary"
      size="small"
      class="derived-override__restore"
      @click="emit('restore')"
    >恢复取数</el-button>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'

/** 单格覆盖态（三家 composable 的 `cellOverrides[field]` 同形契约）。 */
interface DerivedCellOverride {
  state: 'S1' | 'S2' | 'S3' | 'S4'
  stored: number
  snap: number
  derived: number
}

const props = withDefaults(
  defineProps<{
    /** 行对象的 `cellOverrides`（S1/S3 时为 undefined ⇒ 不渲染）。 */
    overrides?: Record<string, DerivedCellOverride> | undefined
    /** 本徽标对应的字段名，如 `currentUnadjusted` / `priorUnadjusted`。 */
    field: string
    readonly?: boolean
  }>(),
  { overrides: undefined, readonly: false },
)

const emit = defineEmits<{ (e: 'restore'): void }>()

const cell = computed<DerivedCellOverride | undefined>(() => props.overrides?.[props.field])

function fmt(v: number): string {
  if (!Number.isFinite(v)) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.derived-override {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 4px;
}
.derived-override__tag {
  cursor: help;
}
.derived-override__tip {
  line-height: 1.6;
}
.derived-override__conflict {
  color: var(--el-color-danger);
  font-weight: 600;
}
.derived-override__restore {
  padding: 0;
}
</style>
