<template>
  <div class="trust-penetration">
    <el-timeline v-if="entries && entries.length">
      <el-timeline-item
        v-for="item in entries"
        :key="item.layer"
        :type="item.value ? 'success' : 'info'"
        :hollow="!item.value"
      >
        <div class="penetration-item">
          <span class="layer-badge">L{{ item.layer }}</span>
          <span class="layer-type">{{ item.label }}</span>
          <span v-if="item.ref" class="layer-ref">{{ item.ref }}</span>
          <span v-if="item.value" class="layer-value">{{ item.value }}</span>
        </div>
      </el-timeline-item>
    </el-timeline>
    <el-empty v-else description="暂无穿透链路数据" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  entries: Array<{
    layer: number
    type: string
    label: string
    ref: string | null
    value: any
  }> | undefined
}>()
</script>

<style scoped>
.trust-penetration {
  padding: 12px 0;
}
.penetration-item {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.layer-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 20px;
  border-radius: 4px;
  background: var(--gt-color-primary-bg, #f4f0fa);
  color: var(--gt-color-primary, #4b2d77);
  font-size: 11px;
  font-weight: 600;
}
.layer-type {
  font-weight: 500;
  color: var(--gt-color-text, #1d1d1f);
}
.layer-ref {
  color: var(--gt-color-text-secondary, #6e6e73);
  font-size: 12px;
  font-family: monospace;
}
.layer-value {
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
}
</style>
