<script setup lang="ts">
/**
 * D1TabDisclosure.vue — 附注披露（上市+国企）专属组件
 *
 * Spec: .kiro/specs/d1-disclosure-note/
 * Tasks: 6.1~6.8
 *
 * 通过 variant='listed'|'soe' 区分上市/国企版本。
 * 每个子节用 el-card 折叠卡片渲染对应 el-table。
 */
import { ref, computed } from 'vue'
import { useDebounceFn } from '@vueuse/core'
import { ElMessage } from 'element-plus'
import { Lock, Delete, Plus } from '@element-plus/icons-vue'
import {
  useD1Disclosure,
  DISCLOSURE_GUIDANCE,
  type DisclosureVariant,
} from '../composables/useD1Disclosure'
import type { ChecklistResponse } from '../composables/useD1FormData'
import type { Ref } from 'vue'
import GtIndexChip from '../GtIndexChip.vue'
import http from '@/utils/http'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = withDefaults(defineProps<{
  variant: DisclosureVariant
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId: string
  isReadonly?: boolean
}>(), { isReadonly: false })

// ─── State ───────────────────────────────────────────────────────────────────

const collapsedSections = ref<Record<string, boolean>>({})

// Note textareas per section
const sectionNotes = ref<Record<string, string>>({})

function toggleSection(key: string) {
  collapsedSections.value[key] = !collapsedSections.value[key]
}

// ─── Persistence (debounced) ─────────────────────────────────────────────────

const pendingSaveItems = ref<any[]>([])

const debouncedSave = useDebounceFn(async () => {
  if (pendingSaveItems.value.length === 0) return
  const items = [...pendingSaveItems.value]
  pendingSaveItems.value = []
  try {
    await http.post(`/api/workpapers/${props.wpId}/checklist-responses/batch`, { items })
  } catch {
    // silently fail - data is already in allResponses map
  }
}, 2000)

async function saveWithDebounce(items: any[]): Promise<void> {
  pendingSaveItems.value.push(...items)
  debouncedSave()
}

// ─── Composable ──────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses) as unknown as Ref<Map<string, ChecklistResponse>>
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>
const projectIdRef = computed(() => props.projectId) as unknown as Ref<string>
const isReadonlyRef = computed(() => props.isReadonly) as unknown as Ref<boolean>

const {
  sectionOrder, isLoading, crossSheetData, crossSheetStatus,
  pledgedRows, pledgedTotal, addPledgedRow, removePledgedRow,
  endorsedRows, endorsedTotal, addEndorsedRow, removeEndorsedRow,
  transferRows, transferTotal,
  classEndRows, classEndTotal, classPriorRows, classPriorTotal,
  individualEndRows, individualPriorRows, addIndividualRow, removeIndividualRow,
  bankPortfolioEndRows, bankPortfolioPriorRows,
  commercialPortfolioEndRows, commercialPortfolioPriorRows,
  addPortfolioRow, removePortfolioRow,
  movementRows, movementTotal, reversalDetailRows, reversalDetailTotal,
  addReversalRow, removeReversalRow,
  writeOffAmount, writeOffDetailRows, writeOffDetailTotal,
  addWriteOffRow, removeWriteOffRow,
  categorySummaryRows, categorySummaryTotal,
  updateCell,
} = useD1Disclosure({
  allResponses: allResponsesRef,
  wpId: wpIdRef,
  projectId: projectIdRef,
  variant: props.variant,
  saveImmediate: saveWithDebounce,
  isReadonly: isReadonlyRef,
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmt(val: number): string {
  if (val === 0) return '-'
  if (val < 0) return `<span style="color:#f56c6c">(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2 })})</span>`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2 })
}

function fmtPct(val: number): string {
  return (val * 100).toFixed(2) + '%'
}

// ─── Section Labels ──────────────────────────────────────────────────────────

const sectionLabels: Record<string, string> = {
  pledged: '一、期末已质押的应收票据',
  endorsed: '二、期末已背书或贴现且未到期的应收票据',
  transfer: '三、期末因出票人未履约而转为应收账款的票据',
  badDebtClass: '四、坏账准备按类别分类情况',
  badDebtMovement: '五、坏账准备变动情况',
  writeOff: '六、本期实际核销的应收票据',
  categorySummary: '一、应收票据按票据种类分类',
}

// ─── Import/Export (Task 10.2) ────────────────────────────────────────────────

async function exportTemplate() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/export-template`,
      null,
      { params: { variant: props.variant }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `D1-附注披露-${props.variant === 'listed' ? '上市' : '国企'}-模板.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function exportData() {
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/export-data`,
      null,
      { params: { variant: props.variant }, responseType: 'blob' }
    )
    const blob = new Blob([res.data])
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `D1-附注披露-${props.variant === 'listed' ? '上市' : '国企'}-数据.xlsx`
    a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportFile(file: File) {
  const formData = new FormData()
  formData.append('file', file)
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d1/disclosure/import-data`,
      formData,
      { params: { variant: props.variant }, headers: { 'Content-Type': 'multipart/form-data' } }
    )
    const data = res.data?.data ?? res.data
    if (data?.invalid_columns?.length) {
      ElMessage.error(`列名不匹配: ${data.invalid_columns.join(', ')}`)
    } else {
      ElMessage.success(`导入成功: ${data?.rowCount ?? 0}行`)
    }
  } catch { ElMessage.error('导入失败') }
}

function onNoteChange(sectionKey: string, value: string) {
  sectionNotes.value[sectionKey] = value
  updateCell(`D1-disc-${props.variant}-note-${sectionKey}`, '', 'note', value)
}
</script>

<template>
  <div class="d1-disclosure">
    <!-- Header: variant tag + mode switch + toolbar -->
    <div class="d1-disclosure__header">
      <el-tag :type="variant === 'listed' ? 'primary' : 'success'" effect="plain">
        {{ variant === 'listed' ? '上市公司版' : '国企版' }}
      </el-tag>
      <GtIndexChip value="附注全文" :context-project-id="projectId" />
      <div class="d1-disclosure__toolbar">
        <el-button-group size="small">
          <el-button @click="exportTemplate">导出模板</el-button>
          <el-button @click="exportData">导出数据</el-button>
          <el-upload
            :show-file-list="false"
            accept=".xlsx"
            :auto-upload="false"
            :on-change="(f: any) => handleImportFile(f.raw)"
            style="display:inline-block"
          >
            <el-button size="small">导入数据</el-button>
          </el-upload>
        </el-button-group>
      </div>
    </div>

    <el-skeleton v-if="isLoading" :rows="10" animated />
    <template v-else>
        <!-- Top guidance -->
        <details class="guidance-fold">
          <summary>📋 编制提示</summary>
          <p v-for="(t, i) in DISCLOSURE_GUIDANCE.top" :key="'top-'+i">{{ t }}</p>
        </details>

        <!-- Cross-sheet summary (listed only) -->
        <div v-if="variant === 'listed'" class="cross-sheet-summary">
          <GtIndexChip value="D1-1" :context-project-id="projectId" />
          <span>银行承兑期末余额: <span class="value" v-html="fmtAmt(crossSheetData.bankEndBalance)" /></span>
          <span>商业承兑期末余额: <span class="value" v-html="fmtAmt(crossSheetData.commercialEndBalance)" /></span>
          <span>银行承兑期末坏账: <span class="value" v-html="fmtAmt(crossSheetData.bankEndProvision)" /></span>
          <span>商业承兑期末坏账: <span class="value" v-html="fmtAmt(crossSheetData.commercialEndProvision)" /></span>
        </div>

        <!-- Sections rendered by sectionOrder -->
        <el-card
          v-for="section in sectionOrder"
          :key="section"
          class="d1-section-card"
          shadow="never"
        >
          <template #header>
            <div style="display:flex;align-items:center;justify-content:space-between">
              <span style="font-weight:600">{{ sectionLabels[section] }}</span>
              <div style="display:flex;align-items:center;gap:8px">
                <GtIndexChip v-if="section === 'badDebtClass' || section === 'badDebtMovement'" value="D1-4" :context-project-id="projectId" />
                <el-button text size="small" @click="toggleSection(section)">
                  {{ collapsedSections[section] ? '展开' : '收起' }}
                </el-button>
              </div>
            </div>
          </template>

          <div v-show="!collapsedSections[section]">

            <!-- ═══ 6.2 Pledged Section ═══ -->
            <template v-if="section === 'pledged'">
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPledgedRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...pledgedRows, pledgedTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('pledged', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="期末已质押金额" min-width="180" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.pledgedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.pledgedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('pledged', row.rowId, 'pledgedAmount', row.pledgedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removePledgedRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <!-- Note textarea for pledged -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['pledged'] || ''" placeholder="请输入质押票据相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('pledged', v)" />
                <div class="note-actions">
                  <el-button size="small" disabled>🤖 AI</el-button>
                  <el-button size="small" disabled>💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.3 Endorsed Section ═══ -->
            <template v-if="section === 'endorsed'">
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addEndorsedRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...endorsedRows, endorsedTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('endorsed', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="终止确认金额" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.derecognizedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.derecognizedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('endorsed', row.rowId, 'derecognizedAmount', row.derecognizedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="未终止确认金额" min-width="160" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.notDerecognizedAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.notDerecognizedAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('endorsed', row.rowId, 'notDerecognizedAmount', row.notDerecognizedAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }">
                    <el-button v-if="row.rowType === 'dynamic'" :icon="Delete" text type="danger" size="small" @click="removeEndorsedRow(row.rowId)" />
                  </template>
                </el-table-column>
              </el-table>
              <el-alert type="info" :closable="false" style="margin-top:8px" show-icon>
                <template #title>CAS23 终止确认判断提示</template>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.endorsed" :key="i" style="margin:4px 0;font-size:12px">{{ t }}</p>
              </el-alert>
              <!-- Guidance fold for endorsed -->
              <details class="guidance-fold">
                <summary>📋 编制提示 — 背书贴现终止确认判断</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.endorsed" :key="'eg-'+i">{{ t }}</p>
              </details>
              <!-- Note textarea for endorsed -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['endorsed'] || ''" placeholder="请输入背书贴现相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('endorsed', v)" />
                <div class="note-actions">
                  <el-button size="small" disabled>🤖 AI</el-button>
                  <el-button size="small" disabled>💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.4 Transfer Section ═══ -->
            <template v-if="section === 'transfer'">
              <el-table :data="[...transferRows, transferTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="200">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b>{{ row.category }}</b></template>
                    <template v-else-if="row.isFixed">
                      <el-icon :size="12" style="margin-right:4px"><Lock /></el-icon>{{ row.category }}
                    </template>
                    <template v-else>
                      <el-input v-model="row.category" size="small" :disabled="isReadonly" @change="updateCell('transfer', row.rowId, 'category', row.category)" />
                    </template>
                  </template>
                </el-table-column>
                <el-table-column label="转应收账款金额" min-width="180" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType === 'summary'"><b class="amount-cell" v-html="fmtAmt(row.transferAmount)" /></template>
                    <template v-else>
                      <el-input-number v-model="row.transferAmount" :controls="false" size="small" :disabled="isReadonly"
                        @change="updateCell('transfer', row.rowId, 'transferAmount', row.transferAmount)" style="width:100%" />
                    </template>
                  </template>
                </el-table-column>
              </el-table>
            </template>

            <!-- ═══ 6.5 Bad Debt Classification (most complex) ═══ -->
            <template v-if="section === 'badDebtClass'">
              <!-- 期末分类表 -->
              <h4 style="margin:0 0 8px">期末坏账准备分类情况</h4>
              <el-table :data="[...classEndRows, classEndTotal]" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="类别" min-width="180">
                  <template #default="{ row }"><span :style="row.rowType==='summary'?'font-weight:600':''">{{ row.label }}</span></template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.balance)" /></template>
                    <template v-else><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('classEnd', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="比例(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.ratio) }}</span></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.provision)" /></template>
                    <template v-else><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('classEnd', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="130" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                </el-table-column>
              </el-table>

              <!-- 上年分类表 -->
              <h4 style="margin:0 0 8px">上年同期坏账准备分类情况</h4>
              <el-table :data="[...classPriorRows, classPriorTotal]" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="类别" min-width="180">
                  <template #default="{ row }"><span :style="row.rowType==='summary'?'font-weight:600':''">{{ row.label }}</span></template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.balance)" /></template>
                    <template v-else><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('classPrior', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="比例(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.ratio) }}</span></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="130" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.provision)" /></template>
                    <template v-else><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('classPrior', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="账面价值" min-width="130" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.bookValue)" /></template>
                </el-table-column>
              </el-table>

              <!-- 按单项明细（期末） -->
              <h4 style="margin:0 0 8px">按单项计提坏账准备明细（期末）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addIndividualRow('end')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="individualEndRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="名称" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.name" size="small" :disabled="isReadonly" @change="updateCell('individualEnd', row.rowId, 'name', row.name)" /></template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('individualEnd', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('individualEnd', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="计提依据" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.basis" size="small" :disabled="isReadonly" @change="updateCell('individualEnd', row.rowId, 'basis', row.basis)" /></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'end')" /></template>
                </el-table-column>
              </el-table>

              <!-- 按单项明细（上年） -->
              <h4 style="margin:0 0 8px">按单项计提坏账准备明细（上年）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addIndividualRow('prior')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="individualPriorRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="名称" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.name" size="small" :disabled="isReadonly" @change="updateCell('individualPrior', row.rowId, 'name', row.name)" /></template>
                </el-table-column>
                <el-table-column label="账面余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('individualPrior', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('individualPrior', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column label="计提依据" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.basis" size="small" :disabled="isReadonly" @change="updateCell('individualPrior', row.rowId, 'basis', row.basis)" /></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removeIndividualRow(row.rowId, 'prior')" /></template>
                </el-table-column>
              </el-table>

              <!-- 银行承兑组合明细（期末+上年） -->
              <h4 style="margin:0 0 8px">银行承兑汇票按组合计提明细（期末）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPortfolioRow('bank', 'end')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="bankPortfolioEndRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="出票人类型/账龄" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.drawerTypeOrAging" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-end', row.rowId, 'drawerTypeOrAging', row.drawerTypeOrAging)" /></template>
                </el-table-column>
                <el-table-column label="应收票据余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-end', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-end', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removePortfolioRow(row.rowId, 'bank', 'end')" /></template>
                </el-table-column>
              </el-table>

              <h4 style="margin:0 0 8px">银行承兑汇票按组合计提明细（上年）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPortfolioRow('bank', 'prior')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="bankPortfolioPriorRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="出票人类型/账龄" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.drawerTypeOrAging" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-prior', row.rowId, 'drawerTypeOrAging', row.drawerTypeOrAging)" /></template>
                </el-table-column>
                <el-table-column label="应收票据余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-prior', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-bank-prior', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removePortfolioRow(row.rowId, 'bank', 'prior')" /></template>
                </el-table-column>
              </el-table>

              <!-- 商业承兑组合明细（期末+上年） -->
              <h4 style="margin:0 0 8px">商业承兑汇票按组合计提明细（期末）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPortfolioRow('commercial', 'end')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="commercialPortfolioEndRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="出票人类型/账龄" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.drawerTypeOrAging" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-end', row.rowId, 'drawerTypeOrAging', row.drawerTypeOrAging)" /></template>
                </el-table-column>
                <el-table-column label="应收票据余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-end', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-end', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removePortfolioRow(row.rowId, 'commercial', 'end')" /></template>
                </el-table-column>
              </el-table>

              <h4 style="margin:0 0 8px">商业承兑汇票按组合计提明细（上年）</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addPortfolioRow('commercial', 'prior')" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="commercialPortfolioPriorRows" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="出票人类型/账龄" min-width="150">
                  <template #default="{ row }"><el-input v-model="row.drawerTypeOrAging" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-prior', row.rowId, 'drawerTypeOrAging', row.drawerTypeOrAging)" /></template>
                </el-table-column>
                <el-table-column label="应收票据余额" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.balance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-prior', row.rowId, 'balance', row.balance)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="坏账准备" min-width="120" align="right">
                  <template #default="{ row }"><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('portfolio-commercial-prior', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                </el-table-column>
                <el-table-column label="损失率(%)" min-width="90" align="right">
                  <template #default="{ row }"><span class="amount-cell">{{ fmtPct(row.lossRate) }}</span></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button :icon="Delete" text type="danger" size="small" @click="removePortfolioRow(row.rowId, 'commercial', 'prior')" /></template>
                </el-table-column>
              </el-table>
              <!-- Guidance fold for badDebtClass -->
              <details class="guidance-fold">
                <summary>📋 编制提示 — 坏账分类</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.badDebtClassification" :key="'bdg-'+i">{{ t }}</p>
              </details>
              <!-- Note textarea for badDebtClass -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['badDebtClass'] || ''" placeholder="请输入坏账分类相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('badDebtClass', v)" />
                <div class="note-actions">
                  <el-button size="small" disabled>🤖 AI</el-button>
                  <el-button size="small" disabled>💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.6 Bad Debt Movement Section ═══ -->
            <template v-if="section === 'badDebtMovement'">
              <h4 style="margin:0 0 8px">坏账准备变动情况</h4>
              <el-table :data="variant === 'listed' ? movementRows : [...movementRows, movementTotal]" border size="small" style="width:100%;margin-bottom:16px">
                <el-table-column label="项目" min-width="120">
                  <template #default="{ row }"><span :style="row.rowType==='summary'?'font-weight:600':''">{{ row.label }}</span></template>
                </el-table-column>
                <el-table-column label="上年末余额" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.priorBalance)" /></template>
                    <template v-else><el-input-number v-model="row.priorBalance" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'priorBalance', row.priorBalance)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="本期计提" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.provision)" /></template>
                    <template v-else><el-input-number v-model="row.provision" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'provision', row.provision)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="本期转回" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.reversal)" /></template>
                    <template v-else><el-input-number v-model="row.reversal" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'reversal', row.reversal)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="本期核销" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.writeOff)" /></template>
                    <template v-else><el-input-number v-model="row.writeOff" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'writeOff', row.writeOff)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="本期转销" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.transfer)" /></template>
                    <template v-else><el-input-number v-model="row.transfer" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'transfer', row.transfer)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="其他变动" min-width="110" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b v-html="fmtAmt(row.other)" /></template>
                    <template v-else><el-input-number v-model="row.other" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('movement', row.rowId, 'other', row.other)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="期末余额" min-width="110" align="right">
                  <template #default="{ row }"><span class="amount-cell" :style="row.rowType==='summary'?'font-weight:600':''" v-html="fmtAmt(row.endBalance)" /></template>
                </el-table-column>
              </el-table>

              <!-- 重要转回明细 -->
              <h4 style="margin:0 0 8px">重要转回明细</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addReversalRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...reversalDetailRows, reversalDetailTotal]" border size="small" style="width:100%">
                <el-table-column label="单位名称" min-width="140">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b>{{ row.companyName }}</b></template>
                    <template v-else><el-input v-model="row.companyName" size="small" :disabled="isReadonly" @change="updateCell('reversalDetail', row.rowId, 'companyName', row.companyName)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="转回原因" min-width="120">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.reversalReason" size="small" :disabled="isReadonly" @change="updateCell('reversalDetail', row.rowId, 'reversalReason', row.reversalReason)" /></template>
                </el-table-column>
                <el-table-column label="原确认方式" min-width="120">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.originalMethod" size="small" :disabled="isReadonly" @change="updateCell('reversalDetail', row.rowId, 'originalMethod', row.originalMethod)" /></template>
                </el-table-column>
                <el-table-column label="转回依据" min-width="120">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.reversalBasis" size="small" :disabled="isReadonly" @change="updateCell('reversalDetail', row.rowId, 'reversalBasis', row.reversalBasis)" /></template>
                </el-table-column>
                <el-table-column label="转回金额" min-width="120" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.amount)" /></template>
                    <template v-else><el-input-number v-model="row.amount" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('reversalDetail', row.rowId, 'amount', row.amount)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button v-if="row.rowType==='dynamic'" :icon="Delete" text type="danger" size="small" @click="removeReversalRow(row.rowId)" /></template>
                </el-table-column>
              </el-table>
            </template>

            <!-- ═══ 6.7 Write-off Section ═══ -->
            <template v-if="section === 'writeOff'">
              <h4 style="margin:0 0 8px">核销汇总</h4>
              <div style="margin-bottom:16px;padding:8px 12px;background:#f5f7fa;border-radius:4px;display:flex;align-items:center;gap:12px">
                <span>本期核销总额：</span>
                <el-input-number v-model="writeOffAmount" :controls="false" size="small" :disabled="isReadonly"
                  @change="updateCell('writeOffAmount', '', 'amount', writeOffAmount)" style="width:200px" />
              </div>

              <h4 style="margin:0 0 8px">重要核销明细</h4>
              <el-button v-if="!isReadonly" size="small" :icon="Plus" @click="addWriteOffRow" style="margin-bottom:8px">添加行</el-button>
              <el-table :data="[...writeOffDetailRows, writeOffDetailTotal]" border size="small" style="width:100%">
                <el-table-column label="单位名称" min-width="140">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b>{{ row.companyName }}</b></template>
                    <template v-else><el-input v-model="row.companyName" size="small" :disabled="isReadonly" @change="updateCell('writeOffDetail', row.rowId, 'companyName', row.companyName)" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="票据性质" min-width="120">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.noteType" size="small" :disabled="isReadonly" @change="updateCell('writeOffDetail', row.rowId, 'noteType', row.noteType)" /></template>
                </el-table-column>
                <el-table-column label="核销金额" min-width="120" align="right">
                  <template #default="{ row }">
                    <template v-if="row.rowType==='summary'"><b class="amount-cell" v-html="fmtAmt(row.amount)" /></template>
                    <template v-else><el-input-number v-model="row.amount" :controls="false" size="small" :disabled="isReadonly" @change="updateCell('writeOffDetail', row.rowId, 'amount', row.amount)" style="width:100%" /></template>
                  </template>
                </el-table-column>
                <el-table-column label="核销原因" min-width="140">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.reason" size="small" :disabled="isReadonly" @change="updateCell('writeOffDetail', row.rowId, 'reason', row.reason)" /></template>
                </el-table-column>
                <el-table-column label="履行程序" min-width="140">
                  <template #default="{ row }"><el-input v-if="row.rowType!=='summary'" v-model="row.procedure" size="small" :disabled="isReadonly" @change="updateCell('writeOffDetail', row.rowId, 'procedure', row.procedure)" /></template>
                </el-table-column>
                <el-table-column v-if="!isReadonly" label="" width="50" align="center">
                  <template #default="{ row }"><el-button v-if="row.rowType==='dynamic'" :icon="Delete" text type="danger" size="small" @click="removeWriteOffRow(row.rowId)" /></template>
                </el-table-column>
              </el-table>
              <!-- Guidance fold for writeOff -->
              <details class="guidance-fold">
                <summary>📋 编制提示 — 核销披露</summary>
                <p v-for="(t, i) in DISCLOSURE_GUIDANCE.writeOff" :key="'wog-'+i">{{ t }}</p>
              </details>
              <!-- Note textarea for writeOff -->
              <div class="section-note">
                <label>说明：</label>
                <el-input type="textarea" :rows="3" :model-value="sectionNotes['writeOff'] || ''" placeholder="请输入核销相关说明..." :disabled="isReadonly" @input="(v: string) => onNoteChange('writeOff', v)" />
                <div class="note-actions">
                  <el-button size="small" disabled>🤖 AI</el-button>
                  <el-button size="small" disabled>💬 复核</el-button>
                </div>
              </div>
            </template>

            <!-- ═══ 6.8 Category Summary (SOE only) ═══ -->
            <template v-if="section === 'categorySummary' && variant === 'soe'">
              <el-table :data="[...categorySummaryRows, categorySummaryTotal]" border size="small" style="width:100%">
                <el-table-column label="票据种类" min-width="140">
                  <template #default="{ row }"><span :style="row.rowType==='summary'?'font-weight:600':''">{{ row.category }}</span></template>
                </el-table-column>
                <el-table-column label="期末余额" min-width="120" align="right">
                  <template #default="{ row }">
                    <el-tooltip content="取自审定表D1-1" placement="top">
                      <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endBalance)" />
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column label="期末坏账准备" min-width="120" align="right">
                  <template #default="{ row }">
                    <el-tooltip content="取自审定表D1-1" placement="top">
                      <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.endProvision)" />
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column label="期末账面价值" min-width="120" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.endBookValue)" /></template>
                </el-table-column>
                <el-table-column label="期初余额" min-width="120" align="right">
                  <template #default="{ row }">
                    <el-tooltip content="取自审定表D1-1" placement="top">
                      <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorBalance)" />
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column label="期初坏账准备" min-width="120" align="right">
                  <template #default="{ row }">
                    <el-tooltip content="取自审定表D1-1" placement="top">
                      <span class="amount-cell auto-fetch-cell" v-html="fmtAmt(row.priorProvision)" />
                    </el-tooltip>
                  </template>
                </el-table-column>
                <el-table-column label="期初账面价值" min-width="120" align="right">
                  <template #default="{ row }"><span class="amount-cell" v-html="fmtAmt(row.priorBookValue)" /></template>
                </el-table-column>
              </el-table>
            </template>

          </div>
        </el-card>
      </template>
  </div>
</template>

<style scoped>
.d1-disclosure { padding: 16px }
.d1-disclosure__header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap }
.d1-disclosure__toolbar { margin-left: auto }
.d1-section-card { margin-bottom: 12px }
.cross-sheet-summary { background: #ecf5ff; border-radius: 4px; padding: 12px; margin-bottom: 16px; display: flex; flex-wrap: wrap; gap: 16px; align-items: center }
.cross-sheet-summary .value { font-weight: 600; color: #409eff }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums }
.amount-negative { color: #f56c6c }
.auto-fetch-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px }
.guidance-fold { margin: 12px 0; border-left: 3px solid #409eff; background: #ecf5ff; padding: 10px 14px; border-radius: 0 4px 4px 0; font-size: 13px; color: #606266 }
.guidance-fold summary { cursor: pointer; font-weight: 500; color: #409eff }
.guidance-fold p { margin: 6px 0; line-height: 1.6 }
.section-note { margin-top: 12px; padding: 10px 0 }
.section-note label { font-size: 13px; font-weight: 500; color: #606266; display: block; margin-bottom: 6px }
.note-actions { margin-top: 6px; display: flex; gap: 8px }
</style>
