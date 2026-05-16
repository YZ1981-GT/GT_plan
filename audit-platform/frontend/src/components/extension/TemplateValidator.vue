<template>
  <el-card class="gt-template-validator" shadow="never">
    <template #header>
      <div class="gt-validator-header">
        <span class="gt-validator-title">模板验证结果</span>
        <el-tag :type="result.valid ? 'success' : 'danger'" size="small">
          {{ result.valid ? '验证通过' : '存在问题' }}
        </el-tag>
      </div>
    </template>
    <div class="gt-check-list">
      <div v-for="(check, i) in checks" :key="i" class="gt-check-item">
        <el-icon :class="check.passed ? 'gt-check-pass' : 'gt-check-fail'">
          <CircleCheckFilled v-if="check.passed" />
          <CircleCloseFilled v-else />
        </el-icon>
        <div class="gt-check-content">
          <span class="gt-check-label">{{ check.label }}</span>
          <span v-if="check.message" class="gt-check-msg">{{ check.message }}</span>
        </div>
      </div>
    </div>
  </el-card>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { CircleCheckFilled, CircleCloseFilled } from '@element-plus/icons-vue'

const props = defineProps<{
  result: {
    valid: boolean
    issues?: Array<{ type: string; message: string }>
    checks?: Array<{ name: string; passed: boolean; message?: string }>
  }
}>()

const checks = computed(() => {
  if (props.result.checks) {
    return props.result.checks.map(c => ({
      label: c.name,
      passed: c.passed,
      message: c.message || '',
    }))
  }
  // Fallback: derive from issues
  const defaultChecks = [
    { key: 'formula_syntax', label: '公式语法检查' },
    { key: 'region_definition', label: '区域定义检查' },
    { key: 'named_ranges', label: '命名范围检查' },
    { key: 'file_format', label: '文件格式检查' },
  ]
  const issueTypes = new Set((props.result.issues || []).map(i => i.type))
  return defaultChecks.map(c => ({
    label: c.label,
    passed: !issueTypes.has(c.key),
    message: (props.result.issues || []).find(i => i.type === c.key)?.message || '',
  }))
})
</script>

<style scoped>
.gt-template-validator { border-radius: var(--gt-radius-md); }
.gt-validator-header { display: flex; justify-content: space-between; align-items: center; }
.gt-validator-title { font-weight: 600; }
.gt-check-list { display: flex; flex-direction: column; gap: var(--gt-space-3); }
.gt-check-item { display: flex; align-items: flex-start; gap: var(--gt-space-2); }
.gt-check-pass { color: var(--gt-color-success); font-size: var(--gt-font-size-xl); flex-shrink: 0; }
.gt-check-fail { color: var(--gt-color-coral); font-size: var(--gt-font-size-xl); flex-shrink: 0; }
.gt-check-content { display: flex; flex-direction: column; }
.gt-check-label { font-size: var(--gt-font-size-base); }
.gt-check-msg { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-top: 2px; }
</style>
