<template>
  <div class="note-outline-view">
    <!-- 工具栏 -->
    <div class="note-outline-toolbar">
      <el-input
        v-model="searchText"
        placeholder="搜索章节..."
        size="small"
        clearable
        style="width: 200px"
      />
      <el-select v-model="filterStatus" size="small" placeholder="按状态筛选" clearable style="width: 140px; margin-left: 8px">
        <el-option label="全部" value="" />
        <el-option label="未开始" value="not_started" />
        <el-option label="自动填充" value="auto_filled" />
        <el-option label="编辑中" value="editing" />
        <el-option label="已完成" value="completed" />
        <el-option label="已复核" value="reviewed" />
      </el-select>
      <el-select v-model="sortBy" size="small" style="width: 120px; margin-left: 8px">
        <el-option label="默认排序" value="order" />
        <el-option label="按金额" value="amount" />
      </el-select>
      <div style="flex: 1" />
      <el-button size="small" @click="collapseAll">折叠全部</el-button>
      <el-button size="small" @click="expandAll">展开全部</el-button>
    </div>

    <!-- 大纲列表 -->
    <div class="note-outline-list">
      <div
        v-for="section in filteredSections"
        :key="section.section_code"
        class="note-outline-item"
        :class="{ 'is-collapsed': collapsedSet.has(section.section_code) }"
        @click="$emit('jump', section.section_code)"
      >
        <div class="note-outline-header">
          <el-icon
            class="note-outline-toggle"
            @click.stop="toggleCollapse(section.section_code)"
          >
            <component :is="collapsedSet.has(section.section_code) ? 'ArrowRight' : 'ArrowDown'" />
          </el-icon>
          <span class="note-outline-title">{{ section.title }}</span>
          <el-tag
            v-if="section.completion_status"
            :type="statusTagType(section.completion_status)"
            size="small"
            style="margin-left: 8px"
          >
            {{ statusLabel(section.completion_status) }}
          </el-tag>
          <span class="note-outline-amount gt-amt">
            {{ formatTotalAmount(section.total_amount) }}
          </span>
        </div>
        <div v-if="!collapsedSet.has(section.section_code)" class="note-outline-summary">
          {{ section.summary || '—' }}
        </div>
      </div>

      <div v-if="filteredSections.length === 0" class="note-outline-empty">
        暂无匹配的章节
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { ArrowRight, ArrowDown } from '@element-plus/icons-vue'

interface NoteSection {
  section_code: string
  title: string
  summary?: string
  total_amount?: number
  completion_status?: string
  sort_order?: number
}

const props = defineProps<{
  sections: NoteSection[]
}>()

defineEmits<{
  jump: [sectionCode: string]
}>()

const searchText = ref('')
const filterStatus = ref('')
const sortBy = ref('order')
const collapsedSet = ref<Set<string>>(new Set())

const filteredSections = computed(() => {
  let list = [...props.sections]

  // 搜索过滤
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    list = list.filter(s => s.title.toLowerCase().includes(q))
  }

  // 状态过滤
  if (filterStatus.value) {
    list = list.filter(s => s.completion_status === filterStatus.value)
  }

  // 排序
  if (sortBy.value === 'amount') {
    list.sort((a, b) => Math.abs(b.total_amount || 0) - Math.abs(a.total_amount || 0))
  } else {
    list.sort((a, b) => (a.sort_order || 0) - (b.sort_order || 0))
  }

  return list
})

function toggleCollapse(code: string) {
  if (collapsedSet.value.has(code)) {
    collapsedSet.value.delete(code)
  } else {
    collapsedSet.value.add(code)
  }
}

function collapseAll() {
  collapsedSet.value = new Set(props.sections.map(s => s.section_code))
}

function expandAll() {
  collapsedSet.value = new Set()
}

function formatTotalAmount(amount?: number): string {
  if (amount == null || amount === 0) return ''
  return amount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(status: string): 'info' | 'primary' | 'warning' | 'success' | 'danger' {
  const map: Record<string, 'info' | 'primary' | 'warning' | 'success' | 'danger'> = {
    not_started: 'info',
    auto_filled: 'primary',
    editing: 'warning',
    completed: 'success',
    reviewed: 'success',
  }
  return map[status] || 'info'
}

function statusLabel(status: string): string {
  const map: Record<string, string> = {
    not_started: '未开始',
    auto_filled: '自动填充',
    editing: '编辑中',
    completed: '已完成',
    reviewed: '已复核',
  }
  return map[status] || status
}
</script>

<style scoped>
.note-outline-view {
  height: 100%;
  display: flex;
  flex-direction: column;
}

.note-outline-toolbar {
  display: flex;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  flex-shrink: 0;
}

.note-outline-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.note-outline-item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: background 0.15s;
  margin-bottom: 4px;
}

.note-outline-item:hover {
  background: var(--el-fill-color-light);
}

.note-outline-header {
  display: flex;
  align-items: center;
  gap: 6px;
}

.note-outline-toggle {
  cursor: pointer;
  color: var(--el-text-color-secondary);
  flex-shrink: 0;
}

.note-outline-title {
  font-weight: 500;
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-outline-amount {
  font-family: 'Arial Narrow', Arial, sans-serif;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
  color: var(--el-text-color-regular);
  font-size: 13px;
}

.note-outline-summary {
  margin-top: 4px;
  padding-left: 22px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.note-outline-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--el-text-color-placeholder);
}
</style>
