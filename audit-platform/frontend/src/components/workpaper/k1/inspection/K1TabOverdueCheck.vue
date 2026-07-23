<!--
  K1TabOverdueCheck.vue — K1-10 长期未收回款项检查表

  对齐致同源模板：审计目标 + 长期未收回明细（15列）+ 审计说明 + 结论
  增强：期末公式、账龄枚举、K1-2 导入、Stage 建议、风险高亮
-->
<template>
  <div class="k1-audit-sheet" data-testid="k1-overdue-check">
    <details class="compile-hint open-hint">
      <summary>编制提示（CSRC 551-9）</summary>
      <ul>
        <li>本表检查账龄较长、长期未收回的其他应收款：按债务人列示期初/借贷/期末，说明未收回原因与处理计划。</li>
        <li>期末余额 = 期初余额 + 本期借方 − 本期贷方（灰底自动）；审定余额可「同步净值」（期末 − 坏账准备）。</li>
        <li>可从 K1-2 导入账龄超 1 年明细；期后收款凭证检查索引 K1-12；重大无法收回应衔接 K1-7/K1-8。</li>
        <li>账龄较长的其他应收款，判断是否长期挂账推迟正常开支或无需支付，必要时函证（551-9）。</li>
      </ul>
    </details>

    <div class="section-head">
      <h3 class="sheet-title">K1-10 长期未收回款项检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
        <el-button v-if="!isReadonly" size="small" @click="addRow()">＋ 新增</el-button>
        <el-button v-if="!isReadonly" size="small" @click="onImportFromDetail">从 K1-2 导入超1年</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :loading="postPaymentLoading"
          @click="onImportPostPayment"
        >取期后回款</el-button>
        <el-button v-if="!isReadonly" size="small" type="warning" plain @click="onSyncStagesToK17">同步 Stage → K1-7</el-button>
        <span class="muted">账龄口径</span>
        <el-select
          :model-value="agingPresetModel"
          size="small"
          style="width: 110px"
          :disabled="isReadonly"
          @change="onAgingPresetChange"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
          <el-option label="自定义" value="CUSTOM" />
        </el-select>
        <el-tag size="small" type="info">共 {{ dataRows.length }} 行</el-tag>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应收款、坏账准备是存在的，且已记录于恰当的账户；</li>
        <li><b>计价和分摊：</b>其他应收款、坏账准备以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录，披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <el-alert
      v-if="provisionReconciliation.hasK18Data"
      :type="provisionReconciliation.isBookMatch ? 'success' : 'warning'"
      :closable="false"
      class="recon-bar"
    >
      <template #title>
        <span>K1-8 坏账勾稽：本表计提合计 {{ fmtAmt(provisionReconciliation.k110ProvisionTotal) }} ·
          K1-8 账面准备 {{ fmtAmt(provisionReconciliation.k18BookTotal) }} ·
          差异 {{ fmtAmt(provisionReconciliation.diffVsBook) }}
          <span v-if="Math.abs(provisionReconciliation.diffVsExpected) >= 0.01" class="muted">
            （vs 应计提 {{ fmtAmt(provisionReconciliation.k18ExpectedTotal) }}，差 {{ fmtAmt(provisionReconciliation.diffVsExpected) }}）
          </span>
        </span>
      </template>
      <p v-if="provisionReconciliation.rowMismatches.length" class="recon-detail">
        逐户差异：{{ provisionReconciliation.rowMismatches.map(m => `${m.debtorName}(${fmtAmt(m.diffVsBook)})`).join('、') }}
      </p>
    </el-alert>
    <el-alert v-else type="info" :closable="false" class="recon-bar" title="完成 K1-8 坏账测算后可自动勾稽本表计提合计" />

    <el-dialog v-model="showCustomDialog" title="自定义账龄段" width="420px" destroy-on-close>
      <p class="muted">每行一个段名，至少 2 段、最多 10 段。</p>
      <el-input v-model="customInput" type="textarea" :rows="8" placeholder="1年以内&#10;1-2年&#10;2-3年&#10;3年以上" />
      <template #footer>
        <el-button @click="cancelCustomAging">取消</el-button>
        <el-button type="primary" @click="confirmCustomAging">确定</el-button>
      </template>
    </el-dialog>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">二、长期未收回款项明细</span></template>
      <el-alert
        v-if="deeplinkHint"
        type="info"
        :closable="false"
        show-icon
        class="deeplink-bar"
      >
        <template #title>
          <span>{{ deeplinkHint }}</span>
          <el-button size="small" link type="primary" style="margin-left: 8px" @click="clearDeeplink">清除筛选</el-button>
        </template>
      </el-alert>
      <div class="filter-bar">
        <el-input v-model="searchFilter" placeholder="搜索债务人..." size="small" clearable class="search-input" />
        <span v-if="searchFilter.trim()" class="filter-hint">显示 {{ filteredDataRows.length }} / {{ dataRows.length }} 户</span>
      </div>
      <el-table
        ref="tableRef"
        :data="tableRows"
        row-key="id"
        border
        size="small"
        :max-height="460"
        class="audit-table"
        :row-class-name="rowClassName"
      >
        <el-table-column label="#" width="42" align="center">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)">—</span>
            <span v-else>{{ row.seq }}</span>
          </template>
        </el-table-column>
        <el-table-column label="债务人名称" min-width="150" fixed>
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-label">{{ row.debtorName }}</span>
            <div v-else class="debtor-cell">
              <el-input
                :model-value="row.debtorName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.id, 'debtorName', v)"
              />
              <el-tooltip v-if="row.debtorName.trim()" content="跳转 K1-2 明细表">
                <el-button
                  link
                  type="primary"
                  size="small"
                  class="jump-btn"
                  @click="navigateToDetail(row)"
                >→</el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="105" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.openingBalance) }}</span>
            <el-input-number
              v-else
              :model-value="row.openingBalance"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'openingBalance', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="本期借方发生额" min-width="115" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.periodDebit) }}</span>
            <el-input-number
              v-else
              :model-value="row.periodDebit"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'periodDebit', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="本期贷方发生额" min-width="115" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.periodCredit) }}</span>
            <el-input-number
              v-else
              :model-value="row.periodCredit"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'periodCredit', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末 = 期初 + 借方 − 贷方">{{ fmtAmt(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="110">
          <template #default="{ row }">
            <el-select
              v-if="!isMetaRow(row)"
              :model-value="row.aging"
              size="small"
              :disabled="isReadonly"
              filterable
              allow-create
              clearable
              placeholder="选择账龄"
              @change="(v: string) => updateCell(row.id, 'aging', v ?? '')"
            >
              <el-option v-for="opt in agingOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="Stage建议" width="92" align="center">
          <template #default="{ row }">
            <el-tag
              v-if="!isMetaRow(row) && getStageSuggestion(row) !== 'none'"
              size="small"
              :type="stageTagType(getStageSuggestion(row))"
              effect="plain"
            >{{ getStageSuggestion(row) }}</el-tag>
            <span v-else-if="!isMetaRow(row)" class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="经济业务说明" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.businessDesc"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'businessDesc', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="未收回或未结转的原因" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.unrecoveredReason"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'unrecoveredReason', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="是否诉讼" width="88" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isMetaRow(row)"
              :model-value="row.litigation"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => updateCell(row.id, 'litigation', v ?? '')"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="是否无法收回" width="108" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isMetaRow(row)"
              :model-value="row.isUncollectible"
              size="small"
              :disabled="isReadonly"
              clearable
              @change="(v: string) => updateCell(row.id, 'isUncollectible', v ?? '')"
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
        <el-table-column label="处理计划" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.actionPlan"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'actionPlan', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="计提坏账准备金额" min-width="120" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.provision) }}</span>
            <el-input-number
              v-else
              :model-value="row.provision"
              :controls="false"
              size="small"
              class="amt"
              :class="{ 'provision-warn': isProvisionMismatch(row.debtorName) }"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'provision', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="审定余额" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.auditedBalance) }}</span>
            <div v-else class="audited-cell">
              <el-input-number
                :model-value="row.auditedBalance"
                :controls="false"
                size="small"
                class="amt"
                :disabled="isReadonly"
                @update:model-value="(v: number) => updateCell(row.id, 'auditedBalance', v ?? 0)"
              />
              <el-button
                v-if="!isReadonly"
                link
                type="primary"
                size="small"
                title="审定余额 = 期末 − 坏账准备"
                @click="syncAuditedFromNet(row.id)"
              >同步</el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="期后收款金额" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.postPeriodCollection) }}</span>
            <el-input-number
              v-else
              :model-value="row.postPeriodCollection"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'postPeriodCollection', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.remark"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'remark', v)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!isMetaRow(row)"
              size="small"
              type="danger"
              link
              @click="removeRow(row.id)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-summary">
        长期挂账 {{ summary.longTermCount }} 笔 ·
        涉诉 {{ summary.litigationCount }} 笔 ·
        无法收回/部分 {{ summary.uncollectibleCount }} 笔 ·
        审定合计 {{ fmtAmt(summary.auditedBalance) }} ·
        期后收款 {{ fmtAmt(summary.postPeriodCollection) }}
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、审计说明</span>
          <el-button v-if="!isReadonly" size="small" type="primary" link :loading="aiLoading" @click="onAiAuditNote">AI 生成</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="（1）抽样/全查范围；（2）长期未收回原因与处理计划；（3）期后收款验证，详见 K1-12 凭证检查；（4）坏账准备衔接 K1-8，拟调整事项索引 K1-1"
        @change="persistTextFields()"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-select
        v-model="conclusionOption"
        :disabled="isReadonly"
        size="small"
        class="concl-select"
        placeholder="选择结论模板"
        @change="onConclusionOption"
      >
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="形成审计结论..."
        @change="persistTextFields()"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** K1TabOverdueCheck.vue — K1-10 长期未收回款项检查表 | Req 8.x */
import { computed, inject, toRef, ref, onMounted, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import {
  useK1OverdueCheck,
  UNCOLLECTIBLE_OPTIONS,
  type K1OverdueCheckRow,
} from '../../composables/useK1OverdueCheck'
import {
  K1RowNavigationKey,
  applyK1IncomingFocus,
  buildK1DeeplinkHint,
} from '../../composables/useK1RowNavigation'
import { K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import type { AgingPreset } from '@/composables/useAgingConfig'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  bsDate?: string
  year?: number
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
const { generateAndConfirm, loading: aiLoading } = useK1AiGenerate(toRef(props, 'wpId'))
const searchFilter = ref('')
const deeplinkHint = ref('')
const tableRef = ref<InstanceType<typeof ElTable>>()

const uncollectibleOptions = UNCOLLECTIBLE_OPTIONS

const overdueApi = useK1OverdueCheck({
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  bsDate: computed(() => props.bsDate || ''),
  year: computed(() => props.year),
  onSave: (itemId, payload) => {
    props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: payload.remark })
    emit('save', itemId, payload)
  },
})

const {
  auditNote,
  conclusion,
  conclusionOption,
  dataRows,
  displayRows,
  summary,
  provisionReconciliation,
  agingOptions,
  agingPreset,
  customSegments,
  isMetaRow,
  isLongTerm,
  addRow,
  removeRow,
  updateCell,
  setAgingPreset,
  syncAuditedFromNet,
  importFromDetail,
  importPostPaymentFromLedger,
  postPaymentLoading,
  syncStagesToK17,
  persistTextFields,
  getStageSuggestion,
  resolveOverdueStage,
} = overdueApi

const filteredDataRows = computed(() => {
  const keyword = searchFilter.value.trim().toLowerCase()
  if (!keyword) return dataRows.value
  return dataRows.value.filter((r) => String(r.debtorName ?? '').toLowerCase().includes(keyword))
})

const tableRows = computed(() => {
  if (searchFilter.value.trim()) return filteredDataRows.value
  return displayRows.value
})

onMounted(() => {
  applyIncomingFocus()
})

function applyIncomingFocus(): void {
  applyK1IncomingFocus({
    sheet: 'K1-10',
    k1Nav,
    rows: dataRows.value,
    nameOf: (r) => (r as K1OverdueCheckRow).debtorName,
    onResolved: (resolved, focus) => {
      searchFilter.value = resolved.counterparty
      deeplinkHint.value = buildK1DeeplinkHint(focus, resolved.counterparty)
      if (resolved.rowId) {
        k1Nav?.focusRow(resolved.rowId)
        scrollToRow(resolved.rowId)
      }
    },
  })
}

function scrollToRow(rowId: string): void {
  if (!rowId) return
  nextTick(() => {
    const root = tableRef.value?.$el as HTMLElement | undefined
    const rowEl = root?.querySelector(`tr[data-row-key="${rowId}"]`) as HTMLElement | null
    rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function clearDeeplink(): void {
  searchFilter.value = ''
  deeplinkHint.value = ''
}

const agingPresetModel = computed(() => agingPreset.value)
const showCustomDialog = ref(false)
const customInput = ref('')
const lastNonCustomPreset = ref<AgingPreset>(
  agingPreset.value === 'CUSTOM' ? 'THREE_YEAR' : agingPreset.value,
)

function navigateToDetail(row: K1OverdueCheckRow) {
  const name = row.debtorName.trim()
  if (!name) {
    ElMessage.warning('请先填写债务人名称')
    return
  }
  if (k1Nav) {
    k1Nav.navigateToRow({
      sheet: 'K1-2',
      rowId: row.sourceRowId || undefined,
      counterparty: name,
      sourceSheet: 'K1-10',
    })
    return
  }
  emit('navigate-sheet', 'K1-2 明细表')
}

function onImportFromDetail() {
  const r = importFromDetail()
  if (r.imported + r.updated === 0) {
    ElMessage.warning('K1-2 中未找到账龄超 1 年的明细')
  } else {
    ElMessage.success(`已导入 ${r.imported} 行、更新 ${r.updated} 行（按债务人合并）`)
  }
}

async function onImportPostPayment() {
  await importPostPaymentFromLedger()
}

function onSyncStagesToK17() {
  const r = syncStagesToK17()
  if (r.added + r.upgraded === 0) {
    ElMessage.info('无需要写入 K1-7 的阶段升级信号')
  } else {
    ElMessage.success(`已同步 K1-7：新增 ${r.added} 户、升级 ${r.upgraded} 户`)
  }
}

function isProvisionMismatch(debtorName: string): boolean {
  return provisionReconciliation.value.rowMismatches.some((m) => m.debtorName === debtorName.trim())
}

function onAgingPresetChange(val: AgingPreset) {
  if (val === 'CUSTOM') {
    const labels = customSegments.value.length
      ? customSegments.value.map((s) => s.label)
      : agingOptions.value
    customInput.value = (labels.length ? labels : ['1年以内', '1-2年', '2-3年', '3年以上']).join('\n')
    showCustomDialog.value = true
    return
  }
  lastNonCustomPreset.value = val
  setAgingPreset(val)
}

function confirmCustomAging() {
  const lines = customInput.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (!setAgingPreset('CUSTOM', lines.slice(0, 10))) return
  showCustomDialog.value = false
}

function cancelCustomAging() {
  showCustomDialog.value = false
  if (!customSegments.value.length && agingPreset.value === 'CUSTOM') {
    setAgingPreset(lastNonCustomPreset.value)
  }
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) {
    conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  }
  persistTextFields()
}

function rowClassName({ row }: { row: K1OverdueCheckRow }) {
  const parts: string[] = []
  if (isMetaRow(row)) parts.push('row-subtotal')
  else {
    const hl = k1Nav?.rowHighlightClass(row.id)
    if (hl) parts.push(hl)
    if (row.isUncollectible === '是' || row.litigation === '是') parts.push('row-uncollectible')
    else if (isLongTerm(row) || row.isUncollectible === '部分') parts.push('row-long-term')
  }
  return parts.join(' ')
}

function stageTagType(stage: string): 'info' | 'warning' | 'danger' {
  if (stage === 'Stage3') return 'danger'
  if (stage === 'Stage2') return 'warning'
  return 'info'
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function onAiAuditNote() {
  const content = await generateAndConfirm('overdue-eval', auditNote.value, {
    rowCount: dataRows.value.length,
    longTermCount: summary.value.longTermCount,
    litigationCount: summary.value.litigationCount,
    uncollectibleCount: summary.value.uncollectibleCount,
    auditedBalance: summary.value.auditedBalance,
  }, 'AI 生成 K1-10 审计说明')
  if (content) {
    auditNote.value = content
    persistTextFields()
  }
}

function handleReview() { openReviewDialog('K1-10-overdue') }
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.audit-objective { margin-bottom: 10px; }
.recon-bar { margin-bottom: 10px; }
.recon-detail { margin: 4px 0 0; font-size: 12px; line-height: 1.5; }
.provision-warn :deep(.el-input__wrapper) { box-shadow: 0 0 0 1px var(--el-color-warning) inset; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell, .subtotal-val { font-variant-numeric: tabular-nums; }
.subtotal-label { font-weight: 600; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-variant-numeric: tabular-nums; }
.audit-table :deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.audit-table :deep(.row-subtotal) { background: #fafafa !important; font-weight: 600; }
.audit-table :deep(.row-long-term) { background: #fdf6ec !important; }
.debtor-cell { display: flex; align-items: center; gap: 4px; }
.debtor-cell :deep(.el-input) { flex: 1; min-width: 0; }
.jump-btn { flex-shrink: 0; padding: 0 2px; font-weight: 600; }
.audit-table :deep(.row-uncollectible) { background: #fef0f0 !important; }
.audit-table :deep(.k1-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: k1-row-flash 1.2s ease-in-out 0s 2; }
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
.deeplink-bar { margin-bottom: 8px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.search-input { width: 220px; }
.filter-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.audited-cell { display: flex; flex-direction: column; gap: 2px; }
.table-summary { margin-top: 8px; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-bottom: 10px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
.open-hint { border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
</style>
