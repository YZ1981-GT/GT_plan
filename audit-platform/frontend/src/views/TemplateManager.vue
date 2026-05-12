<template>
  <div class="gt-tpl-manager gt-fade-in">
    <GtPageHeader title="模板管理" :show-back="false">
      <template #actions>
        <el-button v-if="!isEditing" size="small" @click="enterEdit">✏️ 编辑</el-button>
        <el-button v-else size="small" type="warning" @click="() => exitEdit()">退出编辑</el-button>
        <SharedTemplatePicker
          config-type="workpaper_template"
          :project-id="projectId"
          :get-config-data="getTemplateConfigData"
          @applied="onTemplateConfigApplied"
        />
        <el-button type="primary" @click="showUploadDialog = true">上传模板</el-button>
      </template>
    </GtPageHeader>

    <div v-if="isEditing" class="gt-edit-mode-ribbon"><span class="gt-edit-mode-icon">✏️</span> 编辑中 · 请记得保存</div>

    <el-tabs v-model="activeTab">
      <!-- 模板列表 -->
      <el-tab-pane label="模板列表" name="templates">
        <el-table :data="templates" v-loading="tplLoading" border stripe>
          <el-table-column prop="template_code" label="编号" width="130" />
          <el-table-column prop="template_name" label="名称" min-width="200" show-overflow-tooltip />
          <el-table-column prop="audit_cycle" label="循环" width="100" />
          <el-table-column label="版本" width="90" align="center">
            <template #default="{ row }">v{{ row.version_major }}.{{ row.version_minor }}</template>
          </el-table-column>
          <el-table-column prop="status" label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="(tplStatusType(row.status)) || undefined" size="small">{{ tplStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="onNewVersion(row)">新版本</el-button>
              <el-button size="small" @click="onViewTemplate(row)">查看</el-button>
              <el-button size="small" type="danger" @click="onDeleteTemplate(row)" v-permission="'template:delete'">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 模板集管理 -->
      <el-tab-pane label="模板集" name="sets">
        <el-table :data="templateSets" v-loading="setLoading" border stripe>
          <el-table-column prop="set_name" label="集合名称" min-width="200" />
          <el-table-column label="模板数" width="100" align="center">
            <template #default="{ row }">{{ row.template_codes?.length || 0 }}</template>
          </el-table-column>
          <el-table-column prop="applicable_audit_type" label="适用类型" width="140" />
          <el-table-column prop="description" label="描述" min-width="200" show-overflow-tooltip />
          <el-table-column label="操作" width="140" fixed="right">
            <template #default="{ row }">
              <el-button size="small" @click="onEditSet(row)">编辑</el-button>
              <el-button size="small" @click="onViewSet(row)">查看</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 上传模板弹窗 -->
    <el-dialog append-to-body v-model="showUploadDialog" title="上传模板" width="500px" destroy-on-close>
      <el-form :model="uploadForm" label-width="90px">
        <el-form-item label="模板编号" required>
          <el-input v-model="uploadForm.template_code" placeholder="如 D10" />
        </el-form-item>
        <el-form-item label="模板名称" required>
          <el-input v-model="uploadForm.template_name" placeholder="如 货币资金审定表" />
        </el-form-item>
        <el-form-item label="审计循环">
          <el-select v-model="uploadForm.audit_cycle" placeholder="选择循环" clearable style="width: 100%">
            <el-option label="B类 穿行测试" value="B" />
            <el-option label="C类 控制测试" value="C" />
            <el-option label="D类 货币资金" value="D" />
            <el-option label="E类 应收账款" value="E" />
            <el-option label="F类 存货" value="F" />
            <el-option label="G类 固定资产" value="G" />
          </el-select>
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="uploadForm.description" type="textarea" :rows="2" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showUploadDialog = false">取消</el-button>
        <el-button type="primary" @click="onUploadSubmit" :loading="uploadLoading"
          :disabled="!uploadForm.template_code || !uploadForm.template_name">
          上传
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { confirmDelete, confirmLeave } from '@/utils/confirm'
import { useEditMode } from '@/composables/useEditMode'
import {
  listTemplates, uploadTemplate, createTemplateVersion, deleteTemplate,
  listTemplateSets,
  type TemplateItem, type TemplateSetItem,
} from '@/services/workpaperApi'
import SharedTemplatePicker from '@/components/shared/SharedTemplatePicker.vue'
import { handleApiError } from '@/utils/errorHandler'

const route = useRoute()
const projectId = computed(() => (route.params.projectId as string) || '')
const { isEditing, isDirty, enterEdit, exitEdit, markDirty, clearDirty } = useEditMode()

const activeTab = ref('templates')
const tplLoading = ref(false)
const setLoading = ref(false)
const uploadLoading = ref(false)
const showUploadDialog = ref(false)

const templates = ref<TemplateItem[]>([])
const templateSets = ref<TemplateSetItem[]>([])

const uploadForm = ref({
  template_code: '',
  template_name: '',
  audit_cycle: '',
  description: '',
})

function tplStatusType(s: string): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  const m: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = { draft: 'info', published: 'success', deprecated: 'danger' }
  return m[s] || 'info'
}

function tplStatusLabel(s: string) {
  const m: Record<string, string> = { draft: '草稿', published: '已发布', deprecated: '已废弃' }
  return m[s] || s
}

async function fetchTemplates() {
  tplLoading.value = true
  try { templates.value = await listTemplates() }
  finally { tplLoading.value = false }
}

async function fetchSets() {
  setLoading.value = true
  try { templateSets.value = await listTemplateSets() }
  finally { setLoading.value = false }
}

async function onUploadSubmit() {
  uploadLoading.value = true
  try {
    await uploadTemplate({
      template_code: uploadForm.value.template_code,
      template_name: uploadForm.value.template_name,
      audit_cycle: uploadForm.value.audit_cycle || undefined,
      description: uploadForm.value.description || undefined,
    })
    ElMessage.success('模板上传成功')
    showUploadDialog.value = false
    uploadForm.value = { template_code: '', template_name: '', audit_cycle: '', description: '' }
    fetchTemplates()
  } finally { uploadLoading.value = false }
}

async function onNewVersion(row: TemplateItem) {
  try {
    await createTemplateVersion(row.template_code, 'minor')
    ElMessage.success('新版本已创建')
    fetchTemplates()
  } catch (e: any) { handleApiError(e, '创建版本') }
}

function onViewTemplate(row: TemplateItem) {
  ElMessage.info(`查看模板: ${row.template_code} ${row.template_name}`)
}

async function onDeleteTemplate(row: TemplateItem) {
  await confirmDelete(`模板 ${row.template_code}`)
  try {
    await deleteTemplate(row.id)
    ElMessage.success('模板已删除')
    fetchTemplates()
  } catch (e: any) { handleApiError(e, '删除') }
}

function onEditSet(row: TemplateSetItem) {
  ElMessage.info(`编辑模板集: ${row.set_name}`)
}

function onViewSet(row: TemplateSetItem) {
  ElMessage.info(`查看模板集: ${row.set_name}，包含 ${row.template_codes?.length || 0} 个模板`)
}

onMounted(() => {
  fetchTemplates()
  fetchSets()
})

// ── 共享模板 ──
function getTemplateConfigData(): Record<string, any> {
  return {
    templates: templates.value.map(t => ({
      template_code: t.template_code,
      template_name: t.template_name,
      audit_cycle: t.audit_cycle,
      status: t.status,
    })),
    sets: templateSets.value.map(s => ({
      set_name: s.set_name,
      template_codes: s.template_codes,
      applicable_audit_type: s.applicable_audit_type,
    })),
  }
}

function onTemplateConfigApplied(data: Record<string, any>) {
  const tpls = data?.templates || []
  if (tpls.length) {
    ElMessage.success(`已引用 ${tpls.length} 个模板配置，请刷新查看`)
    fetchTemplates()
  } else {
    ElMessage.info('模板中无数据')
  }
}
</script>

<style scoped>
.gt-tpl-manager { padding: var(--gt-space-4); }
.gt-tpl-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--gt-space-4); }
</style>
