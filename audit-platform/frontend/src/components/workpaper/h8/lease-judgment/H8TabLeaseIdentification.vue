<template>
  <div class="h8-tab-lease-identification">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：①核实使用权资产存在且记入恰当账户；②确认应记录的使用权资产及相关披露完整；③确认使用权资产以恰当金额列报，计价/分摊调整及披露恰当（CAS21 第4-13条、第32条）。"
    />

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 H8-4）：①按合同判断三要素（已识别资产∩主导使用∩几乎全部经济利益）→
        ②含租赁则评估分拆/合并 → ③判断短期/低价值简化 → ④结论联动 H8-5/H8-6/H8-13。
      </p>
      <p class="def-note">
        控制已识别资产使用的权利 = 存在已识别资产 ＋ 有权主导使用 ＋ 有权获得几乎全部经济利益。
        详细蓝字提示请点各节「提示」或顶部「准则总览 / 决策树」，避免主表拥挤。
      </p>
    </div>

    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-4" />
      <el-tag size="small" type="info">共 {{ records.length }} 份合同</el-tag>
      <el-tag v-if="shortTermCount > 0" size="small" type="warning">短期 {{ shortTermCount }}</el-tag>
      <el-tag v-if="lowValueCount > 0" size="small" type="warning">低价值 {{ lowValueCount }}</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-5')">H8-5 租赁期 →</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-6')">H8-6 计量</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-13')">H8-13 简化</el-tag>
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
      <el-button size="small" type="primary" plain @click="openTip('overview')">准则总览</el-button>
      <el-button size="small" @click="openTip('flowchart')">决策树</el-button>
    </div>

    <div class="stats-bar">
      <el-tag type="info" size="small">合同 {{ records.length }}</el-tag>
      <el-tag type="success" size="small">已完成 {{ completedCount }}</el-tag>
      <el-tag type="primary" size="small">含租赁 {{ leaseCount }}</el-tag>
      <el-tag v-if="missingH82Contracts.length" type="danger" size="small">
        H8-2待带入 {{ missingH82Contracts.length }}
      </el-tag>
      <el-tag v-if="pendingPushH85.length" type="warning" size="small">
        待推H8-5 {{ pendingPushH85.length }}
      </el-tag>
      <el-tag v-if="pendingPushH813.length" type="warning" size="small">
        待推H8-13 {{ pendingPushH813.length }}
      </el-tag>
      <div class="stats-actions">
        <el-button
          v-if="!isReadonly"
          size="small"
          :disabled="!missingH82Contracts.length"
          @click="handlePullH82"
        >
          从 H8-2 带入
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="success"
          plain
          :disabled="!pendingPushH85.length"
          @click="handlePushH85"
        >
          推送 H8-5
        </el-button>
        <el-button
          v-if="!isReadonly"
          size="small"
          type="warning"
          plain
          :disabled="!pendingPushH813.length"
          @click="handlePushH813"
        >
          推送 H8-13
        </el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRecord">+ 新增合同</el-button>
        <el-button size="small" type="primary" plain @click="emit('open-ai', 'lease-identification')">AI 辅助</el-button>
        <el-button size="small" @click="emit('open-review', 'lease-identification')">复核</el-button>
      </div>
    </div>

    <el-alert
      v-if="missingH82Contracts.length"
      type="warning"
      :closable="false"
      show-icon
      class="linkage-alert"
      :title="`H8-2 有 ${missingH82Contracts.length} 份合同尚未做租赁识别：${missingH82Contracts.map(c => c.contractNo).slice(0, 8).join('、')}${missingH82Contracts.length > 8 ? '…' : ''}`"
    />
    <el-alert
      v-if="pendingPushH85.length"
      type="info"
      :closable="false"
      show-icon
      class="linkage-alert"
      :title="`已识别为租赁但 H8-5 尚无记录 ${pendingPushH85.length} 份，可一键推送后确定租赁期`"
    />
    <el-alert
      v-if="pendingPushH813.length"
      type="info"
      :closable="false"
      show-icon
      class="linkage-alert"
      :title="`已判定短期/低价值但 H8-13 尚无行 ${pendingPushH813.length} 份，可推送后做简化费用检查`"
    />

    <div v-if="records.length === 0" class="empty-state">
      <el-empty description="暂无租赁识别记录，请点击「+ 新增合同」按 H8-4 决策树编制" />
    </div>

    <div v-for="record in records" :key="record.recordId" class="id-card">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <div class="header-left">
              <span class="contract-label">合同号：{{ record.contractNo }}</span>
              <el-tag
                :type="leaseTagType(record)"
                size="small"
              >
                {{ leaseText(record) }}
              </el-tag>
              <el-tag
                v-if="shortText(record) === '属于短期租赁'"
                type="warning"
                size="small"
              >
                短期租赁
              </el-tag>
              <el-tag
                v-if="lowText(record) === '属于低价值资产租赁'"
                type="warning"
                size="small"
              >
                低价值
              </el-tag>
              <el-tag
                v-if="gapsOf(record).length"
                type="info"
                size="small"
                effect="plain"
              >
                缺口 {{ gapsOf(record).length }}
              </el-tag>
            </div>
            <div class="card-actions">
              <el-button
                v-if="!isReadonly"
                type="danger"
                link
                size="small"
                @click="handleDeleteRecord(record.recordId)"
              >
                删除
              </el-button>
            </div>
          </div>
        </template>

        <div class="inline-fields meta-row">
          <el-input
            :model-value="record.assetDesc"
            :disabled="isReadonly"
            size="small"
            placeholder="承租资产/合同标的简述"
            style="flex: 1"
            @change="(v: string) => onField(record.recordId, 'assetDesc', v)"
          />
        </div>

        <!-- ════ §1 租赁的识别 ════ -->
        <div class="section-block">
          <div class="section-title">
            <span>1. 租赁的识别【要素须同时满足】</span>
            <el-button link type="primary" size="small" @click="openTip('s1-conclusion')">提示</el-button>
          </div>

          <!-- (1) 已识别资产 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（1）</span>
              <span class="item-label">是否存在已识别资产</span>
              <el-tag
                :type="identifiedAsset(record) === '是' ? 'success' : identifiedAsset(record) === '否' ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                自动 {{ identifiedAsset(record) || '待填' }}
              </el-tag>
              <el-button link type="primary" size="small" @click="openTip('s1-asset')">?</el-button>
            </div>
            <p class="formula-hint">公式：物理可区分=是 且 供应方实质替换权=否 → 已识别资产=是（对齐 Excel F11）</p>

            <div class="judgment-row">
              <span class="judgment-label">①物理可区分</span>
              <el-radio-group
                :model-value="record.physicallyDistinct"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'physicallyDistinct', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <el-input
              :model-value="record.physicallyDistinctInfo"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="公司具体情况：资产如何指定/物理可区分说明…"
              class="mb-6"
              @change="(v: string) => onField(record.recordId, 'physicallyDistinctInfo', v)"
            />

            <div class="judgment-row">
              <span class="judgment-label">②供应方实质性替换权</span>
              <el-radio-group
                :model-value="record.supplierSubstantiveSubstitution"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'supplierSubstantiveSubstitution', v)"
              >
                <el-radio-button value="是">有（否定已识别）</el-radio-button>
                <el-radio-button value="否">无（支持已识别）</el-radio-button>
              </el-radio-group>
            </div>
            <div class="judgment-row nested">
              <span class="judgment-label">替换权两条件是否同时符合（实际能力＋经济利益）</span>
              <el-radio-group
                :model-value="record.substitutionBothConditions"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'substitutionBothConditions', v)"
              >
                <el-radio-button value="是">是 → 联动「有」</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="inline-fields">
              <el-input
                :model-value="record.substitutionInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="公司具体情况：替换权评估…"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'substitutionInfo', v)"
              />
              <el-input
                :model-value="record.substitutionIndex"
                :disabled="isReadonly"
                size="small"
                placeholder="索引"
                style="width: 120px"
                @change="(v: string) => onField(record.recordId, 'substitutionIndex', v)"
              />
            </div>
          </div>

          <!-- (2) 主导使用 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（2）</span>
              <span class="item-label">是否有权在约定使用期间主导已识别资产的使用</span>
              <el-tag
                :type="directUse(record) === '是' ? 'success' : directUse(record) === '否' ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                自动 {{ directUse(record) || '待填' }}
              </el-tag>
              <el-button link type="primary" size="small" @click="openTip('s1-direct')">?</el-button>
            </div>
            <p class="formula-hint">
              路径①主导目的/方式=是；或 路径②预先确定=是 且（有权运营 或 客户设计）=是
            </p>

            <div class="judgment-row">
              <span class="judgment-label">①有权在整个使用期间主导使用目的和使用方式</span>
              <el-radio-group
                :model-value="record.canDirectPurposeManner"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'canDirectPurposeManner', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <el-input
              :model-value="record.directPurposeInfo"
              :disabled="isReadonly"
              size="small"
              placeholder="公司具体情况…"
              class="mb-6"
              @change="(v: string) => onField(record.recordId, 'directPurposeInfo', v)"
            />

            <div class="judgment-row">
              <span class="judgment-label">②使用目的和使用方式在使用期间前已预先确定</span>
              <el-radio-group
                :model-value="record.usePredetermined"
                :disabled="isReadonly || record.canDirectPurposeManner === '是'"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'usePredetermined', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div
              v-if="record.usePredetermined === '是' || (record.canDirectPurposeManner !== '是' && record.usePredetermined !== '否')"
              class="sub-judgments"
            >
              <div class="judgment-row nested">
                <span class="judgment-label">有权自行/主导他人按确定方式运营该资产</span>
                <el-radio-group
                  :model-value="record.canOperateAsset"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'canOperateAsset', v)"
                >
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
              <div class="judgment-row nested">
                <span class="judgment-label">设计了已识别资产并预先确定使用目的/方式</span>
                <el-radio-group
                  :model-value="record.designedAsset"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'designedAsset', v)"
                >
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
            </div>

            <div class="judgment-row">
              <span class="judgment-label">主导使用权总判断（可手填覆盖自动）</span>
              <el-radio-group
                :model-value="record.directUseOverride || directUse(record)"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'directUseOverride', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
              <el-button
                v-if="record.directUseOverride && !isReadonly"
                link
                size="small"
                @click="onField(record.recordId, 'directUseOverride', '')"
              >
                清除覆盖
              </el-button>
            </div>
            <div class="inline-fields">
              <el-input
                :model-value="record.directUseIndex"
                :disabled="isReadonly"
                size="small"
                placeholder="索引"
                style="width: 160px"
                @change="(v: string) => onField(record.recordId, 'directUseIndex', v)"
              />
            </div>
          </div>

          <!-- (3) 经济利益 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（3）</span>
              <span class="item-label">是否有权获得使用期间内几乎全部经济利益</span>
              <el-button link type="primary" size="small" @click="openTip('s1-benefits')">?</el-button>
            </div>
            <div class="judgment-row">
              <span class="judgment-label">几乎全部经济利益</span>
              <el-radio-group
                :model-value="record.economicBenefits"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'economicBenefits', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="inline-fields">
              <el-input
                :model-value="record.economicBenefitsInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="公司具体情况：独家使用/产出与副产品等…"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'economicBenefitsInfo', v)"
              />
              <el-input
                :model-value="record.economicBenefitsIndex"
                :disabled="isReadonly"
                size="small"
                placeholder="索引"
                style="width: 120px"
                @change="(v: string) => onField(record.recordId, 'economicBenefitsIndex', v)"
              />
            </div>
          </div>

          <div class="calc-result">
            <div class="formula-display">
              <strong>结 论：</strong>{{ leaseText(record) }}
            </div>
            <p
              class="auto-conclusion"
              :class="isContainsLease(leaseText(record)) ? 'success' : leaseText(record) === '不包含租赁' ? 'danger' : 'warning'"
            >
              {{
                isContainsLease(leaseText(record))
                  ? '三要素齐备 → 继续 §2/§3，并前往 H8-5 确定租赁期'
                  : leaseText(record) === '不包含租赁'
                    ? '不构成租赁 → §2~§5 通常无须分析；请保留否定证据索引'
                    : '请完成（1）（2）（3）判断'
              }}
            </p>
            <div v-if="isContainsLease(leaseText(record))" class="jump-row">
              <span>下一步：</span>
              <el-button size="small" type="primary" @click="emit('navigate-sheet', 'H8-5')">跳转 H8-5</el-button>
              <el-button size="small" @click="emit('navigate-sheet', 'H8-6')">跳转 H8-6</el-button>
            </div>
          </div>
        </div>

        <!-- ════ §2 分拆 ════ -->
        <div
          class="section-block"
          :class="{ muted: !isContainsLease(leaseText(record)) && record.splitApplicable !== '是' }"
        >
          <div class="section-title">
            <span>2. 租赁的分拆【条件须同时满足】</span>
            <div class="title-right">
              <span class="appl-label">是否适用</span>
              <el-radio-group
                :model-value="record.splitApplicable"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'splitApplicable', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
              <el-button link type="primary" size="small" @click="openTip('s2-split')">提示</el-button>
            </div>
          </div>

          <template v-if="record.splitApplicable === '是'">
            <div class="judgment-row">
              <span class="judgment-label">（1）可单独或与易于获得资源一起使用中获利</span>
              <el-radio-group
                :model-value="record.canBenefitSeparately"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'canBenefitSeparately', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="inline-fields mb-6">
              <el-input
                :model-value="record.canBenefitSeparatelyInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="公司具体情况…"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'canBenefitSeparatelyInfo', v)"
              />
              <el-input
                :model-value="record.canBenefitSeparatelyIndex"
                :disabled="isReadonly"
                size="small"
                placeholder="索引"
                style="width: 120px"
                @change="(v: string) => onField(record.recordId, 'canBenefitSeparatelyIndex', v)"
              />
            </div>
            <div class="judgment-row">
              <span class="judgment-label">（2）与合同中其他资产不存在高度依赖/关联</span>
              <el-radio-group
                :model-value="record.notHighlyDependent"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'notHighlyDependent', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="inline-fields mb-6">
              <el-input
                :model-value="record.notHighlyDependentInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="公司具体情况…"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'notHighlyDependentInfo', v)"
              />
            </div>
            <div class="judgment-row">
              <span class="judgment-label">实务简化：按资产类别选择不分拆非租赁部分</span>
              <el-radio-group
                :model-value="record.electNotSplitNonLease"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'electNotSplitNonLease', v)"
              >
                <el-radio-button value="是">选择不分拆</el-radio-button>
                <el-radio-button value="否">仍分拆</el-radio-button>
              </el-radio-group>
            </div>
            <div class="calc-result">
              <div class="formula-display"><strong>结 论：</strong>{{ splitText(record) }}</div>
            </div>
          </template>
          <p v-else class="skip-hint">标记「是否适用=是」后展开分拆判断；合同无多项标的时可选否。</p>
        </div>

        <!-- ════ §3 合并 ════ -->
        <div class="section-block">
          <div class="section-title">
            <span>3. 租赁的合并【条件满足任一】</span>
            <div class="title-right">
              <span class="appl-label">是否适用</span>
              <el-radio-group
                :model-value="record.combineApplicable"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'combineApplicable', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
              <el-button link type="primary" size="small" @click="openTip('s3-combine')">提示</el-button>
            </div>
          </div>
          <template v-if="record.combineApplicable === '是'">
            <div class="judgment-row">
              <span class="judgment-label">（1）一揽子交易 / 总体商业目的</span>
              <el-radio-group
                :model-value="record.packageCommercialPurpose"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'packageCommercialPurpose', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <el-input
              :model-value="record.packageInfo"
              :disabled="isReadonly"
              size="small"
              placeholder="公司具体情况…"
              class="mb-6"
              @change="(v: string) => onField(record.recordId, 'packageInfo', v)"
            />
            <div class="judgment-row">
              <span class="judgment-label">（2）对价取决于其他合同定价或履行</span>
              <el-radio-group
                :model-value="record.considerationDepends"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'considerationDepends', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="judgment-row">
              <span class="judgment-label">（3）使用权合起来构成一项单独租赁</span>
              <el-radio-group
                :model-value="record.combinedSingleLease"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'combinedSingleLease', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="calc-result">
              <div class="formula-display"><strong>结 论：</strong>{{ combineText(record) }}</div>
            </div>
          </template>
          <p v-else class="skip-hint">仅当同期/近乎同时订立多份相关合同时标记适用。</p>
        </div>

        <!-- ════ §4 短期 ════ -->
        <div
          class="section-block"
          :class="{ highlight: shortText(record) === '属于短期租赁' }"
        >
          <div class="section-title">
            <span>4. 短期租赁【条件须同时满足】</span>
            <div class="title-right">
              <span class="appl-label">是否适用</span>
              <el-radio-group
                :model-value="record.shortTermApplicable"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'shortTermApplicable', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
              <el-button link type="primary" size="small" @click="openTip('s4-short')">提示</el-button>
            </div>
          </div>
          <template v-if="record.shortTermApplicable === '是'">
            <div class="judgment-head">
              <span class="item-label">（1）租赁期不超过12个月</span>
              <el-tag
                :type="termWithin12(record) === '是' ? 'success' : termWithin12(record) === '否' ? 'danger' : 'info'"
                size="small"
                effect="plain"
              >
                自动 {{ termWithin12(record) || '待填' }}
              </el-tag>
            </div>
            <p class="formula-hint">公式：续租后≤12月 且 续签后≤12月 → 是（对齐 Excel F41）</p>
            <div class="judgment-row">
              <span class="judgment-label">考虑续租选择权后租赁期不超过12个月</span>
              <el-radio-group
                :model-value="record.termWithRenewalWithin12"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'termWithRenewalWithin12', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="judgment-row">
              <span class="judgment-label">续签合同租赁期不超过12个月</span>
              <el-radio-group
                :model-value="record.renewContractWithin12"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'renewContractWithin12', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="judgment-row">
              <span class="judgment-label">（2）不包含购买选择权</span>
              <el-radio-group
                :model-value="record.noPurchaseOption"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'noPurchaseOption', v)"
              >
                <el-radio-button value="是">无购买权</el-radio-button>
                <el-radio-button value="否">有购买权</el-radio-button>
              </el-radio-group>
            </div>
            <el-input
              :model-value="record.noPurchaseOptionInfo"
              :disabled="isReadonly"
              size="small"
              placeholder="公司具体情况 / 与 H8-5 租赁期勾稽说明…"
              class="mb-6"
              @change="(v: string) => onField(record.recordId, 'noPurchaseOptionInfo', v)"
            />
            <div class="calc-result">
              <div class="formula-display"><strong>结 论：</strong>{{ shortText(record) }}</div>
              <div v-if="shortText(record) === '属于短期租赁'" class="jump-row">
                <span>可选择简化处理：</span>
                <el-button size="small" type="primary" @click="emit('navigate-sheet', 'H8-13')">跳转 H8-13</el-button>
                <el-button size="small" @click="emit('navigate-sheet', 'H8-5')">核验 H8-5 租赁期</el-button>
              </div>
            </div>
          </template>
          <p v-else class="skip-hint">拟按第32条简化处理短期租赁时标记适用；含购买选择权一律不属于短期租赁。</p>
        </div>

        <!-- ════ §5 低价值 ════ -->
        <div
          class="section-block"
          :class="{ highlight: lowText(record) === '属于低价值资产租赁' }"
        >
          <div class="section-title">
            <span>5. 低价值资产租赁【条件须同时满足】</span>
            <div class="title-right">
              <span class="appl-label">是否适用</span>
              <el-radio-group
                :model-value="record.lowValueApplicable"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'lowValueApplicable', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
              <el-button link type="primary" size="small" @click="openTip('s5-low')">提示</el-button>
            </div>
          </div>
          <template v-if="record.lowValueApplicable === '是'">
            <div class="judgment-row">
              <span class="judgment-label">（1）全新资产时价值较低（如低于 {{ LOW_VALUE_THRESHOLD.toLocaleString() }} 元）</span>
              <el-radio-group
                :model-value="record.lowValueWhenNew"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'lowValueWhenNew', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否</el-radio-button>
              </el-radio-group>
            </div>
            <div class="inline-fields mb-6">
              <el-form-item label="全新价值(元)" class="compact-item">
                <el-input-number
                  :model-value="record.newAssetValue"
                  :controls="false"
                  :min="0"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: number | undefined) => onField(record.recordId, 'newAssetValue', v)"
                />
              </el-form-item>
              <el-input
                :model-value="record.lowValueInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="评估依据（按全新状态，绝对金额）…"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'lowValueInfo', v)"
              />
            </div>
            <div class="judgment-row">
              <span class="judgment-label">（2）并未转租赁或不预期转租赁</span>
              <el-radio-group
                :model-value="record.noSubleaseExpected"
                :disabled="isReadonly"
                size="small"
                @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'noSubleaseExpected', v)"
              >
                <el-radio-button value="是">是</el-radio-button>
                <el-radio-button value="否">否（已/预期转租）</el-radio-button>
              </el-radio-group>
            </div>
            <div class="calc-result">
              <div class="formula-display"><strong>结 论：</strong>{{ lowText(record) }}</div>
              <div v-if="lowText(record) === '属于低价值资产租赁'" class="jump-row">
                <span>可选择简化处理：</span>
                <el-button size="small" type="primary" @click="emit('navigate-sheet', 'H8-13')">跳转 H8-13</el-button>
              </div>
            </div>
          </template>
          <p v-else class="skip-hint">拟按第32条简化处理低价值租赁时标记适用；已转租/预期转租不得简化。</p>
        </div>

        <el-form size="small" label-position="top" class="term-form">
          <el-form-item v-if="gapsOf(record).length" label="编制缺口">
            <div class="gap-list">
              <el-tag
                v-for="g in gapsOf(record)"
                :key="g"
                size="small"
                type="warning"
                effect="plain"
                class="gap-tag"
              >
                {{ g }}
              </el-tag>
            </div>
          </el-form-item>
          <el-form-item label="判断说明">
            <el-input
              type="textarea"
              :autosize="{ minRows: 2 }"
              :model-value="record.explanation"
              :readonly="isReadonly"
              placeholder="综合说明识别、分拆/合并及简化处理判断依据…"
              @change="(v: string | number) => onField(record.recordId, 'explanation', v)"
            />
          </el-form-item>
          <el-form-item label="本项结论">
            <el-radio-group
              :model-value="record.conclusion"
              :disabled="isReadonly"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'conclusion', v)"
            >
              <el-radio-button value="是">属于/包含租赁</el-radio-button>
              <el-radio-button value="否">不包含租赁</el-radio-button>
              <el-radio-button value="不适用">不适用</el-radio-button>
            </el-radio-group>
          </el-form-item>
        </el-form>
      </el-card>
    </div>

    <el-card shadow="never" class="audit-note-card">
      <template #header><span class="card-title">三、审计说明</span></template>
      <el-input
        type="textarea"
        :model-value="auditNote"
        :disabled="isReadonly"
        :autosize="{ minRows: 5 }"
        placeholder="请输入审计说明（合同抽查范围、识别关键判断、与 H8-2/H8-5 勾稽等）…"
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
        placeholder="请输入审计结论…"
        @change="saveAuditConclusion"
      />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（摘要）</summary>
      <ul>
        <li>详细准则/蓝字说明请点各节「提示」或顶部「准则总览 / 决策树」打开右侧抽屉</li>
        <li>§1 已识别资产：物理可区分=是 <strong>且</strong> 实质替换权=否（有替换权会否定已识别资产）</li>
        <li>§1 结论：三要素 AND →「合同为租赁或者包含租赁」；否则「不包含租赁」</li>
        <li>§2 分拆同时满足；§3 合并满足任一；§4/§5 对齐第32条简化，结论为「属于…」时跳转 H8-13</li>
        <li>每份合同与 H8-2 明细一行对应；含租赁后须完成 H8-5 租赁期</li>
        <li>工具栏「从 H8-2 带入 / 推送 H8-5 / 推送 H8-13」做跨表联动；否定关键判断会自动弹出对应准则提示</li>
      </ul>
    </details>

    <el-drawer v-model="tipDrawerVisible" :title="activeTip?.title ?? '编制提示'" direction="rtl" size="460px">
      <div v-if="activeTip" class="tip-body">
        <p v-for="(p, i) in activeTip.paragraphs" :key="i" class="tip-para">{{ p }}</p>
        <div v-if="activeTip.jumps?.length" class="tip-jumps">
          <div class="tip-jumps-title">相关跳转</div>
          <el-button
            v-for="j in activeTip.jumps"
            :key="j.sheet"
            size="small"
            type="primary"
            plain
            @click="jumpFromTip(j.sheet)"
          >
            {{ j.label }}
          </el-button>
        </div>
        <div class="tip-nav">
          <el-button
            v-for="t in H8_LEASE_ID_TIPS"
            :key="t.id"
            size="small"
            :type="t.id === activeTip.id ? 'primary' : 'default'"
            text
            @click="openTip(t.id)"
          >
            {{ t.title.length > 14 ? t.title.slice(0, 14) + '…' : t.title }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabLeaseIdentification.vue — H8-4 租赁的识别
 * 对齐 Excel：§1~§5 决策树 + 公式结论 + 提示抽屉 + 跨表跳转
 */
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH8LeaseIdentification,
  H8_LEASE_ID_TIPS,
  type H8IdentificationRecord,
  type H8LeaseIdTip,
} from '../../composables/useH8LeaseIdentification'
import { useH8ImportExport } from '../../composables/useH8ImportExport'
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

const {
  records,
  completedCount,
  leaseCount,
  shortTermCount,
  lowValueCount,
  missingH82Contracts,
  pendingPushH85,
  pendingPushH813,
  addRecord,
  deleteRecord,
  updateField,
  pullFromH82,
  pushToH85,
  pushToH813,
  calcIdentifiedAsset,
  resolveDirectUse,
  calcLeaseIdentificationConclusion,
  calcSplitConclusion,
  calcCombineConclusion,
  calcTermWithin12,
  calcShortTermConclusion,
  calcLowValueConclusion,
  isContainsLease,
  calcCompletenessGaps,
  LOW_VALUE_THRESHOLD,
  load,
} = useH8LeaseIdentification({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: toRef(props, 'allResponses'),
  onSave: (itemId, value) => emit('save', itemId, value),
})

const wpIdRef = toRef(props, 'wpId')
const projectIdRef = toRef(props, 'projectId')
const fileInputRef = ref<HTMLInputElement | null>(null)
const h8ReloadAll = inject<() => Promise<void>>('h8ReloadAll', async () => {})
const { isExporting, isImporting, exportTemplate, exportData, importData } = useH8ImportExport({
  wpId: wpIdRef,
  projectId: projectIdRef,
  sheetCode: 'H8-4',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-4'])
  else if (cmd === 'export-data') await exportData(['H8-4'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

const AUDIT_NOTE_KEY = 'H8-lease-identification-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-lease-identification-audit-conclusion'
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

const tipDrawerVisible = ref(false)
const activeTipId = ref('overview')
const activeTip = computed<H8LeaseIdTip | undefined>(() =>
  H8_LEASE_ID_TIPS.find(t => t.id === activeTipId.value),
)

function openTip(id: string) {
  activeTipId.value = id
  tipDrawerVisible.value = true
}
function jumpFromTip(sheet: string) {
  tipDrawerVisible.value = false
  emit('navigate-sheet', sheet)
}

function identifiedAsset(r: H8IdentificationRecord) {
  return calcIdentifiedAsset(r.physicallyDistinct, r.supplierSubstantiveSubstitution)
}
function directUse(r: H8IdentificationRecord) {
  return resolveDirectUse(r)
}
function leaseText(r: H8IdentificationRecord) {
  return calcLeaseIdentificationConclusion(identifiedAsset(r), directUse(r), r.economicBenefits)
}
function leaseTagType(r: H8IdentificationRecord): 'success' | 'danger' | 'info' {
  const t = leaseText(r)
  if (isContainsLease(t)) return 'success'
  if (t === '不包含租赁') return 'danger'
  return 'info'
}
function splitText(r: H8IdentificationRecord) {
  return calcSplitConclusion(r.canBenefitSeparately, r.notHighlyDependent)
}
function combineText(r: H8IdentificationRecord) {
  return calcCombineConclusion(r.packageCommercialPurpose, r.considerationDepends, r.combinedSingleLease)
}
function termWithin12(r: H8IdentificationRecord) {
  return calcTermWithin12(r.termWithRenewalWithin12, r.renewContractWithin12)
}
function shortText(r: H8IdentificationRecord) {
  return calcShortTermConclusion(termWithin12(r), r.noPurchaseOption)
}
function lowText(r: H8IdentificationRecord) {
  return calcLowValueConclusion(r.lowValueWhenNew, r.noSubleaseExpected)
}
function gapsOf(r: H8IdentificationRecord) {
  return calcCompletenessGaps(r)
}

function onField(recordId: string, field: string, value: any) {
  const tipId = updateField(recordId, field, value)
  if (tipId) openTip(tipId)
}

function handlePullH82() {
  const res = pullFromH82()
  if (res.added) ElMessage.success(res.message)
  else ElMessage.info(res.message)
}

function handlePushH85() {
  const res = pushToH85()
  if (res.added) {
    ElMessage.success(res.message)
    emit('navigate-sheet', 'H8-5')
  } else {
    ElMessage.info(res.message)
  }
}

function handlePushH813() {
  const res = pushToH813()
  if (res.added) {
    ElMessage.success(res.message)
    emit('navigate-sheet', 'H8-13')
  } else {
    ElMessage.info(res.message)
  }
}

async function handleAddRecord() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增租赁识别', {
    confirmButtonText: '确认',
    cancelButtonText: '取消',
    inputPlaceholder: '如：ZL-2024-001',
  })
  if (value) addRecord(value)
}

function handleDeleteRecord(recordId: string) {
  deleteRecord(recordId)
}
</script>

<style scoped>
.h8-tab-lease-identification { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
.linkage-alert { margin-bottom: 10px; }
.audit-note-card, .audit-conclusion-card { margin-bottom: 16px; }
.card-title { font-weight: 600; }

.methodology-context {
  background: #fffbeb; border-left: 4px solid #f59e0b; padding: 10px 14px;
  border-radius: 0 6px 6px 0; margin-bottom: 16px; font-size: 12px; color: #92400e;
}
.methodology-context p { margin: 0 0 6px; }
.methodology-context p:last-child { margin-bottom: 0; }
.def-note { color: #78716c; }

.h8-tab-toolbar {
  display: flex; align-items: center; gap: 8px; margin-bottom: 12px; flex-wrap: wrap;
}
.nav-chip { cursor: pointer; }
.nav-chip:hover { opacity: 0.85; }

.stats-bar {
  display: flex; align-items: center; gap: 10px; margin-bottom: 16px; flex-wrap: wrap;
}
.stats-actions { margin-left: auto; display: flex; gap: 6px; flex-wrap: wrap; }

.empty-state { padding: 40px 0; }
.id-card { margin-bottom: 16px; }
.card-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
}
.header-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.contract-label { font-weight: 600; }
.card-actions { display: flex; align-items: center; gap: 8px; }
.meta-row { margin-bottom: 12px; }

.section-block {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 12px; margin-bottom: 12px; background: #fafafa;
}
.section-block.highlight {
  background: #fff7ed; border-color: #fdba74;
}
.section-block.muted { opacity: 0.72; }
.section-title {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600; margin-bottom: 10px; font-size: 13px; gap: 8px; flex-wrap: wrap;
}
.title-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.appl-label { font-weight: 400; font-size: 12px; color: var(--el-text-color-secondary); }

.judgment-block {
  border: 1px solid var(--el-border-color-extra-light); border-radius: 6px;
  padding: 10px 12px; margin-bottom: 10px; background: #fff;
}
.judgment-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.item-no { font-weight: 600; color: var(--el-color-primary); }
.item-label { flex: 1; min-width: 180px; line-height: 1.45; }
.formula-hint {
  margin: 0 0 8px; font-size: 11px; color: var(--el-text-color-secondary); line-height: 1.4;
}

.sub-judgments { margin-top: 8px; padding-left: 8px; border-left: 3px solid #e5e7eb; }
.judgment-row {
  display: flex; align-items: flex-start; justify-content: space-between;
  gap: 12px; margin-bottom: 8px; flex-wrap: wrap;
}
.judgment-row.nested { padding-left: 12px; }
.judgment-label { flex: 1; min-width: 200px; line-height: 1.5; color: var(--el-text-color-regular); }

.inline-fields {
  display: flex; align-items: center; gap: 10px; flex-wrap: wrap; margin-bottom: 6px;
}
.compact-item { margin-bottom: 0 !important; }
.mb-6 { margin-bottom: 6px; }

.calc-result {
  background: #f0f9ff; border-radius: 6px; padding: 10px 14px; margin-top: 4px;
}
.formula-display { font-size: var(--wp-font-size, 13px); color: var(--el-color-primary); line-height: 1.7; }

.auto-conclusion { margin: 8px 0 0; font-size: 12px; line-height: 1.5; }
.auto-conclusion.success { color: #15803d; }
.auto-conclusion.warning { color: #b45309; }
.auto-conclusion.danger { color: #b91c1c; }

.jump-row {
  display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap;
  font-size: 12px; color: var(--el-text-color-secondary);
}
.skip-hint {
  margin: 0; font-size: 12px; color: var(--el-text-color-secondary); line-height: 1.5;
}

.term-form { margin-top: 8px; }
.gap-list { display: flex; flex-wrap: wrap; gap: 6px; }
.gap-tag { max-width: 100%; }

.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }

.tip-body { padding: 0 4px 16px; }
.tip-para {
  font-size: 13px; line-height: 1.65; color: var(--el-text-color-regular);
  margin: 0 0 10px; white-space: pre-wrap;
}
.tip-jumps { margin: 16px 0; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.tip-jumps-title { font-weight: 600; margin-bottom: 8px; font-size: 13px; }
.tip-jumps .el-button { margin: 0 8px 8px 0; }
.tip-nav {
  display: flex; flex-wrap: wrap; gap: 4px; margin-top: 16px;
  padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter);
}
</style>
