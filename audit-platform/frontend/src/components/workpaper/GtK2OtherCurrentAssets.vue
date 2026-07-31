<template>
  <div class="k2-other-current-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 目录页(currentSheet==='K2')不显示双模式工具栏 -->
      <div v-if="isHtmlSheet && currentSheet !== 'K2'" class="k2-header-toolbar">
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
        <!-- 底稿目录 -->
        <K2TabIndex
          v-if="currentSheet === 'K2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2A 程序表（复用 GtAProgramConsole） -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'K2A'"
          sheet-code="K2A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- K2-1 审定表 -->
        <K2TabAdjudication
          v-else-if="currentSheet === 'K2-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-data="tbData"
          :prefill="adjudicationPrefill"
          :tb-source-codes="tbSourceCodes"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @remove="handleChildRemove"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2-2 明细表 -->
        <K2TabDetail
          v-else-if="currentSheet === 'K2-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-source-codes="tbSourceCodes"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2-3 调整分录 -->
        <K2TabAdjustment
          v-else-if="currentSheet === 'K2-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-source-codes="tbSourceCodes"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2-4 合同取得成本明细 -->
        <K2TabContractCost
          v-else-if="currentSheet === 'K2-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2-5 摊销测算 -->
        <K2TabAmortization
          v-else-if="currentSheet === 'K2-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- K2-6 检查表（凭证级测试） -->
        <K2TabCheck
          v-else-if="currentSheet === 'K2-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :tb-source-codes="tbSourceCodes"
          :is-readonly="isReadonly"
          :year="props.year"
          @save="handleChildSave"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- 附注披露（上市） -->
        <K2TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
        />

        <!-- 附注披露（国企） -->
        <K2TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @save="handleChildSave"
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
 * GtK2OtherCurrentAssets.vue — K2 其他流动资产底稿主入口
 *
 * sheetName prop v-if 分发到全部子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * checklist_responses 前缀: "K2-{sheet}-{field}"
 *
 * 科目：1231其他流动资产（借方/资产类）
 * 核心：合同取得成本 + 摊销测算引擎（直线法/进度法）+ 资产类三角勾稽
 *
 * Spec: .kiro/specs/k2-other-current-assets/ Task 1.1
 * Requirements: 1.1-1.10
 */
import { ref, computed, onMounted, onBeforeUnmount, inject, defineAsyncComponent, toRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
import { useChecklistPersistence } from '@/composables/workpaper/useChecklistPersistence'
import { collectChecklistResponses, toChecklistPatch } from '@/composables/workpaper/checklistPersistenceHelpers'
import {
  WorkpaperRuntimeContextKey,
  type WorkpaperRuntimeContext,
} from './composables/useWorkpaperScaffold'
import {
  sumLongestPrefixOnly,
  tbQueryCodes,
  type TbSourceCodes,
} from './composables/shared/tbSourceCodes'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

/** 原值兜底标准码（报表行 BS-014 实证公式 `TB('1901','期末余额')`） */
const K2_GROSS_FALLBACK_STANDARD = '1901'
// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core
const K2TabIndex = defineAsyncComponent(() => import('./k2/core/K2TabIndex.vue'))
const K2TabAdjudication = defineAsyncComponent(() => import('./k2/core/K2TabAdjudication.vue'))
const K2TabDetail = defineAsyncComponent(() => import('./k2/core/K2TabDetail.vue'))
const K2TabAdjustment = defineAsyncComponent(() => import('./k2/core/K2TabAdjustment.vue'))
const K2TabDisclosureListed = defineAsyncComponent(() => import('./k2/core/K2TabDisclosureListed.vue'))
const K2TabDisclosureSoe = defineAsyncComponent(() => import('./k2/core/K2TabDisclosureSoe.vue'))

// amortization
const K2TabContractCost = defineAsyncComponent(() => import('./k2/amortization/K2TabContractCost.vue'))
const K2TabAmortization = defineAsyncComponent(() => import('./k2/amortization/K2TabAmortization.vue'))

// inspection
const K2TabCheck = defineAsyncComponent(() => import('./k2/inspection/K2TabCheck.vue'))

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
const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed<string | undefined>(() => props.projectId || undefined)
const persistence = useChecklistPersistence({ wpId: wpIdRef, projectId: projectIdRef })
const allResponses = persistence.responses
const runtime = inject<WorkpaperRuntimeContext | null>(WorkpaperRuntimeContextKey, null)

/**
 * 试算平衡表核对数 —— 口径由报表行 `BS-014` 映射解析得出（见 `tbSourceCodes`）。
 * 🔴 历史实现按硬编码前缀 `1231` 汇总，而 `1231` 是应收款项坏账准备，与本科目无关。
 */
const tbData = ref({ unadjusted: 0, audited: 0 })

/** K2-1 审定表明细子科目预填（来自后端 render adjudication_prefill） */
const adjudicationPrefill = computed(() =>
  Array.isArray(props.htmlData?.adjudication_prefill) ? props.htmlData.adjudication_prefill : []
)

/** 四表取数溯源（report_line_accounts 解析结果，供溯源面板 + 回写科目码） */
const tbSourceCodes = computed<TbSourceCodes | null>(() => {
  const src = props.htmlData?.tb_source_codes
  return src && typeof src === 'object' ? (src as TbSourceCodes) : null
})

/** 试算平衡表查询口径（标准码集）；溯源缺失时回退 `1901` */
const tbQueryStandardCodes = computed(() =>
  tbQueryCodes(tbSourceCodes.value?.gross_standard, K2_GROSS_FALLBACK_STANDARD),
)

// ─── 版本链 + 复核对话 provide（供子组件inject使用）────────────────────────
import { provide } from 'vue'

const scheduleAutoSnapshot = () => runtime?.version?.scheduleAutoSnapshot?.()

// 复核对话：从runtime获取或创建no-op fallback
const openReviewDialog = (sectionId: string) => {
  runtime?.review?.openReviewDialog?.(sectionId)
}
provide('openReviewDialog', openReviewDialog)
provide('scheduleAutoSnapshot', scheduleAutoSnapshot)

// 复核圆点
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

// ─── 双模式 (OO 健康检查 + el-segmented) ────────────────────────────────────
const dualMode = (() => {
  const currentMode = ref<'html' | 'onlyoffice'>('html')
  const isOoAvailable = ref(false)
  const checking = ref(true)
  const modeOptions = [
    { label: '结构化视图', value: 'html' },
    { label: '在线编辑', value: 'onlyoffice' },
  ]

  async function checkOoHealth(): Promise<void> {
    try {
      const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
      isOoAvailable.value = !!(res?.data?.data?.healthy ?? res?.data?.healthy)
    } catch {
      isOoAvailable.value = false
    } finally {
      checking.value = false
    }
  }

  function onModeChange(val: string | number): void {
    currentMode.value = val as 'html' | 'onlyoffice'
  }

  // 启动时检查 OO 可用性
  checkOoHealth()

  return { currentMode, isOoAvailable, checking, modeOptions, onModeChange }
})()

/** 当前 sheet 是否为 HTML 可渲染（有匹配子组件） */
const isHtmlSheet = computed(() => currentSheet.value !== '')

/**
 * 从 sheetName 提取编码 (K2/K2A/K2-1~K2-6/附注)
 * 支持格式：
 *  - "底稿目录" → K2
 *  - "实质性程序表 K2A" → K2A
 *  - "审定表K2-1" → K2-1
 *  - "附注披露信息（上市公司）" → 附注上市
 *  - "附注披露信息（国企）" → 附注国企
 *  - "明细表K2-2" → K2-2
 *  - "调整分录汇总K2-3" → K2-3
 *  - "合同取得成本明细表K2-4" → K2-4
 *  - "摊销测算表K2-5" → K2-5
 *  - "其他流动资产检查表表K2-6" → K2-6
 */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 底稿目录
  if (/底稿目录/.test(name)) return 'K2'
  // 附注匹配
  if (/附注.*上市/.test(name)) return '附注上市'
  if (/附注.*国/.test(name)) return '附注国企'
  // 程序表 K2A
  if (/K2A/.test(name)) return 'K2A'
  // K2-N 编码（K2-1 到 K2-6）
  const m = name.match(/(K2-\d+)/)
  if (m) return m[1]
  // 底稿目录 K2（无后缀）
  if (/底稿目录/.test(name) || (/\bK2\b/.test(name) && !/K2-/.test(name) && !/K2A/.test(name))) return 'K2'
  return ''
})

// ─── 子组件 save 回调（统一 Persistence Adapter） ─────────────────────────────
async function handleChildSave(itemId: string, value: unknown): Promise<void> {
  if (!props.wpId) return
  try {
    await persistence.save(itemId, toChecklistPatch(value))
    runtime?.version.scheduleAutoSnapshot()
    emit('save')
  } catch (error) {
    ElMessage.error(persistence.stateOf(itemId).lastError || '保存失败，数据已保留在本地，请稍后重试')
    console.warn(`[GtK2OtherCurrentAssets] save failed: ${itemId}`, error)
  }
}

/**
 * 子组件删除动态行 → 清理该行全部字段键。
 *
 * `checklist_responses` 无删除端点（PUT 语义是 upsert）→ 置空串即视为无值
 * （`readNum` 归 0、`readRaw` 返空），与「行已删除」等价且不留脏数据。
 */
async function handleChildRemove(itemIds: string[]): Promise<void> {
  if (!props.wpId || !itemIds?.length) return
  for (const id of itemIds) {
    try {
      await persistence.save(id, toChecklistPatch(''))
    } catch (error) {
      console.warn(`[GtK2OtherCurrentAssets] remove failed: ${id}`, error)
    }
  }
  runtime?.version.scheduleAutoSnapshot()
  emit('save')
}

// ─── TB 自动取数（口径 = 报表行 BS-014 解析出的标准码，实证 1901） ─────────────
async function _loadTbData(): Promise<void> {
  // render 已按最长前缀归属算好 → 优先直读，避免重复请求与口径分叉
  const tv = props.htmlData?.tb_values
  if (tv && typeof tv === 'object') {
    tbData.value = {
      unadjusted: Number((tv as any).other_current_unadjusted ?? 0) || 0,
      audited: Number((tv as any).other_current_audited ?? 0) || 0,
    }
    return
  }
  if (!props.projectId) return
  // selfLoad 路径（htmlData 为 null）兜底请求：按解析出的标准码取，最长前缀求和防父子双计
  try {
    const codes = tbQueryStandardCodes.value
    const res = await http.get(`/api/projects/${props.projectId}/trial-balance`, {
      params: { account_prefix: codes[0], year: props.year },
      _silent: true,
    } as any)
    const list: any[] = Array.isArray(res?.data?.data ?? res?.data) ? (res?.data?.data ?? res?.data) : []
    const sum = sumLongestPrefixOnly(
      list.map((item) => ({
        code: String(item.standard_account_code ?? item.account_code ?? ''),
        unadjusted: Number(item.unadjusted_amount ?? 0) || 0,
        audited: Number(item.audited_amount ?? 0) || 0,
      })),
      codes,
    )
    tbData.value = { unadjusted: sum.unadjusted, audited: sum.audited }
  } catch {
    // TB取数失败静默处理（fail-open）
  }
}

// ─── selfLoad（统一 Persistence Adapter） ─────────────────────────────────────
async function selfLoad(): Promise<void> {
  try {
    const snapshot = props.htmlData
      ? collectChecklistResponses(
          props.htmlData.responses_snapshot,
          props.htmlData.allResponses,
          props.htmlData.checklist_responses,
        )
      : []
    if (snapshot.length > 0) persistence.hydrate(snapshot)
    else await persistence.load()
  } catch (err) {
    console.warn('[GtK2OtherCurrentAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────
onBeforeUnmount(() => { void persistence.flush().catch(() => undefined) })

onMounted(() => {
  void selfLoad()
  void _loadTbData()
})
</script>

<style scoped>
.k2-other-current-assets {
  padding: 0;
  height: 100%;
}

.loading-container {
  padding: 24px;
}

.k2-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  background: var(--el-bg-color);
}
</style>
