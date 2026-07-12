<template>
  <div class="i1-tab-recoverable-test">
    <!-- 方法论上下文 -->
    <div class="methodology-block">
      <p><strong>CAS8 可收回金额确定</strong>：可收回金额应当根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值（使用价值）两者之间较高者确定。预计资产未来现金流量的现值，应当按照资产在持续使用过程中和最终处置时所产生的预计未来现金流量，选择恰当的折现率对其进行折现后的金额加以确定。折现率应当反映货币时间价值和资产特定风险的当前市场评价。</p>
    </div>

    <!-- 资产选择 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I1-13 可收回金额测试（DCF折现现金流模型）</span>
          <div class="section-header-actions">
            <el-button v-if="!isReadonly" size="small" type="warning" @click="handleLinkToI12">
              联动I1-12
            </el-button>
            <el-dropdown v-if="!isReadonly" trigger="click" @command="handleExportImport">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" type="primary" link @click="handleAiGenerate('dcf')">
              <el-icon><MagicStick /></el-icon> AI
            </el-button>
            <el-button size="small" circle @click="openReview('I1-13')">💬</el-button>
          </div>
        </div>
      </template>

      <!-- 逐资产DCF测算 -->
      <div v-for="(row, rowIdx) in recoverableRows" :key="row.rowId" class="dcf-asset-block">
        <div class="dcf-asset-header">
          <div class="dcf-asset-name">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" style="width:200px"
              placeholder="资产名称" @blur="handleNameChange(rowIdx, row.name)" />
            <strong v-else>{{ row.name || '未命名' }}</strong>
            <el-tag size="small" type="info">DCF模型</el-tag>
          </div>
          <div class="dcf-asset-actions" v-if="!isReadonly">
            <el-button size="small" type="danger" link @click="handleRemoveRow(rowIdx)">删除</el-button>
          </div>
        </div>

        <!-- DCF 参数输入区 -->
        <div class="dcf-params-grid">
          <div class="param-item">
            <label>折现率 (r)</label>
            <el-input-number v-if="!isReadonly" v-model="row.discountRate" :step="0.005"
              :precision="4" :min="0.001" :max="1" size="small" :controls="true"
              @change="handleRateChange(rowIdx, 'discountRate', $event)" />
            <span v-else class="param-value">{{ (row.discountRate * 100).toFixed(2) }}%</span>
          </div>
          <div class="param-item">
            <label>永续增长率 (g)</label>
            <el-input-number v-if="!isReadonly" v-model="row.growthRate" :step="0.005"
              :precision="4" :min="-0.1" :max="0.5" size="small" :controls="true"
              @change="handleRateChange(rowIdx, 'growthRate', $event)" />
            <span v-else class="param-value">{{ (row.growthRate * 100).toFixed(2) }}%</span>
          </div>
          <div class="param-item">
            <label>公允价值-处置费用</label>
            <el-input-number v-if="!isReadonly" v-model="row.fairValueLessDisposal" :controls="false"
              size="small" class="amt-input"
              @change="handleRateChange(rowIdx, 'fairValueLessDisposal', $event)" />
            <span v-else class="param-value amt-cell">{{ fmtAmt(row.fairValueLessDisposal) }}</span>
          </div>
        </div>

        <!-- 5年现金流表格 -->
        <el-table :data="buildCashFlowTableData(row)" border size="small" class="cf-table">
          <el-table-column prop="label" label="年度" width="80" align="center" />
          <el-table-column label="预测现金流" min-width="130" align="right">
            <template #default="{ row: cfRow }">
              <el-input-number v-if="!isReadonly" v-model="cfRow.cashFlow" :controls="false"
                size="small" class="amt-input"
                @change="handleCashFlowChange(rowIdx, cfRow.yearIndex, $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(cfRow.cashFlow) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="折现现金流" min-width="130" align="right">
            <template #header>
              <span class="formula-header" title="= CF_i / (1+r)^(i+1)">折现现金流</span>
            </template>
            <template #default="{ row: cfRow }">
              <span class="formula-cell" title="= CF / (1+r)^年">{{ fmtAmt(cfRow.discountedCF) }}</span>
            </template>
          </el-table-column>
        </el-table>

        <!-- DCF 计算结果 -->
        <div class="dcf-result-grid">
          <div class="result-item">
            <label class="formula-header" title="= CF_last × (1+g) / (r - g)">终值(TV)</label>
            <span class="formula-cell">{{ fmtAmt(row.terminalValue) }}</span>
          </div>
          <div class="result-item">
            <label class="formula-header" title="= TV / (1+r)^n">终值现值</label>
            <span class="formula-cell">{{ fmtAmt(row.discountedTerminalValue) }}</span>
          </div>
          <div class="result-item highlight-result">
            <label class="formula-header" title="= Σ(CF_i/(1+r)^(i+1)) + TV/(1+r)^n">使用价值(DCF)</label>
            <span class="formula-cell result-value">{{ fmtAmt(row.valueInUse) }}</span>
          </div>
          <div class="result-item highlight-result">
            <label class="formula-header" title="= MAX(公允-处置费, DCF使用价值)">可收回金额</label>
            <span class="formula-cell result-value primary-value">{{ fmtAmt(row.recoverableAmount) }}</span>
          </div>
        </div>

        <!-- 敏感性分析 -->
        <div class="sensitivity-section">
          <div class="sensitivity-header">
            <span>敏感性分析</span>
            <el-button size="small" type="primary" link @click="toggleSensitivity(rowIdx)">
              {{ sensitivityVisible[rowIdx] ? '收起' : '展开' }}
            </el-button>
          </div>
          <el-table v-if="sensitivityVisible[rowIdx]" :data="getSensitivityData(rowIdx)"
            border size="small" class="sensitivity-table">
            <el-table-column prop="scenario" label="情景" min-width="180" />
            <el-table-column label="折现率" width="100" align="center">
              <template #default="{ row: sRow }">{{ (sRow.discountRate * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="增长率" width="100" align="center">
              <template #default="{ row: sRow }">{{ (sRow.growthRate * 100).toFixed(2) }}%</template>
            </el-table-column>
            <el-table-column label="使用价值" min-width="120" align="right">
              <template #default="{ row: sRow }">
                <span class="amt-cell">{{ fmtAmt(sRow.valueInUse) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可收回金额" min-width="120" align="right">
              <template #default="{ row: sRow }">
                <span class="amt-cell">{{ fmtAmt(sRow.recoverableAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="与基准差额" min-width="110" align="right">
              <template #default="{ row: sRow }">
                <span :class="['amt-cell', { 'error-amount': sRow.differenceFromBase < 0 }]">
                  {{ fmtAmt(sRow.differenceFromBase) }}
                </span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <el-divider v-if="rowIdx < recoverableRows.length - 1" />
      </div>

      <!-- 空状态 -->
      <el-empty v-if="recoverableRows.length === 0" description="暂无可收回金额测试数据" :image-size="60" />

      <!-- 新增行 -->
      <div class="add-row-bar" v-if="!isReadonly">
        <el-button size="small" @click="handleAddRow">+ 新增资产DCF测算</el-button>
      </div>
    </el-card>

    <!-- 审计说明与结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link @click="handleAiGenerate('conclusion')">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写可收回金额测算结论（如：采用折现现金流模型测算各资产使用价值，选取的折现率为…，经测算各资产可收回金额均高于账面净值…）"
        :disabled="isReadonly" @blur="handleSaveConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>DCF公式: PV = Σ(CF_i / (1+r)^(i+1)) + TV / (1+r)^n</li>
        <li>终值公式(Gordon Model): TV = CF_last × (1+g) / (r - g)，要求 r > g</li>
        <li>可收回金额 = MAX(公允价值 - 处置费用, 使用价值DCF)</li>
        <li>折现率应反映货币时间价值和该资产特定风险（通常使用WACC或资产特定折现率）</li>
        <li>预测期一般为5年，超过5年需特别说明理由</li>
        <li>永续增长率不应超过所处行业/经济体长期增长率</li>
        <li>敏感性分析展示折现率±1%、增长率±0.5%对可收回金额的影响</li>
        <li>"联动I1-12"按钮将可收回金额自动填入减值准备测试表对应行</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabRecoverableTest.vue — I1-13 可收回金额测试（DCF折现现金流）
 * 10 formulas: PV=Σ(CF_i/(1+r)^(i+1)) + TV/(1+r)^n; 可收回=MAX(公允-处置费, DCF)
 * + 敏感性分析(r±1%, g±0.5%) + 联动I1-12
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 13.1-13.5
 */
import { ref, reactive, inject, toRef, computed } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useI1Impairment, DCF_FORECAST_YEARS } from '../../composables/useI1Impairment'
import type { I1RecoverableTestRow, SensitivityResult } from '../../composables/useI1Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save'): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  recoverableRows,
  addRecoverableRow,
  removeRecoverableRow,
  updateCashFlow,
  updateRecoverableField,
  linkRecoverableToImpairment,
  calcSensitivity,
  exportRecoverableRows,
  importRecoverableRows,
} = useI1Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: () => emit('save'),
  },
)

// ─── Local State ─────────────────────────────────────────────────────────────

const auditConclusion = ref('')
const sensitivityVisible = reactive<Record<number, boolean>>({})

// ─── Cash Flow Table Helper ──────────────────────────────────────────────────

interface CashFlowTableRow {
  label: string
  yearIndex: number
  cashFlow: number
  discountedCF: number
}

function buildCashFlowTableData(row: I1RecoverableTestRow): CashFlowTableRow[] {
  const result: CashFlowTableRow[] = []
  for (let i = 0; i < DCF_FORECAST_YEARS; i++) {
    result.push({
      label: `第${i + 1}年`,
      yearIndex: i,
      cashFlow: row.cashFlows[i] ?? 0,
      discountedCF: row.discountedCashFlows?.[i] ?? 0,
    })
  }
  return result
}

// ─── Sensitivity Analysis ────────────────────────────────────────────────────

function toggleSensitivity(rowIdx: number) {
  sensitivityVisible[rowIdx] = !sensitivityVisible[rowIdx]
}

function getSensitivityData(rowIdx: number): SensitivityResult[] {
  return calcSensitivity(rowIdx)
}

// ─── Actions ─────────────────────────────────────────────────────────────────

function handleNameChange(rowIdx: number, name: string) {
  // Name is already v-model bound, just trigger save
  emit('save')
}

function handleCashFlowChange(rowIdx: number, yearIndex: number, value: number) {
  updateCashFlow(rowIdx, yearIndex, value ?? 0)
}

function handleRateChange(rowIdx: number, field: 'discountRate' | 'growthRate' | 'fairValueLessDisposal', value: number) {
  updateRecoverableField(rowIdx, field, value ?? 0)
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入资产名称', '新增DCF测算', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (name) {
      addRecoverableRow({
        name: name.trim(),
        discountRate: 0.08,
        growthRate: 0.02,
      })
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  removeRecoverableRow(index)
}

function handleLinkToI12() {
  linkRecoverableToImpairment()
  ElMessage.success('已将可收回金额联动至I1-12减值准备测试表')
}

function handleExportImport(command: string) {
  switch (command) {
    case 'export-template':
      console.log('[I1-13] Export template')
      break
    case 'export-data':
      console.log('[I1-13] Export data:', exportRecoverableRows())
      break
    case 'import-data':
      console.log('[I1-13] Import data')
      break
  }
}

function handleAiGenerate(section: string) {
  console.log('[I1-13] AI generate:', section)
}

function handleSaveConclusion() {
  emit('save')
}

function openReview(id: string) {
  openReviewDialog(id)
}

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-recoverable-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 方法论上下文 */
.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.block-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }

/* DCF 资产块 */
.dcf-asset-block { margin-bottom: 16px; }
.dcf-asset-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  padding: 8px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
}
.dcf-asset-name { display: flex; align-items: center; gap: 8px; }
.dcf-asset-actions { display: flex; gap: 4px; }

/* 参数网格 */
.dcf-params-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-bottom: 12px;
}
.param-item { display: flex; flex-direction: column; gap: 4px; }
.param-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.param-value { font-weight: 500; font-variant-numeric: tabular-nums; }

/* 现金流表格 */
.cf-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }

/* DCF 结果网格 */
.dcf-result-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  margin-bottom: 12px;
}
.result-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.result-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.result-value { font-weight: 600; font-size: 14px; }
.primary-value { color: var(--el-color-primary); }
.highlight-result {
  background: #fff;
  padding: 8px;
  border-radius: 4px;
  border: 1px solid var(--el-border-color-lighter);
}

/* 表格通用 */
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }

/* 公式列样式 */
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}

/* 差额负数红色 */
.error-amount { color: var(--el-color-danger); font-weight: 600; }

/* 敏感性分析 */
.sensitivity-section { margin-top: 12px; }
.sensitivity-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--el-text-color-secondary);
}
.sensitivity-table { font-size: 12px; }

/* 新增行 */
.add-row-bar { margin-top: 16px; }
.audit-note-card { margin-bottom: 12px; }

/* 编制提示 */
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
