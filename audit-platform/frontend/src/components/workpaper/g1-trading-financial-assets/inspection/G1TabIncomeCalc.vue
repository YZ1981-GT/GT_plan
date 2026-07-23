<template>
  <div class="g1-income-calc">
    <div class="section-head">
      <div class="title-block">
        <h3 class="sheet-title">G1-5 收益测算表</h3>
        <p class="sheet-sub">
          主路径：合同金额 × 年化利率 × 天数/基数（结息前/后分段）→ 与账上投资收益、应计利息勾稽
        </p>
      </div>
      <div class="head-actions">
        <G1ImportExportDropdown
          v-if="wpId"
          :wp-id="wpId"
          sheet="G1-5"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" :disabled="isReadonly" @click="onSyncDetail">从 G1-2 带入</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || calc.interestRows.value.length === 0"
          @click="onPushInterest"
        >回写利息至 G1-2</el-button>
        <el-button
          size="small"
          type="danger"
          plain
          :disabled="isReadonly || calc.balanceOk.value"
          @click="onPushAdj"
        >差异推送 G1-3</el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="onAddRow">
          {{ addLabel }}
        </el-button>
        <span class="chip-wrap"><GtIndexChip value="wp:G1-2" /></span>
        <el-button size="small" @click="openReviewDialog('G1-5-conclusion')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      title="审计目标：核实本期账面确认的投资收益（利息/股利）是否准确；对债类按合同重算应计利息并与投资收益、应计利息账面勾稽。"
      class="objective-alert"
    />

    <!-- 编制闸门 -->
    <section class="gates-card">
      <header class="gates-head">
        <div>
          <h4>编制闸门</h4>
          <p>对应程序：取债类合同 → 重算 → 与账面比对 → 差异沟通</p>
        </div>
        <el-tag :type="calc.gatesReady.value ? 'success' : 'warning'" size="small" effect="plain">
          {{ calc.gatesReady.value ? '已就绪' : '待完成' }}
        </el-tag>
      </header>
      <div class="gates-grid">
        <label class="gate-item">
          <el-checkbox
            :model-value="calc.gates.value.sampleCovered"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => calc.updateGates({ sampleCovered: !!v })"
          />
          <span>
            <strong>重大债类/固收样本已覆盖</strong>
            <small>已取得债券及其他固定收益产品清单与合同要素</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="calc.gates.value.basisConfirmed"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => calc.updateGates({ basisConfirmed: !!v })"
          />
          <span>
            <strong>计息基数已确认</strong>
            <small>Actual/365 或 360，与合同约定一致</small>
          </span>
        </label>
        <label class="gate-item">
          <el-checkbox
            :model-value="calc.gates.value.accruedBoundaryNoted"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => calc.updateGates({ accruedBoundaryNoted: !!v })"
          />
          <span>
            <strong>应计利息边界已关注</strong>
            <small>已到期应计利息进应收利息，不在 G1-2 明细重复列示</small>
          </span>
        </label>
      </div>
      <details class="guidance-details">
        <summary>准则提示（折叠）</summary>
        <div class="guidance-content">
          <p>交易性金融资产持有期间的利息/股利，通常确认为投资收益计入当期损益；与「冲减成本」类资产区分。</p>
          <p>差异原因常见：截止（结息跨期）、天数/基数错误、提前结息、利息进错科目。</p>
        </div>
      </details>
    </section>

    <!-- 账面勾稽块 -->
    <section class="recon-card">
      <header class="recon-head">
        <h4>账面勾稽</h4>
        <el-tag :type="calc.balanceOk.value ? 'success' : 'warning'" size="small" effect="plain">
          {{ calc.balanceOk.value ? '债息勾平' : '存在差异' }}
        </el-tag>
      </header>
      <div class="recon-grid">
        <div class="recon-field">
          <label>项目截止日</label>
          <el-date-picker
            :model-value="calc.bookRecon.value.cutoffDate || undefined"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="影响结息后计息截止"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => calc.updateBookRecon({ cutoffDate: v || '' })"
          />
        </div>
        <div class="recon-field">
          <label>测算应计利息合计</label>
          <div class="recon-readonly">{{ fmtNum(calc.interestTotal.value) }}</div>
        </div>
        <div class="recon-field">
          <label>账上投资收益（利息）</label>
          <el-input-number
            :model-value="calc.bookRecon.value.bookInvestmentIncome"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => calc.updateBookRecon({ bookInvestmentIncome: v ?? 0 })"
          />
        </div>
        <div class="recon-field">
          <label>账上应计利息</label>
          <el-input-number
            :model-value="calc.bookRecon.value.bookAccruedInterest"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => calc.updateBookRecon({ bookAccruedInterest: v ?? 0 })"
          />
        </div>
        <div class="recon-field">
          <label>账上合计</label>
          <div class="recon-readonly">{{ fmtNum(calc.bookInterestTotal.value) }}</div>
        </div>
        <div class="recon-field" :class="{ 'diff-warn': !calc.balanceOk.value }">
          <label>差异（测算 − 账上）</label>
          <div class="recon-readonly">{{ fmtNum(calc.interestBookDiff.value) }}</div>
        </div>
        <div class="recon-field">
          <label>账上股利收入</label>
          <el-input-number
            :model-value="calc.bookRecon.value.bookDividendIncome"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: number | undefined) => calc.updateBookRecon({ bookDividendIncome: v ?? 0 })"
          />
        </div>
        <div class="recon-field">
          <label>股利测算差异</label>
          <div class="recon-readonly">{{ fmtNum(calc.dividendBookDiff.value) }}</div>
        </div>
      </div>
    </section>

    <!-- G11 投资收益跨底稿勾稽 -->
    <section class="recon-card g11-recon-card">
      <header class="recon-head">
        <h4>↔ G11 投资收益勾稽</h4>
        <el-button size="small" :loading="g11Loading" @click="pullG11">刷新G11数据</el-button>
        <GtIndexChip value="wp:G11" />
        <el-tag
          v-if="g11Source !== 'unavailable'"
          :type="g11Reconcile.isConsistent ? 'success' : 'warning'"
          size="small"
          effect="plain"
        >
          {{ g11Reconcile.isConsistent ? '勾稽一致' : '存在差异' }}
        </el-tag>
        <el-tag v-else size="small" type="info" effect="plain">G11数据不可用</el-tag>
      </header>
      <div v-if="g11Source !== 'unavailable'" class="recon-grid">
        <div class="recon-field">
          <label>G1-5 利息合计</label>
          <div class="recon-readonly">{{ fmtNum(g11Reconcile.g1InterestTotal) }}</div>
        </div>
        <div class="recon-field">
          <label>G1-5 股利合计</label>
          <div class="recon-readonly">{{ fmtNum(g11Reconcile.g1DividendTotal) }}</div>
        </div>
        <div class="recon-field">
          <label>G1-5 处置净损益</label>
          <div class="recon-readonly">{{ fmtNum(g11Reconcile.g1DisposalTotal) }}</div>
        </div>
        <div class="recon-field">
          <label>G1-5 测算合计</label>
          <div class="recon-readonly"><b>{{ fmtNum(g11Reconcile.g1Total) }}</b></div>
        </div>
        <div class="recon-field">
          <label>G11 投资收益审定</label>
          <div class="recon-readonly"><b>{{ fmtNum(g11Reconcile.g11Audited) }}</b></div>
        </div>
        <div class="recon-field" :class="{ 'diff-warn': !g11Reconcile.isConsistent }">
          <label>差异（G1 − G11）</label>
          <div class="recon-readonly">{{ fmtNum(g11Reconcile.difference) }}</div>
        </div>
      </div>
      <p v-if="g11Source !== 'unavailable' && !g11Reconcile.isConsistent" class="g11-hint">
        差异常见原因：G11含权益法核算收益(G7-14)、债务重组损益、其他非G1循环投资收益。
      </p>
    </section>

    <div class="tab-toolbar">
      <el-segmented v-model="calc.segment.value" :options="segmentOptions" size="small" />
      <el-tag size="small" type="info" effect="plain">共 {{ currentRowCount }} 行</el-tag>
    </div>
    <p class="segment-hint">{{ segmentHint }}</p>

    <!-- 债息主表 -->
    <el-table
      v-if="calc.segment.value === 'interest'"
      :data="calc.interestRows.value"
      border
      size="small"
      max-height="480"
      class="detail-table"
    >
      <el-table-column prop="securityName" label="金融投资名称" width="140" fixed>
        <template #default="{ row }">
          <el-input
            v-model="row.securityName"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateInterestRow(row.id, { securityName: row.securityName })"
          />
        </template>
      </el-table-column>
      <el-table-column label="合同金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.contractAmount"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateInterestRow(row.id, { contractAmount: row.contractAmount })"
          />
        </template>
      </el-table-column>
      <el-table-column label="年化利率(%)" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.annualRatePct"
            size="small"
            :controls="false"
            :precision="4"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateInterestRow(row.id, { annualRatePct: row.annualRatePct })"
          />
        </template>
      </el-table-column>
      <el-table-column label="起始日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.startDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateInterestRow(row.id, { startDate: row.startDate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结息日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.settlementDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateInterestRow(row.id, { settlementDate: row.settlementDate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="到期日" width="130">
        <template #default="{ row }">
          <el-date-picker
            v-model="row.maturityDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateInterestRow(row.id, { maturityDate: row.maturityDate })"
          />
        </template>
      </el-table-column>
      <el-table-column label="基数" width="88">
        <template #default="{ row }">
          <el-select
            v-model="row.dayCountBasis"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateInterestRow(row.id, { dayCountBasis: row.dayCountBasis })"
          >
            <el-option :value="365" label="365" />
            <el-option :value="360" label="360" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="结息前天数" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.daysBeforeManual ?? row.daysBefore"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            :title="row.daysBeforeManual == null ? '自动计算，修改即转为手工覆盖' : '手工覆盖中'"
            @change="(v: number | undefined) => calc.updateInterestRow(row.id, { daysBeforeManual: v ?? null })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结息后天数" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.daysAfterManual ?? row.daysAfter"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            :title="row.daysAfterManual == null ? '自动计算，修改即转为手工覆盖' : '手工覆盖中'"
            @change="(v: number | undefined) => calc.updateInterestRow(row.id, { daysAfterManual: v ?? null })"
          />
        </template>
      </el-table-column>
      <el-table-column label="结息前利息" width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="合同金额×利率×结息前天数/基数">{{ fmtNum(row.interestBefore) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="结息后利息" width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtNum(row.interestAfter) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="应计利息小计" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell">{{ fmtNum(row.interestSubtotal) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateInterestRow(row.id, { remark: row.remark })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="100" fixed="right" align="center">
        <template #default="{ row }">
          <el-button
            v-if="row.daysBeforeManual != null || row.daysAfterManual != null"
            size="small"
            link
            @click="clearDays(row.id)"
          >自动天数</el-button>
          <el-button size="small" type="danger" link @click="calc.removeInterestRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 股利 -->
    <el-table
      v-else-if="calc.segment.value === 'dividend'"
      :data="calc.dividendRows.value"
      border
      size="small"
      max-height="480"
    >
      <el-table-column
        v-for="col in calc.dividendColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : 'left'"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <span v-if="col.formula" class="formula-cell">{{ fmtNum(row[col.prop]) }}</span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateDividendRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-date-picker
            v-else-if="col.type === 'date'"
            v-model="row[col.prop]"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateDividendRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateDividendRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="calc.removeDividendRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 处置 -->
    <el-table
      v-else
      :data="calc.disposalRows.value"
      border
      size="small"
      max-height="480"
    >
      <el-table-column
        v-for="col in calc.disposalColumns"
        :key="String(col.prop)"
        :label="col.label"
        :width="col.width"
        :align="col.type === 'number' || col.formula ? 'right' : 'left'"
        :fixed="col.prop === 'securityName' ? 'left' : undefined"
      >
        <template #default="{ row }">
          <span v-if="col.formula" class="formula-cell">{{ fmtNum(row[col.prop]) }}</span>
          <el-input-number
            v-else-if="col.type === 'number'"
            v-model="row[col.prop]"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            style="width: 100%"
            @change="calc.updateDisposalRow(row.id, { [col.prop]: row[col.prop] })"
          />
          <el-input
            v-else
            v-model="row[col.prop]"
            size="small"
            :disabled="isReadonly"
            @change="calc.updateDisposalRow(row.id, { [col.prop]: row[col.prop] })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="calc.removeDisposalRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="totals">
      <div v-if="calc.segment.value === 'interest'" class="grand-total">
        <span class="subtotal-label">债息测算合计</span>
        应计利息 {{ fmtNum(calc.interestTotal.value) }} ·
        账上合计 {{ fmtNum(calc.bookInterestTotal.value) }} ·
        差异 {{ fmtNum(calc.interestBookDiff.value) }}
      </div>
      <div v-else-if="calc.segment.value === 'dividend'" class="grand-total">
        <span class="subtotal-label">股利测算合计</span>
        应收 {{ fmtNum(calc.dividendReceivableTotal.value) }} ·
        与账上差异 {{ fmtNum(calc.dividendBookDiff.value) }} ·
        行内应收−实收 {{ fmtNum(calc.dividendDiffTotal.value) }}
      </div>
      <div v-else class="grand-total">
        <span class="subtotal-label">处置损益合计</span>
        净损益 {{ fmtNum(calc.disposalNetTotal.value) }}
      </div>
    </div>

    <G1AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      :conclusion="calc.auditConclusion.value"
      @update:conclusion="(v: string) => { calc.auditConclusion.value = v }"
      note-ai-section="income-note"
      conclusion-ai-section="income-conclusion"
      :related-context="{
        债息测算合计: calc.interestTotal.value,
        账上投资收益: calc.bookRecon.value.bookInvestmentIncome,
        账上应计利息: calc.bookRecon.value.bookAccruedInterest,
        债息差异: calc.interestBookDiff.value,
        股利测算合计: calc.dividendReceivableTotal.value,
        股利差异: calc.dividendBookDiff.value,
        处置净损益: calc.disposalNetTotal.value,
        闸门就绪: calc.gatesReady.value,
      }"
      note-placeholder="审计说明：（1）样本与合同要素；（2）分段计息结果与账面比对；（3）差异原因（截止/天数/科目）；（4）提议调整。"
      note-hint="覆盖债息重算、结息分段、投资收益与应计利息勾稽、差异解释。"
      conclusion-hint="A 未见异常；B 除重大调整外未见异常；C 因未调整或范围受限无法确认。"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, toRef, computed, inject, watch, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useG1IncomeCalc } from '../../composables/useG1IncomeCalc'
import { pullG11AuditedForG1, buildG1G11Reconcile } from '../../composables/g1G11IncomePull'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G1AuditTextCards from '../G1AuditTextCards.vue'
import G1ImportExportDropdown from '../G1ImportExportDropdown.vue'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  wpId?: string
  projectId?: string
}>()

const wpId = computed(() => props.wpId ?? '')
const emit = defineEmits<{ imported: [] }>()
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const calc = useG1IncomeCalc({
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly'),
})

// ─── G11 投资收益跨底稿勾稽 ───────────────────────────────────────────────────
const g11Audited = ref(0)
const g11Source = ref<'audited' | 'unadjusted' | 'unavailable'>('unavailable')
const g11Loading = ref(false)

const g11Reconcile = computed(() => buildG1G11Reconcile({
  g1InterestTotal: calc.interestTotal.value,
  g1DividendTotal: calc.dividendReceivableTotal.value,
  g1DisposalTotal: calc.disposalNetTotal.value,
  g11Audited: g11Audited.value,
  g11Source: g11Source.value,
}))

async function pullG11() {
  if (!props.projectId) return
  g11Loading.value = true
  try {
    const result = await pullG11AuditedForG1(props.projectId)
    g11Audited.value = result.audited
    g11Source.value = result.source
  } finally {
    g11Loading.value = false
  }
}

onMounted(() => {
  if (props.projectId) void pullG11()
})

const AUDIT_NOTE_KEY = 'G1-5-audit-note'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})

const segmentOptions = [
  { label: '①债息测算', value: 'interest' },
  { label: '②股利测算', value: 'dividend' },
  { label: '③处置损益', value: 'disposal' },
]

const segmentHint = computed(() => {
  switch (calc.segment.value) {
    case 'interest':
      return '录入合同金额、年化利率、起始/结息/到期日；天数与利息自动计算。结息后截止取 min(到期日, 项目截止日)。'
    case 'dividend':
      return '权益工具：应收 = 持有数量 × 每股股利；与账上股利收入勾稽。'
    default:
      return '补充程序：成交金额 = 数量 × 单价；处置损益 = 成交 − 成本；净损益 = 处置 − 手续费。'
  }
})

const addLabel = computed(() => {
  switch (calc.segment.value) {
    case 'interest':
      return '新增债息行'
    case 'dividend':
      return '新增股利行'
    default:
      return '新增处置行'
  }
})

const currentRowCount = computed(() => {
  switch (calc.segment.value) {
    case 'interest':
      return calc.interestRows.value.length
    case 'dividend':
      return calc.dividendRows.value.length
    default:
      return calc.disposalRows.value.length
  }
})

function onAddRow() {
  if (calc.segment.value === 'interest') void calc.addInterestRow()
  else if (calc.segment.value === 'dividend') void calc.addDividendRow()
  else void calc.addDisposalRow()
}

function onSyncDetail() {
  const r = calc.syncFromDetail()
  if (!r.interest && !r.dividend) {
    ElMessage.warning('G1-2 无可用明细，或投资类型无法映射')
    return
  }
  ElMessage.success(`已带入债息 ${r.interest} 行、股利 ${r.dividend} 行`)
}

function onPushInterest() {
  const { matched, unmatchedNames } = calc.pushInterestToDetail()
  if (!matched) {
    ElMessage.warning('未匹配到 G1-2 同名证券，请先带入或核对名称')
    return
  }
  ElMessage.success(`已回写 ${matched} 行利息/股利至 G1-2`)
  if (unmatchedNames.length) {
    const sample = unmatchedNames.slice(0, 3).join('、')
    const more = unmatchedNames.length > 3 ? ` 等 ${unmatchedNames.length} 只` : ''
    ElMessage.warning(`以下债息行未匹配到 G1-2：${sample}${more}`)
  }
}

function onPushAdj() {
  const n = calc.pushDiffToAdjustment()
  if (!n) {
    ElMessage.warning('无显著债息/股利差异可推送')
    return
  }
  ElMessage.success(`已推送 ${n} 条调整草稿至 G1-3（债息/股利）`)
}

function clearDays(rowId: string) {
  calc.clearDaysManual(rowId, 'both')
  ElMessage.success('已恢复自动计息天数')
}

function fmtNum(v: unknown): string {
  return typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : String(v ?? '')
}

function onImported() {
  emit('imported')
  calc.loadAll()
}
</script>

<style scoped>
.g1-income-calc {
  padding: 4px 4px 20px;
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}
.g1-income-calc :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 14px;
  flex-wrap: wrap;
}
.title-block { min-width: 200px; }
.sheet-title { margin: 0; font-size: 16px; font-weight: 600; color: #1f2a37; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #86909c; line-height: 1.4; }
.head-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.objective-alert { margin-bottom: 12px; }

.gates-card,
.recon-card {
  margin-bottom: 12px;
  border: 1px solid #e8ecf2;
  border-radius: 6px;
  padding: 12px 14px;
}
.gates-card {
  border-left: 3px solid #3d6b8e;
  background: #f7fafc;
}
.recon-card {
  border-left: 3px solid #5a7d5a;
  background: #f7faf7;
}
.gates-head,
.recon-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 10px;
}
.gates-head h4,
.recon-head h4 {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: #1f2a37;
}
.gates-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: #86909c;
}
.gates-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 8px 16px;
}
.gate-item {
  display: flex;
  gap: 8px;
  align-items: flex-start;
  cursor: pointer;
  font-size: 12px;
  color: #4e5969;
  line-height: 1.45;
}
.gate-item strong { display: block; color: #1f2a37; font-weight: 600; }
.gate-item small { display: block; color: #86909c; margin-top: 2px; }

.guidance-details {
  margin-top: 10px;
  border-top: 1px dashed #dce3ea;
  padding-top: 8px;
}
.guidance-details summary {
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  color: #3d6b8e;
  list-style: none;
}
.guidance-details summary::-webkit-details-marker { display: none; }
.guidance-content {
  margin-top: 6px;
  font-size: 12px;
  color: #606266;
  line-height: 1.65;
}
.guidance-content p { margin: 2px 0; }

.recon-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(160px, 1fr));
  gap: 10px 12px;
}
.recon-field label {
  display: block;
  font-size: 11px;
  color: #86909c;
  margin-bottom: 4px;
}
.recon-readonly {
  min-height: 28px;
  padding: 4px 8px;
  background: #fff;
  border: 1px solid #e4e7ed;
  border-radius: 4px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}
.diff-warn .recon-readonly {
  color: #b36b00;
  border-color: #f0d9b8;
  background: #fff8f0;
}

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
  flex-wrap: wrap;
  gap: 8px;
}
.segment-hint {
  margin: 0 0 8px;
  font-size: 12px;
  color: #86909c;
}
.detail-table { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #606266;
}
.totals { margin-top: 12px; font-size: 12px; color: #606266; }
.subtotal-label { font-weight: 600; margin-right: 8px; }
.grand-total {
  margin-top: 6px;
  padding-top: 8px;
  border-top: 1px solid #dcdfe6;
  font-weight: 600;
  color: #303133;
}
.g11-recon-card { border-left: 3px solid var(--el-color-primary-light-5); }
.g11-hint { font-size: 12px; color: #909399; margin: 6px 0 0 4px; }
</style>
