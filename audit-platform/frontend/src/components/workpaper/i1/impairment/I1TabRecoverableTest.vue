<template>
  <div class="i1-tab-recoverable-test">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实无形资产可收回金额是否按 CAS8 以公允净额与预计未来现金流量现值孰高确定；复核公允取值层次、处置费用、现金流假设及 WACC/折现率；结果联动 I1-12。"
    />

    <div class="methodology-block">
      <p>
        <strong>CAS8：</strong>可收回金额 = MAX(公允价值减处置费用后的净额, 预计未来现金流量现值)。
        折现率应为反映当前市场货币时间价值和资产特定风险的<strong>税前利率</strong>；现金流与折现率口径须一致。
        公允取值优先：销售协议 → 活跃市场 → 估计；处置费用含法律/税费/搬运等直接费用。
        WACC(税后) = E/(D+E)×Ke + D/(D+E)×Kd×(1−t)；Ke = Rf + β×(Rm−Rf)；税前折现率 ≈ WACC税后/(1−t)。
      </p>
    </div>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-13" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ recoverableRows.length }} 项</el-tag>
        <el-tag v-if="missingRecoverableRows.length" size="small" type="danger">
          须测试待测 {{ missingRecoverableRows.length }}
        </el-tag>
        <el-tag v-if="staleSyncCount" size="small" type="danger">
          与 I1-12 不一致 {{ staleSyncCount }}
        </el-tag>
        <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'I1-12')">← I1-12</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" size="small" @click="handleSeedFromI12">从 I1-12 建组</el-button>
        <el-button v-if="!isReadonly" size="small" type="warning" @click="handleLinkToI12">联动回写 I1-12</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleAddRow">+ 新增测算</el-button>
        <el-button size="small" circle @click="openReview('I1-13')">💬</el-button>
      </div>
    </div>

    <el-alert
      v-if="needTestGatePending"
      type="warning"
      :closable="false"
      show-icon
      class="mb-12"
      :title="gateAlertTitle"
      :description="gateAlertDesc"
    />

    <!-- 与 I1-12 回写一致性 -->
    <el-card v-if="syncChecks.length" shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>与 I1-12 回写一致性</span>
          <el-tag v-if="staleSyncCount" size="small" type="danger">{{ staleSyncCount }} 项待处理</el-tag>
          <el-tag v-else size="small" type="success">全部一致/无需测</el-tag>
        </div>
      </template>
      <el-table :data="syncChecks" border size="small">
        <el-table-column prop="name" label="资产名称" min-width="120" />
        <el-table-column label="状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="row.status === 'synced' ? 'success' : row.status === 'no-test' ? 'info' : 'danger'"
            >
              {{ syncStatusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="I1-12⑤" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.i12Recoverable) }}</template>
        </el-table-column>
        <el-table-column label="I1-13可收回" width="110" align="right">
          <template #default="{ row }">{{ fmtAmt(row.i13Recoverable) }}</template>
        </el-table-column>
        <el-table-column prop="message" label="说明" min-width="200" />
      </el-table>
    </el-card>

    <el-empty v-if="recoverableRows.length === 0" description="暂无可收回金额测试：可从 I1-12 建组或新增测算" :image-size="60" />

    <div v-for="(row, rowIdx) in recoverableRows" :key="row.rowId" class="asset-block">
      <!-- 测试对象 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header">
            <span class="section-title">可收回金额测试 · {{ row.name || '未命名' }}</span>
            <div class="section-header-actions">
              <el-tag v-if="row.rateInvalid" size="small" type="danger">折现率≤增长率</el-tag>
              <el-tag v-if="row.waccAfterTax > 0" size="small" type="success">WACC</el-tag>
              <el-tag v-else size="small" type="info">手工折现率</el-tag>
              <el-button v-if="!isReadonly" size="small" type="danger" link @click="handleRemoveRow(rowIdx)">删除</el-button>
            </div>
          </div>
        </template>
        <el-form :inline="true" size="small" label-width="80px">
          <el-form-item label="资产名称">
            <el-input
              v-if="!isReadonly"
              v-model="row.name"
              style="width: 180px"
              placeholder="与 I1-12 同名匹配"
              @blur="persistRow(rowIdx)"
            />
            <strong v-else>{{ row.name || '-' }}</strong>
          </el-form-item>
          <el-form-item label="账面净值">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.bookValue"
              :controls="false"
              @change="(v: number | undefined) => updateRecoverableField(rowIdx, 'bookValue', v ?? 0)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </el-form-item>
        </el-form>
      </el-card>

      <!-- 一、公允净额 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>一、公允价值减去处置费用后的净额</span></div>
        </template>

        <h4 class="sub-title">（1）公允价值确定（优先：销售协议 → 活跃市场 → 估计）</h4>
        <el-table :data="fvPriceRows(row, rowIdx)" border size="small" class="mb-12">
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
            <el-col :span="8">
              <el-form-item label="法律费用">
                <el-input-number
                  :model-value="row.fvDisposal.legalFees"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateFvField(rowIdx, 'legalFees', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="相关税费">
                <el-input-number
                  :model-value="row.fvDisposal.relatedTaxes"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateFvField(rowIdx, 'relatedTaxes', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="搬运费">
                <el-input-number
                  :model-value="row.fvDisposal.transportCosts"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateFvField(rowIdx, 'transportCosts', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="直接费用">
                <el-input-number
                  :model-value="row.fvDisposal.directCosts"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateFvField(rowIdx, 'directCosts', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="其他费用">
                <el-input-number
                  :model-value="row.fvDisposal.otherCosts"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateFvField(rowIdx, 'otherCosts', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="处置费用合计">
                <span class="formula-cell">{{ fmtAmt(row.disposalTotal) }}</span>
              </el-form-item>
            </el-col>
          </el-row>
        </el-form>

        <div class="result-bar">
          <span>公允价值（{{ row.fairValueSource }}）</span>
          <b class="amt-cell">{{ fmtAmt(row.fairValueLessDisposal + row.disposalTotal) }}</b>
          <span>− 处置费用</span>
          <b class="amt-cell">{{ fmtAmt(row.disposalTotal) }}</b>
          <span>= 公允净额</span>
          <b class="highlight">{{ fmtAmt(row.fairValueLessDisposal) }}</b>
        </div>

        <el-input
          v-if="!isReadonly"
          :model-value="row.fvDisposal.auditNote"
          type="textarea"
          :autosize="{ minRows: 2 }"
          placeholder="审计说明：公允价值及处置费用取值依据；若无法可靠确定公允净额请说明原因（可仅测使用价值）..."
          class="mt-8"
          @change="(v: string) => updateFvField(rowIdx, 'auditNote', v)"
        />
        <p v-else class="readonly-note">{{ row.fvDisposal.auditNote || '' }}</p>
      </el-card>

      <!-- 二、DCF + WACC -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header"><span>二、预计未来现金流量的现值（使用价值）</span></div>
        </template>

        <h4 class="sub-title">（1）未来现金流量预测（一般不超过5年）</h4>
        <el-form :inline="true" size="small" class="mb-8">
          <el-form-item label="永续增长率 g">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.growthRate"
              :step="0.005"
              :precision="4"
              :min="-0.1"
              :max="0.5"
              size="small"
              @change="(v: number | undefined) => updateRecoverableField(rowIdx, 'growthRate', v ?? 0)"
            />
            <span v-else>{{ (row.growthRate * 100).toFixed(2) }}%</span>
          </el-form-item>
          <el-form-item label="增长率依据">
            <el-input
              v-if="!isReadonly"
              :model-value="row.growthRateBasis"
              size="small"
              style="width: 260px"
              placeholder="应≤行业/市场长期增长率"
              @change="(v: string) => updateRecoverableField(rowIdx, 'growthRateBasis', v)"
            />
            <span v-else>{{ row.growthRateBasis || '-' }}</span>
          </el-form-item>
        </el-form>

        <el-table :data="buildCashFlowTableData(row)" border size="small" class="mb-12">
          <el-table-column prop="label" label="年度" width="90" align="center" />
          <el-table-column label="预测净现金流" min-width="140" align="right">
            <template #default="{ row: cfRow }">
              <el-input-number
                v-if="!isReadonly"
                :model-value="cfRow.cashFlow"
                :controls="false"
                size="small"
                class="amt-input"
                @change="(v: number | undefined) => updateCashFlow(rowIdx, cfRow.yearIndex, v ?? 0)"
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

        <h4 class="sub-title">（2）折现率 / 加权平均资金成本（WACC）</h4>
        <el-form label-width="130px" size="small">
          <el-row :gutter="12">
            <el-col :span="8">
              <el-form-item label="所得税率 t%">
                <el-input-number
                  :model-value="row.waccParams.taxRate"
                  :controls="false"
                  :min="0"
                  :max="100"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'taxRate', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="付息负债 D">
                <el-input-number
                  :model-value="row.waccParams.totalDebt"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'totalDebt', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="权益资本 E">
                <el-input-number
                  :model-value="row.waccParams.totalEquity"
                  :controls="false"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'totalEquity', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="债务成本 Kd%">
                <el-input-number
                  :model-value="row.waccParams.costOfDebt"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'costOfDebt', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="无风险利率 Rf%">
                <el-input-number
                  :model-value="row.waccParams.riskFreeRate"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'riskFreeRate', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="β系数">
                <el-input-number
                  :model-value="row.waccParams.beta"
                  :controls="false"
                  :precision="3"
                  :step="0.1"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'beta', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="市场回报 Rm%">
                <el-input-number
                  :model-value="row.waccParams.marketReturn"
                  :controls="false"
                  :precision="2"
                  :disabled="isReadonly"
                  @change="(v: number | undefined) => updateWaccField(rowIdx, 'marketReturn', v ?? 0)"
                />
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="权益成本 Ke%">
                <span class="formula-cell" title="Ke = Rf + β×(Rm−Rf)">{{ (row.costOfEquity || 0).toFixed(2) }}%</span>
              </el-form-item>
            </el-col>
            <el-col :span="8">
              <el-form-item label="折现口径">
                <el-radio-group
                  :model-value="row.usePreTaxRate"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: boolean | string | number) => updateRecoverableField(rowIdx, 'usePreTaxRate', v === true || v === 'true')"
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
          <b>{{ (row.waccAfterTax || 0).toFixed(2) }}%</b>
          <span title="税前折现率 ≈ WACC税后/(1−t)">折现率(税前)</span>
          <b>{{ (row.preTaxDiscountRate || 0).toFixed(2) }}%</b>
          <span>实际折现率</span>
          <b class="highlight">{{ ((row.effectiveDiscountRate || 0) * 100).toFixed(2) }}%</b>
          <el-tag v-if="row.rateInvalid" type="danger" size="small">折现率≤增长率，终值无效</el-tag>
          <el-tag v-if="!(row.waccAfterTax > 0)" type="warning" size="small">未填 D/E，使用手工折现率</el-tag>
        </div>

        <el-alert
          v-for="(w, wi) in getWaccWarnings(rowIdx)"
          :key="`wacc-${rowIdx}-${wi}`"
          type="warning"
          :closable="false"
          show-icon
          class="mt-8"
          :title="w"
        />

        <el-form v-if="!(row.waccAfterTax > 0)" :inline="true" size="small" class="mt-8">
          <el-form-item label="手工折现率">
            <el-input-number
              v-if="!isReadonly"
              :model-value="row.discountRate"
              :step="0.005"
              :precision="4"
              :min="0.001"
              :max="1"
              size="small"
              @change="(v: number | undefined) => updateRecoverableField(rowIdx, 'discountRate', v ?? 0.08)"
            />
            <span v-else>{{ (row.discountRate * 100).toFixed(2) }}%</span>
          </el-form-item>
        </el-form>

        <h4 class="sub-title">（3）现值汇总</h4>
        <el-descriptions :column="4" border size="small">
          <el-descriptions-item label="预测期现值合计">
            <span class="formula-cell">{{ fmtAmt(row.pvForecast) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="终值（未折现）">
            <span class="formula-cell" title="TV = CFn×(1+g)/(r−g)">{{ fmtAmt(row.terminalValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="终值现值">
            <span class="formula-cell">{{ fmtAmt(row.discountedTerminalValue) }}</span>
          </el-descriptions-item>
          <el-descriptions-item label="使用价值(DCF)">
            <b class="highlight">{{ fmtAmt(row.valueInUse) }}</b>
          </el-descriptions-item>
        </el-descriptions>
      </el-card>

      <!-- 三、可收回金额 -->
      <el-card shadow="never" class="block-card recoverable-card">
        <template #header>
          <div class="section-header"><span>三、可收回金额</span></div>
        </template>
        <div class="final-recoverable">
          <div class="cmp-item">
            <div class="cmp-label">公允净额</div>
            <div class="cmp-value">{{ fmtAmt(row.fairValueLessDisposal) }}</div>
          </div>
          <div class="cmp-vs">vs</div>
          <div class="cmp-item">
            <div class="cmp-label">使用价值(DCF)</div>
            <div class="cmp-value">{{ fmtAmt(row.valueInUse) }}</div>
          </div>
          <div class="cmp-vs">→</div>
          <div class="cmp-item highlight-box">
            <div class="cmp-label">可收回金额（取较高者）</div>
            <div class="cmp-value highlight">{{ fmtAmt(row.recoverableAmount) }}</div>
            <el-tag size="small" type="primary">{{ row.recoverableSource || '未测算' }}</el-tag>
          </div>
        </div>
        <div class="impairment-hint" :class="{ 'has-impairment': impliedImpairment(row) > 0 }">
          <span>账面净值 {{ fmtAmt(row.bookValue) }}</span>
          <span>− 可收回金额 {{ fmtAmt(row.recoverableAmount) }}</span>
          <span>= 应计提减值</span>
          <b>{{ fmtAmt(impliedImpairment(row)) }}</b>
          <el-tag v-if="impliedImpairment(row) > 0" type="danger" size="small">存在减值</el-tag>
          <el-tag v-else type="success" size="small">无需减值</el-tag>
          <el-tag type="warning" size="small">减值一经确认不得转回</el-tag>
        </div>
      </el-card>

      <!-- 四、敏感性 -->
      <el-card shadow="never" class="block-card">
        <template #header>
          <div class="section-header">
            <span>四、敏感性分析（折现率 ±1% / 增长率 ±0.5%）</span>
            <el-button size="small" type="primary" link @click="toggleSensitivity(rowIdx)">
              {{ sensitivityVisible[rowIdx] ? '收起' : '展开' }}
            </el-button>
          </div>
        </template>
        <el-table
          v-if="sensitivityVisible[rowIdx]"
          :data="getSensitivityData(rowIdx)"
          border
          size="small"
        >
          <el-table-column prop="scenario" label="情景" min-width="180" />
          <el-table-column label="折现率" width="100" align="center">
            <template #default="{ row: sRow }">{{ (sRow.discountRate * 100).toFixed(2) }}%</template>
          </el-table-column>
          <el-table-column label="增长率" width="100" align="center">
            <template #default="{ row: sRow }">{{ (sRow.growthRate * 100).toFixed(2) }}%</template>
          </el-table-column>
          <el-table-column label="使用价值" min-width="120" align="right">
            <template #default="{ row: sRow }">
              <span class="amt-cell">{{ fmtAmt(sRow.valueInUse) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="可收回金额" min-width="120" align="right">
            <template #default="{ row: sRow }">
              <span
                class="amt-cell"
                :class="{ 'error-amount': row.bookValue > 0 && sRow.recoverableAmount < row.bookValue }"
              >
                {{ fmtAmt(sRow.recoverableAmount) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column label="与基准差额" min-width="110" align="right">
            <template #default="{ row: sRow }">
              <span :class="['amt-cell', { 'error-amount': sRow.differenceFromBase < 0 }]">
                {{ fmtAmt(sRow.differenceFromBase) }}
              </span>
            </template>
          </el-table-column>
        </el-table>
        <p v-if="sensitivityVisible[rowIdx]" class="sensitivity-note">
          红色 = 该情景下可收回金额低于账面净值，或相对基准下降。
        </p>
      </el-card>

      <el-divider v-if="rowIdx < recoverableRows.length - 1" />
    </div>

    <!-- 五、审计说明 / 结论（全局，覆盖全部测算项） -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><div class="section-header"><span>五、审计说明</span></div></template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：公允取值层次或无法可靠确定的理由、现金流预测来源（预算/管理层批准）、WACC参数取值、与管理层沟通及复核情况等。"
        @blur="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>六、审计结论</span>
          <el-button
            v-if="!isReadonly && recoverableRows.length"
            size="small"
            plain
            @click="fillConclusionDraft"
          >
            填入结论模板
          </el-button>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="可收回金额测试结论（如：经测算可收回金额为…，高于/低于账面净值…，减值准备计提是否充分；联动 I1-12 / I1-11）"
        @blur="saveAuditConclusion"
      />
    </el-card>

    <div class="jump-targets">
      <span class="jump-label">跨表联动：</span>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'I1-12')">I1-12 减值测算</el-button>
      <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'I1-11')">I1-11 摊销（含减值）</el-button>
      <GtIndexChip value="wp:K11" :context-project-id="projectId" />
    </div>

    <details class="edit-tips">
      <summary>编制提示（CAS8 / 对齐 Excel I1-13）</summary>
      <ul>
        <li>「从 I1-12 建组」仅拉取须测试且有账面的行；测算完成后「联动回写 I1-12」写入③公允净额、④DCF 现值并重算⑤⑥⑧⑨</li>
        <li>可收回金额 = MAX(公允净额, 使用价值)；折现率默认税前；现金流与折现率口径须一致</li>
        <li>公允取值优先：销售协议 → 活跃市场 → 估计；处置费用为直接费用合计</li>
        <li>敏感性：折现率±1%、增长率±0.5%；结论草稿可一键填入审计结论</li>
      </ul>
      <ol>
        <li>可收回金额 = MAX(公允价值−处置费用净额, 预计未来现金流量现值)。源模板 N23=MAX(N14,N20)。</li>
        <li>公允净额 N = IF(销售协议&gt;0,协议,IF(活跃市场&gt;0,市场,估计)) − Σ处置费用（法律/税费/搬运/直接/其他）。</li>
        <li>DCF：PV = Σ(CF_t×1/(1+r)^t) + TV/(1+r)^n；TV = CF_n×(1+g)/(r−g)，要求 r&gt;g。</li>
        <li>折现率优先 WACC 税前；未填 D/E 时回退手工折现率。Rm、Kd、Rf 均按百分比填写（如市场回报 8 表示 8%）。</li>
        <li>永续增长率通常为 0 或负；大于 0 须填写依据，且不应超过行业/经济体长期增长率。</li>
        <li>「从 I1-12 建组」按须测试且有账面的行自动建测算项；「联动回写 I1-12」按同名写入③公允净额、④DCF 现值并重算⑤⑥⑧⑨。</li>
        <li>无形资产减值损失一经确认，以后期间不得转回。</li>
      </ol>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabRecoverableTest.vue — I1-13 可收回金额测试
 * 对齐 Excel：一公允净额 / 二 DCF+WACC / 三 MAX / 敏感性 / 说明结论
 * Spec: .kiro/specs/i1-intangible-assets/ | Requirements: 13.1-13.5
 */
import { ref, reactive, inject, toRef, computed, onMounted, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { useI1Impairment, DCF_FORECAST_YEARS } from '../../composables/useI1Impairment'
import type { I1RecoverableTestRow, SensitivityResult } from '../../composables/useI1Impairment'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
  (e: 'save', itemId?: string, value?: any): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  recoverableRows,
  addRecoverableRow,
  removeRecoverableRow,
  updateCashFlow,
  updateRecoverableField,
  updateFvField,
  updateWaccField,
  persistRecoverableRow,
  linkRecoverableToImpairment,
  seedFromImpairment,
  buildConclusionDraft,
  calcSensitivity,
  syncChecks,
  staleSyncCount,
  missingRecoverableRows,
  needTestGatePending,
  getWaccWarnings,
} = useI1Impairment(
  toRef(props, 'wpId'),
  allResponsesRef as any,
  {
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const gateAlertTitle = computed(() => {
  const miss = missingRecoverableRows.value.length
  const stale = staleSyncCount.value
  if (miss && stale) return `须测试闸门：${miss} 项待测算，另有 ${stale} 项与 I1-12 不一致`
  if (miss) return `须测试闸门：${miss} 项寿命不确定/有迹象但尚未完成可收回测算`
  return `与 I1-12 回写不一致 ${stale} 项，请联动回写`
})

const gateAlertDesc = computed(() => {
  const names = missingRecoverableRows.value.map((r) => r.name).filter(Boolean).slice(0, 5)
  const parts: string[] = []
  if (names.length) parts.push(`待测资产：${names.join('、')}${missingRecoverableRows.value.length > 5 ? '…' : ''}`)
  parts.push('可点「从 I1-12 建组」后完成公允/DCF，再「联动回写 I1-12」。')
  return parts.join(' ')
})

function syncStatusLabel(status: string): string {
  switch (status) {
    case 'synced': return '一致'
    case 'stale': return '不一致'
    case 'missing-i13': return '缺测算'
    case 'no-test': return '无须测'
    default: return status
  }
}

const auditNote = ref('')
const auditConclusion = ref('')
const sensitivityVisible = reactive<Record<number, boolean>>({})

const NOTE_KEY = 'I1-13-audit-note'
const CONCLUSION_KEY = 'I1-13-audit-conclusion'

function loadAuditText(): void {
  const n = props.allResponses.get(NOTE_KEY)
  if (n) auditNote.value = (n.remark ?? n.conclusion ?? '') as string
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c) auditConclusion.value = (c.remark ?? c.conclusion ?? '') as string
}

onMounted(loadAuditText)
watch(() => props.allResponses, loadAuditText, { deep: true })

function saveAuditNote(): void {
  if (props.isReadonly) return
  emit('save', NOTE_KEY, auditNote.value)
}

function saveAuditConclusion(): void {
  if (props.isReadonly) return
  emit('save', CONCLUSION_KEY, auditConclusion.value)
}

function persistRow(rowIdx: number) {
  persistRecoverableRow(rowIdx)
}

interface CashFlowTableRow {
  label: string
  yearIndex: number
  cashFlow: number
  discountFactor: number
  discountedCF: number
}

function buildCashFlowTableData(row: I1RecoverableTestRow): CashFlowTableRow[] {
  const result: CashFlowTableRow[] = []
  for (let i = 0; i < DCF_FORECAST_YEARS; i++) {
    result.push({
      label: `第${i + 1}年`,
      yearIndex: i,
      cashFlow: row.cashFlows[i] ?? 0,
      discountFactor: row.discountFactors?.[i] ?? 0,
      discountedCF: row.discountedCashFlows?.[i] ?? 0,
    })
  }
  return result
}

function fvPriceRows(row: I1RecoverableTestRow, rowIdx: number) {
  const fv = row.fvDisposal
  const source = row.fairValueSource
  return [
    {
      label: '销售协议价格',
      amount: fv.salesAgreementPrice,
      note: fv.salesAgreementNote,
      selected: source === '销售协议价格',
      onAmount: (v: number | undefined) => updateFvField(rowIdx, 'salesAgreementPrice', v ?? 0),
      onNote: (v: string) => updateFvField(rowIdx, 'salesAgreementNote', v),
    },
    {
      label: '活跃市场价格',
      amount: fv.activeMarketPrice,
      note: fv.activeMarketNote,
      selected: source === '活跃市场价格',
      onAmount: (v: number | undefined) => updateFvField(rowIdx, 'activeMarketPrice', v ?? 0),
      onNote: (v: string) => updateFvField(rowIdx, 'activeMarketNote', v),
    },
    {
      label: '估计价格',
      amount: fv.estimatedPrice,
      note: fv.estimatedNote,
      selected: source === '估计价格',
      onAmount: (v: number | undefined) => updateFvField(rowIdx, 'estimatedPrice', v ?? 0),
      onNote: (v: string) => updateFvField(rowIdx, 'estimatedNote', v),
    },
  ]
}

function impliedImpairment(row: I1RecoverableTestRow): number {
  return Math.max((row.bookValue || 0) - (row.recoverableAmount || 0), 0)
}

function toggleSensitivity(rowIdx: number) {
  sensitivityVisible[rowIdx] = !sensitivityVisible[rowIdx]
}

function getSensitivityData(rowIdx: number): SensitivityResult[] {
  return calcSensitivity(rowIdx)
}

async function handleAddRow() {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入资产名称（建议与 I1-12 同名）', '新增可收回测算', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (name) {
      addRecoverableRow({
        name: name.trim(),
        discountRate: 0.08,
        growthRate: 0.02,
      })
    }
  } catch { /* cancelled */ }
}

function handleRemoveRow(index: number) {
  removeRecoverableRow(index)
}

function handleLinkToI12() {
  const r = linkRecoverableToImpairment()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleSeedFromI12() {
  const r = seedFromImpairment()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

function fillConclusionDraft() {
  const parts = recoverableRows.value.map((_, i) => buildConclusionDraft(i)).filter(Boolean)
  auditConclusion.value = parts.join('\n')
  saveAuditConclusion()
  ElMessage.success('已填入结论模板')
}

function openReview(id: string) {
  openReviewDialog(id)
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-recoverable-test { padding: 16px; font-size: var(--wp-font-size, 13px); }

.methodology-block {
  border-left: 4px solid var(--el-color-warning);
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 12px;
  font-size: 12px;
  color: var(--el-text-color-regular);
  line-height: 1.6;
}

.objective-alert { margin-bottom: 12px; }

.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left, .toolbar-right { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.nav-chip { cursor: pointer; }

.asset-block { margin-bottom: 8px; }
.block-card { margin-bottom: 12px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-title { font-weight: 600; }
.section-header-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }

.sub-title {
  margin: 8px 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--el-text-color-primary);
}

.mb-8 { margin-bottom: 8px; }
.mb-12 { margin-bottom: 12px; }
.mt-8 { margin-top: 8px; }

.result-bar, .wacc-result-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px 12px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
}
.highlight { color: var(--el-color-primary); font-weight: 700; }

.recoverable-card .final-recoverable {
  display: flex;
  align-items: stretch;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.cmp-item {
  flex: 1;
  min-width: 140px;
  padding: 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  text-align: center;
}
.cmp-label { font-size: 12px; color: var(--el-text-color-secondary); margin-bottom: 6px; }
.cmp-value { font-size: 18px; font-weight: 600; font-variant-numeric: tabular-nums; }
.cmp-vs { display: flex; align-items: center; color: var(--el-text-color-secondary); font-weight: 600; }
.highlight-box { border: 1px solid var(--el-color-primary-light-5); background: #fff; }

.impairment-hint {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
  padding: 10px 12px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  font-size: 13px;
}
.impairment-hint.has-impairment { background: #fef0f0; }

.amt-cell, .formula-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
}
.error-amount { color: var(--el-color-danger); font-weight: 600; }

.sensitivity-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.audit-note-card { margin-bottom: 12px; }
.readonly-note { font-size: 12px; color: var(--el-text-color-regular); margin-top: 8px; }

.jump-targets {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  margin: 8px 0 12px;
}
.jump-label { font-size: 12px; color: var(--el-text-color-secondary); }

.edit-tips { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ol { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
