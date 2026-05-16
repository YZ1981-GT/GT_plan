<!--
  ExcelImportPreviewDialog — 通用 Excel 导入预览弹窗 [R5.3]
  内置：隐藏 file input + xlsx 解析 + 预览表格 + 统计 + 确认追加

  用法：
    <ExcelImportPreviewDialog
      v-model:visible="showImport"
      title="导入子企业信息"
      :expected-columns="['子企业名称','企业代码','核算科目']"
      :sheet-name="'数据填写'"
      :skip-rows="3"
      :skip-example-prefix="'示例'"
      @confirm="onImportConfirm"
    />

  调用 open / selectFile 方法触发文件选择：
    const importRef = ref()
    importRef.value?.selectFile()
-->
<template>
  <el-dialog
    :model-value="visible"
    :title="title || '导入Excel数据'"
    width="720px"
    append-to-body
    @update:model-value="$emit('update:visible', $event)"
    @closed="onClosed"
  >
    <!-- 提示信息 -->
    <el-alert v-if="alertText" type="warning" :closable="false" style="margin-bottom: 12px">
      <template #title><span v-html="alertText"></span></template>
    </el-alert>

    <!-- 列映射校验警告 -->
    <el-alert
      v-if="columnWarning"
      type="error"
      :closable="false"
      style="margin-bottom: 12px"
    >
      <template #title>{{ columnWarning }}</template>
    </el-alert>

    <!-- 统计栏 -->
    <div v-if="parsedRows.length > 0" class="import-stats">
      <span class="stat-item">
        <span class="stat-label">总行数</span>
        <span class="stat-value">{{ parsedRows.length }}</span>
      </span>
      <span class="stat-sep" />
      <span class="stat-item">
        <span class="stat-label">有效行</span>
        <span class="stat-value stat-valid">{{ validCount }}</span>
      </span>
      <span class="stat-sep" />
      <span class="stat-item">
        <span class="stat-label">异常行</span>
        <span class="stat-value" :class="{ 'stat-error': errorCount > 0 }">{{ errorCount }}</span>
      </span>
    </div>

    <!-- 预览表格 -->
    <div v-if="parsedRows.length > 0" class="import-preview">
      <el-table
        :data="parsedRows"
        border
        size="small"
        max-height="350"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="#" width="45" align="center" />
        <el-table-column
          v-for="col in displayColumns"
          :key="col"
          :prop="col"
          :label="col"
          min-width="120"
          show-overflow-tooltip
        >
          <template #default="{ row }">
            <span :class="{ 'cell-error': isCellError(row, col) }">
              {{ row[col] ?? '' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-empty v-else-if="fileSelected" description="未解析到有效数据，请检查文件格式" :image-size="60" />

    <template #footer>
      <el-button @click="$emit('update:visible', false)">取消</el-button>
      <el-button
        type="primary"
        :disabled="parsedRows.length === 0 || (errorCount > 0 && !allowErrorRows)"
        @click="onConfirm"
      >
        确认导入 ({{ validCount }} 条)
      </el-button>
    </template>
  </el-dialog>

  <!-- 隐藏的文件输入 -->
  <input
    ref="fileInputRef"
    type="file"
    accept=".xlsx,.xls"
    style="display: none"
    @change="onFileChange"
  />
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'

/* ── Props ── */
const props = withDefaults(defineProps<{
  /** 弹窗可见性（v-model:visible） */
  visible: boolean
  /** 弹窗标题 */
  title?: string
  /** 期望的列名数组，用于列映射校验 */
  expectedColumns?: string[]
  /** 目标工作表名称，找不到时取最后一个 sheet */
  sheetName?: string
  /** 跳过前 N 行（如分类行+说明行+表头行=3） */
  skipRows?: number
  /** 以此前缀开头的行自动跳过（如"示例"） */
  skipExamplePrefix?: string
  /** 提示文字（支持 HTML） */
  alertText?: string
  /** 是否允许存在异常行时仍可确认导入 */
  allowErrorRows?: boolean
  /** 自定义行校验函数，返回错误字段名数组（空=无错误） */
  validateRow?: (row: Record<string, any>, index: number) => string[]
}>(), {
  title: '导入Excel数据',
  sheetName: '',
  skipRows: 0,
  skipExamplePrefix: '',
  alertText: '',
  allowErrorRows: false,
})

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'confirm', data: Record<string, any>[]): void
}>()

/* ── 内部状态 ── */
const fileInputRef = ref<HTMLInputElement | null>(null)
const parsedRows = ref<Record<string, any>[]>([])
const parsedHeaders = ref<string[]>([])
const rowErrors = ref<Map<number, Set<string>>>(new Map())
const fileSelected = ref(false)
const columnWarning = ref('')

/* ── 计算属性 ── */
const displayColumns = computed(() => {
  // 使用解析到的表头作为列名
  return parsedHeaders.value
})

const errorCount = computed(() => rowErrors.value.size)
const validCount = computed(() => parsedRows.value.length - errorCount.value)

/* ── 公开方法：触发文件选择 ── */
function selectFile() {
  fileInputRef.value?.click()
}
// 别名
const open = selectFile

/* ── 文件选择处理 ── */
async function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  fileSelected.value = true

  try {
    const XLSX = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = XLSX.read(buf, { type: 'array' })

    // 查找目标 sheet
    let targetSheet = ''
    if (props.sheetName) {
      targetSheet = wb.SheetNames.find(n => n === props.sheetName) || ''
    }
    if (!targetSheet) {
      // 取最后一个 sheet（跳过可能的"填写说明"）
      targetSheet = wb.SheetNames[wb.SheetNames.length - 1]
    }

    const ws = wb.Sheets[targetSheet]
    if (!ws) {
      ElMessage.error(`未找到工作表"${props.sheetName || targetSheet}"`)
      return
    }

    const jsonData: any[][] = XLSX.utils.sheet_to_json(ws, { header: 1 })

    if (jsonData.length <= props.skipRows) {
      ElMessage.warning('文件中没有数据行')
      return
    }

    // 表头行 = skipRows 位置的前一行（如 skipRows=3 则表头在第3行即 index=2）
    const headerRowIndex = props.skipRows > 0 ? props.skipRows - 1 : 0
    const headers: string[] = (jsonData[headerRowIndex] || []).map((h: any) => String(h || '').trim())
    parsedHeaders.value = headers.filter(h => h !== '')

    // 列映射校验
    columnWarning.value = ''
    if (props.expectedColumns && props.expectedColumns.length > 0) {
      const missing = props.expectedColumns.filter(c => !headers.includes(c))
      if (missing.length > 0) {
        columnWarning.value = `缺少期望列：${missing.join('、')}。请检查模板是否正确。`
      }
    }

    // 解析数据行
    const rows: Record<string, any>[] = []
    const errors = new Map<number, Set<string>>()
    const dataStartRow = props.skipRows

    for (let i = dataStartRow; i < jsonData.length; i++) {
      const rawRow = jsonData[i]
      if (!rawRow || rawRow.length === 0) continue

      // 跳过空行（第一列为空）
      const firstCell = String(rawRow[0] || '').trim()
      if (!firstCell) continue

      // 跳过示例行
      if (props.skipExamplePrefix && firstCell.startsWith(props.skipExamplePrefix)) continue

      // 构建行对象
      const rowObj: Record<string, any> = {}
      parsedHeaders.value.forEach((header, colIdx) => {
        const val = rawRow[colIdx]
        rowObj[header] = val != null && val !== '' ? val : null
      })

      const rowIndex = rows.length

      // 自定义校验
      if (props.validateRow) {
        const errFields = props.validateRow(rowObj, rowIndex)
        if (errFields.length > 0) {
          errors.set(rowIndex, new Set(errFields))
        }
      }

      rows.push(rowObj)
    }

    parsedRows.value = rows
    rowErrors.value = errors

    // 自动打开弹窗
    if (!props.visible) {
      emit('update:visible', true)
    }
  } catch (err: any) {
    ElMessage.error('文件解析失败：' + (err.message || '格式错误'))
  } finally {
    // 重置 input 以便重复选择同一文件
    if (fileInputRef.value) fileInputRef.value.value = ''
  }
}

/* ── 行样式 ── */
function rowClassName({ rowIndex }: { row: any; rowIndex: number }) {
  return rowErrors.value.has(rowIndex) ? 'import-row-error' : ''
}

/* ── 单元格错误判断 ── */
function isCellError(row: Record<string, any>, col: string): boolean {
  const rowIndex = parsedRows.value.indexOf(row)
  return rowErrors.value.get(rowIndex)?.has(col) ?? false
}

/* ── 确认导入 ── */
function onConfirm() {
  const data = props.allowErrorRows
    ? parsedRows.value
    : parsedRows.value.filter((_, i) => !rowErrors.value.has(i))
  emit('confirm', data)
  emit('update:visible', false)
}

/* ── 弹窗关闭时重置 ── */
function onClosed() {
  parsedRows.value = []
  parsedHeaders.value = []
  rowErrors.value = new Map()
  columnWarning.value = ''
  fileSelected.value = false
}

/* ── 暴露方法 ── */
defineExpose({ selectFile, open })
</script>

<style scoped>
.import-stats {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  margin-bottom: 12px;
  background: var(--gt-bg-subtle);
  border-radius: 6px;
  font-size: var(--gt-font-size-sm);
}
.stat-item {
  display: flex;
  align-items: center;
  gap: 6px;
}
.stat-label {
  color: var(--gt-color-info);
}
.stat-value {
  font-weight: 600;
  color: var(--gt-color-text-primary);
}
.stat-valid {
  color: var(--gt-color-success);
}
.stat-error {
  color: var(--gt-color-coral);
}
.stat-sep {
  width: 1px;
  height: 16px;
  background: var(--gt-color-border);
}
.import-preview {
  margin-bottom: 8px;
}
.cell-error {
  color: var(--gt-color-coral);
  font-weight: 600;
}
:deep(.import-row-error) {
  background-color: var(--gt-bg-danger) !important;
}
:deep(.import-row-error:hover > td) {
  background-color: var(--gt-color-coral-light) !important;
}
</style>
