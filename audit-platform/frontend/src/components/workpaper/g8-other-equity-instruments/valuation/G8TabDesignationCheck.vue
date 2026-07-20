<template>
  <div class="g8-designation" data-testid="g8-designation-check">
    <div class="section-head">
      <div class="title-block">
        <h3>G8-5 指定适当性检查（{{ dc.rows.value.length }} 行）</h3>
        <p class="sheet-sub">按被投资单位矩阵核查 CAS22 非交易性权益工具指定 FVOCI 的适当性</p>
      </div>
      <div class="head-actions tab-toolbar">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="dc.syncFromDetail(false)">
          从 G8-2 取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="dc.applyFromFairValue()">
          从 G8-4 带入 FV
        </el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="dc.refreshLinkage()">
          联动刷新
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="dc.fillDefaultChecks()">
          一键默认勾选
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" :loading="dc.validating.value" @click="onValidate">
          校验勾稽
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="dc.applyConclusionDraft(false)">
          结论草稿
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="dc.syncFromDetail(true)">
          强制刷新
        </el-button>
        <el-button
          size="small"
          type="success"
          plain
          :disabled="isReadonly"
          :loading="dc.procedureMarking.value"
          @click="onMarkProcedure"
        >
          {{ dc.procedureMarked.value ? '已回填 G8A（可重写）' : '回填 G8A seq2' }}
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="dc.addRow()">新增项目</el-button>
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-5" @imported="emit('imported')" />
        <GtReviewTrigger section-id="G8-5-designation" />
        <span class="chip-wrap"><GtIndexChip value="wp:G8-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-5" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8A" /></span>
      </div>
    </div>

    <div class="methodology">{{ G8_DESIGNATION_METHODOLOGY }}</div>

    <el-alert type="info" :closable="false" class="objective-alert" :title="G8_DESIGNATION_OBJECTIVE" />

    <details class="procedure-block">
      <summary>二、审计过程（展开）</summary>
      <ol>
        <li v-for="(step, i) in G8_DESIGNATION_PROCEDURE_STEPS" :key="i">{{ step }}</li>
      </ol>
    </details>

    <div class="stats-bar">
      <span>已列示 <b>{{ dc.stats.value.listed }}</b> 项</span>
      <span>指定适当 <b>{{ dc.stats.value.appropriate }}</b></span>
      <span v-if="dc.stats.value.tradingRisk" class="warn">
        存在交易性特征 <b>{{ dc.stats.value.tradingRisk }}</b>
      </span>
      <span v-if="dc.stats.value.incomplete" class="warn">
        待完成勾选 <b>{{ dc.stats.value.incomplete }}</b>
      </span>
      <span class="total">期末账面合计 {{ fmt(dc.totalBookValue.value) }}</span>
    </div>

    <el-alert
      v-if="dc.fvStale.value"
      type="warning"
      :closable="true"
      class="missing-alert"
      data-testid="g8-desig-fv-stale"
      title="G8-4 公允价值数据已更新，建议点击「联动刷新」或「从 G8-4 带入 FV」同步层次与可靠计量。"
      @close="dc.fvStale.value = false"
    />

    <el-alert
      v-if="dc.stats.value.incomplete"
      type="warning"
      :closable="false"
      class="missing-alert"
      :title="`有 ${dc.stats.value.incomplete} 项已列示账面价值但未完成「非交易性 / 权益工具 / FVOCI指定」矩阵勾选；完成后可回填 G8A 程序表 seq2。`"
    />

    <el-alert
      v-if="reconcileWarn"
      type="error"
      :closable="false"
      class="missing-alert"
      :title="reconcileWarn"
    />

    <el-alert
      v-if="levelReconcileWarn"
      type="warning"
      :closable="false"
      class="missing-alert"
      data-testid="g8-desig-level-mismatch"
      :title="levelReconcileWarn"
    />

    <el-alert
      v-if="remoteErrors.length"
      type="error"
      :closable="true"
      class="missing-alert"
      data-testid="g8-desig-validate-errors"
      @close="remoteErrors = []"
      :title="`远程校验 ${remoteErrors.length} 项：${remoteErrors.slice(0, 3).map(e => e.message).join('；')}${remoteErrors.length > 3 ? '…' : ''}`"
    />

    <el-table
      :data="tableRows"
      border
      size="small"
      max-height="560"
      style="font-size:13px"
      :row-class-name="rowClassName"
    >
      <el-table-column label="被投资单位" min-width="140" fixed>
        <template #default="{ row }">
          <b v-if="row.isTotal">合计</b>
          <el-input
            v-else
            :model-value="row.investeeName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateRow(row.rowId, { investeeName: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="期末账面价值" width="120" align="right">
        <template #default="{ row }">
          <b v-if="row.isTotal">{{ fmt(row.closingBookValue) }}</b>
          <el-input-number
            v-else
            :model-value="row.closingBookValue"
            size="small"
            :controls="false"
            style="width: 100%"
            :disabled="isReadonly"
            @change="(v: number) => dc.updateRow(row.rowId, { closingBookValue: v ?? 0 })"
          />
        </template>
      </el-table-column>

      <el-table-column label="「非交易性」[需不属于下列任一情形]" align="center">
        <el-table-column label="近期出售或回购" width="110" align="center">
          <template #header>
            <el-tooltip content="勾「是」表示存在该情形，不宜指定 FVOCI" placement="top">
              <span>近期出售或回购</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingNearTermSale"
              size="small"
              :disabled="isReadonly"
              clearable
              :class="{ 'cell-risk': row.tradingNearTermSale === 'yes' }"
              @change="(v: string) => dc.updateRow(row.rowId, { tradingNearTermSale: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="组合短期获利" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingPortfolioShortTerm"
              size="small"
              :disabled="isReadonly"
              clearable
              :class="{ 'cell-risk': row.tradingPortfolioShortTerm === 'yes' }"
              @change="(v: string) => dc.updateRow(row.rowId, { tradingPortfolioShortTerm: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="衍生/交易性" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.tradingDerivative"
              size="small"
              :disabled="isReadonly"
              clearable
              :class="{ 'cell-risk': row.tradingDerivative === 'yes' }"
              @change="(v: string) => dc.updateRow(row.rowId, { tradingDerivative: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="「权益工具投资」[需满足]" align="center">
        <el-table-column label="权益工具定义" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.equityInstrument"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => dc.updateRow(row.rowId, { equityInstrument: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="不可撤销指定" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.designatedFvtoci"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => dc.updateRow(row.rowId, { designatedFvtoci: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="FV可靠计量" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!row.isTotal"
              :model-value="row.fvReliable"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => dc.updateRow(row.rowId, { fvReliable: (v || '') as any })"
            >
              <el-option v-for="o in dc.ynOptions" :key="o.value" :label="o.label" :value="o.value" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="公允价值层次" width="110" align="center">
        <template #default="{ row }">
          <span v-if="row.isTotal">—</span>
          <el-select
            v-else
            :model-value="row.fairValueLevel"
            size="small"
            :disabled="isReadonly"
            clearable
            placeholder="层次"
            @change="(v: string) => dc.updateRow(row.rowId, { fairValueLevel: v || '' })"
          >
            <el-option v-for="lv in fvLevelOptions" :key="lv" :label="lv" :value="lv" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="指定原因(G8-2)" min-width="120">
        <template #default="{ row }">
          <span v-if="row.isTotal">—</span>
          <el-input
            v-else
            :model-value="row.designationReason"
            size="small"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 2 }"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateRow(row.rowId, { designationReason: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="指定适当性（自动）" min-width="160">
        <template #default="{ row }">
          <span
            v-if="!row.isTotal"
            :class="{
              'basis-ok': dc.hasFvtociBasis(row),
              'basis-warn': !dc.hasFvtociBasis(row) && (row.investeeName || row.closingBookValue),
              'basis-risk': dc.hasTradingCharacteristic(row),
            }"
          >
            {{ dc.designationBasisLabel(row) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="其他说明" min-width="100">
        <template #default="{ row }">
          <span v-if="row.isTotal">—</span>
          <el-input
            v-else
            :model-value="row.other"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateRow(row.rowId, { other: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="书面文件索引号" width="110">
        <template #default="{ row }">
          <el-input
            v-if="!row.isTotal"
            :model-value="row.indexRef"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dc.updateRow(row.rowId, { indexRef: v })"
          />
        </template>
      </el-table-column>

      <el-table-column label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button
            v-if="!row.isTotal && !isReadonly"
            size="small"
            type="danger"
            link
            @click="dc.removeRow(row.rowId)"
          >
            删
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="conclusionProxy"
      note-ai-section="designation-note"
      conclusion-ai-section="designation-conclusion"
      note-title="三、审计说明"
      conclusion-title="四、审计结论"
      note-placeholder="说明指定适当性检查范围、与 G8-2/G8-4 勾稽结果、存在交易性特征项目的核查及拟调整事项。"
      note-hint="覆盖非交易性三情形、权益工具定义、不可撤销指定及书面证据索引。"
      conclusion-placeholder="A、指定适当，未见异常。B、除上述应调整事项外，其余未见异常。C、因重大未调整事项或范围受限，不可确认。"
      :related-context="{
        已列示项数: dc.stats.value.listed,
        指定适当项数: dc.stats.value.appropriate,
        交易性风险项数: dc.stats.value.tradingRisk,
        待完成勾选项数: dc.stats.value.incomplete,
      }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示与准则脚注</summary>
      <p>① 先从 G8-2 取数；② 「一键默认勾选」填空白；③ 从 G8-4 带入 FV；④ 「校验勾稽」调用服务端校验；⑤ 「结论草稿」生成 A/B/C 口径结论；⑥ 完成后回填 G8A seq2。</p>
      <ul class="footnotes">
        <li v-for="(note, i) in G8_DESIGNATION_FOOTNOTES" :key="i">{{ note }}</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, toRef, inject } from 'vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import { useG8DesignationCheck, type G8DesignationRow } from '../../composables/useG8DesignationCheck'
import {
  G8_DESIGNATION_FOOTNOTES,
  G8_DESIGNATION_METHODOLOGY,
  G8_DESIGNATION_OBJECTIVE,
  G8_DESIGNATION_PROCEDURE_STEPS,
} from '../../composables/g8DesignationSeed'
import { G8_FV_LEVEL_OPTIONS } from '../../composables/g8Constants'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
  jumpToG8Sheet,
  G8A_DESIGNATION_PROGRAM_NOS,
} from '../../composables/g8CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)
const fvLevelOptions = G8_FV_LEVEL_OPTIONS

const dc = useG8DesignationCheck({
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
})

async function onMarkProcedure(): Promise<void> {
  const n = await dc.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G8A_DESIGNATION_PROGRAM_NOS],
    sheetCode: 'G8A',
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G8A',
    message: '指定适当性程序已标记完成。是否前往 G8A 程序表查看并定位 seq2？',
    confirmText: '前往 G8A',
  })
  if (go) {
    jumpToG8Sheet('G8A', jumpToSection)
    setTimeout(() => {
      dispatchProcedureFocus({ programNos: [...G8A_DESIGNATION_PROGRAM_NOS], sheetCode: 'G8A' })
    }, 400)
  }
}
type TableRow = G8DesignationRow & { isTotal?: boolean }

const tableRows = computed<TableRow[]>(() => {
  const data = dc.rows.value
  if (!data.length) return data
  return [
    ...data,
    {
      ...emptyTotalRow(),
      closingBookValue: dc.totalBookValue.value,
      isTotal: true,
    },
  ]
})

function emptyTotalRow(): G8DesignationRow {
  return {
    rowId: '__total__',
    seq: 0,
    investeeName: '',
    closingBookValue: 0,
    tradingNearTermSale: '',
    tradingPortfolioShortTerm: '',
    tradingDerivative: '',
    equityInstrument: '',
    designatedFvtoci: '',
    fvReliable: '',
    designationReason: '',
    fairValueLevel: '',
    other: '',
    indexRef: '',
  }
}

const remoteErrors = ref<{ field: string; message: string; rowKey?: string }[]>([])

async function onValidate() {
  const res = await dc.validateDesignationRemote()
  remoteErrors.value = res.errors
}

function fmt(n: number): string {
  if (!n) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: TableRow }): string {
  if (row.isTotal) return 'total-row'
  if (dc.hasTradingCharacteristic(row)) return 'risk-row'
  if (dc.hasFvtociBasis(row)) return 'ok-row'
  return ''
}

const AUDIT_NOTE_KEY = 'G8-5-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const conclusionProxy = computed({
  get: () => dc.overallConclusion.value,
  set: (v: string) => dc.updateOverallConclusion(v),
})

const reconcileWarn = computed(() => {
  const r = dc.detailReconcile.value
  if (!r.hasDetail) return ''
  const parts: string[] = []
  if (r.missingInDesignation.length) {
    parts.push(`G8-2 有、本表缺：${r.missingInDesignation.slice(0, 5).join('、')}${r.missingInDesignation.length > 5 ? '…' : ''}`)
  }
  if (r.missingInDetail.length) {
    parts.push(`本表有、G8-2 无：${r.missingInDetail.slice(0, 5).join('、')}${r.missingInDetail.length > 5 ? '…' : ''}`)
  }
  if (Math.abs(r.bookDiff) >= 0.01) {
    parts.push(`账面合计差 ${r.bookDiff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}（本表 − G8-2）`)
  }
  return parts.length ? `与 G8-2 勾稽异常：${parts.join('；')}` : ''
})

const levelReconcileWarn = computed(() => {
  if (!dc.hasLevelMismatch.value) return ''
  const r = dc.levelReconcile.value
  const parts: string[] = []
  if (r.mismatches.length) {
    parts.push(
      r.mismatches.slice(0, 3).map((m) => `${m.investeeName}：${m.issue}`).join('；'),
    )
  }
  if (r.missingInDesignation.length) {
    parts.push(`G8-4 有、本表缺：${r.missingInDesignation.slice(0, 5).join('、')}`)
  }
  if (r.missingInFv.length) {
    parts.push(`本表有、G8-4 无：${r.missingInFv.slice(0, 5).join('、')}`)
  }
  return parts.length ? `与 G8-4 层次勾稽异常：${parts.join('；')}` : ''
})
</script>

<style scoped>
.g8-designation { font-size: var(--wp-font-size, 13px); padding: 4px; }
.section-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; margin-bottom: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0 0 4px; font-size: 15px; }
.sheet-sub { margin: 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.methodology { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 8px 12px; margin-bottom: 10px; font-size: 12px; }
.objective-alert { margin-bottom: 10px; }
.procedure-block { margin-bottom: 10px; font-size: 12px; color: #606266; }
.procedure-block ol { margin: 8px 0 0; padding-left: 20px; }
.stats-bar { display: flex; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; font-size: 12px; color: #606266; }
.stats-bar .warn { color: #e6a23c; }
.stats-bar .total { margin-left: auto; font-weight: 600; }
.missing-alert { margin-bottom: 8px; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.footnotes { margin: 8px 0 0; padding-left: 18px; }
.basis-ok { color: #67c23a; }
.basis-warn { color: #e6a23c; }
.basis-risk { color: #f56c6c; font-weight: 500; }
:deep(.total-row) { background: #f5f7fa; font-weight: 600; }
:deep(.risk-row) { background: #fef0f0; }
:deep(.ok-row) { background: #f0f9eb; }
:deep(.cell-risk .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
