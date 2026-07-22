<template>
  <div class="h1-tab-impairment">
    <!-- 审计目标 / 过程（对齐源模板一、二） -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px"
      title="一、审计目标：确认固定资产减值准备以恰当金额列报。二、审计过程：先判断减值迹象（CAS8），再按单项资产/资产组测算可收回金额与应补提。" />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H1-14" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-15" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-4" :context-project-id="projectId" />
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">迹象 {{ state.indications.value.length }} 项</el-tag>
        <el-tag v-if="hasImpairmentSign" size="small" type="warning">需测算 {{ signCount }} 项</el-tag>
        <el-tag v-if="state.hasOverProvision.value" size="small" type="danger">⑦&gt;⑥·核查不得转回</el-tag>
        <el-tag :type="state.prepValidation.value.ok ? 'success' : 'danger'" size="small">
          编制校验 {{ state.prepValidation.value.ok ? '通过' : `${state.prepValidation.value.messages.length}项` }}
        </el-tag>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        编制路径：迹象判断（CAS8）→ 按单项/资产组测算 →
        ⑤可收回金额 = MAX(③公允−处置费, ④DCF) →
        ⑥应计提 = MAX(②账面−⑤, 0) →
        ⑧本期应补提 = MAX(⑥−⑦, 0)。
        账面②取原值−累计折旧（未扣减值）。
        <b>④须强制自 H1-15 回写并校验</b>；⑧与 K11 固定资产减值交叉核对。
        <b class="key-warn">【关键·不得转回】CAS8第17条：固定资产减值一经确认不得转回损益。</b>
      </p>
    </div>

    <el-alert
      v-if="stocktakeConcernItems.length"
      type="warning"
      :closable="false"
      show-icon
      style="margin-bottom:12px"
      :title="`H1-11 监盘推送减值关注 ${stocktakeConcernItems.length} 项：${stocktakeConcernItems.map((i: any) => i.assetName).slice(0, 5).join('、')}${stocktakeConcernItems.length > 5 ? '…' : ''}`"
    />

    <!-- H1-4 闲置减值主动预警：有迹象且未计提 → 红色待处理 -->
    <el-alert
      v-if="idleSignCount > 0"
      type="error"
      :closable="false"
      show-icon
      style="margin-bottom:12px"
    >
      <template #title>
        H1-4 闲置检查发现 {{ idleSignCount }} 项资产存在减值迹象且尚未计提减值，建议引入本表测算：{{ idleSignAssets.map(a => a.name).slice(0, 5).join('、') }}{{ idleSignAssets.length > 5 ? '…' : '' }}
      </template>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="primary"
        style="margin-top:6px"
        @click="handleImportIdle"
      >一键引入 H1-4 闲置资产</el-button>
    </el-alert>

    <!-- 一、减值迹象6项判断 -->
    <el-card shadow="never" class="indication-card">
      <template #header>
        <div class="section-title">
          <span>一、减值迹象判断（CAS8 六项）</span>
          <div class="title-actions">
            <el-button size="small" type="default" link @click="handleReview('H1-14-indications')">💬 复核</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.indications.value" border stripe size="small">
        <el-table-column type="index" width="40" />
        <el-table-column prop="description" label="减值迹象描述（CAS8）" min-width="350" />
        <el-table-column prop="result" label="判断" width="140" align="center">
          <template #default="{ row }">
            <el-radio-group v-model="row.result" :disabled="isReadonly" size="small" @change="onIndicationChange(row, 'result')">
              <el-radio-button value="Y">有</el-radio-button>
              <el-radio-button value="N">无</el-radio-button>
              <el-radio-button value="NA">N/A</el-radio-button>
            </el-radio-group>
          </template>
        </el-table-column>
        <el-table-column prop="explanation" label="说明" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.explanation" size="small" placeholder="判断依据..." @change="onIndicationChange(row, 'explanation')" />
            <span v-else>{{ row.explanation }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="indication-summary">
        <el-alert :type="hasImpairmentSign ? 'warning' : 'success'" :closable="false" show-icon>
          {{ hasImpairmentSign ? `存在减值迹象（${signCount}项），须进行减值测试并填列测算表` : '未发现明显减值迹象；若账面仍有减值准备余额，请在说明中交代形成原因' }}
        </el-alert>
      </div>
    </el-card>

    <!-- 二、减值测算表（始终展示，对齐源模板主表） -->
    <el-card shadow="never" class="calc-card">
      <template #header>
        <div class="section-title">
          <span>二、减值测算表</span>
          <div class="title-actions" v-if="!isReadonly">
            <el-button
              size="small"
              :disabled="!idleCount"
              @click="handleImportIdle"
            >
              自 H1-4 引入闲置{{ idleCount ? `（${idleCount}）` : '' }}
            </el-button>
            <el-button
              size="small"
              type="warning"
              plain
              :disabled="!state.groups.value.length"
              @click="handleForceSyncH15"
            >
              强制自 H1-15 回写④
            </el-button>
            <el-button size="small" @click="handleReconcileK11">核对 K11</el-button>
            <el-button size="small" type="primary" @click="handleAddCalcRow">+ 新增资产组</el-button>
          </div>
        </div>
      </template>

      <el-table :data="state.calcRows.value" border stripe size="small" empty-text="暂无测算行：存在迹象时请新增或自 H1-4 引入">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="固定资产类别" width="120" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              default-first-option
              placeholder="类别"
              @change="onCalcChange(row, 'category')"
            >
              <el-option v-for="c in categories" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="项目名称" min-width="110" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetGroup" size="small" @change="onCalcChange(row, 'assetGroup')" />
            <span v-else>{{ row.assetGroup }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否存在减值迹象" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.hasIndication"
              size="small"
              clearable
              placeholder="—"
              @change="onCalcChange(row, 'hasIndication')"
            >
              <el-option label="有" value="Y" />
              <el-option label="无" value="N" />
            </el-select>
            <el-tag v-else :type="row.hasIndication === 'Y' ? 'danger' : 'info'" size="small">
              {{ row.hasIndication === 'Y' ? '有' : row.hasIndication === 'N' ? '无' : '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="①减值迹象描述" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indicationDesc" size="small" placeholder="简述迹象..." @change="onCalcChange(row, 'indicationDesc')" />
            <span v-else>{{ row.indicationDesc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="②账面价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCalcChange(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="③公允−处置费" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.fairValueLessDisposal" :controls="false" size="small" @change="onCalcChange(row, 'fairValueLessDisposal')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.fairValueLessDisposal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="④DCF现值" width="130" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'sync-stale': dcfStatus(row.rowId) === 'stale', 'sync-missing': dcfStatus(row.rowId) === 'missing-h15' }"
              :title="dcfStatusTitle(row.rowId)"
            >{{ fmtAmt(row.dcfValue) }}</span>
            <el-tag v-if="dcfStatus(row.rowId) === 'stale'" size="small" type="danger" class="sync-tag">过期</el-tag>
            <el-tag v-else-if="dcfStatus(row.rowId) === 'synced'" size="small" type="success" class="sync-tag">H15</el-tag>
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
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.alreadyProvided" :controls="false" size="small" @change="onCalcChange(row, 'alreadyProvided')" />
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
        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" placeholder="H1-15" @change="onCalcChange(row, 'indexRef')" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCalcChange(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="48" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="handleRemoveCalc(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 合计 + 分类汇总 -->
      <div class="totals-bar">
        <span>⑥应计提合计: <b class="amount-cell">{{ fmtAmt(state.impairmentTotal.value) }}</b></span>
        <span>⑦已计提合计: <b class="amount-cell">{{ fmtAmt(state.alreadyProvidedTotal.value) }}</b></span>
        <span>⑧本期应补提: <b :class="['amount-cell', { 'error-amount': state.supplementTotal.value > 0.01 }]">{{ fmtAmt(state.supplementTotal.value) }}</b></span>
        <span v-if="state.overProvisionTotal.value > 0.01">
          多提: <b class="reversal-warn">{{ fmtAmt(state.overProvisionTotal.value) }}</b>
        </span>
      </div>

      <div class="category-block" v-if="state.calcRows.value.length">
        <div class="category-title">按固定资产类别汇总</div>
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
        v-if="!state.dcfSyncSummary.value.ok"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="state.dcfSyncSummary.value.message + '——请点击「强制自 H1-15 回写④」'"
      />
      <el-alert
        :type="state.k11Reconcile.value.k11Amount == null ? 'info' : (state.k11Reconcile.value.isMatch ? 'success' : 'error')"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="state.k11Reconcile.value.message"
      />
      <el-alert
        v-if="state.hasOverProvision.value"
        type="error"
        :closable="false"
        show-icon
        style="margin-top:10px"
        title="存在⑦&gt;⑥（已计提超过应计提）。CAS8第17条：固定资产减值一经确认不得转回损益；负差仅可为处置/报废结转或前期差错更正，请在审计说明核实。"
      />
      <el-alert
        v-if="!state.prepValidation.value.ok"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:10px"
        :title="'编制校验：' + state.prepValidation.value.messages.join('；')"
      />
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title"><span>三、审计说明</span></div>
      </template>
      <el-input
        v-model="noteLocal"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写指引：①六项迹象判断结论与依据（闲置见H1-4）；②测试单元（单项/资产组）划分；③可收回金额方法及H1-15/评估来源；④⑧≠0的差异原因及拟调整；⑤⑦&gt;⑥时说明是否仅为处置结转；⑥上期估计与本期实际对照。"
        @change="persistNote"
      />
    </el-card>

    <!-- 四、审计结论（结构化模板） -->
    <el-card shadow="never" class="note-card conclusion-card">
      <template #header>
        <div class="section-title">
          <span>四、审计结论</span>
          <el-button v-if="!isReadonly" size="small" @click="fillConclusionDraft">按测算生成草稿</el-button>
        </div>
      </template>
      <el-input
        v-model="conclusionLocal"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="（1）迹象识别□充分/□不充分；（2）测试资产组___个，应计提⑥___、已计提⑦___、应补提⑧___；（3）差异□已调整/□不重大/□见调整分录；（4）CAS8第17条：未发现不当转回损益；（5）减值准备在重大方面□公允反映/□存在错报。"
        @change="persistConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>提示（编制与复核要点）</summary>
      <ol>
        <li>取得/编制减值明细，验算加总，与总账及 H1-1、H1-2 审定数勾稽；关注未纳入评估范围的资产。</li>
        <li>按 CAS8 逐项判断六项迹象；即使本期未补提，存在迹象也应在说明中披露并考虑测算。</li>
        <li>复核可收回金额逻辑：比较③公允净额与④使用价值（DCF），明细见 H1-15；重大减值应获取评估/内部估值底稿。</li>
        <li>资产处置/报废时同步结转减值准备；对照上期估计与本期实际。</li>
        <li class="key-warn">【关键·不得转回】长期资产减值损失一经确认不得转回；警惕「大洗澡」后次年冲回调节利润。</li>
        <li>评价管理层对资产组划分、折现率与现金流假设的合理性；④须自 H1-15 回写并校验；⑧本期补提与 K11 固定资产减值勾稽。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import { useH1Impairment, H1_14_ASSET_CATEGORIES, type ImpairmentCalcRow } from '../../composables/useH1Impairment'
import { evaluateImpairmentIndication } from '../../composables/useH1IdleCheck'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const state = useH1Impairment(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const categories = H1_14_ASSET_CATEGORIES
const noteLocal = ref('')
const conclusionLocal = ref('')

onMounted(syncNoteFromState)
watch(() => state.auditNote.value, (v) => { if (v !== noteLocal.value) noteLocal.value = v || '' })
watch(() => state.auditConclusion.value, (v) => { if (v !== conclusionLocal.value) conclusionLocal.value = v || '' })

function syncNoteFromState() {
  noteLocal.value = state.auditNote.value || ''
  conclusionLocal.value = state.auditConclusion.value || ''
  // 兼容旧键（组件本地曾单独持久化）
  if (!noteLocal.value) {
    const n = props.allResponses.get('H1-14-audit-note')
    if (n?.remark) noteLocal.value = String(n.remark)
  }
  if (!conclusionLocal.value) {
    const c = props.allResponses.get('H1-14-audit-conclusion')
    if (c?.remark) conclusionLocal.value = String(c.remark)
  }
}

function persistNote() { state.saveNote(noteLocal.value) }
function persistConclusion() { state.saveConclusion(conclusionLocal.value) }

const hasImpairmentSign = computed(() => state.indications.value.some((i: any) => i.result === 'Y'))
const signCount = computed(() => state.indications.value.filter((i: any) => i.result === 'Y').length)
const idleCount = computed(() => state.idleAssetsAvailable.value.length)

// ─── H1-4 → H1-14 闲置减值主动预警（EventBus + allResponses 兜底）──────────────
const idleSignCount = ref(0)
const idleSignAssets = ref<Array<{ name: string; netValue: number }>>([])

function _computeIdleSignFromResponses() {
  const item = props.allResponses.get('H1-4-rows')
  if (!item?.remark) { idleSignCount.value = 0; idleSignAssets.value = []; return }
  try {
    const rows = JSON.parse(item.remark)
    if (!Array.isArray(rows)) return
    const flagged = rows.filter((r: any) => evaluateImpairmentIndication(r) && r.hasImpairment !== 'Y')
    idleSignCount.value = flagged.length
    idleSignAssets.value = flagged.map((r: any) => ({
      name: r.name || r.assetNo || '未命名资产',
      netValue: Number(r.netValue) || 0,
    }))
  } catch { /* ignore */ }
}

function _onIdleSign(payload: any) {
  // 仅响应本底稿（同 wpId）的预警
  if (payload?.wpId && props.wpId && payload.wpId !== props.wpId) return
  idleSignCount.value = Number(payload?.count) || 0
  idleSignAssets.value = Array.isArray(payload?.assets) ? payload.assets : []
}

onMounted(() => {
  _computeIdleSignFromResponses()
  eventBus.on('h1:idle-impairment-sign' as any, _onIdleSign)
})
onUnmounted(() => {
  eventBus.off('h1:idle-impairment-sign' as any, _onIdleSign)
})

const stocktakeConcernItems = computed(() => {
  const item = props.allResponses.get('H1-14-stocktake-concerns')
  if (!item?.remark) return [] as any[]
  try {
    const p = JSON.parse(item.remark)
    return Array.isArray(p?.items) ? p.items : []
  } catch {
    return []
  }
})

const categoryDisplayRows = computed(() =>
  state.categoryTotals.value.filter((t) => t.rowCount > 0 || t.impairmentAmount > 0 || t.alreadyProvided > 0),
)

function rowSupplement(row: ImpairmentCalcRow): number {
  return Math.max(Number(row.difference) || 0, 0)
}

function onIndicationChange(row: any, field: string) {
  state.updateIndication(row.key, field as any, row[field])
}
function onCalcChange(row: any, field: string) {
  state.updateCalcRow(row.rowId, field as any, row[field])
}

async function handleAddCalcRow() {
  const { value: name } = await ElMessageBox.prompt('资产组/项目名称', '新增减值测算', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
  })
  if (name) state.addCalcRow(name)
}

async function handleRemoveCalc(rowId: string) {
  await ElMessageBox.confirm('确认删除该测算行？', '删除', { type: 'warning' })
  state.removeCalcRow(rowId)
}

function handleImportIdle() {
  const result = state.importFromIdleAssets()
  ElMessage.success(`自 H1-4 引入：新增 ${result.added}，刷新 ${result.skipped}，共 ${result.total} 项`)
}

function handleForceSyncH15() {
  const result = state.forceSyncFromH15()
  const unmatched = result.unmatched.length
    ? `；未匹配 H1-15：${result.unmatched.join('、')}`
    : ''
  ElMessage.success(`已强制回写④：更新 ${result.updated}，新建 ${result.created}${unmatched}`)
}

async function handleReconcileK11() {
  const result = await state.reconcileWithK11(props.projectId)
  if (result.k11Amount == null) ElMessage.warning(result.message)
  else if (result.isMatch) ElMessage.success(result.message)
  else ElMessage.error(result.message)
}

function dcfStatus(rowId: string): string {
  return state.dcfSyncChecks.value.find((c) => c.rowId === rowId)?.status ?? 'no-test'
}

function dcfStatusTitle(rowId: string): string {
  const c = state.dcfSyncChecks.value.find((x) => x.rowId === rowId)
  if (!c) return '④须自 H1-15 回写'
  if (c.status === 'synced') return `已与 H1-15 一致：④=${fmtAmt(c.h15Dcf)}`
  if (c.status === 'stale') return `过期：H1-14=${fmtAmt(c.h14Dcf)}，H1-15=${fmtAmt(c.h15Dcf)}，请强制回写`
  if (c.status === 'missing-h15') return 'H1-15 无同名资产组，请先在 H1-15 测算'
  return '④须自 H1-15 回写'
}

function fillConclusionDraft() {
  conclusionLocal.value = state.buildConclusionDraft()
  persistConclusion()
  ElMessage.success('已按当前测算生成结论草稿，请审阅后定稿')
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-impairment { padding: 16px; font-size: var(--wp-font-size, 13px); }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.key-warn { color: var(--el-color-danger); }
.indication-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.indication-summary { margin-top: 12px; }
.calc-card { margin-bottom: 16px; }
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
.note-card { margin-bottom: 12px; }
.conclusion-card :deep(.el-textarea__inner) { background: #f6ffed; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
