<template>
  <div class="confirmation-full-grid">
    <!-- 列显隐设置（宽表，Requirement 6.1） -->
    <div v-if="!readonly" class="confirmation-full-grid__toolbar">
      <el-popover placement="bottom-start" trigger="click" :width="300">
        <template #reference>
          <el-button size="small" plain>⚙ 列设置（{{ visibleColumns.length }}/{{ allColumns.length }}）</el-button>
        </template>
        <div class="confirmation-full-grid__prefs">
          <div class="confirmation-full-grid__prefs-presets">
            <el-button size="small" @click="applyPreset('all')">全部</el-button>
            <el-button size="small" @click="applyPreset('core')">核心</el-button>
            <el-button size="small" @click="applyPreset('nonEmpty')">隐藏空列</el-button>
          </div>
          <el-scrollbar max-height="320px">
            <el-checkbox-group v-model="visibleKeys">
              <div v-for="g in columnGroups" :key="g.group" class="confirmation-full-grid__prefs-group">
                <div class="confirmation-full-grid__prefs-group-title">{{ g.label }}</div>
                <el-checkbox
                  v-for="col in g.cols"
                  :key="col.key"
                  :value="col.key"
                  :disabled="col.fixed === 'left'"
                >{{ col.label }}</el-checkbox>
              </div>
            </el-checkbox-group>
          </el-scrollbar>
        </div>
      </el-popover>
    </div>

    <div class="confirmation-full-grid__scroll">
      <table class="confirmation-full-grid__table">
        <colgroup>
          <col v-for="col in visibleColumns" :key="col.key" :style="colStyle(col)" />
        </colgroup>
        <thead>
          <tr class="confirmation-full-grid__group-header">
            <th
              v-for="(group, gi) in visibleColumnGroups"
              :key="group.group"
              :colspan="group.cols.length"
              :class="'group--' + GROUP_COLOR[gi % GROUP_COLOR.length]"
            >
              {{ group.label }}
            </th>
          </tr>
          <tr class="confirmation-full-grid__col-header">
            <th v-for="col in visibleColumns" :key="col.key" :class="{ 'col--frozen': col.fixed === 'left' }">
              {{ col.label }}
            </th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="(row, idx) in rows" :key="row._row_id" :class="{ 'row--zebra': idx % 2 === 1 }">
            <td
              v-for="col in visibleColumns"
              :key="col.key"
              :class="[
                { 'col--frozen': col.fixed === 'left' },
                { 'cell--empty': isEmpty(row, col.key) },
                { 'cell--right': col.align === 'right' },
              ]"
            >
              <!-- Readonly / derived span -->
              <span v-if="readonly || col.editable === false || col.derived">
                {{ formatCell(row, col) }}
              </span>
              <!-- Select (match/一致性判定/相符情况) -->
              <el-select
                v-else-if="col.kind === 'select'"
                :model-value="(row as any)[col.key]"
                size="small"
                clearable
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.key, v)"
              >
                <el-option v-for="opt in optionsFor(col.key)" :key="opt.value" :label="opt.label" :value="opt.value" />
              </el-select>
              <!-- Amount / number -->
              <el-input-number
                v-else-if="col.kind === 'amount' || col.kind === 'number'"
                :model-value="(row as any)[col.key]"
                size="small"
                :controls="false"
                :precision="col.kind === 'amount' ? 2 : undefined"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.key, v)"
              />
              <!-- Boolean -->
              <el-checkbox
                v-else-if="col.kind === 'bool'"
                :model-value="(row as any)[col.key]"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.key, v)"
              />
              <!-- Date -->
              <el-date-picker
                v-else-if="col.kind === 'date'"
                :model-value="(row as any)[col.key]"
                size="small"
                type="date"
                value-format="YYYY-MM-DD"
                style="width: 100%"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.key, v)"
              />
              <!-- Text input -->
              <el-input
                v-else
                :model-value="(row as any)[col.key]"
                size="small"
                @update:model-value="(v: any) => $emit('update', row._row_id!, col.key, v)"
              />
            </td>
          </tr>
          <tr v-if="!rows.length">
            <td :colspan="visibleColumns.length" class="confirmation-full-grid__empty">暂无数据</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import type { ConfirmationRow } from './confirmationTypes'
import {
  resolveConfirmationColumns,
  COLUMN_GROUP_LABELS,
  CORE_COLUMN_KEYS,
  type ColumnDef,
  type ColumnGroup,
  type ConfirmCycle,
} from './confirmationColumnSpec'

const props = withDefaults(
  defineProps<{ rows: ConfirmationRow[]; readonly: boolean; cycle?: ConfirmCycle }>(),
  { cycle: 'D0' },
)
defineEmits<{ (e: 'update', rowId: string, field: string, value: any): void }>()

const GROUP_COLOR = ['blue', 'green', 'orange', 'purple', 'teal']

// 该枢纽全部列（BASE ∪ variant，配置驱动，Requirement 2.1）
const allColumns = computed<ColumnDef[]>(() => resolveConfirmationColumns(props.cycle))

// ─── 列显隐（localStorage 持久化，key 按枢纽，Requirement 6.1） ───────────────

const prefsKey = computed(() => `confirmation-${props.cycle}-column-prefs`)
const visibleKeys = ref<string[]>([])

function loadPrefs() {
  try {
    const raw = localStorage.getItem(prefsKey.value)
    if (raw) {
      const saved = JSON.parse(raw) as string[]
      const valid = new Set(allColumns.value.map((c) => c.key))
      visibleKeys.value = saved.filter((k) => valid.has(k))
      // 固定列强制可见
      for (const c of allColumns.value) {
        if (c.fixed === 'left' && !visibleKeys.value.includes(c.key)) visibleKeys.value.push(c.key)
      }
      if (visibleKeys.value.length) return
    }
  } catch { /* ignore */ }
  visibleKeys.value = allColumns.value.map((c) => c.key) // 默认全部
}

watch(prefsKey, loadPrefs, { immediate: true })
watch(visibleKeys, (v) => {
  try { localStorage.setItem(prefsKey.value, JSON.stringify(v)) } catch { /* ignore */ }
}, { deep: true })

const visibleColumns = computed<ColumnDef[]>(() => {
  const set = new Set(visibleKeys.value)
  return allColumns.value.filter((c) => set.has(c.key))
})

function applyPreset(preset: 'all' | 'core' | 'nonEmpty') {
  if (preset === 'all') {
    visibleKeys.value = allColumns.value.map((c) => c.key)
  } else if (preset === 'core') {
    const core = new Set(CORE_COLUMN_KEYS)
    visibleKeys.value = allColumns.value.filter((c) => core.has(c.key) || c.fixed === 'left').map((c) => c.key)
  } else {
    // 隐藏空列：保留固定列 + 有任一行非空的列
    visibleKeys.value = allColumns.value
      .filter((c) => c.fixed === 'left' || props.rows.some((r) => !isEmpty(r, c.key)))
      .map((c) => c.key)
  }
}

// ─── 分组表头（按 ColumnGroup 顺序） ─────────────────────────────────────────

interface GridGroup { group: ColumnGroup; label: string; cols: ColumnDef[] }

function buildGroups(cols: ColumnDef[]): GridGroup[] {
  const order: ColumnGroup[] = ['send_info', 'reply_info', 'reply_amount', 'alternative', 'send_memo']
  const groups: GridGroup[] = []
  for (const g of order) {
    const gc = cols.filter((c) => c.group === g)
    if (gc.length) groups.push({ group: g, label: COLUMN_GROUP_LABELS[g], cols: gc })
  }
  return groups
}

const columnGroups = computed<GridGroup[]>(() => buildGroups(allColumns.value))
const visibleColumnGroups = computed<GridGroup[]>(() => buildGroups(visibleColumns.value))

// ─── 单元格渲染 ──────────────────────────────────────────────────────────────

const MATCH_OPTIONS = [
  { label: '相符', value: '相符' },
  { label: '不符', value: '不符' },
  { label: '未回函', value: '未回函' },
]
const CONSISTENCY_OPTIONS = [
  { label: '一致', value: 'consistent' },
  { label: '不一致', value: 'inconsistent' },
  { label: '待核对', value: 'pending' },
]

function optionsFor(key: string): Array<{ label: string; value: string }> {
  if (key === 'match_status') return MATCH_OPTIONS
  // send_addr_match / send_reply_addr_match / term_match → 一致性判定
  return CONSISTENCY_OPTIONS
}

function colStyle(col: ColumnDef): Record<string, string> {
  const w = col.width ?? col.minWidth ?? 120
  return { width: w + 'px' }
}

function isEmpty(row: ConfirmationRow, field: string): boolean {
  const val = (row as any)[field]
  return val == null || val === '' || val === false
}

const CONSISTENCY_LABEL: Record<string, string> = {
  consistent: '一致',
  inconsistent: '不一致',
  pending: '待核对',
}

function formatCell(row: ConfirmationRow, col: ColumnDef): string {
  const val = (row as any)[col.key]
  if (val == null || val === '') return ''
  if (col.kind === 'amount' || col.kind === 'number') {
    return typeof val === 'number' ? val.toLocaleString() : String(val)
  }
  if (col.kind === 'bool') return val ? '是' : '否'
  if (col.kind === 'select' && col.key !== 'match_status') return CONSISTENCY_LABEL[val] ?? String(val)
  return String(val)
}
</script>

<style scoped>
.confirmation-full-grid {
  overflow: hidden;
}
.confirmation-full-grid__toolbar {
  margin-bottom: 8px;
}
.confirmation-full-grid__prefs-presets {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
}
.confirmation-full-grid__prefs-group {
  margin-bottom: 8px;
}
.confirmation-full-grid__prefs-group-title {
  font-size: 12px;
  color: #909399;
  margin-bottom: 2px;
}

.confirmation-full-grid__scroll {
  overflow-x: auto;
  max-height: 600px;
  overflow-y: auto;
}

.confirmation-full-grid__table {
  border-collapse: collapse;
  font-size: 12px;
  white-space: nowrap;
}

.confirmation-full-grid__table th,
.confirmation-full-grid__table td {
  border: 1px solid var(--el-border-color-lighter);
  padding: 4px 6px;
}
.confirmation-full-grid__table td.cell--right { text-align: right; }

.confirmation-full-grid__group-header th {
  text-align: center;
  font-weight: 600;
  font-size: 12px;
}

.group--blue { background: #e8f4fd; color: #1890ff; }
.group--green { background: #e8f8e8; color: #52c41a; }
.group--orange { background: #fff7e6; color: #fa8c16; }
.group--purple { background: #f3e8ff; color: #722ed1; }
.group--teal { background: #e6fffb; color: #13c2c2; }

.confirmation-full-grid__col-header th {
  background: #fafafa;
  font-weight: 500;
  text-align: center;
}

.col--frozen {
  position: sticky;
  left: 0;
  z-index: 2;
  background: #fff;
}

.row--zebra td {
  background: #fafbfc;
}

.cell--empty {
  opacity: 0.4;
}
.confirmation-full-grid__empty {
  text-align: center;
  color: #909399;
  padding: 16px;
}

.confirmation-full-grid__table .el-select,
.confirmation-full-grid__table .el-input,
.confirmation-full-grid__table .el-input-number {
  width: 100%;
}
</style>
