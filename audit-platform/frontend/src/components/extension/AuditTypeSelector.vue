<template>
  <div class="gt-audit-type-selector">
    <el-select
      v-model="selected"
      :placeholder="placeholder"
      :size="size"
      :disabled="disabled"
      @change="onChange"
    >
      <el-option
        v-for="t in auditTypes"
        :key="t.value"
        :label="t.label"
        :value="t.value"
      >
        <div class="gt-type-option">
          <span>{{ t.label }}</span>
          <el-tooltip v-if="t.description" :content="t.description" placement="right">
            <el-icon class="gt-type-info"><InfoFilled /></el-icon>
          </el-tooltip>
        </div>
      </el-option>
    </el-select>
    <div v-if="recommendation" class="gt-type-recommendation">
      <el-icon><InfoFilled /></el-icon>
      <span>{{ recommendation }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { InfoFilled } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'

const auditTypes = [
  { value: 'annual_audit', label: '年度审计', description: '常规年度财务报表审计' },
  { value: 'special_audit', label: '专项审计', description: '针对特定事项的专项审计' },
  { value: 'ipo_audit', label: 'IPO审计', description: '首次公开发行股票审计' },
  { value: 'internal_control_audit', label: '内控审计', description: '内部控制有效性审计' },
  { value: 'capital_verification', label: '验资', description: '注册资本实缴验证' },
  { value: 'tax_audit', label: '税审', description: '企业所得税汇算清缴审计' },
]

const props = withDefaults(defineProps<{
  modelValue?: string
  placeholder?: string
  size?: 'small' | 'default' | 'large'
  disabled?: boolean
}>(), {
  placeholder: '选择审计类型',
  size: 'default',
  disabled: false,
})

const emit = defineEmits<{
  (e: 'update:modelValue', v: string): void
  (e: 'change', type: string, rec: string | null): void
}>()

const selected = ref(props.modelValue || '')
const recommendation = ref('')

watch(() => props.modelValue, (v) => { selected.value = v || '' })

async function onChange(val: string) {
  emit('update:modelValue', val)
  recommendation.value = ''
  try {
    const data = await api.get(`/api/audit-types/${val}/recommendation`)
    const result = data
    recommendation.value = result.recommendation || result.message || ''
  } catch { /* ignore */ }
  emit('change', val, recommendation.value || null)
}
</script>

<style scoped>
.gt-audit-type-selector { display: flex; flex-direction: column; gap: var(--gt-space-2); }
.gt-type-option { display: flex; align-items: center; justify-content: space-between; width: 100%; }
.gt-type-info { color: var(--gt-color-text-tertiary); margin-left: 8px; font-size: 14px; }
.gt-type-recommendation {
  display: flex; align-items: flex-start; gap: 6px;
  padding: var(--gt-space-2) var(--gt-space-3);
  background: var(--gt-color-primary-bg);
  border-radius: var(--gt-radius-sm);
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary);
  line-height: 1.5;
}
</style>
