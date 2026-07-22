<template>
  <div class="g10-disclosure" :data-testid="variant === 'listed' ? 'g10-disclosure-listed-table' : 'g10-disclosure-soe-table'">
    <div class="section-head">
      <h3 class="sheet-title">{{ dis.title.value }}</h3>
      <div class="head-actions">
        <GtIndexChip value="wp:G10-1" />
        <GtIndexChip v-if="noteSectionId" :value="noteChip" />
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g10-disclosure-sync-notes"
          :loading="isSyncing"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="primary"
          plain
          data-testid="g10-disclosure-pull-adj"
          @click="dis.pullFromAdjudication()"
        >↓ 从 G10-1/G10-2 分项带入</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          plain
          data-testid="g10-disclosure-pull-note-text"
          @click="onPullNoteTextFromCentral"
        >↑ 从附注带入文本</el-button>
        <G10ImportExportDropdown
          :wp-id="wpId"
          :sheet="variant === 'listed' ? '附注上市' : '附注国企'"
          @imported="onImported"
        />
        <el-button size="small" :loading="dis.aiLoading.value" :disabled="isReadonly" @click="dis.generateAiConclusion()">🤖 AI</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :loading="dis.procedureMarking.value"
          data-testid="g10-disclosure-mark-procedure"
          @click="onMarkProcedure"
        >
          {{ dis.procedureMarked.value ? '已回填 G10A（可重写）' : '回填 G10A 列报披露' }}
        </el-button>
        <GtReviewTrigger :section-id="variant === 'listed' ? 'G10-disclosure-listed' : 'G10-disclosure-soe'" />
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      :title="objectiveTitle"
    />

    <el-alert
      v-if="dis.adjudicatedAmount.value != null && !dis.hasAdjCrossMismatch.value"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已同步审定数（2101）：{{ fmt(dis.adjudicatedAmount.value) }}；附注合计
      {{ fmt(dis.disclosureClosingSum.value) }} 勾稽一致。
      <el-button link size="small" @click="dis.pullLatestAdjudicated(false)">刷新</el-button>
    </el-alert>

    <el-alert
      v-if="dis.adjChangedSincePull.value"
      type="info"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g10-disclosure-adj-stale"
    >
      G10-1 审定数已更新为 {{ fmt(dis.adjudicatedAmount.value ?? 0) }}，披露分项尚未重新带入。
      <el-button v-if="!isReadonly" link size="small" type="primary" @click="dis.pullFromAdjudication()">重新分项带入</el-button>
    </el-alert>

    <el-alert
      v-if="dis.pullSummary.value"
      :type="dis.lastPullUsedResidual.value ? 'warning' : 'info'"
      :closable="true"
      class="sync-hint"
      data-testid="g10-disclosure-pull-meta"
      @close="dis.clearPullSummary()"
    >
      带入来源：{{ dis.pullSummary.value }}
    </el-alert>

    <el-alert
      v-if="dis.hasAdjCrossMismatch.value"
      type="warning"
      :closable="false"
      show-icon
      class="sync-hint"
      data-testid="g10-disclosure-adj-cross"
    >
      附注合计 {{ fmt(dis.disclosureClosingSum.value) }} 与 G10-1 审定数
      {{ fmt(dis.adjudicatedAmount.value ?? 0) }} 差异 {{ fmt(dis.adjCrossVariance.value ?? 0) }}。
      <el-button v-if="!isReadonly" link size="small" type="primary" @click="dis.pullFromAdjudication()">分项带入</el-button>
    </el-alert>

    <el-alert
      v-for="(c, ci) in dis.crossChecks.value"
      :key="`${c.code}-${ci}`"
      :type="c.level === 'info' ? 'info' : 'warning'"
      :closable="false"
      show-icon
      class="sync-hint"
      :data-testid="`g10-disclosure-check-${c.code}`"
    >
      {{ c.message }}
      <template v-if="c.code === 'disclosure-l3-hint' || c.code === 'disclosure-fv5-vs-l6'">
        <span class="l3-chips">
          <GtIndexChip value="wp:G10-5" />
          <GtIndexChip value="wp:G10-6" />
        </span>
      </template>
    </el-alert>

    <!-- 上市：表1 变动表 -->
    <template v-if="variant === 'listed'">
      <h4 class="table-caption">交易性金融负债</h4>
      <el-table
        :data="dis.listedMovementDisplay.value"
        border
        size="small"
        style="font-size:13px"
        max-height="360"
        :row-class-name="rowClass"
        data-testid="g10-disclosure-movement-table"
      >
        <el-table-column :label="dis.colLabels.value.movement.item" prop="label" min-width="220" fixed />
        <el-table-column :label="dis.colLabels.value.movement.opening" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.openingAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateListedMovement(row.rowKey, 'openingAmount', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal || row.isParent }">{{ fmt(row.openingAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.movement.increase" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.increaseAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateListedMovement(row.rowKey, 'increaseAmount', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal || row.isParent }">{{ fmt(row.increaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.movement.decrease" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.decreaseAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateListedMovement(row.rowKey, 'decreaseAmount', v ?? 0)"
            />
            <span v-else :class="{ 'formula-cell': row.isTotal || row.isParent }">{{ fmt(row.decreaseAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.movement.closing" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.closingAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateListedMovement(row.rowKey, 'closingAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.closingAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <p class="guidance-inline">
        对于指定为以公允价值计量且其变动计入当期损益的金融负债，应分别列示期初、期末余额，并披露指定的理由和依据。
      </p>

      <div class="table-caption-row">
        <h4 class="table-caption">指定为 FVTPL 的金融负债</h4>
        <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addDesignatedRow()">+ 增行</el-button>
      </div>
      <el-table
        :data="dis.designatedDetailRows.value"
        border
        size="small"
        style="font-size:13px;margin-top:8px"
        data-testid="g10-disclosure-designated-table"
      >
        <el-table-column :label="dis.colLabels.value.designated.item" prop="label" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.label"
              size="small"
              @update:model-value="(v: string) => dis.updateDesignatedDetail(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.designated.opening" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.openingAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateDesignatedDetail(row.rowKey, 'openingAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.openingAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.designated.closing" width="120" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.closingAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateDesignatedDetail(row.rowKey, 'closingAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.closingAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.designated.reason" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.designationReason"
              size="small"
              placeholder="指定的理由和依据"
              @update:model-value="(v: string) => dis.updateDesignatedDetail(row.rowKey, 'designationReason', v)"
            />
            <span v-else>{{ row.designationReason }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button link size="small" type="danger" @click="dis.removeDesignatedRow(row.rowKey)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-caption-row">
        <p class="guidance-inline guidance-inline--tight">
          依据 CAS 37 第 41–43 条，应区分因自身信用风险变动引起的公允价值变动（计入其他综合收益）与其余变动（计入当期损益）。
        </p>
        <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addFvCreditRow()">+ 增行</el-button>
      </div>

      <el-table
        :data="[...dis.fvCreditRows.value, dis.fvCreditTotal.value]"
        border
        size="small"
        style="font-size:13px;margin-top:8px"
        :row-class-name="rowClass"
        data-testid="g10-disclosure-fv-credit-table"
      >
        <el-table-column :label="dis.colLabels.value.fvCredit.item" prop="label" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @update:model-value="(v: string) => dis.updateFvCredit(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.fvChange" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.fvChangeAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'fvChangeAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.creditCurrent" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.creditRiskCurrent"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'creditRiskCurrent', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.creditRiskCurrent) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.creditCumulative" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.creditRiskCumulative"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'creditRiskCumulative', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.creditRiskCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              link
              size="small"
              type="danger"
              @click="dis.removeFvCreditRow(row.rowKey)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-input
        class="maturity-note"
        :model-value="dis.maturityDiffNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly"
        :placeholder="dis.maturityDiffPlaceholder.value"
        @update:model-value="(v: string) => dis.updateTextField('maturityDiffNote', v)"
      />

      <div class="table-caption-row">
        <h4 class="table-caption">衍生金融负债</h4>
        <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addDerivativeRow()">+ 增行</el-button>
      </div>
      <el-table
        :data="dis.derivativeDisplay.value"
        border
        size="small"
        style="font-size:13px;margin-top:8px"
        :row-class-name="rowClass"
        data-testid="g10-disclosure-derivative-table"
      >
        <el-table-column :label="dis.colLabels.value.derivative.item" prop="label" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @update:model-value="(v: string) => dis.updateDerivativeRow(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.derivative.current" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.currentAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateDerivativeRow(row.rowKey, 'currentAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.derivative.prior" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateDerivativeRow(row.rowKey, 'priorAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              link
              size="small"
              type="danger"
              @click="dis.removeDerivativeRow(row.rowKey)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-input
        class="derivative-note"
        :model-value="dis.derivativeNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly"
        placeholder="说明：衍生金融负债产生的原因以及相关会计处理。"
        @update:model-value="(v: string) => dis.updateTextField('derivativeNote', v)"
      />
    </template>

    <!-- 国企：表1 余额表 -->
    <template v-else>
      <h4 class="table-caption">六、交易性金融负债</h4>
      <el-table
        :data="dis.soeBalanceDisplay.value"
        border
        size="small"
        style="font-size:13px"
        max-height="400"
        :row-class-name="rowClass"
        data-testid="g10-disclosure-balance-table"
      >
        <el-table-column :label="dis.colLabels.value.balance.item" prop="label" min-width="220" fixed />
        <el-table-column :label="dis.colLabels.value.balance.current" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.currentAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateSoeBalance(row.rowKey, 'currentAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.balance.prior" width="130" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !row.isParent && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateSoeBalance(row.rowKey, 'priorAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="table-caption-row">
        <p class="guidance-inline guidance-inline--tight">
          对于指定为以公允价值计量且其变动计入当期损益的金融负债，应披露因自身信用风险变动引起的公允价值变动计入其他综合收益的金额。
        </p>
        <el-button v-if="!isReadonly" size="small" link type="primary" @click="dis.addFvCreditRow()">+ 增行</el-button>
      </div>

      <el-table
        :data="[...dis.fvCreditRows.value, dis.fvCreditTotal.value]"
        border
        size="small"
        style="font-size:13px;margin-top:8px"
        :row-class-name="rowClass"
        data-testid="g10-disclosure-fv-credit-table"
      >
        <el-table-column :label="dis.colLabels.value.fvCredit.item" prop="label" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @update:model-value="(v: string) => dis.updateFvCredit(row.rowKey, 'label', v)"
            />
            <span v-else>{{ row.label }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.fvChange" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.fvChangeAmount"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'fvChangeAmount', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.fvChangeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.creditCurrent" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.creditRiskCurrent"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'creditRiskCurrent', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.creditRiskCurrent) }}</span>
          </template>
        </el-table-column>
        <el-table-column :label="dis.colLabels.value.fvCredit.creditCumulative" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.creditRiskCumulative"
              size="small"
              :controls="false"
              style="width:100%"
              @update:model-value="(v: number) => dis.updateFvCredit(row.rowKey, 'creditRiskCumulative', v ?? 0)"
            />
            <span v-else class="formula-cell">{{ fmt(row.creditRiskCumulative) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              link
              size="small"
              type="danger"
              @click="dis.removeFvCreditRow(row.rowKey)"
            >删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-input
        class="maturity-note"
        :model-value="dis.maturityDiffNote.value"
        type="textarea"
        :autosize="{ minRows: 2, maxRows: 4 }"
        :disabled="isReadonly"
        :placeholder="dis.maturityDiffPlaceholder.value"
        @update:model-value="(v: string) => dis.updateTextField('maturityDiffNote', v)"
      />
    </template>

    <G10AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      v-model:note="auditNote"
      v-model:conclusion="auditConclusion"
      :note-ai-section="noteAiSection"
      conclusion-ai-section="disclosure-conclusion"
      note-placeholder="填写审计说明：披露完整性、列报格式、与 G10-1 审定勾稽及 CAS 37 信用风险拆分披露核对情况。"
      note-hint="覆盖披露完整性、金额勾稽及监管格式要求。"
      conclusion-placeholder="填写审计结论：A、未见异常。B、除上述重大不符事项应作为调整事项予以调整外，其余未见异常。C、由于存在重大未调整事项或审计范围受限，不可确认。"
      :related-context="{ variant, 审定数: dis.adjudicatedAmount.value, 附注合计: dis.disclosureClosingSum.value }"
    />

    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>结构与 Excel 底稿一致；期末合计应与 G10-1 审定表（2101）勾稽。</p>
        <p>「同步到附注」推送结构化子表至附注模块「{{ noteSectionId }} 交易性金融负债」。</p>
        <p>「从附注带入文本」可从附注模块「{{ noteSectionId }}」反向拉取叙述正文至审计说明（与 EventBus 刷新互补）。</p>
        <p v-if="variant === 'listed'">
          上市格式：变动表（期初/增加/减少/期末）→ 指定负债理由 → 信用风险拆分 → 衍生负债；建议先在 G10-2 维护种类与增减，再点「分项带入」。
        </p>
        <p v-else>
          国企格式：项目/期末公允价值/期初公允价值 + 信用风险拆分表；C 列可引用 G10-1 审定表分项。
        </p>
        <p>有 Level3 余额时，公允价值层次及调节过程见 G10-5/G10-6。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, watch, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useG10Disclosure } from '../../composables/useG10Disclosure'
import {
  buildG10ListedSyncPayloads,
  buildG10SoeSyncPayloads,
} from '../../composables/g10DisclosureSyncPayload'
import { G10_NOTE_SECTION } from '../../composables/g10NoteSectionMap'
import { api } from '@/services/apiProxy'
import {
  confirmNavigateToSheet,
  dispatchProcedureFocus,
} from '../../composables/g8CrossHelpers'
import {
  G10A_DISCLOSURE_PROGRAM_NOS,
  G10A_PROCEDURE_SHEET,
} from '../../composables/g10FvCrossHelpers'
import type { ChecklistResponse } from '../../composables/useF1FormData'
import type { G10AiSection } from '../../composables/useG10AiGenerate'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import G10AuditTextCards from '../G10AuditTextCards.vue'
import G10ImportExportDropdown from '../G10ImportExportDropdown.vue'

const props = defineProps<{
  variant: 'listed' | 'soe'
  allResponses: Map<string, ChecklistResponse>
  wpId: string
  projectId?: string
  applicableStandards?: string[]
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const emit = defineEmits<{ imported: [] }>()

const jumpToSection = inject<((sheetName: string) => void) | null>('jumpToSection', null)

const dis = useG10Disclosure({
  variant: props.variant,
  allResponses: toRef(props, 'allResponses'),
  debouncedSave: props.debouncedSave,
  wpId: toRef(props, 'wpId'),
  projectId: computed(() => props.projectId || ''),
  isReadonly: toRef(props, 'isReadonly'),
})

const objectiveTitle = computed(() =>
  props.variant === 'listed'
    ? '审计目标：确认交易性金融负债附注（上市公司格式：变动表 + 指定理由 + 信用风险拆分 + 衍生负债）披露充分恰当，并与 G10-1 审定勾稽。'
    : '审计目标：确认交易性金融负债附注（国企格式：期末/期初公允价值 + 信用风险拆分）披露充分恰当，并与 G10-1 审定勾稽。',
)

const noteAiSection = computed<G10AiSection>(() =>
  props.variant === 'listed' ? 'disclosure-listed-note' : 'disclosure-soe-note',
)

const NOTE_KEY = `G10-disclosure-${props.variant}-audit-note`
const CONCLUSION_KEY = `G10-disclosure-${props.variant}-audit-conclusion`
const auditNote = ref(props.allResponses.get(NOTE_KEY)?.remark ?? '')
const auditConclusion = ref(props.allResponses.get(CONCLUSION_KEY)?.remark ?? '')
watch(auditNote, (v) => {
  if (!props.isReadonly) props.debouncedSave(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: v })
})
watch(auditConclusion, (v) => {
  if (!props.isReadonly) props.debouncedSave(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: v })
})

const noteSectionId = computed(() => G10_NOTE_SECTION[props.variant].trading)
const noteChip = computed(() => `Note:${noteSectionId.value}`)
const isSyncing = ref(false)

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const standards = props.applicableStandards ?? []
  const snap = dis.getSyncSnapshot(auditNote.value)
  const payloads = props.variant === 'listed'
    ? buildG10ListedSyncPayloads(props.wpId, standards, snap as any)
    : buildG10SoeSyncPayloads(props.wpId, standards, snap as any)
  if (!payloads.length) {
    ElMessage.warning('当前项目准则不适用附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      const data = result?.data ?? result
      rows += Number(data?.rows_synced ?? 0)
    }
    ElMessage.success(`已同步 ${rows} 行到附注「${noteSectionId.value} 交易性金融负债」`)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}

function onImported(): void {
  emit('imported')
}

async function onPullNoteTextFromCentral(): Promise<void> {
  const text = await dis.pullNoteTextFromCentral()
  if (text) auditNote.value = text
}

async function onMarkProcedure() {
  const n = await dis.markProcedureComplete()
  if (n < 0) return
  dispatchProcedureFocus({
    programNos: [...G10A_DISCLOSURE_PROGRAM_NOS],
    sheetCode: 'G10A',
    sheetName: G10A_PROCEDURE_SHEET,
  })
  const go = await confirmNavigateToSheet({
    title: '已回填 G10A',
    message: `列报披露程序（步骤 ${[...G10A_DISCLOSURE_PROGRAM_NOS].join('/')}）已标记完成。是否前往 G10A 程序表查看？`,
    confirmText: '前往 G10A',
  })
  if (go && jumpToSection) {
    jumpToSection('G10A')
    setTimeout(() => {
      dispatchProcedureFocus({
        programNos: [...G10A_DISCLOSURE_PROGRAM_NOS],
        sheetCode: 'G10A',
        sheetName: G10A_PROCEDURE_SHEET,
      })
    }, 400)
  }
}

function fmt(v: number) {
  return Number(v || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function rowClass({ row }: { row: { isTotal?: boolean; isParent?: boolean } }): string {
  if (row.isTotal) return 'is-total-row'
  if (row.isParent) return 'is-parent-row'
  return ''
}
</script>

<style scoped>
.g10-disclosure { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.sync-hint { margin-bottom: 8px; }
.objective-alert { margin-bottom: 8px; }
.table-caption { margin: 12px 0 6px; font-size: 14px; font-weight: 600; }
.table-caption-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin: 12px 0 6px; }
.table-caption-row .table-caption { margin: 0; }
.guidance-inline { margin: 8px 0; font-size: 12px; color: #606266; line-height: 1.5; }
.guidance-inline--tight { margin: 0; flex: 1; }
.l3-chips { display: inline-flex; gap: 6px; margin-left: 8px; vertical-align: middle; }
.maturity-note, .derivative-note { margin-top: 8px; }
.formula-cell { font-weight: 600; font-variant-numeric: tabular-nums; border-bottom: 1px dashed #999; }
.guidance-details { margin-top: 10px; font-size: 12px; color: #606266; }
.guidance-content p { margin: 4px 0; }
:deep(.is-total-row) { font-weight: 600; background: var(--el-fill-color-light); }
:deep(.is-parent-row) { background: #fafafa; }
</style>
