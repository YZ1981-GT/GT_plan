<template>
  <div class="disclosure-editor-page">
    <div class="de-header">
      <h2 class="de-title">附注编辑</h2>
      <div class="de-actions">
        <el-select v-model="templateType" style="width: 120px" @change="onGenerate">
          <el-option label="国企版" value="soe" />
          <el-option label="上市版" value="listed" />
        </el-select>
        <el-button @click="onGenerate" :loading="genLoading">生成附注</el-button>
        <el-button @click="onValidate" :loading="validateLoading" type="warning">执行校验</el-button>
      </div>
    </div>

    <el-row :gutter="12" class="de-body">
      <!-- 左侧：目录树 -->
      <el-col :span="5">
        <div class="panel tree-panel">
          <h4 class="panel-title">附注目录</h4>
          <el-tree :data="treeData" :props="{ label: 'label', children: 'children' }"
            highlight-current node-key="id" @node-click="onNodeClick"
            default-expand-all />
          <div v-if="!treeData.length && !treeLoading" class="empty-hint">
            暂无附注，请先生成
          </div>
        </div>
      </el-col>

      <!-- 中间：编辑区 -->
      <el-col :span="12">
        <div class="panel editor-panel" v-loading="detailLoading">
          <template v-if="currentNote">
            <div class="editor-header">
              <h4>{{ currentNote.note_section }} {{ currentNote.section_title }}</h4>
              <el-tag :type="currentNote.status === 'confirmed' ? 'success' : 'info'" size="small">
                {{ currentNote.status === 'confirmed' ? '已确认' : '草稿' }}
              </el-tag>
            </div>

            <!-- 表格型 -->
            <div v-if="currentNote.content_type === 'table' || currentNote.content_type === 'mixed'">
              <el-table v-if="currentNote.table_data?.rows" :data="currentNote.table_data.rows"
                border size="small" style="margin-bottom: 12px">
                <el-table-column v-for="(h, hi) in (currentNote.table_data.headers || [])" :key="hi"
                  :label="h" :min-width="hi === 0 ? 160 : 120" :align="hi === 0 ? 'left' : 'right'">
                  <template #default="{ row }">
                    <template v-if="hi === 0">
                      <span :class="{ 'total-label': row.is_total }">{{ row.label }}</span>
                    </template>
                    <template v-else>
                      <el-input-number v-if="editMode && !row.is_total"
                        v-model="row.values[hi - 1]" :controls="false" :precision="2"
                        size="small" style="width: 100%" />
                      <span v-else :class="{ 'total-val': row.is_total }">
                        {{ fmtAmt(row.values?.[hi - 1]) }}
                      </span>
                    </template>
                  </template>
                </el-table-column>
              </el-table>
            </div>

            <!-- 文字型 -->
            <div v-if="currentNote.content_type === 'text' || currentNote.content_type === 'mixed'">
              <el-input v-model="textContent" type="textarea" :rows="8"
                placeholder="请输入附注文字内容" />
            </div>

            <div class="editor-footer">
              <el-button v-if="!editMode" @click="editMode = true">编辑</el-button>
              <template v-else>
                <el-button @click="editMode = false">取消</el-button>
                <el-button type="primary" @click="onSave" :loading="saveLoading">保存</el-button>
              </template>
            </div>
          </template>
          <div v-else class="empty-hint">请从左侧目录选择章节</div>
        </div>
      </el-col>

      <!-- 右侧：校验面板 -->
      <el-col :span="7">
        <div class="panel validation-panel">
          <h4 class="panel-title">校验结果</h4>
          <div v-if="validationFindings.length === 0" class="empty-hint">暂无校验结果</div>
          <div v-for="(f, fi) in validationFindings" :key="fi" class="finding-item"
            :class="'severity-' + f.severity">
            <div class="finding-header">
              <el-tag :type="severityTagType(f.severity)" size="small">{{ f.severity }}</el-tag>
              <span class="finding-type">{{ f.check_type }}</span>
            </div>
            <div class="finding-section">{{ f.note_section }} {{ f.table_name }}</div>
            <div class="finding-msg">{{ f.message }}</div>
            <div v-if="f.expected_value || f.actual_value" class="finding-values">
              期望: {{ f.expected_value ?? '-' }} | 实际: {{ f.actual_value ?? '-' }}
            </div>
          </div>
        </div>
      </el-col>
    </el-row>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import {
  generateDisclosureNotes, getDisclosureNoteTree, getDisclosureNoteDetail,
  updateDisclosureNote, validateDisclosureNotes, getValidationResults,
  type DisclosureNoteTreeItem, type DisclosureNoteDetail, type NoteValidationFinding,
} from '@/services/auditPlatformApi'

const route = useRoute()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => Number(route.query.year) || new Date().getFullYear())

const treeLoading = ref(false)
const detailLoading = ref(false)
const genLoading = ref(false)
const validateLoading = ref(false)
const saveLoading = ref(false)
const editMode = ref(false)
const templateType = ref('soe')

const noteList = ref<DisclosureNoteTreeItem[]>([])
const currentNote = ref<DisclosureNoteDetail | null>(null)
const textContent = ref('')
const validationFindings = ref<NoteValidationFinding[]>([])

interface TreeNode { id: string; label: string; data: DisclosureNoteTreeItem; children?: TreeNode[] }

const treeData = computed<TreeNode[]>(() => {
  return noteList.value.map(n => ({
    id: n.id,
    label: `${n.note_section} ${n.section_title}`,
    data: n,
  }))
})

function fmtAmt(v: any): string {
  if (v === null || v === undefined) return '-'
  const n = typeof v === 'string' ? parseFloat(v) || 0 : v
  if (n === 0) return '-'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
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

async function onNodeClick(node: TreeNode) {
  detailLoading.value = true
  editMode.value = false
  try {
    currentNote.value = await getDisclosureNoteDetail(projectId.value, year.value, node.data.note_section)
    textContent.value = currentNote.value.text_content || ''
  } catch { currentNote.value = null }
  finally { detailLoading.value = false }
}

async function onGenerate() {
  genLoading.value = true
  try {
    await generateDisclosureNotes(projectId.value, year.value, templateType.value)
    ElMessage.success('附注生成完成')
    await fetchTree()
  } finally { genLoading.value = false }
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

onMounted(fetchTree)
</script>

<style scoped>
.disclosure-editor-page { padding: 16px; }
.de-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.de-title { margin: 0; color: var(--gt-color-primary); font-size: 20px; }
.de-actions { display: flex; gap: 8px; align-items: center; }
.de-body { height: calc(100vh - 180px); }
.panel { background: #fff; border-radius: var(--gt-radius-sm); padding: 12px; box-shadow: var(--gt-shadow-sm); height: 100%; overflow-y: auto; }
.panel-title { margin: 0 0 8px; font-size: 14px; color: var(--gt-color-primary); }
.empty-hint { color: #999; font-size: 13px; text-align: center; padding: 20px 0; }
.editor-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.editor-header h4 { margin: 0; font-size: 15px; }
.editor-footer { margin-top: 12px; text-align: right; }
.total-label { font-weight: 700; }
.total-val { font-weight: 700; }
.finding-item { padding: 8px; border-bottom: 1px solid #eee; }
.finding-item.severity-error { border-left: 3px solid #e74c3c; }
.finding-item.severity-warning { border-left: 3px solid #f39c12; }
.finding-item.severity-info { border-left: 3px solid #999; }
.finding-header { display: flex; align-items: center; gap: 6px; margin-bottom: 4px; }
.finding-type { font-size: 12px; color: #666; }
.finding-section { font-size: 12px; color: #999; }
.finding-msg { font-size: 13px; margin-top: 2px; }
.finding-values { font-size: 12px; color: #888; margin-top: 2px; }
</style>
