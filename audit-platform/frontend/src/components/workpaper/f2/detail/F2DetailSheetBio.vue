<template>
  <div class="f2-bio-asset">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">消耗性生物资产明细表 F2-13</h3>
        <el-tag size="small" effect="plain">科目 1411</el-tag>
      </div>
      <p class="hero-sub">（一）原值收发存 ·（二）跌价准备 ·（三）净值 · 库龄</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按存货名称/品种列示：单位；期初 → 本期增加 → 本期转出 → 期末（存栏数·单价·金额）。</p>
        <p>2. 灰色列为自动计算：期末 = 期初 + 增加 − 转出；单价 = 金额 ÷ 存栏数；库龄合计须等于期末金额。</p>
        <p>3. 跌价准备按同一品名勾稽；净值 = 原值 − 跌价（未审）。</p>
        <p>4. 可用「原值 / 跌价 / 净值」切换视图。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实消耗性生物资产收发存与库龄，验证跌价计提充分性，勾稽账面净值。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="sheet.addRow()">新增品名</el-button>
        <el-input
          v-model="sheet.searchText.value"
          size="small"
          clearable
          placeholder="搜索名称 / 品种…"
          class="search"
        />
        <span class="muted">库龄口径</span>
        <el-select
          :model-value="sheet.agingPreset.value"
          size="small"
          class="aging-sel"
          :disabled="isReadonly"
          @change="(v: string) => sheet.applyAgingPreset(v as any)"
        >
          <el-option label="3年段" value="THREE_YEAR" />
          <el-option label="5年段" value="FIVE_YEAR" />
        </el-select>
        <el-radio-group v-model="sheet.activeView.value" size="small">
          <el-radio-button value="gross">（一）原值</el-radio-button>
          <el-radio-button value="impairment">（二）跌价</el-radio-button>
          <el-radio-button value="net">（三）净值</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <el-tag v-if="sheet.totals.value.agingOk" type="success" size="small" effect="dark">库龄 OK</el-tag>
        <el-tag v-else type="danger" size="small">库龄与期末不匹配</el-tag>
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-13"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ sheet.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="sheet.filteredRows.value" border size="small" class="main-table" max-height="520">
      <el-table-column label="存货名称" min-width="120" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.itemName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { itemName: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="品种" width="100">
        <template #default="{ row }">
          <el-input
            :model-value="row.variety"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { variety: v })"
          />
        </template>
      </el-table-column>
      <el-table-column v-if="sheet.activeView.value === 'gross'" label="单位" width="72">
        <template #default="{ row }">
          <el-input
            :model-value="row.unit"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => sheet.updateRow(row.id, { unit: v })"
          />
        </template>
      </el-table-column>

      <template v-if="sheet.activeView.value === 'gross'">
        <el-table-column label="期初库存" align="center">
          <el-table-column label="存栏数" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { openQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.openUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.openAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { openAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期增加" align="center">
          <el-table-column label="存栏数" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.incQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { incQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.incUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.incAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { incAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期转出" align="center">
          <el-table-column label="存栏数" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decQty"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { decQty: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.decUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.decAmt"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { decAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末库存" align="center">
          <el-table-column label="存栏数" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.closeQty }}</span></template>
          </el-table-column>
          <el-table-column label="单价" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.closeUnitPrice) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closeAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="库龄" align="center">
          <el-table-column
            v-for="seg in sheet.segments.value"
            :key="seg.key"
            :label="seg.label"
            width="100"
          >
            <template #default="{ row }">
              <el-input-number
                :model-value="Number(row.aging?.[seg.key] ?? 0)"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateAgingCell(row.id, seg.key, v ?? 0)"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="库龄合计" width="100" class-name="auto-calc-col">
          <template #default="{ row }">
            <span :class="row.agingOk ? 'formula' : 'bad'">{{ fmtAmt(row.agingTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="状况" width="100">
          <template #default="{ row }">
            <el-select
              :model-value="row.status"
              size="small"
              clearable
              :disabled="isReadonly"
              @change="(v: string) => sheet.updateRow(row.id, { status: v || '' })"
            >
              <el-option v-for="o in STATUS" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="sheet.activeView.value === 'impairment'">
        <el-table-column label="本年数" align="center">
          <el-table-column label="期初余额" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impOpen"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impOpen: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="账项调整" align="center">
          <el-table-column label="重分类调整" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjReclass"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjReclass: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjInc"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <WpAmountInput
                :model-value="row.impAdjDec"
                size="small"
                :disabled="isReadonly"
                @change="(v: number | undefined) => sheet.updateRow(row.id, { impAdjDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudOpen) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudInc) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudDec) }}</span></template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impAudClose) }}</span></template>
          </el-table-column>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="期初未审数" align="center">
          <el-table-column label="存栏数" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.netOpenQty }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.netOpenUnit) }}</span></template>
          </el-table-column>
          <el-table-column label="期初数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netOpenAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末未审数" align="center">
          <el-table-column label="存栏数" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.netCloseQty }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.netCloseUnit) }}</span></template>
          </el-table-column>
          <el-table-column label="期末数" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netCloseAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="sheet.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">原值期末合计</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.closeAmt) }}</span>
      </div>
      <div class="summary-row">
        <span class="lab">跌价期末合计</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.impClose) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(sheet.totals.value.impAudClose) }}</span>
      </div>
      <div class="summary-row net">
        <span class="lab">净值期末（原值−跌价）</span>
        <span class="val">{{ fmtAmt(sheet.totals.value.netCloseAmt) }}</span>
      </div>
    </section>

    <section class="notes-panel">
      <h4>审计说明</h4>
      <div class="note-label">
        <span>审计说明</span>
        <el-button
          size="small"
          text
          type="primary"
          :disabled="isReadonly || !aiAvailable || aiBusyKey === 'note'"
          :loading="aiBusyKey === 'note'"
          @click="generateNote"
        >AI</el-button>
      </div>
      <el-input
        type="textarea"
        :rows="4"
        :model-value="sheet.notePack.value.auditNote"
        :disabled="isReadonly"
        placeholder="填写审计说明…"
        @change="(v: string) => sheet.persistNotePack({ auditNote: v })"
      />
    </section>

    <section class="notes-panel conclusion">
      <div class="note-label">
        <span>审计结论</span>
        <el-button
          size="small"
          text
          type="primary"
          :disabled="isReadonly || !aiAvailable || aiBusyKey === 'conclusion'"
          :loading="aiBusyKey === 'conclusion'"
          @click="generateConclusion"
        >AI</el-button>
      </div>
      <el-input
        type="textarea"
        :rows="3"
        :model-value="sheet.auditConclusion.value"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(v: string) => sheet.persistConclusion(v)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { inject, ref, toRef, type Ref } from 'vue'
import { useF2BioAssetSheet, BIO_ASSET_STATUS } from '../../composables/useF2BioAssetSheet'
import { useF2AiGenerate } from '../../composables/useF2AiGenerate'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const STATUS = BIO_ASSET_STATUS

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const sheet = useF2BioAssetSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const { aiAvailable, generateAndConfirm } = useF2AiGenerate(toRef(props, 'wpId') as Ref<string>)
const aiBusyKey = ref<string | null>(null)

async function generateNote() {
  aiBusyKey.value = 'note'
  try {
    const text = await generateAndConfirm(
      'detail-change',
      sheet.notePack.value.auditNote,
      {
        sheetCode: 'F2-13',
        sheetName: '消耗性生物资产',
        noteHint: '审计说明',
        closeAmt: sheet.totals.value.closeAmt,
        netCloseAmt: sheet.totals.value.netCloseAmt,
        agingOk: sheet.totals.value.agingOk,
      },
      'AI 生成 · F2-13 审计说明',
    )
    if (text) sheet.persistNotePack({ auditNote: text })
  } finally {
    aiBusyKey.value = null
  }
}

async function generateConclusion() {
  aiBusyKey.value = 'conclusion'
  try {
    const text = await generateAndConfirm(
      'detail-conclusion',
      sheet.auditConclusion.value,
      {
        sheetCode: 'F2-13',
        sheetName: '消耗性生物资产',
        closeAmt: sheet.totals.value.closeAmt,
        netCloseAmt: sheet.totals.value.netCloseAmt,
        agingOk: sheet.totals.value.agingOk,
      },
      'AI · F2-13 审计结论',
    )
    if (text) sheet.persistConclusion(text)
  } finally {
    aiBusyKey.value = null
  }
}

function fmtAmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPrice(v: number | ''): string {
  if (v === '' || v == null) return '-'
  return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
async function onImported() { await reloadWorkpaperData?.() }
</script>

<style scoped>
.f2-bio-asset { padding: 8px 4px 24px; }
.hero { margin-bottom: 10px; }
.hero-main { display: flex; align-items: center; gap: 10px; }
.hero-title { margin: 0; font-size: 16px; font-weight: 600; }
.hero-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.guidance { margin-bottom: 10px; font-size: 13px; }
.guidance-body { padding: 8px 4px; color: #606266; line-height: 1.6; }
.obj-alert { margin-bottom: 10px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.search { width: 160px; }
.aging-sel { width: 100px; }
.chip { display: inline-flex; }
.muted { color: #909399; font-size: 12px; }
.main-table :deep(.auto-calc-col) { background: #faf8fc; }
.formula { color: #606266; font-variant-numeric: tabular-nums; }
.bad { color: #e6a23c; font-weight: 600; }
.summary-panel { margin-top: 12px; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.summary-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.summary-row.net .lab, .summary-row.net .val { font-weight: 600; }
.lab { min-width: 160px; color: #606266; }
.val { font-variant-numeric: tabular-nums; }
.muted.tiny { color: #909399; font-size: 12px; }
.notes-panel { margin-top: 14px; }
.notes-panel h4 { margin: 0 0 8px; font-size: 14px; }
.note-label {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  font-size: 13px;
  color: #606266;
  font-weight: 500;
}
.conclusion { border-top: 1px dashed #e4e7ed; padding-top: 10px; margin-top: 10px; }
</style>
