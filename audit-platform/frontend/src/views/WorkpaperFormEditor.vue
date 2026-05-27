<template>
  <div class="gt-form-editor gt-fade-in">
    <!-- spec workpaper-editor-refactor Phase 4.3: useWpDetailGuard 守卫 -->
    <div v-if="!guard.ready.value && !guard.loading.value" class="gt-sub-editor-error-overlay">
      <div class="gt-sub-editor-error-card">
        <div class="gt-sub-editor-error-icon">
          <span v-if="guard.state.value === 'no_file'">📄</span>
          <span v-else-if="guard.state.value === 'no_index'">🔍</span>
          <span v-else-if="guard.state.value === 'invalid_id'">⚠️</span>
          <span v-else>❌</span>
        </div>
        <div class="gt-sub-editor-error-title">
          <template v-if="guard.state.value === 'no_file'">底稿文件尚未生成</template>
          <template v-else-if="guard.state.value === 'no_index'">底稿不存在</template>
          <template v-else-if="guard.state.value === 'invalid_id'">底稿 ID 不合法</template>
          <template v-else>加载底稿失败</template>
        </div>
        <div class="gt-sub-editor-error-message">{{ guard.errorMessage.value }}</div>
        <div class="gt-sub-editor-error-actions">
          <el-button size="small" @click="goBack">返回底稿列表</el-button>
          <el-button v-if="guard.state.value === 'error'" size="small" type="primary" @click="guard.refresh">重试</el-button>
        </div>
      </div>
    </div>

    <template v-else>
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

    <div class="gt-form-editor-body" v-loading="loading || guard.loading.value">
      <GtEmpty v-if="!loading && !formSchema.length" preset="no-data" title="暂无表单配置" />
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
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import EditorSharedToolbar from '@/components/workpaper/EditorSharedToolbar.vue'
import { api as httpApi } from '@/services/apiProxy'
import { workpapers as P_wp } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { useWpDetailGuard } from '@/composables/useWpDetailGuard'
import type { WorkpaperDetail } from '@/services/workpaperApi'
import GtEmpty from '@/components/common/GtEmpty.vue'

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

// spec workpaper-editor-refactor Phase 4.3: useWpDetailGuard 入口守卫
const guard = useWpDetailGuard(
  () => props.projectId,
  () => props.wpId,
)
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
.gt-form-editor { display: flex; flex-direction: column; height: 100%; position: relative; }
.gt-form-editor-body { flex: 1; overflow-y: auto; padding: 24px 32px; }
.gt-form-editor-form { max-width: 800px; margin: 0 auto; }
/* spec workpaper-editor-refactor Phase 4.3: 加载失败友好引导 overlay */
.gt-sub-editor-error-overlay {
  position: absolute; inset: 0; z-index: 100;
  display: flex; align-items: center; justify-content: center;
  background: var(--gt-color-bg-page, #f5f7fa);
  padding: 32px;
}
.gt-sub-editor-error-card {
  display: flex; flex-direction: column; align-items: center;
  gap: 16px; max-width: 480px;
  padding: 32px 40px;
  background: var(--gt-color-bg-white, #fff);
  border-radius: 12px;
  box-shadow: 0 4px 24px rgba(0, 0, 0, 0.06);
  text-align: center;
}
.gt-sub-editor-error-icon { font-size: 48px; line-height: 1; }
.gt-sub-editor-error-title {
  font-size: 18px; font-weight: 600;
  color: var(--gt-color-text-primary, #303133);
}
.gt-sub-editor-error-message {
  font-size: 14px; line-height: 1.6;
  color: var(--gt-color-text-secondary, #606266);
}
.gt-sub-editor-error-actions {
  display: flex; gap: 8px; margin-top: 8px;
}
</style>
