<script setup lang="ts">
/**
 * E1TabKeyPersonFlow.vue — E1-32 董监高关键岗位及其他关联方资金流水核查
 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { MagicStick, Paperclip } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useE1KeyPersonFlow,
  type YesNo,
  type KeyPersonTxnRow,
  type E31SeedMode,
} from '../composables/useE1KeyPersonFlow'
import { useE1AiGenerate } from '../composables/useE1AiGenerate'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import E1KeyPersonFlowOcrConfirmDialog, {
  type KeyPersonOcrFields,
} from './E1KeyPersonFlowOcrConfirmDialog.vue'
import E1IpoSheetChrome from './E1IpoSheetChrome.vue'
import http from '@/utils/http'
import { amountFormatter, amountParser } from '../composables/wpAmountInput'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const options: UseE1BaseOptions = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
}

const {
  pack,
  activePerson,
  activeRows,
  auditNote,
  auditConclusion,
  isLoading,
  isApplicable,
  totals,
  allHitCount,
  setApplicable,
  setActivePerson,
  addPerson,
  removePerson,
  updatePersonMeta,
  addRow,
  removeRow,
  updateRow,
  mergeOcrLines,
  seedFromE31,
  previewSeedFromE31,
  saveNote,
  saveConclusion,
  hydrate,
} = useE1KeyPersonFlow(options)

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)
const sheetCode = computed(() => 'E1-32')
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

const rowFilter = ref<'all' | 'hit' | 'anomaly'>('all')
const page = ref(1)
const pageSize = ref(50)
const ocrVisible = ref(false)
const ocrLoading = ref(false)
const ocrFields = ref<Partial<KeyPersonOcrFields>>({})
const ocrConfidence = ref<number | undefined>()
const ocrPreview = ref('')
const ocrFileName = ref('')
const ocrAttachmentId = ref('')
const ocrSkippedCount = ref(0)

const lastOcrHint = computed(() => {
  const jobs = pack.value.ocrJobs || []
  if (!jobs.length) return ''
  const j = jobs[jobs.length - 1]
  const when = j.at ? j.at.slice(0, 16).replace('T', ' ') : ''
  return `最近OCR：${j.fileName || '未命名'} · ${j.lineCount}笔`
    + (j.skippedCount ? `/跳过${j.skippedCount}` : '')
    + (when ? ` · ${when}` : '')
})

const ynOptions = [
  { label: '是', value: '是' },
  { label: '否', value: '否' },
]

const conclusionTemplates = [
  {
    value: 'A',
    label: 'A—未见异常',
    text: '已取得董监高及关键岗位人员银行流水并核查，未发现与被审计单位、客户/供应商或其他共同交易对手的异常大额资金往来，未见关联方资金占用或舞弊迹象。',
  },
  {
    value: 'B',
    label: 'B—异常已说明',
    text: '除已识别并记录的异常或关联往来事项外，关键人员个人流水核查未见其他重大异常；相关交易背景合理或已提请进一步核查。',
  },
  {
    value: 'C',
    label: 'C—需关注/扩大',
    text: '因存在与被审计单位或客商的大额异常往来、其他共同交易对手往来等情形，已扩大核查范围，结果见审计说明；提示项目组关注关联方占用及体外循环风险。',
  },
]

function isHitRow(r: KeyPersonTxnRow): boolean {
  return r.isAuditee === '是'
    || r.isCustomerOrSupplier === '是'
    || r.isCommonCounterparty === '是'
    || !!String(r.otherAnomaly || '').trim()
}

const filteredRows = computed(() => {
  let rows = activeRows.value
  if (rowFilter.value === 'hit') {
    rows = rows.filter(r =>
      r.isAuditee === '是' || r.isCustomerOrSupplier === '是' || r.isCommonCounterparty === '是',
    )
  } else if (rowFilter.value === 'anomaly') {
    rows = rows.filter(r => !!String(r.otherAnomaly || '').trim() || isHitRow(r))
  }
  return rows
})

const pagedRows = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredRows.value.slice(start, start + pageSize.value)
})

watch(rowFilter, () => { page.value = 1 })
watch(() => pack.value.activePersonId, () => { page.value = 1 })

function rowClass({ row }: { row: KeyPersonTxnRow }): string {
  return isHitRow(row) ? 'e1-kp-hit' : ''
}

function aiContext(): Record<string, unknown> {
  return {
    底稿: 'E1-32 董监高关键岗位流水核查',
    人员数: pack.value.persons.length,
    当前人员: activePerson.value?.name,
    职位: activePerson.value?.position,
    当前流水笔数: totals.value.rowCount,
    收入合计: totals.value.income,
    支出合计: totals.value.expense,
    命中笔数: totals.value.hitCount,
    全部命中: allHitCount.value,
  }
}

function sanitize(raw: string, kind: 'note' | 'conclusion'): string {
  let t = String(raw || '').trim()
  if (kind === 'note') {
    t = t.replace(/^\*{0,2}审计说明\*{0,2}\s*/i, '')
    t = t.replace(/\n+\s*\*{0,2}审计结论\*{0,2}.*$/s, '')
  } else {
    t = t.replace(/^\*{0,2}审计结论\*{0,2}\s*/i, '')
    t = t.replace(/^[ABC]、\s*/i, '')
  }
  return t.trim()
}

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-32-audit-note',
    prompt: [
      '你是注册会计师助理。请撰写 E1-32「审计说明」，只描述关键人员流水核查过程与发现，不要写审计结论。',
      '应概括：核查人员范围与授权、OCR/取数、与被审计单位及客商往来命中情况、异常背景。',
      '严禁 markdown；约 150～280 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditNote.value,
    confirmTitle: 'AI 生成 · 审计说明',
  })
  if (text) saveNote(sanitize(text, 'note'))
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-32-audit-conclusion',
    prompt: [
      '你是注册会计师助理。请撰写 E1-32「审计结论」。',
      '可参考：A 未见异常；B 异常已说明；C 需关注/扩大。',
      '只写结论；严禁 markdown；约 60～150 字。',
    ].join(''),
    context: aiContext(),
    existingContent: auditConclusion.value,
    confirmTitle: 'AI 生成 · 审计结论',
  })
  if (text) saveConclusion(sanitize(text, 'conclusion'))
}

function applyConclusionTemplate(code: string): void {
  const t = conclusionTemplates.find(i => i.value === code)
  if (t) saveConclusion(t.text)
}

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
    hydrate()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

async function runOcr(file: File): Promise<boolean> {
  if (props.isReadonly) return false
  ocrLoading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const { data } = await http.post(`/api/workpapers/${props.wpId}/e1/statement-ocr`, form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    })
    const extracted = data?.extracted_fields || {}
    const lines = Array.isArray(extracted.lines) ? extracted.lines : []
    if (!lines.length) ElMessage.warning('OCR 完成，未识别到流水明细')
    ocrFields.value = {
      name: activePerson.value?.name || '',
      position: activePerson.value?.position || '',
      bank: extracted.bank || '',
      accountNo: extracted.accountNo || '',
      lines: lines.map((r: any) => ({
        date: r.date || '',
        summary: r.summary || '',
        counterparty: r.counterparty || '',
        counterpartyAccount: r.counterpartyAccount || '',
        amount: Number(r.amount) || 0,
        direction: r.direction || '',
        cardNo: r.cardNo || '',
        cardType: r.cardType || '',
      })),
    }
    ocrConfidence.value = typeof data?.confidence === 'number' ? data.confidence : undefined
    ocrPreview.value = String(data?.ocr_text || '').slice(0, 2000)
    ocrFileName.value = file.name
    ocrAttachmentId.value = String(data?.attachment_id || '')
    ocrSkippedCount.value = Number(data?.skipped_line_count ?? extracted.skippedLineCount ?? 0) || 0
    ocrVisible.value = true
  } catch {
    ElMessage.error('个人流水 OCR 识别失败')
  } finally {
    ocrLoading.value = false
  }
  return false
}

function onOcrConfirm(fields: KeyPersonOcrFields): void {
  const confirmed = fields.lines?.length || 0
  const n = mergeOcrLines(fields.lines, {
    bank: fields.bank,
    accountNo: fields.accountNo,
    name: fields.name,
    position: fields.position,
    ocrJob: {
      fileName: ocrFileName.value,
      attachmentId: ocrAttachmentId.value || undefined,
      lineCount: confirmed,
      skippedCount: ocrSkippedCount.value,
      confidence: ocrConfidence.value || 0,
      bank: fields.bank,
      accountNo: fields.accountNo,
      personName: fields.name,
    },
  })
  ElMessage.success(`已回填 ${n} 笔至「${fields.name || activePerson.value?.name || '当前人员'}」`)
}

async function onSeedE31(mode: E31SeedMode = 'append'): Promise<void> {
  const preview = previewSeedFromE31()
  if (!preview || !preview.count) {
    ElMessage.warning('E1-31 无第三方/不一致/大额未匹配抽样可导入')
    return
  }
  try {
    await ElMessageBox.confirm(
      `预览：可疑 ${preview.count} 笔`
      + `（第三方 ${preview.third} / 不一致 ${preview.inconsistent} / 大额未匹配 ${preview.largeUnmatched}）`
      + ` → 当前人员「${activePerson.value?.name || '未命名'}」。\n`
      + (mode === 'replace'
        ? '覆盖：先清除当前人员来源为 E1-31 的行，再写入本次种子。'
        : '追加：在现有流水后增量写入。')
      + '\n是否继续？',
      mode === 'replace' ? '从 E1-31 覆盖导入' : '从 E1-31 追加导入',
      { type: 'warning', confirmButtonText: '执行', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  const n = seedFromE31(mode)
  if (!n) {
    ElMessage.warning('E1-31 无第三方/不一致/大额未匹配抽样可导入')
    return
  }
  ElMessage.success(`已${mode === 'replace' ? '覆盖' : '追加'}导入 ${n} 笔可疑往来`)
}

async function onAddPerson(): Promise<void> {
  if (props.isReadonly) return
  try {
    const { value } = await ElMessageBox.prompt('请输入姓名', '添加核查对象', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '姓名',
    })
    addPerson(String(value || '').trim(), '')
  } catch {
    /* cancel */
  }
}

async function onRemovePerson(): Promise<void> {
  if (props.isReadonly || !activePerson.value) return
  try {
    await ElMessageBox.confirm(
      `确认删除「${activePerson.value.name || '未命名'}」及其全部流水？`,
      '删除人员',
      { type: 'warning' },
    )
    removePerson(activePerson.value.id)
  } catch {
    /* cancel */
  }
}
</script>

<template>
  <div class="e1-tab-keyperson-flow">
    <E1IpoSheetChrome
      title="关键岗位流水核查 (E1-32)"
      :is-applicable="isApplicable"
      :is-readonly="isReadonly"
      :is-loading="isLoading"
      :project-id="projectId"
      :index-chips="['wp:E1-31', 'wp:D4-32']"
      :is-importing="isImporting"
      @update:applicable="setApplicable"
      @export-template="exportTemplate"
      @export-data="exportData"
      @import="handleImport"
    >
      <template #guidance>
        <details class="guidance-details">
          <summary>📋 编制提示</summary>
          <div class="guidance-content">
            <p>1. 按人编制：先添加董监高/关键岗位人员，填写姓名、职位。</p>
            <p>2. 上传个人银行流水 OCR，确认后回填账号/日期/摘要/收付/对方等客观列。</p>
            <p>3. 人工判断交易背景，并勾选三维对手方（被审计单位 / 客商 / 共同其他对手）；异常写入「其他异常」。</p>
            <p>4. 所内核查工具能力由平台 OCR 替代；可与 E1-31、D4 资金流水交叉索引。</p>
          </div>
        </details>
      </template>

      <template #goal>
        <el-alert type="info" :closable="false" class="mb8" title="一、审计目标">
          <p>所有应当记录的货币资金均已记录，所有应当包括在财务报表中的相关披露均已包括。</p>
        </el-alert>
      </template>

      <template #status>
        <el-tag v-if="isApplicable && allHitCount" size="small" type="danger">命中 {{ allHitCount }}</el-tag>
      </template>

      <template #actions>
        <el-upload
          :show-file-list="false"
          accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
          :before-upload="runOcr"
          :disabled="isReadonly || !isApplicable || ocrLoading"
        >
          <el-button size="small" type="primary" plain :loading="ocrLoading" :disabled="isReadonly || !isApplicable">
            <el-icon><Paperclip /></el-icon> 流水 OCR
          </el-button>
        </el-upload>
        <el-dropdown size="small" trigger="click" :disabled="isReadonly || !isApplicable">
          <el-button size="small" :disabled="isReadonly || !isApplicable">从 E1-31 导入可疑 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="onSeedE31('append')">追加导入</el-dropdown-item>
              <el-dropdown-item @click="onSeedE31('replace')">覆盖 E1-31 种子行</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-tag v-if="lastOcrHint" size="small" type="info" effect="plain">{{ lastOcrHint }}</el-tag>
      </template>

        <el-card shadow="never" class="section-card">
          <div class="person-bar">
            <el-radio-group
              :model-value="pack.activePersonId"
              size="small"
              @change="(v: string | number | boolean | undefined) => setActivePerson(String(v))"
            >
              <el-radio-button v-for="p in pack.persons" :key="p.id" :label="p.id">
                {{ p.name || '未命名' }}{{ p.position ? `·${p.position}` : '' }}
                <span v-if="p.rows.length" class="cnt">({{ p.rows.length }})</span>
              </el-radio-button>
            </el-radio-group>
            <el-button size="small" :disabled="isReadonly" @click="onAddPerson">+ 人员</el-button>
            <el-button size="small" type="danger" plain :disabled="isReadonly || pack.persons.length <= 1" @click="onRemovePerson">删除当前</el-button>
          </div>
          <el-form inline size="small" class="person-meta">
            <el-form-item label="姓名">
              <el-input
                :model-value="activePerson?.name || ''"
                :disabled="isReadonly"
                style="width: 160px"
                @change="(v: string) => updatePersonMeta('name', v)"
              />
            </el-form-item>
            <el-form-item label="职位">
              <el-input
                :model-value="activePerson?.position || ''"
                :disabled="isReadonly"
                style="width: 160px"
                @change="(v: string) => updatePersonMeta('position', v)"
              />
            </el-form-item>
            <el-form-item>
              <el-radio-group v-model="rowFilter" size="small">
                <el-radio-button label="all">全部</el-radio-button>
                <el-radio-button label="hit">三维命中</el-radio-button>
                <el-radio-button label="anomaly">异常</el-radio-button>
              </el-radio-group>
            </el-form-item>
            <el-form-item>
              <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow()">+ 流水行</el-button>
            </el-form-item>
          </el-form>
        </el-card>

        <div class="table-scroll">
          <el-table :data="pagedRows" border size="small" max-height="520" :row-class-name="rowClass">
            <el-table-column type="index" label="序号" width="50" fixed />
            <el-table-column label="账号" width="120" fixed>
              <template #default="{ row }">
                <el-input :model-value="row.accountNo" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'accountNo', v)" />
              </template>
            </el-table-column>
            <el-table-column label="开户行" width="110">
              <template #default="{ row }">
                <el-input :model-value="row.bank" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'bank', v)" />
              </template>
            </el-table-column>
            <el-table-column label="账号/卡号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.cardNo" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'cardNo', v)" />
              </template>
            </el-table-column>
            <el-table-column label="卡片类型" width="90">
              <template #default="{ row }">
                <el-input :model-value="row.cardType" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'cardType', v)" />
              </template>
            </el-table-column>
            <el-table-column label="交易日期" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.transDate" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'transDate', v)" />
              </template>
            </el-table-column>
            <el-table-column label="币种" width="70">
              <template #default="{ row }">
                <el-input :model-value="row.currency" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'currency', v)" />
              </template>
            </el-table-column>
            <el-table-column label="摘要" min-width="100">
              <template #default="{ row }">
                <el-input :model-value="row.summary" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'summary', v)" />
              </template>
            </el-table-column>
            <el-table-column label="收入金额" width="110" align="right">
              <template #default="{ row }">
                <el-input-number :model-value="row.income" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                  @change="(v: number) => updateRow(row.id, 'income', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column label="支出金额" width="110" align="right">
              <template #default="{ row }">
                <el-input-number :model-value="row.expense" :disabled="isReadonly" :controls="false" :precision="2" :formatter="amountFormatter" :parser="amountParser" size="small" style="width: 100%"
                  @change="(v: number) => updateRow(row.id, 'expense', v ?? 0)" />
              </template>
            </el-table-column>
            <el-table-column label="对方户名" min-width="110">
              <template #default="{ row }">
                <el-input :model-value="row.counterpartyName" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'counterpartyName', v)" />
              </template>
            </el-table-column>
            <el-table-column label="对方账号" width="120">
              <template #default="{ row }">
                <el-input :model-value="row.counterpartyAccount" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'counterpartyAccount', v)" />
              </template>
            </el-table-column>
            <el-table-column label="交易背景" min-width="120">
              <template #default="{ row }">
                <el-input :model-value="row.transBackground" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'transBackground', v)" />
              </template>
            </el-table-column>
            <el-table-column label="对手=被审计单位" width="120" class-name="emphasis-col">
              <template #default="{ row }">
                <el-select :model-value="row.isAuditee" :disabled="isReadonly" size="small" clearable
                  @change="(v: string) => updateRow(row.id, 'isAuditee', (v || '') as YesNo)">
                  <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="对手=客商" width="100" class-name="emphasis-col">
              <template #default="{ row }">
                <el-select :model-value="row.isCustomerOrSupplier" :disabled="isReadonly" size="small" clearable
                  @change="(v: string) => updateRow(row.id, 'isCustomerOrSupplier', (v || '') as YesNo)">
                  <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="共同其他对手" width="110" class-name="emphasis-col">
              <template #default="{ row }">
                <el-select :model-value="row.isCommonCounterparty" :disabled="isReadonly" size="small" clearable
                  @change="(v: string) => updateRow(row.id, 'isCommonCounterparty', (v || '') as YesNo)">
                  <el-option v-for="o in ynOptions" :key="o.value" :label="o.label" :value="o.value" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="其他异常" min-width="100">
              <template #default="{ row }">
                <el-input :model-value="row.otherAnomaly" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'otherAnomaly', v)" />
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="90">
              <template #default="{ row }">
                <el-input :model-value="row.remark" :disabled="isReadonly" size="small"
                  @change="(v: string) => updateRow(row.id, 'remark', v)" />
              </template>
            </el-table-column>
            <el-table-column width="50" fixed="right">
              <template #default="{ row }">
                <el-button type="danger" text size="small" :disabled="isReadonly" @click="removeRow(row.id)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <div class="pager-row">
          <el-pagination
            v-model:current-page="page"
            v-model:page-size="pageSize"
            :total="filteredRows.length"
            :page-sizes="[30, 50, 100, 200]"
            layout="total, sizes, prev, pager, next"
            small
            background
          />
        </div>
        <p class="sum-line">
          合计 · 收入 {{ displayPrefs.fmtAmount(totals.income) }} / 支出 {{ displayPrefs.fmtAmount(totals.expense) }}
          · 当前命中 {{ totals.hitCount }} / {{ totals.rowCount }}
        </p>

        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>三、审计说明</span>
              <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-32-audit-note')" @click="generateAuditNote">
                <el-icon><MagicStick /></el-icon> AI辅助
              </el-button>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 4 }"
            placeholder="说明核查人员范围、授权取数、命中往来及异常背景…"
            @update:model-value="(v: string) => { if (!isReadonly) auditNote = v }"
            @change="(v: string) => saveNote(v)"
          />
        </el-card>

        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header">
              <span>四、审计结论</span>
              <div class="header-actions">
                <el-select size="small" placeholder="结论模板" style="width: 140px" :disabled="isReadonly" @change="applyConclusionTemplate">
                  <el-option v-for="t in conclusionTemplates" :key="t.value" :label="t.label" :value="t.value" />
                </el-select>
                <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="isGenerating('e1-32-audit-conclusion')" @click="generateAuditConclusion">
                  <el-icon><MagicStick /></el-icon> AI辅助
                </el-button>
              </div>
            </div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论…"
            @update:model-value="(v: string) => { if (!isReadonly) auditConclusion = v }"
            @change="(v: string) => saveConclusion(v)"
          />
        </el-card>
    </E1IpoSheetChrome>

    <E1KeyPersonFlowOcrConfirmDialog
      v-model="ocrVisible"
      :fields="ocrFields"
      :confidence="ocrConfidence"
      :ocr-preview="ocrPreview"
      :file-name="ocrFileName"
      @confirm="onOcrConfirm"
    />
  </div>
</template>

<style scoped>
.e1-tab-keyperson-flow { padding: 12px 0; }
.guidance-details {
  margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff;
  border-radius: 4px; padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.mb8 { margin-bottom: 8px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 8px; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right, .card-header, .header-actions, .person-bar {
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.person-bar { margin-bottom: 8px; }
.person-meta { margin-bottom: 0; }
.cnt { color: #909399; font-size: 12px; }
.chip-wrap { display: inline-flex; }
.not-applicable { padding: 48px 0; text-align: center; }
.section-card { margin-bottom: 12px; }
.table-scroll { overflow-x: auto; margin-bottom: 8px; }
.pager-row { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.sum-line { font-size: 13px; color: #606266; margin: 0 0 12px; }
.audit-note-card { margin-top: 12px; }
.card-header { font-weight: 500; width: 100%; justify-content: space-between; }
:deep(.emphasis-col .cell) { color: #c45656; font-weight: 600; }
:deep(.e1-kp-hit) { background-color: #fef0f0 !important; }
</style>
