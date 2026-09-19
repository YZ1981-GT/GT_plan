<!--
  K1TabRelatedParty.vue — K1-11 关联方及交易检查表

  对齐致同源模板：关联方其他应收款真实性/合理性/合法性/会计处理，
  考虑未识别关联方。13列明细 + 审计说明 + 结论；期末/账面价值自动计算；
  支持从 K1-2 导入关联方行并勾稽合计。
-->
<template>
  <div class="k1-audit-sheet">
    <details class="compile-hint compile-hint-top">
      <summary>编制提示</summary>
      <ul>
        <li>本表列示关联方其他应收款，核真实性、商业实质与定价公允性，防止漏识关联方及资金占用</li>
        <li>期末余额 = 期初 + 借方 − 贷方；账面价值 = 期末 − 坏账准备（自动计算）</li>
        <li>可从 K1-2 导入标记为关联方的明细行；期后收款凭证检查详见 K1-12</li>
        <li>结合 B19 关联方识别程序，核对附注 CAS36 披露是否完整</li>
      </ul>
    </details>

    <div class="section-head">
      <h3 class="sheet-title">K1-11 关联方及交易检查表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleReview">💬 复核</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleAddRow">＋ 新增</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleImportFromK1">从 K1-2 导入</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :loading="postPaymentLoading"
          @click="onImportPostPayment"
        >取期后回款</el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title><span class="ao-title">一、审计目标（认定）</span></template>
      <ol class="ao-list">
        <li><b>完整性：</b>关联方识别是否完整（8 类关联关系），是否存在未识别关联方；</li>
        <li><b>存在与计价：</b>对关联方的其他应收款真实、金额合理，坏账准备计提恰当；</li>
        <li><b>列报与披露：</b>关联交易及余额按 CAS36 充分披露，期后收款可验证回收性。</li>
      </ol>
    </el-alert>

    <el-alert
      v-if="missingRelatedParties.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="import-hint"
    >
      <template #title>
        <span>
          B19 清单中有 {{ missingRelatedParties.length }} 个未在本表识别：
          {{ missingRelatedParties.slice(0, 5).join('、') }}{{ missingRelatedParties.length > 5 ? '…' : '' }}
        </span>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          style="margin-left: 8px"
          @click="handleAddMissing"
        >补充漏列（{{ missingRelatedParties.length }}）</el-button>
        <el-button
          size="small"
          link
          type="primary"
          style="margin-left: 4px"
          :loading="jumpingToB19"
          @click="goToB19RelatedPartyList"
        >前往 B19-1 维护清单 →</el-button>
      </template>
    </el-alert>

    <el-alert
      v-if="k1DetailImportCount === 0 && !isReadonly"
      type="warning"
      :closable="false"
      show-icon
      class="import-hint"
    >
      K1-2 明细表尚未标记关联方行，可先在 K1-2「关联关系」列标记后一键导入
    </el-alert>

    <el-alert
      v-if="reconcileGap !== null && Math.abs(reconcileGap) >= 0.01"
      type="warning"
      :closable="false"
      show-icon
      class="reconcile-alert"
    >
      本表期末余额合计 {{ fmtAmt(subtotal.endBalance) }} 与 K1-2 关联方期末合计
      {{ fmtAmt(k1DetailRelatedTotal) }} 差异 {{ fmtAmt(reconcileGap) }}，请核对
    </el-alert>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、关联方及交易明细</span>
          <div class="index-chips">
            <GtIndexChip value="wp:K1-2" :context-project-id="projectId" />
            <GtIndexChip value="wp:K1-12" :context-project-id="projectId" />
          </div>
        </div>
      </template>

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
      <div class="filter-bar">
        <el-input v-model="searchFilter" placeholder="搜索关联方..." size="small" clearable class="search-input" />
        <span v-if="searchFilter.trim()" class="filter-hint">显示 {{ filteredDisplayRows.length }} / {{ displayRows.length }} 户</span>
      </div>

      <el-table
        ref="tableRef"
        :data="filteredTableData"
        row-key="id"
        border
        size="small"
        :max-height="420"
        class="audit-table"
        :row-class-name="tableRowClass"
      >
        <el-table-column label="#" width="42" align="center">
          <template #default="{ row }">
            <span v-if="row.__subtotal">—</span>
            <span v-else>{{ rowIndex(row) + 1 }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方名称" min-width="156" fixed>
          <template #default="{ row }">
            <span v-if="row.__subtotal" class="subtotal-label">小计</span>
            <div v-else class="debtor-cell">
              <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onRowEdit(row)" />
              <span v-else>{{ row.name || '-' }}</span>
              <el-tooltip v-if="row.name?.trim()" content="跳转 K1-2 明细表">
                <el-button
                  link
                  type="primary"
                  size="small"
                  class="jump-btn"
                  @click="navigateToDetail(row)"
                >→</el-button>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="关联关系" min-width="160">
          <template #default="{ row }">
            <el-select
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.relation"
              size="small"
              filterable
              allow-create
              @change="onRowEdit(row)"
            >
              <el-option v-for="opt in relationOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else-if="!row.__subtotal">{{ row.relation || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.beginBalance"
              :controls="false"
              size="small"
              class="amt"
              @change="onRowEdit(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方发生额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.debit"
              :controls="false"
              size="small"
              class="amt"
              @change="onRowEdit(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.debit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方发生额" min-width="105" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.credit"
              :controls="false"
              size="small"
              class="amt"
              @change="onRowEdit(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.credit) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="105" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期初 + 借方 − 贷方（自动）" placement="top">
              <span class="formula-cell amount-cell">{{ fmtAmt(row.endBalance) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="减：坏账准备" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.provision"
              :controls="false"
              size="small"
              class="amt"
              @change="onRowEdit(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面价值" min-width="110" align="right" class-name="auto-calc-col">
          <template #default="{ row }">
            <el-tooltip content="期末余额 − 坏账准备（自动）" placement="top">
              <span class="formula-cell amount-cell">{{ fmtAmt(bookValueOf(row)) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="发生时间及账龄" min-width="130">
          <template #default="{ row }">
            <el-input
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.aging"
              size="small"
              placeholder="如 2024-06/2年"
              @change="onRowEdit(row)"
            />
            <span v-else-if="!row.__subtotal">{{ row.aging || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发生原因（款项性质）" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.nature"
              size="small"
              @change="onRowEdit(row)"
            />
            <span v-else-if="!row.__subtotal">{{ row.nature || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期后收款金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.postCollection"
              :controls="false"
              size="small"
              class="amt"
              @change="onRowEdit(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.postCollection) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否公允" min-width="96" align="center">
          <template #default="{ row }">
            <el-select v-if="!row.__subtotal && !isReadonly" v-model="row.isFair" size="small" @change="onRowEdit(row)">
              <el-option v-for="opt in triOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else-if="!row.__subtotal" size="small" :type="fairTagType(row.isFair)">{{ row.isFair || '待评估' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="是否披露" min-width="96" align="center">
          <template #default="{ row }">
            <el-select v-if="!row.__subtotal && !isReadonly" v-model="row.isDisclosed" size="small" @change="onRowEdit(row)">
              <el-option v-for="opt in discloseOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else-if="!row.__subtotal" size="small" :type="disclosedTagType(row.isDisclosed)">{{ row.isDisclosed || '待评估' }}</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="资金占用" min-width="96" align="center">
          <template #default="{ row }">
            <el-select v-if="!row.__subtotal && !isReadonly" v-model="row.capitalOccupation" size="small" @change="onRowEdit(row)">
              <el-option v-for="opt in occupationOptions" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <el-tag v-else-if="!row.__subtotal" size="small" :type="occupationTagType(row.capitalOccupation)">
              {{ row.capitalOccupation || '待评估' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.indexNo"
              size="small"
              placeholder="K1-12"
              @change="onRowEdit(row)"
            />
            <span v-else-if="!row.__subtotal">{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!row.__subtotal && !isReadonly"
              v-model="row.remark"
              size="small"
              @change="onRowEdit(row)"
            />
            <span v-else-if="!row.__subtotal">{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              v-if="!row.__subtotal"
              size="small"
              type="danger"
              link
              @click="removeRow('rows', row.id); persist()"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="relation-ref">
        <span class="rr-label">关联关系分类参考：</span>
        <el-tag v-for="opt in relationOptions" :key="opt" size="small" effect="plain" class="rr-tag">{{ opt }}</el-tag>
      </div>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="针对期后收款的凭证检查详见 K1-12；关注是否存在未识别关联方，关联交易定价是否公允、是否存在资金占用，披露是否完整"
        @change="persist"
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
        @change="persist"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/** K1TabRelatedParty.vue — K1-11 关联方及交易检查表 */
import { computed, inject, onMounted, ref, toRef, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { ElTable } from 'element-plus'
import { getWpIndex } from '@/services/workpaperApi'
import { useK1AuditRows, K1_CONCLUSION_TEMPLATES, type AuditRow } from '../../composables/useK1AuditRows'
import { useK1ImportExport } from '../../composables/useK1ImportExport'
import {
  addMissingK1RelatedPartyRows,
  bookValueOf,
  computeK1MissingRelatedParties,
  computeK1RelatedPartySubtotal,
  extractRelatedPartyDetailRows,
  k1DetailRelatedPartyEndTotal,
  K1_RELATED_PARTY_RELATIONSHIP_OPTIONS,
  mergeRelatedPartyFromK1Detail,
  normalizeK1RelatedPartyRow,
  rowBalanceGap,
  type K1RelatedPartyRow,
} from '../../composables/useK1RelatedParty'
import {
  fetchK1PostPaymentFromLedger,
  resolveK1BsDate,
} from '../../composables/k1PostPaymentFromLedger'
import {
  K1RowNavigationKey,
  applyK1IncomingFocus,
  buildK1DeeplinkHint,
} from '../../composables/useK1RowNavigation'
// @ts-ignore
import GtIndexChip from '../../GtIndexChip.vue'

const triOptions = ['是', '否', '待评估']
const discloseOptions = ['是', '否', '不适用', '待评估']
const occupationOptions = ['是', '否', '待评估']

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

const relationOptions = K1_RELATED_PARTY_RELATIONSHIP_OPTIONS
const registryParties = computed(() => props.relatedParties ?? [])

const allResponsesRef = computed(() => props.allResponses)
const ITEM_ID = 'K1-11-related-party'
const { tables, auditNote, conclusion, conclusionOption, load, addRow, removeRow, serialize } =
  useK1AuditRows({
    allResponses: allResponsesRef as any,
    itemId: ITEM_ID,
    tableKeys: ['rows'],
    rowDefaults: {
      rows: { isFair: '待评估', isDisclosed: '待评估', capitalOccupation: '待评估' },
    },
  })

const { exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })

const displayRows = computed(() =>
  (tables.value.rows ?? []).map(r => normalizeK1RelatedPartyRow(r as K1RelatedPartyRow)),
)

const subtotal = computed(() => computeK1RelatedPartySubtotal(displayRows.value))
const missingRelatedParties = computed(() =>
  computeK1MissingRelatedParties(registryParties.value, displayRows.value),
)

const tableData = computed(() => [
  ...displayRows.value,
  { id: '__subtotal__', __subtotal: true, ...subtotal.value },
])

const filteredDisplayRows = computed(() => {
  const keyword = searchFilter.value.trim().toLowerCase()
  if (!keyword) return displayRows.value
  return displayRows.value.filter((r) => String(r.name ?? '').toLowerCase().includes(keyword))
})

const filteredTableData = computed(() => {
  if (searchFilter.value.trim()) return filteredDisplayRows.value
  return tableData.value
})

const k1DetailImportCount = computed(() => extractRelatedPartyDetailRows(props.allResponses).length)
const k1DetailRelatedTotal = computed(() => k1DetailRelatedPartyEndTotal(props.allResponses))
const reconcileGap = computed(() => {
  if (!displayRows.value.length && !k1DetailRelatedTotal.value) return null
  return subtotal.value.endBalance - k1DetailRelatedTotal.value
})

onMounted(() => {
  load()
  applyIncomingFocus()
})

function applyIncomingFocus(): void {
  applyK1IncomingFocus({
    sheet: 'K1-11',
    k1Nav,
    rows: displayRows.value,
    nameOf: (r) => String((r as K1RelatedPartyRow).name ?? ''),
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

function persist() {
  const data = serialize()
  props.allResponses.set(ITEM_ID, { item_id: ITEM_ID, conclusion: null, remark: data })
  emit('save', ITEM_ID, { remark: data })
}

const postPaymentLoading = ref(false)

async function onImportPostPayment() {
  if (props.isReadonly) return
  postPaymentLoading.value = true
  try {
    const rows = (tables.value.rows ?? []) as K1RelatedPartyRow[]
    const result = await fetchK1PostPaymentFromLedger({
      projectId: props.projectId,
      bsDate: resolveK1BsDate(props.bsDate, props.year),
      rows: rows.map((r) => ({ id: String(r.id), name: String(r.name || '') })),
    })
    if (result.cancelled || result.matched === 0) return
    for (const [id, amt] of result.amounts) {
      const row = rows.find((r) => String(r.id) === id)
      if (row) row.postCollection = amt
    }
    persist()
  } finally {
    postPaymentLoading.value = false
  }
}

function onConclusionOption(val: string) {
  if (K1_CONCLUSION_TEMPLATES[val] && !conclusion.value) conclusion.value = K1_CONCLUSION_TEMPLATES[val]
  persist()
}

function navigateToDetail(row: K1RelatedPartyRow) {
  const name = String(row.name || '').trim()
  if (!name) {
    ElMessage.warning('请先填写关联方名称')
    return
  }
  if (k1Nav) {
    k1Nav.navigateToRow({
      sheet: 'K1-2',
      counterparty: name,
      sourceSheet: 'K1-11',
    })
    return
  }
  emit('navigate-sheet', 'K1-2 明细表')
}

function handleAddRow() {
  addRow('rows')
  const last = tables.value.rows[tables.value.rows.length - 1]
  if (last) tables.value.rows[tables.value.rows.length - 1] = normalizeK1RelatedPartyRow(last as K1RelatedPartyRow)
  persist()
}

function onRowEdit(row: AuditRow) {
  const idx = tables.value.rows.findIndex(r => r.id === row.id)
  if (idx === -1) return
  tables.value.rows[idx] = normalizeK1RelatedPartyRow(row as K1RelatedPartyRow)
  persist()
}

function handleImportFromK1() {
  const detailRows = extractRelatedPartyDetailRows(props.allResponses)
  if (!detailRows.length) {
    ElMessage.warning('K1-2 明细表无关联方行（关联关系≠否），请先在 K1-2 标记')
    return
  }
  tables.value.rows = mergeRelatedPartyFromK1Detail(
    tables.value.rows as K1RelatedPartyRow[],
    detailRows,
  )
  persist()
  ElMessage.success(`已从 K1-2 导入/更新 ${detailRows.length} 笔关联方明细`)
}

function handleAddMissing() {
  const missing = missingRelatedParties.value
  if (!missing.length) return
  tables.value.rows = addMissingK1RelatedPartyRows(tables.value.rows as K1RelatedPartyRow[], missing)
  persist()
  ElMessage.success(`已补充 ${missing.length} 个 B19 清单漏列关联方`)
}

async function goToB19RelatedPartyList() {
  if (!props.projectId || jumpingToB19.value) return
  jumpingToB19.value = true
  try {
    const index = await getWpIndex(props.projectId)
    const b19 = index.find(i => i.wp_code === 'B19')
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

function rowIndex(row: AuditRow): number {
  return tables.value.rows.findIndex(r => r.id === row.id)
}

function tableRowClass({ row }: { row: AuditRow & { __subtotal?: boolean } }): string {
  if (row.__subtotal) return 'subtotal-row'
  const parts: string[] = []
  const hl = k1Nav?.rowHighlightClass(row.id)
  if (hl) parts.push(hl)
  const rp = row as K1RelatedPartyRow
  if (Math.abs(rowBalanceGap(rp)) >= 0.01) parts.push('mismatch-row')
  else if (rp.isFair === '否' || rp.isDisclosed === '否' || rp.capitalOccupation === '是') parts.push('risk-row')
  return parts.join(' ')
}

function fairTagType(v: string) {
  if (v === '是') return 'success'
  if (v === '否') return 'danger'
  return 'info'
}
function disclosedTagType(v: string) {
  if (v === '是') return 'success'
  if (v === '否') return 'danger'
  if (v === '不适用') return 'info'
  return 'warning'
}
function occupationTagType(v: string) {
  if (v === '是') return 'danger'
  if (v === '否') return 'success'
  return 'info'
}

function fmtAmt(v: number | null | undefined): string {
  if (v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleReview() {
  openReviewDialog('K1-11-related-party')
}

function handleExportTemplate() {
  exportTemplate('K1-11')
}

function handleExportData() {
  exportData('K1-11')
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-11', file)
    if (result) load()
  }
  input.click()
}
</script>

<style scoped>
.k1-audit-sheet { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }
.import-hint, .reconcile-alert { margin-bottom: 10px; }
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.card-title { font-weight: 600; }
.index-chips { display: flex; gap: 6px; flex-wrap: wrap; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amt { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.subtotal-label { font-weight: 600; }
.debtor-cell { display: flex; align-items: center; gap: 4px; }
.debtor-cell :deep(.el-input) { flex: 1; min-width: 0; }
.jump-btn { flex-shrink: 0; padding: 0 2px; font-weight: 600; }
.deeplink-bar { margin-bottom: 8px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; }
.search-input { width: 220px; }
.filter-hint { font-size: 12px; color: var(--el-text-color-secondary); }
.audit-table :deep(.k1-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: k1-row-flash 1.2s ease-in-out 0s 2; }
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
.relation-ref { margin-top: 10px; display: flex; align-items: center; flex-wrap: wrap; gap: 6px; }
.rr-label { font-size: 12px; color: var(--el-text-color-secondary); }
.rr-tag { margin: 0; }
.conclusion-card { margin-bottom: 10px; }
.conclusion-card :deep(.el-card__header) { padding: 8px 14px; }
.conclusion-card :deep(.el-card__body) { padding: 12px 14px; }
.concl-select { width: 100%; margin-bottom: 8px; }
.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint-top { margin-bottom: 10px; }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 18px; margin-top: 8px; line-height: 1.7; }
:deep(.subtotal-row) { background: var(--el-fill-color-light); font-weight: 600; }
:deep(.mismatch-row) { background: color-mix(in srgb, var(--el-color-warning-light-9) 60%, transparent); }
:deep(.risk-row) { background: color-mix(in srgb, var(--el-color-danger-light-9) 50%, transparent); }
:deep(.auto-calc-col) { background: var(--el-fill-color-lighter); }
</style>
