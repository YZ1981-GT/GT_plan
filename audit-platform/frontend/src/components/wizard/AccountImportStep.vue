<template>
  <div class="gt-account-import-step">
    <h2 class="step-title">数据导入</h2>
    <p class="step-desc">上传 Excel/CSV 文件（科目表、序时账、余额表、辅助账等），系统自动识别列并预览</p>

    <!-- Phase 1: Upload -->
    <div v-if="phase === 'upload'" class="upload-section">
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        :auto-upload="false"
        :limit="1"
        accept=".xlsx,.xls,.csv"
        :on-change="onFileChange"
        :on-exceed="onExceed"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .xlsx / .xls / .csv 格式，可上传科目表、序时账、余额表、辅助账等
          </div>
        </template>
      </el-upload>

      <el-button
        type="primary"
        :loading="previewing"
        :disabled="!selectedFile"
        style="margin-top: 16px"
        @click="handlePreview"
      >
        上传预览
      </el-button>
    </div>

    <!-- Phase 2: Preview + Mapping -->
    <div v-if="phase === 'preview' && previewSheets.length" class="preview-section">
      <!-- Sheet tabs (if multiple sheets) -->
      <el-tabs
        v-if="previewSheets.length > 1"
        v-model="activeSheetIdx"
        type="card"
        class="sheet-tabs"
        @tab-change="(idx: any) => onSheetChange(Number(idx))"
      >
        <el-tab-pane
          v-for="(sheet, idx) in previewSheets"
          :key="idx"
          :label="sheet.sheet_name"
          :name="idx"
        />
      </el-tabs>

      <!-- File type detection -->
      <div v-if="activeSheet" class="file-type-bar">
        <el-tag :type="fileTypeTagType" size="large">
          检测到：{{ fileTypeLabel }}
        </el-tag>
        <span class="row-count">
          {{ activeSheet.sheet_name }} — 共 {{ activeSheet.total_rows }} 行数据，预览前 {{ activeSheet.rows.length }} 行（已跳过前2行）
        </span>
      </div>

      <!-- Column mapping + preview table -->
      <div v-if="activeSheet" class="preview-table-wrapper">
        <el-table
          :data="activeSheet.rows"
          border
          stripe
          size="small"
          max-height="480"
          style="width: 100%"
        >
          <el-table-column
            v-for="header in activeSheet.headers"
            :key="header"
            :prop="header"
            min-width="160"
          >
            <template #header>
              <div class="column-mapping-header">
                <el-select
                  v-model="columnMapping[header]"
                  size="small"
                  placeholder="(忽略)"
                  clearable
                  class="mapping-select"
                >
                  <el-option-group
                    v-for="group in FIELD_GROUPS"
                    :key="group.label"
                    :label="group.label"
                  >
                    <el-option
                      v-for="opt in group.options"
                      :key="opt.value"
                      :label="opt.label"
                      :value="opt.value"
                      :disabled="isFieldUsed(opt.value, header)"
                    />
                  </el-option-group>
                </el-select>
                <div class="header-label">
                  <el-icon v-if="columnMapping[header]" class="matched-icon"><CircleCheckFilled /></el-icon>
                  <el-icon v-else class="unmatched-icon"><WarningFilled /></el-icon>
                  <span>{{ header }}</span>
                </div>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- Action buttons -->
      <div class="preview-actions">
        <el-button @click="handleReupload">重新上传</el-button>
        <el-button type="primary" :loading="importing" @click="handleImport">
          确认导入
        </el-button>
      </div>
    </div>

    <!-- Phase 3: Import Result -->
    <div v-if="phase === 'result' && importResult" class="result-section">
      <el-alert
        :title="`成功导入 ${importResult.total_imported} 个科目`"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      />

      <!-- Category Summary -->
      <div class="category-summary">
        <el-tag
          v-for="(count, cat) in importResult.by_category"
          :key="cat"
          :type="categoryTagType(cat as string)"
          size="large"
          style="margin-right: 8px; margin-bottom: 8px"
        >
          {{ categoryLabel(cat as string) }}: {{ count }}
        </el-tag>
      </div>

      <!-- Errors -->
      <el-alert
        v-if="importResult.errors.length > 0"
        title="导入警告"
        type="warning"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #default>
          <ul class="error-list">
            <li v-for="(err, idx) in importResult.errors" :key="idx">{{ err }}</li>
          </ul>
        </template>
      </el-alert>

      <el-button @click="handleReupload" style="margin-bottom: 16px">重新上传</el-button>
    </div>

    <!-- Client Chart Tree (shown after import) -->
    <div v-if="clientTree && Object.keys(clientTree).length > 0" class="tree-section">
      <h3 class="section-title">客户科目表</h3>
      <div v-for="(nodes, cat) in clientTree" :key="cat" class="category-group">
        <div class="category-header">
          <el-tag :type="categoryTagType(cat)" size="small">{{ categoryLabel(cat) }}</el-tag>
          <span class="category-count">{{ countNodes(nodes) }} 个科目</span>
        </div>
        <el-tree
          :data="toElTreeData(nodes)"
          :props="treeProps"
          default-expand-all
          :expand-on-click-node="false"
          class="account-tree"
        >
          <template #default="{ data }">
            <span class="tree-node">
              <span class="node-code">{{ data.account_code }}</span>
              <span class="node-name">{{ data.account_name }}</span>
              <el-tag size="small" :type="data.direction === 'debit' ? 'primary' : 'warning'">
                {{ data.direction === 'debit' ? '借' : '贷' }}
              </el-tag>
            </span>
          </template>
        </el-tree>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { UploadFilled, CircleCheckFilled, WarningFilled } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import http from '@/utils/http'
import { useWizardStore } from '@/stores/wizard'

const wizardStore = useWizardStore()
const uploadRef = ref<UploadInstance>()
const selectedFile = ref<File | null>(null)
const previewing = ref(false)
const importing = ref(false)

type Phase = 'upload' | 'preview' | 'result'
const phase = ref<Phase>('upload')

// --- Field mapping options grouped by category ---
const FIELD_GROUPS = [
  {
    label: '科目信息',
    options: [
      { value: 'account_code', label: 'account_code (科目编码)' },
      { value: 'account_name', label: 'account_name (科目名称)' },
      { value: 'direction', label: 'direction (借贷方向)' },
      { value: 'parent_code', label: 'parent_code (上级编码)' },
    ],
  },
  {
    label: '金额信息',
    options: [
      { value: 'debit_amount', label: 'debit_amount (借方金额)' },
      { value: 'credit_amount', label: 'credit_amount (贷方金额)' },
      { value: 'opening_balance', label: 'opening_balance (期初余额)' },
      { value: 'closing_balance', label: 'closing_balance (期末余额)' },
    ],
  },
  {
    label: '凭证信息',
    options: [
      { value: 'voucher_date', label: 'voucher_date (凭证日期)' },
      { value: 'voucher_no', label: 'voucher_no (凭证号)' },
      { value: 'summary', label: 'summary (摘要)' },
      { value: 'counterpart_account', label: 'counterpart_account (对方科目)' },
      { value: 'preparer', label: 'preparer (制单人)' },
    ],
  },
  {
    label: '辅助核算',
    options: [
      { value: 'aux_type', label: 'aux_type (辅助类型)' },
      { value: 'aux_code', label: 'aux_code (辅助编码)' },
      { value: 'aux_name', label: 'aux_name (辅助名称)' },
    ],
  },
]

// --- Preview data ---
interface SheetPreview {
  sheet_name: string
  headers: string[]
  rows: Record<string, string>[]
  total_rows: number
  column_mapping: Record<string, string | null>
  file_type_guess: string
}

interface PreviewResponse {
  sheets: SheetPreview[]
  active_sheet: number
}

const previewSheets = ref<SheetPreview[]>([])
const activeSheetIdx = ref(0)
const columnMapping = reactive<Record<string, string | null>>({})

// --- Import result ---
interface AccountImportResult {
  total_imported: number
  by_category: Record<string, number>
  errors: string[]
}

interface AccountTreeNode {
  account_code: string
  account_name: string
  direction: string
  level: number
  category: string
  parent_code: string | null
  children: AccountTreeNode[]
}

const importResult = ref<AccountImportResult | null>(null)
const clientTree = ref<Record<string, AccountTreeNode[]> | null>(null)

const treeProps = { children: 'children', label: 'account_name' }

const FILE_TYPE_LABELS: Record<string, string> = {
  account_chart: '科目表文件',
  ledger: '序时账文件',
  balance: '余额表文件',
  aux_balance: '辅助账文件',
  unknown: '未识别类型',
}

const FILE_TYPE_TAG: Record<string, string> = {
  account_chart: 'success',
  ledger: 'primary',
  balance: 'warning',
  aux_balance: '',
  unknown: 'info',
}

const CATEGORY_LABELS: Record<string, string> = {
  asset: '资产类', liability: '负债类', equity: '权益类',
  revenue: '收入类', expense: '费用类',
}

const CATEGORY_TAG_TYPES: Record<string, string> = {
  asset: '', liability: 'warning', equity: 'success',
  revenue: 'primary', expense: 'danger',
}

const fileTypeLabel = ref('')
const fileTypeTagType = ref('')

// Computed: current active sheet data
const activeSheet = computed(() => previewSheets.value[activeSheetIdx.value] || null)

function onSheetChange(idx: number) {
  activeSheetIdx.value = idx
  // Update column mapping for the new sheet
  for (const key of Object.keys(columnMapping)) delete columnMapping[key]
  const sheet = previewSheets.value[idx]
  if (sheet) {
    for (const [h, v] of Object.entries(sheet.column_mapping)) {
      columnMapping[h] = v
    }
    fileTypeLabel.value = FILE_TYPE_LABELS[sheet.file_type_guess] || '未识别类型'
    fileTypeTagType.value = FILE_TYPE_TAG[sheet.file_type_guess] || 'info'
  }
}

function categoryLabel(cat: string): string { return CATEGORY_LABELS[cat] || cat }
function categoryTagType(cat: string): string { return CATEGORY_TAG_TYPES[cat] || '' }

function countNodes(nodes: AccountTreeNode[]): number {
  let count = 0
  for (const n of nodes) {
    count += 1
    if (n.children) count += countNodes(n.children)
  }
  return count
}

function toElTreeData(nodes: AccountTreeNode[]): Record<string, unknown>[] {
  return nodes.map((n) => ({
    account_code: n.account_code,
    account_name: n.account_name,
    direction: n.direction,
    level: n.level,
    children: n.children ? toElTreeData(n.children) : [],
  }))
}

function isFieldUsed(fieldValue: string, currentHeader: string): boolean {
  for (const [h, v] of Object.entries(columnMapping)) {
    if (h !== currentHeader && v === fieldValue) return true
  }
  return false
}

function onFileChange(file: UploadFile) {
  selectedFile.value = file.raw || null
}

function onExceed() {
  ElMessage.warning('只能上传一个文件，请先移除已选文件')
}

async function handlePreview() {
  if (!selectedFile.value || !wizardStore.projectId) return
  previewing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)
    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/account-chart/preview?skip_rows=2`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const result: PreviewResponse = data.data ?? data
    previewSheets.value = result.sheets || []

    if (previewSheets.value.length > 0) {
      activeSheetIdx.value = 0
      onSheetChange(0)
    }

    phase.value = 'preview'
  } catch {
    // Error handled by http interceptor
  } finally {
    previewing.value = false
  }
}

function handleReupload() {
  phase.value = 'upload'
  previewSheets.value = []
  activeSheetIdx.value = 0
  importResult.value = null
  clientTree.value = null
  selectedFile.value = null
  for (const key of Object.keys(columnMapping)) delete columnMapping[key]
  uploadRef.value?.clearFiles()
}

async function handleImport() {
  if (!selectedFile.value || !wizardStore.projectId) return
  importing.value = true
  try {
    const formData = new FormData()
    formData.append('file', selectedFile.value)

    // Build clean mapping (exclude null / empty)
    const cleanMapping: Record<string, string> = {}
    for (const [h, v] of Object.entries(columnMapping)) {
      if (v) cleanMapping[h] = v
    }
    formData.append('column_mapping', JSON.stringify(cleanMapping))

    const { data } = await http.post(
      `/api/projects/${wizardStore.projectId}/account-chart/import`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' } },
    )
    const result: AccountImportResult = data.data ?? data
    importResult.value = result
    ElMessage.success(`成功导入 ${result.total_imported} 个科目`)

    await wizardStore.saveStep('account_import', {
      total_imported: result.total_imported,
      by_category: result.by_category,
    })

    phase.value = 'result'
    await loadClientTree()
  } catch {
    // Error handled by http interceptor
  } finally {
    importing.value = false
  }
}

async function loadClientTree() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/client`,
    )
    clientTree.value = data.data ?? data
  } catch {
    // Silently fail
  }
}

onMounted(async () => {
  if (wizardStore.projectId && wizardStore.isStepCompleted('account_import')) {
    const saved = wizardStore.stepData.account_import as Record<string, unknown> | undefined
    if (saved) {
      importResult.value = {
        total_imported: (saved.total_imported as number) || 0,
        by_category: (saved.by_category as Record<string, number>) || {},
        errors: [],
      }
      phase.value = 'result'
    }
    await loadClientTree()
  }
})
</script>

<style scoped>
.gt-account-import-step {
  max-width: 960px;
  margin: 0 auto;
}

.step-title {
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-1);
  font-size: 20px;
}

.step-desc {
  color: #999;
  margin-bottom: var(--gt-space-6);
  font-size: 14px;
}

.upload-section {
  margin-bottom: var(--gt-space-6);
}

.upload-area {
  width: 100%;
}

/* Preview phase */
.sheet-tabs { margin-bottom: var(--gt-space-3); }
.file-type-bar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: var(--gt-space-4);
}

.row-count {
  color: #999;
  font-size: 13px;
}

.preview-table-wrapper {
  margin-bottom: var(--gt-space-4);
  border: 1px solid #eee;
  border-radius: var(--gt-radius-md);
  overflow: hidden;
}

.column-mapping-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.mapping-select {
  width: 100%;
}

.header-label {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #666;
}

.matched-icon {
  color: #67c23a;
  font-size: 14px;
}

.unmatched-icon {
  color: #e6a23c;
  font-size: 14px;
}

.preview-actions {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

/* Result phase */
.result-section {
  margin-bottom: var(--gt-space-6);
}

.category-summary {
  margin-bottom: var(--gt-space-4);
}

.error-list {
  margin: 0;
  padding-left: 20px;
}

.tree-section {
  margin-top: var(--gt-space-4);
}

.section-title {
  font-size: 16px;
  color: var(--gt-color-primary);
  margin-bottom: var(--gt-space-4);
}

.category-group {
  margin-bottom: var(--gt-space-4);
  border: 1px solid #eee;
  border-radius: var(--gt-radius-md);
  padding: var(--gt-space-3);
}

.category-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: var(--gt-space-2);
  padding-bottom: var(--gt-space-2);
  border-bottom: 1px solid #f0f0f0;
}

.category-count {
  color: #999;
  font-size: 13px;
}

.account-tree {
  background: transparent;
}

.tree-node {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.node-code {
  color: var(--gt-color-primary);
  font-family: monospace;
  min-width: 60px;
}

.node-name {
  color: #333;
}
</style>
