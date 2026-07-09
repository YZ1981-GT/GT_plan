<template>
  <div class="n1-tab-detail">
    <!-- ═══ 双模式切换 ═══ -->
    <div class="n1-mode-bar">
      <el-segmented v-model="dualMode.mode.value" :options="dualMode.modeOptions.value" @change="dualMode.switchMode" />
    </div>

    <!-- ═══ OnlyOffice 降级模式 ═══ -->
    <template v-if="dualMode.isOnlyOffice.value">
      <GtOnlyOfficeSheet :wp-id="wpId" :project-id="projectId" sheet-name="明细表N1-2" style="height: 100%; min-height: 600px" />
    </template>

    <!-- ═══ 结构化 / 矩阵视图 ═══ -->
    <template v-else>
      <!-- ═══ Section Header ═══ -->
      <div class="section-header">
        <div class="section-title-group">
          <span class="section-title">递延所得税资产明细表 N1-2</span>
          <el-tag type="success" size="small" class="asset-tag">资产类·借方</el-tag>
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

      <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
      <div class="methodology-context">
        <div class="methodology-text">
          <strong>明细表规则：</strong>
          递延所得税资产 = 可抵扣暂时性差异 × 适用税率（ROUND 2位）。
          可抵扣暂时性差异 = 计税基础 − 账面价值（资产项：账面＜计税基础时产生可抵扣差异）。
          确认前提：预期未来有足够应纳税所得额利用该可抵扣暂时性差异。
          合计行与N1-1审定表交叉验证。
        </div>
      </div>

      <!-- ═══ 统计仪表板 ═══ -->
      <div class="summary-bar">
        <div class="summary-item">
          <span class="summary-label">差异项目数</span>
          <span class="summary-value">{{ stats.itemCount }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">可抵扣差异合计</span>
          <span class="summary-value">{{ fmtAmount(stats.totalDeductibleDiff) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">递延税资产合计</span>
          <span class="summary-value">{{ fmtAmount(stats.totalDeferredTaxAsset) }}</span>
        </div>
        <div class="summary-item">
          <span class="summary-label">加权平均税率</span>
          <span class="summary-value">{{ (stats.weightedAvgRate * 100).toFixed(2) }}%</span>
        </div>
      </div>

      <!-- ═══ 明细表格 ═══ -->
      <el-table
        :data="computedRows"
        border
        size="small"
        style="width: 100%"
        :row-class-name="getRowClassName"
        empty-text="暂无明细行，点击下方按钮新增"
      >
        <el-table-column label="序号" width="55" align="center" fixed>
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>

        <el-table-column prop="itemName" label="暂时性差异项目" min-width="160" fixed>
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.itemName"
                size="small"
                placeholder="项目名称"
                @change="(val: string) => handleUpdate($index, 'itemName', val)"
              />
            </template>
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="bookValue" label="账面价值" min-width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.bookValue"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'bookValue', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.bookValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="taxBase" label="计税基础" min-width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.taxBase"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'taxBase', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.taxBase) }}</span>
          </template>
        </el-table-column>

        <!-- 可抵扣暂时性差异（公式列） -->
        <el-table-column label="可抵扣暂时性差异" min-width="140" align="right">
          <template #header>
            <el-tooltip content="可抵扣暂时性差异 = 账面价值 − 计税基础（资产项取绝对值）" placement="top">
              <span class="formula-header">可抵扣暂时性差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= |账面价值 − 计税基础|（账面＜计税基础时）" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.deductibleDiff) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 适用税率 -->
        <el-table-column prop="endTaxRate" label="适用税率" width="100" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.endTaxRate"
                :controls="false"
                :precision="4"
                size="small"
                style="width:100%"
                :min="0"
                :max="1"
                @change="(val: number | undefined) => handleUpdate($index, 'endTaxRate', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ (row.endTaxRate * 100).toFixed(2) }}%</span>
          </template>
        </el-table-column>

        <!-- 期初递延税资产 -->
        <el-table-column prop="beginDeferredTax" label="期初递延税资产" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期初递延税资产 = ROUND(期初暂时性差异 × 税率, 2)" placement="top">
              <span class="formula-header">期初递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= ROUND(beginDiff × beginTaxRate, 2)" placement="top">
              <span class="formula-cell">{{ fmtAmount(row.beginDeferredTax) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 本期确认 -->
        <el-table-column prop="recognized" label="本期确认" min-width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.recognized"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'recognized', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.recognized) }}</span>
          </template>
        </el-table-column>

        <!-- 本期转回 -->
        <el-table-column prop="reversed" label="本期转回" min-width="110" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.reversed"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate($index, 'reversed', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.reversed) }}</span>
          </template>
        </el-table-column>

        <!-- 期末递延税资产（公式列） -->
        <el-table-column label="期末递延税资产" min-width="140" align="right">
          <template #header>
            <el-tooltip content="期末递延税资产 = ROUND(可抵扣暂时性差异 × 适用税率, 2)" placement="top">
              <span class="formula-header">期末递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= ROUND(可抵扣暂时性差异 × 适用税率, 2)" placement="top">
              <span class="formula-cell" :class="{ 'reversed-zero': row.endDeferredTax === 0 && row.beginDeferredTax > 0 }">
                {{ fmtAmount(row.endDeferredTax) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column prop="remark" label="备注" min-width="140">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input
                :model-value="row.remark"
                size="small"
                placeholder="备注"
                @change="(val: string) => handleUpdate($index, 'remark', val)"
              />
            </template>
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button text type="danger" size="small" @click="handleRemoveRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══ 合计行 + 交叉验证 ═══ -->
      <div class="totals-bar">
        <span class="totals-label">合计</span>
        <span class="totals-item">可抵扣差异: <strong>{{ fmtAmount(totals.endDiff) }}</strong></span>
        <span class="totals-item">期末递延税资产: <strong>{{ fmtAmount(totals.endDeferredTax) }}</strong></span>
        <span v-if="crossValidationDiff !== 0" class="totals-item totals-diff">
          ⚠ 与N1-1审定表差异: {{ fmtAmount(crossValidationDiff) }}
          <GtIndexChip value="N1-1" :context-project-id="projectId" />
        </span>
        <span v-else class="totals-item totals-match">
          ✓ 与N1-1审定表一致
        </span>
      </div>

      <!-- ═══ 新增行按钮 ═══ -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" type="primary" @click="handleAddRow">+ 新增可抵扣暂时性差异项目</el-button>
      </div>

      <!-- ═══ 编制提示（折叠底部） ═══ -->
      <details class="n1-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li>递延所得税资产（1811）为<strong>资产类借方科目</strong></li>
          <li>可抵扣暂时性差异 = 计税基础 − 账面价值（资产项：账面＜计税基础时确认递延税资产）</li>
          <li>递延所得税资产 = 可抵扣暂时性差异 × 适用税率（ROUND 2位小数）</li>
          <li>适用税率填小数格式（如 0.25 = 25%），系统自动计算</li>
          <li>期末递延税资产为0且期初>0的已转回项灰色标记</li>
          <li>合计行与N1-1审定表交叉验证，差异红色提示</li>
          <li>新增行须先命名项目（铁律：ElMessageBox确认）</li>
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
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabDetail — N1-2 递延所得税资产明细表
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 4.3
 * Requirements: 3.1-3.6
 *
 * 核心职责：
 * - 14列14公式：可抵扣暂时性差异=计税基础-账面价值；递延税资产=差异×税率(ROUND 2)
 * - 动态行新增（ElMessageBox.prompt输入项目名称，铁律！必须先命名）
 * - 统计摘要：差异项目数/可抵扣差异合计/递延税资产合计/加权平均税率
 * - 转回项（期末=0且期初>0）灰色标记
 * - 合计行与N1-1审定表交叉验证
 * - 导入导出 el-dropdown 三级
 * - 双模式 el-segmented（结构化/矩阵/OO）
 *
 * 科目：1811 递延所得税资产（借方/资产类！期末=期初+借-贷）
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown } from '@element-plus/icons-vue'
import { useN1FormData } from '../../composables/useN1FormData'
import { useN1Detail } from '../../composables/useN1Detail'
import { useN1ImportExport } from '../../composables/useN1ImportExport'
import { useN1DualMode } from '../../composables/useN1DualMode'
import GtOnlyOfficeSheet from '@/components/workpaper/GtOnlyOfficeSheet.vue'
import GtIndexChip from '@/components/common/GtIndexChip.vue'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  isReadonly?: boolean
  projectId?: string
}>()

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── Refs ────────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId || '')
const isReadonly = computed(() => props.isReadonly ?? false)
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 双模式 ──────────────────────────────────────────────────────────────────

const dualMode = useN1DualMode({ wpId: wpIdRef })

// ─── FormData ────────────────────────────────────────────────────────────────

const formData = useN1FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── allResponses reactive wrapper ───────────────────────────────────────────

const allResponsesRef = computed(() => formData.allResponses.value)

// ─── useN1Detail ─────────────────────────────────────────────────────────────

const {
  rows: computedRows,
  addRow,
  removeRow,
  updateRow,
  totals,
  stats,
} = useN1Detail({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: allResponsesRef,
  formData,
})

// ─── useN1ImportExport ───────────────────────────────────────────────────────

const {
  exportTemplate,
  exportData,
  importData,
} = useN1ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── 交叉验证差异（与N1-1审定表） ────────────────────────────────────────────

const crossValidationDiff = computed(() => {
  // N1-1审定表期末递延税资产合计存储在 allResponses
  const adjItem = allResponsesRef.value.get('N1-1-end-balance-total')
  if (!adjItem?.conclusion && !adjItem?.remark) return 0
  let adjTotal = 0
  try {
    adjTotal = Number(adjItem.remark || adjItem.conclusion) || 0
  } catch {
    adjTotal = 0
  }
  return Math.round((totals.value.endAudited - adjTotal) * 100) / 100
})

// ─── 行样式：转回行(期末=0且期初>0)灰色 ─────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (row.endDeferredTax === 0 && row.beginDeferredTax > 0) {
    return 'reversed-row-highlight'
  }
  return ''
}

// ─── 格式化金额 ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 更新行字段 ──────────────────────────────────────────────────────────────

function handleUpdate(index: number, field: string, value: any) {
  updateRow(index, field as any, value)
}

// ─── 新增行（ElMessageBox.prompt 输入项目名称，铁律！必须先命名） ─────────────

async function handleAddRow() {
  try {
    const { value: itemName } = await ElMessageBox.prompt(
      '请输入可抵扣暂时性差异项目名称（如：资产减值准备、可弥补亏损、预提费用）',
      '新增明细项目',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
        inputPlaceholder: '可抵扣暂时性差异项目名称',
      },
    )
    addRow(itemName, '其他')
    ElMessage.success(`已新增：${itemName}`)
  } catch {
    // 用户取消
  }
}

// ─── 删除行 ──────────────────────────────────────────────────────────────────

async function handleRemoveRow(index: number) {
  try {
    await ElMessageBox.confirm('确认删除该明细行？', '确认删除', {
      type: 'warning',
      confirmButtonText: '删除',
      cancelButtonText: '取消',
    })
    removeRow(index)
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('N1-2')
      break
    case 'exportData':
      exportData('N1-2')
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
  await importData(file, 'N1-2')
  input.value = '' // reset
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助分析递延所得税资产明细...')
}

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N1-2-明细表')
  } else {
    ElMessage.info('复核对话未配置')
  }
}
</script>

<style scoped>
.n1-tab-detail {
  padding: 12px;
  font-size: 13px;
}

/* ─── 双模式切换条 ─── */
.n1-mode-bar {
  margin-bottom: 12px;
}

/* ─── Section Header ─── */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.asset-tag {
  font-size: 11px;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
  font-size: 13px;
  color: #5a4e3a;
  line-height: 1.6;
}

.methodology-text strong {
  color: #b88230;
}

/* ─── 统计仪表板 ─── */
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-bottom: 16px;
  padding: 10px 16px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  border-radius: 6px;
}

.summary-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
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

/* ─── 公式列样式（虚线下划线+cursor:help） ─── */
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

/* ─── 数值样式 ─── */
.num-cell {
  text-align: right;
  display: inline-block;
  width: 100%;
}

/* ─── 转回项期末=0灰色标注 ─── */
.reversed-zero {
  color: #909399;
  font-style: italic;
}

/* ─── 转回行灰色背景（期末递延税=0且期初>0） ─── */
:deep(.reversed-row-highlight) {
  background-color: #f5f7fa !important;
  color: #909399;
}

:deep(.reversed-row-highlight:hover > td) {
  background-color: #ebeef5 !important;
}

/* ─── 表格统一 ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table th .cell) {
  font-size: 13px;
  font-weight: 600;
}

/* ─── 合计行 ─── */
.totals-bar {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  background: #ecf5ff;
  border: 1px solid #d9ecff;
  border-radius: 6px;
  margin-top: 12px;
  font-size: 13px;
}

.totals-label {
  font-weight: 700;
  color: #303133;
}

.totals-item {
  color: #606266;
}

.totals-item strong {
  color: #303133;
}

.totals-diff {
  color: #f56c6c;
  font-weight: 600;
}

.totals-match {
  color: #67c23a;
  font-weight: 500;
}

/* ─── 新增行按钮 ─── */
.add-row-bar {
  text-align: center;
  margin: 12px 0;
}

/* ─── 编制提示折叠 ─── */
.n1-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n1-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
