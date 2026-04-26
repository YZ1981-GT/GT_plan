<template>
  <el-select
    v-model="selected"
    :placeholder="placeholder"
    :size="size"
    :disabled="disabled"
    :loading="loading"
    filterable
    @change="onChange"
  >
    <el-option
      v-for="s in standards"
      :key="s.id"
      :label="`${s.standard_code} - ${s.standard_name}`"
      :value="s.id"
    />
  </el-select>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { api } from '@/services/apiProxy'

interface Standard {
  id: string
  standard_code: string
  standard_name: string
  standard_description?: string
  is_active: boolean
}

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  size?: 'small' | 'default' | 'large'
  disabled?: boolean
}>(), {
  placeholder: '选择会计准则',
  size: 'default',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'change', standardId: string, standard: Standard | undefined): void
}>()

const loading = ref(false)
const standards = ref<Standard[]>([])
const selected = ref(props.modelValue || '')

watch(() => props.modelValue, (v) => { selected.value = v || '' })

async function loadStandards() {
  loading.value = true
  try {
    const data = await api.get('/api/accounting-standards')
    standards.value = (data ?? []).filter((s: Standard) => s.is_active)
  } catch { standards.value = [] }
  finally { loading.value = false }
}

function onChange(val: string) {
  emit('update:modelValue', val)
  emit('change', val, standards.value.find(s => s.id === val))
}

onMounted(loadStandards)
</script>
