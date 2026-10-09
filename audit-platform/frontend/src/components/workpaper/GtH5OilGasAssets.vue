<template>
  <div class="h5-oil-gas-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <!-- 行业适用性守卫：非 oil_gas/mining 行业 -->
    <el-empty
      v-else-if="!isApplicable"
      description="本底稿仅适用于石油天然气/采矿行业项目"
      :image-size="120"
    />

    <template v-else>
      <!--
        🔴 切换器改 `v-model` 且**不再带 `:disabled`**：原 `modeOptions` 里
        `disabled: !isOoAvailable.value` 在健康检查（mount 期异步）未就绪时把「在线编辑」
        锁死、点击被彻底吞掉 —— D4 已实证的 bug ③。健康门禁移进
        `useHSyncMode.switchMode`（await 兜底），切换器保持可点。
      -->
      <div v-if="showHtmlToolbar && currentSheet !== 'H5'" class="h5-header-toolbar">
        <el-segmented v-model="currentMode" :options="modeOptions" size="small" />
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-h5-oil-gas-assets" />
        <span class="h5-oo-tag" :class="`h5-oo-tag--${hSync.syncStateTag.value.type}`">
          {{ hSync.syncStateTag.value.text }}
        </span>
      </div>

      <!--
        受管 sheet（H5-2）的在线编辑 —— 统一双向宿主。
        🔴 `.oo-container` 必须有**确定高度**（D4 踩过 height:100% 被压成一条）。
      -->
      <div v-if="currentMode === 'onlyoffice' && isH5SyncManagedSheet" class="oo-container">
        <WorkpaperSyncEditorHost
          ref="syncEditorHostRef"
          :descriptor="hSync.descriptor.value"
          :bridge="hSync.syncBridge"
        />
      </div>

      <!-- 非受管 sheet 的 OnlyOffice 模式（legacy 只读视图，无双向回写） -->
      <GtOnlyOfficeSheet
        v-else-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        @fallback="onOoLoadFailed"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录 H5 -->
        <H5TabIndex
          v-if="currentSheet === 'H5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H5A'"
          sheet-code="H5A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H5-1 审定表 -->
        <template v-else-if="currentSheet === 'H5-1'">
          <HiFourTableSourcePanel
            v-if="props.htmlData?.hi_extraction_enabled"
            :wp-code="'H5'"
            :segments="getHiExtractionSegments('H5')"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @refresh-complete="selfLoad()"
          />
          <H5TabAdjudication
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H5-2 明细表 -->
        <H5TabDetail
          v-else-if="currentSheet === 'H5-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-3 调整分录 -->
        <H5TabAdjustment
          v-else-if="currentSheet === 'H5-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-4 闲置检查 -->
        <H5TabIdleCheck
          v-else-if="currentSheet === 'H5-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-5 会计政策（CAS27） -->
        <H5TabPolicyCheck
          v-else-if="currentSheet === 'H5-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-6 分析表 -->
        <H5TabAnalysis
          v-else-if="currentSheet === 'H5-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-7 增加检查 -->
        <H5TabAdditionCheck
          v-else-if="currentSheet === 'H5-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-8 减少检查 -->
        <H5TabDisposalCheck
          v-else-if="currentSheet === 'H5-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-9 监盘计划 -->
        <H5TabStocktakePlan
          v-else-if="currentSheet === 'H5-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-10 盘点检查 -->
        <H5TabStocktakeCheck
          v-else-if="currentSheet === 'H5-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H5-11 监盘小结 -->
        <H5TabStocktakeSummary
          v-else-if="currentSheet === 'H5-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-12 折耗测算（双分支：不含减值/含减值） -->
        <template v-else-if="currentSheet === 'H5-12'">
          <div class="depletion-branch-selector" style="margin-bottom:12px;padding:0 16px">
            <el-segmented
              v-model="depletionBranch"
              :options="[{label:'不含减值',value:'noImpair'},{label:'含减值',value:'withImpair'}]"
              size="small"
            />
          </div>
          <H5TabDepletionNoImpair
            v-if="depletionBranch === 'noImpair'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
          <H5TabDepletionWithImpair
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- H5-13 折耗分配 -->
        <H5TabDepletionAlloc
          v-else-if="currentSheet === 'H5-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-14 减值测算 -->
        <H5TabImpairment
          v-else-if="currentSheet === 'H5-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-15 可收回金额 -->
        <H5TabRecoverable
          v-else-if="currentSheet === 'H5-15'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-16 权属检查（采矿权） -->
        <H5TabTitleCheck
          v-else-if="currentSheet === 'H5-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-17 关联交易 -->
        <H5TabRelatedParty
          v-else-if="currentSheet === 'H5-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-18 经营租出 -->
        <H5TabOperatingLease
          v-else-if="currentSheet === 'H5-18'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H5-19 融资租出 -->
        <H5TabFinanceLease
          v-else-if="currentSheet === 'H5-19'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H5TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <H5TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
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

      <!-- 复核对话与版本链 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH5OilGasAssets.vue — H5 油气资产底稿主入口
 *
 * sheetName prop v-if 分发到全部21个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 行业守卫: applicable_when industry IN ['oil_gas','mining']。
 * useVersionTrail: autoSnapshot on save。
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9, 1.11
 */
import { ref, computed, onMounted, provide, toRef, inject, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { useHSyncMode } from './composables/useHSyncMode'
import { flushHPendingWrites } from './sync/hPendingWrites'

/** H5 entry id（manifest 冻结值，与 `phase5_h5_oil_gas_assets.ENTRY_ID` 逐字一致）。 */
const H5_SYNC_ENTRY_ID = 'xlsx/gt-h5-oil-gas-assets'
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载

// core — H5TabIndex 非 lazy（底稿目录轻量，首屏必显）
import H5TabIndex from './h5/core/H5TabIndex.vue'
const H5TabAdjudication = defineAsyncComponent(() => import('./h5/core/H5TabAdjudication.vue'))
const H5TabDetail = defineAsyncComponent(() => import('./h5/core/H5TabDetail.vue'))
const H5TabAdjustment = defineAsyncComponent(() => import('./h5/core/H5TabAdjustment.vue'))
const H5TabAnalysis = defineAsyncComponent(() => import('./h5/core/H5TabAnalysis.vue'))
const H5TabDisclosureListed = defineAsyncComponent(() => import('./h5/core/H5TabDisclosureListed.vue'))
const H5TabDisclosureSoe = defineAsyncComponent(() => import('./h5/core/H5TabDisclosureSoe.vue'))

// inspection
const H5TabIdleCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabIdleCheck.vue'))
const H5TabPolicyCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabPolicyCheck.vue'))
const H5TabAdditionCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabAdditionCheck.vue'))
const H5TabDisposalCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabDisposalCheck.vue'))
const H5TabTitleCheck = defineAsyncComponent(() => import('./h5/inspection/H5TabTitleCheck.vue'))
const H5TabRelatedParty = defineAsyncComponent(() => import('./h5/inspection/H5TabRelatedParty.vue'))

// stocktake
const H5TabStocktakePlan = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakePlan.vue'))
const H5TabStocktakeCheck = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakeCheck.vue'))
const H5TabStocktakeSummary = defineAsyncComponent(() => import('./h5/stocktake/H5TabStocktakeSummary.vue'))

// depletion
const H5TabDepletionNoImpair = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionNoImpair.vue'))
const H5TabDepletionWithImpair = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionWithImpair.vue'))
const H5TabDepletionAlloc = defineAsyncComponent(() => import('./h5/depletion/H5TabDepletionAlloc.vue'))

// impairment
const H5TabImpairment = defineAsyncComponent(() => import('./h5/impairment/H5TabImpairment.vue'))
const H5TabRecoverable = defineAsyncComponent(() => import('./h5/impairment/H5TabRecoverable.vue'))

// lease
const H5TabOperatingLease = defineAsyncComponent(() => import('./h5/lease/H5TabOperatingLease.vue'))
const H5TabFinanceLease = defineAsyncComponent(() => import('./h5/lease/H5TabFinanceLease.vue'))

// ─── Props & Emits ───────────────────────────────────────────────────────────
const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string
  sheetName?: string
  year?: number
  htmlData?: any
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save'): void; (e: 'completed'): void; (e: 'navigate-sheet', sheetName: string): void }>()

// ─── 行业适用性守卫 ──────────────────────────────────────────────────────────
const projectContext = inject<any>('projectContext', null)
const isApplicable = ref(true)

function checkIndustryApplicability() {
  if (!projectContext?.value && !projectContext) return // 无context默认放行
  const ctx = projectContext?.value || projectContext
  const industry = ctx?.industry || ctx?.project?.industry || ''
  if (industry && !['oil_gas', 'mining'].includes(industry)) {
    isApplicable.value = false
  }
}

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
const depletionBranch = ref<'noImpair' | 'withImpair'>('noImpair')

// ─── 双模式切换（统一接桥，替代宿主内联的第二份实现）──────────────────────────
//
// 原实现是宿主内联的 `currentMode` ref + `checkOoHealth` + `switchMode`（deletion plan 的
// `host_inlined_second_implementation` 四条之一）。它**不建桥** ⇒ OO 侧编辑回不到 HTML。
//
// 🔴 H5 的映射面很窄（10/54）：契约里 44 列判 template-only（前端 `H5DetailRow` 只 17 字段、
//    无减值也无审定口径）。接桥不改变这一点 —— 回写只动两侧真正对齐的那 10 格，
//    其余由 Excel 自己算。三条缺口见契约 `review.declared_coverage_gaps`。
const hSync = useHSyncMode({
  entryId: H5_SYNC_ENTRY_ID,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  currentCode: computed(() => currentSheet.value),
  isReadonly,
  flushHtml: async () => {
    // 🔴 H5 是 `per_tab_formdata_instance` 载体：`H5TabDetail.vue` 自己 new 一份
    //    `useH5FormData`，宿主拿不到那个实例 ⇒ 只能走模块级注册表。
    //    防抖窗口 **2s**（全 H 与 H3 并列最长），漏 flush 会静默丢最多 2 秒的编辑。
    await flushHPendingWrites()
    const snap = await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: H5_SYNC_ENTRY_ID,
    })
    return {
      expectedRevision: snap.expectedRevision,
      projection: snap.projection,
      sheetKey: hSync.sheetKey.value,
    }
  },
  reloadHtml: async () => { await selfLoad() },
})

const syncEditorHostRef = hSync.syncHostRef
const isH5SyncManagedSheet = computed(() => hSync.isManagedSheet.value)
const modeOptions = hSync.modeOptions
const currentMode = hSync.renderMode

/** legacy OO 组件加载失败的兜底（只对**非受管** sheet 生效）。 */
function onOoLoadFailed(): void {
  void hSync.switchMode('html')
}
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  // 源模板国企 sheet 名是「附注披露信息（国有企业）」——「国有企业」而非「国企」，
  // 只认「国企」会落到末尾 fallback 被误判成上市（H1 实测踩中过）
  if (/附注.*上市|H5-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有|H5-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H5A/.test(name)) return 'H5A'
  // H5-N 编码（H5-1 到 H5-19）
  const m = name.match(/(H5-\d+)/)
  if (m) return m[1]
  // 底稿目录 H5（无后缀）
  if (/底稿目录/.test(name) || (/\bH5\b/.test(name) && !/H5-/.test(name) && !/H5A/.test(name))) return 'H5'
  return ''
})

const showHtmlToolbar = computed(() => {
  return currentSheet.value !== '' && currentMode.value !== 'onlyoffice'
})

// ─── 双模式切换由 switchMode 处理 ────────────────────────────────────────────

// ─── selfLoad ────────────────────────────────────────────────────────────────
/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
}

async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H5 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h5-oil-gas-assets' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtH5OilGasAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h5VersionTrailRef', versionTrailRef)
provide('h5OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  checkIndustryApplicability()
  void selfLoad()
})
</script>

<style scoped>
.h5-oil-gas-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h5-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}

.h5-oo-tag {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 4px;
}
/*
 * 🔴 类名跟随 `useHSyncMode.syncStateTag.type`（`success|info|warning|danger`），
 *    不是原宿主内联实现的 `ready|fetching|checking|unavailable` —— 后者在接桥后
 *    一个都不会命中，标签会变成无样式裸文本（D4 踩过的样式孤儿）。
 */
.h5-oo-tag--success { background: #f0f9eb; color: #67c23a; }
.h5-oo-tag--info { background: #f4f4f5; color: #909399; }
.h5-oo-tag--warning { background: #fdf6ec; color: #e6a23c; }
.h5-oo-tag--danger { background: #fef0f0; color: #f56c6c; }

/*
 * 🔴 `height: 100%` 会被父级压成一条（D4 踩过）：OnlyOffice iframe 需要
 *    **确定**高度才撑得开，min-height 兜住父级无高度时的退化。
 */
.oo-container {
  width: 100%;
  min-height: 600px;
  height: calc(100vh - 200px);
}

.depletion-branch-selector {
  padding: 8px 16px;
}
</style>
