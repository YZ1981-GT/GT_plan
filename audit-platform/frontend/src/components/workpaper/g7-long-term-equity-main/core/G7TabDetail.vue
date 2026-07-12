<!--
  G7TabDetail.vue — G7-2 明细表（103行×54列 → 5区段Tab）

  5区段Tab切换（el-segmented）：
  - Tab1: 基础信息(8列): 被投资单位|控制类型(下拉)|持股比例|投票权比例|行业|注册地|主营业务|是否关联方
  - Tab2: 期初余额(10列): 期初投资成本|期初权益法调整|期初减值准备|期初账面价值(公式)|期初审定成本|期初审定权益法|期初审定减值|期初审定净值(公式)|备注
  - Tab3: 本期变动(12列): 新增投资|权益法增加|处置减少|权益法调整减少|减值计提|减值转回|被投资方净利润|持股比例调整|OCI|其他权益变动|利润分配
  - Tab4: 期末+减值(12列): 期末投资成本(公式)|期末权益法调整(公式)|期末小计(公式)|期末减值(公式)|期末账面价值(公式)|审定调整|审定数(公式)|可收回金额|减值测试结论|发函情况|索引
  - Tab5: 权益法详情(12列): 被投资方净资产|享有份额(公式)|商誉|内部交易抵销|未确认损失|权益法投资收益|本期OCI|股利收入|计量方法确认|处置损益|备注

  区段间行同步：所有区段共享同一行集合，切换Tab只改可见列
  虚拟滚动：103行 max-height
  底部合计行
  公式列：虚线下划线+cursor:help+tooltip来源

  Spec: .kiro/specs/g7-long-term-equity-main/ Task 5.1
  Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4, 6.6
-->
<template>
  <div class="g7-detail">
    <!-- 顶部工具栏 -->
    <div class="section-head">
      <h3 class="sheet-title">G7-2 长期股权投资明细表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
          + 被投资单位
        </el-button>
        <el-dropdown trigger="click" size="small" @command="handleDropdownCommand">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export">导出数据</el-dropdown-item>
              <el-dropdown-item command="import">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G7-2-detail')">💬复核</el-button>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      审计目标：核实各被投资单位长期股权投资明细的期初、本期变动及期末余额的完整性与准确性，验证成本法/权益法核算方法适当，账面价值、减值准备及权益法调整计算正确，并与 G7-1 审定表勾稽一致。
    </el-alert>

    <!-- 5区段Tab切换 -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 明细表格（单一实例，列定义按Tab切换） -->
    <el-table
      :data="displayRows"
      border
      size="small"
      max-height="580"
      highlight-current-row
      row-key="id"
      :row-class-name="rowClassName"
      class="detail-table"
      @current-change="onCurrentChange"
    >
      <!-- 序号列（始终显示） -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal">
            <span class="total-label">合计</span>
          </template>
          <template v-else>{{ row.seq }}</template>
        </template>
      </el-table-column>

      <!-- 被投资单位列（始终显示作为锚定列） -->
      <el-table-column label="被投资单位" width="150" fixed>
        <template #default="{ row }">
          <template v-if="row._isTotal" />
          <span v-else>{{ row.investeeName }}</span>
        </template>
      </el-table-column>

      <!-- ═══ Tab1: 基础信息(8列) ═══ -->
      <template v-if="activeTab === 'tab1'">
        <el-table-column label="控制类型" min-width="120">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-select v-if="!isReadonly" :model-value="row.controlType" size="small" style="width:100%"
                @change="(v: string) => updateField(row.id, 'controlType', v)">
                <el-option value="subsidiary" label="子公司" />
                <el-option value="joint_venture" label="合营企业" />
                <el-option value="associate" label="联营企业" />
              </el-select>
              <span v-else>{{ controlTypeLabel(row.controlType) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="持股比例" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.holdingRatio" size="small"
                :controls="false" :precision="4" :step="0.01" :min="0" :max="1" class="compact-num"
                @change="(v: number) => updateField(row.id, 'holdingRatio', v)" />
              <span v-else>{{ fmtPercent(row.holdingRatio) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="投票权比例" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.votingRatio" size="small"
                :controls="false" :precision="4" :step="0.01" :min="0" :max="1" class="compact-num"
                @change="(v: number) => updateField(row.id, 'votingRatio', v)" />
              <span v-else>{{ fmtPercent(row.votingRatio) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="行业" min-width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.industry" size="small"
                @change="(v: string) => updateField(row.id, 'industry', v)" />
              <span v-else>{{ row.industry }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="注册地" min-width="100">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.registeredPlace" size="small"
                @change="(v: string) => updateField(row.id, 'registeredPlace', v)" />
              <span v-else>{{ row.registeredPlace }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="主营业务" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.mainBusiness" size="small"
                @change="(v: string) => updateField(row.id, 'mainBusiness', v)" />
              <span v-else>{{ row.mainBusiness }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="是否关联方" min-width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-checkbox v-if="!isReadonly" :model-value="row.isRelatedParty"
                @change="(v: boolean) => updateField(row.id, 'isRelatedParty', v)" />
              <span v-else>{{ row.isRelatedParty ? '是' : '否' }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab2: 期初余额(10列) ═══ -->
      <template v-if="activeTab === 'tab2'">
        <el-table-column label="期初投资成本" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingInvestCost) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingInvestCost" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingInvestCost', v)" />
              <span v-else>{{ fmtNum(row.openingInvestCost) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初权益法调整" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingEquityAdj) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingEquityAdj" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingEquityAdj', v)" />
              <span v-else>{{ fmtNum(row.openingEquityAdj) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初减值准备" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingImpairment) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingImpairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingImpairment', v)" />
              <span v-else>{{ fmtNum(row.openingImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingBookValue) }}</span></template>
            <template v-else>
              <el-tooltip content="期初账面价值 = 期初投资成本 + 期初权益法调整 - 期初减值准备" placement="top">
                <span class="formula-cell">{{ fmtNum(row.openingBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初审定成本" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingAuditedCost) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingAuditedCost" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingAuditedCost', v)" />
              <span v-else>{{ fmtNum(row.openingAuditedCost) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初审定权益法" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingAuditedEquity) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingAuditedEquity" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingAuditedEquity', v)" />
              <span v-else>{{ fmtNum(row.openingAuditedEquity) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初审定减值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingAuditedImpairment) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.openingAuditedImpairment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'openingAuditedImpairment', v)" />
              <span v-else>{{ fmtNum(row.openingAuditedImpairment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期初审定净值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.openingAuditedNetValue) }}</span></template>
            <template v-else>
              <el-tooltip content="期初审定净值 = 期初审定成本 + 期初审定权益法 - 期初审定减值" placement="top">
                <span class="formula-cell">{{ fmtNum(row.openingAuditedNetValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.openingRemark" size="small"
                @change="(v: string) => updateField(row.id, 'openingRemark', v)" />
              <span v-else>{{ row.openingRemark }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab3: 本期变动(12列) ═══ -->
      <template v-if="activeTab === 'tab3'">
        <el-table-column label="新增投资" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.increaseNewInvest) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.increaseNewInvest" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'increaseNewInvest', v)" />
              <span v-else>{{ fmtNum(row.increaseNewInvest) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="权益法增加" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.increaseEquityMethod) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.increaseEquityMethod" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'increaseEquityMethod', v)" />
              <span v-else>{{ fmtNum(row.increaseEquityMethod) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="处置减少" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.decreaseDisposal) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.decreaseDisposal" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'decreaseDisposal', v)" />
              <span v-else>{{ fmtNum(row.decreaseDisposal) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="权益法调整减少" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.decreaseEquityAdj) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.decreaseEquityAdj" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'decreaseEquityAdj', v)" />
              <span v-else>{{ fmtNum(row.decreaseEquityAdj) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="减值计提" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.impairmentProvision) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.impairmentProvision" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'impairmentProvision', v)" />
              <span v-else>{{ fmtNum(row.impairmentProvision) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="减值转回" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.impairmentReversal) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.impairmentReversal" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'impairmentReversal', v)" />
              <span v-else>{{ fmtNum(row.impairmentReversal) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="被投资方净利润" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.investeeNetProfit) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.investeeNetProfit" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'investeeNetProfit', v)" />
              <span v-else>{{ fmtNum(row.investeeNetProfit) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="持股比例调整" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.holdingRatioChange" size="small"
                :controls="false" :precision="4" class="compact-num"
                @change="(v: number) => updateField(row.id, 'holdingRatioChange', v)" />
              <span v-else>{{ fmtPercent(row.holdingRatioChange) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="其他综合收益" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.otherComprehensiveIncome) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.otherComprehensiveIncome" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'otherComprehensiveIncome', v)" />
              <span v-else>{{ fmtNum(row.otherComprehensiveIncome) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="其他权益变动" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.otherEquityChange) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.otherEquityChange" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'otherEquityChange', v)" />
              <span v-else>{{ fmtNum(row.otherEquityChange) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="利润分配" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.profitDistribution) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.profitDistribution" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'profitDistribution', v)" />
              <span v-else>{{ fmtNum(row.profitDistribution) }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab4: 期末+减值(12列) ═══ -->
      <template v-if="activeTab === 'tab4'">
        <el-table-column label="期末投资成本" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.closingInvestCost) }}</span></template>
            <template v-else>
              <el-tooltip content="期末投资成本 = 期初投资成本 + 新增投资 - 处置减少" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingInvestCost) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末权益法调整" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.closingEquityAdj) }}</span></template>
            <template v-else>
              <el-tooltip content="期末权益法调整 = 期初权益法调整 + 权益法增加 - 权益法调整减少" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingEquityAdj) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末小计" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.closingSubtotal) }}</span></template>
            <template v-else>
              <el-tooltip content="期末小计 = 期末投资成本 + 期末权益法调整" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingSubtotal) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末减值准备" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.closingImpairment) }}</span></template>
            <template v-else>
              <el-tooltip content="期末减值 = 期初减值 + 减值计提 - 减值转回" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingImpairment) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="期末账面价值" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.closingBookValue) }}</span></template>
            <template v-else>
              <el-tooltip content="期末账面价值 = 期末小计 - 期末减值准备" placement="top">
                <span class="formula-cell">{{ fmtNum(row.closingBookValue) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="审定调整" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.auditAdjustment) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.auditAdjustment" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'auditAdjustment', v)" />
              <span v-else>{{ fmtNum(row.auditAdjustment) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="审定数" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.auditedAmount) }}</span></template>
            <template v-else>
              <el-tooltip content="审定数 = 期末账面价值 + 审定调整" placement="top">
                <span class="formula-cell">{{ fmtNum(row.auditedAmount) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="可收回金额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.recoverableAmount" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'recoverableAmount', v)" />
              <span v-else>{{ fmtNum(row.recoverableAmount) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="减值测试结论" min-width="130">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.impairmentTestConclusion" size="small"
                @change="(v: string) => updateField(row.id, 'impairmentTestConclusion', v)" />
              <span v-else>{{ row.impairmentTestConclusion }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="发函情况" min-width="110">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.confirmationStatus" size="small"
                @change="(v: string) => updateField(row.id, 'confirmationStatus', v)" />
              <span v-else>{{ row.confirmationStatus }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="索引" width="90" align="center">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <GtIndexChip v-else :value="row.indexRef" />
          </template>
        </el-table-column>
      </template>

      <!-- ═══ Tab5: 权益法详情(12列) ═══ -->
      <template v-if="activeTab === 'tab5'">
        <el-table-column label="被投资方净资产" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.investeeNetAssets) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.investeeNetAssets" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'investeeNetAssets', v)" />
              <span v-else>{{ fmtNum(row.investeeNetAssets) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="享有份额" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.shareOfNetAssets) }}</span></template>
            <template v-else>
              <el-tooltip content="享有份额 = 被投资方净资产 × 持股比例" placement="top">
                <span class="formula-cell">{{ fmtNum(row.shareOfNetAssets) }}</span>
              </el-tooltip>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="商誉" min-width="100" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.goodwill) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.goodwill" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'goodwill', v)" />
              <span v-else>{{ fmtNum(row.goodwill) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="内部交易抵销" min-width="120" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.internalTransElim) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.internalTransElim" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'internalTransElim', v)" />
              <span v-else>{{ fmtNum(row.internalTransElim) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="未确认损失" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.unrecognizedLoss) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.unrecognizedLoss" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'unrecognizedLoss', v)" />
              <span v-else>{{ fmtNum(row.unrecognizedLoss) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="权益法投资收益" min-width="130" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.equityMethodIncome) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.equityMethodIncome" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'equityMethodIncome', v)" />
              <span v-else>{{ fmtNum(row.equityMethodIncome) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="本期OCI" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.currentOCI) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.currentOCI" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'currentOCI', v)" />
              <span v-else>{{ fmtNum(row.currentOCI) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="股利收入" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.dividendIncome) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.dividendIncome" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'dividendIncome', v)" />
              <span v-else>{{ fmtNum(row.dividendIncome) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="计量方法确认" min-width="120">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.measurementConfirm" size="small"
                @change="(v: string) => updateField(row.id, 'measurementConfirm', v)" />
              <span v-else>{{ row.measurementConfirm }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="处置损益" min-width="110" align="right">
          <template #default="{ row }">
            <template v-if="row._isTotal"><span class="total-num">{{ fmtNum(row.disposalGainLoss) }}</span></template>
            <template v-else>
              <el-input-number v-if="!isReadonly" :model-value="row.disposalGainLoss" size="small"
                :controls="false" class="compact-num"
                @change="(v: number) => updateField(row.id, 'disposalGainLoss', v)" />
              <span v-else>{{ fmtNum(row.disposalGainLoss) }}</span>
            </template>
          </template>
        </el-table-column>

        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <template v-if="row._isTotal" />
            <template v-else>
              <el-input v-if="!isReadonly" :model-value="row.equityRemark" size="small"
                @change="(v: string) => updateField(row.id, 'equityRemark', v)" />
              <span v-else>{{ row.equityRemark }}</span>
            </template>
          </template>
        </el-table-column>
      </template>

      <!-- 操作列（删除） -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-popconfirm v-if="!row._isTotal" title="确认删除该被投资单位？"
            @confirm="removeRow(row.id)">
            <template #reference>
              <el-button size="small" type="danger" link>删</el-button>
            </template>
          </el-popconfirm>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>期初账面价值 = 期初投资成本 + 期初权益法调整 - 期初减值准备</li>
        <li>期末投资成本 = 期初投资成本 + 新增投资 - 处置减少</li>
        <li>期末权益法调整 = 期初权益法调整 + 权益法增加 - 权益法调整减少</li>
        <li>期末小计 = 期末投资成本 + 期末权益法调整</li>
        <li>期末减值 = 期初减值 + 减值计提 - 减值转回</li>
        <li>期末账面价值 = 期末小计 - 期末减值准备</li>
        <li>审定数 = 期末账面价值 + 审定调整</li>
        <li>享有份额 = 被投资方净资产 × 持股比例</li>
        <li>控制类型：子公司用成本法、合营/联营用权益法</li>
        <li>5区段Tab切换保持当前选中行索引不变</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G7TabDetail.vue — G7-2 长期股权投资明细表（103行×54列→5区段Tab）
 *
 * - el-segmented 切换 Tab1~Tab5
 * - 行共享同一reactive数组，Tab切换只改可见列
 * - selectedRowIndex跨Tab保持（行同步 P9）
 * - 底部合计行
 * - Tab4/Tab5公式列自动计算(useG7FormulaEngine)
 * - 控制类型下拉(子公司/合营/联营)
 * - 动态行增删(ElMessageBox.prompt必填被投资单位名称)
 * - 导入导出(useG7ImportExport, sheet='G7-2')
 * - 虚拟滚动: 103行 max-height
 *
 * Spec: .kiro/specs/g7-long-term-equity-main/ Task 5.1
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 6.4, 6.6
 */
import { ref, reactive, computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  calcEndingCost,
  calcEndingEquityAdj,
  calcBookValue,
  parseNum,
} from '../../composables/useG7FormulaEngine'
import { useG7ImportExport } from '../../composables/useG7ImportExport'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── 5区段Tab ────────────────────────────────────────────────────────────────

type TabKey = 'tab1' | 'tab2' | 'tab3' | 'tab4' | 'tab5'
const activeTab = ref<TabKey>('tab1')

const segmentOptions = [
  { label: '基础信息(8)', value: 'tab1' },
  { label: '期初余额(10)', value: 'tab2' },
  { label: '本期变动(12)', value: 'tab3' },
  { label: '期末+减值(12)', value: 'tab4' },
  { label: '权益法详情(12)', value: 'tab5' },
]

// ─── 控制类型 ────────────────────────────────────────────────────────────────

type ControlType = 'subsidiary' | 'joint_venture' | 'associate'

const CONTROL_TYPE_LABELS: Record<ControlType, string> = {
  subsidiary: '子公司',
  joint_venture: '合营企业',
  associate: '联营企业',
}

function controlTypeLabel(ct: string): string {
  return CONTROL_TYPE_LABELS[ct as ControlType] || ct
}

// ─── 行数据模型（54列） ──────────────────────────────────────────────────────

interface G7DetailRow {
  id: string
  seq: number
  // Tab1: 基础信息
  investeeName: string
  controlType: ControlType
  holdingRatio: number
  votingRatio: number
  industry: string
  registeredPlace: string
  mainBusiness: string
  isRelatedParty: boolean
  // Tab2: 期初余额
  openingInvestCost: number
  openingEquityAdj: number
  openingImpairment: number
  openingBookValue: number         // 公式
  openingAuditedCost: number
  openingAuditedEquity: number
  openingAuditedImpairment: number
  openingAuditedNetValue: number   // 公式
  openingRemark: string
  // Tab3: 本期变动
  increaseNewInvest: number
  increaseEquityMethod: number
  decreaseDisposal: number
  decreaseEquityAdj: number
  impairmentProvision: number
  impairmentReversal: number
  investeeNetProfit: number
  holdingRatioChange: number
  otherComprehensiveIncome: number
  otherEquityChange: number
  profitDistribution: number
  // Tab4: 期末+减值
  closingInvestCost: number        // 公式
  closingEquityAdj: number         // 公式
  closingSubtotal: number          // 公式
  closingImpairment: number        // 公式
  closingBookValue: number         // 公式
  auditAdjustment: number
  auditedAmount: number            // 公式
  recoverableAmount: number
  impairmentTestConclusion: string
  confirmationStatus: string
  indexRef: string
  // Tab5: 权益法详情
  investeeNetAssets: number
  shareOfNetAssets: number         // 公式
  goodwill: number
  internalTransElim: number
  unrecognizedLoss: number
  equityMethodIncome: number
  currentOCI: number
  dividendIncome: number
  measurementConfirm: string
  disposalGainLoss: number
  equityRemark: string
}

interface DisplayRow extends G7DetailRow {
  _isTotal?: boolean
}

function createEmptyRow(seq: number, name: string): G7DetailRow {
  return {
    id: crypto.randomUUID(),
    seq,
    investeeName: name,
    controlType: 'subsidiary',
    holdingRatio: 0,
    votingRatio: 0,
    industry: '',
    registeredPlace: '',
    mainBusiness: '',
    isRelatedParty: false,
    openingInvestCost: 0,
    openingEquityAdj: 0,
    openingImpairment: 0,
    openingBookValue: 0,
    openingAuditedCost: 0,
    openingAuditedEquity: 0,
    openingAuditedImpairment: 0,
    openingAuditedNetValue: 0,
    openingRemark: '',
    increaseNewInvest: 0,
    increaseEquityMethod: 0,
    decreaseDisposal: 0,
    decreaseEquityAdj: 0,
    impairmentProvision: 0,
    impairmentReversal: 0,
    investeeNetProfit: 0,
    holdingRatioChange: 0,
    otherComprehensiveIncome: 0,
    otherEquityChange: 0,
    profitDistribution: 0,
    closingInvestCost: 0,
    closingEquityAdj: 0,
    closingSubtotal: 0,
    closingImpairment: 0,
    closingBookValue: 0,
    auditAdjustment: 0,
    auditedAmount: 0,
    recoverableAmount: 0,
    impairmentTestConclusion: '',
    confirmationStatus: '',
    indexRef: '',
    investeeNetAssets: 0,
    shareOfNetAssets: 0,
    goodwill: 0,
    internalTransElim: 0,
    unrecognizedLoss: 0,
    equityMethodIncome: 0,
    currentOCI: 0,
    dividendIncome: 0,
    measurementConfirm: '',
    disposalGainLoss: 0,
    equityRemark: '',
  }
}

const rows = reactive<G7DetailRow[]>([])
const selectedRowIndex = ref(0)

// ─── 公式重算（使用 useG7FormulaEngine） ─────────────────────────────────────

function recalcRow(row: G7DetailRow): void {
  // Tab2 公式
  row.openingBookValue = parseNum(row.openingInvestCost) + parseNum(row.openingEquityAdj) - parseNum(row.openingImpairment)
  row.openingAuditedNetValue = parseNum(row.openingAuditedCost) + parseNum(row.openingAuditedEquity) - parseNum(row.openingAuditedImpairment)

  // Tab4 公式（使用 useG7FormulaEngine）
  row.closingInvestCost = calcEndingCost(parseNum(row.openingInvestCost), parseNum(row.increaseNewInvest), parseNum(row.decreaseDisposal))
  row.closingEquityAdj = calcEndingEquityAdj(parseNum(row.openingEquityAdj), parseNum(row.increaseEquityMethod), parseNum(row.decreaseEquityAdj))
  row.closingSubtotal = row.closingInvestCost + row.closingEquityAdj
  row.closingImpairment = parseNum(row.openingImpairment) + parseNum(row.impairmentProvision) - parseNum(row.impairmentReversal)
  row.closingBookValue = calcBookValue(row.closingSubtotal, row.closingImpairment)
  row.auditedAmount = row.closingBookValue + parseNum(row.auditAdjustment)

  // Tab5 公式
  row.shareOfNetAssets = parseNum(row.investeeNetAssets) * parseNum(row.holdingRatio)
}

// ─── 合计行 ──────────────────────────────────────────────────────────────────

/** 数值字段列表（合计用） */
const NUMERIC_FIELDS: (keyof G7DetailRow)[] = [
  'openingInvestCost', 'openingEquityAdj', 'openingImpairment', 'openingBookValue',
  'openingAuditedCost', 'openingAuditedEquity', 'openingAuditedImpairment', 'openingAuditedNetValue',
  'increaseNewInvest', 'increaseEquityMethod', 'decreaseDisposal', 'decreaseEquityAdj',
  'impairmentProvision', 'impairmentReversal', 'investeeNetProfit',
  'otherComprehensiveIncome', 'otherEquityChange', 'profitDistribution',
  'closingInvestCost', 'closingEquityAdj', 'closingSubtotal', 'closingImpairment',
  'closingBookValue', 'auditAdjustment', 'auditedAmount',
  'investeeNetAssets', 'shareOfNetAssets', 'goodwill', 'internalTransElim',
  'unrecognizedLoss', 'equityMethodIncome', 'currentOCI', 'dividendIncome', 'disposalGainLoss',
]

const totalRow = computed<DisplayRow>(() => {
  const t: DisplayRow = { ...createEmptyRow(0, ''), _isTotal: true }
  for (const r of rows) {
    for (const f of NUMERIC_FIELDS) {
      ;(t as any)[f] = ((t as any)[f] || 0) + parseNum((r as any)[f])
    }
  }
  return t
})

const displayRows = computed<DisplayRow[]>(() => {
  const result: DisplayRow[] = [...(rows as unknown as DisplayRow[])]
  result.push(totalRow.value)
  return result
})

// ─── 行同步（selectedRowIndex 跨Tab保持） ───────────────────────────────────

function onCurrentChange(row: DisplayRow | null) {
  if (!row || row._isTotal) return
  const idx = rows.findIndex(r => r.id === row.id)
  if (idx >= 0) selectedRowIndex.value = idx
}

// ─── 行样式 ─────────────────────────────────────────────────────────────────

function rowClassName({ row }: { row: DisplayRow }): string {
  if (row._isTotal) return 'row-total'
  return ''
}

// ─── 字段更新（触发公式重算） ───────────────────────────────────────────────

function updateField(id: string, field: keyof G7DetailRow, value: any) {
  const row = rows.find(r => r.id === id)
  if (!row) return
  ;(row as any)[field] = value ?? (typeof (row as any)[field] === 'number' ? 0 : '')
  recalcRow(row)
}

// ─── 动态行增删（ElMessageBox.prompt必填被投资单位名称） ─────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入被投资单位名称', '新增被投资单位', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '被投资单位名称不能为空',
    })
    if (value?.trim()) {
      const newRow = createEmptyRow(rows.length + 1, value.trim())
      rows.push(newRow)
      recalcRow(newRow)
    }
  } catch {
    // 用户取消
  }
}

function removeRow(id: string) {
  const idx = rows.findIndex(r => r.id === id)
  if (idx >= 0) {
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
  }
}

// ─── 导入导出 ────────────────────────────────────────────────────────────────

const ie = useG7ImportExport({ wpId: computed(() => props.wpId) })

async function handleDropdownCommand(command: string) {
  if (command === 'template') {
    await ie.exportTemplate('G7-2')
  } else if (command === 'export') {
    await ie.exportData('G7-2')
  } else if (command === 'import') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = async (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) {
        const result = await ie.importData('G7-2', file)
        if (result) loadFromHtmlData(props.htmlData)
      }
    }
    input.click()
  }
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

function fmtPercent(v: unknown): string {
  if (typeof v === 'number') return `${(v * 100).toFixed(2)}%`
  return String(v ?? '')
}

// ─── 数据加载（从htmlData或导入后刷新） ─────────────────────────────────────

function loadFromHtmlData(data: Record<string, any> | null): void {
  if (!data) return
  rows.length = 0

  // 尝试从htmlData.detail.rows加载
  const detailData = data.detail || data
  const rawRows = detailData?.rows || []

  if (Array.isArray(rawRows) && rawRows.length > 0) {
    for (let i = 0; i < rawRows.length; i++) {
      const raw = rawRows[i]
      const row: G7DetailRow = {
        ...createEmptyRow(i + 1, raw.investeeName || raw.investee_name || ''),
        ...raw,
        seq: i + 1,
        id: raw.id || crypto.randomUUID(),
      }
      rows.push(row)
      recalcRow(row)
    }
  }
}

onMounted(() => {
  loadFromHtmlData(props.htmlData)
})
</script>

<style scoped>
.g7-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.audit-objective { margin-bottom: 12px; }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 12px; }
.sheet-title { margin: 0; font-size: 15px; font-weight: 600; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.segment-bar { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.compact-num { width: 100%; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; display: inline-block; min-width: 40px; text-align: right; }
.total-label { font-weight: 600; color: #303133; }
.total-num { font-weight: 600; color: #303133; }
.prep-hint { margin-top: 16px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }

:deep(.row-total) {
  background-color: #f5f7fa !important;
  font-weight: 600;
}
:deep(.row-total td) {
  border-top: 2px solid #dcdfe6;
}
</style>
