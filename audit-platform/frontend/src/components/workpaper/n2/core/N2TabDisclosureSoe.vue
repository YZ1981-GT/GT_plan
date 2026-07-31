<template>
  <div class="n2-tab-disclosure-soe">
    <!-- ═══ 标题 + 同步/跳转/AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">{{ N2_DISCLOSURE_SHEET_NAME.soe }}</h3>
        <el-tag type="success" size="small">国企 变动表</el-tag>
      </div>
      <div class="section-header-right">
        <el-button
          size="small"
          type="success"
          :loading="syncing"
          @click="syncToDisclosureNotes"
        >
          同步到附注（{{ N2_NOTE_SECTION.soe }}）
        </el-button>
        <el-dropdown split-button size="small" type="primary" @click="jumpToNote('soe')">
          ↩ 跳转回附注（{{ N2_NOTE_SECTION.soe }}）
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="jumpToNote('soe')">国企版（{{ N2_NOTE_SECTION.soe }}）</el-dropdown-item>
              <el-dropdown-item @click="jumpToNote('listed')">上市版（{{ N2_NOTE_SECTION.listed }}）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading" @click="handleAI('conclusion')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <GtReviewTrigger :section-id="`N2-附注国企-${N2_NOTE_SECTION.soe}`" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 方法论上下文（源模板口径，不自造）═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>应交税费（国企版 = 变动表）：</strong>
        按税种列示<strong>期初余额 / 本期应交 / 本期已交 / 期末余额</strong>，
        其中<strong>期末余额是公式列</strong>（源模板 <code>=B8+C8-D8</code>，即期初 + 本期应交 − 本期已交），
        不由手工录入。末行合计为四列各自求和。
        🔴 上市版是<strong>双期余额表</strong>（期末 / 上年年末），两版口径不同不可套用。
        数据来源为 N2-2 明细表。
      </div>
    </div>

    <!-- ═══ 披露内部勾稽 ═══ -->
    <WpDisclosureConsistencyPanel
      :results="tables.checks.value"
      :project-id="props.projectId"
      :default-expanded="hasCheckError"
    />

    <!-- ═══ 应交税费（源模板 R7~R23）═══ -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-header">
          <span>应交税费</span>
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

      <div class="source-hint">
        <div>{{ SOURCE_HINT }}</div>
        <div>{{ FORMULA_HINT }}</div>
      </div>
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
        placeholder="说明各税种本期应交与已交的构成、期末余额与 N2-2 明细表的勾稽、异常波动原因及披露完整性..."
        @change="onConclusionChange"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>本页逐字对齐致同源模板 <code>附注披露信息（国企）</code>，是附注 {{ N2_NOTE_SECTION.soe }} 的交付物源</li>
        <li>国企版为<strong>变动表</strong>；<strong>上市版是双期余额表</strong>，两版不可互相套用</li>
        <li>期末余额为公式列（源模板 <code>=B8+C8-D8</code>），逐行由期初 + 本期应交 − 本期已交算出</li>
        <li>合计 = 四列各自求和（源模板 =SUM(B8:B22) 等），由勾稽面板实时校验</li>
        <li>增值税按「应交税费-未交增值税、简易计税、转让金融商品应交增值税、代扣代缴增值税」贷方余额填列</li>
        <li>税种测算与变动分析属审计过程，在 N2-2 明细表与 N2-6~N2-10 测算表，不在披露表列示</li>
        <li>编辑后自动同步到附注（防抖 800ms），也可点「同步到附注」立即推送</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N2TabDisclosureSoe — 应交税费附注披露（国企）
 *
 * Spec: `.kiro/specs/n-cycle-tax-disclosure-alignment/`（R1 / R4 / R6）
 *
 * 结构逐字对齐源模板 `N2 应交税费.xlsx` 的 `附注披露信息（国企）`（A1:K24）：
 * 1 张 5 列变动表（期末余额为行内公式列）+ `合  计` 四列求和 + R24 提示。
 *
 * 🔴 本组件此前列名是自造的（本期计提 / 本期缴纳 ≠ 源模板的 本期应交 / 本期已交），
 * 期末余额是手填而非公式，另有源模板没有的「应缴国有资本收益说明」小节；同步链路完全缺失。
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
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useN2FormData } from '../../composables/useN2FormData'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { N2_DISCLOSURE_SHEET_NAME, N2_NOTE_SECTION } from '../../composables/n2NoteSectionMap'
import { generateWpText } from '../../composables/shared/wpAiText'
import { useN2DisclosureTables } from '../../composables/useN2DisclosureTables'
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

// ─── 源模板只读文案（含中文引号，故只放 script 常量，不进模板属性）───────────

const SOURCE_HINT =
  '【提示：增值税，根据“应交税费-未交增值税、简易计税、转让金融商品应交增值税、代扣代缴增值税”科目贷方余额计算填列。】'

const FORMULA_HINT =
  '勾稽：每行 期末余额 = 期初余额 + 本期应交 − 本期已交（源模板 =B8+C8-D8）；合计 = 该列各税种之和。'

// ─── 上下文 ──────────────────────────────────────────────────────────────────

const router = useRouter()
const auditCtx = useAuditContext()
const isReadonly = computed(() => props.isReadonly ?? false)
const syncing = ref(false)
const aiLoading = ref(false)
const syncYear = computed(() => props.year || auditCtx.year.value || new Date().getFullYear())

const formData = useN2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const tables = useN2DisclosureTables({
  variant: 'soe',
  allResponses: formData.allResponses,
})

const autoSync = useDisclosureAutoSync({ isReadonly: () => isReadonly.value })

const hasCheckError = computed(() => tables.checks.value.some((c) => c.level === 'error'))

// ─── 持久化 ──────────────────────────────────────────────────────────────────

function persistRows(): void {
  formData.debouncedSave(tables.itemIds.taxes, { conclusion: tables.serializeRows() })
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

function onConclusionChange(): void {
  formData.debouncedSave(tables.itemIds.conclusion, { remark: tables.conclusionNote.value || null })
  emitNoteUpdated('conclusion-soe', tables.conclusionNote.value)
  autoSync.scheduleAutoSync(syncToDisclosureNotes)
}

// ─── 附注事件 ────────────────────────────────────────────────────────────────

function emitNoteUpdated(section: string, text?: string): void {
  eventBus.emit('disclosure:note-text-updated', {
    wpCode: 'N2',
    section,
    accountCode: '2221',
    projectId: props.projectId,
    sectionIds: [N2_NOTE_SECTION.soe],
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
      markSynced(dataTableNames(payload.sub_table_data))
      emitNoteUpdated('sync-soe')
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

function jumpToNote(variant: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'N2', variant, syncYear.value)
  if (!route) {
    ElMessage.warning('缺少项目上下文，无法跳转附注')
    return
  }
  router.push(route)
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const AI_PROMPTS: Record<string, string> = {
  taxes:
    '请基于应交税费（国企版变动表）数据给出披露复核建议：税种列示是否完整、'
    + '每行期末余额与「期初 + 本期应交 − 本期已交」是否勾稽、本期应交与本期已交的合理性、'
    + '增值税是否按「应交税费-未交增值税、简易计税、转让金融商品应交增值税、代扣代缴增值税」贷方余额填列。不得虚构数据。',
  conclusion:
    '请撰写国企版应交税费附注披露说明与结论：各税种本期应交与已交的构成、'
    + '期末余额与 N2-2 明细表的勾稽是否一致、异常波动原因、披露完整性。不得虚构数据。',
}

async function handleAI(section: string): Promise<void> {
  if (aiLoading.value) return
  aiLoading.value = true
  try {
    // 🔴 端点/字段契约见 composables/shared/wpAiText.ts（写错会静默空转）
    const text = (await generateWpText({
      wpId: props.wpId,
      section: `n2-disclosure-soe-${section}`,
      prompt: AI_PROMPTS[section] || AI_PROMPTS.conclusion,
      context: {
        章节: N2_NOTE_SECTION.soe,
        审计年度: String(syncYear.value ?? ''),
        合计期初: String(tables.soeTotals.value.opening ?? ''),
        合计本期应交: String(tables.soeTotals.value.payable ?? ''),
        合计本期已交: String(tables.soeTotals.value.paid ?? ''),
        合计期末: String(tables.soeTotals.value.end ?? ''),
        勾稽不一致项数: String(tables.checks.value.filter((c) => c.level === 'error').length),
      },
      existingContent: section === 'conclusion' ? tables.conclusionNote.value : '',
    })).trim()
    if (!text) return
    if (section === 'conclusion') {
      tables.conclusionNote.value = text
      onConclusionChange()
      ElMessage.success('AI 已生成披露说明与结论')
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
  formData.loadData().then(() => {
    tables.restore()
    emitNoteUpdated('auto-refresh-soe')
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
.n2-tab-disclosure-soe { padding: 12px; font-size: var(--wp-font-size, 13px); }

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

.n2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.n2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
