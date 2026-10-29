<template>
  <el-dialog
    v-model="visible"
    title="插入公式引用"
    width="700px"
    append-to-body
    destroy-on-close
  >
    <el-alert
      v-if="truncatedHint"
      type="warning"
      :closable="false"
      show-icon
      :title="truncatedHint"
      style="margin-bottom: 8px"
    />
    <el-tabs v-model="activeTab">
      <!-- 报表引用 -->
      <el-tab-pane label="📊 报表行" name="report">
        <div class="gt-ref-filter">
          <el-input v-model="reportSearch" placeholder="搜索行次编码或名称..." size="small" clearable style="width: 250px" />
          <el-select v-model="reportPeriod" size="small" style="width: 100px">
            <el-option label="期末" value="期末" />
            <el-option label="期初" value="期初" />
          </el-select>
        </div>
        <el-table :data="filteredReportRows" size="small" max-height="300" highlight-current-row
          @row-click="onSelectReport" style="cursor: pointer">
          <el-table-column prop="row_code" label="编码" width="90" />
          <el-table-column label="项目名称" min-width="200">
            <template #default="{ row }">
              <span :style="{ paddingLeft: (row.indent_level || 0) * 12 + 'px' }">{{ row.row_name || row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              {{ reportPeriod === '期末' ? fmtAmt(row.current_period_amount) : fmtAmt(row.prior_period_amount) }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 试算表引用 -->
      <el-tab-pane label="📋 试算表科目" name="tb">
        <div class="gt-ref-filter">
          <el-input v-model="tbSearch" placeholder="搜索科目编码或名称..." size="small" clearable style="width: 250px" />
          <el-select v-model="tbColumn" size="small" style="width: 100px">
            <el-option label="审定数" value="审定数" />
            <el-option label="未审数" value="未审数" />
            <el-option label="期初" value="期初" />
          </el-select>
        </div>
        <el-table :data="filteredTbRows" size="small" max-height="300" highlight-current-row
          @row-click="onSelectTb" style="cursor: pointer">
          <el-table-column label="编码" width="100">
            <template #default="{ row }">
              {{ row.standard_account_code || row.account_code }}
            </template>
          </el-table-column>
          <el-table-column label="科目名称" min-width="180">
            <template #default="{ row }">
              {{ row.account_name || row.label }}
            </template>
          </el-table-column>
          <el-table-column label="金额" width="120" align="right">
            <template #default="{ row }">
              {{ tbColumn === '审定数' ? fmtAmt(row.audited_amount) : tbColumn === '未审数' ? fmtAmt(row.unadjusted_amount) : fmtAmt(row.opening_balance) }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 附注引用 -->
      <el-tab-pane label="📝 其他附注" name="note">
        <div class="gt-ref-filter">
          <el-input v-model="noteSearch" placeholder="搜索章节..." size="small" clearable style="width: 250px" />
          <!-- 地址库条目按「章节 × 合计行 × 表头列」逐条登记，选哪一条就插哪一列；期间选择只给页面自带的章节列表用 -->
          <el-select v-if="!noteFromStore" v-model="notePeriod" size="small" style="width: 100px">
            <el-option label="期末" value="期末" />
            <el-option label="期初" value="期初" />
          </el-select>
        </div>
        <el-table :data="filteredNoteRows" size="small" max-height="300" highlight-current-row
          @row-click="onSelectNote" style="cursor: pointer">
          <el-table-column prop="note_section" label="章节" width="80" />
          <el-table-column label="标题" min-width="180">
            <template #default="{ row }">
              {{ row.section_title || row.label }}
            </template>
          </el-table-column>
          <el-table-column label="合计值" width="120" align="right">
            <template #default="{ row }">
              {{ fmtAmt(notePeriod === '期末' ? row.total_closing : row.total_opening) }}
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 底稿单元格引用（ACNR WP 域） -->
      <el-tab-pane label="🧾 底稿单元格" name="wp">
        <div class="gt-ref-filter">
          <el-select
            v-model="selectedWpSheetAddrId"
            filterable
            clearable
            placeholder="选择底稿 Sheet"
            size="small"
            style="width: 320px"
            :loading="wpSheetsLoading"
            @change="onWpSheetChange"
          >
            <el-option
              v-for="s in wpSheets"
              :key="s.addr_id"
              :label="s.display_label || s.sheet_code"
              :value="s.addr_id"
            />
          </el-select>
          <el-input v-model="wpCellSearch" placeholder="搜索单元格/引用..." size="small" clearable style="width: 220px" />
        </div>
        <el-table
          v-if="filteredWpCells.length"
          v-loading="wpCellsLoading"
          :data="filteredWpCells"
          size="small"
          max-height="300"
          highlight-current-row
          @row-click="onSelectWpCell"
          style="cursor: pointer"
        >
          <el-table-column label="单元格" min-width="200">
            <template #default="{ row }">{{ row.cell_label }}</template>
          </el-table-column>
          <el-table-column label="引用" min-width="200">
            <template #default="{ row }">
              <code style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ row.formula_ref }}</code>
            </template>
          </el-table-column>
        </el-table>
        <el-empty v-else :description="wpEmptyDescription" :image-size="72" />
      </el-tab-pane>
    </el-tabs>

    <!-- 预览区 -->
    <div v-if="selectedFormula" class="gt-ref-preview">
      <div class="gt-ref-preview-label">将插入：</div>
      <div class="gt-ref-preview-formula">
        <el-tag type="primary" size="default">{{ selectedLabel }}</el-tag>
        <code style="margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ selectedFormula }}</code>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedFormula" @click="onConfirm">插入</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { fmtAmount } from '@/utils/formatters'
import { useAddressRegistry } from '@/stores/addressRegistry'
import { useAcnr, isListedCell, type AcnrSheetEntry, type AcnrCellEntry } from '@/services/acnr/useAcnr'
import { useCurrentProjectId } from '@/composables/useCurrentProjectId'

const addrStore = useAddressRegistry()
// D9（需求 11.1）：按当前项目订阅 ACNR 失效（组件无项目入参，取路由/store 当前项目）。
const acnr = useAcnr(useCurrentProjectId())

const props = defineProps<{
  modelValue: boolean
  reportRows: any[]   // 报表行数据
  tbRows: any[]       // 试算表科目数据
  noteRows: any[]     // 附注章节数据
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'insert': [formula: string, label: string]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeTab = ref('report')
const reportSearch = ref('')
const reportPeriod = ref('期末')
const tbSearch = ref('')
const tbColumn = ref('审定数')
const noteSearch = ref('')
const notePeriod = ref('期末')

const selectedFormula = ref('')
const selectedLabel = ref('')

// ─── WP 域（ACNR 底稿单元格）───
interface WpCellRow {
  cell_address: string
  /** 单元格表「单元格」列（目录 cell_label） */
  cell_label: string
  /** 统一显示名（目录 display_label），搜索与「将插入」标签用 */
  display_label: string
  formula_ref: string
  parent_wp_code: string
  sheet_code: string
}

const wpSheets = ref<AcnrSheetEntry[]>([])
const wpSheetsLoading = ref(false)
const selectedWpSheetAddrId = ref('')
const wpCells = ref<AcnrCellEntry[]>([])
const wpCellsLoading = ref(false)
const wpCellSearch = ref('')
/** 已向 ACNR 取过 sheet 目录（取到为空 ⇒ 底稿页签回退旧地址库）。 */
const wpSheetsLoaded = ref(false)

const selectedWpSheet = computed(
  () => wpSheets.value.find(s => s.addr_id === selectedWpSheetAddrId.value) || null,
)
// ACNR 是否可用：listSheets 有结果。为空则回退 legacy store 的 wp 域地址。
const wpAcnrAvailable = computed(() => wpSheets.value.length > 0)

/** 兜底构造 grammar_v1 3 参 WP 引用（AcnrCellEntry.formula_ref 缺失时）。 */
function buildWpFormulaRef(parent: string, sheet: string, cell: string): string {
  return `WP('${parent}','${sheet}','${cell}')`
}

// 单元格候选：ACNR 命中用 listCells，否则回退 legacy store 的 wp 域 cell 条目。
const filteredWpCells = computed<WpCellRow[]>(() => {
  const kw = wpCellSearch.value.toLowerCase()
  let rows: WpCellRow[]
  if (wpAcnrAvailable.value) {
    const sheet = selectedWpSheet.value
    if (!sheet) return []
    rows = wpCells.value.map(c => {
      const cellAddr = c.cell_address || ''
      return {
        cell_address: cellAddr,
        cell_label: c.cell_label || cellAddr || c.addr_id,
        display_label: c.display_label || c.cell_label || cellAddr || c.addr_id,
        // R14.5: 优先用 ACNR 条目自带的 grammar_v1 formula_ref（含 custom_flat），
        // 缺失时兜底构造 3 参 WP('parent','sheet','cell')。
        formula_ref: c.formula_ref || buildWpFormulaRef(sheet.parent_wp_code, sheet.sheet_code, cellAddr),
        parent_wp_code: sheet.parent_wp_code,
        sheet_code: sheet.sheet_code,
      }
    })
  } else {
    // 回退 legacy store（R14.4，无回归）：wp 域 cell 级条目自带 formula_ref。
    rows = addrStore.wpAddresses
      .filter(e => e.formula_ref)
      .map(e => ({
        cell_address: e.cell || '',
        cell_label: e.label || e.cell || e.uri,
        display_label: e.label || e.cell || e.uri,
        formula_ref: e.formula_ref,
        parent_wp_code: e.wp_code || '',
        sheet_code: e.sheet_code || '',
      }))
  }
  if (!kw) return rows
  return rows.filter(r =>
    (r.cell_address || '').toLowerCase().includes(kw) ||
    (r.display_label || '').toLowerCase().includes(kw) ||
    (r.formula_ref || '').toLowerCase().includes(kw),
  )
})

const wpEmptyDescription = computed(() => {
  if (wpAcnrAvailable.value && !selectedWpSheet.value) return '请选择底稿 Sheet'
  return '暂无可用底稿单元格'
})

async function ensureWpSheets() {
  if (wpSheetsLoaded.value) return
  wpSheetsLoading.value = true
  try {
    wpSheets.value = await acnr.listSheets()
  } catch {
    wpSheets.value = []
  } finally {
    wpSheetsLoading.value = false
    wpSheetsLoaded.value = true
  }
}

async function onWpSheetChange(addrId: string | null) {
  wpCells.value = []
  const s = wpSheets.value.find(x => x.addr_id === addrId)
  if (!s) return
  wpCellsLoading.value = true
  try {
    // 停用 cell 不列（与地址树 loadCellNodes 同一谓词，RV7-02）
    wpCells.value = (await acnr.listCells(s.parent_wp_code, s.sheet_code)).filter(isListedCell)
  } catch {
    wpCells.value = []
  } finally {
    wpCellsLoading.value = false
  }
}

function onSelectWpCell(row: WpCellRow) {
  if (!row.formula_ref) return
  selectedFormula.value = row.formula_ref
  selectedLabel.value = `底稿 ${row.display_label}`
}

// WP tab 首次激活时懒加载 sheet 目录
watch(activeTab, (t) => {
  if (t === 'wp') ensureWpSheets()
})

// 弹窗关闭时重置 WP 选择态（sheet 目录缓存保留，避免重复请求）
watch(visible, (v) => {
  if (!v) {
    selectedWpSheetAddrId.value = ''
    wpCells.value = []
    wpCellSearch.value = ''
  }
})

// ─── 数据源：优先 store（该域完整加载时），回退 props ───

/** 期间选择 → 地址库登记的期间列：资产负债表 期末 / 期初，利润表与现金流量表 本期 / 上期，权益变动表 本年 / 上年。 */
const REPORT_PERIOD_CELLS: Record<string, readonly string[]> = {
  期末: ['期末', '本期', '本年'],
  期初: ['期初', '上期', '上年'],
}
/** 被截断后改用页面自带数据的域（各有页签）。辅助余额在本选择器没有页签；底稿页签走 ACNR 目录，只在回退旧地址库时受影响。 */
const PAGE_FALLBACK_DOMAINS: Record<string, string> = { report: '报表', tb: '试算表', note: '附注' }

// 该域被地址库加载上限截断时不当成完整的用（R3.2）：改用页面自带的数据
const reportFromStore = computed(() => addrStore.isDomainComplete('report') && addrStore.reportAddresses.length > 0)
const tbFromStore = computed(() => addrStore.isDomainComplete('tb') && addrStore.tbAddresses.length > 0)
const noteFromStore = computed(() => addrStore.isDomainComplete('note') && addrStore.noteAddresses.length > 0)

// 只提示本选择器页签真受影响的域：只截断了辅助余额（真实项目最常见）时不提示
const truncatedHint = computed(() => {
  const truncated = addrStore.truncatedDomains || []
  const parts: string[] = []
  const fallback = Object.keys(PAGE_FALLBACK_DOMAINS).filter(d => truncated.includes(d)).map(d => PAGE_FALLBACK_DOMAINS[d])
  if (fallback.length) parts.push(`${fallback.join('、')}只加载了一部分，相关页签改用当前页面的数据`)
  if (truncated.includes('wp') && wpSheetsLoaded.value && !wpAcnrAvailable.value) parts.push('底稿单元格只加载了一部分，列表不全')
  return parts.length ? `地址库条目太多，${parts.join('；')}` : ''
})

const filteredReportRows = computed(() => {
  const kw = reportSearch.value.toLowerCase()
  // 优先使用 store 中的报表地址（按期间列过滤，每行次一条）
  if (reportFromStore.value) {
    const cells = REPORT_PERIOD_CELLS[reportPeriod.value] || []
    return addrStore.reportAddresses.filter(e =>
      cells.includes(e.cell)
      && (!kw || (e.row_code || '').toLowerCase().includes(kw) || (e.label || '').toLowerCase().includes(kw)),
    )
  }
  return (props.reportRows || []).filter(r =>
    !kw || (r.row_code || '').toLowerCase().includes(kw) || (r.row_name || '').toLowerCase().includes(kw)
  )
})

const filteredTbRows = computed(() => {
  const kw = tbSearch.value.toLowerCase()
  // 优先使用 store 中的试算表地址
  if (tbFromStore.value) {
    return addrStore.tbAddresses.filter(e =>
      !kw || (e.account_code || '').includes(kw) || (e.label || '').toLowerCase().includes(kw)
    )
  }
  return (props.tbRows || []).filter(r =>
    !kw || (r.standard_account_code || '').includes(kw) || (r.account_name || '').toLowerCase().includes(kw)
  )
})

const filteredNoteRows = computed(() => {
  const kw = noteSearch.value.toLowerCase()
  // 优先使用 store 中的附注地址
  if (noteFromStore.value) {
    return addrStore.noteAddresses.filter(e =>
      !kw || (e.note_section || '').includes(kw) || (e.label || '').toLowerCase().includes(kw)
    )
  }
  return (props.noteRows || []).filter(r =>
    !kw || (r.note_section || '').includes(kw) || (r.section_title || '').toLowerCase().includes(kw)
  )
})

const fmtAmt = fmtAmount

// 地址库条目带登记的引用写法 ⇒ 原样插入（能过保存校验）；只有页面自带的行才按选择拼写法。
// 原先一律拼 REPORT(行次,'期末') / NOTE(章节,'合计','期末')：利润表登记的是本期 / 上期、附注登记的是表头原文
// （如「期末余额」），附注域有数之后插入的引用保存时都判悬空（R3.3）。
function onSelectReport(row: any) {
  const code = row.row_code || ''
  const name = row.row_name || row.label || ''
  if (row.formula_ref) {
    selectedFormula.value = row.formula_ref
    selectedLabel.value = `[${code}] ${name}`
    return
  }
  const period = reportPeriod.value
  selectedFormula.value = `REPORT('${code}','${period}')`
  selectedLabel.value = `[${code}] ${name} · ${period}`
}

function onSelectTb(row: any) {
  const code = row.standard_account_code || row.account_code || ''
  const name = row.account_name || row.label || ''
  const col = tbColumn.value
  selectedFormula.value = `TB('${code}','${col}')`
  selectedLabel.value = `[${code}] ${name} · ${col}`
}

function onSelectNote(row: any) {
  const section = row.note_section || ''
  const title = row.section_title || row.label || ''
  if (row.formula_ref) {
    selectedFormula.value = row.formula_ref
    selectedLabel.value = `[${section}] ${title}`
    return
  }
  const period = notePeriod.value
  selectedFormula.value = `NOTE('${section}','合计','${period}')`
  selectedLabel.value = `[${section}] ${title} · 合计 · ${period}`
}

function onConfirm() {
  if (selectedFormula.value) {
    emit('insert', selectedFormula.value, selectedLabel.value)
    visible.value = false
    selectedFormula.value = ''
    selectedLabel.value = ''
  }
}
</script>

<style scoped>
.gt-ref-filter { display: flex; gap: 8px; margin-bottom: 8px; }
.gt-ref-preview {
  margin-top: 16px; padding: 12px; background: var(--gt-color-primary-bg);
  border-radius: 8px; border: 1px solid var(--gt-color-border-purple);
}
.gt-ref-preview-label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-bottom: 4px; }
.gt-ref-preview-formula { display: flex; align-items: center; }
</style>
