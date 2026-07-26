<template>
  <div class="h4-tab-detail">
    <!-- 方法论上下文（源模板红字思路） -->
    <div class="methodology-context">
      <p>
        H4-2 工程物资明细表对齐致同源模板编制逻辑：①未审原值 rollforward（期初+增加−减少=期末，含数量/单价/金额）；
        ②核实调整后得审定原值；③跌价准备 rollforward → 账面价值=原值−跌价，审定净值与未审净值差异须追查。
        单价在数量为 0 时显示「—」，避免源 Excel 常见 #DIV/0!。分类小计对齐 SUMPRODUCT 汇总。
      </p>
    </div>

    <el-alert type="info" :closable="false" class="objective-alert">
      <template #title>
        <div class="ao-wrap">
          <strong>审计目标</strong>
          <ul class="ao-list">
            <li>存在/完整性：明细与科目1605、H4-1 审定表勾稽一致</li>
            <li>计价：原值 rollforward、跌价准备与净值计算正确</li>
            <li>权利与义务 / 列报：库龄与品质支撑减值迹象判断（→ H4-7）</li>
          </ul>
        </div>
      </template>
    </el-alert>

    <!-- 编制路径引导 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="step-num">①</span> 基础+未审原值：逐项填数量与金额分项</div>
      <div class="guide-step"><span class="step-num">②</span> 调整+审定：录入账项调整，核对审定三角勾稽</div>
      <div class="guide-step"><span class="step-num">③</span> 减值+净值：填跌价准备，差异→H4-3/H4-7</div>
      <div class="guide-step"><span class="step-num">④</span> 分类小计与 H4-1 勾稽，再推送 H4-4/H4-5/H4-6</div>
    </div>

    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H4-2" :context-project-id="props.projectId" context="明细表" /></span>
      <GtIndexChip value="wp:H4-1" :context-project-id="props.projectId" context="审定勾稽" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="hasMaterialDiff" size="small" type="warning">存在审定差异 {{ fmtAmt(subtotalRow.bookValueDiff) }}</el-tag>
      <el-tag v-else-if="rows.length" size="small" type="success">未审=审定净值</el-tag>
      <el-button size="small" type="warning" plain :loading="ledgerPulling" @click="handlePullFromLedger">📥从序时账取数</el-button>
    </div>

    <!-- H4-1 勾稽 -->
    <el-alert
      v-if="crossCheck"
      :type="crossCheck.isMatch ? 'success' : 'warning'"
      :closable="false"
      show-icon
      class="cross-alert"
      :title="crossCheck.isMatch
        ? `与 H4-1 审定勾稽一致（明细期末原值 ${fmtAmt(endTotal)}）`
        : `与 H4-1 审定不一致：差额 ${fmtAmt(crossCheck.diff)}（明细期末 ${fmtAmt(endTotal)} vs 审定 ${fmtAmt(h41Audited)}）`"
    />

    <div class="section-header">
      <span>工程物资明细表 H4-2</span>
      <div class="section-header-actions">
        <el-button size="small" circle @click="openReview('H4-2-detail')">💬</el-button>
      </div>
    </div>

    <el-tabs v-model="activeTab" type="border-card" class="detail-tabs" @tab-change="onTabChange">
      <!-- 区段1：基础+未审原值 -->
      <el-tab-pane label="基础+未审原值" name="book">
        <el-table
          :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId"
        >
          <el-table-column type="index" label="序号" width="50" align="center" fixed />
          <el-table-column prop="category" label="物资分类" min-width="100" fixed>
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" :model-value="row.category" size="small"
                @change="updateCell(row.rowId, 'category', $event)" />
              <span v-else>{{ row.category || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="物资名称" min-width="110" fixed>
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" :model-value="row.name" size="small"
                @change="updateCell(row.rowId, 'name', $event)" />
              <span v-else>{{ row.name }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="spec" label="规格" min-width="80">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" :model-value="row.spec" size="small"
                @change="updateCell(row.rowId, 'spec', $event)" />
              <span v-else>{{ row.spec || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="unit" label="单位" width="60">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" :model-value="row.unit" size="small"
                @change="updateCell(row.rowId, 'unit', $event)" />
              <span v-else>{{ row.unit || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="supplier" label="供应商" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!props.isReadonly" :model-value="row.supplier" size="small"
                @change="updateCell(row.rowId, 'supplier', $event)" />
              <span v-else>{{ row.supplier || '—' }}</span>
            </template>
          </el-table-column>

          <el-table-column label="期初" align="center">
            <el-table-column label="数量" width="78" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.beginQty" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'beginQty', $event)" />
                <span v-else class="amt-cell">{{ fmtQty(row.beginQty) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单价" width="78" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="单价 = 金额 ÷ 数量（数量为0显示—）">{{ fmtPrice(row.beginUnitPrice) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.beginAmount" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'beginAmount', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.beginAmount) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="本期增加" align="center">
            <el-table-column label="数量" width="78" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.increaseQty" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'increaseQty', $event)" />
                <span v-else class="amt-cell">{{ fmtQty(row.increaseQty) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="采购" width="96" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.purchaseAmount" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'purchaseAmount', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.purchaseAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="其他增加" width="96" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.otherIncrease" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'otherIncrease', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.otherIncrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="小计" width="96" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="入库小计 = 采购 + 其他增加">{{ fmtAmt(row.increaseSubtotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单价" width="78" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="单价 = 增加小计 ÷ 增加数量">{{ fmtPrice(row.increaseUnitPrice) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="本期减少" align="center">
            <el-table-column label="数量" width="78" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.decreaseQty" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'decreaseQty', $event)" />
                <span v-else class="amt-cell">{{ fmtQty(row.decreaseQty) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="领用" width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.usageAmount" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'usageAmount', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.usageAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="退货" width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.returnAmount" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'returnAmount', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.returnAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="报废" width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.scrapAmount" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'scrapAmount', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.scrapAmount) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="其他" width="90" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!props.isReadonly" :model-value="row.otherDecrease" :controls="false"
                  size="small" class="amt-input" @change="updateCell(row.rowId, 'otherDecrease', $event)" />
                <span v-else class="amt-cell">{{ fmtAmt(row.otherDecrease) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="小计" width="96" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="出库合计 = 领用+退货+报废+其他">{{ fmtAmt(row.decreaseTotal) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column label="期末" align="center">
            <el-table-column label="数量" width="78" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末数量 = 期初 + 增加 − 减少">{{ fmtQty(row.endQty) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="单价" width="78" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="单价 = 期末金额 ÷ 期末数量">{{ fmtPrice(row.endUnitPrice) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="金额" width="100" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末 = 期初 + 入库小计 − 出库合计">{{ fmtAmt(row.endAmount) }}</span>
              </template>
            </el-table-column>
          </el-table-column>

          <el-table-column v-if="!props.isReadonly" label="" width="42" fixed="right">
            <template #default="{ row }">
              <el-button size="small" type="danger" link @click="handleDeleteRow(row.rowId)">✕</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- 区段2：调整+审定原值 -->
      <el-tab-pane label="调整+审定原值" name="adjust">
        <el-table
          :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId"
        >
          <el-table-column type="index" label="序号" width="50" align="center" />
          <el-table-column prop="name" label="物资名称" min-width="110" />
          <el-table-column label="未审期末" width="100" align="right">
            <template #default="{ row }">
              <span class="amt-cell">{{ fmtAmt(row.endAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整-期初" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.ajeBegin" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'ajeBegin', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.ajeBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整-增加" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.ajeIncrease" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'ajeIncrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.ajeIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整-减少" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.ajeDecrease" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'ajeDecrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.ajeDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定期初" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定期初 = 未审期初 + 账项调整">{{ fmtAmt(row.auditedBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定增加" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定增加 = 未审增加 + 账项调整">{{ fmtAmt(row.auditedIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定减少" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定减少 = 未审减少 + 账项调整">{{ fmtAmt(row.auditedDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定期末" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定期末 = 审定期初 + 审定增加 − 审定减少">{{ fmtAmt(row.auditedEnd) }}</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="tab-hint">行级账项调整与 H4-3 分录可通过底部「推送账项调整 → H4-3 / 从 H4-3 回写」双向同步；整表借贷平衡以 H4-3 为准（类别：账项调整/报表调整）。</p>
      </el-tab-pane>

      <!-- 区段3：减值+净值 -->
      <el-tab-pane label="减值+净值" name="impair">
        <el-table
          :data="rows" border stripe size="small" class="detail-table"
          highlight-current-row :current-row-key="selectedRowId"
          @current-change="onCurrentRowChange" row-key="rowId"
        >
          <el-table-column type="index" label="序号" width="50" align="center" />
          <el-table-column prop="name" label="物资名称" min-width="110" />
          <el-table-column label="跌价期初" width="96" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.impairBegin" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'impairBegin', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairBegin) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期计提" width="96" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.impairIncrease" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'impairIncrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairIncrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期转销" width="96" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.impairDecrease" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'impairDecrease', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.impairDecrease) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="跌价期末" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="跌价期末 = 期初 + 计提 − 转销">{{ fmtAmt(row.impairEnd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账项调整-减值" width="110" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!props.isReadonly" :model-value="row.ajeImpair" :controls="false"
                size="small" class="amt-input" @change="updateCell(row.rowId, 'ajeImpair', $event)" />
              <span v-else class="amt-cell">{{ fmtAmt(row.ajeImpair) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定跌价" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定跌价 = 跌价期末 + 账项调整">{{ fmtAmt(row.auditedImpairEnd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="未审净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="未审净值 = 未审原值期末 − 跌价期末">{{ fmtAmt(row.bookValueEnd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="审定净值" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="审定净值 = 审定原值期末 − 审定跌价">{{ fmtAmt(row.auditedBookValue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="差异" width="96" align="right">
            <template #default="{ row }">
              <span :class="['formula-cell', Math.abs(row.bookValueDiff) >= 0.01 ? 'diff-warn' : '']"
                title="差异 = 未审净值 − 审定净值">{{ fmtAmt(row.bookValueDiff) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="库龄" min-width="90">
            <template #default="{ row }">
              <el-select v-if="!props.isReadonly" :model-value="row.aging || undefined" size="small" clearable
                placeholder="选择" @change="updateCell(row.rowId, 'aging', $event ?? '')">
                <el-option v-for="o in AGING_OPTS" :key="o" :label="o" :value="o" />
              </el-select>
              <span v-else>{{ row.aging || '—' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="品质" min-width="90">
            <template #default="{ row }">
              <el-select v-if="!props.isReadonly" :model-value="row.quality || undefined" size="small" clearable
                placeholder="选择" @change="updateCell(row.rowId, 'quality', $event ?? '')">
                <el-option v-for="o in QUALITY_OPTS" :key="o" :label="o" :value="o" />
              </el-select>
              <span v-else>{{ row.quality || '—' }}</span>
            </template>
          </el-table-column>
        </el-table>
        <p class="tab-hint">库龄偏长或品质异常应在 H4-7 评估减值迹象；减值账项调整可推送至 H4-3。</p>
      </el-tab-pane>
    </el-tabs>

    <!-- 合计 + 分类小计 -->
    <el-card shadow="never" class="subtotal-card">
      <div class="subtotal-grid">
        <div class="subtotal-item"><span class="st-label">期初原值：</span><span class="st-value">{{ fmtAmt(subtotalRow.beginAmount) }}</span></div>
        <div class="subtotal-item"><span class="st-label">本期增加：</span><span class="st-value">{{ fmtAmt(subtotalRow.increaseSubtotal) }}</span></div>
        <div class="subtotal-item"><span class="st-label">本期减少：</span><span class="st-value">{{ fmtAmt(subtotalRow.decreaseTotal) }}</span></div>
        <div class="subtotal-item"><span class="st-label">期末原值：</span><span class="st-value formula-cell" title="Σ期末原值">{{ fmtAmt(subtotalRow.endAmount) }}</span></div>
        <div class="subtotal-item"><span class="st-label">跌价期末：</span><span class="st-value">{{ fmtAmt(subtotalRow.impairEnd) }}</span></div>
        <div class="subtotal-item"><span class="st-label">未审净值：</span><span class="st-value">{{ fmtAmt(subtotalRow.bookValueEnd) }}</span></div>
        <div class="subtotal-item"><span class="st-label">审定净值：</span><span class="st-value formula-cell">{{ fmtAmt(subtotalRow.auditedBookValue) }}</span></div>
        <div class="subtotal-item"><span class="st-label">净值差异：</span>
          <span :class="['st-value', hasMaterialDiff ? 'diff-warn' : '']">{{ fmtAmt(subtotalRow.bookValueDiff) }}</span>
        </div>
      </div>
    </el-card>

    <el-card v-if="categorySubtotals.length" shadow="never" class="category-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>按物资分类小计</span>
          <el-tag size="small" type="info">对齐 Excel SUMPRODUCT</el-tag>
        </div>
      </template>
      <el-table :data="categorySubtotals" border size="small" class="detail-table">
        <el-table-column prop="category" label="分类" min-width="120" />
        <el-table-column prop="rowCount" label="行数" width="60" align="center" />
        <el-table-column label="期初" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.beginAmount) }}</template>
        </el-table-column>
        <el-table-column label="增加" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.increaseSubtotal) }}</template>
        </el-table-column>
        <el-table-column label="减少" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.decreaseTotal) }}</template>
        </el-table-column>
        <el-table-column label="期末原值" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.endAmount) }}</template>
        </el-table-column>
        <el-table-column label="跌价" width="90" align="right">
          <template #default="{ row }">{{ fmtAmt(row.impairEnd) }}</template>
        </el-table-column>
        <el-table-column label="未审净值" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.bookValueEnd) }}</template>
        </el-table-column>
        <el-table-column label="审定净值" width="100" align="right">
          <template #default="{ row }">{{ fmtAmt(row.auditedBookValue) }}</template>
        </el-table-column>
        <el-table-column label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="Math.abs(row.bookValueDiff) >= 0.01 ? 'diff-warn' : ''">{{ fmtAmt(row.bookValueDiff) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <div class="action-bar" v-if="!props.isReadonly">
      <el-button size="small" type="primary" @click="handleAddRow">+ 添加物资行</el-button>
      <el-button size="small" type="success" plain @click="handlePushAje">推送账项调整 → H4-3</el-button>
      <el-button size="small" @click="handlePullAje">从 H4-3 回写账项调整</el-button>
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

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计说明</span>
          <div class="section-header-actions">
            <el-button size="small" :icon="MagicStick" @click="generateNoteAi" :loading="aiLoading">AI</el-button>
            <el-button size="small" circle @click="openReview('H4-2-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }"
        placeholder="请填写审计说明（可引用分类小计、差异及与 H4-1/H4-4/H4-5 勾稽情况）..."
        :disabled="props.isReadonly" @blur="saveAuditNote" />
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="section-header" style="margin-bottom:0">
          <span>审计结论</span>
          <div class="section-header-actions">
            <el-button size="small" @click="applyConclusionTemplate" :disabled="props.isReadonly">套用模板</el-button>
            <el-button size="small" circle @click="openReview('H4-2-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 6 }"
        placeholder="请填写审计结论..." :disabled="props.isReadonly" @blur="saveAuditConclusion" />
    </el-card>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>三区段对齐源模板：未审原值（数量·单价·金额）→ 账项调整/审定 → 跌价准备与净值差异。</li>
        <li>核心公式：期末原值=期初+采购+其他增加−领用−退货−报废−其他减少；净值=原值−跌价。</li>
        <li>单价数量为 0 时显示「—」，不产生 #DIV/0!。</li>
        <li>行级账项调整可「推送 → H4-3」生成借贷平衡草稿，亦可「从 H4-3 回写」；H4-3 侧有「从 H4-2 带入行级调整」。</li>
        <li>分类小计便于与 H4-1 分类行及附注核对。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H4TabDetail.vue — H4-2 明细表（C4：基础+未审原值 / 调整+审定 / 减值+净值）
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import http from '@/utils/http'
import { useH4Detail, type H4DetailTab } from '../../composables/useH4Detail'
import { useH4ImportExport } from '../../composables/useH4ImportExport'
import { useH4CrossSheet } from '../../composables/useH4CrossSheet'
import { pullAssetMovementFromLedger } from '../../composables/assetLedgerMovementPull'
import GtIndexChip from '../../GtIndexChip.vue'

const AGING_OPTS = ['1年以内', '1-2年', '2-3年', '3年以上']
const QUALITY_OPTS = ['正常', '闲置', '毁损', '待报废', '积压']

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(itemId: string, value: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)

const {
  rows, activeTab, selectedRowId, subtotalRow, categorySubtotals,
  endTotal, hasMaterialDiff,
  addRow, deleteRow, updateCell, setActiveTab, selectRow,
  pushAjeToH43, pullAjeFromH43,
} = useH4Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
  onSave: (itemId: string, value: any) => {
    // 与 H4-4/H4-5 一致：走主入口 persistResponse 落库
    saveResponse(itemId, value)
  },
})

const crossSheet = useH4CrossSheet(allResponsesRef as any)
const crossCheck = computed(() => crossSheet.adjudicationVsDetail.value)
const h41Audited = computed(() => crossSheet.adjudicationTotals.value.adjudicatedTotal)

const importExport = useH4ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => { /* allResponses 由主入口 reload */ },
})

const auditNote = ref('')
const auditConclusion = ref('')
const aiLoading = ref(false)

// ─── 从序时账取数（资产类科目1605 借方=增加 贷方=减少）────────────────────────
const ledgerPulling = ref(false)
async function handlePullFromLedger() {
  const year = new Date().getFullYear() - 1
  ledgerPulling.value = true
  try {
    const result = await pullAssetMovementFromLedger(props.projectId, year, '1605')
    if (!result.ok) {
      ElMessageBox.alert(result.message, '取数提示', { type: 'warning' })
      return
    }
    const fmtN = (n: number) => n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
    await ElMessageBox.confirm(
      `从序时账聚合 ${result.rows.length} 个明细科目：\n合计增加 ${fmtN(result.totalIncrease)}，合计减少 ${fmtN(result.totalDecrease)}\n\n确认填入明细表？（只填空值不覆盖已有数据）`,
      '📥 从序时账取数预览',
      { confirmButtonText: '填入', cancelButtonText: '取消', type: 'info' },
    )
    let matched = 0
    for (const item of result.rows) {
      const existing = rows.value.find(
        (r) => r.name === item.name || r.name.includes(item.name) || item.name.includes(r.name),
      )
      if (existing) {
        // H4 增加=purchaseAmount（采购）+otherIncrease；填入 purchaseAmount 主入口
        if (!existing.purchaseAmount && !existing.otherIncrease && item.increase > 0.005) {
          updateCell(existing.rowId, 'purchaseAmount', item.increase)
          matched++
        }
        // H4 减少=usageAmount+returnAmount+scrapAmount+otherDecrease；填入 usageAmount 主入口
        if (!existing.usageAmount && !existing.otherDecrease && item.decrease > 0.005) {
          updateCell(existing.rowId, 'usageAmount', item.decrease)
          matched++
        }
      }
    }
    ElMessageBox.alert(`已匹配填入 ${matched} 个字段`, '取数完成', { type: 'success' })
  } catch (e: any) {
    if (e === 'cancel' || e?.toString?.().includes('cancel')) return
    ElMessageBox.alert(String(e?.message || e), '取数失败', { type: 'error' })
  } finally {
    ledgerPulling.value = false
  }
}

function saveAuditNote() {
  saveResponse('H4-2-note', auditNote.value)
}
function saveAuditConclusion() {
  saveResponse('H4-2-conclusion', auditConclusion.value)
}

onMounted(() => {
  const n = props.allResponses.get('H4-2-note'); if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get('H4-2-conclusion'); if (c?.remark) auditConclusion.value = c.remark
})

function onTabChange(tab: string | number) {
  setActiveTab(tab as H4DetailTab)
}
function onCurrentRowChange(row: any) {
  selectRow(row?.rowId ?? null)
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入物资名称', '添加物资行', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) addRow(value)
  } catch { /* cancelled */ }
}

function handleDeleteRow(rowId: string) {
  deleteRow(rowId)
}

function handlePushAje() {
  const r = pushAjeToH43()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handlePullAje() {
  const r = pullAjeFromH43()
  if (r.ok) ElMessage.success(r.message)
  else ElMessage.warning(r.message)
}

function handleImportExport(command: string) {
  if (command === 'export-template') importExport.exportTemplate('H4-2')
  else if (command === 'export-data') importExport.exportData('H4-2')
  else if (command === 'import-data') {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls,.csv'
    input.onchange = (e: Event) => {
      const file = (e.target as HTMLInputElement).files?.[0]
      if (file) importExport.importData('H4-2', file)
    }
    input.click()
  }
}

function openReview(id: string) {
  openReviewDialog(id)
}

function applyConclusionTemplate() {
  const diff = subtotalRow.value.bookValueDiff
  const ok = Math.abs(diff) < 0.01
  auditConclusion.value = ok
    ? `经核对，工程物资明细期末原值合计 ${fmtAmt(subtotalRow.value.endAmount)}、未审净值 ${fmtAmt(subtotalRow.value.bookValueEnd)} 与审定净值一致，可为 H4-1 审定及报表列报提供充分、适当的审计证据。`
    : `工程物资明细未审净值与审定净值存在差异 ${fmtAmt(diff)}，已/拟通过 H4-3 调整分录处理，并在 H4-7 评估相关减值影响。`
  saveAuditConclusion()
  ElMessage.success('已套用结论模板')
}

async function generateNoteAi() {
  if (!props.wpId) return
  aiLoading.value = true
  try {
    const cats = categorySubtotals.value.map(c => `${c.category}:${c.endAmount}`).join('；')
    const { data } = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'H4-2-note',
      existingContent: auditNote.value,
      relatedContext: {
        rowCount: rows.value.length,
        endAmount: subtotalRow.value.endAmount,
        bookValueEnd: subtotalRow.value.bookValueEnd,
        auditedBookValue: subtotalRow.value.auditedBookValue,
        bookValueDiff: subtotalRow.value.bookValueDiff,
        categorySubtotals: cats,
        crossMatch: crossCheck.value?.isMatch,
      },
    })
    const text = data?.content || data?.text || data?.result
    if (text) {
      auditNote.value = String(text)
      saveAuditNote()
      ElMessage.success('AI 说明已生成')
    } else {
      // 本地降级
      auditNote.value = [
        `本期工程物资明细共 ${rows.value.length} 项，期末原值合计 ${fmtAmt(subtotalRow.value.endAmount)}，未审净值 ${fmtAmt(subtotalRow.value.bookValueEnd)}，审定净值 ${fmtAmt(subtotalRow.value.auditedBookValue)}。`,
        Math.abs(subtotalRow.value.bookValueDiff) >= 0.01
          ? `未审与审定净值差异 ${fmtAmt(subtotalRow.value.bookValueDiff)}，需与 H4-3 调整及 H4-7 减值测算勾稽。`
          : '未审与审定净值一致。',
        cats ? `分类小计：${cats}。` : '',
        '增加/减少总体已/拟分别与 H4-4、H4-5 检查比例勾稽；期末余额支撑 H4-6 监盘抽样。',
      ].filter(Boolean).join('\n')
      saveAuditNote()
      ElMessage.info('AI 不可用，已生成本地说明草稿')
    }
  } catch {
    auditNote.value = `本期明细 ${rows.value.length} 行，期末原值 ${fmtAmt(subtotalRow.value.endAmount)}，审定净值 ${fmtAmt(subtotalRow.value.auditedBookValue)}。请补充抽样与差异说明。`
    saveAuditNote()
    ElMessage.warning('AI 调用失败，已写入本地草稿')
  } finally {
    aiLoading.value = false
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

function fmtQty(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return Number(val).toLocaleString('zh-CN', { maximumFractionDigits: 4 })
}

function fmtPrice(val: number | null | undefined): string {
  if (val == null) return '—'
  if (val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 4 })
}
</script>

<style scoped>
.h4-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.ao-wrap { font-size: 12px; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; }

.guide-banner {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px 16px;
  background: linear-gradient(135deg, #eff6ff 0%, #f0f9ff 100%);
  border: 1px solid #bfdbfe;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 12px;
  font-size: 12px;
  color: #1e3a8a;
}
.guide-step { display: flex; align-items: flex-start; gap: 6px; line-height: 1.45; }
.step-num {
  flex-shrink: 0; width: 18px; height: 18px; border-radius: 50%;
  background: #2563eb; color: #fff; font-size: 11px; font-weight: 600;
  display: inline-flex; align-items: center; justify-content: center;
}

.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap; }
.chip-wrap { display: inline-flex; align-items: center; }
.cross-alert { margin-bottom: 12px; }

.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 10px 14px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.6;
}

.section-header {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 14px; font-weight: 600; margin-bottom: 12px;
}
.section-header-actions { display: flex; align-items: center; gap: 4px; }

.detail-tabs { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amt-input { width: 100%; }
.amt-cell { display: block; text-align: right; }
.tab-hint { margin: 8px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }

.formula-cell {
  display: inline-block; text-align: right;
  border-bottom: 1px dashed #67c23a;
  cursor: help;
  color: var(--el-text-color-primary);
}
.diff-warn { color: #e6a23c; font-weight: 600; }

.subtotal-card, .category-card { margin-bottom: 12px; }
.subtotal-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 10px 12px; }
.subtotal-item { display: flex; align-items: center; gap: 6px; }
.st-label { color: var(--el-text-color-secondary); font-size: 12px; white-space: nowrap; }
.st-value { font-weight: 600; font-variant-numeric: tabular-nums; }

.action-bar { display: flex; align-items: center; margin-bottom: 12px; }
.audit-note-card { margin-bottom: 12px; }
.edit-tips { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }

@media (max-width: 900px) {
  .guide-banner { grid-template-columns: 1fr; }
  .subtotal-grid { grid-template-columns: repeat(2, 1fr); }
}
</style>
