<template>
  <div class="h1-fixed-assets">
    <div v-if="isLoading" class="loading-container">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- 双模式切换器（OO 模式也需可见，否则无法切回结构化） -->
      <div v-if="showModeSwitch" class="h1-mode-switch-bar">
        <el-segmented
          :model-value="currentMode"
          :options="modeOptions"
          size="small"
          :disabled="ooChecking"
          @change="onModeChange"
        />
        <el-tag v-if="!isOoAvailable && !ooChecking" size="small" type="info">OnlyOffice 不可用</el-tag>
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
        <H1TabIndex
          v-if="currentSheet === 'H1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1A 程序表 -->
        <CycleTabProcedure
          v-else-if="currentSheet === 'H1A'"
          sheet-code="H1A"
          :html-data="props.htmlData"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :is-readonly="isReadonly"
        />

        <!-- H1-1 审定表 -->
        <H1TabAdjudication
          v-else-if="currentSheet === 'H1-1'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :html-data="resolvedHtmlData"
        />

        <!-- H1-2 明细表 -->
        <H1TabDetail
          v-else-if="currentSheet === 'H1-2'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-3 调整分录 -->
        <H1TabAdjustment
          v-else-if="currentSheet === 'H1-3'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-4 闲置检查 -->
        <H1TabIdleCheck
          v-else-if="currentSheet === 'H1-4'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-5 会计政策 -->
        <H1TabPolicyCheck
          v-else-if="currentSheet === 'H1-5'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-6 分析表 -->
        <H1TabAnalysis
          v-else-if="currentSheet === 'H1-6'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-7 增加检查 -->
        <H1TabAdditionCheck
          v-else-if="currentSheet === 'H1-7'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="h1Year"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H1-8 减少检查 -->
        <H1TabDisposalCheck
          v-else-if="currentSheet === 'H1-8'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :year="h1Year"
        />

        <!-- H1-9 监盘计划 -->
        <H1TabStocktakePlan
          v-else-if="currentSheet === 'H1-9'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H1-10 盘点检查 -->
        <H1TabStocktakeCheck
          v-else-if="currentSheet === 'H1-10'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H1-11 监盘小结 -->
        <H1TabStocktakeSummary
          v-else-if="currentSheet === 'H1-11'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          @navigate-sheet="(s: string) => emit('navigate-sheet', s)"
        />

        <!-- H1-12 折旧测算 (3分支：不含减值/含减值/多次减值，导入时按减值联动推荐) -->
        <template v-else-if="currentSheet === 'H1-12'">
          <div class="dep-branch-selector" style="margin-bottom:12px;padding:0 16px;display:flex;align-items:center;gap:12px;flex-wrap:wrap">
            <el-segmented
              v-model="depreciationBranch"
              :options="[
                { label: '不含减值-直线法', value: 'A' },
                { label: '含减值', value: 'B' },
                { label: '多次减值', value: 'C' },
              ]"
              size="small"
            />
            <span style="font-size:12px;color:var(--el-text-color-secondary)">
              三表联动：按资产减值余额/次数自动推荐分支；支持从 H1-2 或企业台账一键导入测算
            </span>
          </div>
          <H1TabDepreciationStraight
            v-if="depreciationBranch === 'A'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            :period-end="h1PeriodEnd"
            @branch-change="onDepBranchChange"
          />
          <H1TabDepreciationImpair
            v-else-if="depreciationBranch === 'B'"
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            :period-end="h1PeriodEnd"
            @branch-change="onDepBranchChange"
          />
          <H1TabDepreciationMulti
            v-else
            :wp-id="props.wpId"
            :project-id="props.projectId"
            :all-responses="allResponses"
            :is-readonly="isReadonly"
            :period-end="h1PeriodEnd"
            @branch-change="onDepBranchChange"
          />
        </template>

        <!-- H1-13 折旧分配（跨科目核对：类别×费用矩阵 → F5/D5/K8/K9/I6） -->
        <H1TabDepreciationAlloc
          v-else-if="currentSheet === 'H1-13'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :depreciation-by-category="depreciationForAlloc.byCategory"
          :depreciation-total="depreciationForAlloc.total"
        />

        <!-- H1-14 减值测算 -->
        <H1TabImpairment
          v-else-if="currentSheet === 'H1-14'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-15 可收回金额 -->
        <H1TabRecoverable
          v-else-if="currentSheet === 'H1-15'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-16 房屋建筑物权属 -->
        <H1TabTitleBuilding
          v-else-if="currentSheet === 'H1-16'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-17 运输设备权属 -->
        <H1TabTitleVehicle
          v-else-if="currentSheet === 'H1-17'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :html-data="props.htmlData"
          :period-end="h1PeriodEnd"
        />

        <!-- H1-18 关联交易 -->
        <H1TabRelatedParty
          v-else-if="currentSheet === 'H1-18'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-19 经营租出 -->
        <H1TabOperatingLease
          v-else-if="currentSheet === 'H1-19'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- H1-20 融资租出 -->
        <H1TabFinanceLease
          v-else-if="currentSheet === 'H1-20'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
        />

        <!-- 附注披露（上市） -->
        <H1TabDisclosureListed
          v-else-if="currentSheet === '附注上市'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :template-type="projectTemplateType"
          :report-scope="projectReportScope"
        />

        <!-- 附注披露（国企） -->
        <H1TabDisclosureSoe
          v-else-if="currentSheet === '附注国企'"
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :all-responses="allResponses"
          :is-readonly="isReadonly"
          :template-type="projectTemplateType"
          :report-scope="projectReportScope"
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
 * GtH1FixedAssets.vue — H1 固定资产底稿主入口
 *
 * sheetName prop v-if 分发到全部22个子组件，无内部 el-tabs。
 * 外层 GtWpRenderer 通过底稿目录行(chips)控制当前 sheet。
 * selfLoad: 当 htmlData prop 为 null 时自行调 render-config。
 * useVersionTrail: autoSnapshot on save。
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 6.1
 * Requirements: 1.2-1.3, 17.1
 */
import { ref, computed, onMounted, onUnmounted, provide, toRef, inject, defineAsyncComponent, watch } from 'vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { WorkpaperRuntimeContextKey } from './composables/useWorkpaperScaffold'
import { useH1CrossSheet } from './composables/useH1CrossSheet'
import { useH1DualMode } from './composables/useH1DualMode'
import {
  buildDetailSeedRows,
  shouldSeedDetailRows,
  mergeSeedRows,
  type H1FourTablePrefill,
} from './composables/h1FourTablePrefill'
import CycleTabProcedure from './shared/CycleTabProcedure.vue'

// ─── Lazy-loaded 子组件 ──────────────────────────────────────────────────────
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))

// core — H1TabIndex 非 lazy（底稿目录轻量，首屏必显）
import H1TabIndex from './h1/core/H1TabIndex.vue'
const H1TabAdjudication = defineAsyncComponent(() => import('./h1/core/H1TabAdjudication.vue'))
const H1TabDetail = defineAsyncComponent(() => import('./h1/core/H1TabDetail.vue'))
const H1TabAdjustment = defineAsyncComponent(() => import('./h1/core/H1TabAdjustment.vue'))
const H1TabAnalysis = defineAsyncComponent(() => import('./h1/core/H1TabAnalysis.vue'))
const H1TabDisclosureListed = defineAsyncComponent(() => import('./h1/core/H1TabDisclosureListed.vue'))
const H1TabDisclosureSoe = defineAsyncComponent(() => import('./h1/core/H1TabDisclosureSoe.vue'))

// inspection
const H1TabIdleCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabIdleCheck.vue'))
const H1TabPolicyCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabPolicyCheck.vue'))
const H1TabAdditionCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabAdditionCheck.vue'))
const H1TabDisposalCheck = defineAsyncComponent(() => import('./h1/inspection/H1TabDisposalCheck.vue'))
const H1TabTitleBuilding = defineAsyncComponent(() => import('./h1/inspection/H1TabTitleBuilding.vue'))
const H1TabTitleVehicle = defineAsyncComponent(() => import('./h1/inspection/H1TabTitleVehicle.vue'))
const H1TabRelatedParty = defineAsyncComponent(() => import('./h1/inspection/H1TabRelatedParty.vue'))
const H1TabOperatingLease = defineAsyncComponent(() => import('./h1/inspection/H1TabOperatingLease.vue'))
const H1TabFinanceLease = defineAsyncComponent(() => import('./h1/inspection/H1TabFinanceLease.vue'))

// stocktake
const H1TabStocktakePlan = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakePlan.vue'))
const H1TabStocktakeCheck = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakeCheck.vue'))
const H1TabStocktakeSummary = defineAsyncComponent(() => import('./h1/stocktake/H1TabStocktakeSummary.vue'))

// depreciation
const H1TabDepreciationStraight = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationStraight.vue'))
const H1TabDepreciationImpair = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationImpair.vue'))
const H1TabDepreciationMulti = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationMulti.vue'))
const H1TabDepreciationAlloc = defineAsyncComponent(() => import('./h1/depreciation/H1TabDepreciationAlloc.vue'))

// impairment
const H1TabImpairment = defineAsyncComponent(() => import('./h1/impairment/H1TabImpairment.vue'))
const H1TabRecoverable = defineAsyncComponent(() => import('./h1/impairment/H1TabRecoverable.vue'))

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

// 目录卡片跳转（H1TabIndex → GtWpRenderer）
provide('jumpToSection', (sheetName: string) => emit('navigate-sheet', sheetName))

// ─── Runtime Boundary（须早于 dual-mode，供 autoSave 快照）──────────────────
const runtime = inject(WorkpaperRuntimeContextKey, null)
const versionTrailRef = runtime?.version.versionTrailRef ?? ref<{ openDrawer: () => void } | null>(null)
const openVersionHistory = runtime?.version.openVersionHistory ?? (() => undefined)
const scheduleAutoSnapshot = runtime?.version.scheduleAutoSnapshot ?? (() => undefined)
provide('h1VersionTrailRef', versionTrailRef)
provide('h1OpenVersionHistory', openVersionHistory)

// ─── State ───────────────────────────────────────────────────────────────────
const isReadonly = computed(() => !!props.readonly)
const isLoading = ref(true)
const allResponses = ref<Map<string, any>>(new Map())
/** 合并 props.htmlData 与 selfLoad 的 render 元数据（含 TB 分类预填） */
const resolvedHtmlData = ref<any>(props.htmlData || null)

/** H1-12 → H1-13 按分类折旧额（跨 sheet computed） */
const { depreciationForAlloc } = useH1CrossSheet(allResponses)
const depreciationBranch = ref<'A' | 'B' | 'C'>('A')

const dual = useH1DualMode({
  wpId: toRef(props, 'wpId'),
  sheetName: computed(() => props.sheetName || ''),
  autoSave: async () => { scheduleAutoSnapshot() },
  reloadAll: async () => { await selfLoad() },
})
const currentMode = dual.currentMode
const modeOptions = dual.modeOptions
const _rawOnModeChange = dual.onModeChange
const isOoAvailable = dual.isOoAvailable
const ooChecking = dual.checking

/** C1: 目录/程序表不支持在线编辑 */
function onModeChange(val: string | number | boolean): void {
  if (val === 'onlyoffice') {
    const s = currentSheet.value
    if (s === 'H1' || s.endsWith('A')) {
      // 目录/程序表不切 OO
      return
    }
  }
  _rawOnModeChange(val)
}

/** 资产负债表日：供 H1-17 年检过期判定等 */
const h1PeriodEnd = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  return (
    ctx.period_end
    || ctx.audit_period_end
    || ctx.bs_date
    || props.htmlData?.period_end
    || ''
  ) as string
})

/**
 * 附注披露口径（权威变体源 = projects.template_type / report_scope，由 render project_context 注入）。
 * 上市披露表只能同步上市章节（五、22）、国企只能同步国企章节（八、22），不可混用。
 */
const projectTemplateType = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  return String(ctx.template_type ?? '')
})
const projectReportScope = computed(() => {
  const ctx = props.htmlData?.project_context ?? props.htmlData?.projectContext ?? {}
  return String(ctx.report_scope ?? '')
})

// ─── 四表取数（灰度 H1_FOUR_TABLE_EXTRACTION_ENABLED，关闭时载荷不存在）────────
/** 后端 render 注入的四表取数载荷（明细/序时账增减/对方科目可用性） */
const fourTablePrefill = computed<H1FourTablePrefill | null>(() => {
  const hd: any = resolvedHtmlData.value || props.htmlData || {}
  return (hd.h1_four_table_prefill ?? hd.h1FourTablePrefill ?? null) as H1FourTablePrefill | null
})
provide('h1FourTablePrefill', fourTablePrefill)

/**
 * 四表取数 → H1-2 种子行（Persist_First，Req1.3 / Req6.2）
 * - 默认仅在 H1-2 明细为空时写入，绝不覆盖审计师已录数据
 * - force=true（「重新取数」）覆盖取数行，保留手工新增行
 */
function seedDetailFromFourTable(force = false): number {
  if (isReadonly.value) return 0
  const seeds = buildDetailSeedRows(fourTablePrefill.value)
  if (!seeds.length) return 0
  const raw = allResponses.value.get('H1-2-rows')?.remark
  if (!force) {
    if (!shouldSeedDetailRows(raw)) return 0
    persistResponse('H1-2-rows', seeds)
    return seeds.length
  }
  persistResponse('H1-2-rows', mergeSeedRows(seeds, raw))
  return seeds.length
}
provide('h1SeedDetailFromFourTable', seedDetailFromFourTable)

/** 审计年度：优先 prop，其次从资产负债表日提取，最后回退当前年（供抽凭引擎） */
const h1Year = computed(() => {
  if (props.year) return props.year
  const m = /^(\d{4})/.exec(h1PeriodEnd.value || '')
  if (m) return Number(m[1])
  return new Date().getFullYear()
})

/** 从 sheetName 提取编码 (H1/H1A/H1-1~H1-20/附注) */
const currentSheet = computed(() => {
  const name = props.sheetName || props.wpCode || ''
  // 附注匹配
  // 注意：H1 源模板国企 sheet 名是「附注披露信息（国有企业）」——用的是「国有企业」
  // 而非其他循环的「国企」。只认「国企」会落到末尾 fallback 被误判成上市，
  // 导致国企 TAB 渲染上市组件（实测踩中）。故两种写法都要认。
  if (/附注.*上市|H1-note-listed/.test(name)) return '附注上市'
  if (/附注.*国企|附注.*国有|H1-note-soe/.test(name)) return '附注国企'
  if (/附注/.test(name)) return name.includes('国企') || name.includes('国有') ? '附注国企' : '附注上市'
  // 程序表
  const mA = name.match(/H1A/)
  if (mA) return 'H1A'
  // H1-N 编码（H1-1 到 H1-20）
  const m = name.match(/(H1-\d+)/)
  if (m) return m[1]
  // 底稿目录 H1（无后缀）
  if (/底稿目录/.test(name) || (/\bH1\b/.test(name) && !/H1-/.test(name) && !/H1A/.test(name))) return 'H1'
  return ''
})

const showHtmlToolbar = computed(() => {
  const s = currentSheet.value
  // 目录 sheet（H1）不显示工具栏（目录页无编辑对象）
  // 注：el-segmented 切换器独立于此 v-if，确保 OO 模式也能切回
  return s !== '' && s !== 'H1' && currentMode.value !== 'onlyoffice'
})

/** 双模式切换器是否可见（OO 模式也需要，否则无法切回结构化） */
const showModeSwitch = computed(() => {
  const s = currentSheet.value
  return s !== '' && s !== 'H1'
})

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
      resolvedHtmlData.value = props.htmlData
      const map = new Map<string, any>()
      _mergeResponses(map, props.htmlData.allResponses)
      _mergeResponses(map, props.htmlData.responses_snapshot)
      if (map.size > 0) allResponses.value = map
    } else {
      const res = await http.get(`/api/workpapers/${props.wpId}/render-config`, {
        params: { force_component_type: 'h1-fixed-assets' },
        _silent: true,
      } as any)
      const data = res.data?.data || res.data
      // 顶层或首个 sheet 的 html_data 均可带 TB 预填
      const topHd = data?.html_data || data
      let mergedHd: any = topHd && typeof topHd === 'object' ? { ...topHd } : {}
      if (data?.sheets && Array.isArray(data.sheets)) {
        const map = new Map<string, any>()
        for (const sheet of data.sheets) {
          _mergeResponses(map, sheet.html_data?.allResponses)
          _mergeResponses(map, sheet.html_data?.responses_snapshot)
          const hd = sheet.html_data
          if (hd?.adjudication_category_prefill && !mergedHd.adjudication_category_prefill) {
            mergedHd = { ...mergedHd, ...hd }
          }
          if (hd?.tb_values && !mergedHd.tb_values) {
            mergedHd = { ...mergedHd, tb_values: hd.tb_values }
          }
        }
        allResponses.value = map
      }
      if (Object.keys(mergedHd).length) resolvedHtmlData.value = mergedHd
    }
  } catch (err) {
    console.warn('[GtH1FixedAssets] selfLoad failed:', err)
  } finally {
    isLoading.value = false
    const br = allResponses.value.get('H1-12-branch')?.remark
    if (br === 'A' || br === 'B' || br === 'C') depreciationBranch.value = br
  }
}

// ─── 子组件 save 持久化（H2/H7 范式：entry 未接持久化 → 补 persistResponse+provide） ──
// 子组件契约：inject('saveResponse')(itemId, value, opts?)。value 为字符串或对象（对象序列化进 remark）。
// 防抖 800ms 批量 PUT /checklist-responses，并乐观更新本地 Map；默认 conclusion=null，C6 等可显式传 conclusion。
const _saveTimers = new Map<string, ReturnType<typeof setTimeout>>()
function persistResponse(
  itemId: string,
  value: any,
  opts?: { conclusion?: string | null },
): void {
  if (!itemId || !props.wpId) return
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  const existing = allResponses.value.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
  const conclusion = opts?.conclusion !== undefined ? opts.conclusion : null
  const updated = {
    ...existing,
    item_id: itemId,
    remark: strVal,
    ...(opts?.conclusion !== undefined ? { conclusion: opts.conclusion } : {}),
  }
  allResponses.value.set(itemId, updated)
  if (isReadonly.value) return
  const prev = _saveTimers.get(itemId)
  if (prev) clearTimeout(prev)
  _saveTimers.set(itemId, setTimeout(() => {
    _saveTimers.delete(itemId)
    http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{ item_id: itemId, conclusion, remark: updated.remark ?? null }],
    }).then(() => { scheduleAutoSnapshot() })
      .catch((err: unknown) => console.warn('[GtH1] persistResponse failed:', itemId, err))
  }, 800))
}

// ─── provide for child components ────────────────────────────────────────────
// openReviewDialog 由 Runtime Boundary(GtWpRenderer) 统一 provide，子组件 inject 命中祖先
provide('allResponses', allResponses)
provide('saveResponse', persistResponse)

// 复核圆点：GtReviewTrigger 依赖 getThreadDot/getRowDot 才渲染蓝/红点
import { useWorkpaperReviewThreads } from './composables/useWorkpaperReviewThreads'
const { getThreadDot, getRowDot } = useWorkpaperReviewThreads(toRef(props, 'wpId'))
provide('getThreadDot', getThreadDot)
provide('getRowDot', getRowDot)

function onDepBranchChange(b: 'A' | 'B' | 'C') {
  if (b === 'A' || b === 'B' || b === 'C') {
    depreciationBranch.value = b
    persistResponse('H1-12-branch', b)
  }
}

watch(depreciationBranch, (b) => {
  const cur = allResponses.value.get('H1-12-branch')?.remark
  if (cur !== b) persistResponse('H1-12-branch', b)
})

// ─── Lifecycle ───────────────────────────────────────────────────────────────

// 审定数变更 / 试算表更新 → 刷新 allResponses（各子 tab 含附注据此重算跨 sheet 取数）。
// 经 crossWpEventBridge 统一，无论源底稿走 window 还是 eventBus 都能命中。
let _refreshTimer: ReturnType<typeof setTimeout> | null = null
function _handleAdjudicatedRefresh(): void {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  _refreshTimer = setTimeout(() => { void selfLoad() }, 400)
}

onMounted(() => {
  void selfLoad().then(() => { seedDetailFromFourTable() })
  // 版本追踪：已集成 useVersionTrail — createSnapshot 由保存流程触发

  // 附注/取数联动：审定数变更或 TB 更新时刷新（P1 — 修 H1 附注刷新 double no-op）
  eventBus.on('substantive:adjudicated', _handleAdjudicatedRefresh)
  eventBus.on('trial-balance:updated', _handleAdjudicatedRefresh)

  // C6 前置控制完成 → 持久化 H1A 前置状态（eventBus + window 双活通道；
  // 后端不广播 control:c6-completed topic，故不再订阅 SSE 死路径）
  eventBus.on('control:c6-completed' as any, _handleC6Completed)
  window.addEventListener('control:c6-completed', _handleC6CompletedWindow)
})

function _applyC6Prerequisite(payload?: any): void {
  const remark = `C6完成于 ${payload?.timestamp || new Date().toISOString()}`
  persistResponse('H1A-c6-prerequisite', remark, { conclusion: 'Y' })
}

function _handleC6Completed(payload?: any): void {
  _applyC6Prerequisite(payload)
}

function _handleC6CompletedWindow(e: Event): void {
  _applyC6Prerequisite((e as CustomEvent).detail)
}

onUnmounted(() => {
  if (_refreshTimer) clearTimeout(_refreshTimer)
  eventBus.off('substantive:adjudicated', _handleAdjudicatedRefresh)
  eventBus.off('trial-balance:updated', _handleAdjudicatedRefresh)
  eventBus.off('control:c6-completed' as any, _handleC6Completed)
  window.removeEventListener('control:c6-completed', _handleC6CompletedWindow)
})
</script>

<style scoped>
.h1-fixed-assets {
  width: 100%;
  min-height: 400px;
}

.loading-container {
  padding: 24px;
}

.h1-header-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--el-border-color-lighter);
}
</style>
