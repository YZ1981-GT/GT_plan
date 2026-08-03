<script setup lang="ts">
/**
 * D4TabDisclosureListed — 附注披露（上市公司版）
 *
 * 8 小节卡片（源模板 `附注披露信息（上市公司）` A1:I85）:
 * (1) 营业收入和营业成本（跨sheet自动取数 D4-1/D4-2/M循环，4 数据列）
 * (2) 营业收入、营业成本按行业（或产品类型）划分（动态行，4 数据列）
 * (3) 营业收入、营业成本按地区划分（动态行，4 数据列；叶子列名 = 主营业务收入/主营业务成本，源 R37）
 * (4) 营业收入、营业成本按分解信息（收入时点/时段）
 * (5)~(8) 文字说明区
 *
 * 🔴 两版（3）叶子列名不得统一（Property 12 / Req 4.3）：
 *   上市 = 主营业务收入/主营业务成本（源 R37）
 *   国企 = 收入/成本（源 R31）
 *
 * spec: d4-four-table-extraction-and-disclosure-alignment (Task 5.2)
 * Requirements: 4.2, 4.3, 4.8
 */
import { ref, computed, onMounted, onBeforeUnmount, inject } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDebounceFn } from '@vueuse/core'
import http from '@/utils/http'
import { useDisplayPrefsStore, DisplayPrefs_Key } from '@/stores/displayPrefs'
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { useD4Disclosure } from '../../composables/useD4Disclosure'
import { useD4DisclosureAi } from '../../composables/useD4DisclosureAi'
import { buildD4SyncPayload, D4_NOTE_SECTION, type D4DisclosureSnapshot } from '../../composables/d4NoteSectionMap'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { parseNum } from '../../composables/useD4FormulaEngine'
import { getDisclosureNoteDetail } from '@/services/auditPlatformApi'
import { useAuditContext } from '@/composables/useAuditContext'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { D4_MAIN_REVENUE_STANDARD, D4_OTHER_REVENUE_STANDARD, D4_MAIN_COST_STANDARD, D4_OTHER_COST_STANDARD } from '../../composables/d4AccountScope'
import {
  D4_TRANSPOSE_CHECK_ITEMS,
  buildD4ObligationColumns,
  deriveObligationTotal,
  getObligationYearKeys,
  buildD4TwoPeriodColumns,
  type D4ObligationRow,
  type D4TwoPeriodRow,
} from '../../composables/d4DisclosureModel'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  htmlData?: any
  applicableStandards?: string[]
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

/**
 * 🔴 金额格式单一真源 = displayPrefs store 成员（不是模块级导出）。
 * setup 顶层 inject —— 写进函数体会静默失效（useDisplayPrefsStore 是 setup 作用域 composable）。
 */
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

// ─── Debounced batch save ──────────────────────────────────────────────────
const pendingItems = ref<any[]>([])

/**
 * 🔴 同一批次不得重复提交相同 `item_id` —— 后端会**整批拒绝**，该批全部数据丢失。
 *
 * 披露表把每张动态表整表存成一个 JSON item，2 秒防抖窗口内改同一张表两个格子
 * 就必然产生两条同 id 记录。D1 已浏览器实测中招（界面有值但库里根本没有这个键）。
 * 按 item_id 去重，**后写覆盖先写**（累积顺序即时间顺序，最后一条是最新整表快照）。
 *
 * 守卫：`__tests__/disclosureSaveBatchDedupe.spec.ts`
 */
function dedupeByItemId(items: any[]): any[] {
  const byId = new Map<string, any>()
  for (const it of items) {
    const key = String(it?.item_id ?? '')
    if (!key) continue
    byId.set(key, it)
  }
  return [...byId.values()]
}

const debouncedFlush = useDebounceFn(async () => {
  if (pendingItems.value.length === 0) return
  const items = dedupeByItemId(pendingItems.value)
  pendingItems.value = []
  if (items.length === 0) return
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, { items }, { _silent: true } as any)
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  } catch (err) {
    // 保存失败必须让用户知道（旧实现完全静默 → 数据丢了没人发现）
    ElMessage.warning('披露表保存失败，请检查网络后重新编辑该单元格')
    // eslint-disable-next-line no-console
    console.error('[D4Disclosure] checklist-responses 保存失败', err)
  }
}, 2000)

function saveBatch(items: any[]) {
  pendingItems.value.push(...items)
  debouncedFlush()
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())

// ─── Composable ──────────────────────────────────────────────────────────────
const allResponsesRef = computed(() => props.allResponses) as any
const wpIdRef = computed(() => props.wpId) as any
const projectIdRef = computed(() => props.projectId) as any
const isReadonlyRef = computed(() => props.isReadonly) as any

const {
  crossSheetRevenue, crossSheetCost,
  isRefreshing, lastRefreshTime, refreshFromTb,
  section1Data, section1Total, grossMarginRate, priorGrossMarginRate,
  section2Rows, section2Total, addSection2Row, removeSection2Row, updateSection2, seedSection2FromSegmentPrefill,
  section3Rows, section3Total, addSection3Row, removeSection3Row, updateSection3,
  section4Rows, section4Total, addSection4Row, removeSection4Row, updateSection4,
  // 列转置专用
  section4Categories, section4Cells,
  getSection4Cell, updateSection4Cell,
  addSection4Category, removeSection4Category, renameSection4Category,
  section4RowTotal, section4ColTotal,
  noteTexts, updateNote,
} = useD4Disclosure({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  variant: 'listed',
  saveBatch,
  isReadonly: isReadonlyRef,
})

// ─── 列转置辅助常量 ─────────────────────────────────────────────────────────
const transposeCheckItems = D4_TRANSPOSE_CHECK_ITEMS

// ─── （6）剩余履约义务结构化表 ─────────────────────────────────────────────────
const SECTION6_KEY = 'D4-disc-listed-section6-rows'
const obligationYearKeys = computed(() => getObligationYearKeys(auditYear.value))
const obligationColumns = computed(() => buildD4ObligationColumns(auditYear.value))

const section6Rows = computed<D4ObligationRow[]>(() => {
  const raw = props.allResponses?.get(SECTION6_KEY)
  if (raw && typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return [] }
  }
  if (Array.isArray(raw)) return raw
  return []
})

function persistSection6(rows: D4ObligationRow[]): void {
  saveBatch([{ item_id: SECTION6_KEY, conclusion: JSON.stringify(rows) }])
}

function addSection6Row(): void {
  const rows = [...section6Rows.value, { label: '' } as D4ObligationRow]
  persistSection6(rows)
}

function removeSection6Row(idx: number): void {
  const rows = [...section6Rows.value]
  rows.splice(idx, 1)
  persistSection6(rows)
}

function updateSection6Cell(idx: number, field: string, value: string | number | null): void {
  const rows = section6Rows.value.map((r, i) => (i === idx ? { ...r, [field]: value } : r))
  persistSection6(rows)
}

function getSection6Total(field: string): number | null {
  if (field === 'total') {
    // total of totals = sum of each row's total
    let sum: number | null = null
    for (const row of section6Rows.value) {
      const t = deriveObligationTotal(row, auditYear.value)
      if (t !== null) { sum = (sum ?? 0) + t }
    }
    return sum
  }
  let sum: number | null = null
  for (const row of section6Rows.value) {
    const v = row[field]
    if (typeof v === 'number') { sum = (sum ?? 0) + v }
  }
  return sum
}

// ─── （8）试运行销售收入结构化表（仅上市） ──────────────────────────────────────
const SECTION8_KEY = 'D4-disc-listed-section8-rows'
const TRIAL_RUN_FIXED_ROWS = ['固定资产试运行收入', '研发样品销售收入'] as const

const section8Rows = computed<D4TwoPeriodRow[]>(() => {
  const raw = props.allResponses?.get(SECTION8_KEY)
  let parsed: D4TwoPeriodRow[] = []
  if (raw && typeof raw === 'string') {
    try { parsed = JSON.parse(raw) } catch { /* empty */ }
  } else if (Array.isArray(raw)) {
    parsed = raw
  }
  // Ensure fixed rows exist
  if (parsed.length === 0) {
    parsed = TRIAL_RUN_FIXED_ROWS.map(label => ({
      label,
      endRevenue: null, endCost: null, priorRevenue: null, priorCost: null,
    }))
  }
  return parsed
})

function persistSection8(rows: D4TwoPeriodRow[]): void {
  saveBatch([{ item_id: SECTION8_KEY, conclusion: JSON.stringify(rows) }])
}

function updateSection8Cell(idx: number, field: keyof D4TwoPeriodRow, value: number | null): void {
  const rows = section8Rows.value.map((r, i) => (i === idx ? { ...r, [field]: value } : r))
  persistSection8(rows)
}

// ─── （2）从四表配对带入处理器 ─────────────────────────────────────────────────

/**
 * 从 render 下发的 segment_prefill 带入按行业/产品类型数据。
 * 手工已填的行不覆盖。
 * spec: d4-four-table-extraction-and-disclosure-alignment (Fix 3)
 */
function handleSeedFromSegmentPrefill(): void {
  const segmentPrefill = props.htmlData?.segment_prefill
  if (!segmentPrefill || !Array.isArray(segmentPrefill) || segmentPrefill.length === 0) {
    ElMessage.info('暂无四表配对数据（请确认四表已入库且灰度开关已开启）')
    return
  }
  const count = seedSection2FromSegmentPrefill(segmentPrefill)
  if (count > 0) {
    ElMessage.success(`已从四表配对带入 ${count} 项数据`)
  } else {
    ElMessage.info('所有行已有手工数据，未覆盖')
  }
}

// ─── （4）类别操作处理器（ElMessageBox.prompt 先命名再创建）─────────────────────
async function handleAddCategory(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入新增类别名称', '添加分解类别', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '类别名称不能为空',
    })
    if (value?.trim()) {
      addSection4Category(value.trim())
    }
  } catch { /* 用户取消 */ }
}

async function handleRenameCategory(catKey: string, currentLabel: string): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入新名称', `重命名类别「${currentLabel}」`, {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: currentLabel,
      inputPattern: /\S+/,
      inputErrorMessage: '类别名称不能为空',
    })
    if (value?.trim() && value.trim() !== currentLabel) {
      renameSection4Category(catKey, value.trim())
    }
  } catch { /* 用户取消 */ }
}

async function handleRemoveCategory(catKey: string, label: string): Promise<void> {
  try {
    await ElMessageBox.confirm(
      `确定删除类别「${label}」？该类别下所有已录入的收入/成本数据将一并删除。`,
      '删除分解类别',
      { confirmButtonText: '确定删除', cancelButtonText: '取消', type: 'warning' },
    )
    removeSection4Category(catKey)
  } catch { /* 用户取消 */ }
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const VARIANT: DisclosureVariant = 'listed'
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D4', target)
  if (route) router.push(route)
}

function buildSnapshot(): D4DisclosureSnapshot {
  return {
    revenueRows: section1Data.value.map((r: any) => ({
      label: r.category,
      currentRevenue: r.currentRevenue, currentCost: r.currentCost,
      priorRevenue: r.priorRevenue, priorCost: r.priorCost,
    })),
    revenueTotal: {
      label: section1Total.value.category,
      currentRevenue: section1Total.value.currentRevenue, currentCost: section1Total.value.currentCost,
      priorRevenue: section1Total.value.priorRevenue, priorCost: section1Total.value.priorCost,
    },
    industryRows: section2Rows.value.map((r: any) => ({
      label: r.category, currentRevenue: parseNum(r.currentAmount), currentCost: parseNum(r.priorAmount),
    })),
    regionRows: section3Rows.value.map((r: any) => ({
      label: r.name, currentRevenue: parseNum(r.amount), currentCost: parseNum(r.proportion),
    })),
    timingRows: D4_TRANSPOSE_CHECK_ITEMS.map((checkLabel) => {
      const row: Record<string, string | number | null> = { label: checkLabel }
      let totalRev = 0
      let totalCost = 0
      for (const cat of section4Categories.value) {
        const rv = getSection4Cell(checkLabel, cat.key, 'revenue')
        const cv = getSection4Cell(checkLabel, cat.key, 'cost')
        row[`${cat.key}_revenue`] = rv
        row[`${cat.key}_cost`] = cv
        totalRev += (typeof rv === 'number' ? rv : 0)
        totalCost += (typeof cv === 'number' ? cv : 0)
      }
      row.total_revenue = totalRev
      row.total_cost = totalCost
      return row
    }),
    timingCategories: section4Categories.value.map((c: any) => ({ key: c.key, label: c.label })),
    notes: { ...noteTexts.value },
  }
}

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const payload = buildD4SyncPayload(VARIANT, props.wpId || '', null, buildSnapshot())
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { wpCode: 'D4', accountCode: D4_MAIN_REVENUE_STANDARD, projectId: props.projectId, section: VARIANT, sectionIds: [D4_NOTE_SECTION[VARIANT]] },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D4_NOTE_SECTION[VARIANT]} 营业收入和营业成本」`)
    await checkNoteConsistency(true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// ─── 校对附注一致性（只读比对，不改附注）───────────────────────────────────────────
const { year: auditYear } = useAuditContext()

const noteCheckState = ref<{ status: 'idle' | 'loading' | 'ok' | 'diff' | 'missing' | 'error'; message: string }>({
  status: 'idle',
  message: '',
})

async function checkNoteConsistency(silent = false): Promise<void> {
  if (!props.projectId) return
  noteCheckState.value = { status: 'loading', message: '正在读取附注现存数据…' }
  try {
    const detail = await getDisclosureNoteDetail(props.projectId, auditYear.value, D4_NOTE_SECTION[VARIANT])
    const td = detail?.table_data
    const tables: any[] = Array.isArray(td?._tables) ? td._tables : []
    const candidates = tables.length > 0 ? tables : (Array.isArray(td?.rows) ? [{ rows: td.rows }] : [])
    let noteTotal: number | null = null
    for (const t of candidates) {
      const rows: any[] = Array.isArray(t?.rows) ? t.rows : []
      const totalRow = rows.find((r: any) => r?.is_total || String(r?.label ?? '').trim() === '合计')
      if (!totalRow) continue
      const values: any[] = Array.isArray(totalRow.values) ? totalRow.values : []
      for (const v of values) {
        const n = Number(v)
        if (Number.isFinite(n) && n !== 0) { noteTotal = n; break }
      }
      if (noteTotal !== null) break
    }
    const pageTotal = section1Total.value.currentRevenue ?? 0
    if (noteTotal === null) {
      noteCheckState.value = { status: 'missing', message: `附注「${D4_NOTE_SECTION[VARIANT]}」暂无可比对的合计行（尚未同步或附注为空）` }
    } else if (Math.abs(noteTotal - pageTotal) <= 0.01) {
      noteCheckState.value = { status: 'ok', message: `附注现存收入合计与本页一致` }
    } else {
      noteCheckState.value = { status: 'diff', message: `附注现存合计 ${fmtAmt(noteTotal)} 与本页收入合计 ${fmtAmt(pageTotal)} 不一致（差异 ${fmtAmt(noteTotal - pageTotal)}）` }
    }
    if (!silent) {
      if (noteCheckState.value.status === 'ok') ElMessage.success(noteCheckState.value.message)
      else ElMessage.warning(noteCheckState.value.message)
    }
  } catch {
    noteCheckState.value = { status: 'error', message: '读取附注数据失败（附注可能尚未生成）' }
    if (!silent) ElMessage.warning(noteCheckState.value.message)
  }
}


// ─── Format helpers ──────────────────────────────────────────────────────────
function fmtAmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}

function fmtPct(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toFixed(2) + '%'
}

// ─── AI 辅助生成 ─────────────────────────────────────────────────────────────
const { aiLoading, aiGenerate } = useD4DisclosureAi({
  wpId: computed(() => props.wpId),
  variant: 'listed',
  getNoteText: (k) => noteTexts.value[k] || '',
  setNoteText: (k, v) => updateNote(k, v),
})

// ─── 公式管理 ────────────────────────────────────────────────────────────────
const showFormulaDrawer = ref(false)

// 公式映射表：描述每个自动填充单元格的数据来源
const formulaMap = [
  { field: '主营业务-本期收入', source: 'trial_balance', formula: `SUM(audited_amount WHERE standard_account_code=${D4_MAIN_REVENUE_STANDARD})`, account: D4_MAIN_REVENUE_STANDARD },
  { field: '其他业务-本期收入', source: 'trial_balance', formula: `SUM(audited_amount WHERE standard_account_code=${D4_OTHER_REVENUE_STANDARD})`, account: D4_OTHER_REVENUE_STANDARD },
  { field: '主营业务-本期成本', source: 'trial_balance', formula: `SUM(audited_amount WHERE standard_account_code=${D4_MAIN_COST_STANDARD})`, account: D4_MAIN_COST_STANDARD },
  { field: '其他业务-本期成本', source: 'trial_balance', formula: `SUM(audited_amount WHERE standard_account_code=${D4_OTHER_COST_STANDARD})`, account: D4_OTHER_COST_STANDARD },
  { field: '主营业务-上期收入', source: 'trial_balance(year-1)', formula: `SUM(audited_amount WHERE code=${D4_MAIN_REVENUE_STANDARD}, year=prior)`, account: D4_MAIN_REVENUE_STANDARD },
  { field: '其他业务-上期收入', source: 'trial_balance(year-1)', formula: `SUM(audited_amount WHERE code=${D4_OTHER_REVENUE_STANDARD}, year=prior)`, account: D4_OTHER_REVENUE_STANDARD },
  { field: '主营业务-上期成本', source: 'trial_balance(year-1)', formula: `SUM(audited_amount WHERE code=${D4_MAIN_COST_STANDARD}, year=prior)`, account: D4_MAIN_COST_STANDARD },
  { field: '其他业务-上期成本', source: 'trial_balance(year-1)', formula: `SUM(audited_amount WHERE code=${D4_OTHER_COST_STANDARD}, year=prior)`, account: D4_OTHER_COST_STANDARD },
  { field: '毛利率', source: '计算', formula: '(总收入 - 总成本) / 总收入 × 100%', account: '-' },
]
</script>

<template>
  <div class="d4-disclosure-listed">
    <!-- 工具栏 -->
    <div class="disclosure-toolbar">
      <el-button size="small" :loading="isRefreshing" @click="refreshFromTb">🔄 全量刷新取数</el-button>
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、62 营业收入和营业成本）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote('listed')" @command="jumpToNote">
        ↩ 跳转回附注（五、62）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、62）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、64）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" @click="showFormulaDrawer = true">ƒx 公式管理</el-button>
      <el-button size="small" @click="checkNoteConsistency(false)" title="只读校对本页收入合计与附注合计是否一致">校对附注</el-button>
      <span v-if="lastRefreshTime" class="toolbar-hint">
        上次取数：{{ lastRefreshTime.slice(0,16).replace('T',' ') }}
      </span>
    </div>

    <!-- 附注校对结果 -->
    <el-alert
      v-if="noteCheckState.status === 'ok' || noteCheckState.status === 'diff' || noteCheckState.status === 'missing'"
      :type="noteCheckState.status === 'ok' ? 'success' : (noteCheckState.status === 'diff' ? 'warning' : 'info')"
      show-icon
      :closable="true"
      style="margin: 0 0 8px"
      :title="noteCheckState.message"
    />

    <!-- 公式管理抽屉 -->
    <el-drawer v-model="showFormulaDrawer" title="公式管理 - 数据来源映射" size="480px" direction="rtl">
      <div class="formula-drawer-content">
        <p class="formula-desc">以下字段从试算表(trial_balance)自动提取审定数，点击"🔄全量刷新取数"更新。</p>
        <el-table :data="formulaMap" border size="small" style="width: 100%">
          <el-table-column prop="field" label="字段" width="160" />
          <el-table-column prop="source" label="数据源" width="130" />
          <el-table-column prop="formula" label="公式/取数逻辑" min-width="200">
            <template #default="{ row }">
              <code class="formula-code">{{ row.formula }}</code>
            </template>
          </el-table-column>
          <el-table-column prop="account" label="科目" width="60" align="center" />
        </el-table>
        <el-divider />
        <h4>自动提取区域（刷新时从其他sheet汇总）</h4>
        <ul class="formula-manual-list">
          <li>(2) 按行业/产品类型 — 从D4-2主营明细按产品名汇总 + D4-3其他收入</li>
          <li>(3) 按地区 — 需手工录入（地区维度数据暂无对应sheet）</li>
        </ul>
        <h4>手工填写区域</h4>
        <ul class="formula-manual-list">
          <li>(4) 收入分解信息 — 手工录入时点/时段分解</li>
          <li>(5)~(8) 文字描述 — 手工填写或AI生成</li>
        </ul>
      </div>
    </el-drawer>
    <!-- (1) 营业收入和营业成本 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(1) 营业收入和营业成本</span>
          <div class="header-actions">
            <el-tag size="small" type="info" effect="plain">TB:6001</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6051</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6401</el-tag>
            <el-tag size="small" type="info" effect="plain">TB:6402</el-tag>
          </div>
        </div>
      </template>
      <div v-if="lastRefreshTime" class="refresh-hint">
        数据来源：trial_balance 审定数 · 公式：收入=6001+6051, 成本=6401+6402, 毛利=收入-成本 · {{ lastRefreshTime.slice(0,16).replace('T',' ') }}
      </div>
      <!-- 方法论上下文 -->
      <div class="method-context">
        <p>1. 处置投资性房地产的收入在"其他业务收入"列示，相应结转成本至"其他业务成本"，不计入"资产处置损益"。</p>
        <p>2. 停工停产期间继续计提固定资产折旧和无形资产摊销，计入营业成本。</p>
        <p>3. 披露本公司前期已经履行(或部分履行)的履约义务在本期调整的收入金额及原因。</p>
      </div>
      <el-table :data="[...section1Data, section1Total]" border size="small" class="disclosure-table">
        <el-table-column prop="category" label="项目" min-width="120" />
        <el-table-column label="本期收入" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId !== '__total__' ? 'cross-sheet-cell' : 'font-bold'">{{ fmtAmt(row.currentRevenue) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="110" align="right">
          <template #default="{ row }"><span :class="[row.currentCost === 0 ? 'placeholder-cell' : 'cross-sheet-cell', row.rowId === '__total__' ? 'font-bold' : '']">{{ row.currentCost === 0 ? '待刷新' : fmtAmt(row.currentCost) }}</span></template>
        </el-table-column>
        <el-table-column label="上期收入" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId === '__total__' ? 'font-bold' : ''">{{ fmtAmt(row.priorRevenue) }}</span></template>
        </el-table-column>
        <el-table-column label="上期成本" min-width="110" align="right">
          <template #default="{ row }"><span :class="row.rowId === '__total__' ? 'font-bold' : ''">{{ row.priorCost === 0 ? '-' : fmtAmt(row.priorCost) }}</span></template>
        </el-table-column>
      </el-table>
      <div class="note-area"><el-input :model-value="noteTexts['note-1']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明：披露前期已履行的履约义务在本期调整的收入金额及原因..." :disabled="isReadonly" @input="(v: string) => updateNote('note-1', v)" /></div>
    </el-card>

    <!-- (2) 按行业/产品类型划分 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(2) 营业收入、营业成本按行业（或产品类型）划分</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSeedFromSegmentPrefill">从四表配对带入</el-button>
            <el-button size="small" :disabled="isReadonly" @click="addSection2Row">+ 添加行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="section2Rows" border size="small" class="disclosure-table">
        <el-table-column label="主要产品类型（或行业）" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.category" size="small" placeholder="如：消费品/汽车/能源/销售材料..." @change="(v: string) => updateSection2(row.rowId, 'category', v)" />
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期收入" min-width="100" align="right">
          <template #default="{ row }"><WpAmountInput v-if="!isReadonly" :model-value="row.currentAmount" size="small" @update:model-value="(v: number) => updateSection2(row.rowId, 'currentAmount', v)" /><span v-else>{{ fmtAmt(row.currentAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="本期成本" min-width="100" align="right">
          <template #default="{ row }"><WpAmountInput v-if="!isReadonly" :model-value="row.priorAmount" size="small" @update:model-value="(v: number) => updateSection2(row.rowId, 'priorAmount', v)" /><span v-else>{{ fmtAmt(row.priorAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="上期收入" min-width="100" align="right">
          <template #default="{ row }"><span class="placeholder-cell">-</span></template>
        </el-table-column>
        <el-table-column label="上期成本" min-width="100" align="right">
          <template #default="{ row }"><span class="placeholder-cell">-</span></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection2Row(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div v-if="section2Rows.length > 0" class="subtotal-row">合计：收入 <span class="font-bold">{{ fmtAmt(section2Total.currentAmount) }}</span> / 成本 <span class="font-bold">{{ fmtAmt(section2Total.priorAmount) }}</span></div>
      <div class="note-area"><el-input :model-value="noteTexts['note-2']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明..." :disabled="isReadonly" @input="(v: string) => updateNote('note-2', v)" /></div>
    </el-card>

    <!-- (3) 按地区划分 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(3) 营业收入、营业成本按地区划分</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="addSection3Row">+ 添加行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="section3Rows" border size="small" class="disclosure-table">
        <el-table-column label="主要经营地区" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.name" size="small" placeholder="如：东北/华北/西北/华东..." @change="(v: string) => updateSection3(row.rowId, 'name', v)" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <!-- 🔴 上市（3）按地区叶子列名 = 主营业务收入/主营业务成本（源 R37），与国企「收入/成本」不同（Property 12） -->
        <el-table-column label="主营业务收入" min-width="110" align="right">
          <template #default="{ row }"><WpAmountInput v-if="!isReadonly" :model-value="row.amount" size="small" @update:model-value="(v: number) => updateSection3(row.rowId, 'amount', v)" /><span v-else>{{ fmtAmt(row.amount) }}</span></template>
        </el-table-column>
        <el-table-column label="主营业务成本" min-width="110" align="right">
          <template #default="{ row }"><WpAmountInput v-if="!isReadonly" :model-value="row.proportion" size="small" @update:model-value="(v: number) => updateSection3(row.rowId, 'proportion', v)" /><span v-else>{{ fmtAmt(row.proportion) }}</span></template>
        </el-table-column>
        <el-table-column label="上期主营业务收入" min-width="110" align="right">
          <template #default="{ row }"><span class="placeholder-cell">-</span></template>
        </el-table-column>
        <el-table-column label="上期主营业务成本" min-width="110" align="right">
          <template #default="{ row }"><span class="placeholder-cell">-</span></template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ row }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection3Row(row.rowId)">删</el-button></template>
        </el-table-column>
      </el-table>
      <div v-if="section3Rows.length > 0" class="subtotal-row">合计：收入 <span class="font-bold">{{ fmtAmt(section3Total.amount) }}</span> / 成本 <span class="font-bold">{{ fmtAmt(section3Total.proportion) }}</span></div>
      <div class="note-area"><el-input :model-value="noteTexts['note-3']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明..." :disabled="isReadonly" @input="(v: string) => updateNote('note-3', v)" /></div>
    </el-card>

    <!-- (4) 营业收入、营业成本按分解信息 — 列转置 + 动态类别列 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(4) 营业收入、营业成本按分解信息</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAddCategory">+ 添加类别</el-button>
          </div>
        </div>
      </template>
      <div class="method-context">
        <p>企业应考虑：①财务报表之外披露的收入信息；②管理层定期复核的经营分部信息；③使用者评价财务业绩的信息类型。</p>
        <p>分解类别包括：商品类型、经营地区、客户类型、合同类型（固定造价/成本加成）、转让时间（时点/时段）、合同期限、销售渠道等。租赁收入需单独披露。</p>
      </div>
      <!-- 列转置表格：行=检查项，列=动态类别（各含收入+成本子列）+ 合计 -->
      <div class="transpose-table-wrapper">
        <table class="transpose-table">
          <thead>
            <tr class="group-header-row">
              <th rowspan="2" class="label-th">项 目</th>
              <th v-for="cat in section4Categories" :key="cat.key" colspan="2" class="group-th">
                <span class="cat-label">{{ cat.label }}</span>
                <span v-if="!isReadonly" class="cat-actions">
                  <el-button size="small" link @click="handleRenameCategory(cat.key, cat.label)" title="重命名">✎</el-button>
                  <el-button size="small" link type="danger" @click="handleRemoveCategory(cat.key, cat.label)" title="删除">✕</el-button>
                </span>
              </th>
              <th colspan="2" class="group-th total-group-th">合计</th>
            </tr>
            <tr class="leaf-header-row">
              <template v-for="cat in section4Categories" :key="'hdr-' + cat.key">
                <th class="leaf-th">收入</th>
                <th class="leaf-th">成本</th>
              </template>
              <th class="leaf-th total-leaf-th">收入</th>
              <th class="leaf-th total-leaf-th">成本</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(checkItem, rowIdx) in transposeCheckItems" :key="rowIdx">
              <td class="label-td">{{ checkItem }}</td>
              <template v-for="cat in section4Categories" :key="cat.key + '-' + rowIdx">
                <td class="amount-td">
                  <WpAmountInput
                    v-if="!isReadonly"
                    :model-value="getSection4Cell(cat.key, rowIdx, 'revenue')"
                    size="small"
                    @update:model-value="(v: number) => updateSection4Cell(cat.key, rowIdx, 'revenue', v || null)"
                  />
                  <span v-else>{{ fmtAmt(getSection4Cell(cat.key, rowIdx, 'revenue') ?? 0) }}</span>
                </td>
                <td class="amount-td">
                  <WpAmountInput
                    v-if="!isReadonly"
                    :model-value="getSection4Cell(cat.key, rowIdx, 'cost')"
                    size="small"
                    @update:model-value="(v: number) => updateSection4Cell(cat.key, rowIdx, 'cost', v || null)"
                  />
                  <span v-else>{{ fmtAmt(getSection4Cell(cat.key, rowIdx, 'cost') ?? 0) }}</span>
                </td>
              </template>
              <td class="amount-td total-td">{{ fmtAmt(section4RowTotal(rowIdx, 'revenue') ?? 0) }}</td>
              <td class="amount-td total-td">{{ fmtAmt(section4RowTotal(rowIdx, 'cost') ?? 0) }}</td>
            </tr>
            <!-- 合计行 -->
            <tr class="total-row">
              <td class="label-td font-bold">合 计</td>
              <template v-for="cat in section4Categories" :key="'tot-' + cat.key">
                <td class="amount-td font-bold">{{ fmtAmt(section4ColTotal(cat.key, 'revenue') ?? 0) }}</td>
                <td class="amount-td font-bold">{{ fmtAmt(section4ColTotal(cat.key, 'cost') ?? 0) }}</td>
              </template>
              <td class="amount-td total-td font-bold">{{ fmtAmt(section4Total.totalRevenue ?? 0) }}</td>
              <td class="amount-td total-td font-bold">{{ fmtAmt(section4Total.totalCost ?? 0) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div class="note-area"><el-input :model-value="noteTexts['note-4']" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }" placeholder="说明：收入分解维度选择依据..." :disabled="isReadonly" @input="(v: string) => updateNote('note-4', v)" /></div>
    </el-card>

    <!-- (5) 履约义务的说明 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(5) 履约义务的说明</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-5')">🤖 AI生成</el-button>
        </div>
      </template>
      <div class="method-context">
        <p>披露与履约义务相关的信息，包括：履行时间（通常的履行时间）、重要的支付条款、企业承诺转让的商品的性质（包括说明企业是否作为代理人）、企业承担的预期将退还给客户的款项等类似义务、质量保证的类型及相关义务等。</p>
      </div>
      <el-input :model-value="noteTexts['note-5'] || ''" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="请填写履约义务相关信息..." :disabled="isReadonly" @input="(v: string) => updateNote('note-5', v)" />
    </el-card>

    <!-- (6) 与剩余履约义务有关的信息 — STRUCTURED TABLE + 文本说明 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(6) 与剩余履约义务有关的信息</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="addSection6Row">+ 添加行</el-button>
            <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-6')">🤖 AI生成</el-button>
          </div>
        </div>
      </template>
      <div class="method-context">
        <p>披露：①分摊至本期末尚未履行(或部分未履行)履约义务的交易价格总额；②上述金额确认为收入的预计时间。</p>
        <p>说明是否存在任何对价金额未纳入交易价格（如因可变对价限制要求而未计入的部分）。</p>
        <p>简化操作方法适用条件：一是原预计合同期限不超过一年；二是企业有权发出账单且账单金额能代表已履约部分价值。采用简化方法的应提供定性说明。</p>
      </div>
      <!-- 结构化表：年度 + 动态年度列（由审计年度派生） + 合计 -->
      <el-table :data="section6Rows" border size="small" class="disclosure-table" style="margin-bottom: 8px;">
        <el-table-column label="年 度" min-width="180">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" :model-value="row.label" size="small" placeholder="如：xx合同预计将确认的收入" @change="(v: string) => updateSection6Cell($index, 'label', v)" />
            <span v-else>{{ row.label || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-for="yk in obligationYearKeys" :key="yk" :label="obligationColumns.find((c: any) => c.key === yk)?.label || yk" min-width="110" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row[yk]" size="small" @update:model-value="(v: number) => updateSection6Cell($index, yk, v || null)" />
            <span v-else>{{ fmtAmt(row[yk] ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合计" min-width="110" align="right">
          <template #default="{ row }">
            <span class="font-bold">{{ fmtAmt(deriveObligationTotal(row, auditYear) ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column width="50" align="center">
          <template #default="{ $index }"><el-button v-if="!isReadonly" type="danger" size="small" link @click="removeSection6Row($index)">删</el-button></template>
        </el-table-column>
      </el-table>
      <!-- 合计行 -->
      <div v-if="section6Rows.length > 0" class="subtotal-row">
        合计：<template v-for="yk in obligationYearKeys" :key="'s6t-' + yk">
          {{ obligationColumns.find((c: any) => c.key === yk)?.label }} <span class="font-bold">{{ fmtAmt(getSection6Total(yk) ?? 0) }}</span>&nbsp;/&nbsp;
        </template>
        总计 <span class="font-bold">{{ fmtAmt(getSection6Total('total') ?? 0) }}</span>
      </div>
      <!-- 文本说明区（保留原有 textarea） -->
      <div class="note-area"><el-input :model-value="noteTexts['note-6'] || ''" type="textarea" :autosize="{ minRows: 4, maxRows: 12 }" placeholder="披露分摊至尚未履行的履约义务的交易价格总额及确认为收入的预计时间..." :disabled="isReadonly" @input="(v: string) => updateNote('note-6', v)" /></div>
    </el-card>

    <!-- (7) 重大合同变更或重大交易价格调整 -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(7) 重大合同变更【或重大交易价格调整】</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-7')">🤖 AI生成</el-button>
        </div>
      </template>
      <el-input :model-value="noteTexts['note-7'] || ''" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" placeholder="披露重大合同变更或重大交易价格调整相关的信息、会计处理方法及对收入的影响金额。" :disabled="isReadonly" @input="(v: string) => updateNote('note-7', v)" />
    </el-card>

    <!-- (8) 试运行销售收入 — STRUCTURED TABLE + 文本说明（仅上市，Req 4.6） -->
    <el-card class="section-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">(8) 试运行销售收入</span>
          <el-button size="small" :disabled="isReadonly || aiLoading" :loading="aiLoading" @click="aiGenerate('note-8')">🤖 AI生成</el-button>
        </div>
      </template>
      <div class="method-context">
        <p>企业应当按照《企业会计准则解释第15号》的规定，将试运行销售相关收入和成本分别确认为营业收入和营业成本，不应将试运行销售相关收入抵销相关成本后的净额冲减固定资产成本。</p>
      </div>
      <!-- 结构化表：5 列两级（项 目 + 本期发生额{收入,成本} + 上期发生額{收入,成本}） -->
      <el-table :data="section8Rows" border size="small" class="disclosure-table" style="margin-bottom: 8px;">
        <el-table-column prop="label" label="项 目" min-width="180" />
        <el-table-column label="收入" min-width="110" align="right">
          <template #header><span class="col-group-label">本期发生额</span><br/><span>收入</span></template>
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.endRevenue" size="small" @update:model-value="(v: number) => updateSection8Cell($index, 'endRevenue', v || null)" />
            <span v-else>{{ fmtAmt(row.endRevenue ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成本" min-width="110" align="right">
          <template #header><span class="col-group-label">本期发生额</span><br/><span>成本</span></template>
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.endCost" size="small" @update:model-value="(v: number) => updateSection8Cell($index, 'endCost', v || null)" />
            <span v-else>{{ fmtAmt(row.endCost ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收入" min-width="110" align="right">
          <template #header><span class="col-group-label">上期发生额</span><br/><span>收入</span></template>
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorRevenue" size="small" @update:model-value="(v: number) => updateSection8Cell($index, 'priorRevenue', v || null)" />
            <span v-else>{{ fmtAmt(row.priorRevenue ?? 0) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="成本" min-width="110" align="right">
          <template #header><span class="col-group-label">上期发生额</span><br/><span>成本</span></template>
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.priorCost" size="small" @update:model-value="(v: number) => updateSection8Cell($index, 'priorCost', v || null)" />
            <span v-else>{{ fmtAmt(row.priorCost ?? 0) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <!-- 文本说明区 -->
      <div class="note-area"><el-input :model-value="noteTexts['note-8'] || ''" type="textarea" :autosize="{ minRows: 3, maxRows: 10 }" placeholder="披露试运行期间的销售收入及相关会计处理（如适用）。" :disabled="isReadonly" @input="(v: string) => updateNote('note-8', v)" /></div>
    </el-card>

    <!-- 报表校对区 -->
    <el-card class="section-card reconcile-card" shadow="never">
      <template #header>
        <div class="section-header-row">
          <span class="section-title">📊 报表校对</span>
          <el-button size="small" :loading="isRefreshing" @click="refreshFromTb">🔄 重新校对</el-button>
        </div>
      </template>
      <div class="reconcile-grid">
        <div class="reconcile-item">
          <span class="reconcile-label">审定表收入合计</span>
          <span class="reconcile-value">{{ fmtAmt(crossSheetRevenue.totalRevenue) }}</span>
        </div>
        <div class="reconcile-item">
          <span class="reconcile-label">本表(1)收入合计</span>
          <span class="reconcile-value">{{ fmtAmt(section1Total.currentRevenue) }}</span>
        </div>
        <div class="reconcile-item" :class="{ 'reconcile-diff': Math.abs(crossSheetRevenue.totalRevenue - section1Total.currentRevenue) > 0.01 }">
          <span class="reconcile-label">差异</span>
          <span class="reconcile-value">{{ fmtAmt(crossSheetRevenue.totalRevenue - section1Total.currentRevenue) }}</span>
        </div>
      </div>
      <div class="reconcile-note">数据应与附注模块"营业收入"章节一致。差异≠0时请检查审定表是否已更新。</div>
    </el-card>

  </div>
</template>

<style scoped>
.d4-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.d4-disclosure-listed :deep(*) { font-size: var(--wp-font-size, 13px); }
.disclosure-toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; }
.toolbar-hint { font-size: 12px; color: #909399; margin-left: auto; }
.formula-drawer-content { padding: 0 4px; }
.formula-desc { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 12px; }
.formula-code { font-size: 11px; background: #f5f7fa; padding: 2px 4px; border-radius: 2px; color: #409eff; word-break: break-all; }
.formula-manual-list { font-size: var(--wp-font-size, 13px); color: #606266; padding-left: 20px; }
.formula-manual-list li { margin-bottom: 6px; }
.section-card { margin-bottom: 16px; }
.section-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; }
.section-title { font-size: var(--wp-font-size, 13px); font-weight: 600; color: #303133; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; }
.header-actions { display: flex; gap: 6px; align-items: center; }
.disclosure-table { font-size: var(--wp-font-size, 13px); }
.disclosure-table :deep(th) { font-size: var(--wp-font-size, 13px); background: #f5f7fa !important; }
.cross-sheet-cell { background-color: #e6f7ff; padding: 2px 6px; border-radius: 2px; border-bottom: 1px dashed #91caff; cursor: help; }
.method-context { margin-bottom: 12px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 0 4px 4px 0; font-size: 12px; color: #865c0a; line-height: 1.6; }
.method-context p { margin: 0 0 4px; }
.method-context p:last-child { margin-bottom: 0; }
.placeholder-cell { color: #c0c4cc; font-style: italic; }
.font-bold { font-weight: 600; }
.subtotal-row { margin-top: 8px; padding: 6px 12px; background: #f5f7fa; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #606266; }
.note-area { margin-top: 12px; }
.refresh-hint { font-size: var(--wp-font-size, 13px); color: #909399; margin-bottom: 8px; padding: 4px 8px; background: #f0f9ff; border-radius: 3px; }
.reconcile-card :deep(.el-card__header) { background: #f0f9eb; }
.reconcile-grid { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 12px; padding: 8px 0; }
.reconcile-item { display: flex; flex-direction: column; align-items: center; padding: 8px; background: #fafafa; border-radius: 4px; }
.reconcile-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.reconcile-value { font-size: 14px; font-weight: 600; color: #303133; }
.reconcile-diff { background: #fef0f0; }
.reconcile-diff .reconcile-value { color: #f56c6c; }
.reconcile-note { font-size: 12px; color: #909399; margin-top: 8px; }
/* 列转置表格样式 */
.transpose-table-wrapper { overflow-x: auto; margin-bottom: 8px; }
.transpose-table { width: 100%; border-collapse: collapse; font-size: var(--wp-font-size, 13px); border: 1px solid #ebeef5; }
.transpose-table th, .transpose-table td { border: 1px solid #ebeef5; padding: 6px 8px; text-align: center; }
.transpose-table .group-header-row th { background: #f5f7fa; font-weight: 600; }
.transpose-table .leaf-header-row th { background: #fafafa; font-weight: normal; font-size: 12px; }
.transpose-table .label-th { min-width: 130px; text-align: left; }
.transpose-table .label-td { text-align: left; white-space: nowrap; font-weight: 500; }
.transpose-table .group-th { position: relative; min-width: 160px; }
.transpose-table .total-group-th { background: #f0f9eb !important; }
.transpose-table .total-leaf-th { background: #f0f9eb !important; }
.transpose-table .amount-td { min-width: 80px; }
.transpose-table .total-td { background: #f0f9eb; }
.transpose-table .total-row td { background: #fafafa; border-top: 2px solid #dcdfe6; }
.cat-label { margin-right: 4px; }
.cat-actions { display: inline-flex; gap: 2px; opacity: 0.6; }
.cat-actions:hover { opacity: 1; }
.col-group-label { font-size: 11px; color: #909399; font-weight: normal; }
</style>
