<template>
  <div class="i3-tab-disclosure-soe">
    <div class="section-header">
      <span class="section-title">商誉附注披露（国有企业）</span>
      <div class="section-actions">
        <GtIndexChip v-if="noteTarget" :value="noteTarget.chipValue" :context-project-id="projectId" />
        <el-button size="small" type="info" plain :disabled="isReadonly" @click="handlePull(true)">
          从 I3-2 取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
        <el-button size="small" type="default" text @click="handleReview('disc-soe')">💬复核</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> （1）（2）原值/减值准备滚动</div>
        <div class="guide-step"><span class="step-num">②</span> 净值=原值期末−减值期末</div>
        <div class="guide-step"><span class="step-num">③</span> 减值测试方法与参数说明</div>
        <div class="guide-step"><span class="step-num">④</span> 同步至附注模块 §八、29</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">CAS8 商誉披露（国有企业附注格式）</div>
      <div class="methodology-content">
        国企附注披露（1）商誉账面原值、（2）商誉减值准备的期初/本期增/本期减/期末，
        并说明减值测试方法、减值原因及金额确认依据。商誉不摊销，减值不可转回。
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实国有企业商誉附注完整性与准确性；矩阵与 I3-2 勾稽；同步至附注模块「八、29 商誉」。"
    />
    <el-alert
      v-if="needsDetailSplitWarning"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
      title="当前为合计占位行（无明细分项），期初可能未填。请点「从 I3-2 取数」按被投资单位展开。"
    />

    <template v-for="section in sections" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="card-title-row">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-button
                v-if="isEditableMatrix(section.key) && !isReadonly"
                size="small"
                @click="handleAddMatrix(section.key)"
              >+ 行</el-button>
              <el-button size="small" type="default" link @click="handleReview(`disc-soe-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <template v-if="section.hasTable">
          <el-table :data="getMatrixRows(section.key)" border stripe size="small" class="matrix-table">
            <el-table-column prop="investee" label="被投资单位名称或形成商誉的事项" min-width="180" fixed>
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly && isEditableMatrix(section.key)"
                  v-model="row.investee"
                  size="small"
                  @change="() => handleInvesteeChange(section.key, row)"
                />
                <span v-else>{{ row.investee }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初余额" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly && isEditableMatrix(section.key)"
                  :model-value="row.beginBalance"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'beginBalance', v)"
                />
                <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly && isEditableMatrix(section.key)"
                  :model-value="row.increase"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'increase', v)"
                />
                <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期减少" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput
                  v-if="!isReadonly && isEditableMatrix(section.key)"
                  :model-value="row.decrease"
                  size="small"
                  :disabled="isReadonly"
                  style="width:100%"
                  @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'decrease', v)"
                />
                <span v-else class="amount-cell">{{ fmtAmt(row.decrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末余额" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+增加-减少">{{ fmtAmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly && isEditableMatrix(section.key)" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveMatrix(section.key, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="section.key === 'goodwill_book_value'" class="matrix-subtotal">
            合计：期初 {{ fmtAmt(bookValueTotal.beginBalance) }}
            ｜ 增加 {{ fmtAmt(bookValueTotal.increase) }}
            ｜ 减少 {{ fmtAmt(bookValueTotal.decrease) }}
            ｜ 期末 {{ fmtAmt(bookValueTotal.endBalance) }}
          </div>
          <div v-else-if="section.key === 'goodwill_impairment'" class="matrix-subtotal">
            合计：期初 {{ fmtAmt(impairmentTotal.beginBalance) }}
            ｜ 增加 {{ fmtAmt(impairmentTotal.increase) }}
            ｜ 减少 {{ fmtAmt(impairmentTotal.decrease) }}
            ｜ 期末 {{ fmtAmt(impairmentTotal.endBalance) }}
            <div class="impairment-warning">⚠️ 商誉减值不可转回，「本期减少」仅限处置/注销</div>
          </div>
        </template>

        <template v-if="section.hasDynamicRows">
          <el-divider v-if="section.hasTable" content-position="left">CGU分摊</el-divider>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="资产组(CGU)名称" min-width="150">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="handleDynamicChange(section.key, row.rowId, 'name', row.name)" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="分摊商誉额" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly" v-model="row.amount" size="small" :disabled="isReadonly" @change="(v: number) => handleDynamicChange(section.key, row.rowId, 'amount', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="分摊依据/说明" min-width="180">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="handleDynamicChange(section.key, row.rowId, 'description', row.description)" />
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveDynamic(section.key, row.rowId)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!isReadonly" class="dynamic-actions">
            <el-button size="small" @click="handleAddDynamic(section.key)">+ 新增CGU</el-button>
          </div>
        </template>

        <template v-if="section.hasNoteText">
          <el-divider v-if="section.hasTable || section.hasDynamicRows" content-position="left">文字说明</el-divider>
          <el-input
            v-model="sectionNotes[section.key]"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :disabled="isReadonly"
            :placeholder="getPlaceholder(section.key)"
            @change="handleNoteChange(section.key)"
          />
          <div v-if="!isReadonly && !sectionNotes[section.key]" class="template-actions">
            <el-button size="small" text type="primary" @click="applyTemplate(section.key)">插入模板段落</el-button>
          </div>
        </template>
      </el-card>
    </template>

    <el-card shadow="never" class="summary-card">
      <template #header><span class="summary-title">商誉账面净值合计</span></template>
      <div class="summary-formula">
        净值 = 原值期末 {{ fmtAmt(bookValueTotal.endBalance) }}
        − 减值期末 {{ fmtAmt(impairmentTotal.endBalance) }}
        = <span class="net-value">{{ fmtAmt(netValueTotal) }}</span>
      </div>
      <div class="summary-note">同步目标附注「{{ noteTarget.sectionId }}」</div>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, watch, onMounted, onUnmounted, onBeforeUnmount } from 'vue'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI3Disclosure,
  SOE_SECTIONS,
  type I3DisclosureMatrixRow,
} from '../../composables/useI3Disclosure'
import { resolveI3NoteSectionTarget } from '../../composables/i3NoteSectionMap'
import { buildI3SoeSyncPayloads } from '../../composables/i3DisclosureSyncPayload'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { DisplayPrefs_Key } from '../../composables/displayPrefsKey'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  crossSheetAutoFill?: Record<string, number>
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
// 🔴 inject 分支让宿主 provide 的偏好优先于全局 store；
//    必须 setup 顶层（写进函数体静默失效）。
const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()
const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'I3', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}
const allResponsesRef = computed(() => props.allResponses)
const noteTarget = resolveI3NoteSectionTarget('soe')
const isSyncing = ref(false)
const sections = SOE_SECTIONS

const {
  bookValueRows,
  impairmentRows,
  sectionRows,
  sectionNotes,
  bookValueTotal,
  impairmentTotal,
  netValueTotal,
  applyAutoFill,
  needsDetailSplitWarning,
  pullFromDetailRows,
  addDynamicRow,
  removeDynamicRow,
  updateDynamicRow,
  updateMatrixCell,
  addMatrixRow,
  removeMatrixRow,
  saveSectionNote,
  getSyncSnapshot,
  dispose: disposeDisclosure,
} = useI3Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    variant: ref('soe') as any,
    crossSheetAutoFill: computed(() => props.crossSheetAutoFill ?? {}),
    onSave(itemId: string, value: any) {
      emit('save', itemId, value)
    },
  },
)

function handleAdjudicated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (!detail || detail.wpCode === 'I3' || detail.accountCode === '1711') applyAutoFill()
}

onMounted(() => {
  applyAutoFill()
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
})
onUnmounted(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  disposeDisclosure()
})

function isEditableMatrix(key: string) {
  return key === 'goodwill_book_value' || key === 'goodwill_impairment'
}

function getMatrixRows(sectionKey: string): I3DisclosureMatrixRow[] {
  if (sectionKey === 'goodwill_book_value') return bookValueRows.value
  if (sectionKey === 'goodwill_impairment') return impairmentRows.value
  if (sectionKey === 'impairment_result') {
    return (sectionRows.value.cgu_allocation ?? []).map((cgu) => ({
      rowId: `result-${cgu.rowId}`,
      investee: cgu.name || '未命名CGU',
      beginBalance: cgu.amount ?? 0,
      increase: 0,
      decrease: 0,
      endBalance: cgu.amount ?? 0,
      isAutoFilled: false,
    }))
  }
  return []
}

function getDynamicRows(key: string) {
  return sectionRows.value[key] ?? []
}

async function handleAddDynamic(sectionKey: string) {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产组(CGU)名称', '新增CGU行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
    })
    if (value?.trim()) addDynamicRow(sectionKey, value.trim())
  } catch { /* cancel */ }
}

function handleRemoveDynamic(sectionKey: string, rowId: string) {
  removeDynamicRow(sectionKey, rowId)
}

function handleDynamicChange(sectionKey: string, rowId: string, field: string, value: any) {
  updateDynamicRow(sectionKey, rowId, field as any, value)
}

function handleMatrixEdit(sectionKey: string, rowId: string, field: string, value: number) {
  updateMatrixCell(
    sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment',
    rowId,
    field as keyof I3DisclosureMatrixRow,
    value ?? 0,
  )
}

function handleAddMatrix(sectionKey: string) {
  addMatrixRow(sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment')
}

function handleRemoveMatrix(sectionKey: string, rowId: string) {
  removeMatrixRow(sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment', rowId)
}

function handleInvesteeChange(sectionKey: string, row: I3DisclosureMatrixRow) {
  updateMatrixCell(
    sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment',
    row.rowId,
    'investee',
    row.investee,
  )
}

function handleNoteChange(sectionKey: string) {
  saveSectionNote(sectionKey, sectionNotes.value[sectionKey] ?? '')
}

function handlePull(overwrite: boolean) {
  const res = pullFromDetailRows({ overwrite })
  ElMessage({ type: res.count ? 'success' : 'warning', message: res.message })
}

const SOE_PROCESS_TEMPLATE =
  '本公司采用预计未来现金流现值的方法计算资产组的可收回金额。本公司根据管理层批准的财务预算预计未来5年内现金流量，'
  + '其后年度采用的现金流量增长率预计为XX%（上期：XX%），不会超过资产组经营业务的长期平均增长率。'
  + '管理层根据过往表现及其对市场发展的预期编制上述财务预算。计算未来现金流现值所采用的税前折现率为XX%（上期：XX%），'
  + '已反映了相对于有关分部的风险。根据减值测试的结果，本期期末商誉未发生减值（上期期末：无）。'
  + '【或：本期期末对商誉计提减值准备XX元（上期期末：XX元）。】'

const TEMPLATES: Record<string, string> = {
  impairment_test_process: SOE_PROCESS_TEMPLATE,
  key_assumptions: '关键假设（增长率、利润率、折现率）及其确定依据；与上期差异原因：',
  impairment_result: '本期减值结论及金额确认依据：',
  cgu_allocation: '商誉分摊至资产组的构成及依据：',
  other_disclosure: '其他说明：',
}

function applyTemplate(sectionKey: string) {
  const t = TEMPLATES[sectionKey]
  if (!t) return
  sectionNotes.value[sectionKey] = t
  saveSectionNote(sectionKey, t)
}

function getPlaceholder(key: string): string {
  return TEMPLATES[key] || '请填写披露文字…'
}

function fmtAmt(v: number): string {
  return displayPrefs.fmtAmount(Number(v) || 0)
}

function handleReview(id: string) {
  openReviewDialog(id)
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const snap = getSyncSnapshot()
  if (!snap.bookValueRows.length && !snap.impairmentRows.length) {
    ElMessage.warning('请先从 I3-2 取数或手工填写变动矩阵')
    return
  }
  const payloads = buildI3SoeSyncPayloads(props.wpId, props.applicableStandards || [], snap)
  if (!payloads.length) {
    ElMessage.warning('当前不适用国企附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      rows += Number((result?.data ?? result)?.rows_synced ?? 0)
    }
    eventBus.emit('disclosure:note-text-updated' as any, {
      projectId: props.projectId,
      sectionIds: [noteTarget.sectionId],
      wpId: props.wpId,
      sheet: '附注披露（国有企业）',
    })
    ElMessage.success(`已同步至附注 ${noteTarget.sectionId}（${rows} 行）`)
  } catch (e: any) {
    ElMessage.error(e?.message || '同步失败')
  } finally {
    isSyncing.value = false
  }
}

watch(
  [
    () => bookValueRows.value,
    () => impairmentRows.value,
    () => sectionRows.value,
    () => sectionNotes.value,
  ],
  () => autoSync.scheduleAutoSync(syncToNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.i3-tab-disclosure-soe { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px; flex-wrap: wrap;
}
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions, .title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-title-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
  font-size: 14px; font-weight: 600;
}
.guide-area {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #93c5fd; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 12px; color: #1e3a5f; }
.guide-step { display: flex; gap: 6px; }
.step-num { color: #2563eb; font-weight: 700; }
.methodology-block {
  border-left: 4px solid #f59e0b; background: #fffbeb; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 12px; font-size: 12px; line-height: 1.7; color: #78350f;
}
.methodology-title { font-weight: 600; margin-bottom: 4px; }
.objective-alert { margin-bottom: 12px; }
.disclosure-card { margin-bottom: 12px; }
.matrix-table { width: 100%; margin-bottom: 8px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-weight: 600; border-bottom: 1px dashed #94a3b8; cursor: help; }
.matrix-subtotal { font-size: 12px; color: #475569; margin-top: 6px; }
.impairment-warning { color: #b45309; margin-top: 4px; }
.dynamic-actions, .template-actions { margin-top: 8px; }
.summary-card { margin-top: 8px; }
.summary-title { font-weight: 600; }
.summary-formula { font-size: 13px; line-height: 1.8; }
.net-value { color: #92400e; font-weight: 700; font-size: 15px; }
.summary-note { font-size: 12px; color: #6b7280; margin-top: 4px; }
</style>
