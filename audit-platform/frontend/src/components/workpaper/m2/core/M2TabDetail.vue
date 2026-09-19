<template>
  <div class="m2-tab-detail">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M2-2 实收资本（股本）明细表</h3>
        <el-tag type="warning" size="small">双版本·区段Tab·动态行</el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown :disabled="isReadonly" @command="handleImportExport" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 分支选择器（上市 / 非上市） ═══ -->
    <el-segmented
      v-model="activeBranch"
      :options="branchOptions"
      size="default"
      class="branch-switcher"
    />

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>权益类方向（贷方科目4001）：</strong>
        期末 = 期初 + 贷方（增资）− 借方（减资）。
        <template v-if="activeBranch === 'listed'">
          上市公司版按股份列示（38×36），36列拆3区段Tab管理：股东信息 / 股数增减变动 / 比例与金额。
        </template>
        <template v-else>
          非上市公司版按出资列示（37×24），24列拆3区段Tab管理：出资人信息 / 出资增减 / 比例。
        </template>
        明细合计应与M2-1审定表期末一致。
      </div>
    </div>

    <!-- ═══ 跨sheet交叉验证警告 ═══ -->
    <el-alert
      v-if="crossValidation && !crossValidation.isMatch"
      type="error"
      :closable="false"
      show-icon
      class="cross-sheet-alert"
    >
      <template #title>
        明细合计与审定表M2-1不一致（差额：{{ fmtAmount(crossValidation.diff) }}）
      </template>
    </el-alert>

    <!-- ═══ 上市公司版 / 非上市公司版 ═══ -->
    <M2TabDetailListed
      v-if="activeBranch === 'listed'"
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      :detail="detail"
    />
    <M2TabDetailUnlisted
      v-else
      :wp-id="wpId"
      :project-id="projectId"
      :is-readonly="isReadonly"
      :detail="detail"
    />

    <!-- ═══ 明细分析说明 ═══ -->
    <el-card shadow="never" class="detail-note-card">
      <template #header>
        <div class="card-header">
          <span class="card-title">明细分析说明</span>
          <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="handleAI('detail')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="detailNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="概述股本/出资结构及本期变动情况、明细与审定表勾稽结果等，或点击 AI 辅助生成..."
        @change="saveDetailNote"
      />
    </el-card>

    <!-- ═══ 跨底稿联动（cross_wp_ref GtIndexChip） ═══ -->
    <div class="cross-wp-links">
      <span class="cross-wp-label">cross_wp_ref 关联底稿：</span>
      <GtIndexChip value="M2-1" :context-project-id="projectId" />
      <span class="cross-wp-desc">审定表（合计验证）</span>
      <GtIndexChip value="M2-4" :context-project-id="projectId" />
      <span class="cross-wp-desc">外币投资汇率</span>
      <GtIndexChip value="M4" :context-project-id="projectId" />
      <span class="cross-wp-desc">资本公积（外币折算差异）</span>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m2-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>上市公司按股份（股数×比例）列示；非上市公司按出资（金额×比例）列示</li>
        <li><strong>权益类公式</strong>：期末 = 期初 + 本期增加（贷方增资）− 本期减少（借方减资）</li>
        <li>持股/出资比例 = 个体期末 / 合计期末（自动计算）</li>
        <li>新增行需先输入股东/出资人名称（弹窗确认）</li>
        <li>明细合计应与M2-1审定表实收资本期末余额一致</li>
        <li>外币出资请同步填写M2-4外币投资汇率测算表</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M2TabDetail — M2-2 明细表分支选择器容器
 *
 * Requirements: 3.1-3.7
 * - el-segmented 分支选择器：上市公司版 / 非上市公司版
 * - v-if 切换 M2TabDetailListed / M2TabDetailUnlisted
 * - 使用 useM2Detail composable 管理双版本状态
 * - 导入导出 useM2ImportExport
 * - DualMode el-segmented (HTML/OO)
 * - Section header with 复核 + AI buttons
 *
 * 科目：4001 实收资本/股本（贷方/权益类！期末=期初+贷方-借方）
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '@/components/workpaper/GtIndexChip.vue'
import M2TabDetailListed from './M2TabDetailListed.vue'
import M2TabDetailUnlisted from './M2TabDetailUnlisted.vue'
import { useM2FormData } from '../../composables/useM2FormData'
import {
  useM2Detail,
  type M2DetailBranch,
  type M2DetailListedRow,
  type M2DetailUnlistedRow,
} from '../../composables/useM2Detail'
import { useM2ImportExport, type M2ImportableSheet } from '../../composables/useM2ImportExport'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate', sheetName: string): void
}>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref(false)
const detailNote = ref('')

// ─── FormData + Composables ──────────────────────────────────────────────────

const formData = useM2FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const listedRows = ref<M2DetailListedRow[]>([])
const unlistedRows = ref<M2DetailUnlistedRow[]>([])

const detail = useM2Detail(formData, listedRows, unlistedRows)

const { exportTemplate, exportData, importData } = useM2ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

// ─── Branch (wrapper around detail.activeBranch) ─────────────────────────────

const activeBranch = computed({
  get: () => detail.activeBranch.value,
  set: (val: M2DetailBranch) => detail.switchBranch(val),
})

const branchOptions = [
  { label: '上市公司版', value: 'listed' as const },
  { label: '非上市公司版', value: 'unlisted' as const },
]

// ─── Cross-sheet validation ──────────────────────────────────────────────────

const adjudicationEndAudited = ref(0)

const crossValidation = computed(() => {
  return detail.crossValidate(adjudicationEndAudited.value)
})

// Load adjudication total from checklist_responses
watch(() => formData.allResponses.value, (responses) => {
  const auditedResp = responses.get('M2-M2-1-total-audited')
  if (auditedResp?.remark) {
    const val = parseFloat(auditedResp.remark)
    if (!isNaN(val)) adjudicationEndAudited.value = val
  }
}, { immediate: true })

// ─── Import/Export Handler ────────────────────────────────────────────────────

function handleImportExport(command: string) {
  const sheet: M2ImportableSheet = activeBranch.value === 'listed' ? 'M2-2-listed' : 'M2-2-unlisted'

  switch (command) {
    case 'exportTemplate':
      exportTemplate(sheet)
      break
    case 'exportData':
      exportData(sheet)
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importData(file, sheet)
          if (result) {
            await formData.loadData()
            _restoreRows()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

// ─── AI / Review ─────────────────────────────────────────────────────────────

async function handleAI(_section: string) {
  if (props.isReadonly) return
  aiLoading.value = true
  try {
    const cv = crossValidation.value
    const detailTotal = adjudicationEndAudited.value + (cv?.diff ?? 0)
    const context: Record<string, string> = {
      科目: '4001 实收资本/股本明细表',
      版本: activeBranch.value === 'listed' ? '上市公司版（股份）' : '非上市公司版（出资）',
      明细期末合计: fmtAmount(detailTotal),
      审定表期末: fmtAmount(adjudicationEndAudited.value),
      与审定表差额: cv ? fmtAmount(cv.diff ?? 0) : '—',
      是否勾稽一致: cv ? (cv.isMatch ? '是' : '否') : '—',
    }
    const text = await generateAiText({ section: 'm2-2-detail-note', context, existingContent: detailNote.value })
    if (!text) { ElMessage.warning('AI 未生成内容，请稍后重试'); return }
    detailNote.value = text
    saveDetailNote()
  } catch {
    ElMessage.warning('AI 生成失败，请稍后重试')
  } finally {
    aiLoading.value = false
  }
}
function saveDetailNote() {
  formData.debouncedSave('M2-M2-2-detail-note', { remark: detailNote.value || null })
}
function handleReview() { openReviewDialog?.('M2-2-detail', '明细表') }

// ─── Format ──────────────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
  const noteResp = formData.allResponses.value.get('M2-M2-2-detail-note')
  if (noteResp?.remark) detailNote.value = noteResp.remark
})

function _restoreRows() {
  // Restore listed rows
  const listedData = formData.allResponses.value.get('M2-M2-2-listed-full-data')
  if (listedData?.remark) {
    try {
      const parsed = JSON.parse(listedData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        listedRows.value = parsed
      }
    } catch { /* keep empty */ }
  }

  // Restore unlisted rows
  const unlistedData = formData.allResponses.value.get('M2-M2-2-unlisted-full-data')
  if (unlistedData?.remark) {
    try {
      const parsed = JSON.parse(unlistedData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        unlistedRows.value = parsed
      }
    } catch { /* keep empty */ }
  }
}
</script>

<style scoped>
.m2-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.branch-switcher { margin-bottom: 12px; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.detail-note-card { margin-top: 16px; }
.detail-note-card .card-header { display: flex; align-items: center; justify-content: space-between; }
.detail-note-card .card-title { font-size: 14px; font-weight: 600; color: #303133; }
.cross-wp-links { display: flex; align-items: center; gap: 8px; margin-top: 16px; padding: 10px 14px; background: #f0f9ff; border: 1px solid #d9ecff; border-radius: 6px; flex-wrap: wrap; }
.cross-wp-label { font-size: 12px; color: #409eff; font-weight: 500; }
.cross-wp-desc { font-size: 12px; color: #909399; }
.m2-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m2-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m2-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
