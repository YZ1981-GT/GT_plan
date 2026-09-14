<template>
  <div class="n4-tab-disclosure-listed">
    <!-- ═══ 标题 + 同步/跳转/AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N4_DISCLOSURE_SHEET_NAME.listed }}</h3>
        <el-tag type="primary" size="small">上市 双期发生额表</el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="success" :loading="syncing" @click="syncToDisclosureNotes">
          同步到附注（{{ N4_NOTE_SECTION.listed }}）
        </el-button>
        <el-button size="small" @click="jumpToNote">
          ↩ 跳转回附注（{{ N4_NOTE_SECTION.listed }}）
        </el-button>
        <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="`N4-附注上市-${N4_NOTE_SECTION.listed}`" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（源模板说明，不自造）═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>税金及附加（上市版）：</strong>
        按税费项目列示本期发生额与上期发生额，末行合计。数据来源为 N4-1 审定表（损益类取发生额）。
        各项税金及附加的<strong>计缴标准详见附注四、税项</strong>，本表不重复列示标准。
        🔴 变动额 / 变动率 / 变动原因属审计过程，在 N4-1 审定表与 N4-2 明细表，源模板披露表不含这三列。
      </div>
    </div>

    <!-- ═══ 披露内部勾稽 ═══ -->
    <WpDisclosureConsistencyPanel
      :results="tables.checks.value"
      :project-id="props.projectId"
      :default-expanded="hasCheckError"
    />

    <!-- ═══ 税金及附加（源模板 R7~R17）═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>税金及附加</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('taxes')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <WpDisclosureSegmentTable
        :label-header="tables.labelHeader.value"
        :columns="tables.columns.value"
        :segments="tables.segments.value"
        :readonly="isReadonly"
        @change-cell="onCell"
        @change-label="onLabel"
        @add-row="tables.addRow"
        @remove-row="onRemove"
      />

      <div class="source-hint">{{ SOURCE_HINT }}</div>
    </el-card>

    <!-- ═══ 计缴标准说明（源模板 R18）═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>计缴标准说明</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('standard')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="tables.standardNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="各项税金及附加的计缴标准详见附注四、税项；如本期有税收优惠、税率变动或新增税种，在此补充说明..."
        @change="onStandardChange"
      />
    </el-card>

    <!-- ═══ 披露说明与结论 ═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>披露说明与结论</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <el-input
        v-model="tables.conclusionNote.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明各税费项目构成、与 N4-1 审定表的勾稽、本期较上期重大变动原因及披露完整性..."
        @change="onConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n4-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页逐字对齐致同源模板 <code>附注披露信息（上市公司）</code>，是附注 {{ N4_NOTE_SECTION.listed }} 的交付物源</li>
        <li>合计 = 各税费项目之和（源模板 =SUM(B8:B16) / =SUM(C8:C16)），由勾稽面板实时校验</li>
        <li>税费项目行可增删；本期无发生额的项目可删除，不要留零行</li>
        <li>损益类科目取<strong>发生额</strong>（非期末余额），科目 6403</li>
        <li>🔴 国企版源模板此节为「附注披露信息：无」→ 国企不披露税金及附加</li>
        <li>编辑后自动同步到附注（防抖 800ms），也可点「同步到附注」立即推送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N4TabDisclosureListed — 税金及附加附注披露（上市公司）
 *
 * Spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`（R2 / R4 / R6）
 *
 * 结构逐字对齐源模板 `N4 税金及附加.xlsx` 的 `附注披露信息（上市公司）`（A1:L18）：
 * 1 张 3 列表（项目 / 本期发生额 / 上期发生额）+ `合  计` 公式行 + R18 说明。
 *
 * 🔴 本组件此前是自造的 **6 列**表（多出变动额 / 变动率 / 变动原因 —— 审计过程列），
 * 且同步链路完全缺失。已按源模板重建。
 */
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
// @ts-ignore
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { useAuditContext } from '@/composables/useAuditContext'
import { buildNoteJumpRoute } from '@/views/composables/noteDisclosureReverseJump'
import { useN4FormData } from '../../composables/useN4FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { N4_DISCLOSURE_SHEET_NAME, N4_NOTE_SECTION } from '../../composables/n4NoteSectionMap'
import { generateWpText } from '../../composables/shared/wpAiText'
import { useN4DisclosureTables } from '../../composables/useN4DisclosureTables'
import { dataTableNames, serializeSyncedTableNames } from '../../composables/disclosureSyncedTables'
import WpDisclosureSegmentTable from '../../shared/disclosure/WpDisclosureSegmentTable.vue'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

/** 源模板 R18（含中文引号风险的文案只放 script 常量，不进模板属性） */
const SOURCE_HINT = '各项税金及附加的计缴标准详见附注四、税项。'

const router = useRouter()
const auditCtx = useAuditContext()
const isReadonly = computed(() => props.isReadonly ?? false)
const syncing = ref(false)
const aiLoading = ref(false)
const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

const formData = useN4FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const tables = useN4DisclosureTables({ allResponses: formData.allResponses })
const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })
const hasCheckError = computed(() => tables.checks.value.some((c) => c.level === 'error'))

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function save(itemId: string, value: { conclusion?: string | null; remark?: string | null }): void {
  formData.debouncedSave(itemId, {
    item_id: itemId,
    conclusion: value.conclusion ?? null,
    remark: value.remark ?? null,
  } as any)
}

function persistRows(): void {
  save(tables.itemIds.taxes, { conclusion: tables.serializeRows() })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onCell(p: { seg: string; index: number; key: string; value: number | string }): void {
  tables.setCell(p.index, p.key, p.value)
  persistRows()
}

function onLabel(p: { seg: string; index: number; value: string }): void {
  tables.setLabel(p.index, p.value)
  persistRows()
}

function onRemove(p: { seg: string; index: number }): void {
  tables.removeRow(p.index)
  persistRows()
}

function onStandardChange(): void {
  save(tables.itemIds.standardNote, { remark: tables.standardNote.value || null })
  emitNoteUpdated('standard-listed', tables.standardNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onConclusionChange(): void {
  save(tables.itemIds.conclusion, { remark: tables.conclusionNote.value || null })
  emitNoteUpdated('conclusion-listed', tables.conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 附注事件 ────────────────────────────────────────────────────────────────

function emitNoteUpdated(section: string, text?: string): void {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N4',
    section,
    accountCode: '6403',
    projectId: props.projectId,
    sectionIds: [N4_NOTE_SECTION.listed],
    ...(text !== undefined ? { text } : {}),
    timestamp: Date.now(),
  } as any)
}

// ─── 同步到附注 ──────────────────────────────────────────────────────────────

async function syncToDisclosureNotes(): Promise<void> {
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法同步')
    return
  }
  const payload = tables.buildPayload({ wpId: props.wpId, year: syncYear.value })
  if (!payload) return
  syncing.value = true
  try {
    const resp: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = resp?.data?.data ?? resp?.data
    if (data?.success) {
      ElMessage.success(
        `已${data.created ? '新建' : '更新'}附注 ${data.section_id}：${data.rows_synced} 行`
        + (data.texts_synced ? `，正文 ${data.texts_synced} 段` : ''),
      )
      // 🔴 只有同步成功后才记录已同步表名（失败也写会把现存表当孤儿删）
      markSynced(dataTableNames(payload.sub_table_data))
      emitNoteUpdated('sync-listed')
    } else {
      ElMessage.error('附注同步返回异常，请重试')
    }
  } catch (err: any) {
    if (err?.code === 'ERR_CANCELED' || err?.name === 'CanceledError' || err?.__CANCEL__) return
    ElMessage.error(`附注同步失败：${err?.response?.data?.detail || err?.message || '未知错误'}`)
  } finally {
    syncing.value = false
  }
}

function markSynced(names: string[]): void {
  tables.syncedTables.value = names
  save(tables.itemIds.syncedTables, { conclusion: serializeSyncedTableNames(names) })
}

function jumpToNote(): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'N4', 'listed', syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const AI_PROMPTS: Record<string, string> = {
  taxes:
    '请基于税金及附加披露表（项目 / 本期发生额 / 上期发生额）给出披露复核建议：'
    + '税费项目列示是否完整、合计与各项目是否勾稽、本期较上期重大变动是否已分析、'
    + '是否存在应在其他科目列示的税费。不得虚构数据。',
  standard:
    '请撰写税金及附加计缴标准说明：各税种的计税依据与税率、本期税收优惠或税率变动情况、'
    + '与附注四、税项的一致性。不得虚构数据。',
  conclusion:
    '请撰写上市公司税金及附加附注披露说明与结论：各税费项目构成、'
    + '与 N4-1 审定表及 N4-2 明细表的勾稽是否一致、本期较上期变动原因、披露完整性。不得虚构数据。',
}

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    // 🔴 端点/字段契约见 composables/shared/wpAiText.ts（写错会静默空转）
    const text = (await generateWpText({
      wpId: props.wpId,
      section: `n4-disclosure-listed-${section}`,
      prompt: AI_PROMPTS[section] || AI_PROMPTS.conclusion,
      context: {
        章节: N4_NOTE_SECTION.listed,
        审计年度: String(syncYear.value ?? ''),
        合计本期: String(tables.totals.value.current ?? ''),
        合计上期: String(tables.totals.value.prior ?? ''),
        勾稽不一致项数: String(tables.checks.value.filter((c) => c.level === 'error').length),
      },
      existingContent: section === 'conclusion' ? tables.conclusionNote.value : '',
    })).trim()
    if (!text) return
    if (section === 'conclusion') {
      tables.conclusionNote.value = text
      onConclusionChange()
      ElMessage.success('AI 已生成披露说明与结论')
    } else if (section === 'standard') {
      tables.standardNote.value = text
      onStandardChange()
      ElMessage.success('AI 已生成计缴标准说明')
    } else {
      const { ElMessageBox } = await import('element-plus')
      await ElMessageBox.alert(text, 'AI 披露复核建议', { confirmButtonText: '知道了' }).catch(() => {})
    }
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────

function onAdjudicatedRefresh(): void {
  formData.selfLoad().then(() => {
    tables.restore()
    emitNoteUpdated('auto-refresh-listed')
  })
}

onMounted(async () => {
  await formData.selfLoad()
  tables.restore()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
  autoSync.cancelPending()
})
</script>

<style scoped>
.n4-tab-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.7; }
.methodology-text strong { color: #b88230; }

.disclosure-card { margin-bottom: 16px; }
.card-header { display: flex; align-items: center; justify-content: space-between; }

.source-hint { margin-top: 10px; padding: 8px 10px; background: #fffbe6; border-left: 3px solid #f7ba2a; border-radius: 0 4px 4px 0; font-size: 12px; color: #8c6d1f; line-height: 1.7; }

.n4-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n4-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n4-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
