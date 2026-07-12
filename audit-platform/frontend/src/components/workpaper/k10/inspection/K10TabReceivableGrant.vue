<template>
  <div class="k10-tab-receivable-grant">
    <!-- ═══ 标题 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">K10-5 应收政府补助检查表</h3>
        <el-tag type="warning" effect="dark" size="small" class="account-badge">
          收款确凿性·可收回·确认时点
        </el-tag>
      </div>
      <div class="section-header-right">
        <el-button size="small" @click="handleAI">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><Check /></el-icon> 复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>应收政府补助确认检查：</strong>
        对于期末确认的应收政府补助，需逐项核查：①批文依据是否充分 ②收款权利是否确凿（有文件证明）
        ③预期可收回性判断 ④确认时点是否合理（以批文日/条件满足日为准，而非收款日）。
        存在"不合规"项需关注是否应调整。
      </div>
    </div>

    <!-- ═══ 不合规红色提示 ═══ -->
    <div v-if="checks.receivableSummary.value.nonCompliant > 0" class="non-compliant-alert">
      <el-alert
        type="error"
        :closable="false"
        show-icon
      >
        <template #title>
          存在 {{ checks.receivableSummary.value.nonCompliant }} 项不合规：{{ checks.receivableSummary.value.nonCompliantItems.join('、') }}
        </template>
      </el-alert>
    </div>

    <!-- ═══ 检查表格 ═══ -->
    <el-table
      :data="checks.receivableRows.value"
      border
      size="small"
      style="width: 100%"
      empty-text="暂无应收政府补助检查项目"
      :row-class-name="receivableRowClass"
      class="check-table"
    >
      <el-table-column prop="projectName" label="补助项目" min-width="130">
        <template #default="{ row }">
          <span class="project-name">{{ row.projectName || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column prop="documentBasis" label="批文依据" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.documentBasis"
            size="small"
            placeholder="如：X财[2025]N号"
            @change="(val: string) => checks.updateReceivableCell(row.rowKey, 'documentBasis', val)"
          />
          <span v-else>{{ row.documentBasis || '—' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="收款权利确凿性" width="130" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.receivableRight"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateReceivableCell(row.rowKey, 'receivableRight', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.receivableRight)" size="small">{{ row.receivableRight }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="预期可收回" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.expectedRecoverable"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateReceivableCell(row.rowKey, 'expectedRecoverable', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.expectedRecoverable)" size="small">{{ row.expectedRecoverable }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="确认时点" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.recognitionTiming"
            size="small"
            style="width: 100%"
            @change="(val: string) => checks.updateReceivableCell(row.rowKey, 'recognitionTiming', val)"
          >
            <el-option v-for="opt in checkOptions" :key="opt" :label="opt" :value="opt" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.recognitionTiming)" size="small">{{ row.recognitionTiming }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.amount"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => checks.updateReceivableCell(row.rowKey, 'amount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.remark"
            size="small"
            placeholder="备注"
            @change="(val: string) => checks.updateReceivableCell(row.rowKey, 'remark', val)"
          />
          <span v-else>{{ row.remark || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 📎 附件列（行级OCR） -->
      <el-table-column label="📎" width="60" align="center">
        <template #default="{ row }">
          <el-upload
            v-if="!props.isReadonly"
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            @change="(file: any) => handleOCR(row, file)"
          >
            <el-button size="small" link type="primary">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!props.isReadonly" label="" width="60" align="center">
        <template #default="{ row }">
          <el-button v-if="row.isEditable" type="danger" size="small" link @click="checks.removeRow(row.rowKey)">
            删除
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 新增按钮 ═══ -->
    <div v-if="!props.isReadonly" class="add-row-bar">
      <el-button size="small" type="primary" plain @click="handleAddRow">
        + 新增检查项目
      </el-button>
    </div>

    <!-- ═══ 统计摘要 ═══ -->
    <div class="summary-stats">
      <el-tag type="success" size="small" effect="plain">
        合规: {{ checks.receivableSummary.value.compliant }}
      </el-tag>
      <el-tag type="danger" size="small" effect="plain">
        不合规: {{ checks.receivableSummary.value.nonCompliant }}
      </el-tag>
      <el-tag type="info" size="small" effect="plain">
        不适用: {{ checks.receivableSummary.value.notApplicable }}
      </el-tag>
      <el-tag size="small" effect="plain">
        合计: {{ checks.receivableSummary.value.total }} 项
      </el-tag>
    </div>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应收政府补助确认三要素：收款权利确凿性 + 预期可收回 + 确认时点合理</li>
        <li>批文依据：政府批文/拨款通知/奖补公示等文件编号</li>
        <li>收款权利：以政府发文日为准，非收到款项日</li>
        <li>📎列可上传批文扫描件，OCR自动识别填入批文依据</li>
        <li>存在"不合规"项应关注是否需要审计调整</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K10TabReceivableGrant — K10-5 应收政府补助检查表
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 4.5
 * Requirements: 5.1-5.4
 *
 * 功能：
 * - 逐项检查应收政府补助：批文依据/收款权利确凿性/预期可收回/确认时点
 * - Dropdown选项：合规/不合规/不适用
 * - 动态行（ElMessageBox.prompt）
 * - 不合规红色高亮行
 * - 📎附件列（行级OCR识别批文）
 * - 底部统计摘要（合规/不合规/不适用计数）
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, Check } from '@element-plus/icons-vue'
import { useK10Checks, type CheckStatus } from '../../composables/useK10Checks'
import { api } from '@/services/apiProxy'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
}>()

// ─── Inject复核对话 ──────────────────────────────────────────────────────────
const openReviewDialog = inject<(sectionId: string, sectionLabel?: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const checks = useK10Checks({
  allResponses: computed(() => props.allResponses),
  projectId: computed(() => props.projectId),
  wpId: computed(() => props.wpId),
  sheetKey: 'K10-5',
  isReadonly: computed(() => props.isReadonly),
  onSave: (itemId, value) => emit('save', itemId, value),
})

// ─── Constants ───────────────────────────────────────────────────────────────

const checkOptions: CheckStatus[] = ['合规', '不合规', '不适用']

// ─── Handlers ────────────────────────────────────────────────────────────────

function fmtAmount(val: number | undefined | null): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function statusTagType(status: CheckStatus): 'success' | 'danger' | 'info' {
  if (status === '合规') return 'success'
  if (status === '不合规') return 'danger'
  return 'info'
}

/** 不合规行红色高亮 */
function receivableRowClass({ row }: { row: any }): string {
  const statuses = [row.receivableRight, row.expectedRecoverable, row.recognitionTiming]
  if (statuses.includes('不合规')) return 'non-compliant-row'
  return ''
}

/** 新增行（ElMessageBox.prompt） */
async function handleAddRow(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入补助项目名称',
      '新增应收补助检查项',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPlaceholder: '如：研发补助-XX项目...',
        inputValidator: (val: string) => {
          if (!val || !val.trim()) return '请输入项目名称'
          return true
        },
      },
    )
    checks.addReceivableRow(value.trim())
  } catch {
    // 用户取消
  }
}

/** 📎行级OCR处理 */
async function handleOCR(row: any, file: any): Promise<void> {
  if (!file?.raw) return
  const formData = new FormData()
  formData.append('file', file.raw)
  try {
    const res = await api.post('/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrText = res?.data?.text || res?.text || ''
    if (ocrText) {
      await ElMessageBox.confirm(
        `OCR识别结果：\n${ocrText.slice(0, 200)}...\n\n是否填入批文依据？`,
        'OCR识别',
        { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
      )
      checks.updateReceivableCell(row.rowKey, 'documentBasis', ocrText.trim())
      ElMessage.success('已填入批文依据')
    } else {
      ElMessage.warning('OCR未识别到内容')
    }
  } catch {
    // 用户取消或请求失败
  }
}

function handleAI(): void {
  // AI辅助钩子
}

function handleReview(): void {
  openReviewDialog?.('K10-5-receivable-grant', '应收政府补助检查')
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  checks.initFromResponses()
})
</script>

<style scoped>
.k10-tab-receivable-grant { padding: 12px; font-size: var(--wp-font-size, 13px); }

.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; flex-wrap: wrap; gap: 8px;
}
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; }
.account-badge { font-size: 11px; }

.methodology-context {
  background: linear-gradient(135deg, #fffbe6 0%, #fff8e1 100%);
  border-left: 3px solid #e6a23c;
  padding: 8px 12px; margin-bottom: 12px;
  border-radius: 0 4px 4px 0; font-size: 12px; color: #8b6914;
}
.methodology-text strong { color: #c77d00; }

.non-compliant-alert { margin-bottom: 12px; }

.check-table { font-size: var(--wp-font-size, 13px); }
.check-table :deep(.non-compliant-row) { background: #fef0f0 !important; }
.project-name { font-weight: 500; }

.add-row-bar { margin-top: 12px; }

.summary-stats {
  display: flex; gap: 8px; margin-top: 12px; flex-wrap: wrap; align-items: center;
}

.k10-details-tip {
  margin-top: 16px; padding: 8px 12px;
  background: #f5f7fa; border-radius: 4px;
  font-size: 12px; color: #606266;
}
.k10-details-tip summary { cursor: pointer; font-weight: 500; color: #409eff; }
.k10-details-tip ul { margin: 8px 0 0 0; padding-left: 20px; }
.k10-details-tip li { margin-bottom: 4px; }
</style>
