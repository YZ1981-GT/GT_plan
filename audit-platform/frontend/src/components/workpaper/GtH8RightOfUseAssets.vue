<template>
  <div class="h8-right-of-use-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- H9联动状态指示栏 -->
      <div
        class="h8-h9-linkage-bar"
        :class="h9LinkageStatus.isConsistent ? 'status-green' : 'status-red'"
      >
        <span v-if="h9LinkageStatus.isConsistent">
          ✓ H8-H9联动一致
        </span>
        <span v-else>
          ⚠ {{ h9LinkageStatus.message }}
        </span>
      </div>

      <!-- 顶部工具栏（双模式切换） -->
      <div class="h8-header-toolbar">
        <el-segmented
          v-model="currentMode"
          :options="modeOptions"
          size="small"
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
        <!-- 底稿目录 H8 -->
        <H8TabIndex
          v-if="currentSheet === 'H8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :h9-linkage-status="h9LinkageStatus.status"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8A 程序表 -->
        <GtAProgramConsole
          v-else-if="currentSheet === 'H8A'"
          sheet-code="H8A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H8-1 审定表（四区块：原值/折旧/减值/净额 + H8-3 账项回写） -->
        <H8TabAdjudication
          v-else-if="currentSheet === 'H8-1'"
          @save="persistResponse"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（上市公司） -->
        <H8TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露信息（国有企业） -->
        <H8TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H8-2 明细表（源模板58列→原值/折旧/减值4区段） -->
        <H8TabDetail
          v-else-if="currentSheet === 'H8-2'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-3 调整分录汇总（Excel列+调整分录模块双向联动+A13/H8-1） -->
        <H8TabAdjustment
          v-else-if="currentSheet === 'H8-3'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="props.year"
        />

        <!-- H8-4 租赁的识别（段落型90行：§1~5+提示抽屉） -->
        <H8TabLeaseIdentification
          v-else-if="currentSheet === 'H8-4'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-5 租赁期的确定（段落型52行） -->
        <H8TabLeaseTerm
          v-else-if="currentSheet === 'H8-5'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-6 使用权资产初始及后续计量（按年/按月双分支） -->
        <div v-else-if="currentSheet === 'H8-6'" class="h8-branch-container">
          <div class="h8-branch-selector">
            <el-segmented
              v-model="measurementBranch"
              :options="measurementBranchOptions"
              size="default"
            />
          </div>
          <H8TabMeasurementAnnual
            v-if="measurementBranch === '按年计量'"
            @save="persistResponse"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
          <H8TabMeasurementMonthly
            v-else
            @save="persistResponse"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </div>

        <!-- H8-7 租赁变更（100行11列） -->
        <H8TabLeaseModification
          v-else-if="currentSheet === 'H8-7'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-8 折旧测算表（不含减值/含减值双分支） -->
        <div v-else-if="currentSheet === 'H8-8'" class="h8-branch-container">
          <div class="h8-branch-selector">
            <el-segmented
              v-model="depreciationBranch"
              :options="depreciationBranchOptions"
              size="default"
              @change="onDepreciationBranchChange"
            />
            <span class="branch-hint">{{ depreciationBranch === '含减值' ? '已计提减值：按减值日分段重算月折旧' : '未计提减值：直线法全期同率' }}</span>
          </div>
          <H8TabDepreciationNoImpair
            v-if="depreciationBranch === '不含减值'"
            @save="persistResponse"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            :branch="depreciationBranch"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
          <H8TabDepreciationWithImpair
            v-else
            @save="persistResponse"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            :branch="depreciationBranch"
            @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
          />
        </div>

        <!-- H8-9 折旧分配分析表 -->
        <H8TabDepreciationAlloc
          v-else-if="currentSheet === 'H8-9'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-10 减值测算表 -->
        <H8TabImpairment
          v-else-if="currentSheet === 'H8-10'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-11 可收回金额测试表 -->
        <H8TabRecoverable
          v-else-if="currentSheet === 'H8-11'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-12 减少检查表（租赁终止） -->
        <H8TabDisposalCheck
          v-else-if="currentSheet === 'H8-12'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-13 简化处理的租赁检查表 -->
        <H8TabSimplifiedCheck
          v-else-if="currentSheet === 'H8-13'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H8-14 关联交易检查表 -->
        <H8TabRelatedParty
          v-else-if="currentSheet === 'H8-14'"
          @save="persistResponse"
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
 * GtH8RightOfUseAssets.vue — H8 使用权资产底稿主入口
 *
 * sheetName prop v-if 分发到18个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * H9联动状态栏: 初始计量一致→绿色；不一致→红色告警。
 * H8-6分支选择器: el-segmented("按年计量"/"按月计量")
 * H8-8分支选择器: el-segmented("不含减值"/"含减值")
 * useVersionTrail: autoSnapshot on save。
 * 双模式: HTML↔OnlyOffice切换。
 *
 * 科目: 1901使用权资产（借方/资产类）+ 累计折旧（贷方/备抵类）
 * CAS21核心: H8=H9+直接费用-激励
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent, inject} from 'vue'
import http from '@/utils/http'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useH8CrossSheet } from './composables/useH8CrossSheet'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))
const GtAProgramConsole = defineAsyncComponent(() => import('./GtCycleAProgramRouter.vue'))

// core/
const H8TabIndex = defineAsyncComponent(() => import('./h8/core/H8TabIndex.vue'))
const H8TabAdjudication = defineAsyncComponent(() => import('./h8/core/H8TabAdjudication.vue'))
const H8TabDetail = defineAsyncComponent(() => import('./h8/core/H8TabDetail.vue'))
const H8TabAdjustment = defineAsyncComponent(() => import('./h8/core/H8TabAdjustment.vue'))
const H8TabDisclosureListed = defineAsyncComponent(() => import('./h8/core/H8TabDisclosureListed.vue'))
const H8TabDisclosureSoe = defineAsyncComponent(() => import('./h8/core/H8TabDisclosureSoe.vue'))

// lease-judgment/
const H8TabLeaseIdentification = defineAsyncComponent(() => import('./h8/lease-judgment/H8TabLeaseIdentification.vue'))
const H8TabLeaseTerm = defineAsyncComponent(() => import('./h8/lease-judgment/H8TabLeaseTerm.vue'))
const H8TabLeaseModification = defineAsyncComponent(() => import('./h8/lease-judgment/H8TabLeaseModification.vue'))

// measurement/
const H8TabMeasurementAnnual = defineAsyncComponent(() => import('./h8/measurement/H8TabMeasurementAnnual.vue'))
const H8TabMeasurementMonthly = defineAsyncComponent(() => import('./h8/measurement/H8TabMeasurementMonthly.vue'))

// depreciation/
const H8TabDepreciationNoImpair = defineAsyncComponent(() => import('./h8/depreciation/H8TabDepreciationNoImpair.vue'))
const H8TabDepreciationWithImpair = defineAsyncComponent(() => import('./h8/depreciation/H8TabDepreciationWithImpair.vue'))
const H8TabDepreciationAlloc = defineAsyncComponent(() => import('./h8/depreciation/H8TabDepreciationAlloc.vue'))

// impairment/
const H8TabImpairment = defineAsyncComponent(() => import('./h8/impairment/H8TabImpairment.vue'))
const H8TabRecoverable = defineAsyncComponent(() => import('./h8/impairment/H8TabRecoverable.vue'))

// inspection/
const H8TabDisposalCheck = defineAsyncComponent(() => import('./h8/inspection/H8TabDisposalCheck.vue'))
const H8TabSimplifiedCheck = defineAsyncComponent(() => import('./h8/inspection/H8TabSimplifiedCheck.vue'))
const H8TabRelatedParty = defineAsyncComponent(() => import('./h8/inspection/H8TabRelatedParty.vue'))

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

// ─── H8-6 分支选择器（按年计量/按月计量） ────────────────────────────────────
const measurementBranch = ref<string>('按年计量')
const measurementBranchOptions = ['按年计量', '按月计量']

// ─── H8-8 分支选择器（不含减值/含减值） ──────────────────────────────────────
const depreciationBranch = ref<string>('不含减值')
const depreciationBranchOptions = ['不含减值', '含减值']

function hydrateDepreciationBranch() {
  const item = allResponses.value.get('H8-8-branch')
  const raw = item?.remark ?? item?.conclusion
  if (raw === '含减值' || raw === '不含减值') depreciationBranch.value = raw
}
watch(allResponses, hydrateDepreciationBranch, { immediate: true })

function onDepreciationBranchChange(val: string | number | boolean) {
  const b = val === '含减值' ? '含减值' : '不含减值'
  depreciationBranch.value = b
  persistResponse('H8-8-branch', b)
}

// ─── H9联动状态（与 useH8CrossSheet 统一多键兜底）────────────────────────────
const { h8VsH9Linkage } = useH8CrossSheet(allResponses)
const h9LinkageStatus = computed(() => {
  const link = h8VsH9Linkage.value
  // Index 用 consistent|inconsistent|unknown 三态
  if (!link.isConsistent && /未加载/.test(link.message)) {
    return { isConsistent: true, diff: 0, message: link.message, status: 'unknown' as const }
  }
  return {
    isConsistent: link.isConsistent,
    diff: link.diff,
    message: link.message,
    status: (link.isConsistent ? 'consistent' : 'inconsistent') as 'consistent' | 'inconsistent',
  }
})

// ─── 双模式切换 ──────────────────────────────────────────────────────────────
const currentMode = ref<'html' | 'onlyoffice'>('html')
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]

// ─── sheetName → 编码提取 ────────────────────────────────────────────────────
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  if (/H8A/.test(name)) return 'H8A'
  // H8-N 编码（H8-1 到 H8-14）
  const m = name.match(/(H8-\d+)/)
  if (m) return m[1]
  // 底稿目录 H8（无后缀）
  if (/底稿目录/.test(name) || (/\bH8\b/.test(name) && !/H8-/.test(name) && !/H8A/.test(name))) return 'H8'
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
    params: { force_component_type: 'h8-right-of-use-assets' },
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
    console.warn('[GtH8RightOfUseAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

/** IE 导入 / 跨表事件后：必须打服务端，避免 htmlData 快照导致 UI 假旧 */
async function reloadFromServer(): Promise<void> {
  try {
    allResponses.value = await fetchResponsesFromServer()
  } catch (err) {
    console.warn('[GtH8RightOfUseAssets] reloadFromServer failed:', err)
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
  // 替换 Map 引用以触发依赖 allResponses 的 computed / watch
  const next = new Map(allResponses.value)
  next.set(itemId, updated)
  allResponses.value = next
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
    }).catch((err: unknown) => console.warn('[GtH8] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[H8] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)
provide('h8ReloadAll', reloadFromServer)

// ─── Runtime Boundary：版本链/复核由 GtWpRenderer 统一提供，不再本地重复接线 ───
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h8VersionTrailRef', versionTrailRef)
provide('h8OpenVersionHistory', openVersionHistory)

// ─── EventBus: H9联动 ───────────────────────────────────────────────────────
function _handleH9Updated(_e: Event): void {
  // H9租赁负债数据更新时刷新H8，保持联动数据同步
  void reloadFromServer()
}

function _handleH9PaymentUpdated(_e: Event): void {
  // H9付款计划/摊销表变更时刷新H8（影响折旧测算和初始计量校验）
  void reloadFromServer()
}

function _handleTbUpdated(_e: Event): void {
  // TB更新(科目1901相关)触发刷新
  void reloadFromServer()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  // Subscribe: TB updates
  window.addEventListener('tb:updated', _handleTbUpdated)
  // Subscribe: 审定数变更
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
  // Subscribe: H9租赁负债更新 → 刷新H8联动数据
  window.addEventListener('h9:liability-updated', _handleH9Updated)
  // Subscribe: H9付款计划/摊销表变更 → 刷新H8初始计量/折旧校验
  window.addEventListener('h9:lease-payment-updated', _handleH9PaymentUpdated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
  window.removeEventListener('h9:liability-updated', _handleH9Updated)
  window.removeEventListener('h9:lease-payment-updated', _handleH9PaymentUpdated)
  for (const t of _saveTimers.values()) clearTimeout(t)
})
</script>

<style scoped>
.h8-right-of-use-assets {
  padding: 0;
}

.loading-container {
  padding: 24px;
}

.h8-h9-linkage-bar {
  padding: 8px 16px;
  border-radius: 4px;
  margin-bottom: 12px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
}

.h8-h9-linkage-bar.status-green {
  background: #f0f9eb;
  color: #67c23a;
  border: 1px solid #e1f3d8;
}

.h8-h9-linkage-bar.status-red {
  background: #fef0f0;
  color: #f56c6c;
  border: 1px solid #fde2e2;
}

.h8-header-toolbar {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
  gap: 12px;
}

.h8-branch-container {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.h8-branch-selector {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  flex-wrap: wrap;
}

.branch-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
</style>
