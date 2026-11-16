<!--
  M7TabDetail.vue — M7-2 明细表（计提+使用，27列 → 3区段Tab）

  3区段Tab切换：计提(贷方增加) / 费用化使用(借方减少) / 资本化使用(借方减少+转固)
  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  22公式实时计算：权益类 期末=期初+贷方(计提)-借方(使用)
  动态行新增（ElMessageBox.prompt输入名称）+ 删除
  导入导出三级（el-dropdown）useM7ImportExport

  Spec: .kiro/specs/m7-special-reserve/ Task 4.3
  Requirements: 3.1-3.5
-->
<template>
  <div class="m7-tab-detail">
    <!-- ═══ 标题 + AI/复核按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M7-2 专项储备明细表</h3>
        <el-tag type="warning" size="small">27列·3区段Tab</el-tag>
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
        <el-button size="small" :loading="aiLoading === 'detail'" @click="handleAI('detail')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文琥珀块 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>M7-2 专项储备明细表（27列按3区段Tab管理）：</strong>
        计提区（项目名称/期初余额/本期计提/期末余额/期初AJE·RJE/计提AJE·RJE/审定期初·审定计提） →
        费用化使用区（费用性支出/使用AJE·RJE/审定使用） →
        资本化使用区（资本性支出/审定期末/上期对比/变动额·率/备注）。
        <em>权益类贷方：期末=期初+贷方(计提)-借方(使用)</em>
      </div>
    </div>

    <!-- ═══ 明细表（模板驱动：固定 7 行 × 18 列） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">专项储备明细</h4>
        <span class="block-hint">行与列均按权威模板渲染；公式列在线编辑侧重算</span>
      </div>
      <GtMCycleDetailTable
        entry="M7"
        :rows="detailRows"
        :readonly="isReadonly"
        @update="handleCellUpdate"
      />
    </div>

    <!-- ═══ 编制提示details折叠底部 ═══ -->
    <details class="m7-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>27列按3区段Tab拆分（计提/费用化使用/资本化使用），行跨区段同步</li>
        <li><strong>权益类贷方</strong>：期末=期初+贷方(计提)-借方(使用)</li>
        <li>公式列（虚线下划线）：E=B+C-D期末 | L=B+F+G审定期初 | M=C+H+J审定计提 | N=D+I+K审定使用 | O=L+M-N审定期末</li>
        <li>计提（贷方增加）：安全生产费/维简费等按产量或收入计提</li>
        <li>费用化使用（借方减少）：直接冲减专项储备</li>
        <li>资本化使用（借方减少）：形成固定资产+全额折旧冲减专项储备（联动H1）</li>
        <li>明细合计应与审定表M7-1核对一致</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * M7TabDetail — M7-2 专项储备明细表（**模板驱动**）
 *
 * spec: `m-cycle-key-naming-unification` §R12
 *
 * 旧实现把明细表手写成 3 个区段（计提 / 费用化 / 资本化）+ 动态行，
 * 而模板实际是 **7 固定行 × 18 列**（项目 + 未审数 + 三组调整 + 审定数 + 依据/索引/备注）。
 */
import { computed, inject, onMounted, ref } from 'vue'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useM7FormData } from '../../composables/useM7FormData'
import { useM7Detail, createM7EmptyRows, type M7DetailRow } from '../../composables/useM7Detail'
import GtMCycleDetailTable from '../../m-cycle/GtMCycleDetailTable.vue'
import { useM7ImportExport } from '../../composables/useM7ImportExport'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>(
  'openReviewDialog',
  () => {},
)
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

// ─── FormData + Composables ────────────────────────────────────────────
const formData = useM7FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetName: 'M7-2',
})

const detailRows = ref<M7DetailRow[]>(createM7EmptyRows())
const { ensureTemplateRows, updateRow, saveAll } = useM7Detail(formData, detailRows)

const importExport = useM7ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})

const M7_SHEET = 'M7-2'

function handleCellUpdate(payload: { index: number; jsonKey: string; value: string | number }): void {
  updateRow(payload.index, payload.jsonKey, payload.value)
}

// ─── UI state ─────────────────────────────────────────────────────
const isSaving = ref(false)
const fileInputRef = ref<HTMLInputElement | null>(null)

function fmtAmount(val: number): string {
  if (!val) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

async function handleSave() {
  isSaving.value = true
  try {
    saveAll()
    ElMessage.success('明细表已保存')
  } finally { isSaving.value = false }
}

async function handleAI(section: string) {
  if (props.isReadonly) return
  aiLoading.value = section
  try {
    await generateAiText(section, { wpId: props.wpId, projectId: props.projectId })
  } catch { ElMessage.error('AI 辅助失败') } finally { aiLoading.value = '' }
}

function handleReview() {
  openReviewDialog('M7-2', 'M7-2 专项储备明细表')
}

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'exportTemplate') await importExport.exportTemplate(M7_SHEET)
    else if (command === 'exportData') await importExport.exportData(M7_SHEET)
    else if (command === 'importData') fileInputRef.value?.click()
  } catch { ElMessage.error('操作失败') }
}

async function handleFileSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const rows = await importExport.importData(M7_SHEET, file)
    if (Array.isArray(rows) && rows.length) {
      detailRows.value = rows as M7DetailRow[]
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
.m7-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.formula-value--primary { color: #67c23a; font-weight: 600; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.el-table .summary-row) { background: #f0f9eb !important; font-weight: 600; }
.summary-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; flex-wrap: wrap; position: sticky; bottom: 0; z-index: 5; }
.m7-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m7-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m7-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
