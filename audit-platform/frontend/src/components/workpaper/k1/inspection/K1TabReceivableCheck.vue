<!--
  K1TabReceivableCheck.vue — K1-12 其他应收款检查表（凭证级测试）

  忠实反映致同源模板 K1-12 结构：
    一、审计目标（存在/权利义务/计价分摊 三认定）
    二、样本选取标准与规模（测试总体/特定样本/抽样总体/样本量/抽样方法/抽样过程）
    三、测试（1.本期发生额检查 2.期后收款检查，凭证级明细 + 抽凭引擎 + 核对内容勾选）
    四、审计说明（检查比例表：本期借方/本期贷方/期末余额 → 账面/检查/比例）
    五、审计结论

  Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6 | Requirements: 8.4-8.6
-->
<template>
  <div class="k1-tab-receivable-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <!-- 顶部引导区 -->
    <div class="guide-banner">
      <div class="guide-step"><span class="gs-no">1</span>确认审计目标（三认定）</div>
      <div class="guide-step"><span class="gs-no">2</span>填写样本选取标准与规模</div>
      <div class="guide-step"><span class="gs-no">3</span>抽凭执行凭证级测试</div>
      <div class="guide-step"><span class="gs-no">4</span>核对检查比例，形成结论</div>
    </div>

    <!-- 标题栏 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-12 其他应收款检查表</h3>
      <div class="head-actions">
        <el-tag size="small" type="info">本期 {{ occurrenceRows.length }} · 期后 {{ postCollectionRows.length }}</el-tag>
        <el-tag v-if="abnormalRows.length" size="small" type="danger">异常 {{ abnormalRows.length }}</el-tag>
        <el-tag v-if="incompleteCheckRows.length" size="small" type="warning">待核对 {{ incompleteCheckRows.length }}</el-tag>
        <el-button size="small" type="primary" link @click="handleAiGenerate">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">💬 复核</el-button>
      </div>
    </div>

    <!-- 一、审计目标 -->
    <el-alert type="info" :closable="false" class="audit-objective">
      <template #title>
        <span class="ao-title">一、审计目标（认定）</span>
      </template>
      <ol class="ao-list">
        <li><b>存在：</b>资产负债表中记录的其他应收款是存在的，且已记录在恰当的账户中；</li>
        <li><b>权利和义务：</b>记录的其他应收款由被审计单位拥有或控制；</li>
        <li><b>计价和分摊：</b>其他应收款以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。</li>
      </ol>
    </el-alert>

    <!-- 二、样本选取标准与规模 -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">二、样本选取标准与规模</span>
          <div class="hdr-btns">
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="importFromK1">从 K1-1/K1-2 带入</el-button>
            <el-button v-if="!isReadonly" size="small" plain @click="importFromK5">从 K1-5 带入大额</el-button>
            <el-button v-if="!isReadonly" size="small" @click="onRecalcSampling">重算抽样总体</el-button>
          </div>
        </div>
      </template>
      <div class="criteria-grid">
        <div class="cg-item">
          <label>测试总体（借方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationDebitCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationDebitAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>测试总体（贷方）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.populationCreditCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.populationCreditAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>特定样本</label>
          <el-input v-model="criteria.specificSample" :disabled="isReadonly" size="small"
            placeholder="大额（XX金额以上）、关联方/关联交易形成的款项、异常款项全部测试" @change="persist" />
        </div>
        <div class="cg-item">
          <label>特定样本笔数</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.specificSampleCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" :min="0" @change="onSpecificSampleChange" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>特定样本金额</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.specificSampleAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" :min="0" @change="onSpecificSampleChange" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样总体（测试总体 − 特定样本）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.samplingPopulationCount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="笔数" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
            <el-input-number v-model="criteria.samplingPopulationAmount" :controls="false" :disabled="isReadonly"
              size="small" placeholder="金额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样样本量</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.sampleSize" :controls="false" :disabled="isReadonly"
              size="small" placeholder="样本量" class="num-sm" @change="persist" />
            <span class="cg-unit">笔</span>
          </div>
        </div>
        <div class="cg-item">
          <label>抽样方法</label>
          <el-select v-model="criteria.samplingMethod" :disabled="isReadonly" size="small" @change="persist">
            <el-option label="随机选样" value="随机选样" />
            <el-option label="系统选样" value="系统选样" />
            <el-option label="货币单元抽样" value="货币单元抽样" />
            <el-option label="随意选样（非统计抽样）" value="随意选样" />
          </el-select>
        </div>
        <div class="cg-item">
          <label>账面本期借方（检查比例分母，勾 K1-1）</label>
          <el-input-number v-model="criteria.bookDebitOccurrence" :controls="false" :disabled="isReadonly"
            size="small" placeholder="账面借方" class="num-md" @change="persist" />
        </div>
        <div class="cg-item">
          <label>账面本期贷方（检查比例分母，勾 K1-1）</label>
          <el-input-number v-model="criteria.bookCreditOccurrence" :controls="false" :disabled="isReadonly"
            size="small" placeholder="账面贷方" class="num-md" @change="persist" />
        </div>
        <div class="cg-item">
          <label>期末余额（检查比例基准，勾 K1-2）</label>
          <div class="cg-inline">
            <el-input-number v-model="criteria.endBalance" :controls="false" :disabled="isReadonly"
              size="small" placeholder="期末余额" class="num-md" @change="persist" />
            <span class="cg-unit">元</span>
          </div>
        </div>
        <div class="cg-item cg-full">
          <label>抽样过程</label>
          <el-input v-model="criteria.samplingProcess" type="textarea" :autosize="{ minRows: 2 }"
            :disabled="isReadonly" size="small"
            placeholder="使用IDEA（XX抽样工具）选择XX数量、金额XX的样本进行测试，抽样工具中的样本选择过程和结果见相关底稿" @change="persist" />
        </div>
      </div>
      <el-alert type="warning" :closable="false" show-icon class="criteria-tip">
        选取路径：全部项目 → 特定项目（大额/关联方/异常全测）→ 审计抽样。特定项目≠审计抽样。
      </el-alert>
      <el-alert v-if="sampleSizeDeviation?.needsExpansion" type="warning" :closable="false" show-icon class="criteria-tip">
        本期实际检查 {{ sampleSizeDeviation.actual }} 笔，少于计划样本量 {{ sampleSizeDeviation.planned }} 笔，应补抽或说明原因。
      </el-alert>
    </el-card>

    <!-- 三、测试 -->
    <el-alert
      v-if="deeplinkHint"
      type="info"
      :closable="false"
      show-icon
      class="deeplink-bar"
    >
      <template #title>
        <span>{{ deeplinkHint }}</span>
        <el-button size="small" link type="primary" style="margin-left: 8px" @click="clearDeeplink">清除筛选</el-button>
      </template>
    </el-alert>
    <div class="filter-bar">
      <el-input v-model="voucherFilter" placeholder="筛选债务人..." size="small" clearable class="search-input" />
      <el-radio-group v-model="viewMode" size="small">
        <el-radio-button value="table">完整表格</el-radio-button>
        <el-radio-button value="card">逐笔核对</el-radio-button>
      </el-radio-group>
    </div>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 1. 本期发生额检查</span>
          <div>
            <el-tag size="small" type="info" effect="plain" class="check-legend">核对：1完整 2相符 3处理 4期间 5对手</el-tag>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('occurrence')">
              <el-icon><MagicStick /></el-icon> 抽凭
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="addOccurrenceRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <p class="check-desc">测试内容说明：{{ checkLabels.map((l, i) => `${i + 1}.${l}`).join('；') }}</p>

      <!-- 卡片视图 -->
      <div v-if="viewMode === 'card'" class="k1vc-card-grid">
        <el-empty v-if="!filteredOccurrenceRows.length" description="暂无本期发生额检查行" :image-size="64" />
        <div
          v-for="row in filteredOccurrenceRows"
          :key="row.id"
          class="k1vc-vcard"
          :class="{ 'is-abnormal': row.abnormal }"
          @click="openVoucher(row, 'occurrence')"
        >
          <div class="k1vc-vcard-head">
            <span class="k1vc-vcard-title">{{ row.debtorName || row.voucherNo || '未命名' }}</span>
            <el-tag size="small" :type="cardStatus(row).type">{{ cardStatus(row).label }}</el-tag>
          </div>
          <div class="k1vc-vcard-meta">{{ row.voucherNo || '无凭证号' }} · {{ row.date || '无日期' }}</div>
          <div class="k1vc-vcard-amt">借 {{ fmtAmt(row.debitAmount) }} / 贷 {{ fmtAmt(row.creditAmount) }}</div>
        </div>
      </div>

      <el-table v-else ref="occurrenceTableRef" :data="filteredOccurrenceRows" border size="small" :max-height="360" class="voucher-table"
        row-key="id"
        :row-class-name="voucherRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="债务人名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" />
            <span v-else>{{ row.businessContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方明细" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetSubAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="借方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.debitAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.debitAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="贷方金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" @change="persist" />
            <span v-else>{{ row.supportingDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" width="168" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content>
                <div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div>
              </template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group"
              @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCR" width="72" align="center" fixed="right">
          <template #default="{ row }">
            <el-upload
              v-if="!isReadonly"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              :disabled="ocrLoading"
              @change="(f: any) => onRowOcr(row, 'occurrence', f?.raw)"
            >
              <el-button link size="small" type="primary" :loading="ocrLoading">
                {{ row.ocrAttachment ? '✓' : '📎' }}
              </el-button>
            </el-upload>
            <span v-else-if="row.ocrAttachment" class="ocr-ok">✓</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openVoucher(row, 'occurrence')">核对</el-button>
            <el-button v-if="!isReadonly" size="small" type="danger" link @click="removeOccurrenceRow(row.id); persist()">删</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　借方：{{ fmtAmt(occurrenceDebitChecked) }}　贷方：{{ fmtAmt(occurrenceCreditChecked) }}</div>
        </template>
      </el-table>
    </el-card>

    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="card-header-row">
          <span class="card-title">三、测试 — 2. 期后收款检查</span>
          <div>
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="openSampling('post')">
              <el-icon><MagicStick /></el-icon> 抽凭
            </el-button>
            <el-button v-if="!isReadonly" size="small" @click="addPostCollectionRow(); persist()">＋ 手工新增</el-button>
          </div>
        </div>
      </template>
      <p class="check-desc">验证截止日后回款，佐证期末余额真实性；核对内容与本期发生额检查一致。</p>

      <div v-if="viewMode === 'card'" class="k1vc-card-grid">
        <el-empty v-if="!filteredPostCollectionRows.length" description="暂无期后收款检查行" :image-size="64" />
        <div
          v-for="row in filteredPostCollectionRows"
          :key="row.id"
          class="k1vc-vcard"
          :class="{ 'is-abnormal': row.abnormal }"
          @click="openVoucher(row, 'post')"
        >
          <div class="k1vc-vcard-head">
            <span class="k1vc-vcard-title">{{ row.debtorName || row.voucherNo || '未命名' }}</span>
            <el-tag size="small" :type="cardStatus(row).type">{{ cardStatus(row).label }}</el-tag>
          </div>
          <div class="k1vc-vcard-meta">{{ row.voucherNo || '无凭证号' }} · {{ row.date || '无日期' }}</div>
          <div class="k1vc-vcard-amt">收款 {{ fmtAmt(row.creditAmount) }}</div>
        </div>
      </div>

      <el-table v-else ref="postTableRef" :data="filteredPostCollectionRows" border size="small" :max-height="300" class="voucher-table"
        row-key="id"
        :row-class-name="voucherRowClass">
        <el-table-column label="#" type="index" width="42" align="center" />
        <el-table-column label="债务人名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.debtorName" size="small" @change="persist" />
            <span v-else>{{ row.debtorName || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="日期" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.date" size="small" placeholder="YYYY-MM-DD" @change="persist" />
            <span v-else>{{ row.date || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="凭证编号" width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.voucherNo" size="small" @change="persist" />
            <span v-else>{{ row.voucherNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="业务内容" min-width="150">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.businessContent" size="small" @change="persist" />
            <span v-else>{{ row.businessContent || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方科目" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="对方明细" min-width="100">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.offsetSubAccount" size="small" @change="persist" />
            <span v-else>{{ row.offsetSubAccount || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="收款金额" min-width="110" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" v-model="row.creditAmount" :controls="false" size="small"
              class="amount-input" @change="persist" />
            <span v-else class="amount-cell">{{ fmtAmt(row.creditAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性文件" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.supportingDoc" size="small" @change="persist" />
            <span v-else>{{ row.supportingDoc || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="核对内容" width="168" align="center">
          <template #header>
            <el-tooltip placement="top">
              <template #content>
                <div v-for="(lbl, i) in checkLabels" :key="i">{{ i + 1 }}. {{ lbl }}</div>
              </template>
              <span class="col-help">核对内容 ⓘ</span>
            </el-tooltip>
          </template>
          <template #default="{ row }">
            <el-checkbox-group :model-value="checkedValues(row)" :disabled="isReadonly" class="check-group"
              @update:model-value="(v: any) => setChecks(row, v as number[])">
              <el-checkbox v-for="(_, i) in checkLabels" :key="i" :value="i" :label="i + 1" />
            </el-checkbox-group>
          </template>
        </el-table-column>
        <el-table-column label="是否异常" width="80" align="center">
          <template #default="{ row }">
            <el-switch v-model="row.abnormal" :disabled="isReadonly" size="small" @change="persist" />
          </template>
        </el-table-column>
        <el-table-column label="索引号" width="90">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.indexNo" size="small" @change="persist" />
            <span v-else>{{ row.indexNo || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注说明" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.remark" size="small" @change="persist" />
            <span v-else>{{ row.remark || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="OCR" width="72" align="center" fixed="right">
          <template #default="{ row }">
            <el-upload
              v-if="!isReadonly"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg,.webp"
              :disabled="ocrLoading"
              @change="(f: any) => onRowOcr(row, 'post', f?.raw)"
            >
              <el-button link size="small" type="primary" :loading="ocrLoading">
                {{ row.ocrAttachment ? '✓' : '📎' }}
              </el-button>
            </el-upload>
            <span v-else-if="row.ocrAttachment" class="ocr-ok">✓</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openVoucher(row, 'post')">核对</el-button>
            <el-button v-if="!isReadonly" size="small" type="danger" link @click="removePostCollectionRow(row.id); persist()">删</el-button>
          </template>
        </el-table-column>
        <template #append>
          <div class="table-total">合计　期后收款：{{ fmtAmt(postCollectionChecked) }}</div>
        </template>
      </el-table>
    </el-card>

    <!-- 四、审计说明（检查比例表）-->
    <el-card shadow="never" class="section-card">
      <template #header>
        <span class="card-title">四、审计说明 — 检查比例</span>
      </template>
      <el-table :data="checkRatios" border size="small" class="ratio-table">
        <el-table-column label="方向" prop="direction" width="120" />
        <el-table-column label="账面金额" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ row.bookAmount > 0 ? fmtAmt(row.bookAmount) : '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="检查金额" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.checkedAmount) }}</span></template>
        </el-table-column>
        <el-table-column label="检查比例" width="130" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.ratio != null" :type="row.ratio < 0.3 ? 'danger' : row.ratio < 0.6 ? 'warning' : 'success'"
              size="small" effect="plain">
              {{ (row.ratio * 100).toFixed(1) }}%
            </el-tag>
            <span v-else class="muted" title="分母为零时不显示比例（避免 #DIV/0!）">—</span>
          </template>
        </el-table-column>
      </el-table>
      <el-alert v-if="lowRatioWarnings.length > 0" type="warning" :closable="false" show-icon class="ratio-warn">
        <template #title>检查比例偏低（&lt;30%）：{{ lowRatioWarnings.map(r => r.direction).join('、') }}，应扩大检查样本量或说明原因</template>
      </el-alert>
      <div v-if="lowRatioWarnings.length > 0" class="note-block">
        <label>检查比例偏低说明（必填）</label>
        <el-input v-model="lowRatioExplanation" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
          placeholder="说明检查比例偏低的原因，或已采取的扩大样本量措施" @change="persist" />
      </div>
      <div class="note-block">
        <label>审计说明</label>
        <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 3 }" :disabled="isReadonly"
          placeholder="概述测试情况、结果；拟调整事项及分录、未调整事项及其影响等" @change="persist" />
      </div>
    </el-card>

    <!-- 异常凭证摘要 -->
    <div v-if="abnormalRows.length > 0" class="abnormal-summary">
      <div class="as-header">
        ⚠️ 异常凭证摘要（{{ abnormalRows.length }} 笔）
        <el-button v-if="!isReadonly" size="small" type="danger" plain class="push-btn" @click="pushAbnormalToK14">
          推送 K1-4
        </el-button>
      </div>
      <ul class="as-list">
        <li v-for="r in abnormalRows" :key="r.id">
          <b>{{ r.debtorName || '（未填债务人）' }}</b> — 凭证 {{ r.voucherNo || '-' }}：{{ r.remark || '未说明' }}
        </li>
      </ul>
    </div>

    <!-- 五、审计结论 -->
    <el-card shadow="never" class="conclusion-card">
      <template #header><span class="card-title">五、审计结论</span></template>
      <el-select v-model="conclusionOption" :disabled="isReadonly" size="small" class="concl-select"
        placeholder="选择结论模板" @change="onConclusionOption">
        <el-option label="A、未见异常" value="A" />
        <el-option label="B、除上述重大不符事项作为调整事项予以调整外，其余未见异常" value="B" />
        <el-option label="C、由于存在重大未调整事项（或审计范围受限），不可确认" value="C" />
      </el-select>
      <el-input v-model="conclusion" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="基于上述检查情况，形成综合审计结论..." @change="persist" />
    </el-card>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示（CAS 1231 / CAS 1314）</summary>
      <ul>
        <li>审计目标对应三项认定：存在、权利和义务、计价和分摊</li>
        <li>样本选取：测试总体扣除特定样本得抽样总体；大额、关联方、异常款项应全部测试</li>
        <li>五项核对：原始凭证完整、账务相符、会计处理、会计期间、债务人对手一致</li>
        <li>本期发生额检查：关注贷方非收款减少、借方其他调整；逐笔核对凭证与原始单据</li>
        <li>期后收款检查：截止日后回款金额与期末余额比对，验证期末余额真实性</li>
        <li>检查比例分母可「从 K1-1/K1-2 带入」自动勾稽（对齐 Excel E61–E63 公式）</li>
        <li>特定样本可从 K1-5 大额分析带入；抽样总体 = 测试总体 − 特定样本</li>
        <li>异常凭证可一键推送 K1-4 调整分录备忘（金额待追查补录）</li>
        <li>检查比例 = 检查金额 / 账面金额；比例偏低（&lt;30%）须扩样或填写说明</li>
        <li>抽凭引擎复用序时账，按方法/科目（1221）选凭证号一键回填</li>
      </ul>
    </details>

    <!-- 抽凭引擎对话框 -->
    <el-dialog v-model="samplingVisible" title="抽凭引擎 — 其他应收款(1221)" width="90%" top="5vh" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="samplingVisible"
        account-code="1221"
        :phase="samplingTarget === 'occurrence' ? 'current' : 'post'"
        :workpaper-id="props.wpId"
        :project-id="props.projectId"
        :year="year"
        @filled="onSamplesFilled"
      />
    </el-dialog>

    <K1VoucherCheckDialog
      v-model="voucherDialogVisible"
      :row="voucherDialogRow"
      :mode="voucherDialogMode"
      :readonly="isReadonly"
      @save="handleSaveVoucher"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabReceivableCheck.vue — K1-12 其他应收款检查表（凭证级测试）
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6 | Requirements: 8.4-8.6
 */
import { ref, computed, inject, toRef, onMounted, nextTick, defineAsyncComponent } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import type { ElTable } from 'element-plus'
import { useK1VoucherCheck, k1VoucherCardStatus, type K1VoucherRow } from '../../composables/useK1VoucherCheck'
import { useK1VoucherOcr } from '../../composables/useK1VoucherOcr'
import {
  K1RowNavigationKey,
  applyK1IncomingFocus,
  buildK1DeeplinkHint,
} from '../../composables/useK1RowNavigation'

import { injectK1Adjustments } from '../../composables/k1AdjustmentInject'
import { useK1AiGenerate } from '../../composables/useK1AiGenerate'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const K1_12_ADJ_SOURCE = 'k1-12-voucher'

const GtVoucherSamplingEngine = defineAsyncComponent(
  () => import('../../voucher-sampling/GtVoucherSamplingEngine.vue')
)
const K1VoucherCheckDialog = defineAsyncComponent(
  () => import('./K1VoucherCheckDialog.vue')
)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const k1Nav = inject(K1RowNavigationKey, null)
const { generateAndConfirm } = useK1AiGenerate(toRef(props, 'wpId'))
const voucherFilter = ref('')
const deeplinkHint = ref('')
const occurrenceTableRef = ref<InstanceType<typeof ElTable>>()
const postTableRef = ref<InstanceType<typeof ElTable>>()

const year = computed(() => props.year ?? new Date().getFullYear())

const allResponsesRef = computed(() => props.allResponses)

const {
  itemId, checkLabels,
  criteria, occurrenceRows, postCollectionRows, auditNote, lowRatioExplanation,
  conclusion, conclusionOption,
  checkRatios, lowRatioWarnings, sampleSizeDeviation, incompleteCheckRows, abnormalRows,
  occurrenceDebitChecked, occurrenceCreditChecked, postCollectionChecked,
  load, addOccurrenceRow, addPostCollectionRow, removeOccurrenceRow, removePostCollectionRow,
  updateVoucherRow,
  fillFromSamples, applyFromK1Sheets, applyFromK1LargeAmount, recalcSamplingPopulation,
  buildAbnormalAdjDrafts, serialize,
} = useK1VoucherCheck({ allResponses: allResponsesRef as any })

const { ocrLoading, runOcr } = useK1VoucherOcr()

const viewMode = ref<'table' | 'card'>('table')
const voucherDialogVisible = ref(false)
const voucherDialogRow = ref<K1VoucherRow | null>(null)
const voucherDialogMode = ref<'occurrence' | 'post'>('occurrence')

function cardStatus(row: K1VoucherRow) {
  return k1VoucherCardStatus(row)
}

function openVoucher(row: K1VoucherRow, mode: 'occurrence' | 'post') {
  voucherDialogRow.value = row
  voucherDialogMode.value = mode
  voucherDialogVisible.value = true
}

function handleSaveVoucher(patch: Partial<K1VoucherRow> & { id: string }) {
  updateVoucherRow(voucherDialogMode.value, patch.id, patch)
  persist()
}

function onRowOcr(row: K1VoucherRow, target: 'occurrence' | 'post', file?: File) {
  if (!file || props.isReadonly) return
  void runOcr(file, (text, fileName) => {
    updateVoucherRow(target, row.id, {
      supportingDoc: row.supportingDoc
        ? `${row.supportingDoc}\n[OCR] ${text}`
        : `[OCR] ${text}`,
      ocrAttachment: fileName,
      remark: row.remark?.includes('[OCR]')
        ? row.remark
        : (row.remark ? `${row.remark}\n[OCR附件] ${fileName}` : `[OCR附件] ${fileName}`),
    })
    persist()
  })
}

onMounted(() => {
  load()
  applyIncomingFocus()
})

const filteredOccurrenceRows = computed(() => {
  const keyword = voucherFilter.value.trim().toLowerCase()
  if (!keyword) return occurrenceRows.value
  return occurrenceRows.value.filter((r) =>
    String(r.debtorName ?? '').toLowerCase().includes(keyword),
  )
})

const filteredPostCollectionRows = computed(() => {
  const keyword = voucherFilter.value.trim().toLowerCase()
  if (!keyword) return postCollectionRows.value
  return postCollectionRows.value.filter((r) =>
    String(r.debtorName ?? '').toLowerCase().includes(keyword),
  )
})

function applyIncomingFocus(): void {
  applyK1IncomingFocus({
    sheet: 'K1-12',
    k1Nav,
    rows: [...occurrenceRows.value, ...postCollectionRows.value],
    nameOf: (r) => (r as K1VoucherRow).debtorName,
    onResolved: (resolved, focus) => {
      voucherFilter.value = resolved.counterparty
      deeplinkHint.value = buildK1DeeplinkHint(focus, resolved.counterparty)
      const pool = focus.section === 'post' ? postCollectionRows.value : occurrenceRows.value
      const match = resolved.rowId
        ? pool.find((r) => r.id === resolved.rowId)
        : pool.find((r) =>
            String(r.debtorName ?? '').toLowerCase().includes(resolved.counterparty.toLowerCase()),
          )
      const rowId = match?.id ?? resolved.rowId
      if (rowId) {
        k1Nav?.focusRow(rowId)
        scrollToVoucherRow(rowId, focus.section === 'post' ? 'post' : 'occurrence')
      }
    },
  })
}

function scrollToVoucherRow(rowId: string, section: 'occurrence' | 'post'): void {
  if (!rowId) return
  nextTick(() => {
    const table = section === 'post' ? postTableRef.value : occurrenceTableRef.value
    const root = table?.$el as HTMLElement | undefined
    const rowEl = root?.querySelector(`tr[data-row-key="${rowId}"]`) as HTMLElement | null
    rowEl?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  })
}

function clearDeeplink(): void {
  voucherFilter.value = ''
  deeplinkHint.value = ''
}

// ─── 核对内容：boolean[] ↔ el-checkbox-group（number[]）适配 ────────────────────
function checkedValues(row: K1VoucherRow): number[] {
  return row.checks.map((c, i) => (c ? i : -1)).filter(i => i >= 0)
}
function setChecks(row: K1VoucherRow, vals: number[]): void {
  row.checks = checkLabels.map((_, i) => vals.includes(i))
  persist()
}

// ─── 抽凭引擎 ────────────────────────────────────────────────────────────────
const samplingVisible = ref(false)
const samplingTarget = ref<'occurrence' | 'post'>('occurrence')

function openSampling(target: 'occurrence' | 'post') {
  samplingTarget.value = target
  samplingVisible.value = true
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'K1',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => emit('save', itemId, { remark }),
  isReadonly: computed(() => props.isReadonly === true),
})

function onSamplesFilled(payload: { samples: any[] }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  fillFromSamples(samplingTarget.value, payload?.samples ?? [])
  samplingVisible.value = false
  persist()
}

function importFromK1() {
  const { debit, credit, endBalance, filled } = applyFromK1Sheets()
  persist()
  if (filled) {
    ElMessage.success(`已带入：借方 ${debit.toLocaleString()} / 贷方 ${credit.toLocaleString()} / 期末 ${endBalance.toLocaleString()}`)
  } else {
    ElMessage.warning('K1-1/K1-2 暂无可用账面数据，请先完成审定表或明细表')
  }
}

function importFromK5() {
  const result = applyFromK1LargeAmount()
  persist()
  if (result.filled) {
    ElMessage.success(`已从 K1-5 带入 ${result.count} 户大额特定样本，合计 ${result.totalAmount.toLocaleString()} 元`)
  } else {
    ElMessage.warning('K1-5 大额分析暂无数据，请先完成 K1-5')
  }
}

function onSpecificSampleChange() {
  recalcSamplingPopulation()
  persist()
}

function onRecalcSampling() {
  const derived = recalcSamplingPopulation()
  persist()
  ElMessage.success(`抽样总体已重算：${derived.count} 笔 / ${derived.amount.toLocaleString()} 元`)
}

function pushAbnormalToK14(): void {
  if (props.isReadonly) return
  const drafts = buildAbnormalAdjDrafts()
  if (!drafts.length) {
    ElMessage.info('无异常凭证可推送')
    return
  }
  const added = injectK1Adjustments(props.allResponses, drafts, K1_12_ADJ_SOURCE)
  const payload = props.allResponses.get('K1-4-adj-entries')?.remark
  emit('save', 'K1-4-adj-entries', payload)
  ElMessage.success(`已向 K1-4 推送 ${added.length} 条异常备忘（金额待追查补录）`)
}

// ─── 持久化 ──────────────────────────────────────────────────────────────────
function persist() {
  const data = serialize()
  props.allResponses.set(itemId, { item_id: itemId, conclusion: null, remark: data })
  emit('save', itemId, { remark: data })
}

function onConclusionOption(val: string) {
  const map: Record<string, string> = {
    A: '未见异常。',
    B: '除上述重大不符事项应当作为调整事项予以调整外，其余未见异常。',
    C: '由于存在重大未调整事项（或审计范围受到限制无法获取充分、适当证据），不可确认。',
  }
  if (map[val] && !conclusion.value) conclusion.value = map[val]
  persist()
}

// ─── 格式化 ──────────────────────────────────────────────────────────────────
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function abnormalRowClass({ row }: { row: K1VoucherRow }): string {
  return voucherRowClass({ row })
}

function voucherRowClass({ row }: { row: K1VoucherRow }): string {
  const parts: string[] = []
  const hl = k1Nav?.rowHighlightClass(row.id)
  if (hl) parts.push(hl)
  if (row.abnormal) parts.push('abnormal-row')
  return parts.join(' ')
}

// ─── AI / 复核 ───────────────────────────────────────────────────────────────
async function handleAiGenerate() {
  const content = await generateAndConfirm('overall-opinion', auditNote.value, {
    occurrenceCount: occurrenceRows.value.length,
    postCount: postCollectionRows.value.length,
    abnormalCount: abnormalRows.value.length,
    checkRatios: checkRatios.value,
  }, 'AI 生成 K1-12 审计说明')
  if (content) {
    auditNote.value = content
    persist()
  }
}
function handleReview() { openReviewDialog('K1-12-check') }
</script>

<style scoped>
.k1-tab-receivable-check { padding: 12px 14px; font-size: var(--wp-font-size, 13px); }

/* 顶部引导区（蓝色渐变，4列，紧凑） */
.guide-banner {
  display: grid; grid-template-columns: repeat(4, 1fr); gap: 6px;
  background: linear-gradient(135deg, #eef4ff 0%, #e0ecff 100%);
  border: 1px solid #c6dbff; border-radius: 6px; padding: 7px 12px; margin-bottom: 10px;
}
.guide-step { display: flex; align-items: center; gap: 6px; font-size: 12px; color: #1e40af; }
.gs-no {
  display: inline-flex; align-items: center; justify-content: center;
  width: 18px; height: 18px; border-radius: 50%; background: #2563eb; color: #fff;
  font-size: 11px; font-weight: 600; flex-shrink: 0;
}

.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }

/* 认定目标：紧凑 */
.audit-objective { margin-bottom: 10px; }
.audit-objective :deep(.el-alert__content) { padding: 2px 0; }
.ao-title { font-weight: 600; }
.ao-list { margin: 4px 0 0; padding-left: 18px; line-height: 1.55; font-size: 12px; }

/* 卡片：收紧间距与内边距 */
.section-card { margin-bottom: 10px; }
.section-card :deep(.el-card__header) { padding: 8px 14px; }
.section-card :deep(.el-card__body) { padding: 12px 14px; }
.card-title { font-weight: 600; }
.card-header-row { display: flex; align-items: center; justify-content: space-between; }
.hdr-btns { display: flex; gap: 6px; flex-wrap: wrap; }

/* 样本选取标准网格：3列紧凑 */
.criteria-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 10px 18px; }
.cg-item { display: flex; flex-direction: column; gap: 4px; }
.cg-item.cg-full { grid-column: 1 / -1; }
.cg-item label { font-size: 12px; color: var(--el-text-color-secondary); }
.cg-inline { display: flex; align-items: center; gap: 5px; }
.cg-unit { font-size: 12px; color: var(--el-text-color-secondary); }
.num-sm { width: 78px; }
.num-md { width: 130px; }
.criteria-tip { margin-top: 10px; }
.check-desc { margin: 0 0 8px; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.6; }
.check-legend { margin-right: 6px; }

/* 凭证表 */
.voucher-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.col-help { cursor: help; border-bottom: 1px dashed var(--el-border-color); }
.check-group { display: flex; flex-wrap: wrap; gap: 0 4px; }
.check-group :deep(.el-checkbox) { margin-right: 4px; }
.table-total { padding: 6px 12px; text-align: right; font-size: 12px; color: var(--el-text-color-regular); font-weight: 600; }

.voucher-table :deep(.abnormal-row td) { background-color: #fef2f2 !important; }

/* 检查比例表 */
.ratio-table { max-width: 640px; }
.ratio-warn { margin-top: 12px; }
.muted { color: var(--el-text-color-placeholder); }

.note-block { margin-top: 10px; display: flex; flex-direction: column; gap: 4px; }
.note-block label { font-size: 12px; color: var(--el-text-color-secondary); }

/* 异常摘要 */
.abnormal-summary {
  margin-bottom: 10px; padding: 10px 12px; border-radius: 6px;
  background: #fef2f2; border: 1px solid #fecaca;
}
.as-header { font-weight: 600; color: var(--el-color-danger); margin-bottom: 6px; display: flex; align-items: center; gap: 8px; }
.push-btn { margin-left: auto; }
.as-list { padding-left: 18px; margin: 0; line-height: 1.7; color: var(--el-color-danger-dark-2); }

.conclusion-card { margin-bottom: 10px; }
.concl-select { width: 100%; margin-bottom: 8px; }

.compile-hint { margin-top: 6px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
.deeplink-bar { margin-bottom: 10px; }
.filter-bar { display: flex; align-items: center; gap: 10px; margin-bottom: 10px; flex-wrap: wrap; }
.search-input { width: 220px; }
.voucher-table :deep(.k1-row-deeplink-hl > td) { background-color: #ecf5ff !important; animation: k1-row-flash 1.2s ease-in-out 0s 2; }
@keyframes k1-row-flash { 0%, 100% { background-color: #ecf5ff; } 50% { background-color: #d9ecff; } }
.k1vc-card-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: 10px;
  margin-bottom: 8px;
}
.k1vc-vcard {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 6px;
  padding: 10px 12px;
  cursor: pointer;
  background: var(--el-bg-color);
  transition: border-color 0.15s;
}
.k1vc-vcard:hover { border-color: var(--el-color-primary); }
.k1vc-vcard.is-abnormal {
  border-color: var(--el-color-danger-light-5);
  background: var(--el-color-danger-light-9);
}
.k1vc-vcard-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 4px; }
.k1vc-vcard-title {
  font-weight: 600;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.k1vc-vcard-meta, .k1vc-vcard-amt { font-size: 12px; color: var(--el-text-color-secondary); }
.ocr-ok { color: var(--el-color-success); font-size: 12px; }
</style>
