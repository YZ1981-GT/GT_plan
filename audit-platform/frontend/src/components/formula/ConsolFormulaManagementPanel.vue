<!--
  公式管理中心的合并专用面板（任务 13.1~13.3 / 需求 7）。
  - 合并报表：精确读取 `{soe|listed}_consolidated` 六类 report_config，不与单体 project/standalone 缓存串用；
  - 合并附注：读写 consol_note_formula，按章节维护自动种子/人工公式；
  - 每次模板级变更先明确确认，写成功后仅对当前项目发 formula_changed 合并推送；
  - 「合并推送」页使用独立运行面板，不复用 E1 公式推送引擎。
-->
<template>
  <div class="gt-cfmp" data-testid="consol-formula-panel">
    <el-alert type="warning" :closable="false" show-icon class="gt-cfmp-alert"
      title="这里维护的是模板级合并公式：修改会影响所有使用同一模板的合并项目；保存后将立即为当前项目启动合并推送。" />
    <el-alert v-if="mode === 'note' && !canManage" type="info" :closable="false" show-icon class="gt-cfmp-alert"
      title="当前角色可查看合并附注公式；只有管理员、合伙人和经理可以新增、修改、删除或重新种子化。" />

    <el-tabs v-model="panelTab" data-testid="consol-formula-tabs">
      <el-tab-pane name="formulas" :label="mode === 'report' ? '合并报表公式' : '合并附注公式'">
        <template v-if="mode === 'report'">
          <div class="gt-cfmp-toolbar">
            <span><b>{{ reportTypeLabel(reportType) }}</b> · {{ consolidatedStandard }} · {{ reportRows.length }} 行 · {{ EDIT_HINT }}</span>
            <el-button size="small" :loading="loading" data-testid="consol-report-formula-refresh" @click="load">🔄 刷新</el-button>
          </div>
          <!-- 公式 / 分类 / 说明格内编辑（spec excel-style-table-editing 5.5，替换「编辑 → 行内输入框 → 保存 / 取消」）：
               平时显示文字，双击 / F2 / 直接输入才挂编辑器；提交后攒成一批，确认一次模板级影响再逐行保存、推送一次 -->
          <el-table v-loading="loading" :data="reportRows" border size="small" max-height="calc(100vh - 300px)"
            empty-text="当前模板没有该报表行" data-testid="consol-report-formulas">
            <el-table-column prop="row_code" label="行次" width="90" />
            <el-table-column prop="row_name" label="项目" min-width="190" show-overflow-tooltip />
            <el-table-column label="公式" min-width="330">
              <template #default="{ row }">
                <GtGridCell :editable="!!row.id" :value="cellValue(row, 'formula')">
                  <template #display><code>{{ cellValue(row, 'formula') || '—' }}</code></template>
                  <ElInput :model-value="String(cellValue(row, 'formula') ?? '')" size="small"
                    placeholder="如 TB('1001','期末余额') 或 ROW('BS-001')" @change="(v: unknown) => onCellEdit(row, 'formula', v)" />
                </GtGridCell>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="130">
              <template #default="{ row }">
                <GtGridCell :editable="!!row.id" :value="cellValue(row, 'formula_category')" kind="select">
                  <template #display>{{ categoryLabel(cellValue(row, 'formula_category') as string | null) }}</template>
                  <ElSelect :model-value="cellValue(row, 'formula_category') || 'auto_calc'" size="small"
                    @change="(v: unknown) => onCellEdit(row, 'formula_category', v)">
                    <el-option label="自动运算" value="auto_calc" />
                    <el-option label="逻辑审核" value="logic_check" />
                    <el-option label="合理性" value="reasonability" />
                  </ElSelect>
                </GtGridCell>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">
                <GtGridCell :editable="!!row.id" :value="cellValue(row, 'formula_description')">
                  <template #display>{{ cellValue(row, 'formula_description') || '' }}</template>
                  <ElInput :model-value="String(cellValue(row, 'formula_description') ?? '')" size="small"
                    @change="(v: unknown) => onCellEdit(row, 'formula_description', v)" />
                </GtGridCell>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-else>
          <el-alert type="info" :closable="false" show-icon class="gt-cfmp-source-note">
            <template #title>
              合并附注有两条取数路径：<b>🧮 公式计算</b>（本页维护，按试算表口径算含调整/抵销的合并数，附注页「按公式填入」触发；
              「🔄 重新汇总」用它算各差额节点）· <b>📋 明细映射 / 🔄 重新汇总</b>（各子企业按确认过的对应规则从单体附注拉个别数，
              差额节点按抵销分录算差额，再自下而上汇总到所选节点）。两者写入同一章节，以最后执行的为准；
              推送后与试算表变动后的自动刷新不覆盖从单体附注拉来的数，公式值有变化只标「待更新」。
            </template>
          </el-alert>
          <div class="gt-cfmp-toolbar">
            <div class="gt-cfmp-note-select">
              <span>章节</span>
              <el-select v-model="selectedSectionId" filterable size="small" style="width:320px"
                placeholder="选择附注章节" data-testid="consol-note-formula-section" @change="discardPendingEdits">
                <el-option v-for="section in noteSectionOptions" :key="section.section_id"
                  :label="`${section.section_id} ${section.title || ''}`" :value="section.section_id" />
              </el-select>
              <span>{{ noteRows.length }} 条公式<template v-if="canManage"> · {{ EDIT_HINT }}</template></span>
            </div>
            <div class="gt-cfmp-actions">
              <el-button size="small" :loading="loading" @click="load">🔄 刷新</el-button>
              <el-button v-if="canManage" size="small" :loading="saving" data-testid="consol-note-formula-reseed"
                @click="reseed">🌱 重新种子化</el-button>
              <el-button v-if="canManage" size="small" type="primary" data-testid="consol-note-formula-add"
                :disabled="!selectedSectionId" @click="openCreate">+ 新增公式</el-button>
            </div>
          </div>
          <el-table v-loading="loading" :data="noteRows" border size="small" max-height="calc(100vh - 300px)"
            empty-text="该章节暂无合并附注公式" data-testid="consol-note-formulas">
            <el-table-column prop="position" label="单元格" min-width="220" show-overflow-tooltip />
            <el-table-column label="公式" min-width="330">
              <template #default="{ row }">
                <GtGridCell :editable="canManage" :value="cellValue(row, 'formula')">
                  <template #display><code>{{ cellValue(row, 'formula') }}</code></template>
                  <ElInput :model-value="String(cellValue(row, 'formula') ?? '')" size="small"
                    @change="(v: unknown) => onCellEdit(row, 'formula', v)" />
                </GtGridCell>
              </template>
            </el-table-column>
            <el-table-column prop="source_label" label="来源" width="100" />
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">
                <GtGridCell :editable="canManage" :value="cellValue(row, 'description')">
                  <template #display>{{ cellValue(row, 'description') || '' }}</template>
                  <ElInput :model-value="String(cellValue(row, 'description') ?? '')" size="small"
                    @change="(v: unknown) => onCellEdit(row, 'description', v)" />
                </GtGridCell>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" min-width="165">
              <template #default="{ row }">{{ formatTime(row.updated_at) || '—' }}</template>
            </el-table-column>
            <el-table-column v-if="canManage" label="操作" width="80" fixed="right">
              <template #default="{ row }">
                <el-button link type="danger" size="small" @click="removeNoteRow(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-tab-pane>
      <el-tab-pane name="push" label="📤 合并推送">
        <ConsolPushPanel v-if="panelTab === 'push'" ref="pushPanelRef" :project-id="projectId" :year="year" />
      </el-tab-pane>
    </el-tabs>

    <el-dialog v-model="showCreateDialog" title="新增合并附注公式" width="560px" append-to-body destroy-on-close>
      <el-form ref="createFormRef" :model="createForm" :rules="createRules" label-width="100px">
        <el-form-item label="章节">
          <span>{{ selectedSectionId }} {{ selectedSectionTitle }}</span>
        </el-form-item>
        <el-form-item label="行号" prop="rowNumber">
          <el-input-number v-model="createForm.rowNumber" :min="1" :max="10001" controls-position="right" />
          <span class="gt-cfmp-form-hint">模板表格中的行号，从 1 开始</span>
        </el-form-item>
        <el-form-item label="数值列序号" prop="colIndex">
          <el-input-number v-model="createForm.colIndex" :min="1" :max="100" controls-position="right" />
          <span class="gt-cfmp-form-hint">1 = 项目名右侧第一个数值列</span>
        </el-form-item>
        <el-form-item label="公式" prop="formula">
          <el-input v-model="createForm.formula" type="textarea" :rows="3"
            placeholder="如 TB('1001','期末余额') 或 REPORT('BS-002')" />
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="createForm.description" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" data-testid="consol-note-formula-create" @click="createNoteRow">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'
import { consolNoteSections as P_cn, reportConfig as P_rc } from '@/services/apiPaths'
import {
  createConsolNoteFormula,
  deleteConsolNoteFormula,
  listConsolNoteFormulas,
  pushConsolidation,
  reseedConsolNoteFormulas,
  updateConsolNoteFormula,
  type ConsolNoteFormula,
  type ConsolNoteFormulaSection,
  type ConsolNoteTemplateType,
} from '@/services/consolidationApi'
import { confirmDangerous } from '@/utils/confirm'
import { handleApiError } from '@/utils/errorHandler'
import { formatTime, reportTypeLabel } from '@/components/consolidation/composables/consolTrialView'
import ConsolPushPanel from '@/components/consolidation/ConsolPushPanel.vue'
import GtGridCell from '@/components/grid/GtGridCell.vue'
import { ElInput, ElSelect } from '@/components/grid/adapters'
import { useAuthStore } from '@/stores/auth'
import { useRoleContextStore } from '@/stores/roleContext'

defineOptions({ name: 'ConsolFormulaManagementPanel' })

interface ReportFormulaRow {
  id: string
  row_code: string
  row_name: string
  formula: string | null
  formula_category: string | null
  formula_description: string | null
  /** 公式版本：修改须原样带回（spec formula-global-settings-sync，缺失 428、已被他人修改 409） */
  formula_version?: number
}

const props = withDefaults(defineProps<{
  mode: 'report' | 'note'
  projectId: string
  year: number
  templateType: string
  reportType?: string
  noteSection?: string
}>(), { reportType: 'balance_sheet', noteSection: '' })

const auth = useAuthStore()
const roleContext = useRoleContextStore()
const managerRoles = new Set(['admin', 'partner', 'manager'])
const effectiveRole = computed(() => roleContext.effectiveRole || auth.user?.role || '')
const canManage = computed(() => managerRoles.has(effectiveRole.value))
const templateType = computed<ConsolNoteTemplateType>(() => props.templateType === 'listed' ? 'listed' : 'soe')
const consolidatedStandard = computed(() => `${templateType.value}_consolidated`)
const panelTab = ref('formulas')
const loading = ref(false)
const saving = ref(false)
const reportRows = ref<ReportFormulaRow[]>([])
const formulaSections = ref<ConsolNoteFormulaSection[]>([])
const noteSectionOptions = ref<Array<{ section_id: string; title: string | null }>>([])
const selectedSectionId = ref('')
const selectedSectionTitle = computed(() => noteSectionOptions.value.find((s) => s.section_id === selectedSectionId.value)?.title || '')
const noteRows = computed(() => formulaSections.value.find((s) => s.section_id === selectedSectionId.value)?.formulas || [])
const pushPanelRef = ref<InstanceType<typeof ConsolPushPanel> | null>(null)
let loadSeq = 0

async function load() {
  if (!props.projectId || !props.year) return
  const seq = ++loadSeq
  loading.value = true
  try {
    if (props.mode === 'report') {
      reportRows.value = await api.get<ReportFormulaRow[]>(P_rc.list, {
        params: { report_type: props.reportType, applicable_standard: consolidatedStandard.value },
      })
    } else {
      // 章节列表（静态模板）和公式列表（按需种子化）独立容错：
      // 公式加载可能因报表配置不全而失败，此时章节导航仍可用。
      let groups: any[] = []
      let formulas: { sections: any[] } = { sections: [] }
      const [groupsResult, formulasResult] = await Promise.allSettled([
        api.get<any[]>(P_cn.list(templateType.value)),
        listConsolNoteFormulas(templateType.value),
      ])
      if (seq !== loadSeq) return
      if (groupsResult.status === 'fulfilled') groups = groupsResult.value ?? []
      if (formulasResult.status === 'fulfilled') formulas = formulasResult.value ?? { sections: [] }
      else console.warn('[ConsolFormulaPanel] 公式加载失败（章节导航仍可用）', formulasResult.reason)

      const options: Array<{ section_id: string; title: string | null }> = []
      for (const group of groups || []) {
        for (const section of group.children || []) {
          options.push({ section_id: section.section_id, title: section.title || null })
        }
      }
      // 公式表里可能有历史章节；仍应可见，不能因模板导航缺一项而静默藏掉
      for (const section of formulas.sections || []) {
        if (!options.some((item) => item.section_id === section.section_id)) {
          options.push({ section_id: section.section_id, title: section.title })
        }
      }
      noteSectionOptions.value = options
      formulaSections.value = formulas.sections || []
      const requested = props.noteSection || selectedSectionId.value
      selectedSectionId.value = options.some((item) => item.section_id === requested)
        ? requested
        : (formulas.sections[0]?.section_id || options[0]?.section_id || '')
    }
  } catch (err) {
    if (seq !== loadSeq) return
    if (props.mode === 'report') reportRows.value = []
    else { formulaSections.value = []; noteSectionOptions.value = [] }
    handleApiError(err, props.mode === 'report' ? '加载合并报表公式' : '加载合并附注公式')
  } finally {
    if (seq === loadSeq) loading.value = false
  }
}

const EDIT_HINT = '双击单元格修改，提交后确认保存'

function categoryLabel(value: string | null): string {
  return ({ auto_calc: '自动运算', logic_check: '逻辑审核', reasonability: '合理性' } as Record<string, string>)[value || ''] || value || '未分类'
}

// ── 格内编辑（spec excel-style-table-editing 5.5）─────────────────────────────
// 每格提交先记下（界面立即显示新值），攒 200ms 成一批：确认一次模板级影响 → 逐行保存（同一行的几格合并成一次请求）
// → 有保存成功的才推送一次。取消确认 / 保存失败的格退回服务器上的值（行对象只在保存成功后才改）。
type EditField = 'formula' | 'formula_category' | 'formula_description' | 'description'
type AnyRow = ReportFormulaRow | ConsolNoteFormula
const pending = reactive<Record<string, Partial<Record<EditField, string | null>>>>({})
const inflight = reactive<Record<string, Partial<Record<EditField, string | null>>>>({})
const pendingRows = new Map<string, AnyRow>()
let editTimer: ReturnType<typeof setTimeout> | null = null
const EDIT_BATCH_MS = 200

/** 格子当前显示 / 编辑的值：待保存 > 保存中 > 行上的值 */
function cellValue(row: AnyRow, field: EditField): string | null {
  const id = row.id
  if (pending[id] && field in pending[id]) return pending[id][field] ?? null
  if (inflight[id] && field in inflight[id]) return inflight[id][field] ?? null
  return ((row as unknown as Record<string, unknown>)[field] as string | null | undefined) ?? null
}

function normalizeEdit(field: EditField, value: unknown): string | null {
  const text = value == null ? '' : String(value)
  if (field === 'formula_category') return text || 'auto_calc'
  // 报表行的公式 / 说明清空存 null（与原保存一致）；附注公式原样（后端校验非空）
  if (field === 'formula' && props.mode === 'note') return text
  return text || null
}

function onCellEdit(row: AnyRow, field: EditField, value: unknown) {
  if (!row?.id) return
  if (props.mode === 'note' && !canManage.value) return
  const next = normalizeEdit(field, value)
  const current = normalizeEdit(field, (row as unknown as Record<string, unknown>)[field])
  const slot = (pending[row.id] ||= {})
  // 改回行上的值（且这一格没有正在保存的新值）：不算修改
  if (next === current && !(inflight[row.id] && field in inflight[row.id])) {
    delete slot[field]
    if (!Object.keys(slot).length) { delete pending[row.id]; pendingRows.delete(row.id) }
    return
  }
  slot[field] = next
  pendingRows.set(row.id, row)
  if (editTimer) clearTimeout(editTimer)
  editTimer = setTimeout(() => { void flushCellEdits() }, EDIT_BATCH_MS)
}

function discardPendingEdits() {
  if (editTimer) { clearTimeout(editTimer); editTimer = null }
  for (const id of Object.keys(pending)) delete pending[id]
  pendingRows.clear()
}

async function saveRowFields(row: AnyRow, fields: Partial<Record<EditField, string | null>>) {
  if (props.mode === 'report') {
    const r = row as ReportFormulaRow
    const merged = {
      formula: 'formula' in fields ? fields.formula ?? null : r.formula,
      formula_category: 'formula_category' in fields ? fields.formula_category ?? 'auto_calc' : (r.formula_category || 'auto_calc'),
      formula_description: 'formula_description' in fields ? fields.formula_description ?? null : (r.formula_description || null),
    }
    const saved = await api.put<Partial<ReportFormulaRow>>(P_rc.detail(r.id), {
      ...merged,
      expected_version: r.formula_version ?? 1,
      project_id: props.projectId,
      year: props.year,
      template_type: templateType.value,
    })
    Object.assign(r, merged)
    if (saved?.formula_version != null) r.formula_version = saved.formula_version
    return
  }
  const n = row as ConsolNoteFormula
  const updated = await updateConsolNoteFormula(n.id, {
    formula: 'formula' in fields ? String(fields.formula ?? '') : n.formula,
    description: 'description' in fields ? fields.description ?? null : (n.description || null),
    expected_version: n.version ?? 1,
  })
  const section = formulaSections.value.find((item) => item.section_id === n.section_id)
  if (section) {
    const index = section.formulas.findIndex((item) => item.id === n.id)
    if (index >= 0) section.formulas[index] = updated
  }
}

/** 保存攒下的格（测试与「保存中又有新提交」时直接调用） */
async function flushCellEdits(): Promise<void> {
  if (editTimer) { clearTimeout(editTimer); editTimer = null }
  if (saving.value) { // 上一批还在保存：等它结束再发
    editTimer = setTimeout(() => { void flushCellEdits() }, EDIT_BATCH_MS)
    return
  }
  const ids = Object.keys(pending)
  if (!ids.length) return
  const batch = ids.map((id) => ({ row: pendingRows.get(id)!, fields: { ...pending[id] } }))
  for (const id of ids) { inflight[id] = pending[id]; delete pending[id]; pendingRows.delete(id) }
  const release = (id: string) => { delete inflight[id] }
  try {
    await confirmTemplateChange(props.mode === 'report' ? '修改合并报表公式' : '修改合并附注公式')
  } catch {
    ids.forEach(release)
    return
  }
  saving.value = true
  let saved = 0
  try {
    for (const { row, fields } of batch) {
      try {
        await saveRowFields(row, fields)
        saved++
      } catch (err) {
        handleApiError(err, props.mode === 'report' ? '保存合并报表公式' : '保存合并附注公式')
      } finally {
        release(row.id)
      }
    }
  } finally { saving.value = false }
  if (saved) await pushAfterChange()
}

async function confirmTemplateChange(action: string) {
  await confirmDangerous({
    title: `${action}确认`,
    message: `当前修改属于 ${consolidatedStandard.value} 模板级配置，将影响所有使用该模板的合并项目。确认继续？`,
    confirmText: '确认保存',
  })
}

async function pushAfterChange() {
  try {
    await pushConsolidation(props.projectId, props.year, 'formula_changed')
    ElMessage.success('公式已保存，已开始推送当前合并项目')
  } catch {
    ElMessage.warning('公式已保存，但合并推送启动失败，请在“合并推送”页手工重试')
  }
  pushPanelRef.value?.load()
}

const showCreateDialog = ref(false)
const createFormRef = ref<FormInstance>()
const createForm = reactive({ rowNumber: 1, colIndex: 1, formula: '', description: '' })
const createRules: FormRules = {
  rowNumber: [{ required: true, message: '请输入行号', trigger: 'blur' }],
  colIndex: [{ required: true, message: '请输入数值列序号', trigger: 'blur' }],
  formula: [{ required: true, message: '请输入公式', trigger: 'blur' }],
}

function openCreate() {
  if (!canManage.value || !selectedSectionId.value) return
  Object.assign(createForm, { rowNumber: 1, colIndex: 1, formula: '', description: '' })
  showCreateDialog.value = true
}

async function createNoteRow() {
  if (!canManage.value || saving.value || !selectedSectionId.value) return
  if (!await createFormRef.value?.validate().catch(() => false)) return
  try {
    await confirmTemplateChange('新增合并附注公式')
  } catch { return }
  saving.value = true
  try {
    await createConsolNoteFormula({
      template_type: templateType.value,
      section_id: selectedSectionId.value,
      row_index: createForm.rowNumber - 1,
      col_index: createForm.colIndex,
      formula: createForm.formula,
      description: createForm.description || null,
    })
    showCreateDialog.value = false
    await load()
    await pushAfterChange()
  } catch (err) {
    handleApiError(err, '新增合并附注公式')
  } finally { saving.value = false }
}

async function removeNoteRow(row: ConsolNoteFormula) {
  if (!canManage.value || saving.value) return
  try {
    await confirmDangerous({
      title: '删除合并附注公式',
      message: `将删除“${row.position}”的模板公式；自动种子不会补回该单元格，并影响所有使用 ${templateType.value} 模板的合并项目。`,
      confirmText: '确认删除',
    })
  } catch { return }
  saving.value = true
  try {
    await deleteConsolNoteFormula(row.id, row.version ?? 1)
    await load()
    await pushAfterChange()
  } catch (err) {
    handleApiError(err, '删除合并附注公式')
  } finally { saving.value = false }
}

async function reseed() {
  if (!canManage.value || saving.value) return
  try {
    await confirmDangerous({
      title: '重新种子化合并附注公式',
      message: `将按 ${consolidatedStandard.value} 合并报表口径补齐自动种子；不会覆盖人工公式，也不会补回人工删除项。`,
      confirmText: '确认种子化',
    })
  } catch { return }
  saving.value = true
  try {
    const result = await reseedConsolNoteFormulas(templateType.value)
    await load()
    await pushAfterChange()
    ElMessage.info(`种子化完成：新增 ${result.inserted || 0} 条，保留人工 ${result.kept_manual || 0} 条`)
  } catch (err) {
    handleApiError(err, '重新种子化合并附注公式')
  } finally { saving.value = false }
}
watch(
  () => [props.mode, props.projectId, props.year, props.templateType, props.reportType, props.noteSection] as const,
  () => {
    discardPendingEdits()
    if (props.noteSection) selectedSectionId.value = props.noteSection
    load()
  },
  { immediate: true },
)

defineExpose({ load, panelTab })
</script>

<style scoped>
.gt-cfmp { min-height: 360px; }
.gt-cfmp-alert { margin-bottom: 8px; }
.gt-cfmp-source-note { margin-bottom: 8px; }
.gt-cfmp-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.gt-cfmp-toolbar > span { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-cfmp-note-select, .gt-cfmp-actions { display: flex; align-items: center; gap: 8px; }
.gt-cfmp-note-select { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-cfmp code { font-size: var(--gt-font-size-xs); white-space: normal; word-break: break-all; }
.gt-cfmp-form-hint { margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
