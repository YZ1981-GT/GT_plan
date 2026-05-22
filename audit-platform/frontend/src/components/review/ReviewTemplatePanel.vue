<template>
  <el-drawer
    :model-value="visible"
    title="复核意见模板库"
    direction="rtl"
    size="420px"
    @update:model-value="$emit('update:visible', $event)"
  >
    <!-- 搜索 + 过滤 -->
    <div class="template-filters">
      <el-input
        v-model="searchText"
        placeholder="搜索模板..."
        clearable
        size="small"
        prefix-icon="Search"
        style="margin-bottom: 8px"
      />
      <div class="filter-row">
        <el-select
          v-model="filterCycle"
          placeholder="循环过滤"
          clearable
          size="small"
          style="width: 120px"
        >
          <el-option
            v-for="c in cycleOptions"
            :key="c"
            :label="c + ' 循环'"
            :value="c"
          />
        </el-select>
        <el-radio-group v-model="filterTag" size="small">
          <el-radio-button value="">全部</el-radio-button>
          <el-radio-button value="must_fix">必改</el-radio-button>
          <el-radio-button value="suggest">建议</el-radio-button>
          <el-radio-button value="info">参考</el-radio-button>
        </el-radio-group>
      </div>
    </div>

    <!-- 模板列表 -->
    <div class="template-list">
      <div
        v-for="tpl in filteredTemplates"
        :key="tpl.id"
        class="template-card"
        @click="onSelectTemplate(tpl)"
      >
        <div class="template-header">
          <span class="template-title">{{ tpl.title }}</span>
          <el-tag
            :type="tagType(tpl.priority_tag)"
            size="small"
          >
            {{ tagLabel(tpl.priority_tag) }}
          </el-tag>
        </div>
        <div class="template-content">{{ tpl.content }}</div>
        <div class="template-meta">
          <span class="cycles">{{ (tpl.applicable_cycles || []).join(', ') }}</span>
          <span class="use-count">已使用 {{ tpl.use_count }} 次</span>
        </div>
      </div>
      <el-empty v-if="filteredTemplates.length === 0" description="暂无匹配模板" />
    </div>
  </el-drawer>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api } from '@/services/apiProxy'

interface ReviewTemplate {
  id: string
  title: string
  content: string
  applicable_cycles: string[]
  priority_tag: string
  use_count: number
  created_at: string
  updated_at: string
}

const props = defineProps<{
  visible: boolean
  currentCycle?: string
}>()

const emit = defineEmits<{
  (e: 'insert', content: string): void
  (e: 'update:visible', val: boolean): void
}>()

const searchText = ref('')
const filterCycle = ref(props.currentCycle || '')
const filterTag = ref('')
const templates = ref<ReviewTemplate[]>([])

const cycleOptions = ['D', 'E', 'F', 'G', 'H', 'I', 'J', 'K', 'L', 'M', 'N']

const filteredTemplates = computed(() => {
  let result = templates.value
  if (searchText.value) {
    const q = searchText.value.toLowerCase()
    result = result.filter(
      t => t.title.toLowerCase().includes(q) || t.content.toLowerCase().includes(q)
    )
  }
  if (filterCycle.value) {
    result = result.filter(t =>
      (t.applicable_cycles || []).includes(filterCycle.value)
    )
  }
  if (filterTag.value) {
    result = result.filter(t => t.priority_tag === filterTag.value)
  }
  return result
})

function tagType(tag: string) {
  switch (tag) {
    case 'must_fix': return 'danger'
    case 'suggest': return 'warning'
    case 'info': return 'info'
    default: return 'info'
  }
}

function tagLabel(tag: string) {
  switch (tag) {
    case 'must_fix': return '必改'
    case 'suggest': return '建议'
    case 'info': return '参考'
    default: return tag
  }
}

async function loadTemplates() {
  try {
    const params: Record<string, string> = {}
    const res = await api.get('/api/review-templates', { params })
    templates.value = res.data || res
  } catch {
    templates.value = []
  }
}

async function onSelectTemplate(tpl: ReviewTemplate) {
  emit('insert', tpl.content)
  // Increment use count
  try {
    await api.post(`/api/review-templates/${tpl.id}/use`)
    tpl.use_count += 1
  } catch {
    // non-critical
  }
}

onMounted(() => {
  loadTemplates()
})
</script>

<style scoped>
.template-filters {
  padding: 0 0 12px;
  border-bottom: 1px solid var(--el-border-color-lighter);
  margin-bottom: 12px;
}
.filter-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.template-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.template-card {
  padding: 12px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.template-card:hover {
  border-color: var(--el-color-primary);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}
.template-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.template-title {
  font-weight: 500;
  font-size: 14px;
}
.template-content {
  font-size: 13px;
  color: var(--el-text-color-secondary);
  line-height: 1.5;
  margin-bottom: 6px;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.template-meta {
  display: flex;
  justify-content: space-between;
  font-size: 12px;
  color: var(--el-text-color-placeholder);
}
</style>
