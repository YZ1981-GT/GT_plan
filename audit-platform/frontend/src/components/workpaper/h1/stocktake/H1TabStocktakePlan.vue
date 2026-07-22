<template>
  <div class="h1-tab-stocktake-plan">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按「风险评估→了解状况/内控/以前年度→胜任能力→计划安排」制定固定资产监盘计划，明确范围、方法与双向抽查，支撑 H1-10 执行与 H1-11 小结。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H1-9" :context-project-id="projectId" />
        <el-tag size="small" type="info">类别 {{ form.categoryScopes.length }}</el-tag>
        <el-tag size="small" :type="totals.coverageRate >= (riskSug.minCoverageRate || 30) ? 'success' : 'warning'">
          计划覆盖 {{ totals.coverageRate }}%
          <template v-if="form.existenceRiskLevel">（建议≥{{ riskSug.minCoverageRate }}%）</template>
        </el-tag>
        <el-tag v-if="form.existenceRiskLevel" size="small" :type="riskTagType">
          存在性风险 {{ form.existenceRiskLevel }}
        </el-tag>
        <el-tag size="small" :type="planReady ? 'success' : 'danger'">
          {{ planReady ? '可进 H1-10' : `缺 ${gateBlockers.length} 项` }}
        </el-tag>
      </div>
      <div class="toolbar-right">
        <el-button v-if="!isReadonly" size="small" @click="handleImportH12">从 H1-2 带入</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleImportH4">从 H1-4 闲置</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handleApplyRisk" :disabled="!form.existenceRiskLevel">按风险建议样本量</el-button>
        <el-button v-if="!isReadonly" size="small" @click="handlePriorYear">带入上年</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleDraftSample">按类别回填抽查数量</el-button>
        <el-button size="small" @click="mapDialog = true">字段映射</el-button>
        <el-button size="small" :loading="exporting" @click="handleExportWord">导出 Word</el-button>
        <el-button size="small" type="primary" @click="goCheckWithGate">进入 H1-10 →</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H1-11')">H1-11 小结 →</el-button>
        <el-button size="small" type="default" link @click="handleReview('H1-9')">💬 复核</el-button>
      </div>
    </div>

    <el-alert
      v-for="(w, i) in state.planLogicWarnings.value"
      :key="i"
      type="warning"
      :closable="false"
      :title="w"
      class="logic-warn"
      show-icon
    />

    <nav class="sec-nav" aria-label="监盘计划分区">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <div class="attach-bar">
      <span class="attach-label">监盘计划附件</span>
      <ItemAttachment
        v-if="projectId && wpId"
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="H1-9"
        :item-index="0"
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx"
      />
    </div>

    <!-- 一、风险评估 -->
    <el-card id="sec-risk" shadow="never" class="block-card">
      <template #header><span>一、固定资产存在性认定重大错报风险</span></template>
      <el-form label-width="120px" size="small">
        <el-form-item label="风险程度">
          <el-radio-group v-model="form.existenceRiskLevel" :disabled="isReadonly" @change="onRiskChange">
            <el-radio value="低">低</el-radio>
            <el-radio value="中">中</el-radio>
            <el-radio value="高">高</el-radio>
          </el-radio-group>
          <el-tag v-if="form.existenceRiskLevel" type="info" size="small" class="ml-8">{{ riskSug.label }}</el-tag>
        </el-form-item>
        <el-form-item label="评估说明">
          <el-input
            v-model="form.existenceRiskNote"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="结合固有风险、控制风险、以前年度发现等说明风险程度依据…"
            @change="persist"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 二、了解 -->
    <el-card id="sec-understand" shadow="never" class="block-card">
      <template #header><span>二、了解固定资产期末状况与管理规定</span></template>

      <h4 class="sub-h">（一）固定资产的期末状况</h4>
      <el-form-item label="闲置资产" label-width="100px">
        <div class="field-with-ocr">
          <el-input
            v-model="form.idleAssetsNote"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="描述期末闲置固定资产情况及对应金额…"
            @change="persist"
          />
          <el-button v-if="!isReadonly" size="small" @click="handleImportH4">从 H1-4 回填</el-button>
        </div>
      </el-form-item>
      <div class="section-title mb-8">
        <span class="hint" style="margin:0">存放地点</span>
        <el-button v-if="!isReadonly" size="small" type="primary" @click="openLocDialog()">+ 新增</el-button>
      </div>
      <el-table :data="form.locations" border stripe size="small">
        <el-table-column type="index" label="序" width="44" />
        <el-table-column prop="category" label="类别" min-width="100" />
        <el-table-column prop="warehouse" label="仓库（或场所）" min-width="120" />
        <el-table-column prop="place" label="地点" min-width="120" />
        <el-table-column prop="note" label="说明" min-width="120" />
        <el-table-column v-if="!isReadonly" width="100">
          <template #default="{ row }">
            <el-button size="small" link @click="openLocDialog(row)">编辑</el-button>
            <el-button size="small" link type="danger" @click="state.removePlanLocation(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <p class="hint">提示：存放地点将回填至 H1-11「主要资产存放情况」。</p>

      <h4 class="sub-h">（二）企业定期盘点内部控制制度与执行情况</h4>
      <div class="section-title mb-8">
        <span class="hint" style="margin:0">可 OCR 企业盘点计划/通知</span>
        <el-button v-if="!isReadonly" size="small" :loading="ocrLoading" @click="runClientPlanOcr">📎 OCR 企业盘点计划</el-button>
      </div>
      <el-form label-width="140px" size="small">
        <el-form-item label="制度名称/索引">
          <el-input v-model="form.icSystemName" :disabled="isReadonly" placeholder="制度名称" style="width:40%;margin-right:8px" @change="persist" />
          <el-input v-model="form.icSystemIndex" :disabled="isReadonly" placeholder="索引号" style="width:30%" @change="persist" />
        </el-form-item>
        <el-form-item label="盘点时间/频次">
          <el-input v-model="form.icFrequency" :disabled="isReadonly" placeholder="如：每年末一次 / 每半年" @change="persist" />
        </el-form-item>
        <el-form-item label="负责部门/人员">
          <el-input v-model="form.icResponsible" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <p class="hint">提示：如制度规定与实际执行不一致，应按制度规定与实际负责部门分别填写。</p>
        <el-divider content-position="left">企业实际盘点情况</el-divider>
        <el-form-item label="盘点计划安排">
          <el-input v-model="form.clientPlanArrange" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="会议信息">
          <el-input v-model="form.clientMeetingNote" :disabled="isReadonly" placeholder="会议时间、参会人员…" @change="persist" />
        </el-form-item>
        <el-form-item label="预计人数">
          <el-input v-model="form.clientHeadcountEstimate" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="对盘点计划评价">
          <el-input
            v-model="form.clientPlanEvaluation"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="评价企业盘点计划是否适当、能否发现错报…"
            @change="persist"
          />
        </el-form-item>
      </el-form>

      <h4 class="sub-h">（三）查阅以前年度工作底稿</h4>
      <div class="section-title mb-8">
        <span class="hint" style="margin:0">可从上年同底稿自动带入</span>
        <el-button v-if="!isReadonly" size="small" :loading="priorLoading" @click="handlePriorYear">带入上年计划要点</el-button>
      </div>
      <el-form label-width="140px" size="small">
        <el-form-item label="上年监盘日期/人员">
          <el-input v-model="form.priorYearDate" :disabled="isReadonly" placeholder="日期" style="width:40%;margin-right:8px" @change="persist" />
          <el-input v-model="form.priorYearStaff" :disabled="isReadonly" placeholder="人员" style="width:40%" @change="persist" />
        </el-form-item>
        <el-form-item label="抽样范围/比例">
          <el-input v-model="form.priorYearScope" :disabled="isReadonly" placeholder="范围" style="width:40%;margin-right:8px" @change="persist" />
          <el-input v-model="form.priorYearSampleRate" :disabled="isReadonly" placeholder="比例" style="width:40%" @change="persist" />
        </el-form-item>
        <el-form-item label="发现问题与不足">
          <el-input
            v-model="form.priorYearIssues"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="上年监盘发现的问题；若本所未承接上年审计，记录与前任沟通情况…"
            @change="persist"
          />
        </el-form-item>
      </el-form>
      <p class="hint">提示：同一事务所承接时查阅上年底稿；新承接项目应与前任注册会计师沟通。</p>
    </el-card>

    <!-- 三、胜任能力 -->
    <el-card id="sec-competence" shadow="never" class="block-card">
      <template #header><span>三、评估审计人员的专业胜任能力</span></template>
      <el-input
        v-model="form.competenceNote"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="评估团队是否具备监盘所需技能；对特殊类型固定资产（如大型专用设备、需专家协助等）尤需说明…"
        @change="persist"
      />
      <p class="hint">提示：应针对特殊类型资产评估胜任能力，必要时利用专家工作。</p>
    </el-card>

    <!-- 四、盘点计划安排 -->
    <el-card id="sec-arrange" shadow="never" class="block-card">
      <template #header><span>四、盘点计划安排</span></template>

      <h4 class="sub-h">（一）预计监盘时间</h4>
      <el-form inline size="small">
        <el-form-item label="预计日期">
          <el-date-picker
            v-model="form.plannedDate"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="时段说明">
          <el-input
            v-model="form.plannedTimeNote"
            :disabled="isReadonly"
            placeholder="如：9:00集合→17:00结束"
            style="width:280px"
            @change="persist"
          />
        </el-form-item>
      </el-form>

      <h4 class="sub-h">（二）预计安排监盘人员</h4>
      <el-form label-width="120px" size="small">
        <el-form-item label="预计人数">
          <el-input-number v-model="form.plannedHeadcount" :min="0" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="程序负责人">
          <el-input v-model="form.plannedLead" :disabled="isReadonly" placeholder="监盘程序负责人" @change="persist" />
        </el-form-item>
      </el-form>

      <h4 class="sub-h">（三）预计监盘的固定资产范围</h4>
      <div class="section-title mb-8">
        <span>1. 类别范围</span>
        <div>
          <el-button v-if="!isReadonly" size="small" @click="handleImportH12">从 H1-2 带入余额</el-button>
          <el-button v-if="!isReadonly" size="small" type="primary" @click="state.addSampleRow()">+ 新增类别</el-button>
        </div>
      </div>
      <el-table :data="form.categoryScopes" border stripe size="small" show-summary :summary-method="scopeSummary">
        <el-table-column type="index" width="40" />
        <el-table-column label="类别" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.category" size="small" @change="onScopeChange(row)" />
            <span v-else>{{ row.category }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.endingBalance"
              size="small"
              :controls="false"
              @change="onScopeChange(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.endingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="减值准备" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.impairment"
              size="small"
              :controls="false"
              @change="onScopeChange(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.impairment) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账面净值" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell formula-cell">{{ fmtAmt(row.netBookValue) }}</span></template>
        </el-table-column>
        <el-table-column label="单位" width="70">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.unit" size="small" @change="onScopeChange(row)" />
            <span v-else>{{ row.unit }}</span>
          </template>
        </el-table-column>
        <el-table-column label="数量" width="80" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.quantity"
              size="small"
              :controls="false"
              :min="0"
              @change="onScopeChange(row)"
            />
            <span v-else>{{ row.quantity }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划监盘数量" width="100" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.planQty"
              size="small"
              :controls="false"
              :min="0"
              @change="onScopeChange(row)"
            />
            <span v-else>{{ row.planQty }}</span>
          </template>
        </el-table-column>
        <el-table-column label="计划监盘金额" width="110" align="right">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.planAmount"
              size="small"
              :controls="false"
              :min="0"
              @change="onScopeChange(row)"
            />
            <span v-else class="amount-cell">{{ fmtAmt(row.planAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="监盘比例%" width="90" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.coverageRate }}%</span></template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="56">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="state.removeSampleRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <el-form-item label="2. 地点范围" label-width="100px" class="mt-12">
        <el-input
          v-model="form.locationScopeNote"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :disabled="isReadonly"
          placeholder="拟监盘的存放地点范围说明…"
          @change="persist"
        />
      </el-form-item>

      <h4 class="sub-h">（四）拟实施的盘点方法</h4>
      <el-form label-width="100px" size="small">
        <el-form-item label="方法">
          <el-select v-model="form.method" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="全面盘点" value="全面盘点" />
            <el-option label="抽样盘点" value="抽样盘点" />
          </el-select>
        </el-form-item>
        <el-form-item label="方法说明">
          <el-input
            v-model="form.methodDetail"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="说明观察、抽盘、截止测试等具体安排…"
            @change="persist"
          />
        </el-form-item>
      </el-form>

      <h4 class="sub-h">（五）就监盘计划与管理层沟通</h4>
      <el-form label-width="100px" size="small">
        <el-form-item label="沟通时间">
          <el-input v-model="form.mgmtCommTime" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="管理层人员">
          <el-input v-model="form.mgmtCommNames" :disabled="isReadonly" @change="persist" />
        </el-form-item>
        <el-form-item label="审计人员">
          <el-input v-model="form.mgmtCommAuditors" :disabled="isReadonly" @change="persist" />
        </el-form-item>
      </el-form>

      <h4 class="sub-h">（六）特殊要求</h4>
      <el-input
        v-model="form.specialRequirements"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="根据被审计单位情况向管理层提出的特殊要求（停产配合、专家到场、第三方存放等）…"
        @change="persist"
      />

      <h4 class="sub-h">（七）预计监盘中抽取样本的方法与数量</h4>
      <el-form label-width="160px" size="small">
        <el-form-item label="1. 账面→实物">
          <el-input
            v-model="form.sampleBookToFloorMethod"
            :disabled="isReadonly"
            style="width:55%;margin-right:8px"
            @change="persist"
          />
          <span class="muted">预计数量</span>
          <el-input-number
            v-model="form.sampleBookToFloorQty"
            :min="0"
            :disabled="isReadonly"
            class="ml-8"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="2. 实物→账面">
          <el-input
            v-model="form.sampleFloorToBookMethod"
            :disabled="isReadonly"
            style="width:55%;margin-right:8px"
            @change="persist"
          />
          <span class="muted">预计数量</span>
          <el-input-number
            v-model="form.sampleFloorToBookQty"
            :min="0"
            :disabled="isReadonly"
            class="ml-8"
            @change="persist"
          />
        </el-form-item>
      </el-form>
      <p class="hint">提示：双向抽查分别对应存在性与完整性；执行结果记入 H1-10，结论汇总至 H1-11。</p>

      <h4 class="sub-h">（八）推算方法</h4>
      <el-form label-width="160px" size="small">
        <el-form-item label="1. 推断方法说明">
          <el-input
            v-model="form.rollForwardMethod"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            placeholder="监盘日非资产负债表日时，如何将盘点结果推算至报表日…"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="2. 预计复盘比例(%)">
          <el-input-number
            v-model="form.plannedRecountRatio"
            :min="0"
            :max="100"
            :precision="1"
            :disabled="isReadonly"
            @change="persist"
          />
          <el-tag v-if="!ratioOk" type="danger" size="small" class="ml-8">须为 0~100（已拦截异常大百分比）</el-tag>
        </el-form-item>
      </el-form>
      <p class="hint">提示：原 Excel 模板「23500%」属异常占位/公式错误，本底稿强制合理区间。</p>
    </el-card>

    <!-- 五、结论 -->
    <el-card id="sec-conclusion" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>五、监盘计划结论</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="handleLocalDraft">规则草稿</el-button>
            <el-button v-if="!isReadonly" size="small" type="primary" plain :loading="aiLoading" @click="handleAiDraft">AI 润色</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="form.planConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="概括风险应对、监盘范围与覆盖安排、人员分工是否适当，是否可进入 H1-10 执行…"
        @change="persist"
      />
      <div class="sign-area">
        <div class="sign-row">
          <span>编制人：</span>
          <el-input v-if="!isReadonly" v-model="form.preparedBy" size="small" style="width:120px" @change="persist" />
          <span v-else>{{ form.preparedBy || '________' }}</span>
          <span class="ml-16">日期：</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="form.preparedDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            @change="persist"
          />
          <span v-else>{{ form.preparedDate || '____年__月__日' }}</span>
        </div>
        <div class="sign-row mt-8">
          <span>复核人：</span>
          <el-input v-if="!isReadonly" v-model="form.reviewedBy" size="small" style="width:120px" @change="persist" />
          <span v-else>{{ form.reviewedBy || '________' }}</span>
          <span class="ml-16">日期：</span>
          <el-date-picker
            v-if="!isReadonly"
            v-model="form.reviewedDate"
            type="date"
            value-format="YYYY-MM-DD"
            size="small"
            @change="persist"
          />
          <span v-else>{{ form.reviewedDate || '____年__月__日' }}</span>
        </div>
      </div>
    </el-card>

    <details class="compile-hint">
      <summary>编制提示（对照 H1-11）</summary>
      <ul>
        <li>编制逻辑：风险定调 → 了解现状与内控 → 复盘以前年度 → 评估胜任能力 → 敲定时间/人员/范围/方法/双向抽查/推算。</li>
        <li>优先「从 H1-2 带入」类别余额，再「按风险建议样本量」；闲置说明可从 H1-4 回填。</li>
        <li>进入 H1-10 前会检查风险/时间/负责人/覆盖率；可强制进入但会列明缺项。</li>
        <li>企业盘点计划支持 OCR；结论支持规则草稿与 AI 润色；可导出 Word 底稿。</li>
        <li>「字段映射」查看计划字段如何回填至 H1-11；执行侧低于计划样本量时 H1-10/11 告警。</li>
        <li>完成计划后进入 H1-10 执行双向抽盘，再在 H1-11 形成结论。</li>
      </ul>
    </details>

    <el-dialog v-model="locDialog.visible" title="编辑存放地点" width="520px" destroy-on-close>
      <el-form label-width="110px" size="small">
        <el-form-item label="类别"><el-input v-model="locDialog.draft.category" /></el-form-item>
        <el-form-item label="仓库（或场所）"><el-input v-model="locDialog.draft.warehouse" /></el-form-item>
        <el-form-item label="地点"><el-input v-model="locDialog.draft.place" /></el-form-item>
        <el-form-item label="说明"><el-input v-model="locDialog.draft.note" type="textarea" :autosize="{ minRows: 2 }" /></el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="locDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="saveLocDialog">确认回写</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="mapDialog" title="H1-9 → H1-11 字段映射" width="640px">
      <p class="hint">小结页「从 H1-9/10 回填」时，下列计划字段会写入对应分区（仅填空不覆盖）。</p>
      <el-table :data="fieldMap" border size="small">
        <el-table-column prop="planLabel" label="计划字段" min-width="140" />
        <el-table-column prop="summarySection" label="小结分区" min-width="160" />
        <el-table-column prop="summaryField" label="小结字段" width="160" />
      </el-table>
      <template #footer>
        <el-button type="primary" @click="mapDialog = false">关闭</el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="ocrDialog.visible" title="OCR 识别结果确认" width="560px" destroy-on-close>
      <el-alert type="info" :closable="false" title="请核对后确认回写，可直接修改。" class="mb-8" />
      <el-form label-width="140px" size="small">
        <el-form-item v-for="(val, key) in ocrDialog.editable" :key="key" :label="String(key)">
          <el-input
            v-if="typeof val === 'string' && val.length > 60"
            v-model="ocrDialog.editable[key]"
            type="textarea"
            :autosize="{ minRows: 2 }"
          />
          <el-input v-else v-model="ocrDialog.editable[key]" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="ocrDialog.visible = false">取消</el-button>
        <el-button type="primary" @click="confirmOcrWriteback">确认回写</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
/**
 * H1TabStocktakePlan — H1-9 固定资产监盘计划
 * 对齐致同模板；H1-2/H1-4 带入、风险建议、门禁、OCR、上年、Word 导出、字段映射
 */
import { computed, inject, reactive, ref, toRef } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'
import { useH1Stocktake } from '../../composables/useH1Stocktake'
import { useStickySectionNav } from '../../composables/useStickySectionNav'
import {
  isPlannedRecountRatioValid,
  newPlanLocationRow,
  type PlanCategoryScopeRow,
  type PlanLocationRow,
} from '../../composables/h1StocktakePlanModel'
import {
  PLAN_TO_SUMMARY_FIELD_MAP,
  draftPlanConclusion,
} from '../../composables/h1StocktakePlanEnhance'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{ (e: 'navigate-sheet', sheetName: string): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const allResponsesRef = computed(() => props.allResponses)
const state = useH1Stocktake(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  { onSave: (itemId, value) => saveResponse(itemId, value) },
)

const form = computed(() => state.planForm.value)
const totals = computed(() => state.planScopeTotals.value)
const riskSug = computed(() => state.riskSuggestion.value)
const gateBlockers = computed(() => state.planGateBlockers.value)
const planReady = computed(() => state.planReadyForCheck.value)
const isReadonly = computed(() => props.isReadonly)
const ratioOk = computed(() => isPlannedRecountRatioValid(form.value.plannedRecountRatio))
const fieldMap = PLAN_TO_SUMMARY_FIELD_MAP

const mapDialog = ref(false)
const aiLoading = ref(false)
const ocrLoading = ref(false)
const priorLoading = ref(false)
const exporting = ref(false)

const riskTagType = computed(() => {
  const r = form.value.existenceRiskLevel
  if (r === '高') return 'danger'
  if (r === '中') return 'warning'
  return 'success'
})

const navItems = [
  { id: 'sec-risk', label: '一·风险' },
  { id: 'sec-understand', label: '二·了解' },
  { id: 'sec-competence', label: '三·胜任' },
  { id: 'sec-arrange', label: '四·安排' },
  { id: 'sec-conclusion', label: '五·结论' },
]
const { activeId, scrollTo } = useStickySectionNav(navItems)

function persist(): void {
  state.persistPlanForm()
}

function handleReview(id: string): void {
  openReviewDialog(id)
}

function handleDraftSample(): void {
  state.draftPlanSampleQty()
  ElMessage.success('已按类别计划数量回填双向抽查预计数量（仅填空）')
}

function onRiskChange(): void {
  persist()
}

function handleImportH12(): void {
  const r = state.importCategoryScopesFromH12()
  if (!r.categories) {
    ElMessage.warning('H1-2 暂无明细可带入')
    return
  }
  ElMessage.success(`已从 H1-2 汇总 ${r.categories} 个类别` + (r.locations ? `，地点 ${r.locations} 处` : ''))
}

function handleImportH4(): void {
  const ok = state.importIdleNoteFromH4({ overwrite: !form.value.idleAssetsNote })
  if (!ok && form.value.idleAssetsNote) {
    ElMessageBox.confirm('闲置说明已有内容，是否覆盖？', '从 H1-4 回填', { type: 'warning' })
      .then(() => {
        state.importIdleNoteFromH4({ overwrite: true })
        ElMessage.success('已从 H1-4 覆盖闲置说明')
      })
      .catch(() => {})
    return
  }
  ElMessage.success('已从 H1-4 回填闲置说明')
}

function handleApplyRisk(): void {
  if (!form.value.existenceRiskLevel) {
    ElMessage.warning('请先选择存在性风险程度')
    return
  }
  ElMessageBox.confirm(
    `${riskSug.value.label}。将按建议回填空的计划监盘金额/数量与复盘比例（已填不覆盖）。是否继续？`,
    '按风险建议样本量',
    { type: 'info' },
  ).then(() => {
    state.applyRiskSampleSuggestions()
    ElMessage.success('已套用风险样本量建议')
  }).catch(() => {})
}

async function goCheckWithGate(): Promise<void> {
  if (planReady.value) {
    emit('navigate-sheet', 'H1-10')
    return
  }
  const list = gateBlockers.value.map((b, i) => `${i + 1}. ${b}`).join('\n')
  try {
    await ElMessageBox.confirm(
      `计划尚不完整，建议补全后再执行：\n\n${list}\n\n仍要强制进入 H1-10？`,
      '进入检查表前检查',
      { type: 'warning', confirmButtonText: '强制进入', cancelButtonText: '返回补全' },
    )
    emit('navigate-sheet', 'H1-10')
  } catch { /* cancel */ }
}

function handleLocalDraft(): void {
  const draft = draftPlanConclusion(form.value)
  if (!form.value.planConclusion) {
    state.fillPlanConclusionDraft()
    ElMessage.success('已生成规则草稿')
    return
  }
  ElMessageBox.confirm('结论已有内容，是否覆盖为规则草稿？', '规则草稿', { type: 'warning' })
    .then(() => {
      state.fillPlanConclusionDraft({ overwrite: true })
      ElMessage.success('已覆盖为规则草稿')
    })
    .catch(() => {
      // 展示草稿供复制
      ElMessageBox.alert(draft, '规则草稿预览', { confirmButtonText: '关闭' })
    })
}

async function handleAiDraft(): Promise<void> {
  aiLoading.value = true
  try {
    const ruleDraft = form.value.planConclusion || draftPlanConclusion(form.value)
    const res = await http.post(`/api/workpapers/${props.wpId}/h1/ai-generate`, {
      section: 'stocktake-plan',
      existingContent: form.value.planConclusion || '',
      relatedContext: {
        ruleDraft,
        risk: form.value.existenceRiskLevel,
        coverageRate: totals.value.coverageRate,
        method: form.value.method,
        plannedDate: form.value.plannedDate,
        sampleBookToFloorQty: form.value.sampleBookToFloorQty,
        sampleFloorToBookQty: form.value.sampleFloorToBookQty,
        plannedRecountRatio: form.value.plannedRecountRatio,
      },
    })
    const content = res.data?.content || res.data?.data?.content
    if (!content) {
      ElMessage.warning('AI 未返回内容')
      return
    }
    form.value.planConclusion = content
    persist()
    ElMessage.success('AI 结论已写入，可继续编辑')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || 'AI 生成失败')
  } finally {
    aiLoading.value = false
  }
}

async function handlePriorYear(): Promise<void> {
  priorLoading.value = true
  try {
    const meta = await http.get(`/api/projects/${props.projectId}/workpapers/${props.wpId}/prior-year`)
    const priorWpId = meta.data?.wp_id || meta.data?.data?.wp_id
    if (!priorWpId) {
      ElMessage.warning('未找到上年底稿')
      return
    }
    const resp = await http.get(`/api/workpapers/${priorWpId}/checklist-responses`)
    const items = Array.isArray(resp.data) ? resp.data : (resp.data?.items || resp.data?.data || [])
    const list = Array.isArray(items) ? items : []
    const formItem = list.find((x: any) => x.item_id === 'H1-9-form' || x.itemId === 'H1-9-form')
    let priorForm: any = null
    const raw = formItem?.remark || formItem?.value
    if (raw) {
      try { priorForm = typeof raw === 'string' ? JSON.parse(raw) : raw } catch { priorForm = null }
    }
    if (!priorForm) {
      const infoItem = list.find((x: any) => (x.item_id || x.itemId) === 'H1-9-info')
      if (infoItem?.remark) {
        try {
          const info = JSON.parse(infoItem.remark)
          priorForm = {
            plannedDate: info.stocktakeDate,
            plannedLead: info.participants,
            locationScopeNote: info.location,
            planConclusion: info.scope,
          }
        } catch { /* */ }
      }
    }
    const n = state.mergePriorYearHints(priorForm)
    ElMessage.success(n > 0 ? `已带入上年 ${n} 个字段到「以前年度」分区` : '上年无可带入的空字段（或上年无计划数据）')
  } catch (e: any) {
    const status = e?.response?.status
    ElMessage.warning(status === 404 ? '未关联上年项目或无对应 H1 底稿' : (e?.response?.data?.detail || '带入上年失败'))
  } finally {
    priorLoading.value = false
  }
}

async function runClientPlanOcr(): Promise<void> {
  const input = document.createElement('input')
  input.type = 'file'
  input.accept = '.pdf,.png,.jpg,.jpeg,.webp'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    ocrLoading.value = true
    try {
      const fd = new FormData()
      fd.append('file', file)
      const res = await http.post(
        `/api/workpapers/${props.wpId}/h1/stocktake-summary-ocr?section=client-plan`,
        fd,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const fields = res.data?.extracted_fields || res.data?.data?.extracted_fields || {}
      ocrDialog.editable = { ...fields }
      ocrDialog.visible = true
    } catch (e: any) {
      ElMessage.error(e?.response?.data?.detail || 'OCR 失败')
    } finally {
      ocrLoading.value = false
    }
  }
  input.click()
}

const ocrDialog = reactive({
  visible: false,
  editable: {} as Record<string, any>,
})

function confirmOcrWriteback(): void {
  const e = ocrDialog.editable
  const keys = [
    'icSystemName', 'icFrequency', 'icResponsible', 'clientPlanArrange',
    'clientMeetingNote', 'clientHeadcountEstimate', 'specialRequirements',
  ] as const
  for (const k of keys) {
    if (e[k] && !form.value[k]) (form.value as any)[k] = String(e[k])
  }
  if (e.content && !form.value.clientPlanArrange) {
    form.value.clientPlanArrange = String(e.content)
  }
  persist()
  ocrDialog.visible = false
  ElMessage.success('已确认回写企业盘点计划字段')
}

async function handleExportWord(): Promise<void> {
  exporting.value = true
  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/h1/stocktake-plan-export`,
      { fields: { ...form.value }, index_no: 'H1-9' },
      { responseType: 'blob' },
    )
    const blob = new Blob([res.data], {
      type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
    })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'H1-9_固定资产监盘计划.docx'
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('已导出 Word')
  } catch (e: any) {
    ElMessage.error(e?.response?.data?.detail || '导出失败')
  } finally {
    exporting.value = false
  }
}

function onScopeChange(row: PlanCategoryScopeRow): void {
  state.updateCategoryScope(row.rowId, { ...row })
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return Number(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function scopeSummary({ columns }: { columns: { property?: string; label?: string }[] }): string[] {
  const t = totals.value
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    const label = (col as any).label
    if (label === '期末余额') return fmtAmt(t.endingBalance)
    if (label === '减值准备') return fmtAmt(t.impairment)
    if (label === '账面净值') return fmtAmt(t.netBookValue)
    if (label === '数量') return String(t.quantity)
    if (label === '计划监盘数量') return String(t.planQty)
    if (label === '计划监盘金额') return fmtAmt(t.planAmount)
    if (label === '监盘比例%') return `${t.coverageRate}%`
    return ''
  })
}

const locDialog = reactive({
  visible: false,
  editingId: '' as string,
  draft: newPlanLocationRow(),
})

function openLocDialog(row?: PlanLocationRow): void {
  if (row) {
    locDialog.editingId = row.rowId
    locDialog.draft = { ...row }
  } else {
    locDialog.editingId = ''
    locDialog.draft = newPlanLocationRow()
  }
  locDialog.visible = true
}

function saveLocDialog(): void {
  const d = locDialog.draft
  if (locDialog.editingId) {
    const row = form.value.locations.find((r) => r.rowId === locDialog.editingId)
    if (row) Object.assign(row, d)
    persist()
  } else {
    state.addPlanLocation(d)
  }
  locDialog.visible = false
}
</script>

<style scoped>
.h1-tab-stocktake-plan {
  padding: 12px 16px 24px;
  font-size: var(--wp-font-size, 13px);
  max-width: 1100px;
}
.objective-alert { margin-bottom: 10px; }
.logic-warn { margin-bottom: 6px; }
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
  flex-wrap: wrap;
}
.sec-nav {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-bottom: 12px;
  padding: 8px;
  background: var(--el-fill-color-lighter);
  border-radius: 6px;
  position: sticky;
  top: 0;
  z-index: 5;
}
.sec-btn {
  border: 1px solid transparent;
  background: transparent;
  padding: 4px 8px;
  border-radius: 4px;
  font-size: 12px;
  cursor: pointer;
  color: var(--el-text-color-regular);
}
.sec-btn:hover { background: var(--el-fill-color); }
.sec-btn.active {
  background: var(--el-color-primary-light-9);
  color: var(--el-color-primary);
  border-color: var(--el-color-primary-light-5);
}
.attach-bar {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}
.attach-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
  padding-top: 6px;
}
.block-card { margin-bottom: 14px; }
.section-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.sub-h { margin: 14px 0 8px; font-size: 13px; font-weight: 600; }
.hint { font-size: 12px; color: var(--el-text-color-secondary); margin: 6px 0 8px; }
.field-with-ocr { display: flex; flex-direction: column; gap: 6px; width: 100%; }
.title-actions { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); }
.sign-area { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--el-border-color-lighter); }
.sign-row { display: flex; align-items: center; gap: 8px; }
.muted { color: var(--el-text-color-secondary); font-size: 12px; }
.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }
.mb-8 { margin-bottom: 8px; }
.ml-8 { margin-left: 8px; }
.ml-16 { margin-left: 16px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
</style>
