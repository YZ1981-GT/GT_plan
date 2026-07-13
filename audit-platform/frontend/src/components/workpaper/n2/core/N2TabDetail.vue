<template>
  <div class="n2-tab-detail">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>应交税费明细表 N2-2</span>
        <el-tag type="danger" size="small" class="liability-tag">负债类·贷方</el-tag>
      </div>
      <div class="section-actions">
        <!-- 导入导出 -->
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 负债类公式提示 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>明细表规则：</strong>
        各税种期末余额 = 期初余额 + 本期计提（贷方增加）− 本期缴纳（借方减少）。
        差异 = 账面期末 − 申报表金额，差异行自动红色高亮。22个公式自动计算。
      </div>
    </div>

    <!-- ═══ 统计摘要区 ═══ -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-label">税种数</span>
        <span class="summary-value">{{ summary.taxTypeCount }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">计提合计</span>
        <span class="summary-value">{{ fmtAmount(summary.accrualTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">缴纳合计</span>
        <span class="summary-value">{{ fmtAmount(summary.paymentTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">期末合计</span>
        <span class="summary-value">{{ fmtAmount(summary.endBalanceTotal) }}</span>
      </div>
      <div class="summary-item" :class="{ 'summary-item--warn': summary.diffRowCount > 0 }">
        <span class="summary-label">差异行</span>
        <span class="summary-value">{{ summary.diffRowCount }}</span>
      </div>
    </div>

    <!-- ═══ 区段 Tab 切换 ═══ -->
    <el-tabs v-model="activeSection" class="detail-tabs">
      <!-- ─── 基础信息 ─── -->
      <el-tab-pane label="基础信息" name="basic">
        <el-table
          :data="rows"
          border
          size="small"
          style="width: 100%"
          :row-class-name="getRowClassName"
          empty-text="暂无明细行，点击下方按钮新增"
        >
          <el-table-column label="序号" width="55" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="taxType" label="税种" min-width="120">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input :model-value="row.taxType" size="small" placeholder="税种"
                  @input="(val: string) => handleUpdate(row.id, 'taxType', val)" />
              </template>
              <span v-else>{{ row.taxType }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="subItem" label="明细子目" min-width="160">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input :model-value="row.subItem" size="small" placeholder="子目"
                  @input="(val: string) => handleUpdate(row.id, 'subItem', val)" />
              </template>
              <span v-else>{{ row.subItem || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="taxBase" label="计税依据" min-width="130" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.taxBase" :controls="false" :precision="2" size="small"
                  style="width:100%"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'taxBase', val ?? 0)" />
              </template>
              <span v-else>{{ fmtAmount(row.taxBase) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="taxRate" label="税率(%)" width="100" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.taxRate" :controls="false" :precision="4" size="small"
                  style="width:100%" :min="0" :max="1"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'taxRate', val ?? 0)" />
              </template>
              <span v-else>{{ (row.taxRate * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
            <template #default="{ row }">
              <el-button text type="danger" size="small" @click="handleRemoveRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ─── 计提缴纳 ─── -->
      <el-tab-pane label="计提缴纳" name="accrual-payment">
        <el-table
          :data="rows"
          border
          size="small"
          style="width: 100%"
          :row-class-name="getRowClassName"
          empty-text="暂无明细行"
        >
          <el-table-column label="序号" width="55" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="taxType" label="税种" min-width="100" />
          <el-table-column prop="subItem" label="子目" min-width="130" />
          <el-table-column prop="beginning" label="期初余额" min-width="120" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.beginning" :controls="false" :precision="2" size="small"
                  style="width:100%"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'beginning', val ?? 0)" />
              </template>
              <span v-else>{{ fmtAmount(row.beginning) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期计提" min-width="120" align="right">
            <template #header>
              <el-tooltip content="贷方增加（计提）" placement="top">
                <span class="formula-header">本期计提</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.accrual" :controls="false" :precision="2" size="small"
                  style="width:100%"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'accrual', val ?? 0)" />
              </template>
              <span v-else>{{ fmtAmount(row.accrual) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期缴纳" min-width="120" align="right">
            <template #header>
              <el-tooltip content="借方减少（缴纳）" placement="top">
                <span class="formula-header">本期缴纳</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.payment" :controls="false" :precision="2" size="small"
                  style="width:100%"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'payment', val ?? 0)" />
              </template>
              <span v-else>{{ fmtAmount(row.payment) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" min-width="120" align="right">
            <template #header>
              <el-tooltip content="期末 = 期初 + 计提(贷方) − 缴纳(借方)（负债类）" placement="top">
                <span class="formula-header">期末余额</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-tooltip content="期末 = 期初 + 计提 − 缴纳（负债类贷方）" placement="top">
                <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ─── 核对 ─── -->
      <el-tab-pane label="核对" name="reconcile">
        <el-table
          :data="rows"
          border
          size="small"
          style="width: 100%"
          :row-class-name="getRowClassName"
          empty-text="暂无明细行"
        >
          <el-table-column label="序号" width="55" align="center">
            <template #default="{ $index }">{{ $index + 1 }}</template>
          </el-table-column>
          <el-table-column prop="taxType" label="税种" min-width="100" />
          <el-table-column prop="subItem" label="子目" min-width="130" />
          <el-table-column label="账面期末" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmount(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="申报表金额" min-width="130" align="right">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input-number :model-value="row.declaredAmount" :controls="false" :precision="2" size="small"
                  style="width:100%"
                  @change="(val: number | undefined) => handleUpdate(row.id, 'declaredAmount', val ?? 0)" />
              </template>
              <span v-else>{{ fmtAmount(row.declaredAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" min-width="110" align="right">
            <template #header>
              <el-tooltip content="差异 = 账面期末 − 申报表金额" placement="top">
                <span class="formula-header">差异</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="['formula-cell', { 'diff-cell': Math.abs(row.diff) > 0.01 }]">
                {{ fmtAmount(row.diff) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="conclusion" label="核查结论" min-width="160">
            <template #default="{ row }">
              <template v-if="!isReadonly">
                <el-input :model-value="row.conclusion" size="small" placeholder="核查结论"
                  @input="(val: string) => handleUpdate(row.id, 'conclusion', val)" />
              </template>
              <span v-else>{{ row.conclusion || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- ═══ 新增行 ═══ -->
    <div v-if="!isReadonly" class="add-row-bar">
      <el-button size="small" @click="handleAddRow">+ 新增税种明细行</el-button>
    </div>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应交税费（2221）为<strong>负债类贷方科目</strong>：期末 = 期初 + 计提（贷方）− 缴纳（借方）</li>
        <li>基础信息Tab：税种/子目/计税依据/适用税率（小数格式如0.07=7%）</li>
        <li>计提缴纳Tab：期初余额/本期计提/本期缴纳/期末余额（22个公式列自动计算）</li>
        <li>核对Tab：账面期末与申报表金额比对，差异行自动红色背景</li>
        <li>新增行需先输入税种/子目名称，确认后创建</li>
        <li>支持导入导出（模板/数据/xlsx）</li>
      </ul>
    </details>

    <!-- ═══ 隐藏文件上传 ═══ -->
    <input
      ref="fileInputRef"
      type="file"
      accept=".xlsx,.xls"
      style="display:none"
      @change="handleFileSelected"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabDetail — N2-2 应交税费明细表
 *
 * Spec: .kiro/specs/n2-taxes-payable/
 * Task: 4.3
 * Requirements: 3.1-3.6
 *
 * 核心职责：
 * - 23列区段Tab（基础/计提缴纳/核对）
 * - 22公式自动计算：期末=期初+计提-缴纳（负债类）；差异=账面-申报表
 * - 差异行红色背景（diffRowIds computed）
 * - 动态行新增（ElMessageBox.prompt输入税种/子目）
 * - 统计摘要：税种数/计提合计/缴纳合计/期末合计
 * - 导入导出三级
 *
 * 科目：2221 应交税费（贷方/负债类！）
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown } from '@element-plus/icons-vue'
import { useN2FormData } from '../../composables/useN2FormData'
import { useN2Detail, type N2DetailTabSection } from '../../composables/useN2Detail'
import { useN2ImportExport } from '../../composables/useN2ImportExport'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const formData = useN2FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── useN2Detail ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  summary,
  diffRowIds,
  addRow,
  removeRow,
  updateRow,
  syncSummary,
} = useN2Detail({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
})

// ─── useN2ImportExport ───────────────────────────────────────────────────────

const {
  isExporting,
  isImporting,
  exportTemplate,
  exportData,
  importData,
} = useN2ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── State ───────────────────────────────────────────────────────────────────

const activeSection = ref<N2DetailTabSection>('basic')
const fileInputRef = ref<HTMLInputElement | null>(null)
const isReadonly = computed(() => props.isReadonly ?? false)

// ─── 行样式：差异行红色背景 ─────────────────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (diffRowIds.value.has(row.id)) return 'diff-row-highlight'
  return ''
}

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 更新行字段 ──────────────────────────────────────────────────────────────

async function handleUpdate(rowId: string, field: string, value: any) {
  await updateRow(rowId, field as any, value)
}

// ─── 新增行（ElMessageBox.prompt 输入税种/子目名称） ─────────────────────────

async function handleAddRow() {
  try {
    const { value: taxType } = await ElMessageBox.prompt(
      '请输入税种名称（如：增值税、城建税、房产税）',
      '新增税种明细',
      {
        confirmButtonText: '下一步',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '税种名称不能为空',
        inputPlaceholder: '税种名称',
      },
    )
    const { value: subItem } = await ElMessageBox.prompt(
      `请输入"${taxType}"的明细子目名称（如：应交增值税-销项税额）`,
      '新增明细子目',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPlaceholder: '明细子目（可选）',
      },
    )
    await addRow(taxType, subItem || '')
    ElMessage.success(`已新增：${taxType} - ${subItem || '(无子目)'}`)
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

async function handleRemoveRow(rowId: string) {
  try {
    await ElMessageBox.confirm('确认删除该明细行？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    await removeRow(rowId)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('N2-2')
      break
    case 'exportData':
      exportData('N2-2')
      break
    case 'importData':
      fileInputRef.value?.click()
      break
  }
}

async function handleFileSelected(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importData(file, 'N2-2')
  input.value = '' // reset
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n2-detail',
      prompt: '请基于应交税费底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N2-2-明细表')
  } else {
    ElMessage.info('复核对话未配置')
  }
}
</script>

<style scoped>
.n2-tab-detail {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title {
  display: flex;
  align-items: center;
  gap: 10px;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.liability-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: var(--wp-font-size, 13px);
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 统计摘要区 ─── */
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f5f7fa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
}

.summary-item--warn {
  color: #f56c6c;
}

.summary-label {
  font-size: 12px;
  color: #909399;
}

.summary-value {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.summary-item--warn .summary-value {
  color: #f56c6c;
}

/* ─── Tabs ─── */
.detail-tabs {
  margin-bottom: 12px;
}

/* ─── 公式列样式 ─── */
.formula-header {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
  font-weight: 600;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
  padding-bottom: 1px;
}

.diff-cell {
  color: #f56c6c;
  font-weight: 700;
}

/* ─── 差异行红色背景 ─── */
:deep(.diff-row-highlight) {
  background-color: #fef0f0 !important;
}

:deep(.diff-row-highlight:hover > td) {
  background-color: #fde2e2 !important;
}

/* ─── 表格统一 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
}

/* ─── 新增行按钮 ─── */
.add-row-bar {
  text-align: center;
  margin: 12px 0;
}

/* ─── 编制提示折叠 ─── */
.n2-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n2-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n2-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
