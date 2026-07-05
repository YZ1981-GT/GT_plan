<script setup lang="ts">
/**
 * GtC22ItgcBundle — C22 IT 一般控制测试聚合组件（含 C21 / C21-1）
 *
 * Spec: .kiro/specs/c22-itgc-bundle/  Task 4.1 / 4.3
 * Requirements: 1.1, 3.1, 3.2, 3.3, 3.4（4.1）；6.1, 6.2, 6.3, 6.4, 9.1, 9.2, 9.3（4.3）
 *
 * Task 4.3 — sheetName 路由 + readonly 透传：
 *   - 路由：navigate('C22',{sheet}) / URL ?sheet= / props.sheetName 变更均经 activateSheet
 *     激活对应 Tab；非法 sheetName 保持当前（默认 matrix）。active 为唯一真源，
 *     顶层分组 section（activeSection）由 active 派生，故路由到子页会自动选中所属大类。
 *   - 只读：props.readonly 经 isReadonly 透传给控制点子页（GtC22ControlSheet）与
 *     C21/C21-1（GtOnlyOfficeSheet）；matrix 与 C21-1 汇总为浏览/跳转视图，只读下仍可用。
 *
 * C22 为单一 34-sheet 工作簿（1 主矩阵 + 33 子页），走 C1 整册模式
 * （后端 _WHOLE_WP_MULTISHEET_DEDICATED + render_c22_itgc 轻量策略）。
 * 本组件为自加载聚合入口，内部以「ITGC 矩阵总览 + 子页页签 + C21/C21-1」切换：
 *   - matrix：ITGC 控制矩阵总览面板（默认），一屏掌握各控制点结论与缺陷，
 *     点击控制点行 → 切换到对应控制域子页 Tab（Req 3.3）。
 *   - 子页：通过 GtOnlyOfficeSheet 渲染同一工作簿对应 sheet（分组/在页测试见 Task 4.2）。
 *   - C21 / C21-1：独立底稿，经 wp_index wp_id 渲染（详细汇总见 Task 5.x）。
 *
 * 模式参考：GtA17Bundle / GtF2StocktakeBundle（bundle shell + selfLoad）。
 * bundle 顶层 el-tabs 允许（tasks.md Notes）。
 */
import { ref, computed, watch, onMounted, defineAsyncComponent } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '@/services/apiProxy'
import {
  useC22BundleState,
  statusToDisplay,
  ITGC_GROUPS,
  CONCLUSION_OPTIONS,
  IT_CATEGORY_OPTIONS,
  APP_SYSTEM_OPTIONS,
  itgcItemId,
  itgcFieldStorage,
  type TabDef,
  type CompletionStatus,
} from './composables/useC22BundleState'

const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
const GtC22ControlSheet = defineAsyncComponent(() => import('./GtC22ControlSheet.vue'))
const GtC21FindingsSummary = defineAsyncComponent(() => import('./GtC21FindingsSummary.vue'))

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId?: string
  sheetName?: string
  readonly?: boolean
}>()

const route = useRoute()

const projectIdRef = computed(() =>
  props.projectId || (route.params.projectId as string) || '',
)

const isReadonly = computed(() => props.readonly === true)

// ─── Bundle state（composable） ───
const wpIdRef = computed(() => props.wpId)
const bundleState = useC22BundleState({
  projectId: projectIdRef,
  wpId: wpIdRef,
})
const {
  sheetTabs,
  controlPointTabs,
  wpIdMap,
  completionMap,
  controlFields,
  defects,
  progressSummary,
  loading,
  loadWpIndex,
  refreshCompletion,
} = bundleState

// ─── selfLoad：主矩阵行内容（render-config，供 matrix 总览面板静态列） ───
interface MatrixRow {
  row: number
  category: string
  risk: string
  controlNo: string
  description: string
  appSystem: string
  indexNo: string
}
const matrixRows = ref<MatrixRow[]>([])
const selfLoading = ref(false)

/** 按矩阵行号索引（TabDef.matrixRow → 该行静态内容） */
const matrixByRow = computed<Record<number, MatrixRow>>(() => {
  const map: Record<number, MatrixRow> = {}
  for (const r of matrixRows.value) {
    if (typeof r.row === 'number') map[r.row] = r
  }
  return map
})

async function selfLoadMatrix(): Promise<void> {
  if (!props.wpId) return
  selfLoading.value = true
  try {
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=c22-itgc-bundle`,
      { _silent: true } as any,
    )
    const sheets: any[] = res?.sheets ?? []
    // 找主矩阵 sheet（策略在其 html_data 上标记 is_matrix + matrix 数组）
    const matrixSheet = sheets.find(
      (s) => s?.html_data?.is_matrix === true || Array.isArray(s?.html_data?.matrix),
    )
    const list = matrixSheet?.html_data?.matrix
    matrixRows.value = Array.isArray(list) ? (list as MatrixRow[]) : []
  } catch (e) {
    // 降级：matrix 静态列留空，仍从 TabDef + responses 构建行
    console.warn('[GtC22ItgcBundle] selfLoad render-config 失败，matrix 静态列降级:', e)
    matrixRows.value = []
  } finally {
    selfLoading.value = false
  }
}

// ─── 提取风险编号 ITRxxx（Req 3.2：风险编号列 + tooltip 完整风险描述） ───
function riskNo(text: string): string {
  const m = (text || '').match(/ITR\s*\d+/i)
  return m ? m[0].replace(/\s+/g, '') : ''
}

// ─── matrix 总览：每个控制点行的合并数据 ───
interface MatrixDisplayRow {
  tab: TabDef
  category: string
  risk: string
  riskNo: string
  controlNo: string
  description: string
  appSystem: string
  itCategory: string
  designConclusion: string
  execConclusion: string
  abnormal: string
  defectNo: string
  status: CompletionStatus
}

const matrixDisplayRows = computed<MatrixDisplayRow[]>(() =>
  controlPointTabs.value.map((tab) => {
    const mc = tab.matrixRow != null ? matrixByRow.value[tab.matrixRow] : undefined
    const f = controlFields.value[tab.id] || {
      designConclusion: null, execConclusion: null, abnormal: null,
      defectDesc: null, defectNo: null, appSystem: null, itCategory: null,
    }
    const risk = mc?.risk || ''
    return {
      tab,
      category: mc?.category || tab.group,
      risk,
      riskNo: riskNo(risk),
      controlNo: mc?.controlNo || tab.id,
      description: mc?.description || '',
      // 应用系统：用户填报优先（多选 JSON），其次矩阵 E 列
      appSystem: f.appSystem || mc?.appSystem || '',
      itCategory: f.itCategory || '',
      designConclusion: f.designConclusion || '',
      execConclusion: f.execConclusion || '',
      abnormal: f.abnormal || '',
      defectNo: f.defectNo || '',
      status: completionMap.value[tab.id] || 'not_started',
    }
  }),
)

// ─── 页签结构 ───
const active = ref('matrix')

/** 可见页签：matrix + 子页（itgc-sheet/itgc-aux） + C21/C21-1（wp_id 存在才显示） */
const visibleTabs = computed<TabDef[]>(() =>
  sheetTabs.value.filter((t) => {
    if (t.kind === 'matrix') return true
    if (t.kind === 'c21' || t.kind === 'c21-1') {
      return !!(t.wpCode && wpIdMap.value[t.wpCode])
    }
    return true // itgc-sheet / itgc-aux（同工作簿 sheet）
  }),
)

// ─── 顶层分组页签（matrix + 4 大类 + C21 + C21-1）（Req 4.1/4.2） ───
type SectionKey = 'matrix' | ItgcGroupKey | 'C21' | 'C21-1'
type ItgcGroupKey = '信息安全' | '运行维护' | '程序变更' | '新系统'

interface SectionDef {
  key: SectionKey
  label: string
  /** matrix / group / c21 / c21-1 */
  kind: 'matrix' | 'group' | 'c21' | 'c21-1'
}

/** 各大类 → 该组内可见子页（itgc-sheet + itgc-aux 续页） */
function groupSubTabs(group: string): TabDef[] {
  return visibleTabs.value.filter(
    (t) => (t.kind === 'itgc-sheet' || t.kind === 'itgc-aux') && t.group === group,
  )
}

/** 顶层 section 列表：matrix 必有；4 大类有子页才显示；C21/C21-1 有 wp_id 才显示 */
const topSections = computed<SectionDef[]>(() => {
  const out: SectionDef[] = [{ key: 'matrix', label: 'ITGC 控制矩阵总览', kind: 'matrix' }]
  for (const g of ITGC_GROUPS) {
    if (groupSubTabs(g).length > 0) {
      out.push({ key: g as ItgcGroupKey, label: g, kind: 'group' })
    }
  }
  if (visibleTabs.value.some((t) => t.kind === 'c21')) {
    out.push({ key: 'C21', label: 'C21 IT专业成员', kind: 'c21' })
  }
  if (visibleTabs.value.some((t) => t.kind === 'c21-1')) {
    out.push({ key: 'C21-1', label: 'C21-1 IT发现汇总', kind: 'c21-1' })
  }
  return out
})

/** 当前 active 子页 tab 定义 */
const activeControlTab = computed<TabDef | undefined>(() =>
  visibleTabs.value.find(
    (t) => t.id === active.value && (t.kind === 'itgc-sheet' || t.kind === 'itgc-aux'),
  ),
)

/**
 * 顶层 section（由 active 派生）：
 * - matrix → 'matrix'；C21/C21-1 → 对应；控制点子页 → 其所属大类。
 * 设置时：matrix/C21/C21-1 直接切；大类则跳到该组首个子页（若 active 已在该组则保持）。
 */
const activeSection = computed<SectionKey>({
  get(): SectionKey {
    if (active.value === 'matrix') return 'matrix'
    const tab = sheetTabs.value.find((t) => t.id === active.value)
    if (!tab) return 'matrix'
    if (tab.kind === 'c21') return 'C21'
    if (tab.kind === 'c21-1') return 'C21-1'
    return tab.group as ItgcGroupKey
  },
  set(section: SectionKey) {
    if (section === 'matrix') { active.value = 'matrix'; return }
    if (section === 'C21' || section === 'C21-1') { active.value = section; return }
    // 大类：保持已在组内的 active，否则跳首个子页
    const subs = groupSubTabs(section)
    if (subs.length === 0) return
    if (!subs.some((t) => t.id === active.value)) {
      active.value = subs[0].id
    }
  },
})

/** 当前 section 是否为 4 大类分组（渲染二级可滚动页签 + 子页） */
const isGroupSection = computed(() => {
  const s = activeSection.value
  return s === '信息安全' || s === '运行维护' || s === '程序变更' || s === '新系统'
})

/** 当前大类下的二级子页（可滚动页签） */
const currentGroupTabs = computed<TabDef[]>(() =>
  isGroupSection.value ? groupSubTabs(activeSection.value) : [],
)

/** 当前 active 的独立底稿 Tab（C21 / C21-1） */
const activeDocTab = computed<TabDef | undefined>(() =>
  visibleTabs.value.find(
    (t) => t.id === active.value && (t.kind === 'c21' || t.kind === 'c21-1'),
  ),
)

/** 当前 active 控制点对应的矩阵行静态内容（供子页公式引用列） */
const activeMatrixInfo = computed(() => {
  const tab = activeControlTab.value
  if (!tab || tab.matrixRow == null) return null
  return matrixByRow.value[tab.matrixRow] ?? null
})

/** 子页字段保存后刷新完成状态/缺陷汇总（Req 7.3/7.4） */
async function onSubUpdated(): Promise<void> {
  await refreshCompletion()
}

// ─── 结论 → 颜色标签 ───
function conclusionTagType(v: string): '' | 'success' | 'warning' | 'danger' | 'info' {
  if (!v) return 'info'
  if (v.includes('无效')) return 'danger'
  if (v.includes('部分')) return 'warning'
  if (v.includes('有效')) return 'success'
  return 'info'
}

// ─── 点击矩阵控制点行 → 切换到对应子页 Tab（Req 3.3） ───
function onMatrixRowClick(tab: TabDef): void {
  if (visibleTabs.value.some((t) => t.id === tab.id)) {
    active.value = tab.id
  }
}

// ─── 仪表盘：状态 → 显示 ───
function statusDisplay(status: CompletionStatus) {
  return statusToDisplay(status)
}

// ─── 矩阵行内编辑（点选控件，Task 8.1 Req 10.1/10.2）───
// 矩阵总览面板允许直接点选 设计/执行有效性结论、是否异常、IT类别、应用系统。
// 保存到 checklist-responses（item_id = C22.{controlId}.{field}），与子页保持一致。

/** 保存矩阵行字段（结论/枚举/多选） */
async function saveMatrixField(
  controlId: string,
  field: 'design-conclusion' | 'exec-conclusion' | 'abnormal' | 'it-category' | 'app-system',
  value: string,
): Promise<void> {
  if (isReadonly.value || !props.wpId) return
  const slot = itgcFieldStorage(field)
  const item = {
    item_id: itgcItemId(controlId, field),
    conclusion: slot === 'conclusion' ? (value || null) : null,
    remark: slot === 'remark' ? (value || null) : null,
  }
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: projectIdRef.value || undefined,
      items: [item],
    })
    await refreshCompletion()
  } catch {
    // 静默：保存失败保留本地值
  }
}

/** 矩阵行：设计有效性结论变更 */
function onMatrixDesignChange(controlId: string, v: string): void {
  saveMatrixField(controlId, 'design-conclusion', v)
}
/** 矩阵行：执行有效性结论变更 */
function onMatrixExecChange(controlId: string, v: string): void {
  saveMatrixField(controlId, 'exec-conclusion', v)
}
/** 矩阵行：是否异常变更 */
function onMatrixAbnormalChange(controlId: string, v: string): void {
  saveMatrixField(controlId, 'abnormal', v)
}
/** 矩阵行：IT 控制类别变更（多选 → JSON 数组） */
function onMatrixCategoryChange(controlId: string, v: string[]): void {
  saveMatrixField(controlId, 'it-category', JSON.stringify(v))
}
/** 矩阵行：相关应用系统变更（多选 → JSON 数组） */
function onMatrixAppSystemChange(controlId: string, v: string[]): void {
  saveMatrixField(controlId, 'app-system', JSON.stringify(v))
}

/** 解析 JSON 数组字符串（多选字段回显） */
function parseJsonArray(raw: string): string[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) ? arr : [raw]
  } catch {
    return raw ? [raw] : []
  }
}

/** IT 类别列显示文本 */
function categoryDisplayText(raw: string): string {
  const arr = parseJsonArray(raw)
  return arr.length > 0 ? arr.join('、') : '—'
}
/** 应用系统列显示文本 */
function appSystemDisplayText(raw: string): string {
  const arr = parseJsonArray(raw)
  return arr.length > 0 ? arr.join('、') : '—'
}

// ─── sheetName 路由（Req 6.1~6.4） ───
/**
 * 激活指定 Tab（供 props.sheetName / URL ?sheet= / 外部 navigate 复用）。
 * - 合法且在可见 Tab 列表中 → 切换 active（activeSection 由 active 派生，
 *   路由到子页会自动选中所属大类分组 section，Req 6.1/6.2/6.3）。
 * - 非法 / 空 / 不可见 → 不改变 active，保持当前（默认 matrix，Req 6.4）。
 */
function activateSheet(v: string | null | undefined): void {
  const id = (v ?? '').trim()
  if (!id) return
  if (visibleTabs.value.some((t) => t.id === id)) {
    active.value = id
  }
}
watch(() => props.sheetName, (v) => activateSheet(v))
watch(() => route.query.sheet as string | undefined, (v) => activateSheet(v))

/** 子页 wp_id：C21/C21-1 用独立 wp_id；其余同工作簿用父 wpId */
function subWpId(tab: TabDef): string {
  if ((tab.kind === 'c21' || tab.kind === 'c21-1') && tab.wpCode) {
    return wpIdMap.value[tab.wpCode] || ''
  }
  return props.wpId
}

// ─── Lifecycle ───
onMounted(async () => {
  await Promise.all([selfLoadMatrix(), loadWpIndex(), refreshCompletion()])
  // 初始激活：props.sheetName 或 URL query
  const initial = props.sheetName || (route.query.sheet as string | undefined)
  activateSheet(initial)
})
</script>

<template>
  <div class="c22-itgc-bundle" v-loading="loading || selfLoading">
    <!-- ═══ 完成/缺陷仪表盘（Req 7.2/7.3 — 页签栏上方，三色 + 缺陷总数，实时更新） ═══ -->
    <div class="c22-progress-dashboard">
      <div class="c22-progress-dashboard__stats">
        <div class="c22-progress-dashboard__item c22-progress-dashboard__item--completed">
          <span class="c22-progress-dashboard__num">{{ progressSummary.completed }}</span>
          <span class="c22-progress-dashboard__label">已完成</span>
        </div>
        <div class="c22-progress-dashboard__item c22-progress-dashboard__item--inprogress">
          <span class="c22-progress-dashboard__num">{{ progressSummary.inProgress }}</span>
          <span class="c22-progress-dashboard__label">进行中</span>
        </div>
        <div class="c22-progress-dashboard__item c22-progress-dashboard__item--notstarted">
          <span class="c22-progress-dashboard__num">{{ progressSummary.notStarted }}</span>
          <span class="c22-progress-dashboard__label">未开始</span>
        </div>
        <span class="c22-progress-dashboard__divider" />
        <div class="c22-progress-dashboard__item c22-progress-dashboard__item--defect">
          <span class="c22-progress-dashboard__num">{{ progressSummary.defectCount }}</span>
          <span class="c22-progress-dashboard__label">缺陷总数</span>
        </div>
      </div>
      <el-progress
        class="c22-progress-dashboard__bar"
        :percentage="controlPointTabs.length
          ? Math.round((progressSummary.completed / controlPointTabs.length) * 100)
          : 0"
        :stroke-width="8"
        :color="[
          { color: '#67C23A', percentage: 100 },
          { color: '#E6A23C', percentage: 99 },
          { color: '#909399', percentage: 30 },
        ]"
      />
    </div>

    <!-- ═══ 顶层分组页签：matrix + 4 大类（SA/PE/PM/NS）+ C21 + C21-1（Req 4.1/4.2） ═══ -->
    <el-tabs v-model="activeSection" v-tab-wheel class="c22-top-tabs" type="card">
      <el-tab-pane
        v-for="sec in topSections"
        :key="sec.key"
        :name="sec.key"
        :label="sec.label"
      />
    </el-tabs>

    <!-- ═══ matrix 总览面板（默认，Req 3.1） ═══ -->
    <div v-if="activeSection === 'matrix'" class="c22-section c22-section--matrix">
        <!-- 操作引导（琥珀色方法论上下文，Req 10.4） -->
        <div class="c22-methodology-context">
          <div class="c22-methodology-context__header">
            <span class="c22-methodology-context__icon">📋</span>
            <span class="c22-methodology-context__title">方法论上下文 — ITGC 控制矩阵</span>
          </div>
          <div class="c22-methodology-context__body">
            IT 一般控制（ITGC）矩阵总览：按 4 大类（信息安全 SA / 运行维护 PE / 程序变更 PM / 新系统 NS）
            汇总各控制点的设计/执行有效性结论与缺陷。<br>
            <strong>操作：</strong>直接在表中点选设计/执行有效性结论、是否异常；IT 控制类别与相关应用系统支持多选。
            点击控制编号可跳转到对应控制域测试子页。
          </div>
        </div>

        <!-- ITGC 控制矩阵表（Req 3.2 + Req 10.1/10.2/10.5 交互增强） -->
        <table class="c22-matrix-table">
          <thead>
            <tr>
              <th style="width: 40px">状态</th>
              <th style="min-width: 120px">IT控制类别</th>
              <th style="min-width: 88px">风险编号</th>
              <th style="min-width: 80px">控制编号</th>
              <th style="min-width: 220px">控制描述</th>
              <th style="min-width: 140px">相关应用系统</th>
              <th style="min-width: 120px">设计有效性结论</th>
              <th style="min-width: 120px">执行有效性结论</th>
              <th style="min-width: 88px">是否异常</th>
              <th style="min-width: 88px">缺陷编号</th>
            </tr>
          </thead>
          <tbody>
            <tr
              v-for="r in matrixDisplayRows"
              :key="r.tab.id"
              class="c22-matrix-row"
              @click="onMatrixRowClick(r.tab)"
            >
              <td class="c22-cell-status">
                <span
                  class="c22-status-dot"
                  :style="{ color: statusDisplay(r.status).color }"
                >{{ statusDisplay(r.status).icon }}</span>
              </td>
              <!-- IT 控制类别（多选点选，Req 10.2） -->
              <td class="c22-cell-select" @click.stop>
                <el-select
                  v-if="!isReadonly"
                  :model-value="parseJsonArray(r.itCategory)"
                  multiple
                  collapse-tags
                  collapse-tags-tooltip
                  size="small"
                  placeholder="选择类别"
                  class="c22-inline-select"
                  @change="(v: string[]) => onMatrixCategoryChange(r.tab.id, v)"
                >
                  <el-option v-for="o in IT_CATEGORY_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
                <span v-else class="c22-cell-text">{{ categoryDisplayText(r.itCategory) }}</span>
              </td>
              <!-- 风险编号（tooltip 展示完整风险描述，Req 10.5） -->
              <td>
                <el-tooltip
                  v-if="r.risk"
                  :content="`风险描述：${r.risk}`"
                  placement="top"
                  :show-after="200"
                  :max-width="320"
                >
                  <span class="c22-cell-code c22-cell-tooltip">{{ r.riskNo || r.risk }}</span>
                </el-tooltip>
                <span v-else class="c22-cell-empty">—</span>
              </td>
              <!-- 控制编号（tooltip 展示完整控制描述，Req 10.5；点击跳子页） -->
              <td>
                <el-tooltip
                  v-if="r.description"
                  :content="`控制描述：${r.description}`"
                  placement="top"
                  :show-after="200"
                  :max-width="400"
                >
                  <span class="c22-cell-code c22-cell-link">{{ r.controlNo }}</span>
                </el-tooltip>
                <span v-else class="c22-cell-code c22-cell-link">{{ r.controlNo }}</span>
              </td>
              <td class="c22-cell-desc">{{ r.description || '—' }}</td>
              <!-- 相关应用系统（多选点选，Req 10.2） -->
              <td class="c22-cell-select" @click.stop>
                <el-select
                  v-if="!isReadonly"
                  :model-value="parseJsonArray(r.appSystem)"
                  multiple
                  filterable
                  allow-create
                  collapse-tags
                  collapse-tags-tooltip
                  size="small"
                  placeholder="选择系统"
                  class="c22-inline-select"
                  @change="(v: string[]) => onMatrixAppSystemChange(r.tab.id, v)"
                >
                  <el-option v-for="o in APP_SYSTEM_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
                <span v-else class="c22-cell-text">{{ appSystemDisplayText(r.appSystem) }}</span>
              </td>
              <!-- 设计有效性结论（下拉点选，Req 10.1） -->
              <td class="c22-cell-select" @click.stop>
                <el-select
                  v-if="!isReadonly"
                  :model-value="r.designConclusion || ''"
                  size="small"
                  clearable
                  placeholder="请选择"
                  class="c22-inline-select c22-inline-select--conclusion"
                  @change="(v: string) => onMatrixDesignChange(r.tab.id, v)"
                >
                  <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
                <template v-else>
                  <el-tag v-if="r.designConclusion" :type="conclusionTagType(r.designConclusion)" size="small" effect="plain">{{ r.designConclusion }}</el-tag>
                  <span v-else class="c22-cell-empty">—</span>
                </template>
              </td>
              <!-- 执行有效性结论（下拉点选，Req 10.1） -->
              <td class="c22-cell-select" @click.stop>
                <el-select
                  v-if="!isReadonly"
                  :model-value="r.execConclusion || ''"
                  size="small"
                  clearable
                  placeholder="请选择"
                  class="c22-inline-select c22-inline-select--conclusion"
                  @change="(v: string) => onMatrixExecChange(r.tab.id, v)"
                >
                  <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                </el-select>
                <template v-else>
                  <el-tag v-if="r.execConclusion" :type="conclusionTagType(r.execConclusion)" size="small" effect="plain">{{ r.execConclusion }}</el-tag>
                  <span v-else class="c22-cell-empty">—</span>
                </template>
              </td>
              <!-- 是否异常（单选点选，Req 10.1） -->
              <td class="c22-cell-select" @click.stop>
                <el-select
                  v-if="!isReadonly"
                  :model-value="r.abnormal || ''"
                  size="small"
                  clearable
                  placeholder="—"
                  class="c22-inline-select c22-inline-select--sm"
                  @change="(v: string) => onMatrixAbnormalChange(r.tab.id, v)"
                >
                  <el-option label="是" value="是" />
                  <el-option label="否" value="否" />
                </el-select>
                <template v-else>
                  <el-tag v-if="r.abnormal" :type="r.abnormal === '是' ? 'danger' : 'success'" size="small" effect="plain">{{ r.abnormal }}</el-tag>
                  <span v-else class="c22-cell-empty">—</span>
                </template>
              </td>
              <td>
                <span v-if="r.defectNo" class="c22-cell-defect">{{ r.defectNo }}</span>
                <span v-else class="c22-cell-empty">—</span>
              </td>
            </tr>
            <tr v-if="matrixDisplayRows.length === 0">
              <td colspan="10" class="c22-empty-row">暂无控制点数据</td>
            </tr>
          </tbody>
        </table>
    </div>

    <!-- ═══ 4 大类分组：二级可滚动页签 + IT 控制域子页（Req 4.2/4.3/4.4） ═══ -->
    <div v-else-if="isGroupSection" class="c22-section c22-section--group">
      <el-tabs v-model="active" v-tab-wheel class="c22-sub-tabs" type="card">
        <el-tab-pane
          v-for="tab in currentGroupTabs"
          :key="tab.id"
          :name="tab.id"
        >
          <template #label>
            <span class="c22-tab-label">
              <span class="c22-tab-id">{{ tab.label }}</span>
              <span
                v-if="completionMap[tab.id]"
                class="c22-tab-dot"
                :style="{ color: statusDisplay(completionMap[tab.id]).color }"
              >{{ statusDisplay(completionMap[tab.id]).icon }}</span>
            </span>
          </template>
        </el-tab-pane>
      </el-tabs>

      <!-- 子页交互渲染（设计有效性 + 执行有效性 + 样本记录 + 缺陷评估） -->
      <GtC22ControlSheet
        v-if="activeControlTab && subWpId(activeControlTab)"
        :key="activeControlTab.id"
        :wp-id="subWpId(activeControlTab)"
        :project-id="projectIdRef"
        :tab="activeControlTab"
        :matrix-row="activeMatrixInfo"
        :readonly="isReadonly"
        @updated="onSubUpdated"
      />
      <div v-else class="c22-empty-sub">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
    </div>

    <!-- ═══ C21-1 IT 发现汇总（交互式，缺陷联动汇总，Task 5.1） ═══ -->
    <div v-else-if="activeSection === 'C21-1'" class="c22-section c22-section--doc">
      <GtC21FindingsSummary
        :wp-id="wpId"
        :project-id="projectIdRef"
        :defects="defects"
        :readonly="isReadonly"
        @updated="onSubUpdated"
      />
    </div>

    <!-- ═══ C21 独立底稿（IT 专业成员，OnlyOffice；详见 Task 5.2） ═══ -->
    <div v-else class="c22-section c22-section--doc">
      <GtOnlyOfficeSheet
        v-if="activeDocTab && subWpId(activeDocTab)"
        :key="activeDocTab.id"
        :wp-id="subWpId(activeDocTab)"
        :project-id="projectIdRef"
        :sheet-name="activeDocTab.wpCode || ''"
        :readonly="isReadonly"
        style="height: calc(100vh - 220px)"
      />
      <div v-else class="c22-empty-sub">该子底稿尚未生成，请先在底稿管理中生成底稿</div>
    </div>
  </div>
</template>

<style scoped>
.c22-itgc-bundle {
  padding: 12px;
  font-size: 13px;
}

/* 顶层分组页签 */
.c22-top-tabs {
  margin-bottom: 8px;
}
.c22-top-tabs :deep(.el-tabs__content) {
  display: none; /* 顶层仅作导航，内容由 section 渲染 */
}
.c22-top-tabs :deep(.el-tabs__nav-scroll) {
  scroll-behavior: smooth;
}

/* 二级可滚动子页页签 */
.c22-sub-tabs {
  margin-bottom: 12px;
}
.c22-sub-tabs :deep(.el-tabs__content) {
  display: none; /* 子页内容由下方 GtC22ControlSheet 渲染 */
}
.c22-sub-tabs :deep(.el-tabs__nav-scroll) {
  scroll-behavior: smooth;
}

/* section 容器 */
.c22-section {
  min-height: 200px;
}

.c22-tab-label {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  line-height: 1.2;
}
.c22-tab-id {
  font-size: 13px;
  font-weight: 600;
}
.c22-tab-dot {
  font-size: 12px;
  font-weight: 700;
}

/* 引导区（琥珀色方法论上下文，Req 10.4） */
.c22-methodology-context {
  margin-bottom: 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  overflow: hidden;
}
.c22-methodology-context__header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 12px 4px;
  font-weight: 600;
  color: #7d5b1e;
}
.c22-methodology-context__icon {
  font-size: 15px;
}
.c22-methodology-context__title {
  font-size: 13px;
}
.c22-methodology-context__body {
  padding: 2px 12px 10px;
  color: #7d5b1e;
  line-height: 1.6;
  font-size: 12px;
}
.c22-guide {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  margin-bottom: 12px;
  background: #fdf6ec;
  border-left: 3px solid #e6a23c;
  border-radius: 4px;
  color: #7d5b1e;
  line-height: 1.5;
}
.c22-guide-icon {
  font-size: 16px;
}

/* 完成/缺陷仪表盘（页签栏上方，三色 + 缺陷总数，实时更新 Req 7.2/7.3） */
.c22-progress-dashboard {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 10px 16px;
  margin-bottom: 8px;
  background: var(--gt-color-bg-elevated, #f5f7fa);
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  border-radius: 6px;
}
.c22-progress-dashboard__stats {
  display: flex;
  align-items: center;
  gap: 14px;
}
.c22-progress-dashboard__item {
  display: flex;
  flex-direction: column;
  align-items: center;
  min-width: 50px;
}
.c22-progress-dashboard__num {
  font-size: 20px;
  font-weight: 700;
  line-height: 1;
}
.c22-progress-dashboard__label {
  font-size: 11px;
  color: var(--gt-color-text-secondary, #606266);
  margin-top: 2px;
}
.c22-progress-dashboard__item--completed .c22-progress-dashboard__num { color: #67c23a; }
.c22-progress-dashboard__item--inprogress .c22-progress-dashboard__num { color: #e6a23c; }
.c22-progress-dashboard__item--notstarted .c22-progress-dashboard__num { color: #909399; }
.c22-progress-dashboard__item--defect .c22-progress-dashboard__num { color: #f56c6c; }
.c22-progress-dashboard__divider {
  width: 1px;
  height: 28px;
  background: var(--gt-color-border-light, #dcdfe6);
}
.c22-progress-dashboard__bar {
  flex: 1;
  min-width: 140px;
}

/* 矩阵表 */
.c22-matrix-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}
.c22-matrix-table th,
.c22-matrix-table td {
  border: 1px solid var(--gt-color-border-light, #ebeef5);
  padding: 6px 8px;
  text-align: left;
  vertical-align: middle;
}
.c22-matrix-table thead th {
  background: var(--gt-color-bg-elevated, #f5f7fa);
  font-weight: 600;
  color: var(--gt-color-text, #303133);
  position: sticky;
  top: 0;
  z-index: 1;
}
.c22-matrix-row {
  cursor: pointer;
  transition: background 0.15s;
}
.c22-matrix-row:hover {
  background: var(--gt-color-primary-bg, #ecf5ff);
}
.c22-cell-status {
  text-align: center;
}
.c22-status-dot {
  font-size: 15px;
  font-weight: 700;
}
.c22-cell-code {
  font-family: var(--gt-font-mono, monospace);
  font-weight: 600;
}
.c22-cell-link {
  color: var(--gt-color-primary, #409eff);
  text-decoration: underline dotted;
  cursor: pointer;
}
.c22-cell-link:hover {
  color: var(--gt-color-primary-dark, #337ecc);
}
.c22-cell-tooltip {
  text-decoration: underline dotted;
  cursor: help;
}
.c22-cell-desc {
  color: var(--gt-color-text-secondary, #606266);
  line-height: 1.4;
}
.c22-cell-select {
  padding: 2px 4px;
}
.c22-inline-select {
  width: 100%;
  min-width: 100px;
}
.c22-inline-select--conclusion {
  min-width: 100px;
}
.c22-inline-select--sm {
  min-width: 72px;
}
.c22-cell-text {
  font-size: 12px;
  color: var(--gt-color-text-secondary, #606266);
}
.c22-cell-defect {
  color: #f56c6c;
  font-weight: 600;
}
.c22-cell-empty {
  color: var(--gt-color-text-placeholder, #c0c4cc);
}
.c22-empty-row,
.c22-empty-sub {
  text-align: center;
  padding: 32px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
