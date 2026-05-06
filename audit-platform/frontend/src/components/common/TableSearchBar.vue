<template>
  <Transition name="gt-slide-down">
    <div v-if="isVisible" class="gt-search-bar">
      <div class="gt-search-bar-row">
        <div class="gt-search-bar-icon">🔍</div>
        <el-input
          ref="inputRef"
          :model-value="keyword"
          @update:model-value="$emit('update:keyword', $event)"
          size="small"
          placeholder="输入关键词搜索表格内容..."
          clearable
          class="gt-search-input"
          @keyup.enter.exact="$emit('next')"
          @keyup.enter.shift="$emit('prev')"
          @keyup.escape="$emit('close')"
        />
        <span v-if="keyword" class="gt-search-info">{{ matchInfo }}</span>
        <el-button-group size="small" class="gt-search-nav">
          <el-button @click="$emit('prev')" :disabled="!hasMatches" title="上一个 (Shift+Enter)">
            <span style="font-size:12px">▲</span>
          </el-button>
          <el-button @click="$emit('next')" :disabled="!hasMatches" title="下一个 (Enter)">
            <span style="font-size:12px">▼</span>
          </el-button>
        </el-button-group>
        <el-checkbox :model-value="caseSensitive" @update:model-value="$emit('update:caseSensitive', !!$event); $emit('search')" size="small" class="gt-search-case">Aa</el-checkbox>
        <el-button v-if="showReplace" size="small" class="gt-search-replace-btn" @click="replaceVisible = !replaceVisible">
          {{ replaceVisible ? '收起' : '替换' }}
        </el-button>
        <div class="gt-search-close" @click="$emit('close')" title="关闭 (Esc)">✕</div>
      </div>
      <div v-if="replaceVisible && showReplace" class="gt-search-bar-row">
        <div class="gt-search-bar-icon" style="opacity:0">🔍</div>
        <el-input
          :model-value="replaceText"
          @update:model-value="$emit('update:replaceText', $event)"
          size="small"
          placeholder="替换为..."
          clearable
          class="gt-search-input"
        />
        <el-button size="small" @click="$emit('replace-one')" :disabled="!hasMatches" class="gt-search-action-btn">替换</el-button>
        <el-button size="small" @click="$emit('replace-all')" :disabled="!hasMatches" class="gt-search-action-btn">全部</el-button>
      </div>
    </div>
  </Transition>
</template>

<script setup lang="ts">
import { ref, watch, nextTick } from 'vue'

const props = defineProps<{
  isVisible: boolean
  keyword: string
  replaceText?: string
  matchInfo: string
  hasMatches: boolean
  caseSensitive: boolean
  showReplace?: boolean
}>()

defineEmits<{
  'update:keyword': [value: string]
  'update:replaceText': [value: string]
  'update:caseSensitive': [value: boolean]
  search: []
  next: []
  prev: []
  close: []
  'replace-one': []
  'replace-all': []
}>()

const inputRef = ref<any>(null)
const replaceVisible = ref(false)

// 打开时自动聚焦
watch(() => props.isVisible, (v) => {
  if (v) nextTick(() => inputRef.value?.focus())
})
</script>

<style scoped>
.gt-search-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #f5f0ff 0%, #ece6f5 100%);
  border: 1px solid #d8d0e8;
  border-radius: 8px;
  box-shadow: 0 2px 12px rgba(75, 45, 119, 0.12);
  margin-bottom: 10px;
}
.gt-search-bar-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.gt-search-bar-icon {
  font-size: 16px;
  flex-shrink: 0;
  width: 24px;
  text-align: center;
}
.gt-search-input {
  width: 280px;
  flex-shrink: 0;
}
.gt-search-input :deep(.el-input__wrapper) {
  border-radius: 6px;
  box-shadow: 0 0 0 1px #d0c4e4 inset;
  background: #fff;
}
.gt-search-input :deep(.el-input__wrapper:focus-within) {
  box-shadow: 0 0 0 2px var(--gt-color-primary, #4b2d77) inset;
}
.gt-search-input :deep(.el-input__inner) {
  font-size: 13px;
}
.gt-search-info {
  font-size: 12px;
  color: var(--gt-color-primary, #4b2d77);
  font-weight: 600;
  min-width: 60px;
  white-space: nowrap;
  background: rgba(75, 45, 119, 0.08);
  padding: 2px 8px;
  border-radius: 4px;
}
.gt-search-nav :deep(.el-button) {
  padding: 4px 8px;
  background: rgba(75, 45, 119, 0.06);
  border-color: #d0c4e4;
  color: #4b2d77;
}
.gt-search-nav :deep(.el-button:hover) {
  background: rgba(75, 45, 119, 0.12);
}
.gt-search-case {
  font-size: 11px;
}
.gt-search-case :deep(.el-checkbox__label) {
  font-size: 11px;
  color: #666;
  padding-left: 4px;
}
.gt-search-replace-btn {
  background: transparent;
  border-color: #d0c4e4;
  color: #4b2d77;
  font-size: 12px;
}
.gt-search-action-btn {
  background: var(--gt-color-primary, #4b2d77);
  border-color: var(--gt-color-primary, #4b2d77);
  color: #fff;
  font-size: 12px;
}
.gt-search-close {
  cursor: pointer;
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  color: #999;
  font-size: 14px;
  transition: all 0.15s;
  flex-shrink: 0;
}
.gt-search-close:hover {
  background: rgba(75, 45, 119, 0.1);
  color: #4b2d77;
}
.gt-slide-down-enter-active { transition: all 0.25s cubic-bezier(0.22, 1, 0.36, 1); }
.gt-slide-down-leave-active { transition: all 0.15s ease; }
.gt-slide-down-enter-from { opacity: 0; transform: translateY(-12px); }
.gt-slide-down-leave-to { opacity: 0; transform: translateY(-6px); }
</style>
