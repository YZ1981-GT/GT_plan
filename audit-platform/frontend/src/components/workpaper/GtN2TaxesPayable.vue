<template>
  <div class="n2-taxes-payable">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <template v-else>
      <div class="n2-taxes-payable-toolbar">
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

      <!-- N2A 程序表 → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else-if="currentSheet === 'N2A'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 底稿目录 -->
      <N2TabIndex
        v-else-if="currentSheet === 'N2' || currentSheet === '底稿目录'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- N2-1 审定表（负债类，85公式，多税种分行） -->
      <N2TabAdjudication
        v-else-if="currentSheet === 'N2-1'"
        :all-responses="allResponsesRef"
        :wp-id="wpIdRef"
        :project-id="projectIdRef"
        :is-readonly="isReadonly"
      />

      <!-- N2-2 明细表（23列区段Tab，22公式） -->
      <N2TabDetail
        v-else-if="currentSheet === 'N2-2'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-3 调整分录 -->
      <N2TabAdjustment
        v-else-if="currentSheet === 'N2-3'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-4 税收政策检查 -->
      <N2TabPolicyCheck
        v-else-if="currentSheet === 'N2-4'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-5 应交税金认定表（54×15） -->
      <N2TabRecognition
        v-else-if="currentSheet === 'N2-5'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-6 增值税测算表（48×8） -->
      <N2TabVatCalc
        v-else-if="currentSheet === 'N2-6'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-7 出口退税核对表 -->
      <N2TabExportRefund
        v-else-if="currentSheet === 'N2-7'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-8 应交其他税费测算表（26×9，11公式） -->
      <N2TabOtherTaxCalc
        v-else-if="currentSheet === 'N2-8'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-9 房产税测算表（30×7） -->
      <N2TabPropertyTax
        v-else-if="currentSheet === 'N2-9'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-10 土地增值税测算表（51×7） -->
      <N2TabLvt
        v-else-if="currentSheet === 'N2-10'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- N2-11 应交税费检查表 -->
      <N2TabTaxCheck
        v-else-if="currentSheet === 'N2-11'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注（上市） -->
      <N2TabDisclosureListed
        v-else-if="currentSheet === '附注(上市)' || currentSheet === '附注（上市）'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- 附注（国企） -->
      <N2TabDisclosureSoe
        v-else-if="currentSheet === '附注(国企)' || currentSheet === '附注（国企）'"
        :all-responses="allResponsesRef"
        :wp-id="props.wpId"
        :is-readonly="isReadonly"
      />

      <!-- 兜底：skip sheet / 未迁移 → OnlyOffice fallback -->
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
 * GtN2TaxesPayable.vue — N2 应交税费底稿主入口
 *
 * Spec: .kiro/specs/n2-taxes-payable/ Task 1.1
 * 科目: 2221应交税费（负债类/贷方）
 * sheetName 分发到 N2 专属子组件（N2-1~N2-11），N2A/O1A/出口退税额复核示例走 OnlyOffice 兜底
 * 集成：useWorkpaperVersionToolbar(autoSnapshot on save) + provide('openReviewDialog')
 * EventBus：substantive:adjudicated(2221) / tax-accrual:updated → N4
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, defineAsyncComponent } from 'vue'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { eventBus } from '@/utils/eventBus'
import http from '@/utils/http'

// ─── defineAsyncComponent lazy 加载子组件 ────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const N2TabIndex = defineAsyncComponent(() => import('./n2/core/N2TabIndex.vue'))
const N2TabAdjudication = defineAsyncComponent(() => import('./n2/core/N2TabAdjudication.vue'))
const N2TabDetail = defineAsyncComponent(() => import('./n2/core/N2TabDetail.vue'))
const N2TabAdjustment = defineAsyncComponent(() => import('./n2/core/N2TabAdjustment.vue'))
const N2TabDisclosureListed = defineAsyncComponent(() => import('./n2/core/N2TabDisclosureListed.vue'))
const N2TabDisclosureSoe = defineAsyncComponent(() => import('./n2/core/N2TabDisclosureSoe.vue'))
const N2TabPolicyCheck = defineAsyncComponent(() => import('./n2/inspection/N2TabPolicyCheck.vue'))
const N2TabRecognition = defineAsyncComponent(() => import('./n2/inspection/N2TabRecognition.vue'))
const N2TabTaxCheck = defineAsyncComponent(() => import('./n2/inspection/N2TabTaxCheck.vue'))
const N2TabVatCalc = defineAsyncComponent(() => import('./n2/calc/N2TabVatCalc.vue'))
const N2TabExportRefund = defineAsyncComponent(() => import('./n2/calc/N2TabExportRefund.vue'))
const N2TabOtherTaxCalc = defineAsyncComponent(() => import('./n2/calc/N2TabOtherTaxCalc.vue'))
const N2TabPropertyTax = defineAsyncComponent(() => import('./n2/calc/N2TabPropertyTax.vue'))
const N2TabLvt = defineAsyncComponent(() => import('./n2/calc/N2TabLvt.vue'))

// ─── Props ───────────────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  htmlData?: any
  readonly?: boolean
}>()

// ─── 状态 ────────────────────────────────────────────────────────────────────
const isLoading = ref(true)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const allResponses = ref<Map<string, any>>(new Map())
const allResponsesRef = computed(() => allResponses.value)
const isReadonly = computed(() => !!props.readonly)
const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── 双模式 ──────────────────────────────────────────────────────────────────
const dualMode = {
  currentMode: ref<'html' | 'onlyoffice'>('html'),
  modeOptions: [
    { label: 'HTML', value: 'html' },
    { label: 'OnlyOffice', value: 'onlyoffice' },
  ],
  isOoAvailable: ref(true),
  onModeChange: () => {},
}

// ─── sheetName 正则提取编码 ──────────────────────────────────────────────────
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 匹配 N2A, N2-1~N2-11, N2, 底稿目录, 附注(上市), 附注(国企) 等
  const m = name.match(/(N2A|N2-\d+|N2)/)
  if (m) return m[1]
  // 附注匹配
  if (name.includes('附注') && (name.includes('上市') || name.includes('國企'))) {
    return name.includes('上市') ? '附注(上市)' : '附注(国企)'
  }
  if (name.includes('底稿目录')) return '底稿目录'
  return name
})

/** skip sheet 列表（O1A原底稿/出口退税额复核示例走OO兜底，不做HTML组件化） */
const SKIP_SHEETS = ['O1A', '出口退税额复核示例']

/** N2-1~N2-11 为 HTML 专属组件渲染的 sheet（支持双模式切换）；N2A/skip走 OnlyOffice */
const isHtmlSheet = computed(() => {
  const s = currentSheet.value
  if (SKIP_SHEETS.some(sk => (props.sheetName || '').includes(sk))) return false
  return /^N2-\d+$/.test(s) || s === 'N2' || s === '底稿目录'
    || s.includes('附注')
})

// ─── selfLoad（bundle内嵌场景 htmlData 为 null 时自加载） ─────────────────────
async function selfLoad(): Promise<void> {
  try {
    const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
      params: { project_id: props.projectId },
    })
    const sheets = res.data?.data?.sheets || res.data?.sheets || []
    const targetSheet = sheets.find((s: any) =>
      s.sheet_name === props.sheetName || s.wp_code === props.wpCode,
    )
    if (targetSheet?.html_data) {
      // 解析 checklist_responses 到 allResponses map
      const responses = targetSheet.html_data?.checklist_responses || []
      const map = new Map<string, any>()
      for (const r of responses) {
        if (r?.item_id) map.set(r.item_id, r)
      }
      allResponses.value = map
    }
  } catch (e) {
    console.error('[N2] selfLoad failed:', e)
  }
}

// ─── provide openReviewDialog 供子组件 inject ────────────────────────────────
function openReviewDialog(sectionId: string): void {
  console.log('[N2] openReviewDialog:', sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('reloadWorkpaperData', selfLoad)

// ─── 生命周期 ────────────────────────────────────────────────────────────────
onMounted(async () => {
  // 如果 htmlData 为 null（selfLoad 场景），自行加载
  if (!props.htmlData) {
    await selfLoad()
  } else {
    // 从 htmlData 解析 checklist_responses
    const responses = props.htmlData?.checklist_responses || []
    const map = new Map<string, any>()
    for (const r of responses) {
      if (r?.item_id) map.set(r.item_id, r)
    }
    allResponses.value = map
  }
  isLoading.value = false

  // ─── EventBus 订阅 'disclosure:refresh' → 刷新数据（Task 6.1） ─────────
  eventBus.on('disclosure:refresh' as any, onDisclosureRefresh)
})

onBeforeUnmount(() => {
  // 清理 EventBus 监听
  eventBus.off('disclosure:refresh' as any, onDisclosureRefresh)
})

// ─── EventBus handler: disclosure:refresh → 重新加载数据 ─────────────────────
function onDisclosureRefresh(): void {
  selfLoad()
}

// ─── 版本快照：子组件保存后触发自动快照（六大集成标准 Task 6.3） ──────────────
provide('scheduleAutoSnapshot', versionToolbar.scheduleAutoSnapshot)
</script>

<style scoped>
.n2-taxes-payable { padding: 12px; }
.loading-container { padding: 24px; }
.n2-taxes-payable-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; }
</style>
