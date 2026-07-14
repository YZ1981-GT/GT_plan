<script setup lang="ts">
/** E1-6 银行存款余额调节表：账户级四类逐笔未达账项。 */
import { ref, inject, toRef, onMounted, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  OUTSTANDING_ITEM_CATEGORIES,
  useE1Reconciliation,
  type OutstandingItem,
  type OutstandingItemCategory,
} from '../composables/useE1Reconciliation'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
}

const {
  rows,
  isLoading,
  hasDiff,
  isMissingReason,
  categoryTotal,
  getRiskAlerts,
  getOutstandingItemRiskTags,
  addRow,
  removeRow,
  updateCell,
  addOutstandingItem,
  removeOutstandingItem,
  updateOutstandingItem,
} = useE1Reconciliation(options)

const activeItemTabs = ref<Record<string, OutstandingItemCategory>>({})
function setActiveTab(rowId: string, value: string | number): void {
  activeItemTabs.value[rowId] = value as OutstandingItemCategory
}

const NOTE_KEY = 'E1-recon-audit-note'
const CONCLUSION_KEY = 'E1-recon-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId'))

onMounted(() => {
  auditNote.value = String(props.allResponses.get(NOTE_KEY)?.remark || '')
  auditConclusion.value = String(props.allResponses.get(CONCLUSION_KEY)?.remark || '')
})

function saveText(itemId: string, value: string): void {
  if (props.isReadonly) return
  const item = { item_id: itemId, conclusion: null, remark: value }
  props.allResponses.set(itemId, item)
  void props.saveImmediate([item])
}
function saveAuditNote(value: string): void {
  auditNote.value = value
  saveText(NOTE_KEY, value)
}
function saveAuditConclusion(value: string): void {
  auditConclusion.value = value
  saveText(CONCLUSION_KEY, value)
}

function buildAiContext(): Record<string, unknown> {
  return {
    formula: {
      bookSide: '企业账面余额 + 银行已收企业未收 - 银行已付企业未付',
      statementSide: '银行对账单余额 + 企业已收银行未收 - 企业已付银行未付',
    },
    largeAmountThreshold: 100000,
    accounts: rows.value.map(row => ({
      bankName: row.bankName,
      accountNo: row.accountNo,
      bookBalance: row.bookBalance,
      statementBalance: row.statementBalance,
      reconciledBook: row.reconciledBook,
      reconciledStatement: row.reconciledStatement,
      difference: row.diff,
      differenceReason: row.diffReason,
      risks: getRiskAlerts(row),
      outstandingItems: Object.fromEntries(
        OUTSTANDING_ITEM_CATEGORIES.map(category => [category.label, row[category.key]]),
      ),
    })),
  }
}

async function handleAiGenerate(target: 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  const isNote = target === 'note'
  const content = await generateText({
    section: isNote ? 'reconciliation-audit-note' : 'reconciliation-audit-conclusion',
    prompt: isNote
      ? '请根据各银行账户四类未达账项逐笔记录、调节差异和风险提示，生成专业审计说明，重点说明长期未达、大额及报表日后未入账事项的核查情况。'
      : '请根据银行存款余额调节结果生成简洁审计结论，明确双方调节后余额是否一致、未达账项是否合理、是否需要审计调整。',
    context: buildAiContext(),
    existingContent: isNote ? auditNote.value : auditConclusion.value,
  })
  if (!content) return
  if (isNote) saveAuditNote(content)
  else saveAuditConclusion(content)
  ElMessage.success(isNote ? 'AI 审计说明已生成' : 'AI 审计结论已生成')
}

function updateItem(
  rowId: string,
  category: OutstandingItemCategory,
  itemId: string,
  field: keyof OutstandingItem,
  value: unknown,
): void {
  updateOutstandingItem(rowId, category, itemId, field, value)
}
</script>

<template>
  <div class="e1-tab-reconciliation">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 每个银行账户逐笔登记四类未达账项，并检查期后入账凭证、银行对账单及记账凭证。</p>
        <p>2. 企业账面侧＝账面余额＋银行已收企业未收－银行已付企业未付。</p>
        <p>3. 银行对账单侧＝对账单余额＋企业已收银行未收－企业已付银行未付。</p>
        <p>4. 调节后双方余额应一致；重点追查超过90天、大额及报表日后仍未入账项目，并与 E1-3、函证回函核对。</p>
      </div>
    </details>

    <div class="methodology-context">
      <strong>源模板方法：</strong>未达账项应逐笔列示而非仅填汇总金额。旧版四个汇总金额载入时会自动迁移为占位明细，请补齐日期、凭证号、对方科目及期后入账证据。
    </div>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：验证银行存款账面余额与银行对账单余额的一致性，识别截止错报、长期挂账及异常调节事项。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <div class="tab-toolbar">
          <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">+ 新增银行账户</el-button>
          <div class="toolbar-right">
            <span class="chip-wrap"><GtIndexChip value="wp:E1-3" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 个账户</el-tag>
          </div>
        </div>

        <div class="recon-list">
          <div
            v-for="row in rows"
            :key="row.id"
            class="recon-card"
            :class="{ 'recon-card-error': hasDiff(row) }"
          >
            <div class="recon-header">
              <div class="recon-bank-info">
                <el-input
                  :model-value="row.bankName"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="开户银行"
                  @change="(value: string) => updateCell(row.id, 'bankName', value)"
                />
                <el-input
                  :model-value="row.accountNo"
                  :disabled="isReadonly"
                  size="small"
                  placeholder="银行账号"
                  @change="(value: string) => updateCell(row.id, 'accountNo', value)"
                />
              </div>
              <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeRow(row.id)">删除账户</el-button>
            </div>

            <div class="recon-body">
              <div class="recon-side">
                <div class="side-title">企业账面侧</div>
                <div class="side-row">
                  <span class="side-label">企业账面余额</span>
                  <el-input-number
                    :model-value="row.bookBalance"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(value: number | undefined) => updateCell(row.id, 'bookBalance', value ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">+ 银行已收企业未收</span>
                  <span class="formula-value" title="由“银行已收企业未收”逐笔金额自动汇总">{{ displayPrefs.fmtAmount(row.companyReceived) }}</span>
                </div>
                <div class="side-row">
                  <span class="side-label">- 银行已付企业未付</span>
                  <span class="formula-value" title="由“银行已付企业未付”逐笔金额自动汇总">{{ displayPrefs.fmtAmount(row.companyPaid) }}</span>
                </div>
                <div class="side-row side-result">
                  <span class="side-label">= 调节后企业余额</span>
                  <span class="side-computed" title="账面余额 + 银行已收企业未收 - 银行已付企业未付">{{ displayPrefs.fmtAmount(row.reconciledBook) }}</span>
                </div>
              </div>

              <div class="recon-side">
                <div class="side-title">银行对账单侧</div>
                <div class="side-row">
                  <span class="side-label">银行对账单余额</span>
                  <el-input-number
                    :model-value="row.statementBalance"
                    :disabled="isReadonly"
                    :controls="false"
                    size="small"
                    @change="(value: number | undefined) => updateCell(row.id, 'statementBalance', value ?? 0)"
                  />
                </div>
                <div class="side-row">
                  <span class="side-label">+ 企业已收银行未收</span>
                  <span class="formula-value" title="由“企业已收银行未收”逐笔金额自动汇总">{{ displayPrefs.fmtAmount(row.bankReceived) }}</span>
                </div>
                <div class="side-row">
                  <span class="side-label">- 企业已付银行未付</span>
                  <span class="formula-value" title="由“企业已付银行未付”逐笔金额自动汇总">{{ displayPrefs.fmtAmount(row.bankPaid) }}</span>
                </div>
                <div class="side-row side-result">
                  <span class="side-label">= 调节后银行余额</span>
                  <span class="side-computed" title="对账单余额 + 企业已收银行未收 - 企业已付银行未付">{{ displayPrefs.fmtAmount(row.reconciledStatement) }}</span>
                </div>
              </div>
            </div>

            <div class="recon-diff" :class="{ 'diff-error': hasDiff(row) }">
              <span class="diff-label">调节差异：</span>
              <span class="diff-value">{{ displayPrefs.fmtAmount(row.diff) }}</span>
              <span v-if="!hasDiff(row)" class="diff-ok">✓ 一致</span>
              <span v-else class="diff-warn">⚠ 存在差异</span>
            </div>

            <div v-if="getRiskAlerts(row).length" class="risk-alerts">
              <el-alert title="未达账项风险提示" type="warning" :closable="false" show-icon>
                <ul><li v-for="alert in getRiskAlerts(row)" :key="alert">{{ alert }}</li></ul>
              </el-alert>
            </div>

            <div class="outstanding-section">
              <div class="section-heading">
                <span>四类未达账项明细</span>
                <small>金额汇总自动驱动上方两侧调节公式</small>
              </div>
              <el-tabs
                :model-value="activeItemTabs[row.id] || OUTSTANDING_ITEM_CATEGORIES[0].key"
                type="border-card"
                @update:model-value="value => setActiveTab(row.id, value)"
              >
                <el-tab-pane
                  v-for="category in OUTSTANDING_ITEM_CATEGORIES"
                  :key="category.key"
                  :name="category.key"
                >
                  <template #label>
                    <span>{{ category.label }}</span>
                    <el-badge :value="row[category.key].length" :hidden="!row[category.key].length" class="tab-badge" />
                  </template>
                  <div class="item-toolbar">
                    <span>{{ category.side === 'book' ? '企业账面侧' : '银行对账单侧' }} {{ category.operator }} 项合计：<b>{{ displayPrefs.fmtAmount(categoryTotal(row, category.key)) }}</b></span>
                    <el-button v-if="!isReadonly" type="primary" plain size="small" @click="addOutstandingItem(row.id, category.key)">+ 新增明细</el-button>
                  </div>
                  <el-table :data="row[category.key]" border empty-text="暂无明细，请逐笔新增" class="outstanding-table">
                    <el-table-column label="银行日期" width="140">
                      <template #default="{ row: item }">
                        <el-date-picker :model-value="item.bankDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="银行日期" @change="value => updateItem(row.id, category.key, item.id, 'bankDate', value)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="金额（元）" width="145" align="right">
                      <template #default="{ row: item }">
                        <el-input-number :model-value="item.amount" :disabled="isReadonly" :controls="false" @change="value => updateItem(row.id, category.key, item.id, 'amount', value ?? 0)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="报表日后处理" width="120" align="center">
                      <template #default="{ row: item }">
                        <el-switch :model-value="item.postedAfterPeriod" :disabled="isReadonly" inline-prompt active-text="是" inactive-text="否" @change="value => updateItem(row.id, category.key, item.id, 'postedAfterPeriod', value)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="入账日期" width="140">
                      <template #default="{ row: item }">
                        <el-date-picker :model-value="item.postingDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="入账日期" @change="value => updateItem(row.id, category.key, item.id, 'postingDate', value)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="凭证号" width="130">
                      <template #default="{ row: item }"><el-input :model-value="item.voucherNo" :disabled="isReadonly" @change="value => updateItem(row.id, category.key, item.id, 'voucherNo', value)" /></template>
                    </el-table-column>
                    <el-table-column label="摘要" min-width="180">
                      <template #default="{ row: item }"><el-input :model-value="item.description" :disabled="isReadonly" @change="value => updateItem(row.id, category.key, item.id, 'description', value)" /></template>
                    </el-table-column>
                    <el-table-column label="对方科目" width="150">
                      <template #default="{ row: item }"><el-input :model-value="item.counterAccount" :disabled="isReadonly" @change="value => updateItem(row.id, category.key, item.id, 'counterAccount', value)" /></template>
                    </el-table-column>
                    <el-table-column label="对账单日期" width="140">
                      <template #default="{ row: item }">
                        <el-date-picker :model-value="item.statementDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="对账单日期" @change="value => updateItem(row.id, category.key, item.id, 'statementDate', value)" />
                      </template>
                    </el-table-column>
                    <el-table-column label="会计处理正确" width="130">
                      <template #default="{ row: item }">
                        <el-select :model-value="item.accountingCorrect" :disabled="isReadonly" clearable placeholder="待评价" @change="value => updateItem(row.id, category.key, item.id, 'accountingCorrect', value)">
                          <el-option label="是" :value="true" /><el-option label="否" :value="false" />
                        </el-select>
                      </template>
                    </el-table-column>
                    <el-table-column label="需要调整" width="120">
                      <template #default="{ row: item }">
                        <el-select :model-value="item.adjustmentRequired" :disabled="isReadonly" clearable placeholder="待评价" @change="value => updateItem(row.id, category.key, item.id, 'adjustmentRequired', value)">
                          <el-option label="是" :value="true" /><el-option label="否" :value="false" />
                        </el-select>
                      </template>
                    </el-table-column>
                    <el-table-column label="风险" min-width="165">
                      <template #default="{ row: item }">
                        <div class="risk-tags">
                          <el-tag v-for="risk in getOutstandingItemRiskTags(item)" :key="risk" type="warning" size="small">{{ risk }}</el-tag>
                          <span v-if="!getOutstandingItemRiskTags(item).length" class="muted">—</span>
                        </div>
                      </template>
                    </el-table-column>
                    <el-table-column label="备注" min-width="180">
                      <template #default="{ row: item }"><el-input :model-value="item.note" :disabled="isReadonly" @change="value => updateItem(row.id, category.key, item.id, 'note', value)" /></template>
                    </el-table-column>
                    <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
                      <template #default="{ row: item }"><el-button type="danger" text size="small" @click="removeOutstandingItem(row.id, category.key, item.id)">删除</el-button></template>
                    </el-table-column>
                  </el-table>
                </el-tab-pane>
              </el-tabs>
            </div>

            <div v-if="hasDiff(row)" class="recon-reason">
              <label class="reason-label">差异原因 <span class="required-mark">*</span></label>
              <el-input
                type="textarea"
                :model-value="row.diffReason"
                :disabled="isReadonly"
                :autosize="{ minRows: 2, maxRows: 4 }"
                :class="{ 'missing-reason': isMissingReason(row) }"
                placeholder="请填写差异原因及拟采取的审计程序"
                @change="(value: string) => updateCell(row.id, 'diffReason', value)"
              />
              <span v-if="isMissingReason(row)" class="reason-hint">差异不为零时必须填写原因</span>
            </div>
          </div>
        </div>

        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
              <el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('reconciliation-audit-note')" @click="handleAiGenerate('note')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
            </div>
          </template>
          <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="填写未达账项核查过程、期后入账证据及异常处理..." @change="saveAuditNote" />
        </el-card>

        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
              <el-button type="primary" plain size="small" :disabled="isReadonly" :loading="isGenerating('reconciliation-audit-conclusion')" @click="handleAiGenerate('conclusion')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
            </div>
          </template>
          <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="填写调节结果及是否需要审计调整..." @change="saveAuditConclusion" />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-reconciliation { padding: 12px 0; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.methodology-context { margin-bottom: 12px; padding: 9px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; color: #7a4d00; line-height: 1.55; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar, .recon-header, .card-header, .section-heading, .item-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.tab-toolbar { margin-bottom: 12px; flex-wrap: wrap; }
.toolbar-right, .recon-bank-info, .risk-tags { display: flex; gap: 6px; align-items: center; }
.recon-bank-info :deep(.el-input) { width: 210px; }
.chip-wrap { display: inline-flex; align-items: center; }
.recon-list { display: flex; flex-direction: column; gap: 16px; }
.recon-card { border: 1px solid #ebeef5; border-radius: 8px; padding: 14px; background: #fff; }
.recon-card-error { border-color: #f56c6c; }
.recon-header { margin-bottom: 12px; }
.recon-body { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 12px; }
.recon-side { border: 1px solid #ebeef5; border-radius: 6px; padding: 12px; background: #fafafa; }
.side-title { font-weight: 700; color: #303133; margin-bottom: 8px; padding-bottom: 6px; border-bottom: 1px solid #ebeef5; }
.side-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; min-height: 34px; }
.side-label { color: #606266; min-width: 165px; }
.side-result { padding-top: 8px; border-top: 1px solid #dcdfe6; margin-top: 4px; }
.side-computed { font-weight: 700; color: #303133; font-size: 14px; border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 600; border-bottom: 1px dashed #409eff; cursor: help; }
.recon-diff { display: flex; align-items: center; gap: 8px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; }
.recon-diff.diff-error { background: #fef0f0; }
.diff-label { font-weight: 600; color: #303133; }
.diff-value { font-weight: 700; font-size: 14px; }
.diff-ok { color: #67c23a; font-weight: 600; }
.diff-warn, .required-mark, .reason-hint { color: #f56c6c; font-weight: 600; }
.risk-alerts { margin-top: 10px; }
.risk-alerts ul { margin: 2px 0; padding-left: 18px; line-height: 1.6; }
.outstanding-section { margin-top: 12px; }
.section-heading { margin-bottom: 8px; font-weight: 600; }
.section-heading small { color: #909399; font-weight: 400; }
.item-toolbar { margin-bottom: 8px; color: #606266; }
.tab-badge { margin-left: 8px; }
.outstanding-table { width: 100%; font-size: var(--wp-font-size, 13px); }
.outstanding-table :deep(.el-input-number), .outstanding-table :deep(.el-date-editor), .outstanding-table :deep(.el-select) { width: 100%; }
.risk-tags { flex-wrap: wrap; }
.muted { color: #c0c4cc; }
.recon-reason { margin-top: 12px; }
.reason-label { font-weight: 600; color: #303133; display: block; margin-bottom: 4px; }
.reason-hint { font-size: 12px; margin-top: 4px; display: block; }
:deep(.missing-reason .el-textarea__inner) { border-color: #f56c6c !important; }
.audit-note-card { margin-top: 16px; }
.card-header { font-weight: 500; }
@media (max-width: 980px) {
  .recon-body { grid-template-columns: 1fr; }
  .recon-bank-info { flex-wrap: wrap; }
}
</style>
