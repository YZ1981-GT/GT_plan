<script setup lang="ts">
/** G 循环编制流程提示条（对标 D4 guide-strip） */
withDefaults(defineProps<{
  label?: string
  steps: string[]
  /** 当前所在步骤（0-based），-1 表示不高亮 */
  activeIndex?: number
  /** 已完成步骤索引列表 */
  completedIndices?: number[]
}>(), {
  label: '编制流程',
  activeIndex: -1,
  completedIndices: () => [],
})
</script>

<template>
  <div class="g-cycle-guide-strip" data-testid="g-cycle-guide-strip">
    <span class="guide-label">{{ label }}：</span>
    <template v-for="(step, i) in steps" :key="`${step}-${i}`">
      <span
        class="guide-chip"
        :class="{
          'is-active': i === activeIndex,
          'is-done': completedIndices.includes(i) && i !== activeIndex,
        }"
        :data-testid="`g-cycle-guide-step-${i}`"
      >
        <span v-if="completedIndices.includes(i)" class="step-check">✓</span>
        {{ step }}
      </span>
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
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #fff;
  border: 1px solid var(--gt-color-success-border, #c2e7b0);
  border-radius: 4px;
  padding: 2px 8px;
  color: var(--gt-color-success-dark, #529b2e);
  transition: border-color 0.15s, background 0.15s;
}
.guide-chip.is-done {
  background: #f0f9eb;
  border-color: #b3e19d;
  color: #529b2e;
}
.guide-chip.is-active {
  background: #ecf5ff;
  border-color: #409eff;
  color: #409eff;
  font-weight: 600;
  box-shadow: 0 0 0 1px rgba(64, 158, 255, 0.25);
}
.step-check {
  font-size: 11px;
  font-weight: 700;
}
.guide-arrow {
  color: #a8abb2;
}
</style>
