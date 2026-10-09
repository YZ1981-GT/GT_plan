<template>
  <div class="g7-long-term-equity-main">
    <div v-if="isLoading" class="loading-container"><el-skeleton :rows="8" animated /></div>
    <div v-else-if="loadError" class="error-container">
      <el-card shadow="never">
        <el-result icon="error" title="数据加载失败" :sub-title="loadError">
          <template #extra>
            <el-button type="primary" @click="retrySelfLoad">重试</el-button>
          </template>
        </el-result>
      </el-card>
    </div>
    <template v-else>
      <div class="g7-long-term-equity-main-toolbar">
        <!--
          🔴 切换器**不带 `:disabled`**：健康检查异步，disabled 在未就绪时会把「在线编辑」
          锁死、点击被彻底吞掉（D4 已实证的 bug ③）。门禁在 switchRenderMode 里 await 兜底。
        -->
        <el-segmented
          v-if="isHtmlSheet"
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          @change="(v: any) => switchRenderMode(v as 'html' | 'onlyoffice')"
        />
        <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        <GtEntrySyncCapabilityNotice entry-id="xlsx/gt-g7-long-term-equity-main" />
        <el-tag v-if="isSoeDisclosureSheet && syncBusy" size="small" type="info">同步中…</el-tag>
        <el-tag v-if="syncSwitching" size="small" type="info">切换中…</el-tag>
      </div>

      <!-- 合并联动 stale 常驻提示（Task 6.1） -->
      <el-alert
        v-if="linkageStale.stale.value"
        type="warning"
        :closable="false"
        show-icon
        class="g7-linkage-stale-banner"
        title="合并侧联动结果已过期，请重新联动"
        :description="linkageStale.staleSheets.value.length
          ? `受影响：${linkageStale.staleSheets.value.join('、')}`
          : ''"
      />


      <!--
        受管 sheet（附注披露信息（国企）= g7n-managed）的在线编辑 —— 统一双向宿主。
        🔴 `.oo-container` 必须有**确定高度**（D4 踩过 height:100% 被压成一条）。
      -->
      <div
        v-if="isHtmlSheet && currentMode === 'onlyoffice' && isSoeDisclosureSheet"
        class="oo-container"
      >
        <WorkpaperSyncEditorHost
          v-if="syncOoDescriptor"
          ref="syncEditorHostRef"
          :descriptor="syncOoDescriptor"
          :bridge="syncBridge"
        />
        <div v-else class="oo-loading">正在打开国企附注同步编辑器…</div>
      </div>

      <!-- 非受管 sheet 的 OnlyOffice 模式（legacy 只读视图，无双向回写） -->
      <GtOnlyOfficeSheet
        v-else-if="isHtmlSheet && currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- G7A 实质性程序表 -->
      <G7TabProcedure
        v-else-if="currentSheet === 'procedure'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-1 审定表 -->
      <G7TabAdjudication
        v-else-if="currentSheet === 'adjudication'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-2 明细表 -->
      <G7TabDetail
        v-else-if="currentSheet === 'detail'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- G7-3 调整分录汇总 -->
      <G7TabAdjustment
        v-else-if="currentSheet === 'adjustment'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 附注披露信息（上市公司） -->
      <G7TabDisclosureListed
          :applicable-standards="applicableStandards"
        v-else-if="currentSheet === 'disclosureListed'"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!--
        附注披露信息（国企）—— 受管 sheet 的 HTML 侧。
        🔴 `ref="soeTabRef"` 是接桥所需：桥的 `flushHtml` 要 await 它的 `flushPendingSave()`
        （该 Tab 是 `G7-main-disclosure-soe-v2` 的唯一写入方，防抖 600ms）。
      -->
      <G7TabDisclosureSOE
          :applicable-standards="applicableStandards"
        v-else-if="currentSheet === 'disclosureSOE'"
        ref="soeTabRef"
        :html-data="resolvedHtmlData"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :is-readonly="isReadonly"
      />

      <!-- 底稿目录 -->
      <template v-else-if="currentSheet === 'directory'">
        <div class="g7-index-toolbar">
          <el-button size="small" @click="openVersionHistory()">版本历史</el-button>
        </div>
        <G7TabDirectory
          :all-responses="g7AllResponses"
          :available-sheets="availableSheets"
        />
        <GCycleBIndexExtras
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName"
          :wp-code="'G7'"
          :html-data="resolvedHtmlData ?? undefined"
          :available-sheets="availableSheets"
          :all-responses="g7AllResponses"
        />
      </template>

      <!-- 兜底：未迁移/未匹配 sheet → OnlyOffice fallback -->
      <GtOnlyOfficeSheet
        v-else
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- 版本链/复核 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载 -->
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtG7LongTermEquityMain.vue — G7 长期股权投资底稿(main组)主入口
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 2.1
 * sheetName正则提取编码(G7A/G7-1/G7-2/G7-3/附注披露(上市)/附注披露(国企)/底稿目录) → v-if分发到7个子组件（defineAsyncComponent lazy）
 * 未匹配 → OnlyOffice fallback
 * 集成：useWorkpaperVersionToolbar(autoSnapshot) + provide('openReviewDialog') + useG7DualMode双模式切换
 * selfLoad：htmlData为null时通过useG7FormData调用render-config获取数据
 *
 * Requirements: 1.1, 1.2, 1.4, 6.3, 6.7
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, inject, defineAsyncComponent } from 'vue'
// ── G7 sync bridge（原 `usePilotBridgeAdapter` 是零 API 空壳，见下方 syncBridge 注释）──
import GtEntrySyncCapabilityNotice from './sync/GtEntrySyncCapabilityNotice.vue'
import { useWorkpaperSyncBridge, WP_BRIDGE_IN_FLIGHT_STATES } from './sync/useWorkpaperSyncBridge'
import { readStoreProjection } from './sync/workpaperSyncApi'
import { capabilityForEntry } from './sync/workpaperSyncCapability'
import WorkpaperSyncEditorHost from './sync/WorkpaperSyncEditorHost.vue'

/** G7 entry id（manifest 冻结值，与 `pilot_g7_two_level_dynamic.PILOT_ENTRY_ID` 逐字一致）。 */
const G7_SYNC_ENTRY_ID = 'xlsx/gt-g7-long-term-equity-main'
/** 受管 sheet 的契约键（与 `pilot_g7_two_level_dynamic.SHEET_KEY` 逐字一致）。 */
const G7_SOE_SHEET_KEY = 'g7n-managed'
import { useG7FormData } from './composables/useG7FormData'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useG7ConsolLinkageEntry } from './composables/g7ConsolLinkageEntry'
import { useHostApplicableStandards } from './composables/hostApplicableStandards'

// 🔴 科目码单一真源：运行态取 render 下发的 tb_source_codes（报表映射解析结果），
//    常量只作兜底。禁在本文件写字面量科目码（R11.1 / Property 15）。
import {
  g7AccountCode,
  g7ImpairmentAccountCode,
  isG7GrossCode,
} from './composables/g7AccountScope'
import type { TbSourceCodes } from './composables/shared/tbSourceCodes'

// ─── defineAsyncComponent 懒加载所有子组件 ───────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const G7TabProcedure = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabProcedure.vue'),
)
const G7TabAdjudication = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabAdjudication.vue'),
)
const G7TabDetail = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabDetail.vue'),
)
const G7TabAdjustment = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabAdjustment.vue'),
)
const G7TabDisclosureListed = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureListed.vue'),
)
const G7TabDisclosureSOE = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/disclosure/G7TabDisclosureSOE.vue'),
)
const G7TabDirectory = defineAsyncComponent(
  () => import('./g7-long-term-equity-main/core/G7TabDirectory.vue'),
)
const GCycleBIndexExtras = defineAsyncComponent(() => import('./shared/GCycleBIndexExtras.vue'))

// ─── Props ──────────────────────────────────────────────────────────────────
const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

// ─── sheetName 正则 → 编码映射 ──────────────────────────────────────────────
const SHEET_CODE_MAP: Record<string, string> = {
  'G7A': 'procedure',
  'G7-1': 'adjudication',
  'G7-2': 'detail',
  'G7-3': 'adjustment',
  '附注披露信息（上市公司）': 'disclosureListed',
  '附注披露信息（国企）': 'disclosureSOE',
  '底稿目录': 'directory',
}

const isLoading = ref(true)
const loadError = ref<string | null>(null)
const selfLoadData = ref<Record<string, any> | null>(null)
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)
const isReadonly = computed(() => !!props.readonly)

// 适用准则门控：阻止在国企项目渲染上市 Tab（反之亦然），防止同步时传错 current_standard
const applicableStandards = useHostApplicableStandards({
  htmlData: () => props.htmlData,
})

/** 提取当前sheetName对应的组件标识 */
const currentSheet = computed(() => {
  const name = props.sheetName || ''

  // 优先匹配中文sheet名
  if (name.includes('附注披露信息（上市公司）') || name.includes('附注披露(上市)') || name.includes('附注-上市')) {
    // 🔴 用户裁决（2026-08-16）：底稿侧不做准则门控，两个版本始终可编辑
    return 'disclosureListed'
  }
  if (name.includes('附注披露信息（国企）') || name.includes('附注披露(国企)') || name.includes('附注-国企')) {
    return 'disclosureSOE'
  }
  if (name.includes('底稿目录')) {
    return 'directory'
  }

  // 正则匹配：G7A
  if (/G7A/i.test(name)) {
    return 'procedure'
  }

  // 正则匹配：G7-1/G7-2/G7-3
  const codeMatch = name.match(/G7-([1-3])/)
  if (codeMatch) {
    const code = `G7-${codeMatch[1]}`
    return SHEET_CODE_MAP[code] || ''
  }

  return ''
})

/** 已迁移为HTML专属组件的sheet列表（支持双模式切换） */
const HTML_SHEETS = new Set([
  'procedure',
  'adjudication',
  'detail',
  'adjustment',
  'disclosureListed',
  'disclosureSOE',
  'directory',
])
const isHtmlSheet = computed(() => HTML_SHEETS.has(currentSheet.value))

/** 解析后的 htmlData（优先使用prop，fallback到selfLoad结果） */
const resolvedHtmlData = computed(() => props.htmlData ?? selfLoadData.value)

const availableSheets = computed(() => {
  const hd = resolvedHtmlData.value
  const fromHtml = hd?.sheets ?? hd?.render_config?.sheets
  if (Array.isArray(fromHtml) && fromHtml.length) return fromHtml
  const metaSheets = formData.renderMeta.value?.sheets
  if (Array.isArray(metaSheets) && metaSheets.length) return metaSheets
  // 对齐 G1：htmlData 无 sheets 时用自加载 render-config 的 sheetCache 兜底，
  // 保证底稿目录架构树非空
  return Object.keys(formData.sheetCache.value).map(sheet_name => ({ sheet_name }))
})

// ─── useG7FormData 用于selfLoad ─────────────────────────────────────────────
// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)

provide('g7VersionTrailRef', versionTrailRef)
provide('g7OpenVersionHistory', openVersionHistory)

const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(wpIdRef)
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

/** 目录页跳转：G7TabDirectory inject('jumpToSection') → emit('navigate-sheet') → GtWpRenderer */
const emit = defineEmits<{ 'navigate-sheet': [sheetName: string] }>()
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

const formData = useG7FormData({
  wpId: wpIdRef,
  projectId: projectIdRef,
  onAfterSave: () => scheduleAutoSnapshot(),
})
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一提供，子组件 inject 命中祖先

/** G7 allResponses Map 供目录页进度/结论看板使用 */
const g7AllResponses = computed(() => formData.data.value)

// ─── 双模式切换（真桥；原 `usePilotBridgeAdapter` 是零 API 空壳）────────────────
//
// 🔴 原实现的 docstring 声称「底层全部委派给 sync bridge」，实现里却是：`switchMode()`
//    只置 `currentMode` + 写 localStorage（**零 API 调用**）、`isOoAvailable` 硬编码
//    `ref(true)`、`ooConfig` 恒 `null`（自称「仅作兼容占位」）⇒ G7 此前**没有**真双向：
//    切 OO 渲染的是 legacy 只读 `GtOnlyOfficeSheet`，切回来只是重读 store。
//
// 🔴 更要紧的一条（本轮实测）：`WorkpaperSyncEditorHost` **自己不触发 materialize** ——
//    它只在 `descriptor !== null && bridge.mode === 'oo'` 时创建 DocEditor，而 descriptor
//    只能由 `bridge.switchToOnlyOffice()` 产出。所以「挂了宿主」≠「接了桥」；必须真调那个
//    方法。全仓现算有 27 个宿主犯了这个错（挂了却从不驱动，用户永远停在「正在打开…」），
//    已由 `sync/__tests__/bridgeMaterializeDriven.spec.ts` 钉住基线。本处按 G2/D3 范式写全。
const isSoeDisclosureSheet = computed(() => currentSheet.value === 'disclosureSOE')
/** SOE 披露 Tab 的实例引用 —— 只为拿它的 `flushPendingSave()`（切换前必须 await）。 */
const soeTabRef = ref<{ flushPendingSave: () => Promise<void> } | null>(null)
const syncEditorHostRef = ref<{ forceSave: () => Promise<{ operationId: string }> } | null>(null)

const syncBridge = useWorkpaperSyncBridge({
  entryId: ref(G7_SYNC_ENTRY_ID),
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetKey: ref(G7_SOE_SHEET_KEY),
  capability: capabilityForEntry(G7_SYNC_ENTRY_ID),
  flushHtml: async () => {
    // 🔴 先 await Tab 落库再读投影：SOE 披露的防抖窗口是 600ms，不等它
    //    materialize 出的 xlsx 会少掉最后那批编辑且无提示。
    await soeTabRef.value?.flushPendingSave()
    return await readStoreProjection({
      projectId: props.projectId,
      wpId: props.wpId,
      entryId: G7_SYNC_ENTRY_ID,
    })
  },
  reloadHtml: async () => {
    await formData.load()
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed as Record<string, any>
    }
  },
})

const syncOoDescriptor = computed(() => syncBridge.descriptor.value)
const syncBusy = computed(() =>
  (WP_BRIDGE_IN_FLIGHT_STATES as readonly string[]).includes(String(syncBridge.state.value)),
)
const syncSwitching = ref(false)

/** 渲染模式：受管 sheet 以**桥**为真源，非受管 sheet 用本地 ref（legacy 只读视图）。 */
const legacyOoMode = ref(false)
const currentMode = computed<'html' | 'onlyoffice'>(() =>
  isSoeDisclosureSheet.value
    ? (syncBridge.mode.value === 'oo' ? 'onlyoffice' : 'html')
    : (legacyOoMode.value ? 'onlyoffice' : 'html'),
)
const modeOptions = [
  { label: '结构化视图', value: 'html' as const },
  { label: '在线编辑', value: 'onlyoffice' as const },
]

/**
 * 四分支保存协议（照 D3/F3/G2 同构）。
 *
 * 🔴 切换器**不带 `:disabled`**：健康检查是异步的，disabled 在未就绪时会把「在线编辑」
 *    锁死、点击被彻底吞掉（D4 已实证的 bug ③）。
 */
async function switchRenderMode(target: 'html' | 'onlyoffice'): Promise<void> {
  if (target === currentMode.value || syncSwitching.value) return
  // 非受管 sheet：只切 legacy 只读视图，不建桥
  if (!isSoeDisclosureSheet.value) {
    legacyOoMode.value = target === 'onlyoffice'
    return
  }
  syncSwitching.value = true
  try {
    if (target === 'onlyoffice') {
      // ① HTML → OO：桥内部先 flushHtml（await Tab 落库）→ pending → materialize → descriptor
      await syncBridge.switchToOnlyOffice()
      return
    }
    if (syncBridge.mode.value !== 'oo') return
    if (String(syncBridge.state.value) === 'applied') {
      // ② 改动已落库 ⇒ 只重载，不再发保存 ⇒ 秒切
      await syncBridge.reloadAfterApplied()
    } else if (!syncBridge.dirty.value) {
      // ③ 未改动 ⇒ clean close，不发强制保存 ⇒ 丝滑
      await syncBridge.leaveWithoutSaving()
    } else if (syncBridge.canForcesave.value && syncEditorHostRef.value) {
      // ④ 有改动 ⇒ 强制保存（慢是允许的，用户没先保存）
      await syncEditorHostRef.value.forceSave()
    } else {
      await syncBridge.switchToHtml()
    }
  } catch {
    // 失败保持当前视图；错误已由桥写入 lastError / feedback（fail visible）
  } finally {
    syncSwitching.value = false
  }
}

// ─── 合并联动 stale 常驻提示（Task 6.1，只读；失败静默降级 Property 12）────
const auditYear = computed<number>(() => {
  const ctx = (resolvedHtmlData.value?.project_context ?? {}) as Record<string, any>
  const y = ctx.audit_year ?? ctx.auditYear
  if (y) return Number(y)
  const bs = ctx.bs_date ?? ctx.bsDate
  if (typeof bs === 'string' && bs.length >= 4) return Number(bs.slice(0, 4))
  return new Date().getFullYear()
})
const linkageStale = useG7ConsolLinkageEntry(projectIdRef, auditYear)
function handleLinkageChanged(): void {
  void linkageStale.refreshStale()
}

/** 四表取数溯源（render 下发；snake_case 为准，camelCase 回退） */
const tbSourceCodes = computed<TbSourceCodes | null>(() => {
  const ctx = (resolvedHtmlData.value?.project_context
    ?? resolvedHtmlData.value?.projectContext
    ?? {}) as Record<string, any>
  const raw = ctx.tb_source_codes ?? ctx.tbSourceCodes
  return raw && typeof raw === 'object' ? (raw as TbSourceCodes) : null
})
provide('g7TbSourceCodes', tbSourceCodes)

// spec: tb-writeback-explicit-publish-gate Task 12：移除 handleG7Adjudicated 的 TB 回写旁路
// —— 原「审定表保存后 substantive:adjudicated{writebackTb:true} → formData.writebackTB(1511/1512)」
// 是绕过显式确认门的自动写（违反 Req 1/2）。TB 回写改由 G7-1 审定表「发布到试算表」显式确认门
// （G7TabAdjudication.handlePublishToTb → 单次 POST publish-to-tb 双科目原子发布）承载。

// ─── selfLoad 模式：htmlData 为 null 时自动获取数据 ─────────────────────────
async function selfLoadInit(): Promise<void> {
  if (props.htmlData != null) return
  try {
    await formData.load()
    const parsed = formData.parseContent()
    if (parsed && Object.keys(parsed).length > 0) {
      selfLoadData.value = parsed as Record<string, any>
    }
  } catch (err: any) {
    loadError.value = err?.message || '加载渲染配置失败'
  }
}

async function retrySelfLoad(): Promise<void> {
  loadError.value = null
  isLoading.value = true
  await selfLoadInit()
  isLoading.value = false
}

// ─── 生命周期 ───────────────────────────────────────────────────────────────
onMounted(async () => {
  window.addEventListener('g7:linkage-changed', handleLinkageChanged)
  await selfLoadInit()
  isLoading.value = false
  void linkageStale.refreshStale()
})

onBeforeUnmount(() => {
  window.removeEventListener('g7:linkage-changed', handleLinkageChanged)
})
</script>

<style scoped>
.g7-long-term-equity-main { padding: 12px; }
.loading-container { padding: 24px; }
.error-container { padding: 24px; }
.g7-long-term-equity-main-toolbar { margin-bottom: 8px; display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

/*
 * 🔴 `height: 100%` 会被父级压成一条（D4 踩过）：OnlyOffice iframe 需要
 *    **确定**高度才撑得开，min-height 兜住父级无高度时的退化。
 */
.oo-container { width: 100%; min-height: 600px; height: calc(100vh - 200px); }
.oo-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 400px;
  color: var(--el-text-color-secondary);
}
.g7-index-toolbar { display: flex; gap: 8px; align-items: center; margin-bottom: 12px; }
</style>
