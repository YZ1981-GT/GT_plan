<template>
  <el-tooltip
    v-if="hint"
    :content="hint.content"
    placement="top"
    :show-after="300"
    effect="light"
    :popper-style="{ maxWidth: '360px', whiteSpace: 'pre-wrap' }"
  >
    <el-icon class="field-hint-icon"><QuestionFilled /></el-icon>
  </el-tooltip>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { QuestionFilled } from '@element-plus/icons-vue'
import { getFieldHint } from './fieldHints'

const props = defineProps<{
  field: string
}>()

const hint = computed(() => getFieldHint(props.field))
</script>

<style scoped>
.field-hint-icon {
  margin-left: 4px;
  font-size: 14px;
  color: var(--el-color-info);
  cursor: help;
  vertical-align: middle;
}
</style>
