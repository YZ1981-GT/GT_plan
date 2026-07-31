<template>
  <div class="k1-disclosure-soe" data-testid="k1-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露信息（国企）</h3>
      <div class="head-actions">
        <span class="chip-wrap"><GtIndexChip :value="noteTarget.chipValue" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">八、9 · 其他应收款项</el-tag>
        <el-tag size="small">单位：{{ displayPrefs.unitSuffix }}</el-tag>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="dis.refreshFromSources(false)">
          从源底稿取数
        </el-button>
        <el-button size="small" plain :disabled="isReadonly" @click="dis.refreshFromSources(true)">
          强制覆盖
        </el-button>
        <el-button
          size="small"
          type="success"
          :loading="dis.isSyncing.value"
          :disabled="isReadonly || !projectId"
          @click="syncToDisclosureNotes()"
        >
          同步至附注
        </el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('soe')">↩ 跳转回附注</el-button>
        <el-button size="small" @click="openReviewDialog('K1-disclosure-soe')">💬 复核</el-button>
      </div>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert"
      title="审计目标：按国有企业附注格式披露其他应收款项账龄、计提方法分类、单项/组合计提明细、ECL 三阶段坏账与账面余额变动、转回核销、前五名、转移终止确认及政府补助，与 K1-1/K1-2/K1-3/K1-7/K1-9 勾稽，并回写附注八、9。" />

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①②</span> 先分类：账龄 → 按坏账准备计提方法（单项 / 组合，期末＋期初）</div>
        <div class="guide-step"><span class="step-num">③④</span> 后明细：单项逐户 → 组合（账龄组合 ＋ 其他组合）</div>
        <div class="guide-step"><span class="step-num">⑤</span> 双变动表：坏账准备三阶段 ＋ 账面余额三阶段（国企特有）</div>
        <div class="guide-step"><span class="step-num">⑥⑦⑧</span> 转回（含转回前累计已计提）→ 核销 → 前五名</div>
        <div class="guide-step"><span class="step-num">⑨⑩</span> 表外化：转移终止确认 → 继续涉入资产负债</div>
        <div class="guide-step"><span class="step-num">⑪</span> 特殊性质：涉及政府补助的应收款项</div>
      </div>
    </div>

    <el-alert
      v-if="dis.adjudication.value.receivableEnd"
      type="success"
      :closable="false"
      class="sync-hint"
    >
      已联动 K1-1：其他应收款期末 {{ fmt(dis.adjudication.value.receivableEnd) }}
      · 坏账准备 {{ fmt(dis.adjudication.value.badDebtEnd) }}
      <template v-if="dis.lastSyncHint.value"> · 取数 {{ dis.lastSyncHint.value }}</template>
    </el-alert>

    <K1DisclosureTracePanel
      :rows="trace.traceRows.value"
      :open-count="trace.openCount.value"
      @navigate-sheet="(s) => emit('navigate-sheet', s)"
    />

    <!-- 勾稽告警 T1/T8/T9/T10/T11/T12 -->
    <el-alert
      v-if="!dis.agingTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T1 账龄小计 ${fmt(dis.agingTieOut.value.subtotal)} ≠ K1-1 审定 ${fmt(dis.adjudication.value.receivableEnd)}（差额 ${fmt(dis.agingTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!dis.provisionTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T8 账龄表坏账 ${fmt(dis.provisionTieOut.value.agingProvision)} ≠ ECL 期末合计 ${fmt(dis.provisionTieOut.value.eclClosing)}（差额 ${fmt(dis.provisionTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="!dis.individualTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T9 单项明细合计（余额 ${fmt(dis.individualTieOut.value.detailBalance)} / 坏账 ${fmt(dis.individualTieOut.value.detailProvision)}）≠ 计提方法表单项行（余额 ${fmt(dis.individualTieOut.value.methodBalance)} / 坏账 ${fmt(dis.individualTieOut.value.methodProvision)}）`"
    />
    <el-alert
      v-if="!dis.portfolioSplitTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T10 账龄组合＋其他组合坏账 ${fmt(dis.portfolioSplitTieOut.value.sumProvision)} ≠ 计提方法表组合行坏账 ${fmt(dis.portfolioSplitTieOut.value.methodProvision)}（差额 ${fmt(dis.portfolioSplitTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="dis.balanceStageMovements.value.length && !dis.balanceStageTieOut.value.matched"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T11 账面余额三阶段期末合计 ${fmt(dis.balanceStageTieOut.value.closingTotal)} ≠ K1-1 审定 ${fmt(dis.adjudication.value.receivableEnd)}（差额 ${fmt(dis.balanceStageTieOut.value.diff)}）`"
    />
    <el-alert
      v-if="dis.top5Check.value.exceeded"
      type="warning"
      :closable="false"
      class="tie-out-alert"
      :title="`T12 前五名占比合计 ${dis.top5Check.value.totalPct.toFixed(2)}% 超过 100%，请检查占比分母是否取自账龄小计`"
    />

    <el-collapse v-model="activeSections" class="section-collapse">
      <!-- ① 按账龄 -->
      <el-collapse-item name="aging">
        <template #title>
          <span class="collapse-title">① 按账龄列示其他应收款项</span>
          <el-tag size="small" type="warning" class="collapse-tag">附注子表</el-tag>
        </template>
        <SectionHint :guide="sectionGuide('aging')" />
        <el-table :data="dis.agingRows.value" border size="small" :row-class-name="agingRowClass">
          <el-table-column prop="label" label="账　龄" min-width="160" />
          <el-table-column label="期末数" width="170" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.endAmount"
                size="small"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                style="width: 100%"
                @change="(v: number) => dis.updateAgingRow(row.rowId, 'endAmount', v ?? 0)"
              />
              <span v-else class="amount-cell" :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期初数" width="170" align="right">
            <template #default="{ row }">
              <el-input-number
                v-if="row.editable && !isReadonly"
                :model-value="row.priorAmount"
                size="small"
                :controls="false"
                :precision="2"
                :formatter="amountFormatter"
                :parser="amountParser"
                style="width: 100%"
                @change="(v: number) => dis.updateAgingRow(row.rowId, 'priorAmount', v ?? 0)"
              />
              <span v-else class="amount-cell" :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.priorAmount) }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ② 按计提方法 -->
      <el-collapse-item name="method">
        <template #title>
          <span class="collapse-title">② 按坏账准备计提方法分类披露其他应收款项</span>
        </template>
        <SectionHint :guide="sectionGuide('method')" />
        <template v-for="period in (['end', 'prior'] as const)" :key="period">
          <div class="dual-table-label">{{ period === 'end' ? '期末余额' : '期初余额（续：）' }}</div>
          <el-table :data="dis.methodRows.value" border size="small" class="method-table">
            <el-table-column prop="label" label="类　别" min-width="240" />
            <el-table-column label="账面余额" align="center">
              <el-table-column label="金额" width="160" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="row.editable && !isReadonly"
                    :model-value="period === 'end' ? row.endBalance : row.priorBalance"
                    size="small"
                    :controls="false"
                    :precision="2"
                    :formatter="amountFormatter"
                    :parser="amountParser"
                    style="width: 100%"
                    @change="(v: number) => dis.updateMethodRow(row.rowKey, period === 'end' ? 'endBalance' : 'priorBalance', v ?? 0)"
                  />
                  <span v-else class="amount-cell">{{ fmt(period === 'end' ? row.endBalance : row.priorBalance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="比例(%)" width="110" align="right">
                <template #default="{ row }">
                  <el-tooltip content="公式：本类账面余额 ÷ 合计账面余额" placement="top">
                    <span class="formula-cell">{{ pct(period === 'end' ? row.endBalancePct : row.priorBalancePct) }}</span>
                  </el-tooltip>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="坏账准备" align="center">
              <el-table-column label="金额" width="160" align="right">
                <template #default="{ row }">
                  <el-input-number
                    v-if="row.editable && !isReadonly"
                    :model-value="period === 'end' ? row.endProvision : row.priorProvision"
                    size="small"
                    :controls="false"
                    :precision="2"
                    :formatter="amountFormatter"
                    :parser="amountParser"
                    style="width: 100%"
                    @change="(v: number) => dis.updateMethodRow(row.rowKey, period === 'end' ? 'endProvision' : 'priorProvision', v ?? 0)"
                  />
                  <span v-else class="amount-cell">{{ fmt(period === 'end' ? row.endProvision : row.priorProvision) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="预期信用损失率(%)" width="150" align="right">
                <template #default="{ row }">
                  <el-tooltip content="公式：坏账准备 ÷ 账面余额" placement="top">
                    <span class="formula-cell">{{ pct(period === 'end' ? row.endEclRate : row.priorEclRate) }}</span>
                  </el-tooltip>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="账面价值" width="160" align="right">
              <template #default="{ row }">
                <el-tooltip content="公式：账面余额 − 坏账准备" placement="top">
                  <span class="formula-cell">{{ fmt(period === 'end' ? row.endBookValue : row.priorBookValue) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table>
        </template>
      </el-collapse-item>

      <!-- ③ 单项计提明细 -->
      <el-collapse-item name="individual">
        <template #title><span class="collapse-title">③ 单项计提坏账准备的其他应收款项</span></template>
        <SectionHint :guide="sectionGuide('individual')" />
        <el-empty v-if="!dis.individualDetailRows.value.length" description="无单项计提行（可从 K1-3 取数）" :image-size="48" />
        <el-table v-else :data="dis.individualDetailRows.value" border size="small">
          <el-table-column label="债务人名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.debtorName" size="small"
                @change="(v: string) => dis.updateIndividualRow(row.rowId, 'debtorName', v)" />
              <span v-else>{{ row.debtorName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.balance" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateIndividualRow(row.rowId, 'balance', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.provision" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateIndividualRow(row.rowId, 'provision', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率(%)" width="150" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式：坏账准备 ÷ 账面余额" placement="top">
                <span class="formula-cell">{{ pct(row.eclRate) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="计提理由" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.reason" size="small" type="textarea" :autosize="{ minRows: 1 }"
                @change="(v: string) => dis.updateIndividualRow(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-collapse-item>

      <!-- ④ 组合计提 -->
      <el-collapse-item name="portfolio">
        <template #title><span class="collapse-title">④ 按信用风险特征组合计提坏账准备的其他应收款项</span></template>
        <SectionHint :guide="sectionGuide('portfolioAging')" />
        <div class="sub-block-title">账龄组合</div>
        <el-table :data="dis.portfolioAgingRows.value" border size="small">
          <el-table-column prop="label" label="账　龄" min-width="140" />
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endBalance" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'endBalance', v ?? 0)" />
                <span v-else class="amount-cell" :class="{ 'auto-fill': row.autoFilled }">{{ fmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" width="100" align="right">
              <template #default="{ row }">{{ pct(row.endBalancePct) }}</template>
            </el-table-column>
            <el-table-column label="坏账准备" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="row.editable && !isReadonly" :model-value="row.endProvision" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'endProvision', v ?? 0)" />
                <span v-else class="amount-cell">{{ fmt(row.endProvision) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="账面余额" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="row.editable && !isReadonly" :model-value="row.priorBalance" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'priorBalance', v ?? 0)" />
                <span v-else class="amount-cell">{{ fmt(row.priorBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" width="100" align="right">
              <template #default="{ row }">{{ pct(row.priorBalancePct) }}</template>
            </el-table-column>
            <el-table-column label="坏账准备" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="row.editable && !isReadonly" :model-value="row.priorProvision" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updatePortfolioRow(row.rowId, 'priorProvision', v ?? 0)" />
                <span v-else class="amount-cell">{{ fmt(row.priorProvision) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>

        <div class="sub-block-title-row">
          <span class="sub-block-title">采用余额百分比法或其他组合方法计提坏账准备的其他应收款项（其他组合）</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAddOtherPortfolio">＋ 新增组合</el-button>
        </div>
        <SectionHint :guide="sectionGuide('portfolioOther')" />
        <el-table :data="otherPortfolioTableData" border size="small" :row-class-name="totalRowClass">
          <el-table-column label="组合名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!row.isTotal && !isReadonly" :model-value="row.label" size="small"
                @change="(v: string) => dis.updateOtherPortfolioRow(row.rowId, 'label', v)" />
              <span v-else :class="{ 'is-total': row.isTotal }">{{ row.label || '（未命名）' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.endBalance" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updateOtherPortfolioRow(row.rowId, 'endBalance', v ?? 0)" />
                <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="计提比例(%)" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.endRatePct ?? 0" size="small" :controls="false"
                  :precision="2" :min="0" :max="100" style="width:100%"
                  @change="(v: number) => dis.updateOtherPortfolioRow(row.rowId, 'endRatePct', v ?? 0)" />
                <span v-else>{{ pct(row.endRatePct) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="150" align="right">
              <template #default="{ row }">
                <el-tooltip v-if="!row.isTotal" content="公式：账面余额 × 计提比例" placement="top">
                  <span class="formula-cell">{{ fmt(row.endProvision) }}</span>
                </el-tooltip>
                <span v-else class="amount-cell is-total">{{ fmt(row.endProvision) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="账面余额" width="150" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.priorBalance" size="small" :controls="false"
                  :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                  @change="(v: number) => dis.updateOtherPortfolioRow(row.rowId, 'priorBalance', v ?? 0)" />
                <span v-else class="amount-cell">{{ fmt(row.priorBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="计提比例(%)" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!row.isTotal && !isReadonly" :model-value="row.priorRatePct ?? 0" size="small" :controls="false"
                  :precision="2" :min="0" :max="100" style="width:100%"
                  @change="(v: number) => dis.updateOtherPortfolioRow(row.rowId, 'priorRatePct', v ?? 0)" />
                <span v-else>{{ pct(row.priorRatePct) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="坏账准备" width="150" align="right">
              <template #default="{ row }">
                <span class="amount-cell" :class="{ 'is-total': row.isTotal }">{{ fmt(row.priorProvision) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button v-if="!row.isTotal" size="small" type="danger" link
                @click="dis.removeOtherPortfolioRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无其他组合（如余额百分比法组合），点击「＋ 新增组合」添加</template>
        </el-table>
      </el-collapse-item>

      <!-- ⑤ ECL三阶段 -->
      <el-collapse-item name="ecl">
        <template #title><span class="collapse-title">⑤ 其他应收款项坏账准备计提情况（ECL 三阶段）</span></template>
        <SectionHint :guide="sectionGuide('ecl')" />
        <el-table :data="dis.stageMovements.value" border size="small" :row-class-name="movementRowClass">
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
          <template #empty>暂无数据，请先在 K1-3 维护三阶段转入转出后点击「从源底稿取数」</template>
        </el-table>
        <p class="hint-text">数据来自 K1-3 三阶段转入转出（只读）。</p>
      </el-collapse-item>

      <!-- ⑤b 账面余额三阶段 -->
      <el-collapse-item name="balanceStage">
        <template #title>
          <span class="collapse-title">⑤b 其他应收款项账面余额变动（三阶段）</span>
          <el-tag v-if="dis.balanceStageMovements.value.length" size="small" type="success" class="collapse-tag">K1-7</el-tag>
        </template>
        <SectionHint :guide="sectionGuide('balanceStage')" />
        <el-empty v-if="!dis.balanceStageMovements.value.length" description="K1-7 暂无三阶段划分数据" :image-size="48" />
        <el-table v-else :data="dis.balanceStageMovements.value" border size="small" :row-class-name="movementRowClass">
          <el-table-column prop="label" label="账面余额" min-width="200" />
          <el-table-column v-for="col in BALANCE_STAGE_COLUMNS" :key="col.field" :label="col.label" width="170" align="right">
            <template #header>
              <el-tooltip :content="col.hint" placement="top">
                <span class="header-hint">{{ col.label }}</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <span :class="{ 'sign-abnormal': isSignAbnormal(row.key, col.field, row[col.field]) }">
                {{ fmt(row[col.field]) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="合计" width="150" align="right">
            <template #default="{ row }">{{ fmt(row.stage1 + row.stage2 + row.stage3) }}</template>
          </el-table-column>
        </el-table>
        <p class="hint-text">
          自 K1-7 按户汇总：期初取 K1-2 期初余额按 priorStage 归集；阶段迁移取 priorStage→stage 变动；同阶段差额计入本期新增/收回。
          红色标记表示方向与源模板【正数】/【负数】约定不符。
        </p>

        <div class="note-block">
          <div class="note-block-head">
            <span>说明：对本期发生损失准备变动的账面余额显著变动的情况说明</span>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('balanceChange')">🤖 AI</el-button>
          </div>
          <el-input
            :model-value="dis.noteSection('balanceChange')"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="isReadonly"
            placeholder="说明账面余额较期初的增减金额与幅度、主要成因及对损失准备计提的影响"
            @change="(v: string) => dis.updateNoteSection('balanceChange', v)"
          />
        </div>
        <div class="note-block">
          <div class="note-block-head">
            <span>本期坏账准备计提金额以及评估金融工具的信用风险是否显著增加的采用依据</span>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('eclBasis')">🤖 AI</el-button>
          </div>
          <el-input
            :model-value="dis.noteSection('eclBasis')"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="isReadonly"
            placeholder="三阶段划分的量化/定性标准、预期信用损失率确定依据、本期计提金额与上期计提比例差异原因"
            @change="(v: string) => dis.updateNoteSection('eclBasis', v)"
          />
        </div>
      </el-collapse-item>

      <!-- ⑥ 转回/收回 -->
      <el-collapse-item name="reversal">
        <template #title><span class="collapse-title">⑥ 收回或转回的坏账准备</span></template>
        <SectionHint :guide="sectionGuide('reversal')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">逐笔列示</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addReversalRow()">＋ 新增行</el-button>
        </div>
        <el-table :data="dis.reversalRows.value" border size="small" class="sub-table">
          <el-table-column label="债务人名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.unitName" size="small"
                @change="(v: string) => dis.updateReversalRow(row.rowId, 'unitName', v)" />
              <span v-else>{{ row.unitName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转回或收回金额" width="170" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateReversalRow(row.rowId, 'amount', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转回或收回前累计已计提坏账准备金额" width="220" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.cumulativeProvision ?? 0" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateReversalRow(row.rowId, 'cumulativeProvision', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.cumulativeProvision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转回或收回原因" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.reason" size="small"
                @change="(v: string) => dis.updateReversalRow(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="方式" width="140">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" :model-value="row.method" size="small" clearable filterable allow-create
                placeholder="选择" style="width:100%"
                @change="(v: string) => dis.updateReversalRow(row.rowId, 'method', v ?? '')">
                <el-option v-for="m in RECOVERY_METHODS" :key="m" :label="m" :value="m" />
              </el-select>
              <span v-else>{{ row.method || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="dis.removeReversalRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无转回/收回记录（可在 K1-9 维护后取数）</template>
          <template #append>
            <div class="table-total">
              合计　转回或收回金额：{{ fmt(reversalTotals.amount) }}　·　转回前累计已计提：{{ fmt(reversalTotals.cumulative) }}
            </div>
          </template>
        </el-table>
        <div class="methodology-block">
          （注：本表列报本报告期前已全额计提坏账准备，或计提减值准备的比例较大，但在本期又全额收回或转回，或在本期收回或转回比例较大的其他应收款项。对本期通过重组等方式收回的金额重大的其他应收款项，则应逐笔列报，金额不重大的，可汇总列报。）
        </div>
      </el-collapse-item>

      <!-- ⑦ 核销 -->
      <el-collapse-item name="writeoff">
        <template #title><span class="collapse-title">⑦ 本期实际核销的其他应收款项</span></template>
        <SectionHint :guide="sectionGuide('writeoff')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">合计核销金额：<b class="amount-cell">{{ fmt(dis.payload.value.writeoffSummaryAmount) }}</b></span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addWriteoffRow()">＋ 新增行</el-button>
        </div>
        <el-table :data="dis.writeoffDetailRows.value" border size="small" class="sub-table">
          <el-table-column label="债务人名称" min-width="170">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.unitName" size="small"
                @change="(v: string) => dis.updateWriteoffRow(row.rowId, 'unitName', v)" />
              <span v-else>{{ row.unitName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他应收款项性质" width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.nature" size="small"
                @change="(v: string) => dis.updateWriteoffRow(row.rowId, 'nature', v)" />
              <span v-else>{{ row.nature || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="核销金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.amount" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateWriteoffRow(row.rowId, 'amount', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="核销原因" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.reason" size="small"
                @change="(v: string) => dis.updateWriteoffRow(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="履行的核销程序" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.procedure" size="small"
                @change="(v: string) => dis.updateWriteoffRow(row.rowId, 'procedure', v)" />
              <span v-else>{{ row.procedure || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="是否因关联交易产生" width="160">
            <template #default="{ row }">
              <el-select v-if="!isReadonly" :model-value="row.relatedParty" size="small" clearable placeholder="选择" style="width:100%"
                @change="(v: string) => dis.updateWriteoffRow(row.rowId, 'relatedParty', v ?? '')">
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
              <span v-else>{{ row.relatedParty || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="dis.removeWriteoffRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无核销记录（可在 K1-9 维护后取数）</template>
        </el-table>
        <div class="methodology-block">
          对重要的核销应逐项披露款项性质、核销原因、履行的核销程序及核销金额；因关联交易产生的应单独披露。
        </div>
      </el-collapse-item>

      <!-- ⑧ 前五名 -->
      <el-collapse-item name="top5">
        <template #title><span class="collapse-title">⑧ 按欠款方归集的期末余额前五名的其他应收款项</span></template>
        <SectionHint :guide="sectionGuide('top5')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">前五名明细</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addTop5Row()">＋ 新增行</el-button>
        </div>
        <el-table :data="dis.top5Rows.value" border size="small">
          <el-table-column label="债务人名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.unitName" size="small"
                @change="(v: string) => dis.updateTop5Row(row.rowId, 'unitName', v)" />
              <span v-else :class="{ 'auto-fill': row.autoFilled }">{{ row.unitName || '（未命名）' }}</span>
              <el-tag v-if="row.autoFilled" size="small" type="info" class="auto-badge">K1-2</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="款项性质" width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.nature" size="small"
                @change="(v: string) => dis.updateTop5Row(row.rowId, 'nature', v)" />
              <span v-else>{{ row.nature || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateTop5Row(row.rowId, 'endBalance', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账龄" width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.aging" size="small"
                @change="(v: string) => dis.updateTop5Row(row.rowId, 'aging', v)" />
              <span v-else>{{ row.aging || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="占其他应收款项合计的比例（%）" width="190" align="right">
            <template #default="{ row }">
              <el-tooltip content="公式：本行账面余额 ÷ 账龄表小计" placement="top">
                <span class="formula-cell">{{ pct(row.proportionPct) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="150" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.provision" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateTop5Row(row.rowId, 'provision', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="dis.removeTop5Row(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>暂无数据（可从 K1-2 按期末余额降序取前 5）</template>
        </el-table>
      </el-collapse-item>

      <!-- ⑨ 转移终止确认 -->
      <el-collapse-item name="transfer">
        <template #title><span class="collapse-title">⑨ 由金融资产转移而终止确认的其他应收款项</span></template>
        <SectionHint :guide="sectionGuide('transfer')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">终止确认逐笔列示</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addTransferRow()">＋ 新增行</el-button>
        </div>
        <el-table :data="dis.transferRows.value" border size="small" class="sub-table">
          <el-table-column label="债务人名称" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.item" size="small"
                @change="(v: string) => dis.updateTransferRow(row.rowId, 'item', v)" />
              <span v-else>{{ row.item || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="终止确认金额" width="170" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.derecognizedAmount" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateTransferRow(row.rowId, 'derecognizedAmount', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.derecognizedAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="与终止确认相关的利得或损失" width="220" align="right">
            <template #header>
              <el-tooltip content="损失以「-」填列" placement="top">
                <span class="header-hint">与终止确认相关的利得或损失</span>
              </el-tooltip>
            </template>
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.gainLoss" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateTransferRow(row.rowId, 'gainLoss', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.gainLoss) }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="dis.removeTransferRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>本期不存在由金融资产转移而终止确认的其他应收款项</template>
          <template #append>
            <div class="table-total">
              合计　终止确认金额：{{ fmt(transferTotals.amount) }}　·　利得或损失：{{ fmt(transferTotals.gainLoss) }}
            </div>
          </template>
        </el-table>
      </el-collapse-item>

      <!-- ⑩ 继续涉入 -->
      <el-collapse-item name="continuedInvolvement">
        <template #title>
          <span class="collapse-title">⑩ 其他应收款项转移继续涉入形成的资产、负债的金额</span>
          <el-tag size="small" type="info" class="collapse-tag">如证券化、保理等</el-tag>
        </template>
        <SectionHint :guide="sectionGuide('continuedInvolvement')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">分资产 / 负债列示</span>
          <div class="head-actions">
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addContinuedInvolvementRow('asset')">＋资产行</el-button>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addContinuedInvolvementRow('liability')">＋负债行</el-button>
          </div>
        </div>
        <el-table :data="continuedInvolvementTableData" border size="small" :row-class-name="ciRowClass">
          <el-table-column label="项　目" min-width="260">
            <template #default="{ row }">
              <el-input v-if="row.kind === 'data' && !isReadonly" :model-value="row.item" size="small"
                placeholder="如：因保理继续涉入形成的应收款"
                @change="(v: string) => dis.updateContinuedInvolvementRow(row.rowId, 'item', v)" />
              <span v-else :class="{ 'is-total': row.kind === 'subtotal', 'is-header': row.kind === 'header' }">{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末金额" width="180" align="right">
            <template #default="{ row }">
              <el-input-number v-if="row.kind === 'data' && !isReadonly" :model-value="row.amount" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateContinuedInvolvementRow(row.rowId, 'amount', v ?? 0)" />
              <span v-else-if="row.kind === 'subtotal'" class="amount-cell is-total">{{ fmt(row.amount) }}</span>
              <span v-else>—</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button v-if="row.kind === 'data'" size="small" type="danger" link
                @click="dis.removeContinuedInvolvementRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
        <div class="note-block">
          <div class="note-block-head">
            <span>说明（资产转移方式；未全部终止确认的被转移金融资产与相关负债之间的关系；已终止确认的金融资产继续涉入的性质及相关风险的信息）</span>
            <el-button size="small" type="primary" link :disabled="isReadonly" @click="onAiNote('transferNote')">🤖 AI</el-button>
          </div>
          <el-input
            :model-value="dis.noteSection('transferNote')"
            type="textarea"
            :autosize="{ minRows: 3 }"
            :disabled="isReadonly"
            placeholder="若无此类交易，可填写：本期不存在其他应收款项转移且继续涉入的情形。"
            @change="(v: string) => dis.updateNoteSection('transferNote', v)"
          />
        </div>
      </el-collapse-item>

      <!-- ⑪ 政府补助 -->
      <el-collapse-item name="govGrant">
        <template #title><span class="collapse-title">⑪ 涉及政府补助的应收款项</span></template>
        <SectionHint :guide="sectionGuide('govGrant')" />
        <div class="sub-block-title-row">
          <span class="sub-block-title">逐项列示</span>
          <el-button size="small" type="primary" link :disabled="isReadonly" @click="dis.addGovGrantRow()">＋ 新增行</el-button>
        </div>
        <el-table :data="dis.govGrantRows.value" border size="small">
          <el-table-column label="单位名称（政府补助的发文单位）" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.unitName" size="small"
                @change="(v: string) => dis.updateGovGrantRow(row.rowId, 'unitName', v)" />
              <span v-else>{{ row.unitName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="政府补助项目名称" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.projectName" size="small"
                @change="(v: string) => dis.updateGovGrantRow(row.rowId, 'projectName', v)" />
              <span v-else>{{ row.projectName || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末余额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small" :controls="false"
                :precision="2" :formatter="amountFormatter" :parser="amountParser" style="width:100%"
                @change="(v: number) => dis.updateGovGrantRow(row.rowId, 'endBalance', v ?? 0)" />
              <span v-else class="amount-cell">{{ fmt(row.endBalance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末账龄" width="120">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.aging" size="small"
                @change="(v: string) => dis.updateGovGrantRow(row.rowId, 'aging', v)" />
              <span v-else>{{ row.aging || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预计收取的时间、金额及依据" min-width="220">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" :model-value="row.expectedCollection" size="small"
                @change="(v: string) => dis.updateGovGrantRow(row.rowId, 'expectedCollection', v)" />
              <span v-else>{{ row.expectedCollection || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="56" align="center">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="dis.removeGovGrantRow(row.rowId)">删除</el-button>
            </template>
          </el-table-column>
          <template #empty>K1-2 无「政府补助」性质明细，可手工新增</template>
        </el-table>
        <div class="methodology-block">（注：涉及重要的政府补助的应收款项应披露相关信息。）</div>
      </el-collapse-item>
    </el-collapse>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="card-title-row">
          <span class="card-title">审计说明（同步至附注文字）</span>
          <el-button size="small" @click="openReviewDialog('K1-disclosure-soe-note')">💬 复核</el-button>
        </div>
      </template>
      <el-input
        v-model="dis.noteText.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="说明账龄变动、阶段迁移、核销原因及与 K1-8 测算衔接等"
        @change="dis.persistNote()"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（源模板 8 段对照 · 非打印）</summary>
      <ul>
        <li><b>① 账龄</b>：期末数/期初数两列 + 小计 + 减：坏账准备 + 合计；国企版无 1 年以内月度细分（上市版才有）。</li>
        <li><b>② 按计提方法</b>：期末余额表 + 续：期初余额表；比例(%) = 本类账面余额 ÷ 合计；预期信用损失率(%) = 坏账准备 ÷ 账面余额。</li>
        <li><b>③ 单项计提明细</b>：从 K1-3 单项评估子行取数，逐户给出计提理由；合计须与 ② 单项行勾稽（T9）。</li>
        <li><b>④ 组合计提</b>：账龄组合（结构占比派生）+ 其他组合（人工设定计提比例，坏账准备派生）；两表坏账合计须与 ② 组合行勾稽（T10）。</li>
        <li><b>⑤ 双变动表</b>：坏账准备三阶段来自 K1-3；账面余额三阶段来自 K1-7 + K1-2，为国企版特有（上市版无）。</li>
        <li><b>⑥ 转回/收回</b>：「转回或收回前累计已计提坏账准备金额」为国企版专有列，自 K1-9 的 accumProvision 取数。</li>
        <li><b>⑦ 核销</b>：合计由明细自动汇总；关联交易产生的须单独披露。</li>
        <li><b>⑧ 前五名</b>：占比分母取账龄表小计（非前五名合计），占比合计超 100% 会告警。</li>
        <li><b>⑨⑩ 转移 / 继续涉入</b>：国企源模板转移表<b>无</b>「转移方式」列（上市版才有）；损失以「-」填列。</li>
        <li><b>⑪ 政府补助</b>：国企附注为文字 + 表，逐项披露发文单位、项目、期末余额、期末账龄与预计收取依据。</li>
        <li><b>资金集中管理</b>：国企附注独立成 §八、8「应收资金集中管理款」章节，不在本表内披露。</li>
        <li><b>同步范围</b>：「同步至附注」写入 八、9 的 14 张子表 + 文字段落。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabDisclosureSoe.vue — 附注披露信息（国企）
 *
 * 结构对齐源模板 `K1 其他应收款.xlsx` sheet「附注披露信息（国企）」8 段
 * （R6 账龄 → R130 政府补助）+ note_template_soe §八、9。
 * spec: k1-other-receivable-disclosure-alignment Sprint 5
 */
import { ref, computed, inject, toRef, defineComponent, h, onBeforeUnmount, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import GtIndexChip from '../../GtIndexChip.vue'
import { amountFormatter, amountParser } from '../../composables/wpAmountInput'
import { useDisclosureAutoSync } from '../../composables/useDisclosureAutoSync'
import { useK1DisclosureSoe } from '../../composables/useK1DisclosureSoe'
import { useK1DisclosureTrace } from '../../composables/k1DisclosureTrace'
import { useK1AiGenerate, type K1AiSection } from '../../composables/useK1AiGenerate'
import K1DisclosureTracePanel from './K1DisclosureTracePanel.vue'
import { K1_SOE_SECTION_GUIDES } from '../../composables/k1NoteSectionMap'
import type { K1AgingDisclosureRow } from '../../composables/k1DisclosureModel'

const SectionHint = defineComponent({
  props: { guide: { type: Object, default: null } },
  setup(props) {
    return () => {
      const g = props.guide as { structure?: string; source?: string; noteTarget?: string } | null
      if (!g) return null
      return h('el-alert', {
        type: 'info',
        closable: false,
        class: 'section-hint',
        title: `结构：${g.structure}`,
        description: `取数：${g.source} → ${g.noteTarget}`,
      })
    }
  },
})

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const allResponsesRef = computed(() => props.allResponses)
const displayPrefs = useDisplayPrefsStore()
const router = useRouter()
const isReadonly = computed(() => props.isReadonly)

const RECOVERY_METHODS = ['银行转账收回', '现金收回', '票据收回', '抵债资产', '债务重组', '第三方代偿'] as const

/** 源模板 R80-R83 的【正数】/【负数】方向约定 */
const BALANCE_STAGE_COLUMNS = [
  { field: 'stage1' as const, label: '第一阶段', hint: '未来12个月预期信用损失。转入第二/三阶段为【负数】，转回第一阶段为【正数】' },
  { field: 'stage2' as const, label: '第二阶段', hint: '整个存续期预期信用损失（未发生信用减值）。转入第二阶段为【正数】，转入第三阶段/转回第一阶段为【负数】' },
  { field: 'stage3' as const, label: '第三阶段', hint: '整个存续期预期信用损失（已发生信用减值）。转入第三阶段为【正数】，转回第一/二阶段为【负数】' },
]

/** 方向约定：key → 各阶段应有符号（1 正 / -1 负 / 0 不校验） */
const SIGN_RULES: Record<string, Record<'stage1' | 'stage2' | 'stage3', number>> = {
  's1-s2': { stage1: -1, stage2: 1, stage3: 0 },
  's1-s3': { stage1: -1, stage2: -1, stage3: 1 },
  's2-s3': { stage1: 0, stage2: -1, stage3: 1 },
  's2-s1': { stage1: 1, stage2: -1, stage3: 0 },
  's3-s1': { stage1: 1, stage2: 0, stage3: -1 },
  's3-s2': { stage1: 0, stage2: 1, stage3: -1 },
}

const AI_SECTION_BY_NOTE: Record<string, K1AiSection> = {
  balanceChange: 'disclosure-balance-change',
  eclBasis: 'disclosure-ecl-basis',
  transferNote: 'disclosure-transfer-note',
}

// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'K1', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}

const activeSections = ref([
  'aging', 'method', 'portfolio', 'ecl', 'balanceStage', 'reversal', 'top5',
])

const dis = useK1DisclosureSoe({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef,
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId, value) => emit('save', itemId, { remark: typeof value === 'string' ? value : JSON.stringify(value) }),
})

const trace = useK1DisclosureTrace('soe', allResponsesRef)
const ai = useK1AiGenerate(toRef(props, 'wpId'))
const noteTarget = dis.noteTarget

const otherPortfolioTableData = computed(() => {
  const rows = dis.otherPortfolioRows.value
  if (!rows.length) return []
  const sum = (pick: (r: typeof rows[number]) => number) => rows.reduce((s, r) => s + (pick(r) || 0), 0)
  return [
    ...rows,
    {
      rowId: '__total__',
      label: '合　计',
      isTotal: true,
      endBalance: sum((r) => r.endBalance),
      endRatePct: null,
      endProvision: sum((r) => r.endProvision),
      priorBalance: sum((r) => r.priorBalance),
      priorRatePct: null,
      priorProvision: sum((r) => r.priorProvision),
    },
  ]
})

const reversalTotals = computed(() => ({
  amount: dis.reversalRows.value.reduce((s, r) => s + (Number(r.amount) || 0), 0),
  cumulative: dis.reversalRows.value.reduce((s, r) => s + (Number(r.cumulativeProvision) || 0), 0),
}))

const transferTotals = computed(() => ({
  amount: dis.transferRows.value.reduce((s, r) => s + (Number(r.derecognizedAmount) || 0), 0),
  gainLoss: dis.transferRows.value.reduce((s, r) => s + (Number(r.gainLoss) || 0), 0),
}))

/** ⑩ 继续涉入：资产区 → 资产小计 → 负债区 → 负债小计（对齐源模板 R117-R123） */
const continuedInvolvementTableData = computed(() => {
  const rows = dis.continuedInvolvementRows.value
  const totals = dis.continuedInvolvementTotals.value
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

function sectionGuide(id: string) {
  return K1_SOE_SECTION_GUIDES.find((g) => g.id === id)
}

function fmt(v: number | null | undefined): string {
  return displayPrefs.fmtAmount(v)
}

function pct(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v)) return '—'
  return `${v.toFixed(2)}%`
}

function isSignAbnormal(rowKey: string, field: 'stage1' | 'stage2' | 'stage3', value: number): boolean {
  const rule = SIGN_RULES[rowKey]?.[field]
  if (!rule || !value) return false
  return Math.sign(value) !== rule
}

function agingRowClass({ row }: { row: K1AgingDisclosureRow }) {
  if (row.kind === 'total' || row.kind === 'subtotal') return 'is-total-row'
  if (row.kind === 'provision') return 'is-provision-row'
  return ''
}

function totalRowClass({ row }: { row: { isTotal?: boolean } }) {
  return row.isTotal ? 'is-total-row' : ''
}

function movementRowClass({ row }: { row: { key?: string } }) {
  return row.key === 'closing' || row.key === 'opening' ? 'is-total-row' : ''
}

function ciRowClass({ row }: { row: { kind?: string } }) {
  if (row.kind === 'subtotal') return 'is-total-row'
  if (row.kind === 'header') return 'is-header-row'
  return ''
}

async function onAddOtherPortfolio(): Promise<void> {
  try {
    const { value } = await ElMessageBox.prompt('请输入组合名称', '新增其他组合', {
      confirmButtonText: '新增',
      cancelButtonText: '取消',
      inputPlaceholder: '如：余额百分比法组合 / 押金保证金组合',
      inputValidator: (v: string) => (String(v || '').trim() ? true : '组合名称不能为空'),
    })
    dis.addOtherPortfolioRow(String(value).trim())
  } catch {
    /* 用户取消 */
  }
}

async function onAiNote(key: string): Promise<void> {
  const section = AI_SECTION_BY_NOTE[key]
  if (!section) return
  const text = await ai.generateAndConfirm(
    section,
    dis.noteSection(key),
    {
      其他应收款期末审定: dis.adjudication.value.receivableEnd,
      坏账准备期末审定: dis.adjudication.value.badDebtEnd,
      ECL期末合计: dis.provisionTieOut.value.eclClosing,
      本期核销合计: dis.payload.value.writeoffSummaryAmount,
      本期转回合计: reversalTotals.value.amount,
      终止确认合计: transferTotals.value.amount,
    },
    'AI 生成附注披露段落',
  )
  if (text) dis.updateNoteSection(key, text)
}

const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })

async function syncToDisclosureNotes() {
  await dis.syncToNotes()
}

// [auto-sync] 监听实际数据（历史实现是 syncToDisclosureNotes 里调度自己 → 800ms 周期无限 POST，
// 且让 disclosureAutoSyncCoverage 守卫误判为「已接自动同步」= 假接入）。
// 🔴 不加 `_xxxMounted` 一次性防护：Vue watch 默认 immediate:false，挂载本身不触发；
//    该防护会吞掉「切走再切回后的第一次编辑」（平台铁律）。
watch(
  [
    () => dis.agingRows,
    () => dis.methodRows,
    () => dis.individualDetailRows,
    () => dis.portfolioAgingRows,
    () => dis.otherPortfolioRows,
    () => dis.continuedInvolvementRows,
    () => dis.stageMovements,
    () => dis.balanceStageMovements,
    () => dis.top5Rows,
    () => dis.reversalRows,
    () => dis.writeoffDetailRows,
    () => dis.govGrantRows,
    () => dis.transferRows,
    () => dis.noteText,
  ],
  () => autoSync.scheduleAutoSync(syncToDisclosureNotes),
  { deep: true },
)

onBeforeUnmount(() => autoSync.cancelPending())
</script>

<style scoped>
.k1-disclosure-soe { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; flex-wrap: wrap; gap: 8px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; }
.objective-alert, .sync-hint, .tie-out-alert { margin-bottom: 8px; }
.guide-area { background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%); border-radius: 8px; padding: 12px 16px; margin-bottom: 12px; }
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.section-collapse { margin-bottom: 12px; }
.collapse-title { font-weight: 600; margin-right: 8px; }
.collapse-tag { margin-left: 8px; }
.section-hint { margin-bottom: 8px; }
.dual-table-label { font-size: 12px; font-weight: 600; margin: 8px 0 4px; color: var(--el-text-color-secondary); }
.method-table { margin-bottom: 10px; }
.sub-block-title { font-size: 12px; font-weight: 600; }
.sub-block-title-row { display: flex; align-items: center; justify-content: space-between; margin: 12px 0 6px; gap: 8px; flex-wrap: wrap; }
.sub-table { margin-bottom: 8px; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); margin: 6px 0 0; line-height: 1.7; }
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
.note-block { margin-top: 12px; }
.note-block-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; font-size: 12px; font-weight: 600; margin-bottom: 4px; }
.table-total { padding: 6px 10px; font-size: 12px; font-weight: 600; background: #fafafa; text-align: right; }
.note-card { margin-top: 12px; }
.card-title-row { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.card-title { font-weight: 600; }
.auto-fill { color: var(--el-color-primary); }
.auto-badge { margin-left: 4px; }
.amount-cell, .formula-cell { font-variant-numeric: tabular-nums; white-space: nowrap; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.header-hint { border-bottom: 1px dotted var(--el-border-color); cursor: help; }
.sign-abnormal { color: var(--el-color-danger); font-weight: 600; }
.is-total { font-weight: 600; }
.is-header { color: var(--el-text-color-secondary); font-weight: 600; }
:deep(.is-total-row) { font-weight: 600; background: #f5f7fa; }
:deep(.is-header-row) { color: var(--el-text-color-secondary); background: #fafafa; }
:deep(.is-provision-row) { color: var(--el-color-warning); }
:deep(.el-table td.is-right .cell) { white-space: nowrap; font-variant-numeric: tabular-nums; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.9; }
</style>
