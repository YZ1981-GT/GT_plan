import { defineStore } from 'pinia'
import http from '@/utils/http'

export interface BasicInfo {
  client_name: string
  short_name: string
  audit_year: number | null
  project_type: string
  accounting_standard: string
  company_code: string
  template_type: string
  // audit-report-template-integration 需求 1.5：企业子类型 type_a/b/c/d
  company_subtype: string | null
  custom_template_id: string
  custom_template_name: string
  custom_template_version: string
  report_scope: string
  // 集团架构（consol-tree-three-code-autobuild 需求 1）：所有报表类型都填写，企业树由此自动推导。
  // 「合并类型」已移除：合并方式按下级企业的与上级关系自动识别（需求 4）。
  parent_company_name: string
  parent_company_code: string
  /** 与上级关系：'subsidiary' 子公司 / 'branch' 分公司 / '' 未填（上级代码为空时恒为空） */
  relation_to_parent: string
  ultimate_company_name: string
  ultimate_company_code: string
  signing_partner_id: string | null
  manager_id: string | null
  budget_hours: number | null
  contract_amount: number | null
}

export interface WizardStepData {
  step: string
  data: Record<string, unknown>
  completed: boolean
}

export interface WizardState {
  project_id: string | null
  current_step: string
  steps: Record<string, WizardStepData>
  completed: boolean
}

export interface ValidationMessage {
  field: string
  message: string
  severity: string
}

export interface ValidationResult {
  valid: boolean
  messages: ValidationMessage[]
}

export type StepKey = 'basic_info' | 'account_import' | 'account_mapping' | 'materiality' | 'team_assignment' | 'confirmation'

const STEP_KEYS: StepKey[] = [
  'basic_info',
]

export const STEP_LABELS: Record<StepKey, string> = {
  basic_info: '基本信息',
  account_import: '科目导入',
  account_mapping: '科目映射',
  materiality: '重要性水平',
  team_assignment: '团队分工',
  confirmation: '确认',
}

export const CONFIRMATION_REQUIRED_STEPS: StepKey[] = [
  'basic_info',
]

/** 集团关系字段（与后端 group_links.GROUP_FIELDS 同序） */
export const GROUP_FIELDS = [
  'parent_company_name',
  'parent_company_code',
  'relation_to_parent',
  'ultimate_company_name',
  'ultimate_company_code',
] as const

type GroupField = (typeof GROUP_FIELDS)[number]

/** 从项目详情/创建响应取集团关系字段（null → ''，便于直接回填表单） */
export function pickGroupFields(source: Record<string, unknown> | null | undefined): Record<GroupField, string> {
  const out = {} as Record<GroupField, string>
  for (const key of GROUP_FIELDS) {
    const value = source?.[key]
    out[key] = typeof value === 'string' ? value : ''
  }
  return out
}

export const useWizardStore = defineStore('wizard', {
  state: () => ({
    projectId: null as string | null,
    currentStepIndex: 0,
    stepList: [...STEP_KEYS] as string[],
    stepData: {} as Record<string, Record<string, unknown>>,
    completedSteps: {} as Record<string, boolean>,
    loading: false,
    /** 最近一次建项/保存基本信息时后端给出的说明（如「已同步集团关系到同企业的合并项目」） */
    lastNotices: [] as string[],
  }),

  getters: {
    currentStepKey(state): StepKey {
      return state.stepList[state.currentStepIndex] as StepKey
    },
    isFirstStep(state): boolean {
      return state.currentStepIndex === 0
    },
    isLastStep(state): boolean {
      return state.currentStepIndex === state.stepList.length - 1
    },
  },

  actions: {
    isStepCompleted(step: string): boolean {
      return !!this.completedSteps[step]
    },

    applyWizardState(state: WizardState) {
      this.projectId = state.project_id
      this.stepData = {}
      this.completedSteps = {}
      for (const [key, stepInfo] of Object.entries(state.steps)) {
        this.stepData[key] = stepInfo.data
        if (stepInfo.completed) {
          this.completedSteps[key] = true
        }
      }
      const idx = this.stepList.indexOf(state.current_step)
      if (idx >= 0) {
        this.currentStepIndex = idx
      } else {
        const nextVisibleStep = this.stepList.findIndex((step) => !this.completedSteps[step])
        this.currentStepIndex = nextVisibleStep >= 0 ? nextVisibleStep : this.stepList.length - 1
      }
    },

    /** Create project via POST /api/projects */
    async createProject(basicInfo: BasicInfo) {
      this.loading = true
      try {
        // Filter out null values for optional fields
        const payload: Record<string, unknown> = {
          client_name: basicInfo.client_name,
          short_name: basicInfo.short_name,
          audit_year: basicInfo.audit_year,
          project_type: basicInfo.project_type,
          accounting_standard: basicInfo.accounting_standard,
          company_code: basicInfo.company_code,
        }
        if (basicInfo.template_type) {
          payload.template_type = basicInfo.template_type
        }
        if (basicInfo.company_subtype) {
          payload.company_subtype = basicInfo.company_subtype
        }
        if (basicInfo.template_type === 'custom' && basicInfo.custom_template_id) {
          payload.custom_template_id = basicInfo.custom_template_id
          if (basicInfo.custom_template_name) {
            payload.custom_template_name = basicInfo.custom_template_name
          }
          if (basicInfo.custom_template_version) {
            payload.custom_template_version = basicInfo.custom_template_version
          }
        }
        if (basicInfo.report_scope) {
          payload.report_scope = basicInfo.report_scope
        }
        // 集团架构对所有报表类型发送（需求 1.6）：单户子公司/分公司正是企业树的叶子
        for (const key of GROUP_FIELDS) {
          const value = (basicInfo[key] ?? '').trim()
          if (value) payload[key] = value
        }
        if (basicInfo.signing_partner_id) {
          payload.signing_partner_id = basicInfo.signing_partner_id
        }
        if (basicInfo.manager_id) {
          payload.manager_id = basicInfo.manager_id
        }
        if (basicInfo.budget_hours != null) {
          payload.budget_hours = basicInfo.budget_hours
        }
        if (basicInfo.contract_amount != null) {
          payload.contract_amount = basicInfo.contract_amount
        }
        
        const { data } = await http.post('/api/projects', payload)
        const project = data
        this.projectId = project.id
        // 后端可能补齐了集团关系（按名称默认关系、继承同企业另一口径项目、按上级补控制方），以响应为准
        this.stepData.basic_info = { ...basicInfo, ...pickGroupFields(project) }
        this.completedSteps.basic_info = true
        this.lastNotices = Array.isArray(project?.notices) ? project.notices : []
        return project
      } finally {
        this.loading = false
      }
    },

    /** Load existing wizard state via GET /api/projects/{id}/wizard */
    async loadWizardState(projectId: string) {
      this.loading = true
      try {
        // validateStatus: 404 不触发 http.ts 拦截器弹窗（项目已完成向导时 404 正常）
        const resp = await http.get(`/api/projects/${projectId}/wizard`, {
          validateStatus: (s: number) => s < 400 || s === 404,
        })
        if (resp.status === 404) {
          // 无向导状态 → 从项目详情回填基本信息（兼容批量导入项目）
          await this._fallbackFromProjectDetail(projectId)
          return
        }
        const state: WizardState = resp.data
        this.applyWizardState(state)
        // 如果 wizard_state 存在但 basic_info 为空（批量导入项目），从项目详情回填
        if (!this.stepData.basic_info || !Object.keys(this.stepData.basic_info).length) {
          await this._fallbackFromProjectDetail(projectId)
        }
      } catch (e: any) {
        // 其他错误静默（不阻塞页面加载）
        console.warn('[wizard] loadWizardState failed:', e?.message)
        // 尝试从项目详情回填
        await this._fallbackFromProjectDetail(projectId)
      } finally {
        this.loading = false
      }
    },

    /** 从项目详情 API 回填 basic_info（批量导入项目的兜底） */
    async _fallbackFromProjectDetail(projectId: string) {
      try {
        const { data } = await http.get(`/api/projects/${projectId}`)
        const proj = data
        this.projectId = projectId
        this.stepData.basic_info = {
          client_name: proj.client_name || '',
          short_name: proj.short_name || '',
          company_code: proj.company_code || '',
          audit_year: proj.audit_year || null,
          project_type: proj.project_type || 'annual',
          accounting_standard: 'CAS',
          template_type: proj.template_type || 'soe',
          report_scope: proj.report_scope || 'standalone',
          // 需求 1.6：批量导入项目的兜底回填也要恢复集团关系
          ...pickGroupFields(proj),
        }
        this.completedSteps.basic_info = true
      } catch {
        // 项目详情也失败则放弃
      }
    },

    /** Save step data via PUT /api/projects/{id}/wizard/{step} */
    async saveStep(step: StepKey, stepData: Record<string, unknown>) {
      if (!this.projectId) return
      this.loading = true
      try {
        const { data } = await http.put(`/api/projects/${this.projectId}/wizard/${step}`, stepData)
        const state = data as WizardState & { notices?: string[] }
        this.applyWizardState(state)
        this.lastNotices = Array.isArray(state?.notices) ? state.notices : []
      } finally {
        this.loading = false
      }
    },

    async validateStep(step: StepKey): Promise<ValidationResult> {
      if (!this.projectId) {
        return {
          valid: false,
          messages: [{ field: 'project_id', message: '请先创建项目', severity: 'error' }],
        }
      }

      this.loading = true
      try {
        const { data } = await http.post(`/api/projects/${this.projectId}/wizard/validate/${step}`)
        return (data) as ValidationResult
      } finally {
        this.loading = false
      }
    },

    /** Confirm project via POST /api/projects/{id}/wizard/confirm */
    async confirmProject() {
      if (!this.projectId) return
      this.loading = true
      try {
        const { data } = await http.post(
          `/api/projects/${this.projectId}/wizard/confirm`,
        )
        return data
      } finally {
        this.loading = false
      }
    },

    goNext() {
      if (this.currentStepIndex < this.stepList.length - 1) {
        this.currentStepIndex++
      }
    },

    goPrev() {
      if (this.currentStepIndex > 0) {
        this.currentStepIndex--
      }
    },

    goToStep(index: number) {
      if (index >= 0 && index < this.stepList.length) {
        this.currentStepIndex = index
      }
    },

    reset() {
      this.projectId = null
      this.currentStepIndex = 0
      this.stepData = {}
      this.completedSteps = {}
      this.loading = false
      this.lastNotices = []
    },
  },
})
