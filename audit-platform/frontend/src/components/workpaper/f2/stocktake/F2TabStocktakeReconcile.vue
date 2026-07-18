<template>
  <div class="f2-reconcile">
    <header class="rec-hero">
      <div class="rec-hero-main">
        <div class="rec-kicker">F2-24 · 双向核对</div>
        <h2 class="rec-title">账面余额与仓储台账（ERP）核对</h2>
        <p class="rec-objective">
          抽查核对存货收发存明细账与仓储台账（ERP）、卡片记录是否相符（双向核对），
          关注漏记、重号与入账及时性；大数据量可借助 IT 审计。
        </p>
      </div>
      <div class="rec-hero-actions">
        <GtIndexChip value="wp:F2-24" :context-project-id="projectId" />
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-24"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-reconcile"
          :existing-content="bsSheet.auditNote.value"
          :related-context="{
            varianceRows: bsVarianceCount + countVarianceCount,
            countDiffers: showCountSection,
            bsVarianceSummary: aiContext.bsVarianceSummary,
            countVarianceSummary: aiContext.countVarianceSummary,
          }"
          ai-title="AI 生成 · 账面核对结论"
          review-section="F2-24-conclusion"
          @ai-filled="(t: string) => { bsSheet.auditNote.value = t }"
        />
      </div>
    </header>

    <details class="rec-guide">
      <summary>编制提示</summary>
      <ol>
        <li>第一节必填：资产负债表日账面 ↔ 仓储台账双向核对。</li>
        <li>第二节仅当监盘/盘点日 ≠ 截止日时填写；相同时可关闭。</li>
        <li>数量差异 = 账面数量 − ERP 数量；金额差异 = 账面金额 − ERP 金额；有差异自动标红。</li>
        <li>差异应区分未达账项 / 计量或记录错误 / 盘盈盘亏，并评估是否提议调整。</li>
      </ol>
    </details>

    <F2StocktakeSheetAttachments
      v-if="wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-24"
    />

    <nav class="st-sec-nav" aria-label="分区导航">
      <button
        v-for="item in recNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <section v-for="group in F2_24_LAYOUT" :id="`st-${group.id}`" :key="group.id" class="rec-card">
      <header class="rec-card-head">
        <div>
          <h3>{{ group.title }}</h3>
          <p v-if="group.subtitle">{{ group.subtitle }}</p>
        </div>
        <el-button
          v-if="group.id === 'meta' && wpId && !isReadonly"
          size="small"
          plain
          @click="() => seedFromPlan()"
        >从计划/小结带入</el-button>
      </header>
      <div
        class="rec-card-grid"
        :style="{ gridTemplateColumns: `repeat(${group.cols}, minmax(0, 1fr))` }"
      >
        <div
          v-for="fid in group.fieldIds"
          :key="fid"
          class="rec-field"
          :class="{ span2: isSpan2(group, fid) }"
        >
          <div class="rec-field-label">
            <span>{{ fieldMap[fid]?.label || fid }}</span>
            <button
              v-if="wpId && !isReadonly && !fieldMap[fid]?.date"
              type="button"
              class="ai-chip"
              :disabled="!aiAvailable || aiLoadingId === fid"
              :title="`AI 起草「${fieldMap[fid]?.label || fid}」`"
              :aria-label="`AI 起草${fieldMap[fid]?.label || fid}`"
              @click="aiFillField(fid, fieldMap[fid]?.label || fid)"
            >
              {{ aiLoadingId === fid ? '…' : 'AI' }}
            </button>
          </div>
          <el-date-picker
            v-if="fieldMap[fid]?.date"
            :model-value="toPickerDate(meta.fields.value[fid])"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY年MM月DD日"
            :placeholder="fieldMap[fid]?.hint || '选择日期'"
            :disabled="isReadonly"
            style="width: 100%"
            @update:model-value="(v: string | null) => meta.updateField(fid, v || '')"
          />
          <el-input
            v-else-if="fieldMap[fid]?.multiline"
            :model-value="meta.fields.value[fid] || ''"
            type="textarea"
            :rows="fieldMap[fid]?.rows || 2"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            resize="vertical"
            @update:model-value="(v: string) => meta.updateField(fid, v)"
          />
          <el-input
            v-else
            :model-value="meta.fields.value[fid] || ''"
            :placeholder="fieldMap[fid]?.hint || ''"
            :disabled="isReadonly"
            @update:model-value="(v: string) => meta.updateField(fid, v)"
          />
        </div>
      </div>
    </section>

    <!-- 一、资产负债表日 -->
    <section id="st-bs" class="rec-card">
      <header class="rec-card-head">
        <div>
          <h3>一、资产负债表日核对记录</h3>
          <p>截止日 {{ displayCutoff }} · 账面 ↔ ERP 双向核对</p>
        </div>
        <div class="rec-card-actions">
          <el-tag v-if="bsVarianceCount > 0" size="small" type="danger">{{ bsVarianceCount }} 行差异</el-tag>
          <el-tag v-else-if="bsSheet.rows.value.length" size="small" type="success">核对一致</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="bsSheet.addRow()">+ 明细行</el-button>
        </div>
      </header>
      <div class="rec-card-body">
        <div class="rec-inline-note">
          <div class="rec-field-label">
            <span>核对说明</span>
            <button
              v-if="wpId && !isReadonly"
              type="button"
              class="ai-chip"
              :disabled="!aiAvailable || aiLoadingId === 'bsNote'"
              title="AI 起草资产负债表日核对说明"
              aria-label="AI 起草资产负债表日核对说明"
              @click="aiFillField('bsNote', '资产负债表日核对说明')"
            >
              {{ aiLoadingId === 'bsNote' ? '…' : 'AI' }}
            </button>
          </div>
          <el-input
            :model-value="meta.fields.value.bsNote || ''"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="本节核对范围、抽样方式或重大差异概述…"
            @update:model-value="(v: string) => meta.updateField('bsNote', v)"
          />
        </div>
        <el-empty
          v-if="!bsSheet.rows.value.length"
          description="暂无明细；点击「+ 明细行」或导入 Excel"
          :image-size="64"
        />
        <el-table
          v-else
          :data="bsEnriched"
          border
          size="small"
          max-height="360"
          :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''"
        >
          <el-table-column label="品名" min-width="110">
            <template #default="{ row }">
              <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => bsSheet.updateRow(row.id, { itemName: v })" />
            </template>
          </el-table-column>
          <el-table-column label="规格" width="90">
            <template #default="{ row }">
              <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => bsSheet.updateRow(row.id, { spec: v })" />
            </template>
          </el-table-column>
          <el-table-column label="账面数量" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => bsSheet.updateRow(row.id, { bookQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面金额" width="110">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => bsSheet.updateRow(row.id, { bookAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="ERP数量" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.erpQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => bsSheet.updateRow(row.id, { erpQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="ERP金额" width="110">
            <template #default="{ row }">
              <el-input-number :model-value="row.erpAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => bsSheet.updateRow(row.id, { erpAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="数量差异" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="账面数量 − ERP数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.qtyDiff.toLocaleString() }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="金额差异" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="账面金额 − ERP金额" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.amtDiff.toLocaleString() }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="90">
            <template #default="{ row }">
              <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => bsSheet.updateRow(row.id, { remark: v })" />
            </template>
          </el-table-column>
          <el-table-column width="50">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="bsSheet.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="wpId && !isReadonly" label="OCR" width="50" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
                :disabled="ocrLoadingId === row.id"
                @change="(f: any) => onOcrBs(row.id, f?.raw)">
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </section>

    <!-- 二、盘点日 -->
    <section id="st-count" class="rec-card">
      <header class="rec-card-head">
        <div>
          <h3>二、盘点日核对记录</h3>
          <p>仅当监盘/盘点日 ≠ 资产负债表日时填写</p>
        </div>
        <div class="rec-card-actions">
          <el-switch
            :model-value="showCountSection"
            :disabled="isReadonly"
            inline-prompt
            active-text="需填"
            inactive-text="同截止日"
            @change="onCountDiffersChange"
          />
        </div>
      </header>
      <div v-if="showCountSection" class="rec-card-body">
        <div class="count-meta">
          <span class="muted">盘点日</span>
          <el-date-picker
            :model-value="toPickerDate(meta.fields.value.countDate)"
            type="date"
            value-format="YYYY-MM-DD"
            format="YYYY年MM月DD日"
            placeholder="选择盘点日"
            :disabled="isReadonly"
            @update:model-value="(v: string | null) => meta.updateField('countDate', v || '')"
          />
          <el-tag v-if="countVarianceCount > 0" size="small" type="danger">{{ countVarianceCount }} 行差异</el-tag>
          <el-tag v-else-if="countSheet.rows.value.length" size="small" type="success">核对一致</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="countSheet.addRow()">+ 明细行</el-button>
        </div>
        <div class="rec-inline-note">
          <div class="rec-field-label">
            <span>核对说明</span>
            <button
              v-if="wpId && !isReadonly"
              type="button"
              class="ai-chip"
              :disabled="!aiAvailable || aiLoadingId === 'countNote'"
              title="AI 起草盘点日核对说明"
              aria-label="AI 起草盘点日核对说明"
              @click="aiFillField('countNote', '盘点日核对说明')"
            >
              {{ aiLoadingId === 'countNote' ? '…' : 'AI' }}
            </button>
          </div>
          <el-input
            :model-value="meta.fields.value.countNote || ''"
            type="textarea"
            :rows="2"
            :disabled="isReadonly"
            placeholder="盘点日核对说明；对齐后可衔接 F2-26 倒轧至报告日…"
            @update:model-value="(v: string) => meta.updateField('countNote', v)"
          />
        </div>
        <el-empty
          v-if="!countSheet.rows.value.length"
          description="暂无明细；点击「+ 明细行」或导入盘点日 Excel"
          :image-size="64"
        />
        <el-table
          v-else
          :data="countEnriched"
          border
          size="small"
          max-height="360"
          :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''"
        >
          <el-table-column label="品名" min-width="110">
            <template #default="{ row }">
              <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => countSheet.updateRow(row.id, { itemName: v })" />
            </template>
          </el-table-column>
          <el-table-column label="规格" width="90">
            <template #default="{ row }">
              <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => countSheet.updateRow(row.id, { spec: v })" />
            </template>
          </el-table-column>
          <el-table-column label="账面数量" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => countSheet.updateRow(row.id, { bookQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面金额" width="110">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => countSheet.updateRow(row.id, { bookAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="ERP数量" width="100">
            <template #default="{ row }">
              <el-input-number :model-value="row.erpQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => countSheet.updateRow(row.id, { erpQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="ERP金额" width="110">
            <template #default="{ row }">
              <el-input-number :model-value="row.erpAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => countSheet.updateRow(row.id, { erpAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="数量差异" width="90" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="账面数量 − ERP数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.qtyDiff.toLocaleString() }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="金额差异" width="100" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="账面金额 − ERP金额" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': row.hasVariance }">{{ row.amtDiff.toLocaleString() }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="90">
            <template #default="{ row }">
              <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => countSheet.updateRow(row.id, { remark: v })" />
            </template>
          </el-table-column>
          <el-table-column width="50">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="countSheet.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="wpId && !isReadonly" label="OCR" width="50" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
                :disabled="ocrLoadingId === row.id"
                @change="(f: any) => onOcrCount(row.id, f?.raw)">
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
        </el-table>
      </div>
      <div v-else class="muted-box">
        盘点日与截止日相同，本节不适用。若实际监盘日不同，请打开上方开关并填写核对明细。
      </div>
    </section>

    <section id="st-note" class="rec-card rec-card-conclusion">
      <header class="rec-card-head">
        <div>
          <h3>三、审计说明</h3>
          <p>差异原因、未达账项、是否提议调整</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__note__'"
          title="AI 起草审计说明"
          aria-label="AI 起草审计说明"
          @click="aiFillNote"
        >
          {{ aiLoadingId === '__note__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="bsSheet.auditNote.value"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="填写审计说明…"
        resize="vertical"
      />
    </section>

    <section id="st-conclusion" class="rec-card rec-card-conclusion">
      <header class="rec-card-head">
        <div>
          <h3>四、审计结论</h3>
          <p>A 未见异常 · B 除重大不符应调整外其余未见异常 · C 重大未调整或范围受限不可确认</p>
        </div>
        <button
          v-if="wpId && !isReadonly"
          type="button"
          class="ai-chip"
          :disabled="!aiAvailable || aiLoadingId === '__conclusion__'"
          title="AI 起草审计结论"
          aria-label="AI 起草审计结论"
          @click="aiFillConclusion"
        >
          {{ aiLoadingId === '__conclusion__' ? '…' : 'AI' }}
        </button>
      </header>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :rows="3"
        :disabled="isReadonly"
        placeholder="填写审计结论…"
        resize="vertical"
        @change="saveAuditConclusion"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, toRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useF2StocktakeFields, useF2StocktakeRows } from '../../composables/useF2StocktakeSheet'
import { useF2StocktakeOcr } from '../../composables/useF2StocktakeOcr'
import { useF2StocktakeAiGenerate } from '../../composables/useF2StocktakeAiGenerate'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import {
  applyMetaSeedToFields,
  formatVarianceSummary,
  readStocktakeMetaSeed,
} from '../../composables/useF2StocktakeCrossSheet'
import type { ChecklistResponse } from '../../composables/useF2StocktakeFormData'
import {
  F2_24_FIELDS,
  F2_24_LAYOUT,
  type F2PlanLayoutGroup,
  type StocktakeReconcileRow,
  type StocktakeSectionField,
} from './f2StocktakeConfigs'
import F2SheetToolbar from '../shared/F2SheetToolbar.vue'
import F2StocktakeSheetAttachments from './F2StocktakeSheetAttachments.vue'
import GtIndexChip from '../../GtIndexChip.vue'

function shortNavLabel(title: string): string {
  return title
    .replace(/^[\d一二三四五六七八九十～\-·\s]+/, '')
    .replace(/^[·\s]+/, '')
    .slice(0, 8) || title
}

const recNav = [
  ...F2_24_LAYOUT.map((g) => ({ id: `st-${g.id}`, label: shortNavLabel(g.title) })),
  { id: 'st-bs', label: '截止日核对' },
  { id: 'st-count', label: '盘点日核对' },
  { id: 'st-note', label: '审计说明' },
  { id: 'st-conclusion', label: '审计结论' },
]
const { activeId, scrollTo } = useStickySectionNav(recNav)

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const fieldIds = F2_24_FIELDS.filter((f) => !f.isSection).map((f) => f.id)
const fieldMap = Object.fromEntries(
  F2_24_FIELDS.filter((f) => !f.isSection).map((f) => [f.id, f]),
) as Record<string, StocktakeSectionField>

const meta = useF2StocktakeFields({
  fieldsKey: 'F2-24-fields',
  noteKey: 'F2-24-fields-note',
  fieldIds,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function emptyRow(): StocktakeReconcileRow {
  return {
    id: `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    itemName: '',
    spec: '',
    bookQty: 0,
    bookAmount: 0,
    erpQty: 0,
    erpAmount: 0,
    remark: '',
  }
}

const bsSheet = useF2StocktakeRows<StocktakeReconcileRow>({
  rowsKey: 'F2-24-rows',
  noteKey: 'F2-24-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

const countSheet = useF2StocktakeRows<StocktakeReconcileRow>({
  rowsKey: 'F2-24-count-rows',
  noteKey: 'F2-24-count-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

function enrich(rows: StocktakeReconcileRow[]) {
  return rows.map((r) => {
    const qtyDiff = r.bookQty - r.erpQty
    const amtDiff = r.bookAmount - r.erpAmount
    return {
      ...r,
      qtyDiff,
      amtDiff,
      hasVariance: Math.abs(qtyDiff) > 0.001 || Math.abs(amtDiff) > 0.01,
    }
  })
}

const bsEnriched = computed(() => enrich(bsSheet.rows.value))
const countEnriched = computed(() => enrich(countSheet.rows.value))
const bsVarianceCount = computed(() => bsEnriched.value.filter((r) => r.hasVariance).length)
const countVarianceCount = computed(() => countEnriched.value.filter((r) => r.hasVariance).length)

const showCountSection = computed(() => {
  const flag = (meta.fields.value.countDiffers || '').trim()
  if (flag === '是' || flag.toLowerCase() === 'yes' || flag === '1' || flag === 'true') return true
  if (flag === '否' || flag.toLowerCase() === 'no' || flag === '0' || flag === 'false') return false
  const cutoff = toPickerDate(meta.fields.value.cutoffDate)
  const count = toPickerDate(meta.fields.value.countDate)
  return !!(cutoff && count && cutoff !== count)
})

function onCountDiffersChange(val: string | number | boolean): void {
  meta.updateField('countDiffers', val ? '是' : '否')
}

function toPickerDate(raw: string | undefined): string {
  const s = (raw || '').trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  const m2 = s.match(/^(\d{4})[./-](\d{1,2})[./-](\d{1,2})/)
  if (m2) return `${m2[1]}-${m2[2].padStart(2, '0')}-${m2[3].padStart(2, '0')}`
  return ''
}

function displayCnDate(iso: string): string {
  const s = toPickerDate(iso)
  if (!s) return '未填'
  const m = s.match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!m) return s
  return `${m[1]}年${Number(m[2])}月${Number(m[3])}日`
}

const displayCutoff = computed(() => displayCnDate(meta.fields.value.cutoffDate || ''))

function isSpan2(group: F2PlanLayoutGroup, fid: string): boolean {
  return group.cols === 2 && (fid === 'purpose' || fid === 'method')
}

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const projectIdRef = toRef(() => props.projectId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)
const { aiAvailable, generateAndConfirm } = useF2StocktakeAiGenerate({
  wpId: wpIdRef,
  projectId: projectIdRef,
})
const aiLoadingId = ref('')

function onOcrBs(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-24', rowId, file, (id, patch) => bsSheet.updateRow(id, patch))
}
function onOcrCount(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-24', rowId, file, (id, patch) => countSheet.updateRow(id, patch))
}

const CONCLUSION_KEY = 'F2-24-audit-conclusion'
const auditConclusion = ref('')
function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item: ChecklistResponse = { item_id: CONCLUSION_KEY, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY, item)
  window.dispatchEvent(new CustomEvent('f2-stocktake:save-items', { detail: { items: [item] } }))
}

onMounted(() => {
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
  seedFromPlan({ silent: true })
})

function seedFromPlan(opts?: { silent?: boolean }): void {
  if (props.isReadonly) return
  const seed = readStocktakeMetaSeed(props.allResponses)
  const patch = applyMetaSeedToFields(seed, meta.fields.value, {
    entityName: 'entityName',
    bsDate: 'cutoffDate',
    countDate: 'countDate',
  })
  if (!Object.keys(patch).length) {
    if (!opts?.silent) {
      ElMessage.info(seed.source ? '文首字段已有内容，未覆盖' : '计划/小结中暂无可带入的文首信息')
    }
    return
  }
  meta.applyFields(patch, { overwriteEmptyOnly: true })
  if (!opts?.silent) ElMessage.success(`已从 ${seed.source || '上游'} 带入文首信息`)
}

const aiContext = computed(() => {
  const filled = Object.fromEntries(
    Object.entries(meta.fields.value).filter(([, v]) => v),
  )
  const bsVarRows = bsEnriched.value.filter((r) => r.hasVariance)
  const countVarRows = countEnriched.value.filter((r) => r.hasVariance)
  return {
    sheet: 'F2-24',
    bsVariance: bsVarianceCount.value,
    countVariance: countVarianceCount.value,
    countDiffers: showCountSection.value,
    bsRows: bsEnriched.value.length,
    countRows: countEnriched.value.length,
    bsVarianceSummary: formatVarianceSummary(bsVarRows, { label: '截止日差异' }),
    countVarianceSummary: formatVarianceSummary(countVarRows, { label: '盘点日差异' }),
    ...filled,
  }
})

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      'stocktake-reconcile-field',
      meta.fields.value[fieldId] || '',
      { ...aiContext.value, fieldId, fieldLabel },
      `AI · ${fieldLabel}`,
    )
    if (text) {
      meta.updateField(fieldId, text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillNote(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__note__'
  try {
    const text = await generateAndConfirm(
      'stocktake-reconcile-field',
      bsSheet.auditNote.value || '',
      { ...aiContext.value, fieldId: 'auditNote', fieldLabel: '审计说明' },
      'AI · 审计说明',
    )
    if (text) {
      bsSheet.auditNote.value = text
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}

async function aiFillConclusion(): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = '__conclusion__'
  try {
    const text = await generateAndConfirm(
      'stocktake-reconcile',
      auditConclusion.value || '',
      { ...aiContext.value, fieldId: 'conclusion', fieldLabel: '审计结论' },
      'AI · 审计结论',
    )
    if (text) {
      saveAuditConclusion(text)
      ElMessage.success('已填入，可继续编辑')
    }
  } finally {
    aiLoadingId.value = ''
  }
}
</script>

<style scoped>
.f2-reconcile {
  --rec-border: #e8eaef;
  --rec-muted: #6b7280;
  --rec-ink: #1f2937;
  --rec-accent: var(--gt-color-primary, #334155);
  --rec-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--rec-ink);
  max-width: 1180px;
}
.f2-reconcile :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-reconcile :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

.rec-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--rec-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #f8fafc 0%, #fff 55%);
}
.rec-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--rec-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.rec-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
}
.rec-objective {
  margin: 6px 0 0;
  color: var(--rec-muted);
  line-height: 1.5;
  max-width: 56em;
}
.rec-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
}

.rec-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rec-surface);
}
.rec-guide summary {
  cursor: pointer;
  font-weight: 600;
  color: #374151;
  list-style: none;
}
.rec-guide summary::-webkit-details-marker { display: none; }
.rec-guide ol {
  margin: 8px 0 4px;
  padding-left: 1.2em;
  color: var(--rec-muted);
  line-height: 1.55;
}

.rec-card {
  margin-bottom: 12px;
  border: 1px solid var(--rec-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.rec-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--rec-border);
  background: var(--rec-surface);
}
.rec-card-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
}
.rec-card-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--rec-muted);
}
.rec-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.rec-card-grid {
  display: grid;
  gap: 12px 14px;
  padding: 12px 14px 14px;
}
.rec-card-body {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.rec-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.rec-field.span2 { grid-column: 1 / -1; }
.rec-field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 550;
  color: #374151;
}
.rec-field :deep(.el-textarea__inner),
.rec-field :deep(.el-input__wrapper),
.rec-field :deep(.el-date-editor.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e5e7eb inset;
}
.rec-field :deep(.el-date-editor) { width: 100%; }

.rec-inline-note {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.ai-chip {
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--rec-surface);
  color: var(--rec-accent);
  border-radius: 999px;
  padding: 0 8px;
  height: 22px;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.02em;
  cursor: pointer;
  line-height: 20px;
  flex-shrink: 0;
}
.ai-chip:hover:not(:disabled) {
  background: #f1f5f9;
}
.ai-chip:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.count-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.muted { color: var(--rec-muted); font-size: 12px; }
.muted-box {
  padding: 16px 14px;
  color: var(--rec-muted);
  font-size: 13px;
  line-height: 1.5;
}

.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.formula-cell.diff-warn { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f5f7fa !important; }
:deep(.warn-row) { background: #fef0f0; }

.rec-card-conclusion .rec-card-head { background: var(--rec-surface); }
.rec-card-conclusion :deep(.el-textarea) {
  padding: 0 14px 14px;
  display: block;
}

@media (max-width: 900px) {
  .rec-hero { flex-direction: column; }
  .rec-card-grid { grid-template-columns: 1fr !important; }
  .rec-field.span2 { grid-column: auto; }
}
</style>

<style src="./f2StocktakeSoftNav.css"></style>
