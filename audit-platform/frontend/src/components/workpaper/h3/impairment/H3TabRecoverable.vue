<template>
  <div class="h3-tab-recoverable">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表用于测算投资性房地产（成本模式）可收回金额，取公允价值减处置费用与预计未来现金流量现值（DCF）孰高（CAS8）。</p>
        <p>2. 公允价值优先序：销售协议价格 → 活跃市场价格 → 最佳估计；处置费用含法律费、税费、搬运费及使资产可销售状态的直接费用。</p>
        <p>3. DCF 折现率应反映当前市场货币时间价值及资产特定风险，一般为税前利率；现金流口径须与折现率一致。</p>
        <p>4. 可收回金额结果应回写 H3-10 减值测算表，与账面价值比较确定减值损失。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：复核投资性房地产可收回金额测算的准确性，评估公允净额与 DCF 关键假设的合理性，为 H3-10 减值判断提供支持。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:H3-11" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">{{ groups.length }} 个物业</el-tag>
        <el-tag size="small" type="info">预测 {{ assumptions.forecastYears }} 期</el-tag>
        <el-tag v-if="fairValueSourcesAvailable.length" size="small" type="success">H3-8 {{ fairValueSourcesAvailable.length }} 项</el-tag>
        <el-tag v-if="rentalSourcesAvailable.length" size="small" type="success">H3-14 {{ rentalSourcesAvailable.length }} 项</el-tag>
        <el-tag v-if="dcfResult.rateInvalid" size="small" type="danger">折现率≤增长率</el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:H3-8" :context-project-id="projectId" />
        <GtIndexChip value="wp:H3-14" :context-project-id="projectId" />
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-10 减值测算')">← H3-10</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handlePushToH10">回写当前组</el-button>
        <el-button size="small" type="primary" plain :disabled="isReadonly || groups.length <= 1" @click="handlePushAllToH10">回写全部</el-button>
        <el-button size="small" @click="generateAI('H3-11-dcf')">AI</el-button>
      </div>
    </div>

    <div class="methodology-context">
      <p>
        <strong>CAS8：</strong>可收回金额 = MAX(公允价值减处置费用后的净额, 预计未来现金流量现值)。
        WACC(税后) = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)；Ke = Rf + β×(Rm−Rf)。
      </p>
    </div>

    <!-- 测试对象 / 多物业切换 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-header-row">
          <span class="section-title-text">测试对象（多物业/资产组切换）</span>
          <div class="header-actions">
            <el-button size="small" :disabled="isReadonly" @click="handleSyncFromH10">从 H3-10 同步</el-button>
            <el-button size="small" :disabled="isReadonly || !fairValueSourcesAvailable.length" @click="handleImportAllH38">从 H3-8 批量导入</el-button>
            <el-button size="small" :disabled="isReadonly" @click="handleAddGroup">+ 新增物业</el-button>
            <el-button size="small" type="danger" plain :disabled="isReadonly || groups.length <= 1" @click="handleRemoveGroup">删除当前</el-button>
          </div>
        </div>
      </template>
      <el-form :inline="true" size="small" label-width="88px">
        <el-form-item label="切换物业">
          <el-select :model-value="activeGroupId" style="width: 260px" filterable @change="setActiveGroup">
            <el-option
              v-for="g in groups"
              :key="g.groupId"
              :label="`${g.name || '未命名'}（账面 ${fmtNum(g.bookValue)}）`"
              :value="g.groupId"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="物业名称">
          <el-input
            :model-value="activeGroup.name"
            :disabled="isReadonly"
            style="width: 200px"
            placeholder="与 H3-10/H3-8/H3-14 一致"
            @update:model-value="(v: string) => { activeGroup.name = v; activeGroup.fvDisposal.assetName = v }"
            @change="(v: string) => renameActiveGroup(v)"
          />
        </el-form-item>
        <el-form-item label="账面价值">
          <el-input-number v-model="bookValue" :controls="false" :disabled="isReadonly" />
        </el-form-item>
        <el-form-item v-if="activeGroup.sourceH38RowId" label="H3-8">
          <el-tag size="small" type="success">已关联</el-tag>
        </el-form-item>
        <el-form-item v-if="activeGroup.sourceH14RowId" label="H3-14">
          <el-tag size="small" type="success">已关联</el-tag>
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 一、公允价值减处置费用 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title-text">（一）公允价值减去处置费用后的净额</span>
      </template>

      <div class="import-row">
        <el-select
          v-if="fairValueSourcesAvailable.length"
          v-model="selectedH38RowId"
          size="small"
          clearable
          placeholder="选择 H3-8 物业行（可选）"
          style="width: 240px"
        >
          <el-option
            v-for="r in fairValueSourcesAvailable"
            :key="r.rowId"
            :label="`${r.assetName}（评估 ${fmtNum(r.appraisalValue)}）`"
            :value="r.rowId"
          />
        </el-select>
        <el-button size="small" :disabled="isReadonly || !fairValueSourcesAvailable.length" @click="handleImportH38">
          从 H3-8 带入公允价值
        </el-button>
        <el-button size="small" link @click="emit('navigate-sheet', 'H3-8 公允价值复核')">打开 H3-8 →</el-button>
      </div>

      <h4 class="sub-title">1. 公允价值确定（优先：销售协议 → 活跃市场 → 估计）</h4>
      <el-table :data="fvPriceRows" border size="small" class="audit-table mb-12">
        <el-table-column prop="label" label="确定方法" width="160" />
        <el-table-column label="金额" width="150" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.amount"
              :controls="false"
              size="small"
              @change="row.onAmount"
            />
            <span v-else>{{ fmtNum(row.amount) }}</span>
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

      <h4 class="sub-title">2. 处置费用</h4>
      <div class="disposal-grid">
        <div v-for="item in disposalFields" :key="item.key" class="disposal-item">
          <label>{{ item.label }}</label>
          <el-input-number
            v-model="fvDisposal[item.key]"
            :controls="false"
            size="small"
            :disabled="isReadonly"
            @change="onFvChange"
          />
        </div>
      </div>

      <div class="result-bar">
        <span>公允价值（{{ fairValueResolved.source }}）</span>
        <b>{{ fmtNum(fairValueResolved.value) }}</b>
        <span>− 处置费用合计</span>
        <b>{{ fmtNum(disposalTotal) }}</b>
        <span>= 公允净额</span>
        <b class="result-value">{{ fmtNum(fairValueLessDisposal) }}</b>
      </div>

      <el-form-item label="资产名称" label-width="80px" size="small" class="asset-name-row">
        <el-input
          v-model="fvDisposal.assetName"
          :disabled="isReadonly"
          placeholder="与 H3-10 减值测算表资产名称一致"
          style="max-width: 280px"
          @change="onFvChange"
        />
      </el-form-item>
    </el-card>

    <!-- 二、DCF 现值 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="section-title-text">（二）预计未来现金流量的现值</span>
      </template>

      <div class="import-row">
        <el-select
          v-if="rentalSourcesAvailable.length"
          v-model="selectedH14RowId"
          size="small"
          clearable
          placeholder="选择 H3-14 合同行（可选）"
          style="width: 240px"
        >
          <el-option
            v-for="r in rentalSourcesAvailable"
            :key="r.rowId"
            :label="`${r.assetName}（应计 ${fmtNum(r.expectedRent || r.annualRent)}）`"
            :value="r.rowId"
          />
        </el-select>
        <el-button size="small" :disabled="isReadonly || !rentalSourcesAvailable.length" @click="handleImportH14">
          从 H3-14 带入年租金
        </el-button>
        <el-button size="small" link @click="emit('navigate-sheet', 'H3-14 租金收入')">打开 H3-14 →</el-button>
      </div>

      <h4 class="sub-title">1. 未来现金流量预测</h4>
      <div class="assumptions-grid">
        <div class="assumption-item">
          <label>预测期(年)</label>
          <el-input-number v-model="assumptions.forecastYears" :min="3" :max="10" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年租金收入</label>
          <el-input-number v-model="assumptions.annualRent" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>年运营成本</label>
          <el-input-number v-model="assumptions.annualCost" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>预测期末残值</label>
          <el-input-number v-model="assumptions.residualValue" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>永续增长率(%)</label>
          <el-input-number v-model="assumptions.terminalGrowth" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </div>
        <div class="assumption-item">
          <label>增长率确定依据</label>
          <el-input v-model="assumptions.growthRateBasis" size="small" :disabled="isReadonly" placeholder="应≤行业/市场长期增长率" @change="onAssumptionChange" />
        </div>
      </div>

      <el-descriptions :column="3" border size="small" class="growth-benchmarks">
        <el-descriptions-item label="行业长期平均增长率%">
          <el-input-number v-model="assumptions.industryGrowthRate" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </el-descriptions-item>
        <el-descriptions-item label="市场长期增长率%">
          <el-input-number v-model="assumptions.marketGrowthRate" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </el-descriptions-item>
        <el-descriptions-item label="国家/地区长期增长率%">
          <el-input-number v-model="assumptions.countryGrowthRate" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
        </el-descriptions-item>
      </el-descriptions>

      <el-table :data="cashFlowRows" border size="small" class="audit-table" style="margin-top:12px">
        <el-table-column prop="yearLabel" label="年份" width="100" align="center" />
        <el-table-column prop="revenue" label="收入" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.revenue) }}</template>
        </el-table-column>
        <el-table-column prop="cost" label="成本" min-width="100" align="right">
          <template #default="{ row }">{{ fmtNum(row.cost) }}</template>
        </el-table-column>
        <el-table-column label="净现金流" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.netCashFlow) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折现系数" width="90" align="right">
          <template #default="{ row }">{{ row.discountFactor.toFixed(4) }}</template>
        </el-table-column>
        <el-table-column label="现值" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtNum(row.presentValue) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <h4 class="sub-title">2. 折现率 / WACC</h4>
      <div class="wacc-grid">
        <div class="wacc-item"><label>所得税率 t%</label><el-input-number v-model="waccParams.taxRate" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>付息负债 D</label><el-input-number v-model="waccParams.totalDebt" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>权益资本 E</label><el-input-number v-model="waccParams.totalEquity" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>债务成本 Kd%</label><el-input-number v-model="waccParams.costOfDebt" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>无风险利率 Rf%</label><el-input-number v-model="waccParams.riskFreeRate" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>β 系数</label><el-input-number v-model="waccParams.beta" :controls="false" :step="0.1" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item"><label>市场回报 Rm%</label><el-input-number v-model="waccParams.marketReturn" :controls="false" size="small" :disabled="isReadonly" @change="onWaccChange" /></div>
        <div class="wacc-item">
          <label>权益成本 Ke%</label>
          <span class="formula-value">{{ costOfEquity.toFixed(2) }}%</span>
        </div>
      </div>

      <div class="wacc-result-bar">
        <span>WACC(税后)</span><b>{{ waccAfterTax.toFixed(2) }}%</b>
        <span>折现率(税前)</span><b>{{ preTaxDiscountRate.toFixed(2) }}%</b>
        <span>实际折现率</span><b class="result-value">{{ effectiveDiscountRate.toFixed(2) }}%</b>
        <el-radio-group v-model="assumptions.usePreTaxRate" size="small" :disabled="isReadonly" @change="onAssumptionChange">
          <el-radio-button :value="true">税前(CAS8)</el-radio-button>
          <el-radio-button :value="false">税后</el-radio-button>
        </el-radio-group>
        <el-tag v-if="waccAfterTax <= 0" size="small" type="warning">未填 D/E，使用手工折现率</el-tag>
      </div>

      <div v-if="waccAfterTax <= 0" class="manual-rate">
        <label>手工折现率(%)</label>
        <el-input-number v-model="assumptions.discountRate" :controls="false" size="small" :disabled="isReadonly" @change="onAssumptionChange" />
      </div>

      <h4 class="sub-title">3. 现值汇总</h4>
      <el-descriptions :column="4" border size="small">
        <el-descriptions-item label="预测期现值合计">
          <span class="formula-value">{{ fmtNum(dcfResult.pvCashFlows) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="终值（未折现）">
          <span class="formula-value">{{ fmtNum(dcfResult.terminalValue) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="终值现值">
          <span class="formula-value">{{ fmtNum(dcfResult.terminalValueDiscounted) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="使用价值(DCF)">
          <b class="result-value">{{ fmtNum(dcfResult.totalPV) }}</b>
        </el-descriptions-item>
      </el-descriptions>
    </el-card>

    <!-- 三、可收回金额 -->
    <el-card shadow="never" class="section-card recoverable-card">
      <template #header>
        <span class="section-title-text">（三）可收回金额</span>
      </template>
      <div class="final-recoverable">
        <div class="cmp-item">
          <div class="cmp-label">公允净额</div>
          <div class="cmp-value">{{ fmtNum(fairValueLessDisposal) }}</div>
        </div>
        <div class="cmp-vs">vs</div>
        <div class="cmp-item">
          <div class="cmp-label">使用价值(DCF)</div>
          <div class="cmp-value">{{ fmtNum(dcfResult.totalPV) }}</div>
        </div>
        <div class="cmp-vs">→</div>
        <div class="cmp-item highlight">
          <div class="cmp-label">可收回金额（取较高者）</div>
          <div class="cmp-value result-value">{{ fmtNum(recoverableAmount) }}</div>
          <el-tag size="small" type="primary">{{ recoverableSource }}</el-tag>
        </div>
      </div>
      <div class="impairment-hint" :class="{ 'has-impairment': impliedImpairment > 0 }">
        <span>账面价值 {{ fmtNum(bookValue) }}</span>
        <span>− 可收回金额 {{ fmtNum(recoverableAmount) }}</span>
        <span>= 隐含减值</span>
        <b>{{ fmtNum(impliedImpairment) }}</b>
        <el-tag v-if="impliedImpairment > 0" size="small" type="danger">存在减值</el-tag>
        <el-tag v-else size="small" type="success">无需减值</el-tag>
      </div>
    </el-card>

    <!-- 敏感性分析 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span>四、敏感性分析</span>
      </template>

      <h4 class="sub-title">（1）可收回金额矩阵（折现率 ±1% × 增长率 ±1%）</h4>
      <el-table :data="sensitivityRows" border size="small" class="audit-table mb-12">
        <el-table-column prop="label" label="折现率 \\ 增长率" width="120" />
        <el-table-column v-for="col in sensitivityCols" :key="col" :label="col + '%'" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="{ 'warn-cell': (row[col] as number) < bookValue && bookValue > 0 }">
              {{ fmtNum(row[col] as number) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
      <div class="matrix-hint mb-12">橙色 = 可收回金额 &lt; 账面价值（该情景下存在减值）</div>

      <h4 class="sub-title">（2）终值单独敏感轴（固定另一参数，观察终值现值）</h4>
      <el-row :gutter="16">
        <el-col :span="12">
          <div class="axis-caption">折现率轴（g 固定 {{ assumptions.terminalGrowth }}%）</div>
          <el-table :data="terminalSensitivityByRate" border size="small" class="audit-table">
            <el-table-column prop="paramLabel" label="折现率" min-width="110" />
            <el-table-column label="终值（未折现）" width="120" align="right">
              <template #default="{ row }">
                <span :class="{ 'warn-cell': row.invalid }">{{ row.invalid ? '无效' : fmtNum(row.terminalValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="终值现值" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-value">{{ row.invalid ? '-' : fmtNum(row.terminalValueDiscounted) }}</span>
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
          <div class="axis-caption">增长率轴（折现率固定 {{ effectiveDiscountRate.toFixed(2) }}%）</div>
          <el-table :data="terminalSensitivityByGrowth" border size="small" class="audit-table">
            <el-table-column prop="paramLabel" label="永续增长率 g" min-width="120" />
            <el-table-column label="终值（未折现）" width="120" align="right">
              <template #default="{ row }">
                <span :class="{ 'warn-cell': row.invalid }">{{ row.invalid ? '无效' : fmtNum(row.terminalValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="终值现值" width="120" align="right">
              <template #default="{ row }">
                <span class="formula-value">{{ row.invalid ? '-' : fmtNum(row.terminalValueDiscounted) }}</span>
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
      <div class="matrix-hint">终值占比过高时，需加强永续增长率 g 与 H3-8/H3-14 外部基准的复核。</div>
    </el-card>

    <!-- 审计过程提示 -->
    <details class="audit-process-details">
      <summary>审计过程提示</summary>
      <ol class="audit-process-list">
        <li>获取减值准备明细表，复核加计正确，并与总账核对；</li>
        <li>检查减值准备计提的批准程序，获取估值报告，评价计提依据是否充分、会计处理是否正确；</li>
        <li>检查已计提减值准备的资产处置时，相关减值准备是否已正确结转；</li>
        <li>重新执行减值测试，将预期结果与账面计提比较，分析差异；</li>
        <li>检查本期减值准备变动是否合理。</li>
      </ol>
    </details>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-11')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-11')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：公允价值/处置费用依据、DCF 关键假设（折现率/增长率/租金）来源与合理性、敏感性分析结论、可收回金额确定。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、假设合理、测算准确。B、除下列事项外未见异常。C、关键假设不合理，需重新评估。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabRecoverable.vue — H3-11 可收回金额测试表
 * 对齐 Excel：公允净额 + DCF/WACC + MAX + 敏感性 + 回写 H3-10
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { useH3Impairment } from '../../composables/useH3Impairment'
import { useH3FormData } from '../../composables/useH3FormData'
import GtIndexChip from '../../GtIndexChip.vue'
import type { FairValueDisposal } from '../../composables/useH3Impairment'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost') as any,
})

const {
  groups, activeGroupId, activeGroup, bookValue,
  assumptions, fvDisposal, waccParams,
  fairValueSourcesAvailable, rentalSourcesAvailable,
  cashFlowRows, dcfResult, recoverableAmount, recoverableSource, impliedImpairment,
  costOfEquity, waccAfterTax, preTaxDiscountRate, effectiveDiscountRate,
  fairValueResolved, disposalTotal, fairValueLessDisposal,
  sensitivityRows, sensitivityCols,
  terminalSensitivityByRate, terminalSensitivityByGrowth,
  setActiveGroup, addRecoverableGroup, removeRecoverableGroup, renameActiveGroup,
  syncGroupsFromH10, importFairValueFromH38, importRentalFromH14, importAllGroupsFromH38,
  updateAssumptions, updateFvDisposal, updateWaccParams,
  pushRecoverableToH10, pushAllGroupsToH10,
} = useH3Impairment({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  getValue, setValue, saveImmediate,
})

const NOTE_KEY = 'H3-11-audit-note'
const CONCLUSION_KEY = 'H3-11-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
const selectedH38RowId = ref<string>('')
const selectedH14RowId = ref<string>('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

const disposalFields: { key: keyof FairValueDisposal; label: string }[] = [
  { key: 'legalFees', label: '法律费用' },
  { key: 'relatedTaxes', label: '相关税费' },
  { key: 'transportCosts', label: '搬运费' },
  { key: 'directCosts', label: '直接费用' },
  { key: 'otherCosts', label: '其他' },
]

const fvPriceRows = computed(() => {
  const fv = fvDisposal.value
  const resolved = fairValueResolved.value
  return [
    {
      label: '销售协议价格',
      amount: fv.salesAgreementPrice,
      note: fv.salesAgreementNote,
      selected: resolved.source === '销售协议价格',
      onAmount: (v: number | undefined) => { fv.salesAgreementPrice = v ?? 0; onFvChange() },
      onNoteInput: (v: string) => { fv.salesAgreementNote = v },
      onNote: () => onFvChange(),
    },
    {
      label: '活跃市场价格',
      amount: fv.activeMarketPrice,
      note: fv.activeMarketNote,
      selected: resolved.source === '活跃市场价格',
      onAmount: (v: number | undefined) => { fv.activeMarketPrice = v ?? 0; onFvChange() },
      onNoteInput: (v: string) => { fv.activeMarketNote = v },
      onNote: () => onFvChange(),
    },
    {
      label: '估计价格',
      amount: fv.estimatedPrice,
      note: fv.estimatedNote,
      selected: resolved.source === '估计价格',
      onAmount: (v: number | undefined) => { fv.estimatedPrice = v ?? 0; onFvChange() },
      onNoteInput: (v: string) => { fv.estimatedNote = v },
      onNote: () => onFvChange(),
    },
  ]
})

function onAssumptionChange() { updateAssumptions() }
function onFvChange() { updateFvDisposal() }
function onWaccChange() { updateWaccParams() }

function handlePushToH10() {
  const result = pushRecoverableToH10()
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
  if (result.ok) emit('navigate-sheet', 'H3-10 减值测算')
}

function handlePushAllToH10() {
  const result = pushAllGroupsToH10()
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
  if (result.ok) emit('navigate-sheet', 'H3-10 减值测算')
}

function handleAddGroup() {
  addRecoverableGroup()
  ElMessage.success('已新增物业组')
}

function handleRemoveGroup() {
  removeRecoverableGroup()
  ElMessage.success('已删除当前物业组')
}

function handleSyncFromH10() {
  const { added, updated } = syncGroupsFromH10()
  ElMessage.success(`已从 H3-10 同步：新增 ${added}，更新 ${updated}`)
}

function handleImportH38() {
  const result = importFairValueFromH38(selectedH38RowId.value || undefined)
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
}

function handleImportH14() {
  const result = importRentalFromH14(selectedH14RowId.value || undefined)
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
}

function handleImportAllH38() {
  const result = importAllGroupsFromH38()
  ElMessage[result.ok ? 'success' : 'warning'](result.message)
}

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}

function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-recoverable { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.methodology-context { margin-bottom: 12px; padding: 10px 14px; border-left: 3px solid #e6a23c; background: #fdf6ec; border-radius: 4px; font-size: 12px; color: #606266; line-height: 1.6; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }
.section-card { margin-bottom: 16px; }
.section-title-text { font-weight: 500; }
.sub-title { margin: 12px 0 8px; font-size: 13px; font-weight: 500; color: var(--el-text-color-regular); }
.mb-12 { margin-bottom: 12px; }
.assumptions-grid, .disposal-grid, .wacc-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin-bottom: 12px; }
.assumption-item label, .disposal-item label, .wacc-item label { display: block; font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.growth-benchmarks { margin-top: 8px; margin-bottom: 12px; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); }
.result-bar, .wacc-result-bar { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 12px; padding: 10px 14px; background: var(--el-fill-color-lighter); border-radius: 4px; font-weight: 500; }
.wacc-result-bar { margin-top: 8px; }
.result-value { font-size: 16px; color: var(--el-color-primary); }
.manual-rate { display: flex; align-items: center; gap: 8px; margin-top: 8px; font-size: 12px; }
.asset-name-row { margin-top: 12px; margin-bottom: 0; }
.final-recoverable { display: flex; align-items: center; justify-content: center; flex-wrap: wrap; gap: 16px; padding: 16px; }
.cmp-item { text-align: center; min-width: 120px; }
.cmp-item.highlight { background: var(--el-color-primary-light-9); padding: 12px 20px; border-radius: 8px; }
.cmp-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.cmp-value { font-size: 18px; font-weight: 600; }
.cmp-vs { font-size: 14px; color: var(--el-text-color-secondary); }
.audit-process-details { margin: 16px 0; border-left: 3px solid #909399; background: #f4f4f5; border-radius: 4px; padding: 8px 12px; }
.audit-process-details summary { cursor: pointer; font-weight: 500; color: #606266; }
.audit-process-list { margin: 8px 0 0 20px; font-size: 12px; color: #606266; line-height: 1.8; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
.section-header-row { display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 8px; }
.header-actions { display: flex; gap: 6px; flex-wrap: wrap; }
.import-row { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.impairment-hint { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-top: 16px; padding: 10px 14px; background: var(--el-fill-color-lighter); border-radius: 4px; }
.impairment-hint.has-impairment { background: var(--el-color-danger-light-9); }
.matrix-hint { font-size: 12px; color: var(--el-text-color-secondary); margin-top: 6px; }
.axis-caption { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.warn-cell { color: var(--el-color-warning); font-weight: 500; }
</style>
