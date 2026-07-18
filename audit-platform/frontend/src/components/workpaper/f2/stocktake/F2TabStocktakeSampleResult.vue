<template>
  <div class="f2-sample">
    <header class="smp-hero">
      <div class="smp-hero-main">
        <div class="smp-kicker">F2-25 · 双向抽盘</div>
        <h2 class="smp-title">存货抽盘结果汇总表</h2>
        <p class="smp-objective">
          从盘点记录追查至实物（存在性），并从实物追查至盘点记录（完整性）；
          比对账面、企业盘点与审计抽盘三数量，记录品质状况与差异原因。
        </p>
      </div>
      <div class="smp-hero-actions">
        <GtIndexChip value="wp:F2-25" :context-project-id="projectId" />
        <F2SheetToolbar
          v-if="wpId"
          :wp-id="wpId"
          :project-id="projectId"
          api-prefix="f2-st"
          sheet="F2-25"
          :disabled="isReadonly"
          :show-import-export="true"
          ai-section="stocktake-sample"
          :existing-content="existSheet.auditNote.value"
          :related-context="{
            varianceRows: existVariance + floorVariance,
            existVarianceSummary: aiContext.existVarianceSummary,
            floorVarianceSummary: aiContext.floorVarianceSummary,
          }"
          ai-title="AI 生成 · 抽盘汇总结论"
          review-section="F2-25-conclusion"
          @ai-filled="(t: string) => { existSheet.auditNote.value = t }"
        />
      </div>
    </header>

    <details class="smp-guide">
      <summary>编制提示</summary>
      <ol>
        <li>录入抽盘结果并核对差异；现场盘点记录、抽盘表应作为附件。</li>
        <li>财务账面与仓储记录宜一致；不一致应先调整（参见 F2-24）。</li>
        <li>账面与实盘差异须分析原因，并说明企业对盘点结果的处理。</li>
        <li>关注存货品质状况，影响跌价准备计提。</li>
        <li>双向测试：记录→实物测存在；实物→记录测完整。</li>
        <li>保留现场照片、标签、系统库位截图等证据。</li>
      </ol>
    </details>

    <section id="st-objectives" class="smp-card smp-objectives">
      <header class="smp-card-head">
        <div>
          <h3>一、审计目标</h3>
          <p>存在 · 完整 · 权属 · 计价与披露</p>
        </div>
      </header>
      <ul class="obj-list">
        <li>账面记录的存货真实存在，并计入正确科目</li>
        <li>应入账的存货均已完整记录</li>
        <li>存货由被审计单位拥有或控制</li>
        <li>存货计价恰当，披露充分</li>
      </ul>
    </section>

    <F2StocktakeSheetAttachments
      v-if="wpId"
      :project-id="projectId"
      :wp-id="wpId"
      sheet-code="F2-25"
    />

    <nav class="st-sec-nav" aria-label="分区导航">
      <button
        v-for="item in smpNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <section v-for="group in F2_25_LAYOUT" :id="`st-${group.id}`" :key="group.id" class="smp-card">
      <header class="smp-card-head">
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
        class="smp-card-grid"
        :style="{ gridTemplateColumns: `repeat(${group.cols}, minmax(0, 1fr))` }"
      >
        <div
          v-for="fid in group.fieldIds"
          :key="fid"
          class="smp-field"
          :class="{ span2: fid === 'sampleBasis' }"
        >
          <div class="smp-field-label">
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

    <!-- （一）记录 → 实物 -->
    <section id="st-exist" class="smp-card">
      <header class="smp-card-head">
        <div>
          <h3>（一）从存货盘点记录追查至实物</h3>
          <p>测存在性 · 账面 / 企业盘点 / 审计抽盘</p>
        </div>
        <div class="smp-card-actions">
          <el-tag v-if="existVariance > 0" size="small" type="danger">{{ existVariance }} 行差异</el-tag>
          <el-tag v-else-if="existSheet.rows.value.length" size="small" type="success">无差异</el-tag>
          <el-button
            size="small"
            type="warning"
            plain
            :disabled="isReadonly || diffLoading"
            :loading="diffLoading"
            @click="runDiffAi"
          >
            LLM 差异分析
          </el-button>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="existSheet.addRow()">+ 明细行</el-button>
        </div>
      </header>
      <div class="smp-card-body">
        <el-empty
          v-if="!existSheet.rows.value.length"
          description="暂无抽盘明细；可新增或导入「记录→实物」"
          :image-size="64"
        />
        <el-table
          v-else
          :data="existEnriched"
          border
          size="small"
          max-height="380"
          :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''"
        >
          <el-table-column label="编码" width="88">
            <template #default="{ row }">
              <el-input :model-value="row.itemCode" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { itemCode: v })" />
            </template>
          </el-table-column>
          <el-table-column label="名称/类别" min-width="100">
            <template #default="{ row }">
              <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { itemName: v })" />
            </template>
          </el-table-column>
          <el-table-column label="规格" width="72">
            <template #default="{ row }">
              <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { spec: v })" />
            </template>
          </el-table-column>
          <el-table-column label="单位" width="56">
            <template #default="{ row }">
              <el-input :model-value="row.unit" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { unit: v })" />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="80">
            <template #default="{ row }">
              <el-input-number :model-value="row.unitPrice" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => existSheet.updateRow(row.id, { unitPrice: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面数量" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => existSheet.updateRow(row.id, { bookQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面金额" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => existSheet.updateRow(row.id, { bookAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="企业盘点" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.clientCountQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => existSheet.updateRow(row.id, { clientCountQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="抽盘数量" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.sampleQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => existSheet.updateRow(row.id, { sampleQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="抽盘−账面" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="抽盘数量 − 账面数量（+盈 −亏）" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsBook) > 0.001 }">{{ fmt(row.sampleVsBook) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="抽盘−企业" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="抽盘数量 − 企业盘点数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsClient) > 0.001 }">{{ fmt(row.sampleVsClient) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="企业−账面" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="企业盘点 − 账面数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.clientVsBook) > 0.001 }">{{ fmt(row.clientVsBook) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="品质" width="88">
            <template #default="{ row }">
              <el-select
                :model-value="row.qualityStatus || undefined"
                size="small"
                clearable
                allow-create
                filterable
                placeholder="选择"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { qualityStatus: v || '' })"
              >
                <el-option v-for="q in QUALITY_OPTS" :key="q" :label="q" :value="q" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="90">
            <template #default="{ row }">
              <el-input :model-value="row.varianceReason" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => existSheet.updateRow(row.id, { varianceReason: v })" />
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="existSheet.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="wpId && !isReadonly" label="OCR" width="48" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
                :disabled="ocrLoadingId === row.id"
                @change="(f: any) => onOcrExist(row.id, f?.raw)">
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="existSheet.rows.value.length" class="totals muted">
          合计：账面数量 {{ fmt(existTotals.bookQty) }} · 账面金额 {{ fmt(existTotals.bookAmount) }} ·
          企业盘点 {{ fmt(existTotals.clientCountQty) }} · 抽盘 {{ fmt(existTotals.sampleQty) }}
        </div>
      </div>
    </section>

    <!-- （二）实物 → 记录 -->
    <section id="st-floor" class="smp-card">
      <header class="smp-card-head">
        <div>
          <h3>（二）从存货实物追查至盘点记录</h3>
          <p>测完整性 · 列结构与上表相同</p>
        </div>
        <div class="smp-card-actions">
          <el-tag v-if="floorVariance > 0" size="small" type="danger">{{ floorVariance }} 行差异</el-tag>
          <el-tag v-else-if="floorSheet.rows.value.length" size="small" type="success">无差异</el-tag>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="floorSheet.addRow()">+ 明细行</el-button>
        </div>
      </header>
      <div class="smp-card-body">
        <el-empty
          v-if="!floorSheet.rows.value.length"
          description="暂无抽盘明细；可新增或导入「实物→记录」"
          :image-size="64"
        />
        <el-table
          v-else
          :data="floorEnriched"
          border
          size="small"
          max-height="380"
          :row-class-name="({ row }) => row.hasVariance ? 'warn-row' : ''"
        >
          <el-table-column label="编码" width="88">
            <template #default="{ row }">
              <el-input :model-value="row.itemCode" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { itemCode: v })" />
            </template>
          </el-table-column>
          <el-table-column label="名称/类别" min-width="100">
            <template #default="{ row }">
              <el-input :model-value="row.itemName" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { itemName: v })" />
            </template>
          </el-table-column>
          <el-table-column label="规格" width="72">
            <template #default="{ row }">
              <el-input :model-value="row.spec" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { spec: v })" />
            </template>
          </el-table-column>
          <el-table-column label="单位" width="56">
            <template #default="{ row }">
              <el-input :model-value="row.unit" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { unit: v })" />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="80">
            <template #default="{ row }">
              <el-input-number :model-value="row.unitPrice" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => floorSheet.updateRow(row.id, { unitPrice: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面数量" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => floorSheet.updateRow(row.id, { bookQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="账面金额" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.bookAmount" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => floorSheet.updateRow(row.id, { bookAmount: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="企业盘点" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.clientCountQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => floorSheet.updateRow(row.id, { clientCountQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="抽盘数量" width="88">
            <template #default="{ row }">
              <el-input-number :model-value="row.sampleQty" size="small" :controls="false" :disabled="isReadonly"
                @update:model-value="(v: number | undefined) => floorSheet.updateRow(row.id, { sampleQty: v ?? 0 })" />
            </template>
          </el-table-column>
          <el-table-column label="抽盘−账面" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="抽盘数量 − 账面数量（+盈 −亏）" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsBook) > 0.001 }">{{ fmt(row.sampleVsBook) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="抽盘−企业" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="抽盘数量 − 企业盘点数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.sampleVsClient) > 0.001 }">{{ fmt(row.sampleVsClient) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="企业−账面" width="84" align="right" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tooltip content="企业盘点 − 账面数量" placement="top">
                <span class="formula-cell" :class="{ 'diff-warn': Math.abs(row.clientVsBook) > 0.001 }">{{ fmt(row.clientVsBook) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="品质" width="88">
            <template #default="{ row }">
              <el-select
                :model-value="row.qualityStatus || undefined"
                size="small"
                clearable
                allow-create
                filterable
                placeholder="选择"
                :disabled="isReadonly"
                style="width: 100%"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { qualityStatus: v || '' })"
              >
                <el-option v-for="q in QUALITY_OPTS" :key="q" :label="q" :value="q" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="差异原因" min-width="90">
            <template #default="{ row }">
              <el-input :model-value="row.varianceReason" size="small" :disabled="isReadonly"
                @update:model-value="(v: string) => floorSheet.updateRow(row.id, { varianceReason: v })" />
            </template>
          </el-table-column>
          <el-table-column width="44">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" link type="danger" size="small" @click="floorSheet.removeRow(row.id)">删</el-button>
            </template>
          </el-table-column>
          <el-table-column v-if="wpId && !isReadonly" label="OCR" width="48" align="center">
            <template #default="{ row }">
              <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls"
                :disabled="ocrLoadingId === row.id"
                @change="(f: any) => onOcrFloor(row.id, f?.raw)">
                <el-button link size="small" :loading="ocrLoadingId === row.id">📎</el-button>
              </el-upload>
            </template>
          </el-table-column>
        </el-table>
        <div v-if="floorSheet.rows.value.length" class="totals muted">
          合计：账面数量 {{ fmt(floorTotals.bookQty) }} · 账面金额 {{ fmt(floorTotals.bookAmount) }} ·
          企业盘点 {{ fmt(floorTotals.clientCountQty) }} · 抽盘 {{ fmt(floorTotals.sampleQty) }}
        </div>
      </div>
    </section>

    <section id="st-note" class="smp-card smp-card-conclusion">
      <header class="smp-card-head">
        <div>
          <h3>三、审计说明</h3>
          <p>差异原因、企业处理、抽样充分性</p>
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
        v-model="existSheet.auditNote.value"
        type="textarea"
        :rows="4"
        :disabled="isReadonly"
        placeholder="填写审计说明…"
        resize="vertical"
      />
    </section>

    <section id="st-conclusion" class="smp-card smp-card-conclusion">
      <header class="smp-card-head">
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
  F2_25_FIELDS,
  F2_25_LAYOUT,
  type StocktakeSampleRow,
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

const smpNav = [
  { id: 'st-objectives', label: '审计目标' },
  ...F2_25_LAYOUT.map((g) => ({ id: `st-${g.id}`, label: shortNavLabel(g.title) })),
  { id: 'st-exist', label: '记录→实物' },
  { id: 'st-floor', label: '实物→记录' },
  { id: 'st-note', label: '审计说明' },
  { id: 'st-conclusion', label: '审计结论' },
]
const { activeId, scrollTo } = useStickySectionNav(smpNav)

type Enriched = StocktakeSampleRow & {
  sampleVsBook: number
  sampleVsClient: number
  clientVsBook: number
  hasVariance: boolean
}

const QUALITY_OPTS = ['正常', '毁损', '呆滞', '过期', '其他']

const props = defineProps<{
  wpId?: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const fieldIds = F2_25_FIELDS.filter((f) => !f.isSection).map((f) => f.id)
const fieldMap = Object.fromEntries(
  F2_25_FIELDS.filter((f) => !f.isSection).map((f) => [f.id, f]),
) as Record<string, StocktakeSectionField>

const meta = useF2StocktakeFields({
  fieldsKey: 'F2-25-fields',
  noteKey: 'F2-25-fields-note',
  fieldIds,
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

function emptyRow(): StocktakeSampleRow {
  return {
    id: `st-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    itemCode: '',
    itemName: '',
    spec: '',
    unit: '',
    unitPrice: 0,
    bookQty: 0,
    bookAmount: 0,
    clientCountQty: 0,
    sampleQty: 0,
    qualityStatus: '',
    varianceReason: '',
    remark: '',
  }
}

function normalizeRow(r: Partial<StocktakeSampleRow> & { id: string }): StocktakeSampleRow {
  return {
    ...emptyRow(),
    ...r,
    itemCode: r.itemCode ?? '',
    unitPrice: Number(r.unitPrice ?? 0),
    bookAmount: Number(r.bookAmount ?? 0),
    clientCountQty: Number(r.clientCountQty ?? 0),
    qualityStatus: r.qualityStatus ?? '',
  }
}

const existSheet = useF2StocktakeRows<StocktakeSampleRow>({
  rowsKey: 'F2-25-rows',
  noteKey: 'F2-25-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

const floorSheet = useF2StocktakeRows<StocktakeSampleRow>({
  rowsKey: 'F2-25-floor-rows',
  noteKey: 'F2-25-floor-note',
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  emptyRow,
})

function enrich(rows: StocktakeSampleRow[]): Enriched[] {
  return rows.map((raw) => {
    const r = normalizeRow(raw)
    const sampleVsBook = r.sampleQty - r.bookQty
    const sampleVsClient = r.sampleQty - r.clientCountQty
    const clientVsBook = r.clientCountQty - r.bookQty
    return {
      ...r,
      sampleVsBook,
      sampleVsClient,
      clientVsBook,
      hasVariance:
        Math.abs(sampleVsBook) > 0.001
        || Math.abs(sampleVsClient) > 0.001
        || Math.abs(clientVsBook) > 0.001,
    }
  })
}

const existEnriched = computed(() => enrich(existSheet.rows.value))
const floorEnriched = computed(() => enrich(floorSheet.rows.value))
const existVariance = computed(() => existEnriched.value.filter((r) => r.hasVariance).length)
const floorVariance = computed(() => floorEnriched.value.filter((r) => r.hasVariance).length)

function sumOf(rows: Enriched[]) {
  return rows.reduce(
    (a, r) => ({
      bookQty: a.bookQty + r.bookQty,
      bookAmount: a.bookAmount + r.bookAmount,
      clientCountQty: a.clientCountQty + r.clientCountQty,
      sampleQty: a.sampleQty + r.sampleQty,
    }),
    { bookQty: 0, bookAmount: 0, clientCountQty: 0, sampleQty: 0 },
  )
}
const existTotals = computed(() => sumOf(existEnriched.value))
const floorTotals = computed(() => sumOf(floorEnriched.value))

function fmt(n: number): string {
  return Number(n || 0).toLocaleString(undefined, { maximumFractionDigits: 4 })
}

function toPickerDate(raw: string | undefined): string {
  const s = (raw || '').trim()
  if (!s) return ''
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s
  const m = s.match(/(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日?/)
  if (m) return `${m[1]}-${m[2].padStart(2, '0')}-${m[3].padStart(2, '0')}`
  return ''
}

const wpIdRef = toRef(() => props.wpId || '') as Ref<string>
const projectIdRef = toRef(() => props.projectId || '') as Ref<string>
const { ocrLoadingId, uploadAndMerge } = useF2StocktakeOcr(wpIdRef)
const { aiAvailable, generateAndConfirm, diffLoading, generateDiffSummary } = useF2StocktakeAiGenerate({
  wpId: wpIdRef,
  projectId: projectIdRef,
})
const aiLoadingId = ref('')

function onOcrExist(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-25', rowId, file, (id, patch) => existSheet.updateRow(id, patch as Partial<StocktakeSampleRow>))
}
function onOcrFloor(rowId: string, file?: File) {
  if (!file) return
  void uploadAndMerge('F2-25', rowId, file, (id, patch) => floorSheet.updateRow(id, patch as Partial<StocktakeSampleRow>))
}

const CONCLUSION_KEY = 'F2-25-audit-conclusion'
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
  const legacy = props.allResponses.get('F2-25-fields')
  if (legacy?.remark) {
    try {
      const parsed = JSON.parse(legacy.remark) as Record<string, string>
      if (parsed.locations && !meta.fields.value.warehouseName) {
        meta.applyFields({ warehouseName: parsed.locations }, { overwriteEmptyOnly: true })
      }
    } catch { /* ignore */ }
  }
  seedFromPlan({ silent: true })
})

function seedFromPlan(opts?: { silent?: boolean }): void {
  if (props.isReadonly) return
  const seed = readStocktakeMetaSeed(props.allResponses)
  const patch = applyMetaSeedToFields(seed, meta.fields.value, {
    entityName: 'entityName',
    bsDate: 'cutoffDate',
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
  const existVar = existEnriched.value.filter((r) => r.hasVariance)
  const floorVar = floorEnriched.value.filter((r) => r.hasVariance)
  return {
    sheet: 'F2-25',
    existVariance: existVariance.value,
    floorVariance: floorVariance.value,
    existRows: existEnriched.value.length,
    floorRows: floorEnriched.value.length,
    existVarianceSummary: formatVarianceSummary(
      existVar.map((r) => ({
        itemName: r.itemName,
        qtyDiff: r.sampleVsBook,
        bookQty: r.bookQty,
        sampleQty: r.sampleQty,
        varianceReason: r.varianceReason,
        hasVariance: true,
      })),
      { label: '记录→实物差异' },
    ),
    floorVarianceSummary: formatVarianceSummary(
      floorVar.map((r) => ({
        itemName: r.itemName,
        qtyDiff: r.sampleVsBook,
        bookQty: r.bookQty,
        sampleQty: r.sampleQty,
        varianceReason: r.varianceReason,
        hasVariance: true,
      })),
      { label: '实物→记录差异' },
    ),
    ...filled,
  }
})

async function aiFillField(fieldId: string, fieldLabel: string): Promise<void> {
  if (props.isReadonly || !props.wpId) return
  aiLoadingId.value = fieldId
  try {
    const text = await generateAndConfirm(
      'stocktake-sample-field',
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
      'stocktake-sample-field',
      existSheet.auditNote.value || '',
      { ...aiContext.value, fieldId: 'auditNote', fieldLabel: '审计说明' },
      'AI · 审计说明',
    )
    if (text) {
      existSheet.auditNote.value = text
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
      'stocktake-sample',
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

async function runDiffAi() {
  const differences = [...existEnriched.value, ...floorEnriched.value]
    .filter((r) => r.hasVariance)
    .map((r) => ({
      itemName: r.itemName,
      bookQty: r.bookQty,
      actualQty: r.sampleQty,
      reason: r.varianceReason || `企业盘点${r.clientCountQty}`,
    }))
  const result = await generateDiffSummary(differences, existSheet.auditNote.value)
  if (result) {
    existSheet.auditNote.value = result.summary
    if (result.riskAlerts.length) {
      ElMessage.warning(`风险提示：${result.riskAlerts.join('；')}`)
    }
  }
}
</script>

<style scoped>
.f2-sample {
  --smp-border: #e8eaef;
  --smp-muted: #6b7280;
  --smp-ink: #1f2937;
  --smp-accent: var(--gt-color-primary, #334155);
  --smp-surface: var(--gt-color-primary-bg, #f4f0fa);
  padding: 8px 12px 20px;
  font-size: var(--wp-font-size, 13px);
  color: var(--smp-ink);
  max-width: 1280px;
}
.f2-sample :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f2-sample :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

.smp-hero {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
  padding: 14px 16px;
  margin-bottom: 12px;
  border: 1px solid var(--smp-border);
  border-radius: 10px;
  background: linear-gradient(135deg, #f8fafc 0%, #fff 55%);
}
.smp-kicker {
  font-size: 11px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  color: var(--smp-accent);
  font-weight: 600;
  margin-bottom: 4px;
}
.smp-title {
  margin: 0;
  font-size: 18px;
  font-weight: 650;
  line-height: 1.3;
}
.smp-objective {
  margin: 6px 0 0;
  color: var(--smp-muted);
  line-height: 1.5;
  max-width: 56em;
}
.smp-hero-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  justify-content: flex-end;
  flex-shrink: 0;
}

.smp-guide {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-radius: 8px;
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--smp-surface);
}
.smp-guide summary {
  cursor: pointer;
  font-weight: 600;
  color: #374151;
  list-style: none;
}
.smp-guide summary::-webkit-details-marker { display: none; }
.smp-guide ol {
  margin: 8px 0 4px;
  padding-left: 1.2em;
  color: var(--smp-muted);
  line-height: 1.55;
}

.smp-card {
  margin-bottom: 12px;
  border: 1px solid var(--smp-border);
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.smp-card-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 14px;
  border-bottom: 1px solid var(--smp-border);
  background: var(--smp-surface);
}
.smp-card-head h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 650;
}
.smp-card-head p {
  margin: 2px 0 0;
  font-size: 12px;
  color: var(--smp-muted);
}
.smp-card-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
}
.smp-card-grid {
  display: grid;
  gap: 12px 14px;
  padding: 12px 14px 14px;
}
.smp-card-body {
  padding: 12px 14px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.smp-field {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}
.smp-field.span2 { grid-column: 1 / -1; }
.smp-field-label {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  font-size: 12px;
  font-weight: 550;
  color: #374151;
}
.smp-field :deep(.el-textarea__inner),
.smp-field :deep(.el-input__wrapper),
.smp-field :deep(.el-date-editor.el-input__wrapper) {
  box-shadow: 0 0 0 1px #e5e7eb inset;
}
.smp-field :deep(.el-date-editor) { width: 100%; }

.ai-chip {
  border: 1px solid var(--gt-color-primary-lighter, #c4a8e8);
  background: var(--smp-surface);
  color: var(--smp-accent);
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

.obj-list {
  margin: 0;
  padding: 10px 14px 14px 28px;
  color: var(--smp-muted);
  line-height: 1.55;
}
.totals { font-size: 12px; }
.muted { color: var(--smp-muted); }

.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.formula-cell.diff-warn { color: #f56c6c; font-weight: 600; }
:deep(.auto-calc-col) { background-color: #f8f7fc !important; }
:deep(.warn-row) { background: #fef0f0; }

.smp-card-conclusion .smp-card-head { background: #f8fafc; }
.smp-card-conclusion :deep(.el-textarea) {
  padding: 0 14px 14px;
  display: block;
}

@media (max-width: 900px) {
  .smp-hero { flex-direction: column; }
  .smp-card-grid { grid-template-columns: 1fr !important; }
  .smp-field.span2 { grid-column: auto; }
}
</style>

<style src="./f2StocktakeSoftNav.css"></style>
