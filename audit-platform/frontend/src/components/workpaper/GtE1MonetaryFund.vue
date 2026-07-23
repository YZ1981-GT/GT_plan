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
      <div v-if="isProcedureSheet" class="e1-mode-toolbar">
        <el-segmented
          v-model="procedureDualMode.currentMode.value"
          :options="procedureDualMode.modeOptions"
          size="small"
          @change="procedureDualMode.onModeChange"
        />
        <el-tag v-if="!procedureDualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <GtOnlyOfficeSheet
        v-if="isProcedureSheet && procedureDualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <CycleTabProcedure
        v-else-if="currentSheet === 'E1A'"
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
      <E1TabAdjudication v-else-if="currentSheet === 'E1-1'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
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
      <E1TabCreditReport v-else-if="currentSheet === 'E1-18'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="query" />
      <!-- E1-19 企业信用报告核对 -->
      <E1TabCreditReport v-else-if="currentSheet === 'E1-19'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="check" />
      <!-- E1-20 应计利息测算 -->
      <E1TabAccruedInterest v-else-if="currentSheet === 'E1-20'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-21 银行存款截止测试 -->
      <E1TabCutoffTest v-else-if="currentSheet === 'E1-21'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="bank" />
      <!-- E1-22 其他货币资金截止测试 -->
      <E1TabCutoffTest v-else-if="currentSheet === 'E1-22'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="other" />
      <!-- E1-23 收支检查情况表 -->
      <E1TabLargeCheck v-else-if="currentSheet === 'E1-23'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" />
      <!-- E1-26~32 IPO/舞弊应对 -->
      <E1TabIpoSpecial v-else-if="ipoSheetCode" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" :sheet-code="ipoSheetCode" />
      <!-- 附注(上市) -->
      <E1TabDisclosure v-else-if="currentSheet === '附注上市'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="listed" />
      <!-- 附注(国企) -->
      <E1TabDisclosure v-else-if="currentSheet === '附注国企'" :wp-id="props.wpId" :project-id="props.projectId" :all-responses="allResponses" :save-immediate="saveImmediate" :debounced-save="debouncedSave" :is-readonly="isReadonly" :bs-date="bsDate" variant="soe" />
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

    <!-- 版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
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
import { useG1DualMode } from './composables/useG1DualMode'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

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
const allResponses: Ref<Map<string, any>> = ref(new Map())

// ─── P2#13: 全局告警面板 ─────────────────────────────────────────────────────

const globalAlerts = computed(() => {
  const alerts: Array<{ type: 'warning' | 'info' | 'success'; message: string }> = []

  // ① 审定合计 vs TB 差异
  const totalAudited = parseFloat(allResponses.value.get('E1-adj-total-1001')?.remark || '0')
    + parseFloat(allResponses.value.get('E1-adj-total-1002')?.remark || '0')
    + parseFloat(allResponses.value.get('E1-adj-total-1012')?.remark || '0')
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

const isProcedureSheet = computed(() => {
  const s = currentSheet.value
  return s === 'E1A' || s === 'E26A'
})

const procedureDualMode = useG1DualMode({ wpId: wpIdRef })

/**
 * E1-3 双 variant: sheetName 含"仅人民币"→rmb，含"人民币及外币"→multi
 */
const e13Variant = computed<'rmb' | 'multi'>(() => {
  const name = props.sheetName || ''
  if (name.includes('仅人民币')) return 'rmb'
  return 'multi'
})

/**
 * IPO 系列 sheet (E1-26~E1-32) 提取 sheetCode
 */
const ipoSheetCode = computed<string | null>(() => {
  const sheet = currentSheet.value
  const match = sheet.match(/^E1-(2[6-9]|3[0-2])$/)
  return match ? sheet : null
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.projectContext) {
    bsDate.value = props.htmlData.projectContext.bs_date || ''
    // P0#1: Seed TB amount from render strategy into allResponses for E1-1 consumption
    const tbAmount = props.htmlData.projectContext.tb_amount
    if (tbAmount && !allResponses.value.has('E1-adj-tb-amount-ending')) {
      allResponses.value.set('E1-adj-tb-amount-ending', {
        item_id: 'E1-adj-tb-amount-ending',
        conclusion: null,
        remark: String(tbAmount),
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
})
</script>

<style scoped>
.e1-monetary-fund {
  padding: 12px;
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
</style>
