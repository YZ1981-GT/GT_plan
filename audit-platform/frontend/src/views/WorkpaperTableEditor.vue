<template>
  <div class="gt-table-editor gt-fade-in">
    <EditorSharedToolbar
      :wp-code="wpDetail?.wp_code"
      :wp-name="wpDetail?.wp_name"
      :status="wpDetail?.status"
      component-type="table"
      :dirty="dirty"
      :saving="saving"
      @back="goBack"
      @save="onSave"
      @export="onExport"
      @versions="$emit('show-versions')"
      @toggle-panel="$emit('toggle-panel')"
    />

    <div class="gt-table-editor-body" v-loading="loading">
      <!-- 操作栏 -->
      <div class="gt-table-editor-actions">
        <el-input v-model="searchText" placeholder="搜索..." clearable style="width: 240px" size="small" />
        <el-button size="small" type="primary" @click="onAddRow">+ 新增行</el-button>
        <el-button size="small" @click="onImport">📥 导入 Excel</el-button>
        <el-button size="small" danger @click="onDeleteSelected" :disabled="!selectedRows.length">
          🗑️ 删除选中 ({{ selectedRows.length }})
        </el-button>
      </div>

      <!-- 数据表格 -->
      <el-table
        :data="filteredRows"
        border
        stripe
        highlight-current-row
        @selection-change="onSelectionChange"
        style="width: 100%"
        max-height="calc(100vh - 200px)"
        class="gt-table-editor-table"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column type="index" label="#" width="50" />
        <el-table-column
          v-for="col in columns"
          :key="col.key"
          :prop="col.key"
          :label="col.label"
          :width="col.width"
          :min-width="col.minWidth || 120"
          sortable
        >
          <template #default="{ row }">
            <el-input
              v-model="row[col.key]"
              size="small"
              @change="markDirty"
            />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" fixed="right">
          <template #default="{ $index }">
            <el-button size="small" text type="danger" @click="onRemoveRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import EditorSharedToolbar from '@/components/workpaper/EditorSharedToolbar.vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import type { WorkpaperDetail } from '@/services/workpaperApi'

interface TableColumn {
  key: string
  label: string
  width?: number
  minWidth?: number
}

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
}>()

const emit = defineEmits<{
  'show-versions': []
  'toggle-panel': []
  saved: []
}>()

const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const searchText = ref('')
const columns = ref<TableColumn[]>([])
const rows = ref<Record<string, any>[]>([])
const selectedRows = ref<Record<string, any>[]>([])

const filteredRows = computed(() => {
  if (!searchText.value) return rows.value
  const q = searchText.value.toLowerCase()
  return rows.value.filter(r =>
    Object.values(r).some(v => String(v || '').toLowerCase().includes(q))
  )
})

function markDirty() { dirty.value = true }
function goBack() { window.history.back() }

function onSelectionChange(selection: Record<string, any>[]) {
  selectedRows.value = selection
}

function onAddRow() {
  const newRow: Record<string, any> = {}
  for (const col of columns.value) newRow[col.key] = ''
  rows.value.push(newRow)
  markDirty()
}

function onRemoveRow(index: number) {
  rows.value.splice(index, 1)
  markDirty()
}

function onDeleteSelected() {
  const set = new Set(selectedRows.value)
  rows.value = rows.value.filter(r => !set.has(r))
  selectedRows.value = []
  markDirty()
}

function onImport() {
  ElMessage.info('Excel 导入功能开发中')
}

async function loadData() {
  loading.value = true
  try {
    const detail = await httpApi.get(P_wp.detail(props.projectId, props.wpId))
    const parsed = detail?.parsed_data || {}
    columns.value = parsed._columns || [
      { key: 'item', label: '项目' },
      { key: 'description', label: '描述' },
      { key: 'amount', label: '金额' },
      { key: 'remark', label: '备注' },
    ]
    rows.value = parsed._rows || []
  } catch (e: any) {
    handleApiError(e, '加载表格')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    await httpApi.put(P_wp.detail(props.projectId, props.wpId), {
      parsed_data: { _columns: columns.value, _rows: rows.value },
    })
    dirty.value = false
    ElMessage.success('保存成功')
    emit('saved')
  } catch (e: any) {
    handleApiError(e, '保存表格')
  } finally {
    saving.value = false
  }
}

function onExport() {
  ElMessage.info('表格导出功能开发中')
}

watch(() => props.wpId, () => { if (props.wpId) loadData() })
onMounted(() => { if (props.wpId) loadData() })
</script>

<style scoped>
.gt-table-editor { display: flex; flex-direction: column; height: 100%; }
.gt-table-editor-body { flex: 1; overflow-y: auto; padding: 16px; }
.gt-table-editor-actions {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px;
}
.gt-table-editor-table :deep(.el-input__inner) { font-size: var(--gt-font-size-sm); }
</style>
