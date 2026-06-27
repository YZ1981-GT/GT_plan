<template>
<div class="d2-accounts-receivable" :class="{ 'is-readonly': review.isReadonly.value }">
  <div v-if="review.isReviewed.value" class="reviewed-banner">
    <el-icon><CircleCheckFilled /></el-icon>
    <span>已复核 — {{ review.reviewInfo.value?.reviewer }} {{ review.reviewInfo.value?.date }}</span>
  </div>
  <div class="linkage-bar">
    <el-tag v-for="link in d2.linkageRefs.value" :key="link.targetWpCode" type="info" class="ref-chip">{{ link.icon }} {{ link.label }}</el-tag>
  </div>
  <el-tabs v-model="d2.activeTab.value" @tab-change="d2.setActiveTab">
    <!-- Tab 1: 底稿目录 -->
    <el-tab-pane name="directory">
      <template #label><span :class="tabDotClass('directory')">○</span> 底稿目录</template>
      <div class="d2-section">
        <h3>D2 应收账款底稿目录</h3>
        <el-table :data="sheetDirectory" size="small" border stripe>
          <el-table-column prop="code" label="编号" width="80" />
          <el-table-column prop="name" label="名称" />
        </el-table>
      </div>
    </el-tab-pane>
    <!-- Tab 2: 程序表 D2A -->
    <el-tab-pane name="procedure">
      <template #label><span :class="tabDotClass('procedure')">○</span> 程序表 D2A</template>
      <div class="d2-section">
        <div class="progress-bar">
          <span>审计程序进度：{{ d2.procedureProgress.value.completed }}/{{ d2.procedureProgress.value.total }}</span>
          <el-progress :percentage="procPct" :stroke-width="10" />
        </div>
        <div v-if="d2.riskIndicators.value.size > 0" class="risk-badges">
          <el-tag v-for="[, ri] in d2.riskIndicators.value" :key="ri.description" :type="ri.level === 'H' ? 'danger' : ri.level === 'M' ? 'warning' : 'success'" size="small">
            {{ ri.level === 'H' ? '高风险' : ri.level === 'M' ? '中风险' : '低风险' }} {{ ri.description }}
          </el-tag>
        </div>
        <div v-for="(step, idx) in d2.procedureSteps.value" :key="step.stepOrder" class="procedure-card">
          <div class="card-header">
            <span class="step-num">{{ step.stepOrder }}</span>
            <span class="step-name">{{ step.stepName }}</span>
            <el-tag v-if="step.relatedTab" size="small" type="info" class="ref-chip" @click="d2.setActiveTab(step.relatedTab!)">→{{ step.relatedTab }}</el-tag>
            <el-select v-model="step.status" size="small" :disabled="review.isReadonly.value" style="width:100px;margin-left:auto" @change="(val: string) => d2.setProcedureStatus(idx, val as any)">
              <el-option value="未开始" label="未开始" />
              <el-option value="执行中" label="执行中" />
              <el-option value="已完成" label="已完成" />
              <el-option value="不适用" label="不适用" />
            </el-select>
          </div>
          <div class="card-body-proc">
            <el-input v-model="step.executor" size="small" placeholder="执行人" :disabled="review.isReadonly.value" style="width:120px" @input="onProcTextChange(idx, 'executor', $event)" />
            <el-input v-model="step.executeDate" size="small" placeholder="日期" :disabled="review.isReadonly.value" style="width:120px" @input="onProcTextChange(idx, 'date', $event)" />
          </div>
        </div>
        <div class="overall-conclusion">
          <h4>整体审计结论</h4>
          <el-input v-model="d2.overallConclusion.value" type="textarea" :rows="3" :disabled="review.isReadonly.value || !d2.canInputOverallConclusion.value" placeholder="全部必要步骤完成后可录入整体结论" @input="onOverallConclusionChange" />
          <el-alert v-if="!d2.canInputOverallConclusion.value" type="info" :closable="false" title="需完成所有必要审计步骤后方可录入整体结论" show-icon />
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 3: 审定表 D2-1 (SUMIF) -->
    <el-tab-pane name="adjudication">
      <template #label><span :class="tabDotClass('adjudication')">○</span> 审定表 D2-1</template>
      <div class="d2-section">
        <h3>应收账款审定表（SUMIF 联动）</h3>
        <el-table :data="d2.adjudicationRows.value" size="small" border>
          <el-table-column prop="label" label="项目" width="180" fixed />
          <el-table-column label="期初未审" width="120">
            <template #default="{ row }"><span :class="{ 'cross-ref': row.isFromSumif }">{{ fmtAmount(row.priorUnadjusted) }}</span></template>
          </el-table-column>
          <el-table-column label="期末未审" width="120">
            <template #default="{ row }"><span :class="{ 'cross-ref': row.isFromSumif }">{{ fmtAmount(row.currentUnadjusted) }}</span></template>
          </el-table-column>
          <el-table-column label="SUMIF期初" width="110">
            <template #default="{ row }"><span class="cross-ref">{{ row.isFromSumif ? fmtAmount(row.sumifPrior) : '-' }}</span></template>
          </el-table-column>
          <el-table-column label="SUMIF变动" width="110">
            <template #default="{ row }"><span class="cross-ref">{{ row.isFromSumif ? fmtAmount(row.sumifChange) : '-' }}</span></template>
          </el-table-column>
          <el-table-column label="SUMIF期末" width="110">
            <template #default="{ row }"><span class="cross-ref">{{ row.isFromSumif ? fmtAmount(row.sumifEnd) : '-' }}</span></template>
          </el-table-column>
          <el-table-column label="AJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.ajeAdjustment) }}</template>
          </el-table-column>
          <el-table-column label="RJE" width="100">
            <template #default="{ row }">{{ fmtAmount(row.rjeAdjustment) }}</template>
          </el-table-column>
          <el-table-column label="审定数" width="120">
            <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.auditedAmount) }}</span></template>
          </el-table-column>
          <el-table-column label="变动率" width="100">
            <template #default="{ row }"><span class="auto-calc">{{ row.changeRate === '' ? '-' : fmtPercent(row.changeRate) }}</span></template>
          </el-table-column>
        </el-table>
        <!-- 函证汇总区 -->
        <div v-if="d2.confirmationSummary.value" class="confirmation-panel">
          <h4>函证汇总</h4>
          <span>发函：{{ d2.confirmationSummary.value.sentCount }}</span>
          <span>回函：{{ d2.confirmationSummary.value.receivedCount }}</span>
          <span>回函率：{{ fmtPercent(d2.confirmationSummary.value.responseRate) }}</span>
          <span>确认金额：{{ fmtAmount(d2.confirmationSummary.value.confirmedAmount) }}</span>
          <span>差异：{{ fmtAmount(d2.confirmationSummary.value.differenceAmount) }}</span>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 4: 附注披露 -->
    <el-tab-pane name="disclosure">
      <template #label><span :class="tabDotClass('disclosure')">○</span> 附注披露</template>
      <div class="d2-section">
        <el-radio-group v-model="disclosureType" size="small" :disabled="review.isReadonly.value">
          <el-radio-button value="listed">上市公司</el-radio-button>
          <el-radio-button value="soe">国企</el-radio-button>
        </el-radio-group>
        <el-alert v-if="d2.hasUndisclosedItems.value" type="error" title="存在未披露需补充事项，请关注！" :closable="false" show-icon style="margin:12px 0" />
        <el-table :data="d2.disclosureItems.value" size="small" border style="margin-top:12px">
          <el-table-column type="index" width="50" />
          <el-table-column prop="checkItem" label="检查事项" />
          <el-table-column label="结论" width="180">
            <template #default="{ row }">
              <el-select v-model="row.conclusion" size="small" :disabled="review.isReadonly.value" placeholder="请选择" @change="onDisclosureChange(row)">
                <el-option value="已披露且准确" label="已披露且准确" />
                <el-option value="已披露但需修改" label="已披露但需修改" />
                <el-option value="未披露需补充" label="未披露需补充" />
                <el-option value="不适用" label="不适用" />
              </el-select>
            </template>
          </el-table-column>
          <el-table-column label="备注" width="200">
            <template #default="{ row }">
              <el-input v-model="row.remark" size="small" :disabled="review.isReadonly.value" placeholder="备注" @input="onDisclosureRemarkChange(row)" />
            </template>
          </el-table-column>
        </el-table>
      </div>
    </el-tab-pane>
    <!-- Tab 5: D2-2 明细表 (子底稿 lazy) -->
    <el-tab-pane name="detail-d2-2" :lazy="true">
      <template #label><span :class="tabDotClass('detail-d2-2')">○</span> D2-2 明细表</template>
      <div class="d2-sub-wp-placeholder">子底稿 D2-2 通过 GtWpRenderer 懒加载</div>
    </el-tab-pane>
    <!-- Tab 6: 坏账准备 D2-3 -->
    <el-tab-pane name="bad-debt">
      <template #label><span :class="tabDotClass('bad-debt')">○</span> 坏账准备 D2-3</template>
      <div class="d2-section">
        <div class="ecl-header">
          <span>坏账计提方式：</span>
          <el-radio-group :model-value="d2.badDebtMethod.value" size="small" :disabled="review.isReadonly.value" @change="(val: string) => d2.setBadDebtMethod(val as any)">
            <el-radio-button value="单项计提">单项计提</el-radio-button>
            <el-radio-button value="账龄组合">账龄组合</el-radio-button>
            <el-radio-button value="客户类型组合">客户类型组合</el-radio-button>
          </el-radio-group>
        </div>
        <div v-if="d2.badDebtMethod.value === '账龄组合'" class="migration-matrix">
          <h4>迁徙率矩阵</h4>
          <el-table :data="d2.migrationRateMatrix.value" size="small" border>
            <el-table-column prop="fromBand" label="从" width="120" />
            <el-table-column prop="toBand" label="到" width="120" />
            <el-table-column prop="year1Rate" label="第1年" width="90"><template #default="{ row }">{{ fmtPercent(row.year1Rate) }}</template></el-table-column>
            <el-table-column prop="year2Rate" label="第2年" width="90"><template #default="{ row }">{{ fmtPercent(row.year2Rate) }}</template></el-table-column>
            <el-table-column prop="year3Rate" label="第3年" width="90"><template #default="{ row }">{{ fmtPercent(row.year3Rate) }}</template></el-table-column>
            <el-table-column prop="averageRate" label="平均" width="90"><template #default="{ row }"><span class="auto-calc">{{ fmtPercent(row.averageRate) }}</span></template></el-table-column>
          </el-table>
        </div>
        <h4>账龄段明细（6档）</h4>
        <el-table :data="d2.agingBands.value" size="small" border>
          <el-table-column prop="label" label="账龄段" width="120" fixed />
          <el-table-column prop="endBalance" label="期末余额" width="110"><template #default="{ row }">{{ fmtAmount(row.endBalance) }}</template></el-table-column>
          <el-table-column prop="expectedLossRate" label="预期损失率" width="100"><template #default="{ row }">{{ fmtPercent(row.expectedLossRate) }}</template></el-table-column>
          <el-table-column prop="shouldProvision" label="应计提" width="110"><template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.shouldProvision) }}</span></template></el-table-column>
          <el-table-column prop="actualProvision" label="实际计提" width="110"><template #default="{ row }">{{ fmtAmount(row.actualProvision) }}</template></el-table-column>
          <el-table-column label="差异" width="110"><template #default="{ row }"><span :class="{ 'diff-exceed': Math.abs(row.difference) > 0 }">{{ fmtAmount(row.difference) }}</span></template></el-table-column>
        </el-table>
        <div class="ecl-summary">
          <span>总余额：{{ fmtAmount(d2.eclSummary.value.totalEndBalance) }}</span>
          <span>应计提：{{ fmtAmount(d2.eclSummary.value.totalShouldProvision) }}</span>
          <span>实际计提：{{ fmtAmount(d2.eclSummary.value.totalActualProvision) }}</span>
          <span :class="{ 'diff-exceed': d2.eclSummary.value.exceedsMateriality }">差异：{{ fmtAmount(d2.eclSummary.value.totalDifference) }}</span>
          <el-alert v-if="d2.eclSummary.value.exceedsMateriality" type="error" title="差异超过重要性水平！" :closable="false" show-icon />
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 7: 截止测试 -->
    <el-tab-pane name="cutoff-test">
      <template #label><span :class="tabDotClass('cutoff-test')">○</span> 截止测试</template>
      <div class="d2-section">
        <div class="adj-header">
          <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d2.addCutoffSample({})">+ 新增样本</el-button>
        </div>
        <el-alert v-if="d2.hasCutoffErrors.value" type="error" title="存在截止错误，需评估影响" :closable="false" show-icon style="margin:8px 0" />
        <el-table :data="d2.cutoffTestSamples.value" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column prop="invoiceNo" label="发票号" width="120" />
          <el-table-column prop="revenueDate" label="收入确认日" width="120" />
          <el-table-column prop="arBookingDate" label="入账日期" width="120" />
          <el-table-column label="金额" width="110"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column>
          <el-table-column label="跨期" width="80"><template #default="{ row }"><span :class="{ 'diff-exceed': row.isCutoffError }">{{ row.conclusion }}</span></template></el-table-column>
          <el-table-column prop="remark" label="备注" />
          <el-table-column label="操作" width="60"><template #default="{ row }"><el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d2.removeCutoffSample(row.index)">删</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-tab-pane>
    <!-- Tab 8: 调整分录 D2-4 -->
    <el-tab-pane name="adjustment">
      <template #label><span :class="tabDotClass('adjustment')">○</span> 调整分录 D2-4</template>
      <div class="d2-section">
        <div class="adj-header">
          <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d2.addAdjustment({})">+ 新增分录</el-button>
          <span class="adj-totals">AJE合计：{{ fmtAmount(d2.ajeTotal.value) }} | RJE合计：{{ fmtAmount(d2.rjeTotal.value) }}</span>
        </div>
        <el-table :data="d2.adjustmentEntries.value" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column label="类型" width="90"><template #default="{ row }"><el-select v-model="row.type" size="small" :disabled="review.isReadonly.value" @change="onAdjChange(row)"><el-option value="AJE" label="AJE" /><el-option value="RJE" label="RJE" /></el-select></template></el-table-column>
          <el-table-column label="借方科目" width="140"><template #default="{ row }"><el-input v-model="row.debitAccount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" /></template></el-table-column>
          <el-table-column label="贷方科目" width="140"><template #default="{ row }"><el-input v-model="row.creditAccount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" /></template></el-table-column>
          <el-table-column label="金额" width="120"><template #default="{ row }"><el-input v-model="row.amount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" /></template></el-table-column>
          <el-table-column label="摘要"><template #default="{ row }"><el-input v-model="row.description" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" /></template></el-table-column>
          <el-table-column label="操作" width="140"><template #default="{ row }"><el-button size="small" type="primary" plain :disabled="review.isReadonly.value" @click="pushToA13(row)">推送A13</el-button><el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d2.removeAdjustment(row.index)">删除</el-button></template></el-table-column>
        </el-table>
      </div>
    </el-tab-pane>
    <!-- Tab 9: ECL 测算 D2-9 -->
    <el-tab-pane name="ecl-calculation" :lazy="true">
      <template #label><span :class="tabDotClass('ecl-calculation')">○</span> ECL测算 D2-9</template>
      <div class="d2-section">
        <h3>应收账款坏账准备测算表</h3>
        <p class="d2-audit-objective">审计目标：应收账款以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录</p>
        <h4>（一）单项计提坏账准备</h4>
        <el-table :data="d2.eclIndividualItems?.value || []" size="small" border>
          <el-table-column type="index" label="序号" width="50" />
          <el-table-column prop="debtorName" label="债务人名称" width="140" />
          <el-table-column label="审定账面余额①" width="120"><template #default="{ row }">{{ fmtAmount(row.balance) }}</template></el-table-column>
          <el-table-column label="预期信用损失率②" width="120"><template #default="{ row }">{{ fmtPercent(row.eclRate) }}</template></el-table-column>
          <el-table-column label="应计提③=①×②" width="120"><template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.shouldProvision) }}</span></template></el-table-column>
          <el-table-column label="实际计提④" width="110"><template #default="{ row }">{{ fmtAmount(row.actualProvision) }}</template></el-table-column>
          <el-table-column label="差异⑤=③-④" width="110"><template #default="{ row }"><span :class="{ 'diff-exceed': Math.abs(row.difference || 0) > 0 }">{{ fmtAmount(row.difference) }}</span></template></el-table-column>
          <el-table-column prop="basis" label="计提依据" />
        </el-table>
        <h4>（二）账龄组合计提</h4>
        <el-alert type="info" :closable="false" show-icon title="账龄组合测算数据参见 D2-3 坏账准备 Tab（迁徙率矩阵+账龄段明细）" />
      </div>
    </el-tab-pane>
    <!-- Tab 10: 计量测试 D2-10 -->
    <el-tab-pane name="ecl-measurement" :lazy="true">
      <template #label><span :class="tabDotClass('ecl-measurement')">○</span> 计量测试 D2-10</template>
      <div class="d2-section">
        <h3>预期信用损失的计量测试表</h3>
        <p class="d2-audit-objective">审计目标：验证预期信用损失计量的合理性（CAS 22 / IFRS 9）</p>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:12px">
          <template #title>计量原则</template>
          <template #default>
            <ul class="d2-ecl-notes">
              <li>预期信用损失 = 账面余额 × (1 - 估计未来现金流量折现值 / 账面余额)</li>
              <li>折现率采用初始确认时确定的实际利率或其近似值</li>
              <li>即使预计可全额收款但晚于合同到期期限，也会产生信用损失</li>
            </ul>
          </template>
        </el-alert>
        <h4>单项计提 ECL 率确定</h4>
        <el-table :data="d2.eclMeasurementItems?.value || []" size="small" border>
          <el-table-column prop="category" label="单项计提" width="120" />
          <el-table-column label="账面余额" width="110"><template #default="{ row }">{{ fmtAmount(row.balance) }}</template></el-table-column>
          <el-table-column label="估计现金流(1年)" width="120"><template #default="{ row }">{{ fmtAmount(row.cf1y) }}</template></el-table-column>
          <el-table-column label="估计现金流(2年)" width="120"><template #default="{ row }">{{ fmtAmount(row.cf2y) }}</template></el-table-column>
          <el-table-column label="折现值" width="110"><template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.discountedValue) }}</span></template></el-table-column>
          <el-table-column label="发生概率" width="90"><template #default="{ row }">{{ fmtPercent(row.probability) }}</template></el-table-column>
          <el-table-column label="ECL率" width="90"><template #default="{ row }"><span class="auto-calc">{{ fmtPercent(row.eclRate) }}</span></template></el-table-column>
        </el-table>
      </div>
    </el-tab-pane>
    <!-- Tab 11: 分析程序 D2-5 -->
    <el-tab-pane name="analysis" :lazy="true">
      <template #label><span :class="tabDotClass('analysis')">○</span> 分析程序 D2-5</template>
      <div class="d2-section">
        <div class="analysis-ratios">
          <span>周转率：{{ d2.analysisRatios.value.turnoverRate }}</span>
          <span>周转天数：{{ d2.analysisRatios.value.turnoverDays }}</span>
          <span>上期周转天数：{{ d2.analysisRatios.value.priorTurnoverDays }}</span>
          <span>坏账率：{{ fmtPercent(d2.analysisRatios.value.badDebtRate / 100) }}</span>
        </div>
        <el-alert v-if="d2.isTurnoverDaysWarning.value" type="warning" title="周转天数同比变化超过30%，需关注原因" :closable="false" show-icon style="margin:8px 0" />
        <div class="d2-sub-wp-placeholder">子底稿 D2-5 通过 GtWpRenderer 懒加载</div>
      </div>
    </el-tab-pane>
    <!-- Tab 12: 关联方 D2-6 -->
    <el-tab-pane name="related-party" :lazy="true">
      <template #label><span :class="tabDotClass('related-party')">○</span> 关联方 D2-6</template>
      <div class="d2-section">
        <div v-if="d2.matchedRelatedParties.value.length > 0" class="match-panel">
          <el-alert type="info" title="已匹配关联方" :closable="false" show-icon>
            <template #default><el-tag v-for="p in d2.matchedRelatedParties.value" :key="p" size="small" style="margin:2px">{{ p }}</el-tag></template>
          </el-alert>
        </div>
        <div class="d2-sub-wp-placeholder">子底稿 D2-6 通过 GtWpRenderer 懒加载</div>
      </div>
    </el-tab-pane>
    <!-- Tab 13: 保理分析 D2-12 -->
    <el-tab-pane name="factoring">
      <template #label><span :class="tabDotClass('factoring')">○</span> 保理分析 D2-12</template>
      <div class="d2-section">
        <div class="adj-header">
          <el-button size="small" type="primary" :disabled="review.isReadonly.value || d2.factoringItems.value.length >= 100" @click="d2.addFactoring({})">+ 新增</el-button>
          <span>质押比例：{{ fmtPercent(d2.pledgeRatio.value) }}</span>
        </div>
        <el-alert v-if="d2.isPledgeRatioWarning.value" type="warning" title="质押比例超50%，需关注流动性和披露" :closable="false" show-icon style="margin:8px 0" />
        <el-table :data="d2.factoringItems.value" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column prop="category" label="类别" width="80" />
          <el-table-column prop="customerName" label="客户" width="100" />
          <el-table-column label="金额" width="110"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column>
          <el-table-column prop="counterparty" label="对手方" width="100" />
          <el-table-column label="终止确认" width="120"><template #default="{ row }"><span v-if="row.derecognition">{{ row.derecognition }}</span></template></el-table-column>
          <el-table-column label="备注"><template #default="{ row }"><span v-if="row.derecognition === '不终止确认'" class="warning-text">应继续在资产负债表确认</span><span v-else>{{ row.remark }}</span></template></el-table-column>
          <el-table-column label="操作" width="60"><template #default="{ row }"><el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d2.removeFactoring(row.index)">删</el-button></template></el-table-column>
        </el-table>
        <div class="endorse-summary">
          <span>已质押：{{ fmtAmount(d2.factoringSummary.value.pledgedTotal) }}</span>
          <span>已保理：{{ fmtAmount(d2.factoringSummary.value.factoredTotal) }}</span>
          <span>终止确认：{{ fmtAmount(d2.factoringSummary.value.derecognizedAmount) }}</span>
          <span>不终止确认：{{ fmtAmount(d2.factoringSummary.value.notDerecognizedAmount) }}</span>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 14: 检查表 D2-7 -->
    <el-tab-pane name="general-check">
      <template #label><span :class="tabDotClass('general-check')">○</span> 检查表 D2-7</template>
      <div class="d2-section">
        <h3>应收账款检查表</h3>
        <p class="d2-audit-objective">审计目标：应收账款是存在的，记录于恰当账户，以恰当金额包括在财务报表中</p>
        <h4>样本选取</h4>
        <div class="d2-sample-params">
          <div class="check-row">
            <span class="check-label">测试总体：</span>
            <el-input size="small" :disabled="review.isReadonly.value" placeholder="如：借方发生额XX笔金额XX" style="flex:1" @input="(val: string) => onProcTextChange(0, 'd2-7-population', val)" />
          </div>
          <div class="check-row">
            <span class="check-label">抽样方法：</span>
            <el-select size="small" :disabled="review.isReadonly.value" placeholder="选择" style="width:200px" @change="(val: string) => onCheckChange('d2-7-method', 0, val)">
              <el-option value="随机选样" label="随机选样" />
              <el-option value="系统选样" label="系统选样" />
              <el-option value="货币单元抽样" label="货币单元抽样" />
              <el-option value="随意选样" label="随意选样（非统计）" />
            </el-select>
          </div>
        </div>
        <h4>本期增减变动检查</h4>
        <el-alert type="info" :closable="false" show-icon title="核对内容：1.原始凭证是否齐全 2.记账凭证与原始凭证是否相符 3.账务处理是否正确 4.是否记录于恰当的会计期间 5.其他" style="margin-bottom:8px" />
        <el-table :data="d2.voucherCheckSamples?.value || []" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column prop="customerName" label="客户名称" width="120" />
          <el-table-column prop="voucherDate" label="日期" width="100" />
          <el-table-column prop="voucherNo" label="凭证编号" width="100" />
          <el-table-column prop="content" label="业务内容" width="140" />
          <el-table-column prop="counterAccount" label="对方科目" width="100" />
          <el-table-column label="借方" width="100"><template #default="{ row }">{{ fmtAmount(row.debitAmount) }}</template></el-table-column>
          <el-table-column label="贷方" width="100"><template #default="{ row }">{{ fmtAmount(row.creditAmount) }}</template></el-table-column>
          <el-table-column label="1" width="40"><template #default="{ row }">{{ row.check1 || '' }}</template></el-table-column>
          <el-table-column label="2" width="40"><template #default="{ row }">{{ row.check2 || '' }}</template></el-table-column>
          <el-table-column label="3" width="40"><template #default="{ row }">{{ row.check3 || '' }}</template></el-table-column>
          <el-table-column label="4" width="40"><template #default="{ row }">{{ row.check4 || '' }}</template></el-table-column>
          <el-table-column label="5" width="40"><template #default="{ row }">{{ row.check5 || '' }}</template></el-table-column>
          <el-table-column prop="isAbnormal" label="异常" width="60" />
          <el-table-column prop="remark" label="备注" />
        </el-table>
        <el-button v-if="!review.isReadonly.value" size="small" type="primary" style="margin-top:8px" @click="d2.addVoucherCheckSample?.({})">+ 新增样本行</el-button>
      </div>
    </el-tab-pane>
    <!-- Tab 15: 会计政策 D2-8 -->
    <el-tab-pane name="policy-check">
      <template #label><span :class="tabDotClass('policy-check')">○</span> 会计政策 D2-8</template>
      <div class="d2-section">
        <h3>坏账准备计提会计政策检查</h3>
        <p class="d2-audit-objective">审计目标：验证坏账准备计提政策的合理性和一致性</p>
        <div class="d2-policy-sections">
          <div class="policy-block">
            <h4>（一）应收账款坏账准备计提会计政策</h4>
            <p class="policy-hint">说明被审计单位信用风险组合划分依据、预期信用损失计量方法等</p>
            <el-input type="textarea" :rows="4" :disabled="review.isReadonly.value" placeholder="描述被审计单位的坏账准备计提政策..." @input="(val: string) => onProcTextChange(0, 'd2-8-policy-desc', val)" />
          </div>
          <div class="policy-block">
            <h4>（二）被审计单位历史坏账损失情况</h4>
            <p class="policy-hint">说明历史损失率的数据来源，以及项目组核实该等数据所执行的程序。需考虑货币的时间价值</p>
            <el-input type="textarea" :rows="4" :disabled="review.isReadonly.value" placeholder="描述历史坏账损失数据及核实程序..." @input="(val: string) => onProcTextChange(0, 'd2-8-history', val)" />
          </div>
          <div class="policy-block">
            <h4>（三）前瞻性信息的来源及其影响</h4>
            <p class="policy-hint">说明预期损失率的前瞻性信息来源（内部模型/第三方/外部专家），以及项目组对前瞻性信息可靠性所执行的程序</p>
            <el-input type="textarea" :rows="4" :disabled="review.isReadonly.value" placeholder="描述前瞻性信息来源及核实程序..." @input="(val: string) => onProcTextChange(0, 'd2-8-forward', val)" />
          </div>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 16: 转回核销 D2-11 -->
    <el-tab-pane name="writeoff-check">
      <template #label><span :class="tabDotClass('writeoff-check')">○</span> 转回核销 D2-11</template>
      <div class="d2-section">
        <h3>大额坏账准备转回、核销检查表</h3>
        <p class="d2-audit-objective">审计目标：验证坏账准备转回/核销的合理性和完整性</p>
        <h4>（一）本期重要的坏账准备转回或转销检查</h4>
        <el-table :data="d2.writeoffReversalItems?.value || []" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column prop="companyName" label="单位名称" width="120" />
          <el-table-column prop="reversalReason" label="转回原因" width="140" />
          <el-table-column prop="recoveryMethod" label="收回方式" width="100" />
          <el-table-column prop="originalBasis" label="原确定坏账准备的依据" width="160" />
          <el-table-column label="收回/转回金额" width="120"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column>
          <el-table-column label="转回前累计已计提" width="130"><template #default="{ row }">{{ fmtAmount(row.priorProvision) }}</template></el-table-column>
          <el-table-column prop="reasonability" label="合理性分析" />
        </el-table>
        <el-button v-if="!review.isReadonly.value" size="small" type="primary" style="margin-top:8px" @click="d2.addWriteoffReversal?.({})">+ 新增转回记录</el-button>

        <h4 style="margin-top:16px">（二）本期重要的核销应收账款检查</h4>
        <el-table :data="d2.writeoffItems?.value || []" size="small" border>
          <el-table-column type="index" width="50" />
          <el-table-column prop="companyName" label="单位名称" width="120" />
          <el-table-column prop="nature" label="应收账款性质" width="120" />
          <el-table-column label="核销金额" width="110"><template #default="{ row }">{{ fmtAmount(row.amount) }}</template></el-table-column>
          <el-table-column prop="writeoffReason" label="核销原因" width="140" />
          <el-table-column prop="procedure" label="履行的核销程序" width="140" />
          <el-table-column prop="isRelatedParty" label="关联交易" width="80" />
          <el-table-column prop="reasonability" label="合理性分析" />
        </el-table>
        <el-button v-if="!review.isReadonly.value" size="small" type="primary" style="margin-top:8px" @click="d2.addWriteoffItem?.({})">+ 新增核销记录</el-button>
      </div>
    </el-tab-pane>
    <!-- Tab 17: 业务模式 D2-13 -->
    <el-tab-pane name="bizmodel-check">
      <template #label><span :class="tabDotClass('bizmodel-check')">○</span> 业务模式 D2-13</template>
      <div class="d2-section">
        <h3>应收账款业务模式分析</h3>
        <p class="d2-audit-objective">审计目标：验证应收账款金融资产分类的恰当性（CAS 22 / IFRS 9）</p>
        <h4>（一）应收账款业务模式及依据</h4>
        <el-table :data="d2.bizModelGroups?.value || []" size="small" border>
          <el-table-column prop="groupName" label="组合名称" width="160" />
          <el-table-column prop="bizModel" label="管理应收账款业务模式" width="220" />
          <el-table-column prop="basis" label="具体依据" />
        </el-table>
        <h4 style="margin-top:16px">（二）应收账款分类判断</h4>
        <el-table :data="d2.bizModelQuestions?.value || []" size="small" border>
          <el-table-column prop="question" label="了解并观察实际情况" width="380" />
          <el-table-column v-for="g in (d2.bizModelGroups?.value || []).slice(0, 3)" :key="g.groupName" :label="g.groupName" width="100">
            <template #default="{ row }">{{ row.answers?.[g.groupName] || '' }}</template>
          </el-table-column>
        </el-table>
        <div v-if="d2.bizModelConclusion?.value" class="biz-conclusion">
          <h4>分类结论</h4>
          <p>{{ d2.bizModelConclusion.value }}</p>
        </div>
      </div>
    </el-tab-pane>
  </el-tabs>
  <!-- 复核签字区 -->
  <div class="review-section">
    <h4>现场经理复核</h4>
    <div v-if="review.pendingItems.value.length > 0" class="pending-list">
      <p>待完成事项：</p>
      <ul><li v-for="(item, idx) in review.pendingItems.value" :key="idx">{{ item }}</li></ul>
    </div>
    <el-button v-if="!review.isReadonly.value" type="primary" :disabled="!review.canReview.value" @click="onReview">签字复核</el-button>
    <el-button v-if="review.isReviewed.value && !props.readonly" type="warning" plain @click="showAmendDialog = true">启动修改</el-button>
  </div>
  <!-- 修改原因对话框 -->
  <el-dialog v-model="showAmendDialog" title="启动修改" width="400px">
    <el-input v-model="amendReason" type="textarea" :rows="3" placeholder="请填写修改原因" />
    <template #footer>
      <el-button @click="showAmendDialog = false">取消</el-button>
      <el-button type="primary" :disabled="!amendReason.trim()" @click="onAmend">确定</el-button>
    </template>
  </el-dialog>
</div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { CircleCheckFilled } from '@element-plus/icons-vue'
import { useD2FormData } from './composables/useD2FormData'
import { useD2AccountsReceivable, type TabStatus } from './composables/useD2AccountsReceivable'
import { useD2Review } from './composables/useD2Review'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string
  year: number
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const { allResponses, loadAll, saveImmediate, saveDebouncedText, flushPendingSave, setFieldImmediate, loadSubWorkpaperData } =
  useD2FormData(toRef(props, 'wpId'), toRef(props, 'projectId'))

const d2 = useD2AccountsReceivable(
  allResponses,
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'year'),
  saveImmediate,
  computed(() => props.readonly ?? false),
  loadSubWorkpaperData
)

const review = useD2Review(
  allResponses,
  d2.procedureProgress,
  d2.canInputOverallConclusion,
  saveImmediate,
  computed(() => props.readonly ?? false)
)

// ─── Local UI State ──────────────────────────────────────────────────────────

const showAmendDialog = ref(false)
const amendReason = ref('')
const disclosureType = ref<'listed' | 'soe'>('listed')

// ─── Sheet Directory ─────────────────────────────────────────────────────────

const sheetDirectory = computed(() => [
  { code: 'D2A', name: '审计程序表' },
  { code: 'D2-1', name: '审定表' },
  { code: 'D2-2', name: '应收账款明细表' },
  { code: 'D2-3', name: '坏账准备计算表' },
  { code: 'D2-4', name: '调整分录汇总' },
  { code: 'D2-5', name: '分析程序' },
  { code: 'D2-6', name: '关联方检查' },
  { code: 'D2-7', name: '通用检查表' },
  { code: 'D2-8', name: 'ECL会计政策' },
  { code: 'D2-9', name: 'ECL测算' },
  { code: 'D2-10', name: '计量测试' },
  { code: 'D2-11', name: '转回核销' },
  { code: 'D2-12', name: '保理/质押分析' },
  { code: 'D2-13', name: '业务模式' },
  { code: 'D2-14', name: '附注披露(上市公司)' },
  { code: 'D2-15', name: '附注披露(国企)' },
  { code: 'D2-16', name: '函证联动' },
  { code: 'D2-17', name: '截止测试' },
  { code: 'D2-18', name: '替代程序' },
  { code: 'D2-19', name: '底稿目录' },
])

// ─── Computed ────────────────────────────────────────────────────────────────

const procPct = computed(() => {
  const { completed, total } = d2.procedureProgress.value
  return total > 0 ? Math.round(completed / total * 100) : 0
})

// ─── Formatters ──────────────────────────────────────────────────────────────

function fmtAmount(val: number | null | undefined): string {
  if (val === null || val === undefined) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPercent(val: number | '' | null | undefined): string {
  if (val === null || val === undefined || val === '') return '-'
  return (Number(val) * 100).toFixed(2) + '%'
}

// ─── Tab Status Helper ───────────────────────────────────────────────────────

function tabDotClass(tabName: string): string {
  const status: TabStatus = d2.tabCompletionStatus.value.get(tabName) || 'not-started'
  if (status === 'completed') return 'tab-dot tab-dot-completed'
  if (status === 'in-progress') return 'tab-dot tab-dot-progress'
  return 'tab-dot tab-dot-empty'
}

// ─── Event Handlers ──────────────────────────────────────────────────────────

function onProcTextChange(stepIdx: number, field: string, val: string): void {
  const n = stepIdx + 1
  const itemId = `D2-proc-${n}-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onOverallConclusionChange(val: string): void {
  const item = { item_id: 'D2-proc-overall', conclusion: null, remark: val }
  allResponses.value.set('D2-proc-overall', item)
  saveDebouncedText(item)
}

function onDisclosureChange(row: any): void {
  const prefix = disclosureType.value === 'soe' ? 'D2-disc-soe' : 'D2-disc-listed'
  const itemId = `${prefix}-${row.index}`
  setFieldImmediate(itemId, { conclusion: row.conclusion })
}

function onDisclosureRemarkChange(row: any): void {
  const prefix = disclosureType.value === 'soe' ? 'D2-disc-soe' : 'D2-disc-listed'
  const itemId = `${prefix}-${row.index}`
  const item = { item_id: itemId, conclusion: null, remark: row.remark }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onAdjChange(row: any): void {
  d2.updateAdjustment(row.index, { type: row.type })
}

function onAdjTextChange(row: any): void {
  d2.updateAdjustment(row.index, row)
}

function pushToA13(row: any): void {
  d2.publishAdjustmentCreated(row)
}

function onCheckChange(prefix: string, n: number, val: string): void {
  const itemId = `D2-${prefix}-${n}-conclusion`
  setFieldImmediate(itemId, { conclusion: val })
}

async function onReview(): Promise<void> {
  await review.doReview()
  emit('completed')
}

async function onAmend(): Promise<void> {
  if (!amendReason.value.trim()) return
  await review.startAmendment(amendReason.value)
  showAmendDialog.value = false
  amendReason.value = ''
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await loadAll()
  await d2.refreshSumifData()
})

onBeforeUnmount(() => {
  flushPendingSave()
  d2.unregisterEventListeners()
})

// Suppress unused
void emit
void props
</script>

<style scoped>
.d2-accounts-receivable { padding: 16px; max-width: 1400px; margin: 0 auto; }
.d2-accounts-receivable.is-readonly { pointer-events: auto; }
.reviewed-banner { background: #f6ffed; border: 1px solid #b7eb8f; border-radius: 4px; padding: 8px 16px; margin-bottom: 12px; display: flex; align-items: center; gap: 8px; color: #52c41a; font-weight: 500; }
.linkage-bar { display: flex; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.ref-chip { cursor: pointer; }
.d2-section { padding: 12px 0; }
.d2-sub-wp-placeholder { padding: 48px; text-align: center; color: #bfbfbf; font-size: 14px; border: 1px dashed #d9d9d9; border-radius: 8px; margin: 16px 0; }
.tab-dot { margin-right: 4px; font-size: 10px; }
.tab-dot-completed { color: #52c41a; }
.tab-dot-completed::before { content: '✓'; }
.tab-dot-progress { color: #1890ff; }
.tab-dot-progress::before { content: '●'; }
.tab-dot-empty { color: #bfbfbf; }
.tab-dot-empty::before { content: '○'; }
.progress-bar { margin-bottom: 16px; }
.risk-badges { margin-bottom: 12px; display: flex; gap: 6px; }
.procedure-card { border: 1px solid #f0f0f0; border-radius: 6px; margin-bottom: 10px; overflow: hidden; }
.procedure-card .card-header { display: flex; align-items: center; gap: 8px; padding: 10px 14px; background: #fafafa; }
.step-num { background: #1890ff; color: #fff; width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 12px; font-weight: 600; flex-shrink: 0; }
.step-name { font-weight: 500; font-size: 14px; }
.card-body-proc { padding: 10px 14px; display: flex; flex-wrap: wrap; gap: 8px; }
.overall-conclusion { margin-top: 20px; padding: 16px; background: #f9f9f9; border-radius: 8px; }
.overall-conclusion h4 { margin: 0 0 8px; }
.cross-ref { background: #e6f7ff; padding: 2px 4px; border-radius: 2px; }
.auto-calc { color: #8c8c8c; font-style: italic; }
.ecl-header { display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }
.migration-matrix { margin-bottom: 16px; }
.ecl-summary { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; padding: 12px; background: #fafafa; border-radius: 6px; }
.diff-exceed { color: #ff4d4f; font-weight: 600; }
.adj-header { display: flex; align-items: center; gap: 16px; margin-bottom: 12px; }
.adj-totals { font-size: 13px; color: #666; }
.endorse-summary { margin-top: 12px; display: flex; gap: 16px; font-size: 13px; flex-wrap: wrap; }
.warning-text { color: #ff4d4f; font-size: 12px; }
.check-row { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.check-label { min-width: 200px; font-size: 13px; }
.match-panel { margin-bottom: 8px; }
.confirmation-panel { margin-top: 12px; display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; padding: 12px; background: #f0f9ff; border-radius: 6px; }
.analysis-ratios { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; margin-bottom: 12px; }
.review-section { border-top: 1px solid #f0f0f0; padding-top: 16px; margin-top: 16px; }
.review-section h4 { margin: 0 0 8px; }
.pending-list { margin-bottom: 12px; font-size: 13px; color: #666; }
.pending-list ul { margin: 4px 0; padding-left: 20px; }
.d2-audit-objective { font-size: 12px; color: #666; margin: 4px 0 16px; padding: 8px 12px; background: #f5f5f5; border-radius: 4px; border-left: 3px solid #1890ff; }
.d2-sample-params { margin-bottom: 16px; }
.d2-policy-sections { display: flex; flex-direction: column; gap: 16px; }
.policy-block h4 { margin: 0 0 4px; }
.policy-hint { font-size: 12px; color: #999; margin: 0 0 8px; }
.d2-ecl-notes { margin: 4px 0 0 16px; font-size: 12px; line-height: 1.8; }
.biz-conclusion { margin-top: 12px; padding: 12px; background: #f6ffed; border-radius: 6px; border: 1px solid #b7eb8f; }
.biz-conclusion h4 { margin: 0 0 4px; }
</style>
