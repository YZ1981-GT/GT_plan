<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/** F3TabRelatedParty — F3-6 应付票据关联方及交易检查表 */
import { inject, toRef, type Ref } from 'vue'
import {
  F3_PRICING_POLICY_OPTIONS,
  F3_RELATED_AGING_OPTIONS,
  F3_RELATED_NOTE_TYPES,
  F3_RELATED_RELATIONSHIPS,
  useF3RelatedParty,
  type F3RelatedPartyNoteRow,
} from '../composables/useF3RelatedParty'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3SheetAttachments from './F3SheetAttachments.vue'
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
  rows, summary, filledCount, auditNote, auditConclusion,
  addRow, removeRow, updateCell, rowClassName,
} = useF3RelatedParty({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

function fmt(value: number): string {
  return value === 0 ? '-' : value.toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
}

function aiContext() {
  return {
    partyCount: summary.value.count,
    openingBalance: summary.value.openingBalance,
    debitMovement: summary.value.debitMovement,
    creditMovement: summary.value.creditMovement,
    closingBalance: summary.value.closingBalance,
    subsequentPaymentAmount: summary.value.subsequentPaymentAmount,
    riskCount: summary.value.riskCount,
    riskRows: rows.value.filter((row) => row.riskFlags.length).map((row) => ({
      partyName: row.partyName,
      relationship: row.relationship,
      noteType: row.noteType,
      closingBalance: row.closingBalance,
      concentration: row.concentration,
      pricingPolicy: row.pricingPolicy,
      transactionReason: row.transactionReason,
      riskFlags: row.riskFlags,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'related-note', auditNote.value, aiContext(), 'AI 生成 · 关联方票据审计说明',
  )
  if (text) auditNote.value = text
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'related-conclusion', auditConclusion.value, aiContext(), 'AI 生成 · 关联方票据审计结论',
  )
  if (text) auditConclusion.value = text
}

function summaryMethod({ columns }: { columns: any[] }) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    if (column.property === 'openingBalance') return fmt(summary.value.openingBalance)
    if (column.property === 'debitMovement') return fmt(summary.value.debitMovement)
    if (column.property === 'creditMovement') return fmt(summary.value.creditMovement)
    if (column.property === 'closingBalance') return fmt(summary.value.closingBalance)
    if (column.property === 'subsequentPaymentAmount') {
      return fmt(summary.value.subsequentPaymentAmount)
    }
    return ''
  })
}
</script>

<template>
  <div class="f3-tab-related">
    <details class="guidance-details">
      <summary>📋 编制提示与勾稽逻辑</summary>
      <div class="guidance-content">
        <p>1. 将关联方清单、工商信息、征信报告及F3-2票据明细交叉核对，识别关联方开具、承兑、收款或实际承担的票据，关注未识别关联方。</p>
        <p>2. 按关联方和票据类别汇总期初余额、本期借方减少、本期贷方增加；期末余额自动按“期初＋贷方－借方”计算，并与F3-2及总账核对。</p>
        <p>3. 说明交易发生原因和款项性质，核查合同、发票、验收及资金流，判断是否具有真实商业背景，是否构成资金占用、变相融资或报表调节。</p>
        <p>4. 定价政策应与非关联第三方交易、市场价格或成本加成依据比较；复核期后付款和账龄，关注长期挂账及异常集中度。</p>
        <p>5. 核对关联方关系、交易发生额、期末余额及担保承兑安排是否在关联方附注中完整、准确披露。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：关注关联方应付票据的真实性、合理性、合法性及会计处理，考虑未识别关联方，并检查关联交易和余额披露是否正确。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">
          + 添加关联方
        </el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar
          :wp-id="wpId" :project-id="projectId" sheet="F3-6"
          :disabled="isReadonly" @imported="reloadWorkpaperData?.()"
        />
        <span class="chip-wrap">
          <GtIndexChip value="wp:F3-6" :context-project-id="projectId" />
        </span>
        <el-tag size="small" type="info">已填 {{ filledCount }} 项</el-tag>
        <el-tag v-if="summary.riskCount" size="small" type="warning">
          风险 {{ summary.riskCount }} 项
        </el-tag>
      </div>
    </div>

    <F3SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F3-6" label="关联方检查附件" />

    <div class="table-scroll-wrap">
      <el-table
        :data="rows" border size="small" class="related-table"
        :row-class-name="rowClassName" show-summary :summary-method="summaryMethod"
      >
        <el-table-column prop="seq" label="序号" width="50" fixed="left" align="center" />
        <el-table-column prop="partyName" label="关联方名称" width="155" fixed="left">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly" :model-value="row.partyName" size="small"
              @change="(value: string) => updateCell(row.rowId, 'partyName', value)"
            />
            <span v-else>{{ row.partyName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="relationship" label="关联关系" width="210">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly" :model-value="row.relationship" size="small"
              clearable filterable allow-create style="width:100%"
              @change="(value: string) => updateCell(row.rowId, 'relationship', value)"
            >
              <el-option
                v-for="item in F3_RELATED_RELATIONSHIPS"
                :key="item" :label="item" :value="item"
              />
            </el-select>
            <span v-else>{{ row.relationship }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="noteType" label="票据类别" width="135">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly" :model-value="row.noteType" size="small" clearable
              @change="(value: string) => updateCell(row.rowId, 'noteType', value)"
            >
              <el-option
                v-for="item in F3_RELATED_NOTE_TYPES"
                :key="item" :label="item" :value="item"
              />
            </el-select>
            <span v-else>{{ row.noteType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="openingBalance" label="期初余额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly" :model-value="row.openingBalance"
              size="small" style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'openingBalance', value ?? 0)"
            />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="debitMovement" label="借方发生" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly" :model-value="row.debitMovement"
              size="small" style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'debitMovement', value ?? 0)"
            />
            <span v-else>{{ fmt(row.debitMovement) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="creditMovement" label="贷方发生" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly" :model-value="row.creditMovement"
              size="small" style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'creditMovement', value ?? 0)"
            />
            <span v-else>{{ fmt(row.creditMovement) }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="closingBalance" label="期末余额" width="125"
          align="right" class-name="auto-calc-col"
        >
          <template #default="{ row }">
            <span class="formula-cell" title="期末余额 = 期初余额 + 贷方发生 - 借方发生">
              {{ fmt(row.closingBalance) }}
            </span>
            <small v-if="row.concentration" class="concentration">
              占比 {{ row.concentration.toFixed(2) }}%
            </small>
          </template>
        </el-table-column>
        <el-table-column prop="aging" label="账龄" width="105">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly" :model-value="row.aging" size="small" clearable
              @change="(value: string) => updateCell(row.rowId, 'aging', value)"
            >
              <el-option
                v-for="item in F3_RELATED_AGING_OPTIONS"
                :key="item" :label="item" :value="item"
              />
            </el-select>
            <span v-else>{{ row.aging }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="pricingPolicy" label="定价政策" width="145">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly" :model-value="row.pricingPolicy" size="small"
              clearable filterable allow-create style="width:100%"
              @change="(value: string) => updateCell(row.rowId, 'pricingPolicy', value)"
            >
              <el-option
                v-for="item in F3_PRICING_POLICY_OPTIONS"
                :key="item" :label="item" :value="item"
              />
            </el-select>
            <span v-else>{{ row.pricingPolicy }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="transactionReason" label="发生原因（款项性质）" width="210">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly" :model-value="row.transactionReason"
              type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
              @change="(value: string) => updateCell(row.rowId, 'transactionReason', value)"
            />
            <span v-else>{{ row.transactionReason }}</span>
          </template>
        </el-table-column>
        <el-table-column
          prop="subsequentPaymentAmount" label="期后付款金额" width="135" align="right"
        >
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly" :model-value="row.subsequentPaymentAmount" size="small" style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'subsequentPaymentAmount', value ?? 0)"
            />
            <span v-else>{{ fmt(row.subsequentPaymentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="indexNo" label="索引号" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly" :model-value="row.indexNo" size="small"
              placeholder="如 F3-2"
              @change="(value: string) => updateCell(row.rowId, 'indexNo', value)"
            />
            <span v-else>{{ row.indexNo }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" width="170">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly" :model-value="row.remark"
              type="textarea" :autosize="{ minRows: 1, maxRows: 3 }"
              @change="(value: string) => updateCell(row.rowId, 'remark', value)"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险提示" width="170">
          <template #default="{ row }">
            <div class="risk-flags">
              <el-tag
                v-for="flag in row.riskFlags" :key="flag"
                size="small" type="warning"
              >
                {{ flag }}
              </el-tag>
              <span v-if="!row.riskFlags.length">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button
              link type="danger" size="small" :disabled="isReadonly"
              @click="removeRow(row.rowId)"
            >
              删除
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-strip">
      <span>关联方 {{ summary.count }} 项</span>
      <span>期初 {{ fmt(summary.openingBalance) }}</span>
      <span>借方发生 {{ fmt(summary.debitMovement) }}</span>
      <span>贷方发生 {{ fmt(summary.creditMovement) }}</span>
      <span>期末 {{ fmt(summary.closingBalance) }}</span>
      <span>期后付款 {{ fmt(summary.subsequentPaymentAmount) }}</span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <div class="opinion-actions">
            <el-button
              size="small" type="primary" plain
              :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
              @click="generateAiNote"
            >
              🤖 AI 生成说明
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-6-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明关联方识别来源、余额勾稽、交易商业实质、定价政策、期后付款及披露核查情况..."
      />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <div class="opinion-actions">
            <el-button
              size="small" type="primary" plain
              :disabled="isReadonly || !aiAvailable" :loading="aiLoading"
              @click="generateAiConclusion"
            >
              🤖 AI 生成结论
            </el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-6-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion" type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly"
        placeholder="评价关联方票据真实性、商业实质、定价公允性、会计处理及披露是否恰当..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-related { padding: 12px; min-width: 0; font-size: var(--wp-font-size, 13px); }
.f3-tab-related :deep(.el-table), .f3-tab-related :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #4b2d77; border-radius: 4px; background: #f5f1fa; }
.guidance-details summary { cursor: pointer; color: #4b2d77; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar, .toolbar-left, .toolbar-right, .opinion-header, .opinion-actions { display: flex; align-items: center; }
.tab-toolbar, .opinion-header { justify-content: space-between; }
.tab-toolbar { margin-bottom: 8px; }
.toolbar-left, .toolbar-right, .opinion-actions { gap: 7px; }
.chip-wrap { display: inline-flex; align-items: center; }
.table-scroll-wrap { width: 100%; overflow-x: auto; border-radius: 4px; }
.related-table { width: 2180px; }
.formula-cell { display: block; border-bottom: 1px dashed #c0c4cc; background: #f5f7fa; text-align: right; }
.concentration { display: block; margin-top: 2px; color: #909399; text-align: right; }
:deep(.auto-calc-col) { background: #f5f7fa !important; }
:deep(.related-risk td) { background: #fdf6ec !important; }
:deep(.el-table__footer .cell) { font-weight: 700; }
.risk-flags { display: flex; flex-wrap: wrap; gap: 3px; }
.summary-strip { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px 18px; padding: 9px 12px; border-radius: 0 0 4px 4px; background: #f5f1fa; font-weight: 600; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.opinion-title { font-size: 14px; font-weight: 600; }
</style>
