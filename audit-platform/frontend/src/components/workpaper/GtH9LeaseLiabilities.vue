<template>
  <div class="h9-lease-liabilities">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- H8联动状态指示栏 -->
      <div
        class="h9-h8-linkage-bar"
        :class="h8LinkageStatus.isConsistent ? 'status-green' : 'status-red'"
      >
        <span v-if="h8LinkageStatus.isConsistent">
          ✓ H9-H8联动一致
        </span>
        <span v-else>
          ⚠ {{ h8LinkageStatus.message }}
        </span>
      </div>

      <!-- 顶部工具栏（双模式切换）— 目录页隐藏 -->
      <div v-if="currentSheet !== 'H9'" class="h9-header-toolbar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          @change="switchMode"
          size="small"
        />
        <el-tag v-if="ooHealthChecking" size="small" type="info">检测中...</el-tag>
        <el-tag v-else-if="isOoAvailable" size="small" type="success">OnlyOffice 拉取成功</el-tag>
        <el-tag v-else size="small" type="warning">仅结构化视图</el-tag>
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
        <H9TabIndex
          v-if="currentSheet === 'H9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :h8-linkage-status="h8LinkageStatus"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H9A 程序表 -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'H9A'"
          sheet-code="H9A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H9-1 审定表（负债类双区块：租赁负债+未确认融资费用） -->
        <template v-else-if="currentSheet === 'H9-1'">
          <HiFourTableSourcePanel
            v-if="props.htmlData?.hi_extraction_enabled"
            :wp-code="'H9'"
            :segments="getHiExtractionSegments('H9')"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @refresh-complete="selfLoad()"
          />
          <H9TabAdjudication
            @save="persistResponse"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
          />
        </template>

        <!-- 附注披露信息（上市公司） -->
        <H9TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（国企） -->
        <H9TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H9-2 租赁负债明细表 -->
        <H9TabDetail
          v-else-if="currentSheet === 'H9-2'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H9-3 未确认融资费用明细表 -->
        <H9TabFinanceCost
          v-else-if="currentSheet === 'H9-3'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H9-4 调整分录汇总 -->
        <H9TabAdjustment
          v-else-if="currentSheet === 'H9-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 摊销表（纯前端计算视图，核心！） -->
        <H9TabAmortization
          v-else-if="currentSheet === '摊销表'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H9-6 关联方检查（筛选视图，无物理sheet） -->
        <H9TabRelatedParty
          v-else-if="currentSheet === 'H9-6'"
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtH9LeaseLiabilities.vue — H9 租赁负债底稿主入口
 *
 * sheetName prop v-if 分发到子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * H8联动状态栏: 初始确认一致→绿色；不一致→红色告警。
 * 双模式: HTML↔OnlyOffice切换（useH9DualMode composable 后续创建）。
 *
 * 科目: 2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）
 * CAS21核心: H9初始确认 ≈ H8初始 - 直接费用 + 激励
 * 配对底稿: 与H8使用权资产强联动
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent, inject} from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { applyH8TerminationToH92Rows } from './composables/useH9Detail'
import { useH9CrossSheet } from './composables/useH9CrossSheet'
import HiFourTableSourcePanel from './shared/HiFourTableSourcePanel.vue'
import { getHiExtractionSegments } from './composables/hiExtractionSegments'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtAProgramConsole = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// core/
const H9TabIndex = defineAsyncComponent(() => import('./h9/core/H9TabIndex.vue'))
const H9TabAdjudication = defineAsyncComponent(() => import('./h9/core/H9TabAdjudication.vue'))
const H9TabDetail = defineAsyncComponent(() => import('./h9/core/H9TabDetail.vue'))
const H9TabFinanceCost = defineAsyncComponent(() => import('./h9/core/H9TabFinanceCost.vue'))
const H9TabAdjustment = defineAsyncComponent(() => import('./h9/core/H9TabAdjustment.vue'))
const H9TabDisclosureListed = defineAsyncComponent(() => import('./h9/core/H9TabDisclosureListed.vue'))
const H9TabDisclosureSoe = defineAsyncComponent(() => import('./h9/core/H9TabDisclosureSoe.vue'))

// amortization/ (纯前端计算视图，无物理xlsx sheet)
const H9TabAmortization = defineAsyncComponent(() => import('./h9/amortization/H9TabAmortization.vue'))

// inspection/
const H9TabRelatedParty = defineAsyncComponent(() => import('./h9/inspection/H9TabRelatedParty.vue'))

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

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())

// ─── H8联动状态（与 useH9CrossSheet 统一多键兜底）──────────────────────────
const { h9VsH8Linkage } = useH9CrossSheet(allResponses)
const h8LinkageStatus = computed(() => {
  const link = h9VsH8Linkage.value
  // 未加载时不刷红（与 H8 父栏一致）
  if (!link.isConsistent && /未加载/.test(link.message)) {
    return { isConsistent: true, diff: 0, message: '' }
  }
  return {
    isConsistent: link.isConsistent,
    diff: link.diff,
    message: link.isConsistent ? '' : link.message,
  }
})

// ─── 双模式切换（拉取成功才允许切 OnlyOffice） ──────────────────────────────
const currentMode = ref<'html' | 'onlyoffice'>('html')
const isOoAvailable = ref(false)
const ooHealthChecking = ref(true)

const modeOptions = computed(() => [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !isOoAvailable.value },
])

/** 健康检查（拉取成功才解锁在线编辑） */
async function checkOoHealth() {
  ooHealthChecking.value = true
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    const data = res?.data ?? res
    isOoAvailable.value = !!(data?.healthy ?? data?.data?.healthy)
  } catch {
    isOoAvailable.value = false
  } finally {
    ooHealthChecking.value = false
  }
}

/** 切换模式：OO 不可用时阻断 */
function switchMode(val: 'html' | 'onlyoffice') {
  if (val === 'onlyoffice' && !isOoAvailable.value) return
  currentMode.value = val
}

// ─── sheetName → 编码提取 ────────────────────────────────────────────────────
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'H9'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  // 程序表 H9A
  if (/H9A/.test(name)) return 'H9A'
  // H9-N 编码（H9-1 到 H9-4）
  const m = name.match(/(H9-\d+)/)
  if (m) return m[1]
  // 明细表（无编码命中时用关键字匹配）
  if (/租赁负债明细/.test(name)) return 'H9-2'
  if (/未确认融资费用明细/.test(name)) return 'H9-3'
  if (/调整分录/.test(name)) return 'H9-4'
  // 摊销表（纯前端计算视图，无物理sheet）
  if (/摊销表/.test(name)) return '摊销表'
  // 关联方检查（筛选视图，无物理sheet）
  if (/关联/.test(name) || /H9-6/.test(name)) return 'H9-6'
  // H9（无后缀，底稿目录）
  if (/底稿目录/.test(name) || (/\bH9\b/.test(name) && !/H9-/.test(name) && !/H9A/.test(name))) return 'H9'
  return ''
})

// ─── selfLoad / reloadFromServer ─────────────────────────────────────────────
function _mergeResponses(map: Map<string, any>, src: any): void {
  if (!src || typeof src !== 'object') return
  // 注入权威 item_id：dict 值缺 item_id 时以键补齐（否则保存 items 缺 item_id 触发 422）；v 自带 item_id 则以其为准
  for (const [k, v] of Object.entries(src)) map.set(k, (v && typeof v === 'object' && !Array.isArray(v)) ? { item_id: k, ...v } : { item_id: k, remark: v })
}

/** 强制从服务端拉最新 checklist（忽略父级 htmlData 快照）— IE 导入后必用 */
async function fetchResponsesFromServer(): Promise<Map<string, any>> {
  const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
    params: { force_component_type: 'h9-lease-liabilities' },
    _silent: true,
  } as any)
  const data = res.data?.data || res.data
  const map = new Map<string, any>()
  if (data?.sheets && Array.isArray(data.sheets)) {
    for (const sheet of data.sheets) {
      _mergeResponses(map, sheet.html_data?.allResponses)
      _mergeResponses(map, sheet.html_data?.responses_snapshot)
    }
  }
  return map
}

async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses（首屏快路径）
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      allResponses.value = await fetchResponsesFromServer()
    }
  } catch (err) {
    console.warn('[GtH9LeaseLiabilities] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

/** IE 导入 / 跨表事件后：必须打服务端，避免 htmlData 快照导致 UI 假旧 */
async function reloadFromServer(): Promise<void> {
  try {
    allResponses.value = await fetchResponsesFromServer()
  } catch (err) {
    console.warn('[GtH9LeaseLiabilities] reloadFromServer failed:', err)
  }
}

// ─── 子组件 save 持久化（Bug C 修复：子 tab emit('save') 此前无人接线 → 数据不落库） ──
// 子组件契约：emit('save', itemId, value)。value 为字符串或对象（对象序列化进 remark）。
// 防抖 800ms 批量 PUT /checklist-responses，并乐观更新本地 Map 供 selfLoad/跨表读取。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(itemId: string, value: any): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const updated = { ...existing, item_id: itemId, remark: strVal }
  // 替换 Map 引用以触发依赖 allResponses 的 computed / watch（对齐 H8）
  const next = new Map(allResponses.value)
  next.set(itemId, updated)
  allResponses.value = next
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    const conclusionRaw = updated.conclusion
    const conclusion =
      conclusionRaw == null || String(conclusionRaw).trim() === ''
        ? null
        : String(conclusionRaw)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtH9] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H9] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)
provide('h9ReloadAll', reloadFromServer)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h9VersionTrailRef', versionTrailRef)
provide('h9OpenVersionHistory', openVersionHistory)

// ─── H8联动: 终止合同标记 + 落库 H9-2 ───────────────────────────────────────
const terminatedContractIds = ref<Set<string>>(new Set())
provide('terminatedContractIds', terminatedContractIds)

function _handleH8LeaseTerminated(e: Event): void {
  const detail = (e as CustomEvent)?.detail || {}
  const cn = String(detail.contractNo || detail.contractId || '').trim()
  if (!cn) return
  terminatedContractIds.value.add(cn)

  // 直接落库 H9-2（不依赖明细 tab 是否挂载）
  const item = allResponses.value.get('H9-2-rows')
  let rawRows: any[] = []
  try {
    const raw = item?.remark ?? item?.conclusion
    rawRows = typeof raw === 'string' ? JSON.parse(raw) : (Array.isArray(raw) ? raw : [])
  } catch { rawRows = [] }
  const { rows: next, matched } = applyH8TerminationToH92Rows(rawRows, {
    contractNo: cn,
    reductionDate: detail.reductionDate,
    settle: true,
  })
  if (matched > 0) {
    persistResponse('H9-2-rows', next)
  }
  void reloadFromServer()
}

function _handleH8Updated(e: Event): void {
  const detail = (e as CustomEvent)?.detail || {}
  // H8-2 persist 推送的 CAS21 镜像键 → 落库 H9-h8-*，供本页勾稽
  const h8Initial = Number(detail.h8InitialMeasurement)
  const direct = Number(detail.h8DirectCost)
  const incentive = Number(detail.h8Incentive)
  if (Number.isFinite(h8Initial) && h8Initial !== 0) {
    persistResponse('H9-h8-initial-measurement', h8Initial)
  }
  if (Number.isFinite(direct)) {
    persistResponse('H9-h8-direct-cost', direct)
  }
  if (Number.isFinite(incentive)) {
    persistResponse('H9-h8-incentive', incentive)
  }
  void reloadFromServer()
}

function _handleTbUpdated(_payload?: unknown): void {
  void reloadFromServer()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  void checkOoHealth()
  // Subscribe: TB / 审定更新（经 crossWpEventBridge 双通道）
  window.addEventListener('tb:updated', _handleTbUpdated)
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
  eventBus.on('substantive:adjudicated', _handleTbUpdated)
  eventBus.on('trial-balance:updated', _handleTbUpdated)
  // Subscribe: H8租赁终止 → 标记已终止合同
  window.addEventListener('h8:lease-terminated', _handleH8LeaseTerminated)
  // Subscribe: H8数据更新 → 刷新H9联动
  window.addEventListener('h8:asset-updated', _handleH8Updated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
  eventBus.off('substantive:adjudicated', _handleTbUpdated)
  eventBus.off('trial-balance:updated', _handleTbUpdated)
  window.removeEventListener('h8:lease-terminated', _handleH8LeaseTerminated)
  window.removeEventListener('h8:asset-updated', _handleH8Updated)
  for (const t of _saveTimers.values()) clearTimeout(t)
})
</script>

<style scoped>
.h9-lease-liabilities {
  padding: 0;
}

.loading-container {
  padding: 24px;
}

.h9-h8-linkage-bar {
  padding: 8px 16px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  display: flex;
  align-items: center;
  gap: 8px;
}

.h9-h8-linkage-bar.status-green {
  background: #f0f9eb;
  border: 1px solid #b3e19d;
  color: #67c23a;
}

.h9-h8-linkage-bar.status-red {
  background: #fef0f0;
  border: 1px solid #fbc4c4;
  color: #f56c6c;
}

.h9-header-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  padding: 8px 16px;
  margin-bottom: 8px;
}
</style>
