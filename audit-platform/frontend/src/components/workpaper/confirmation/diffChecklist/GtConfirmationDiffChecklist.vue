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
            @export-template="handleExportTemplate"
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
        :total-companies="data.companies.value.length"
        :balanced-count="data.companies.value.filter(c => c.status === 'balanced').length"
        :diff-count="data.companies.value.filter(c => c.status === 'diff' || c.status === 'over_materiality').length"
        :over-materiality-count="data.companies.value.filter(c => c.status === 'over_materiality').length"
        @update-global-note="handleGlobalNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
        @update-materiality="handleMaterialityUpdate"
      />
    </template>

    <!-- D0-4 带入确认弹窗 -->
    <el-dialog v-model="showD04ImportDialog" title="从 D0-4 差异调节表带入" width="520px" append-to-body>
      <div style="font-size:13px;line-height:1.8;color:#606266">
        <p style="margin:0 0 12px"><strong>操作说明：</strong></p>
        <ol style="padding-left:20px;margin:0 0 16px">
          <li>系统将从 D0-4 差异调节表中，筛选<strong>差异金额≠0</strong>的记录</li>
          <li>自动带入：函证索引号、被询证单位、科目、发函金额→A回函金额、回函金额→E账面金额</li>
          <li>每家公司创建一条调节记录，自动设置 A 和 E 初始值</li>
          <li>已存在相同索引号的公司不会重复导入</li>
        </ol>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:0">
          <template #title>带入后仍需补充</template>
          B/C/F/G 未达明细需在下方调节区域逐笔手动添加
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showD04ImportDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmD04Import">确认带入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted } from 'vue'
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
const isNewFormat = computed(() => !props.htmlData || !!props.htmlData?._format || Object.keys(props.htmlData || {}).length === 0)

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useDiffChecklistData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 当前选中公司 ────────────────────────────────────────────────────────────

const selectedCompany = ref<DiffChecklistCompany | null>(null)

// ─── 自动获取重要性水平 ──────────────────────────────────────────────────────

onMounted(async () => {
  // 如果重要性未配置且有 projectId，自动从 B15 获取
  if (!data.materialityConfig.value?.performance_materiality && props.projectId) {
    try {
      const { getMateriality } = await import('@/services/auditPlatformApi')
      const year = props.year ? parseInt(props.year) : new Date().getFullYear()
      const matData = await getMateriality(props.projectId, year)
      if (matData?.performance_materiality) {
        data.materialityConfig.value = {
          performance_materiality: matData.performance_materiality,
          source: 'auto',
          is_overridden: false,
        }
      }
    } catch (e) {
      // 静默失败：重要性获取非关键路径
      console.debug('[DiffChecklist] 自动获取重要性失败（可手动配置）:', e)
    }
  }
})

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
  showD04ImportDialog.value = true
}

const showD04ImportDialog = ref(false)

function confirmD04Import() {
  showD04ImportDialog.value = false
  // TODO: 调用跨底稿引用 API 获取 D0-4 差异≠0 行
  console.log('[GtConfirmationDiffChecklist] 执行从 D0-4 带入')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationDiffChecklist] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationDiffChecklist] Excel 导出')
}

async function handleExportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 数据模板（基础信息）
    const headers = ['序号', '函证索引号', '被询证单位', '科目', 'A回函金额(对方确认)', 'E账面金额(我方账面)']
    const example = ['1', 'D0-001', '示例公司（请删除）', '应收账款', '100000', '100000']
    const ws = utils.aoa_to_sheet([headers, example])
    ws['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 22 }, { wch: 12 }, { wch: 18 }, { wch: 18 }]
    utils.book_append_sheet(wb, ws, '差异检查表')

    // Sheet 2: 未达明细模板（B/C/F/G 调节明细行）
    const subHeaders = ['函证索引号', '调节区块', '货物验收/付款日期', '确认增减日期', '凭证号', '摘要', '金额']
    const subExample1 = ['D0-001', 'B(对方已收我方未付)', '2025-12-28', '2025-12-30', '记-128', '12月发货在途', '5000']
    const subExample2 = ['D0-001', 'F(我方已收对方未付)', '2025-12-29', '2025-12-31', '收-099', '12月回款在途', '3000']
    const subWs = utils.aoa_to_sheet([subHeaders, subExample1, subExample2])
    subWs['!cols'] = [{ wch: 12 }, { wch: 22 }, { wch: 16 }, { wch: 14 }, { wch: 10 }, { wch: 18 }, { wch: 10 }]
    utils.book_append_sheet(wb, subWs, '未达明细')

    // Sheet 3: 填写说明
    const instructions = [
      ['D0-4b 函证差异检查表 — 导入模板填写说明'],
      [''],
      ['【Sheet 1: 差异检查表】— 每家公司一行'],
      ['  函证索引号：与 D0-1/D0-4 索引一致（必填）'],
      ['  被询证单位：被函证公司全称（必填）'],
      ['  A回函金额：对方确认的金额（必填）'],
      ['  E账面金额：我方账面余额（必填）'],
      ['  科目：涉及科目（选填）'],
      [''],
      ['【Sheet 2: 未达明细】— 每笔未达账项一行'],
      ['  函证索引号：对应 Sheet1 中的公司（必填）'],
      ['  调节区块：填 B/C/F/G 之一（必填）'],
      ['    B = 对方已收我方未付（我方未达）'],
      ['    C = 我方已付对方未收（对方未达）'],
      ['    F = 我方已收对方未付（对方未达）'],
      ['    G = 对方已付我方未收（我方未达）'],
      ['  货物验收/付款日期：业务发生日期'],
      ['  确认增减日期：对方/我方确认入账日期'],
      ['  凭证号：记账凭证编号'],
      ['  摘要：简要说明'],
      ['  金额：未达金额（正数）'],
      [''],
      ['【A-I 公式链】'],
      ['  D = A + B - C（调节后对方余额）'],
      ['  H = E + F - G（调节后我方余额）'],
      ['  I = D - H（最终差异，应为0）'],
      [''],
      ['【注意】'],
      ['  1. 导入时系统按函证索引号匹配公司，自动归入对应 B/C/F/G 明细'],
      ['  2. D/H/I 系统自动计算，无需手动填写'],
      ['  3. 示例行请删除后再填写实际数据'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 65 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'D0-4b差异检查表导入模板.xlsx')
  } catch (e: any) {
    console.error('[DiffChecklist] Export template error:', e)
  }
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
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-top: 8px;
}

.gt-confirmation-diff-checklist__master {
  width: 100%;
}

.gt-confirmation-diff-checklist__detail {
  width: 100%;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  max-height: 700px;
  overflow-y: auto;
}

@media (max-width: 1200px) {
  .gt-confirmation-diff-checklist__layout {
    gap: 8px;
  }
}
</style>
