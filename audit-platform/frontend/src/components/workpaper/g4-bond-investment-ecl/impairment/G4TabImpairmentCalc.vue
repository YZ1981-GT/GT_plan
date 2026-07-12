<!--
  G4TabImpairmentCalc.vue — G4-10 减值准备测算表（19列 → 2区段Tab）

  2区段Tab切换（el-segmented）：
  - Tab1: 未审数+审计调整(11列): 投资项目|①账面余额|现金流量现值|②信用损失率|③减值准备(公式)|④账面价值(公式)|⑤余额调整|②A调整后损失率|⑥减值调整(公式)
  - Tab2: 审定数+差异(8列): 投资项目|⑦审定余额(公式)|⑧审定减值(公式)|⑨审定账面价值(公式)|上年减值|本年计提(公式)|本年转回(公式)|差异说明

  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  按Stage分组：Stage1/Stage2/Stage3 + 分组小计 + 总计行
  公式列：虚线下划线 + cursor:help + el-tooltip显示公式来源

  Spec: .kiro/specs/g4-bond-investment-ecl/ Task 6.1
  Requirements: 3.1, 3.8, 3.9, 3.10, 3.11, 3.12, 3.13, 11.2, 11.5, 11.8
-->
<template>
  <div class="g4-impairment-calc">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：确认债权投资减值准备的计量准确，审定减值、审定账面价值及本年计提/转回金额计算正确，按 Stage 分组恰当。"
      style="margin-bottom: 12px"
    />
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G4-10 减值准备测算表</h3>
      <div class="head-actions">
        <el-segmented v-model="activeTab" :options="segmentOptions" size="small" />
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 投资项目
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-10-impairment-calc')">💬复核</el-button>
      </div>
    </div>

    <!-- Stage分组表格 -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="520"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="impairment-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal">
            <span class="subtotal-label">{{ row._groupLabel }}小计</span>
          </template>
          <template v-else-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 投资项目列（始终显示作为锚定列） -->
      <el-table-column label="投资项目" width="140" fixed>
        <template #default="{ row }">
          <template v-if="row._isSubtotal || row._isTotal" />
          <span v-else>{{ row.investProject }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 未审数+审计调整列 ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="①账面余额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookBalance) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.bookBalance" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'bookBalance', v)" />
              <span v-else>{{ fmtNum(row.bookBalance) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="现金流量现值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.pvFutureCashFlow" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'pvFutureCashFlow', v)" />
              <span v-else>{{ fmtNum(row.pvFutureCashFlow) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②信用损失率" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.creditLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'creditLossRate', v)" />
              <span v-else>{{ (row.creditLossRate * 100).toFixed(2) }}%</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="③减值准备" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentProvision) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="③ = ① × ②" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="④账面价值" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.bookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="④ = ① - ③" placement="top">
                <span class="formula-cell">{{ fmtNum(row.bookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑤余额调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.balanceAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'balanceAdjustment', v)" />
              <span v-else>{{ fmtNum(row.balanceAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="②A调整后损失率" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.adjustedCreditLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="compact-num"
                @change="(v: number) => updateField(row.id, 'adjustedCreditLossRate', v)" />
              <span v-else>{{ (row.adjustedCreditLossRate * 100).toFixed(2) }}%</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑥减值调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.impairmentAdjustment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑥ = ⑤×②A + ①×(②A-②)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.impairmentAdjustment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 审定数+差异列 ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="⑦审定账面余额" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBookBalance) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑦ = ① + ⑤" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBookBalance) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑧审定减值准备" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjImpairment) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑧ = ③ + ⑥" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjImpairment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="⑨审定账面价值" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal">
              <span class="subtotal-num">{{ fmtNum(row.adjBookValue) }}</span>
            </template>
            <template v-else>
              <el-tooltip content="⑨ = ⑦ - ⑧" placement="top">
                <span class="formula-cell">{{ fmtNum(row.adjBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="上年减值准备" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.priorImpairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'priorImpairment', v)" />
              <span v-else>{{ fmtNum(row.priorImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年计提" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-tooltip content="本年计提 = max(0, ⑧ - 上年减值)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.currentProvision) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本年转回" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-tooltip content="本年转回 = max(0, 上年减值 - ⑧)" placement="top">
                <span class="formula-cell">{{ fmtNum(row.currentReversal) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="差异说明" min-width="150">
          <template #default="{ row }">
            <template v-if="row._isSubtotal || row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.differenceNote" size="small"
                @change="(v: string) => updateField(row.id, 'differenceNote', v)" />
              <span v-else>{{ row.differenceNote }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isSubtotal && !row._isTotal" title="确认删除？"
            @confirm="calc.removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly" @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入减值准备测算的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>③ 减值准备 = ① 账面余额 × ② 信用损失率</li>
        <li>④ 账面价值 = ① - ③</li>
        <li>⑥ 减值准备调整 = ⑤×②A + ①×(②A-②)，可为负值（代表冲回）</li>
        <li>⑦ 审定账面余额 = ① + ⑤</li>
        <li>⑧ 审定减值准备 = ③ + ⑥</li>
        <li>⑨ 审定账面价值 = ⑦ - ⑧</li>
        <li>本年计提 = max(0, ⑧ - 上年减值准备)</li>
        <li>本年转回 = max(0, 上年减值准备 - ⑧)</li>
        <li>按Stage分组：Stage1(12个月ECL) / Stage2(整个存续期ECL) / Stage3(存续期ECL+净额利息)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabImpairmentCalc.vue — G4-10 减值准备测算表（2区段Tab + Stage分组）
 *
 * - el-segmented 切换 Tab1(未审数+审计调整) / Tab2(审定数+差异)
 * - 行共享同一reactive数组，Tab切换只改可见列
 * - selectedRowIndex跨Tab保持（行同步）
 * - Stage1/Stage2/Stage3分组 + 小计行 + 总计行
 * - 公式列tooltip显示来源
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG4EclImpairmentCalc } from '../../composables/useG4EclImpairmentCalc'
import type { ImpairmentCalcRow } from '../../composables/useG4EclFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG4EclImpairmentCalc()
const conclusion = ref('')
const activeTab = ref<'tab1' | 'tab2'>('tab1')

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '未审数+审计调整', value: 'tab1' },
  { label: '审定数+差异', value: 'tab2' },
]

// ─── Stage分组显示行（插入小计和总计行） ─────────────────────────────────────

interface DisplayRow extends ImpairmentCalcRow {
  _isSubtotal?: boolean
  _isTotal?: boolean
  _groupLabel?: string
}

const displayRows = computed<DisplayRow[]>(() => {
  const grouped = calc.groupedRows.value
  const result: DisplayRow[] = []

  // Stage1
  if (grouped.stage1.rows.length > 0) {
    for (const r of grouped.stage1.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage1',
      ...grouped.stage1.subtotal,
    } as DisplayRow)
  }

  // Stage2
  if (grouped.stage2.rows.length > 0) {
    for (const r of grouped.stage2.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage2',
      ...grouped.stage2.subtotal,
    } as DisplayRow)
  }

  // Stage3
  if (grouped.stage3.rows.length > 0) {
    for (const r of grouped.stage3.rows) result.push(r as DisplayRow)
    result.push({
      ...createEmptyRow(),
      _isSubtotal: true,
      _groupLabel: 'Stage3',
      ...grouped.stage3.subtotal,
    } as DisplayRow)
  }

  // 总计行
  result.push({
    ...createEmptyRow(),
    _isTotal: true,
    ...grouped.grandTotal,
  } as DisplayRow)

  return result
})

function createEmptyRow(): ImpairmentCalcRow {
  return {
    id: crypto.randomUUID(),
    seq: 0,
    investProject: '',
    stageGroup: 'Stage1',
    bookBalance: 0,
    pvFutureCashFlow: 0,
    creditLossRate: 0,
    impairmentProvision: 0,
    bookValue: 0,
    balanceAdjustment: 0,
    adjustedCreditLossRate: 0,
    impairmentAdjustment: 0,
    adjBookBalance: 0,
    adjImpairment: 0,
    adjBookValue: 0,
    priorImpairment: 0,
    currentProvision: 0,
    currentReversal: 0,
    differenceNote: '',
  }
}

// ─── 行同步（selectedRowIndex 跨Tab保持） ───────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isSubtotal || row._isTotal) return
  const idx = calc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) calc.activeRowIndex.value = idx
}

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isSubtotal) return 'row-subtotal'
  if (row._isTotal) return 'row-total'
  return ''
}

// ─── 字段更新（触发公式重算） ───────────────────────────────────────────────

function updateField(id: string, field: keyof ImpairmentCalcRow, value: any) {
  const row = calc.rows.value.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? 0
  calc.recalcRow(row)
}

// ─── 动态行增删（ElMessageBox.prompt） ──────────────────────────────────────

async function handleAddRow() {
  await calc.addRow('Stage1')
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成审计结论功能将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载（从htmlData初始化） ───────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.impairmentCalc) {
    const data = props.htmlData.impairmentCalc
    if (data.rows) calc.loadRows(data.rows)
    if (data.conclusion) conclusion.value = data.conclusion
  }
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    rows: calc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g4-impairment-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.impairment-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 50px;
  text-align: right;
}

/* 小计行 */
:deep(.row-subtotal) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.row-subtotal td) {
  background-color: #f5f7fa !important;
}

.subtotal-label {
  color: #606266;
  font-weight: 600;
  font-size: 12px;
}

.subtotal-num {
  font-weight: 600;
  color: #303133;
}

/* 总计行 */
:deep(.row-total) {
  background-color: #ecf5ff !important;
  font-weight: 700;
}
:deep(.row-total td) {
  background-color: #ecf5ff !important;
}

.total-label {
  color: #409eff;
  font-weight: 700;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
