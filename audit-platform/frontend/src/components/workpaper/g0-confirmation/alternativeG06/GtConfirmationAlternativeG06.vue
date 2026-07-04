<template>
  <div class="gt-confirmation-alternative-g06">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-g06__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-g06-v1 -->
    <template v-else>
      <!-- 顶部说明 -->
      <div class="gt-confirmation-alternative-g06__header-tip">
        <el-alert type="info" :closable="true" show-icon>
          提示③：对回函可能性不高的、余额重大的，发函同时执行替代程序。
        </el-alert>
      </div>

      <!-- 看板 -->
      <AlternativeD05Dashboard :metrics="data.metrics.value" />

      <!-- 主表 -->
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
        @import-d01="handleImportG01"
        @import-excel="handleImportExcel"
        @export-template="handleExportExcel"
        @export-data="handleExportData"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-g06__detail">
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
                      placeholder="如应付账款借方发生额所有凭证共XX笔金额XX、贷方发生额所有凭证共XX笔金额XX"
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
                      placeholder="XX金额以上（大额）、关联方/关联交易形成的款项、XX异常款项全部测试，共XX笔"
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
                      placeholder="交易性金融资产"
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
                    <span class="balance-card__label">本期增加</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.increase_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.increase_amount) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">本期减少</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.decrease_amount"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.decrease_amount) }}</span>
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
                  <div class="balance-card__item">
                    <span class="balance-card__label">投资收益</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.investment_income"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.investment_income) }}</span>
                  </div>
                  <div class="balance-card__item">
                    <span class="balance-card__label">公允价值变动</span>
                    <el-input
                      v-if="!readonly"
                      v-model.number="selectedCompany.balance!.fv_change"
                      type="number"
                      size="small"
                      @change="markDirty"
                    />
                    <span v-else class="balance-card__value balance-card__value--num">{{ formatAmount(selectedCompany.balance?.fv_change) }}</span>
                  </div>
                </div>
              </div>
              <!-- 右卡：检查比例指标 -->
              <div class="balance-card balance-card--ratio">
                <div class="balance-card__title">检查比例</div>
                <div class="ratio-indicators">
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">股利检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'payment'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'payment')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块②实收合计 / 期末余额</div>
                  </div>
                  <div class="ratio-indicator">
                    <div class="ratio-indicator__label">持仓检查比例</div>
                    <div class="ratio-indicator__value" :class="ratioClass(data.getCheckRatio(selectedCompany, 'inbound'))">
                      {{ formatRatio(data.getCheckRatio(selectedCompany, 'inbound')) }}
                    </div>
                    <div class="ratio-indicator__desc">区块①市值合计 / 期末余额</div>
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
              @add-row="data.addBlockRow(selectedCompany._company_id!, bt)"
              @delete-row="(rowId: string) => data.deleteBlockRow(selectedCompany!._company_id!, bt, rowId)"
              @update-field="(rowId: string, field: string, val: any) => data.updateBlockField(selectedCompany!._company_id!, bt, rowId, field, val)"
            />
          </div>

          <!-- 审计结论 -->
          <div class="detail-section">
            <div class="detail-section__header">
              <span>四、审计说明与结论</span>
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
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { useAlternativeG06Data } from './composables/useAlternativeG06Data'
import type { AlternativeCompany, BlockType, CheckRow } from '../../confirmation/alternativeD05/alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS_G06 } from './blockColumnConfigsG06'

// 复用 D0-5 的 Dashboard 和 Master 组件
import AlternativeD05Dashboard from '../../confirmation/alternativeD05/AlternativeD05Dashboard.vue'
import AlternativeD05Master from '../../confirmation/alternativeD05/AlternativeD05Master.vue'
// 复用 D0-5 的 CheckBlock 组件
import CheckBlock from '../../confirmation/alternativeD05/CheckBlock.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../../GtGridSheet.vue'))

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
const isNewFormat = computed(() => props.htmlData?._format === 'alternative-g06-v1')

// ─── 数据核心（D06 专属 composable） ─────────────────────────────────────────

const prefs = useDisplayPrefsStore()
const data = useAlternativeG06Data({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 区块配置（D06 专属列定义） ──────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS_G06

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
  return data.getCheckRatio(company, type === 'receipt' ? 'payment' : 'inbound')
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  const company = data.addCompany()
  data.selectedCompanyId.value = company._company_id!
  nextTick(() => {
    const el = document.querySelector('.gt-confirmation-alternative-g06__detail')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

function handleImportG01() {
  ElMessage.info('从 G0-1 带入功能待跨底稿引用 API 接入后启用')
}

const importFileInput = ref<HTMLInputElement | null>(null)

function handleImportExcel() {
  importFileInput.value?.click()
}

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
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
      entity_name: ['供应商/客户名称', '单位名称', '被询证单位', '客户名称', '公司名称'],
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
  } finally {
    if (importFileInput.value) importFileInput.value.value = ''
  }
}

async function handleExportExcel() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 公司清单模板
    const companyHeaders = ['序号', '函证索引号', '供应商/客户名称']
    const companyExample = ['1', 'D0-001', '示例公司（请删除）']
    const wsCompany = utils.aoa_to_sheet([companyHeaders, companyExample])
    wsCompany['!cols'] = [{ wch: 6 }, { wch: 12 }, { wch: 30 }]
    utils.book_append_sheet(wb, wsCompany, '公司清单')

    // Sheet 2~5: 4 区块列头
    const blockSheets: { key: string; name: string }[] = [
      { key: 'block1', name: '①持仓证明' },
      { key: 'block2', name: '②股利收入' },
      { key: 'block3', name: '③处置收益' },
      { key: 'block4', name: '④公允价值' },
    ]
    for (const { key, name } of blockSheets) {
      const cols = BLOCK_COLUMN_CONFIGS_G06[key].columns
      const headers = cols.map(c => c.label)
      const ws = utils.aoa_to_sheet([headers])
      ws['!cols'] = cols.map(c => ({ wch: Math.max((c.width || 100) / 8, (c.label?.length || 4) * 2.5) }))
      utils.book_append_sheet(wb, ws, name)
    }

    // Sheet 6: 填写说明
    const instructions = [
      ['G0-6 投资循环替代程序 — 导入模板说明'],
      [''],
      ['【Sheet 说明】'],
      ['  公司清单：填写替代程序的公司列表（必须），导入后每公司自动创建 4 区块检查记录'],
      ['  ①期末余额证据：应付账款检查-形成期末余额的订单/合同、出库单等支持性证据'],
      ['  ②期后回款：应付账款检查-检查期后回款情况'],
      ['  ③本期出库：销售检查-本期销售出库的合同、出库单、运输单、验收单等'],
      ['  ④本期收款：销售检查-本期收款检查'],
      [''],
      ['【公司清单列说明】'],
      ['  序号：自动生成（留空即可）'],
      ['  函证索引号：来自 F0-1 的索引号（如 D0-001），用于跨底稿追溯'],
      ['  供应商/客户名称：被检查公司全称（必填）'],
      [''],
      ['【注意事项】'],
      ['  1. 先导入"公司清单" Sheet（系统仅读取第一个 Sheet 的公司数据）'],
      ['  2. 已存在相同索引号的公司不会重复导入'],
      ['  3. 导入后选中公司 → 在 4 个区块中录入检查明细'],
      ['  4. 付款检查比例 = 区块④收款金额合计 / 本期采购额（自动计算）'],
      ['  5. 入库检查比例 = 区块③出库金额合计 / 本期采购额（自动计算）'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 80 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'G0-6投资循环替代程序_导入模板.xlsx')
    ElMessage.success('模板已导出')
  } catch (e: any) {
    ElMessage.error('生成模板失败：' + (e?.message || '未知错误'))
  }
}

async function handleExportData() {
  if (data.companies.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 公司汇总
    const summaryHeaders = ['序号', '索引号', '公司名称', '完成度', '收款比例', '出库比例', '是否异常']
    const summaryData = data.companies.value.map(c => [
      c.seq ?? '',
      c.confirm_index ?? '',
      c.entity_name ?? '',
      `${data.getCompletionStatus(c).completed}/4`,
      data.getCheckRatio(c, 'payment') !== null ? `${data.getCheckRatio(c, 'payment')!.toFixed(1)}%` : 'N/A',
      data.getCheckRatio(c, 'inbound') !== null ? `${data.getCheckRatio(c, 'inbound')!.toFixed(1)}%` : 'N/A',
      data.hasAbnormal(c) ? '是' : '否',
    ])
    const wsSummary = utils.aoa_to_sheet([summaryHeaders, ...summaryData])
    wsSummary['!cols'] = [{ wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 8 }, { wch: 10 }, { wch: 10 }, { wch: 8 }]
    utils.book_append_sheet(wb, wsSummary, '公司汇总')

    // 每个区块一个 Sheet
    const blockSheets: { key: BlockType; name: string }[] = [
      { key: 'block1', name: '①持仓证明' },
      { key: 'block2', name: '②股利收入' },
      { key: 'block3', name: '③处置收益' },
      { key: 'block4', name: '④公允价值' },
    ]
    for (const { key, name } of blockSheets) {
      const cols = BLOCK_COLUMN_CONFIGS_G06[key].columns
      const headers = ['公司名称', ...cols.map(c => c.label)]
      const rows: any[][] = []
      for (const company of data.companies.value) {
        const blockRows = getBlockRows(company, key)
        for (const row of blockRows) {
          rows.push([
            company.entity_name ?? '',
            ...cols.map(c => row[c.field] ?? ''),
          ])
        }
      }
      const ws = utils.aoa_to_sheet([headers, ...rows])
      ws['!cols'] = [{ wch: 20 }, ...cols.map(c => ({ wch: Math.max((c.width || 80) / 8, 10) }))]
      utils.book_append_sheet(wb, ws, name)
    }

    writeFileXLSX(wb, 'G0-6投资循环替代程序_数据导出.xlsx')
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

const aiLoading = ref(false)

function handleAiFill() {
  if (!selectedCompany.value) return
  aiLoading.value = true
  try {
    const company = selectedCompany.value
    const entityName = company.entity_name || '该公司'
    const receiptRatio = data.getCheckRatio(company, 'payment')
    const shipmentRatio = data.getCheckRatio(company, 'inbound')
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
        `对${entityName}执行替代程序，共检查 ${totalRows} 笔凭证/单据（期末余额证据 ${b1Count} 笔、期后回款 ${b2Count} 笔、本期出库 ${b3Count} 笔、本期收款 ${b4Count} 笔），完成度 ${status.completed}/4 区块。`
      )
    } else {
      parts.push(`对${entityName}执行替代程序，尚未录入检查数据。`)
    }

    if (receiptRatio !== null || shipmentRatio !== null) {
      const rPart = receiptRatio !== null ? `付款检查比例 ${receiptRatio.toFixed(1)}%` : '付款检查比例待计算'
      const sPart = shipmentRatio !== null ? `入库检查比例 ${shipmentRatio.toFixed(1)}%` : '入库检查比例待计算'
      parts.push(`${rPart}，${sPart}。`)
    }

    if (hasAnomaly) {
      parts.push(`检查中发现 ${abnormalRows} 笔异常项，需进一步核实原因并评估是否需要调整。`)
    } else if (totalRows > 0) {
      parts.push('检查中未发现异常事项。')
    }

    if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
      parts.push('替代程序结果支持账面余额的合理性，未发现需要调整事项。')
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

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

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

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleExportTemplate: handleExportExcel,
  handleExportData,
  handleImport: handleImportExcel,
  handleImportClick: handleImportExcel,
  handleDownloadImportTemplate: handleExportExcel,
})
</script>

<style scoped>
.gt-confirmation-alternative-g06 {
  padding: 8px 0;
}

.gt-confirmation-alternative-g06__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-g06__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-g06__detail {
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
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: var(--el-fill-color-light);
  border-radius: 3px;
  display: flex;
  align-items: center;
}

.ratio-display {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 14px;
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
  font-size: 13px;
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
