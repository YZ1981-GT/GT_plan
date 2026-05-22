<template>
  <el-dialog
    :model-value="visible"
    @update:model-value="$emit('update:visible', $event)"
    title="预填充变更预览"
    width="800px"
    append-to-body
  >
    <!-- 汇总统计 -->
    <div class="gt-prefill-summary">
      <el-tag type="info">总变更 {{ summary.total_changes }}</el-tag>
      <el-tag type="success">新增 {{ summary.new_cells }}</el-tag>
      <el-tag type="warning">修改 {{ summary.modified_cells }}</el-tag>
      <el-tag v-if="summary.highlight_count > 0" type="danger">
        ⚠️ 大幅变动 {{ summary.highlight_count }}
      </el-tag>
    </div>

    <!-- 变更列表 -->
    <el-table
      :data="changes"
      border
      size="small"
      max-height="400px"
      @selection-change="onSelectionChange"
    >
      <el-table-column type="selection" width="40" />
      <el-table-column prop="sheet" label="Sheet" width="150" />
      <el-table-column prop="cell_ref" label="单元格" width="80" />
      <el-table-column prop="formula" label="公式" width="200" show-overflow-tooltip />
      <el-table-column label="旧值" width="120">
        <template #default="{ row }">
          <span class="gt-prefill-old">{{ formatVal(row.old_value) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="新值" width="120">
        <template #default="{ row }">
          <span class="gt-prefill-new">{{ formatVal(row.new_value) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动" width="80">
        <template #default="{ row }">
          <span :class="{ 'gt-prefill-highlight': row.is_highlight }">
            {{ row.change_pct != null ? `${row.change_pct.toFixed(1)}%` : '-' }}
          </span>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部操作 -->
    <template #footer>
      <el-button @click="$emit('cancel')">取消</el-button>
      <el-button
        type="primary"
        :disabled="selectedCells.length === 0 && changes.length > 0"
        @click="$emit('accept-selected', selectedCells)"
      >
        应用选中 ({{ selectedCells.length }})
      </el-button>
      <el-button type="success" @click="$emit('accept-all')">
        全部接受 ({{ changes.length }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface PrefillChange {
  sheet: string
  cell_ref: string
  formula: string
  old_value: number | null
  new_value: number | null
  change_pct: number | null
  is_highlight: boolean
}

defineProps<{
  visible: boolean
  changes: PrefillChange[]
  summary: {
    total_changes: number
    new_cells: number
    modified_cells: number
    highlight_count: number
  }
}>()

defineEmits<{
  'update:visible': [val: boolean]
  'accept-all': []
  'accept-selected': [cells: string[]]
  cancel: []
}>()

const selectedCells = ref<string[]>([])

function onSelectionChange(rows: PrefillChange[]) {
  selectedCells.value = rows.map(r => r.cell_ref)
}

function formatVal(v: number | null): string {
  if (v == null) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.gt-prefill-summary {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
}

.gt-prefill-old {
  color: #999;
  text-decoration: line-through;
}

.gt-prefill-new {
  color: #67c23a;
  font-weight: 600;
}

.gt-prefill-highlight {
  color: #e6a23c;
  font-weight: 600;
  background: #fdf6ec;
  padding: 2px 4px;
  border-radius: 3px;
}
</style>
