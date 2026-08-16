<!--
  G3TabOverdueCheck.vue — G3-5 长期未收回款项检查表

  对齐致同 Excel：期初/借贷/期末/账龄/未收回原因/是否无法收回/处理计划/审定/期后收款
  保留股利专用：宣告日、约定付款日、逾期天数（勾稽 G3-1 账龄≥365天）
-->
<template>
  <div class="g3-overdue-check" data-testid="g3-overdue-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表检查长期未收回应收股利：按被投资方列示期初/借贷发生/期末，说明未收回原因与处理计划。</p>
        <p>2. 期末余额 = 期初 + 本期借方 − 本期贷方（灰底自动）；审定余额可「同步期末」。</p>
        <p>3. 约定付款日驱动逾期天数；逾期≥365 天金额汇总至 G3-1「一年以上」账龄条。</p>
        <p>4. 账龄支持 3年段 / 5年段 / 自定义；期后收款用于验证可收回性（可索引 G3-4）。</p>
        <p>5. 可「从 G3-2 导入逾期」：按被投资方合并期末应收&gt;0 且已逾期的明细。</p>
        <p class="cas-basis">CAS：评估可收回性并考虑减值（CAS 22 预期信用损失）。结论可按 A/B/C 口径表述。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：核实长期未收回应收股利的存在与列报；评价未收回原因、处理计划及坏账/减值是否恰当；确保披露完整准确。"
    />

    <div class="section-head tab-toolbar">
      <div class="toolbar-left">
        <h3 class="sheet-title">G3-5 长期未收回款项检查表</h3>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="overdue.addRow()">＋ 新增</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onImportFromDetail">从 G3-2 导入逾期</el-button>
        <span class="muted">账龄口径</span>
        <el-select
          :model-value="agingPresetModel"
          size="small"
          style="width: 120px"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <G3ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G3-5"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right head-actions">
        <span class="chip-wrap"><GtIndexChip value="wp:G3-2" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G3-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G3-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ overdue.dataRows.value.length }} 行</el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('G3-5-overdue')">💬复核</el-button>
      </div>
    </div>

    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" destroy-on-close>
      <p class="muted">每行一个段名，至少 2 段、最多 10 段。</p>
      <el-input v-model="customInput" type="textarea" :rows="8" placeholder="1年以内&#10;1-2年&#10;2-3年&#10;3年以上" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>

    <el-table
      :data="overdue.displayRows.value"
      border
      size="small"
      max-height="520"
      :row-class-name="rowClassName"
      class="overdue-table"
    >
      <el-table-column label="被投资方" width="140" fixed>
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-label">{{ row.investeeName }}</span>
          <el-input
            v-else
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="期初余额" width="110" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.openingBalance) }}</span>
          <WpAmountInput
            v-else
            :model-value="row.openingBalance"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => overdue.updateRow(row.id, { openingBalance: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="本期借方发生额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.periodDebit) }}</span>
          <WpAmountInput
            v-else
            :model-value="row.periodDebit"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => overdue.updateRow(row.id, { periodDebit: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="本期贷方发生额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.periodCredit) }}</span>
          <WpAmountInput
            v-else
            :model-value="row.periodCredit"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => overdue.updateRow(row.id, { periodCredit: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="期末余额" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span class="formula-cell" title="期末 = 期初 + 借方 − 贷方">{{ fmtNum(row.closingBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="账龄" width="120">
        <template #default="{ row }">
          <el-select
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.aging"
            size="small"
            :disabled="isReadonly"
            filterable
            allow-create
            clearable
            placeholder="选择账龄"
            @change="(v: string) => overdue.updateRow(row.id, { aging: v ?? '' })"
          >
            <el-option v-for="opt in overdue.agingOptions.value" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="经营业务说明" width="140">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.businessDesc"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { businessDesc: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="未收回或未结转的原因" width="160">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.unrecoveredReason"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { unrecoveredReason: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="是否无法收回" width="110">
        <template #default="{ row }">
          <el-select
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.isUncollectible"
            size="small"
            :disabled="isReadonly"
            clearable
            @change="(v: string) => overdue.updateRow(row.id, { isUncollectible: (v ?? '') as any })"
          >
            <el-option
              v-for="opt in overdue.UNCOLLECTIBLE_OPTIONS"
              :key="String(opt.value)"
              :value="opt.value"
              :label="opt.label"
            />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="处理计划" width="140">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.actionPlan"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { actionPlan: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="审定余额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.auditedBalance) }}</span>
          <div v-else class="audited-cell">
            <WpAmountInput
              :model-value="row.auditedBalance"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => overdue.updateRow(row.id, { auditedBalance: v ?? 0 })"
            />
            <el-button
              v-if="!isReadonly"
              link
              type="primary"
              size="small"
              title="将审定余额同步为期末余额"
              @click="overdue.syncAuditedFromClosing(row.id)"
            >同步</el-button>
          </div>
        </template>
      </el-table-column>

      <el-table-column label="期后收款金额" width="120" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.postPeriodCollection) }}</span>
          <WpAmountInput
            v-else
            :model-value="row.postPeriodCollection"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: number) => overdue.updateRow(row.id, { postPeriodCollection: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="宣告日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.declarationDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => overdue.updateRow(row.id, { declarationDate: v ?? '' })"
          />
        </template>
      </el-table-column>

      <el-table-column label="约定付款日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.agreedPaymentDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width:100%"
            @update:model-value="(v: string) => overdue.updateRow(row.id, { agreedPaymentDate: v ?? '' })"
          />
        </template>
      </el-table-column>

      <el-table-column label="逾期天数" width="90" align="right" class-name="auto-calc-col">
        <template #default="{ row }">
          <span
            v-if="!overdue.isMetaRow(row)"
            class="formula-cell"
            title="逾期天数 = MAX(0, 当前日期 − 约定付款日)；≥365 天计入 G3-1 一年以上"
          >{{ row.overdueDays }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateRow(row.id, { remark: v })"
          />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon
            v-if="!overdue.isMetaRow(row)"
            class="delete-icon"
            @click="overdue.removeRow(row.id)"
          ><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <div class="summary-bar">
      <span class="summary-label">汇总</span>
      <span class="summary-item">逾期 {{ overdue.summary.value.overdueCount }} 笔</span>
      <span class="summary-item">逾期金额 {{ fmtNum(overdue.summary.value.overdueTotal) }}</span>
      <span class="summary-item">长期/一年以上 {{ overdue.summary.value.longTermCount }} 笔</span>
      <span class="summary-item">审定合计 {{ fmtNum(overdue.summary.value.auditedBalance) }}</span>
      <span class="summary-item">期后收款 {{ fmtNum(overdue.summary.value.postPeriodCollection) }}</span>
      <span class="summary-item">无法收回/部分 {{ overdue.summary.value.uncollectibleCount }} 笔</span>
      <span class="summary-item">高风险 {{ overdue.summary.value.highRiskCount }} 笔</span>
    </div>

    <G3AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="overdue-note"
      conclusion-ai-section="overdue-evaluation"
      :related-context="{
        检查行数: overdue.dataRows.value.length,
        逾期笔数: overdue.summary.value.overdueCount,
        逾期总金额: overdue.summary.value.overdueTotal,
        长期挂账笔数: overdue.summary.value.longTermCount,
        审定合计: overdue.summary.value.auditedBalance,
        期后收款合计: overdue.summary.value.postPeriodCollection,
        无法收回笔数: overdue.summary.value.uncollectibleCount,
        高风险笔数: overdue.summary.value.highRiskCount,
        账龄口径: overdue.agingPreset.value,
      }"
      note-placeholder="填写审计说明：（1）抽样/全查范围；（2）长期未收回原因与处理计划；（3）期后收款验证（可索引 G3-4）；（4）减值/坏账衔接与拟调整事项。"
      note-hint="覆盖逾期天数、账龄、可收回性及与 G3-1/G3-2/G3-4 勾稽。"
      conclusion-hint="按参考结论 A（未见异常）/ B（除…外未见异常）/ C（证据不足无法表示意见）口径表述。"
      conclusion-placeholder="参考：A. 经检查，长期未收回应收股利未见异常。B. 除……外，未见异常。C. 因……证据不足，无法对可收回性表示意见。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, watch, toRef, computed, inject, onMounted } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import G3ImportExportDropdown from './G3ImportExportDropdown.vue'
import G3AuditTextCards from './G3AuditTextCards.vue'
import {
  useG3OverdueCheck,
  getOverdueRiskClass,
  type OverdueDividendRow,
} from '../composables/useG3OverdueCheck'
import type { AgingPreset } from '@/composables/useAgingConfig'
import type { ChecklistResponse } from '../composables/useF1FormData'
import { G3DetailRevisionKey } from '../composables/g3InternalKeys'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
const detailRevision = inject(G3DetailRevisionKey, null)
let lastDetailRevSeen = -1

const overdue = useG3OverdueCheck({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId: toRef(props, 'projectId'),
})

/** G3-2 变更后：若已有逾期行则静默重导入（保留手工字段） */
function softImportFromDetailIfNeeded() {
  if (props.isReadonly || !detailRevision) return
  const rev = detailRevision.value
  if (rev <= lastDetailRevSeen) return
  lastDetailRevSeen = rev
  const hasRows = overdue.dataRows.value.some((r) => r.investeeName.trim())
  if (!hasRows) return
  overdue.importFromDetail()
}

onMounted(() => softImportFromDetailIfNeeded())
if (detailRevision) watch(detailRevision, () => softImportFromDetailIfNeeded())

const agingPresetModel = computed(() => overdue.agingPreset.value)
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  overdue.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : overdue.agingPreset.value,
)

function onImportFromDetail() {
  const r = overdue.importFromDetail()
  if (r.imported + r.updated === 0) {
    ElMessage.warning('G3-2 中未找到「期末应收>0 且已逾期」的明细')
  } else {
    ElMessage.success(`已导入 ${r.imported} 行、更新 ${r.updated} 行（按被投资方合并）`)
  }
}

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = overdue.customSegments.value.length
      ? overdue.customSegments.value.map((s) => s.label)
      : overdue.agingOptions.value
    customInput.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  overdue.setAgingPreset(val)
}

function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!overdue.setAgingPreset('CUSTOM', lines.slice(0, 10))) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!overdue.customSegments.value.length && overdue.agingPreset.value === 'CUSTOM') {
    overdue.setAgingPreset(lastNonCustomPreset.value)
  }
}

const CONCLUSION_KEY = 'G3-5-overdue-audit-conclusion'
const LEGACY_CONCLUSION_KEY = 'G3-5-overdue-conclusion'
const auditConclusion = ref(
  props.allResponses.get(CONCLUSION_KEY)?.remark
  ?? props.allResponses.get(LEGACY_CONCLUSION_KEY)?.conclusion
  ?? '',
)
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: v })
})
watch(
  () => props.allResponses.get(CONCLUSION_KEY)?.remark,
  (v) => { if (v != null) auditConclusion.value = v },
)

const NOTE_KEY = 'G3-5-overdue-audit-note'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { conclusion: null, remark: v })
})
watch(
  () => props.allResponses.get(NOTE_KEY)?.remark,
  (v) => { if (v != null) auditNote.value = v },
)

function rowClassName({ row }: { row: OverdueDividendRow }): string {
  return getOverdueRiskClass(row)
}

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}
</script>

<style scoped>
.g3-overdue-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.g3-overdue-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.g3-overdue-check :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right, .head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}
.muted { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
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
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover { color: #f56c6c; }
.summary-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  flex-wrap: wrap;
}
.summary-label { color: #303133; min-width: 36px; }
.summary-item { color: #606266; }
.audit-objective { margin-bottom: 12px; }
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
.subtotal-label, .subtotal-val { font-weight: 600; }
.audited-cell { display: flex; flex-direction: column; gap: 2px; }
</style>

<style>
.g3-overdue-check .overdue-danger,
.g3-overdue-check .overdue-danger td {
  background-color: #fef0f0 !important;
}
.g3-overdue-check .overdue-warning,
.g3-overdue-check .overdue-warning td {
  background-color: #fdf6ec !important;
}
.g3-overdue-check .row-subtotal,
.g3-overdue-check .row-subtotal td {
  background: #fafafa !important;
  font-weight: 600;
}
</style>
