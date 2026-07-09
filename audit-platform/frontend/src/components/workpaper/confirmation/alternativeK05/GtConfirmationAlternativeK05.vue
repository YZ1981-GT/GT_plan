<template>
  <div class="gt-confirmation-alternative-k05" data-testid="k0-alternative-k05">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-k05__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-k05-v1 -->
    <template v-else>
      <!-- 工具栏 -->
      <div class="gt-confirmation-alternative-k05__toolbar">
        <span class="gt-confirmation-alternative-k05__title">K0-5 其他应收款替代程序</span>
        <div class="gt-confirmation-alternative-k05__toolbar-right">
          <GtIndexChip value="K0-1" :context-project-id="projectId" />
          <!-- 导入导出下拉 -->
          <el-dropdown trigger="click" @command="handleIeCommand">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
                <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
                <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" @click="versionToolbar.openVersionHistory()">版本历史</el-button>
          <GtReviewTrigger section-id="K0-5-alternative" label="复核" />
        </div>
      </div>

      <!-- 编制提示 -->
      <details class="gt-confirmation-alternative-k05__tips">
        <summary>编制提示</summary>
        <p>对回函可能性不高的、余额重大的被询证单位，发函同时执行替代程序：期后收款+余额支持性证据+本期发生额+往来对账。</p>
      </details>

      <!-- 余额汇总区 -->
      <el-card shadow="never" class="gt-confirmation-alternative-k05__summary-card">
        <template #header><span style="font-size:13px;font-weight:600">余额汇总与检查比例</span></template>
        <el-table :data="balanceSummaryRows" size="small" border style="font-size:13px">
          <el-table-column prop="label" label="函证项目" width="120" />
          <el-table-column prop="opening" label="年初余额" width="120" align="right" />
          <el-table-column prop="debit" label="借方发生额" width="120" align="right" />
          <el-table-column prop="credit" label="贷方发生额" width="120" align="right" />
          <el-table-column prop="closing" label="期末余额" width="120" align="right" />
          <el-table-column prop="current" label="本期发生额" width="120" align="right" />
          <el-table-column prop="postRatio" label="期后收款检查比例" width="130" align="right" />
          <el-table-column prop="reconcileRatio" label="往来对账比例" width="120" align="right" />
        </el-table>
      </el-card>

      <!-- 多公司 Master-Detail: el-tabs -->
      <el-tabs v-model="activeTab" type="card" @tab-click="handleTabClick">
        <el-tab-pane
          v-for="company in data.companies.value"
          :key="company._company_id"
          :label="company.entity_name || '未命名'"
          :name="company._company_id"
        />
        <el-tab-pane name="__add__" :closable="false">
          <template #label><span style="color:var(--el-color-primary)">+ 新增公司</span></template>
        </el-tab-pane>
      </el-tabs>

      <!-- Detail: 选中公司 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-k05__detail">
          <!-- 抽样参数区 -->
          <div class="detail-section">
            <div class="detail-section__header">一、抽样参数</div>
            <el-form :model="selectedCompany.sampling || {}" label-width="100px" size="small" :disabled="readonly">
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="测试范围">
                    <el-input v-model="selectedCompany.sampling!.test_scope" type="textarea" :rows="2"
                      placeholder="其他应收款借方发生额全部凭证共XX笔金额XX" @change="markDirty" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="特定样本">
                    <el-input v-model="selectedCompany.sampling!.specific_samples" type="textarea" :rows="2"
                      placeholder="XX金额以上大额、关联方款项全部测试，共XX笔" @change="markDirty" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样总体">
                    <el-input v-model="selectedCompany.sampling!.sampling_population" type="textarea" :rows="2"
                      placeholder="测试总体扣除特定样本，共XX笔、金额XX" @change="markDirty" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="确定样本量">
                    <el-input v-model="selectedCompany.sampling!.sample_size" type="textarea" :rows="2"
                      placeholder="抽取XX笔" @change="markDirty" />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样方法">
                    <el-input v-model="selectedCompany.sampling!.sampling_method" type="textarea" :rows="2"
                      placeholder="随机选样/系统选样/货币单元抽样/随意选样" @change="markDirty" />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="抽样过程">
                    <el-input v-model="selectedCompany.sampling!.sampling_process" type="textarea" :rows="2"
                      placeholder="使用XX抽样工具选择XX数量占比XX%的样本" @change="markDirty" />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- 4区块检查表 -->
          <div class="detail-section">
            <div class="detail-section__header">二、检查过程记录</div>
            <CheckBlock
              v-for="bt in blockTypes"
              :key="bt"
              :config="blockConfigs[bt]"
              :rows="getBlockRows(selectedCompany, bt)"
              :totals="data.getBlockTotal(selectedCompany, bt)"
              :readonly="readonly"
              :enable-ocr="true"
              :ocr-loading-row-id="ocrLoadingRowId"
              :formula-fn="bt === 'block4' ? reconcileDiffFn : undefined"
              @add-row="data.addBlockRow(selectedCompany._company_id!, bt)"
              @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, bt, rowId)"
              @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, bt, rowId, field, val)"
              @ocr-upload="(rowId: string, file: File) => handleRowOcr(bt, rowId, file)"
            />
          </div>

          <!-- 审计说明与结论 -->
          <div class="detail-section">
            <div class="detail-section__header">
              <span>三、审计说明与结论</span>
              <el-button v-if="!readonly" type="primary" size="small" plain :loading="aiLoading"
                style="margin-left:auto" @click="handleAiFill">AI 辅助生成</el-button>
            </div>
            <el-card shadow="never" class="conclusion-card">
              <el-form :model="selectedCompany.conclusion || {}" label-width="80px" size="small" :disabled="readonly">
                <el-form-item label="审计说明">
                  <div style="display:flex;align-items:flex-start;gap:4px;width:100%">
                    <el-input v-model="selectedCompany.conclusion!.audit_note" type="textarea" :rows="3"
                      placeholder="概述替代程序执行情况、结果、拟调整事项及其影响" @change="markDirty" />
                  </div>
                </el-form-item>
                <el-form-item label="审计结论">
                  <div style="display:flex;align-items:flex-start;gap:4px;width:100%">
                    <el-input v-model="selectedCompany.conclusion!.conclusion_text" type="textarea" :rows="3"
                      placeholder="替代程序结论：余额是否得到充分支持" @change="markDirty" />
                  </div>
                </el-form-item>
              </el-form>
            </el-card>
          </div>
        </div>
      </template>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- 版本链抽屉 -->
    <GtWpVersionTrail v-if="wpId" ref="versionTrailRef" :workpaper-id="wpId" :project-id="projectId || ''" />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import type { ConfirmationUpdatedPayload } from '@/utils/eventBus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import useAlternativeK05Data from '../k0-confirmation/composables/useAlternativeK05Data'
import { useK0FormulaEngine } from '../k0-confirmation/composables/useK0FormulaEngine'
import type { AlternativeCompany, BlockType, CheckRow } from '../alternativeD05/alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS_K05 } from './blockColumnConfigsK05'
import { useWorkpaperVersionToolbar } from '../../composables/useWorkpaperVersionToolbar'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

// Shared D0-5 components
import CheckBlock from '../alternativeD05/CheckBlock.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../../version-trail/GtWpVersionTrail.vue'))
const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const emit = defineEmits<{ (e: 'save', payload: any): void }>()

const readonly = computed(() => props.readonly ?? false)
const wpIdRef = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')
const prefs = useDisplayPrefsStore()
const { calcReconcileDiff, parseNum } = useK0FormulaEngine()

const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar

// ─── selfLoad 兜底 ────────────────────────────────────────────────────────
const selfLoadedData = ref<any>(null)
const htmlDataRef = computed(() => props.htmlData ?? selfLoadedData.value)
const isNewFormat = computed(() => htmlDataRef.value?._format === 'alternative-k05-v1')

onMounted(async () => {
  if (props.htmlData == null && props.wpId) {
    try {
      const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
      for (const sheet of sheets) {
        const hd = sheet?.html_data ?? sheet?.htmlData
        if (hd?._format === 'alternative-k05-v1') { selfLoadedData.value = hd; break }
      }
    } catch (e) { console.warn('[GtConfirmationAlternativeK05] selfLoad failed:', e) }
  }
})

// ─── Data composable ──────────────────────────────────────────────────────
const data = useAlternativeK05Data({
  wpId: props.wpId,
  projectId: props.projectId,
  htmlData: () => htmlDataRef.value,
  readonly: readonly.value,
})

// ─── Block configs ────────────────────────────────────────────────────────
const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_K05

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

/** 区块④对账差异公式列 */
function reconcileDiffFn(row: CheckRow): number {
  return calcReconcileDiff(parseNum(row.self_balance), parseNum(row.other_balance))
}

// ─── 余额汇总 Rows ───────────────────────────────────────────────────────
const balanceSummaryRows = computed(() => {
  const s = data.balanceSummary.value
  return [{
    label: s.investmentType,
    opening: prefs.fmt(s.openingBalance),
    debit: prefs.fmt(s.debitAmount),
    credit: prefs.fmt(s.creditAmount),
    closing: prefs.fmt(s.closingBalance),
    current: prefs.fmt(s.currentAmount),
    postRatio: s.postCheckRatio > 0 ? `${s.postCheckRatio.toFixed(1)}%` : '—',
    reconcileRatio: s.reconcileRatio > 0 ? `${s.reconcileRatio.toFixed(1)}%` : '—',
  }]
})

// ─── Tab: 多公司 Master-Detail ────────────────────────────────────────────
const activeTab = ref<string>(data.companies.value[0]?._company_id ?? '')

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!activeTab.value || activeTab.value === '__add__') return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === activeTab.value)
})

watch(() => data.companies.value, (cs) => {
  if (cs.length && !activeTab.value) activeTab.value = cs[0]._company_id!
}, { immediate: true })

async function handleTabClick(tab: any) {
  const name = tab.paneName ?? tab.props?.name
  if (name === '__add__') {
    try {
      const { value: companyName } = await ElMessageBox.prompt('请输入公司名称', '新增公司', {
        confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '被询证单位名称',
      })
      if (!companyName?.trim()) { ElMessage.warning('公司名称不能为空'); return }
      const company = data.addCompany({ entity_name: companyName.trim() })
      activeTab.value = company._company_id!
    } catch { /* 用户取消 */ }
  }
}

// ─── EventBus: K0-1→K0-5 联动 ────────────────────────────────────────────
function onConfirmationUpdated(payload: ConfirmationUpdatedPayload) {
  if (payload.projectId !== props.projectId) return
  if (!payload.wpCode.startsWith('K0-')) return
  if (payload.wpId === props.wpId) return
  if (payload.wpCode === 'K0-1') {
    ElMessage.info({ message: 'K0-1 函证结果汇总已更新，可通过"导入K0-1"刷新未回函公司列表', duration: 4000 })
  }
}
onMounted(() => { eventBus.on('confirmation:updated', onConfirmationUpdated) })
onUnmounted(() => { eventBus.off('confirmation:updated', onConfirmationUpdated) })

// ─── 行级 OCR ─────────────────────────────────────────────────────────────
const ocrLoadingRowId = ref<string | null>(null)

const OCR_FIELD_MAP: Record<BlockType, Record<string, string>> = {
  block1: { date: 'voucher_date', voucher_no: 'voucher_no', amount: 'voucher_amount', 金额: 'receipt_amount', 收款方: 'receipt_payer', 银行回单: 'receipt_date_no' },
  block2: { date: 'voucher_date', voucher_no: 'voucher_no', amount: 'voucher_amount', 协议编号: 'agreement_no', 对方单位: 'agreement_party', 协议金额: 'agreement_amount' },
  block3: { date: 'voucher_date', voucher_no: 'voucher_no', amount: 'voucher_amount', 单据编号: 'doc_date_no', 事由: 'doc_reason', 审批人: 'approval_person', 审批金额: 'approval_amount' },
  block4: { date: 'voucher_date', voucher_no: 'voucher_no', amount: 'voucher_amount', 对方余额: 'other_balance', 本方余额: 'self_balance', 协议编号: 'agreement_no', 签订日期: 'agreement_date' },
}

async function handleRowOcr(blockType: BlockType, rowId: string, file: File) {
  if (!selectedCompany.value || !props.wpId) return
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`, formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) { ElMessage.info('OCR完成，未识别到可填充字段'); return }
    const map = OCR_FIELD_MAP[blockType]
    const patch: Record<string, any> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = map[ocrKey]
      if (target && val != null && String(val).trim() !== '') patch[target] = val
    }
    if (!Object.keys(patch).length) { ElMessage.info('OCR完成，识别字段无法匹配本区块'); return }
    const preview = Object.entries(patch).map(([k, v]) => `${k}: ${v}`).join('，')
    await ElMessageBox.confirm(`识别到信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', { confirmButtonText: '填入', cancelButtonText: '取消' })
    for (const [field, val] of Object.entries(patch)) {
      data.updateBlockField(selectedCompany.value._company_id!, blockType, rowId, field, val)
    }
    ElMessage.success('已填入识别结果')
  } catch (e) { if (e !== 'cancel') ElMessage.warning('OCR识别失败') }
  finally { ocrLoadingRowId.value = null }
}

// ─── AI 辅助填充 ──────────────────────────────────────────────────────────
const aiLoading = ref(false)

async function handleAiFill() {
  if (!selectedCompany.value || !props.wpId) return
  aiLoading.value = true
  try {
    const company = selectedCompany.value
    const context = {
      entity_name: company.entity_name,
      balance: company.balance,
      block_totals: blockTypes.map(bt => ({ block: bt, totals: data.getBlockTotal(company, bt) })),
      has_abnormal: data.hasAbnormal(company),
      completion: data.getCompletionStatus(company),
    }
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'alternative-audit-note',
      prompt: '根据K0-5其他应收款替代程序检查记录，生成审计说明和审计结论',
      context: JSON.stringify(context),
      existingContent: company.conclusion?.audit_note || '',
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (!company.conclusion) company.conclusion = {}
      company.conclusion.audit_note = text
      data.isDirty.value = true
      ElMessage.success('AI已生成审计说明（请根据实际情况修改）')
    }
  } catch { ElMessage.warning('AI生成失败，请稍后重试') }
  finally { aiLoading.value = false }
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────
const importFileInput = ref<HTMLInputElement | null>(null)

function handleIeCommand(command: string) {
  switch (command) {
    case 'export-template': handleExportTemplate(); break
    case 'export-data': handleExportData(); break
    case 'import-data': importFileInput.value?.click(); break
  }
}

async function handleExportTemplate() {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k0/export-template`, null, { params: { sheet: 'K0-5' }, responseType: 'blob' })
    downloadBlob(res.data, 'K0-5其他应收款替代程序_模板.xlsx')
    ElMessage.success('模板已导出')
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  if (!data.companies.value.length) { ElMessage.warning('暂无数据可导出'); return }
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k0/export-data`, null, { params: { sheet: 'K0-5' }, responseType: 'blob' })
    downloadBlob(res.data, 'K0-5其他应收款替代程序_数据.xlsx')
    ElMessage.success('数据已导出')
  } catch { ElMessage.error('导出失败') }
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(`/api/workpapers/${props.wpId}/k0/import-data`, formData, {
      params: { sheet: 'K0-5' }, headers: { 'Content-Type': 'multipart/form-data' },
    })
    const count = res.data?.data?.rowCount ?? res.data?.rowCount ?? 0
    ElMessage.success(`成功导入 ${count} 条数据`)
    // 重载数据
    if (props.wpId) {
      const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
      for (const sheet of sheets) {
        const hd = sheet?.html_data ?? sheet?.htmlData
        if (hd?._format === 'alternative-k05-v1') { selfLoadedData.value = hd; break }
      }
    }
  } catch (e: any) { ElMessage.error('导入失败：' + (e?.response?.data?.message || e?.message || '未知错误')) }
  finally { if (importFileInput.value) importFileInput.value.value = '' }
}

function downloadBlob(data: Blob, filename: string) {
  const url = URL.createObjectURL(data)
  const a = document.createElement('a')
  a.href = url; a.download = filename; a.click()
  URL.revokeObjectURL(url)
}

// ─── 保存 ─────────────────────────────────────────────────────────────────
function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  versionToolbar.scheduleAutoSnapshot()
  if (props.projectId) {
    eventBus.emit('confirmation:updated', { projectId: props.projectId, wpCode: 'K0-5', wpId: props.wpId, timestamp: Date.now() })
  }
}

function markDirty() { data.isDirty.value = true }

defineExpose({ handleSave, handleExportTemplate, handleExportData, handleImport: () => importFileInput.value?.click() })
</script>

<style scoped>
.gt-confirmation-alternative-k05 { padding: 8px 0; font-size: 13px; }
.gt-confirmation-alternative-k05__toolbar { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.gt-confirmation-alternative-k05__title { font-size: 15px; font-weight: 600; }
.gt-confirmation-alternative-k05__toolbar-right { display: flex; align-items: center; gap: 8px; }
.gt-confirmation-alternative-k05__legacy-notice { margin-bottom: 12px; }
.gt-confirmation-alternative-k05__tips { margin-bottom: 12px; font-size: 12px; color: #606266; border: 1px solid var(--el-border-color-lighter); border-radius: 4px; padding: 8px 12px; }
.gt-confirmation-alternative-k05__tips summary { cursor: pointer; font-weight: 500; }
.gt-confirmation-alternative-k05__summary-card { margin-bottom: 16px; }
.gt-confirmation-alternative-k05__detail { margin-top: 12px; }
.detail-section { margin-bottom: 16px; }
.detail-section__header { font-size: 13px; font-weight: 600; margin-bottom: 8px; padding: 4px 8px; background: var(--el-fill-color-light); border-radius: 3px; display: flex; align-items: center; }
.conclusion-card { margin-top: 8px; }

/* 公式列：虚线下划线 + cursor:help */
:deep(.formula-cell) { border-bottom: 1px dashed #409eff; cursor: help; }
</style>
