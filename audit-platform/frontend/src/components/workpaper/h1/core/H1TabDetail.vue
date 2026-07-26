<template>
  <div class="h1-tab-detail">
    <!-- 审计目标（对齐源模板认定表述） -->
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px">
      <template #title><span style="font-weight:600">一、审计目标</span></template>
      <ol style="margin:4px 0 0;padding-left:18px;line-height:1.55;font-size:12px">
        <li>资产负债表中记录的固定资产是存在的，且已记录于恰当的账户；</li>
        <li>所有应记录的固定资产均已记录，所有应当包括在财务报表中的相关披露均已包括；</li>
        <li>固定资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 四表取数来源面板（灰度关闭时 prefill 为 null，面板不渲染） -->
    <H1FourTableSourcePanel
      :prefill="fourTablePrefill"
      :is-readonly="isReadonly"
      :has-manual-data="rows.length > 0"
      @re-extract="onReExtractFromFourTable"
    />

    <!-- 本期增减 vs 序时账核对（只读告警，Req2；序时账不可用时显示"未取到"） -->
    <el-alert
      v-if="fourTablePrefill && movementReconcile.available"
      :type="movementReconcile.hasDiff ? 'warning' : 'success'"
      :closable="false" show-icon style="margin-bottom:12px"
    >
      <template #title>
        <span style="font-weight:600">本期增减 ↔ 序时账 1601 核对</span>
      </template>
      <div style="font-size:12px;line-height:1.6">
        {{ movementReconcile.message }}
        <span style="margin-left:8px;color:#909399">
          （明细增加 {{ fmtAmt(movementReconcile.detailIncrease) }} vs 序时账 {{ fmtAmt(movementReconcile.ledgerIncrease) }}；
          明细减少 {{ fmtAmt(movementReconcile.detailDecrease) }} vs 序时账 {{ fmtAmt(movementReconcile.ledgerDecrease) }}）
        </span>
      </div>
    </el-alert>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-2" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ rows.length }} 项</el-tag>
      <el-tag v-if="crossValidation.hasCostWarning" size="small" type="warning">
        原值审定≠H1-1（差 {{ fmtAmt(crossValidation.costDiff) }}）
      </el-tag>
      <el-tag v-if="crossValidation.hasDepWarning" size="small" type="warning">
        折旧审定≠H1-1（差 {{ fmtAmt(crossValidation.depDiff) }}）
      </el-tag>
      <el-tag v-else-if="rows.length && !crossValidation.hasCostWarning && !crossValidation.hasDepWarning" size="small" type="success">
        与 H1-1 勾稽一致
      </el-tag>
    </div>

    <!-- 引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 基础信息：分类/编号/年限/折旧方法 + 权属/闲置/抵押核对标志</div>
        <div class="guide-step"><span class="step-num">②</span> 原值：未审(期初+增−减=期末) → 期初调整/账项调整 → 审定自动</div>
        <div class="guide-step"><span class="step-num">③</span> 累计折旧：计提|其他增 / 处置|其他减；审定=未审+调整</div>
        <div class="guide-step"><span class="step-num">④</span> 减值准备：同折旧结构；净值=原值−折旧−减值（未审/审定）</div>
      </div>
    </div>

    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <div class="toolbar" v-if="!isReadonly">
      <el-button size="small" type="primary" @click="handleAddRow">+ 新增资产</el-button>
      <el-button size="small" @click="handleRemoveSelected" :disabled="!selectedRowId">删除选中</el-button>
      <span class="row-count">共 {{ rows.length }} 项 · 灰色虚线列为自动计算</span>
    </div>

    <!-- 区段1: 基础信息 + 核对标志 -->
    <div v-show="activeSegment === 'basic'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="分类" width="120" fixed>
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.category" size="small" filterable allow-create
              @change="onFieldChange(row, 'category')">
              <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产名称" min-width="140" fixed>
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="onFieldChange(row, 'name')" />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.assetNo" size="small" @change="onFieldChange(row, 'assetNo')" />
            <span v-else>{{ row.assetNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="入账日期" width="120">
          <template #default="{ row }">
            <el-date-picker v-if="!isReadonly" v-model="row.acquisitionDate" type="date" value-format="YYYY-MM-DD"
              size="small" style="width:100%" @change="onFieldChange(row, 'acquisitionDate')" />
            <span v-else>{{ row.acquisitionDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="年限(年)" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.usefulLife" :min="0" :max="99" :controls="false"
              size="small" @change="onFieldChange(row, 'usefulLife')" />
            <span v-else>{{ row.usefulLife }}</span>
          </template>
        </el-table-column>
        <el-table-column label="残值率%" width="80" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.salvageRate" :min="0" :max="99" :controls="false"
              size="small" @change="onFieldChange(row, 'salvageRate')" />
            <span v-else>{{ row.salvageRate }}%</span>
          </template>
        </el-table-column>
        <el-table-column label="折旧方法" width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.depMethod" size="small" @change="onFieldChange(row, 'depMethod')">
              <el-option label="直线法" value="直线法" />
              <el-option label="双倍余额递减" value="双倍余额递减" />
              <el-option label="年数总和" value="年数总和" />
              <el-option label="工作量法" value="工作量法" />
            </el-select>
            <span v-else>{{ row.depMethod }}</span>
          </template>
        </el-table-column>
        <el-table-column label="存放地点" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small" @change="onFieldChange(row, 'location')" />
            <span v-else>{{ row.location }}</span>
          </template>
        </el-table-column>
        <el-table-column label="使用部门" width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" @change="onFieldChange(row, 'department')" />
            <span v-else>{{ row.department }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否提足折旧" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isFullyDepreciated" size="small" clearable
              @change="onFieldChange(row, 'isFullyDepreciated')">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.isFullyDepreciated) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否闲置" width="90" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isIdle" size="small" clearable
              @change="onFieldChange(row, 'isIdle')">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.isIdle) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否有权属证明" width="120" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.hasTitleDoc" size="small" clearable
              @change="onFieldChange(row, 'hasTitleDoc')">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.hasTitleDoc) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否抵押受限" width="110" align="center">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.isMortgaged" size="small" clearable
              @change="onFieldChange(row, 'isMortgaged')">
              <el-option label="是" value="Y" /><el-option label="否" value="N" />
            </el-select>
            <span v-else>{{ ynLabel(row.isMortgaged) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段2: 原值变动（未审→调整→审定） -->
    <div v-show="activeSegment === 'cost'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="120" fixed />

        <el-table-column label="未审数" align="center">
          <el-table-column label="期初数" width="110" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="costBeginUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="金额" width="110" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costIncUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="增加方式" width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.costIncMethod" size="small" placeholder="购入等"
                  @change="onFieldChange(row, 'costIncMethod')" />
                <span v-else>{{ row.costIncMethod }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="本期减少" align="center">
            <el-table-column label="金额" width="110" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costDecUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="减少方式" width="100">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.costDecMethod" size="small" placeholder="处置等"
                  @change="onFieldChange(row, 'costDecMethod')" />
                <span v-else>{{ row.costDecMethod }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末=期初+增加−减少">{{ fmtAmt(row.costEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期初调整" width="100" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="costOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期增加" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="costAjeInc" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="costAjeDec" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="审定数" align="center">
          <el-table-column label="期初数" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期初审定=期初未审+期初调整">{{ fmtAmt(row.costBeginAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期增加" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="增加审定=未审增加+账项调整增加">{{ fmtAmt(row.costIncAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="本期减少" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="减少审定=未审减少+账项调整减少">{{ fmtAmt(row.costDecAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末数" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末审定=期初审定+增加审定−减少审定">{{ fmtAmt(row.costEndAud) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段3: 累计折旧 -->
    <div v-show="activeSegment === 'dep'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="110" fixed />

        <el-table-column label="未审数" align="center">
          <el-table-column label="期初数" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depBeginUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="本期计提" width="100" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depProvUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他增加" width="100" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depOtherIncUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="本期减少" align="center">
            <el-table-column label="处置" width="90" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depDispUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他减少" width="100" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depOtherDecUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="期末=期初+计提+其他增−处置−其他减">{{ fmtAmt(row.depEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期初调整" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="depOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column label="账项调整" align="center">
          <el-table-column label="本期计提" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeProv" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增加" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeOtherInc" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="处置" width="80" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeDisp" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeOtherDec" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="审定数" align="center">
          <el-table-column label="期初" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.depBeginAud) }}</span></template>
          </el-table-column>
          <el-table-column label="本期增加" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.depIncAud) }}</span></template>
          </el-table-column>
          <el-table-column label="本期减少" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.depDecAud) }}</span></template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.depEndAud) }}</span></template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <!-- 区段4: 减值 + 净值 -->
    <div v-show="activeSegment === 'impairment'" class="segment-panel">
      <el-table :data="rows" border stripe size="small" highlight-current-row
        @current-change="onRowSelect" max-height="520" class="detail-table">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="分类" width="100" fixed />
        <el-table-column prop="name" label="资产名称" min-width="110" fixed />

        <el-table-column label="减值准备·未审数" align="center">
          <el-table-column label="期初" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairBeginUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期计提" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairProvUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增加" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairOtherIncUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="处置" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairDispUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减少" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairOtherDecUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-cell">{{ fmtAmt(row.impairEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="期初调整" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="impairOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column label="账项调整" align="center">
          <el-table-column label="计提" width="85" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeProv" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增" width="85" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeOtherInc" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="处置" width="80" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeDisp" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减" width="85" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeOtherDec" :readonly="isReadonly" @change="onFieldChange" />
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
      </el-table>
      <p class="cas8-hint">提示：固定资产减值损失一经确认不得转回（CAS8）；「其他减少/处置」通常对应资产转出时冲销已提减值，而非损失转回。</p>
    </div>

    <!-- 合计 + 分类汇总 + 与 H1-1 勾稽 -->
    <div class="summary-section">
      <el-descriptions :column="4" border size="small" title="二、审计过程 — 合计（审定口径）">
        <el-descriptions-item label="原值期末审定">{{ fmtAmt(subtotals.costEndAud) }}</el-descriptions-item>
        <el-descriptions-item label="折旧期末审定">{{ fmtAmt(subtotals.depEndAud) }}</el-descriptions-item>
        <el-descriptions-item label="减值期末审定">{{ fmtAmt(subtotals.impairEndAud) }}</el-descriptions-item>
        <el-descriptions-item label="净值期末审定">{{ fmtAmt(subtotals.netEndAud) }}</el-descriptions-item>
      </el-descriptions>

      <el-table v-if="categorySubtotals.length" :data="categorySubtotals" border size="small"
        style="margin-top:10px" max-height="200">
        <el-table-column prop="category" label="其中：按类别" min-width="120" />
        <el-table-column prop="count" label="项数" width="70" align="center" />
        <el-table-column label="原值审定" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.costEndAud) }}</template>
        </el-table-column>
        <el-table-column label="折旧审定" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.depEndAud) }}</template>
        </el-table-column>
        <el-table-column label="减值审定" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.impairEndAud) }}</template>
        </el-table-column>
        <el-table-column label="净值审定" width="120" align="right">
          <template #default="{ row }">{{ fmtAmt(row.netEndAud) }}</template>
        </el-table-column>
      </el-table>

      <el-alert
        :type="crossValidation.hasCostWarning || crossValidation.hasDepWarning ? 'warning' : 'success'"
        :closable="false" style="margin-top:10px" show-icon
        :title="crossCheckTitle"
      />
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card" style="margin-bottom:12px">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="auditNoteText" type="textarea" :autosize="{ minRows: 5 }" :disabled="isReadonly"
        placeholder="可概述：（1）程序的测试情况、结果；（2）拟调整事项及其调整分录、未调整事项及其影响，审计范围受到限制情况及其影响。明细取数来源、与审定表(H1-1)勾稽差异及跟进。"
        @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
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
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
        placeholder="参考：A、未见异常。 B、除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。 C、由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。"
        @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（对齐致同源模板）</summary>
      <ul>
        <li>编制逻辑：未审 roll-forward（期初+增−减=期末）→ 记录期初调整与账项调整 → 审定自动勾稽 → 净值与 H1-1 交叉验证。</li>
        <li>原值期末审定 = 期初审定 + 增加审定 − 减少审定；折旧/减值同理（备抵类）。</li>
        <li>净值 = 原值 − 累计折旧 − 减值准备（分别计算未审净值与审定净值）。</li>
        <li>闲置标志为「是」的资产可带入 H1-4；权属/抵押可联动 H1-16/H1-17 与附注受限披露。</li>
        <li>本科目核算企业持有的固定资产原价；建造承包商临时设施及未单独计价的附带软件亦通过本科目核算。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabDetail — H1-2 固定资产、累计折旧及减值准备明细表
 * 对齐源模板 54 列：4 区段 Tab + 未审/期初调整/账项调整/审定 + 净值 + 核对标志 + 结论 A/B/C
 */
import { ref, computed, toRef, inject, onMounted, defineComponent, h } from 'vue'
import { ElMessageBox, ElInputNumber } from 'element-plus'
import {
  useH1Detail,
  type DetailRow,
  H1_2_CATEGORY_OPTIONS,
} from '../../composables/useH1Detail'
import GtIndexChip from '../../GtIndexChip.vue'
import H1FourTableSourcePanel from './H1FourTableSourcePanel.vue'
import {
  buildMovementReconcile,
  type H1FourTablePrefill,
} from '../../composables/h1FourTablePrefill'
import type { Ref } from 'vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const allResponsesRef = computed(() => props.allResponses)
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

// ─── 四表取数（主入口 GtH1FixedAssets provide）────────────────────────────────
const fourTablePrefillRef = inject<Ref<H1FourTablePrefill | null>>('h1FourTablePrefill', undefined)
const fourTablePrefill = computed(() => fourTablePrefillRef?.value ?? null)
const seedDetailFromFourTable = inject<(force?: boolean) => number>('h1SeedDetailFromFourTable', undefined)
function onReExtractFromFourTable() {
  seedDetailFromFourTable?.(true)
}

const NOTE_KEY = 'H1-2-audit-note'
const CONCLUSION_KEY = 'H1-2-audit-conclusion'
const auditNoteText = ref('')
const auditConclusionText = ref('')

function saveAuditNote() {
  if (props.isReadonly) return
  saveResponse(NOTE_KEY, auditNoteText.value)
  saveNote(auditNoteText.value)
}
function saveAuditConclusion() {
  if (props.isReadonly) return
  saveResponse(CONCLUSION_KEY, auditConclusionText.value)
  saveConclusion(auditConclusionText.value)
}

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNoteText.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusionText.value = c.remark
})

const activeSegment = ref('basic')
const segmentOptions = [
  { label: '基础信息', value: 'basic' },
  { label: '原值变动', value: 'cost' },
  { label: '累计折旧', value: 'dep' },
  { label: '减值与净值', value: 'impairment' },
]
const categoryOptions = [...H1_2_CATEGORY_OPTIONS]
const selectedRowId = ref<string | null>(null)

const {
  rows,
  subtotalRow: subtotals,
  crossValidation,
  categorySubtotals,
  addRow,
  removeRow,
  updateCell: updateField,
  saveNote,
  saveConclusion,
  applyConclusionTemplate,
} = useH1Detail(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

/** 本期原值增减 vs 序时账 1601 发生额（只读核对，Req2.4 不自动改数） */
const movementReconcile = computed(() =>
  buildMovementReconcile(rows.value, fourTablePrefill.value?.ledger_movement),
)

/** 金额输入子组件，减少模板重复 */
const AmtInput = defineComponent({
  name: 'H1DetailAmtInput',
  props: {
    row: { type: Object as () => DetailRow, required: true },
    field: { type: String, required: true },
    readonly: { type: Boolean, default: false },
  },
  emits: ['change'],
  setup(p, { emit }) {
    return () => {
      if (p.readonly) {
        return h('span', { class: 'amount-cell' }, fmtAmt((p.row as any)[p.field]))
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

function onRowSelect(row: DetailRow | null) {
  selectedRowId.value = row?.rowId ?? null
}

async function handleAddRow() {
  const { value: name } = await ElMessageBox.prompt('请输入资产名称', '新增固定资产', {
    confirmButtonText: '确定',
    cancelButtonText: '取消',
    inputPlaceholder: '如：XX办公楼、XX生产设备',
  })
  if (name) addRow(name)
}

function handleRemoveSelected() {
  if (selectedRowId.value) {
    removeRow(selectedRowId.value)
    selectedRowId.value = null
  }
}

function onFieldChange(row: DetailRow, field: string) {
  updateField(row.rowId, field as keyof DetailRow, (row as any)[field])
}

function applyTpl(key: 'A' | 'B' | 'C') {
  applyConclusionTemplate(key)
  auditConclusionText.value = (
    { A: '未见异常。',
      B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
      C: '由于存在以下重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。' }
  )[key]
}

function ynLabel(v: string) {
  if (v === 'Y') return '是'
  if (v === 'N') return '否'
  return '—'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || !Number.isFinite(val)) return '-'
  if (Math.abs(val) < 0.005) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const crossCheckTitle = computed(() => {
  const cv = crossValidation.value
  if (!rows.value.length) return '尚未录入明细；录入后将与 H1-1 审定表自动勾稽。'
  if (cv.hasCostWarning || cv.hasDepWarning) {
    const parts: string[] = []
    if (cv.hasCostWarning) {
      parts.push(`原值期末审定 ${fmtAmt(cv.costTotal)} ≠ H1-1 ${fmtAmt(cv.costFromH1)}（差额 ${fmtAmt(cv.costDiff)}）`)
    }
    if (cv.hasDepWarning) {
      parts.push(`折旧期末审定 ${fmtAmt(cv.depTotal)} ≠ H1-1 ${fmtAmt(cv.depFromH1)}（差额 ${fmtAmt(cv.depDiff)}）`)
    }
    return parts.join('；')
  }
  return `与 H1-1 勾稽一致：原值 ${fmtAmt(cv.costTotal)} / 折旧 ${fmtAmt(cv.depTotal)} / 减值 ${fmtAmt(cv.impairTotal)}`
})
</script>

<style scoped>
.h1-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }
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
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; }
.step-num { font-weight: 700; color: var(--el-color-primary); }
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }
.segment-panel { margin-bottom: 12px; }
.detail-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color); cursor: help;
  font-variant-numeric: tabular-nums; color: var(--el-text-color-regular);
}
.summary-section { margin: 12px 0; }
.cas8-hint { margin: 6px 0 0; font-size: 12px; color: var(--el-text-color-secondary); }
.conclusion-header { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.conclusion-actions { display: flex; gap: 6px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.audit-note-card :deep(.el-card__header) { padding: 8px 12px; }
.audit-note-card :deep(.el-card__body) { padding: 12px; }
</style>
