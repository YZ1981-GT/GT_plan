<template>
  <div class="h3-tab-impairment">
    <!-- 审计目标 / 过程（对齐源模板一、二） -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="一、审计目标：核实投资性房地产（成本模式）以恰当金额列报，减值迹象判断充分、减值测算准确。二、审计过程：先判断减值迹象（CAS8），再按类别/项目测算可收回金额与应补提。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H3-10" :context-project-id="projectId" />
        <GtIndexChip value="wp:H3-11" :context-project-id="projectId" />
        <el-tag size="small" type="info">迹象 {{ impairmentSigns.length }} 项</el-tag>
        <el-tag v-if="hasImpairmentSigns" size="small" type="warning">需测算 {{ signYesCount }} 项</el-tag>
        <el-tag v-if="hasOverProvision" size="small" type="danger">⑦&gt;⑥·核查不得转回</el-tag>
        <el-tag :type="prepValidation.ok ? 'success' : 'danger'" size="small">
          编制校验 {{ prepValidation.ok ? '通过' : `${prepValidation.messages.length}项` }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-11 可收回金额')">→ H3-11</el-tag>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        编制路径：迹象判断（CAS8）→ 按类别/项目测算 →
        ⑤可收回金额 = MAX(③公允−处置费, ④DCF) →
        ⑥应计提 = MAX(②账面−⑤, 0) →
        ⑧本期应补提 = MAX(⑥−⑦, 0)。
        账面②取原值−累计折旧（未扣减值）。
        <b>④须自 H3-11 回写并校验</b>；结果应与 H3-1 审定表、H3-7 折旧（含减值）勾稽。
        <b class="key-warn">【关键·不得转回】CAS8第17条：投资性房地产减值一经确认不得转回损益。</b>
      </p>
    </div>

    <el-alert title="减值测算（H3-10）— 仅成本模式适用；公允价值模式不计提减值" type="info" :closable="false" show-icon class="mode-alert" />

    <el-alert
      v-if="stocktakeConcernItems.length"
      type="warning"
      :closable="false"
      show-icon
      class="mode-alert"
      :title="`H3-9 盘点推送减值关注 ${stocktakeConcernItems.length} 项：${stocktakeConcernItems.map((i) => i.assetName).slice(0, 5).join('、')}${stocktakeConcernItems.length > 5 ? '…' : ''}`"
    />

    <!-- 一、减值迹象判断 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>一、减值迹象判断（CAS8 六项）</span>
          <el-button size="small" @click="generateAI('H3-10-signs')">AI</el-button>
        </div>
      </template>
      <el-table :data="impairmentSigns" border stripe size="small" class="audit-table">
        <el-table-column type="index" width="40" label="序号" />
        <el-table-column prop="indicator" label="减值迹象描述（CAS8）" min-width="320" />
        <el-table-column prop="exists" label="是否存在" width="110" align="center">
          <template #default="{ row, $index }">
            <el-select v-model="row.exists" size="small" :disabled="isReadonly" @change="onSignChange($index, row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="evidence" label="判断依据" min-width="200">
          <template #default="{ row, $index }">
            <el-input v-model="row.evidence" size="small" :disabled="isReadonly" placeholder="判断依据..." @change="onSignChange($index, row)" />
          </template>
        </el-table-column>
      </el-table>
      <div class="indication-summary">
        <el-alert :type="hasImpairmentSigns ? 'warning' : 'success'" :closable="false" show-icon>
          {{ hasImpairmentSigns ? `存在减值迹象（${signYesCount}项），须进行减值测试并填列测算表` : '未发现明显减值迹象；若账面仍有减值准备余额，请在说明中交代形成原因' }}
        </el-alert>
      </div>
    </el-card>

    <!-- 二、减值测算表 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>二、减值测算表</span>
          <div class="title-actions" v-if="!isReadonly">
            <el-button size="small" @click="handleImportH32">自 H3-2 带入②⑦</el-button>
            <el-button
              size="small"
              :disabled="!stocktakeConcernItems.length"
              @click="handleImportH39"
            >
              自 H3-9 引入关注{{ stocktakeConcernItems.length ? `（${stocktakeConcernItems.length}）` : '' }}
            </el-button>
            <el-button size="small" type="warning" plain @click="handleForceSyncH11">强制自 H3-11 回写④</el-button>
            <el-button size="small" @click="handleReconcileK11">核对 K11</el-button>
            <el-button size="small" type="primary" @click="handleAddCalcRow">+ 新增项目</el-button>
          </div>
        </div>
      </template>

      <el-table :data="impairmentCalcRows" border stripe size="small" class="audit-table" empty-text="暂无测算行：存在迹象时请新增或填写默认类别行">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="类别" width="120" fixed>
          <template #default="{ row, $index }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              placeholder="类别"
              @change="onCalcChange($index, 'category')"
            >
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="110" fixed>
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.assetName" size="small" @change="onCalcChange($index, 'assetName')" />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否存在减值迹象" width="110" align="center">
          <template #default="{ row, $index }">
            <el-select v-if="!isReadonly" v-model="row.hasIndication" size="small" clearable placeholder="—" @change="onCalcChange($index, 'hasIndication')">
              <el-option label="有" value="Y" />
              <el-option label="无" value="N" />
            </el-select>
            <el-tag v-else :type="row.hasIndication === 'Y' ? 'danger' : 'info'" size="small">
              {{ row.hasIndication === 'Y' ? '有' : row.hasIndication === 'N' ? '无' : '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="①减值迹象描述" min-width="130">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.indicationDesc" size="small" placeholder="简述迹象..." @change="onCalcChange($index, 'indicationDesc')" />
            <span v-else>{{ row.indicationDesc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②账面价值" width="115" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" v-model="row.bookValue" size="small" @change="onCalcChange($index, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="③公允−处置费" width="110" align="right">
          <template #default="{ row, $index }">
            <el-input-number v-if="!isReadonly" v-model="row.fairValueLessDisposal" :controls="false" size="small" @change="onCalcChange($index, 'fairValueLessDisposal')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fairValueLessDisposal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="④DCF现值" width="120" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'sync-stale': dcfStatus(row.rowId) === 'stale', 'sync-missing': dcfStatus(row.rowId) === 'missing-h11' }"
              :title="dcfStatusTitle(row.rowId)"
            >{{ fmtAmt(row.dcfValue) }}</span>
            <el-tag v-if="dcfStatus(row.rowId) === 'stale'" size="small" type="danger" class="sync-tag">过期</el-tag>
            <el-tag v-else-if="dcfStatus(row.rowId) === 'synced'" size="small" type="success" class="sync-tag">H11</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="⑤可收回金额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="MAX(③,④)">{{ fmtAmt(row.recoverableAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑥应计提" width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.impairmentAmount > 0 }]" title="MAX(②−⑤,0)">
              {{ fmtAmt(row.impairmentAmount) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="⑦已计提" width="100" align="right">
          <template #default="{ row, $index }">
            <WpAmountInput v-if="!isReadonly" v-model="row.alreadyProvided" size="small" @change="onCalcChange($index, 'alreadyProvided')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.alreadyProvided) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="⑧本期应补提" width="110" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'error-amount': rowSupplement(row) > 0.01, 'reversal-warn': row.difference < -0.01 }]"
              :title="row.difference < -0.01 ? `⑦多提 ${fmtAmt(-row.difference)}：核查处置结转；CAS下不得转回` : '⑧=MAX(⑥−⑦,0)'"
            >{{ fmtAmt(rowSupplement(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="H3-11" @change="onCalcChange($index, 'indexRef')" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row, $index }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCalcChange($index, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="44" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveCalc(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="totals-bar">
        <span>⑥应计提合计: <b class="amount-cell">{{ fmtAmt(totalImpairment) }}</b></span>
        <span>⑦已计提合计: <b class="amount-cell">{{ fmtAmt(alreadyProvidedTotal) }}</b></span>
        <span>⑧本期应补提: <b :class="['amount-cell', { 'error-amount': supplementTotal > 0.01 }]">{{ fmtAmt(supplementTotal) }}</b></span>
        <span v-if="overProvisionTotal > 0.01">
          多提: <b class="reversal-warn">{{ fmtAmt(overProvisionTotal) }}</b>
        </span>
      </div>

      <div class="category-block" v-if="impairmentCalcRows.length">
        <div class="category-title">按投资性房地产类别汇总</div>
        <el-table :data="categoryDisplayRows" border size="small" class="category-table">
          <el-table-column prop="category" label="类别" min-width="120" />
          <el-table-column label="行数" width="60" align="center" prop="rowCount" />
          <el-table-column label="②账面" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.bookValue) }}</template>
          </el-table-column>
          <el-table-column label="⑥应计提" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.impairmentAmount) }}</template>
          </el-table-column>
          <el-table-column label="⑦已计提" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.alreadyProvided) }}</template>
          </el-table-column>
          <el-table-column label="⑧应补提" width="110" align="right">
            <template #default="{ row }">{{ fmtAmt(row.supplement) }}</template>
          </el-table-column>
        </el-table>
      </div>

      <el-alert
        v-if="!dcfSyncSummary.ok"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="dcfSyncSummary.message + '——请点击「强制自 H3-11 回写④」'"
      />
      <el-alert
        :type="k11Reconcile.k11Amount == null ? 'info' : (k11Reconcile.isMatch ? 'success' : 'error')"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="k11Reconcile.message"
      />
      <el-alert
        v-if="hasOverProvision"
        type="error"
        :closable="false"
        show-icon
        style="margin-top:10px"
        title="存在⑦&gt;⑥（已计提超过应计提）。CAS8第17条：减值一经确认不得转回损益；负差仅可为处置/报废结转或前期差错更正，请在审计说明核实。"
      />
      <el-alert
        v-if="!prepValidation.ok"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="'编制校验：' + prepValidation.messages.join('；')"
      />
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-10')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-10')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        placeholder="填写指引：①六项迹象判断结论与依据；②测试单元（类别/项目）划分；③可收回金额方法及H3-11/评估来源；④⑧≠0的差异原因及拟调整；⑤⑦&gt;⑥时说明是否仅为处置结转；⑥与H3-1/H3-7勾稽情况。"
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card conclusion-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" @click="fillConclusionDraft">按测算生成草稿</el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        placeholder="（1）迹象识别□充分/□不充分；（2）测试项目___个，应计提⑥___、已计提⑦___、应补提⑧___；（3）差异□已调整/□不重大/□见调整分录；（4）CAS8第17条：未发现不当转回损益；（5）减值准备在重大方面□公允反映/□存在错报。"
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>提示（编制与复核要点）</summary>
      <ol>
        <li>取得/编制投资性房地产减值明细，验算加总，与总账及 H3-1、H3-2 审定数勾稽。</li>
        <li>按 CAS8 逐项判断六项迹象；关注长期空置、租金下降、房地产市场恶化等投资性房地产特有风险。</li>
        <li>复核可收回金额逻辑：比较③公允净额与④使用价值（DCF），明细见 H3-11；重大减值应获取评估/内部估值底稿。</li>
        <li>资产处置/报废时同步结转减值准备；对照上期估计与本期实际；与 H3-7 折旧（含减值）一致。</li>
        <li class="key-warn">【关键·不得转回】长期资产减值损失一经确认不得转回；警惕不当冲回调节利润。</li>
        <li>评价管理层对折现率与租金现金流假设的合理性；④须自 H3-11 回写并校验。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H3TabImpairment.vue — H3-10 减值测算（仅成本模式）
 * 对齐致同源模板：CAS8六项 + ①~⑧测算表 + H3-11回写校验
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH3Impairment, H3_10_ASSET_CATEGORIES, type ImpairmentCalcRow } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  impairmentSigns, impairmentCalcRows,
  hasImpairmentSigns, signYesCount, totalImpairment,
  alreadyProvidedTotal, supplementTotal, overProvisionTotal, hasOverProvision,
  categoryTotals, prepValidation, dcfSyncChecks, dcfSyncSummary,
  stocktakeConcernItems, k11Reconcile,
  updateSign, addCalcRow, removeCalcRow, updateCalcRow,
  forceSyncFromH11, buildConclusionDraft,
  importBookValuesFromH32, importFromStocktakeConcerns, reconcileWithK11,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const categories = H3_10_ASSET_CATEGORIES

const NOTE_KEY = 'H3-10-audit-note'
const CONCLUSION_KEY = 'H3-10-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const categoryDisplayRows = computed(() =>
  categoryTotals.value.filter((t) => t.rowCount > 0 || t.impairmentAmount > 0 || t.alreadyProvided > 0),
)

function rowSupplement(row: ImpairmentCalcRow): number {
  return Math.max(Number(row.difference) || 0, 0)
}

function onSignChange(index: number, row: any) { updateSign(index, row) }

function onCalcChange(index: number, field: keyof ImpairmentCalcRow) {
  updateCalcRow(index, field)
}

async function handleAddCalcRow() {
  const { value: name } = await ElMessageBox.prompt('项目名称', '新增减值测算', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name) addCalcRow(name)
}

async function handleRemoveCalc(rowId: string) {
  await ElMessageBox.confirm('确认删除该测算行？', '删除', { type: 'warning' })
  removeCalcRow(rowId)
}

function handleForceSyncH11() {
  const result = forceSyncFromH11()
  const unmatched = result.unmatched.length ? `；未匹配 H3-11：${result.unmatched.join('、')}` : ''
  ElMessage.success(`已强制回写④：更新 ${result.updated}，新建 ${result.created}${unmatched}`)
}

function handleImportH32() {
  const result = importBookValuesFromH32()
  ElMessage[result.updated + result.created > 0 ? 'success' : 'warning'](result.message)
}

function handleImportH39() {
  const result = importFromStocktakeConcerns()
  ElMessage[result.added + result.refreshed > 0 ? 'success' : 'warning'](result.message)
}

async function handleReconcileK11() {
  const result = await reconcileWithK11(props.projectId)
  if (result.k11Amount == null) ElMessage.warning(result.message)
  else if (result.isMatch) ElMessage.success(result.message)
  else ElMessage.error(result.message)
}

function fillConclusionDraft() {
  auditConclusion.value = buildConclusionDraft()
  saveAuditConclusion(auditConclusion.value)
  ElMessage.success('已按当前测算生成结论草稿，请审阅后定稿')
}

function dcfStatus(rowId: string): string {
  return dcfSyncChecks.value.find((c) => c.rowId === rowId)?.status ?? 'no-test'
}

function dcfStatusTitle(rowId: string): string {
  const c = dcfSyncChecks.value.find((x) => x.rowId === rowId)
  if (!c) return '④须自 H3-11 回写'
  if (c.status === 'synced') return `已与 H3-11 一致：④=${fmtAmt(c.h11Dcf)}`
  if (c.status === 'stale') return `过期：H3-10=${fmtAmt(c.h10Dcf)}，H3-11=${fmtAmt(c.h11Dcf)}，请强制回写`
  if (c.status === 'missing-h11') return 'H3-11 无同名项目或未测算，请先在 H3-11 完成'
  return '④须自 H3-11 回写'
}

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}

function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; line-height: 1.6; }
.key-warn { color: var(--el-color-danger); }
.mode-alert { margin-bottom: 16px; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.nav-chip { cursor: pointer; }
.indication-summary { margin-top: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.sync-stale { color: var(--el-color-danger); font-weight: 600; }
.sync-missing { color: var(--el-color-warning); }
.sync-tag { margin-left: 4px; vertical-align: middle; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.reversal-warn { color: var(--el-color-danger); font-weight: 700; text-decoration: underline dotted; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; flex-wrap: wrap; }
.category-block { margin-top: 12px; }
.category-title { font-size: 12px; font-weight: 600; margin-bottom: 6px; color: var(--el-text-color-secondary); }
.category-table { max-width: 720px; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.conclusion-card :deep(.el-textarea__inner) { background: #f6ffed; }
.action-btns { display: flex; gap: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
