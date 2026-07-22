<template>
  <div class="h1-tab-finance-lease">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：①核实资产负债表列示的融资租出固定资产真实存在且分类正确；②确认资产归被审计单位所有或控制；③验证应收融资租赁款、未确认融资收益计量正确且披露充分。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-20" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ financeRows.length }} 项</el-tag>
      <el-tag size="small" type="success">融资分类 {{ financeSummary.financeCount }}</el-tag>
    </div>

    <div class="methodology-context">
      <p>
        编制逻辑：识别合同 → CAS21 五项分类判断（满足任一即为融资租赁）→ 确定最低租赁收款额/初始直接费用/内含利率 →
        计算应收融资租赁款与未确认融资收益 → 按实际利率法编制收益分配表 → 形成审计说明与结论。
      </p>
    </div>

    <!-- 一、合同识别与分类判断 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、融资租赁合同识别与分类判断</span>
          <div class="title-actions">
            <el-button size="small" type="success" plain :disabled="isReadonly || g5Loading" :loading="g5Loading" @click="handlePullG5">
              从 G5 带入
            </el-button>
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">+ 新增</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-20')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="financeRows"
        border
        stripe
        size="small"
        max-height="360"
        highlight-current-row
        @current-change="onSelectRow"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="assetCode" label="资产编号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCode" size="small" @change="onCell(row, 'assetCode')" />
            <span v-else>{{ row.assetCode || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCell(row, 'assetName')" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="lessee" label="承租单位" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.lessee" size="small" @change="onCell(row, 'lessee')" />
            <span v-else>{{ row.lessee }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="leaseStart" label="租赁开始日" width="125">
          <template #default="{ row }">
            <el-date-picker
              v-if="!isReadonly"
              v-model="row.leaseStart"
              type="date"
              value-format="YYYY-MM-DD"
              size="small"
              style="width:115px"
              @change="onCell(row, 'leaseStart')"
            />
            <span v-else>{{ row.leaseStart || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="contractIndex" label="合同索引" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.contractIndex" size="small" @change="onCell(row, 'contractIndex')" />
            <span v-else>{{ row.contractIndex || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column
          v-for="c in classCols"
          :key="c.field"
          :label="c.short"
          :width="72"
          align="center"
        >
          <template #header>
            <el-tooltip :content="c.full" placement="top">
              <span>{{ c.short }}</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row[c.field]"
              size="small"
              style="width:56px"
              @change="onCell(row, c.field)"
            >
              <el-option label="是" value="Y" />
              <el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ row[c.field] || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="分类" width="72" align="center">
          <template #default="{ row }">
            <el-tag :type="classifyFinanceLease(row) === '融资' ? 'success' : 'warning'" size="small">
              {{ classifyFinanceLease(row) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId" title="上传租赁合同 OCR 预填" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="50" v-if="!isReadonly" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('20', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="classification-criteria">
        <h4>CAS21 融资租赁五项判断（满足任一即为融资租赁）</h4>
        <el-descriptions :column="1" size="small" border>
          <el-descriptions-item v-for="c in classCols" :key="c.field" :label="c.short">
            {{ c.full }}
          </el-descriptions-item>
        </el-descriptions>
      </div>
    </el-card>

    <!-- 二、初始计量 -->
    <el-card v-if="selected" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、确定应收融资租赁款与未确认融资收益 — {{ selected.assetName || '未命名资产' }}</span>
        </div>
      </template>

      <el-row :gutter="12" class="measure-grid">
        <el-col :span="8">
          <div class="field-label">公允价值</div>
          <el-input-number
            v-if="!isReadonly"
            v-model="selected.fairValue"
            :controls="false"
            size="small"
            class="w-full"
            @change="onCell(selected, 'fairValue')"
          />
          <div v-else class="amount-cell">{{ fmtAmt(selected.fairValue) }}</div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">最低租赁收款额</div>
          <el-input-number
            v-if="!isReadonly"
            v-model="selected.minLeasePayment"
            :controls="false"
            size="small"
            class="w-full"
            @change="onCell(selected, 'minLeasePayment')"
          />
          <div v-else class="amount-cell">{{ fmtAmt(selected.minLeasePayment) }}</div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">初始直接费用</div>
          <el-input-number
            v-if="!isReadonly"
            v-model="selected.initialDirectCosts"
            :controls="false"
            size="small"
            class="w-full"
            @change="onCell(selected, 'initialDirectCosts')"
          />
          <div v-else class="amount-cell">{{ fmtAmt(selected.initialDirectCosts) }}</div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">未担保余值</div>
          <el-input-number
            v-if="!isReadonly"
            v-model="selected.unguaranteedResidual"
            :controls="false"
            size="small"
            class="w-full"
            @change="onCell(selected, 'unguaranteedResidual')"
          />
          <div v-else class="amount-cell">{{ fmtAmt(selected.unguaranteedResidual) }}</div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">租赁投资净额（现值）</div>
          <el-input-number
            v-if="!isReadonly"
            v-model="selected.presentValue"
            :controls="false"
            size="small"
            class="w-full"
            @change="onCell(selected, 'presentValue')"
          />
          <div v-else class="amount-cell">{{ fmtAmt(selected.presentValue) }}</div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">
            租赁内含利率 %
            <el-tag v-if="selected.rateSolved" size="small" type="success" class="rate-tag">IRR</el-tag>
          </div>
          <div class="rate-row">
            <el-input-number
              v-if="!isReadonly"
              v-model="selected.allocRate"
              :controls="false"
              :precision="4"
              size="small"
              class="rate-input"
              @change="onCell(selected, 'allocRate')"
            />
            <span v-else>{{ selected.allocRate }}%</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              @click="handleSolveRate"
            >
              IRR求解
            </el-button>
          </div>
        </el-col>
        <el-col :span="8">
          <div class="field-label">现值/公允占比</div>
          <div :class="['amount-cell', { 'ok-ratio': (selected.pvFvRatio ?? 0) >= 90 }]">
            {{ selected.pvFvRatio != null ? selected.pvFvRatio.toFixed(1) + '%' : '-' }}
            <el-tag v-if="(selected.pvFvRatio ?? 0) >= 90" size="small" type="success">≥90%</el-tag>
          </div>
        </el-col>
      </el-row>

      <el-table :data="measureRows" border size="small" class="measure-table">
        <el-table-column prop="label" label="项目" min-width="180" />
        <el-table-column prop="amount" label="金额" width="160" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="hint" label="说明" min-width="220" />
      </el-table>
    </el-card>

    <!-- 三、未确认融资收益分配表 -->
    <el-card v-if="selected" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、未确认融资收益分配表（实际利率法）</span>
          <div class="title-actions" v-if="!isReadonly">
            <span class="param-inline">
              各期租金
              <el-input-number
                v-model="selected.annualRent"
                :controls="false"
                size="small"
                style="width:110px"
                @change="onCell(selected, 'annualRent')"
              />
            </span>
            <span class="param-inline">
              期数
              <el-input-number
                v-model="selected.periodCount"
                :controls="false"
                :min="0"
                :max="40"
                size="small"
                style="width:70px"
                @change="onCell(selected, 'periodCount')"
              />
            </span>
            <el-button size="small" type="primary" plain @click="rebuildAmortSchedule(selected.rowId)">
              重算分配表
            </el-button>
          </div>
        </div>
      </template>

      <el-alert
        type="info"
        :closable="false"
        show-icon
        class="formula-alert"
        title="③确认融资收入 = 期初⑤×内含利率；④净投资减少 = ②租金−③；期末⑤ = 期初⑤−④"
      />

      <el-table
        v-if="selected.amortSchedule.length"
        :data="selected.amortSchedule"
        border
        stripe
        size="small"
        max-height="320"
        show-summary
        :summary-method="amortSummary"
      >
        <el-table-column prop="date" label="①日期" width="120" />
        <el-table-column prop="rent" label="②租金" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.rent) }}</span></template>
        </el-table-column>
        <el-table-column prop="financeIncome" label="③确认融资收入" width="130" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.financeIncome) }}</span></template>
        </el-table-column>
        <el-table-column prop="netDecrease" label="④净投资减少" width="120" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netDecrease) }}</span></template>
        </el-table-column>
        <el-table-column prop="netBalance" label="⑤净投资余额" width="120" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netBalance) }}</span></template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="请录入各期租金与期数后点击「重算分配表」" :image-size="64" />
    </el-card>

    <el-empty v-if="!selected && financeRows.length" description="点击上方表格某行，展开初始计量与分配表" :image-size="72" />

    <div class="summary-bar">
      <span>最低收款额合计: <b class="amount-cell">{{ fmtAmt(financeSummary.totalMinLease) }}</b></span>
      <span>应收融资租赁款: <b class="amount-cell">{{ fmtAmt(financeSummary.totalReceivable) }}</b></span>
      <span>未确认融资收益: <b class="amount-cell">{{ fmtAmt(financeSummary.totalUnearned) }}</b></span>
      <span>净投资合计: <b class="amount-cell">{{ fmtAmt(financeSummary.totalNetInvestment) }}</b></span>
      <span>本期融资收入: <b class="amount-cell">{{ fmtAmt(financeSummary.totalPeriodInterest) }}</b></span>
    </div>

    <!-- G5 勾稽对照 -->
    <el-card v-if="reconcileRows.length" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>与 G5 长期应收款勾稽对照 {{ g5SourceLabel }}</span>
          <el-button size="small" :loading="g5Loading" @click="handleRefreshReconcile">刷新勾稽</el-button>
        </div>
      </template>
      <el-table :data="reconcileRows" border stripe size="small" max-height="280">
        <el-table-column prop="h1AssetName" label="H1资产/项目" min-width="120" />
        <el-table-column prop="h1Lessee" label="承租人" width="100" />
        <el-table-column prop="g5ProjectName" label="G5项目" min-width="120">
          <template #default="{ row }">
            <span v-if="row.matched">{{ row.g5ProjectName }}</span>
            <el-tag v-else size="small" type="warning">未匹配</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="净投资差异" width="120" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': Math.abs(row.netVariance) > 0.01 }]">
              {{ row.matched ? fmtAmt(row.netVariance) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="未确认收益差异" width="130" align="right">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': Math.abs(row.unearnedVariance) > 0.01 }]">
              {{ row.matched ? fmtAmt(row.unearnedVariance) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="利率 H1/G5" width="120" align="center">
          <template #default="{ row }">
            {{ row.h1Rate }}% / {{ row.matched ? row.g5Rate + '%' : '-' }}
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 四、审计说明（结构化核对点） -->
    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计说明</span></template>
      <el-checkbox-group v-model="checkItems" :disabled="isReadonly" @change="syncAuditNoteFromChecks">
        <div v-for="item in auditCheckOptions" :key="item" class="check-line">
          <el-checkbox :label="item">{{ item }}</el-checkbox>
        </div>
      </el-checkbox-group>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        class="note-extra"
        placeholder="补充说明：分类依据、内含利率测算方法、与账面长期应收款/未确认融资收益核对差异等。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>五、审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="例：经检查，融资租出固定资产分类正确，应收融资租赁款及未确认融资收益初始计量与分配未见异常。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>五项判断满足任一 → 融资租赁；均不满足 → 应改按经营租赁（H1-19）</li>
        <li>应收融资租赁款 = 最低租赁收款额 + 初始直接费用；未确认融资收益 = 最低租赁收款额 + 未担保余值 − 租赁投资净额</li>
        <li>内含利率可用「IRR求解」：使各期租金与未担保余值的现值等于公允价值+初始直接费用（净投资）</li>
        <li>融资租出终止确认固定资产，转入长期应收款；可用「从 G5 带入」与长期应收款底稿勾稽</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH1LeaseCheck, type FinanceLeaseRow } from '../../composables/useH1LeaseCheck'
import {
  fetchG5FinanceLeaseSeeds,
  buildH1G5Reconcile,
  type H1FinanceLeaseG5Seed,
  type H1G5ReconcileRow,
} from '../../composables/h1FinanceLeaseG5Pull'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const conclusion = ref('')
const auditNoteText = ref('')
const ocrLoadingId = ref('')
const checkItems = ref<string[]>([])
const selectedId = ref<string | null>(null)
const g5Loading = ref(false)
const g5Seeds = ref<H1FinanceLeaseG5Seed[]>([])
const g5Source = ref<'G5-5' | 'G5-2' | null>(null)

const NOTE_KEY = 'H1-20-audit-note'
const CONCLUSION_KEY = 'H1-20-audit-conclusion'
const CHECK_KEY = 'H1-20-audit-checks'

const auditCheckOptions = [
  '1. 融资租出固定资产是否满足融资租赁确认条件（CAS21五项判断）',
  '2. 长期应收款、应收融资租赁款、未确认融资收益初始入账价值是否正确',
  '3. 租赁内含利率确定是否正确',
  '4. 未确认融资收益按实际利率法分配是否恰当',
]

const classCols = [
  { field: 'classResult1' as const, short: '①所有权', full: '租赁期届满时，资产所有权转移给承租人' },
  { field: 'classResult2' as const, short: '②购买权', full: '承租人有优惠购买选择权，且行使可能性很大（价格远低于公允）' },
  { field: 'classResult3' as const, short: '③租期75%', full: '租赁期占资产使用寿命的大部分（通常≥75%）' },
  { field: 'classResult4' as const, short: '④PV90%', full: '最低租赁收款额现值几乎相当于公允价值（通常≥90%）' },
  { field: 'classResult5' as const, short: '⑤专用性', full: '租赁资产性质特殊，若不作较大改造只有承租人才能使用' },
]

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }
function saveChecks() { saveResponse(CHECK_KEY, checkItems.value) }

function syncAuditNoteFromChecks() {
  saveChecks()
  const checked = checkItems.value
  const lines = auditCheckOptions.map((opt) => `${checked.includes(opt) ? '✓' : '○'} ${opt}`)
  const extra = auditNoteText.value
    .split('\n')
    .filter((l) => l && !auditCheckOptions.some((o) => l.includes(o.slice(0, 8))))
    .join('\n')
  auditNoteText.value = [lines.join('\n'), extra].filter(Boolean).join('\n\n')
  saveAuditNote()
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = typeof n.remark === 'string' ? n.remark : String(n.remark)
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = typeof c.remark === 'string' ? c.remark : String(c.remark)
  const ch = props.allResponses.get(CHECK_KEY)
  if (ch?.remark) {
    try {
      const parsed = JSON.parse(ch.remark)
      if (Array.isArray(parsed)) checkItems.value = parsed
    } catch { /* ignore */ }
  }
})

const {
  financeRows,
  financeSummary,
  addFinanceRow,
  removeRow,
  updateFinanceCell,
  applyFinanceLeaseOcr,
  rebuildAmortSchedule,
  solveImplicitRate,
  importFromG5Seeds,
  classifyFinanceLease,
} = useH1LeaseCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const selected = computed(() =>
  financeRows.value.find((r) => r.rowId === selectedId.value) ?? financeRows.value[0] ?? null,
)

watch(financeRows, (rows) => {
  if (!selectedId.value && rows.length) selectedId.value = rows[0].rowId
  if (selectedId.value && !rows.some((r) => r.rowId === selectedId.value)) {
    selectedId.value = rows[0]?.rowId ?? null
  }
}, { immediate: true })

const measureRows = computed(() => {
  const r = selected.value
  if (!r) return []
  return [
    { label: '最低租赁收款额', amount: r.minLeasePayment, hint: '各期租金 + 担保余值等' },
    { label: '加：未担保余值', amount: r.unguaranteedResidual, hint: '出租人未担保的资产余值' },
    { label: '加：初始直接费用', amount: r.initialDirectCosts, hint: '出租人发生的初始直接费用' },
    { label: '应收融资租赁款', amount: r.leaseReceivable, hint: '最低租赁收款额 + 初始直接费用' },
    { label: '减：租赁投资净额（现值）', amount: r.presentValue, hint: '通常≈公允价值 + 初始直接费用' },
    { label: '未确认融资收益', amount: r.unrecognizedFinIncome, hint: '最低租赁收款额 + 未担保余值 − 净投资' },
  ]
})

const reconcileRows = computed<H1G5ReconcileRow[]>(() => {
  if (!g5Seeds.value.length || !financeRows.value.length) return []
  return buildH1G5Reconcile(financeRows.value, g5Seeds.value)
})

const g5SourceLabel = computed(() => (g5Source.value ? `（来源 ${g5Source.value}）` : ''))

function onSelectRow(row: FinanceLeaseRow | null) {
  if (row) selectedId.value = row.rowId
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('资产名称', '新增融资租出', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name != null) {
    addFinanceRow()
    const last = financeRows.value[financeRows.value.length - 1]
    if (last) {
      updateFinanceCell(last.rowId, 'assetName', name)
      selectedId.value = last.rowId
    }
  }
}

function onCell(row: FinanceLeaseRow, field: keyof FinanceLeaseRow) {
  updateFinanceCell(row.rowId, field, (row as any)[field])
}

/** 行级租赁合同 OCR：📎 → contract-ocr → 确认 → 仅填空预填 */
async function handleOcr(row: FinanceLeaseRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    ocrLoadingId.value = row.rowId
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = { ...(data?.extracted_fields || {}) }
      if (data?.attachment_id) fields.attachment_id = data.attachment_id
      const preview = Object.entries(fields)
        .filter(([k, v]) => k !== 'attachment_id' && v !== '' && v != null && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
      if (!preview.length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      await ElMessageBox.confirm(`识别结果：\n${preview.join('\n')}\n\n确认填入空白字段？`, '租赁合同 OCR 识别结果', {
        confirmButtonText: '填入', cancelButtonText: '取消',
      })
      const filled = applyFinanceLeaseOcr(row.rowId, fields)
      ElMessage.success(filled.length ? `已预填 ${filled.length} 个字段` : '无可填空字段（已有值未覆盖）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('合同 OCR 失败，请稍后重试或手工录入')
    } finally {
      ocrLoadingId.value = ''
    }
  }
  input.click()
}

function handleSolveRate() {
  const row = selected.value
  if (!row) return
  if (!(row.periodCount > 0) || !(row.annualRent > 0 || row.unguaranteedResidual > 0)) {
    ElMessage.warning('请先填写各期租金、期数（及未担保余值），并确认净投资/公允价值')
    return
  }
  const rate = solveImplicitRate(row.rowId)
  if (rate == null) {
    ElMessage.error('无法求解内含利率：请检查净投资是否小于各期租金合计')
    return
  }
  ElMessage.success(`内含利率已求解为 ${rate}%`)
}

async function handlePullG5() {
  g5Loading.value = true
  try {
    const { seeds, missing, source } = await fetchG5FinanceLeaseSeeds(props.projectId)
    g5Seeds.value = seeds
    g5Source.value = source
    if (missing.includes('G5')) {
      ElMessage.warning('本项目未找到 G5 长期应收款底稿')
      return
    }
    if (!seeds.length) {
      ElMessage.warning('G5 中暂无融资租赁项目可带入（请先在 G5-5 或 G5-2 录入）')
      return
    }
    const added = importFromG5Seeds(seeds)
    if (added > 0) {
      ElMessage.success(`已从 ${source} 带入 ${added} 项（同名已存在的已跳过）`)
      const last = financeRows.value[financeRows.value.length - 1]
      if (last) selectedId.value = last.rowId
    } else {
      ElMessage.info(`G5 共 ${seeds.length} 项，均已存在于本表；已刷新勾稽对照`)
    }
  } catch (e) {
    console.warn('[H1-20] pull G5 failed', e)
    ElMessage.error('从 G5 带入失败')
  } finally {
    g5Loading.value = false
  }
}

async function handleRefreshReconcile() {
  g5Loading.value = true
  try {
    const { seeds, source } = await fetchG5FinanceLeaseSeeds(props.projectId)
    g5Seeds.value = seeds
    g5Source.value = source
    if (!seeds.length) ElMessage.warning('未获取到 G5 融资租赁数据')
    else ElMessage.success(`已刷新勾稽（${source}，${seeds.length} 项）`)
  } finally {
    g5Loading.value = false
  }
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function amortSummary({ columns, data }: { columns: any[]; data: any[] }) {
  const sums: string[] = []
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合计'; return }
    const prop = col.property
    if (prop === 'rent' || prop === 'financeIncome' || prop === 'netDecrease') {
      const total = data.reduce((s, r) => s + (Number(r[prop]) || 0), 0)
      sums[idx] = fmtAmt(total)
    } else {
      sums[idx] = ''
    }
  })
  return sums
}
</script>

<style scoped>
.h1-tab-finance-lease { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6;
  padding: 10px 14px;
  margin-bottom: 12px;
  border-radius: 4px;
  font-size: 12px;
}
.block-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.param-inline { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.ok-ratio { color: var(--el-color-success); display: flex; align-items: center; gap: 6px; }
.classification-criteria { margin-top: 16px; }
.classification-criteria h4 { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.measure-grid { margin-bottom: 12px; }
.field-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; display: flex; align-items: center; gap: 6px; }
.rate-tag { margin-left: 4px; }
.rate-row { display: flex; align-items: center; gap: 6px; }
.rate-input { flex: 1; width: auto; }
.w-full { width: 100%; }
.measure-table { margin-top: 4px; }
.formula-alert { margin-bottom: 10px; }
.error-amount { color: var(--el-color-danger); }
.summary-bar {
  display: flex;
  gap: 20px;
  flex-wrap: wrap;
  padding: 10px 12px;
  margin: 12px 0;
  background: var(--el-fill-color-light);
  border-radius: 4px;
}
.note-card { margin-top: 12px; }
.check-line { margin-bottom: 4px; }
.note-extra { margin-top: 10px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
