<template>
  <div class="g8-detail" data-testid="g8-detail-table">
    <details class="guidance-details" open>
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p><b>定位</b>：本表是科目 1503 其他权益工具投资（FVOCI）的被投资单位明细锚点，向上勾稽 G8-1 审定，向下供 G8-4 / G8-5 / G8-6 取数。</p>
        <p><b>编制顺序</b>：①「辅助核算取数」或手工录入被投资单位 → ② 填滚动金额 → ③ 填指定 OCI 原因 → ④「FV→本期OCI」并校 OCI 滚动 → ⑤「回写 G8-1」→ 与 G8-4/G8-5 联动。</p>
        <p><b>公式</b>：期初审定=期初+调整；期末余额=期初审定+增加−减少+FV变动；审定=期末+调整；OCI期末累计=期初累计+本期OCI−转入留存。持股数×每股公允可回填公允合计。</p>
        <p><b>勾稽要点</b>：明细审定 ↔ G8-1；公允合计 ↔ 期末审定；本期OCI ↔ FV变动；OCI滚动自洽；层次/估值与 G8-4 一致。</p>
      </div>
    </details>

    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实其他权益工具投资各被投资单位期末成本、公允价值及 OCI 累计变动明细的准确与完整，验证公允价值层次划分与指定恰当，为审定表 G8-1（科目1503）提供明细支撑。"
      class="objective-alert"
    />

    <div class="toolbar">
      <div class="title-block">
        <h3>G8-2 明细表</h3>
        <p class="sheet-sub">被投资单位明细锚点 · 向上勾稽 G8-1 · 向下供 G8-4/G8-5/G8-6 取数</p>
      </div>
      <div class="head-actions">
        <G8ImportExportDropdown :wp-id="wpId" sheet="G8-2" @imported="onImported" />
        <GtReviewTrigger section-id="G8-2-detail" />
        <el-button
          v-if="!isReadonly"
          size="small"
          :loading="detail.auxLoading.value"
          data-testid="g8-detail-seed-aux"
          @click="onSeedAux"
        >
          辅助核算取数
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g8-detail-fill-oci"
          @click="onFillOci"
        >
          FV→本期OCI
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g8-detail-sync-oci"
          @click="onSyncOciRoll"
        >
          重算OCI累计
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g8-detail-sync-fv"
          @click="onSyncFv"
        >
          数量×单价→公允合计
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          data-testid="g8-detail-push-adj"
          @click="onPushAdj"
        >
          回写 G8-1
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" data-testid="g8-detail-add" @click="detail.addRow()">
          + 新增行
        </el-button>
      </div>
    </div>
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-1" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G8-5" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:G8-2" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ detail.rows.value.length }} 行</el-tag>
      </div>
    </div>

    <div v-if="detail.rows.value.length" class="summary-bar" data-testid="g8-detail-summary">
      <span>审定合计 {{ fmt(detail.totals.value.closingAdjusted) }}</span>
      <span>公允合计 {{ fmt(detail.totals.value.fairValueTotal) }}</span>
      <span>本期 OCI {{ fmt(detail.totals.value.ociCurrentChange) }}</span>
      <span :class="detail.hasAdjCrossMismatch.value ? 'bad' : 'ok'">
        ↔ G8-1 {{ detail.hasAdjCrossMismatch.value ? '差异' : '一致' }}
      </span>
    </div>

    <el-alert
      v-if="detail.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-adj-cross"
    >
      <template #title>
        <span>
          明细审定合计 {{ fmt(detail.totals.value.closingAdjusted) }} 与 G8-1 审定合计
          {{ fmt(detail.adjudicationClosingTotal.value ?? 0) }} 差异 {{ fmt(detail.adjCrossVariance.value ?? 0) }}
        </span>
        <el-button size="small" link type="primary" @click="goSheet('G8-1')">前往 G8-1</el-button>
      </template>
    </el-alert>
    <el-alert
      v-if="detail.hasFvVsClosingMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-fv-cross"
      :title="`公允价值合计 ${fmt(detail.totals.value.fairValueTotal)} 与期末审定合计 ${fmt(detail.totals.value.closingAdjusted)} 差异 ${fmt(detail.fvVsClosingVariance.value)}`"
    />
    <el-alert
      v-if="detail.integrityIssues.value.length"
      type="warning"
      :closable="false"
      show-icon
      class="cross-alert"
      data-testid="g8-detail-integrity"
      :title="integrityTitle"
    />

    <div class="fine-checks" data-testid="g8-detail-fine-checks">
      <el-tag size="small" :type="detail.hasAdjCrossMismatch.value ? 'warning' : 'success'">G8-CHK-02 ↔ G8-1</el-tag>
      <el-tag size="small" :type="detail.hasFvVsClosingMismatch.value ? 'warning' : 'success'">公允合计 ↔ 审定</el-tag>
      <el-tag size="small" :type="detail.missingDesignationCount.value ? 'warning' : 'success'">
        指定原因 {{ detail.missingDesignationCount.value ? `缺 ${detail.missingDesignationCount.value}` : '齐' }}
      </el-tag>
      <el-tag size="small" :type="detail.ociRollIssueCount.value ? 'warning' : 'success'">
        OCI滚动 {{ detail.ociRollIssueCount.value ? `差 ${detail.ociRollIssueCount.value}` : '齐' }}
      </el-tag>
      <el-tag size="small" :type="detail.integrityIssues.value.length ? 'warning' : 'success'">
        行完整性 {{ detail.integrityIssues.value.length ? detail.integrityIssues.value.length : '通过' }}
      </el-tag>
    </div>

    <el-segmented v-model="detail.activeTab.value" :options="tabOptions" size="small" data-testid="g8-detail-tabs" />
    <el-table
      :data="detail.rows.value"
      border
      size="small"
      style="font-size:13px;margin-top:8px"
      max-height="520"
      highlight-current-row
      :current-row-key="currentRowKey"
      row-key="rowId"
      empty-text="暂无明细。点击「新增行」按被投资单位录入，或先导入台账后再与 G8-1/G8-4 勾稽。"
      :row-class-name="rowClassName"
      @current-change="onRowChange"
    >
      <el-table-column prop="seq" label="#" width="44" align="center" fixed />
      <template v-if="detail.activeTab.value === 'basic'">
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" min-width="120" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.investeeName" size="small" @update:model-value="(v: string) => detail.updateRow(row.rowId, { investeeName: v })" />
            <span v-else>{{ row.investeeName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="投资比例%" :render-header="th('投资比例%')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="ratioPct(row.investmentRatio)"
              size="small"
              :controls="false"
              :step="0.01"
              :precision="2"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { investmentRatio: pctToRatio(v) })"
            />
            <span v-else>{{ ratioPct(row.investmentRatio).toFixed(2) }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="期初余额" :render-header="th('期初余额')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingBalance" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingBalance: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初调整" :render-header="th('期初调整')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.openingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { openingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.openingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初审定" :render-header="th('期初审定')" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初余额+期初调整">{{ fmt(row.openingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="增加" :render-header="th('增加')" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.increaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { increaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少" :render-header="th('减少')" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.decreaseAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { decreaseAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="FV变动" :render-header="th('FV变动')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.fvChangeAmount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fvChangeAmount: v ?? 0 })" />
            <span v-else>{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" :render-header="th('期末余额')" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期初审定+增加-减少+FV变动">{{ fmt(row.closingBalance) }}</span></template>
        </el-table-column>
        <el-table-column label="调整数" :render-header="th('调整数')" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.closingAdjustment" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { closingAdjustment: v ?? 0 })" />
            <span v-else>{{ fmt(row.closingAdjustment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" :render-header="th('审定数')" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期末余额+调整数">{{ fmt(row.closingAdjusted) }}</span></template>
        </el-table-column>
        <el-table-column label="指定OCI原因" :render-header="th('指定OCI原因')" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.designationReason"
              size="small"
              :class="{ 'field-warn': needsDesignation(row) }"
              placeholder="不可撤销指定须说明"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { designationReason: v })"
            />
            <span v-else>{{ row.designationReason }}</span>
          </template>
        </el-table-column>
      </template>
      <template v-else>
        <el-table-column label="被投资单位" :render-header="th('被投资单位')" prop="investeeName" min-width="120" fixed />
        <el-table-column label="期初OCI累计" :render-header="th('期初OCI累计')" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ociOpeningCumulative"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociOpeningCumulative: v ?? 0 })"
            />
            <span v-else>{{ fmt(row.ociOpeningCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期OCI" :render-header="th('本期OCI')" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.ociCurrentChange"
              size="small"
              :controls="false"
              style="width:100%"
              :class="{ 'field-warn': ociFvMismatch(row) }"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociCurrentChange: v ?? 0 })"
            />
            <span v-else :class="{ 'rate-warn': ociFvMismatch(row) }">{{ fmt(row.ociCurrentChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCI转留存" :render-header="th('OCI转留存')" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.ociToRetainedEarnings" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { ociToRetainedEarnings: v ?? 0 })" />
            <span v-else>{{ fmt(row.ociToRetainedEarnings) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末OCI累计" :render-header="th('期末OCI累计')" width="120" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'rate-warn': ociRollMismatch(row) }"
              title="期初OCI累计+本期OCI−转入留存"
            >{{ fmt(row.ociCumulativeChange) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入原因" :render-header="th('转入原因')" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.transferReason"
              size="small"
              :class="{ 'field-warn': needsTransferReason(row) }"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { transferReason: v })"
            />
            <span v-else>{{ row.transferReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="发函情况" :render-header="th('发函情况')" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.confirmationStatus || undefined"
              size="small"
              clearable
              filterable
              allow-create
              placeholder="选/填"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { confirmationStatus: v ?? '' })"
            >
              <el-option v-for="o in detail.confirmationStatusOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.confirmationStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column label="层次" :render-header="th('层次')" width="96">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.fairValueLevel" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { fairValueLevel: v })">
              <el-option v-for="o in detail.fvLevelOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.fairValueLevel }}</span>
          </template>
        </el-table-column>
        <el-table-column label="估值方法" :render-header="th('估值方法')" width="120">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.valuationMethod"
              size="small"
              allow-create
              filterable
              :class="{ 'field-warn': needsValuation(row) }"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { valuationMethod: v })"
            >
              <el-option v-for="o in detail.valuationMethodOptions" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.valuationMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="持股数" :render-header="th('持股数')" width="96" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.shareCount" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { shareCount: v ?? 0 })" />
            <span v-else>{{ row.shareCount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="每股公允价值" :render-header="th('每股公允价值')" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.pricePerShare" size="small" :controls="false" style="width:100%"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { pricePerShare: v ?? 0 })" />
            <span v-else>{{ fmt(row.pricePerShare) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允价值合计" :render-header="th('公允价值合计')" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.fairValueTotal"
              size="small"
              :controls="false"
              style="width:100%"
              :class="{ 'field-warn': fvClosingMismatch(row) }"
              @update:model-value="(v: number) => detail.updateRow(row.rowId, { fairValueTotal: v ?? 0 })"
            />
            <span v-else class="formula-cell" :title="fvHint(row)">{{ fmt(row.fairValueTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" :render-header="th('备注')" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.remark" size="small"
              @update:model-value="(v: string) => detail.updateRow(row.rowId, { remark: v })" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </template>
      <el-table-column v-if="!isReadonly" label="操作" width="56" fixed="right">
        <template #default="{ row }">
          <el-button link type="danger" size="small" @click="detail.removeRow(row.rowId)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-table v-if="detail.rows.value.length" :data="[detail.totals.value]" border size="small" class="totals-table" style="font-size:13px;margin-top:8px">
      <el-table-column label="合计" :render-header="th('合计')" width="80" />
      <el-table-column label="期初审定" :render-header="th('期初审定')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.openingAdjusted) }}</template>
      </el-table-column>
      <el-table-column label="增加" :render-header="th('增加')" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.increaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="减少" :render-header="th('减少')" width="96" align="right">
        <template #default="{ row }">{{ fmt(row.decreaseAmount) }}</template>
      </el-table-column>
      <el-table-column label="FV变动" :render-header="th('FV变动')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.fvChangeAmount) }}</template>
      </el-table-column>
      <el-table-column label="期末余额" :render-header="th('期末余额')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.closingBalance) }}</template>
      </el-table-column>
      <el-table-column label="审定数" :render-header="th('审定数')" width="100" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.closingAdjusted) }}</strong></template>
      </el-table-column>
      <el-table-column label="本期OCI" :render-header="th('本期OCI')" width="100" align="right">
        <template #default="{ row }">{{ fmt(row.ociCurrentChange) }}</template>
      </el-table-column>
      <el-table-column label="期末OCI累计" :render-header="th('期末OCI累计')" width="120" align="right">
        <template #default="{ row }">{{ fmt(row.ociCumulativeChange) }}</template>
      </el-table-column>
      <el-table-column label="公允合计" :render-header="th('公允合计')" width="110" align="right">
        <template #default="{ row }"><strong>{{ fmt(row.fairValueTotal) }}</strong></template>
      </el-table-column>
    </el-table>

    <G8AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      note-ai-section="detail-note"
      conclusion-ai-section="detail-conclusion"
      note-placeholder="填写审计说明：（1）明细核对程序及结果；（2）各被投资单位成本、公允价值、OCI 变动的核实情况；（3）与 G8-1/G8-4 勾稽及异常事项。"
      note-hint="覆盖被投资单位明细、指定 OCI 原因、公允价值层次与跨表勾稽。"
      conclusion-placeholder="填写审计结论：A、明细准确完整，与 G8-1 勾稽一致，指定与层次恰当。B、除已注明事项外未见异常。C、存在重大未决差异或范围受限，不可确认。"
      conclusion-hint="按 A/B/C 口径评价明细充分性。"
      :related-context="{
        rowCount: detail.rows.value.length,
        closingAdjustedTotal: detail.totals.value.closingAdjusted,
        fairValueTotal: detail.totals.value.fairValueTotal,
        integrityIssueCount: detail.integrityIssues.value.length,
        adjCrossVariance: detail.adjCrossVariance.value,
      }"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, inject, ref, watch, h } from 'vue'
import { ElMessage, ElTooltip } from 'element-plus'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G8ImportExportDropdown from '../G8ImportExportDropdown.vue'
import G8AuditTextCards from '../G8AuditTextCards.vue'
import { useG8Detail, type G8DetailRow } from '../../composables/useG8Detail'
import { calcFairValueAmount, calcOciCumulativeEnding } from '../../composables/useG8FormulaEngine'
import { jumpToG8Sheet } from '../../composables/g8CrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'

/** 表头悬停显示完整列名（避免窄列截断） */
function th(label: string) {
  return () =>
    h(
      ElTooltip,
      { content: label, placement: 'top', showAfter: 200, effect: 'dark' },
      { default: () => h('span', { class: 'th-label' }, label) },
    )
}

const props = defineProps<{
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  isReadonly: boolean
  debouncedSave: (id: string, d: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()
const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const detail = useG8Detail({
  allResponses: computed(() => props.allResponses),
  debouncedSave: props.debouncedSave,
  isReadonly: computed(() => props.isReadonly),
  projectId: computed(() => props.projectId ?? ''),
})

const AUDIT_NOTE_KEY = 'G8-2-audit-note'
const AUDIT_CONCLUSION_KEY = 'G8-2-audit-conclusion'
const auditNote = ref(props.allResponses.get(AUDIT_NOTE_KEY)?.remark ?? '')
const _detailConcl = props.allResponses.get(AUDIT_CONCLUSION_KEY)
const auditConclusion = ref(String(_detailConcl?.conclusion ?? _detailConcl?.remark ?? ''))
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_NOTE_KEY, { conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(AUDIT_CONCLUSION_KEY, { conclusion: v, remark: null })
})

const tabOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '公允价值+OCI', value: 'fv_oci' },
]

const currentRowKey = computed(() => {
  const r = detail.rows.value[detail.activeRowIndex.value]
  return r?.rowId
})

const integrityTitle = computed(() => {
  const issues = detail.integrityIssues.value
  if (!issues.length) return ''
  const sample = issues.slice(0, 3).map((i) => `${i.investeeName}：${i.message}`).join('；')
  const more = issues.length > 3 ? `…等共 ${issues.length} 项` : ''
  return `明细完整性提示：${sample}${more}`
})

function onRowChange(row: G8DetailRow | undefined) {
  if (row?.seq) detail.activeRowIndex.value = row.seq - 1
}

function rowClassName({ row }: { row: G8DetailRow }) {
  const hit = detail.integrityIssues.value.some((i) => i.rowId === row.rowId)
  return hit ? 'row-warn' : ''
}

function onSyncFv() {
  const n = detail.syncFairValueFromQtyPrice()
  if (n) ElMessage.success(`已按数量×单价回填 ${n} 行公允价值合计`)
  else ElMessage.info('无可用的持股数×每股公允价值可回填')
}

async function onSeedAux() {
  const r = await detail.seedFromAuxBalance()
  if (r.error) {
    ElMessage.warning(r.error)
    return
  }
  ElMessage.success(`辅助核算（${r.dimType}）已同步：新增 ${r.added}，更新 ${r.updated}`)
}

function onFillOci() {
  const n = detail.fillOciFromFvChange()
  if (n) ElMessage.success(`已将 ${n} 行 FV 变动填入本期 OCI，并重算期末累计`)
  else ElMessage.info('无需填入（本期 OCI 已有值或 FV 变动为空）')
}

function onSyncOciRoll() {
  const n = detail.syncOciCumulativeRoll()
  if (n) ElMessage.success(`已按滚动公式重算 ${n} 行期末 OCI 累计`)
}

function onPushAdj() {
  if (!detail.rows.value.length) {
    ElMessage.warning('明细为空，无法回写 G8-1')
    return
  }
  if (detail.pushTotalsToAdjudication()) {
    ElMessage.success('已将明细期初审定/期末未审合计回写 G8-1 首行')
  }
}

function onImported() { emit('imported') }

function goSheet(code: string) {
  jumpToG8Sheet(code, jumpToSection)
}

function fmt(n: number) {
  return Number(n || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ratioPct(ratio: number) {
  return Math.round(Number(ratio || 0) * 10000) / 100
}

function pctToRatio(pct: number | undefined | null) {
  return Math.round(Number(pct || 0) * 100) / 10000
}

function needsDesignation(row: G8DetailRow) {
  return Math.abs(row.closingAdjusted) > 0.01 && !row.designationReason?.trim()
}

function needsValuation(row: G8DetailRow) {
  return row.fairValueLevel === 'Level3' && !row.valuationMethod?.trim()
}

function needsTransferReason(row: G8DetailRow) {
  return Math.abs(row.ociToRetainedEarnings) > 0.01 && !row.transferReason?.trim()
}

function ociFvMismatch(row: G8DetailRow) {
  return (
    Math.abs(row.fvChangeAmount) > 0.01
    && Math.abs(row.ociCurrentChange) > 0.01
    && Math.abs(row.fvChangeAmount - row.ociCurrentChange) > 0.01
  )
}

function ociRollMismatch(row: G8DetailRow) {
  const expected = calcOciCumulativeEnding(
    row.ociOpeningCumulative,
    row.ociCurrentChange,
    row.ociToRetainedEarnings,
  )
  return Math.abs(row.ociCumulativeChange - expected) > 0.01
}

function fvClosingMismatch(row: G8DetailRow) {
  return (
    Math.abs(row.fairValueTotal) > 0.01
    && Math.abs(row.closingAdjusted) > 0.01
    && Math.abs(row.fairValueTotal - row.closingAdjusted) > 0.01
  )
}

function fvHint(row: G8DetailRow) {
  if (row.shareCount && row.pricePerShare) {
    return `数量×单价=${fmt(calcFairValueAmount(row.shareCount, row.pricePerShare))}`
  }
  return '公允价值合计'
}
</script>

<style scoped>
.g8-detail { font-size: var(--wp-font-size, 13px); }
.toolbar { display: flex; justify-content: space-between; margin-bottom: 8px; align-items: flex-start; gap: 8px; flex-wrap: wrap; }
.title-block h3 { margin: 0; font-size: 15px; }
.sheet-sub { margin: 4px 0 0; font-size: 12px; color: #909399; }
.head-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.summary-bar {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  align-items: center;
  margin-bottom: 8px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
}
.summary-bar .ok { color: #67c23a; font-weight: 600; }
.summary-bar .bad { color: #e6a23c; font-weight: 600; }
.tab-toolbar .toolbar-left { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.formula-cell { border-bottom: 1px dashed #c0c4cc; cursor: help; }
.guidance-details { margin-bottom: 10px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 10px; }
.cross-alert { margin-bottom: 8px; }
.fine-checks { display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 8px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin: 8px 0; flex-wrap: wrap; gap: 8px; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }
.field-warn :deep(.el-input__wrapper),
.field-warn :deep(.el-select__wrapper) {
  box-shadow: 0 0 0 1px #e6a23c inset;
}
.rate-warn { color: #e6a23c; font-weight: 600; }
:deep(.row-warn) { background: #fdf6ec !important; }
.th-label {
  display: inline-block;
  max-width: 100%;
  line-height: 1.25;
  white-space: normal;
  word-break: keep-all;
  vertical-align: middle;
  cursor: help;
}
:deep(.el-table th.el-table__cell > .cell) {
  white-space: normal;
  line-height: 1.25;
  overflow: visible;
  text-overflow: unset;
}
</style>
