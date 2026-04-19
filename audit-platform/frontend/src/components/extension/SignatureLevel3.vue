<template>
  <el-dialog append-to-body v-model="visible" title="CA证书签名 (Level 3)" width="400px" @close="$emit('close')">
    <el-result icon="info" title="CA证书签名功能开发中" sub-title="该功能需要对接CA证书服务商，预计后续版本支持">
      <template #extra>
        <el-button @click="visible = false">关闭</el-button>
      </template>
    </el-result>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  modelValue: boolean
  objectType: string
  objectId: string
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'close'): void
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})
</script>
