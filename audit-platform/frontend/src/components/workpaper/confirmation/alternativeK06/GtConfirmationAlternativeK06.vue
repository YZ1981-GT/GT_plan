<template>
  <div class="gt-confirmation-alternative-k06" data-testid="k0-alternative-k06">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-k06__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-k06-v1 -->
    <template v-else>
      <!-- 工具栏 -->
      <div class="gt-confirmation-alternative-k06__toolbar">
        <span class="gt-confirmation-alternative-k06__title">K0-6 其他应付款替代程序</span>
        <div class="gt-confirmation-alternative-k06__toolbar-right">
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
          <GtReviewTrigger section-id="K0-6-alternative" label="复核" />
        </div>
      </div>

      <!-- 顶部说明 -->
      <div class="gt-confirmation-alternative-k06__header-tip">
        <el-alert type="info" :closable="true" show-icon>
          提示：对回函可能性不高的、余额重大的其他应付款，发函同时执行替代程序。
        </el-alert>
      </div>

      <!-- 看板 -->
      <AlternativeD05Dashboard :metrics="data.metrics.value" />

      <!-- 主表（Master：公司列表） -->
      <AlternativeD05Master
        :companies="data.companies.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :get-completion-status="data.getCompletionStatus"
        :has-abnormal="data.hasAbnormal"
        :get-check-ratio="getCheckRatioForMaster"
        @select="handleSelectCompany"
        @add-company="handleAddCompany"
        @delete-company="handleDeleteCompany"
        @import-d01="handleImportK01"
        @import-excel="handleImportExcel"
        @export-template="handleExportExcel"
        @export-data="handleExportData"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-k06__detail">
          <div class="detail-title">
            {{ selectedCompany.entity_name || '未命名公司' }} — 检查详情
          </div>

          <!-- 抽样配置 -->
          <div class="detail-section">
            <div class="detail-section__header">一、样本选取标准与规模</div>
            <el-form
              :model="selectedCompany.sampling || {}"
              label-width="100px"
              size="small"
              :disabled="readonly"
            >
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="测试范围">
                    <el-input
                      v-model="selectedCompany.sampling!.test_scope"
                      type="textarea"
                      :rows="2"
                      placeholder="如其他应付款贷方发生额所有凭证共XX笔金额XX"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="特定样本">
                    <el-input
                      v-model="selectedCompany.sampling!.specific_samples"
                      type="textarea"
                      :rows="2"
                      placeholder="XX金额以上（大额）、关联方交易形成的款项、异常款项全部测试，共XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样总体">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_population"
                      placeholder="测试总体扣除特定样本以外的样本，共XX笔、金额XX"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="样本量">
                    <el-input
                      v-model="selectedCompany.sampling!.sample_size"
                      placeholder="抽取XX笔"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
              <el-row :gutter="12">
                <el-col :span="12">
                  <el-form-item label="抽样方法">
                    <el-select
                      v-model="selectedCompany.sampling!.sampling_method"
                      placeholder="选择抽样方法"
                      @change="markDirty"
                    >
                      <el-option value="随机选样" label="随机选样" />
                      <el-option value="系统选样" label="系统选样" />
                      <el-option value="货币单元抽样" label="货币单元抽样" />
                      <el-option value="随意选样" label="随意选样（非统计抽样适用）" />
                    </el-select>
                  </el-form-item>
                </el-col>
                <el-col :span="12">
                  <el-form-item label="抽样过程">
                    <el-input
                      v-model="selectedCompany.sampling!.sampling_process"
                      type="textarea"
                      :rows="2"
                      placeholder="使用IDEA（XX抽样工具）选择XX数量占比XX%的样本进行测试"
                      @change="markDirty"
                    />
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>
          </div>

          <!-- 余额汇总 -->
          <div class="detail-section">
            <div class="detail-section__header">二、余额汇总与检查比例</div>
            <div class="balance-cards">
              <!-- 左卡：余额数据 -->
              <div class="balance-card balance-card--data">
                <div class="balance-card__title">余额数据</div>
                <div class="balance-card__grid">
                  <div class="balance-card__item">
                    <span class="balance-card__label">函证项目</span>
                    <el-input
                      v-if="!readonly"
                      v-model="selectedCompany.balance!.item_name"
                      size="small"
                      placeholder="其他应付款"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value">{{ selectedCompany.balance?.item_name || '—' }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">年初余额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.opening_balance"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.opening_balance) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">借方发生额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.debit_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.debit_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">贷方发生额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.credit_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.credit_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">期末余额</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.closing_balance"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.closing_balance) }}</span>
                  </div>
                </div>
              </div>
              <!-- 右卡：检查比例指标 -->
              <div class="balance-card balance-card--ratio">
                <div class="balance-card__title">检查比例</div>
                <div class="ratio-indicators">
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">期后付款检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getPostPaymentRatio(selectedCompany))">
                      {{ formatRatio(data.getPostPaymentRatio(selectedCompany)) }}
                    </div>
                    <div class="ratio-indicator__desc">区块①付款金额合计 / 期末余额</div>
                  </div>
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">往来对账比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getReconcileRatio(selectedCompany))">
                      {{ formatRatio(data.getReconcileRatio(selectedCompany)) }}
                    </div>
                    <div class="ratio-indicator__desc">区块④对账覆盖金额合计 / 期末余额</div>
                  </div>
                </div>
              </div>
            </div>
          </div>

          <!-- 4 区块检查表 -->
          <div class="detail-section">
            <div class="detail-section__header">三、检查过程记录</div>
            <CheckBlock
              v-for="bt in blockTypes"
              :key="bt"
              :config="blockConfigs[bt]"
              :rows="getBlockRows(selectedCompany, bt)"
              :totals="data.getBlockTotal(selectedCompany, bt)"
              :readonly="readonly"
              :enable-ocr="true"
              :ocr-loading-row-id="ocrLoadingRowId"
              @add-row="data.addBlockRow(selectedCompany._company_id!, bt)"
              @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, bt, rowId)"
              @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, bt, rowId, field, val)"
              @ocr-upload="(rowId: string, file: File) => handleRowOcr(bt, rowId, file)"
            />
          </div>

          <!-- 审计结论 -->
          <div class="detail-section">
            <div class="detail-section__header">
              <span>四、审计说明与结论</span>
              <GtReviewTrigger section-id="K0-6-conclusion" label="复核" style="margin-left: 8px" />
              <el-button
                v-if="!readonly"
                type="primary"
                size="small"
                plain
                :loading="aiLoading"
                style="margin-left: auto"
                @click="handleAiFill"
              >
                AI 智能填充
              </el-button>
            </div>
            <el-form
              :model="selectedCompany.conclusion || {}"
              label-width="80px"
              size="small"
              :disabled="readonly"
            >
              <el-form-item label="审计说明">
                <el-input
                  v-model="selectedCompany.conclusion!.audit_note"
                  type="textarea"
                  :rows="3"
                  placeholder="概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。"
                  @change="markDirty"
                />
              </el-form-item>
              <el-form-item label="审计结论">
                <el-radio-group v-model="selectedCompany.conclusion!.conclusion_type" @change="markDirty">
                  <el-radio value="A">A - 替代程序结果支持余额</el-radio>
                  <el-radio value="B">B - 部分事项待进一步确认</el-radio>
                  <el-radio value="C">C - 存在重大异常需扩大程序</el-radio>
                </el-radio-group>
              </el-form-item>
              <el-form-item v-if="selectedCompany.conclusion?.conclusion_type" label="结论文本">
                <el-input
                  v-model="selectedCompany.conclusion!.conclusion_text"
                  type="textarea"
                  :rows="2"
                  @change="markDirty"
                />
              </el-form-item>
              <!-- 异常未决提示 -->
              <el-alert
                v-if="data.hasAbnormal(selectedCompany)"
                type="warning"
                :closable="false"
                show-icon
                class="mt-8"
              >
                当前存在异常行，请确认是否需要调整或扩大替代程序范围。
              </el-alert>
            </el-form>
          </div>
        </div>
      </template>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- 版本链抽屉 -->
    <GtWpVersionTrail
      v-if="wpId"
      ref="versionTrailRef"
      :workpaper-id="wpId"
      :project-id="projectId || ''"
    />

    <!-- 复核对话 -->
    <GtWpReviewDialogHost />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, nextTick, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import type { ConfirmationUpdatedPayload } from '@/utils/eventBus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import useAlternativeK06Data from '../k0-confirmation/composables/useAlternativeK06Data'
import { BLOCK_COLUMN_CONFIGS_K06 } from './blockColumnConfigsK06'
import type { AlternativeCompany, BlockType, CheckRow } from '../alternativeD05/alternativeD05Types'
import { useWorkpaperVersionToolbar } from '../../composables/useWorkpaperVersionToolbar'
import { useG0ReviewDialogProvide } from '../../g0-confirmation/composables/useG0ReviewDialogProvide'
import { useWorkpaperImportExport } from '../../composables/useWorkpaperImportExport'
import GtReviewTrigger from '../../GtReviewTrigger.vue'

// 复用 D0-5 的 Dashboard 和 Master 组件
import AlternativeD05Dashboard from '../alternativeD05/AlternativeD05Dashboard.vue'
import AlternativeD05Master from '../alternativeD05/AlternativeD05Master.vue'
// 复用 D0-5 的 CheckBlock 组件
import CheckBlock from '../alternativeD05/CheckBlock.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))
const GtWpVersionTrail = defineAsyncComponent(() => import('../../version-trail/GtWpVersionTrail.vue'))
const GtWpReviewDialogHost = defineAsyncComponent(() => import('../../GtWpReviewDialogHost.vue'))
const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  htmlData: Record<string, any> | null
  sheetName: string
  wpId: string
  projectId: string
  readonly?: boolean
}>()

const wpIdRef = computed(() => props.wpId ?? '')
const projectIdRef = computed(() => props.projectId ?? '')

const versionToolbar = useWorkpaperVersionToolbar({ wpId: wpIdRef, projectId: projectIdRef })
const { versionTrailRef } = versionToolbar
useG0ReviewDialogProvide({ wpId: wpIdRef, projectId: projectIdRef })

// ─── 导入导出 composable（后端三端点） ────────────────────────────────────────
const k0Ie = useWorkpaperImportExport({ wpId: wpIdRef, apiPrefix: 'k0' })

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 + selfLoad ────────────────────────────────────────────────────

const selfLoadedData = ref<any>(null)
const htmlDataRef = computed(() => props.htmlData ?? selfLoadedData.value)
const isNewFormat = computed(() => htmlDataRef.value?._format === 'alternative-k06-v1')

// selfLoad: bundle 内嵌场景 htmlData=null 时自动加载 render-config
onMounted(async () => {
  if (props.htmlData == null && props.wpId) {
    try {
      const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
      const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
      for (const sheet of sheets) {
        const hd = sheet?.html_data ?? sheet?.htmlData
        if (hd?._format === 'alternative-k06-v1') {
          selfLoadedData.value = hd
          break
        }
      }
    } catch (e) {
      console.warn('[GtConfirmationAlternativeK06] selfLoad render-config failed:', e)
    }
  }
})

// ─── EventBus 联动：K0-1→K0-6 importFromSummary + confirmation:updated 刷新 ──

const K0_WP_CODES = ['K0-1', 'K0-2', 'K0-3', 'K0-4', 'K0-5', 'K0-6', 'K0-7', 'K0-8']

function onConfirmationUpdated(payload: ConfirmationUpdatedPayload) {
  if (payload.projectId !== props.projectId) return
  if (!K0_WP_CODES.some((code) => payload.wpCode.startsWith(code))) return
  if (payload.wpId === props.wpId) return

  if (payload.wpCode === 'K0-1') {
    ElMessage.info({
      message: 'K0-1 函证结果汇总已更新，可点击"导入K0-1"刷新未回函公司列表',
      duration: 4000,
    })
  }

  if (props.wpId) {
    reloadDataFromRenderConfig()
  }
}

async function reloadDataFromRenderConfig() {
  if (!props.wpId) return
  try {
    const cfg = await api.get<any>(`/api/workpapers/${props.wpId}/render-config`, { _silent: true } as any)
    const sheets = cfg?.sheets ?? cfg?.data?.sheets ?? []
    for (const sheet of sheets) {
      const hd = sheet?.html_data ?? sheet?.htmlData
      if (hd?._format === 'alternative-k06-v1') {
        selfLoadedData.value = hd
        break
      }
    }
  } catch {
    // 静默失败
  }
}

onMounted(() => {
  eventBus.on('confirmation:updated', onConfirmationUpdated)
})

onUnmounted(() => {
  eventBus.off('confirmation:updated', onConfirmationUpdated)
})

// ─── 数据核心（K06 专属 composable） ─────────────────────────────────────────

const prefs = useDisplayPrefsStore()
const data = useAlternativeK06Data(props.wpId, props.projectId)

// ─── 区块配置（K06 专属列定义） ──────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_K06

// ─── 选中公司 ────────────────────────────────────────────────────────────────

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!data.selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === data.selectedCompanyId.value)
})

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

function getCheckRatioForMaster(company: AlternativeCompany, type: 'receipt' | 'shipment') {
  return type === 'receipt'
    ? data.getPostPaymentRatio(company)
    : data.getReconcileRatio(company)
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  ElMessageBox.prompt('请输入公司名称', '新增公司', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：XX科技有限公司',
    inputValidator: (val) => (val && val.trim() ? true : '公司名称不能为空'),
  }).then(({ value }) => {
    const company = data.addCompany({ entity_name: value.trim() })
    data.selectedCompanyId.value = company._company_id!
    nextTick(() => {
      const el = document.querySelector('.gt-confirmation-alternative-k06__detail')
      el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    })
  }).catch(() => { /* 取消 */ })
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

async function handleImportK01() {
  try {
    const count = await data.importFromSummary()
    if (count > 0) {
      ElMessage.success(`已从 K0-1 带入 ${count} 个未回函项目`)
    } else {
      ElMessage.info('K0-1 暂无新的未回函项目可带入')
    }
  } catch (e: any) {
    ElMessage.warning('从 K0-1 带入失败：' + (e?.message || '未知错误'))
  }
}

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExcel() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  if (props.wpId) {
    try {
      await handleImportViaBackend(file)
    } catch {
      await handleImportFileFallback(file)
    }
  } else {
    await handleImportFileFallback(file)
  }
  if (importFileInput.value) importFileInput.value.value = ''
}

async function handleImportFileFallback(file: File) {
  try {
    const { read, utils } = await import('xlsx')
    const buf = await file.arrayBuffer()
    const wb = read(buf, { type: 'array' })
    const ws = wb.Sheets[wb.SheetNames[0]]
    const rawRows: Record<string, any>[] = utils.sheet_to_json(ws)
    if (rawRows.length === 0) {
      ElMessage.warning('Excel 文件为空或无法解析')
      return
    }
    const colMap: Record<string, string[]> = {
      entity_name: ['供应商/客户名称', '单位名称', '被询证单位', '客户名称', '公司名称', '债权人'],
      confirm_index: ['索引号', '函证索引号', '编号'],
    }
    const importData: Partial<AlternativeCompany>[] = []
    for (const raw of rawRows) {
      const hasValue = Object.values(raw).some(v => v != null && String(v).trim() !== '')
      if (!hasValue) continue
      const row: Partial<AlternativeCompany> = {}
      for (const [field, aliases] of Object.entries(colMap)) {
        for (const alias of aliases) {
          if (raw[alias] != null && String(raw[alias]).trim() !== '') {
            ;(row as any)[field] = String(raw[alias]).trim()
            break
          }
        }
      }
      if (row.entity_name) importData.push(row)
    }
    if (importData.length > 0) {
      data.importCompanies(importData)
      ElMessage.success(`成功导入 ${importData.length} 家公司`)
    } else {
      ElMessage.warning('未识别到有效数据，请检查列头是否包含：供应商/客户名称')
    }
  } catch (e: any) {
    ElMessage.error('导入失败：' + (e?.message || '文件格式错误'))
  }
}

async function handleExportExcel() {
  try {
    await k0Ie.exportTemplate('K0-6')
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('导出模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (data.companies.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    await k0Ie.exportData('K0-6')
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

// ─── 导入导出下拉命令 ──────────────────────────────────────────────────────

function handleIeCommand(command: string) {
  switch (command) {
    case 'export-template': handleExportExcel(); break
    case 'export-data': handleExportData(); break
    case 'import-data': handleImportExcel(); break
  }
}

async function handleImportViaBackend(file: File) {
  const result = await k0Ie.importData('K0-6', file)
  if (result && result.rowCount != null) {
    ElMessage.success(`成功导入 ${result.rowCount} 条数据`)
    if (props.wpId) {
      await reloadDataFromRenderConfig()
    }
  } else {
    ElMessage.success('导入完成')
  }
}

// ─── AI 智能填充 ─────────────────────────────────────────────────────────────

const aiLoading = ref(false)

function handleAiFill() {
  if (!selectedCompany.value) return
  aiLoading.value = true
  try {
    const company = selectedCompany.value
    const entityName = company.entity_name || '该公司'
    const postPaymentRatio = data.getPostPaymentRatio(company)
    const reconcileRatio = data.getReconcileRatio(company)
    const status = data.getCompletionStatus(company)
    const hasAnomaly = data.hasAbnormal(company)

    const b1Count = (company.block1_rows || []).length
    const b2Count = (company.block2_rows || []).length
    const b3Count = (company.block3_rows || []).length
    const b4Count = (company.block4_rows || []).length
    const totalRows = b1Count + b2Count + b3Count + b4Count
    const abnormalRows = [
      ...(company.block1_rows || []),
      ...(company.block2_rows || []),
      ...(company.block3_rows || []),
      ...(company.block4_rows || []),
    ].filter(r => r.is_abnormal === '是').length

    const parts: string[] = []

    if (totalRows > 0) {
      parts.push(
        `对${entityName}其他应付款执行替代程序，共检查 ${totalRows} 笔凭证/单据（期后付款 ${b1Count} 笔、期末余额证据 ${b2Count} 笔、本期发生额 ${b3Count} 笔、往来对账/协议 ${b4Count} 笔），完成度 ${status.completed}/4 区块。`,
      )
    } else {
      parts.push(`对${entityName}其他应付款执行替代程序，尚未录入检查数据。`)
    }

    if (postPaymentRatio !== null || reconcileRatio !== null) {
      const pPart = postPaymentRatio !== null ? `期后付款检查比例 ${postPaymentRatio.toFixed(1)}%` : '期后付款检查比例待计算'
      const rPart = reconcileRatio !== null ? `往来对账比例 ${reconcileRatio.toFixed(1)}%` : '往来对账比例待计算'
      parts.push(`${pPart}，${rPart}。`)
    }

    if (hasAnomaly) {
      parts.push(`检查中发现 ${abnormalRows} 笔异常项，需进一步核实原因并评估是否需要调整。`)
    } else if (totalRows > 0) {
      parts.push('检查中未发现异常事项。')
    }

    if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
      parts.push('替代程序结果支持其他应付款账面余额的合理性，未发现需要调整事项。')
    } else if (hasAnomaly) {
      parts.push('建议：对异常项扩大检查范围或追加审计程序，并与管理层确认相关事项。')
    }

    const generatedText = parts.join('')

    if (!company.conclusion) company.conclusion = {}
    if (!company.conclusion.audit_note) {
      company.conclusion.audit_note = generatedText
    } else {
      company.conclusion.audit_note += '\n' + generatedText
    }
    data.isDirty.value = true

    if (!company.conclusion.conclusion_type) {
      if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
        company.conclusion.conclusion_type = 'A'
      } else if (hasAnomaly) {
        company.conclusion.conclusion_type = 'C'
      } else {
        company.conclusion.conclusion_type = 'B'
      }
      data.isDirty.value = true
    }

    ElMessage.success('已根据检查数据生成审计说明（仅供参考，请根据实际情况修改）')
  } finally {
    aiLoading.value = false
  }
}

// ─── 保存 ────────────────────────────────────────────────────────────────────

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
  versionToolbar.scheduleAutoSnapshot()
  if (props.projectId) {
    eventBus.emit('confirmation:updated', {
      projectId: props.projectId,
      wpCode: 'K0-6',
      wpId: props.wpId,
      timestamp: Date.now(),
    })
  }
}

// ─── 行级 OCR：上传证据文件 → contract-ocr 识别 → 确认 → merge 填入 ────────
const ocrLoadingRowId = ref<string | null>(null)

const OCR_FIELD_MAP: Record<BlockType, Record<string, string>> = {
  block1: {
    date: 'approvalDateNo', 日期: 'approvalDateNo',
    approval_no: 'approvalDateNo', 审批编号: 'approvalDateNo',
    receipt_date: 'receiptDate', 回单日期: 'receiptDate',
    payee: 'payee', 收款方: 'payee',
    amount: 'paymentAmount', 金额: 'paymentAmount', 付款金额: 'paymentAmount',
  },
  block2: {
    date: 'loanApprovalDateNo', 日期: 'loanApprovalDateNo',
    agreement_no: 'agreementNo', 协议编号: 'agreementNo', 借据编号: 'agreementNo',
    counterparty: 'counterparty', 对方单位: 'counterparty',
    amount: 'agreementAmount', 金额: 'agreementAmount',
  },
  block3: {
    date: 'docDateNo', 日期: 'docDateNo',
    doc_no: 'docDateNo', 单据编号: 'docDateNo',
    reason: 'docReason', 事由: 'docReason',
    approver: 'approver', 审批人: 'approver',
    amount: 'approvalAmount', 金额: 'approvalAmount',
  },
  block4: {
    date: 'reconcileDate', 日期: 'reconcileDate', 对账日期: 'reconcileDate',
    other_balance: 'otherBalance', 对方余额: 'otherBalance',
    self_balance: 'selfBalance', 本方余额: 'selfBalance',
    agreement_no: 'agreementNo', 协议编号: 'agreementNo',
    sign_date: 'signDate', 签订日期: 'signDate',
  },
}

async function handleRowOcr(blockType: BlockType, rowId: string, file: File): Promise<void> {
  if (!selectedCompany.value || !props.wpId) return
  ocrLoadingRowId.value = rowId
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return
    }
    const map = OCR_FIELD_MAP[blockType]
    const patch: Record<string, any> = {}
    for (const [ocrKey, val] of Object.entries(fields)) {
      const target = map[ocrKey]
      if (target && val != null && String(val).trim() !== '') {
        patch[target] = val
      }
    }
    if (Object.keys(patch).length === 0) {
      ElMessage.info('OCR完成，识别字段无法匹配本区块')
      return
    }
    const preview = Object.entries(patch)
      .map(([k, v]) => `${k}: ${v}`)
      .join('，')
    await ElMessageBox.confirm(`识别到证据信息：\n${preview}\n是否填入当前行？`, 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
    })
    for (const [field, val] of Object.entries(patch)) {
      data.updateBlockField(selectedCompany.value._company_id!, blockType, rowId, field, val)
    }
    ElMessage.success('已填入识别结果')
  } catch (e) {
    if (e !== 'cancel') ElMessage.warning('OCR识别失败')
  } finally {
    ocrLoadingRowId.value = null
  }
}

// ─── Utility ─────────────────────────────────────────────────────────────────

function markDirty() {
  data.isDirty.value = true
}

function formatRatio(val: number | null): string {
  if (val === null) return 'N/A'
  return `${val.toFixed(1)}%`
}

function formatAmount(val: number | undefined | null): string {
  if (val == null) return '—'
  return prefs.fmt(val)
}

function ratioClass(val: number | null): string {
  if (val === null) return 'ratio-indicator__value--na'
  if (val >= 80) return 'ratio-indicator__value--good'
  if (val >= 50) return 'ratio-indicator__value--warn'
  return 'ratio-indicator__value--danger'
}

defineExpose({
  handleExportTemplate: handleExportExcel,
  handleExportData: handleExportData,
  handleImport: handleImportExcel,
  handleImportClick: handleImportExcel,
  handleDownloadImportTemplate: handleExportExcel,
})
</script>

<style scoped>
.gt-confirmation-alternative-k06 {
  padding: 8px 0;
  font-size: var(--wp-font-size, 13px);
}

.gt-confirmation-alternative-k06__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}

.gt-confirmation-alternative-k06__title {
  font-size: 15px;
  font-weight: 600;
}

.gt-confirmation-alternative-k06__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-confirmation-alternative-k06__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-k06__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-k06__detail {
  margin-top: 16px;
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}

.detail-title {
  font-size: 14px;
  font-weight: 600;
  margin-bottom: 12px;
  color: var(--el-text-color-primary);
}

.detail-section {
  margin-bottom: 16px;
}

.detail-section__header {
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  display: flex;
  align-items: center;
}

/* ─── 卡片式双栏：余额汇总与检查比例 ───────────────────────────────────── */

.balance-cards {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 12px;
}

.balance-card {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px 16px;
  background: #fafbfc;
}

.balance-card__title {
  font-size: 12px;
  font-weight: 600;
  color: #909399;
  margin-bottom: 10px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.balance-card__grid {
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 10px 16px;
}

.balance-card__item {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.balance-card__label {
  font-size: 11px;
  color: #909399;
}

.balance-card__value {
  font-size: var(--wp-font-size, 13px);
  color: #303133;
}

.balance-card__value--num {
  font-variant-numeric: tabular-nums;
  font-weight: 500;
}

.balance-card--ratio {
  display: flex;
  flex-direction: column;
  justify-content: center;
  background: linear-gradient(135deg, #f5f0ff 0%, #eef2ff 100%);
  border-color: #d9d0f0;
}

.ratio-indicators {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.ratio-indicator {
  text-align: center;
}

.ratio-indicator__label {
  font-size: 11px;
  color: #606266;
  margin-bottom: 4px;
}

.ratio-indicator__value {
  font-size: 24px;
  font-weight: 700;
  line-height: 1.2;
}

.ratio-indicator__value--good { color: #67c23a; }
.ratio-indicator__value--warn { color: #e6a23c; }
.ratio-indicator__value--danger { color: #f56c6c; }
.ratio-indicator__value--na { color: #c0c4cc; }

.ratio-indicator__desc {
  font-size: 10px;
  color: #c0c4cc;
  margin-top: 2px;
}

@media (max-width: 900px) {
  .balance-cards {
    grid-template-columns: 1fr;
  }
  .balance-card__grid {
    grid-template-columns: 1fr 1fr;
  }
}

.mt-8 { margin-top: 8px; }
</style>
