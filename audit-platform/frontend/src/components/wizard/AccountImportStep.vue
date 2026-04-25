<template>
  <div class="gt-account-import-step" v-loading="previewing || importing" :element-loading-text="loadingText" element-loading-background="rgba(255,255,255,0.85)">
    <h2 class="step-title">数据导入</h2>
    <p class="step-desc">上传 Excel/CSV 文件（科目表、序时账、余额表、辅助账等），支持多个文件同时上传，系统自动识别列并预览</p>

    <!-- Phase 1: Upload -->
    <div v-if="phase === 'upload'" class="upload-section">
      <el-upload
        ref="uploadRef"
        class="upload-area"
        drag
        multiple
        :auto-upload="false"
        accept=".xlsx,.csv"
        :on-change="onFileChange"
        :file-list="fileList"
      >
        <el-icon class="el-icon--upload"><UploadFilled /></el-icon>
        <div class="el-upload__text">
          将文件拖到此处，或<em>点击上传</em>
        </div>
        <template #tip>
          <div class="el-upload__tip">
            支持 .xlsx / .csv 格式，可同时上传多个文件（如余额表 + 多个序时账）
          </div>
        </template>
      </el-upload>

      <el-button
        type="primary"
        :loading="previewing"
        :disabled="selectedFiles.length === 0"
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
          :name="idx"
        >
          <template #label>
            <span class="sheet-tab-label">
              {{ sheet.sheet_name }}
              <el-badge
                :value="getSheetMappedCount(idx) + '/' + sheet.headers.length"
                :type="getSheetMappedCount(idx) > 0 ? 'success' : 'warning'"
                class="sheet-badge"
              />
            </span>
          </template>
        </el-tab-pane>
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
            :class-name="getColumnClass(header)"
          >
            <template #header>
              <div class="column-mapping-header" :class="getColumnClass(header)">
                <el-select
                  v-model="columnMapping[header]"
                  size="small"
                  placeholder="(忽略)"
                  clearable
                  filterable
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
                    >
                      <span>{{ opt.label }}</span>
                      <el-tag v-if="_getKeyFields().has(opt.value)" size="small" type="danger" style="margin-left: 4px; transform: scale(0.8)">关键</el-tag>
                      <el-tag v-else-if="_getImportantFields().has(opt.value)" size="small" type="warning" style="margin-left: 4px; transform: scale(0.8)">重要</el-tag>
                    </el-option>
                  </el-option-group>
                </el-select>
                <div class="header-label">
                  <el-icon v-if="isKeyField(columnMapping[header])" class="key-matched-icon"><CircleCheckFilled /></el-icon>
                  <el-icon v-else-if="isImportantField(columnMapping[header])" class="important-matched-icon"><CircleCheckFilled /></el-icon>
                  <el-icon v-else-if="columnMapping[header]" class="matched-icon"><CircleCheckFilled /></el-icon>
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
        <el-button @click="showRefMappingDialog = true" type="info" plain>
          <el-icon><Connection /></el-icon> 参照映射
        </el-button>
        <el-button @click="handleReupload">重新上传</el-button>
        <el-button @click="saveMapping(false)" :disabled="!hasAnyMapping">
          保存映射
        </el-button>
        <el-button type="primary" :loading="importing" @click="handleImport">
          确认导入
        </el-button>
      </div>

      <!-- 参照映射弹窗 -->
      <el-dialog append-to-body v-model="showRefMappingDialog" title="参照已有映射" width="600px" destroy-on-close>
        <p style="color: var(--gt-color-text-secondary); margin-bottom: 12px">
          选择一个项目，将其保存的列映射关系应用到当前文件
        </p>
        <el-table
          :data="refProjects"
          v-loading="loadingRefProjects"
          size="small"
          stripe
          highlight-current-row
          @current-change="selectedRefProject = $event"
          empty-text="暂无可参照的项目"
          max-height="300"
        >
          <el-table-column prop="name" label="项目名称" min-width="180" />
          <el-table-column prop="client_name" label="客户" width="120" />
          <el-table-column prop="mapping_count" label="映射数" width="80" align="center" />
          <el-table-column label="包含类型" min-width="160">
            <template #default="{ row }">
              <el-tag v-for="ft in (row.file_types || [])" :key="ft" size="small" style="margin-right: 4px">
                {{ fileTypeShortLabel(ft) }}
              </el-tag>
            </template>
          </el-table-column>
        </el-table>
        <template #footer>
          <el-button @click="showRefMappingDialog = false">取消</el-button>
          <el-button type="primary" :disabled="!selectedRefProject" @click="applyRefMapping">
            应用映射
          </el-button>
        </template>
      </el-dialog>
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

      <!-- Data sheets imported -->
      <el-alert
        v-if="importResult.data_sheets_imported && Object.keys(importResult.data_sheets_imported).length > 0"
        type="success"
        :closable="false"
        show-icon
        style="margin-bottom: 16px"
      >
        <template #title>
          同时导入数据表：
          <span v-for="(cnt, dt) in importResult.data_sheets_imported" :key="dt" style="margin-right: 12px">
            {{ dataTypeLabel(dt as string) }} {{ cnt.toLocaleString() }} 条
          </span>
        </template>
      </el-alert>

      <!-- 四表数据识别诊断 -->
      <el-alert
        v-if="importResult?.sheet_diagnostics?.length"
        :title="hasBalanceData ? '数据表识别结果' : '未识别到余额表数据，查账功能将不可用'"
        :type="hasBalanceData ? 'info' : 'error'"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      >
        <template #default>
          <div style="margin-top: 6px">
            <div v-for="(d, idx) in importResult.sheet_diagnostics" :key="`${d.sheet_name}_${idx}`"
              style="font-size: 13px; margin-bottom: 4px; display: flex; align-items: center; gap: 6px"
            >
              <el-icon v-if="isSheetOk(d)" style="color: #67c23a"><CircleCheck /></el-icon>
              <el-icon v-else-if="d.missing_cols.length" style="color: #f56c6c"><CircleClose /></el-icon>
              <el-icon v-else style="color: #909399"><InfoFilled /></el-icon>
              <span>{{ d.sheet_name }}</span>
              <el-tag :type="sheetTagType(d.guessed_type)" size="small">{{ typeLabel(d.guessed_type) }}</el-tag>
              <span style="color: #999">{{ d.row_count }} 行</span>
              <span v-if="d.missing_cols.length" style="color: #f56c6c; font-size: 12px">
                缺少必需列：{{ d.missing_cols.map(colLabel).join('、') }}
              </span>
              <span v-if="d.missing_recommended?.length" style="color: #e6a23c; font-size: 12px">
                {{ d.missing_cols.length ? '，' : '' }}建议补充：{{ d.missing_recommended.map(colLabel).join('、') }}
              </span>
            </div>
          </div>
          <div style="font-size: 12px; color: #999; margin-top: 8px; border-top: 1px solid #eee; padding-top: 6px">
            必需列（红色）：余额表（科目编码）、凭证表（科目编码+凭证日期+凭证号）、辅助余额（科目编码+辅助类型）、辅助明细（科目编码）<br/>
            建议列（橙色）：余额表（期初余额+借方发生额+贷方发生额+期末余额）、凭证表（借方金额+贷方金额+摘要）、辅助余额（期初余额+期末余额+辅助编码+辅助名称）
          </div>
        </template>
      </el-alert>

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
      <div class="tree-header">
        <h3 class="section-title">客户科目表</h3>
        <div class="tree-actions">
          <el-button v-if="hasEdits" type="primary" size="small" @click="saveEdits" :loading="saving">
            保存修改
          </el-button>
          <el-button v-if="hasEdits" size="small" @click="cancelEdits">取消</el-button>
        </div>
      </div>

      <!-- 大类 Tab 切换 -->
      <el-tabs v-model="activeCategory" type="border-card" class="category-tabs">
        <el-tab-pane
          v-for="(nodes, cat) in clientTree"
          :key="cat"
          :name="cat"
        >
          <template #label>
            <span>
              <el-tag :type="categoryTagType(cat)" size="small" style="margin-right: 4px">{{ categoryLabel(cat) }}</el-tag>
              {{ countNodes(nodes) }}
            </span>
          </template>

          <el-tree
            :data="toElTreeData(nodes)"
            :props="treeProps"
            :default-expanded-keys="getLevel1Keys(nodes)"
            node-key="account_code"
            :expand-on-click-node="true"
            class="account-tree"
          >
            <template #default="{ data }">
              <div class="tree-node" :class="{ 'tree-node--editing': editingCode === data.account_code }">
                <span class="node-code">{{ data.account_code }}</span>

                <!-- 编辑模式 -->
                <template v-if="editingCode === data.account_code">
                  <el-input
                    v-model="editForm.account_name"
                    size="small"
                    style="width: 200px; margin: 0 6px"
                    @keyup.enter="confirmEdit(data)"
                  />
                  <el-select v-model="editForm.direction" size="small" style="width: 60px">
                    <el-option label="借" value="debit" />
                    <el-option label="贷" value="credit" />
                  </el-select>
                  <el-button size="small" type="primary" text @click="confirmEdit(data)">确认</el-button>
                  <el-button size="small" text @click="editingCode = ''">取消</el-button>
                </template>

                <!-- 显示模式 -->
                <template v-else>
                  <span class="node-name" :class="{ 'node-name--edited': editedCodes.has(data.account_code) }">
                    {{ data.account_name }}
                  </span>
                  <el-tag size="small" :type="data.direction === 'debit' ? '' : 'warning'">
                    {{ data.direction === 'debit' ? '借' : '贷' }}
                  </el-tag>
                  <span class="node-level">L{{ data.level }}</span>
                  <el-button class="node-edit-btn" size="small" text @click.stop="startEdit(data)">编辑</el-button>
                </template>
              </div>
            </template>
          </el-tree>
        </el-tab-pane>
      </el-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted, watch } from 'vue'
import { UploadFilled, CircleCheckFilled, WarningFilled, Connection, CircleCheck, CircleClose, InfoFilled } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { UploadFile, UploadInstance } from 'element-plus'
import http from '@/utils/http'
import { useWizardStore } from '@/stores/wizard'

const wizardStore = useWizardStore()
const uploadRef = ref<UploadInstance>()
const selectedFiles = ref<File[]>([])
const fileList = ref<any[]>([])
const previewing = ref(false)
const importing = ref(false)
const importProgress = ref('')  // 导入进度文字

const loadingText = computed(() => {
  if (previewing.value) return '正在解析文件，请稍候...'
  if (importing.value && importProgress.value) return importProgress.value
  if (importing.value) return '正在导入数据，请稍候...'
  return ''
})

type Phase = 'upload' | 'preview' | 'result'
const phase = ref<Phase>('upload')

// --- Field mapping options grouped by category ---
const FIELD_GROUPS = [
  {
    label: '科目信息',
    options: [
      { value: 'account_code', label: '科目编码' },
      { value: 'account_name', label: '科目名称' },
      { value: 'direction', label: '借贷方向' },
      { value: 'parent_code', label: '上级编码' },
      { value: 'level', label: '科目级次' },
      { value: 'category', label: '科目类别' },
    ],
  },
  {
    label: '金额信息',
    options: [
      { value: 'debit_amount', label: '借方发生额' },
      { value: 'credit_amount', label: '贷方发生额' },
      { value: 'opening_balance', label: '期初余额（净额）' },
      { value: 'opening_debit', label: '期初借方金额' },
      { value: 'opening_credit', label: '期初贷方金额' },
      { value: 'closing_balance', label: '期末余额（净额）' },
      { value: 'closing_debit', label: '期末借方金额' },
      { value: 'closing_credit', label: '期末贷方金额' },
      { value: 'year_opening_debit', label: '年初借方金额' },
      { value: 'year_opening_credit', label: '年初贷方金额' },
      { value: 'year_debit', label: '本年累计借方' },
      { value: 'year_credit', label: '本年累计贷方' },
      { value: 'opening_qty', label: '期初数量' },
      { value: 'opening_fc', label: '期初外币' },
      { value: 'debit_qty', label: '借方数量' },
      { value: 'credit_qty', label: '贷方数量' },
      { value: 'debit_fc', label: '借方外币' },
      { value: 'credit_fc', label: '贷方外币' },
    ],
  },
  {
    label: '凭证信息',
    options: [
      { value: 'voucher_date', label: '凭证日期' },
      { value: 'accounting_period', label: '会计月份' },
      { value: 'voucher_type', label: '凭证类型' },
      { value: 'voucher_no', label: '凭证编号' },
      { value: 'entry_seq', label: '分录序号' },
      { value: 'summary', label: '摘要' },
      { value: 'counterpart_account', label: '对方科目' },
      { value: 'preparer', label: '制单人/填制人' },
      { value: 'reviewer', label: '审核人' },
      { value: 'bookkeeper', label: '记账人' },
    ],
  },
  {
    label: '辅助核算',
    options: [
      { value: 'aux_dimensions', label: '核算维度（混合）' },
      { value: 'aux_type', label: '核算项目类型编号' },
      { value: 'aux_type_name', label: '核算项目类型名称' },
      { value: 'aux_code', label: '核算项目编号' },
      { value: 'aux_name', label: '核算项目名称' },
    ],
  },
  {
    label: '其他',
    options: [
      { value: 'currency_code', label: '币种' },
      { value: 'company_code', label: '公司编码' },
      { value: 'opening_direction', label: '期初方向' },
      { value: 'closing_direction', label: '期末方向' },
      { value: 'unit', label: '计量单位' },
      { value: 'exchange_rate', label: '汇率' },
      { value: 'unit_price', label: '单价' },
      { value: 'aux_info', label: '辅助账核算项目' },
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
  _source_file?: string
}

interface PreviewResponse {
  sheets: SheetPreview[]
  active_sheet: number
}

const previewSheets = ref<SheetPreview[]>([])
const activeSheetIdx = ref(0)
const columnMapping = reactive<Record<string, string | null>>({})

// 每个 sheet 的映射缓存（切换 sheet 时不丢失手动调整）
const sheetMappingCache = reactive<Record<number, Record<string, string | null>>>({})

// --- Import result ---
interface AccountImportResult {
  total_imported: number
  by_category: Record<string, number>
  errors: string[]
  data_sheets_imported?: Record<string, number>
  sheet_diagnostics?: SheetDiagnostic[]
  year?: number | null
}

interface SheetDiagnostic {
  sheet_name: string
  guessed_type: string
  matched_cols: string[]
  missing_cols: string[]
  missing_recommended: string[]
  row_count: number
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

async function onSheetChange(idx: number) {
  _isSheetChanging = true
  try {
    // 1. 保存当前 sheet 的映射到缓存
    const prevIdx = activeSheetIdx.value
    const prevSheet = previewSheets.value[prevIdx]
    if (prevSheet) {
      const save: Record<string, string | null> = {}
      for (const h of prevSheet.headers) {
        save[h] = columnMapping[h] ?? null
      }
      sheetMappingCache[prevIdx] = save
    }

    // 2. 清空当前映射
    for (const key of Object.keys(columnMapping)) delete columnMapping[key]

    // 3. 切换到新 sheet
    activeSheetIdx.value = idx
    const sheet = previewSheets.value[idx]
    if (!sheet) return

    // 4. 恢复映射
    const cached = sheetMappingCache[idx]
    if (cached) {
      for (const h of sheet.headers) {
        if (cached[h] !== undefined && cached[h] !== null) {
          columnMapping[h] = cached[h]
        }
      }
    } else {
      if (sheet.column_mapping) {
        for (const [h, v] of Object.entries(sheet.column_mapping)) {
          if (v) columnMapping[h] = v
        }
      }
      try {
        const saved = await loadSavedMapping(sheet.file_type_guess, sheet.headers)
        for (const [h, v] of Object.entries(saved)) {
          if (v) columnMapping[h] = v
        }
      } catch { /* ignore */ }
      const newCache: Record<string, string | null> = {}
      for (const h of sheet.headers) {
        newCache[h] = columnMapping[h] ?? null
      }
      sheetMappingCache[idx] = newCache
    }

    fileTypeLabel.value = FILE_TYPE_LABELS[sheet.file_type_guess] || '未识别类型'
    fileTypeTagType.value = FILE_TYPE_TAG[sheet.file_type_guess] || 'info'
  } finally {
    _isSheetChanging = false
  }
}

function categoryLabel(cat: string): string { return CATEGORY_LABELS[cat] || cat }
function categoryTagType(cat: string): string { return CATEGORY_TAG_TYPES[cat] || '' }

function dataTypeLabel(dt: string): string {
  const m: Record<string, string> = {
    tb_balance: '余额表', tb_ledger: '序时账',
    tb_aux_balance: '辅助余额', tb_aux_ledger: '辅助明细',
  }
  return m[dt] || dt
}

function typeLabel(t: string): string {
  const m: Record<string, string> = {
    balance: '余额表', ledger: '序时账', aux_balance: '辅助余额',
    aux_ledger: '辅助明细', account_chart: '科目表', unknown: '未识别', empty: '空表',
  }
  return m[t] || t
}

function fileTypeShortLabel(ft: string): string {
  const m: Record<string, string> = {
    balance: '余额', ledger: '凭证', aux_balance: '辅助余额',
    aux_ledger: '辅助明细', account_chart: '科目',
  }
  return m[ft] || ft
}

function isSheetOk(d: SheetDiagnostic): boolean {
  return d.guessed_type !== 'unknown' && d.guessed_type !== 'empty' && d.missing_cols.length === 0 && d.row_count > 0
}

function sheetTagType(t: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  if (t === 'balance' || t === 'ledger' || t === 'aux_balance' || t === 'aux_ledger') return 'success'
  if (t === 'account_chart') return ''
  if (t === 'empty') return 'info'
  return 'warning'
}

function colLabel(col: string): string {
  const m: Record<string, string> = {
    account_code: '科目编码', account_name: '科目名称',
    closing_balance: '期末余额', opening_balance: '期初余额',
    debit_amount: '借方金额', credit_amount: '贷方金额',
    voucher_date: '凭证日期', voucher_no: '凭证号',
    aux_type: '辅助类型', aux_code: '辅助编码', aux_name: '辅助名称',
    summary: '摘要', counterpart_account: '对方科目', preparer: '制单人',
  }
  return m[col] || col
}

const hasBalanceData = computed(() => {
  if (!importResult.value?.data_sheets_imported) return false
  return (importResult.value.data_sheets_imported['tb_balance'] ?? 0) > 0
})

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
  const currentHeaders = activeSheet.value?.headers || []
  for (const h of currentHeaders) {
    if (h !== currentHeader && columnMapping[h] === fieldValue) return true
  }
  return false
}

// 按数据类型区分的关键字段
const _KEY_FIELDS_BY_TYPE: Record<string, Set<string>> = {
  balance: new Set([
    'account_code', 'account_name',
    'opening_balance', 'opening_debit', 'opening_credit',
    'closing_balance', 'closing_debit', 'closing_credit',
    'year_opening_debit', 'year_opening_credit',
    'debit_amount', 'credit_amount',
    'aux_dimensions',
  ]),
  ledger: new Set([
    'account_code', 'account_name',
    'voucher_date', 'voucher_no',
    'debit_amount', 'credit_amount',
    'summary', 'aux_dimensions',
  ]),
  aux_balance: new Set([
    'account_code', 'aux_type', 'aux_code', 'aux_name',
    'opening_balance', 'closing_balance',
    'debit_amount', 'credit_amount',
  ]),
  aux_ledger: new Set([
    'account_code', 'aux_type', 'aux_code', 'aux_name',
    'voucher_date', 'voucher_no',
    'debit_amount', 'credit_amount',
  ]),
}

const _IMPORTANT_FIELDS_BY_TYPE: Record<string, Set<string>> = {
  balance: new Set(['direction', 'level', 'company_code']),
  ledger: new Set(['accounting_period', 'voucher_type', 'preparer', 'counterpart_account']),
  aux_balance: new Set(['direction', 'company_code']),
  aux_ledger: new Set(['accounting_period', 'voucher_type', 'summary', 'preparer']),
}

// 通用兜底
const _KEY_FIELDS_DEFAULT = new Set([
  'account_code', 'account_name', 'debit_amount', 'credit_amount',
  'opening_balance', 'closing_balance', 'voucher_date', 'voucher_no',
])

// 必需字段（与后端 _REQUIRED_FIELD_GROUPS 一致，用于阻断导入）
const _REQUIRED_FIELDS_BY_TYPE: Record<string, Array<{ label: string; candidates: Set<string> }>> = {
  balance: [
    { label: '科目编码', candidates: new Set(['account_code']) },
  ],
  ledger: [
    { label: '科目编码', candidates: new Set(['account_code']) },
    { label: '凭证日期', candidates: new Set(['voucher_date']) },
    { label: '凭证号', candidates: new Set(['voucher_no']) },
  ],
  aux_balance: [
    { label: '科目编码', candidates: new Set(['account_code']) },
    { label: '辅助类型', candidates: new Set(['aux_type']) },
  ],
  aux_ledger: [
    { label: '科目编码', candidates: new Set(['account_code']) },
  ],
  account_chart: [
    { label: '科目编码', candidates: new Set(['account_code']) },
    { label: '科目名称', candidates: new Set(['account_name']) },
  ],
}

/** 检查所有 sheet 的必需字段是否已映射，返回缺失信息 */
function checkRequiredFieldsMissing(): Array<{ sheet: string; type: string; missing: string[] }> {
  const results: Array<{ sheet: string; type: string; missing: string[] }> = []
  for (let i = 0; i < previewSheets.value.length; i++) {
    const sheet = previewSheets.value[i]
    const dt = sheet.file_type_guess || 'unknown'
    if (dt === 'unknown') continue
    const reqs = _REQUIRED_FIELDS_BY_TYPE[dt]
    if (!reqs) continue
    const cached = sheetMappingCache[i] || {}
    const mappedFields = new Set(Object.values(cached).filter(Boolean))
    const missing: string[] = []
    for (const req of reqs) {
      const found = [...req.candidates].some(c => mappedFields.has(c))
      if (!found) missing.push(req.label)
    }
    if (missing.length > 0) {
      results.push({ sheet: sheet.sheet_name, type: dt, missing })
    }
  }
  return results
}

function _getKeyFields(): Set<string> {
  const ft = activeSheet.value?.file_type_guess || ''
  return _KEY_FIELDS_BY_TYPE[ft] || _KEY_FIELDS_DEFAULT
}

/** 前端版数据类型推断（与后端 _guess_data_type 逻辑一致） */
function _guessDataTypeFrontend(fields: Set<string>): string {
  const hasCode = fields.has('account_code')
  const hasVoucherDate = fields.has('voucher_date')
  const hasVoucherNo = fields.has('voucher_no')
  const hasDebit = fields.has('debit_amount')
  const hasCredit = fields.has('credit_amount')
  const hasOpening = ['opening_balance', 'opening_debit', 'opening_credit', 'year_opening_debit', 'year_opening_credit'].some(f => fields.has(f))
  const hasClosing = ['closing_balance', 'closing_debit', 'closing_credit'].some(f => fields.has(f))
  const hasAuxDimensions = fields.has('aux_dimensions')
  const hasAuxSeparate = ['aux_code', 'aux_name'].some(f => fields.has(f)) && fields.has('aux_type')

  if (hasAuxSeparate && !hasAuxDimensions) {
    return hasVoucherDate ? 'aux_ledger' : 'aux_balance'
  }
  if (hasVoucherDate && hasVoucherNo && (hasDebit || hasCredit)) return 'ledger'
  if (hasCode && (hasOpening || hasClosing)) return 'balance'
  if (hasCode && (hasDebit || hasCredit) && !hasVoucherDate) return 'balance'
  if (hasCode) return 'account_chart'
  return 'unknown'
}

function _getImportantFields(): Set<string> {
  const ft = activeSheet.value?.file_type_guess || ''
  return _IMPORTANT_FIELDS_BY_TYPE[ft] || new Set(['accounting_period', 'voucher_type', 'preparer', 'direction', 'level'])
}

function isKeyField(field: string | null | undefined): boolean {
  return !!field && _getKeyFields().has(field)
}

function isImportantField(field: string | null | undefined): boolean {
  return !!field && _getImportantFields().has(field)
}

function getColumnClass(header: string): string {
  const mapped = columnMapping[header]
  if (!mapped) return ''
  if (_getKeyFields().has(mapped)) return 'col-key-matched'
  if (_getImportantFields().has(mapped)) return 'col-important-matched'
  return 'col-other-matched'
}

function getSheetMappedCount(sheetIdx: number): number {
  const cached = sheetMappingCache[sheetIdx]
  if (!cached) return 0
  return Object.values(cached).filter(v => v !== null && v !== undefined && v !== '').length
}

function onFileChange(_file: UploadFile, fileListVal: UploadFile[]) {
  selectedFiles.value = fileListVal.map(f => f.raw!).filter(Boolean)
}

async function handlePreview() {
  if (selectedFiles.value.length === 0 || !wizardStore.projectId) return
  previewing.value = true
  try {
    // 支持多文件：逐个上传预览，合并所有 sheet
    const allSheets: any[] = []
    for (const file of selectedFiles.value) {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await http.post(
        `/api/projects/${wizardStore.projectId}/account-chart/preview`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120000 },
      )
      const result: PreviewResponse = data.data ?? data
      const sheets = result.sheets || []
      // 给 sheet 名加文件名前缀（避免多文件同名 sheet 冲突）
      for (const s of sheets) {
        if (selectedFiles.value.length > 1) {
          s.sheet_name = `[${file.name}] ${s.sheet_name}`
        }
        s._source_file = file.name
        allSheets.push(s)
      }
    }
    previewSheets.value = allSheets

    // 对所有 sheet 预先做自动列名匹配（存入缓存，切换时直接恢复）
    for (let i = 0; i < previewSheets.value.length; i++) {
      const sheet = previewSheets.value[i]
      const autoMapping: Record<string, string | null> = {}

      // 1. 使用后端返回的自动匹配结果
      if (sheet.column_mapping) {
        for (const [h, v] of Object.entries(sheet.column_mapping)) {
          if (v) autoMapping[h] = v
        }
      }

      // 2. 尝试从后端加载已保存的映射覆盖
      try {
        const saved = await loadSavedMapping(sheet.file_type_guess, sheet.headers)
        for (const [h, v] of Object.entries(saved)) {
          if (v) autoMapping[h] = v
        }
      } catch { /* ignore */ }

      // 存入缓存
      sheetMappingCache[i] = autoMapping
    }

    // 激活第一个 sheet
    if (previewSheets.value.length > 0) {
      activeSheetIdx.value = 0
      // 从缓存恢复（不再重复请求后端）
      const cached = sheetMappingCache[0]
      if (cached) {
        for (const key of Object.keys(columnMapping)) delete columnMapping[key]
        for (const [h, v] of Object.entries(cached)) {
          columnMapping[h] = v
        }
      }
      const sheet = previewSheets.value[0]
      fileTypeLabel.value = FILE_TYPE_LABELS[sheet.file_type_guess] || '未识别类型'
      fileTypeTagType.value = FILE_TYPE_TAG[sheet.file_type_guess] || 'info'
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
  selectedFiles.value = []
  for (const key of Object.keys(columnMapping)) delete columnMapping[key]
  uploadRef.value?.clearFiles()
}

// ── 列映射保存/加载 ──

const MAPPING_STORAGE_KEY = 'gt-column-mapping'

const hasAnyMapping = computed(() => {
  return Object.values(columnMapping).some(v => v !== null && v !== undefined)
})

// 映射变化时自动防抖保存
let _saveMappingTimer: ReturnType<typeof setTimeout> | null = null
let _isSheetChanging = false  // 切换 sheet 期间暂停 watch

watch(columnMapping, () => {
  if (_isSheetChanging) return  // 切换 sheet 期间不触发

  // 保存到内存缓存（立即）
  const idx = activeSheetIdx.value
  const sheet = previewSheets.value[idx]
  if (sheet) {
    const save: Record<string, string | null> = {}
    for (const h of sheet.headers) {
      save[h] = columnMapping[h] ?? null
    }
    sheetMappingCache[idx] = save

    // ── 重新推断数据类型（与后端 _guess_data_type 逻辑一致） ──
    const mappedFields = new Set(Object.values(save).filter(Boolean) as string[])
    const newType = _guessDataTypeFrontend(mappedFields)
    if (newType !== sheet.file_type_guess) {
      sheet.file_type_guess = newType
      fileTypeLabel.value = FILE_TYPE_LABELS[newType] || '未识别类型'
      fileTypeTagType.value = FILE_TYPE_TAG[newType] || 'info'
    }
  }

  // 同步到 wizardStore（供"保存"按钮使用）
  wizardStore.stepData['account_import'] = {
    column_mappings: { ...sheetMappingCache },
    active_sheet: idx,
    sheets: previewSheets.value.map(s => ({
      sheet_name: s.sheet_name,
      file_type_guess: s.file_type_guess,
      total_rows: s.total_rows,
    })),
  }

  // 防抖保存当前 sheet 到后端（800ms）
  if (_saveMappingTimer) clearTimeout(_saveMappingTimer)
  _saveMappingTimer = setTimeout(() => {
    if (hasAnyMapping.value) saveCurrentSheetMapping()
  }, 800)
}, { deep: true })

/** 只保存当前活跃 sheet 的映射（防抖用） */
async function saveCurrentSheetMapping() {
  const sheet = activeSheet.value
  if (!sheet || !wizardStore.projectId) return
  const cleanMapping: Record<string, string> = {}
  for (const [h, v] of Object.entries(columnMapping)) {
    if (v) cleanMapping[h] = v
  }
  if (Object.keys(cleanMapping).length === 0) return
  try {
    await http.post(`/api/projects/${wizardStore.projectId}/column-mappings`, {
      file_type: sheet.file_type_guess,
      sheet_name: sheet.sheet_name,
      mapping: cleanMapping,
    })
  } catch {
    // 静默失败
  }
}

async function saveMapping(silent = false) {
  if (!wizardStore.projectId) return

  // 保存所有 sheet 的映射（不仅是当前活跃 sheet）
  let savedCount = 0
  for (let i = 0; i < previewSheets.value.length; i++) {
    const sheet = previewSheets.value[i]
    const cached = sheetMappingCache[i]
    if (!cached || !sheet) continue

    const cleanMapping: Record<string, string> = {}
    for (const [h, v] of Object.entries(cached)) {
      if (v) cleanMapping[h] = v
    }
    if (Object.keys(cleanMapping).length === 0) continue

    try {
      await http.post(`/api/projects/${wizardStore.projectId}/column-mappings`, {
        file_type: sheet.file_type_guess,
        sheet_name: sheet.sheet_name,
        mapping: cleanMapping,
      })
      savedCount++
    } catch {
      // 单个 sheet 保存失败不阻断
    }
  }

  // 如果没有缓存，回退到只保存当前 sheet
  if (savedCount === 0) {
    const sheet = activeSheet.value
    if (!sheet) return
    const cleanMapping: Record<string, string> = {}
    for (const [h, v] of Object.entries(columnMapping)) {
      if (v) cleanMapping[h] = v
    }
    if (Object.keys(cleanMapping).length === 0) return
    try {
      await http.post(`/api/projects/${wizardStore.projectId}/column-mappings`, {
        file_type: sheet.file_type_guess,
        sheet_name: sheet.sheet_name,
        mapping: cleanMapping,
      })
      savedCount = 1
    } catch {
      const saved = JSON.parse(localStorage.getItem(MAPPING_STORAGE_KEY) || '{}')
      saved[sheet.file_type_guess] = cleanMapping
      localStorage.setItem(MAPPING_STORAGE_KEY, JSON.stringify(saved))
      if (!silent) ElMessage.success('列映射已本地保存')
      return
    }
  }

  if (!silent) {
    ElMessage.success(`已保存 ${savedCount} 张表的列映射，其他项目可通过「参照映射」引用`)
  }
}

async function loadSavedMapping(fileType: string, headers: string[]): Promise<Record<string, string | null>> {
  // 优先从后端加载
  if (wizardStore.projectId) {
    try {
      const { data } = await http.get(
        `/api/projects/${wizardStore.projectId}/column-mappings`,
        { params: { file_type: fileType } }
      )
      const mappings = data.data ?? data ?? {}
      // 找到匹配的映射
      for (const [_key, mapping] of Object.entries(mappings)) {
        if (mapping && typeof mapping === 'object') {
          const result: Record<string, string | null> = {}
          for (const h of headers) {
            const m = mapping as Record<string, string>
            if (m[h]) result[h] = m[h]
          }
          if (Object.keys(result).length > 0) return result
        }
      }
    } catch { /* fall through to localStorage */ }
  }

  // 回退到 localStorage
  const saved = JSON.parse(localStorage.getItem(MAPPING_STORAGE_KEY) || '{}')
  const savedMapping = saved[fileType] as Record<string, string> | undefined
  if (!savedMapping) return {}
  const result: Record<string, string | null> = {}
  for (const h of headers) {
    if (savedMapping[h]) result[h] = savedMapping[h]
  }
  return result
}

async function handleImport() {
  if (selectedFiles.value.length === 0 || !wizardStore.projectId) return

  // 关键列硬阻断：检查所有 sheet 的必需字段是否已映射
  const missingInfo = checkRequiredFieldsMissing()
  if (missingInfo.length > 0) {
    const details = missingInfo.map(m =>
      `「${m.sheet}」(${m.type}) 缺少: ${m.missing.join('、')}`
    ).join('\n')
    ElMessageBox.alert(
      `以下数据表缺少必需的关键列映射，无法导入：\n\n${details}\n\n请在列映射中手动指定这些列。`,
      '关键列缺失',
      { type: 'warning', confirmButtonText: '去修改映射' },
    )
    return
  }

  importing.value = true

  // 启动进度轮询
  const pollTimer = setInterval(async () => {
    try {
      const { data } = await http.get(`/api/data-lifecycle/import-queue/${wizardStore.projectId}`)
      const status = data.data ?? data
      if (status && typeof status === 'object' && status.message && status.status !== 'idle') {
        importProgress.value = status.message
      }
    } catch { /* ignore */ }
  }, 2000)

  try {
    // ── 构建 FormData（所有文件 + 合并映射一次发送） ──
    const formData = new FormData()
    let totalSizeBytes = 0
    for (const file of selectedFiles.value) {
      formData.append('files', file)
      totalSizeBytes += file.size
    }
    const totalSizeMB = (totalSizeBytes / 1024 / 1024).toFixed(1)

    // 组装所有 sheet 的列映射（按原始 sheet 名）
    const perSheetMapping: Record<string, Record<string, string>> = {}
    for (let i = 0; i < previewSheets.value.length; i++) {
      const cached = sheetMappingCache[i]
      if (!cached) continue
      const clean: Record<string, string> = {}
      for (const [h, v] of Object.entries(cached)) {
        if (v) clean[h] = v
      }
      if (Object.keys(clean).length > 0) {
        // 使用原始 sheet 名（去掉多文件前缀 "[file.xlsx] "）
        let sheetName = previewSheets.value[i].sheet_name
        const prefixMatch = sheetName.match(/^\[.+?\]\s+(.+)$/)
        if (prefixMatch) sheetName = prefixMatch[1]
        perSheetMapping[sheetName] = clean
      }
    }
    const sheetNames = Object.keys(perSheetMapping)
    const mappingToSend = sheetNames.length === 1
      ? perSheetMapping[sheetNames[0]]
      : perSheetMapping
    formData.append('column_mapping', JSON.stringify(mappingToSend))

    importProgress.value = `正在上传 ${selectedFiles.value.length} 个文件（${totalSizeMB} MB）…`

    // ── 大文件或多文件用异步，小单文件用同步 ──
    const useAsync = totalSizeBytes > 10 * 1024 * 1024 || selectedFiles.value.length > 2

    let finalResult: AccountImportResult | null = null

    if (useAsync) {
      // 异步导入：立即返回，轮询进度
      await http.post(
        `/api/projects/${wizardStore.projectId}/account-chart/import-async`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 600000 },
      )
      // 等待后台任务完成
      let done = false
      while (!done) {
        await new Promise(r => setTimeout(r, 2000))
        try {
          const { data: statusData } = await http.get(`/api/data-lifecycle/import-queue/${wizardStore.projectId}`)
          const status = statusData.data ?? statusData
          if (status && typeof status === 'object') {
            const pct = status.progress ?? 0
            const msg = status.message || ''
            importProgress.value = `[${pct}%] ${msg}`
            if (pct >= 100 || pct < 0 || status.status === 'idle') {
              done = true
              if (pct < 0) {
                ElMessage.error(msg || '导入失败')
                throw new Error(msg || '导入失败')
              }
              const res = status.result
              if (res && typeof res === 'object') {
                finalResult = res as AccountImportResult
              }
            }
          } else {
            done = true
          }
        } catch (e) {
          if (e instanceof Error && e.message.includes('导入失败')) throw e
          done = true
        }
      }
    } else {
      // 同步导入
      const { data } = await http.post(
        `/api/projects/${wizardStore.projectId}/account-chart/import`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 },
      )
      finalResult = (data.data ?? data) as AccountImportResult
    }

    // ── 处理结果 ──
    importResult.value = finalResult || {
      total_imported: 0, by_category: {}, errors: [],
      data_sheets_imported: {}, sheet_diagnostics: [], year: null,
    }
    const importedYear = importResult.value.year ?? null

    let msg = `成功导入 ${importResult.value.total_imported} 个科目`
    const sheetLabels: Record<string, string> = {
      tb_balance: '余额表', tb_ledger: '序时账',
      tb_aux_balance: '辅助余额', tb_aux_ledger: '辅助明细',
    }
    const parts: string[] = []
    for (const [dt, cnt] of Object.entries(importResult.value.data_sheets_imported || {})) {
      if ((cnt as number) > 0) parts.push(`${sheetLabels[dt] || dt} ${(cnt as number).toLocaleString()} 条`)
    }
    if (parts.length > 0) msg += `，同时导入 ${parts.join('、')}`
    ElMessage.success(msg)

    saveMapping(true)

    await wizardStore.saveStep('account_import', {
      total_imported: importResult.value.total_imported,
      by_category: importResult.value.by_category,
      errors: importResult.value.errors,
      data_sheets_imported: importResult.value.data_sheets_imported,
      sheet_diagnostics: importResult.value.sheet_diagnostics,
      year: importedYear,
    })

    phase.value = 'result'
    await loadClientTree()
  } catch {
    // Error handled by http interceptor
  } finally {
    clearInterval(pollTimer)
    importing.value = false
    importProgress.value = ''
  }
}

async function _importOtherSheets() {
  if (selectedFiles.value.length === 0 || !wizardStore.projectId) return

  // 优先使用导入识别出的年度，其次回退向导基本信息
  const importStep = wizardStore.stepData?.account_import as Record<string, any> | undefined
  const basicInfo = wizardStore.stepData?.basic_info as Record<string, any> | undefined
  const year = importResult.value?.year || importStep?.year || basicInfo?.audit_year || basicInfo?.year || new Date().getFullYear()

  // 识别每个 sheet 的数据类型，跳过科目表（已导入）
  const typeMap: Record<string, string> = {
    'balance': 'tb_balance',
    'ledger': 'tb_ledger',
    'aux_balance': 'tb_aux_balance',
    'aux_ledger': 'tb_aux_ledger',
  }

  // 收集需要导入的 sheet 类型
  const sheetsToImport: { sheetName: string; dataType: string; guessedType: string }[] = []
  for (const sheet of previewSheets.value) {
    const guessedType = sheet.file_type_guess
    if (guessedType === 'account_chart' || guessedType === 'unknown' || !typeMap[guessedType]) {
      continue
    }
    sheetsToImport.push({
      sheetName: sheet.sheet_name,
      dataType: typeMap[guessedType],
      guessedType,
    })
  }

  if (sheetsToImport.length === 0) return

  // 显示导入进度
  ElMessage.info(`正在导入 ${sheetsToImport.length} 张数据表，请稍候...`)

  let importedCount = 0
  let totalRecords = 0

  for (const item of sheetsToImport) {
    try {
      const formData = new FormData()
      formData.append('file', selectedFiles.value[0])
      formData.append('source_type', 'generic')
      formData.append('data_type', item.dataType)
      formData.append('year', String(year))
      formData.append('on_duplicate', 'overwrite')

      const { data } = await http.post(
        `/api/projects/${wizardStore.projectId}/import`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300000 }
      )
      const batch = data?.data ?? data
      if (batch?.record_count) totalRecords += batch.record_count
      importedCount++
    } catch {
      // 单个 sheet 导入失败不阻断其他
    }
  }

  if (importedCount > 0) {
    ElMessage.success(`导入完成：${importedCount} 张表，共 ${totalRecords.toLocaleString()} 条记录`)
  }
}

async function loadClientTree() {
  if (!wizardStore.projectId) return
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/account-chart/client`,
    )
    clientTree.value = data.data ?? data
    // 默认激活第一个大类
    if (clientTree.value) {
      const keys = Object.keys(clientTree.value)
      if (keys.length > 0) activeCategory.value = keys[0]
    }
  } catch {
    // Silently fail
  }
}

// ── 科目编辑功能 ──
const activeCategory = ref('asset')
const editingCode = ref('')
const editForm = reactive({ account_name: '', direction: 'debit' })
const editedCodes = reactive(new Set<string>())
const pendingEdits = reactive<Record<string, { account_name: string; direction: string }>>({})
const saving = ref(false)

const hasEdits = computed(() => Object.keys(pendingEdits).length > 0)

function getLevel1Keys(nodes: AccountTreeNode[]): string[] {
  return nodes.filter(n => n.level === 1).map(n => n.account_code)
}

function startEdit(data: any) {
  editingCode.value = data.account_code
  editForm.account_name = data.account_name
  editForm.direction = data.direction
}

function confirmEdit(data: any) {
  if (editForm.account_name !== data.account_name || editForm.direction !== data.direction) {
    data.account_name = editForm.account_name
    data.direction = editForm.direction
    pendingEdits[data.account_code] = {
      account_name: editForm.account_name,
      direction: editForm.direction,
    }
    editedCodes.add(data.account_code)
  }
  editingCode.value = ''
}

function cancelEdits() {
  // 重新加载原始数据
  loadClientTree()
  Object.keys(pendingEdits).forEach(k => delete pendingEdits[k])
  editedCodes.clear()
}

async function saveEdits() {
  if (!wizardStore.projectId || !hasEdits.value) return
  saving.value = true
  try {
    const updates = Object.entries(pendingEdits).map(([code, vals]) => ({
      account_code: code,
      ...vals,
    }))
    await http.put(
      `/api/projects/${wizardStore.projectId}/account-chart/batch-update`,
      { updates },
    )
    ElMessage.success(`已保存 ${updates.length} 条修改`)
    Object.keys(pendingEdits).forEach(k => delete pendingEdits[k])
    editedCodes.clear()
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '保存失败')
  } finally {
    saving.value = false
  }
}

// ── 参照映射功能 ──
const showRefMappingDialog = ref(false)
const refProjects = ref<any[]>([])
const loadingRefProjects = ref(false)
const selectedRefProject = ref<any>(null)

watch(showRefMappingDialog, async (visible) => {
  if (!visible || !wizardStore.projectId) return
  loadingRefProjects.value = true
  try {
    const { data } = await http.get(
      `/api/projects/${wizardStore.projectId}/column-mappings/reference-projects`,
      { validateStatus: (s: number) => s < 600 }
    )
    const d = data?.data ?? data
    refProjects.value = Array.isArray(d) ? d : []
  } catch {
    refProjects.value = []
  } finally {
    loadingRefProjects.value = false
  }
})

async function applyRefMapping() {
  if (!selectedRefProject.value || !wizardStore.projectId) return
  try {
    await http.post(
      `/api/projects/${wizardStore.projectId}/column-mappings/reference-copy`,
      { source_project_id: selectedRefProject.value.id }
    )
    ElMessage.success(`已从「${selectedRefProject.value.name}」复制映射关系`)
    showRefMappingDialog.value = false

    // 重新加载当前 sheet 的映射
    const sheet = activeSheet.value
    if (sheet) {
      const saved = await loadSavedMapping(sheet.file_type_guess, sheet.headers)
      for (const [h, v] of Object.entries(saved)) {
        if (v) columnMapping[h] = v
      }
    }
  } catch (e: any) {
    ElMessage.error(e.response?.data?.detail || '复制映射失败')
  }
}

onMounted(async () => {
  if (wizardStore.projectId && wizardStore.isStepCompleted('account_import')) {
    const saved = wizardStore.stepData.account_import as Record<string, unknown> | undefined
    if (saved) {
      importResult.value = {
        total_imported: (saved.total_imported as number) || 0,
        by_category: (saved.by_category as Record<string, number>) || {},
        errors: (saved.errors as string[]) || [],
        data_sheets_imported: (saved.data_sheets_imported as Record<string, number>) || {},
        sheet_diagnostics: (saved.sheet_diagnostics as SheetDiagnostic[]) || [],
        year: (saved.year as number | null | undefined) ?? null,
      }
      phase.value = 'result'
    }
    await loadClientTree()
  }
})

// 暴露校验方法给父组件（ProjectWizard）
defineExpose({
  validate(): boolean {
    if (!importResult.value || importResult.value.total_imported === 0) {
      ElMessage.warning('请先导入科目表')
      return false
    }
    if (!hasBalanceData.value) {
      ElMessage.warning('未识别到余额表数据，请确保上传的文件包含余额表 sheet（需含科目编码、期末余额列）')
      return false
    }
    return true
  },
  saveMapping,
  importOtherSheets: _importOtherSheets,
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
.sheet-tab-label { display: inline-flex; align-items: center; gap: 6px; }
.sheet-badge { margin-left: 2px; }
.sheet-badge :deep(.el-badge__content) { font-size: 10px; padding: 0 4px; height: 16px; line-height: 16px; }
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
.key-matched-icon {
  color: #409eff;
  font-size: 14px;
}
.important-matched-icon {
  color: #67c23a;
  font-size: 14px;
}

.unmatched-icon {
  color: #e6a23c;
  font-size: 14px;
}

/* 关键列高亮 */
.col-key-matched { background: #ecf5ff !important; }
.col-important-matched { background: #f0f9eb !important; }
.col-other-matched { background: #fafafa !important; }

:deep(.col-key-matched) { background: #ecf5ff !important; }
:deep(.col-important-matched) { background: #f0f9eb !important; }

.column-mapping-header.col-key-matched {
  border-bottom: 2px solid #409eff;
}
.column-mapping-header.col-important-matched {
  border-bottom: 2px solid #67c23a;
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



.error-list {
  margin: 0;
  padding-left: 20px;
}

.tree-section {
  margin-top: var(--gt-space-4);
}
.tree-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-3);
}
.tree-actions { display: flex; gap: var(--gt-space-2); }

.section-title {
  font-size: 16px;
  color: var(--gt-color-primary);
  margin: 0;
}

.category-tabs :deep(.el-tabs__content) { padding: var(--gt-space-2) 0; }

.account-tree { background: transparent; }
.account-tree :deep(.el-tree-node__content) { height: auto; min-height: 32px; padding: 2px 0; }

.tree-node {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  width: 100%;
}
.tree-node--editing { background: var(--gt-color-primary-bg); border-radius: 4px; padding: 2px 4px; }

.node-code {
  color: var(--gt-color-primary);
  font-family: monospace;
  min-width: 80px;
  flex-shrink: 0;
}
.node-name { color: #333; flex: 1; min-width: 0; }
.node-name--edited { color: var(--gt-color-primary); font-weight: 600; }
.node-level { color: #bbb; font-size: 11px; flex-shrink: 0; }
.node-edit-btn { opacity: 0; transition: opacity 0.15s; flex-shrink: 0; }
.tree-node:hover .node-edit-btn { opacity: 1; }
</style>
