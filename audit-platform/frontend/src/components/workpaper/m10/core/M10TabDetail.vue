<template>
  <div class="m10-tab-detail">
    <!-- HTML 结构化模式（双模式已上移至入口级 GtM10OtherEquityInstruments，避免双重切换栏） -->
    <template>
      <!-- ═══ 标题 + 操作栏 ═══ -->
      <div class="section-header">
        <div class="section-header-left">
          <h3 class="section-title">M10-2 其他权益工具明细表</h3>
          <el-tag type="warning" size="small">30列·3区段Tab·动态行</el-tag>
        </div>
        <div class="section-header-right">
          <el-dropdown :disabled="isReadonly" trigger="click" @command="handleImportExport">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
                <el-dropdown-item command="importData">导入数据</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-dropdown :disabled="isReadonly" trigger="click" @command="handleAddByType">
            <el-button size="small" type="primary">
              <el-icon><Plus /></el-icon> 新增
            </el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item command="perpetualBond">新增永续债</el-dropdown-item>
                <el-dropdown-item command="preferredStock">新增优先股</el-dropdown-item>
                <el-dropdown-item command="convertible">新增转股特征工具</el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
          <el-button size="small" @click="handleReview">
            <el-icon><Check /></el-icon> 复核
          </el-button>
        </div>
      </div>

      <!-- ═══ 方法论上下文（琥珀色） ═══ -->
      <div class="methodology-context">
        <div class="methodology-text">
          <strong>30列明细表按区段Tab拆分查看，切换Tab不影响行数据。</strong>
          权益类贷方：期末=期初+发行-赎回。永续债/优先股/转股特征三组分类小计+合计。
        </div>
      </div>

      <!-- ═══ 跨sheet验证警告（与M10-1差异） ═══ -->
      <el-alert
        v-if="showCrossValidation"
        :type="crossValidation.isMatch ? 'success' : 'error'"
        :closable="false"
        show-icon
        class="cross-sheet-alert"
      >
        <template #title>
          <span v-if="crossValidation.isMatch">明细合计与审定表M10-1一致 ✓</span>
          <span v-else>明细合计与审定表M10-1不一致（差额：{{ fmtAmount(crossValidation.diff) }}）</span>
        </template>
      </el-alert>

      <!-- ═══ 3 区段Tab (el-segmented) ═══ -->
      <el-segmented
        v-model="activeTabValue"
        :options="tabSegmentOptions"
        size="default"
        class="segment-switcher"
      />

      <!-- ═══════════════ 区段1: 工具信息 ═══════════════ -->
      <template v-if="detail.activeTab.value === 'instrumentInfo'">
        <!-- 永续债组 -->
        <div class="group-section">
          <div class="group-header perpetual-bond">永续债</div>
          <el-table :data="detail.perpetualBondRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="160">
              <template #default="{ row }">
                <span class="instrument-name">{{ row.instrumentName || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行日" min-width="120">
              <template #default="{ row, $index }">
                <el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="发行日" @change="(val: string) => updateRowByKey(row.key, 'issueDate', val || '')" />
                <span v-else>{{ row.issueDate || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="面值" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'faceValue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.faceValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="利率(%)" min-width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.couponRate" :controls="false" :min="0" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'couponRate', val ?? 0)" />
                <span v-else>{{ row.couponRate ? row.couponRate + '%' : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="到期日" min-width="120">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" :model-value="row.maturityDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="到期日" @change="(val: string) => updateRowByKey(row.key, 'maturityDate', val || '')" />
                <span v-else>{{ row.maturityDate || '无固定期限' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可赎回" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isRedeemable" @change="(val: boolean) => updateRowByKey(row.key, 'isRedeemable', val)" />
                <span v-else>{{ row.isRedeemable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可转股" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isConvertible" @change="(val: boolean) => updateRowByKey(row.key, 'isConvertible', val)" />
                <span v-else>{{ row.isConvertible ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="分派方式" min-width="110">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionMethod" size="small" placeholder="分派方式" @change="(val: string) => updateRowByKey(row.key, 'distributionMethod', val)" />
                <span v-else>{{ row.distributionMethod || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'remark', val)" />
                <span v-else>{{ row.remark || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" @click="removeRowByKey(row.key)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">永续债小计 — 期末：{{ fmtAmount(detail.perpetualBondSubtotal.value.endBalance) }}</div>
        </div>

        <!-- 优先股组 -->
        <div class="group-section">
          <div class="group-header preferred-stock">优先股</div>
          <el-table :data="detail.preferredStockRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="160">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="发行日" min-width="120">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="发行日" @change="(val: string) => updateRowByKey(row.key, 'issueDate', val || '')" />
                <span v-else>{{ row.issueDate || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="面值" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'faceValue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.faceValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="股息率(%)" min-width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.couponRate" :controls="false" :min="0" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'couponRate', val ?? 0)" />
                <span v-else>{{ row.couponRate ? row.couponRate + '%' : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="到期日" min-width="120">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" :model-value="row.maturityDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="到期日" @change="(val: string) => updateRowByKey(row.key, 'maturityDate', val || '')" />
                <span v-else>{{ row.maturityDate || '无固定期限' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可赎回" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isRedeemable" @change="(val: boolean) => updateRowByKey(row.key, 'isRedeemable', val)" />
                <span v-else>{{ row.isRedeemable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可转股" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isConvertible" @change="(val: boolean) => updateRowByKey(row.key, 'isConvertible', val)" />
                <span v-else>{{ row.isConvertible ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="分派方式" min-width="110">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionMethod" size="small" placeholder="分派方式" @change="(val: string) => updateRowByKey(row.key, 'distributionMethod', val)" />
                <span v-else>{{ row.distributionMethod || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'remark', val)" />
                <span v-else>{{ row.remark || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" @click="removeRowByKey(row.key)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">优先股小计 — 期末：{{ fmtAmount(detail.preferredStockSubtotal.value.endBalance) }}</div>
        </div>

        <!-- 转股特征工具组 -->
        <div class="group-section">
          <div class="group-header convertible">转股特征工具</div>
          <el-table :data="detail.convertibleRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="160">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="发行日" min-width="120">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="发行日" @change="(val: string) => updateRowByKey(row.key, 'issueDate', val || '')" />
                <span v-else>{{ row.issueDate || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="面值" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'faceValue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.faceValue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="利率(%)" min-width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.couponRate" :controls="false" :min="0" :precision="2" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'couponRate', val ?? 0)" />
                <span v-else>{{ row.couponRate ? row.couponRate + '%' : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="到期日" min-width="120">
              <template #default="{ row }">
                <el-date-picker v-if="!isReadonly" :model-value="row.maturityDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" placeholder="到期日" @change="(val: string) => updateRowByKey(row.key, 'maturityDate', val || '')" />
                <span v-else>{{ row.maturityDate || '无固定期限' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可赎回" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isRedeemable" @change="(val: boolean) => updateRowByKey(row.key, 'isRedeemable', val)" />
                <span v-else>{{ row.isRedeemable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="可转股" width="70" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isConvertible" @change="(val: boolean) => updateRowByKey(row.key, 'isConvertible', val)" />
                <span v-else>{{ row.isConvertible ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转股价格" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.conversionPrice" :controls="false" :min="0" :precision="4" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'conversionPrice', val ?? 0)" />
                <span v-else>{{ row.conversionPrice ? fmtAmount(row.conversionPrice) : '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="分派方式" min-width="110">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionMethod" size="small" placeholder="分派方式" @change="(val: string) => updateRowByKey(row.key, 'distributionMethod', val)" />
                <span v-else>{{ row.distributionMethod || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.remark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'remark', val)" />
                <span v-else>{{ row.remark || '—' }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" text size="small" @click="removeRowByKey(row.key)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">转股特征工具小计 — 期末：{{ fmtAmount(detail.convertibleSubtotal.value.endBalance) }}</div>
        </div>
      </template>

      <!-- ═══════════════ 区段2: 发行赎回 ═══════════════ -->
      <template v-if="detail.activeTab.value === 'issuanceRedemption'">
        <!-- 永续债组 -->
        <div class="group-section">
          <div class="group-header perpetual-bond">永续债</div>
          <el-table :data="detail.perpetualBondRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="期初" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'beginning', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.beginning) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行总额" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.grossIssuance" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'grossIssuance', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.grossIssuance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行费用" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.issuanceCost" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'issuanceCost', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.issuanceCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 发行总额 − 发行费用" placement="top"><span class="formula-col-header">净发行</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.netIssuance) }}</span></template>
            </el-table-column>
            <el-table-column label="赎回" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.redemption" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'redemption', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.redemption) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转换" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.conversion" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'conversion', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.conversion) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 赎回 + 转换" placement="top"><span class="formula-col-header">减少合计</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.totalReduction) }}</span></template>
            </el-table-column>
            <el-table-column min-width="120" align="right">
              <template #header><el-tooltip content="公式: 期初 + 净发行 − 减少合计（权益类贷方！）" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">永续债小计 — 期初：{{ fmtAmount(detail.perpetualBondSubtotal.value.beginning) }} | 净发行：{{ fmtAmount(detail.perpetualBondSubtotal.value.netIssuance) }} | 期末：{{ fmtAmount(detail.perpetualBondSubtotal.value.endBalance) }}</div>
        </div>

        <!-- 优先股组 -->
        <div class="group-section">
          <div class="group-header preferred-stock">优先股</div>
          <el-table :data="detail.preferredStockRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="期初" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'beginning', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.beginning) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行总额" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.grossIssuance" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'grossIssuance', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.grossIssuance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行费用" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.issuanceCost" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'issuanceCost', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.issuanceCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 发行总额 − 发行费用" placement="top"><span class="formula-col-header">净发行</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.netIssuance) }}</span></template>
            </el-table-column>
            <el-table-column label="赎回" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.redemption" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'redemption', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.redemption) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转换" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.conversion" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'conversion', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.conversion) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 赎回 + 转换" placement="top"><span class="formula-col-header">减少合计</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.totalReduction) }}</span></template>
            </el-table-column>
            <el-table-column min-width="120" align="right">
              <template #header><el-tooltip content="公式: 期初 + 净发行 − 减少合计（权益类贷方！）" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">优先股小计 — 期初：{{ fmtAmount(detail.preferredStockSubtotal.value.beginning) }} | 净发行：{{ fmtAmount(detail.preferredStockSubtotal.value.netIssuance) }} | 期末：{{ fmtAmount(detail.preferredStockSubtotal.value.endBalance) }}</div>
        </div>

        <!-- 转股特征工具组 -->
        <div class="group-section">
          <div class="group-header convertible">转股特征工具</div>
          <el-table :data="detail.convertibleRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="期初" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginning" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'beginning', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.beginning) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行总额" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.grossIssuance" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'grossIssuance', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.grossIssuance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="发行费用" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.issuanceCost" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'issuanceCost', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.issuanceCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 发行总额 − 发行费用" placement="top"><span class="formula-col-header">净发行</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.netIssuance) }}</span></template>
            </el-table-column>
            <el-table-column label="赎回" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.redemption" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'redemption', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.redemption) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="转换" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.conversion" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'conversion', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.conversion) }}</span>
              </template>
            </el-table-column>
            <el-table-column min-width="110" align="right">
              <template #header><el-tooltip content="公式: 赎回 + 转换" placement="top"><span class="formula-col-header">减少合计</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.totalReduction) }}</span></template>
            </el-table-column>
            <el-table-column min-width="120" align="right">
              <template #header><el-tooltip content="公式: 期初 + 净发行 − 减少合计（权益类贷方！）" placement="top"><span class="formula-col-header">期末</span></el-tooltip></template>
              <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
          <div class="subtotal-row">转股特征工具小计 — 期初：{{ fmtAmount(detail.convertibleSubtotal.value.beginning) }} | 净发行：{{ fmtAmount(detail.convertibleSubtotal.value.netIssuance) }} | 期末：{{ fmtAmount(detail.convertibleSubtotal.value.endBalance) }}</div>
        </div>
      </template>

      <!-- ═══════════════ 区段3: 分派 ═══════════════ -->
      <template v-if="detail.activeTab.value === 'distribution'">
        <!-- 永续债组 -->
        <div class="group-section">
          <div class="group-header perpetual-bond">永续债</div>
          <el-table :data="detail.perpetualBondRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="AJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.ajeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'ajeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.ajeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.rjeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'rjeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.rjeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="应付利息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestDue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestDue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestDue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已付利息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestPaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestPaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestPaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="累计未付" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.accruedUnpaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'accruedUnpaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.accruedUnpaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferrable" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferrable', val)" />
                <span v-else>{{ row.isDeferrable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferred" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferred', val)" />
                <span v-else>{{ row.isDeferred ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="CAS37分类" min-width="100">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" :model-value="row.classification" size="small" placeholder="—" @change="(val: string) => updateRowByKey(row.key, 'classification', val)">
                  <el-option label="权益" value="equity" />
                  <el-option label="负债" value="liability" />
                </el-select>
                <el-tag v-else-if="row.classification === 'equity'" type="success" size="small">权益</el-tag>
                <el-tag v-else-if="row.classification === 'liability'" type="danger" size="small">负债</el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="分派备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionRemark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'distributionRemark', val)" />
                <span v-else>{{ row.distributionRemark || '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 优先股组 -->
        <div class="group-section">
          <div class="group-header preferred-stock">优先股</div>
          <el-table :data="detail.preferredStockRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="AJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.ajeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'ajeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.ajeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.rjeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'rjeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.rjeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="应付股息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestDue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestDue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestDue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已付股息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestPaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestPaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestPaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="累计未付" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.accruedUnpaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'accruedUnpaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.accruedUnpaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferrable" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferrable', val)" />
                <span v-else>{{ row.isDeferrable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferred" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferred', val)" />
                <span v-else>{{ row.isDeferred ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="CAS37分类" min-width="100">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" :model-value="row.classification" size="small" placeholder="—" @change="(val: string) => updateRowByKey(row.key, 'classification', val)">
                  <el-option label="权益" value="equity" />
                  <el-option label="负债" value="liability" />
                </el-select>
                <el-tag v-else-if="row.classification === 'equity'" type="success" size="small">权益</el-tag>
                <el-tag v-else-if="row.classification === 'liability'" type="danger" size="small">负债</el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="分派备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionRemark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'distributionRemark', val)" />
                <span v-else>{{ row.distributionRemark || '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>

        <!-- 转股特征工具组 -->
        <div class="group-section">
          <div class="group-header convertible">转股特征工具</div>
          <el-table :data="detail.convertibleRows.value" border size="small" style="width:100%">
            <el-table-column type="index" label="#" width="45" align="center" />
            <el-table-column label="工具名称" min-width="140">
              <template #default="{ row }"><span class="instrument-name">{{ row.instrumentName || '—' }}</span></template>
            </el-table-column>
            <el-table-column label="AJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.ajeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'ajeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.ajeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="RJE" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.rjeAmount" :controls="false" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'rjeAmount', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.rjeAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="应付利息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestDue" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestDue', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestDue) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已付利息" min-width="110" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.interestPaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'interestPaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.interestPaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="累计未付" min-width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.accruedUnpaid" :controls="false" :min="0" size="small" style="width:100%" @change="(val: number | undefined) => updateRowByKey(row.key, 'accruedUnpaid', val ?? 0)" />
                <span v-else>{{ fmtAmount(row.accruedUnpaid) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferrable" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferrable', val)" />
                <span v-else>{{ row.isDeferrable ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="已递延" width="65" align="center">
              <template #default="{ row }">
                <el-checkbox v-if="!isReadonly" :model-value="row.isDeferred" @change="(val: boolean) => updateRowByKey(row.key, 'isDeferred', val)" />
                <span v-else>{{ row.isDeferred ? '是' : '否' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="CAS37分类" min-width="100">
              <template #default="{ row }">
                <el-select v-if="!isReadonly" :model-value="row.classification" size="small" placeholder="—" @change="(val: string) => updateRowByKey(row.key, 'classification', val)">
                  <el-option label="权益" value="equity" />
                  <el-option label="负债" value="liability" />
                </el-select>
                <el-tag v-else-if="row.classification === 'equity'" type="success" size="small">权益</el-tag>
                <el-tag v-else-if="row.classification === 'liability'" type="danger" size="small">负债</el-tag>
                <span v-else>—</span>
              </template>
            </el-table-column>
            <el-table-column label="分派备注" min-width="120">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" :model-value="row.distributionRemark" size="small" placeholder="备注" @change="(val: string) => updateRowByKey(row.key, 'distributionRemark', val)" />
                <span v-else>{{ row.distributionRemark || '—' }}</span>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </template>

      <!-- ═══ 合计区 ═══ -->
      <div class="total-bar">
        <span>期初合计：<strong>{{ fmtAmount(detail.grandTotal.value.beginning) }}</strong></span>
        <span>净发行合计：<strong>{{ fmtAmount(detail.grandTotal.value.netIssuance) }}</strong></span>
        <span>减少合计：<strong>{{ fmtAmount(detail.grandTotal.value.totalReduction) }}</strong></span>
        <span>期末合计：<strong class="formula-value">{{ fmtAmount(detail.grandTotal.value.endBalance) }}</strong></span>
      </div>

      <!-- ═══ 编制提示 ═══ -->
      <details class="m10-details-tip">
        <summary>编制提示</summary>
        <ul>
          <li>1. 新增行前先确认工具名称（弹窗输入）</li>
          <li>2. 发行费用从总额扣减：净发行 = 发行总额 − 发行费用</li>
          <li>3. 期末公式自动计算：期末 = 期初 + 净发行 − 减少合计（权益类贷方！）</li>
          <li>4. 减少合计 = 赎回 + 转换</li>
          <li>5. 明细合计应与M10-1审定表期末一致</li>
          <li>6. CAS37分类判定在M10-4检查表逐条进行</li>
        </ul>
      </details>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * M10TabDetail — M10-2 其他权益工具明细表（30列区段Tab+动态行）
 *
 * Spec: .kiro/specs/m10-other-equity-instruments/
 * Task: 4.3
 * Requirements: 3.1-3.5
 *
 * 功能：
 * - 30列宽表拆3区段Tab (el-segmented): 工具信息 / 发行赎回 / 分派（行同步）
 * - 三工具类型分组：永续债 / 优先股 / 转股特征工具 + 小计 + 合计
 * - 动态行新增（先弹ElMessageBox.prompt输入工具名）
 * - 导入导出 el-dropdown（导出模板/导出数据/导入数据）
 * - 公式列自动计算（13公式，权益类贷方！）
 * - 与M10-1审定表交叉验证
 * - el-segmented双模式（HTML/OnlyOffice）
 *
 * 科目：4003 其他权益工具（**贷方/权益类！期末=期初+贷方-借方**）
 */
import { computed, inject, onMounted, ref, watch } from 'vue'
import { Plus, Check } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useM10FormData } from '../../composables/useM10FormData'
import { useM10Detail, M10_DETAIL_TABS, type M10DetailRow, type M10DetailTab, type M10InstrumentType } from '../../composables/useM10Detail'
import { useM10ImportExport } from '../../composables/useM10ImportExport'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string, sectionLabel?: string) => void) | null>('openReviewDialog', null)

// ─── Composables ─────────────────────────────────────────────────────────────

const formData = useM10FormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  sheetName: 'M10-2',
})

const detailRows = ref<M10DetailRow[]>([])

const detail = useM10Detail(formData, detailRows)

const importExport = useM10ImportExport({
  wpId: computed(() => props.wpId),
})

// ─── 区段Tab状态 ─────────────────────────────────────────────────────────────

const activeTabValue = computed({
  get: () => detail.activeTab.value,
  set: (val: string) => detail.switchTab(val as M10DetailTab),
})

const tabSegmentOptions = M10_DETAIL_TABS.map(t => ({
  label: t.label,
  value: t.key,
}))

// ─── 跨sheet交叉验证（与M10-1审定表） ────────────────────────────────────────

const adjudicationTotal = ref(0)

const crossValidation = computed(() => {
  return detail.crossValidateWithAdjudication(adjudicationTotal.value)
})

const showCrossValidation = computed(() => {
  return adjudicationTotal.value !== 0 || detail.grandTotal.value.endBalance !== 0
})

watch(() => formData.allResponses.value, (responses) => {
  const auditedResp = responses.get('M10-1-total-audited')
  if (auditedResp?.remark) {
    const val = parseFloat(auditedResp.remark)
    if (!isNaN(val)) adjudicationTotal.value = val
  }
}, { immediate: true })

// ─── Row helpers (by key for stable indexing across computed rows) ────────────

function findRawIndex(key: string): number {
  return detailRows.value.findIndex(r => r.key === key)
}

function updateRowByKey(key: string, field: keyof M10DetailRow, value: any): void {
  const idx = findRawIndex(key)
  if (idx >= 0) detail.updateRow(idx, field, value)
}

function removeRowByKey(key: string): void {
  const idx = findRawIndex(key)
  if (idx >= 0) detail.removeRow(idx)
}

// ─── Handlers ────────────────────────────────────────────────────────────────

async function handleAddByType(type: string) {
  await detail.addRow(type as M10InstrumentType)
}

function handleImportExport(command: string) {
  switch (command) {
    case 'exportTemplate':
      importExport.exportTemplate('M10-2')
      break
    case 'exportData':
      importExport.exportData('M10-2')
      break
    case 'importData': {
      const input = document.createElement('input')
      input.type = 'file'
      input.accept = '.xlsx,.xls'
      input.onchange = async (e: Event) => {
        const file = (e.target as HTMLInputElement).files?.[0]
        if (file) {
          const result = await importExport.importData('M10-2', file)
          if (result?.success) {
            await formData.loadData()
            _restoreRows()
            ElMessage.success(`导入完成，共 ${result.rowCount} 行`)
          }
        }
      }
      input.click()
      break
    }
  }
}

function handleReview() {
  openReviewDialog?.('M10-2-detail', '其他权益工具明细表')
}

// ─── Format helpers ──────────────────────────────────────────────────────────

function fmtAmount(val: number): string {
  if (val === 0 || val === undefined || val === null) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Restore rows from checklist_responses ───────────────────────────────────

function _restoreRows() {
  const fullData = formData.allResponses.value.get('M10-2-full-data')
  if (fullData?.remark) {
    try {
      const parsed = JSON.parse(fullData.remark)
      if (Array.isArray(parsed) && parsed.length > 0) {
        detailRows.value = parsed
      }
    } catch { /* keep empty */ }
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  _restoreRows()
})
</script>

<style scoped>
.m10-tab-detail { padding: 12px; font-size: var(--wp-font-size, 13px); }
.dual-mode-switcher { margin-bottom: 12px; }

.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; flex-wrap: wrap; gap: 8px; }
.section-header-left { display: flex; align-items: center; gap: 8px; }
.section-header-right { display: flex; align-items: center; gap: 8px; }
.section-title { margin: 0; font-size: 15px; font-weight: 600; color: #303133; }

.methodology-context { border-left: 4px solid #e6a23c; background: #fdf6ec; padding: 12px 16px; border-radius: 0 6px 6px 0; margin-bottom: 16px; }
.methodology-text { font-size: var(--wp-font-size, 13px); color: #6b5900; line-height: 1.6; }

.cross-sheet-alert { margin-bottom: 12px; }
.segment-switcher { margin-bottom: 12px; }

.group-section { margin-bottom: 16px; }
.group-header { padding: 6px 12px; font-size: var(--wp-font-size, 13px); font-weight: 600; border-radius: 4px 4px 0 0; }
.group-header.perpetual-bond { background: #ecf5ff; color: #409eff; border-left: 3px solid #409eff; }
.group-header.preferred-stock { background: #f0f9eb; color: #67c23a; border-left: 3px solid #67c23a; }
.group-header.convertible { background: #fdf6ec; color: #e6a23c; border-left: 3px solid #e6a23c; }

.instrument-name { font-weight: 500; color: #303133; }
.formula-col-header { border-bottom: 1px dashed #909399; cursor: help; }
.formula-value { color: #409eff; font-weight: 500; }

.subtotal-row { padding: 6px 12px; font-size: 12px; color: #606266; background: #fafafa; border: 1px solid #ebeef5; border-top: none; border-radius: 0 0 4px 4px; margin-bottom: 4px; }

:deep(.el-table) { font-size: var(--wp-font-size, 13px); }
.total-bar { display: flex; gap: 24px; padding: 10px 16px; margin-top: 12px; border-radius: 6px; background: #f0f9eb; font-size: var(--wp-font-size, 13px); align-items: center; flex-wrap: wrap; }

.m10-details-tip { margin-top: 16px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.m10-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; }
.m10-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
