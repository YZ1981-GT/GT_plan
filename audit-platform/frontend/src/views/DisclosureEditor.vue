<template>
  <div class="gt-disclosure-editor gt-fade-in">
    <div class="gt-de-header">
      <h2 class="gt-page-title">附注编辑</h2>
      <div class="gt-de-actions">
        <el-tag v-if="templateType" size="small" type="info" style="margin-right: 8px">
          {{ templateTypeLabel }}
        </el-tag>
        <el-select v-model="templateType" style="width: 180px" @change="handleTemplateChange">
          <el-option label="国企版" value="soe" />
          <el-option label="上市版" value="listed" />
          <el-option
            v-if="customTemplateId"
            :label="customTemplateName ? `自定义：${customTemplateName}` : '自定义模板'"
            value="custom"
          />
        </el-select>
        <el-button @click="onRefreshFromWP" :loading="refreshLoading" size="small">从底稿刷新</el-button>
        <el-button @click="onGenerate" :loading="genLoading">生成附注</el-button>
        <el-tooltip content="当前仅支持余额核对和子项校验，其他校验规则开发中" placement="top">
          <el-button @click="onValidate" :loading="validateLoading" type="warning">执行校验</el-button>
        </el-tooltip>
        <el-button @click="onExportWord" :loading="exportLoading" type="primary">导出 Word</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="gt-de-body">
      <!-- 左侧：目录树 -->
      <el-col :span="5">
        <div class="gt-de-panel gt-de-tree-panel">
          <h4 class="gt-de-panel-title">附注目录</h4>
          <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }"
            highlight-current node-key="id" @node-click="onNodeClick"
            default-expand-all />
          <div v-if="!treeData.length && !treeLoading" class="gt-de-empty-hint">
            暂无附注，请先生成
          </div>
        </div>
      </el-col>

      <!-- 中间：编辑区 -->
      <el-col :span="12">
        <div class="gt-de-panel gt-de-editor-panel" v-loading="detailLoading">
          <template v-if="currentNote">
            <div class="gt-de-editor-header">
              <h4>{{ currentNote.note_section }} {{ currentNote.section_title }}</h4>
              <el-tag :type="currentNote.status === 'confirmed' ? 'success' : 'info'" size="small">
                {{ currentNote.status === 'confirmed' ? '已确认' : '草稿' }}
              </el-tag>
            </div>

            <!-- 表格型 -->
            <div v-if="currentNote.content_type === 'table' || currentNote.content_type === 'mixed'">
              <el-table v-if="currentNote.table_data?.rows" :data="currentNote.table_data.rows"
                border size="small" style="margin-bottom: 12px">
                <el-table-column v-for="(h, hiRaw) in (currentNote.table_data.headers || [])" :key="hiRaw"
                  :label="h" :min-width="Number(hiRaw) === 0 ? 160 : 120" :align="Number(hiRaw) === 0 ? 'left' : 'right'">
                  <template #default="{ row }">
                    <template v-if="Number(hiRaw) === 0">
                      <span :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
                    </template>
                    <template v-else>
                      <div class="gt-cell-wrapper">
                        <el-input-number v-if="editMode && !row.is_total"
                          v-model="row.values[Number(hiRaw) - 1]" :controls="false" :precision="2"
                          size="small" style="width: 100%"
                          @change="onCellValueChange($index, Number(hiRaw) - 1, $event)" />
                        <span v-else-if="row.is_total" :class="{ 'gt-formula-mismatch': isFormulaMismatch(row, Number(hiRaw) - 1) }">
                          {{ fmtAmt(getCellValue(row, Number(hiRaw) - 1)) }}
                        </span>
                        <span v-else :class="{ 'total-val': row.is_total }">
                          {{ fmtAmt(getCellValue(row, Number(hiRaw) - 1)) }}
                        </span>
                        <span v-if="getCellMode(row, Number(hiRaw) - 1) === 'auto'" class="gt-cell-source" title="自动提数">📊</span>
                        <span v-else-if="getCellMode(row, Number(hiRaw) - 1) === 'manual'" class="gt-cell-manual" title="手动编辑">✏️</span>
                      </div>
                    </template>
                  </template>
                </el-table-column>
                <!-- 上年数据列 -->
                <el-table-column v-if="priorYearNote?.table_data" label="上年数" width="120" align="right">
                  <template #default="{ $index }">
                    <span class="gt-prior-year-val">{{ fmtAmt(getPriorYearValue(currentNote.table_data.rows[$index], $index)) }}</span>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 文字型 — TipTap 富文本编辑器 -->
            <div v-if="currentNote.content_type === 'text' || currentNote.content_type === 'mixed'" class="gt-de-tiptap-wrapper">
              <div v-if="editor" class="gt-de-tiptap-toolbar">
                <el-button-group size="small">
                  <el-button @click="editor.chain().focus().toggleBold().run()" :type="editor.isActive('bold') ? 'primary' : ''">B</el-button>
                  <el-button @click="editor.chain().focus().toggleItalic().run()" :type="editor.isActive('italic') ? 'primary' : ''">I</el-button>
                  <el-button @click="editor.chain().focus().toggleBulletList().run()">列表</el-button>
                  <el-button @click="editor.chain().focus().toggleHeading({ level: 3 }).run()">H3</el-button>
                  <el-button @click="editor.chain().focus().undo().run()">撤销</el-button>
                  <el-button @click="editor.chain().focus().redo().run()">重做</el-button>
                </el-button-group>
              </div>
              <editor-content :editor="editor" class="gt-de-tiptap-content" />
            </div>

            <div class="gt-de-editor-footer">
              <el-button v-if="!editMode" @click="editMode = true">编辑</el-button>
              <template v-else>
                <el-button @click="editMode = false">取消</el-button>
                <el-button type="primary" @click="onSave" :loading="saveLoading">保存</el-button>
              </template>
            </div>
          </template>
          <div v-else class="gt-de-empty-hint">请从左侧目录选择章节</div>
        </div>
      </el-col>

      <!-- 右侧：校验面板 -->
      <el-col :span="7">
        <div class="gt-de-panel gt-de-validation-panel">
          <h4 class="gt-de-panel-title">校验结果</h4>
          <div v-if="validationFindings.length === 0" class="gt-de-empty-hint">暂无校验结果</div>
          <div v-for="(f, fi) in validationFindings" :key="fi" class="gt-de-finding-item"
            :class="'gt-de-severity-' + f.severity">
            <div class="gt-de-finding-header">
              <el-tag :type="severityTagType(f.severity)" size="small">{{ f.severity }}</el-tag>
              <span class="gt-de-finding-type">{{ f.check_type }}</span>
            </div>
            <div class="gt-de-finding-section">{{ f.note_section }} {{ f.table_name }}</div>
            <div class="gt-de-finding-msg">{{ f.message }}</div>
            <div v-if="f.expected_value || f.actual_value" class="gt-de-finding-values">
              期望: {{ f.expected_value ?? '-' }} | 实际: {{ f.actual_value ?? '-' }}
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { refreshDisclosureFromWorkpapers, getProjectWizardState } from '@/services/commonApi'
import { useEditor, EditorContent } from '@tiptap/vue-3'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import {
  generateDisclosureNotes, getDisclosureNoteTree, getDisclosureNoteDetail,
  updateDisclosureNote, validateDisclosureNotes, getValidationResults,
  type DisclosureNoteTreeItem, type DisclosureNoteDetail, type NoteValidationFinding,
} from '@/services/auditPlatformApi'
import { api } from '@/services/apiProxy'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const treeLoading = ref(false)
const detailLoading = ref(false)
const genLoading = ref(false)
const validateLoading = ref(false)
const saveLoading = ref(false)
const refreshLoading = ref(false)
const exportLoading = ref(false)
const editMode = ref(false)
const templateType = ref('soe')
const customTemplateId = ref('')
const customTemplateName = ref('')
const customTemplateVersion = ref('')

const noteList = ref<DisclosureNoteTreeItem[]>([])
const currentNote = ref<DisclosureNoteDetail | null>(null)
const textContent = ref('')
const validationFindings = ref<NoteValidationFinding[]>([])
const priorYearNote = ref<any>(null)
// TipTap 编辑器
const editor = useEditor({
  extensions: [
    StarterKit,
    Placeholder.configure({ placeholder: '请输入附注文字内容...' }),
  ],
  content: '',
  onUpdate: ({ editor: e }) => { textContent.value = e.getHTML() },
})

onBeforeUnmount(() => { editor.value?.destroy() })
interface TreeNode { id: string; label: string; data: DisclosureNoteTreeItem; children?: TreeNode[] }

const treeData = computed<TreeNode[]>(() => {
  return noteList.value.map(n => ({
    id: n.id,
    label: `${n.note_section} ${n.section_title}`,
    data: n,
  }))
})

const templateTypeLabel = computed(() => {
  if (templateType.value === 'custom') {
    return customTemplateVersion.value && customTemplateName.value
      ? `自定义：${customTemplateName.value}（${customTemplateVersion.value}）`
      : customTemplateName.value || '自定义模板'
  }
  return templateType.value === 'listed' ? '上市版' : '国企版'
})

function fmtAmt(v: any): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getCellValue(row: any, colIdx: number): any {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.value ?? cell.manual_value ?? 0
  return cell
}

function getCellMode(row: any, colIdx: number): string {
  const cells = row.cells || row.values || []
  const cell = cells[colIdx]
  if (cell && typeof cell === 'object') return cell.mode || 'auto'
  return ''
}

function getPriorYearValue(row: any, rowIndex: number): any {
  if (!priorYearNote.value?.table_data?.rows) return null
  const priorRow = priorYearNote.value.table_data.rows[rowIndex]
  if (!priorRow) return null
  const values = priorRow.values || priorRow.cells || []
  return values[0] ?? null
}

function onCellValueChange(rowIndex: number, colIndex: number, _newValue: number) {
  if (!currentNote.value?.table_data?.rows) return
  const rows = currentNote.value.table_data.rows
  const totalRowIndex = rows.findIndex((r: any) => r.is_total)
  if (totalRowIndex < 0) return
  // 纵向合计：所有非合计行的同列求和
  let sum = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    sum += parseFloat(vals[colIndex]) || 0
  }
  if (!rows[totalRowIndex].values) rows[totalRowIndex].values = []
  rows[totalRowIndex].values[colIndex] = sum
  // 横向公式
  recalcHorizontalFormula(rowIndex)
}

function recalcHorizontalFormula(rowIndex: number) {
  const row = currentNote.value?.table_data?.rows?.[rowIndex]
  if (!row || !row.formula_type) return
  if (row.formula_type === 'opening_plus_changes') {
    const vals = row.values || []
    if (vals.length >= 3) {
      const opening = parseFloat(vals[0]) || 0
      let changes = 0
      for (let i = 1; i < vals.length - 1; i++) changes += parseFloat(vals[i]) || 0
      vals[vals.length - 1] = opening + changes
    }
  }
}

function isFormulaMismatch(row: any, colIdx: number): boolean {
  if (!row.is_total || !currentNote.value?.table_data?.rows) return false
  const rows = currentNote.value.table_data.rows
  let expected = 0
  for (let i = 0; i < rows.length; i++) {
    if (rows[i].is_total) continue
    const vals = rows[i].values || []
    expected += parseFloat(vals[colIdx]) || 0
  }
  const actual = parseFloat((row.values || [])[colIdx]) || 0
  return Math.abs(expected - actual) > 0.01
}

async function onRefreshFromWP() {
  refreshLoading.value = true
  try {
    await refreshDisclosureFromWorkpapers(projectId.value, year.value)
    ElMessage.success('已从底稿刷新数据')
    if (currentNote.value) await fetchDetail(currentNote.value.note_section)
  } catch { ElMessage.error('刷新失败') }
  finally { refreshLoading.value = false }
}

async function onExportWord() {
  exportLoading.value = true
  try {
    const { default: http } = await import('@/utils/http')
    const resp = await http.post(
      `/api/disclosure-notes/${projectId.value}/${year.value}/export-word`,
      {},
      { responseType: 'blob' }
    )
    // 下载 blob
    const blob = new Blob([resp.data], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `附注_${year.value}.docx`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('附注 Word 导出成功')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '请稍后重试'))
  } finally { exportLoading.value = false }
}

function severityTagType(s: string) {
  const m: Record<string, string> = { error: 'danger', warning: 'warning', info: 'info' }
  return m[s] || 'info'
}

async function fetchTree() {
  treeLoading.value = true
  try { noteList.value = await getDisclosureNoteTree(projectId.value, year.value) }
  catch { noteList.value = [] }
  finally { treeLoading.value = false }
}

async function loadProjectTemplateConfig() {
  try {
    const state = await getProjectWizardState(projectId.value)
    const basicInfo = state?.steps?.basic_info?.data || state?.basic_info?.data || {}
    customTemplateId.value = basicInfo.custom_template_id || ''
    customTemplateName.value = basicInfo.custom_template_name || ''
    customTemplateVersion.value = basicInfo.custom_template_version || ''
    templateType.value = basicInfo.template_type || 'soe'
    if (templateType.value === 'custom' && !customTemplateId.value) {
      templateType.value = 'soe'
    }
  } catch {
    templateType.value = 'soe'
    customTemplateId.value = ''
    customTemplateName.value = ''
    customTemplateVersion.value = ''
  }
}

async function onNodeClick(node: TreeNode) {
  detailLoading.value = true
  editMode.value = false
  try {
    await fetchDetail(node.data.note_section)
  } catch { currentNote.value = null }
  finally { detailLoading.value = false }
}

async function fetchDetail(noteSection: string) {
  currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, noteSection)
  textContent.value = currentNote.value.text_content || ''
  if (editor.value) editor.value.commands.setContent(textContent.value)
  // 并行加载上年数据
  try {
    priorYearNote.value = await api.get(
      `/api/disclosure-notes/${projectId.value}/${year.value}/${noteSection}/prior-year`
    )
  } catch { priorYearNote.value = null }
}

async function onGenerate() {
  if (templateType.value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    return
  }
  genLoading.value = true
  try {
    await generateDisclosureNotes(projectId.value, year.value, templateType.value)
    ElMessage.success('附注生成完成')
    await fetchTree()
  } finally { genLoading.value = false }
}

async function handleTemplateChange(value: string) {
  if (value === 'custom' && !customTemplateId.value) {
    ElMessage.warning('当前项目未绑定自定义附注模板，请先在项目基本信息中选择')
    templateType.value = 'soe'
    return
  }
  await onGenerate()
}

async function onValidate() {
  validateLoading.value = true
  try {
    await validateDisclosureNotes(projectId.value, year.value)
    validationFindings.value = await getValidationResults(projectId.value, year.value)
    ElMessage.success(`校验完成，发现 ${validationFindings.value.length} 项`)
  } finally { validateLoading.value = false }
}

async function onSave() {
  if (!currentNote.value) return
  saveLoading.value = true
  try {
    const body: Record<string, any> = {}
    if (currentNote.value.content_type === 'text' || currentNote.value.content_type === 'mixed') {
      body.text_content = textContent.value
    }
    if (currentNote.value.content_type === 'table' || currentNote.value.content_type === 'mixed') {
      body.table_data = currentNote.value.table_data
    }
    await updateDisclosureNote(currentNote.value.id, body)
    ElMessage.success('保存成功')
    editMode.value = false
    currentNote.value.status = 'confirmed'
  } finally { saveLoading.value = false }
}

onMounted(async () => {
  await loadProjectTemplateConfig()
  await fetchTree()
})
</script>

<style scoped>
.gt-disclosure-editor { padding: var(--gt-space-4); }
.gt-de-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-de-actions { display: flex; gap: var(--gt-space-2); align-items: center; }
.gt-de-body { height: calc(100vh - 180px); }
.gt-de-panel { background: var(--gt-color-bg-white); border-radius: var(--gt-radius-sm); padding: var(--gt-space-3); box-shadow: var(--gt-shadow-sm); height: 100%; overflow-y: auto; }
.gt-de-panel-title { margin: 0 0 var(--gt-space-2); font-size: var(--gt-font-size-base); color: var(--gt-color-primary); }
.gt-de-empty-hint { color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-sm); text-align: center; padding: var(--gt-space-5) 0; }
.gt-de-editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-3); }
.gt-de-editor-header h4 { margin: 0; font-size: var(--gt-font-size-md); }
.gt-de-editor-footer { margin-top: var(--gt-space-3); text-align: right; }
.gt-de-total-label { font-weight: 700; }
.gt-de-total-val { font-weight: 700; }
.gt-de-finding-item { padding: var(--gt-space-2); border-bottom: 1px solid var(--gt-color-border-light); }
.gt-de-finding-item.gt-de-severity-error { border-left: 3px solid var(--gt-color-coral); }
.gt-de-finding-item.gt-de-severity-warning { border-left: 3px solid var(--gt-color-wheat); }
.gt-de-finding-item.gt-de-severity-info { border-left: 3px solid var(--gt-color-text-tertiary); }
.gt-de-finding-header { display: flex; align-items: center; gap: 6px; margin-bottom: var(--gt-space-1); }
.gt-de-finding-type { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); }
.gt-de-finding-section { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.gt-de-finding-msg { font-size: var(--gt-font-size-sm); margin-top: 2px; }
.gt-de-finding-values { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); margin-top: 2px; }
.gt-cell-wrapper { display: flex; align-items: center; gap: 4px; }
.gt-cell-source { font-size: 10px; cursor: help; }
.gt-cell-manual { font-size: 10px; cursor: help; }
.gt-de-tiptap-wrapper { border: 1px solid var(--gt-color-border-light, #e4e7ed); border-radius: var(--gt-radius-sm, 4px); }
.gt-de-tiptap-toolbar { padding: 4px 8px; border-bottom: 1px solid var(--gt-color-border-light, #e4e7ed); background: #fafafa; }
.gt-de-tiptap-content { padding: 12px; min-height: 200px; }
.gt-de-tiptap-content :deep(.ProseMirror) { outline: none; min-height: 180px; }
.gt-de-tiptap-content :deep(.ProseMirror p.is-editor-empty:first-child::before) { color: #adb5bd; content: attr(data-placeholder); float: left; height: 0; pointer-events: none; }
.gt-prior-year-val { color: var(--gt-color-text-tertiary); font-style: italic; font-size: 12px; }
.gt-formula-mismatch { color: var(--gt-color-coral, #FF5149) !important; font-weight: 700; text-decoration: underline wavy var(--gt-color-coral, #FF5149); }
</style>
