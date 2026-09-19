<template>
  <el-card shadow="never" class="h1-consistency">
    <div class="bar" :class="`bar-${overall}`">
      <span class="bar-title">披露内部勾稽</span>
      <el-tag size="small" type="success" effect="plain">一致 {{ result.okCount }}</el-tag>
      <el-tag v-if="result.warnCount" size="small" type="warning" effect="plain">待补数 {{ result.warnCount }}</el-tag>
      <el-tag v-if="result.errorCount" size="small" type="danger" effect="plain">不一致 {{ result.errorCount }}</el-tag>
      <span class="bar-hint">{{ barHint }}</span>
      <el-button link size="small" class="bar-toggle" @click="expanded = !expanded">
        {{ expanded ? '收起明细 ▴' : '展开明细 ▾' }}
      </el-button>
    </div>

    <el-table
      v-if="expanded"
      :data="result.checks"
      size="small"
      class="wp-table check-table"
      :row-class-name="rowClass"
    >
      <el-table-column label="校验项" min-width="200">
        <template #default="{ row }">
          <span class="check-label">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本表金额" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.left) }}</template>
      </el-table-column>
      <el-table-column label="勾稽值" width="130" align="right">
        <template #default="{ row }">{{ fmtAmount(row.right) }}</template>
      </el-table-column>
      <el-table-column label="差额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-bad': row.level === 'error' }">{{ fmtAmount(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="tagType(row.level)" effect="plain">{{ levelText(row.level) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="勾稽依据" min-width="260">
        <template #default="{ row }">
          <el-tooltip placement="top" :content="row.rule">
            <span class="rule-cell">{{ row.detail }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="追溯" width="150">
        <template #default="{ row }">
          <span v-for="ref in row.refs" :key="ref" class="ref-chip">
            <GtIndexChip :value="ref" :context-project-id="projectId" />
          </span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
/**
 * H1 披露内部勾稽校验面板（上市 / 国企共用）
 *
 * 只做展示：校验逻辑在 `h1DisclosureConsistency.ts`（纯函数、可单测）。
 * 「勾稽依据」列 tooltip 给出规则原文，「追溯」列用 GtIndexChip 跳到来源底稿 / 附注章节。
 */
import { computed, inject, ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import type { H1CheckLevel, H1ConsistencySummary } from '../../composables/h1DisclosureConsistency'

const props = defineProps<{
  result: H1ConsistencySummary
  projectId: string
  /** 默认展开（不一致时建议传 true） */
  defaultExpanded?: boolean
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const fmtAmount = (v: number) => displayPrefs.fmtAmount(v)

const expanded = ref(props.defaultExpanded ?? false)

const overall = computed<H1CheckLevel>(() => {
  if (props.result.errorCount > 0) return 'error'
  if (props.result.warnCount > 0) return 'warn'
  return 'ok'
})

const barHint = computed(() => {
  if (props.result.errorCount > 0) {
    return '存在不一致项，同步到附注前请先修正（附注数据以本表为源）'
  }
  if (props.result.warnCount > 0) return '部分子表已填但①情况表尚未取数'
  return '各表勾稽关系全部成立'
})

function tagType(level: H1CheckLevel): 'success' | 'warning' | 'danger' {
  if (level === 'error') return 'danger'
  if (level === 'warn') return 'warning'
  return 'success'
}

function levelText(level: H1CheckLevel): string {
  if (level === 'error') return '不一致'
  if (level === 'warn') return '待补数'
  return '一致'
}

function rowClass({ row }: { row: { level: H1CheckLevel } }): string {
  return row.level === 'error' ? 'row-error' : row.level === 'warn' ? 'row-warn' : ''
}
</script>

<style scoped>
.h1-consistency {
  margin-bottom: 12px;
}

.h1-consistency :deep(.el-card__body) {
  padding: 10px 12px;
}

.bar {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  padding: 4px 8px;
  border-left: 3px solid var(--el-color-success);
  background: var(--el-color-success-light-9);
  border-radius: 3px;
}

.bar-warn {
  border-left-color: var(--el-color-warning);
  background: var(--el-color-warning-light-9);
}

.bar-error {
  border-left-color: var(--el-color-danger);
  background: var(--el-color-danger-light-9);
}

.bar-title {
  font-weight: 600;
}

.bar-hint {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.bar-toggle {
  margin-left: auto;
}

.check-table {
  margin-top: 10px;
  font-size: 13px;
}

.check-label {
  font-weight: 500;
}

.rule-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}

.diff-bad {
  color: var(--el-color-danger);
  font-weight: 600;
}

.ref-chip {
  margin-right: 4px;
}

.check-table :deep(.row-error) {
  background: var(--el-color-danger-light-9);
}

.check-table :deep(.row-warn) {
  background: var(--el-color-warning-light-9);
}

.check-table :deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
