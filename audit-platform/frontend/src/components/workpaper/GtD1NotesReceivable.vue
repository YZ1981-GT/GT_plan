<template>
  <div class="d1-notes-receivable" :class="{ 'is-readonly': review.isReadonly.value }">
    <!-- 已复核横幅 -->
    <div v-if="review.isReviewed.value" class="reviewed-banner">
      <el-icon><CircleCheckFilled /></el-icon>
      <span>已复核 — {{ review.reviewInfo.value?.reviewer }} {{ review.reviewInfo.value?.date }}</span>
    </div>

    <!-- 联动面板 ref_chips -->
    <div class="linkage-bar">
      <el-tag v-for="link in d1.linkageRefs.value" :key="link.targetWpCode" type="info" class="ref-chip">
        {{ link.icon }} {{ link.label }}
      </el-tag>
    </div>

    <!-- 主 Tabs -->
    <el-tabs v-model="d1.activeTab.value" @tab-change="d1.setActiveTab">
      <!-- Tab 1: 底稿目录 -->
      <el-tab-pane name="directory">
        <template #label><span :class="tabDotClass('directory')">○</span> 底稿目录</template>
        <div class="d1-section">
          <h3>D1 应收票据底稿目录</h3>
          <el-table :data="sheetDirectory" size="small" border stripe>
            <el-table-column prop="code" label="编号" width="80" />
            <el-table-column prop="name" label="名称" />
            <el-table-column label="状态" width="100">
              <template #default="{ row }">
                <el-tag :type="row.statusType" size="small">{{ row.statusLabel }}</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 2: 程序表 D1A -->
      <el-tab-pane name="procedure">
        <template #label><span :class="tabDotClass('procedure')">○</span> 程序表 D1A</template>
        <div class="d1-section">
          <!-- 进度条 -->
          <div class="progress-bar">
            <span>审计程序进度：{{ d1.procedureProgress.value.completed }}/{{ d1.procedureProgress.value.total }}</span>
            <el-progress :percentage="Math.round(d1.procedureProgress.value.completed / d1.procedureProgress.value.total * 100)" :stroke-width="10" />
          </div>
          <!-- 风险标识 -->
          <div v-if="d1.riskIndicators.value.size > 0" class="risk-badges">
            <el-tag v-for="[, ri] in d1.riskIndicators.value" :key="ri.description" :type="ri.level === 'H' ? 'danger' : ri.level === 'M' ? 'warning' : 'success'" size="small">
              {{ ri.level === 'H' ? '高风险' : ri.level === 'M' ? '中风险' : '低风险' }} {{ ri.description }}
            </el-tag>
          </div>
          <!-- 8步骤卡片 -->
          <div v-for="(step, idx) in d1.procedureSteps.value" :key="step.stepOrder" class="procedure-card">
            <div class="card-header">
              <span class="step-num">{{ step.stepOrder }}</span>
              <span class="step-name">{{ step.stepName }}</span>
              <el-tag v-if="step.relatedTab" size="small" type="info" class="ref-chip" @click="d1.setActiveTab(step.relatedTab!)">→{{ step.relatedTab }}</el-tag>
              <el-select v-model="step.status" size="small" :disabled="review.isReadonly.value" style="width:100px;margin-left:auto" @change="(val: string) => d1.setProcedureStatus(idx, val as any)">
                <el-option value="未开始" label="未开始" />
                <el-option value="执行中" label="执行中" />
                <el-option value="已完成" label="已完成" />
                <el-option value="不适用" label="不适用" />
              </el-select>
            </div>
            <div class="card-body-proc">
              <el-input v-model="step.executor" size="small" placeholder="执行人" :disabled="review.isReadonly.value" style="width:120px" @input="onProcTextChange(idx, 'executor', $event)" />
              <el-input v-model="step.executeDate" size="small" placeholder="日期" :disabled="review.isReadonly.value" style="width:120px" @input="onProcTextChange(idx, 'date', $event)" />
              <el-input v-model="step.findings" type="textarea" :rows="2" placeholder="审计发现" :disabled="review.isReadonly.value" @input="onProcTextChange(idx, 'findings', $event)" />
              <el-input v-model="step.conclusion" type="textarea" :rows="2" placeholder="结论" :disabled="review.isReadonly.value" @input="onProcTextChange(idx, 'conclusion', $event)" />
            </div>
          </div>
          <!-- 整体结论 -->
          <div class="overall-conclusion">
            <h4>整体审计结论</h4>
            <el-input v-model="d1.overallConclusion.value" type="textarea" :rows="3" :disabled="review.isReadonly.value || !d1.canInputOverallConclusion.value" placeholder="全部必要步骤完成后可录入整体结论" @input="onOverallConclusionChange" />
            <el-alert v-if="!d1.canInputOverallConclusion.value" type="info" :closable="false" title="需完成所有必要审计步骤后方可录入整体结论" show-icon />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 3: 审定表 D1-1 -->
      <el-tab-pane name="adjudication">
        <template #label><span :class="tabDotClass('adjudication')">○</span> 审定表 D1-1</template>
        <div class="d1-section">
          <h3>应收票据审定表</h3>
          <el-table :data="d1.adjudicationRows.value" size="small" border>
            <el-table-column prop="label" label="项目" width="180" fixed />
            <el-table-column label="期初数" width="120">
              <template #default="{ row }">
                <span :class="{ 'cross-ref': row.isFromCrossSheet }">{{ fmtAmount(row.priorPeriod) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期末未审数" width="120">
              <template #default="{ row }">
                <span :class="{ 'cross-ref': row.isFromCrossSheet }">{{ fmtAmount(row.currentUnadjusted) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="变动" width="100">
              <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.periodChange) }}</span></template>
            </el-table-column>
            <el-table-column label="AJE借" width="100">
              <template #default="{ row }">{{ fmtAmount(row.ajeDebit) }}</template>
            </el-table-column>
            <el-table-column label="AJE贷" width="100">
              <template #default="{ row }">{{ fmtAmount(row.ajeCredit) }}</template>
            </el-table-column>
            <el-table-column label="RJE借" width="100">
              <template #default="{ row }">{{ fmtAmount(row.rjeDebit) }}</template>
            </el-table-column>
            <el-table-column label="RJE贷" width="100">
              <template #default="{ row }">{{ fmtAmount(row.rjeCredit) }}</template>
            </el-table-column>
            <el-table-column label="审定数" width="120">
              <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.auditedAmount) }}</span></template>
            </el-table-column>
            <el-table-column label="变动率" width="100">
              <template #default="{ row }"><span class="auto-calc">{{ row.changeRate === '' ? '-' : fmtPercent(row.changeRate) }}</span></template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 4: 附注披露 -->
      <el-tab-pane name="disclosure">
        <template #label><span :class="tabDotClass('disclosure')">○</span> 附注披露</template>
        <div class="d1-section">
          <el-radio-group v-model="disclosureType" size="small" :disabled="review.isReadonly.value">
            <el-radio-button value="listed">上市公司</el-radio-button>
            <el-radio-button value="soe">国企</el-radio-button>
          </el-radio-group>
          <el-alert v-if="d1.hasUndisclosedItems.value" type="error" title="存在未披露需补充事项，请关注！" :closable="false" show-icon style="margin:12px 0" />
          <el-table :data="d1.disclosureItems.value" size="small" border style="margin-top:12px">
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

      <!-- Tab 5: 原值明细 D1-2 -->
      <el-tab-pane name="detail-category">
        <template #label><span :class="tabDotClass('detail-category')">○</span> D1-2 原值(类别)</template>
        <div class="d1-sub-wp-placeholder">子底稿 D1-2 通过 GtWpRenderer 懒加载</div>
      </el-tab-pane>

      <!-- Tab 6: 原值明细 D1-3 -->
      <el-tab-pane name="detail-customer">
        <template #label><span :class="tabDotClass('detail-customer')">○</span> D1-3 原值(客户)</template>
        <div class="d1-sub-wp-placeholder">子底稿 D1-3 通过 GtWpRenderer 懒加载</div>
      </el-tab-pane>

      <!-- Tab 7: 坏账准备 D1-4 -->
      <el-tab-pane name="bad-debt">
        <template #label><span :class="tabDotClass('bad-debt')">○</span> 坏账准备 D1-4</template>
        <div class="d1-section">
          <div class="ecl-header">
            <span>ECL方法：</span>
            <el-radio-group :model-value="d1.eclMethod.value" size="small" :disabled="review.isReadonly.value" @change="(val: string) => d1.setEclMethod(val as any)">
              <el-radio-button value="组合评估">组合评估</el-radio-button>
              <el-radio-button value="个别认定">个别认定</el-radio-button>
            </el-radio-group>
          </div>
          <!-- 迁徙率矩阵 -->
          <div v-if="d1.eclMethod.value === '组合评估'" class="migration-matrix">
            <h4>迁徙率矩阵</h4>
            <el-table :data="d1.migrationRateMatrix.value" size="small" border>
              <el-table-column prop="fromBand" label="从" width="120" />
              <el-table-column prop="toBand" label="到" width="120" />
              <el-table-column prop="year1Rate" label="第1年" width="90">
                <template #default="{ row }">{{ fmtPercent(row.year1Rate) }}</template>
              </el-table-column>
              <el-table-column prop="year2Rate" label="第2年" width="90">
                <template #default="{ row }">{{ fmtPercent(row.year2Rate) }}</template>
              </el-table-column>
              <el-table-column prop="year3Rate" label="第3年" width="90">
                <template #default="{ row }">{{ fmtPercent(row.year3Rate) }}</template>
              </el-table-column>
              <el-table-column prop="averageRate" label="平均" width="90">
                <template #default="{ row }"><span class="auto-calc">{{ fmtPercent(row.averageRate) }}</span></template>
              </el-table-column>
            </el-table>
          </div>
          <!-- 账龄段表 -->
          <h4>账龄段明细</h4>
          <el-table :data="d1.agingBands.value" size="small" border>
            <el-table-column prop="label" label="账龄段" width="120" fixed />
            <el-table-column prop="endBalance" label="期末余额" width="110">
              <template #default="{ row }">{{ fmtAmount(row.endBalance) }}</template>
            </el-table-column>
            <el-table-column prop="expectedLossRate" label="预期损失率" width="100">
              <template #default="{ row }">{{ fmtPercent(row.expectedLossRate) }}</template>
            </el-table-column>
            <el-table-column prop="shouldProvision" label="应计提" width="110">
              <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.shouldProvision) }}</span></template>
            </el-table-column>
            <el-table-column prop="actualProvision" label="实际计提" width="110">
              <template #default="{ row }">{{ fmtAmount(row.actualProvision) }}</template>
            </el-table-column>
            <el-table-column label="差异" width="110">
              <template #default="{ row }">
                <span :class="{ 'diff-exceed': Math.abs(row.difference) > 0 }">{{ fmtAmount(row.difference) }}</span>
              </template>
            </el-table-column>
          </el-table>
          <!-- ECL 汇总 -->
          <div class="ecl-summary">
            <span>总余额：{{ fmtAmount(d1.eclSummary.value.totalEndBalance) }}</span>
            <span>应计提：{{ fmtAmount(d1.eclSummary.value.totalShouldProvision) }}</span>
            <span>实际计提：{{ fmtAmount(d1.eclSummary.value.totalActualProvision) }}</span>
            <span :class="{ 'diff-exceed': d1.eclSummary.value.exceedsMateriality }">差异：{{ fmtAmount(d1.eclSummary.value.totalDifference) }}</span>
            <el-alert v-if="d1.eclSummary.value.exceedsMateriality" type="error" title="差异超过重要性水平！" :closable="false" show-icon />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 8: 调整分录 D1-5 -->
      <el-tab-pane name="adjustment">
        <template #label><span :class="tabDotClass('adjustment')">○</span> 调整分录 D1-5</template>
        <div class="d1-section">
          <div class="adj-header">
            <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d1.addAdjustment({})">+ 新增分录</el-button>
            <span class="adj-totals">AJE合计：{{ fmtAmount(d1.ajeTotal.value) }} | RJE合计：{{ fmtAmount(d1.rjeTotal.value) }}</span>
          </div>
          <el-table :data="d1.adjustmentEntries.value" size="small" border>
            <el-table-column type="index" width="50" />
            <el-table-column label="类型" width="90">
              <template #default="{ row }">
                <el-select v-model="row.type" size="small" :disabled="review.isReadonly.value" @change="onAdjChange(row)">
                  <el-option value="AJE" label="AJE" />
                  <el-option value="RJE" label="RJE" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="借方科目" width="140">
              <template #default="{ row }">
                <el-input v-model="row.debitAccount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="贷方科目" width="140">
              <template #default="{ row }">
                <el-input v-model="row.creditAccount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="金额" width="120">
              <template #default="{ row }">
                <el-input v-model="row.amount" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="摘要">
              <template #default="{ row }">
                <el-input v-model="row.description" size="small" :disabled="review.isReadonly.value" @input="onAdjTextChange(row)" />
              </template>
            </el-table-column>
            <el-table-column label="操作" width="140">
              <template #default="{ row }">
                <el-button size="small" type="primary" plain :disabled="review.isReadonly.value" @click="pushToA13(row)">推送A13</el-button>
                <el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d1.removeAdjustment(row.index)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 9: 业务模式 D1-6 -->
      <el-tab-pane name="business-model">
        <template #label><span :class="tabDotClass('business-model')">○</span> 业务模式 D1-6</template>
        <div class="d1-section">
          <!-- 到期分析 -->
          <h4>到期分析</h4>
          <el-table :data="d1.maturityAnalysis.value" size="small" border>
            <el-table-column prop="label" label="分组" width="140" />
            <el-table-column label="金额" width="140">
              <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
            </el-table-column>
            <el-table-column label="占比" width="100">
              <template #default="{ row }">{{ fmtPercent(row.percentage) }}</template>
            </el-table-column>
          </el-table>
          <el-alert v-if="d1.hasOverdue90Plus.value" type="error" title="存在逾期90天以上票据，请重点关注！" :closable="false" show-icon style="margin:12px 0" />
          <!-- SPPI 检查 -->
          <h4>SPPI 合同现金流量特征测试</h4>
          <el-radio-group :model-value="d1.sppiTestResult.value" size="small" :disabled="review.isReadonly.value" @change="(val: string) => d1.setSppiTestResult(val as any)">
            <el-radio-button value="Y">通过 (Y)</el-radio-button>
            <el-radio-button value="N">未通过 (N)</el-radio-button>
          </el-radio-group>
          <!-- 业务模式分类 -->
          <h4 style="margin-top:16px">业务模式分类</h4>
          <el-select :model-value="d1.businessModelChoice.value" size="small" :disabled="review.isReadonly.value" placeholder="请选择业务模式" @change="(val: string) => d1.setBusinessModelChoice(val as any)">
            <el-option value="以摊余成本计量" label="以摊余成本计量" />
            <el-option value="以公允价值计量且变动计入其他综合收益" label="以公允价值计量且变动计入其他综合收益" />
            <el-option value="以公允价值计量且变动计入当期损益" label="以公允价值计量且变动计入当期损益" />
          </el-select>
          <el-alert v-if="d1.suggestedClassification.value" :type="d1.sppiTestResult.value === 'N' ? 'warning' : 'success'" :title="d1.suggestedClassification.value" :closable="false" show-icon style="margin-top:12px" />
        </div>
      </el-tab-pane>

      <!-- Tab 10: 备查簿核对 D1-7 -->
      <el-tab-pane name="ledger-reconciliation">
        <template #label><span :class="tabDotClass('ledger-reconciliation')">○</span> 备查簿 D1-7</template>
        <div class="d1-section">
          <h4>备查簿核对检查</h4>
          <div v-for="n in 5" :key="n" class="check-row">
            <span>{{ n }}. 核对项目{{ n }}</span>
            <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论">
              <el-option value="符合" label="符合" />
              <el-option value="不符合" label="不符合" />
              <el-option value="不适用" label="不适用" />
            </el-select>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 11: 背书贴现 D1-8 -->
      <el-tab-pane name="endorsement">
        <template #label><span :class="tabDotClass('endorsement')">○</span> 背书贴现 D1-8</template>
        <div class="d1-section">
          <div class="adj-header">
            <el-button size="small" type="primary" :disabled="review.isReadonly.value || d1.endorsementItems.value.length >= 100" @click="d1.addEndorsement({})">+ 新增</el-button>
          </div>
          <el-table :data="d1.endorsementItems.value" size="small" border>
            <el-table-column type="index" width="50" />
            <el-table-column prop="noteNo" label="票据编号" width="120" />
            <el-table-column prop="drawer" label="出票人" width="100" />
            <el-table-column label="金额" width="110">
              <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="maturityDate" label="到期日" width="100" />
            <el-table-column prop="transferee" label="受让人" width="100" />
            <el-table-column label="终止确认" width="120">
              <template #default="{ row }">
                <el-select v-model="row.derecognition" size="small" :disabled="review.isReadonly.value" placeholder="判断">
                  <el-option value="终止确认" label="终止确认" />
                  <el-option value="不终止确认" label="不终止确认" />
                </el-select>
              </template>
            </el-table-column>
            <el-table-column label="备注">
              <template #default="{ row }">
                <span v-if="row.derecognition === '不终止确认'" class="warning-text">应作为表外事项披露</span>
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d1.removeEndorsement(row.index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <!-- 汇总 -->
          <div class="endorse-summary">
            <span>已背书未到期：{{ fmtAmount(d1.endorsementSummary.value.endorsedNotMatured) }}</span>
            <span>已贴现未到期：{{ fmtAmount(d1.endorsementSummary.value.discountedNotMatured) }}</span>
            <span>终止确认：{{ fmtAmount(d1.endorsementSummary.value.derecognizedAmount) }}</span>
            <span>不终止确认：{{ fmtAmount(d1.endorsementSummary.value.notDerecognizedAmount) }}</span>
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 12: 贴息 D1-9 -->
      <el-tab-pane name="interest">
        <template #label><span :class="tabDotClass('interest')">○</span> 贴息 D1-9</template>
        <div class="d1-section">
          <div class="adj-header">
            <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d1.addDiscountInterest({})">+ 新增</el-button>
          </div>
          <el-table :data="d1.discountInterestItems.value" size="small" border>
            <el-table-column type="index" width="50" />
            <el-table-column label="贴现金额(P)" width="120">
              <template #default="{ row }">{{ fmtAmount(row.discountAmount) }}</template>
            </el-table-column>
            <el-table-column label="贴现率(R)" width="100">
              <template #default="{ row }">{{ fmtPercent(row.discountRate) }}</template>
            </el-table-column>
            <el-table-column label="天数(D)" width="80">
              <template #default="{ row }">{{ row.discountDays }}</template>
            </el-table-column>
            <el-table-column label="单位贴息" width="120">
              <template #default="{ row }">{{ fmtAmount(row.auditeeInterest) }}</template>
            </el-table-column>
            <el-table-column label="审计师复核" width="120">
              <template #default="{ row }"><span class="auto-calc">{{ fmtAmount(row.auditorInterest) }}</span></template>
            </el-table-column>
            <el-table-column label="差异" width="110">
              <template #default="{ row }">
                <span :class="{ 'diff-exceed': Math.abs(row.difference) > 0.01 }">{{ fmtAmount(row.difference) }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 13: 监盘 D1-10 -->
      <el-tab-pane name="inventory">
        <template #label><span :class="tabDotClass('inventory')">○</span> 监盘 D1-10</template>
        <div class="d1-section">
          <h4>票据监盘倒推</h4>
          <el-form label-width="120px" size="small">
            <el-form-item label="盘点日期">
              <el-input :model-value="d1.inventoryReconciliation.value.countDate" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('countDate', $event)" />
            </el-form-item>
            <el-form-item label="盘点地点">
              <el-input :model-value="d1.inventoryReconciliation.value.countLocation" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('countLocation', $event)" />
            </el-form-item>
            <el-form-item label="盘点日余额">
              <el-input :model-value="String(d1.inventoryReconciliation.value.countBalance)" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('countBalance', $event)" />
            </el-form-item>
            <el-form-item label="期间增加">
              <el-input :model-value="String(d1.inventoryReconciliation.value.additions)" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('additions', $event)" />
            </el-form-item>
            <el-form-item label="期间减少">
              <el-input :model-value="String(d1.inventoryReconciliation.value.deductions)" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('deductions', $event)" />
            </el-form-item>
            <el-form-item label="倒推余额">
              <span class="auto-calc">{{ fmtAmount(d1.inventoryReconciliation.value.bsDateBalance) }}</span>
            </el-form-item>
            <el-form-item label="账面余额">
              <el-input :model-value="String(d1.inventoryReconciliation.value.bookBalance)" :disabled="review.isReadonly.value" style="width:200px" @input="onInventoryChange('bookBalance', $event)" />
            </el-form-item>
            <el-form-item label="差异">
              <span :class="{ 'diff-exceed': d1.inventoryReconciliation.value.difference !== 0 }">{{ fmtAmount(d1.inventoryReconciliation.value.difference) }}</span>
            </el-form-item>
          </el-form>
          <el-alert v-if="d1.inventoryReconciliation.value.difference !== 0" type="warning" title="监盘差异非零，请核实数据" :closable="false" show-icon />
        </div>
      </el-tab-pane>

      <!-- Tab 14: 关联方 D1-11 -->
      <el-tab-pane name="related-party">
        <template #label><span :class="tabDotClass('related-party')">○</span> 关联方 D1-11</template>
        <div class="d1-section">
          <div class="adj-header">
            <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d1.addRelatedParty({})">+ 新增</el-button>
          </div>
          <!-- 自动匹配面板 -->
          <div v-if="d1.matchedRelatedParties.value.length > 0" class="match-panel">
            <el-alert type="info" title="已自动匹配关联方" :closable="false" show-icon>
              <template #default>
                <el-tag v-for="p in d1.matchedRelatedParties.value" :key="p" size="small" style="margin:2px">{{ p }}</el-tag>
              </template>
            </el-alert>
          </div>
          <el-table :data="d1.relatedPartyItems.value" size="small" border style="margin-top:8px">
            <el-table-column type="index" width="50" />
            <el-table-column prop="partyName" label="关联方" width="120" />
            <el-table-column prop="relationType" label="关系类型" width="100" />
            <el-table-column label="金额" width="120">
              <template #default="{ row }">
                <span :class="{ 'diff-exceed': row.transactionAmount > 0 }">{{ fmtAmount(row.transactionAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="noteNo" label="票据编号" width="120" />
            <el-table-column label="正常条款" width="80">
              <template #default="{ row }">{{ row.isNormalTerms ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column prop="remark" label="备注" />
            <el-table-column label="操作" width="60">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d1.removeRelatedParty(row.index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 15: 质押 D1-12 -->
      <el-tab-pane name="pledge">
        <template #label><span :class="tabDotClass('pledge')">○</span> 质押 D1-12</template>
        <div class="d1-section">
          <div class="adj-header">
            <el-button size="small" type="primary" :disabled="review.isReadonly.value" @click="d1.addPledge({})">+ 新增</el-button>
            <span>质押比例：{{ fmtPercent(d1.pledgeRatio.value) }} | 合计：{{ fmtAmount(d1.pledgeTotalAmount.value) }}</span>
          </div>
          <el-alert v-if="d1.isPledgeRatioWarning.value" type="warning" title="质押比例超50%，需关注流动性和披露" :closable="false" show-icon style="margin:8px 0" />
          <el-table :data="d1.pledgeItems.value" size="small" border>
            <el-table-column type="index" width="50" />
            <el-table-column prop="noteNo" label="票据编号" width="120" />
            <el-table-column label="金额" width="120">
              <template #default="{ row }">{{ fmtAmount(row.amount) }}</template>
            </el-table-column>
            <el-table-column prop="pledgee" label="质押对象" width="120" />
            <el-table-column prop="purpose" label="用途" />
            <el-table-column prop="releaseDate" label="解质押日" width="100" />
            <el-table-column label="限制性" width="70">
              <template #default="{ row }">{{ row.isRestricted ? '是' : '否' }}</template>
            </el-table-column>
            <el-table-column label="操作" width="60">
              <template #default="{ row }">
                <el-button size="small" type="danger" plain :disabled="review.isReadonly.value" @click="d1.removePledge(row.index)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- Tab 16: 检查表 D1-13 -->
      <el-tab-pane name="general-check">
        <template #label><span :class="tabDotClass('general-check')">○</span> 检查表 D1-13</template>
        <div class="d1-section">
          <h4>一般检查事项</h4>
          <div v-for="n in 8" :key="n" class="check-row">
            <span class="check-label">{{ n }}. 检查项{{ n }}</span>
            <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="onCheckChange('check', n, $event)">
              <el-option value="符合" label="符合" />
              <el-option value="不符合" label="不符合" />
              <el-option value="不适用" label="不适用" />
            </el-select>
            <el-input size="small" placeholder="备注" :disabled="review.isReadonly.value" style="width:200px" />
          </div>
        </div>
      </el-tab-pane>

      <!-- Tab 17: ECL政策/测试/转回 -->
      <el-tab-pane name="ecl-policy">
        <template #label><span :class="tabDotClass('ecl-policy')">○</span> ECL政策 D1-14~16</template>
        <div class="d1-section">
          <h4>D1-14 ECL会计政策一致性检查</h4>
          <div v-for="n in 5" :key="'policy-'+n" class="check-row">
            <span class="check-label">{{ n }}. 政策一致性检查项{{ n }}</span>
            <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="onCheckChange('policy', n, $event)">
              <el-option value="符合" label="符合" />
              <el-option value="不符合" label="不符合" />
              <el-option value="不适用" label="不适用" />
            </el-select>
          </div>
          <h4 style="margin-top:24px">D1-15 ECL测试数据</h4>
          <el-form label-width="140px" size="small">
            <el-form-item label="测试样本量"><el-input :disabled="review.isReadonly.value" style="width:200px" /></el-form-item>
            <el-form-item label="偏差数"><el-input :disabled="review.isReadonly.value" style="width:200px" /></el-form-item>
          </el-form>
          <h4 style="margin-top:24px">D1-16 转回核销检查</h4>
          <div v-for="n in 4" :key="'writeoff-'+n" class="check-row">
            <span class="check-label">{{ n }}. 转回核销检查项{{ n }}</span>
            <el-select size="small" :disabled="review.isReadonly.value" placeholder="结论" @change="onCheckChange('writeoff', n, $event)">
              <el-option value="符合" label="符合" />
              <el-option value="不符合" label="不符合" />
              <el-option value="不适用" label="不适用" />
            </el-select>
          </div>
        </div>
      </el-tab-pane>

      <!-- Placeholder tabs for ecl-test and writeoff (combined in ecl-policy above, but keep tab names for status tracking) -->
      <el-tab-pane name="ecl-test" :lazy="true">
        <template #label><span :class="tabDotClass('ecl-test')">○</span> ECL测试</template>
        <div class="d1-section"><p>ECL测试数据已合并至"ECL政策 D1-14~16"Tab</p></div>
      </el-tab-pane>

      <el-tab-pane name="writeoff" :lazy="true">
        <template #label><span :class="tabDotClass('writeoff')">○</span> 转回核销</template>
        <div class="d1-section"><p>转回核销检查已合并至"ECL政策 D1-14~16"Tab</p></div>
      </el-tab-pane>
    </el-tabs>

    <!-- 复核签字区 -->
    <div class="review-section">
      <h4>现场经理复核</h4>
      <div v-if="review.pendingItems.value.length > 0" class="pending-list">
        <p>待完成事项：</p>
        <ul>
          <li v-for="(item, idx) in review.pendingItems.value" :key="idx">{{ item }}</li>
        </ul>
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
import { useD1FormData } from './composables/useD1FormData'
import { useD1NotesReceivable, type TabStatus } from './composables/useD1NotesReceivable'
import { useD1Review } from './composables/useD1Review'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode: string  // "D1"
  year: number
  readonly?: boolean
}>()

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── Composables ─────────────────────────────────────────────────────────────

const { allResponses, loading, saving, loadAll, saveImmediate, saveDebouncedText, flushPendingSave, getField, setFieldImmediate, writebackTrialBalance, loadSubWorkpaperData } =
  useD1FormData(toRef(props, 'wpId'), toRef(props, 'projectId'))

const d1 = useD1NotesReceivable(
  allResponses,
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'year'),
  saveImmediate,
  computed(() => props.readonly ?? false),
  loadSubWorkpaperData
)

const review = useD1Review(
  allResponses,
  d1.procedureProgress,
  d1.canInputOverallConclusion,
  saveImmediate,
  computed(() => props.readonly ?? false)
)

// ─── Local UI State ──────────────────────────────────────────────────────────

const showAmendDialog = ref(false)
const amendReason = ref('')
const disclosureType = ref<'listed' | 'soe'>('listed')

// ─── Sheet Directory ─────────────────────────────────────────────────────────

const sheetDirectory = computed(() => {
  const sheets = [
    { code: 'D1A', name: '审计程序表' },
    { code: 'D1-1', name: '审定表' },
    { code: 'D1-2', name: '原值明细表(按类别)' },
    { code: 'D1-3', name: '原值明细表(按客户)' },
    { code: 'D1-4', name: '坏账准备计算表' },
    { code: 'D1-5', name: '调整分录汇总' },
    { code: 'D1-6', name: '业务模式分析' },
    { code: 'D1-7', name: '备查簿核对' },
    { code: 'D1-8', name: '背书贴现明细' },
    { code: 'D1-9', name: '贴息检查' },
    { code: 'D1-10', name: '票据监盘' },
    { code: 'D1-11', name: '关联方检查' },
    { code: 'D1-12', name: '质押检查' },
    { code: 'D1-13', name: '一般检查表' },
    { code: 'D1-14', name: 'ECL会计政策一致性' },
    { code: 'D1-15', name: 'ECL测试数据' },
    { code: 'D1-16', name: '转回核销检查' },
    { code: 'D1-17', name: '附注披露(上市公司)' },
    { code: 'D1-18', name: '附注披露(国企)' },
    { code: 'D1-19', name: '分析提示' },
    { code: 'D1-20', name: '工作底稿目录' },
  ]
  return sheets.map(s => {
    const statusMap: Record<string, string> = {
      'completed': 'success',
      'in-progress': '',
      'not-started': 'info',
    }
    const labelMap: Record<string, string> = {
      'completed': '已完成',
      'in-progress': '进行中',
      'not-started': '未开始',
    }
    // Simple status lookup from tab completion
    const status: TabStatus = 'not-started'
    return { ...s, statusType: statusMap[status] || 'info', statusLabel: labelMap[status] || '未开始' }
  })
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
  const status = d1.tabCompletionStatus.value.get(tabName) || 'not-started'
  if (status === 'completed') return 'tab-dot tab-dot-completed'
  if (status === 'in-progress') return 'tab-dot tab-dot-progress'
  return 'tab-dot tab-dot-empty'
}

// ─── Event Handlers ──────────────────────────────────────────────────────────

function onProcTextChange(stepIdx: number, field: string, val: string): void {
  const n = stepIdx + 1
  const itemId = `D1-proc-${n}-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onOverallConclusionChange(val: string): void {
  const item = { item_id: 'D1-proc-overall', conclusion: null, remark: val }
  allResponses.value.set('D1-proc-overall', item)
  saveDebouncedText(item)
}

function onDisclosureChange(row: any): void {
  const itemId = `D1-disc-${disclosureType.value}-${row.index}`
  setFieldImmediate(itemId, { conclusion: row.conclusion })
}

function onDisclosureRemarkChange(row: any): void {
  const itemId = `D1-disc-${disclosureType.value}-${row.index}-remark`
  const item = { item_id: itemId, conclusion: null, remark: row.remark }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onAdjChange(row: any): void {
  d1.updateAdjustment(row.index, { type: row.type })
}

function onAdjTextChange(row: any): void {
  d1.updateAdjustment(row.index, row)
}

function pushToA13(row: any): void {
  d1.publishAdjustmentCreated(row)
}

function onInventoryChange(field: string, val: string): void {
  const itemId = `D1-inventory-${field}`
  const item = { item_id: itemId, conclusion: null, remark: val }
  allResponses.value.set(itemId, item)
  saveDebouncedText(item)
}

function onCheckChange(prefix: string, n: number, val: string): void {
  const itemId = `D1-${prefix}-${n}-conclusion`
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
  await d1.refreshCrossSheetData()
})

onBeforeUnmount(() => {
  flushPendingSave()
})
</script>

<style scoped>
.d1-notes-receivable {
  padding: 16px;
  max-width: 1400px;
  margin: 0 auto;
}
.d1-notes-receivable.is-readonly {
  pointer-events: auto;
}
.reviewed-banner {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  border-radius: 4px;
  padding: 8px 16px;
  margin-bottom: 12px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: #52c41a;
  font-weight: 500;
}
.linkage-bar {
  display: flex;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.ref-chip {
  cursor: pointer;
}
.d1-section {
  padding: 12px 0;
}
.d1-sub-wp-placeholder {
  padding: 48px;
  text-align: center;
  color: #bfbfbf;
  font-size: 14px;
  border: 1px dashed #d9d9d9;
  border-radius: 8px;
  margin: 16px 0;
}

/* Tab dots */
.tab-dot {
  margin-right: 4px;
  font-size: 10px;
}
.tab-dot-completed {
  color: #52c41a;
}
.tab-dot-completed::before {
  content: '✓';
}
.tab-dot-progress {
  color: #1890ff;
}
.tab-dot-progress::before {
  content: '●';
}
.tab-dot-empty {
  color: #bfbfbf;
}
.tab-dot-empty::before {
  content: '○';
}

/* Procedure cards */
.progress-bar {
  margin-bottom: 16px;
}
.risk-badges {
  margin-bottom: 12px;
  display: flex;
  gap: 6px;
}
.procedure-card {
  border: 1px solid #f0f0f0;
  border-radius: 6px;
  margin-bottom: 10px;
  overflow: hidden;
}
.procedure-card .card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 14px;
  background: #fafafa;
}
.step-num {
  background: #1890ff;
  color: #fff;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  font-weight: 600;
  flex-shrink: 0;
}
.step-name {
  font-weight: 500;
  font-size: 14px;
}
.card-body-proc {
  padding: 10px 14px;
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.card-body-proc .el-textarea {
  width: 100%;
}
.overall-conclusion {
  margin-top: 20px;
  padding: 16px;
  background: #f9f9f9;
  border-radius: 8px;
}
.overall-conclusion h4 {
  margin: 0 0 8px;
}

/* Adjudication table */
.cross-ref {
  background: #e6f7ff;
  padding: 2px 4px;
  border-radius: 2px;
}
.auto-calc {
  color: #8c8c8c;
  font-style: italic;
}

/* ECL */
.ecl-header {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 16px;
}
.migration-matrix {
  margin-bottom: 16px;
}
.ecl-summary {
  margin-top: 12px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  font-size: 13px;
  padding: 12px;
  background: #fafafa;
  border-radius: 6px;
}
.diff-exceed {
  color: #ff4d4f;
  font-weight: 600;
}

/* Adjustment */
.adj-header {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 12px;
}
.adj-totals {
  font-size: 13px;
  color: #666;
}

/* Endorsement */
.endorse-summary {
  margin-top: 12px;
  display: flex;
  gap: 16px;
  font-size: 13px;
  flex-wrap: wrap;
}
.warning-text {
  color: #ff4d4f;
  font-size: 12px;
}

/* Check rows */
.check-row {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.check-label {
  min-width: 200px;
  font-size: 13px;
}

/* Match panel */
.match-panel {
  margin-bottom: 8px;
}

/* Review */
.review-section {
  border-top: 1px solid #f0f0f0;
  padding-top: 16px;
  margin-top: 16px;
}
.review-section h4 {
  margin: 0 0 8px;
}
.pending-list {
  margin-bottom: 12px;
  font-size: 13px;
  color: #666;
}
.pending-list ul {
  margin: 4px 0;
  padding-left: 20px;
}
</style>
