<script setup lang="ts">
/**
 * GtA17Summary — A17-1 重大事项概要汇总
 *
 * 章节导航式 HTML 底稿组件（16 章）。
 * 左侧目录导航（点击跳转 + 完成状态）+ 右侧章节编辑区（提示栏 + textarea）。
 * MVP（A17-core）：纯文本编辑 + 提示栏折叠 + 「从关联模块拉取」按钮壳。
 * debounce 1500ms 自动保存至 checklist_responses 表。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───
interface ChapterDefinition {
  id: string; seq: number; title: string; guidance: string
  data_source: { type: 'auto' | 'manual'; sources: string[]; ready: boolean | string | null }
  required: boolean
}
interface ChapterData { content: string; source_label: string }

// ─── Props / Emits ───
const props = defineProps<{ projectId: string; wpId: string; wpCode?: string }>()
const emit = defineEmits<{
  (e: 'save'): void
  (e: 'chapter-change', chapterId: string, content: string): void
}>()

// ─── State ───
const chapters = ref<ChapterDefinition[]>([])
const chapterDataMap = ref<Record<string, ChapterData>>({})
const activeChapterId = ref('')
const loading = ref(false)
const pulling = ref<string | null>(null)
const collapseActive = ref<string[]>([])

// ─── Save State ───
const saving = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Issue hints (ch15 等含 issue_tickets 数据源) ───
interface IssueHintsPayload {
  fraud?: { count?: number; titles?: string[]; items?: Array<{ title: string }>; note?: string; heuristic_only?: boolean }
  legal?: { count?: number; titles?: string[] }
  legal_violation?: { count?: number; items?: Array<{ title: string }>; note?: string; heuristic_only?: boolean }
}

const issueHints = ref<IssueHintsPayload | null>(null)

const showIssueHints = computed(() => {
  const ch = activeChapter.value
  if (!ch?.data_source?.sources) return false
  return ch.data_source.sources.includes('issue_tickets')
})

const issueHintsLines = computed(() => {
  const hints = issueHints.value
  if (!hints) return [] as string[]
  const lines: string[] = []
  const fraud = hints.fraud
  if (fraud?.count) {
    const titles = fraud.titles || fraud.items?.map(i => i.title) || []
    lines.push(`舞弊相关问题单 ${fraud.count} 条${titles.length ? '：' + titles.slice(0, 5).join('；') : ''}`)
  } else {
    lines.push('舞弊相关问题单：0 条')
  }
  const legal = hints.legal_violation || hints.legal
  if (legal?.count) {
    const titles = (legal as any).titles || (legal as any).items?.map((i: any) => i.title) || []
    lines.push(`违规相关问题单 ${legal.count} 条${titles.length ? '：' + titles.slice(0, 5).join('；') : ''}`)
  }
  const note = fraud?.note || (hints.legal_violation as any)?.note
  if (note) lines.push(String(note))
  return lines
})

async function loadIssueHints() {
  if (!props.projectId) return
  try {
    const res = await api.get(`/api/projects/${props.projectId}/issue-hints`)
    issueHints.value = (res as IssueHintsPayload) || null
  } catch {
    issueHints.value = null
  }
}

// ─── AI Assist State ───
const aiEnabled = ref(false)
const aiLoading = ref(false)
const aiDialogVisible = ref(false)
const aiDraft = ref('')
const aiError = ref('')

// ─── Computed ───
const activeChapter = computed(() => chapters.value.find((ch) => ch.id === activeChapterId.value))
const activeContent = computed({
  get: () => chapterDataMap.value[activeChapterId.value]?.content ?? '',
  set: (val: string) => {
    if (!chapterDataMap.value[activeChapterId.value])
      chapterDataMap.value[activeChapterId.value] = { content: '', source_label: '' }
    chapterDataMap.value[activeChapterId.value].content = val
    emit('chapter-change', activeChapterId.value, val)
    debouncedSave(activeChapterId.value)
  },
})
const activeSourceLabel = computed(() => chapterDataMap.value[activeChapterId.value]?.source_label || '')

function isChapterFilled(chId: string): boolean {
  return !!(chapterDataMap.value[chId]?.content?.trim())
}
function canPull(ch: ChapterDefinition): boolean {
  return ch.data_source.type === 'auto' && (ch.data_source.ready === true || ch.data_source.ready === 'partial')
}

// ─── Debounce Save ───
async function saveChapter(chapterId: string) {
  if (!props.projectId || !props.wpId || !chapterId) return
  const data = chapterDataMap.value[chapterId]
  if (!data) return

  saving.value = true
  saveStatus.value = 'saving'
  try {
    await api.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items: [{
        item_id: chapterId,
        conclusion: null,
        remark: data.content,
        wp_ref: data.source_label || null,
      }],
    })
    saveStatus.value = 'saved'
    emit('save')
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch (err: any) {
    saveStatus.value = 'error'
    const msg = err?.message || ''
    if (msg !== 'canceled' && err?.code !== 'ERR_CANCELED') {
      ElMessage.warning('保存失败，请重试')
    }
  } finally {
    saving.value = false
  }
}

function debouncedSave(chapterId: string) {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => {
    saveTimer = null
    saveChapter(chapterId)
  }, 1500)
}

/** 页面卸载前立即保存未落盘的变更 */
function flushPendingSave() {
  if (saveTimer) {
    clearTimeout(saveTimer)
    saveTimer = null
    // 同步 sendBeacon 兜底（页面即将关闭时 async 不可靠）
    const chId = activeChapterId.value
    const data = chapterDataMap.value[chId]
    if (chId && data && props.projectId && props.wpId) {
      const payload = JSON.stringify({
        project_id: props.projectId,
        items: [{
          item_id: chId,
          conclusion: null,
          remark: data.content,
          wp_ref: data.source_label || null,
        }],
      })
      const url = `/api/workpapers/${props.wpId}/checklist-responses`
      if (navigator.sendBeacon) {
        navigator.sendBeacon(url, new Blob([payload], { type: 'application/json' }))
      }
    }
  }
}

// ─── AI Assist ───
async function checkAiEnabled() {
  try {
    const resp = await api.get('/api/feature-flags') as any
    const flags = resp?.flags || resp || {}
    aiEnabled.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch { aiEnabled.value = false }
}

async function handleAiGenerate() {
  if (!activeChapter.value) return
  aiDraft.value = ''
  aiError.value = ''
  aiDialogVisible.value = true
  aiLoading.value = true
  try {
    const result = await api.post(`/api/a17/chapters/${activeChapter.value.id}/ai-generate`, {
      project_id: props.projectId,
      user_hint: '',
    }) as { draft?: string; error?: string }
    if (result?.error) { aiError.value = result.error }
    else if (result?.draft) { aiDraft.value = result.draft }
    else { aiError.value = '未获取到生成内容' }
  } catch (err: any) { aiError.value = err?.message || 'AI 服务请求失败' }
  finally { aiLoading.value = false }
}

function adoptAiDraft() {
  if (aiDraft.value && activeChapterId.value) {
    activeContent.value = aiDraft.value
    aiDialogVisible.value = false
    ElMessage.success('已采纳 AI 建议稿')
  }
}

// ─── Data Loading ───
async function loadChapterDefinitions() {
  try {
    const data = await api.get('/api/a17/chapter-definitions')
    chapters.value = (data as ChapterDefinition[]) || []
    if (chapters.value.length > 0 && !activeChapterId.value)
      activeChapterId.value = chapters.value[0].id
  } catch (err: any) { ElMessage.error('加载章节定义失败: ' + (err?.message || '')) }
}

async function loadResponses() {
  if (!props.projectId || !props.wpId) return
  loading.value = true
  try {
    const data = await api.get(`/api/workpapers/${props.wpId}/checklist-responses`, {
      params: { project_id: props.projectId },
    })
    const records = (data as Array<{ item_id: string; remark: string | null; wp_ref: string | null }>) || []
    for (const rec of records) {
      if (rec.item_id?.startsWith('A17-1-ch'))
        chapterDataMap.value[rec.item_id] = { content: rec.remark || '', source_label: rec.wp_ref || '' }
    }
  } catch (err: any) { ElMessage.error('加载章节数据失败: ' + (err?.message || '')) }
  finally { loading.value = false }
}

// ─── Navigation ───
function selectChapter(chId: string) {
  activeChapterId.value = chId
  nextTick(() => {
    document.getElementById(`a17-chapter-${chId}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

// ─── Pull Data ───
async function handlePull(ch: ChapterDefinition) {
  if (!canPull(ch)) { ElMessage.warning('该章节数据源未就绪'); return }
  pulling.value = ch.id
  try {
    const result = (await api.post(`/api/a17/chapters/${ch.id}/pull`, {
      project_id: props.projectId, wp_id: props.wpId,
    })) as { content?: string; source_label?: string }
    if (result?.content) {
      if (!chapterDataMap.value[ch.id])
        chapterDataMap.value[ch.id] = { content: '', source_label: '' }
      chapterDataMap.value[ch.id].content = result.content
      chapterDataMap.value[ch.id].source_label = result.source_label || ''
      ElMessage.success('拉取成功')
      emit('chapter-change', ch.id, result.content)
      debouncedSave(ch.id)
    } else { ElMessage.info('暂无可拉取的数据') }
  } catch (err: any) { ElMessage.error('拉取失败: ' + (err?.message || '')) }
  finally { pulling.value = null }
}

// ─── Lifecycle ───
onMounted(async () => {
  await loadChapterDefinitions()
  await loadResponses()
  await loadIssueHints()
  checkAiEnabled()
})
onBeforeUnmount(() => { flushPendingSave() })
watch(() => [props.projectId, props.wpId], async () => {
  if (props.projectId && props.wpId) await loadResponses()
})
</script>

<template>
  <div class="gt-a17-summary" v-loading="loading">
    <!-- 左侧目录导航 -->
    <aside class="gt-a17-summary__nav">
      <div class="gt-a17-summary__nav-title">章节目录</div>
      <el-scrollbar height="calc(100vh - 160px)">
        <div v-for="ch in chapters" :key="ch.id"
          class="gt-a17-summary__nav-item"
          :class="{ 'is-active': activeChapterId === ch.id, 'is-filled': isChapterFilled(ch.id) }"
          @click="selectChapter(ch.id)">
          <span class="nav-item__indicator" :class="{ filled: isChapterFilled(ch.id) }" />
          <span class="nav-item__seq">{{ ch.seq }}.</span>
          <span class="nav-item__title">{{ ch.title }}</span>
        </div>
      </el-scrollbar>
    </aside>
    <!-- 右侧章节编辑区 -->
    <main class="gt-a17-summary__main">
      <template v-if="activeChapter">
        <div :id="`a17-chapter-${activeChapter.id}`" class="gt-a17-summary__chapter">
          <div class="gt-a17-summary__chapter-title">
            <span class="chapter-seq">{{ activeChapter.seq }}.</span>
            {{ activeChapter.title }}
            <el-tag v-if="activeChapter.required" type="danger" size="small" effect="plain">必填</el-tag>
          </div>
          <!-- 提示栏（折叠面板，不导出） -->
          <el-collapse v-model="collapseActive" class="gt-a17-summary__guidance">
            <el-collapse-item title="编制说明" :name="activeChapter.id">
              <div class="guidance-content">{{ activeChapter.guidance }}</div>
              <div v-if="activeChapter.data_source.type === 'auto'" class="guidance-sources">
                <span class="guidance-sources__label">数据来源：</span>
                <el-tag v-for="src in activeChapter.data_source.sources" :key="src"
                  size="small" effect="plain">{{ src }}</el-tag>
              </div>
              <div v-if="showIssueHints && issueHintsLines.length" class="guidance-issue-hints">
                <el-alert type="warning" :closable="false" show-icon title="问题单提示（启发式，仅供编制参考）">
                  <ul class="guidance-issue-hints__list">
                    <li v-for="(line, idx) in issueHintsLines" :key="idx">{{ line }}</li>
                  </ul>
                </el-alert>
              </div>
            </el-collapse-item>
          </el-collapse>
          <!-- 操作栏 -->
          <div class="gt-a17-summary__action-bar">
            <el-button size="small" :type="canPull(activeChapter) ? 'primary' : 'info'"
              :loading="pulling === activeChapter.id" :disabled="!canPull(activeChapter)"
              @click="handlePull(activeChapter)">从关联模块拉取</el-button>
            <el-button v-if="aiEnabled" size="small" type="success"
              :loading="aiLoading" @click="handleAiGenerate">AI 辅助生成</el-button>
            <el-tag v-if="activeSourceLabel" size="small" type="info" effect="plain">
              来源: {{ activeSourceLabel }}
            </el-tag>
            <span class="gt-a17-summary__save-status">
              <span v-if="saveStatus === 'saving'" class="save-status--saving">保存中...</span>
              <span v-else-if="saveStatus === 'saved'" class="save-status--saved">✓ 已保存</span>
              <span v-else-if="saveStatus === 'error'" class="save-status--error">保存失败</span>
            </span>
          </div>
          <!-- 正文编辑区 -->
          <el-input v-model="activeContent" type="textarea"
            :autosize="{ minRows: 8, maxRows: 24 }" placeholder="请输入本章节内容..."
            class="gt-a17-summary__textarea" />
        </div>
      </template>
      <div v-else class="gt-a17-summary__empty">请从左侧目录选择章节开始编辑</div>
    </main>
    <!-- AI 预览弹窗 -->
    <el-dialog v-model="aiDialogVisible" title="AI 辅助生成预览" width="600px" :close-on-click-modal="false">
      <div v-if="aiLoading" class="gt-a17-summary__ai-loading">
        <el-icon class="is-loading"><i class="el-icon-loading" /></el-icon>
        <span>正在生成建议稿...</span>
      </div>
      <div v-else-if="aiError" class="gt-a17-summary__ai-error">{{ aiError }}</div>
      <el-input v-else v-model="aiDraft" type="textarea" readonly :autosize="{ minRows: 6, maxRows: 16 }" />
      <template #footer>
        <el-button @click="aiDialogVisible = false">关闭</el-button>
        <el-button type="primary" :disabled="!aiDraft || aiLoading" @click="adoptAiDraft">采纳</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.gt-a17-summary { display: flex; height: 100%; background: var(--gt-color-bg-white); border-radius: var(--gt-radius-md); overflow: hidden; }
/* ─── 左侧导航 ─── */
.gt-a17-summary__nav { width: 220px; min-width: 220px; border-right: 1px solid var(--gt-color-border); background: var(--gt-color-bg-elevated); display: flex; flex-direction: column; }
.gt-a17-summary__nav-title { padding: var(--gt-space-3) var(--gt-space-4); font-size: var(--gt-font-size-sm); font-weight: 600; color: var(--gt-color-text-secondary); border-bottom: 1px solid var(--gt-color-border-light); }
.gt-a17-summary__nav-item { display: flex; align-items: center; padding: var(--gt-space-2) var(--gt-space-3); cursor: pointer; font-size: var(--gt-font-size-xs); color: var(--gt-color-text); transition: background var(--gt-transition-fast); gap: var(--gt-space-1); line-height: 1.4; }
.gt-a17-summary__nav-item:hover { background: var(--gt-color-primary-bg); }
.gt-a17-summary__nav-item.is-active { background: var(--gt-color-primary-bg); color: var(--gt-color-primary); font-weight: 600; border-left: 3px solid var(--gt-color-primary); }
.nav-item__indicator { width: 8px; height: 8px; border-radius: 50%; border: 1.5px solid var(--gt-color-border); flex-shrink: 0; }
.nav-item__indicator.filled { background: var(--gt-color-success); border-color: var(--gt-color-success); }
.nav-item__seq { flex-shrink: 0; width: 20px; color: var(--gt-color-text-tertiary); }
.nav-item__title { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
/* ─── 右侧主体 ─── */
.gt-a17-summary__main { flex: 1; overflow-y: auto; padding: var(--gt-space-5) var(--gt-space-6); }
.gt-a17-summary__chapter { max-width: 800px; }
.gt-a17-summary__chapter-title { font-size: var(--gt-font-size-lg); font-weight: 600; color: var(--gt-color-text); margin-bottom: var(--gt-space-4); display: flex; align-items: center; gap: var(--gt-space-2); }
.chapter-seq { color: var(--gt-color-primary); font-weight: 700; }
/* ─── 提示栏 ─── */
.gt-a17-summary__guidance { margin-bottom: var(--gt-space-4); border: 1px solid var(--gt-color-border-light); border-radius: var(--gt-radius-sm); }
.gt-a17-summary__guidance :deep(.el-collapse-item__header) { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); padding-left: var(--gt-space-3); height: 36px; background: var(--gt-bg-subtle); }
.gt-a17-summary__guidance :deep(.el-collapse-item__content) { padding: var(--gt-space-3); }
.guidance-content { font-size: var(--gt-font-size-sm); color: var(--gt-color-text-secondary); line-height: var(--gt-line-height-loose); }
.guidance-sources { margin-top: var(--gt-space-2); display: flex; align-items: center; gap: var(--gt-space-1); flex-wrap: wrap; }
.guidance-sources__label { font-size: var(--gt-font-size-xs); color: var(--gt-color-text-tertiary); }
.guidance-issue-hints { margin-top: var(--gt-space-3); }
.guidance-issue-hints__list { margin: var(--gt-space-2) 0 0; padding-left: 18px; font-size: var(--gt-font-size-sm); line-height: 1.6; }
/* ─── 操作栏 ─── */
.gt-a17-summary__action-bar { display: flex; align-items: center; gap: var(--gt-space-3); margin-bottom: var(--gt-space-3); }
.gt-a17-summary__save-status { margin-left: auto; font-size: var(--gt-font-size-xs); line-height: 1; }
.save-status--saving { color: var(--gt-color-text-tertiary); }
.save-status--saved { color: var(--gt-color-success); }
.save-status--error { color: var(--gt-color-danger); }
/* ─── 文本编辑区 ─── */
.gt-a17-summary__textarea :deep(.el-textarea__inner) { font-size: var(--gt-font-size-base); line-height: var(--gt-line-height-loose); font-family: var(--gt-font-family); border-radius: var(--gt-radius-sm); }
.gt-a17-summary__textarea :deep(.el-textarea__inner:focus) { border-color: var(--gt-color-primary); box-shadow: 0 0 0 2px rgba(75, 45, 119, 0.1); }
/* ─── 空状态 ─── */
.gt-a17-summary__empty { display: flex; align-items: center; justify-content: center; height: 200px; color: var(--gt-color-text-tertiary); }
/* ─── AI 弹窗 ─── */
.gt-a17-summary__ai-loading { display: flex; align-items: center; gap: var(--gt-space-2); padding: var(--gt-space-4); color: var(--gt-color-text-secondary); }
.gt-a17-summary__ai-error { padding: var(--gt-space-3); color: var(--gt-color-danger); font-size: var(--gt-font-size-sm); }
</style>
