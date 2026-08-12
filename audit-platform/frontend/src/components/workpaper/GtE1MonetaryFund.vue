<template>
  <div class="e1-monetary-fund">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 根据外层 GtWpRenderer 传入的 sheetName 分发到对应子组件 -->
    <template v-else>
      <!-- P2#13: 全局告警面板 -->
      <template v-if="globalAlerts.length">
        <el-alert
          v-for="(alert, idx) in globalAlerts"
          :key="idx"
          :type="alert.type"
          :title="alert.message"
          :closable="false"
          style="margin-bottom: 8px"
          show-icon
        />
      </template>
      <!-- 双模式 + 版本历史 + 编制/使用手册（对齐 G1，所有 E1 底稿通用） -->
      <div class="e1-mode-toolbar">
        <el-segmented
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions.value"
          size="small"
          @change="dualMode.onModeChange"
        />
        <span class="e1-mode-divider" aria-hidden="true"></span>
        <el-button size="small" @click="openFormulaManager()">公式管理</el-button>
        <el-button size="small" @click="openHandbook('preparation')">📖 编制手册</el-button>
        <el-button size="small" @click="openHandbook('usage')">使用手册</el-button>
        <el-tag v-if="!dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 四表取数（公式管理）面板：现金/银行/账户清单明细 sheet（仅结构化视图） -->
      <E1FourTableSourcePanel
        v-if="dualMode.currentMode.value === 'html' && showFtPanel && (ftSources.length || ftHasAccountSource)"
        :sources="ftSources"
        :as-of="ftAsOf"
        :is-readonly="isReadonly"
        :has-manual-data="ftHasManualData"
        :accounts="ftAccountsForPanel"
        @re-extract="reExtractFromFourTable"
      />

      <!-- 在线编辑模式：任意 sheet 用真实 sheet_name 渲染 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="dualMode.currentMode.value === 'onlyoffice'"
        :key="props.sheetName || ''"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 结构化视图：按 sheet 分发到专属子组件 -->
      <template v-else>
      <CycleTabProcedure
        v-if="currentSheet === 'E1A'"
        sheet-code="E1A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <CycleTabProcedure
        v-else-if="currentSheet === 'E26A'"
        sheet-code="E26A"
        :html-data="props.htmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- E1-1 审定表 -->
      <E1TabAdjudication v-else-if="currentSheet === 'E1-1'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :html-data="props.htmlData" />
      <!-- E1-2 现金明细 -->
      <E1TabCashDetail v-else-if="currentSheet === 'E1-2'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-3 银行存款明细(双variant) -->
      <E1TabBankDetail v-else-if="currentSheet === 'E1-3'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :variant="e13Variant" />
      <!-- E1-4 数字货币明细 -->
      <E1TabDigitalCurrency v-else-if="currentSheet === 'E1-4'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-5 调整分录 -->
      <E1TabAdjustment v-else-if="currentSheet === 'E1-5'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-6 余额调节 -->
      <E1TabReconciliation v-else-if="currentSheet === 'E1-6'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-7 库存现金(人民币)盘点 -->
      <E1TabCashCount v-else-if="currentSheet === 'E1-7'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="rmb" />
      <!-- E1-8 库存现金(外币)盘点 -->
      <E1TabCashCount v-else-if="currentSheet === 'E1-8'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="fx" />
      <!-- E1-9 银行存单盘点 -->
      <E1TabCertificateCount v-else-if="currentSheet === 'E1-9'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-10 银行账户核对 -->
      <E1TabAccountList v-else-if="currentSheet === 'E1-10'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-11 承诺书 -->
      <E1TabAccountCommitment v-else-if="currentSheet === 'E1-11'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-14 分析表 -->
      <E1TabAnalysis v-else-if="currentSheet === 'E1-14'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-15 利息收入月度分析 -->
      <E1TabInterestAnalysis v-else-if="currentSheet === 'E1-15'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-18 企业信用报告查询 -->
      <E1TabCreditReport v-else-if="currentSheet === 'E1-18'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-19 企业信用报告信息与账面核对记录（五小节：注册资本对照/信贷类别/不一致调节/担保/关联关系） -->
      <E1TabCreditCheck v-else-if="currentSheet === 'E1-19'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-20 应计利息测算 -->
      <E1TabAccruedInterest v-else-if="currentSheet === 'E1-20'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-21 银行存款截止测试 -->
      <E1TabCutoffTest v-else-if="currentSheet === 'E1-21'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="bank" />
      <!-- E1-22 其他货币资金截止测试 -->
      <E1TabCutoffTest v-else-if="currentSheet === 'E1-22'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="other" />
      <!-- E1-23 收支检查情况表 -->
      <E1TabLargeCheck v-else-if="currentSheet === 'E1-23'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-26 现金交易分析 -->
      <E1TabCashTxnAnalysis v-else-if="currentSheet === 'E1-26'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-name="props.sheetName" />
      <!-- E1-27/28 IPO 通用表（无专属组件） -->
      <E1TabIpoSpecial v-else-if="ipoSheetCode" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-code="ipoSheetCode" />
      <!-- E1-29 银行账户分析 -->
      <E1TabBankAccountAnalysis v-else-if="currentSheet === 'E1-29'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-name="props.sheetName" />
      <!-- E1-30 存款规模与利息收入匹配性 -->
      <E1TabDepositInterestDaily v-else-if="currentSheet === 'E1-30'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-name="props.sheetName" />
      <!-- E1-31 银行流水双向核对 -->
      <E1TabBankFlowReconcile v-else-if="currentSheet === 'E1-31'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-name="props.sheetName" />
      <!-- E1-32 董监高关键岗位资金流水核查 -->
      <E1TabKeyPersonFlow v-else-if="currentSheet === 'E1-32'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-name="props.sheetName" />
      <!-- 附注(上市) -->
      <E1TabDisclosure v-else-if="currentSheet === '附注上市'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :html-data="props.htmlData" :applicable-standards="applicableStandards" variant="listed" />
      <!-- 附注(国企) -->
      <E1TabDisclosure v-else-if="currentSheet === '附注国企'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :html-data="props.htmlData" :applicable-standards="applicableStandards" variant="soe" />
      <!-- Fallback: 未匹配 → OnlyOffice (全高) -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />
      </template>
    </template>

    <!-- 版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    <!-- E1 编制/使用手册弹窗（对齐 G1） -->
    <E1PreparationHandbookDialog v-model="handbookVisible" :initial-tab="handbookTab" />
  </div>
</template>

<script setup lang="ts">
/**
 * GtE1MonetaryFund.vue — E1 货币资金底稿主入口
 *
 * 由外层 GtWpRenderer 的 sheet 目录行控制当前显示的 sheet。
 * 组件接收 sheetName prop，按 v-if 分发到对应子组件。
 * 不使用内部 el-tabs（避免双层 Tab 问题，同 D4 铁律）。
 *
 * 科目覆盖：1001 库存现金 / 1002 银行存款 / 1012 其他货币资金
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import type { Ref } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'
import { useG1DualMode } from './composables/useG1DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import E1FourTableSourcePanel from './e1/E1FourTableSourcePanel.vue'
import E1PreparationHandbookDialog from './e1/E1PreparationHandbookDialog.vue'
import {
  normalizePrefill,
  buildCashSeedRows,
  buildBankSeedRows,
  buildAccountListSeedRows,
  buildCrossSheetSeeds,
} from './composables/e1FourTablePrefill'
import {
  normalizeAccountPrefill,
  buildBankSeedRowsFromAccounts,
  buildAccountListSeedRowsFromAccounts,
  buildDigitalSeedRows,
} from './composables/e1BankAccountPrefill'

// ─── Lazy-loaded child components ────────────────────────────────────────────

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const E1TabAdjudication = defineAsyncComponent(() => import('./e1/E1TabAdjudication.vue'))
const E1TabCashDetail = defineAsyncComponent(() => import('./e1/E1TabCashDetail.vue'))
const E1TabBankDetail = defineAsyncComponent(() => import('./e1/E1TabBankDetail.vue'))
const E1TabDigitalCurrency = defineAsyncComponent(() => import('./e1/E1TabDigitalCurrency.vue'))
const E1TabAdjustment = defineAsyncComponent(() => import('./e1/E1TabAdjustment.vue'))
const E1TabReconciliation = defineAsyncComponent(() => import('./e1/E1TabReconciliation.vue'))
const E1TabCashCount = defineAsyncComponent(() => import('./e1/E1TabCashCount.vue'))
const E1TabCertificateCount = defineAsyncComponent(() => import('./e1/E1TabCertificateCount.vue'))
const E1TabAccountList = defineAsyncComponent(() => import('./e1/E1TabAccountList.vue'))
const E1TabAccountCommitment = defineAsyncComponent(() => import('./e1/E1TabAccountCommitment.vue'))
const E1TabAnalysis = defineAsyncComponent(() => import('./e1/E1TabAnalysis.vue'))
const E1TabInterestAnalysis = defineAsyncComponent(() => import('./e1/E1TabInterestAnalysis.vue'))
const E1TabCreditReport = defineAsyncComponent(() => import('./e1/E1TabCreditReport.vue'))
const E1TabAccruedInterest = defineAsyncComponent(() => import('./e1/E1TabAccruedInterest.vue'))
const E1TabCutoffTest = defineAsyncComponent(() => import('./e1/E1TabCutoffTest.vue'))
const E1TabLargeCheck = defineAsyncComponent(() => import('./e1/E1TabLargeCheck.vue'))
const E1TabIpoSpecial = defineAsyncComponent(() => import('./e1/E1TabIpoSpecial.vue'))
const E1TabDisclosure = defineAsyncComponent(() => import('./e1/E1TabDisclosure.vue'))
// ★ 孤儿组件接线 (spec: e1-orphan-components-wiring)
const E1TabCreditCheck = defineAsyncComponent(() => import('./e1/E1TabCreditCheck.vue'))
const E1TabCashTxnAnalysis = defineAsyncComponent(() => import('./e1/E1TabCashTxnAnalysis.vue'))
const E1TabBankAccountAnalysis = defineAsyncComponent(() => import('./e1/E1TabBankAccountAnalysis.vue'))
const E1TabDepositInterestDaily = defineAsyncComponent(() => import('./e1/E1TabDepositInterestDaily.vue'))
const E1TabBankFlowReconcile = defineAsyncComponent(() => import('./e1/E1TabBankFlowReconcile.vue'))
const E1TabKeyPersonFlow = defineAsyncComponent(() => import('./e1/E1TabKeyPersonFlow.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────

const isLoading = ref(false)
const isReadonly = computed(() => !!props.readonly)
const wpIdRef = computed(() => props.wpId)
const bsDate = ref('')

/**
 * 适用准则（平台单一入口）：`html_data.project_context.applicable_standards`
 * → runtime context。决定披露载荷的 `current_standard`（合并 vs 个别报表）。
 * 🔴 setup 顶层调用（内部 `inject`）。
 */
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

// ─── 编制/使用手册弹窗（对齐 G1）───────────────────────────────────────────────
const handbookVisible = ref(false)
const handbookTab = ref<'preparation' | 'usage'>('preparation')
function openHandbook(tab: 'preparation' | 'usage' = 'preparation') {
  handbookTab.value = tab
  handbookVisible.value = true
}

// ─── 公式管理（打开平台全局公式管理中心，定位到本底稿 E1）───────────────────
// 由 ThreeColumnLayout 顶层挂载的全局 FormulaManagerDialog 响应 `open-formula-manager`。
function openFormulaManager() {
  const base = (props.wpCode || 'E1').split('-')[0].toLowerCase()
  const sheet = currentSheet.value || ''
  // 具体 sheet（如 E1-1）→ 定位到该 sheet 叶子节点 wp_e1_1；非编码 sheet（附注/程序表）→ 回退父节点 wp_e1
  const nodeKey = /^[A-Za-z]+\d+-\d+$/.test(sheet)
    ? `wp_${sheet.replace(/-/g, '_').toLowerCase()}`
    : `wp_${base}`
  eventBus.emit('open-formula-manager', { nodeKey })
}
const allResponses: Ref<Map<string, any>> = ref(new Map())

// ─── 四表取数（公式管理）───────────────────────────────────────────────────
const fourTablePrefill = computed(() => normalizePrefill(props.htmlData?.four_table_prefill))
const ftAsOf = computed(() => String((fourTablePrefill.value.meta as any)?.as_of || bsDate.value || ''))

/**
 * 账户级取数（`tb_aux_balance` 的「银行账户」维度）。
 *
 * 🔴 客户的 `1002 银行存款` 在 `tb_balance` 里**不分户**（叶子恒 1 行）⇒ E1-3 逐户
 * 列示与 E1-10 账户完整性核对只能靠 aux 维度。账户级有数据时**优先**于叶子口径；
 * 全空时 `build*FromAccounts` 返 `null`，宿主自动退回叶子口径（Property 8 零回归）。
 */
const accountPrefill = computed(() => normalizeAccountPrefill(props.htmlData?.account_prefill))

/** 是否显示四表取数面板（现金/银行/账户清单/数字货币明细 sheet） */
const showFtPanel = computed(() => ['E1-2', 'E1-3', 'E1-4', 'E1-10'].includes(currentSheet.value))
/** 当前 sheet 对应的四表来源行 */
const ftSources = computed(() => {
  if (currentSheet.value === 'E1-2') return fourTablePrefill.value.cash
  if (currentSheet.value === 'E1-3') return [...fourTablePrefill.value.bank, ...fourTablePrefill.value.other]
  if (currentSheet.value === 'E1-4') return fourTablePrefill.value.digital
  if (currentSheet.value === 'E1-10') return fourTablePrefill.value.bank
  return []
})
/** 当前 sheet 是否已有持久化编制数据（决定重新取数是否提示覆盖） */
const ftRowsKey = computed(() => {
  if (currentSheet.value === 'E1-2') return 'E1-cash-detail-rows'
  if (currentSheet.value === 'E1-3') return 'E1-bank-detail-rows'
  // 🔴 E1-4 的持久化键是 `E1-digital-rows`（`E1TabDigitalCurrency.vue` 的 STORAGE_KEY），
  // 不是 `E1-digital-detail-rows` —— 后者在全前端零消费方，写进去就是孤儿键。
  if (currentSheet.value === 'E1-4') return 'E1-digital-rows'
  if (currentSheet.value === 'E1-10') return 'E1-account-list-rows'
  return ''
})
const ftHasManualData = computed(() => !!ftRowsKey.value && allResponses.value.has(ftRowsKey.value))

/**
 * 传给溯源面板的账户级载荷 —— **只有 E1-3 / E1-10 传**（那两张才按户列示）。
 *
 * 🔴 `undefined`（未传）与「传了但账户为空」是两种状态：前者面板完全不渲染账户级块，
 * 后者显示「本项目无账户级明细，已退回叶子口径」。E1-2 现金 / E1-4 数字货币没有
 * 账户维度 ⇒ 必须传 `undefined` 而不是空载荷，否则会显示一条无意义的「无账户级明细」。
 */
const ftAccountsForPanel = computed(() =>
  ['E1-3', 'E1-10'].includes(currentSheet.value) ? accountPrefill.value : undefined,
)

/** 账户级是否有数据（决定叶子来源为空时面板是否仍显示）。 */
const ftHasAccountSource = computed(() => {
  const a = ftAccountsForPanel.value
  if (!a) return false
  return (
    a.accounts.bank.length +
      a.accounts.other.length +
      a.accounts.finance_co.length +
      a.accounts.unassigned.length >
    0
  )
})

function seedRowsKey(key: string, rows: Record<string, unknown>[] | null): void {
  if (!rows || !rows.length) return
  if (allResponses.value.has(key)) return // persist-first：已有数据不覆盖
  allResponses.value.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(rows) })
}

/** 在无持久化数据时，从四表预填种子填充明细行 + 跨 sheet 聚合键（仅内存，不落库）。 */
function seedFromFourTable(): void {
  const p = fourTablePrefill.value
  const ap = accountPrefill.value
  const cashSeed = buildCashSeedRows(p)
  // 🔴 账户级优先、叶子口径兜底：`??` 只在账户级返 null（aux 无数据）时回退 ⇒
  // 账户级全空时产出与改造前逐字节相同（Property 8 零回归支点）。
  const bankSeed = buildBankSeedRowsFromAccounts(ap, e13Variant.value) ?? buildBankSeedRows(p)
  const acctSeed = buildAccountListSeedRowsFromAccounts(ap) ?? buildAccountListSeedRows(p)
  const digitalSeed = buildDigitalSeedRows(p.digital)
  seedRowsKey('E1-cash-detail-rows', cashSeed)
  seedRowsKey('E1-bank-detail-rows', bankSeed)
  seedRowsKey('E1-account-list-rows', acctSeed)
  seedRowsKey('E1-digital-rows', digitalSeed)
  // 跨 sheet 聚合键：仅当键缺失时种子（供 E1-1 审定表在未打开明细 tab 时直接取数）。
  // 注：明细行持久化时，composable 已一并持久化对应聚合键 → 此处 has() 守卫自然跳过。
  for (const { itemId, remark } of buildCrossSheetSeeds(p)) {
    if (!allResponses.value.has(itemId)) {
      allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark })
    }
  }
  // 🔴 修复历史不一致：现金明细行(E1-cash-detail-rows)有数据但聚合键被存为陈旧 0
  //（早期"打开空表→写聚合0→再种子行"竞态所致）→ E1-1 审定表读到 0 → 现金缺失 → 差异恒为现金额。
  // 从持久化的明细行权威重算聚合，仅当聚合陈旧为 0/空而行合计非 0 时纠正（不覆盖 E1-2 中的真实编辑）。
  reconcileCashAggregateFromRows()
}

/** 从持久化的现金明细行重算 E1-cash-detail 聚合键（未审期初/期末），修复陈旧 0 聚合。 */
function reconcileCashAggregateFromRows(): void {
  const rowsResp = allResponses.value.get('E1-cash-detail-rows')
  if (!rowsResp?.remark) return
  let parsed: any[]
  try { parsed = JSON.parse(rowsResp.remark) } catch { return }
  if (!Array.isArray(parsed) || parsed.length === 0) return
  const num = (v: any): number => { const n = parseFloat(String(v ?? '')); return isFinite(n) ? n : 0 }
  let opening = 0, ending = 0
  for (const r of parsed) {
    const op = num(r.opening), inc = num(r.increase), dec = num(r.decrease)
    const fx = num(r.fxRate) || 1
    opening += op
    ending += (op + inc - dec) * fx   // 未审期末（人民币）= (期初+增-减)×汇率，与 useE1CashDetail.recalcRow 一致
  }
  const corrections: Array<{ item_id: string; conclusion: null; remark: string }> = []
  const fix = (key: string, val: number): void => {
    const cur = allResponses.value.get(key)
    const curNum = cur ? parseFloat(String(cur.remark ?? '')) : NaN
    if (Math.abs(val) >= 0.005 && (!cur || !isFinite(curNum) || Math.abs(curNum) < 0.005)) {
      allResponses.value.set(key, { item_id: key, conclusion: null, remark: String(val) })
      corrections.push({ item_id: key, conclusion: null, remark: String(val) })
    }
  }
  fix('E1-cash-detail-opening-unaudited', opening)
  fix('E1-cash-detail-total-unaudited', ending)
  if (corrections.length && !isReadonly.value) {
    saveImmediate(corrections).catch(() => { /* silent：纠正持久化失败不阻断显示 */ })
  }
}

/** 重新从四表取数：以四表库最新数据覆盖当前 sheet 明细行并持久化。 */
async function reExtractFromFourTable(): Promise<void> {
  if (isReadonly.value) return
  const p = fourTablePrefill.value
  const ap = accountPrefill.value
  const key = ftRowsKey.value
  let rows: Record<string, unknown>[] | null = null
  if (currentSheet.value === 'E1-2') rows = buildCashSeedRows(p)
  // E1-3 / E1-10 与种子化同口径：账户级优先、叶子口径兜底（两处必须一致，
  // 否则「首次种子」与「重新取数」会产出两套行 id ⇒ 行数翻倍或数据错位）
  else if (currentSheet.value === 'E1-3') {
    rows = buildBankSeedRowsFromAccounts(ap, e13Variant.value) ?? buildBankSeedRows(p)
  } else if (currentSheet.value === 'E1-4') rows = buildDigitalSeedRows(p.digital)
  else if (currentSheet.value === 'E1-10') {
    rows = buildAccountListSeedRowsFromAccounts(ap) ?? buildAccountListSeedRows(p)
  }
  if (!key || !rows || !rows.length) return
  const item = { item_id: key, conclusion: null, remark: JSON.stringify(rows) }
  allResponses.value.set(key, item) // 触发 composable watch 重载
  await saveImmediate([item])
}

// ─── P2#13: 全局告警面板 ─────────────────────────────────────────────────────

const globalAlerts = computed(() => {
  const alerts: Array<{ type: 'warning' | 'info' | 'success'; message: string }> = []

  // ① 审定合计 vs TB 差异
  // 🔴 审定合计从跨sheet未审聚合键+账项调整实时计算（与 useE1Adjudication.writebackTrialBalance 的
  // 1001/1002/1012 归组口径一致），而非读 E1-adj-total-*（那些仅在审定表 flushSave 后才写，
  // 审定表未编辑时为 0 → 误报「审定合计 0.00 ≠ TB数」）。writeback 键非 0 时优先用（已编辑场景）。
  const _num = (k: string) => parseFloat(allResponses.value.get(k)?.remark || '0') || 0
  const _adj = (k: string) => _num(`E1-adjustment-by-item-${k}-ending`)
  const _wb = _num('E1-adj-total-1001') + _num('E1-adj-total-1002') + _num('E1-adj-total-1012')
  const _computed =
    (_num('E1-cash-detail-total-unaudited') + _adj('cash'))                                  // 1001
    + (_num('E1-bank-detail-principal-total-unaudited') + _adj('bank_principal'))            // 1002
    + (_num('E1-bank-detail-other-total-unaudited') + _num('E1-digital-total-unaudited')      // 1012
       + _adj('other_mf') + _adj('digital'))
  const totalAudited = Math.abs(_wb) > 0.005 ? _wb : _computed
  const tbAmount = parseFloat(allResponses.value.get('E1-adj-tb-amount-ending')?.remark || '0')
  if (tbAmount && Math.abs(totalAudited - tbAmount) > 1) {
    alerts.push({ type: 'warning', message: `E1-1 审定合计 ${totalAudited.toFixed(2)} ≠ TB数 ${tbAmount.toFixed(2)}，差异 ${(totalAudited - tbAmount).toFixed(2)}` })
  } else if (tbAmount && totalAudited) {
    alerts.push({ type: 'success', message: 'E1-1 审定合计与试算平衡表核对一致' })
  }

  // ② 账户清单疑似账外账户
  const accountListRaw = allResponses.value.get('E1-account-list-rows')?.remark
  if (accountListRaw) {
    try {
      const accountRows = JSON.parse(accountListRaw)
      const offBookCount = accountRows.filter((r: any) => r.hasBookRecord === 'N').length
      if (offBookCount > 0) {
        alerts.push({ type: 'warning', message: `E1-10 存在 ${offBookCount} 个疑似账外账户（清单有/账面无），需关注完整性认定` })
      }
    } catch { /* silent */ }
  }

  // ③ P1-9: 审定合计 vs 现金流量表期末现金勾稽提示(info级)
  // 注：E1-20(期末应计利息存量) 与 E1-15(全年利息收入流量) 属不同维度，不做直接等式勾稽以免误报。
  if (totalAudited > 0) {
    alerts.push({ type: 'info', message: `货币资金审定合计 ${totalAudited.toFixed(2)}，应与现金流量表"期末现金及现金等价物余额"勾稽（差额=受限资金+非等价物存款）` })
  }

  return alerts
})

// Save functions (passed to children; children call these for persistence + auto snapshot)
async function saveImmediate(items: any[]) {
  if (!items?.length) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items })
    scheduleAutoSnapshot()
  } catch (e) {
    console.warn('[GtE1MonetaryFund] saveImmediate failed:', e)
  }
}
function debouncedSave(items: any[]) { void saveImmediate(items) }

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('e1VersionTrailRef', versionTrailRef)
provide('e1OpenVersionHistory', openVersionHistory)

// ─── Sheet 分发逻辑 ─────────────────────────────────────────────────────────

/**
 * 当前激活的 sheet 编码。
 * GtWpRenderer 传入完整 sheet_name（如"货币资金审定表E1-1"），
 * 需提取末尾编码(E1-1)或特殊匹配(附注/E1A/E26A)。
 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''
  // E26A 须在 E1A 之前（避免误匹配）
  if (/E26A/.test(name)) return 'E26A'
  if (/E1A/.test(name)) return 'E1A'
  // 提取 E1-\d+ 格式编码
  const match = name.match(/E1-(\d+)/)
  if (match) return `E1-${match[1]}`
  // 附注特殊匹配
  if (name.includes('上市')) return '附注上市'
  if (name.includes('国企')) return '附注国企'
  return name
})

const dualMode = useG1DualMode({
  wpId: wpIdRef,
  currentSheet,
  availableSheets: computed(() => []),
  sheetName: computed(() => props.sheetName || ''),
  projectId: computed(() => props.projectId),
})

/**
 * E1-3 双 variant: sheetName 含"仅人民币"→rmb，含"人民币及外币"→multi
 */
const e13Variant = computed<'rmb' | 'multi'>(() => {
  const name = props.sheetName || ''
  if (name.includes('仅人民币')) return 'rmb'
  return 'multi'
})

/**
 * IPO 系列 sheet：只剩 E1-27/E1-28 无专属组件，走通用 E1TabIpoSpecial
 */
const ipoSheetCode = computed<string | null>(() => {
  const sheet = currentSheet.value
  const match = sheet.match(/^E1-(27|28)$/)
  return match ? sheet : null
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  // 🔴 后端 render 返回 html_data.project_context（snake_case）；此前误读 projectContext(camelCase)
  // 导致整个 seeding 块被静默跳过 → E1-1 审定表「试算平衡表数」恒空 → 差异 = 全额审定合计。
  const pctx: any = (props.htmlData as any)?.project_context ?? (props.htmlData as any)?.projectContext
  if (pctx) {
    bsDate.value = pctx.bs_date || ''
    // 期末 TB（trial_balance 审定，科目 1001/1002/1012 汇总）
    const tbEnding = pctx.tb_amount
    if (tbEnding && !allResponses.value.has('E1-adj-tb-amount-ending')) {
      allResponses.value.set('E1-adj-tb-amount-ending', {
        item_id: 'E1-adj-tb-amount-ending', conclusion: null, remark: String(tbEnding),
      })
    }
    // 期初 TB（tb_balance 期初余额叶子合计），供审定表期初核对；此前从不 seed → 期初差异恒为全额
    const tbOpening = pctx.tb_amount_opening
    if (tbOpening && !allResponses.value.has('E1-adj-tb-amount-opening')) {
      allResponses.value.set('E1-adj-tb-amount-opening', {
        item_id: 'E1-adj-tb-amount-opening', conclusion: null, remark: String(tbOpening),
      })
    }
  }
  // 从 render-config 返回的 responses_snapshot 加载已持久化数据
  const snapshot = props.htmlData?.responses_snapshot
  if (snapshot && typeof snapshot === 'object') {
    for (const [key, val] of Object.entries(snapshot)) {
      const entry = val as Record<string, unknown>
      allResponses.value.set(key, {
        item_id: String(entry?.item_id ?? key),
        conclusion: (entry?.conclusion as string | null) ?? null,
        remark: (entry?.remark as string | null) ?? null,
      })
    }
  }
  // 四表取数：无持久化数据时从四表库种子填充明细行 + 跨 sheet 聚合键（persist-first）
  seedFromFourTable()
})
</script>

<style scoped>
.e1-monetary-fund {
  padding: 12px;
}

/* ─── 模块级数值列规范（参照 E1-1 审定表）：所有子 tab 的表格统一生效 ───
   1) 右对齐数值列一律千分符+两位小数（由各 tab 的 displayPrefs.fmtAmount / 输入框 formatter 保证）
   2) 数值列防折行：单行显示 + 等宽数字（tabular-nums）对齐
   3) 数值字号比正文小 1 号（13→12px），仍放不下时最小 11px；文本列不受影响
   :deep 从主入口穿透到全部子 tab 的 el-table，无需逐个组件重复。 */
.e1-monetary-fund :deep(.el-table td.is-right .cell) {
  white-space: nowrap !important;
  font-variant-numeric: tabular-nums;
  font-size: 12px !important;
}
/* 数值列内的输入框同样单行 + 等宽数字（千分符较长时不换行） */
.e1-monetary-fund :deep(.el-table td.is-right .cell .el-input__inner),
.e1-monetary-fund :deep(.el-table td.is-right .cell .el-input-number) {
  font-variant-numeric: tabular-nums;
  font-size: 12px !important;
}

.loading-container {
  padding: 24px;
}

.e1-mode-toolbar {
  display: flex;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
}
/* 视图切换器与操作按钮之间的分隔线（避免「编制手册」等按钮被误当作切换页签） */
.e1-mode-divider {
  display: inline-block;
  width: 1px;
  height: 20px;
  background: #dcdfe6;
  margin: 0 4px;
}
/* 修复双模式页签看不清：给切换器加清晰边框「页框」，选中项深紫底+白字（原主题选中 pill 背景透明→白字浮在浅色上不可读） */
.e1-mode-toolbar :deep(.el-segmented) {
  --el-segmented-item-selected-bg-color: var(--gt-color-primary, #4b2d77);
  --el-segmented-item-selected-color: #ffffff;
  --el-segmented-item-hover-bg-color: rgba(75, 45, 119, 0.08);
  background-color: #f0edf7;        /* 浅紫灰轨道底，让整个切换器「页框」可辨 */
  border: 1px solid #cfc4e6;        /* 明确边框 */
  border-radius: 6px;
  padding: 2px;
  font-size: 13px;
}
.e1-mode-toolbar :deep(.el-segmented__item-selected) {
  background-color: var(--gt-color-primary, #4b2d77) !important;
  border-radius: 4px;
  box-shadow: 0 1px 3px rgba(75, 45, 119, 0.35);   /* 选中 pill 阴影强化立体感 */
}
.e1-mode-toolbar :deep(.el-segmented__item.is-selected),
.e1-mode-toolbar :deep(.el-segmented__item.is-selected .el-segmented__item-label) {
  color: #ffffff !important;
  font-weight: 600;                 /* 选中态加粗，白字更清晰 */
}
.e1-mode-toolbar :deep(.el-segmented__item:not(.is-selected)),
.e1-mode-toolbar :deep(.el-segmented__item:not(.is-selected) .el-segmented__item-label) {
  color: #4b2d77 !important;        /* 未选用深紫字，浅紫轨道上清晰 */
}
</style>
