<template>
  <el-card shadow="never" class="n1-consistency">
    <div class="bar" :class="`bar-${overall}`">
      <span class="bar-title">披露内部勾稽</span>
      <el-tag size="small" type="success" effect="plain">一致 {{ summary.ok }}</el-tag>
      <el-tag v-if="summary.skip" size="small" type="warning" effect="plain">待补数 {{ summary.skip }}</el-tag>
      <el-tag v-if="summary.error" size="small" type="danger" effect="plain">不一致 {{ summary.error }}</el-tag>
      <span class="bar-hint">{{ barHint }}</span>
      <el-button link size="small" class="bar-toggle" @click="expanded = !expanded">
        {{ expanded ? '收起明细 ▴' : '展开明细 ▾' }}
      </el-button>
    </div>

    <el-table v-if="expanded" :data="results" size="small" class="check-table" :row-class-name="rowClass">
      <el-table-column label="校验项" min-width="220">
        <template #default="{ row }">
          <span class="check-label">{{ row.label }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本表金额" width="140" align="right">
        <template #default="{ row }">{{ fmt(row.left) }}</template>
      </el-table-column>
      <el-table-column label="勾稽值" width="140" align="right">
        <template #default="{ row }">{{ fmt(row.right) }}</template>
      </el-table-column>
      <el-table-column label="差额" width="130" align="right">
        <template #default="{ row }">
          <span :class="{ 'diff-bad': row.level === 'error' }">{{ fmt(row.diff) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="tagType(row.level)" effect="plain">{{ levelText(row.level) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="勾稽依据（源模板公式）" min-width="300">
        <template #default="{ row }">
          <el-tooltip placement="top" :content="row.rule">
            <span class="rule-cell">{{ row.rule }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="追溯" width="160">
        <template #default="{ row }">
          <span v-for="r in row.refs || []" :key="r" class="ref-chip">
            <GtIndexChip :value="r" :context-project-id="projectId" />
          </span>
        </template>
      </el-table-column>
    </el-table>
  </el-card>
</template>

<script setup lang="ts">
/**
 * N1 披露内部勾稽校验面板（上市 / 国企共用，纯展示）
 *
 * 校验逻辑在 `composables/n1DisclosureConsistency.ts`（纯函数、可单测 + PBT）。
 * 「勾稽依据」列直接展示源模板公式出处（如 `源模板 B40=B52`），
 * 「追溯」列用 `GtIndexChip` 跳到来源底稿（N1-2 / N1-4 / N1-5 / N3）。
 */
import { computed, inject, ref } from 'vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import {
  summarizeN1Checks,
  type N1CheckLevel,
  type N1CheckResult,
} from '../../composables/n1DisclosureConsistency'

const props = defineProps<{
  results: N1CheckResult[]
  projectId: string
  defaultExpanded?: boolean
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
function fmt(v: number | null | undefined): string {
  if (v === null || v === undefined) return '—'
  return displayPrefs.fmtAmount(v)
}

const expanded = ref(props.defaultExpanded ?? false)
const summary = computed(() => summarizeN1Checks(props.results))

const overall = computed<'ok' | 'warn' | 'error'>(() => {
  if (summary.value.error > 0) return 'error'
  if (summary.value.skip > 0) return 'warn'
  return 'ok'
})

const barHint = computed(() => {
  if (props.results.length === 0) return '暂无可校验项（各表尚未录入）'
  if (summary.value.error > 0) return '存在不一致项，同步到附注前请先修正（附注数据以本表为源）'
  if (summary.value.skip > 0) return '部分勾稽项尚缺数据（跨底稿取数未就绪时不判定）'
  return '各表勾稽关系全部成立'
})

function tagType(level: N1CheckLevel): 'success' | 'warning' | 'danger' {
  if (level === 'error') return 'danger'
  if (level === 'ok') return 'success'
  return 'warning'
}

function levelText(level: N1CheckLevel): string {
  if (level === 'error') return '不一致'
  if (level === 'ok') return '一致'
  return '待补数'
}

function rowClass({ row }: { row: N1CheckResult }): string {
  if (row.level === 'error') return 'row-error'
  if (row.level === 'ok') return ''
  return 'row-warn'
}
</script>

<style scoped>
.n1-consistency { margin-bottom: 12px; }
.n1-consistency :deep(.el-card__body) { padding: 10px 12px; }

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
.bar-warn { border-left-color: var(--el-color-warning); background: var(--el-color-warning-light-9); }
.bar-error { border-left-color: var(--el-color-danger); background: var(--el-color-danger-light-9); }
.bar-title { font-weight: 600; }
.bar-hint { color: var(--el-text-color-secondary); font-size: 12px; }
.bar-toggle { margin-left: auto; }

.check-table { margin-top: 10px; font-size: 13px; }
.check-label { font-weight: 500; }
.rule-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.diff-bad { color: var(--el-color-danger); font-weight: 600; }
.ref-chip { margin-right: 4px; }
.check-table :deep(.row-error) { background: var(--el-color-danger-light-9); }
.check-table :deep(.row-warn) { background: var(--el-color-warning-light-9); }
.check-table :deep(td.is-right .cell) { white-space: nowrap; font-variant-numeric: tabular-nums; }
</style>
