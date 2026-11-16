<template>
  <div class="m5-tab-detail">
    <!-- ═══ 标题 + DualMode + 导入导出 + AI/复核 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <el-button text size="small" @click="$emit('navigate', '底稿目录')">← 返回目录</el-button>
        <h3 class="section-title">M5-2 盈余公积明细表</h3>
        <el-tag type="success" effect="dark" size="small" class="equity-badge">
          权益类·贷方余额
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">
            导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
          </el-button>
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
        <el-button type="primary" size="small" :loading="isSaving" @click="handleSave">
          保存
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>盈余公积明细（4101）为权益类贷方科目：</strong>
        期末余额 = 期初 + 本期计提（贷方增加） − 本期转增资本（借方减少） − 本期弥补亏损（借方减少）。
        法定盈余公积按净利润（弥补以前年度亏损后）10%计提，累计达注册资本50%可不再计提。
        任意盈余公积由股东大会决议自主计提。
        明细表分两区段展示，合计应与M5-1审定表一致。
        支持动态新增明细行 + 导入导出。
      </div>
    </div>

    <!-- ═══ 明细表（模板驱动：固定 4 行 × 17 列，行标签与列均来自模板） ═══ -->
    <div class="block-section">
      <div class="block-header">
        <h4 class="block-title">盈余公积明细（法定 / 任意 / 利润归还投资 / 其他）</h4>
        <span class="block-hint">行与列均按权威模板渲染；公式列在线编辑侧重算</span>
      </div>
      <GtMCycleDetailTable
        entry="M5"
        :rows="detailRows"
        :readonly="isReadonly"
        @update="handleCellUpdate"
      />
    </div>

    <!-- ═══ 交叉验证状态（只比审定数合计，不重算模板公式） ═══ -->
    <div class="detail-footer">
      <el-tag :type="crossValidation.isMatch ? 'success' : 'warning'" size="small" effect="plain">
        与 M5-1 审定表对比：{{ crossValidation.hint }}
      </el-tag>
    </div>

    <!-- ═══ 审计说明（el-card包裹） ═══ -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span class="card-title">明细表审计说明</span>
          <el-button size="small" :loading="aiLoading === 'detailNote'" :disabled="isReadonly" @click="handleAI('detailNote')"><el-icon><MagicStick /></el-icon> AI辅助</el-button>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请填写盈余公积明细表审计说明..." :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- ═══ 编制提示（折叠） ═══ -->
    <details class="m5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>盈余公积（4101）为<strong>权益类贷方科目</strong>：期末 = 期初 + 本期计提 − 本期转增资本 − 本期弥补亏损</li>
        <li>法定盈余公积：按净利润（弥补以前年度亏损后）<strong>10%</strong>计提，累计达注册资本<strong>50%</strong>可不再计提</li>
        <li>任意盈余公积：股东大会决议自主计提（无比例限制）</li>
        <li>明细表分两区段：法定盈余公积明细 + 任意盈余公积明细</li>
        <li>明细表合计应与 M5-1 审定表对应区块小计一致（交叉验证）</li>
        <li>支持动态行新增：点击"+ 新增明细"后输入来源项目名称</li>
        <li>支持导入导出：通过"导入导出"下拉菜单操作（导出模板/导出数据/导入数据）</li>
        <li>12公式实时计算：每行期末自动 = 期初 + 计提 − 转增 − 弥补</li>
      </ul>
    </details>

    <!-- ═══ 隐藏文件上传input ═══ -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="handleFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * M5TabDetail — M5-2 盈余公积明细表（**模板驱动**）
 *
 * spec: `m-cycle-key-naming-unification` §R12
 *
 * 旧实现把明细表手写成 6 列（项目/期初/本期计提/转增资本/弥补亏损/期末）并按「法定 / 任意」
 * 两个区段拆表、各自加一行小计 —— 而模板实际是 **4 固定行 × 17 列**（未审数 6 列 + 期初调整 2 列 +
 * 账项调整 2 列 + 重分类调整 2 列 + 审定数 4 列）+ 一行合计。两者列集合交集 = 0。
 *
 * 现在：列与行全部来自生成文件（真源 = provider + 权威 xlsx）；
 * 区段、小计、前端公式重算一律不再存在（模板那一行就是合计公式）。
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, Check, ArrowDown } from '@element-plus/icons-vue'
import { useM5FormData } from '../../composables/useM5FormData'
import { useM5ImportExport } from '../../composables/useM5ImportExport'
import type { GenerateWorkpaperAiText } from '../../composables/useWorkpaperScaffold'
import { useM5Detail, createM5EmptyRows, type M5DetailRow } from '../../composables/useM5Detail'
import GtMCycleDetailTable from '../../m-cycle/GtMCycleDetailTable.vue'

const props = defineProps<{ wpId: string; projectId: string; isReadonly: boolean }>()
const emit = defineEmits<{ (e: 'navigate', sheetName: string): void; (e: 'save'): void }>()

const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ────────────────────────────────────────────────────────────
const formData = useM5FormData({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const importExport = useM5ImportExport({ wpId: computed(() => props.wpId), projectId: computed(() => props.projectId) })
const generateAiText = inject<GenerateWorkpaperAiText>('generateAiText', async () => '')
const aiLoading = ref('')

const detailRows = ref<M5DetailRow[]>(createM5EmptyRows())
const { ensureTemplateRows, updateRow, saveAll } = useM5Detail(formData, detailRows)

/** 单元格修改（来自模板驱动表格） */
function handleCellUpdate(payload: { index: number; jsonKey: string; value: string | number }): void {
  updateRow(payload.index, payload.jsonKey, payload.value)
}

// ─── 与 M5-1 审定表对比（只比合计，不重算模板公式） ──────────────────
const crossValidation = computed(() => {
  const resp = formData.allResponses.value.get('M5-1-total-audited')
  const adjudicated = Number(resp?.remark) || 0
  const local = detailRows.value.reduce((sum, r) => sum + (Number(r.auditedClosing ?? 0) || 0), 0)
  const diff = local - adjudicated
  const isMatch = Math.abs(diff) < 0.01
  return {
    isMatch,
    hint: isMatch
      ? '一致 ✓'
      : `本表审定合计 ${fmtAmount(local)} vs 审定表 ${fmtAmount(adjudicated)}（差 ${fmtAmount(diff)}）`,
  }
})

// ─── UI State ────────────────────────────────────────────────────────────
const isSaving = ref(false)
const auditNote = ref('')
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
    emit('save')
  } finally { isSaving.value = false }
}

function saveAuditNote() {
  formData.debouncedSave('M5-2-auditNote', { remark: auditNote.value || null })
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
  openReviewDialog('M5-2', 'M5-2 盈余公积明细表')
}

/** M5-2 明细表在导入导出侧的 sheet 名（与 M5ImportExport 的 sheet 白名单一致） */
const M5_IMPORT_EXPORT_SHEET = 'M5-2'

async function handleImportExport(command: string): Promise<void> {
  try {
    if (command === 'exportTemplate') await importExport.exportTemplate(M5_IMPORT_EXPORT_SHEET)
    else if (command === 'exportData') await importExport.exportData(M5_IMPORT_EXPORT_SHEET)
    else if (command === 'importData') fileInputRef.value?.click()
  } catch { ElMessage.error('操作失败') }
}

async function handleFileSelected(e: Event): Promise<void> {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  try {
    const rows = await importExport.importData(M5_IMPORT_EXPORT_SHEET, file)
    if (Array.isArray(rows) && rows.length) {
      detailRows.value = rows as M5DetailRow[]
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
.m5-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.equity-badge { font-weight: 600; }
.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }
.block-section { margin-bottom: 24px; }
.block-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.block-title { margin: 0; font-size: 14px; font-weight: 600; color: #303133; }
.block-subtotal { margin-top: 8px; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }
.total-row-label { font-weight: 700; color: #303133; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
:deep(.subtotal-row) { background: #f0f9eb !important; font-weight: 600; }
:deep(.subtotal-row td) { border-top: 2px solid #67c23a; }
.detail-footer { margin-top: 8px; margin-bottom: 16px; display: flex; align-items: center; gap: 12px; flex-wrap: wrap; padding: 12px 16px; background: #f5f7fa; border-radius: 6px; }
.audit-note-card { margin-top: 16px; }
.card-title { font-size: 14px; font-weight: 600; color: #303133; }
.m5-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m5-details-tip summary { cursor: pointer; font-weight: 600; color: #303133; }
.m5-details-tip ul { margin: 8px 0 0; padding-left: 20px; }
.m5-details-tip li { margin-bottom: 4px; line-height: 1.5; }
</style>
