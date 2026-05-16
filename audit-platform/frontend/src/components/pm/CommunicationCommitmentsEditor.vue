<template>
  <div class="commitments-editor">
    <div class="commitments-header">
      <span class="commitments-label">承诺事项</span>
      <el-button v-if="!readonly" size="small" type="primary" link @click="addItem">+ 添加承诺</el-button>
    </div>
    <div v-if="items.length === 0" class="commitments-empty">
      {{ readonly ? '暂无承诺事项' : '暂无承诺事项，点击"添加承诺"录入' }}
    </div>
    <div v-for="(item, index) in items" :key="index" class="commitment-row">
      <el-input
        v-model="item.content"
        placeholder="承诺内容，如：本周五前提供银行询证函回函"
        class="commitment-content"
        :disabled="readonly"
        @input="emitChange"
      />
      <el-date-picker
        v-model="item.due_date"
        type="date"
        value-format="YYYY-MM-DD"
        placeholder="到期日"
        class="commitment-date"
        :disabled="readonly"
        @change="emitChange"
      />
      <el-button
        v-if="!readonly"
        size="small"
        type="danger"
        link
        class="commitment-remove"
        @click="removeItem(index)"
      >
        删除
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

export interface CommitmentItem {
  content: string
  due_date: string | null
}

const props = defineProps<{
  modelValue: CommitmentItem[]
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'update:modelValue', value: CommitmentItem[]): void
}>()

const items = ref<CommitmentItem[]>([...props.modelValue])

watch(
  () => props.modelValue,
  (val) => {
    items.value = [...val]
  },
  { deep: true }
)

function addItem() {
  items.value.push({ content: '', due_date: null })
  emitChange()
}

function removeItem(index: number) {
  items.value.splice(index, 1)
  emitChange()
}

function emitChange() {
  emit('update:modelValue', items.value.filter(i => i.content.trim() !== ''))
}
</script>

<style scoped>
.commitments-editor {
  width: 100%;
}

.commitments-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.commitments-label {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
  font-weight: 500;
}

.commitments-empty {
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-xs);
  padding: 8px 0;
}

.commitment-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
}

.commitment-content {
  flex: 1;
  min-width: 0;
}

.commitment-date {
  width: 160px;
  flex-shrink: 0;
}

.commitment-remove {
  flex-shrink: 0;
}
</style>
