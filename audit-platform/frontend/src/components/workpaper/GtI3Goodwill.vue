<template>
  <div class="i3-goodwill">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet && currentSheet !== 'I3'" class="i3-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          :model-value="dualMode.currentMode.value"
          :options="dualMode.modeOptions"
          size="small"
          @change="dualMode.onModeChange"
        />
        <el-tag v-if="isHtmlSheet && !dualMode.isOoAvailable.value && !dualMode.checking.value" size="small" type="info">仅结构化视图</el-tag>
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="isHtmlSheet && dualMode.currentMode.value === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else-if="dualMode.currentMode.value === 'html'">
        <!-- 底稿目录 I3 -->
        <I3TabIndex
          v-if="currentSheet === 'I3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3A 程序表 → OO fallback（程序表） -->
        <GtOnlyOfficeSheet
          v-else-if="currentSheet === 'I3A'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />

        <!-- I3-1 审定表（66公式，商誉不摊销！） -->
        <I3TabAdjudication
          v-else-if="currentSheet === 'I3-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-2 明细表（原值/减值双表滚动） -->
        <I3TabDetail
          v-else-if="currentSheet === 'I3-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- I3-3 调整分录汇总 -->
        <I3TabAdjustment
          v-else-if="currentSheet === 'I3-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-4 入账价值测算表 -->
        <I3TabInitialValue
          v-else-if="currentSheet === 'I3-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-5 针对性检查表 -->
        <I3TabTargetedCheck
          v-else-if="currentSheet === 'I3-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-6 商誉减值测试（CGU分摊） -->
        <I3TabImpairmentTest
          v-else-if="currentSheet === 'I3-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-7 可收回金额测试（对齐致同 Excel：公允净额 + DCF/CAPM） -->
        <I3TabRecoverableTest
          v-else-if="currentSheet === 'I3-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I3-8 复核公司减值测试过程及结论（对齐 Excel 1~11 + 二） -->
        <I3TabReviewProcess
          v-else-if="currentSheet === 'I3-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市公司） -->
        <I3TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
          :cross-sheet-auto-fill="crossSheet.disclosureAutoFill.value"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（国有企业） -->
        <I3TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :applicable-standards="applicableStandards"
          :cross-sheet-auto-fill="crossSheet.disclosureAutoFill.value"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 市场平均收益率参考数据 → OO fallback -->
        <GtOnlyOfficeSheet
          v-else-if="currentSheet === '参考数据'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />

        <!-- 未匹配 → OnlyOffice fallback -->
        <GtOnlyOfficeSheet
          v-else
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />
      </template>

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtI3Goodwill.vue — I3 商誉底稿主入口
 *
 * sheetName prop v-if 分发到全部11个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 *
 * 商誉核心特殊：
 * - 不摊销！仅年度减值测试
 * - 期末=期初+新并购-减值（只减不增）
 * - DCF资产组(CGU)模型
 * - 减值先冲商誉再分摊至资产组其他资产
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent, inject} from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useI3DualMode } from './composables/useI3DualMode'
import { useI3CrossSheet } from './composables/useI3CrossSheet'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
const I3TabIndex = defineAsyncComponent(() => import('./i3/core/I3TabIndex.vue'))
const I3TabAdjudication = defineAsyncComponent(() => import('./i3/core/I3TabAdjudication.vue'))
const I3TabDetail = defineAsyncComponent(() => import('./i3/core/I3TabDetail.vue'))
const I3TabAdjustment = defineAsyncComponent(() => import('./i3/core/I3TabAdjustment.vue'))
const I3TabInitialValue = defineAsyncComponent(() => import('./i3/core/I3TabInitialValue.vue'))
const I3TabTargetedCheck = defineAsyncComponent(() => import('./i3/core/I3TabTargetedCheck.vue'))
const I3TabDisclosureListed = defineAsyncComponent(() => import('./i3/core/I3TabDisclosureListed.vue'))
const I3TabDisclosureSoe = defineAsyncComponent(() => import('./i3/core/I3TabDisclosureSoe.vue'))

// impairment
const I3TabImpairmentTest = defineAsyncComponent(() => import('./i3/impairment/I3TabImpairmentTest.vue'))
const I3TabRecoverableTest = defineAsyncComponent(() => import('./i3/impairment/I3TabRecoverableTest.vue'))
const I3TabReviewProcess = defineAsyncComponent(() => import('./i3/impairment/I3TabReviewProcess.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

const runtimeCtx = inject(WorkpaperRuntimeContextKey, null)
const applicableStandards = computed<string[]>(() => {
  const fromProp = props.applicableStandards
  if (Array.isArray(fromProp) && fromProp.length) return fromProp
  const fromRuntime = (runtimeCtx as any)?.applicableStandards?.value
  if (Array.isArray(fromRuntime) && fromRuntime.length) return fromRuntime
  const fromHtml = props.htmlData?.applicableStandards
  return Array.isArray(fromHtml) ? fromHtml : []
})

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
const tbData = ref({
  unadjusted1711: 0,
  audited1711: 0,
})

// 跨 sheet 联动（供子页 inject）
const crossSheet = useI3CrossSheet(allResponses)
provide('i3CrossSheet', crossSheet)
provide('i3AllResponses', allResponses)

// ─── 双模式 useI3DualMode (OO 健康检查 + el-segmented) ──────────────────────
const wpIdRef = computed(() => props.wpId)
const dualMode = useI3DualMode({
  wpId: wpIdRef,
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { void selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/** 从 sheetName 提取编码 (I3/I3A/I3-1~I3-8/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|国有企业/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表 I3A
  if (/I3A/.test(name)) return 'I3A'
  // 市场平均收益率(参考数据) → OO fallback
  if (/市场平均收益率/.test(name)) return '参考数据'
  // I3-N 编码（I3-1 到 I3-8）
  const m = name.match(/(I3-\d+)/)
  if (m) return m[1]
  // 底稿目录 I3（无后缀）
  if (/底稿目录/.test(name) || (/\bI3\b/.test(name) && !/I3-/.test(name) && !/I3A/.test(name))) return 'I3'
  return ''
})

// ─── 子组件 save 回调（持久化 checklist_responses） ────────────────────────────
async function handleChildSave(itemId: string, value: any): Promise<void> {
  if (!props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  // 乐观更新本地 Map
  allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: strVal })
  try {
    await http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: null, remark: strVal }],
    })
  } catch (err: any) {
    const msg = err?.response?.data?.detail || err?.response?.data?.message || err?.message || '保存失败'
    console.error('[GtI3Goodwill] save failed:', itemId, err)
    ElMessage.error(`底稿保存失败（${itemId}）：${msg}`)
  }
}

// ─── TB自动取数（1711 商誉） ─────────────────────────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '1711' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u1711 = 0, a1711 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('1711')) {
        u1711 += Number(item.unadjusted_amount ?? 0)
        a1711 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted1711: u1711, audited1711: a1711 }
  } catch {
    // TB取数失败静默处理
  }
}

// ─── selfLoad ────────────────────────────────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      if (props.htmlData.allResponses) {
        const map = new Map<string, any>()
        for (const [k, v] of Object.entries(props.htmlData.allResponses)) {
          map.set(k, v)
        }
        allResponses.value = map
      }
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'i3-goodwill' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          if (sheet.html_data?.allResponses) {
            for (const [k, v] of Object.entries(sheet.html_data.allResponses)) {
              map.set(k, v)
            }
          }
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtI3Goodwill] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide（真实复核对话）

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('i3VersionTrailRef', versionTrailRef)
provide('i3OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.i3-goodwill {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.i3-header-toolbar {
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  display: flex;
  align-items: center;
  gap: 12px;
}
</style>
