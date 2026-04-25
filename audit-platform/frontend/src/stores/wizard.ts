import { defineStore } from 'pinia'
import http from '@/utils/http'

export interface BasicInfo {
  client_name: string
  audit_year: number | null
  project_type: string
  accounting_standard: string
  company_code: string
  template_type: string
  custom_template_id: string
  custom_template_name: string
  custom_template_version: string
  report_scope: string
  parent_company_name: string
  parent_company_code: string
  ultimate_company_name: string
  ultimate_company_code: string
  signing_partner_id: string | null
  manager_id: string | null
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

export type StepKey =
  | 'basic_info'
  | 'account_import'
  | 'account_mapping'
  | 'materiality'
  | 'team_assignment'
  | 'confirmation'

const STEP_KEYS: StepKey[] = [
  'basic_info',
  'materiality',
  'team_assignment',
  'confirmation',
]

export const STEP_LABELS: Record<StepKey, string> = {
  basic_info: '基本信息',
  account_import: '科目导入',
  account_mapping: '科目映射',
  materiality: '重要性水平',
  team_assignment: '团队分工',
  confirmation: '确认',
}

export const useWizardStore = defineStore('wizard', {
  state: () => ({
    projectId: null as string | null,
    currentStepIndex: 0,
    stepList: [...STEP_KEYS] as string[],
    stepData: {} as Record<string, Record<string, unknown>>,
    completedSteps: {} as Record<string, boolean>,
    loading: false,
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
          audit_year: basicInfo.audit_year,
          project_type: basicInfo.project_type,
          accounting_standard: basicInfo.accounting_standard,
        }
        if (basicInfo.company_code) {
          payload.company_code = basicInfo.company_code
        }
        if (basicInfo.template_type) {
          payload.template_type = basicInfo.template_type
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
        if (basicInfo.report_scope === 'consolidated') {
          if (basicInfo.parent_company_name) payload.parent_company_name = basicInfo.parent_company_name
          if (basicInfo.parent_company_code) payload.parent_company_code = basicInfo.parent_company_code
          if (basicInfo.ultimate_company_name) payload.ultimate_company_name = basicInfo.ultimate_company_name
          if (basicInfo.ultimate_company_code) payload.ultimate_company_code = basicInfo.ultimate_company_code
        }
        if (basicInfo.signing_partner_id) {
          payload.signing_partner_id = basicInfo.signing_partner_id
        }
        if (basicInfo.manager_id) {
          payload.manager_id = basicInfo.manager_id
        }
        
        const { data } = await http.post('/api/projects', payload)
        const project = data.data ?? data
        this.projectId = project.id
        this.stepData.basic_info = { ...basicInfo }
        this.completedSteps.basic_info = true
        return project
      } finally {
        this.loading = false
      }
    },

    /** Load existing wizard state via GET /api/projects/{id}/wizard */
    async loadWizardState(projectId: string) {
      this.loading = true
      try {
        const { data } = await http.get(`/api/projects/${projectId}/wizard`)
        const state: WizardState = data.data ?? data
        this.applyWizardState(state)
      } finally {
        this.loading = false
      }
    },

    /** Save step data via PUT /api/projects/{id}/wizard/{step} */
    async saveStep(step: StepKey, stepData: Record<string, unknown>) {
      if (!this.projectId) return
      this.loading = true
      try {
        const { data } = await http.put(`/api/projects/${this.projectId}/wizard/${step}`, stepData)
        const state: WizardState = data.data ?? data
        this.applyWizardState(state)
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
        return data.data ?? data
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
    },
  },
})
