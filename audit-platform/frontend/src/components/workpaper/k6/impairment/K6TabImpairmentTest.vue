<template>
  <div class="k6-tab-impairment-test">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>计价和分摊：</b>持有待售资产按账面价值与公允价值减出售费用后净额孰低计量，减值损失计算准确；</li>
        <li><b>完整性：</b>应计提的减值损失均已确认，公允价值/出售费用估计合理。</li>
      </ol>
    </el-alert>

    <!-- ═══ 蓝色渐变引导区 ═══ -->
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step">
          <span class="step-num">①</span>
          <span>逐项录入账面价值、公允价值、出售费用</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">②</span>
          <span>公式自动计算：公允净额 = 公允 - 出售费用</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">③</span>
          <span>孰低法：减值 = MAX(0, 账面 - 公允净额)</span>
        </div>
        <div class="guidance-step">
          <span class="step-num">④</span>
          <span>核对已计提 → 计算应补提 → AI辅助生成结论</span>
        </div>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色块） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 后续计量（孰低法）：</strong>企业对持有待售的非流动资产或处置组，应当按照<strong>账面价值与公允价值减去出售费用后的净额孰低</strong>进行后续计量。后者低于前者的差额确认为减值损失（资产减值损失）。已划分为持有待售的非流动资产不应计提折旧或进行摊销。</p>
    </div>

    <!-- ═══ 交叉验证提示 ═══ -->
    <el-alert
      v-if="crossValidationDiff !== 0"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
    >
      <template #title>
        与K6-1审定表减值准备列差异 {{ fmtAmt(crossValidationDiff) }} 元，请核对
      </template>
    </el-alert>

    <!-- ═══ 减值测试主表 ═══ -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">K6-5 减值准备测试表（孰低法）</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" plain :loading="aiLoading" @click="handleAiGenerate">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" circle @click="openReview('K6-5')">💬</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="impairmentRows"
        border
        stripe
        size="small"
        class="impairment-table"
        row-key="rowId"
        max-height="520"
      >
        <!-- 序号 -->
        <el-table-column type="index" label="序号" width="52" align="center" />

        <!-- 项目 -->
        <el-table-column prop="assetName" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.assetName"
              size="small"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'assetName', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.assetName || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 账面价值 -->
        <el-table-column label="账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookValue"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'bookValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>

        <!-- 公允价值 -->
        <el-table-column label="公允价值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.fairValue"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'fairValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.fairValue) }}</span>
          </template>
        </el-table-column>

        <!-- 公允价值确定依据 -->
        <el-table-column label="公允价值确定依据" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.fairValueBasis"
              size="small"
              placeholder="如：评估报告/活跃市场报价/协议价"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'fairValueBasis', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.fairValueBasis || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 出售费用 -->
        <el-table-column label="出售费用" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.sellingCost"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'sellingCost', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.sellingCost) }}</span>
          </template>
        </el-table-column>

        <!-- 公允净额（公式列） -->
        <el-table-column label="公允净额" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="= 公允价值 - 出售费用">公允净额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 公允价值 - 出售费用" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.fairValueNet) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 减值金额（公式列） -->
        <el-table-column label="减值金额" min-width="120" align="right">
          <template #header>
            <span class="formula-header" title="= MAX(0, 账面价值 - 公允净额)（孰低法）">减值金额</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= MAX(0, 账面 - 公允净额)（孰低法）" placement="top">
              <span :class="['formula-cell', { 'impaired-amount': row.impairmentAmount > 0 }]">
                {{ fmtAmt(row.impairmentAmount) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 已计提 -->
        <el-table-column label="已计提" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.existingProvision"
              :controls="false"
              size="small"
              class="amt-input"
              @change="(v: number | null) => updateCell(row.rowId, 'existingProvision', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.existingProvision) }}</span>
          </template>
        </el-table-column>

        <!-- 应补提（公式列） -->
        <el-table-column label="应补提" min-width="110" align="right">
          <template #header>
            <span class="formula-header" title="= 减值金额 - 已计提">应补提</span>
          </template>
          <template #default="{ row }">
            <el-tooltip content="= 减值金额 - 已计提" placement="top">
              <span :class="['formula-cell', { 'provision-positive': row.additionalProvision > 0, 'provision-negative': row.additionalProvision < 0 }]">
                {{ fmtAmt(row.additionalProvision) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>

        <!-- 结论 -->
        <el-table-column label="结论" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.conclusion"
              size="small"
              placeholder="结论"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'conclusion', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.conclusion || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 备注 -->
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              size="small"
              placeholder="备注"
              @blur="(e: FocusEvent) => updateCell(row.rowId, 'remark', (e.target as HTMLInputElement)?.value ?? '')"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ $index }">
            <el-button size="small" type="danger" link @click="removeRow($index)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计行 -->
      <div class="summary-row">
        <span class="summary-label">合计</span>
        <span class="summary-item">账面: <strong>{{ fmtAmt(subtotals.bookValue) }}</strong></span>
        <span class="summary-item">公允净额: <strong>{{ fmtAmt(subtotals.fairValueNet) }}</strong></span>
        <span class="summary-item" :class="{ 'impaired-amount': subtotals.impairmentAmount > 0 }">
          减值: <strong>{{ fmtAmt(subtotals.impairmentAmount) }}</strong>
        </span>
        <span class="summary-item">已计提: <strong>{{ fmtAmt(subtotals.existingProvision) }}</strong></span>
        <span class="summary-item" :class="{ 'provision-positive': subtotals.additionalProvision > 0 }">
          应补提: <strong>{{ fmtAmt(subtotals.additionalProvision) }}</strong>
        </span>
        <span class="summary-item">{{ subtotals.count }} 项</span>
      </div>

      <!-- 新增按钮 -->
      <div v-if="!isReadonly" class="add-row-bar">
        <el-button size="small" @click="addRow()">+ 新增</el-button>
      </div>
    </el-card>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明与结论</span>
          <el-button size="small" type="primary" link :loading="aiLoading" @click="handleAiConclusion">
            <el-icon><MagicStick /></el-icon> AI生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="请填写减值测试结论（如：经减值测试，各资产公允价值减出售费用后的净额均高于/低于其账面价值…）"
        @blur="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>公允价值净额 = 公允价值 - 预计出售费用（可为负，此时减值=全部账面价值）</li>
        <li>减值金额 = MAX(0, 账面价值 - 公允价值净额)，即孰低法</li>
        <li>应补提 = 减值金额 - 已计提减值准备（正数=需补提，负数=可转回但有上限）</li>
        <li>CAS42转回上限：不超过假设未划分持有待售时确认的折旧/摊销调整后的账面价值</li>
        <li>与K6-1审定表"减值准备"列交叉验证，差异应核对说明</li>
        <li>处置组减值请跳转K6-6进行分摊计算</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabImpairmentTest.vue — K6-5 减值准备测试表（孰低法，23行虚拟滚动）
 *
 * 减值测试表：项目/账面价值/公允价值/出售费用/公允净额(公式)/减值(公式)/已计提/应补提(公式)/结论/备注
 * 公式列虚线下划线 + tooltip
 * 与K6-1审定减值准备交叉验证
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.5
 * Requirements: 5.1-5.6
 */
import { ref, computed, inject } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK6Impairment } from '../../composables/useK6Impairment'
import http from '@/utils/http'

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

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponse(field: string, value: any): Promise<void> {
  emit('save', field, value)
  return Promise.resolve()
}

const {
  impairmentRows,
  subtotals,
  auditConclusion,
  updateCell,
  addRow,
  removeRow,
  saveConclusion,
} = useK6Impairment({
  allResponses: allResponsesRef,
  saveResponse,
})

// ─── Cross Validation with K6-1 ─────────────────────────────────────────────

const crossValidationDiff = computed(() => {
  const k6_1_impairment = props.allResponses.get('K6-1-impairment-total')
  const k6_1_val = Number(k6_1_impairment?.remark ?? k6_1_impairment?.conclusion ?? 0) || 0
  return subtotals.value.impairmentAmount - k6_1_val
})

// ─── AI ──────────────────────────────────────────────────────────────────────

const aiLoading = ref(false)

async function handleAiGenerate() {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const context = `减值测试合计：账面价值${subtotals.value.bookValue}，公允净额${subtotals.value.fairValueNet}，减值${subtotals.value.impairmentAmount}，已计提${subtotals.value.existingProvision}，应补提${subtotals.value.additionalProvision}，共${subtotals.value.count}项`
    const resp = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'impairment-conclusion',
      context,
      prompt: '根据减值测试结果，生成持有待售资产减值测试审计结论',
      existingContent: auditConclusion.value,
    })
    const text = resp?.data?.content || resp?.data?.text || resp?.content || ''
    if (text) {
      auditConclusion.value = text
      saveConclusion()
      ElMessage.success('AI结论已生成')
    }
  } catch (e: any) {
    ElMessage.error('AI生成失败: ' + (e?.message || '未知错误'))
  } finally {
    aiLoading.value = false
  }
}

async function handleAiConclusion() {
  await handleAiGenerate()
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-impairment-test {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 蓝色渐变引导区 */
.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border-radius: 8px;
  padding: 14px 18px;
  margin-bottom: 16px;
  border: 1px solid #b3d8fd;
}
.guidance-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 24px;
}
.guidance-step {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #1d3557;
}
.step-num {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: #409eff;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}

/* 琥珀色方法论上下文 */
.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  border-radius: 4px;
  padding: 12px 16px;
  margin-bottom: 16px;
  font-size: 12.5px;
  color: #78350f;
  line-height: 1.6;
}

/* 交叉验证提示 */
.cross-alert {
  margin-bottom: 16px;
}

/* 块卡片 */
.block-card {
  margin-bottom: 16px;
}

/* Section标题 */
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.section-title {
  font-weight: 600;
  font-size: 14px;
}
.section-header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.impairment-table {
  font-size: var(--wp-font-size, 13px);
}
.impairment-table :deep(.el-table__cell) {
  padding: 6px 0;
}
.amt-input {
  width: 100%;
}
.amt-input :deep(.el-input__inner) {
  text-align: right;
}
.amt-cell {
  font-variant-numeric: tabular-nums;
}

/* 公式列：虚线下划线 + cursor:help */
.formula-header {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 2px;
}
.formula-cell {
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
  padding-bottom: 1px;
  font-variant-numeric: tabular-nums;
}

/* 减值金额高亮 */
.impaired-amount {
  color: #dc2626;
  font-weight: 600;
}
.provision-positive {
  color: #dc2626;
}
.provision-negative {
  color: #059669;
}

/* 合计行 */
.summary-row {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 12px;
  margin-top: 10px;
  background: #f9fafb;
  border-radius: 4px;
  border: 1px solid #e5e7eb;
  font-size: var(--wp-font-size, 13px);
  flex-wrap: wrap;
}
.summary-label {
  font-weight: 600;
  color: #374151;
}
.summary-item {
  color: #4b5563;
}

/* 新增按钮 */
.add-row-bar {
  padding-top: 10px;
}

/* 审计结论卡 */
.audit-note-card {
  margin-bottom: 16px;
}

/* 编制提示 */
.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #6b7280;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
}
.edit-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #374151;
}
.edit-tips ul {
  margin: 8px 0 0 0;
  padding-left: 18px;
  line-height: 1.8;
}
</style>
