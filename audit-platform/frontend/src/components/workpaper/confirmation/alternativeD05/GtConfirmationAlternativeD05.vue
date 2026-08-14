<template>
  <div class="gt-confirmation-alternative-d05">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-alternative-d05__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：alternative-d05-v1 -->
    <template v-else>
      <!-- 顶部说明 -->
      <div class="gt-confirmation-alternative-d05__header-tip">
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
        :get-check-ratio="data.getCheckRatio"
        @select="handleSelectCompany"
        @add-company="handleAddCompany"
        @delete-company="handleDeleteCompany"
        @update-field="handleUpdateField"
        @import-d01="showD01Dialog = true"
        @import-excel="handleImportExcel"
        @export-template="handleExportTemplate"
        @export-data="handleExportData"
        @save="handleSave"
      />

      <!-- Detail: 选中公司的详情 -->
      <template v-if="selectedCompany">
        <div class="gt-confirmation-alternative-d05__detail">
          <div class="detail-title">
            {{ selectedCompany.entity_name || '请在上方表格填写公司名称' }} — 检查详情
          </div>

          <AlternativeDetailPanel
            :company="selectedCompany"
            :readonly="readonly"
            :block-types="blockTypes"
            :block-configs="blockConfigs"
            balance-field="sales_amount"
            item-name-placeholder="合同负债"
            sampling-scope-placeholder="如合同负债借方发生额所有凭证共XX笔金额XX、贷方发生额所有凭证共XX笔金额XX"
            audit-note-placeholder="概述程序的测试情况、结果；拟调整事项及其调整分录、未调整事项及其影响。"
            :ratios="detailRatios"
            :ai-loading="aiLoading"
            :get-block-total="data.getBlockTotal"
            :get-check-ratio="(c, t) => data.getCheckRatio(c, t as 'receipt' | 'shipment')"
            :add-block-row="data.addBlockRow"
            :delete-block-row="data.deleteBlockRow"
            :update-block-field="data.updateBlockField"
            :has-abnormal="data.hasAbnormal"
            @mark-dirty="markDirty"
            @ai-fill="handleAiFill"
          />
        </div>
      </template>
    </template>

    <!-- 隐藏文件选择器 -->
    <input ref="importFileInput" type="file" accept=".xlsx,.xls,.csv" style="display:none" @change="handleImportFile" />

    <!-- D0-1 带入确认弹窗 -->
    <el-dialog v-model="showD01Dialog" title="从 D0-1 带入未回函公司" width="520px" append-to-body>
      <div style="font-size:13px;line-height:1.8;color:#606266">
        <p style="margin:0 0 12px"><strong>操作说明：</strong></p>
        <ol style="padding-left:20px;margin:0 0 16px">
          <li>系统将从 D0-1 函证汇总表中，筛选<strong>未回函</strong>的函证对象</li>
          <li>自动带入：函证索引号、被询证单位名称、科目、函证金额</li>
          <li>为每家未回函公司创建替代程序记录（4 项检查待填）</li>
          <li>已存在相同索引号的公司不会重复导入</li>
        </ol>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:0">
          <template #title>带入后需完成</template>
          逐公司执行 4 项替代程序检查（期后收款/合同/出库单/对账单），记录检查结果
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showD01Dialog = false">取消</el-button>
        <el-button type="primary" @click="handleImportD01">确认带入</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import { exportMultiSheetData, parseFile } from '@/composables/useExcelIO'
import { useAlternativeData } from './composables/useAlternativeData'
import { importUnrepliedAsCompanies } from '../coordination/importFromSummary'
import type { AlternativeCompany, BlockType, CheckRow } from './alternativeD05Types'
import { BLOCK_COLUMN_CONFIGS } from './blockColumnConfigs'

import AlternativeD05Dashboard from './AlternativeD05Dashboard.vue'
import AlternativeD05Master from './AlternativeD05Master.vue'
import AlternativeDetailPanel from './AlternativeDetailPanel.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

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
const isNewFormat = computed(() => props.htmlData?._format === 'alternative-d05-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useAlternativeData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 区块配置 ────────────────────────────────────────────────────────────────

const blockTypes: BlockType[] = ['block1', 'block2', 'block3', 'block4']
const blockConfigs = BLOCK_COLUMN_CONFIGS
const detailRatios = [
  { type: 'receipt', label: '收款检查比例', desc: '区块③收款合计 / 本期销售额' },
  { type: 'shipment', label: '出库检查比例', desc: '区块④出库合计 / 本期销售额' },
]

// ─── 选中公司 ────────────────────────────────────────────────────────────────

const selectedCompany = computed<AlternativeCompany | undefined>(() => {
  if (!data.selectedCompanyId.value) return data.companies.value[0]
  return data.companies.value.find((c) => c._company_id === data.selectedCompanyId.value)
})

function getBlockRows(company: AlternativeCompany, blockType: BlockType): CheckRow[] {
  const key = `${blockType}_rows` as keyof AlternativeCompany
  return (company[key] as CheckRow[]) || []
}

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleSelectCompany(companyId: string) {
  data.selectedCompanyId.value = companyId
}

function handleAddCompany() {
  const company = data.addCompany()
  data.selectedCompanyId.value = company._company_id!
  // 自动滚动到详情区
  nextTick(() => {
    const el = document.querySelector('.gt-confirmation-alternative-d05__detail')
    el?.scrollIntoView({ behavior: 'smooth', block: 'start' })
  })
}

function handleDeleteCompany(companyId: string) {
  data.deleteCompany(companyId)
}

function handleUpdateField(companyId: string, field: string, value: any) {
  data.updateCompany(companyId, field, value)
}

function handleImportD01() {
  showD01Dialog.value = false
  if (!props.projectId) {
    ElMessage.warning('缺少项目上下文')
    return
  }
  // 循环码派生：D0-5→D0-1 优先; 回退 D0（整册）
  const cycleBase = (props.wpCode || '').split('-')[0]
  const summaryCode = cycleBase + '-1'
  importUnrepliedAsCompanies(props.projectId, summaryCode, { defaultItemName: '应收账款' })
    .then(async (res) => {
      if (!res.ok) {
        // 回退尝试父底稿
        const res2 = await importUnrepliedAsCompanies(props.projectId!, cycleBase, { defaultItemName: '应收账款' })
        if (!res2.ok) {
          ElMessage.warning(res2.reason === 'missing-summary' ? `未找到 ${summaryCode} 或 ${cycleBase}` : res2.message)
          return
        }
        if (res2.companies.length === 0) {
          ElMessage.info(res2.emptyReason || '无未回函项目')
          return
        }
        data.importCompanies(res2.companies)
        ElMessage.success(`已从 ${cycleBase} 带入 ${res2.companies.length} 个未回函被函证单位`)
        return
      }
      if (res.companies.length === 0) {
        ElMessage.info(res.emptyReason || '无未回函项目')
        return
      }
      data.importCompanies(res.companies)
      ElMessage.success(`已从 ${summaryCode} 带入 ${res.companies.length} 个未回函被函证单位`)
    })
    .catch((e: any) => {
      ElMessage.error('带入失败：' + (e?.message || '网络错误'))
    })
}

function handleImportExcel() {
  importFileInput.value?.click()
}

const importFileInput = ref<HTMLInputElement | null>(null)

async function handleImportFile(event: Event) {
  const file = (event.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    // 走 useExcelIO 单一入口（spec: frontend-excel-io-single-entry-convergence，B2 批）。
    //
    // 原实现是 `sheet_to_json(ws)` 不带 header:1 ⇒ 对象模式（键取第一行列名），
    // 且取 `wb.SheetNames[0]`。三个参数逐项对齐原行为：
    // - `sheetName: ''` + 不传 matcher ⇒ 降级取第一个 sheet（同原实现）
    // - `skipRows: 1` ⇒ 表头占一行，数据从第二行起
    // - 🔴 `requireFirstCell: false` ⇒ 本表首列是「序号」，模板说明里写着
    //   「序号：自动生成（留空即可）」。`parseFile` 默认要求首列非空，会把用户
    //   留空序号的行**静默丢弃**；原实现不做此检查。全空行由下方 hasValue 过滤。
    // - `skipExamplePrefix: ''` ⇒ 原实现无示例行跳过逻辑（示例行靠用户手删，
    //   且其首列是 '1' 而非 '示例'，默认前缀本就命中不到）
    const { rows: rawRows } = await parseFile(file, {
      sheetName: '',
      skipRows: 1,
      skipExamplePrefix: '',
      requireFirstCell: false,
    })
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

/** 区块模板 sheet 的列宽（与原实现逐字一致，勿改公式） */
function blockColWidths(key: BlockType): Array<{ wch: number }> {
  return BLOCK_COLUMN_CONFIGS[key].columns.map(c => ({
    wch: Math.max((c.width || 100) / 8, (c.label?.length || 4) * 2.5),
  }))
}

async function handleExportTemplate() {
  try {
    // Sheet 1: 公司清单模板
    const companyHeaders = ['序号', '函证索引号', '供应商/客户名称']
    const companyExample = ['1', 'D0-001', '示例公司（请删除）']

    // Sheet 2~5: 四个区块（只有表头行的空模板）
    const blockTemplates: Array<{ key: BlockType; name: string }> = [
      { key: 'block1', name: '①期后结转' },
      { key: 'block2', name: '②期末余额证据' },
      { key: 'block3', name: '③本期收款检查' },
      { key: 'block4', name: '④本期出库' },
    ]

    // Sheet 6: 填写说明
    const instructions = [
      ['D0-5 合同负债及销售替代程序 — 导入模板说明'],
      [''],
      ['【Sheet 说明】'],
      ['  公司清单：填写替代程序的公司列表（必须），导入后每公司自动创建 4 区块检查记录'],
      ['  ①期后结转：合同负债检查-检查期后结转明细'],
      ['  ②期末余额证据：合同负债检查-形成期末余额的合同、订单、银行收款凭单等支持性证据'],
      ['  ③本期收款检查：销售检查-本期收款检查明细'],
      ['  ④本期出库：销售检查-本期出库的合同、出库单、运输单、验收单等支持性证据检查'],
      [''],
      ['【公司清单列说明】'],
      ['  序号：自动生成（留空即可）'],
      ['  函证索引号：来自 D0-1 的索引号（如 D0-001），用于跨底稿追溯'],
      ['  供应商/客户名称：被检查公司全称（必填）'],
      [''],
      ['【检查区块通用说明】'],
      ['  每个区块 Sheet 的第一行为表头，请勿修改'],
      ['  区块数据按公司分组填写（可先导入公司清单，再手动录入各区块）'],
      ['  "是否异常"列填写：是 / 否'],
      ['  金额列为数值格式，无需添加千分位'],
      [''],
      ['【抽样配置与余额汇总】'],
      ['  这两个区域在系统中按公司逐个填写，不通过 Excel 导入'],
      ['  导入公司清单后，在系统中选中公司 → 填写"样本选取标准"和"余额汇总"'],
      [''],
      ['【注意事项】'],
      ['  1. 先导入"公司清单" Sheet（系统仅读取第一个 Sheet 的公司数据）'],
      ['  2. 已存在相同索引号的公司不会重复导入'],
      ['  3. 导入后选中公司 → 在 4 个区块中录入检查明细'],
      ['  4. 收款检查比例 = 区块③收款金额合计 / 本期销售额（自动计算）'],
      ['  5. 出库检查比例 = 区块④出库金额合计 / 本期销售额（自动计算）'],
    ]
    // 六个 sheet 全是纯 AOA 形态（表头+示例 / 只有表头 / 纯文本说明），
    // 故走 exportMultiSheetData 的 AOA 分支 —— rows 与 colWidths 原样传，产物零变化。
    // successMessage:false 因本函数自行弹提示（下一行），开着会双弹。
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '公司清单',
          rows: [companyHeaders, companyExample],
          colWidths: [{ wch: 6 }, { wch: 12 }, { wch: 30 }],
        },
        ...blockTemplates.map(({ key, name }) => ({
          sheetName: name,
          rows: [BLOCK_COLUMN_CONFIGS[key].columns.map(c => c.label)],
          colWidths: blockColWidths(key),
        })),
        { sheetName: '填写说明', rows: instructions, colWidths: [{ wch: 80 }] },
      ],
      fileName: 'D0-5合同负债及销售替代程序_导入模板.xlsx',
      applyStyles: false,
      successMessage: false,
    })
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
    // Sheet 1: 公司汇总
    const summaryHeaders = ['序号', '索引号', '公司名称', '完成度', '收款比例', '出库比例', '是否异常']
    const summaryData = data.companies.value.map(c => [
      c.seq ?? '',
      c.confirm_index ?? '',
      c.entity_name ?? '',
      `${data.getCompletionStatus(c).completed}/4`,
      data.getCheckRatio(c, 'receipt') !== null ? `${data.getCheckRatio(c, 'receipt')!.toFixed(1)}%` : 'N/A',
      data.getCheckRatio(c, 'shipment') !== null ? `${data.getCheckRatio(c, 'shipment')!.toFixed(1)}%` : 'N/A',
      data.hasAbnormal(c) ? '是' : '否',
    ])
    // 每个区块一个 Sheet（sheet 名与模板导出略有差异：此处第三个是「③本期收款」
    // 而模板里是「③本期收款检查」—— 保持原样，不在本次收敛中「顺手统一」）
    const blockSheets: { key: BlockType; name: string }[] = [
      { key: 'block1', name: '①期后结转' },
      { key: 'block2', name: '②期末余额证据' },
      { key: 'block3', name: '③本期收款' },
      { key: 'block4', name: '④本期出库' },
    ]

    await exportMultiSheetData({
      sheets: [
        {
          sheetName: '公司汇总',
          rows: [summaryHeaders, ...summaryData],
          colWidths: [{ wch: 6 }, { wch: 10 }, { wch: 25 }, { wch: 8 }, { wch: 10 }, { wch: 10 }, { wch: 8 }],
        },
        ...blockSheets.map(({ key, name }) => {
          const cols = BLOCK_COLUMN_CONFIGS[key].columns
          const headers = ['公司名称', ...cols.map(c => c.label)]
          const rows: any[][] = []
          for (const company of data.companies.value) {
            for (const row of getBlockRows(company, key)) {
              rows.push([company.entity_name ?? '', ...cols.map(c => row[c.field] ?? '')])
            }
          }
          return {
            sheetName: name,
            rows: [headers, ...rows],
            colWidths: [{ wch: 20 }, ...cols.map(c => ({ wch: Math.max((c.width || 80) / 8, 10) }))],
          }
        }),
      ],
      fileName: 'D0-5合同负债及销售替代程序_数据导出.xlsx',
      applyStyles: false,
      successMessage: false,
    })
    ElMessage.success('数据已导出')
  } catch (e: any) {
    ElMessage.error('导出失败：' + (e?.message || '未知错误'))
  }
}

const showD01Dialog = ref(false)
const aiLoading = ref(false)

function handleAiFill() {
  if (!selectedCompany.value) return
  aiLoading.value = true
  try {
    const company = selectedCompany.value
    const entityName = company.entity_name || '该公司'
    const receiptRatio = data.getCheckRatio(company, 'receipt')
    const shipmentRatio = data.getCheckRatio(company, 'shipment')
    const status = data.getCompletionStatus(company)
    const hasAnomaly = data.hasAbnormal(company)

    // 区块统计
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

    // 生成审计说明
    const parts: string[] = []

    // 第一段：测试概况
    if (totalRows > 0) {
      parts.push(
        `对${entityName}执行替代程序，共检查 ${totalRows} 笔凭证/单据（期后结转 ${b1Count} 笔、期末余额证据 ${b2Count} 笔、本期收款 ${b3Count} 笔、本期出库 ${b4Count} 笔），完成度 ${status.completed}/4 区块。`
      )
    } else {
      parts.push(`对${entityName}执行替代程序，尚未录入检查数据。`)
    }

    // 第二段：检查比例
    if (receiptRatio !== null || shipmentRatio !== null) {
      const rPart = receiptRatio !== null ? `收款检查比例 ${receiptRatio.toFixed(1)}%` : '收款检查比例待计算'
      const sPart = shipmentRatio !== null ? `出库检查比例 ${shipmentRatio.toFixed(1)}%` : '出库检查比例待计算'
      parts.push(`${rPart}，${sPart}。`)
    }

    // 第三段：异常情况
    if (hasAnomaly) {
      parts.push(`检查中发现 ${abnormalRows} 笔异常项，需进一步核实原因并评估是否需要调整。`)
    } else if (totalRows > 0) {
      parts.push('检查中未发现异常事项。')
    }

    // 第四段：结论建议
    if (totalRows > 0 && !hasAnomaly && status.completed === 4) {
      parts.push('替代程序结果支持账面余额的合理性，未发现需要调整事项。')
    } else if (hasAnomaly) {
      parts.push('建议：对异常项扩大检查范围或追加审计程序，并与管理层确认相关事项。')
    }

    const generatedText = parts.join('')

    // 仅填充空白字段
    if (!company.conclusion) company.conclusion = {}
    if (!company.conclusion.audit_note) {
      company.conclusion.audit_note = generatedText
      data.isDirty.value = true
    } else {
      // 已有内容，追加到末尾
      company.conclusion.audit_note += '\n' + generatedText
      data.isDirty.value = true
    }

    // 自动推荐结论类型
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

// 暴露给父组件通过 ref 调用（页面级工具栏转发）
defineExpose({
  handleExportTemplate,
  handleExportData,
  handleImport: handleImportExcel,
  handleImportClick: handleImportExcel,
  handleDownloadImportTemplate: handleExportTemplate,
})
</script>

<style scoped>
.gt-confirmation-alternative-d05 {
  padding: 8px 0;
}

.gt-confirmation-alternative-d05__legacy-notice {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-d05__header-tip {
  margin-bottom: 12px;
}

.gt-confirmation-alternative-d05__detail {
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

.ratio-display {
  font-weight: 700;
  color: var(--el-color-primary);
  font-size: 14px;
}

</style>
