<template>

  <div class="g10-adjustment" data-testid="g10-adjustment">

    <div class="section-head">

      <div class="title-block">

        <h3 class="sheet-title">G10-3 调整分录汇总</h3>

        <p class="sheet-sub">登记 2101 相关 AJE/RJE → 借贷平衡校验 → 分项回写 G10-1 (三)</p>

      </div>

      <div class="head-actions">

        <span class="chip-wrap"><GtIndexChip value="wp:G10-1" /></span>

        <span class="chip-wrap"><GtIndexChip value="wp:G10-5" /></span>

        <G10ImportExportDropdown :wp-id="wpId" sheet="G10-3" @imported="emit('imported')" />

        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="adj.procedureMarking.value"
          :disabled="!projectId || !adj.rows.value.length"
          data-testid="g10-adj-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ adj.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 调整程序' }}
        </el-button>

        <GtReviewTrigger section-id="G10-3-adjustment" />

      </div>

    </div>



    <details class="guidance-details" open>

      <summary>📋 编制提示（对齐 Excel 调整分录汇总 G10-3）</summary>

      <div class="guidance-content">

        <p>1. 本表汇总交易性金融负债（2101）相关的账项调整（AJE）与重分类（RJE）；整表借贷须平衡。</p>

        <p>2. Excel 模板按「调整事项说明 / 类别 / 报表项目 / 科目 / 附注项目 / 借贷 / 索引」列示；系统以分录行登记，<b>回写行</b>对应 G10-1 (三) 分项，<b>索引</b>对应支持性底稿（如 G10-5）。</p>

        <p>3. FVTPL 公允变动通常成对：负债 FV 上升 Dr 6101 / Cr 2101；下降反向。可用「+ 公允变动组」一键生成。</p>

        <p>4. 2101 净额（贷−借）按回写行汇总至 G10-1 期末账项调整；未指定时按负债类型或摘要关键词自动推断。</p>

        <p>5. 可从 G10-4/5/6/7/8「推送→G10-3」带入；亦可与中央调整分录模块双向同步（2101/6101 等）。</p>
        <p>6. 来自 G10-4「生成重分类草稿」的分录以橙色高亮；默认 RJE 借 2101 / 贷 2501，须复核对方科目与回写行。</p>
        <p>7. RJE 仅影响列报重分类；AJE 涉及损益的须与 G10-2 明细「计入损益」及 G10-5 公允测试勾稽。</p>
        <p>8. 编制完成后可「回填 G10A 调整程序」（步骤 3/4：公允证据与损益勾稽）。</p>
        <p>8. 工具栏「来源筛选」可按 G10-4/5/6/7/8、模块、零金额备忘等过滤；跨表推送后会自动切至对应来源。</p>
        <p>9. 2101 净额须与 G10-1 (三) 分项回写一致；不一致时目录 CHK-11 告警，可点「重新回写 G10-1」同步。</p>

      </div>

    </details>



    <el-alert type="info" :closable="false" class="objective-alert"

      title="审计目标：核实交易性金融负债相关 AJE/RJE 依据充分、借贷平衡、对方科目正确，并按分项回写 G10-1 审定表 (三) 账面余额。" />



    <el-alert

      v-if="g104PendingProjects > 0"

      type="warning"

      :closable="false"

      show-icon

      class="balance-alert"

      data-testid="g10-adj-g104-banner"

    >

      <template #title>

        来自 G10-4 的待复核重分类草稿 {{ g104PendingProjects }} 项（共 {{ g104PendingRows }} 行），请复核对方科目（默认 2501）及回写行后确认。

      </template>

      <div class="g104-banner-actions">

        <el-button size="small" type="primary" plain @click="scrollToFirstG104Draft">定位首行</el-button>

        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          data-testid="g10-adj-confirm-all-g104"
          @click="onConfirmAllG104Drafts"
        >
          全部确认已复核
        </el-button>

        <el-button size="small" :type="sourceFilter === 'pending_g104' ? 'primary' : 'default'" @click="togglePendingG104Filter">

          {{ sourceFilter === 'pending_g104' ? '显示全部' : '仅看待复核' }}

        </el-button>

        <span class="chip-wrap"><GtIndexChip value="wp:G10-4" /></span>

      </div>

    </el-alert>



    <el-alert
      v-if="hasWritebackMismatch"
      type="warning"
      :closable="false"
      show-icon
      class="balance-alert"
      data-testid="g10-adj-writeback-mismatch"
    >
      <template #title>
        G10-3 2101 净额 {{ fmt(writebackCross!.adj3Net2101) }} 与 G10-1 (三) 已回写 {{ fmt(writebackCross!.g101BookNet) }} 不一致，差额 {{ fmt(Math.abs(writebackCross!.diff)) }}（CHK-11）
      </template>
      <div v-if="!isReadonly" class="g104-banner-actions">
        <el-button size="small" type="primary" plain data-testid="g10-adj-reapply-writeback" @click="onReapplyWriteback">
          重新回写 G10-1
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G10-1" /></span>
      </div>
    </el-alert>

    <el-alert v-if="!adj.isBalanced.value" type="error" :closable="false" class="balance-alert" data-testid="g10-adj-balance-error">

      借贷不平衡：借方 {{ fmt(adj.debitTotal.value) }} ≠ 贷方 {{ fmt(adj.creditTotal.value) }}，差额 {{ fmt(Math.abs(adj.balanceDiff.value)) }}

    </el-alert>

    <el-alert

      v-else-if="writebackSummary"

      type="success"

      :closable="false"

      class="balance-alert"

      data-testid="g10-adj-writeback-hint"

    >

      已按分项回写 G10-1 期末账项调整：{{ writebackSummary }}

      （2101 净额 {{ fmt(adj.adjustmentNet.value) }}；6101 净额 {{ fmt(adj.summary.value.fvPlNet) }}）

    </el-alert>

    <el-alert

      v-else-if="adj.rows.value.length > 0 && adj.isBalanced.value"

      type="info"

      :closable="false"

      class="balance-alert"

    >

      借贷已平衡；2101 净额为 0，G10-1 期末账项调整保持 0。

    </el-alert>



    <div class="adj-toolbar">

      <el-button v-if="!isReadonly" size="small" type="primary" data-testid="g10-adj-add" @click="adj.addRow()">+ 新增分录</el-button>

      <el-button v-if="!isReadonly" size="small" plain data-testid="g10-adj-add-fvtpl" @click="adj.addFvPlPair()">+ 公允变动组(FVTPL)</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        :loading="adj.syncing.value"
        :disabled="!projectId"
        data-testid="g10-adj-sync-module"
        @click="onSyncFromModule"
      >
        从调整分录模块同步
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :disabled="!adj.isBalanced.value || !projectId"
        data-testid="g10-adj-push-module"
        @click="onPushToModule"
      >
        推送至调整分录模块
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        plain
        :loading="centralSyncing"
        :disabled="!adj.isBalanced.value || adj.rows.value.length === 0"
        title="把本页调整分录汇聚到集中调整登记，供合伙人跨循环审阅"
        @click="syncToCentral"
      >
        同步到集中登记
      </el-button>
      <el-tag
        v-if="centralStatus?.review_status"
        size="small"
        :type="centralStatus.review_status === 'approved' ? 'success' : (centralStatus.review_status === 'rejected' ? 'danger' : 'info')"
        :title="centralStatus.rejection_reason || ''"
      >
        集中登记：{{ CENTRAL_STATUS_LABELS[centralStatus.review_status] || centralStatus.review_status }}
      </el-tag>
      <span class="row-count">共 {{ adj.summary.value.rowCount }} 行（AJE {{ adj.summary.value.ajeCount }} / RJE {{ adj.summary.value.rjeCount }}）</span>
      <span v-if="adj.lastSyncMsg.value" class="sync-msg">{{ adj.lastSyncMsg.value }}</span>

    </div>

    <div v-if="adj.rows.value.length" class="source-filter-bar" data-testid="g10-adj-source-filter">
      <span class="filter-label">来源筛选：</span>
      <el-radio-group
        :model-value="sourceFilter"
        size="small"
        @update:model-value="(v: string | number | boolean | undefined) => { sourceFilter = String(v) as typeof sourceFilter }"
      >
        <el-radio-button
          v-for="opt in visibleSourceFilters"
          :key="opt.value"
          :value="opt.value"
        >
          {{ opt.label }}
          <template v-if="sourceCountFor(opt.value)">（{{ sourceCountFor(opt.value) }}）</template>
        </el-radio-button>
      </el-radio-group>
    </div>



    <el-table

      ref="adjTableRef"

      :data="displayRows"

      border

      size="small"

      style="font-size:13px"

      max-height="480"

      empty-text="暂无调整分录。可「新增分录」、录入公允变动分录组，或从 G10-5 推送公允差异。"
      :row-class-name="adjRowClassName"
    >

      <el-table-column prop="seq" label="#" width="44" align="center" />

      <el-table-column label="类型" width="78">

        <template #default="{ row }">

          <el-select v-if="!isReadonly" :model-value="row.entryType" size="small"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { entryType: v as 'AJE' | 'RJE' })">

            <el-option label="AJE" value="AJE" /><el-option label="RJE" value="RJE" />

          </el-select>

          <span v-else>{{ row.entryType }}</span>

        </template>

      </el-table-column>

      <el-table-column label="日期" width="128">

        <template #default="{ row }">

          <el-input v-if="!isReadonly" type="date" :model-value="row.date" size="small"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { date: v })" />

          <span v-else>{{ row.date || '—' }}</span>

        </template>

      </el-table-column>

      <el-table-column label="摘要" min-width="130">

        <template #default="{ row }">

          <div class="summary-cell">
            <el-tag v-if="isFromG104(row)" size="small" type="danger" class="src-tag">G10-4</el-tag>
            <el-tag v-else-if="isFromG105(row)" size="small" type="warning" class="src-tag">G10-5</el-tag>
            <el-tag v-else-if="isFromG106(row)" size="small" type="success" class="src-tag">G10-6</el-tag>
            <el-tag v-else-if="isFromG107(row)" size="small" type="info" class="src-tag">G10-7</el-tag>
            <el-tag v-else-if="isFromG108(row)" size="small" type="primary" class="src-tag">G10-8</el-tag>
            <el-input v-if="!isReadonly" :model-value="row.summary" size="small" placeholder="调整事由"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { summary: v })" />

            <span v-else>{{ row.summary }}</span>
          </div>

        </template>

      </el-table-column>

      <el-table-column label="负债类型" width="108">

        <template #default="{ row }">

          <el-select v-if="!isReadonly" :model-value="row.liabilityType || ''" size="small" clearable placeholder="推断回写"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { liabilityType: v })">

            <el-option v-for="t in adj.liabilityTypeOptions" :key="t" :label="t" :value="t" />

          </el-select>

          <span v-else>{{ row.liabilityType || '—' }}</span>

        </template>

      </el-table-column>

      <el-table-column label="回写行" width="148">

        <template #default="{ row }">

          <el-select v-if="!isReadonly" :model-value="row.adjudicationRowKey || ''" size="small" clearable filterable

            placeholder="自动推断"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { adjudicationRowKey: v })">

            <el-option v-for="o in adj.writebackOptions" :key="o.rowKey" :label="o.label" :value="o.rowKey" />

          </el-select>

          <span v-else>{{ writebackLabel(row.adjudicationRowKey) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="科目" width="168">

        <template #default="{ row }">

          <el-select v-if="!isReadonly" :model-value="row.accountCode" size="small" filterable allow-create default-first-option

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { accountCode: v })">

            <el-option v-for="opt in G10_ADJ_ACCOUNT_OPTIONS" :key="opt.code" :value="opt.code" :label="`${opt.code} ${opt.name}`" />

          </el-select>

          <span v-else>{{ row.accountCode }} {{ row.accountName }}</span>

        </template>

      </el-table-column>

      <el-table-column label="借方" width="108" align="right">

        <template #default="{ row }">

          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" size="small" :controls="false" :precision="2" style="width:100%"

            @update:model-value="(v: number | undefined) => adj.updateRow(row.rowId, { debitAmount: v ?? 0 })" />

          <span v-else>{{ fmt(row.debitAmount) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="贷方" width="108" align="right">

        <template #default="{ row }">

          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" size="small" :controls="false" :precision="2" style="width:100%"

            @update:model-value="(v: number | undefined) => adj.updateRow(row.rowId, { creditAmount: v ?? 0 })" />

          <span v-else>{{ fmt(row.creditAmount) }}</span>

        </template>

      </el-table-column>

      <el-table-column label="索引" width="88">

        <template #default="{ row }">

          <el-input v-if="!isReadonly" :model-value="row.indexRef" size="small" placeholder="G10-5"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { indexRef: v })" />

          <GtIndexChip v-else-if="row.indexRef" :value="row.indexRef.startsWith('wp:') ? row.indexRef : `wp:${row.indexRef}`" />

          <span v-else>—</span>

        </template>

      </el-table-column>

      <el-table-column label="编制人" width="80">

        <template #default="{ row }">

          <el-input v-if="!isReadonly" :model-value="row.preparedBy" size="small"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { preparedBy: v })" />

          <span v-else>{{ row.preparedBy || '—' }}</span>

        </template>

      </el-table-column>

      <el-table-column label="备注" min-width="90">

        <template #default="{ row }">

          <el-input v-if="!isReadonly" :model-value="row.remark" size="small"

            @update:model-value="(v: string) => adj.updateRow(row.rowId, { remark: v })" />

          <span v-else>{{ row.remark || '—' }}</span>

        </template>

      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="100" fixed="right">

        <template #default="{ row }">

          <el-button
            v-if="isPendingG104(row)"
            link
            type="success"
            size="small"
            @click="onConfirmG104Draft(row)"
          >
            已复核
          </el-button>
          <el-button link type="danger" size="small" @click="adj.removeRow(row.rowId)">删</el-button>

        </template>

      </el-table-column>

    </el-table>



    <div class="adj-footer" :class="{ 'balance-fail': !adj.isBalanced.value }" data-testid="g10-adj-footer">

      <span class="footer-label">合计</span>

      <span>借方 {{ fmt(adj.debitTotal.value) }}</span>

      <span>贷方 {{ fmt(adj.creditTotal.value) }}</span>

      <span v-if="adj.isBalanced.value" class="ok">✓ 平衡</span>

      <span v-else class="err">✗ 差额 {{ fmt(Math.abs(adj.balanceDiff.value)) }}</span>

      <span class="sep">|</span>

      <span>2101 净额 {{ fmt(adj.adjustmentNet.value) }}</span>

      <span>6101 净额 {{ fmt(adj.summary.value.fvPlNet) }}</span>

    </div>



    <G10AuditTextCards

      :wp-id="wpId"

      :is-readonly="isReadonly"

      v-model:note="auditNote"

      v-model:conclusion="auditConclusion"

      note-ai-section="adjustment-note"

      conclusion-ai-section="adjustment-conclusion"

      note-placeholder="填写审计说明：调整依据、AJE/RJE 判断、对 2101 与公允变动损益的影响、与 G10-5/G10-2 及 G10-1 回写勾稽情况。"

      note-hint="覆盖调整依据、借贷平衡、对方科目及按分项回写 G10-1 情况。"

      conclusion-placeholder="填写审计结论：A、调整分录借贷平衡且依据充分，已正确回写 G10-1。B、除上述调整事项外未见异常。C、存在重大未调整事项或范围受限，不可确认。"

      :related-context="{

        分录数: adj.summary.value.rowCount,

        AJE行数: adj.summary.value.ajeCount,

        RJE行数: adj.summary.value.rjeCount,

        借贷平衡: adj.isBalanced.value,

        差额: adj.balanceDiff.value,

        回写2101净额: adj.adjustmentNet.value,

        公允变动净额: adj.summary.value.fvPlNet,

      }"

    />

  </div>

</template>



<script setup lang="ts">

import { computed, ref, toRef, watch, onMounted, onBeforeUnmount, nextTick, inject } from 'vue'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import { useG10Adjustment, G10_ADJ_ACCOUNT_OPTIONS } from '../../composables/useG10Adjustment'
import { useAdjustmentCentralSync, CENTRAL_STATUS_LABELS } from '../../composables/useAdjustmentCentralSync'
import { useAuditContext } from '@/composables/useAuditContext'
import {
  isG10ClassificationAdjDraft,
  isPendingG10ClassificationAdjDraft,
  countPendingG10ClassificationAdjDrafts,
  countPendingG10ClassificationDraftProjects,
  G10_REVIEW_CLASSIFICATION_ADJ_KEY,
} from '../../composables/g10ClassificationCross'
import {
  countG10AdjBySource,
  filterG10AdjRows,
  G10_ADJ_SOURCE_FILTER_OPTIONS,
  g10AdjSourceFilterFromEvent,
  isFromG105,
  type G10AdjSourceFilter,
} from '../../composables/g10AdjSource'
import { isFromG107 } from '../../composables/g10VoucherCross'
import { isFromG108 } from '../../composables/g10DerivativeCross'
import { isFromG106 } from '../../composables/g10L3CrossHelpers'
import { compareG10Adj3VsG101Writeback } from '../../composables/g10AdjStorage'
import { G10_CROSS_TOLERANCE } from '../../composables/g10DisclosureFromAdj'
import {
  G10A_ADJUSTMENT_PROGRAM_NOS,
  G10A_PROCEDURE_SHEET,
} from '../../composables/g10FvCrossHelpers'
import { confirmNavigateToSheet, dispatchProcedureFocus } from '../../composables/g8CrossHelpers'

import type { ChecklistResponse } from '../../composables/useF1FormData'

import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'

import G10AuditTextCards from '../G10AuditTextCards.vue'

import GtReviewTrigger from '../../GtReviewTrigger.vue'

import GtIndexChip from '../../GtIndexChip.vue'



const props = defineProps<{

  allResponses: Map<string, ChecklistResponse>

  wpId: string

  projectId: string
  auditYear?: number | null
  isReadonly: boolean

  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void

}>()



const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)



const adj = useG10Adjustment({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
  projectId: computed(() => props.projectId || ''),
  auditYear: computed(() => props.auditYear),
})

// ─── 同步到集中调整登记（workpaper-adjustment-centralization） ───
const { year: centralYear } = useAuditContext()
const { centralStatus, syncing: centralSyncing, syncToCentral, refreshStatus } = useAdjustmentCentralSync({
  projectId: () => props.projectId || '',
  year: centralYear,
  wpId: () => props.wpId,
  wpCode: 'G10',
  itemId: 'G10-3-rows',
  buildLineItems: () => adj.rows.value.map((r) => ({
    standard_account_code: r.accountCode || undefined,
    account_name: r.accountName,
    debit_amount: r.debitAmount,
    credit_amount: r.creditAmount,
  })),
  buildMeta: () => ({
    description: adj.rows.value.find((r) => r.summary)?.summary || 'G10 交易性金融负债调整',
    adjustmentType: adj.rows.value.length > 0 && adj.rows.value.every((r) => r.entryType === 'RJE') ? 'rje' : 'aje',
  }),
})
onMounted(() => refreshStatus())

const adjTableRef = ref<InstanceType<typeof ElTable>>()
const sourceFilter = ref<G10AdjSourceFilter>('all')

const g104PendingRows = computed(() => countPendingG10ClassificationAdjDrafts(adj.rows.value))
const g104PendingProjects = computed(() => countPendingG10ClassificationDraftProjects(adj.rows.value))
const sourceCounts = computed(() => countG10AdjBySource(adj.rows.value))
const visibleSourceFilters = computed(() =>
  G10_ADJ_SOURCE_FILTER_OPTIONS.filter((opt) =>
    opt.value === 'all'
    || opt.value === 'pending_g104'
    || opt.value === 'zero_memo'
    || sourceCountFor(opt.value) > 0,
  ),
)
const displayRows = computed(() => filterG10AdjRows(adj.rows.value, sourceFilter.value))

const writebackCross = computed(() => compareG10Adj3VsG101Writeback(props.allResponses))
const hasWritebackMismatch = computed(() =>
  !!writebackCross.value && Math.abs(writebackCross.value.diff) > G10_CROSS_TOLERANCE,
)

function sourceCountFor(filter: G10AdjSourceFilter): number {
  return sourceCounts.value[filter as keyof typeof sourceCounts.value] ?? 0
}

function isPendingG104(row: {
  summary?: string
  remark?: string
  indexRef?: string
  draftReviewStatus?: string
}): boolean {
  return isPendingG10ClassificationAdjDraft(row)
}

function isFromG104(row: { summary?: string; remark?: string; indexRef?: string; draftReviewStatus?: string }): boolean {
  return isG10ClassificationAdjDraft(row)
}

function onConfirmG104Draft(row: {
  classificationSourceId?: string
  summary?: string
}) {
  const sourceIds = row.classificationSourceId ? [row.classificationSourceId] : undefined
  const summaries = row.summary ? [String(row.summary).trim()] : undefined
  const n = adj.confirmClassificationDrafts({ sourceIds, summaries })
  if (n > 0) ElMessage.success('已标记该重分类草稿为已复核')
  else ElMessage.info('该草稿已确认或无法匹配')
}

function togglePendingG104Filter() {
  sourceFilter.value = sourceFilter.value === 'pending_g104' ? 'all' : 'pending_g104'
}

function onConfirmAllG104Drafts() {
  const n = adj.confirmClassificationDrafts({ allPending: true })
  if (n > 0) ElMessage.success(`已确认 ${n} 项 G10-4 重分类草稿`)
  else ElMessage.info('无待复核的 G10-4 草稿')
}

function adjRowClassName({ row }: {
  row: {
    remark?: string
    summary?: string
    indexRef?: string
    sourceGroupId?: string
    draftReviewStatus?: string
  }
}) {
  if (isPendingG104(row)) return 'row-from-classification'
  if (isFromG104(row)) return 'row-g104-confirmed'
  if (isFromG105(row)) return 'row-from-fv'
  if (isFromG106(row)) return 'row-from-l3'
  if (isFromG107(row)) return 'row-from-voucher'
  if (isFromG108(row)) return 'row-from-derivative'
  if (row.sourceGroupId) return 'row-from-module'
  return ''
}

function scrollToFirstG104Draft() {
  const idx = adj.rows.value.findIndex(isPendingG104)
  if (idx < 0) return
  nextTick(() => {
    const tableEl = adjTableRef.value?.$el as HTMLElement | undefined
    const bodyRows = tableEl?.querySelectorAll('.el-table__body tbody tr')
    const displayIdx = sourceFilter.value === 'pending_g104'
      ? 0
      : displayRows.value.findIndex(isPendingG104)
    const target = bodyRows?.[displayIdx >= 0 ? displayIdx : idx] as HTMLElement | undefined
    target?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function onAdjUpdatedFromCross(ev: Event) {
  const filter = g10AdjSourceFilterFromEvent(
    (ev as CustomEvent<{ source?: string }>).detail?.source,
  )
  if (!filter) return
  sourceFilter.value = filter
  if (filter === 'pending_g104') nextTick(() => scrollToFirstG104Draft())
}

onMounted(() => {
  window.addEventListener('g10:adjustment-updated', onAdjUpdatedFromCross)
  if (sessionStorage.getItem(G10_REVIEW_CLASSIFICATION_ADJ_KEY)) {
    sourceFilter.value = 'pending_g104'
    nextTick(() => {
      scrollToFirstG104Draft()
      sessionStorage.removeItem(G10_REVIEW_CLASSIFICATION_ADJ_KEY)
    })
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('g10:adjustment-updated', onAdjUpdatedFromCross)
})

async function onSyncFromModule() {
  const n = await adj.syncFromAdjustmentModule()
  if (n > 0) ElMessage.success(`已从调整分录模块同步 ${n} 行`)
}

function onReapplyWriteback() {
  if (props.isReadonly || !adj.rows.value.length) return
  adj.syncWriteback()
  ElMessage.success('已按当前 G10-3 分录重新回写 G10-1 (三) 分项')
}

async function onMarkProcedure() {
  const n = await adj.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_ADJUSTMENT_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `调整/公允损益程序（步骤 ${[...G10A_ADJUSTMENT_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_ADJUSTMENT_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

async function onPushToModule() {
  const { ok, pushed } = await adj.confirmAndPush()
  if (!ok) {
    ElMessage.warning('请先保证借贷平衡后再推送')
    return
  }
  if (pushed > 0) ElMessage.success(`已推送 ${pushed} 笔至调整分录模块，并回写 G10-1`)
  else ElMessage.info(adj.lastSyncMsg.value || '无可推送分录（可能已同步）')
}



const writebackSummary = computed(() => {
  const entries = Object.entries(adj.writebackPreview.value.byRow).filter(([, v]) =>
    Math.abs(v.closingAje) > 0.005 || Math.abs(v.closingRje) > 0.005,
  )
  if (!entries.length) return ''
  return entries.map(([k, v]) => {
    const parts: string[] = []
    if (Math.abs(v.closingAje) > 0.005) parts.push(`AJE ${fmt(v.closingAje)}`)
    if (Math.abs(v.closingRje) > 0.005) parts.push(`RJE ${fmt(v.closingRje)}`)
    return `${writebackLabel(k)} ${parts.join(' / ')}`
  }).join('；')
})



function writebackLabel(rowKey: string): string {

  if (!rowKey) return '自动推断'

  return adj.writebackOptions.find((o) => o.rowKey === rowKey)?.label ?? rowKey

}



const NOTE_KEY = 'G10-3-adjustment-audit-note'

const CONCLUSION_KEY = 'G10-3-adjustment-audit-conclusion'

const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')

const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')

watch(auditNote, (v) => {

  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })

})

watch(auditConclusion, (v) => {

  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })

})



function fmt(v: number) {

  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })

}

</script>



<style scoped>

.g10-adjustment { font-size: var(--wp-font-size, 13px); }

.section-head { display: flex; justify-content: space-between; margin-bottom: 8px; flex-wrap: wrap; gap: 8px; }

.title-block .sheet-title { margin: 0; font-size: 15px; }

.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }

.head-actions { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }

.chip-wrap { display: inline-flex; }

.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }

.guidance-content p { margin: 4px 0; }

.objective-alert { margin-bottom: 8px; }

.balance-alert { margin-bottom: 8px; }

.adj-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }

.row-count { font-size: 12px; color: #909399; }
.sync-msg { font-size: 12px; color: #e6a23c; }
.summary-cell { display: flex; align-items: center; gap: 4px; }
.src-tag { flex-shrink: 0; }
:deep(.row-from-fv) { background: #fdf6ec; }
:deep(.row-from-l3) { background: #e8f4ff; }
:deep(.row-from-voucher) { background: #ecf5ff; }
:deep(.row-from-derivative) { background: #f4f4f5; }
:deep(.row-from-classification) { background: #fef0f0; }
:deep(.row-g104-confirmed) { background: #f0f9eb; }
:deep(.row-from-module) { background: #f0f9eb; }
.g104-banner-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 6px; }
.source-filter-bar {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center;
  margin-bottom: 8px; font-size: 12px;
}
.filter-label { color: #909399; flex-shrink: 0; }

.adj-footer {

  display: flex; flex-wrap: wrap; gap: 12px; align-items: center;

  margin-top: 8px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 13px;

}

.adj-footer.balance-fail { background: #fef0f0; }

.footer-label { font-weight: 600; }

.ok { color: #67c23a; }

.err { color: #f56c6c; font-weight: 600; }

.sep { color: #dcdfe6; }

</style>


