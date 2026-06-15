<!--
  WorkpaperHtmlTable — 统一 HTML 底稿渲染框架组件

  配置驱动渲染程序表/核查表/复核表：致同标准表头 + 列定义 + 行数据。
  列类型：text / tristate(是/否/不适用) / editable / indexLink / computed
  行内编辑失焦保存到 FieldOverrideService（POST /api/workpapers/field-overrides）。
  统一导出 Excel；GT 紫令牌 + gt-compact-table 紧凑样式。

  Foundation Kit Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6
-->
<template>
  <div class="wp-html-table">
    <!-- ── 致同标准表头 ── -->
    <WorkpaperStandardHeader v-if="header" :header="header" />

    <!-- ── 工具栏 ── -->
    <div class="wp-html-table__toolbar">
      <span class="wp-html-table__title">{{ title }}</span>
      <el-button
        size="small"
        :icon="Download"
        @click="onExportExcel"
      >导出 Excel</el-button>
    </div>

    <!-- ── 表格主体 ── -->
    <el-table
      :data="rows"
      border
      class="gt-compact-table wp-html-table__el"
      :row-key="rowKey"
    >
      <el-table-column
        v-for="col in columns"
        :key="col.key"
        :label="col.label"
        :width="col.width"
        :min-width="col.minWidth"
        :align="col.align || 'left'"
      >
        <template #default="{ row }">
          <!-- text -->
          <span v-if="col.type === 'text'">{{ displayValue(row, col) }}</span>

          <!-- computed (只读自动计算值) -->
          <span v-else-if="col.type === 'computed'" class="wp-html-table__computed">
            {{ displayValue(row, col) }}
          </span>

          <!-- tristate (是/否/不适用) -->
          <el-select
            v-else-if="col.type === 'tristate'"
            :model-value="cellValue(row, col)"
            size="small"
            :disabled="readonly"
            placeholder="—"
            @update:model-value="(v: any) => onTristateChange(row, col, v)"
          >
            <el-option label="是" value="yes" />
            <el-option label="否" value="no" />
            <el-option label="不适用" value="na" />
          </el-select>

          <!-- editable (可编辑文本，失焦保存) -->
          <el-input
            v-else-if="col.type === 'editable'"
            :model-value="cellValue(row, col)"
            size="small"
            :disabled="readonly"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 4 }"
            @update:model-value="(v: any) => setLocal(row, col, v)"
            @blur="onEditableBlur(row, col)"
          />

          <!-- indexLink (索引号可点击跳转) -->
          <span v-else-if="col.type === 'indexLink'" class="wp-html-table__index-links">
            <template v-for="(ref, i) in parseRefs(displayValue(row, col))" :key="i">
              <el-link
                v-if="ref.entry"
                type="primary"
                :underline="false"
                @click="onIndexClick(ref.code)"
              >{{ ref.code }}</el-link>
              <span v-else class="wp-html-table__index-missing">{{ ref.code }}</span>
              <span v-if="i < parseRefs(displayValue(row, col)).length - 1">、</span>
            </template>
          </span>

          <!-- fallback -->
          <span v-else>{{ displayValue(row, col) }}</span>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { useExcelIO } from '@/composables/useExcelIO'
import { useWorkpaperNavigation } from '@/composables/useWorkpaperNavigation'
import { useWorkpaperRegistry } from '@/composables/useWorkpaperRegistry'
import WorkpaperStandardHeader from './WorkpaperStandardHeader.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export type ColumnType = 'text' | 'tristate' | 'editable' | 'indexLink' | 'computed'

export interface ColumnDef {
  /** 数据字段名 */
  key: string
  /** 列标题 */
  label: string
  /** 列类型 */
  type: ColumnType
  width?: number | string
  minWidth?: number | string
  align?: 'left' | 'center' | 'right'
  /** 该列是否绑定字段覆盖存储（editable/tristate 默认 true） */
  override?: boolean
}

export interface StandardHeader {
  entityName?: string
  wpName?: string
  indexNo?: string
  preparer?: string
  reviewer?: string
  preparedDate?: string
  reviewedDate?: string
  period?: string
}

export interface RowData {
  /** 行唯一键（item_key） */
  _key: string
  [field: string]: any
}

const props = withDefaults(
  defineProps<{
    title?: string
    header?: StandardHeader | null
    columns: ColumnDef[]
    rows: RowData[]
    /** 字段覆盖存储 scope（如 'procedure_table:A1'） */
    scope: string
    projectId: string
    year: number
    readonly?: boolean
    rowKey?: string
  }>(),
  {
    title: '',
    header: null,
    readonly: false,
    rowKey: '_key',
  },
)

const emit = defineEmits<{
  'field-change': [payload: { itemKey: string; field: string; value: any }]
}>()

// ─── 本地覆盖值缓存 {itemKey: {field: value}} ──────────────────────────────────

const localOverrides = ref<Record<string, Record<string, any>>>({})

const { exportData } = useExcelIO()
const { parseIndexRefs, navigateToWorkpaper } = useWorkpaperNavigation()
const registry = useWorkpaperRegistry()

// ─── 数据访问 ──────────────────────────────────────────────────────────────────

/** 取单元格原始值（覆盖优先于行内自动值） */
function cellValue(row: RowData, col: ColumnDef): any {
  const ov = localOverrides.value[row._key]?.[col.key]
  if (ov !== undefined && ov !== null) return ov
  return row[col.key]
}

/** 显示值（用于 text/computed/indexLink） */
function displayValue(row: RowData, col: ColumnDef): any {
  const v = cellValue(row, col)
  return v == null ? '' : v
}

/** 设置本地值（不立即保存） */
function setLocal(row: RowData, col: ColumnDef, value: any) {
  if (!localOverrides.value[row._key]) {
    localOverrides.value[row._key] = {}
  }
  localOverrides.value[row._key][col.key] = value
}

// ─── 保存到字段覆盖存储 ────────────────────────────────────────────────────────

async function saveField(itemKey: string, field: string, value: any) {
  try {
    await api.post('/api/workpapers/field-overrides', {
      project_id: props.projectId,
      year: props.year,
      scope: props.scope,
      item_key: itemKey,
      field,
      value,
    })
    emit('field-change', { itemKey, field, value })
  } catch {
    ElMessage.error('保存失败')
  }
}

function onTristateChange(row: RowData, col: ColumnDef, value: any) {
  setLocal(row, col, value)
  if (props.readonly) return
  void saveField(row._key, col.key, value)
}

function onEditableBlur(row: RowData, col: ColumnDef) {
  if (props.readonly) return
  const value = cellValue(row, col)
  void saveField(row._key, col.key, value)
}

// ─── 索引跳转 ──────────────────────────────────────────────────────────────────

function parseRefs(refStr: any) {
  return parseIndexRefs(String(refStr ?? ''))
}

function onIndexClick(code: string) {
  void navigateToWorkpaper(code, props.projectId, props.year)
}

// ─── 导出 Excel ────────────────────────────────────────────────────────────────

async function onExportExcel() {
  const excelColumns = props.columns.map((c) => ({ key: c.key, header: c.label }))
  const data = props.rows.map((row) => {
    const rec: Record<string, any> = {}
    for (const col of props.columns) {
      const v = cellValue(row, col)
      if (col.type === 'tristate') {
        rec[col.key] = v === 'yes' ? '是' : v === 'no' ? '否' : v === 'na' ? '不适用' : ''
      } else {
        rec[col.key] = v ?? ''
      }
    }
    return rec
  })

  // 致同标准表头行（导出时前置）
  const headerRows: Record<string, any>[] = []
  const h = props.header
  if (h) {
    const firstKey = props.columns[0]?.key || ''
    headerRows.push({ [firstKey]: '致同会计师事务所' })
    headerRows.push({ [firstKey]: h.wpName || props.title || '' })
    headerRows.push({
      [firstKey]: `被审计单位：${h.entityName || ''}`,
      [props.columns[2]?.key || '']: `编制人：${h.preparer || ''}`,
      [props.columns[4]?.key || '']: `索引号：${h.indexNo || ''}`,
    })
    headerRows.push({}) // 空行分隔
  }

  await exportData({
    data: [...headerRows, ...data],
    columns: excelColumns,
    sheetName: props.title || '底稿',
    fileName: `${h?.indexNo || props.title || '底稿'}.xlsx`,
  })
}

// ─── 初始化：加载注册表 + 已有覆盖值 ──────────────────────────────────────────────

async function loadOverrides() {
  try {
    const batch = await api.get<Record<string, Record<string, any>>>(
      '/api/workpapers/field-overrides',
      { params: { project_id: props.projectId, year: props.year, scope: props.scope } },
    )
    localOverrides.value = batch || {}
  } catch {
    // 无覆盖值时保持空
  }
}

onMounted(async () => {
  await registry.load()
  await loadOverrides()
})

defineExpose({ onExportExcel, loadOverrides, cellValue })
</script>

<style scoped>
.wp-html-table {
  --gt-purple: var(--gt-color-primary, #4b2d77);
  --gt-purple-light: var(--gt-color-primary-bg, #f4f0fa);
  --gt-purple-border: var(--gt-color-primary-lighter, #d8b8ee);
}

.wp-html-table__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 0;
}

.wp-html-table__title {
  font-weight: 600;
  color: var(--gt-purple);
  font-size: 14px;
}

.wp-html-table__computed {
  color: #606266;
  font-style: italic;
}

.wp-html-table__index-links :deep(.el-link) {
  margin: 0 1px;
}

.wp-html-table__index-missing {
  color: #c0c4cc;
  text-decoration: line-through;
}

.wp-html-table__el :deep(.el-table__header th) {
  background: var(--gt-purple-light);
  color: var(--gt-purple);
  font-weight: 600;
}
</style>
