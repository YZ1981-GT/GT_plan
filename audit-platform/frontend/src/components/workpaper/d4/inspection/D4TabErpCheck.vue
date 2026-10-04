<script setup lang="ts">
/**
 * D4TabErpCheck — D4-13 营业收入账面金额与ERP系统核对记录
 *
 * 对齐源模板：叙述性文档
 *   一、核对过程（大文本，AI可辅助生成）
 *   二、核对结论（大文本，AI可辅助生成）
 *   底部提示（红）
 *
 * 无独立"审计意见区"（源模板中不存在）
 */
import { ref, computed, watch, inject, onBeforeUnmount, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useD4ImportExport } from '../../composables/useD4ImportExport'
import { useD4InspectionWriteback } from '../../composables/useD4InspectionWriteback'
import { readStoreProjection } from '../../sync/workpaperSyncApi'
import WorkpaperSyncEditorHost from '../../sync/WorkpaperSyncEditorHost.vue'
import { useD4SyncMode, D4_SYNC_ENTRY_ID } from '../composables/useD4SyncMode'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── AI 健康 ─────────────────────────────────────────────────────────
const aiAvailable = ref(false)
async function checkAiHealth() {
  try {
    const res = await http.get('/api/ai/health', { _silent: true } as any)
    const s = res.data?.data?.status ?? res.data?.status
    aiAvailable.value = s === 'healthy' || s === 'degraded'
  } catch { aiAvailable.value = false }
}
checkAiHealth()

// ─── 数据 ────────────────────────────────────────────────────────────
const ITEM_PROCESS = 'D4-13-process'
const ITEM_CONCLUSION = 'D4-13-conclusion'

function getResp(id: string): string { return props.allResponses.get(id)?.remark ?? '' }

const processText = ref(getResp(ITEM_PROCESS))
const conclusionText = ref(getResp(ITEM_CONCLUSION))

watch(() => props.allResponses, () => {
  processText.value = getResp(ITEM_PROCESS)
  conclusionText.value = getResp(ITEM_CONCLUSION)
}, { deep: true })

// ─── 持久化 debounce 2s ──────────────────────────────────────────────
let timer: ReturnType<typeof setTimeout> | null = null
function save() {
  if (timer) clearTimeout(timer)
  timer = setTimeout(flush, 2000)
}
function flush() {
  if (props.isReadonly) return
  const items = [
    { item_id: ITEM_PROCESS, conclusion: null, remark: processText.value },
    { item_id: ITEM_CONCLUSION, conclusion: null, remark: conclusionText.value },
  ]
  for (const it of items) props.allResponses.set(it.item_id, { ...it })
  window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
}
function onProcess(v: string) { processText.value = v; save() }
function onConclusion(v: string) { conclusionText.value = v; save() }
onBeforeUnmount(() => { if (timer) { clearTimeout(timer); flush() } })

// ─── 双模式 sync bridge（治本改造：D4-13 全篇无插删动态行表，两段文本走 useD4SyncMode
//     静态受管区，同 D4-33/D4-8。sheet_key=d413-managed，同 entry gt-d4-operating-revenue，
//     provider=phase5_d4_erp_check_sheet） ─────────────────────────────────
const D4_13_SHEET_KEY = 'd413-managed'
const {
  syncBridge, descriptor: syncOoDescriptor, editorMode, modeOptions,
  busy: syncBusy, syncStateTag, syncHostRef,
} = useD4SyncMode({
  sheetKey: D4_13_SHEET_KEY,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  isReadonly: toRef(props, 'isReadonly'),
  views: ['结构化视图'],
  flushHtml: async () => {
    if (timer) { clearTimeout(timer); timer = null }
    flush()
    const snap = await readStoreProjection({ projectId: props.projectId, wpId: props.wpId, entryId: D4_SYNC_ENTRY_ID })
    return { expectedRevision: snap.expectedRevision, projection: snap.projection, sheetKey: D4_13_SHEET_KEY }
  },
  reloadHtml: async () => { window.dispatchEvent(new CustomEvent('d4:reload-responses')) },
})

// ─── AI 核对过程 ─────────────────────────────────────────────────────
const aiProcessLoading = ref(false)
async function genProcess() {
  if (props.isReadonly || !aiAvailable.value) return
  aiProcessLoading.value = true
  try {
    const revenueTotal = props.allResponses.get('D4-adj-revenue-total')?.remark ?? ''
    const entityName = props.allResponses.get('D4-entity-name')?.remark ?? ''
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      {
        section: 'adj-note',
        existingContent: processText.value || '',
        relatedContext: {
          task: '请为D4-13底稿生成"一、核对过程"部分的审计文本',
          entityName: entityName || '被审计单位',
          revenueTotal: revenueTotal || '（请补充审定收入金额）',
          guidance: [
            '需要包含以下要素：',
            '1. 获取被审计单位ERP系统名称及版本',
            '2. 核对的数据范围（XX年1-12月，主营业务收入科目6001）',
            '3. 核对方式（按月汇总核对/逐笔核对/导出后交叉比对）',
            '4. 数据获取方式（由XX导出ERP明细数据/审计人员直接查询）',
            '5. 比对结果概述（一致/存在差异及原因简述）',
            '6. 若存在差异，分析差异性质并评估影响',
          ].join('\n'),
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 核对过程', {
      confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
      customStyle: { maxWidth: '600px' },
    })
    processText.value = text; save()
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败')
  } finally { aiProcessLoading.value = false }
}

// ─── AI 核对结论 ─────────────────────────────────────────────────────
const aiConclusionLoading = ref(false)
async function genConclusion() {
  if (props.isReadonly || !aiAvailable.value) return
  aiConclusionLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/ai-generate`,
      {
        section: 'adj-conclusion',
        existingContent: conclusionText.value || '',
        relatedContext: {
          task: '请为D4-13底稿生成"二、核对结论"部分',
          process: processText.value || '（核对过程未填写）',
          guidance: [
            '核对结论应包含：',
            '1. 核对结果陈述（一致/不一致）',
            '2. 如一致：明确表述"账面记录金额与ERP系统记录金额核对一致"',
            '3. 如存在差异：差异金额、原因、是否已调整、对审计结论的影响',
            '4. 最终判断：核对结果是否可接受/是否需要进一步追查',
          ].join('\n'),
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.data?.content ?? res.data?.content ?? ''
    if (!text) { ElMessage.warning('AI 未生成内容'); return }
    await ElMessageBox.confirm(text, 'AI 生成 · 核对结论', {
      confirmButtonText: '填入', cancelButtonText: '取消', type: 'info',
      customStyle: { maxWidth: '600px' },
    })
    conclusionText.value = text; save()
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('AI 生成失败')
  } finally { aiConclusionLoading.value = false }
}

const aiTip = computed(() => aiAvailable.value ? 'AI 辅助生成' : 'AI 服务暂不可用')

// ─── 导入导出（叙述式：导出核对过程/结论，导入按区块回写）────────────────
const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)
const { exportTemplate, exportData, importData, importing } = useD4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
function handleExportTemplate() { exportTemplate('D4-13') }
function handleExportData() { exportData('D4-13') }
async function handleImportFile(uploadFile: any) {
  const file = uploadFile.raw || uploadFile
  const res = await importData('D4-13', file)
  if (res) await reloadWorkpaperData?.()
}
async function handleImportClick() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async () => { const f = input.files?.[0]; if (f) await handleImportFile(f) }
  input.click()
}

// ─── 双向回写：ERP 核对差异 → A13 错报 + D4-1 审计说明 ─────────────────
// 叙述式底稿无结构化差异数据，由审计师填差异金额后推送（结论文本作描述）。
const { pushToA13 } = useD4InspectionWriteback({
  wpCode: 'D4-13',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})
async function handlePushToA13() {
  if (props.isReadonly) return
  let amountStr: string
  try {
    const r = await ElMessageBox.prompt(
      '请输入 ERP 核对差异金额（账面 − ERP，元）。描述将取自「核对结论」文本。',
      '推送差异至 A13',
      { confirmButtonText: '推送', cancelButtonText: '取消', inputPattern: /^-?\d+(\.\d+)?$/, inputErrorMessage: '请输入有效金额' },
    )
    amountStr = (r as any).value
  } catch { return }
  const amount = Number(amountStr)
  if (!amount) { ElMessage.info('差异金额为 0，无需推送'); return }
  const desc = (conclusionText.value || '').trim() || 'ERP 系统核对存在差异'
  pushToA13([{ amount, description: `账面与ERP核对差异：${desc}`, indexRef: 'D4-13' }], '6001', '营业收入')
}

defineExpose({ handleExportTemplate, handleExportData, handleImportClick })
</script>

<template>
  <div class="d4-erp">
    <!-- 工具条 -->
    <div class="toolbar">
      <div class="toolbar-left">
        <el-segmented v-model="editorMode" :options="modeOptions" size="small" :disabled="syncBusy" />
        <el-tag :type="syncStateTag.type" size="small" effect="light" style="margin-left:8px">{{ syncStateTag.text }}</el-tag>
      </div>
      <div class="toolbar-right">
        
        <span class="chip-label">关联</span>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-5" :context-project-id="projectId" />
        <el-tooltip content="填写差异金额后推送至 A13 未更正错报汇总，并同步至 D4-1 审计说明" placement="top">
          <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handlePushToA13">推送差异至 A13</el-button>
        </el-tooltip>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-13')">💬 复核</el-button>
      </div>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode !== '在线编辑'">
      <!-- 一、核对过程 -->
      <section class="block">
        <div class="block-head">
          <h3>一、核对过程</h3>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiProcessLoading"
              :disabled="isReadonly || !aiAvailable" @click="genProcess">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input type="textarea" :autosize="{ minRows: 6, maxRows: 24 }"
          :model-value="processText" :disabled="isReadonly"
          placeholder="描述ERP系统核对过程：&#10;• ERP系统名称及版本&#10;• 核对数据范围（期间、科目）&#10;• 核对方式（逐笔/汇总/抽样）&#10;• 数据导出方式及导出人&#10;• 比对过程及差异分析"
          @input="onProcess" />
      </section>

      <!-- 二、核对结论 -->
      <section class="block">
        <div class="block-head">
          <h3>二、核对结论</h3>
          <el-tooltip :content="aiTip" placement="top">
            <el-button size="small" type="primary" plain :loading="aiConclusionLoading"
              :disabled="isReadonly || !aiAvailable" @click="genConclusion">🤖 AI辅助</el-button>
          </el-tooltip>
        </div>
        <el-input type="textarea" :autosize="{ minRows: 4, maxRows: 14 }"
          :model-value="conclusionText" :disabled="isReadonly"
          placeholder="核对结论，例如：&#10;经核对，被审计单位XX年度营业收入账面记录金额与ERP系统记录金额一致/存在差异XX元（原因：...），核对结果可接受。"
          @input="onConclusion" />
      </section>

      <!-- 编制提示 -->
      <details class="guidance">
        <summary>📋 编制提示</summary>
        <p>对于互联网等业务数据量大的被审计单位，应结合IT审计完成核对。</p>
      </details>
    </template>

    <!-- 在线编辑：平台 sync bridge（治本改造，非裸 GtOnlyOfficeSheet）-->
    <template v-if="editorMode === '在线编辑'">
      <div class="oo-container">
        <WorkpaperSyncEditorHost v-if="syncOoDescriptor" ref="syncHostRef" :descriptor="syncOoDescriptor" :bridge="syncBridge" />
        <div v-else class="oo-loading">正在打开 D4-13 同步编辑器…</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.d4-erp { padding: 12px 16px; font-size: var(--wp-font-size, 13px); }

.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 20px; flex-wrap: wrap; gap: 8px;
}
.toolbar-left { display: flex; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-label { font-size: 12px; color: #909399; margin-right: 2px; }

.block { margin-bottom: 28px; }
.block-head {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 10px;
}
.block-head h3 {
  margin: 0; font-size: 15px; font-weight: 600; color: #303133;
}

.guidance {
  margin-top: 8px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 10px 14px;
}
.guidance summary { cursor: pointer; font-weight: 500; color: #e6a23c; font-size: var(--wp-font-size, 13px); }
.guidance p { margin: 8px 0 0; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; }

.oo-container { min-height: 600px; height: calc(100vh - 280px); border-radius: 8px; overflow: hidden; }
.oo-loading { padding: 40px; text-align: center; color: #909399; }
</style>
