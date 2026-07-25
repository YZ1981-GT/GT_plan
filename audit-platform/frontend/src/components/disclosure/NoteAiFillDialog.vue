<script setup lang="ts">
/**
 * NoteAiFillDialog — 附注正文 AI 填充 / 参照文档填充对话框
 *
 * spec: disclosure-note-knowledge-ai-enrichment / Task 8
 * 需求: 3.1, 3.2, 3.4, 3.6, 4.1, 4.5, 5.1, 9.3
 *
 * 能力:
 *  - 模式切换: AI 生成(Grounded_Draft) / 参照文档(Reference_Only, 仅展示原文片段供人工引用)
 *  - 参照范围多选: 知识库文档 / 文件夹(可空 = 项目 + Global_KB)
 *  - 触发后端 ai-fill 端点(不落库), 预览 Grounded_Draft + Citation 列表
 *  - Citation 显示 document_name / folder_path, is_stale 标"过期"tag
 *  - 含金额提示"披露数字须与附注表格核对"(Req9.3, Narrative_Only)
 *  - 采纳走 useDocAiChat.adoptContent(治理确认流, 不直接落库)
 *  - 章节被 sectionLocks 锁定时"采纳"禁用(可预览不可写, Req5.1)
 *  - 无命中明确提示"未检索到可参照的知识库文档, 已用通用生成"(degraded=true)
 *
 * 注: 前端调 ai-fill 类端点 http 用 default import(@/utils/http), 非 /ai/generate-text。
 */
import { ref, computed, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useDocAiChat } from '@/composables/useDocAiChat'

interface Citation {
  document_name: string | null
  folder_path: string | null
  snippet: string
  score: number
  source_id: string
  is_stale: boolean
}

interface AiFillResult {
  text: string | null
  citations: Citation[]
  degraded: boolean
  skipped_docs: string[]
}

const props = defineProps<{
  visible: boolean
  projectId: string
  year: number
  noteSection: string
  sectionTitle?: string
  accountName?: string
  /** 该章节是否被 sectionLocks 锁定(锁定时可预览不可采纳, Req3.6/5.1) */
  locked?: boolean
  /** 打开时的默认模式(AI 填充按钮=ai, 参照文档填充按钮=reference) */
  initialMode?: FillMode
}>()

const emit = defineEmits<{
  (e: 'update:visible', v: boolean): void
  (e: 'adopted', payload: { noteSection: string; text: string }): void
}>()

const dialogVisible = computed({
  get: () => props.visible,
  set: (v) => emit('update:visible', v),
})

// ── 模式 ────────────────────────────────────────────────
type FillMode = 'ai' | 'reference'
const mode = ref<FillMode>('ai')

// ── 参照范围(知识库文档/文件夹多选, 懒加载树) ──────────────
const referenceScope = ref<string[]>([])
const docNodeIds = ref<Set<string>>(new Set())
const folderChildren = new Map<string, any[]>()
const treeProps = { label: 'label', children: 'children', isLeaf: 'isLeaf' }

function indexFolders(folders: any[]): void {
  for (const f of folders || []) {
    folderChildren.set(String(f.id), f.children || [])
    indexFolders(f.children || [])
  }
}

function toFolderNode(f: any) {
  return { value: String(f.id), label: `📁 ${f.name}`, isDoc: false, isLeaf: false }
}

function toDocNode(d: any) {
  docNodeIds.value.add(String(d.id))
  return { value: String(d.id), label: `📄 ${d.name}`, isDoc: true, isLeaf: true }
}

async function loadNode(node: any, resolve: (data: any[]) => void): Promise<void> {
  try {
    if (node.level === 0) {
      const res = await http.get('/api/knowledge-library/tree', { _silent: true } as any)
      const folders = (res.data as any[]) || []
      indexFolders(folders)
      resolve(folders.map(toFolderNode))
      return
    }
    const raw = node.data
    if (!raw || raw.isDoc) {
      resolve([])
      return
    }
    const folderId = String(raw.value)
    const subs = (folderChildren.get(folderId) || []).map(toFolderNode)
    let docs: any[] = []
    try {
      const res = await http.get(
        `/api/knowledge-library/folders/${folderId}/documents`,
        { _silent: true } as any,
      )
      docs = ((res.data as any[]) || []).map(toDocNode)
    } catch {
      docs = []
    }
    resolve([...subs, ...docs])
  } catch {
    resolve([])
  }
}

/** 仅取叶子文档 id 作为 doc_filter(过滤掉文件夹 id, 避免后端误判 skipped_docs) */
const docFilter = computed<string[]>(() =>
  referenceScope.value.filter((id) => docNodeIds.value.has(id)),
)

// ── 生成 ────────────────────────────────────────────────
const loading = ref(false)
const result = ref<AiFillResult | null>(null)

async function generate(): Promise<void> {
  loading.value = true
  result.value = null
  try {
    const res = await http.post(
      `/api/disclosure-notes/${props.projectId}/${props.year}/${encodeURIComponent(props.noteSection)}/ai-fill`,
      {
        doc_filter: docFilter.value.length ? docFilter.value : null,
        reference_only: mode.value === 'reference',
      },
    )
    result.value = (res.data as AiFillResult) || null
  } catch {
    ElMessage.error('AI 填充失败, 请稍后重试')
  } finally {
    loading.value = false
  }
}

// ── 结果派生 ────────────────────────────────────────────
const hasCitations = computed(() => (result.value?.citations?.length ?? 0) > 0)
const draftText = computed(() => result.value?.text || '')
/** AI 模式下无任何知识库依据(降级为通用生成) */
const noKnowledgeHit = computed(
  () => mode.value === 'ai' && !!result.value && !hasCitations.value,
)
/** 草稿含金额/数字 → 提示与附注表格核对(Req9.3) */
const draftHasNumber = computed(() => /[0-9]/.test(draftText.value))
const skippedDocs = computed(() => result.value?.skipped_docs || [])

// ── 采纳(走 useDocAiChat.adoptContent 治理确认流) ──────────
const docChat = useDocAiChat({
  docType: 'note',
  docId: computed(() => props.noteSection),
  projectId: computed(() => props.projectId),
  year: computed(() => props.year),
})

const adopting = ref(false)
const canAdopt = computed(
  () => mode.value === 'ai' && !!draftText.value && !props.locked,
)

async function adopt(): Promise<void> {
  if (!canAdopt.value) return
  adopting.value = true
  try {
    const msgId = `notefill_${Date.now()}`
    docChat.messages.value.push({ id: msgId, role: 'assistant', text: draftText.value })
    const { success } = await docChat.adoptContent(msgId)
    if (success) {
      ElMessage.success('已提交采纳(经治理确认流, 未直接落库)')
      emit('adopted', { noteSection: props.noteSection, text: draftText.value })
      dialogVisible.value = false
    } else {
      ElMessage.error('采纳失败, 请稍后重试')
    }
  } finally {
    adopting.value = false
  }
}

// 打开时重置结果, 保留参照范围选择
watch(
  () => props.visible,
  (v) => {
    if (v) {
      result.value = null
      mode.value = props.initialMode ?? 'ai'
    }
  },
  { immediate: true },
)
</script>

<template>
  <el-dialog
    v-model="dialogVisible"
    title="AI 填充附注正文"
    width="720px"
    class="note-ai-fill-dialog"
    :close-on-click-modal="false"
    append-to-body
  >
    <div class="naf-body">
      <div class="naf-section-label">
        章节：<strong>{{ sectionTitle || noteSection }}</strong>
        <span v-if="accountName" class="naf-account">（{{ accountName }}）</span>
      </div>

      <!-- 模式切换 -->
      <div class="naf-row">
        <span class="naf-row-label">填充模式</span>
        <el-radio-group v-model="mode" size="small">
          <el-radio-button value="ai">AI 生成</el-radio-button>
          <el-radio-button value="reference">参照文档（仅原文）</el-radio-button>
        </el-radio-group>
        <span class="naf-mode-hint">
          {{ mode === 'ai' ? '检索知识库参照资料并起草叙述' : '只检索并展示原文片段，供人工引用（不调用 AI 生成）' }}
        </span>
      </div>

      <!-- 参照范围 -->
      <div class="naf-row">
        <span class="naf-row-label">参照范围</span>
        <el-tree-select
          v-model="referenceScope"
          :props="treeProps"
          :load="loadNode"
          lazy
          multiple
          show-checkbox
          node-key="value"
          check-strictly
          collapse-tags
          collapse-tags-tooltip
          clearable
          placeholder="留空 = 项目文档 + 全局知识库"
          class="naf-scope-select"
        />
      </div>

      <div class="naf-actions">
        <el-button type="primary" size="small" :loading="loading" @click="generate">
          {{ mode === 'ai' ? '生成草稿' : '检索参照片段' }}
        </el-button>
      </div>

      <!-- 结果 -->
      <div v-if="result" class="naf-result">
        <!-- 无命中提示(AI 模式降级) -->
        <el-alert
          v-if="noKnowledgeHit"
          type="warning"
          :closable="false"
          show-icon
          title="未检索到可参照的知识库文档，已用通用生成"
          class="naf-alert"
        />

        <!-- 跳过文档提示 -->
        <el-alert
          v-if="skippedDocs.length"
          type="info"
          :closable="false"
          show-icon
          :title="`已跳过 ${skippedDocs.length} 个不可访问的参照文档`"
          class="naf-alert"
        />

        <!-- AI 草稿 -->
        <template v-if="mode === 'ai' && draftText">
          <div class="naf-draft-label">草稿正文</div>
          <div class="naf-draft-text">{{ draftText }}</div>
          <el-alert
            v-if="draftHasNumber"
            type="warning"
            :closable="false"
            show-icon
            title="披露数字须与附注表格核对（AI 仅起草叙述，不产出权威数值）"
            class="naf-alert naf-number-hint"
          />
        </template>

        <!-- 参照模式无原文提示 -->
        <el-empty
          v-if="mode === 'reference' && !hasCitations"
          description="未检索到可参照的原文片段"
          :image-size="60"
        />

        <!-- Citation 列表 -->
        <div v-if="hasCitations" class="naf-citations">
          <div class="naf-citations-title">
            参照来源（{{ result.citations.length }}）
          </div>
          <div
            v-for="(c, idx) in result.citations"
            :key="c.source_id || idx"
            class="naf-citation"
          >
            <div class="naf-citation-head">
              <span class="naf-doc-name">{{ c.document_name || '未命名文档' }}</span>
              <el-tag v-if="c.is_stale" type="danger" size="small" effect="plain">过期</el-tag>
              <span v-if="c.folder_path" class="naf-folder-path">{{ c.folder_path }}</span>
              <span class="naf-score">相关度 {{ (c.score ?? 0).toFixed(2) }}</span>
            </div>
            <div class="naf-snippet">{{ c.snippet }}</div>
          </div>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="naf-footer">
        <el-tooltip
          :disabled="!locked"
          content="该章节被锁定，可预览但不可采纳"
          placement="top"
        >
          <span class="naf-adopt-wrap">
            <el-button
              type="primary"
              size="small"
              :disabled="!canAdopt"
              :loading="adopting"
              @click="adopt"
            >
              采纳草稿
            </el-button>
          </span>
        </el-tooltip>
        <el-button size="small" @click="dialogVisible = false">关闭</el-button>
      </div>
    </template>
  </el-dialog>
</template>

<style scoped>
.note-ai-fill-dialog :deep(.el-dialog__body) {
  padding-top: 8px;
}
.naf-body {
  font-size: 13px;
  color: var(--el-text-color-primary);
}
.naf-section-label {
  font-size: 13px;
  margin-bottom: 12px;
  color: var(--el-text-color-regular);
}
.naf-section-label strong {
  color: var(--el-text-color-primary);
}
.naf-account {
  color: var(--el-text-color-secondary);
}
.naf-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.naf-row-label {
  width: 64px;
  flex: 0 0 64px;
  font-size: 13px;
  color: var(--el-text-color-regular);
}
.naf-mode-hint {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.naf-scope-select {
  flex: 1;
  min-width: 320px;
}
.naf-actions {
  margin-bottom: 12px;
}
.naf-result {
  border-top: 1px dashed var(--el-border-color);
  padding-top: 12px;
}
.naf-alert {
  margin-bottom: 10px;
  font-size: 13px;
}
.naf-number-hint {
  margin-top: 10px;
}
.naf-draft-label,
.naf-citations-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
  margin-bottom: 6px;
}
.naf-draft-text {
  font-size: 13px;
  line-height: 1.7;
  white-space: pre-wrap;
  background: var(--el-fill-color-light);
  border-radius: 6px;
  padding: 10px 12px;
  color: var(--el-text-color-primary);
}
.naf-citations {
  margin-top: 14px;
}
.naf-citation {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 8px;
  background: var(--el-bg-color);
}
.naf-citation-head {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin-bottom: 4px;
}
.naf-doc-name {
  font-size: 13px;
  font-weight: 600;
  color: var(--el-color-primary);
}
.naf-folder-path {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.naf-score {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  margin-left: auto;
}
.naf-snippet {
  font-size: 12px;
  line-height: 1.6;
  color: var(--el-text-color-regular);
  white-space: pre-wrap;
}
.naf-footer {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.naf-adopt-wrap {
  display: inline-block;
}
</style>
