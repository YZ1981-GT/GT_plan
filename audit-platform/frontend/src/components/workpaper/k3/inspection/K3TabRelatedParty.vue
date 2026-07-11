<!-- K3TabRelatedParty.vue — K3-6 关联方及交易检查表 | Task 4.5 | Req 6.1-6.3 -->
<template>
  <div class="k3-tab-related-party">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K3-6关联方及交易检查表用于核查其他应付款中涉及关联方的款项。重点关注：
        ①关联方识别是否完整（8类关联关系）②往来金额是否公允（与市场价格/同类交易比较）
        ③是否按CAS 36充分披露 ④是否存在资金占用（无息长期挂账无商业理由）。
        行级抽凭+OCR识别自动填充审计证据。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K3-6 关联方及交易检查</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('related-party-eval')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-button size="small" @click="handleReview('K3-6-related')">💬 复核</el-button>
      </div>
    </div>

    <!-- 主表格 -->
    <el-table
      :data="relatedPartyRows"
      border
      size="small"
      :max-height="520"
      class="related-party-table"
      :row-style="tableRowStyle"
    >
      <el-table-column label="关联方名称" min-width="130" fixed>
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.counterparty" size="small" placeholder="关联方名称"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.counterparty || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="关联关系" min-width="140">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.relationship" size="small" clearable placeholder="请选择"
            @change="handleRowChange(row)">
            <el-option label="控股股东" value="控股股东" />
            <el-option label="实际控制人" value="实际控制人" />
            <el-option label="控股子公司" value="控股子公司" />
            <el-option label="合营企业" value="合营企业" />
            <el-option label="联营企业" value="联营企业" />
            <el-option label="关键管理人员" value="关键管理人员" />
            <el-option label="近亲属控制企业" value="近亲属控制企业" />
            <el-option label="其他关联方" value="其他关联方" />
          </el-select>
          <span v-else>{{ row.relationship || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="往来金额" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.amount" size="small"
            :controls="false" class="amount-input"
            @change="handleRowChange(row)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否公允" min-width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.isFair" size="small"
            @change="handleRowChange(row)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="待评估" value="待评估" />
          </el-select>
          <el-tag v-else :type="fairTagType(row.isFair)" size="small">{{ row.isFair }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="是否披露" min-width="100" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.isDisclosed" size="small"
            @change="handleRowChange(row)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag v-else :type="disclosedTagType(row.isDisclosed)" size="small">{{ row.isDisclosed }}</el-tag>
        </template>
      </el-table-column>

      <el-table-column label="资金占用" min-width="90" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.capitalOccupation" size="small"
            @change="handleRowChange(row)">
            <el-option label="是" value="是" />
            <el-option label="否" value="否" />
          </el-select>
          <el-tag v-else :type="row.capitalOccupation === '是' ? 'danger' : 'success'" size="small">
            {{ row.capitalOccupation }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="结论" min-width="110" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.conclusion" size="small" clearable placeholder="请选择"
            @change="handleRowChange(row)">
            <el-option label="合规" value="合规" />
            <el-option label="不合规" value="不合规" />
            <el-option label="不适用" value="不适用" />
          </el-select>
          <el-tag v-else :type="conclusionTagType(row.conclusion)" size="small">
            {{ row.conclusion || '未判定' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="备注" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.remark" size="small" placeholder="备注"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.remark || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 抽凭 + OCR列 -->
      <el-table-column label="📎" width="90" align="center">
        <template #default="{ row }">
          <el-button size="small" link @click="handleVoucherSampling(row)" title="行级抽凭">📋</el-button>
          <el-upload
            :show-file-list="false"
            :before-upload="(file: any) => handleOcrUpload(row, file)"
            accept=".pdf,.png,.jpg,.jpeg"
            style="display:inline-block"
          >
            <el-button size="small" link title="OCR识别">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 不合规红色摘要 -->
    <el-alert
      v-if="nonComplianceCount > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-top: 12px"
    >
      <template #title>
        ⚠️ 存在 <b>{{ nonComplianceCount }}</b> 项不合规关联方交易，请重点关注并评估是否需调整
      </template>
    </el-alert>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>关联关系8类：控股股东/实际控制人/控股子公司/合营/联营/关键管理人员/近亲属控制/其他</li>
        <li>公允性判断：与同类非关联方交易对比、独立评估报告、市场价格参照</li>
        <li>资金占用嫌疑：大额无息+无明确商业理由+长期不清→报告管理层</li>
        <li>CAS 36披露：关联方关系+交易类型+金额+定价政策+余额+坏账准备</li>
        <li>📎列：行级抽凭(GtVoucherSamplingEngine)+OCR识别(contract-ocr自动填充)</li>
      </ul>
    </details>

    <!-- 抽凭引擎 dialog -->
    <el-dialog v-model="showSamplingDialog" title="⚡ 抽凭引擎（科目 2241 其他应付款）" width="720px" :close-on-click-modal="false" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog && props.wpId && props.projectId"
        :project-id="props.projectId"
        :wp-id="props.wpId"
        account-code="2241"
        @filled="onSampleFilled"
      />
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabRelatedParty.vue — K3-6 关联方及交易检查表
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.5
 * Requirements: 6.1-6.3, 6.5
 */
import { computed, inject, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK3Checks, type K3RelatedPartyRow, type ComplianceState } from '../../composables/useK3Checks'
import GtVoucherSamplingEngine from '../../../voucher-sampling/GtVoucherSamplingEngine.vue'
import http from '@/utils/http'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

function saveResponseFn(itemId: string, payload: any) {
  props.allResponses.set(itemId, { item_id: itemId, ...payload })
  emit('save', itemId, payload)
}

const {
  relatedPartyRows,
  updateRelatedPartyConclusion,
  saveAll,
} = useK3Checks({ allResponses: allResponsesRef as any, saveResponse: saveResponseFn })

// ─── Computed ────────────────────────────────────────────────────────────────

const nonComplianceCount = computed(() =>
  relatedPartyRows.value.filter(r => r.conclusion === '不合规').length
)

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入关联方名称',
      '新增关联方',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '关联方名称' }
    )
    if (!value?.trim()) { ElMessage.warning('名称不能为空'); return }
    relatedPartyRows.value.push({
      rowId: `rp-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: relatedPartyRows.value.length + 1,
      counterparty: value.trim(),
      relationship: '',
      amount: 0,
      isFair: '待评估',
      isDisclosed: '不适用',
      capitalOccupation: '否',
      conclusion: null,
      remark: '',
    })
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string) {
  relatedPartyRows.value = relatedPartyRows.value.filter(r => r.rowId !== rowId)
  relatedPartyRows.value.forEach((r, i) => { r.seqNo = i + 1 })
  persistRows()
}

function handleRowChange(_row: K3RelatedPartyRow) {
  persistRows()
}

function persistRows() {
  saveAll()
}

// ─── Voucher Sampling ────────────────────────────────────────────────────────

const showSamplingDialog = ref(false)
const currentSamplingRow = ref<K3RelatedPartyRow | null>(null)

function handleVoucherSampling(row: K3RelatedPartyRow) {
  currentSamplingRow.value = row
  showSamplingDialog.value = true
}

function onSampleFilled(payload: any): void {
  if (currentSamplingRow.value && payload?.voucherNo) {
    currentSamplingRow.value.remark = currentSamplingRow.value.remark
      ? `${currentSamplingRow.value.remark} [凭证:${payload.voucherNo}]`
      : `[凭证:${payload.voucherNo}]`
    persistRows()
  }
  showSamplingDialog.value = false
}

// ─── OCR ─────────────────────────────────────────────────────────────────────

async function handleOcrUpload(row: K3RelatedPartyRow, file: File): Promise<boolean> {
  try {
    const formData = new FormData()
    formData.append('file', file)

    const res = await http.post('/api/d4/contract-ocr', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const ocrResult = res.data?.data?.text || res.data?.text || ''

    if (!ocrResult) {
      ElMessage.warning('OCR未识别出内容')
      return false
    }

    await ElMessageBox.confirm(
      `OCR识别结果：\n\n${ocrResult.slice(0, 500)}${ocrResult.length > 500 ? '...' : ''}`,
      'OCR结果确认',
      { confirmButtonText: '填入备注', cancelButtonText: '取消', type: 'info' },
    )

    // 合并OCR结果到备注
    row.remark = row.remark ? `${row.remark}\n[OCR] ${ocrResult}` : `[OCR] ${ocrResult}`
    persistRows()
    ElMessage.success('OCR内容已填入')
  } catch {
    /* cancelled or error */
  }
  return false // prevent default upload behavior
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function tableRowStyle({ row }: { row: K3RelatedPartyRow }): Record<string, string> {
  if (row.conclusion === '不合规') return { 'background-color': '#fef2f2' }
  if (row.capitalOccupation === '是') return { 'background-color': '#fff7ed' }
  return {}
}

function fairTagType(val: string): 'success' | 'danger' | 'warning' | 'info' {
  if (val === '是') return 'success'
  if (val === '否') return 'danger'
  return 'warning'
}

function disclosedTagType(val: string): 'success' | 'danger' | 'info' {
  if (val === '是') return 'success'
  if (val === '否') return 'danger'
  return 'info'
}

function conclusionTagType(val: string | null): 'success' | 'danger' | 'info' | 'warning' {
  if (val === '合规') return 'success'
  if (val === '不合规') return 'danger'
  if (val === '不适用') return 'info'
  return 'warning'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiGenerate(section: string) {
  console.log('[K3-6] AI generate:', section)
}

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k3-tab-related-party { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 4px solid var(--el-color-warning); background: #fffbeb; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.related-party-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
