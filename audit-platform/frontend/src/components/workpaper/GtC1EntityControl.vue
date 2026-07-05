<template>
  <div class="c1-entity-control" :class="{ 'is-readonly': isReadonly }">
    <!-- 加载状态 -->
    <div v-if="isLoading" class="c1-loading">
      <el-skeleton :rows="8" animated />
    </div>

    <template v-else>
      <!-- ═══ 程序表：九段分组程序中控台（默认 / 无效 sheetName 回退） ═══ -->
      <div v-if="mode === 'program'" class="c1-program">
        <!-- 顶部操作引导区（蓝色渐变 2 列 grid 序号步骤，Req 9.3） -->
        <div class="c1-guide">
          <div class="c1-guide-head">
            <el-icon class="c1-guide-head-icon"><InfoFilled /></el-icon>
            C1 企业层面控制测试 · 操作指引
          </div>
          <div class="c1-guide-grid">
            <div v-for="s in GUIDE_STEPS" :key="s.no" class="c1-guide-step">
              <span class="c1-guide-no">{{ s.no }}</span>
              <div class="c1-guide-txt">
                <div class="c1-guide-title">{{ s.title }}</div>
                <div class="c1-guide-desc">{{ s.desc }}</div>
              </div>
            </div>
          </div>
        </div>

        <!-- 九段分组导航 + 各组完成进度 + 整段适用性裁剪（Req 2.1/2.3/3.x） -->
        <el-collapse v-model="activeSections" class="c1-section-nav">
          <el-collapse-item
            v-for="g in sectionGroups"
            :key="g.slug"
            :name="g.slug"
          >
            <template #title>
              <div class="c1-sec-head">
                <span class="c1-sec-title">{{ g.order }}. {{ g.title }}</span>
                <el-tag
                  v-if="!g.defaultApplicable"
                  size="small"
                  type="info"
                  effect="plain"
                >{{ g.note || '按需适用' }}</el-tag>
                <!-- 整段适用性裁剪开关（Req 3.1/3.4 即时保存；不适用需理由 Req 3.2） -->
                <span class="c1-sec-applicable" @click.stop>
                  <span class="c1-applicable-label">适用</span>
                  <el-switch
                    :model-value="isSectionApplicable(g.slug)"
                    :disabled="isReadonly"
                    size="small"
                    inline-prompt
                    active-text="是"
                    inactive-text="否"
                    @change="(val: any) => onToggleSectionApplicable(g.slug, !!val)"
                  />
                </span>
                <el-progress
                  class="c1-sec-progress"
                  :percentage="sectionProgress(g.slug)"
                  :stroke-width="8"
                  :color="sectionProgress(g.slug) === 100 ? '#67C23A' : '#4b2d77'"
                  style="width: 120px"
                />
              </div>
            </template>
            <div class="c1-sec-body">
              <!-- 不适用：显示裁剪理由，排除进度统计（Req 3.3） -->
              <div v-if="!isSectionApplicable(g.slug)" class="c1-sec-trimmed">
                <el-alert type="info" :closable="false" show-icon>
                  <template #title>
                    本段已标记「不适用」，不参与完成进度统计。
                  </template>
                  <div class="c1-trim-reason">裁剪理由：{{ sectionReason(g.slug) || '（未填写）' }}</div>
                </el-alert>
              </div>
              <template v-else>
                <!-- 方法论上下文（源模板红字提示 → 琥珀色左边线区块，Req 9.4） -->
                <div v-if="methodologyOf(g.slug)" class="c1-methodology">
                  <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
                  <span class="c1-meth-text">{{ methodologyOf(g.slug) }}</span>
                </div>
                <!-- 已分组：本段程序步骤（复用 GtAProgramConsole，Req 2.2） -->
                <GtAProgramConsole
                  v-if="hasSectionData"
                  :wp-id="props.wpId"
                  :sheet-name="programSheetName"
                  :schema="programSchema"
                  :html-data="{ programs: groupedPrograms(g.slug), schema: programSchema }"
                  :readonly="isReadonly"
                  :hide-categories="true"
                />
                <p v-else class="c1-sec-hint">
                  本段（{{ g.title }}）测试程序请在下方程序表中执行；分组进度依据适用性与测试结果实时统计。
                </p>
              </template>
            </div>
          </el-collapse-item>
        </el-collapse>

        <!-- 未分组时：单一程序中控台（selfLoad 全量；GtAProgramConsole 内建 grid 兜底，Req 2.4） -->
        <GtAProgramConsole
          v-if="!hasSectionData"
          class="c1-program-console"
          :wp-id="props.wpId"
          :sheet-name="programSheetName"
          :schema="programSchema"
          :html-data="{ programs: [], schema: programSchema }"
          :readonly="isReadonly"
          :hide-categories="true"
        />

        <!-- ═══ 整体结论 + 缺陷联动（Task 7.3, Req 11.1~11.4） ═══ -->
        <el-card shadow="never" class="c1-card c1-conclusion-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">企业层面控制整体结论</span>
              <el-tooltip content="就低聚合各适用段结论自动建议整体结论；用户可点选覆盖。结论变更时回写 B50 风险评估。" placement="top">
                <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
              </el-tooltip>
            </div>
          </template>

          <!-- 各段结论点选（汇总各要素结论，供自动建议） -->
          <table class="c1-grid-table c1-conclusion-table">
            <thead>
              <tr>
                <th style="min-width: 200px">要素 / 段</th>
                <th style="min-width: 160px">本段测试结论</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in sectionGroups" :key="g.slug">
                <td class="c1-cell-name">
                  {{ g.order }}. {{ g.title }}
                  <el-tag v-if="!isSectionApplicable(g.slug)" size="small" type="info" effect="plain">不适用</el-tag>
                </td>
                <td>
                  <el-select
                    :model-value="getConclusion(sectionConclusionId(g.slug))"
                    :disabled="isReadonly || !isSectionApplicable(g.slug)"
                    size="small"
                    clearable
                    placeholder="结论"
                    @change="(v: any) => setSectionConclusion(g.slug, v)"
                  >
                    <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </td>
              </tr>
            </tbody>
          </table>

          <!-- 整体结论：自动建议 + 点选覆盖 -->
          <div class="c1-overall-row">
            <span class="c1-overall-label">企业层面控制整体结论</span>
            <el-select
              :model-value="overallConclusion"
              :disabled="isReadonly"
              size="small"
              clearable
              placeholder="请点选整体结论"
              class="c1-overall-select"
              @change="(v: any) => setOverallConclusion(v)"
            >
              <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
            </el-select>
            <el-tag v-if="suggestedOverall" size="small" type="warning" effect="plain" class="c1-suggest-tag">
              建议：{{ suggestedOverall }}
            </el-tag>
            <el-button
              v-if="!isReadonly"
              size="small"
              type="primary"
              plain
              :disabled="!suggestedOverall"
              @click="applySuggestedOverall"
            >采用建议</el-button>
          </div>
        </el-card>

        <!-- 识别缺陷 → 一键跳 A14 缺陷评价（带入摘要，Req 11.2） -->
        <el-card shadow="never" class="c1-card c1-defect-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">识别的企业层面控制缺陷</span>
              <div class="c1-card-actions">
                <el-tooltip content="登记识别出的企业层面控制缺陷；点击 A14 chip 一键跳转缺陷评价底稿并带入摘要。" placement="top">
                  <el-icon class="c1-meth-icon"><InfoFilled /></el-icon>
                </el-tooltip>
                <el-button v-if="!isReadonly" size="small" type="primary" @click="addDefectRow">+ 新增缺陷</el-button>
              </div>
            </div>
          </template>
          <table class="c1-grid-table c1-defect-table">
            <thead>
              <tr>
                <th style="width: 32px">#</th>
                <th style="min-width: 320px">缺陷摘要</th>
                <th style="width: 140px">缺陷评价</th>
                <th v-if="!isReadonly" style="width: 48px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in defectRows" :key="row.__did">
                <td class="c1-cell-idx">{{ i + 1 }}</td>
                <td>
                  <el-input
                    :model-value="row.summary"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    size="small"
                    placeholder="描述识别出的企业层面控制缺陷（将带入 A14 缺陷评价）"
                    @input="(v: any) => onDefectSummary(i, v)"
                  />
                </td>
                <td class="c1-defect-jump">
                  <GtIndexChip
                    :value="A14_WP_CODE"
                    :context-project-id="props.projectId"
                    @click="onDefectJumpToA14(i)"
                  />
                </td>
                <td v-if="!isReadonly">
                  <el-button type="danger" size="small" text @click="removeDefectRow(i)">删除</el-button>
                </td>
              </tr>
              <tr v-if="defectRows.length === 0">
                <td :colspan="isReadonly ? 3 : 4" class="c1-empty-row">
                  暂无识别的企业层面控制缺陷{{ isReadonly ? '' : '，点击「+ 新增缺陷」登记' }}
                </td>
              </tr>
            </tbody>
          </table>
        </el-card>
      </div>

      <!-- ═══ 示例 sheet（C1-1~C1-3）：只读参考（Req 5） ═══ -->
      <div v-else-if="mode === 'example'" class="c1-example">
        <el-alert
          title="示例（供参考）"
          type="info"
          :closable="false"
          show-icon
          description="本 sheet 为企业层面控制测试示例，仅供编制参考，不参与完成进度统计。"
        />
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="true"
          style="height: calc(100vh - 220px)"
        />
      </div>

      <!-- ═══ 财报内控关键控制汇总（C1-4，Req 4，交互式汇总表） ═══ -->
      <div v-else-if="mode === 'fr-summary'" class="c1-fr-summary">
        <el-alert
          title="财务报告内部控制 — 关键控制汇总"
          type="warning"
          :closable="false"
          show-icon
          description="6 项关键控制汇总。过程记录明细见 C1-4-1~C1-4-6 子表。"
        />
        <el-card shadow="never" class="c1-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">财报内控关键控制 — 测试说明</span>
              <el-tooltip :content="aiTip" placement="top">
                <el-button
                  size="small"
                  type="primary"
                  plain
                  :disabled="isReadonly || !aiEnabled"
                  class="c1-ai-btn"
                >
                  <el-icon><MagicStick /></el-icon> AI 辅助
                </el-button>
              </el-tooltip>
            </div>
          </template>
          <table class="c1-grid-table">
            <thead>
              <tr>
                <th style="width: 32px">#</th>
                <th style="min-width: 200px">关键控制</th>
                <!-- 判断列 tooltip：说明来源与判断依据（Req 9.5） -->
                <th style="min-width: 120px">
                  <el-tooltip content="控制频率：源自客户控制描述；判断依据为该控制的执行周期（每月/每季/每年/按需）" placement="top">
                    <span class="c1-judge-head">控制频率</span>
                  </el-tooltip>
                </th>
                <th style="min-width: 200px">
                  <el-tooltip content="测试方法（可多选）：询问和观察/检查/重新执行/抽样；依据控制性质与测试目标选择" placement="top">
                    <span class="c1-judge-head">测试方法</span>
                  </el-tooltip>
                </th>
                <th style="min-width: 120px">
                  <el-tooltip content="测试结论：有效/部分有效/无效；依据样本测试结果与偏差评价判断" placement="top">
                    <span class="c1-judge-head">测试结论</span>
                  </el-tooltip>
                </th>
                <th style="min-width: 220px">说明</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(name, i) in FR_SUMMARY_CONTROLS" :key="i">
                <td class="c1-cell-idx">{{ i + 1 }}</td>
                <td class="c1-cell-name">{{ name }}</td>
                <td>
                  <el-select
                    :model-value="getConclusion(summaryItemId(i + 1, 'freq'))"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    placeholder="频率"
                    @change="(v: any) => setEnum(summaryItemId(i + 1, 'freq'), v)"
                  >
                    <el-option v-for="o in FREQ_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </td>
                <td>
                  <!-- 测试方法多选点选（checkbox-group，Req 9.1） -->
                  <el-checkbox-group
                    :model-value="getMultiEnum(summaryItemId(i + 1, 'method'))"
                    :disabled="isReadonly"
                    size="small"
                    class="c1-method-group"
                    @change="(v: any) => setMultiEnum(summaryItemId(i + 1, 'method'), v)"
                  >
                    <el-checkbox v-for="o in TEST_METHOD_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-checkbox-group>
                </td>
                <td>
                  <el-select
                    :model-value="getConclusion(summaryItemId(i + 1, 'conclusion'))"
                    :disabled="isReadonly"
                    size="small"
                    clearable
                    placeholder="结论"
                    @change="(v: any) => setEnum(summaryItemId(i + 1, 'conclusion'), v)"
                  >
                    <el-option v-for="o in CONCLUSION_OPTIONS" :key="o" :label="o" :value="o" />
                  </el-select>
                </td>
                <td>
                  <el-input
                    :model-value="getRemark(summaryItemId(i + 1, 'note')) || ''"
                    :disabled="isReadonly"
                    type="textarea"
                    :autosize="{ minRows: 1, maxRows: 4 }"
                    size="small"
                    placeholder="说明"
                    @input="(v: any) => setTextDebounced(summaryItemId(i + 1, 'note'), v)"
                  />
                </td>
              </tr>
            </tbody>
          </table>
        </el-card>
      </div>

      <!-- ═══ 过程记录表（C1-4-1/2/3/5/6，Req 4.1/4.2 交互式字段） ═══ -->
      <div v-else-if="mode === 'process-record'" class="c1-process-record">
        <el-card shadow="never" class="c1-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">过程记录 — 测试结果说明</span>
              <div class="c1-card-actions">
                <el-tooltip :content="aiTip" placement="top">
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :disabled="isReadonly || !aiEnabled"
                    class="c1-ai-btn"
                  >
                    <el-icon><MagicStick /></el-icon> AI 辅助
                  </el-button>
                </el-tooltip>
                <!-- 📎 附件上传 + OCR 识别（Req 10.1/10.2；非破坏性 merge Req 10.3；只读仅查看 Req 10.5） -->
                <el-upload
                  v-if="!isReadonly"
                  :show-file-list="false"
                  :auto-upload="false"
                  accept="image/*,.pdf"
                  class="c1-attach-upload"
                  @change="(f: any) => onUploadProcOcr(f.raw || f)"
                >
                  <el-button link size="small" title="上传凭证/记录图片或 PDF，OCR 识别后确认填入">📎 附件</el-button>
                </el-upload>
                <el-tooltip v-if="procAttachName()" :content="procAttachName()" placement="top">
                  <el-icon class="c1-attach-flag"><Paperclip /></el-icon>
                </el-tooltip>
                <span v-else-if="isReadonly" class="c1-ref-empty c1-attach-empty">📎 —</span>
              </div>
            </div>
          </template>
          <ProcessRecordFields
            :sub-index="subIndex"
            :fields="processFields"
            :readonly="isReadonly"
            :get-enum="getConclusion"
            :get-text="getRemark"
            :freq-options="FREQ_OPTIONS"
            :method-options="TEST_METHOD_OPTIONS"
            :proc-item-id="procItemId"
            @set-enum="setEnum"
            @set-text="setTextDebounced"
          />
          <!-- 关联底稿索引（GtIndexChip，Req 6.1/6.2/6.3） -->
          <div class="c1-ref-row">
            <span class="c1-ref-label">关联底稿索引</span>
            <div class="c1-ref-body">
              <el-input
                v-if="!isReadonly"
                :model-value="getRemark(procItemId('refIndex')) || ''"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }"
                size="small"
                placeholder="输入关联底稿编码，如 C21-1、A14（多个用逗号分隔）"
                @input="(v: any) => setTextDebounced(procItemId('refIndex'), v)"
              />
              <div class="c1-ref-chips">
                <GtIndexChip
                  v-for="(r, ri) in splitRefs(getRemark(procItemId('refIndex')))"
                  :key="ri"
                  :value="r"
                  :context-project-id="props.projectId"
                />
                <span v-if="splitRefs(getRemark(procItemId('refIndex'))).length === 0" class="c1-ref-empty">—</span>
              </div>
            </div>
          </div>
        </el-card>
      </div>

      <!-- ═══ 过程记录 + 借贷勾稽样本表（C1-4-4，Req 4.3/4.4） ═══ -->
      <div v-else-if="mode === 'process-record-sample'" class="c1-process-sample">
        <el-card shadow="never" class="c1-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">过程记录 — 测试结果说明</span>
              <div class="c1-card-actions">
                <el-tooltip :content="aiTip" placement="top">
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :disabled="isReadonly || !aiEnabled"
                    class="c1-ai-btn"
                  >
                    <el-icon><MagicStick /></el-icon> AI 辅助
                  </el-button>
                </el-tooltip>
                <!-- 📎 附件上传 + OCR 识别（Req 10.1/10.2；非破坏性 merge Req 10.3；只读仅查看 Req 10.5） -->
                <el-upload
                  v-if="!isReadonly"
                  :show-file-list="false"
                  :auto-upload="false"
                  accept="image/*,.pdf"
                  class="c1-attach-upload"
                  @change="(f: any) => onUploadProcOcr(f.raw || f)"
                >
                  <el-button link size="small" title="上传凭证/记录图片或 PDF，OCR 识别后确认填入">📎 附件</el-button>
                </el-upload>
                <el-tooltip v-if="procAttachName()" :content="procAttachName()" placement="top">
                  <el-icon class="c1-attach-flag"><Paperclip /></el-icon>
                </el-tooltip>
                <span v-else-if="isReadonly" class="c1-ref-empty c1-attach-empty">📎 —</span>
              </div>
            </div>
          </template>
          <ProcessRecordFields
            :sub-index="4"
            :fields="processFields"
            :readonly="isReadonly"
            :get-enum="getConclusion"
            :get-text="getRemark"
            :freq-options="FREQ_OPTIONS"
            :method-options="TEST_METHOD_OPTIONS"
            :proc-item-id="procItemId"
            @set-enum="setEnum"
            @set-text="setTextDebounced"
          />
          <!-- 关联底稿索引（GtIndexChip，Req 6.1/6.2/6.3） -->
          <div class="c1-ref-row">
            <span class="c1-ref-label">关联底稿索引</span>
            <div class="c1-ref-body">
              <el-input
                v-if="!isReadonly"
                :model-value="getRemark(procItemId('refIndex')) || ''"
                type="textarea"
                :autosize="{ minRows: 1, maxRows: 2 }"
                size="small"
                placeholder="输入关联底稿编码，如 C21-1、A14（多个用逗号分隔）"
                @input="(v: any) => setTextDebounced(procItemId('refIndex'), v)"
              />
              <div class="c1-ref-chips">
                <GtIndexChip
                  v-for="(r, ri) in splitRefs(getRemark(procItemId('refIndex')))"
                  :key="ri"
                  :value="r"
                  :context-project-id="props.projectId"
                />
                <span v-if="splitRefs(getRemark(procItemId('refIndex'))).length === 0" class="c1-ref-empty">—</span>
              </div>
            </div>
          </div>
        </el-card>

        <el-card shadow="never" class="c1-card c1-sample-card">
          <template #header>
            <div class="c1-card-head">
              <span class="c1-card-title">会计分录人工授权测试 — 样本明细</span>
              <div class="c1-card-actions">
                <el-tooltip :content="aiTip" placement="top">
                  <el-button
                    size="small"
                    type="primary"
                    plain
                    :disabled="isReadonly || !aiEnabled"
                    class="c1-ai-btn"
                  >
                    <el-icon><MagicStick /></el-icon> AI 辅助
                  </el-button>
                </el-tooltip>
                <el-button
                  v-if="!isReadonly"
                  type="primary"
                  size="small"
                  @click="addSampleRow"
                >+ 新增样本行</el-button>
              </div>
            </div>
          </template>

          <table class="c1-grid-table c1-sample-table">
            <thead>
              <tr>
                <th style="width: 32px">#</th>
                <th style="min-width: 120px">日期</th>
                <th style="min-width: 120px">账户编码</th>
                <th style="min-width: 120px">引用（关联底稿）</th>
                <th style="min-width: 200px">交易描述</th>
                <th style="min-width: 120px">借方金额（元）</th>
                <th style="min-width: 120px">贷方金额（元）</th>
                <!-- 只读派生列：借贷勾稽（useC1SampleEngine，不可手工覆盖，Req 4.4） -->
                <th style="min-width: 120px">
                  <el-tooltip content="源模板 C1-4-4 借贷勾稽公式：累计 Σ借方 − Σ贷方（只读派生，不可手工覆盖）" placement="top">
                    <span class="c1-formula-head">累计借贷差<sup>ƒ</sup></span>
                  </el-tooltip>
                </th>
                <!-- 📎 附件上传 + OCR 识别列（Req 10.1/10.2；只读仅查看，Req 10.5） -->
                <th style="width: 96px">
                  <el-tooltip content="上传凭证/记录图片或 PDF，OCR 识别关键字段后确认填入（非破坏性 merge，不覆盖已有值）" placement="top">
                    <span class="c1-judge-head">📎 附件</span>
                  </el-tooltip>
                </th>
                <th v-if="!isReadonly" style="width: 48px">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, i) in sampleRows" :key="row.__rid">
                <td class="c1-cell-idx">{{ i + 1 }}</td>
                <td>
                  <el-input
                    :model-value="row.date"
                    :disabled="isReadonly"
                    size="small"
                    placeholder="日期"
                    @input="(v: any) => onSampleCell(i, 'date', v)"
                  />
                </td>
                <td>
                  <el-input
                    :model-value="row.account"
                    :disabled="isReadonly"
                    size="small"
                    placeholder="账户编码"
                    @input="(v: any) => onSampleCell(i, 'account', v)"
                  />
                </td>
                <td>
                  <!-- 引用列：可编辑输入 + GtIndexChip 关联底稿跳转（Req 6.1/6.2/6.3） -->
                  <el-input
                    v-if="!isReadonly"
                    :model-value="row.ref"
                    size="small"
                    placeholder="引用底稿，如 C21-1"
                    @input="(v: any) => onSampleCell(i, 'ref', v)"
                  />
                  <div class="c1-ref-chips">
                    <GtIndexChip
                      v-for="(r, ri) in splitRefs(row.ref)"
                      :key="ri"
                      :value="r"
                      :context-project-id="props.projectId"
                    />
                    <span v-if="isReadonly && splitRefs(row.ref).length === 0" class="c1-ref-empty">—</span>
                  </div>
                </td>
                <td>
                  <el-input
                    :model-value="row.desc"
                    :disabled="isReadonly"
                    size="small"
                    placeholder="交易描述"
                    @input="(v: any) => onSampleCell(i, 'desc', v)"
                  />
                </td>
                <td>
                  <el-input
                    :model-value="row.debit"
                    :disabled="isReadonly"
                    size="small"
                    placeholder="借方"
                    @input="(v: any) => onSampleCell(i, 'debit', v)"
                  />
                </td>
                <td>
                  <el-input
                    :model-value="row.credit"
                    :disabled="isReadonly"
                    size="small"
                    placeholder="贷方"
                    @input="(v: any) => onSampleCell(i, 'credit', v)"
                  />
                </td>
                <!-- 只读派生列 -->
                <td class="c1-formula-cell">
                  <span class="c1-formula-val">{{ fmtAmount(rowCumulativeDiff(i)) }}</span>
                </td>
                <!-- 📎 附件上传 + OCR（Req 10.1~10.5） -->
                <td class="c1-attach-cell">
                  <el-upload
                    v-if="!isReadonly"
                    :show-file-list="false"
                    :auto-upload="false"
                    accept="image/*,.pdf"
                    @change="(f: any) => onUploadSampleOcr(i, f.raw || f)"
                    style="display: inline-block"
                  >
                    <el-button link size="small" title="上传附件并 OCR 识别">📎</el-button>
                  </el-upload>
                  <el-tooltip
                    v-if="sampleAttachName(row.__rid)"
                    :content="sampleAttachName(row.__rid)"
                    placement="top"
                  >
                    <el-icon class="c1-attach-flag"><Paperclip /></el-icon>
                  </el-tooltip>
                  <span v-else-if="isReadonly" class="c1-ref-empty">—</span>
                </td>
                <td v-if="!isReadonly">
                  <el-button
                    type="danger"
                    size="small"
                    text
                    @click="removeSampleRow(i)"
                  >删除</el-button>
                </td>
              </tr>
              <tr v-if="sampleRows.length === 0">
                <td :colspan="isReadonly ? 9 : 10" class="c1-empty-row">
                  暂无样本明细{{ isReadonly ? '' : '，点击「+ 新增样本行」开始录入' }}
                </td>
              </tr>
            </tbody>
            <!-- 合计 + 借贷勾稽（只读派生，Req 4.4） -->
            <tfoot v-if="sampleRows.length > 0">
              <tr class="c1-sample-foot">
                <td colspan="5" style="text-align: right">合计（元）</td>
                <td class="c1-formula-cell">
                  <el-tooltip content="源模板 C1-4-4：Σ借方金额（只读派生）" placement="top">
                    <span class="c1-formula-val">{{ fmtAmount(sampleBalance.debitTotal) }}</span>
                  </el-tooltip>
                </td>
                <td class="c1-formula-cell">
                  <el-tooltip content="源模板 C1-4-4：Σ贷方金额（只读派生）" placement="top">
                    <span class="c1-formula-val">{{ fmtAmount(sampleBalance.creditTotal) }}</span>
                  </el-tooltip>
                </td>
                <td class="c1-formula-cell">
                  <el-tag
                    :type="sampleBalance.balanced ? 'success' : 'danger'"
                    size="small"
                    effect="plain"
                  >{{ sampleBalance.balanced ? '借贷平衡' : '借贷不平' }}</el-tag>
                </td>
                <td></td>
                <td v-if="!isReadonly"></td>
              </tr>
            </tfoot>
          </table>
        </el-card>
      </div>

      <!-- ═══ 兜底：无效 sheetName 已在 mode 计算中回退 program，此分支仅防御 ═══ -->
      <div v-else class="c1-fallback">
        <GtOnlyOfficeSheet
          :wp-id="props.wpId"
          :project-id="props.projectId"
          :sheet-name="props.sheetName || ''"
          :readonly="isReadonly"
          style="height: calc(100vh - 180px)"
        />
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
/**
 * GtC1EntityControl.vue — C1 企业层面控制测试底稿主入口
 *
 * Spec: .kiro/specs/c1-entity-level-control/  Task 4.1 + 4.2
 * Requirements: 1.1, 1.5, 2.1~2.4, 3.1~3.4, 4.1~4.3, 5.1~5.3
 *
 * sheetName v-if 分发（不使用内部 el-tabs，同 D4 铁律）：
 *   program                → 九段分组程序中控台 + 整段适用性裁剪
 *   example                → C1-1~C1-3 示例只读（供参考标注，不计进度）
 *   fr-summary             → C1-4 财报内控关键控制汇总（交互式表格）
 *   process-record         → C1-4-1/2/3/5/6 过程记录表（交互式字段）
 *   process-record-sample  → C1-4-4 过程记录 + 借贷勾稽样本表（只读派生列）
 *   无效 sheetName          → 回退 program（design Error Handling）
 *
 * Task 4.2 交付：适用性裁剪（是否适用 + 理由，不适用无理由拒绝保存，排除进度分母）；
 * 过程记录子表交互字段（phase0 §5）；C1-4-4 样本明细可编辑 + useC1SampleEngine 借贷勾稽只读派生列；
 * 示例只读保留。数据经 useC1ControlData（适用性/枚举即时保存，文本 debounce）。
 */
import { ref, computed, onMounted, toRef, defineAsyncComponent, defineComponent, h, type PropType } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick, InfoFilled, Paperclip } from '@element-plus/icons-vue'
import { api } from '@/services/apiProxy'
import http from '@/utils/http'
import { eventBus } from '@/utils/eventBus'
import { fmtAmount } from '@/utils/formatters'
import { useC1ControlData, C1_ITEM_PREFIX } from './composables/useC1ControlData'
import {
  calcSampleBalance,
  mapOcrToSampleCells,
  mergeSampleRow,
  type JeSample,
  type SampleCellMap,
} from './composables/useC1SampleEngine'
import { C1_SECTION_DEFS, sectionProgressPercent } from './composables/useC1SectionEngine'
import {
  FREQ_OPTIONS as ENGINE_FREQ_OPTIONS,
  TEST_METHOD_OPTIONS as ENGINE_TEST_METHOD_OPTIONS,
  CONCLUSION_OPTIONS as ENGINE_CONCLUSION_OPTIONS,
  sanitizeEnumValue,
  sanitizeMultiEnum,
  suggestOverallConclusion,
  shouldPublishConclusion,
  normalizeConclusion,
} from './composables/useC1ConclusionEngine'

const GtAProgramConsole = defineAsyncComponent(() => import('./GtAProgramConsole.vue'))
const GtOnlyOfficeSheet = defineAsyncComponent(() => import('./GtOnlyOfficeSheet.vue'))
// 跨底稿索引跳转 chip（prop 名 `value`，非 `wp`；自带存在性校验+灰态，Req 6.1~6.3）
const GtIndexChip = defineAsyncComponent(() => import('./GtIndexChip.vue'))

// ─── Props / Emits ─────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  wpCode?: string // "C1"
  year?: number
  readonly?: boolean
  sheetName?: string
  htmlData?: any
}>()

defineEmits<{
  (e: 'save'): void
  (e: 'completed'): void
}>()

// ─── 枚举点选选项（phase0 §5 实测取值，Req 9.1 点选候选） ────────────────────

// 单一来源：点选字段枚举统一由 useC1ConclusionEngine 提供（P7 点选值合法性同源）。
// 展开为可变 string[]，便于模板 v-for 与 .includes 使用。
const FREQ_OPTIONS: string[] = [...ENGINE_FREQ_OPTIONS]
// 测试方法为多选（点选 checkbox-group，Req 9.1 / design 点选控件映射）
const TEST_METHOD_OPTIONS: string[] = [...ENGINE_TEST_METHOD_OPTIONS]
const CONCLUSION_OPTIONS: string[] = [...ENGINE_CONCLUSION_OPTIONS]

// ─── 顶部操作引导区（蓝色渐变 2 列 grid，Req 9.3） ───────────────────────────

const GUIDE_STEPS = [
  { no: 1, title: '填写项目信息', desc: '确认被审计单位、会计期间与集团/关联方适用范围' },
  { no: 2, title: '逐要素测试', desc: '按 COSO 五要素派生的九段执行询问/观察/检查，点选是否适用与结论' },
  { no: 3, title: '财报内控过程记录', desc: '在 C1-4 记录关键控制描述、测试方法与样本借贷勾稽' },
  { no: 4, title: '形成结论', desc: '汇总各要素测试结论，形成企业层面控制整体结论' },
]

// ─── 方法论上下文（源模板红字提示 → 琥珀色左边线区块，Req 9.4） ───────────────
// 将 COSO 五要素方法论内涵嵌入对应九段分组上方，作为编制方法论叙述。

const C1_METHODOLOGY: Record<string, string> = {
  ce: '控制环境（COSO 要素一）：内部控制的基础。评价管理层诚信与道德价值观、治理层独立性与监督、组织架构与权责分配、人力资源政策。',
  ra: '风险评估（COSO 要素二）：识别与分析实现财务报告目标相关的风险，关注舞弊风险与经营环境重大变化的识别与应对。',
  mo: '监督（COSO 要素五）：通过持续监督与专项评价，确认内部控制各要素是否持续有效运行、缺陷是否及时沟通整改。',
  bu: '仅集团审计适用：评价集团管理层对业务单元（组成部分）的监控，是否覆盖组成部分层面的重大错报风险。非集团审计可整段标记不适用。',
  ic: '信息与沟通（COSO 要素四）：确认相关、高质量的信息在组织内部与外部得到识别、获取、处理与传递，支持内部控制运行。',
  fr: '财务报告内部控制：与财务报告认定直接相关的关键控制，是整合审计的核心测试对象（详见 C1-4 过程记录子表）。',
  el: '对业务层面控制的影响：评价企业层面控制对业务流程层面控制的影响，据此确定控制测试的性质、时间与范围。',
  ye: '年终程序：关注期末财务报告编制与列报相关的企业层面控制，如合并、关账与重大会计估计复核。',
  rp: '仅有关联方交易时适用：测试与降低关联方关系及其交易导致重大错报风险相关的控制环境内容。无关联方交易可整段标记不适用。',
}

function methodologyOf(slug: string): string {
  return C1_METHODOLOGY[slug] || ''
}

/** C1-4 财报内控 6 项关键控制（phase0 tab #6 实测） */
const FR_SUMMARY_CONTROLS = [
  'FINC-US-002 账户结构图变更',
  '会计准则符合性评估',
  '追溯原始分录',
  'FINC-US 会计分录人工授权',
  'FINC-US-008 分录分类',
  '会计准则遵循评价',
]

// ─── 过程记录字段配置（phase0 §5 统一字段集） ────────────────────────────────

type ProcFieldType = 'text' | 'freq' | 'method'
interface ProcField { key: string; label: string; type: ProcFieldType }

const PROCESS_FIELDS_COMMON: ProcField[] = [
  { key: 'activity', label: '活动名', type: 'text' },
  { key: 'process', label: '流程名', type: 'text' },
  { key: 'control', label: '控制', type: 'text' },
  { key: 'custDesc', label: '客户控制描述', type: 'text' },
  { key: 'custCode', label: '客户控制编码', type: 'text' },
  { key: 'freq', label: '控制频率', type: 'freq' },
  { key: 'execDate', label: '执行日期', type: 'text' },
  { key: 'processOwner', label: '流程负责人', type: 'text' },
  { key: 'controlOwner', label: '控制负责人', type: 'text' },
  { key: 'interviewee', label: '访问的人员', type: 'text' },
  { key: 'interviewDate', label: '访问日期', type: 'text' },
  { key: 'testMethod', label: '测试方法', type: 'method' },
  { key: 'howTest', label: '如何测试', type: 'text' },
  { key: 'testResult', label: '测试结果', type: 'text' },
]

// ─── 九段分组配置（Phase0 实测；后端 render-config 优先，常量兜底） ──────────

interface C1SectionGroup {
  slug: string
  order: number
  title: string
  defaultApplicable: boolean
  note?: string
}

/** 常量兜底：派生自 useC1SectionEngine.C1_SECTION_DEFS（单一来源），
 * 与后端 _c1_entity_control.C1_SECTION_GROUPS / C1.yaml section_groups 对齐 */
const C1_SECTIONS_FALLBACK: C1SectionGroup[] = C1_SECTION_DEFS.map((d) => ({
  slug: d.slug,
  order: d.order,
  title: d.title,
  defaultApplicable: d.defaultApplicable,
  note: d.note,
}))

// ─── State ───────────────────────────────────────────────────────────────

const isLoading = ref(false)
const isReadonly = computed(() => !!props.readonly)
const sectionGroups = ref<C1SectionGroup[]>([...C1_SECTIONS_FALLBACK])
const activeSections = ref<string[]>(C1_SECTIONS_FALLBACK.map((g) => g.slug))
const programSheetName = computed(() => props.sheetName || 'C1 企业层面控制测试程序表')
const programSchema = { columns: [], rows: [] }

/** 已加载的程序步骤（用于分组，含 section/phase 字段时启用分组渲染） */
const programs = ref<any[]>([])
const hasSectionData = computed(() =>
  programs.value.some((p) => typeof (p?.section ?? p?.phase) === 'string'
    && sectionGroups.value.some((g) => g.slug === (p.section ?? p.phase))),
)

// ─── 数据持久化（useC1ControlData：加载 C1- 前缀 checklist-responses） ────────

const c1data = useC1ControlData(toRef(props, 'wpId'), {
  projectId: toRef(props, 'projectId') as any,
  readonly: isReadonly,
})

// 读写便捷透传
const getConclusion = (id: string) => c1data.getConclusion(id)
const getRemark = (id: string) => c1data.getRemark(id)
const setEnum = (id: string, v: string | null) => c1data.setConclusion(id, v ?? null)
const setTextDebounced = (id: string, v: string) => c1data.setText(id, v ?? '')

// 多选枚举（测试方法 checkbox-group，Req 9.1）：conclusion 存逗号连接串，读取切分为数组。
// 保存前过滤到合法选项，杜绝自由文本注入（Property 7 点选值合法性）。
const getMultiEnum = (id: string): string[] => {
  const v = getConclusion(id)
  return v ? v.split(',').map((s) => s.trim()).filter(Boolean) : []
}
const setMultiEnum = (id: string, arr: string[] | null): void => {
  // P7 点选值合法性：仅保留合法枚举成员，杜绝自由文本注入（sanitizeMultiEnum 单一来源）
  const clean = sanitizeMultiEnum(TEST_METHOD_OPTIONS, arr)
  setEnum(id, clean.length ? clean.join(',') : null)
}
/** 单选点选安全写入（P7）：非法值一律落为 null，不保存自由文本 */
const setPointSelect = (id: string, options: string[], v: unknown): void => {
  setEnum(id, sanitizeEnumValue(options, v))
}

// ─── 跨底稿引用解析（Req 6.1：索引列/过程记录含其他底稿编码 → GtIndexChip） ──────
// 文本可能含多个引用（如「C21-1，A14」或「<C21-1>」），按常见分隔符切分并去符号。
// 具体存在性校验与灰态由 GtIndexChip 自身完成（validate 调 /api/wp-index-resolve）。
function splitRefs(text?: string | null): string[] {
  if (!text) return []
  return String(text)
    .split(/[,，;；、\s/]+/)
    .map((s) => s.replace(/[<>【】()（）\[\]]/g, '').trim())
    .filter(Boolean)
}

// ─── AI 辅助（Req 8.3：section 标题行右侧提供 AI 辅助按钮） ────────────────────
// 依 WP_AI_SERVICE_ENABLED feature-flag 启用；真实生成逻辑在 Task 7.1 接入。
const aiEnabled = ref(false)
const aiTip = computed(() => (aiEnabled.value ? 'AI 辅助生成' : 'AI 辅助生成（服务暂未开启）'))
async function checkAiHealth(): Promise<void> {
  try {
    const resp: any = await api.get('/api/feature-flags', { _silent: true } as any)
    const flags = resp?.flags || resp || {}
    aiEnabled.value = !!flags.WP_AI_SERVICE_ENABLED
  } catch {
    aiEnabled.value = false
  }
}

// ─── sheetName v-if 分发（Req 1.5） ──────────────────────────────────────────

const mode = computed<string>(() => {
  const n = props.sheetName || ''
  if (!n) return 'program'
  if (/C1-4-4/.test(n)) return 'process-record-sample'
  if (/C1-4-[1-6]/.test(n)) return 'process-record'
  if (/C1-4/.test(n) || /财务报告内部控制/.test(n)) return 'fr-summary'
  if (/C1-[123](?!\d)/.test(n) || /示例[123１２３]/.test(n)) return 'example'
  if (/程序表/.test(n)) return 'program'
  return 'program'
})

/** 子表序号（C1-4-{k}）：process-record=1/2/3/5/6，sample=4，fr-summary=0 */
const subIndex = computed<number>(() => {
  const m = (props.sheetName || '').match(/C1-4-([1-6])/)
  return m ? Number(m[1]) : 0
})

/** 当前过程记录表字段集（C1-4-2 额外含「重要性」，phase0 §5） */
const processFields = computed<ProcField[]>(() => {
  const k = mode.value === 'process-record-sample' ? 4 : subIndex.value
  if (k === 2) {
    const fields = [...PROCESS_FIELDS_COMMON]
    // 在「流程名」后插入「重要性」
    const idx = fields.findIndex((f) => f.key === 'process')
    fields.splice(idx + 1, 0, { key: 'materiality', label: '重要性', type: 'text' })
    return fields
  }
  return PROCESS_FIELDS_COMMON
})

// ─── item_id 构造（phase0 §6 命名规范） ──────────────────────────────────────

const procItemId = (field: string): string => {
  const k = mode.value === 'process-record-sample' ? 4 : subIndex.value
  return `${C1_ITEM_PREFIX}4-${k}-${field}`
}
const summaryItemId = (n: number, field: string): string => `${C1_ITEM_PREFIX}4-summary-${n}-${field}`
const sampleCellItemId = (rid: number, col: string): string => `${C1_ITEM_PREFIX}4-4-sample-${rid}-${col}`

// ─── 分组渲染辅助 ────────────────────────────────────────────────────────────

function groupedPrograms(slug: string): any[] {
  return programs.value.filter((p) => (p?.section ?? p?.phase) === slug)
}

const sectionApplicableId = (slug: string): string => `${C1_ITEM_PREFIX}${slug}-section-applicable`

/** 某段是否适用（整段裁剪，默认适用；Req 3.3 进度排除依据） */
function isSectionApplicable(slug: string): boolean {
  return c1data.isApplicable(sectionApplicableId(slug))
}

/** 某段裁剪理由（不适用时展示） */
function sectionReason(slug: string): string {
  return c1data.getRemark(sectionApplicableId(slug)) || ''
}

/**
 * 切换整段适用性（Req 3.1/3.4 即时保存）。
 * 标记「不适用」时弹框收集理由，未填理由拒绝保存（Req 3.2）。
 */
async function onToggleSectionApplicable(slug: string, applicable: boolean): Promise<void> {
  if (isReadonly.value) return
  if (applicable) {
    c1data.setApplicable(sectionApplicableId(slug), true)
    return
  }
  // 不适用 → 必须填理由
  try {
    const { value } = await ElMessageBox.prompt('请填写该段「不适用」的理由（必填）', '标记不适用', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      inputPlaceholder: '如：本项目非集团审计 / 无关联方交易',
      inputValidator: (v: string) => (v && v.trim() ? true : '不适用理由不能为空'),
    })
    const ok = c1data.setApplicable(sectionApplicableId(slug), false, value)
    if (!ok) {
      // 兜底：理由为空未保存，回滚为适用
      c1data.setApplicable(sectionApplicableId(slug), true)
    }
  } catch {
    // 用户取消 → 不改变（开关由 :model-value 绑定自动回弹）
  }
}

/**
 * 某段完成进度（Req 2.3 / 3.3）：
 * - 整段不适用 → 返回 100（已裁剪，不拖累进度）
 * - 否则以 checklist-responses 中「适用」步骤的已填占比估算（排除不适用步骤，Req 3.3）
 */
function sectionProgress(slug: string): number {
  // 单一来源：分组/适用性排除/进度分母逻辑统一在 useC1SectionEngine（Req 2.3/3.3）
  return sectionProgressPercent(
    [...c1data.responses.value.values()],
    slug,
    isSectionApplicable(slug),
  )
}

// ─── C1-4-4 样本明细（可编辑 + useC1SampleEngine 借贷勾稽） ────────────────────

interface SampleRow {
  __rid: number
  date: string
  account: string
  ref: string
  desc: string
  debit: string
  credit: string
}

const SAMPLE_COLS = ['date', 'account', 'ref', 'desc', 'debit', 'credit'] as const
const sampleRows = ref<SampleRow[]>([])
let sampleRidSeq = 0

/** 从已加载的 checklist-responses 重建样本行（按 rid 分组） */
function buildSampleRows(): void {
  const byRid = new Map<number, Partial<SampleRow>>()
  const re = /^C1-4-4-sample-(\d+)-(date|account|ref|desc|debit|credit)$/
  for (const [itemId, r] of c1data.responses.value.entries()) {
    const m = itemId.match(re)
    if (!m) continue
    const rid = Number(m[1])
    const col = m[2] as (typeof SAMPLE_COLS)[number]
    const cur = byRid.get(rid) ?? { __rid: rid }
    ;(cur as any)[col] = r.remark ?? ''
    byRid.set(rid, cur)
  }
  const rows = [...byRid.entries()]
    .sort((a, b) => a[0] - b[0])
    .map(([rid, v]) => ({
      __rid: rid,
      date: v.date ?? '',
      account: v.account ?? '',
      ref: v.ref ?? '',
      desc: v.desc ?? '',
      debit: v.debit ?? '',
      credit: v.credit ?? '',
    }))
  sampleRows.value = rows
  sampleRidSeq = rows.reduce((mx, r) => Math.max(mx, r.__rid), -1) + 1
}

/** 借贷勾稽（只读派生，useC1SampleEngine，Req 4.4 实时重算） */
const sampleBalance = computed(() => calcSampleBalance(toJeSamples(sampleRows.value)))

function toJeSamples(rows: SampleRow[]): JeSample[] {
  return rows.map((r) => ({
    date: r.date,
    account: r.account,
    ref: r.ref,
    desc: r.desc,
    debit: Number(r.debit) || 0,
    credit: Number(r.credit) || 0,
  }))
}

/** 累计借贷差（只读派生列，复用 useC1SampleEngine，不手工计算） */
function rowCumulativeDiff(i: number): number {
  const slice = toJeSamples(sampleRows.value.slice(0, i + 1))
  const b = calcSampleBalance(slice)
  return b.debitTotal - b.creditTotal
}

function addSampleRow(): void {
  if (isReadonly.value) return
  sampleRows.value.push({
    __rid: sampleRidSeq++,
    date: '',
    account: '',
    ref: '',
    desc: '',
    debit: '',
    credit: '',
  })
}

function removeSampleRow(i: number): void {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row) return
  // 清空该行所有已持久化单元（remark=空），再从本地移除
  for (const col of SAMPLE_COLS) {
    if (c1data.responses.value.has(sampleCellItemId(row.__rid, col))) {
      c1data.setFieldDebounced(sampleCellItemId(row.__rid, col), { remark: '' })
    }
  }
  sampleRows.value.splice(i, 1)
}

/** 样本单元编辑：本地即时更新（驱动实时重算），保存 debounce */
function onSampleCell(i: number, col: (typeof SAMPLE_COLS)[number], val: string): void {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row) return
  ;(row as any)[col] = val
  c1data.setFieldDebounced(sampleCellItemId(row.__rid, col), { remark: val })
}

// ─── 附件上传 + OCR + 非破坏性 merge（Task 7.2, Req 10.1~10.5） ────────────────

/** 样本行附件 item_id（phase0 §6.4：C1-4-4-sample-{row}-attach） */
const sampleAttachItemId = (rid: number): string => `${C1_ITEM_PREFIX}4-4-sample-${rid}-attach`
/** 过程记录表附件 item_id（C1-4-{k}-attach） */
const procAttachItemId = (): string => {
  const k = mode.value === 'process-record-sample' ? 4 : subIndex.value
  return `${C1_ITEM_PREFIX}4-${k}-attach`
}

/** 样本行附件名（已上传附件展示，只读模式仅查看） */
function sampleAttachName(rid: number): string {
  return c1data.getRemark(sampleAttachItemId(rid)) || ''
}

/** 列中文标签（merge 确认弹窗展示用） */
const SAMPLE_COL_LABELS: Record<string, string> = {
  date: '日期',
  account: '账户编码',
  ref: '引用',
  desc: '交易描述',
  debit: '借方金额',
  credit: '贷方金额',
}

/** 从 axios 响应解包 extracted_fields（兼容 {data:{data}} 信封） */
function unwrapOcrFields(res: any): Record<string, any> {
  const data = res?.data?.data ?? res?.data ?? {}
  return data.extracted_fields || {}
}

/**
 * 样本行 📎 上传：调用 OCR 端点识别 → 确认弹窗 → 非破坏性 merge 填入（Req 10.2/10.3/10.4）。
 * 附件名与 item_id 关联持久化（Req 10.5）。识别失败/无字段 → 提示手动填写，保留附件。
 */
async function onUploadSampleOcr(i: number, rawFile: File): Promise<void> {
  if (isReadonly.value) return
  const row = sampleRows.value[i]
  if (!row || !rawFile) return

  // 附件与 item_id 关联持久化（无论 OCR 成败都保留附件，Req 10.5）
  c1data.setFieldDebounced(sampleAttachItemId(row.__rid), { remark: rawFile.name })

  const formData = new FormData()
  formData.append('file', rawFile)
  let ocrFields: Record<string, any>
  try {
    // 铁律：复用 /d4/contract-ocr 端点；用 http(axios) 携带 Authorization（不能用原生 fetch）
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    // OCR 服务不可用/失败（Req 10.4）：提示手动填写，附件已保留
    ElMessage.warning('识别失败，请手动填写')
    return
  }

  const mapped = mapOcrToSampleCells(ocrFields)
  const existing: SampleCellMap = {
    date: row.date, account: row.account, ref: row.ref,
    desc: row.desc, debit: row.debit, credit: row.credit,
  }
  // 先算非破坏性 merge：仅可填充空字段（Property P8）
  const preview = mergeSampleRow(existing, mapped)
  if (preview.filledCols.length === 0) {
    // 无可填充字段（未识别或均已有值）→ 识别失败提示（Req 10.4）
    ElMessage.info(mapped && Object.keys(mapped).length
      ? 'OCR 识别字段均已有值，未覆盖既有内容'
      : '识别失败，请手动填写')
    return
  }

  // 确认弹窗供用户核对后 merge（Req 10.3）
  const previewMsg = preview.filledCols
    .map((c) => `${SAMPLE_COL_LABELS[c] || c}：${mapped[c]}`)
    .join('\n')
  const skippedMsg = preview.skippedCols.length
    ? `\n\n以下字段已有值，将保留不覆盖：${preview.skippedCols.map((c) => SAMPLE_COL_LABELS[c] || c).join('、')}`
    : ''
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下字段，确认填入？\n\n${previewMsg}${skippedMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return // 用户取消，不 merge
  }

  // 用户确认 → 仅写入 filledCols（非破坏性）
  for (const col of preview.filledCols) {
    onSampleCell(i, col as (typeof SAMPLE_COLS)[number], preview.merged[col])
  }
  ElMessage.success(`已填入 ${preview.filledCols.length} 个字段`)
}

/**
 * 过程记录表 📎 上传：OCR 识别 → 确认 → 非破坏性 merge 填入过程记录字段（Req 10.1~10.4）。
 * 附件名持久化到 C1-4-{k}-attach（Req 10.5）。
 */
async function onUploadProcOcr(rawFile: File): Promise<void> {
  if (isReadonly.value) return
  if (!rawFile) return

  c1data.setFieldDebounced(procAttachItemId(), { remark: rawFile.name })

  const formData = new FormData()
  formData.append('file', rawFile)
  let ocrFields: Record<string, any>
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/d4/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    ocrFields = unwrapOcrFields(res)
  } catch {
    ElMessage.warning('识别失败，请手动填写')
    return
  }

  // 过程记录字段：日期→执行日期，摘要→测试结果（非破坏性，仅填空字段）
  const mapped = mapOcrToSampleCells(ocrFields)
  const targets: Array<{ col: string; field: string; label: string }> = [
    { col: 'date', field: 'execDate', label: '执行日期' },
    { col: 'desc', field: 'testResult', label: '测试结果' },
  ]
  const fillable = targets.filter(
    (t) => mapped[t.col] && !((c1data.getRemark(procItemId(t.field)) || '').trim()),
  )
  if (fillable.length === 0) {
    ElMessage.info(Object.keys(mapped).length
      ? 'OCR 识别字段均已有值，未覆盖既有内容'
      : '识别失败，请手动填写')
    return
  }

  const previewMsg = fillable.map((t) => `${t.label}：${mapped[t.col]}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `OCR 识别到以下字段，确认填入？\n\n${previewMsg}`,
      'OCR 识别结果',
      { confirmButtonText: '确认填入', cancelButtonText: '取消', type: 'info' },
    )
  } catch {
    return
  }
  for (const t of fillable) {
    setTextDebounced(procItemId(t.field), mapped[t.col])
  }
  ElMessage.success(`已填入 ${fillable.length} 个字段`)
}

/** 过程记录表附件名（展示用） */
function procAttachName(): string {
  return c1data.getRemark(procAttachItemId()) || ''
}

// ─── 整体结论点选 + 自动建议 + EventBus 回写 B50（Task 7.3, Req 11.1/11.3/11.4） ──

/** 企业层面控制整体结论 item_id（phase0 §6.5） */
const OVERALL_ITEM_ID = `${C1_ITEM_PREFIX}overall-conclusion`
/** 各段结论 item_id（C1-{slug}-conclusion，phase0 §6.1） */
const sectionConclusionId = (slug: string): string => `${C1_ITEM_PREFIX}${slug}-conclusion`

/** 各段（仅适用段）结论值集合，用于自动建议整体结论 */
const sectionConclusions = computed<(string | null)[]>(() =>
  sectionGroups.value
    .filter((g) => isSectionApplicable(g.slug))
    .map((g) => getConclusion(sectionConclusionId(g.slug))),
)

/** 自动建议的整体结论（就低聚合各段结论；无有效输入时为 null） */
const suggestedOverall = computed<string | null>(() =>
  suggestOverallConclusion(sectionConclusions.value),
)

/** 当前整体结论（点选值） */
const overallConclusion = computed<string | null>(() => getConclusion(OVERALL_ITEM_ID))

/** 某段结论点选（P7 合法化 + 即时保存） */
function setSectionConclusion(slug: string, v: unknown): void {
  setPointSelect(sectionConclusionId(slug), CONCLUSION_OPTIONS, v)
}

/**
 * 设置整体结论（点选，用户可覆盖自动建议）。
 * P7：合法化到 CONCLUSION_OPTIONS ∪ null；
 * P9/Req 11.4：仅在新旧值实际不同时发布 EventBus 事件供 B50 订阅。
 */
function setOverallConclusion(v: unknown): void {
  if (isReadonly.value) return
  const oldVal = normalizeConclusion(getConclusion(OVERALL_ITEM_ID))
  const cleaned = sanitizeEnumValue(CONCLUSION_OPTIONS, v)
  setEnum(OVERALL_ITEM_ID, cleaned)
  publishConclusionIfChanged(oldVal, cleaned)
}

/** 应用自动建议为整体结论（点选优先，用户仍可再覆盖） */
function applySuggestedOverall(): void {
  if (isReadonly.value) return
  const s = suggestedOverall.value
  if (!s) {
    ElMessage.info('各段结论尚未填写，暂无可建议的整体结论')
    return
  }
  setOverallConclusion(s)
  ElMessage.success(`已应用建议结论：${s}`)
}

/**
 * 仅在结论实际变更时发布企业层面控制结论事件（Req 11.1/11.4，Property P9）。
 * 铁律：EventBus 只传结构化 payload。
 */
function publishConclusionIfChanged(oldVal: string | null | undefined, newVal: string | null | undefined): void {
  if (!shouldPublishConclusion(oldVal, newVal)) return
  eventBus.emit('c1:entity-control-conclusion', {
    projectId: props.projectId,
    wpId: props.wpId,
    wpCode: props.wpCode,
    conclusion: normalizeConclusion(newVal),
    previousConclusion: normalizeConclusion(oldVal),
  })
}

// ─── 识别缺陷 → 一键跳转 A14 缺陷评价并带入摘要（Task 7.3, Req 11.2） ─────────────

/** A14 缺陷评价底稿编码（GtIndexChip value） */
const A14_WP_CODE = 'A14'

interface DefectRow {
  __did: number
  summary: string
}

const defectRows = ref<DefectRow[]>([])
let defectDidSeq = 0

/** 缺陷摘要 item_id（phase0 §6.5：C1-defect-{d}-summary） */
const defectItemId = (did: number): string => `${C1_ITEM_PREFIX}defect-${did}-summary`

/** 从已加载 checklist-responses 重建缺陷行（按 did 排序） */
function buildDefectRows(): void {
  const re = /^C1-defect-(\d+)-summary$/
  const rows: DefectRow[] = []
  for (const [itemId, r] of c1data.responses.value.entries()) {
    const m = itemId.match(re)
    if (!m) continue
    rows.push({ __did: Number(m[1]), summary: r.remark ?? '' })
  }
  rows.sort((a, b) => a.__did - b.__did)
  defectRows.value = rows
  defectDidSeq = rows.reduce((mx, r) => Math.max(mx, r.__did), -1) + 1
}

function addDefectRow(): void {
  if (isReadonly.value) return
  defectRows.value.push({ __did: defectDidSeq++, summary: '' })
}

function removeDefectRow(i: number): void {
  if (isReadonly.value) return
  const row = defectRows.value[i]
  if (!row) return
  if (c1data.responses.value.has(defectItemId(row.__did))) {
    c1data.setFieldDebounced(defectItemId(row.__did), { remark: '' })
  }
  defectRows.value.splice(i, 1)
}

/** 缺陷摘要编辑（本地即时 + debounce 保存） */
function onDefectSummary(i: number, val: string): void {
  if (isReadonly.value) return
  const row = defectRows.value[i]
  if (!row) return
  row.summary = val
  c1data.setFieldDebounced(defectItemId(row.__did), { remark: val })
}

/**
 * 缺陷 chip 跳转 A14 时同时发布缺陷事件，供 A14 缺陷评价预填缺陷摘要（Req 11.2）。
 * GtIndexChip 自身完成路由跳转，本处仅补发结构化摘要 payload。
 */
function onDefectJumpToA14(i: number): void {
  const row = defectRows.value[i]
  if (!row) return
  eventBus.emit('c1:defect-identified', {
    projectId: props.projectId,
    wpId: props.wpId,
    wpCode: props.wpCode,
    defectSummary: (row.summary || '').trim(),
    itemId: defectItemId(row.__did),
  })
}

// ─── selfLoad：render-config 获取 section_groups（bundle 内嵌 htmlData 为 null） ──

async function selfLoad(): Promise<void> {
  const applyGroups = (data: any) => {
    const groups = data?.section_groups
    if (Array.isArray(groups) && groups.length) {
      sectionGroups.value = groups.map((g: any, i: number) => ({
        slug: String(g.slug ?? ''),
        order: Number(g.order ?? i + 1),
        title: String(g.title ?? ''),
        defaultApplicable: g.defaultApplicable ?? g.default_applicable ?? true,
        note: g.note,
      }))
      activeSections.value = sectionGroups.value.map((g) => g.slug)
    }
  }

  if (props.htmlData) {
    applyGroups(props.htmlData)
  } else if (props.wpId) {
    try {
      const res = await api.get<any>(
        `/api/workpapers/${props.wpId}/render-config?force_component_type=c1-entity-level-control`,
        { _silent: true } as any,
      )
      const data = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
      applyGroups(data)
    } catch (e) {
      console.warn('[GtC1EntityControl] selfLoad render-config 失败，使用九段常量兜底:', e)
    }
  }
}

/** 程序步骤 selfLoad（force a-program-console + 程序表 sheet 名），用于九段分组 */
async function loadPrograms(): Promise<void> {
  if (!props.wpId) return
  try {
    const res = await api.get<any>(
      `/api/workpapers/${props.wpId}/render-config?force_component_type=a-program-console`,
      { _silent: true } as any,
    )
    const data = res?.sheets?.[0]?.html_data ?? res?.htmlData ?? res
    const list = data?.programs
    if (Array.isArray(list)) programs.value = list
  } catch (e) {
    console.warn('[GtC1EntityControl] loadPrograms 失败，交由 GtAProgramConsole selfLoad:', e)
  }
}

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(async () => {
  isLoading.value = true
  try {
    await Promise.all([selfLoad(), c1data.loadAll(), loadPrograms(), checkAiHealth()])
    buildSampleRows()
    buildDefectRows()
  } finally {
    isLoading.value = false
  }
})

// ─── 内联子组件：过程记录字段表（避免额外文件，同一 sheet 内聚） ───────────────

const ProcessRecordFields = defineComponent({
  name: 'C1ProcessRecordFields',
  props: {
    subIndex: { type: Number, required: true },
    fields: { type: Array as PropType<ProcField[]>, required: true },
    readonly: { type: Boolean, default: false },
    getEnum: { type: Function as PropType<(id: string) => string | null>, required: true },
    getText: { type: Function as PropType<(id: string) => string | null>, required: true },
    freqOptions: { type: Array as PropType<string[]>, required: true },
    methodOptions: { type: Array as PropType<string[]>, required: true },
    procItemId: { type: Function as PropType<(field: string) => string>, required: true },
  },
  emits: ['set-enum', 'set-text'],
  setup(p, { emit }) {
    return () =>
      h('div', { class: 'c1-proc-fields' }, [
        h(
          'table',
          { class: 'c1-grid-table c1-proc-table' },
          [
            h('tbody', {}, p.fields.map((f) => {
              const id = p.procItemId(f.key)
              let control
              if (f.type === 'method') {
                // 测试方法多选点选（Req 9.1）：checkbox 组，值以逗号连接存 conclusion
                const selected = new Set(
                  (p.getEnum(id) ?? '')
                    .split(',')
                    .map((s: string) => s.trim())
                    .filter(Boolean),
                )
                control = h(
                  'div',
                  { class: 'c1-check-group' },
                  p.methodOptions.map((o) =>
                    h(
                      'label',
                      { key: o, class: ['c1-check-item', { 'is-checked': selected.has(o) }] },
                      [
                        h('input', {
                          type: 'checkbox',
                          disabled: p.readonly,
                          checked: selected.has(o),
                          onChange: (e: any) => {
                            const next = new Set(selected)
                            if (e.target.checked) next.add(o)
                            else next.delete(o)
                            emit('set-enum', id, next.size ? [...next].join(',') : null)
                          },
                        }),
                        h('span', {}, o),
                      ],
                    ),
                  ),
                )
              } else if (f.type === 'freq') {
                control = h(
                  'select' as any,
                  {
                    class: 'c1-native-select',
                    disabled: p.readonly,
                    value: p.getEnum(id) ?? '',
                    onChange: (e: any) => emit('set-enum', id, e.target.value || null),
                  },
                  [
                    h('option', { value: '' }, '请选择'),
                    ...p.freqOptions.map((o) => h('option', { value: o }, o)),
                  ],
                )
              } else {
                control = h('textarea' as any, {
                  class: 'c1-native-textarea',
                  disabled: p.readonly,
                  rows: 1,
                  value: p.getText(id) ?? '',
                  placeholder: f.label,
                  onInput: (e: any) => emit('set-text', id, e.target.value),
                })
              }
              return h('tr', { key: f.key }, [
                h('td', { class: 'c1-proc-label' }, f.label),
                h('td', { class: 'c1-proc-value' }, [control]),
              ])
            })),
          ],
        ),
      ])
  },
})

// ─── 暴露（供集成/单元测试与父级调用） ────────────────────────────────────────

defineExpose({
  mode,
  subIndex,
  processFields,
  splitRefs,
  aiEnabled,
  GUIDE_STEPS,
  methodologyOf,
  getMultiEnum,
  setMultiEnum,
  TEST_METHOD_OPTIONS,
  sectionGroups,
  sectionProgress,
  isSectionApplicable,
  sectionReason,
  onToggleSectionApplicable,
  procItemId,
  summaryItemId,
  sampleCellItemId,
  sampleRows,
  sampleBalance,
  rowCumulativeDiff,
  addSampleRow,
  removeSampleRow,
  onSampleCell,
  buildSampleRows,
  // Task 7.3：整体结论 + 缺陷联动
  setPointSelect,
  CONCLUSION_OPTIONS,
  OVERALL_ITEM_ID,
  sectionConclusionId,
  sectionConclusions,
  suggestedOverall,
  overallConclusion,
  setSectionConclusion,
  setOverallConclusion,
  applySuggestedOverall,
  A14_WP_CODE,
  defectRows,
  defectItemId,
  buildDefectRows,
  addDefectRow,
  removeDefectRow,
  onDefectSummary,
  onDefectJumpToA14,
})
</script>

<style scoped>
.c1-entity-control {
  padding: 12px;
  font-size: 13px;
}

.c1-loading {
  padding: 24px;
}

/* 顶部操作引导区（蓝色渐变 2 列 grid，Req 9.3） */
.c1-guide {
  margin-bottom: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  background: linear-gradient(135deg, #e6f0ff 0%, #d6e4ff 100%);
  border: 1px solid #b9d2ff;
}

.c1-guide-head {
  display: flex;
  align-items: center;
  gap: 6px;
  font-weight: 600;
  font-size: 13px;
  color: #1d4ed8;
  margin-bottom: 10px;
}

.c1-guide-head-icon {
  color: #2563eb;
}

.c1-guide-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px 20px;
}

.c1-guide-step {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.c1-guide-no {
  flex: 0 0 22px;
  width: 22px;
  height: 22px;
  line-height: 22px;
  text-align: center;
  border-radius: 50%;
  background: #2563eb;
  color: #fff;
  font-size: 12px;
  font-weight: 600;
}

.c1-guide-txt {
  flex: 1 1 auto;
  min-width: 0;
}

.c1-guide-title {
  font-weight: 600;
  font-size: 13px;
  color: #1e293b;
}

.c1-guide-desc {
  font-size: 12px;
  color: #475569;
  line-height: 1.4;
}

/* 方法论上下文（琥珀色左边线区块，Req 9.4） */
.c1-methodology {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin: 4px 0 10px;
  padding: 8px 12px;
  background: #fffbeb;
  border-left: 3px solid #d97706;
  border-radius: 0 4px 4px 0;
  font-size: 12px;
  color: #92400e;
  line-height: 1.5;
}

.c1-meth-icon {
  flex: 0 0 auto;
  margin-top: 2px;
  color: #d97706;
}

.c1-meth-text {
  flex: 1 1 auto;
}

/* 九段分组导航 */
.c1-section-nav {
  margin-bottom: 12px;
}

.c1-sec-head {
  display: flex;
  align-items: center;
  gap: 12px;
  width: 100%;
}

.c1-sec-title {
  font-weight: 600;
  font-size: 13px;
}

.c1-sec-applicable {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  margin-left: 8px;
}

.c1-applicable-label {
  color: #909399;
  font-size: 12px;
}

.c1-sec-progress {
  margin-left: auto;
}

.c1-sec-body {
  padding: 4px 0;
}

.c1-sec-hint {
  margin: 0;
  color: #909399;
  font-size: 12px;
}

.c1-sec-trimmed {
  padding: 4px 0;
}

.c1-trim-reason {
  margin-top: 4px;
  color: #606266;
  font-size: 12px;
}

.c1-program-console {
  margin-top: 8px;
}

.c1-example :deep(.el-alert),
.c1-fr-summary :deep(.el-alert) {
  margin-bottom: 8px;
}

.c1-card {
  margin-top: 8px;
}

.c1-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.c1-card-title {
  font-weight: 600;
  font-size: 13px;
}

/* section 标题行右侧 AI 辅助按钮（UI 铁律：不只底部有） */
.c1-card-actions {
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

/* 📎 附件已上传标记（过程记录卡头 / 样本行；只读仅查看不可删除，Req 10.5） */
.c1-attach-flag {
  color: #4b2d77;
  font-size: 15px;
  vertical-align: middle;
}

.c1-attach-upload {
  display: inline-block;
}

.c1-attach-empty {
  font-size: 12px;
  color: #c0c4cc;
}

.c1-ai-btn .el-icon {
  margin-right: 2px;
}

/* 关联底稿索引行（GtIndexChip 渲染 + 可编辑输入） */
.c1-ref-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #ebeef5;
  font-size: 13px;
}

.c1-ref-label {
  flex: 0 0 96px;
  color: #606266;
  font-weight: 500;
  padding-top: 4px;
}

.c1-ref-body {
  flex: 1 1 auto;
  min-width: 0;
}

.c1-ref-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
  align-items: center;
}

.c1-ref-empty {
  color: #c0c4cc;
}

/* 通用网格表格（13px 铁律） */
.c1-grid-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.c1-grid-table th,
.c1-grid-table td {
  border: 1px solid #ebeef5;
  padding: 4px 8px;
  text-align: left;
  vertical-align: middle;
}

.c1-grid-table th {
  background: #f5f7fa;
  font-weight: 600;
  color: #303133;
}

.c1-cell-idx {
  text-align: center;
  color: #909399;
}

.c1-cell-name {
  font-weight: 500;
}

.c1-empty-row {
  text-align: center;
  color: #909399;
  padding: 12px;
}

/* 过程记录字段表（标签 | 值 两列） */
.c1-proc-table {
  margin-top: 8px;
}

.c1-proc-label {
  width: 140px;
  background: #fafafa;
  color: #606266;
  font-weight: 500;
}

.c1-proc-value {
  padding: 2px 6px;
}

.c1-native-textarea,
.c1-native-select {
  width: 100%;
  font-size: 13px;
  border: 1px solid #dcdfe6;
  border-radius: 4px;
  padding: 4px 8px;
  box-sizing: border-box;
  resize: vertical;
  font-family: inherit;
}

.c1-native-textarea:disabled,
.c1-native-select:disabled {
  background: #f5f7fa;
  color: #909399;
  cursor: not-allowed;
}

/* 只读派生/公式列（虚线下划线 + help 光标 + tooltip，UI 铁律） */
.c1-formula-head,
.c1-formula-val {
  border-bottom: 1px dashed #b88230;
  cursor: help;
  color: #b88230;
}

/* 判断列表头（虚线下划线 + help 光标 + tooltip 说明来源与判断依据，Req 9.5） */
.c1-judge-head {
  border-bottom: 1px dashed #909399;
  cursor: help;
}

/* 测试方法多选点选（fr-summary el-checkbox-group 紧凑排布） */
.c1-method-group {
  display: flex;
  flex-wrap: wrap;
  gap: 2px 10px;
}

/* 过程记录测试方法多选（原生 checkbox 点选，tag 样式） */
.c1-check-group {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.c1-check-item {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 8px;
  border: 1px solid #dcdfe6;
  border-radius: 12px;
  font-size: 12px;
  cursor: pointer;
  user-select: none;
}

.c1-check-item.is-checked {
  border-color: #4b2d77;
  background: #f3eefb;
  color: #4b2d77;
}

.c1-check-item input:disabled {
  cursor: not-allowed;
}

.c1-formula-cell {
  text-align: right;
  font-variant-numeric: tabular-nums;
}

.c1-sample-foot td {
  background: #fdf6ec;
  font-weight: 600;
}

.is-readonly .c1-native-textarea,
.is-readonly .c1-native-select {
  background: #f5f7fa;
  cursor: not-allowed;
}

/* 整体结论 + 缺陷联动（Task 7.3） */
.c1-conclusion-card,
.c1-defect-card {
  margin-top: 12px;
}

.c1-conclusion-table {
  margin-bottom: 12px;
}

.c1-overall-row {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
  padding: 10px 12px;
  background: #f3eefb;
  border-radius: 6px;
}

.c1-overall-label {
  font-weight: 600;
  font-size: 13px;
  color: #4b2d77;
}

.c1-overall-select {
  min-width: 160px;
}

.c1-suggest-tag {
  margin-left: 2px;
}

.c1-defect-jump {
  text-align: center;
}
</style>
