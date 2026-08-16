<template>
  <div class="h1-tab-analysis">
    <!-- 审计目标（对齐致同模板） -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px">
      <template #title>
        <div class="obj-title">一、审计目标</div>
      </template>
      <ol class="obj-list">
        <li>资产负债表中记录的固定资产是存在的，并均已记录至恰当的账户中。</li>
        <li>所有应当记录的固定资产均已记录，所有应当包括在财务报表中的相关披露均已包括。</li>
        <li>固定资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露正确。</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H1-6" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-2" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-7" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-8" :context-project-id="projectId" />
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">分类 {{ structureRows.length }}</el-tag>
        <el-tag v-if="anomalies.length" size="small" type="danger">异常 {{ anomalies.length }}</el-tag>
        <el-button size="small" type="default" link @click="handleReview('H1-6')">💬 复核</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        编制逻辑：先做<strong>比率分析性程序</strong>（识别需追加程序的领域）→
        再按分类做<strong>结构/成新率</strong>与<strong>期间变动</strong>追踪 →
        异常项跳转 H1-7/H1-8 做细节测试。比率变动超阈值或成新率&lt;20%、增减率&gt;50%须说明原因。
      </p>
    </div>

    <!-- 二、比例分析（致同模板核心表） -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>二、审计过程 — 比例分析</span>
          <el-tag size="small" type="warning">程序表分析性程序</el-tag>
        </div>
      </template>

      <!-- 外部指标输入区 -->
      <div class="ratio-inputs">
        <div class="input-grid">
          <label>资产总额（本期）
            <el-input-number v-model="localInputs.totalAssetsCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('totalAssetsCurrent', $event)" />
          </label>
          <label>资产总额（上期）
            <el-input-number v-model="localInputs.totalAssetsPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('totalAssetsPrior', $event)" />
          </label>
          <label>本期产品产量
            <el-input-number v-model="localInputs.productionVolumeCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('productionVolumeCurrent', $event)" />
          </label>
          <label>上期产品产量
            <el-input-number v-model="localInputs.productionVolumePrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('productionVolumePrior', $event)" />
          </label>
          <label>租入资产原值（本期）
            <el-input-number v-model="localInputs.leasedInCostCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('leasedInCostCurrent', $event)" />
          </label>
          <label>租入资产原值（上期）
            <el-input-number v-model="localInputs.leasedInCostPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('leasedInCostPrior', $event)" />
          </label>
          <label>租金收入（本期{{ leaseRentAuto > 0 ? '·已取H1-19' : '' }}）
            <el-input-number v-model="localInputs.rentalIncomeCurrent" :controls="false" size="small"
              :placeholder="leaseRentAuto > 0 ? String(leaseRentAuto) : ''"
              :disabled="isReadonly" @change="onInput('rentalIncomeCurrent', $event)" />
          </label>
          <label>租金收入（上期）
            <el-input-number v-model="localInputs.rentalIncomePrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('rentalIncomePrior', $event)" />
          </label>
          <label>维修费用（本期）
            <el-input-number v-model="localInputs.maintenanceExpenseCurrent" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('maintenanceExpenseCurrent', $event)" />
          </label>
          <label>维修费用（上期）
            <el-input-number v-model="localInputs.maintenanceExpensePrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('maintenanceExpensePrior', $event)" />
          </label>
          <label>上期计提折旧
            <el-input-number v-model="localInputs.periodDepPrior" :controls="false" size="small"
              :disabled="isReadonly" @change="onInput('periodDepPrior', $event)" />
          </label>
        </div>
        <div class="fa-summary">
          <span>原值期末 <b>{{ fmtAmt(faTotals.costEnd) }}</b></span>
          <span>净值期末 <b>{{ fmtAmt(faTotals.netEnd) }}</b></span>
          <span>本期计提 <b>{{ fmtAmt(faTotals.periodDep) }}</b></span>
          <span>累计折旧 <b>{{ fmtAmt(faTotals.accDepEnd) }}</b></span>
          <span>减值余额 <b>{{ fmtAmt(faTotals.impairmentEnd) }}</b></span>
        </div>
      </div>

      <el-table :data="ratioRows" border stripe size="small" class="ratio-table">
        <el-table-column prop="seq" label="序号" width="56" align="center" />
        <el-table-column prop="name" label="比例" min-width="220">
          <template #default="{ row }">
            <div class="ratio-name">
              <span>{{ row.name }}</span>
              <el-tooltip :content="row.riskHint" placement="top">
                <span class="hint-dot" :title="row.formulaHint">?</span>
              </el-tooltip>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="本期" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'auto-src': row.autoCurrent }]" :title="row.formulaHint">
              {{ fmtRatio(row.current, row.unit) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="上期" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'auto-src': row.autoPrior }]" :title="row.formulaHint">
              {{ fmtRatio(row.prior, row.unit) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动" width="110" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isRatioAbnormal(row) }]">
              {{ fmtChange(row) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动原因及合理性解释" min-width="220">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.explanation"
              size="small"
              :placeholder="isRatioAbnormal(row) ? '变动超阈值，须说明…' : '变动原因…'"
              @change="(v: string) => setRatioExplanation(row.id, v)"
            />
            <span v-else>{{ row.explanation || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 结构分析 -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>三、结构分析（各类占比）</span>
          <el-button size="small" type="default" link @click="handleReview('H1-6-struct')">💬 复核</el-button>
        </div>
      </template>
      <el-table :data="structureRows" border stripe size="small" empty-text="请先在 H1-2 录入明细（自动取数）">
        <el-table-column prop="category" label="资产分类" min-width="120" />
        <el-table-column prop="costEnd" label="原值期末" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.costEnd) }}</span></template>
        </el-table-column>
        <el-table-column label="净值占比%" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'warn-amount': (row.proportion ?? 0) > 50 }"
              title="占比=本项净值÷净值合计×100%"
            >{{ row.proportion != null ? row.proportion.toFixed(2) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="netValue" label="净值" width="130" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.netValue) }}</span></template>
        </el-table-column>
        <el-table-column label="成新率%" width="90" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'warn-amount': row.newRate != null && row.newRate < THRESHOLD_NEW_RATE }"
              title="成新率=净值÷原值×100%"
            >{{ row.newRate != null ? row.newRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="平均年限" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="平均使用年限=原值÷本期计提折旧">
              {{ row.avgUsefulLife != null ? row.avgUsefulLife.toFixed(1) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="剩余年限" width="90" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="剩余年限=净值÷本期计提折旧">
              {{ row.remainingLife != null ? row.remainingLife.toFixed(1) : '-' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 变动分析 -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>四、变动分析（期间增减）</span>
        </div>
      </template>
      <el-table :data="changeRows" border stripe size="small" empty-text="请先在 H1-2 录入明细（自动取数）">
        <el-table-column prop="category" label="资产分类" min-width="110" />
        <el-table-column prop="priorEnd" label="上期期末" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.priorEnd) }}</span></template>
        </el-table-column>
        <el-table-column prop="currentEnd" label="本期期末" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.currentEnd) }}</span></template>
        </el-table-column>
        <el-table-column label="变动额" width="120" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.changeAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="净变动率%" width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'error-amount': isNetChangeAbnormal(row.changeRate) }"
              title="净变动率=(本期-上期)÷上期×100%"
            >{{ row.changeRate != null ? row.changeRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="增加率%" width="90" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'error-amount': (row.increaseRate ?? 0) > THRESHOLD_CHANGE_RATE }"
              title="增加率=本期增加÷期初原值×100%"
            >{{ row.increaseRate != null ? row.increaseRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减少率%" width="90" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'error-amount': (row.decreaseRate ?? 0) > THRESHOLD_CHANGE_RATE }"
              title="减少率=本期减少÷期初原值×100%"
            >{{ row.decreaseRate != null ? row.decreaseRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动原因" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.explanation"
              size="small"
              placeholder="变动原因说明…"
              @change="(v: string) => onExplanationChange(row.category, v)"
            />
            <span v-else>{{ row.explanation || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="anomalies.length" type="warning" :closable="false" show-icon class="alert-abnormal">
        <template #title>存在 {{ anomalies.length }} 项异常，请补充说明并视情况扩大至 H1-7/H1-8</template>
        <ul class="anomaly-list">
          <li v-for="(a, i) in anomalies" :key="i">{{ a.message }}</li>
        </ul>
      </el-alert>
    </el-card>

    <!-- 折旧合理性整体重算（实质性分析程序） -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>五、折旧合理性整体重算（实质性分析程序）</span>
          <el-tag size="small" type="warning">独立预期</el-tag>
        </div>
      </template>
      <div class="methodology-context recalc-hint">
        <p>
          独立重算：<strong>预期本期折旧 = 平均原值[(期初+期末)/2] × 综合年折旧率</strong>。
          综合率默认取「上期计提折旧 ÷ 期初原值」，可手工覆盖为独立测算率（如按 H1-12 加权综合率）。
          差异率超 {{ depRecalc.threshold }}% 须查明原因（折旧政策变更 / 大额集中增减 / 计提差错），
          上期计提折旧在上方比例分析区录入。
        </p>
      </div>
      <el-table :data="[depRecalc]" border size="small" class="recalc-table">
        <el-table-column label="平均原值" align="right" min-width="120">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.avgCost) }}</span></template>
        </el-table-column>
        <el-table-column label="综合年折旧率%" align="right" width="150">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!isReadonly"
              :model-value="depRecalcRate"
              size="small"
              :placeholder="row.compositeRate != null ? row.compositeRate.toFixed(2) : '待填/取上期'"
              style="width:100%"
              @change="setDepRecalcRate"
            />
            <span v-else>{{ row.compositeRate != null ? row.compositeRate.toFixed(2) + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预期本期折旧" align="right" min-width="120">
          <template #default="{ row }">
            <span class="formula-cell" :title="`来源：${row.compositeRateSource || '缺依据'}`">
              {{ row.expectedDep != null ? fmtAmt(row.expectedDep) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="账面本期折旧" align="right" min-width="120">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookedDep) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" align="right" width="120">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': row.flagged }]">
              {{ row.diff != null ? fmtAmt(row.diff) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" align="right" width="100">
          <template #default="{ row }">
            <span :class="{ 'error-amount': row.flagged }">
              {{ row.diffRate != null ? row.diffRate.toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert
        v-if="!depRecalc.hasBasis"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="缺少测算依据：请在比例分析区填写「上期计提折旧」，或手工输入综合年折旧率。"
      />
      <el-alert
        v-else-if="depRecalc.flagged"
        type="warning"
        :closable="false"
        show-icon
        style="margin-top:8px"
        :title="`账面折旧与独立预期差异 ${depRecalc.diffRate?.toFixed(1)}%（超阈值 ${depRecalc.threshold}%），请说明原因并视情况扩大测试。`"
      />
      <div class="recalc-explain">
        <label>差异原因及合理性说明</label>
        <el-input
          v-if="!isReadonly"
          :model-value="depRecalcExplanation"
          type="textarea"
          :autosize="{ minRows: 2 }"
          placeholder="如：本期大额购建集中在下半年（半年折旧）、折旧政策/残值率变更、上年基数含一次性处置等…"
          @change="setDepRecalcExplanation"
        />
        <span v-else class="explain-ro">{{ depRecalcExplanation || '—' }}</span>
      </div>
    </el-card>

    <!-- 折旧税会差异 → 递延所得税联动 -->
    <el-card shadow="never" class="analysis-card">
      <template #header>
        <div class="section-title">
          <span>六、折旧税会差异（递延所得税联动）</span>
          <div class="header-chips">
            <GtIndexChip value="wp:N1" :context-project-id="projectId" />
            <GtIndexChip value="wp:N3" :context-project-id="projectId" />
          </div>
        </div>
      </template>
      <div class="methodology-context recalc-hint">
        <p>
          <strong>暂时性差异 = 账面价值 − 计税基础</strong>；计税基础 = 原值 − 税法累计折旧（税法不认减值）。
          账面价值 &lt; 计税基础 → 可抵扣暂时性差异 → 递延所得税资产（N1）；账面价值 &gt; 计税基础 → 应纳税暂时性差异 → 递延所得税负债（N3）。
          税率差异（加速折旧/一次性税前扣除）由本期折旧税会差异驱动，结果供 N1/N3 底稿取数。
        </p>
      </div>
      <div class="ratio-inputs">
        <div class="input-grid">
          <label>税法累计折旧（期末）
            <el-input-number :model-value="taxAccumDep" :controls="false" size="small"
              :disabled="isReadonly" @change="setTaxAccumDep" />
          </label>
          <label>本期税法折旧
            <el-input-number :model-value="taxPeriodDep" :controls="false" size="small"
              :disabled="isReadonly" @change="setTaxPeriodDep" />
          </label>
          <label>适用所得税率%（默认25）
            <el-input-number :model-value="taxRate" :controls="false" size="small" :precision="2"
              :placeholder="'25'" :disabled="isReadonly" @change="setTaxRate" />
          </label>
        </div>
      </div>
      <el-table :data="[dtRecalc]" border size="small" class="recalc-table">
        <el-table-column label="账面价值" align="right" min-width="120">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookCarrying) }}</span></template>
        </el-table-column>
        <el-table-column label="计税基础" align="right" min-width="120">
          <template #default="{ row }">
            <span class="formula-cell" title="原值−税法累计折旧">{{ row.taxBase != null ? fmtAmt(row.taxBase) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="暂时性差异" align="right" min-width="120">
          <template #default="{ row }">
            <span :class="['amount-cell', { 'error-amount': row.nature !== 'none' }]">
              {{ row.temporaryDiff != null ? fmtAmt(row.temporaryDiff) : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="性质" align="center" width="110">
          <template #default="{ row }">
            <el-tag v-if="row.nature === 'deductible'" size="small" type="success">可抵扣</el-tag>
            <el-tag v-else-if="row.nature === 'taxable'" size="small" type="warning">应纳税</el-tag>
            <span v-else>—</span>
          </template>
        </el-table-column>
        <el-table-column label="递延所得税资产(N1)" align="right" min-width="140">
          <template #default="{ row }">
            <span class="formula-cell" title="可抵扣暂时性差异×税率">{{ row.deferredTaxAsset ? fmtAmt(row.deferredTaxAsset) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="递延所得税负债(N3)" align="right" min-width="140">
          <template #default="{ row }">
            <span class="formula-cell" title="应纳税暂时性差异×税率">{{ row.deferredTaxLiability ? fmtAmt(row.deferredTaxLiability) : '-' }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="fa-summary" style="margin-top:8px">
        <span>账面本期折旧 <b>{{ fmtAmt(faTotals.periodDep) }}</b></span>
        <span>本期折旧税会差异 <b :class="{ 'error-amount': dtRecalc.periodDepDiff != null && Math.abs(dtRecalc.periodDepDiff) > 0.005 }">{{ dtRecalc.periodDepDiff != null ? fmtAmt(dtRecalc.periodDepDiff) : '—' }}</b></span>
      </div>
      <el-alert
        v-if="!dtRecalc.hasBasis"
        type="info"
        :closable="false"
        show-icon
        style="margin-top:8px"
        title="缺少计税基础依据：请填写「税法累计折旧（期末）」以测算暂时性差异及递延所得税。"
      />
      <div class="recalc-explain">
        <label>税会差异说明（加速折旧 / 一次性扣除 / 减值不得税前扣除等）</label>
        <el-input
          v-if="!isReadonly"
          :model-value="taxDiffExplanation"
          type="textarea"
          :autosize="{ minRows: 2 }"
          placeholder="如：本期享受固定资产一次性税前扣除政策，税法折旧大于账面折旧，形成应纳税暂时性差异；减值准备不得税前扣除，形成可抵扣暂时性差异…"
          @change="setTaxDiffExplanation"
        />
        <span v-else class="explain-ro">{{ taxDiffExplanation || '—' }}</span>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>七、审计说明</span>
          <el-button size="small" type="primary" link :loading="aiLoading" :disabled="isReadonly" @click="handleAiDraft">
            <el-icon><MagicStick /></el-icon> AI 生成
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：所实施的比例分析、结构/期间变动、数据来源（H1-2/H1-19）、异常项识别及跟进程序。"
        @change="saveAnalysisNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="note-card">
      <template #header><span>八、审计结论（分析性程序）</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="分析性程序总体结论：比率/结构/变动是否合理，是否需追加细节测试…"
        @change="saveAnalysisConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>比例分析对齐程序表：净值/资产总额、折旧与减值占原值、原值/产量、租入占比、租金收益率、维修费占比</li>
        <li>固定资产原值/折旧/减值自动取自 H1-2；租金收入可自动取自 H1-19；其余外部指标手填</li>
        <li>比率变动：百分点差绝对值&gt;{{ THRESHOLD_RATIO_PP }}pp（或倍数相对变动&gt;{{ THRESHOLD_RATIO_REL }}%）标红须说明</li>
        <li>成新率&lt;{{ THRESHOLD_NEW_RATE }}% 黄色；增加/减少率&gt;{{ THRESHOLD_CHANGE_RATE }}% 红色</li>
        <li>异常增减分别跳转 H1-7 增加检查 / H1-8 减少检查做细节测试</li>
        <li>分类「变动说明」与 H1-1 净值表共用，两边编辑双向同步</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, reactive, watch, inject, toRef, onMounted } from 'vue'
import { MagicStick } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useH1Analysis, type RatioInputs, type RatioRow } from '../../composables/useH1Analysis'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const conclusion = ref('')
const auditNoteText = ref('')
const aiLoading = ref(false)
const NOTE_KEY = 'H1-6-audit-note'
const CONCLUSION_KEY = 'H1-6-audit-conclusion'

const allResponsesRef = toRef(props, 'allResponses')

const {
  ratioRows,
  structureRows,
  changeRows,
  anomalies,
  faTotals,
  leaseRentAuto,
  ratioInputs,
  depreciationRecalc: depRecalc,
  depRecalcRate,
  depRecalcExplanation,
  setDepRecalcRate,
  setDepRecalcExplanation,
  deferredTaxRecalc: dtRecalc,
  taxAccumDep,
  taxPeriodDep,
  taxRate,
  taxDiffExplanation,
  setTaxAccumDep,
  setTaxPeriodDep,
  setTaxRate,
  setTaxDiffExplanation,
  updateRatioInput,
  setRatioExplanation,
  setChangeExplanation,
  saveNote,
  saveConclusion,
  THRESHOLD_NEW_RATE,
  THRESHOLD_CHANGE_RATE,
  THRESHOLD_RATIO_PP,
  THRESHOLD_RATIO_REL,
} = useH1Analysis(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    onSave: (itemId, value) => {
      const existing = props.allResponses.get(itemId) || { item_id: itemId, conclusion: null, remark: null }
      props.allResponses.set(itemId, { ...existing, remark: typeof value === 'string' ? value : JSON.stringify(value) })
      saveResponse(itemId, value)
    },
  },
)

const localInputs = reactive<RatioInputs>({ ...ratioInputs.value })

watch(ratioInputs, (v) => {
  Object.assign(localInputs, v)
}, { deep: true, immediate: true })

function onInput<K extends keyof RatioInputs>(key: K, val: RatioInputs[K]) {
  updateRatioInput(key, val)
}

function saveAnalysisNote() {
  auditNoteText.value && saveNote(auditNoteText.value)
  saveResponse(NOTE_KEY, auditNoteText.value)
}
function saveAnalysisConclusion() {
  conclusion.value && saveConclusion(conclusion.value)
  saveResponse(CONCLUSION_KEY, conclusion.value)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) conclusion.value = c.remark
})

function isRatioAbnormal(row: RatioRow): boolean {
  if (row.change == null) return false
  const abs = Math.abs(row.change)
  return row.unit === 'pct' ? abs > THRESHOLD_RATIO_PP : abs > THRESHOLD_RATIO_REL
}

function isNetChangeAbnormal(rate: number | null): boolean {
  return rate != null && Math.abs(rate) > 20
}

function onExplanationChange(category: string, text: string) {
  setChangeExplanation(category, text)
}

function handleReview(id: string) { openReviewDialog(id) }

async function handleAiDraft() {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/ai-generate`,
      {
        section: 'analysis-change',
        existingContent: auditNoteText.value || '',
        relatedContext: {
          ratios: ratioRows.value.map((r) => ({
            name: r.name,
            current: r.current,
            prior: r.prior,
            change: r.change,
            explanation: r.explanation,
            abnormal: isRatioAbnormal(r),
          })),
          structure: structureRows.value,
          changes: changeRows.value,
          anomalies: anomalies.value,
          faTotals: faTotals.value,
        },
      },
      { _silent: true } as any,
    )
    const text = res.data?.content || res.data?.data?.content || ''
    if (!text) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    auditNoteText.value = text
    saveAnalysisNote()
    ElMessage.success('已生成审计说明')
  } catch {
    ElMessage.error('AI 生成失败')
  } finally {
    aiLoading.value = false
  }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtRatio(val: number | null, unit: 'pct' | 'multiple'): string {
  if (val == null) return '—'
  return unit === 'pct' ? `${val.toFixed(2)}%` : val.toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtChange(row: RatioRow): string {
  if (row.change == null) return '—'
  if (row.unit === 'pct') return `${row.change >= 0 ? '+' : ''}${row.change.toFixed(2)}pp`
  return `${row.change >= 0 ? '+' : ''}${row.change.toFixed(1)}%`
}
</script>

<style scoped>
.h1-tab-analysis { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-title { font-weight: 600; margin-bottom: 4px; }
.obj-list { margin: 4px 0 0; padding-left: 18px; font-size: 12px; line-height: 1.6; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning); background: #fffbe6;
  padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px;
}
.analysis-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.ratio-inputs { margin-bottom: 12px; }
.input-grid {
  display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 8px 12px; margin-bottom: 10px;
}
.input-grid label {
  display: flex; flex-direction: column; gap: 4px;
  font-size: 12px; color: var(--el-text-color-secondary);
}
.input-grid :deep(.el-input-number) { width: 100%; }
.fa-summary {
  display: flex; flex-wrap: wrap; gap: 12px 20px;
  font-size: 12px; color: var(--el-text-color-regular);
  padding: 8px 10px; background: var(--el-fill-color-lighter); border-radius: 4px;
}
.ratio-name { display: flex; align-items: center; gap: 6px; }
.hint-dot {
  display: inline-flex; align-items: center; justify-content: center;
  width: 14px; height: 14px; border-radius: 50%;
  font-size: 10px; background: var(--el-color-info-light-7); cursor: help;
}
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums;
}
.auto-src { color: var(--el-color-primary); }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); font-weight: 600; }
.alert-abnormal { margin-top: 12px; }
.anomaly-list { margin: 6px 0 0; padding-left: 18px; font-size: 12px; }
.recalc-hint { margin-bottom: 10px; }
.recalc-table { margin-bottom: 4px; }
.recalc-explain { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.recalc-explain label { font-size: 12px; color: var(--el-text-color-secondary); }
.explain-ro { font-size: 12px; color: var(--el-text-color-regular); }
.header-chips { display: flex; align-items: center; gap: 6px; }
.note-card { margin-bottom: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
