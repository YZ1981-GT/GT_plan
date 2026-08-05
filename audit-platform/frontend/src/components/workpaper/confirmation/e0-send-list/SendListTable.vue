<script setup lang="ts">
/**
 * SendListTable — E0 发函清单共用表格组件
 *
 * 功能：列显隐 / 枚举 el-select / 日期 el-date-picker / 金额 WpAmountInput / 动态行增删
 * 铁律：13px 字号 / 金额右对齐 tabular-nums / 零 el-input-number :formatter
 */
import { computed } from 'vue'
import type { SendListColumn, SendListSpec } from './sendListSpec'
import type { SendListRow } from './useSendListData'
import WpAmountInput from '../../shared/WpAmountInput.vue'

const props = defineProps<{
  spec: SendListSpec
  rows: SendListRow[]
  visibleColumns: SendListColumn[]
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'add-row'): void
  (e: 'remove-row', rowId: string): void
  (e: 'move-row', rowId: string, dir: 'up' | 'down'): void
  (e: 'toggle-column', field: string): void
  (e: 'save'): void
  (e: 'export-template'): void
  (e: 'export-data'): void
  (e: 'import-data'): void
}>()

const tableData = computed(() => props.rows)

function onCellChange() {
  emit('save')
}
</script>

<template>
  <div class="send-list-table-wrapper">
    <!-- 工具栏 -->
    <div class="send-list-toolbar">
      <el-button
        v-if="!isReadonly"
        type="primary"
        size="small"
        @click="emit('add-row')"
      >
        + 新增行
      </el-button>

      <!-- 导入导出 -->
      <el-dropdown size="small" style="margin-left: 8px" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="emit('export-template')">导出模板</el-dropdown-item>
            <el-dropdown-item @click="emit('export-data')">导出数据</el-dropdown-item>
            <el-dropdown-item @click="emit('import-data')" :disabled="isReadonly">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>

      <!-- 列显隐（仅宽表） -->
      <el-popover
        v-if="spec.columnToggle"
        placement="bottom-end"
        trigger="click"
        :width="200"
      >
        <template #reference>
          <el-button size="small" style="margin-left: 8px">⚙ 列设置</el-button>
        </template>
        <div style="max-height: 300px; overflow-y: auto">
          <el-checkbox
            v-for="col in spec.columns"
            :key="col.field"
            :model-value="!props.visibleColumns.every(vc => vc.field !== col.field) || props.visibleColumns.some(vc => vc.field === col.field)"
            :label="col.label"
            style="display: block; margin: 4px 0"
            @change="emit('toggle-column', col.field)"
          />
        </div>
      </el-popover>

      <span class="send-list-count">共 {{ rows.length }} 条</span>
    </div>

    <!-- 表格 -->
    <el-table
      :data="tableData"
      border
      size="small"
      style="width: 100%"
      :max-height="600"
      class="send-list-el-table"
    >
      <!-- 序号 -->
      <el-table-column type="index" label="#" width="45" fixed="left" />

      <!-- 动态列 -->
      <el-table-column
        v-for="col in visibleColumns"
        :key="col.field"
        :label="col.label"
        :width="col.width"
        :min-width="col.width ? undefined : 120"
        :align="col.render === 'amount' ? 'right' : undefined"
        :class-name="col.render === 'amount' ? 'is-right' : undefined"
      >
        <template #default="{ row }">
          <!-- 枚举列 → el-select -->
          <template v-if="col.type === 'enum' && col.enum">
            <el-select
              v-model="row[col.field]"
              :disabled="isReadonly"
              placeholder="请选择"
              size="small"
              clearable
              style="width: 100%"
              @change="onCellChange"
            >
              <el-option
                v-for="opt in col.enum"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
          </template>

          <!-- 日期列 → el-date-picker -->
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              v-model="row[col.field]"
              type="date"
              :disabled="isReadonly"
              placeholder="选择日期"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              @change="onCellChange"
            />
          </template>

          <!-- 金额列 → WpAmountInput（千分符 + 两位小数 + 粘贴解析） -->
          <template v-else-if="col.render === 'amount'">
            <WpAmountInput
              :model-value="row[col.field]"
              :disabled="isReadonly"
              size="small"
              @change="(v: number) => { row[col.field] = v; onCellChange() }"
            />
          </template>

          <!-- 普通数值列（利率等，不套金额格式） -->
          <template v-else-if="col.type === 'number'">
            <el-input
              :model-value="row[col.field] != null ? String(row[col.field]) : ''"
              :disabled="isReadonly"
              size="small"
              style="width: 100%"
              @blur="(e: FocusEvent) => {
                const target = e.target as HTMLInputElement
                const val = target?.value
                row[col.field] = val ? Number(val) : null
                onCellChange()
              }"
            />
          </template>

          <!-- 文本列 → el-input -->
          <template v-else>
            <el-input
              v-model="row[col.field]"
              :disabled="isReadonly"
              size="small"
              style="width: 100%"
              @blur="onCellChange"
            />
          </template>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column
        v-if="!isReadonly"
        label="操作"
        width="80"
        fixed="right"
        align="center"
      >
        <template #default="{ row }">
          <el-button
            type="danger"
            size="small"
            text
            @click="emit('remove-row', row._row_id)"
          >
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<style scoped>
.send-list-table-wrapper {
  font-size: 13px;
}
.send-list-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 8px;
}
.send-list-count {
  margin-left: auto;
  color: #909399;
  font-size: 12px;
}
.send-list-el-table :deep(td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}
</style>
