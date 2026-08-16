<template>
  <div class="j1-tab-industry">
    <!-- 审计目标（简洁alert） -->
    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>
        审计目标：将被审计单位人均薪酬、薪酬占收入比等指标与同行业均值对比，识别显著偏离，评估薪酬水平的合理性。
      </template>
    </el-alert>

    <!-- 审计过程（方法论琥珀块，对齐源模板行9~12） -->
    <div class="amber-context">
      <div class="amber-title">二、审计过程</div>
      <p>1. 分析企业报告期人均工资（分部门、地区或产品线）是否与同地区同行业的水平一致，并与招股书等相关数据核对</p>
      <p>2. 分析人力投入及其变化是否合理，人数是否与企业规模一致</p>
      <p>3. 如果存在异常，了解公司异常的原因。关注：考务公司是否有关联方代为发行人属员支付薪酬、是否存在其他方（如关联方）代付工资情况；应关注实际薪酬发放日与资产负债表日的间隔时间，考虑本期留存金额是否合理。以及实际薪酬水平在行业所处位置的合理性和相关披露信息的准确性、完整</p>
    </div>

    <!-- 统计概览 -->
    <div class="stats-cards">
      <div class="stat-card">
        <div class="stat-label">本公司人均薪酬</div>
        <div class="stat-value">{{ fmtAmt(companyTotal.curAvg) }}</div>
      </div>
      <div class="stat-card">
        <div class="stat-label">薪酬占收入比</div>
        <div class="stat-value">{{ companyTotal.revenueRatio.toFixed(2) }}%</div>
      </div>
      <div class="stat-card" :class="{ 'stat-danger': Math.abs(companyTotal.avgChangeRate) > 30 }">
        <div class="stat-label">人均变动率</div>
        <div class="stat-value">{{ companyTotal.avgChangeRate.toFixed(1) }}%</div>
      </div>
      <div class="stat-card" :class="{ 'stat-danger': socialDiff !== 0 }">
        <div class="stat-label">社保人数差异</div>
        <div class="stat-value">{{ socialDiff }} 人</div>
      </div>
    </div>

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-popover placement="bottom" :width="280" trigger="click">
          <template #reference>
            <el-button size="small" type="primary" plain>⚙ 可比公司管理</el-button>
          </template>
          <div class="peer-manager">
            <div class="peer-title">可比公司列表（影响Tab3&4）</div>
            <div v-for="p in peerCompanies" :key="p" class="peer-item">
              <span>{{ p }}</span>
              <el-button v-if="!isReadonly" type="danger" link size="small" @click="removePeer(p)">删除</el-button>
            </div>
            <div v-if="!isReadonly" class="peer-add">
              <el-input v-model="newPeerName" size="small" placeholder="输入公司名" style="width:160px" @keyup.enter="doAddPeer" />
              <el-button size="small" type="primary" @click="doAddPeer">添加</el-button>
            </div>
          </div>
        </el-popover>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleAddDept">+ 新增岗位</el-button>
        <GtIndexChip value="wp:J1-4" :context-project-id="projectId" />
        <el-tag size="small" type="info">{{ peerCompanies.length }} 家可比公司</el-tag>
      </div>
      <div class="toolbar-right">
        <span class="revenue-input">
          营业收入：
          <el-input-number v-if="!isReadonly" v-model="revenue" :controls="false" size="small" style="width:140px" @change="scheduleSave" />
          <b v-else>{{ fmtAmt(revenue) }}</b>
        </span>
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate('industry')">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData('industry')">导出数据</el-dropdown-item>
              <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 4 Tab -->
    <el-tabs v-model="activeTab" type="border-card">
      <!-- Tab1: 公司薪酬总览 -->
      <el-tab-pane label="公司薪酬总览" name="overview">
        <el-table :data="[...companyDeptRows, companyTotal]" border size="small" class="industry-table"
          :row-class-name="({ row }) => row.id === 'total' ? 'total-row' : ''">
          <el-table-column label="部门/岗位" width="120" fixed>
            <template #default="{ row }">
              <el-input v-if="!isReadonly && row.id !== 'total'" :model-value="row.dept" size="small" @change="(v: string) => updateDeptCell(row.id, 'dept', v)" />
              <b v-else>{{ row.dept }}</b>
            </template>
          </el-table-column>
          <el-table-column label="本期计提" align="center">
            <el-table-column label="人数" width="80" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && row.id !== 'total'" :model-value="row.curHeadcount" :controls="false" size="small" style="width:68px" @change="(v: number) => updateDeptCell(row.id, 'curHeadcount', v ?? 0)" />
                <span v-else>{{ row.curHeadcount || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="总额" width="110" align="right">
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && row.id !== 'total'" :model-value="row.curTotal" size="small" style="width:98px" @change="(v: number) => updateDeptCell(row.id, 'curTotal', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.curTotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人均" width="100" align="right" class-name="calc-col">
              <template #default="{ row }"><el-tooltip content="人均 = 总额 ÷ 人数" placement="top"><span class="formula-cell">{{ fmtAmt(row.curAvg) }}</span></el-tooltip></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="上期计提" align="center">
            <el-table-column label="人数" width="80" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && row.id !== 'total'" :model-value="row.priorHeadcount" :controls="false" size="small" style="width:68px" @change="(v: number) => updateDeptCell(row.id, 'priorHeadcount', v ?? 0)" />
                <span v-else>{{ row.priorHeadcount || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="总额" width="110" align="right">
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && row.id !== 'total'" :model-value="row.priorTotal" size="small" style="width:98px" @change="(v: number) => updateDeptCell(row.id, 'priorTotal', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.priorTotal) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人均" width="100" align="right" class-name="calc-col">
              <template #default="{ row }"><el-tooltip content="上期人均 = 上期总额 ÷ 上期人数" placement="top"><span class="formula-cell">{{ fmtAmt(row.priorAvg) }}</span></el-tooltip></template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="占收入比" width="85" align="right" class-name="calc-col" show-overflow-tooltip>
            <template #default="{ row }"><el-tooltip content="占收入比 = 本期总额 ÷ 营业收入 × 100%" placement="top"><span class="formula-cell">{{ fmtPct(row.revenueRatio) }}</span></el-tooltip></template>
          </el-table-column>
          <el-table-column label="人均变动率" width="90" align="right" class-name="calc-col" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tooltip content="人均变动率 = (本期人均 - 上期人均) ÷ |上期人均| × 100%，>30%红色预警" placement="top">
                <span :class="{ 'text-danger': Math.abs(row.avgChangeRate) > 30 }" class="formula-cell">{{ fmtPct(row.avgChangeRate) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="行业人均" width="100" align="right" show-overflow-tooltip>
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && row.id !== 'total'" :model-value="row.industryAvg" :controls="false" size="small" style="width:88px" @change="(v: number) => updateDeptCell(row.id, 'industryAvg', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.industryAvg) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="行业差异" width="85" align="right" class-name="calc-col" show-overflow-tooltip>
            <template #default="{ row }">
              <el-tooltip content="行业差异 = (本公司人均 - 行业人均) ÷ |行业人均| × 100%，>30%红色预警" placement="top">
                <span :class="{ 'text-danger': Math.abs(row.industryDiff) > 30 }" class="formula-cell">{{ fmtPct(row.industryDiff) }}</span>
              </el-tooltip>
            </template>
          </el-table-column>
          <el-table-column label="异常分析说明" min-width="200" show-overflow-tooltip>
            <template #default="{ row }">
              <div v-if="!isReadonly && row.id !== 'total'" class="analysis-cell">
                <el-input :model-value="row.analysis" size="small" placeholder="异常原因说明" @change="(v: string) => updateDeptCell(row.id, 'analysis', v)" />
                <el-button
                  v-if="Math.abs(row.avgChangeRate) > 30 || Math.abs(row.industryDiff) > 30"
                  size="small" type="primary" link class="ai-btn"
                  :loading="aiAnalysisLoading === row.id"
                  @click="generateRowAnalysis(row)"
                >🤖</el-button>
              </div>
              <span v-else>{{ row.analysis || '-' }}</span>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab2: 社保人数核对 -->
      <el-tab-pane label="社保人数核对" name="social">
        <div class="social-grid">
          <el-card shadow="never" class="social-card">
            <template #header><span class="social-title">公司发放工资人数</span></template>
            <el-table :data="socialLeft" border size="small" class="industry-table">
              <el-table-column prop="label" label="类别" min-width="200" />
              <el-table-column label="人数" width="100" align="right">
                <template #default="{ row, $index }">
                  <el-input-number v-if="!isReadonly" :model-value="row.count" :controls="false" size="small" style="width:88px" @change="(v: number) => { socialLeft[$index].count = v ?? 0; scheduleSave() }" />
                  <span v-else>{{ row.count }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="social-subtotal">小计：<b>{{ socialLeftTotal }}</b></div>
          </el-card>
          <el-card shadow="never" class="social-card">
            <template #header><span class="social-title">公司实际上交社会保险的人数</span></template>
            <el-table :data="socialRight" border size="small" class="industry-table">
              <el-table-column prop="label" label="类别" min-width="200" />
              <el-table-column label="人数" width="100" align="right">
                <template #default="{ row, $index }">
                  <el-input-number v-if="!isReadonly" :model-value="row.count" :controls="false" size="small" style="width:88px" @change="(v: number) => { socialRight[$index].count = v ?? 0; scheduleSave() }" />
                  <span v-else>{{ row.count }}</span>
                </template>
              </el-table-column>
            </el-table>
            <div class="social-subtotal">小计：<b>{{ socialRightTotal }}</b></div>
          </el-card>
        </div>
        <div class="social-diff" :class="{ 'diff-danger': socialDiff !== 0 }">
          差异：<b>{{ socialDiff }}</b> 人
          <el-tag v-if="socialDiff === 0" type="success" size="small">一致</el-tag>
          <el-tag v-else type="danger" size="small">不一致，需说明原因</el-tag>
        </div>
      </el-tab-pane>

      <!-- Tab3: 同行业对比——生产 -->
      <el-tab-pane label="同行业对比(生产)" name="peerProd">
        <el-table :data="[...peerProductionRows, peerProdAvg, selfProdRow, diffProdRow]" border size="small" class="industry-table"
          :row-class-name="({ row }) => row.company === '同行业平均' || row.company === '被审计单位' || row.company === '差异' ? 'total-row' : ''">
          <el-table-column label="单位名称" width="100" fixed>
            <template #default="{ row }"><b v-if="['同行业平均','被审计单位','差异'].includes(row.company)">{{ row.company }}</b><span v-else>{{ row.company }}</span></template>
          </el-table-column>
          <el-table-column label="生产人数" width="90" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.headcount" :controls="false" size="small" style="width:78px" @change="(v: number) => updateProdCell(row.id, 'headcount', v ?? 0)" />
              <span v-else>{{ row.headcount || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column label="人工成本（生产人员）" width="120" align="right" show-overflow-tooltip>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.laborCost" size="small" style="width:98px" @change="(v: number) => updateProdCell(row.id, 'laborCost', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.laborCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="主营业务成本中人工成本" width="130" align="right" show-overflow-tooltip>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.mainLaborCost" size="small" style="width:98px" @change="(v: number) => updateProdCell(row.id, 'mainLaborCost', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.mainLaborCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="收入" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.revenue" size="small" style="width:98px" @change="(v: number) => updateProdCell(row.id, 'revenue', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.revenue) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="总成本" width="110" align="right">
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.totalCost" size="small" style="width:98px" @change="(v: number) => updateProdCell(row.id, 'totalCost', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.totalCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="主营业务成本" width="110" align="right" show-overflow-tooltip>
            <template #default="{ row }">
              <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.mainCost" size="small" style="width:98px" @change="(v: number) => updateProdCell(row.id, 'mainCost', v ?? 0)" />
              <span v-else>{{ fmtAmt(row.mainCost) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="指标" align="center">
            <el-table-column label="人均产值（收入/人数）" width="110" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="人均产值 = 收入 ÷ 生产人数" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.perCapitaOutput) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="总成本中人工成本占比" width="110" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="占比 = 人工成本 ÷ 总成本 × 100%" placement="top">
                  <span class="formula-cell">{{ fmtPct(row.costRatio) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
            <el-table-column label="主营业务成本总人工成本" width="120" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="占比 = 主营人工成本 ÷ 主营业务成本 × 100%" placement="top">
                  <span class="formula-cell">{{ fmtPct(row.mainBizRatio) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <!-- Tab4: 同行业对比——销管研 -->
      <el-tab-pane label="同行业对比(销管研)" name="peerSMR">
        <el-table :data="[...peerSMRRows, peerSMRAvg, selfSMRRow, diffSMRRow]" border size="small" class="industry-table"
          :row-class-name="({ row }) => ['同行业平均','被审计单位','差异'].includes(row.company) ? 'total-row' : ''">
          <el-table-column label="单位名称" width="100" fixed>
            <template #default="{ row }"><b v-if="['同行业平均','被审计单位','差异'].includes(row.company)">{{ row.company }}</b><span v-else>{{ row.company }}</span></template>
          </el-table-column>
          <el-table-column label="销售人员" align="center">
            <el-table-column label="销售人数" width="85" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.salesCount" :controls="false" size="small" style="width:73px" @change="(v: number) => updateSMRCell(row.id, 'salesCount', v ?? 0)" />
                <span v-else>{{ row.salesCount || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人工成本（销售人员）" width="120" align="right" show-overflow-tooltip>
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.salesCost" size="small" style="width:98px" @change="(v: number) => updateSMRCell(row.id, 'salesCost', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.salesCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="销售人员平均薪酬" width="110" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="销售人员平均薪酬 = 人工成本(销售) ÷ 销售人数" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.salesAvg) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="管理人员" align="center">
            <el-table-column label="管理人数" width="85" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.mgmtCount" :controls="false" size="small" style="width:73px" @change="(v: number) => updateSMRCell(row.id, 'mgmtCount', v ?? 0)" />
                <span v-else>{{ row.mgmtCount || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人工成本（管理人员）" width="120" align="right" show-overflow-tooltip>
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.mgmtCost" size="small" style="width:98px" @change="(v: number) => updateSMRCell(row.id, 'mgmtCost', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.mgmtCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="管理人员平均薪酬" width="110" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="管理人员平均薪酬 = 人工成本(管理) ÷ 管理人数" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.mgmtAvg) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
          <el-table-column label="研发人员" align="center">
            <el-table-column label="研发人数" width="85" align="right">
              <template #default="{ row }">
                <el-input-number v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.rdCount" :controls="false" size="small" style="width:73px" @change="(v: number) => updateSMRCell(row.id, 'rdCount', v ?? 0)" />
                <span v-else>{{ row.rdCount || '-' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="人工成本（研发人员）" width="120" align="right" show-overflow-tooltip>
              <template #default="{ row }">
                <WpAmountInput v-if="!isReadonly && !['同行业平均','被审计单位','差异'].includes(row.company)" :model-value="row.rdCost" size="small" style="width:98px" @change="(v: number) => updateSMRCell(row.id, 'rdCost', v ?? 0)" />
                <span v-else>{{ fmtAmt(row.rdCost) }}</span>
              </template>
            </el-table-column>
            <el-table-column label="研发人员平均薪酬" width="110" align="right" class-name="calc-col" show-overflow-tooltip>
              <template #default="{ row }">
                <el-tooltip content="研发人员平均薪酬 = 人工成本(研发) ÷ 研发人数" placement="top">
                  <span class="formula-cell">{{ fmtAmt(row.rdAvg) }}</span>
                </el-tooltip>
              </template>
            </el-table-column>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <!-- 审计说明与结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明与结论</span>
        </div>
      </template>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">三、审计说明</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'note'" :disabled="isReadonly" @click="generateAi('note')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" placeholder="分析各类薪酬指标与行业水平差异原因..." :disabled="isReadonly" @change="saveOpinion" />
      </div>
      <div class="opinion-section">
        <div class="opinion-section-header">
          <span class="opinion-section-label">四、审计结论</span>
          <el-button size="small" type="primary" plain :loading="aiLoading === 'conclusion'" :disabled="isReadonly" @click="generateAi('conclusion')">🤖 AI辅助</el-button>
        </div>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2 }" placeholder="审计结论..." :disabled="isReadonly" @change="saveOpinion" />
      </div>
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 同行业对比属分析性程序，用于评估薪酬总额、人均薪酬与行业水平的偏离合理性。</p>
        <p>2. 行业均值数据来源须注明（如上市公司年报、行业协会统计、Wind数据等）。</p>
        <p>3. 差异率>30%自动红色标记，须结合企业规模、地区、岗位结构分析合理性。</p>
        <p>4. 社保人数与工资人数不一致须查明原因（退休返聘/劳务派遣/兼职等）。</p>
        <p>5. 确认公司的各项薪酬是否在行业合理范围内，关注是否存在代付工资等异常。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import WpAmountInput from '../../shared/WpAmountInput.vue'
import { ref, computed, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useJ1IndustryCompare } from '@/composables/workpaper/j1/useJ1IndustryCompare'
import { useJ1ImportExport } from '@/composables/workpaper/j1/useJ1ImportExport'
import GtIndexChip from '../../GtIndexChip.vue'
import http from '@/utils/http'

const props = defineProps<{
  wpId: string
  projectId: string
  htmlData?: Record<string, unknown> | null
  allResponses?: Map<string, any>
  isReadonly?: boolean
  saveImmediate?: (items: Array<any>) => Promise<void>
}>()

const isReadonly = computed(() => props.isReadonly ?? false)
const allResponsesRef = ref(props.allResponses || new Map())

const {
  revenue, companyDeptRows, companyTotal, socialLeft, socialRight,
  socialLeftTotal, socialRightTotal, socialDiff,
  peerCompanies, peerProductionRows, peerSMRRows, peerProdAvg, peerSMRAvg,
  auditNote, auditConclusion,
  updateDeptCell, updateProdCell, updateSMRCell,
  addPeer, removePeer, scheduleSave, saveOpinion, reload,
} = useJ1IndustryCompare({
  allResponses: allResponsesRef,
  saveImmediate: props.saveImmediate || (async () => {}),
  isReadonly: toRef(props, 'isReadonly') as any || ref(false),
})

// 导入导出
const { exportTemplate, exportData, importData } = useJ1ImportExport(props.wpId)
function triggerImport() {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const f = (e.target as HTMLInputElement).files?.[0]
    if (!f) return
    const ok = await importData('industry', f)
    if (ok) {
      const res = await http.get(`/api/workpapers/${props.wpId}/checklist-responses`)
      const arr = res.data?.data || res.data || []
      for (const it of arr) allResponsesRef.value.set(it.item_id, it)
      reload()
    }
  }
  input.click()
}

const activeTab = ref('overview')
const newPeerName = ref('')

function doAddPeer() {
  if (newPeerName.value.trim()) {
    addPeer(newPeerName.value.trim())
    newPeerName.value = ''
  }
}

async function handleAddDept() {
  try {
    const { value } = await ElMessageBox.prompt('请输入岗位/部门名称（如：研发人员）', '新增岗位', { confirmButtonText: '确定', cancelButtonText: '取消' })
    if (value?.trim()) {
      // Add to companyDeptRows
      const newRow = {
        id: `j1i-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
        dept: value.trim(),
        curHeadcount: 0, curTotal: 0, curAvg: 0,
        priorHeadcount: 0, priorTotal: 0, priorAvg: 0,
        revenueRatio: 0, avgChangeRate: 0, industryAvg: 0, industryDiff: 0, analysis: '',
      }
      companyDeptRows.value = [...companyDeptRows.value, newRow]
      scheduleSave()
    }
  } catch { /* cancelled */ }
}

function fmtAmt(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { maximumFractionDigits: 2 })
}

function fmtPct(v: number): string {
  if (v === 0) return '-'
  return v.toFixed(1) + '%'
}

// 被审计单位行 & 差异行（生产）
const selfProdRow = computed(() => recalcSelfProdRow())
const diffProdRow = computed(() => {
  const self = selfProdRow.value
  const avg = peerProdAvg.value
  return {
    id: 'diff-prod', company: '差异',
    headcount: self.headcount - avg.headcount,
    laborCost: self.laborCost - avg.laborCost,
    mainLaborCost: self.mainLaborCost - avg.mainLaborCost,
    avgWage: self.avgWage - avg.avgWage,
    revenue: self.revenue - avg.revenue,
    totalCost: self.totalCost - avg.totalCost,
    mainCost: self.mainCost - avg.mainCost,
    perCapitaOutput: self.perCapitaOutput - avg.perCapitaOutput,
    costRatio: self.costRatio - avg.costRatio,
    mainBizRatio: self.mainBizRatio - avg.mainBizRatio,
  }
})

function recalcSelfProdRow() {
  // 从公司薪酬总览取"生产人员"行数据
  const prodRow = companyDeptRows.value.find(r => r.dept.includes('生产'))
  return {
    id: 'self-prod', company: '被审计单位',
    headcount: prodRow?.curHeadcount || 0,
    laborCost: prodRow?.curTotal || 0,
    mainLaborCost: 0, // 用户需在此Tab手填
    avgWage: prodRow?.curAvg || 0,
    revenue: revenue.value,
    totalCost: 0,
    mainCost: 0,
    perCapitaOutput: (prodRow?.curHeadcount || 0) === 0 ? 0 : revenue.value / (prodRow?.curHeadcount || 1),
    costRatio: 0,
    mainBizRatio: 0,
  }
}

// 被审计单位行 & 差异行（销管研）
const selfSMRRow = computed(() => {
  const salesRow = companyDeptRows.value.find(r => r.dept.includes('销售'))
  const mgmtRow = companyDeptRows.value.find(r => r.dept.includes('管理'))
  const rdRow = companyDeptRows.value.find(r => r.dept.includes('研发'))
  return {
    id: 'self-smr', company: '被审计单位',
    salesCount: salesRow?.curHeadcount || 0, salesCost: salesRow?.curTotal || 0, salesAvg: salesRow?.curAvg || 0,
    mgmtCount: mgmtRow?.curHeadcount || 0, mgmtCost: mgmtRow?.curTotal || 0, mgmtAvg: mgmtRow?.curAvg || 0,
    rdCount: rdRow?.curHeadcount || 0, rdCost: rdRow?.curTotal || 0, rdAvg: rdRow?.curAvg || 0,
  }
})
const diffSMRRow = computed(() => {
  const self = selfSMRRow.value
  const avg = peerSMRAvg.value
  return {
    id: 'diff-smr', company: '差异',
    salesCount: self.salesCount - avg.salesCount, salesCost: self.salesCost - avg.salesCost, salesAvg: self.salesAvg - avg.salesAvg,
    mgmtCount: self.mgmtCount - avg.mgmtCount, mgmtCost: self.mgmtCost - avg.mgmtCost, mgmtAvg: self.mgmtAvg - avg.mgmtAvg,
    rdCount: self.rdCount - avg.rdCount, rdCost: self.rdCost - avg.rdCost, rdAvg: self.rdAvg - avg.rdAvg,
  }
})

// AI row-level analysis
const aiAnalysisLoading = ref<string | null>(null)

async function generateRowAnalysis(row: any) {
  if (isReadonly.value) return
  aiAnalysisLoading.value = row.id
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'j1-5-row-analysis',
      prompt: `请分析以下薪酬异常情况并给出可能原因（50字以内简要说明）：岗位"${row.dept}"，本期人均${fmtAmt(row.curAvg)}，上期人均${fmtAmt(row.priorAvg)}，人均变动率${row.avgChangeRate.toFixed(1)}%，行业人均${fmtAmt(row.industryAvg)}，与行业差异${row.industryDiff.toFixed(1)}%。`,
      context: { '岗位': row.dept, '人均变动率': `${row.avgChangeRate.toFixed(1)}%`, '行业差异': `${row.industryDiff.toFixed(1)}%` },
      existingContent: row.analysis || '',
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      updateDeptCell(row.id, 'analysis', text)
      ElMessage.success('AI分析完成')
    }
  } catch { ElMessage.warning('AI分析失败') }
  finally { aiAnalysisLoading.value = null }
}

// AI
const aiLoading = ref<string | null>(null)
async function generateAi(section: 'note' | 'conclusion') {
  if (isReadonly.value) return
  aiLoading.value = section
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: `j1-5-${section}`,
      prompt: section === 'note'
        ? '根据应付职工薪酬同行业对比数据，分析各指标与行业水平差异原因，生成审计说明。'
        : '根据同行业对比数据和审计说明，生成审计结论。',
      context: {
        '本公司人均': fmtAmt(companyTotal.value.curAvg),
        '人均变动率': `${companyTotal.value.avgChangeRate.toFixed(1)}%`,
        '社保差异': `${socialDiff.value}人`,
        '可比公司数': String(peerCompanies.value.length),
      },
      existingContent: section === 'note' ? auditNote.value : auditConclusion.value,
    })
    const text = res.data?.data?.content || res.data?.content
    if (text) {
      if (section === 'note') auditNote.value = text; else auditConclusion.value = text
      saveOpinion()
      ElMessage.success('AI生成完成')
    }
  } catch { ElMessage.warning('AI生成失败') }
  finally { aiLoading.value = null }
}
</script>

<style scoped>
.j1-tab-industry { padding: 12px; }
.j1-tab-industry :deep(.el-table) { font-size: 13px !important; }
.j1-tab-industry :deep(.el-table th), .j1-tab-industry :deep(.el-table td) { font-size: 13px !important; padding: 4px 0 !important; }
.j1-tab-industry :deep(.el-table th .cell) { white-space: normal !important; word-break: break-all; line-height: 1.3; padding: 4px 6px !important; }
.j1-tab-industry :deep(.el-table td .cell) { padding: 2px 6px !important; line-height: 1.4; }
.j1-tab-industry :deep(.el-table--border th) { padding: 4px 0 !important; }
.j1-tab-industry :deep(.el-table .el-input-number) { line-height: 28px; }
.j1-tab-industry :deep(.el-table .el-input--small .el-input__inner) { height: 28px; line-height: 28px; }
.industry-table { font-size: 13px; }
.audit-objective { margin-bottom: 10px; }
.amber-context { border-left: 3px solid #e6a23c; background: #fdf6ec; padding: 10px 14px; border-radius: 4px; margin-bottom: 12px; font-size: 13px; color: #606266; line-height: 1.7; }
.amber-context .amber-title { font-weight: 600; color: #303133; margin-bottom: 4px; }
.amber-context p { margin: 3px 0; }
.stats-cards { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 12px; }
.stat-card { background: #f5f7fa; border-radius: 8px; padding: 14px 16px; text-align: center; border: 1px solid #ebeef5; }
.stat-label { font-size: 12px; color: #909399; margin-bottom: 4px; }
.stat-value { font-size: 18px; font-weight: 700; color: #303133; }
.stat-danger .stat-value { color: #f56c6c; }
.stat-danger { border-color: #fde2e2; background: #fef0f0; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.revenue-input { font-size: 13px; color: #606266; display: flex; align-items: center; gap: 6px; }
.peer-manager { padding: 4px 0; }
.peer-title { font-weight: 600; font-size: 13px; margin-bottom: 8px; color: #303133; }
.peer-item { display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid #f0f0f0; }
.peer-add { display: flex; gap: 6px; margin-top: 8px; }
:deep(.calc-col) { background-color: #f5f7fa !important; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; color: #606266; }
.text-danger { color: #f56c6c; font-weight: 600; }
:deep(.total-row) { background: #f0f5ff !important; font-weight: 600; }
:deep(.total-row td) { border-top: 1px solid #d9ecff !important; }
.analysis-cell { display: flex; align-items: center; gap: 4px; }
.analysis-cell .el-input { flex: 1; }
.ai-btn { padding: 2px 4px; min-width: auto; }
.social-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.social-card :deep(.el-card__header) { padding: 8px 12px; background: #fafafa; }
.social-title { font-size: 13px; font-weight: 600; }
.social-subtotal { padding: 8px 12px; font-size: 13px; color: #303133; border-top: 1px solid #ebeef5; margin-top: 8px; }
.social-diff { padding: 10px 16px; margin-top: 12px; background: #f0f9eb; border-radius: 6px; font-size: 14px; display: flex; align-items: center; gap: 12px; }
.social-diff b { font-size: 18px; color: #67c23a; }
.diff-danger { background: #fef0f0; }
.diff-danger b { color: #f56c6c; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 10px 14px; background: #fafafa; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; }
.opinion-section { margin-bottom: 14px; }
.opinion-section:last-child { margin-bottom: 0; }
.opinion-section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 6px; }
.opinion-section-label { font-size: 13px; font-weight: 500; }
.guidance-details { margin-top: 16px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: 13px; color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
</style>
