<template>
  <!-- C.3.7: 段落变量编辑器 + 实时预览 -->
  <el-drawer
    v-model="visible"
    title="段落变量编辑"
    direction="rtl"
    size="500px"
  >
    <div class="vars-editor">
      <el-alert
        title="编辑变量后实时预览段落渲染效果"
        type="info"
        :closable="false"
        show-icon
        style="margin-bottom: 12px"
      />

      <!-- 变量编辑区 -->
      <div class="vars-form">
        <h4>变量列表</h4>
        <el-form label-width="120px" size="small">
          <el-form-item v-for="(_, key) in vars" :key="key" :label="key">
            <el-input v-model="vars[key]" placeholder="输入变量值" @input="debouncedPreview" />
          </el-form-item>
        </el-form>

        <el-button size="small" @click="addVariable" style="margin-top: 8px">+ 添加变量</el-button>
      </div>

      <!-- 实时预览 -->
      <div class="vars-preview">
        <h4>段落预览</h4>
        <div class="preview-content" v-loading="previewing">
          <div v-if="previewText" v-text="previewText" />
          <el-empty v-else description="加载中..." />
        </div>
      </div>

      <!-- 操作 -->
      <div class="vars-actions">
        <el-button :loading="saving" type="primary" @click="handleSave">保存变量</el-button>
        <el-button @click="visible = false">取消</el-button>
      </div>
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, watch, reactive } from 'vue'
import { api } from '@/services/apiProxy'
import { handleApiError } from '@/utils/errorHandler'
import { ElMessage, ElMessageBox } from 'element-plus'

interface Props {
  modelValue: boolean
  projectId: string
  year: number
  sectionId: string
}

const props = defineProps<Props>()
const emit = defineEmits<{ 'update:modelValue': [val: boolean]; 'saved': [] }>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const vars = reactive<Record<string, string>>({})
const previewText = ref('')
const previewing = ref(false)
const saving = ref(false)

let previewTimer: number | null = null

watch(visible, (v) => {
  if (v && props.sectionId) loadVars()
})

async function loadVars() {
  try {
    const resp: any = await api.get(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/text-template-vars`
    )
    Object.keys(vars).forEach(k => delete vars[k])
    Object.assign(vars, resp || {})
    refreshPreview()
  } catch {
    // ignore
  }
}

function debouncedPreview() {
  if (previewTimer) window.clearTimeout(previewTimer)
  previewTimer = window.setTimeout(refreshPreview, 300)
}

async function refreshPreview() {
  previewing.value = true
  try {
    const resp: any = await api.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/preview-text`,
      { vars }
    )
    previewText.value = resp?.text || ''
  } catch {
    previewText.value = ''
  } finally {
    previewing.value = false
  }
}

async function addVariable() {
  try {
    const { value: name } = await ElMessageBox.prompt('输入变量名', '添加变量', {
      inputPattern: /^[a-zA-Z_][a-zA-Z0-9_]*$/,
      inputErrorMessage: '变量名只能包含字母、数字、下划线，且以字母或下划线开头',
    })
    if (name) {
      vars[name] = ''
    }
  } catch {
    // user cancelled
  }
}

async function handleSave() {
  saving.value = true
  try {
    await api.put(
      `/api/disclosure-notes/${props.projectId}/${props.year}/sections/${props.sectionId}/text-template-vars`,
      { vars }
    )
    ElMessage.success('变量保存成功')
    emit('saved')
    visible.value = false
  } catch (e: any) {
    handleApiError(e, '保存')
  } finally {
    saving.value = false
  }
}
</script>

<style scoped>
.vars-editor {
  padding: 0 4px;
  display: flex;
  flex-direction: column;
  height: 100%;
}
.vars-form {
  flex: 1;
  margin-bottom: 16px;
}
.vars-form h4,
.vars-preview h4 {
  margin: 0 0 8px;
  font-size: 14px;
  color: #303133;
}
.vars-preview {
  border-top: 1px solid #ebeef5;
  padding-top: 12px;
  margin-bottom: 16px;
}
.preview-content {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 4px;
  min-height: 100px;
  font-size: 13px;
  line-height: 1.6;
  white-space: pre-wrap;
}
.vars-actions {
  display: flex;
  gap: 8px;
  justify-content: flex-end;
  padding-top: 12px;
  border-top: 1px solid #ebeef5;
}
</style>
