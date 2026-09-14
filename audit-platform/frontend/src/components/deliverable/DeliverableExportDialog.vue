<template>
  <el-dialog v-model="visible" title="选择性导出" width="560px" @close="emit('close')">
    <DocStructureTree :doc-type="docType" @change="onSectionsChange" />
    <el-alert
      v-if="checkedCount === 0"
      type="warning"
      :closable="false"
      title="请至少选择一个章节"
    />
    <template #footer>
      <el-button @click="emit('close')">取消</el-button>
      <el-button type="primary" :disabled="checkedCount === 0" @click="onConfirm">
        确认导出
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import DocStructureTree from './DocStructureTree.vue'

defineProps<{
  projectId: string
  year: number
  docType: string
}>()

const emit = defineEmits<{
  close: []
  confirm: [sections: string[]]
}>()

const visible = ref(true)
const selectedSections = ref<string[]>([])
const checkedCount = computed(() => selectedSections.value.length)

function onSectionsChange(sections: string[]) {
  selectedSections.value = sections
}

function onConfirm() {
  // 需求 1.4：空选禁用确认（按钮已 disabled，此处再做守卫）
  if (!selectedSections.value.length) return
  emit('confirm', selectedSections.value)
}
</script>
