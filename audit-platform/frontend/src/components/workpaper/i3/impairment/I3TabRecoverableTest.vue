<template>
  <div class="i3-tab-recoverable-test">
    <div class="guidance-block">
      <div class="guidance-grid">
        <div class="guidance-step"><span class="step-num">①</span><span>从 I3-6 选择资产组(CGU)，填写公允净额或勾选仅测使用价值</span></div>
        <div class="guidance-step"><span class="step-num">②</span><span>录入税前净现金流（一般≤5年）及永续增长率，对照行业/市场基准</span></div>
        <div class="guidance-step"><span class="step-num">③</span><span>按 CAPM 填 Rf/β/Rm 与 D/E/Kd，系统算 Ke→WACC税后→税前折现率</span></div>
        <div class="guidance-step"><span class="step-num">④</span><span>确认可收回金额=MAX(公允净额,DCF)，回写 I3-6 并做敏感性复核</span></div>
      </div>
    </div>

    <div class="methodology-block">
      <p>
        <strong>CAS8：</strong>可收回金额 = MAX(公允价值减处置费用后的净额, 预计未来现金流量现值)。
        折现率应为反映货币时间价值与资产特定风险的<strong>税前利率</strong>；现金流与折现率口径须一致。
        公允取值优先：销售协议 → 活跃市场 → 估计；处置费用含法律/税费/搬运等直接费用。
        WACC(税后)=(D×Kd×(1−t)+E×Ke)/(D+E)；Ke=Rf+β×(Rm−Rf)；税前折现率≈WACC税后/(1−t)。
      </p>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：验证资产组(CGU)可收回金额按 CAS8 以公允净额与使用价值孰高确定；复核公允层次、处置费用、现金流假设及 WACC/CAPM；结果回传 I3-6（商誉减值不可转回）。"
    />

    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span class="section-title">I3-7 可收回金额测试（对齐致同 Excel）</span>
          <div class="section-header-actions">
            <GtIndexChip value="wp:I3-7" :context-project-id="projectId" />
            <el-select
              v-model="activeCguIndex"
              size="small"
              placeholder="选择资产组(CGU)"
              style="width: 220px"
            >
              <el-option
                v-for="(cgu, idx) in cguList"
                :key="cgu.rowId || idx"
                :label="cgu.cguName"
                :value="idx"
              />
            </el-select>
            <el-button
              v-if="!isReadonly && activeCgu"
              size="small"
              type="warning"
              @click="handleLinkToI36"
            >
              回写 I3-6
            </el-button>
            <I3SheetImportExport
              v-if="!isReadonly"
              sheet="I3-7"
              :wp-id="wpId"
              :project-id="projectId"
            />
            <el-button size="small" circle @click="openReview('I3-7')">💬</el-button>
          </div>
        </div>
      </template>

      <div class="tab-toolbar">
        <div class="toolbar-left">
          <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I3-6')">← I3-6</el-tag>
          <el-tag size="small" type="info">共 {{ cguList.length }} 个资产组</el-tag>
          <el-tag v-if="activeCgu" size="small">账面(含商誉) {{ fmtAmt(activeCgu.cguBookValue) }}</el-tag>
        </div>
        <div class="toolbar-right">
          <GtIndexChip value="wp:I3-6" :context-project-id="projectId" />
        </div>
      </div>

      <!-- 多 CGU 测算状态 -->
      <div v-if="cguStatusList.length" class="cgu-status-bar" data-testid="i3-7-cgu-status">
        <span
          v-for="(s, idx) in cguStatusList"
          :key="s.rowId"
          class="cgu-status-chip"
          :class="{ active: idx === activeCguIndex, done: s.tested, pending: !s.tested }"
          @click="activeCguIndex = idx"
        >
          {{ s.cguName }}
          <el-tag size="small" :type="s.tested ? 'success' : 'info'" effect="plain">
            {{ s.tested ? fmtAmt(s.recoverableAmount) : '未测' }}
          </el-tag>
        </span>
      </div>

      <el-empty
        v-if="!activeCgu"
        description="请先在 I3-6 商誉减值测试中添加资产组(CGU)"
        :image-size="60"
      />

      <template v-else>
        <!-- 一、公允净额 -->
        <el-card shadow="never" class="inner-card">
          <template #header>
            <div class="section-header">
              <span>一、公允价值减去处置费用后的净额</span>
              <el-checkbox
                v-if="!isReadonly"
                v-model="preferValueInUse"
                @change="persistState"
              >
                仅测使用价值（无可靠公允）
              </el-checkbox>
              <el-tag v-else-if="preferValueInUse" size="small" type="warning">仅使用价值</el-tag>
            </div>
          </template>

          <el-alert
            v-if="preferValueInUse"
            type="info"
            :closable="false"
            show-icon
            class="mb-12"
            title="无法可靠估计公允净额时，可收回金额取预计未来现金流量现值。请说明理由。"
          />
          <el-form v-if="preferValueInUse" label-width="140px" size="small" class="mb-12">
            <el-form-item label="仅使用价值理由" required>
              <el-input
                v-if="!isReadonly"
                v-model="preferValueInUseReason"
                type="textarea"
                :autosize="{ minRows: 2 }"
                placeholder="例如：资产组无销售协议/活跃市场报价，无法合理估计公允价值…"
                @blur="persistState"
              />
              <span v-else>{{ preferValueInUseReason || '—' }}</span>
            </el-form-item>
          </el-form>

          <template v-if="!preferValueInUse">
            <h4 class="sub-title">（1）公允价值确定（优先：销售协议 → 活跃市场 → 估计）</h4>
            <el-table :data="fvPriceRows" border size="small" class="mb-12">
              <el-table-column prop="label" label="确定方法" width="160" />
              <el-table-column label="金额" width="160" align="right">
                <template #default="{ row: pr }">
                  <el-input-number
                    v-if="!isReadonly"
                    :model-value="pr.amount"
                    :controls="false"
                    size="small"
                    @change="pr.onAmount"
                  />
                  <span v-else class="amt-cell">{{ fmtAmt(pr.amount) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="说明" min-width="200">
                <template #default="{ row: pr }">
                  <el-input
                    v-if="!isReadonly"
                    :model-value="pr.note"
                    size="small"
                    placeholder="取值依据..."
                    @change="pr.onNote"
                  />
                  <span v-else>{{ pr.note || '-' }}</span>
                </template>
              </el-table-column>
              <el-table-column label="选用" width="80" align="center">
                <template #default="{ row: pr }">
                  <el-tag v-if="pr.selected" type="success" size="small">选用</el-tag>
                </template>
              </el-table-column>
            </el-table>

            <h4 class="sub-title">（2）处置费用（直接归属于处置）</h4>
            <el-form label-width="100px" size="small">
              <el-row :gutter="12">
                <el-col v-for="item in disposalFields" :key="item.key" :span="8">
                  <el-form-item :label="item.label">
                    <el-input-number
                      :model-value="(fvDisposal as any)[item.key]"
                      :controls="false"
                      :disabled="isReadonly"
                      @change="(v: number | undefined) => updateFvField(item.key, v ?? 0)"
                    />
                  </el-form-item>
                </el-col>
                <el-col :span="8">
                  <el-form-item label="处置费用合计">
                    <span class="formula-cell">{{ fmtAmt(calcResult.disposalTotal) }}</span>
                  </el-form-item>
                </el-col>
              </el-row>
            </el-form>

            <div class="result-bar">
              <span>公允价值（{{ calcResult.fairValueSource }}）</span>
              <b class="amt-cell">{{ fmtAmt(calcResult.fairValueLessDisposal + calcResult.disposalTotal) }}</b>
              <span>− 处置费用</span>
              <b class="amt-cell">{{ fmtAmt(calcResult.disposalTotal) }}</b>
              <span>= 公允净额</span>
              <b class="highlight">{{ fmtAmt(calcResult.fairValueLessDisposal) }}</b>
            </div>

            <el-input
              v-if="!isReadonly"
              v-model="fvDisposal.auditNote"
              type="textarea"
              :autosize="{ minRows: 2 }"
              placeholder="审计说明：公允价值及处置费用取值依据…"
              class="mt-8"
              @blur="persistState"
            />
          </template>
        </el-card>

        <!-- 二、DCF + WACC -->
        <el-card shadow="never" class="inner-card">
          <template #header>
            <div class="section-header"><span>二、预计未来现金流量的现值（使用价值）</span></div>
          </template>

          <h4 class="sub-title">（1）未来现金流量预测（一般不超过5年；税前净现金流）</h4>
          <el-form :inline="true" size="small" class="mb-8">
            <el-form-item label="永续增长率 g%">
              <el-input-number
                v-if="!isReadonly"
                :model-value="growthRatePct"
                :step="0.1"
                :precision="2"
                :min="-10"
                :max="50"
                size="small"
                @change="(v: number | undefined) => { growthRate = (v ?? 0) / 100; persistState() }"
              />
              <span v-else>{{ growthRatePct.toFixed(2) }}%</span>
            </el-form-item>
            <el-form-item label="行业长期平均%">
              <el-input-number
                v-if="!isReadonly"
                :model-value="growthBenchmarks.industryGrowthRate * 100"
                :step="0.1"
                :precision="2"
                size="small"
                @change="(v: number | undefined) => { growthBenchmarks.industryGrowthRate = (v ?? 0) / 100; persistState() }"
              />
              <span v-else>{{ (growthBenchmarks.industryGrowthRate * 100).toFixed(2) }}%</span>
            </el-form-item>
            <el-form-item label="市场长期平均%">
              <el-input-number
                v-if="!isReadonly"
                :model-value="growthBenchmarks.marketGrowthRate * 100"
                :step="0.1"
                :precision="2"
                size="small"
                @change="(v: number | undefined) => { growthBenchmarks.marketGrowthRate = (v ?? 0) / 100; persistState() }"
              />
              <span v-else>{{ (growthBenchmarks.marketGrowthRate * 100).toFixed(2) }}%</span>
            </el-form-item>
            <el-form-item label="国家/地区长期平均%">
              <el-input-number
                v-if="!isReadonly"
                :model-value="growthBenchmarks.countryGrowthRate * 100"
                :step="0.1"
                :precision="2"
                size="small"
                @change="(v: number | undefined) => { growthBenchmarks.countryGrowthRate = (v ?? 0) / 100; persistState() }"
              />
              <span v-else>{{ (growthBenchmarks.countryGrowthRate * 100).toFixed(2) }}%</span>
            </el-form-item>
            <el-form-item label="增长率依据">
              <el-input
                v-if="!isReadonly"
                v-model="growthBenchmarks.growthRateBasis"
                size="small"
                style="width: 240px"
                placeholder="应≤行业/市场长期增长率；常为0或负"
                @blur="persistState"
              />
              <span v-else>{{ growthBenchmarks.growthRateBasis || '-' }}</span>
            </el-form-item>
          </el-form>

          <el-alert
            v-for="(w, wi) in growthWarnings"
            :key="`g-${wi}`"
            type="warning"
            :closable="false"
            show-icon
            class="mb-8"
            :title="w"
          />

          <el-table :data="cashFlowTableData" border size="small" class="mb-12">
            <el-table-column prop="label" label="年度" width="100" align="center" />
            <el-table-column label="预测净现金流(税前)" min-width="150" align="right">
              <template #default="{ row: cfRow }">
                <el-input-number
                  v-if="!isReadonly"
                  :model-value="cfRow.cashFlow"
                  :controls="false"
                  size="small"
                  class="amt-input"
                  @change="(v: number | undefined) => updateCashFlow(cfRow.yearIndex, v ?? 0)"
                />
                <span v-else class="amt-cell">{{ fmtAmt(cfRow.cashFlow) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="折现系数" width="110" align="right">
              <template #header>
                <span class="formula-header" title="= 1/(1+r)^t">折现系数</span>
              </template>
              <template #default="{ row: cfRow }">
                <span class="formula-cell">{{ cfRow.discountFactor?.toFixed(4) ?? '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="现值" min-width="130" align="right">
              <template #header>
                <span class="formula-header" title="= CF × 折现系数">现值</span>
              </template>
              <template #default="{ row: cfRow }">
                <span class="formula-cell">{{ fmtAmt(cfRow.discountedCF) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <p class="hint-text">注：预测期一般不超过5年；超过5年须有充分证据。以后年度按永续增长模型折现。</p>

          <h4 class="sub-title">（2）折现率 / 加权平均资金成本（WACC · CAPM）</h4>
          <el-form label-width="130px" size="small">
            <el-row :gutter="12">
              <el-col :span="8">
                <el-form-item label="所得税率 t%">
                  <el-input-number
                    v-model="waccParams.taxRate"
                    :controls="false"
                    :min="0"
                    :max="100"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="付息负债 D">
                  <el-input-number
                    v-model="waccParams.totalDebt"
                    :controls="false"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="权益资本 E">
                  <el-input-number
                    v-model="waccParams.totalEquity"
                    :controls="false"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="债务成本 Kd%">
                  <el-input-number
                    v-model="waccParams.costOfDebt"
                    :controls="false"
                    :precision="2"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="无风险利率 Rf%">
                  <el-input-number
                    v-model="waccParams.riskFreeRate"
                    :controls="false"
                    :precision="2"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="β系数">
                  <el-input-number
                    v-model="waccParams.beta"
                    :controls="false"
                    :precision="3"
                    :step="0.1"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="市场回报 Rm%">
                  <el-input-number
                    v-model="waccParams.marketReturn"
                    :controls="false"
                    :precision="2"
                    :disabled="isReadonly"
                    @change="persistState"
                  />
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="权益成本 Ke%">
                  <span class="formula-cell" title="Ke = Rf + β×(Rm−Rf)">{{ (calcResult.costOfEquity || 0).toFixed(2) }}%</span>
                </el-form-item>
              </el-col>
              <el-col :span="8">
                <el-form-item label="折现口径">
                  <el-radio-group
                    v-model="usePreTaxRate"
                    :disabled="isReadonly"
                    size="small"
                    @change="persistState"
                  >
                    <el-radio-button :value="true">税前(CAS8)</el-radio-button>
                    <el-radio-button :value="false">税后</el-radio-button>
                  </el-radio-group>
                </el-form-item>
              </el-col>
            </el-row>
          </el-form>

          <div class="wacc-result-bar">
            <span title="WACC税后 = (D×Kd×(1−t)+E×Ke)/(D+E)">WACC(税后)</span>
            <b>{{ (calcResult.waccAfterTax || 0).toFixed(2) }}%</b>
            <span title="税前折现率 ≈ WACC税后/(1−t)">折现率(税前)</span>
            <b>{{ (calcResult.preTaxDiscountRate || 0).toFixed(2) }}%</b>
            <span>实际折现率</span>
            <b class="highlight">{{ ((calcResult.effectiveDiscountRate || 0) * 100).toFixed(2) }}%</b>
            <el-tag v-if="calcResult.rateInvalid" type="danger" size="small">折现率≤增长率，终值无效</el-tag>
            <el-tag v-if="!(calcResult.waccAfterTax > 0)" type="warning" size="small">未填 D/E，使用手工折现率</el-tag>
          </div>

          <el-alert
            v-for="(w, wi) in waccWarnings"
            :key="`w-${wi}`"
            type="warning"
            :closable="false"
            show-icon
            class="mt-8"
            :title="w"
          />

          <el-form v-if="!(calcResult.waccAfterTax > 0)" :inline="true" size="small" class="mt-8">
            <el-form-item label="手工折现率">
              <el-input-number
                v-if="!isReadonly"
                v-model="manualDiscountRate"
                :step="0.005"
                :precision="4"
                :min="0.001"
                :max="1"
                size="small"
                @change="persistState"
              />
              <span v-else>{{ (manualDiscountRate * 100).toFixed(2) }}%</span>
            </el-form-item>
          </el-form>

          <h4 class="sub-title">（3）现值汇总</h4>
          <el-descriptions :column="4" border size="small">
            <el-descriptions-item label="预测期现值合计">
              <span class="formula-cell">{{ fmtAmt(calcResult.pvForecast) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="终值（未折现）">
              <span class="formula-cell" title="TV = CFn×(1+g)/(r−g)">{{ fmtAmt(calcResult.terminalValue) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="终值现值">
              <span class="formula-cell">{{ fmtAmt(calcResult.discountedTerminalValue) }}</span>
            </el-descriptions-item>
            <el-descriptions-item label="使用价值(DCF)">
              <b class="highlight">{{ fmtAmt(calcResult.valueInUse) }}</b>
            </el-descriptions-item>
          </el-descriptions>
        </el-card>

        <!-- 三、可收回金额 -->
        <el-card shadow="never" class="inner-card recoverable-card">
          <template #header>
            <div class="section-header"><span>三、可收回金额 = MAX(公允净额, 使用价值)</span></div>
          </template>
          <div class="final-recoverable">
            <div class="cmp-item">
              <div class="cmp-label">公允净额</div>
              <div class="cmp-value">{{ fmtAmt(displayFairValueNet) }}</div>
            </div>
            <div class="cmp-vs">vs</div>
            <div class="cmp-item">
              <div class="cmp-label">使用价值(DCF)</div>
              <div class="cmp-value">{{ fmtAmt(calcResult.valueInUse) }}</div>
            </div>
            <div class="cmp-vs">→</div>
            <div class="cmp-item highlight-box">
              <div class="cmp-label">{{ preferValueInUse ? '可收回金额（仅使用价值）' : '可收回金额（取较高者）' }}</div>
              <div class="cmp-value highlight">{{ fmtAmt(finalRecoverableAmount) }}</div>
              <el-tag size="small" type="primary">{{ recoverableSource }}</el-tag>
            </div>
          </div>
          <div class="impairment-hint" :class="{ 'has-impairment': impliedImpairment > 0 }">
            <span>资产组账面(含商誉) {{ fmtAmt(activeCgu.cguBookValue) }}</span>
            <span>− 可收回金额 {{ fmtAmt(finalRecoverableAmount) }}</span>
            <span>= 应计提减值</span>
            <b>{{ fmtAmt(impliedImpairment) }}</b>
            <el-tag v-if="impliedImpairment > 0" type="danger" size="small">存在减值 → I3-6</el-tag>
            <el-tag v-else type="success" size="small">无需减值</el-tag>
            <el-tag type="warning" size="small">商誉减值不得转回</el-tag>
          </div>
        </el-card>

        <!-- 四、敏感性 -->
        <el-card shadow="never" class="inner-card">
          <template #header>
            <div class="section-header">
              <span>四、敏感性分析（折现率 ±1% / 增长率 ±0.5%）</span>
              <el-button size="small" type="primary" link @click="sensitivityVisible = !sensitivityVisible">
                {{ sensitivityVisible ? '收起' : '展开' }}
              </el-button>
            </div>
          </template>
          <div v-if="sensitivityVisible" class="sensitivity-matrix-wrapper">
            <table class="sensitivity-matrix">
              <thead>
                <tr>
                  <th class="matrix-corner">折现率 \ g</th>
                  <th v-for="gDelta in growthDeltas" :key="gDelta">
                    g {{ gDelta >= 0 ? '+' : '' }}{{ (gDelta * 100).toFixed(1) }}%
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="wDelta in waccDeltas" :key="wDelta">
                  <td class="matrix-row-header">
                    r {{ wDelta >= 0 ? '+' : '' }}{{ (wDelta * 100).toFixed(1) }}%
                  </td>
                  <td
                    v-for="gDelta in growthDeltas"
                    :key="gDelta"
                    :class="getSensitivityCellClass(wDelta, gDelta)"
                  >
                    {{ fmtAmt(getSensitivityValue(wDelta, gDelta)) }}
                  </td>
                </tr>
              </tbody>
            </table>
            <p class="sensitivity-note">红色 = 相对基准下降超过 5%；蓝色 = 基准情景。</p>
          </div>
        </el-card>
      </template>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>五、审计说明</span></div></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="记录测算过程：公允取值层次或无法可靠确定的理由、现金流预测来源（管理层批准预算）、WACC/CAPM 参数依据、永续增长率对照等"
        @blur="handleSaveNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>六、审计结论</span>
          <el-button v-if="!isReadonly && activeCgu" size="small" plain @click="fillConclusionDraft">
            填入结论模板
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="如：经测算资产组可收回金额为…，高于/低于账面价值…，应/无需计提商誉减值；已回写 I3-6"
        @blur="handleSaveConclusion"
      />
    </el-card>

    <details class="edit-tips" open>
      <summary>编制说明（对齐致同 I3-7 / CAS8）</summary>
      <ol>
        <li>可收回金额应当根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值两者之间较高者确定。</li>
        <li>公允净额：优先公平交易销售协议价格，其次活跃市场报价，再次以可获取的最佳信息估计；仍无法可靠估计时，以预计未来现金流量现值作为可收回金额。</li>
        <li>处置费用包括与资产处置有关的法律费用、相关税费、搬运费以及为使资产达到可销售状态所发生的直接费用等。</li>
        <li>预计未来现金流量现值：按资产持续使用及最终处置所产生的预计未来现金流量，选择恰当折现率折现；预测一般以管理层批准的最近财务预算为基础，通常不超过5年。</li>
        <li>折现率应反映货币时间价值和资产特定风险的当前市场评价；现金流与折现率税前/税后口径须一致。WACC=(D×Kd×(1−t)+E×Ke)/(D+E)；Ke=Rf+β×(Rm−Rf)。</li>
        <li>Rm/Kd/Rf 均按<strong>百分比</strong>填写（如市场回报 8 表示 8%，勿填 0.08）。测算完成后点击「回写 I3-6」同步可收回金额。</li>
        <li>资产组：企业可以认定的最小资产组合，其产生的现金流入基本独立于其他资产或资产组。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I3TabRecoverableTest.vue — I3-7 可收回金额测试
 * 对齐致同 Excel：一公允净额 / 二 DCF+CAPM / 三 MAX / 敏感性 / 编制说明
 * 公式链复用 i3RecoverableModel ← i1RecoverableModel（CAS8）
 */
import { ref, reactive, computed, watch, inject, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import {
  DCF_FORECAST_YEARS,
  defaultFvDisposal,
  defaultWaccParams,
  defaultGrowthBenchmarks,
  normalizeFvDisposal,
  normalizeWaccParams,
  normalizeGrowthBenchmarks,
  calcI3RecoverableResult,
  validateWaccParams,
  validateGrowthRate,
  buildI3ConclusionDraft,
  migrateLegacyCashFlows,
  readResponsePayload,
  type I3FairValueDisposal,
  type I3WaccParams,
  type I3GrowthBenchmarks,
} from '../../composables/i3RecoverableModel'
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

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

interface CguItem {
  rowId: string
  cguName: string
  cguBookValue: number
  goodwillAmount: number
}

const FORECAST_YEARS = DCF_FORECAST_YEARS
const waccDeltas = [-0.01, 0, 0.01]
const growthDeltas = [-0.005, 0, 0.005]
const disposalFields = [
  { key: 'legalFees', label: '法律费用' },
  { key: 'relatedTaxes', label: '相关税费' },
  { key: 'transportCosts', label: '搬运费' },
  { key: 'directCosts', label: '直接费用' },
  { key: 'otherCosts', label: '其他费用' },
] as const

const activeCguIndex = ref(0)
const auditNote = ref('')
const auditConclusion = ref('')
const sensitivityVisible = ref(true)
const preferValueInUse = ref(false)
const preferValueInUseReason = ref('')
const growthRate = ref(0)
const manualDiscountRate = ref(0.1)
const usePreTaxRate = ref(true)
const cashFlows = ref<number[]>(Array.from({ length: FORECAST_YEARS }, () => 0))
const fvDisposal = reactive<I3FairValueDisposal>(defaultFvDisposal())
const waccParams = reactive<I3WaccParams>(defaultWaccParams())
const growthBenchmarks = reactive<I3GrowthBenchmarks>(defaultGrowthBenchmarks())

const cguList = computed<CguItem[]>(() => {
  const raw = readResponsePayload(props.allResponses?.get('I3-6-rows'))
  if (Array.isArray(raw) && raw.length) {
    return raw.map((r: any, idx: number) => {
      const b1 = Number(r.goodwillB1 ?? r.goodwillAmount) || 0
      const b2 = Number(r.minorityB2) || 0
      const a = Number(r.assetGroupCarrying) || 0
      const book = Number(r.cguBookValue) || (a + b1 + b2)
      return {
        rowId: String(r.rowId || `cgu-${idx}`),
        cguName: String(r.cguName || `资产组${idx + 1}`),
        cguBookValue: book,
        goodwillAmount: b1,
      }
    })
  }
  return [{ rowId: 'cgu-default', cguName: '资产组1', cguBookValue: 0, goodwillAmount: 0 }]
})

const activeCgu = computed(() => cguList.value[activeCguIndex.value] ?? null)

const growthRatePct = computed(() => (growthRate.value || 0) * 100)

const calcResult = computed(() =>
  calcI3RecoverableResult({
    cashFlows: cashFlows.value,
    manualDiscountRate: manualDiscountRate.value,
    growthRate: growthRate.value,
    fvDisposal: { ...fvDisposal },
    waccParams: { ...waccParams },
    usePreTaxRate: usePreTaxRate.value,
  }),
)

const displayFairValueNet = computed(() =>
  preferValueInUse.value ? 0 : calcResult.value.fairValueLessDisposal,
)

const finalRecoverableAmount = computed(() => {
  if (preferValueInUse.value) return calcResult.value.valueInUse
  return calcResult.value.recoverableAmount
})

const recoverableSource = computed(() => {
  if (preferValueInUse.value) return '使用价值（仅测）'
  return calcResult.value.recoverableSource
})

/** 各 CGU 测算状态（来自 I3-7-rows + 当前页） */
const cguStatusList = computed(() => {
  const savedRows = readResponsePayload(props.allResponses?.get('I3-7-rows'))
  const byName = new Map<string, any>()
  if (Array.isArray(savedRows)) {
    for (const r of savedRows) byName.set(String(r.cguName || ''), r)
  }
  return cguList.value.map((cgu, idx) => {
    const isActive = idx === activeCguIndex.value
    const saved = byName.get(cgu.cguName)
    const recoverableAmount = isActive
      ? finalRecoverableAmount.value
      : (Number(saved?.recoverableAmount) || 0)
    return {
      rowId: cgu.rowId,
      cguName: cgu.cguName,
      recoverableAmount,
      tested: recoverableAmount > 0.005,
    }
  })
})

const impliedImpairment = computed(() =>
  Math.max((activeCgu.value?.cguBookValue || 0) - finalRecoverableAmount.value, 0),
)

const waccWarnings = computed(() => validateWaccParams(waccParams))
const growthWarnings = computed(() =>
  validateGrowthRate(growthRate.value, growthBenchmarks),
)

const fvPriceRows = computed(() => {
  const src = calcResult.value.fairValueSource
  return [
    {
      label: '销售协议价格',
      amount: fvDisposal.salesAgreementPrice,
      note: fvDisposal.salesAgreementNote,
      selected: src === '销售协议价格',
      onAmount: (v: number | undefined) => updateFvField('salesAgreementPrice', v ?? 0),
      onNote: (v: string) => updateFvField('salesAgreementNote', v),
    },
    {
      label: '活跃市场价格',
      amount: fvDisposal.activeMarketPrice,
      note: fvDisposal.activeMarketNote,
      selected: src === '活跃市场价格',
      onAmount: (v: number | undefined) => updateFvField('activeMarketPrice', v ?? 0),
      onNote: (v: string) => updateFvField('activeMarketNote', v),
    },
    {
      label: '估计价格',
      amount: fvDisposal.estimatedPrice,
      note: fvDisposal.estimatedNote,
      selected: src === '估计价格',
      onAmount: (v: number | undefined) => updateFvField('estimatedPrice', v ?? 0),
      onNote: (v: string) => updateFvField('estimatedNote', v),
    },
  ]
})

const cashFlowTableData = computed(() => {
  const r = calcResult.value
  return cashFlows.value.map((cf, i) => ({
    label: `第${i + 1}年`,
    yearIndex: i,
    cashFlow: cf,
    discountFactor: r.discountFactors[i],
    discountedCF: r.discountedCashFlows[i],
  }))
})

function updateFvField(key: string, value: number | string) {
  ;(fvDisposal as any)[key] = value
  persistState()
}

function updateCashFlow(yearIndex: number, value: number) {
  const next = [...cashFlows.value]
  next[yearIndex] = value
  cashFlows.value = next
  persistState()
}

function getSensitivityValue(waccDelta: number, growthDelta: number): number {
  const r = calcResult.value.effectiveDiscountRate + waccDelta
  const g = growthRate.value + growthDelta
  const forced = calcI3RecoverableResult({
    cashFlows: cashFlows.value,
    manualDiscountRate: r > 0 ? r : 0.001,
    growthRate: g,
    fvDisposal: preferValueInUse.value ? defaultFvDisposal() : { ...fvDisposal },
    waccParams: defaultWaccParams(), // 空 D/E → 强制用手工折现率做情景
    usePreTaxRate: true,
    legacyFairValueNet: preferValueInUse.value ? 0 : calcResult.value.fairValueLessDisposal,
  })
  if (preferValueInUse.value) return forced.valueInUse
  return forced.recoverableAmount
}

function getSensitivityCellClass(waccDelta: number, growthDelta: number): string {
  if (waccDelta === 0 && growthDelta === 0) return 'matrix-cell matrix-base'
  const val = getSensitivityValue(waccDelta, growthDelta)
  const base = finalRecoverableAmount.value
  if (base === 0) return 'matrix-cell'
  const diff = (val - base) / Math.abs(base)
  if (diff > 0.05) return 'matrix-cell matrix-positive'
  if (diff < -0.05) return 'matrix-cell matrix-negative'
  return 'matrix-cell'
}

let saveTimer: ReturnType<typeof setTimeout> | null = null

function persistState() {
  if (saveTimer) clearTimeout(saveTimer)
  saveTimer = setTimeout(() => doPersist(), 600)
}

function doPersist() {
  const cgu = activeCgu.value
  if (!cgu) return
  const cguIdx = activeCguIndex.value
  const payload = {
    schemaVersion: 2,
    cguIndex: cguIdx,
    cguName: cgu.cguName,
    cguRowId: cgu.rowId,
    cashFlows: cashFlows.value,
    growthRate: growthRate.value,
    growthBenchmarks: { ...growthBenchmarks },
    waccParams: { ...waccParams },
    fvDisposal: { ...fvDisposal },
    manualDiscountRate: manualDiscountRate.value,
    usePreTaxRate: usePreTaxRate.value,
    preferValueInUse: preferValueInUse.value,
    preferValueInUseReason: preferValueInUseReason.value,
    fairValueLessDisposal: displayFairValueNet.value,
    valueInUse: calcResult.value.valueInUse,
    recoverableAmount: finalRecoverableAmount.value,
  }
  emit('save', `I3-7-dcf-cgu-${cguIdx}`, payload)
  emit('save', `I3-7-recoverable-cgu-${cguIdx}`, finalRecoverableAmount.value)
  persistRowsAggregate()
}

function persistRowsAggregate() {
  const rows = cguList.value.map((cgu, idx) => {
    if (idx === activeCguIndex.value) {
      return {
        rowId: cgu.rowId,
        cguName: cgu.cguName,
        fairValueLessDisposal: displayFairValueNet.value,
        valueInUse: calcResult.value.valueInUse,
        recoverableAmount: finalRecoverableAmount.value,
      }
    }
    const saved = readResponsePayload(props.allResponses?.get(`I3-7-dcf-cgu-${idx}`))
    return {
      rowId: cgu.rowId,
      cguName: cgu.cguName,
      fairValueLessDisposal: Number(saved?.fairValueLessDisposal) || 0,
      valueInUse: Number(saved?.valueInUse) || 0,
      recoverableAmount: Number(saved?.recoverableAmount) || Number(
        readResponsePayload(props.allResponses?.get(`I3-7-recoverable-cgu-${idx}`)),
      ) || 0,
    }
  })
  emit('save', 'I3-7-rows', rows)
}

function resetForm() {
  Object.assign(fvDisposal, defaultFvDisposal())
  Object.assign(waccParams, defaultWaccParams())
  Object.assign(growthBenchmarks, defaultGrowthBenchmarks())
  cashFlows.value = Array.from({ length: FORECAST_YEARS }, () => 0)
  growthRate.value = 0
  manualDiscountRate.value = 0.1
  usePreTaxRate.value = true
  preferValueInUse.value = false
  preferValueInUseReason.value = ''
}

function loadState() {
  resetForm()
  const cguIdx = activeCguIndex.value
  const state = readResponsePayload(props.allResponses?.get(`I3-7-dcf-cgu-${cguIdx}`))
  if (state && typeof state === 'object') {
    const migrated = migrateLegacyCashFlows(state)
    if (migrated) {
      cashFlows.value = migrated.length >= FORECAST_YEARS
        ? migrated.slice(0, FORECAST_YEARS)
        : [...migrated, ...Array(FORECAST_YEARS - migrated.length).fill(0)]
    }
    if (state.growthRate != null) growthRate.value = Number(state.growthRate) || 0
    if (state.growthBenchmarks) Object.assign(growthBenchmarks, normalizeGrowthBenchmarks(state.growthBenchmarks))
    if (state.waccParams) {
      // 旧版小数口径 → 百分比
      const wp = { ...state.waccParams }
      if (state.schemaVersion == null && wp.taxRate != null && wp.taxRate > 0 && wp.taxRate <= 1) {
        wp.taxRate = wp.taxRate * 100
        if (wp.costOfDebt != null && wp.costOfDebt <= 1) wp.costOfDebt = wp.costOfDebt * 100
        if (wp.costOfEquity != null && wp.costOfEquity <= 1) {
          // 旧版直接填 Re，映射为近似：放入 marketReturn 不便；改用手工折现率
        }
      }
      Object.assign(waccParams, normalizeWaccParams(wp))
      // 旧 E/V + Re 形式：无 D/E 金额时回退手工折现率
      if (state.schemaVersion == null && state.waccParams?.equityRatio != null) {
        const old = state.waccParams
        const approx = (Number(old.equityRatio) || 0) * (Number(old.costOfEquity) || 0)
          + (Number(old.debtRatio) || 0) * (Number(old.costOfDebt) || 0) * (1 - (Number(old.taxRate) || 0))
        if (approx > 0) manualDiscountRate.value = approx
      }
    }
    if (state.fvDisposal) Object.assign(fvDisposal, normalizeFvDisposal(state.fvDisposal))
    else if (state.fairValueLessDisposal > 0 && !state.fvDisposal) {
      fvDisposal.estimatedPrice = Number(state.fairValueLessDisposal) || 0
      fvDisposal.estimatedNote = '由旧版「公允净额」字段迁移'
    }
    if (state.manualDiscountRate != null) manualDiscountRate.value = Number(state.manualDiscountRate) || 0.1
    if (state.usePreTaxRate != null) usePreTaxRate.value = !!state.usePreTaxRate
    if (state.preferValueInUse != null) preferValueInUse.value = !!state.preferValueInUse
    if (state.preferValueInUseReason) preferValueInUseReason.value = String(state.preferValueInUseReason)
  }

  const note = readResponsePayload(props.allResponses?.get('I3-7-conclusion'))
  if (typeof note === 'string') auditNote.value = note
  else if (note?.remark) auditNote.value = note.remark

  const conc = readResponsePayload(props.allResponses?.get('I3-7-audit-conclusion'))
  if (typeof conc === 'string') auditConclusion.value = conc
  else if (conc?.remark) auditConclusion.value = conc.remark
}

watch(activeCguIndex, () => loadState())

onMounted(() => loadState())

function handleLinkToI36() {
  doPersist()
  const cgu = activeCgu.value
  if (!cgu) return
  const rowsRaw = readResponsePayload(props.allResponses?.get('I3-6-rows'))
  if (Array.isArray(rowsRaw) && rowsRaw.length) {
    const next = rowsRaw.map((r: any) => {
      const match = (r.rowId && r.rowId === cgu.rowId)
        || String(r.cguName || '') === cgu.cguName
      if (!match) return r
      const fv = displayFairValueNet.value
      const viu = calcResult.value.valueInUse
      return {
        ...r,
        fairValueLessCost: fv > 0 ? fv : null,
        valueInUse: viu > 0 ? viu : null,
        recoverableAmount: finalRecoverableAmount.value,
      }
    })
    emit('save', 'I3-6-rows', next)
  }
  ElMessage.success(
    `已将「${cgu.cguName}」可收回金额 ${fmtAmt(finalRecoverableAmount.value)} 回写 I3-6（①公允/②使用价值）`,
  )
  emit('navigate-sheet', 'I3-6')
}

function fillConclusionDraft() {
  if (!activeCgu.value) return
  auditConclusion.value = buildI3ConclusionDraft({
    cguName: activeCgu.value.cguName,
    fairValueNet: displayFairValueNet.value,
    valueInUse: calcResult.value.valueInUse,
    recoverableAmount: finalRecoverableAmount.value,
    recoverableSource: recoverableSource.value,
    bookValue: activeCgu.value.cguBookValue,
    effectiveDiscountRate: calcResult.value.effectiveDiscountRate,
    growthRate: growthRate.value,
    fromWacc: calcResult.value.waccAfterTax > 0,
    preferValueInUse: preferValueInUse.value,
    preferValueInUseReason: preferValueInUseReason.value,
  })
  handleSaveConclusion()
}

function handleSaveNote() {
  emit('save', 'I3-7-conclusion', auditNote.value)
}

function handleSaveConclusion() {
  emit('save', 'I3-7-audit-conclusion', auditConclusion.value)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function pct(val: number | null | undefined): string {
  if (val == null) return '-'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.i3-tab-recoverable-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

.guidance-block {
  background: linear-gradient(135deg, #e8f4fd 0%, #d6ecfa 100%);
  border: 1px solid #b3d8f0;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
}
.guidance-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px 24px; }
.guidance-step {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: var(--wp-font-size, 13px); color: #1a5276; line-height: 1.5;
}
.step-num {
  display: inline-flex; align-items: center; justify-content: center;
  width: 22px; height: 22px; border-radius: 50%; background: #2980b9;
  color: #fff; font-size: 12px; font-weight: 600; flex-shrink: 0;
}

.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb; padding: 12px 16px; margin-bottom: 16px;
  font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6;
}

.objective-alert { margin-bottom: 16px; }
.block-card, .inner-card, .audit-note-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.nav-chip { cursor: pointer; }

.cgu-status-bar {
  display: flex; flex-wrap: wrap; gap: 8px;
  margin-bottom: 12px; padding: 8px 10px;
  background: #f5f7fa; border-radius: 6px;
}
.cgu-status-chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 4px 10px; border-radius: 16px;
  border: 1px solid var(--el-border-color); cursor: pointer;
  font-size: 12px; background: #fff;
}
.cgu-status-chip.active { border-color: var(--el-color-primary); box-shadow: 0 0 0 1px var(--el-color-primary-light-7); }
.cgu-status-chip.done { background: #f0f9eb; }
.cgu-status-chip.pending { opacity: 0.85; }

.sub-title {
  font-size: var(--wp-font-size, 13px); font-weight: 600;
  margin: 12px 0 8px; color: var(--el-text-color-primary);
}
.mb-8 { margin-bottom: 8px; }
.mb-12 { margin-bottom: 12px; }
.mt-8 { margin-top: 8px; }
.amt-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-header { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.highlight { color: var(--el-color-primary); font-weight: 700; }
.hint-text { font-size: 12px; color: var(--el-color-primary); margin: 0 0 12px; }

.result-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  padding: 10px 12px; background: #f5f7fa; border-radius: 6px; margin-top: 8px;
}
.wacc-result-bar {
  display: flex; flex-wrap: wrap; align-items: center; gap: 10px;
  padding: 10px 0; font-size: var(--wp-font-size, 13px);
}

.final-recoverable {
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
  padding: 16px; background: linear-gradient(135deg, #e8f5e9 0%, #c8e6c9 100%);
  border: 2px solid #66bb6a; border-radius: 10px;
}
.cmp-item { text-align: center; min-width: 120px; }
.cmp-label { font-size: 12px; color: #2e7d32; margin-bottom: 4px; }
.cmp-value { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.cmp-vs { font-weight: 600; color: #558b2f; }
.highlight-box {
  background: #fff; padding: 10px 16px; border-radius: 8px; border: 1px solid #81c784;
}

.impairment-hint {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
  margin-top: 12px; padding: 10px 12px; background: #f5f7fa; border-radius: 6px;
}
.impairment-hint.has-impairment { background: #fef0f0; }

.sensitivity-matrix-wrapper { overflow-x: auto; }
.sensitivity-matrix {
  width: 100%; border-collapse: collapse; font-size: 12px;
  font-variant-numeric: tabular-nums;
}
.sensitivity-matrix th, .sensitivity-matrix td {
  border: 1px solid var(--el-border-color); padding: 8px 12px; text-align: right;
}
.sensitivity-matrix th { background: #f5f7fa; font-weight: 600; text-align: center; }
.matrix-corner { text-align: center !important; background: #ebeef5 !important; }
.matrix-row-header { text-align: left !important; font-weight: 500; background: #f5f7fa; }
.matrix-base { background: #e3f2fd !important; font-weight: 600; }
.matrix-positive { background: #e8f5e9 !important; color: #2e7d32; }
.matrix-negative { background: #fce4ec !important; color: #c62828; }
.sensitivity-note { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 8px; }

.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
