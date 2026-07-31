<template>
  <div class="n5-disclosure-body" :class="`n5-disc-${props.variant}`">
    <!-- ═══ 标题 + 同步/跳转/AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N5_DISCLOSURE_SHEET_NAME[props.variant] }}</h3>
        <el-tag :type="props.variant === 'listed' ? 'primary' : 'warning'" size="small">
          {{ props.variant === 'listed' ? '上市' : '国企' }}
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" type="success" :loading="syncing" @click="syncToDisclosureNotes">
          同步到附注（{{ N5_NOTE_SECTION[props.variant] }}）
        </el-button>
        <el-button size="small" @click="jumpToNote">
          ↩ 跳转回附注（{{ N5_NOTE_SECTION[props.variant] }}）
        </el-button>
        <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="reviewSectionId" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（源模板红字/注，不自造）═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>所得税费用披露（{{ props.variant === 'listed' ? '上市版' : '国企版' }}）：</strong>
        表（1）按当期 / 递延两段列示所得税费用构成；表（2）列示{{ props.variant === 'listed' ? '所得税费用与利润总额的关系' : '会计利润与所得税费用调整过程' }}。
        <br>
        <strong>源模板注：</strong>{{ SOURCE_NOTES.join(' ') }}
      </div>
    </div>

    <!-- ═══ 披露内部勾稽 ═══ -->
    <WpDisclosureConsistencyPanel
      :results="tables.checks.value"
      :project-id="props.projectId"
      :default-expanded="hasCheckError"
    />

    <!-- ═══ 表（1）═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（1）{{ N5_SUB_TABLE_KEYS[props.variant].detail }}</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('detail')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <WpDisclosureSegmentTable
        :label-header="tables.labelHeader.value"
        :columns="tables.columns.value"
        :segments="tables.detailSegments.value"
        :readonly="isReadonly"
        @change-cell="(p: any) => onCell('detail', p)"
        @change-label="(p: any) => onLabel('detail', p)"
        @add-row="() => tables.addRow('detail')"
        @remove-row="(p: any) => onRemove('detail', p)"
      />

      <el-input
        v-model="tables.detailNote.value"
        class="note-input"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明当期所得税与递延所得税的计算依据、与 N5-4 当期所得税费用计算表及 N5-8 递延所得税费用核对表的勾稽..."
        @change="onDetailNoteChange"
      />
    </el-card>

    <!-- ═══ 表（2）═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>（2）{{ RECONCILE_TITLE }}</span>
          <el-button size="small" :loading="aiLoading" @click="handleAI('reconcile')">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>

      <WpDisclosureSegmentTable
        :label-header="tables.labelHeader.value"
        :columns="tables.columns.value"
        :segments="tables.reconcileSegments.value"
        :readonly="isReadonly"
        @change-cell="(p: any) => onCell('reconcile', p)"
        @change-label="(p: any) => onLabel('reconcile', p)"
        @add-row="() => tables.addRow('reconcile')"
        @remove-row="(p: any) => onRemove('reconcile', p)"
      />

      <div class="source-hint">
        <div v-for="(t, i) in SOURCE_NOTES" :key="i">{{ t }}</div>
      </div>

      <el-input
        v-model="tables.reconcileNote.value"
        class="note-input"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="说明各调整项的性质与金额来源、适用税率、不适用项目的删除依据、「其他」金额构成..."
        @change="onReconcileNoteChange"
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
        placeholder="说明所得税费用构成、与 N5-1 审定表及 N5-2 明细表的勾稽、两表间同一金额是否一致、披露完整性..."
        @change="onConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页逐字对齐致同源模板 <code>{{ N5_DISCLOSURE_SHEET_NAME[props.variant] }}</code>，是附注 {{ N5_NOTE_SECTION[props.variant] }} 的交付物源</li>
        <li>表（1）合计 = 各明细行之和（源模板 {{ props.variant === 'listed' ? '=SUM(C9:C10)' : '=SUM(C8:C10)' }}）</li>
        <li><strong>表（2）末行「{{ tables.tailLabel.value }}」是公式行</strong>：= 第二行至倒数第二行之和（<strong>不含首行「利润总额」</strong>，源模板注 1），不可手工录入</li>
        <li>两表间同一金额两处列示：表（2）「{{ tables.tailLabel.value }}」应等于表（1）「合计」，由勾稽面板实时校验</li>
        <li>不适用的调整项可删行；「其他」金额不应过大</li>
        <li>「不可抵扣的成本、费用和损失」「未确认可抵扣亏损和可抵扣暂时性差异的纳税影响」不应为负数</li>
        <li v-if="props.variant === 'soe'">🔴 本页源模板 sheet 名为 <code>附注披露信息（国企</code>（缺右括号，源模板如此），同步 sheet 名与之逐字一致</li>
        <li>编辑后自动同步到附注（防抖 800ms），也可点「同步到附注」立即推送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5DisclosureBody — 所得税费用附注披露（两变体共用实现）
 *
 * Spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`（R3 / R4 / R6）
 *
 * 结构逐字对齐源模板 `N5 所得税费用.xlsx`：两张 3 列表（项目 / 本期发生额 / 上期发生额）
 * + 表（1）`合  计` 公式行 + 表（2）末行公式行 + 源模板注。
 *
 * 🔴 两变体差异只在「章节号 / sheet 名 / 表名 / 行骨架 / 表（2）标题括注」，
 * 列结构与交互完全相同 → 共用本实现，避免两份复制粘贴各自漂移
 * （N2/N4 现状缺陷正是复制粘贴导致的口径互串）。薄壳必须声明全部 prop，
 * 否则 `v-bind="$props"` 转发不到（漏 `projectId` = 同步按钮永久锁死）。
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
import { useN5FormData } from '../../composables/useN5FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import {
  N5_DISCLOSURE_SHEET_NAME,
  N5_NOTE_SECTION,
  N5_SUB_TABLE_KEYS,
  type N5DisclosureVariant,
} from '../../composables/n5NoteSectionMap'
import { generateWpText } from '../../composables/shared/wpAiText'
import { useN5DisclosureTables } from '../../composables/useN5DisclosureTables'
import { dataTableNames, serializeSyncedTableNames } from '../../composables/disclosureSyncedTables'
import WpDisclosureSegmentTable from '../../shared/disclosure/WpDisclosureSegmentTable.vue'
import WpDisclosureConsistencyPanel from '../../shared/disclosure/WpDisclosureConsistencyPanel.vue'

const props = defineProps<{
  variant: N5DisclosureVariant
  wpId: string
  projectId: string
  allResponses?: Map<string, any>
  isReadonly?: boolean
  year?: number
}>()

const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

// ─── 源模板只读文案（含中文引号，只放 script 常量，不进模板属性）─────────────

const SOURCE_NOTES = [
  '1、上表中，所得税费用等于第二行至倒数第二行之和；',
  '2、“对以前期间当期所得税的调整”是指，对以前年度所得税进行汇算清缴的结果与以前年度确认的金额不同而调整本年所得税费用的金额。',
  '3、“不可抵扣的成本、费用和损失”、“未确认可抵扣亏损和可抵扣暂时性差异的纳税影响”不应为负数。',
]

/** 表（2）标题括注逐字取自源模板 */
const RECONCILE_TITLE = computed(() =>
  props.variant === 'listed'
    ? `${N5_SUB_TABLE_KEYS.listed.reconcile}列示如下：（不适用项目可删除，“其他”金额不应过大）`
    : `${N5_SUB_TABLE_KEYS.soe.reconcile}：（国资委格式未要求披露，建议披露）`,
)

const reviewSectionId = computed(
  () => `N5-附注${props.variant === 'listed' ? '上市' : '国企'}-${N5_NOTE_SECTION[props.variant]}`,
)

// ─── 上下文 ──────────────────────────────────────────────────────────────────

const router = useRouter()
const auditCtx = useAuditContext()
const isReadonly = computed(() => props.isReadonly ?? false)
const syncing = ref(false)
const aiLoading = ref(false)
const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

const formData = useN5FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const tables = useN5DisclosureTables({
  variant: props.variant,
  allResponses: formData.allResponses,
})

const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })
const hasCheckError = computed(() => tables.checks.value.some((c) => c.level === 'error'))

// ─── 持久化 ──────────────────────────────────────────────────────────────────

type TableKey = 'detail' | 'reconcile'

function persistRows(table: TableKey): void {
  const itemId = table === 'detail' ? tables.itemIds.detail : tables.itemIds.reconcile
  formData.debouncedSave(itemId, { conclusion: tables.serializeRows(table) })
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onCell(table: TableKey, p: { index: number; key: string; value: number | string }): void {
  tables.setCell(table, p.index, p.key, p.value)
  persistRows(table)
}

function onLabel(table: TableKey, p: { index: number; value: string }): void {
  tables.setLabel(table, p.index, p.value)
  persistRows(table)
}

function onRemove(table: TableKey, p: { index: number }): void {
  tables.removeRow(table, p.index)
  persistRows(table)
}

function onDetailNoteChange(): void {
  formData.debouncedSave(tables.itemIds.detailNote, { remark: tables.detailNote.value || null })
  emitNoteUpdated(`detail-${props.variant}`, tables.detailNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onReconcileNoteChange(): void {
  formData.debouncedSave(tables.itemIds.reconcileNote, {
    remark: tables.reconcileNote.value || null,
  })
  emitNoteUpdated(`reconcile-${props.variant}`, tables.reconcileNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

function onConclusionChange(): void {
  formData.debouncedSave(tables.itemIds.conclusion, {
    remark: tables.conclusionNote.value || null,
  })
  emitNoteUpdated(`conclusion-${props.variant}`, tables.conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 附注事件 ────────────────────────────────────────────────────────────────

function emitNoteUpdated(section: string, text?: string): void {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N5',
    section,
    accountCode: '6801',
    projectId: props.projectId,
    sectionIds: [N5_NOTE_SECTION[props.variant]],
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
  syncing.value = true
  try {
    const payload = tables.buildPayload({ wpId: props.wpId, year: syncYear.value })
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
      // 🔴 只有同步成功后才 markSynced（失败也写会把现存表当孤儿删）
      markSynced(dataTableNames(payload.sub_table_data))
      emitNoteUpdated(`sync-${props.variant}`)
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
  formData.debouncedSave(tables.itemIds.syncedTables, {
    conclusion: serializeSyncedTableNames(names),
  })
}

function jumpToNote(): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'N5', props.variant, syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const AI_PROMPTS: Record<string, string> = {
  detail:
    '请撰写所得税费用明细披露说明：当期所得税与递延所得税的计算依据与金额来源、'
    + '与 N5-4 当期所得税费用计算表及 N5-8 递延所得税费用核对表的勾稽关系。不得虚构数据。',
  reconcile:
    '请撰写所得税费用与利润总额（会计利润）关系的调整过程说明：适用税率依据、'
    + '各调整项的性质与金额来源、不适用项目的删除依据、「其他」金额构成；'
    + '注意不可抵扣的成本费用损失与未确认可抵扣亏损的纳税影响不应为负数。不得虚构数据。',
  conclusion:
    '请撰写所得税费用附注披露说明与结论：所得税费用构成、'
    + '与 N5-1 审定表及 N5-2 明细表的勾稽是否一致、两张披露表间同一金额是否相符、'
    + '有效税率与法定税率差异的主要原因、披露完整性。不得虚构数据。',
}

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    // 🔴 端点/字段契约见 composables/shared/wpAiText.ts（写错会静默空转）
    const text = (await generateWpText({
      wpId: props.wpId,
      section: `n5-disclosure-${props.variant}-${section}`,
      prompt: AI_PROMPTS[section] || AI_PROMPTS.conclusion,
      context: {
        章节: N5_NOTE_SECTION[props.variant],
        审计年度: String(syncYear.value ?? ''),
        表1合计本期: String(tables.detailTotals.value.current ?? ''),
        表2末行本期: String(tables.reconcileTail.value.current ?? ''),
        勾稽不一致项数: String(tables.checks.value.filter((c) => c.level === 'error').length),
      },
      existingContent:
        section === 'conclusion'
          ? tables.conclusionNote.value
          : section === 'detail'
            ? tables.detailNote.value
            : tables.reconcileNote.value,
    })).trim()
    if (!text) return
    if (section === 'detail') {
      tables.detailNote.value = text
      onDetailNoteChange()
    } else if (section === 'reconcile') {
      tables.reconcileNote.value = text
      onReconcileNoteChange()
    } else {
      tables.conclusionNote.value = text
      onConclusionChange()
    }
    ElMessage.success('AI 已生成披露文本')
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}

// ─── 生命周期 ────────────────────────────────────────────────────────────────

function onAdjudicatedRefresh(): void {
  formData.loadData().then(() => {
    tables.restore()
    emitNoteUpdated(`auto-refresh-${props.variant}`)
  })
}

onMounted(async () => {
  await formData.loadData()
  tables.restore()
  eventBus.on('substantive:adjudicated', onAdjudicatedRefresh)
})

onUnmounted(() => {
  eventBus.off('substantive:adjudicated', onAdjudicatedRefresh)
  autoSync.cancelPending()
})
</script>

<style scoped>
.n5-disclosure-body { padding: 12px; font-size: var(--wp-font-size, 13px); }

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
.note-input { margin-top: 12px; }

.n5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
