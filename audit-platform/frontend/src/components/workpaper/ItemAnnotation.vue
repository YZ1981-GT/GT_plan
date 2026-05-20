<template>
  <div class="gt-item-annotation">
    <div class="gt-item-annotation-list">
      <div
        v-for="(ann, idx) in modelValue || []"
        :key="ann.id || idx"
        class="gt-item-annotation-row"
      >
        <span class="gt-item-annotation-author">{{ ann.author || '匿名' }}</span>
        <span class="gt-item-annotation-text">{{ ann.text }}</span>
        <span class="gt-item-annotation-time">{{ ann.created_at?.slice(0, 10) || '' }}</span>
        <el-button text size="small" type="danger" @click="onDelete(idx)">×</el-button>
      </div>
    </div>
    <div class="gt-item-annotation-input">
      <el-input
        v-model="newComment"
        size="small"
        placeholder="输入批注（按 Enter 发送）"
        @keyup.enter="onAdd"
      >
        <template #append>
          <el-button size="small" @click="onAdd">+</el-button>
        </template>
      </el-input>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ItemAnnotation — 逐项批注组件（Sprint 2 Task 2.24）
 *
 * 锚定 requirements F6.4
 * 数据存放：parsed_data.items[N].annotations[]
 *
 * v-model: ItemAnnotationEntry[]
 */
import { ref } from 'vue'

export interface ItemAnnotationEntry {
  id?: string
  author?: string
  text: string
  created_at?: string
}

interface Props {
  modelValue?: ItemAnnotationEntry[] | null
  author?: string
}
const props = withDefaults(defineProps<Props>(), { modelValue: () => [], author: '当前用户' })
const emit = defineEmits<{ 'update:modelValue': [list: ItemAnnotationEntry[]] }>()

const newComment = ref('')

function onAdd() {
  const text = newComment.value.trim()
  if (!text) return
  const next = [...(props.modelValue || [])]
  next.push({
    id: 'ann-' + Date.now(),
    author: props.author,
    text,
    created_at: new Date().toISOString(),
  })
  emit('update:modelValue', next)
  newComment.value = ''
}

function onDelete(idx: number) {
  const next = [...(props.modelValue || [])]
  next.splice(idx, 1)
  emit('update:modelValue', next)
}
</script>

<style scoped>
.gt-item-annotation {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.gt-item-annotation-list {
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.gt-item-annotation-row {
  display: flex;
  gap: 6px;
  align-items: center;
  font-size: 12px;
  padding: 2px 6px;
  background: var(--gt-color-bg-page, #f8f7fc);
  border-radius: 3px;
}
.gt-item-annotation-author {
  font-weight: 600;
  color: var(--gt-color-primary, #4b2d77);
  min-width: 56px;
}
.gt-item-annotation-text {
  flex: 1;
  color: var(--gt-color-text-regular, #606266);
}
.gt-item-annotation-time {
  font-size: 11px;
  color: var(--gt-color-text-tertiary, #909399);
}
</style>
