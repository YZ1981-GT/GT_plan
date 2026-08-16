<template>
  <div class="h6-tab-detail">
    <!-- 审计目标（对齐致同模板三认定） -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实固定资产清理存在性与记录恰当性；确认应记清理均已入账且披露充分；验证金额准确、结转及时，关注长期挂账。"
    />

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p>
        H6-2 明细表：逐项登记清理全过程 + 1606 余额变动（期初/增减/期末×未审·调整·审定）。
        净值=原值−累计折旧−减值准备；净损益=处置收入−净值−清理费用−税费。
        过渡科目期末应清零；转入清理超 1 年须说明进展（挂账关注）。
      </p>
    </div>

    <!-- Section Title -->
    <div class="section-header">
      <span>固定资产清理明细表 H6-2</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H6-2-detail')">💬</el-button>
      </div>
    </div>

    <!-- 工具栏：底稿索引 + 行数 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button
          v-if="!props.isReadonly && rows.length"
          size="small"
          plain
          @click="handleSyncBalanceFromNbv"
        >
          按净值同步余额增减
        </el-button>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:H6-2" :context-project-id="props.projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-tag size="small" type="info">截止日 {{ asOfDate }}</el-tag>
      </div>
    </div>

    <!-- 状态摘要 -->
    <div v-if="rows.length > 0" class="status-summary">
      <el-tag size="small" type="info">共 {{ statusSummary.total }} 项</el-tag>
      <el-tag v-if="statusSummary.clearing > 0" size="small" type="warning">清理中 {{ statusSummary.clearing }}</el-tag>
      <el-tag v-if="statusSummary.completed > 0" size="small" type="success">已完成 {{ statusSummary.completed }}</el-tag>
      <el-tag v-if="statusSummary.transferred > 0" size="small" type="primary">已结转 {{ statusSummary.transferred }}</el-tag>
      <el-tag v-if="statusSummary.uncleared > 0" size="small" type="warning">
        未结转 {{ statusSummary.uncleared }}
      </el-tag>
      <el-tag v-if="statusSummary.overOneYearUncleared > 0" size="small" type="danger">
        超1年未结转 {{ statusSummary.overOneYearUncleared }}
      </el-tag>
      <el-tag v-if="hasCriticalWarning" size="small" type="danger">
        ⚠ 存在挂账/结转缺陷，请关注
      </el-tag>
    </div>

    <!-- 3区段Tab -->
    <el-segmented v-model="activeTab" :options="segmentOptions" size="small" class="segment-bar" />

    <!-- 基础信息区段 -->
    <el-table
      v-if="activeTab === 'basic'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!props.isReadonly" v-model="row.assetName" size="small"
            @change="updateCell(row.rowId, 'assetName', $event)" />
          <span v-else>{{ row.assetName }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="originalCost" label="原值" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.originalCost"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'originalCost', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.originalCost) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="accumulatedDepreciation" label="累计折旧" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.accumulatedDepreciation"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'accumulatedDepreciation', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.accumulatedDepreciation) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="impairmentProvision" label="减值准备" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.impairmentProvision"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'impairmentProvision', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.impairmentProvision) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="netBookValue" label="净值" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="净值 = 原值 − 累计折旧 − 减值准备">{{ fmtAmt(row.netBookValue) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="disposalReason" label="清理原因" min-width="140">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly"
            v-model="row.disposalReason"
            size="small"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="updateCell(row.rowId, 'disposalReason', $event)"
          >
            <el-option v-for="opt in reasonOptions" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.disposalReason || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="startDate" label="转入清理时间" min-width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!props.isReadonly"
            v-model="row.startDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%"
            @change="updateCell(row.rowId, 'startDate', $event)"
          />
          <span v-else>{{ row.startDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 余额变动区段（对齐 Excel H6-2 B–L） -->
    <el-table
      v-if="activeTab === 'balance'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="项目" min-width="120" fixed />
      <el-table-column label="未审数" align="center">
        <el-table-column label="期初数" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.beginUnadjusted"
              size="small"
              class="amt-input"
              @change="updateCell(row.rowId, 'beginUnadjusted', $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.beginUnadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.periodIncrease"
              size="small"
              class="amt-input"
              @change="updateCell(row.rowId, 'periodIncrease', $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.periodIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.periodDecrease"
              size="small"
              class="amt-input"
              @change="updateCell(row.rowId, 'periodDecrease', $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.periodDecrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="期末=期初+增加−减少">{{ fmtAmt(row.endUnadjusted) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="期初调整" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!props.isReadonly"
            v-model="row.beginAdjustment"
            :controls="false"
            size="small"
            class="amt-input"
            @change="updateCell(row.rowId, 'beginAdjustment', $event)"
          />
          <span v-else class="amt-cell">{{ fmtAmt(row.beginAdjustment) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="账项调整" align="center">
        <el-table-column label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.ajeIncrease"
              size="small"
              class="amt-input"
              @change="updateCell(row.rowId, 'ajeIncrease', $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.ajeIncrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="!props.isReadonly"
              v-model="row.ajeDecrease"
              size="small"
              class="amt-input"
              @change="updateCell(row.rowId, 'ajeDecrease', $event)"
            />
            <span v-else class="amt-cell">{{ fmtAmt(row.ajeDecrease) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column label="审定数" align="center">
        <el-table-column label="期初数" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="审定期初=未审期初+期初调整">{{ fmtAmt(row.beginAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.increaseAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.decreaseAudited) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末数" min-width="100" align="right">
          <template #default="{ row }">
            <span
              class="formula-cell"
              :class="{ 'error-amount': row.status === '已结转' && Math.abs(row.endAudited) > 0.01 }"
              title="审定期末=审定期初+审定增加−审定减少"
            >{{ fmtAmt(row.endAudited) }}</span>
          </template>
        </el-table-column>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
    </el-table>

    <!-- 清理信息区段 -->
    <el-table
      v-if="activeTab === 'disposal'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed />
      <el-table-column prop="disposalIncome" label="处置收入" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.disposalIncome"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'disposalIncome', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.disposalIncome) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="disposalExpenses" label="清理费用" min-width="110" align="right">
        <template #default="{ row }">
          <WpAmountInput v-if="!props.isReadonly" v-model="row.disposalExpenses"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'disposalExpenses', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.disposalExpenses) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="taxAmount" label="税费" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!props.isReadonly" v-model="row.taxAmount" :controls="false"
            size="small" class="amt-input"
            @change="updateCell(row.rowId, 'taxAmount', $event)" />
          <span v-else class="amt-cell">{{ fmtAmt(row.taxAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="gainLoss" label="净损益" min-width="110" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="净损益 = 处置收入 − 净值 − 清理费用 − 税费">
            {{ fmtAmt(row.gainLoss) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column prop="transferAccount" label="结转科目" min-width="140">
        <template #default="{ row }">
          <el-select
            v-if="!props.isReadonly"
            v-model="row.transferAccount"
            size="small"
            clearable
            filterable
            allow-create
            placeholder="选择或输入"
            @change="updateCell(row.rowId, 'transferAccount', $event)"
          >
            <el-option v-for="opt in transferAccountOptions" :key="opt" :value="opt" :label="opt" />
          </el-select>
          <span v-else>{{ row.transferAccount || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="completionDate" label="完成日期" min-width="130">
        <template #default="{ row }">
          <el-date-picker
            v-if="!props.isReadonly"
            v-model="row.completionDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            style="width: 100%"
            @change="updateCell(row.rowId, 'completionDate', $event)"
          />
          <span v-else>{{ row.completionDate || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!props.isReadonly" v-model="row.status" size="small"
            @change="handleStatusChange(row.rowId, $event)">
            <el-option value="清理中" label="清理中" />
            <el-option value="已完成" label="已完成" />
            <el-option value="已结转" label="已结转" />
          </el-select>
          <el-tag v-else :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="refH1Code" label="联动H1编号" min-width="130">
        <template #default="{ row }">
          <template v-if="!props.isReadonly">
            <el-input v-model="row.refH1Code" size="small" placeholder="H1-8-xxx"
              @change="updateCell(row.rowId, 'refH1Code', $event)" />
          </template>
          <GtIndexChip v-else-if="row.refH1Code" :value="row.refH1Code" :context-project-id="props.projectId" />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column prop="refH10Code" label="联动H10编号" min-width="130">
        <template #default="{ row }">
          <template v-if="!props.isReadonly">
            <el-input v-model="row.refH10Code" size="small" placeholder="H10-xxx"
              @change="updateCell(row.rowId, 'refH10Code', $event)" />
          </template>
          <GtIndexChip v-else-if="row.refH10Code" :value="row.refH10Code" :context-project-id="props.projectId" />
          <span v-else class="text-muted">-</span>
        </template>
      </el-table-column>
      <el-table-column label="警告" width="70" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="criticalWarnings(row).length"
            :content="criticalWarnings(row).map(w => w.message).join('；')"
            placement="top"
          >
            <span class="warning-icon">⚠</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 挂账关注区段（对齐 xlsx：超1年进展 / 备注） -->
    <el-table
      v-if="activeTab === 'aging'"
      :data="rows"
      border
      stripe
      size="small"
      class="detail-table"
      row-key="rowId"
      max-height="480"
      :row-class-name="rowClassName"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />
      <el-table-column prop="assetName" label="资产名称" min-width="120" fixed />
      <el-table-column prop="startDate" label="转入清理时间" min-width="120" />
      <el-table-column label="是否超1年" width="100" align="center">
        <template #default="{ row }">
          <el-tag v-if="isRowOverOneYear(row)" size="small" type="danger">是</el-tag>
          <el-tag v-else size="small" type="info">否</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="status" label="状态" width="90" align="center">
        <template #default="{ row }">
          <el-tag :type="statusTagType(row.status)" size="small">{{ row.status }}</el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="overOneYearProgress" label="超1年清理进展情况" min-width="220">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            v-model="row.overOneYearProgress"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 3 }"
            size="small"
            :placeholder="isRowOverOneYear(row) && row.status !== '已结转' ? '必填：说明长期挂账原因与预计结转安排' : '可选'"
            @change="updateCell(row.rowId, 'overOneYearProgress', $event)"
          />
          <span v-else>{{ row.overOneYearProgress || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="remarks" label="备注" min-width="160">
        <template #default="{ row }">
          <el-input
            v-if="!props.isReadonly"
            v-model="row.remarks"
            size="small"
            @change="updateCell(row.rowId, 'remarks', $event)"
          />
          <span v-else>{{ row.remarks || '-' }}</span>
        </template>
      </el-table-column>
      <el-table-column label="警告" width="70" align="center">
        <template #default="{ row }">
          <el-tooltip
            v-if="criticalWarnings(row).length"
            :content="criticalWarnings(row).map(w => w.message).join('；')"
            placement="top"
          >
            <span class="warning-icon">⚠</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column label="" width="45" v-if="!props.isReadonly">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 合计行 -->
    <el-card shadow="never" class="subtotal-card">
      <div class="subtotal-grid">
        <div class="subtotal-item">
          <span class="st-label">原值合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.originalCost) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">累计折旧合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.accumulatedDepreciation) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">减值准备合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.impairmentProvision) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">净值合计：</span>
          <span class="st-value formula-cell" title="Σ净值 = Σ原值 − Σ累计折旧 − Σ减值">{{ fmtAmt(subtotalRow.netBookValue) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">处置收入合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.disposalIncome) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">清理费用合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.disposalExpenses) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">净损益合计：</span>
          <span class="st-value formula-cell" title="Σ净损益 = Σ处置收入 − Σ净值 − Σ清理费用 − Σ税费">{{ fmtAmt(subtotalRow.gainLoss) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">未审期初合计：</span>
          <span class="st-value">{{ fmtAmt(subtotalRow.beginUnadjusted) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">未审期末合计：</span>
          <span class="st-value formula-cell">{{ fmtAmt(subtotalRow.endUnadjusted) }}</span>
        </div>
        <div class="subtotal-item">
          <span class="st-label">审定期末合计：</span>
          <span class="st-value formula-cell" title="供 H6-1 回填 / 过渡科目校验">{{ fmtAmt(subtotalRow.endAudited) }}</span>
        </div>
      </div>
    </el-card>

    <!-- 操作栏 -->
    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" @click="handleAddRow">+ 添加清理项目</el-button>
      <el-dropdown trigger="click" @command="handleImportExport" style="margin-left: 8px">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-2-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 10 }"
        placeholder="请填写审计说明（含超1年挂账原因、结转时点、与H6-1勾稽差异等）..."
        :disabled="props.isReadonly"
        @blur="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" circle @click="openReview('H6-2-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly"
        @blur="saveAuditConclusion" />
    </el-card>

    <!-- 编制提示 -->
    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>编制思路：存在性/完整性/准确性 → 逐项清理过程 → 余额变动勾稽 → 挂账关注 → 说明与结论</li>
        <li>四区段：基础信息 / 余额变动 / 清理结转 / 挂账关注；切换后行数据不丢失</li>
        <li>余额变动对齐 Excel：期末未审=期初+增加−减少；审定期初=未审期初+期初调整；供 H6-1 回填</li>
        <li>净值=原值−累计折旧−减值准备；净损益=处置收入−净值−清理费用−税费（结转后净损益≠0属正常）</li>
        <li>状态：清理中→已完成→已结转；已结转须填写结转科目（资产处置损益/营业外收支等）</li>
        <li>超1年未结转且无进展说明 → 红色警告（致同模板核心关注点）</li>
        <li>联动H1/H10编号可追溯处置来源与损益去向；合计行与H6-1交叉验证</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
/**
 * H6TabDetail.vue — H6-2 明细表
 *
 * 区段：基础信息 | 余额变动 | 清理结转 | 挂账关注
 * 改进：Excel 期初/增减/调整列、减值入净值、原因枚举、超1年进展
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH6Detail,
  H6_DISPOSAL_REASON_OPTIONS,
  type H6DetailRow,
  type H6DetailRowWarning,
} from '../../composables/useH6Detail'
import { useH6ImportExport } from '../../composables/useH6ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', (itemId, value) => {
  const strVal = value != null ? (typeof value === 'string' ? value : JSON.stringify(value)) : null
  props.allResponses.set(itemId, { item_id: itemId, remark: strVal, conclusion: null })
})

const allResponsesRef = computed(() => props.allResponses)

const {
  rows, activeTab, asOfDate, subtotalRow, statusSummary, hasCriticalWarning,
  addRow, deleteRow, updateCell, save: _save, createFromH1Disposal,
  syncBalanceFromNetBook,
  rowWarnings, isRowOverOneYear,
} = useH6Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const registerDetailCreateFn = inject<(fn: (payload: any) => void) => void>('registerDetailCreateFn', () => {})

onMounted(() => {
  registerDetailCreateFn(createFromH1Disposal)
  const noteItem = props.allResponses.get('H6-2-note')
  if (noteItem?.remark) auditNote.value = noteItem.remark
  const concItem = props.allResponses.get('H6-2-conclusion')
  if (concItem?.remark) auditConclusion.value = concItem.remark
})

const importExport = useH6ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => {},
})

const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '余额变动', value: 'balance' },
  { label: '清理结转', value: 'disposal' },
  { label: '挂账关注', value: 'aging' },
]

const reasonOptions = [...H6_DISPOSAL_REASON_OPTIONS]

/** 结转科目常见选项（CAS30：正常处置→资产处置损益；非正常→营业外） */
const transferAccountOptions = [
  '资产处置损益',
  '营业外收入',
  '营业外支出——处置非流动资产损失',
  '营业外支出——非常损失',
]

function criticalWarnings(row: H6DetailRow): H6DetailRowWarning[] {
  return rowWarnings(row).filter(
    w => w.kind === 'over_one_year_no_progress' || w.kind === 'transferred_missing_account',
  )
}

function rowClassName({ row }: { row: H6DetailRow }): string {
  if (isRowOverOneYear(row) && row.status !== '已结转') return 'row-aging-risk'
  if (row.status !== '已结转') return 'row-uncleared'
  return ''
}

const auditNote = ref('')
function saveAuditNote() {
  saveResponse('H6-2-note', auditNote.value)
}
const auditConclusion = ref('')
function saveAuditConclusion() {
  saveResponse('H6-2-conclusion', auditConclusion.value)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产名称', '添加清理项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '资产名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleSyncBalanceFromNbv() {
  const { applied } = syncBalanceFromNetBook()
  ElMessage.success(`已按净值同步 ${applied} 行余额增减`)
}

async function handleDeleteRow(rowId: string) {
  try {
    await ElMessageBox.confirm('确认删除该清理项目？删除后不可恢复。', '删除确认', {
      confirmButtonText: '确认删除',
      cancelButtonText: '取消',
      type: 'warning',
    })
    deleteRow(rowId)
  } catch { /* cancelled */ }
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H6-2')
  else if (command === 'export-data') importExport.exportData('H6-2')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H6-2', file)
    }
    input.click()
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function statusTagType(status: string): '' | 'success' | 'warning' | 'info' | 'danger' {
  switch (status) {
    case '清理中': return 'warning'
    case '已完成': return 'success'
    case '已结转': return 'info'
    default: return ''
  }
}

/**
 * 状态变更为「已结转」时发布 disposal:completed → H10
 * 注：净损益≠0 属正常（即结转到损益的金额），不告警
 */
function handleStatusChange(rowId: string, newStatus: string): void {
  updateCell(rowId, 'status', newStatus)

  if (newStatus === '已结转') {
    const row = rows.value.find(r => r.rowId === rowId)
    if (row) {
      window.dispatchEvent(new CustomEvent('disposal:completed', {
        detail: {
          wpCode: 'H6',
          assetName: row.assetName,
          gainLoss: row.gainLoss,
          refH10Code: row.refH10Code || '',
          refH1Code: row.refH1Code || '',
          originalCost: row.originalCost,
          impairmentProvision: row.impairmentProvision,
          netBookValue: row.netBookValue,
          disposalIncome: row.disposalIncome,
          disposalExpenses: row.disposalExpenses,
          taxAmount: row.taxAmount,
          completionDate: row.completionDate,
          transferAccount: row.transferAccount,
          linkageId: `h6-${row.rowId}`,
        },
      }))
    }
  }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  if (val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h6-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.methodology-context {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  font-size: 12px;
  color: #856404;
  line-height: 1.6;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 14px;
}
.section-header-actions { display: flex; gap: 4px; align-items: center; }

.status-summary { display: flex; gap: 6px; margin-bottom: 10px; flex-wrap: wrap; }

.tab-toolbar {
  display: flex; align-items: center; justify-content: space-between;
  gap: 8px; margin-bottom: 10px;
}
.tab-toolbar .toolbar-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.tab-toolbar .toolbar-right { display: flex; align-items: center; gap: 8px; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.segment-bar { margin-bottom: 12px; }

.detail-table { width: 100%; }

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  color: #303133;
}
.error-amount { color: #f56c6c; font-weight: 600; }

.amt-input { width: 100%; }
.amt-cell { font-variant-numeric: tabular-nums; }

.warning-icon { color: #f56c6c; font-size: 16px; }
.text-muted { color: #c0c4cc; }

.subtotal-card { margin-top: 12px; }
.subtotal-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px 16px;
}
.subtotal-item { display: flex; align-items: center; }
.st-label { font-size: 12px; color: #606266; white-space: nowrap; }
.st-value { font-weight: 600; font-size: var(--wp-font-size, 13px); color: #303133; margin-left: 4px; }

.action-bar { margin-top: 12px; display: flex; align-items: center; }

.audit-note-card { margin-top: 16px; }

.edit-tips {
  margin-top: 16px;
  font-size: 12px;
  color: #909399;
}
.edit-tips summary {
  cursor: pointer;
  font-weight: 500;
  color: #606266;
}
.edit-tips ul {
  margin: 8px 0 0;
  padding-left: 20px;
  line-height: 1.8;
}

:deep(.row-aging-risk) > td {
  background-color: #fef0f0 !important;
}
:deep(.row-uncleared) > td {
  background-color: #fdf6ec !important;
}
</style>
