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
            <span><b>{{ reportTypeLabel(reportType) }}</b> · {{ consolidatedStandard }} · {{ reportRows.length }} 行</span>
            <el-button size="small" :loading="loading" data-testid="consol-report-formula-refresh" @click="load">🔄 刷新</el-button>
          </div>
          <el-table v-loading="loading" :data="reportRows" border size="small" max-height="calc(100vh - 300px)"
            empty-text="当前模板没有该报表行" data-testid="consol-report-formulas">
            <el-table-column prop="row_code" label="行次" width="90" />
            <el-table-column prop="row_name" label="项目" min-width="190" show-overflow-tooltip />
            <el-table-column label="公式" min-width="330">
              <template #default="{ row }">
                <el-input v-if="editingId === row.id" v-model="editFormula" size="small"
                  placeholder="如 TB('1001','期末余额') 或 ROW('BS-001')" />
                <code v-else>{{ row.formula || '—' }}</code>
              </template>
            </el-table-column>
            <el-table-column label="分类" width="130">
              <template #default="{ row }">
                <el-select v-if="editingId === row.id" v-model="editCategory" size="small">
                  <el-option label="自动运算" value="auto_calc" />
                  <el-option label="逻辑审核" value="logic_check" />
                  <el-option label="合理性" value="reasonability" />
                </el-select>
                <span v-else>{{ categoryLabel(row.formula_category) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">
                <el-input v-if="editingId === row.id" v-model="editDescription" size="small" />
                <span v-else>{{ row.formula_description || '' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="130" fixed="right">
              <template #default="{ row }">
                <template v-if="editingId === row.id">
                  <el-button link type="primary" size="small" data-testid="consol-report-formula-save" @click="saveReportRow(row)">保存</el-button>
                  <el-button link size="small" @click="cancelEdit">取消</el-button>
                </template>
                <el-button v-else link type="primary" size="small" @click="startReportEdit(row)">编辑</el-button>
              </template>
            </el-table-column>
          </el-table>
        </template>

        <template v-else>
          <div class="gt-cfmp-toolbar">
            <div class="gt-cfmp-note-select">
              <span>章节</span>
              <el-select v-model="selectedSectionId" filterable size="small" style="width:320px"
                placeholder="选择附注章节" data-testid="consol-note-formula-section" @change="cancelEdit">
                <el-option v-for="section in noteSectionOptions" :key="section.section_id"
                  :label="`${section.section_id} ${section.title || ''}`" :value="section.section_id" />
              </el-select>
              <span>{{ noteRows.length }} 条公式</span>
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
                <el-input v-if="editingId === row.id" v-model="editFormula" size="small" />
                <code v-else>{{ row.formula }}</code>
              </template>
            </el-table-column>
            <el-table-column prop="source_label" label="来源" width="100" />
            <el-table-column label="说明" min-width="180">
              <template #default="{ row }">
                <el-input v-if="editingId === row.id" v-model="editDescription" size="small" />
                <span v-else>{{ row.description || '' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="更新时间" min-width="165">
              <template #default="{ row }">{{ formatTime(row.updated_at) || '—' }}</template>
            </el-table-column>
            <el-table-column v-if="canManage" label="操作" width="150" fixed="right">
              <template #default="{ row }">
                <template v-if="editingId === row.id">
                  <el-button link type="primary" size="small" data-testid="consol-note-formula-save" @click="saveNoteRow(row)">保存</el-button>
                  <el-button link size="small" @click="cancelEdit">取消</el-button>
                </template>
                <template v-else>
                  <el-button link type="primary" size="small" @click="startNoteEdit(row)">编辑</el-button>
                  <el-button link type="danger" size="small" @click="removeNoteRow(row)">删除</el-button>
                </template>
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

const editingId = ref<string | null>(null)
const editFormula = ref('')
const editCategory = ref('auto_calc')
const editDescription = ref('')

function categoryLabel(value: string | null): string {
  return ({ auto_calc: '自动运算', logic_check: '逻辑审核', reasonability: '合理性' } as Record<string, string>)[value || ''] || value || '未分类'
}

function cancelEdit() {
  editingId.value = null
  editFormula.value = ''
  editDescription.value = ''
}

function startReportEdit(row: ReportFormulaRow) {
  editingId.value = row.id
  editFormula.value = row.formula || ''
  editCategory.value = row.formula_category || 'auto_calc'
  editDescription.value = row.formula_description || ''
}

function startNoteEdit(row: ConsolNoteFormula) {
  if (!canManage.value) return
  editingId.value = row.id
  editFormula.value = row.formula
  editDescription.value = row.description || ''
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

async function saveReportRow(row: ReportFormulaRow) {
  if (!row.id || saving.value) return
  try {
    await confirmTemplateChange('修改合并报表公式')
  } catch { return }
  saving.value = true
  try {
    await api.put(P_rc.detail(row.id), {
      formula: editFormula.value || null,
      formula_category: editCategory.value,
      formula_description: editDescription.value || null,
      project_id: props.projectId,
      year: props.year,
      template_type: templateType.value,
    })
    row.formula = editFormula.value || null
    row.formula_category = editCategory.value
    row.formula_description = editDescription.value || null
    cancelEdit()
    await pushAfterChange()
  } catch (err) {
    handleApiError(err, '保存合并报表公式')
  } finally { saving.value = false }
}

async function saveNoteRow(row: ConsolNoteFormula) {
  if (!canManage.value || saving.value) return
  try {
    await confirmTemplateChange('修改合并附注公式')
  } catch { return }
  saving.value = true
  try {
    const updated = await updateConsolNoteFormula(row.id, {
      formula: editFormula.value,
      description: editDescription.value || null,
    })
    const section = formulaSections.value.find((item) => item.section_id === row.section_id)
    if (section) {
      const index = section.formulas.findIndex((item) => item.id === row.id)
      if (index >= 0) section.formulas[index] = updated
    }
    cancelEdit()
    await pushAfterChange()
  } catch (err) {
    handleApiError(err, '保存合并附注公式')
  } finally { saving.value = false }
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
    await deleteConsolNoteFormula(row.id)
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
    cancelEdit()
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
.gt-cfmp-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 12px; margin-bottom: 8px; }
.gt-cfmp-toolbar > span { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-cfmp-note-select, .gt-cfmp-actions { display: flex; align-items: center; gap: 8px; }
.gt-cfmp-note-select { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-cfmp code { font-size: var(--gt-font-size-xs); white-space: normal; word-break: break-all; }
.gt-cfmp-form-hint { margin-left: 8px; font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
</style>
