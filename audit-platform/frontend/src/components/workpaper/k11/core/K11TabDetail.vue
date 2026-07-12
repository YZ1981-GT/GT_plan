<template>
  <div class="k11-tab-detail">
    <!-- ═══ Section标题 + 导入导出 + AI + 复核 ═══ -->
    <div class="section-header">
      <h3>K11-2 资产减值损失明细表</h3>
      <div class="header-actions">
        <el-dropdown size="small" trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p>明细表K11-2按资产类别逐项列示减值损失明细，与各来源底稿（F2/H1/I1/I3等）交叉核对。<strong>差异=本期发生额−源底稿计提金额</strong>，差异非零红色高亮。<strong>商誉减值不可转回</strong>（CAS8）。</p>
    </div>

    <!-- ═══ 2区段Tab切换（el-segmented）+ 新增按钮 ═══ -->
    <div class="tab-bar">
      <el-segmented
        v-model="activeTab"
        :options="tabOptions"
        size="small"
      />
      <div class="tab-right">
        <span class="row-count">共 {{ rows.length }} 行</span>
        <el-button size="small" type="success" plain :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增
        </el-button>
      </div>
    </div>

    <!-- ═══ 明细表主表（50行，max-height控制） ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
      max-height="580"
      :row-class-name="detailRowClass"
    >
      <!-- 序号（所有区段共享） -->
      <el-table-column type="index" label="序号" width="52" align="center" fixed />

      <!-- ═══ 基础区段 ═══ -->
      <template v-if="activeTab === 'basic'">
        <el-table-column prop="assetCategory" label="资产类别" min-width="130">
          <template #default="{ row }">
            <span class="asset-category">{{ row.assetCategory }}</span>
            <el-tag v-if="row.isNonReversible" size="small" type="warning" class="no-reversal-tag">不可转回</el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="impairmentItem" label="减值项目" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !isReadonly"
              :model-value="row.impairmentItem"
              size="small"
              placeholder="减值项目名称"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'impairmentItem', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.impairmentItem || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期计提" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.currentProvision"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100px"
              @change="(v: number | undefined) => handleCellChange(row.rowKey, 'currentProvision', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmtNum(row.currentProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期转回" width="120" align="right">
          <template #header>
            <el-tooltip content="商誉减值不可转回（CAS8）" placement="top">
              <span>本期转回</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly && !row.isNonReversible"
              :model-value="row.currentReversal"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 100px"
              @change="(v: number | undefined) => handleCellChange(row.rowKey, 'currentReversal', v ?? 0)"
            />
            <span v-else-if="row.isNonReversible" class="disabled-cell">—</span>
            <span v-else class="formula-cell">{{ fmtNum(row.currentReversal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" width="120" align="right">
          <template #header>
            <el-tooltip content="公式：本期计提 − 本期转回" placement="top">
              <span class="formula-header">本期发生额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 本期计提 − 本期转回" placement="top">
              <span class="formula-cell formula-underline">{{ fmtNum(row.currentOccurrence) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="55" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.isEditable && !isReadonly"
              type="danger"
              link
              size="small"
              @click="handleRemoveRow(row.rowKey)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ 核对区段 ═══ -->
      <template v-if="activeTab === 'reconcile'">
        <el-table-column prop="assetCategory" label="资产类别" min-width="120" fixed />
        <el-table-column label="本期发生额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtNum(row.currentOccurrence) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="sourceWp" label="来源底稿" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.sourceWp" size="small" type="info" class="source-tag">{{ row.sourceWp }}</el-tag>
            <span v-else class="empty-cell">—</span>
          </template>
        </el-table-column>
        <el-table-column label="源底稿计提金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.isEditable && !isReadonly"
              :model-value="row.sourceAmount"
              size="small"
              :controls="false"
              :precision="2"
              style="width: 110px"
              @change="(v: number | undefined) => handleCellChange(row.rowKey, 'sourceAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmtNum(row.sourceAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异" width="110" align="right">
          <template #header>
            <el-tooltip content="公式：本期发生额 − 源底稿计提金额" placement="top">
              <span class="formula-header">差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 本期发生额 − 源底稿计提金额" placement="top">
              <span
                class="formula-cell formula-underline"
                :class="{ 'variance-nonzero': Math.abs(row.variance) >= 0.01 }"
              >
                {{ fmtNum(row.variance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="凭证" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !isReadonly"
              :model-value="row.voucherRef"
              size="small"
              placeholder="凭证编号/抽查"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'voucherRef', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.voucherRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="结论" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="row.isEditable && !isReadonly"
              :model-value="row.conclusion"
              size="small"
              placeholder="核查结论"
              @blur="(e: FocusEvent) => handleCellChange(row.rowKey, 'conclusion', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="55" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="row.isEditable && !isReadonly"
              type="danger"
              link
              size="small"
              @click="handleRemoveRow(row.rowKey)"
            >
              <el-icon><Delete /></el-icon>
            </el-button>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- ═══ 合计行（底部固定加粗） ═══ -->
    <div class="subtotal-bar">
      <span class="total-label">合  计</span>
      <span class="total-item">本期计提: <strong>{{ fmtNum(subtotal.currentProvision) }}</strong></span>
      <span class="total-item">本期转回: <strong>{{ fmtNum(subtotal.currentReversal) }}</strong></span>
      <span class="total-item">本期发生额: <strong>{{ fmtNum(subtotal.currentOccurrence) }}</strong></span>
      <span class="total-item">源底稿合计: <strong>{{ fmtNum(subtotal.sourceAmount) }}</strong></span>
      <span class="total-item" :class="{ 'variance-highlight': Math.abs(subtotal.variance) >= 0.01 }">
        差异合计: <strong>{{ fmtNum(subtotal.variance) }}</strong>
      </span>
      <span class="total-item">共 <strong>{{ rows.length }}</strong> 行</span>
    </div>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="k11-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>明细表K11-2列示各资产类别减值损失的本期计提/转回/发生额</li>
        <li><strong>2区段Tab切换</strong>：基础（序号/资产类别/减值项目/本期计提/本期转回/本期发生额）| 核对（来源底稿/源底稿计提金额/差异/凭证/结论）</li>
        <li><strong>本期发生额 = 本期计提 − 本期转回</strong></li>
        <li><strong>差异 = 本期发生额 − 源底稿计提金额</strong>，差异非零行红色高亮</li>
        <li><strong>商誉减值不可转回</strong>（CAS8），商誉行"本期转回"列灰色禁用</li>
        <li>新增行需先输入<strong>资产类别名称</strong>（弹窗确认），系统自动关联来源底稿</li>
        <li>合计行应与K11-1审定表合计保持一致（交叉勾稽）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K11TabDetail.vue — K11-2 资产减值损失明细表
 * 18列×50行 → 2区段Tab（基础/核对）+ 动态行 + 导入导出
 *
 * 核心特性：
 * - 2区段Tab切换（行保持同步）：基础信息 | 核对
 * - 差异非零行红色标记（row class binding）
 * - 商誉减值不可转回（CAS8）：商誉行"本期转回"列灰色禁用
 * - 合计行（底部加粗）
 * - 50行动态行管理 + 新增按钮（ElMessageBox.prompt确认资产类别名）
 * - 导入导出 el-dropdown（使用useK11ImportExport）
 * - 公式列虚线下划线+cursor:help+tooltip
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/ | Task: 4.3
 * Requirements: 3.1-3.5, 4.5
 */
import { inject, ref, toRef, type Ref } from 'vue'
import { ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown, Plus, Delete } from '@element-plus/icons-vue'
import { useK11Detail, DETAIL_TABS, type K11DetailTabKey } from '../../composables/useK11Detail'
import { useK11ImportExport } from '../../composables/useK11ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

// ─── 复核对话 inject ─────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, label?: string) => void>('openReviewDialog', () => {})

// ─── Tab state ───────────────────────────────────────────────────────────────
const activeTab = ref<K11DetailTabKey>('basic')
const tabOptions = DETAIL_TABS.map(t => ({ label: t.label, value: t.key }))

// ─── Composable wiring ───────────────────────────────────────────────────────
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  rows,
  subtotal,
  updateCell,
  addRow,
  removeRow,
} = useK11Detail({
  allResponses: allResponsesRef,
  projectId: toRef(props, 'projectId') as Ref<string>,
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
  onSave: (itemId: string, value: any) => {
    emit('save', itemId, value)
  },
})

// ─── 导入导出 composable ─────────────────────────────────────────────────────
const { exportTemplate, exportData, importData } = useK11ImportExport({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  sheetCode: 'K11-2',
})

// ─── Handlers ────────────────────────────────────────────────────────────────

function handleCellChange(rowKey: string, field: string, value: any): void {
  updateCell(rowKey, field, value)
}

async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产类别名称', '新增减值明细', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPlaceholder: '如：存货跌价、固定资产减值、商誉减值等',
      inputValidator: (v: string) => {
        if (!v || !v.trim()) return '资产类别不能为空'
        return true
      },
    })
    if (value && value.trim()) {
      addRow(value.trim())
    }
  } catch {
    // cancelled
  }
}

function handleRemoveRow(rowKey: string): void {
  removeRow(rowKey)
}

function handleImportExport(command: string): void {
  switch (command) {
    case 'export-template': exportTemplate(); break
    case 'export-data': exportData(); break
    case 'import-data': triggerImport(); break
  }
}

/** 触发文件选择器进行导入 */
function triggerImport(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls,.csv'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (file) await importData(file)
  }
  input.click()
}

function handleAiGenerate(): void {
  emit('save', 'K11-2-ai-trigger', { remark: 'generate' })
}

function handleReview(): void {
  openReviewDialog('K11-2', '资产减值损失明细表复核')
}

// ─── Row class binding：差异非零行红色标记 ───────────────────────────────────
function detailRowClass({ row }: { row: any }): string {
  if (Math.abs(row.variance) >= 0.01) return 'variance-row'
  return ''
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtNum(v: number | null | undefined): string {
  if (v === null || v === undefined) return '-'
  if (v === 0) return '0.00'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k11-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }

/* ─── Section header ─── */
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }

/* ─── 方法论上下文（琥珀色块） ─── */
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }

/* ─── Tab栏 ─── */
.tab-bar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.tab-right { display: flex; align-items: center; gap: 10px; }
.row-count { font-size: 12px; color: #909399; }

/* ─── 表格 ─── */
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.asset-category { font-size: var(--wp-font-size, 13px); color: #303133; font-weight: 500; }
.no-reversal-tag { margin-left: 4px; font-size: 10px; }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.formula-header { border-bottom: 1px dashed #909399; cursor: help; }
.disabled-cell { color: #c0c4cc; font-style: italic; }
.empty-cell { color: #c0c4cc; }
.source-tag { cursor: default; }

/* ─── 差异非零红色高亮 ─── */
.variance-nonzero { color: #f56c6c !important; font-weight: 600; }
:deep(.variance-row) { background-color: #fef0f0 !important; }
:deep(.variance-row:hover > td) { background-color: #fde2e2 !important; }

/* ─── 合计行（底部加粗） ─── */
.subtotal-bar {
  display: flex; align-items: center; gap: 16px; flex-wrap: wrap;
  margin: 12px 0; padding: 10px 14px;
  background: linear-gradient(90deg, #eef6ff 0%, #f5faff 100%);
  border: 1px solid #d6e4f0; border-radius: 6px; font-size: var(--wp-font-size, 13px);
}
.total-label { font-weight: 700; color: #303133; min-width: 50px; }
.total-item { color: #606266; }
.total-item strong { color: #303133; font-family: 'JetBrains Mono', monospace; }
.variance-highlight { color: #f56c6c !important; }
.variance-highlight strong { color: #f56c6c !important; }

/* ─── 编制提示（折叠底部） ─── */
.k11-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k11-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k11-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
