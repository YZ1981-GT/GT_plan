<template>
  <span
    v-if="notice"
    class="entry-sync-notice"
    :data-entry-sync-notice="props.entryId"
  >
    <el-tag size="small" type="warning" effect="plain">{{ notice.label }}</el-tag>
    <el-tooltip placement="bottom-start" effect="dark" :show-after="120">
      <template #content>
        <div class="entry-sync-notice__reason">{{ notice.reason }}</div>
      </template>
      <span class="entry-sync-notice__summary">{{ notice.summary }}</span>
    </el-tooltip>
  </span>
</template>

<script setup lang="ts">
/**
 * GtEntrySyncCapabilityNotice — AC 1.4 的「可操作原因」渲染宿主
 *
 * spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Task 46 收口
 *
 * 🔴 只声明 capability 而模板零引用 = 结构性死代码，数据层守卫看不见（G7 两级表头
 *    0/38 的同型缺陷）。所以本组件必须真挂在各宿主的模式切换工具栏里，且后端守卫
 *    按「宿主 import + 模板标签 + entry-id 绑定」三要素判定，缺一即红。
 */
import { computed } from 'vue'
import { entrySyncNotice } from './workpaperEntrySyncNotice'

const props = defineProps<{
  /** manifest 的稳定 entry_id */
  entryId: string
}>()

const notice = computed(() => entrySyncNotice(props.entryId))
</script>

<style scoped>
.entry-sync-notice {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}
.entry-sync-notice__summary {
  cursor: help;
  font-size: 12px;
  color: var(--el-color-warning);
  border-bottom: 1px dashed var(--el-color-warning);
}
.entry-sync-notice__reason {
  max-width: 380px;
  line-height: 1.6;
}
</style>
