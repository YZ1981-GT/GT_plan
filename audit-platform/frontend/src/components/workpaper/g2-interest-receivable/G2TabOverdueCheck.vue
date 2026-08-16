<template>
  <div class="g2-overdue-check" data-testid="g2-overdue-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表检查长期未收回应收利息：按债务人列示期初/借贷发生/期末，说明未收回原因与处理计划。</p>
        <p>2. 期末余额 = 期初余额 + 本期借方 − 本期贷方（灰底自动）；审定余额默认可「同步期末」。</p>
        <p>3. 账龄支持「3年段 / 5年段 / 自定义」枚举（与 G2-2/G2-3 及项目账龄配置一致）。</p>
        <p>4. 账龄超过 1 年、或「是否无法收回」为是/部分时，行高亮提示；结论可按编制说明 A/B/C 口径表述。</p>
        <p>5. 可「从 G2-2 导入超1年」：按债务人合并账龄超 1 年挂账；期后收款可验证可收回性；重大无法收回事项应衔接 G2-3 / G2-7。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实长期未收回应收利息的存在与可收回性，评价未收回原因、处理计划及坏账准备计提是否恰当，为报表列报提供依据。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="sheet-title">G2-6 长期未收回款项检查表</span>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="overdue.addRow()">新增行</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onImportFromDetail">从 G2-2 导入超1年</el-button>
        <el-button size="small" :disabled="isReadonly" @click="onSyncAging">同步账龄至各表</el-button>
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
        <G2ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G2-6"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G2-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G2-3" /></span>
        <el-tag size="small" type="info">共 {{ overdue.dataRows.value.length }} 行</el-tag>
        <el-button size="small" @click="openReviewDialog('G2-6-overdue')">💬复核</el-button>
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
    >
      <el-table-column label="债务人名称" width="140" fixed>
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-label">{{ row.debtorName }}</span>
          <el-input
            v-else
            :model-value="row.debtorName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'debtorName', v)"
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
            @update:model-value="(v: number) => overdue.updateCell(row.id, 'openingBalance', v ?? 0)"
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
            @update:model-value="(v: number) => overdue.updateCell(row.id, 'periodDebit', v ?? 0)"
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
            @update:model-value="(v: number) => overdue.updateCell(row.id, 'periodCredit', v ?? 0)"
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
            @change="(v: string) => overdue.updateCell(row.id, 'aging', v ?? '')"
          >
            <el-option v-for="opt in overdue.agingOptions.value" :key="opt" :label="opt" :value="opt" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="Stage建议" width="100" align="center">
        <template #default="{ row }">
          <el-tag
            v-if="!overdue.isMetaRow(row) && overdue.getStageSuggestion(row) !== 'none'"
            size="small"
            :type="stageTagType(overdue.getStageSuggestion(row))"
            effect="plain"
          >{{ overdue.getStageSuggestion(row) }}</el-tag>
          <span v-else-if="!overdue.isMetaRow(row)" class="muted">—</span>
        </template>
      </el-table-column>

      <el-table-column label="经济业务说明" width="140">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.businessDesc"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'businessDesc', v)"
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
            @change="(v: string) => overdue.updateCell(row.id, 'unrecoveredReason', v)"
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
            @change="(v: string) => overdue.updateCell(row.id, 'isUncollectible', v ?? '')"
          >
            <el-option
              v-for="opt in uncollectibleOptions"
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
            @change="(v: string) => overdue.updateCell(row.id, 'actionPlan', v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="审定余额" width="110" align="right">
        <template #default="{ row }">
          <span v-if="overdue.isMetaRow(row)" class="subtotal-val">{{ fmtNum(row.auditedBalance) }}</span>
          <div v-else class="audited-cell">
            <WpAmountInput
              :model-value="row.auditedBalance"
              size="small"
              :disabled="isReadonly"
              style="width:100%"
              @update:model-value="(v: number) => overdue.updateCell(row.id, 'auditedBalance', v ?? 0)"
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
            @update:model-value="(v: number) => overdue.updateCell(row.id, 'postPeriodCollection', v ?? 0)"
          />
        </template>
      </el-table-column>

      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input
            v-if="!overdue.isMetaRow(row)"
            :model-value="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => overdue.updateCell(row.id, 'remark', v)"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="60" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!isReadonly && !overdue.isMetaRow(row)"
            size="small"
            type="danger"
            link
            @click="overdue.removeRow(row.id)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div class="grand-total">
        <span class="subtotal-label">汇总</span>
        长期挂账 {{ overdue.summary.value.longTermCount }} 笔 ·
        审定合计 {{ fmtNum(overdue.summary.value.auditedBalance) }} ·
        期后收款 {{ fmtNum(overdue.summary.value.postPeriodCollection) }} ·
        无法收回/部分 {{ overdue.summary.value.uncollectibleCount }} 笔
      </div>
    </div>

    <G2AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="overdue-note"
      conclusion-ai-section="overdue-evaluation"
      :related-context="{
        检查行数: overdue.dataRows.value.length,
        长期挂账笔数: overdue.summary.value.longTermCount,
        审定合计: overdue.summary.value.auditedBalance,
        期后收款合计: overdue.summary.value.postPeriodCollection,
        无法收回笔数: overdue.summary.value.uncollectibleCount,
        账龄口径: overdue.agingPreset.value,
      }"
      note-placeholder="填写审计说明：（1）抽样/全查范围；（2）长期挂账原因与处理计划；（3）期后收款验证；（4）坏账准备衔接。"
      note-hint="覆盖账龄枚举、未收回原因、可收回性及与 G2-3/G2-7 勾稽。"
      conclusion-hint="按编制说明 A（正常）/ B（除…外正常）/ C（无法表示意见）口径表述。"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
import { ref, toRef, computed, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useG2OverdueCheck,
  UNCOLLECTIBLE_OPTIONS,
  type OverdueCheckRow,
} from '../composables/useG2OverdueCheck'
import type { AgingPreset } from '@/composables/useAgingConfig'
import GtIndexChip from '../GtIndexChip.vue'
import G2ImportExportDropdown from './G2ImportExportDropdown.vue'
import G2AuditTextCards from './G2AuditTextCards.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const wpId = computed(() => props.wpId ?? '')

const overdue = useG2OverdueCheck({
  wpId: toRef(props, 'wpId', ''),
  projectId: toRef(props, 'projectId', ''),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const uncollectibleOptions = UNCOLLECTIBLE_OPTIONS

const agingPresetModel = computed(() => overdue.agingPreset.value)
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  overdue.agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : overdue.agingPreset.value,
)

function onImportFromDetail() {
  const r = overdue.importFromDetail()
  if (r.imported + r.updated === 0) {
    ElMessage.warning('G2-2 中未找到账龄超 1 年的明细')
  } else {
    ElMessage.success(`已导入 ${r.imported} 行、更新 ${r.updated} 行（按债务人合并）`)
  }
}

function onSyncAging() {
  overdue.syncAgingAcrossSheets()
}

function stageTagType(stage: string): 'info' | 'warning' | 'danger' {
  if (stage === 'Stage3') return 'danger'
  if (stage === 'Stage2') return 'warning'
  return 'info'
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

function rowClassName({ row }: { row: OverdueCheckRow }) {
  if (overdue.isMetaRow(row)) return 'row-subtotal'
  if (row.isUncollectible === '是') return 'row-uncollectible'
  if (overdue.isLongTerm(row) || row.isUncollectible === '部分') return 'row-long-term'
  return ''
}

function fmtNum(v: unknown): string {
  return typeof v === 'number'
    ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
    : String(v ?? '')
}

const NOTE_KEY = 'G2-6-audit-note'
const CONCLUSION_KEY = 'G2-6-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (v != null) auditNote.value = v })
watch(() => props.allResponses.get(CONCLUSION_KEY)?.remark, (v) => { if (v != null) auditConclusion.value = v })
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})
</script>

<style scoped>
.g2-overdue-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.g2-overdue-check :deep(.el-table) { --el-table-font-size: var(--wp-font-size, 13px); font-size: var(--wp-font-size, 13px); }
.g2-overdue-check :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.muted { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; align-items: center; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.subtotal-label, .subtotal-val { font-weight: 600; }
:deep(.row-subtotal) { background: #fafafa !important; font-weight: 600; }
:deep(.row-long-term) { background: #fdf6ec !important; }
:deep(.row-uncollectible) { background: #fef0f0 !important; }
.audited-cell { display: flex; flex-direction: column; gap: 2px; }
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.grand-total { margin-top: 6px; padding-top: 6px; border-top: 1px solid #dcdfe6; font-weight: 600; color: #303133; }
</style>
