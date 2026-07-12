<template>
  <div class="m6-tab-disclosure-listed">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">附注披露信息（上市公司）</h3>
        <el-tag type="primary" size="small">上市</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI('disclosure-listed')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>上市公司未分配利润附注披露（30×19）：</strong>
        按利润分配顺序逐行列示未分配利润变动过程，含本期审定数与上期审定数对比。
        公式列（带虚线下划线）只读自动计算，手动列可编辑。
        数据自动从审定表/明细表拉取（subscribe 'substantive:adjudicated' 事件刷新）。
      </div>
    </div>

    <!-- ═══ Section 1: 未分配利润变动表 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>未分配利润变动明细</span>
          <el-button size="small" @click="handleAI('section-movement')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-table :data="movementRows" border size="small" style="width: 100%">
        <el-table-column prop="item" label="项目" min-width="220" fixed>
          <template #default="{ row }">
            <span :class="{ 'formula-row': row.isFormula, 'subtotal-row': row.isSubtotal }">
              {{ row.item }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="本期审定数" min-width="150" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.currentPeriod) }}
            </span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.currentPeriod"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateMovementRow($index, 'currentPeriod', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.currentPeriod) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上期审定数" min-width="150" align="right">
          <template #default="{ row, $index }">
            <span v-if="row.isFormula" class="formula-cell" :title="row.formulaDesc">
              {{ fmtAmount(row.priorPeriod) }}
            </span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.priorPeriod"
              :controls="false"
              size="small"
              style="width: 100%"
              @change="(val: number | undefined) => updateMovementRow($index, 'priorPeriod', val ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.priorPeriod) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ Section 2: 会计政策变更/差错更正说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>会计政策变更/前期差错更正说明</span>
          <el-button size="small" @click="handleAI('section-policy-change')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="policyChangeNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明会计政策变更或前期差错更正对期初未分配利润的影响金额及原因..."
        @change="handlePolicyChangeNoteChange"
      />
    </el-card>

    <!-- ═══ Section 3: 利润分配方案说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>利润分配方案</span>
          <el-button size="small" @click="handleAI('section-distribution-plan')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="distributionPlanNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="说明本年利润分配方案、提取盈余公积比例、现金股利金额、股票股利金额..."
        @change="handleDistributionPlanNoteChange"
      />
    </el-card>

    <!-- ═══ Section 4: 子公司盈余公积转入说明 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>子公司盈余公积转入母公司未分配利润说明</span>
          <el-button size="small" @click="handleAI('section-subsidiary')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="subsidiaryNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :readonly="isReadonly"
        placeholder="合并报表中子公司盈余公积转入母公司未分配利润的金额及说明..."
        @change="handleSubsidiaryNoteChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>数据优先从M6-1审定表和M6-2明细表自动拉取</li>
        <li>订阅 'substantive:adjudicated' 事件自动刷新</li>
        <li>上市公司需额外披露利润分配方案及子公司盈余公积转入</li>
        <li>公式列（虚线下划线）自动计算：期初=上年末+调整；期末=期初+净利+其他-分配合计</li>
        <li>格式：30行×19列（含公式行）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M6TabDisclosureListed — 附注披露信息（上市公司）30×19
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 4.5
 * Requirements: 5.4, 5.5
 *
 * 功能：
 * - 未分配利润变动表：项目 | 本期审定 | 上期审定
 * - 行结构：调整前上期末/调整/调整后期初/+本期净利润/+其他/-法定盈余/-任意盈余/-现金股利/-转股股利/-其他/期末未分配利润/子公司盈余公积
 * - 公式列 read-only（期初=上年末+调整, 期末=期初+净利+其他-分配合计）
 * - Subscribe 'substantive:adjudicated' to refresh
 * - 说明文本区（会计政策变更/差错更正/利润分配方案/子公司盈余公积）
 * - inject openReviewDialog
 */
import { computed, inject, onMounted, onUnmounted, ref } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { eventBus } from '@/utils/eventBus'
import { useM6FormData } from '../../composables/useM6FormData'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── FormData ───────────────────────────────────────────────────────────────

const formData = useM6FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Movement Table Rows ─────────────────────────────────────────────────────

interface MovementRow {
  item: string
  currentPeriod: number
  priorPeriod: number
  isFormula: boolean
  isSubtotal: boolean
  formulaDesc?: string
  key: string
}

const movementRows = ref<MovementRow[]>([
  { item: '一、调整前上期期末未分配利润', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'prior-end-before-adj' },
  { item: '  加：会计政策变更调整', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'policy-change-adj' },
  { item: '  加：前期差错更正调整', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'error-correction-adj' },
  { item: '  加：其他调整', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'other-adj' },
  { item: '二、调整后期初未分配利润', currentPeriod: 0, priorPeriod: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 上期末 + 会计政策变更 + 差错更正 + 其他调整', key: 'begin-after-adj' },
  { item: '  加：本期净利润', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'net-profit' },
  { item: '  加：其他综合收益转入', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'oci-transfer' },
  { item: '三、可供分配利润', currentPeriod: 0, priorPeriod: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 调整后期初 + 本期净利润 + 其他综合收益转入', key: 'distributable' },
  { item: '  减：提取法定盈余公积', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'statutory-surplus' },
  { item: '  减：提取任意盈余公积', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'discretionary-surplus' },
  { item: '  减：应付普通股现金股利', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'cash-dividend' },
  { item: '  减：转作股本的普通股股利', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'stock-dividend' },
  { item: '  减：其他', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'other-deduction' },
  { item: '四、期末未分配利润', currentPeriod: 0, priorPeriod: 0, isFormula: true, isSubtotal: true, formulaDesc: '= 可供分配利润 - 法定盈余 - 任意盈余 - 现金股利 - 转股股利 - 其他', key: 'end-retained' },
  { item: '  其中：子公司盈余公积转入', currentPeriod: 0, priorPeriod: 0, isFormula: false, isSubtotal: false, key: 'subsidiary-surplus-in' },
])

// ─── Text Notes ──────────────────────────────────────────────────────────────

const policyChangeNote = ref('')
const distributionPlanNote = ref('')
const subsidiaryNote = ref('')

// ─── Formula Calculations ────────────────────────────────────────────────────

function recalcFormulas() {
  const rows = movementRows.value
  const getVal = (key: string, field: 'currentPeriod' | 'priorPeriod') => {
    const row = rows.find(r => r.key === key)
    return row ? row[field] : 0
  }

  // 二、调整后期初 = 上期末 + 政策变更 + 差错更正 + 其他调整
  const beginAfterAdj = rows.find(r => r.key === 'begin-after-adj')
  if (beginAfterAdj) {
    beginAfterAdj.currentPeriod = getVal('prior-end-before-adj', 'currentPeriod')
      + getVal('policy-change-adj', 'currentPeriod')
      + getVal('error-correction-adj', 'currentPeriod')
      + getVal('other-adj', 'currentPeriod')
    beginAfterAdj.priorPeriod = getVal('prior-end-before-adj', 'priorPeriod')
      + getVal('policy-change-adj', 'priorPeriod')
      + getVal('error-correction-adj', 'priorPeriod')
      + getVal('other-adj', 'priorPeriod')
  }

  // 三、可供分配利润 = 调整后期初 + 净利润 + OCI转入
  const distributable = rows.find(r => r.key === 'distributable')
  if (distributable && beginAfterAdj) {
    distributable.currentPeriod = beginAfterAdj.currentPeriod
      + getVal('net-profit', 'currentPeriod')
      + getVal('oci-transfer', 'currentPeriod')
    distributable.priorPeriod = beginAfterAdj.priorPeriod
      + getVal('net-profit', 'priorPeriod')
      + getVal('oci-transfer', 'priorPeriod')
  }

  // 四、期末未分配利润 = 可供分配 - 法定 - 任意 - 现金股利 - 转股股利 - 其他
  const endRetained = rows.find(r => r.key === 'end-retained')
  if (endRetained && distributable) {
    endRetained.currentPeriod = distributable.currentPeriod
      - getVal('statutory-surplus', 'currentPeriod')
      - getVal('discretionary-surplus', 'currentPeriod')
      - getVal('cash-dividend', 'currentPeriod')
      - getVal('stock-dividend', 'currentPeriod')
      - getVal('other-deduction', 'currentPeriod')
    endRetained.priorPeriod = distributable.priorPeriod
      - getVal('statutory-surplus', 'priorPeriod')
      - getVal('discretionary-surplus', 'priorPeriod')
      - getVal('cash-dividend', 'priorPeriod')
      - getVal('stock-dividend', 'priorPeriod')
      - getVal('other-deduction', 'priorPeriod')
  }
}

// ─── Handlers ────────────────────────────────────────────────────────────────

function updateMovementRow(index: number, field: 'currentPeriod' | 'priorPeriod', val: number) {
  if (index >= 0 && index < movementRows.value.length) {
    movementRows.value[index][field] = val
    recalcFormulas()
    formData.debouncedSave(`M6-disclosure-listed-${movementRows.value[index].key}-${field}`, { remark: String(val) })
  }
}

function handlePolicyChangeNoteChange() {
  formData.debouncedSave('M6-disclosure-listed-policy-change', { remark: policyChangeNote.value || null })
}

function handleDistributionPlanNoteChange() {
  formData.debouncedSave('M6-disclosure-listed-distribution-plan', { remark: distributionPlanNote.value || null })
}

function handleSubsidiaryNoteChange() {
  formData.debouncedSave('M6-disclosure-listed-subsidiary', { remark: subsidiaryNote.value || null })
}

function handleAI(_section: string) {
  // AI辅助钩子（后续集成）
}

function handleReview() {
  openReviewDialog?.('M6-disclosure-listed', '附注披露（上市公司）')
}

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore from saved data ─────────────────────────────────────────────────

function restoreData(): void {
  const responses = formData.allResponses.value
  for (const row of movementRows.value) {
    if (row.isFormula) continue
    const currentResp = responses.get(`M6-disclosure-listed-${row.key}-currentPeriod`)
    const priorResp = responses.get(`M6-disclosure-listed-${row.key}-priorPeriod`)
    if (currentResp?.remark) row.currentPeriod = Number(currentResp.remark) || 0
    if (priorResp?.remark) row.priorPeriod = Number(priorResp.remark) || 0
  }
  recalcFormulas()

  const policyResp = responses.get('M6-disclosure-listed-policy-change')
  if (policyResp?.remark) policyChangeNote.value = policyResp.remark

  const planResp = responses.get('M6-disclosure-listed-distribution-plan')
  if (planResp?.remark) distributionPlanNote.value = planResp.remark

  const subResp = responses.get('M6-disclosure-listed-subsidiary')
  if (subResp?.remark) subsidiaryNote.value = subResp.remark
}

// ─── EventBus subscribe: 审定变化刷新 ───────────────────────────────────────

function onAdjudicatedRefresh() {
  formData.loadData().then(() => restoreData())
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  restoreData()
  eventBus.on('substantive:adjudicated' as any, onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated' as any, onAdjudicatedRefresh)
})
</script>

<style scoped>
.m6-tab-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.section-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.section-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.methodology-context {
  border-left: 4px solid #e6a23c;
  background: #fdf6ec;
  padding: 12px 16px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 16px;
}

.methodology-text {
  font-size: var(--wp-font-size, 13px);
  color: #6b5900;
  line-height: 1.6;
}

.disclosure-card {
  margin-bottom: 16px;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.formula-row {
  font-weight: 600;
  color: #303133;
}

.subtotal-row {
  font-weight: 700;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 500;
  color: #303133;
}

:deep(.el-table) {
  font-size: var(--wp-font-size, 13px);
}

.m6-details-tip {
  margin-top: 16px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
}

.m6-details-tip summary {
  cursor: pointer;
  font-weight: 500;
  color: #303133;
}

.m6-details-tip ul {
  padding-left: 20px;
  margin: 8px 0 0;
  line-height: 1.8;
}
</style>
