<template>
  <div class="gt-priority-selector">
    <el-radio-group :model-value="modelValue" @update:model-value="(v: string | number | boolean | undefined) => $emit('update:modelValue', String(v ?? ''))" size="small">
      <el-radio-button value="must_fix">
        <span class="gt-priority-label must-fix">🔴 必须修改</span>
      </el-radio-button>
      <el-radio-button value="suggest">
        <span class="gt-priority-label suggest">🟠 建议修改</span>
      </el-radio-button>
      <el-radio-button value="info">
        <span class="gt-priority-label info">⚪ 仅供参考</span>
      </el-radio-button>
    </el-radio-group>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  modelValue: string
}>()

defineEmits<{
  'update:modelValue': [val: string]
}>()
</script>

<style scoped>
.gt-priority-selector {
  display: inline-flex;
}

.gt-priority-label {
  font-size: 12px;
}

.gt-priority-label.must-fix { color: #c62828; }
.gt-priority-label.suggest { color: #e65100; }
.gt-priority-label.info { color: #666; }
</style>
