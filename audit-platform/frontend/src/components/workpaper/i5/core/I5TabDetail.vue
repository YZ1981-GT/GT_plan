<template>
  <div class="i5-tab-detail">
    <!-- 方法论上下文（琥珀色左边线） -->
    <div class="methodology-context">
      <p><strong>I5-2 明细表 — 3区段Tab使用说明：</strong></p>
      <p>本表26列按功能拆分为3个区段Tab切换查看，切换Tab时行保持同步高亮。</p>
      <p>① 基础：项目名称/资产类型/发生日期/到期日期/摘要/合同编号/对方单位/索引号</p>
      <p>② 金额：期初余额/本期增加/本期减少/期末余额(公式)/增加原因/减少原因/原始金额/累计金额/净值</p>
      <p>③ 检查：凭证号/凭证日期/检查方法/检查结果/结论/是否异常/备注/复核标记/状态</p>
    </div>

    <!-- 操作栏：区段Tab + 按钮 -->
    <div class="toolbar-row">
      <el-segmented
        v-model="activeSection"
        :options="segmentOptions"
        class="segment-bar"
      />
      <div class="toolbar-right">
        <el-button
          v-if="!isReadonly"
          type="primary"
          size="small"
          @click="handleAddRow"
        >
          + 新增
        </el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" class="import-export-dropdown">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" text @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" type="default" text @click="handleReview">
          复核
        </el-button>
        <span class="row-count">共 {{ rows.length }} 行</span>
      </div>
    </div>

    <!-- 数据表格（根据 activeSection 渲染不同列） -->
    <el-table
      :data="rows"
      border
      size="small"
      highlight-current-row
      row-key="rowId"
      class="detail-table"
      max-height="520"
      @current-change="onCurrentRowChange"
    >
      <!-- 序号列 -->
      <el-table-column type="index" label="#" width="45" align="center" fixed="left" />

      <!-- 动态列 -->
      <el-table-column
        v-for="col in activeColumns"
        :key="col.key"
        :prop="col.key"
        :label="col.label"
        :min-width="col.width"
        :align="col.type === 'number' || col.type === 'formula' ? 'right' : 'left'"
      >
        <!-- 公式列表头带tooltip -->
        <template v-if="col.type === 'formula'" #header>
          <el-tooltip :content="col.tooltip" placement="top">
            <span class="formula-col-header">{{ col.label }}</span>
          </el-tooltip>
        </template>

        <!-- 单元格渲染 -->
        <template #default="{ row }">
          <!-- 公式列（只读） -->
          <template v-if="col.type === 'formula'">
            <el-tooltip :content="col.tooltip" placement="top">
              <span class="formula-value">
                {{ fmtAmount(row[col.key]) }}
              </span>
            </el-tooltip>
          </template>
          <!-- 数值列 -->
          <template v-else-if="col.type === 'number'">
            <el-input-number
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              :controls="false"
              @change="(v: number | null) => onCellEdit(row.rowId, col.key, v ?? 0)"
            />
            <span v-else>{{ fmtAmount(row[col.key]) }}</span>
          </template>
          <!-- 日期列 -->
          <template v-else-if="col.type === 'date'">
            <el-date-picker
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              style="width: 100%"
              @update:model-value="(v: string) => onCellEdit(row.rowId, col.key, v)"
            />
            <span v-else>{{ row[col.key] }}</span>
          </template>
          <!-- 选择列 -->
          <template v-else-if="col.type === 'select'">
            <el-select
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              style="width: 100%"
              @change="(v: string) => onCellEdit(row.rowId, col.key, v)"
            >
              <el-option
                v-for="opt in col.options"
                :key="opt"
                :label="opt"
                :value="opt"
              />
            </el-select>
            <span v-else>{{ row[col.key] }}</span>
          </template>
          <!-- 布尔列 -->
          <template v-else-if="col.type === 'boolean'">
            <el-switch
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              @change="(v: boolean) => onCellEdit(row.rowId, col.key, v)"
            />
            <el-tag v-else :type="row[col.key] ? 'danger' : 'success'" size="small">
              {{ row[col.key] ? '是' : '否' }}
            </el-tag>
          </template>
          <!-- 文本列 -->
          <template v-else>
            <el-input
              v-if="col.editable && !isReadonly"
              :model-value="row[col.key]"
              size="small"
              @change="(v: string) => onCellEdit(row.rowId, col.key, v)"
            />
            <span v-else>{{ row[col.key] }}</span>
          </template>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="60" align="center" fixed="right" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button type="danger" link size="small" @click="handleRemoveRow(row.rowId)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行卡片 -->
    <div class="subtotals-bar">
      <span class="subtotal-label">合计：</span>
      <span class="subtotal-item">期初 {{ fmtAmount(subtotals.beginBalance) }}</span>
      <span class="subtotal-item">增加 {{ fmtAmount(subtotals.increase) }}</span>
      <span class="subtotal-item">减少 {{ fmtAmount(subtotals.decrease) }}</span>
      <span class="subtotal-item">期末 {{ fmtAmount(subtotals.endBalance) }}</span>
      <span class="subtotal-item">原始金额 {{ fmtAmount(subtotals.originalAmount) }}</span>
      <span class="subtotal-item">净值 {{ fmtAmount(subtotals.netValue) }}</span>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>3个区段Tab切换不影响数据，行跨Tab保持同步</li>
        <li>公式列自动计算：期末=期初+增加-减少（标准资产类借方1911）</li>
        <li>合计行联动审定表I5-1：本表合计=审定表对应行</li>
        <li>动态行：点击"+ 新增"输入项目名称后添加</li>
        <li>导入导出支持Excel模板，多区段分sheet导出</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I5TabDetail.vue — I5-2 其他非流动资产明细表（26列3区段Tab，63行虚拟滚动）
 *
 * 26列拆分为3区段Tab：基础(8列) | 金额(9列含1公式) | 检查(9列)
 * - Tab切换时行同步（activeRowIndex统一）
 * - 公式列tooltip显示来源，虚线下划线+cursor:help
 * - 动态行添加(ElMessageBox.prompt) / 删除
 * - 合计行联动审定表I5-1
 * - 导入导出(el-dropdown三级)
 * - 63行虚拟滚动（el-table max-height）
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 4.3
 * Requirements: 3.1-3.4
 */
import { computed, toRef, inject } from 'vue'
import { ArrowDown, MagicStick } from '@element-plus/icons-vue'
import { useI5Detail, type I5DetailRow } from '../../composables/useI5Detail'
import { useI5ImportExport } from '../../composables/useI5ImportExport'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const openReviewDialog = inject<(section?: string) => void>('openReviewDialog', () => {})

// ─── Composable: Detail ──────────────────────────────────────────────────────

const {
  rows,
  activeSection,
  activeColumns,
  subtotals,
  sections,
  setActiveRow,
  updateCell,
  addRow,
  removeRow,
} = useI5Detail(
  toRef(props, 'allResponses'),
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

// ─── Composable: Import/Export ────────────────────────────────────────────────

const {
  exportTemplate,
  exportData,
  importData,
} = useI5ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

// ─── Segment Options ─────────────────────────────────────────────────────────

const segmentOptions = computed(() =>
  sections.map((s) => ({ label: s.label, value: s.key })),
)

// ─── Actions ─────────────────────────────────────────────────────────────────

function onCurrentRowChange(row: I5DetailRow | null): void {
  if (row) {
    const idx = rows.value.findIndex((r) => r.rowId === row.rowId)
    setActiveRow(idx)
  }
}

function onCellEdit(rowId: string, field: string, value: any): void {
  updateCell(rowId, field, value)
}

async function handleAddRow(): Promise<void> {
  await addRow()
}

function handleRemoveRow(rowId: string): void {
  removeRow(rowId)
}

function handleExportTemplate(): void {
  exportTemplate('I5-2')
}

function handleExportData(): void {
  exportData('I5-2')
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) await importData('I5-2', file)
  }
  input.click()
}

async function handleAiGenerate(): Promise<void> {
  try {
    await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'detail',
      prompt: 'I5其他非流动资产明细表数据分析',
      context: { wpCode: 'I5-2', rowCount: rows.value.length },
    })
  } catch { /* ignore */ }
}

function handleReview(): void {
  openReviewDialog('I5-2 明细表')
}

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i5-tab-detail { padding: 16px; font-size: 13px; }

/* 方法论上下文（琥珀色左边线+浅黄背景） */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p { margin: 0; }
.methodology-context strong { color: #78350f; }

/* 操作栏 */
.toolbar-row {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.segment-bar { flex-shrink: 0; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); }

/* 表格 */
.detail-table { font-size: 13px; }
.detail-table :deep(.el-table__body-wrapper) {
  overflow-y: auto;
}
.formula-col-header {
  border-bottom: 1px dashed #909399;
  cursor: help; padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help; padding-bottom: 1px;
  color: #303133; font-weight: 500;
}

/* 合计行 */
.subtotals-bar {
  display: flex; align-items: center; gap: 16px;
  padding: 10px 12px; margin-top: 12px;
  background: #f0f9ff; border-radius: 6px; font-size: 13px;
  flex-wrap: wrap;
}
.subtotal-label { font-weight: 600; color: #303133; }
.subtotal-item { color: #606266; }

/* 编制提示 */
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
