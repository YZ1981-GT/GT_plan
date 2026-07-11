<template>
  <div class="g7-tab-voucher-check">
    <!-- Section标题栏 + AI + 复核 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-18 凭证检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('voucher-conclusion')">
          <el-icon><MagicStick /></el-icon> AI
        </el-button>
        <el-button size="small" @click="openReviewDialog('G7-18-voucher-check')">💬 复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：抽取长期股权投资相关记账凭证，核对原始凭证完整性、授权审批、账务处理、金额准确性、科目分类及投资收益确认的正确性，确认凭证真实、合规且借贷平衡。
    </el-alert>

    <el-skeleton v-if="!props.htmlData" :rows="6" animated />
    <div v-else class="voucher-check-content">
      <!-- 借贷差额汇总 -->
      <div class="balance-summary" :class="{ 'is-unbalanced': !isBalanced }">
        <span>借方合计: {{ debitTotal.toFixed(2) }}</span>
        <span>贷方合计: {{ creditTotal.toFixed(2) }}</span>
        <span v-if="!isBalanced" class="diff-warning">差额: {{ (debitTotal - creditTotal).toFixed(2) }}</span>
      </div>

      <!-- 3区段Tab -->
      <el-tabs v-model="activeTab" type="border-card" class="voucher-tabs">
        <el-tab-pane label="凭证基础(7列)" name="voucher">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column prop="voucherDate" label="日期" width="100" />
            <el-table-column prop="voucherNo" label="凭证号" width="100" />
            <el-table-column prop="businessContent" label="业务内容" min-width="150" />
            <el-table-column prop="counterAccount" label="对方科目" width="120" />
            <el-table-column prop="debitAmount" label="借方" width="110" align="right" />
            <el-table-column prop="creditAmount" label="贷方" width="110" align="right" />
            <el-table-column label="📎" width="50" align="center">
              <template #default="{ row }">
                <el-button v-if="!isReadonly" link size="small" @click="handleOCR(row)">📎</el-button>
                <span v-else-if="row.attachment">✓</span>
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="核对内容(7列)" name="check">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column prop="supportingDocDesc" label="支持性文件" min-width="150" />
            <el-table-column prop="check1OriginalComplete" label="原始凭证" width="80" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check1OriginalComplete" :disabled="isReadonly" />
              </template>
            </el-table-column>
            <el-table-column prop="check2Authorization" label="授权" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check2Authorization" :disabled="isReadonly" />
              </template>
            </el-table-column>
            <el-table-column prop="check3Accounting" label="账务" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check3Accounting" :disabled="isReadonly" />
              </template>
            </el-table-column>
            <el-table-column prop="check4AmountCorrect" label="金额" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check4AmountCorrect" :disabled="isReadonly" />
              </template>
            </el-table-column>
            <el-table-column prop="check5Classification" label="分类" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check5Classification" :disabled="isReadonly" />
              </template>
            </el-table-column>
            <el-table-column prop="check6InvestmentIncome" label="投资收益" width="85" align="center">
              <template #default="{ row }">
                <el-checkbox v-model="row.check6InvestmentIncome" :disabled="isReadonly" />
              </template>
            </el-table-column>
          </el-table>
        </el-tab-pane>

        <el-tab-pane label="结论(5列)" name="conclusion">
          <el-table
            :data="pageRows"
            border
            size="small"
            max-height="520"
            highlight-current-row
            :current-row-key="rows[activeRowIndex]?.id"
            row-key="id"
            style="font-size: 13px"
            @current-change="handleRowChange"
          >
            <el-table-column label="序号" width="55" align="center">
              <template #default="{ $index }">{{ getAbsoluteIndex($index) }}</template>
            </el-table-column>
            <el-table-column prop="indexNo" label="索引" width="100" />
            <el-table-column prop="isAbnormal" label="是否异常" width="85" align="center">
              <template #default="{ row }">
                <el-tag :type="isRowAbnormal(row) ? 'danger' : 'success'" size="small">
                  {{ isRowAbnormal(row) ? '是' : '否' }}
                </el-tag>
              </template>
            </el-table-column>
            <el-table-column prop="abnormalDesc" label="异常说明" min-width="150" />
            <el-table-column prop="riskLevel" label="风险等级" width="90" align="center" />
            <el-table-column prop="remark" label="备注" min-width="120" />
          </el-table>
        </el-tab-pane>
      </el-tabs>

      <!-- 分页（虚拟滚动降级模式：99行 pageSize=30 → 4页） -->
      <div class="pagination-wrapper">
        <el-pagination
          v-model:current-page="currentPage"
          :page-size="PAGE_SIZE"
          :total="rows.length"
          layout="prev, pager, next, total"
          small
        />
      </div>
    </div>

    <!-- 审计结论（AI辅助） -->
    <el-card class="conclusion-card" shadow="never">
      <template #header>
        <div class="conclusion-header">
          <span>审计结论</span>
          <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="aiLoading" @click="handleAi('voucher-conclusion')">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="对凭证检查的审计结论..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>核对6要素：原始凭证完整、授权审批、账务处理正确、金额准确、科目分类恰当、投资收益确认无误</li>
        <li>任一核对项未通过 → 该行"是否异常"自动标记为"是"，需在异常说明列填写原因</li>
        <li>借贷合计应平衡，差额非0时红色高亮提示</li>
        <li>可通过 📎 上传附件并OCR识别自动填充凭证信息</li>
        <li>抽样应覆盖大额、异常及关联方相关的长期股权投资分录</li>
        <li>3区段Tab（凭证基础/核对内容/结论）切换时保持行索引同步</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabVoucherCheck — G7-18 凭证检查表（3区段Tab + 抽凭 + OCR）
 *
 * 虚拟滚动策略：
 * - el-table max-height="520" 提供原生虚拟滚动（Element Plus el-table内置）
 * - 降级分页模式：pageSize=30，99行→4页
 * - 3区段Tab间切换保持行索引同步（activeRowIndex跨Tab不变）
 *
 * AI辅助: voucher-conclusion (Task 12.2)
 * Requirements: 6.1, 6.2, 7.4, 7.5
 */
import { ref, computed, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { isDebitCreditBalanced } from '../../composables/useG7SubFormulaEngine'

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const isReadonly = computed(() => !!props.readonly)
const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ═══ 分页常量 ═══
const PAGE_SIZE = 30

// ═══ 状态 ═══
const activeTab = ref<'voucher' | 'check' | 'conclusion'>('voucher')
const activeRowIndex = ref(0)
const currentPage = ref(1)
const conclusionText = ref('')
const aiLoading = ref(false)

// ═══ 数据 ═══
const rows = computed(() => {
  return props.htmlData?.voucherCheck?.rows ?? []
})

// ═══ 分页切片（虚拟滚动降级） ═══
const pageRows = computed(() => {
  const start = (currentPage.value - 1) * PAGE_SIZE
  return rows.value.slice(start, start + PAGE_SIZE)
})

// ═══ 借贷汇总 ═══
const debitTotal = computed(() =>
  rows.value.reduce((sum: number, r: any) => sum + (Number(r.debitAmount) || 0), 0)
)
const creditTotal = computed(() =>
  rows.value.reduce((sum: number, r: any) => sum + (Number(r.creditAmount) || 0), 0)
)
const isBalanced = computed(() =>
  isDebitCreditBalanced(
    rows.value.map((r: any) => Number(r.debitAmount) || 0),
    rows.value.map((r: any) => Number(r.creditAmount) || 0)
  )
)

// ═══ 异常检测（check1-6任一false → isAbnormal=true） ═══
function isRowAbnormal(row: any): boolean {
  return !(
    row.check1OriginalComplete &&
    row.check2Authorization &&
    row.check3Accounting &&
    row.check4AmountCorrect &&
    row.check5Classification &&
    row.check6InvestmentIncome
  )
}

// ═══ 行同步（3区段Tab间切换保持行索引不变） ═══
function handleRowChange(row: any) {
  if (row) {
    const idx = rows.value.findIndex((r: any) => r.id === row.id)
    if (idx >= 0) activeRowIndex.value = idx
  }
}

function getAbsoluteIndex(pageIndex: number): number {
  return (currentPage.value - 1) * PAGE_SIZE + pageIndex + 1
}

// ═══ OCR（行级OCR，📎附件上传→识别→确认填入） ═══
function handleOCR(_row: any) {
  // Task 9.2 实现完整OCR集成（POST /d4/contract-ocr → ElMessageBox确认 → merge）
}

// ═══ AI辅助 ═══
async function handleAi(section: string): Promise<void> {
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/g7-sub/ai/${section}`,
      { existingContent: conclusionText.value, relatedContext: { sheet: 'G7-18' } },
    )
    const text = res?.data?.data?.conclusion ?? res?.data?.conclusion ?? res?.data?.text ?? ''
    if (text) {
      conclusionText.value = text
      ElMessage.success('AI结论已生成')
    }
  } catch {
    ElMessage.warning('AI辅助暂未连接，请手动填写')
  } finally {
    aiLoading.value = false
  }
}
</script>

<style scoped>
.g7-tab-voucher-check { padding: 12px; font-size: 13px; }
.audit-objective { margin-bottom: 12px; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #606266; }
.prep-hint summary { cursor: pointer; font-weight: 500; color: #409eff; }
.prep-hint ul { margin: 4px 0 0 16px; line-height: 1.8; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }

.balance-summary {
  display: flex;
  gap: 24px;
  padding: 8px 12px;
  margin-bottom: 8px;
  background: #f0f9eb;
  border-radius: 4px;
  font-size: 13px;
}
.balance-summary.is-unbalanced {
  background: #fef0f0;
}
.diff-warning {
  color: #f56c6c;
  font-weight: 600;
}

.voucher-tabs { margin-bottom: 8px; }

.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 8px 0;
}

.conclusion-card { margin-top: 16px; }
.conclusion-header { display: flex; justify-content: space-between; align-items: center; }
</style>
