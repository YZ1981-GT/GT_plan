<template>
  <el-dialog
    v-model="visible"
    title="附注公式管理"
    width="960px"
    append-to-body
    destroy-on-close
  >
    <div v-if="!currentNote" class="gt-nf-empty">
      请先选择一个附注章节
    </div>
    <template v-else>
      <div class="gt-nf-header">
        <span>{{ currentNote.note_section }} {{ currentNote.section_title }}</span>
        <el-tag v-if="currentNote.content_type" size="small" type="info">{{ currentNote.content_type }}</el-tag>
      </div>

      <!-- 分类 Tab -->
      <el-tabs v-model="activeCategory" style="margin-top: 12px">
        <el-tab-pane label="⚡ 自动运算" name="auto_calc" />
        <el-tab-pane label="🔍 逻辑审核" name="logic_check" />
        <el-tab-pane label="💡 合理性" name="reasonability" />
      </el-tabs>

      <div class="gt-nf-edit-hint">双击公式 / 说明格修改，提交后自动保存</div>

      <!-- 公式列表 -->
      <el-table v-loading="loading" :data="filteredFormulas" size="small" border max-height="350">
        <el-table-column label="目标单元格" min-width="200">
          <template #default="{ row }">
            <!-- 新增公式选目标（表 / 行 / 列）：原先目标列不可编辑，新增的公式保存时被当空行丢掉却提示「已保存」 -->
            <div v-if="row._isNew" class="gt-nf-target">
              <template v-if="targetTables.length">
                <el-select :model-value="cellOf(row).table" size="small" placeholder="表" aria-label="目标表"
                           @update:model-value="(v: number) => setCell(row, { table: v })">
                  <el-option v-for="t in targetTables" :key="t.index" :label="t.name" :value="t.index" />
                </el-select>
                <el-select :model-value="cellOf(row).row" size="small" placeholder="行" aria-label="目标行"
                           :disabled="cellOf(row).table === undefined"
                           @update:model-value="(v: number) => setCell(row, { ...cellOf(row), row: v })">
                  <el-option v-for="(label, i) in tableOf(row)?.rows || []" :key="i" :label="label" :value="i" />
                </el-select>
                <el-select :model-value="cellOf(row).col" size="small" placeholder="列" aria-label="目标列"
                           :disabled="cellOf(row).table === undefined"
                           @update:model-value="(v: number) => setCell(row, { ...cellOf(row), col: v })">
                  <el-option v-for="(label, i) in tableOf(row)?.columns || []" :key="i" :label="label" :value="i" />
                </el-select>
              </template>
              <span v-else class="gt-nf-hint">本章节没有表格，不能设单元格公式</span>
            </div>
            <span v-else :title="row.target" style="font-size: var(--gt-font-size-xs)">
              {{ row.target_label || row.target || '（未选目标）' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="公式" min-width="250">
          <template #default="{ row }">
            <GtGridCell :value="row.formula" :text="row.formula || ''">
              <template #display><code style="font-size: var(--gt-font-size-xs)">{{ row.formula }}</code></template>
              <ElInput :model-value="row.formula" size="small" @change="onFormulaCellCommit(row, 'formula', $event)">
                <template #append>
                  <el-button size="small" @click="openRefPicker(row)">引用</el-button>
                </template>
              </ElInput>
            </GtGridCell>
          </template>
        </el-table-column>
        <el-table-column label="说明" width="160">
          <template #default="{ row }">
            <GtGridCell :value="row.description" :text="row.description || ''">
              <template #display><span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ row.description }}</span></template>
              <ElInput :model-value="row.description" size="small" @change="onFormulaCellCommit(row, 'description', $event)" />
            </GtGridCell>
          </template>
        </el-table-column>
        <el-table-column label="来源" width="120">
          <template #default="{ row }">
            <el-tag v-if="row.layer_label" size="small" effect="plain" :type="row.layer === 'project' ? 'warning' : 'info'">{{ row.layer_label }}</el-tag>
            <el-tag v-if="row.pending" size="small" type="danger" effect="plain">待确认</el-tag>
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary)">{{ row.source }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="80" align="center">
          <template #default="{ row }">
            <el-button v-if="row._isNew" size="small" link type="success" :loading="persisting" @click="completeRow">保存</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div style="margin-top: 12px; display: flex; gap: 8px">
        <el-button size="small" @click="addFormula">新增公式</el-button>
      </div>

      <!-- S2 ADR-CCN-02：logic_check / reasonability 执行结果问题清单（不回填单元格，只展示） -->
      <div v-if="lastCheckedAt" style="margin-top: 16px">
        <GtFormulaIssuePanel
          :issues="checkIssues"
          :outcomes="checkOutcomes"
          :last-computed-at="lastCheckedAt"
          :loading="applying || regenerating"
          :show-refresh="false"
        />
      </div>
    </template>

    <template #footer>
      <el-button v-if="currentNote" @click="onRegenerate" :loading="regenerating">重新生成</el-button>
      <el-button type="primary" @click="onApply" :loading="applying">应用自动运算</el-button>
      <el-button @click="visible = false">关闭</el-button>
    </template>

    <!-- 引用选择器 -->
    <FormulaRefPicker
      v-model="showRefPicker"
      :report-rows="refPickerData.reportRows"
      :tb-rows="refPickerData.tbRows"
      :note-rows="refPickerData.noteRows"
      @insert="onInsertRef"
    />
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { fetchTrialBalanceRows } from '@/services/trialBalanceRows'
// spec: formula-management-runtime-closure Task 14 — 端点收敛进 apiPaths（纯搬迁）
import { noteFormula } from '@/services/apiPaths/formula'
import { SINGLE_WP_REF, useAddressRegistry, type ValidateResult } from '@/stores/addressRegistry'
import { acnr, addressRegistry } from '@/services/apiPaths/system'
import { isAcnrRegistryFailure, parseAcnrRegistryFailure } from '@/services/acnr/registryLockFailure'
import type { AcnrResolveResult } from '@/services/acnr/useAcnr'
import { formatRefIssue } from '@/utils/formulaRefIssues'
import { showFormulaError } from '@/composables/formula/useFormulaSettings'
import FormulaRefPicker from './FormulaRefPicker.vue'
import GtGridCell from '@/components/grid/GtGridCell.vue'
import GtFormulaIssuePanel from './GtFormulaIssuePanel.vue'
import { formulaOutcomeStatus, formulaCheckNumber, formulaCheckSeverity, type FormulaIssueItem, type FormulaCheckOutcome } from './formulaIssueHint'
import { checkReasonOf } from '@/utils/consistencyCheckStatus'
import { ElInput } from '@/components/grid/adapters'
import {
  describeApplyResult, describeFormulaTarget, formulaKey, parseFormulaKey, type NoteFormulaTargetTable,
} from './noteFormulaTargets'

const props = defineProps<{
  modelValue: boolean
  currentNote: any
  projectId: string
  year: number
  /** 未生成附注时的模板口径；缺省遵循接口的 soe，而不继承其他弹窗的共享绑定。 */
  templateType?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'applied': []
  /** 公式集已保存（宿主据此刷新自己展示的附注公式） */
  'saved': []
}>()

// 父组件回传关闭状态前，也不能被已经排队的 props watcher 重新建代。
let locallyClosed = false
const visible = computed({
  get: () => props.modelValue,
  set: (v) => {
    if (!v) {
      locallyClosed = true
      invalidateContext()
    }
    emit('update:modelValue', v)
  },
})

const activeCategory = ref('auto_calc')
const applying = ref(false)
const regenerating = ref(false)
/** 上次「应用自动运算」返回的校对结果（logic_check / reasonability 类别公式，不回填单元格）。 */
const lastChecks = ref<any[]>([])
/** 上次执行时间（ISO UTC 串），用于面板显示"最近计算"。 */
const lastCheckedAt = ref<string | null>(null)

// 上下文身份不可变；CAS 和队列只在该代内推进，不能跨项目 / 年度 / 章节续用。
type DialogContext = Readonly<{
  generation: number
  projectId: string
  year: number
  note: any
  noteSection: string
  modelValue: boolean
  templateType: string
  invalidated: Promise<void>
  invalidate: () => void
  state: {
    rows: any[]
    loaded: Record<string, string | null> | null
    loadGeneration: number
    persistTail: Promise<void>
    pending: CellSave[]
    active: CellSave[]
    worker: Promise<void> | null
  }
}>
let contextGeneration = 0
let currentContext: DialogContext | null = null
let disposed = false

function isCurrent(context: DialogContext | null): context is DialogContext {
  return !!context && !disposed && !locallyClosed && currentContext === context
    && context.generation === contextGeneration && context.modelValue && props.modelValue
    && context.projectId === props.projectId && context.year === props.year
    && context.note === props.currentNote && context.noteSection === props.currentNote?.note_section
    && context.templateType === (props.templateType || 'soe')
}

/** 只结束本代调用方的等待，不取消已经发往原目标的请求。 */
function untilInvalidated<T>(context: DialogContext, pending: Promise<T>, fallback: T): Promise<T> {
  return Promise.race([pending, context.invalidated.then(() => fallback)])
}

function invalidateContext() {
  contextGeneration += 1
  if (currentContext) {
    currentContext.invalidate()
    for (const edit of [...currentContext.state.pending.splice(0), ...currentContext.state.active]) {
      edit.waiters.splice(0).forEach((resolve) => resolve(false))
    }
  }
  currentContext = null
  clearCheckResults()
  formulas.value = []
  loadedTokens.value = null
  targetTables.value = []
  loading.value = persisting.value = applying.value = regenerating.value = false
  editingRow.value = null
  showRefPicker.value = false
  refPickerData.value = { reportRows: [], tbRows: [], noteRows: [] }
}

/** 复用统一五态与金额口径；缺少 / 未知状态不得被 passed 或标签冒充。 */
const normalizedChecks = computed(() => lastChecks.value.map((c) => ({
  ...c,
  status: formulaOutcomeStatus(c),
  reason: typeof c.reason === 'string' && c.reason.trim() ? c.reason : checkReasonOf(c),
})))
const checkIssues = computed<FormulaIssueItem[]>(() => normalizedChecks.value
  .filter((c) => ['failed', 'not_executed', 'error'].includes(c.status))
  .map((c) => ({
    formula_id: String(c.rule_id || c.source || ''),
    description: String(c.description || c.label || c.reason || '校对未完成'),
    left_value: formulaCheckNumber(c.left) == null ? null : String(c.left),
    right_value: formulaCheckNumber(c.right) == null ? null : String(c.right),
    addr_id: c.source ? String(c.source) : null,
    status: c.status,
    reason: c.reason,
    label: c.label,
    severity: formulaCheckSeverity(c.severity),
  })))

const checkOutcomes = computed<FormulaCheckOutcome[]>(() => normalizedChecks.value.map((c) => ({
  formula_id: String(c.rule_id || c.source || ''),
  description: String(c.description || c.label || c.reason || ''),
  expression: String(c.rule_id || ''),
  passed: c.status === 'passed',
  status: c.status,
  reason: c.reason,
  label: c.label,
  severity: formulaCheckSeverity(c.severity),
  left_value: formulaCheckNumber(c.left),
  right_value: formulaCheckNumber(c.right),
})))

function clearCheckResults() {
  lastChecks.value = []
  lastCheckedAt.value = null
}

function applyCheckResults(result: any, context: DialogContext) {
  if (!isCurrent(context)) return
  lastChecks.value = result?.no_result === true || result?.status === 'no_result' ? []
    : Array.isArray(result?.checks) ? result.checks.filter((c: any) => c && typeof c === 'object') : []
  lastCheckedAt.value = new Date().toISOString()
}
const persisting = ref(false)
const loading = ref(false)
const showRefPicker = ref(false)
const editingRow = ref<any>(null)

// 地址库只供引用选择器使用；保存校验显式携带本代参数，不读取共享 store 的可变绑定。
const addrStore = useAddressRegistry()

// 引用选择器数据（懒加载）
const refPickerData = ref<{ reportRows: any[], tbRows: any[], noteRows: any[] }>({
  reportRows: [], tbRows: [], noteRows: [],
})

async function openRefPicker(row: any) {
  const context = currentContext
  if (!isCurrent(context) || !context.state.rows.includes(row)) return
  editingRow.value = row
  try {
    if (!refPickerData.value.reportRows.length) {
      const [reportData, tbData] = await Promise.all([
        api.get(`/api/reports/${context.projectId}/${context.year}/balance_sheet`, { _silent: true, _dedupe: false } as any).catch(() => []),
        fetchTrialBalanceRows(context.projectId, { year: context.year }).then((r) => r.rows).catch(() => []),
      ])
      if (!isCurrent(context) || editingRow.value !== row || !context.state.rows.includes(row)) return
      refPickerData.value.reportRows = Array.isArray(reportData) ? reportData : (reportData || [])
      refPickerData.value.tbRows = Array.isArray(tbData) ? tbData : (tbData || [])
    }
  } catch { /* 静默 */ }
  if (isCurrent(context) && editingRow.value === row && context.state.rows.includes(row)) showRefPicker.value = true
}

function onInsertRef(formula: string, _label: string) {
  const context = currentContext
  const row = editingRow.value
  if (!isCurrent(context) || !context.state.rows.includes(row)) return
  const before = String(row.formula || '')
  const value = before + formula
  row.formula = value
  if (!row._isNew) void scheduleSave(row, 'formula', before, value)
}

// 附注公式列表（Req 15.1：onOpen 从后端加载已保存/预览集，替代此前空 ref）
const formulas = ref<any[]>([])
/**
 * 载入时的版本令牌（spec formula-global-settings-sync）：保存时原样带回，后端据此只写
 * 改过的公式位并判定并发冲突（缺失 428、已被他人修改 409）。
 */
const loadedTokens = ref<Record<string, string | null> | null>(null)

/** 目标清单：逐表行名 / 列名（列表接口 `targets`，与执行器同一份表格）。 */
const targetTables = ref<NoteFormulaTargetTable[]>([])

/** 列表 / 保存接口同形：`{formulas, loaded, targets}`；每条带层级标签（全局 / 本项目 / 系统预设 …）与可读目标。 */
function applyListing(resp: any, context: DialogContext) {
  if (!isCurrent(context)) return
  const list = resp?.formulas
  formulas.value = (Array.isArray(list) ? list : []).map((f: any) => ({ ...f }))
  context.state.rows = formulas.value
  context.state.loaded = resp?.loaded ?? {}
  loadedTokens.value = context.state.loaded
  targetTables.value = Array.isArray(resp?.targets) ? resp.targets : []
}

type DraftCell = { table?: number; row?: number; col?: number }

/** 新增行正在选的目标（选齐表 / 行 / 列才写回 `target`）。 */
function cellOf(row: any): DraftCell {
  if (row._cell) return row._cell
  return parseFormulaKey(row.target) ?? {}
}

function tableOf(row: any): NoteFormulaTargetTable | undefined {
  const t = cellOf(row).table
  return targetTables.value.find((x) => x.index === t)
}

function setCell(row: any, cell: DraftCell) {
  if (!isCurrent(currentContext) || !currentContext.state.rows.includes(row)) return
  row._cell = cell
  if (cell.table !== undefined && cell.row !== undefined && cell.col !== undefined) {
    row.target = formulaKey({ table: cell.table, row: cell.row, col: cell.col })
    row.target_label = describeFormulaTarget(row.target, targetTables.value)
  } else {
    row.target = ''
    row.target_label = ''
  }
}

const filteredFormulas = computed(() => {
  return formulas.value.filter(f => f.category === activeCategory.value)
})

// ─── 加载当前公式集（Req 15.1） ───────────────────────────────
async function loadFormulas(context = currentContext): Promise<boolean> {
  if (!isCurrent(context)) return false
  const generation = ++context.state.loadGeneration
  const ownsLoad = () => isCurrent(context) && generation === context.state.loadGeneration
  loading.value = true
  try {
    const resp = await api.get(
      noteFormula.list(context.projectId, context.year, context.noteSection), { _silent: true, _dedupe: false } as any,
    )
    if (!ownsLoad()) return false
    applyListing(resp, context)
    // 旧 GET 不得绑定选择器；保存校验不依赖此共享状态。
    try { void Promise.resolve(addrStore.refresh(context.projectId, context.year, context.templateType)).catch(() => {}) } catch { /* 静默 */ }
    return true
  } catch (e: any) {
    if (ownsLoad()) {
      formulas.value = []
      context.state.rows = formulas.value
      loadedTokens.value = context.state.loaded = null
      targetTables.value = []
      handleApiError(e, '加载公式失败')
    }
    return false
  } finally {
    if (ownsLoad()) loading.value = false
  }
}

// ─── 引用校验：每个请求显式冻结项目 / 年度 / 模板 ───
async function validateFormula(formula: string, context: DialogContext): Promise<ValidateResult | null> {
  if (!isCurrent(context)) return null
  if (SINGLE_WP_REF.test(formula)) {
    let result: AcnrResolveResult | null = null
    try {
      result = await api.get<AcnrResolveResult>(acnr.resolve, {
        params: { formula_ref: formula, project_id: context.projectId }, _silent: true, _dedupe: false,
      } as any)
    } catch (error) {
      result = parseAcnrRegistryFailure(error)
    }
    if (!isCurrent(context)) return null
    if (result?.found) return { valid: true, issues: [], formula }
    if (isAcnrRegistryFailure(result)) {
      return { valid: false, issues: [{ ref: formula, message: result?.reason }], formula }
    }
  }
  if (!isCurrent(context)) return null
  try {
    return await api.post<ValidateResult>(addressRegistry.validate, {
      formula, project_id: context.projectId, year: context.year, template_type: context.templateType,
    }, { _silent: true } as any)
  } catch {
    return { valid: false, issues: [{ ref: formula, message: '校验请求失败' }], formula }
  }
}

async function collectDanglingRefs(list: any[], context: DialogContext): Promise<string[]> {
  const dangling: string[] = []
  for (const row of list) {
    if (!isCurrent(context)) break
    const expr = (row?.formula || '').trim()
    if (!expr) continue
    try {
      const res = await validateFormula(expr, context)
      if (!isCurrent(context)) break
      if (res && res.valid === false) {
        for (const iss of (res.issues || [])) dangling.push(formatRefIssue(iss) || expr)
      }
    } catch {
      // 请求失败已明确返回 invalid；保留既有设施意外失败的 fail-open。
    }
  }
  return dangling
}

// ─── 持久化当前编辑集（Req 15.2/15.3） ────────────────────────
// 整体 PUT 用户编辑集（"这套就是最新集"语义）；空行由后端过滤。
// 保存前经 ACNR 校验，悬空引用提示且不入库（Req 15.5）。
type PersistOptions = { skipNew?: boolean }

/** 保存回执只就地刷新同代元数据，不替换编辑值，也不把旧令牌带进新上下文。 */
function applyPersistResult(resp: any, context: DialogContext) {
  if (!isCurrent(context) || !resp?.loaded) return
  context.state.loaded = resp.loaded
  loadedTokens.value = context.state.loaded
  const fresh = new Map<string, any>((resp.formulas || []).map((f: any) => [f.target, f]))
  for (const formula of context.state.rows) {
    const saved = fresh.get(formula.target)
    if (!saved) continue
    Object.assign(formula, {
      layer: saved.layer,
      layer_label: saved.layer_label,
      pending: saved.pending,
      slot_key: saved.slot_key,
      target_label: saved.target_label ?? formula.target_label,
    })
    formula._isNew = false
    delete formula._cell
  }
}

async function performPersist(context: DialogContext, options: PersistOptions): Promise<boolean> {
  if (!isCurrent(context)) return false
  // 出队时冻结同代模型；CAS 仍取该代上一批的回执，而不是入队时的陈旧令牌。
  const candidates = context.state.rows
    .filter((formula) => !options.skipNew || !formula._isNew)
    .map((formula) => ({ ...formula }))
  // 自动保存只提交既有行：尚未选完目标的新行留在本地，不能阻塞另一格的提交。
  const untargeted = candidates.filter(f => (f?.formula || '').trim() && !String(f?.target || '').trim())
  if (untargeted.length) {
    ElMessage.warning(`有 ${untargeted.length} 条公式没有选择目标单元格（表 / 行 / 列），未保存`)
    return false
  }
  const dangling = await collectDanglingRefs(candidates, context)
  if (!isCurrent(context)) return false
  if (dangling.length) {
    ElMessage.error(`公式引用无法解析，未保存：${[...new Set(dangling)].join('；')}`)
    return false
  }
  // 剔除前端本地态字段（_isNew / _cell）与只读展示字段（层级 / 可读目标），只送持久化 shape。
  const payload = candidates
    .filter(f => (f?.formula || '').trim())
    .map(({ _isNew, _cell, layer, layer_label, pending, slot_key, target_label, ...rest }) => rest)
  persisting.value = true
  try {
    const resp = await api.put(
      noteFormula.list(context.projectId, context.year, context.noteSection),
      { formulas: payload, loaded: context.state.loaded },
      { _silent: true } as any,
    )
    if (!isCurrent(context)) return false
    applyPersistResult(resp, context)
    emit('saved')
    return true
  } catch (e: any) {
    // 仅当前代展示 428 / 409 / 403 / 423 / 422；失效不等于当前保存失败。
    if (isCurrent(context)) showFormulaError(e, '保存失败')
    return false
  } finally {
    if (isCurrent(context)) persisting.value = false
  }
}

/** 同代 PUT 串行续传 CAS；新上下文不等待旧上下文的在途请求。 */
function persistFormulas(options: PersistOptions = {}, context = currentContext): Promise<boolean> {
  if (!isCurrent(context)) return Promise.resolve(false)
  const run = () => performPersist(context, options)
  const result = context.state.persistTail.then(run, run)
  context.state.persistTail = result.then(() => undefined, () => undefined)
  return untilInvalidated(context, result, false)
}

type EditableFormulaField = 'formula' | 'description'
type CellSave = {
  row: any
  field: EditableFormulaField
  before: string
  value: string
  waiters: Array<(saved: boolean) => void>
}
function sameCell(a: Pick<CellSave, 'row' | 'field'>, row: any, field: EditableFormulaField) {
  return a.row === row && a.field === field
}

/**
 * 合并同一轮格内提交，并在上一批完成后再发下一批。失败时只还原仍等于失败值的格；
 * 保存期间再次修改同一格时，下一批继承最近一次真正落库的基准。
 */
function scheduleSave(row: any, field: EditableFormulaField, before: string, value: string): Promise<boolean> {
  const context = currentContext
  if (!isCurrent(context) || !context.state.rows.includes(row)) return Promise.resolve(false)
  const state = context.state
  const result = new Promise<boolean>((resolve) => {
    const queued = state.pending.find((item) => sameCell(item, row, field))
    if (queued) {
      queued.value = value
      queued.waiters.push(resolve)
      return
    }
    const inflight = state.active.find((item) => sameCell(item, row, field))
    state.pending.push({ row, field, before: inflight?.before ?? before, value, waiters: [resolve] })
  })
  ensureCellSaveWorker(context)
  return result
}

function ensureCellSaveWorker(context: DialogContext) {
  const state = context.state
  if (state.worker || !isCurrent(context)) return
  // 延后一微任务：同一用户动作里相邻格的提交合成一次整体 PUT。
  state.worker = Promise.resolve().then(() => runCellSaveQueue(context)).finally(() => {
    state.worker = null
    if (state.pending.length) ensureCellSaveWorker(context)
  })
}

async function runCellSaveQueue(context: DialogContext) {
  const state = context.state
  while (state.pending.length && isCurrent(context)) {
    const batch = state.pending.splice(0)
    state.active = batch
    const saved = await persistFormulas({ skipNew: true }, context)
    const current = isCurrent(context)
    for (const edit of batch) {
      const queued = state.pending.find((item) => sameCell(item, edit.row, edit.field))
      if (current && saved) {
        if (queued) queued.before = edit.value
      } else if (current && !queued && String(edit.row[edit.field] ?? '') === edit.value) {
        edit.row[edit.field] = edit.before
      }
      edit.waiters.forEach((resolve) => resolve(current && saved))
    }
    state.active = []
    if (current && saved) ElMessage.success('已保存')
  }
}

async function flushScheduledSaves(context = currentContext): Promise<boolean> {
  if (!isCurrent(context)) return false
  while (true) {
    const tail = context.state.persistTail
    const worker = context.state.worker
    await untilInvalidated(context, Promise.all([worker, tail]).then(() => undefined), undefined)
    if (!isCurrent(context)) return false
    if (!context.state.worker && tail === context.state.persistTail) return true
  }
}

/** 既有行格内提交即排队保存；新增行先选完目标，再点行尾「保存」。 */
function onFormulaCellCommit(row: any, field: EditableFormulaField, value: string) {
  if (!isCurrent(currentContext) || !currentContext.state.rows.includes(row)) return Promise.resolve(false)
  const before = String(row[field] ?? '')
  const next = String(value ?? '')
  if (before === next) return Promise.resolve(true)
  row[field] = next
  if (row._isNew) return Promise.resolve(true)
  return scheduleSave(row, field, before, next)
}

// 新增行「保存」：先清空格内自动保存队列，再校验并持久化完整集合。
async function completeRow() {
  const context = currentContext
  if (!isCurrent(context) || !await flushScheduledSaves(context)) return
  const ok = await persistFormulas({}, context)
  if (ok && isCurrent(context)) ElMessage.success('已保存')
}

// 新增公式：推入空行（Req 15.3，去掉硬编码 SUM 占位）；目标在行内选（表 / 行 / 列）
function addFormula() {
  if (!isCurrent(currentContext)) return
  formulas.value.push({
    target: '',
    target_label: '',
    formula: '',
    category: activeCategory.value,
    description: '',
    source: '手工',
    type: '',
    _isNew: true,
  })
}

// ─── 应用自动运算（Req 15.4）：执行当前持久化/编辑集 ──────────────
// 先 PUT 持久化编辑集（保证跨重开不丢），再触发后端计算回填。
// 注：后端暂无"执行任意用户公式"端点，apply-formulas 按 check_presets 计算并
// 回填 auto 单元格；用户编辑集通过 PUT 持久化并在下次打开时重新加载（Req 15.2）。
async function onApply() {
  const context = currentContext
  if (!isCurrent(context)) {
    if (!disposed && !locallyClosed && props.modelValue) ElMessage.warning('请先选择附注章节')
    return
  }
  if (applying.value || regenerating.value) return
  applying.value = true
  try {
    if (!await flushScheduledSaves(context) || !isCurrent(context)) return
    const saved = await persistFormulas({}, context)
    if (!saved || !isCurrent(context)) return
    const result = await api.post(
      noteFormula.apply(context.projectId, context.year, context.noteSection), undefined, { _silent: true } as any,
    )
    if (!isCurrent(context)) return
    applyCheckResults(result, context)
    ElMessage.success(describeApplyResult(result))
    emit('applied')
  } catch (e: any) {
    if (isCurrent(context)) handleApiError(e, '应用失败')
  } finally {
    if (isCurrent(context)) applying.value = false
  }
}

// ─── 重新生成（Req 15.4）：按每张表当前结构重新生成预设公式并计算 ─────
// 独立于 onApply，不持久化用户编辑集；regenerate=true 让后端丢掉章节里存过的旧公式（按行号指格，增删行后会指错格）。
async function onRegenerate() {
  const context = currentContext
  if (!isCurrent(context)) {
    if (!disposed && !locallyClosed && props.modelValue) ElMessage.warning('请先选择附注章节')
    return
  }
  if (applying.value || regenerating.value) return
  regenerating.value = true
  try {
    const result = await api.post(
      noteFormula.apply(context.projectId, context.year, context.noteSection), null,
      { params: { regenerate: true }, _silent: true } as any,
    )
    if (!isCurrent(context)) return
    // 重新生成的 reload 也属于原代；等待期间切换，不再提示或通知宿主。
    if (!await loadFormulas(context) || !isCurrent(context)) return
    applyCheckResults(result, context)
    ElMessage.success(describeApplyResult(result, '已重新生成'))
    emit('applied')
  } catch (e: any) {
    if (isCurrent(context)) handleApiError(e, '重新生成失败')
  } finally {
    if (isCurrent(context)) regenerating.value = false
  }
}

// 先同步失效，再合并本轮 props 变更加载一次；覆盖同对象 note_section 原地变化。
watch(() => props.modelValue, () => { locallyClosed = false }, { flush: 'sync' })
watch(
  () => [props.modelValue, props.projectId, props.year, props.currentNote, props.currentNote?.note_section, props.templateType],
  invalidateContext,
  { flush: 'sync' },
)
watch(
  () => [props.modelValue, props.projectId, props.year, props.currentNote, props.currentNote?.note_section, props.templateType],
  () => {
    if (disposed || locallyClosed || !props.modelValue || !props.projectId || !props.year || !props.currentNote?.note_section) return
    let invalidate!: () => void
    const invalidated = new Promise<void>((resolve) => { invalidate = resolve })
    const context: DialogContext = Object.freeze({
      generation: contextGeneration, projectId: props.projectId, year: props.year,
      note: props.currentNote, noteSection: props.currentNote.note_section, modelValue: props.modelValue,
      templateType: props.templateType || 'soe', invalidated, invalidate,
      state: { rows: formulas.value, loaded: null, loadGeneration: 0, persistTail: Promise.resolve(),
        pending: [], active: [], worker: null },
    })
    currentContext = context
    void loadFormulas(context)
  },
  { immediate: true },
)
onBeforeUnmount(() => {
  disposed = true
  invalidateContext()
})
</script>

<style scoped>
.gt-nf-empty { text-align: center; padding: 40px; color: var(--gt-color-text-tertiary); }
.gt-nf-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.gt-nf-edit-hint { margin: -4px 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-nf-target { display: flex; gap: 4px; }
.gt-nf-target .el-select { flex: 1; min-width: 0; }
.gt-nf-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
