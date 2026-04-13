<template>
  <el-select
    v-model="selected"
    :placeholder="placeholder"
    :size="size"
    filterable
    @change="onChange"
  >
    <el-option
      v-for="m in models"
      :key="m.value"
      :label="m.label"
      :value="m.value"
    >
      <div class="gt-model-option">
        <span>{{ m.label }}</span>
        <span class="gt-model-ctx">{{ m.contextLimit }}</span>
      </div>
    </el-option>
  </el-select>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  size?: 'small' | 'default' | 'large'
}>(), {
  placeholder: '选择LLM模型',
  size: 'default',
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'change', model: string): void
}>()

const models = [
  { value: 'deepseek-chat', label: 'DeepSeek Chat', contextLimit: '64K' },
  { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner', contextLimit: '64K' },
  { value: 'qwen-plus', label: '通义千问 Plus', contextLimit: '128K' },
  { value: 'qwen-turbo', label: '通义千问 Turbo', contextLimit: '128K' },
  { value: 'glm-4', label: '智谱 GLM-4', contextLimit: '128K' },
  { value: 'moonshot-v1-128k', label: 'Kimi 128K', contextLimit: '128K' },
  { value: 'gpt-4o', label: 'GPT-4o', contextLimit: '128K' },
  { value: 'ollama-local', label: 'Ollama 本地模型', contextLimit: '8K' },
]

const selected = ref(props.modelValue || '')

function onChange(val: string) {
  emit('update:modelValue', val)
  emit('change', val)
}
</script>

<style scoped>
.gt-model-option { display: flex; justify-content: space-between; width: 100%; }
.gt-model-ctx { font-size: 12px; color: var(--gt-color-text-tertiary); }
</style>
