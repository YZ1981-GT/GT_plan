<template>
  <div class="h8-tab-lease-term">
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="objective-alert"
      title="审计目标：核实使用权资产存在性、完整性、计价与分摊及准确性；确认租赁期（不可撤销期＋合理确定续租期＋合理确定不行使终止权涵盖期）符合 CAS21 第14-17条。"
    />

    <div class="methodology-context">
      <p>
        编制逻辑（对齐致同 H8-5）：①按合同逐项判断租赁期构成期间是否包含 →
        ②汇总「确定的租赁期」→ ③检查重大事件是否触发重新评估 →
        ④若触发或发生四类修改情形，重新确定租赁期并联动 H8-6/H8-7。
      </p>
      <p class="def-note">
        租赁期 = 不可撤销期间 ＋ 续租选择权期（合理确定行使）＋ 终止选择权期（合理确定不行使）。
        签订日至开始日不计入；双方均可无重大罚金终止则租赁不再可强制执行。
      </p>
    </div>

    <div class="h8-tab-toolbar">
      <GtIndexChip value="wp:H8-5" />
      <el-tag size="small" type="info">共 {{ records.length }} 份合同</el-tag>
      <el-tag v-if="reassessmentNeededCount > 0" size="small" type="warning">
        需重新评估 {{ reassessmentNeededCount }}
      </el-tag>
      <el-tag
        v-if="shortTermCandidateCount > 0"
        size="small"
        type="warning"
        class="nav-chip"
        @click="handlePushAllShortTerm"
      >
        短期候选 {{ shortTermCandidateCount }} → H8-13
      </el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-4')">← H8-4 识别</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-6')">H8-6 计量 →</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-8')">H8-8 折旧</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-13')">H8-13 简化</el-tag>
      <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H8-7')">H8-7 变更</el-tag>
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
      <el-button size="small" type="primary" plain @click="openTip('definition')">准则提示</el-button>
      <el-button size="small" @click="openTip('flowchart')">构成示意</el-button>
    </div>

    <div class="stats-bar">
      <el-tag type="info" size="small">合同 {{ records.length }}</el-tag>
      <el-tag type="success" size="small">已完成 {{ completedCount }}</el-tag>
      <el-tag type="primary" size="small">平均租赁期 {{ avgLeaseTerm }} 月</el-tag>
      <div class="stats-actions">
        <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddRecord">+ 新增合同</el-button>
        <el-button size="small" type="primary" plain @click="emit('open-ai', 'lease-term')">AI 辅助</el-button>
        <el-button size="small" @click="emit('open-review', 'lease-term')">复核</el-button>
      </div>
    </div>

    <div v-if="records.length === 0" class="empty-state">
      <el-empty description="暂无租赁期确定记录，请点击「+ 新增合同」按 H8-5 决策树编制" />
    </div>

    <div v-for="record in records" :key="record.recordId" class="term-card">
      <el-card shadow="never">
        <template #header>
          <div class="card-header">
            <div class="header-left">
              <span class="contract-label">合同号：{{ record.contractNo }}</span>
              <el-tag type="primary" size="small">
                有效租赁期 {{ resolveEffectiveLeaseTermMonths(record) }} 月
              </el-tag>
              <el-tag
                v-if="reassessmentText(record).startsWith('应当')"
                type="warning"
                size="small"
              >
                需重新评估
              </el-tag>
              <el-tag v-if="needsTermModification(record)" type="danger" size="small">需修改租赁期</el-tag>
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

        <!-- ════ §1 租赁期的确定 ════ -->
        <div class="section-block">
          <div class="section-title">
            <span>1. 租赁期的确定【承租人有权使用租赁资产且不可撤销的期间】</span>
            <el-button link type="primary" size="small" @click="openTip('definition')">提示</el-button>
          </div>

          <!-- (1) 签订日至开始日 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（1）</span>
              <span class="item-label">合同签订日至租赁期开始日之间的期间</span>
              <el-tag type="danger" size="small" effect="plain">不包含</el-tag>
              <el-button link type="primary" size="small" @click="openTip('item1')">?</el-button>
            </div>
            <el-input
              :model-value="record.signingToCommencementInfo"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="合同信息：签订日、约定开始日、间隔说明…"
              @change="(v: string) => onField(record.recordId, 'signingToCommencementInfo', v)"
            />
          </div>

          <!-- (2) 开始日 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（2）</span>
              <span class="item-label">租赁期开始日（出租人使资产可供承租人使用之日）</span>
              <el-tag type="success" size="small" effect="plain">包含</el-tag>
              <el-button link type="primary" size="small" @click="openTip('item2')">?</el-button>
            </div>
            <div class="inline-fields">
              <el-input
                :model-value="record.commencementDate"
                :disabled="isReadonly"
                size="small"
                placeholder="开始日 YYYY-MM-DD"
                style="width: 160px"
                @change="(v: string) => onField(record.recordId, 'commencementDate', v)"
              />
              <el-input
                :model-value="record.commencementInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="合同信息/取数依据"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'commencementInfo', v)"
              />
            </div>
          </div>

          <!-- (3) 不可撤销期间 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（3）</span>
              <span class="item-label">不可撤销期间</span>
              <el-button link type="primary" size="small" @click="openTip('item3')">?</el-button>
            </div>
            <div class="inline-fields">
              <el-form-item label="月数" class="compact-item">
                <el-input-number
                  :model-value="record.nonCancellableMonths"
                  :controls="false"
                  :min="0"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: number | undefined) => onField(record.recordId, 'nonCancellableMonths', v)"
                />
              </el-form-item>
              <el-input
                :model-value="record.nonCancellableInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="合同信息：不可撤销条款摘要"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'nonCancellableInfo', v)"
              />
            </div>

            <div class="sub-judgments">
              <div class="judgment-row">
                <span class="judgment-label">仅出租人有权终止租赁（该期间属不可撤销）</span>
                <el-radio-group
                  :model-value="record.lessorOnlyTerminate"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'lessorOnlyTerminate', v)"
                >
                  <el-radio-button value="是">是 → 包含</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
              <div class="judgment-row">
                <span class="judgment-label">仅承租人有权终止租赁</span>
                <el-radio-group
                  :model-value="record.lesseeOnlyTerminate"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'lesseeOnlyTerminate', v)"
                >
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
              <div
                v-if="record.lesseeOnlyTerminate === '是'"
                class="judgment-row nested"
              >
                <span class="judgment-label">是否合理确定将<strong>不</strong>行使终止选择权</span>
                <el-radio-group
                  :model-value="record.lesseeReasonablyCertainNotTerminate"
                  :disabled="isReadonly || record.bothCanTerminateNoPenalty === '是'"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'lesseeReasonablyCertainNotTerminate', v)"
                >
                  <el-radio-button value="是">是 → 计入该期间</el-radio-button>
                  <el-radio-button value="否">否 → 不计入</el-radio-button>
                </el-radio-group>
              </div>
              <div
                v-if="record.lesseeOnlyTerminate === '是' && record.lesseeReasonablyCertainNotTerminate === '是'"
                class="inline-fields nested"
              >
                <el-form-item label="终止权涵盖期(月)" class="compact-item">
                  <el-input-number
                    :model-value="record.terminationOptionMonths"
                    :controls="false"
                    :min="0"
                    :disabled="isReadonly"
                    size="small"
                    @change="(v: number | undefined) => onField(record.recordId, 'terminationOptionMonths', v)"
                  />
                </el-form-item>
              </div>
              <div class="judgment-row">
                <span class="judgment-label">双方均可终止且无需支付重大罚金（租赁不再可强制执行）</span>
                <el-radio-group
                  :model-value="record.bothCanTerminateNoPenalty"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'bothCanTerminateNoPenalty', v)"
                >
                  <el-radio-button value="是">是 → 不包含</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </div>
              <p v-if="record.bothCanTerminateNoPenalty === '是'" class="auto-conclusion danger">
                → 自双方均可无重大罚金终止时点起，租赁不再可强制执行，该期间不纳入租赁期。
              </p>
            </div>
          </div>

          <!-- (4) 续租 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（4）</span>
              <span class="item-label">续租选择权涵盖的期间（合理确定将行使时包含）</span>
              <el-button link type="primary" size="small" @click="openTip('item4')">?</el-button>
            </div>
            <div class="inline-fields">
              <el-form-item label="续租月数" class="compact-item">
                <el-input-number
                  :model-value="record.renewalMonths"
                  :controls="false"
                  :min="0"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: number | undefined) => onField(record.recordId, 'renewalMonths', v)"
                />
              </el-form-item>
              <el-form-item label="合理确定行使" class="compact-item">
                <el-radio-group
                  :model-value="record.renewalReasonablyCertain"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'renewalReasonablyCertain', v)"
                >
                  <el-radio-button value="是">是 → 包含</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </el-form-item>
            </div>
            <el-input
              :model-value="record.renewalInfo"
              :disabled="isReadonly"
              size="small"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="合同信息及合理确定判断依据（改良、迁移成本、经营重要性等）"
              @change="(v: string) => onField(record.recordId, 'renewalInfo', v)"
            />
          </div>

          <!-- (5) 购买选择权 -->
          <div class="judgment-block">
            <div class="judgment-head">
              <span class="item-no">（5）</span>
              <span class="item-label">购买选择权</span>
              <el-button link type="primary" size="small" @click="openTip('item5')">?</el-button>
            </div>
            <div class="inline-fields">
              <el-form-item label="合理确定行使" class="compact-item">
                <el-radio-group
                  :model-value="record.purchaseReasonablyCertain"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'purchaseReasonablyCertain', v)"
                >
                  <el-radio-button value="是">是</el-radio-button>
                  <el-radio-button value="否">否</el-radio-button>
                </el-radio-group>
              </el-form-item>
              <el-input
                :model-value="record.purchaseOptionInfo"
                :disabled="isReadonly"
                size="small"
                placeholder="行权价、市价比较、判断依据"
                style="flex: 1"
                @change="(v: string) => onField(record.recordId, 'purchaseOptionInfo', v)"
              />
            </div>
            <p v-if="record.purchaseReasonablyCertain === '是'" class="auto-conclusion primary">
              → 合理确定行使购买选择权时，折旧年限应结合资产剩余使用寿命（
              <el-button link type="primary" size="small" @click="emit('navigate-sheet', 'H8-8')">跳转 H8-8</el-button>
              ）。
            </p>
          </div>

          <!-- 确定的租赁期 -->
          <div class="calc-result">
            <div class="formula-display">
              建议租赁期 =
              {{ record.nonCancellableMonths }}
              <template v-if="record.renewalReasonablyCertain === '是'">
                ＋ {{ record.renewalMonths }}（续租）
              </template>
              <template v-if="record.lesseeReasonablyCertainNotTerminate === '是'">
                ＋ {{ record.terminationOptionMonths }}（不行使终止权）
              </template>
              ＝ <strong>{{ suggestedTerm(record) }}</strong> 月
            </div>
            <div class="inline-fields term-final">
              <el-form-item label="确定的租赁期(月)" class="compact-item">
                <el-input-number
                  :model-value="record.determinedLeaseTermMonths"
                  :controls="false"
                  :min="0"
                  :disabled="isReadonly"
                  size="small"
                  @change="(v: number | undefined) => onField(record.recordId, 'determinedLeaseTermMonths', v)"
                />
              </el-form-item>
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                plain
                @click="applySuggestedTerm(record.recordId)"
              >
                采用建议值
              </el-button>
              <el-input
                :model-value="record.termEndDate"
                :disabled="isReadonly"
                size="small"
                placeholder="租赁期截止日"
                style="width: 140px"
                @change="(v: string) => onField(record.recordId, 'termEndDate', v)"
              />
              <el-input
                :model-value="record.indexRef"
                :disabled="isReadonly"
                size="small"
                placeholder="索引"
                style="width: 120px"
                @change="(v: string) => onField(record.recordId, 'indexRef', v)"
              />
              <el-button
                v-if="!isReadonly"
                size="small"
                type="primary"
                @click="handlePushToH86(record.recordId)"
              >
                回写 H8-6
              </el-button>
              <el-button
                v-if="!isReadonly"
                size="small"
                @click="handlePushToH88(record.recordId)"
              >
                回写 H8-8
              </el-button>
              <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-6')">
                打开 H8-6 →
              </el-button>
              <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H8-8')">
                打开 H8-8 →
              </el-button>
              <el-button
                v-if="!isReadonly && resolveEffectiveLeaseTermMonths(record) > 0 && resolveEffectiveLeaseTermMonths(record) <= 12"
                size="small"
                type="warning"
                plain
                @click="handlePushShortTerm(record.recordId)"
              >
                {{ record.purchaseReasonablyCertain === '是' ? '含购买权·非短期' : '推送 H8-13' }}
              </el-button>
              <el-button
                v-if="resolveEffectiveLeaseTermMonths(record) > 0 && resolveEffectiveLeaseTermMonths(record) <= 12"
                size="small"
                link
                type="warning"
                @click="emit('navigate-sheet', 'H8-13')"
              >
                打开 H8-13
              </el-button>
            </div>
          </div>
        </div>

        <!-- ════ §2.1 重新评估 ════ -->
        <div class="section-block">
          <div class="section-title">
            <span>2.1 重大事件或变化（承租人可控范围内）— 是否重新评估</span>
            <el-button link type="primary" size="small" @click="openTip('reassess')">提示</el-button>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">重大租赁资产改良</span>
            <el-radio-group
              :model-value="record.majorImprovement"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'majorImprovement', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">对租赁资产进行的重大定制化改造</span>
            <el-radio-group
              :model-value="record.majorCustomization"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'majorCustomization', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">直接相关的经营决策</span>
            <el-radio-group
              :model-value="record.relatedBusinessDecision"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'relatedBusinessDecision', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <p
            class="auto-conclusion"
            :class="reassessmentText(record).startsWith('应当') ? 'warning' : reassessmentText(record).startsWith('无需') ? 'success' : 'primary'"
          >
            结论：{{ reassessmentText(record) }}
          </p>
        </div>

        <!-- ════ §2.2 修改租赁期 ════ -->
        <div
          class="section-block"
          :class="{ highlight: needsTermModification(record) || reassessmentText(record).startsWith('应当') }"
        >
          <div class="section-title">
            <span>2.2 根据重新评估结果修改租赁期</span>
            <el-button link type="primary" size="small" @click="openTip('modify')">提示</el-button>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">（1）实际行使了以前未纳入租赁期的选择权</span>
            <el-radio-group
              :model-value="record.exercisedOptionNotIncluded"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'exercisedOptionNotIncluded', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">（2）未行使以前已纳入租赁期的选择权</span>
            <el-radio-group
              :model-value="record.didNotExerciseIncludedOption"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'didNotExerciseIncludedOption', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">（3）事件强制行使以前未纳入的选择权</span>
            <el-radio-group
              :model-value="record.eventForcesExercise"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'eventForcesExercise', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="judgment-row">
            <span class="judgment-label">（4）事件禁止行使以前已纳入的选择权</span>
            <el-radio-group
              :model-value="record.eventPreventsExercise"
              :disabled="isReadonly"
              size="small"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'eventPreventsExercise', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
            </el-radio-group>
          </div>
          <div class="inline-fields term-final">
            <el-form-item label="重新确定的租赁期(月)" class="compact-item">
              <el-input-number
                :model-value="record.redeterminedLeaseTermMonths"
                :controls="false"
                :min="0"
                :disabled="isReadonly"
                size="small"
                @change="(v: number | undefined) => onField(record.recordId, 'redeterminedLeaseTermMonths', v)"
              />
            </el-form-item>
            <el-input
              :model-value="record.redeterminedInfo"
              :disabled="isReadonly"
              size="small"
              placeholder="重新确定说明 / 合同信息"
              style="flex: 1"
              @change="(v: string) => onField(record.recordId, 'redeterminedInfo', v)"
            />
          </div>
          <div v-if="needsTermModification(record)" class="jump-row">
            <span>租赁期已变更，请同步更新计量与折旧底稿：</span>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              @click="handlePushToH86(record.recordId)"
            >
              回写 H8-6
            </el-button>
            <el-button
              v-if="!isReadonly"
              size="small"
              @click="handlePushToH88(record.recordId)"
            >
              回写 H8-8
            </el-button>
            <el-button size="small" @click="emit('navigate-sheet', 'H8-7')">跳转 H8-7</el-button>
          </div>
        </div>

        <!-- 判断说明 + 结论 -->
        <el-form size="small" label-position="top" class="term-form">
          <el-form-item label="判断说明">
            <el-input
              type="textarea"
              :autosize="{ minRows: 2 }"
              :model-value="record.explanation"
              :readonly="isReadonly"
              placeholder="综合说明续租/终止/购买选择权合理确定判断及重新评估结论…"
              @change="(v: string | number) => onField(record.recordId, 'explanation', v)"
            />
          </el-form-item>
          <el-form-item label="本项结论">
            <el-radio-group
              :model-value="record.conclusion"
              :disabled="isReadonly"
              @change="(v: string | number | boolean | undefined) => onField(record.recordId, 'conclusion', v)"
            >
              <el-radio-button value="是">是</el-radio-button>
              <el-radio-button value="否">否</el-radio-button>
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
        placeholder="请输入审计说明…"
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
        <li>详细准则说明请点各节「提示」或顶部「准则提示 / 构成示意」打开弹窗，避免主表被蓝字淹没</li>
        <li>终止选择权：合理确定<strong>不</strong>行使时才计入涵盖期间（勿与「合理确定行使」混淆）</li>
        <li>§2.1 任一重大事件为「是」→ 自动结论「应当重新评估…」（对齐 Excel C29）</li>
        <li>重新确定租赁期后跳转 H8-6 重计量；构成租赁变更时同步 H8-7</li>
        <li>有效租赁期优先取「重新确定」＞「确定的租赁期」＞公式建议值</li>
      </ul>
    </details>

    <!-- 提示弹窗 -->
    <el-drawer v-model="tipDrawerVisible" :title="activeTip?.title ?? '编制提示'" direction="rtl" size="440px">
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
            v-for="t in H8_LEASE_TERM_TIPS"
            :key="t.id"
            size="small"
            :type="t.id === activeTip.id ? 'primary' : 'default'"
            text
            @click="openTip(t.id)"
          >
            {{ t.title.length > 12 ? t.title.slice(0, 12) + '…' : t.title }}
          </el-button>
        </div>
      </div>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
/**
 * H8TabLeaseTerm.vue — H8-5 租赁期的确定
 * 对齐 Excel：§1 决策树 + §2.1/2.2 重新评估 + 提示抽屉 + 跨表跳转
 */
import { ref, computed, toRef, watch, inject } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  useH8LeaseTerm,
  H8_LEASE_TERM_TIPS,
  type H8LeaseTermRecord,
  type H8LeaseTermTip,
} from '../../composables/useH8LeaseTerm'
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
  avgLeaseTerm,
  reassessmentNeededCount,
  shortTermCandidateCount,
  addRecord,
  deleteRecord,
  updateField,
  applySuggestedTerm,
  pushLeaseTermToH86,
  pushLeaseTermToH88,
  pushShortTermToH813,
  calcLeaseTermMonths,
  calcReassessmentConclusion,
  resolveEffectiveLeaseTermMonths,
  needsTermModification,
  load,
} = useH8LeaseTerm({
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
  sheetCode: 'H8-5',
  onImported: async () => {
    await h8ReloadAll()
    load()
  },
})
const ieBusy = computed(() => isExporting.value || isImporting.value)
const fileInputRef = ref<HTMLInputElement | null>(null)

async function handleExportCommand(cmd: string) {
  if (cmd === 'export-template') await exportTemplate(['H8-5'])
  else if (cmd === 'export-data') await exportData(['H8-5'])
  else if (cmd === 'import-data') fileInputRef.value?.click()
}

async function onFileSelected(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) await importData(file, ['H8-5'])
  ;(e.target as HTMLInputElement).value = ''
}

const AUDIT_NOTE_KEY = 'H8-lease-term-audit-note'
const AUDIT_CONCLUSION_KEY = 'H8-lease-term-audit-conclusion'
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

// ── Tips drawer ──
const tipDrawerVisible = ref(false)
const activeTipId = ref('definition')
const activeTip = computed<H8LeaseTermTip | undefined>(() =>
  H8_LEASE_TERM_TIPS.find(t => t.id === activeTipId.value),
)

function openTip(id: string) {
  activeTipId.value = id
  tipDrawerVisible.value = true
}
function jumpFromTip(sheet: string) {
  tipDrawerVisible.value = false
  emit('navigate-sheet', sheet)
}

function suggestedTerm(r: H8LeaseTermRecord): number {
  return calcLeaseTermMonths(r)
}
function reassessmentText(r: H8LeaseTermRecord): string {
  return calcReassessmentConclusion(r.majorImprovement, r.majorCustomization, r.relatedBusinessDecision)
}

function onField(recordId: string, field: string, value: any) {
  updateField(recordId, field, value)
}

async function handlePushToH86(recordId: string) {
  if (props.isReadonly) return
  const r = pushLeaseTermToH86(recordId)
  if (!r.ok) {
    ElMessage.warning(r.reason || '回写失败')
    return
  }
  const changed = r.previousMonths !== r.months
  ElMessage.success(
    changed
      ? `已回写 H8-6：合同 ${r.contractNo} 租赁期 ${r.previousMonths}→${r.months} 月`
      : `已回写 H8-6：合同 ${r.contractNo} 租赁期 ${r.months} 月`,
  )
  if (r.shortTermHint) {
    ElMessage.info('租赁期≤12个月，请关注是否适用 H8-13 短期租赁简化处理')
  }
  emit('navigate-sheet', 'H8-6')
}

function handlePushToH88(recordId: string) {
  if (props.isReadonly) return
  const r = pushLeaseTermToH88(recordId)
  if (!r.ok && r.updated === 0) {
    ElMessage.warning(r.reason || '回写 H8-8 失败')
    if (r.unmatchedContracts.length) emit('navigate-sheet', 'H8-8')
    return
  }
  if (r.updated > 0) {
    ElMessage.success(`已回写 H8-8：更新 ${r.updated} 行折旧租赁期`)
  } else {
    ElMessage.info(r.reason || 'H8-8 租赁期已一致')
  }
  if (r.unmatchedContracts.length) {
    ElMessage.warning(`H8-8 无匹配合同：${r.unmatchedContracts.join('、')}（请先从 H8-2 带入）`)
  }
  emit('navigate-sheet', 'H8-8')
}

function reportH813Push(r: ReturnType<typeof pushShortTermToH813>) {
  if (!r.ok && r.updated + r.added === 0) {
    ElMessage.warning(r.reason || '推送 H8-13 失败')
    return false
  }
  const parts: string[] = []
  if (r.added) parts.push(`新增 ${r.added}`)
  if (r.updated) parts.push(`更新 ${r.updated}`)
  ElMessage.success(parts.length ? `已推送 H8-13：${parts.join('，')}` : (r.reason || '已同步'))
  if (r.skippedPurchaseOption) {
    ElMessage.info(`${r.skippedPurchaseOption} 份含购买选择权，按准则不属于短期租赁，已跳过`)
  }
  return true
}

function handlePushShortTerm(recordId: string) {
  if (props.isReadonly) return
  const rec = records.value.find(x => x.recordId === recordId)
  if (rec?.purchaseReasonablyCertain === '是') {
    ElMessage.warning('含合理确定行使的购买选择权，不属于短期租赁（CAS21），请勿按简化处理')
    return
  }
  const r = pushShortTermToH813(recordId)
  if (reportH813Push(r)) emit('navigate-sheet', 'H8-13')
}

function handlePushAllShortTerm() {
  if (props.isReadonly) return
  const r = pushShortTermToH813()
  if (reportH813Push(r)) emit('navigate-sheet', 'H8-13')
}

async function handleAddRecord() {
  const { value } = await ElMessageBox.prompt('请输入租赁合同号', '新增租赁期确定', {
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
.h8-tab-lease-term { padding: 16px; font-size: var(--wp-font-size, 13px); }

.objective-alert { margin-bottom: 12px; }
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
.stats-actions { margin-left: auto; display: flex; gap: 6px; }

.empty-state { padding: 40px 0; }
.term-card { margin-bottom: 16px; }
.card-header {
  display: flex; align-items: center; justify-content: space-between; gap: 8px; flex-wrap: wrap;
}
.header-left { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.contract-label { font-weight: 600; }
.card-actions { display: flex; align-items: center; gap: 8px; }

.section-block {
  border: 1px solid var(--el-border-color-lighter); border-radius: 6px;
  padding: 12px; margin-bottom: 12px; background: #fafafa;
}
.section-block.highlight {
  background: #fff7ed; border-color: #fdba74;
}
.section-title {
  display: flex; align-items: center; justify-content: space-between;
  font-weight: 600; margin-bottom: 10px; font-size: 13px; gap: 8px;
}

.judgment-block {
  border: 1px solid var(--el-border-color-extra-light); border-radius: 6px;
  padding: 10px 12px; margin-bottom: 10px; background: #fff;
}
.judgment-head {
  display: flex; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap;
}
.item-no { font-weight: 600; color: var(--el-color-primary); }
.item-label { flex: 1; min-width: 180px; line-height: 1.45; }

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
.inline-fields.nested { padding-left: 12px; }
.compact-item { margin-bottom: 0 !important; }
.term-final { margin-top: 8px; }

.calc-result {
  background: #f0f9ff; border-radius: 6px; padding: 10px 14px; margin-top: 4px;
}
.formula-display { font-size: var(--wp-font-size, 13px); color: var(--el-color-primary); line-height: 1.7; }

.auto-conclusion { margin: 8px 0 0; font-size: 12px; line-height: 1.5; }
.auto-conclusion.success { color: #15803d; }
.auto-conclusion.warning { color: #b45309; }
.auto-conclusion.primary { color: #1d4ed8; }
.auto-conclusion.danger { color: #b91c1c; }

.jump-row {
  display: flex; align-items: center; gap: 8px; margin-top: 10px; flex-wrap: wrap;
  font-size: 12px; color: var(--el-text-color-secondary);
}

.term-form { margin-top: 8px; }

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
