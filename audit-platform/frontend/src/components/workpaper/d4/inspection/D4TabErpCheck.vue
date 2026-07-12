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
import { ref, computed, watch, inject, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtOnlyOfficeSheet from '../../GtOnlyOfficeSheet.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 双模式 ──────────────────────────────────────────────────────────
const editorMode = ref<'structured' | 'onlyoffice'>('structured')
const ooHealthy = ref(false)
const modeOptions = computed(() => [
  { label: '结构化视图', value: 'structured' },
  { label: '在线编辑', value: 'onlyoffice', disabled: !ooHealthy.value },
])
async function checkOoHealth() {
  try {
    const res = await http.get('/api/workpapers/onlyoffice/health', { _silent: true } as any)
    ooHealthy.value = res.data?.data?.healthy ?? res.data?.healthy ?? false
  } catch { ooHealthy.value = false }
}
checkOoHealth()

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
</script>

<template>
  <div class="d4-erp">
    <!-- 工具条 -->
    <div class="toolbar">
      <el-segmented v-model="editorMode" :options="modeOptions" size="small" />
      <div class="toolbar-right">
        <span class="chip-label">关联</span>
        <GtIndexChip value="wp:D4-1" :context-project-id="projectId" />
        <GtIndexChip value="wp:D4-5" :context-project-id="projectId" />
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('D4-13')">💬 复核</el-button>
      </div>
    </div>

    <!-- 结构化视图 -->
    <template v-if="editorMode === 'structured'">
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

    <!-- 在线编辑 -->
    <template v-else>
      <div class="oo-container">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          sheet-name="营业收入账面金额与ERP系统核对记录D4-13"
          :readonly="isReadonly"
        />
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

.oo-container { min-height: 600px; height: calc(100vh - 280px); }
</style>
