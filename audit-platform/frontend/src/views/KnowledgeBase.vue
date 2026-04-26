<template>
  <div class="gt-knowledge">
    <div class="gt-kb-header">
      <h2>知识库</h2>
      <el-button size="small" type="primary" @click="refresh" :loading="loading">
        <el-icon><Refresh /></el-icon> 刷新
      </el-button>
    </div>

    <!-- 全局 / 项目 Tab 切换 -->
    <el-tabs v-model="activeTab" @tab-change="onTabChange">
      <el-tab-pane label="全局知识库" name="global">
        <p class="gt-kb-desc">所有项目共享的参考资料（会计准则、监管规定、行业指引等）</p>
      </el-tab-pane>
      <el-tab-pane label="项目知识库" name="project">
        <p class="gt-kb-desc">
          项目专属文档（底稿、附注、工作记录等）
          <el-select
            v-model="selectedProjectId"
            placeholder="选择项目"
            size="small"
            filterable
            style="width: 280px; margin-left: 12px"
            @change="loadProjectDocs"
          >
            <el-option
              v-for="p in projects"
              :key="p.id"
              :label="`${p.client_name || p.name} (${p.audit_year || ''})`"
              :value="p.id"
            />
          </el-select>
        </p>
      </el-tab-pane>
    </el-tabs>

    <!-- 全局知识库：分类卡片 -->
    <template v-if="activeTab === 'global'">
      <div class="gt-kb-grid">
        <div
          v-for="lib in libraries"
          :key="lib.key"
          class="gt-kb-card"
          :class="{ 'gt-kb-card--active': selectedCategory === lib.key }"
          @click="selectCategory(lib.key)"
        >
          <div class="gt-kb-card-icon">{{ lib.icon }}</div>
          <div class="gt-kb-card-info">
            <div class="gt-kb-card-name">{{ lib.name }}</div>
            <div class="gt-kb-card-count">{{ lib.doc_count ?? 0 }} 个文档</div>
          </div>
        </div>
      </div>
    </template>

    <!-- 文档列表（全局分类 或 项目级） -->
    <div v-if="showDocList" class="gt-kb-detail">
      <div class="gt-kb-detail-header">
        <h3>{{ docListTitle }}</h3>
        <el-upload :auto-upload="false" :show-file-list="false" @change="onUpload">
          <el-button size="small" type="primary">上传文档</el-button>
        </el-upload>
      </div>

      <el-table :data="documents" stripe size="small" v-loading="docLoading">
        <el-table-column prop="name" label="文档名称" min-width="250" show-overflow-tooltip />
        <el-table-column label="大小" width="100" align="right">
          <template #default="{ row }">{{ formatSize(row.size) }}</template>
        </el-table-column>
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ formatTime(row.modified_at) }}</template>
        </el-table-column>
        <el-table-column label="操作" width="160" align="center">
          <template #default="{ row }">
            <el-button size="small" @click="onDownload(row.name)">下载</el-button>
            <el-button type="danger" size="small" text @click="onDelete(row.name)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-empty v-if="!docLoading && documents.length === 0" description="暂无文档，点击上传添加" />
    </div>

    <!-- 项目未选择提示 -->
    <el-empty
      v-if="activeTab === 'project' && !selectedProjectId"
      description="请先选择一个项目"
      style="margin-top: 40px"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh } from '@element-plus/icons-vue'
import {
  listProjects, listKnowledgeLibraries, listKnowledgeDocs,
  uploadKnowledgeDoc, downloadKnowledgeDoc, deleteKnowledgeDoc,
} from '@/services/commonApi'

interface Library { key: string; name: string; icon: string; doc_count: number; description?: string }

const loading = ref(false)
const docLoading = ref(false)
const activeTab = ref('global')
const selectedCategory = ref('')
const selectedProjectId = ref('')
const documents = ref<any[]>([])
const projects = ref<any[]>([])

const libraries = ref<Library[]>([])

const showDocList = computed(() => {
  if (activeTab.value === 'global') return !!selectedCategory.value
  return !!selectedProjectId.value
})

const docListTitle = computed(() => {
  if (activeTab.value === 'global') {
    const lib = libraries.value.find(l => l.key === selectedCategory.value)
    return lib?.name || selectedCategory.value
  }
  const proj = projects.value.find(p => p.id === selectedProjectId.value)
  return proj ? `${proj.client_name || proj.name} — 项目文档` : '项目文档'
})

// 当前文档操作的 API 基础路径
function docApiBase(): string {
  if (activeTab.value === 'global') {
    return `/api/knowledge/${selectedCategory.value}/documents`
  }
  return `/api/projects/${selectedProjectId.value}/knowledge/documents`
}

async function loadLibraries() {
  loading.value = true
  try {
    libraries.value = await listKnowledgeLibraries()
  } catch {
    // 降级使用默认分类
    libraries.value = [
      { key: 'workpaper_templates', name: '底稿模板库', icon: '📋', doc_count: 0 },
      { key: 'regulations', name: '监管规定库', icon: '⚖️', doc_count: 0 },
      { key: 'accounting_standards', name: '会计准则库', icon: '📖', doc_count: 0 },
      { key: 'quality_control', name: '质控标准库', icon: '✅', doc_count: 0 },
      { key: 'audit_procedures', name: '审计程序库', icon: '📝', doc_count: 0 },
      { key: 'industry_guides', name: '行业指引库', icon: '🏭', doc_count: 0 },
      { key: 'prompts', name: '提示词库', icon: '💡', doc_count: 0 },
      { key: 'report_templates', name: '报告模板库', icon: '📄', doc_count: 0 },
      { key: 'notes', name: '笔记库', icon: '📌', doc_count: 0 },
    ]
  } finally {
    loading.value = false
  }
}

async function loadProjectList() {
  try {
    projects.value = await listProjects()
  } catch {
    projects.value = []
  }
}

async function selectCategory(key: string) {
  selectedCategory.value = key
  await loadDocuments()
}

async function loadProjectDocs() {
  if (!selectedProjectId.value) return
  await loadDocuments()
}

async function loadDocuments() {
  docLoading.value = true
  documents.value = []
  try {
    documents.value = await listKnowledgeDocs(docApiBase())
  } catch {
    documents.value = []
  } finally {
    docLoading.value = false
  }
}

async function onUpload(file: any) {
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    await uploadKnowledgeDoc(docApiBase(), formData)
    ElMessage.success('上传成功')
    await loadDocuments()
    if (activeTab.value === 'global') await loadLibraries()
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '上传失败')
  }
}

async function onDownload(name: string) {
  try {
    const blob = await downloadKnowledgeDoc(docApiBase(), name)
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = name
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    ElMessage.error('下载失败')
  }
}

async function onDelete(name: string) {
  await ElMessageBox.confirm(`确定删除「${name}」？`, '删除确认', { type: 'warning' })
  try {
    await deleteKnowledgeDoc(docApiBase(), name)
    ElMessage.success('已删除')
    await loadDocuments()
    if (activeTab.value === 'global') await loadLibraries()
  } catch {
    ElMessage.error('删除失败')
  }
}

function onTabChange() {
  documents.value = []
  selectedCategory.value = ''
}

async function refresh() {
  await loadLibraries()
  if (activeTab.value === 'project') await loadProjectList()
  if (showDocList.value) await loadDocuments()
}

function formatSize(bytes: number) {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + 'B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + 'KB'
  return (bytes / 1024 / 1024).toFixed(1) + 'MB'
}

function formatTime(t: string | null) {
  if (!t) return '—'
  return t.slice(0, 19).replace('T', ' ')
}

onMounted(async () => {
  await loadLibraries()
  await loadProjectList()
})
</script>

<style scoped>
.gt-knowledge { padding: 20px; }
.gt-kb-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
.gt-kb-header h2 { margin: 0; font-size: 20px; color: #333; }
.gt-kb-desc { color: #888; font-size: 13px; margin: 0 0 16px; display: flex; align-items: center; }

.gt-kb-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 12px; margin-bottom: 24px;
}
.gt-kb-card {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; border: 1px solid #eee; border-radius: 8px;
  cursor: pointer; transition: all 0.2s; background: #fff;
}
.gt-kb-card:hover { border-color: var(--gt-color-primary, #4b2d77); box-shadow: 0 2px 8px rgba(75,45,119,0.08); }
.gt-kb-card--active {
  border-color: var(--gt-color-primary, #4b2d77);
  background: #f5f0ff;
  box-shadow: 0 2px 8px rgba(75,45,119,0.12);
}
.gt-kb-card-icon { font-size: 28px; }
.gt-kb-card-name { font-size: 14px; font-weight: 600; color: #333; }
.gt-kb-card-count { font-size: 12px; color: #999; margin-top: 2px; }

.gt-kb-detail { margin-top: 8px; }
.gt-kb-detail-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid #eee;
}
.gt-kb-detail-header h3 { margin: 0; font-size: 16px; color: #333; }
</style>
