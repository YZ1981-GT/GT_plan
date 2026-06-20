<script setup lang="ts">
/**
 * GtRegulatoryLetter — A18-2 与监管层沟通函
 *
 * 结构化 HTML 底稿组件（componentType: regulatory-letter）。
 * 三段式布局：
 *   1. 表头区：监管机构 + 公司名 + 年度
 *   2. 议题卡片区（4 卡片）：适用 Y/N + textarea + 议题3 radio + GtIndexChip
 *   3. 签名区：致同 + 合伙人 + 日期 + 工具栏
 *
 * 数据存储：checklist_responses（item_id: A18-2-001~004 + A18-2-header）
 * debounce 1500ms 自动保存。
 */
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { api } from '@/services/apiProxy'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'

// ─── Types ───
interface TopicDefinition {
  id: string
  seq: number
  title: string
  guidance: string
  hasRadio?: boolean
  radioOptions?: { label: string; value: string }[]
}

interface TopicData {
  applicable: 'Y' | 'N' | ''
  content: string
  radioChoice?: string
  wpRefs: string[]
}

interface HeaderData {
  regulator: string
  companyName: string
  auditYear: string
  partnerName: string
}

// ─── Props / Emits ───
const props = defineProps<{ projectId: string; wpId: string; wpCode?: string }>()
const emit = defineEmits<{ (e: 'save'): void }>()

// ─── State ───
const topics = ref<TopicDefinition[]>([])
const topicDataMap = ref<Record<string, TopicData>>({})
const headerData = ref<HeaderData>({ regulator: '', companyName: '', auditYear: '', partnerName: '' })
const loading = ref(false)
const saving = ref(false)
const saveStatus = ref<'idle' | 'saving' | 'saved' | 'error'>('idle')
let saveTimer: ReturnType<typeof setTimeout> | null = null

// ─── Issue hints (P1) ───
const issueHints = ref<{ topic: string; count: number; titles: string[] }[]>([])
const a8Suggestion = ref<{ suggested_radio: string | null; a8_status: Record<string, string> }>({ suggested_radio: null, a8_status: {} })

// ─── Load suggestions (P1: issue_hints + A8) ───
async function loadSuggestions() {
  try {
    const res = await api.get(`/projects/${props.projectId}/a18/suggestions`)
    const data = res?.data ?? res
    if (data?.issue_hints) {
      const hints = data.issue_hints
      const list: { topic: string; count: number; titles: string[] }[] = []
      if (hints?.fraud?.count) list.push({ topic: 'fraud', count: hints.fraud.count, titles: hints.fraud.items?.map((i: any) => i.title) || [] })
      if (hints?.legal_violation?.count) list.push({ topic: 'violation', count: hints.legal_violation.count, titles: hints.legal_violation.items?.map((i: any) => i.title) || [] })
      issueHints.value = list
    }
    if (data?.a8_suggestion) {
      a8Suggestion.value = data.a8_suggestion
    }
  } catch (e) {
    // non-critical, degrade gracefully
    console.warn('[A18] suggestions load failed:', e)
  }
}

// ─── Computed ───
const completedCount = computed(() =>
  topics.value.filter((t) => {
    const d = topicDataMap.value[t.id]
    if (!d) return false
    if (d.applicable === 'N') return true
    return d.applicable === 'Y' && d.content.trim().length > 0
  }).length,
)

// ─── Load topic definitions ───
async function loadTopicDefinitions() {
  try {
    const { default: defs } = await import('@/data/a18_topic_definitions.json')
    topics.value = defs as TopicDefinition[]
  } catch (e) {
    console.error('[A18] Failed to load topic definitions:', e)
    ElMessage.error('加载议题定义失败')
  }
}

// ─── Load saved data ───
async function loadSavedData() {
  loading.value = true
  try {
    const res = await api.get(`/projects/${props.projectId}/working-papers/${props.wpId}/checklist-responses`)
    const items: { item_id: string; conclusion: string; remark: string }[] = Array.isArray(res) ? res : (res?.data ?? [])
    for (const item of items) {
      if (item.item_id === 'A18-2-header') {
        try {
          const parsed = JSON.parse(item.remark || '{}')
          headerData.value = { ...headerData.value, ...parsed }
        } catch { /* ignore */ }
      } else if (item.item_id.startsWith('A18-2-')) {
        const seq = item.item_id.replace('A18-2-', '')
        const topicId = `topic_${seq}`
        try {
          const parsed = JSON.parse(item.remark || '{}')
          topicDataMap.value[topicId] = {
            applicable: (item.conclusion as 'Y' | 'N' | '') || '',
            content: parsed.content || '',
            radioChoice: parsed.radioChoice || '',
            wpRefs: parsed.wpRefs || [],
          }
        } catch {
          topicDataMap.value[topicId] = { applicable: item.conclusion as 'Y' | 'N' | '', content: item.remark || '', wpRefs: [] }
        }
      }
    }
  } catch (e) {
    console.error('[A18] Load failed:', e)
  } finally {
    loading.value = false
  }
}

// ─── Save with debounce ───
function debouncedSave() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doSave(), 1500)
}

async function doSave() {
  saving.value = true
  saveStatus.value = 'saving'
  try {
    const payload: { item_id: string; conclusion: string; remark: string }[] = []
    // Header
    payload.push({
      item_id: 'A18-2-header',
      conclusion: 'done',
      remark: JSON.stringify(headerData.value),
    })
    // Topics
    for (const topic of topics.value) {
      const d = topicDataMap.value[topic.id]
      if (!d) continue
      const seq = topic.id.replace('topic_', '')
      payload.push({
        item_id: `A18-2-${seq}`,
        conclusion: d.applicable || '',
        remark: JSON.stringify({ content: d.content, radioChoice: d.radioChoice, wpRefs: d.wpRefs }),
      })
    }
    await api.put(
      `/projects/${props.projectId}/working-papers/${props.wpId}/checklist-responses`,
      payload,
    )
    saveStatus.value = 'saved'
    emit('save')
    setTimeout(() => { if (saveStatus.value === 'saved') saveStatus.value = 'idle' }, 2000)
  } catch (e) {
    saveStatus.value = 'error'
    ElMessage.error('保存失败')
  } finally {
    saving.value = false
  }
}

// ─── Auto-fill header (Task 8) ───
async function autoFillHeader() {
  try {
    const project = await api.get(`/projects/${props.projectId}`)
    const p = project?.data ?? project
    headerData.value.companyName = p.client_name || p.name || ''
    if (p.audit_period_end) {
      headerData.value.auditYear = new Date(p.audit_period_end).getFullYear().toString()
    }
    // Partner name from project assignments
    try {
      const assignments = await api.get(`/projects/${props.projectId}/assignments`)
      const list = Array.isArray(assignments) ? assignments : (assignments?.data ?? [])
      const partner = list.find((a: any) => a.role === 'partner' || a.role === '合伙人')
      if (partner) headerData.value.partnerName = partner.staff_name || partner.name || ''
    } catch { /* non-critical */ }
  } catch (e) {
    console.warn('[A18] Auto-fill header failed:', e)
  }
}

// ─── Export Word (P1) ───
async function exportWord() {
  try {
    const check = await api.get(
      `/projects/${props.projectId}/working-papers/${props.wpId}/export-word/check-incomplete`,
    )
    const incomplete = check?.data ?? check
    if (incomplete?.has_incomplete) {
      await ElMessageBox.confirm(
        `存在 ${incomplete.count} 项未完成内容，继续导出可能包含占位符。确认导出？`,
        '未完成项提示',
        { confirmButtonText: '继续导出', cancelButtonText: '返回完善', type: 'warning' },
      )
    }
    const blob = await api.get(
      `/projects/${props.projectId}/working-papers/${props.wpId}/export-word`,
      { responseType: 'blob' },
    )
    const url = URL.createObjectURL(blob as unknown as Blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `A18-2 与监管层沟通函.docx`
    a.click()
    URL.revokeObjectURL(url)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') {
      ElMessage.error('导出失败')
    }
  }
}

// ─── Add wp ref helper ───
function addWpRef(topicId: string) {
  const refVal = prompt('输入底稿索引号（如 A13-1）：')
  if (!refVal?.trim()) return
  if (!topicDataMap.value[topicId]) {
    topicDataMap.value[topicId] = { applicable: 'Y', content: '', wpRefs: [] }
  }
  if (!topicDataMap.value[topicId].wpRefs.includes(refVal.trim())) {
    topicDataMap.value[topicId].wpRefs.push(refVal.trim())
  }
}

// ─── Lifecycle ───
onMounted(async () => {
  await loadTopicDefinitions()
  await loadSavedData()
  // Auto-fill header if empty
  if (!headerData.value.companyName) await autoFillHeader()
  // Load P1 suggestions (non-blocking)
  loadSuggestions()
})

onBeforeUnmount(() => {
  if (saveTimer) { clearTimeout(saveTimer); doSave() }
})

// Watch for changes to trigger debounced save
watch([topicDataMap, headerData], () => debouncedSave(), { deep: true })
</script>

<template>
  <div v-loading="loading" class="gt-regulatory-letter">
    <!-- ═══ 表头区 ═══ -->
    <section class="rl-header">
      <h3 class="rl-section-title">函件信息</h3>
      <el-form label-width="100px" size="default">
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="监管机构">
              <el-input v-model="headerData.regulator" placeholder="如：证监会XX局 / 银保监局" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="公司名称">
              <el-input v-model="headerData.companyName" placeholder="被审计单位全称" />
            </el-form-item>
          </el-col>
        </el-row>
        <el-row :gutter="16">
          <el-col :span="12">
            <el-form-item label="审计年度">
              <el-input v-model="headerData.auditYear" placeholder="2025" />
            </el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="签字合伙人">
              <el-input v-model="headerData.partnerName" placeholder="合伙人姓名" />
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>
    </section>

    <!-- ═══ 议题卡片区 ═══ -->
    <section class="rl-topics">
      <h3 class="rl-section-title">沟通议题（{{ completedCount }}/{{ topics.length }}）</h3>

      <!-- Issue hints banner (P1) -->
      <div v-if="issueHints.length" class="rl-hints-banner">
        <el-alert type="info" :closable="false" show-icon>
          <template #title>
            <span v-for="h in issueHints" :key="h.topic" style="margin-right: 12px;">
              {{ h.topic === 'fraud' ? '舞弊线索' : '违法违规' }}：{{ h.count }} 条
            </span>
            <span style="font-size:12px;color:#999;">（来自问题单启发式，仅供提示）</span>
          </template>
        </el-alert>
      </div>
      <div v-for="topic in topics" :key="topic.id" class="rl-topic-card">
        <div class="rl-topic-header">
          <span class="rl-topic-seq">{{ topic.seq }}</span>
          <span class="rl-topic-title">{{ topic.title }}</span>
          <el-tag
            v-if="topicDataMap[topic.id]?.applicable === 'Y'"
            type="success" size="small"
          >适用</el-tag>
          <el-tag
            v-else-if="topicDataMap[topic.id]?.applicable === 'N'"
            type="info" size="small"
          >不适用</el-tag>
        </div>

        <!-- 提示栏（折叠） -->
        <el-collapse v-if="topic.guidance" v-model="collapseActive">
          <el-collapse-item :name="topic.id" title="准则提示">
            <p class="rl-guidance-text">{{ topic.guidance }}</p>
          </el-collapse-item>
        </el-collapse>

        <!-- 适用性 Y/N -->
        <div class="rl-topic-body">
          <div class="rl-applicable-row">
            <span class="rl-label">是否适用：</span>
            <el-radio-group
              :model-value="topicDataMap[topic.id]?.applicable || ''"
              @update:model-value="(v: string) => {
                if (!topicDataMap[topic.id]) topicDataMap[topic.id] = { applicable: '', content: '', wpRefs: [] }
                topicDataMap[topic.id].applicable = v as 'Y' | 'N'
              }"
            >
              <el-radio value="Y">是</el-radio>
              <el-radio value="N">否（不适用）</el-radio>
            </el-radio-group>
          </div>

          <!-- 议题3 三选一 radio -->
          <div v-if="topic.hasRadio && topicDataMap[topic.id]?.applicable === 'Y'" class="rl-radio-sub">
            <span class="rl-label">结论：</span>
            <el-radio-group
              :model-value="topicDataMap[topic.id]?.radioChoice || ''"
              @update:model-value="(v: string) => {
                if (topicDataMap[topic.id]) topicDataMap[topic.id].radioChoice = v
              }"
            >
              <el-radio
                v-for="opt in topic.radioOptions"
                :key="opt.value"
                :value="opt.value"
              >{{ opt.label }}</el-radio>
            </el-radio-group>
            <span
              v-if="a8Suggestion.suggested_radio && !topicDataMap[topic.id]?.radioChoice"
              class="rl-a8-hint"
            >💡 A8 建议：{{ a8Suggestion.suggested_radio === 'no_inconsistency' ? '未发现不一致' : '存在不一致' }}</span>
          </div>

          <!-- 描述 textarea -->
          <el-input
            v-if="topicDataMap[topic.id]?.applicable === 'Y'"
            v-model="topicDataMap[topic.id]!.content"
            type="textarea"
            :rows="4"
            :placeholder="`描述${topic.title}相关情况…`"
            class="rl-textarea"
          />

          <!-- 底稿引用 GtIndexChip -->
          <div v-if="topicDataMap[topic.id]?.applicable === 'Y'" class="rl-refs">
            <span class="rl-label">关联底稿：</span>
            <GtIndexChip
              v-for="ref in (topicDataMap[topic.id]?.wpRefs || [])"
              :key="ref"
              :value="ref"
              :validate="true"
              :prevent-navigate="false"
            />
            <el-button size="small" text @click="addWpRef(topic.id)">+ 添加引用</el-button>
          </div>
        </div>
      </div>
    </section>

    <!-- ═══ 签名区 ═══ -->
    <section class="rl-signature">
      <div class="rl-signature-block">
        <p>致同会计师事务所（特殊普通合伙）</p>
        <p>签字合伙人：{{ headerData.partnerName || '________' }}</p>
        <p>日期：{{ headerData.auditYear || '____' }} 年 __ 月 __ 日</p>
      </div>
    </section>

    <!-- ═══ 工具栏 ═══ -->
    <div class="rl-toolbar">
      <span class="rl-save-indicator">
        <template v-if="saveStatus === 'saving'">保存中…</template>
        <template v-else-if="saveStatus === 'saved'">✓ 已保存</template>
        <template v-else-if="saveStatus === 'error'">✗ 保存失败</template>
      </span>
      <el-button type="primary" @click="exportWord" :disabled="saving">
        导出 Word
      </el-button>
    </div>
  </div>
</template>



<style scoped>
.gt-regulatory-letter {
  max-width: 900px;
  margin: 0 auto;
  padding: 24px;
}
.rl-section-title {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 16px;
  padding-bottom: 8px;
  border-bottom: 2px solid var(--gt-purple, #4b2d77);
  color: var(--gt-purple, #4b2d77);
}
.rl-header {
  margin-bottom: 24px;
  padding: 16px;
  background: var(--gt-purple-bg, #f4f0fa);
  border-radius: 8px;
}
.rl-topics {
  margin-bottom: 24px;
}
.rl-topic-card {
  margin-bottom: 16px;
  padding: 16px;
  border: 1px solid var(--gt-purple-border, #d8b8ee);
  border-radius: 8px;
  background: #fff;
}
.rl-topic-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.rl-topic-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  background: var(--gt-purple, #4b2d77);
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}
.rl-topic-title {
  font-weight: 600;
  font-size: 14px;
}
.rl-guidance-text {
  font-size: 12px;
  color: #666;
  line-height: 1.6;
  white-space: pre-wrap;
}
.rl-topic-body {
  padding-left: 32px;
}
.rl-applicable-row, .rl-radio-sub, .rl-refs {
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.rl-label {
  font-size: 13px;
  color: #333;
  flex-shrink: 0;
}
.rl-textarea {
  margin-bottom: 12px;
}
.rl-signature {
  margin: 24px 0;
  padding: 16px;
  border-top: 1px solid #e0e0e0;
  text-align: right;
}
.rl-signature-block p {
  margin: 4px 0;
  font-size: 14px;
}
.rl-toolbar {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
  padding: 12px 0;
  border-top: 1px solid #e0e0e0;
}
.rl-save-indicator {
  font-size: 12px;
  color: #999;
}
.rl-hints-banner {
  margin-bottom: 16px;
}
.rl-a8-hint {
  font-size: 12px;
  color: var(--gt-purple, #4b2d77);
  margin-left: 8px;
}
</style>
