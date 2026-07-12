<template>
  <div class="n3-tab-detail">
    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>递延所得税负债明细表 N3-2</span>
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

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>明细表规则：</strong>
        递延所得税负债 = 应纳税暂时性差异 × 适用税率（ROUND 2位）。
        应纳税暂时性差异 = 账面价值 − 计税基础（正值→递延税负债）。
        商誉初始确认/长期股权投资拟长期持有为特殊项，不确认递延税负债。
        合计行与N3-1审定表交叉验证。
      </div>
    </div>

    <!-- ═══ 统计摘要区 ═══ -->
    <div class="summary-bar">
      <div class="summary-item">
        <span class="summary-label">差异项目数</span>
        <span class="summary-value">{{ summary.itemCount }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">应纳税差异合计</span>
        <span class="summary-value">{{ fmtAmount(summary.taxableDiffTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">递延税负债合计</span>
        <span class="summary-value">{{ fmtAmount(summary.endDtlTotal) }}</span>
      </div>
      <div class="summary-item">
        <span class="summary-label">加权平均税率</span>
        <span class="summary-value">{{ (summary.weightedAvgRate * 100).toFixed(2) }}%</span>
      </div>
      <div class="summary-item" :class="{ 'summary-item--warn': summary.reversedCount > 0 }">
        <span class="summary-label">已转回项</span>
        <span class="summary-value">{{ summary.reversedCount }}</span>
      </div>
    </div>

    <!-- ═══ 明细表格 ═══ -->
    <el-table
      :data="rows"
      border
      size="small"
      style="width: 100%"
      :row-class-name="getRowClassName"
      empty-text="暂无明细行，点击下方按钮新增"
    >
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <el-table-column prop="itemName" label="应纳税暂时性差异项目" min-width="180" fixed>
        <template #default="{ row }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.itemName"
              size="small"
              placeholder="项目名称"
              @change="(val: string) => handleUpdate(row.id, 'itemName', val)"
            />
          </template>
          <span v-else>
            {{ row.itemName }}
            <el-tag v-if="row.isSpecialNonRecognition" type="warning" size="small" class="special-tag">
              不确认递延税负债
            </el-tag>
          </span>
        </template>
      </el-table-column>

      <el-table-column prop="category" label="分类" width="110">
        <template #default="{ row }">
          <template v-if="!isReadonly">
            <el-select
              :model-value="row.category"
              size="small"
              @change="(val: string) => handleUpdate(row.id, 'category', val)"
            >
              <el-option v-for="c in CATEGORIES" :key="c" :label="c" :value="c" />
            </el-select>
          </template>
          <span v-else>{{ row.category }}</span>
        </template>
      </el-table-column>

      <!-- 期初区段 -->
      <el-table-column label="期初" align="center">
        <el-table-column prop="bookValue" label="账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.bookValue"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row.id, 'bookValue', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.bookValue) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="taxBase" label="计税基础" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.taxBase"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row.id, 'taxBase', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.taxBase) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="暂时性差异" min-width="120" align="right">
          <template #header>
            <el-tooltip content="应纳税暂时性差异 = 账面价值 − 计税基础" placement="top">
              <span class="formula-header">暂时性差异</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 账面价值 − 计税基础" placement="top">
              <span class="formula-cell" :class="{ 'num-negative': row.taxableDiff < 0 }">
                {{ fmtAmount(row.taxableDiff) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 税率 -->
      <el-table-column prop="taxRate" label="适用税率" width="100" align="right">
        <template #default="{ row }">
          <template v-if="!isReadonly">
            <el-input-number
              :model-value="row.taxRate"
              :controls="false"
              :precision="4"
              size="small"
              style="width:100%"
              :min="0"
              :max="1"
              @change="(val: number | undefined) => handleUpdate(row.id, 'taxRate', val ?? 0)"
            />
          </template>
          <span v-else class="num-cell">{{ (row.taxRate * 100).toFixed(2) }}%</span>
        </template>
      </el-table-column>

      <!-- 递延税负债区段 -->
      <el-table-column label="递延所得税负债" align="center">
        <el-table-column prop="beginDtl" label="期初余额" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.beginDtl"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row.id, 'beginDtl', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.beginDtl) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="recognized" label="本期确认" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.recognized"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row.id, 'recognized', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.recognized) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="reversed" label="本期转回" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="!isReadonly">
              <el-input-number
                :model-value="row.reversed"
                :controls="false"
                :precision="2"
                size="small"
                style="width:100%"
                @change="(val: number | undefined) => handleUpdate(row.id, 'reversed', val ?? 0)"
              />
            </template>
            <span v-else class="num-cell">{{ fmtAmount(row.reversed) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期末余额" min-width="130" align="right">
          <template #header>
            <el-tooltip content="期末递延税负债 = ROUND(暂时性差异 × 税率, 2)" placement="top">
              <span class="formula-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= ROUND(应纳税暂时性差异 × 适用税率, 2)" placement="top">
              <span
                class="formula-cell"
                :class="{
                  'num-negative': row.endDtl < 0,
                  'special-zero': row.isSpecialNonRecognition && row.endDtl === 0,
                }"
              >
                {{ row.isSpecialNonRecognition ? '—（不确认）' : fmtAmount(row.endDtl) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column prop="remark" label="备注" min-width="150">
        <template #default="{ row }">
          <template v-if="!isReadonly">
            <el-input
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @change="(val: string) => handleUpdate(row.id, 'remark', val)"
            />
          </template>
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button text type="danger" size="small" @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="totals-bar">
      <span class="totals-label">合计</span>
      <span class="totals-item">暂时性差异: <strong>{{ fmtAmount(summary.taxableDiffTotal) }}</strong></span>
      <span class="totals-item">期末递延税负债: <strong>{{ fmtAmount(summary.endDtlTotal) }}</strong></span>
      <span v-if="crossValidationDiff !== 0" class="totals-item totals-diff">
        ⚠ 与N3-1审定表差异: {{ fmtAmount(crossValidationDiff) }}
      </span>
    </div>

    <!-- ═══ 新增行按钮 ═══ -->
    <div v-if="!isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" @click="handleAddRow">+ 新增应纳税暂时性差异项目</el-button>
    </div>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>递延所得税负债（2901）为<strong>负债类贷方科目</strong></li>
        <li>应纳税暂时性差异 = 账面价值 − 计税基础（正值→递延税负债）</li>
        <li>递延所得税负债 = 应纳税暂时性差异 × 适用税率（ROUND 2位小数）</li>
        <li>适用税率填小数格式（如 0.25 = 25%），系统自动计算</li>
        <li>特殊项（商誉初始确认/长期股权投资拟长期持有）不确认递延所得税负债，琥珀色标注</li>
        <li>期末递延税负债为0且期初>0的已转回项灰色标记</li>
        <li>合计行与N3-1审定表交叉验证，差异红色提示</li>
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
  </div>
</template>

<script setup lang="ts">
/**
 * N3TabDetail — N3-2 递延所得税负债明细表
 *
 * Spec: .kiro/specs/n3-deferred-tax-liabilities/
 * Task: 4.3
 * Requirements: 3.1-3.6
 *
 * 核心职责：
 * - 14列14公式：应纳税暂时性差异=账面-计税基础；递延税负债=差异×税率(ROUND 2)
 * - 动态行新增（ElMessageBox.prompt输入项目名称，铁律！必须先命名）
 * - 统计摘要：差异项目数/应纳税差异合计/递延税负债合计/加权平均税率
 * - 转回项（期末=0）灰色标记
 * - 特殊项（商誉/长期股权投资）琥珀色标注"不确认递延税负债"
 * - 合计行与N3-1审定表交叉验证
 * - 导入导出 el-dropdown 三级
 *
 * 科目：2901 递延所得税负债（贷方/负债类！）
 */
import { ref, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, ChatDotSquare, ArrowDown } from '@element-plus/icons-vue'
import { useN3FormData } from '../../composables/useN3FormData'
import { useN3Detail } from '../../composables/useN3Detail'
import { useN3ImportExport } from '../../composables/useN3ImportExport'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
  projectId?: string
}>()

// ─── Constants ───────────────────────────────────────────────────────────────

/** N3-1审定表分类选项（对应SUMIF汇总） */
const CATEGORIES = [
  '固定资产折旧差异',
  '公允价值变动',
  '一次性税前扣除',
  '长期股权投资',
  '商誉',
  '其他',
]

// ─── Inject 复核对话 ─────────────────────────────────────────────────────────

const openReviewDialog = inject<((section: string) => void) | undefined>(
  'openReviewDialog',
  undefined,
)

// ─── FormData ────────────────────────────────────────────────────────────────

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId || '')

const formData = useN3FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── useN3Detail ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => {
  // 兼容 ComputedRef<Map> | Map 两种传入方式
  const r = props.allResponses
  return r instanceof Map ? r : new Map()
})

const {
  rows,
  summary,
  reversedRowIds,
  specialRowIds,
  addRow,
  removeRow,
  updateRow,
  syncSummary,
} = useN3Detail({
  allResponses: allResponsesRef,
  saveField: formData.setField,
  getField: formData.getField,
})

// ─── useN3ImportExport ───────────────────────────────────────────────────────

const {
  isExporting,
  isImporting,
  exportTemplate,
  exportData,
  importData,
} = useN3ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
})

// ─── State ───────────────────────────────────────────────────────────────────

const fileInputRef = ref<HTMLInputElement | null>(null)
const isReadonly = computed(() => props.isReadonly ?? false)

// ─── 交叉验证差异（与N3-1审定表） ────────────────────────────────────────────

const crossValidationDiff = computed(() => {
  // N3-1审定表期末递延税负债合计存储在 allResponses
  const adjItem = allResponsesRef.value.get('N3-1-end-balance-total')
  if (!adjItem?.conclusion) return 0
  let adjTotal = 0
  try { adjTotal = JSON.parse(adjItem.conclusion) } catch { adjTotal = Number(adjItem.conclusion) || 0 }
  return Math.round((summary.value.endDtlTotal - adjTotal) * 100) / 100
})

// ─── 行样式：转回行灰色/特殊项琥珀色 ───────────────────────────────────────

function getRowClassName({ row }: { row: any }): string {
  if (specialRowIds.value.has(row.id)) return 'special-row-highlight'
  if (reversedRowIds.value.has(row.id)) return 'reversed-row-highlight'
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
  // 同步合计到独立字段（供N3-1审定表交叉验证）
  await syncSummary()
}

// ─── 新增行（ElMessageBox.prompt 输入项目名称，铁律！必须先命名） ─────────────

async function handleAddRow() {
  try {
    const { value: itemName } = await ElMessageBox.prompt(
      '请输入应纳税暂时性差异项目名称（如：固定资产折旧差异、公允价值变动）',
      '新增明细项目',
      {
        confirmButtonText: '确认新增',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '项目名称不能为空',
        inputPlaceholder: '应纳税暂时性差异项目名称',
      },
    )
    await addRow(itemName, '其他')
    await syncSummary()
    ElMessage.success(`已新增：${itemName}`)
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
    await syncSummary()
    ElMessage.success('已删除')
  } catch {
    // 用户取消
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      exportTemplate('N3-2')
      break
    case 'exportData':
      exportData('N3-2')
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
  await importData(file, 'N3-2')
  input.value = '' // reset
}

// ─── AI辅助 / 复核 ──────────────────────────────────────────────────────────

function handleAiAssist() {
  ElMessage.info('AI辅助分析递延所得税负债明细...')
}

function handleReview() {
  if (openReviewDialog) {
    openReviewDialog('N3-2-明细表')
  } else {
    ElMessage.info('复核对话未配置')
  }
}
</script>

<style scoped>
.n3-tab-detail {
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

/* ─── 方法论上下文（琥珀色左边线+浅黄背景） ─── */
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
  color: #e6a23c;
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
  color: #e6a23c;
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

.num-negative {
  color: #f56c6c;
  font-weight: 600;
}

/* ─── 特殊项（不确认递延税负债）琥珀色标注 ─── */
.special-tag {
  margin-left: 4px;
  font-size: 11px;
}

.special-zero {
  color: #e6a23c;
  font-style: italic;
}

/* ─── 转回行灰色背景 ─── */
:deep(.reversed-row-highlight) {
  background-color: #f5f7fa !important;
  color: #909399;
}

:deep(.reversed-row-highlight:hover > td) {
  background-color: #ebeef5 !important;
}

/* ─── 特殊项琥珀色背景 ─── */
:deep(.special-row-highlight) {
  background-color: #fdf6ec !important;
}

:deep(.special-row-highlight:hover > td) {
  background-color: #faecd8 !important;
}

/* ─── 表格统一 ─── */
:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

:deep(.el-table th .cell) {
  font-size: var(--wp-font-size, 13px);
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
  font-size: var(--wp-font-size, 13px);
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

/* ─── 新增行按钮 ─── */
.add-row-bar {
  text-align: center;
  margin: 12px 0;
}

/* ─── 编制提示折叠 ─── */
.n3-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.n3-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
  margin-bottom: 8px;
}

.n3-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
