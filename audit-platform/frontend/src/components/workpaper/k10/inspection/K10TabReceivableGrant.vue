<template>
  <div class="k10-tab-receivable-grant">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>存在与权利：</b>应收政府补助真实存在、被审计单位有权收取（已满足确认条件）；</li>
        <li><b>完整性与计价：</b>符合确认条件的应收补助均已确认、金额以批文/文件为据计量恰当。</li>
      </ol>
    </el-alert>

    <!-- ═══ 标题 + 按钮 ═══ -->
    <div class="section-header">
      <div class="section-header-left">
        <h3 class="section-title">K10-5 应收政府补助检查表</h3>
        <el-tag type="warning" effect="dark" size="small" class="account-badge">
          收款确凿性·可收回·确认时点
        </el-tag>
      </div>
      <div class="section-header-right">
        <GtReviewTrigger section-id="K10-5-receivable-grant" label="💬 复核" />
      </div>
    </div>

    <!-- ═══ 跨底稿引用（期后收款核对至货币资金/银行） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="wp:K10-1" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:K10-4" :context-project-id="props.projectId" />
      <GtIndexChip value="wp:E1" :context-project-id="props.projectId" />
      <span class="cross-ref-hint">期后收款可核对至 E1 货币资金/银行回单</span>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <div class="methodology-text">
        <strong>应收政府补助确认检查：</strong>
        对于期末确认的应收政府补助，需逐项核查：①批文依据是否充分 ②收款权利是否确凿（有文件证明）
        ③预期可收回性判断 ④确认时点是否合理（以批文日/条件满足日为准，而非收款日）。
        <strong>并核对期后银行回单/收款凭证</strong>验证实际收款情况（可追溯至 E1 货币资金），
        期后已收回可佐证收款权利确凿；长期未收回需关注可收回性。存在"不合规"项需关注是否应调整。
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

      <el-table-column label="应收金额" width="120" align="right">
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

      <!-- 期后收款（核对银行回单/收款凭证，佐证可收回性） -->
      <el-table-column label="期后收款" width="120" align="right">
        <template #header>
          <span title="核对期后银行回单/收款凭证的实际收款金额（可追溯至 E1）">期后收款</span>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly && row.isEditable"
            :model-value="row.postCollectionAmount"
            :controls="false"
            size="small"
            style="width: 100%"
            @change="(val: number | undefined) => checks.updateReceivableCell(row.rowKey, 'postCollectionAmount', val ?? 0)"
          />
          <span v-else>{{ fmtAmount(row.postCollectionAmount) }}</span>
        </template>
      </el-table-column>

      <!-- 期后收款状态（派生） -->
      <el-table-column label="收款状态" width="100" align="center">
        <template #default="{ row }">
          <el-tag :type="collectionTagType(collectionStatus(row))" size="small" effect="plain">{{ collectionStatus(row) }}</el-tag>
        </template>
      </el-table-column>

      <!-- 综合结论（派生） -->
      <el-table-column label="综合结论" width="100" align="center">
        <template #header>
          <span title="由 收款权利/预期可收回/确认时点 三项派生">综合结论</span>
        </template>
        <template #default="{ row }">
          <el-tag :type="statusTagType(overallStatus(row))" size="small">{{ overallStatus(row) }}</el-tag>
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

    <!-- ═══ 检查说明与结论（AI辅助） ═══ -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="note-card-header">
          <span>检查说明与结论</span>
          <el-button size="small" type="primary" text :loading="aiLoading" @click="handleAI">
            <el-icon><MagicStick /></el-icon> AI辅助
          </el-button>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="props.isReadonly"
        placeholder="填写应收政府补助检查说明与结论（批文依据、收款权利、可收回性、确认时点合理性）..."
        @change="handleNoteSave"
      />
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k10-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>应收政府补助确认三要素：收款权利确凿性 + 预期可收回 + 确认时点合理</li>
        <li>批文依据：政府批文/拨款通知/奖补公示等文件编号</li>
        <li>收款权利：以政府发文日为准，非收到款项日</li>
        <li>期后收款：填入期后实际收到金额（核对银行回单/收款凭证，可追溯 E1），系统据此派生"收款状态"（已收回/部分收回/未收回）佐证可收回性</li>
        <li>综合结论由 收款权利/预期可收回/确认时点 三项自动派生（任一不合规→不合规）</li>
        <li>📎列可上传批文扫描件，OCR自动识别填入批文依据</li>
        <li>存在"不合规"项或"未收回"应关注是否需要审计调整</li>
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
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import {
  useK10Checks, deriveReceivableStatus, deriveCollectionStatus,
  type CheckStatus, type CollectionStatus,
} from '../../composables/useK10Checks'
import { api } from '@/services/apiProxy'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'

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

/** 综合结论（由三项子判断派生） */
function overallStatus(row: any): CheckStatus {
  return deriveReceivableStatus(row.receivableRight, row.expectedRecoverable, row.recognitionTiming)
}

/** 期后收款状态 + tag 颜色 */
function collectionStatus(row: any): CollectionStatus {
  return deriveCollectionStatus(Number(row.amount || 0), Number(row.postCollectionAmount || 0))
}
function collectionTagType(s: CollectionStatus): 'success' | 'warning' | 'info' {
  if (s === '已收回') return 'success'
  if (s === '部分收回') return 'warning'
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

// ─── 检查说明 + AI ───────────────────────────────────────────────────────────
const noteText = ref('')
const aiLoading = ref(false)

function loadNote(): void {
  const saved = props.allResponses.get('K10-5-note')
  if (saved) noteText.value = (saved.remark ?? saved.conclusion ?? '') as string
}

function handleNoteSave(): void {
  emit('save', 'K10-5-note', { remark: noteText.value })
}

async function handleAI(): Promise<void> {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const s = checks.receivableSummary.value
    const ctx = {
      合规项: String(s.compliant),
      不合规项: String(s.nonCompliant),
      不适用项: String(s.notApplicable),
      合计项: String(s.total),
      不合规明细: (s.nonCompliantItems || []).join('、') || '无',
    }
    const res = await api.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'K10-5-note',
      prompt: '为K10应收政府补助检查表生成检查说明与结论：批文依据充分性、收款权利确凿性、预期可收回性、确认时点合理性，以及不合规项是否需审计调整。',
      existingContent: noteText.value,
      context: ctx,
    })
    const content = (res?.data?.content ?? res?.content ?? '') as string
    if (content) { noteText.value = content; handleNoteSave(); ElMessage.success('AI生成完成') }
    else ElMessage.warning('AI未返回内容，请手动填写')
  } catch { ElMessage.warning('AI生成失败，请手动填写') } finally { aiLoading.value = false }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => {
  checks.initFromResponses()
  loadNote()
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

.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }
.cross-ref-hint { color: #909399; font-size: 12px; }

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

.note-card { margin-top: 16px; }
.note-card-header { display: flex; justify-content: space-between; align-items: center; }
.note-card-header span { font-weight: 600; font-size: 14px; }
</style>
