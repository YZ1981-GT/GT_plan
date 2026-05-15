<template>
  <div class="gt-form-editor gt-fade-in">
    <EditorSharedToolbar
      :wp-code="wpDetail?.wp_code"
      :wp-name="wpDetail?.wp_name"
      :status="wpDetail?.status"
      component-type="form"
      :dirty="dirty"
      :saving="saving"
      @back="goBack"
      @save="onSave"
      @export="onExport"
      @versions="$emit('show-versions')"
      @toggle-panel="$emit('toggle-panel')"
    />

    <div class="gt-form-editor-body" v-loading="loading">
      <el-empty v-if="!loading && !formSchema.length" description="暂无表单配置" />
      <el-form
        v-else
        ref="formRef"
        :model="formData"
        label-width="180px"
        label-position="top"
        class="gt-form-editor-form"
      >
        <template v-for="field in formSchema" :key="field.key">
          <!-- 分组标题 -->
          <el-divider v-if="field.type === 'divider'" content-position="left">
            {{ field.label }}
          </el-divider>

          <!-- 文本输入 -->
          <el-form-item v-else-if="field.type === 'input'" :label="field.label" :prop="field.key">
            <el-input v-model="formData[field.key]" :placeholder="field.placeholder" @change="markDirty" />
          </el-form-item>

          <!-- 多行文本 -->
          <el-form-item v-else-if="field.type === 'textarea'" :label="field.label" :prop="field.key">
            <el-input v-model="formData[field.key]" type="textarea" :rows="field.rows || 3" :placeholder="field.placeholder" @change="markDirty" />
          </el-form-item>

          <!-- 下拉选择 -->
          <el-form-item v-else-if="field.type === 'select'" :label="field.label" :prop="field.key">
            <el-select v-model="formData[field.key]" :placeholder="field.placeholder" @change="markDirty">
              <el-option v-for="opt in field.options" :key="opt.value" :label="opt.label" :value="opt.value" />
            </el-select>
          </el-form-item>

          <!-- 日期 -->
          <el-form-item v-else-if="field.type === 'date'" :label="field.label" :prop="field.key">
            <el-date-picker v-model="formData[field.key]" type="date" :placeholder="field.placeholder" @change="markDirty" />
          </el-form-item>

          <!-- 复选框 -->
          <el-form-item v-else-if="field.type === 'checkbox'" :label="field.label" :prop="field.key">
            <el-checkbox v-model="formData[field.key]" @change="markDirty">{{ field.checkLabel || '是' }}</el-checkbox>
          </el-form-item>

          <!-- 评分/打分 -->
          <el-form-item v-else-if="field.type === 'radio'" :label="field.label" :prop="field.key">
            <el-radio-group v-model="formData[field.key]" @change="markDirty">
              <el-radio v-for="opt in field.options" :key="opt.value" :value="opt.value">{{ opt.label }}</el-radio>
            </el-radio-group>
          </el-form-item>
        </template>
      </el-form>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import EditorSharedToolbar from '@/components/workpaper/EditorSharedToolbar.vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import type { WorkpaperDetail } from '@/services/workpaperApi'

interface FormField {
  key: string
  label: string
  type: 'input' | 'textarea' | 'select' | 'date' | 'checkbox' | 'radio' | 'divider'
  placeholder?: string
  rows?: number
  options?: { label: string; value: string }[]
  checkLabel?: string
}

const props = defineProps<{
  projectId: string
  wpId: string
  wpDetail: WorkpaperDetail | null
}>()

const emit = defineEmits<{
  'show-versions': []
  'toggle-panel': []
  saved: []
}>()

const loading = ref(true)
const saving = ref(false)
const dirty = ref(false)
const formRef = ref()
const formSchema = ref<FormField[]>([])
const formData = reactive<Record<string, any>>({})

function markDirty() { dirty.value = true }

function goBack() {
  window.history.back()
}

async function loadFormData() {
  loading.value = true
  try {
    // Load parsed_data which contains form schema + saved values
    const detail = await httpApi.get(P_wp.detail(props.projectId, props.wpId))
    const parsed = detail?.parsed_data || {}
    // Schema from template metadata procedure_steps or parsed_data._schema
    const schema: FormField[] = parsed._schema || parsed.procedure_steps || []
    formSchema.value = schema.filter((f: FormField) => f.key && f.type)
    // Populate form data
    for (const field of formSchema.value) {
      if (field.type !== 'divider') {
        formData[field.key] = parsed[field.key] ?? ''
      }
    }
  } catch (e: any) {
    handleApiError(e, '加载表单')
  } finally {
    loading.value = false
  }
}

async function onSave() {
  saving.value = true
  try {
    const payload = { ...formData, _schema: formSchema.value }
    await httpApi.put(P_wp.detail(props.projectId, props.wpId), {
      parsed_data: payload,
    })
    dirty.value = false
    ElMessage.success('保存成功')
    emit('saved')
  } catch (e: any) {
    handleApiError(e, '保存表单')
  } finally {
    saving.value = false
  }
}

function onExport() {
  ElMessage.info('表单导出功能开发中')
}

watch(() => props.wpId, () => { if (props.wpId) loadFormData() })
onMounted(() => { if (props.wpId) loadFormData() })
</script>

<style scoped>
.gt-form-editor { display: flex; flex-direction: column; height: 100%; }
.gt-form-editor-body { flex: 1; overflow-y: auto; padding: 24px 32px; }
.gt-form-editor-form { max-width: 800px; margin: 0 auto; }
</style>
