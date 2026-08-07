<script setup lang="ts">
/**
 * 公式管理面板（侧面板"公式"Tab）
 *
 * spec: d-cycle-four-table-extraction-formulas Task 4.1 / 4.2
 *   (Requirements 5.1–5.7 / Property 5, 6, 7, 11)
 *
 * - Task 4.1：修正端点错配 —— 改真实端点 `GET /api/workpapers/{wp_id}/formulas`
 *   解析 `items`（此前调不存在的 projects 作用域端点、读 `data.formulas` 恒空）；
 *   按 sheet 分组；三层展示（持久化公式 items / Tier A 可编辑提取公式 /
 *   Tier B 四表库自动预填只读溯源）；值复用 render 的 seed（不逐条重求值 / R5.6）。
 * - Task 4.2：Tier A 编辑（PUT 覆盖预设）/ 恢复默认（DELETE 用户覆盖回落预设）/
 *   禁用（PUT category='__disabled__'）；权限门控（`usePermissionMatrix`，
 *   仅编辑角色可变更，只读用户仅可查看 / R5.7）；422（FORMULA_UNSUPPORTED_FUNCTION /
 *   FORMULA_REF_NOT_FOUND）清晰提示（R5.3）。
 *
 * `extraction` 缺失（灰度关 / 非 D 循环）时 → 仅展示 items，优雅无报错（R7.1）。
 *
 * spec: formula-management-runtime-closure Task 2（Requirements 2.1–2.6）
 *   后端 `_formula_to_dict` 下发 17 键，而本面板改造前只声明 7 键，把
 *   `issue_description` / `hint_text` / `last_computed_at` / `refs` 全部丢弃，
 *   且 `formula_type` 以裸英文值渲染（违反 UI 全中文化）。本轮补齐四字段展示，
 *   中文标签**复用**单一真源 `formulaEngineInventory.FORMULA_TYPE_LABEL`
 *   （禁本文件内自建 `Record<FormulaType, string>` 字面量 —— 会形成第二份标签表）。
 */
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
// spec: formula-management-runtime-closure Task 14 — 公式端点收敛进 apiPaths（纯搬迁，URL 逐字不变）
import { wpFormula } from '@/services/apiPaths/formula'
import { usePermissionMatrix } from '@/composables/usePermissionMatrix'
import {
  FORMULA_TYPE_LABEL,
  formulaLifecycleLabel,
  type FormulaType,
} from './composables/formulaEngineInventory'

/** 用户已落库的原始公式（wp_formula 行，键集与后端 `_formula_to_dict` 对齐） */
interface RawFormulaItem {
  id: string
  sheet_name: string
  target_cell: string
  expression: string
  category?: string | null
  description?: string | null
  formula_type: string
  /** 逻辑判断说明（logic_check 类公式的判断结论） */
  issue_description?: string | null
  /** 合理性提示（reasonability 类公式的提示文字） */
  hint_text?: string | null
  /** 最近一次求值时间（ISO 字符串；未计算为 null） */
  last_computed_at?: string | null
  /** 该公式引用的地址列表 */
  refs?: unknown[] | null
  /**
   * 定义生命周期（`draft` / `active` / `archived`）。
   *
   * spec: formula-management-runtime-closure Task 11（Property 16）——
   * 该列此前不在后端 `_formula_to_dict` 下发键集内，故全前端命中 0。
   */
  lifecycle_state?: string | null
  /** 定义版本号（每次 upsert 递增，供排查「用户改过几次」） */
  definition_version?: number | null
}

/** Tier A 提取公式绑定（预设 ∪ 用户，读时收敛） */
interface TierABinding {
  wp_code: string
  sheet_name: string
  anchor: string
  expression: string
  formula_type: string
  description: string
  source: 'preset' | 'custom' | 'disabled'
  tier: 'A'
  value?: number | string | null
  /** P1-4：取数语义标注（trial_balance 审定核对标量，与 Tier B 未审口径消歧） */
  semantic?: string
}

/** Tier B 四表库自动预填只读溯源 */
interface TierBProvenance {
  wp_code: string
  sheet_name: string
  anchor: string
  description: string
  source: 'prefill'
  editable: false
  tier: 'B'
  value?: number | string | null
  /** P1-4：四表库未审/明细来源标注（tb_balance/tb_aux_balance/序时账，非审定数） */
  semantic?: string
}

interface ExtractionBlock {
  wp_code: string
  enabled: boolean
  note: string
  tierA: TierABinding[]
  tierB: TierBProvenance[]
}

interface FormulasResponse {
  wp_id: string
  count: number
  items: RawFormulaItem[]
  extraction?: ExtractionBlock
}

const props = defineProps<{
  projectId: string
  wpId: string
  /** 保存/求值悬空校验所需年度；缺省回退当前年度 */
  year?: number
}>()

const { canDo } = usePermissionMatrix(props.projectId)
/** 仅编辑角色可变更 Tier A（只读用户仅查看 / R5.7）。 */
const canEdit = computed(() => canDo('edit', 'workpaper'))

const effYear = computed(() => props.year ?? new Date().getFullYear())

const loading = ref(false)
const rawItems = ref<RawFormulaItem[]>([])
const tierA = ref<TierABinding[]>([])
const tierB = ref<TierBProvenance[]>([])
const extractionNote = ref<string>('')

const sourceLabel: Record<string, string> = {
  preset: '预设',
  custom: '自定义',
  disabled: '已禁用',
}
const sourceTagType: Record<string, string> = {
  preset: 'info',
  custom: 'primary',
  disabled: 'danger',
}

/** 按 sheet 分组：union of items / tierA / tierB 的 sheet_name。 */
interface SheetGroup {
  sheet: string
  items: RawFormulaItem[]
  tierA: TierABinding[]
  tierB: TierBProvenance[]
}

const groupedBySheet = computed<SheetGroup[]>(() => {
  const sheets = new Set<string>()
  for (const it of rawItems.value) sheets.add(it.sheet_name || '')
  for (const b of tierA.value) sheets.add(b.sheet_name || '')
  for (const b of tierB.value) sheets.add(b.sheet_name || '')
  return Array.from(sheets)
    .sort((a, b) => a.localeCompare(b))
    .map((sheet) => ({
      sheet,
      items: rawItems.value.filter((it) => (it.sheet_name || '') === sheet),
      tierA: tierA.value.filter((b) => (b.sheet_name || '') === sheet),
      tierB: tierB.value.filter((b) => (b.sheet_name || '') === sheet),
    }))
    .filter((g) => g.items.length || g.tierA.length || g.tierB.length)
})

const hasAnything = computed(
  () => rawItems.value.length > 0 || tierA.value.length > 0 || tierB.value.length > 0,
)

function displayValue(v: number | string | null | undefined): string {
  if (v === null || v === undefined || v === '') return '—'
  return typeof v === 'number' ? v.toLocaleString() : String(v)
}

/**
 * 三类型中文标签（Requirements 2.2 / 2.5）。
 *
 * 真源 = `formulaEngineInventory.FORMULA_TYPE_LABEL`；未登记的取值原样透出
 * （宁可显示原值也不编造标签，便于发现后端新增了未登记的 formula_type）。
 */
function formulaTypeLabel(t: string | null | undefined): string {
  if (!t) return '未分类'
  return FORMULA_TYPE_LABEL[t as FormulaType] ?? t
}

const FORMULA_TYPE_TAG_TYPE: Record<string, string> = {
  auto_calc: 'primary',
  logic_check: 'warning',
  reasonability: 'success',
}

function formulaTypeTagType(t: string | null | undefined): string {
  return (t && FORMULA_TYPE_TAG_TYPE[t]) || 'info'
}

/**
 * 生命周期是否为**非生效**态（Task 11 / Property 16）。
 *
 * `active` 是常态；`null`/`undefined`（历史行或后端未下发）也不算异常
 * —— 否则每条公式都挂一个标签，等于噪音。
 */
function isAbnormalLifecycle(state: string | null | undefined): boolean {
  return !!state && state !== 'active'
}

/** 计算时间（Requirements 2.3）：为空显示「未计算」，有值显示本地化时间。 */
function computedAtText(iso: string | null | undefined): string {
  if (!iso) return '未计算'
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return String(iso)
  return d.toLocaleString('zh-CN', { hour12: false })
}

/** 引用数量（Requirements 2.4）：非数组或空数组返回 0。 */
function refsCount(refs: unknown[] | null | undefined): number {
  return Array.isArray(refs) ? refs.length : 0
}

function refText(r: unknown): string {
  if (r === null || r === undefined) return '—'
  if (typeof r === 'string' || typeof r === 'number') return String(r)
  try {
    return JSON.stringify(r)
  } catch {
    return String(r)
  }
}

/** 展开引用列表的公式 id 集合（Requirements 2.4）。 */
const expandedRefs = ref<Set<string>>(new Set())

function toggleRefs(id: string) {
  const next = new Set(expandedRefs.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  expandedRefs.value = next
}

async function loadFormulas() {
  if (!props.wpId) return
  loading.value = true
  try {
    // 真实端点（Task 4.1）：GET /api/workpapers/{wp_id}/formulas → { items, extraction? }
    const data = await api.get<FormulasResponse>(wpFormula.list(props.wpId))
    rawItems.value = Array.isArray(data?.items) ? data.items : []
    const ex = data?.extraction
    if (ex) {
      tierA.value = Array.isArray(ex.tierA) ? ex.tierA : []
      tierB.value = Array.isArray(ex.tierB) ? ex.tierB : []
      extractionNote.value = ex.note || ''
    } else {
      // extraction 缺失（灰度关 / 非 D 循环）→ 仅展示 items（R7.1 优雅无报错）
      tierA.value = []
      tierB.value = []
      extractionNote.value = ''
    }
  } catch {
    rawItems.value = []
    tierA.value = []
    tierB.value = []
    extractionNote.value = ''
  } finally {
    loading.value = false
  }
}

/** 从已落库 items 中按锚点(+sheet)找到对应 wp_formula id（用于 DELETE 恢复默认）。 */
function resolveFormulaId(binding: TierABinding): string | null {
  const exact = rawItems.value.find(
    (it) => it.target_cell === binding.anchor && it.sheet_name === binding.sheet_name,
  )
  if (exact) return exact.id
  const byAnchor = rawItems.value.find((it) => it.target_cell === binding.anchor)
  return byAnchor ? byAnchor.id : null
}

/** 统一处理 PUT 的 422 错误码（R5.3）。 */
function handleSaveError(err: any): void {
  const detail = err?.response?.data?.detail
  const code = detail?.error_code
  if (code === 'FORMULA_UNSUPPORTED_FUNCTION') {
    const fns = (detail.unsupported_functions || []).join(' / ')
    ElMessage.error(
      detail.message || `公式含不受支持的函数：${fns}；可编辑公式仅支持 TB/SUM_TB/WP。`,
    )
  } else if (code === 'FORMULA_REF_NOT_FOUND') {
    const issues = (detail.issues || []).join('；')
    ElMessage.error(`公式引用不存在：${issues || '存在悬空引用'}`)
  } else {
    ElMessage.error('保存失败，请检查公式表达式')
  }
}

async function putFormula(binding: {
  sheet_name: string
  anchor: string
  expression: string
  description?: string
  category?: string
}): Promise<boolean> {
  try {
    await api.put(
      wpFormula.upsert(props.wpId),
      {
        sheet_name: binding.sheet_name,
        target_cell: binding.anchor,
        expression: binding.expression,
        year: effYear.value,
        formula_type: 'auto_calc',
        category: binding.category ?? null,
        description: binding.description ?? null,
      },
      { _silent: true } as any,
    )
    return true
  } catch (err) {
    handleSaveError(err)
    return false
  }
}

// ─── 编辑弹窗 ────────────────────────────────────────────
const editVisible = ref(false)
const editSaving = ref(false)
const editForm = ref<{ sheet_name: string; anchor: string; expression: string; description: string }>({
  sheet_name: '',
  anchor: '',
  expression: '',
  description: '',
})

function openEdit(binding: TierABinding) {
  if (!canEdit.value) return
  editForm.value = {
    sheet_name: binding.sheet_name,
    anchor: binding.anchor,
    // 禁用状态下编辑视为重新启用：预填原表达式（禁用时可能为空）
    expression: binding.source === 'disabled' ? binding.expression : binding.expression,
    description: binding.description || '',
  }
  editVisible.value = true
}

async function confirmEdit() {
  if (!editForm.value.expression.trim()) {
    ElMessage.warning('请输入公式表达式')
    return
  }
  editSaving.value = true
  try {
    const ok = await putFormula({
      sheet_name: editForm.value.sheet_name,
      anchor: editForm.value.anchor,
      expression: editForm.value.expression.trim(),
      description: editForm.value.description,
      // 编辑=覆盖为自定义（清除禁用标记）
      category: null,
    })
    if (ok) {
      ElMessage.success('已保存')
      editVisible.value = false
      await loadFormulas()
    }
  } finally {
    editSaving.value = false
  }
}

/** 恢复默认（DELETE 用户覆盖 → 回落预设 / R5.4）。 */
async function restoreDefault(binding: TierABinding) {
  if (!canEdit.value) return
  const fid = resolveFormulaId(binding)
  if (!fid) {
    ElMessage.error('未找到对应的用户公式记录')
    return
  }
  try {
    await api.delete(wpFormula.remove(props.wpId, fid))
    ElMessage.success('已恢复默认')
    await loadFormulas()
  } catch {
    ElMessage.error('恢复默认失败')
  }
}

/** 禁用某提取（PUT category='__disabled__' 使该锚点不再自动填充 / R5.5）。 */
async function disableBinding(binding: TierABinding) {
  if (!canEdit.value) return
  const ok = await putFormula({
    sheet_name: binding.sheet_name,
    anchor: binding.anchor,
    // 保留原表达式（后端按 category==='__disabled__' 判定禁用，不改值逻辑）
    expression: binding.expression || "TB('','')",
    description: binding.description,
    category: '__disabled__',
  })
  if (ok) {
    ElMessage.success('已禁用该自动提取')
    await loadFormulas()
  }
}

onMounted(loadFormulas)

defineExpose({ loadFormulas })
</script>

<template>
  <div class="formula-status-panel" v-loading="loading">
    <!-- 汇总 -->
    <div class="formula-summary">
      <span class="summary-badge">持久化 {{ rawItems.length }}</span>
      <span class="summary-badge tier-a">Tier A {{ tierA.length }}</span>
      <span class="summary-badge tier-b">Tier B {{ tierB.length }}</span>
    </div>
    <div v-if="extractionNote" class="formula-note">{{ extractionNote }}</div>

    <div class="formula-list">
      <div v-for="grp in groupedBySheet" :key="grp.sheet" class="sheet-group">
        <div class="sheet-title">{{ grp.sheet || '(未命名 sheet)' }}</div>

        <!-- 持久化公式（items，向后兼容） -->
        <div v-if="grp.items.length" class="tier-section">
          <div class="tier-section-title">持久化公式</div>
          <div v-for="it in grp.items" :key="it.id" class="formula-item">
            <div class="formula-header">
              <span class="formula-cell">{{ it.target_cell }}</span>
              <!-- Requirements 2.2：中文类型标签，真源 FORMULA_TYPE_LABEL -->
              <el-tag size="small" :type="(formulaTypeTagType(it.formula_type) as any)">
                {{ formulaTypeLabel(it.formula_type) }}
              </el-tag>
              <!--
                Task 11 / Property 16：生命周期标签。
                `active`（生效）是常态，不渲染以免噪音；只在 `draft` / `archived`
                这类**非生效**态显示警示，让「这条公式当前不参与求值」可见。
              -->
              <el-tag
                v-if="isAbnormalLifecycle(it.lifecycle_state)"
                size="small"
                type="warning"
                effect="plain"
                :title="`定义版本 v${it.definition_version ?? '?'}`"
              >
                {{ formulaLifecycleLabel(it.lifecycle_state) }}
              </el-tag>
              <!-- Requirements 2.3：计算时间，为空显示「未计算」 -->
              <span class="formula-computed-at" :title="it.last_computed_at || '尚未求值'">
                {{ computedAtText(it.last_computed_at) }}
              </span>
            </div>
            <div class="formula-detail">{{ it.expression }}</div>
            <div v-if="it.description" class="formula-desc">{{ it.description }}</div>
            <!-- Requirements 2.1：逻辑判断说明（issue_description），有值才渲染 -->
            <div v-if="it.issue_description" class="formula-issue">
              <el-tag size="small" type="danger" effect="plain">逻辑判断</el-tag>
              <span class="formula-issue-text">{{ it.issue_description }}</span>
            </div>
            <!-- Requirements 2.1：合理性提示（hint_text），有值才渲染 -->
            <div v-if="it.hint_text" class="formula-hint">💡 {{ it.hint_text }}</div>
            <!-- Requirements 2.4：引用数量 + 可展开引用列表 -->
            <div v-if="refsCount(it.refs)" class="formula-refs">
              <el-button link type="primary" size="small" @click="toggleRefs(it.id)">
                引用 {{ refsCount(it.refs) }} 项
                <span class="refs-caret">{{ expandedRefs.has(it.id) ? '▴' : '▾' }}</span>
              </el-button>
              <ul v-if="expandedRefs.has(it.id)" class="refs-list">
                <li v-for="(r, ri) in (it.refs || [])" :key="ri">{{ refText(r) }}</li>
              </ul>
            </div>
          </div>
        </div>

        <!-- Tier A 可编辑提取公式 -->
        <div v-if="grp.tierA.length" class="tier-section">
          <div class="tier-section-title">Tier A 提取公式（可编辑）</div>
          <div
            v-for="b in grp.tierA"
            :key="`A-${b.anchor}`"
            class="formula-item"
            :class="{ 'is-disabled': b.source === 'disabled' }"
          >
            <div class="formula-header">
              <span class="formula-cell">{{ b.anchor }}</span>
              <el-tag size="small" :type="(sourceTagType[b.source] as any)">{{ sourceLabel[b.source] }}</el-tag>
            </div>
            <div class="formula-detail">{{ b.expression || '（已禁用，不自动填充）' }}</div>
            <div v-if="b.semantic" class="formula-semantic">🔖 {{ b.semantic }}</div>
            <div v-if="b.description" class="formula-desc">{{ b.description }}</div>
            <div class="formula-value">当前值：{{ displayValue(b.value) }}</div>
            <div v-if="canEdit" class="formula-actions">
              <el-button link type="primary" size="small" @click="openEdit(b)">编辑</el-button>
              <el-button
                v-if="b.source === 'custom' || b.source === 'disabled'"
                link
                type="warning"
                size="small"
                @click="restoreDefault(b)"
              >恢复默认</el-button>
              <el-button
                v-if="b.source !== 'disabled'"
                link
                type="danger"
                size="small"
                @click="disableBinding(b)"
              >禁用</el-button>
            </div>
          </div>
        </div>

        <!-- Tier B 只读溯源 -->
        <div v-if="grp.tierB.length" class="tier-section">
          <div class="tier-section-title">Tier B 自动预填来源（只读）</div>
          <div v-for="b in grp.tierB" :key="`B-${b.anchor}`" class="formula-item is-readonly">
            <div class="formula-header">
              <span class="formula-cell">{{ b.anchor }}</span>
              <el-tag size="small" type="success">自动预填来源</el-tag>
            </div>
            <div v-if="b.semantic" class="formula-semantic">🔖 {{ b.semantic }}</div>
            <div class="formula-desc">{{ b.description }}</div>
          </div>
        </div>
      </div>

      <el-empty v-if="!loading && !hasAnything" description="暂无公式" />
    </div>

    <!-- Tier A 编辑弹窗 -->
    <el-dialog v-model="editVisible" title="编辑提取公式" width="480px" append-to-body>
      <el-form label-width="72px" label-position="right">
        <el-form-item label="Sheet">
          <span class="edit-readonly">{{ editForm.sheet_name }}</span>
        </el-form-item>
        <el-form-item label="锚点">
          <span class="edit-readonly">{{ editForm.anchor }}</span>
        </el-form-item>
        <el-form-item label="公式">
          <el-input
            v-model="editForm.expression"
            type="textarea"
            :rows="2"
            placeholder="如 TB('1402','期末余额')；仅支持 TB/SUM_TB/WP"
          />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="editForm.description" placeholder="可选" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="editVisible = false">取消</el-button>
        <el-button type="primary" :loading="editSaving" @click="confirmEdit">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.formula-status-panel {
  padding: 8px;
  font-size: 13px;
}

.formula-summary {
  display: flex;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 8px;
}

.summary-badge {
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--el-fill-color-light);
}
.summary-badge.tier-a { color: var(--el-color-primary); }
.summary-badge.tier-b { color: var(--el-color-success); }

.formula-note {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-bottom: 8px;
}

.formula-list {
  max-height: calc(100vh - 300px);
  overflow-y: auto;
}

.sheet-group {
  margin-bottom: 12px;
}

.sheet-title {
  font-weight: 600;
  font-size: 13px;
  color: var(--el-text-color-primary);
  padding: 4px 0;
  border-bottom: 1px dashed var(--el-border-color);
  margin-bottom: 6px;
}

.tier-section {
  margin-bottom: 8px;
}

.tier-section-title {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin: 4px 0;
}

.formula-item {
  padding: 6px 8px;
  border-radius: 4px;
  margin-bottom: 4px;
  border-left: 3px solid var(--el-border-color);
  background: var(--el-fill-color-lighter);
}
.formula-item.is-disabled { opacity: 0.65; border-left-color: var(--el-color-danger); }
.formula-item.is-readonly { border-left-color: var(--el-color-success); }

.formula-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.formula-cell {
  font-weight: 500;
  font-size: 13px;
  font-family: 'Consolas', monospace;
}

.formula-detail {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Consolas', monospace;
  word-break: break-all;
}

.formula-desc {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}

.formula-value {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-color-primary);
  font-variant-numeric: tabular-nums;
}

.formula-semantic {
  margin-top: 2px;
  font-size: 12px;
  color: var(--el-color-warning);
  line-height: 1.4;
}

/* R2.3：计算时间（右对齐在 header 末尾） */
.formula-computed-at {
  margin-left: auto;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
  white-space: nowrap;
}

.formula-issue {
  margin-top: 4px;
  display: flex;
  align-items: flex-start;
  gap: 4px;
}

.formula-issue-text {
  font-size: 12px;
  color: var(--el-color-danger);
  line-height: 1.4;
}

.formula-hint {
  margin-top: 4px;
  padding: 4px 6px;
  border-left: 2px solid var(--el-color-warning);
  background: var(--el-color-warning-light-9);
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.4;
}

.formula-refs {
  margin-top: 2px;
}

.refs-caret {
  margin-left: 2px;
}

.refs-list {
  margin: 2px 0 0;
  padding-left: 18px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  font-family: 'Consolas', monospace;
  word-break: break-all;
}

.formula-actions {
  margin-top: 4px;
  display: flex;
  gap: 4px;
}

.edit-readonly {
  font-family: 'Consolas', monospace;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
</style>
