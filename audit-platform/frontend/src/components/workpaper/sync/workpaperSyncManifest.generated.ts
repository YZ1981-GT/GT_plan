/**
 * 本文件由 `backend/scripts/gen/generate_workpaper_sync_manifest.py` 生成，请勿手工编辑。
 * 业务裁决真源：`backend/data/workpaper_sync_entry_overlay.json`。
 * 源码事实真源：Vue template AST + htmlRendererRegistry 的 word-template dispatcher。
 */

export type WorkpaperSyncCapability =
  | 'bidirectional'
  | 'single_html'
  | 'single_onlyoffice'
  | 'unreachable'

/** source-backed，与 V151 `working_paper_sync_test_run.editability` 的 CHECK 同域。 */
export type WorkpaperSyncEditability = 'editable' | 'readonly' | 'unreachable'

/** source-backed，与 V151 `working_paper_sync_test_run.room_model` 的 CHECK 同域。 */
export type WorkpaperSyncRoomModel = 'shared' | 'exclusive' | 'none'

export interface WorkpaperSyncManifestEntry {
  entryId: string
  hostPath: string
  documentType: 'xlsx' | 'docx'
  capability: WorkpaperSyncCapability | null
  adjudicationState: 'terminal' | 'pending' | 'inherited'
  capabilityVerdictStage: string | null
  capabilityTarget: WorkpaperSyncCapability | null
  capabilityTargetBlockedBy: string[]
  htmlCounterpartVerdict: 'exists' | 'none' | null
  htmlCounterpartSourceRefs: string[]
  effectiveEntryId: string
  migrationState: string
  independentEntry: boolean
  parentEntryId: string | null
  wpMatch: {
    wp_code_patterns: string[]
    component_types: string[]
    sheet_literals: string[]
    sheet_expressions: string[]
    source_host: string
    wp_code_adjudication_source?: string
  }
  editability: WorkpaperSyncEditability
  roomModel: WorkpaperSyncRoomModel
  scenarioProfileId: string
  roomServiceState: string
  reasonCodes: string[]
  hasContractEvidence: boolean
  hasBrowserEvidence: boolean
}

export const WORKPAPER_SYNC_MANIFEST_DIGEST = "dcde4f2377050e7e5527ff0bc2a7a32913c325339657e25358289139b4c92424"

export const WORKPAPER_SYNC_ADJUDICATION_SOURCE_DIGEST = "3382b0a961727e5826372683a2db995eff201a2535b886014d4d44f5eee6ae6e"

export const WORKPAPER_SYNC_WP_CODE_ADJUDICATION_DIGEST = "26708767e63fd645ad049562b3609f99fee21c32ec075291fb6e70f4b9da4ad9"

export const WORKPAPER_SYNC_PROFILE_SOURCE_DIGEST = "6390de60a6a7f895abb09f036b7c94aaf736e66324255e149dffcaf24ceec040"

export const WORKPAPER_SYNC_MANIFEST_STATS = {
  "by_component": {
    "GtOnlyOfficeSheet": 225,
    "OnlyOfficeWordDialog": 2,
    "WorkpaperSyncEditorHost": 108,
    "WorkpaperWordEditor": 4
  },
  "capability_counts": {
    "bidirectional": 111,
    "unreachable": 1
  },
  "dispatcher_count": 1,
  "editability_counts": {
    "editable": 197,
    "unreachable": 1
  },
  "entry_count": 198,
  "host_count": 196,
  "independent_entry_count": 145,
  "legacy_fake_bidirectional_count": 59,
  "mount_count": 339,
  "parent_duplicate_count": 52,
  "room_model_counts": {
    "exclusive": 6,
    "none": 1,
    "shared": 191
  },
  "room_service_state": "room_service_wired",
  "scenario_profile_counts": {
    "docx.editable.exclusive.dynamic.room_service_wired.v1": 1,
    "docx.editable.exclusive.single.room_service_wired.v1": 5,
    "docx.editable.shared.single.room_service_wired.v1": 1,
    "xlsx.editable.shared.none.room_service_wired.v1": 1,
    "xlsx.editable.shared.single.room_service_wired.v1": 189,
    "xlsx.unreachable.none.single.room_service_wired.v1": 1
  },
  "unadjudicated_count": 78,
  "unreachable_count": 1
} as const

export const WORKPAPER_SYNC_MANIFEST = [
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "definition_producer_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-a10-bundle",
    "entryId": "docx/gt-a10-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA10Bundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA10Bundle.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "html_reload_only",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA10Bundle.vue",
      "wp_code_patterns": [
        "A10B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "definition_producer_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-a12-bundle",
    "entryId": "docx/gt-a12-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA12Bundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA12Bundle.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "html_reload_only",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA12Bundle.vue",
      "wp_code_patterns": [
        "A12B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "definition_producer_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-a16-bundle",
    "entryId": "docx/gt-a16-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA16Bundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA16Bundle.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "html_reload_only",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA16Bundle.vue",
      "wp_code_patterns": [
        "A16B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "definition_producer_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-a17-bundle",
    "entryId": "docx/gt-a17-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "html_reload_only",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
      "wp_code_patterns": [
        "A17B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "definition_producer_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-wp-renderer",
    "entryId": "docx/gt-wp-renderer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "html_reload_only",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.dynamic.room_service_wired.v1",
    "wpMatch": {
      "component_types": [
        "word-template"
      ],
      "sheet_expressions": [
        ":sheet-name=\"activeSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "per_entry_definition_runtime_and_evidence"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/gt-a16-bundle",
    "entryId": "docx/workpaper-word-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA16Bundle.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "docx/gt-a16-bundle",
    "reasonCodes": [
      "document_state_is_not_durable_ack",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "exclusive",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.exclusive.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "counterpart_pending",
    "documentType": "docx",
    "editability": "editable",
    "effectiveEntryId": "docx/wp-popup-docx-editor",
    "entryId": "docx/wp-popup-docx-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/WpPopupDocxEditor.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "document_state_is_not_durable_ack",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "docx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/WpPopupDocxEditor.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "counterpart_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/b60/gt-b60-bundle",
    "entryId": "xlsx/b60/gt-b60-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/b60/GtB60Bundle.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"B60\""
      ],
      "sheet_literals": [
        "B60"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/b60/GtB60Bundle.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "B60-1"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/b60/gt-b60-bundle",
    "entryId": "xlsx/b60/gt-b60-docx-pane",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/b60/GtB60DocxPane.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/b60/gt-b60-bundle",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/b60/GtB60DocxPane.vue",
      "wp_code_patterns": [
        "B60D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-10",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/cash-flow-verification",
    "entryId": "xlsx/cash-flow-verification",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue#L133",
      "audit-platform/frontend/src/components/workpaper/composables/useA51CashflowAudit.ts#L344",
      "audit-platform/frontend/src/components/workpaper/composables/useA51CashflowAudit.ts#L394"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sub.code\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-customer-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerPrice.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerPrice.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-customer-structure",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerStructure.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerStructure.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-indicator",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabIndicator.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabIndicator.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-margin-monthly",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabMarginMonthly.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabMarginMonthly.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-product-margin",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductMargin.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductMargin.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/analysis/d4-tab-product-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductPrice.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductPrice.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/core/d4-tab-adjudication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/core/D4TabAdjudication.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/core/D4TabAdjudication.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/core/d4-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/core/D4TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/core/D4TabAdjustment.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-completeness",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCompleteness.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCompleteness.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-contract",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabContract.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabContract.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-cutoff-backward",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffBackward.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffBackward.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-cutoff-forward",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffForward.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffForward.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-discount",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabDiscount.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabDiscount.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-erp-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabErpCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabErpCheck.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-export",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabExport.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabExport.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-return",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabReturn.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabReturn.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/inspection/d4-tab-voucher-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabVoucherCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabVoucherCheck.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-customer-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerChecklist.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerChecklist.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-customer-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerDetail.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerDetail.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-dealer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabDealer.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabDealer.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-fund-flow",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-interview-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewDetail.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewDetail.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-interview-summary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-invoice-compare",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInvoiceCompare.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInvoiceCompare.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-ipo-indicator",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabIpoIndicator.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabIpoIndicator.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-overseas",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabOverseas.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabOverseas.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-third-party",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabThirdParty.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabThirdParty.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/ipo/d4-tab-undisclosed-rp",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabUndisclosedRp.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabUndisclosedRp.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/other/d4-tab-other-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCheck.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/other/d4-tab-other-contract",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherContract.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherContract.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/other/d4-tab-other-cutoff",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCutoff.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCutoff.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/other/d4-tab-other-margin",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherMargin.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherMargin.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/policy/d4-tab-policy-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/policy/D4TabPolicyCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/policy/D4TabPolicyCheck.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/d4/related/d4-tab-related-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/related/D4TabRelatedPrice.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/related/D4TabRelatedPrice.vue",
      "wp_code_patterns": [
        "D4T"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a101-governance-communication",
    "entryId": "xlsx/gt-a101-governance-communication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA101GovernanceCommunication.ts#L247"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue",
      "wp_code_patterns": [
        "A101G"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a111-subsequent-events-inquiry",
    "entryId": "xlsx/gt-a111-subsequent-events-inquiry",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA111SubsequentEventsInquiry.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA111SubsequentEvents.ts#L109",
      "audit-platform/frontend/src/components/workpaper/composables/useA111SubsequentEvents.ts#L191"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA111SubsequentEventsInquiry.vue",
      "wp_code_patterns": [
        "A111S"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a112-dual-checklist",
    "entryId": "xlsx/gt-a112-dual-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L568",
      "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L624",
      "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L638"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"A1-12\""
      ],
      "sheet_literals": [
        "A1-12"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue",
      "wp_code_patterns": [
        "A1-12",
        "A112D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a115-disclosure-checklist",
    "entryId": "xlsx/gt-a115-disclosure-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA115DisclosureChecklist.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA115Checklist.ts#L113",
      "audit-platform/frontend/src/components/workpaper/composables/useA115Checklist.ts#L175",
      "audit-platform/frontend/src/components/workpaper/composables/useA115Checklist.ts#L269"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"A1-15\""
      ],
      "sheet_literals": [
        "A1-15"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA115DisclosureChecklist.vue",
      "wp_code_patterns": [
        "A1-15",
        "A115D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a121-legal-confirmation",
    "entryId": "xlsx/gt-a121-legal-confirmation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA121LegalConfirmation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA121LegalConfirmation.ts#L360"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA121LegalConfirmation.vue",
      "wp_code_patterns": [
        "A121L"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a171-audit-summary",
    "entryId": "xlsx/gt-a171-audit-summary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue#L541",
      "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue#L555",
      "audit-platform/frontend/src/components/workpaper/GtA171Chapter15.vue#L238",
      "audit-platform/frontend/src/components/workpaper/GtA171Chapter15.vue#L246"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue",
      "wp_code_patterns": [
        "A171A"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a1721-kam",
    "entryId": "xlsx/gt-a1721-kam",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA1721Kam.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA1721Kam.vue#L411",
      "audit-platform/frontend/src/components/workpaper/composables/useA1721Kam.ts#L338"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA1721Kam.vue",
      "wp_code_patterns": [
        "A1721K"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a173-consultation-record",
    "entryId": "xlsx/gt-a173-consultation-record",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA173ConsultationRecord.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA173ConsultationRecord.ts#L109",
      "audit-platform/frontend/src/components/workpaper/composables/useA173ConsultationRecord.ts#L204"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA173ConsultationRecord.vue",
      "wp_code_patterns": [
        "A173C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a1731-consultation-execution",
    "entryId": "xlsx/gt-a1731-consultation-execution",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA1731ConsultationExecution.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA1731ConsultationExecution.ts#L107",
      "audit-platform/frontend/src/components/workpaper/composables/useA1731ConsultationExecution.ts#L175"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA1731ConsultationExecution.vue",
      "wp_code_patterns": [
        "A1731C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a174-disagreement-record",
    "entryId": "xlsx/gt-a174-disagreement-record",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA174DisagreementRecord.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA174DisagreementRecord.ts#L120",
      "audit-platform/frontend/src/components/workpaper/composables/useA174DisagreementRecord.ts#L235"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA174DisagreementRecord.vue",
      "wp_code_patterns": [
        "A174D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a176-closing-meeting",
    "entryId": "xlsx/gt-a176-closing-meeting",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue#L208",
      "audit-platform/frontend/src/components/workpaper/composables/useA176ClosingMeeting.ts#L142",
      "audit-platform/frontend/src/components/workpaper/composables/useA176ClosingMeeting.ts#L99"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue",
      "wp_code_patterns": [
        "A176C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a177-independence-declaration",
    "entryId": "xlsx/gt-a177-independence-declaration",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue#L463",
      "audit-platform/frontend/src/components/workpaper/composables/useA177IndependenceDeclaration.ts#L101",
      "audit-platform/frontend/src/components/workpaper/composables/useA177IndependenceDeclaration.ts#L127"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue",
      "wp_code_patterns": [
        "A177I"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a181-regulatory-submission",
    "entryId": "xlsx/gt-a181-regulatory-submission",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA181RegulatorySubmission.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA181RegulatorySubmission.ts#L54",
      "audit-platform/frontend/src/components/workpaper/composables/useA181RegulatorySubmission.ts#L92"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA181RegulatorySubmission.vue",
      "wp_code_patterns": [
        "A181R"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a182-regulatory-communication",
    "entryId": "xlsx/gt-a182-regulatory-communication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA182RegulatoryCommunication.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA182RegulatoryCommunication.ts#L137",
      "audit-platform/frontend/src/components/workpaper/composables/useA182RegulatoryCommunication.ts#L74"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA182RegulatoryCommunication.vue",
      "wp_code_patterns": [
        "A182R"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a271-it-audit-memo",
    "entryId": "xlsx/gt-a271-it-audit-memo",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA271ItAuditMemo.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA271ItAuditMemo.ts#L283"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA271ItAuditMemo.vue",
      "wp_code_patterns": [
        "A271I"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-10",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a3-consolidation-console",
    "entryId": "xlsx/gt-a3-consolidation-console",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue#L362",
      "audit-platform/frontend/src/components/workpaper/composables/useA38Goodwill.ts#L212",
      "audit-platform/frontend/src/components/workpaper/composables/useA38Goodwill.ts#L239"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue",
      "wp_code_patterns": [
        "A3C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-6",
      "BP-7"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a38-goodwill-impairment",
    "entryId": "xlsx/gt-a38-goodwill-impairment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA38GoodwillImpairment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA38Goodwill.ts#L212",
      "audit-platform/frontend/src/components/workpaper/composables/useA38Goodwill.ts#L239"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"A3-8\""
      ],
      "sheet_literals": [
        "A3-8"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA38GoodwillImpairment.vue",
      "wp_code_patterns": [
        "A3-8",
        "A38G"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a51-cashflow-audit",
    "entryId": "xlsx/gt-a51-cashflow-audit",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA51CashflowAudit.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA51CashflowAudit.ts#L344",
      "audit-platform/frontend/src/components/workpaper/composables/useA51CashflowAudit.ts#L394"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA51CashflowAudit.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "A5-1"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a81-other-info-representation",
    "entryId": "xlsx/gt-a81-other-info-representation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA81OtherInfoRepresentation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA81OtherInfoRepresentation.ts#L190",
      "audit-platform/frontend/src/components/workpaper/composables/useA81OtherInfoRepresentation.ts#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA81OtherInfoRepresentation.vue",
      "wp_code_patterns": [
        "A81O"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-11",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-a91-deficiency-letter",
    "entryId": "xlsx/gt-a91-deficiency-letter",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA91DeficiencyLetter.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useA91DeficiencyLetter.ts#L270",
      "audit-platform/frontend/src/components/workpaper/composables/useA91DeficiencyLetter.ts#L297"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA91DeficiencyLetter.vue",
      "wp_code_patterns": [
        "A91D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b1-evaluation",
    "entryId": "xlsx/gt-b1-evaluation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1Evaluation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB1Evaluation.ts#L101",
      "audit-platform/frontend/src/components/workpaper/composables/useB1Evaluation.ts#L193",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sourceSheet || '业务评价表B1-3'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB1Evaluation.vue",
      "wp_code_patterns": [
        "B1E"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b1-kaa-check",
    "entryId": "xlsx/gt-b1-kaa-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1KaaCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB1KaaCheck.ts#L167",
      "audit-platform/frontend/src/components/workpaper/composables/useB1KaaCheck.ts#L84",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sourceSheet || ' B1-5 KAA检查表-业务承接'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB1KaaCheck.vue",
      "wp_code_patterns": [
        "B1K"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b1-risk-assessment",
    "entryId": "xlsx/gt-b1-risk-assessment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1RiskAssessment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB1RiskAssessment.ts#L145",
      "audit-platform/frontend/src/components/workpaper/composables/useB1RiskAssessment.ts#L261",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB1RiskAssessment.vue",
      "wp_code_patterns": [
        "B1R"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b14-due-diligence-report",
    "entryId": "xlsx/gt-b14-due-diligence-report",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB14DueDiligenceReport.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB14DueDiligence.ts#L230",
      "audit-platform/frontend/src/components/workpaper/composables/useB14DueDiligence.ts#L383",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sourceSheet || '尽职调查报告B1-4'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB14DueDiligenceReport.vue",
      "wp_code_patterns": [
        "B14D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b22-a-control-matrix",
    "entryId": "xlsx/gt-b22-a-control-matrix",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22AControlMatrix.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB22AFormData.ts#L106",
      "audit-platform/frontend/src/components/workpaper/composables/useB22AFormData.ts#L52"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.wpCode || 'B22A'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB22AControlMatrix.vue",
      "wp_code_patterns": [
        "B22A"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b22-b-control-matrix",
    "entryId": "xlsx/gt-b22-b-control-matrix",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22BControlMatrix.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L160",
      "audit-platform/frontend/src/components/workpaper/composables/useB22BControlMatrix.ts#L197"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.wpCode || 'B22B'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB22BControlMatrix.vue",
      "wp_code_patterns": [
        "B22B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b22-b-deficiency-evaluation",
    "entryId": "xlsx/gt-b22-b-deficiency-evaluation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue#L386",
      "audit-platform/frontend/src/components/workpaper/composables/useB22AFormData.ts#L106"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.wpCode || 'B22B'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue",
      "wp_code_patterns": [
        "B22B"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b22-c-design-effectiveness",
    "entryId": "xlsx/gt-b22-c-design-effectiveness",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue#L198",
      "audit-platform/frontend/src/components/workpaper/composables/useB22CDesignEffectiveness.ts#L282"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.wpCode || 'B22C'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue",
      "wp_code_patterns": [
        "B22C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b23-process-control",
    "entryId": "xlsx/gt-b23-process-control",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB23ProcessControl.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/AuditLegendPanel.vue#L132",
      "audit-platform/frontend/src/components/workpaper/AuditLegendPanel.vue#L146",
      "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue#L133",
      "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L568",
      "audit-platform/frontend/src/components/workpaper/GtA117CorrespondingData.vue#L174",
      "audit-platform/frontend/src/components/workpaper/GtA117CorrespondingData.vue#L210",
      "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue#L541",
      "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue#L208"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"currentCard.name\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB23ProcessControl.vue",
      "wp_code_patterns": [
        "B23P"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-b50-risk-assessment",
    "entryId": "xlsx/gt-b50-risk-assessment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1174",
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1472",
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L906",
      "audit-platform/frontend/src/components/workpaper/WpPopupChecklist.vue#L123",
      "audit-platform/frontend/src/components/workpaper/WpPopupChecklist.vue#L75",
      "audit-platform/frontend/src/composables/useAProgramPopups.ts#L252"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue",
      "wp_code_patterns": [
        "B50R"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-c-control-test",
    "entryId": "xlsx/gt-c-control-test",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtCControlTest.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtCControlTest.vue#L604",
      "audit-platform/frontend/src/components/workpaper/cControlTest/CControlTestSubPage.vue#L616",
      "audit-platform/frontend/src/components/workpaper/cControlTest/CControlTestSubPage.vue#L796",
      "audit-platform/frontend/src/components/workpaper/composables/useCControlTestData.ts#L44"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtCControlTest.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "C2"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-10",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-c22-itgc-bundle",
    "entryId": "xlsx/gt-c22-itgc-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtC21FindingsSummary.vue#L106",
      "audit-platform/frontend/src/components/workpaper/GtC21FindingsSummary.vue#L171",
      "audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue#L108",
      "audit-platform/frontend/src/components/workpaper/composables/useC22BundleState.ts#L526"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"activeDocTab.ooSheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue",
      "wp_code_patterns": [
        "C22I"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-custom-wp-editor",
    "entryId": "xlsx/gt-custom-wp-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/custom/GtCustomGridSheet.vue#L417",
      "audit-platform/frontend/src/services/apiPaths/workpaper.ts#L36",
      "audit-platform/frontend/src/services/apiPaths/workpaper.ts#L54"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_candidate",
    "parentEntryId": null,
    "reasonCodes": [
      "no_durable_forcesave_ack",
      "missing_unified_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d1-notes-receivable",
    "entryId": "xlsx/gt-d1-notes-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD1NotesReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD1NotesReceivable.vue#L27",
      "audit-platform/frontend/src/components/workpaper/composables/useD1FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD1DetailCustomer.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d1_notes_receivable.py",
      "backend/wp_templates/D/D1 应收票据.xlsx!原值明细表（按客户）D1-3!A10 = '客户名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD1NotesReceivable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d2-accounts-receivable",
    "entryId": "xlsx/gt-d2-accounts-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue#L76",
      "audit-platform/frontend/src/components/workpaper/composables/useD2FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD2Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d2_accounts_receivable.py",
      "backend/wp_templates/D/D2-1至D2-4  应收账款- 审定表明细表（Leap-常规程序）.xlsx!明细表D2-2!B11 = '客户名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D2"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "dedicated_host_binding",
      "runtime_representation_and_evidence"
    ],
    "capabilityVerdictStage": "host_binding_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d2-inspection",
    "entryId": "xlsx/gt-d2-inspection",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "provider_ready_host_pending",
    "parentEntryId": null,
    "reasonCodes": [
      "dedicated_host_binding_missing",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.none.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
      "wp_code_patterns": [
        "D2-6",
        "D2-7",
        "D2-9",
        "D2-10",
        "D2-11",
        "D2-12",
        "D2-13"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-3",
      "BP-4",
      "BP-5"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d3-prepaid-accounts",
    "entryId": "xlsx/gt-d3-prepaid-accounts",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue#L13",
      "audit-platform/frontend/src/components/workpaper/composables/useD3FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD3Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d3_prepaid_accounts.py",
      "backend/wp_templates/D/D3 预收账款.xlsx!预收账款明细表D3-2!A10 = '对方单位名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D3"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d4-operating-revenue",
    "entryId": "xlsx/gt-d4-operating-revenue",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue#L15",
      "audit-platform/frontend/src/components/workpaper/composables/useD4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD4Adjustment.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d4_operating_revenue.py",
      "backend/wp_templates/D/D4-1至D4-4 营业收入 - 审定表明细表（Leap-常规程序）.xlsx!营业收入调整分录汇总D4-4!A5 = '调整事项说明'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D4"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-3",
      "BP-4",
      "BP-5"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d5-receivables-financing",
    "entryId": "xlsx/gt-d5-receivables-financing",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD5ReceivablesFinancing.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD5ReceivablesFinancing.vue#L13",
      "audit-platform/frontend/src/components/workpaper/composables/useD5FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD5Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d5_receivables_financing.py",
      "backend/wp_templates/D/D5 应收款项融资.xlsx!应收款项融资明细表D5-2!B10 = '明细项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD5ReceivablesFinancing.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D5"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-3",
      "BP-4",
      "BP-5"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d6-contract-assets",
    "entryId": "xlsx/gt-d6-contract-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD6ContractAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD6ContractAssets.vue#L13",
      "audit-platform/frontend/src/components/workpaper/composables/useD6FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD6Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d6_contract_assets.py",
      "backend/wp_templates/D/D6 合同资产.xlsx!明细表D6-2!B12 = '合同名称/项目名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD6ContractAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D6"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-3",
      "BP-4",
      "BP-5"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-d7-contract-liabilities",
    "entryId": "xlsx/gt-d7-contract-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD7ContractLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtD7ContractLiabilities.vue#L13",
      "audit-platform/frontend/src/components/workpaper/composables/useD7FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useD7Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_d7_contract_liabilities.py",
      "backend/wp_templates/D/D7 合同负债.xlsx!明细表D7-2!A8 = '合同名称/项目名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD7ContractLiabilities.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "D7"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "counterpart_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-e1-monetary-fund",
    "entryId": "xlsx/gt-e1-monetary-fund",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "E1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f1-prepayment",
    "entryId": "xlsx/gt-f1-prepayment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue#L19",
      "audit-platform/frontend/src/components/workpaper/composables/useF1FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF1Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f1_prepayment.py",
      "backend/wp_templates/F/F1 预付账款.xlsx!明细表F1-2!A12 = '债权人名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f2-inventory-main",
    "entryId": "xlsx/gt-f2-inventory-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue#L16",
      "audit-platform/frontend/src/components/workpaper/composables/useF2FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2DetailSheet.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2DetailSummary.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f2_inventory_main.py",
      "backend/wp_templates/F/F2-1至F2-14 存货及跌价准备-审定明细表类（Leap-常规程序）.xlsx!一、原材料明细表F2-3!A6 = '存货编码'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f2-inventory-special",
    "entryId": "xlsx/gt-f2-inventory-special",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventorySpecial.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF2InventorySpecial.vue#L26",
      "audit-platform/frontend/src/components/workpaper/composables/useF2SpecialFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2ContractCost.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2ContractCostFormulas.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f2_inventory_special.py",
      "backend/wp_templates/F/F2-55至F2-58 合同履约成本.xlsx!合同履约成本构成明细表F2-55!A5 = '项目编码'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventorySpecial.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f2-inventory-valuation",
    "entryId": "xlsx/gt-f2-inventory-valuation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventoryValuation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF2InventoryValuation.vue#L16",
      "audit-platform/frontend/src/components/workpaper/composables/useF2ValuationFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2ImpairmentTest.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2ImpairmentTestFormulas.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f2_inventory_valuation_impairment.py",
      "backend/wp_templates/F/F2-47至F2-49 存货及跌价准备 -跌价准备测试（Leap应对措施-会计估计）.xlsx!跌价准备测试表F2-47!A18 = '存货类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventoryValuation.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f2-stocktake-bundle",
    "entryId": "xlsx/gt-f2-stocktake-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue#L23",
      "audit-platform/frontend/src/components/workpaper/composables/useF2StocktakeFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF2StocktakeQuestionnaire.ts",
      "audit-platform/frontend/src/components/workpaper/f2/stocktake/f2StocktakeQuestionnaire.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f2_stocktake.py",
      "backend/wp_templates/F/F2-21至F2-26 存货及跌价准备 - 盘点类（Leap应对措施- 存货监盘）.xlsx!盘点计划问卷F2-21!A7 = '地点'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || activeTab\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f3-notes-payable",
    "entryId": "xlsx/gt-f3-notes-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue#L39",
      "audit-platform/frontend/src/components/workpaper/composables/useF3FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF3Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f3_notes_payable.py",
      "backend/wp_templates/F/F3 应付票据.xlsx!明细表F3-2!A13 = '票据号'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F3"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f4-accounts-payable",
    "entryId": "xlsx/gt-f4-accounts-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue#L38",
      "audit-platform/frontend/src/components/workpaper/composables/useF4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF4Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f4_accounts_payable.py",
      "backend/wp_templates/F/F4 应付账款.xlsx!明细表F4-2!A9 = '债权人名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-f5-cost-of-sales",
    "entryId": "xlsx/gt-f5-cost-of-sales",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue#L29",
      "audit-platform/frontend/src/components/workpaper/composables/useF5CosSalFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF5MonthlyDetail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useF5Adjudication.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_f5_cost_of_sales.py",
      "backend/wp_templates/F/F5 营业成本.xlsx!主营业务成本月度明细表F5-2!A9 = '项目 月份'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "F5"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g1-trading-financial-assets",
    "entryId": "xlsx/gt-g1-trading-financial-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG1TraFinFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG1Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG1Detail.ts#L648",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G1 交易性金融资产.xlsx!明细表G1-2!A9 = '类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g10-trading-financial-liabilities",
    "entryId": "xlsx/gt-g10-trading-financial-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG10TradingFinancialLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG10TradingFinancialLiabilities.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG10FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG10Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG10Detail.ts#L382",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G10 交易性金融负债.xlsx!明细表G10-2!A9 = '类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG10TradingFinancialLiabilities.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G10"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g11-investment-income",
    "entryId": "xlsx/gt-g11-investment-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG11FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG11DetailAnalysis.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG11DetailAnalysis.ts#L233",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G11 投资收益.xlsx!明细分析表G11-2!B9 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G11"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g12-net-hedge-gains",
    "entryId": "xlsx/gt-g12-net-hedge-gains",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG12NetHedgeGains.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG12NetHedgeGains.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG12FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG12HedgeDetail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG12HedgeDetail.ts#L138",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G12 净敞口套期收益.xlsx!明细表G12-2!A7 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG12NetHedgeGains.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G12"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g13-fair-value-changes",
    "entryId": "xlsx/gt-g13-fair-value-changes",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG13FairValueChanges.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG13FairValueChanges.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG13FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG13Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG13Detail.ts#L212",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G13 公允价值变动收益.xlsx!明细表G13-2!A9 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG13FairValueChanges.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G13"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g14-credit-impairment-loss",
    "entryId": "xlsx/gt-g14-credit-impairment-loss",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG14FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG14Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG14Detail.ts#L195",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G14 信用减值损失.xlsx!明细表G14-2!A9 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G14"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g2-interest-receivable",
    "entryId": "xlsx/gt-g2-interest-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG2InterestReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG2InterestReceivable.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG2IntRecFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG2Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG2Detail.ts#L517",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G2 应收利息.xlsx!明细表G2-2!A9 = '投资种类'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG2InterestReceivable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g3-dividend-receivable",
    "entryId": "xlsx/gt-g3-dividend-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG3DividendReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG3DividendReceivable.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG3FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/g3Constants.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG3Detail.ts#L336",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G3 应收股利.xlsx!明细表G3-2!A9 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG3DividendReceivable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G3"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6",
      "BP-8"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g4-bond-investment-ecl",
    "entryId": "xlsx/gt-g4-bond-investment-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentEcl.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentEcl.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG4EclFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/g4CrossHelpers.ts",
      "audit-platform/frontend/src/components/workpaper/g4-bond-investment-ecl/impairment/G4TabStageClassification.vue#L505",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G4 债权投资.xlsx!债权投资三阶段划分G4-9!A9 = '需要考虑的信息'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentEcl.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g4-bond-investment-main",
    "entryId": "xlsx/gt-g4-bond-investment-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentMain.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentMain.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG4BonInvFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG4MainDetail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG4MainDetail.ts#L544",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G4 债权投资.xlsx!明细表G4-2!A9 = '投资种类'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentMain.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G4"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-8"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g4-bond-investment-sppi",
    "entryId": "xlsx/gt-g4-bond-investment-sppi",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentSppi.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentSppi.vue",
      "audit-platform/frontend/src/composables/useG4SppiFormData.ts",
      "audit-platform/frontend/src/composables/useG4SppiInventory.ts",
      "audit-platform/frontend/src/composables/useG4SppiInventory.ts#L305",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G4 债权投资.xlsx!有价证券盘点表G4-7!B13 = '证券名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentSppi.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g5-long-term-receivable",
    "entryId": "xlsx/gt-g5-long-term-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG5LonRecFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/g5StorageContract.ts",
      "audit-platform/frontend/src/components/workpaper/g5-long-term-receivable/core/G5TabBalanceDetail.vue#L292",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G5 长期应收款.xlsx!余额明细表G5-2!B10 = '债务人名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G5"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "unreachable",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "unreachable",
    "effectiveEntryId": "xlsx/gt-g6-other-bond-ecl",
    "entryId": "xlsx/gt-g6-other-bond-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondEcl.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": false,
    "migrationState": "unreachable_pending_delete",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "none",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.unreachable.none.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondEcl.vue",
      "wp_code_patterns": [
        "G6O"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6",
      "BP-8"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g6-other-bond-investment-ecl",
    "entryId": "xlsx/gt-g6-other-bond-investment-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondInvestmentEcl.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG6OtherBondInvestmentEcl.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG6EclFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/g6StorageContract.ts",
      "audit-platform/frontend/src/components/workpaper/g6-other-bond-investment-ecl/impairment/G6TabStageClassification.vue#L452",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G6 其他债权投资.xlsx!其他债权投资三阶段划分G6-11!A10 = '需要考虑的信息'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondInvestmentEcl.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G6"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g6-other-bond-main",
    "entryId": "xlsx/gt-g6-other-bond-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondMain.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG6OtherBondMain.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG6MainFormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG6MainDetail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG6MainDetail.ts#L453",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G6 其他债权投资.xlsx!明细表G6-2!A9 = '投资种类'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondMain.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G6"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g6-other-bond-sppi",
    "entryId": "xlsx/gt-g6-other-bond-sppi",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondSppi.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG6OtherBondSppi.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG6SppiFormData.ts",
      "audit-platform/frontend/src/components/workpaper/g6-other-bond-investment-sppi/fair-value/G6TabFairValueTest.vue",
      "audit-platform/frontend/src/components/workpaper/g6-other-bond-investment-sppi/fair-value/G6TabFairValueTest.vue#L615",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G6 其他债权投资.xlsx!公允价值测试表G6-5!A7 = '投资项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondSppi.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G6"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "counterpart_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g7-equity-method",
    "entryId": "xlsx/gt-g7-equity-method",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7EquityMethod.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG7EquityMethod.vue",
      "wp_code_patterns": [
        "G7E"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "single_onlyoffice",
    "capabilityTargetBlockedBy": [
      "html_counterpart_investigation"
    ],
    "capabilityVerdictStage": "counterpart_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g7-equity-subsidiary",
    "entryId": "xlsx/gt-g7-equity-subsidiary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7EquitySubsidiary.vue",
    "htmlCounterpartSourceRefs": [],
    "htmlCounterpartVerdict": null,
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG7EquitySubsidiary.vue",
      "wp_code_patterns": [
        "G7E"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g7-long-term-equity-main",
    "entryId": "xlsx/gt-g7-long-term-equity-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G7"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g8-other-equity-instruments",
    "entryId": "xlsx/gt-g8-other-equity-instruments",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG8OtherEquityInstruments.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG8OtherEquityInstruments.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG8FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG8Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG8Detail.ts#L400",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G8 其他权益工具投资.xlsx!明细表G8-2!A9 = '被投资单位名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG8OtherEquityInstruments.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G8"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-g9-other-noncurrent-financial",
    "entryId": "xlsx/gt-g9-other-noncurrent-financial",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue",
      "audit-platform/frontend/src/components/workpaper/composables/useG9FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG9Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useG9Detail.ts#L323",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/wp_templates/G/G9 其他非流动金融资产.xlsx!明细表G9-2!A9 = '类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "G9"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h1-fixed-assets",
    "entryId": "xlsx/gt-h1-fixed-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h10-asset-disposal-income",
    "entryId": "xlsx/gt-h10-asset-disposal-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH10AssetDisposalIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH10AssetDisposalIncome.vue#L150",
      "audit-platform/frontend/src/components/workpaper/composables/useH10FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH10Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h10_asset_disposal_income.py",
      "backend/wp_templates/H/H10 资产处置损益.xlsx!明细表H10-2!A7 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH10AssetDisposalIncome.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H10"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h2-construction-in-progress",
    "entryId": "xlsx/gt-h2-construction-in-progress",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue#L313",
      "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue#L522",
      "audit-platform/frontend/src/components/workpaper/composables/useH2Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h2_construction_in_progress.py",
      "backend/wp_templates/H/H2 在建工程.xlsx!明细表H2-2!A9 = '工程项目名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H2"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h3-investment-property",
    "entryId": "xlsx/gt-h3-investment-property",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH3InvestmentProperty.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH3InvestmentProperty.vue#L322",
      "audit-platform/frontend/src/components/workpaper/composables/useH3FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH3DetailCost.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH3MeasurementModel.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h3_investment_property.py",
      "backend/wp_templates/H/H3 投资性房地产.xlsx!明细表（成本模式）H3-2!A9 = '投资性房地产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH3InvestmentProperty.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H3"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h4-engineering-materials",
    "entryId": "xlsx/gt-h4-engineering-materials",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue#L212",
      "audit-platform/frontend/src/components/workpaper/composables/useH4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH4Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h4DetailPrefill.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h4_engineering_materials.py",
      "backend/wp_templates/H/H4 工程物资.xlsx!明细表H4-2!A8 = '序号'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h5-oil-gas-assets",
    "entryId": "xlsx/gt-h5-oil-gas-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue#L305",
      "audit-platform/frontend/src/components/workpaper/composables/useH5FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH5Detail.ts",
      "audit-platform/frontend/src/components/workpaper/h5/core/H5TabDetail.vue",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h5_oil_gas_assets.py",
      "backend/wp_templates/H/H5 油气资产.xlsx!明细表H5-2!A9 = '油气资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H5"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h6-asset-disposal-clearing",
    "entryId": "xlsx/gt-h6-asset-disposal-clearing",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue#L167",
      "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue#L242",
      "audit-platform/frontend/src/components/workpaper/composables/useH6Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h6_asset_disposal_clearing.py",
      "backend/wp_templates/H/H6 固定资产清理.xlsx!明细表H6-2!A9 = '项目'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H6"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h7-biological-assets",
    "entryId": "xlsx/gt-h7-biological-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue#L372",
      "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue#L599",
      "audit-platform/frontend/src/components/workpaper/h7/core/H7TabDetailCost.vue#L250",
      "audit-platform/frontend/src/components/workpaper/h7/core/H7TabDetailCost.vue#L268",
      "audit-platform/frontend/src/components/workpaper/composables/h7ListedDisclosureModel.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h7_biological_assets.py",
      "backend/wp_templates/H/H7 生产性生物资产.xlsx!明细表（成本模式）H7-2!A9 = '生产性生物资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H7"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h8-right-of-use-assets",
    "entryId": "xlsx/gt-h8-right-of-use-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L341",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L535",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L629",
      "audit-platform/frontend/src/components/workpaper/composables/useH8Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h8DisclosureSyncPayload.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h8_right_of_use_assets.py",
      "backend/wp_templates/H/H8 使用权资产.xlsx!明细表H8-2!A8 = '使用权资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H8"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-8"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h9-lease-liabilities",
    "entryId": "xlsx/gt-h9-lease-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue#L198",
      "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue#L329",
      "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue#L394",
      "audit-platform/frontend/src/components/workpaper/composables/useH9Detail.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h9_lease_liabilities.py",
      "backend/wp_templates/H/H9 租赁负债.xlsx!租赁负债明细表H9-2!A7 = '出租方名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "H9"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6",
      "BP-7"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i1-intangible-assets",
    "entryId": "xlsx/gt-i1-intangible-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue#L271",
      "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue#L380",
      "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue#L418",
      "audit-platform/frontend/src/components/workpaper/composables/useI1Detail.ts#L164",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i1_intangible_assets.py",
      "backend/wp_templates/I/I1 无形资产、累计摊销及减值准备.xlsx!明细表I1-2!A8 = '无形资产项目'",
      "backend/wp_templates/I/I1 无形资产、累计摊销及减值准备.xlsx!底稿目录!A9 = '土地使用权'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i2-development-expenditure",
    "entryId": "xlsx/gt-i2-development-expenditure",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue#L371",
      "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue#L486",
      "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue#L496",
      "audit-platform/frontend/src/components/workpaper/composables/useI2Detail.ts#L145",
      "audit-platform/frontend/src/components/workpaper/composables/useI2FormData.ts#L185",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i2_development_expenditure.py",
      "backend/wp_templates/I/I2 开发支出.xlsx!明细表I2-2!A10 = '研究开发项目名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I2"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i3-goodwill",
    "entryId": "xlsx/gt-i3-goodwill",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue#L220",
      "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue#L319",
      "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue#L355",
      "audit-platform/frontend/src/components/workpaper/composables/useI3Detail.ts#L186",
      "audit-platform/frontend/src/components/workpaper/composables/useI3Disclosure.ts#L487",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i3_goodwill.py",
      "backend/wp_templates/I/I3 商誉.xlsx!明细表I3-2!A10 = '被投资单位名称或形成商誉的事项'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I3"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i4-long-term-prepaid",
    "entryId": "xlsx/gt-i4-long-term-prepaid",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue#L199",
      "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue#L296",
      "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue#L338",
      "audit-platform/frontend/src/components/workpaper/composables/useI4Detail.ts#L180",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i4_long_term_prepaid.py",
      "backend/wp_templates/I/I4 长期待摊费用.xlsx!明细表I4-2!A8 = '项目名称'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I4"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4"
    ],
    "capabilityVerdictStage": "pipeline_entry_pending_definition_delivery",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i5-other-noncurrent-assets",
    "entryId": "xlsx/gt-i5-other-noncurrent-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI5OtherNoncurrentAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useI5FormData.ts#L109",
      "audit-platform/frontend/src/components/workpaper/composables/useI5FormData.ts#L280",
      "audit-platform/frontend/src/components/workpaper/composables/useI5Detail.ts#L180",
      "audit-platform/frontend/src/components/workpaper/composables/useI5Detail.ts#L185",
      "audit-platform/frontend/src/components/workpaper/GtI5OtherNoncurrentAssets.vue#L161",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i5_other_noncurrent_assets.py",
      "backend/wp_templates/I/I5 其他非流动资产.xlsx!明细表I5-2!A8 = '项目'",
      "backend/wp_templates/I/I5 其他非流动资产.xlsx!明细表I5-2!A11 = '预付土地出让金'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI5OtherNoncurrentAssets.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I5"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-i6-research-development-expense",
    "entryId": "xlsx/gt-i6-research-development-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue#L190",
      "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue#L292",
      "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue#L311",
      "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue#L350",
      "audit-platform/frontend/src/components/workpaper/composables/useI6Detail.ts#L152",
      "audit-platform/frontend/src/components/workpaper/composables/useI6Detail.ts#L163",
      "backend/app/routers/checklist_responses.py",
      "backend/app/routers/wp_render_strategies/_i6_research_development_expense.py",
      "backend/wp_templates/I/I6 研发费用.xlsx!明细表I6-2!A8 = '类别'",
      "backend/wp_templates/I/I6 研发费用.xlsx!明细表I6-2!A9 = '人工费'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "I6"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k1-other-receivables",
    "entryId": "xlsx/gt-k1-other-receivables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue#L9",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K1"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-9"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k10-other-income",
    "entryId": "xlsx/gt-k10-other-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK10OtherIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK10OtherIncome.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK10OtherIncome.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K10"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k11-asset-impairment-loss",
    "entryId": "xlsx/gt-k11-asset-impairment-loss",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K11"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k12-non-operating-income",
    "entryId": "xlsx/gt-k12-non-operating-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K12"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k13-non-operating-expense",
    "entryId": "xlsx/gt-k13-non-operating-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K13"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k2-other-current-assets",
    "entryId": "xlsx/gt-k2-other-current-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK2OtherCurrentAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK2OtherCurrentAssets.vue#L9",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK2OtherCurrentAssets.vue",
      "wp_code_patterns": [
        "K2O"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k3-other-payables",
    "entryId": "xlsx/gt-k3-other-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK3OtherPayables.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK3OtherPayables.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK3OtherPayables.vue",
      "wp_code_patterns": [
        "K3O"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k4-other-current-liabilities",
    "entryId": "xlsx/gt-k4-other-current-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK4OtherCurrentLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK4OtherCurrentLiabilities.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK4OtherCurrentLiabilities.vue",
      "wp_code_patterns": [
        "K4O"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k5-provisions",
    "entryId": "xlsx/gt-k5-provisions",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK5Provisions.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK5Provisions.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK5Provisions.vue",
      "wp_code_patterns": [
        "K5P"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k6-held-for-sale",
    "entryId": "xlsx/gt-k6-held-for-sale",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK6HeldForSale.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK6HeldForSale.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK6HeldForSale.vue",
      "wp_code_patterns": [
        "K6H"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k7-deferred-income",
    "entryId": "xlsx/gt-k7-deferred-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK7DeferredIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK7DeferredIncome.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK7DeferredIncome.vue",
      "wp_code_patterns": [
        "K7D"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k8-selling-expenses",
    "entryId": "xlsx/gt-k8-selling-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K8"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k9-admin-expenses",
    "entryId": "xlsx/gt-k9-admin-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "K9"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l1-short-term-loans",
    "entryId": "xlsx/gt-l1-short-term-loans",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL1ShortTermLoans.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/composables/useL1FormData.ts#L282",
      "audit-platform/frontend/src/composables/useL1FormData.ts#L467",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L1A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL1ShortTermLoans.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l2-interest-payable",
    "entryId": "xlsx/gt-l2-interest-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL2InterestPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL2FormData.ts#L81",
      "audit-platform/frontend/src/components/workpaper/composables/useL2FormData.ts#L116",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L2A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL2InterestPayable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l3-long-term-loans",
    "entryId": "xlsx/gt-l3-long-term-loans",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL3FormData.ts#L86",
      "audit-platform/frontend/src/components/workpaper/composables/useL3FormData.ts#L121",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L3A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L3"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l4-bonds-payable",
    "entryId": "xlsx/gt-l4-bonds-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL4BondsPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL4FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useL4FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L4A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL4BondsPayable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l5-long-term-payables",
    "entryId": "xlsx/gt-l5-long-term-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL5LongTermPayables.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL5FormData.ts#L96",
      "audit-platform/frontend/src/components/workpaper/composables/useL5FormData.ts#L131",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L5A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL5LongTermPayables.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L5"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l6-special-payables",
    "entryId": "xlsx/gt-l6-special-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL6SpecialPayables.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL6FormData.ts#L90",
      "audit-platform/frontend/src/components/workpaper/composables/useL6FormData.ts#L127",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L6A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL6SpecialPayables.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L6"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l7-other-noncurrent-liabilities",
    "entryId": "xlsx/gt-l7-other-noncurrent-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL7FormData.ts#L89",
      "audit-platform/frontend/src/components/workpaper/composables/useL7FormData.ts#L124",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L7A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L7"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-l8-financial-expenses",
    "entryId": "xlsx/gt-l8-financial-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL8FinancialExpenses.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useL8FormData.ts#L108",
      "audit-platform/frontend/src/components/workpaper/composables/useL8FormData.ts#L183",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || 'L8A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL8FinancialExpenses.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "L8"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m1-dividends-payable",
    "entryId": "xlsx/gt-m1-dividends-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM1DividendsPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM1FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useM1FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM1FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useM1FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM1DividendsPayable.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M1"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m10-other-equity-instruments",
    "entryId": "xlsx/gt-m10-other-equity-instruments",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM10OtherEquityInstruments.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM10FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useM10FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM10FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useM10FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM10OtherEquityInstruments.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M10"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m2-paid-in-capital",
    "entryId": "xlsx/gt-m2-paid-in-capital",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM2PaidInCapital.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM2FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useM2FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM2FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useM2FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM2PaidInCapital.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M2"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m3-treasury-stock",
    "entryId": "xlsx/gt-m3-treasury-stock",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM3TreasuryStock.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM3FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useM3FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM3FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useM3FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM3TreasuryStock.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M3"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m4-capital-reserve",
    "entryId": "xlsx/gt-m4-capital-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM4CapitalReserve.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM4FormData.ts#L45",
      "audit-platform/frontend/src/components/workpaper/composables/useM4FormData.ts#L93",
      "audit-platform/frontend/src/components/workpaper/composables/useM4FormData.ts#L89",
      "audit-platform/frontend/src/components/workpaper/composables/useM4FormData.ts#L124",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM4CapitalReserve.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M4"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m5-surplus-reserve",
    "entryId": "xlsx/gt-m5-surplus-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM5SurplusReserve.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM5FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useM5FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM5FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useM5FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM5SurplusReserve.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M5"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-5",
      "BP-7",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m6-retained-earnings",
    "entryId": "xlsx/gt-m6-retained-earnings",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM6RetainedEarnings.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM6FormData.ts#L48",
      "audit-platform/frontend/src/components/workpaper/composables/useM6FormData.ts#L96",
      "audit-platform/frontend/src/components/workpaper/composables/useM6FormData.ts#L92",
      "audit-platform/frontend/src/components/workpaper/composables/useM6FormData.ts#L127",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM6RetainedEarnings.vue",
      "wp_code_patterns": [
        "M6R"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m7-special-reserve",
    "entryId": "xlsx/gt-m7-special-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": true,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM7SpecialReserve.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM7FormData.ts#L46",
      "audit-platform/frontend/src/components/workpaper/composables/useM7FormData.ts#L94",
      "audit-platform/frontend/src/components/workpaper/composables/useM7FormData.ts#L90",
      "audit-platform/frontend/src/components/workpaper/composables/useM7FormData.ts#L127",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [
      "real_onlyoffice_acceptance_pending"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM7SpecialReserve.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M7"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m8-general-risk-reserve",
    "entryId": "xlsx/gt-m8-general-risk-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM8GeneralRiskReserve.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM8FormData.ts#L59",
      "audit-platform/frontend/src/components/workpaper/composables/useM8FormData.ts#L126",
      "audit-platform/frontend/src/components/workpaper/composables/useM8FormData.ts#L122",
      "audit-platform/frontend/src/components/workpaper/composables/useM8FormData.ts#L159",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM8GeneralRiskReserve.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M8"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-m9-other-comprehensive-income",
    "entryId": "xlsx/gt-m9-other-comprehensive-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM9OtherComprehensiveIncome.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useM9FormData.ts#L47",
      "audit-platform/frontend/src/components/workpaper/composables/useM9FormData.ts#L95",
      "audit-platform/frontend/src/components/workpaper/composables/useM9FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useM9FormData.ts#L128",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM9OtherComprehensiveIncome.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "M9"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "entryId": "xlsx/gt-n1-deferred-tax-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN1DeferredTaxAssets.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L61",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L231",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L235",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L317",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN1DeferredTaxAssets.vue",
      "wp_code_patterns": [
        "N1D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-11"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n2-taxes-payable",
    "entryId": "xlsx/gt-n2-taxes-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN2TaxesPayable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN2FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useN2FormData.ts#L87",
      "audit-platform/frontend/src/components/workpaper/composables/useN2FormData.ts#L91",
      "audit-platform/frontend/src/components/workpaper/composables/useN2FormData.ts#L122",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN2TaxesPayable.vue",
      "wp_code_patterns": [
        "N2T"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6",
      "BP-7",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n3-deferred-tax-liabilities",
    "entryId": "xlsx/gt-n3-deferred-tax-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN3DeferredTaxLiabilities.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN3FormData.ts#L43",
      "audit-platform/frontend/src/components/workpaper/composables/useN3FormData.ts#L102",
      "audit-platform/frontend/src/components/workpaper/composables/useN3FormData.ts#L106",
      "audit-platform/frontend/src/components/workpaper/composables/useN3FormData.ts#L137",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN3DeferredTaxLiabilities.vue",
      "wp_code_patterns": [
        "N3D"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n4-taxes-and-surcharges",
    "entryId": "xlsx/gt-n4-taxes-and-surcharges",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN4TaxesAndSurcharges.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN4FormData.ts#L63",
      "audit-platform/frontend/src/components/workpaper/composables/useN4FormData.ts#L262",
      "audit-platform/frontend/src/components/workpaper/composables/useN4FormData.ts#L265",
      "audit-platform/frontend/src/components/workpaper/composables/useN4FormData.ts#L127",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN4TaxesAndSurcharges.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "N4"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-5",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-11",
      "BP-12"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n5-income-tax-expense",
    "entryId": "xlsx/gt-n5-income-tax-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN5IncomeTaxExpense.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN5FormData.ts#L60",
      "audit-platform/frontend/src/components/workpaper/composables/useN5FormData.ts#L107",
      "audit-platform/frontend/src/components/workpaper/composables/useN5FormData.ts#L111",
      "audit-platform/frontend/src/components/workpaper/composables/useN5FormData.ts#L182",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN5IncomeTaxExpense.vue",
      "wp_code_patterns": [
        "N5I"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-10",
      "BP-12",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-wp-renderer",
    "entryId": "xlsx/gt-wp-renderer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/AuditLegendPanel.vue#L132",
      "audit-platform/frontend/src/components/workpaper/AuditLegendPanel.vue#L146",
      "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue#L133",
      "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue#L568",
      "audit-platform/frontend/src/components/workpaper/GtA117CorrespondingData.vue#L174",
      "audit-platform/frontend/src/components/workpaper/GtA117CorrespondingData.vue#L210",
      "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue#L541",
      "audit-platform/frontend/src/components/workpaper/GtA171Chapter15.vue#L238"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [
        "onlyoffice-sheet"
      ],
      "sheet_expressions": [
        ":sheet-name=\"isWholeExcelTab ? wholeWorkbookSheetName : activeSheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
      "wp_code_patterns": []
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h4-engineering-materials",
    "entryId": "xlsx/h4/impairment/h4-tab-impairment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabImpairment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue#L212",
      "audit-platform/frontend/src/components/workpaper/composables/useH4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH4Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h4DetailPrefill.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h4_engineering_materials.py",
      "backend/wp_templates/H/H4 工程物资.xlsx!明细表H4-2!A8 = '序号'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-h4-engineering-materials",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabImpairment.vue",
      "wp_code_patterns": [
        "H4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-6"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h4-engineering-materials",
    "entryId": "xlsx/h4/impairment/h4-tab-recoverable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabRecoverable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue#L212",
      "audit-platform/frontend/src/components/workpaper/composables/useH4FormData.ts",
      "audit-platform/frontend/src/components/workpaper/composables/useH4Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h4DetailPrefill.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h4_engineering_materials.py",
      "backend/wp_templates/H/H4 工程物资.xlsx!明细表H4-2!A8 = '序号'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-h4-engineering-materials",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabRecoverable.vue",
      "wp_code_patterns": [
        "H4T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h8-right-of-use-assets",
    "entryId": "xlsx/h8/impairment/h8-tab-recoverable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/impairment/H8TabRecoverable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L341",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L535",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L629",
      "audit-platform/frontend/src/components/workpaper/composables/useH8Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h8DisclosureSyncPayload.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h8_right_of_use_assets.py",
      "backend/wp_templates/H/H8 使用权资产.xlsx!明细表H8-2!A8 = '使用权资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-h8-right-of-use-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/h8/impairment/H8TabRecoverable.vue",
      "wp_code_patterns": [
        "H8T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h8-right-of-use-assets",
    "entryId": "xlsx/h8/measurement/h8-tab-measurement-annual",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementAnnual.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L341",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L535",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L629",
      "audit-platform/frontend/src/components/workpaper/composables/useH8Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h8DisclosureSyncPayload.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h8_right_of_use_assets.py",
      "backend/wp_templates/H/H8 使用权资产.xlsx!明细表H8-2!A8 = '使用权资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-h8-right-of-use-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"'使用权资产 租赁负债初始及后续计量（按年）H8-6'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementAnnual.vue",
      "wp_code_patterns": [
        "H8T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-h8-right-of-use-assets",
    "entryId": "xlsx/h8/measurement/h8-tab-measurement-monthly",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementMonthly.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L341",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L535",
      "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue#L629",
      "audit-platform/frontend/src/components/workpaper/composables/useH8Detail.ts",
      "audit-platform/frontend/src/components/workpaper/composables/h8DisclosureSyncPayload.ts",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/wp_render_strategies/_h8_right_of_use_assets.py",
      "backend/wp_templates/H/H8 使用权资产.xlsx!明细表H8-2!A8 = '使用权资产类别'"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-h8-right-of-use-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"'使用权资产 租赁负债初始及后续计量（按月）H8-6'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementMonthly.vue",
      "wp_code_patterns": [
        "H8T"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/j1/gt-j1-employee-compensation",
    "entryId": "xlsx/j1/gt-j1-employee-compensation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L105",
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L186",
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L213",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L182",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L263",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Detail.ts#L108",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Detail.ts#L247",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Adjudication.ts#L94",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"dualMode.resolveOoSheetName()\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue",
      "wp_code_adjudication_source": "backend/data/workpaper_sync_entry_wp_code_adjudication.json",
      "wp_code_patterns": [
        "J1"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/j1/gt-j1-employee-compensation",
    "entryId": "xlsx/j1/inspection/j1-tab-general-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabGeneralCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L105",
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L186",
      "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue#L213",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L182",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L263",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Detail.ts#L108",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Detail.ts#L247",
      "audit-platform/frontend/src/composables/workpaper/j1/useJ1Adjudication.ts#L94",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/j1/gt-j1-employee-compensation",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"检查表J1-8\""
      ],
      "sheet_literals": [
        "检查表J1-8"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabGeneralCheck.vue",
      "wp_code_patterns": [
        "J1-8",
        "J1T"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/j2/gt-j2-defined-benefit-plan",
    "entryId": "xlsx/j2/gt-j2-defined-benefit-plan",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j2/GtJ2DefinedBenefitPlan.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/j2/GtJ2DefinedBenefitPlan.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/j2/GtJ2DefinedBenefitPlan.vue",
      "wp_code_patterns": [
        "J2D"
      ]
    }
  },
  {
    "adjudicationState": "terminal",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/j3/gt-j3-share-based-payment",
    "entryId": "xlsx/j3/gt-j3-share-based-payment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j3/GtJ3ShareBasedPayment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/j3/GtJ3ShareBasedPayment.vue"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "adapter_registered",
    "parentEntryId": null,
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/j3/GtJ3ShareBasedPayment.vue",
      "wp_code_patterns": [
        "J3S"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k1-other-receivables",
    "entryId": "xlsx/k1/inspection/k1-tab-writeoff-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k1/inspection/K1TabWriteoffCheck.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue#L9",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k1-other-receivables",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k1/inspection/K1TabWriteoffCheck.vue",
      "wp_code_patterns": [
        "K1T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k11-asset-impairment-loss",
    "entryId": "xlsx/k11/core/k11-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k11/core/K11TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k11-asset-impairment-loss",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k11/core/K11TabAdjustment.vue",
      "wp_code_patterns": [
        "K11T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k12-non-operating-income",
    "entryId": "xlsx/k12/core/k12-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k12/core/K12TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k12-non-operating-income",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k12/core/K12TabAdjustment.vue",
      "wp_code_patterns": [
        "K12T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k13-non-operating-expense",
    "entryId": "xlsx/k13/core/k13-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k13/core/K13TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k13-non-operating-expense",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k13/core/K13TabAdjustment.vue",
      "wp_code_patterns": [
        "K13T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k8-selling-expenses",
    "entryId": "xlsx/k8/core/k8-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k8/core/K8TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k8-selling-expenses",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k8/core/K8TabAdjustment.vue",
      "wp_code_patterns": [
        "K8T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": "bidirectional",
    "capabilityTarget": null,
    "capabilityTargetBlockedBy": [],
    "capabilityVerdictStage": null,
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-k9-admin-expenses",
    "entryId": "xlsx/k9/core/k9-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/k9/core/K9TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue#L8",
      "audit-platform/frontend/src/composables/workpaper/useChecklistPersistence.ts#L183",
      "backend/app/routers/checklist_responses.py#L132",
      "backend/app/routers/checklist_responses.py#L84"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-k9-admin-expenses",
    "reasonCodes": [],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/k9/core/K9TabAdjustment.vue",
      "wp_code_patterns": [
        "K9T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "entryId": "xlsx/n1/calc/n1-tab-calc-table",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/calc/N1TabCalcTable.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L61",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L231",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L235",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L317",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"递延所得税资产（负债）测算表N1-4\""
      ],
      "sheet_literals": [
        "递延所得税资产（负债）测算表N1-4"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/n1/calc/N1TabCalcTable.vue",
      "wp_code_patterns": [
        "N1-4",
        "N1T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "entryId": "xlsx/n1/core/n1-tab-adjudication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjudication.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L61",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L231",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L235",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L317",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"递延所得税资产审定表N1-1\""
      ],
      "sheet_literals": [
        "递延所得税资产审定表N1-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjudication.vue",
      "wp_code_patterns": [
        "N1-1",
        "N1T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "entryId": "xlsx/n1/core/n1-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjustment.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L61",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L231",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L235",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L317",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"调整分录汇总N1-3\""
      ],
      "sheet_literals": [
        "调整分录汇总N1-3"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjustment.vue",
      "wp_code_patterns": [
        "N1-3",
        "N1T"
      ]
    }
  },
  {
    "adjudicationState": "inherited",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-6",
      "BP-7",
      "BP-8",
      "BP-9",
      "BP-10",
      "BP-11"
    ],
    "capabilityVerdictStage": "inherited_parent_pending",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "entryId": "xlsx/n1/core/n1-tab-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabDetail.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L61",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L231",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L235",
      "audit-platform/frontend/src/components/workpaper/composables/useN1FormData.ts#L317",
      "backend/app/routers/checklist_responses.py#L84",
      "backend/app/routers/checklist_responses.py#L132"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-n1-deferred-tax-assets",
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        "sheet-name=\"递延所得税资产明细表N1-2\""
      ],
      "sheet_literals": [
        "递延所得税资产明细表N1-2"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabDetail.vue",
      "wp_code_patterns": [
        "N1-2",
        "N1T"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s12-cpa-expert/gt-s12-cpa-expert",
    "entryId": "xlsx/s12-cpa-expert/gt-s12-cpa-expert",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue#L336",
      "audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue#L370",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue",
      "wp_code_patterns": [
        "S12C"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s13-mgmt-expert/gt-s13-mgmt-expert",
    "entryId": "xlsx/s13-mgmt-expert/gt-s13-mgmt-expert",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue#L321",
      "audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue#L354",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue",
      "wp_code_patterns": [
        "S13M"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s14-accounting-estimate/gt-s14-accounting-estimate",
    "entryId": "xlsx/s14-accounting-estimate/gt-s14-accounting-estimate",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue#L293",
      "audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue#L326",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue",
      "wp_code_patterns": [
        "S14A"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s15-eps-roe/gt-s15-eps-roe",
    "entryId": "xlsx/s15-eps-roe/gt-s15-eps-roe",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue#L283",
      "audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue#L318",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue",
      "wp_code_patterns": [
        "S15E"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s20-revenue-deduction/gt-s20-revenue-deduction",
    "entryId": "xlsx/s20-revenue-deduction/gt-s20-revenue-deduction",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue#L916",
      "audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue#L960",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || '营业收入扣除情况核查'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue",
      "wp_code_patterns": [
        "S20R"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s21-data-asset/gt-s21-data-asset",
    "entryId": "xlsx/s21-data-asset/gt-s21-data-asset",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue#L292",
      "audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue#L327",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue",
      "wp_code_patterns": [
        "S21D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s3-policy-change/gt-s3-policy-change",
    "entryId": "xlsx/s3-policy-change/gt-s3-policy-change",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s3-policy-change/GtS3PolicyChange.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s3-policy-change/GtS3PolicyChange.vue#L314",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s3-policy-change/GtS3PolicyChange.vue",
      "wp_code_patterns": [
        "S3P"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange",
    "entryId": "xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s4-nonmonetary-exchange/GtS4NonmonetaryExchange.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s4-nonmonetary-exchange/GtS4NonmonetaryExchange.vue#L250",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s4-nonmonetary-exchange/GtS4NonmonetaryExchange.vue",
      "wp_code_patterns": [
        "S4N"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s5-debt-restructuring/gt-s5-debt-restructuring",
    "entryId": "xlsx/s5-debt-restructuring/gt-s5-debt-restructuring",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s5-debt-restructuring/GtS5DebtRestructuring.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s5-debt-restructuring/GtS5DebtRestructuring.vue#L251",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s5-debt-restructuring/GtS5DebtRestructuring.vue",
      "wp_code_patterns": [
        "S5D"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/s6-fund-occupation/gt-s6-fund-occupation",
    "entryId": "xlsx/s6-fund-occupation/gt-s6-fund-occupation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s6-fund-occupation/GtS6FundOccupation.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/s6-fund-occupation/GtS6FundOccupation.vue#L250",
      "audit-platform/frontend/src/composables/useReviewDialog.ts#L427"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/s6-fund-occupation/GtS6FundOccupation.vue",
      "wp_code_patterns": [
        "S6F"
      ]
    }
  },
  {
    "adjudicationState": "pending",
    "capability": null,
    "capabilityTarget": "bidirectional",
    "capabilityTargetBlockedBy": [
      "BP-1",
      "BP-12",
      "BP-2",
      "BP-3",
      "BP-4",
      "BP-5",
      "BP-7",
      "BP-8"
    ],
    "capabilityVerdictStage": "step_4_blocked_by_step_3_result_exists",
    "documentType": "xlsx",
    "editability": "editable",
    "effectiveEntryId": "xlsx/shared/cycle-standalone-procedure-shell",
    "entryId": "xlsx/shared/cycle-standalone-procedure-shell",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/shared/CycleStandaloneProcedureShell.vue",
    "htmlCounterpartSourceRefs": [
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1174",
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L1472",
      "audit-platform/frontend/src/components/workpaper/GtAProgramConsole.vue#L906"
    ],
    "htmlCounterpartVerdict": "exists",
    "independentEntry": true,
    "migrationState": "legacy_fake_bidirectional",
    "parentEntryId": null,
    "reasonCodes": [
      "template_only_open",
      "no_durable_forcesave_ack",
      "missing_adapter"
    ],
    "roomModel": "shared",
    "roomServiceState": "room_service_wired",
    "scenarioProfileId": "xlsx.editable.shared.single.room_service_wired.v1",
    "wpMatch": {
      "component_types": [],
      "sheet_expressions": [
        ":sheet-name=\"sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/shared/CycleStandaloneProcedureShell.vue",
      "wp_code_patterns": []
    }
  }
] as const satisfies readonly WorkpaperSyncManifestEntry[]
