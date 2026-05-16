<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="680px"
    append-to-body
    destroy-on-close
    @close="onCancel"
  >
    <!-- 搜索栏 -->
    <div class="gt-kp-search">
      <el-input
        v-model="keyword"
        placeholder="搜索知识库文档..."
        clearable
        size="default"
        @keyup.enter="onSearch"
      >
        <template #prefix>🔍</template>
      </el-input>
      <el-button type="primary" @click="onSearch" :loading="searching" style="margin-left: 8px">
        搜索
      </el-button>
    </div>

    <!-- 文档列表 -->
    <div class="gt-kp-list">
      <el-table
        v-if="docList.length"
        :data="docList"
        size="small"
        border
        stripe
        max-height="360"
        @selection-change="onSelectionChange"
        ref="tableRef"
      >
        <el-table-column type="selection" width="40" :selectable="canSelect" />
        <el-table-column prop="name" label="文档名称" min-width="200" show-overflow-tooltip />
        <el-table-column label="分类" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" type="info">{{ row.category || row.folder_name || '—' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="60" align="center">
          <template #default="{ row }">
            {{ row.file_type || '—' }}
          </template>
        </el-table-column>
        <el-table-column label="摘要" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-kp-snippet">{{ row.snippet || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-empty
        v-if="searched && !searching && docList.length === 0"
        description="未找到匹配的文档"
        :image-size="60"
      />

      <div v-if="!searched && !searching" class="gt-kp-hint">
        输入关键词搜索知识库文档，选择后可作为 AI 参考上下文
      </div>

      <div v-if="searching" class="gt-kp-loading">
        <el-icon class="is-loading" style="font-size: 20px /* allow-px: special */; margin-right: 8px"><Loading /></el-icon>
        搜索中...
      </div>
    </div>

    <!-- 已选计数 -->
    <div v-if="selectedDocs.length" class="gt-kp-selected-info">
      已选 {{ selectedDocs.length }} / {{ maxSelect }} 个文档
    </div>

    <template #footer>
      <el-button @click="onCancel">取消</el-button>
      <el-button type="primary" @click="onConfirm" :disabled="selectedDocs.length === 0">
        确认选择 ({{ selectedDocs.length }})
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Loading } from '@element-plus/icons-vue'
import { useKnowledge, knowledgePickerOptions, _resolvePickerSelection, _rejectPickerSelection } from '@/composables/useKnowledge'
import type { KnowledgeDoc } from '@/composables/useKnowledge'

const visible = defineModel<boolean>('visible', { default: false })
const route = useRoute()

const { search: doSearch } = useKnowledge()

/** 当前底稿上下文（wp_code + account_name），注入搜索请求 */
const currentContext = computed(() => {
  const wpCode = route.query.wp_code as string || ''
  const accountName = route.query.account_name as string || ''
  return [wpCode, accountName].filter(Boolean).join(' ')
})

const keyword = ref('')
const searching = ref(false)
const searched = ref(false)
const docList = ref<KnowledgeDoc[]>([])
const selectedDocs = ref<KnowledgeDoc[]>([])
const tableRef = ref<any>(null)

const maxSelect = computed(() => knowledgePickerOptions.value?.maxSelect || 5)
const dialogTitle = computed(() => knowledgePickerOptions.value?.title || '选择知识库文档')

function canSelect(_row: KnowledgeDoc, _index: number): boolean {
  // 如果已达上限，只允许取消已选的
  if (selectedDocs.value.length >= maxSelect.value) {
    return selectedDocs.value.some(d => d.id === _row.id)
  }
  return true
}

function onSelectionChange(rows: KnowledgeDoc[]) {
  selectedDocs.value = rows.slice(0, maxSelect.value)
}

async function onSearch() {
  if (!keyword.value.trim()) return
  searching.value = true
  searched.value = true
  selectedDocs.value = []
  try {
    const category = knowledgePickerOptions.value?.category
    docList.value = await doSearch(keyword.value, category, currentContext.value)
  } finally {
    searching.value = false
  }
}

function onConfirm() {
  _resolvePickerSelection(selectedDocs.value)
  resetState()
}

function onCancel() {
  _rejectPickerSelection()
  resetState()
}

function resetState() {
  keyword.value = ''
  searched.value = false
  docList.value = []
  selectedDocs.value = []
}

// 弹窗打开时重置
watch(visible, (v) => {
  if (v) resetState()
})
</script>

<style scoped>
.gt-kp-search {
  display: flex;
  align-items: center;
  margin-bottom: 12px;
}
.gt-kp-list {
  min-height: 200px;
}
.gt-kp-hint {
  text-align: center;
  color: var(--gt-color-text-tertiary);
  font-size: var(--gt-font-size-sm);
  padding: 40px 0;
}
.gt-kp-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 0;
  color: var(--gt-color-text-secondary);
  font-size: var(--gt-font-size-sm);
}
.gt-kp-snippet {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
.gt-kp-selected-info {
  margin-top: 8px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-primary, #6b4c9a);
  font-weight: 500;
}
</style>
