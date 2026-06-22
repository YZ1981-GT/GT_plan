<template>
  <div class="gt-confirmation-diff-checklist">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-diff-checklist__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：diff-checklist-v1 -->
    <template v-else>
      <!-- 看板 -->
      <ChecklistDashboard :metrics="data.metrics.value" />

      <!-- Master-Detail 布局 -->
      <div class="gt-confirmation-diff-checklist__layout">
        <!-- 左：公司列表 -->
        <div class="gt-confirmation-diff-checklist__master">
          <DiffChecklistMaster
            :companies="data.companies.value"
            :readonly="readonly"
            :is-dirty="data.isDirty.value"
            :subject-options="subjectOptions"
            @add="handleAddCompany"
            @delete="handleDeleteCompany"
            @save="handleSave"
            @update="handleUpdateCompany"
            @import-d04="handleImportD04"
            @import-excel="handleImportExcel"
            @export-excel="handleExportExcel"
            @jump-d04="handleJumpD04"
            @select="handleSelectCompany"
          />
        </div>

        <!-- 右：A-I 调节详情 -->
        <div class="gt-confirmation-diff-checklist__detail">
          <DiffChecklistDetail
            :company="selectedCompany"
            :readonly="readonly"
            @update="handleUpdateCompany"
            @add-sub-row="handleAddSubRow"
            @delete-sub-row="handleDeleteSubRow"
            @update-sub-row="handleUpdateSubRow"
          />
        </div>
      </div>

      <!-- 审计说明 + 结论 -->
      <ChecklistAuditNote
        :global-note="data.globalNote.value"
        :conclusion="data.conclusion.value"
        :materiality-config="data.materialityConfig.value"
        :readonly="readonly"
        @update-global-note="handleGlobalNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
        @update-materiality="handleMaterialityUpdate"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { useDiffChecklistData } from './composables/useDiffChecklistData'
import type { DiffChecklistCompany } from './diffChecklistTypes'

import ChecklistDashboard from './ChecklistDashboard.vue'
import DiffChecklistMaster from './DiffChecklistMaster.vue'
import DiffChecklistDetail from './DiffChecklistDetail.vue'
import ChecklistAuditNote from './ChecklistAuditNote.vue'

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

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'diff-checklist-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useDiffChecklistData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 当前选中公司 ────────────────────────────────────────────────────────────

const selectedCompany = ref<DiffChecklistCompany | null>(null)

function handleSelectCompany(company: DiffChecklistCompany | null) {
  // 刷新引用：从 companies 取最新数据
  if (company) {
    selectedCompany.value = data.companies.value.find((c) => c._row_id === company._row_id) ?? null
  } else {
    selectedCompany.value = null
  }
}

// ─── 字典选项 ────────────────────────────────────────────────────────────────

const subjectOptions = computed(() => [
  { value: '应收账款', label: '应收账款' },
  { value: '合同负债', label: '合同负债' },
  { value: '销售收入', label: '销售收入' },
  { value: '应收票据', label: '应收票据' },
  { value: '合同资产', label: '合同资产' },
  { value: '预付账款', label: '预付账款' },
  { value: '应付账款', label: '应付账款' },
  { value: '预收账款', label: '预收账款' },
  { value: '其他应收款', label: '其他应收款' },
  { value: '其他应付款', label: '其他应付款' },
  { value: '银行存款', label: '银行存款' },
  { value: '短期借款', label: '短期借款' },
  { value: '长期借款', label: '长期借款' },
])

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAddCompany() {
  const newCompany = data.addCompany()
  selectedCompany.value = newCompany
}

function handleDeleteCompany(ids: string[]) {
  data.deleteCompany(ids)
  // 如果删除了当前选中的
  if (selectedCompany.value && ids.includes(selectedCompany.value._row_id!)) {
    selectedCompany.value = null
  }
}

function handleUpdateCompany(companyId: string, field: string, value: any) {
  data.updateCompany(companyId, field, value)
  // 刷新 detail 视图
  if (selectedCompany.value?._row_id === companyId) {
    selectedCompany.value = data.companies.value.find((c) => c._row_id === companyId) ?? null
  }
}

function handleAddSubRow(companyId: string, section: 'b' | 'c' | 'f' | 'g') {
  data.addSubTableRow(companyId, section)
  refreshSelectedCompany(companyId)
}

function handleDeleteSubRow(companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string) {
  data.deleteSubTableRow(companyId, section, rowId)
  refreshSelectedCompany(companyId)
}

function handleUpdateSubRow(companyId: string, section: 'b' | 'c' | 'f' | 'g', rowId: string, field: string, value: any) {
  data.updateSubTableRow(companyId, section, rowId, field, value)
  refreshSelectedCompany(companyId)
}

function refreshSelectedCompany(companyId: string) {
  if (selectedCompany.value?._row_id === companyId) {
    selectedCompany.value = { ...data.companies.value.find((c) => c._row_id === companyId)! }
  }
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleImportD04() {
  // TODO: 调用跨底稿引用机制获取 D0-4 差异≠0 行
  console.log('[GtConfirmationDiffChecklist] 从 D0-4 带入（待接入跨底稿引用）')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationDiffChecklist] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationDiffChecklist] Excel 导出')
}

function handleJumpD04(confirmIndex: string) {
  // TODO: 跨底稿跳转 D0-4
  console.log('[GtConfirmationDiffChecklist] 跳转 D0-4:', confirmIndex)
}

function handleGlobalNoteUpdate(value: string) {
  data.globalNote.value = value
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
  // 重算所有公司状态
  data.recomputeAll()
}
</script>

<style scoped>
.gt-confirmation-diff-checklist {
  padding: 8px 0;
}

.gt-confirmation-diff-checklist__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-diff-checklist__layout {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  margin-top: 8px;
}

.gt-confirmation-diff-checklist__master {
  min-width: 0;
}

.gt-confirmation-diff-checklist__detail {
  min-width: 0;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  max-height: 700px;
  overflow-y: auto;
}

@media (max-width: 1200px) {
  .gt-confirmation-diff-checklist__layout {
    grid-template-columns: 1fr;
  }
}
</style>
