<template>
  <div class="gt-template-editor">
    <div class="gt-page-header">
      <el-button size="small" @click="$router.back()"><el-icon><ArrowLeft /></el-icon> 返回</el-button>
      <h2 class="gt-page-title">{{ isNew ? '新建模板' : '编辑模板' }}</h2>
    </div>

    <el-form ref="formRef" :model="form" :rules="rules" label-width="100px" style="max-width: 700px">
      <el-form-item label="模板名称" prop="template_name">
        <el-input v-model="form.template_name" placeholder="输入模板名称" />
      </el-form-item>
      <el-form-item label="分类" prop="category">
        <el-select v-model="form.category" style="width: 100%">
          <el-option label="行业专用" value="industry" />
          <el-option label="客户专用" value="client" />
          <el-option label="个人收藏" value="personal" />
        </el-select>
      </el-form-item>
      <el-form-item label="版本号" prop="version">
        <el-input v-model="form.version" placeholder="如 1.0.0" />
      </el-form-item>
      <el-form-item label="描述">
        <el-input v-model="form.description" type="textarea" :rows="3" placeholder="模板用途说明" />
      </el-form-item>
      <el-form-item label="模板文件">
        <TemplateUpload v-model="form.file" />
      </el-form-item>
      <el-form-item>
        <el-button type="primary" @click="onSave" :loading="saving">保存</el-button>
        <el-button @click="onValidate" :loading="validating" v-if="!isNew">验证模板</el-button>
      </el-form-item>
    </el-form>

    <TemplateValidator v-if="validationResult" :result="validationResult" style="margin-top: 16px; max-width: 700px" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ArrowLeft } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import type { FormInstance, FormRules } from 'element-plus'
import TemplateUpload from '@/components/extension/TemplateUpload.vue'
import TemplateValidator from '@/components/extension/TemplateValidator.vue'
import {
  getCustomTemplate, createCustomTemplate, updateCustomTemplate,
  validateCustomTemplate,
} from '@/services/commonApi'

const route = useRoute()
const router = useRouter()
const templateId = computed(() => route.params.id as string)
const isNew = computed(() => !templateId.value || templateId.value === 'new')

const formRef = ref<FormInstance>()
const saving = ref(false)
const validating = ref(false)
const validationResult = ref<any>(null)

const form = ref({
  template_name: '',
  category: 'personal',
  version: '1.0.0',
  description: '',
  file: null as File | null,
})

const rules: FormRules = {
  template_name: [{ required: true, message: '请输入模板名称', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  version: [{ required: true, message: '请输入版本号', trigger: 'blur' }],
}

async function loadTemplate() {
  if (isNew.value) return
  try {
    const t = await getCustomTemplate(templateId.value)
    form.value.template_name = t.template_name
    form.value.category = t.category
    form.value.version = t.version
    form.value.description = t.description || ''
  } catch { ElMessage.error('加载模板失败') }
}

async function onSave() {
  const valid = await formRef.value?.validate().catch(() => false)
  if (!valid) return
  saving.value = true
  try {
    const fd = new FormData()
    fd.append('template_name', form.value.template_name)
    fd.append('category', form.value.category)
    fd.append('version', form.value.version)
    if (form.value.description) fd.append('description', form.value.description)
    if (form.value.file) fd.append('file', form.value.file)

    if (isNew.value) {
      await createCustomTemplate(fd)
      ElMessage.success('模板创建成功')
    } else {
      await updateCustomTemplate(templateId.value, fd)
      ElMessage.success('模板更新成功')
    }
    router.push('/extension/custom-templates')
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}

async function onValidate() {
  validating.value = true
  try {
    validationResult.value = await validateCustomTemplate(templateId.value)
  } catch { ElMessage.error('验证请求失败') }
  finally { validating.value = false }
}

onMounted(loadTemplate)
</script>

<style scoped>
.gt-template-editor { padding: var(--gt-space-4); }
.gt-page-header { display: flex; align-items: center; gap: var(--gt-space-3); margin-bottom: var(--gt-space-4); }
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
</style>
