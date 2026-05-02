<template>
  <div class="gt-knowledge gt-fade-in">
    <!-- 后台上传进度指示器（横幅下方固定条） -->
    <transition name="el-fade-in">
      <div v-if="bgUploading || bgUploadJustDone" class="gt-kb-upload-bar">
        <el-progress :percentage="bgUploadProgress" :stroke-width="6" :show-text="false" style="flex: 1" />
        <span class="gt-kb-upload-bar-text">
          <template v-if="bgUploading">
            📤 上传中 {{ bgUploadDone }}/{{ bgUploadTotal }}
            <span v-if="bgUploadError > 0" style="color: #e6553a">（{{ bgUploadError }} 失败）</span>
          </template>
          <template v-else>
            ✅ 上传完成 {{ bgUploadDone - bgUploadError }}/{{ bgUploadTotal }}
          </template>
        </span>
      </div>
    </transition>

    <!-- 页面横幅 -->
    <div class="gt-kb-banner">
      <div class="gt-kb-banner-text">
        <el-button text style="color: #fff; font-size: 13px; padding: 0; margin-right: 12px" @click="goHome">← 返回</el-button>
        <div>
          <h2 style="margin: 0">知识库</h2>
          <p style="margin: 2px 0 0; opacity: 0.85">{{ folderTree.length }} 个分类 · {{ totalDocs }} 个文档</p>
        </div>
      </div>
      <div class="gt-kb-banner-actions">
        <el-input v-model="searchKeyword" placeholder="搜索文档..." size="small" clearable style="width: 180px"
          @keyup.enter="onSearch" />
        <el-button size="small" @click="onSearch" :loading="searchLoading" round>搜索</el-button>
        <el-button size="small" @click="onCreateFolder" round>新建文件夹</el-button>
        <el-button size="small" @click="onUploadDocs" round>上传文档</el-button>
        <el-button size="small" @click="onUploadFolder" round>上传文件夹</el-button>
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
              <div class="gt-kb-tree-node">
                <span class="gt-kb-tree-node-name">{{ data.name }}</span>
                <el-tag v-if="data.category" size="small" type="info" style="margin-left: 4px">预制</el-tag>
                <el-tag v-if="data.access_level === 'project_group'" size="small" type="warning" style="margin-left: 4px">项目组</el-tag>
                <el-tag v-if="data.access_level === 'private'" size="small" type="danger" style="margin-left: 4px">私有</el-tag>
                <span class="gt-kb-doc-count">({{ data.doc_count || 0 }})</span>
                <span class="gt-kb-tree-actions">
                  <el-button size="small" link @click.stop="onRenameFolder(data)" title="重命名">✏️</el-button>
                  <el-button size="small" link @click.stop="onDeleteFolder(data)" title="删除文件夹">🗑️</el-button>
                </span>
              </div>
            </template>
          </el-tree>
          <el-empty v-if="!treeLoading && folderTree.length === 0" description="暂无文件夹" :image-size="60" />
        </div>
      </el-col>

      <!-- 右侧：文档列表 + 预览 -->
      <el-col :span="17">
        <div class="gt-kb-panel gt-kb-doc-panel">
          <div class="gt-kb-doc-header">
            <h4>{{ selectedFolder?.name || '请选择文件夹' }}</h4>
            <div class="gt-kb-doc-header-actions">
              <el-button v-if="selectedDocIds.length > 0" size="small" type="danger" @click="onBatchDelete">
                删除选中 ({{ selectedDocIds.length }})
              </el-button>
              <el-button v-if="selectedFolder" size="small" type="primary" @click="onUploadToFolder">
                上传到此文件夹
              </el-button>
            </div>
          </div>

          <!-- 文档表格 + 右侧预览分栏 -->
          <div class="gt-kb-doc-body">
            <div class="gt-kb-doc-table" :class="{ 'gt-kb-doc-table--narrow': !!previewDoc }">
              <el-table v-if="documents.length" :data="documents" size="small" border stripe
                @selection-change="onDocSelectionChange" highlight-current-row @row-click="onDocRowClick">
                <el-table-column type="selection" width="40" />
                <el-table-column prop="name" label="文档名称" min-width="200" show-overflow-tooltip />
                <el-table-column prop="file_type" label="类型" width="60" align="center">
                  <template #default="{ row }">
                    <el-tag size="small">{{ row.file_type || '—' }}</el-tag>
                  </template>
                </el-table-column>
                <el-table-column label="大小" width="80" align="right">
                  <template #default="{ row }">{{ formatSize(row.file_size) }}</template>
                </el-table-column>
                <el-table-column prop="created_at" label="时间" width="90">
                  <template #default="{ row }">{{ row.created_at?.slice(0, 10) || '—' }}</template>
                </el-table-column>
                <el-table-column label="操作" width="150" align="center">
                  <template #default="{ row }">
                    <el-button size="small" link type="primary" @click.stop="onPreviewDoc(row)">预览</el-button>
                    <el-button size="small" link @click.stop="onRenameDoc(row)">重命名</el-button>
                    <el-button size="small" link type="danger" @click.stop="onDeleteDoc(row)">删除</el-button>
                  </template>
                </el-table-column>
              </el-table>
              <el-empty v-if="selectedFolder && !docLoading && documents.length === 0" description="暂无文档" :image-size="60" />
              <div v-if="!selectedFolder" class="gt-kb-placeholder">
                <p>← 请从左侧选择一个文件夹查看文档</p>
              </div>
            </div>

            <!-- 预览面板 -->
            <div v-if="previewDoc" class="gt-kb-preview-panel">
              <div class="gt-kb-preview-header">
                <span class="gt-kb-preview-title">{{ previewDoc.name }}</span>
                <div>
                  <el-button size="small" link @click="onDownloadDoc(previewDoc)">下载</el-button>
                  <el-button size="small" link @click="previewDoc = null">关闭</el-button>
                </div>
              </div>
              <div class="gt-kb-preview-body">
                <!-- 图片预览 -->
                <img v-if="isImageFile(previewDoc)" :src="previewUrl" class="gt-kb-preview-img" />
                <!-- PDF 预览 -->
                <iframe v-else-if="isPdfFile(previewDoc)" :src="previewUrl" class="gt-kb-preview-iframe" />
                <!-- Office 文件预览（通过后端转换或提示下载） -->
                <div v-else-if="isOfficeFile(previewDoc)" class="gt-kb-preview-office">
                  <div style="text-align: center; padding: 40px 20px">
                    <div style="font-size: 36px; margin-bottom: 12px">{{ getFileEmoji(previewDoc) }}</div>
                    <div style="font-size: 14px; color: #666; margin-bottom: 8px">{{ previewDoc.name }}</div>
                    <div style="font-size: 12px; color: #999; margin-bottom: 16px">{{ formatSize(previewDoc.file_size) }}</div>
                    <el-button type="primary" size="small" @click="onDownloadDoc(previewDoc)">下载查看</el-button>
                  </div>
                </div>
                <!-- 文本预览 -->
                <pre v-else-if="previewText !== null" class="gt-kb-preview-text">{{ previewText }}</pre>
                <!-- 其他 -->
                <div v-else class="gt-kb-preview-office">
                  <div style="text-align: center; padding: 40px">
                    <div style="font-size: 13px; color: #999">不支持预览此文件类型</div>
                    <el-button type="primary" size="small" style="margin-top: 12px" @click="onDownloadDoc(previewDoc)">下载</el-button>
                  </div>
                </div>
              </div>
            </div>
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

    <!-- 重命名弹窗 -->
    <el-dialog v-model="showRename" :title="renameType === 'folder' ? '重命名文件夹' : '重命名文档'" width="400px" append-to-body>
      <el-input v-model="renameNewName" placeholder="输入新名称" @keyup.enter="doRename" />
      <template #footer>
        <el-button @click="showRename = false">取消</el-button>
        <el-button type="primary" @click="doRename" :disabled="!renameNewName.trim()" :loading="renameLoading">确认</el-button>
      </template>
    </el-dialog>

    <!-- 上传文档弹窗 -->
    <el-dialog v-model="showUpload" title="上传文档" width="550px" append-to-body>
      <div style="display: flex; gap: 8px; margin-bottom: 12px">
        <el-radio-group v-model="uploadMode" size="small">
          <el-radio-button value="files">选择文件</el-radio-button>
          <el-radio-button value="folder">选择文件夹</el-radio-button>
        </el-radio-group>
      </div>
      <!-- 文件上传 -->
      <el-upload
        v-if="uploadMode === 'files'"
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
      <!-- 文件夹上传 -->
      <div v-else class="gt-kb-folder-upload">
        <div
          class="gt-kb-folder-drop"
          @click="triggerFolderInput"
          @dragover.prevent
          @drop.prevent="onFolderDrop"
        >
          <el-icon style="font-size: 40px; color: #c0c4cc; margin-bottom: 8px"><FolderOpened /></el-icon>
          <div>点击选择文件夹，或拖拽文件夹到此处</div>
          <div style="color: #999; font-size: 12px; margin-top: 4px">将自动按子文件夹结构创建目录</div>
        </div>
        <input
          ref="folderInputRef"
          type="file"
          webkitdirectory
          multiple
          style="display: none"
          @change="onFolderSelected"
        />
        <div v-if="folderFiles.length" style="margin-top: 12px">
          <el-tag size="small" type="info">{{ folderFiles.length }} 个文件</el-tag>
          <span style="font-size: 12px; color: #999; margin-left: 8px">
            {{ folderSubDirs.length }} 个子文件夹
          </span>
        </div>
      </div>
      <template #footer>
        <el-button @click="showUpload = false">取消</el-button>
        <el-button type="primary" @click="doUpload" :loading="uploading"
          :disabled="uploadMode === 'files' ? uploadFiles.length === 0 : folderFiles.length === 0">
          上传 ({{ uploadMode === 'files' ? uploadFiles.length : folderFiles.length }} 个文件)
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Upload, FolderOpened } from '@element-plus/icons-vue'
import http from '@/utils/http'

const router = useRouter()

function goHome() {
  router.push('/')
}

const folderTree = ref<any[]>([])
const documents = ref<any[]>([])
const selectedFolder = ref<any>(null)
const treeLoading = ref(false)
const docLoading = ref(false)
const searchKeyword = ref('')
const searchLoading = ref(false)
const _searchResults = ref<any[]>([])

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
  folderFiles.value = []
  uploadMode.value = 'files'
  showUpload.value = true
}

function onUploadFolder() {
  if (!selectedFolder.value) {
    ElMessage.warning('请先选择一个目标文件夹')
    return
  }
  uploadFiles.value = []
  folderFiles.value = []
  uploadMode.value = 'folder'
  showUpload.value = true
}

// 文件夹上传
const uploadMode = ref<'files' | 'folder'>('files')
const folderFiles = ref<File[]>([])
const folderInputRef = ref<HTMLInputElement | null>(null)

const folderSubDirs = computed(() => {
  const dirs = new Set<string>()
  for (const f of folderFiles.value) {
    const rel = (f as any).webkitRelativePath || f.name
    const parts = rel.split('/')
    if (parts.length > 1) {
      dirs.add(parts.slice(0, -1).join('/'))
    }
  }
  return Array.from(dirs)
})

function triggerFolderInput() {
  folderInputRef.value?.click()
}

function onFolderSelected(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) {
    folderFiles.value = Array.from(input.files)
  }
}

function onFolderDrop(e: DragEvent) {
  const items = e.dataTransfer?.items
  if (!items) return
  const files: File[] = []
  const traverse = (entry: any): Promise<void> => {
    return new Promise((resolve) => {
      if (entry.isFile) {
        entry.file((f: File) => { files.push(f); resolve() })
      } else if (entry.isDirectory) {
        const reader = entry.createReader()
        reader.readEntries(async (entries: any[]) => {
          for (const e of entries) await traverse(e)
          resolve()
        })
      } else {
        resolve()
      }
    })
  }
  Promise.all(Array.from(items).map(item => {
    const entry = item.webkitGetAsEntry?.()
    return entry ? traverse(entry) : Promise.resolve()
  })).then(() => {
    folderFiles.value = files
  })
}

function onUploadToFolder() {
  uploadFiles.value = []
  showUpload.value = true
}

async function doUpload() {
  if (!selectedFolder.value) return
  const isFolder = uploadMode.value === 'folder'
  const files = isFolder ? folderFiles.value : uploadFiles.value.map((f: any) => f.raw)
  if (files.length === 0) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }

  showUpload.value = false  // 立即关闭弹窗

  if (isFolder) {
    // 文件夹模式：后台逐个上传，保留完整目录结构
    startBackgroundUpload(folderFiles.value, selectedFolder.value)
  } else {
    // 普通文件模式：也走后台上传
    startBackgroundUpload(files, selectedFolder.value)
  }
}

// ── 后台上传 + 进度指示 ──
const bgUploadProgress = ref(0)    // 0~100
const bgUploadTotal = ref(0)
const bgUploadDone = ref(0)
const bgUploading = ref(false)
const bgUploadError = ref(0)
const bgUploadJustDone = ref(false)

async function startBackgroundUpload(files: File[], targetFolder: any) {
  bgUploading.value = true
  bgUploadJustDone.value = false
  bgUploadTotal.value = files.length
  bgUploadDone.value = 0
  bgUploadError.value = 0
  bgUploadProgress.value = 0
  ElMessage.info(`开始上传 ${files.length} 个文件，可继续操作...`)

  // 构建目录树结构：{ files: File[], children: { name: { files, children } } }
  interface DirNode { files: File[]; children: Record<string, DirNode> }
  const root: DirNode = { files: [], children: {} }

  for (const f of files) {
    const rel = (f as any).webkitRelativePath || f.name
    const parts = rel.split('/')
    // 保留完整目录层级（最后一段是文件名，前面都是目录）
    const dirParts = parts.slice(0, -1)
    let node = root
    for (const p of dirParts) {
      if (!node.children[p]) node.children[p] = { files: [], children: {} }
      node = node.children[p]
    }
    node.files.push(f)
  }

  // 用原生 fetch 上传（绕过 http.ts 的拦截器/去重/重试机制）
  function getAuthHeader(): Record<string, string> {
    const token = localStorage.getItem('token')
    return token ? { 'Authorization': `Bearer ${token}` } : {}
  }

  async function createFolderRaw(name: string, parentId: string): Promise<string | null> {
    try {
      const resp = await fetch('/api/knowledge-library/folders', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeader() },
        body: JSON.stringify({ name, parent_id: parentId, access_level: targetFolder.access_level || 'public' }),
      })
      if (!resp.ok) return null
      const json = await resp.json()
      const data = json?.data ?? json
      return data?.id || null
    } catch { return null }
  }

  async function uploadFileRaw(folderId: string, file: File): Promise<boolean> {
    return new Promise((resolve) => {
      const formData = new FormData()
      const cleanName = file.name.split('/').pop() || file.name
      formData.append('files', file, cleanName)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', `/api/knowledge-library/folders/${folderId}/upload`)
      const token = localStorage.getItem('token')
      if (token) xhr.setRequestHeader('Authorization', `Bearer ${token}`)

      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            const json = JSON.parse(xhr.responseText)
            const uploaded = json?.data?.uploaded ?? json?.uploaded ?? 0
            if (uploaded > 0) { resolve(true); return }
          } catch { /* ignore */ }
        }
        console.error('[KB Upload] failed:', cleanName, 'status:', xhr.status, 'resp:', xhr.responseText?.slice(0, 200))
        resolve(false)
      }
      xhr.onerror = () => {
        console.error('[KB Upload] xhr error:', cleanName)
        resolve(false)
      }
      xhr.timeout = 120000
      xhr.send(formData)
    })
  }

  // 逐级处理：先上传当前层文件，再创建子文件夹并递归
  async function processNode(node: DirNode, folderId: string) {
    // 1. 先上传当前层级的文件
    for (const f of node.files) {
      const ok = await uploadFileRaw(folderId, f)
      if (ok) {
        bgUploadDone.value += 1
      } else {
        bgUploadError.value += 1
        bgUploadDone.value += 1
      }
      bgUploadProgress.value = Math.round((bgUploadDone.value / bgUploadTotal.value) * 100)
    }

    // 2. 再创建子文件夹并递归处理
    for (const [childName, childNode] of Object.entries(node.children)) {
      const childId = await createFolderRaw(childName, folderId)
      await processNode(childNode, childId || folderId)
    }
  }

  await processNode(root, targetFolder.id)

  bgUploading.value = false
  bgUploadJustDone.value = true
  setTimeout(() => { bgUploadJustDone.value = false }, 3000)
  if (bgUploadError.value > 0) {
    ElMessage.warning(`上传完成：${bgUploadDone.value - bgUploadError.value} 成功，${bgUploadError.value} 失败`)
  } else {
    ElMessage.success(`上传完成：${bgUploadDone.value} 个文件`)
  }
  await loadTree()
  if (selectedFolder.value) await onFolderClick(selectedFolder.value)
}

// ── 重命名 ──
const showRename = ref(false)
const renameType = ref<'folder' | 'doc'>('folder')
const renameTargetId = ref('')
const renameNewName = ref('')
const renameLoading = ref(false)

function onRenameFolder(folder: any) {
  renameType.value = 'folder'
  renameTargetId.value = folder.id
  renameNewName.value = folder.name
  showRename.value = true
}

function onRenameDoc(doc: any) {
  renameType.value = 'doc'
  renameTargetId.value = doc.id
  renameNewName.value = doc.name
  showRename.value = true
}

async function doRename() {
  if (!renameNewName.value.trim()) return
  renameLoading.value = true
  try {
    if (renameType.value === 'folder') {
      await http.put(`/api/knowledge-library/folders/${renameTargetId.value}/rename`, {
        name: renameNewName.value.trim(),
      })
    } else {
      await http.put(`/api/knowledge-library/documents/${renameTargetId.value}`, {
        name: renameNewName.value.trim(),
      })
    }
    ElMessage.success('重命名成功')
    showRename.value = false
    await loadTree()
    if (selectedFolder.value) await onFolderClick(selectedFolder.value)
  } catch { ElMessage.error('重命名失败') }
  finally { renameLoading.value = false }
}

// ── 删除文件夹 ──
async function onDeleteFolder(folder: any) {
  await ElMessageBox.confirm(
    `确认删除文件夹「${folder.name}」及其所有内容？此操作不可恢复。`,
    '删除确认',
    { type: 'warning' },
  )
  try {
    await http.delete(`/api/knowledge-library/folders/${folder.id}`)
    ElMessage.success('文件夹已删除')
    if (selectedFolder.value?.id === folder.id) {
      selectedFolder.value = null
      documents.value = []
    }
    await loadTree()
  } catch { ElMessage.error('删除失败') }
}

// ── 删除文档 ──
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

// ── 批量选择与删除 ──
const selectedDocIds = ref<string[]>([])

function onDocSelectionChange(rows: any[]) {
  selectedDocIds.value = rows.map((r: any) => r.id)
}

async function onBatchDelete() {
  await ElMessageBox.confirm(`确认删除选中的 ${selectedDocIds.value.length} 个文档？`, '批量删除', { type: 'warning' })
  let deleted = 0
  for (const id of selectedDocIds.value) {
    try {
      await http.delete(`/api/knowledge-library/documents/${id}`)
      deleted++
    } catch { /* 单个失败不阻断 */ }
  }
  ElMessage.success(`已删除 ${deleted} 个文档`)
  selectedDocIds.value = []
  if (selectedFolder.value) await onFolderClick(selectedFolder.value)
  await loadTree()
}

// ── 文档预览（右侧面板） ──
const previewDoc = ref<any>(null)
const previewUrl = ref('')
const previewText = ref<string | null>(null)

function isImageFile(doc: any): boolean {
  const ext = (doc.name || '').split('.').pop()?.toLowerCase() || ''
  return ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(ext)
}

function isPdfFile(doc: any): boolean {
  return (doc.name || '').toLowerCase().endsWith('.pdf')
}

function isOfficeFile(doc: any): boolean {
  const ext = (doc.name || '').split('.').pop()?.toLowerCase() || ''
  return ['xlsx', 'xls', 'docx', 'doc', 'pptx', 'ppt'].includes(ext)
}

function isTextFile(doc: any): boolean {
  const ext = (doc.name || '').split('.').pop()?.toLowerCase() || ''
  return ['txt', 'md', 'csv', 'json', 'xml', 'log'].includes(ext)
}

function getFileEmoji(doc: any): string {
  const ext = (doc.name || '').split('.').pop()?.toLowerCase() || ''
  if (['xlsx', 'xls'].includes(ext)) return '📊'
  if (['docx', 'doc'].includes(ext)) return '📝'
  if (['pptx', 'ppt'].includes(ext)) return '📽️'
  if (['pdf'].includes(ext)) return '📕'
  return '📄'
}

function onDocRowClick(row: any) {
  onPreviewDoc(row)
}

async function onPreviewDoc(doc: any) {
  previewDoc.value = doc
  previewUrl.value = ''
  previewText.value = null

  if (isImageFile(doc) || isPdfFile(doc)) {
    // 图片和 PDF 直接用下载 URL 预览
    previewUrl.value = `/api/knowledge-library/documents/${doc.id}/download`
  } else if (isTextFile(doc)) {
    // 文本文件加载内容
    try {
      const { data } = await http.get(`/api/knowledge-library/documents/${doc.id}/preview`)
      const result = data?.data ?? data
      previewText.value = result?.content || '（空文件）'
    } catch {
      previewText.value = '加载失败'
    }
  }
  // Office 文件和其他类型在模板中直接显示下载入口
}

async function onDownloadDoc(doc: any) {
  try {
    const resp = await http.get(`/api/knowledge-library/documents/${doc.id}/download`, { responseType: 'blob' })
    const blob = new Blob([resp.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = doc.name
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('下载失败') }
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
.gt-kb-doc-panel { display: flex; flex-direction: column; }
.gt-kb-panel-title { margin: 0 0 12px; font-size: 14px; color: var(--gt-color-text); }
.gt-kb-tree-node { display: flex; align-items: center; gap: 4px; font-size: 13px; }
.gt-kb-doc-count { font-size: 11px; color: #999; margin-left: 2px; }
.gt-kb-doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-kb-doc-header h4 { margin: 0; font-size: 14px; }
.gt-kb-doc-header-actions { display: flex; gap: 8px; }
.gt-kb-placeholder { text-align: center; padding: 60px 0; color: #999; }

/* 文档列表 + 预览分栏 */
.gt-kb-doc-body { display: flex; gap: 12px; flex: 1; min-height: 0; overflow: hidden; }
.gt-kb-doc-table { flex: 1; min-width: 0; overflow: auto; }
.gt-kb-doc-table--narrow { max-width: 55%; }

/* 预览面板 */
.gt-kb-preview-panel {
  width: 45%; min-width: 300px; background: #fafafa; border: 1px solid #f0f0f0;
  border-radius: var(--gt-radius-md); display: flex; flex-direction: column; overflow: hidden;
}
.gt-kb-preview-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-bottom: 1px solid #f0f0f0; background: #fff;
}
.gt-kb-preview-title { font-size: 13px; font-weight: 600; color: #333; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-preview-body { flex: 1; overflow: auto; padding: 0; }
.gt-kb-preview-img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
.gt-kb-preview-iframe { width: 100%; height: 100%; border: none; }
.gt-kb-preview-text {
  margin: 0; padding: 12px 16px; font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-all; color: #333; font-family: monospace;
}
.gt-kb-preview-office { display: flex; align-items: center; justify-content: center; height: 100%; }

/* 文件夹上传 */
.gt-kb-folder-upload { }
.gt-kb-folder-drop {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 20px; border: 2px dashed #dcdfe6; border-radius: 8px;
  cursor: pointer; transition: border-color 0.2s;
  color: #606266; font-size: 14px;
}
.gt-kb-folder-drop:hover { border-color: var(--gt-color-primary); }

/* 树节点操作按钮 */
.gt-kb-tree-node { display: flex; align-items: center; gap: 4px; width: 100%; }
.gt-kb-tree-node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-tree-actions { display: none; margin-left: auto; flex-shrink: 0; }
.gt-kb-tree-node:hover .gt-kb-tree-actions { display: inline-flex; gap: 2px; }
.gt-kb-tree-actions .el-button { padding: 0 2px; font-size: 12px; }

/* 后台上传进度条 */
.gt-kb-upload-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; margin-bottom: 8px;
  background: #fff; border-radius: var(--gt-radius-md);
  border: 1px solid #e8e0f0; box-shadow: var(--gt-shadow-sm);
}
.gt-kb-upload-bar-text { font-size: 12px; color: #555; white-space: nowrap; }
</style>
