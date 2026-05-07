<template>
  <div class="gt-template-list">
    <div class="gt-page-header">
      <h2 class="gt-page-title">自定义模板管理</h2>
      <div class="gt-header-actions">
        <el-select v-model="filterCategory" placeholder="分类筛选" clearable size="small" style="width: 140px" @change="loadTemplates">
          <el-option label="行业专用" value="industry" />
          <el-option label="客户专用" value="client" />
          <el-option label="个人收藏" value="personal" />
        </el-select>
        <el-button type="primary" size="small" @click="$router.push('/extension/custom-templates/new')">
          <el-icon><Plus /></el-icon> 新建模板
        </el-button>
      </div>
    </div>

    <el-table :data="templates" v-loading="loading" stripe size="small" style="width: 100%">
      <el-table-column prop="template_name" label="模板名称" min-width="200" show-overflow-tooltip />
      <el-table-column prop="category" label="分类" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="(categoryTag(row.category)) || undefined">{{ categoryLabel(row.category) }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="version" label="版本" width="80" align="center" />
      <el-table-column prop="is_published" label="发布状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag size="small" :type="row.is_published ? 'success' : 'info'">
            {{ row.is_published ? '已发布' : '未发布' }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="updated_at" label="更新时间" width="140">
        <template #default="{ row }">{{ fmtDate(row.updated_at) }}</template>
      </el-table-column>
      <el-table-column label="操作" width="220" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" size="small" @click="editTemplate(row)">编辑</el-button>
          <el-button link type="primary" size="small" @click="validateTemplate(row)" :loading="row._validating">验证</el-button>
          <el-button link type="success" size="small" @click="publishTemplate(row)" v-if="!row.is_published">发布</el-button>
          <el-button link type="danger" size="small" @click="deleteTemplate(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { Plus } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { confirmDelete, confirmDangerous } from '@/utils/confirm'
import {
  listCustomTemplates, validateCustomTemplate as validateTpl,
  publishCustomTemplate, deleteCustomTemplate,
} from '@/services/commonApi'

const router = useRouter()
const loading = ref(false)
const templates = ref<any[]>([])
const filterCategory = ref('')

async function loadTemplates() {
  loading.value = true
  try {
    const params: any = {}
    if (filterCategory.value) params.category = filterCategory.value
    templates.value = (await listCustomTemplates(params)).map((t: any) => ({ ...t, _validating: false }))
  } catch { templates.value = [] }
  finally { loading.value = false }
}

function editTemplate(row: any) {
  router.push(`/extension/custom-templates/${row.id}/edit`)
}

async function validateTemplate(row: any) {
  row._validating = true
  try {
    const result = await validateTpl(row.id)
    if (result.valid) ElMessage.success('模板验证通过')
    else ElMessage.warning(`验证发现 ${result.issues?.length || 0} 个问题`)
  } catch { ElMessage.error('验证失败') }
  finally { row._validating = false }
}

async function publishTemplate(row: any) {
  try {
    await confirmDangerous('确认发布此模板？发布后其他用户可在模板市场中使用。', '发布确认')
    await publishCustomTemplate(row.id)
    ElMessage.success('发布成功')
    loadTemplates()
  } catch { /* cancelled or error */ }
}

async function deleteTemplate(row: any) {
  try {
    await confirmDelete('此模板')
    await deleteCustomTemplate(row.id)
    ElMessage.success('已删除')
    loadTemplates()
  } catch { /* cancelled */ }
}

function categoryTag(c: string): 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined {
  const m: Record<string, 'success' | 'warning' | 'info' | 'danger' | 'primary' | undefined> = { industry: undefined, client: 'success', personal: 'warning' }
  return m[c] || 'info'
}
function categoryLabel(c: string) {
  const m: Record<string, string> = { industry: '行业专用', client: '客户专用', personal: '个人收藏' }
  return m[c] || c
}
function fmtDate(d: string) {
  return d ? new Date(d).toLocaleDateString('zh-CN') : '-'
}

onMounted(loadTemplates)
</script>

<style scoped>
.gt-template-list { padding: var(--gt-space-4); }
.gt-page-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: var(--gt-space-4);
}
.gt-page-title { font-size: var(--gt-font-size-xl); font-weight: 600; margin: 0; }
.gt-header-actions { display: flex; gap: var(--gt-space-2); align-items: center; }
</style>
