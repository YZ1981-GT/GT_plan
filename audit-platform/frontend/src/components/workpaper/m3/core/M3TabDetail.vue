<template>
  <div class="m3-tab-detail">
    <!-- ═══ 标题 + 操作栏 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M3-2 库存股明细表</h3>
        <el-tag type="warning" size="small">19列·区段Tab·动态行</el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown :disabled="isReadonly" trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" :loading="aiLoading === 'detail'" :disabled="isReadonly" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>库存股明细表（按回购批次列示）：</strong>
        库存股是<strong>权益备抵类借方科目</strong>。期末库存股数 = 期初 + 回购股数 − 注销股数；
        期末金额 = 期初金额 + 回购金额 − 注销金额。
        19列宽表拆3区段Tab管理（回购信息 / 注销情况 / 期末余额），行同步。
      </div>
    </div>

    <!-- ═══ 明细表（模板驱动：固定 10 行 × 19 列） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">库存股明细（按回购类别）</h4>
        <span class="block-hint">行与列均按权威模板渲染；公式列在线编辑侧重算</span>
      </div>
      <GtMCycleDetailTable
        entry="M3"
        :rows="detailRows"
        :readonly="isReadonly"
        @update="handleCellUpdate"
      />
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="m3-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li><strong>权益备抵借方铁律</strong>：期末 = 期初 + 本期增加 − 本期减少（转让 / 注销）</li>
        <li>本表按权威模板渲染：**10 固定行 × 19 列**，行标签与列均来自模板</li>
        <li>未审数 / 期初调整 / 账项调整 / 重分类调整 / 审定数 五组列与模板一致</li>
        <li>公式列（期末数 / 审定数）由在线编辑侧重算后同步，前端不重复计算</li>
        <li>明细合计应与 M3-1 审定表库存股期末余额一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M3TabDetail — M3-2 库存股明细表（**模板驱动**）
 *
 * spec: `m-cycle-key-naming-unification` §R12
 *
 * 旧实现把 19 列手写拆成 3 个区段 Tab（回购 / 注销 / 期末）、每段一张 el-table，
 * 而模板实际是 **10 固定行 × 19 列**。行与列现均按权威模板渲染。
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useM3FormData } from '../../composables/useM3FormData'
import { useM3Detail, createM3EmptyRows, type M3DetailRow } from '../../composables/useM3Detail'
import GtMCycleDetailTable from '../../m-cycle/GtMCycleDetailTable.vue'
import { useM3ImportExport } from '../../composables/useM3ImportExport'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>(
  'openReviewDialog',
  null,
)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData + Composables ────────────────────────────────────────────
const formData = useM3FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const detailRows = ref<M3DetailRow[]>(createM3EmptyRows())
const { ensureTemplateRows, updateRow, saveAll } = useM3Detail(formData, detailRows)

const { exportTemplate, exportData, importData } = useM3ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const M3_SHEET = 'M3-2'

function handleCellUpdate(payload: { index: number; jsonKey: string; value: string | number }): void {
  updateRow(payload.index, payload.jsonKey, payload.value)
}

// ─── UI state ─────────────────────────────────────────────────────
const isSaving = ref(false)
const auditNote = ref('')
const fileInputRef = ref<HTMLInputElement | null>(null)

function fmtAmount(val: number): string {
  if (!val) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtNumber(val: number): string {
  if (!val) return '—'
  return val.toLocaleString('zh-CN')
}

async function handleSave() {
  isSaving.value = true
  try {
    saveAll()
    ElMessage.success('明细表已保存')
  } finally { isSaving.value = false }
}

function saveAuditNote() {
  formData.debouncedSave('M3-2-auditNote', { remark: auditNote.value || null })
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    const text = await generateAiText(section, { wpId: props.wpId, projectId: props.projectId })
    if (section === 'detailNote' && text) { auditNote.value = text; saveAuditNote() }
  } catch { ElMessage.error('AI 辅助失败') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog?.('M3-2', 'M3-2 库存股明细表')
}

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'exportTemplate') await exportTemplate(M3_SHEET)
    else if (command === 'exportData') await exportData(M3_SHEET)
    else if (command === 'importData') fileInputRef.value?.click()
  } catch { ElMessage.error('操作失败') }
}

async function handleFileSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const rows = await importData(file, M3_SHEET as never)
    if (Array.isArray(rows) && rows.length) {
      detailRows.value = rows as M3DetailRow[]
      saveAll()
      ElMessage.success('导入成功')
    }
  } catch { ElMessage.error('导入失败') } finally { input.value = '' }
}

onMounted(async () => {
  await formData.loadData()
  ensureTemplateRows()
})
</script>

<style scoped>
.m3-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.batch-name { font-weight: 500; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.total-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; background: #f0f9eb; font-size: var(--wp-font-size, 13px); align-items: center; flex-wrap: wrap; }
.m3-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m3-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m3-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
