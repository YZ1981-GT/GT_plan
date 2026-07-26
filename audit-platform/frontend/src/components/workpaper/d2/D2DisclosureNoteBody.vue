<script setup lang="ts">
/**
 * D2DisclosureNoteBody — D2 应收账款附注披露底稿页（单一 variant 渲染体）
 *
 * 结构严格对齐附注 五、5（上市）/ 八、5（国企），表名与列头以
 * `composables/d2NoteSectionMap.ts` 常量为唯一真源（同步契约）。
 *
 * 由 D2TabDisclosure.vue 以 :key="variant" 挂载（切换版本即重建，持久化前缀随之切换）。
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useDebounceFn } from '@vueuse/core'
import { Delete, Plus, RefreshLeft } from '@element-plus/icons-vue'
import http from '@/utils/http'
import GtIndexChip from '../GtIndexChip.vue'
import GtReviewTrigger from '../GtReviewTrigger.vue'
import { useD2DisclosureNote } from '../composables/useD2DisclosureNote'
import { useD2AiGenerate } from '../composables/useD2AiGenerate'
import {
  buildD2SyncPayload,
  D2_NOTE_SECTION,
  D2_NOTE_TEXT_SECTIONS,
  D2_TABLE_NAMES,
  type D2DisclosureVariant,
} from '../composables/d2NoteSectionMap'
import type { ChecklistItem, ChecklistResponse } from '../composables/useD2FormData'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { getDisclosureNoteDetail } from '@/services/auditPlatformApi'
import { useAuditContext } from '@/composables/useAuditContext'
import { useD2DisclosureImportExport } from '../composables/useD2DisclosureImportExport'

const props = withDefaults(defineProps<{
  variant: D2DisclosureVariant
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly?: boolean
  applicableStandards?: string[] | null
}>(), { isReadonly: false, applicableStandards: null })

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const isSoeVariant = computed(() => props.variant === 'soe')
/** 审计年度（附注按 audit_year 存储，反向校对读取时需要） */
const { year: auditYear } = useAuditContext()

// ─── 持久化（debounce 2s，与 D1 一致）──────────────────────────────────────────

const pending = ref<ChecklistItem[]>([])
const debouncedSave = useDebounceFn(async () => {
  if (pending.value.length === 0) return
  const items = [...pending.value]
  pending.value = []
  try {
    await http.put(`/api/workpapers/${props.wpId}/checklist-responses`, {
      project_id: props.projectId,
      items,
    })
  } catch {
    // 静默：数据已写入 allResponses，下次编辑会重试
  }
}, 2000)

function save(items: ChecklistItem[]): void {
  pending.value.push(...items)
  debouncedSave()
}

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses) as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = toRef(props, 'wpId') as Ref<string>
const projectIdRef = toRef(props, 'projectId') as Ref<string>
const isReadonlyRef = computed(() => props.isReadonly) as unknown as Ref<boolean>

const {
  agingSegments,
  agingRows,
  detailAgingHasData,
  classRows,
  individualRows, addIndividualRow, removeIndividualRow, updateIndividualRow, importIndividualFromBadDebt,
  portfolios, addPortfolio, renamePortfolio, removePortfolio, updatePortfolioCell,
  otherPortfolioRows, addOtherPortfolioRow, removeOtherPortfolioRow, updateOtherPortfolioRow,
  movementFields, movementEndBalance, movementByCategory,
  reversalRows, addReversalRow, removeReversalRow, updateReversalRow, importReversalFromWriteoffCheck,
  writeOffAmountCell, setWriteOffAmount,
  writeOffRows, addWriteOffRow, removeWriteOffRow, updateWriteOffRow, importWriteOffFromWriteoffCheck,
  top5Rows, top5Total, top5Ratio, addTop5Row, removeTop5Row, updateTop5Row, importTop5FromAnalysis,
  derecognizedRows, addDerecognizedRow, removeDerecognizedRow, updateDerecognizedRow,
  sectionNotes, setNote,
  setOverride, resetOverride,
  inconsistencyWarnings,
  buildSnapshot,
  legacyDisclosureInfo, importFromLegacyDisclosure,
  rehydrate,
} = useD2DisclosureNote({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  variant: props.variant,
  save,
  isReadonly: isReadonlyRef,
})

// ─── 列头文案（口径随 variant）────────────────────────────────────────────────

const endLabel = computed(() => (isSoeVariant.value ? '期末数' : '期末余额'))
const priorLabel = computed(() => (isSoeVariant.value ? '期初数' : '上年年末余额'))
const T = computed(() => (isSoeVariant.value ? D2_TABLE_NAMES.soe : D2_TABLE_NAMES.listed))

const NOTE_TITLES = computed<Record<string, string>>(() => {
  const map: Record<string, string> = {}
  for (const s of D2_NOTE_TEXT_SECTIONS) map[s.key] = s.title
  return map
})

function fmt(v: number): string {
  return displayPrefs.fmtAmount(v)
}
function fmtPct(v: number): string {
  return `${(v || 0).toFixed(2)}%`
}

// ─── AI 辅助 ─────────────────────────────────────────────────────────────────

const ai = useD2AiGenerate(wpIdRef)
const aiLoadingKey = ref('')

function buildAiContext(key: string): Record<string, string> {
  const ctx: Record<string, string> = {
    披露版本: isSoeVariant.value ? '国企版（八、5 应收账款）' : '上市公司版（五、5 应收账款）',
    子节: NOTE_TITLES.value[key] ?? key,
  }
  if (key === 'aging') {
    ctx.账龄结构 = agingRows.value
      .filter((r) => r.kind === 'segment')
      .map((r) => `${r.label}=${r.endAmount.toFixed(2)}`)
      .join('；')
    ctx.小计与坏账 = agingRows.value
      .filter((r) => r.kind !== 'segment')
      .map((r) => `${r.label}=${r.endAmount.toFixed(2)}`)
      .join('；')
  } else if (key === 'badDebtClass') {
    ctx.分类披露 = classRows.value
      .filter((r) => r.kind !== 'hint')
      .map((r) => `${r.label}: 期末=${r.endAmount.toFixed(2)}, ${priorLabel.value}=${r.priorAmount.toFixed(2)}`)
      .join('；')
  } else if (key === 'individual') {
    ctx.单项计提明细 = individualRows.value
      .map((r) => `${r.name || '（未命名）'}=${r.endAmount.toFixed(2)}`)
      .join('；') || '（暂无明细）'
  } else if (key === 'portfolio') {
    ctx.组合计提项目 = portfolios.value
      .map((g) => `${g.name || '（未命名）'}: ${g.rows.map((r) => `${r.label}=${r.endAmount.toFixed(2)}`).join('/')}`)
      .join('；') || '（暂无组合）'
  } else if (key === 'movement') {
    if (isSoeVariant.value) {
      ctx.坏账准备变动 = movementByCategory.value
        .map((r) => `${r.label}: 期初=${r.priorAmount.toFixed(2)}, 变动=${r.changeAmount.toFixed(2)}, 期末=${r.endAmount.toFixed(2)}`)
        .join('；')
    } else {
      ctx.坏账准备变动 = movementFields.value.map((f) => `${f.label}=${f.amount.toFixed(2)}`).join('；')
      ctx.期末余额 = movementEndBalance.value.toFixed(2)
    }
  } else if (key === 'writeOff') {
    ctx.本期实际核销金额 = writeOffAmountCell.value.amount.toFixed(2)
    ctx.重要核销笔数 = String(writeOffRows.value.length)
  } else if (key === 'top5') {
    ctx.前五名 = top5Rows.value
      .map((r) => `${r.companyName || '（未命名）'}=${(r.arAmount + r.contractAssetAmount).toFixed(2)}（占比${fmtPct(top5Ratio(r))}）`)
      .join('；') || '（暂无前五名）'
  }
  return ctx
}

async function handleAiGenerate(key: string): Promise<void> {
  if (props.isReadonly) return
  aiLoadingKey.value = key
  try {
    const text = await ai.generateAndConfirm(
      'disclosure-note',
      sectionNotes.value[key] || '',
      buildAiContext(key),
      `AI 生成「${NOTE_TITLES.value[key] ?? key}」`,
    )
    if (text) {
      setNote(key, text)
      ElMessage.success('已填入说明')
    }
  } finally {
    aiLoadingKey.value = ''
  }
}

/** 工具栏统一入口：按子节生成（与卡片内 🤖 AI 同一路径，仅收敛访问入口） */
const emptyNoteKeys = computed<string[]>(() =>
  D2_NOTE_TEXT_SECTIONS.filter((s) => !String(sectionNotes.value[s.key] ?? '').trim()).map((s) => s.key),
)

async function handleAiFillEmpty(): Promise<void> {
  if (props.isReadonly) return
  const keys = emptyNoteKeys.value
  if (keys.length === 0) {
    ElMessage.info('各子节说明均已填写，无需补全')
    return
  }
  // 逐节走同一确认流（AI 输出需人工确认后才填入），中途取消即停止
  for (const key of keys) {
    aiLoadingKey.value = key
    try {
      const text = await ai.generateAndConfirm(
        'disclosure-note',
        '',
        buildAiContext(key),
        `AI 生成「${NOTE_TITLES.value[key] ?? key}」`,
      )
      if (!text) break
      setNote(key, text)
    } finally {
      aiLoadingKey.value = ''
    }
  }
}

function onAiMenuCommand(cmd: string): void {
  if (cmd === '__empty__') { void handleAiFillEmpty(); return }
  void handleAiGenerate(cmd)
}

// ─── 导入导出（多工作表工作簿：一张披露表一个 worksheet + 说明文本）──────────

const ie = useD2DisclosureImportExport({ wpId: wpIdRef, variant: props.variant })
const fileInputRef = ref<HTMLInputElement | null>(null)

function onIeCommand(cmd: string): void {
  if (cmd === 'template') { void ie.exportTemplate(); return }
  if (cmd === 'data') { void ie.exportData(); return }
  if (cmd === 'import') {
    if (props.isReadonly) return
    fileInputRef.value?.click()
  }
}

async function onImportFileChange(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  const result = await ie.importData(file)
  if (result) {
    // 导入直接写库，本地状态需重新 hydrate → 拉取最新 checklist-responses
    try {
      const res: any = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
      const list: any[] = res?.data?.data ?? res?.data ?? res ?? []
      for (const item of Array.isArray(list) ? list : []) {
        if (item?.item_id) props.allResponses.set(item.item_id, item)
      }
      rehydrate()
    } catch {
      ElMessage.info('导入已写入，请刷新页面查看最新数据')
    }
  }
}

// ─── 动态行新增（需命名的行先 prompt）─────────────────────────────────────────

async function promptAddIndividual(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入债务人/单位名称', '新增单项计提行', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '名称不能为空'),
    })
    addIndividualRow()
    const last = individualRows.value[individualRows.value.length - 1]
    if (last) updateIndividualRow(last.rowId, 'name', value.trim())
  } catch {
    // cancel
  }
}

async function promptAddPortfolio(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入组合名称（如：应收中央企业客户）', '新增组合计提项目', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '组合名称不能为空'),
    })
    addPortfolio(value.trim())
  } catch {
    // cancel
  }
}

async function promptAddOtherPortfolio(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入组合名称', '新增其他组合方法行', {
      confirmButtonText: '添加',
      cancelButtonText: '取消',
      inputValidator: (v: string) => (v && v.trim() ? true : '组合名称不能为空'),
    })
    addOtherPortfolioRow()
    const last = otherPortfolioRows.value[otherPortfolioRows.value.length - 1]
    if (last) updateOtherPortfolioRow(last.rowId, 'name', value.trim())
  } catch {
    // cancel
  }
}

async function promptRenamePortfolio(groupId: string, current: string): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('修改组合名称', '重命名组合', {
      confirmButtonText: '保存',
      cancelButtonText: '取消',
      inputValue: current,
      inputValidator: (v: string) => (v && v.trim() ? true : '组合名称不能为空'),
    })
    renamePortfolio(groupId, value.trim())
  } catch {
    // cancel
  }
}

// ─── 从其他底稿带入 ───────────────────────────────────────────────────────────

function reportImport(count: number, source: string): void {
  if (count > 0) ElMessage.success(`已从 ${source} 带入 ${count} 行`)
  else ElMessage.info(`${source} 暂无可带入数据（或已全部带入）`)
}

// ─── 旧版披露数据（D2-disclosure-*）带入 ─────────────────────────────────────

const legacyDismissed = ref(false)
const hasLegacyData = computed(() => {
  const info = legacyDisclosureInfo.value
  return !legacyDismissed.value && (info.top5 > 0 || info.aging > 0 || info.unmapped.length > 0)
})
const legacyHint = computed(() => {
  const info = legacyDisclosureInfo.value
  const parts: string[] = []
  if (info.top5 > 0) parts.push(`前五名 ${info.top5} 行`)
  if (info.aging > 0) parts.push(`账龄 ${info.aging} 段`)
  const mapped = parts.length > 0 ? `可带入：${parts.join('、')}` : '无可自动带入的区块'
  const unmapped = info.unmapped.length > 0
    ? `；旧版「${info.unmapped.join('、')}」区块为自由文本行，与附注模板固定分类不对应，需人工核对录入`
    : ''
  return `检测到旧版披露页数据。${mapped}${unmapped}`
})

function onImportLegacy(): void {
  const { top5, aging } = importFromLegacyDisclosure()
  if (top5 === 0 && aging === 0) {
    ElMessage.info('旧版数据无可带入项（或已带入 / 已被手工覆盖）')
    return
  }
  const seg: string[] = []
  if (top5 > 0) seg.push(`前五名 ${top5} 行`)
  if (aging > 0) seg.push(`账龄期末 ${aging} 段`)
  ElMessage.success(`已带入 ${seg.join('、')}，请核对后再同步附注`)
}

// ─── 同步到附注 ───────────────────────────────────────────────────────────────

const isSyncing = ref(false)

async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  try {
    const payload = buildD2SyncPayload(
      props.variant,
      props.wpId || '',
      props.applicableStandards ?? null,
      buildSnapshot(),
    )
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D2',
        accountCode: '1122',
        projectId: props.projectId,
        section: props.variant,
        sectionIds: [D2_NOTE_SECTION[props.variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D2_NOTE_SECTION[props.variant]} 应收账款」`)
    await checkNoteConsistency(true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

// ─── 反向校对：附注现存合计 vs 本页合计 ───────────────────────────────────────
// 同步是单向（底稿→附注），但附注侧可能被手工改过或来自另一底稿的旧推送，
// 故提供只读校对：拉附注该章节主表合计与本页分类合计比对，不改附注任何数据。

const noteCheckState = ref<{ status: 'idle' | 'loading' | 'ok' | 'diff' | 'missing' | 'error'; message: string }>({
  status: 'idle',
  message: '',
})

function pickNoteTotal(detail: any): number | null {
  const td = detail?.table_data
  const tables: any[] = Array.isArray(td?._tables) ? td._tables : []
  const candidates = tables.length > 0
    ? tables
    : (Array.isArray(td?.rows) ? [{ rows: td.rows }] : [])
  for (const t of candidates) {
    const rows: any[] = Array.isArray(t?.rows) ? t.rows : []
    const totalRow = rows.find((r) => r?.is_total || String(r?.label ?? '').trim() === '合计')
    if (!totalRow) continue
    const values: any[] = Array.isArray(totalRow.values) ? totalRow.values : []
    for (const v of values) {
      const n = Number(v)
      if (Number.isFinite(n) && n !== 0) return n
    }
  }
  return null
}

async function checkNoteConsistency(silent = false): Promise<void> {
  if (!props.projectId) return
  noteCheckState.value = { status: 'loading', message: '正在读取附注现存数据…' }
  try {
    const detail = await getDisclosureNoteDetail(props.projectId, auditYear.value, D2_NOTE_SECTION[props.variant])
    const noteTotal = pickNoteTotal(detail)
    const pageTotal = classRows.value.find((r) => r.kind === 'total')?.endAmount ?? 0
    if (noteTotal === null) {
      noteCheckState.value = {
        status: 'missing',
        message: `附注「${D2_NOTE_SECTION[props.variant]}」暂无可比对的合计行（尚未同步或附注为空）`,
      }
    } else if (Math.abs(noteTotal - pageTotal) <= 0.01) {
      noteCheckState.value = {
        status: 'ok',
        message: `附注现存合计 ${fmt(noteTotal)} 与本页分类合计一致`,
      }
    } else {
      noteCheckState.value = {
        status: 'diff',
        message: `附注现存合计 ${fmt(noteTotal)} 与本页分类合计 ${fmt(pageTotal)} 不一致（差异 ${fmt(noteTotal - pageTotal)}）：附注可能被手工修改，或本页改动尚未同步`,
      }
    }
    if (!silent) {
      if (noteCheckState.value.status === 'ok') ElMessage.success(noteCheckState.value.message)
      else ElMessage.warning(noteCheckState.value.message)
    }
  } catch {
    noteCheckState.value = { status: 'error', message: '读取附注数据失败（附注可能尚未生成）' }
    if (!silent) ElMessage.warning(noteCheckState.value.message)
  }
}
</script>

<template>
  <div class="d2-disc">
    <!-- 工具栏 -->
    <div class="d2-disc__toolbar">
      <el-tag :type="isSoeVariant ? 'success' : 'primary'" effect="plain" size="small">
        {{ isSoeVariant ? '国企版（八、5）' : '上市公司版（五、5）' }}
      </el-tag>
      <GtIndexChip value="wp:D2-1" :context-project-id="projectId" />
      <GtIndexChip value="wp:D2-3" :context-project-id="projectId" />
      <div class="d2-disc__toolbar-right">
        <GtReviewTrigger :section-id="`D2-disc-${variant}-header`" label="💬 复核" />
        <el-dropdown trigger="click" @command="onAiMenuCommand">
          <el-button
            size="small"
            plain
            :loading="!!aiLoadingKey"
            :disabled="isReadonly || !ai.aiAvailable.value"
            title="按子节生成披露说明（与卡片内 🤖 AI 同一入口）"
          >🤖 AI 说明<span style="margin-left:2px">▾</span></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item
                v-for="s in D2_NOTE_TEXT_SECTIONS"
                :key="s.key"
                :command="s.key"
              >{{ s.title }}<span v-if="!String(sectionNotes[s.key] || '').trim()" style="color:#e6a23c;margin-left:4px">（空）</span></el-dropdown-item>
              <el-dropdown-item command="__empty__" divided :disabled="emptyNoteKeys.length === 0">
                一键补全空白说明（{{ emptyNoteKeys.length }} 节）
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button
          size="small"
          plain
          :loading="noteCheckState.status === 'loading'"
          title="只读比对附注模块该章节现存合计与本页合计，不修改附注"
          @click="checkNoteConsistency(false)"
        >校对附注</el-button>
        <el-dropdown trigger="click" @command="onIeCommand">
          <el-button
            size="small"
            plain
            :loading="ie.busy.value || ie.importing.value"
            title="导入导出手工录入的披露明细表与说明文本（多工作表 xlsx）"
          >📥 导入导出<span style="margin-left:2px">▾</span></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出空白模板</el-dropdown-item>
              <el-dropdown-item command="data">导出当前数据</el-dropdown-item>
              <el-dropdown-item command="import" divided :disabled="isReadonly">导入数据（xlsx）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input
          ref="fileInputRef"
          type="file"
          accept=".xlsx"
          style="display:none"
          @change="onImportFileChange"
        />
        <el-button
          type="success"
          size="small"
          :loading="isSyncing"
          :disabled="isReadonly"
          title="将本页表格与说明文本同步到附注模块"
          @click="syncToDisclosureNotes"
        >同步到附注</el-button>
      </div>
    </div>

    <!-- 附注反向校对结果（只读，不改附注） -->
    <el-alert
      v-if="noteCheckState.status === 'ok' || noteCheckState.status === 'diff' || noteCheckState.status === 'missing'"
      :type="noteCheckState.status === 'ok' ? 'success' : (noteCheckState.status === 'diff' ? 'warning' : 'info')"
      show-icon
      :closable="true"
      class="d2-disc__warn"
      :title="noteCheckState.message"
    />

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon title="审计目标" class="d2-disc__objective">
      <template #default>
        <p>
          按附注 {{ D2_NOTE_SECTION[variant] }}「应收账款」格式编制披露信息：账龄结构、坏账准备计提方法分类、
          单项/组合计提明细、坏账准备变动、重要转回与核销、前五名欠款方，并与 D2-1 审定表、D2-3 坏账准备表勾稽一致（CAS30/CAS22）。
        </p>
      </template>
    </el-alert>

    <!-- 旧版披露数据带入提示（只在检测到旧数据时出现） -->
    <el-alert
      v-if="hasLegacyData"
      type="info"
      show-icon
      class="d2-disc__warn"
      :closable="true"
      @close="legacyDismissed = true"
    >
      <template #title>
        <span style="font-size:13px">{{ legacyHint }}</span>
      </template>
      <template #default>
        <el-button
          size="small"
          type="primary"
          plain
          :disabled="isReadonly || (legacyDisclosureInfo.top5 === 0 && legacyDisclosureInfo.aging === 0)"
          @click="onImportLegacy"
        >一键带入旧版数据</el-button>
      </template>
    </el-alert>

    <!-- 不一致告警 -->
    <el-alert
      v-for="(w, i) in inconsistencyWarnings"
      :key="`warn-${i}`"
      type="warning"
      :closable="false"
      show-icon
      class="d2-disc__warn"
      :title="w"
    />

    <!-- ① 按账龄披露 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ T.aging }}</span>
          <div class="card-head-right">
            <el-tag v-if="detailAgingHasData" type="info" size="small" effect="plain">已取 D2-2 明细账龄</el-tag>
            <el-tag v-else type="warning" size="small" effect="plain">D2-2 明细账龄为空，需手工录入</el-tag>
            <el-button
              size="small"
              :loading="aiLoadingKey === 'aging'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('aging')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-aging`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="agingRows" border size="small" class="d2-disc__table">
        <el-table-column label="账龄" min-width="160">
          <template #default="{ row }">
            <span :class="{ 'row-strong': row.kind !== 'segment' }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="endLabel" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.endAuto }"
              @change="(v: number | undefined) => setOverride(`aging:end:${row.key}`, v ?? 0)"
            />
            <el-tooltip v-else-if="row.autoSource" :content="row.autoSource" placement="top">
              <span class="amt-cell auto-cell">{{ fmt(row.endAmount) }}</span>
            </el-tooltip>
            <span v-else class="amt-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="priorLabel" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.priorAuto }"
              @change="(v: number | undefined) => setOverride(`aging:prior:${row.key}`, v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数" width="130" align="center">
          <template #default="{ row }">
            <el-tooltip v-if="row.autoSource" :content="row.autoSource" placement="top">
              <el-tag v-if="row.endAuto" size="small" type="info" effect="plain">自动</el-tag>
              <el-tag v-else size="small" type="warning" effect="plain">手工覆盖</el-tag>
            </el-tooltip>
            <el-button
              v-if="row.editable && !row.endAuto && !isReadonly"
              :icon="RefreshLeft"
              text
              size="small"
              title="恢复自动取数"
              @click="resetOverride(`aging:end:${row.key}`)"
            />
          </template>
        </el-table-column>
      </el-table>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['aging'] || ''"
          :disabled="isReadonly"
          placeholder="请说明账龄划分口径、长账龄款项回收情况等..."
          @input="(v: string) => setNote('aging', v)"
        />
      </div>
    </el-card>

    <!-- ② 按坏账准备计提方法分类披露 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ isSoeVariant ? T.classEnd : D2_TABLE_NAMES.listed.classEnd }}</span>
          <div class="card-head-right">
            <el-button
              size="small"
              :loading="aiLoadingKey === 'badDebtClass'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('badDebtClass')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-badDebtClass`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="classRows" border size="small" class="d2-disc__table">
        <el-table-column label="类别" min-width="220">
          <template #default="{ row }">
            <span
              :class="{ 'row-strong': row.kind === 'method' || row.kind === 'total', 'row-hint': row.kind === 'hint', 'row-detail': row.kind === 'detail' }"
            >{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="endLabel" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.auto }"
              @change="(v: number | undefined) => setOverride(`class:end:${row.key}`, v ?? 0)"
            />
            <el-tooltip v-else-if="row.autoSource" :content="row.autoSource" placement="top">
              <span class="amt-cell" :class="{ 'auto-cell': row.kind !== 'hint' }">{{ row.kind === 'hint' ? '' : fmt(row.endAmount) }}</span>
            </el-tooltip>
            <span v-else class="amt-cell">{{ row.kind === 'hint' ? '' : fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="priorLabel" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.auto }"
              @change="(v: number | undefined) => setOverride(`class:prior:${row.key}`, v ?? 0)"
            />
            <span v-else class="amt-cell">{{ row.kind === 'hint' ? '' : fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数说明" min-width="220">
          <template #default="{ row }">
            <span class="src-hint">{{ row.autoSource }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['badDebtClass'] || ''"
          :disabled="isReadonly"
          placeholder="请说明按单项/按组合计提坏账准备的划分依据（CAS22 预期信用损失）..."
          @input="(v: string) => setNote('badDebtClass', v)"
        />
      </div>
    </el-card>

    <!-- ③ 按单项计提坏账准备的应收账款 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ isSoeVariant ? T.individualEnd : D2_TABLE_NAMES.listed.individualEnd }}</span>
          <div class="card-head-right">
            <el-button size="small" :disabled="isReadonly" @click="reportImport(importIndividualFromBadDebt(), 'D2-3 单项计提子行')">从 D2-3 带入</el-button>
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="promptAddIndividual">新增行</el-button>
            <el-button
              size="small"
              :loading="aiLoadingKey === 'individual'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('individual')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-individual`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="individualRows" border size="small" class="d2-disc__table">
        <el-table-column :label="isSoeVariant ? '债务人名称' : '名称'" min-width="180">
          <template #default="{ row }">
            <el-input
              :model-value="row.name"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateIndividualRow(row.rowId, 'name', v)"
            />
          </template>
        </el-table-column>
        <el-table-column :label="isSoeVariant ? '账面余额' : endLabel" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.endAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateIndividualRow(row.rowId, 'endAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isSoeVariant" :label="priorLabel" min-width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.priorAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateIndividualRow(row.rowId, 'priorAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <template v-if="isSoeVariant">
          <el-table-column label="坏账准备" min-width="140" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.provision"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateIndividualRow(row.rowId, 'provision', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账龄" min-width="120">
            <template #default="{ row }">
              <el-select
                :model-value="row.aging"
                size="small"
                filterable
                allow-create
                clearable
                :disabled="isReadonly"
                @change="(v: string) => updateIndividualRow(row.rowId, 'aging', v || '')"
              >
                <el-option v-for="seg in agingSegments" :key="seg.key" :label="seg.label" :value="seg.label" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率（%）" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.lossRate"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateIndividualRow(row.rowId, 'lossRate', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="计提理由" min-width="200">
            <template #default="{ row }">
              <el-input
                :model-value="row.basis"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateIndividualRow(row.rowId, 'basis', v)"
              />
            </template>
          </el-table-column>
        </template>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId)" />
          </template>
        </el-table-column>
        <template #empty>暂无单项计提明细，请「新增行」或从 D2-3 带入</template>
      </el-table>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['individual'] || ''"
          :disabled="isReadonly"
          placeholder="请说明单项计提坏账准备的判断依据、预期信用损失率确定过程..."
          @input="(v: string) => setNote('individual', v)"
        />
      </div>
    </el-card>

    <!-- ④ 组合计提项目（每个组合一张分表）-->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">组合计提项目（每个组合一张分表）</span>
          <div class="card-head-right">
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="promptAddPortfolio">新增组合</el-button>
            <el-button
              size="small"
              :loading="aiLoadingKey === 'portfolio'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('portfolio')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-portfolio`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-empty v-if="portfolios.length === 0" description="暂无组合计提项目，请「新增组合」（组合名称将作为附注分表名）" :image-size="60" />

      <div v-for="group in portfolios" :key="group.groupId" class="portfolio-group">
        <div class="portfolio-group__head">
          <span class="portfolio-group__name">组合计提项目：{{ group.name || '（未命名组合）' }}</span>
          <div>
            <el-button size="small" text :disabled="isReadonly" @click="promptRenamePortfolio(group.groupId, group.name)">重命名</el-button>
            <el-button size="small" text type="danger" :icon="Delete" :disabled="isReadonly" @click="removePortfolio(group.groupId)">删除组合</el-button>
          </div>
        </div>
        <el-table :data="group.rows" border size="small" class="d2-disc__table">
          <el-table-column label="账龄" min-width="160">
            <template #default="{ row }">{{ row.label }}</template>
          </el-table-column>
          <el-table-column :label="endLabel" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.endAmount"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updatePortfolioCell(group.groupId, row.key, 'endAmount', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column :label="priorLabel" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.priorAmount"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updatePortfolioCell(group.groupId, row.key, 'priorAmount', v ?? 0)"
              />
            </template>
          </el-table-column>
        </el-table>
      </div>

      <!-- 国企：采用余额百分比或其他组合方法计提 -->
      <template v-if="isSoeVariant">
        <div class="portfolio-group__head" style="margin-top:14px">
          <span class="portfolio-group__name">{{ D2_TABLE_NAMES.soe.otherPortfolio }}</span>
          <el-button size="small" text :icon="Plus" :disabled="isReadonly" @click="promptAddOtherPortfolio">新增行</el-button>
        </div>
        <el-table :data="otherPortfolioRows" border size="small" class="d2-disc__table">
          <el-table-column label="组合名称" min-width="200">
            <template #default="{ row }">
              <el-input
                :model-value="row.name"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateOtherPortfolioRow(row.rowId, 'name', v)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末数" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.endAmount"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateOtherPortfolioRow(row.rowId, 'endAmount', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="期初数" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.priorAmount"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateOtherPortfolioRow(row.rowId, 'priorAmount', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="60" align="center">
            <template #default="{ row }">
              <el-button :icon="Delete" text type="danger" size="small" @click="removeOtherPortfolioRow(row.rowId)" />
            </template>
          </el-table-column>
          <template #empty>暂无其他组合方法计提的应收账款</template>
        </el-table>
      </template>
    </el-card>

    <!-- ⑤ 坏账准备变动 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ T.movement }}</span>
          <div class="card-head-right">
            <el-button
              size="small"
              :loading="aiLoadingKey === 'movement'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('movement')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-movement`" label="💬 复核" />
          </div>
        </div>
      </template>

      <!-- 上市：纵向 7 行 -->
      <el-table v-if="!isSoeVariant" :data="movementFields" border size="small" class="d2-disc__table amount-table">
        <el-table-column label="项目" min-width="180">
          <template #default="{ row }">{{ row.label }}</template>
        </el-table-column>
        <el-table-column label="坏账准备金额" min-width="170" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.amount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.auto }"
              @change="(v: number | undefined) => setOverride(`movement:${row.key}`, v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数说明" min-width="240">
          <template #default="{ row }">
            <span class="src-hint">{{ row.autoSource || '无数据源，手工录入' }}</span>
            <el-button
              v-if="!row.auto && row.autoSource && !isReadonly"
              :icon="RefreshLeft"
              text
              size="small"
              title="恢复自动取数"
              @click="resetOverride(`movement:${row.key}`)"
            />
          </template>
        </el-table-column>
      </el-table>
      <div v-if="!isSoeVariant" class="movement-end">
        <span class="movement-end__label">期末余额（= 期初 + 计提 − 转回 − 核销 − 转销 + 其他）：</span>
        <span class="amt-cell row-strong">{{ fmt(movementEndBalance) }}</span>
      </div>

      <!-- 国企：按类别 -->
      <el-table v-else :data="movementByCategory" border size="small" class="d2-disc__table">
        <el-table-column label="类别" min-width="220">
          <template #default="{ row }">
            <span :class="{ 'row-strong': row.isTotal }">{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初数" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.auto }"
              @change="(v: number | undefined) => setOverride(`movementCat:prior:${row.key}`, v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期变动金额" min-width="150" align="right">
          <template #default="{ row }">
            <el-tooltip content="= 期末数 − 期初数（自动计算）" placement="top">
              <span class="amt-cell calc-cell">{{ fmt(row.changeAmount) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="期末数" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.endAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :class="{ 'auto-cell': row.auto }"
              @change="(v: number | undefined) => setOverride(`movementCat:end:${row.key}`, v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="取数说明" min-width="220">
          <template #default="{ row }">
            <span class="src-hint">{{ row.autoSource }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['movement'] || ''"
          :disabled="isReadonly"
          placeholder="请说明本期坏账准备计提、收回或转回的原因与合理性..."
          @input="(v: string) => setNote('movement', v)"
        />
      </div>
    </el-card>

    <!-- ⑥ 转回或收回金额重要的坏账准备 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ T.reversal }}</span>
          <div class="card-head-right">
            <el-button size="small" :disabled="isReadonly" @click="reportImport(importReversalFromWriteoffCheck(), 'D2-11 转回明细')">从 D2-11 带入</el-button>
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="addReversalRow">新增行</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-reversal`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="reversalRows" border size="small" class="d2-disc__table">
        <el-table-column :label="isSoeVariant ? '债务人名称' : '单位名称'" min-width="170">
          <template #default="{ row }">
            <el-input :model-value="row.companyName" size="small" :disabled="isReadonly" @change="(v: string) => updateReversalRow(row.rowId, 'companyName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="170">
          <template #default="{ row }">
            <el-input :model-value="row.reversalReason" size="small" :disabled="isReadonly" @change="(v: string) => updateReversalRow(row.rowId, 'reversalReason', v)" />
          </template>
        </el-table-column>
        <el-table-column label="收回方式" min-width="150">
          <template #default="{ row }">
            <el-input :model-value="row.recoveryMethod" size="small" :disabled="isReadonly" @change="(v: string) => updateReversalRow(row.rowId, 'recoveryMethod', v)" />
          </template>
        </el-table-column>
        <el-table-column label="原确定坏账准备的依据" min-width="190">
          <template #default="{ row }">
            <el-input :model-value="row.originalBasis" size="small" :disabled="isReadonly" @change="(v: string) => updateReversalRow(row.rowId, 'originalBasis', v)" />
          </template>
        </el-table-column>
        <el-table-column v-if="isSoeVariant" label="转回或收回前累计已计提坏账准备金额" min-width="180" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.cumulativeProvision"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateReversalRow(row.rowId, 'cumulativeProvision', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="转回或收回金额" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.amount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateReversalRow(row.rowId, 'amount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button :icon="Delete" text type="danger" size="small" @click="removeReversalRow(row.rowId)" />
          </template>
        </el-table-column>
        <template #empty>暂无重要转回或收回，可从 D2-11 带入或手工新增</template>
      </el-table>
    </el-card>

    <!-- ⑦ 核销 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">
            {{ isSoeVariant ? T.writeOffDetail : `${D2_TABLE_NAMES.listed.writeOffAmount} / ${D2_TABLE_NAMES.listed.writeOffDetail}` }}
          </span>
          <div class="card-head-right">
            <el-button size="small" :disabled="isReadonly" @click="reportImport(importWriteOffFromWriteoffCheck(), 'D2-11 核销明细')">从 D2-11 带入</el-button>
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="addWriteOffRow">新增行</el-button>
            <el-button
              size="small"
              :loading="aiLoadingKey === 'writeOff'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('writeOff')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-writeOff`" label="💬 复核" />
          </div>
        </div>
      </template>

      <div class="writeoff-amount">
        <span class="writeoff-amount__label">本期实际核销的应收账款金额：</span>
        <el-input-number
          v-if="!isReadonly"
          :model-value="writeOffAmountCell.amount"
          :controls="false"
          :precision="2"
          size="small"
          class="amt-input"
          :class="{ 'auto-cell': writeOffAmountCell.auto }"
          @change="(v: number | undefined) => setWriteOffAmount(v ?? 0)"
        />
        <span v-else class="amt-cell">{{ fmt(writeOffAmountCell.amount) }}</span>
        <el-tooltip content="默认取自 D2-3 坏账准备表本期核销合计，可手工覆盖" placement="top">
          <el-tag size="small" :type="writeOffAmountCell.auto ? 'info' : 'warning'" effect="plain">
            {{ writeOffAmountCell.auto ? '取自 D2-3' : '手工覆盖' }}
          </el-tag>
        </el-tooltip>
        <el-button
          v-if="!writeOffAmountCell.auto && !isReadonly"
          :icon="RefreshLeft"
          text
          size="small"
          title="恢复自动取数"
          @click="resetOverride('writeoff:amount')"
        />
      </div>

      <el-table :data="writeOffRows" border size="small" class="d2-disc__table">
        <el-table-column :label="isSoeVariant ? '债务人名称' : '单位名称'" min-width="170">
          <template #default="{ row }">
            <el-input :model-value="row.companyName" size="small" :disabled="isReadonly" @change="(v: string) => updateWriteOffRow(row.rowId, 'companyName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="应收账款性质" min-width="150">
          <template #default="{ row }">
            <el-input :model-value="row.nature" size="small" :disabled="isReadonly" @change="(v: string) => updateWriteOffRow(row.rowId, 'nature', v)" />
          </template>
        </el-table-column>
        <el-table-column label="核销金额" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.amount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateWriteOffRow(row.rowId, 'amount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="170">
          <template #default="{ row }">
            <el-input :model-value="row.reason" size="small" :disabled="isReadonly" @change="(v: string) => updateWriteOffRow(row.rowId, 'reason', v)" />
          </template>
        </el-table-column>
        <el-table-column label="履行的核销程序" min-width="170">
          <template #default="{ row }">
            <el-input :model-value="row.procedure" size="small" :disabled="isReadonly" @change="(v: string) => updateWriteOffRow(row.rowId, 'procedure', v)" />
          </template>
        </el-table-column>
        <el-table-column :label="isSoeVariant ? '是否因关联交易产生' : '款项是否由关联交易产生'" min-width="160">
          <template #default="{ row }">
            <el-select
              :model-value="row.relatedParty"
              size="small"
              clearable
              :disabled="isReadonly"
              @change="(v: string) => updateWriteOffRow(row.rowId, 'relatedParty', v || '')"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button :icon="Delete" text type="danger" size="small" @click="removeWriteOffRow(row.rowId)" />
          </template>
        </el-table-column>
        <template #empty>暂无重要核销明细，可从 D2-11 带入或手工新增</template>
      </el-table>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['writeOff'] || ''"
          :disabled="isReadonly"
          placeholder="请说明核销依据、审批程序，关联交易产生的款项应单独披露..."
          @input="(v: string) => setNote('writeOff', v)"
        />
      </div>
    </el-card>

    <!-- ⑧ 前五名 -->
    <el-card shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ T.top5 }}</span>
          <div class="card-head-right">
            <el-button size="small" :disabled="isReadonly" @click="reportImport(importTop5FromAnalysis(), 'D2-5 期末前十名')">从 D2-5 带入</el-button>
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="addTop5Row">新增行</el-button>
            <el-button
              size="small"
              :loading="aiLoadingKey === 'top5'"
              :disabled="isReadonly || !ai.aiAvailable.value"
              @click="handleAiGenerate('top5')"
            >🤖 AI</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-note-top5`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="top5Rows" border size="small" class="d2-disc__table">
        <el-table-column :label="isSoeVariant ? '债务人名称' : '单位名称'" min-width="180">
          <template #default="{ row }">
            <el-input :model-value="row.companyName" size="small" :disabled="isReadonly" @change="(v: string) => updateTop5Row(row.rowId, 'companyName', v)" />
          </template>
        </el-table-column>
        <el-table-column :label="isSoeVariant ? '账面余额' : '应收账款期末余额'" min-width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.arAmount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateTop5Row(row.rowId, 'arAmount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <template v-if="!isSoeVariant">
          <el-table-column label="合同资产期末余额" min-width="150" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.contractAssetAmount"
                :controls="false"
                :precision="2"
                size="small"
                class="amt-input"
                :disabled="isReadonly"
                @change="(v: number | undefined) => updateTop5Row(row.rowId, 'contractAssetAmount', v ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="合计" min-width="150" align="right">
            <template #default="{ row }">
              <el-tooltip content="= 应收账款期末余额 + 合同资产期末余额（自动计算）" placement="top">
                <span class="amt-cell calc-cell">{{ fmt(row.arAmount + row.contractAssetAmount) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </template>
        <el-table-column :label="isSoeVariant ? '占应收账款合计的比例（%）' : '占期末余额合计数的比例%'" min-width="160" align="right">
          <template #default="{ row }">
            <el-tooltip content="= 本行余额 ÷ D2-1 审定表期末审定合计（自动计算）" placement="top">
              <span class="amt-cell calc-cell">{{ fmtPct(top5Ratio(row)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column :label="isSoeVariant ? '坏账准备' : '坏账准备和合同资产减值准备期末余额'" min-width="170" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.provision"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateTop5Row(row.rowId, 'provision', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button :icon="Delete" text type="danger" size="small" @click="removeTop5Row(row.rowId)" />
          </template>
        </el-table-column>
        <template #empty>暂无前五名，可从 D2-5 带入或手工新增</template>
      </el-table>
      <div class="top5-base">
        占比分母（D2-1 审定表期末审定合计）：<span class="amt-cell">{{ fmt(top5Total) }}</span>
      </div>

      <div class="section-note">
        <label>说明：</label>
        <el-input
          type="textarea"
          :autosize="{ minRows: 3 }"
          :model-value="sectionNotes['top5'] || ''"
          :disabled="isReadonly"
          placeholder="请说明客户集中度、关联方情况及信用风险..."
          @input="(v: string) => setNote('top5', v)"
        />
      </div>
    </el-card>

    <!-- ⑨ 国企：由金融资产转移而终止确认的应收账款 -->
    <el-card v-if="isSoeVariant" shadow="never" class="d2-disc__card">
      <template #header>
        <div class="card-head">
          <span class="card-title">{{ D2_TABLE_NAMES.soe.derecognized }}</span>
          <div class="card-head-right">
            <el-button size="small" type="primary" plain :icon="Plus" :disabled="isReadonly" @click="addDerecognizedRow">新增行</el-button>
            <GtReviewTrigger :section-id="`D2-disc-${variant}-derecognized`" label="💬 复核" />
          </div>
        </div>
      </template>

      <el-table :data="derecognizedRows" border size="small" class="d2-disc__table">
        <el-table-column label="债务人名称" min-width="200">
          <template #default="{ row }">
            <el-input :model-value="row.companyName" size="small" :disabled="isReadonly" @change="(v: string) => updateDerecognizedRow(row.rowId, 'companyName', v)" />
          </template>
        </el-table-column>
        <el-table-column label="终止确认金额" min-width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.amount"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateDerecognizedRow(row.rowId, 'amount', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="与终止确认相关的利得或损失" min-width="200" align="right">
          <template #default="{ row }">
            <el-input-number
              :model-value="row.gainLoss"
              :controls="false"
              :precision="2"
              size="small"
              class="amt-input"
              :disabled="isReadonly"
              @change="(v: number | undefined) => updateDerecognizedRow(row.rowId, 'gainLoss', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="60" align="center">
          <template #default="{ row }">
            <el-button :icon="Delete" text type="danger" size="small" @click="removeDerecognizedRow(row.rowId)" />
          </template>
        </el-table-column>
        <template #empty>暂无因金融资产转移而终止确认的应收账款（损失以负数填列）</template>
      </el-table>
    </el-card>

    <!-- 编制提示 -->
    <details class="d2-disc__guidance">
      <summary>📋 编制提示</summary>
      <p>1. 本页结构对齐附注 {{ D2_NOTE_SECTION[variant] }}「应收账款」，表名与列头与附注模板一致；编制完成后点「同步到附注」把表格与说明一并推送到附注模块。</p>
      <p>2. 浅蓝底单元格为跨底稿自动取数（账龄取 D2-2 明细、分类取 D2-1 审定表、坏账变动取 D2-3），可手工覆盖；覆盖后可点↩恢复自动取数。</p>
      <p>3. 组合名称将作为附注分表名（组合计提项目：XXX），请与被审计单位实际信用风险组合口径一致。</p>
      <p>4. CAS22：单项计提需说明判断依据与预期信用损失率；CAS30：核销由关联交易产生的款项应单独披露。</p>
      <p>5. 顶部黄色告警表示披露合计与 D2-1 审定表 / D2-3 坏账准备表不一致，须查明差异后再同步附注。</p>
    </details>
  </div>
</template>

<style scoped>
.d2-disc { padding: 12px; font-size: 13px; }
.d2-disc__toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; }
.d2-disc__toolbar-right { margin-left: auto; display: flex; align-items: center; gap: 8px; }
.d2-disc__objective { margin-bottom: 10px; }
.d2-disc__objective p { margin: 0; font-size: 13px; line-height: 1.6; }
.d2-disc__warn { margin-bottom: 8px; }
.d2-disc__card { margin-bottom: 14px; }
.d2-disc__card :deep(.el-card__header) { padding: 8px 12px; background: #fafafa; }
.d2-disc__card :deep(.el-card__body) { padding: 12px; }
.card-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; font-size: 13px; border-left: 3px solid var(--el-color-primary); padding-left: 8px; }
.card-head-right { display: flex; align-items: center; gap: 6px; }
.d2-disc__table { width: 100%; font-size: 13px; }
.d2-disc__table :deep(.el-table__cell) { padding: 3px 6px; }
.d2-disc__table :deep(th.el-table__cell) { padding: 4px 6px; }
.d2-disc__table :deep(td.is-right .cell) { white-space: nowrap; font-variant-numeric: tabular-nums; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.amt-input :deep(.el-input__inner) { text-align: right; font-variant-numeric: tabular-nums; }
.auto-cell :deep(.el-input__wrapper) { background-color: #ecf5ff; }
span.auto-cell { background-color: #ecf5ff; padding: 1px 4px; border-radius: 2px; }
.calc-cell { color: #606266; }
.row-strong { font-weight: 600; }
.row-hint { color: #909399; }
.row-detail { padding-left: 16px; color: #606266; }
.src-hint { color: #909399; font-size: 12px; }
.portfolio-group { margin-bottom: 14px; }
.portfolio-group__head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.portfolio-group__name { font-weight: 600; }
.movement-end { margin-top: 8px; display: flex; align-items: center; gap: 6px; }
.movement-end__label { color: #606266; }
.writeoff-amount { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; max-width: 640px; }
.writeoff-amount__label { color: #606266; white-space: nowrap; }
.top5-base { margin-top: 6px; color: #909399; font-size: 12px; }
.section-note { margin-top: 10px; }
.section-note label { display: block; margin-bottom: 4px; color: #606266; }
.amount-table { max-width: 760px; }
.d2-disc__guidance { margin-top: 10px; background: #fffbeb; border-left: 4px solid #f59e0b; padding: 8px 12px; border-radius: 4px; }
.d2-disc__guidance summary { cursor: pointer; font-weight: 600; color: #78350f; }
.d2-disc__guidance p { margin: 6px 0 0; color: #78350f; font-size: 13px; line-height: 1.6; }
</style>
