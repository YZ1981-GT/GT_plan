<template>
  <div class="k6-tab-adjudication">
    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>CAS42 持有待售</strong>：持有待售资产按账面价值与公允价值减去出售费用后的净额孰低计量。
        资产科目1481（借方）期末=期初+增加-减少-减值；负债科目2605（贷方）期末=期初+增加-减少。
        审定数=未审数+AJE+RJE。三角勾稽要求期末(公式)与审定数一致或差异合理。</p>
    </div>

    <!-- ═══ 持有待售资产区块（1481，借方/资产类） ═══ -->
    <div v-for="section in adjudicationSections" :key="section.sectionKey" class="adj-section">
      <div class="section-header">
        <h4 class="section-title">{{ section.sectionLabel }}</h4>
        <div class="section-actions">
          <el-button size="small" text type="primary" @click="handleAiGenerate(section.sectionKey)">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
          <el-button size="small" text @click="handleReview(section.sectionKey)">
            <el-icon><View /></el-icon> 复核
          </el-button>
        </div>
      </div>

      <!-- 三角勾稽告警 -->
      <el-alert
        v-if="section.sectionKey === 'asset' && !assetReconciliation.isBalanced"
        type="error"
        :closable="false"
        show-icon
        class="reconciliation-alert"
      >
        资产区块三角勾稽不平！差异 = {{ fmtAmt(assetReconciliation.diff) }} 元
      </el-alert>
      <el-alert
        v-if="section.sectionKey === 'liability' && !liabilityReconciliation.isBalanced"
        type="error"
        :closable="false"
        show-icon
        class="reconciliation-alert"
      >
        负债区块三角勾稽不平！差异 = {{ fmtAmt(liabilityReconciliation.diff) }} 元
      </el-alert>

      <!-- 审定表 el-table -->
      <el-table
        :data="getDisplayRows(section)"
        border
        size="small"
        style="width: 100%"
        :row-class-name="({ row }) => getRowClassName(row, section.sectionKey)"
      >
        <el-table-column prop="label" label="项目" min-width="120" fixed />
        <el-table-column label="期初" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.begin"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'begin', v)"
            />
            <span v-else>{{ fmtAmt(row.begin) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.increase"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'increase', v)"
            />
            <span v-else>{{ fmtAmt(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.decrease"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'decrease', v)"
            />
            <span v-else>{{ fmtAmt(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="section.sectionKey === 'asset'" label="减值准备" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.impairment"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'impairment', v)"
            />
            <span v-else>{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末(公式)" min-width="110" align="right" class-name="formula-col">
          <template #header>
            <el-tooltip :content="section.sectionKey === 'asset' ? '期末=期初+增加-减少-减值' : '期末=期初+增加-减少'" placement="top">
              <span class="formula-header">期末<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.end) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.unadjusted"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'unadj', v)"
            />
            <span v-else>{{ fmtAmt(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.aje"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'aje', v)"
            />
            <span v-else>{{ fmtAmt(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.rje"
              :controls="false"
              size="small"
              class="adj-input"
              @change="(v) => onFieldChange(section.sectionKey, row.rowKey, 'rje', v)"
            />
            <span v-else>{{ fmtAmt(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数(公式)" min-width="110" align="right" class-name="formula-col">
          <template #header>
            <el-tooltip content="审定数=未审+AJE+RJE" placement="top">
              <span class="formula-header">审定数<el-icon class="formula-icon"><QuestionFilled /></el-icon></span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="80" align="right">
          <template #default="{ row }">
            <span :class="{ 'rate-warning': row.variationRate != null && Math.abs(row.variationRate) > 0.3 }">
              {{ row.variationRate != null ? (row.variationRate * 100).toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="row.rowKey !== 'subtotal' && !isReadonly"
              v-model="row.remark"
              size="small"
              @change="(v) => onRemarkChange(section.sectionKey, row.rowKey, v)"
            />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="tb-writeback-section">
      <el-button
        type="primary"
        :loading="publishing"
        :disabled="isReadonly"
        @click="handleWritebackTB"
      >
        <el-icon><Upload /></el-icon>
        审定数回写TB（1481资产 + 2605负债）
      </el-button>
      <span class="tb-hint">
        资产审定合计: {{ fmtAmt(getAssetAuditedTotal()) }} |
        负债审定合计: {{ fmtAmt(getLiabilityAuditedTotal()) }}
      </span>
    </div>

    <!-- ═══ 审计说明 + 结论 ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header-row">
          <span>审计说明</span>
          <el-button size="small" text type="primary" @click="handleAiGenerate('audit-note')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="填写审计说明（执行程序、获取证据、分析结论等）"
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header-row">
          <span>审计结论</span>
          <div>
            <el-button size="small" text type="primary" @click="handleAiGenerate('conclusion')">
              <el-icon><MagicStick /></el-icon> AI辅助
            </el-button>
            <el-button size="small" text @click="handleReview('conclusion')">
              <el-icon><View /></el-icon> 复核
            </el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="填写审计结论"
        :disabled="isReadonly"
        @change="saveConclusion"
      />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="k6-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>资产区块(1481)</strong>：期末 = 期初 + 增加 − 减少 − 减值（借方/资产类）</li>
        <li><strong>负债区块(2605)</strong>：期末 = 期初 + 增加 − 减少（贷方/负债类）</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>三角勾稽：期末(公式) 应与 审定数 一致或差异合理</li>
        <li>减值列仅资产区块使用（CAS42孰低法）</li>
        <li>回写TB分别写入1481(资产)和2605(负债)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K6TabAdjudication.vue — K6-1 审定表（资产+负债双区块，45公式）
 *
 * Spec: .kiro/specs/k6-held-for-sale/ Task 4.2
 * Requirements: 2.1-2.8
 *
 * 功能：
 * - 双区块el-table：持有待售资产(1481借方) + 持有待售负债(2605贷方)
 * - 资产类期末=期初+增加-减少-减值；负债类期末=期初+增加-减少
 * - 审定数=未审+AJE+RJE
 * - 三角勾稽红色高亮（reconciliation.isBalanced → red text）
 * - TB回写按钮 → writebackTB(assetAudited, liabilityAudited)
 * - 底部审计说明+结论+复核按钮(inject openReviewDialog)
 * - Font 13px; formula columns dashed underline + cursor:help + tooltip
 * - AI按钮 section标题右侧
 * - 方法论上下文(琥珀色左边线+浅黄背景)
 */
import { ref, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, View, Upload, QuestionFilled } from '@element-plus/icons-vue'
import { useK6Adjudication, type K6AdjRow, type K6AdjSection } from '../../composables/useK6Adjudication'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjustedAsset: number; auditedAsset: number; unadjustedLiability: number; auditedLiability: number }
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const writebackTBFn = inject<(asset: number, liability: number) => Promise<void>>('k6WritebackTB', async () => {})
const allResponsesRef = computed(() => props.allResponses)

const {
  adjudicationSections,
  assetReconciliation,
  liabilityReconciliation,
  auditNote,
  auditConclusion,
  getAssetAuditedTotal,
  getLiabilityAuditedTotal,
  saveAll,
} = useK6Adjudication({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', field, value)
  },
})

const publishing = ref(false)

// ─── Display rows (data + subtotal appended) ─────────────────────────────────

function getDisplayRows(section: K6AdjSection): K6AdjRow[] {
  return [...section.rows, { ...section.subtotalRow }]
}

// ─── Row class styling ───────────────────────────────────────────────────────

function getRowClassName(row: K6AdjRow, sectionKey: string): string {
  if (row.rowKey === 'subtotal') return 'subtotal-row'
  // 三角勾稽不平时数据行红色
  if (sectionKey === 'asset' && !assetReconciliation.value.isBalanced) return 'reconciliation-error-row'
  if (sectionKey === 'liability' && !liabilityReconciliation.value.isBalanced) return 'reconciliation-error-row'
  return ''
}

// ─── 字段变化处理 ────────────────────────────────────────────────────────────

function onFieldChange(sectionKey: string, rowKey: string, field: string, value: number | undefined) {
  const v = value ?? 0
  const prefix = sectionKey === 'asset' ? 'K6-1-asset' : 'K6-1-liab'
  const itemId = `${prefix}-${rowKey}-${field}`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: String(v) })
  emit('save', itemId, { remark: String(v) })
}

function onRemarkChange(sectionKey: string, rowKey: string, value: string) {
  const prefix = sectionKey === 'asset' ? 'K6-1-asset' : 'K6-1-liab'
  const itemId = `${prefix}-${rowKey}-remark`
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: value })
  emit('save', itemId, { remark: value })
}

// ─── 保存审计说明+结论 ───────────────────────────────────────────────────────

function saveConclusion() {
  emit('save', 'K6-1-audit-note', { remark: auditNote.value })
  emit('save', 'K6-1-audit-conclusion', { remark: auditConclusion.value })
}

// ─── TB回写 ─────────────────────────────────────────────────────────────────

async function handleWritebackTB() {
  publishing.value = true
  try {
    const assetAudited = getAssetAuditedTotal()
    const liabilityAudited = getLiabilityAuditedTotal()
    // 实际回写 trial_balance + EventBus emit substantive:adjudicated
    await writebackTBFn(assetAudited, liabilityAudited)
    // 保存合计到 responses 供后续回写使用
    emit('save', 'K6-1-audited-asset', { remark: String(assetAudited) })
    emit('save', 'K6-1-audited-liability', { remark: String(liabilityAudited) })
    ElMessage.success(`审定数已回写TB：资产(1481)=${fmtAmt(assetAudited)}，负债(2605)=${fmtAmt(liabilityAudited)}`)
  } catch {
    ElMessage.error('TB回写失败')
  } finally {
    publishing.value = false
  }
}

// ─── AI / 复核 ──────────────────────────────────────────────────────────────

function handleAiGenerate(section: string) {
  console.log('[K6-1] AI generate:', section)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

// ─── 金额格式化 ─────────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k6-tab-adjudication { padding: 12px; font-size: 13px; }

/* ─── 方法论上下文 ─── */
.methodology-context {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 0 6px 6px 0;
  font-size: 13px;
  color: #92400e;
  line-height: 1.6;
}
.methodology-context p { margin: 0; }

/* ─── Section ─── */
.adj-section { margin-bottom: 20px; }
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.section-actions { display: flex; gap: 4px; }
.reconciliation-alert { margin-bottom: 8px; }

/* ─── 公式列样式 ─── */
.formula-header { cursor: help; }
.formula-icon { margin-left: 4px; font-size: 12px; color: #909399; }
.formula-value {
  border-bottom: 1px dashed #909399;
  cursor: help;
  padding-bottom: 1px;
}

/* ─── 表格样式 ─── */
:deep(.el-table) { font-size: 13px; }
:deep(.subtotal-row) { font-weight: 700; background-color: #fafafa !important; }
:deep(.reconciliation-error-row) { color: #f56c6c !important; }
:deep(.formula-col) { background-color: #fafff8; }
.adj-input { width: 100%; }
.adj-input :deep(.el-input__inner) { text-align: right; font-size: 13px; }
.rate-warning { color: #e6a23c; font-weight: 500; }

/* ─── TB回写 ─── */
.tb-writeback-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin: 16px 0;
  padding: 12px 16px;
  background: #f0f9ff;
  border: 1px solid #bae6fd;
  border-radius: 6px;
}
.tb-hint { font-size: 12px; color: #606266; }

/* ─── 审计说明/结论 ─── */
.audit-note-card { margin-bottom: 12px; }
.audit-note-card :deep(.el-card__header) { padding: 10px 16px; }
.card-header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 14px;
  font-weight: 500;
}

/* ─── 编制提示 ─── */
.k6-details-tip {
  margin-top: 12px;
  padding: 12px 16px;
  background: #fafafa;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  font-size: 13px;
  color: #606266;
}
.k6-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.k6-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
