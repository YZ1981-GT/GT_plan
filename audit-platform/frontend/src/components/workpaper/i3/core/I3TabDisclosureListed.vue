<template>
  <div class="i3-tab-disclosure-listed">
    <div class="section-header">
      <span class="section-title">商誉附注披露（上市公司）</span>
      <div class="section-actions">
        <GtIndexChip v-if="noteTarget" :value="noteTarget.chipValue" :context-project-id="projectId" />
        <el-button size="small" type="info" plain :disabled="isReadonly" @click="handlePull(true)">
          从 I3-2 取数
        </el-button>
        <el-button
          size="small"
          type="primary"
          plain
          :loading="isSyncing"
          :disabled="isReadonly || !projectId"
          @click="syncToNotes"
        >同步到附注</el-button>
        <el-button size="small" type="primary" plain :disabled="!projectId" @click="jumpToNote('listed')">↩ 跳转回附注</el-button>
        <el-button size="small" type="default" text @click="handleReview('disc-listed')">💬复核</el-button>
      </div>
    </div>

    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 原值/减值准备滚动（对齐附注五、28）</div>
        <div class="guide-step"><span class="step-num">②</span> 净值=原值期末−减值期末（商誉不摊销）</div>
        <div class="guide-step"><span class="step-num">③</span> CGU/关键假设/敏感性/业绩承诺子表</div>
        <div class="guide-step"><span class="step-num">④</span> 「同步到附注」写入附注模块 §五、28</div>
      </div>
    </div>

    <div class="methodology-block">
      <div class="methodology-title">CAS8 + 15号文第十九条（二十）+ 会计监管风险提示第8号</div>
      <div class="methodology-content">
        上市公司应披露：商誉账面原值及变动；累计减值准备及变动；资产组构成及是否与以前年度一致；
        可收回金额确定方法及关键参数（增长率、利润率、折现率）及与以前年度/实际情况差异原因；
        业绩承诺完成情况。即使未计提减值，亦须按上述要求披露。商誉减值不可转回。
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实上市公司商誉附注完整性与准确性；矩阵与 I3-2/I3-1/I3-6 勾稽；同步至附注模块「五、28 商誉」。"
    />
    <el-alert
      v-if="needsDetailSplitWarning"
      type="warning"
      :closable="false"
      show-icon
      class="objective-alert"
      title="当前为合计占位行（无明细分项），期初可能未填。请点「从 I3-2 取数」按被投资单位展开。"
    />

    <div class="reg-tip">
      <strong>监管提示：</strong>其他增减变动原因包括境外子公司汇率变化等；资产组变化须披露变化前后构成及客观依据；
      关键假设与以前年度或外部信息不一致时须披露差异原因。
    </div>

    <template v-for="section in sections" :key="section.key">
      <el-card shadow="never" class="disclosure-card">
        <template #header>
          <div class="card-title-row">
            <span>{{ section.title }}</span>
            <div class="title-actions">
              <el-button
                v-if="section.hasTable && isEditableMatrix(section.key) && !isReadonly"
                size="small"
                @click="handleAddMatrix(section.key)"
              >+ 行</el-button>
              <el-button size="small" type="default" link @click="handleReview(`disc-listed-${section.key}`)">💬</el-button>
            </div>
          </div>
        </template>

        <template v-if="section.hasTable && isEditableMatrix(section.key)">
          <!-- 原值：Excel 细列 -->
          <el-table
            v-if="section.key === 'goodwill_book_value'"
            :data="bookValueRows"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="investee" label="被投资单位名称或形成商誉的事项" min-width="160" fixed>
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.investee" size="small" @change="() => handleInvesteeChange(section.key, row)" />
                <span v-else>{{ row.investee }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初余额" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'beginBalance', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" align="center">
              <el-table-column label="企业合并形成的" width="110" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.incBusinessCombination ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'incBusinessCombination', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.incBusinessCombination ?? 0) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="合营取得" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.incJoint ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'incJoint', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.incJoint ?? 0) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.incOther ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'incOther', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.incOther ?? 0) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="本期减少" align="center">
              <el-table-column label="处置" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.decDisposal ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'decDisposal', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.decDisposal ?? 0) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.decOther ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'decOther', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.decOther ?? 0) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末余额" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+增加分项−减少分项">{{ fmtAmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveMatrix(section.key, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 减值：Excel 细列 -->
          <el-table
            v-else
            :data="impairmentRows"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="investee" label="被投资单位名称或形成商誉的事项" min-width="160" fixed>
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.investee" size="small" @change="() => handleInvesteeChange(section.key, row)" />
                <span v-else>{{ row.investee }}</span>
              </template>
            </el-table-column>
            <el-table-column label="期初余额" width="100" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" :model-value="row.beginBalance" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'beginBalance', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本期增加" align="center">
              <el-table-column label="计提" width="100" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.increase" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'increase', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.increase) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.impIncOther ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'impIncOther', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.impIncOther ?? 0) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="本期减少" align="center">
              <el-table-column label="处置" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.impDecDisposal ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'impDecDisposal', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.impDecDisposal ?? 0) }}</span>
                </template>
              </el-table-column>
              <el-table-column label="其他" width="90" align="right">
                <template #default="{ row }">
                  <el-input-number v-if="!isReadonly" :model-value="row.impDecOther ?? 0" :controls="false" size="small" style="width:100%" @change="(v: number) => handleMatrixEdit(section.key, row.rowId, 'impDecOther', v)" />
                  <span v-else class="amount-cell">{{ fmtAmt(row.impDecOther ?? 0) }}</span>
                </template>
              </el-table-column>
            </el-table-column>
            <el-table-column label="期末余额" width="110" align="right">
              <template #default="{ row }">
                <span class="formula-cell" title="期末=期初+计提+其他增加−处置−其他减少">{{ fmtAmt(row.endBalance) }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveMatrix(section.key, row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>

          <div v-if="section.key === 'goodwill_book_value'" class="matrix-subtotal">
            合计：期初 {{ fmtAmt(bookValueTotal.beginBalance) }}
            ｜ 增加 {{ fmtAmt(bookValueTotal.increase) }}
            ｜ 减少 {{ fmtAmt(bookValueTotal.decrease) }}
            ｜ 期末 {{ fmtAmt(bookValueTotal.endBalance) }}
            <div class="auto-fill-hint">其他增减可含境外子公司汇率变动等；同步附注时按「本期增加/减少」汇总写入</div>
          </div>
          <div v-else class="matrix-subtotal">
            合计：期初 {{ fmtAmt(impairmentTotal.beginBalance) }}
            ｜ 增加 {{ fmtAmt(impairmentTotal.increase) }}
            ｜ 转出 {{ fmtAmt(impairmentTotal.decrease) }}
            ｜ 期末 {{ fmtAmt(impairmentTotal.endBalance) }}
            <div class="impairment-warning">⚠️ 商誉减值不可转回，「本期减少」仅限处置/注销转出</div>
          </div>
        </template>

        <template v-else-if="section.hasTable">
          <el-table
            :data="getMatrixRows(section.key)"
            border
            stripe
            size="small"
            class="matrix-table"
          >
            <el-table-column prop="investee" label="被投资单位/CGU" min-width="160" />
            <el-table-column label="参考值1" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.beginBalance) }}</span></template>
            </el-table-column>
            <el-table-column label="参考值2" width="120" align="right">
              <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.endBalance) }}</span></template>
            </el-table-column>
          </el-table>
        </template>

        <template v-if="section.hasDynamicRows">
          <el-divider v-if="section.hasTable" content-position="left">CGU分摊明细</el-divider>
          <el-table :data="getDynamicRows(section.key)" border stripe size="small">
            <el-table-column type="index" width="40" />
            <el-table-column prop="name" label="资产组(CGU)名称" min-width="160">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="handleDynamicChange(section.key, row.rowId, 'name', row.name)" />
                <span v-else>{{ row.name }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="amount" label="分摊商誉账面" width="130" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly" v-model="row.amount" :controls="false" size="small" @change="(v: number) => handleDynamicChange(section.key, row.rowId, 'amount', v)" />
                <span v-else class="amount-cell">{{ fmtAmt(row.amount) }}</span>
              </template>
            </el-table-column>
            <el-table-column prop="description" label="分摊依据/可收回金额" min-width="200">
              <template #default="{ row }">
                <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="handleDynamicChange(section.key, row.rowId, 'description', row.description)" />
                <span v-else>{{ row.description }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="handleRemoveDynamic(section.key, row.rowId)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!isReadonly" class="dynamic-actions">
            <el-button size="small" @click="handleAddDynamic(section.key)">+ 新增CGU</el-button>
          </div>
        </template>

        <!-- (5) 关键假设参数子表（对齐附注毛利率/增长率/折现率） -->
        <template v-if="section.key === 'key_assumptions'">
          <div class="card-title-row assume-toolbar">
            <span class="assume-label">关键假设参数</span>
            <div class="title-actions">
              <el-button
                v-if="!isReadonly"
                size="small"
                type="info"
                plain
                @click="handleSeedAssumption"
              >从 CGU 预填</el-button>
              <el-button v-if="!isReadonly" size="small" @click="addAssumptionParamRow()">+ 行</el-button>
            </div>
          </div>
          <div class="perf-hint">
            披露各资产组预测期毛利率、收入/利润增长率、税前折现率等；与以前年度或外部信息不一致时须在文字说明中披露差异原因。
            同步写入附注「关键假设」参数子表（毛利率/增长率/折现率）。
          </div>
          <el-table :data="assumptionParamRows" border stripe size="small" class="matrix-table">
            <el-table-column type="index" width="42" align="center" />
            <el-table-column label="资产组/业务" min-width="140">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.label"
                  size="small"
                  placeholder="资产组名称"
                  @change="() => updateAssumptionParamRow(row.rowId, 'label', row.label)"
                />
                <span v-else>{{ row.label }}</span>
              </template>
            </el-table-column>
            <el-table-column label="毛利率" width="110">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.grossMargin"
                  size="small"
                  placeholder="如 28%"
                  @change="() => updateAssumptionParamRow(row.rowId, 'grossMargin', row.grossMargin)"
                />
                <span v-else>{{ row.grossMargin }}</span>
              </template>
            </el-table-column>
            <el-table-column label="增长率" width="110">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.growthRate"
                  size="small"
                  placeholder="如 5%"
                  @change="() => updateAssumptionParamRow(row.rowId, 'growthRate', row.growthRate)"
                />
                <span v-else>{{ row.growthRate }}</span>
              </template>
            </el-table-column>
            <el-table-column label="折现率" width="110">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.discountRate"
                  size="small"
                  placeholder="如 12%"
                  @change="() => updateAssumptionParamRow(row.rowId, 'discountRate', row.discountRate)"
                />
                <span v-else>{{ row.discountRate }}</span>
              </template>
            </el-table-column>
            <el-table-column label="备注" min-width="120">
              <template #default="{ row }">
                <el-input
                  v-if="!isReadonly"
                  v-model="row.remark"
                  size="small"
                  placeholder="预测期/稳定期等"
                  @change="() => updateAssumptionParamRow(row.rowId, 'remark', row.remark)"
                />
                <span v-else>{{ row.remark }}</span>
              </template>
            </el-table-column>
            <el-table-column v-if="!isReadonly" label="操作" width="56" align="center">
              <template #default="{ row }">
                <el-button type="danger" link size="small" @click="removeAssumptionParamRow(row.rowId)">删</el-button>
              </template>
            </el-table-column>
          </el-table>
          <div v-if="!assumptionParamRows.length" class="auto-fill-hint">可从（4）CGU 预填行，再填入参数后同步附注</div>
        </template>

        <template v-if="section.hasNoteText">
          <el-divider
            v-if="section.hasTable || section.hasDynamicRows || section.key === 'key_assumptions'"
            content-position="left"
          >文字说明</el-divider>
          <el-input
            v-model="sectionNotes[section.key]"
            type="textarea"
            :autosize="{ minRows: 3, maxRows: 12 }"
            :disabled="isReadonly"
            :placeholder="getPlaceholder(section.key)"
            @change="handleNoteChange(section.key)"
          />
          <div v-if="!isReadonly && !sectionNotes[section.key]" class="template-actions">
            <el-button size="small" text type="primary" @click="applyTemplate(section.key)">插入模板段落</el-button>
          </div>
        </template>
      </el-card>
    </template>

    <!-- 业绩承诺完成及对应商誉减值（上市附注子表） -->
    <el-card shadow="never" class="disclosure-card">
      <template #header>
        <div class="card-title-row">
          <span>（9）业绩承诺完成及对应商誉减值情况</span>
          <div class="title-actions">
            <el-button
              v-if="!isReadonly"
              size="small"
              type="info"
              plain
              @click="handleSeedPerformance"
            >从原值预填</el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPerformanceRow()">+ 行</el-button>
            <el-button size="small" type="default" link @click="handleReview('disc-listed-performance')">💬</el-button>
          </div>
        </div>
      </template>
      <div class="perf-hint">
        形成商誉时存在业绩承诺，且报告期或上一期间处于承诺期内的，应披露完成情况及对应商誉减值（15号文第十九条（二十））。
        同步写入附注子表「业绩承诺完成及对应商誉减值情况如下：」。
      </div>
      <el-table :data="performanceRows" border stripe size="small" class="matrix-table">
        <el-table-column type="index" width="42" align="center" />
        <el-table-column label="项目" min-width="160">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.name"
              size="small"
              placeholder="被投资单位/项目"
              @change="() => updatePerformanceRow(row.rowId, 'name', row.name)"
            />
            <span v-else>{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业绩承诺完成情况" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.commitmentStatus"
              size="small"
              placeholder="如：已完成 / 未完成（完成率XX%）/ 不适用"
              @change="() => updatePerformanceRow(row.rowId, 'commitmentStatus', row.commitmentStatus)"
            />
            <span v-else>{{ row.commitmentStatus }}</span>
          </template>
        </el-table-column>
        <el-table-column label="商誉减值金额" width="140" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairmentAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(v: number) => updatePerformanceRow(row.rowId, 'impairmentAmount', v ?? 0)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairmentAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="140">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.remark"
              size="small"
              placeholder="承诺期/补偿安排等"
              @change="() => updatePerformanceRow(row.rowId, 'remark', row.remark)"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center">
          <template #default="{ row }">
            <el-button type="danger" link size="small" @click="removePerformanceRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="matrix-subtotal">
        减值金额合计 {{ fmtAmt(performanceImpairmentTotal) }}
        <span v-if="!performanceRows.length" class="auto-fill-hint"> — 无业绩承诺可留空；有则须填报并同步</span>
      </div>
    </el-card>

    <el-card shadow="never" class="summary-card">
      <template #header><span class="summary-title">商誉账面净值合计</span></template>
      <div class="summary-formula">
        净值 = 商誉原值期末 <span class="amount-cell">{{ fmtAmt(bookValueTotal.endBalance) }}</span>
        − 减值准备期末 <span class="amount-cell">{{ fmtAmt(impairmentTotal.endBalance) }}</span>
        = <span class="amount-cell net-value">{{ fmtAmt(netValueTotal) }}</span>
      </div>
      <div class="summary-note">商誉不摊销；同步目标附注「{{ noteTarget.sectionId }}」</div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>（1）~（2）变动矩阵与附注五、28 子表一致，可从 I3-2 取数</li>
        <li>（3）~（8）文字按 15 号文及风险提示第 8 号，即使未减值也须披露测试过程与参数</li>
        <li>点「同步到附注」将原值/减值细列汇总 + 关键假设参数 + 业绩承诺 + 文字写入附注模块</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, onUnmounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useRouter } from 'vue-router'
import { buildNoteJumpRoute, type DisclosureVariant } from '@/views/composables/noteDisclosureReverseJump'
import { api } from '@/services/apiProxy'
import { eventBus } from '@/utils/eventBus'
import GtIndexChip from '../../GtIndexChip.vue'
import {
  useI3Disclosure,
  LISTED_SECTIONS,
  type I3DisclosureMatrixRow,
} from '../../composables/useI3Disclosure'
import { resolveI3NoteSectionTarget } from '../../composables/i3NoteSectionMap'
import { buildI3ListedSyncPayloads } from '../../composables/i3DisclosureSyncPayload'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  crossSheetAutoFill?: Record<string, number>
  applicableStandards?: string[]
}>()

const emit = defineEmits<{
  save: [itemId: string, value: any]
  'navigate-sheet': [sheetName: string]
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const router = useRouter()
// 跳转回附注模块（披露表 → 附注为单向推送；此处仅导航，方便相互编辑确认）
function jumpToNote(target: DisclosureVariant): void {
  const route = buildNoteJumpRoute(props.projectId || '', 'I3', target)
  if (!route) { ElMessage.warning('未找到对应的附注章节'); return }
  router.push(route)
}
const allResponsesRef = computed(() => props.allResponses)
const noteTarget = resolveI3NoteSectionTarget('listed')
const isSyncing = ref(false)
const sections = LISTED_SECTIONS

const {
  bookValueRows,
  impairmentRows,
  sectionRows,
  sectionNotes,
  performanceRows,
  assumptionParamRows,
  bookValueTotal,
  impairmentTotal,
  netValueTotal,
  applyAutoFill,
  needsDetailSplitWarning,
  pullFromDetailRows,
  addDynamicRow,
  removeDynamicRow,
  updateDynamicRow,
  updateMatrixCell,
  addMatrixRow,
  removeMatrixRow,
  addPerformanceRow,
  removePerformanceRow,
  updatePerformanceRow,
  seedPerformanceFromBookValue,
  addAssumptionParamRow,
  removeAssumptionParamRow,
  updateAssumptionParamRow,
  seedAssumptionFromCgu,
  saveSectionNote,
  getSyncSnapshot,
  dispose: disposeDisclosure,
} = useI3Disclosure(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    variant: ref('listed') as any,
    crossSheetAutoFill: computed(() => props.crossSheetAutoFill ?? {}),
    onSave(itemId: string, value: any) {
      emit('save', itemId, value)
    },
  },
)

const performanceImpairmentTotal = computed(() =>
  performanceRows.value.reduce((s, r) => s + (Number(r.impairmentAmount) || 0), 0),
)

function handleSeedPerformance() {
  const res = seedPerformanceFromBookValue()
  ElMessage({ type: res.count ? 'success' : 'info', message: res.message })
}

function handleSeedAssumption() {
  const res = seedAssumptionFromCgu()
  ElMessage({ type: res.count ? 'success' : 'info', message: res.message })
}

function handleAdjudicated(e: Event): void {
  const detail = (e as CustomEvent).detail
  if (!detail || detail.wpCode === 'I3' || detail.accountCode === '1711') applyAutoFill()
}

onMounted(() => {
  applyAutoFill()
  window.addEventListener('substantive:adjudicated', handleAdjudicated)
})
onUnmounted(() => {
  window.removeEventListener('substantive:adjudicated', handleAdjudicated)
  disposeDisclosure()
})

function isEditableMatrix(key: string) {
  return key === 'goodwill_book_value' || key === 'goodwill_impairment'
}

function getMatrixRows(sectionKey: string): I3DisclosureMatrixRow[] {
  switch (sectionKey) {
    case 'goodwill_book_value': return bookValueRows.value
    case 'goodwill_impairment': return impairmentRows.value
    case 'sensitivity_analysis':
      return (sectionRows.value.cgu_allocation ?? []).map((cgu) => ({
        rowId: `sens-${cgu.rowId}`,
        investee: cgu.name || '未命名CGU',
        beginBalance: cgu.amount ?? 0,
        increase: 0,
        decrease: 0,
        endBalance: cgu.amount ?? 0,
        isAutoFilled: false,
      }))
    case 'impairment_result':
      return (sectionRows.value.cgu_allocation ?? []).map((cgu) => ({
        rowId: `result-${cgu.rowId}`,
        investee: cgu.name || '未命名CGU',
        beginBalance: cgu.amount ?? 0,
        increase: 0,
        decrease: 0,
        endBalance: cgu.amount ?? 0,
        isAutoFilled: false,
      }))
    default: return []
  }
}

function getDynamicRows(key: string) {
  return sectionRows.value[key] ?? []
}

async function handleAddDynamic(sectionKey: string) {
  try {
    const { value } = await ElMessageBox.prompt('请输入资产组(CGU)名称', '新增CGU行', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：XX子公司/XX事业部',
    })
    if (value?.trim()) addDynamicRow(sectionKey, value.trim())
  } catch { /* cancel */ }
}

function handleRemoveDynamic(sectionKey: string, rowId: string) {
  removeDynamicRow(sectionKey, rowId)
}

function handleDynamicChange(sectionKey: string, rowId: string, field: string, value: any) {
  updateDynamicRow(sectionKey, rowId, field as any, value)
}

function handleMatrixEdit(sectionKey: string, rowId: string, field: string, value: number) {
  updateMatrixCell(
    sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment',
    rowId,
    field as keyof I3DisclosureMatrixRow,
    value ?? 0,
  )
}

function handleAddMatrix(sectionKey: string) {
  addMatrixRow(sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment')
}

function handleRemoveMatrix(sectionKey: string, rowId: string) {
  removeMatrixRow(sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment', rowId)
}

function handleInvesteeChange(sectionKey: string, row: I3DisclosureMatrixRow) {
  updateMatrixCell(
    sectionKey === 'goodwill_book_value' ? 'bookValue' : 'impairment',
    row.rowId,
    'investee',
    row.investee,
  )
}

function handleNoteChange(sectionKey: string) {
  saveSectionNote(sectionKey, sectionNotes.value[sectionKey] ?? '')
}

function handlePull(overwrite: boolean) {
  const res = pullFromDetailRows({ overwrite })
  ElMessage({ type: res.count ? 'success' : 'warning', message: res.message })
}

const TEMPLATES: Record<string, string> = {
  impairment_test_process:
    '商誉所属资产组构成及与以前年度一致性：\n'
    + '可收回金额确定方法（公允价值减处置费用净额 / 预计未来现金流量现值）：\n'
    + '若采用现值法：预测期年限、预测期收入增长率/利润率、稳定期增长率/利润率、税前折现率及其确定依据：\n'
    + '与以前年度减值测试信息或外部信息不一致的，差异原因：\n'
    + '以前年度减值测试信息与本年实际情况是否一致：',
  key_assumptions:
    '本公司采用预计未来现金流量现值计算资产组可收回金额。根据管理层批准的财务预算预计未来5年内现金流量，'
    + '其后年度现金流量增长率预计为XX%（上期：XX%），不超过长期平均增长率；税前折现率为XX%（上期：XX%）。'
    + '管理层根据历史经验及对市场发展的预测确定预算毛利率及增长率。',
  sensitivity_analysis:
    '若未来现金流量计算中采用的预算增长率低于管理层目前采用的增长率的10%，本公司仍无需对商誉计提减值准备。\n'
    + '若预计折现率高于管理层目前采用的折现率的10%，本公司亦无需对商誉计提减值准备。',
  impairment_result:
    '经过评估，管理层认为本公司无需对该等资产组计提减值准备。【或：本期期末对商誉计提减值准备XX元（上期：XX元）。】',
  cgu_allocation:
    '商誉已分摊至预期受益于企业合并协同效应的资产组/组合，分摊层级代表内部监控商誉的最低水平，且不大于报告分部。资产组构成变化（若有）及依据：',
  other_disclosure:
    '其他需说明事项（汇率变动、处置、无业绩承诺说明等）：',
}

function applyTemplate(sectionKey: string) {
  const t = TEMPLATES[sectionKey]
  if (!t) return
  sectionNotes.value[sectionKey] = t
  saveSectionNote(sectionKey, t)
}

function getPlaceholder(key: string): string {
  return TEMPLATES[key] || '请填写披露文字…'
}

function fmtAmt(v: number): string {
  return (Number(v) || 0).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleReview(id: string) {
  openReviewDialog(id)
}

async function syncToNotes() {
  if (isSyncing.value || props.isReadonly || !props.projectId || !props.wpId) return
  const snap = getSyncSnapshot()
  if (!snap.bookValueRows.length && !snap.impairmentRows.length) {
    ElMessage.warning('请先从 I3-2 取数或手工填写变动矩阵')
    return
  }
  const payloads = buildI3ListedSyncPayloads(props.wpId, props.applicableStandards || [], snap)
  if (!payloads.length) {
    ElMessage.warning('当前不适用上市附注同步')
    return
  }
  isSyncing.value = true
  try {
    let rows = 0
    for (const payload of payloads) {
      const result: any = await api.post(
        `/api/projects/${props.projectId}/disclosure-notes/sync-from-workpaper`,
        payload,
      )
      rows += Number((result?.data ?? result)?.rows_synced ?? 0)
    }
    eventBus.emit('disclosure:note-text-updated' as any, {
      projectId: props.projectId,
      sectionIds: [noteTarget.sectionId],
      wpId: props.wpId,
      sheet: '附注披露（上市公司）',
    })
    ElMessage.success(`已同步至附注 ${noteTarget.sectionId}（${rows} 行）`)
  } catch (e: any) {
    ElMessage.error(e?.message || '同步失败')
  } finally {
    isSyncing.value = false
  }
}
</script>

<style scoped>
.i3-tab-disclosure-listed { padding: 16px; font-size: var(--wp-font-size, 13px); }
.section-header {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 12px; gap: 12px; flex-wrap: wrap;
}
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions, .title-actions { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.card-title-row {
  display: flex; justify-content: space-between; align-items: center; width: 100%;
  font-size: 14px; font-weight: 600;
}
.guide-area {
  background: linear-gradient(135deg, #eff6ff, #dbeafe);
  border: 1px solid #93c5fd; border-radius: 8px; padding: 12px 14px; margin-bottom: 12px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 6px 16px; font-size: 12px; color: #1e3a5f; }
.guide-step { display: flex; gap: 6px; }
.step-num { color: #2563eb; font-weight: 700; }
.methodology-block {
  border-left: 4px solid #f59e0b; background: #fffbeb; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 12px; font-size: 12px; line-height: 1.7; color: #78350f;
}
.methodology-title { font-weight: 600; margin-bottom: 4px; }
.objective-alert { margin-bottom: 12px; }
.reg-tip {
  background: #ecfdf5; border: 1px solid #6ee7b7; border-radius: 6px;
  padding: 8px 12px; margin-bottom: 12px; font-size: 12px; color: #065f46; line-height: 1.6;
}
.disclosure-card { margin-bottom: 12px; }
.matrix-table { width: 100%; margin-bottom: 8px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.formula-cell { font-weight: 600; border-bottom: 1px dashed #94a3b8; cursor: help; }
.matrix-subtotal { font-size: 12px; color: #475569; margin-top: 6px; }
.impairment-warning { color: #b45309; margin-top: 4px; }
.auto-fill-hint { font-size: 12px; color: #64748b; margin-top: 6px; }
.perf-hint {
  font-size: 12px;
  color: #065f46;
  background: #ecfdf5;
  border: 1px solid #a7f3d0;
  border-radius: 6px;
  padding: 8px 10px;
  margin-bottom: 10px;
  line-height: 1.6;
}
.dynamic-actions, .template-actions { margin-top: 8px; }
.assume-toolbar { margin-bottom: 8px; }
.assume-label { font-size: 13px; font-weight: 600; color: #334155; }
.summary-card { margin-top: 8px; }
.summary-title { font-weight: 600; }
.summary-formula { font-size: 13px; line-height: 1.8; }
.net-value { color: #92400e; font-weight: 700; font-size: 15px; }
.summary-note { font-size: 12px; color: #6b7280; margin-top: 4px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: #6b7280; }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { margin: 8px 0 0; padding-left: 18px; line-height: 1.8; }
</style>
