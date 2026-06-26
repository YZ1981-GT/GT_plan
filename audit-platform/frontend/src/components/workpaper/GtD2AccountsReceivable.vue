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
      <div class="d2-section"><p>ECL 测算面板（迁徙率法 / 个别认定）</p></div>
    </el-tab-pane>
    <!-- Tab 10: 计量测试 D2-10 -->
    <el-tab-pane name="ecl-measurement" :lazy="true">
      <template #label><span :class="tabDotClass('ecl-measurement')">○</span> 计量测试 D2-10</template>
      <div class="d2-section"><p>ECL 计量测试面板</p></div>
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
        <h4>应收账款通用检查</h4>
        <div v-for="n in 8" :key="n" class="check-row">
          <span class="check-label">{{ n }}. 检查项{{ n }}</span>
          <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="(val: string) => onCheckChange('check7', n, val)">
            <el-option value="符合" label="符合" />
            <el-option value="不符合" label="不符合" />
            <el-option value="不适用" label="不适用" />
          </el-select>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 15: 会计政策 D2-8 -->
    <el-tab-pane name="policy-check">
      <template #label><span :class="tabDotClass('policy-check')">○</span> 会计政策 D2-8</template>
      <div class="d2-section">
        <h4>ECL 会计政策一致性检查</h4>
        <div v-for="n in 5" :key="'policy-'+n" class="check-row">
          <span class="check-label">{{ n }}. 政策检查项{{ n }}</span>
          <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="(val: string) => onCheckChange('policy', n, val)">
            <el-option value="符合" label="符合" />
            <el-option value="不符合" label="不符合" />
            <el-option value="不适用" label="不适用" />
          </el-select>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 16: 转回核销 D2-11 -->
    <el-tab-pane name="writeoff-check">
      <template #label><span :class="tabDotClass('writeoff-check')">○</span> 转回核销 D2-11</template>
      <div class="d2-section">
        <h4>转回核销检查</h4>
        <div v-for="n in 4" :key="'wo-'+n" class="check-row">
          <span class="check-label">{{ n }}. 转回核销检查项{{ n }}</span>
          <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="(val: string) => onCheckChange('writeoff', n, val)">
            <el-option value="符合" label="符合" />
            <el-option value="不符合" label="不符合" />
            <el-option value="不适用" label="不适用" />
          </el-select>
        </div>
      </div>
    </el-tab-pane>
    <!-- Tab 17: 业务模式 D2-13 -->
    <el-tab-pane name="bizmodel-check">
      <template #label><span :class="tabDotClass('bizmodel-check')">○</span> 业务模式 D2-13</template>
      <div class="d2-section">
        <h4>业务模式分析检查</h4>
        <div v-for="n in 5" :key="'biz-'+n" class="check-row">
          <span class="check-label">{{ n }}. 业务模式检查项{{ n }}</span>
          <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="(val: string) => onCheckChange('bizmodel', n, val)">
            <el-option value="符合" label="符合" />
            <el-option value="不符合" label="不符合" />
            <el-option value="不适用" label="不适用" />
          </el-select>
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
</style>
