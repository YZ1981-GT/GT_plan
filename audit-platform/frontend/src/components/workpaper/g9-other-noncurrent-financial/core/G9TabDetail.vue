<template>
  <div class="g9-detail" data-testid="g9-detail-table">
    <div class="toolbar">
      <div class="title-block">
        <h3>G9-2 明细表</h3>
        <p class="sheet-sub">分类计量明细 → 期初/变动/期末勾稽 → 分类合计回写 G9-1</p>
      </div>
      <div class="head-actions tab-toolbar">
        <span class="chip-wrap"><GtIndexChip value="wp:G9-1" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-2" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G9-4" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
        <G9ImportExportDropdown :wp-id="wpId" sheet="G9-2" @imported="onImported" />
        <GtReviewTrigger section-id="G9-2-detail" />
      </div>
    </div>

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 按 CAS 22：FVTPL / FVOCI / 摊余成本分类须与合同现金流量特征及业务模式一致。</p>
        <p>2. 期初审定 = 期初 + 期初调整；期末余额 = 期初审定 + 增加 − 减少 + FV + 利息 − 减值 + OCI；审定 = 期末 + 调整。</p>
        <p>3. 可「辅助核算取数」从 1504 带入；「回写 G9-1」按分类合计写入各组首行未审数。</p>
        <p>4. Level3 须填估值方法，并在 G9-4 补充估值技术与不可观察输入值；可带入 G9-5。</p>
        <p>5. 「工具种类」「指定FVTPL」供附注分项带入；分类非 FVTPL 时指定标记自动清除。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：核对其他非流动金融资产明细的存在、计价与分类，期末审定合计应与 G9-1 审定表勾稽一致。"
    />

    <div class="adj-toolbar">
      <el-button v-if="!isReadonly" size="small" type="primary" @click="detail.addRow()">+ 新增行</el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        plain
        :loading="detail.auxLoading.value"
        :disabled="!projectId"
        data-testid="g9-detail-aux"
        @click="onSeedAux"
      >
        辅助核算取数
      </el-button>
      <el-button
        v-if="!isReadonly"
        size="small"
        type="success"
        plain
        :disabled="!detail.rows.value.length"
        data-testid="g9-detail-push-adj"
        @click="detail.pushTotalsToAdjudication()"
      >
        ↑ 回写 G9-1
      </el-button>
      <!-- 🔴 C-2：移除「FVOCI：FV→OCI」按钮与「L3缺估值方法」标记。
           G9 五类资产全 FVTPL（编制说明 A38-A43），CAS 22 下不确认 OCI ⇒ 前者是会计错误；
           公允价值层次与估值方法的权威源是 公允价值测试表G9-4 ⇒ 后者不属本表。 -->
      <el-tag v-if="detail.integrityIssues.value.length" size="small" type="danger">
        校验未通过 {{ detail.integrityIssues.value.length }}
      </el-tag>
    </div>

    <el-alert
      v-if="detail.hasLegacyPayload.value"
      type="info"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g9-detail-migration"
      :title="`已按权威模板列模型迁移 ${detail.migrationStats.value.migratedRows} 行存量数据`"
    >
      <div v-if="Object.keys(detail.migrationStats.value.droppedByField).length" class="drop-note">
        以下旧字段在模板列体系里不存在，已丢弃（明细见
        <code>evidence/task8-template-design-logic.md</code> §3.3）：
        <span v-for="(n, f) in detail.migrationStats.value.droppedByField" :key="f">
          {{ f }}×{{ n }}
        </span>
      </div>
    </el-alert>

    <el-alert
      v-if="detail.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g9-detail-adj-cross"
      :title="`明细审定合计 ${fmt(detail.totals.value.closingAuditedFairValue)} 与 G9-1 审定合计 ${fmt(detail.adjudicationClosingTotal.value ?? 0)} 差异 ${fmt(detail.adjCrossVariance.value ?? 0)}`"
    />

    <el-alert
      v-if="detail.integrityIssues.value.length"
      type="error"
      :closable="false"
      show-icon
      class="cross-alert"
      title="以下明细行校验未通过"
    >
      <ul class="issue-list">
        <li v-for="(item, i) in detail.integrityIssues.value.slice(0, 8)" :key="`${item.rowId}-${i}`">
          {{ item.investTarget }}：{{ item.message }}
        </li>
        <li v-if="detail.integrityIssues.value.length > 8">…共 {{ detail.integrityIssues.value.length }} 项</li>
      </ul>
    </el-alert>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" />

    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      highlight-current-row
      :current-row-key="detail.currentRowKey.value"
      row-key="rowId"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />

      <!-- 🔴 C-2：列集对齐权威模板 `明细表G9-2` 的 28 列 A..AB（两级表头 R9/R10）。
           嵌套 el-table-column 表达模板的一级分组；`formula-cell` 为公式列（只读）。
           已移除 15 列，理由见 useG9Detail.DROPPED_LEGACY_FIELDS：
           OCI 与减值四列是**会计错误**（G9 全 FVTPL）· 层次/估值方法属 G9-4 ·
           其余九列模板 G9-2 没有。 -->
      <template v-if="detail.activeTab.value === 'opening'">
        <el-table-column label="投资项目" prop="investTarget" min-width="150" fixed />
        <el-table-column label="期初余额">
          <el-table-column label="成本" width="116" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="140" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingCumulativeFv" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingCumulativeFv: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingCumulativeFv) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="116" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 E 列 =C+D">{{ fmt(row.openingFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初账项调整">
          <el-table-column label="成本" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingAdjCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingAdjCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值变动" width="126" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.openingAdjFvChange" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjFvChange: v ?? 0 })" />
              <span v-else>{{ fmt(row.openingAdjFvChange) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初审定数">
          <el-table-column label="成本" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 H 列 =C+F">{{ fmt(row.openingAuditedCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="140" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 I 列 =D+G">{{ fmt(row.openingAuditedCumulativeFv) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="116" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 J 列 =H+I（三分量恒等式）">{{ fmt(row.openingAuditedFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期初重分类数" width="122" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.openingReclass" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingReclass: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingReclass) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初报表数" width="118" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="模板 L 列 =E+K">{{ fmt(row.openingReported) }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-if="detail.activeTab.value === 'movement'">
        <el-table-column label="投资项目" prop="investTarget" min-width="150" fixed />
        <el-table-column label="本期变动（借方发生填正数）">
          <el-table-column label="成本" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.periodCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { periodCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.periodCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期公允价值变动" width="146" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.periodFvChange" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { periodFvChange: v ?? 0 })" />
              <span v-else>{{ fmt(row.periodFvChange) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计入投资收益的股息" width="156" align="right">
            <template #header>
              <span title="模板 O 列。🔴 损益项，**不参与任何余额公式**（它挂在「本期变动」分组下，易被误当第三个变动分量）">
                计入投资收益的股息
              </span>
            </template>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.periodDividendIncome" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { periodDividendIncome: v ?? 0 })" />
              <span v-else>{{ fmt(row.periodDividendIncome) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末余额（未审）">
          <el-table-column label="成本" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 P 列 =C+M（🔴 未审线，不从审定数推）">{{ fmt(row.closingCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="140" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 Q 列 =D+N（🔴 未审线）">{{ fmt(row.closingCumulativeFv) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="116" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 R 列 =P+Q">{{ fmt(row.closingFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </template>

      <template v-if="detail.activeTab.value === 'closing'">
        <el-table-column label="投资项目" prop="investTarget" min-width="150" fixed />
        <el-table-column label="账项调整">
          <el-table-column label="成本" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.closingAdjCost" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjCost: v ?? 0 })" />
              <span v-else>{{ fmt(row.closingAdjCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值变动" width="126" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly" :model-value="row.closingAdjFvChange" size="small" style="width:100%"
                @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjFvChange: v ?? 0 })" />
              <span v-else>{{ fmt(row.closingAdjFvChange) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末审定数">
          <el-table-column label="成本" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 U 列 =P+S">{{ fmt(row.closingAuditedCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="累计公允价值变动" width="140" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 V 列 =Q+T">{{ fmt(row.closingAuditedCumulativeFv) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="公允价值" width="116" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="模板 W 列 =U+V（三分量恒等式）">{{ fmt(row.closingAuditedFairValue) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末重分类数" width="122" align="right">
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.closingReclass" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingReclass: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingReclass) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末报表数" width="118" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="模板 Y 列 =R+X">{{ fmt(row.closingReported) }}</span>
          </template>
        </el-table-column>
      </template>

      <template v-if="detail.activeTab.value === 'supplement'">
        <el-table-column label="区" width="210">
          <template #header><span title="模板三个受管区的区标题行 R11 / R18 / R25">区</span></template>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.section" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { section: v as any })">
              <el-option v-for="s in detail.sections" :key="s.key" :label="s.title" :value="s.key" />
            </el-select>
            <span v-else>{{ detail.sections.find((s) => s.key === row.section)?.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类别" width="130">
          <template #header><span title="模板 A 列">类别</span></template>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.category" size="small" filterable allow-create
              default-first-option
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { category: v })">
              <el-option v-for="o in detail.categoryOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投资项目" min-width="170" fixed>
          <template #header>
            <span title="模板 B 列：按明细项目列示，如证券名称或被投资单位名称">投资项目</span>
          </template>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investTarget" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { investTarget: v })" />
            <span v-else>{{ row.investTarget }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末应收利息" width="126" align="right">
          <template #header><span title="模板 Z 列">期末应收利息</span></template>
          <template #default="{ row }">
            <WpAmountInput v-if="!isReadonly" :model-value="row.closingInterestReceivable" size="small" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingInterestReceivable: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingInterestReceivable) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变现是否存在限制" width="146">
          <template #header><span title="模板 AA 列">变现是否存在限制</span></template>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.realizationRestricted" size="small" filterable
              allow-create default-first-option
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { realizationRestricted: v })">
              <el-option v-for="o in detail.realizationRestrictedOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.realizationRestricted }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" width="140">
          <template #header><span title="模板 AB 列">发函情况</span></template>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.confirmationStatus" size="small" clearable
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v || '' })">
              <el-option v-for="o in detail.confirmationOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.confirmationStatus || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <div class="summary-bar" data-testid="g9-detail-summary">
      <span>期初审定 <strong>{{ fmt(detail.totals.value.openingAuditedFairValue) }}</strong></span>
      <span>期末未审 <strong>{{ fmt(detail.totals.value.closingFairValue) }}</strong></span>
      <span>期末审定 <strong>{{ fmt(detail.totals.value.closingAuditedFairValue) }}</strong></span>
      <span>期末报表数 <strong>{{ fmt(detail.totals.value.closingReported) }}</strong></span>
      <span>本期股息 <strong>{{ fmt(detail.totals.value.periodDividendIncome) }}</strong></span>
    </div>

    <div class="subtotals" data-testid="g9-detail-subtotals">
      <span
        v-for="(amt, cls) in detail.sectionSubtotals.value"
        :key="cls"
        :class="{ 'total-line': cls === '合计' }"
      >{{ cls }}: {{ fmt(amt) }}</span>
    </div>

    <G9AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：可概述明细核对情况、分类计量恰当性、与 G9-1 审定表合计勾稽情况及拟调整事项。"
      note-hint="覆盖分类计量、明细加计及与 G9-1 / G9-4 / G9-5 勾稽。"
      :related-context="{
        行数: detail.rows.value.length,
        期末审定合计: detail.totals.value.closingAuditedFairValue,
        与G91差异: detail.adjCrossVariance.value,
        校验问题: detail.integrityIssues.value.length,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { computed, onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G9ImportExportDropdown from '../G9ImportExportDropdown.vue'
import G9AuditTextCards from '../G9AuditTextCards.vue'
import { useG9Detail } from '../../composables/useG9Detail'
import type { ChecklistResponse } from '../../composables/useF1FormData'

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

// 🔴 C-2：四段对应模板两级表头的四个一级分组
//    （期初余额 C-E+F/G+K/L · 本期变动 M-O · 期末余额 P-R+S/T+U-W+X/Y · 单列补充 A/B/Z/AA/AB）
const tabOptions = [
  { label: '期初', value: 'opening' },
  { label: '本期变动', value: 'movement' },
  { label: '期末', value: 'closing' },
  { label: '补充信息', value: 'supplement' },
]

const detail = useG9Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId || ''),
})

function onImported() { emit('imported') }

function onRowChange(r: { rowId?: string } | null) {
  if (!r?.rowId) return
  const idx = detail.rows.value.findIndex((x) => x.rowId === r.rowId)
  if (idx >= 0) detail.activeRowIndex.value = idx
}

async function onSeedAux() {
  const res = await detail.seedFromAuxBalance()
  if (res.error) {
    ElMessage.warning(res.error)
    return
  }
  ElMessage.success(`辅助核算（${res.dimType}）：新增 ${res.added}，更新 ${res.updated}`)
}

// 🔴 C-2：原 `onFillOci`（把本期 FV 变动填入 OCI 变动）已删 —— G9 五类资产全 FVTPL
//    （编制说明 A38-A43），CAS 22 下公允价值变动计入**当期损益**、不走其他综合收益，
//    该按钮本身是会计错误。FVOCI 口径见 G8 / G6（那两条**有** OCI 列，不得照抄本文件）。

// 载入时若存量载荷是旧列形态，迁移后立即回写一次（否则每次载入都要重跑迁移，
// 且跨表消费方读到的仍是旧键）。
onMounted(() => {
  const n = detail.persistMigrationIfNeeded()
  if (n > 0) ElMessage.success(`已按权威模板列模型迁移并回写 ${n} 行存量数据`)
})

const NOTE_KEY = 'G9-detail-audit-note'
const CONCLUSION_KEY = 'G9-detail-audit-conclusion'
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const _detailConcl = props.allResponses.get(CONCLUSION_KEY)
const auditConclusion = ref(String(_detailConcl?.conclusion ?? _detailConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: v, remark: null })
})

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g9-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.guidance-details { margin-bottom: 8px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
.audit-objective { margin-bottom: 10px; }
.adj-toolbar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 8px; }
.cross-alert { margin-bottom: 8px; }
.issue-list { margin: 4px 0 0; padding-left: 18px; }
.summary-bar { display: flex; gap: 16px; margin-top: 10px; flex-wrap: wrap; font-size: 13px; }
.subtotals { margin-top: 8px; display: flex; gap: 16px; flex-wrap: wrap; color: #606266; }
.total-line { font-weight: 600; color: #303133; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; background: #f5f7fa; display: inline-block; width: 100%; }
.l3-required :deep(.el-input__wrapper),
.l3-required :deep(.el-select__wrapper) { box-shadow: 0 0 0 1px #f56c6c inset; }
</style>
