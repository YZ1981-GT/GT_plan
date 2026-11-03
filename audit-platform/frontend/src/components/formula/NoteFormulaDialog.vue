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
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import { api } from '@/services/apiProxy'
import { fetchTrialBalanceRows } from '@/services/trialBalanceRows'
// spec: formula-management-runtime-closure Task 14 — 端点收敛进 apiPaths（纯搬迁）
import { noteFormula } from '@/services/apiPaths/formula'
import { useAddressRegistry } from '@/stores/addressRegistry'
import { formatRefIssue } from '@/utils/formulaRefIssues'
import { showFormulaError } from '@/composables/formula/useFormulaSettings'
import FormulaRefPicker from './FormulaRefPicker.vue'
import GtGridCell from '@/components/grid/GtGridCell.vue'
import { ElInput } from '@/components/grid/adapters'
import {
  describeApplyResult, describeFormulaTarget, formulaKey, parseFormulaKey, type NoteFormulaTargetTable,
} from './noteFormulaTargets'

const props = defineProps<{
  modelValue: boolean
  currentNote: any
  projectId: string
  year: number
}>()

const emit = defineEmits<{
  'update:modelValue': [val: boolean]
  'applied': []
  /** 公式集已保存（宿主据此刷新自己展示的附注公式） */
  'saved': []
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const activeCategory = ref('auto_calc')
const applying = ref(false)
const regenerating = ref(false)
const persisting = ref(false)
const loading = ref(false)
const showRefPicker = ref(false)
const editingRow = ref<any>(null)

// ACNR-backed 公式引用校验（Req 15.5 → Req 9）。
// store.validate 优先走 ACNR resolveFormula（与后端 Req 9 同源），
// 未命中/非 WP 域/infra 失败时 fail-open 回退 legacy 权威校验。
const addrStore = useAddressRegistry()

// 引用选择器数据（懒加载）
const refPickerData = ref<{ reportRows: any[], tbRows: any[], noteRows: any[] }>({
  reportRows: [], tbRows: [], noteRows: [],
})

async function openRefPicker(row: any) {
  editingRow.value = row
  // 加载引用数据
  try {
    if (!refPickerData.value.reportRows.length) {
      const [reportData, tbData] = await Promise.all([
        api.get(`/api/reports/${props.projectId}/${props.year}/balance_sheet`).catch(() => []),
        // 经试算表唯一入口（原先请求后端没有的 `/api/trial-balance/` ⇒ 404 被吞，试算表候选恒空）
        fetchTrialBalanceRows(props.projectId, { year: props.year }).then((r) => r.rows).catch(() => []),
      ])
      refPickerData.value.reportRows = Array.isArray(reportData) ? reportData : (reportData || [])
      refPickerData.value.tbRows = Array.isArray(tbData) ? tbData : (tbData || [])
    }
  } catch { /* 静默 */ }
  showRefPicker.value = true
}

function onInsertRef(formula: string, _label: string) {
  const row = editingRow.value
  if (!row) return
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
function applyListing(resp: any) {
  const list = resp?.formulas
  formulas.value = (Array.isArray(list) ? list : []).map((f: any) => ({ ...f }))
  loadedTokens.value = resp?.loaded ?? {}
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
async function loadFormulas() {
  if (!props.currentNote || !props.projectId || !props.year) {
    formulas.value = []
    return
  }
  const noteSection = props.currentNote.note_section
  loading.value = true
  try {
    // GET 返回 { formulas: [...] }（http 拦截器已解包 {code,data} 信封）
    const resp = await api.get(
      noteFormula.list(props.projectId, props.year, noteSection)
    )
    applyListing(resp)
  } catch (e: any) {
    formulas.value = []
    loadedTokens.value = null
    handleApiError(e, '加载公式失败')
  } finally {
    loading.value = false
  }
  // 设置校验上下文（供 validate 的 legacy 回退按项目/年度解析非 WP 域引用）。
  // refresh 会同步写入 _projectId/_year，故无需 await 即可让后续 validate 生效。
  try { addrStore.refresh(props.projectId, props.year) } catch { /* 静默 */ }
}

// 弹窗打开 / 切换附注章节时加载（Req 15.1）
watch(() => props.modelValue, (val) => {
  if (val) loadFormulas()
})
watch(() => props.currentNote, () => {
  if (props.modelValue) loadFormulas()
})

// ─── 引用校验（Req 15.5 → Req 9，ACNR-backed，悬空引用不入库） ───
async function collectDanglingRefs(list: any[]): Promise<string[]> {
  const dangling: string[] = []
  for (const row of list) {
    const expr = (row?.formula || '').trim()
    if (!expr) continue
    try {
      const res = await addrStore.validate(expr)
      if (res && res.valid === false) {
        // 「引用：原因」—— 原先只列引用，看不出是章节不存在、写成了标题还是行列对不上
        for (const iss of (res.issues || [])) {
          dangling.push(formatRefIssue(iss) || expr)
        }
      }
    } catch {
      // infra 失败 fail-open：不因校验设施故障阻断保存（Req 9.3）
    }
  }
  return dangling
}

// ─── 持久化当前编辑集（Req 15.2/15.3） ────────────────────────
// 整体 PUT 用户编辑集（"这套就是最新集"语义）；空行由后端过滤。
// 保存前经 ACNR 校验，悬空引用提示且不入库（Req 15.5）。
type PersistOptions = { skipNew?: boolean }
let persistTail: Promise<void> = Promise.resolve()

/** 保存回执只就地刷新服务端元数据；不替换 formulas，避免把保存途中新增或继续编辑的行抹掉。 */
function applyPersistResult(resp: any) {
  if (!resp?.loaded) return
  loadedTokens.value = resp.loaded
  const fresh = new Map<string, any>((resp.formulas || []).map((f: any) => [f.target, f]))
  for (const formula of formulas.value) {
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

async function performPersist(options: PersistOptions): Promise<boolean> {
  if (!props.currentNote || !props.projectId || !props.year) {
    ElMessage.warning('请先选择附注章节')
    return false
  }
  // 先冻结本次快照。保存期间继续编辑的值留给下一批，不会被本次旧回执覆盖。
  const candidates = formulas.value
    .filter((formula) => !options.skipNew || !formula._isNew)
    .map((formula) => ({ ...formula }))
  // 自动保存只提交既有行：尚未选完目标的新行留在本地，不能阻塞另一格的提交。
  const untargeted = candidates.filter(f => (f?.formula || '').trim() && !String(f?.target || '').trim())
  if (untargeted.length) {
    ElMessage.warning(`有 ${untargeted.length} 条公式没有选择目标单元格（表 / 行 / 列），未保存`)
    return false
  }
  const dangling = await collectDanglingRefs(candidates)
  if (dangling.length) {
    ElMessage.error(`公式引用无法解析，未保存：${[...new Set(dangling)].join('；')}`)
    return false
  }
  const noteSection = props.currentNote.note_section
  // 剔除前端本地态字段（_isNew / _cell）与只读展示字段（层级 / 可读目标），只送持久化 shape。
  const payload = candidates
    .filter(f => (f?.formula || '').trim())
    .map(({ _isNew, _cell, layer, layer_label, pending, slot_key, target_label, ...rest }) => rest)
  persisting.value = true
  try {
    const resp = await api.put(
      noteFormula.list(props.projectId, props.year, noteSection),
      { formulas: payload, loaded: loadedTokens.value },
      { _silent: true } as any,
    )
    applyPersistResult(resp)
    emit('saved')
    return true
  } catch (e: any) {
    // 缺令牌 428 / 并发修改 409 / 无权 403 / 归档 423 / 悬空引用 422 均由统一公式错误处理写明原因。
    showFormulaError(e, '保存失败')
    return false
  } finally {
    persisting.value = false
  }
}

/** 全部 PUT 共用一条 Promise 链，确保版本令牌严格按响应顺序更新。 */
function persistFormulas(options: PersistOptions = {}): Promise<boolean> {
  const result = persistTail.then(() => performPersist(options), () => performPersist(options))
  persistTail = result.then(() => undefined, () => undefined)
  return result
}

type EditableFormulaField = 'formula' | 'description'
type CellSave = {
  row: any
  field: EditableFormulaField
  before: string
  value: string
  waiters: Array<(saved: boolean) => void>
}
const pendingCellSaves: CellSave[] = []
let activeCellSaves: CellSave[] = []
let cellSaveWorker: Promise<void> | null = null

function sameCell(a: Pick<CellSave, 'row' | 'field'>, row: any, field: EditableFormulaField) {
  return a.row === row && a.field === field
}

/**
 * 合并同一轮格内提交，并在上一批完成后再发下一批。失败时只还原仍等于失败值的格；
 * 保存期间再次修改同一格时，下一批继承最近一次真正落库的基准。
 */
function scheduleSave(row: any, field: EditableFormulaField, before: string, value: string): Promise<boolean> {
  const result = new Promise<boolean>((resolve) => {
    const queued = pendingCellSaves.find((item) => sameCell(item, row, field))
    if (queued) {
      queued.value = value
      queued.waiters.push(resolve)
      return
    }
    const inflight = activeCellSaves.find((item) => sameCell(item, row, field))
    pendingCellSaves.push({ row, field, before: inflight?.before ?? before, value, waiters: [resolve] })
  })
  ensureCellSaveWorker()
  return result
}

function ensureCellSaveWorker() {
  if (cellSaveWorker) return
  // 延后一微任务：同一用户动作里相邻格的提交合成一次整体 PUT。
  cellSaveWorker = Promise.resolve().then(runCellSaveQueue).finally(() => {
    cellSaveWorker = null
    // 前一轮最后一个 waiter 已唤醒、finally 尚未执行时可能又入队；不能让这一格永久挂起。
    if (pendingCellSaves.length) ensureCellSaveWorker()
  })
}

async function runCellSaveQueue() {
  while (pendingCellSaves.length) {
    const batch = pendingCellSaves.splice(0)
    activeCellSaves = batch
    const saved = await persistFormulas({ skipNew: true })
    for (const edit of batch) {
      const queued = pendingCellSaves.find((item) => sameCell(item, edit.row, edit.field))
      if (saved) {
        // 下一批失败时回到本批已落库的值，而不是更早的旧值。
        if (queued) queued.before = edit.value
      } else if (!queued && String(edit.row[edit.field] ?? '') === edit.value) {
        edit.row[edit.field] = edit.before
      }
      edit.waiters.forEach((resolve) => resolve(saved))
    }
    activeCellSaves = []
    if (saved) ElMessage.success('已保存')
  }
}

async function flushScheduledSaves() {
  while (cellSaveWorker) await cellSaveWorker
}

/** 既有行格内提交即排队保存；新增行先选完目标，再点行尾「保存」。 */
function onFormulaCellCommit(row: any, field: EditableFormulaField, value: string) {
  const before = String(row[field] ?? '')
  const next = String(value ?? '')
  if (before === next) return Promise.resolve(true)
  row[field] = next
  if (row._isNew) return Promise.resolve(true)
  return scheduleSave(row, field, before, next)
}

// 新增行「保存」：先清空格内自动保存队列，再校验并持久化完整集合。
async function completeRow() {
  await flushScheduledSaves()
  const ok = await persistFormulas()
  if (ok) ElMessage.success('已保存')
}

// 新增公式：推入空行（Req 15.3，去掉硬编码 SUM 占位）；目标在行内选（表 / 行 / 列）
function addFormula() {
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
  if (!props.projectId || !props.year || !props.currentNote) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  applying.value = true
  try {
    await flushScheduledSaves()
    const saved = await persistFormulas()
    if (!saved) return
    const noteSection = props.currentNote.note_section
    const result = await api.post(
      noteFormula.apply(props.projectId, props.year, noteSection)
    )
    ElMessage.success(describeApplyResult(result))
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '应用失败')
  } finally {
    applying.value = false
  }
}

// ─── 重新生成（Req 15.4）：按每张表当前结构重新生成预设公式并计算 ─────
// 独立于 onApply，不持久化用户编辑集；regenerate=true 让后端丢掉章节里存过的旧公式（按行号指格，增删行后会指错格）。
async function onRegenerate() {
  if (!props.projectId || !props.year || !props.currentNote) {
    ElMessage.warning('请先选择附注章节')
    return
  }
  regenerating.value = true
  try {
    const noteSection = props.currentNote.note_section
    const result = await api.post(
      noteFormula.apply(props.projectId, props.year, noteSection), null, { params: { regenerate: true } },
    )
    ElMessage.success(describeApplyResult(result, '已重新生成'))
    // 重新生成后刷新列表，展示最新预设公式
    await loadFormulas()
    emit('applied')
  } catch (e: any) {
    handleApiError(e, '重新生成失败')
  } finally {
    regenerating.value = false
  }
}
</script>

<style scoped>
.gt-nf-empty { text-align: center; padding: 40px; color: var(--gt-color-text-tertiary); }
.gt-nf-header { display: flex; align-items: center; gap: 8px; font-weight: 600; }
.gt-nf-edit-hint { margin: -4px 0 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-nf-target { display: flex; gap: 4px; }
.gt-nf-target .el-select { flex: 1; min-width: 0; }
.gt-nf-hint { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
