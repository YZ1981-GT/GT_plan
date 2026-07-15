<script setup lang="ts">
/**
 * E1TabCreditCheck.vue — E1-19 企业信用报告信息与账面核对记录
 *
 * 结构对齐致同源模板：
 *  一、审计目标（静态）
 *  （一）注册资本/出资人对照表
 *  （二）信贷类别征信 vs 账面汇总（差异自动算）
 *  （三）不一致事项时点调节（④=①+②−③，⑥=④−⑤）
 *  过程索引说明 → L1-4 / L3-4
 *  （四）担保事项（附件截图区）
 *  （五）关联关系企业表
 *  三、审计说明 / 四、审计结论（AI）
 *  提示（静态）
 *
 * 联动：E1-18 查询记录 · L1-4 短期借款征信核对 · L3-4 长期借款征信核对
 */
import { ref, computed, inject, onMounted, onBeforeUnmount, toRef, type Ref } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import ItemAttachment from '../ItemAttachment.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  bsDate?: string
}>()

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

const sheetCode = computed(() => 'E1-19')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
    loadPack()
    loadTexts()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

// ─── Storage keys ────────────────────────────────────────────────────────────

const PACK_KEY = 'E1-credit-check-pack'
const NOTE_KEY = 'E1-credit-audit-note-check'
const CONCLUSION_KEY = 'E1-credit-audit-conclusion-check'
const QUERY_FORM_KEY = 'E1-credit-query-form'

// ─── Types ───────────────────────────────────────────────────────────────────

interface CapitalRow {
  id: string
  creditInvestor: string
  creditRatio: string
  bookRatio: string
  checkResult: '' | '一致' | '不一致'
  diffReason: string
  remark: string
}

interface SummaryCol {
  key: string
  label: string
  creditAmount: number
  bookAmount: number
}

interface AdjustRow {
  id: string
  category: string
  printUncleared: number   // ①
  plusRepaid: number       // ②
  minusNew: number         // ③
  glAccount: string
  glAmount: number         // ⑤
  diffReason: string
}

interface RelatedPartyRow {
  id: string
  creditName: string
  creditRelation: string
  inRegistry: '' | '是' | '否'
  disclosedRelation: string
}

interface CheckPack {
  capitalRows: CapitalRow[]
  summaryCols: SummaryCol[]
  adjustRows: AdjustRow[]
  relatedPartyRows: RelatedPartyRow[]
  processNote: string
  guaranteeAssert: string
}

function uid(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

const DEFAULT_PROCESS_NOTE =
  '1.短期借款与企业信用报告详细核对见短期借款底稿 L1-4。\n2.中长期借款与企业信用报告详细核对见长期借款底稿 L3-4。'

const DEFAULT_GUARANTEE_ASSERT = '担保事项应与报告披露核对一致。'

const SUMMARY_DEFS: Array<{ key: string; label: string }> = [
  { key: 'midLong', label: '中长期借款' },
  { key: 'short', label: '短期借款' },
  { key: 'acceptance', label: '银行承兑汇票' },
  { key: 'lc', label: '信用证' },
  { key: 'guarantee', label: '银行保函' },
  { key: 'discount', label: '贴现' },
  { key: 'other', label: '其他' },
]

const ADJUST_CATEGORIES = [
  '短期借款',
  '中长期借款',
  '循环透支',
  '银行承兑汇票',
  '信用证',
  '银行保函',
  '贴现',
]

function emptyCapitalRow(): CapitalRow {
  return { id: uid('cap'), creditInvestor: '', creditRatio: '', bookRatio: '', checkResult: '', diffReason: '', remark: '' }
}

function defaultSummaryCols(): SummaryCol[] {
  return SUMMARY_DEFS.map(d => ({ ...d, creditAmount: 0, bookAmount: 0 }))
}

function emptyAdjustRow(category = ''): AdjustRow {
  return {
    id: uid('adj'),
    category,
    printUncleared: 0,
    plusRepaid: 0,
    minusNew: 0,
    glAccount: '',
    glAmount: 0,
    diffReason: '',
  }
}

function defaultAdjustRows(): AdjustRow[] {
  return ADJUST_CATEGORIES.map(c => emptyAdjustRow(c))
}

function emptyRelatedRow(): RelatedPartyRow {
  return { id: uid('rp'), creditName: '', creditRelation: '', inRegistry: '', disclosedRelation: '' }
}

function defaultPack(): CheckPack {
  return {
    capitalRows: [emptyCapitalRow(), emptyCapitalRow(), emptyCapitalRow()],
    summaryCols: defaultSummaryCols(),
    adjustRows: defaultAdjustRows(),
    relatedPartyRows: [emptyRelatedRow(), emptyRelatedRow()],
    processNote: DEFAULT_PROCESS_NOTE,
    guaranteeAssert: DEFAULT_GUARANTEE_ASSERT,
  }
}

// ─── State ───────────────────────────────────────────────────────────────────

const pack = ref<CheckPack>(defaultPack())
const auditNote = ref('')
const auditConclusion = ref('')
let saveTimer: ReturnType<typeof setTimeout> | null = null

function adjustBsAmount(row: AdjustRow): number {
  return Number(row.printUncleared || 0) + Number(row.plusRepaid || 0) - Number(row.minusNew || 0)
}

function adjustResidual(row: AdjustRow): number {
  return adjustBsAmount(row) - Number(row.glAmount || 0)
}

function summaryDiff(col: SummaryCol): number {
  return Number(col.creditAmount || 0) - Number(col.bookAmount || 0)
}

const hasSummaryDiff = computed(() => pack.value.summaryCols.some(c => Math.abs(summaryDiff(c)) > 0.005))
const hasAdjustDiff = computed(() => pack.value.adjustRows.some(r => Math.abs(adjustResidual(r)) > 0.005))

const e18Borrower = computed(() => {
  try {
    const raw = props.allResponses.get(QUERY_FORM_KEY)?.remark
    if (!raw) return ''
    const parsed = JSON.parse(raw)
    return String(parsed?.borrowerName || '')
  } catch {
    return ''
  }
})

// ─── Load / Save ─────────────────────────────────────────────────────────────

function loadPack(): void {
  const resp = props.allResponses.get(PACK_KEY)
  if (!resp?.remark) {
    pack.value = defaultPack()
    return
  }
  try {
    const parsed = JSON.parse(resp.remark)
    const base = defaultPack()
    pack.value = {
      ...base,
      ...parsed,
      capitalRows: Array.isArray(parsed.capitalRows) && parsed.capitalRows.length ? parsed.capitalRows : base.capitalRows,
      summaryCols: Array.isArray(parsed.summaryCols) && parsed.summaryCols.length
        ? SUMMARY_DEFS.map(d => {
            const found = parsed.summaryCols.find((c: any) => c.key === d.key)
            return {
              key: d.key,
              label: d.label,
              creditAmount: Number(found?.creditAmount) || 0,
              bookAmount: Number(found?.bookAmount) || 0,
            }
          })
        : base.summaryCols,
      adjustRows: Array.isArray(parsed.adjustRows) && parsed.adjustRows.length ? parsed.adjustRows : base.adjustRows,
      relatedPartyRows: Array.isArray(parsed.relatedPartyRows) && parsed.relatedPartyRows.length
        ? parsed.relatedPartyRows
        : base.relatedPartyRows,
      processNote: parsed.processNote || DEFAULT_PROCESS_NOTE,
      guaranteeAssert: parsed.guaranteeAssert || DEFAULT_GUARANTEE_ASSERT,
    }
  } catch {
    pack.value = defaultPack()
  }
}

function loadTexts(): void {
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}

function persistPack(): void {
  const item = { item_id: PACK_KEY, conclusion: null, remark: JSON.stringify(pack.value) }
  props.allResponses.set(PACK_KEY, item)
  props.saveImmediate([item]).catch(() => {})
}

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    persistPack()
  }, 1500)
}

function touch(): void {
  if (props.isReadonly) return
  scheduleSave()
}

loadPack()
loadTexts()
onMounted(() => {
  loadPack()
  loadTexts()
})

onBeforeUnmount(() => {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    persistPack()
  }
})

// ─── Capital CRUD ────────────────────────────────────────────────────────────

function addCapitalRow(): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, capitalRows: [...pack.value.capitalRows, emptyCapitalRow()] }
  touch()
}

function removeCapitalRow(id: string): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, capitalRows: pack.value.capitalRows.filter(r => r.id !== id) }
  touch()
}

function updateCapital(id: string, field: keyof CapitalRow, val: string): void {
  if (props.isReadonly) return
  pack.value = {
    ...pack.value,
    capitalRows: pack.value.capitalRows.map(r => (r.id === id ? { ...r, [field]: val } : r)),
  }
  touch()
}

// ─── Summary ─────────────────────────────────────────────────────────────────

function updateSummary(key: string, field: 'creditAmount' | 'bookAmount', val: number): void {
  if (props.isReadonly) return
  pack.value = {
    ...pack.value,
    summaryCols: pack.value.summaryCols.map(c => (c.key === key ? { ...c, [field]: Number(val) || 0 } : c)),
  }
  touch()
}

/** 将（二）征信金额灌入（三）①打印日未结清（同名类别） */
function seedAdjustFromSummary(): void {
  if (props.isReadonly) return
  const map: Record<string, string> = {
    short: '短期借款',
    midLong: '中长期借款',
    acceptance: '银行承兑汇票',
    lc: '信用证',
    guarantee: '银行保函',
    discount: '贴现',
  }
  const next = pack.value.adjustRows.map(row => {
    const entry = Object.entries(map).find(([, cat]) => cat === row.category)
    if (!entry) return row
    const col = pack.value.summaryCols.find(c => c.key === entry[0])
    if (!col) return row
    return { ...row, printUncleared: Number(col.creditAmount) || 0 }
  })
  pack.value = { ...pack.value, adjustRows: next }
  touch()
  ElMessage.success('已将汇总表征信金额填入调节表①列（同名类别）')
}

// ─── Adjust ──────────────────────────────────────────────────────────────────

function addAdjustRow(): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, adjustRows: [...pack.value.adjustRows, emptyAdjustRow()] }
  touch()
}

function removeAdjustRow(id: string): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, adjustRows: pack.value.adjustRows.filter(r => r.id !== id) }
  touch()
}

function updateAdjust(id: string, field: keyof AdjustRow, val: string | number): void {
  if (props.isReadonly) return
  pack.value = {
    ...pack.value,
    adjustRows: pack.value.adjustRows.map(r => (r.id === id ? { ...r, [field]: val } : r)),
  }
  touch()
}

// ─── Related party ───────────────────────────────────────────────────────────

function addRelatedRow(): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, relatedPartyRows: [...pack.value.relatedPartyRows, emptyRelatedRow()] }
  touch()
}

function removeRelatedRow(id: string): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, relatedPartyRows: pack.value.relatedPartyRows.filter(r => r.id !== id) }
  touch()
}

function updateRelated(id: string, field: keyof RelatedPartyRow, val: string): void {
  if (props.isReadonly) return
  pack.value = {
    ...pack.value,
    relatedPartyRows: pack.value.relatedPartyRows.map(r => (r.id === id ? { ...r, [field]: val } : r)),
  }
  touch()
}

// ─── Text fields ────────────────────────────────────────────────────────────

function updateProcessNote(val: string): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, processNote: val ?? '' }
  touch()
}

function updateGuaranteeAssert(val: string): void {
  if (props.isReadonly) return
  pack.value = { ...pack.value, guaranteeAssert: val ?? '' }
  touch()
}

function onAuditNoteInput(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val ?? ''
}

function onAuditConclusionInput(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val ?? ''
}

function saveAuditNote(): void {
  if (props.isReadonly) return
  const item = { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(): void {
  if (props.isReadonly) return
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}

// ─── AI ──────────────────────────────────────────────────────────────────────

function aiContext(): Record<string, unknown> {
  const summaryLines = pack.value.summaryCols
    .map(c => `${c.label}: 征信${c.creditAmount} / 账面${c.bookAmount} / 差异${summaryDiff(c)}`)
    .join('；')
  const adjustDiffs = pack.value.adjustRows
    .filter(r => Math.abs(adjustResidual(r)) > 0.005)
    .map(r => `${r.category} 残余差异${adjustResidual(r)}（原因:${r.diffReason || '未填'}）`)
    .join('；')
  const capitalDiffs = pack.value.capitalRows
    .filter(r => r.checkResult === '不一致')
    .map(r => `${r.creditInvestor}:${r.diffReason || '未说明'}`)
    .join('；')
  const rpMissing = pack.value.relatedPartyRows
    .filter(r => r.inRegistry === '否')
    .map(r => r.creditName)
    .join('、')
  return {
    底稿: 'E1-19 企业信用报告与账面核对',
    报表日: props.bsDate || '',
    E118借款人: e18Borrower.value || '未取得',
    出资人不一致: capitalDiffs || '无',
    汇总差异: summaryLines,
    调节残余差异: adjustDiffs || '无',
    关联方未入清单: rpMissing || '无',
    担保断言: pack.value.guaranteeAssert,
    过程索引说明: pack.value.processNote,
  }
}

function sanitizeNote(raw: string): string {
  let t = String(raw || '').trim()
  t = t.replace(/^\*{0,2}审计说明\*{0,2}\s*/i, '')
  t = t.replace(/\n+\s*\*{0,2}结\s*论\*{0,2}\s*[:：].*$/s, '')
  t = t.replace(/\n+\s*\*{0,2}审计结论\*{0,2}.*$/s, '')
  return t.trim()
}

function sanitizeConclusion(raw: string): string {
  let t = String(raw || '').trim()
  t = t.replace(/^\*{0,2}审计结论\*{0,2}\s*/i, '')
  t = t.replace(/^[ABC]、\s*/i, '')
  return t.trim()
}

async function generateAi(target: 'note' | 'conclusion'): Promise<void> {
  if (props.isReadonly) return
  if (target === 'note') {
    const text = await generateText({
      section: 'e1-19-audit-note',
      prompt: [
        '你是注册会计师助理。请撰写 E1-19「审计说明」，只描述核对过程与发现，不要写审计结论。',
        '应概括：出资人核对、信贷汇总差异、时点调节残余差异、担保与关联方核对情况；差异须说明已处理或待进一步核实。',
        '可提示短期/中长期借款细核对见 L1-4、L3-4。',
        '严禁输出「结论」「审计结论」段落；严禁 markdown；严禁编造金额；约 150～280 字。',
      ].join(''),
      context: aiContext(),
      existingContent: auditNote.value,
      confirmTitle: 'AI 生成 · 审计说明',
    })
    if (!text) return
    auditNote.value = sanitizeNote(text)
    saveAuditNote()
    return
  }
  const text = await generateText({
    section: 'e1-19-audit-conclusion',
    prompt: [
      '你是注册会计师助理。请撰写 E1-19「审计结论」正式表述（2～4句）。',
      '要点：征信信息与账面总体是否相符；重大差异是否已解释；担保/关联方是否需关注；细项是否见 L1-4/L3-4。',
      '严禁输出 A/B/C 选项代号；严禁重复审计说明全文；仅输出结论正文。',
    ].join(''),
    context: aiContext(),
    existingContent: auditConclusion.value,
    confirmTitle: 'AI 生成 · 审计结论',
  })
  if (!text) return
  const cleaned = sanitizeConclusion(text)
  if (cleaned.length < 12) {
    ElMessage.warning('AI 结论过短，请重试或手工填写')
    return
  }
  auditConclusion.value = cleaned
  saveAuditConclusion()
}
</script>

<template>
  <div class="e1-tab-credit-check">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表承接 E1-18：先完成征信查询，再在本表做征信 vs 账面核对。</p>
        <p>2. （二）填征信/账面金额，差异自动算；（三）将打印日余额调节至报表日再与总账比对（④=①+②−③，⑥=④−⑤）。</p>
        <p>3. 短期/中长期借款明细核对分别跳转 L1-4、L3-4；担保与披露、关联方清单交叉印证。</p>
        <p>4. 审计说明写过程与差异分析，审计结论写认定结果，二者分开。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核对征信报告信息与账面记录是否一致；借款、银行承兑汇票、信用证等完整性。"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="warning">征信核对 (E1-19)</el-tag>
        <el-tag v-if="e18Borrower" size="small" type="success">E1-18 借款人：{{ e18Borrower }}</el-tag>
        <el-tag v-if="hasSummaryDiff" size="small" type="danger">汇总存在差异</el-tag>
        <el-tag v-if="hasAdjustDiff" size="small" type="danger">调节后仍有差异</el-tag>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-18" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:L1-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:L3-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-10" :context-project-id="projectId" /></span>
      </div>
    </div>

    <!-- （一）注册资本 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>（一）注册资本及主要出资人信息</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addCapitalRow">+ 添加行</el-button>
        </div>
      </template>
      <el-table :data="pack.capitalRows" border size="small" max-height="280">
        <el-table-column label="征信-出资方" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.creditInvestor" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateCapital(row.id, 'creditInvestor', v)" />
          </template>
        </el-table-column>
        <el-table-column label="征信-出资比例" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.creditRatio" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateCapital(row.id, 'creditRatio', v)" />
          </template>
        </el-table-column>
        <el-table-column label="账面-出资比例" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.bookRatio" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateCapital(row.id, 'bookRatio', v)" />
          </template>
        </el-table-column>
        <el-table-column label="核对" width="110">
          <template #default="{ row }">
            <el-select :model-value="row.checkResult" :disabled="isReadonly" size="small" clearable placeholder="选择"
              @update:model-value="(v: string) => updateCapital(row.id, 'checkResult', v || '')">
              <el-option label="一致" value="一致" />
              <el-option label="不一致" value="不一致" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="不一致原因" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.diffReason" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateCapital(row.id, 'diffReason', v)" />
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input :model-value="row.remark" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateCapital(row.id, 'remark', v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeCapitalRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- （二）汇总核对 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>（二）征信报告信息与账面核对记录</span>
          <el-button size="small" :disabled="isReadonly" @click="seedAdjustFromSummary">灌入（三）①列</el-button>
        </div>
      </template>
      <el-table :data="[
        { kind: 'credit', label: '征信报告信息' },
        { kind: 'book', label: '账面记录' },
        { kind: 'diff', label: '差异' },
      ]" border size="small" class="summary-table">
        <el-table-column prop="label" label="类别" width="120" fixed />
        <el-table-column v-for="col in pack.summaryCols" :key="col.key" :label="col.label" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row.kind === 'credit'">
              <el-input-number
                :model-value="col.creditAmount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => updateSummary(col.key, 'creditAmount', v ?? 0)"
              />
            </template>
            <template v-else-if="row.kind === 'book'">
              <el-input-number
                :model-value="col.bookAmount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                style="width: 100%"
                @change="(v: number | undefined) => updateSummary(col.key, 'bookAmount', v ?? 0)"
              />
            </template>
            <span v-else :class="{ 'diff-warn': Math.abs(summaryDiff(col)) > 0.005 }" class="auto-calc">
              {{ displayPrefs.fmtAmount(summaryDiff(col)) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint-line">差异 = 征信报告信息 − 账面记录（自动计算）。存在差异时请在（三）做时点调节。</p>
    </el-card>

    <!-- （三）时点调节 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>（三）不一致事项账面差异调节</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addAdjustRow">+ 添加行</el-button>
        </div>
      </template>
      <el-table :data="pack.adjustRows" border size="small" max-height="420">
        <el-table-column label="类别" width="120">
          <template #default="{ row }">
            <el-input :model-value="row.category" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateAdjust(row.id, 'category', v)" />
          </template>
        </el-table-column>
        <el-table-column label="①打印日未结清" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.printUncleared" :disabled="isReadonly" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateAdjust(row.id, 'printUncleared', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="②加：BS日至打印日已还" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.plusRepaid" :disabled="isReadonly" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateAdjust(row.id, 'plusRepaid', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="③减：BS日至打印日新增" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.minusNew" :disabled="isReadonly" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateAdjust(row.id, 'minusNew', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="④=①+②−③" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="auto-calc">{{ displayPrefs.fmtAmount(adjustBsAmount(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="总账科目" min-width="110">
          <template #default="{ row }">
            <el-input :model-value="row.glAccount" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateAdjust(row.id, 'glAccount', v)" />
          </template>
        </el-table-column>
        <el-table-column label="⑤总账金额" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number :model-value="row.glAmount" :disabled="isReadonly" :controls="false" size="small" style="width:100%"
              @change="(v: number | undefined) => updateAdjust(row.id, 'glAmount', v ?? 0)" />
          </template>
        </el-table-column>
        <el-table-column label="⑥=④−⑤" width="120" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="{ 'diff-warn': Math.abs(adjustResidual(row)) > 0.005 }" class="auto-calc">
              {{ displayPrefs.fmtAmount(adjustResidual(row)) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异原因" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.diffReason" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateAdjust(row.id, 'diffReason', v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeAdjustRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint-line">
        报表日应有额④ = 打印日未结清① + 报表日至打印日已还② − 新增③；残余差异⑥ = ④ − 总账⑤。细核对：
        <span class="chip-wrap"><GtIndexChip value="wp:L1-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:L3-4" :context-project-id="projectId" /></span>
      </p>
    </el-card>

    <!-- 过程索引说明 -->
    <el-card shadow="never" class="section-card">
      <template #header><span>交叉底稿索引说明</span></template>
      <el-input
        type="textarea"
        :model-value="pack.processNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        @update:model-value="updateProcessNote"
      />
    </el-card>

    <!-- （四）担保 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>（四）担保事项</span>
          <span class="sub-hint">上传征信担保截图/打印件，并与披露核对</span>
        </div>
      </template>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="E1-19"
        :item-index="0"
      />
      <el-input
        class="guarantee-assert"
        type="textarea"
        :model-value="pack.guaranteeAssert"
        :disabled="isReadonly"
        :autosize="{ minRows: 2 }"
        @update:model-value="updateGuaranteeAssert"
      />
    </el-card>

    <!-- （五）关联方 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>（五）关联关系企业</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="addRelatedRow">+ 添加行</el-button>
        </div>
      </template>
      <el-table :data="pack.relatedPartyRows" border size="small" max-height="280">
        <el-table-column label="征信报告关联方名称" min-width="160">
          <template #default="{ row }">
            <el-input :model-value="row.creditName" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateRelated(row.id, 'creditName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="征信报告中关联关系" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.creditRelation" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateRelated(row.id, 'creditRelation', v)" />
          </template>
        </el-table-column>
        <el-table-column label="是否纳入关联方清单" width="150">
          <template #default="{ row }">
            <el-select :model-value="row.inRegistry" :disabled="isReadonly" size="small" clearable placeholder="选择"
              @update:model-value="(v: string) => updateRelated(row.id, 'inRegistry', v || '')">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="披露的关联关系" min-width="140">
          <template #default="{ row }">
            <el-input :model-value="row.disclosedRelation" :disabled="isReadonly" size="small"
              @update:model-value="(v: string) => updateRelated(row.id, 'disclosedRelation', v)" />
          </template>
        </el-table-column>
        <el-table-column label="操作" width="70" align="center" fixed="right">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" type="danger" text size="small" @click="removeRelatedRow(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <el-button size="small" text type="primary" :disabled="isReadonly" :loading="isGenerating('e1-19-audit-note')" @click="generateAi('note')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="填写核对过程与差异分析（不要写结论）。可概述出资人、汇总差异、时点调节、担保与关联方情况。"
        @update:model-value="onAuditNoteInput"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button size="small" text type="primary" :disabled="isReadonly" :loading="isGenerating('e1-19-audit-conclusion')" @click="generateAi('conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="填写正式审计结论（与说明分开）。例如：征信信息与账面总体核对相符；差异已调节至报表日并无未解释差异；担保与关联方未见未披露事项等。"
        @update:model-value="onAuditConclusionInput"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-alert type="warning" :closable="false" class="tips-alert" title="提示">
      <p>1. 如存在未披露担保，需进一步询问管理层及相关人员、查阅会议纪要与法律函件、复核相关费用账户、与外部法律顾问沟通、检查公章管理，必要时查询中国裁判文书网等。</p>
      <p>2. 保持职业怀疑，关注企业信用报告真实完整及局限性（银行填列滞后、离岸账户等特殊安排）。</p>
    </el-alert>
  </div>
</template>

<style scoped>
.e1-tab-credit-check {
  padding: 12px 0;
  font-size: var(--wp-font-size, 13px);
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.chip-wrap { display: inline-flex; align-items: center; }
.section-card { margin-bottom: 12px; }
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  font-weight: 500;
}
.sub-hint { font-size: 12px; color: #909399; font-weight: 400; }
.hint-line {
  margin: 8px 0 0;
  font-size: 12px;
  color: #909399;
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
}
.auto-calc { color: #606266; }
.diff-warn { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background: #f5f7fa !important; }
.guarantee-assert { margin-top: 10px; }
.tips-alert { margin-top: 8px; }
.tips-alert p { margin: 4px 0; line-height: 1.6; }
.e1-tab-credit-check :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
</style>
