<template>
  <el-dropdown-item
    data-test="historical-upload-entry"
    :disabled="disabled"
    :title="disabled ? reason : '导入历史 Word/PDF 附注'"
    @click="onClick"
  >
    📄 历史 Word/PDF 导入<span v-if="disabled">（暂不可用）</span>
  </el-dropdown-item>
</template>

<script setup lang="ts">
const props = withDefaults(defineProps<{
  disabled?: boolean
  reason?: string
}>(), {
  disabled: true,
  reason: '历史 Word/PDF 解析尚未实现',
})

const emit = defineEmits<{
  request: []
}>()

function onClick() {
  if (props.disabled) return
  emit('request')
}
</script>
