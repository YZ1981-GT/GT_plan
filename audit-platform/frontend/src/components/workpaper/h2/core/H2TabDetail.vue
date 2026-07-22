<template>
  <div class="h2-tab-detail">
    <!-- 一、审计目标（对齐致同源模板 + H1） -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">一、审计目标</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li>资产负债表中记录的在建工程是存在的；</li>
        <li>所有应记录的在建工程均已记录；</li>
        <li>在建工程以恰当的金额包括在财务报表中，与之相关的计价或分摊调整（含利息资本化）已恰当记录。</li>
      </ol>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <GtIndexChip value="wp:H2-2" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ state.rows.value.length }} 项</el-tag>
      <el-tag v-if="state.rows.value.length && !cv.isMatch" size="small" type="warning">
        审定期末≠H2-1（差 {{ fmtAmt(cv.diff) }}）
      </el-tag>
      <el-tag v-else-if="state.rows.value.length && cv.isMatch" size="small" type="success">
        与 H2-1 勾稽一致
      </el-tag>
      <el-button size="small" circle @click="openReview('H2-2')">💬</el-button>
    </div>

    <!-- 引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 基本信息：预算/进度/状态/资金来源/资本化率 + 抵押标志</div>
        <div class="guide-step"><span class="step-num">②</span> 账面原值：期初+增(材料/人工/机械/利息/其他)−转固−其他减=期末；利息子列单独勾稽</div>
        <div class="guide-step"><span class="step-num">③</span> 审定原值：期初调整/账项调整 → 审定自动；与 H2-1 交叉验证</div>
        <div class="guide-step"><span class="step-num">④</span> 减值与净值：减值未审→调整→审定；净值=原值−减值（无折旧）</div>
      </div>
    </div>

    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <div class="toolbar" v-if="!isReadonly">
      <el-button size="small" type="primary" @click="handleAddRow">+ 新增工程</el-button>
      <el-button size="small" @click="handleRemoveSelected" :disabled="!selectedRowId">删除选中</el-button>
      <el-dropdown trigger="click" @command="handleExportCmd">
        <el-button size="small" :loading="ie.importing.value">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="export-template">导出模板（4区段）</el-dropdown-item>
            <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
            <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button
        size="small"
        type="warning"
        plain
        :disabled="!mortgagedCount"
        @click="syncMortgageToDisclosure"
      >同步抵押至附注（{{ mortgagedCount }}）</el-button>
      <span class="row-count">共 {{ state.rows.value.length }} 项 · 灰色虚线列为自动计算</span>
    </div>

    <!-- 区段1: 基本信息 -->
    <div v-show="activeSegment === 'basic'" class="segment-panel">
      <el-table :data="displayRows" border stripe size="small" highlight-current-row
        :row-class-name="detailRowClass" @current-change="handleRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="工程项目" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.name" size="small"
              @change="onCellChange(row.rowId, 'name', row.name)" />
            <span v-else :class="{ 'total-label': row.isTotal }">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程编号" width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.projectCode" size="small"
              @change="onCellChange(row.rowId, 'projectCode', row.projectCode)" />
            <span v-else>{{ row.projectCode || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预算金额" width="110" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="budget" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
          </template>
        </el-table-column>
        <el-table-column label="工程类别" width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.category" size="small"
              @change="onCellChange(row.rowId, 'category', row.category)" />
            <span v-else>{{ row.category || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程状态" width="120">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.projectStatus" size="small"
              @change="onCellChange(row.rowId, 'projectStatus', row.projectStatus)">
              <el-option v-for="s in statusOptions" :key="s" :label="s" :value="s" />
            </el-select>
            <span v-else>{{ row.projectStatus || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="开工日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.startDate" type="date"
              value-format="YYYY-MM-DD" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'startDate', row.startDate)" />
            <span v-else>{{ row.startDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="预计竣工" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.plannedEndDate" type="date"
              value-format="YYYY-MM-DD" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'plannedEndDate', row.plannedEndDate)" />
            <span v-else>{{ row.plannedEndDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="实际竣工" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.actualEndDate" type="date"
              value-format="YYYY-MM-DD" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'actualEndDate', row.actualEndDate)" />
            <span v-else>{{ row.actualEndDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="完工进度(%)" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" :class="{ 'over-budget': !row.isTotal && row.completionRate != null && row.completionRate > 100 }"
              title="=累计投入/预算×100">
              {{ row.completionRate != null ? row.completionRate.toFixed(1) + '%' : '—' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column label="累计投入" width="110" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="accumulatedInput" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
          </template>
        </el-table-column>
        <el-table-column label="资金来源" width="100">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.fundSource" size="small"
              @change="onCellChange(row.rowId, 'fundSource', row.fundSource)" />
            <span v-else>{{ row.fundSource || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资本化率(%)" width="100" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!row.isTotal && !isReadonly" v-model="row.capRate" :controls="false"
              size="small" class="amt-input"
              @change="onCellChange(row.rowId, 'capRate', row.capRate)" />
            <span v-else>{{ row.capRate != null ? row.capRate + '%' : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="批准文号" width="110">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.approvalDocNo" size="small"
              @change="onCellChange(row.rowId, 'approvalDocNo', row.approvalDocNo)" />
            <span v-else>{{ row.approvalDocNo || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否抵押" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!row.isTotal && !isReadonly" v-model="row.isMortgaged" size="small" clearable
              @change="onCellChange(row.rowId, 'isMortgaged', row.isMortgaged)">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.isMortgaged) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转固日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!row.isTotal && !isReadonly" v-model="row.transferDate" type="date"
              value-format="YYYY-MM-DD" size="small" style="width:100%"
              @change="onCellChange(row.rowId, 'transferDate', row.transferDate)" />
            <span v-else>{{ row.transferDate || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="转入固定资产类别" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!row.isTotal && !isReadonly" v-model="row.transferToH1" size="small"
              @change="onCellChange(row.rowId, 'transferToH1', row.transferToH1)" />
            <span v-else>{{ row.transferToH1 || '—' }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段2: 账面原值（未审） -->
    <div v-show="activeSegment === 'costUnadj'" class="segment-panel">
      <el-table :data="displayRows" border stripe size="small" highlight-current-row
        :row-class-name="detailRowClass" @current-change="handleRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="工程项目" min-width="120" fixed />

        <el-table-column label="期初余额" align="center">
          <el-table-column label="余额" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="cipBegin" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="其中:累计资本化" width="120" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="interestBegin" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期增加" align="center">
          <el-table-column label="材料" width="95" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseMaterial" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="人工" width="95" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseLabor" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="机械" width="95" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseMachinery" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="利息资本化" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseInterest" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他" width="95" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseOther" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="合计" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="=材料+人工+机械+利息+其他">{{ fmtAmt(row.increaseTotal) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="本期减少" align="center">
          <el-table-column label="转入固定资产" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="transferAmount" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="decrease" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="其中:资本化转出" width="120" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="interestDec" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期末余额" align="center">
          <el-table-column label="余额" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末=期初+增加−转固−其他减少">{{ fmtAmt(row.cipEnd) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其中:累计资本化" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="=期初资本化+本期利息资本化−资本化转出">{{ fmtAmt(row.interestEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段3: 审定原值 -->
    <div v-show="activeSegment === 'costAud'" class="segment-panel">
      <el-table :data="displayRows" border stripe size="small" highlight-current-row
        :row-class-name="detailRowClass" @current-change="handleRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="工程项目" min-width="120" fixed />

        <el-table-column label="期初调整" width="100" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="adjustBegin" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
          </template>
        </el-table-column>

        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期增加" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="increaseAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="转入固定资产" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="transferAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="decreaseAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="利息资本化增" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="interestIncAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="资本化转出调" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="interestDecAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="审定数" align="center">
          <el-table-column label="期初" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初审定=期初未审+期初调整">{{ fmtAmt(row.beginAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="增加审定=未审增加+账项调整增加">{{ fmtAmt(row.increaseAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="转入固定资产" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.transferAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.decreaseAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末审定=期初审定+增加审定−转固审定−其他减少审定">{{ fmtAmt(row.endAudited) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="其中:累计资本化" width="120" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.interestEndAud) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段4: 减值与净值 -->
    <div v-show="activeSegment === 'impair'" class="segment-panel">
      <el-table :data="displayRows" border stripe size="small" highlight-current-row
        :row-class-name="detailRowClass" @current-change="handleRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="name" label="工程项目" min-width="120" fixed />

        <el-table-column label="减值准备·未审数" align="center">
          <el-table-column label="期初" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairmentBegin" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairmentIncrease" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairmentDecrease" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末=期初+增加−减少">{{ fmtAmt(row.impairmentEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期初调整" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="impairOpenAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
          </template>
        </el-table-column>

        <el-table-column label="账项调整" align="center">
          <el-table-column label="增加" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairIncAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
          <el-table-column label="减少" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairDecAdj" :readonly="isReadonly || row.isTotal" @change="onAmtChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="减值审定·期末" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell">{{ fmtAmt(row.impairEndAud) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="期初净值" align="center">
          <el-table-column label="未审" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netBeginUnadj) }}</span></template>
          </el-table-column>
          <el-table-column label="审定" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netBeginAud) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="期末净值" align="center">
          <el-table-column label="未审" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netEndUnadj) }}</span></template>
          </el-table-column>
          <el-table-column label="审定" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.netEndAud) }}</span></template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="是否抵押" width="90" align="center">
          <template #default="{ row }">
            <span>{{ ynLabel(row.isMortgaged) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="cas-hint">提示：在建工程不计提折旧；达预定可使用状态应及时转固（→H2-5）。减值一经确认一般不得转回（CAS8）；「减少」通常对应转固/处置时冲销已提减值。</p>
    </div>

    <!-- 合计 + 勾稽 -->
    <div class="summary-section">
      <el-descriptions :column="4" border size="small" title="二、审计过程 — 合计（审定口径）">
        <el-descriptions-item label="原值期末审定">{{ fmtAmt(state.subtotalRow.value.endAudited) }}</el-descriptions-item>
        <el-descriptions-item label="累计资本化(审定)">{{ fmtAmt(state.subtotalRow.value.interestEndAud) }}</el-descriptions-item>
        <el-descriptions-item label="减值期末审定">{{ fmtAmt(state.subtotalRow.value.impairEndAud) }}</el-descriptions-item>
        <el-descriptions-item label="净值期末审定">{{ fmtAmt(state.subtotalRow.value.netEndAud) }}</el-descriptions-item>
      </el-descriptions>

      <el-alert
        :type="!state.rows.value.length ? 'info' : (cv.isMatch ? 'success' : 'warning')"
        :closable="false" style="margin-top:10px" show-icon
        :title="crossCheckTitle"
      />
    </div>

    <!-- 三、审计说明 -->
    <el-card shadow="never" class="audit-note-card" style="margin-bottom:12px">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="state.auditNote.value" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="可概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响；取数来源、三角勾稽、利息资本化核查、与 H2-1/H2-5 交叉验证情况。"
        @blur="state.saveNote(state.auditNote.value)" />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card shadow="never" class="audit-note-card" style="margin-bottom:12px">
      <template #header>
        <div class="conclusion-header">
          <span>四、审计结论</span>
          <div v-if="!isReadonly" class="conclusion-actions">
            <el-button size="small" @click="applyTpl('A')">套用 A</el-button>
            <el-button size="small" @click="applyTpl('B')">套用 B</el-button>
            <el-button size="small" type="warning" @click="applyTpl('C')">套用 C</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="state.auditConclusion.value" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
        @blur="state.saveConclusion(state.auditConclusion.value)" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（对齐致同源模板 / 参照 H1-2）</summary>
      <ul>
        <li>编制逻辑：未审 roll-forward（期初+增−转固−其他减=期末）→ 期初调整与账项调整 → 审定自动勾稽 → 净值与 H2-1 交叉验证。</li>
        <li>与固定资产差异：无累计折旧区段；减少主路径为「转入固定资产」；利息资本化设独立子列（风险关注点）。</li>
        <li>利息勾稽：期末累计资本化 = 期初累计 + 本期利息资本化 − 资本化转出；应与 H2-10/H2-11 测算勾稽。</li>
        <li>净值 = 原值 − 减值准备（分别计算未审/审定）；「是否抵押=是」可一键同步附注受限披露。</li>
        <li>导入导出为 4 区段多 sheet，表头与本页字段一致；已达可用仍挂账 → H2-5；重大增减 → H2-8/H2-9。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabDetail.vue — H2-2 在建工程明细表
 * 对齐致同 50 列逻辑 + H1-2 编制范式：4 区段 Tab / 未审→调整→审定 / 减值净值 / 结论 A/B/C
 */
import { ref, computed, inject, toRef, defineComponent, h } from 'vue'
import { ElMessage, ElMessageBox, ElInputNumber } from 'element-plus'
import {
  useH2Detail,
  H2_2_PROJECT_STATUS_OPTIONS,
  type H2DetailRow,
} from '../../composables/useH2Detail'
import { useH2ImportExport } from '../../composables/useH2ImportExport'
import {
  H2_LISTED_ITEM,
  mapMortgagedDetailToRows,
  buildMortgageNoteText,
} from '../../composables/h2ListedDisclosureModel'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const activeSegment = ref<'basic' | 'costUnadj' | 'costAud' | 'impair'>('basic')
const segmentOptions = [
  { label: '基本信息', value: 'basic' },
  { label: '账面原值', value: 'costUnadj' },
  { label: '审定原值', value: 'costAud' },
  { label: '减值与净值', value: 'impair' },
]
const statusOptions = [...H2_2_PROJECT_STATUS_OPTIONS]
const selectedRowId = ref('')

const state = useH2Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const ie = useH2ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  onImported: () => state.initFromAllResponses(),
})

const mortgagedCount = computed(() =>
  state.rows.value.filter((r) => r.isMortgaged === 'Y').length,
)

type DisplayRow = H2DetailRow & { isTotal?: boolean }

const displayRows = computed<DisplayRow[]>(() => [
  ...state.rows.value,
  { ...state.subtotalRow.value, isTotal: true },
])

const cv = computed(() => state.crossValidationH1.value)

const crossCheckTitle = computed(() => {
  if (!state.rows.value.length) return '尚未录入明细；录入后将与 H2-1 审定表自动勾稽。'
  if (!cv.value.isMatch) {
    return `原值期末审定 ${fmtAmt(cv.value.detailTotal)} ≠ H2-1 ${fmtAmt(cv.value.h1Total)}（差额 ${fmtAmt(cv.value.diff)}）`
  }
  return `与 H2-1 勾稽一致：原值审定期末 ${fmtAmt(cv.value.detailTotal)} / 净值审定 ${fmtAmt(state.subtotalRow.value.netEndAud)}`
})

const AmtInput = defineComponent({
  name: 'H2DetailAmtInput',
  props: {
    row: { type: Object as () => DisplayRow, required: true },
    field: { type: String, required: true },
    readonly: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(p, { emit }) {
    return () => {
      if (p.readonly || (p.row as DisplayRow).isTotal) {
        return h('span', { class: 'amt-cell' }, fmtAmt((p.row as any)[p.field]))
      }
      return h(ElInputNumber, {
        modelValue: (p.row as any)[p.field],
        'onUpdate:modelValue': (v: number | undefined) => {
          ;(p.row as any)[p.field] = v ?? 0
        },
        controls: false,
        size: 'small',
        precision: 2,
        style: { width: '100%' },
        onChange: () => emit('change', p.row, p.field),
      })
    }
  },
})

function detailRowClass({ row }: { row: DisplayRow }) {
  if (row.isTotal) return 'total-row'
  if (state.overBudgetRowIds.value.has(row.rowId)) return 'over-budget-row'
  return ''
}

function handleRowSelect(row: DisplayRow | null) {
  if (row && !row.isTotal) selectedRowId.value = row.rowId
}

function onCellChange(rowId: string, field: string, value: any) {
  state.updateCell(rowId, field, value)
}

function onAmtChange(row: DisplayRow, field: string) {
  if (row.isTotal) return
  state.updateCell(row.rowId, field, (row as any)[field])
}

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt('请输入工程项目名称', '新增工程', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addRow(value)
  } catch { /* cancelled */ }
}

function handleRemoveSelected() {
  if (selectedRowId.value) {
    state.removeRow(selectedRowId.value)
    selectedRowId.value = ''
  }
}

function handleExportCmd(cmd: string) {
  if (cmd === 'export-template') void ie.exportTemplate('H2-2')
  else if (cmd === 'export-data') void ie.exportData('H2-2')
  else if (cmd === 'import-data') ie.pickAndImport('H2-2')
}

function syncMortgageToDisclosure() {
  const rows = mapMortgagedDetailToRows(state.rows.value)
  if (!rows.length) {
    ElMessage.info('无抵押工程可同步')
    return
  }
  saveResponse(H2_LISTED_ITEM.mortgageRows, rows)
  const note = buildMortgageNoteText(rows)
  if (note) saveResponse(H2_LISTED_ITEM.noteMortgage, note)
  ElMessage.success(`已同步 ${rows.length} 项抵押在建工程至附注受限披露`)
}

function applyTpl(key: 'A' | 'B' | 'C') {
  state.applyConclusionTemplate(key)
}

function openReview(id: string) {
  openReviewDialog(id)
}

function ynLabel(v: string) {
  if (v === 'Y') return '是'
  if (v === 'N') return '否'
  return '—'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return '—'
  if (Math.abs(val) < 0.005) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.h2-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
.tab-toolbar {
  display: flex; justify-content: flex-end; align-items: center; gap: 8px;
  margin-bottom: 8px; flex-wrap: wrap;
}
.objective-alert :deep(.el-alert__content) { width: 100%; }
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 12px 16px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); flex-shrink: 0; }
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.segment-panel { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amt-cell { font-variant-numeric: tabular-nums; }
.amt-input { width: 100%; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums;
}
.over-budget { color: var(--el-color-danger); font-weight: 600; }
.summary-section { margin: 12px 0; }
.cas-hint { margin: 6px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.conclusion-actions { display: flex; gap: 6px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 8px 12px; }
.audit-note-card :deep(.el-card__body) { padding: 12px; }
.total-label { font-weight: 600; }
:deep(.total-row) { font-weight: 600; background-color: var(--el-fill-color-light) !important; }
:deep(.over-budget-row) { background-color: var(--el-color-danger-light-9) !important; }
</style>
