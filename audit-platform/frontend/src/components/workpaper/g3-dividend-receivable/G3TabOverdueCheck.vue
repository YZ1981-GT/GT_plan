<!--
  G3TabOverdueCheck.vue — G3-5 长期未收回检查（13列）

  Uses useG3OverdueCheck composable
  Row class: getOverdueRiskClass (>180天红色 / >90天橙色)
  Dropdowns: recoverability(预计可收回性) + riskLevel(风险等级)
  底部汇总: 逾期笔数 / 逾期总金额 / 高风险笔数
  AI结论 + 动态行增删 + 导入导出

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.4
  Requirements: 8.1~8.8
-->
<template>
  <div class="g3-overdue-check">
    <div class="section-head">
      <h3 class="sheet-title">G3-5 长期未收回检查</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="overdue.addRow()">＋ 新增</el-button>
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
        <el-button size="small" @click="openReviewDialog('G3-5-overdue')">💬复核</el-button>
        <GtIndexChip value="wp:G3-5" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ overdue.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：评估长期未收回应收股利的可收回性与减值风险，关注被投资方经营状况及偿付能力，识别高风险逾期事项。"
    />

    <el-table
      :data="overdue.rows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
      class="overdue-table"
    >
      <!-- 序号 -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">{{ row.seq }}</template>
      </el-table-column>

      <!-- 被投资方 -->
      <el-table-column label="被投资方" width="150" fixed>
        <template #default="{ row }">
          <el-input :model-value="row.investeeName" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { investeeName: v })" />
        </template>
      </el-table-column>

      <!-- 应收金额 -->
      <el-table-column label="应收金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.receivableAmount" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => overdue.updateRow(row.id, { receivableAmount: v ?? 0 })" />
        </template>
      </el-table-column>

      <!-- 宣告日 -->
      <el-table-column label="宣告日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.declarationDate" type="date" size="small"
            value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => overdue.updateRow(row.id, { declarationDate: v ?? '' })" />
        </template>
      </el-table-column>

      <!-- 约定付款日 -->
      <el-table-column label="约定付款日" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.agreedPaymentDate" type="date" size="small"
            value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => overdue.updateRow(row.id, { agreedPaymentDate: v ?? '' })" />
        </template>
      </el-table-column>

      <!-- 逾期天数（公式列） -->
      <el-table-column label="逾期天数" width="100" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="逾期天数 = MAX(0, 当前日期 - 约定付款日)">
            {{ row.overdueDays }}
          </span>
        </template>
      </el-table-column>

      <!-- 逾期原因 -->
      <el-table-column label="逾期原因" width="150">
        <template #default="{ row }">
          <el-input :model-value="row.overdueReason" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { overdueReason: v })" />
        </template>
      </el-table-column>

      <!-- 被投资方经营状况 -->
      <el-table-column label="经营状况" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.investeeOperatingStatus" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { investeeOperatingStatus: v })" />
        </template>
      </el-table-column>

      <!-- 历史分红记录 -->
      <el-table-column label="历史分红记录" width="150">
        <template #default="{ row }">
          <el-input :model-value="row.historicalDividendRecord" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { historicalDividendRecord: v })" />
        </template>
      </el-table-column>

      <!-- 预计可收回性(下拉) -->
      <el-table-column label="预计可收回性" width="140">
        <template #default="{ row }">
          <el-select :model-value="row.recoverability" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { recoverability: v as any })">
            <el-option v-for="opt in overdue.RECOVERABILITY_OPTIONS" :key="opt.value"
              :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 风险等级(下拉) -->
      <el-table-column label="风险等级" width="100">
        <template #default="{ row }">
          <el-select :model-value="row.riskLevel" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { riskLevel: v as any })">
            <el-option v-for="opt in overdue.RISK_LEVEL_OPTIONS" :key="opt.value"
              :value="opt.value" :label="opt.label" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 审计建议 -->
      <el-table-column label="审计建议" width="160">
        <template #default="{ row }">
          <el-input :model-value="row.auditSuggestion" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { auditSuggestion: v })" />
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { remark: v })" />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="overdue.removeRow(row.id)"><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部汇总 -->
    <div class="summary-bar">
      <span class="summary-label">汇总</span>
      <span class="summary-item">逾期笔数：{{ overdue.summary.value.overdueCount }}</span>
      <span class="summary-item">逾期总金额：{{ fmtNum(overdue.summary.value.overdueTotal) }}</span>
      <span class="summary-item">高风险笔数：{{ overdue.summary.value.highRiskCount }}</span>
    </div>

    <!-- 审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" :disabled="isReadonly" @click="fillAiConclusion">🤖AI辅助</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对长期未收回应收股利的风险评估结论..."
        @change="persistConclusion"
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. 逾期天数 = MAX(0, 当前日期 - 约定付款日)。</p>
        <p>2. 逾期 &gt; 180 天：红色高亮（极高风险）；逾期 &gt; 90 天且 ≤180 天：橙色高亮（高风险）。</p>
        <p>3. 预计可收回性：全额可收回 / 部分可收回 / 很可能无法收回 / 无法收回。</p>
        <p>4. 风险等级：低 / 中 / 高 / 极高；需关注被投资方经营状况及历史分红记录，综合评估收回可能性。</p>
        <p class="cas-basis">CAS 依据：应对应收款项的可收回性进行评估并考虑减值（《企业会计准则第 22 号——金融工具确认和计量》预期信用损失）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import {
  useG3OverdueCheck,
  getOverdueRiskClass,
} from '../composables/useG3OverdueCheck'
import type { OverdueDividendRow } from '../composables/useG3OverdueCheck'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const overdue = useG3OverdueCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── 审计结论 ───
const CONCLUSION_KEY = 'G3-5-overdue-conclusion'
const auditConclusion = ref(
  props.allResponses.get(CONCLUSION_KEY)?.conclusion ?? '',
)

function persistConclusion() {
  if (!props.isReadonly) {
    props.debouncedSave(CONCLUSION_KEY, { conclusion: auditConclusion.value })
  }
}

// ─── Row class for risk highlighting ───
function rowClassName({ row }: { row: OverdueDividendRow }): string {
  return getOverdueRiskClass(row)
}

// ─── AI辅助结论 ───
function fillAiConclusion() {
  if (props.isReadonly) return
  const s = overdue.summary.value
  const rows = overdue.rows.value

  const draft =
    `经检查，共 ${rows.length} 笔应收股利中，` +
    `逾期未收回 ${s.overdueCount} 笔，逾期总金额 ${fmtNum(s.overdueTotal)} 元。` +
    (s.highRiskCount > 0
      ? `其中高风险 ${s.highRiskCount} 笔，需重点关注。`
      : '未发现高风险逾期事项。') +
    (s.overdueCount === 0
      ? ' 各笔应收股利均在约定期限内，收回风险可控。'
      : ' 建议对逾期金额较大项目进一步核实被投资方经营状况及偿付能力。')

  auditConclusion.value = auditConclusion.value
    ? `${auditConclusion.value}\n${draft}`
    : draft
  persistConclusion()
}

// ─── Formatting ───
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v ?? '')
}

// ─── 导入导出（占位，useG3ImportExport Task 8.2 实现） ───
function handleExportTemplate() { ElMessage.info('导出模板功能将在导入导出模块完成后启用') }
function handleExportData() { ElMessage.info('导出数据功能将在导入导出模块完成后启用') }
function handleImportData() { ElMessage.info('导入数据功能将在导入导出模块完成后启用') }
</script>

<style scoped>
.g3-overdue-check {
  padding: 12px;
  font-size: 13px;
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
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 公式列：灰底 + 虚线下划线 + cursor:help */
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
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

/* 底部汇总 */
.summary-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  flex-wrap: wrap;
}
.summary-label {
  color: #303133;
  min-width: 36px;
}
.summary-item {
  color: #606266;
}

/* 审计结论 */
.conclusion-card {
  margin-top: 12px;
}
.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

/* 审计目标 */
.audit-objective {
  margin-bottom: 12px;
}

/* 编制提示（guidance-details gold 样式） */
.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>

<!-- 非 scoped — el-table 行级样式穿透 -->
<style>
.g3-overdue-check .overdue-danger {
  background-color: #fef0f0 !important;
}
.g3-overdue-check .overdue-danger td {
  background-color: #fef0f0 !important;
}
.g3-overdue-check .overdue-warning {
  background-color: #fdf6ec !important;
}
.g3-overdue-check .overdue-warning td {
  background-color: #fdf6ec !important;
}
</style>
