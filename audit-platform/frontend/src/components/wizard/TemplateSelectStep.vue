<template>
  <div class="template-select-step">
    <div class="step-header">
      <h3>选择模板</h3>
      <p class="step-desc">从事务所默认模板或集团定制模板中选择，拉取到项目使用</p>
    </div>

    <!-- 模板类型切换 -->
    <el-radio-group v-model="activeType" class="type-tabs" @change="loadTemplates">
      <el-radio-button value="workpaper_preset">底稿模板</el-radio-button>
      <el-radio-button value="report_soe">报告模板-国企版</el-radio-button>
      <el-radio-button value="report_listed">报告模板-上市版</el-radio-button>
    </el-radio-group>

    <!-- 已选择的模板 -->
    <div v-if="selectedTemplates.length" class="selected-section">
      <h4>已选择的模板 ({{ selectedTemplates.length }})</h4>
      <el-table :data="selectedTemplates" size="small" stripe>
        <el-table-column prop="template_name" label="模板名称" min-width="200" />
        <el-table-column prop="template_type" label="类型" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="(typeTagColor(row.template_type)) || undefined">
              {{ typeLabel(row.template_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="level" label="来源" width="120">
          <template #default="{ row }">
            <el-tag size="small" effect="plain">
              {{ row.level === 'firm_default' ? '事务所默认' : row.group_name || '集团定制' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="联动状态" width="180">
          <template #default="{ row }">
            <span class="link-status">
              <el-icon v-if="row.linked_trial_balance" color="#67c23a"><Check /></el-icon>
              <el-icon v-else color="#c0c4cc"><Close /></el-icon>
              试算表
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 可用模板列表 -->
    <div class="available-section">
      <div class="section-header">
        <h4>可用模板</h4>
        <el-input
          v-model="searchKeyword"
          placeholder="搜索模板名称/编号"
          clearable
          style="width: 240px"
          :prefix-icon="Search"
        />
      </div>

      <el-table
        v-loading="loading"
        :data="filteredTemplates"
        size="small"
        stripe
        max-height="400"
        @selection-change="onSelectionChange"
      >
        <el-table-column type="selection" width="40" />
        <el-table-column prop="name" label="模板名称" min-width="200" />
        <el-table-column prop="wp_code" label="编号" width="80" />
        <el-table-column prop="audit_cycle" label="循环" width="60" />
        <el-table-column prop="level_label" label="来源" width="120">
          <template #default="{ row }">
            <el-tag size="small" :type="(row.level === 'firm_default' ? '' : 'warning') || undefined" effect="plain">
              {{ row.level_label }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="report_scope" label="口径" width="80">
          <template #default="{ row }">
            {{ row.report_scope === 'consolidated' ? '合并' : row.report_scope === 'standalone' ? '单体' : '' }}
          </template>
        </el-table-column>
        <el-table-column prop="description" label="说明" min-width="150" show-overflow-tooltip />
      </el-table>

      <div class="action-bar" v-if="batchSelection.length">
        <el-button type="primary" @click="batchSelect" :loading="selecting">
          选择 {{ batchSelection.length }} 个模板
        </el-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { Search, Check, Close } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { handleApiError } from '@/utils/errorHandler'
import {
  getAvailableTemplates,
  getProjectTemplates,
  selectTemplateForProject,
  type TemplateLibraryItem,
  type ProjectTemplateSelection,
} from '@/services/commonApi'
import { useWizardStore } from '@/stores/wizard'

const props = defineProps<{ projectId?: string }>()
const wizardStore = useWizardStore()

const activeType = ref('workpaper_preset')
const loading = ref(false)
const selecting = ref(false)
const searchKeyword = ref('')
const availableTemplates = ref<TemplateLibraryItem[]>([])
const selectedTemplates = ref<ProjectTemplateSelection[]>([])
const batchSelection = ref<TemplateLibraryItem[]>([])

const projectId = computed(() => props.projectId || wizardStore.projectId || '')

const filteredTemplates = computed(() => {
  if (!searchKeyword.value) return availableTemplates.value
  const kw = searchKeyword.value.toLowerCase()
  return availableTemplates.value.filter(
    t => t.name.toLowerCase().includes(kw) || (t.wp_code || '').toLowerCase().includes(kw)
  )
})

function typeLabel(type: string) {
  const map: Record<string, string> = {
    workpaper_preset: '底稿',
    workpaper_custom: '底稿(自定义)',
    report_soe: '报告-国企',
    report_listed: '报告-上市',
  }
  return map[type] || type
}

function typeTagColor(type: string) {
  if (type.startsWith('report')) return 'warning'
  return ''
}

async function loadTemplates() {
  loading.value = true
  try {
    availableTemplates.value = await getAvailableTemplates({ template_type: activeType.value })
  } catch {
    availableTemplates.value = []
  } finally {
    loading.value = false
  }
}

async function loadSelected() {
  if (!projectId.value) return
  try {
    selectedTemplates.value = await getProjectTemplates(projectId.value)
  } catch {
    selectedTemplates.value = []
  }
}

function onSelectionChange(rows: TemplateLibraryItem[]) {
  batchSelection.value = rows
}

async function batchSelect() {
  if (!projectId.value) {
    ElMessage.warning('请先创建项目')
    return
  }
  selecting.value = true
  let count = 0
  try {
    for (const tmpl of batchSelection.value) {
      await selectTemplateForProject(projectId.value, tmpl.id)
      count++
    }
    ElMessage.success(`已选择 ${count} 个模板`)
    batchSelection.value = []
    await loadSelected()
  } catch (e: any) {
    handleApiError(e, '选择失败')
  } finally {
    selecting.value = false
  }
}

// 供父组件调用的验证方法
function validate() {
  return true // 模板选择为可选步骤
}

defineExpose({ validate })

onMounted(async () => {
  await loadTemplates()
  await loadSelected()
})
</script>

<style scoped>
.template-select-step {
  padding: 16px 0;
}
.step-header h3 {
  margin: 0 0 4px;
  font-size: var(--gt-font-size-md);
}
.step-desc {
  color: var(--gt-color-info);
  font-size: var(--gt-font-size-sm);
  margin: 0 0 16px;
}
.type-tabs {
  margin-bottom: 16px;
}
.selected-section {
  margin-bottom: 20px;
  padding: 12px;
  background: var(--gt-color-primary-bg);
  border-radius: 8px;
}
.selected-section h4 {
  margin: 0 0 8px;
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-primary, #4b2d77);
}
.available-section {
  margin-top: 12px;
}
.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
.section-header h4 {
  margin: 0;
  font-size: var(--gt-font-size-sm);
}
.action-bar {
  margin-top: 12px;
  text-align: right;
}
.link-status {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-regular);
}
</style>
