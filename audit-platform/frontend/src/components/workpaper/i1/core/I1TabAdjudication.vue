<template>
  <div class="i1-adjudication">
    <!-- 双模式切换 -->
    <div class="mode-switcher">
      <el-segmented v-model="viewMode" :options="['结构化视图', '在线编辑']" />
      <el-segmented
        v-model="columnLayout"
        size="small"
        :options="[
          { label: '增减编制', value: 'movement' },
          { label: 'Excel六列', value: 'excel6' },
        ]"
      />
    </div>

    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>三角勾稽原理：</strong>审定表按三科目（原值1701/累计摊销1702/减值准备1703）分区块校验。</p>
      <p>原值（资产类借方）：期末余额 = 期初余额 + 本期增加 - 本期减少</p>
      <p>摊销/减值（备抵类贷方）：期末余额 = 期初余额 + 贷方发生（计提）- 借方发生（转回）</p>
      <p>净值合计 = 原值小计 - 摊销小计 - 减值小计。任一行勾稽差额≠0将红色高亮提示。</p>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：核实无形资产原值(1701)、累计摊销(1702)、减值准备(1703)期末审定余额的准确、完整，确认三角勾稽及与 TB、明细表勾稽一致。"
      class="objective-alert"
    />

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 审定表按原值(1701借方/资产类)、累计摊销(1702贷方/备抵类)、减值准备(1703贷方/备抵类)三区块分别列示。</p>
        <p>2. 资产类：期末=期初+本期增加-本期减少；备抵类：期末=期初+贷方发生(计提/摊销)-借方发生(转回/转出)。</p>
        <p>3. 审定数=未审数+AJE+RJE，应与 TB 未审数核对差异；净值=原值小计-摊销小计-减值小计。</p>
        <p>4. 审定完成后回写 TB 科目 1701/1702/1703，并与明细表 I1-2 小计交叉验证（差额红色/黄色高亮）。</p>
      </div>
    </details>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :loading="adjPullCost.loading.value" @click="openBringInCost">
          <el-icon><Download /></el-icon>带入调整(原值)
        </el-button>
        <el-button size="small" type="primary" plain :loading="adjPullAmort.loading.value" @click="openBringInAmort">
          <el-icon><Download /></el-icon>带入调整(摊销)
        </el-button>
        <el-button size="small" type="primary" plain :loading="adjPullImpair.loading.value" @click="openBringInImpair">
          <el-icon><Download /></el-icon>带入调整(减值)
        </el-button>
        <el-dropdown v-if="!isReadonly" trigger="click" @command="handleFillFromDetail">
          <el-button size="small">从 I1-2 带入 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="book">写入未审（保留 AJE/RJE）</el-dropdown-item>
              <el-dropdown-item command="full">按审定覆盖（清零 AJE/RJE）</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-dropdown
          v-if="!isReadonly"
          size="small"
          :disabled="ieBusy"
          @command="handleIeCommand"
        >
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data" divided>导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || !canSyncI13"
          @click="handleSyncI13"
        >
          从 I1-3 回写 AJE/RJE
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" :loading="publishing" @click="handlePublish">
          确认审定 → 回写TB
        </el-button>
        <el-tag size="small" :type="isAllReconciled ? 'success' : 'danger'">
          {{ isAllReconciled ? '三角勾稽平衡' : '勾稽不平' }}
        </el-tag>
        <el-tag v-if="significantNetChanges.length" size="small" type="warning">
          重大变动 {{ significantNetChanges.length }}
        </el-tag>
        <el-tag v-if="canSyncI13" size="small" type="success" effect="plain">
          I1-3：1701 {{ fmtAmount(i13Nets.costAje) }} / 1702 {{ fmtAmount(-i13Nets.amortAje) }}
        </el-tag>
        <el-tag
          v-if="amortProvisionCross.periodTotal !== 0 || amortProvisionCross.provision !== 0"
          size="small"
          :type="amortProvisionCross.matched ? 'success' : 'warning'"
          class="nav-chip"
          @click="navigateTo('I1-10')"
        >
          {{ amortProvisionCross.matched ? '摊销测算已勾稽' : '摊销测算待勾稽' }}
        </el-tag>
        <el-tag
          v-if="allocCross.allocSum !== 0"
          size="small"
          :type="allocCross.matched ? 'success' : 'warning'"
          class="nav-chip"
          @click="navigateTo('I1-9')"
        >
          {{ allocCross.matched ? 'I1-9分配已勾稽' : 'I1-9分配待勾稽' }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:I1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" class="nav-chip" @click="navigateTo('I1-2')">I1-2 →</el-tag>
        <el-tag size="small" class="nav-chip" @click="navigateTo('I1-3')">I1-3 →</el-tag>
      </div>
    </div>

    <WpFourTableSourcePanel
      :source-codes="tbSourceCodes"
      :gross-label="sourceConfig.grossLabel"
      :provision-label="sourceConfig.provisionLabel"
      :fallback-row-code="sourceConfig.fallbackRowCode"
      :hints="sourceConfig.hints"
    />

    <!-- 交叉验证警告 -->
    <div v-if="hasCrossWarning" class="cross-validation-warning">
      <el-badge :value="crossWarningCount" type="warning" class="cross-badge">
        <span>⚠ 审定表合计与I1-2明细表不一致，请核对</span>
      </el-badge>
    </div>

    <!-- Excel 六列只读对照（不改存储结构） -->
    <div v-if="columnLayout === 'excel6'" class="excel6-view">
      <el-alert
        type="info"
        :closable="false"
        show-icon
        title="Excel 六列视图为只读对照：期初/期末各「未审·调整·审定」。编制与保存请切回「增减编制」。"
        class="excel6-alert"
      />
      <div v-for="block in excel6Blocks" :key="block.key" class="block-section">
        <div class="block-header">
          <span class="block-title">{{ block.title }}</span>
        </div>
        <el-table :data="block.rows" border size="small" class="adjudication-table">
          <el-table-column prop="category" label="项目" min-width="140" fixed />
          <el-table-column label="期初未审" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginUnadj) }}</template>
          </el-table-column>
          <el-table-column label="期初调整" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.beginAdj) }}</template>
          </el-table-column>
          <el-table-column label="期初审定" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.beginAudited) }}</span></template>
          </el-table-column>
          <el-table-column label="期末未审" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endUnadj) }}</template>
          </el-table-column>
          <el-table-column label="期末调整" min-width="100" align="right">
            <template #default="{ row }">{{ fmtAmount(row.endAdj) }}</template>
          </el-table-column>
          <el-table-column label="期末审定" min-width="100" align="right">
            <template #default="{ row }"><span class="formula-value">{{ fmtAmount(row.endAudited) }}</span></template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <div v-show="columnLayout === 'movement'">
    <!-- 区块一：无形资产-原值（1701借方/资产类） -->
    <div class="block-section block-cost">
      <div class="block-header">
        <span class="block-title">一、无形资产-原值（1701借方/资产类）</span>
        <div class="block-actions">
          <el-button size="small" type="default" text @click="handleReview('cost')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="costDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              @change="onCellChange('cost', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              @change="onCellChange('cost', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              @change="onCellChange('cost', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="期末余额 = 期初余额 + 本期增加 - 本期减少" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              @change="onCellChange('cost', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              @change="onCellChange('cost', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              @change="onCellChange('cost', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="100" align="right">
          <template #header>
            <el-tooltip content="变动额 = 期末审定 − 期初（对齐 Excel 比较列）" placement="top">
              <span class="formula-col-header">变动额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(rowChange(row).amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-value', { 'sig-change': rowChange(row).significant }]">
              {{ fmtPct(rowChange(row).rate) }}
            </span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区块二：累计摊销（1702贷方/备抵类） -->
    <div class="block-section block-amort">
      <div class="block-header">
        <span class="block-title">二、累计摊销（1702贷方/备抵类）</span>
        <div class="block-actions">
          <el-button size="small" type="default" text @click="handleReview('amort')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="amortDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              @change="onCellChange('amort', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              @change="onCellChange('amort', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              @change="onCellChange('amort', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="备抵类：期末 = 期初 + 贷方(增加) - 借方(减少)" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              @change="onCellChange('amort', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              @change="onCellChange('amort', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              @change="onCellChange('amort', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
      
        <el-table-column label="变动额" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(rowChange(row).amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-value', { 'sig-change': rowChange(row).significant }]">
              {{ fmtPct(rowChange(row).rate) }}
            </span>
          </template>
        </el-table-column>

      </el-table>
    </div>

    <!-- 区块三：减值准备（1703贷方/备抵类） -->
    <div class="block-section block-impairment">
      <div class="block-header">
        <span class="block-title">三、减值准备（1703贷方/备抵类）</span>
        <div class="block-actions">
          <el-button size="small" type="default" text @click="handleReview('impairment')">
            复核
          </el-button>
        </div>
      </div>
      <el-table
        :data="impairmentDisplayRows"
        border
        size="small"
        :row-class-name="getRowClassName"
        class="adjudication-table"
      >
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="beginBalance" label="期初余额" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.beginBalance"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'beginBalance', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.beginBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.increase"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'increase', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.increase) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.decrease"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'decrease', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.decrease) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" min-width="110" align="right">
          <template #header>
            <el-tooltip content="备抵类：期末 = 期初 + 贷方(增加) - 借方(减少)" placement="top">
              <span class="formula-col-header">期末余额</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-tooltip :content="getReconciliationTooltip(row.rowId)" placement="top" :disabled="isRowBalanced(row.rowId)">
              <span :class="['formula-value', { 'subtotal-text': row.isSubtotal, 'reconciliation-error': !isRowBalanced(row.rowId) }]">
                {{ fmtAmount(row.endBalance) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="110" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.unadjusted"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'unadjusted', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.unadjusted) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.aje"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'aje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.aje) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="100" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="row.isEditable && !isReadonly"
              v-model="row.rje"
              size="small"
              @change="onCellChange('impairment', row.rowId, 'rje', $event)"
            />
            <span v-else :class="{ 'subtotal-text': row.isSubtotal }">{{ fmtAmount(row.rje) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="110" align="right">
          <template #header>
            <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
              <span class="formula-col-header">审定数</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <span :class="['formula-value', { 'subtotal-text': row.isSubtotal }]">
              {{ fmtAmount(row.audited) }}
            </span>
          </template>
        </el-table-column>
      
        <el-table-column label="变动额" min-width="100" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(rowChange(row).amount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-value', { 'sig-change': rowChange(row).significant }]">
              {{ fmtPct(rowChange(row).rate) }}
            </span>
          </template>
        </el-table-column>

      </el-table>
    </div>

        <!-- 四、净值（按分类 + 变动额/率，对齐 Excel） -->
    <div class="block-section block-net">
      <div class="block-header">
        <span class="block-title">四、净值（原值 − 累计摊销 − 减值准备）</span>
      </div>
      <el-table :data="netRows" border size="small" class="adjudication-table" :row-class-name="netRowClass">
        <el-table-column prop="category" label="项目" min-width="140" fixed>
          <template #default="{ row }">
            <span :class="{ 'subtotal-text': row.isSubtotal, 'net-value-text': row.isSubtotal }">{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期初净值" min-width="120" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.beginNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末审定净值" min-width="130" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.endNet) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动额" min-width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmount(row.changeAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动率" min-width="100" align="right">
          <template #default="{ row }">
            <span :class="['formula-value', { 'sig-change': row.isSignificant }]">{{ fmtPct(row.changeRate) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="变动说明" min-width="180">
          <template #default="{ row }">
            <template v-if="!row.isSubtotal">
              <el-input
                v-if="!isReadonly"
                :model-value="row.explanation"
                size="small"
                :placeholder="row.isSignificant ? '重大变动须说明…' : '可选说明…'"
                @change="(v: string) => setNetExplanation(row.category, v)"
              />
              <span v-else>{{ row.explanation || '—' }}</span>
            </template>
            <span v-else>—</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="net-hint">
        审定净值合计 <b>{{ fmtAmount(netValueAudited) }}</b>
        （期初 {{ fmtAmount(netValueBegin) }}）；变动率绝对值≥{{ CHANGE_RATE_THRESHOLD }}% 须在下方说明原因。
      </p>
    </div>

    <!-- TB取数行 + 差异行 -->
    <div class="tb-section">
      <div class="block-header">
        <span class="block-title">TB取数与差异</span>
      </div>
      <el-table :data="differenceRows" border size="small" class="adjudication-table tb-table">
        <el-table-column prop="label" label="科目" min-width="160" />
        <el-table-column prop="tbAmount" label="TB未审数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.tbAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="audited" label="审定表审定数" min-width="120" align="right">
          <template #default="{ row }">
            <span>{{ fmtAmount(row.audited) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="difference" label="差异" min-width="120" align="right">
          <template #default="{ row }">
            <el-tooltip
              :content="`差异 = 审定数(${fmtAmount(row.audited)}) - TB未审数(${fmtAmount(row.tbAmount)})`"
              placement="top"
            >
              <span :class="{ 'difference-warning': Math.abs(row.difference) > 0.01 }">
                {{ fmtAmount(row.difference) }}
              </span>
            </el-tooltip>
          </template>
        </el-table-column>
      </el-table>
    </div>

    </div><!-- /columnLayout movement -->

    <div class="cross-ref-bar">
      <span class="cross-ref-label">跨底稿联动：</span>
      <GtIndexChip value="wp:I1-2" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-3" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-5" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-7" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-8" :context-project-id="projectId" />
      <GtIndexChip value="wp:I1-9" :context-project-id="projectId" />
    </div>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>1. 审计说明事项（对齐源模板）</span>
          <el-button size="small" :disabled="isReadonly" @click="fillFluctuationDraft">填入重大变动草稿</el-button>
          <el-button size="small" :disabled="isReadonly" data-testid="i1-1-draft-indefinite" @click="fillIndefiniteDraft">
            从 I1-7 带入说明(2)
          </el-button>
        </div>
      </template>
      <div class="qual-grid">
        <div class="qual-item">
          <label>(1) 净值重大变动原因（变动率≥{{ CHANGE_RATE_THRESHOLD }}%）</label>
          <el-input
            v-model="qualitativeNotes.fluctuation"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 5 }"
            :disabled="isReadonly"
            placeholder="分析期末与期初净值变动；变动率≥30% 须说明主要原因…"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(2) 使用寿命不确定无形资产的判断依据</label>
          <el-input
            v-model="qualitativeNotes.indefiniteLife"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="列示寿命不确定资产及管理层判断依据（可与 I1-7 勾稽）…"
            @blur="saveQualitativeNotes()"
          />
        </div>
        <div class="qual-item">
          <label>(3) 权属、抵押情况说明</label>
          <el-input
            v-model="qualitativeNotes.ownershipPledge"
            type="textarea"
            :autosize="{ minRows: 2, maxRows: 4 }"
            :disabled="isReadonly"
            placeholder="说明权属归属、抵押/质押受限情况（可与 I1-8 勾稽）…"
            @blur="saveQualitativeNotes()"
          />
        </div>
      </div>
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header"><span>审计说明</span></div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="概述三角勾稽、重大变动、调整事项及与 I1-2/TB 勾稽结果…"
        :disabled="isReadonly"
        @blur="onNoteBlur"
      />
    </el-card>

    <el-card class="audit-note-card" shadow="never">
      <template #header>
        <div class="card-header">
          <span>2. 审计结论</span>
          <el-select
            v-if="!isReadonly"
            size="small"
            placeholder="套用结论模板"
            style="width: 160px"
            @change="onConclusionTemplate"
          >
            <el-option label="A 公允反映" value="A" />
            <el-option label="B 存在调整" value="B" />
            <el-option label="C 重大错报" value="C" />
          </el-select>
        </div>
      </template>
      <el-input
        v-model="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 10 }"
        placeholder="评价无形资产及相关备抵科目在重大方面是否公允反映…"
        :disabled="isReadonly"
        @blur="onConclusionBlur"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制说明（摘自源模板）</summary>
      <ul>
        <li>结构：原值 → 累计摊销 → 减值准备 → 净值（含变动额/率）→ TB 差异 → 说明事项 → 结论</li>
        <li>「从 I1-2 带入」：未审模式保留 AJE/RJE；审定覆盖写入明细审定并清零调整；审定=未审+AJE+RJE</li>
        <li>净值变动率≥{{ CHANGE_RATE_THRESHOLD }}% 须在说明事项(1)或分类说明中解释</li>
        <li>结论模板：A 无异常确认 / B 调整后确认 / C 重大未调整或范围受限不能确认</li>
        <li>「确认审定」回写 TB 1701/1702/1703 并发布 substantive:adjudicated</li>
        <li>「带入调整(原值/摊销/减值)」：从集中登记按科目 1701/1702/1703 拉取调整分录，逐笔分配到各分类行的 AJE/RJE，带入后审定数自动更新并联动附注</li>
      </ul>
    </details>

    <AdjudicationBringInDialog
      v-model="bringInCostVisible"
      :matches="adjPullCost.matches.value"
      :row-options="bringInCostRowOptions"
      subject-label="1701 无形资产原值"
      :loading="adjPullCost.loading.value"
      @apply="onBringInCostApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInAmortVisible"
      :matches="adjPullAmort.matches.value"
      :row-options="bringInAmortRowOptions"
      subject-label="1702 累计摊销"
      :loading="adjPullAmort.loading.value"
      @apply="onBringInAmortApply"
    />
    <AdjudicationBringInDialog
      v-model="bringInImpairVisible"
      :matches="adjPullImpair.matches.value"
      :row-options="bringInImpairRowOptions"
      subject-label="1703 减值准备"
      :loading="adjPullImpair.loading.value"
      @apply="onBringInImpairApply"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, toRef, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import { useI1Adjudication, type I1BlockType, type I1AdjudicationRow, type I1NetValueRow } from '../../composables/useI1Adjudication'
import { useI1CrossSheet } from '../../composables/useI1CrossSheet'
import { useI1ImportExport } from '../../composables/useI1ImportExport'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import { useAuditContext } from '@/composables/useAuditContext'
import { eventBus } from '@/utils/eventBus'
import { Download } from '@element-plus/icons-vue'
import GtIndexChip from '../../GtIndexChip.vue'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import WpFourTableSourcePanel from '../../shared/WpFourTableSourcePanel.vue'
import { getICycleSourceConfig, extractTbSourceCodes } from '../../composables/useICycleFourTableSource'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: {
    unadjusted1701: number
    audited1701: number
    unadjusted1702: number
    audited1702: number
    unadjusted1703: number
    audited1703: number
  }
  isReadonly: boolean
  crossSheetCostAudited?: number
  crossSheetAmortAudited?: number
  crossSheetImpairAudited?: number
  htmlData?: Record<string, unknown> | null
}>()

const sourceConfig = getICycleSourceConfig('I1')
const tbSourceCodes = computed(() => extractTbSourceCodes(props.htmlData))

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Composable ──────────────────────────────────────────────────────────────

const {
  costRows,
  amortRows,
  impairmentRows,
  auditNote,
  auditConclusion,
  qualitativeNotes,
  costSubtotal,
  amortSubtotal,
  impairmentSubtotal,
  netValueRow,
  netValueAudited,
  netValueBegin,
  netRows,
  reconciliationResults,
  differenceRows,
  crossValidation,
  isAllReconciled,
  significantNetChanges,
  updateCell,
  saveAdjudication,
  saveNote,
  saveConclusion,
  saveQualitativeNotes,
  setNetExplanation,
  fillFromDetail,
  rowChange,
  applyConclusionTemplate,
  draftFluctuationNote,
  draftIndefiniteLifeNote,
  syncAjeRjeFromI13,
  CHANGE_RATE_THRESHOLD,
} = useI1Adjudication(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  toRef(props, 'allResponses'),
  {
    tbData: toRef(props, 'tbData'),
    crossSheetCostAudited: toRef(props, 'crossSheetCostAudited'),
    crossSheetAmortAudited: toRef(props, 'crossSheetAmortAudited'),
    crossSheetImpairAudited: toRef(props, 'crossSheetImpairAudited'),
    onSave: (itemId: string, value: any) => emit('save', itemId, value),
  },
)

const publishing = ref(false)

// ─── 从集中登记带入调整（三科目：1701原值[资产借方] / 1702累计摊销[备抵credit] / 1703减值准备[备抵credit]；带入期末 AJE/RJE） ───
const bringInCostRows = computed(() =>
  costRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const bringInAmortRows = computed(() =>
  amortRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const bringInImpairRows = computed(() =>
  impairmentRows.value.filter((r) => !r.isSubtotal).map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull: adjPullCost,
  visible: bringInCostVisible,
  rowOptions: bringInCostRowOptions,
  open: openBringInCost,
  apply: onBringInCostApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1701',
  direction: 'debit',
  subjectCode: '1701',
  wpCode: 'I1',
  subjectLabel: '无形资产原值(1701)',
  rows: bringInCostRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('cost', rowKey, field, value),
  totalAudited: () => costSubtotal.value.audited,
})
const {
  adjPull: adjPullAmort,
  visible: bringInAmortVisible,
  rowOptions: bringInAmortRowOptions,
  open: openBringInAmort,
  apply: onBringInAmortApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1702',
  direction: 'credit',
  subjectCode: '1702',
  wpCode: 'I1',
  subjectLabel: '累计摊销(1702)',
  rows: bringInAmortRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('amort', rowKey, field, value),
  totalAudited: () => amortSubtotal.value.audited,
})
const {
  adjPull: adjPullImpair,
  visible: bringInImpairVisible,
  rowOptions: bringInImpairRowOptions,
  open: openBringInImpair,
  apply: onBringInImpairApply,
} = useAdjudicationBringIn({
  projectId: computed(() => props.projectId) as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1703',
  direction: 'credit',
  subjectCode: '1703',
  wpCode: 'I1',
  subjectLabel: '减值准备(1703)',
  rows: bringInImpairRows,
  updateCell: (rowKey: string, field: any, value: number) => updateCell('impairment', rowKey, field, value),
  totalAudited: () => impairmentSubtotal.value.audited,
})

const { adjustmentNets } = useI1CrossSheet(toRef(props, 'allResponses'))
const i13Nets = computed(() => adjustmentNets.value)
const canSyncI13 = computed(() => {
  const n = i13Nets.value
  return (
    Math.abs(n.costAje) + Math.abs(n.costRje) + Math.abs(n.amortAje)
    + Math.abs(n.amortRje) + Math.abs(n.impairAje) + Math.abs(n.impairRje)
  ) >= 0.005
})

function _readPeriodAmortTotal(): number {
  const m = props.allResponses
  for (const key of ['I1-11-period-amort-total', 'I1-10-period-amort-total']) {
    const raw = m.get(key)?.remark ?? m.get(key)?.conclusion
    const n = Number(raw)
    if (Number.isFinite(n) && Math.abs(n) >= 0.005) return n
  }
  // 回退：从行合计
  for (const key of ['I1-11-rows', 'I1-10-rows']) {
    const raw = m.get(key)?.remark ?? m.get(key)?.conclusion
    if (!raw) continue
    try {
      const rows = typeof raw === 'string' ? JSON.parse(raw) : raw
      if (!Array.isArray(rows)) continue
      const sum = rows.reduce((s: number, r: any) => s + (Number(r.periodAmortization) || 0), 0)
      if (Math.abs(sum) >= 0.005) return sum
    } catch { /* continue */ }
  }
  return 0
}

const amortProvisionCross = computed(() => {
  const provision = amortSubtotal.value.increase
  const periodTotal = _readPeriodAmortTotal()
  const diff = Math.round((periodTotal - provision) * 100) / 100
  const matched =
    provision === 0
      ? Math.abs(periodTotal) < 0.01
      : Math.abs(diff) <= 0.01
  return { provision, periodTotal, diff, matched }
})

const allocCross = computed(() => {
  const raw = props.allResponses.get('I1-9-alloc-totals')?.remark
    ?? props.allResponses.get('I1-9-alloc-totals')?.conclusion
  let allocSum = 0
  if (raw) {
    try {
      const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
      allocSum = Number(parsed?.allocSum) || 0
    } catch { /* ignore */ }
  }
  const provision = amortSubtotal.value.increase
  const diff = Math.round((allocSum - provision) * 100) / 100
  const matched = allocSum === 0 ? true : Math.abs(diff) <= 0.01
  return { allocSum, provision, diff, matched }
})

function handleFillFromDetail(mode: 'book' | 'full' = 'book') {
  const res = fillFromDetail(mode)
  if (res.ok) ElMessage.success(res.message)
  else ElMessage.warning(res.message)
}

const fileInputRef = ref<HTMLInputElement | null>(null)
const { importing, exporting, exportTemplate, exportData, importData } = useI1ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
})
const ieBusy = computed(() => importing.value || exporting.value)

async function handleIeCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate('I1')
  else if (cmd === 'export-data') await exportData('I1')
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  ;(e.target as HTMLInputElement).value = ''
  if (file) await importData('I1', file)
}

async function handlePublish() {
  publishing.value = true
  try {
    await saveAdjudication()
    ElMessage.success('已保存审定并尝试回写 TB')
  } finally {
    publishing.value = false
  }
}

function handleSyncI13() {
  const res = syncAjeRjeFromI13(i13Nets.value)
  if (res.applied) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function onAdjustmentCreated(payload?: any) {
  if (props.isReadonly) return
  const detail = payload?.detail ?? payload
  if (detail?.wpCode && detail.wpCode !== 'I1') return
  // 保存后自动回写（与 H8 联动一致）；若 Map 尚未刷新则用事件净额
  syncAjeRjeFromI13({
    costAje: detail?.costAjeNet ?? i13Nets.value.costAje,
    costRje: detail?.costRjeNet ?? i13Nets.value.costRje,
    amortAje: detail?.amortAjeNet ?? i13Nets.value.amortAje,
    amortRje: detail?.amortRjeNet ?? i13Nets.value.amortRje,
    impairAje: detail?.impairAjeNet ?? i13Nets.value.impairAje,
    impairRje: detail?.impairRjeNet ?? i13Nets.value.impairRje,
  })
}

function _onWindowAdjustment(e: Event) {
  onAdjustmentCreated((e as CustomEvent).detail)
}

onMounted(() => {
  eventBus.on('adjustment:created', onAdjustmentCreated)
  window.addEventListener('adjustment:created', _onWindowAdjustment)
})
onBeforeUnmount(() => {
  eventBus.off('adjustment:created', onAdjustmentCreated)
  window.removeEventListener('adjustment:created', _onWindowAdjustment)
})

// ─── View Mode ───────────────────────────────────────────────────────────────

const viewMode = ref('结构化视图')
const columnLayout = ref<'movement' | 'excel6'>('movement')

function toExcel6Row(row: I1AdjudicationRow) {
  const endAdj = (Number(row.aje) || 0) + (Number(row.rje) || 0)
  return {
    category: row.category,
    beginUnadj: row.beginBalance,
    beginAdj: 0,
    beginAudited: row.beginBalance,
    endUnadj: row.unadjusted,
    endAdj,
    endAudited: row.audited,
    isSubtotal: row.isSubtotal,
  }
}

const excel6Blocks = computed(() => [
  {
    key: 'cost',
    title: '一、无形资产-原值（Excel 六列对照）',
    rows: costDisplayRows.value.map(toExcel6Row),
  },
  {
    key: 'amort',
    title: '二、累计摊销（Excel 六列对照）',
    rows: amortDisplayRows.value.map(toExcel6Row),
  },
  {
    key: 'impair',
    title: '三、减值准备（Excel 六列对照）',
    rows: impairmentDisplayRows.value.map(toExcel6Row),
  },
])

// ─── Display Rows (detail + subtotal) ────────────────────────────────────────

const costDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = costRows.value.filter((r) => !r.isSubtotal)
  return [...detail, costSubtotal.value]
})

const amortDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = amortRows.value.filter((r) => !r.isSubtotal)
  return [...detail, amortSubtotal.value]
})

const impairmentDisplayRows = computed<I1AdjudicationRow[]>(() => {
  const detail = impairmentRows.value.filter((r) => !r.isSubtotal)
  return [...detail, impairmentSubtotal.value]
})

// ─── Cross Validation Warning ────────────────────────────────────────────────

const hasCrossWarning = computed(() => {
  const cv = crossValidation.value
  return cv.hasCostWarning || cv.hasAmortWarning || cv.hasImpairWarning
})

const crossWarningCount = computed(() => {
  const cv = crossValidation.value
  let count = 0
  if (cv.hasCostWarning) count++
  if (cv.hasAmortWarning) count++
  if (cv.hasImpairWarning) count++
  return count
})

// ─── Reconciliation Helpers ──────────────────────────────────────────────────

function isRowBalanced(rowId: string): boolean {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  return result ? result.isBalanced : true
}

function getReconciliationTooltip(rowId: string): string {
  const result = reconciliationResults.value.find((r) => r.rowId === rowId)
  if (!result || result.isBalanced) return ''
  return `三角勾稽差额: ${fmtAmount(result.difference)}（期末 ≠ 期初 + 增加 - 减少）`
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I1AdjudicationRow }): string {
  const classes: string[] = []
  if (row.isSubtotal) classes.push('subtotal-row')
  if (!isRowBalanced(row.rowId)) classes.push('reconciliation-error-row')
  return classes.join(' ')
}

function netRowClass({ row }: { row: I1NetValueRow }): string {
  if (row.isSubtotal) return 'subtotal-row'
  if (row.isSignificant) return 'sig-change-row'
  return ''
}

function onConclusionTemplate(kind: string): void {
  if (kind === 'A' || kind === 'B' || kind === 'C') {
    applyConclusionTemplate(kind)
    ElMessage.success(`已套用结论模板 ${kind}`)
  }
}

function fillFluctuationDraft(): void {
  qualitativeNotes.value.fluctuation = draftFluctuationNote()
  saveQualitativeNotes()
  ElMessage.success('已填入重大变动草稿')
}

function fillIndefiniteDraft(): void {
  qualitativeNotes.value.indefiniteLife = draftIndefiniteLifeNote()
  saveQualitativeNotes()
  ElMessage.success('已从 I1-7 填入说明事项(2)')
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(block: I1BlockType, rowId: string, field: keyof I1AdjudicationRow, value: number | null): void {
  updateCell(block, rowId, field, value ?? 0)
  saveAdjudication()
}

// ─── Note / Conclusion ───────────────────────────────────────────────────────

function onNoteBlur(): void {
  saveNote(auditNote.value)
}

function onConclusionBlur(): void {
  saveConclusion(auditConclusion.value)
}

// ─── Review ──────────────────────────────────────────────────────────────────

function handleReview(section: string): void {
  // 由主入口 provide 的 openReviewDialog 处理
  console.log('[I1-Adjudication] Review:', section)
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Amount Formatter ────────────────────────────────────────────────────────

function fmtAmount(value: number | null | undefined): string {
  if (value == null) return '-'
  if (Math.abs(value) < 0.005) return '-'
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(rate: number | null | undefined): string {
  if (rate == null || !Number.isFinite(rate)) return '-'
  return `${rate.toFixed(2)}%`
}
</script>

<style scoped>
.i1-adjudication {
  font-size: var(--wp-font-size, 13px);
  padding: 16px;
}

/* 双模式切换 */
.mode-switcher {
  margin-bottom: 16px;
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  align-items: center;
}
.excel6-view { margin-bottom: 16px; }
.excel6-alert { margin-bottom: 12px; }

/* 方法论上下文 */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 审计目标 alert */
.objective-alert { margin-bottom: 12px; }

/* 编制提示 details */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 6px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 交叉验证警告 */
.cross-validation-warning {
  margin-bottom: 16px;
  padding: 8px 12px;
  background: #fefce8;
  border: 1px solid #fde047;
  border-radius: 6px;
}
.cross-badge {
  display: inline-flex;
  align-items: center;
}

/* 区块通用 */
.block-section {
  margin-bottom: 20px;
  border-radius: 8px;
  overflow: hidden;
}
.block-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 16px;
  font-weight: 600;
  font-size: 14px;
}
.block-actions {
  display: flex;
  align-items: center;
  gap: 4px;
}
.block-title {
  font-size: 14px;
}

/* 区块颜色 */
.block-cost .block-header {
  background: #dcfce7;
  color: #166534;
}
.block-cost {
  border: 1px solid #bbf7d0;
}

.block-amort .block-header {
  background: #dbeafe;
  color: #1e3a5f;
}
.block-amort {
  border: 1px solid #bfdbfe;
}

.block-impairment .block-header {
  background: #ede9fe;
  color: #4c1d95;
}
.block-impairment {
  border: 1px solid #ddd6fe;
}

/* 表格 */
.adjudication-table {
  font-size: var(--wp-font-size, 13px);
}
.adjudication-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.adjudication-table :deep(.wp-amount-input) {
  width: 100%;
}
.adjudication-table :deep(.wp-amount-input .el-input__inner) {
  text-align: right;
  font-size: var(--wp-font-size, 13px);
}

/* 小计行 */
.subtotal-text {
  font-weight: 700;
}
:deep(.subtotal-row) {
  background-color: #f1f5f9 !important;
}
:deep(.subtotal-row td) {
  font-weight: 700;
}

/* 公式列 */
.formula-col-header {
  border-bottom: 1px dashed #94a3b8;
  cursor: help;
  padding-bottom: 2px;
}
.formula-value {
  border-bottom: 1px dashed #94a3b8;
  cursor: help;
  padding-bottom: 1px;
}

/* 三角勾稽校验失败 */
.reconciliation-error {
  color: #dc2626;
  font-weight: 600;
}
:deep(.reconciliation-error-row) {
  background-color: #fef2f2 !important;
}
:deep(.reconciliation-error-row td) {
  color: #991b1b;
}

/* 净值行 */
.net-value-section {
  margin-bottom: 20px;
}
.net-value-table {
  border: 2px solid #1e293b;
}
.net-value-text {
  font-weight: 700;
  font-size: 14px;
  color: #0f172a;
}

/* TB取数/差异 */
.tb-section {
  margin-bottom: 20px;
}
.tb-section .block-header {
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-bottom: none;
  border-radius: 6px 6px 0 0;
}
.tb-table {
  border: 1px solid #e2e8f0;
}
.difference-warning {
  color: #dc2626;
  font-weight: 600;
}

/* 审计说明/结论卡片 */
.audit-note-card {
  margin-bottom: 16px;
}
.audit-note-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #f8fafc;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-weight: 600;
  font-size: 14px;
}
.audit-note-card :deep(.el-textarea__inner) {
  font-size: var(--wp-font-size, 13px);
}

/* 跨底稿联动栏 */
.cross-ref-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  margin-bottom: 16px;
  background: var(--el-fill-color-lighter);
  border-radius: 4px;
  border: 1px dashed var(--el-border-color);
  font-size: 12px;
}
.cross-ref-label {
  color: var(--el-text-color-secondary);
  font-weight: 500;
}

.sig-change {
  color: var(--el-color-warning-dark-2);
  font-weight: 700;
}
:deep(.sig-change-row) td {
  background: #fffbeb !important;
}
.net-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.qual-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.qual-item label {
  display: block;
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
  color: var(--el-text-color-regular);
}
.nav-chip { cursor: pointer; }
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
