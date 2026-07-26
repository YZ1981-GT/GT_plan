<template>
  <div class="h3-tab-detail-cost">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（成本模式）</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产明细表（成本模式），分「基本信息 / 增减转换 / 折旧减值」三区段，行数据跨区段同步。</p>
        <p>2. 期末原值 = 期初 + 本期增加 − 本期减少 + 转入 − 转出；折旧期末 = 期初 + 计提 − 转回；净值 = 期末原值 − 折旧期末 − 减值期末。</p>
        <p>3. 明细合计应与 H3-1 审定表（成本模式）原值审定数勾稽一致，差异时顶部提示红色。</p>
        <p>4. 增减方式如涉及 H1/H2 互转，需同步填写 H3-6 互转审核表，并在凭证号列注明转账凭证。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：逐项核实投资性房地产（成本模式）的原值、累计折旧、减值准备、净值及增减变动的真实、准确与完整，支持 H3-1 审定表。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <span class="chip-wrap"><GtIndexChip value="wp:H3-2" :context-project-id="projectId" /></span>
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag size="small" :type="crossValidationDiff === 0 ? 'success' : 'danger'">
        {{ crossValidationDiff === 0 ? '已与H3-1勾稽' : `与H3-1差异 ${fmtNum(crossValidationDiff)}` }}
      </el-tag>
      <el-tag
        v-if="unmatchedCategory.unmatchedCount > 0"
        size="small"
        type="warning"
      >
        非标准类别 {{ unmatchedCategory.unmatchedCount }} 行 / {{ fmtNum(unmatchedCategory.unmatchedEnd) }}
      </el-tag>
    </div>

    <!-- 汇总看板 -->
    <div class="summary-strip">
      <div class="summary-card cost">
        <div class="sc-label">期末原值</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.costEnd) }}</div>
      </div>
      <div class="summary-card dep">
        <div class="sc-label">折旧期末</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.accDepEnd) }}</div>
      </div>
      <div class="summary-card imp">
        <div class="sc-label">减值期末</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.impairmentEnd) }}</div>
      </div>
      <div class="summary-card net">
        <div class="sc-label">净值合计</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.netValue) }}</div>
      </div>
      <div class="summary-card inc">
        <div class="sc-label">本期增加</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.costIncrease) }}</div>
      </div>
      <div class="summary-card dec">
        <div class="sc-label">本期减少</div>
        <div class="sc-value">{{ fmtNum(subtotalRow.costDecrease) }}</div>
      </div>
      <div class="summary-card restrict">
        <div class="sc-label">权属受限</div>
        <div class="sc-value">{{ restrictedCount }} 项</div>
      </div>
      <div class="summary-card mortgage">
        <div class="sc-label">抵押/质押</div>
        <div class="sc-value">{{ mortgagedCount }} 项</div>
      </div>
    </div>

    <!-- 分类小计 -->
    <el-table
      v-if="categorySubtotals.length"
      :data="categorySubtotals"
      border
      size="small"
      class="category-table"
    >
      <el-table-column prop="category" label="资产类别小计" min-width="140" />
      <el-table-column prop="count" label="项数" width="70" align="center" />
      <el-table-column label="期末原值" min-width="120" align="right">
        <template #default="{ row }">{{ fmtNum(row.costEnd) }}</template>
      </el-table-column>
      <el-table-column label="折旧期末" min-width="110" align="right">
        <template #default="{ row }">{{ fmtNum(row.accDepEnd) }}</template>
      </el-table-column>
      <el-table-column label="减值期末" min-width="110" align="right">
        <template #default="{ row }">{{ fmtNum(row.impairmentEnd) }}</template>
      </el-table-column>
      <el-table-column label="净值" min-width="120" align="right">
        <template #default="{ row }">{{ fmtNum(row.netValue) }}</template>
      </el-table-column>
    </el-table>

    <!-- 区段Tab切换 -->
    <el-segmented v-model="activeSegment" :options="segmentOptions" class="segment-bar" />

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddAsset">
        + 添加资产行
      </el-button>
      <el-dropdown size="small" class="export-dropdown" trigger="click">
        <el-button size="small">导入导出 ▾</el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="doExportTemplate">导出空白模板</el-dropdown-item>
            <el-dropdown-item @click="doExportData">导出当前数据</el-dropdown-item>
            <el-dropdown-item :divided="true" @click="doImportData">从Excel导入</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display: none" @change="onFileSelected" />
    </div>

    <!-- ───────────── 区段1：基本信息 ───────────── -->
    <template v-if="activeSegment === '基本信息'">
      <div class="segment-header cost-header">一、基本信息</div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryBasic">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }">
            <span class="seq-cell">{{ row.seq }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="150" fixed>
          <template #default="{ row }">
            <el-input v-model="row.assetName" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="assetType" label="类别" min-width="120">
          <template #default="{ row }">
            <el-select v-model="row.assetType" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option v-for="t in ASSET_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="location" label="位置/地址" min-width="180">
          <template #default="{ row }">
            <el-input v-model="row.location" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="area" label="面积(㎡)" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.area" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="acquireDate" label="取得日期" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.acquireDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="originalCost" label="入账原值" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.originalCost" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="costBegin" label="原值期初" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.costBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column label="期末原值" min-width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少+转入-转出（在增减转换区段录入）">{{ fmtNum(row.costEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="remark" label="备注" min-width="160">
          <template #default="{ row }">
            <el-input v-model="row.remark" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="ownershipRestricted" label="权属受限" min-width="90" align="center">
          <template #default="{ row }">
            <el-select v-model="row.ownershipRestricted" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="—" value="" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="mortgaged" label="抵押/质押" min-width="90" align="center">
          <template #default="{ row }">
            <el-select v-model="row.mortgaged" size="small" :disabled="isReadonly" style="width:100%" @change="onCellChange(row)">
              <el-option label="是" value="是" />
              <el-option label="否" value="否" />
              <el-option label="—" value="" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text :disabled="isReadonly" @click="handleRemoveRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ───────────── 区段2：增减转换 ───────────── -->
    <template v-if="activeSegment === '增减转换'">
      <div class="segment-header change-header">二、增减转换（原值变动明细）</div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryChange">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
        <el-table-column prop="assetType" label="类别" min-width="100" fixed />
        <el-table-column prop="changeDate" label="增减日期" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.changeDate" size="small" placeholder="YYYY-MM-DD" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="changeType" label="增减方式" min-width="130">
          <template #default="{ row }">
            <el-select v-model="row.changeType" size="small" :disabled="isReadonly" style="width:100%" allow-create filterable @change="onCellChange(row)">
              <el-option v-for="t in CHANGE_TYPE_OPTIONS" :key="t" :label="t" :value="t" />
            </el-select>
          </template>
        </el-table-column>
        <el-table-column prop="voucherNo" label="凭证号" min-width="110">
          <template #default="{ row }">
            <el-input v-model="row.voucherNo" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="counterAccount" label="对方科目" min-width="140">
          <template #default="{ row }">
            <el-input v-model="row.counterAccount" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="costIncrease" label="本期增加" min-width="110" align="right" class-name="inc-col">
          <template #default="{ row }">
            <el-input v-model.number="row.costIncrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="costDecrease" label="本期减少" min-width="110" align="right" class-name="dec-col">
          <template #default="{ row }">
            <el-input v-model.number="row.costDecrease" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferIn" label="转入" min-width="100" align="right" class-name="inc-col">
          <template #default="{ row }">
            <el-input v-model.number="row.transferIn" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="transferOut" label="转出" min-width="100" align="right" class-name="dec-col">
          <template #default="{ row }">
            <el-input v-model.number="row.transferOut" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="costBegin" label="期初原值" min-width="110" align="right" />
        <el-table-column label="期末原值" min-width="120" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少+转入-转出">{{ fmtNum(row.costEnd) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text :disabled="isReadonly" @click="handleRemoveRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ───────────── 区段3：折旧减值 ───────────── -->
    <template v-if="activeSegment === '折旧减值'">
      <div class="segment-header dep-header">三、折旧与减值</div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryDep">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="140" fixed />
        <el-table-column prop="assetType" label="类别" min-width="100" fixed />
        <!-- 折旧列组 -->
        <el-table-column label="累计折旧" align="center">
          <el-table-column prop="accDepBegin" label="期初" min-width="100" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.accDepBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="depProvision" label="本期计提" min-width="100" align="right" class-name="inc-col">
            <template #default="{ row }">
              <el-input v-model.number="row.depProvision" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="depReversal" label="转回/处置" min-width="100" align="right" class-name="dec-col">
            <template #default="{ row }">
              <el-input v-model.number="row.depReversal" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="期初+计提-转回">{{ fmtNum(row.accDepEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 减值列组 -->
        <el-table-column label="减值准备" align="center">
          <el-table-column prop="impairmentBegin" label="期初" min-width="100" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.impairmentBegin" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="impairmentProvision" label="本期计提" min-width="100" align="right" class-name="inc-col">
            <template #default="{ row }">
              <el-input v-model.number="row.impairmentProvision" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="impairmentReversal" label="转回/处置" min-width="100" align="right" class-name="dec-col">
            <template #default="{ row }">
              <el-input v-model.number="row.impairmentReversal" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="期末" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="期初+计提-转回">{{ fmtNum(row.impairmentEnd) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <!-- 净值 -->
        <el-table-column label="期末净值" min-width="120" align="right" class-name="formula-col net-col">
          <template #default="{ row }">
            <span class="formula-value net-value" title="期末原值-折旧期末-减值期末">{{ fmtNum(row.netValue) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="60" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="danger" text :disabled="isReadonly" @click="handleRemoveRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- ───────────── 区段4：审定调整 ───────────── -->
    <template v-if="activeSegment === '审定调整'">
      <div class="segment-header audit-header">四、审定调整（未审 / AJE / RJE / 审定）</div>
      <div class="toolbar-inline">
        <el-button size="small" :disabled="isReadonly" @click="handleSeedUnadj">从账面期末带入未审数</el-button>
        <span class="hint-text">审定数 = 未审 + AJE + RJE；审定净值 = 原值审定 − 折旧审定 − 减值审定</span>
      </div>
      <el-table :data="rows" border size="small" class="audit-table" show-summary :summary-method="getSummaryAudit">
        <el-table-column label="序号" prop="seq" width="52" align="center" fixed>
          <template #default="{ row }"><span class="seq-cell">{{ row.seq }}</span></template>
        </el-table-column>
        <el-table-column prop="assetName" label="资产名称" min-width="130" fixed />
        <el-table-column label="原值" align="center">
          <el-table-column prop="costUnadj" label="未审" min-width="100" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.costUnadj" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="costAje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.costAje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="costRje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.costRje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="审定" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.costAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="累计折旧" align="center">
          <el-table-column prop="depUnadj" label="未审" min-width="100" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.depUnadj" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="depAje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.depAje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="depRje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.depRje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="审定" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtNum(row.depAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="减值准备" align="center">
          <el-table-column prop="impairUnadj" label="未审" min-width="100" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.impairUnadj" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="impairAje" label="AJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.impairAje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column prop="impairRje" label="RJE" min-width="90" align="right">
            <template #default="{ row }">
              <el-input v-model.number="row.impairRje" size="small" :disabled="isReadonly" @change="onCellChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="审定" min-width="100" align="right" class-name="formula-col">
            <template #default="{ row }">
              <span class="formula-value">{{ fmtNum(row.impairAudited) }}</span>
            </template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="审定净值" min-width="110" align="right" class-name="formula-col net-col">
          <template #default="{ row }">
            <span class="formula-value net-value">{{ fmtNum(row.netAudited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </template>

    <!-- 交叉验证差异提示 -->
    <div v-if="crossValidationDiff !== 0" class="cross-validation-warn">
      <el-alert type="error" :closable="false" show-icon
        :title="`明细期末原值合计与 H3-1 审定数差异：${fmtNum(crossValidationDiff)}，请核对。`"
      />
    </div>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-2-cost')">AI生成</el-button>
            <el-button size="small" circle @click="openReview('H3-2-cost')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        placeholder="填写审计说明：明细逐项核对情况、折旧测算复核结论、增减变动核查过程（关注凭证/合同/评估报告）、与 H3-1 审定表勾稽差异及原因分析。"
        :disabled="isReadonly"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        placeholder="A、未见异常。B、除上述事项外未见异常。C、存在重大未调整事项，不可确认。"
        :disabled="isReadonly"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabDetailCost.vue — H3-2 明细表（成本模式）
 * 3区段Tab + 序号 + 增减日期/方式/凭证号/对方科目 + 折旧减值列组 + 行删除 + 导入导出
 */
import { ref, computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH3DetailCost, ASSET_TYPE_OPTIONS, CHANGE_TYPE_OPTIONS } from '../../composables/useH3DetailCost'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3ImportExport } from '../../composables/useH3ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('cost'),
})

const {
  rows, subtotal: subtotalRow, categorySubtotals, unmatchedCategory, restrictedCount, mortgagedCount,
  crossValidationDiff, addRow, removeRow, updateCell, seedUnadjFromBook, loadRows,
} = useH3DetailCost({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

const { exportTemplate, exportData, importData } = useH3ImportExport({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref<'cost' | 'fair_value'>('cost'),
  onImported: () => loadRows(),
})

const activeSegment = ref('基本信息')
const segmentOptions = ['基本信息', '增减转换', '折旧减值', '审定调整']
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── 审计说明 / 审计结论 ──────────────────────────────────────────────────────
const NOTE_KEY = 'H3-2-cost-audit-note'
const CONCLUSION_KEY = 'H3-2-cost-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})

function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}

function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

// ─── Row 操作 ─────────────────────────────────────────────────────────────────
async function handleAddAsset() {
  const { value } = await ElMessageBox.prompt('请输入资产名称', '添加资产行', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
  })
  if (value) addRow(value)
}

async function handleRemoveRow(rowId: string) {
  await ElMessageBox.confirm('确认删除该资产行？删除后不可恢复。', '删除确认', {
    confirmButtonText: '删除',
    cancelButtonText: '取消',
    type: 'warning',
  })
  removeRow(rowId)
}

async function handleSeedUnadj() {
  await ElMessageBox.confirm('将用账面期末原值/折旧/减值覆盖各行「未审数」，是否继续？', '带入未审数', {
    confirmButtonText: '确认带入',
    cancelButtonText: '取消',
    type: 'info',
  })
  seedUnadjFromBook()
  ElMessage.success('已从账面期末带入未审数')
}

function onCellChange(row: any) { updateCell(row.rowId) }

// ─── 格式化 ───────────────────────────────────────────────────────────────────
function fmtNum(v: number): string {
  if (!v || v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtNumRaw(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 合计行方法 ──────────────────────────────────────────────────────────────
function _buildSummary(propMap: Record<string, () => number>) {
  return ({ columns }: { columns: any[] }): string[] =>
    columns.map((col, idx) => {
      if (idx === 0) return '合计'
      const fn = propMap[col.property as string]
      if (fn) return fmtNumRaw(fn())
      // label 匹配（无 property 的公式列）
      const lmap: Record<string, () => number> = {
        '期末原值': () => subtotalRow.value.costEnd,
        '期末净值': () => subtotalRow.value.netValue,
        '审定净值': () => subtotalRow.value.netAudited,
        '审定': () => 0,
      }
      if (col.label === '审定' && col.parent?.label === '原值') return fmtNumRaw(subtotalRow.value.costAudited)
      if (col.label === '审定' && col.parent?.label === '累计折旧') return fmtNumRaw(subtotalRow.value.depAudited)
      if (col.label === '审定' && col.parent?.label === '减值准备') return fmtNumRaw(subtotalRow.value.impairAudited)
      if (col.label === '审定') {
        // 嵌套表头时 parent 可能不可用，按顺序回退
        return ''
      }
      const lfn = lmap[col.label as string]
      if (lfn) return fmtNumRaw(lfn())
      return ''
    })
}

const getSummaryBasic = _buildSummary({
  area: () => subtotalRow.value.area,
  originalCost: () => subtotalRow.value.originalCost,
  costBegin: () => subtotalRow.value.costBegin,
})

const getSummaryChange = _buildSummary({
  costBegin: () => subtotalRow.value.costBegin,
  costIncrease: () => subtotalRow.value.costIncrease,
  costDecrease: () => subtotalRow.value.costDecrease,
  transferIn: () => subtotalRow.value.transferIn,
  transferOut: () => subtotalRow.value.transferOut,
})

const getSummaryDep = _buildSummary({
  accDepBegin: () => subtotalRow.value.accDepBegin,
  depProvision: () => subtotalRow.value.depProvision,
  depReversal: () => subtotalRow.value.depReversal,
  impairmentBegin: () => subtotalRow.value.impairmentBegin,
  impairmentProvision: () => subtotalRow.value.impairmentProvision,
  impairmentReversal: () => subtotalRow.value.impairmentReversal,
})

const getSummaryAudit = _buildSummary({
  costUnadj: () => subtotalRow.value.costUnadj,
  costAje: () => subtotalRow.value.costAje,
  costRje: () => subtotalRow.value.costRje,
  depUnadj: () => subtotalRow.value.depUnadj,
  depAje: () => subtotalRow.value.depAje,
  depRje: () => subtotalRow.value.depRje,
  impairUnadj: () => subtotalRow.value.impairUnadj,
  impairAje: () => subtotalRow.value.impairAje,
  impairRje: () => subtotalRow.value.impairRje,
})

// ─── 导入导出 ─────────────────────────────────────────────────────────────────
async function doExportTemplate() { await exportTemplate('H3-2') }
async function doExportData() { await exportData('H3-2') }
function doImportData() { fileInputRef.value?.click() }

async function onFileSelected(e: Event) {
  const input = e.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const result = await importData('H3-2', file)
  if (result?.success) ElMessage.success(`H3-2（成本）已导入 ${result.rowCount} 行`)
  input.value = ''
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}

function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-detail-cost { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 编制提示 */
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; user-select: none; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.7; }
.guidance-content p { margin: 3px 0; }

/* 工具栏 */
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; }
.chip-wrap { display: inline-flex; align-items: center; }

/* 汇总看板 */
.summary-strip { display: flex; flex-wrap: wrap; gap: 10px; margin-bottom: 14px; }
.summary-card { display: flex; flex-direction: column; min-width: 120px; padding: 8px 14px; border-radius: 6px; border: 1px solid var(--el-border-color-lighter); }
.sc-label { font-size: 11px; color: var(--el-text-color-secondary); margin-bottom: 4px; }
.sc-value { font-size: 14px; font-weight: 600; color: var(--el-text-color-primary); }
.summary-card.cost { background: #f0f9ff; border-color: #91d5ff; }
.summary-card.dep  { background: #fff7e6; border-color: #ffd591; }
.summary-card.imp  { background: #fff1f0; border-color: #ffa39e; }
.summary-card.net  { background: #f6ffed; border-color: #95de64; }
.summary-card.inc  { background: #f9f0ff; border-color: #d3adf7; }
.summary-card.dec  { background: #fff2f0; border-color: #ffccc7; }
.summary-card.restrict { background: #fffbe6; border-color: #ffe58f; }
.summary-card.mortgage { background: #fff1f0; border-color: #ffa39e; }
.category-table { margin-bottom: 14px; }

/* 区段标题 */
.segment-header { padding: 6px 10px; font-weight: 600; font-size: 13px; border-radius: 4px; margin-bottom: 8px; }
.cost-header  { background: #e6f4ff; color: #0958d9; border-left: 3px solid #1677ff; }
.change-header { background: #f9f0ff; color: #531dab; border-left: 3px solid #722ed1; }
.dep-header   { background: #fff7e6; color: #874d00; border-left: 3px solid #fa8c16; }
.audit-header { background: #f6ffed; color: #237804; border-left: 3px solid #52c41a; }
.toolbar-inline { display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }
.hint-text { font-size: 12px; color: var(--el-text-color-secondary); }

/* 操作栏 */
.segment-bar { margin-bottom: 12px; }
.toolbar { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }
.export-dropdown { margin-left: auto; }

/* 表格 */
.audit-table { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.audit-table :deep(.inc-col .cell) { background: rgba(82, 196, 26, 0.06); }
.audit-table :deep(.dec-col .cell) { background: rgba(255, 77, 79, 0.06); }
.audit-table :deep(.net-col) { background: #f6ffed; }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-weight: 500; }
.net-value { color: #389e0d; font-weight: 600; }
.seq-cell { color: var(--el-text-color-secondary); font-size: 12px; }

/* 交叉验证 */
.cross-validation-warn { margin: 12px 0; }

/* 审计说明 */
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.action-btns { display: flex; gap: 4px; }
</style>
