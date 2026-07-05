<template>
  <div class="f5-cost-of-sales">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="f5-cost-of-sales-toolbar">
        <el-segmented
          v-if="isHtmlSheet"
          v-model="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value" size="small" type="warning">OO不可用</el-tag>
      </div>

      <!-- 双模式：HTML sheet 切到 OnlyOffice -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- F5A 程序表 → OnlyOffice -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'F5A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- F5-1 审定表（损益类专属组件） -->
      <F5TabAdjudication
        v-else-if="currentSheet === 'F5-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
      />

      <!-- F5-2 月度明细 -->
      <F5TabMonthlyDetail
        v-else-if="currentSheet === 'F5-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- F5-3 其他业务成本 -->
      <F5TabOtherCost
        v-else-if="currentSheet === 'F5-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- F5-4 调整分录 -->
      <F5TabAdjustment
        v-else-if="currentSheet === 'F5-4'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- F5-5 比较分析 -->
      <F5TabComparison
        v-else-if="currentSheet === 'F5-5'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- F5-6 数量核对 -->
      <F5TabQuantityRecon
        v-else-if="currentSheet === 'F5-6'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- F5-7 成本倒轧表 -->
      <F5TabCostRollforward
        v-else-if="currentSheet === 'F5-7'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
        :adjudicated-c-o-g-s="adjudicatedCOGS"
        :tb-data="formData.rollforwardTb.value"
      />

      <!-- F5-8 重大调整核查表 -->
      <F5TabMajorAdjustment
        v-else-if="currentSheet === 'F5-8'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
        @imported="onImported"
      />

      <!-- 兜底：未迁移 sheet → OnlyOffice -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtF5CostOfSales.vue — F5 营业成本底稿主入口
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 1.1, 9.1, 9.3
 * sheetName 分发到 F5 专属子组件（F5-1~F5-8），F5A/未迁移走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：监听 f5:save-items 持久化 + substantive:adjudicated(6401) 供 F5-7 校验区消费
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { useF5CosSalFormData } from './composables/useF5CosSalFormData'
import { useF5CosOfDualMode } from './composables/useF5CosOfDualMode'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import type { ChecklistResponse } from './composables/useF1FormData'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const F5TabAdjudication = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabAdjudication.vue'))
const F5TabMonthlyDetail = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabMonthlyDetail.vue'))
const F5TabOtherCost = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabOtherCost.vue'))
const F5TabAdjustment = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabAdjustment.vue'))
const F5TabComparison = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabComparison.vue'))
const F5TabQuantityRecon = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabQuantityRecon.vue'))
const F5TabCostRollforward = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabCostRollforward.vue'))
const F5TabMajorAdjustment = defineAsyncComponent(() => import('./f5-cost-of-sales/F5TabMajorAdjustment.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const formData = useF5CosSalFormData({ wpId: wpIdRef, projectId: projectIdRef })
const allResponsesRef = computed(() => formData.allResponses.value)
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

/** F5-7 校验区消费的审定营业成本（来自 F5-1 EventBus publish） */
const adjudicatedCOGS = ref(0)

const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  const m = name.match(/(F5A|F5-\d+)/)
  return m ? m[1] : ''
})

/** F5-1~F5-8 为 HTML 专属组件渲染的 sheet（支持双模式切换）；F5A/未匹配走 OnlyOffice */
const isHtmlSheet = computed(() => /^F5-\d+$/.test(currentSheet.value))

const dualMode = useF5CosOfDualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: () => formData.loadAll(),
})

async function onImported() {
  await formData.loadAll()
}

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[F5] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', () => formData.loadAll())

// ─── 监听 f5:save-items → 保存 + autoSnapshot ───────────────────────────────
async function handleF5SaveItems(e: Event): Promise<void> {
  const items = (e as CustomEvent<{ items: ChecklistResponse[] }>).detail?.items
  if (Array.isArray(items) && items.length > 0) {
    for (const it of items) {
      if (it?.item_id) await formData.saveImmediate(it.item_id, it)
    }
    versionToolbar.scheduleAutoSnapshot()
  }
}

// ─── 监听 substantive:adjudicated(6401) → 供 F5-7 校验区 ─────────────────────
const ADJUDICATED_KEY = 'F5-7-adjudicated-cogs'

function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; auditedAmount: number }>).detail
  if (d?.accountCode === '6401' && d.auditedAmount != null) {
    adjudicatedCOGS.value = d.auditedAmount
    // 持久化，供 F5-7 校验区在重载后仍可读取（composable 兜底读此 key）
    void formData.saveImmediate(ADJUDICATED_KEY, {
      item_id: ADJUDICATED_KEY,
      conclusion: null,
      remark: String(d.auditedAmount),
    })
  }
}

/** 从已持久化数据 seed 审定营业成本（刷新后 F5-1 未重新发布事件时的回退） */
function seedAdjudicatedFromStore(): void {
  const raw = formData.allResponses.value.get(ADJUDICATED_KEY)?.remark
  const n = raw != null && raw !== '' ? Number(raw) : NaN
  if (Number.isFinite(n)) adjudicatedCOGS.value = n
  // render 策略提供的回退值（后端读取的持久化审定成本）
  else if (formData.adjudicatedCogs.value) adjudicatedCOGS.value = formData.adjudicatedCogs.value
}

onMounted(async () => {
  window.addEventListener('f5:save-items', handleF5SaveItems)
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
  await formData.loadAll()
  seedAdjudicatedFromStore()
  isLoading.value = false
})

onBeforeUnmount(() => {
  window.removeEventListener('f5:save-items', handleF5SaveItems)
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
})
</script>

<style scoped>
.f5-cost-of-sales { padding: 12px; }
.loading-container { padding: 24px; }
.f5-cost-of-sales-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
