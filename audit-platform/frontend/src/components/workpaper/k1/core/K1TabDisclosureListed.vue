<template>
  <div class="k1-disclosure-listed" data-testid="k1-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（上市公司）</h3>
      <div class="head-actions">
        <el-tag size="small" type="info">{{ disc.noteTarget.value.sectionId }} · 其他应收款</el-tag>
        <el-tag size="small" type="warning">{{ agingPresetLabel }}</el-tag>
        <el-tag size="small">单位：{{ displayPrefs.unitSuffix }}</el-tag>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="disc.refreshFromSources(false)">
          从源底稿取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="disc.refreshFromSources(true)">
          强制覆盖
        </el-button>
        <el-button
          size="small"
          type="success"
          :loading="disc.isSyncing.value"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes()"
        >
          同步至附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <el-button size="small" @click="handleReview('K1-disclosure-listed')">💬复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按上市公司附注格式披露其他应收款账龄、款项性质、ECL 三阶段（期末＋上年年末）坏账、变动、核销及前五名等，与 K1-1/K1-2/K1-3/K1-9 勾稽，并回写附注五、8。"
    />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①②</span> 规模·结构：账龄（含 1 年以内月度细分）→ 款项性质</div>
        <div class="guide-step"><span class="step-num">③</span> 减值计量：ECL 三阶段 × 期末/上年年末，共 6 张表</div>
        <div class="guide-step"><span class="step-num">④⑤</span> 减值变动 → 转回逐笔 → 核销（汇总＋逐项）</div>
        <div class="guide-step"><span class="step-num">⑥⑦</span> 集中度：前五名；特殊列报：资金集中管理</div>
        <div class="guide-step"><span class="step-num">⑧</span> 特殊性质：应收政府补助逐项</div>
        <div class="guide-step"><span class="step-num">⑨⑩</span> 表外化：转移终止确认 → 继续涉入资产负债</div>
      </div>
    </div>

    <el-alert
      v-if="disc.adjudication.value.receivableEnd"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动 K1-1 审定：其他应收款期末 {{ fmt(disc.adjudication.value.receivableEnd) }}
      · 坏账准备 {{ fmt(disc.adjudication.value.badDebtEnd) }}
      <template v-if="disc.lastSyncHint.value"> · 取数 {{ disc.lastSyncHint.value }}</template>
    </el-alert>

    <!-- 勾稽告警区（T1/T3/T4/T4prior/T5/T6/T7/T12/F8-48） -->
    <el-alert
      v-if="disc.summaryTieOut.value.applicable && !disc.summaryTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`F8-48 汇总表明细行之和 ${fmt(disc.summaryTieOut.value.sum)} ≠ 合计 ${fmt(disc.summaryFigures.value.total)}（差 ${fmt(disc.summaryTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!disc.agingTieOut.value.matched && disc.agingTieOut.value.subtotal"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`T1 账龄小计 ${fmt(disc.agingTieOut.value.subtotal)} ≠ K1-1 审定 ${fmt(disc.adjudication.value.receivableEnd)}（差 ${fmt(disc.agingTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!disc.withinOneYearTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`T3 1年以内月度细分合计 ${fmt(disc.withinOneYearTieOut.value.subSumEnd)} ≠ 1年以内 ${fmt(disc.withinOneYearTieOut.value.within1End)}（差 ${fmt(disc.withinOneYearTieOut.value.diffEnd)}）`"
    />
    <el-alert
      v-if="!disc.provisionTieOut.value.matched && disc.endStageProvisionTotal.value"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`T4 账龄表减：坏账准备 ${fmt(disc.provisionTieOut.value.agingProvision)} ≠ 期末三阶段坏账合计 ${fmt(disc.provisionTieOut.value.stageClosing)}（差 ${fmt(disc.provisionTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!disc.priorProvisionTieOut.value.matched && disc.priorStageProvisionTotal.value"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`T4' 账龄表上年年末坏账准备 ${fmt(disc.priorProvisionTieOut.value.agingProvision)} ≠ 上年年末三阶段坏账合计 ${fmt(disc.priorProvisionTieOut.value.stageTotal)}（差 ${fmt(disc.priorProvisionTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!disc.movementTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="movementTieOutTitle"
    />
    <el-alert
      v-if="disc.top5Check.value.exceeded"
      type="warning"
      :closable="false"
      class="tie-alert"
      :title="`T12 前五名占比合计 ${disc.top5Check.value.totalPct.toFixed(2)}% 超过 100%，请检查占比分母是否取自账龄小计`"
    />

    <K1DisclosureTracePanel
      :rows="trace.traceRows.value"
      :open-count="trace.openCount.value"
      @navigate-sheet="(s) => emit('navigate-sheet', s)"
    />

    <!-- ① 按账龄披露 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">① 按账龄披露</span>
          <el-tag size="small" type="warning">附注 {{ disc.noteTarget.value.sectionId }}·按账龄披露</el-tag>
        </div>
      </template>
      <el-table :data="disc.agingRows.value" border size="small" :row-class-name="agingRowClass">
        <el-table-column label="账　龄" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="row.labelEditable && !isReadonly"
              :model-value="row.label"
              size="small"
              class="sub-label-input"
              @change="(v: string) => disc.updateAgingRowLabel(row.rowId, v)"
            />
            <span
              v-else
              :class="{
                'is-total': row.kind === 'total' || row.kind === 'subtotal' || row.kind === 'subtotal1y' || row.kind === 'provision',
                'is-sub': row.kind === 'sub',
              }"
            >{{ row.label }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.endAmount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateAgingRow(row.rowId, 'endAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="上年年末余额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.editable && !isReadonly"
              :model-value="row.priorAmount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateAgingRow(row.rowId, 'priorAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.priorAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="template-tip">
        「其中：0-X个月」「X-Y个月」为 1 年以内的月度细分行（标签可按项目改写），不参与「小计」求和；
        「1年以内小计：」自动等于「1年以内」行。
      </p>
    </el-card>

    <!-- ② 按款项性质披露 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">② 按款项性质披露</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAddNature">新增性质行</el-button>
        </div>
      </template>
      <el-table :data="natureTableData" border size="small" :row-class-name="natureRowClass">
        <el-table-column label="项　目" min-width="150" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!row.isTotal && !isReadonly"
              :model-value="row.label"
              size="small"
              @change="(v: string) => disc.updateNatureRow(row.rowId, 'label', v)"
            />
            <span v-else :class="{ 'is-total': row.isTotal }">{{ row.label }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">自动</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="期末金额" align="center">
          <el-table-column label="账面余额" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.endGross"
                size="small"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'endGross', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.endGross) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.endProvision"
                size="small"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'endProvision', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.endProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="150" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式：账面余额 − 坏账准备" placement="top">
                <span class="formula-cell">{{ fmt(row.endBookValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="上年年末金额" align="center">
          <el-table-column label="账面余额" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.priorGross"
                size="small"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'priorGross', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.priorGross) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="150" align="right">
            <template #default="{ row }">
              <WpAmountInput
                v-if="!row.isTotal && !isReadonly"
                :model-value="row.priorProvision"
                size="small"
                style="width: 100%"
                @change="(v: number) => disc.updateNatureRow(row.rowId, 'priorProvision', v ?? 0)"
              />
              <span v-else class="amount-cell">{{ fmt(row.priorProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面价值" width="150" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式：账面余额 − 坏账准备" placement="top">
                <span class="formula-cell">{{ fmt(row.priorBookValue) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button
              v-if="!row.isTotal"
              size="small"
              type="danger"
              link
              @click="disc.removeNatureRow(row.rowId)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="!disc.natureTieOut.value.matched && disc.natureTieOut.value.totalGross"
        type="warning"
        :closable="false"
        class="inline-alert"
        :title="`T2 性质合计账面余额 ${fmt(disc.natureTieOut.value.totalGross)} ≠ K1-1 审定 ${fmt(disc.adjudication.value.receivableEnd)}（差 ${fmt(disc.natureTieOut.value.diff)}）`"
      />
    </el-card>

    <!-- ③ 坏账准备计提情况 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">③ 坏账准备计提情况（ECL 三阶段）</span>
          <div class="head-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('eclBasis')">🤖 AI 生成计提依据</el-button>
            <el-button size="small" link @click="handleReview('K1-disclosure-listed-ecl')">💬复核</el-button>
          </div>
        </div>
      </template>

      <div class="methodology-block">
        <p>（15号文第十九条（四）5.采用一般预期信用损失模型计提坏账准备的应收款项，应分三阶段披露坏账准备计提情况，以及各阶段划分依据和坏账准备计提比例。）</p>
        <p><b>第二阶段划分依据</b>：发生下列情形中的一种或多种时，则属于「自初始确认后信用风险显著增加」——款项逾期超过 30 天但未超过 90 天；欠款方发生影响其偿付能力的负面事件；担保物价值或第三方提供的担保或信用增级质量的显著不利变化。</p>
        <p><b>第三阶段划分依据</b>：发生下列情形中的一种或多种时，则属于「已发生信用减值」——款项逾期超过 90 天；欠款方发生重大财务困难，或很可能破产或进行其他财务重组；其他违反合同约定且表明金融资产已存在客观减值证据的情形。</p>
      </div>

      <div class="period-label">期末</div>
      <template v-for="block in endStageBlocks" :key="`end-${block.stage}`">
        <div class="stage-head">
          <span class="stage-title">{{ block.title }}</span>
          <el-switch
            v-if="block.stage === 2"
            :model-value="disc.payload.value.stage2NoneEnd"
            :disabled="isReadonly"
            size="small"
            active-text="本期不存在第二阶段"
            @change="(v: boolean) => disc.toggleStage2None('end', v)"
          />
        </div>
        <el-alert
          v-if="block.stage === 2 && disc.payload.value.stage2NoneEnd"
          type="info"
          :closable="false"
          class="inline-alert"
          :title="STAGE2_NONE_TEXT_END"
        />
        <K1StageEclTable
          v-else
          :rows="block.rows"
          :rate-label="block.rateLabel"
          :is-readonly="isReadonly"
          @update="(rowId, field, value) => disc.updateStageRow(block.stage, rowId, field, value, 'end')"
        />
      </template>

      <div class="note-block">
        <div class="note-block-head">
          <span>说明：本期发生损失准备的其他应收款账面余额显著变动的情况</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('balanceChange')">🤖 AI</el-button>
        </div>
        <el-input
          :model-value="disc.noteSection('balanceChange')"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="说明账面余额较上年年末的增减金额与幅度、主要成因及对损失准备计提的影响"
          @change="(v: string) => disc.updateNoteSection('balanceChange', v)"
        />
      </div>
      <div class="note-block">
        <div class="note-block-head">
          <span>说明：本期坏账准备计提金额以及评估金融工具的信用风险是否显著增加所采用的依据</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('eclBasis')">🤖 AI</el-button>
        </div>
        <el-input
          :model-value="disc.noteSection('eclBasis')"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="三阶段划分的量化/定性标准、预期信用损失率确定依据、本期计提金额与上期计提比例差异原因"
          @change="(v: string) => disc.updateNoteSection('eclBasis', v)"
        />
      </div>

      <el-collapse v-model="priorStageCollapse" class="prior-collapse">
        <el-collapse-item name="prior">
          <template #title>
            <span class="collapse-title">上年年末坏账准备计提情况（三阶段快照）</span>
            <el-tag size="small" type="info" class="collapse-tag">
              合计 {{ fmt(disc.priorStageProvisionTotal.value) }}
            </el-tag>
          </template>
          <template v-for="block in priorStageBlocks" :key="`prior-${block.stage}`">
            <div class="stage-head">
              <span class="stage-title">{{ block.title }}</span>
              <el-switch
                v-if="block.stage === 2"
                :model-value="disc.payload.value.stage2NonePrior"
                :disabled="isReadonly"
                size="small"
                active-text="上年年末不存在第二阶段"
                @change="(v: boolean) => disc.toggleStage2None('prior', v)"
              />
            </div>
            <el-alert
              v-if="block.stage === 2 && disc.payload.value.stage2NonePrior"
              type="info"
              :closable="false"
              class="inline-alert"
              :title="STAGE2_NONE_TEXT_PRIOR"
            />
            <K1StageEclTable
              v-else
              :rows="block.rows"
              :rate-label="block.rateLabel"
              :is-readonly="isReadonly"
              @update="(rowId, field, value) => disc.updateStageRow(block.stage, rowId, field, value, 'prior')"
            />
          </template>
        </el-collapse-item>
      </el-collapse>
    </el-card>

    <!-- ④ 本期计提、收回或转回 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header><span class="card-title">④ 本期计提、收回或转回的坏账准备情况</span></template>
      <el-table :data="disc.stageMovements.value" border size="small" :row-class-name="movementRowClass">
        <el-table-column prop="label" label="坏账准备" min-width="200" />
        <el-table-column label="第一阶段" align="center">
          <el-table-column label="未来12个月预期信用损失" width="180" align="right">
            <template #default="{ row }">{{ fmt(row.stage1) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="第二阶段" align="center">
          <el-table-column label="整个存续期预期信用损失（未发生信用减值）" width="200" align="right">
            <template #default="{ row }">{{ fmt(row.stage2) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="第三阶段" align="center">
          <el-table-column label="整个存续期预期信用损失（已发生信用减值）" width="200" align="right">
            <template #default="{ row }">{{ fmt(row.stage3) }}</template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="合计" width="150" align="right">
          <template #default="{ row }">{{ fmt(row.stage1 + row.stage2 + row.stage3) }}</template>
        </el-table-column>
        <template #empty>暂无数据，请先在 K1-3 维护三阶段转入转出矩阵后点击「从源底稿取数」</template>
      </el-table>
      <p class="template-tip">
        数据来自 K1-3 三阶段转入转出矩阵（只读）。勾稽：期末余额 = 期末三阶段坏账合计
        {{ fmt(disc.endStageProvisionTotal.value) }}；期初余额 = 上年年末三阶段坏账合计
        {{ fmt(disc.priorStageProvisionTotal.value) }}。
      </p>
    </el-card>

    <!-- ⑤ 重大转回 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">其中：本期转回或收回金额重要的坏账准备</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addReversalRow()">新增行</el-button>
        </div>
      </template>
      <el-table :data="disc.reversalRows.value" border size="small" max-height="320">
        <el-table-column label="单位名称" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回原因" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收回方式" width="130">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.method"
              size="small"
              clearable
              filterable
              allow-create
              placeholder="选择"
              style="width: 100%"
              @change="(v: string) => disc.updateReversalRow(row.rowId, 'method', v ?? '')"
            >
              <el-option v-for="m in RECOVERY_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.method || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="原确定坏账准备的依据" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.basis" size="small" @change="(v: string) => disc.updateReversalRow(row.rowId, 'basis', v)" />
            <span v-else>{{ row.basis || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转回或收回金额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.amount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateReversalRow(row.rowId, 'amount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <template #empty>暂无重大转回记录（可在 K1-9 维护后取数）</template>
        <template #append>
          <div class="table-total">合　计　转回或收回金额：{{ fmt(reversalTotal) }}</div>
        </template>
      </el-table>
      <div class="methodology-block">
        （注：本表列报本报告期前已全额计提坏账准备，或计提减值准备的比例较大，但在本期又全额收回或转回，或在本期收回或转回比例较大的其他应收款。对本期通过重组等方式收回的金额重大的其他应收款，则应逐笔列报，金额不重大的，可汇总列报。）
      </div>
    </el-card>

    <!-- ⑤b 核销 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑤ 本期实际核销的其他应收款情况</span>
          <div class="head-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addWriteoffRow()">新增明细</el-button>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('writeoffNote')">🤖 AI 生成说明</el-button>
          </div>
        </div>
      </template>
      <div class="writeoff-summary">
        实际核销的其他应收款合计：<b class="amount-cell">{{ fmt(disc.payload.value.writeoffSummaryAmount) }}</b>
        <span class="hint-inline">（由下方明细自动汇总，勾稽 ④「本年核销」行）</span>
      </div>
      <div class="sub-block-title">其中：重要的其他应收款核销情况（逐项披露）</div>
      <el-table :data="disc.payload.value.writeoffDetailRows" border size="small" max-height="320">
        <el-table-column label="单位名称" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他应收款性质" width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.nature" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'nature', v)" />
            <span v-else>{{ row.nature || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销金额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.amount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateWriteoffRow(row.rowId, 'amount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.reason" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'reason', v)" />
            <span v-else>{{ row.reason || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="履行的核销程序" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.procedure" size="small" @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'procedure', v)" />
            <span v-else>{{ row.procedure || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否由关联交易产生" width="150">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.relatedParty"
              size="small"
              clearable
              placeholder="选择"
              style="width: 100%"
              @change="(v: string) => disc.updateWriteoffRow(row.rowId, 'relatedParty', v ?? '')"
            >
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
            </el-select>
            <span v-else>{{ row.relatedParty || '—' }}</span>
          </template>
        </el-table-column>
        <template #empty>暂无核销明细（可在 K1-9 维护后取数）</template>
      </el-table>
      <div class="methodology-block">
        【15号文第十九条（四）6，对于其中重要的应收款项，应<b>逐项</b>披露款项性质、核销原因、履行的核销程序及核销金额。实际核销的款项由关联交易产生的，应单独披露；】
      </div>
      <div class="note-block">
        <div class="note-block-head">
          <span>说明</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('writeoffNote')">🤖 AI</el-button>
        </div>
        <el-input
          :model-value="disc.noteSection('writeoffNote')"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="核销总额及笔数、主要核销原因、已履行的内部审批程序、是否存在关联交易产生的核销"
          @change="(v: string) => disc.updateNoteSection('writeoffNote', v)"
        />
      </div>
    </el-card>

    <!-- ⑥ 前五名 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑥ 按欠款方归集的其他应收款期末余额前五名单位情况</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addTop5Row()">新增行</el-button>
        </div>
      </template>
      <el-table :data="disc.top5Rows.value" border size="small">
        <el-table-column label="单位名称" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName || '—' }}</span>
            <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">K1-2</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="款项性质" width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.nature" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'nature', v)" />
            <span v-else>{{ row.nature || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="其他应收款期末余额" width="170" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.endBalance"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateTop5Row(row.rowId, 'endBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => disc.updateTop5Row(row.rowId, 'aging', v)" />
            <span v-else>{{ row.aging || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占其他应收款期末余额合计数的比例(%)" width="180" align="right">
          <template #default="{ row }">
            <el-tooltip content="公式：本行期末余额 ÷ 前五名合计" placement="top">
              <span class="formula-cell">{{ formatRate(row.proportionPct) }}</span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column label="坏账准备期末余额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.provision"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateTop5Row(row.rowId, 'provision', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.provision) }}</span>
          </template>
        </el-table-column>
        <template #empty>暂无数据（可从 K1-2 明细按期末余额降序取前 5）</template>
      </el-table>
      <div class="methodology-block">
        【按欠款方归集的期末余额前五名的其他应收款，应分别披露欠款方名称、期末余额及占其他应收款期末余额合计数的比例、款项的性质、对应的账龄、坏账准备期末余额；】
      </div>
    </el-card>

    <!-- ⑦ 资金集中管理 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑦ 资金集中管理</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('fundCentralization')">🤖 AI</el-button>
        </div>
      </template>
      <div class="fund-row">
        <span>因资金集中管理列报于其他应收款的金额：</span>
        <el-input-number
          v-if="!isReadonly"
          :model-value="disc.payload.value.fundCentralizationAmount"
          size="small"
          :controls="false"
          :precision="2"
          :formatter="amountFormatter"
          :parser="amountParser"
          style="width: 200px"
          @change="(v: number) => disc.updateFundCentralization('amount', v ?? 0)"
        />
        <span v-else class="amount-cell">{{ fmt(disc.payload.value.fundCentralizationAmount) }}</span>
      </div>
      <el-input
        v-model="fundNoteProxy"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="披露因资金集中管理而列报于其他应收款的金额及相关情况（15号文第十九条（五）8.）"
        class="note-area"
      />
      <div class="methodology-block">
        <p>【提示：考虑对「非经营性资金占有和其他关联资金往来的专项说明」的影响。】</p>
        <p>【提示：根据《企业会计准则解释第15号》，通过内部结算中心、财务公司等对母公司及成员单位资金实行集中统一管理的，对于成员单位归集至集团母公司账户的资金，成员单位应当在资产负债表「其他应收款」项目中列示，或者根据重要性原则并结合本企业的实际情况，在「其他应收款」项目之上增设「应收资金集中管理款」项目单独列示。】</p>
      </div>
    </el-card>

    <!-- ⑧ 应收政府补助 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑧ 应收政府补助情况（逐项披露）</span>
          <div class="head-actions">
            <el-tag size="small" type="success">附注去向：五、8·应收政府补助情况</el-tag>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addGovGrantRow()">新增行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="disc.payload.value.govGrantRows" border size="small" max-height="300">
        <el-table-column label="单位名称（政府补助的发文单位）" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.unitName" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'unitName', v)" />
            <span v-else>{{ row.unitName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="政府补助项目名称" min-width="160">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.projectName" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'projectName', v)" />
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="150" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.endBalance"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateGovGrantRow(row.rowId, 'endBalance', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.aging" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'aging', v)" />
            <span v-else>{{ row.aging || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预计收取的时间、金额及依据" min-width="200">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.expectedCollection" size="small" @change="(v: string) => disc.updateGovGrantRow(row.rowId, 'expectedCollection', v)" />
            <span v-else>{{ row.expectedCollection || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="disc.removeGovGrantRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>K1-2 无「政府补助」性质明细，可手工新增</template>
      </el-table>
      <div class="methodology-block">
        <p>（信息披露解释性公告2号要求：对于报告期末按应收金额确认的政府补助，公司应按补助单位和补助项目逐项披露应收款项的期末余额、账龄以及预计收取的时间、金额及依据。如公司未能在预计时点收到预计金额的政府补助，公司应披露原因。）</p>
        <p>【确认应收款项时，应履行重大业务咨询程序。】</p>
      </div>
    </el-card>

    <!-- ⑨ 转移终止确认 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑨ 因金融资产转移而终止确认的其他应收款情况</span>
          <div class="head-actions">
            <el-tag size="small" type="success">附注去向：五、8·因金融资产转移而终止确认的其他应收款情况</el-tag>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addTransferRow()">新增行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="disc.payload.value.transferRows" border size="small">
        <el-table-column label="项　目" min-width="170">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.item" size="small" @change="(v: string) => disc.updateTransferRow(row.rowId, 'item', v)" />
            <span v-else>{{ row.item || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转移方式" width="150">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.method"
              size="small"
              clearable
              filterable
              allow-create
              placeholder="选择"
              style="width: 100%"
              @change="(v: string) => disc.updateTransferRow(row.rowId, 'method', v ?? '')"
            >
              <el-option v-for="m in TRANSFER_METHODS" :key="m" :label="m" :value="m" />
            </el-select>
            <span v-else>{{ row.method || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="终止确认金额" width="160" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="row.derecognizedAmount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateTransferRow(row.rowId, 'derecognizedAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.derecognizedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="与终止确认相关的利得或损失" width="200" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.gainLoss"
              size="small"
              :controls="false"
              :precision="2"
              :formatter="amountFormatter"
              :parser="amountParser"
              style="width: 100%"
              @change="(v: number) => disc.updateTransferRow(row.rowId, 'gainLoss', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmt(row.gainLoss) }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="disc.removeTransferRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
        <template #empty>本期不存在因金融资产转移而终止确认的其他应收款</template>
        <template #append>
          <div class="table-total">
            合　计　终止确认金额：{{ fmt(transferTotals.amount) }}　·　利得或损失：{{ fmt(transferTotals.gainLoss) }}
          </div>
        </template>
      </el-table>
      <div class="methodology-block">
        【因金融资产转移而终止确认的应收款项，应列示金融资产转移的方式、终止确认的应收款项金额，及与终止确认相关的利得或损失；】
      </div>
    </el-card>

    <!-- ⑩ 继续涉入 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">⑩ 转移其他应收款且继续涉入形成的资产、负债的金额</span>
          <div class="head-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addContinuedInvolvementRow('asset')">＋资产行</el-button>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="disc.addContinuedInvolvementRow('liability')">＋负债行</el-button>
          </div>
        </div>
      </template>
      <el-table :data="continuedInvolvementTableData" border size="small" :row-class-name="ciRowClass">
        <el-table-column label="项　目" min-width="240">
          <template #default="{ row }">
            <el-input
              v-if="row.kind === 'data' && !isReadonly"
              :model-value="row.item"
              size="small"
              placeholder="如：因保理继续涉入形成的应收款"
              @change="(v: string) => disc.updateContinuedInvolvementRow(row.rowId, 'item', v)"
            />
            <span v-else :class="{ 'is-total': row.kind === 'subtotal', 'is-header': row.kind === 'header' }">
              {{ row.label }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" width="180" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.kind === 'data' && !isReadonly"
              :model-value="row.amount"
              size="small"
              style="width: 100%"
              @change="(v: number) => disc.updateContinuedInvolvementRow(row.rowId, 'amount', v ?? 0)"
            />
            <span v-else-if="row.kind === 'subtotal'" class="amount-cell is-total">{{ fmt(row.amount) }}</span>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="56" align="center">
          <template #default="{ row }">
            <el-button
              v-if="row.kind === 'data'"
              size="small"
              type="danger"
              link
              @click="disc.removeContinuedInvolvementRow(row.rowId)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="methodology-block">
        【转移应收款项且继续涉入的，应披露资产转移方式、分项列示继续涉入形成的资产、负债的金额。】
      </div>
      <div class="note-block">
        <div class="note-block-head">
          <span>说明（资产转移方式；未全部终止确认的被转移金融资产与相关负债之间的关系；已终止确认的金融资产继续涉入的性质及相关风险的信息）</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('transferNote')">🤖 AI</el-button>
        </div>
        <el-input
          :model-value="disc.noteSection('transferNote')"
          type="textarea"
          :autosize="{ minRows: 3 }"
          :disabled="isReadonly"
          placeholder="若无此类交易，可填写：本期不存在转移其他应收款且继续涉入的情形。"
          @change="(v: string) => disc.updateNoteSection('transferNote', v)"
        />
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">审计说明（同步至附注文字）</span>
          <el-button size="small" @click="handleReview('K1-disclosure-listed-note')">💬复核</el-button>
        </div>
      </template>
      <el-input
        v-model="disc.noteText.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="其他应收款披露的整体说明、与源底稿的衔接、特殊事项等"
        @change="disc.persistNote()"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（源模板 10 段对照 · 非打印）</summary>
      <ul>
        <li><b>① 按账龄</b>：账龄段随项目 aging config（三年/五年/自定义）；1 年以内可细分月度区间（源模板 R9/R10），细分行不进「小计」，「1年以内小计：」= 1年以内。</li>
        <li><b>② 按款项性质</b>：期末/上年年末各三列（账面余额−坏账准备=账面价值），默认「备用金」「保证金、押金」，可无限量添加行。</li>
        <li><b>③ 坏账准备计提情况</b>：期末＋上年年末共 6 张表；无第二阶段时开启开关改为文字表述（源模板 R49/R80）；两个说明段落对应源模板 R59/R60。</li>
        <li><b>④ 坏账变动</b>：数据来自 K1-3 三阶段转入转出矩阵（本表只读，请在 K1-3 修改后重新取数）。源模板另列「本期转销」行，K1-3 当前未区分转销与核销，如需区分请在 K1-3 增设。</li>
        <li><b>⑤ 核销</b>：汇总金额由逐项明细自动求和；重要核销须逐项披露，关联交易产生的单独披露。</li>
        <li><b>⑥ 前五名</b>：占比分母为账龄小计；占比合计超 100% 会告警。</li>
        <li><b>⑦ 资金集中管理</b>：仅文字披露（附注 五、8 无独立表），需考虑对「非经营性资金占有和其他关联资金往来的专项说明」的影响。</li>
        <li><b>⑧⑨⑩ 应收政府补助 / 转移终止确认 / 继续涉入</b>：源模板 R136-R160 明确列在其他应收款披露内，<b>推送</b>至 五、8（模板 2026-07-31 已补齐这三张表）。</li>
        <li><b>汇总表「其他应收款」</b>：由 K1-1「与经审计的财务报表核对」区（应收利息/应收股利/报表数）三行推送；三项全为 0 时不推送（可能由 G2/G3 承载，见下条）。</li>
        <li><b>同步范围</b>：「同步至附注」写入 五、8 的汇总表/账龄/性质/6 张三阶段/变动/转回/核销/前五名/政府补助/转移终止确认/继续涉入共 17 张子表 + 文字段落。</li>
        <li>G2 应收利息 / G3 应收股利明细亦挂在 五、8 章节下，请勿覆盖其已同步数据。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * K1TabDisclosureListed.vue — 附注披露信息（上市公司）
 *
 * 结构对齐源模板 `K1 其他应收款.xlsx` sheet「附注披露信息(上市公司）」10 段
 * （R6 账龄 → R160 继续涉入说明）+ note_template_listed §五、8。
 * spec: k1-other-receivable-disclosure-alignment Sprint 4
 */
import { computed, inject, ref, toRef, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { amountFormatter, amountParser } from '../../composables/wpAmountInput'
import { useK1DisclosureListed } from '../../composables/useK1DisclosureListed'
import { useK1DisclosureTrace } from '../../composables/k1DisclosureTrace'
import { useK1AiGenerate, type K1AiSection } from '../../composables/useK1AiGenerate'
import {
  K1_STAGE2_NONE_TEXT_END,
  K1_STAGE2_NONE_TEXT_PRIOR,
} from '../../composables/k1DisclosureModel'
import K1DisclosureTracePanel from './K1DisclosureTracePanel.vue'
import K1StageEclTable from './K1StageEclTable.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const displayPrefs = useDisplayPrefsStore()
const router = useRouter()

const STAGE2_NONE_TEXT_END = K1_STAGE2_NONE_TEXT_END
const STAGE2_NONE_TEXT_PRIOR = K1_STAGE2_NONE_TEXT_PRIOR
const RECOVERY_METHODS = ['银行转账收回', '现金收回', '票据收回', '抵债资产', '债务重组', '第三方代偿'] as const
const TRANSFER_METHODS = ['应收账款保理', '资产证券化', '债权转让', '以物抵债'] as const

/** 披露表文字段落 ↔ AI section 映射 */
const AI_SECTION_BY_NOTE: Record<string, K1AiSection> = {
  balanceChange: 'disclosure-balance-change',
  eclBasis: 'disclosure-ecl-basis',
  writeoffNote: 'disclosure-writeoff-note',
  transferNote: 'disclosure-transfer-note',
  fundCentralization: 'disclosure-fund-centralization',
}

// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'K1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const disc = useK1DisclosureListed({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, value),
  applicableStandards: () => props.applicableStandards,
})

const trace = useK1DisclosureTrace('listed', toRef(props, 'allResponses'))
const ai = useK1AiGenerate(toRef(props, 'wpId'))
const isReadonly = computed(() => props.isReadonly)
const priorStageCollapse = ref<string[]>([])

const agingPresetLabel = computed(() => {
  const p = disc.agingConfig.preset.value
  if (p === 'THREE_YEAR') return '账龄：三年分段'
  if (p === 'FIVE_YEAR') return '账龄：五年分段'
  return '账龄：自定义'
})

const natureTableData = computed(() => [
  ...disc.natureRows.value,
  { ...disc.natureTotal.value, isTotal: true },
])

const endStageBlocks = computed(() => [
  { stage: 1 as const, title: '期末，处于第一阶段的坏账准备', rateLabel: '未来12个月内的预期信用损失率(%)', rows: disc.stage1Rows.value },
  { stage: 2 as const, title: '期末，处于第二阶段的坏账准备', rateLabel: '整个存续期预期信用损失率（%）', rows: disc.stage2Rows.value },
  { stage: 3 as const, title: '期末，处于第三阶段的坏账准备', rateLabel: '整个存续期预期信用损失率（%）', rows: disc.stage3Rows.value },
])

const priorStageBlocks = computed(() => [
  { stage: 1 as const, title: '上年年末，处于第一阶段的坏账准备', rateLabel: '未来12个月内的预期信用损失率(%)', rows: disc.priorStage1Rows.value },
  { stage: 2 as const, title: '上年年末，处于第二阶段的坏账准备', rateLabel: '整个存续期预期信用损失率（%）', rows: disc.priorStage2Rows.value },
  { stage: 3 as const, title: '上年年末，处于第三阶段的坏账准备', rateLabel: '整个存续期预期信用损失率（%）', rows: disc.priorStage3Rows.value },
])

const reversalTotal = computed(() =>
  disc.reversalRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0),
)

const transferTotals = computed(() => ({
  amount: disc.payload.value.transferRows.reduce((s, r) => s + (Number(r.derecognizedAmount) || 0), 0),
  gainLoss: disc.payload.value.transferRows.reduce((s, r) => s + (Number(r.gainLoss) || 0), 0),
}))

/** ⑩ 继续涉入：资产区 → 资产小计 → 负债区 → 负债小计（对齐源模板 R153-R159） */
const continuedInvolvementTableData = computed(() => {
  const rows = disc.continuedInvolvementRows.value
  const totals = disc.continuedInvolvementTotals.value
  const out: Array<Record<string, any>> = [{ kind: 'header', label: '资产：' }]
  for (const r of rows.filter((x) => x.side === 'asset')) {
    out.push({ kind: 'data', rowId: r.rowId, item: r.item, amount: r.amount })
  }
  out.push({ kind: 'subtotal', label: '资产小计', amount: totals.assets })
  out.push({ kind: 'header', label: '负债：' })
  for (const r of rows.filter((x) => x.side === 'liability')) {
    out.push({ kind: 'data', rowId: r.rowId, item: r.item, amount: r.amount })
  }
  out.push({ kind: 'subtotal', label: '负债小计', amount: totals.liabilities })
  return out
})

const movementTieOutTitle = computed(() => {
  const t = disc.movementTieOut.value
  const parts: string[] = []
  if (Math.abs(t.closingDiff) >= 0.01) parts.push(`T5 期末余额 ${fmt(t.closingTotal)} ≠ 期末三阶段坏账合计（差 ${fmt(t.closingDiff)}）`)
  if (Math.abs(t.openingDiff) >= 0.01) parts.push(`T6 期初余额 ${fmt(t.openingTotal)} ≠ 上年年末三阶段坏账合计（差 ${fmt(t.openingDiff)}）`)
  if (Math.abs(t.writeoffDiff) >= 0.01) parts.push(`T7 本年核销 ${fmt(t.writeOffTotal)} ≠ ⑤ 核销汇总（差 ${fmt(t.writeoffDiff)}）`)
  return parts.join('；')
})

const fundNoteProxy = computed({
  get: () => disc.payload.value.fundCentralizationNote,
  set: (v: string) => disc.updateFundCentralization('note', v),
})

function fmt(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}

function formatRate(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return '—'
  return `${v.toFixed(2)}%`
}

function agingRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'total' || row.kind === 'subtotal') return 'row-total'
  if (row.kind === 'subtotal1y') return 'row-subtotal-1y'
  if (row.kind === 'sub') return 'row-sub'
  if (row.kind === 'provision') return 'row-provision'
  return ''
}

function natureRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'row-total' : ''
}

function movementRowClass({ row }: { row: { key?: string } }) {
  return row.key === 'closing' || row.key === 'opening' ? 'row-total' : ''
}

function ciRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'subtotal') return 'row-total'
  if (row.kind === 'header') return 'row-header'
  return ''
}

async function onAddNature(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入款项性质名称', '新增性质行', {
      confirmButtonText: '新增',
      cancelButtonText: '取消',
      inputPlaceholder: '如：应收暂付款 / 关联方往来 / 政府补助',
      inputValidator: (v: string) => (String(v || '').trim() ? true : '名称不能为空'),
    })
    disc.addNatureRow(String(value).trim())
  } catch {
    /* 用户取消 */
  }
}

async function onAiNote(key: keyof typeof AI_SECTION_BY_NOTE | string): Promise<void> {
  const section = AI_SECTION_BY_NOTE[String(key)]
  if (!section) return
  // fundCentralization 不走通用 notes 键（专属字段 fundCentralizationNote）。
  const existing = key === 'fundCentralization'
    ? disc.payload.value.fundCentralizationNote
    : disc.noteSection(String(key))
  const text = await ai.generateAndConfirm(
    section,
    existing,
    {
      其他应收款期末审定: disc.adjudication.value.receivableEnd,
      坏账准备期末审定: disc.adjudication.value.badDebtEnd,
      期末三阶段坏账合计: disc.endStageProvisionTotal.value,
      上年年末三阶段坏账合计: disc.priorStageProvisionTotal.value,
      本期核销合计: disc.payload.value.writeoffSummaryAmount,
      本期转回合计: reversalTotal.value,
      终止确认合计: transferTotals.value.amount,
      资金集中管理金额: disc.payload.value.fundCentralizationAmount,
    },
    'AI 生成附注披露段落',
  )
  if (!text) return
  if (key === 'fundCentralization') disc.updateFundCentralization('note', text)
  else disc.updateNoteSection(String(key), text)
}

function handleReview(id: string): void {
  openReviewDialog(id)
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes() {
  await disc.syncToNotes()
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => disc.agingRows,
    () => disc.natureRows,
    () => disc.stage1Rows,
    () => disc.stage2Rows,
    () => disc.stage3Rows,
    () => disc.priorStage1Rows,
    () => disc.priorStage2Rows,
    () => disc.priorStage3Rows,
    () => disc.stageMovements,
    () => disc.top5Rows,
    () => disc.reversalRows,
    // 🔴 ⑧⑨⑩ 三块 2026-07-31 起也进 §五、8（原以为附注真源在别处 → 既没进载荷
    //    也没进 watch，改了这三块不会触发自动同步 = 半接入）
    () => disc.govGrantRows,
    () => disc.transferRows,
    () => disc.continuedInvolvementRows,
    () => disc.noteText,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.k1-disclosure-listed { padding: 12px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.objective-alert, .sync-hint { margin-bottom: 12px; }
.tie-alert { margin-bottom: 8px; }
.inline-alert { margin-top: 8px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.disclosure-card { margin-bottom: 12px; }
.card-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; font-size: 14px; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; white-space: nowrap; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.auto-badge { margin-left: 4px; }
.template-tip, .hint-inline { font-size: 12px; color: var(--el-text-color-secondary); }
.template-tip { margin: 8px 0 0; line-height: 1.7; }
.methodology-block {
  margin-top: 10px;
  padding: 8px 12px;
  background: #fffbe6;
  border-left: 3px solid var(--el-color-warning);
  border-radius: 4px;
  font-size: 12px;
  color: #614700;
  line-height: 1.75;
}
.methodology-block p { margin: 0 0 6px; }
.methodology-block p:last-child { margin-bottom: 0; }
.period-label { font-size: 13px; font-weight: 600; margin: 10px 0 6px; color: var(--el-color-primary); }
.stage-head { display: flex; align-items: center; justify-content: space-between; margin: 10px 0 6px; gap: 12px; flex-wrap: wrap; }
.stage-title { font-size: 12px; font-weight: 600; color: var(--el-text-color-regular); }
.note-block { margin-top: 12px; }
.note-block-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.prior-collapse { margin-top: 12px; }
.collapse-title { font-weight: 600; margin-right: 8px; }
.collapse-tag { margin-left: 8px; }
.sub-block-title { font-size: 12px; font-weight: 600; margin: 10px 0 6px; }
.writeoff-summary { margin-bottom: 8px; font-size: 13px; }
.table-total { padding: 6px 10px; font-size: 12px; font-weight: 600; background: #fafafa; text-align: right; }
.fund-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.note-area { margin-top: 8px; }
.sub-label-input { max-width: 200px; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.9; }
:deep(.row-total) { font-weight: 600; background: #fafafa; }
:deep(.row-subtotal-1y) { font-weight: 600; background: #f6f9ff; }
:deep(.row-sub td:first-child .cell) { padding-left: 22px; color: var(--el-text-color-secondary); }
:deep(.row-provision) { color: var(--el-color-warning); }
:deep(.row-header) { color: var(--el-text-color-secondary); background: #fafafa; }
:deep(.el-table td.is-right .cell) { white-space: nowrap; font-variant-numeric: tabular-nums; }
.is-total { font-weight: 600; }
.is-header { color: var(--el-text-color-secondary); font-weight: 600; }
.is-sub { color: var(--el-text-color-secondary); }
</style>
