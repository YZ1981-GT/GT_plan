<script setup lang="ts">
/**
 * E1TabDigitalCurrency.vue — E1-4 数字货币明细表
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.4
 *
 * 渲染：
 * - el-table 动态行：序号 | 开户银行 | 币种 | 汇率 | 期初 | 增加 | 减少 |
 *   期末原币 | 本位币 | 账项调整 | 审定原币 | 审定人民币 | 查询余额 | 差异 | 索引号 | 备注
 * - 底部合计行 + 审计说明/审计结论 textarea
 * - 动态行增删
 * - el-skeleton加载占位
 *
 * Requirements: 14.1-14.4
 */
import { ref, inject, toRef, computed, onMounted, onBeforeUnmount, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import type { ChecklistItem } from '../composables/useE1Adjudication'
import { parseNum, calcCashBalance, calcFxConvert, sumField } from '../composables/useE1FormulaEngine'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { Setting } from '@element-plus/icons-vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface DigitalRow {
  id: string
  seq: number
  bankName: string
  currency: string
  fxRate: number
  opening: number
  increase: number
  decrease: number
  endingFc: number       // readonly: opening+increase-decrease
  endingRmb: number      // readonly: endingFc×fxRate
  adjustment: number     // 账项调整(原币)
  auditedFc: number      // readonly: endingFc+adjustment
  auditedRmb: number     // readonly: auditedFc×fxRate
  queryBalance: number   // 查询余额
  diff: number           // readonly: queryBalance-auditedFc
  diffReason: string     // 差异非零时必填
  indexNo: string        // 银行余额索引号
  confirmationIndexNo: string // 银行询证函索引号
  note: string
}

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = toRef(props, 'wpId') as Ref<string>

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-digital-rows'
const CROSS_KEY_OPENING = 'E1-digital-opening-unaudited'
const CROSS_KEY_ENDING = 'E1-digital-total-unaudited'
const NOTE_KEY = 'E1-digital-audit-note'
const CONCLUSION_KEY = 'E1-digital-audit-conclusion'

const USER_FIELDS = ['id', 'seq', 'bankName', 'currency', 'fxRate', 'opening', 'increase', 'decrease', 'adjustment', 'queryBalance', 'diffReason', 'indexNo', 'confirmationIndexNo', 'note']

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<DigitalRow[]>([])
const isLoading = ref(false)
const auditNote = ref('')
const auditConclusion = ref('')

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateId(): string {
  return `digi-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function recalcRow(row: DigitalRow): DigitalRow {
  const endingFc = calcCashBalance(row.opening, row.increase, row.decrease)
  const endingRmb = calcFxConvert(endingFc, row.fxRate)
  const auditedFc = endingFc + row.adjustment
  const auditedRmb = calcFxConvert(auditedFc, row.fxRate)
  const diff = row.queryBalance - auditedFc
  return { ...row, endingFc, endingRmb, auditedFc, auditedRmb, diff }
}

function createEmptyRow(seq: number): DigitalRow {
  return recalcRow({
    id: generateId(), seq, bankName: '', currency: '人民币', fxRate: 1,
    opening: 0, increase: 0, decrease: 0, endingFc: 0, endingRmb: 0,
    adjustment: 0, auditedFc: 0, auditedRmb: 0, queryBalance: 0, diff: 0,
    diffReason: '', indexNo: '', confirmationIndexNo: '', note: '',
  })
}

// ─── Load/Save ───────────────────────────────────────────────────────────────

function loadFromResponses(): void {
  const raw = props.allResponses.get(STORAGE_KEY)?.remark
  if (!raw) {
    rows.value = [createEmptyRow(1)]
  } else {
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) && parsed.length
        ? parsed.map((r: any, i: number) => recalcRow({
          id: String(r.id || generateId()), seq: i + 1, bankName: String(r.bankName || ''),
          currency: String(r.currency || ''), fxRate: parseNum(r.fxRate) || 1,
          opening: parseNum(r.opening), increase: parseNum(r.increase), decrease: parseNum(r.decrease),
          endingFc: 0, endingRmb: 0, adjustment: parseNum(r.adjustment),
          auditedFc: 0, auditedRmb: 0, queryBalance: parseNum(r.queryBalance), diff: 0,
          diffReason: String(r.diffReason || ''), indexNo: String(r.indexNo || ''),
          confirmationIndexNo: String(r.confirmationIndexNo || ''), note: String(r.note || ''),
        }))
        : [createEmptyRow(1)]
    } catch { rows.value = [createEmptyRow(1)] }
  }
  auditNote.value = props.allResponses.get(NOTE_KEY)?.remark || ''
  auditConclusion.value = props.allResponses.get(CONCLUSION_KEY)?.remark || ''
}

loadFromResponses()
watch(() => props.allResponses, loadFromResponses)

function serializeRows(): string {
  return JSON.stringify(rows.value.map(row => {
    const obj: Record<string, unknown> = {}
    for (const f of USER_FIELDS) obj[f] = (row as any)[f]
    return obj
  }))
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function scheduleSave(): void {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => { saveTimer = null; persistToResponses() }, 2000)
}

function persistToResponses(): void {
  const serialized = serializeRows()
  const items: ChecklistItem[] = [{ item_id: STORAGE_KEY, conclusion: null, remark: serialized }]
  props.allResponses.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })

  // Cross-sheet totals for E1-1
  const openingTotal = String(totalRow.value.opening)
  const endingTotal = String(totalRow.value.auditedRmb)
  props.allResponses.set(CROSS_KEY_OPENING, { item_id: CROSS_KEY_OPENING, conclusion: null, remark: openingTotal })
  props.allResponses.set(CROSS_KEY_ENDING, { item_id: CROSS_KEY_ENDING, conclusion: null, remark: endingTotal })
  items.push({ item_id: CROSS_KEY_OPENING, conclusion: null, remark: openingTotal })
  items.push({ item_id: CROSS_KEY_ENDING, conclusion: null, remark: endingTotal })

  // Audit note/conclusion
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })
  items.push({ item_id: NOTE_KEY, conclusion: null, remark: auditNote.value })
  items.push({ item_id: CONCLUSION_KEY, conclusion: null, remark: auditConclusion.value })

  props.saveImmediate(items).catch(() => {})
}

onBeforeUnmount(() => { if (saveTimer) { clearTimeout(saveTimer); persistToResponses() } })

// ─── Computed Total ──────────────────────────────────────────────────────────

const totalRow = computed(() => {
  const r = rows.value as unknown as Array<Record<string, unknown>>
  return {
    opening: sumField(r, 'opening'),
    increase: sumField(r, 'increase'),
    decrease: sumField(r, 'decrease'),
    endingFc: sumField(r, 'endingFc'),
    endingRmb: sumField(r, 'endingRmb'),
    adjustment: sumField(r, 'adjustment'),
    auditedFc: sumField(r, 'auditedFc'),
    auditedRmb: sumField(r, 'auditedRmb'),
    queryBalance: sumField(r, 'queryBalance'),
    diff: sumField(r, 'diff'),
  }
})

// ─── Row CRUD ────────────────────────────────────────────────────────────────

function addRow(): void {
  if (props.isReadonly) return
  rows.value = [...rows.value, createEmptyRow(rows.value.length + 1)]
  scheduleSave()
}

function removeRow(rowId: string): void {
  if (props.isReadonly) return
  rows.value = rows.value.filter(r => r.id !== rowId).map((r, i) => ({ ...r, seq: i + 1 }))
  scheduleSave()
}

function updateCell(rowId: string, field: string, value: number | string): void {
  if (props.isReadonly) return
  const idx = rows.value.findIndex(r => r.id === rowId)
  if (idx === -1) return
  const row = { ...rows.value[idx] }
  const numericFields = ['fxRate', 'opening', 'increase', 'decrease', 'adjustment', 'queryBalance']
  if (numericFields.includes(field)) (row as any)[field] = parseNum(value)
  else (row as any)[field] = String(value)
  const newRows = [...rows.value]
  newRows[idx] = recalcRow(row)
  rows.value = newRows
  scheduleSave()
}

function onNoteChange(val: string): void {
  auditNote.value = val; scheduleSave()
}
function onConclusionChange(val: string): void {
  auditConclusion.value = val; scheduleSave()
}

const sheetCode = computed(() => 'E1-4')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: wpIdRef,
  sheet: sheetCode,
})
const { generateText, isGenerating } = useE1AiGenerate(wpIdRef)

async function handleImport(file: File): Promise<boolean> {
  const result = await importData(file)
  if (result.success) {
    ElMessage.success(result.message || '导入成功')
    await reloadWorkpaperData?.()
  } else ElMessage.warning(result.message || '导入失败')
  return false
}

function needsDiffReason(row: DigitalRow): boolean {
  return Math.abs(row.diff) > 0.005 && !row.diffReason.trim()
}

function getRowClass({ row }: { row: DigitalRow }): string {
  return needsDiffReason(row) ? 'e1-digital-missing-reason-row' : ''
}

function buildAiContext(): Record<string, unknown> {
  return {
    明细: rows.value,
    合计: totalRow.value,
    未说明差异: rows.value.filter(needsDiffReason),
    全部差异: rows.value.filter(row => Math.abs(row.diff) > 0.005),
  }
}

async function generateNarrative(kind: 'note' | 'conclusion' | 'anomaly'): Promise<void> {
  if (props.isReadonly) return
  const isConclusion = kind === 'conclusion'
  const target = isConclusion ? auditConclusion : auditNote
  const text = await generateText({
    section: `e1-digital-${kind}`,
    prompt: kind === 'anomaly'
      ? '分析数字货币查询余额与审定原币差异、异常汇率、账项调整、钱包或平台可回收性及受限风险，形成可追溯的异常分析和后续审计程序。'
      : isConclusion
        ? '根据数字货币明细、查询余额核对、差异原因、账项调整和审计说明形成审慎审计结论；存在未说明差异时不得直接表述未见异常。'
        : '根据数字货币明细、钱包或平台查询证据、汇率折算、账项调整和差异原因生成专业审计说明。',
    context: { ...buildAiContext(), 审计说明: auditNote.value },
    existingContent: target.value,
    confirmTitle: kind === 'anomaly' ? '确认填入异常分析' : `确认填入审计${isConclusion ? '结论' : '说明'}`,
  })
  if (text) isConclusion ? onConclusionChange(text) : onNoteChange(text)
}

async function generateDiffReason(row: DigitalRow): Promise<void> {
  if (props.isReadonly || Math.abs(row.diff) <= 0.005) return
  const text = await generateText({
    section: `e1-digital-diff-${row.id}`,
    prompt: '根据该数字货币明细的查询余额、审定原币、差异、汇率及账项调整，生成简明、可核验的差异原因；不得虚构未提供的证据。',
    context: { 行明细: row },
    existingContent: row.diffReason,
    confirmTitle: '确认填入差异原因',
  })
  if (text) updateCell(row.id, 'diffReason', text)
}

// ─── 列设置 ──────────────────────────────────────────────────────────────────

const DIG_COL_STORAGE_KEY = 'e1-digital-currency-column-prefs'

const DIG_COL_GROUPS = [
  { label: '基础', keys: ['bankName', 'currency', 'fxRate'] },
  { label: '余额变动', keys: ['opening', 'increase', 'decrease'] },
  { label: '审定与差异', keys: ['adjustment', 'queryBalance', 'diffReason'] },
  { label: '索引', keys: ['indexNo', 'confirmationIndexNo', 'note'] },
]

const DIG_COL_LABELS: Record<string, string> = {
  bankName: '开户银行', currency: '币种', fxRate: '汇率',
  opening: '期初', increase: '增加', decrease: '减少',
  adjustment: '账项调整', queryBalance: '查询余额', diffReason: '差异原因',
  indexNo: '银行余额索引号', confirmationIndexNo: '询证函索引号', note: '备注',
}

const DIG_DEFAULT_HIDDEN: string[] = ['confirmationIndexNo']
const digHiddenCols = ref<Set<string>>(new Set())

;(() => {
  try {
    const stored = localStorage.getItem(DIG_COL_STORAGE_KEY)
    if (stored) { digHiddenCols.value = new Set(JSON.parse(stored)); return }
  } catch {}
  digHiddenCols.value = new Set(DIG_DEFAULT_HIDDEN)
})()

function isDigColVisible(key: string): boolean { return !digHiddenCols.value.has(key) }
function toggleDigCol(key: string): void {
  const s = new Set(digHiddenCols.value)
  if (s.has(key)) s.delete(key); else s.add(key)
  digHiddenCols.value = s
  localStorage.setItem(DIG_COL_STORAGE_KEY, JSON.stringify([...s]))
}
function resetDigColDefaults(): void {
  digHiddenCols.value = new Set(DIG_DEFAULT_HIDDEN)
  localStorage.setItem(DIG_COL_STORAGE_KEY, JSON.stringify(DIG_DEFAULT_HIDDEN))
}
</script>

<template>
  <div class="e1-tab-digital-currency">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表列示数字货币（人民币数字货币/其他）明细，归入其他货币资金（科目1012）列报。</p>
        <p>2. 灰色底纹列（期末原币/本位币/审定原币/审定人民币）为自动计算，不可手工录入。</p>
        <p>3. 差异列=查询余额-审定原币，差异≠0时红色高亮，须核对钱包/平台查询余额并说明原因。</p>
        <p>4. 数字货币列报参照企业会计准则解释第15号资金集中管理相关规定，关注可回收性与受限情况。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确定数字货币在资产负债表日确实存在且已恰当记录（存在、完整、计价与列报）；通过查询余额验证真实性，为 E1-1 审定表提供其他货币资金审定依据。"
      class="objective-alert"
    />

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <!-- 工具栏 -->
        <div class="tab-toolbar">
          <div class="toolbar-left">
            <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">+ 新增行</el-button>
          </div>
          <div class="toolbar-right">
            <el-dropdown size="small" trigger="click" :disabled="isReadonly">
              <el-button size="small">导入导出 ▾</el-button>
              <template #dropdown>
                <el-dropdown-menu>
                  <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
                  <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
                  <el-dropdown-item>
                    <el-upload :show-file-list="false" accept=".xlsx,.xls" :before-upload="handleImport" :disabled="isImporting">
                      <span>导入数据</span>
                    </el-upload>
                  </el-dropdown-item>
                </el-dropdown-menu>
              </template>
            </el-dropdown>
            <el-popover trigger="click" :width="260" placement="bottom-end">
              <template #reference>
                <el-button size="small" circle><el-icon><Setting /></el-icon></el-button>
              </template>
              <div class="col-prefs-popover">
                <div class="col-prefs-header">
                  <span>列显示设置</span>
                  <el-button size="small" text type="primary" @click="resetDigColDefaults">重置默认</el-button>
                </div>
                <div v-for="group in DIG_COL_GROUPS" :key="group.label" class="col-prefs-group">
                  <div class="col-prefs-group-label">{{ group.label }}</div>
                  <div v-for="key in group.keys" :key="key" class="col-prefs-item">
                    <el-checkbox :model-value="isDigColVisible(key)" size="small" @change="toggleDigCol(key)">{{ DIG_COL_LABELS[key] || key }}</el-checkbox>
                  </div>
                </div>
              </div>
            </el-popover>
            <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
            <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
          </div>
        </div>

        <el-table :data="rows" border stripe size="small" style="width: 100%" max-height="500" :row-class-name="getRowClass">
          <el-table-column label="序号" width="60" align="center">
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('bankName')" label="开户银行" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.bankName" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'bankName', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('currency')" label="币种" width="90">
            <template #default="{ row }">
              <el-input :model-value="row.currency" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'currency', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('fxRate')" label="汇率" width="80" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.fxRate" :disabled="isReadonly" :controls="false" :precision="4" size="small" @change="(v: number | undefined) => updateCell(row.id, 'fxRate', v ?? 1)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('opening')" label="期初" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.opening" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'opening', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('increase')" label="增加" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.increase" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'increase', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('decrease')" label="减少" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.decrease" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'decrease', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="期末原币" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingFc) }}</span></template>
          </el-table-column>
          <el-table-column label="本位币" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.endingRmb) }}</span></template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('adjustment')" label="账项调整" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.adjustment" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'adjustment', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="审定原币" width="110" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedFc) }}</span></template>
          </el-table-column>
          <el-table-column label="审定人民币" width="120" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="readonly-val">{{ displayPrefs.fmtAmount(row.auditedRmb) }}</span></template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('queryBalance')" label="查询余额" width="110" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.queryBalance" :disabled="isReadonly" :controls="false" size="small" @change="(v: number | undefined) => updateCell(row.id, 'queryBalance', v ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="差异" width="110" align="right">
            <template #default="{ row }">
              <span :class="{ 'red-text': Math.abs(row.diff) > 0.005 }">{{ displayPrefs.fmtAmount(row.diff) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('diffReason')" label="差异原因" min-width="220">
            <template #default="{ row }">
              <div class="diff-reason-cell">
                <el-input
                  :model-value="row.diffReason"
                  :disabled="isReadonly || Math.abs(row.diff) <= 0.005"
                  size="small"
                  :class="{ 'required-input': needsDiffReason(row) }"
                  :placeholder="Math.abs(row.diff) > 0.005 ? '差异非零，必须说明原因' : '无差异'"
                  @change="(v: string) => updateCell(row.id, 'diffReason', v)"
                />
                <el-button
                  v-if="Math.abs(row.diff) > 0.005"
                  text
                  type="warning"
                  size="small"
                  :disabled="isReadonly"
                  :loading="isGenerating(`e1-digital-diff-${row.id}`)"
                  @click="generateDiffReason(row)"
                >🤖</el-button>
              </div>
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('indexNo')" label="银行余额索引号" width="120">
            <template #default="{ row }">
              <el-input :model-value="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'indexNo', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('confirmationIndexNo')" label="银行询证函索引号" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.confirmationIndexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'confirmationIndexNo', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="isDigColVisible('note')" label="备注" min-width="120">
            <template #default="{ row }">
              <el-input :model-value="row.note" :disabled="isReadonly" size="small" @change="(v: string) => updateCell(row.id, 'note', v)" />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="操作" width="70" fixed="right" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- Total Row -->
        <div class="total-row">
          <span class="total-label">合计</span>
          <span>期初: {{ displayPrefs.fmtAmount(totalRow.opening) }}</span>
          <span>期末原币: {{ displayPrefs.fmtAmount(totalRow.endingFc) }}</span>
          <span>本位币: {{ displayPrefs.fmtAmount(totalRow.endingRmb) }}</span>
          <span>审定人民币: {{ displayPrefs.fmtAmount(totalRow.auditedRmb) }}</span>
        </div>

        <!-- 审计意见区（卡片式） -->
        <el-card class="opinion-card" shadow="never">
          <template #header>
            <div class="opinion-header">
              <span class="opinion-title">审计说明与结论</span>
              <div class="opinion-chips">
                <GtIndexChip value="wp:E1-1" :context-project-id="projectId" />
              </div>
            </div>
          </template>

          <div class="opinion-section">
            <div class="opinion-section-header">
              <span class="opinion-section-label">1. 审计说明</span>
              <div class="opinion-actions">
                <el-button size="small" type="warning" plain :disabled="isReadonly" :loading="isGenerating('e1-digital-anomaly')" @click="generateNarrative('anomaly')">🤖 异常分析</el-button>
                <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-digital-note')" @click="generateNarrative('note')">🤖 AI辅助</el-button>
              </div>
            </div>
            <el-input
              type="textarea"
              :model-value="auditNote"
              :disabled="isReadonly"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="填写审计说明（数字货币查询余额核对、可回收性、受限情况等）"
              @change="onNoteChange"
            />
          </div>

          <div class="opinion-section">
            <div class="opinion-section-header">
              <span class="opinion-section-label">2. 审计结论</span>
              <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-digital-conclusion')" @click="generateNarrative('conclusion')">🤖 AI辅助</el-button>
            </div>
            <el-input
              type="textarea"
              :model-value="auditConclusion"
              :disabled="isReadonly"
              :autosize="{ minRows: 2, maxRows: 6 }"
              placeholder="填写审计结论"
              @change="onConclusionChange"
            />
          </div>
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-digital-currency { padding: 12px 0; }
.e1-tab-digital-currency :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-digital-currency :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
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
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.readonly-val { color: #909399; background: #f5f7fa; padding: 2px 6px; border-radius: 2px; }
.red-text { color: #f56c6c; font-weight: 600; }
:deep(.e1-digital-missing-reason-row) { background: #fef0f0 !important; }
.diff-reason-cell { display: flex; align-items: center; gap: 4px; }
.diff-reason-cell .el-input { flex: 1; }
:deep(.required-input .el-input__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
.opinion-actions { display: flex; gap: 6px; }
.total-row {
  display: flex; gap: 16px; padding: 10px 12px; margin-top: 8px;
  background: #f5f7fa; border: 1px solid #ebeef5; border-radius: 4px;
  font-weight: 700; font-size: var(--wp-font-size, 13px); flex-wrap: wrap;
}
.total-label { color: #303133; min-width: 40px; }
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-chips { display: flex; gap: 6px; }
.opinion-section { margin-bottom: 16px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.opinion-section-label {
  font-size: 14px;
  font-weight: 500;
  color: #303133;
}
/* 列设置 popover */
.col-prefs-popover { max-height: 320px; overflow-y: auto; }
.col-prefs-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; font-weight: 600; font-size: 13px; }
.col-prefs-group { margin-bottom: 8px; }
.col-prefs-group-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.col-prefs-item { margin-left: 8px; }
</style>
