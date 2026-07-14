<template>
  <div class="h6-asset-disposal-clearing">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 过渡科目状态栏 -->
      <div
        class="h6-transit-status-bar"
        :class="transitAccountStatus.isZero ? 'status-green' : 'status-red'"
      >
        <span v-if="transitAccountStatus.isZero">
          ✓ 所有清理已结转
        </span>
        <span v-else>
          ⚠ 存在未结转项目，余额：{{ transitAccountStatus.balance }}元
        </span>
      </div>

      <!-- 顶部工具栏（双模式切换） -->
      <div class="h6-header-toolbar">
        <el-segmented
          v-model="currentMode"
          :options="modeOptions"
          size="small"
          :disabled="!isOoAvailable && currentMode === 'html'"
          @change="onModeChange"
        />
      </div>

      <!-- OnlyOffice 模式 -->
      <GtOnlyOfficeSheet
        v-if="currentMode === 'onlyoffice'"
        :wp-id="props.wpId"
        :project-id="props.projectId"
        :sheet-name="props.sheetName || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 180px)"
      />

      <!-- HTML 结构化视图 -->
      <template v-else>
        <!-- 底稿目录 -->
        <H6TabIndex
          v-if="currentSheet === 'H6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :transit-account-status="transitAccountStatus"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H6A 程序表（selfLoad） -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'H6A'"
          sheet-code="H6A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H6-1 审定表（过渡科目59公式+期末应为零） -->
        <H6TabAdjudication
          v-else-if="currentSheet === 'H6-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（上市公司） -->
        <H6TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（国有企业） -->
        <H6TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H6-2 明细表（25列2区块） -->
        <H6TabDetail
          v-else-if="currentSheet === 'H6-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H6-3 调整分录汇总 -->
        <H6TabAdjustment
          v-else-if="currentSheet === 'H6-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H6-4 检查表（清理过程检查） -->
        <H6TabCheck
          v-else-if="currentSheet === 'H6-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
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
 * GtH6AssetDisposalClearing.vue — H6 固定资产清理底稿主入口
 *
 * sheetName prop v-if 分发到7个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * 过渡科目状态栏: 期末余额=0→绿色；≠0→红色告警。
 * useVersionTrail: autoSnapshot on save。
 * 双模式: HTML↔OnlyOffice切换+OO健康检查。
 *
 * 科目: 1606固定资产清理（借方/资产类，过渡科目）
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 1.1
 * Requirements: 1.1, 1.2, 1.6, 1.7, 1.8, 1.9
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, inject, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
// 版本 Host 由 Runtime Boundary(GtWpRenderer) 统一挂载
const GtAProgramConsole = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// core
const H6TabIndex = defineAsyncComponent(() => import('./h6/core/H6TabIndex.vue'))
const H6TabAdjudication = defineAsyncComponent(() => import('./h6/core/H6TabAdjudication.vue'))
const H6TabDetail = defineAsyncComponent(() => import('./h6/core/H6TabDetail.vue'))
const H6TabAdjustment = defineAsyncComponent(() => import('./h6/core/H6TabAdjustment.vue'))
const H6TabDisclosureListed = defineAsyncComponent(() => import('./h6/core/H6TabDisclosureListed.vue'))
const H6TabDisclosureSoe = defineAsyncComponent(() => import('./h6/core/H6TabDisclosureSoe.vue'))

// inspection
const H6TabCheck = defineAsyncComponent(() => import('./h6/inspection/H6TabCheck.vue'))

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

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())

// ─── 过渡科目状态（期末余额应为0） ──────────────────────────────────────────
const transitAccountStatus = computed(() => {
  // 从 allResponses 中提取 H6-1 审定表期末余额
  const endBalanceStr = allResponses.value.get('H6-1-end-balance-audited')
  const balance = parseFloat(endBalanceStr) || 0
  return {
    isZero: balance === 0,
    balance,
  }
})

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
const currentMode = ref<'html' | 'onlyoffice'>('html')
const isOoAvailable = ref(true)
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]

function onModeChange(_val: string | number): void {
  // Phase 3 will integrate useH6DualMode with OO health check
}

/** 从 sheetName 提取编码 (H6/H6A/H6-1~H6-4/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H6A/.test(name)) return 'H6A'
  // H6-N 编码（H6-1 到 H6-4）
  const m = name.match(/(H6-\d+)/)
  if (m) return m[1]
  // 底稿目录 H6（无后缀）
  if (/底稿目录/.test(name) || (/\bH6\b/.test(name) && !/H6-/.test(name) && !/H6A/.test(name))) return 'H6'
  return ''
})

// ─── selfLoad ────────────────────────────────────────────────────────────────
/** 合并一个 responses 对象（{item_id: {...}}）到目标 Map */
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  for (const [k, v] of Object.entries(src)) map.set(k, v)
}

async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H6 render 策略实际输出）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h6-asset-disposal-clearing' },
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
    console.warn('[GtH6AssetDisposalClearing] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── 子组件 save 持久化（Bug C 修复：子 tab 此前仅写内存 Map，从不落库 → 刷新丢数据） ──
// 子组件通过 inject('saveResponse') 调用；防抖 800ms 批量 PUT /checklist-responses。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(itemId: string, value: any): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = { ...existing, item_id: itemId, remark: strVal }
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtH6] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h6VersionTrailRef', versionTrailRef)
provide('h6OpenVersionHistory', openVersionHistory)

// ─── EventBus: H6-2 Detail接口（供外部事件调用） ─────────────────────────────
/**
 * H6-2 明细表的 createFromH1Disposal 方法引用。
 * 由 H6TabDetail 组件在 mounted 时通过 provide/inject 或直接 expose 注册。
 * 这里用一个函数引用来实现主入口对H6-2 composable的间接调用。
 */
const _h6DetailCreateFn = ref<((payload: { assetName: string; originalCost: number; accDep: number; refH1Code: string }) => void) | null>(null)

/** 注册 H6-2 的 createFromH1Disposal 函数（由子组件调用） */
function registerDetailCreateFn(fn: (payload: { assetName: string; originalCost: number; accDep: number; refH1Code: string }) => void): void {
  _h6DetailCreateFn.value = fn
}
provide('registerDetailCreateFn', registerDetailCreateFn)

// ─── EventBus: Subscribe 'h1:disposal-completed' (H1-8→H6自动创建行) ─────────
/**
 * 当H1-8减少检查发布 'h1:disposal-completed' 事件时，
 * H6自动为每个处置项创建H6-2明细行。
 * 事件payload: { rows: [{name, originalCost, netValue, ...}], totalGainLoss }
 * Requirement 5.3
 */
function _handleDisposalInitiated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (!detail) return

  const rows: any[] = detail.rows ?? []
  if (rows.length === 0) return

  // 逐行创建 H6-2 明细
  let created = 0
  for (const row of rows) {
    const assetName = row.name || row.assetName || '未命名资产'
    const originalCost = Number(row.originalCost) || 0
    const accDep = Number(row.accDep ?? row.accumulatedDepreciation ?? (originalCost - (Number(row.netValue) || 0))) || 0
    const refH1Code = row.assetNo ? `H1-8-${row.assetNo}` : (row.refH1Code || '')

    if (_h6DetailCreateFn.value) {
      _h6DetailCreateFn.value({ assetName, originalCost, accDep, refH1Code })
      created++
    }
  }

  if (created > 0) {
    ElMessage.success(`已从H1-8减少检查自动创建${created}项清理明细`)
  }
}

// ─── EventBus: Subscribe 'disposal:source-updated' (H1数据更新刷新) ──────────
function _handleDisposalSourceUpdated(_e: Event): void {
  // H1源数据更新时刷新H6，保持数据同步
  void selfLoad()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  // Subscribe: TB updates → refresh H6-1 取数 when trial_balance changes externally
  window.addEventListener('tb:updated', _handleTbUpdated)
  // Subscribe: 其他底稿审定数变更 → 刷新H6（仅1606科目相关）
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
  // Subscribe: H1-8减少检查处置完成 → 自动创建H6-2清理明细行 (Req 5.3)
  window.addEventListener('h1:disposal-completed', _handleDisposalInitiated)
  // Subscribe: H1源数据更新 → 刷新
  window.addEventListener('disposal:source-updated', _handleDisposalSourceUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
  window.removeEventListener('h1:disposal-completed', _handleDisposalInitiated)
  window.removeEventListener('disposal:source-updated', _handleDisposalSourceUpdated)
  for (const t of _saveTimers.values()) clearTimeout(t)
})

/**
 * TB更新事件处理：当试算表外部更新时（如其他底稿回写），刷新H6数据。
 * 过滤：仅科目1606相关的更新触发刷新（避免无关科目刷新噪音）。
 */
function _handleTbUpdated(e: Event) {
  const detail = (e as CustomEvent).detail
  // 仅在科目1606相关或无明确科目信息时刷新
  if (!detail || !detail.accountCode || detail.accountCode === '1606' || detail.wpCode === 'H6') {
    void selfLoad()
  }
}
</script>

<style scoped>
.h6-asset-disposal-clearing {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h6-transit-status-bar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  border-radius: 4px;
  margin: 8px 16px;
}

.h6-transit-status-bar.status-green {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #c2e7b0;
}

.h6-transit-status-bar.status-red {
  background: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fbc4c4;
}

.h6-header-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-fill-color-blank);
}
</style>
