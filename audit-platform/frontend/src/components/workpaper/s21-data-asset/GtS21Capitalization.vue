<template>
  <div class="s21-capitalization">
    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>审计目标</template>
      <div class="audit-objective-text">
        核查数据资产开发支出资本化的合规性：验证资本化5项条件是否全部满足、开发支出按月归集的完整准确性、类目合计与占比计算，确认资本化金额符合《企业会计准则第6号——无形资产》确认条件。
      </div>
    </el-alert>

    <!-- ─── 蓝色渐变引导区（多步骤底稿） ─── -->
    <div class="guide-banner">
      <div class="guide-grid">
        <div class="guide-step">
          <span class="step-number">①</span>
          <span class="step-text">判断资本化5项条件是否满足</span>
        </div>
        <div class="guide-step">
          <span class="step-number">②</span>
          <span class="step-text">按月归集各类目开发支出金额</span>
        </div>
        <div class="guide-step">
          <span class="step-number">③</span>
          <span class="step-text">系统自动计算合计与占比（公式不可覆盖）</span>
        </div>
        <div class="guide-step">
          <span class="step-number">④</span>
          <span class="step-text">确认资本化总额并生成审计结论</span>
        </div>
      </div>
    </div>

    <!-- ─── 区段一：资本化5项条件判断（Req 5.4） ─── -->
    <el-card shadow="never" class="audit-section">
      <template #header>
        <div class="section-header">
          <span>资本化时点判断 — 5 项条件</span>
          <GtIndexChip value="CAS6" />
        </div>
      </template>

      <!-- 方法论上下文 -->
      <div class="methodology-context">
        <p>根据《企业会计准则第6号——无形资产》，企业内部研究开发项目开发阶段的支出，同时满足下列条件的，才能确认为无形资产：</p>
      </div>

      <el-table
        :data="capitalizationConditions"
        border
        style="width: 100%; font-size: 13px"
      >
        <el-table-column type="index" label="序号" width="60" align="center" />
        <el-table-column prop="condition" label="资本化条件" min-width="250" />
        <el-table-column prop="judgment" label="判断结论" width="140" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.judgment"
              size="small"
              placeholder="请选择"
            >
              <el-option label="满足" value="满足" />
              <el-option label="不满足" value="不满足" />
              <el-option label="不适用" value="不适用" />
            </el-select>
            <el-tag
              v-else
              :type="row.judgment === '满足' ? 'success' : row.judgment === '不满足' ? 'danger' : 'info'"
              size="small"
            >
              {{ row.judgment || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据" min-width="300">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.evidence"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              size="small"
              placeholder="填写判断依据"
            />
            <span v-else>{{ row.evidence || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- 研究/开发阶段合计 -->
      <div class="phase-summary">
        <el-descriptions :column="3" border size="small" class="phase-descriptions">
          <el-descriptions-item label="研究阶段支出合计">
            <span class="formula-cell" title="SUM(研究阶段各项支出)">
              {{ fmtAmount(researchDevResult.researchTotal) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="开发阶段支出合计">
            <span class="formula-cell" title="SUM(开发阶段各项支出)">
              {{ fmtAmount(researchDevResult.developmentTotal) }}
            </span>
          </el-descriptions-item>
          <el-descriptions-item label="资本化条件结论">
            <el-tag :type="allConditionsMet ? 'success' : 'warning'" size="small">
              {{ allConditionsMet ? '全部满足，可资本化' : '存在未满足条件' }}
            </el-tag>
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- ─── 区段二：资本化金额按月归集 12月网格（核心计算） ─── -->
    <el-card shadow="never" class="audit-section capitalization-grid-section">
      <template #header>
        <div class="section-header">
          <span>开发支出资本化 — 按月归集（S21-2）</span>
          <div class="section-header-right">
            <el-dropdown trigger="click" @command="handleImportExport">
              <el-button size="small">
                导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
              </el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
                  <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
                  <el-dropdown-item v-if="!isReadonly" command="importData">导入数据</el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
          </div>
        </div>
      </template>

      <div class="grid-table-wrapper">
        <table class="cap-grid-table">
          <thead>
            <tr>
              <th class="category-col">成本类目</th>
              <th v-for="m in 12" :key="m" class="month-col">{{ m }}月</th>
              <th class="total-col">合计</th>
              <th class="ratio-col">占比</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(cat, idx) in categories" :key="cat.key">
              <td class="category-col">{{ cat.label }}</td>
              <td v-for="m in 12" :key="m" class="month-col">
                <el-input-number
                  v-if="!isReadonly"
                  v-model="monthlyData[cat.key][m - 1]"
                  :controls="false"
                  :precision="2"
                  size="small"
                  class="month-input"
                />
                <span v-else>{{ fmtAmount(monthlyData[cat.key][m - 1]) }}</span>
              </td>
              <!-- 合计（公式，不可覆盖） -->
              <td class="total-col">
                <span class="formula-cell" :title="`${cat.label}合计 = SUM(1-12月)`">
                  {{ fmtAmount(capResult.categoryTotals[cat.key] || 0) }}
                </span>
              </td>
              <!-- 占比（公式，不可覆盖） -->
              <td class="ratio-col">
                <span
                  class="formula-cell"
                  :class="{ unable: capResult.unable }"
                  :title="`${cat.label}占比 = 类目合计 ÷ 资本化总额`"
                >
                  {{ capResult.unable ? '—' : fmtPercent(capResult.categoryRatios[cat.key] || 0) }}
                </span>
              </td>
            </tr>
            <!-- 月合计行（公式） -->
            <tr class="summary-row">
              <td class="category-col"><strong>月合计</strong></td>
              <td v-for="m in 12" :key="m" class="month-col">
                <span class="formula-cell" :title="`${m}月合计 = SUM(各类目${m}月)`">
                  {{ fmtAmount(capResult.monthlyTotals[m - 1] || 0) }}
                </span>
              </td>
              <td class="total-col">
                <span class="formula-cell formula-total" title="资本化总额 = SUM(所有类目合计)">
                  {{ fmtAmount(capResult.total) }}
                </span>
              </td>
              <td class="ratio-col">
                <span class="formula-cell" title="总占比 = 100%（校验）">
                  {{ capResult.unable ? '—' : '100.00%' }}
                </span>
              </td>
            </tr>
            <!-- 月比例行（公式） -->
            <tr class="summary-row ratio-row">
              <td class="category-col"><strong>月比例</strong></td>
              <td v-for="m in 12" :key="m" class="month-col">
                <span
                  class="formula-cell"
                  :class="{ unable: capResult.unable }"
                  :title="`${m}月比例 = ${m}月合计 ÷ 资本化总额`"
                >
                  {{ capResult.unable ? '—' : fmtPercent(capResult.monthlyRatios[m - 1] || 0) }}
                </span>
              </td>
              <td class="total-col">—</td>
              <td class="ratio-col">—</td>
            </tr>
          </tbody>
        </table>
      </div>
    </el-card>

    <!-- ─── 审计结论 ─── -->
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header>
        <div class="section-header">
          <span>审计结论</span>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="填写开发支出资本化分析的审计结论"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-hints">
      <summary>编制提示</summary>
      <p>① 首先判断资本化5项条件是否全部满足，不满足则全部费用化。</p>
      <p>② 在"按月归集"网格中录入各月各类目的开发支出金额，合计与占比由公式自动计算（虚线下划线单元格不可手工覆盖）。</p>
      <p>③ 成本类目包括：采购成本、人工成本、脱敏清洗标注整合分析支出、数据权属鉴证费、质量评估费、登记结算费、安全管理费。</p>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * GtS21Capitalization.vue — 开发支出资本化分析表 S21-2（核心计算表）
 *
 * 功能：
 * - 资本化5项条件逐项判断（Req 5.4）
 * - 12月 × N类目网格表格（行=类目, 列=1-12月+合计+占比）
 * - 使用 useS21FormulaEngine 实时计算合计与占比
 * - 公式单元格只读不可手工覆盖（Req 5.6）
 * - 分月明细变更时汇总与占比实时重算
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.6
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 4.2
 */
import { ref, reactive, computed, defineAsyncComponent } from 'vue'
import { ArrowDown } from '@element-plus/icons-vue'
import {
  useS21FormulaEngine,
  type CapitalizationInput,
  type ResearchDevInput,
} from '../composables/useS21FormulaEngine'
import { useSEstimateImportExport } from '../composables/useSEstimateImportExport'
import { fmtAmount } from '@/utils/formatters'

const GtIndexChip = defineAsyncComponent(() => import('../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

// ─── 5项资本化条件 ───────────────────────────────────────────

interface ConditionRow {
  condition: string
  judgment: string
  evidence: string
}

const capitalizationConditions = ref<ConditionRow[]>([
  { condition: '完成该无形资产以使其能够使用或出售在技术上具有可行性', judgment: '', evidence: '' },
  { condition: '具有完成该无形资产并使用或出售的意图', judgment: '', evidence: '' },
  { condition: '无形资产产生经济利益的方式，包括能够证明运用该无形资产生产的产品存在市场或无形资产自身存在市场', judgment: '', evidence: '' },
  { condition: '有足够的技术、财务资源和其他资源支持，以完成该无形资产的开发，并有能力使用或出售该无形资产', judgment: '', evidence: '' },
  { condition: '归属于该无形资产开发阶段的支出能够可靠地计量（单独核算）', judgment: '', evidence: '' },
])

const allConditionsMet = computed(() =>
  capitalizationConditions.value.every(c => c.judgment === '满足'),
)

// ─── 成本类目定义 ────────────────────────────────────────────

const categories = [
  { key: 'purchase', label: '采购成本' },
  { key: 'labor', label: '人工成本' },
  { key: 'cleaning', label: '脱敏清洗标注整合分析支出' },
  { key: 'ownership', label: '数据权属鉴证费' },
  { key: 'quality', label: '质量评估费' },
  { key: 'registration', label: '登记结算费' },
  { key: 'security', label: '安全管理费' },
]

// ─── 月度数据（12月 × N类目） ────────────────────────────────

const monthlyData = reactive<Record<string, number[]>>(
  Object.fromEntries(categories.map(c => [c.key, new Array(12).fill(0)])),
)

// ─── 研究/开发阶段数据 ──────────────────────────────────────

const researchItems = ref<number[]>([0, 0, 0])
const developmentItems = ref<number[]>([0, 0, 0, 0, 0])

// ─── 公式引擎 ────────────────────────────────────────────────

const capInput = computed<CapitalizationInput>(() => ({
  monthly: { ...monthlyData },
}))

const rdInput = computed<ResearchDevInput>(() => ({
  researchItems: researchItems.value,
  developmentItems: developmentItems.value,
}))

const { capitalization, researchDev } = useS21FormulaEngine(capInput, rdInput)

const capResult = computed(() => capitalization.value)
const researchDevResult = computed(() => researchDev.value)

// ─── 审计结论 ────────────────────────────────────────────────

const auditConclusion = ref('')

// ─── 导入导出（Req 10.1, 10.2, 10.3） ───────────────────────

const importExport = useSEstimateImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

/** 导入导出 el-dropdown command handler */
function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('S21-2')
      break
    case 'exportData':
      importExport.exportData('S21-2')
      break
    case 'importData':
      _triggerFileUpload()
      break
  }
}

function _triggerFileUpload(): void {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e: Event) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    await importExport.importData('S21-2', file)
    // 导入成功后需重新加载数据（由父组件处理）
  }
  input.click()
}

// ─── 格式化 ──────────────────────────────────────────────────

function fmtPercent(val: number): string {
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.s21-capitalization {
  padding: 12px;
}

.audit-objective {
  margin-bottom: 12px;
}

.audit-objective-text {
  font-size: 13px;
  line-height: 1.6;
}

/* 蓝色渐变引导区 */
.guide-banner {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfa 100%);
  border: 1px solid #b3d8fd;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.guide-step {
  display: flex;
  align-items: center;
  gap: 8px;
}
.step-number {
  font-weight: 700;
  color: #409eff;
  font-size: 16px;
}
.step-text {
  font-size: 13px;
  color: #303133;
}

/* 方法论上下文 */
.methodology-context {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 13px;
  color: #606266;
}

.section-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.section-header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.audit-section {
  margin-bottom: 16px;
}

.phase-summary {
  margin-top: 16px;
}

/* 12月网格表格 */
.capitalization-grid-section {
  overflow-x: auto;
}
.grid-table-wrapper {
  overflow-x: auto;
}
.cap-grid-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  white-space: nowrap;
}
.cap-grid-table th,
.cap-grid-table td {
  border: 1px solid #ebeef5;
  padding: 6px 8px;
  text-align: center;
}
.cap-grid-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}
.category-col {
  text-align: left !important;
  min-width: 180px;
  white-space: nowrap;
}
.month-col {
  min-width: 90px;
}
.total-col {
  min-width: 100px;
  background: #fafafa;
}
.ratio-col {
  min-width: 80px;
  background: #fafafa;
}
.month-input {
  width: 80px;
}
.summary-row {
  background: #f0f9ff;
  font-weight: 600;
}
.ratio-row {
  background: #f5f5f5;
}

/* 公式单元格样式 */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  font-weight: 600;
  color: #303133;
  padding: 2px 4px;
}
.formula-cell.unable {
  color: #f56c6c;
  font-style: italic;
}
.formula-total {
  color: #409eff;
  font-size: 14px;
}

.audit-conclusion-card {
  margin-top: 16px;
}

.edit-hints {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-hints summary {
  cursor: pointer;
  user-select: none;
}
</style>
