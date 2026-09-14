<!--
  I3TabInitialValue.vue — I3-4 商誉入账价值测算表

  对齐致同 Excel「入账价值测算表I3-4」：
  一、审计目标 → 二、审计过程（横向测算表）→ 三、审计说明 → 四、审计结论
  公式：④应占份额=②×③；⑤商誉=①−④（非同一控制）；合计行 SUM
  改进：同一控制门禁、入账金额↔⑤勾稽、CAS20 交易费用不计入合并成本、持久化 I3-4-rows

  Spec: .kiro/specs/i3-goodwill/ Task 4.5
  Requirements: 4.1~4.3
-->
<template>
  <div class="i3-initial-value">
    <div class="section-header">
      <span class="section-title">I3-4 商誉入账价值测算表</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">💬复核</el-button>
      </div>
    </div>

    <div class="guide-panel">
      <div class="guide-header">编制逻辑（CAS20）</div>
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span>判断是否同一控制 — 是则不确认商誉</div>
        <div class="guide-step"><span class="step-num">②</span>核定购买日是否符合控制权转移条件</div>
        <div class="guide-step"><span class="step-num">③</span>确定合并成本与可辨认净资产公允价值</div>
        <div class="guide-step"><span class="step-num">④</span>⑤商誉=①−④（④=②×③），并与入账金额勾稽</div>
      </div>
    </div>

    <div class="methodology-block">
      <strong>CAS20 — 非同一控制下企业合并：</strong>
      商誉 = 合并成本 − 被购买方可辨认净资产公允价值×股权比例。
      合并成本为购买日付出对价的公允价值（含或有对价）；
      <em>购买相关费用（审计/法律/评估中介费等）计入当期损益，不计入合并成本。</em>
      同一控制下企业合并不产生商誉。若①&lt;④，差额计入当期损益（负商誉），表头「⑤&gt;0」为正常情形提示而非强制截断。
    </div>

    <!-- 一、审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="一、审计目标：确定商誉是否存在，计价是否准确（CAS20）。"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <ul>
        <li>「是否属于同一控制」选「是」时，⑤商誉强制为 0，不得确认商誉。</li>
        <li>④应占份额 = ②可辨认净资产公允价值 × ③股权比例；⑤商誉 = ①合并成本 − ④。</li>
        <li>入账金额应与⑤商誉一致（非同一控制）；差异须在备注说明。</li>
        <li>合并成本勿计入中介等购买费用；费用可记在备注或审计说明中复核费用化。</li>
        <li>本表结果写入 I3-4-rows，供 I3-2 明细初始确认勾稽。</li>
      </ul>
    </details>

    <!-- 二、审计过程：测算表 -->
    <div class="process-header">
      <span class="process-title">二、审计过程 — 入账价值测算</span>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I3-2" :context-project-id="projectId" @click="emit('navigate-sheet', '明细表I3-2')" />
        <GtIndexChip value="wp:I3-4" :context-project-id="projectId" />
        <I3SheetImportExport
          v-if="!isReadonly"
          sheet="I3-4"
          :wp-id="wpId"
          :project-id="projectId"
        />
        <el-button v-if="!isReadonly" type="primary" size="small" @click="addRow">+ 新增</el-button>
        <span class="row-count">共 {{ dataRows.length }} 行</span>
      </div>
    </div>

    <el-alert
      v-if="gateWarnings.length"
      type="warning"
      :closable="false"
      show-icon
      class="gate-alert"
    >
      <div v-for="(w, i) in gateWarnings" :key="i">{{ w }}</div>
    </el-alert>

    <el-table
      :data="rows"
      border
      size="small"
      class="calc-table"
      max-height="520"
      row-key="rowId"
      :row-class-name="rowClassName"
      show-summary
      :summary-method="summaryMethod"
    >
      <el-table-column type="index" label="#" width="42" align="center" fixed="left" />

      <el-table-column prop="projectName" label="项目名称" min-width="140" fixed="left">
        <template #default="{ row }">
          <el-input
            v-model="row.projectName"
            size="small"
            :disabled="isReadonly"
            placeholder="被购买方/项目"
            @change="persist"
          />
        </template>
      </el-table-column>

      <el-table-column prop="bookedAmount" label="入账金额" width="110" align="right">
        <template #default="{ row }">
          <el-input-number
            v-model="row.bookedAmount"
            :controls="false"
            size="small"
            :disabled="isReadonly"
            style="width:100%"
            @change="persist"
          />
        </template>
      </el-table-column>

      <el-table-column prop="sameControl" label="是否属于同一控制" width="120" align="center">
        <template #default="{ row }">
          <el-select
            v-model="row.sameControl"
            size="small"
            :disabled="isReadonly"
            placeholder="—"
            style="width:100%"
            @change="() => onSameControlChange(row)"
          >
            <el-option label="否" value="否" />
            <el-option label="是" value="是" />
          </el-select>
        </template>
      </el-table-column>

      <el-table-column label="购买日的确定" align="center">
        <el-table-column label="具体日期" width="130">
          <template #default="{ row }">
            <el-date-picker
              v-model="row.acquisitionDate"
              type="date"
              size="small"
              value-format="YYYY-MM-DD"
              :disabled="isReadonly"
              style="width:100%"
              @change="persist"
            />
          </template>
        </el-table-column>
        <el-table-column label="是否符合规定" width="110" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.dateCompliant"
              size="small"
              :disabled="isReadonly"
              placeholder="—"
              style="width:100%"
              @change="persist"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="待确认" value="待确认" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="商誉的确定" align="center">
        <el-table-column prop="mergerCost" label="①合并成本" width="110" align="right">
          <template #header>
            <el-tooltip content="购买日付出对价的公允价值（可含或有对价）；不含购买相关费用" placement="top">
              <span class="formula-hdr">①合并成本</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-model="row.mergerCost"
              :controls="false"
              size="small"
              :disabled="isReadonly || row.sameControl === '是'"
              style="width:100%"
              @change="persist"
            />
          </template>
        </el-table-column>
        <el-table-column prop="netAssetFV" label="②净资产公允价值" width="120" align="right">
          <template #header>
            <el-tooltip content="被购买方可辨认净资产公允价值（100%口径）" placement="top">
              <span class="formula-hdr">②净资产公允</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-input-number
              v-model="row.netAssetFV"
              :controls="false"
              size="small"
              :disabled="isReadonly || row.sameControl === '是'"
              style="width:100%"
              @change="persist"
            />
          </template>
        </el-table-column>
        <el-table-column prop="equityRatio" label="③股权比例" width="100" align="right">
          <template #default="{ row }">
            <div class="ratio-cell">
              <el-input-number
                v-model="row.equityRatio"
                :controls="false"
                :precision="2"
                :min="0"
                :max="100"
                size="small"
                :disabled="isReadonly || row.sameControl === '是'"
                style="width:72px"
                @change="persist"
              />
              <span class="pct">%</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column prop="shareAmount" label="④应占份额" width="110" align="right">
          <template #header>
            <el-tooltip content="④ = ② × ③" placement="top">
              <span class="formula-hdr">④应占份额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-cell">{{ fmt(rowShare(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="goodwillAmount" label="⑤商誉(⑤>0)" width="110" align="right">
          <template #header>
            <el-tooltip content="⑤ = ① − ④；同一控制强制为 0；负值提示负商誉" placement="top">
              <span class="formula-hdr">⑤商誉</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{
                'gw-ok': rowGoodwill(row) > 0 && row.sameControl !== '是',
                'gw-zero': rowGoodwill(row) === 0,
                'gw-neg': rowGoodwill(row) < 0,
              }"
            >{{ fmt(rowGoodwill(row)) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="商誉确定是否符合规定" width="130" align="center">
          <template #default="{ row }">
            <el-select
              v-model="row.goodwillCompliant"
              size="small"
              :disabled="isReadonly"
              placeholder="—"
              style="width:100%"
              @change="persist"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="不适用" value="不适用" />
              <el-option label="待确认" value="待确认" />
            </el-select>
          </template>
        </el-table-column>
      </el-table-column>

      <el-table-column label="备注" min-width="140">
        <template #default="{ row }">
          <el-input
            v-model="row.remark"
            size="small"
            :disabled="isReadonly"
            placeholder="或有对价/费用化中介费/差异说明"
            @change="persist"
          />
        </template>
      </el-table-column>

      <el-table-column v-if="!isReadonly" label="操作" width="70" align="center" fixed="right">
        <template #default="{ $index }">
          <el-button type="danger" link size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="recon-bar">
      <span>勾稽：入账金额合计 {{ fmt(totals.bookedAmount) }}</span>
      <span>｜ ⑤商誉合计 {{ fmt(totals.goodwill) }}</span>
      <span :class="Math.abs(totals.bookedAmount - totals.goodwill) < 0.01 ? 'ok' : 'bad'">
        ｜ 差异 {{ fmt(totals.bookedAmount - totals.goodwill) }}
        {{ Math.abs(totals.bookedAmount - totals.goodwill) < 0.01 ? '✓' : '⚠ 须说明' }}
      </span>
      <el-button size="small" text type="primary" @click="emit('navigate-sheet', '明细表I3-2')">→ I3-2 明细表</el-button>
    </div>

    <!-- 三、审计说明 -->
    <el-card class="note-card" shadow="never">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="记录购买日判断依据、合并成本构成（含或有对价）、可辨认净资产评估来源、同一控制判断、购买费用费用化复核、与 I3-2 勾稽情况等…"
        @change="persistMeta"
      />
    </el-card>

    <!-- 四、审计结论（模板原文无，补齐以闭环底稿） -->
    <el-card class="note-card" shadow="never">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="如：经测算，非同一控制下商誉初始确认准确，入账金额与⑤勾稽一致；同一控制项目未确认商誉…"
        @change="persistMeta"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  type I3InitialValueRow as InitialValueRow,
  emptyI3InitialValueRow,
  calcI34Share,
  calcI34Goodwill,
  normalizeI3InitialValueRow,
  buildI34GateWarnings,
  toI34CrossSheetPayload,
  summarizeI34,
} from '../../composables/i3InitialValueModel'
import { calcInitialGoodwill } from '../../composables/useI3FormulaEngine'
import GtIndexChip from '../../GtIndexChip.vue'
import I3SheetImportExport from '../shared/I3SheetImportExport.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const ROWS_KEY = 'I3-4-rows'
const META_KEY = 'I3-4-meta'
const LEGACY_KEY = 'I3-4-initial-value'
const LEGACY_NOTE = 'I3-4-conclusion'
const LEGACY_CONC = 'I3-4-audit-conclusion'

const rows = ref<InitialValueRow[]>([])
const auditNote = ref('')
const auditConclusion = ref('')

function newId(): string {
  return emptyI3InitialValueRow().rowId
}

function emptyRow(): InitialValueRow {
  return emptyI3InitialValueRow()
}

function rowShare(row: InitialValueRow): number {
  return calcI34Share(row)
}

function rowGoodwill(row: InitialValueRow): number {
  return calcI34Goodwill(row)
}

const dataRows = computed(() => rows.value)

const totals = computed(() => summarizeI34(rows.value))

const gateWarnings = computed(() => buildI34GateWarnings(rows.value))

function fmt(v: number): string {
  const n = Number(v) || 0
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClassName({ row }: { row: InitialValueRow }): string {
  if (row.sameControl === '是') return 'row-same-control'
  if (rowGoodwill(row) < 0) return 'row-neg-gw'
  const booked = Number(row.bookedAmount) || 0
  if (Math.abs(booked - rowGoodwill(row)) >= 0.01 && (booked !== 0 || rowGoodwill(row) !== 0)) {
    return 'row-diff'
  }
  return ''
}

function summaryMethod(param: { columns: { property?: string }[] }): string[] {
  const t = totals.value
  return param.columns.map((col, idx) => {
    if (idx === 0) return '合计'
    switch (col.property) {
      case 'bookedAmount': return fmt(t.bookedAmount)
      case 'mergerCost': return fmt(t.mergerCost)
      case 'netAssetFV': return fmt(t.netAssetFV)
      case 'shareAmount': return fmt(t.share)
      case 'goodwillAmount': return fmt(t.goodwill)
      default: return ''
    }
  })
}

function onSameControlChange(row: InitialValueRow) {
  if (row.sameControl === '是') {
    row.goodwillCompliant = '不适用'
    if (!row.remark.includes('同一控制')) {
      row.remark = [row.remark, '同一控制下企业合并不确认商誉'].filter(Boolean).join('；')
    }
  }
  persist()
}

function addRow() {
  rows.value.push(emptyRow())
  persist()
}

async function removeRow(index: number) {
  try {
    await ElMessageBox.confirm('确认删除该行？', '删除', { type: 'warning' })
    rows.value.splice(index, 1)
    persist()
  } catch { /* cancel */ }
}

function toCrossSheetPayload() {
  return toI34CrossSheetPayload(rows.value)
}

function persist() {
  if (props.isReadonly) return
  emit('save', ROWS_KEY, JSON.stringify(toCrossSheetPayload()))
}

function persistMeta() {
  if (props.isReadonly) return
  emit('save', META_KEY, JSON.stringify({
    auditNote: auditNote.value,
    auditConclusion: auditConclusion.value,
  }))
}

function normalizeRow(raw: any): InitialValueRow {
  return normalizeI3InitialValueRow(raw)
}

/** 从旧版「按被投资单位纵表」Map 迁移 */
function migrateLegacyMap(parsed: Record<string, any>): InitialValueRow[] {
  const out: InitialValueRow[] = []
  for (const [name, data] of Object.entries(parsed)) {
    const consideration = Number(data?.consideration) || 0
    const contingent = Number(data?.contingentConsideration) || 0
    // CAS20：交易费用不计入合并成本
    const mergerCost = consideration + contingent
    const assets = Number(data?.totalAssetsFV) || 0
    const liab = Number(data?.totalLiabilitiesFV) || 0
    const netAssetFV = assets - liab
    const equityRatio = Number(data?.equityRatio) || 100
    const share = netAssetFV * (equityRatio / 100)
    const gw = calcInitialGoodwill(mergerCost, share)
    const tx = Number(data?.transactionCost) || 0
    out.push({
      rowId: newId(),
      projectName: name,
      bookedAmount: Number(data?.detailGoodwillAmount) || gw,
      sameControl: '否',
      acquisitionDate: String(data?.acquisitionDate || ''),
      dateCompliant: '',
      mergerCost,
      netAssetFV,
      equityRatio,
      goodwillCompliant: '',
      remark: [
        tx > 0 ? `购买费用${tx}已费用化未计入合并成本` : '',
        data?.considerationNote,
        data?.contingentNote,
        data?.appraiser ? `评估：${data.appraiser}` : '',
      ].filter(Boolean).join('；'),
    })
  }
  return out
}

function readRemark(raw: any): any {
  if (raw == null) return null
  if (typeof raw === 'string') {
    try { return JSON.parse(raw) } catch { return raw }
  }
  if (raw.remark != null) {
    if (typeof raw.remark === 'string') {
      try { return JSON.parse(raw.remark) } catch { return raw.remark }
    }
    return raw.remark
  }
  return raw
}

function loadData() {
  const rowsRaw = readRemark(props.allResponses.get(ROWS_KEY))
  if (Array.isArray(rowsRaw) && rowsRaw.length) {
    rows.value = rowsRaw.map(normalizeRow)
  } else if (!rows.value.length) {
    const legacy = readRemark(props.allResponses.get(LEGACY_KEY))
    if (legacy && typeof legacy === 'object' && !Array.isArray(legacy)) {
      const migrated = migrateLegacyMap(legacy as Record<string, any>)
      if (migrated.length) {
        rows.value = migrated
        persist()
        ElMessage.info('已将旧版入账测算数据迁移为横向测算表（交易费用已从合并成本剔除）')
      } else {
        rows.value = [emptyRow()]
      }
    } else {
      rows.value = [emptyRow()]
    }
  }

  const meta = readRemark(props.allResponses.get(META_KEY))
  if (meta && typeof meta === 'object') {
    auditNote.value = meta.auditNote || ''
    auditConclusion.value = meta.auditConclusion || ''
  } else if (!auditNote.value && !auditConclusion.value) {
    const n = props.allResponses.get(LEGACY_NOTE)
    const c = props.allResponses.get(LEGACY_CONC)
    if (n) auditNote.value = typeof n === 'string' ? n : (n.remark ?? n.conclusion ?? '')
    if (c) auditConclusion.value = typeof c === 'string' ? c : (c.remark ?? c.conclusion ?? '')
  }
}

watch(() => props.allResponses, () => loadData(), { immediate: true })

function handleReview() {
  openReviewDialog('I3-4-入账价值测算')
}
</script>

<style scoped>
.i3-initial-value {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  color: #1f2937;
}

.guide-panel {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #93c5fd;
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.guide-header {
  font-weight: 600;
  color: #1e40af;
  margin-bottom: 8px;
  font-size: 13px;
}
.guide-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px 16px;
  font-size: 12px;
  color: #1e3a5f;
}
.guide-step {
  display: flex;
  gap: 6px;
  align-items: flex-start;
}
.step-num {
  color: #2563eb;
  font-weight: 700;
}

.methodology-block {
  border-left: 4px solid #f59e0b;
  background: #fffbeb;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 12px;
  font-size: 12px;
  line-height: 1.7;
  color: #78350f;
}

.objective-alert,
.gate-alert {
  margin-bottom: 12px;
}

.guidance-details {
  margin-bottom: 12px;
  font-size: 12px;
  color: #6b7280;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
}
.guidance-details ul {
  margin: 8px 0 0;
  padding-left: 18px;
  line-height: 1.8;
}

.process-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
  gap: 12px;
  flex-wrap: wrap;
}
.process-title {
  font-weight: 600;
  color: #1f2937;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}
.row-count {
  font-size: 12px;
  color: #6b7280;
}

.calc-table {
  width: 100%;
  margin-bottom: 8px;
}
.formula-hdr {
  border-bottom: 1px dashed #909399;
  cursor: help;
}
.formula-cell {
  font-weight: 600;
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 64px;
  text-align: right;
}
.gw-ok { color: #92400e; }
.gw-zero { color: #6b7280; }
.gw-neg { color: #dc2626; }
.num { font-weight: 600; }
.ratio-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 2px;
}
.pct { font-size: 12px; color: #6b7280; }

.recon-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #374151;
  padding: 8px 0 12px;
}
.recon-bar .ok { color: #16a34a; font-weight: 600; }
.recon-bar .bad { color: #dc2626; font-weight: 600; }

.note-card {
  margin-top: 12px;
}
.card-title {
  font-weight: 600;
}

:deep(.row-same-control) {
  background: #f3f4f6;
}
:deep(.row-neg-gw) {
  background: #fef2f2;
}
:deep(.row-diff) {
  background: #fff7ed;
}
</style>
