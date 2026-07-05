<!--
  G6TabVoucherCheck.vue — G6-15 凭证检查表（100行×22列 → 3区段Tab）

  3区段Tab切换（el-segmented）：
  - Tab1: 凭证基础(8列): 日期|凭证号|业务内容|对方科目|明细|借方|贷方|📎附件
  - Tab2: 核对内容(8列): 支持性文件|核对1-原始凭证|核对2-授权|核对3-账务|核对4-金额|核对5-分类|核对6-减值|核对7-利息
  - Tab3: 结论(6列): 索引|是否异常|异常说明|风险等级|处理建议|备注

  Tab切换行同步：切换Tab保持activeRowIndex
  虚拟滚动（100行）
  📎附件列: el-upload → handleRowOcr → OCR确认弹窗 → 字段填入
  GtVoucherSamplingEngine dialog集成（抽凭引擎）
  借贷平衡实时校验: 顶部借方合计/贷方合计/差额 + 不平衡红色banner
  AI按钮(voucher-conclusion) + 复核按钮 + 导入导出dropdown + GtIndexChip

  Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 9.3
  Requirements: 5.2, 5.3, 5.4, 6.2, 6.5
-->
<template>
  <div class="g6-voucher-check">
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G6-15 凭证检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link :disabled="isReadonly"
          @click="handleAiConclusion">
          🤖 AI生成结论
        </el-button>
        <el-button size="small" @click="openReviewDialog('G6-15-voucher-check')">💬复核</el-button>
        <!-- 导入导出 dropdown -->
        <el-dropdown size="small" trigger="click" @command="handleImportExportCmd">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板（3区段）</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据（3区段）</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 借贷平衡汇总区 -->
    <div class="balance-summary" :class="{ unbalanced: !vc.isBalanced.value }">
      <span class="balance-item">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.debitTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.creditTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">差额：</span>
        <span class="balance-value" :class="{ 'diff-red': !vc.isBalanced.value }">
          {{ fmtNum(vc.difference.value) }}
        </span>
      </span>
      <el-tag v-if="vc.isBalanced.value" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">借贷不平衡</el-tag>
    </div>

    <!-- Tab切换 + 操作按钮 -->
    <div class="tab-toolbar">
      <el-segmented v-model="vc.activeTab.value" :options="segmentOptions" size="small" />
      <div class="tab-toolbar-right">
        <el-button size="small" type="warning" :disabled="isReadonly" @click="showSampling = !showSampling">
          ⚡ 抽凭引擎
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 新增行
        </el-button>
      </div>
    </div>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSampling" title="⚡ 抽凭引擎（科目 1503 其他债权投资）" width="720px" :close-on-click-modal="false">
      <GtVoucherSamplingEngine
        v-if="showSampling && props.wpId && props.projectId"
        account-code="1503"
        phase="final"
        default-method="random"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="currentYear"
        @filled="handleSamplingFilled"
      />
    </el-dialog>

    <!-- 主表格（虚拟滚动 100行） -->
    <el-table
      :data="displayRows"
      border
      size="small"
      :max-height="480"
      highlight-current-row
      row-key="id"
      :row-class-name="getRowClassName"
      class="voucher-table"
      @current-change="onCurrentChange"
    >
      <!-- ═══ Tab1: 凭证基础(8列) ═══ -->
      <template v-if="vc.activeTab.value === 'tab1'">
        <el-table-column label="序号" width="50" align="center" fixed>
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="日期" min-width="110">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.date" size="small"
              type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
              style="width: 100%" placeholder="选择日期" />
            <span v-else>{{ row.date }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证号" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
            <span v-else>{{ row.voucherNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" />
            <span v-else>{{ row.businessContent }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" />
            <span v-else>{{ row.counterAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="明细" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" />
            <span v-else>{{ row.detailAccount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small"
              :controls="false" class="compact-num" />
            <span v-else>{{ fmtNum(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方" min-width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small"
              :controls="false" class="compact-num" />
            <span v-else>{{ fmtNum(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="📎" width="70" align="center">
          <template #default="{ row }">
            <el-upload
              :show-file-list="false"
              accept="image/*,.pdf"
              :before-upload="(file: File) => vc.handleRowOcr(row, file)"
              :disabled="isReadonly"
            >
              <el-button size="small" link :loading="vc.ocrLoadingRowId.value === row.id" :disabled="isReadonly">
                <el-icon :class="{ 'has-file': row.attachment }"><Paperclip /></el-icon>
              </el-button>
            </el-upload>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 核对内容(8列) ═══ -->
      <template v-if="vc.activeTab.value === 'tab2'">
        <el-table-column label="序号" width="50" align="center" fixed>
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="凭证号" width="90" fixed>
          <template #default="{ row }">{{ row.voucherNo }}</template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" />
            <span v-else>{{ row.supportingDoc }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原始凭证" width="85" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkOriginal" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="授权" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkAuthorized" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="账务" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkAccounting" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="金额" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkAmount" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="分类" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkClassification" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="减值" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkImpairment" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="利息" width="70" align="center">
          <template #default="{ row }">
            <el-checkbox v-model="row.checkInterest" :disabled="isReadonly"
              @change="onCheckChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="状态" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="vc.isAllChecked(row)" type="success" size="small">全部通过</el-tag>
            <el-tag v-else type="info" size="small">待核对</el-tag>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab3: 结论(6列) ═══ -->
      <template v-if="vc.activeTab.value === 'tab3'">
        <el-table-column label="序号" width="50" align="center" fixed>
          <template #default="{ row }">{{ row.seq }}</template>
        </el-table-column>
        <el-table-column label="凭证号" width="90" fixed>
          <template #default="{ row }">{{ row.voucherNo }}</template>
        </el-table-column>
        <el-table-column label="索引" width="100">
          <template #default="{ row }">
            <GtIndexChip v-if="row.indexRef" :value="row.indexRef" />
            <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
              placeholder="索引" />
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="85" align="center">
          <template #default="{ row }">
            <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
              {{ row.isAbnormal ? '是' : '否' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="异常说明" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly && row.isAbnormal" v-model="row.abnormalNote"
              size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
            <span v-else>{{ row.abnormalNote }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险等级" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.riskLevel" size="small"
              placeholder="—" clearable style="width: 100%">
              <el-option label="高" value="高" />
              <el-option label="中" value="中" />
              <el-option label="低" value="低" />
            </el-select>
            <span v-else>{{ row.riskLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处理建议" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.suggestion" size="small" />
            <span v-else>{{ row.suggestion }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>

      <!-- 删除操作列（所有Tab共享） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm title="确认删除？" @confirm="vc.removeRow(row.id)">
            <template #reference>
              <el-icon class="delete-icon"><Delete /></el-icon>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 底部审计结论 -->
    <el-card class="conclusion-card" shadow="never">
      <div class="conclusion-header">
        <span class="conclusion-title">审计结论</span>
        <el-button size="small" type="primary" link :disabled="isReadonly"
          @click="handleAiConclusion">
          🤖 AI生成
        </el-button>
      </div>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请输入凭证检查的审计结论..."
        :disabled="isReadonly"
      />
    </el-card>

    <!-- 隐藏的导入文件 input -->
    <input ref="importFileRef" type="file" accept=".xlsx,.xls" style="display: none"
      @change="handleImportFile" />

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>凭证检查应按抽样结果逐笔记录</li>
        <li>7项核对内容全部✓后显示"全部通过"标签</li>
        <li>任一核对项未通过将自动标记为异常行（红色高亮）</li>
        <li>借贷金额合计应平衡，差额以红色显示在顶部汇总区</li>
        <li>📎附件列可上传凭证附件进行OCR识别自动填充</li>
        <li>索引号可跳转至关联底稿</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G6TabVoucherCheck.vue — G6-15 凭证检查表（100行×22列→3区段Tab）
 *
 * - el-segmented 切换 Tab1(凭证基础)/Tab2(核对内容)/Tab3(结论)
 * - Tab2: 7项checkbox，全✓→绿色badge
 * - Tab3: 任一核对✗→自动isAbnormal=true+红色高亮
 * - 顶部借贷平衡汇总 + 不平衡红色banner
 * - 虚拟滚动(100行)
 * - 动态行增删(ElMessageBox.prompt)
 * - GtIndexChip索引跳转
 * - inject openReviewDialog
 * - GtVoucherSamplingEngine 抽凭引擎 dialog
 * - 行级OCR：📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge填入
 * - 导入导出dropdown (G6-15)
 * - AI按钮 (voucher-conclusion)
 */
import { ref, computed, inject, onMounted } from 'vue'
import { Delete, Paperclip } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useG6EclVoucherCheck } from '@/composables/useG6EclVoucherCheck'
import { useG6EclImportExport } from '../../composables/useG6EclImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { VoucherCheckRow } from '../../composables/useG6EclFormData'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const wpIdRef = computed(() => props.wpId)
const projectIdRef = computed(() => props.projectId)

const vc = useG6EclVoucherCheck(
  wpIdRef,
  projectIdRef,
  computed(() => props.htmlData),
)
const conclusion = ref('')
const showSampling = ref(false)
const importFileRef = ref<HTMLInputElement | null>(null)

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const importExport = useG6EclImportExport({
  wpId: wpIdRef,
  onImported: () => {
    // 导入后重新加载数据
    if (props.htmlData?.voucherCheck) {
      vc.loadRows(props.htmlData.voucherCheck.rows || [])
    }
  },
})

function handleImportExportCmd(cmd: string) {
  if (cmd === 'export-template') {
    importExport.exportTemplate('G6-15')
  } else if (cmd === 'export-data') {
    importExport.exportData('G6-15')
  } else if (cmd === 'import-data') {
    importFileRef.value?.click()
  }
}

async function handleImportFile(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  await importExport.importData('G6-15', file)
  input.value = '' // reset for re-upload
}

// ─── 当前年份（从htmlData或默认） ────────────────────────────────────────────

const currentYear = computed(() => {
  const bsDate = props.htmlData?.bsDate as string | undefined
  if (bsDate && bsDate.length >= 4) return parseInt(bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '凭证基础', value: 'tab1' },
  { label: '核对内容', value: 'tab2' },
  { label: '结论', value: 'tab3' },
]

// ─── 显示行（虚拟滚动100行限制） ─────────────────────────────────────────────

const displayRows = computed(() => vc.rows.value.slice(0, 100))

// ─── 行同步（activeRowIndex 跨Tab保持） ─────────────────────────────────────

function onCurrentChange(row: VoucherCheckRow | null) {
  if (!row) return
  const idx = vc.rows.value.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
}

// ─── 行样式（异常行红色高亮） ───────────────────────────────────────────────

function getRowClassName({ row }: { row: VoucherCheckRow }): string {
  if (row.isAbnormal) return 'row-abnormal'
  return ''
}

// ─── 核对checkbox变更 → 自动重算异常状态 ────────────────────────────────────

function onCheckChange(row: VoucherCheckRow): void {
  vc.recalcAbnormal(row)
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddRow() {
  await vc.addRow()
}

// ─── 抽凭引擎集成 ───────────────────────────────────────────────────────────

function handleSamplingFilled(payload: { samples: Array<{
  voucherNo: string
  voucherDate?: string
  summary?: string
  counterpartAccount?: string
  accountName?: string
  debitAmount?: string
  creditAmount?: string
}> }): void {
  const mapped = payload.samples.map(s => ({
    voucherNo: s.voucherNo,
    date: s.voucherDate || '',
    businessContent: s.summary || '',
    counterAccount: s.counterpartAccount || '',
    detailAccount: s.accountName || '',
    debitAmount: s.debitAmount ? parseFloat(s.debitAmount) : 0,
    creditAmount: s.creditAmount ? parseFloat(s.creditAmount) : 0,
  }))
  vc.fillVoucherSamples(mapped)
  showSampling.value = false
  ElMessage.success(`已填入 ${mapped.length} 条抽凭样本`)
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

function handleAiConclusion() {
  ElMessage.info('AI生成凭证检查结论功能将在AI模块完成后启用')
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

onMounted(() => {
  if (props.htmlData?.voucherCheck) {
    const data = props.htmlData.voucherCheck
    vc.loadRows(data.rows || [])
    if (data.conclusion) conclusion.value = data.conclusion
  }
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    ...vc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g6-voucher-check {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 借贷平衡汇总区 */
.balance-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.balance-summary.unbalanced {
  background: #fef0f0;
  border-color: #fde2e2;
}

.balance-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.balance-label {
  color: #606266;
  font-size: 13px;
}

.balance-value {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.diff-red {
  color: #f56c6c !important;
  font-weight: 700;
}

/* Tab工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.tab-toolbar-right {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 表格 */
.voucher-table {
  font-size: 13px;
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 异常行：红色高亮 */
:deep(.row-abnormal) {
  background-color: #fef0f0 !important;
}
:deep(.row-abnormal td) {
  background-color: #fef0f0 !important;
}

/* 附件图标 */
.has-file {
  color: #67c23a !important;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 审计结论卡片 */
.conclusion-card {
  margin-top: 16px;
}

.conclusion-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.conclusion-title {
  font-weight: 600;
  font-size: 14px;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
