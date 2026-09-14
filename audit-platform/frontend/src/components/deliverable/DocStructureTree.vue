<template>
  <div class="doc-structure-tree">
    <p class="doc-structure-tree__hint">
      默认全选所有内容；取消勾选后仅导出选中项{{ docType === 'disclosure_notes' ? '（附注支持按层级展开/折叠选择）' : '' }}。
    </p>
    <el-tree
      ref="treeRef"
      :data="treeData"
      show-checkbox
      node-key="id"
      default-expand-all
      :default-checked-keys="defaultChecked"
      @check="onCheck"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { ElTree } from 'element-plus'
import { buildDocStructure, defaultCheckedKeys, projectedSections } from './docStructureTree'

const props = defineProps<{ docType: string }>()

const emit = defineEmits<{
  /** 选中的叶子章节列表变化时上抛（已按结构顺序投影） */
  change: [sections: string[]]
}>()

const treeRef = ref<InstanceType<typeof ElTree>>()
const treeData = computed(() => buildDocStructure(props.docType))
const defaultChecked = computed(() => defaultCheckedKeys(treeData.value))

function currentSections(): string[] {
  // getCheckedKeys(true)：仅返回叶子节点（el-tree leafOnly），与投影语义一致
  const leaves = (treeRef.value?.getCheckedKeys(true) as string[]) || []
  const checked = new Set(leaves)
  return projectedSections(treeData.value, checked)
}

function emitChange() {
  emit('change', currentSections())
}

function onCheck() {
  emitChange()
}

// 文档类型切换时重建结构并广播默认全选结果
watch(
  () => props.docType,
  () => {
    // 等下一拍 el-tree 用新 default-checked-keys 重渲染后再投影
    setTimeout(emitChange, 0)
  },
)

// 初始化即广播默认全选（需求 1.2）
watch(
  defaultChecked,
  () => {
    emit('change', defaultChecked.value)
  },
  { immediate: true },
)

defineExpose({ currentSections })
</script>

<style scoped>
.doc-structure-tree__hint {
  margin: 0 0 12px;
  color: var(--el-text-color-secondary);
  font-size: 13px;
}
</style>
