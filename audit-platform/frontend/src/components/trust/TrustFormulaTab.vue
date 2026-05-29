<template>
  <div class="trust-formula">
    <template v-if="tree">
      <div class="formula-root">
        <el-tag type="primary" size="small">根节点</el-tag>
        <span class="formula-ref">{{ tree.root }}</span>
      </div>
      <div v-if="tree.dependencies && tree.dependencies.length" class="formula-deps">
        <div v-for="(dep, idx) in tree.dependencies" :key="idx" class="formula-dep-item">
          <span class="dep-icon">→</span>
          <span>{{ dep.ref || dep }}</span>
          <span v-if="dep.value" class="dep-value">{{ dep.value }}</span>
        </div>
      </div>
      <el-empty v-else description="无公式依赖" :image-size="60" />
      <div v-if="tree.status === 'placeholder'" class="formula-placeholder-hint">
        <el-alert type="info" :closable="false" show-icon>
          公式依赖树功能正在开发中，当前为占位数据
        </el-alert>
      </div>
    </template>
    <el-empty v-else description="该单元格无公式依赖" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
defineProps<{
  tree: {
    root: string
    dependencies: Array<any>
    depth: number
    status: string
  } | null | undefined
}>()
</script>

<style scoped>
.trust-formula {
  padding: 12px 0;
}
.formula-root {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 16px;
}
.formula-ref {
  font-family: monospace;
  color: var(--gt-color-text-secondary, #6e6e73);
}
.formula-deps {
  padding-left: 16px;
}
.formula-dep-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}
.dep-icon {
  color: var(--gt-color-primary, #4b2d77);
}
.dep-value {
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
}
.formula-placeholder-hint {
  margin-top: 16px;
}
</style>
