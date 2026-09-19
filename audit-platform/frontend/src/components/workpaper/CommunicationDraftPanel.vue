<!--
  CommunicationDraftPanel — A13-5 沟通函草稿生成面板

  功能：
  1. "生成沟通函草稿" 按钮调用 POST communication-draft 端点
  2. 无未更正错报时按钮禁用 + 提示
  3. 展示草稿内容: 条目列表 + 汇总 + 结论
  4. 支持复制到 A10-1 或导出
  5. 已有持久化草稿时直接展示

  Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.7
-->
<template>
  <div class="communication-draft-panel">
    <el-divider content-position="left">沟通函草稿</el-divider>

    <!-- 操作栏 -->
    <div class="communication-draft-panel__actions">
      <el-tooltip
        :content="noMisstatements ? '当前无未更正错报，无需生成沟通函' : '根据当前未更正错报生成管理层沟通函草稿'"
        placement="top"
      >
        <el-button
          type="primary"
          :disabled="noMisstatements"
          :loading="generating"
          @click="generateDraft"
        >
          生成沟通函草稿
        </el-button>
      </el-tooltip>

      <template v-if="draft">
        <el-button @click="copyToClipboard">
          <el-icon><CopyDocument /></el-icon>
          复制内容
        </el-button>
        <el-button @click="exportDraft">
          <el-icon><Download /></el-icon>
          导出
        </el-button>
      </template>
    </div>

    <!-- 空态提示 -->
    <el-alert
      v-if="noMisstatements && !draft"
      type="info"
      :closable="false"
      show-icon
    >
      当前无未更正错报，无需生成沟通函。
    </el-alert>

    <!-- 草稿展示 -->
    <div v-if="draft" class="communication-draft-panel__content">
      <!-- 条目列表 -->
      <el-table :data="draft.items" border size="small" stripe>
        <el-table-column label="序号" prop="seq" width="60" align="center" />
        <el-table-column label="内容说明" prop="description" min-width="180" />
        <el-table-column label="涉及科目" prop="affected_account" width="120" />
        <el-table-column label="金额(元)" prop="amount" width="120" align="right">
          <template #default="{ row }">
            {{ prefs.fmt(row.amount) }}
          </template>
        </el-table-column>
        <el-table-column label="错报类型" prop="misstatement_type" width="100">
          <template #default="{ row }">
            {{ typeLabel(row.misstatement_type) }}
          </template>
        </el-table-column>
        <el-table-column label="管理层原因" prop="management_reason" min-width="160" />
      </el-table>

      <!-- 汇总信息 -->
      <div v-if="draft.summary" class="communication-draft-panel__summary">
        <el-descriptions :column="3" border size="small">
          <el-descriptions-item label="错报总数">
            {{ draft.summary.total_count }} 项
          </el-descriptions-item>
          <el-descriptions-item label="累计金额">
            {{ prefs.fmt(draft.summary.cumulative_amount) }} 元
          </el-descriptions-item>
          <el-descriptions-item label="占重要性比率">
            {{ draft.summary.ratio != null ? (draft.summary.ratio * 100).toFixed(1) + '%' : '—' }}
          </el-descriptions-item>
        </el-descriptions>
      </div>

      <!-- 结论文本 -->
      <div v-if="draft.conclusion_text" class="communication-draft-panel__conclusion">
        <el-card shadow="never">
          <template #header>
            <span>审计师结论</span>
            <el-tag size="small" type="info" style="margin-left: 8px">
              模板 {{ draft.template_type }}
            </el-tag>
          </template>
          <p>{{ draft.conclusion_text }}</p>
        </el-card>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { CopyDocument, Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useProjectStore } from '@/stores/project'
import { api } from '@/services/apiProxy'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
}>()

const route = useRoute()
const projectStore = useProjectStore()

const resolvedProjectId = computed(
  () => (route.params.projectId as string) || '',
)
const resolvedYear = computed(
  () => parseInt(route.query.year as string) || projectStore.year || new Date().getFullYear() - 1,
)

// ─── Types ─────────────────────────────────────────────────────────────────

interface DraftItem {
  seq: number
  description: string
  affected_account: string
  amount: number
  misstatement_type: string
  management_reason: string
}

interface DraftSummary {
  total_count: number
  cumulative_amount: number
  pm?: number
  ratio?: number | null
  conclusion?: string
}

interface CommunicationDraft {
  _format?: string
  template_type: string
  items: DraftItem[]
  summary: DraftSummary
  conclusion_text: string
}

// ─── State ─────────────────────────────────────────────────────────────────

const draft = ref<CommunicationDraft | null>(null)
const generating = ref(false)
const noMisstatements = ref(false)

// ─── Methods ───────────────────────────────────────────────────────────────

const prefs = useDisplayPrefsStore()


function typeLabel(type: string): string {
  switch (type) {
    case 'factual': return '事实性'
    case 'judgmental': return '判断性'
    case 'projected': return '推断性'
    default: return type || '—'
  }
}

/** 加载已持久化的草稿 */
async function loadPersistedDraft() {
  try {
    const resp = await api.get<{ communication_draft?: CommunicationDraft; empty?: boolean }>(
      `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/misstatement-evaluation`,
    )
    // 从 evaluation 结果中尝试获取已存的 draft (存于 A13-5 sheet data)
    if (resp && (resp as any).communication_draft) {
      draft.value = (resp as any).communication_draft
    }
    // 检查是否有未更正错报
    if (resp && (resp as any).total_amount === 0) {
      noMisstatements.value = true
    }
  } catch {
    // 忽略错误 — 降级为无草稿
  }
}

/** 生成沟通函草稿 */
async function generateDraft() {
  if (!resolvedProjectId.value) return
  generating.value = true
  try {
    const result = await api.post<CommunicationDraft | { empty: boolean }>(
      `/api/workpapers/${resolvedProjectId.value}/${resolvedYear.value}/communication-draft`,
    )
    if (result && 'empty' in result && result.empty) {
      noMisstatements.value = true
      ElMessage.info('当前无未更正错报，无需生成沟通函')
      return
    }
    draft.value = result as CommunicationDraft
    ElMessage.success('沟通函草稿生成成功')
  } catch (e: any) {
    ElMessage.error('生成失败: ' + (e?.message || '网络异常'))
  } finally {
    generating.value = false
  }
}

/** 复制草稿到剪贴板 */
async function copyToClipboard() {
  if (!draft.value) return
  const text = buildDraftText(draft.value)
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.warning('复制失败，请手动选择文本')
  }
}

/** 导出草稿为文本文件 */
function exportDraft() {
  if (!draft.value) return
  const text = buildDraftText(draft.value)
  const blob = new Blob([text], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `A13-5_沟通函草稿_${resolvedYear.value}.txt`
  a.click()
  URL.revokeObjectURL(url)
}

/** 构建纯文本格式草稿 */
function buildDraftText(d: CommunicationDraft): string {
  let text = '管理层沟通函 — 未更正错报明细\n'
  text += '═'.repeat(50) + '\n\n'

  for (const item of d.items) {
    text += `${item.seq}. ${item.description}\n`
    text += `   涉及科目: ${item.affected_account}  金额: ${prefs.fmt(item.amount)}元\n`
    text += `   错报类型: ${typeLabel(item.misstatement_type)}\n`
    text += `   管理层原因: ${item.management_reason || '未说明'}\n\n`
  }

  if (d.summary) {
    text += '─'.repeat(50) + '\n'
    text += `汇总: 共 ${d.summary.total_count} 项, 累计金额 ${prefs.fmt(d.summary.cumulative_amount)}元\n`
    if (d.summary.ratio != null) {
      text += `占重要性水平比率: ${(d.summary.ratio * 100).toFixed(1)}%\n`
    }
  }

  if (d.conclusion_text) {
    text += '\n' + '─'.repeat(50) + '\n'
    text += `审计师结论 (模板${d.template_type}):\n${d.conclusion_text}\n`
  }

  return text
}

// ─── Lifecycle ─────────────────────────────────────────────────────────────

onMounted(() => {
  loadPersistedDraft()
})
</script>

<style scoped>
.communication-draft-panel {
  margin-top: 24px;
}
.communication-draft-panel__actions {
  margin-bottom: 16px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.communication-draft-panel__content {
  margin-top: 12px;
}
.communication-draft-panel__summary {
  margin-top: 16px;
}
.communication-draft-panel__conclusion {
  margin-top: 16px;
}
</style>
