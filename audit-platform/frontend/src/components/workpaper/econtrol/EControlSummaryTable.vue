<!--
  EControlSummaryTable.vue — summary 子模式：动态表 + per_row 缺陷着色

  抽离自 GtEControlTest.vue Task 13（design §2.3）
  渲染 summaryColumns（enum/multi_enum/number/text）+ summaryRowClass（重大缺陷红/控制缺陷黄）+ 增删行
-->

<template>
  <section class="gt-e__summary">
    <div class="gt-e__toolbar">
      <h3 class="gt-e__title">控制测试汇总表</h3>
      <div v-if="!readonly" class="gt-e__toolbar-actions">
        <el-button size="small" :icon="PlusIcon" @click="handleAddRow">
          新增控制行
        </el-button>
      </div>
    </div>

    <el-table
      :data="rows"
      border
      size="small"
      class="gt-e__summary-table"
      :row-class-name="summaryRowClass"
      empty-text="暂无控制项，点击「新增控制行」开始"
    >
      <el-table-column
        v-for="col in summaryColumns"
        :key="col.field"
        :label="col.label"
        :min-width="col.width"
        resizable
      >
        <template #default="{ row, $index }">
          <!-- enum 单选下拉 -->
          <el-select
            v-if="col.type === 'enum'"
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            clearable
            :placeholder="col.label"
            @change="emit('field-change', row, col.field, $index)"
          >
            <el-option
              v-for="opt in col.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>

          <!-- multi_enum 多选 -->
          <el-select
            v-else-if="col.type === 'multi_enum'"
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            multiple
            collapse-tags
            collapse-tags-tooltip
            :placeholder="col.label"
            @change="emit('field-change', row, col.field, $index)"
          >
            <el-option
              v-for="opt in col.enum || []"
              :key="opt"
              :label="opt"
              :value="opt"
            />
          </el-select>

          <!-- number -->
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.field]"
            :disabled="readonly"
            :min="col.min ?? 0"
            size="small"
            controls-position="right"
            @change="emit('field-change', row, col.field, $index)"
          />

          <!-- index_chip 渲染 -->
          <GtIndexChip
            v-else-if="col.render === 'index_chip' && row[col.field]"
            :value="row[col.field]"
            :validate="true"
          />

          <!-- text/textarea -->
          <el-input
            v-else
            v-model="row[col.field]"
            :disabled="readonly"
            size="small"
            :type="col.type === 'textarea' ? 'textarea' : 'text'"
            :rows="col.type === 'textarea' ? 2 : undefined"
            :maxlength="col.max_length"
            :placeholder="col.label"
            @input="emit('field-change', row, col.field, $index)"
          />
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!readonly" label="操作" width="120" fixed="right">
        <template #default="{ row, $index }">
          <el-button
            link
            type="danger"
            size="small"
            @click="emit('remove-row', $index)"
          >
            删除
          </el-button>
          <el-button
            link
            size="small"
            @click="$emit('open-attachment', `row_${$index}`)"
          >
            📎
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Plus as PlusIcon } from '@element-plus/icons-vue'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import type { EControlTestSchema, SummaryRow, DynamicTableColumnDef } from '../GtEControlTest.types'

const props = defineProps<{
  schema: EControlTestSchema
  rows: SummaryRow[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  'field-change': [row: SummaryRow, field: string, index: number]
  'add-row': []
  'remove-row': [index: number]
  'open-attachment': [rowRef: string]
}>()

// ─── Computed ────────────────────────────────────────────────────────────────

const summaryColumns = computed<DynamicTableColumnDef[]>(() => {
  const cols = props.schema?.dynamic_table?.columns ?? {}
  return Object.entries(cols).map(([_cellLetter, def]) => {
    const colDef = def as DynamicTableColumnDef
    const width = colDef.type === 'textarea' ? 200 : 120
    return {
      ...colDef,
      width,
    }
  })
})

// ─── Row class (deficiency coloring) ─────────────────────────────────────────

function summaryRowClass(payload: { row: SummaryRow }): string {
  if (payload.row?.deficiency === '重大缺陷') return 'gt-e__summary-row--danger'
  if (payload.row?.deficiency === '控制缺陷') return 'gt-e__summary-row--warning'
  return ''
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleAddRow() {
  emit('add-row')
}
</script>

<style scoped>
.gt-e__summary {
  display: flex;
  flex-direction: column;
}
.gt-e__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}
.gt-e__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.gt-e__toolbar-actions {
  display: flex;
  gap: 8px;
}
.gt-e__summary-table :deep(.gt-e__summary-row--warning) {
  background: var(--el-color-warning-light-9);
}
.gt-e__summary-table :deep(.gt-e__summary-row--danger) {
  background: var(--el-color-danger-light-9);
}
</style>
