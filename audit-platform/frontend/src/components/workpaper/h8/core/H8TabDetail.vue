<template>
  <div class="h8-tab-detail">
    <!-- 审计目标（对齐源模板认定表述） -->
    <el-alert type="info" :closable="false" class="objective-alert" show-icon>
      <template #title><span class="obj-title">一、审计目标</span></template>
      <ol class="obj-list">
        <li>确定资产负债表中记录的使用权资产是存在的；</li>
        <li>确定所有应当记录的使用权资产均已记录；</li>
        <li>确定记录的使用权资产由被审计单位拥有或控制；</li>
        <li>确定使用权资产以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录；</li>
        <li>确定使用权资产已按照企业会计准则的规定在财务报表中作出恰当列报。</li>
      </ol>
    </el-alert>

    <div class="methodology-context">
      <p>
        源模板将「原值 / 累计折旧 / 减值准备」横排三页（共58列）。本表按区段拆分；
        审定 = 未审 + 期初调整/账项调整。CAS21：入账值 = H9租赁负债初始 + 初始直接费用 − 租赁激励。
        CAS8：使用权资产减值一经确认不得转回。
      </p>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 基础：类别/合同号/起止日 + CAS21 初始计量（与 H9 勾稽）</div>
        <div class="guide-step"><span class="step-num">②</span> 原值：期初 + 租入/重估/其他增 − 转租融资/转让待售/其他减 → 调整 → 审定</div>
        <div class="guide-step"><span class="step-num">③</span> 累计折旧：本期计提|其他增 / 转租融资|转让待售|其他减；审定自动</div>
        <div class="guide-step"><span class="step-num">④</span> 减值+净值：同折旧结构；净值=原值−折旧−减值（未审/审定）</div>
      </div>
    </div>

    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-2" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ rows.length }} 笔合同</el-tag>
      <el-tag size="small" type="success">原值审定 {{ fmtAmt(subtotalRow.costEndAud) }}</el-tag>
      <el-tag size="small">净值审定 {{ fmtAmt(subtotalRow.netEndAud) }}</el-tag>
      <el-tag
        v-if="shortTermCandidates.length"
        size="small"
        type="warning"
        title="租赁期≤12月，请确认是否应转入 H8-13 简化处理"
      >
        疑似短期 {{ shortTermCandidates.length }}
      </el-tag>
      <el-tag v-if="crossValidation.hasCostWarning" size="small" type="warning">
        原值≠H8-1（差 {{ fmtAmt(crossValidation.costDiff) }}）
      </el-tag>
      <el-tag v-if="crossValidation.hasDepWarning" size="small" type="warning">
        折旧≠H8-1（差 {{ fmtAmt(crossValidation.depDiff) }}）
      </el-tag>
      <el-tag v-if="crossValidation.hasImpairWarning" size="small" type="warning">
        减值≠H8-1（差 {{ fmtAmt(crossValidation.impairDiff) }}）
      </el-tag>
      <el-tag v-if="crossValidation.hasNetWarning && !crossValidation.hasCostWarning" size="small" type="warning">
        净值≠H8-1（差 {{ fmtAmt(crossValidation.netDiff) }}）
      </el-tag>
      <el-tag
        v-else-if="rows.length && !crossValidation.isEmpty && crossValidation.isConsistent"
        size="small"
        type="success"
      >
        与 H8-1 勾稽一致
      </el-tag>
    </div>

    <div class="segment-bar">
      <el-segmented v-model="activeSegment" :options="segmentOptions" size="default" />
      <div v-if="activeSegment !== 'basic'" class="col-pref-bar">
        <span class="col-pref-label">列：</span>
        <el-radio-group
          :model-value="activePreset === 'custom' ? '' : activePreset"
          size="small"
          @change="(v: string | number | boolean | undefined) => applyPreset(String(v) as 'core' | 'full')"
        >
          <el-radio-button value="core">核心</el-radio-button>
          <el-radio-button value="full">完整</el-radio-button>
        </el-radio-group>
        <el-popover placement="bottom-end" :width="280" trigger="click">
          <template #reference>
            <el-button size="small" text type="primary">列设置</el-button>
          </template>
          <div class="col-pref-pop">
            <div v-for="g in allGroups" :key="g" class="col-pref-row">
              <el-checkbox
                :model-value="isGroupVisible(g)"
                @change="(v: boolean | string | number) => toggleGroup(g, !!v)"
              >
                {{ groupLabels[g] }}
              </el-checkbox>
            </div>
            <p class="col-pref-hint">核心＝未审+审定；完整＝含期初调整与账项调整细列。偏好保存在本机。</p>
          </div>
        </el-popover>
      </div>
      <div class="bar-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRow">+ 新增合同</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="danger"
          plain
          :disabled="!selectedRowId"
          @click="handleDeleteSelected"
        >删除选中</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          @click="handleSeedCost"
        >用入账值填本期租入</el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          @click="handlePullH88"
        >从 H8-8 回填计提</el-button>
        <el-dropdown size="small" @command="handleExportCommand">
          <el-button size="small" :loading="ieBusy">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="export-template">导出模板</el-dropdown-item>
              <el-dropdown-item command="export-data">导出数据</el-dropdown-item>
              <el-dropdown-item command="import-data">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
        <el-button size="small" type="primary" plain @click="$emit('open-ai', 'detail')">AI 辅助</el-button>
        <el-button size="small" @click="$emit('open-review', 'detail')">复核</el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-1')">→ H8-1</el-button>
        <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-13')">→ H8-13</el-button>
      </div>
    </div>

    <!-- ① 基础 + 初始计量 -->
    <div v-show="activeSegment === 'basic'" class="segment-panel">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        highlight-current-row
        max-height="520"
        class="detail-table"
        show-summary
        :summary-method="sumBasic"
        @current-change="onRowSelect"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column label="类别" width="120" fixed>
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              v-model="row.category"
              size="small"
              filterable
              allow-create
              @change="onFieldChange(row, 'category')"
            >
              <el-option v-for="c in categoryOptions" :key="c" :label="c" :value="c" />
            </el-select>
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="租赁合同号" min-width="130" fixed>
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.contractNo"
              size="small"
              @change="onFieldChange(row, 'contractNo')"
            />
            <span v-else>{{ row.contractNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="H9" width="64" align="center">
          <template #default="{ row }">
            <GtIndexChip
              v-if="row.contractNo"
              value="H9-2"
              :context-project-id="projectId"
              context="H9租赁负债明细对应行"
              :prevent-navigate="true"
              @click="emit('navigate-sheet', 'H9-2')"
            />
          </template>
        </el-table-column>
        <el-table-column label="资产名称" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.assetName"
              size="small"
              @change="onFieldChange(row, 'assetName')"
            />
            <span v-else>{{ row.assetName }}</span>
          </template>
        </el-table-column>
        <el-table-column label="资产编号" width="100">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.assetNo"
              size="small"
              @change="onFieldChange(row, 'assetNo')"
            />
            <span v-else>{{ row.assetNo }}</span>
          </template>
        </el-table-column>
        <el-table-column label="出租方" min-width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.lessor"
              size="small"
              @change="onFieldChange(row, 'lessor')"
            />
            <span v-else>{{ row.lessor }}</span>
          </template>
        </el-table-column>
        <el-table-column label="起始日" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.startDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="onFieldChange(row, 'startDate')"
            />
            <span v-else>{{ row.startDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="到期日" width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.endDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="onFieldChange(row, 'endDate')"
            />
            <span v-else>{{ row.endDate }}</span>
          </template>
        </el-table-column>
        <el-table-column label="租赁期(月)" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="leaseTermMonths" :readonly="isReadonly" :precision="0" @change="onFieldChange" />
          </template>
        </el-table-column>
        <el-table-column label="H9初始计量" width="120" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="h9InitialAmount" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>
        <el-table-column label="初始直接费用" width="110" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="directCost" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>
        <el-table-column label="租赁激励" width="100" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="incentive" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>
        <el-table-column label="入账值(CAS21)" width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="H9初始+直接费用−激励；若未填则取原值审定期末">{{ fmtAmt(row.initialAmount) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ② 原值变动 -->
    <div v-show="activeSegment === 'cost'" class="segment-panel">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        highlight-current-row
        max-height="520"
        class="detail-table"
        show-summary
        :summary-method="sumCost"
        @current-change="onRowSelect"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="类别" width="100" fixed />
        <el-table-column prop="contractNo" label="合同号" width="110" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="100" fixed />

        <el-table-column v-if="isGroupVisible('unadj')" label="未审数" align="center">
          <el-table-column label="期初数" width="100" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="costBeginUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期增加" align="center">
            <el-table-column label="本期租入" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costIncLease" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="负债重估" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costIncReval" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他增加" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costIncOther" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="本期减少" align="center">
            <el-table-column label="转租融资" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costDecSublease" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="转让/待售" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他减少" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costDecOther" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-value" title="期初+三项增−三项减">{{ fmtAmt(row.costEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('openAdj')" label="期初调整" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="costOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('aje')" label="账项调整" align="center">
          <el-table-column label="增加" align="center">
            <el-table-column label="租入" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeIncLease" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="重估" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeIncReval" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeIncOther" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="减少" align="center">
            <el-table-column label="转租" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeDecSublease" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="转让" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他" width="80" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="costAjeDecOther" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('audited')" label="审定数" align="center">
          <el-table-column label="期初" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value" title="未审期初+期初调整">{{ fmtAmt(row.costBeginAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="增加" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.costIncAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减少" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.costDecAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-value" title="审定期初+增−减">{{ fmtAmt(row.costEndAud) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
    </div>

    <!-- ③ 累计折旧 -->
    <div v-show="activeSegment === 'dep'" class="segment-panel">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        highlight-current-row
        max-height="520"
        class="detail-table"
        show-summary
        :summary-method="sumDep"
        @current-change="onRowSelect"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="类别" width="100" fixed />
        <el-table-column prop="contractNo" label="合同号" width="110" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="100" fixed />

        <el-table-column v-if="isGroupVisible('unadj')" label="未审数" align="center">
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
            <el-table-column label="转租融资" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depDecSublease" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="转让/待售" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
            <el-table-column label="其他减少" width="96" align="right">
              <template #default="{ row }">
                <AmtInput :row="row" field="depOtherDecUnadj" :readonly="isReadonly" @change="onFieldChange" />
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.depEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('openAdj')" label="期初调整" width="90" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="depOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('aje')" label="账项调整" align="center">
          <el-table-column label="计提" width="88" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeProv" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增" width="88" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeOtherInc" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="转租减" width="88" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeDecSublease" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="转让减" width="88" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减" width="88" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="depAjeOtherDec" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('audited')" label="审定数" align="center">
          <el-table-column label="期初" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.depBeginAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="增加" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.depIncAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="减少" width="96" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.depDecAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末" width="100" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.depEndAud) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
      </el-table>
      <p class="seg-hint">提示：折旧自租赁期开始日或次月起计提，须在审计说明中披露；可与 H8-8 折旧测算交叉核对。</p>
    </div>

    <!-- ④ 减值 + 净值 + 变更 -->
    <div v-show="activeSegment === 'impair'" class="segment-panel">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        highlight-current-row
        max-height="480"
        class="detail-table"
        show-summary
        :summary-method="sumImpair"
        @current-change="onRowSelect"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="类别" width="100" fixed />
        <el-table-column prop="contractNo" label="合同号" width="110" fixed />
        <el-table-column prop="assetName" label="资产名称" min-width="100" fixed />

        <el-table-column v-if="isGroupVisible('unadj')" label="减值准备·未审" align="center">
          <el-table-column label="期初" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairBeginUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="本期计提" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairProvUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增" width="86" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairOtherIncUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="转租减" width="86" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairDecSublease" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="转让减" width="86" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他减" width="86" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairOtherDecUnadj" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="期末" width="90" align="right">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtAmt(row.impairEndUnadj) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('openAdj')" label="期初调整" width="86" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="impairOpenAdj" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('aje')" label="账项调整" align="center">
          <el-table-column label="计提" width="80" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeProv" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="其他增" width="80" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeOtherInc" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
          <el-table-column label="减少合计*" width="90" align="right">
            <template #default="{ row }">
              <AmtInput :row="row" field="impairAjeDecDisposal" :readonly="isReadonly" @change="onFieldChange" />
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('audited')" label="减值审定期末" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-value">{{ fmtAmt(row.impairEndAud) }}</span>
          </template>
        </el-table-column>

        <el-table-column v-if="isGroupVisible('audited')" label="审定净值" align="center">
          <el-table-column label="期初净值" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-value" title="审定原值期初−折旧期初−减值期初">{{ fmtAmt(row.netBeginAud) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="期末净值" width="110" align="right">
            <template #default="{ row }">
              <span class="formula-value" title="审定原值期末−折旧期末−减值期末">{{ fmtAmt(row.netEndAud) }}</span>
            </template>
          </el-table-column>
        </el-table-column>

        <el-table-column label="变更调整额" width="110" align="right">
          <template #default="{ row }">
            <AmtInput :row="row" field="modificationAmount" :readonly="isReadonly" @change="onFieldChange" />
          </template>
        </el-table-column>
        <el-table-column label="终止日" width="110">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.terminationDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="onFieldChange(row, 'terminationDate')"
            />
            <span v-else>{{ row.terminationDate || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              @change="onFieldChange(row, 'remark')"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
      </el-table>
      <p class="seg-hint warn">
        *账项调整「减少合计」写入转让减列；转租/其他减可在未审区填写。CAS8：减值一经确认不得转回——减少仅可为处置/转租结转。
      </p>
    </div>

    <div class="stat-bar">
      <span>合同 {{ rows.length }} 笔</span>
      <span>入账值合计 {{ fmtAmt(initialTotal) }}</span>
      <span>原值审定 {{ fmtAmt(subtotalRow.costEndAud) }}</span>
      <span>折旧审定 {{ fmtAmt(subtotalRow.depEndAud) }}</span>
      <span>净值审定 {{ fmtAmt(subtotalRow.netEndAud) }}</span>
    </div>

    <el-card v-if="categorySubtotals.length" shadow="never" class="cat-card">
      <template #header><span class="card-title">按类别小计（对齐源模板「其中」）</span></template>
      <el-table :data="categorySubtotals" border size="small" max-height="200">
        <el-table-column prop="category" label="类别" min-width="120" />
        <el-table-column prop="count" label="笔数" width="70" align="center" />
        <el-table-column label="原值审定" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.costEndAud) }}</template>
        </el-table-column>
        <el-table-column label="折旧审定" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.depEndAud) }}</template>
        </el-table-column>
        <el-table-column label="净值审定" width="130" align="right">
          <template #default="{ row }">{{ fmtAmt(row.netEndAud) }}</template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 4 }"
        placeholder="说明抽样范围、增减变动核查、与 H8-1/H8-8/H9 勾稽情况…"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span class="card-title">四、审计结论</span></template>
      <el-input
        type="textarea"
        :model-value="auditConclusion"
        :disabled="isReadonly"
        :autosize="{ minRows: 3 }"
        placeholder="使用权资产原值/累计折旧/减值及净值在所有重大方面是否公允反映…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（对照源模板）</summary>
      <ul>
        <li>源表 58 列横排三页；本界面按「基础 / 原值 / 折旧 / 减值净值」四区段录入，同一行数据全程同步。</li>
        <li>原值增加细分：本期租入、租赁负债重估调整、其他增加；减少：转租转为融资租赁、转让或持有待售、其他减少。</li>
        <li>入账值 = H9 初始 + 直接费用 − 激励；旧数据自动迁入「原值期初」。</li>
        <li>审定净值 = 审定原值 − 审定累计折旧 − 审定减值；可与 H8-1 交叉验证。</li>
        <li>明细行按合同登记，供 H8-4/5/7/8/10/12 带入；短期/低价值租赁走 H8-13，不进本表。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabDetail.vue — H8-2 明细表（源模板58列 → 4区段Tab）
 */
import { ref, toRef, watch, computed, defineComponent, h, inject } from 'vue'
import { ElMessageBox, ElInputNumber, ElMessage } from 'element-plus'
import {
  useH8Detail,
  H8_2_CATEGORY_OPTIONS,
  H8_DETAIL_SEGMENTS,
  type H8DetailRow,
} from '../../composables/useH8Detail'
import { useH8ImportExport } from '../../composables/useH8ImportExport'
import { useH8DetailColumnPrefs } from '../../composables/useH8DetailColumnPrefs'
import GtIndexChip from '../../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'open-ai', section: string): void
  (e: 'open-review', section: string): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const activeSegment = ref('basic')
const segmentOptions = H8_DETAIL_SEGMENTS
const categoryOptions = [...H8_2_CATEGORY_OPTIONS]
const selectedRowId = ref<string | null>(null)

const {
  activePreset,
  groupLabels,
  allGroups,
  isGroupVisible,
  toggleGroup,
  applyPreset,
} = useH8DetailColumnPrefs()

const AUDIT_NOTE_KEY = 'H8-detail-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-detail-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function _hydrateAudit() {
  const n = props.allResponses.get(AUDIT_NOTE_KEY)
  if (n?.remark != null) auditNote.value = n.remark
  const c = props.allResponses.get(AUDIT_CONCLUSION_KEY)
  if (c?.remark != null) auditConclusion.value = c.remark
}
_hydrateAudit()
watch(() => props.allResponses, _hydrateAudit)

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  emit('save', AUDIT_NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  emit('save', AUDIT_CONCLUSION_KEY, val)
}

const {
  rows,
  subtotalRow,
  initialTotal,
  categorySubtotals,
  crossValidation,
  shortTermCandidates,
  addRow,
  deleteRow,
  updateCell,
  load,
  pullDepFromH88,
  seedCostIncFromInitial,
} = useH8Detail({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isExporting, isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'H8-2',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-2'])
  else if (cmd === 'export-data') await exportData(['H8-2'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

function handlePullH88() {
  const r = pullDepFromH88()
  if (r.updated) ElMessage.success(r.message)
  else ElMessage.info(r.message)
  if (r.unmatched.length) {
    ElMessage.warning(`未匹配合同：${r.unmatched.slice(0, 5).join('、')}${r.unmatched.length > 5 ? '…' : ''}`)
  }
}

function handleSeedCost() {
  const r = seedCostIncFromInitial()
  if (r.updated) ElMessage.success(r.message)
  else ElMessage.info(r.message)
}

function fmtAmt(v: number): string {
  if (!v) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const AmtInput = defineComponent({
  name: 'H8DetailAmtInput',
  props: {
    row: { type: Object as () => H8DetailRow, required: true },
    field: { type: String, required: true },
    readonly: { type: Boolean, default: false },
    precision: { type: Number, default: 2 },
  },
  emits: ['change'],
  setup(p, { emit: localEmit }) {
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
        precision: p.precision,
        style: { width: '100%' },
        onChange: () => localEmit('change', p.row, p.field),
      })
    }
  },
})

function onRowSelect(row: H8DetailRow | null) {
  selectedRowId.value = row?.rowId ?? null
}

function onFieldChange(row: H8DetailRow, field: string) {
  updateCell(row.rowId, field, (row as any)[field])
}

async function handleAddRow() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增明细行', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) {
    addRow(value)
    ElMessage.info('短期/低价值租赁请走 H8-13，勿重复登记本表')
  }
}

function handleDeleteSelected() {
  if (!selectedRowId.value) return
  deleteRow(selectedRowId.value)
  selectedRowId.value = null
}

function sumBasic({ columns }: any) {
  return columns.map((_: any, idx: number) => {
    if (idx === 0) return `合计（${rows.value.length}）`
    if (idx === 13) return fmtAmt(initialTotal.value)
    return ''
  })
}

function sumCost({ columns }: any) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.label === '期末数' || col.label === '期末') return fmtAmt(subtotalRow.value.costEndAud)
    return ''
  })
}

function sumDep({ columns }: any) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.label === '期末' || col.label === '期末数') return fmtAmt(subtotalRow.value.depEndAud)
    return ''
  })
}

function sumImpair({ columns }: any) {
  return columns.map((col: any, idx: number) => {
    if (idx === 0) return '合计'
    if (col.label === '减值审定期末') return fmtAmt(subtotalRow.value.impairEndAud)
    if (col.label === '期末净值') return fmtAmt(subtotalRow.value.netEndAud)
    return ''
  })
}</script>

<style scoped>
.h8-tab-detail { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.obj-title { font-weight: 600; }
.obj-list {
  margin: 4px 0 0;
  padding-left: 18px;
  line-height: 1.55;
  font-size: 12px;
}

.methodology-context {
  background: #fffbeb;
  border-left: 4px solid #f59e0b;
  padding: 10px 14px;
  border-radius: 0 6px 6px 0;
  margin-bottom: 12px;
  font-size: 12px;
  color: #92400e;
}
.methodology-context p { margin: 0; }

.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px;
  padding: 12px 14px;
  margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 12px; line-height: 1.4; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 18px; }

.h8-tab-toolbar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}

.segment-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}
.col-pref-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
  min-width: 200px;
}
.col-pref-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.col-pref-pop { display: flex; flex-direction: column; gap: 4px; }
.col-pref-row { line-height: 1.6; }
.col-pref-hint {
  margin: 8px 0 0;
  font-size: 11px;
  color: var(--el-text-color-secondary);
  line-height: 1.4;
}
.bar-actions { display: flex; gap: 6px; flex-wrap: wrap; }

.segment-panel { margin-bottom: 8px; }
.detail-table { font-size: var(--wp-font-size, 13px); margin-bottom: 8px; }
.detail-table :deep(.formula-col) { background: #f0f9ff; }
.formula-value {
  border-bottom: 1px dashed #409eff;
  cursor: help;
  color: #409eff;
}
.amount-cell { font-variant-numeric: tabular-nums; }

.seg-hint {
  margin: 0 0 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.seg-hint.warn { color: #b45309; }

.stat-bar {
  display: flex;
  gap: 20px;
  padding: 10px 0;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  flex-wrap: wrap;
  margin-bottom: 12px;
}

.cat-card,
.audit-note-card,
.audit-conclusion-card { margin-bottom: 12px; }
.card-title { font-weight: 600; }

.compile-hint { margin-top: 8px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
