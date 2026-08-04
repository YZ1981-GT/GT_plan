<template>
  <div class="gt-confirmation-diff-reconcile">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-diff-reconcile__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：diff-reconcile-v1 -->
    <template v-else>
      <!-- 看板 -->
      <DiffReconcileDashboard
        :metrics="data.metrics.value"
        :subject-summary="data.subjectSummary.value"
        :unclassified-count="analysis.unclassifiedCount.value"
        :has-materiality-config="!!data.materialityConfig.value.performance_materiality"
      />

      <!-- 差异明细网格 -->
      <DiffReconcileMaster
        :rows="data.rows.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :subject-options="subjectOptions"
        :diff-type-options="diffTypeOptions"
        :subject-summary="data.subjectSummary.value"
        :is-over-materiality="data.isOverMateriality"
        @add="handleAdd"
        @delete="handleDelete"
        @save="handleSave"
        @update="handleUpdate"
        @import-d01="handleImportD01"
        @import-excel="handleImportExcel"
        @export-excel="handleExportExcel"
        @export-template="handleExportTemplate"
        @jump-d01="handleJumpD01"
      />

      <!-- 差异原因分析表 -->
      <DiffReconcileAnalysis
        :analysis-groups="analysis.analysisGroups.value"
        :totals="analysis.analysisTotals.value"
        :unclassified-count="analysis.unclassifiedCount.value"
        :readonly="readonly"
        @update-note="analysis.updateAnalysisNote"
        @update-action="analysis.updateAnalysisAction"
      />

      <!-- 审计说明 + 结论 + 重要性配置 -->
      <DiffReconcileConclusion
        :audit-note="data.auditNote.value"
        :conclusion="data.conclusion.value"
        :materiality-config="data.materialityConfig.value"
        :readonly="readonly"
        :has-unresolved="analysis.unclassifiedCount.value > 0"
        :total-count="data.metrics.value.total_count"
        :difference-net="data.metrics.value.difference_net_total"
        :difference-abs="data.metrics.value.difference_abs_total"
        :adjustment-count="data.metrics.value.adjustment_count"
        :analyzed-rate="data.metrics.value.analyzed_rate"
        @update-note="handleAuditNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
        @update-materiality="handleMaterialityUpdate"
      />
    </template>

    <!-- D0-1 带入确认弹窗 -->
    <el-dialog v-model="showD01ImportDialog" title="从 D0-1 带入差异数据" width="520px" append-to-body>
      <div style="font-size:13px;line-height:1.8;color:#606266">
        <p style="margin:0 0 12px"><strong>操作说明：</strong></p>
        <ol style="padding-left:20px;margin:0 0 16px">
          <li>系统将从 D0-1 函证结果汇总表中，筛选<strong>相符情况为"不符"</strong>的函证记录</li>
          <li>自动带入：函证索引号、被询证单位、科目、发函金额、回函金额</li>
          <li>差异金额将自动计算（发函金额 − 回函金额）</li>
          <li>已存在相同索引号的记录不会重复导入</li>
        </ol>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:0">
          <template #title>带入后仍需补充</template>
          差异类型、是否调整、差异说明等字段需手动填写完善
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showD01ImportDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmD01Import">确认带入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useDiffReconcileData } from './composables/useDiffReconcileData'
import { useDiffAnalysis } from './composables/useDiffAnalysis'
import { useD01DiffImport } from './composables/useD01DiffImport'
import { filterSummaryRows, defaultDiffFilter } from '../coordination/importFromSummary'
import { CONFIRMATION_DICTS, fallbackSelectOptions } from '../coordination/confirmationDicts'
import { getCycleConfirmationMeta } from '../coordination/cycleConfirmationMeta'
import { navigateToCycleSheet } from '../coordination/navigateToCycleSheet'
import type { DiffReconcileRow } from './diffReconcileTypes'

import DiffReconcileDashboard from './DiffReconcileDashboard.vue'
import DiffReconcileMaster from './DiffReconcileMaster.vue'
import DiffReconcileAnalysis from './DiffReconcileAnalysis.vue'
import DiffReconcileConclusion from './DiffReconcileConclusion.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// 🔴 setup 顶层取（useRouter 是 setup 作用域 composable，写进函数体静默失效）
const router = useRouter()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'diff-reconcile-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useDiffReconcileData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 分析层 ──────────────────────────────────────────────────────────────────

const analysis = useDiffAnalysis({
  rows: data.rows,
  analysisNotes: data.analysisNotes,
  computeDifference: data.computeDifference,
})

// ─── D0-1 带入 ──────────────────────────────────────────────────────────────

const d01Import = useD01DiffImport({
  existingIndexes: () => new Set(
    data.rows.value.map((r) => r.confirm_index).filter(Boolean) as string[]
  ),
  onImport: data.importRows,
})

// ─── 字典选项 ────────────────────────────────────────────────────────────────

/**
 * 「账户/交易」列取值 —— 单一真源 `CONFIRMATION_DICT_FALLBACK[SUBJECT]`。
 *
 * 🔴 改造前这里是 13 项硬编码字面量，**无一个 H 循环科目** →
 * H0-4 差异核对表在固定资产循环上选不出固定资产/工程物资/使用权资产/租赁负债。
 * spec: h0-confirmation-source-fidelity-and-linkage R1.4
 */
const subjectOptions = computed(() => fallbackSelectOptions(CONFIRMATION_DICTS.SUBJECT))

const diffTypeOptions = computed(() => [
  { value: 'time', label: '时间性差异' },
  { value: 'accounting', label: '记账差异' },
  { value: 'unrecorded', label: '未达账项' },
  { value: 'other', label: '其他差异' },
])

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAdd() {
  data.addRow()
}

/** 删除勾选行（行 ID 由 DiffReconcileMaster 随 delete 事件上报）。 */
function handleDelete(rowIds: string[]) {
  if (!rowIds?.length) {
    ElMessage.info('请先勾选要删除的差异行')
    return
  }
  data.deleteRows(rowIds)
  ElMessage.success(`已删除 ${rowIds.length} 行`)
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

function handleImportD01() {
  showD01ImportDialog.value = true
}

const showD01ImportDialog = ref(false)

async function confirmD01Import() {
  showD01ImportDialog.value = false
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文，无法带入')
    return
  }
  // 循环码派生：D0-4→D0-1, F0-4→F0-1（独立注册优先）; 回退 D0/F0（整册）
  const cycleBase = (props.wpCode || '').split('-')[0]
  const summaryCode = cycleBase + '-1'
  try {
    let res = await filterSummaryRows(props.projectId, summaryCode, defaultDiffFilter)
    // 回退：X0-1 不存在时尝试父底稿 X0（整册含 confirmation-v1 sheet）
    if (!res) {
      res = await filterSummaryRows(props.projectId, cycleBase, defaultDiffFilter)
    }
    if (!res) {
      ElMessage.warning(`未找到 ${summaryCode} 或 ${cycleBase} 函证结果汇总底稿`)
      return
    }
    if (res.rows.length === 0) {
      ElMessage.info(`${summaryCode} 暂无不符项（差异=0 或未回函的行不纳入）`)
      return
    }
    d01Import.fetchAndImport(res.rows)
    ElMessage.success(`已从汇总表带入 ${d01Import.lastImportCount.value} 条差异`)
  } catch (e: any) {
    console.warn('[GtConfirmationDiffReconcile] 从 D0-1 带入失败:', e)
    ElMessage.error('带入失败：' + (e?.message || '网络错误'))
  }
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationDiffReconcile] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationDiffReconcile] Excel 导出')
}

async function handleExportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 数据模板
    const headers = ['序号', '函证索引号', '被询证单位', '科目', '发函金额', '回函金额', '差异类型', '是否调整', '差异说明']
    const example = ['1', 'D0-001', '示例公司（请删除）', '应收账款', '100000', '99000', '时间性差异', '否', '在途款项']
    const ws = utils.aoa_to_sheet([headers, example])
    ws['!cols'] = [
      { wch: 6 }, { wch: 12 }, { wch: 22 }, { wch: 12 }, { wch: 12 },
      { wch: 12 }, { wch: 12 }, { wch: 8 }, { wch: 20 },
    ]
    utils.book_append_sheet(wb, ws, '差异明细')

    // Sheet 2: 填写说明
    const instructions = [
      ['D0-4 差异调节表 — 导入模板填写说明'],
      [''],
      ['【必填列】'],
      ['  函证索引号：与 D0-1 函证汇总表索引一致（如 D0-001）'],
      ['  被询证单位：被函证公司全称'],
      ['  发函金额：账面函证金额（数字，单位：元）'],
      ['  回函金额：对方确认金额（数字，单位：元）'],
      [''],
      ['【选填列】'],
      ['  序号：自动生成（留空即可）'],
      ['  科目：涉及科目（应收账款/合同负债等，可自定义）'],
      ['  差异类型：时间性差异 / 记账差异 / 未达账项 / 其他差异'],
      ['  是否调整：填"是"或"否"，表示该差异是否需要审计调整'],
      ['  差异说明：简述差异原因（如：在途款项、截止日差异）'],
      [''],
      ['【差异金额】'],
      ['  系统自动计算：差异金额 = 发函金额 − 回函金额'],
      ['  无需手动填写'],
      [''],
      ['【注意事项】'],
      ['  1. 第一行为表头请勿修改'],
      ['  2. 示例行（第2行）请删除后再填写实际数据'],
      ['  3. 金额列请填纯数字，不要带"元"或千分位逗号'],
      ['  4. 也可使用"从 D0-1 带入"按钮自动带入不符项'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 60 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'D0-4差异调节导入模板.xlsx')
  } catch (e: any) {
    console.error('[DiffReconcile] Export template error:', e)
  }
}

/**
 * 跳转本循环的函证结果汇总表。
 * 🔴 目标编码按 `getCycleConfirmationMeta(wpCode).summaryCode` 派生，禁写 `'D0-1'` 字面量
 *    —— 本组件被 D0/F0/G0/H0/K0/L0 六个循环共享（E0 无独立差异表）。
 */
function handleJumpD01(confirmIndex: string) {
  const meta = getCycleConfirmationMeta(props.wpCode)
  void navigateToCycleSheet({
    router,
    projectId: props.projectId,
    targetWpCode: meta.summaryCode,
    confirmIndex,
  })
}

function handleAuditNoteUpdate(field: string, value: string) {
  ;(data.auditNote.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

function handleMaterialityUpdate(value: number) {
  data.materialityConfig.value.performance_materiality = value
  data.materialityConfig.value.is_overridden = true
  data.materialityConfig.value.source = 'manual'
  data.isDirty.value = true
}
</script>

<style scoped>
.gt-confirmation-diff-reconcile {
  padding: 8px 0;
}

.gt-confirmation-diff-reconcile__legacy-notice {
  margin-bottom: 12px;
}
</style>
