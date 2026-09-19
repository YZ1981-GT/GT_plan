<!--
  K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表

  对齐致同源模板：审计目标 + 审计过程（前10名）+ 查验汇总表 + 审计说明 + 结论
  增强：期末/账面价值公式、K1-2 导入前10、合计行、占比、K1-12 联动
-->
<template>
  <div class="k1-audit-sheet" data-testid="k1-large-amount">
    <details class="compile-hint open-hint">
      <summary>编制提示</summary>
      <ul>
        <li>选取期末余额前 10 名大额其他应收款（不含合并范围内关联方），通过函证、核对支持性证据确认存在性。</li>
        <li>期末未审余额 = 期初 + 借方 − 贷方（灰底自动）；账面价值 = 期末未审 − 坏账准备。</li>
        <li>可从 K1-2 一键导入前 10 名；期后收款凭证检查索引 K1-12；关注未识别关联方（结合 B19）。</li>
      </ul>
    </details>

    <div class="section-head">
      <h3 class="sheet-title">K1-5 大额其他应收款情况分析表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
        <el-button v-if="!isReadonly" size="small" @click="onImportTop">从 K1-2 导入前10</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :loading="postPaymentLoading"
          @click="onImportPostPayment"
        >取期后回款</el-button>
        <el-button
          v-if="!isReadonly && registry.length"
          size="small"
          type="primary"
          plain
          @click="onApplyB19Match"
        >B19 自动比对</el-button>
        <el-button
          v-if="registry.length"
          size="small"
          link
          type="primary"
          :loading="jumpingToB19"
          @click="goToB19RelatedPartyList"
        >前往 B19-1</el-button>
        <el-button v-if="!isReadonly && dataRows.length < 10" size="small" @click="addRow()">＋ 新增</el-button>
        <el-button size="small" @click="onExportTemplate">导出模板</el-button>
        <el-button size="small" @click="onExportData">导出数据</el-button>
        <el-upload v-if="!isReadonly" :show-file-list="false" accept=".xlsx,.xls" :auto-upload="false" :on-change="onImportChange">
          <el-button size="small" :loading="importing">导入 Excel</el-button>
        </el-upload>
        <el-tag size="small" type="info">{{ dataRows.length }} / 10 行</el-tag>
        <el-tag v-if="isOverTopN" size="small" type="warning">超出前10限制</el-tag>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应收款、坏账准备是存在的，且已记录于恰当的账户；</li>
        <li><b>计价和分摊：</b>其他应收款、坏账准备以恰当的金额包括在财务报表中，相关计价或分摊调整已恰当记录，披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <el-alert type="warning" :closable="false" class="process-hint">
      <template #title>
        <span>二、审计过程：选择前 10 名大额其他应收款余额，通过函证、与高管及相关人员核对，检查支持性证据，确定其存在性，识别是否存在未识别的关联方。</span>
      </template>
    </el-alert>

    <el-alert
      v-if="b19SuspectRows.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="b19-alert"
    >
      <template #title>
        <span>
          B19 清单匹配 {{ b19SuspectRows.length }} 户债务人但未勾选关联方：
          {{ b19SuspectRows.slice(0, 3).map((r) => r.debtorName).join('、') }}{{ b19SuspectRows.length > 3 ? '…' : '' }}
        </span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          style="margin-left: 8px"
          @click="onApplyB19Match"
        >自动标记关联方</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="b19MissingFromTable.length > 0 && dataRows.length > 0"
      type="info"
      :closable="false"
      show-icon
      class="b19-alert"
    >
      <template #title>
        <span>
          B19 清单中有 {{ b19MissingFromTable.length }} 个关联方未出现在本表前10（可能余额未进前十或非其他应收款）：
          {{ b19MissingFromTable.slice(0, 4).join('、') }}{{ b19MissingFromTable.length > 4 ? '…' : '' }}
        </span>
      </template>
    </el-alert>

    <el-alert
      v-if="summary.detailTotal > 0"
      type="info"
      :closable="false"
      class="summary-bar"
      :title="`前${dataRows.length}名合计占 K1-2 总额 ${fmtPct(summary.topTotalProportion)}（${fmtAmt(summary.endUnaudited)} / ${fmtAmt(summary.detailTotal)}）`"
    />

    <el-alert
      v-if="deeplinkHint"
      type="info"
      :closable="false"
      show-icon
      class="deeplink-bar"
    >
      <template #title>
        <span>{{ deeplinkHint }}</span>
        <el-button size="small" link type="primary" style="margin-left: 8px" @click="clearDeeplink">清除筛选</el-button>
      </template>
    </el-alert>

    <div v-if="dataRows.length" class="filter-bar">
      <el-input v-model="searchFilter" placeholder="搜索债务人..." size="small" clearable class="search-input" />
      <span v-if="searchFilter.trim()" class="filter-hint">显示 {{ filteredDataRows.length }} / {{ dataRows.length }} 户</span>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">（二）前 10 名查验汇总表（不含合并范围内关联方）</span></template>
      <el-table
        ref="tableRef"
        :data="filteredDisplayRows"
        row-key="id"
        border
        size="small"
        :max-height="460"
        class="audit-table"
        :row-class-name="rowClassName"
      >
        <el-table-column label="序号" width="52" align="center">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)">—</span>
            <span v-else>{{ row.seq }}</span>
          </template>
        </el-table-column>
        <el-table-column label="债务人名称" min-width="156" fixed>
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-label">{{ row.debtorName }}</span>
            <div v-else class="debtor-cell">
              <el-input
                :model-value="row.debtorName"
                size="small"
                :disabled="isReadonly"
                @change="(v: string) => updateCell(row.id, 'debtorName', v)"
              />
              <el-tooltip v-if="row.debtorName.trim()" content="跳转 K1-2 明细表">
                <el-button
                  link
                  type="primary"
                  size="small"
                  class="jump-btn"
                  @click="navigateToDetail(row)"
                >→</el-button>
              </el-tooltip>
              <el-tag v-if="isB19Suspect(row)" size="small" type="danger" class="b19-tag">B19</el-tag>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="100" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.openingBalance) }}</span>
            <el-input-number
              v-else
              :model-value="row.openingBalance"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'openingBalance', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="本期借方发生额" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.periodDebit) }}</span>
            <el-input-number
              v-else
              :model-value="row.periodDebit"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'periodDebit', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="本期贷方发生额" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.periodCredit) }}</span>
            <el-input-number
              v-else
              :model-value="row.periodCredit"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'periodCredit', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="期末未审余额" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="期末未审 = 期初 + 借方 − 贷方">{{ fmtAmt(row.endUnaudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减:坏账准备" min-width="105" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.provision) }}</span>
            <el-input-number
              v-else
              :model-value="row.provision"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'provision', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column label="账面价值" min-width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <span class="formula-cell" title="账面价值 = 期末未审 − 坏账准备">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占比" width="72" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="占比 = 单项期末未审 / K1-2 总额">{{ fmtPct(row.proportion) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发生时间及账龄" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.aging"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'aging', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="经济业务说明" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.businessDesc"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'businessDesc', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="关联方" width="72" align="center">
          <template #default="{ row }">
            <el-tooltip
              v-if="!isMetaRow(row) && isB19Suspect(row)"
              content="B19 清单已匹配，建议勾选关联方"
            >
              <el-checkbox
                :model-value="row.isRelated"
                :disabled="isReadonly"
                @change="(v: boolean) => updateCell(row.id, 'isRelated', v)"
              />
            </el-tooltip>
            <el-checkbox
              v-else-if="!isMetaRow(row)"
              :model-value="row.isRelated"
              :disabled="isReadonly"
              @change="(v: boolean) => updateCell(row.id, 'isRelated', v)"
            />
            <span v-else-if="summary.relatedCount">标记 {{ summary.relatedCount }} 户</span>
          </template>
        </el-table-column>
        <el-table-column label="协议或合同索引" min-width="115">
          <template #default="{ row }">
            <el-input
              v-if="!isMetaRow(row)"
              :model-value="row.contractIndex"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => updateCell(row.id, 'contractIndex', v)"
            />
          </template>
        </el-table-column>
        <el-table-column label="期后收款金额" min-width="110" align="right">
          <template #default="{ row }">
            <span v-if="isMetaRow(row)" class="subtotal-val">{{ fmtAmt(row.postCollection) }}</span>
            <el-input-number
              v-else
              :model-value="row.postCollection"
              :controls="false"
              size="small"
              class="amt"
              :disabled="isReadonly"
              @update:model-value="(v: number) => updateCell(row.id, 'postCollection', v ?? 0)"
            />
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!isMetaRow(row)"
              size="small"
              type="danger"
              link
              @click="removeRow(row.id)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-summary">
        账面价值合计 {{ fmtAmt(summary.bookValue) }} ·
        期后收款 {{ fmtAmt(summary.postCollection) }} ·
        关联方标记 {{ summary.relatedCount }} 户
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、审计说明</span>
          <el-button v-if="!isReadonly" size="small" type="primary" link :loading="aiLoading" @click="onAiAuditNote">AI 生成</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="1. 针对期后收款的凭证检查，详见 K1-12；2. 说明大额款项核查情况与识别的未识别关联方"
        @change="persistTextFields()"
      />
    </el-card>

    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-select
        v-model="conclusionOption"
        :disabled="isReadonly"
        size="small"
        class="concl-select"
        placeholder="选择结论模板"
        @change="onConclusionOption"
      >
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述调整事项外，其余未见异常" value="B" />
        <el-option label="C、存在重大未调整事项，不可确认" value="C" />
      </el-select>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="形成审计结论..."
        @change="persistTextFields()"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表 */
import { computed, inject, ref, toRef, onMounted, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import { getWpIndex } from '@/services/workpaperApi'
import {
  useK1LargeAmountSheet,
  type K1LargeAmountSheetRow,
} from '../../composables/useK1LargeAmountSheet'
import {
  K1RowNavigationKey,
  applyK1IncomingFocus,
  buildK1DeeplinkHint,
  type K1NavSheet,
} from '../../composables/useK1RowNavigation'
import { K1_CONCLUSION_TEMPLATES } from '../../composables/useK1AuditRows'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import type { UploadFile } from 'element-plus'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  relatedParties?: string[]
  bsDate?: string
  year?: number
}>()
const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
const router = useRouter()
const jumpingToB19 = ref(false)
const searchFilter = ref('')
const deeplinkHint = ref('')
const tableRef = ref<InstanceType<typeof ElTable>>()

const registryParties = computed(() => props.relatedParties ?? [])

const sheet = useK1LargeAmountSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  relatedParties: registryParties,
  projectId: toRef(props, 'projectId'),
  bsDate: computed(() => props.bsDate || ''),
  year: computed(() => props.year),
  onSave: (itemId, payload) => {
    props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: payload.remark })
    emit('save', itemId, payload)
  },
})

const {
  auditNote,
  conclusion,
  conclusionOption,
  dataRows,
  displayRows,
  summary,
  isOverTopN,
  isMetaRow,
  addRow,
  removeRow,
  updateCell,
  importTopFromDetail,
  importPostPaymentFromLedger,
  postPaymentLoading,
  persistTextFields,
  registry,
  b19SuspectRows,
  b19MissingFromTable,
  isB19Suspect,
  applyB19Match,
} = sheet

const { isImporting: importing, exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })
const { loading: aiLoading, generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))

const filteredDataRows = computed(() => {
  const keyword = searchFilter.value.trim().toLowerCase()
  if (!keyword) return dataRows.value
  return dataRows.value.filter((r) => String(r.debtorName ?? '').toLowerCase().includes(keyword))
})

const filteredDisplayRows = computed(() => {
  if (!searchFilter.value.trim()) return displayRows.value
  const rows = filteredDataRows.value
  if (!rows.length) return rows
  const t = summary.value
  const endUnaudited = rows.reduce((s, r) => s + r.endUnaudited, 0)
  return [
    ...rows,
    {
      id: '__subtotal__',
      seq: 0,
      debtorName: '合计',
      openingBalance: rows.reduce((s, r) => s + r.openingBalance, 0),
      periodDebit: rows.reduce((s, r) => s + r.periodDebit, 0),
      periodCredit: rows.reduce((s, r) => s + r.periodCredit, 0),
      endUnaudited,
      provision: rows.reduce((s, r) => s + r.provision, 0),
      bookValue: rows.reduce((s, r) => s + r.bookValue, 0),
      aging: '',
      businessDesc: '',
      isRelated: false,
      contractIndex: '',
      postCollection: rows.reduce((s, r) => s + r.postCollection, 0),
      proportion: t.detailTotal > 0 ? endUnaudited / t.detailTotal : null,
      sourceRowId: '',
    } as K1LargeAmountSheetRow,
  ]
})

onMounted(() => {
  applyIncomingFocus()
})

function applyIncomingFocus(): void {
  applyK1IncomingFocus({
    sheet: 'K1-5',
    k1Nav,
    rows: dataRows.value,
    nameOf: (r) => (r as K1LargeAmountSheetRow).debtorName,
    onResolved: (resolved, focus) => {
      searchFilter.value = resolved.counterparty
      deeplinkHint.value = buildK1DeeplinkHint(focus, resolved.counterparty)
      if (resolved.rowId) {
        k1Nav?.focusRow(resolved.rowId)
        scrollToRow(resolved.rowId)
      }
    },
  })
}

function scrollToRow(rowId: string): void {
  if (!rowId) return
  nextTick(() => {
    const root = tableRef.value?.$el as HTMLElement | undefined
    const rowEl = root?.querySelector(`tr[data-row-key="${rowId}"]`) as HTMLElement | null
    rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function clearDeeplink(): void {
  searchFilter.value = ''
  deeplinkHint.value = ''
}

function navigateToDetail(row: K1LargeAmountSheetRow) {
  const name = row.debtorName.trim()
  if (!name) {
    ElMessage.warning('请先填写债务人名称')
    return
  }
  if (k1Nav) {
    k1Nav.navigateToRow({
      sheet: 'K1-2',
      rowId: row.sourceRowId || undefined,
      counterparty: name,
      sourceSheet: 'K1-5',
    })
    return
  }
  emit('navigate-sheet', 'K1-2 明细表')
}

function onApplyB19Match() {
  if (!registry.value.length) {
    ElMessage.warning('B19 关联方清单为空，请先在 B19-1 维护')
    return
  }
  const count = applyB19Match()
  if (!count) {
    ElMessage.info('未发现 B19 匹配且未标记的关联方行')
    return
  }
  ElMessage.success(`已自动标记 ${count} 户 B19 关联方`)
}

async function goToB19RelatedPartyList() {
  if (!props.projectId || jumpingToB19.value) return
  jumpingToB19.value = true
  try {
    const index = await getWpIndex(props.projectId)
    const b19 = index.find((i) => i.wp_code === 'B19')
    if (b19?.id) {
      await router.push({
        name: 'WorkpaperEditor',
        params: { projectId: props.projectId, wpId: b19.id },
        query: { sheet: 'B19识别关联方程序表', view: 'B19-1' },
      })
      return
    }
    ElMessage.warning('当前项目未找到 B19 识别关联方底稿，请先在底稿目录中启用')
  } catch {
    ElMessage.warning('无法打开 B19 关联方清单')
  } finally {
    jumpingToB19.value = false
  }
}

function onImportTop() {
  const r = importTopFromDetail(true)
  if (!r.imported) {
    ElMessage.warning('K1-2 明细为空或无可导入的大额户')
  } else {
    const extra = r.skippedRelated ? `，已排除关联方 ${r.skippedRelated} 户` : ''
    ElMessage.success(`已导入前 ${r.imported} 名大额户${extra}`)
  }
}

async function onImportPostPayment() {
  await importPostPaymentFromLedger()
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) {
    conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  }
  persistTextFields()
}

function rowClassName({ row }: { row: K1LargeAmountSheetRow }) {
  if (isMetaRow(row)) return 'row-subtotal'
  const parts: string[] = []
  const hl = k1Nav?.rowHighlightClass(row.id)
  if (hl) parts.push(hl)
  if (row.isRelated) parts.push('row-related')
  else if (isB19Suspect(row)) parts.push('row-b19-suspect')
  else if ((row.proportion ?? 0) >= 0.1) parts.push('row-large')
  return parts.join(' ')
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(v: number | null | undefined): string {
  if (v == null) return '-'
  return (Number(v) * 100).toFixed(2) + '%'
}

function handleReview() { openReviewDialog('K1-5-large-amount') }

function onExportTemplate() { exportTemplate('K1-5') }
function onExportData() { exportData('K1-5') }
async function onImportChange(uploadFile: UploadFile) {
  const raw = uploadFile.raw
  if (!raw) return
  await importData('K1-5', raw)
}

async function onAiAuditNote() {
  const content = await generateAndConfirm('large-amount-eval', auditNote.value, {
    rowCount: dataRows.value.length,
    bookValueTotal: summary.value.bookValue,
    relatedCount: summary.value.relatedCount,
    topNames: dataRows.value.slice(0, 5).map((r) => r.counterparty),
  }, 'AI 生成 K1-5 审计说明')
  if (content) {
    auditNote.value = content
    persistTextFields()
  }
}
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.audit-objective { margin-bottom: 8px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.process-hint { margin-bottom: 10px; }
.process-hint :deep(.el-alert__title) { font-size: 12px; line-height: 1.55; }
.summary-bar { margin-bottom: 10px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell, .subtotal-val { font-variant-numeric: tabular-nums; }
.subtotal-label { font-weight: 600; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.audit-table :deep(.auto-calc-col) { background-color: #f5f7fa !important; }
.audit-table :deep(.row-subtotal) { background: #fafafa !important; font-weight: 600; }
.audit-table :deep(.row-related) { background: #fef0f0 !important; }
.audit-table :deep(.row-b19-suspect) { background: #fdf4ff !important; }
.audit-table :deep(.row-large) { background: #fdf6ec !important; }
.debtor-cell { display: flex; align-items: center; gap: 4px; }
.debtor-cell :deep(.el-input) { flex: 1; min-width: 0; }
.jump-btn { flex-shrink: 0; padding: 0 2px; font-weight: 600; }
.b19-tag { flex-shrink: 0; }
.b19-alert { margin-bottom: 10px; }
.deeplink-bar { margin-bottom: 10px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; }
.search-input { width: 220px; }
.filter-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.audit-table :deep(.k1-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: k1-row-flash 1.2s ease-in-out 0s 2; }
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
.table-summary { margin-top: 8px; font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-bottom: 10px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
.open-hint { border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
</style>
