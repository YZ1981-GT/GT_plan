<script setup lang="ts">
/**
 * E1TabCertificateCount.vue — E1-9 存单盘点
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.8
 *
 * - Uses useE1CashCount composable with variant='cert'
 * - Dynamic rows: 存单编号 | 开户银行 | 存单类型 | 存入日 | 到期日 | 金额 | 利率 | 盘点结果
 *
 * Requirements: 7.3
 */
import { ref, inject, toRef, computed, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useE1CashCount, type CertCountRow } from '../composables/useE1CashCount'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: 'cert' } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  variant: 'cert',
}

const {
  rows,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CashCount(options)

// ─── 导入导出（E1-9） ─────────────────────────────────────────────────────────

const sheetCode = computed(() => 'E1-9')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

function asCert(row: any): CertCountRow { return row }

// ─── 审计说明 / 审计结论 ───────────────────────────────────────────────────────

const NOTE_KEY = 'E1-cert-audit-note'
const CONCLUSION_KEY = 'E1-cert-audit-conclusion'
const SIGNATURE_KEY = 'E1-cert-signatures'
const auditNote = ref('')
const auditConclusion = ref('')

interface SignatureState {
  cashier: string
  cashierDate: string
  accountant: string
  accountantDate: string
  supervisor: string
  supervisorDate: string
}
const signatures = ref<SignatureState>({
  cashier: '',
  cashierDate: '',
  accountant: '',
  accountantDate: '',
  supervisor: '',
  supervisorDate: '',
})

function updateSignature(field: keyof SignatureState, value: string): void {
  if (props.isReadonly) return
  signatures.value = { ...signatures.value, [field]: value || '' }
  const item = { item_id: SIGNATURE_KEY, conclusion: null, remark: JSON.stringify(signatures.value) }
  props.allResponses.set(SIGNATURE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  void props.saveImmediate([item])
}

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

function buildAiContext(): Record<string, unknown> {
  return {
    sheet: 'E1-9',
    certificateCount: rows.value,
    signatures: signatures.value,
    summary: {
      totalRows: rows.value.length,
      unseenRows: rows.value.filter(r => asCert(r).result === '未见').length,
      inconsistentRows: rows.value.filter(r => asCert(r).bookConsistent === '否').length,
      restrictedRows: rows.value.filter(r => asCert(r).pledged === '是').length,
    },
  }
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-audit-note',
    prompt: '请根据盘点过程、倒轧链、差异及证据索引生成专业、可追溯的审计说明。',
    context: buildAiContext(),
    existingContent: auditNote.value,
  })
  if (text) saveAuditNote(text)
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-audit-conclusion',
    prompt: '请根据盘点结果生成审计结论，说明账实是否相符及是否存在需调整事项。',
    context: buildAiContext(),
    existingContent: auditConclusion.value,
  })
  if (text) saveAuditConclusion(text)
}

onMounted(() => {
  const noteResp = props.allResponses.get(NOTE_KEY)
  if (noteResp?.remark) auditNote.value = noteResp.remark
  const concResp = props.allResponses.get(CONCLUSION_KEY)
  if (concResp?.remark) auditConclusion.value = concResp.remark
  const signatureResp = props.allResponses.get(SIGNATURE_KEY)
  if (signatureResp?.remark) {
    try {
      signatures.value = { ...signatures.value, ...JSON.parse(signatureResp.remark) }
    } catch { /* keep defaults for legacy/invalid JSON */ }
  }
})
</script>

<template>
  <div class="e1-tab-certificate-count">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（对照源模板 E1-9 审计过程与提示）</summary>
      <div class="guidance-content">
        <p>1. <b>监盘程序：</b>监盘开户证实书或定期存单（若无法获取，应取得质押回单等其他支持文件），编制银行存单盘点表，核对存款人、账号、期间、截止日、计息等是否与账面记录一致；关注是否抵押或限制使用。</p>
        <p>2. <b>未质押存单：</b>检查开户证实书/定期存单原件，核对存款人、金额、期限等信息。</p>
        <p>3. <b>已质押存单：</b>检查定期存单复印件、质押回单，并与相应的<b>质押合同核对</b>（存款人、金额、期限）；<b>关注质押借款是否入账</b>；对质押事项逾期的，重点<b>关注相关质权是否已被行使</b>；为他人担保的关注担保是否逾期。</p>
        <p>4. <b>已提取/兑付：</b>已到期提取或兑付的存单，核对兑付凭证、银行对账单，确认资金流向及入账。</p>
        <p>5. <b>电子存单：</b>监盘电子存单的，记录现场获取过程（有权限人员登录网银平台查询、下载等操作）。</p>
        <p>6. <b>披露：</b>所列存单存在的抵押或限制使用情况应在财务报告附注恰当披露。</p>
        <p class="calc-hint">警惕舞弊：质押套现后用所得资金虚增收入或挪作他用。核对信息如有异常需实施进一步审计程序。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：确认定期存单/开户证实书在资产负债表日确实存在且账实相符；核实是否被质押、担保或限制使用；确认存单为被审计单位所有并已恰当记录与披露。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table :data="rows" border stripe size="small" max-height="500" style="width: 100%">
          <el-table-column type="expand" width="48" fixed="left">
            <template #default="{ row }">
              <div class="certificate-detail">
                <div class="detail-title">存单详情与证据索引</div>
                <el-descriptions :column="3" border size="small">
                  <el-descriptions-item label="存款人/户名">
                    <el-input :model-value="asCert(row).depositor" :disabled="isReadonly" size="small" @change="(val: string) => updateCell(row.id, 'depositor', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="账号">
                    <el-input :model-value="asCert(row).account" :disabled="isReadonly" size="small" @change="(val: string) => updateCell(row.id, 'account', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="存款类型">
                    <el-input :model-value="asCert(row).certType" :disabled="isReadonly" size="small" @change="(val: string) => updateCell(row.id, 'certType', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="存入日">
                    <el-date-picker :model-value="asCert(row).depositDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" size="small" style="width: 100%" @update:model-value="(val: string) => updateCell(row.id, 'depositDate', val || '')" />
                  </el-descriptions-item>
                  <el-descriptions-item label="利率(%)">
                    <el-input-number :model-value="asCert(row).interestRate" :disabled="isReadonly" :controls="false" :precision="4" size="small" @change="(val: number) => updateCell(row.id, 'interestRate', val ?? 0)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="不一致原因">
                    <el-input :model-value="asCert(row).inconsistencyReason" :disabled="isReadonly" size="small" placeholder="账面不一致时说明" @change="(val: string) => updateCell(row.id, 'inconsistencyReason', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="质押/受限事项" :span="3">
                    <el-input :model-value="asCert(row).pledgeMatter" :disabled="isReadonly" size="small" placeholder="质押合同、借款入账、逾期质权等" @change="(val: string) => updateCell(row.id, 'pledgeMatter', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="存单/开户证实书索引">
                    <el-input :model-value="asCert(row).certificateIndex" :disabled="isReadonly" size="small" placeholder="如 E1-9-01" @change="(val: string) => updateCell(row.id, 'certificateIndex', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="开户证明索引">
                    <el-input :model-value="asCert(row).openingProofIndex" :disabled="isReadonly" size="small" placeholder="开户/权属证明" @change="(val: string) => updateCell(row.id, 'openingProofIndex', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="保管/质押证明索引">
                    <el-input :model-value="asCert(row).custodyProofIndex" :disabled="isReadonly" size="small" placeholder="保管、质押回单/合同" @change="(val: string) => updateCell(row.id, 'custodyProofIndex', val)" />
                  </el-descriptions-item>
                  <el-descriptions-item label="备注" :span="3">
                    <el-input :model-value="asCert(row).note" :disabled="isReadonly" size="small" @change="(val: string) => updateCell(row.id, 'note', val)" />
                  </el-descriptions-item>
                </el-descriptions>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="存单编号" width="130">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).certNo"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'certNo', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="开户银行" width="140">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).bank"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'bank', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="币种" width="90" align="center">
            <template #default="{ row }">
              <el-input
                :model-value="asCert(row).currency"
                :disabled="isReadonly"
                size="small"
                @change="(val: string) => updateCell(row.id, 'currency', val)"
              />
            </template>
          </el-table-column>
          <el-table-column label="到期日" width="130">
            <template #default="{ row }">
              <el-date-picker
                :model-value="asCert(row).maturityDate"
                :disabled="isReadonly"
                type="date"
                value-format="YYYY-MM-DD"
                size="small"
                style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'maturityDate', val || '')"
              />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="130" align="right">
            <template #default="{ row }">
              <el-input-number
                :model-value="asCert(row).amount"
                :disabled="isReadonly"
                :controls="false"
                size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)"
              />
            </template>
          </el-table-column>
          <el-table-column label="账面一致" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="asCert(row).bookConsistent"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'bookConsistent', val)"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="是否质押/受限" width="120" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="asCert(row).pledged"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'pledged', val)"
              >
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="盘点结果" width="110" align="center">
            <template #default="{ row }">
              <el-select
                :model-value="asCert(row).result"
                :disabled="isReadonly"
                size="small"
                placeholder="选择"
                @change="(val: string) => updateCell(row.id, 'result', val)"
              >
                <el-option label="已见" value="已见" />
                <el-option label="未见" value="未见" />
              </el-select>
            </template>
          </el-table-column>

          <el-table-column label="操作" width="80" align="center" fixed="right">
            <template #default="{ row }">
              <el-button
                v-if="!isReadonly"
                type="danger"
                text
                size="small"
                @click="removeRow(row.id)"
              >删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <el-card shadow="never" class="signature-card">
          <template #header><div class="card-header"><span>盘点签字确认</span></div></template>
          <div class="signature-grid">
            <div class="signature-item">
              <span class="signature-label">出纳</span>
              <el-input :model-value="signatures.cashier" :disabled="isReadonly" placeholder="姓名/签字" @change="(val: string) => updateSignature('cashier', val)" />
              <el-date-picker :model-value="signatures.cashierDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="签字日期" @update:model-value="(val: string) => updateSignature('cashierDate', val || '')" />
            </div>
            <div class="signature-item">
              <span class="signature-label">会计主管</span>
              <el-input :model-value="signatures.accountant" :disabled="isReadonly" placeholder="姓名/签字" @change="(val: string) => updateSignature('accountant', val)" />
              <el-date-picker :model-value="signatures.accountantDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="签字日期" @update:model-value="(val: string) => updateSignature('accountantDate', val || '')" />
            </div>
            <div class="signature-item">
              <span class="signature-label">监盘人</span>
              <el-input :model-value="signatures.supervisor" :disabled="isReadonly" placeholder="姓名/签字" @change="(val: string) => updateSignature('supervisor', val)" />
              <el-date-picker :model-value="signatures.supervisorDate" :disabled="isReadonly" type="date" value-format="YYYY-MM-DD" placeholder="签字日期" @update:model-value="(val: string) => updateSignature('supervisorDate', val || '')" />
            </div>
          </div>
        </el-card>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计说明</span>
              <el-button size="small" type="primary" plain :loading="isGenerating('e1-audit-note')" :disabled="isReadonly" @click="generateAuditNote">🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            placeholder="填写审计说明：可概述监盘程序执行情况与结果；未质押/已质押存单的检查情况（开户证实书、质押回单、质押合同核对、质押借款入账、逾期质权行使）；账实相符情况；拟调整事项及影响；审计范围受限情况等。"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>审计结论</span>
              <el-button size="small" type="primary" plain :loading="isGenerating('e1-audit-conclusion')" :disabled="isReadonly" @click="generateAuditConclusion">🤖 AI辅助</el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、未见异常，银行存单存在且账实相符，抵押/限制使用情况已恰当披露。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>
  </div>
</template>

<style scoped>
.e1-tab-certificate-count {
  padding: 12px 0;
}
.e1-tab-certificate-count :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-certificate-count :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.calc-hint {
  margin-top: 6px;
  color: #e6a23c;
  font-style: italic;
}
.certificate-detail {
  padding: 10px 16px 14px 48px;
  background: #fafafa;
}
.detail-title {
  margin-bottom: 8px;
  color: #303133;
  font-weight: 600;
}
.signature-card {
  margin-top: 16px;
}
.signature-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(260px, 1fr));
  gap: 12px;
}
.signature-item {
  display: grid;
  grid-template-columns: 72px minmax(100px, 1fr) 145px;
  gap: 8px;
  align-items: center;
}
.signature-label {
  color: #606266;
  font-weight: 500;
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}

/* 审计说明 / 审计结论 */
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
