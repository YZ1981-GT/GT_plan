<template>
  <el-dialog :model-value="visible" @update:model-value="$emit('update:visible', $event)"
    title="合并附注明细模板管理" width="800px" top="5vh" append-to-body destroy-on-close>

    <div style="display:flex;gap:12px;align-items:center;margin-bottom:12px">
      <span style="font-size:14px;font-weight:600">{{ sectionTitle || '请先选择章节' }}</span>
      <el-tag v-if="binding" size="small" type="success">已绑定 v{{ binding.version_number }}</el-tag>
      <el-tag v-else size="small" type="info">未绑定模板</el-tag>
      <span style="flex:1" />
      <el-button size="small" type="primary" @click="handleCreate">+ 新建模板</el-button>
      <el-button size="small" @click="loadTemplates" :loading="loading">🔄 刷新</el-button>
    </div>

    <el-alert v-if="errorMsg" type="error" :title="errorMsg" :closable="false" show-icon style="margin-bottom:10px" />

    <!-- 模板列表 -->
    <el-table v-loading="loading" :data="templates" border size="small" max-height="45vh" empty-text="暂无模板">
      <el-table-column label="模板名称" prop="name" min-width="180" show-overflow-tooltip />
      <el-table-column label="类型" width="80" align="center">
        <template #default="{ row }">
          <el-tag size="small">{{ row.template_type === 'listed' ? '上市' : '国企' }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column label="可见性" width="90" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.visibility === 'firm' ? 'success' : row.visibility === 'project' ? '' : 'info'">
            {{ row.visibility === 'firm' ? '全局' : row.visibility === 'project' ? '项目' : '草稿' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column label="版本" width="70" align="center">
        <template #default="{ row }">v{{ row.latest_version?.version_number || 1 }}</template>
      </el-table-column>
      <el-table-column label="行数" width="70" align="center">
        <template #default="{ row }">{{ row.latest_version?.rows?.length || 0 }}</template>
      </el-table-column>
      <el-table-column label="操作" width="180" align="center">
        <template #default="{ row }">
          <el-button size="small" text type="primary" @click="handleEdit(row)">编辑</el-button>
          <el-button size="small" text type="success" @click="handleBind(row)"
            :disabled="binding?.template_version_id === row.latest_version?.id">
            {{ binding?.template_version_id === row.latest_version?.id ? '已绑定' : '绑定' }}
          </el-button>
          <el-button size="small" text type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <template #footer>
      <el-button @click="$emit('update:visible', false)">关闭</el-button>
    </template>
  </el-dialog>

  <!-- 模板编辑器（嵌套） -->
  <ConsolNoteDetailTemplateEditor
    v-model:visible="showEditor"
    :project-id="projectId"
    :section-id="sectionId"
    :year="year"
    :template-type="templateType"
    :template="editingTemplate"
    @saved="onTemplateSaved"
  />
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import ConsolNoteDetailTemplateEditor from './ConsolNoteDetailTemplateEditor.vue'
import type { DetailTemplate, DetailTemplateBinding } from '@/services/consolidationApi'
import {
  listDetailTemplates,
  deleteDetailTemplate,
  getDetailTemplateBinding,
  bindDetailTemplate,
} from '@/services/consolidationApi'

const props = defineProps<{
  visible: boolean
  projectId: string
  sectionId: string
  sectionTitle: string
  year: number
  templateType: 'soe' | 'listed'
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'bound'): void
}>()

const loading = ref(false)
const errorMsg = ref('')
const templates = ref<DetailTemplate[]>([])
const binding = ref<DetailTemplateBinding | null>(null)
const showEditor = ref(false)
const editingTemplate = ref<DetailTemplate | null>(null)

watch(() => props.visible, (v) => { if (v && props.sectionId) loadTemplates() })

async function loadTemplates() {
  if (!props.sectionId) return
  loading.value = true
  errorMsg.value = ''
  try {
    const [list, bind] = await Promise.all([
      listDetailTemplates({ template_type: props.templateType, section_id: props.sectionId }),
      getDetailTemplateBinding(props.projectId, props.sectionId),
    ])
    templates.value = list
    binding.value = bind
  } catch (err: any) {
    errorMsg.value = err?.response?.data?.detail?.message || err?.message || '加载失败'
  } finally {
    loading.value = false
  }
}

function handleCreate() {
  editingTemplate.value = null
  showEditor.value = true
}

function handleEdit(tmpl: DetailTemplate) {
  editingTemplate.value = tmpl
  showEditor.value = true
}

async function handleBind(tmpl: DetailTemplate) {
  if (!tmpl.latest_version) {
    ElMessage.warning('该模板没有版本，请先编辑保存')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定将「${tmpl.name || '未命名'}」v${tmpl.latest_version.version_number} 绑定到当前章节？`,
      '绑定模板',
      { confirmButtonText: '确定', cancelButtonText: '取消', type: 'info' },
    )
    await bindDetailTemplate(props.projectId, props.sectionId, {
      template_version_id: tmpl.latest_version.id,
      confirm: true,
    })
    ElMessage.success('模板已绑定')
    await loadTemplates()
    emit('bound')
  } catch (err: any) {
    if (err === 'cancel' || err?.message === 'cancel') return
    ElMessage.error(err?.response?.data?.detail?.message || err?.message || '绑定失败')
  }
}

async function handleDelete(tmpl: DetailTemplate) {
  try {
    await ElMessageBox.confirm(
      `确定删除模板「${tmpl.name || '未命名'}」？已绑定此模板的项目将受影响。`,
      '删除确认',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning', confirmButtonClass: 'el-button--danger' },
    )
    await deleteDetailTemplate(tmpl.id)
    ElMessage.success('模板已删除')
    await loadTemplates()
  } catch (err: any) {
    if (err === 'cancel' || err?.message === 'cancel') return
    ElMessage.error(err?.response?.data?.detail?.message || err?.message || '删除失败')
  }
}

function onTemplateSaved() {
  showEditor.value = false
  loadTemplates()
}
</script>
