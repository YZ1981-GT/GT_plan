<template>
  <div class="h1-tab-recoverable">
    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：固定资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。复核可收回金额=MAX(公允净额, 预计未来现金流量现值)，关键假设合理。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="info">索引号 H1-15</el-tag>
        <el-tag size="small">{{ state.groups.value.length }} 个资产组</el-tag>
        <el-tag v-if="state.idleAssetsAvailable.value.length" size="small" type="warning">
          H1-4 闲置 {{ state.idleAssetsAvailable.value.length }} 项
        </el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H1-4" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-14" :context-project-id="projectId" />
        <GtIndexChip value="wp:H1-15" :context-project-id="projectId" />
        <el-button size="small" :disabled="isReadonly || !state.idleAssetsAvailable.value.length" @click="handleImportIdle">
          从 H1-4 引入
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleSyncToH14">
          回写当前组
        </el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSyncAll">
          回写全部
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleForceSync">
          强制回写④→H1-14
        </el-button>
        <el-button size="small" circle @click="handleReview('H1-15')">💬</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>CAS8：</strong>可收回金额根据资产的公允价值减去处置费用后的净额与资产预计未来现金流量的现值两者之间较高者确定。
        折现率应为反映当前市场货币时间价值和资产特定风险的<strong>税前利率</strong>；现金流与折现率口径须一致。
      </p>
    </div>

    <!-- 测试对象 / 多资产组切换 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>测试对象（资产组切换）</span>
          <div class="title-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleAddGroup">+ 新增资产组</el-button>
            <el-button
              size="small"
              type="danger"
              plain
              :disabled="isReadonly || state.groups.value.length <= 1"
              @click="handleRemoveGroup"
            >
              删除当前组
            </el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" size="small" label-width="100px">
        <el-form-item label="切换资产组">
          <el-select
            :model-value="state.activeGroupId.value"
            style="width: 260px"
            filterable
            @change="(id: string) => state.setActiveGroup(id)"
          >
            <el-option
              v-for="g in state.groups.value"
              :key="g.groupId"
              :label="`${g.name || '未命名'}（账面 ${fmtAmt(g.bookValue)}）`"
              :value="g.groupId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="资产组名称">
          <el-input
            :model-value="state.activeGroup.value.name"
            :disabled="isReadonly"
            placeholder="项目/资产组名称"
            style="width: 200px"
            @update:model-value="(v: string) => { state.activeGroup.value.name = v; state.activeGroup.value.fvDisposal.assetName = v }"
            @change="(v: string) => state.renameActiveGroup(v)"
          />
        </el-form-item>
        <el-form-item label="账面价值">
          <el-input-number
            :model-value="state.bookValue.value"
            :controls="false"
            :disabled="isReadonly"
            @change="(v: number | undefined) => state.updateBookValue(v ?? 0)"
          />
        </el-form-item>
        <el-form-item v-if="state.activeGroup.value.sourceIdleRowId" label="来源">
          <el-tag size="small" type="success">H1-4 闲置</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 一、公允价值减处置费用净额 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>一、公允价值减去处置费用后的净额</span>
        </div>
      </template>

      <h4 class="sub-title">（1）公允价值确定（优先：销售协议 → 活跃市场 → 估计）</h4>
      <el-table :data="fvPriceRows" border size="small" class="mb-12">
        <el-table-column prop="label" label="确定方法" width="160" />
        <el-table-column label="金额" width="160" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.amount"
              :controls="false"
              size="small"
              @change="row.onAmount"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="说明" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.note"
              size="small"
              placeholder="取值依据..."
              @update:model-value="row.onNoteInput"
              @change="row.onNote"
            />
            <span v-else>{{ row.note }}</span>
          </template>
        </el-table-column>
        <el-table-column label="选用" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.selected" type="success" size="small">选用</el-tag>
          </template>
        </el-table-column>
      </el-table>

      <h4 class="sub-title">（2）处置费用</h4>
      <el-form label-width="110px" size="small">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="法律费用">
              <el-input-number v-model="state.fvDisposal.value.legalFees" :controls="false" :disabled="isReadonly" @change="persistFv" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="相关税费">
              <el-input-number v-model="state.fvDisposal.value.relatedTaxes" :controls="false" :disabled="isReadonly" @change="persistFv" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="搬运费">
              <el-input-number v-model="state.fvDisposal.value.transportCosts" :controls="false" :disabled="isReadonly" @change="persistFv" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="直接费用">
              <el-input-number v-model="state.fvDisposal.value.directCosts" :controls="false" :disabled="isReadonly" @change="persistFv" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="其他">
              <el-input-number v-model="state.fvDisposal.value.otherCosts" :controls="false" :disabled="isReadonly" @change="persistFv" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="处置费用合计">
              <span class="formula-cell">{{ fmtAmt(state.disposalTotal.value) }}</span>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="result-bar">
        <span>公允价值（{{ state.fairValueResolved.value.source }}）</span>
        <b class="amount-cell">{{ fmtAmt(state.fairValueResolved.value.value) }}</b>
        <span>− 处置费用</span>
        <b class="amount-cell">{{ fmtAmt(state.disposalTotal.value) }}</b>
        <span>= 公允净额</span>
        <b class="primary-amt">{{ fmtAmt(state.fairValueLessDisposal.value) }}</b>
      </div>

      <el-input
        v-model="state.fvDisposal.value.auditNote"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="审计说明：公允价值及处置费用取值依据..."
        class="mt-8"
        @change="persistFv"
      />
    </el-card>

    <!-- 二、预计未来现金流量现值 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>二、预计未来现金流量的现值（使用价值）</span>
        </div>
      </template>

      <!-- 现金流预测 -->
      <h4 class="sub-title">（1）未来现金流量预测（一般不超过5年）</h4>
      <el-form :inline="true" size="small" class="mb-8">
        <el-form-item label="预测期(年)">
          <el-input-number
            v-model="state.dcfParams.value.forecastPeriod"
            :min="3"
            :max="10"
            :disabled="isReadonly"
            @change="onForecastPeriodChange"
          />
        </el-form-item>
        <el-form-item label="永续增长率g%">
          <el-input-number
            v-model="state.dcfParams.value.perpetualGrowthRate"
            :min="-5"
            :max="10"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            @change="() => state.updateDcfParams({ perpetualGrowthRate: state.dcfParams.value.perpetualGrowthRate })"
          />
        </el-form-item>
      </el-form>

      <el-table :data="state.cashFlowRows.value" border stripe size="small" class="mb-12">
        <el-table-column prop="yearLabel" label="年份" width="80" align="center" />
        <el-table-column label="现金流入/收入" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.revenue"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateCashFlowYear(row.year - 1, 'revenue', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.revenue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现金流出/成本" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.cost"
              :controls="false"
              size="small"
              @change="(v: number | undefined) => state.updateCashFlowYear(row.year - 1, 'cost', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.cost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="净现金流" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="收入−成本">{{ fmtAmt(row.fcf) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折现系数" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="1/(1+r)^n">{{ row.discountFactor.toFixed(4) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现值" width="130" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="净现金流×折现系数">{{ fmtAmt(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <el-descriptions :column="3" border size="small" class="mb-12">
        <el-descriptions-item label="行业长期平均增长率%">
          <el-input-number
            v-if="!isReadonly"
            v-model="state.dcfParams.value.industryGrowthRate"
            :controls="false"
            size="small"
            @change="() => state.updateDcfParams({ industryGrowthRate: state.dcfParams.value.industryGrowthRate })"
          />
          <span v-else>{{ state.dcfParams.value.industryGrowthRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="市场长期增长率%">
          <el-input-number
            v-if="!isReadonly"
            v-model="state.dcfParams.value.marketGrowthRate"
            :controls="false"
            size="small"
            @change="() => state.updateDcfParams({ marketGrowthRate: state.dcfParams.value.marketGrowthRate })"
          />
          <span v-else>{{ state.dcfParams.value.marketGrowthRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="国家/地区长期增长率%">
          <el-input-number
            v-if="!isReadonly"
            v-model="state.dcfParams.value.countryGrowthRate"
            :controls="false"
            size="small"
            @change="() => state.updateDcfParams({ countryGrowthRate: state.dcfParams.value.countryGrowthRate })"
          />
          <span v-else>{{ state.dcfParams.value.countryGrowthRate }}%</span>
        </el-descriptions-item>
        <el-descriptions-item label="增长率确定依据" :span="3">
          <el-input
            v-if="!isReadonly"
            v-model="state.dcfParams.value.growthRateBasis"
            size="small"
            placeholder="说明永续增长率选取依据（应≤外部基准）"
            @change="() => state.updateDcfParams({ growthRateBasis: state.dcfParams.value.growthRateBasis })"
          />
          <span v-else>{{ state.dcfParams.value.growthRateBasis }}</span>
        </el-descriptions-item>
      </el-descriptions>

      <!-- WACC -->
      <h4 class="sub-title">（2）折现率 / 加权平均资金成本（WACC）</h4>
      <el-form label-width="130px" size="small">
        <el-row :gutter="12">
          <el-col :span="8">
            <el-form-item label="所得税率 t%">
              <el-input-number v-model="state.waccParams.value.taxRate" :controls="false" :min="0" :max="100" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="付息负债 D">
              <el-input-number v-model="state.waccParams.value.totalDebt" :controls="false" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="权益资本 E">
              <el-input-number v-model="state.waccParams.value.totalEquity" :controls="false" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="债务成本 Kd%">
              <el-input-number v-model="state.waccParams.value.costOfDebt" :controls="false" :precision="2" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="无风险利率 Rf%">
              <el-input-number v-model="state.waccParams.value.riskFreeRate" :controls="false" :precision="2" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="β系数">
              <el-input-number v-model="state.waccParams.value.beta" :controls="false" :precision="3" :step="0.1" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="市场回报 Rm%">
              <el-input-number v-model="state.waccParams.value.marketReturn" :controls="false" :precision="2" :disabled="isReadonly" @change="persistWacc" />
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="权益成本 Ke%">
              <span class="formula-cell" title="Ke = Rf + β×(Rm−Rf)">{{ state.costOfEquity.value.toFixed(2) }}%</span>
            </el-form-item>
          </el-col>
          <el-col :span="8">
            <el-form-item label="折现口径">
              <el-radio-group
                v-model="state.dcfParams.value.usePreTaxRate"
                :disabled="isReadonly"
                size="small"
                @change="() => state.updateDcfParams({ usePreTaxRate: state.dcfParams.value.usePreTaxRate })"
              >
                <el-radio-button :value="true">税前(CAS8)</el-radio-button>
                <el-radio-button :value="false">税后</el-radio-button>
              </el-radio-group>
            </el-form-item>
          </el-col>
        </el-row>
      </el-form>

      <div class="wacc-result-bar">
        <span title="WACC税后 = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)">WACC(税后)</span>
        <b>{{ state.waccAfterTax.value.toFixed(2) }}%</b>
        <span title="税前折现率 ≈ WACC税后/(1−t)">折现率(税前)</span>
        <b>{{ state.preTaxDiscountRate.value.toFixed(2) }}%</b>
        <span>实际折现率</span>
        <b class="primary-amt">{{ state.effectiveDiscountRate.value.toFixed(2) }}%</b>
        <el-tag v-if="state.dcfResult.value.rateInvalid" type="danger" size="small">折现率≤增长率，终值无效</el-tag>
        <el-tag v-if="state.waccAfterTax.value <= 0" type="warning" size="small">未填 D/E，使用手工折现率 {{ state.dcfParams.value.discountRate }}%</el-tag>
      </div>

      <el-form v-if="state.waccAfterTax.value <= 0" :inline="true" size="small" class="mt-8">
        <el-form-item label="手工折现率%">
          <el-input-number
            v-model="state.dcfParams.value.discountRate"
            :min="0.1"
            :max="50"
            :controls="false"
            :precision="2"
            :disabled="isReadonly"
            @change="() => state.updateDcfParams({ discountRate: state.dcfParams.value.discountRate })"
          />
        </el-form-item>
      </el-form>

      <!-- DCF结果 -->
      <h4 class="sub-title">（3）现值汇总</h4>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="预测期现值合计">
          <span class="formula-cell">{{ fmtAmt(state.dcfResult.value.pvCashFlows) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="终值（未折现）">
          <span class="formula-cell" title="TV = CFn×(1+g)/(r−g)">{{ fmtAmt(state.dcfResult.value.terminalValue) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="终值现值">
          <span class="formula-cell">{{ fmtAmt(state.dcfResult.value.terminalValueDiscounted) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="使用价值(DCF)">
          <b class="primary-amt">{{ fmtAmt(state.dcfResult.value.totalPV) }}</b>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 三、可收回金额 -->
    <el-card shadow="never" class="block-card recoverable-card">
      <template #header>
        <div class="section-title">
          <span>三、可收回金额</span>
        </div>
      </template>
      <div class="final-recoverable">
        <div class="cmp-item">
          <div class="cmp-label">公允净额</div>
          <div class="cmp-value">{{ fmtAmt(state.fairValueLessDisposal.value) }}</div>
        </div>
        <div class="cmp-vs">vs</div>
        <div class="cmp-item">
          <div class="cmp-label">使用价值(DCF)</div>
          <div class="cmp-value">{{ fmtAmt(state.dcfResult.value.totalPV) }}</div>
        </div>
        <div class="cmp-vs">→</div>
        <div class="cmp-item highlight">
          <div class="cmp-label">可收回金额（取较高者）</div>
          <div class="cmp-value primary-amt">{{ fmtAmt(state.recoverableAmount.value) }}</div>
          <el-tag size="small" type="primary">{{ state.recoverableSource.value }}</el-tag>
        </div>
      </div>
      <div class="impairment-hint" :class="{ 'has-impairment': state.impliedImpairment.value > 0 }">
        <span>账面价值 {{ fmtAmt(state.bookValue.value) }}</span>
        <span>− 可收回金额 {{ fmtAmt(state.recoverableAmount.value) }}</span>
        <span>= 应计提减值</span>
        <b>{{ fmtAmt(state.impliedImpairment.value) }}</b>
        <el-tag v-if="state.impliedImpairment.value > 0" type="danger" size="small">存在减值</el-tag>
        <el-tag v-else type="success" size="small">无需减值</el-tag>
      </div>
    </el-card>

    <!-- 敏感性分析：可收回金额二维矩阵 + 终值单独轴 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>四、敏感性分析</span>
        </div>
      </template>

      <h4 class="sub-title">（1）可收回金额矩阵（折现率 ±2% × 增长率 ±1%）</h4>
      <el-table :data="state.sensitivityGrid.value.rows" border size="small" class="matrix-table mb-12">
        <el-table-column prop="label" label="折现率↓ / g→" width="120" fixed />
        <el-table-column
          v-for="g in state.sensitivityGrid.value.growths"
          :key="g"
          :label="`${g.toFixed(1)}%`"
          width="110"
          align="right"
        >
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'error-amount': (row.cells[`g_${g}`] ?? 0) < state.bookValue.value && state.bookValue.value > 0 }]"
            >
              {{ fmtAmt(row.cells[`g_${g}`]) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div class="matrix-hint mb-12">红色 = 可收回金额 &lt; 账面价值（该情景下存在减值）</div>

      <h4 class="sub-title">（2）终值单独敏感轴（固定另一参数，只观察终值现值）</h4>
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="axis-caption">折现率轴（g 固定为基准 {{ state.dcfParams.value.perpetualGrowthRate }}%）</div>
          <el-table :data="state.terminalSensitivityByRate.value" border size="small" class="matrix-table">
            <el-table-column prop="paramLabel" label="折现率" min-width="110" />
            <el-table-column label="终值（未折现）" width="120" align="right">
              <template #default="{ row }">
                <span :class="{ 'error-amount': row.invalid }">{{ row.invalid ? '无效' : fmtAmt(row.terminalValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="终值现值" width="120" align="right">
              <template #default="{ row }">
                <span
                  class="formula-cell"
                  :class="{ 'error-amount': !row.invalid && row.terminalValueDiscounted + row.forecastPv < state.bookValue.value && state.bookValue.value > 0 }"
                >
                  {{ row.invalid ? '-' : fmtAmt(row.terminalValueDiscounted) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="终值占比" width="90" align="right">
              <template #default="{ row }">
                {{ row.invalid || row.totalDcf <= 0 ? '-' : ((row.terminalValueDiscounted / row.totalDcf) * 100).toFixed(1) + '%' }}
              </template>
            </el-table-column>
          </el-table>
        </el-col>
        <el-col :span="12">
          <div class="axis-caption">增长率轴（折现率固定为基准 {{ state.effectiveDiscountRate.value.toFixed(2) }}%）</div>
          <el-table :data="state.terminalSensitivityByGrowth.value" border size="small" class="matrix-table">
            <el-table-column prop="paramLabel" label="永续增长率 g" min-width="120" />
            <el-table-column label="终值（未折现）" width="120" align="right">
              <template #default="{ row }">
                <span :class="{ 'error-amount': row.invalid }">{{ row.invalid ? '无效' : fmtAmt(row.terminalValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="终值现值" width="120" align="right">
              <template #default="{ row }">
                <span
                  class="formula-cell"
                  :class="{ 'error-amount': !row.invalid && row.terminalValueDiscounted + row.forecastPv < state.bookValue.value && state.bookValue.value > 0 }"
                >
                  {{ row.invalid ? '-' : fmtAmt(row.terminalValueDiscounted) }}
                </span>
              </template>
            </el-table-column>
            <el-table-column label="终值占比" width="90" align="right">
              <template #default="{ row }">
                {{ row.invalid || row.totalDcf <= 0 ? '-' : ((row.terminalValueDiscounted / row.totalDcf) * 100).toFixed(1) + '%' }}
              </template>
            </el-table-column>
          </el-table>
        </el-col>
      </el-row>
      <div class="matrix-hint">终值轴用于评估永续假设对结论的主导程度；占比过高时需加强 g 与外部基准的复核。</div>
    </el-card>

    <!-- 审计说明 / 结论 -->
    <el-card shadow="never" class="block-card">
      <template #header><span>五、审计说明</span></template>
      <el-input
        v-model="state.recoverableNote.value"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：公允取值层次、处置费用依据、现金流预测来源、WACC参数取值、与管理层沟通及复核情况等。"
        @change="(v: string) => state.saveRecoverableNote(v)"
      />
    </el-card>

    <el-card shadow="never" class="block-card">
      <template #header><span>六、审计结论</span></template>
      <el-input
        v-model="state.recoverableConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="可收回金额测试结论（如：经测算可收回金额为…，高于/低于账面价值…，减值准备计提是否充分）"
        @change="(v: string) => state.saveRecoverableConclusion(v)"
      />
    </el-card>

    <!-- 编制提示（对齐 Excel 提示区，并澄清税前/税后口径） -->
    <details class="compile-hint">
      <summary>编制提示（CAS8 可收回金额）</summary>
      <ol>
        <li>可收回金额 = MAX(公允价值−处置费用净额, 预计未来现金流量现值)。</li>
        <li>公允净额优先取公平交易中销售协议价格减处置费用；无协议则取活跃市场价格；再无则按最佳信息估计；无法可靠估计公允时，以预计未来现金流量现值作为可收回金额。</li>
        <li>处置费用包括法律费用、相关税费、搬运费以及为使资产达到可销售状态所发生的直接费用。</li>
        <li>预计未来现金流量应基于管理层批准的最近财务预算/预测；预测期一般不超过5年；以后年度增长率应稳定或递减，且通常不超过产品/行业/国家长期平均增长率。</li>
        <li>折现率应为反映当前市场货币时间价值和资产特定风险的<strong>税前</strong>利率（CAS8）。实务可先算税后WACC再转换为税前；若现金流为税后口径，也可直接使用税后折现率，但须在说明中披露口径匹配关系。</li>
        <li>WACC参数：D取付息负债（宜用市值，实务常近似账面）；E取权益市值；Kd取边际借款成本；Rf通常取10年期国债到期收益率；Rm取覆盖经济周期的长期几何平均回报；β反映资产相对市场的系统风险。</li>
        <li>折现率须与现金流假设一致，且折现率 &gt; 永续增长率，否则终值模型无效。</li>
        <li>测算完成后点击「回写当前组/全部」，将公允净额与DCF现值同步至 H1-14 减值测算表。</li>
        <li>多资产组：可从 H1-4 闲置清单一键引入（账面=净值）；切换资产组分别测算后再全部回写。</li>
        <li>终值敏感轴：在固定另一参数下单独扰动折现率或 g，观察终值现值及占比，避免仅看二维矩阵掩盖终值主导风险。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabRecoverable.vue — H1-15 可收回金额测试表
 *
 * 对齐 Excel「固定资产减值准备测试表-可收回金额」结构：
 * 一、公允净额 → 二、DCF/WACC → 三、可收回金额MAX → 敏感性 → 说明/结论
 * 逻辑层：useH1Impairment（DCF引擎 + WACC/CAPM + 回写H1-14）
 */
import { computed, inject, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH1Impairment } from '../../composables/useH1Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const state = useH1Impairment(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

/** 公允价值三层次表格行 */
const fvPriceRows = computed(() => {
  const fv = state.fvDisposal.value
  const source = state.fairValueResolved.value.source
  return [
    {
      label: '1.销售协议价格',
      amount: fv.salesAgreementPrice,
      note: fv.salesAgreementNote,
      selected: source === '销售协议价格',
      onAmount: (v: number | undefined) => onFvChange({ salesAgreementPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.salesAgreementNote = v },
      onNote: () => onFvChange({ salesAgreementNote: fv.salesAgreementNote }),
    },
    {
      label: '2.活跃市场价格',
      amount: fv.activeMarketPrice,
      note: fv.activeMarketNote,
      selected: source === '活跃市场价格',
      onAmount: (v: number | undefined) => onFvChange({ activeMarketPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.activeMarketNote = v },
      onNote: () => onFvChange({ activeMarketNote: fv.activeMarketNote }),
    },
    {
      label: '3.估计价格',
      amount: fv.estimatedPrice,
      note: fv.estimatedNote,
      selected: source === '估计价格',
      onAmount: (v: number | undefined) => onFvChange({ estimatedPrice: v ?? 0 }),
      onNoteInput: (v: string) => { fv.estimatedNote = v },
      onNote: () => onFvChange({ estimatedNote: fv.estimatedNote }),
    },
  ]
})

function onFvChange(partial: Record<string, any>) {
  state.updateFvDisposal(partial)
}

function persistFv() {
  state.updateFvDisposal({})
}

function persistWacc() {
  state.updateWaccParams({})
}

function onForecastPeriodChange(v: number | undefined) {
  const n = v ?? 5
  state.updateDcfParams({ forecastPeriod: n })
}

function handleSyncToH14() {
  state.syncToImpairmentCalc()
  ElMessage.success(`已回写「${state.activeGroup.value.name}」至 H1-14`)
}

function handleSyncAll() {
  state.syncAllGroupsToImpairmentCalc()
  ElMessage.success(`已回写全部 ${state.groups.value.length} 个资产组至 H1-14`)
}

function handleForceSync() {
  const result = state.forceSyncFromH15()
  ElMessage.success(`强制回写④完成：更新 ${result.updated}，新建 ${result.created}`)
}

function handleImportIdle() {
  const result = state.importFromIdleAssets()
  if (result.total === 0) {
    ElMessage.warning('H1-4 暂无净值>0 的闲置资产可引入')
    return
  }
  ElMessage.success(`从 H1-4 引入：新增 ${result.added}，已存在刷新 ${result.skipped}（共 ${result.total}）`)
}

async function handleAddGroup() {
  try {
    const { value: name } = await ElMessageBox.prompt('资产组名称', '新增可收回金额测试资产组', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputValue: `资产组-${state.groups.value.length + 1}`,
    })
    if (name) state.addRecoverableGroup(name)
  } catch { /* cancel */ }
}

function handleRemoveGroup() {
  state.removeRecoverableGroup(state.activeGroupId.value)
  ElMessage.success('已删除当前资产组')
}

function handleReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6; padding: 10px 14px; margin-bottom: 12px;
  border-radius: 4px; font-size: 12px;
}
.block-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; font-weight: 600; }
.sub-title { margin: 12px 0 8px; font-size: 13px; color: var(--el-text-color-regular); font-weight: 600; }
.mb-8 { margin-bottom: 8px; }
.mb-12 { margin-bottom: 12px; }
.mt-8 { margin-top: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help; font-variant-numeric: tabular-nums;
}
.primary-amt { color: var(--el-color-primary); font-weight: 700; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.result-bar, .wacc-result-bar, .impairment-hint {
  display: flex; flex-wrap: wrap; gap: 10px 16px; align-items: center;
  padding: 10px 12px; margin-top: 8px;
  background: var(--el-fill-color-light); border-radius: 4px; font-size: 13px;
}
.impairment-hint.has-impairment { background: #fef0f0; }
.final-recoverable {
  display: flex; flex-wrap: wrap; align-items: stretch; gap: 12px;
}
.cmp-item {
  flex: 1; min-width: 140px; padding: 12px 14px;
  background: var(--el-fill-color-lighter); border-radius: 6px; text-align: center;
}
.cmp-item.highlight {
  background: var(--el-color-primary-light-9);
  border: 1px solid var(--el-color-primary-light-5);
}
.cmp-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.cmp-value { font-size: 16px; font-variant-numeric: tabular-nums; font-weight: 600; }
.cmp-vs { display: flex; align-items: center; color: var(--el-text-color-secondary); font-weight: 600; }
.matrix-table { font-size: 12px; }
.matrix-hint { font-size: 11px; color: var(--el-text-color-secondary); margin-top: 8px; }
.axis-caption { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.title-actions { display: flex; gap: 8px; align-items: center; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ol { padding-left: 20px; margin-top: 8px; line-height: 1.7; }
</style>
