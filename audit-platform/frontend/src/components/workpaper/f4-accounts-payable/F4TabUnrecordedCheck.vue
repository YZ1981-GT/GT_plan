<script setup lang="ts">
/**
 * F4TabUnrecordedCheck — F4-7 未入账检查（反向截止测试）
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.3
 * 顶部"截止自动提取"按钮(useCutoffAutoSampling)
 * 3区域独立el-table（期后采购/入库/收票）
 * "应入当期"="是" 橙色高亮
 * 各区域独立增删 + 底部小计 + 底部总结textarea(AI)
 * 虚拟滚动(104行) + 导入导出
 * Requirements: 10.1~10.8, 14.6
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4UnrecordedCheck, REGION_CONFIGS } from '../composables/useF4UnrecordedCheck'
import type { UnrecordedRegion, UnrecordedCheckRow } from '../composables/useF4UnrecordedCheck'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  purchaseRows,
  receiptRows,
  invoiceRows,
  purchaseSubtotal,
  receiptSubtotal,
  invoiceSubtotal,
  overallSummary,
  auditConclusion,
  addRow,
  removeRow,
  updateCell,
  distributeCutoffSamples,
  rowClassName,
} = useF4UnrecordedCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── 截止自动提取 ────────────────────────────────────────────────────────────
const cutoffLoading = ref(false)

async function handleCutoffExtract() {
  cutoffLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/cutoff-auto-sampling`, {
      accountCode: '2202',
      dayRange: 5,
    })
    const vouchers = data?.data?.vouchers || data?.vouchers || []
    if (!vouchers.length) {
      ElMessage.warning('无法提取截止数据：序时账无匹配凭证')
      return
    }
    distributeCutoffSamples(vouchers)
    ElMessage.success(`截止自动提取完成：共 ${vouchers.length} 条分配到3区域`)
  } catch {
    ElMessage.error('截止自动提取失败')
  } finally {
    cutoffLoading.value = false
  }
}

// ─── AI 生成结论 ─────────────────────────────────────────────────────────────
const aiLoading = ref(false)

async function generateAiConclusion() {
  aiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/unrecorded-conclusion`)
    auditConclusion.value = data?.data?.conclusion || data?.conclusion || ''
    ElMessage.success('AI结论已生成')
  } catch {
    ElMessage.error('AI生成失败')
  } finally {
    aiLoading.value = false
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-7`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-7未入账检查模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-7`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-7未入账检查数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-7`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getRegionRows(region: UnrecordedRegion) {
  if (region === 'purchase') return purchaseRows.value
  if (region === 'receipt') return receiptRows.value
  return invoiceRows.value
}

function getRegionSubtotal(region: UnrecordedRegion) {
  if (region === 'purchase') return purchaseSubtotal.value
  if (region === 'receipt') return receiptSubtotal.value
  return invoiceSubtotal.value
}
</script>

<template>
  <div class="f4-tab-unrecorded">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 未入账检查是反向截止测试：检查资产负债表日后是否存在应属于本期的未入账应付款。</p>
        <p>2. 3区域分别检查：期后采购（未入账采购）、期后入库（货到票未到）、期后收票（票据回溯）。</p>
        <p>3. "截止自动提取"将从序时账±5天范围内自动提取并分配到对应区域。</p>
        <p>4. "应入当期"="是" 的行橙色高亮，表示该笔应调整计入当期。</p>
        <p>5. 底部汇总合计所有"应入当期"的金额作为建议调整数。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：执行反向截止测试，检查资产负债表日后是否存在应属本期而未入账的应付账款(2202)，验证负债的完整性。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button
          type="primary"
          size="small"
          :loading="cutoffLoading"
          :disabled="isReadonly"
          @click="handleCutoffExtract"
        >截止自动提取</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:F4-8" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ purchaseRows.length + receiptRows.length + invoiceRows.length }} 行</el-tag>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-7-unrecorded')"
        >复核</el-button>
      </div>
    </div>

    <!-- ─── 3区域独立表格 ─────────────────────────────────────────────── -->
    <template v-for="cfg in REGION_CONFIGS" :key="cfg.key">
      <div class="region-section">
        <div class="region-header">
          <h4 class="region-title">{{ cfg.label }}</h4>
          <el-button size="small" :disabled="isReadonly" @click="addRow(cfg.key)">+ 新增行</el-button>
        </div>

        <el-table
          :data="getRegionRows(cfg.key)"
          border
          size="small"
          :row-class-name="rowClassName"
          style="width: 100%; font-size: 13px"
          max-height="400"
        >
          <el-table-column prop="seq" label="序号" width="60" />
          <el-table-column :label="cfg.dateLabel" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.date" size="small" placeholder="YYYY-MM-DD" @change="(v: string) => updateCell(cfg.key, row.rowId, 'date', v)" />
              <span v-else>{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="cfg.counterpartyLabel" min-width="130">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.counterparty" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'counterparty', v)" />
              <span v-else>{{ row.counterparty }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(cfg.key, row.rowId, 'amount', v ?? 0)" />
              <span v-else>{{ fmtAmount(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="cfg.documentLabel" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.documentNo" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'documentNo', v)" />
              <span v-else>{{ row.documentNo }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="cfg.descriptionLabel" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.description" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'description', v)" />
              <span v-else>{{ row.description }}</span>
            </template>
          </el-table-column>
          <el-table-column label="应入当期" min-width="90">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" :model-value="row.shouldRecordCurrent" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'shouldRecordCurrent', v)">
                <el-option label="" value="" />
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else :class="{ 'highlight-yes': row.shouldRecordCurrent === '是' }">{{ row.shouldRecordCurrent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="入账建议" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.suggestion" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'suggestion', v)" />
              <span v-else>{{ row.suggestion }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.remark" size="small" @change="(v: string) => updateCell(cfg.key, row.rowId, 'remark', v)" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="60">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(cfg.key, row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <div class="region-subtotal">
          总金额：{{ fmtAmount(getRegionSubtotal(cfg.key).totalAmount) }}
          ｜应入当期：{{ getRegionSubtotal(cfg.key).shouldRecordCount }}笔 / {{ fmtAmount(getRegionSubtotal(cfg.key).shouldRecordAmount) }}
        </div>
      </div>
    </template>

    <!-- ─── 底部总结 ──────────────────────────────────────────────────── -->
    <div class="summary-section">
      <div class="summary-stats">
        <span>未入账应付合计：<strong>{{ fmtAmount(overallSummary.unrecordedTotal) }}</strong></span>
        <span>合计笔数：<strong>{{ overallSummary.unrecordedCount }}</strong></span>
        <span>建议调整金额：<strong>{{ fmtAmount(overallSummary.suggestedAdjustment) }}</strong></span>
      </div>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
          <div class="opinion-chips">
            <GtIndexChip value="wp:F4-8" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :loading="aiLoading" :disabled="isReadonly" @click="generateAiConclusion">🤖 AI辅助</el-button>
            <el-button
              v-if="openReviewDialog"
              size="small"
              @click="openReviewDialog('f4-7-conclusion')"
            >💬</el-button>
          </div>
        </div>
        <el-input
          v-model="auditConclusion"
          type="textarea"
          :autosize="{ minRows: 3, maxRows: 10 }"
          :disabled="isReadonly"
          placeholder="请输入未入账检查审计结论，或点击AI辅助生成..."
        />
      </div>
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-unrecorded {
  font-size: 13px;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
  font-size: 13px;
}
.guidance-details .guidance-content {
  margin-top: 8px;
  font-size: 13px;
  color: #606266;
  line-height: 1.6;
}
.guidance-details .guidance-content p {
  margin: 2px 0;
}
.audit-objective {
  margin-bottom: 12px;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}
.chip-wrap {
  display: inline-flex;
  align-items: center;
}
.region-section {
  margin-bottom: 20px;
}
.region-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.region-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.region-subtotal {
  margin-top: 6px;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
:deep(.should-record-highlight td) {
  background: #fef3e6 !important;
}
.highlight-yes {
  color: #e6a23c;
  font-weight: 600;
}
.summary-section {
  margin: 16px 0 12px;
  padding: 10px 12px;
  background: #ecf5ff;
  border-radius: 4px;
}
.summary-stats {
  display: flex;
  gap: 24px;
  font-size: 13px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips {
  display: flex;
  gap: 6px;
}
.opinion-section {
  margin-bottom: 0;
}
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
