<template>
  <div class="k5-tab-decommission">
    <!-- 适用性开关 -->
    <div class="applicability-bar">
      <span class="applicability-label">本项目是否存在弃置义务？</span>
      <el-switch v-model="isApplicable" :disabled="isReadonly" active-text="适用" inactive-text="不适用" @change="handleApplicabilityChange" />
      <el-tooltip v-if="!isApplicable" content="适用资产：矿井、核电站、油气设施等有法定弃置义务的长期资产" placement="right">
        <el-icon style="margin-left:4px;color:#909399"><InfoFilled /></el-icon>
      </el-tooltip>
    </div>

    <!-- 不适用时显示简要说明 -->
    <template v-if="!isApplicable">
      <el-card shadow="never" class="k5-section-card">
        <template #header><span class="card-title">不适用说明</span></template>
        <el-input
          v-model="notApplicableReason"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :disabled="isReadonly"
          placeholder="说明本项目不存在弃置义务的原因（如：企业不涉及矿井/核电/油气等有法定弃置义务的资产）"
          @change="persistApplicability"
        />
      </el-card>
    </template>

    <template v-if="isApplicable">
    <!-- 审计目标（认定） -->
    <el-alert type="info" :closable="false" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">审计目标（认定）</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li><b>完整性与义务：</b>存在弃置义务的固定资产均已确认弃置费用预计负债；</li>
        <li><b>计价和分摊：</b>弃置费用按未来支出现值（折现）恰当计量，折现率与期间合理；</li>
        <li><b>列报与披露：</b>弃置费用及其增值已按 CAS13/CAS4 恰当处理与披露。</li>
      </ol>
    </el-alert>

    <!-- ═══ Section标题 ═══ -->
    <div class="section-header">
      <h3>K5-5 弃置费用检查表</h3>
      <div class="header-actions">
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">
          <el-icon><Plus /></el-icon> 新增行
        </el-button>
        <el-dropdown size="small" :disabled="isReadonly">
          <el-button size="small">导入导出 <el-icon><ArrowDown /></el-icon></el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" type="primary" plain @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI结论
        </el-button>
        <el-button size="small" @click="$emit('navigate-sheet', '审定表K5-1')">复核</el-button>
      </div>
    </div>

    <!-- ═══ 方法论上下文 ═══ -->
    <div class="methodology-context">
      <p>弃置费用（弃置义务）现值折现：<strong>现值 = 预计弃置支出 / (1+折现率)^年数</strong>。期末 = 期初 + 本期增加 + 利息调整（期初×折现率）。K5-5期末合计应与K5-1弃置义务行审定数一致。</p>
    </div>

    <!-- ═══ 交叉验证指示器 ═══ -->
    <div class="cross-check-bar">
      <span>K5-5 期末合计: <strong>{{ fmtNum(crossCheck.decommissionTotal) }}</strong></span>
      <span>K5-1 弃置义务审定: <strong>{{ fmtNum(crossCheck.adjudicationDecommission) }}</strong></span>
      <el-tag v-if="crossCheck.isMatch" type="success" size="small">✓ 一致</el-tag>
      <el-tag v-else type="danger" size="small">差异 {{ fmtNum(crossCheck.diff) }}</el-tag>
    </div>

    <!-- ═══（一）弃置费用的完整性检查 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（一）弃置费用的完整性检查</span>
          <el-button v-if="!isReadonly" size="small" @click="addCompletenessRow()">＋ 新增行</el-button>
        </div>
      </template>
      <el-table :data="completenessRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="内部资料/外部评估报告" min-width="170">
          <template #default="{ row }"><el-input v-model="row.internalDesc" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'internalDesc', v)" /></template>
        </el-table-column>
        <el-table-column label="与第三方/监管机构函件" min-width="170">
          <template #default="{ row }"><el-input v-model="row.thirdPartyDesc" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'thirdPartyDesc', v)" /></template>
        </el-table-column>
        <el-table-column label="固定资产本期增加是否迹象计提不足" min-width="180">
          <template #default="{ row }"><el-input v-model="row.faIncreaseCheck" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'faIncreaseCheck', v)" /></template>
        </el-table-column>
        <el-table-column label="实地观察是否迹象计提不足" min-width="170">
          <template #default="{ row }"><el-input v-model="row.onSiteObservation" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'onSiteObservation', v)" /></template>
        </el-table-column>
        <el-table-column label="索引" width="90">
          <template #default="{ row }"><el-input v-model="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateCompletenessCell(row.rowId, 'indexNo', v)" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeCompletenessRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══（二）关键假设评估 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（二）关键假设评估</span>
          <el-button v-if="!isReadonly" size="small" @click="addAssumptionRow()">＋ 新增行</el-button>
        </div>
      </template>
      <el-table :data="assumptionRows" border size="small" style="width:100%">
        <el-table-column type="index" label="序" width="46" align="center" />
        <el-table-column label="关键假设" min-width="200">
          <template #default="{ row }"><el-input v-model="row.assumption" :disabled="isReadonly" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" size="small" placeholder="如：弃置支出金额、折现率、弃置时间等" @change="(v: string) => updateAssumptionCell(row.rowId, 'assumption', v)" /></template>
        </el-table-column>
        <el-table-column label="是否与历史/行业数据一致" width="150" align="center">
          <template #default="{ row }">
            <el-select v-model="row.consistentWithData" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'consistentWithData', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="期后事项是否影响" width="140" align="center">
          <template #default="{ row }">
            <el-select v-model="row.affectedByPostEvent" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'affectedByPostEvent', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="假设是否合理" width="130" align="center">
          <template #default="{ row }">
            <el-select v-model="row.isReasonable" :disabled="isReadonly" size="small" placeholder="选择" @change="(v: string) => updateAssumptionCell(row.rowId, 'isReasonable', v)">
              <el-option label="是" value="是" /><el-option label="否" value="否" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="90">
          <template #default="{ row }"><el-input v-model="row.indexNo" :disabled="isReadonly" size="small" @change="(v: string) => updateAssumptionCell(row.rowId, 'indexNo', v)" /></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="46" align="center">
          <template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAssumptionRow($index)"><el-icon><Delete /></el-icon></el-button></template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- ═══ 现值折现测算（计量辅助）═══ -->
    <div class="sub-section-title">（三）弃置费用现值折现测算（计量辅助）</div>
    <!-- ═══ 主表 ═══ -->
    <el-table :data="decommissionRows" border size="small" style="width: 100%" max-height="480">
      <el-table-column type="index" label="序" width="48" align="center" />
      <el-table-column label="资产名称" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.assetName" :disabled="isReadonly" size="small" @blur="save(row.rowId, 'assetName', row.assetName)" />
        </template>
      </el-table-column>
      <el-table-column label="预计弃置支出" width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.futureExpense" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:100px" @change="(v:number) => save(row.rowId, 'futureExpense', v)" />
        </template>
      </el-table-column>
      <el-table-column label="年数" width="70" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.expectedYears" :disabled="isReadonly" size="small" :controls="false" :precision="0" :min="0" style="width:55px" @change="(v:number) => save(row.rowId, 'expectedYears', v)" />
        </template>
      </el-table-column>
      <el-table-column label="折现率" width="90" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.discountRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:75px" @change="(v:number) => save(row.rowId, 'discountRate', v)" />
          <el-icon v-if="row.discountRate <= 0 && row.futureExpense > 0" color="#f56c6c" style="margin-left:2px"><WarningFilled /></el-icon>
        </template>
      </el-table-column>
      <el-table-column label="现值" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="future / (1+rate)^years" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.presentValue) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期初" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.beginBalance" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'beginBalance', v)" />
        </template>
      </el-table-column>
      <el-table-column label="增加" width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-model="row.periodIncrease" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:85px" @change="(v:number) => save(row.rowId, 'periodIncrease', v)" />
        </template>
      </el-table-column>
      <el-table-column label="利息调整" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 × 折现率" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.interestAdjustment) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="期末" width="110" align="right">
        <template #default="{ row }">
          <el-tooltip content="期初 + 增加 + 利息调整" placement="top">
            <span class="formula-cell formula-underline">{{ fmtNum(row.endBalance) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="结论" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.conclusion" :disabled="isReadonly" size="small" placeholder="结论" @blur="save(row.rowId, 'conclusion', row.conclusion)" />
        </template>
      </el-table-column>
      <el-table-column label="" width="48" align="center">
        <template #default="{ $index }">
          <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow($index)">
            <el-icon><Delete /></el-icon>
          </el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ 合计行 ═══ -->
    <div class="summary-bar">
      <span>合计行数: {{ subtotals.count }}</span>
      <span>现值合计: {{ fmtNum(subtotals.presentValue) }}</span>
      <span>期末合计: <strong>{{ fmtNum(subtotals.endBalance) }}</strong></span>
    </div>

    <!-- ═══ 借方/贷方发生额分析 ═══ -->
    <el-card shadow="never" class="k5-section-card" style="margin-top:12px">
      <template #header><span class="card-title">借方/贷方发生额分析</span></template>
      <div class="dc-grid">
        <div class="dc-col">
          <div class="dc-head">
            <span>借方发生额分析</span>
            <el-button v-if="!isReadonly" size="small" @click="addAmountRow('debit')">＋ 新增</el-button>
          </div>
          <el-table :data="debitRows" border size="small" style="width:100%">
            <el-table-column type="index" label="序" width="42" align="center" />
            <el-table-column label="对应科目" min-width="120"><template #default="{ row }"><el-input v-model="row.offsetAccount" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('debit', row.rowId, 'offsetAccount', v)" /></template></el-table-column>
            <el-table-column label="对应金额" width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.amount" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateAmountCell('debit', row.rowId, 'amount', v)" /></template></el-table-column>
            <el-table-column label="备注" min-width="110"><template #default="{ row }"><el-input v-model="row.remark" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('debit', row.rowId, 'remark', v)" /></template></el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="42" align="center"><template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAmountRow('debit', $index)"><el-icon><Delete /></el-icon></el-button></template></el-table-column>
            <template #append><div class="table-total">借方小计：{{ fmtNum(debitTotal) }}</div></template>
          </el-table>
        </div>
        <div class="dc-col">
          <div class="dc-head">
            <span>贷方发生额分析</span>
            <el-button v-if="!isReadonly" size="small" @click="addAmountRow('credit')">＋ 新增</el-button>
          </div>
          <el-table :data="creditRows" border size="small" style="width:100%">
            <el-table-column type="index" label="序" width="42" align="center" />
            <el-table-column label="对应科目" min-width="120"><template #default="{ row }"><el-input v-model="row.offsetAccount" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('credit', row.rowId, 'offsetAccount', v)" /></template></el-table-column>
            <el-table-column label="对应金额" width="120" align="right"><template #default="{ row }"><el-input-number v-model="row.amount" :disabled="isReadonly" :controls="false" :precision="2" size="small" class="hnum" @change="(v: number) => updateAmountCell('credit', row.rowId, 'amount', v)" /></template></el-table-column>
            <el-table-column label="备注" min-width="110"><template #default="{ row }"><el-input v-model="row.remark" :disabled="isReadonly" size="small" @change="(v: string) => updateAmountCell('credit', row.rowId, 'remark', v)" /></template></el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="42" align="center"><template #default="{ $index }"><el-button link type="danger" size="small" @click="removeAmountRow('credit', $index)"><el-icon><Delete /></el-icon></el-button></template></el-table-column>
            <template #append><div class="table-total">贷方小计：{{ fmtNum(creditTotal) }}</div></template>
          </el-table>
        </div>
      </div>
    </el-card>

    <!-- ═══（四）折现率合理性校验 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header><span class="card-title">（四）折现率合理性校验</span></template>
      <div class="rate-check-grid">
        <div class="rate-item">
          <label>同期国债收益率参考</label>
          <div class="rate-inline">
            <el-input-number v-model="rateCheck.govBondRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:90px" @change="persistRateCheck" />
            <span class="rate-pct">{{ rateCheck.govBondRate ? ((rateCheck.govBondRate) * 100).toFixed(2) + '%' : '' }}</span>
          </div>
        </div>
        <div class="rate-item">
          <label>LPR（1年/5年以上）</label>
          <div class="rate-inline">
            <el-input-number v-model="rateCheck.lprRate" :disabled="isReadonly" size="small" :controls="false" :precision="4" :step="0.001" style="width:90px" @change="persistRateCheck" />
            <span class="rate-pct">{{ rateCheck.lprRate ? ((rateCheck.lprRate) * 100).toFixed(2) + '%' : '' }}</span>
          </div>
        </div>
        <div class="rate-item">
          <label>企业使用折现率</label>
          <span class="rate-pct" style="font-weight:600">{{ avgDiscountRate ? (avgDiscountRate * 100).toFixed(2) + '%' : '未填' }}</span>
        </div>
        <div class="rate-item">
          <label>偏离基准</label>
          <span :class="{ 'rate-warn': rateDeviation > 200 }">
            {{ rateDeviation !== null ? rateDeviation + ' BP' : '—' }}
            <el-tag v-if="rateDeviation !== null && rateDeviation > 200" type="warning" size="small" style="margin-left:4px">偏离>200BP</el-tag>
          </span>
        </div>
      </div>
      <div v-if="rateDeviation !== null && rateDeviation > 200" class="rate-deviation-warn">
        ⚠️ 折现率偏离市场基准超过200BP，应获取管理层说明或考虑审计调整。若企业采用特定行业折现率（如环保行业社会折现率），需取得依据文件。
      </div>
    </el-card>

    <!-- ═══（五）利用专家的工作 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（五）利用专家的工作（CAS1421）</span>
          <div style="display:flex;gap:6px">
            <GtIndexChip value="wp:S12" :context-project-id="props.projectId" />
            <GtIndexChip value="wp:S12A" :context-project-id="props.projectId" />
          </div>
        </div>
      </template>
      <div class="expert-grid">
        <div class="expert-item">
          <label>是否利用专家</label>
          <el-select v-model="expertInfo.useExpert" :disabled="isReadonly" size="small" @change="persistExpert">
            <el-option label="是" value="yes" /><el-option label="否" value="no" />
          </el-select>
        </div>
        <template v-if="expertInfo.useExpert === 'yes'">
          <div class="expert-item">
            <label>专家类型</label>
            <el-select v-model="expertInfo.expertType" :disabled="isReadonly" size="small" @change="persistExpert">
              <el-option label="环保评估专家" value="environment" />
              <el-option label="工程造价专家" value="engineering" />
              <el-option label="矿山复垦专家" value="mining" />
              <el-option label="其他" value="other" />
            </el-select>
          </div>
          <div class="expert-item">
            <label>专家名称/机构</label>
            <el-input v-model="expertInfo.expertName" :disabled="isReadonly" size="small" placeholder="专家/评估机构名称" @change="persistExpert" />
          </div>
          <div class="expert-item expert-full">
            <label>胜任能力与独立性评价</label>
            <el-input v-model="expertInfo.competenceEval" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 2 }"
              placeholder="评价专家的胜任能力（资质/经验/声誉）和独立性（与被审计单位无利益关系）" @change="persistExpert" />
          </div>
          <div class="expert-item expert-full">
            <label>专家工作结果评价</label>
            <el-input v-model="expertInfo.workEval" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 2 }"
              placeholder="评价专家评估报告的假设合理性、方法恰当性、数据可靠性、结论是否用作审计证据" @change="persistExpert" />
          </div>
        </template>
      </div>
    </el-card>

    <!-- ═══（六）会计估计变更追踪 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">（六）会计估计变更（CAS28）</span>
          <GtIndexChip value="wp:H1" :context-project-id="props.projectId" />
        </div>
      </template>
      <div class="estimate-change-hint">
        弃置费用估计变更（弃置支出金额/折现率/预计时间变动）按CAS28处理：变更产生的预计负债差额应同时调整固定资产原值（联动H1），非追溯调整。
      </div>
      <div class="estimate-fields">
        <div class="ef-item">
          <label>本期是否存在估计变更</label>
          <el-select v-model="estimateChange.hasChange" :disabled="isReadonly" size="small" @change="persistEstimateChange">
            <el-option label="否" value="no" /><el-option label="是" value="yes" />
          </el-select>
        </div>
        <template v-if="estimateChange.hasChange === 'yes'">
          <div class="ef-item ef-full">
            <label>变更原因</label>
            <el-input v-model="estimateChange.reason" :disabled="isReadonly" size="small" type="textarea" :autosize="{ minRows: 2 }"
              placeholder="如：环保政策变化导致弃置支出预计增加/折现率调整/弃置时间提前等" @change="persistEstimateChange" />
          </div>
          <div class="ef-item">
            <label>变更前预计负债</label>
            <el-input-number v-model="estimateChange.beforeAmount" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:130px" @change="persistEstimateChange" />
          </div>
          <div class="ef-item">
            <label>变更后预计负债</label>
            <el-input-number v-model="estimateChange.afterAmount" :disabled="isReadonly" size="small" :controls="false" :precision="2" style="width:130px" @change="persistEstimateChange" />
          </div>
          <div class="ef-item">
            <label>差额（应调整FA原值）</label>
            <span class="formula-cell formula-underline">{{ fmtNum((estimateChange.afterAmount || 0) - (estimateChange.beforeAmount || 0)) }}</span>
          </div>
          <div class="ef-item ef-full">
            <label>是否已同步调整固定资产原值（H1）</label>
            <el-select v-model="estimateChange.h1Adjusted" :disabled="isReadonly" size="small" @change="persistEstimateChange">
              <el-option label="已调整" value="yes" /><el-option label="未调整（需关注）" value="no" />
            </el-select>
          </div>
        </template>
      </div>
    </el-card>

    <!-- ═══ 审计说明与结论 ═══ -->
    <el-card shadow="never" class="k5-section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">审计说明与结论</span>
          <el-button size="small" type="primary" plain @click="handleAiGenerate">
            <el-icon><MagicStick /></el-icon> AI
          </el-button>
        </div>
      </template>
      <div style="margin-bottom:10px">
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述弃置费用检查情况：适用资产/弃置支出估计依据/折现率来源/专家利用情况/完整性检查结论/估计变更情况等"
          @change="persistNote" />
      </div>
      <div>
        <label style="font-size:12px;color:#909399;display:block;margin-bottom:4px">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="基于上述检查，对预计负债-弃置义务的完整性、计量和披露形成结论..."
          @change="persistNote" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="k5-details-tip">
      <summary>编制提示（CAS13/CAS4/CAS28/CAS1421）</summary>
      <ul>
        <li><b>现值公式：</b>现值 = 预计弃置支出 / (1+折现率)^年数</li>
        <li><b>利息调整：</b>期初余额 × 折现率（时间价值累积增加负债，计入财务费用）</li>
        <li><b>折现率：</b>应反映货币时间价值和该负债特定风险的税前利率（通常参考同期国债收益率+风险溢价）</li>
        <li><b>折现率为0或负时：</b>现值=未来支出（兜底），利息调整=0</li>
        <li><b>适用资产：</b>矿井、核电站、油气设施、化工厂等有法定/推定弃置义务的长期资产</li>
        <li><b>完整性检查（CAS13§5）：</b>关注未识别弃置义务的固定资产（特别是本期新增的有法定义务的资产）</li>
        <li><b>利用专家（CAS1421）：</b>弃置支出估计通常需环保/工程专家→评价胜任能力+独立性+工作结果</li>
        <li><b>估计变更（CAS28）：</b>弃置支出/折现率/时间变动→调整预计负债同时调整固定资产原值（非追溯，联动H1）</li>
        <li><b>偏离基准预警：</b>折现率偏离同期国债/LPR超过200BP须获取管理层说明</li>
      </ul>
    </details>
    </template><!-- end v-if="isApplicable" -->
  </div>
</template>

<script setup lang="ts">
/**
 * K5TabDecommissionCheck.vue — K5-5 弃置费用检查表
 * 现值折现+利息调整+回连审定+错误状态
 *
 * Spec: .kiro/specs/k5-provisions/ | Task: 4.4
 * Requirements: 7.1-7.4
 */
import { ref, toRef, computed, onMounted } from 'vue'
import { Plus, Delete, MagicStick, WarningFilled, InfoFilled, ArrowDown } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useK5Decommission } from '../../composables/useK5Decommission'
import GtIndexChip from '../../shared/GtIndexChip.vue'
import http from '@/utils/http'
import type { Ref } from 'vue'

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

// 父组件模板绑定会自动解包 ref → 子组件收到纯 Map；重新包成 ref 供 composable 使用
const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>

const {
  decommissionRows,
  subtotals,
  crossCheck,
  updateCell,
  addRow,
  removeRow,
  completenessRows,
  addCompletenessRow,
  updateCompletenessCell,
  removeCompletenessRow,
  assumptionRows,
  addAssumptionRow,
  updateAssumptionCell,
  removeAssumptionRow,
  debitRows,
  creditRows,
  debitTotal,
  creditTotal,
  addAmountRow,
  updateAmountCell,
  removeAmountRow,
} = useK5Decommission({
  allResponses: allResponsesRef,
  saveResponse: async (field: string, value: any) => {
    emit('save', `K5-${field}`, value)
  },
})

function save(rowId: string, field: string, value: any) { updateCell(rowId, field, value) }
function handleAddRow() { addRow() }
function handleAiGenerate() { emit('save', 'K5-5-ai-trigger', { remark: 'decommission-conclusion' }) }

// ─── 适用性开关 ──────────────────────────────────────────────────────────────

const isApplicable = ref(true)
const notApplicableReason = ref('')

function loadApplicability(): void {
  const saved = props.allResponses.get('K5-5-applicability')
  if (saved?.remark) {
    try {
      const data = JSON.parse(saved.remark)
      isApplicable.value = data.applicable !== false
      notApplicableReason.value = data.reason || ''
    } catch {
      isApplicable.value = true
    }
  }
}

function handleApplicabilityChange(val: boolean): void {
  isApplicable.value = val
  persistApplicability()
}

function persistApplicability(): void {
  emit('save', 'K5-5-applicability', {
    remark: JSON.stringify({ applicable: isApplicable.value, reason: notApplicableReason.value }),
  })
}

// ─── 折现率合理性校验 ────────────────────────────────────────────────────────

const rateCheck = ref({ govBondRate: 0, lprRate: 0 })

const avgDiscountRate = computed(() => {
  const rows = decommissionRows.value.filter((r: any) => r.discountRate > 0)
  if (!rows.length) return 0
  return rows.reduce((s: number, r: any) => s + r.discountRate, 0) / rows.length
})

const rateDeviation = computed<number | null>(() => {
  if (!avgDiscountRate.value) return null
  const benchmark = rateCheck.value.govBondRate || rateCheck.value.lprRate
  if (!benchmark) return null
  return Math.round(Math.abs(avgDiscountRate.value - benchmark) * 10000) // BP
})

function loadRateCheck(): void {
  const saved = props.allResponses.get('K5-5-rate-check')
  if (saved?.remark) {
    try { Object.assign(rateCheck.value, JSON.parse(saved.remark)) } catch { /* */ }
  }
}

function persistRateCheck(): void {
  emit('save', 'K5-5-rate-check', { remark: JSON.stringify(rateCheck.value) })
}

// ─── 利用专家的工作 ──────────────────────────────────────────────────────────

const expertInfo = ref({ useExpert: '', expertType: '', expertName: '', competenceEval: '', workEval: '' })

function loadExpert(): void {
  const saved = props.allResponses.get('K5-5-expert')
  if (saved?.remark) {
    try { Object.assign(expertInfo.value, JSON.parse(saved.remark)) } catch { /* */ }
  }
}

function persistExpert(): void {
  emit('save', 'K5-5-expert', { remark: JSON.stringify(expertInfo.value) })
}

// ─── 会计估计变更 ────────────────────────────────────────────────────────────

const estimateChange = ref({ hasChange: 'no', reason: '', beforeAmount: 0, afterAmount: 0, h1Adjusted: '' })

function loadEstimateChange(): void {
  const saved = props.allResponses.get('K5-5-estimate-change')
  if (saved?.remark) {
    try { Object.assign(estimateChange.value, JSON.parse(saved.remark)) } catch { /* */ }
  }
}

function persistEstimateChange(): void {
  emit('save', 'K5-5-estimate-change', { remark: JSON.stringify(estimateChange.value) })
}

// ─── 审计说明与结论 ──────────────────────────────────────────────────────────

const auditNote = ref('')
const auditConclusion = ref('')

function loadNote(): void {
  const noteItem = props.allResponses.get('K5-5-audit-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const conclItem = props.allResponses.get('K5-5-audit-conclusion')
  if (conclItem?.remark) auditConclusion.value = conclItem.remark
}

function persistNote(): void {
  emit('save', 'K5-5-audit-note', { remark: auditNote.value })
  emit('save', 'K5-5-audit-conclusion', { remark: auditConclusion.value })
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

async function handleExportTemplate(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-template`, null, { params: { sheet: 'K5-5' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'K5-5_弃置费用_模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('模板已下载')
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData(): Promise<void> {
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/k5/export-data`, null, { params: { sheet: 'K5-5' }, responseType: 'blob', _silent: true } as any)
    const blob = new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a'); a.href = url; a.download = 'K5-5_弃置费用_数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('数据已导出')
  } catch { ElMessage.error('导出数据失败') }
}

async function handleImportData(): Promise<void> {
  const input = document.createElement('input'); input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]; if (!file) return
    const formData = new FormData(); formData.append('file', file)
    try {
      const res = await http.post(`/api/workpapers/${props.wpId}/k5/import-data`, formData, { params: { sheet: 'K5-5' }, headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any)
      ElMessage.success(`导入成功，共 ${res?.data?.imported_count ?? res?.data?.data?.rowCount ?? 0} 条`)
    } catch (err: any) { ElMessage.error('导入失败：' + (err?.response?.data?.message || err?.response?.data?.detail || '文件格式错误')) }
  }
  input.click()
}

onMounted(() => {
  loadApplicability()
  loadRateCheck()
  loadExpert()
  loadEstimateChange()
  loadNote()
})

function fmtNum(v: number): string {
  if (!v && v !== 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.k5-tab-decommission { padding: 12px; font-size: var(--wp-font-size, 13px); }
.applicability-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 8px 14px; background: linear-gradient(135deg, #f0f9ff 0%, #e0f2fe 100%); border: 1px solid #bae6fd; border-radius: 6px; }
.applicability-label { font-weight: 500; color: #0369a1; font-size: 13px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-header h3 { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }
.header-actions { display: flex; gap: 8px; }
.methodology-context { background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: var(--wp-font-size, 13px); color: #78350f; line-height: 1.6; }
.cross-check-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.formula-cell { font-family: 'JetBrains Mono', monospace; font-size: 12px; color: #303133; }
.formula-underline { border-bottom: 1px dashed #909399; cursor: help; }
.summary-bar { display: flex; gap: 24px; margin-top: 10px; padding: 8px 12px; background: #f5f7fa; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-section-card { margin-bottom: 12px; }
.k5-section-card :deep(.el-card__header) { padding: 8px 14px; }
.k5-section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.sub-section-title { font-weight: 600; color: #303133; margin: 4px 0 8px; font-size: 13px; }
.hnum { width: 100%; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: #606266; font-weight: 600; }
.dc-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
.dc-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; font-size: 12px; font-weight: 600; color: #606266; }
/* 折现率校验 */
.rate-check-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 18px; }
.rate-item { display: flex; flex-direction: column; gap: 4px; }
.rate-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.rate-inline { display: flex; align-items: center; gap: 6px; }
.rate-pct { font-size: 12px; color: #606266; }
.rate-warn { color: #e6a23c; font-weight: 600; }
.rate-deviation-warn { margin-top: 8px; padding: 6px 10px; background: #fef3c7; border-radius: 4px; font-size: 12px; color: #92400e; line-height: 1.5; }
/* 专家 */
.expert-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 18px; }
.expert-item { display: flex; flex-direction: column; gap: 4px; }
.expert-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.expert-full { grid-column: 1 / -1; }
/* 估计变更 */
.estimate-change-hint { padding: 6px 10px; background: #f0f9ff; border-left: 3px solid #3b82f6; border-radius: 4px; font-size: 12px; color: #1e40af; line-height: 1.5; margin-bottom: 10px; }
.estimate-fields { display: grid; grid-template-columns: repeat(2, 1fr); gap: 10px 18px; }
.ef-item { display: flex; flex-direction: column; gap: 4px; }
.ef-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.ef-full { grid-column: 1 / -1; }
:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.k5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.k5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.k5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
