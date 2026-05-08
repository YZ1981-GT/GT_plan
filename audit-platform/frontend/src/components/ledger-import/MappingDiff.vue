<template>
  <div class="mapping-diff">
    <div v-if="diffRows.length === 0" class="no-diff">
      <el-empty description="无映射变更" :image-size="60" />
    </div>
    <div v-else class="diff-list">
      <div
        v-for="(row, idx) in diffRows"
        :key="idx"
        class="diff-row"
        :class="row.type"
      >
        <span class="diff-icon">
          <span v-if="row.type === 'added'">＋</span>
          <span v-else-if="row.type === 'removed'">－</span>
          <span v-else-if="row.type === 'changed'">≠</span>
          <span v-else>＝</span>
        </span>
        <span class="diff-col-header">{{ row.columnHeader }}</span>
        <span class="diff-arrow">→</span>
        <span class="diff-field">
          <span v-if="row.type === 'changed'" class="old-value">{{ row.oldField }}</span>
          <span v-if="row.type === 'changed'" class="change-arrow">→</span>
          <span class="new-value">{{ row.newField || '(未映射)' }}</span>
        </span>
      </div>
    </div>

    <!-- 图例 -->
    <div class="diff-legend">
      <span class="legend-item added">＋ 新增映射</span>
      <span class="legend-item changed">≠ 变更映射</span>
      <span class="legend-item removed">－ 移除映射</span>
      <span class="legend-item unchanged">＝ 未变更</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

// ─── Props ──────────────────────────────────────────────────────────────────

interface MappingEntry {
  columnHeader: string
  standardField: string | null
}

const props = defineProps<{
  previous: MappingEntry[]
  current: MappingEntry[]
}>()

// ─── Types ──────────────────────────────────────────────────────────────────

interface DiffRow {
  type: 'added' | 'removed' | 'changed' | 'unchanged'
  columnHeader: string
  oldField: string | null
  newField: string | null
}

// ─── Computed ───────────────────────────────────────────────────────────────

const diffRows = computed<DiffRow[]>(() => {
  const prevMap = new Map(props.previous.map(m => [m.columnHeader, m.standardField]))
  const currMap = new Map(props.current.map(m => [m.columnHeader, m.standardField]))
  const allHeaders = new Set([...prevMap.keys(), ...currMap.keys()])

  const rows: DiffRow[] = []
  for (const header of allHeaders) {
    const prev = prevMap.get(header) ?? null
    const curr = currMap.get(header) ?? null

    if (prev === null && curr !== null) {
      rows.push({ type: 'added', columnHeader: header, oldField: null, newField: curr })
    } else if (prev !== null && curr === null) {
      rows.push({ type: 'removed', columnHeader: header, oldField: prev, newField: null })
    } else if (prev !== curr) {
      rows.push({ type: 'changed', columnHeader: header, oldField: prev, newField: curr })
    } else {
      rows.push({ type: 'unchanged', columnHeader: header, oldField: prev, newField: curr })
    }
  }
  return rows
})
</script>

<style scoped>
.mapping-diff {
  padding: 8px;
}

.diff-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.diff-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 4px;
  font-size: 13px;
}

.diff-row.added {
  background: var(--el-color-success-light-9);
  border-left: 3px solid var(--el-color-success);
}

.diff-row.removed {
  background: var(--el-color-danger-light-9);
  border-left: 3px solid var(--el-color-danger);
}

.diff-row.changed {
  background: var(--el-color-primary-light-9);
  border-left: 3px solid var(--el-color-primary);
}

.diff-row.unchanged {
  background: var(--el-fill-color-lighter);
  border-left: 3px solid var(--el-border-color-lighter);
  opacity: 0.7;
}

.diff-icon {
  min-width: 20px;
  text-align: center;
  font-weight: bold;
}

.diff-col-header {
  min-width: 120px;
  font-weight: 500;
}

.diff-arrow {
  color: var(--el-text-color-secondary);
}

.diff-field {
  display: flex;
  align-items: center;
  gap: 4px;
}

.old-value {
  text-decoration: line-through;
  color: var(--el-color-danger);
}

.change-arrow {
  color: var(--el-text-color-placeholder);
  font-size: 11px;
}

.new-value {
  color: var(--el-color-success-dark-2);
}

.diff-legend {
  margin-top: 16px;
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.legend-item.added { color: var(--el-color-success); }
.legend-item.changed { color: var(--el-color-primary); }
.legend-item.removed { color: var(--el-color-danger); }
.legend-item.unchanged { color: var(--el-text-color-placeholder); }
</style>
