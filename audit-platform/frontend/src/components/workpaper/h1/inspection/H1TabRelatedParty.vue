<template>
  <div class="h1-tab-related-party">
    <el-alert type="info" :closable="false" show-icon class="obj-alert">
      <template #title>
        审计目标：（1）资产负债表中记录的固定资产是存在的；（2）所有应当记录的固定资产均已记录；（3）记录的固定资产由被审计单位拥有或控制；（4）固定资产以恰当金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录；（5）固定资产已按照企业会计准则的规定在财务报表中作出恰当列报。
      </template>
    </el-alert>

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-18" :context-project-id="projectId" />
      <GtIndexChip value="wp:A7-1" :context-project-id="projectId" context="关联方披露 A7-1" />
      <GtIndexChip value="wp:H10" :context-project-id="projectId" context="处置损益 H10" />
      <el-tag size="small" type="info">共 {{ relatedSummary.count }} 笔</el-tag>
      <el-tag v-if="relatedSummary.abnormalCount > 0" size="small" type="danger">
        价差&gt;{{ relatedSummary.priceDiffThreshold }}% {{ relatedSummary.abnormalCount }}
      </el-tag>
      <el-tag v-if="relatedSummary.entryRemarkMissingCount > 0" size="small" type="warning">
        入账差异待备注 {{ relatedSummary.entryRemarkMissingCount }}
      </el-tag>
      <el-tag v-if="relatedSummary.h10MismatchCount > 0" size="small" type="warning">
        H10不一致 {{ relatedSummary.h10MismatchCount }}
      </el-tag>
      <el-tag v-if="relatedSummary.sourceDriftCount > 0" size="small" type="danger">
        源已变更 {{ relatedSummary.sourceDriftCount }}
      </el-tag>
      <el-tag v-if="a7Status === 'mismatch'" size="small" type="warning">A7勾稽差异</el-tag>
      <el-tag v-if="relatedSummary.noTransaction" size="small" type="success">本期无此类交易</el-tag>
    </div>

    <el-alert
      v-if="relatedSummary.sourceDriftCount > 0 && !isReadonly"
      type="warning"
      show-icon
      :closable="false"
      class="obj-alert"
      title="检测到 H1-7/H1-8 源数据已变更，与已带入行不一致。"
    >
      <el-button size="small" type="primary" @click="handleRefreshDrift">刷新已漂移行</el-button>
    </el-alert>

    <el-alert
      v-if="relatedSummary.entryRemarkMissingCount > 0"
      type="error"
      show-icon
      :closable="false"
      class="obj-alert"
      :title="`有 ${relatedSummary.entryRemarkMissingCount} 笔购入/调拨入账差异超过 ${relatedSummary.entryDiffThreshold}%，请在备注说明税费/运杂费等构成。`"
    />

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
        <b>编制范围：</b>仅登记<strong>合并范围外</strong>关联方固定资产购入/出售/无偿调拨。
        可从 H1-7/H1-8 带入；同类总额可从 H1-2 取数；出售与 H10 按资产编号/源引用匹配。
      </p>
    </div>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!isReadonly">
      <el-button size="small" type="primary" @click="handleImportSources">从 H1-7/H1-8 带入</el-button>
      <el-button size="small" @click="handleFillFromH12">H1-2 同类总额</el-button>
      <el-button size="small" @click="handleRecalcRatio">重算本表占比</el-button>
      <el-button size="small" @click="handleH10Check">勾稽 H10</el-button>
      <el-button size="small" @click="handleA7Reconcile">勾稽 A7-1</el-button>
      <el-button size="small" @click="handleAdjDraft">异常调整建议</el-button>
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
        <div class="section-title">
          <span>二、审计过程 — (1) 向合并范围外关联方采购固定资产</span>
          <div class="title-actions">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('购入')">+ 购入</el-button>
            <el-button size="small" type="default" link @click="handleReview('H1-18')">💬 复核</el-button>
          </div>
        </div>
      </template>
      <el-table :data="purchaseRows" border stripe size="small" max-height="320" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }"><PartyCell :row="row" :parties="partyOptions" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }"><RelationCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="资产类别" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small" @change="onCell(row, 'assetCategory')" />
            <span v-else>{{ row.assetCategory }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购买固定资产名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="购买价款" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" @change="onCell(row, 'transAmount')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入账价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入账差异" width="90" align="right">
          <template #default="{ row }">
            <span
              :class="['formula-cell', {
                'warn-amount': Math.abs(row.entryDiff) > 0.01,
                'error-amount': needsEntryRemark(row),
              }]"
              title="入账价值−购买价款；超阈且无备注标红"
            >{{ fmtAmt(row.entryDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允/评估价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isUnfair(row) }]">{{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="同类总额" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.categoryTotal" :controls="false" size="small" @change="onCell(row, 'categoryTotal')" />
            <span v-else>{{ row.categoryTotal != null ? fmtAmt(row.categoryTotal) : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占同类%" width="80" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.similarRatio != null ? row.similarRatio.toFixed(1) + '%' : '-' }}</span></template>
        </el-table-column>
        <el-table-column label="购入时间" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'transDate')" />
            <span v-else>{{ row.transDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧年限" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.depYears" :controls="false" :min="0" size="small" @change="onCell(row, 'depYears')" />
            <span v-else>{{ row.depYears || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }"><AnomalyCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="备注" min-width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              :placeholder="needsEntryRemark(row) ? '必填：说明入账差异' : ''"
              @change="onCell(row, 'remark')"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="onCell(row, 'indexRef')" />
            <span v-else>{{ row.indexRef }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId" title="上传合同 OCR 预填" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('18', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>购入 {{ relatedSummary.purchaseCount }} 笔</span>
        <span>价款合计 <b class="amount-cell">{{ fmtAmt(relatedSummary.purchaseTotal) }}</b></span>
        <span v-if="relatedSummary.entryDiffCount">入账差异 <b class="warn-amount">{{ relatedSummary.entryDiffCount }}</b> 笔</span>
      </div>
    </el-card>

    <!-- (1b) 无偿调拨 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>(1b) 无偿调拨固定资产</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('无偿调拨')">+ 调拨</el-button>
        </div>
      </template>
      <el-table :data="transferRows" border stripe size="small" max-height="240" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }"><PartyCell :row="row" :parties="partyOptions" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }"><RelationCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="资产名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入账价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.bookValue" :controls="false" size="small" @change="onCell(row, 'bookValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.bookValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="公允/评估价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isUnfair(row) }]">
              {{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="调拨时间" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'transDate')" />
            <span v-else>{{ row.transDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价/依据" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" placeholder="零对价/评估入账等" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }"><AnomalyCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="备注" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="onCell(row, 'remark')" />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId" title="上传合同 OCR 预填" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('18', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar"><span>无偿调拨 {{ relatedSummary.transferCount }} 笔</span></div>
    </el-card>

    <!-- (2) 出售 -->
    <el-card shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>(2) 向合并范围外关联方出售固定资产</span>
          <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAdd('出售')">+ 出售</el-button>
        </div>
      </template>
      <el-table :data="saleRows" border stripe size="small" max-height="320" :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="关联单位名称" min-width="130" fixed>
          <template #default="{ row }"><PartyCell :row="row" :parties="partyOptions" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="关联方关系" width="110">
          <template #default="{ row }"><RelationCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="资产类别" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetCategory" size="small" @change="onCell(row, 'assetCategory')" />
            <span v-else>{{ row.assetCategory }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售固定资产名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onCell(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售时原值" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.originalCost" :controls="false" size="small" @change="onCell(row, 'originalCost')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.originalCost) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="累计折旧" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.accumDep" :controls="false" size="small" @change="onCell(row, 'accumDep')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.accumDep) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.impairment" :controls="false" size="small" @change="onCell(row, 'impairment')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出售时净值" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="原值−累计折旧−减值">{{ fmtAmt(row.netValue) }}</span></template>
        </el-table-column>
        <el-table-column label="销售价格(不含税)" width="120" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.transAmount" :controls="false" size="small" @change="onCell(row, 'transAmount')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.transAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="处置损益" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell" title="售价−净值">{{ fmtAmt(row.disposalGain) }}</span></template>
        </el-table-column>
        <el-table-column label="H10损益" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.h10Gain != null ? fmtAmt(row.h10Gain) : '-' }}</span></template>
        </el-table-column>
        <el-table-column label="H10差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': row.h10Diff != null && Math.abs(row.h10Diff) > 0.01 }]">
              {{ row.h10Diff != null ? fmtAmt(row.h10Diff) : '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="公允/评估价值" width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.appraisedValue" :controls="false" size="small" @change="onCell(row, 'appraisedValue')" />
            <span v-else class="amount-cell">{{ fmtAmt(row.appraisedValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异率%" width="80" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': isUnfair(row) }]">{{ row.appraisedValue > 0 ? row.priceDiffRate.toFixed(1) + '%' : '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="占同类%" width="80" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.similarRatio != null ? row.similarRatio.toFixed(1) + '%' : '-' }}</span></template>
        </el-table-column>
        <el-table-column label="出售时间" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.transDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:110px" @change="onCell(row, 'transDate')" />
            <span v-else>{{ row.transDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="定价政策" min-width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.pricingPolicy" size="small" @change="onCell(row, 'pricingPolicy')" />
            <span v-else>{{ row.pricingPolicy }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="90" align="center">
          <template #default="{ row }"><AnomalyCell :row="row" :readonly="isReadonly" @change="onCell" /></template>
        </el-table-column>
        <el-table-column label="索引号" width="80">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexRef" size="small" @change="onCell(row, 'indexRef')" />
            <span v-else>{{ row.indexRef }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="OCR" width="52" align="center" fixed="right">
          <template #default="{ row }">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId" title="上传合同 OCR 预填" @click="handleOcr(row)">📎</el-button>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="50" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="removeRow('18', row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="summary-bar">
        <span>出售 {{ relatedSummary.saleCount }} 笔</span>
        <span>售价合计 <b class="amount-cell">{{ fmtAmt(relatedSummary.saleTotal) }}</b></span>
        <span>价差超阈 <b :class="{ 'error-amount': relatedSummary.abnormalCount > 0 }">{{ relatedSummary.abnormalCount }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="section-title">
          <span>三、审计说明</span>
          <el-button size="small" :disabled="isReadonly" @click="fillNoteDraft">填入异常摘要</el-button>
          <el-button size="small" :disabled="isReadonly" @click="generateAI">AI</el-button>
        </div>
      </template>
      <el-input
        v-model="auditNoteText"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="说明：合并范围外关联方识别、抽查范围、定价与评估、价差/入账差异/H10勾稽异常及追加程序；无交易可点「本期无此类交易」。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input
        v-model="conclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="结论示例：经检查，合并范围外关联方固定资产购销真实，定价差异未超阈值 / 异常已披露 / 本期无此类交易……"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>H1-7/H1-8 将「关联方=是」并填关联方名称后，可一键带入；源变更会提示刷新</li>
        <li>入账差异=入账价值−购买价款；超阈须填备注。出售净值=原值−累计折旧−减值</li>
        <li>占同类%：优先「H1-2 同类总额」（按资产类别本期增减），或「重算本表占比」</li>
        <li>H10 匹配顺序：sourceRowRef/linkageId → 资产编号 → 唯一资产名称</li>
        <li>关系选「子公司」等会提示确认是否确属合并范围外；A7-1 勾稽为交叉参考</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabRelatedParty — H1-18 关联交易检查表（全量增强）
 * 双表+无偿调拨 / H1-7·8带入 / 入账差异 / 占比 / H10勾稽 / 无交易 / 导入导出 / A7跳转
 */
import { ref, computed, inject, toRef, onMounted, defineComponent, h } from 'vue'
import { ElMessage, ElMessageBox, ElSelect, ElOption } from 'element-plus'
import {
  useH1LeaseCheck,
  type RelatedPartyRow,
  DEFAULT_PRICE_DIFF_THRESHOLD,
  DEFAULT_ENTRY_DIFF_THRESHOLD,
  needsEntryDiffRemark,
  isLikelyInConsolidationScope,
} from '../../composables/useH1LeaseCheck'
import { useH1ImportExport } from '../../composables/useH1ImportExport'
import { pullH10DetailRowsForH1 } from '../../composables/h1RelatedH10Pull'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const RELATION_OPTS = ['母公司', '子公司', '联营企业', '合营企业', '关键管理人', '其他关联方']

const PartyCell = defineComponent({
  name: 'PartyCell',
  props: {
    row: { type: Object as () => RelatedPartyRow, required: true },
    parties: { type: Array as () => string[], default: () => [] },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(props, { emit }) {
    return () => {
      if (props.readonly) return h('span', props.row.counterparty)
      return h(ElSelect, {
        modelValue: props.row.counterparty,
        'onUpdate:modelValue': (v: string) => { props.row.counterparty = v },
        size: 'small',
        filterable: true,
        allowCreate: true,
        defaultFirstOption: true,
        style: { width: '100%' },
        placeholder: '选择或输入',
        onChange: () => emit('change', props.row, 'counterparty'),
      }, () => props.parties.map((p) => h(ElOption, { key: p, label: p, value: p })))
    }
  },
})

const RelationCell = defineComponent({
  name: 'RelationCell',
  props: {
    row: { type: Object as () => RelatedPartyRow, required: true },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(props, { emit }) {
    return () => {
      if (props.readonly) return h('span', props.row.relationship)
      return h(ElSelect, {
        modelValue: props.row.relationship,
        'onUpdate:modelValue': (v: string) => { props.row.relationship = v },
        size: 'small',
        filterable: true,
        allowCreate: true,
        style: { width: '100%' },
        onChange: () => emit('change', props.row, 'relationship'),
      }, () => RELATION_OPTS.map((o) => h(ElOption, { key: o, label: o, value: o })))
    }
  },
})

const AnomalyCell = defineComponent({
  name: 'AnomalyCell',
  props: {
    row: { type: Object as () => RelatedPartyRow, required: true },
    readonly: Boolean,
  },
  emits: ['change'],
  setup(props, { emit }) {
    return () => {
      if (props.readonly) {
        return h('span', { class: props.row.hasAnomaly === '是' ? 'error-amount' : '' }, props.row.hasAnomaly || '-')
      }
      return h(ElSelect, {
        modelValue: props.row.hasAnomaly,
        'onUpdate:modelValue': (v: string) => { props.row.hasAnomaly = v },
        size: 'small',
        style: { width: '80px' },
        onChange: () => emit('change', props.row, 'hasAnomaly'),
      }, () => [
        h(ElOption, { label: '否', value: '否' }),
        h(ElOption, { label: '是', value: '是' }),
        h(ElOption, { label: '待定', value: '待定' }),
      ])
    }
  },
})

const props = defineProps<{ wpId: string; projectId: string; allResponses: Map<string, any>; isReadonly: boolean }>()
const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)

const conclusion = ref('')
const auditNoteText = ref('')
const ocrLoadingId = ref('')
const partyOptions = ref<string[]>([])
const thresholdLocal = ref(DEFAULT_PRICE_DIFF_THRESHOLD)
const entryThLocal = ref(DEFAULT_ENTRY_DIFF_THRESHOLD)
const a7Total = ref<number | null>(null)
const a7ReconcileText = ref('')
const a7Status = ref<'ok' | 'mismatch' | 'no-a7' | 'empty' | ''>('')
const fileInputRef = ref<HTMLInputElement | null>(null)
const NOTE_KEY = 'H1-18-audit-note'
const CONCLUSION_KEY = 'H1-18-audit-conclusion'

function saveAuditNote() { saveResponse(NOTE_KEY, auditNoteText.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, conclusion.value) }

const {
  purchaseRows,
  transferRows,
  saleRows,
  relatedSummary,
  relatedSettings,
  addRelatedRow,
  removeRow,
  updateRelatedCell,
  applyRelatedPartyOcr,
  importFromH7H8,
  refreshDriftedFromSource,
  recalcSimilarRatios,
  fillCategoryTotalsFromH12,
  syncH10CrossCheck,
  applyNoTransaction,
  buildRelatedPartyNoteDraft,
  buildAdjSuggestionAndPersist,
  getA7Reconcile,
  updateRelatedSettings,
} = useH1LeaseCheck(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const { exportTemplate, exportData, importData } = useH1ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})

onMounted(async () => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) conclusion.value = c.remark
  thresholdLocal.value = relatedSettings.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
  entryThLocal.value = relatedSettings.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD
  await loadParties()
  await loadA7Total()
})

function needsEntryRemark(row: RelatedPartyRow) {
  return needsEntryDiffRemark(row, relatedSummary.value.entryDiffThreshold || DEFAULT_ENTRY_DIFF_THRESHOLD)
}

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

function isUnfair(row: RelatedPartyRow) {
  const th = relatedSummary.value.priceDiffThreshold || DEFAULT_PRICE_DIFF_THRESHOLD
  return Math.abs(row.priceDiffRate) > th
}

function rowClass({ row }: { row: RelatedPartyRow }) {
  if (isUnfair(row) || row.hasAnomaly === '是' || needsEntryRemark(row)) return 'row-abnormal'
  if (row.h10Diff != null && Math.abs(row.h10Diff) > 0.01) return 'row-warn'
  return ''
}

async function confirmInScopeIfNeeded(rows: RelatedPartyRow[]) {
  const hits = rows.filter((r) => isLikelyInConsolidationScope(r.relationship))
  if (!hits.length) return
  try {
    await ElMessageBox.confirm(
      `以下 ${hits.length} 笔关联关系疑似合并范围内（如子公司），本表仅登记合并范围外交易。是否仍保留？\n` +
      hits.slice(0, 5).map((r) => `· ${r.counterparty || r.name}（${r.relationship}）`).join('\n'),
      '合并范围确认',
      { confirmButtonText: '仍保留', cancelButtonText: '删除这些行', type: 'warning' },
    )
  } catch {
    for (const r of hits) removeRow('18', r.rowId)
    ElMessage.info(`已删除 ${hits.length} 笔疑似合并范围内交易`)
  }
}

async function handleAdd(transType: string) {
  try {
    const { value: name } = await ElMessageBox.prompt('关联单位名称', `新增${transType}`, {
      confirmButtonText: '确定', cancelButtonText: '取消',
    })
    if (name != null) {
      addRelatedRow(transType)
      const pool = transType === '出售' ? saleRows.value
        : transType === '无偿调拨' ? transferRows.value
          : purchaseRows.value
      const last = pool[pool.length - 1]
      if (last) {
        updateRelatedCell(last.rowId, 'counterparty', name)
        if (transType === '无偿调拨') updateRelatedCell(last.rowId, 'transAmount', 0)
      }
    }
  } catch { /* cancel */ }
}

async function onCell(row: RelatedPartyRow, field: keyof RelatedPartyRow) {
  updateRelatedCell(row.rowId, field, (row as any)[field])
  if (field === 'relationship' && isLikelyInConsolidationScope(row.relationship)) {
    await confirmInScopeIfNeeded([row])
  }
}

function onThresholdChange(v: number | undefined) {
  updateRelatedSettings({ priceDiffThreshold: Number(v) || DEFAULT_PRICE_DIFF_THRESHOLD })
}
function onEntryThChange(v: number | undefined) {
  updateRelatedSettings({ entryDiffThreshold: Number(v) || DEFAULT_ENTRY_DIFF_THRESHOLD })
}

async function handleImportSources() {
  const { added, skipped, inScopeCandidates } = importFromH7H8()
  if (added === 0 && skipped === 0) {
    ElMessage.warning('H1-7/H1-8 中未找到「关联方=是」的记录，请先在增加/减少检查表标记')
  } else {
    ElMessage.success(`带入 ${added} 笔，跳过已存在 ${skipped} 笔`)
  }
  if (inScopeCandidates.length) await confirmInScopeIfNeeded(inScopeCandidates)
}

function handleRefreshDrift() {
  const { refreshed, missing } = refreshDriftedFromSource()
  ElMessage.success(`已刷新 ${refreshed} 笔${missing ? `，源行缺失 ${missing}` : ''}`)
}

function handleFillFromH12() {
  const n = fillCategoryTotalsFromH12()
  if (n === 0) ElMessage.warning('未匹配到 H1-2 同类类别（请先填写资产类别，且 H1-2 有对应本期增减）')
  else ElMessage.success(`已从 H1-2 填入 ${n} 行同类总额并重算占比`)
}

function handleRecalcRatio() {
  const n = recalcSimilarRatios()
  ElMessage.success(`已按本表同类合计重算 ${n} 行占比`)
}

async function handleH10Check() {
  const pull = await pullH10DetailRowsForH1(props.projectId)
  if (pull.status === 'wp_missing' || pull.status === 'error') {
    ElMessage.warning(pull.message)
    return
  }
  if (pull.status === 'empty') {
    ElMessage.warning('H10 明细为空，无法勾稽')
  }
  const { matched, mismatch, unmatched } = syncH10CrossCheck(pull.rows)
  ElMessage.info(`H10 匹配 ${matched}，差异 ${mismatch}，未匹配 ${unmatched}${pull.h10WpId ? '（已跨底稿拉数）' : ''}`)
}

async function handleA7Reconcile() {
  await loadA7Total()
  const r = getA7Reconcile(a7Total.value)
  a7Status.value = r.status
  a7ReconcileText.value = r.note
  if (r.status === 'ok') ElMessage.success(r.note)
  else if (r.status === 'mismatch') ElMessage.warning(r.note)
  else ElMessage.info(r.note)
}

async function handleAdjDraft() {
  if (relatedSummary.value.entryRemarkMissingCount > 0) {
    ElMessage.warning('请先补全入账差异备注后再生成调整建议')
    return
  }
  const draft = buildAdjSuggestionAndPersist()
  try {
    await ElMessageBox.confirm(draft, '异常调整建议草稿', {
      confirmButtonText: '写入审计说明',
      cancelButtonText: '关闭',
      type: 'info',
      customStyle: { maxWidth: '640px', whiteSpace: 'pre-wrap' },
    })
    auditNoteText.value = (auditNoteText.value ? auditNoteText.value + '\n\n' : '') + draft
    saveAuditNote()
    window.dispatchEvent(new CustomEvent('adjustment:push-to-a13', {
      detail: { wp_code: 'H1', source: 'H1-18', draft },
    }))
    ElMessage.success('已写入说明，并广播调整建议事件（可供 A13 监听）')
  } catch { /* cancel */ }
}

function handleNoTransaction() {
  const { note, conclusion: conc } = applyNoTransaction()
  auditNoteText.value = note
  conclusion.value = conc
  ElMessage.success('已写入「本期无此类交易」说明与结论')
}

function fillNoteDraft() {
  auditNoteText.value = buildRelatedPartyNoteDraft()
  saveAuditNote()
  ElMessage.success('已填入异常摘要草稿')
}

function generateAI() {
  const draft = buildRelatedPartyNoteDraft()
  window.dispatchEvent(new CustomEvent('ai:generate', {
    detail: {
      section: 'H1-18',
      wpId: props.wpId,
      existingContent: auditNoteText.value,
      relatedContext: draft,
    },
  }))
}

async function handleImportExport(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('H1-18')
  else if (cmd === 'export-data') await exportData('H1-18')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(ev: Event) {
  const file = (ev.target as HTMLInputElement).files?.[0]
  ;(ev.target as HTMLInputElement).value = ''
  if (!file) return
  await importData('H1-18', file)
}

/** 行级关联交易合同 OCR：📎 → contract-ocr → 确认 → 仅填空预填 */
async function handleOcr(row: RelatedPartyRow) {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = 'image/*,.pdf'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const formData = new FormData()
    formData.append('file', file)
    ocrLoadingId.value = row.rowId
    try {
      const res = await http.post(
        `/api/workpapers/${props.wpId}/d4/contract-ocr`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
      )
      const data = res.data?.data ?? res.data
      const fields = { ...(data?.extracted_fields || {}) }
      if (data?.attachment_id) fields.attachment_id = data.attachment_id
      const preview = Object.entries(fields)
        .filter(([k, v]) => k !== 'attachment_id' && v !== '' && v != null && v !== 0)
        .map(([k, v]) => `${k}: ${v}`)
      if (!preview.length) {
        ElMessageBox.alert('OCR 完成，未识别到可填充字段', '提示')
        return
      }
      await ElMessageBox.confirm(`识别结果：\n${preview.join('\n')}\n\n确认填入空白字段？`, '关联交易合同 OCR 识别结果', {
        confirmButtonText: '填入', cancelButtonText: '取消',
      })
      const filled = applyRelatedPartyOcr(row.rowId, fields)
      ElMessage.success(filled.length ? `已预填 ${filled.length} 个字段` : '无可填空字段（已有值未覆盖）')
    } catch (e: any) {
      if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('合同 OCR 失败，请稍后重试或手工录入')
    } finally {
      ocrLoadingId.value = ''
    }
  }
  input.click()
}

function handleReview(id: string) { openReviewDialog(id) }

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h1-tab-related-party { padding: 16px; font-size: var(--wp-font-size, 13px); }
.obj-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology-context {
  border-left: 3px solid var(--el-color-warning);
  background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px;
  font-size: 12px; line-height: 1.6;
}
.action-bar { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.threshold-wrap { display: inline-flex; align-items: center; gap: 4px; font-size: 12px; color: var(--el-text-color-secondary); margin-left: 4px; }
.block-card { margin-bottom: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap; }
.title-actions { display: flex; gap: 8px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning); font-weight: 600; }
.summary-bar {
  display: flex; flex-wrap: wrap; gap: 16px 24px;
  padding: 10px 12px; margin-top: 12px;
  background: var(--el-fill-color-light); border-radius: 4px; font-size: 12px;
}
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.row-abnormal) { background: var(--el-color-danger-light-9) !important; }
:deep(.row-warn) { background: var(--el-color-warning-light-9) !important; }
</style>
