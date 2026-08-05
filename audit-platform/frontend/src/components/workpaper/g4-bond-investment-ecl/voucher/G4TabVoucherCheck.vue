<!--
  G4TabVoucherCheck.vue — G4-13 凭证检查表（97行×19列 → 3区段Tab）

  3区段Tab切换（el-segmented）：
  - Tab1: 记账凭证基础列(8列): 日期|凭证编号|业务内容|对方科目|明细科目|借方金额|贷方金额|📎附件
  - Tab2: 支持性文件+核对内容(7列): 支持性文件描述|核对1~6(checkbox)|全部通过badge
  - Tab3: 结论+备注(4列): 索引号|是否异常(自动)|异常说明|备注

  分借方区/贷方区两个区块
  Tab切换行同步：切换Tab保持activeRowIndex
  Tab2: 6项checkbox核对，全✓显示绿色"全部通过"badge
  Tab3: 任一核对✗→自动设isAbnormal=true + 红色高亮
  顶部借贷平衡汇总区（差额红色显示）
  虚拟滚动（97行>50阈值）
  动态行增删 + GtIndexChip索引跳转

  Spec: .kiro/specs/g4-bond-investment-ecl/ Task 9.1
  Requirements: 6.1~6.12, 11.1, 11.5, 11.6, 11.9
-->
<template>
  <div class="g4-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 一、审计目标（对齐纸质底稿三认定） -->
    <el-alert type="info" :closable="false" show-icon class="objective-alert">
      <template #title><span class="ao-title">一、审计目标</span></template>
      <ol class="ao-list">
        <li>资产负债表中记录的债权投资是存在的，且已经记录在恰当的账户中；</li>
        <li>所有应当记录的债权投资交易均已记录；</li>
        <li>债权投资以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录。</li>
      </ol>
    </el-alert>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <G4EclImportExportDropdown
          :wp-id="wpId"
          sheet="G4-13"
          :disabled="isReadonly"
          @imported="emit('imported')"
        />
        <span class="chip-wrap"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-12" :context-project-id="projectId" /></span>
      </div>
      <div class="toolbar-right">
        <el-tag size="small" type="info">借 {{ vc.debitRows.value.length }} · 贷 {{ vc.creditRows.value.length }}</el-tag>
        <el-tag v-if="abnormalCount" size="small" type="danger">异常 {{ abnormalCount }}</el-tag>
        <el-tag size="small" :type="vc.isBalanced.value ? 'success' : 'warning'">
          {{ vc.isBalanced.value ? '借贷平衡' : '借贷不平衡' }}
        </el-tag>
        <span class="chip-wrap"><GtIndexChip value="wp:G4-13" :context-project-id="projectId" /></span>
      </div>
    </div>

    <div class="section-head">
      <h3 class="sheet-title">G4-13 凭证检查表</h3>
      <div class="head-actions">
        <el-segmented v-model="vc.activeTab.value" :options="segmentOptions" size="small" />
        <el-button size="small" type="warning" :disabled="isReadonly" @click="showSampling = !showSampling">
          ⚡ 抽凭
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddDebit">
          + 借方行
        </el-button>
        <el-button size="small" type="success" :disabled="isReadonly" @click="handleAddCredit">
          + 贷方行
        </el-button>
        <el-button size="small" type="warning" plain :disabled="isReadonly" @click="pushAbnormalDrafts">
          推送异常至 G4-3
        </el-button>
        <el-button size="small" @click="openReviewDialog('G4-13-voucher-check')">💬复核</el-button>
      </div>
    </div>

    <!-- 二、样本选取标准与结果 -->
    <el-card shadow="never" class="criteria-card">
      <template #header>
        <div class="card-header-row">
          <span>二、样本选取标准与结果</span>
          <el-button size="small" link type="primary" @click="showMethodGuide = !showMethodGuide">
            {{ showMethodGuide ? '收起方法说明' : '选取方法说明' }}
          </el-button>
        </div>
      </template>
      <div class="criteria-grid">
        <div class="cg-item cg-full">
          <label>测试范围</label>
          <el-input
            v-model="criteria.testScope"
            size="small"
            :disabled="isReadonly"
            placeholder="债权投资科目借方、贷方发生额检查（含减值计提/转回/核销）"
            @change="persistCriteria"
          />
        </div>
        <div class="cg-item">
          <label>抽样总体（笔数 / 金额）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCount" :controls="false" size="small"
              :disabled="isReadonly" placeholder="笔" class="num-sm" @change="persistCriteria" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationAmount" :controls="false" size="small"
              :disabled="isReadonly" placeholder="金额" class="num-md" @change="persistCriteria" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" size="small" :disabled="isReadonly" @change="persistCriteria">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="选取特定项目" value="特定项目" />
            <el-option label="选取全部项目" value="全部项目" />
          </el-select>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input
            v-model="criteria.specificSample"
            size="small"
            :disabled="isReadonly"
            placeholder="超过重要性水平、关联方、异常减值/转回/核销等全部测试，共XX笔"
            @change="persistCriteria"
          />
        </div>
        <div class="cg-item">
          <label>代表性样本量</label>
          <el-input-number v-model="criteria.representativeSize" :controls="false" size="small"
            :disabled="isReadonly" @change="persistCriteria" />
        </div>
        <div class="cg-item">
          <label>已检查金额 / 检查比例</label>
          <div class="cg-inline">
            <span class="ratio-val">{{ fmtNum(checkedAmount) }}</span>
            <el-tag size="small" :type="inspectionRatio >= 0.1 ? 'success' : 'info'">
              {{ (inspectionRatio * 100).toFixed(1) }}%
            </el-tag>
          </div>
        </div>
      </div>
      <div v-if="showMethodGuide" class="method-guide">
        <p><b>（1）选取全部项目：</b>总体较小或存在舞弊风险、重大非常规交易、重大关联方交易、重大估计变更时适用。</p>
        <p><b>（2）选取特定项目：</b>大额、超过阈值、异常或高风险项目；不能推断至总体。</p>
        <p><b>（3）审计抽样：</b>可分层后随机/系统选样；样本量结合置信水平与错报风险判断。预计错报扩展系数参考：1%→1.9；5%→1.6；10%→1.5。</p>
      </div>
    </el-card>

    <!-- 抽凭引擎 -->
    <el-collapse v-if="showSampling && props.wpId && props.projectId && !isReadonly" class="sampling-collapse">
      <el-collapse-item title="⚡ 自动抽凭（科目 1501 债权投资）" name="sampling">
        <GtVoucherSamplingEngine
          account-code="1501"
          phase="final"
          default-method="random"
          :workpaper-id="props.wpId"
          :project-id="props.projectId"
          :year="currentYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <!-- 借贷平衡汇总区 -->
    <div class="balance-summary" :class="{ unbalanced: !vc.isBalanced.value }">
      <span class="balance-item">
        <span class="balance-label">借方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.debitTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">贷方合计：</span>
        <span class="balance-value">{{ fmtNum(vc.creditTotal.value) }}</span>
      </span>
      <span class="balance-item">
        <span class="balance-label">差额：</span>
        <span class="balance-value" :class="{ 'diff-red': !vc.isBalanced.value }">
          {{ fmtNum(vc.difference.value) }}
        </span>
      </span>
      <el-tag v-if="vc.isBalanced.value" type="success" size="small">借贷平衡</el-tag>
      <el-tag v-else type="danger" size="small">借贷不平衡</el-tag>
    </div>

    <p class="section-label">三、测试 · 1. 本期发生额检查（按借贷分区记录）</p>
    <div class="section-block">
      <div class="block-header">（一）借方区</div>
      <el-table
        :data="debitDisplayRows"
        border
        size="small"
        max-height="320"
        highlight-current-row
        row-key="id"
        :row-class-name="getRowClassName"
        class="voucher-table"
        @current-change="onCurrentChange"
      >
        <template v-if="vc.activeTab.value === 'tab1'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" size="small"
                type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
                style="width: 100%" placeholder="选择日期" />
              <span v-else>{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo }}</span>
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" />
              <span v-else>{{ row.businessContent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" />
              <span v-else>{{ row.counterAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="明细科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" />
              <span v-else>{{ row.detailAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.debitAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.creditAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="📎" width="70" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :before-upload="(file: File) => handleRowOcr(row, file)"
                :disabled="isReadonly"
              >
                <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">
                  <el-icon :class="{ 'has-file': row.attachment }"><Paperclip /></el-icon>
                </el-button>
              </el-upload>
            </template>
          </el-table-column>
        </template>

        <!-- Tab2: 支持性文件+核对内容 -->
        <template v-if="vc.activeTab.value === 'tab2'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="支持性文件描述" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.supportingDocDesc" size="small" />
              <span v-else>{{ row.supportingDocDesc }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原始凭证完整" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkOriginalComplete" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="有授权批准" width="95" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAuthorized" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="账务处理正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAccountingCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="初始成本正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInitialCostCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="利息计算正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInterestCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="减值计提正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkImpairmentCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="vc.isAllChecked(row)" type="success" size="small">全部通过</el-tag>
              <el-tag v-else type="info" size="small">待核对</el-tag>
            </template>
          </el-table-column>
        </template>

        <!-- Tab3: 结论+备注 -->
        <template v-if="vc.activeTab.value === 'tab3'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
                placeholder="索引" />
            </template>
          </el-table-column>
          <el-table-column label="是否异常" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && row.isAbnormal" v-model="row.abnormalNote"
                size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.abnormalNote }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 删除操作列（所有Tab共享） -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除？" @confirm="vc.removeRow(row.id)">
              <template #reference>
                <el-icon class="delete-icon"><Delete /></el-icon>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- ═══ 贷方区 ═══ -->
    <div class="section-block">
      <div class="block-header">（二）贷方区</div>
      <el-table
        :data="creditDisplayRows"
        border
        size="small"
        max-height="320"
        highlight-current-row
        row-key="id"
        :row-class-name="getRowClassName"
        class="voucher-table"
        @current-change="onCurrentChange"
      >
        <template v-if="vc.activeTab.value === 'tab1'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="日期" min-width="110">
            <template #default="{ row }">
              <el-date-picker v-if="!isReadonly" v-model="row.date" size="small"
                type="date" format="YYYY-MM-DD" value-format="YYYY-MM-DD"
                style="width: 100%" placeholder="选择日期" />
              <span v-else>{{ row.date }}</span>
            </template>
          </el-table-column>
          <el-table-column label="凭证编号" min-width="100">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" />
              <span v-else>{{ row.voucherNo }}</span>
            </template>
          </el-table-column>
          <el-table-column label="业务内容" min-width="140">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" />
              <span v-else>{{ row.businessContent }}</span>
            </template>
          </el-table-column>
          <el-table-column label="对方科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.counterAccount" size="small" />
              <span v-else>{{ row.counterAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="明细科目" min-width="110">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.detailAccount" size="small" />
              <span v-else>{{ row.detailAccount }}</span>
            </template>
          </el-table-column>
          <el-table-column label="借方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.debitAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.debitAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="贷方金额" min-width="120" align="right">
            <template #default="{ row }">
              <el-input-number v-if="!isReadonly" v-model="row.creditAmount" size="small"
                :controls="false" class="compact-num" />
              <span v-else>{{ fmtNum(row.creditAmount) }}</span>
            </template>
          </el-table-column>
          <el-table-column label="📎" width="70" align="center">
            <template #default="{ row }">
              <el-upload
                :show-file-list="false"
                accept="image/*,.pdf"
                :before-upload="(file: File) => handleRowOcr(row, file)"
                :disabled="isReadonly"
              >
                <el-button size="small" link :loading="ocrLoadingRowId === row.id" :disabled="isReadonly">
                  <el-icon :class="{ 'has-file': row.attachment }"><Paperclip /></el-icon>
                </el-button>
              </el-upload>
            </template>
          </el-table-column>
        </template>

        <!-- Tab2: 支持性文件+核对内容（贷方区） -->
        <template v-if="vc.activeTab.value === 'tab2'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="支持性文件描述" min-width="160">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.supportingDocDesc" size="small" />
              <span v-else>{{ row.supportingDocDesc }}</span>
            </template>
          </el-table-column>
          <el-table-column label="原始凭证完整" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkOriginalComplete" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="有授权批准" width="95" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAuthorized" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="账务处理正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkAccountingCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="初始成本正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInitialCostCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="利息计算正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkInterestCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="减值计提正确" width="100" align="center">
            <template #default="{ row }">
              <el-checkbox v-model="row.checkImpairmentCorrect" :disabled="isReadonly"
                @change="onCheckChange(row)" />
            </template>
          </el-table-column>
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-tag v-if="vc.isAllChecked(row)" type="success" size="small">全部通过</el-tag>
              <el-tag v-else type="info" size="small">待核对</el-tag>
            </template>
          </el-table-column>
        </template>

        <!-- Tab3: 结论+备注（贷方区） -->
        <template v-if="vc.activeTab.value === 'tab3'">
          <el-table-column label="序号" width="50" align="center" fixed>
            <template #default="{ row }">{{ row.seq }}</template>
          </el-table-column>
          <el-table-column label="凭证编号" width="90" fixed>
            <template #default="{ row }">{{ row.voucherNo }}</template>
          </el-table-column>
          <el-table-column label="索引号" width="100">
            <template #default="{ row }">
              <GtIndexChip v-if="row.indexRef" :value="row.indexRef" :context-project-id="projectId" />
              <el-input v-else-if="!isReadonly" v-model="row.indexRef" size="small"
                placeholder="索引" />
            </template>
          </el-table-column>
          <el-table-column label="是否异常" width="85" align="center">
            <template #default="{ row }">
              <el-tag :type="row.isAbnormal ? 'danger' : 'success'" size="small">
                {{ row.isAbnormal ? '是' : '否' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column label="异常说明" min-width="180">
            <template #default="{ row }">
              <el-input v-if="!isReadonly && row.isAbnormal" v-model="row.abnormalNote"
                size="small" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" />
              <span v-else>{{ row.abnormalNote }}</span>
            </template>
          </el-table-column>
          <el-table-column label="备注" min-width="150">
            <template #default="{ row }">
              <el-input v-if="!isReadonly" v-model="row.remark" size="small" />
              <span v-else>{{ row.remark }}</span>
            </template>
          </el-table-column>
        </template>

        <!-- 删除操作列（贷方区） -->
        <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
          <template #default="{ row }">
            <el-popconfirm title="确认删除？" @confirm="vc.removeRow(row.id)">
              <template #reference>
                <el-icon class="delete-icon"><Delete /></el-icon>
              </template>
            </el-popconfirm>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <p class="post-period-hint">
      2. 期后处置、新增检查：可在贷方区或借方区按业务性质登记截止日后事项，并在审计说明中单独说明覆盖范围。
    </p>

    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :show-conclusion="false"
      v-model:note="auditNote"
      note-title="四、审计说明"
      note-placeholder="描述测试过程与结果；评估发现的问题对审计的影响；说明检查比例与样本覆盖。"
      @update:note="saveAuditNote"
    />
    <div class="conclusion-toolbar no-print">
      <el-select
        v-if="!isReadonly"
        v-model="conclusionOption"
        size="small"
        clearable
        placeholder="参考结论"
        style="width: 240px"
        @change="applyConclusionTemplate"
      >
        <el-option label="A. 未见异常" value="A" />
        <el-option label="B. 个别例外已说明" value="B" />
        <el-option label="C. 重大事项/例外" value="C" />
      </el-select>
      <el-button size="small" type="primary" link :disabled="isReadonly || !aiAvailable"
        :loading="aiLoading"
        @click="handleAiConclusion">
        🤖 AI生成
      </el-button>
    </div>
    <G4AuditTextCards
      :wp-id="wpId"
      :is-readonly="isReadonly"
      :show-note="false"
      v-model:conclusion="conclusion"
      conclusion-title="五、审计结论"
      conclusion-placeholder="就存在、完整性、计价分摊认定是否达成作出结论。"
    />

    <details class="prep-hint" open>
      <summary>编制提示 / 选取方法要点</summary>
      <ul>
        <li>先确定测试范围与抽样总体，大额/关联方/异常作特定样本全部测试后再抽样。</li>
        <li>六项核对全部✓后显示「全部通过」；任一✗自动标异常（红色），须填异常说明。</li>
        <li>检查比例 = 已检查借贷金额合计 ÷ 抽样总体金额（总体为 0 时显示 0%）。</li>
        <li>减值计提金额可勾对
          <span class="chip-wrap inline"><GtIndexChip value="wp:G4-10" :context-project-id="projectId" /></span>；
          转回/核销可勾对
          <span class="chip-wrap inline"><GtIndexChip value="wp:G4-12" :context-project-id="projectId" /></span>。
        </li>
        <li>📎 可上传凭证附件 OCR；⚡ 抽凭默认写入当前借贷区。</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * G4TabVoucherCheck.vue — G4-13 凭证检查表（97行×19列→3区段Tab）
 *
 * - el-segmented 切换 Tab1(记账凭证)/Tab2(支持性文件+核对)/Tab3(结论+备注)
 * - 分借方区/贷方区两个区块
 * - Tab2: 6项checkbox，全✓→绿色badge
 * - Tab3: 任一核对✗→自动isAbnormal=true+红色高亮
 * - 顶部借贷平衡汇总
 * - 动态行增删(ElMessageBox.prompt)
 * - GtIndexChip索引跳转
 * - inject openReviewDialog
 * - 集成 GtVoucherSamplingEngine 抽凭引擎
 * - 行级OCR：📎上传→POST /d4/contract-ocr→ElMessageBox确认→merge填入
 */
import { ref, computed, inject, watch, onMounted } from 'vue'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist, snapshotToResponseMap } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'
import { Delete, Paperclip } from '@element-plus/icons-vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { useG4EclVoucherCheck } from '../../composables/useG4EclVoucherCheck'
import { useG4EclFormData } from '../../composables/useG4EclFormData'
import GtIndexChip from '../../GtIndexChip.vue'
import G4AuditTextCards from '../../g4-bond-investment-main/G4AuditTextCards.vue'
import GtVoucherSamplingEngine from '../../voucher-sampling/GtVoucherSamplingEngine.vue'
import G4EclImportExportDropdown from '../G4EclImportExportDropdown.vue'
import type { VoucherCheckRow } from '../../composables/useG4EclFormData'
import type { SampledVoucher, FillMode, Phase } from '../../composables/useSamplingAlgorithms'
import { useG4EclAiGenerate } from '../../composables/useG4EclAiGenerate'
import {
  buildG413AbnormalMemos,
  dispatchG4ExceptionDrafts,
} from '../../composables/g4ExceptionRouting'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
  parseCanonicalJson,
} from '../../composables/g4StorageContract'

const props = defineProps<{
  htmlData: Record<string, any> | null
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const emit = defineEmits<{ imported: [] }>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

const wpIdRef = computed(() => props.wpId)
const { generateAndConfirm, aiAvailable, loading: aiLoading } = useG4EclAiGenerate(wpIdRef)

const vc = useG4EclVoucherCheck()
const conclusion = ref('')
const conclusionOption = ref('')
const showSampling = ref(false)
const showMethodGuide = ref(false)

// ─── 审计说明 / 抽样标准（checklist_responses 持久化） ───────────────────────
const formData = useG4EclFormData({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const rowsLoaded = ref(false)

interface G4SampleCriteria {
  testScope: string
  populationCount: number
  populationAmount: number
  samplingMethod: string
  specificSample: string
  representativeSize: number
}

function emptyCriteria(): G4SampleCriteria {
  return {
    testScope: '债权投资科目借方、贷方发生额检查（含减值计提/转回/核销相关凭证）',
    populationCount: 0,
    populationAmount: 0,
    samplingMethod: '随机选样',
    specificSample: '',
    representativeSize: 0,
  }
}

const criteria = ref<G4SampleCriteria>(emptyCriteria())
const CRITERIA_KEY = G4_ITEM_IDS.G4_13_CRITERIA

function persistCriteria(): void {
  if (props.isReadonly) return
  const payload = buildCanonicalPayload(CRITERIA_KEY, criteria.value)
  formData.debouncedSave(payload.item_id, payload)
}

const abnormalCount = computed(() => vc.rows.value.filter(r => r.isAbnormal).length)

const checkedAmount = computed(() =>
  Math.abs(vc.debitTotal.value) + Math.abs(vc.creditTotal.value),
)

const inspectionRatio = computed(() => {
  const pop = Number(criteria.value.populationAmount) || 0
  if (pop <= 0) return 0
  return Math.min(checkedAmount.value / pop, 9.99)
})

const CONCLUSION_TEMPLATES: Record<string, string> = {
  A: '经检查，所抽查债权投资相关凭证支持性文件完整、授权批准与账务处理未见异常，六项核对通过，借贷勾稽合理。未发现影响存在、完整性及计价分摊认定的错报。',
  B: '经检查，除下列事项外其余样本未见异常：【列示例外凭证编号、差异性质及处理】。其余样本核对通过。请结合索引评价对认定的影响。',
  C: '经检查发现重大事项或例外：【性质、金额、对报表影响及建议调整】。在未完成调查/调整前，不能仅依赖本表对相关认定形成无保留结论。',
}

function applyConclusionTemplate(opt: string): void {
  if (!opt || props.isReadonly) return
  const text = CONCLUSION_TEMPLATES[opt]
  if (text) conclusion.value = text
}

const NOTE_KEY = 'G4-13-voucher-check-audit-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  formData.debouncedSave(NOTE_KEY, { remark: val })
}

const CONCLUSION_KEY = 'G4-13-voucher-check-conclusion'
watch(conclusion, (val) => {
  if (props.isReadonly) return
  formData.debouncedSave(CONCLUSION_KEY, { conclusion: null, remark: val })
})

watch(
  vc.rows,
  (rows) => {
    if (!rowsLoaded.value || props.isReadonly) return
    const payload = buildCanonicalPayload(G4_ITEM_IDS.G4_13_ROWS, rows)
    formData.debouncedSave(payload.item_id, payload)
  },
  { deep: true },
)

// ─── 当前年份（从htmlData或默认） ────────────────────────────────────────────

const currentYear = computed(() => {
  const bsDate = props.htmlData?.bsDate as string | undefined
  if (bsDate && bsDate.length >= 4) return parseInt(bsDate.slice(0, 4), 10)
  return new Date().getFullYear() - 1
})

// ─── 区段Tab选项 ─────────────────────────────────────────────────────────────

const segmentOptions = [
  { label: '记账凭证', value: 'tab1' },
  { label: '支持性文件+核对', value: 'tab2' },
  { label: '结论+备注', value: 'tab3' },
]

// ─── 显示行 ─────────────────────────────────────────────────────────────────

const debitDisplayRows = computed(() => vc.debitRows.value)
const creditDisplayRows = computed(() => vc.creditRows.value)

// ─── 行同步（activeRowIndex 跨Tab保持） ─────────────────────────────────────

function onCurrentChange(row: VoucherCheckRow | null) {
  if (!row) return
  const allRows = vc.rows.value
  const idx = allRows.findIndex(r => r.id === row.id)
  if (idx >= 0) vc.activeRowIndex.value = idx
}

// ─── 行样式（Tab3异常行红色高亮） ───────────────────────────────────────────

function getRowClassName({ row }: { row: VoucherCheckRow }): string {
  if (row.isAbnormal) return 'row-abnormal'
  return ''
}

// ─── 核对checkbox变更 → 自动重算异常状态 ────────────────────────────────────

function onCheckChange(row: VoucherCheckRow): void {
  vc.recalcAbnormal(row)
}

// ─── 动态行增删 ─────────────────────────────────────────────────────────────

async function handleAddDebit() {
  await vc.addRow('debit')
}

async function handleAddCredit() {
  await vc.addRow('credit')
}

function pushAbnormalDrafts(): void {
  const drafts = buildG413AbnormalMemos(vc.rows.value)
  if (!drafts.length) {
    ElMessage.info('没有可推送的异常凭证')
    return
  }
  dispatchG4ExceptionDrafts(drafts, formData.allResponses.value)
  ElMessage.success(`已推送 ${drafts.length} 条 G4-3 异常备忘`)
}

// ─── 抽凭引擎集成（Requirements: 6.3, 9.2） ─────────────────────────────────

const methodologyStore = ref(snapshotToResponseMap(props.htmlData))
const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
async function methodologyDirectPersist(itemId: string, remark: string) {
  // 无 allResponses 的宿主：写库同时更新本地只读表，供 bar 即时反映
  methodologyStore.value.set(itemId, { remark })
  await rawMethodologyPersist(itemId, remark)
}
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'G4',
  allResponses: methodologyStore,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  // 将抽样结果映射为 fillVoucherSamples 所需格式
  const mappedSamples = payload.samples.map(s => ({
    voucherNo: s.voucherNo,
    date: s.voucherDate || '',
    businessContent: s.summary || '',
    counterAccount: s.counterpartAccount || '',
    detailAccount: s.accountName || '',
    debitAmount: s.debitAmount ? parseFloat(s.debitAmount) : 0,
    creditAmount: s.creditAmount ? parseFloat(s.creditAmount) : 0,
    section: (s.debitAmount && parseFloat(s.debitAmount) > 0 ? 'debit' : 'credit') as 'debit' | 'credit',
  }))
  vc.fillVoucherSamples(mappedSamples)
  ElMessage.success(`已填入 ${mappedSamples.length} 条抽凭样本`)
}

// ─── 行级OCR（Requirements: 6.4, 9.3） ──────────────────────────────────────

const ocrLoadingRowId = ref<string | null>(null)

/** OCR字段映射：OCR识别字段名 → VoucherCheckRow字段名 */
const OCR_FIELD_MAP: Record<string, keyof VoucherCheckRow> = {
  date: 'date',
  凭证日期: 'date',
  voucher_date: 'date',
  voucher_no: 'voucherNo',
  凭证号: 'voucherNo',
  凭证编号: 'voucherNo',
  summary: 'businessContent',
  摘要: 'businessContent',
  business_content: 'businessContent',
  业务内容: 'businessContent',
  counter_account: 'counterAccount',
  对方科目: 'counterAccount',
  detail_account: 'detailAccount',
  明细科目: 'detailAccount',
  debit_amount: 'debitAmount',
  借方金额: 'debitAmount',
  credit_amount: 'creditAmount',
  贷方金额: 'creditAmount',
  amount: 'debitAmount',
  金额: 'debitAmount',
}

/**
 * 将OCR识别结果映射为VoucherCheckRow可merge的字段对象
 */
function mapOcrToVoucherFields(fields: Record<string, any>): Partial<VoucherCheckRow> {
  const patch: Partial<VoucherCheckRow> = {}
  for (const [ocrKey, val] of Object.entries(fields)) {
    const target = OCR_FIELD_MAP[ocrKey]
    if (target && val != null && String(val).trim() !== '') {
      if (target === 'debitAmount' || target === 'creditAmount') {
        const num = parseFloat(String(val).replace(/,/g, ''))
        if (!isNaN(num)) (patch as any)[target] = num
      } else {
        (patch as any)[target] = String(val).trim()
      }
    }
  }
  return patch
}

/**
 * 渲染OCR识别结果预览HTML
 */
function renderOcrPreview(fields: Record<string, any>): string {
  const patch = mapOcrToVoucherFields(fields)
  const LABEL_MAP: Record<string, string> = {
    date: '日期',
    voucherNo: '凭证编号',
    businessContent: '业务内容',
    counterAccount: '对方科目',
    detailAccount: '明细科目',
    debitAmount: '借方金额',
    creditAmount: '贷方金额',
  }
  const lines = Object.entries(patch)
    .filter(([, v]) => v != null && String(v) !== '')
    .map(([k, v]) => `<div style="margin:4px 0"><b>${LABEL_MAP[k] || k}：</b>${v}</div>`)
  if (lines.length === 0) return '<div>未识别到可填充字段</div>'
  return `<div style="font-size:14px">${lines.join('')}</div>`
}

/**
 * 行级OCR处理：上传→OCR识别→确认→填入
 */
async function handleRowOcr(row: VoucherCheckRow, file: File): Promise<boolean> {
  if (props.isReadonly || !props.wpId) return false
  ocrLoadingRowId.value = row.id
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const fields: Record<string, any> = (res.data?.data ?? res.data)?.extracted_fields || {}
    if (!Object.keys(fields).length) {
      ElMessage.info('OCR完成，未识别到可填充字段')
      return false
    }
    const patch = mapOcrToVoucherFields(fields)
    if (Object.keys(patch).length === 0) {
      ElMessage.info('OCR完成，识别字段无法匹配当前行')
      return false
    }
    // 确认弹窗
    await ElMessageBox.confirm(renderOcrPreview(fields), 'OCR识别结果', {
      confirmButtonText: '填入',
      cancelButtonText: '取消',
      dangerouslyUseHTMLString: true,
    })
    // 合并填入
    Object.assign(row, patch)
    row.attachment = file.name
    ElMessage.success('已填入OCR识别结果')
  } catch (e: any) {
    if (e !== 'cancel' && e?.toString?.() !== 'cancel') {
      ElMessage.warning('OCR识别失败或已取消')
    }
  } finally {
    ocrLoadingRowId.value = null
  }
  return false // 阻止el-upload默认上传行为
}

// ─── AI生成审计结论 ─────────────────────────────────────────────────────────

async function handleAiConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-check-conclusion',
    conclusion.value || '',
    {
      借方行数: vc.debitRows.value.length,
      贷方行数: vc.creditRows.value.length,
      异常行数: abnormalCount.value,
      借贷平衡: vc.isBalanced.value,
      检查比例: `${(inspectionRatio.value * 100).toFixed(1)}%`,
      抽样方法: criteria.value.samplingMethod,
      抽样总体金额: criteria.value.populationAmount,
    },
    'AI 审计结论',
  )
  if (text) conclusion.value = text
}

// ─── 数字格式化 ─────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') {
    return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  }
  return String(v ?? '')
}

// ─── 数据加载 ───────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadAll()

  const storedRows = formData.allResponses.value.get(G4_ITEM_IDS.G4_13_ROWS)
  const storedRowsJson = parseCanonicalJson(storedRows)
  if (storedRowsJson !== null) {
    vc.loadRows(parseCanonicalArray(storedRows) as VoucherCheckRow[])
  } else if (props.htmlData?.voucherCheck) {
    vc.loadRows(props.htmlData.voucherCheck.rows || [])
  }

  if (props.htmlData?.voucherCheck?.conclusion) {
    conclusion.value = props.htmlData.voucherCheck.conclusion
  }
  const note = formData.allResponses.value.get(NOTE_KEY)
  if (note?.remark) auditNote.value = note.remark
  const conc = formData.allResponses.value.get(CONCLUSION_KEY)
  if (conc?.remark) conclusion.value = conc.remark
  const storedCriteria = parseCanonicalJson<Partial<G4SampleCriteria>>(
    formData.allResponses.value.get(CRITERIA_KEY),
  )
  if (storedCriteria && typeof storedCriteria === 'object') {
    criteria.value = { ...emptyCriteria(), ...storedCriteria }
  }
  rowsLoaded.value = true
})

// ─── 暴露序列化接口供父组件保存使用 ─────────────────────────────────────────

defineExpose({
  toJSON: () => ({
    ...vc.toJSON(),
    conclusion: conclusion.value,
    criteria: criteria.value,
  }),
})
</script>

<style scoped>
.g4-voucher-check {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}

/* 工具栏索引 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.tab-toolbar .toolbar-left { display: flex; gap: 8px; align-items: center; }
.tab-toolbar .toolbar-right { display: flex; gap: 6px; align-items: center; }
.tab-toolbar .chip-wrap { display: inline-flex; align-items: center; }

.conclusion-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
}

.head-actions {
  display: flex;
  gap: 8px;
  align-items: center;
}

/* 借贷平衡汇总区 */
.balance-summary {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 8px 12px;
  border-radius: 6px;
  background: #f0f9eb;
  border: 1px solid #e1f3d8;
  margin-bottom: 12px;
  transition: all 0.2s;
}

.balance-summary.unbalanced {
  background: #fef0f0;
  border-color: #fde2e2;
}

.balance-item {
  display: flex;
  align-items: center;
  gap: 4px;
}

.balance-label {
  color: #606266;
  font-size: var(--wp-font-size, 13px);
}

.balance-value {
  font-weight: 600;
  font-size: 14px;
  color: #303133;
}

.diff-red {
  color: #f56c6c !important;
  font-weight: 700;
}

/* 区块 */
.section-block {
  margin-bottom: 16px;
}

.block-header {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
  margin-bottom: 8px;
  padding: 4px 8px;
  background: #ecf5ff;
  border-radius: 4px;
  border-left: 3px solid #409eff;
}

/* 表格 */
.voucher-table {
  font-size: var(--wp-font-size, 13px);
}

.compact-num {
  width: 100%;
}

.compact-num :deep(.el-input__inner) {
  text-align: right;
}

/* 异常行：红色高亮 */
:deep(.row-abnormal) {
  background-color: #fef0f0 !important;
}
:deep(.row-abnormal td) {
  background-color: #fef0f0 !important;
}

/* 附件图标 */
.attach-icon {
  cursor: pointer;
  color: #909399;
  font-size: 16px;
  transition: color 0.2s;
}
.attach-icon:hover {
  color: #409eff;
}
.attach-icon.has-file {
  color: #67c23a;
}

/* 抽凭引擎折叠区 */
.sampling-collapse {
  margin-bottom: 12px;
}
.sampling-collapse :deep(.el-collapse-item__header) {
  font-size: var(--wp-font-size, 13px);
  font-weight: 500;
  color: #e6a23c;
}

/* el-upload行级OCR按钮 */
.has-file {
  color: #67c23a !important;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

.conclusion-toolbar {
  display: flex;
  justify-content: flex-end;
  align-items: center;
  gap: 8px;
  margin-top: 14px;
  flex-wrap: wrap;
}

.objective-alert { margin-bottom: 12px; }
.ao-title { font-weight: 600; }
.ao-list {
  margin: 6px 0 0;
  padding-left: 18px;
  font-size: 12px;
  line-height: 1.7;
  color: #606266;
}

.section-label {
  margin: 12px 0 8px;
  font-size: 13px;
  font-weight: 600;
  color: #303133;
}

.post-period-hint {
  margin: 8px 0 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.6;
}

.criteria-card { margin-bottom: 12px; }
.card-header-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 600;
}
.criteria-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px 16px;
}
.cg-item label {
  display: block;
  font-size: 12px;
  color: #909399;
  margin-bottom: 4px;
}
.cg-full { grid-column: 1 / -1; }
.cg-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.cg-unit { font-size: 12px; color: #909399; }
.num-sm { width: 88px; }
.num-md { width: 140px; }
.ratio-val { font-weight: 600; color: #303133; }
.method-guide {
  margin-top: 10px;
  padding: 8px 10px;
  background: #fafafa;
  border-radius: 4px;
  font-size: 12px;
  color: #606266;
  line-height: 1.7;
}
.method-guide p { margin: 0 0 4px; }

.chip-wrap.inline {
  display: inline-flex;
  vertical-align: middle;
}

/* 编制提示 */
.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
.prep-hint li {
  margin-bottom: 4px;
}
</style>
