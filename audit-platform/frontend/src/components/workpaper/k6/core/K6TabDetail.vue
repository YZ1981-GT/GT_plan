<template>
  <div class="k6-tab-detail">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>明细表K6-2</strong>：逐项登记持有待售处置组或资产的基本信息、计量数据及分类结论。
        账面价值 = 原值 − 累计折旧摊销 − 减值准备。公允价值净额 = 公允价值 − 预计出售费用。
        合计行应与K6-1审定表交叉验证。</p>
    </div>

    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>存在与完整性：</b>逐项登记的持有待售处置组/资产真实存在且登记完整；</li>
        <li><b>计价和分摊：</b>账面价值与公允价值净额计算准确（账面=原值−累计折旧摊销−减值；净额=公允−出售费用），合计与 K6-1 交叉验证一致；</li>
        <li><b>列报与披露：</b>分类结论恰当。</li>
      </ol>
    </el-alert>

    <!-- ═══ 操作栏：新增 + 导入导出 + AI + 复核 ═══ -->
    <div class="detail-toolbar">
      <div class="toolbar-left">
        <el-button type="primary" size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
        <el-dropdown trigger="click" :disabled="isReadonly" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="toolbar-right">
        <el-button size="small" text type="primary" @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" text @click="handleReview('K6-2')">
          <el-icon><View /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 明细表 el-table（15列） ═══ -->
    <el-table
      :data="detailRows"
      border
      size="small"
      style="width: 100%"
      max-height="640"
      :row-class-name="getRowClassName"
    >
      <el-table-column prop="seqNo" label="序号" width="56" align="center" fixed />
      <el-table-column label="处置组/资产名称" min-width="160" fixed>
        <template #default="{ row }">
          <span class="asset-name">{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="类别" min-width="110">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.category"
            size="small"
            placeholder="选择"
            @change="(v) => handleCellChange(row.rowId, 'category', v)"
          >
            <el-option v-for="opt in categoryOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <span v-else>{{ row.category || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面原值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.costValue"
            :controls="false"
            size="small"
            class="detail-input"
            @change="(v) => handleCellChange(row.rowId, 'costValue', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.costValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="累计折旧摊销" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.accumulatedDep"
            :controls="false"
            size="small"
            class="detail-input"
            @change="(v) => handleCellChange(row.rowId, 'accumulatedDep', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.accumulatedDep) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="减值准备" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.impairmentProvision"
            :controls="false"
            size="small"
            class="detail-input"
            @change="(v) => handleCellChange(row.rowId, 'impairmentProvision', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.impairmentProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账面价值(公式)" min-width="120" align="right" class-name="formula-col">
        <template #header>
          <el-tooltip content="账面价值=原值-累计折旧摊销-减值准备" placement="top">
            <span class="formula-header">账面价值<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.bookValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允价值" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.fairValue"
            :controls="false"
            size="small"
            class="detail-input"
            @change="(v) => handleCellChange(row.rowId, 'fairValue', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.fairValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="出售费用" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!isReadonly"
            v-model="row.sellingCost"
            :controls="false"
            size="small"
            class="detail-input"
            @change="(v) => handleCellChange(row.rowId, 'sellingCost', v ?? 0)"
          />
          <span v-else>{{ fmtAmt(row.sellingCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="公允净额(公式)" min-width="120" align="right" class-name="formula-col">
        <template #header>
          <el-tooltip content="公允价值净额=公允价值-出售费用" placement="top">
            <span class="formula-header">公允净额<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.fairValueNet) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="确认日" min-width="120">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            v-model="row.recognitionDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="(v) => handleCellChange(row.rowId, 'recognitionDate', v ?? '')"
          />
          <span v-else>{{ row.recognitionDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="预计出售日" min-width="120">
        <template #default="{ row }">
          <el-date-picker
            v-if="!isReadonly"
            v-model="row.expectedSaleDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="选择日期"
            style="width: 100%"
            @change="(v) => handleCellChange(row.rowId, 'expectedSaleDate', v ?? '')"
          />
          <span v-else>{{ row.expectedSaleDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="凭证" min-width="90">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.voucherRef"
            size="small"
            placeholder="凭证号"
            @change="(v) => handleCellChange(row.rowId, 'voucherRef', v)"
          />
          <span v-else>{{ row.voucherRef || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="100">
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly"
            v-model="row.conclusion"
            size="small"
            placeholder="选择"
            clearable
            @change="(v) => handleCellChange(row.rowId, 'conclusion', v ?? '')"
          >
            <el-option label="无异常" value="无异常" />
            <el-option label="存在异常" value="存在异常" />
            <el-option label="待核实" value="待核实" />
          </el-select>
          <span v-else>{{ row.conclusion || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" min-width="100">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            v-model="row.remark"
            size="small"
            @change="(v) => handleCellChange(row.rowId, 'remark', v)"
          />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button size="small" text type="danger" @click="handleRemoveRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 底部统计 ═══ -->
    <div class="detail-stats">
      <div class="stat-item">
        <span class="stat-label">处置组/资产数：</span>
        <span class="stat-value">{{ subtotals.count }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">账面价值合计：</span>
        <span class="stat-value">{{ fmtAmt(subtotals.bookValue) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">原值合计：</span>
        <span class="stat-value">{{ fmtAmt(subtotals.costValue) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">减值合计：</span>
        <span class="stat-value">{{ fmtAmt(subtotals.impairmentProvision) }}</span>
      </div>
    </div>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>账面价值 = 原值 − 累计折旧摊销 − 减值准备（自动计算，不可手工修改）</li>
        <li>公允价值净额 = 公允价值 − 预计出售费用（自动计算）</li>
        <li>新增行需先填写处置组/资产名称（ElMessageBox弹窗确认）</li>
        <li>明细表合计应与K6-1审定表账面价值合计交叉验证一致</li>
        <li>凭证号用于追溯原始会计凭证</li>
        <li>导出模板为标准格式，导入数据自动识别列名匹配</li>
      </ul>
    </details>

    <!-- ═══ 隐藏的文件上传input ═══ -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display: none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabDetail.vue — K6-2 明细表（15列12公式，40行动态行）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.3
 * Requirements: 3.1-3.5
 *
 * 功能：
 * - 15列 el-table with dynamic rows
 * - Uses useK6Detail composable
 * - Columns: 序号/名称/类别(select)/原值/折旧/减值/账面价值(公式)/公允/出售费用/
 *            公允净额(公式)/确认日/预计出售日/凭证/结论/备注
 * - "+新增" button (calls addRow → ElMessageBox.prompt)
 * - Import/Export el-dropdown (uses useK6ImportExport)
 * - 底部统计：处置组数/账面价值合计
 * - 40行 max-height virtual scrolling
 */
import { ref, computed, inject } from 'vue'
import { Plus, ArrowDown, MagicStick, View, Delete, QuestionFilled } from '@element-plus/icons-vue'
import { useK6Detail } from '../../composables/useK6Detail'
import { useK6ImportExport } from '../../composables/useK6ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const fileInputRef = ref<HTMLInputElement | null>(null)

const allResponsesRef = computed(() => props.allResponses)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

// ─── Composable wiring ───────────────────────────────────────────────────────

const {
  detailRows,
  subtotals,
  categoryOptions,
  updateCell,
  addRow,
  removeRow,
} = useK6Detail({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', field, value)
  },
})

const {
  isExporting,
  isImporting,
  exportTemplate,
  exportData,
  importData,
} = useK6ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'K6-2',
})

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddRow() {
  await addRow()
}

function handleRemoveRow(idx: number) {
  removeRow(idx)
}

function handleCellChange(rowId: string, field: string, value: any) {
  updateCell(rowId, field, value)
}

async function handleImportExport(command: string) {
  switch (command) {
    case 'export-template':
      await exportTemplate()
      break
    case 'export-data':
      await exportData()
      break
    case 'import-data':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importData(file)
  // Reset input so the same file can be re-selected
  input.value = ''
}

function handleAiGenerate() {
  console.log('[K6-2] AI generate: detail-conclusion')
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── Row class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.conclusion === '存在异常') return 'anomaly-row'
  return ''
}

// ─── 金额格式化 ─────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  font-size: var(--wp-font-size, 13px);
  color: #92400e;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

/* ─── Toolbar ─── */
.detail-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 4px; }

/* ─── 表格样式 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.formula-col) { background-color: #fafff8; }
:deep(.anomaly-row) { background-color: #fef0f0 !important; }
.detail-input { width: 100%; }
.detail-input :deep(.el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.asset-name { font-weight: 500; color: #303133; }

/* ─── 公式列样式 ─── */
.formula-header { cursor: help; }
.formula-icon { margin-left: 4px; font-size: 12px; color: #909399; }
.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 底部统计 ─── */
.detail-stats {
  display: flex;
  gap: 24px;
  margin-top: 14px;
  padding: 10px 16px;
  background: #f5f7fa;
  border-radius: 6px;
}
.stat-item { display: flex; align-items: center; gap: 4px; }
.stat-label { font-size: var(--wp-font-size, 13px); color: #909399; }
.stat-value { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }

/* ─── 编制提示 ─── */
.k6-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}
.k6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
