<!--
  GtA176ClosingMeeting.vue — A17-6 总结会会议纪要

  升级版：对齐源模板结构
  - 元信息区（被审计单位/期间/编制人/复核人/会议地点/时间/组织者/召集人/记录员）
  - 编制提示（红色提示折叠）
  - 10项会议议题卡片（每项含AI按钮+编制提示折叠+textarea）
  - 双模式: 结构化视图 / 在线编辑(GtOnlyOfficeSheet)
  - 双向回写: 切OO时generate-docx / 切回时sync-from-docx
  - AI功能: 每项议题支持AI生成
-->
<template>
  <div class="gt-a176">
    <!-- Mode Switch + Toolbar -->
    <div class="gt-a176__toolbar">
      <el-segmented
        v-model="mode"
        :options="modeOptions"
        size="small"
      />
      <div class="gt-a176__toolbar-right">
        <el-button
          v-if="mode === '结构化视图' && !props.readonly"
          size="small"
          type="primary"
          :loading="prefillLoading"
          @click="handleAgendaPrefill"
        >⬇ 议程预填</el-button>
        <span class="gt-a176__save-status">
          <template v-if="saveStatus === 'saving'">
            <el-icon class="is-loading"><Loading /></el-icon> 保存中...
          </template>
          <template v-else-if="saveStatus === 'saved' && lastSavedAt">
            ✓ 已保存
          </template>
          <template v-else-if="saveStatus === 'unsaved'">
            ○ 未保存
          </template>
        </span>
      </div>
    </div>

    <!-- Structured View -->
    <div v-if="mode === '结构化视图'" class="gt-a176__content">
      <el-skeleton v-if="loading" :rows="10" animated />

      <template v-else>
        <!-- Meeting Info Card -->
        <el-card class="gt-a176__card" shadow="never">
          <template #header>
            <span class="gt-a176__card-title">会议信息</span>
          </template>
          <div class="gt-a176__meta-grid">
            <div class="gt-a176__meta-item">
              <label>会议地点</label>
              <el-input :model-value="metaInfo.meeting_place" size="small" :disabled="props.readonly" placeholder="会议地点" @change="(v: string) => updateMeta('meeting_place', v)" />
            </div>
            <div class="gt-a176__meta-item">
              <label>会议时间</label>
              <el-date-picker :model-value="metaInfo.meeting_time" type="datetime" size="small" value-format="YYYY-MM-DD HH:mm" :disabled="props.readonly" placeholder="会议时间" style="width:100%" @change="(v: string) => updateMeta('meeting_time', v || '')" />
            </div>
            <div class="gt-a176__meta-item">
              <label>会议组织者</label>
              <el-input :model-value="metaInfo.organizer" size="small" :disabled="props.readonly" placeholder="会议组织者" @change="(v: string) => updateMeta('organizer', v)" />
            </div>
            <div class="gt-a176__meta-item">
              <label>召开会议者</label>
              <el-input :model-value="metaInfo.convener" size="small" :disabled="props.readonly" placeholder="召开会议者" @change="(v: string) => updateMeta('convener', v)" />
            </div>
            <div class="gt-a176__meta-item">
              <label>记录员</label>
              <el-input :model-value="metaInfo.recorder" size="small" :disabled="props.readonly" placeholder="记录员" @change="(v: string) => updateMeta('recorder', v)" />
            </div>
            <div class="gt-a176__meta-item gt-a176__meta-item--wide">
              <label>参会人员</label>
              <el-input :model-value="metaInfo.attendees" size="small" :disabled="props.readonly" placeholder="全体项目组成员（可列示姓名）" @change="(v: string) => updateMeta('attendees', v)" />
            </div>
          </div>
        </el-card>

        <!-- Guidance Banner -->
        <details class="gt-a176__guidance-banner">
          <summary>📋 提示</summary>
          <div class="gt-a176__guidance-banner-body">
            <p>1. 本会议纪要用于记录项目组总结会情况，可根据项目具体情况进行调整。</p>
            <p>2. 总结会要求全体项目组成员参加，并由现场负责人负责记录。</p>
            <p>3. 建议在 A17-5 核对表完成后再召开；10 项议程与 A17-5 / A17-1 / A17-7 等底稿勾稽。</p>
          </div>
        </details>

        <!-- 10 Agenda Items -->
        <el-card
          v-for="item in AGENDA_ITEMS"
          :key="item.index"
          class="gt-a176__card"
          shadow="never"
        >
          <template #header>
            <div class="gt-a176__section-header">
              <span class="gt-a176__card-title">{{ item.index }}. {{ item.title }}</span>
              <el-tag v-if="staleAgendaIndexes.has(item.index)" size="small" type="warning" effect="plain">上游已更新</el-tag>
              <el-button size="small" :loading="aiLoading === item.index" @click="aiGenerate(item.index)">🤖 AI</el-button>
            </div>
          </template>
          <!-- 编制提示 -->
          <details v-if="AGENDA_GUIDANCE[item.index]" class="gt-a176__guidance">
            <summary>📋 编制提示</summary>
            <div class="gt-a176__guidance-body">{{ AGENDA_GUIDANCE[item.index] }}</div>
          </details>
          <!-- 联动索引跳转 -->
          <div v-if="AGENDA_REFS[item.index]" class="gt-a176__refs">
            <span class="gt-a176__refs-label">关联底稿：</span>
            <GtIndexChip v-for="ref in AGENDA_REFS[item.index]" :key="ref" :value="ref" :context-project-id="props.projectId" />
          </div>
          <!-- Agenda textarea -->
          <el-input
            :model-value="agenda[item.index]"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 15 }"
            :disabled="props.readonly"
            :placeholder="`请填写${item.title}相关内容`"
            @change="(v: string) => updateAgenda(item.index, v)"
          />
        </el-card>
      </template>
    </div>

    <!-- Online Edit Mode (OnlyOffice) -->
    <GtOnlyOfficeSheet
      v-else
      :wp-id="props.wpId"
      sheet-name="A17-6"
      :project-id="props.projectId"
      class="gt-a176__oo"
      @fallback="handleOOFallback"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, defineAsyncComponent } from 'vue'
import { Loading } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import {
  useA176ClosingMeeting,
  AGENDA_ITEMS,
  AGENDA_GUIDANCE,
} from './composables/useA176ClosingMeeting'
import { api } from '@/services/apiProxy'
import GtIndexChip from './GtIndexChip.vue'

/** 每项议题关联的底稿索引（用于GtIndexChip跳转） */
const AGENDA_REFS: Record<number, string[]> = {
  1: ['A17-1', 'A17-5'],
  2: ['B50', 'A17-5'],
  3: ['B50'],
  4: ['B22A', 'B22B'],
  5: ['A13', 'B15'],
  6: ['A11', 'A15'],
  7: ['A17-7'],
  8: ['A17-1'],
  9: ['A17-2-1'],
  10: ['A17-5'],
}

const GtOnlyOfficeSheet = defineAsyncComponent(
  () => import('./GtOnlyOfficeSheet.vue'),
)

defineOptions({ name: 'GtA176ClosingMeeting' })

const props = withDefaults(defineProps<{
  wpId: string
  projectId?: string
  readonly?: boolean
}>(), { projectId: '', readonly: false })

// ─── Mode Switch ───
const mode = ref('结构化视图')
const modeOptions = ref(['结构化视图', '在线编辑'])

// ─── Composable ───
const wpIdRef = ref(props.wpId)
const {
  loading,
  metaInfo,
  agenda,
  saveStatus,
  lastSavedAt,
  loadData,
  updateMeta,
  updateAgenda,
  flushPendingSaves,
} = useA176ClosingMeeting(wpIdRef)

// ─── Dual-mode bidirectional sync ───
watch(mode, async (newMode, oldMode) => {
  if (!props.wpId) return
  if (oldMode === '结构化视图' && newMode === '在线编辑') {
    // 结构化 → OO：先flush保存，再生成docx
    await flushPendingSaves()
    try {
      await api.post(`/api/workpapers/${props.wpId}/a176/generate-docx`, {}, { _silent: true } as any)
    } catch { /* OO will load existing file */ }
  } else if (oldMode === '在线编辑' && newMode === '结构化视图') {
    // OO → 结构化：从docx同步回DB
    try {
      await api.post(`/api/workpapers/${props.wpId}/a176/sync-from-docx`, {}, { _silent: true } as any)
    } catch { /* silent */ }
    await loadData(props.wpId)
  }
})

// ─── AI Generate ───
const aiLoading = ref<number | null>(null)
const prefillLoading = ref(false)
const staleAgendaIndexes = ref<Set<number>>(new Set())

async function loadAgendaStale() {
  if (!props.wpId || !props.projectId) {
    staleAgendaIndexes.value = new Set()
    return
  }
  try {
    const data = await api.get<any>('/api/a17/a176/agenda-stale-check', {
      params: { project_id: props.projectId, wp_id: props.wpId },
      _silent: true,
    } as any)
    const s = new Set<number>()
    for (const it of data?.stale_items || []) {
      if (it.agenda_index) s.add(Number(it.agenda_index))
    }
    staleAgendaIndexes.value = s
  } catch {
    staleAgendaIndexes.value = new Set()
  }
}

async function handleAgendaPrefill() {
  if (!props.projectId || props.readonly) return
  prefillLoading.value = true
  try {
    const data = await api.get<any>('/api/a17/a176/agenda-prefill', {
      params: { project_id: props.projectId },
      _silent: true,
    } as any)
    const agendaMap = (data?.agenda || {}) as Record<string, string>
    let filled = 0
    for (let i = 1; i <= 10; i++) {
      const text = (agendaMap[String(i)] || agendaMap[i as any] || '').trim()
      if (!text) continue
      const existing = (agenda.value[i] || '').trim()
      if (existing) continue
      updateAgenda(i, text)
      filled += 1
    }
    if (filled > 0) ElMessage.success(`已预填 ${filled} 项空议程（已有内容未覆盖）`)
    else ElMessage.info('暂无可预填内容，或议程已全部填写')
    await loadAgendaStale()
  } catch {
    ElMessage.warning('议程预填失败')
  } finally {
    prefillLoading.value = false
  }
}

async function aiGenerate(index: number) {
  const item = AGENDA_ITEMS.find(i => i.index === index)
  if (!item) return
  aiLoading.value = index
  try {
    const existingContent = agenda.value[index] || ''
    const res = await api.post<any>(`/api/workpapers/${props.wpId}/a171/ai-generate`, {
      chapter: index,
      chapter_title: `总结会议题${index}: ${item.title}`,
      guidance: AGENDA_GUIDANCE[index] || '',
      existing_content: existingContent,
      knowledge_doc_ids: [],
    }, { _silent: true } as any)
    const content = res?.content || ''
    if (!content) { ElMessage.info('AI 未生成有效内容'); return }
    updateAgenda(index, content)
    ElMessage.success('AI 已生成')
  } catch {
    ElMessage.warning('AI 生成失败，请检查LLM服务是否可用')
  } finally {
    aiLoading.value = null
  }
}

// ─── OO Health Check ───
async function checkOOHealth() {
  try {
    const http = (await import('@/utils/http')).default
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    const healthy = res?.data?.data?.healthy ?? res?.data?.healthy
    if (!healthy) modeOptions.value = ['结构化视图']
  } catch {
    modeOptions.value = ['结构化视图']
  }
}

function handleOOFallback() {
  ElMessage.warning('OnlyOffice 编辑器加载失败，请尝试 docker restart audit-onlyoffice')
}

// ─── Lifecycle ───
onMounted(() => { checkOOHealth(); loadData(props.wpId); loadAgendaStale() })
onBeforeUnmount(() => { flushPendingSaves() })

defineExpose({ reload: () => loadData(props.wpId) })
</script>

<style scoped>
.gt-a176 {
  padding: 16px;
  max-width: 900px;
}

.gt-a176__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.gt-a176__toolbar-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.gt-a176__save-status {
  font-size: 12px;
  color: #909399;
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

.gt-a176__content {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.gt-a176__card {
  border-radius: 8px;
}

.gt-a176__card--meta :deep(.el-card__body) {
  padding: 12px 16px;
}

.gt-a176__card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.gt-a176__section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.gt-a176__meta-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

.gt-a176__meta-grid--4col {
  grid-template-columns: repeat(4, 1fr);
}

.gt-a176__meta-item--span3 {
  grid-column: span 3;
}

.gt-a176__meta-item--wide {
  grid-column: span 2;
}

.gt-a176__meta-grid label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}

.gt-a176__oo {
  height: calc(100vh - 200px);
  min-height: 500px;
}

/* 编制提示 */
.gt-a176__guidance {
  margin-bottom: 8px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 0;
}
.gt-a176__guidance summary {
  cursor: pointer;
  padding: 6px 10px;
  font-size: 12px;
  color: #409eff;
  font-weight: 500;
  user-select: none;
}
.gt-a176__guidance-body {
  padding: 4px 10px 8px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
  white-space: pre-line;
}

/* 联动索引跳转 */
.gt-a176__refs {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.gt-a176__refs-label {
  font-size: 12px;
  color: #909399;
}

/* 顶部提示banner */
.gt-a176__guidance-banner {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 0;
}
.gt-a176__guidance-banner summary {
  cursor: pointer;
  padding: 8px 12px;
  font-size: var(--wp-font-size, 13px);
  color: #e6a23c;
  font-weight: 500;
  user-select: none;
}
.gt-a176__guidance-banner-body {
  padding: 4px 12px 10px;
  font-size: 12px;
  color: #606266;
  line-height: 1.8;
}
.gt-a176__guidance-banner-body p {
  margin: 0 0 4px;
}
</style>
