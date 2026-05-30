<template>
  <el-dialog
    v-model="visible"
    title="📥 导入填写结果"
    width="680px"
    :close-on-click-modal="false"
    @close="handleClose"
  >
    <!-- Step 1: Upload -->
    <div v-if="step === 1">
      <el-upload
        ref="uploadRef"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx"
        :on-change="handleFileChange"
      >
        <el-icon style="font-size: 48px; color: #409eff"><UploadFilled /></el-icon>
        <div style="margin-top: 8px">将 xlsx 文件拖到此处，或点击上传</div>
        <template #tip>
          <div style="color: #909399; font-size: 12px; margin-top: 4px">
            仅支持由本系统导出的底稿填写模板
          </div>
        </template>
      </el-upload>
    </div>

    <!-- Step 2: Validating -->
    <div v-else-if="step === 2" style="text-align: center; padding: 32px 0">
      <el-icon :size="32" class="is-loading"><Loading /></el-icon>
      <p style="margin-top: 12px; color: #606266">正在校验文件...</p>
    </div>

    <!-- Step 3: Diff Preview -->
    <div v-else-if="step === 3">
      <el-alert
        v-if="validationErrors.length"
        type="error"
        :closable="false"
        style="margin-bottom: 12px"
      >
        <template #title>
          <span>校验失败</span>
        </template>
        <ul style="margin: 4px 0 0 16px; padding: 0">
          <li v-for="(err, i) in validationErrors" :key="i">{{ err }}</li>
        </ul>
      </el-alert>

      <template v-if="!validationErrors.length">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
          <el-descriptions-item label="匹配工作表">{{ summary.matched }}</el-descriptions-item>
          <el-descriptions-item label="仅导入文件">{{ summary.import_only }}</el-descriptions-item>
          <el-descriptions-item label="仅系统">{{ summary.system_only }}</el-descriptions-item>
          <el-descriptions-item label="变更单元格">{{ summary.total_cell_diffs }}</el-descriptions-item>
        </el-descriptions>

        <el-table :data="diffList" max-height="300" border size="small">
          <el-table-column prop="sheet_name" label="工作表" width="160" />
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="statusTagType(row.status)" size="small">
                {{ statusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="diff_count" label="变更数" width="80" />
        </el-table>

        <el-form-item label="冲突策略" style="margin-top: 16px">
          <el-radio-group v-model="strategy">
            <el-radio value="overwrite">覆盖（导入版本优先）</el-radio>
            <el-radio value="keep_system">保留系统版本</el-radio>
            <el-radio value="merge">合并（仅导入变更的可编辑单元格）</el-radio>
          </el-radio-group>
        </el-form-item>

        <!-- Cell-level selection for merge strategy -->
        <template v-if="strategy === 'merge'">
          <div
            v-for="sheet in diffList.filter(d => d.diff_count > 0)"
            :key="sheet.sheet_name"
            style="margin-top: 12px"
          >
            <div style="display: flex; align-items: center; gap: 8px; margin-bottom: 4px">
              <el-checkbox
                :model-value="isSheetAllSelected(sheet.sheet_name)"
                :indeterminate="isSheetIndeterminate(sheet.sheet_name)"
                @change="(val: any) => toggleSheetAll(sheet.sheet_name, !!val)"
              >
                {{ sheet.sheet_name }} ({{ selectedCount(sheet.sheet_name) }}/{{ sheet.diff_count }})
              </el-checkbox>
              <el-button size="small" link type="primary" @click="toggleSheetAll(sheet.sheet_name, true)">全选</el-button>
              <el-button size="small" link type="info" @click="toggleSheetAll(sheet.sheet_name, false)">取消全选</el-button>
            </div>
            <el-table :data="getSheetCellDiffs(sheet.sheet_name)" size="small" max-height="200" border>
              <el-table-column width="40">
                <template #default="{ row }">
                  <el-checkbox
                    :model-value="isCellSelected(sheet.sheet_name, row.cell)"
                    @change="(val: any) => toggleCell(sheet.sheet_name, row.cell, !!val)"
                  />
                </template>
              </el-table-column>
              <el-table-column prop="cell" label="位置" width="80" />
              <el-table-column prop="local" label="系统值" />
              <el-table-column label="" width="30">
                <template #default>→</template>
              </el-table-column>
              <el-table-column prop="imported" label="导入值" />
            </el-table>
          </div>
        </template>
      </template>
    </div>

    <!-- Step 4: Importing -->
    <div v-else-if="step === 4" style="text-align: center; padding: 32px 0">
      <el-progress :percentage="importProgress" :stroke-width="8" style="width: 80%; margin: 0 auto" />
      <p style="margin-top: 12px; color: #606266">正在导入...</p>
    </div>

    <!-- Step 5: Done -->
    <div v-else-if="step === 5" style="text-align: center; padding: 32px 0">
      <el-result icon="success" title="导入完成">
        <template #sub-title>
          <p>导入 {{ importResultData.sheets_imported }} 个工作表，变更 {{ importResultData.cells_changed }} 个单元格</p>
        </template>
      </el-result>
    </div>

    <template #footer>
      <el-button @click="handleClose">{{ step === 5 ? '关闭' : '取消' }}</el-button>
      <el-button
        v-if="step === 1"
        type="primary"
        :disabled="!selectedFile"
        @click="handleValidate"
      >
        下一步：校验
      </el-button>
      <el-button
        v-if="step === 3 && !validationErrors.length"
        type="primary"
        @click="handleApply"
      >
        确认导入
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { UploadFilled, Loading } from '@element-plus/icons-vue'
import { apiProxy } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import type { UploadFile } from 'element-plus'

interface CellDiff {
  cell: string
  local: string
  imported: string
}

interface SheetDiff {
  sheet_name: string
  status: string
  diff_count: number
  cells?: CellDiff[]
}

interface Props {
  modelValue: boolean
  wpId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  'imported': []
}>()

const visible = ref(props.modelValue)
const step = ref(1)
const selectedFile = ref<File | null>(null)
const validationErrors = ref<string[]>([])
const diffList = ref<SheetDiff[]>([])
const summary = ref({ matched: 0, import_only: 0, system_only: 0, total_cell_diffs: 0 })
const strategy = ref('overwrite')
const importProgress = ref(0)
const importResultData = ref({ sheets_imported: 0, cells_changed: 0 })

// Cell-level selection state for merge strategy
const selectedMergeCells = ref<Record<string, string[]>>({})

function handleFileChange(file: UploadFile) {
  selectedFile.value = file.raw || null
}

function handleClose() {
  step.value = 1
  selectedFile.value = null
  validationErrors.value = []
  diffList.value = []
  selectedMergeCells.value = {}
  emit('update:modelValue', false)
}

async function handleValidate() {
  if (!selectedFile.value) return
  step.value = 2

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    const result = await apiProxy.post(
      `/api/workpapers/${props.wpId}/offline/import-preview`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ) as Record<string, unknown>

    const validation = result.validation as Record<string, unknown>
    if (!validation?.valid) {
      validationErrors.value = (validation?.errors as string[]) || ['校验失败']
      step.value = 3
      return
    }

    diffList.value = ((result.diffs as any[]) || []).map((d: any) => ({
      sheet_name: d.sheet_name,
      status: d.status,
      diff_count: d.diff_count || 0,
      cells: (d.diffs || []).map((c: any) => ({
        cell: c.cell,
        local: c.local ?? '—',
        imported: c.imported ?? '—',
      })),
    }))
    summary.value = (result.summary as typeof summary.value) || summary.value
    initMergeCellSelection()
    step.value = 3
  } catch (e: unknown) {
    validationErrors.value = ['请求失败: ' + (e instanceof Error ? e.message : '未知错误')]
    step.value = 3
  }
}

async function handleApply() {
  if (!selectedFile.value) return
  step.value = 4
  importProgress.value = 30

  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    formData.append('strategy', strategy.value)
    if (strategy.value === 'merge') {
      formData.append('merge_cells', JSON.stringify(selectedMergeCells.value))
    } else {
      formData.append('merge_cells', '{}')
    }

    importProgress.value = 60

    const result = await apiProxy.post(
      `/api/workpapers/${props.wpId}/offline/import-apply`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    ) as Record<string, unknown>

    importProgress.value = 100
    importResultData.value = {
      sheets_imported: (result.sheets_imported as number) || 0,
      cells_changed: (result.cells_changed as number) || 0,
    }
    step.value = 5
    emit('imported')
    ElMessage.success('导入完成')
  } catch (e: unknown) {
    handleApiError(e, '导入')
    step.value = 3
  }
}

// --- Merge cell selection helpers ---

function initMergeCellSelection() {
  const selection: Record<string, string[]> = {}
  for (const sheet of diffList.value) {
    if (sheet.diff_count > 0 && sheet.cells?.length) {
      selection[sheet.sheet_name] = sheet.cells.map(c => c.cell)
    }
  }
  selectedMergeCells.value = selection
}

function getSheetCellDiffs(sheetName: string): CellDiff[] {
  const sheet = diffList.value.find(d => d.sheet_name === sheetName)
  return sheet?.cells || []
}

function isCellSelected(sheetName: string, cellKey: string): boolean {
  return selectedMergeCells.value[sheetName]?.includes(cellKey) ?? false
}

function isSheetAllSelected(sheetName: string): boolean {
  const sheet = diffList.value.find(d => d.sheet_name === sheetName)
  if (!sheet?.cells?.length) return false
  const selected = selectedMergeCells.value[sheetName] || []
  return selected.length === sheet.cells.length
}

function isSheetIndeterminate(sheetName: string): boolean {
  const sheet = diffList.value.find(d => d.sheet_name === sheetName)
  if (!sheet?.cells?.length) return false
  const selected = selectedMergeCells.value[sheetName] || []
  return selected.length > 0 && selected.length < sheet.cells.length
}

function selectedCount(sheetName: string): number {
  return selectedMergeCells.value[sheetName]?.length ?? 0
}

function toggleCell(sheetName: string, cellKey: string, checked: boolean) {
  const current = selectedMergeCells.value[sheetName] || []
  if (checked) {
    if (!current.includes(cellKey)) {
      selectedMergeCells.value[sheetName] = [...current, cellKey]
    }
  } else {
    selectedMergeCells.value[sheetName] = current.filter(k => k !== cellKey)
  }
}

function toggleSheetAll(sheetName: string, selectAll: boolean) {
  const sheet = diffList.value.find(d => d.sheet_name === sheetName)
  if (!sheet?.cells?.length) return
  if (selectAll) {
    selectedMergeCells.value[sheetName] = sheet.cells.map(c => c.cell)
  } else {
    selectedMergeCells.value[sheetName] = []
  }
}

function statusTagType(status: string) {
  if (status === 'matched') return 'success'
  if (status === 'import_only') return 'warning'
  return 'info'
}

function statusLabel(status: string) {
  if (status === 'matched') return '匹配'
  if (status === 'import_only') return '仅导入'
  return '仅系统'
}

watch(() => props.modelValue, (val) => { visible.value = val })
watch(visible, (val) => { if (!val) emit('update:modelValue', false) })
</script>
