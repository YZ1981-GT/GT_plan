import { defineStore } from 'pinia'
import http from '@/utils/http'

export interface BasicInfo {
  client_name: string
  audit_year: number | null
  project_type: string
  accounting_standard: string
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

const STEP_KEYS = [
  'basic_info',
  'account_import',
  'account_mapping',
  'materiality',
  'team_assignment',
  'confirmation',
] as const

export type StepKey = (typeof STEP_KEYS)[number]

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
        this.projectId = state.project_id
        for (const [key, stepInfo] of Object.entries(state.steps)) {
          this.stepData[key] = stepInfo.data
          if (stepInfo.completed) {
            this.completedSteps[key] = true
          }
        }
        const idx = this.stepList.indexOf(state.current_step)
        if (idx >= 0) this.currentStepIndex = idx
      } finally {
        this.loading = false
      }
    },

    /** Save step data via PUT /api/projects/{id}/wizard/{step} */
    async saveStep(step: StepKey, stepData: Record<string, unknown>) {
      if (!this.projectId) return
      this.loading = true
      try {
        await http.put(`/api/projects/${this.projectId}/wizard/${step}`, stepData)
        this.stepData[step] = { ...stepData }
        this.completedSteps[step] = true
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
