<!--
  K1TabBadDebtCalc.vue — K1-8 坏账准备测算

  Features:
  1. 2区段Tab (el-tabs): "账龄迁徙" / "ECL测算"
  2. 62行虚拟滚动 (el-table max-height)
  3. 账龄迁徙区段: 账龄区间/期末余额/迁徙率/预期损失率/预期损失(公式)
  4. ECL测算区段: 往来对象/EAD/PD/LGD/ECL(公式=EAD×PD×LGD)/企业计提/差异(公式)/测算结论
  5. 差异>重要性水平时红色标记
  6. 底部合计: 总ECL / 总企业计提 / 总差异
  7. 导入导出 + AI辅助 + 复核
  8. 琥珀色方法论上下文 + 编制提示
  9. Uses: useK1BadDebtCalc composable + useK1ImportExport

  Spec: .kiro/specs/k1-other-receivables/ Task 4.5
  Requirements: 6.1-6.6
-->
<template>
  <div class="k1-tab-bad-debt-calc">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-8坏账准备测算采用预期信用损失法(ECL)独立测算坏账准备充分性。
        账龄迁徙法：按账龄区间计算历史迁徙率→预期损失率→预期损失。
        ECL模型：ECL = EAD × PD × LGD。测算差异 = 测算应计提 - 企业计提，
        差异超过重要性水平时红色标记并提示调整。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-8 坏账准备测算</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-8-calc')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="handleReview('K1-8-calc')">💬 复核</el-button>
      </div>
    </div>

    <!-- 2区段Tab -->
    <el-tabs v-model="activeTab" type="border-card" class="calc-tabs">
      <!-- ═══ 账龄迁徙区段 ═══ -->
      <el-tab-pane label="账龄迁徙" name="aging">
        <el-table
          :data="agingRows"
          border
          size="small"
          :max-height="450"
          class="calc-table"
          show-summary
          :summary-method="agingSummaryMethod"
        >
          <el-table-column label="账龄区间" min-width="130" fixed>
            <template #default="{ row }">
              <span>{{ row.agingBucket }}</span>
            </template>
          </el-table-column>

          <el-table-column label="期末余额" min-width="125" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small"
                :controls="false" class="amount-input"
                @change="(v: number) => handleAgingUpdate(row.id, 'endBalance', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="迁徙率" min-width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.migrationRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="amount-input"
                @change="(v: number) => handleAgingUpdate(row.id, 'migrationRate', v ?? 0)" />
              <span v-else class="amount-cell">{{ (row.migrationRate * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>

          <el-table-column label="预期损失率" min-width="115" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.expectedLossRate" size="small"
                :controls="false" :precision="4" :step="0.01" class="amount-input"
                @change="(v: number) => handleAgingUpdate(row.id, 'expectedLossRate', v ?? 0)" />
              <span v-else class="amount-cell">{{ (row.expectedLossRate * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>

          <el-table-column label="预期损失" min-width="125" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="预期损失=期末余额×预期损失率">
                {{ fmtAmt(row.expectedLoss) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- ═══ ECL测算区段 ═══ -->
      <el-tab-pane label="ECL测算" name="ecl">
        <el-table
          :data="eclRows"
          border
          size="small"
          :max-height="450"
          class="calc-table"
          :row-class-name="eclRowClassName"
          show-summary
          :summary-method="eclSummaryMethod"
        >
          <el-table-column label="往来对象" min-width="130" fixed>
            <template #default="{ row }">
              <span>{{ row.counterparty }}</span>
            </template>
          </el-table-column>

          <el-table-column label="EAD" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.ead" size="small"
                :controls="false" class="amount-input"
                @change="(v: number) => handleEclUpdate(row.id, 'ead', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.ead) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="PD" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.pd" size="small"
                :controls="false" :precision="4" :step="0.01" class="amount-input"
                @change="(v: number) => handleEclUpdate(row.id, 'pd', v ?? 0)" />
              <span v-else class="amount-cell">{{ (row.pd * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>

          <el-table-column label="LGD" min-width="100" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.lgd" size="small"
                :controls="false" :precision="4" :step="0.01" class="amount-input"
                @change="(v: number) => handleEclUpdate(row.id, 'lgd', v ?? 0)" />
              <span v-else class="amount-cell">{{ (row.lgd * 100).toFixed(2) }}%</span>
            </template>
          </el-table-column>

          <el-table-column label="ECL" min-width="125" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="ECL=EAD×PD×LGD">
                {{ fmtAmt(row.ecl) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="企业计提" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.bookedProvision" size="small"
                :controls="false" class="amount-input"
                @change="(v: number) => handleEclUpdate(row.id, 'bookedProvision', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmtAmt(row.bookedProvision) }}</span>
            </template>
          </el-table-column>

          <el-table-column label="差异" min-width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" :class="{ 'variance-exceed': isVarianceExceedsMateriality(row) }"
                title="差异=ECL-企业计提">
                {{ fmtAmt(row.variance) }}
              </span>
            </template>
          </el-table-column>

          <el-table-column label="测算结论" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.conclusion" size="small"
                placeholder="充分/不足/需调整"
                @change="(v: string) => handleEclUpdate(row.id, 'conclusion', v)" />
              <span v-else :class="{ 'conclusion-warn': isVarianceExceedsMateriality(row) }">
                {{ row.conclusion || '-' }}
              </span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 底部合计面板 -->
    <div class="totals-panel">
      <div class="total-item">
        <span class="total-label">总ECL</span>
        <span class="total-value">{{ fmtAmt(totals.totalECL) }}</span>
      </div>
      <div class="total-item">
        <span class="total-label">总企业计提</span>
        <span class="total-value">{{ fmtAmt(totals.totalBooked) }}</span>
      </div>
      <div class="total-item" :class="{ 'total-exceed': Math.abs(totals.totalVariance) > materialityLevel && materialityLevel > 0 }">
        <span class="total-label">总差异</span>
        <span class="total-value">{{ fmtAmt(totals.totalVariance) }}</span>
      </div>
      <div class="total-item total-materiality">
        <span class="total-label">重要性水平</span>
        <el-input-number v-if="!isReadonly" v-model="materialityLevel" size="small"
          :controls="false" class="materiality-input" placeholder="0"
          @change="handleMaterialityChange" />
        <span v-else class="total-value">{{ fmtAmt(materialityLevel) }}</span>
      </div>
    </div>

    <!-- 差异警告 -->
    <div v-if="hasExceedingVariance" class="variance-warning">
      <el-alert type="error" :closable="false" show-icon>
        <template #title>存在差异超过重要性水平的测算项，请关注是否需要建议调整</template>
      </el-alert>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>账龄迁徙法：按账龄区间统计期末余额，结合历史迁徙率计算预期损失率</li>
        <li>预期损失 = 期末余额 × 预期损失率（公式自动计算）</li>
        <li>ECL模型：ECL = EAD × PD × LGD（公式自动计算）</li>
        <li>测算差异 = ECL(测算应计提) - 企业计提（公式自动计算）</li>
        <li>差异超过重要性水平时红色标记，提示需关注是否建议调整</li>
        <li>重要性水平可在底部面板设置，默认为0（不启用差异标记）</li>
        <li>两个区段Tab共享行同步，切换不影响数据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabBadDebtCalc.vue — K1-8 坏账准备测算
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.5
 * Requirements: 6.1-6.6
 *
 * 2区段Tab(账龄迁徙+ECL测算) + 差异标记 + 虚拟滚动 + 合计面板
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useK1BadDebtCalc,
  type K1AgingMigrationRow,
  type K1ECLCalcRow,
} from '../../composables/useK1BadDebtCalc'
import { useK1ImportExport } from '../../composables/useK1ImportExport'

// ─── Props / Emits ───────────────────────────────────────────────────────────

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

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── State ───────────────────────────────────────────────────────────────────

const activeTab = ref<'aging' | 'ecl'>('aging')

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  agingRows,
  eclRows,
  materialityLevel,
  totals,
  hasExceedingVariance,
  loadData,
  updateAgingRow,
  updateEclRow,
  isVarianceExceedsMateriality,
  serializeData,
} = useK1BadDebtCalc({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const {
  exportTemplate,
  exportData,
  importData,
} = useK1ImportExport({ wpId: toRef(props, 'wpId') })

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  loadData()
})

// ─── 行更新 ──────────────────────────────────────────────────────────────────

function handleAgingUpdate(id: string, field: keyof K1AgingMigrationRow, value: any) {
  updateAgingRow(id, field, value)
  persistData()
}

function handleEclUpdate(id: string, field: keyof K1ECLCalcRow, value: any) {
  updateEclRow(id, field, value)
  persistData()
}

function handleMaterialityChange() {
  persistData()
}

/** 持久化所有数据 */
function persistData() {
  const { aging, ecl } = serializeData()

  // 存储账龄行
  const agingId = 'K1-8-aging-rows'
  const agingPayload = { item_id: agingId, conclusion: null, remark: aging }
  props.allResponses.set(agingId, agingPayload)
  emit('save', agingId, { remark: aging })

  // 存储ECL行
  const eclId = 'K1-8-ecl-rows'
  const eclPayload = { item_id: eclId, conclusion: null, remark: ecl }
  props.allResponses.set(eclId, eclPayload)
  emit('save', eclId, { remark: ecl })

  // 存储重要性水平
  const matId = 'K1-8-materiality'
  const matPayload = { item_id: matId, conclusion: null, remark: String(materialityLevel.value) }
  props.allResponses.set(matId, matPayload)
  emit('save', matId, { remark: String(materialityLevel.value) })
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K1-8') }
function handleExportData() { exportData('K1-8') }

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-8', file)
    if (result) { loadData() }
  }
  input.click()
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────

function agingSummaryMethod({ columns, data }: { columns: any[]; data: K1AgingMigrationRow[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop === 'endBalance') {
      sums[idx] = fmtAmt(data.reduce((acc, r) => acc + (r.endBalance || 0), 0))
    } else if (prop === 'expectedLoss') {
      sums[idx] = fmtAmt(data.reduce((acc, r) => acc + (r.expectedLoss || 0), 0))
    } else {
      sums[idx] = ''
    }
  })
  return sums
}

function eclSummaryMethod({ columns, data }: { columns: any[]; data: K1ECLCalcRow[] }) {
  const sums: string[] = []
  columns.forEach((col: any, idx: number) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (['ead', 'ecl', 'bookedProvision', 'variance'].includes(prop)) {
      sums[idx] = fmtAmt(data.reduce((acc, r) => acc + ((r as any)[prop] || 0), 0))
    } else {
      sums[idx] = ''
    }
  })
  return sums
}

// ─── ECL行差异>重要性行类名 ──────────────────────────────────────────────────

function eclRowClassName({ row }: { row: K1ECLCalcRow }): string {
  return isVarianceExceedsMateriality(row) ? 'variance-exceed-row' : ''
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiGenerate(section: string) {
  console.log('[K1-8] AI generate:', section)
}
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-bad-debt-calc {
  padding: 16px;
  font-size: 13px;
}

/* 方法论上下文（琥珀色） */
.methodology-context {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

/* 标题栏 */
.section-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.sheet-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0;
}
.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* Tabs */
.calc-tabs {
  margin-bottom: 16px;
}

/* 表格 */
.calc-table {
  font-size: 13px;
}
.amount-cell {
  font-variant-numeric: tabular-nums;
}
.amount-input {
  width: 100%;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.formula-cell.variance-exceed {
  color: var(--el-color-danger);
  font-weight: 600;
}
.conclusion-warn {
  color: var(--el-color-danger);
  font-weight: 600;
}

/* ECL差异超标行 */
:deep(.variance-exceed-row) {
  background-color: #fef2f2 !important;
}

/* 合计面板 */
.totals-panel {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-top: 16px;
  padding: 12px 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  border: 1px solid var(--el-border-color-lighter);
}
.total-item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.total-label {
  font-size: 11px;
  color: var(--el-text-color-secondary);
}
.total-value {
  font-size: 14px;
  font-weight: 600;
  font-variant-numeric: tabular-nums;
}
.total-item.total-exceed .total-value {
  color: var(--el-color-danger);
}
.materiality-input {
  width: 120px;
}

/* 差异警告 */
.variance-warning {
  margin-top: 12px;
}

/* 编制提示 */
.compile-hint {
  margin-top: 16px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
