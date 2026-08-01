<template>
<div class="d6-disclosure">
  <!-- 同步状态条 -->
  <GtWpDisclosureSyncBar :project-id="projectId" :year="auditYear" :wp-code="'D6'" :sheet-name="displayVariant === 'soe' ? '附注披露信息（国企）' : '附注披露信息(上市公司）'" />

  <!-- 编制提示 -->
  <details class="guidance-details">
    <summary>📋 编制提示</summary>
    <div class="guidance-content">
      <p>1. 合同资产（科目1141）附注依 CAS14 收入准则及 CAS22 减值准则披露，按上市公司版（5子节）/ 国企版（3子节）分别列报。</p>
      <p>2. 表内浅蓝背景单元格为跨sheet自动取数（来源 D6-1 审定表 / D6-3 减值明细 / D6-8 测算），不可手工编辑。</p>
      <p>3. 上市公司版需披露分类构成、减值计提情况、单项与组合明细及计提转回核销变动；国企版仅需披露分类及减值变动。</p>
      <p>4. 各子节说明文本将双向回写至附注模块，请与审定表、减值明细及测算保持勾稽一致。</p>
    </div>
  </details>

  <!-- 工具栏 -->
  <div class="tab-toolbar">
    <div class="toolbar-left">
      <el-segmented v-if="showListed && showSoe" v-model="activeVariant" :options="variantOptions" size="small" />
      <el-button type="primary" plain size="small" :loading="isSyncing" :disabled="isReadonly"
        title="将披露表的表格与文本框内容同步到附注模块（五、10/八、11 合同资产）"
        @click="syncToDisclosureNotes">同步到附注</el-button>
      <el-dropdown split-button type="default" size="small" :disabled="!projectId"
        @click="jumpToNote(displayVariant)"
        @command="jumpToNote">
        ↩ 跳转回附注（{{ displayVariant === 'soe' ? '八、11' : '五、10' }}）
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item command="listed">上市版（五、10）</el-dropdown-item>
            <el-dropdown-item command="soe">国企版（八、11）</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
    </div>
    <div class="toolbar-right">
      <span class="chip-wrap"><GtIndexChip value="wp:D6-1" :context-project-id="projectId" /></span>
      <span class="chip-wrap"><GtIndexChip value="wp:D6-3" :context-project-id="projectId" /></span>
    </div>
  </div>

  <!-- 上市公司版 -->
  <template v-if="displayVariant === 'listed'">
    <div v-for="section in listedSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <!-- Section 1: 分类 -->
      <template v-if="section.sectionKey === 'listed-1'">
        <!-- 源模板 A20「或：披露格式如下」= 二选一表组（同名同表，列/行形态不同） -->
        <div class="format-switch">
          <span class="format-label">披露格式（源模板「或：」二选一）：</span>
          <el-radio-group
            :model-value="mainFormat"
            size="small"
            :disabled="isReadonly"
            @change="(v: any) => setMainFormat(v)"
          >
            <el-radio-button value="detailed">明细式（账面余额/减值准备/账面价值）</el-radio-button>
            <el-radio-button value="simple">简化式（合同资产/减：减值准备/小计）</el-radio-button>
          </el-radio-group>
        </div>

        <!-- 简化式：源模板 A21-A26，单级 3 列，行由明细派生 -->
        <el-table v-if="mainFormat === 'simple'" :data="simpleMainRows" size="small" border>
          <el-table-column prop="label" label="项  目" min-width="260" />
          <el-table-column label="期末余额" width="140" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.end_amount) }}</span></template>
          </el-table-column>
          <el-table-column label="上年年末余额" width="140" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.prior_amount) }}</span></template>
          </el-table-column>
        </el-table>

        <!-- 明细式：源模板 B8:D8「期末余额」/ E8:G8「上年年末余额」两级表头（旧实现拍平成
             「期末账面余额」式组合列名，与附注渲染不一致） -->
        <el-table v-else :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项  目" width="200" />
          <el-table-column label="期末余额">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="上年年末余额">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </template>

      <!-- (1) 本期合同资产账面价值的重大变动 -->
      <template v-else-if="section.sectionKey === 'listed-major-change'">
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="majorChangeIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="majorChangeIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="majorChangeIe.importing.value"
                    @change="(f: any) => onMajorChangeImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-table :data="padRows(majorChangeRows)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small" placeholder="变动项目"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.amount" :controls="false" size="small" style="width:100%"
                @change="(v: number) => updateMajorChangeCell(row.rowId, 'amount', v ?? 0)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="240">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.reason" size="small" placeholder="变动原因"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeMajorChangeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addMajorChangeRow">添加行</el-button>
        <!-- 重大变动情形说明（准则指引） -->
        <details class="amber-context">
          <summary>📖 重大变动情形说明（CAS14）</summary>
          <div class="amber-content">
            <p>履行履约义务的时间与通常的付款时间之间的关系，以及此类因素对合同资产（如果对合同负债产生影响在合同负债科目下说明）账面价值的影响。本期内发生的重大变动的情形包括：</p>
            <p>① 企业合并导致的变动；</p>
            <p>② 对收入进行累积追溯调整导致的相关合同资产和合同负债的变动，此类调整可能源于估计履约进度的变化、估计交易价格的变化（包括对于可变对价是否受到限制的评估发生变化）或者合同变更；</p>
            <p>③ 对合同对价的权利成为无条件权利（即，合同资产重分类为应收款项）的时间安排发生变化。</p>
          </div>
        </details>
      </template>

      <!-- Section 2: 减值计提情况 -->
      <template v-else-if="section.sectionKey === 'listed-2'">
        <div class="section-hint">
          源模板 A42-A54 为三级表头（期末余额 / 上年年末余额 各含「账面余额{金额, 比例(%)}、
          减值准备{金额, 预期信用损失率(%)}、账面价值」）。平台附注只支持两级，故按期间拆两张表：
          期末段自 ECL 底稿取数，上年年末段为源模板要求的**手工填列**。
        </div>
        <div class="sub-caption">期末余额</div>
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="类别" width="180" />
          <el-table-column label="账面余额">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="比例(%)" width="90" align="right">
              <template #default="{ row }">{{ fmtPct(row.endPercentage) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="减值准备">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endAmount) }}</span></template>
            </el-table-column>
            <el-table-column label="预期信用损失率(%)" width="140" align="right">
              <template #default="{ row }">{{ fmtPct100(row.endLossRate) }}</template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              {{ row._isPad ? '' : fmtAmt((row.endBalance || 0) - (row.endAmount || 0)) }}
            </template>
          </el-table-column>
        </el-table>

        <div class="sub-caption">
          续：上年年末余额
          <el-button v-if="!isReadonly" size="small" style="margin-left:8px" @click="addImpairmentPriorRow">添加行</el-button>
        </div>
        <el-table :data="padRows(impairmentPriorRows)" size="small" border>
          <el-table-column label="类别" width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small"
                @input="(v: string) => updateImpairmentPriorCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.balance" :precision="2"
                  aria-label="上年年末账面余额金额"
                  @change="(v: number | null) => updateImpairmentPriorCell(row.rowId, 'balance', v)" />
                <span v-else>{{ row._isPad ? '' : fmtAmt(row.balance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="比例(%)" width="90" align="right">
              <template #default="{ row }">
                <el-input v-if="!isReadonly && !row._isPad" :model-value="String(row.ratio ?? '')" size="small"
                  @input="(v: string) => updateImpairmentPriorCell(row.rowId, 'ratio', v)" />
                <span v-else>{{ row._isPad ? '' : fmtPct100(row.ratio) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="减值准备">
            <el-table-column label="金额" width="120" align="right">
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.provision" :precision="2"
                  aria-label="上年年末减值准备金额"
                  @change="(v: number | null) => updateImpairmentPriorCell(row.rowId, 'provision', v)" />
                <span v-else>{{ row._isPad ? '' : fmtAmt(row.provision) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="预期信用损失率(%)" width="140" align="right">
              <template #default="{ row }">
                <el-input v-if="!isReadonly && !row._isPad" :model-value="String(row.lossRate ?? '')" size="small"
                  @input="(v: string) => updateImpairmentPriorCell(row.rowId, 'lossRate', v)" />
                <span v-else>{{ row._isPad ? '' : fmtPct100(row.lossRate) }}</span>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="账面价值" width="120" align="right">
            <template #default="{ row }">
              {{ row._isPad ? '' : fmtAmt((row.balance || 0) - (row.provision || 0)) }}
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small"
                @click="removeImpairmentPriorRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- Section 3: 单项明细 -->
      <template v-else-if="section.sectionKey === 'listed-3'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="名称" min-width="160" />
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.balance) }}</span></template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="损失率%" width="90" align="right">
            <template #default="{ row }">{{ fmtPct100(row.lossRate) }}</template>
          </el-table-column>
          <el-table-column prop="reason" label="计提理由" min-width="160" />
        </el-table>

        <div class="sub-caption">
          续：上年年末余额
          <el-button v-if="!isReadonly" size="small" style="margin-left:8px" @click="addSinglePriorRow">添加行</el-button>
        </div>
        <div class="section-hint">源模板 A61「续：」段（A62-A66），比较期单项明细为手工填列。</div>
        <el-table :data="padRows(singlePriorRows)" size="small" border>
          <el-table-column label="名 称" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small"
                @input="(v: string) => updateSinglePriorCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="账面余额" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.balance" :precision="2"
                aria-label="上年年末账面余额"
                @change="(v: number | null) => updateSinglePriorCell(row.rowId, 'balance', v)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.balance) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="坏账准备" width="120" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.provision" :precision="2"
                aria-label="上年年末坏账准备"
                @change="(v: number | null) => updateSinglePriorCell(row.rowId, 'provision', v)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.provision) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="预期信用损失率(%)" width="140" align="right">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="String(row.lossRate ?? '')" size="small"
                @input="(v: string) => updateSinglePriorCell(row.rowId, 'lossRate', v)" />
              <span v-else>{{ row._isPad ? '' : fmtPct100(row.lossRate) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="计提理由" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.reason" size="small"
                @input="(v: string) => updateSinglePriorCell(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small"
                @click="removeSinglePriorRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
      </template>

      <!-- Section 4: 按组合明细 -->
      <template v-else-if="section.sectionKey === 'listed-4'">
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="groupsIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="groupsIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="groupsIe.importing.value"
                    @change="(f: any) => onGroupsImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <div v-for="(group, gIdx) in groupedDetails" :key="gIdx" class="group-block">
          <div class="group-header">
            <el-input
              v-if="!isReadonly"
              :model-value="group.groupName"
              size="small"
              placeholder="组合名称"
              style="width:200px"
              @change="(v: string) => updateGroupName(gIdx, v)"
            />
            <span v-else class="group-name">{{ group.groupName || `组合${gIdx + 1}` }}</span>
            <el-button v-if="!isReadonly" size="small" @click="addGroupedDetailRow(group.groupName)">添加行</el-button>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="onFillGroupAgingBands(gIdx)">按账龄段生成</el-button>
            <el-tag size="small" type="info" effect="plain">账龄口径：{{ agingBandLabels.join(' / ') }}</el-tag>
          </div>
          <el-table :data="padRows(group.rows)" size="small" border>
            <el-table-column label="账  龄" width="140">
              <template #default="{ row }">
                <el-select
                  v-if="!isReadonly && !row._isPad"
                  :model-value="row.label"
                  size="small"
                  filterable
                  allow-create
                  default-first-option
                  placeholder="选择账龄段（可自定义）"
                  @change="(v: string) => updateGroupedCell(gIdx, row.rowId, 'label', v || '')"
                >
                  <el-option v-for="label in agingBandLabels" :key="label" :label="label" :value="label" />
                </el-select>
                <span v-else>{{ row.label }}</span>
              </template>
            </el-table-column>
            <!-- 源模板 B69:D69「期末余额」/ E69:G69「上年年末余额」两级表头 -->
            <el-table-column label="期末余额">
              <el-table-column label="合同资产" width="120" align="right">
                <template #default="{ row }">
                  <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.balance" :precision="2"
                    aria-label="期末合同资产"
                    @change="(v: number | null) => updateGroupedCell(gIdx, row.rowId, 'balance', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtAmt(row.balance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="坏账准备" width="120" align="right">
                <template #default="{ row }">
                  <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.provision" :precision="2"
                    aria-label="期末坏账准备"
                    @change="(v: number | null) => updateGroupedCell(gIdx, row.rowId, 'provision', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtAmt(row.provision) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="预期信用损失率(%)" width="130" align="right">
                <template #default="{ row }">
                  <el-input v-if="!isReadonly && !row._isPad" :model-value="String(row.lossRate ?? '')" size="small"
                    @input="(v: string) => updateGroupedCell(gIdx, row.rowId, 'lossRate', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtPct100(row.lossRate) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="上年年末余额">
              <el-table-column label="合同资产" width="120" align="right">
                <template #default="{ row }">
                  <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.priorBalance" :precision="2"
                    aria-label="上年年末合同资产"
                    @change="(v: number | null) => updateGroupedCell(gIdx, row.rowId, 'priorBalance', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtAmt(row.priorBalance) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="坏账准备" width="120" align="right">
                <template #default="{ row }">
                  <WpAmountInput v-if="!isReadonly && !row._isPad" :model-value="row.priorProvision" :precision="2"
                    aria-label="上年年末坏账准备"
                    @change="(v: number | null) => updateGroupedCell(gIdx, row.rowId, 'priorProvision', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtAmt(row.priorProvision) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="预期信用损失率(%)" width="130" align="right">
                <template #default="{ row }">
                  <el-input v-if="!isReadonly && !row._isPad" :model-value="String(row.priorLossRate ?? '')" size="small"
                    @input="(v: string) => updateGroupedCell(gIdx, row.rowId, 'priorLossRate', v)" />
                  <span v-else>{{ row._isPad ? '' : fmtPct100(row.priorLossRate) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="" width="50" align="center">
              <template #default="{ row }">
                <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeGroupedRow(gIdx, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
        </div>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addGroup">添加组合</el-button>
      </template>

      <!-- Section 5: 计提转回核销 -->
      <template v-else-if="section.sectionKey === 'listed-5'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="180" />
          <el-table-column label="本期计提" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
          </el-table-column>
          <el-table-column label="本期转回" width="120" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
          </el-table-column>
          <!-- 源模板 D85 字面为「本期转销/核销」 -->
          <el-table-column label="本期转销/核销" width="130" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
          </el-table-column>
          <el-table-column prop="reason" label="原因" min-width="160" />
        </el-table>
      </template>

      <div class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getListedNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getListedNoteKey(section.sectionKey), v)"
        />
        <div class="note-actions">
          <el-button size="small" :loading="aiLoadingSection === getListedNoteKey(section.sectionKey)" :disabled="isReadonly"
            @click="runAi(getListedNoteKey(section.sectionKey))">🤖 AI</el-button>
          <el-button v-if="openReviewDialog" size="small" @click="openReview(getListedNoteKey(section.sectionKey))">💬 复核</el-button>
        </div>
      </div>
    </div>
  </template>

  <!-- 国企版 -->
  <template v-if="displayVariant === 'soe'">
    <div v-for="section in soeSections" :key="section.sectionKey" class="disclosure-card">
      <h4 class="section-title">{{ section.label }}</h4>

      <!-- (1) 合同资产情况：期末/期初 各含 账面余额/减值准备/账面价值 -->
      <template v-if="section.sectionKey === 'soe-1'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="200" fixed />
          <el-table-column label="期末数" align="center">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期初数" align="center">
            <el-table-column label="账面余额" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="减值准备" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorImpairment) }}</span></template>
            </el-table-column>
            <el-table-column label="账面价值" width="120" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBookValue) }}</span></template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </template>

      <!-- (2) 合同资产减值准备：项目/期初/本期变动(计提/转回/转销核销)/期末/原因 -->
      <template v-else-if="section.sectionKey === 'soe-2'">
        <el-table :data="padRows(section.rows)" size="small" border>
          <el-table-column prop="label" label="项目" width="150" fixed />
          <el-table-column label="期初数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.priorBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="本期变动金额" align="center">
            <el-table-column label="计提" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.provision) }}</span></template>
            </el-table-column>
            <el-table-column label="转回" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.reversal) }}</span></template>
            </el-table-column>
            <el-table-column label="转销/核销" width="110" align="right">
              <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.writeOff) }}</span></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="期末数" width="110" align="right">
            <template #default="{ row }"><span class="cross-sheet-cell">{{ fmtAmt(row.endBalance) }}</span></template>
          </el-table-column>
          <el-table-column label="原因" min-width="160">
            <template #default="{ row }">{{ row._isPad ? '' : row.reason }}</template>
          </el-table-column>
        </el-table>
      </template>

      <!-- (1) 本期合同资产账面价值的重大变动【国资委格式未要求披露】 -->
      <template v-else>
        <div class="sub-toolbar">
          <el-dropdown v-if="!isReadonly" size="small" trigger="click">
            <el-button size="small">导入导出 ▾</el-button>
            <template #dropdown>
              <el-dropdown-menu>
                <el-dropdown-item @click="majorChangeIe.exportTemplate">导出模板</el-dropdown-item>
                <el-dropdown-item @click="majorChangeIe.exportData">导出数据</el-dropdown-item>
                <el-dropdown-item>
                  <el-upload :show-file-list="false" accept=".xlsx" :auto-upload="false" :disabled="majorChangeIe.importing.value"
                    @change="(f: any) => onMajorChangeImport(f.raw || f)"><span>导入数据</span></el-upload>
                </el-dropdown-item>
              </el-dropdown-menu>
            </template>
          </el-dropdown>
        </div>
        <el-table :data="padRows(majorChangeRows)" size="small" border>
          <el-table-column label="项目" min-width="200">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.label" size="small" placeholder="变动项目"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'label', v)" />
              <span v-else>{{ row.label }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动金额" width="160" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !row._isPad" :model-value="row.amount" :controls="false" size="small" style="width:100%"
                @change="(v: number) => updateMajorChangeCell(row.rowId, 'amount', v ?? 0)" />
              <span v-else>{{ row._isPad ? '' : fmtAmt(row.amount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="变动原因" min-width="240">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && !row._isPad" :model-value="row.reason" size="small" placeholder="变动原因"
                @change="(v: string) => updateMajorChangeCell(row.rowId, 'reason', v)" />
              <span v-else>{{ row.reason }}</span>
            </template>
          </el-table-column>
          <el-table-column v-if="!isReadonly" label="" width="50" align="center">
            <template #default="{ row }">
              <el-button v-if="!row._isPad" type="danger" text size="small" @click="removeMajorChangeRow(row.rowId)">删</el-button>
            </template>
          </el-table-column>
        </el-table>
        <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addMajorChangeRow">添加行</el-button>
        <details class="amber-context">
          <summary>📖 重大变动情形说明（CAS14）</summary>
          <div class="amber-content">
            <p>履行履约义务的时间与通常的付款时间之间的关系，以及此类因素对合同资产（如果对合同负债产生影响在合同负债科目下说明）账面价值的影响。本期内发生的重大变动的情形包括：</p>
            <p>① 企业合并导致的变动；</p>
            <p>② 对收入进行累积追溯调整导致的相关合同资产和合同负债的变动，此类调整可能源于估计履约进度的变化、估计交易价格的变化（包括对于可变对价是否受到限制的评估发生变化）或者合同变更；</p>
            <p>③ 对合同对价的权利成为无条件权利（即，合同资产重分类为应收款项）的时间安排发生变化。</p>
          </div>
        </details>
      </template>

      <div v-if="section.sectionKey !== 'soe-3'" class="note-block">
        <div class="note-label">说明：</div>
        <el-input
          :model-value="noteTexts[getSoeNoteKey(section.sectionKey)]"
          type="textarea"
          :autosize="{ minRows: 2, maxRows: 6 }"
          :disabled="isReadonly"
          placeholder="补充披露说明..."
          @change="(v: string) => updateNoteText(getSoeNoteKey(section.sectionKey), v)"
        />
        <div class="note-actions">
          <el-button size="small" :loading="aiLoadingSection === getSoeNoteKey(section.sectionKey)" :disabled="isReadonly"
            @click="runAi(getSoeNoteKey(section.sectionKey))">🤖 AI</el-button>
          <el-button v-if="openReviewDialog" size="small" @click="openReview(getSoeNoteKey(section.sectionKey))">💬 复核</el-button>
        </div>
      </div>
    </div>
  </template>
</div>
</template>

<script setup lang="ts">
/**
 * D6TabDisclosure.vue — 附注披露（上市5子节 / 国企3子节）
 */
import { computed, inject, ref, toRef, watch, onBeforeUnmount, type Ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { useDisclosureAutoSync } from '../composables/useDisclosureAutoSync'
import { useD6Disclosure } from '../composables/useD6Disclosure'
import { useD6ImportExport } from '../composables/useD6ImportExport'
import {
  buildD6SyncPayload,
  buildD6SimpleMainRows,
  D6_NOTE_SECTION,
  D6_NOTE_TEXT_SECTIONS,
  type D6DisclosureSnapshot,
} from '../composables/d6NoteSectionMap'
import { useDisclosureNoteAi } from '../composables/useDisclosureNoteAi'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import type { ChecklistResponse } from '../composables/useD6FormData'
import type useD6CrossSheet from '../composables/useD6CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { checkNoteConsistencyGeneric } from '../composables/noteConsistencyCheck'
import { useAgingConfig } from '@/composables/useAgingConfig'

// @ts-ignore
import GtIndexChip from '../GtIndexChip.vue'
import GtWpDisclosureSyncBar from '../GtWpDisclosureSyncBar.vue'
// 🔴 可编辑金额千分符只能用 el-input（EP 2.13.6 的 el-input-number 无 formatter prop）
import WpAmountInput from '../shared/WpAmountInput.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  isReadonly: boolean
  allResponses: Map<string, ChecklistResponse>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD6CrossSheet>
  variant: 'listed' | 'soe'
}>()

const allResponsesRef = toRef(props, 'allResponses') as unknown as Ref<Map<string, ChecklistResponse>>

const { year: auditYear } = useAuditContext()

const {
  listedSections, soeSections, showListed, showSoe, activeVariant,
  groupedDetails, addGroup, addGroupedDetailRow, fillGroupAgingBands, updateGroupName, updateGroupedCell, removeGroupedRow,
  majorChangeRows, addMajorChangeRow, updateMajorChangeCell, removeMajorChangeRow,
  mainFormat, setMainFormat,
  impairmentPriorRows, addImpairmentPriorRow, updateImpairmentPriorCell, removeImpairmentPriorRow,
  singlePriorRows, addSinglePriorRow, updateSinglePriorCell, removeSinglePriorRow,
  noteTexts,
} = useD6Disclosure({
  allResponses: allResponsesRef,
  crossSheet: props.crossSheet,
  wpId: computed(() => props.wpId) as unknown as Ref<string>,
  projectId: computed(() => props.projectId) as unknown as Ref<string>,
  saveImmediate: async () => {},
  debouncedSave: props.debouncedSave,
})

if (props.variant) {
  activeVariant.value = props.variant
}

// ─── 账龄枚举（3年段 / 5年段 / 自定义，项目账龄配置为唯一真源）────────────────
// 附注模板国企侧组合分表行维度本就是账龄段（源模板「工程施工」「质量保证金」
// 两张组合分表 headers=「账 龄」），此前只有自由文本输入，与 D1/D2/D7 割裂。
const { segments: d6AgingSegments } = useAgingConfig(computed(() => props.projectId) as unknown as Ref<string>, 'D6')
const agingBandLabels = computed<string[]>(() => d6AgingSegments.value.map(s => s.label))

function onFillGroupAgingBands(groupIndex: number): void {
  const added = fillGroupAgingBands(groupIndex, agingBandLabels.value)
  if (added > 0) ElMessage.success(`已按账龄段补齐 ${added} 行`)
  else ElMessage.info('账龄段已齐备，无需新增')
}

// ─── 保存后自动同步到附注（防抖/非阻塞/失败静默）──────────────────────────────
const autoSync = useDisclosureAutoSync({ isReadonly: () => props.isReadonly })
onBeforeUnmount(() => autoSync.cancelPending())
watch(
  [
    listedSections, soeSections, groupedDetails, majorChangeRows,
    impairmentPriorRows, singlePriorRows, mainFormat, noteTexts,
  ],
  () => {
    autoSync.scheduleAutoSync(syncToDisclosureNotes)
  },
  { deep: true },
)

// ─── 导入导出（参照 D4-2）：重大变动表 + 组合明细表 ─────────────────────
const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)
const wpIdRef = computed(() => props.wpId) as unknown as Ref<string>

const majorChangeIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-note-major-change',
  sheetLabel: '重大变动',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})
const groupsIe = useD6ImportExport({
  wpId: wpIdRef,
  sheetCode: 'D6-note-groups',
  sheetLabel: '组合明细',
  onImported: () => reloadWorkpaperData?.() ?? Promise.resolve(),
})

async function onMajorChangeImport(file: File) { await majorChangeIe.importData(file) }
async function onGroupsImport(file: File) { await groupsIe.importData(file) }

const displayVariant = computed(() => {
  if (props.variant) return props.variant
  if (showListed.value && !showSoe.value) return 'listed'
  if (showSoe.value && !showListed.value) return 'soe'
  return activeVariant.value
})

const variantOptions = computed(() => {
  const opts = []
  if (showListed.value) opts.push({ label: '上市公司版', value: 'listed' })
  if (showSoe.value) opts.push({ label: '国企版', value: 'soe' })
  return opts
})

const LISTED_NOTE_MAP: Record<string, string> = {
  'listed-1': 'D6-note-listed-text-1',
  'listed-major-change': 'D6-note-listed-text-major-change',
  'listed-2': 'D6-note-listed-text-2',
  'listed-3': 'D6-note-listed-text-3',
  'listed-4': 'D6-note-listed-text-4',
  'listed-5': 'D6-note-listed-text-5',
}

const SOE_NOTE_MAP: Record<string, string> = {
  'soe-1': 'D6-note-soe-text-1',
  'soe-2': 'D6-note-soe-text-2',
  'soe-3': 'D6-note-soe-text-3',
}

function getListedNoteKey(sectionKey: string): string {
  return LISTED_NOTE_MAP[sectionKey] || ''
}

function getSoeNoteKey(sectionKey: string): string {
  return SOE_NOTE_MAP[sectionKey] || ''
}

function updateNoteText(key: string, value: string) {
  if (!key) return
  noteTexts.value = { ...noteTexts.value, [key]: value }
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  if (val < 0) return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 空表补足占位空行（至少2行），避免"No Data"太丑；占位行 _isPad=true 不渲染输入控件 */
function padRows<T extends { rowId?: string }>(rows: T[], min = 2): any[] {
  const out: any[] = [...(rows || [])]
  let i = 0
  while (out.length < min) {
    out.push({ rowId: `__pad-${i}__`, _isPad: true })
    i++
  }
  return out
}

function fmtPct(rate: number): string {
  if (!rate) return '-'
  return `${(rate * 100).toFixed(1)}%`
}

function fmtPct100(rate: number): string {
  if (!rate) return '-'
  return `${rate.toFixed(2)}%`
}

// ─── 同步到附注 / 跳转回附注 ─────────────────────────────────────────────────
const router = useRouter()
const isSyncing = ref(false)

function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'D6', target)
  if (route) router.push(route)
}

// ─── 说明文本域的 AI 辅助 + 复核入口（共享 composable）──────────────────────
// 🔴 `section_id` 与后端 `review_dialog._SECTION_PROMPTS` 的键逐字一致：
// 文本域键形如 `D6-note-listed-text-1` → 去掉 `D6-note-` 前缀作后缀，
// 得 `d6-disclosure-listed-text-1-note`。未登记会回退通用 prompt（诱导自造内容）。
const openReviewDialog = inject<any>('openReviewDialog', null)
const D6_NOTE_TITLES: Record<string, string> = Object.fromEntries(
  [...D6_NOTE_TEXT_SECTIONS.listed, ...D6_NOTE_TEXT_SECTIONS.soe].map((s) => [s.key, s.title]),
)
const { aiLoadingSection, runAi, openReview } = useDisclosureNoteAi({
  wpId: toRef(props, 'wpId') as Ref<string>,
  isReadonly: () => props.isReadonly,
  getText: (k) => noteTexts.value?.[k] ?? '',
  setText: (k, text) => updateNoteText(k, text),
  buildSectionId: (k) => `d6-disclosure-${String(k).replace(/^D6-note-/, '')}-note`,
  labelOf: (k) => D6_NOTE_TITLES[k] ?? k,
  openReviewDialog,
})

/** 简化式主表行：与同步载荷共用同一纯函数（禁止两处各算一遍）。 */
const simpleMainRows = computed(() => {
  const cls = findSection(listedSections.value, 'listed-1')
  return buildD6SimpleMainRows((cls.rows ?? []) as any[])
})

function findSection(sections: any[], key: string): any {
  return (sections || []).find((s) => s.sectionKey === key) || { rows: [] }
}

/** 底稿披露表 → 附注单向推送（当前 displayVariant 对应上市/国企）。 */
async function syncToDisclosureNotes(): Promise<void> {
  if (isSyncing.value || !props.projectId || props.isReadonly) return
  isSyncing.value = true
  const variant = displayVariant.value as DisclosureVariant
  try {
    let snapshot: D6DisclosureSnapshot
    if (variant === 'soe') {
      const cls = findSection(soeSections.value, 'soe-1')
      const imp = findSection(soeSections.value, 'soe-2')
      snapshot = {
        classRows: (cls.rows ?? []).map((r: any) => ({
          label: r.label,
          endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
          priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
        })),
        soeImpairmentRows: (imp.rows ?? []).map((r: any) => ({
          label: r.label, priorBalance: r.priorBalance, provision: r.provision,
          reversal: r.reversal, writeOff: r.writeOff, endBalance: r.endBalance, reason: r.reason,
        })),
        majorChangeRows: majorChangeRows.value.map((r: any) => ({ label: r.label, amount: r.amount, reason: r.reason })),
        notes: { ...noteTexts.value },
      }
    } else {
      const cls = findSection(listedSections.value, 'listed-1')
      const prov = findSection(listedSections.value, 'listed-2')
      const single = findSection(listedSections.value, 'listed-3')
      const change = findSection(listedSections.value, 'listed-5')
      snapshot = {
        classRows: (cls.rows ?? []).map((r: any) => ({
          label: r.label,
          endBookBalance: r.endBookBalance, endImpairment: r.endImpairment, endBookValue: r.endBookValue,
          priorBookBalance: r.priorBookBalance, priorImpairment: r.priorImpairment, priorBookValue: r.priorBookValue,
        })),
        mainFormat: mainFormat.value,
        majorChangeRows: majorChangeRows.value.map((r: any) => ({ label: r.label, amount: r.amount, reason: r.reason })),
        // 🔴 字段名必须与 `D6ImpairmentProvisionRowLike` 一致（旧代码写的是
        // endBalance/endPercentage/endAmount/endLossRate → 载荷侧读不到，静默推 0）
        impairmentProvisionRows: (prov.rows ?? []).map((r: any) => ({
          label: r.label,
          balance: r.endBalance,
          ratio: r.endPercentage,
          provision: r.endAmount,
          lossRate: r.endLossRate,
        })),
        impairmentProvisionPriorRows: impairmentPriorRows.value.map((r: any) => ({
          label: r.label, balance: r.balance, ratio: r.ratio,
          provision: r.provision, lossRate: r.lossRate,
        })),
        singleItems: (single.rows ?? []).map((r: any) => ({
          label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate, reason: r.reason,
        })),
        singleItemsPrior: singlePriorRows.value.map((r: any) => ({
          label: r.label, balance: r.balance, provision: r.provision, lossRate: r.lossRate, reason: r.reason,
        })),
        groups: groupedDetails.value.map((g: any) => ({
          groupName: g.groupName,
          rows: (g.rows ?? []).map((r: any) => ({
            label: r.label,
            balance: r.balance, provision: r.provision, lossRate: r.lossRate,
            priorBalance: r.priorBalance, priorProvision: r.priorProvision, priorLossRate: r.priorLossRate,
          })),
        })),
        changeRows: (change.rows ?? []).map((r: any) => ({
          label: r.label, provision: r.provision, reversal: r.reversal, writeOff: r.writeOff, reason: r.reason,
        })),
        notes: { ...noteTexts.value },
      }
    }
    const payload = buildD6SyncPayload(variant, props.wpId || '', null, snapshot)
    const result: any = await http.post(
      `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
      payload,
    )
    const data = result?.data ?? result
    const rows = Number(data?.rows_synced ?? 0)
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: {
        wpCode: 'D6',
        accountCode: '1141',
        projectId: props.projectId,
        section: variant,
        sectionIds: [D6_NOTE_SECTION[variant]],
      },
    }))
    ElMessage.success(`已同步 ${rows} 行到附注模块「${D6_NOTE_SECTION[variant]} 合同资产」`)
    // 静默校对附注合计一致性
    checkNoteConsistencyGeneric(props.projectId, auditYear.value, D6_NOTE_SECTION[variant], 0, true)
  } catch {
    ElMessage.warning('同步附注失败，请稍后重试')
  } finally {
    isSyncing.value = false
  }
}


</script>

<style scoped>
.d6-disclosure { padding: 16px; }
.d6-disclosure :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.d6-disclosure :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p { margin: 2px 0; }

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

.disclosure-card {
  margin-bottom: 24px;
  padding: 16px;
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 6px;
}
.section-title { font-size: 14px; font-weight: 600; margin-bottom: 12px; color: #303133; }
/* 源模板方法论上下文（琥珀色左边线 + 浅黄背景，平台统一口径） */
.section-hint {
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  padding: 6px 10px;
  margin-bottom: 8px;
  font-size: 12px;
  line-height: 1.7;
  color: #7d5b1e;
}
.note-actions {
  display: flex;
  gap: 8px;
  margin-top: 6px;
  justify-content: flex-end;
}
.format-switch {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.format-label { font-size: 12px; color: #909399; }
.sub-caption {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: #606266;
  margin: 10px 0 6px;
}

/* 重大变动情形说明（准则指引琥珀块） */
.amber-context {
  margin-top: 12px;
  border-left: 3px solid #e6a23c;
  background: #fdf6ec;
  border-radius: 4px;
  padding: 8px 12px;
}
.amber-context summary { cursor: pointer; font-weight: 500; color: #e6a23c; }
.amber-content { margin-top: 8px; font-size: 12px; color: #606266; line-height: 1.7; }
.amber-content p { margin: 4px 0; }
.cross-sheet-cell { background: #ecf5ff; padding: 2px 6px; border-radius: 2px; cursor: help; }
.sub-toolbar { display: flex; justify-content: flex-end; margin-bottom: 8px; }
.group-block { margin-bottom: 12px; }
.group-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.group-name { font-weight: 600; font-size: var(--wp-font-size, 13px); }
.note-block { margin-top: 12px; }
.note-label { font-size: var(--wp-font-size, 13px); color: #606266; margin-bottom: 6px; }
</style>
