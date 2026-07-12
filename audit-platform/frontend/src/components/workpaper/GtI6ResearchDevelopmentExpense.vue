<template>
  <div class="i6-research-development-expense">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <div v-if="isHtmlSheet" class="i6-header-toolbar">
        <el-segmented
          v-if="dualMode.isOoAvailable.value"
          v-model="dualMode.currentMode.value"
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
        <!-- 底稿目录 -->
        <I6TabIndex
          v-if="currentSheet === 'I6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I6A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'I6A'"
          sheet-code="I6A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- I6-1 审定表（损益类！73公式） -->
        <I6TabAdjudication
          v-else-if="currentSheet === 'I6-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I6-2 明细表（月度12列横向） -->
        <I6TabDetail
          v-else-if="currentSheet === 'I6-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- I6-3 调整分录 -->
        <I6TabAdjustment
          v-else-if="currentSheet === 'I6-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- I6-4 针对性检查 -->
        <I6TabTargetedCheck
          v-else-if="currentSheet === 'I6-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- I6-5 截止测试（账→单据） -->
        <I6TabCutoffForward
          v-else-if="currentSheet === 'I6-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- I6-6 截止测试（单据→账） -->
        <I6TabCutoffBackward
          v-else-if="currentSheet === 'I6-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（上市） -->
        <I6TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（国企） -->
        <I6TabDisclosureSoe
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

      <GtWpVersionTrail ref="versionTrailRef" :workpaper-id="props.wpId" :project-id="props.projectId" />
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtI6ResearchDevelopmentExpense.vue — I6 研发费用底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "I6-{sheet}-{field}"
 *
 * 损益类科目（6602研发费用）— 取发生额非余额！与H10同款处理。
 * I6↔I2双向联动：费用化+资本化=研发总额（VR-I6-01）
 *
 * Spec: .kiro/specs/i6-research-development-expense/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, provide, toRef, defineAsyncComponent } from 'vue'
import http from '@/utils/http'
import { useWorkpaperVersionToolbar } from './composables/useWorkpaperVersionToolbar'
import { useI6DualMode } from './composables/useI6DualMode'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('./version-trail/GtWpVersionTrail.vue'))

// core
const I6TabIndex = defineAsyncComponent(() => import('./i6/core/I6TabIndex.vue'))
const I6TabAdjudication = defineAsyncComponent(() => import('./i6/core/I6TabAdjudication.vue'))
const I6TabDetail = defineAsyncComponent(() => import('./i6/core/I6TabDetail.vue'))
const I6TabAdjustment = defineAsyncComponent(() => import('./i6/core/I6TabAdjustment.vue'))
const I6TabTargetedCheck = defineAsyncComponent(() => import('./i6/core/I6TabTargetedCheck.vue'))
const I6TabDisclosureListed = defineAsyncComponent(() => import('./i6/core/I6TabDisclosureListed.vue'))
const I6TabDisclosureSoe = defineAsyncComponent(() => import('./i6/core/I6TabDisclosureSoe.vue'))

// cutoff
const I6TabCutoffForward = defineAsyncComponent(() => import('./i6/cutoff/I6TabCutoffForward.vue'))
const I6TabCutoffBackward = defineAsyncComponent(() => import('./i6/cutoff/I6TabCutoffBackward.vue'))

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
const tbData = ref({
  /** 6602 未审发生额 */
  unadjusted6602: 0,
  /** 6602 审定发生额 */
  audited6602: 0,
})

// ─── 双模式 useI6DualMode (OO 健康检查 + el-segmented) ──────────────────────
const dualMode = useI6DualMode({
  wpId: computed(() => props.wpId),
  sheetName: computed(() => props.sheetName || ''),
  reloadAll: async () => { await selfLoad() },
})

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (I6/I6A/I6-1~I6-6/附注)
 * 损益类底稿 — 审定取发生额非余额
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'I6'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 I6A
  if (/I6A/.test(name)) return 'I6A'
  // I6-N 编码（I6-1 到 I6-6）
  const m = name.match(/(I6-\d+)/)
  if (m) return m[1]
  // 底稿目录 I6（无后缀）
  if (/\bI6\b/.test(name) && !/I6-/.test(name) && !/I6A/.test(name)) return 'I6'
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
  } catch {
    // 静默失败，数据保留在本地
  }
}

// ─── TB自动取数（6602研发费用 — 损益类取发生额！） ──────────────────────────────
async function _loadTbData(): Promise<void> {
  if (!props.projectId) return
  try {
    const res = await http.get(`/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: '6602' },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    let u6602 = 0, a6602 = 0
    for (const item of list) {
      const code = String(item.standard_account_code ?? item.account_code ?? '')
      if (code.startsWith('6602')) {
        u6602 += Number(item.unadjusted_amount ?? 0)
        a6602 += Number(item.audited_amount ?? 0)
      }
    }
    tbData.value = { unadjusted6602: u6602, audited6602: a6602 }
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
        params: { force_component_type: 'i6-research-development-expense' },
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
    console.warn('[GtI6ResearchDevelopmentExpense] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── provide for child components ────────────────────────────────────────────
function openReviewDialog(sectionId: string, sectionLabel?: string): void {
  console.log('[I6] openReviewDialog:', sectionId, sectionLabel)
}
provide('openReviewDialog', openReviewDialog)

// ─── 版本追踪 useWorkpaperVersionToolbar (autoSnapshot on save) ──────────────
const versionToolbar = useWorkpaperVersionToolbar({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const { versionTrailRef, openVersionHistory, scheduleAutoSnapshot } = versionToolbar
provide('i6VersionTrailRef', versionTrailRef)
provide('i6OpenVersionHistory', openVersionHistory)

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.i6-research-development-expense {
  width: 100%;
  min-height: 400px;
}
.loading-container {
  padding: 24px;
}
.i6-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
