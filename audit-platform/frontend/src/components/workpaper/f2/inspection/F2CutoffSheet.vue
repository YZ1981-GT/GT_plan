<template>
  <div class="f2-cutoff">
    <header class="ct-hero">
      <div class="ct-hero-main">
        <div class="ct-kicker">
          {{ config.sheetCode }} · 原材料/产成品 · {{ config.direction === 'inbound' ? '入库' : '出库' }}
        </div>
        <h2 class="ct-title">{{ config.fullTitle }}</h2>
        <p class="ct-objective">
          <template v-if="config.trace === 'voucher_to_source'">
            从记账凭证追查至{{ config.primaryDocLabel }}等原始凭证，测试<strong>存在/发生</strong>，识别提前入账或跨期。
          </template>
          <template v-else>
            从{{ config.primaryDocLabel }}追查至记账凭证，测试<strong>完整性</strong>，识别推迟入账或漏记。
          </template>
        </p>
      </div>
      <div class="ct-hero-actions">
        <GtIndexChip :value="'wp:' + config.sheetCode" :context-project-id="projectId" />
        <template v-if="config.direction === 'outbound'">
          <GtIndexChip value="wp:D4-17" :context-project-id="projectId" />
          <GtIndexChip value="wp:D4-18" :context-project-id="projectId" />
        </template>
        <CycleImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          api-prefix="f2"
          :sheet="config.sheetCode"
          expanded
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="generateCutoffConclusion"
        >AI 生成</el-button>
        <F2ReviewChip :section-id="`${config.sheetCode}-conclusion`" />
      </div>
    </header>

    <F2CutoffOverviewCard
      v-if="overviewReady"
      :all-responses="allResponses"
      :bs-date="bsDate"
    />

    <details class="ct-guide guidance-details">
      <summary>编制提示</summary>
      <ol>
        <li v-for="(tip, i) in config.footerTips" :key="'ft-' + i">{{ tip }}</li>
        <li>请按原材料 / 产成品分类编制；细判会标出提前入账、推迟入账、有账无单、有单无账。</li>
        <li>单据日与记账日分落截止日两侧则标为跨期；发现错报时应扩大期间或样本量（可用「对称扩展」）。</li>
      </ol>
    </details>

    <section v-if="cutoff.crossHints.value.stocktakeNote" class="ct-link-banner">
      <strong>监盘勾稽</strong>
      <span>{{ cutoff.crossHints.value.stocktakeNote }}</span>
      <span v-if="cutoff.crossHints.value.uncheckedDocNos.length" class="muted">
        未命中示例：{{ cutoff.crossHints.value.uncheckedDocNos.slice(0, 5).join('、') }}
      </span>
    </section>

    <section v-if="config.direction === 'outbound'" class="ct-link-banner">
      <strong>收入截止</strong>
      <span>{{ d4Status }}</span>
      <el-button size="small" plain :loading="d4Loading" :disabled="!projectId" @click="refreshD4Matches">
        对照 D4-17/18
      </el-button>
      <ul v-if="d4Matches.length" class="d4-hits">
        <li v-for="m in d4Matches.slice(0, 8)" :key="m.f2DocNo + m.d4.sheet">
          {{ m.f2DocNo }} ↔ {{ m.d4.sheet }}
          {{ m.amountDiff ? '（金额不一致）' : '' }}
          {{ m.d4.isCutoff === false ? '（收入侧已标跨期）' : '' }}
        </li>
      </ul>
    </section>

    <section class="ct-card">
      <header class="ct-card-head">
        <div>
          <h3>一、审计目标</h3>
          <p>截止准确性 · 原材料/产成品期间归属</p>
        </div>
      </header>
      <ul class="obj-list">
        <li v-for="(o, i) in F2_CUTOFF_OBJECTIVES" :key="'obj-' + i">{{ o }}</li>
      </ul>
    </section>

    <section class="ct-card">
      <header class="ct-card-head">
        <div>
          <h3>二、审计过程</h3>
          <p>抽样窗口 · 金额门槛 · 与监盘/收入截止勾稽</p>
        </div>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="generateTextField('process')"
        >AI 填写过程说明</el-button>
      </header>
      <ol class="process-list">
        <li v-for="(step, i) in filledProcessSteps" :key="'ps-' + i">{{ step }}</li>
      </ol>
      <div class="ct-meta-grid">
        <div class="ct-field">
          <div class="ct-field-label">被审计单位</div>
          <el-input
            :model-value="cutoff.meta.value.entityName"
            :disabled="isReadonly"
            @update:model-value="(v: string) => cutoff.updateMeta({ entityName: v })"
          />
        </div>
        <div class="ct-field">
          <div class="ct-field-label">截止日</div>
          <el-date-picker
            :model-value="cutoff.meta.value.cutoffDate || bsDate || ''"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY年MM月DD日"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => cutoff.updateMeta({ cutoffDate: v || '' })"
          />
        </div>
        <div class="ct-field">
          <div class="ct-field-label">存货类别（分类编制）</div>
          <el-select
            :model-value="cutoff.meta.value.invCategory || ''"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string) => cutoff.updateMeta({ invCategory: v || '' })"
          >
            <el-option
              v-for="opt in F2_CUTOFF_CATEGORY_OPTIONS"
              :key="opt.value || 'all'"
              :label="opt.label === '全部类别' ? '双段展示（原材料+产成品）' : opt.label"
              :value="opt.value"
            />
          </el-select>
        </div>
        <div class="ct-field">
          <div class="ct-field-label">截止日前抽样天数</div>
          <el-input
            :model-value="cutoff.meta.value.sampleDaysBefore"
            :disabled="isReadonly"
            @update:model-value="(v: string) => cutoff.updateMeta({ sampleDaysBefore: v })"
          />
        </div>
        <div class="ct-field">
          <div class="ct-field-label">截止日后抽样天数</div>
          <el-input
            :model-value="cutoff.meta.value.sampleDaysAfter"
            :disabled="isReadonly"
            @update:model-value="(v: string) => cutoff.updateMeta({ sampleDaysAfter: v })"
          />
        </div>
        <div class="ct-field">
          <div class="ct-field-label">金额门槛（大于）</div>
          <el-input
            :model-value="cutoff.meta.value.amountThreshold"
            :disabled="isReadonly"
            placeholder="元，自动提取生效"
            @update:model-value="(v: string) => cutoff.updateMeta({ amountThreshold: v })"
          />
        </div>
        <div class="ct-field">
          <div class="ct-field-label">抽样窗口策略</div>
          <el-select
            :model-value="cutoff.meta.value.sampleWindowMode || 'primary'"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string) => cutoff.updateMeta({ sampleWindowMode: v })"
          >
            <el-option label="主窗（按追查方向侧重）" value="primary" />
            <el-option label="对称前后 N 天" value="symmetric" />
          </el-select>
        </div>
        <div class="ct-field">
          <div class="ct-field-label">窗口操作</div>
          <el-button size="small" :disabled="isReadonly" @click="cutoff.expandSymmetricWindow()">
            对称扩展 ±max(N)
          </el-button>
        </div>
        <div class="ct-field span2">
          <div class="ct-field-label">过程补充说明</div>
          <el-input
            :model-value="cutoff.meta.value.processNote"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="与监盘收发记录交叉核对、与收入截止协调情况等…"
            @update:model-value="(v: string) => cutoff.updateMeta({ processNote: v })"
          />
        </div>
      </div>
      <p class="window-hint">
        当前提取窗口：前 {{ cutoff.samplingDays.value.daysBefore }} 天 /
        后 {{ cutoff.samplingDays.value.daysAfter }} 天
        <template v-if="(cutoff.meta.value.sampleWindowMode || 'primary') === 'primary'">
          （{{ config.trace === 'voucher_to_source' ? '账→单主窗侧重截止日后' : '单→账主窗侧重截止日前' }}）
        </template>
      </p>
    </section>

    <div class="ct-toolbar">
      <div class="ct-toolbar-left">
        <el-tag size="small" type="primary">{{ config.trace === 'voucher_to_source' ? '账→单' : '单→账' }}</el-tag>
        <el-tag size="small">{{ config.direction === 'inbound' ? '入库' : '出库' }}</el-tag>
        <el-tag v-if="cutoff.cutoffSummary.value.earlyCount" size="small" type="danger">
          提前 {{ cutoff.cutoffSummary.value.earlyCount }}
        </el-tag>
        <el-tag v-if="cutoff.cutoffSummary.value.lateCount" size="small" type="warning">
          推迟 {{ cutoff.cutoffSummary.value.lateCount }}
        </el-tag>
        <el-tag v-if="cutoff.cutoffSummary.value.missingDocCount" size="small" type="info">
          有账无单 {{ cutoff.cutoffSummary.value.missingDocCount }}
        </el-tag>
        <el-tag v-if="cutoff.cutoffSummary.value.missingBookCount" size="small" type="info">
          有单无账 {{ cutoff.cutoffSummary.value.missingBookCount }}
        </el-tag>
      </div>
      <div class="ct-toolbar-right">
        <el-tag size="small" type="info">共 {{ cutoff.cutoffSummary.value.total }} 笔</el-tag>
      </div>
    </div>

    <div v-if="!isReadonly && wpId && projectId" class="auto-extract">
      <el-collapse v-model="autoExtractOpen">
        <el-collapse-item
          :title="config.trace === 'source_to_voucher'
            ? '⚡ 自动提取凭证（单→账：先抽邻近入账，再补全单据；理想起点为入库/出库流水）'
            : '⚡ 自动提取凭证'"
          name="auto-extract"
        >
          <!-- 折叠未展开时不挂载：避免首屏打 AI health / 拉起重型抽样面板 -->
          <GtCutoffAutoSampling
            v-if="autoExtractOpen.includes('auto-extract')"
            :key="`${config.sheetCode}-${cutoff.meta.value.sampleWindowMode}-${cutoff.meta.value.amountThreshold}-${cutoff.samplingDays.value.daysBefore}-${cutoff.samplingDays.value.daysAfter}`"
            :account-code="samplingAccountCodes"
            :cutoff-direction="effectiveCutoffDirection"
            :workpaper-id="wpId"
            :project-id="projectId"
            :year="year"
            :default-conditions="{
              directionFilter: samplingParams.directionFilter,
              daysBefore: cutoff.samplingDays.value.daysBefore,
              daysAfter: cutoff.samplingDays.value.daysAfter,
              amountThreshold: Number(cutoff.meta.value.amountThreshold) || 0,
              cutoffDate: cutoff.meta.value.cutoffDate || bsDate || '',
            }"
            @filled="handleAutoExtractFilled"
          />
        </el-collapse-item>
      </el-collapse>
    </div>

    <el-alert
      v-if="cutoff.cutoffSummary.value.uncategorizedCount >= 50"
      type="warning"
      :closable="false"
      show-icon
      class="ct-uncat-alert"
      :title="`当前有 ${cutoff.cutoffSummary.value.uncategorizedCount} 笔未分类样本。请在「存货类别」列标记原材料/产成品，或顶部筛选后分批处理；大样本已分页，避免卡顿。`"
    />

    <!-- 按原材料 / 产成品分类编制 -->
    <template v-for="block in cutoff.categoryBlocks.value" :key="block.key || 'uncat'">
      <section class="ct-card">
        <header class="ct-card-head">
          <div>
            <h3>{{ block.label }} · 截止日前</h3>
            <p>截止日期：{{ displayCutoff }} · {{ block.total }} 笔</p>
          </div>
          <el-button
            size="small"
            type="primary"
            :disabled="isReadonly"
            @click="cutoff.addRow(block.key || undefined)"
          >+ {{ block.label }}行</el-button>
        </header>
        <div class="ct-card-body">
          <el-empty v-if="!block.before.length" description="暂无截止日前样本" :image-size="48" />
          <CutoffTable
            v-else
            :rows="block.before"
            :config="config"
            :is-readonly="isReadonly"
            @update="(id, patch) => cutoff.updateRow(id, patch)"
            @remove="(id) => cutoff.removeRow(id)"
            @check="openCutoffVoucher"
          />
        </div>
      </section>

      <div class="ct-divider">———— {{ block.label }} · 截止日期：{{ displayCutoff }} ————</div>

      <section class="ct-card">
        <header class="ct-card-head">
          <div>
            <h3>{{ block.label }} · 截止日后</h3>
            <p>跨期风险关注区</p>
          </div>
        </header>
        <div class="ct-card-body">
          <el-empty v-if="!block.after.length" description="暂无截止日后样本" :image-size="48" />
          <CutoffTable
            v-else
            :rows="block.after"
            :config="config"
            :is-readonly="isReadonly"
            @update="(id, patch) => cutoff.updateRow(id, patch)"
            @remove="(id) => cutoff.removeRow(id)"
            @check="openCutoffVoucher"
          />
        </div>
      </section>

      <section v-if="block.unsorted.length" class="ct-card">
        <header class="ct-card-head">
          <div>
            <h3>{{ block.label }} · 未填日期</h3>
            <p>请补全以便分段与细判</p>
          </div>
        </header>
        <div class="ct-card-body">
          <CutoffTable
            :rows="block.unsorted"
            :config="config"
            :is-readonly="isReadonly"
            @update="(id, patch) => cutoff.updateRow(id, patch)"
            @remove="(id) => cutoff.removeRow(id)"
            @check="openCutoffVoucher"
          />
        </div>
      </section>
    </template>

    <div class="summary-footer">
      正确 {{ cutoff.cutoffSummary.value.correctCount }} /
      不正确 {{ cutoff.cutoffSummary.value.errorCount }} /
      跨期 {{ cutoff.cutoffSummary.value.crossCount }} /
      提前 {{ cutoff.cutoffSummary.value.earlyCount }} /
      推迟 {{ cutoff.cutoffSummary.value.lateCount }} /
      金额 {{ cutoff.cutoffSummary.value.errorAmount.toLocaleString() }} 元
    </div>

    <section class="ct-card ct-card-conclusion">
      <header class="ct-card-head">
        <div>
          <h3>三、审计说明</h3>
          <p>抽样、勾稽、跨期核实与拟调整事项</p>
        </div>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || !aiAvailable"
          :loading="aiLoading"
          @click="generateTextField('note')"
        >AI 填写审计说明</el-button>
      </header>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :rows="4"
        placeholder="填写审计说明…"
        resize="vertical"
        @change="saveAuditNote"
      />
    </section>

    <section class="ct-card ct-card-conclusion conclusion-card">
      <header class="ct-card-head">
        <div>
          <h3>四、审计结论</h3>
          <p>A 未见异常 · B 除重大不符应调整外其余未见异常 · C 重大未调整或范围受限不可确认</p>
        </div>
        <div class="ct-card-actions">
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateCutoffConclusion"
          >AI 生成结论摘要</el-button>
          <el-button
            size="small"
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateTextField('standard-conclusion')"
          >AI 生成 A/B/C 结论</el-button>
        </div>
      </header>
      <el-input
        v-model="cutoff.cutoffConclusion.value"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="截止测试结论摘要"
        resize="vertical"
      />
      <el-input
        class="ct-std-conclusion"
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :rows="3"
        placeholder="填写标准审计结论 A/B/C…"
        resize="vertical"
        @change="saveAuditConclusion"
      />
    </section>

    <footer class="ct-footer-tips">
      <div class="ct-footer-label">提示</div>
      <ol>
        <li v-for="(tip, i) in config.footerTips" :key="'tip-' + i">{{ tip }}</li>
      </ol>
    </footer>

    <F2CutoffVoucherDialog
      v-model="voucherDialogVisible"
      :row="voucherDialogRow"
      :period-end="cutoffDateRaw"
      :primary-doc-label="config.primaryDocLabel"
      :show-inspect="config.showInspect"
      :readonly="isReadonly"
      @save="handleCutoffVoucherSave"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, defineComponent, h, inject, onMounted, ref, toRef, watch, type PropType, type Ref, type VNode } from 'vue'
import {
  ElButton,
  ElDatePicker,
  ElInput,
  ElInputNumber,
  ElOption,
  ElPagination,
  ElSelect,
  ElSwitch,
  ElTable,
  ElTableColumn,
  ElTooltip,
  ElTag,
  ElAlert,
} from 'element-plus'
import { useF2CutoffSheet, type F2CutoffRow } from '../../composables/useF2CutoffSheet'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import { timingKindLabel } from '../../composables/f2CutoffJudgment'
import { fetchD4CutoffMatches } from '../../composables/useF2CutoffCrossSheet'
import {
  F2_CUTOFF_CATEGORY_OPTIONS,
  F2_CUTOFF_OBJECTIVES,
  getF2CutoffAccountCodes,
  getF2CutoffSamplingParams,
  type F2CutoffInvCategory,
  type F2CutoffSheetConfig,
} from './f2CutoffSheetConfigs'
import type { ChecklistResponse } from '../../composables/useF2FormData'
import type { ExtractedVoucher, FillMode } from '../../composables/useCutoffAutoSampling'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import F2ReviewChip from '../shared/F2ReviewChip.vue'
import F2CutoffOverviewCard from './F2CutoffOverviewCard.vue'
import F2CutoffVoucherDialog from './F2CutoffVoucherDialog.vue'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))

type ColEmit = (e: 'update', id: string, patch: Partial<F2CutoffRow>) => void

function dateCol(
  label: string,
  width: number,
  get: (r: F2CutoffRow) => string,
  key: keyof F2CutoffRow,
  props: { isReadonly: boolean },
  emit: ColEmit,
) {
  return h(ElTableColumn, { label, width }, {
    default: ({ row }: { row: F2CutoffRow }) =>
      h(ElDatePicker, {
        modelValue: get(row),
        type: 'date',
        size: 'small',
        valueFormat: 'YYYY-MM-DD',
        disabled: props.isReadonly,
        style: 'width: 100%',
        'onUpdate:modelValue': (v: string | null) => emit('update', row.id, { [key]: v || '' } as Partial<F2CutoffRow>),
      }),
  })
}

function textCol(
  label: string,
  minWidth: number,
  get: (r: F2CutoffRow) => string,
  key: keyof F2CutoffRow,
  props: { isReadonly: boolean },
  emit: ColEmit,
) {
  return h(ElTableColumn, { label, minWidth }, {
    default: ({ row }: { row: F2CutoffRow }) =>
      h(ElInput, {
        modelValue: get(row),
        size: 'small',
        disabled: props.isReadonly,
        'onUpdate:modelValue': (v: string) => emit('update', row.id, { [key]: v } as Partial<F2CutoffRow>),
      }),
  })
}

function voucherGroup(props: { isReadonly: boolean }, emit: ColEmit): VNode {
  return h(ElTableColumn, { label: '记账凭证' }, () => [
    dateCol('日期', 138, (r) => r.bookDate, 'bookDate', props, emit),
    textCol('凭证编号', 128, (r) => r.voucherNo, 'voucherNo', props, emit),
    textCol('业务内容', 190, (r) => r.businessContent, 'businessContent', props, emit),
    textCol('存货名称', 150, (r) => r.itemName, 'itemName', props, emit),
    h(ElTableColumn, { label: '金额', width: 120 }, {
      default: ({ row }: { row: F2CutoffRow }) =>
        h(ElInputNumber, {
          modelValue: row.amount,
          size: 'small',
          controls: false,
          disabled: props.isReadonly,
          'onUpdate:modelValue': (v: number | undefined) => emit('update', row.id, { amount: v ?? 0 }),
        }),
    }),
  ])
}

function docPair(
  label: string,
  noKey: 'docNo' | 'inspectNo' | 'otherDocNo',
  dateKey: 'docDate' | 'inspectDate' | 'otherDocDate',
  optional: boolean,
  props: { isReadonly: boolean },
  emit: ColEmit,
): VNode {
  return h(ElTableColumn, { label, className: optional ? 'optional-col' : undefined }, () => [
    textCol('编号', 128, (r) => String(r[noKey] || ''), noKey, props, emit),
    dateCol('日期', 138, (r) => String(r[dateKey] || ''), dateKey, props, emit),
  ])
}

const CUTOFF_PAGE_SIZE = 50

const CutoffTable = defineComponent({
  name: 'F2CutoffTable',
  props: {
    rows: { type: Array as PropType<F2CutoffRow[]>, required: true },
    config: { type: Object as PropType<F2CutoffSheetConfig>, required: true },
    isReadonly: { type: Boolean, default: false },
  },
  emits: {
    update: (_id: string, _patch: Partial<F2CutoffRow>) => true,
    remove: (_id: string) => true,
    check: (_row: F2CutoffRow) => true,
  },
  setup(props, { emit }) {
    const page = ref(1)
    watch(
      () => props.rows.length,
      (len) => {
        const maxPage = Math.max(1, Math.ceil(len / CUTOFF_PAGE_SIZE) || 1)
        if (page.value > maxPage) page.value = maxPage
      },
    )
    const pagedRows = computed(() => {
      if (props.rows.length <= CUTOFF_PAGE_SIZE) return props.rows
      const start = (page.value - 1) * CUTOFF_PAGE_SIZE
      return props.rows.slice(start, start + CUTOFF_PAGE_SIZE)
    })

    return () => {
      const sourceCols: VNode[] = [
        docPair(props.config.primaryDocLabel, 'docNo', 'docDate', false, props, emit),
      ]
      if (props.config.showInspect) {
        sourceCols.push(docPair('质检报告', 'inspectNo', 'inspectDate', true, props, emit))
      }
      sourceCols.push(docPair(props.config.otherDocLabel, 'otherDocNo', 'otherDocDate', true, props, emit))
      sourceCols.push(
        h(ElTableColumn, { label: '单据金额', width: 120, className: 'optional-col' }, {
          default: ({ row }: { row: F2CutoffRow }) =>
            h(ElInputNumber, {
              modelValue: row.docAmount,
              size: 'small',
              controls: false,
              disabled: props.isReadonly,
              'onUpdate:modelValue': (v: number | undefined) => emit('update', row.id, { docAmount: v ?? 0 }),
            }),
        }),
      )

      const voucherCols = [voucherGroup(props, emit)]
      const bodyCols = props.config.trace === 'voucher_to_source'
        ? [...voucherCols, ...sourceCols]
        : [...sourceCols, ...voucherCols]

      const needPaging = props.rows.length > CUTOFF_PAGE_SIZE
      const table = h(
        ElTable,
        {
          data: pagedRows.value,
          border: true,
          size: 'small',
          maxHeight: 420,
          class: 'cutoff-detail-table',
          rowClassName: ({ row }: { row: F2CutoffRow }) => (!row.isCorrect ? 'error-row' : ''),
        },
        () => [
          h(ElTableColumn, { prop: 'seq', label: '序号', width: 62, fixed: 'left', align: 'center' }),
          h(ElTableColumn, { label: '类别', width: 108, fixed: 'left' }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h(
                ElSelect,
                {
                  modelValue: row.invCategory || '',
                  size: 'small',
                  disabled: props.isReadonly,
                  style: 'width: 100%',
                  'onUpdate:modelValue': (v: string) =>
                    emit('update', row.id, { invCategory: (v || '') as F2CutoffRow['invCategory'] }),
                },
                () => [
                  h(ElOption, { label: '—', value: '' }),
                  h(ElOption, { label: '原材料', value: 'raw' }),
                  h(ElOption, { label: '产成品', value: 'finished' }),
                ],
              ),
          }),
          ...bodyCols,
          h(ElTableColumn, { label: '细判', width: 88 }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h(ElTag, {
                size: 'small',
                type: row.timingKind === 'ok' ? 'success'
                  : row.timingKind === 'early_book' ? 'danger'
                    : row.timingKind === 'late_book' ? 'warning' : 'info',
              }, () => timingKindLabel(row.timingKind)),
          }),
          h(ElTableColumn, { label: '证据', width: 88 }, {
            default: ({ row }: { row: F2CutoffRow }) => {
              const map: Record<string, string> = {
                missing_doc: '有账无单',
                missing_book: '有单无账',
                amount_mismatch: '金额不符',
              }
              return map[row.evidenceGap] || '—'
            },
          }),
          h(ElTableColumn, { label: '是否跨期', width: 88 }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h(
                ElSelect,
                {
                  modelValue: row.isCrossPeriod ? '是' : '否',
                  size: 'small',
                  disabled: props.isReadonly,
                  style: 'width: 100%',
                  'onUpdate:modelValue': (v: string) => {
                    const cross = v === '是'
                    emit('update', row.id, {
                      isCrossPeriod: cross,
                      isCorrectOverride: !cross,
                    })
                  },
                },
                () => [
                  h(ElOption, { label: '是', value: '是' }),
                  h(ElOption, { label: '否', value: '否' }),
                ],
              ),
          }),
          h(ElTableColumn, { label: '截止正确', width: 92 }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h(ElTooltip, {
                content: row.suggestion || (row.isCorrectOverride !== null
                  ? `自动: ${row.autoCorrect ? '正确' : '不正确'} → 已覆盖`
                  : '同侧正确；分侧/证据缺口为不正确'),
                placement: 'top',
              }, {
                default: () =>
                  h(ElSwitch, {
                    modelValue: row.isCorrect,
                    disabled: props.isReadonly,
                    activeText: '✓',
                    inactiveText: '✗',
                    onChange: (val: string | number | boolean) => {
                      const b = !!val
                      emit('update', row.id, {
                        isCorrectOverride: b !== row.autoCorrect ? b : null,
                      })
                    },
                  }),
              }),
          }),
          h(ElTableColumn, { label: '备注', minWidth: 180 }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h(ElInput, {
                modelValue: row.remark,
                size: 'small',
                disabled: props.isReadonly,
                'onUpdate:modelValue': (v: string) => emit('update', row.id, { remark: v }),
              }),
          }),
          h(ElTableColumn, { width: 88, fixed: 'right' }, {
            default: ({ row }: { row: F2CutoffRow }) =>
              h('div', { class: 'cutoff-row-actions' }, [
                h(ElButton, {
                  link: true,
                  type: 'primary',
                  size: 'small',
                  onClick: () => emit('check', row),
                }, () => '核对'),
                props.isReadonly
                  ? null
                  : h(ElButton, {
                      link: true,
                      type: 'danger',
                      size: 'small',
                      onClick: () => emit('remove', row.id),
                    }, () => '删'),
              ]),
          }),
        ],
      )

      if (!needPaging) return table

      return h('div', { class: 'cutoff-table-paged' }, [
        h(ElAlert, {
          type: 'info',
          closable: false,
          showIcon: true,
          title: `本段共 ${props.rows.length} 笔，分页展示（每页 ${CUTOFF_PAGE_SIZE} 行）以保障流畅编辑`,
          style: 'margin-bottom: 8px',
        }),
        table,
        h(ElPagination, {
          class: 'cutoff-pager',
          background: true,
          layout: 'total, prev, pager, next',
          total: props.rows.length,
          pageSize: CUTOFF_PAGE_SIZE,
          currentPage: page.value,
          small: true,
          'onUpdate:currentPage': (p: number) => { page.value = p },
        }),
      ])
    }
  },
})

const props = defineProps<{
  config: F2CutoffSheetConfig
  wpId?: string
  projectId?: string
  bsDate?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }

/** 自动提取面板默认收起；展开后再挂载抽样组件 */
const autoExtractOpen = ref<string[]>([])
/** 总览四表汇总延后一帧，优先渲染当前表 */
const overviewReady = ref(false)
onMounted(() => {
  requestAnimationFrame(() => { overviewReady.value = true })
})

const configRef = computed(() => props.config)
const samplingParams = computed(() => getF2CutoffSamplingParams(props.config))

const auditNote = ref('')
const auditConclusion = ref('')
const noteKey = computed(() => `${props.config.sheetCode}-audit-note`)
const conclusionKeyStd = computed(() => `${props.config.sheetCode}-audit-conclusion`)

function persistAudit(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  props.allResponses.set(key, item)
  window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
}
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistAudit(noteKey.value, val)
}
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistAudit(conclusionKeyStd.value, val)
}
function hydrateAudit(): void {
  auditNote.value = props.allResponses.get(noteKey.value)?.remark ?? ''
  auditConclusion.value = props.allResponses.get(conclusionKeyStd.value)?.remark ?? ''
}
watch(() => props.config.sheetCode, hydrateAudit)
onMounted(hydrateAudit)

const year = computed(() => {
  const d = props.bsDate || ''
  if (d.length >= 4) return parseInt(d.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

const cutoff = useF2CutoffSheet({
  config: configRef,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  periodEnd: computed(() => props.bsDate || ''),
})

const samplingAccountCodes = computed(() =>
  getF2CutoffAccountCodes((cutoff.meta.value.invCategory || '') as F2CutoffInvCategory),
)

const effectiveCutoffDirection = computed(() => {
  if ((cutoff.meta.value.sampleWindowMode || 'primary') === 'symmetric') return 'window' as const
  return samplingParams.value.cutoffDirection
})

const filledProcessSteps = computed(() => {
  const before = cutoff.meta.value.sampleDaysBefore || '___'
  const after = cutoff.meta.value.sampleDaysAfter || '___'
  const amt = cutoff.meta.value.amountThreshold || '___'
  return props.config.processSteps.map((s) =>
    s
      .replace(/截止日前后各 ___ 天/g, `截止日前后各 ${before}/${after} 天`)
      .replace(/金额大于 ___ 元/g, `金额大于 ${amt} 元`),
  )
})

const displayCutoff = computed(() => {
  const s = cutoff.meta.value.cutoffDate || props.bsDate || ''
  if (!s) return '未填'
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return s
  return `${m[1]}年${Number(m[2])}月${Number(m[3])}日`
})

/** 弹窗细判用原始 YYYY-MM-DD */
const cutoffDateRaw = computed(() => cutoff.meta.value.cutoffDate || props.bsDate || '')

const voucherDialogVisible = ref(false)
const voucherDialogRow = ref<F2CutoffRow | null>(null)
function openCutoffVoucher(row: F2CutoffRow) {
  voucherDialogRow.value = row
  voucherDialogVisible.value = true
}
function handleCutoffVoucherSave(patch: Partial<F2CutoffRow> & { id: string }) {
  cutoff.updateRow(patch.id, patch)
}

const d4Loading = ref(false)
const d4Status = ref('产成品出库应与 D4-17/18 收入截止协调；点击对照')
const d4Matches = ref<Awaited<ReturnType<typeof fetchD4CutoffMatches>>['matches']>([])

async function refreshD4Matches() {
  if (!props.projectId) return
  d4Loading.value = true
  try {
    const res = await fetchD4CutoffMatches(props.projectId, cutoff.rows.value)
    d4Status.value = res.message
    d4Matches.value = res.matches
  } finally {
    d4Loading.value = false
  }
}

function handleAutoExtractFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {
  cutoff.fillFromExtracted(payload.samples, payload.fillMode)
}

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF2AiGenerate(
  toRef(() => props.wpId || '') as Ref<string>,
)

async function generateCutoffConclusion() {
  const crossSamples = cutoff.rows.value
    .filter((r) => r.isCrossPeriod || !r.isCorrect)
    .slice(0, 10)
    .map((r) => {
      const cat = r.invCategory === 'raw' ? '原材料' : r.invCategory === 'finished' ? '产成品' : ''
      return `${cat ? `[${cat}]` : ''}${timingKindLabel(r.timingKind)} ${r.itemName || r.voucherNo}: 账${r.bookDate}/单${r.docDate}`
    })
    .join('；')
  const text = await generateAndConfirm(
    'cutoff-conclusion',
    cutoff.cutoffConclusion.value || auditConclusion.value,
    {
      sheet: props.config.sheetCode,
      title: props.config.fullTitle,
      trace: props.config.trace,
      direction: props.config.direction,
      total: cutoff.cutoffSummary.value.total,
      errorCount: cutoff.cutoffSummary.value.errorCount,
      crossCount: cutoff.cutoffSummary.value.crossCount,
      earlyCount: cutoff.cutoffSummary.value.earlyCount,
      lateCount: cutoff.cutoffSummary.value.lateCount,
      errorAmount: cutoff.cutoffSummary.value.errorAmount,
      stocktakeNote: cutoff.crossHints.value.stocktakeNote,
      varianceSummary: crossSamples || '无跨期样本',
    },
    `AI 生成 · ${props.config.title}结论`,
  )
  if (text) {
    cutoff.cutoffConclusion.value = text
    if (!auditConclusion.value) saveAuditConclusion(text)
  }
}

type CutoffAiTarget = 'process' | 'note' | 'standard-conclusion'

function cutoffAiContext(): Record<string, unknown> {
  const exceptions = cutoff.rows.value
    .filter((r) => r.isCrossPeriod || !r.isCorrect)
    .slice(0, 12)
    .map((r) => ({
      category: r.invCategory === 'raw' ? '原材料' : r.invCategory === 'finished' ? '产成品' : '未分类',
      voucherNo: r.voucherNo,
      itemName: r.itemName,
      bookDate: r.bookDate,
      docDate: r.docDate,
      judgment: timingKindLabel(r.timingKind),
      amount: r.amount,
      suggestion: r.suggestion,
    }))
  return {
    sheet: props.config.sheetCode,
    title: props.config.fullTitle,
    direction: props.config.direction,
    trace: props.config.trace,
    cutoffDate: cutoff.effectiveCutoff.value,
    sampleDaysBefore: cutoff.samplingDays.value.daysBefore,
    sampleDaysAfter: cutoff.samplingDays.value.daysAfter,
    amountThreshold: Number(cutoff.meta.value.amountThreshold) || 0,
    summary: cutoff.cutoffSummary.value,
    stocktakeNote: cutoff.crossHints.value.stocktakeNote,
    exceptions,
  }
}

async function generateTextField(target: CutoffAiTarget): Promise<void> {
  const options = {
    process: {
      section: 'cutoff-process-note' as const,
      existing: cutoff.meta.value.processNote,
      title: `AI 生成 · ${props.config.title}过程说明`,
    },
    note: {
      section: 'cutoff-audit-note' as const,
      existing: auditNote.value,
      title: `AI 生成 · ${props.config.title}审计说明`,
    },
    'standard-conclusion': {
      section: 'cutoff-standard-conclusion' as const,
      existing: auditConclusion.value,
      title: `AI 生成 · ${props.config.title}标准结论`,
    },
  }
  const option = options[target]
  const text = await generateAndConfirm(
    option.section,
    option.existing,
    cutoffAiContext(),
    option.title,
  )
  if (!text) return
  if (target === 'process') cutoff.updateMeta({ processNote: text })
  else if (target === 'note') saveAuditNote(text)
  else saveAuditConclusion(text)
}
</script>

<style scoped>
.f2-cutoff {
  --ct-border: #e8eaef;
  --ct-muted: #6b7280;
  --ct-ink: #1f2937;
  --ct-accent: var(--gt-color-primary, #4b2d77);
  --ct-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--ct-ink);
  width: 100%;
  max-width: none;
  box-sizing: border-box;
}
.f2-cutoff :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-cutoff :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.f2-cutoff :deep(.optional-col) { color: var(--gt-color-coral, #FF5149); }

.ct-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--ct-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #faf9ff 0%, #fff 55%);
}
.ct-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--ct-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.ct-title { margin: 0; font-size: 17px; font-weight: 650; line-height: 1.35; }
.ct-objective { margin: 6px 0 0; color: var(--ct-muted); line-height: 1.5; max-width: 56em; }
.ct-hero-actions {
  display: flex; flex-wrap: wrap; gap: 8px; align-items: center; justify-content: flex-end; flex-shrink: 0;
}

.ct-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--ct-surface);
}
.ct-guide summary { cursor: pointer; font-weight: 600; color: #374151; list-style: none; }
.ct-guide summary::-webkit-details-marker { display: none; }
.ct-guide ol {
  margin: 8px 0 4px; padding-left: 1.2em; color: var(--ct-muted); line-height: 1.55;
}

.ct-link-banner {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 12px;
  align-items: center;
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px dashed var(--gt-color-primary-lighter, #c4a8e8);
  background: #fafafa;
  font-size: 12px;
  color: #374151;
}
.ct-link-banner strong { color: var(--ct-accent); }
.ct-link-banner .muted { color: var(--ct-muted); }
.d4-hits {
  width: 100%;
  margin: 0;
  padding-left: 1.2em;
  color: var(--ct-muted);
}

.ct-card {
  margin-bottom: 12px;
  border: 1px solid var(--ct-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.ct-card-head {
  display: flex; justify-content: space-between; align-items: flex-start; gap: 12px;
  padding: 10px 14px; border-bottom: 1px solid var(--ct-border); background: var(--ct-surface);
}
.ct-card-head h3 { margin: 0; font-size: 13px; font-weight: 650; color: var(--ct-accent); }
.ct-card-head p { margin: 2px 0 0; font-size: 12px; color: var(--ct-muted); }
.ct-card-actions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.ct-card-body { padding: 12px 14px 14px; }
.ct-card-conclusion :deep(.el-textarea) { padding: 0 14px 10px; display: block; }
.ct-std-conclusion { padding: 0 14px 14px !important; }

.obj-list, .process-list {
  margin: 0; padding: 12px 14px 8px 2em; color: #374151; line-height: 1.55;
}
.window-hint {
  margin: 0 14px 12px;
  font-size: 12px;
  color: var(--ct-muted);
}

.ct-meta-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px 14px;
  padding: 12px 14px 8px;
}
.ct-field { display: flex; flex-direction: column; gap: 6px; min-width: 0; }
.ct-field.span2 { grid-column: 1 / -1; }
.ct-field-label { font-size: 12px; font-weight: 550; color: #374151; }

.ct-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.ct-toolbar-left, .ct-toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.f2-cutoff :deep(.cutoff-detail-table .el-table__header th) {
  padding: 7px 0;
  color: #3f2b5f;
  font-weight: 650;
  background: #f8f5fc;
}
.f2-cutoff :deep(.cutoff-detail-table .el-table__body td) { padding: 6px 0; }
.f2-cutoff :deep(.cutoff-detail-table .el-input__wrapper),
.f2-cutoff :deep(.cutoff-detail-table .el-select__wrapper) { min-height: 30px; }

.auto-extract { margin-bottom: 12px; }
.ct-divider {
  text-align: center;
  margin: 8px 0 14px;
  padding: 8px;
  font-size: 12px;
  font-weight: 600;
  color: var(--ct-accent);
  background: var(--ct-surface);
  border-radius: 6px;
  border: 1px dashed var(--gt-color-primary-lighter, #c4a8e8);
}

.summary-footer { margin: 4px 0 12px; font-size: 12px; color: #606266; }
.ct-uncat-alert { margin-bottom: 12px; }
.cutoff-table-paged { width: 100%; }
.cutoff-pager {
  margin-top: 10px;
  justify-content: flex-end;
}
.ct-footer-tips {
  margin-top: 8px;
  padding: 10px 14px;
  border-radius: 8px;
  background: #fafafa;
  border: 1px solid var(--ct-border);
  color: var(--ct-muted);
  font-size: 12px;
}
.ct-footer-label { font-weight: 650; color: var(--ct-accent); margin-bottom: 4px; }
.ct-footer-tips ol { margin: 0; padding-left: 1.2em; }
:deep(.error-row) { background: var(--gt-color-coral-light, #fff0ef); }
:deep(.cutoff-row-actions) { display: flex; flex-direction: column; align-items: flex-start; gap: 0; }
</style>
