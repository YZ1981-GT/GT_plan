<template>
  <div class="n1-tab-loss-check">
    <!-- ═══ 旧版数据检测 alert（Req 6.1） ═══ -->
    <el-alert
      v-if="lossCheck.legacyInfo.value.canImport"
      type="warning"
      :closable="false"
      show-icon
      class="n1-legacy-alert"
    >
      <template #title>
        检测到旧版 N1-5 数据（{{ lossCheck.legacyInfo.value.count }} 行），可一键带入新模型
      </template>
      <template #default>
        <span>旧版数据将按「亏损年度 + 弥补年限 → 到期年度」映射，上期不确认／审计调整／来源三选等需人工补充。</span>
        <el-button type="warning" size="small" style="margin-left: 12px" :disabled="isReadonly" @click="handleImportLegacy">
          一键带入旧版数据
        </el-button>
      </template>
    </el-alert>

    <!-- ═══ 行级勾稽提示区（Req 1.5 / 3.2 / 2.4） ═══ -->
    <div v-if="lossCheck.warnings.value.length > 0" class="n1-warnings-area">
      <div v-for="w in lossCheck.warnings.value" :key="`${w.type}-${w.rowIndex}`" class="warn-item" :class="warnClass(w.type)">
        <el-icon><WarningFilled /></el-icon>
        <span>{{ w.message }}</span>
      </div>
    </div>

    <!-- ═══ 亏损检查主 Section ═══ -->
    <el-card shadow="never" class="n1-section-card">
      <template #header>
        <div class="section-header">
          <div class="section-title-group">
            <span class="section-title">可用以后年度税前利润弥补的亏损检查表 N1-5</span>
            <el-tag type="info" size="small">共 {{ lossCheck.rows.value.length }} 行</el-tag>
          </div>
          <div class="section-actions">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="handleAddRow">+ 新增到期年度</el-button>
            <el-dropdown trigger="click" @command="handleImportExportCmd">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                  <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                  <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-button size="small" :loading="aiLoading" @click="handleAI">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <GtReviewTrigger section-id="N1-5-loss-check" label="复核" />
          </div>
        </div>
      </template>

      <!-- ═══ 主表：按源模板列顺序 ═══ -->
      <el-table
        :data="lossCheck.rows.value"
        border
        size="small"
        style="width: 100%"
        class="loss-check-table"
        :row-class-name="getRowClassName"
      >
        <!-- 1. 到期年度 -->
        <el-table-column prop="expiryYear" label="到期年度" width="90" align="center" fixed>
          <template #default="{ row }">
            <span :class="{ 'text-expired': row.isExpired }">{{ row.expiryYear }}</span>
            <el-tag v-if="row.isExpired" type="danger" size="small" style="margin-left:4px">届满</el-tag>
          </template>
        </el-table-column>

        <!-- 2. 上期不确认 -->
        <el-table-column prop="priorUnrecognized" label="上期不确认" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorUnrecognized"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => lossCheck.updateRow($index, 'priorUnrecognized', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.priorUnrecognized) }}</span>
          </template>
        </el-table-column>

        <!-- 3. 账面金额 -->
        <el-table-column prop="bookAmount" label="账面金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => lossCheck.updateRow($index, 'bookAmount', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 4. 审计调整 -->
        <el-table-column prop="auditAdjustment" label="审计调整" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditAdjustment"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => lossCheck.updateRow($index, 'auditAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.auditAdjustment) }}</span>
          </template>
        </el-table-column>

        <!-- 5. 审定金额 (readonly formula-col) -->
        <el-table-column prop="auditedAmount" label="审定金额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定金额 = 账面金额 + 审计调整" placement="top">
              <span class="formula-col">审定金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 账面金额 + 审计调整" placement="top">
              <span class="formula-value">{{ fmtAmt(row.auditedAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 6. 确认金额 -->
        <el-table-column prop="recognizedAmount" label="确认金额" min-width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number
              v-if="!isReadonly && !row.isExpired"
              :model-value="row.recognizedAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => lossCheck.updateRow($index, 'recognizedAmount', v ?? 0)"
            />
            <span v-else :class="{ 'text-muted': row.isExpired }">{{ row.isExpired ? '0（已届满）' : fmtAmt(row.recognizedAmount) }}</span>
          </template>
        </el-table-column>

        <!-- 7. 不确认金额 (readonly formula-col) -->
        <el-table-column prop="unrecognizedAmount" label="不确认金额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="不确认金额 = 审定金额 - 确认金额" placement="top">
              <span class="formula-col">不确认金额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 审定金额 - 有效确认金额" placement="top">
              <span class="formula-value" :class="{ 'text-warning-bold': row.splitMismatch }">{{ fmtAmt(row.unrecognizedAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 8. 依据 -->
        <el-table-column prop="basis" label="依据" min-width="150">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.basis"
              size="small"
              placeholder="不确认依据..."
              :class="{ 'basis-missing': row.basisMissing }"
              @change="(v: string) => lossCheck.updateRow($index, 'basis', v ?? '')"
            />
            <span v-else :class="{ 'text-warning': row.basisMissing }">{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 9. 是否充足 (el-select) -->
        <el-table-column prop="sufficient" label="是否充足" width="100" align="center">
          <template #header>
            <el-tooltip content="到期前是否有足够的应纳税所得额" placement="top">
              <span>是否充足</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.sufficient"
              size="small"
              placeholder="—"
              clearable
              style="width: 80px"
              @change="(v: string) => lossCheck.updateRow($index, 'sufficient', v ?? '')"
            >
              <el-option value="yes" label="是" />
              <el-option value="no" label="否" />
            </el-select>
            <span v-else :class="{ 'text-danger': row.sufficient === 'no' }">
              {{ row.sufficient === 'yes' ? '是' : row.sufficient === 'no' ? '否' : '—' }}
            </span>
          </template>
        </el-table-column>

        <!-- 10. 来源三选 (3 el-checkbox) -->
        <el-table-column label="来源" min-width="180" align="center">
          <template #header>
            <el-tooltip content="预计应纳税所得额来源（可多选）" placement="top">
              <span>来源三选</span>
            </el-tooltip>
          </template>
          <template #default="{ row, $index }">
            <div class="source-checkboxes">
              <el-checkbox
                :model-value="row.sourceOperating"
                :disabled="isReadonly"
                size="small"
                label="经营"
                @change="(v: boolean) => lossCheck.updateRow($index, 'sourceOperating', !!v)"
              />
              <el-checkbox
                :model-value="row.sourceTemporaryDiff"
                :disabled="isReadonly"
                size="small"
                label="暂时性差异"
                @change="(v: boolean) => lossCheck.updateRow($index, 'sourceTemporaryDiff', !!v)"
              />
              <el-checkbox
                :model-value="row.sourceOther"
                :disabled="isReadonly"
                size="small"
                label="其他"
                @change="(v: boolean) => lossCheck.updateRow($index, 'sourceOther', !!v)"
              />
            </div>
          </template>
        </el-table-column>

        <!-- 11. 检查底稿索引 -->
        <el-table-column prop="indexRef" label="检查底稿索引" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              placeholder="如 N1-4"
              @change="(v: string) => lossCheck.updateRow($index, 'indexRef', v ?? '')"
            />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 12. 可确认递延税资产 (readonly formula-col) -->
        <el-table-column prop="recognizableAsset" label="可确认递延税资产" min-width="140" align="right">
          <template #header>
            <el-tooltip content="可确认递延税资产 = 确认金额 × 适用税率" placement="top">
              <span class="formula-col">可确认递延税资产</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="`= ${fmtAmt(row.effectiveRecognized)} × ${(row.taxRate * 100).toFixed(0)}%`" placement="top">
              <span class="formula-value" :class="{ 'text-muted': row.isExpired }">
                {{ row.isExpired ? '—' : fmtAmt(row.recognizableAsset) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 13. 备注 -->
        <el-table-column prop="remark" label="备注" min-width="120">
          <template #default="{ row, $index }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark || ''"
              size="small"
              placeholder="备注"
              @change="(v: string) => lossCheck.updateRow($index, 'remark', v ?? '')"
            />
            <span v-else>{{ row.remark || '—' }}</span>
          </template>
        </el-table-column>

        <!-- 删除列 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" size="small" link @click="lossCheck.removeRow($index)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 判断矩阵视图（源模板语义 Req 1.6 / Task 3.2） ═══ -->
    <el-card shadow="never" class="n1-section-card n1-matrix-card">
      <template #header>
        <span class="section-title">判断矩阵（复核视角）</span>
      </template>
      <N1LossJudgmentMatrix
        :rows="matrixRows"
        :readonly="isReadonly"
        @locate="handleMatrixLocate"
        @toggle="handleMatrixToggle"
      />
    </el-card>

    <!-- ═══ 引导行区（期末未分配利润 / 其中：可抵扣亏损） ═══ -->
    <el-card shadow="never" class="n1-section-card n1-lead-card">
      <template #header>
        <span class="section-title">引导行（期末未分配利润 / 可抵扣亏损）</span>
      </template>
      <el-table :data="leadRowsDisplay" border size="small" style="width: 100%" class="lead-table">
        <el-table-column prop="label" label="项目" width="180" />
        <el-table-column prop="priorUnrecognized" label="上期不确认" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorUnrecognized"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => updateLead(row.key, 'priorUnrecognized', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.priorUnrecognized) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookAmount" label="账面金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => updateLead(row.key, 'bookAmount', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.bookAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="auditAdjustment" label="审计调整" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditAdjustment"
              :controls="false"
              :precision="2"
              size="small"
              class="cell-input"
              @change="(v: number|null) => updateLead(row.key, 'auditAdjustment', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.auditAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定金额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="= 账面金额 + 审计调整" placement="top"><span class="formula-col">审定金额</span></el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.auditedAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 合计区 ═══ -->
    <div class="n1-totals-bar">
      <div class="total-item"><span class="total-label">上期不确认合计</span><span class="total-value">{{ fmtAmt(lossCheck.totals.value.priorUnrecognized) }}</span></div>
      <div class="total-item"><span class="total-label">本期审定合计</span><span class="total-value">{{ fmtAmt(lossCheck.totals.value.auditedAmount) }}</span></div>
      <div class="total-item"><span class="total-label">确认合计</span><span class="total-value text-success">{{ fmtAmt(lossCheck.totals.value.recognized) }}</span></div>
      <div class="total-item"><span class="total-label">不确认合计</span><span class="total-value text-danger">{{ fmtAmt(lossCheck.totals.value.unrecognized) }}</span></div>
      <div class="total-item total-highlight"><span class="total-label">可确认递延税资产合计</span><span class="total-value text-primary">{{ fmtAmt(lossCheck.totals.value.recognizableAsset) }}</span></div>
      <div class="total-actions">
        <el-button type="success" size="small" :disabled="isReadonly" :loading="writebackLoading" @click="handleWritebackToN4">
          回填 → N1-4 / N1-1
        </el-button>
        <GtIndexChip value="wp:N1-4" :context-project-id="projectId" />
        <GtIndexChip value="wp:N1-1" :context-project-id="projectId" />
      </div>
    </div>

    <!-- ═══ 编制提示（折叠底部） ═══ -->
    <details class="n1-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>到期年度 = 亏损发生年度 + 最长弥补年限（一般5年/高新10年）</li>
        <li>审定金额 = 账面金额 + 审计调整（公式列，只读）</li>
        <li>确认金额由审计师录入；不确认金额 = 审定金额 - 确认金额（公式列）</li>
        <li>弥补期限届满（到期年度 &lt; 审计年度）→ 确认额强制为 0，标红高亮</li>
        <li>可确认递延税资产 = 确认金额 × 适用税率</li>
        <li>回填 N1-4/N1-1 只填空值不覆盖手工数据</li>
        <li>不确认金额 &gt; 0 时须填写依据（系统提示但不阻断保存）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N1TabLossCheck — N1-5 可用以后年度税前利润弥补的亏损检查表（重建为源模板结构）
 *
 * Spec: .kiro/specs/n1-loss-check-source-alignment/
 * Task: 3.1
 * Requirements: 1.1-1.6, 2.3, 2.4, 3.2, 3.3, 6.1
 *
 * 源模板列顺序：到期年度 | 上期不确认 | 账面金额 | 审计调整 | 审定金额(formula) |
 *   确认金额 | 不确认金额(formula) | 依据 | 是否充足(el-select) | 来源三选(3 checkbox) |
 *   检查底稿索引 | 可确认递延税资产(formula) | 备注
 */
import { ref, computed, toRef } from 'vue'
import type { ComputedRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { WarningFilled, MagicStick } from '@element-plus/icons-vue'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import { useN1LossCheck } from '../../composables/useN1LossCheck'
import N1LossJudgmentMatrix from './N1LossJudgmentMatrix.vue'
import type { N1LossComputedRow, N1LossWarning, N1LossLeadKey, EditableLeadField } from '../../composables/useN1LossCheck'
import { generateN1Text } from '../../composables/useN1AiText'
import { eventBus } from '@/utils/eventBus'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  year: number
  isReadonly: boolean
  formData: any
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const auditYearRef = computed(() => props.year || new Date().getFullYear())
const allResponsesRef = computed(() => props.allResponses ?? new Map())

const lossCheck = useN1LossCheck({
  wpId: wpIdRef,
  projectId: projectIdRef,
  allResponses: allResponsesRef as ComputedRef<Map<string, any>>,
  formData: props.formData,
  auditYear: auditYearRef,
})

// ─── State ───────────────────────────────────────────────────────────────────

const writebackLoading = ref(false)
const aiLoading = ref(false)

// ─── Lead Rows display ───────────────────────────────────────────────────────

const leadRowsDisplay = computed(() => {
  const leads = lossCheck.leadRows.value
  return [
    { key: 'retainedEarnings' as N1LossLeadKey, ...leads.retainedEarnings, auditedAmount: leads.retainedEarnings.bookAmount + leads.retainedEarnings.auditAdjustment },
    { key: 'deductibleLoss' as N1LossLeadKey, ...leads.deductibleLoss, auditedAmount: leads.deductibleLoss.bookAmount + leads.deductibleLoss.auditAdjustment },
  ]
})

function updateLead(key: N1LossLeadKey, field: EditableLeadField, value: number) {
  lossCheck.updateLead(key, field, value)
}

// ─── Matrix rows (mapped for N1LossJudgmentMatrix) ───────────────────────────

const matrixRows = computed(() =>
  lossCheck.rows.value.map(r => ({
    expiryYear: r.expiryYear,
    auditedAmount: r.auditedAmount,
    recognizedAmount: r.recognizedAmount ?? 0,
    unrecognizedAmount: r.unrecognizedAmount,
    isExpired: r.isExpired,
    sufficient: r.sufficient ?? '',
    sourceOperating: !!r.sourceOperating,
    sourceTemporaryDiff: !!r.sourceTemporaryDiff,
    sourceOther: !!r.sourceOther,
    basis: r.basis ?? '',
    indexRef: r.indexRef ?? '',
    recognizableAsset: r.recognizableAsset,
  })),
)

/** Matrix locate → scroll to row in main table (no-op for now, could highlight) */
function handleMatrixLocate(_index: number) {
  // In a full implementation this would scroll the main table to highlight the row.
  // For now the matrix is purely a read/toggle view alongside the main table.
}

/** Matrix toggle → update lossCheck row field */
function handleMatrixToggle(payload: { index: number; field: 'sufficient' | 'sourceOperating' | 'sourceTemporaryDiff' | 'sourceOther' }) {
  const { index, field } = payload
  if (field === 'sufficient') {
    // Toggle sufficient: '' → 'yes' → 'no' → ''
    const currentVal = lossCheck.rows.value[index]?.sufficient ?? ''
    let next: string
    if (currentVal === '') next = 'yes'
    else if (currentVal === 'yes') next = 'no'
    else next = ''
    lossCheck.updateRow(index, 'sufficient', next)
  } else {
    // Toggle boolean: false → true → false
    const row = lossCheck.rows.value[index]
    if (!row) return
    const currentVal = !!(row as any)[field]
    lossCheck.updateRow(index, field, !currentVal)
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function fmtAmt(val: number | undefined | null): string {
  if (val == null || isNaN(val) || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function warnClass(type: N1LossWarning['type']): string {
  if (type === 'expired') return 'warn-expired'
  if (type === 'splitMismatch') return 'warn-danger'
  return 'warn-warning'
}

/** Row class: expired rows get red highlight */
function getRowClassName({ row }: { row: N1LossComputedRow }): string {
  if (!row) return ''
  if (row.isExpired) return 'row-expired'
  if (row.splitMismatch) return 'row-mismatch'
  return ''
}

// ─── 新增行（ElMessageBox.prompt + /^\d{4}$/ validation） ────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入可抵扣亏损到期年度（4位数字）',
      '新增到期年度行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /^\d{4}$/,
        inputErrorMessage: '请输入4位数字年份（如2027）',
        inputPlaceholder: '如：2027',
      },
    )
    if (value) {
      lossCheck.addRow(parseInt(value, 10))
      ElMessage.success(`已添加到期年度 ${value} 行`)
    }
  } catch { /* cancelled */ }
}

// ─── 一键带入旧版数据 ────────────────────────────────────────────────────────

function handleImportLegacy() {
  const added = lossCheck.importFromLegacy()
  if (added > 0) {
    ElMessage.success(`已从旧版数据带入 ${added} 行（上期不确认/审计调整/来源三选等需人工补充）`)
  } else {
    ElMessage.info('未有新数据需带入（已存在相同到期年度行）')
  }
}

// ─── 回填 N1-4 / N1-1 ───────────────────────────────────────────────────────

async function handleWritebackToN4() {
  writebackLoading.value = true
  try {
    const total = lossCheck.totals.value.recognizableAsset
    await props.formData.saveField('N1-5-total-recognizable', { remark: String(total) })
    eventBus.emit('loss-check:recognizable-updated', {
      recognizableTotal: total,
      wpCode: 'N1',
      source: 'N1-5',
      timestamp: Date.now(),
    })
    ElMessage.success(`可确认递延税资产合计 ${fmtAmt(total)} 已回填 N1-4/N1-1`)
  } catch (err: any) {
    ElMessage.error(`回填失败：${err?.message || '未知错误'}`)
  } finally {
    writebackLoading.value = false
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleImportExportCmd(cmd: string) {
  const ie = props.formData?.importExport
  if (!ie) { ElMessage.warning('导入导出功能未就绪'); return }
  switch (cmd) {
    case 'export-template':
      await ie.exportTemplate('N1-5')
      break
    case 'export-data':
      await ie.exportData('N1-5')
      break
    case 'import-data': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          await ie.importData(file, 'N1-5')
          await props.formData.loadData?.()
        }
      }
      input.click()
      break
    }
  }
}

// ─── AI辅助 ──────────────────────────────────────────────────────────────────

async function handleAI() {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    const t = lossCheck.totals.value
    const text = await generateN1Text({
      wpId: props.wpId,
      section: 'n1-loss-check-analysis',
      prompt: '请基于可弥补亏损检查表数据，分析各年度到期亏损的确认/不确认合理性（弥补期限、应纳税所得额充足性、来源依据），给出审计建议。',
      context: {
        审计年度: String(props.year ?? ''),
        本期审定合计: String(t.auditedAmount),
        确认合计: String(t.recognized),
        不确认合计: String(t.unrecognized),
        可确认递延税资产合计: String(t.recognizableAsset),
        上期不确认合计: String(t.priorUnrecognized),
        行数: String(lossCheck.rows.value.length),
        届满行数: String(lossCheck.rows.value.filter(r => r.isExpired).length),
      },
      existingContent: '',
    })
    if (text) {
      await ElMessageBox.alert(text, 'AI 辅助分析建议', { confirmButtonText: '知道了' }).catch(() => {})
    } else {
      ElMessage.warning('AI 未能生成内容')
    }
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.n1-tab-loss-check {
  padding: 12px;
  font-size: 13px;
}

/* ─── Legacy Alert ─── */
.n1-legacy-alert {
  margin-bottom: 16px;
}

/* ─── Warnings ─── */
.n1-warnings-area {
  margin-bottom: 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.warn-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 6px;
  font-size: 13px;
}

.warn-expired {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-left: 4px solid #dc2626;
  color: #991b1b;
}

.warn-danger {
  background: #fef2f2;
  border: 1px solid #fca5a5;
  border-left: 4px solid #ef4444;
  color: #991b1b;
}

.warn-warning {
  background: #fffbeb;
  border: 1px solid #fde68a;
  border-left: 4px solid #d97706;
  color: #92400e;
}

/* ─── Section Card ─── */
.n1-section-card {
  margin-bottom: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;
}

.section-title-group {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── Table ─── */
:deep(.el-table) {
  font-size: 13px;
}

:deep(.el-table td.is-right .cell) {
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

:deep(.el-input-number) {
  width: 100%;
}

:deep(.el-input-number .el-input__inner) {
  text-align: right;
  font-size: 13px;
}

.cell-input {
  width: 100%;
}

/* ─── Formula columns: dashed underline + cursor:help ─── */
.formula-col {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}

.formula-value {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  color: #606266;
}

/* ─── Row highlight for expired ─── */
:deep(.row-expired) {
  background-color: #fef2f2 !important;
}

:deep(.row-expired td) {
  color: #991b1b !important;
}

:deep(.row-mismatch) {
  background-color: #fffbeb !important;
}

/* ─── Source checkboxes ─── */
.source-checkboxes {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.source-checkboxes .el-checkbox {
  height: auto;
  margin-right: 0;
}

:deep(.source-checkboxes .el-checkbox__label) {
  font-size: 12px;
}

/* ─── Text helpers ─── */
.text-expired {
  color: #dc2626;
  font-weight: 600;
}

.text-muted {
  color: #909399;
}

.text-warning-bold {
  color: #d97706;
  font-weight: 600;
}

.text-danger {
  color: #dc2626;
}

.text-success {
  color: #059669;
}

.text-primary {
  color: var(--el-color-primary);
  font-weight: 600;
}

.text-warning {
  color: #d97706;
}

.basis-missing :deep(.el-input__wrapper) {
  border-color: #d97706;
}

/* ─── Lead Card ─── */
.n1-lead-card {
  margin-bottom: 16px;
}

/* ─── Totals Bar ─── */
.n1-totals-bar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  padding: 14px 18px;
  margin-bottom: 16px;
  background: #f5f7fa;
  border: 1px solid #e4e7ed;
  border-radius: 8px;
}

.total-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.total-label {
  font-size: 12px;
  color: #909399;
}

.total-value {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}

.total-highlight {
  padding: 6px 12px;
  background: #ecf5ff;
  border-radius: 6px;
}

.total-actions {
  margin-left: auto;
  display: flex;
  align-items: center;
  gap: 8px;
}

/* ─── 编制提示 ─── */
.n1-details-tip {
  margin-top: 12px;
  padding: 10px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 12px;
  color: #606266;
}

.n1-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.n1-details-tip ul {
  padding-left: 18px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
