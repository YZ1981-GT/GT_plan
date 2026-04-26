<template>
  <el-dialog append-to-body v-model="visible" :title="`插件配置 - ${plugin?.plugin_name || ''}`" width="600px" @close="$emit('close')">
    <el-form label-width="100px" size="default" v-if="plugin">
      <el-form-item label="插件名称">
        <el-input :model-value="plugin.plugin_name" disabled />
      </el-form-item>
      <el-form-item label="版本">
        <el-input :model-value="plugin.version" disabled />
      </el-form-item>
      <el-form-item label="配置 (JSON)">
        <el-input
          v-model="configJson"
          type="textarea"
          :rows="10"
          placeholder='{"key": "value"}'
          class="gt-config-editor"
        />
      </el-form-item>
      <el-alert v-if="jsonError" type="error" :title="jsonError" :closable="false" show-icon style="margin-bottom: 12px" />
    </el-form>
    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onSave" :loading="saving">保存配置</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

const props = defineProps<{
  modelValue: boolean
  plugin: any
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'saved'): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

const configJson = ref('')
const jsonError = ref('')
const saving = ref(false)

watch(() => props.plugin, (p) => {
  if (p?.config) {
    configJson.value = JSON.stringify(p.config, null, 2)
  } else {
    configJson.value = '{}'
  }
  jsonError.value = ''
}, { immediate: true })

async function onSave() {
  jsonError.value = ''
  let parsed: any
  try {
    parsed = JSON.parse(configJson.value)
  } catch {
    jsonError.value = 'JSON 格式错误，请检查语法'
    return
  }
  saving.value = true
  try {
    await api.put(`/api/ai-plugins/${props.plugin.id}/config`, { config: parsed })
    ElMessage.success('配置已保存')
    emit('saved')
    visible.value = false
  } catch { ElMessage.error('保存失败') }
  finally { saving.value = false }
}
</script>

<style scoped>
.gt-config-editor :deep(textarea) {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 13px;
}
</style>
