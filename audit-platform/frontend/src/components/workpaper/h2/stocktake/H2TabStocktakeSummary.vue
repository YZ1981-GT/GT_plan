<template>
  <div class="h2-tab-stocktake-summary">
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：按「了解管理→盘前检查→人员/时间→逐项踏勘→总体核对→异常→收尾→结论」汇总在建工程现场察看结果，证实存在性、形象进度与停工/转固风险。"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <GtIndexChip value="wp:H2-14" :context-project-id="projectId" />
        <el-tag size="small" type="info">察看 {{ checkStats.total }} 项</el-tag>
        <el-tag size="small" type="warning">停工 {{ checkStats.stopped }}</el-tag>
        <el-tag size="small" type="danger">异常 {{ form.abnormalProjects.length }}</el-tag>
      </div>
      <div class="toolbar-right">
        <el-button size="small" @click="emit('navigate-sheet', 'H2-12')">← H2-12 计划</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H2-13')">H2-13 检查表</el-button>
        <el-button size="small" @click="emit('navigate-sheet', 'H2-15')">H2-15 减值</el-button>
        <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleSync">
          从 H2-12/13 回填
        </el-button>
        <el-button size="small" circle @click="openReview('H2-14')">💬</el-button>
      </div>
    </div>

    <el-tag v-if="form.lastAutoSyncAt" size="small" type="info" class="sync-tag">
      已回填 {{ form.lastAutoSyncAt.slice(0, 19).replace('T', ' ') }}
    </el-tag>

    <!-- 完工程度闸门 -->
    <el-card id="sec-gate" shadow="never" class="block-card gate-card">
      <template #header>
        <div class="section-title">
          <span>完工程度闸门</span>
          <el-tag :type="completenessOk ? 'success' : 'warning'" size="small">
            {{ completenessOk ? '可签署' : `${incompleteCount} 项待补` }}
          </el-tag>
        </div>
      </template>
      <div class="gate-list">
        <div v-for="c in completeness" :key="c.id" class="gate-item" :class="{ ok: c.ok }">
          <span>{{ c.ok ? '✓' : '○' }} {{ c.label }}</span>
          <span v-if="!c.ok" class="gate-hint">{{ c.hint }}</span>
        </div>
      </div>
    </el-card>

    <el-alert
      v-for="(w, i) in logicWarnings"
      :key="i"
      type="warning"
      :closable="false"
      :title="w"
      class="logic-warn"
      show-icon
    />

    <nav class="sec-nav" aria-label="监盘小结分区">
      <button
        v-for="item in navItems"
        :key="item.id"
        type="button"
        class="sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <div class="attach-bar" v-if="projectId && wpId">
      <span class="attach-label">监盘小结附件</span>
      <ItemAttachment
        :project-id="projectId"
        :wp-id="wpId"
        sheet-key="H2-14"
        :item-index="0"
        accept=".pdf,.png,.jpg,.jpeg,.xlsx,.xls,.doc,.docx,.mp4,.mov"
      />
    </div>

    <!-- 〇、仪表板 -->
    <el-card id="sec-dash" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>〇、现场察看结果仪表板（联动 H2-13）</span>
          <el-button size="small" link type="primary" @click="emit('navigate-sheet', 'H2-13')">打开检查表</el-button>
        </div>
      </template>
      <el-row :gutter="12">
        <el-col :span="6"><div class="stat-box"><div class="stat-label">察看总数</div><div class="stat-value">{{ checkStats.total }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box success"><div class="stat-label">施工中</div><div class="stat-value">{{ checkStats.inProgress }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box warning"><div class="stat-label">停工</div><div class="stat-value">{{ checkStats.stopped }}</div></div></el-col>
        <el-col :span="6"><div class="stat-box primary"><div class="stat-label">完工</div><div class="stat-value">{{ checkStats.completed }}</div></div></el-col>
      </el-row>
    </el-card>

    <!-- 一、资产负债表日 -->
    <el-card id="sec-bs" shadow="never" class="block-card">
      <template #header><span>一、资产负债表日</span></template>
      <el-input
        v-model="form.bsDateNote"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="说明现场察看日与资产负债表日的关系、截止性处理…"
        @change="persist"
      />
    </el-card>

    <!-- 二、盘前检查程序 -->
    <el-card id="sec-pre" shadow="never" class="block-card">
      <template #header><span>二、实际现场察看前的检查程序</span></template>
      <el-form label-width="160px" size="small">
        <el-form-item label="工程管理部门">
          <el-input v-model="form.engDept" :disabled="isReadonly" placeholder="部门名称" @change="persist" />
        </el-form-item>
        <el-form-item label="管理人员">
          <el-input v-model="form.engStaff" :disabled="isReadonly" placeholder="姓名/职务" @change="persist" />
        </el-form-item>
        <el-form-item label="管理制度设计是否合理">
          <el-input v-model="form.policyDesignOk" :disabled="isReadonly" placeholder="是/否及说明" @change="persist" />
        </el-form-item>
        <el-form-item label="是否有效执行">
          <el-input v-model="form.policyExecutedOk" :disabled="isReadonly" placeholder="是/否及说明" @change="persist" />
        </el-form-item>
        <el-form-item label="制度索引">
          <el-input v-model="form.policyIndex" :disabled="isReadonly" placeholder="如 C7 / 附件索引" @change="persist" />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 三、参与人员及时间 -->
    <el-card id="sec-people" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>三、参与察看人员及察看时间</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="state.addClientPersonnel()">+ 企业人员</el-button>
            <el-button v-if="!isReadonly" size="small" @click="state.addAuditorPersonnel()">+ 审计人员</el-button>
          </div>
        </div>
      </template>

      <h4 class="sub-h">1. 被审计单位人员</h4>
      <el-table :data="form.clientPersonnel" border size="small">
        <el-table-column type="index" width="44" label="序" />
        <el-table-column label="所属部门" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.department" size="small" @change="persist" />
            <span v-else>{{ row.department || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人数" width="90">
          <template #default="{ row }">
            <el-input-number
              v-if="!isReadonly"
              v-model="row.headcount"
              :min="0"
              size="small"
              controls-position="right"
              @change="persist"
            />
            <span v-else>{{ row.headcount }}</span>
          </template>
        </el-table-column>
        <el-table-column label="人员名称" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.names" size="small" @change="persist" />
            <span v-else>{{ row.names || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所负责的部分" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.responsibleArea" size="small" @change="persist" />
            <span v-else>{{ row.responsibleArea || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="60">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="state.removeClientPersonnel(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <h4 class="sub-h">2. 审计人员</h4>
      <el-table :data="form.auditorPersonnel" border size="small">
        <el-table-column type="index" width="44" label="序" />
        <el-table-column label="人员名称" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.names" size="small" @change="persist" />
            <span v-else>{{ row.names || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="所负责的部分" min-width="140">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.responsibleArea" size="small" @change="persist" />
            <span v-else>{{ row.responsibleArea || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="60">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="state.removeAuditorPersonnel(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <h4 class="sub-h">3. 实际现场察看日</h4>
      <el-form inline size="small">
        <el-form-item label="日期">
          <el-date-picker
            v-model="form.actualDate"
            type="date"
            value-format="YYYY-MM-DD"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="开始">
          <el-time-select
            v-model="form.startTime"
            start="06:00"
            step="00:15"
            end="22:00"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="结束">
          <el-time-select
            v-model="form.endTime"
            start="06:00"
            step="00:15"
            end="23:45"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-tag v-if="!timeRangeOk" type="danger" size="small">结束时间须晚于开始时间</el-tag>
      </el-form>
    </el-card>

    <!-- 四(一)、逐项工程观察 -->
    <el-card id="sec-obs" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>四、实际现场察看情况说明（一）逐个工程项目形象进度</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" type="primary" plain @click="handleSync">从 H2-13 回填</el-button>
            <el-button v-if="!isReadonly" size="small" @click="state.addProjectObservation()">+ 新增工程</el-button>
          </div>
        </div>
      </template>
      <el-table :data="form.projectObservations" border stripe size="small">
        <el-table-column type="index" width="44" label="序" />
        <el-table-column label="在建工程名称" min-width="130">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.projectName" size="small" @change="persist" />
            <span v-else>{{ row.projectName || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程简图索引" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.diagramIndex" size="small" @change="persist" />
            <span v-else>{{ row.diagramIndex || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="工程地点" min-width="110">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.location" size="small" @change="persist" />
            <span v-else>{{ row.location || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="施工状态" width="90">
          <template #default="{ row }">
            <el-tag
              v-if="row.constructionStatus"
              :type="row.constructionStatus === '停工' ? 'danger' : row.constructionStatus === '完工' ? 'success' : 'info'"
              size="small"
            >{{ row.constructionStatus }}</el-tag>
            <span v-else class="muted">—</span>
          </template>
        </el-table-column>
        <el-table-column label="形象进度等情况描述" min-width="200">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              v-model="row.progressDescription"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              size="small"
              @change="persist"
            />
            <span v-else>{{ row.progressDescription || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column label="现场照片索引" width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.photoIndex" size="small" @change="persist" />
            <span v-else>{{ row.photoIndex || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="60">
          <template #default="{ row }">
            <el-button size="small" link type="danger" @click="state.removeProjectObservation(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-if="!form.projectObservations.length" description="暂无工程观察行，可从 H2-13 回填" :image-size="56" />
    </el-card>

    <!-- 四(二)、总体核对 -->
    <el-card id="sec-checks" shadow="never" class="block-card">
      <template #header><span>四、（二）察看总体情况描述</span></template>
      <el-form label-width="0" size="small" class="check-form">
        <div v-for="(item, idx) in form.observationChecks" :key="item.id" class="check-row">
          <div class="check-label">{{ idx + 1 }}. {{ item.label }}</div>
          <div class="check-fields">
            <el-input
              v-model="item.answer"
              type="textarea"
              :autosize="{ minRows: 2 }"
              :disabled="isReadonly"
              placeholder="填写核对结果与说明…"
              @change="persist"
            />
            <el-input
              v-model="item.indexRef"
              size="small"
              style="width:140px;margin-top:6px"
              :disabled="isReadonly"
              placeholder="检查记录索引"
              @change="persist"
            />
          </div>
        </div>
      </el-form>
      <el-form-item label="总体情况补充" label-width="110px" class="mt-12">
        <el-input
          v-model="form.overallSituation"
          type="textarea"
          :autosize="{ minRows: 2 }"
          :disabled="isReadonly"
          placeholder="可概述范围、方法、覆盖情况（兼容旧版踏勘总体）…"
          @change="persist"
        />
      </el-form-item>
    </el-card>

    <!-- 五、异常 -->
    <el-card id="sec-abn" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>五、现场察看中发现的异常情况说明</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="state.mergeAbnormalFromCheck()">并入 H2-13 异常</el-button>
            <el-button v-if="!isReadonly" size="small" type="primary" @click="handleAddAnomaly">+ 新增异常</el-button>
          </div>
        </div>
      </template>
      <el-table
        v-if="form.abnormalProjects.length"
        :data="form.abnormalProjects"
        border
        stripe
        size="small"
      >
        <el-table-column prop="name" label="工程项目" min-width="120">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.name" size="small" @change="persist" />
            <span v-else>{{ row.name || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="abnormalType" label="异常类型" min-width="110">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.abnormalType" size="small" style="width:100%" @change="persist">
              <el-option label="停工" value="停工" />
              <el-option label="进度异常" value="进度异常" />
              <el-option label="质量问题" value="质量问题" />
              <el-option label="不存在" value="不存在" />
              <el-option label="应转未转" value="应转未转" />
              <el-option label="其他" value="其他" />
            </el-select>
            <el-tag v-else :type="row.abnormalType === '停工' ? 'danger' : 'warning'" size="small">
              {{ row.abnormalType || '—' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="异常描述" min-width="180">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" v-model="row.description" size="small" @change="persist" />
            <span v-else>{{ row.description || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="suggestion" label="后续处理建议" min-width="140">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" v-model="row.suggestion" size="small" style="width:100%" @change="persist">
              <el-option label="关注减值" value="关注减值" />
              <el-option label="追加说明" value="追加说明" />
              <el-option label="管理层书面说明" value="管理层书面说明" />
              <el-option label="建议调整" value="建议调整" />
              <el-option label="关注转固(H2-5)" value="关注转固(H2-5)" />
            </el-select>
            <span v-else>{{ row.suggestion || '—' }}</span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" width="50">
          <template #default="{ row }">
            <el-button size="small" type="danger" link @click="state.removeAbnormalProject(row.rowId)">✕</el-button>
          </template>
        </el-table-column>
      </el-table>
      <el-empty v-else description="无异常情况" :image-size="56" />
      <el-input
        v-model="form.abnormalNote"
        class="mt-12"
        type="textarea"
        :autosize="{ minRows: 2 }"
        :disabled="isReadonly"
        placeholder="其他异常说明（自由文本）…"
        @change="persist"
      />
    </el-card>

    <!-- 六、结束工作 -->
    <el-card id="sec-close" shadow="never" class="block-card">
      <template #header><span>六、工程现场察看结束工作说明</span></template>
      <el-form label-width="220px" size="small">
        <el-form-item label="结束后的工作记录">
          <el-input
            v-model="form.postWorkNote"
            type="textarea"
            :autosize="{ minRows: 2 }"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
        <el-form-item label="工程管理人员熟悉程度">
          <el-select v-model="form.evalFamiliarity" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="对现场察看工作的负责态度">
          <el-select v-model="form.evalAttitude" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="索取资料配合程度">
          <el-select v-model="form.evalCooperation" :disabled="isReadonly" style="width:200px" @change="persist">
            <el-option label="好" value="好" />
            <el-option label="一般" value="一般" />
            <el-option label="差" value="差" />
          </el-select>
        </el-form-item>
        <el-form-item label="已取得《工程现场察看差异说明》并盖章">
          <el-radio-group v-model="form.diffExplanationObtained" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
          <el-input
            v-model="form.diffExplanationIndex"
            size="small"
            style="width:160px;margin-left:12px"
            placeholder="索引"
            :disabled="isReadonly"
            @change="persist"
          />
          <ItemAttachment
            v-if="wpId"
            class="inline-attach"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="H2-14-diff"
            :item-index="0"
          />
        </el-form-item>
        <el-form-item label="被审计单位人员已签字确认">
          <el-radio-group v-model="form.clientSigned" :disabled="isReadonly" @change="persist">
            <el-radio value="Y">是</el-radio>
            <el-radio value="N">否</el-radio>
          </el-radio-group>
          <el-input
            v-model="form.clientSignIndex"
            size="small"
            style="width:160px;margin-left:12px"
            placeholder="索引"
            :disabled="isReadonly"
            @change="persist"
          />
        </el-form-item>
      </el-form>
    </el-card>

    <!-- 结论 -->
    <el-card id="sec-conclusion" shadow="never" class="block-card">
      <template #header>
        <div class="section-title">
          <span>监盘总结与审计结论</span>
          <div class="title-actions">
            <el-button v-if="!isReadonly" size="small" @click="state.applyRuleConclusion()">规则起草</el-button>
          </div>
        </div>
      </template>
      <el-alert
        v-if="!completenessOk"
        type="warning"
        :closable="false"
        title="完工程度闸门未全部通过，仍可签署，但建议先补齐标黄项后再提交复核。"
        class="mb-8"
      />
      <el-input
        v-model="form.conclusion"
        type="textarea"
        :autosize="{ minRows: 4 }"
        :disabled="isReadonly"
        placeholder="总结察看范围、进度核对、停工/转固异常及对报表影响…"
        @change="persist"
      />
    </el-card>

    <div class="sign-area">
      <div class="sign-row">
        <span>编制人：</span>
        <el-input v-if="!isReadonly" v-model="form.preparedBy" size="small" style="width:120px" @change="persist" />
        <span v-else>{{ form.preparedBy || '________' }}</span>
        <span class="ml">日期：</span>
        <el-date-picker
          v-if="!isReadonly"
          v-model="form.preparedDate"
          type="date"
          size="small"
          value-format="YYYY-MM-DD"
          @change="persist"
        />
        <span v-else>{{ form.preparedDate || '____年__月__日' }}</span>
      </div>
      <div class="sign-row mt-8">
        <span>复核人：</span>
        <el-input v-if="!isReadonly" v-model="form.reviewedBy" size="small" style="width:120px" @change="persist" />
        <span v-else>{{ form.reviewedBy || '________' }}</span>
        <span class="ml">日期：</span>
        <el-date-picker
          v-if="!isReadonly"
          v-model="form.reviewedDate"
          type="date"
          size="small"
          value-format="YYYY-MM-DD"
          @change="persist"
        />
        <span v-else>{{ form.reviewedDate || '____年__月__日' }}</span>
      </div>
    </div>

    <details class="edit-tips">
      <summary>编制提示</summary>
      <ul>
        <li>编制逻辑：了解管理 → 盘前资料 → 人员/时间 → 逐项形象进度 → 六项总体核对 → 异常 → 差异说明盖章 → 结论</li>
        <li>存在性（账面→现场）与完整性（现场→账面）宜兼顾；进度宜与监理报告交叉核对</li>
        <li>停工项目建议写明是否长期停工，并联动 H2-15 减值；已达可使用状态仍挂在建联动 H2-5</li>
        <li>索取盖章《工程现场察看差异说明》并请企业人员签字，形成闭环证据</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * H2TabStocktakeSummary.vue — H2-14 在建工程监盘小结
 * 对齐致同模板结构；参照 H1-11 固定资产监盘小结处理范式
 */
import { inject, toRef, computed, ref, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useH2Stocktake } from '../../composables/useH2Stocktake'
import GtIndexChip from '../../GtIndexChip.vue'
import ItemAttachment from '../../ItemAttachment.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheet: string): void
}>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})

const state = useH2Stocktake({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: computed(() => props.allResponses),
  isReadonly: toRef(props, 'isReadonly'),
  phase: 'summary',
  onSave: (itemId: string, value: any) => saveResponse(itemId, value),
})

const isReadonly = computed(() => props.isReadonly)
const form = computed(() => state.summary.value)
const checkStats = computed(() => state.checkStats.value)
const completeness = computed(() => state.completeness.value)
const completenessOk = computed(() => state.completenessOk.value)
const incompleteCount = computed(() => state.incompleteCount.value)
const logicWarnings = computed(() => state.logicWarnings.value)
const timeRangeOk = computed(() => state.timeRangeOk.value)

const navItems = [
  { id: 'sec-dash', label: '仪表板' },
  { id: 'sec-bs', label: '一、资产负债日' },
  { id: 'sec-pre', label: '二、盘前' },
  { id: 'sec-people', label: '三、人员时间' },
  { id: 'sec-obs', label: '四、逐项察看' },
  { id: 'sec-checks', label: '四、总体核对' },
  { id: 'sec-abn', label: '五、异常' },
  { id: 'sec-close', label: '六、收尾' },
  { id: 'sec-conclusion', label: '结论' },
]

const activeId = ref('sec-dash')

function scrollTo(id: string) {
  activeId.value = id
  document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

function onScroll() {
  const ids = navItems.map(n => n.id)
  for (let i = ids.length - 1; i >= 0; i--) {
    const el = document.getElementById(ids[i])
    if (el && el.getBoundingClientRect().top <= 120) {
      activeId.value = ids[i]
      break
    }
  }
}

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onBeforeUnmount(() => window.removeEventListener('scroll', onScroll))

function persist() {
  state.persistSummary()
}

function handleSync() {
  state.syncFromUpstream()
  ElMessage.success('已从 H2-12/H2-13 回填空字段')
}

async function handleAddAnomaly() {
  try {
    const { value } = await ElMessageBox.prompt('请输入异常工程名称', '新增异常', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    if (value) state.addAbnormalProject(value)
  } catch { /* cancelled */ }
}

function openReview(id: string) {
  openReviewDialog(id)
}
</script>

<style scoped>
.h2-tab-stocktake-summary { padding: 16px; font-size: var(--wp-font-size, 13px); }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 8px; gap: 8px; flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; gap: 6px; align-items: center; flex-wrap: wrap; }
.sync-tag { margin-bottom: 8px; }
.block-card { margin-bottom: 16px; }
.gate-card { border-left: 3px solid var(--el-color-warning); }
.gate-list { display: flex; flex-direction: column; gap: 6px; }
.gate-item { display: flex; gap: 12px; align-items: baseline; font-size: 13px; color: var(--el-text-color-secondary); }
.gate-item.ok { color: var(--el-color-success); }
.gate-hint { color: var(--el-color-warning); font-size: 12px; }
.logic-warn { margin-bottom: 8px; }
.sec-nav {
  display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 12px;
  position: sticky; top: 0; z-index: 5; background: var(--el-bg-color); padding: 8px 0;
}
.sec-btn {
  border: 1px solid var(--el-border-color); background: transparent;
  border-radius: 4px; padding: 4px 10px; font-size: 12px; cursor: pointer;
  color: var(--el-text-color-regular);
}
.sec-btn.active, .sec-btn:hover {
  border-color: var(--el-color-primary); color: var(--el-color-primary);
  background: var(--el-color-primary-light-9);
}
.attach-bar { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
.attach-label { font-size: 12px; color: var(--el-text-color-secondary); }
.section-title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.title-actions { display: flex; gap: 6px; align-items: center; }
.stat-box {
  background: var(--el-fill-color-light); border-radius: 6px; padding: 12px; text-align: center;
}
.stat-box.success { background: var(--el-color-success-light-9); }
.stat-box.warning { background: var(--el-color-warning-light-9); }
.stat-box.primary { background: var(--el-color-primary-light-9); }
.stat-label { font-size: 12px; color: var(--el-text-color-secondary); }
.stat-value { font-size: 22px; font-weight: 600; margin-top: 4px; font-variant-numeric: tabular-nums; }
.sub-h { margin: 12px 0 8px; font-size: 13px; font-weight: 600; }
.check-row { margin-bottom: 14px; padding-bottom: 12px; border-bottom: 1px dashed var(--el-border-color-lighter); }
.check-label { font-size: 13px; margin-bottom: 6px; color: var(--el-text-color-primary); line-height: 1.5; }
.check-fields { padding-left: 8px; }
.muted { color: var(--el-text-color-placeholder); }
.mt-8 { margin-top: 8px; }
.mt-12 { margin-top: 12px; }
.mb-8 { margin-bottom: 8px; }
.ml { margin-left: 24px; }
.inline-attach { display: inline-flex; margin-left: 8px; vertical-align: middle; }
.sign-area { padding: 16px 0; }
.sign-row { display: flex; align-items: center; gap: 8px; font-size: var(--wp-font-size, 13px); }
.edit-tips { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.edit-tips summary { cursor: pointer; font-weight: 500; }
.edit-tips ul { padding-left: 20px; margin-top: 8px; }
</style>
