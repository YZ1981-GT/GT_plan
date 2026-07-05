<script setup lang="ts">
/**
 * F4TabSupplierFinancing — F4-9 供应商融资检查
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.5
 * 3区域独立el-table（保理/票据融资/供应链融资）
 * "应重分类"/"未终止确认" 橙色高亮
 * 各区域独立增删 + 底部小计 + 底部总结textarea(AI)
 * 虚拟滚动(84行) + 导入导出
 * Requirements: 12.1~12.6
 */
import { inject, toRef, ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { useF4SupplierFinancing } from '../composables/useF4SupplierFinancing'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  factoringRows,
  noteRows,
  supplyChainRows,
  factoringSubtotal,
  noteSubtotal,
  supplyChainSubtotal,
  overallTotal,
  reclassifySummary,
  auditConclusion,
  addFactoringRow,
  addNoteRow,
  addSupplyChainRow,
  removeFactoringRow,
  removeNoteRow,
  removeSupplyChainRow,
  updateFactoringCell,
  updateNoteCell,
  updateSupplyChainCell,
  factoringRowClassName,
  noteRowClassName,
  supplyChainRowClassName,
} = useF4SupplierFinancing({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

// ─── AI 生成 ─────────────────────────────────────────────────────────────────
const aiLoading = ref(false)

async function generateAiConclusion() {
  aiLoading.value = true
  try {
    const { data } = await axios.post(`/api/workpapers/${props.wpId}/f4/ai/financing-evaluation`)
    auditConclusion.value = data?.data?.conclusion || data?.conclusion || ''
    ElMessage.success('AI结论已生成')
  } catch { ElMessage.error('AI生成失败') }
  finally { aiLoading.value = false }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-9`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-9供应商融资模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-9`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-9供应商融资数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-9`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<template>
  <div class="f4-tab-supplier-financing">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 供应商融资分3区域检查：保理融资、票据融资、供应链融资。</p>
        <p>2. 保理融资关注：是否满足终止确认条件（IFRS 9/CAS 23），未终止确认的橙色高亮。</p>
        <p>3. 票据融资关注：已贴现/已背书转让的票据是否应继续确认为负债。</p>
        <p>4. 供应链融资关注：是否修改了原有付款条件、是否应重分类为金融负债。</p>
        <p>5. "应重分类"或"未终止确认"的行橙色高亮，需在审计结论中披露。</p>
      </div>
    </details>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
      <div class="toolbar-right">
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-9-financing')"
        >复核</el-button>
      </div>
    </div>

    <!-- ─── 保理融资 ──────────────────────────────────────────────────── -->
    <div class="region-section">
      <div class="region-header">
        <h4 class="region-title">一、保理融资</h4>
        <el-button size="small" :disabled="isReadonly" @click="addFactoringRow">+ 新增行</el-button>
      </div>
      <el-table
        :data="factoringRows"
        border
        size="small"
        :row-class-name="factoringRowClassName"
        style="width: 100%; font-size: 13px"
        max-height="350"
      >
        <el-table-column prop="seq" label="序号" width="60" />
        <el-table-column label="供应商" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supplier" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'supplier', v)" />
            <span v-else>{{ row.supplier }}</span>
          </template>
        </el-table-column>
        <el-table-column label="保理公司" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.factoringCompany" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'factoringCompany', v)" />
            <span v-else>{{ row.factoringCompany }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateFactoringCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'date', v)" />
            <span v-else>{{ row.date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dueDate" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'dueDate', v)" />
            <span v-else>{{ row.dueDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="费率(%)" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.feeRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateFactoringCell(row.rowId, 'feeRate', v ?? 0)" />
            <span v-else>{{ row.feeRate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="追索权" min-width="80">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.hasRecourse" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'hasRecourse', v)">
              <el-option label="有" value="有" />
              <el-option label="无" value="无" />
            </el-select>
            <span v-else>{{ row.hasRecourse }}</span>
          </template>
        </el-table-column>
        <el-table-column label="终止确认" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isDerecognized" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'isDerecognized', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else :class="{ 'highlight-warn': row.isDerecognized === '否' }">{{ row.isDerecognized }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditEvaluation" size="small" @change="(v: string) => updateFactoringCell(row.rowId, 'auditEvaluation', v)" />
            <span v-else>{{ row.auditEvaluation }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeFactoringRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="region-subtotal">保理融资合计：{{ fmtAmount(factoringSubtotal) }}</div>
    </div>

    <!-- ─── 票据融资 ──────────────────────────────────────────────────── -->
    <div class="region-section">
      <div class="region-header">
        <h4 class="region-title">二、票据融资</h4>
        <el-button size="small" :disabled="isReadonly" @click="addNoteRow">+ 新增行</el-button>
      </div>
      <el-table
        :data="noteRows"
        border
        size="small"
        :row-class-name="noteRowClassName"
        style="width: 100%; font-size: 13px"
        max-height="350"
      >
        <el-table-column prop="seq" label="序号" width="60" />
        <el-table-column label="供应商" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supplier" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'supplier', v)" />
            <span v-else>{{ row.supplier }}</span>
          </template>
        </el-table-column>
        <el-table-column label="票据类型" min-width="100">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.noteType" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'noteType', v)">
              <el-option label="银行承兑" value="银行承兑" />
              <el-option label="商业承兑" value="商业承兑" />
            </el-select>
            <span v-else>{{ row.noteType }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateNoteCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出票日" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.issueDate" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'issueDate', v)" />
            <span v-else>{{ row.issueDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dueDate" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'dueDate', v)" />
            <span v-else>{{ row.dueDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贴现额" min-width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.discountAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateNoteCell(row.rowId, 'discountAmount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.discountAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贴现率(%)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.discountRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateNoteCell(row.rowId, 'discountRate', v ?? 0)" />
            <span v-else>{{ row.discountRate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="背书转让" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isEndorsed" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'isEndorsed', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.isEndorsed }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditEvaluation" size="small" @change="(v: string) => updateNoteCell(row.rowId, 'auditEvaluation', v)" />
            <span v-else>{{ row.auditEvaluation }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeNoteRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="region-subtotal">票据融资合计：{{ fmtAmount(noteSubtotal) }}</div>
    </div>

    <!-- ─── 供应链融资 ────────────────────────────────────────────────── -->
    <div class="region-section">
      <div class="region-header">
        <h4 class="region-title">三、供应链融资</h4>
        <el-button size="small" :disabled="isReadonly" @click="addSupplyChainRow">+ 新增行</el-button>
      </div>
      <el-table
        :data="supplyChainRows"
        border
        size="small"
        :row-class-name="supplyChainRowClassName"
        style="width: 100%; font-size: 13px"
        max-height="350"
      >
        <el-table-column prop="seq" label="序号" width="60" />
        <el-table-column label="供应商" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.supplier" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'supplier', v)" />
            <span v-else>{{ row.supplier }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核心企业" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.coreEnterprise" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'coreEnterprise', v)" />
            <span v-else>{{ row.coreEnterprise }}</span>
          </template>
        </el-table-column>
        <el-table-column label="金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.amount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSupplyChainCell(row.rowId, 'amount', v ?? 0)" />
            <span v-else>{{ fmtAmount(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.date" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'date', v)" />
            <span v-else>{{ row.date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.dueDate" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'dueDate', v)" />
            <span v-else>{{ row.dueDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="利率(%)" min-width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.rate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateSupplyChainCell(row.rowId, 'rate', v ?? 0)" />
            <span v-else>{{ row.rate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平台" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.platform" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'platform', v)" />
            <span v-else>{{ row.platform }}</span>
          </template>
        </el-table-column>
        <el-table-column label="修改条件" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.hasModifiedTerms" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'hasModifiedTerms', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else :class="{ 'highlight-warn': row.hasModifiedTerms === '是' }">{{ row.hasModifiedTerms }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应重分类" min-width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.shouldReclassify" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'shouldReclassify', v)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else :class="{ 'highlight-warn': row.shouldReclassify === '是' }">{{ row.shouldReclassify }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审计评价" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.auditEvaluation" size="small" @change="(v: string) => updateSupplyChainCell(row.rowId, 'auditEvaluation', v)" />
            <span v-else>{{ row.auditEvaluation }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60">
          <template #default="{ row }">
            <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeSupplyChainRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="region-subtotal">供应链融资合计：{{ fmtAmount(supplyChainSubtotal) }}</div>
    </div>

    <!-- ─── 底部总结 ──────────────────────────────────────────────────── -->
    <div class="summary-section">
      <div class="summary-stats">
        <span>融资合计：<strong>{{ fmtAmount(overallTotal) }}</strong></span>
        <span>未终止确认(保理)：<strong>{{ fmtAmount(reclassifySummary.factoringNotDerecognized) }}</strong></span>
        <span>应重分类(供应链)：<strong>{{ fmtAmount(reclassifySummary.supplyChainReclassify) }}</strong></span>
        <span>重分类建议合计：<strong>{{ fmtAmount(reclassifySummary.total) }}</strong></span>
      </div>
    </div>

    <el-card class="audit-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>审计结论</span>
          <div class="header-actions">
            <el-button size="small" :loading="aiLoading" :disabled="isReadonly" @click="generateAiConclusion">
              ✨ AI生成
            </el-button>
            <el-button
              v-if="openReviewDialog"
              size="small"
              @click="openReviewDialog('f4-9-conclusion')"
            >复核</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="请输入供应商融资检查审计结论，或点击AI生成..."
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-supplier-financing {
  font-size: 13px;
}
.guidance-details {
  margin-bottom: 12px;
  font-size: 13px;
}
.guidance-details .guidance-content {
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #f59e0b;
  margin-top: 6px;
  font-size: 12px;
  line-height: 1.8;
}
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 8px;
}
.region-section {
  margin-bottom: 20px;
}
.region-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.region-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin: 0;
}
.region-subtotal {
  margin-top: 6px;
  padding: 6px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
}
:deep(.financing-highlight td) {
  background: #fef3e6 !important;
}
.highlight-warn {
  color: #e6a23c;
  font-weight: 600;
}
.summary-section {
  margin: 16px 0 12px;
  padding: 10px 12px;
  background: #ecf5ff;
  border-radius: 4px;
}
.summary-stats {
  display: flex;
  gap: 24px;
  flex-wrap: wrap;
  font-size: 13px;
}
.audit-card {
  margin-top: 12px;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.header-actions {
  display: flex;
  gap: 8px;
}
</style>
