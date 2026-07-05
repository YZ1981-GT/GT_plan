<script setup lang="ts">
/** G 循环编制流程提示条（对标 D4 guide-strip） */
withDefaults(defineProps<{
  label?: string
  steps: string[]
}>(), {
  label: '编制流程',
})
</script>

<template>
  <div class="g-cycle-guide-strip" data-testid="g-cycle-guide-strip">
    <span class="guide-label">{{ label }}：</span>
    <template v-for="(step, i) in steps" :key="`${step}-${i}`">
      <span class="guide-chip">{{ step }}</span>
      <span v-if="i < steps.length - 1" class="guide-arrow">→</span>
    </template>
  </div>
</template>

<style scoped>
.g-cycle-guide-strip {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  margin-bottom: 12px;
  padding: 10px 14px;
  background: var(--gt-color-success-bg, #f0f9eb);
  border-radius: 6px;
  border: 1px solid var(--gt-color-success-border, #e1f3d8);
  font-size: 12px;
}
.guide-label {
  font-weight: 600;
  color: var(--gt-color-success, #67c23a);
}
.guide-chip {
  background: #fff;
  border: 1px solid var(--gt-color-success-border, #c2e7b0);
  border-radius: 4px;
  padding: 2px 8px;
  color: var(--gt-color-success-dark, #529b2e);
}
.guide-arrow {
  color: #a8abb2;
}
</style>
