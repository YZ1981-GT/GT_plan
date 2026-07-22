<template>
  <div class="h2-tab-related-party">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：（1）资产负债表中记录的在建工程是存在的，且已记录于恰当的账户；（2）所有应记录的在建工程均已记录，相关披露均已包括；（3）记录的在建工程由被审计单位拥有或控制；（4）在建工程以恰当金额包括在财务报表中，计价或分摊调整已恰当记录；（5）在建工程已恰当汇总/分解且表述清楚，披露相关、可理解。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H2-17" :context-project-id="projectId" />
      <GtIndexChip value="wp:A7-1" :context-project-id="projectId" context="关联方披露 A7-1" />
      <GtIndexChip value="wp:H2-8" :context-project-id="projectId" context="增加检查" />
      <GtIndexChip value="wp:H2-9" :context-project-id="projectId" context="减少检查" />
      <el-tag size="small" type="info">共 {{ state.summary.value.count }} 笔</el-tag>
      <el-tag v-if="state.summary.value.abnormalCount > 0" size="small" type="danger">
        价差/异常 {{ state.summary.value.abnormalCount }}
      </el-tag>
      <el-tag v-if="state.summary.value.entryRemarkMissingCount > 0" size="small" type="warning">
        入账差异待备注 {{ state.summary.value.entryRemarkMissingCount }}
      </el-tag>
      <el-tag v-if="state.summary.value.sourceDriftCount > 0" size="small" type="danger">
        源已变更 {{ state.summary.value.sourceDriftCount }}
      </el-tag>
      <el-tag v-if="a7Status === 'mismatch'" size="small" type="warning">A7勾稽差异</el-tag>
      <el-tag v-if="state.summary.value.noTransaction" size="small" type="success">本期无此类交易</el-tag>
    </div>

    <el-alert
      v-if="state.summary.value.sourceDriftCount > 0 && !isReadonly"
      type="warning"
      show-icon
      :closable="false"
      class="obj-alert"
      title="检测到 H2-8/H2-9 源数据已变更，与已带入行不一致。"
    >
      <el-button size="small" type="primary" @click="handleRefreshDrift">刷新已漂移行</el-button>
    </el-alert>

    <el-alert
      v-if="a7ReconcileText"
      :type="a7Status === 'ok' ? 'success' : a7Status === 'mismatch' ? 'warning' : 'info'"
      show-icon
      :closable="true"
      class="obj-alert"
      :title="a7ReconcileText"
    />

    <div class="methodology-context">
      <p>
        <b>编制范围：</b>仅登记<strong>合并范围外</strong>关联方在建工程购入/出售；
        CIP 实务另设「工程服务」表（施工/供材/设计/监理）。
        可从 H2-8/H2-9 带入（需源表标记关联方）。
        价差率=(交易价−公允)/公允×100%；购入入账差异=入账价值−购买价款；出售净值=原值−减值。
      </p>
    </div>

    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" @click="handleImportSources">从 H2-8/H2-9 带入</el-button>
      <el-button size="small" @click="handleRecalcRatio">重算本表占比</el-button>
      <el-button size="small" @click="handleA7Reconcile">勾稽 A7-1</el-button>
      <el-button size="small" type="success" plain @click="handleNoTransaction">本期无此类交易</el-button>
      <span class="threshold-wrap">
        价差%
        <el-input-number v-model="thresholdLocal" :controls="false" :min="1" :max="100" size="small" style="width:56px" @change="onThresholdChange" />
        入账差异%
        <el-input-number v-model="entryThLocal" :controls="false" :min="1" :max="100" size="small" style="width:56px" @change="onEntryThChange" />
      </span>
      <el-dropdown trigger="click" @command="handleImportExport">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
    </div>

    <!-- (1) 购入 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>二、审计过程 — (1) 向合并范围外关联方采购在建工程</span>
          <div class="section-header-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('购入')">+ 购入</el-button>
            <el-button size="small" circle @click="openReview('H2-17')">💬</el-button>
          </div>
        </div>
      </template>
      <el-table :data="state.purchaseRows.value" border stripe size="small" max-height="320" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.counterparty"
              size="small"
              filterable
              allow-create
              default-first-option
              style="width:100%"
              placeholder="选择或输入"
              @change="onCell(row, 'counterparty')"
            >
              <el-option v-for="p in partyOptions" :key="p" :label="p" :value="p" />
            </el-select>
            <span v-else>{{ row.counterparty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relationship" size="small" filterable allow-create style="width:100%"
              @change="onRelationChange(row)">
              <el-option v-for="o in RELATION_OPTS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产类别" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small" @change="onCell(row, 'assetCategory')" />
            <span v-else>{{ row.assetCategory || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购买在建工程名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购买价款" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'transAmount')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="在建工程入账价值" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'bookValue')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入账差异" width="90" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', { 'warn-amount': Math.abs(row.entryDiff) > 0.01, 'error-amount': state.needsEntryDiffRemark(row) }]"
              title="入账价值−购买价款；超阈且无备注标红"
            >{{ fmtAmt(row.entryDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允/评估价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': state.isUnfair(row) }]">
              {{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="同类总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.categoryTotal" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'categoryTotal')" />
            <span v-else>{{ row.categoryTotal != null ? fmtAmt(row.categoryTotal) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占同类%" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.similarRatio != null ? row.similarRatio.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购入时间" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transDate" type="date" value-format="YYYY-MM-DD"
              size="small" style="width:110px" @change="onCell(row, 'transDate')" />
            <span v-else>{{ row.transDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.hasAnomaly" size="small" style="width:80px" @change="onCell(row, 'hasAnomaly')">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="待定" value="待定" />
            </el-select>
            <span v-else :class="{ 'error-amount': row.hasAnomaly === '是' }">{{ row.hasAnomaly || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small"
              :placeholder="state.needsEntryDiffRemark(row) ? '必填：说明入账差异' : ''"
              @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="onCell(row, 'indexRef')" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>购入 {{ state.summary.value.purchaseCount }} 笔</span>
        <span>价款合计 <b class="amt-cell">{{ fmtAmt(state.summary.value.purchaseTotal) }}</b></span>
        <span v-if="state.summary.value.entryDiffCount">入账差异 <b class="warn-amount">{{ state.summary.value.entryDiffCount }}</b> 笔</span>
      </div>
    </el-card>

    <!-- (2) 出售 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>(2) 向合并范围外关联方出售在建工程</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('出售')">+ 出售</el-button>
        </div>
      </template>
      <el-table :data="state.saleRows.value" border stripe size="small" max-height="320" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.counterparty"
              size="small"
              filterable
              allow-create
              default-first-option
              style="width:100%"
              placeholder="选择或输入"
              @change="onCell(row, 'counterparty')"
            >
              <el-option v-for="p in partyOptions" :key="p" :label="p" :value="p" />
            </el-select>
            <span v-else>{{ row.counterparty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relationship" size="small" filterable allow-create style="width:100%"
              @change="onRelationChange(row)">
              <el-option v-for="o in RELATION_OPTS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产类别" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small" @change="onCell(row, 'assetCategory')" />
            <span v-else>{{ row.assetCategory || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售在建工程名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售时原值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'originalCost')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'impairment')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售时净值" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值−减值">{{ fmtAmt(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="销售价格(不含税)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'transAmount')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="售价−净值">{{ fmtAmt(row.disposalGain) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允/评估价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': state.isUnfair(row) }]">
              {{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="占同类%" width="80" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ row.similarRatio != null ? row.similarRatio.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售时间" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transDate" type="date" value-format="YYYY-MM-DD"
              size="small" style="width:110px" @change="onCell(row, 'transDate')" />
            <span v-else>{{ row.transDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.hasAnomaly" size="small" style="width:80px" @change="onCell(row, 'hasAnomaly')">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="待定" value="待定" />
            </el-select>
            <span v-else :class="{ 'error-amount': row.hasAnomaly === '是' }">{{ row.hasAnomaly || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="onCell(row, 'indexRef')" />
            <span v-else>{{ row.indexRef || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>出售 {{ state.summary.value.saleCount }} 笔</span>
        <span>售价合计 <b class="amt-cell">{{ fmtAmt(state.summary.value.saleTotal) }}</b></span>
      </div>
    </el-card>

    <!-- (3) 工程服务 — CIP 实务增强 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-header">
          <span>(3) 向合并范围外关联方采购工程服务（施工/供材/设计/监理）</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('工程服务')">+ 服务</el-button>
        </div>
      </template>
      <el-table :data="state.serviceRows.value" border stripe size="small" max-height="280" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="120" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.counterparty"
              size="small"
              filterable
              allow-create
              default-first-option
              style="width:100%"
              placeholder="选择或输入"
              @change="onCell(row, 'counterparty')"
            >
              <el-option v-for="p in partyOptions" :key="p" :label="p" :value="p" />
            </el-select>
            <span v-else>{{ row.counterparty || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.relationship" size="small" filterable allow-create style="width:100%"
              @change="onRelationChange(row)">
              <el-option v-for="o in RELATION_OPTS" :key="o" :label="o" :value="o" />
            </el-select>
            <span v-else>{{ row.relationship || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="服务类型" width="90">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.assetCategory" size="small" style="width:100%" @change="onCell(row, 'assetCategory')">
              <el-option label="施工" value="施工" />
              <el-option label="供材" value="供材" />
              <el-option label="设计" value="设计" />
              <el-option label="监理" value="监理" />
            </el-select>
            <span v-else>{{ row.assetCategory || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程/合同名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="合同金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'transAmount')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期发生额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.currentAmount" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'currentAmount')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.currentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计发生额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.cumulativeAmount" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'cumulativeAmount')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.cumulativeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="市场价参考" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" class="amt-input"
              @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amt-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': state.isUnfair(row) }]">
              {{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审批文件" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.approvalDoc" size="small" placeholder="Y/N" @change="onCell(row, 'approvalDoc')" />
            <span v-else>{{ row.approvalDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="独董意见" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.independentDirectorOpinion" size="small"
              @change="onCell(row, 'independentDirectorOpinion')" />
            <span v-else>{{ row.independentDirectorOpinion || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.hasAnomaly" size="small" style="width:80px" @change="onCell(row, 'hasAnomaly')">
              <el-option label="否" value="否" />
              <el-option label="是" value="是" />
              <el-option label="待定" value="待定" />
            </el-select>
            <span v-else :class="{ 'error-amount': row.hasAnomaly === '是' }">{{ row.hasAnomaly || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>工程服务 {{ state.summary.value.serviceCount }} 笔</span>
        <span>金额合计 <b class="amt-cell">{{ fmtAmt(state.summary.value.serviceTotal) }}</b></span>
      </div>
    </el-card>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>三、审计说明</span>
          <el-button size="small" :disabled="isReadonly" @click="fillNoteDraft">填入异常摘要</el-button>
        </div>
      </template>
      <el-input
        v-model="state.auditNote.value"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="说明：合并范围外关联方识别、抽查范围、定价与评估、价差/入账差异异常及追加程序；无交易可点「本期无此类交易」。"
        @blur="state.saveNote(state.auditNote.value)"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input
        v-model="state.auditConclusion.value"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="结论示例：经检查，合并范围外关联方在建工程购销及工程服务真实，定价差异未超阈值 / 异常已披露 / 本期无此类交易……"
        @blur="state.saveConclusion(state.auditConclusion.value)"
      />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>范围：仅合并范围外；关系选「子公司」等会提示确认是否确属合并范围外</li>
        <li>H2-8/H2-9 标记「关联方=是」并填名称后，可一键带入；源变更会提示刷新</li>
        <li>购入：入账差异=入账价值−购买价款；超阈须备注（税费/运杂/利息资本化等）</li>
        <li>出售：净值=原值−减值；处置损益=售价−净值（关注利益输送）</li>
        <li>价差率&gt;阈值红色高亮；须取得评估报告/招投标/市场报价等公允性证据</li>
        <li>工程服务表覆盖 CIP 高频关联方施工/供材场景；旧版单一表数据会自动迁移至此</li>
        <li>A7-1 勾稽为交叉参考（A7 口径通常更宽）；交叉索引 H2-8 / H2-9</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabRelatedParty.vue — H2-17 关联交易检查表
 * 对齐致同 Excel：购入/出售双表 + 审计目标/说明/结论
 * 增强：公允价差、入账差异、处置损益、工程服务表、H2-8/9 带入（容错）、A7 勾稽、导入导出
 */
import { inject, toRef, computed, ref, watch, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH2RelatedParty,
  type H2RelatedPartyRow,
  type H2RpTransType,
  DEFAULT_PRICE_DIFF_THRESHOLD,
  DEFAULT_ENTRY_DIFF_THRESHOLD,
} from '../../composables/useH2RelatedParty'
import { useH2ImportExport } from '../../composables/useH2ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const RELATION_OPTS = ['母公司', '子公司', '联营企业', '合营企业', '关键管理人', '其他关联方']

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2RelatedParty({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const { exportTemplate, exportData, importData } = useH2ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => state.initFromAllResponses(),
})

const thresholdLocal = ref(DEFAULT_PRICE_DIFF_THRESHOLD)
const entryThLocal = ref(DEFAULT_ENTRY_DIFF_THRESHOLD)
const partyOptions = ref<string[]>([])
const a7Total = ref<number | null>(null)
const a7ReconcileText = ref('')
const a7Status = ref<'ok' | 'mismatch' | 'no-a7' | 'empty' | ''>('')
const fileInputRef = ref<HTMLInputElement | null>(null)

watch(() => state.settings.value, (s) => {
  thresholdLocal.value = s.priceDiffThreshold
  entryThLocal.value = s.entryDiffThreshold
}, { immediate: true, deep: true })

onMounted(async () => {
  await loadParties()
  await loadA7Total()
})

async function loadParties() {
  if (!props.projectId) return
  try {
    const res = await http.get(`/api/projects/${props.projectId}/related-parties`, { _silent: true } as any)
    const parties: any[] = Array.isArray(res.data) ? res.data : (res.data?.data ?? res.data?.registries ?? [])
    const names = parties.map((p: any) => (typeof p === 'string' ? p : p.name || p.party_name || '')).filter(Boolean)
    if (names.length) {
      partyOptions.value = [...new Set(names)]
      return
    }
  } catch { /* fallback */ }
  try {
    const res = await http.get(`/api/eqcr/projects/${props.projectId}/related-parties`, { _silent: true } as any)
    const regs: any[] = res.data?.registries ?? res.data?.data?.registries ?? []
    partyOptions.value = [...new Set(regs.map((p: any) => p.name || p.party_name).filter(Boolean))]
  } catch {
    partyOptions.value = []
  }
}

async function loadA7Total() {
  if (!props.projectId) return
  try {
    const year = new Date().getFullYear()
    const res = await http.get(
      `/api/projects/${props.projectId}/related-party-summary`,
      { params: { year }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    a7Total.value = data?.total_amount != null ? Number(data.total_amount) : null
  } catch {
    a7Total.value = null
  }
}

function onThresholdChange(v: number | undefined) {
  state.updateSettings({ priceDiffThreshold: Number(v) || DEFAULT_PRICE_DIFF_THRESHOLD })
}
function onEntryThChange(v: number | undefined) {
  state.updateSettings({ entryDiffThreshold: Number(v) || DEFAULT_ENTRY_DIFF_THRESHOLD })
}

function rowClass({ row }: { row: H2RelatedPartyRow }) {
  if (state.isUnfair(row) || row.hasAnomaly === '是') return 'price-alert-row'
  if (state.needsEntryDiffRemark(row)) return 'entry-warn-row'
  return ''
}

function onCell(row: H2RelatedPartyRow, field: string) {
  state.updateCell(row.rowId, field, (row as any)[field])
}

async function onRelationChange(row: H2RelatedPartyRow) {
  onCell(row, 'relationship')
  if (state.isLikelyInConsolidationScope(row.relationship)) {
    try {
      await ElMessageBox.confirm(
        `「${row.relationship}」通常属于合并范围。本表仅登记合并范围外关联方交易，请确认是否确属合并范围外。`,
        '合并范围提示',
        { confirmButtonText: '确属范围外', cancelButtonText: '我再改', type: 'warning' },
      )
    } catch {
      row.relationship = ''
      onCell(row, 'relationship')
    }
  }
}

function handleAdd(transType: H2RpTransType) {
  state.addRow(transType)
}

function handleRecalcRatio() {
  state.recalcSimilarRatios()
  ElMessage.success('已按本表各类型合计重算占同类%')
}

function handleNoTransaction() {
  state.applyNoTransaction()
  ElMessage.success('已标记本期无此类交易')
}

function fillNoteDraft() {
  const draft = state.buildNoteDraft()
  state.auditNote.value = draft
  state.saveNote(draft)
  ElMessage.success('已填入异常摘要')
}

async function handleImportSources() {
  const result = state.importFromH8H9()
  if (result.added > 0) {
    ElMessage.success(result.message)
    if (result.inScopeCandidates.length) {
      try {
        await ElMessageBox.confirm(
          `其中 ${result.inScopeCandidates.length} 笔关系疑似合并范围内。是否仍保留？`,
          '合并范围确认',
          { confirmButtonText: '仍保留', cancelButtonText: '删除这些行', type: 'warning' },
        )
      } catch {
        for (const r of result.inScopeCandidates) state.removeRow(r.rowId)
        ElMessage.info(`已删除 ${result.inScopeCandidates.length} 笔疑似合并范围内交易`)
      }
    }
  } else {
    ElMessage.warning(result.message)
  }
}

function handleRefreshDrift() {
  const n = state.refreshDriftedFromSource()
  ElMessage.success(n > 0 ? `已刷新 ${n} 笔漂移行` : '无需刷新或源行已删除')
}

async function handleA7Reconcile() {
  await loadA7Total()
  const r = state.getA7Reconcile(a7Total.value)
  a7Status.value = r.status
  a7ReconcileText.value = r.note
  if (r.status === 'ok') ElMessage.success(r.note)
  else if (r.status === 'mismatch') ElMessage.warning(r.note)
  else ElMessage.info(r.note)
}

async function handleImportExport(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H2-17')
  else if (cmd === 'export-data') await exportData('H2-17')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  input.value = ''
  if (!file) return
  await importData('H2-17', file)
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
.h2-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.methodology-context {
  margin-bottom: 10px; padding: 8px 12px;
  background: var(--el-fill-color-lighter); border-radius: 4px; font-size: 12px; color: var(--el-text-color-regular);
}
.methodology-context p { margin: 0; line-height: 1.6; }
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.threshold-wrap { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--el-text-color-secondary); margin-left: 4px; }
.block-card, .audit-note-card { margin-bottom: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.section-header-actions { display: flex; gap: 8px; align-items: center; }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); font-weight: 600; }
.summary-bar {
  display: flex; flex-wrap: wrap; gap: 16px; margin-top: 8px;
  font-size: 12px; color: var(--el-text-color-secondary);
}
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
:deep(.price-alert-row) { background-color: #fef0f0 !important; }
:deep(.entry-warn-row) { background-color: #fdf6ec !important; }
</style>
