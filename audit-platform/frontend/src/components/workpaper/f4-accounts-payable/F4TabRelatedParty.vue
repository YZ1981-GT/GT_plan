<script setup lang="ts">
/** F4TabRelatedParty — F4-6 应付账款关联方及交易检查表 */
import { inject, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  F4_RELATED_PRICING_OPTIONS,
  F4_RELATED_RELATIONSHIPS,
  useF4RelatedParty,
} from '../composables/useF4RelatedParty'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  rows,
  summary,
  filledCount,
  pendingSyncCount,
  agingOptions,
  auditNote,
  auditConclusion,
  loadRows,
  syncFromDetail,
  addRow,
  removeRow,
  updateCell,
  saveAuditNote,
  saveAuditConclusion,
  rowClassName,
} = useF4RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

async function onImported(): Promise<void> {
  if (reloadWorkpaperData) await reloadWorkpaperData()
  loadRows()
}

function fmtAmount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function fmtRate(value: number): string {
  return `${value.toFixed(2)}%`
}

function handleSync(): void {
  const added = syncFromDetail()
  if (added > 0) ElMessage.success(`已从F4-2同步 ${added} 个关联方`)
  else ElMessage.info('F4-2中已标识的关联方均已同步')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-6',
    totals: {
      openingBalance: summary.value.openingTotal,
      currentDebit: summary.value.debitTotal,
      currentCredit: summary.value.creditTotal,
      closingBalance: summary.value.closingTotal,
      postPaymentAmount: summary.value.postPaymentTotal,
      detailClosingBalance: summary.value.sourceClosingTotal,
      reconciliationDifference: summary.value.reconciliationDifference,
    },
    count: summary.value.count,
    highRiskCount: summary.value.highRiskCount,
    missingPricingCount: summary.value.missingPricingCount,
    rows: rows.value
      .filter((row) => row.partyName || row.closingBalance)
      .map((row) => ({
        partyName: row.partyName,
        relationship: row.relationship,
        openingBalance: row.openingBalance,
        currentDebit: row.currentDebit,
        currentCredit: row.currentCredit,
        closingBalance: row.closingBalance,
        aging: row.aging,
        pricingPolicy: row.pricingPolicy,
        transactionNature: row.transactionNature,
        postPaymentAmount: row.postPaymentAmount,
        indexNo: row.indexNo,
        reconciliationDifference: row.reconciliationDifference,
        concentration: row.concentration,
        riskFlags: row.riskFlags,
      })),
  }
}

async function generateAuditNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'related-party-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-6审计说明',
  )
  if (generated) saveAuditNote(generated)
}

async function generateAuditConclusion(): Promise<void> {
  const generated = await generateAndConfirm(
    'related-party-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-6审计结论',
  )
  if (generated) saveAuditConclusion(generated)
}
</script>

<template>
  <div class="f4-tab-related-party">
    <details class="guidance-details">
      <summary>📋 编制思路与联动逻辑</summary>
      <div class="guidance-content">
        <p>1. 先取得并核对完整关联方清单，关注F4-2中关联方标识为空或错误造成的未识别关联方风险；本表仅自动同步F4-2中已标识为关联方的实际债权人。</p>
        <p>2. 逐项核对期初余额、本期借方和本期贷方，期末余额自动按“期初余额＋本期贷方－本期借方”计算，并与F4-2审定余额交叉核对。</p>
        <p>3. 结合合同、订单、发票、验收及付款资料检查交易性质和业务合理性；结合第三方价格、成本加成或协议条款评价定价政策。</p>
        <p>4. 分析账龄及期后付款，关注长期挂账、借方余额、期后付款超过期末余额、余额集中及异常资金往来。</p>
        <p>5. 最后核对关联方交易及余额是否在财务报表附注中完整、准确披露；索引号应指向所取得的合同、定价及付款证据。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：关注关联方应付账款的真实性、合理性、合法性及会计处理是否正确，考虑是否存在未识别关联方，并检查关联交易和余额披露是否正确。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSync">
          ⇄ 从F4-2同步
          <el-badge v-if="pendingSyncCount" :value="pendingSyncCount" class="sync-badge" />
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 手工添加</el-button>
      </div>
      <div class="toolbar-right">
        <F4ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          sheet="F4-6"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        <el-tag size="small" type="info">已填 {{ filledCount }} 项</el-tag>
        <el-tag v-if="summary.highRiskCount" size="small" type="danger">
          高风险 {{ summary.highRiskCount }} 项
        </el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-6-related-party')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-6" label="关联方检查附件" />

    <div class="table-scroll-wrap">
      <el-table
        :data="rows"
        border
        size="small"
        class="related-table"
        max-height="620"
        :row-class-name="rowClassName"
      >
        <el-table-column type="index" label="序号" width="58" fixed="left" />
        <el-table-column label="关联方名称" width="175" fixed="left">
          <template #default="{ row }">
            <el-tooltip v-if="row.linked" content="关联F4-2债权人">
              <span class="linked-value">🔗 {{ row.partyName }}</span>
            </el-tooltip>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.partyName"
              size="small"
              @change="(value: string) => updateCell(row.rowId, 'partyName', value)"
            />
            <span v-else>{{ row.partyName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联关系" width="190">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.relationship"
              size="small"
              filterable
              allow-create
              clearable
              placeholder="选择或据实填写"
              @change="(value: string) => updateCell(row.rowId, 'relationship', value)"
            >
              <el-option v-for="option in F4_RELATED_RELATIONSHIPS" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.relationship }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.openingBalance) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.openingBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'openingBalance', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期借方" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.currentDebit) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.currentDebit"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'currentDebit', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.currentDebit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期贷方" width="130" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.currentCredit) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.currentCredit"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'currentCredit', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.currentCredit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="135" align="right" class-name="formula-col">
          <template #default="{ row }">
            <el-tooltip
              :content="`期初＋贷方－借方；占关联方余额 ${fmtRate(row.concentration)}`"
              placement="top"
            >
              <span class="formula-value">{{ fmtAmount(row.closingBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="155">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ row.aging }}</span>
            <el-select
              v-else-if="!isReadonly"
              :model-value="row.aging"
              size="small"
              filterable
              allow-create
              clearable
              @change="(value: string) => updateCell(row.rowId, 'aging', value)"
            >
              <el-option v-for="option in agingOptions" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.aging }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" width="155">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.pricingPolicy"
              size="small"
              filterable
              allow-create
              clearable
              placeholder="定价依据"
              @change="(value: string) => updateCell(row.rowId, 'pricingPolicy', value)"
            >
              <el-option v-for="option in F4_RELATED_PRICING_OPTIONS" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.pricingPolicy }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发生原因（款项性质）" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.transactionNature"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="交易背景、款项性质及发生原因"
              @change="(value: string) => updateCell(row.rowId, 'transactionNature', value)"
            />
            <span v-else>{{ row.transactionNature }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后付款金额" width="140" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.postPaymentAmount) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.postPaymentAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'postPaymentAmount', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.postPaymentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="125">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexNo"
              size="small"
              placeholder="证据索引"
              @change="(value: string) => updateCell(row.rowId, 'indexNo', value)"
            />
            <span v-else>{{ row.indexNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="170">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              @change="(value: string) => updateCell(row.rowId, 'remark', value)"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险提示" width="180">
          <template #default="{ row }">
            <div class="risk-flags">
              <el-tag
                v-for="flag in row.riskFlags"
                :key="flag"
                size="small"
                :type="row.riskLevel === 'danger' ? 'danger' : 'warning'"
              >{{ flag }}</el-tag>
              <span v-if="!row.riskFlags.length">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-strip">
      <span>期初 {{ fmtAmount(summary.openingTotal) }}</span>
      <span>借方 {{ fmtAmount(summary.debitTotal) }}</span>
      <span>贷方 {{ fmtAmount(summary.creditTotal) }}</span>
      <span>期末 {{ fmtAmount(summary.closingTotal) }}</span>
      <span>期后付款 {{ fmtAmount(summary.postPaymentTotal) }}</span>
      <span :class="{ danger: Math.abs(summary.reconciliationDifference) >= 0.005 }">
        与F4-2审定数差异 {{ fmtAmount(summary.reconciliationDifference) }}
      </span>
    </div>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">1、审计说明</div>
            <div class="card-hint">说明关联方识别、余额勾稽、交易性质、定价依据、账龄、期后付款及披露核对结果。</div>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAuditNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-6-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="记录关联方清单核对、交易及余额检查、定价测试、期后付款和披露检查过程及发现。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">2、审计结论</div>
            <div class="card-hint">评价关联方识别是否完整、交易是否真实公允、余额是否准确以及披露是否充分。</div>
          </div>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAuditConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价关联方应付账款及交易的真实性、合理性、合法性、会计处理和披露。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-related-party { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #315a8a;
  border-radius: 4px;
  background: #eef4fa;
}
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.audit-objective { margin-bottom: 12px; }
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; flex-wrap: wrap; gap: 8px; }
.sync-badge { margin-left: 4px; }
.table-scroll-wrap { width: 100%; overflow-x: auto; }
.related-table { min-width: 1950px; }
.related-table :deep(.el-input-number), .related-table :deep(.el-select) { width: 100%; }
.linked-value { color: #7b4ba3; font-weight: 600; }
.formula-value { border-bottom: 1px dashed #9ca3af; cursor: help; font-weight: 600; }
:deep(.formula-col) { background: #f4f7fa !important; }
:deep(.related-risk-warning td) { background: #fdf6ec !important; }
:deep(.related-risk-danger td) { background: #fef0f0 !important; }
.risk-flags { display: flex; flex-wrap: wrap; gap: 3px; }
.summary-strip {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px 24px;
  padding: 9px 12px;
  border: 1px solid #dcdfe6;
  border-top: none;
  background: #f3f5f8;
  font-weight: 700;
}
.summary-strip .danger { color: #d03050; }
.text-card { margin-top: 16px; border-radius: 8px; }
.text-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.card-title { color: #303133; font-weight: 600; }
.card-hint { margin-top: 3px; color: #909399; font-size: 12px; }
.card-actions { display: flex; gap: 6px; }
</style>
