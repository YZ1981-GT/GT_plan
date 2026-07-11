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

      <!-- 顶部工具栏（双模式切换） -->
      <div class="h9-header-toolbar">
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
        <H9TabAdjudication
          v-else-if="currentSheet === 'H9-1'"
          @save="persistResponse"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

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
import { ref, computed, onMounted, onBeforeUnmount, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import useVersionTrail from './composables/useVersionTrail'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
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

// ─── H8联动状态（H9初始确认 ≈ H8初始 - 直接费用 + 激励） ──────────────────
const h8LinkageStatus = computed(() => {
  const h9Initial = parseFloat(allResponses.value.get('H9-initial-recognition') || '0') || 0
  const h8Initial = parseFloat(allResponses.value.get('H9-h8-initial-measurement') || '0') || 0
  const h8DirectCost = parseFloat(allResponses.value.get('H9-h8-direct-cost') || '0') || 0
  const h8Incentive = parseFloat(allResponses.value.get('H9-h8-incentive') || '0') || 0

  // CAS21: H8 = H9 + 直接费用 - 激励
  // => H9 = H8 - 直接费用 + 激励
  if (h9Initial === 0 && h8Initial === 0) {
    return { isConsistent: true, diff: 0, message: '' }
  }

  const expectedH9 = h8Initial - h8DirectCost + h8Incentive
  const diff = Math.abs(h9Initial - expectedH9)
  const isConsistent = diff <= 1 // 允许尾差±1元

  return {
    isConsistent,
    diff,
    message: isConsistent
      ? ''
      : `H9与H8不一致，差额：${diff.toFixed(2)}元，请检查`,
  }
})

// ─── 双模式切换（后续由 useH9DualMode composable 替代） ─────────────────────
const currentMode = ref<'html' | 'onlyoffice'>('html')
const modeOptions = [
  { label: '结构化视图', value: 'html' },
  { label: '在线编辑', value: 'onlyoffice' },
]

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
  if (/\bH9\b/.test(name) && !/H9-/.test(name) && !/H9A/.test(name)) return 'H9'
  return ''
})

// ─── selfLoad ────────────────────────────────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    if (props.htmlData) {
      // 从父级透传的 htmlData 中提取 responses
      // 兼容两种键名：allResponses（历史）/ responses_snapshot（H9 render 策略实际输出）
      const map = new Map<string, any>()
      if (props.htmlData.allResponses && typeof props.htmlData.allResponses === 'object') {
        for (const [k, v] of Object.entries(props.htmlData.allResponses)) map.set(k, v)
      }
      if (props.htmlData.responses_snapshot && typeof props.htmlData.responses_snapshot === 'object') {
        for (const [k, v] of Object.entries(props.htmlData.responses_snapshot)) map.set(k, v)
      }
      if (map.size > 0) allResponses.value = map
    } else {
      // selfLoad: 自行调用 render-config
      const res = await http.get(`/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h9-lease-liabilities' },
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
          if (sheet.html_data?.responses_snapshot) {
            for (const [k, v] of Object.entries(sheet.html_data.responses_snapshot)) {
              map.set(k, v)
            }
          }
        }
        allResponses.value = map
      }
    }
  } catch (err) {
    console.warn('[GtH9LeaseLiabilities] selfLoad failed:', err)
  } finally {
    isLoading.value = false
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
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion: updated.conclusion ?? null, remark: updated.remark ?? null }],
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

// ─── 版本追踪 useVersionTrail ────────────────────────────────────────────────
const versionTrail = useVersionTrail({
  projectId: toRef(props, 'projectId') as any,
  workpaperId: toRef(props, 'wpId') as any,
})
provide('versionTrail', versionTrail)

// ─── H8联动: 终止合同标记 ───────────────────────────────────────────────────
/** 已终止合同ID集合（由H8终止事件推送） */
const terminatedContractIds = ref<Set<string>>(new Set())
provide('terminatedContractIds', terminatedContractIds)

function _handleH8LeaseTerminated(e: Event): void {
  // H8发布租赁终止事件时，标记已终止合同
  const detail = (e as CustomEvent)?.detail
  if (detail?.contractId) {
    terminatedContractIds.value.add(detail.contractId)
  }
  // 同时刷新数据
  void selfLoad()
}

function _handleH8Updated(_e: Event): void {
  // H8使用权资产数据更新时刷新H9，保持联动数据同步
  void selfLoad()
}

function _handleTbUpdated(_e: Event): void {
  // TB更新(科目2205相关)触发刷新
  void selfLoad()
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  // Subscribe: TB updates
  window.addEventListener('tb:updated', _handleTbUpdated)
  // Subscribe: 审定数变更
  window.addEventListener('substantive:adjudicated', _handleTbUpdated)
  // Subscribe: H8租赁终止 → 标记已终止合同
  window.addEventListener('h8:lease-terminated', _handleH8LeaseTerminated)
  // Subscribe: H8数据更新 → 刷新H9联动
  window.addEventListener('h8:asset-updated', _handleH8Updated)
})

onBeforeUnmount(() => {
  window.removeEventListener('tb:updated', _handleTbUpdated)
  window.removeEventListener('substantive:adjudicated', _handleTbUpdated)
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
  font-size: 13px;
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
