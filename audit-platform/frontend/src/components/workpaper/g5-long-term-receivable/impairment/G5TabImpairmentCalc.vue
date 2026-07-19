<!--
  G5TabImpairmentCalc.vue — G5-10 长期应收款坏账准备测算表

  对齐源模板：
    (一) 单项计提
    (二) 信用期组合（默认 4 段，可自定义）
    (三) 账龄组合（3年段 / 5年段 / 自定义，多组合）

  公式：应计提③ = ①×②；差异⑤ = ③−④
-->
<template>
  <div class="g5-impairment-calc">
    <div class="section-head">
      <h3 class="sheet-title">G5-10 长期应收款坏账准备测算表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-10" />
        <GtIndexChip value="wp:G5-3" />
        <GtIndexChip value="wp:G5-9" />
        <el-button size="small" @click="openReviewDialog('G5-10-impairment-calc')">💬复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：独立测算长期应收款坏账准备（单项 / 信用期组合 / 账龄组合），验证企业计提是否充分、准确，并与 G5-3、G5-9 勾稽。
    </el-alert>

    <details class="prep-hint top-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>结构对齐源模板：单项 → 信用期组合 → 账龄组合；不适用的信用期行可删除。</li>
        <li>公式：应计提③ = 审定余额① × 损失率②；差异⑤ = 应计提③ − 账面准备④。</li>
        <li>账龄段支持「3年段 / 5年段 / 自定义」枚举（默认 5 年双标签，对齐模板）；切换后各组合账龄行自动同步并保留已填数。</li>
        <li>逾期从确认资产凭证日期起算，需考虑信用期；组合划分应与 G5-8 会计政策及附注一致。</li>
        <li>G5-9 同步的阶段写入（一）单项行的 Stage 标记，便于与三阶段划分对照。</li>
        <li>可用「从 G5-2/G5-3 灌数」带入审定余额与账面准备；差异可用「推送差异至 G5-4」生成调整分录。</li>
      </ul>
    </details>

    <div class="aging-toolbar">
      <span class="muted">账龄口径</span>
      <el-select
        :model-value="calc.agingPreset.value"
        size="small"
        style="width: 110px"
        :disabled="isReadonly"
        @change="onAgingPresetChange"
      >
        <el-option label="3年段" value="THREE_YEAR" />
        <el-option label="5年段" value="FIVE_YEAR" />
        <el-option label="自定义" value="CUSTOM" />
      </el-select>
      <el-tag size="small" type="info">{{ calc.agingSegments.value.length }} 段</el-tag>

      <span class="muted" style="margin-left: 12px">信用期口径</span>
      <el-select
        :model-value="calc.creditPreset.value"
        size="small"
        style="width: 110px"
        :disabled="isReadonly"
        @change="onCreditPresetChange"
      >
        <el-option label="默认4段" value="DEFAULT" />
        <el-option label="自定义" value="CUSTOM" />
      </el-select>
      <el-tag size="small" type="info">{{ calc.creditSegments.value.length }} 段</el-tag>

      <el-button
        size="small"
        type="primary"
        plain
        :disabled="isReadonly"
        @click="onPullFromSource"
      >从 G5-2/G5-3 灌数</el-button>
      <el-button
        size="small"
        type="warning"
        :disabled="isReadonly || Math.abs(calc.grandTotal.value.diff) < 0.01"
        @click="onPushDiffs"
      >推送差异至 G5-4</el-button>
    </div>

    <el-alert
      v-if="calc.diffAlert.value"
      type="warning"
      :closable="false"
      show-icon
      :title="calc.diffAlert.value"
      style="margin-bottom: 10px"
    />

    <!-- (一) 单项 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（一）单项计提坏账准备</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="calc.addSingleRow()">添加债务人</el-button>
      </div>
      <el-table :data="calc.singleRows.value" size="small" border stripe>
        <el-table-column label="债务人/项目" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.label"
              size="small"
              @change="(v: string) => calc.updateSingleCell(row.rowId, 'label', v)"
            />
            <span v-else>{{ row.label || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="Stage" width="90" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.stageGroup" size="small" type="info">{{ row.stageGroup }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="审定余额①" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.auditedBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => calc.updateSingleCell(row.rowId, 'auditedBalance', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="损失率②" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.lossRate"
              :controls="false"
              :step="0.01"
              :max="1"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => calc.updateSingleCell(row.rowId, 'lossRate', v ?? 0)"
            />
            <span v-else>{{ fmtPct(row.lossRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="应计提③" width="120" align="right">
          <template #default="{ row }">
            <el-tooltip content="③ = ① × ②" placement="top">
              <span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="账面准备④" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.bookProvision"
              :controls="false"
              size="small"
              style="width:100%"
              @update:model-value="(v: number) => calc.updateSingleCell(row.rowId, 'bookProvision', v ?? 0)"
            />
            <span v-else>{{ fmtAmt(row.bookProvision) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异⑤" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计提依据" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.basis"
              size="small"
              @change="(v: string) => calc.updateSingleCell(row.rowId, 'basis', v)"
            />
            <span v-else>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="80">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.indexRef"
              size="small"
              @change="(v: string) => calc.updateSingleCell(row.rowId, 'indexRef', v)"
            />
            <span v-else>{{ row.indexRef || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" align="center">
          <template #default="{ row }">
            <el-button type="danger" text size="small" @click="calc.removeSingleRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="subtotal-line">
        单项小计 — 应计提 {{ fmtAmt(calc.singleTotal.value.expected) }}，账面 {{ fmtAmt(calc.singleTotal.value.book) }}，差异 {{ fmtAmt(calc.singleTotal.value.diff) }}
      </div>
    </div>

    <!-- (二) 信用期 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（二）按组合计提坏账准备 — 信用期</h4>
        <span class="hint-inline">【不适用的行项请删除】</span>
      </div>
      <p class="aging-hint">逾期从确认资产凭证日期起计算，逾期需考虑信用期。</p>
      <div v-for="group in calc.creditGroups.value" :key="group.groupId" class="aging-group">
        <el-table :data="group.rows.filter((r) => !r.archived)" size="small" border stripe>
          <el-table-column prop="label" label="信用期/逾期" width="160" />
          <el-table-column label="审定余额①" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.auditedBalance"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateCreditCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0)"
              />
              <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="损失率②" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.lossRate"
                :controls="false"
                :step="0.01"
                :max="1"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateCreditCell(group.groupId, row.rowId, 'lossRate', v ?? 0)"
              />
              <span v-else>{{ fmtPct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="应计提③" width="120" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span></template>
          </el-table-column>
          <el-table-column label="账面准备④" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookProvision"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateCreditCell(group.groupId, row.rowId, 'bookProvision', v ?? 0)"
              />
              <span v-else>{{ fmtAmt(row.bookProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑤" width="110" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.basis"
                size="small"
                @change="(v: string) => calc.updateCreditCell(group.groupId, row.rowId, 'basis', v)"
              />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button type="danger" text size="small" @click="calc.removeCreditRow(group.groupId, row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div class="subtotal-line">
        信用期小计 — 应计提 {{ fmtAmt(calc.creditTotal.value.expected) }}，账面 {{ fmtAmt(calc.creditTotal.value.book) }}，差异 {{ fmtAmt(calc.creditTotal.value.diff) }}
      </div>
    </div>

    <!-- (三) 账龄组合 -->
    <div class="ecl-block">
      <div class="block-header">
        <h4 class="block-title">（三）其他组合计提坏账准备 — 账龄</h4>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="calc.addAgingGroup()">添加组合</el-button>
      </div>
      <p class="aging-hint">默认 5 年段标签对齐源模板「账龄/逾期」双口径；可切换 3 年段或自定义段名。</p>

      <div v-for="(group, gIdx) in calc.agingGroups.value" :key="group.groupId" class="aging-group">
        <div class="group-header">
          <el-input
            v-if="!isReadonly"
            :model-value="group.groupName"
            size="small"
            placeholder="组合名称"
            style="width:180px"
            @change="(v: string) => calc.updateGroupName(group.groupId, v)"
          />
          <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
          <el-button
            v-if="!isReadonly"
            type="danger"
            text
            size="small"
            @click="calc.removeAgingGroup(group.groupId)"
          >删除组合</el-button>
        </div>
        <el-table :data="group.rows.filter((r) => !r.archived)" size="small" border stripe>
          <el-table-column prop="label" label="账龄" width="180" />
          <el-table-column label="审定余额①" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.auditedBalance"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateAgingCell(group.groupId, row.rowId, 'auditedBalance', v ?? 0)"
              />
              <span v-else>{{ fmtAmt(row.auditedBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="损失率②" width="100" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.lossRate"
                :controls="false"
                :step="0.01"
                :max="1"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateAgingCell(group.groupId, row.rowId, 'lossRate', v ?? 0)"
              />
              <span v-else>{{ fmtPct(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="应计提③" width="120" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.expectedProvision) }}</span></template>
          </el-table-column>
          <el-table-column label="账面准备④" width="120" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="row.bookProvision"
                :controls="false"
                size="small"
                style="width:100%"
                @update:model-value="(v: number) => calc.updateAgingCell(group.groupId, row.rowId, 'bookProvision', v ?? 0)"
              />
              <span v-else>{{ fmtAmt(row.bookProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异⑤" width="110" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', { 'diff-warn': Math.abs(row.difference) >= 0.01 }]">{{ fmtAmt(row.difference) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提依据" min-width="120">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.basis"
                size="small"
                @change="(v: string) => calc.updateAgingCell(group.groupId, row.rowId, 'basis', v)"
              />
              <span v-else>{{ row.basis || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="索引" width="80">
            <template #default="{ row }">
              <el-input
                v-if="!isReadonly"
                :model-value="row.indexRef"
                size="small"
                @change="(v: string) => calc.updateAgingCell(group.groupId, row.rowId, 'indexRef', v)"
              />
              <span v-else>{{ row.indexRef || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="group-sub">
          小计 — 应计提 {{ fmtAmt(sumGroup(group)) }}
        </div>
      </div>
      <div class="subtotal-line">
        账龄合计 — 应计提 {{ fmtAmt(calc.agingTotal.value.expected) }}，账面 {{ fmtAmt(calc.agingTotal.value.book) }}，差异 {{ fmtAmt(calc.agingTotal.value.diff) }}
      </div>
      <div class="subtotal-line grand">
        总计 — 应计提 {{ fmtAmt(calc.grandTotal.value.expected) }}，账面 {{ fmtAmt(calc.grandTotal.value.book) }}，差异 {{ fmtAmt(calc.grandTotal.value.diff) }}
      </div>
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="isReadonly"
      :note="auditNote"
      :conclusion="conclusion"
      conclusion-ai-section="impairment-calc-conclusion"
      note-placeholder="填写审计说明：可概述抽样阈值、损失率确定逻辑、与 G5-8/G5-9 政策及阶段划分的印证、重大差异处理。"
      conclusion-placeholder="填写坏账准备测算结论：A、计提充分准确。B、除下述事项外未见异常。C、存在重大差异须调整。"
      @update:note="saveAuditNote"
      @update:conclusion="onConclusionUpdate"
    />

    <!-- 自定义账龄对话框 -->
    <el-dialog v-model="showAgingDialog" title="自定义账龄段" width="420px" destroy-on-close @close="cancelAgingDialog">
      <p class="muted">每行一个账龄段名称（至少 2 段，最多 10 段）。</p>
      <el-input v-model="agingDraft" type="textarea" :autosize="{ minRows: 6, maxRows: 12 }" placeholder="例：&#10;6个月以内&#10;6个月-1年&#10;1-2年&#10;2年以上" />
      <template #footer>
        <el-button @click="cancelAgingDialog">取消</el-button>
        <el-button type="primary" @click="confirmAgingCustom">确定</el-button>
      </template>
    </el-dialog>

    <!-- 自定义信用期对话框 -->
    <el-dialog v-model="showCreditDialog" title="自定义信用期段" width="420px" destroy-on-close @close="cancelCreditDialog">
      <p class="muted">每行一个信用期/逾期段名称（至少 2 段，最多 10 段）。</p>
      <el-input v-model="creditDraft" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }" placeholder="例：&#10;合同期内&#10;逾期1-60天&#10;逾期60天以上" />
      <template #footer>
        <el-button @click="cancelCreditDialog">取消</el-button>
        <el-button type="primary" @click="confirmCreditCustom">确定</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, watch, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useG5ImpairmentCalc, type G5EclGroup, type G5AgingPreset, type G5CreditPreset } from '../../composables/useG5ImpairmentCalc'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import GtIndexChip from '../../GtIndexChip.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})
const isReadonly = computed(() => props.isReadonly)
const calc = useG5ImpairmentCalc()
const conclusion = ref('')
const auditNote = ref('')

const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const G5_NOTE_KEY = 'G5-10-audit-note'
const G5_CONCLUSION_KEY = 'G5-10-audit-conclusion'
const G5_ROWS_KEY = G5_ITEM_IDS.G5_10_ROWS

const showAgingDialog = ref(false)
const showCreditDialog = ref(false)
const agingDraft = ref('')
const creditDraft = ref('')
let persistReady = false

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function onConclusionUpdate(val: string): void {
  conclusion.value = val
}
watch(conclusion, (val) => {
  if (props.isReadonly || !persistReady) return
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val ?? '' })
})

function persistRows() {
  if (!persistReady || props.isReadonly) return
  const json = calc.serialize()
  g5Notes.debouncedSave(G5_ROWS_KEY, { remark: json, conclusion: json })
}

watch(() => calc.payload.value, () => persistRows(), { deep: true })

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
  const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ROWS_KEY))
  if (saved) {
    calc.loadFromRaw(saved)
  } else if (props.htmlData?.impairmentCalc) {
    const data = props.htmlData.impairmentCalc
    if (data.rows) calc.loadRows(data.rows)
    if (data.conclusion && !conclusion.value) conclusion.value = data.conclusion
  }
  persistReady = true
  window.addEventListener('g5:stage-updated', onStageUpdated as EventListener)
  window.addEventListener('g5:aging-preset-changed', onAgingSynced as EventListener)
})

onBeforeUnmount(() => {
  window.removeEventListener('g5:stage-updated', onStageUpdated as EventListener)
  window.removeEventListener('g5:aging-preset-changed', onAgingSynced as EventListener)
})

function onAgingSynced(e: Event): void {
  if (props.isReadonly) return
  const d = (e as CustomEvent).detail as { preset?: G5AgingPreset; customLabels?: string[] } | undefined
  if (!d?.preset) return
  if (calc.setAgingPreset(d.preset, d.customLabels)) {
    ElMessage.success('已同步 G5-2 账龄口径')
  }
}

function onStageUpdated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (detail?.written) {
    void g5Notes.loadAll().then(() => {
      const saved = readCanonicalRaw(g5Notes.allResponses.value.get(G5_ROWS_KEY))
      if (saved) calc.loadFromRaw(saved)
    })
    return
  }
  const updates = detail?.updates
  if (!Array.isArray(updates) || !updates.length) return
  const n = calc.applyStageUpdates(updates)
  persistRows()
  ElMessage.success(`已同步 ${n} 条阶段至单项计提`)
}

function onAgingPresetChange(val: G5AgingPreset) {
  if (val === 'CUSTOM') {
    agingDraft.value = (calc.customAgingLabels.value.length
      ? calc.customAgingLabels.value
      : calc.agingSegments.value.map((s) => s.label)
    ).join('\n')
    showAgingDialog.value = true
    return
  }
  calc.setAgingPreset(val)
}

function confirmAgingCustom() {
  const labels = agingDraft.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (calc.setAgingPreset('CUSTOM', labels)) {
    showAgingDialog.value = false
  }
}
function cancelAgingDialog() {
  showAgingDialog.value = false
}

function onCreditPresetChange(val: G5CreditPreset) {
  if (val === 'CUSTOM') {
    creditDraft.value = (calc.customCreditLabels.value.length
      ? calc.customCreditLabels.value
      : calc.creditSegments.value.map((s) => s.label)
    ).join('\n')
    showCreditDialog.value = true
    return
  }
  calc.setCreditPreset(val)
}

function confirmCreditCustom() {
  const labels = creditDraft.value.split('\n').map((l) => l.trim()).filter(Boolean)
  if (calc.setCreditPreset('CUSTOM', labels)) {
    showCreditDialog.value = false
  }
}
function cancelCreditDialog() {
  showCreditDialog.value = false
}

function onPullFromSource() {
  if (props.isReadonly) return
  calc.pullFromG52AndG53(g5Notes.allResponses.value)
  persistRows()
}

function onPushDiffs() {
  if (props.isReadonly) return
  calc.pushDiffsToG54(g5Notes.allResponses.value, (itemId, data) => {
    g5Notes.debouncedSave(itemId, data)
  })
}

function sumGroup(group: G5EclGroup): number {
  return group.rows
    .filter((r) => !r.archived)
    .reduce((s, r) => s + (r.expectedProvision || 0), 0)
}

function fmtAmt(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPct(v: unknown): string {
  const n = typeof v === 'number' ? v : Number(v)
  if (!Number.isFinite(n)) return '—'
  return `${(n * 100).toFixed(2)}%`
}

defineExpose({
  toJSON: () => ({
    ...calc.toJSON(),
    conclusion: conclusion.value,
  }),
})
</script>

<style scoped>
.g5-impairment-calc {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.audit-objective { margin-bottom: 10px; }
.prep-hint { margin: 0 0 10px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.7; }
.aging-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.muted { color: #909399; font-size: 12px; }
.ecl-block {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 12px;
  margin-bottom: 12px;
}
.block-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.block-title { margin: 0; font-size: 13px; font-weight: 600; }
.hint-inline { font-size: 12px; color: #e6a23c; }
.aging-hint { margin: 0 0 8px; font-size: 12px; color: #909399; }
.aging-group { margin-bottom: 12px; }
.group-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
}
.group-name { font-weight: 500; }
.group-sub { margin-top: 4px; font-size: 12px; color: #606266; }
.subtotal-line {
  margin-top: 8px;
  padding: 6px 8px;
  background: #f5f7fa;
  font-size: 12px;
  font-weight: 600;
}
.subtotal-line.grand { background: #ecf5ff; color: #409eff; }
.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 48px;
  text-align: right;
}
.diff-warn { color: #e6a23c; font-weight: 600; }
</style>
