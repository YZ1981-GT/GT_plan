<template>
  <div class="gt-knowledge gt-fade-in">
    <!-- 页面横幅 -->
    <div class="gt-kb-banner">
      <div class="gt-kb-banner-text">
        <h2>知识库</h2>
        <p>{{ folderTree.length }} 个分类 · {{ totalDocs }} 个文档</p>
      </div>
      <div class="gt-kb-banner-actions">
        <el-input v-model="searchKeyword" placeholder="搜索文档..." size="small" clearable style="width: 180px"
          @keyup.enter="onSearch" />
        <el-button size="small" @click="onSearch" :loading="searchLoading" round>搜索</el-button>
        <el-button size="small" @click="onCreateFolder" round>新建文件夹</el-button>
        <el-button size="small" @click="onUploadDocs" round>上传文档</el-button>
        <el-button size="small" @click="loadTree" :loading="treeLoading" round>刷新</el-button>
      </div>
    </div>

    <!-- 主体：左树 + 右文档列表 -->
    <el-row :gutter="12" class="gt-kb-body">
      <!-- 左侧：文件夹树 -->
      <el-col :span="7">
        <div class="gt-kb-panel gt-kb-tree-panel">
          <h4 class="gt-kb-panel-title">目录</h4>
          <el-tree
            :data="folderTree"
            :props="{ label: 'name', children: 'children' }"
            node-key="id"
            highlight-current
            default-expand-all
            @node-click="onFolderClick"
          >
            <template #default="{ data }">
              <div class="gt-kb-tree-node" @contextmenu.prevent="onFolderContextMenu(data, $event)">
                <span>{{ data.name }}</span>
                <el-tag v-if="data.category" size="small" type="info" style="margin-left: 4px">预制</el-tag>
                <el-tag v-if="data.access_level === 'project_group'" size="small" type="warning" style="margin-left: 4px">项目组</el-tag>
                <el-tag v-if="data.access_level === 'private'" size="small" type="danger" style="margin-left: 4px">私有</el-tag>
                <span class="gt-kb-doc-count">({{ data.doc_count }})</span>
              </div>
            </template>
          </el-tree>
          <el-empty v-if="!treeLoading && folderTree.length === 0" description="暂无文件夹" :image-size="60" />
        </div>
      </el-col>

      <!-- 右侧：文档列表 -->
      <el-col :span="17">
        <div class="gt-kb-panel gt-kb-doc-panel">
          <div class="gt-kb-doc-header">
            <h4>{{ selectedFolder?.name || '请选择文件夹' }}</h4>
            <el-button v-if="selectedFolder" size="small" type="primary" @click="onUploadToFolder">
              上传到此文件夹
            </el-button>
          </div>
          <el-table v-if="documents.length" :data="documents" size="small" border stripe>
            <el-table-column prop="name" label="文档名称" min-width="250" show-overflow-tooltip />
            <el-table-column prop="file_type" label="类型" width="70" align="center">
              <template #default="{ row }">
                <el-tag size="small">{{ row.file_type || '—' }}</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="大小" width="90" align="right">
              <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
            </el-table-column>
            <el-table-column label="权限" width="80" align="center">
              <template #default="{ row }">
                <el-tag v-if="row.access_level === 'project_group'" size="small" type="warning">项目组</el-tag>
                <el-tag v-else-if="row.access_level === 'private'" size="small" type="danger">私有</el-tag>
                <el-tag v-else size="small" type="success">公开</el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="created_at" label="创建时间" width="110">
              <template #default="{ row }">{{ row.created_at?.slice(0, 10) || '—' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="130" align="center">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="onPreviewDoc(row)">预览</el-button>
                <el-button size="small" link type="warning" @click="onMoveDoc(row)">移动</el-button>
                <el-button size="small" link type="danger" @click="onDeleteDoc(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <el-empty v-if="selectedFolder && !docLoading && documents.length === 0" description="暂无文档" :image-size="60" />
          <div v-if="!selectedFolder" class="gt-kb-placeholder">
            <p>← 请从左侧选择一个文件夹查看文档</p>
          </div>
        </div>
      </el-col>
    </el-row>

    <!-- 新建文件夹弹窗 -->
    <el-dialog v-model="showCreateFolder" title="新建文件夹" width="400px" append-to-body>
      <el-form label-width="80px">
        <el-form-item label="名称">
          <el-input v-model="newFolderName" placeholder="文件夹名称" />
        </el-form-item>
        <el-form-item label="位置">
          <el-select v-model="newFolderParent" placeholder="顶级（根目录）" clearable style="width: 100%">
            <el-option v-for="f in flatFolders" :key="f.id" :label="f.name" :value="f.id" />
          </el-select>
        </el-form-item>
        <el-form-item label="权限">
          <el-radio-group v-model="newFolderAccess">
            <el-radio value="public">公开</el-radio>
            <el-radio value="project_group">项目组</el-radio>
            <el-radio value="private">私有</el-radio>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateFolder = false">取消</el-button>
        <el-button type="primary" @click="doCreateFolder" :disabled="!newFolderName">创建</el-button>
      </template>
    </el-dialog>

    <!-- 上传文档弹窗 -->
    <el-dialog v-model="showUpload" title="上传文档" width="500px" append-to-body>
      <el-upload
        drag
        multiple
        :auto-upload="false"
        v-model:file-list="uploadFiles"
        accept=".pdf,.docx,.doc,.xlsx,.xls,.txt,.md,.pptx"
      >
        <el-icon style="font-size: 40px; color: #c0c4cc"><Upload /></el-icon>
        <div>拖拽文件到此处，或点击选择</div>
        <template #tip>
          <div style="color: #999; font-size: 12px">支持 PDF/Word/Excel/TXT/Markdown</div>
        </template>
      </el-upload>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="doUpload" :loading="uploading" :disabled="uploadFiles.length === 0">
          上传 ({{ uploadFiles.length }} 个文件)
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload } from '@element-plus/icons-vue'
import http from '@/utils/http'

const folderTree = ref<any[]>([])
const documents = ref<any[]>([])
const selectedFolder = ref<any>(null)
const treeLoading = ref(false)
const docLoading = ref(false)
const searchKeyword = ref('')
const searchLoading = ref(false)
const searchResults = ref<any[]>([])

// 新建文件夹
const showCreateFolder = ref(false)
const newFolderName = ref('')
const newFolderParent = ref<string | null>(null)
const newFolderAccess = ref('public')

// 上传
const showUpload = ref(false)
const uploadFiles = ref<any[]>([])
const uploading = ref(false)

const totalDocs = computed(() => {
  let count = 0
  const countTree = (nodes: any[]) => {
    for (const n of nodes) {
      count += n.doc_count || 0
      if (n.children) countTree(n.children)
    }
  }
  countTree(folderTree.value)
  return count
})

const flatFolders = computed(() => {
  const result: any[] = []
  const flatten = (nodes: any[], prefix = '') => {
    for (const n of nodes) {
      result.push({ id: n.id, name: prefix + n.name })
      if (n.children) flatten(n.children, prefix + n.name + ' / ')
    }
  }
  flatten(folderTree.value)
  return result
})

async function loadTree() {
  treeLoading.value = true
  try {
    const { data } = await http.get('/api/knowledge-library/tree')
    folderTree.value = Array.isArray(data) ? data : (data?.data || [])
  } catch {
    folderTree.value = []
  } finally {
    treeLoading.value = false
  }
}

async function onFolderClick(node: any) {
  selectedFolder.value = node
  docLoading.value = true
  try {
    const { data } = await http.get(`/api/knowledge-library/folders/${node.id}/documents`)
    documents.value = Array.isArray(data) ? data : (data?.data || [])
  } catch {
    documents.value = []
  } finally {
    docLoading.value = false
  }
}

function onCreateFolder() {
  newFolderName.value = ''
  newFolderParent.value = selectedFolder.value?.id || null
  newFolderAccess.value = 'public'
  showCreateFolder.value = true
}

async function doCreateFolder() {
  try {
    await http.post('/api/knowledge-library/folders', {
      name: newFolderName.value,
      parent_id: newFolderParent.value,
      access_level: newFolderAccess.value,
    })
    ElMessage.success('文件夹创建成功')
    showCreateFolder.value = false
    await loadTree()
  } catch { ElMessage.error('创建失败') }
}

function onUploadDocs() {
  if (!selectedFolder.value) {
    ElMessage.warning('请先选择一个文件夹')
    return
  }
  uploadFiles.value = []
  showUpload.value = true
}

function onUploadToFolder() {
  uploadFiles.value = []
  showUpload.value = true
}

async function doUpload() {
  if (!selectedFolder.value || uploadFiles.value.length === 0) return
  uploading.value = true
  try {
    const formData = new FormData()
    for (const f of uploadFiles.value) {
      formData.append('files', f.raw)
    }
    const { data } = await http.post(
      `/api/knowledge-library/folders/${selectedFolder.value.id}/upload`,
      formData,
    )
    const result = data?.data ?? data
    ElMessage.success(`上传成功：${result?.uploaded || 0} 个文件`)
    showUpload.value = false
    // 刷新文档列表
    await onFolderClick(selectedFolder.value)
    await loadTree()
  } catch { ElMessage.error('上传失败') }
  finally { uploading.value = false }
}

async function onDeleteDoc(doc: any) {
  await ElMessageBox.confirm(`确认删除文档「${doc.name}」？`, '删除确认')
  try {
    await http.delete(`/api/knowledge-library/documents/${doc.id}`)
    ElMessage.success('已删除')
    if (selectedFolder.value) await onFolderClick(selectedFolder.value)
    await loadTree()
  } catch { ElMessage.error('删除失败') }
}

function formatSize(bytes: number): string {
  if (!bytes) return '—'
  if (bytes < 1024) return bytes + ' B'
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB'
  return (bytes / 1024 / 1024).toFixed(1) + ' MB'
}

// 全文搜索
async function onSearch() {
  if (!searchKeyword.value.trim()) return
  searchLoading.value = true
  try {
    const { data } = await http.get('/api/knowledge-library/search', { params: { q: searchKeyword.value } })
    const results = Array.isArray(data) ? data : (data?.data || [])
    documents.value = results
    selectedFolder.value = { name: `搜索结果: "${searchKeyword.value}" (${results.length} 条)` }
  } catch { ElMessage.error('搜索失败') }
  finally { searchLoading.value = false }
}

// 文档预览
async function onPreviewDoc(doc: any) {
  try {
    const { data } = await http.get(`/api/knowledge-library/documents/${doc.id}/preview`)
    const result = data?.data ?? data
    if (result.preview_type === 'text') {
      ElMessageBox.alert(result.content?.slice(0, 3000) || '无内容', `预览: ${doc.name}`, {
        confirmButtonText: '关闭',
        customStyle: { maxHeight: '500px', overflow: 'auto' },
      })
    } else if (result.preview_type === 'download') {
      window.open(result.download_url, '_blank')
    } else {
      ElMessage.info('该文档暂不支持预览')
    }
  } catch { ElMessage.error('预览失败') }
}

// 移动文档
async function onMoveDoc(doc: any) {
  const { value } = await ElMessageBox.prompt('输入目标文件夹名称（从列表中选择）', '移动文档', {
    inputPlaceholder: '目标文件夹ID',
  })
  if (!value) return
  // 从 flatFolders 中查找匹配的文件夹
  const target = flatFolders.value.find(f => f.name.includes(value) || f.id === value)
  if (!target) {
    ElMessage.warning('未找到匹配的文件夹')
    return
  }
  try {
    await http.put(`/api/knowledge-library/documents/${doc.id}/move`, { target_folder_id: target.id })
    ElMessage.success(`已移动到「${target.name}」`)
    if (selectedFolder.value) await onFolderClick(selectedFolder.value)
    await loadTree()
  } catch { ElMessage.error('移动失败') }
}

// 文件夹右键重命名
async function onFolderContextMenu(folder: any, event: MouseEvent) {
  event.preventDefault()
  const { value } = await ElMessageBox.prompt(`重命名文件夹「${folder.name}」`, '重命名', {
    inputValue: folder.name,
  })
  if (!value || value === folder.name) return
  try {
    await http.put(`/api/knowledge-library/folders/${folder.id}/rename`, { name: value })
    ElMessage.success('重命名成功')
    await loadTree()
  } catch { ElMessage.error('重命名失败') }
}

onMounted(loadTree)
</script>

<style scoped>
.gt-knowledge { padding: var(--gt-space-5); }
.gt-kb-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px; margin-bottom: 16px; color: #fff;
  position: relative; overflow: hidden;
}
.gt-kb-banner-text h2 { margin: 0 0 2px; font-size: 18px; }
.gt-kb-banner-text p { margin: 0; font-size: 12px; opacity: 0.75; }
.gt-kb-banner-actions { display: flex; gap: 8px; }
.gt-kb-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-kb-body { min-height: 500px; }
.gt-kb-panel { background: #fff; border-radius: var(--gt-radius-md); border: 1px solid #f0f0f0; padding: 16px; height: 100%; }
.gt-kb-panel-title { margin: 0 0 12px; font-size: 14px; color: var(--gt-color-text); }
.gt-kb-tree-node { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.gt-kb-doc-count { font-size: 11px; color: #999; margin-left: 2px; }
.gt-kb-doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-kb-doc-header h4 { margin: 0; font-size: 14px; }
.gt-kb-placeholder { text-align: center; padding: 60px 0; color: #999; }
</style>
