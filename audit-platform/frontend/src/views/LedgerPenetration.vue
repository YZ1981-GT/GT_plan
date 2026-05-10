<template>
  <div class="gt-penetration">
    <!-- 账套信息栏 -->
    <div class="gt-ledger-header">
      <div class="gt-ledger-title">
        <span class="gt-ledger-company">{{ currentProject?.client_name || currentProject?.name || '—' }}</span>
        <el-tag size="small" type="info" style="margin-left: 8px">{{ currentProject?.name || '' }}</el-tag>
      </div>
      <div class="gt-ledger-switches">
        <el-select
          v-model="selectedProjectId"
          size="small"
          style="width: 200px"
          placeholder="切换单位"
          @change="onProjectChange"
        >
          <el-option
            v-for="p in projectList"
            :key="p.id"
            :label="`${p.client_name || p.name}`"
            :value="p.id"
          />
        </el-select>
        <el-select
          v-model="selectedYear"
          size="small"
          style="width: 100px"
          placeholder="年度"
          @change="onYearChange"
        >
          <el-option v-for="y in yearOptions" :key="y" :value="y">
            <span>{{ y }}年</span>
            <el-tag v-if="availableYears.includes(y)" size="small" type="success" style="margin-left: 6px; transform: scale(0.85)">有数据</el-tag>
          </el-option>
        </el-select>
        <el-button size="small" @click="goToImport">
          <el-icon style="margin-right: 2px"><Upload /></el-icon> 导入数据
        </el-button>
        <el-button size="small" plain @click="goToImportHistory">导入历史</el-button>
        <el-button size="small" plain @click="dataManagerVisible = true">
          <el-icon style="margin-right: 2px"><Setting /></el-icon> 数据管理
        </el-button>
        <el-button size="small" @click="runValidation" :loading="validating" type="warning" plain>
          <el-icon style="margin-right: 2px"><Warning /></el-icon> 数据校验
        </el-button>
      </div>
    </div>

    <!-- 面包屑导航 -->
    <div class="gt-breadcrumb">
      <span
        v-for="(crumb, i) in breadcrumbs"
        :key="i"
        class="gt-crumb"
        :class="{ 'gt-crumb--active': i === breadcrumbs.length - 1 }"
        @click="navigateTo(i)"
      >
        {{ crumb.label }}
        <span v-if="i < breadcrumbs.length - 1" class="gt-crumb-sep">/</span>
      </span>
    </div>

    <!-- ═══ 第一层：账簿查询 / 辅助余额表 ═══ -->
    <template v-if="currentLevel === 'balance'">
      <!-- Tab 切换 -->
      <div class="gt-balance-tabs">
        <span
          class="gt-balance-tab"
          :class="{ 'gt-balance-tab--active': balanceTab === 'account' }"
          @click="balanceTab = 'account'"
        >科目余额表</span>
        <span
          class="gt-balance-tab"
          :class="{ 'gt-balance-tab--active': balanceTab === 'aux' }"
          @click="switchToAuxTab"
        >辅助余额表</span>
      </div>

      <!-- 账簿查询筛选栏 -->
      <div v-if="balanceTab === 'account'" class="gt-filter-row">
        <el-input
          v-model="searchKeyword"
          placeholder="搜索科目编号或名称..."
          size="small"
          clearable
          :prefix-icon="Search"
          style="width: 200px"
        />
        <el-select v-model="balanceFilter" size="small" style="width: 180px" placeholder="数据筛选">
          <el-option label="全部科目" value="all" />
          <el-option label="期末有数" value="closing" />
          <el-option label="期初有数" value="opening" />
          <el-option label="期初+期末都有数" value="both" />
          <el-option label="全部有数（期初+变动+期末）" value="all_nonzero" />
          <el-option label="本期有变动" value="changed" />
          <el-option label="借方有发生额" value="debit" />
          <el-option label="贷方有发生额" value="credit" />
          <el-option label="仅一级科目" value="level1" />
        </el-select>
        <el-button size="small" :type="treeMode ? 'primary' : ''" @click="treeMode = !treeMode">
          {{ treeMode ? '扁平视图' : '树形视图' }}
        </el-button>
        <el-button v-if="treeMode" size="small" @click="toggleExpandAll">
          {{ allExpanded ? '全部收起' : '全部展开' }}
        </el-button>
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">账簿查询</el-tag>
        <el-tag size="small">{{ filteredFlatCount }} / {{ balanceData.length }}</el-tag>
        <el-button size="small" @click="refresh" :loading="loading">刷新</el-button>
        <el-button size="small" type="success" plain @click="exportBalanceExcel">导出Excel</el-button>
      </div>

      <!-- 空状态 -->
      <div v-if="balanceTab === 'account' && !loading && balanceData.length === 0" class="gt-empty-state">
        <p style="font-size: 15px; color: #999">暂无科目余额数据</p>
        <p style="font-size: 13px; color: #bbb">请点击右上角「导入数据」上传包含余额表的 Excel/CSV 文件</p>
      </div>

      <!-- 余额表 -->
      <el-table
        v-if="balanceTab === 'account' && balanceData.length > 0"
        ref="balanceTableRef"
        :data="treeMode ? treeBalance : filteredBalance"
        :row-key="treeMode ? 'account_code' : undefined"
        :tree-props="treeMode ? { children: 'children' } : undefined"
        :default-expand-all="false"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToLedger"
        :row-style="balanceRowStyle"
        :indent="24"
      >
        <el-table-column prop="account_code" label="科目编号" width="200" sortable>
          <template #default="{ row }">
            <span class="gt-link" @click.stop="drillToLedger(row)">{{ row.account_code }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="account_name" label="科目名称" min-width="180" show-overflow-tooltip />
        <el-table-column prop="opening_balance" label="期初余额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方发生额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方发生额" width="150" align="right" sortable>
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末余额" width="150" align="right" sortable>
          <template #default="{ row }">
            <span class="gt-link" @click.stop="drillToLedger(row)">{{ fmtAmt(row.closing_balance) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <!-- ═══ 辅助余额表视图 ═══ -->
      <div v-if="balanceTab === 'aux'">
        <!-- 控制区域（可折叠） -->
        <div class="gt-aux-toolbar">
          <div class="gt-aux-toolbar-header">
            <el-tag size="small">{{ auxDisplayCount }} / {{ auxTotalRecords }}</el-tag>
            <el-button size="small" :type="auxTreeMode ? 'primary' : ''" @click="toggleAuxTreeMode">
              {{ auxTreeMode ? '扁平视图' : '树形视图' }}
            </el-button>
            <el-button size="small" :type="auxSummaryOnly ? 'warning' : ''" @click="onToggleSummaryOnly">
              {{ auxSummaryOnly ? '显示明细' : '仅小计' }}
            </el-button>
            <el-button v-if="auxTreeMode" size="small" @click="toggleAuxExpandAll">
              {{ auxAllExpanded ? '全部收起' : '全部展开' }}
            </el-button>
            <div class="gt-filter-spacer" />
            <el-button size="small" @click="loadAllAuxBalance" :loading="loading">刷新</el-button>
            <el-button size="small" type="success" plain @click="exportAuxBalanceExcel">导出Excel</el-button>
            <el-button size="small" text @click="auxToolbarCollapsed = !auxToolbarCollapsed" style="padding: 4px 6px; min-width: auto">
              {{ auxToolbarCollapsed ? '展开筛选 ▼' : '收起筛选 ▲' }}
            </el-button>
          </div>

          <div v-show="!auxToolbarCollapsed">
            <div class="gt-filter-row" style="margin-top: 6px">
              <el-input
                v-model="auxSearchKeyword"
                placeholder="搜索科目、辅助名称或编码..."
                size="small"
                clearable
                :prefix-icon="Search"
                style="width: 220px"
                @input="onAuxSearchInput"
                @clear="onAuxSearchInput"
              />
              <el-select v-model="auxFilter" size="small" style="width: 140px" @change="onAuxFilterChange">
                <el-option label="全部" value="all" />
                <el-option label="期末有数" value="closing" />
                <el-option label="期初有数" value="opening" />
                <el-option label="本期有变动" value="changed" />
              </el-select>
            </div>

            <!-- 维度类型标签 -->
            <div v-if="auxDimTypes.length > 0" class="gt-dim-tabs">
              <span
                v-for="dt in auxDimTypes" :key="dt.type"
                class="gt-dim-tab"
                :class="{ 'gt-dim-tab--active': auxSelectedDimType === dt.type }"
                @click="onAuxDimTypeChange(dt.type)"
              >
                {{ dt.type }}
                <el-tag size="small" type="info" style="margin-left: 4px; transform: scale(0.85)">{{ dt.count.toLocaleString() }}</el-tag>
              </span>
            </div>
          </div>
        </div>

        <!-- 空状态 -->
        <div v-if="!loading && auxSummaryData.length === 0 && auxPagedRows.length === 0" class="gt-empty-state">
          <p style="font-size: 15px; color: #999">暂无辅助余额数据</p>
          <p style="font-size: 13px; color: #bbb">请点击右上角「导入数据」重新上传包含辅助账的 Excel/CSV 文件</p>
        </div>

        <el-table
          v-else
          ref="auxBalanceTableRef"
          :key="_auxTableKey"
          :data="auxTreeMode ? treeAuxBalance : auxFlatDisplayRows"
          :row-key="auxTreeMode ? '_tree_key' : undefined"
          :tree-props="auxTreeMode ? { children: 'children', hasChildren: '_hasChildren' } : undefined"
          :lazy="auxTreeMode && !auxAllExpanded"
          :load="auxTreeMode && !auxAllExpanded ? loadAuxTreeChildren : undefined"
          :default-expand-all="auxAllExpanded"
          border
          size="small"
          :max-height="tableHeight"
          style="width: 100%"
          highlight-current-row
          @row-dblclick="drillToAuxLedgerFromBalance"
          :row-style="auxRowStyle"
        >
          <el-table-column prop="account_code" label="科目编号" width="130" sortable />
          <el-table-column prop="account_name" label="科目名称" width="150" show-overflow-tooltip />
          <el-table-column v-if="!auxTreeMode" prop="aux_type" label="辅助类型" width="90" />
          <el-table-column prop="aux_code" label="辅助编码" width="100" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="auxSummaryOnly && row._isSubtotal" class="gt-link" @click.stop="toggleAuxExpand(row)">
                {{ auxExpandedKeys.has(`${row.account_code}|${row.aux_code}`) ? '−' : '+' }} {{ row.aux_code }}
              </span>
              <span v-else>{{ row.aux_code }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="aux_name" label="辅助名称" min-width="160" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="!row._isGroup" class="gt-link" @click.stop="drillToAuxLedgerFromBalance(row)">{{ row.aux_name }}</span>
              <span v-else style="font-weight: 600; color: #4b2d77">{{ row.aux_name }}</span>
            </template>
          </el-table-column>
          <el-table-column label="关联维度" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <span v-if="!row._isGroup && row.aux_dimensions_raw" style="color: #999">
                {{ formatOtherDims(row.aux_dimensions_raw, row.aux_type || auxSelectedDimType) }}
              </span>
            </template>
          </el-table-column>
          <el-table-column prop="opening_balance" label="期初余额" width="130" align="right" sortable>
            <template #default="{ row }">
              <span :style="{ fontWeight: row._isGroup ? '600' : 'normal' }">{{ fmtAmt(row.opening_balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="debit_amount" label="借方发生额" width="130" align="right" sortable>
            <template #default="{ row }">
              <span :style="{ fontWeight: row._isGroup ? '600' : 'normal' }">{{ fmtAmt(row.debit_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="credit_amount" label="贷方发生额" width="130" align="right" sortable>
            <template #default="{ row }">
              <span :style="{ fontWeight: row._isGroup ? '600' : 'normal' }">{{ fmtAmt(row.credit_amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="closing_balance" label="期末余额" width="130" align="right" sortable>
            <template #default="{ row }">
              <span v-if="!row._isGroup" class="gt-link" @click.stop="drillToAuxLedgerFromBalance(row)">{{ fmtAmt(row.closing_balance) }}</span>
              <span v-else style="font-weight: 600">{{ fmtAmt(row.closing_balance) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <div class="gt-pagination" v-if="!auxTreeMode && auxFlatTotal > auxPageSize">
          <el-pagination
            v-model:current-page="auxPage"
            :page-size="auxPageSize"
            :total="auxFlatTotal"
            layout="prev, pager, next, total"
            size="small"
            @current-change="loadAuxBalancePage"
          />
        </div>
      </div>
    </template>

    <!-- ═══ 第二层：序时账明细 ═══ -->
    <template v-if="currentLevel === 'ledger'">
      <div class="gt-filter-row">
        <el-date-picker
          v-model="dateRange"
          type="daterange"
          size="small"
          start-placeholder="开始日期"
          end-placeholder="结束日期"
          value-format="YYYY-MM-DD"
          style="width: 260px"
          @change="loadLedger"
        />
        <el-button size="small" @click="drillToAuxBalance">辅助余额</el-button>
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} 序时账</el-tag>
        <el-button size="small" @click="loadLedger" :loading="loading">刷新</el-button>
        <el-button size="small" type="success" plain @click="exportLedgerExcel">导出Excel</el-button>
      </div>
      <el-table
        :data="ledgerDisplay"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToVoucher"
        :row-class-name="ledgerRowClass"
      >
        <el-table-column prop="voucher_date" label="日期" width="100" />
        <el-table-column prop="voucher_no" label="凭证号" width="90">
          <template #default="{ row }">
            <span v-if="row._type === 'normal'" class="gt-link" @click.stop="drillToVoucher(row)">{{ row.voucher_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="balance" label="余额" width="140" align="right">
          <template #default="{ row }">
            <span :style="{ fontWeight: row._type !== 'normal' ? '600' : 'normal' }">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="counterpart_account" label="对方科目" width="120" show-overflow-tooltip />
      </el-table>
      <div class="gt-pagination" v-if="ledgerHasMore || ledgerTotal > ledgerPageSize">
        <el-button v-if="ledgerHasMore" @click="loadMoreLedger" :loading="ledgerLoadingMore" size="small" type="primary" plain>
          加载更多
        </el-button>
        <el-tag size="small" type="info" style="margin-left: 8px">已加载 {{ ledgerItems.length }} / {{ ledgerTotal }} 条</el-tag>
      </div>
    </template>

    <!-- ═══ 第三层：凭证分录 ═══ -->
    <template v-if="currentLevel === 'voucher'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">凭证 {{ currentVoucher }}</el-tag>
      </div>
      <el-table :data="voucherItems" border stripe size="small" :max-height="tableHeight" style="width: 100%">
        <el-table-column prop="account_code" label="科目编号" width="120" />
        <el-table-column prop="account_name" label="科目名称" min-width="200" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="140" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="summary" label="摘要" min-width="200" show-overflow-tooltip />
      </el-table>
    </template>

    <!-- ═══ 辅助余额 ═══ -->
    <template v-if="currentLevel === 'aux_balance'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} 辅助余额</el-tag>
      </div>
      <el-table :data="auxBalanceItems" border stripe size="small" :max-height="tableHeight" style="width: 100%" @row-dblclick="drillToAuxLedger">
        <el-table-column prop="aux_type" label="辅助类型" width="100" />
        <el-table-column prop="aux_code" label="编号" width="120" />
        <el-table-column prop="aux_name" label="名称" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="gt-link">{{ row.aux_name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="opening_balance" label="期初" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.opening_balance) }}</template>
        </el-table-column>
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="closing_balance" label="期末" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.closing_balance) }}</template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ═══ 辅助明细 ═══ -->
    <template v-if="currentLevel === 'aux_ledger'">
      <div class="gt-filter-row">
        <div class="gt-filter-spacer" />
        <el-tag type="info" size="small">{{ currentAccount }} / {{ currentAuxCode }} 辅助明细</el-tag>
        <el-button size="small" @click="loadAuxLedger" :loading="loading">刷新</el-button>
      </div>
      <el-table
        :data="auxLedgerDisplay"
        border
        size="small"
        :max-height="tableHeight"
        style="width: 100%"
        highlight-current-row
        @row-dblclick="drillToVoucher"
        :row-class-name="ledgerRowClass"
      >
        <el-table-column prop="voucher_date" label="日期" width="100" />
        <el-table-column prop="voucher_no" label="凭证号" width="90">
          <template #default="{ row }">
            <span v-if="row._type === 'normal'" class="gt-link" @click.stop="drillToVoucher(row)">{{ row.voucher_no }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="aux_name" label="辅助名称" width="150" show-overflow-tooltip />
        <el-table-column prop="summary" label="摘要" min-width="180" show-overflow-tooltip />
        <el-table-column prop="debit_amount" label="借方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.debit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="credit_amount" label="贷方" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.credit_amount) }}</template>
        </el-table-column>
        <el-table-column prop="balance" label="余额" width="140" align="right">
          <template #default="{ row }">
            <span :style="{ fontWeight: row._type !== 'normal' ? '600' : 'normal' }">{{ fmtAmt(row.balance) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <div class="gt-pagination" v-if="auxLedgerTotal > 100">
        <el-pagination
          v-model:current-page="auxLedgerPage"
          :page-size="100"
          :total="auxLedgerTotal"
          layout="prev, pager, next, total"
          size="small"
          @current-change="loadAuxLedger"
        />
      </div>
    </template>

  </div>

  <!-- ── 智能导入弹窗 ── -->
  <el-dialog
    v-model="importDialogVisible"
    title="账套导入"
    width="720px"
    append-to-body
    destroy-on-close
    :close-on-click-modal="!previewing"
    :close-on-press-escape="!previewing"
    :show-close="!previewing"
    :before-close="onDialogBeforeClose"
  >
    <!-- 进度条放在 dialog 顶部（header 下方，不被 v-loading 遮罩覆盖） -->
    <template #header>
      <span style="font-size: 16px; font-weight: 600">账套导入</span>
      <el-progress
        v-if="previewing || importing"
        :percentage="Math.round(importProgressPct)"
        :stroke-width="8"
        :show-text="true"
        :format="(pct: number) => pct < 100 ? `${pct}%` : '完成'"
        :status="importProgressPct >= 100 ? 'success' : ''"
        color="#4b2d77"
        style="margin-top: 8px"
      />
    </template>
    <div v-loading="previewing || importing"
         :element-loading-text="previewing ? '正在解析文件，请稍候...' : importing ? '正在导入数据，请稍候...' : ''"
         element-loading-background="rgba(255,255,255,0.85)">
    <!-- 步骤1：上传文件 -->
    <div v-if="importStep === 'upload'">
      <el-upload
        ref="uploadRef"
        drag
        multiple
        :auto-upload="false"
        accept=".xlsx,.csv"
        :on-change="onImportFileChange"
      >
        <el-icon style="font-size: 40px; color: #c0c4cc"><Upload /></el-icon>
        <div style="margin-top: 8px; color: #666">拖拽文件到此处，或点击选择</div>
        <div style="font-size: 12px; color: #999; margin-top: 4px">
          支持多个文件（如余额表 + 多个序时账），自动识别合并
        </div>
      </el-upload>
      <div style="margin-top: 12px">
        <span style="font-size: 13px; color: #666">年度：</span>
        <el-input-number v-model="importYear" :min="2000" :max="2099" size="small" style="width: 120px" />
        <span style="font-size: 12px; color: #999; margin-left: 8px">不填则自动从文件内容提取</span>
      </div>

      <!-- P2-1.3 + P2: 耗时预估 + 关注事项 -->
      <el-alert
        v-if="importFiles.length > 0"
        :type="importIsLargeFile ? 'warning' : 'info'"
        :closable="false"
        show-icon
        style="margin-top: 12px"
      >
        <template #title>
          <b>预计耗时 {{ importEstimateText }}</b>
          <span v-if="importIsLargeFile"> · 建议上传后使用"关闭（后台继续）"</span>
        </template>
        <div style="font-size: 12px; line-height: 1.8; margin-top: 4px">
          <div>• 总大小 <b>{{ formatFileSize(importTotalBytes) }}</b>，共 {{ importFiles.length }} 个文件</div>
          <div>• 耗时 = 上传 + 识别 + 入库（按网速 20Mbps 估算，实际可能有波动）</div>
          <div>• 损益类科目期末结转后 opening/closing 为空属正常；辅助维度按单一类型聚合应等于主表</div>
          <div v-if="importIsLargeFile">• 大文件（&gt;50MB）识别阶段较慢，前端若无响应 3-5 秒属正常</div>
          <div>• 请确保：同一项目年度无进行中的导入作业，否则 submit 会被阻塞</div>
        </div>
      </el-alert>

      <!-- FAQ 折叠面板 -->
      <el-collapse style="margin-top: 12px">
        <el-collapse-item title="常见问题" name="faq">
          <div style="font-size: 12px; line-height: 1.8; color: #606266">
            <p><b>Q：为什么损益类科目 opening_balance 为空？</b><br/>
            A：会计准则规定损益类期末结转到本年利润，opening/closing 天然为 NULL，只有 debit/credit 有值。余额树形"有金额"过滤器已按此差异化处理。</p>
            <p><b>Q：辅助维度为什么同一笔金额出现在多行？</b><br/>
            A：一行多维度（如客户+项目+成本中心）在 tb_aux_balance 冗余存 N 条，每条记原行金额。按单一 aux_type 分组求和应 = 主表（这是正确的立体坐标存储）。</p>
            <p><b>Q：点"关闭（后台继续）"后如何看进度？</b><br/>
            A：顶栏"导入中"进度环会持续更新，鼠标悬停看阶段 + 剩余耗时；点击该图标跳回此 dialog。</p>
            <p><b>Q：导入失败怎么办？</b><br/>
            A：错误提示会区分"数据关联错误 / 字段格式错误 / 必填为空"等类型。点"导入历史"查看详细 diagnostics。</p>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>

    <!-- 步骤2：预览确认 -->
    <div v-if="importStep === 'preview'" style="max-height: 500px; overflow-y: auto">
      <el-alert
        v-if="previewResult?.preview_mode"
        title="预览模式说明"
        type="info"
        :closable="false"
        style="margin-bottom: 12px"
        :description="`仅解析前 ${previewResult?.preview_rows || 50} 行用于确认列映射，实际数据量以后台导入结果为准。`"
        show-icon
      />

      <!-- P0-U1: 列映射完成率警告 -->
      <el-alert
        v-if="mappingCoverage.hasLow"
        :type="mappingCoverage.isWarning ? 'warning' : 'info'"
        :closable="false"
        style="margin-bottom: 12px"
        show-icon
      >
        <template #title>
          <b>列映射完成率：{{ mappingCoverage.mapped }}/{{ mappingCoverage.total }} ({{ mappingCoverage.rate }}%)</b>
          <span v-if="mappingCoverage.isWarning"> · 建议检查下方未识别列</span>
        </template>
        <div style="font-size: 12px; line-height: 1.8; margin-top: 4px">
          <div v-for="(info, idx) in mappingCoverage.sheets" :key="idx">
            • {{ info.sheet }} ({{ info.data_type }}): {{ info.mapped }}/{{ info.total }} ({{ info.rate }}%)
            <span v-if="info.unmapped.length > 0" style="color: #909399">
              未识别 {{ info.unmapped.length }} 列：{{ info.unmapped.slice(0, 5).join('、') }}{{ info.unmapped.length > 5 ? '…' : '' }}
            </span>
          </div>
          <div style="color: #909399; margin-top: 4px">
            未识别列将不被写入四表，如有需要请在下方"列映射调整"中手动设置。
          </div>
        </div>
      </el-alert>

      <el-descriptions :column="2" size="small" border style="margin-bottom: 12px">
        <el-descriptions-item label="识别年度">{{ previewResult?.year }}</el-descriptions-item>
        <el-descriptions-item label="余额表">{{ previewResult?.summary?.balance || 0 }} 行</el-descriptions-item>
        <el-descriptions-item label="辅助余额表">{{ previewResult?.summary?.aux_balance || 0 }} 行</el-descriptions-item>
        <el-descriptions-item label="序时账">{{ previewResult?.summary?.ledger || 0 }} 行</el-descriptions-item>
        <el-descriptions-item label="辅助明细账">{{ previewResult?.summary?.aux_ledger || 0 }} 行</el-descriptions-item>
      </el-descriptions>

      <!-- 文件诊断 -->
      <div style="margin-bottom: 8px">
        <div style="font-weight: 600; margin-bottom: 6px; font-size: 14px">文件解析诊断</div>
        <div v-for="(d, i) in previewResult?.diagnostics" :key="i"
             style="font-size: 12px; padding: 3px 0; color: #666">
          <el-tag :type="d.status === 'ok' ? 'success' : d.status === 'error' ? 'danger' : 'info'" size="small" style="margin-right: 4px">
            {{ d.data_type || '?' }}
          </el-tag>
          {{ d.file }} / {{ d.sheet }} — {{ d.row_count?.toLocaleString() || 0 }} 行
          <span v-if="d.company_code" style="color: #67c23a; margin-left: 4px">{{ d.company_code }}</span>
          <span v-if="d.year" style="color: #67c23a; margin-left: 2px">{{ d.year }}年</span>
          <span v-if="d.balance_count_est != null" style="color: #409eff">（估算余额 {{ d.balance_count_est.toLocaleString() }}）</span>
          <span v-if="d.ledger_count_est != null" style="color: #409eff">（估算序时账 {{ d.ledger_count_est.toLocaleString() }}）</span>
          <span v-if="d.balance_count != null" style="color: #409eff">（余额{{ d.balance_count }}, 辅助{{ d.aux_balance_count }}）</span>
          <span v-if="d.ledger_count != null" style="color: #409eff">（序时账{{ d.ledger_count?.toLocaleString() }}, 辅助{{ d.aux_ledger_count?.toLocaleString() }}）</span>
          <el-tag v-if="d.wide_table_detected" size="small" type="warning" style="margin-left: 4px">宽表格式</el-tag>
        </div>
      </div>

      <!-- 列映射手动调整 -->
      <div v-for="(d, i) in previewResult?.diagnostics" :key="`map-${i}`" style="margin-bottom: 12px">
        <div style="font-weight: 600; margin-bottom: 6px; font-size: 14px">
          列映射调整 — {{ d.file }}
          <el-tag v-if="d.wide_table_detected" size="small" type="warning" style="margin-left: 4px">检测到宽表格式（前数据后列名）</el-tag>
        </div>
        <el-table :data="d.headers || []" size="small" border style="width: 100%" max-height="300">
          <el-table-column type="index" width="50" />
          <el-table-column label="原始列名" prop="header" width="200">
            <template #default="{ row }">
              <span :style="{ color: (d.column_mapping || {})[row] ? '#333' : '#999' }">{{ row }}</span>
            </template>
          </el-table-column>
          <el-table-column label="识别方式" width="100">
            <template #default="{ row }">
              <el-tag v-if="(d.content_inferred || {})[row]" size="small" type="warning">内容推断</el-tag>
              <el-tag v-else-if="(d.column_mapping || {})[row]" size="small" type="success">表头匹配</el-tag>
              <el-tag v-else size="small" type="info">未识别</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="映射到标准字段" min-width="200">
            <template #default="{ row }">
              <el-select
                v-model="userColumnMapping[`${d.file}/${d.sheet}`][row]"
                size="small"
                clearable
                placeholder="选择标准字段（不映射则留空）"
                style="width: 100%"
              >
                <el-option
                  v-for="opt in STANDARD_FIELDS"
                  :key="opt.value"
                  :label="opt.label"
                  :value="opt.value"
                />
              </el-select>
            </template>
          </el-table-column>
        </el-table>
      </div>
    </div>

    <!-- 步骤3：导入中 -->
    <div v-if="importStep === 'importing'" style="text-align: center; padding: 40px 0">
      <el-icon class="is-loading" style="font-size: 32px; color: #409eff"><Loading /></el-icon>
      <div style="margin-top: 12px; color: #666">
        正在后台写入数据库，可关闭弹窗继续操作…<br>
        <span style="font-size: 12px; color: #999">{{ bgImportMessage }}</span>
      </div>
    </div>

    <!-- 步骤4：完成 -->
    <div v-if="importStep === 'done'" style="text-align: center; padding: 30px 0">
      <ImportCompletionSummary
        title="导入完成"
        :summary-entries="importedResultSummaryEntries"
        :validation-summary="importValidationSummary"
        :grouped-validation-items="groupedImportValidationItems"
        :validation-title="importValidationSummaryTitle"
        :validation-alert-type="importValidationSummaryAlertType"
        :show-success-icon="true"
        container-style="text-align: center; padding: 30px 0"
        validation-panel-style="margin-top: 16px; text-align: left"
      />

      <!-- P3-U3: 导入成功后的下一步引导卡片 -->
      <div class="gt-completion-guide">
        <div class="guide-title">下一步操作建议</div>
        <div class="guide-cards">
          <div class="guide-card" @click="onGuideViewTree">
            <div class="guide-card-icon">📊</div>
            <div class="guide-card-title">查看余额树形</div>
            <div class="guide-card-desc">按维度核对科目余额是否符合原表</div>
          </div>
          <div class="guide-card" @click="onGuideValidate">
            <div class="guide-card-icon">✓</div>
            <div class="guide-card-title">运行数据一致性校验</div>
            <div class="guide-card-desc">检查四表之间的借贷平衡与辅助关系</div>
          </div>
          <div class="guide-card" @click="onGuideHistory">
            <div class="guide-card-icon">📜</div>
            <div class="guide-card-title">查看导入历史</div>
            <div class="guide-card-desc">查看完整的 diagnostics 和处理记录</div>
          </div>
        </div>
      </div>
    </div>

    </div><!-- v-loading wrapper -->

    <template #footer>
      <el-button v-if="importStep === 'upload'" @click="importDialogVisible = false">取消</el-button>
      <el-button v-if="importStep === 'upload'" type="primary" :disabled="importFiles.length === 0" :loading="previewing" @click="doPreview">
        解析预览
      </el-button>
      <el-button v-if="importStep === 'preview'" @click="importStep = 'upload'">返回修改</el-button>
      <el-button v-if="importStep === 'preview'" type="primary" :loading="importing" @click="doImport">
        确认导入
      </el-button>
      <el-button v-if="importStep === 'importing'" @click="onMoveToBackground">关闭（后台继续）</el-button>
      <el-button v-if="importStep === 'done'" type="primary" @click="onImportDone">完成</el-button>
    </template>
  </el-dialog>

  <!-- 数据校验弹窗 -->
  <el-dialog v-model="validateDialogVisible" title="数据一致性校验" width="700px" append-to-body>
    <div v-loading="validating" element-loading-text="正在校验...">
      <div v-if="validateResult">
        <el-descriptions :column="3" border size="small" style="margin-bottom: 12px">
          <el-descriptions-item label="余额表科目">{{ validateResult.summary?.balance_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="辅助核算科目">{{ validateResult.summary?.aux_account_count || 0 }}</el-descriptions-item>
          <el-descriptions-item label="序时账科目">{{ validateResult.summary?.ledger_account_count || 0 }}</el-descriptions-item>
        </el-descriptions>

        <div v-for="(f, idx) in validateResult.findings" :key="idx"
          style="margin-bottom: 6px; font-size: 13px; display: flex; align-items: flex-start; gap: 6px">
          <el-tag :type="f.level === 'error' ? 'danger' : f.level === 'warning' ? 'warning' : 'success'" size="small" style="flex-shrink: 0">
            {{ f.category }}
          </el-tag>
          <span :style="{ color: f.level === 'error' ? '#f56c6c' : f.level === 'warning' ? '#e6a23c' : '#67c23a' }">
            {{ f.message }}
          </span>
        </div>

        <div v-if="!validateResult.findings?.length" style="color: #999; text-align: center; padding: 20px">
          暂无校验结果
        </div>
      </div>
    </div>
    <template #footer>
      <el-button @click="validateDialogVisible = false">关闭</el-button>
    </template>
  </el-dialog>

  <!-- ── 账表数据管理弹窗 ── -->
  <LedgerDataManager
    v-if="projectId"
    v-model="dataManagerVisible"
    :project-id="projectId"
    @data-changed="onDataChanged"
    @request-incremental-upload="onIncrementalUpload"
  />
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, onBeforeUnmount, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Search, Upload, Loading, Warning, Setting } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox, ElNotification } from 'element-plus'
import { api } from '@/services/apiProxy'
import { ledger as P_ledger, projects as P_proj, materiality as P_mat } from '@/services/apiPaths'
import { fmtAmount } from '@/utils/formatters'
import ImportCompletionSummary from '@/components/ImportCompletionSummary.vue'
import LedgerDataManager from '@/components/ledger-import/LedgerDataManager.vue'
import { buildImportFormData } from '@/utils/importFormData'
import { applyImportPreviewSuccess, buildImportPreviewFormData, buildImportPreviewUrl, resolveImportPreviewSuccess } from '@/utils/importPreview'
import { buildImportJobUrl, fetchImportQueueStatus } from '@/utils/importJobRequest'
import { applyImportSuccess, resolveImportSuccess } from '@/utils/importSuccess'
import { resolveImportCompletionToast, resolveImportFailureMessage, shouldFinishImportPolling, hasImportFailed } from '@/utils/useImportJobFlow'
import { runImportPollingFlow } from '@/utils/useImportPollingFlow'
import { useImportValidation } from '@/utils/useImportValidation'
import { getActiveLedgerDataset, getImportJob, smartPreviewLedgerImport, submitSmartLedgerImport } from '@/services/ledgerImportApi'

const route = useRoute()
const router = useRouter()
const projectId = computed(() => route.params.projectId as string)
const year = computed(() => {
  const q = Number(route.query.year)
  if (q && q > 2000) return q
  return new Date().getFullYear() - 1
})

// ── 账套/年度切换 ──
interface ProjectInfo { id: string; name: string; client_name?: string; wizard_state?: any }
const projectList = ref<ProjectInfo[]>([])
const currentProject = ref<ProjectInfo | null>(null)
const selectedProjectId = ref('')
const selectedYear = ref(2025)

const yearOptions = computed(() => {
  const cur = new Date().getFullYear()
  const defaultYears = Array.from({ length: 5 }, (_, i) => cur - i)
  // 合并实际有数据的年度
  const all = new Set([...defaultYears, ...availableYears.value])
  return [...all].sort((a, b) => b - a)
})

const availableYears = ref<number[]>([])

async function loadAvailableYears() {
  if (!projectId.value) return
  try {
    const data = await api.get(P_ledger.years(projectId.value))
    const result = data
    availableYears.value = result?.years ?? []
  } catch {
    availableYears.value = []
  }
}

async function loadProjectList() {
  try {
    const data = await api.get(P_proj.list)
    const list = data ?? []
    projectList.value = Array.isArray(list) ? list : []
  } catch {
    projectList.value = []
  }
}

async function loadCurrentProject() {
  if (!projectId.value) return
  try {
    const data = await api.get(P_proj.wizard(projectId.value))
    const ws = data
    const basicInfo = ws?.steps?.basic_info?.data || {}
    currentProject.value = {
      id: projectId.value,
      name: basicInfo.client_name ? `${basicInfo.client_name}_${basicInfo.audit_year || ''}` : projectId.value,
      client_name: basicInfo.client_name || '',
    }
    selectedYear.value = basicInfo.audit_year || year.value
  } catch {
    // 回退：从项目列表中找
    const found = projectList.value.find(p => p.id === projectId.value)
    if (found) currentProject.value = found
  }
  selectedProjectId.value = projectId.value
  // 需求 25.1~25.3：加载执行重要性水平和审计期末用于序时账视觉标记
  loadProjectMaterialityAndPeriod()
}

// ── 序时账视觉标记所需数据（需求 25.1~25.3） ──
const performanceMateriality = ref<number>(0)
const auditPeriodEnd = ref<string>('')  // "YYYY-MM-DD"

async function loadProjectMaterialityAndPeriod() {
  if (!projectId.value) return
  try {
    // 获取项目基本信息（含 audit_period_end）
    const proj = await api.get(P_proj.detail(projectId.value))
    if (proj?.audit_period_end) {
      auditPeriodEnd.value = proj.audit_period_end
    }
  } catch { /* ignore */ }
  try {
    // 获取重要性水平（含 performance_materiality）
    const mat = await api.get(
      `${P_mat.get(projectId.value)}?year=${selectedYear.value}`
    )
    if (mat?.performance_materiality) {
      performanceMateriality.value = Number(mat.performance_materiality) || 0
    }
  } catch { /* ignore */ }
}

function onProjectChange(newId: string) {
  if (newId && newId !== projectId.value) {
    router.push({ path: `/projects/${newId}/ledger`, query: { year: String(selectedYear.value) } })
  }
}

function onYearChange(newYear: number) {
  selectedYear.value = newYear
  router.push({ path: `/projects/${projectId.value}/ledger`, query: { year: String(newYear) } })
}

function goToImport() {
  openImportDialog()
}

function goToImportHistory() {
  router.push({
    path: `/projects/${projectId.value}/ledger/import-history`,
    query: { year: String(selectedYear.value) },
  })
}

// ── 智能导入 ──
const importDialogVisible = ref(false)

// P2-1.3: 耗时预估 computed
const importTotalBytes = computed(() =>
  importFiles.value.reduce((sum, f) => sum + (f.size || 0), 0)
)
const importTotalMB = computed(() => importTotalBytes.value / (1024 * 1024))
const importIsLargeFile = computed(() => importTotalMB.value > 50)
const importEstimateSeconds = computed(() => {
  const mb = importTotalMB.value
  const uploadSec = Math.round(mb / 2.5)  // 20Mbps = 2.5 MB/s
  let processSec: number
  if (mb < 1) processSec = 10
  else if (mb < 5) processSec = Math.round(mb * 11)
  else if (mb < 20) processSec = Math.round(mb * 12)
  else if (mb < 100) processSec = Math.round(mb * 14)
  else processSec = Math.round(mb * 16)
  return uploadSec + processSec
})
const importEstimateText = computed(() => {
  const s = importEstimateSeconds.value
  if (s < 60) return `约 ${s} 秒`
  if (s < 600) return `约 ${Math.round(s / 60)} 分钟`
  return `约 ${Math.round(s / 60)} 分钟（强烈建议后台继续）`
})

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

// P0-U1: 列映射完成率汇总（preview 后用于警告低质量映射）
interface SheetMappingInfo {
  sheet: string
  data_type: string
  mapped: number
  total: number
  rate: number
  unmapped: string[]
}
const mappingCoverage = computed(() => {
  const sheets: SheetMappingInfo[] = []
  let totalMapped = 0
  let totalHeaders = 0
  for (const d of (previewResult.value?.diagnostics || [])) {
    const headers: string[] = d.headers || d.raw_headers || []
    const mapping = d.column_mapping || {}
    const mapped = Object.keys(mapping).length
    const total = headers.length
    const unmapped = headers.filter((h: string) => !mapping[h])
    sheets.push({
      sheet: `${d.file || ''} / ${d.sheet || ''}`,
      data_type: d.data_type || '未知',
      mapped,
      total,
      rate: total > 0 ? Math.round(mapped * 100 / total) : 0,
      unmapped,
    })
    totalMapped += mapped
    totalHeaders += total
  }
  const rate = totalHeaders > 0 ? Math.round(totalMapped * 100 / totalHeaders) : 0
  // 任一 sheet 低于 70% 或整体低于 70% → 触发警告
  const hasLow = sheets.some((s) => s.rate < 70) || rate < 70
  return {
    sheets,
    mapped: totalMapped,
    total: totalHeaders,
    rate,
    hasLow,
    isWarning: hasLow,
  }
})

// ── 数据校验 ──
const validateDialogVisible = ref(false)
const validating = ref(false)
const validateResult = ref<any>(null)

async function runValidation() {
  validating.value = true
  validateDialogVisible.value = true
  validateResult.value = null
  try {
    const data = await api.get(
      `${P_ledger.validate(projectId.value)}?year=${selectedYear.value}`
    )
    validateResult.value = data
  } catch {
    ElMessage.error('校验失败')
  } finally {
    validating.value = false
  }
}
const importStep = ref<'upload' | 'preview' | 'importing' | 'done'>('upload')

// 账表数据管理弹窗
const dataManagerVisible = ref(false)

function onDataChanged() {
  // 数据被删除/追加后刷新页面数据
  loadBalance()
  loadAuxBalance()
}

function onIncrementalUpload(year: number) {
  // 用户在数据管理弹窗选了增量追加
  dataManagerVisible.value = false
  importDialogVisible.value = true
  importStep.value = 'upload'
  importFiles.value = []
  importYear.value = year
  ElNotification({
    title: '增量追加模式',
    message: `请上传 ${year} 年的序时账文件，系统将自动检测并只追加新月份`,
    type: 'info',
    duration: 5000,
  })
}
const importFiles = ref<File[]>([])
const importYear = ref<number | undefined>(undefined)
const previewResult = ref<any>(null)
interface ImportValidationItem {
  file?: string | null
  sheet?: string | null
  rule_code: string
  severity: 'fatal' | 'error' | 'warning' | 'info' | string
  message: string
  blocking?: boolean
}

interface ImportValidationSummary {
  total: number
  blocking_count: number
  has_blocking?: boolean
  by_severity: Record<string, number>
}

interface LedgerImportResultPayload {
  imported?: Record<string, number>
  year?: number | null
  diagnostics?: Array<Record<string, unknown>>
  validation?: ImportValidationItem[]
  validation_summary?: ImportValidationSummary
  errors?: string[]
  batch_id?: string | null
}

const importedResult = ref<LedgerImportResultPayload | null>(null)
const uploadToken = ref('')
const previewing = ref(false)
const importing = ref(false)
const importProgressPct = ref(0)
const uploadRef = ref()

const DATA_TYPE_LABELS: Record<string, string> = {
  tb_balance: '余额表',
  tb_ledger: '序时账',
  tb_aux_balance: '辅助余额',
  tb_aux_ledger: '辅助明细',
}

const importedResultSummaryEntries = computed(() => {
  const imported = importedResult.value?.imported || {}
  return Object.entries(imported).map(([key, value]) => ({
    key,
    label: DATA_TYPE_LABELS[key] || key,
    value: `${typeof value === 'number' ? value.toLocaleString() : value} 条`,
  }))
})

const {
  validationSummary: importValidationSummary,
  groupedValidationItems: groupedImportValidationItems,
  validationSummaryAlertType: importValidationSummaryAlertType,
  validationSummaryTitle: importValidationSummaryTitle,
} = useImportValidation<ImportValidationItem, ImportValidationSummary>(
  () => importedResult.value?.validation,
  () => importedResult.value?.validation_summary,
)

// ── 列映射手动调整 ──
const userColumnMapping = ref<Record<string, Record<string, string>>>({})
// key: "filename/sheet", value: {原始列名: 标准字段名}

const STANDARD_FIELDS = [
  { value: '', label: '（不映射）' },
  { value: 'account_code', label: '科目编码' },
  { value: 'account_name', label: '科目名称' },
  { value: 'voucher_date', label: '凭证日期' },
  { value: 'voucher_no', label: '凭证号' },
  { value: 'debit_amount', label: '借方金额' },
  { value: 'credit_amount', label: '贷方金额' },
  { value: 'opening_balance', label: '期初余额' },
  { value: 'closing_balance', label: '期末余额' },
  { value: 'aux_dimensions', label: '核算维度（混合）' },
  { value: 'aux_type', label: '辅助类型' },
  { value: 'aux_code', label: '辅助编码' },
  { value: 'aux_name', label: '辅助名称' },
  { value: 'summary', label: '摘要' },
  { value: 'direction', label: '借贷方向' },
  { value: 'preparer', label: '制单人' },
  { value: 'accounting_period', label: '会计期间' },
  { value: 'counterpart_account', label: '对方科目' },
]

function initColumnMapping() {
  userColumnMapping.value = {}
  if (!previewResult.value?.diagnostics) return
  for (const d of previewResult.value.diagnostics) {
    const key = `${d.file}/${d.sheet}`
    const mapping: Record<string, string> = {}
    if (d.column_mapping) {
      for (const [col, field] of Object.entries(d.column_mapping)) {
        if (field) mapping[col] = field as string
      }
    }
    userColumnMapping.value[key] = mapping
  }
}

// ── 后台导入轮询状态 ──
const bgImportPolling = ref(false)
const bgImportMessage = ref('')

// ── 导入状态后台轮询（需求 22.1、22.2） ──
let _importStatusTimer: ReturnType<typeof setInterval> | null = null
let _importStatusPollCount = 0
const MAX_IMPORT_POLL_COUNT = 200  // 200 × 3s = 10 分钟

function startImportStatusPolling(jobId: string) {
  stopImportStatusPolling()
  _importStatusPollCount = 0
  _importStatusTimer = setInterval(async () => {
    _importStatusPollCount++
    if (_importStatusPollCount > MAX_IMPORT_POLL_COUNT) {
      stopImportStatusPolling()
      ElNotification({
        title: '导入超时',
        message: '导入任务超过 10 分钟未完成，请稍后在导入历史中查看结果',
        type: 'warning',
        duration: 6000,
      })
      return
    }
    try {
      // 实际后端路由：GET /api/projects/{project_id}/ledger-import/jobs/{job_id}
      const status = await getImportJob(projectId.value, jobId)
      const jobStatus = status?.status
      if (jobStatus === 'completed') {
        stopImportStatusPolling()
        ElNotification({
          title: '导入完成',
          message: status?.message || status?.progress_message || '账套数据已成功导入',
          type: 'success',
          duration: 5000,
        })
        // 需求 22.2：自动刷新余额表
        _auxBalanceLoadedKey.value = ''
        loadAvailableYears()
        loadBalance()
        if (balanceTab.value === 'aux') {
          loadAllAuxBalance()
        }
      } else if (jobStatus === 'failed' || jobStatus === 'timed_out' || jobStatus === 'canceled') {
        stopImportStatusPolling()
        ElNotification({
          title: '导入失败',
          message: status?.message || status?.error_message || '账套数据导入失败，请检查文件格式',
          type: 'error',
          duration: 8000,
        })
      }
    } catch {
      // 网络错误时继续轮询，不中断
    }
  }, 3000)
}

function stopImportStatusPolling() {
  if (_importStatusTimer !== null) {
    clearInterval(_importStatusTimer)
    _importStatusTimer = null
  }
  _importStatusPollCount = 0
}

function openImportDialog(options: { autoRecoverActiveJob?: boolean } = {}) {
  importDialogVisible.value = true
  importStep.value = 'upload'
  importFiles.value = []
  importYear.value = selectedYear.value || year.value
  previewResult.value = null
  importedResult.value = null
  uploadToken.value = ''
  importing.value = false
  previewing.value = false
  bgImportPolling.value = false
  bgImportMessage.value = ''
  uploadRef.value?.clearFiles?.()
  // P1-2.1: 检查活跃 job
  // - 顶栏跳转回来（autoRecoverActiveJob=true）：直接静默跳 importing step
  // - 用户主动开新导入（默认）：弹对话框让用户选择处理方式
  if (options.autoRecoverActiveJob) {
    void recoverActiveImportJobSilent()
  } else {
    void checkActiveJobBeforeUpload()
  }
}

/**
 * 静默恢复进度（顶栏跳转场景）：
 * - 有活跃 job：跳 importing step 显示进度
 * - 最近 5 分钟内 failed：提示错误
 * - 其他：保持 upload step
 */
async function recoverActiveImportJobSilent() {
  if (!projectId.value) return
  try {
    const resp: any = await api.get(
      `/api/projects/${projectId.value}/ledger-import/active-job`,
      { validateStatus: (s: number) => s < 600 },
    )
    if (resp?.status === 'processing' && resp.job_id) {
      importStep.value = 'importing'
      bgImportPolling.value = true
      bgImportMessage.value = `[${resp.progress ?? 0}%] ${resp.message || '后台导入中...'}（从后台恢复）`
      startImportStatusPolling(resp.job_id)
    } else if (resp?.status === 'failed' && resp.job_id) {
      ElMessage.error({
        message: `最近一次导入失败：${resp.message || '未知错误'}`,
        duration: 6000,
      })
    }
    // completed/canceled 不提示（顶栏 pollImportQueue 已经弹过 toast）
  } catch {
    // ignore
  }
}

/**
 * 上传前检测是否已有活跃 job。
 * 修复 P0：弹确认框让用户选，而非强制跳进度视图——
 * - 查看进度：跳 importing step 追踪旧 job
 * - 取消旧作业：先 cancel 再留在 upload step 让用户重新提交
 * - 稍后：仅提示，保持 upload step，用户自行等待
 */
async function checkActiveJobBeforeUpload() {
  if (!projectId.value) return
  try {
    const resp: any = await api.get(
      `/api/projects/${projectId.value}/ledger-import/active-job`,
      { validateStatus: (s: number) => s < 600 },
    )
    if (resp?.status !== 'processing' || !resp.job_id) return

    const pct = resp.progress ?? 0
    const phase = resp.phase || 'writing'
    const activeJobId = resp.job_id

    try {
      const result: any = await ElMessageBox({
        title: '检测到导入作业进行中',
        message: `当前项目已有导入作业进行中（${phase} ${pct}%）。请选择如何处理：`,
        showCancelButton: true,
        showConfirmButton: true,
        distinguishCancelAndClose: true,
        confirmButtonText: '查看进度',
        cancelButtonText: '取消旧作业并新建',
        type: 'warning',
      })
      // Element Plus MessageBoxData 类型是 `{value, action} & Action` 交叉类型，
      // TS 塌陷为 never，需 any 断言；resolve 时 result 可能是 'confirm' 字符串
      // 或 {action:'confirm', value}，兼容处理
      const action = typeof result === 'string' ? result : result?.action
      if (action === 'confirm') {
        // 查看进度
        importStep.value = 'importing'
        bgImportPolling.value = true
        bgImportMessage.value = `[${pct}%] ${resp.message || '后台导入中...'}`
        startImportStatusPolling(activeJobId)
      }
    } catch (err: any) {
      // reject 时 err 通常是 'cancel' | 'close' 字符串（Element Plus 默认行为）
      const action = typeof err === 'string' ? err : err?.action
      if (action === 'cancel') {
        // 用户选"取消旧作业"
        try {
          await api.post(
            `/api/projects/${projectId.value}/ledger-import/jobs/${activeJobId}/cancel`,
          )
          ElMessage.success('旧作业已取消，可开始新导入')
        } catch (e: any) {
          ElMessage.error(e?.message || '取消旧作业失败')
        }
      }
      // action === 'close'：稍后 → 什么都不做
    }
  } catch {
    // 网络异常不影响 dialog 正常打开
  }
}

function openImportDialogFromRoute() {
  // 顶栏跳回时静默恢复进度，不弹"请选择"对话框打扰用户
  openImportDialog({ autoRecoverActiveJob: true })
  const nextQuery = { ...route.query }
  delete nextQuery.import
  router.replace({ path: route.path, query: nextQuery })
}

function onImportFileChange(file: any) {
  if (file?.raw) {
    uploadToken.value = ''
    importFiles.value.push(file.raw)
  }
}

async function doPreview() {
  if (!importFiles.value.length) return
  previewing.value = true
  importProgressPct.value = 0
  const progressTimer = setInterval(() => {
    if (importProgressPct.value < 90) {
      importProgressPct.value += Math.random() * 12 + 3
      if (importProgressPct.value > 90) importProgressPct.value = 90
    }
  }, 400)
  try {
    const formData = buildImportPreviewFormData(importFiles.value)
    const url = buildImportPreviewUrl({
      basePath: P_ledger.smartPreview(projectId.value),
      year: importYear.value,
      previewRows: 50,
    })
    const data = await smartPreviewLedgerImport(projectId.value, url, formData)
    importProgressPct.value = 100
    const previewSuccess = resolveImportPreviewSuccess({
      result: data,
      nextStage: 'preview' as const,
      getUploadToken: result => result?.upload_token,
      getYear: result => result?.year,
    })
    await applyImportPreviewSuccess({
      previewSuccess,
      applyUploadToken: (value) => { uploadToken.value = value },
      applyPayload: (payload) => { previewResult.value = payload },
      enterStage: (stage) => { importStep.value = stage },
      afterEnterStage: async ({ payload, nextStage, uploadToken: landedUploadToken, year: landedYear }) => {
        void payload
        void nextStage
        void landedUploadToken
        void landedYear
        initColumnMapping()
      },
    })
  } catch (e: any) {
    if (!e?.response) {
      ElMessage.error(e?.message || '解析失败')
    }
  } finally {
    clearInterval(progressTimer)
    importProgressPct.value = 0
    previewing.value = false
  }
}

async function doImport() {
  if ((!importFiles.value.length && !uploadToken.value) || !projectId.value) return
  importing.value = true
  importStep.value = 'importing'
  bgImportPolling.value = true

  try {
    const yr = previewResult.value?.year || importYear.value
    const mappingParam = Object.keys(userColumnMapping.value).length > 0
      ? JSON.stringify(userColumnMapping.value)
      : ''
    const formData = buildImportFormData({
      files: importFiles.value,
      uploadToken: uploadToken.value,
      mappingFieldName: 'custom_mapping',
      mappingPayload: mappingParam,
    })
    const url = buildImportJobUrl({
      basePath: P_ledger.smartImport(projectId.value),
      year: yr,
      uploadToken: uploadToken.value,
    })
    const data = await submitSmartLedgerImport(projectId.value, url, formData)
    uploadToken.value = data?.upload_token || uploadToken.value
    const importJobId = data?.job_id || null
    if (!importJobId) {
      throw new Error('导入任务提交成功但未返回 job_id，请刷新后在导入历史查看任务状态')
    }

    // 需求 22.1：启动后台状态轮询（用户关闭弹窗后继续通知）
    startImportStatusPolling(importJobId)

    await runImportPollingFlow({
      maxPolls: 400,
      timeoutMessage: '导入任务仍在后台运行，请稍后刷新页面查看结果',
      onWait: () => new Promise<void>(resolve => setTimeout(resolve, 3000)),
      fetchStatus: () => fetchImportQueueStatus(() => getImportJob(projectId.value, importJobId)),
      onStatus: (status) => {
        if (status && typeof status === 'object') {
          const pct = status.progress ?? 0
          const msg = status.message || ''
          bgImportMessage.value = `[${pct}%] ${msg}`
        }
      },
      shouldFinish: (status) => shouldFinishImportPolling(status),
      hasFailed: (status) => hasImportFailed(status),
      getFailureMessage: (status) => status?.message || '导入失败',
      onSuccessStatus: (status) => {
        const payload = status?.result
        const resolvedImportedResult = (payload?.imported && !payload?.validation)
          ? { imported: payload.imported }
          : payload
        const importSuccess = resolveImportSuccess({
          result: resolvedImportedResult,
          nextStage: 'done' as const,
        })
        const completionToast = resolveImportCompletionToast(
          status?.message || null,
          resolvedImportedResult?.validation_summary as any,
        )
        if (completionToast.type === 'warning') {
          ElMessage.warning(completionToast.message)
        } else {
          ElMessage.success(completionToast.message)
        }
        return applyImportSuccess({
          success: importSuccess,
          applyResult: (result: any) => { importedResult.value = result },
          enterStage: (stage) => { importStep.value = stage },
          afterEnterStage: async () => {
            // 导入已在前台完成，停止后台轮询避免重复通知
            stopImportStatusPolling()
            _auxBalanceLoadedKey.value = ''
            await getActiveLedgerDataset(projectId.value, yr)
            loadAvailableYears()
            loadBalance()
            if (balanceTab.value === 'aux') {
              loadAllAuxBalance()
            }
          },
        })
      },
    })
  } catch (e: any) {
    const errValidation = e?.response?.data?.validation as ImportValidationItem[] | undefined
    const errMsg = resolveImportFailureMessage(
      errValidation,
      e?.response?.data?.detail || e?.message || '导入失败',
    )
    ElMessage.error(errMsg)
    stopImportStatusPolling()
    importStep.value = 'preview'
    // P1-U4: 失败后主动询问下一步（不强推，关闭即视为"留在预览"自行决定）
    _showFailureActionPrompt(errMsg)
  } finally {
    importing.value = false
    bgImportPolling.value = false
  }
}

/** flag：避免 before-close 钩子和 onMoveToBackground 重复弹 toast */
const _closingAsBackground = ref(false)
/** 组件销毁时清理未触发的弹框计时器 */
let _completionPromptTimer: number | null = null

/**
 * P1-U4: 失败后提示用户下一步操作。
 * 不阻断用户在 preview 继续手动调映射后"确认导入"重试，也提供"导入历史"入口查看完整 diagnostics。
 */
function _showFailureActionPrompt(errMsg: string) {
  ElMessageBox({
    title: '导入失败',
    message: `${errMsg.slice(0, 300)}\n\n可选操作：\n• 返回预览调整列映射后重新导入\n• 查看导入历史查看完整诊断`,
    showCancelButton: true,
    showConfirmButton: true,
    distinguishCancelAndClose: true,
    confirmButtonText: '返回预览重试',
    cancelButtonText: '查看导入历史',
    type: 'error',
  }).catch((err: any) => {
    const action = typeof err === 'string' ? err : err?.action
    if (action === 'cancel') {
      goToImportHistory()
    }
    // close: 什么都不做
  })
}

function onMoveToBackground() {
  // worker 后端继续跑，关闭 dialog；顶栏进度环持续追踪
  // 设 flag 避免 before-close 钩子重复弹 toast
  _closingAsBackground.value = true
  importDialogVisible.value = false
  ElMessage.success({
    message: '已转入后台，顶栏"导入中"进度环可追踪进度',
    duration: 4000,
  })
}

// P3-U3: 导入成功引导卡片的 3 个入口
function onGuideViewTree() {
  importDialogVisible.value = false
  _auxBalanceLoadedKey.value = ''
  loadAvailableYears()
  loadBalance()
  dataManagerVisible.value = true  // 打开余额树形 Tab
}
function onGuideValidate() {
  importDialogVisible.value = false
  validateDialogVisible.value = true
  runValidation()
}
function onGuideHistory() {
  importDialogVisible.value = false
  goToImportHistory()
}

/**
 * dialog 关闭前钩子：importing 态下关闭视同"放后台继续"，弹 toast 引导。
 * 若由 onMoveToBackground 主动触发则跳过 toast（那边已经弹过）。
 */
function onDialogBeforeClose(done: () => void) {
  if (_closingAsBackground.value) {
    _closingAsBackground.value = false
    done()
    return
  }
  if (importStep.value === 'importing' && !importing.value) {
    // × / Esc 关闭 importing dialog → 视同放后台
    ElMessage.success({
      message: '已转入后台，顶栏"导入中"进度环可追踪进度',
      duration: 4000,
    })
  }
  done()
}

function onImportDone() {
  importDialogVisible.value = false
  // 清除缓存，强制重新加载
  _auxBalanceLoadedKey.value = ''
  loadAvailableYears()
  loadBalance()
  // 如果当前在辅助余额表 Tab，也刷新
  if (balanceTab.value === 'aux') {
    loadAllAuxBalance()
  }
  // P2-5.2: 询问是否立即查看树形视图验证数据
  // 延迟 350ms（元素 dialog 关闭动画 ~300ms）再弹确认框，避免两层 dialog 叠加
  _completionPromptTimer = window.setTimeout(() => {
    _completionPromptTimer = null
    if (!importDialogVisible.value && projectId.value) {
      ElMessageBox.confirm(
        '账套导入完成。是否立即打开"账表数据管理 · 余额树形"验证数据正确性？',
        '导入完成',
        {
          confirmButtonText: '打开树形视图',
          cancelButtonText: '稍后',
          type: 'success',
        },
      ).then(() => {
        dataManagerVisible.value = true
      }).catch(() => {
        // 用户选稍后，什么都不做
      })
    }
  }, 350)
}

// 路由变化时重新加载（不在初始化时触发，由 onMounted 处理）
let _initialized = false
watch([projectId, year], () => {
  if (!_initialized) return
  if (projectId.value) {
    _auxBalanceLoadedKey.value = ''  // 清除辅助余额表缓存
    loadCurrentProject()
    loadAvailableYears()
    currentLevel.value = 'balance'
    breadcrumbs.value = [{ label: '账簿查询', level: 'balance' }]
    loadBalance()
  }
})

watch(() => route.query.import, (val) => {
  if (!_initialized) return
  if (val === '1') {
    openImportDialogFromRoute()
  }
})

const loading = ref(false)
const tableHeight = ref(Math.max(400, window.innerHeight - 240))

// ── 导航状态 ──
type Level = 'balance' | 'ledger' | 'voucher' | 'aux_balance' | 'aux_ledger'
const currentLevel = ref<Level>('balance')
const currentAccount = ref('')
const currentAccountOpening = ref(0)  // 穿透时记录期初余额
const currentAuxOpening = ref(0)  // 辅助明细穿透时记录期初余额
const currentVoucher = ref('')
const currentAuxType = ref('')
const currentAuxCode = ref('')
const searchKeyword = ref('')
const balanceFilter = ref('all')
const treeMode = ref(false)
const balanceTab = ref<'account' | 'aux'>('account')
const auxSearchKeyword = ref('')
const auxFilter = ref('all')
const auxPage = ref(1)
const auxPageSize = 100
const dateRange = ref<string[] | null>(null)

interface Crumb { label: string; level: Level; account?: string; voucher?: string; auxType?: string; auxCode?: string }
const breadcrumbs = ref<Crumb[]>([{ label: '账簿查询', level: 'balance' }])

// ── 数据 ──
const balanceData = ref<any[]>([])
const ledgerItems = ref<any[]>([])
const ledgerTotal = ref(0)
const ledgerPage = ref(1)
const ledgerPageSize = 200

// ── 游标分页状态 ──
const ledgerCursor = ref<string | null>(null)
const ledgerHasMore = ref(false)
const ledgerLoadingMore = ref(false)

/** 序时账增强显示：期初行 + 每笔余额 + 月小计行 */
const ledgerDisplay = computed(() => {
  const items = ledgerItems.value
  if (items.length === 0) return []

  const rows: any[] = []
  let balance = currentAccountOpening.value
  let monthDebit = 0
  let monthCredit = 0
  let lastMonth = ''

  // 期初余额行
  rows.push({
    _type: 'opening',
    voucher_date: '',
    voucher_no: '',
    summary: '期初余额',
    debit_amount: null,
    credit_amount: null,
    balance,
    counterpart_account: '',
    account_code: '',
  })

  for (let i = 0; i < items.length; i++) {
    const item = items[i]
    const d = num(item.debit_amount)
    const c = num(item.credit_amount)
    balance += d - c
    monthDebit += d
    monthCredit += c

    const month = (item.voucher_date || '').substring(0, 7) // "2025-01"
    if (!lastMonth) lastMonth = month

    // 月份变化时插入上月小计
    if (month !== lastMonth && lastMonth) {
      rows.push({
        _type: 'subtotal',
        voucher_date: '',
        voucher_no: '',
        summary: `${lastMonth} 本月合计`,
        debit_amount: monthDebit,
        credit_amount: monthCredit,
        balance,
        counterpart_account: '',
        account_code: '',
      })
      monthDebit = d
      monthCredit = c
      lastMonth = month
    }

    rows.push({ ...item, _type: 'normal', balance })
  }

  // 最后一个月的小计
  if (items.length > 0) {
    rows.push({
      _type: 'subtotal',
      voucher_date: '',
      voucher_no: '',
      summary: `${lastMonth} 本月合计`,
      debit_amount: monthDebit,
      credit_amount: monthCredit,
      balance,
      counterpart_account: '',
      account_code: '',
    })
  }

  return rows
})
const voucherItems = ref<any[]>([])
const auxBalanceItems = ref<any[]>([])
const auxLedgerItems = ref<any[]>([])
const auxLedgerTotal = ref(0)
const auxLedgerPage = ref(1)

/** 辅助明细账增强显示：期初行 + 每笔余额 + 月小计行 */
const auxLedgerDisplay = computed(() => {
  const items = auxLedgerItems.value
  if (items.length === 0) return []

  const rows: any[] = []
  let balance = currentAuxOpening.value
  let monthDebit = 0
  let monthCredit = 0
  let lastMonth = ''

  rows.push({
    _type: 'opening', voucher_date: '', voucher_no: '', aux_name: '',
    summary: '期初余额', debit_amount: null, credit_amount: null,
    balance, account_code: '',
  })

  for (const item of items) {
    const d = num(item.debit_amount)
    const c = num(item.credit_amount)
    balance += d - c
    monthDebit += d
    monthCredit += c

    const month = (item.voucher_date || '').substring(0, 7)
    if (!lastMonth) lastMonth = month

    if (month !== lastMonth && lastMonth) {
      rows.push({
        _type: 'subtotal', voucher_date: '', voucher_no: '', aux_name: '',
        summary: `${lastMonth} 本月合计`, debit_amount: monthDebit,
        credit_amount: monthCredit, balance, account_code: '',
      })
      monthDebit = d
      monthCredit = c
      lastMonth = month
    }

    rows.push({ ...item, _type: 'normal', balance })
  }

  if (items.length > 0) {
    rows.push({
      _type: 'subtotal', voucher_date: '', voucher_no: '', aux_name: '',
      summary: `${lastMonth} 本月合计`, debit_amount: monthDebit,
      credit_amount: monthCredit, balance, account_code: '',
    })
  }

  return rows
})

// ── 余额表筛选 + 树形构建 ──
const balanceTableRef = ref<any>(null)
const allExpanded = ref(false)

function toggleExpandAll() {
  allExpanded.value = !allExpanded.value
  // el-table tree 不支持动态切换 default-expand-all，需要手动操作
  if (balanceTableRef.value) {
    const rows = filteredBalance.value
    for (const row of rows) {
      balanceTableRef.value.toggleRowExpansion(row, allExpanded.value)
    }
  }
}

/** 获取科目级次：优先用后端返回的 level 字段，否则从编码推断 */
function getLevel(row: any): number {
  if (row.level != null && row.level > 0) return row.level
  const code = row.account_code || ''
  if (code.includes('.')) return code.split('.').length
  if (code.length <= 4) return 1
  if (code.length <= 6) return 2
  return 3
}

/** 获取科目的父编码（通用规则）
 * 点号分隔：1002.001 → 1002, 1002.001.01 → 1002.001
 * 纯数字：4位为一级，6位为二级（前4位是父），8位为三级（前6位是父）
 */
function getParentCode(code: string): string | null {
  if (code.includes('.')) {
    const lastDot = code.lastIndexOf('.')
    if (lastDot <= 0) return null
    return code.substring(0, lastDot)
  }
  if (code.length > 6) return code.substring(0, 6)
  if (code.length > 4) return code.substring(0, 4)
  return null
}

const filteredBalance = computed(() => {
  let rows = balanceData.value

  // 关键词搜索时不做树形（直接扁平展示搜索结果）
  if (searchKeyword.value) {
    const kw = searchKeyword.value.toLowerCase()
    rows = rows.filter(r =>
      (r.account_code || '').toLowerCase().includes(kw) ||
      (r.account_name || '').toLowerCase().includes(kw)
    )
  }

  // 数据筛选
  const f = balanceFilter.value
  if (f === 'closing') {
    rows = rows.filter(r => num(r.closing_balance) !== 0)
  } else if (f === 'opening') {
    rows = rows.filter(r => num(r.opening_balance) !== 0)
  } else if (f === 'both') {
    rows = rows.filter(r => num(r.opening_balance) !== 0 && num(r.closing_balance) !== 0)
  } else if (f === 'all_nonzero') {
    rows = rows.filter(r =>
      num(r.opening_balance) !== 0 &&
      (num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0) &&
      num(r.closing_balance) !== 0
    )
  } else if (f === 'changed') {
    rows = rows.filter(r => num(r.debit_amount) !== 0 || num(r.credit_amount) !== 0)
  } else if (f === 'debit') {
    rows = rows.filter(r => num(r.debit_amount) !== 0)
  } else if (f === 'credit') {
    rows = rows.filter(r => num(r.credit_amount) !== 0)
  } else if (f === 'level1') {
    rows = rows.filter(r => getLevel(r) === 1)
  }

  return rows
})

const filteredFlatCount = computed(() => filteredBalance.value.length)

/** 将扁平数据构建为树形结构 */
const treeBalance = computed(() => {
  if (!treeMode.value) return []  // 非树形模式不计算

  const rows = filteredBalance.value
  if (rows.length === 0) return []
  if (balanceFilter.value === 'level1') return rows

  // 简单高效的树构建：只用 account_code 的点号分隔判断父子
  const map = new Map<string, any>()
  const roots: any[] = []

  // 1. 创建所有节点
  for (const row of rows) {
    map.set(row.account_code, { ...row, children: [] })
  }

  // 2. 挂载父子关系
  for (const row of rows) {
    const node = map.get(row.account_code)!
    const pc = getParentCode(row.account_code)
    if (pc && map.has(pc)) {
      map.get(pc)!.children.push(node)
    } else {
      roots.push(node)
    }
  }

  // 3. 清理空 children（不显示展开箭头）
  for (const [, node] of map) {
    if (node.children.length === 0) delete node.children
  }

  return roots.length > 0 ? roots : rows
})

function num(v: any): number { return Number(v) || 0 }

const fmtAmt = fmtAmount

/** 从原始维度字符串中提取当前维度以外的其他维度信息 */
function formatOtherDims(raw: string, currentDimType: string): string {
  if (!raw) return ''
  const parts = raw.split(/[;；]/).map(s => s.trim()).filter(Boolean)
  const others: string[] = []
  for (const part of parts) {
    const colonIdx = part.indexOf(':')
    if (colonIdx < 0) continue
    const dimType = part.substring(0, colonIdx).trim()
    if (dimType === currentDimType) continue
    const value = part.substring(colonIdx + 1).trim()
    // 简化显示：类型:名称（去掉编码）
    const commaIdx = value.indexOf(',')
    const displayName = commaIdx > 0 ? value.substring(commaIdx + 1).trim() : value
    others.push(`${dimType}:${displayName}`)
  }
  return others.join(' | ')
}

function ledgerRowClass({ row }: { row: any }): string {
  if (row._type === 'opening') return 'gt-ledger-opening'
  if (row._type === 'subtotal') return 'gt-ledger-subtotal'
  if (row._type !== 'normal') return ''

  const classes: string[] = []

  // 需求 25.3：借方或贷方金额为负数 → 红色文字（红字冲销）
  const debit = Number(row.debit_amount) || 0
  const credit = Number(row.credit_amount) || 0
  if (debit < 0 || credit < 0) {
    classes.push('gt-ledger-row--red-reversal')
  }

  // 需求 25.1：借方或贷方金额绝对值超过执行重要性水平 → 橙色背景
  if (performanceMateriality.value > 0) {
    if (Math.abs(debit) > performanceMateriality.value || Math.abs(credit) > performanceMateriality.value) {
      classes.push('gt-ledger-row--over-materiality')
    }
  }

  // 需求 25.2：凭证日期在审计期末最后 6 天内 → 截止标记
  if (auditPeriodEnd.value && row.voucher_date) {
    const periodEnd = new Date(auditPeriodEnd.value)
    const voucherDate = new Date(row.voucher_date)
    const sixDaysBefore = new Date(periodEnd)
    sixDaysBefore.setDate(sixDaysBefore.getDate() - 6)
    if (voucherDate >= sixDaysBefore && voucherDate <= periodEnd) {
      classes.push('gt-ledger-row--period-end')
    }
  }

  return classes.join(' ')
}

function balanceRowStyle({ row }: { row: any }) {
  const level = getLevel(row)
  const style: Record<string, string> = {}
  if (level === 1) {
    style.fontWeight = '600'
    style.background = '#f8f5fc'
  }
  // 筛选模式下，补充的祖先节点用浅灰色
  if (row._isAncestor) {
    style.color = '#999'
    style.fontStyle = 'italic'
  }
  return style
}

// ── 加载数据 ──
async function loadBalance() {
  if (!projectId.value) {
    console.warn('[Ledger] projectId is empty, skip loading')
    return
  }
  loading.value = true
  try {
    const data = await api.get(P_ledger.balance(projectId.value), {
      params: { year: year.value },
    })
    balanceData.value = data ?? []
    // debug log removed for production
  } catch (e) {
    console.error('[Ledger] loadBalance failed:', e)
    balanceData.value = []
  }
  finally { loading.value = false }
}

async function loadLedger() {
  loading.value = true
  try {
    const params: any = { year: year.value, limit: ledgerPageSize }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    // 首次加载时从后端获取期初余额（确保 running_balance 准确）
    const [data, obData] = await Promise.all([
      api.get(P_ledger.entries(projectId.value, currentAccount.value), { params }),
      api.get(P_ledger.openingBalance(projectId.value, currentAccount.value), { params: { year: year.value } }),
    ])
    const result = data
    const obResult = obData
    currentAccountOpening.value = num(obResult?.opening_balance)
    ledgerItems.value = result.items ?? result ?? []
    ledgerTotal.value = result.total ?? ledgerItems.value.length
    ledgerCursor.value = result.next_cursor ?? null
    ledgerHasMore.value = result.has_more ?? false
  } catch { ledgerItems.value = []; ledgerHasMore.value = false }
  finally { loading.value = false }
}

async function loadMoreLedger() {
  if (!ledgerHasMore.value || !ledgerCursor.value || ledgerLoadingMore.value) return
  ledgerLoadingMore.value = true
  try {
    const params: any = { year: year.value, limit: ledgerPageSize, cursor: ledgerCursor.value }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const data = await api.get(
      P_ledger.entries(projectId.value, currentAccount.value), { params }
    )
    const result = data
    const newItems = result.items ?? result ?? []
    ledgerItems.value = [...ledgerItems.value, ...newItems]
    ledgerCursor.value = result.next_cursor ?? null
    ledgerHasMore.value = result.has_more ?? false
  } catch { ledgerHasMore.value = false }
  finally { ledgerLoadingMore.value = false }
}

async function loadVoucher() {
  loading.value = true
  try {
    const data = await api.get(
      P_ledger.voucher(projectId.value, currentVoucher.value),
      { params: { year: year.value } }
    )
    voucherItems.value = data ?? []
  } catch { voucherItems.value = [] }
  finally { loading.value = false }
}

async function loadAuxBalance() {
  loading.value = true
  try {
    const data = await api.get(
      P_ledger.auxBalance(projectId.value, currentAccount.value),
      { params: { year: year.value } }
    )
    auxBalanceItems.value = data ?? []
  } catch { auxBalanceItems.value = [] }
  finally { loading.value = false }
}

// ── 辅助余额表（全量，Tab 视图用） ──
const allAuxBalanceData = ref<any[]>([])  // 保留用于降级，但不主动加载
const auxTotalRecords = computed(() =>
  auxDimTypesFromServer.value.reduce((s: number, d: any) => s + (d.total_records || 0), 0)
)
const auxTreeMode = ref(false)
const auxSummaryOnly = ref(false)
const auxExpandedKeys = ref(new Set<string>())
const auxToolbarCollapsed = ref(false)  // 仅小计模式下已展开的 key
const auxAllExpanded = ref(false)
const auxSelectedDimType = ref('')

/** 切换树形/扁平模式 */
function toggleAuxTreeMode() {
  auxTreeMode.value = !auxTreeMode.value
  if (auxTreeMode.value) {
    // 进入树形模式时，自动选中数据量最大的维度类型
    const types = auxDimTypes.value.filter(t => t.type !== '全部')
    if (types.length > 0) {
      auxSelectedDimType.value = types[0].type
      loadAuxSummaryForDim()  // 加载该维度的汇总数据
    }
  } else {
    // 回到扁平模式，重新加载分页数据
    loadAuxBalancePage()
  }
}

/** 维度类型列表（优先用后端预计算，降级用前端计算） */
const auxDimTypes = computed(() => {
  // 后端有汇总数据时直接用
  if (auxDimTypesFromServer.value.length > 0) {
    const types: { type: string; count: number }[] = []
    if (!auxTreeMode.value) {
      const total = auxDimTypesFromServer.value.reduce((s: number, d: any) => s + d.total_records, 0)
      types.push({ type: '全部', count: total })
    }
    for (const d of auxDimTypesFromServer.value) {
      types.push({ type: d.type, count: d.total_records })
    }
    return types
  }

  // 降级：从原始数据计算
  const counts = new Map<string, number>()
  for (const r of allAuxBalanceData.value) {
    const t = r.aux_type || '?'
    counts.set(t, (counts.get(t) || 0) + 1)
  }
  const types: { type: string; count: number }[] = []
  if (!auxTreeMode.value) {
    types.push({ type: '全部', count: allAuxBalanceData.value.length })
  }
  for (const [t, c] of [...counts.entries()].sort((a, b) => b[1] - a[1])) {
    types.push({ type: t, count: c })
  }
  return types
})

/** 当前显示的数据条数 */
const auxDisplayCount = computed(() => {
  if (auxTreeMode.value) {
    // 树形模式用汇总数据的维度记录数
    const dt = auxSelectedDimType.value
    const dim = auxDimTypesFromServer.value.find((d: any) => d.type === dt)
    return dim ? dim.total_records : 0
  }
  return auxPagedTotal.value
})

/** 预计算：按维度类型+科目编号的分组汇总（优先用后端汇总数据） */
const _auxGroupCache = computed(() => {
  const cache = new Map<string, Map<string, { name: string; count: number; opening: number; debit: number; credit: number; closing: number }>>()
  const useSummary = auxSummaryData.value.length > 0
  const source = useSummary ? auxSummaryData.value : allAuxBalanceData.value

  for (const row of source) {
    const dimType = useSummary ? row.dim_type : (row.aux_type || '?')
    if (!cache.has(dimType)) cache.set(dimType, new Map())
    const groups = cache.get(dimType)!
    const code = row.account_code || '?'
    if (!groups.has(code)) {
      groups.set(code, { name: row.account_name || '', count: 0, opening: 0, debit: 0, credit: 0, closing: 0 })
    }
    const g = groups.get(code)!
    g.count += useSummary ? (row.record_count || 1) : 1
    g.opening += num(row.opening_balance)
    g.debit += num(row.debit_amount)
    g.credit += num(row.credit_amount)
    g.closing += num(row.closing_balance)
  }
  return cache
})

/** 辅助余额表树形视图：从预计算缓存取科目汇总行。
 *  全部展开时用汇总数据构建完整二级树（不用 lazy），收起时只返回一级节点（用 lazy）。
 */
const treeAuxBalance = computed(() => {
  if (!auxTreeMode.value) return []
  const dimType = auxSelectedDimType.value
  if (!dimType) return []

  const groups = _auxGroupCache.value.get(dimType)
  if (!groups) return []

  // 全部展开模式：用汇总数据构建完整二级树
  const buildChildren = auxAllExpanded.value
  const summaryByCode = buildChildren ? _buildSummaryByCode(dimType) : null

  const tree: any[] = []
  for (const [code, g] of groups) {
    const node: any = {
      _tree_key: code,
      _isGroup: true,
      _level: 'account',
      _hasChildren: g.count > 0,
      account_code: code,
      account_name: g.name,
      aux_type: '',
      aux_code: '',
      aux_name: `${g.count} 条明细`,
      opening_balance: g.opening,
      debit_amount: g.debit,
      credit_amount: g.credit,
      closing_balance: g.closing,
    }

    if (buildChildren && summaryByCode) {
      const auxItems = summaryByCode.get(code) || []
      node.children = auxItems.map((item: any) => ({
        _tree_key: `${code}_${item.aux_code}_group`,
        _isGroup: item.record_count > 1,
        _level: 'aux',
        _hasChildren: item.record_count > 1,
        _parentCode: code,
        _auxKey: item.aux_code || item.aux_name || '?',
        account_code: code,
        account_name: g.name,
        aux_type: dimType,
        aux_code: item.aux_code,
        aux_name: item.record_count > 1 ? `${item.aux_name} (${item.record_count}条)` : item.aux_name,
        opening_balance: item.opening_balance,
        debit_amount: item.debit_amount,
        credit_amount: item.credit_amount,
        closing_balance: item.closing_balance,
      }))
    }

    tree.push(node)
  }

  return tree
})

/** 从汇总数据按科目分组（全部展开时用） */
function _buildSummaryByCode(dimType: string): Map<string, any[]> {
  const map = new Map<string, any[]>()
  const source = auxSummaryData.value.length > 0 ? auxSummaryData.value : []
  for (const row of source) {
    if ((row.dim_type || row.aux_type) !== dimType) continue
    const code = row.account_code || '?'
    if (!map.has(code)) map.set(code, [])
    map.get(code)!.push(row)
  }
  return map
}

/** 懒加载树形子节点（两级），从后端按需查询 */
function loadAuxTreeChildren(row: any, _treeNode: any, resolve: (data: any[]) => void) {
  const dimType = auxSelectedDimType.value

  if (row._isGroup && row._level === 'account') {
    // 第一级展开科目：从汇总数据中取该科目的辅助编码列表
    const code = row.account_code
    const items = auxSummaryData.value.filter(r => r.dim_type === dimType && r.account_code === code)

    const children: any[] = items.map(item => {
      if (item.record_count <= 1) {
        return { ...item, _tree_key: `${code}_${item.aux_code}_single`, _isGroup: false, aux_type: dimType }
      }
      return {
        _tree_key: `${code}_${item.aux_code}_group`, _isGroup: true, _level: 'aux',
        _hasChildren: true, _parentCode: code, _auxKey: item.aux_code,
        account_code: code, account_name: row.account_name, aux_type: dimType,
        aux_code: item.aux_code, aux_name: `${item.aux_name} (${item.record_count}条)`,
        opening_balance: item.opening_balance, debit_amount: item.debit_amount,
        credit_amount: item.credit_amount, closing_balance: item.closing_balance,
      }
    })
    resolve(children)

  } else if (row._isGroup && row._level === 'aux') {
    // 第二级展开辅助编码：从后端按需查询明细
    const code = row._parentCode
    const auxCode = row._auxKey
    api.get(P_ledger.auxBalanceDetail(projectId.value), {
      params: { year: year.value, account_code: code, dim_type: dimType, aux_code: auxCode }
    }).then((data: any) => {
      const items = (data ?? []).map((item: any, idx: number) => ({
        ...item, _tree_key: `${code}_${auxCode}_${idx}`, _isGroup: false,
      }))
      resolve(items)
    }).catch(() => resolve([]))

  } else {
    resolve([])
  }
}

function toggleAuxExpandAll() {
  auxAllExpanded.value = !auxAllExpanded.value
  // 切换展开/收起时强制重建 table（lazy 模式不支持批量展开）
  _auxTableKey.value++
}

function onAuxDimTypeChange(dimType: string) {
  auxSelectedDimType.value = dimType
  auxExpandedKeys.value = new Set()
  _auxExpandedDetails.value = new Map()
  auxPage.value = 1
  if (auxTreeMode.value || auxSummaryOnly.value) {
    // 树形模式和仅小计模式都需要加载该维度的汇总数据
    loadAuxSummaryForDim().then(() => {
      _auxTableKey.value++  // 强制重建表格确保数据刷新
    })
  } else {
    loadAuxBalancePage()
  }
}

let _auxSearchTimer: any = null
function onAuxSearchInput() {
  clearTimeout(_auxSearchTimer)
  _auxSearchTimer = setTimeout(() => {
    auxPage.value = 1
    if (!auxTreeMode.value && !auxSummaryOnly.value) {
      loadAuxBalancePage()
    }
  }, 400)
}

function onAuxFilterChange() {
  auxPage.value = 1
  if (!auxTreeMode.value && !auxSummaryOnly.value) {
    loadAuxBalancePage()
  }
}

function onToggleSummaryOnly() {
  auxSummaryOnly.value = !auxSummaryOnly.value
  auxPage.value = 1
  auxExpandedKeys.value = new Set()
  _auxExpandedDetails.value = new Map()
  if (auxSummaryOnly.value) {
    // 进入仅小计模式，加载当前维度的汇总数据
    loadAuxSummaryForDim().then(() => {
      _auxTableKey.value++  // 强制重建表格
    })
  } else if (!auxTreeMode.value) {
    loadAuxBalancePage()
  }
}

// 用于强制重建 el-table 的 key
const _auxTableKey = ref(0)

function auxRowStyle({ row }: { row: any }) {
  if (row._isGroup) {
    return { background: '#f8f5fc', fontWeight: '600' }
  }
  if (row._isSubtotal) {
    return { background: '#fef6e6', fontWeight: '600', borderTop: '1px solid #e6a23c' }
  }
  if (row._isDetail) {
    return { background: '#f9f9f9', paddingLeft: '20px' }
  }
  return {}
}

// 仅小计模式下已展开的明细数据缓存
const _auxExpandedDetails = ref(new Map<string, any[]>())

async function toggleAuxExpand(row: any) {
  const key = `${row.account_code}|${row.aux_code}`
  const newSet = new Set(auxExpandedKeys.value)
  if (newSet.has(key)) {
    newSet.delete(key)
  } else {
    // 从后端加载明细
    if (!_auxExpandedDetails.value.has(key)) {
      try {
        const data = await api.get(
          P_ledger.auxBalanceDetail(projectId.value),
          { params: { year: year.value, account_code: row.account_code, dim_type: auxSelectedDimType.value, aux_code: row.aux_code } }
        )
        _auxExpandedDetails.value.set(key, (data ?? []).map((r: any) => ({ ...r, _isDetail: true })))
      } catch { _auxExpandedDetails.value.set(key, []) }
    }
    newSet.add(key)
  }
  auxExpandedKeys.value = newSet
}

const auxFlatTotal = computed(() => {
  if (auxSummaryOnly.value) {
    const dimType = auxSelectedDimType.value
    if (dimType && dimType !== '全部') {
      return auxSummaryData.value.filter(r => r.dim_type === dimType).length
    }
    return auxSummaryData.value.length
  }
  return auxPagedTotal.value
})

/** 扁平视图显示数据 */
const auxFlatDisplayRows = computed(() => {
  if (auxTreeMode.value) return []

  // 仅小计模式：用后端汇总数据分页显示
  if (auxSummaryOnly.value) {
    let rows = auxSummaryData.value
    const dimType = auxSelectedDimType.value
    if (dimType && dimType !== '全部') {
      rows = rows.filter(r => r.dim_type === dimType)
    }
    const start = (auxPage.value - 1) * auxPageSize
    const page = rows.slice(start, start + auxPageSize)

    // 构建显示行（含展开的明细）
    const display: any[] = []
    for (const r of page) {
      const isMulti = (r.record_count || 1) > 1
      const summaryRow = {
        ...r,
        aux_type: r.dim_type || r.aux_type,
        _isSubtotal: isMulti,
        aux_name: isMulti ? `${r.aux_name} (${r.record_count}条)` : r.aux_name,
      }
      display.push(summaryRow)

      // 插入已展开的明细行
      if (isMulti) {
        const key = `${r.account_code}|${r.aux_code}`
        if (auxExpandedKeys.value.has(key)) {
          const details = _auxExpandedDetails.value.get(key) || []
          display.push(...details)
        }
      }
    }
    return display
  }

  // 普通模式：直接用后端分页数据
  return auxPagedRows.value
})

async function loadAllAuxBalance() {
  if (!projectId.value) return
  loading.value = true
  try {
    // 只加载维度类型列表（轻量，不加载全部汇总行）
    const summaryData = await api.get(
      P_ledger.auxBalanceSummary(projectId.value),
      { params: { year: year.value, dim_type: '__types_only__' } }
    )
    const summary = summaryData
    auxDimTypesFromServer.value = summary.dim_types || []

    // 设置默认选中维度
    if (!auxSelectedDimType.value || auxSelectedDimType.value === '') {
      auxSelectedDimType.value = '全部'
    }
    _auxBalanceLoadedKey.value = `${projectId.value}_${year.value}`

    // 加载当前维度的汇总数据（用于树形视图）
    await loadAuxSummaryForDim()
    // 加载扁平视图第一页
    await loadAuxBalancePage()
  } catch (e) {
    console.error('loadAllAuxBalance error:', e)
    auxSummaryData.value = []; auxPagedRows.value = []
  }
  finally { loading.value = false }
}

/** 加载指定维度的汇总数据（树形视图和仅小计模式用） */
async function loadAuxSummaryForDim() {
  const dimType = auxSelectedDimType.value
  if (!dimType || (!auxTreeMode.value && !auxSummaryOnly.value)) {
    return
  }
  const params: any = { year: year.value }
  if (dimType !== '全部') {
    params.dim_type = dimType
  }
  try {
    loading.value = true
    const data = await api.get(
      P_ledger.auxBalanceSummary(projectId.value),
      { params }
    )
    const result = data
    auxSummaryData.value = result.rows || []
    // 同时更新维度类型列表
    if (result.dim_types) {
      auxDimTypesFromServer.value = result.dim_types
    }
  } catch { auxSummaryData.value = [] }
  finally { loading.value = false }
}

// 后端预计算的汇总数据
const auxSummaryData = ref<any[]>([])
const auxDimTypesFromServer = ref<any[]>([])

// 扁平视图后端分页数据
const auxPagedRows = ref<any[]>([])
const auxPagedTotal = ref(0)

async function loadAuxBalancePage() {
  try {
    const params: any = { year: year.value, page: auxPage.value, page_size: auxPageSize }
    if (auxSelectedDimType.value && auxSelectedDimType.value !== '全部') {
      params.dim_type = auxSelectedDimType.value
    }
    if (auxSearchKeyword.value) params.search = auxSearchKeyword.value
    if (auxFilter.value && auxFilter.value !== 'all') params.filter = auxFilter.value

    const data = await api.get(
      P_ledger.auxBalancePaged(projectId.value),
      { params }
    )
    const result = data
    auxPagedRows.value = result.rows || []
    auxPagedTotal.value = result.total || 0
  } catch { auxPagedRows.value = [] }
}

// 缓存标记：project_id + year 组合，避免重复加载
const _auxBalanceLoadedKey = ref('')

function switchToAuxTab() {
  balanceTab.value = 'aux'
  const key = `${projectId.value}_${year.value}`
  if (_auxBalanceLoadedKey.value !== key) {
    loadAllAuxBalance()
  }
}

async function exportAuxBalanceExcel() {
  try {
    const params: any = { year: year.value }
    if (auxSelectedDimType.value && auxSelectedDimType.value !== '全部') {
      params.dim_type = auxSelectedDimType.value
    }
    // 搜索和筛选条件也传给后端（当前视图条件）
    if (auxSearchKeyword.value) params.search = auxSearchKeyword.value
    if (auxFilter.value && auxFilter.value !== 'all') params.filter = auxFilter.value

    const blobResult = await api.get(
      P_ledger.exportAuxBalance(projectId.value),
      { params, responseType: 'blob' }
    )
    // apiProxy 直接返回 data，对 blob 响应即为 Blob 本身
    const blobData = blobResult instanceof Blob ? blobResult : new Blob([blobResult])
    const url = URL.createObjectURL(blobData)
    const a = document.createElement('a')
    a.href = url
    a.download = `辅助余额表_${auxSelectedDimType.value || '全部'}_${year.value}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

/** 导出科目余额表为 Excel */
async function exportBalanceExcel() {
  try {
    const blobResult = await api.get(
      P_ledger.exportBalance(projectId.value),
      { params: { year: year.value }, responseType: 'blob' }
    )
    const blobData = blobResult instanceof Blob ? blobResult : new Blob([blobResult])
    const url = URL.createObjectURL(blobData)
    const a = document.createElement('a')
    a.href = url
    a.download = `科目余额表_${currentProject.value?.client_name || ''}_${year.value}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

/** 导出序时账为 Excel */
async function exportLedgerExcel() {
  try {
    const params: any = { year: year.value }
    if (dateRange.value?.length === 2) {
      params.date_from = dateRange.value[0]
      params.date_to = dateRange.value[1]
    }
    const blobResult = await api.get(
      P_ledger.exportLedger(projectId.value, currentAccount.value),
      { params, responseType: 'blob' }
    )
    const blobData = blobResult instanceof Blob ? blobResult : new Blob([blobResult])
    const url = URL.createObjectURL(blobData)
    const a = document.createElement('a')
    a.href = url
    const acctLabel = currentAccount.value.replace('*', '')
    a.download = `序时账_${acctLabel}_${year.value}.xlsx`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    ElMessage.success('导出成功')
  } catch (e: any) {
    ElMessage.error(e?.message || '导出失败')
  }
}

function drillToAuxLedgerFromBalance(row: any) {
  currentAccount.value = row.account_code
  currentAuxType.value = row.aux_type || ''
  currentAuxCode.value = row.aux_code || ''
  currentAuxOpening.value = num(row.opening_balance)
  currentLevel.value = 'aux_ledger'
  auxLedgerPage.value = 1
  breadcrumbs.value = [
    { label: '账簿查询', level: 'balance' },
    {
      label: `${row.account_code} ${row.aux_name || row.aux_code || ''}`,
      level: 'aux_ledger',
      account: currentAccount.value,
      auxType: currentAuxType.value,
      auxCode: currentAuxCode.value,
    },
  ]
  loadAuxLedger()
}

async function loadAuxLedger() {
  loading.value = true
  try {
    const data = await api.get(
      P_ledger.auxEntries(projectId.value, currentAccount.value),
      { params: { year: year.value, aux_type: currentAuxType.value, aux_code: currentAuxCode.value, page: auxLedgerPage.value, page_size: 100 } }
    )
    const result = data
    auxLedgerItems.value = result.items ?? result ?? []
    auxLedgerTotal.value = result.total ?? 0
  } catch { auxLedgerItems.value = [] }
  finally { loading.value = false }
}

// ── 穿透导航 ──
function drillToLedger(row: any) {
  const code = row.account_code
  // 判断是否有子科目（非末级）：在 balanceData 中查找是否有以该编码为前缀的其他科目
  const hasChildren = balanceData.value.some(r =>
    r.account_code !== code && (r.account_code.startsWith(code + '.') || (r.account_code.startsWith(code) && r.account_code.length > code.length && !code.includes('.')))
  )
  // 非末级科目用前缀查询（查所有子科目的明细账）
  currentAccount.value = hasChildren ? code + '*' : code
  currentAccountOpening.value = num(row.opening_balance)
  currentLevel.value = 'ledger'
  ledgerPage.value = 1
  dateRange.value = null
  const label = hasChildren
    ? `${code} ${row.account_name || ''} (含明细)`
    : `${code} ${row.account_name || ''}`
  breadcrumbs.value = [
    { label: '账簿查询', level: 'balance' },
    { label, level: 'ledger', account: currentAccount.value },
  ]
  loadLedger()
}

function drillToVoucher(row: any) {
  if (!row.voucher_no) return
  currentVoucher.value = row.voucher_no
  currentLevel.value = 'voucher'
  breadcrumbs.value.push({
    label: `凭证 ${row.voucher_no}`, level: 'voucher', voucher: row.voucher_no,
  })
  loadVoucher()
}

function drillToAuxBalance() {
  // 从序时账跳到辅助余额（去掉 * 后缀）
  const code = currentAccount.value.replace('*', '')
  currentAccount.value = code
  currentLevel.value = 'aux_balance'
  breadcrumbs.value.push({
    label: `${code} 辅助余额`, level: 'aux_balance', account: code,
  })
  loadAuxBalance()
}

function drillToAuxLedger(row: any) {
  currentAuxType.value = row.aux_type
  currentAuxCode.value = row.aux_code
  currentAuxOpening.value = num(row.opening_balance)
  currentLevel.value = 'aux_ledger'
  auxLedgerPage.value = 1
  breadcrumbs.value.push({
    label: `${row.aux_name || row.aux_code}`,
    level: 'aux_ledger',
    account: currentAccount.value,
    auxType: currentAuxType.value,
    auxCode: currentAuxCode.value,
  })
  loadAuxLedger()
}

function navigateTo(index: number) {
  const crumb = breadcrumbs.value[index]
  breadcrumbs.value = breadcrumbs.value.slice(0, index + 1)
  currentLevel.value = crumb.level
  if (crumb.level === 'balance') loadBalance()
  else if (crumb.level === 'ledger') { currentAccount.value = crumb.account || ''; loadLedger() }
  else if (crumb.level === 'voucher') { currentVoucher.value = crumb.voucher || ''; loadVoucher() }
  else if (crumb.level === 'aux_balance') { currentAccount.value = crumb.account || ''; loadAuxBalance() }
  else if (crumb.level === 'aux_ledger') {
    currentAccount.value = crumb.account || currentAccount.value
    currentAuxType.value = crumb.auxType || currentAuxType.value
    currentAuxCode.value = crumb.auxCode || currentAuxCode.value
    loadAuxLedger()
  }
}

function refresh() {
  if (currentLevel.value === 'balance') loadBalance()
  else if (currentLevel.value === 'ledger') loadLedger()
  else if (currentLevel.value === 'voucher') loadVoucher()
  else if (currentLevel.value === 'aux_balance') loadAuxBalance()
  else if (currentLevel.value === 'aux_ledger') loadAuxLedger()
}

// ── 键盘快捷键：Enter 返回上一级 ──
function onKeyDown(e: KeyboardEvent) {
  if (e.key === 'Enter' && currentLevel.value !== 'balance') {
    e.preventDefault()
    // 返回上一级
    const idx = breadcrumbs.value.length - 2
    if (idx >= 0) navigateTo(idx)
  }
}
onMounted(async () => {
  document.addEventListener('keydown', onKeyDown)
  await loadProjectList()
  await loadCurrentProject()
  await loadAvailableYears()
  await loadBalance()
  _initialized = true
  if (route.query.import === '1') {
    openImportDialogFromRoute()
  }
})
onUnmounted(() => {
  document.removeEventListener('keydown', onKeyDown)
})
onBeforeUnmount(() => {
  // 需求 22.1：组件卸载时清理导入状态轮询定时器
  stopImportStatusPolling()
  // 清理完成提示延时器（防止销毁后回调误触发）
  if (_completionPromptTimer !== null) {
    clearTimeout(_completionPromptTimer)
    _completionPromptTimer = null
  }
})
</script>

<style scoped>
.gt-penetration { padding: var(--gt-space-4); height: 100%; display: flex; flex-direction: column; }

.gt-ledger-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: var(--gt-space-3); padding: 10px 16px;
  background: linear-gradient(135deg, #f8f5fc 0%, #f0ecf7 100%);
  border-radius: var(--gt-radius-md); border: 1px solid var(--gt-color-primary-lighter, #e0d4f0);
}
.gt-ledger-title { display: flex; align-items: center; }
.gt-ledger-company {
  font-size: 16px; font-weight: 600; color: var(--gt-color-primary-dark);
}
.gt-ledger-switches { display: flex; align-items: center; gap: 8px; }

.gt-balance-tabs {
  display: flex; gap: 0; margin-bottom: var(--gt-space-2);
  border-bottom: 2px solid #e8e8e8;
}
.gt-balance-tab {
  padding: 8px 20px; cursor: pointer; font-size: 14px; font-weight: 500;
  color: #666; border-bottom: 2px solid transparent; margin-bottom: -2px;
  transition: all 0.2s;
}
.gt-balance-tab:hover { color: var(--gt-color-primary); }
.gt-balance-tab--active {
  color: var(--gt-color-primary); border-bottom-color: var(--gt-color-primary);
  font-weight: 600;
}

.gt-breadcrumb {
  display: flex; align-items: center; gap: 2px;
  margin-bottom: var(--gt-space-3); font-size: var(--gt-font-size-sm);
}
.gt-crumb {
  cursor: pointer; color: var(--gt-color-primary); padding: 2px 6px;
  border-radius: var(--gt-radius-sm); transition: background var(--gt-transition-fast);
}
.gt-crumb:hover { background: var(--gt-color-primary-bg); }
.gt-crumb--active { color: var(--gt-color-text); font-weight: 600; cursor: default; }
.gt-crumb--active:hover { background: transparent; }
.gt-crumb-sep { color: var(--gt-color-text-tertiary); margin: 0 2px; }

.gt-filter-row {
  display: flex; align-items: center; gap: var(--gt-space-2);
  margin-bottom: var(--gt-space-3); flex-shrink: 0;
}
.gt-filter-spacer { flex: 1; }

.gt-link { color: var(--gt-color-primary); cursor: pointer; }
.gt-link:hover { text-decoration: underline; }

.gt-pagination { margin-top: var(--gt-space-3); display: flex; justify-content: flex-end; }

.gt-empty-state {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  min-height: 300px; border: 1px dashed #e0e0e0; border-radius: var(--gt-radius-md);
  background: #fafafa;
}

/* 序时账特殊行样式 */
:deep(.gt-ledger-opening) {
  background: #f0ecf7 !important;
  font-weight: 600;
  font-style: italic;
}
:deep(.gt-ledger-subtotal) {
  background: #fef6e6 !important;
  font-weight: 600;
  border-top: 1px solid #e6a23c;
}

/* 任务 12.8.1：异常凭证视觉标记（需求 25） */
:deep(.gt-ledger-row--over-materiality) {
  background: #fef0e6 !important;
}
:deep(.gt-ledger-row--over-materiality) td:first-child::before {
  content: '⚠️';
  margin-right: 4px;
}
:deep(.gt-ledger-row--period-end) {
  background: #fff8e8 !important;
}
:deep(.gt-ledger-row--period-end) td:first-child::after {
  content: '  截止';
  color: #e6a23c;
  font-size: 11px;
  font-weight: 600;
  margin-left: 4px;
}
:deep(.gt-ledger-row--red-reversal) td {
  color: #f56c6c !important;
}

/* 辅助余额表维度标签 */
.gt-aux-toolbar {
  margin-bottom: var(--gt-space-2);
}

/* 选中行样式：浅蓝背景，无左边框竖线 */
:deep(.el-table__body tr.current-row > td.el-table__cell) {
  background: #e8f4fd !important;
  border-left: none !important;
}

/* hover 行样式：更浅的蓝灰色 */
:deep(.el-table__body tr:hover > td.el-table__cell) {
  background: #f5f8fc !important;
}

/* 选中行 + hover 同时生效 */
:deep(.el-table__body tr.current-row:hover > td.el-table__cell) {
  background: #dceefb !important;
}

/* 去掉 el-table 默认的选中行左边框效果 */
:deep(.el-table__body tr.current-row > td.el-table__cell::after) {
  display: none !important;
}

.gt-aux-toolbar-header {
  display: flex; align-items: center; gap: var(--gt-space-2); flex-wrap: wrap;
}
.gt-dim-tabs {
  display: flex; flex-wrap: wrap; gap: 4px;
  margin-bottom: var(--gt-space-2); padding: 6px 0;
}
.gt-dim-tab {
  display: inline-flex; align-items: center;
  padding: 4px 12px; font-size: 13px; cursor: pointer;
  border-radius: var(--gt-radius-sm); border: 1px solid #e8e8e8;
  color: #666; background: #fafafa; transition: all 0.15s;
}
.gt-dim-tab:hover { border-color: var(--gt-color-primary-lighter); color: var(--gt-color-primary); }
.gt-dim-tab--active {
  background: var(--gt-color-primary-bg, #f0ecf7);
  border-color: var(--gt-color-primary);
  color: var(--gt-color-primary);
  font-weight: 600;
}

/* P3-U3: 导入成功引导卡片 */
.gt-completion-guide {
  margin-top: 24px;
  padding-top: 20px;
  border-top: 1px dashed #e0dde5;
}
.gt-completion-guide .guide-title {
  font-size: 13px;
  color: #606266;
  margin-bottom: 12px;
  font-weight: 500;
}
.gt-completion-guide .guide-cards {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}
.gt-completion-guide .guide-card {
  padding: 14px 12px;
  border: 1px solid #e0dde5;
  border-radius: 6px;
  cursor: pointer;
  text-align: center;
  transition: all 0.15s ease;
  background: #fff;
}
.gt-completion-guide .guide-card:hover {
  border-color: var(--gt-color-primary);
  background: var(--gt-color-primary-bg, #f8f5ff);
  transform: translateY(-2px);
}
.gt-completion-guide .guide-card-icon {
  font-size: 24px;
  margin-bottom: 6px;
}
.gt-completion-guide .guide-card-title {
  font-size: 13px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 4px;
}
.gt-completion-guide .guide-card-desc {
  font-size: 11px;
  color: #909399;
  line-height: 1.5;
}
</style>

/* 导入进度条 — Teleport 到 body，fixed 定位在屏幕顶部 */
:global(.gt-import-progress-overlay) {
  position: fixed;
  top: 52px;
  left: 0;
  right: 0;
  z-index: 9999;
  padding: 8px 20%;
  background: rgba(255, 255, 255, 0.95);
  box-shadow: 0 2px 8px rgba(0,0,0,0.08);
}
