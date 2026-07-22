<template>
  <div class="g11-detail" data-testid="g11-detail">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表按投资收益 18 类项目骨架（与 G11-1 审定表一致）列示本期/上期发生额、占比及变动；可增补被投资单位明细行。</p>
        <p>2. 投资收益为损益类科目（6111），取发生额而非余额递推；审定=未审+调整；占比按本期/上期审定合计计算。</p>
        <p>3. |变动率|&gt;{{ (detail.CHANGE_RATE_THRESHOLD * 100).toFixed(0) }}% 的项目行高亮，须在「变动原因/索引」注明原因并交叉索引至支持性底稿。</p>
        <p>4. G11-3 账项调整按分项自动回写「本期调整」列；明细合计应与 G11-1 审定合计勾稽。</p>
        <p>5. 「本年利润总额」用于计算投资收益占利润比，便于判断重大性。</p>
        <p>6. 「处置交易性子类」用于上市附注「处置交易性金融资产」明细表灌数；有明细时优先于文本推断。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实各类投资收益的构成、金额及占比，验证本期与上期发生额的完整与准确，为 G11-1 审定表提供明细支持。"
    />

    <div class="section-head">
      <h3 class="sheet-title">G11-2 投资收益明细分析表</h3>
      <div class="head-actions">
        <el-button size="small" plain :disabled="isReadonly || !projectId" @click="onImportG714">从 G7-14 带入</el-button>
        <el-button
          size="small"
          plain
          :disabled="isReadonly || !projectId"
          data-testid="g11-detail-push-g714-adj"
          @click="onPushG714Diff"
        >G7-14 差异→G11-3</el-button>
        <el-button
          size="small"
          plain
          :disabled="isReadonly || !projectId"
          data-testid="g11-detail-prefill-ledger"
          @click="onPrefillLedger"
        >从 TB/序时账预填</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g11-detail-sync-disclosure"
          @click="onSyncDisclosure"
        >同步附注披露</el-button>
        <G11ImportExportDropdown :wp-id="wpId" sheet="G11-2" @imported="onImported" />
        <GtReviewTrigger section-id="G11-2-detail" />
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="detail.addRow()">+ 新增</el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="detail.resetToSkeleton()">重置骨架</el-button>
      </div>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="profit-label">本年利润总额</span>
        <el-input-number
          v-if="!isReadonly"
          :model-value="detail.profitTotal.value"
          size="small"
          :controls="false"
          style="width: 140px"
          @update:model-value="(v: number) => detail.updateProfitTotal(v ?? 0)"
        />
        <span v-else>{{ fmt(detail.profitTotal.value) }}</span>
        <el-tag v-if="detail.totalRow.value.shareOfProfit != null" size="small" type="info">
          占利润 {{ fmtPct(detail.totalRow.value.shareOfProfit) }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G11-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G11-1" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <el-tag v-if="detail.highlightCount.value" size="small" type="warning">
          异常变动 {{ detail.highlightCount.value }}
        </el-tag>
        <el-tag v-if="detail.missingReasonCount.value" size="small" type="danger">
          缺原因 {{ detail.missingReasonCount.value }}
        </el-tag>
      </div>
    </div>

    <el-alert
      v-if="crossValidation.detailCrossValidation.value"
      type="warning"
      :closable="false"
      class="cross-alert"
      data-testid="g11-detail-cross-alert"
    >
      {{ crossValidation.detailCrossValidation.value }}
      <GtIndexChip
        v-if="jumpToSection"
        label="G11-1"
        :prevent-navigate="true"
        :validate="false"
        class="warn-chip"
        @click="jumpToSection(resolveG11SheetLabel('G11-1'))"
      />
    </el-alert>
    <el-alert
      v-else-if="crossValidation.hasDetailData.value"
      type="success"
      :closable="false"
      class="cross-alert"
    >
      G11-1 与 G11-2 明细汇总一致
    </el-alert>

    <el-alert
      v-if="detail.g714ImportMsg.value"
      type="info"
      :closable="false"
      class="import-msg"
      :title="detail.g714ImportMsg.value"
    />
    <el-alert
      v-if="detail.ledgerImportMsg.value"
      type="info"
      :closable="false"
      class="import-msg"
      :title="detail.ledgerImportMsg.value"
    />

    <el-table
      :data="detail.rows.value"
      border
      stripe
      size="small"
      style="font-size:13px"
      max-height="560"
      data-testid="g11-detail-table"
      :row-class-name="detail.tableRowClassName"
    >
      <el-table-column prop="seq" label="序号" width="48" align="center" fixed />
      <el-table-column label="项目" min-width="160" fixed>
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly && !row.isSkeleton"
            :model-value="row.itemName"
            size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { itemName: v })"
          />
          <span v-else>{{ row.itemName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="投资类型" width="110">
        <template #default="{ row }">
          <span class="group-tag">{{ row.group }}</span>
        </template>
      </el-table-column>
      <el-table-column label="被投资单位" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.investeeName"
            size="small"
            @update:model-value="(v: string) => detail.updateRow(row.id, { investeeName: v })"
          />
          <span v-else>{{ row.investeeName }}</span>
        </template>
      </el-table-column>
      <el-table-column
        v-if="detail.hasTradingDisposeRows.value"
        label="处置子类"
        width="120"
        data-testid="g11-trading-dispose-subtype-col"
      >
        <template #default="{ row }">
          <el-select
            v-if="!isReadonly && isTradingDisposeRow(row)"
            :model-value="row.tradingDisposeSubtype || ''"
            size="small"
            clearable
            placeholder="自动推断"
            style="width:100%"
            @update:model-value="(v: string) => detail.updateRow(row.id, { tradingDisposeSubtype: v as any })"
          >
            <el-option
              v-for="opt in tradingDisposeOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
          <span v-else-if="isTradingDisposeRow(row)">{{ tradingDisposeLabel(row.tradingDisposeSubtype) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="本期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.currentUnadjusted"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentUnadjusted: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.currentUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.currentAdjustment"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { currentAdjustment: v ?? 0 })"
            />
            <span v-else class="formula-cell">{{ fmt(row.currentAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.currentAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.currentShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="上期数" align="center">
        <el-table-column label="未审" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorUnadjusted"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorUnadjusted: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.priorUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="调整" width="88" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.priorAdjustment"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.id, { priorAdjustment: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.priorAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定" width="88" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmt(row.priorAudited) }}</span></template>
        </el-table-column>
        <el-table-column label="占比" width="64" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtPct(row.priorShare) }}</span></template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="变动额" width="88" align="right">
        <template #default="{ row }">{{ fmt(row.changeAmount) }}</template>
      </el-table-column>
      <el-table-column label="变动率" width="72" align="right">
        <template #default="{ row }">
          <span :class="{ 'rate-alert': row.changeRateHighlight }">{{ fmtRate(row.changeRate) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="变动原因/索引" min-width="130">
        <template #default="{ row }">
          <el-input
            v-if="!isReadonly"
            :model-value="row.reasonIndex"
            size="small"
            :class="{ 'reason-required': row.reasonRequired && !row.reasonIndex }"
            :placeholder="row.reasonRequired ? '须填写变动原因' : ''"
            @update:model-value="(v: string) => detail.updateRow(row.id, { reasonIndex: v })"
          />
          <GtIndexChip v-else-if="row.reasonIndex" :value="row.reasonIndex" />
        </template>
      </el-table-column>
      <el-table-column label="操作" width="56" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button
            v-if="!row.isSkeleton"
            link
            type="danger"
            size="small"
            @click="detail.removeRow(row.id)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="group-summary" v-if="detail.groupedRows.value.length">
      <span v-for="g in detail.groupedRows.value" :key="g.groupName" class="group-chip">
        {{ g.groupName }} {{ fmt(g.subtotal.currentAudited) }}
      </span>
    </div>
    <div class="total-bar">
      合计 本期审定 {{ fmt(detail.totalRow.value.currentAudited) }}
      · 本期调整 {{ fmt(detail.totalRow.value.currentAdjustment) }}
      · 上期审定 {{ fmt(detail.totalRow.value.priorAudited) }}
      · 变动 {{ fmt(detail.totalRow.value.changeAmount) }}
      <template v-if="detail.totalRow.value.changeRate != null">
        · 变动率 {{ fmtRate(detail.totalRow.value.changeRate) }}
      </template>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计说明</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：可概述（1）投资收益明细分析程序的执行情况与结果；（2）重大变动项目（|变动率|>20%）的原因分析与拟调整/未调整事项及其影响。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="card-header"><span>审计结论</span></div></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受限无法获取充分适当证据），不可确认。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, onMounted, computed, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useG11DetailAnalysis } from '../../composables/useG11DetailAnalysis'
import { useG11CrossValidation } from '../../composables/useG11CrossValidation'
import { offerG11DisclosurePull } from '../../composables/g11DisclosureSync'
import { resolveG11SheetLabel } from '../../composables/g11SheetLabels'
import { G11_TRADING_DISPOSE_SUBTYPE_OPTIONS, isG11TradingDisposeDetailRow } from '../../composables/g11SchemaRows'
import type { G11TradingDisposeSubtype } from '../../composables/useG11DetailAnalysis'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import G11ImportExportDropdown from '../G11ImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  htmlData?: Record<string, unknown> | null
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const projectId = computed(() => props.projectId ?? '')
const htmlDataRef = computed(() => props.htmlData ?? null)

const detail = useG11DetailAnalysis({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId,
  htmlData: htmlDataRef,
})

const crossValidation = useG11CrossValidation(toRef(props, 'allResponses'))
const jumpToSection = inject<((sheetName: string) => void) | undefined>('jumpToSection', undefined)

const NOTE_KEY = 'G11-detail-audit-note'
const CONCLUSION_KEY = 'G11-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  props.debouncedSave(NOTE_KEY, { remark: val, conclusion: null })
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: val, remark: null })
  props.debouncedSave(CONCLUSION_KEY, { conclusion: val, remark: null })
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.conclusion || c?.remark) auditConclusion.value = String(c.conclusion ?? c.remark ?? '')
})

const tradingDisposeOptions = G11_TRADING_DISPOSE_SUBTYPE_OPTIONS

function isTradingDisposeRow(row: { rowKey?: string; itemName?: string }): boolean {
  return isG11TradingDisposeDetailRow(row)
}

function tradingDisposeLabel(v?: G11TradingDisposeSubtype | ''): string {
  if (!v) return '自动推断'
  return tradingDisposeOptions.find((o) => o.value === v)?.label ?? v
}

async function onSyncDisclosure(): Promise<void> {
  await offerG11DisclosurePull(
    props.allResponses,
    props.debouncedSave,
    'G11-2 明细已更新。是否同步更新附注披露（上市/国企）分项金额？',
  )
}

async function onImported() {
  emit('imported')
  detail.reloadFromStore()
}

async function onImportG714() {
  const n = await detail.importFromG714('empty_only')
  if (n > 0) ElMessage.success(detail.g714ImportMsg.value)
  else if (detail.g714ImportMsg.value) ElMessage.warning(detail.g714ImportMsg.value)
}

async function onPrefillLedger() {
  const n = await detail.prefillUnreviewedFromLedger('empty_only')
  if (n > 0) ElMessage.success(detail.ledgerImportMsg.value)
  else if (detail.ledgerImportMsg.value) ElMessage.warning(detail.ledgerImportMsg.value)
}

async function onPushG714Diff() {
  const { seeds } = await detail.loadG714SeedsForPush()
  const lineCount = detail.countG714DiffSuggestions(seeds)
  if (!lineCount) {
    ElMessage.warning('未找到可推送的 G7-14 投资收益差异')
    return
  }
  try {
    await ElMessageBox.confirm(
      `将写入 ${lineCount} 行建议分录至 G11-3（6111↔1511；仅替换同源 G7-14 草稿），是否继续？`,
      'G7-14 差异 → G11-3',
      { confirmButtonText: '推送', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  const result = detail.pushG714DiffToAdjustment(seeds)
  if (result.ok) {
    ElMessage.success(result.message)
    emit('imported')
  } else {
    ElMessage.warning(result.message)
  }
}

function fmt(v: number) {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtRate(r: number | null) {
  return r === null ? 'N/A' : (r * 100).toFixed(1) + '%'
}
function fmtPct(v: number | null) {
  return v === null ? '-' : (v * 100).toFixed(1) + '%'
}
</script>

<style scoped>
.g11-detail { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.profit-label { font-size: 12px; color: #606266; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #999; cursor: help; }
.group-tag { font-size: 11px; color: #606266; }
.group-summary { display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }
.group-chip { padding: 2px 8px; background: #ecf5ff; border-radius: 4px; font-size: 12px; }
.total-bar { margin-top: 8px; padding: 8px; background: #f5f7fa; font-size: 12px; }
.import-msg { margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.warn-chip { margin-left: 8px; }
.rate-alert { color: #e6a23c; font-weight: 600; }
:deep(.change-rate-alert) { background: #fdf6ec !important; }
:deep(.reason-required .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
