<template>
  <div class="gt-knowledge gt-fade-in">
    <!-- 后台上传进度指示器（横幅下方固定条） -->
    <transition name="el-fade-in">
      <div v-if="bgUploading || bgUploadJustDone" class="gt-kb-upload-bar">
        <el-progress :percentage="bgUploadProgress" :stroke-width="6" :show-text="false" style="flex: 1" />
        <span class="gt-kb-upload-bar-text">
          <template v-if="bgUploading">
            📤 上传中 {{ bgUploadDone }}/{{ bgUploadTotal }}
            <span v-if="bgUploadError > 0" style="color: var(--gt-color-coral)">（{{ bgUploadError }} 失败）</span>
          </template>
          <template v-else>
            ✅ 上传完成 {{ bgUploadDone - bgUploadError }}/{{ bgUploadTotal }}
          </template>
        </span>
      </div>
    </transition>

    <!-- 页面横幅 [R7-S3-01] -->
    <GtPageHeader title="知识库" @back="goHome">
      <template #actions>
        <GtToolbar>
          <template #left>
            <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary)">{{ folderTree.length }} 个分类 · {{ totalDocs }} 个文档</span>
          </template>
          <template #right>
            <el-input v-model="searchKeyword" placeholder="搜索文档..." size="small" clearable style="width: 180px"
              @keyup.enter="onSearch" />
            <el-button size="small" @click="onSearch" :loading="searchLoading">搜索</el-button>
            <!-- 写按钮按系统角色门控：readonly / 未知角色一律不展示（后端同口径拒绝，见 canWriteKb） -->
            <el-button v-if="canWriteKb && !treeLoading && !hasPresetFolders" size="small" :loading="initPresetsLoading" @click="onInitPresets">初始化预设文件夹</el-button>
            <el-button v-if="canWriteKb" size="small" @click="onCreateFolder">新建文件夹</el-button>
            <el-button v-if="canWriteKb" size="small" @click="onUploadDocs">上传文档</el-button>
            <el-button v-if="canWriteKb" size="small" @click="onUploadFolder">上传文件夹</el-button>
            <el-button size="small" :disabled="!selectedFolder" @click="showDocAiChat = true">💬 AI 对话</el-button>
            <el-button size="small" @click="loadTree" :loading="treeLoading">刷新</el-button>
          </template>
        </GtToolbar>
      </template>
    </GtPageHeader>

    <!-- 主体：左树 + 右文档列表 -->
    <el-row :gutter="12" class="gt-kb-body">
      <!-- 左侧：文件夹树 -->
      <el-col :span="7">
        <div class="gt-kb-panel gt-kb-tree-panel">
          <h4 class="gt-kb-panel-title">目录</h4>
          <el-tree
            ref="treeRef"
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
                <el-tag v-if="data.is_system" size="small" type="success" style="margin-left: 4px">系统</el-tag>
                <el-tag v-if="data.access_level === 'project_group'" size="small" type="warning" style="margin-left: 4px">项目组</el-tag>
                <el-tag v-if="data.access_level === 'private'" size="small" type="danger" style="margin-left: 4px">私有</el-tag>
                <span class="gt-kb-doc-count">({{ data.doc_count || 0 }})</span>
                <!-- 管理权由后端逐节点下发（创建者或系统管理员；系统文件夹仅管理员） -->
                <span v-if="canWriteKb && data.can_manage" class="gt-kb-tree-actions">
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
              <el-button v-if="canWriteKb && selectedDocIds.length > 0" size="small" type="danger" @click="onBatchDelete">
                删除选中 ({{ selectedDocIds.length }})
              </el-button>
              <!-- 只有真实文件夹（有 id）且有创建权才能上传；搜索结果视图的 selectedFolder 没有 id -->
              <el-button v-if="canCreateInSelected" size="small" type="primary" @click="onUploadDocs">
                上传到此文件夹
              </el-button>
            </div>
          </div>

          <!-- 文档表格 + 右侧预览分栏 -->
          <div class="gt-kb-doc-body">
            <div class="gt-kb-doc-table" :class="{ 'gt-kb-doc-table--narrow': !!previewDoc }">
              <el-table v-if="documents.length" :data="documents" size="small" border stripe
                @selection-change="onDocSelectionChange" highlight-current-row @row-click="onDocRowClick">
                <el-table-column v-if="canWriteKb" type="selection" width="40" :selectable="isRowSelectable" />
                <el-table-column prop="name" label="文档名称" min-width="200">
                  <template #default="{ row }">
                    <div class="gt-kb-doc-name" :title="row.name">{{ row.name }}</div>
                    <!-- 无正文：AI 检索与对话读不到它的内容；扫描件（PDF 需 OCR）与其余原因分开提示；
                         has_text 缺失（搜索视图）不显示 -->
                    <div v-if="row.has_text === false" class="gt-kb-doc-notext"
                      :title="noTextHint(row.name, row.file_type).title">
                      {{ noTextHint(row.name, row.file_type).label }}
                    </div>
                    <!-- 搜索结果：所在文件夹路径 + 命中片段（后端词法检索返回，≤200 字） -->
                    <div v-if="isSearchView && row.folder_path" class="gt-kb-doc-path">📁 {{ row.folder_path }}</div>
                    <div v-if="isSearchView && row.snippet" class="gt-kb-doc-snippet">{{ row.snippet }}</div>
                  </template>
                </el-table-column>
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
                    <!-- 管理权由后端逐行下发：非创建者（且非系统管理员）看不到改名 / 删除 -->
                    <template v-if="canWriteKb && row.can_manage">
                      <el-button size="small" link @click.stop="onRenameDoc(row)">重命名</el-button>
                      <el-button size="small" link type="danger" @click.stop="onDeleteDoc(row)">删除</el-button>
                    </template>
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
                    <div style="font-size: 36px /* allow-px: special */; margin-bottom: 12px">{{ getFileEmoji(previewDoc) }}</div>
                    <div style="font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); margin-bottom: 8px">{{ previewDoc.name }}</div>
                    <div style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-bottom: 16px">{{ formatSize(previewDoc.file_size) }}</div>
                    <el-button type="primary" size="small" @click="onDownloadDoc(previewDoc)">下载查看</el-button>
                  </div>
                </div>
                <!-- 文本预览 -->
                <pre v-else-if="previewText !== null" class="gt-kb-preview-text">{{ previewText }}</pre>
                <!-- 其他 -->
                <div v-else class="gt-kb-preview-office">
                  <div style="text-align: center; padding: 40px">
                    <div style="font-size: var(--gt-font-size-sm); color: var(--gt-color-text-tertiary)">不支持预览此文件类型</div>
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
      <el-form ref="folderFormRef" :model="folderFormModel" :rules="folderRules" label-width="80px">
        <el-form-item label="名称" prop="name">
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
        <!-- 项目组权限必须指定项目：不指定时文件夹对任何人（含创建者）都不可见 -->
        <el-form-item v-if="newFolderAccess === 'project_group'" label="项目">
          <el-select
            v-model="newFolderProjectIds"
            multiple
            filterable
            collapse-tags
            collapse-tags-tooltip
            placeholder="选择可访问的项目（须包含你参与的项目）"
            style="width: 100%"
          >
            <el-option v-for="p in folderProjectOptions" :key="p.id" :label="p.label" :value="p.id" />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showCreateFolder = false">取消</el-button>
        <el-button type="primary" @click="doCreateFolder" :loading="createFolderLoading" :disabled="!canSubmitFolder">创建</el-button>
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
        :accept="UPLOAD_ACCEPT"
      >
        <el-icon style="font-size: 40px /* allow-px: special */; color: var(--gt-color-text-placeholder)"><Upload /></el-icon>
        <div>拖拽文件到此处，或点击选择</div>
        <template #tip>
          <div style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs)">支持 PDF / Word / Excel（含 .xlsm）/ PPT / TXT / Markdown / CSV；扫描件需开启 OCR 才能提取文字</div>
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
          <el-icon style="font-size: 40px /* allow-px: special */; color: var(--gt-color-text-placeholder); margin-bottom: 8px"><FolderOpened /></el-icon>
          <div>点击选择文件夹，或拖拽文件夹到此处</div>
          <div style="color: var(--gt-color-text-tertiary); font-size: var(--gt-font-size-xs); margin-top: 4px">将自动按子文件夹结构创建目录</div>
        </div>
        <input
          ref="folderInputRef"
          type="file"
          webkitdirectory
          multiple
          style="display: none"
          @change="onFolderSelected"
        />
        <div v-if="folderFiles.length || folderSkipped" style="margin-top: 12px">
          <el-tag size="small" type="info">{{ folderFiles.length }} 个文件</el-tag>
          <span style="font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 8px">
            {{ folderSubDirs.length }} 个子文件夹
            <template v-if="folderSkipped">· 已跳过 {{ folderSkipped }} 个系统临时文件</template>
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

    <!-- AI 对话面板（统一内核；文件夹级宿主契约由 useAiHostContext 的知识库 adapter 构造） -->
    <PlatformAiChatPanel
      :host="aiHost"
      :visible="showDocAiChat"
      @adopt="onDocAiAdopt"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, h, nextTick, onMounted, onBeforeUnmount, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { normalizeRole } from '@/utils/roles'
import type { FormInstance, FormRules } from 'element-plus'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import {
  buildUploadSummary,
  collectFromEntries,
  entriesFromDataTransfer,
  isSystemJunkPath,
  noTextHint,
  parseUploadResponse,
  type UploadFailure,
  type UploadOutcome,
  type UploadSummary,
} from '@/utils/knowledgeUpload'
import { confirmDelete, confirmBatch, confirmDangerous } from '@/utils/confirm'
import GtPageHeader from '@/components/common/GtPageHeader.vue'
import GtToolbar from '@/components/common/GtToolbar.vue'
import { Upload, FolderOpened } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import { knowledgeLibrary as P_kl, projects as P_proj } from '@/services/apiPaths'
import { downloadFile } from '@/utils/http'
import { getAuthHeaders } from '@/utils/authToken'
import { handleApiError } from '@/utils/errorHandler'
import { rules } from '@/utils/formRules'
import PlatformAiChatPanel from '@/components/ai/PlatformAiChatPanel.vue'
import { buildKnowledgeFolderHost } from '@/composables/useAiHostContext'

const router = useRouter()
const route = useRoute()

/** 当前底稿上下文（wp_code + account_name），用于搜索相关性加权 */
const currentWpContext = computed(() => {
  const wpCode = route.query.wp_code as string || ''
  const accountName = route.query.account_name as string || ''
  return [wpCode, accountName].filter(Boolean).join(' ')
})

function goHome() {
  router.push('/projects')
}

// ─── AI 宿主上下文（dsh-agent-panel-integration Req 3.3/3.4/3.5） ──────────────
// 知识库是全局页面：没有项目上下文时 projectId 传 **null**（旧实现传 `''` 伪装有效项目 ID，
// 年度还用 `new Date().getFullYear()` 猜）。从项目内跳转进来时才带 project 断言。
// 搜索结果视图的 selectedFolder 没有 id → adapter 返回显式不可用 + 中文原因。
const aiHost = computed(() =>
  buildKnowledgeFolderHost({
    folderId: selectedFolder.value?.id,
    projectId: route.query.project_id,
  }),
)

// ─── AI 文档对话采纳 ─────────────────────────────────────────────────────────
function onDocAiAdopt(_payload: { content: string; messageId: string }) {
  // 知识库文件夹级对话采纳：PlatformAiChatPanel 内部已调用 adoptContent API（走确认流）
  // D4: AI 内容已经过 wrap_ai_output_with_log → pending 状态，不直接写入
  // 知识库无需回写文档，仅记录采纳事件
}

// ─── 写按钮门控（spec knowledge-base-retrieval-and-authz-closure Req 6.8） ─────────
// 后端是权威判定：目录树节点带 can_manage / can_create，文档行与搜索结果带 can_manage，
// 越权请求一律 403/404。前端只负责「不展示必然被拒的按钮」，并额外按系统角色兜底：
// readonly 或未知角色 → 隐藏全部写按钮（与后端 KnowledgeWritePolicy.role_allows_write
// 同口径：白名单，未知角色 fail-closed）。
const authStore = useAuthStore()
const canWriteKb = computed(() => {
  const role = normalizeRole(authStore.user?.role)
  return role !== '' && role !== 'readonly'
})
/** 当前选中的是真实文件夹（搜索 / 链接视图没有 id）且可向其上传、新建子文件夹 */
const canCreateInSelected = computed(
  () => canWriteKb.value && !!selectedFolder.value?.id && !!selectedFolder.value?.can_create,
)
/** 搜索结果视图：显示命中片段与所在文件夹路径 */
const isSearchView = computed(() => !!selectedFolder.value?.isSearch)
/** 批量删除只允许勾选有管理权的行（越权行勾了也只会得到 403） */
function isRowSelectable(row: any): boolean {
  return !!row?.can_manage
}

const folderTree = ref<any[]>([])
const documents = ref<any[]>([])
const selectedFolder = ref<any>(null)
const treeLoading = ref(false)
const docLoading = ref(false)
const searchKeyword = ref('')
const searchLoading = ref(false)
const _searchResults = ref<any[]>([])
const showDocAiChat = ref(false)
const treeRef = ref<any>(null)
/** 项目组权限的可选项目：标签带年度（同一客户多年度项目的 client_name 相同，不带年度无法区分） */
const folderProjectOptions = ref<Array<{ id: string; label: string }>>([])
async function loadFolderProjectOptions() {
  if (folderProjectOptions.value.length > 0) return
  try {
    const data: any = await api.get(P_proj.list)
    const items: any[] = Array.isArray(data) ? data : (data?.items ?? [])
    folderProjectOptions.value = items.map((p: any) => ({
      id: p.id,
      label: p.audit_year
        ? `${p.client_name || p.name}（${p.audit_year} 年度）`
        : (p.name || p.client_name || p.id),
    }))
  } catch {
    folderProjectOptions.value = []
  }
}
// 新建文件夹
const showCreateFolder = ref(false)
const newFolderName = ref('')
const newFolderParent = ref<string | null>(null)
const newFolderAccess = ref('public')
const newFolderProjectIds = ref<string[]>([])
const createFolderLoading = ref(false)
/** 项目组权限未选项目时禁止提交：后端同样会拒绝（否则建出对所有人不可见的文件夹） */
const canSubmitFolder = computed(() =>
  !!newFolderName.value.trim()
  && (newFolderAccess.value !== 'project_group' || newFolderProjectIds.value.length > 0),
)
const folderFormRef = ref<FormInstance>()
const folderFormModel = computed(() => ({ name: newFolderName.value }))
const folderRules: FormRules = {
  name: [rules.required('文件夹名称')],
}

// 上传
const showUpload = ref(false)
const uploadFiles = ref<any[]>([])
const uploading = ref(false)
/**
 * 文件选择框的类型过滤（只影响选择框的默认筛选，拖入不受限；后端对任何类型都会保存原文件）。
 * 旧值漏了 `.xlsm`（B 循环模板全是 xlsm）、`.ppt`、`.csv` —— 选择框里直接看不到这些文件。
 */
const UPLOAD_ACCEPT = '.pdf,.docx,.doc,.xlsx,.xls,.xlsm,.pptx,.ppt,.txt,.md,.csv'

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

/** 可作为「新建位置 / 移动目标」的文件夹（只列有创建权的；路径前缀仍按完整层级拼） */
const flatFolders = computed(() => {
  const result: any[] = []
  const flatten = (nodes: any[], prefix = '') => {
    for (const n of nodes) {
      if (n.can_create) result.push({ id: n.id, name: prefix + n.name })
      if (n.children) flatten(n.children, prefix + n.name + ' / ')
    }
  }
  flatten(folderTree.value)
  return result
})

async function loadTree() {
  treeLoading.value = true
  try {
    const data = await api.get(P_kl.tree)
    folderTree.value = Array.isArray(data) ? data : (data || [])
  } catch {
    folderTree.value = []
  } finally {
    treeLoading.value = false
  }
}

async function onFolderClick(node: any) {
  selectedFolder.value = node
  selectedDocIds.value = []
  docLoading.value = true
  try {
    const data = await api.get(P_kl.folderDocuments(node.id))
    documents.value = Array.isArray(data) ? data : (data || [])
  } catch {
    documents.value = []
  } finally {
    docLoading.value = false
  }
}

// ─── 深链 `/knowledge?folder_id=…&doc_id=…`（spec knowledge-base-retrieval-and-authz-closure Req 5.10） ───
// AI 笔记转存、@引用跳转都生成这种链接（后端单一真源 note_service.knowledge_jump_route）。
// 只给 doc_id 时先调预览接口取 folder_id（该接口同时做可读判定：不可读与不存在同构 404）。
// 目标不在当前用户的目录树里 → 中文提示，不暴露「存在但无权」与「不存在」的差别。
const DEEP_LINK_DENIED = '文件夹不存在或无权访问'
const DOC_DEEP_LINK_DENIED = '文档不存在或无权访问'

function queryParam(v: unknown): string {
  const first = Array.isArray(v) ? v[0] : v
  return typeof first === 'string' ? first.trim() : ''
}

/** 处理深链；返回是否成功定位（供测试与调用方判断） */
async function applyDeepLink(): Promise<boolean> {
  let folderId = queryParam(route.query.folder_id)
  const docId = queryParam(route.query.doc_id)
  if (!folderId && !docId) return false

  let preview: any = null
  if (docId) {
    try {
      // _silent：404 由本处给出统一中文提示，不叠加全局「资源不存在」toast
      preview = await api.get(P_kl.documentPreview(docId), { _silent: true } as any)
    } catch {
      preview = null
    }
    if (!preview?.id) {
      ElMessage.warning(DOC_DEEP_LINK_DENIED)
      if (!folderId) return false
    } else if (!folderId) {
      folderId = String(preview.folder_id || '')
    }
  }

  const node = folderId ? findFolderNode(folderTree.value, folderId) : null
  if (node) {
    await onFolderClick(node)
    await nextTick()
    treeRef.value?.setCurrentKey?.(node.id)
  } else if (preview?.id) {
    // 文档本身可读（如公开文档放在他人的私有文件夹里）但文件夹不在你的目录树中：只打开预览
    ElMessage.info('文档所在文件夹不在你的目录中，已直接打开文档')
  } else {
    ElMessage.warning(DEEP_LINK_DENIED)
    return false
  }

  if (preview?.id) {
    // 预览面板优先用列表里的行（带 file_size / can_manage）；列表里没有（如旧版本）时用预览响应兜底
    const row = documents.value.find((d: any) => d.id === preview.id)
      ?? { id: preview.id, name: preview.name, file_type: preview.file_type }
    await onPreviewDoc(row, preview)
  }
  return true
}

watch(
  () => [route.query.folder_id, route.query.doc_id],
  (next, prev) => {
    // 挂载时由 onMounted 在目录树加载完之后处理；这里只响应同页内的链接变化
    if (!prev || (next[0] === prev[0] && next[1] === prev[1])) return
    void applyDeepLink()
  },
)

function onCreateFolder() {
  newFolderName.value = ''
  // 只有可创建的文件夹才能作为默认父级（否则后端拒绝，用户还得回头改「位置」）
  newFolderParent.value = canCreateInSelected.value ? selectedFolder.value.id : null
  newFolderAccess.value = 'public'
  newFolderProjectIds.value = []
  showCreateFolder.value = true
  // 项目组权限的项目下拉（已加载则不重复请求）
  loadFolderProjectOptions()
}

/** 在已加载的目录树里按 id 找节点（新建后自动选中用） */
function findFolderNode(nodes: any[], id: string): any | null {
  for (const n of nodes) {
    if (n.id === id) return n
    const hit = n.children?.length ? findFolderNode(n.children, id) : null
    if (hit) return hit
  }
  return null
}

async function doCreateFolder() {
  if (!canSubmitFolder.value) return
  createFolderLoading.value = true
  try {
    const isProjectGroup = newFolderAccess.value === 'project_group'
    const created: any = await api.post(P_kl.folders, {
      name: newFolderName.value.trim(),
      parent_id: newFolderParent.value,
      access_level: newFolderAccess.value,
      project_ids: isProjectGroup ? newFolderProjectIds.value : null,
    })
    ElMessage.success('文件夹创建成功')
    showCreateFolder.value = false
    await loadTree()
    // 自动选中新文件夹：用户下一步就是往里上传，不必再回左侧树里找
    const node = created?.id ? findFolderNode(folderTree.value, created.id) : null
    if (node) {
      await onFolderClick(node)
      await nextTick()
      treeRef.value?.setCurrentKey?.(node.id)
    }
  } catch (e: any) { handleApiError(e, '创建') }
  finally { createFolderLoading.value = false }
}

// ── 预设分类文件夹（首次使用引导里的「初始化预设文件夹」） ──
const initPresetsLoading = ref(false)
const hasPresetFolders = computed(() => folderTree.value.some((n: any) => !!n.category))

async function onInitPresets() {
  initPresetsLoading.value = true
  try {
    const res: any = await api.post(P_kl.initPresets)
    const created = Number(res?.created ?? 0)
    ElMessage.success(created > 0 ? `已创建 ${created} 个预设文件夹` : '预设文件夹已存在')
    await loadTree()
  } catch (e: any) { handleApiError(e, '初始化预设文件夹') }
  finally { initPresetsLoading.value = false }
}

/** 上传前置：必须选中真实文件夹且有创建权（否则后端 403/404，文件白传一遍） */
function ensureUploadTarget(emptyHint: string): boolean {
  // 搜索结果视图的 selectedFolder 只有 name 没有 id，不能作为上传目标
  if (!selectedFolder.value?.id) {
    ElMessage.warning(emptyHint)
    return false
  }
  if (!canCreateInSelected.value) {
    ElMessage.warning('你没有向该文件夹添加资料的权限')
    return false
  }
  return true
}

function onUploadDocs() {
  if (!ensureUploadTarget('请先在左侧选择一个文件夹')) return
  uploadFiles.value = []
  folderFiles.value = []
  // 上一次选择的跳过数不能带进新弹窗（否则未选文件就显示「已跳过 N 个」，且会被算进下一批汇总）
  folderSkipped.value = 0
  uploadMode.value = 'files'
  showUpload.value = true
}

function onUploadFolder() {
  if (!ensureUploadTarget('请先选择一个目标文件夹')) return
  uploadFiles.value = []
  folderFiles.value = []
  folderSkipped.value = 0
  uploadMode.value = 'folder'
  showUpload.value = true
}

// 文件夹上传
const uploadMode = ref<'files' | 'folder'>('files')
const folderFiles = ref<File[]>([])
const folderInputRef = ref<HTMLInputElement | null>(null)
/** 选择 / 拖入文件夹时跳过的系统临时文件数（结束汇总里说明） */
const folderSkipped = ref(0)

/**
 * 拖入文件的相对路径。`File.webkitRelativePath` 是只读属性，拖拽得到的 File 上恒为空串，
 * 层级只能另存（来自 FileSystemEntry.fullPath）。WeakMap：File 被释放时条目随之回收。
 */
const droppedRelativePath = new WeakMap<File, string>()

/** 文件相对路径：选择文件夹 → webkitRelativePath；拖入 → fullPath；单文件 → 文件名 */
function relativePathOf(f: File): string {
  return droppedRelativePath.get(f) || (f as any).webkitRelativePath || f.name
}

const folderSubDirs = computed(() => {
  const dirs = new Set<string>()
  for (const f of folderFiles.value) {
    const parts = relativePathOf(f).split('/')
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
    const all = Array.from(input.files)
    // 系统临时文件（~$ 锁文件、.DS_Store 等）不上传：入库后只是一堆无正文的垃圾文档
    folderFiles.value = all.filter((f) => !isSystemJunkPath(relativePathOf(f)))
    folderSkipped.value = all.length - folderFiles.value.length
  }
  // 清空 input：再次选择同一文件夹也能触发 change
  input.value = ''
}

async function onFolderDrop(e: DragEvent) {
  // 🔴 条目必须在 drop 处理函数的同步部分取出：函数返回后 DataTransferItemList 即失效
  const roots = entriesFromDataTransfer(e.dataTransfer)
  if (!roots.length) return
  const { files, failed, skipped } = await collectFromEntries(roots)
  for (const { file, relativePath } of files) droppedRelativePath.set(file, relativePath)
  folderFiles.value = files.map((d) => d.file)
  folderSkipped.value = skipped
  if (failed.length) {
    ElMessage.warning(`有 ${failed.length} 个文件读取失败（如 ${failed[0]}），已跳过`)
  }
}

async function doUpload() {
  if (!selectedFolder.value?.id) return
  const isFolder = uploadMode.value === 'folder'
  const files = isFolder ? folderFiles.value : uploadFiles.value.map((f: any) => f.raw)
  if (files.length === 0) {
    ElMessage.warning('请先选择要上传的文件')
    return
  }

  showUpload.value = false  // 立即关闭弹窗

  // 两种模式都走后台逐个上传；文件夹模式按相对路径保留完整目录结构
  startBackgroundUpload(files, selectedFolder.value, isFolder ? folderSkipped.value : 0)
}

// ── 后台上传 + 进度指示 ──
const bgUploadProgress = ref(0)    // 0~100
const bgUploadTotal = ref(0)
const bgUploadDone = ref(0)
const bgUploading = ref(false)
const bgUploadError = ref(0)
const bgUploadJustDone = ref(false)

async function startBackgroundUpload(files: File[], targetFolder: any, skipped = 0) {
  bgUploading.value = true
  bgUploadJustDone.value = false
  bgUploadTotal.value = files.length
  bgUploadDone.value = 0
  bgUploadError.value = 0
  bgUploadProgress.value = 0
  ElMessage.info(`开始上传 ${files.length} 个文件，可继续操作...`)

  /** 逐文件结果（结束时一次性汇总展示：失败原因 + 未提取到正文） */
  const failures: UploadFailure[] = []
  const noText: string[] = []
  const folderFailures: string[] = []

  // 构建目录树结构：{ files: File[], children: { name: { files, children } } }
  interface DirNode { files: File[]; children: Record<string, DirNode> }
  const root: DirNode = { files: [], children: {} }

  for (const f of files) {
    const parts = relativePathOf(f).split('/')
    // 保留完整目录层级（最后一段是文件名，前面都是目录）
    const dirParts = parts.slice(0, -1)
    let node = root
    for (const p of dirParts) {
      if (!node.children[p]) node.children[p] = { files: [], children: {} }
      node = node.children[p]
    }
    node.files.push(f)
  }

  // 用原生 fetch/XHR 上传（绕过 http.ts 的拦截器/去重/5xx 重试 —— 重试 POST 会重复建版本）。
  // 🔴 鉴权头必须走 getAuthHeaders()：token 已迁到 sessionStorage，读 localStorage 恒为空 → 401
  //    （2026-09-29 实测：本页上传全部 401「Not authenticated」，即「新建文件夹后上传不了」根因）。
  async function createFolderRaw(name: string, parentId: string): Promise<string | null> {
    try {
      const resp = await fetch(P_kl.folders, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        // 子文件夹继承目标文件夹的权限与项目范围（项目组权限缺项目会被后端拒绝）
        body: JSON.stringify({
          name,
          parent_id: parentId,
          access_level: targetFolder.access_level || 'public',
          project_ids: targetFolder.project_ids ?? null,
        }),
      })
      if (!resp.ok) {
        console.error('[KB Upload] create sub-folder failed:', name, 'status:', resp.status)
        return null
      }
      const json = await resp.json()
      const data = json?.data ?? json
      return data?.id || null
    } catch { return null }
  }

  async function uploadFileRaw(folderId: string, file: File): Promise<UploadOutcome> {
    return new Promise((resolve) => {
      const formData = new FormData()
      const cleanName = file.name.split('/').pop() || file.name
      formData.append('files', file, cleanName)

      const xhr = new XMLHttpRequest()
      xhr.open('POST', P_kl.folderUpload(folderId))
      // 每个文件现取 token（长时间批量上传期间拦截器可能已刷新过 token）
      for (const [k, v] of Object.entries(getAuthHeaders())) xhr.setRequestHeader(k, v)

      xhr.onload = () => {
        const outcome = parseUploadResponse(xhr.status, xhr.responseText || '')
        if (!outcome.ok) {
          console.error('[KB Upload] failed:', cleanName, 'status:', xhr.status, 'resp:', xhr.responseText?.slice(0, 200))
        }
        resolve(outcome)
      }
      xhr.onerror = () => {
        console.error('[KB Upload] xhr error:', cleanName)
        resolve({ ok: false, reason: '网络错误，未能连接服务器', textExtracted: false })
      }
      // 超时不触发 onerror，旧实现漏接 ⇒ 该文件的 Promise 永不 resolve，整批上传卡死在进度条上
      xhr.ontimeout = () => {
        console.error('[KB Upload] timeout:', cleanName)
        resolve({ ok: false, reason: '上传超时（超过 2 分钟），文件可能过大或网络较慢', textExtracted: false })
      }
      xhr.timeout = 120000
      xhr.send(formData)
    })
  }

  // 逐级处理：先上传当前层文件，再创建子文件夹并递归
  async function processNode(node: DirNode, folderId: string, dirPath: string) {
    // 1. 先上传当前层级的文件
    for (const f of node.files) {
      const outcome = await uploadFileRaw(folderId, f)
      const shownName = relativePathOf(f)
      if (!outcome.ok) {
        bgUploadError.value += 1
        failures.push({ name: shownName, reason: outcome.reason })
      } else if (!outcome.textExtracted) {
        noText.push(shownName)
      }
      bgUploadDone.value += 1
      bgUploadProgress.value = Math.round((bgUploadDone.value / bgUploadTotal.value) * 100)
    }

    // 2. 再创建子文件夹并递归处理
    for (const [childName, childNode] of Object.entries(node.children)) {
      const childPath = dirPath ? `${dirPath}/${childName}` : childName
      const childId = await createFolderRaw(childName, folderId)
      if (!childId) folderFailures.push(childPath)
      await processNode(childNode, childId || folderId, childPath)
    }
  }

  await processNode(root, targetFolder.id, '')

  bgUploading.value = false
  bgUploadJustDone.value = true
  setTimeout(() => { bgUploadJustDone.value = false }, 3000)
  showUploadSummary(buildUploadSummary({ fileCount: files.length, failures, noText, folderFailures, skipped }))
  await loadTree()
  await refreshDocView()
}

/** 上传汇总通知正文样式（内联，理由见 showUploadSummary） */
const UPLOAD_SUMMARY_STYLE = {
  maxHeight: '240px',
  overflowY: 'auto',
  fontSize: 'var(--gt-font-size-xs)',
  lineHeight: '1.6',
  wordBreak: 'break-all',
} as const

/**
 * 上传结束汇总：有失败 / 无正文 / 子文件夹失败时用通知逐条列出原因（不会像 toast 一闪而过）；
 * 全部顺利时只给轻提示。旧实现只报「N 失败」，原因只在浏览器控制台里。
 */
function showUploadSummary(summary: UploadSummary) {
  if (!summary.lines.length) {
    ElMessage.success(summary.title)
    return
  }
  ElNotification({
    title: summary.title,
    // 🔴 样式必须内联：这里的 h() 在渲染上下文之外调用，VNode 不带本组件 scopeId，
    //    通知又挂在 body 下 ⇒ <style scoped> 里的规则永远匹配不到（失败多时列表会撑出屏幕）
    message: h('div', { class: 'gt-kb-upload-summary', style: UPLOAD_SUMMARY_STYLE },
      summary.lines.map((line) => h('div', line))),
    type: summary.level,
    duration: 0,
  })
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
      await api.put(P_kl.folderRename(renameTargetId.value), {
        name: renameNewName.value.trim(),
      })
    } else {
      await api.put(P_kl.documentDetail(renameTargetId.value), {
        name: renameNewName.value.trim(),
      })
    }
    ElMessage.success('重命名成功')
    showRename.value = false
    await loadTree()
    await refreshDocView()
  } catch (e: any) { handleApiError(e, '重命名') }
  finally { renameLoading.value = false }
}

// ── 删除文件夹 ──
async function onDeleteFolder(folder: any) {
  await confirmDangerous(
    `确认删除文件夹「${folder.name}」及其所有内容？此操作不可恢复。`,
    '删除确认',
  )
  try {
    await api.delete(P_kl.folderDelete(folder.id))
    ElMessage.success('文件夹已删除')
    // 被删的是当前文件夹或其祖先 → refreshDocView 在新树里找不到它，自动清空选择
    await loadTree()
    await refreshDocView()
  } catch (e: any) { handleApiError(e, '删除') }
}

// ── 删除文档 ──
async function onDeleteDoc(doc: any) {
  await confirmDelete(`文档「${doc.name}」`)
  try {
    await api.delete(P_kl.documentDetail(doc.id))
    ElMessage.success('已删除')
    if (previewDoc.value?.id === doc.id) previewDoc.value = null
    await loadTree()
    await refreshDocView()
  } catch (e: any) { handleApiError(e, '删除') }
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
    const params: Record<string, string> = { q: searchKeyword.value }
    // 注入当前底稿上下文做相关性加权
    if (currentWpContext.value) {
      params.context = currentWpContext.value
    }
    const data = await api.get(P_kl.search, { params })
    const results = Array.isArray(data) ? data : (data || [])
    documents.value = results
    selectedDocIds.value = []
    // 搜索视图没有 id：不能作为上传 / 新建子文件夹的目标（canCreateInSelected 为假）
    selectedFolder.value = {
      name: `搜索结果: "${searchKeyword.value}" (${results.length} 条)`,
      isSearch: true,
      keyword: searchKeyword.value,
    }
  } catch (e: any) { handleApiError(e, '搜索') }
  finally { searchLoading.value = false }
}

/**
 * 刷新当前文档视图（调用方先 loadTree）：真实文件夹按 id 在新树里重新定位后列目录
 * （节点的 can_create / doc_count 随之更新；已不在树里 → 清空选择），搜索视图重跑搜索。
 * 旧实现直接拿搜索视图对象去列目录 → 请求 `/folders/undefined/documents`。
 */
async function refreshDocView() {
  const cur = selectedFolder.value
  if (!cur) return
  if (cur.id) {
    const fresh = findFolderNode(folderTree.value, cur.id)
    if (fresh) {
      await onFolderClick(fresh)
    } else {
      selectedFolder.value = null
      documents.value = []
    }
  } else if (cur.isSearch && cur.keyword) {
    searchKeyword.value = cur.keyword
    await onSearch()
  }
}

// ── 批量选择与删除 ──
const selectedDocIds = ref<string[]>([])

function onDocSelectionChange(rows: any[]) {
  selectedDocIds.value = rows.map((r: any) => r.id)
}

function errorStatus(e: any): number {
  return Number(e?.response?.status || e?.status || 0)
}

async function onBatchDelete() {
  await confirmBatch('删除', selectedDocIds.value.length)
  let deleted = 0
  let denied = 0
  let missing = 0
  let failed = 0
  for (const id of selectedDocIds.value) {
    try {
      // _silent：逐条失败不弹全局 toast，统一在下面汇总（否则 N 条越权就弹 N 次「权限不足」）
      await api.delete(P_kl.documentDetail(id), { _silent: true } as any)
      deleted++
    } catch (e: any) {
      const status = errorStatus(e)
      if (status === 403) denied++
      else if (status === 404) missing++
      else failed++
    }
  }
  if (denied + missing + failed === 0) {
    ElMessage.success(`已删除 ${deleted} 个文档`)
  } else {
    const parts = [`已删除 ${deleted} 个`]
    if (denied) parts.push(`${denied} 个无权删除（仅创建者或系统管理员可删除）`)
    if (missing) parts.push(`${missing} 个已不存在或无权访问`)
    if (failed) parts.push(`${failed} 个删除失败，请稍后重试`)
    ElMessage.warning(parts.join('；'))
  }
  selectedDocIds.value = []
  await loadTree()
  await refreshDocView()
}

// ── 文档预览（右侧面板） ──
const previewDoc = ref<any>(null)
const previewUrl = ref('')
const previewText = ref<string | null>(null)

/** 预览分流认识的扩展名（图片 / PDF / Office / 文本） */
const PREVIEW_EXTS = new Set([
  'jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg', 'pdf',
  'xlsx', 'xls', 'docx', 'doc', 'pptx', 'ppt',
  'txt', 'md', 'csv', 'json', 'xml', 'log',
])

/**
 * 文档扩展名：文件名后缀是已知类型就用它，否则用 file_type。
 * AI 笔记转存的文档名是笔记标题（无后缀，或形如「v1.2」这种非扩展名的点号）、file_type='md'
 * —— 只看文件名会判成「不支持预览」，深链打开笔记时预览面板就是空的。
 */
function docExt(doc: any): string {
  const name = String(doc?.name || '')
  const dot = name.lastIndexOf('.')
  const fromName = dot > 0 ? name.slice(dot + 1).toLowerCase() : ''
  if (PREVIEW_EXTS.has(fromName)) return fromName
  const fromType = String(doc?.file_type || '').toLowerCase().replace(/^\./, '')
  return fromType || fromName
}

function isImageFile(doc: any): boolean {
  return ['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp', 'svg'].includes(docExt(doc))
}

function isPdfFile(doc: any): boolean {
  return docExt(doc) === 'pdf'
}

function isOfficeFile(doc: any): boolean {
  return ['xlsx', 'xls', 'docx', 'doc', 'pptx', 'ppt'].includes(docExt(doc))
}

function isTextFile(doc: any): boolean {
  return ['txt', 'md', 'csv', 'json', 'xml', 'log'].includes(docExt(doc))
}

function getFileEmoji(doc: any): string {
  const ext = docExt(doc)
  if (['xlsx', 'xls'].includes(ext)) return '📊'
  if (['docx', 'doc'].includes(ext)) return '📝'
  if (['pptx', 'ppt'].includes(ext)) return '📽️'
  if (['pdf'].includes(ext)) return '📕'
  return '📄'
}

function onDocRowClick(row: any) {
  onPreviewDoc(row)
}

/**
 * 打开右侧预览。
 * @param prefetched 深链流程已调过预览接口时传入其响应，文本类文档不再重复请求
 */
async function onPreviewDoc(doc: any, prefetched?: any) {
  previewDoc.value = doc
  // 清理旧的 blob URL
  if (previewUrl.value?.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl.value)
  }
  previewUrl.value = ''
  previewText.value = null

  if (isImageFile(doc) || isPdfFile(doc)) {
    // 图片和 PDF 通过携带认证头的请求获取 blob，再生成 object URL
    try {
      const ext = docExt(doc)
      const mimeType = isPdfFile(doc) ? 'application/pdf' : `image/${ext === 'jpg' ? 'jpeg' : (ext || 'jpeg')}`
      const response = await api.get(P_kl.documentDownload(doc.id), { responseType: 'blob' })
      const blob = new Blob([response], { type: mimeType })
      previewUrl.value = URL.createObjectURL(blob)
    } catch (e: any) {
      handleApiError(e, '预览加载')
    }
  } else if (isTextFile(doc)) {
    // 文本文件加载内容
    try {
      const result = prefetched?.id === doc.id ? prefetched : await api.get(P_kl.documentPreview(doc.id))
      previewText.value = result?.content || '（空文件）'
    } catch {
      previewText.value = '加载失败'
    }
  }
  // Office 文件和其他类型在模板中直接显示下载入口
}

async function onDownloadDoc(doc: any) {
  try {
    await downloadFile(P_kl.documentDownload(doc.id), { fileName: doc.name })
  } catch (e: any) { handleApiError(e, '下载') }
}

// 移动文档
async function _onMoveDoc(doc: any) {
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
    await api.put(P_kl.documentMove(doc.id), { target_folder_id: target.id })
    ElMessage.success(`已移动到「${target.name}」`)
    await loadTree()
    await refreshDocView()
  } catch (e: any) { handleApiError(e, '移动') }
}

// 文件夹右键重命名
async function _onFolderContextMenu(folder: any, event: MouseEvent) {
  event.preventDefault()
  const { value } = await ElMessageBox.prompt(`重命名文件夹「${folder.name}」`, '重命名', {
    inputValue: folder.name,
  })
  if (!value || value === folder.name) return
  try {
    await api.put(P_kl.folderRename(folder.id), { name: value })
    ElMessage.success('重命名成功')
    await loadTree()
  } catch (e: any) { handleApiError(e, '重命名') }
}

onMounted(async () => {
  await loadTree()
  // 深链（AI 笔记 / @引用跳转）：目录树就绪后再定位，否则节点查不到
  await applyDeepLink()
  // 首次使用引导
  if (folderTree.value.length === 0) {
    const { showGuide } = await import('@/composables/useWorkflowGuide')
    await showGuide(
      'knowledge_first_use',
      '📚 知识库使用指南',
      `<div style="line-height:1.8;font-size: var(--gt-font-size-sm)">
        <p>知识库用于存储和管理审计参考资料，支持 AI 智能检索。</p>
        <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:8px">建议上传以下资料：</p>
        <ul style="padding-left:18px;margin:4px 0">
          <li>📄 上年审计报告和附注（供 AI 参照生成当年内容）</li>
          <li>📋 底稿模板（致同标准模板已预置）</li>
          <li>📖 会计准则、监管规定等参考文献</li>
          <li>📝 项目专属的工作记录和备忘</li>
        </ul>
        <p style="color: var(--gt-color-info);font-size: var(--gt-font-size-xs);margin-top:8px">💡 点击"初始化预设文件夹"可快速创建标准分类目录</p>
      </div>`,
      '知道了',
    )
  }
})

onBeforeUnmount(() => {
  // 清理 blob URL，防止内存泄漏
  if (previewUrl.value?.startsWith('blob:')) {
    URL.revokeObjectURL(previewUrl.value)
  }
})
</script>

<style scoped>
.gt-knowledge { padding: var(--gt-space-5); }
.gt-kb-banner {
  display: flex; justify-content: space-between; align-items: center;
  background: var(--gt-gradient-primary);
  border-radius: var(--gt-radius-lg);
  padding: 16px 24px; margin-bottom: 16px; color: var(--gt-color-text-inverse);
  position: relative; overflow: hidden;
}
.gt-kb-banner-text h2 { margin: 0 0 2px; font-size: var(--gt-font-size-xl); }
.gt-kb-banner-text p { margin: 0; font-size: var(--gt-font-size-xs); opacity: 0.75; }
.gt-kb-banner-actions { display: flex; gap: 8px; }
.gt-kb-banner-actions .el-button { background: rgba(255,255,255,0.15); border: 1px solid rgba(255,255,255,0.25); color: #fff; }
.gt-kb-body { min-height: 500px; }
.gt-kb-panel { background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md); border: 1px solid var(--gt-color-border-light); padding: 16px; height: 100%; }
.gt-kb-doc-panel { display: flex; flex-direction: column; }
.gt-kb-panel-title { margin: 0 0 12px; font-size: var(--gt-font-size-sm); color: var(--gt-color-text); }
.gt-kb-tree-node { display: flex; align-items: center; gap: 4px; font-size: var(--gt-font-size-sm); }
.gt-kb-doc-count { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); margin-left: 2px; }
.gt-kb-doc-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.gt-kb-doc-header h4 { margin: 0; font-size: var(--gt-font-size-sm); }
.gt-kb-doc-header-actions { display: flex; gap: 8px; }
.gt-kb-placeholder { text-align: center; padding: 60px 0; color: var(--gt-color-text-tertiary); }
/* 文档名 + 搜索结果的所在路径与命中片段 */
.gt-kb-doc-name { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-doc-notext { font-size: var(--gt-font-size-xs); color: var(--gt-color-wheat); white-space: nowrap; }
.gt-kb-doc-path { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-doc-snippet {
  font-size: var(--gt-font-size-xs); color: var(--gt-color-text-secondary); line-height: 1.5;
  white-space: normal; word-break: break-all;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}

/* 文档列表 + 预览分栏 */
.gt-kb-doc-body { display: flex; gap: 12px; flex: 1; min-height: 0; overflow: hidden; }
.gt-kb-doc-table { flex: 1; min-width: 0; overflow: auto; }
.gt-kb-doc-table--narrow { max-width: 55%; }

/* 预览面板 */
.gt-kb-preview-panel {
  width: 45%; min-width: 300px; background: var(--gt-color-bg); border: 1px solid var(--gt-color-border-light);
  border-radius: var(--gt-radius-md); display: flex; flex-direction: column; overflow: hidden;
}
.gt-kb-preview-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 8px 12px; border-bottom: 1px solid var(--gt-color-border-light); background: var(--gt-color-bg-white);
}
.gt-kb-preview-title { font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-primary); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-preview-body { flex: 1; overflow: auto; padding: 0; }
.gt-kb-preview-img { max-width: 100%; height: auto; display: block; margin: 12px auto; }
.gt-kb-preview-iframe { width: 100%; height: 100%; border: none; }
.gt-kb-preview-text {
  margin: 0; padding: 12px 16px; font-size: var(--gt-font-size-xs); line-height: 1.6;
  white-space: pre-wrap; word-break: break-all; color: var(--gt-color-text-primary); font-family: monospace;
}
.gt-kb-preview-office { display: flex; align-items: center; justify-content: center; height: 100%; }

/* 文件夹上传 */
.gt-kb-folder-upload { }
.gt-kb-folder-drop {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  padding: 40px 20px; border: 2px dashed var(--gt-color-border-lighter); border-radius: 8px;
  cursor: pointer; transition: border-color 0.2s;
  color: var(--gt-color-text-regular); font-size: var(--gt-font-size-sm);
}
.gt-kb-folder-drop:hover { border-color: var(--gt-color-primary); }

/* 树节点操作按钮 */
.gt-kb-tree-node { display: flex; align-items: center; gap: 4px; width: 100%; }
.gt-kb-tree-node-name { flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.gt-kb-tree-actions { display: none; margin-left: auto; flex-shrink: 0; }
.gt-kb-tree-node:hover .gt-kb-tree-actions { display: inline-flex; gap: 2px; }
.gt-kb-tree-actions .el-button { padding: 0 2px; font-size: var(--gt-font-size-xs); }

/* 后台上传进度条 */
.gt-kb-upload-bar {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 16px; margin-bottom: 8px;
  background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md);
  border: 1px solid var(--gt-color-border-purple); box-shadow: var(--gt-shadow-sm);
}
.gt-kb-upload-bar-text { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-regular); white-space: nowrap; }
</style>
