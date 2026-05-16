<script setup lang="ts">
/**
 * 快照对比视图
 * Sprint 8 Task 8.6: 快照对比 + 差异高亮
 */
import { ref, computed } from 'vue'

interface Snapshot {
  id: string
  trigger_event: string
  created_at: string
  created_by: string
  is_locked: boolean
}

interface Change {
  field: string
  old_value: string | number | null
  new_value: string | number | null
}

const props = defineProps<{
  snapshots: Snapshot[]
  changes: Change[]
  loading?: boolean
}>()

const emit = defineEmits<{
  (e: 'compare', snapshotA: string, snapshotB: string): void
}>()

const selectedA = ref<string>('')
const selectedB = ref<string>('')

const triggerLabels: Record<string, string> = {
  prefill: '预填充',
  review: '提交复核',
  sign: '签字',
}

const canCompare = computed(() => selectedA.value && selectedB.value && selectedA.value !== selectedB.value)

function doCompare() {
  if (canCompare.value) {
    emit('compare', selectedA.value, selectedB.value)
  }
}

function formatValue(val: string | number | null): string {
  if (val === null || val === undefined) return '—'
  if (typeof val === 'number') return val.toLocaleString()
  return String(val)
}

function hasChanged(change: Change): boolean {
  return change.old_value !== change.new_value
}
</script>

<template>
  <div class="snapshot-compare">
    <div class="compare-selector">
      <div class="selector-item">
        <span class="label">快照 A:</span>
        <el-select v-model="selectedA" placeholder="选择基准快照" size="small" style="width: 220px">
          <el-option
            v-for="s in snapshots"
            :key="s.id"
            :value="s.id"
            :label="`${triggerLabels[s.trigger_event] || s.trigger_event} - ${s.created_at?.slice(0, 16)}`"
          >
            <span>{{ triggerLabels[s.trigger_event] || s.trigger_event }}</span>
            <span style="float: right; color: var(--gt-color-info); font-size: var(--gt-font-size-xs)">
              {{ s.created_at?.slice(0, 16) }}
            </span>
          </el-option>
        </el-select>
      </div>

      <div class="selector-item">
        <span class="label">快照 B:</span>
        <el-select v-model="selectedB" placeholder="选择对比快照" size="small" style="width: 220px">
          <el-option
            v-for="s in snapshots"
            :key="s.id"
            :value="s.id"
            :label="`${triggerLabels[s.trigger_event] || s.trigger_event} - ${s.created_at?.slice(0, 16)}`"
          />
        </el-select>
      </div>

      <el-button type="primary" size="small" :disabled="!canCompare" @click="doCompare">
        对比
      </el-button>
    </div>

    <!-- 差异列表 -->
    <el-table
      v-if="changes.length > 0"
      :data="changes"
      size="small"
      stripe
      border
      max-height="350"
      class="diff-table"
    >
      <el-table-column label="字段" prop="field" width="180" show-overflow-tooltip />
      <el-table-column label="快照 A 值" width="160">
        <template #default="{ row }">
          <span :class="{ 'diff-old': hasChanged(row) }">
            {{ formatValue(row.old_value) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="快照 B 值" width="160">
        <template #default="{ row }">
          <span :class="{ 'diff-new': hasChanged(row) }">
            {{ formatValue(row.new_value) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80" align="center">
        <template #default="{ row }">
          <el-tag v-if="hasChanged(row)" type="warning" size="small">变更</el-tag>
          <el-tag v-else type="info" size="small">相同</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <el-empty v-else-if="!loading" description="选择两个快照进行对比" />
  </div>
</template>

<style scoped>
.snapshot-compare {
  padding: 12px;
}
.compare-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.selector-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.selector-item .label {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  white-space: nowrap;
}
.diff-table {
  margin-top: 8px;
}
.diff-old {
  color: var(--gt-color-coral);
  text-decoration: line-through;
}
.diff-new {
  color: var(--gt-color-success);
  font-weight: 600;
}
</style>
