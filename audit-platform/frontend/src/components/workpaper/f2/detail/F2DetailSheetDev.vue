<template>
  <div class="f2-dev-product">
    <header class="hero">
      <div class="hero-main">
        <h3 class="hero-title">开发产品明细表 F2-10</h3>
        <el-tag size="small" effect="plain">科目 1408</el-tag>
      </div>
      <p class="hero-sub">（一）原值 ·（二）跌价准备 ·（三）净值 · 面积/单位成本/调整审定</p>
    </header>

    <details class="guidance">
      <summary>编制提示</summary>
      <div class="guidance-body">
        <p>1. 按项目列示开发产品：总建筑面积、开工/竣工时间；原值含期初结存、期初调整、本期增减、期末结存与期末调整。</p>
        <p>2. 灰色列为自动计算：期末面积/金额 = 期初 + 增加 − 减少；单位成本 = 金额 ÷ 面积；期初/期末审定 = 账面 + 账项调整 + 重分类调整。</p>
        <p>3. 跌价准备按同一项目勾稽；净值 = 原值 − 跌价（账面与审定分列）。</p>
        <p>4. 可用「原值 / 跌价 / 净值」切换视图；重大变动与跌价原因写入审计说明。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="obj-alert"
      title="审计目标：核实开发产品原值收发存与调整审定，验证跌价计提充分性，勾稽账面净值与审定净值。"
    />

    <div class="toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="dev.addRow()">新增项目</el-button>
        <el-input
          v-model="dev.searchText.value"
          size="small"
          clearable
          placeholder="搜索项目名称…"
          class="search"
        />
        <el-radio-group v-model="dev.activeView.value" size="small">
          <el-radio-button value="gross">（一）原值</el-radio-button>
          <el-radio-button value="impairment">（二）跌价</el-radio-button>
          <el-radio-button value="net">（三）净值</el-radio-button>
        </el-radio-group>
      </div>
      <div class="toolbar-right">
        <CycleImportExportDropdown
          :wp-id="wpId"
          api-prefix="f2"
          sheet="F2-10"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <span class="chip"><GtIndexChip value="wp:F2-10" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ dev.enrichedRows.value.length }} 行</el-tag>
      </div>
    </div>

    <el-table :data="dev.filteredRows.value" border size="small" class="main-table" max-height="520">
      <el-table-column type="index" label="序号" width="56" fixed />
      <el-table-column label="项目名称" min-width="140" fixed>
        <template #default="{ row }">
          <el-input
            :model-value="row.projectName"
            size="small"
            :disabled="isReadonly"
            @change="(v: string) => dev.updateRow(row.id, { projectName: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="总建筑面积(㎡)" width="110">
        <template #default="{ row }">
          <el-input-number
            :model-value="row.totalArea"
            size="small"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => dev.updateRow(row.id, { totalArea: v ?? 0 })"
          />
        </template>
      </el-table-column>
      <el-table-column label="开工时间" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.startDate"
            size="small"
            placeholder="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="(v: string) => dev.updateRow(row.id, { startDate: v })"
          />
        </template>
      </el-table-column>
      <el-table-column label="竣工时间" width="120">
        <template #default="{ row }">
          <el-input
            :model-value="row.completeDate"
            size="small"
            placeholder="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="(v: string) => dev.updateRow(row.id, { completeDate: v })"
          />
        </template>
      </el-table-column>

      <template v-if="dev.activeView.value === 'gross'">
        <el-table-column label="期初结存(本币)" align="center">
          <el-table-column label="面积" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openArea"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { openArea: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.openUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { openAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初调整" align="center">
          <el-table-column label="账项调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openAdjAcct"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { openAdjAcct: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.openAdjReclass"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { openAdjReclass: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初审定" align="center">
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.openAudUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.openAudAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期增加" align="center">
          <el-table-column label="面积" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.incArea"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { incArea: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.incUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.incAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { incAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="本期减少" align="center">
          <el-table-column label="面积" width="88">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decArea"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { decArea: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.decUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.decAmt"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { decAmt: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末结存(本币)" align="center">
          <el-table-column label="面积" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.closeArea }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.closeUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closeAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末调整" align="center">
          <el-table-column label="账项调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.closeAdjAcct"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { closeAdjAcct: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.closeAdjReclass"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { closeAdjReclass: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末审定" align="center">
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.closeAudUnitCost) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.closeAudAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="品质状况" width="100">
          <template #default="{ row }">
            <el-select
              :model-value="row.qualityStatus"
              size="small"
              clearable
              :disabled="isReadonly"
              @change="(v: string) => dev.updateRow(row.id, { qualityStatus: v || '' })"
            >
              <el-option v-for="o in QUALITY" :key="o" :label="o" :value="o" />
            </el-select>
          </template>
        </el-table-column>
      </template>

      <template v-else-if="dev.activeView.value === 'impairment'">
        <el-table-column label="未审数" align="center">
          <el-table-column label="期初余额" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.impOpen"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { impOpen: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.impInc"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { impInc: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.impDec"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { impDec: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impClose) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初调整" align="center">
          <el-table-column label="账项调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.impOpenAdjAcct"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { impOpenAdjAcct: v ?? 0 })"
              />
            </template>
          </el-table-column>
          <el-table-column label="重分类调整" width="100">
            <template #default="{ row }">
              <el-input-number
                :model-value="row.impOpenAdjReclass"
                size="small"
                :controls="false"
                :disabled="isReadonly"
                @change="(v: number | undefined) => dev.updateRow(row.id, { impOpenAdjReclass: v ?? 0 })"
              />
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定数" align="center">
          <el-table-column label="期初" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impOpenAud) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impInc) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impDec) }}</span></template>
          </el-table-column>
          <el-table-column label="期末" width="100" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.impCloseAud) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="备注" width="120">
          <template #default="{ row }">
            <el-input
              :model-value="row.impRemark"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => dev.updateRow(row.id, { impRemark: v })"
            />
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="100">
          <template #default="{ row }">
            <el-input
              :model-value="row.impIndex"
              size="small"
              :disabled="isReadonly"
              @change="(v: string) => dev.updateRow(row.id, { impIndex: v })"
            />
          </template>
        </el-table-column>
      </template>

      <template v-else>
        <el-table-column label="期初账面数" align="center">
          <el-table-column label="面积" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.netOpenBookArea }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.netOpenBookUnit) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netOpenBookAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末账面数" align="center">
          <el-table-column label="面积" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.netCloseBookArea }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.netCloseBookUnit) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netCloseBookAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末审定数" align="center">
          <el-table-column label="面积" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ row.netCloseAudArea }}</span></template>
          </el-table-column>
          <el-table-column label="单位成本" width="88" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtPrice(row.netCloseAudUnit) }}</span></template>
          </el-table-column>
          <el-table-column label="金额" width="110" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula">{{ fmtAmt(row.netCloseAudAmt) }}</span></template>
          </el-table-column>
        </el-table-column>
      </template>

      <el-table-column label="" width="56" fixed="right">
        <template #default="{ row }">
          <el-button size="small" text type="danger" :disabled="isReadonly" @click="dev.removeRow(row.id)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <section class="summary-panel">
      <div class="summary-row">
        <span class="lab">原值期末合计</span>
        <span class="val">{{ fmtAmt(dev.totals.value.closeAmt) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(dev.totals.value.closeAudAmt) }}</span>
      </div>
      <div class="summary-row">
        <span class="lab">跌价期末合计</span>
        <span class="val">{{ fmtAmt(dev.totals.value.impClose) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(dev.totals.value.impCloseAud) }}</span>
      </div>
      <div class="summary-row net">
        <span class="lab">净值期末（原值−跌价）</span>
        <span class="val">{{ fmtAmt(dev.totals.value.netCloseBookAmt) }}</span>
        <span class="muted tiny">审定 {{ fmtAmt(dev.totals.value.netCloseAudAmt) }}</span>
      </div>
    </section>

    <section class="notes-panel">
      <h4>审计说明</h4>
      <div v-for="f in noteFields" :key="f.key" class="note-block">
        <div class="note-label">{{ f.label }}</div>
        <el-input
          type="textarea"
          :rows="2"
          :model-value="dev.notePack.value[f.packKey]"
          :disabled="isReadonly"
          :placeholder="f.placeholder"
          @change="(v: string) => dev.persistNotePack({ [f.packKey]: v })"
        />
      </div>
    </section>

    <section class="notes-panel conclusion">
      <div class="note-label">审计结论</div>
      <el-input
        type="textarea"
        :rows="3"
        :model-value="dev.auditConclusion.value"
        :disabled="isReadonly"
        placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在以下重大未调整事项，不可确认。"
        @change="(v: string) => dev.persistConclusion(v)"
      />
    </section>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef } from 'vue'
import { useF2DevProductSheet, DEV_PRODUCT_QUALITY } from '../../composables/useF2DevProductSheet'
import CycleImportExportDropdown from '../../shared/CycleImportExportDropdown.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import type { ChecklistResponse } from '../../composables/useF2FormData'

const QUALITY = DEV_PRODUCT_QUALITY

const props = defineProps<{
  wpId: string
  projectId?: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
}>()

const dev = useF2DevProductSheet({
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
})

const noteFields = [
  { key: 'status', packKey: 'statusNote' as const, label: '1. 开发产品现状说明：', placeholder: '开发产品现状说明：' },
  { key: 'change', packKey: 'significantChange' as const, label: '2. 本期重大变动原因：', placeholder: '本期重大变动原因：' },
  { key: 'diff', packKey: 'bookAuditDiff' as const, label: '3. 账面与审定差异说明：', placeholder: '账面与审定差异说明：' },
  { key: 'imp', packKey: 'impairmentReason' as const, label: '4. 计提跌价准备的主要项目及原因：', placeholder: '计提跌价准备的主要项目及原因：' },
]

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
.f2-dev-product { padding: 8px 4px 24px; }
.hero { margin-bottom: 10px; }
.hero-main { display: flex; align-items: center; gap: 10px; }
.hero-title { margin: 0; font-size: 16px; font-weight: 600; }
.hero-sub { margin: 4px 0 0; color: #909399; font-size: 12px; }
.guidance { margin-bottom: 10px; font-size: 13px; }
.guidance-body { padding: 8px 4px; color: #606266; line-height: 1.6; }
.obj-alert { margin-bottom: 10px; }
.toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.search { width: 180px; }
.chip { display: inline-flex; }
.main-table :deep(.auto-calc-col) { background: #f5f7fa; }
.formula { color: #606266; font-variant-numeric: tabular-nums; }
.summary-panel { margin-top: 12px; border: 1px solid #ebeef5; border-radius: 6px; padding: 8px 12px; }
.summary-row { display: flex; align-items: center; gap: 12px; padding: 4px 0; }
.summary-row.net .lab, .summary-row.net .val { font-weight: 600; }
.lab { min-width: 160px; color: #606266; }
.val { font-variant-numeric: tabular-nums; }
.muted.tiny { color: #909399; font-size: 12px; }
.notes-panel { margin-top: 14px; }
.notes-panel h4 { margin: 0 0 8px; font-size: 14px; }
.note-block { margin-bottom: 8px; }
.note-label { display: flex; align-items: center; gap: 8px; margin-bottom: 4px; font-size: 13px; color: #606266; }
.conclusion { border-top: 1px dashed #e4e7ed; padding-top: 10px; }
</style>
