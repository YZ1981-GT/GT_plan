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
  capability: WorkpaperSyncCapability
  migrationState: string
  independentEntry: boolean
  parentEntryId: string | null
  wpMatch: {
    wp_code_patterns: string[]
    component_types: string[]
    sheet_literals: string[]
    sheet_expressions: string[]
    source_host: string
  }
  editability: WorkpaperSyncEditability
  roomModel: WorkpaperSyncRoomModel
  scenarioProfileId: string
  roomServiceState: string
  reasonCodes: string[]
  hasContractEvidence: boolean
  hasBrowserEvidence: boolean
}

export const WORKPAPER_SYNC_MANIFEST_DIGEST = "8b4f15a5e012f71870cdffb533c906968bb43c036cb9725fd4ec9428a039ef28"

export const WORKPAPER_SYNC_PROFILE_SOURCE_DIGEST = "13961b0c8494be5d979d9c5a110c66a70a5da87c9005fa60d0311b9628ece766"

export const WORKPAPER_SYNC_MANIFEST_STATS = {
  "by_component": {
    "GtOnlyOfficeSheet": 270,
    "OnlyOfficeWordDialog": 2,
    "WorkpaperWordEditor": 4
  },
  "capability_counts": {
    "single_html": 5,
    "single_onlyoffice": 180,
    "unreachable": 1
  },
  "dispatcher_count": 1,
  "editability_counts": {
    "editable": 185,
    "unreachable": 1
  },
  "entry_count": 186,
  "host_count": 185,
  "independent_entry_count": 142,
  "legacy_fake_bidirectional_count": 141,
  "mount_count": 276,
  "parent_duplicate_count": 43,
  "room_model_counts": {
    "exclusive": 6,
    "none": 1,
    "shared": 179
  },
  "room_service_state": "room_service_wired",
  "scenario_profile_counts": {
    "docx.editable.exclusive.dynamic.room_service_wired.v1": 1,
    "docx.editable.exclusive.single.room_service_wired.v1": 5,
    "docx.editable.shared.single.room_service_wired.v1": 1,
    "xlsx.editable.shared.single.room_service_wired.v1": 178,
    "xlsx.unreachable.none.single.room_service_wired.v1": 1
  },
  "unadjudicated_count": 136,
  "unreachable_count": 1
} as const

export const WORKPAPER_SYNC_MANIFEST = [
  {
    "capability": "single_html",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/gt-a10-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA10Bundle.vue",
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
    "capability": "single_html",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/gt-a12-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA12Bundle.vue",
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
    "capability": "single_html",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/gt-a16-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA16Bundle.vue",
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
    "capability": "single_html",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/gt-a17-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA17Bundle.vue",
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
    "capability": "single_html",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/gt-wp-renderer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/workpaper-word-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "docx",
    "editability": "editable",
    "entryId": "docx/wp-popup-docx-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/WpPopupDocxEditor.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/b60/gt-b60-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/b60/GtB60Bundle.vue",
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
      "wp_code_patterns": [
        "B60",
        "B60B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/b60/gt-b60-docx-pane",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/b60/GtB60DocxPane.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/cash-flow-verification",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/CashFlowVerification.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/analysis/d4-tab-customer-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerPrice.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"重要客户销售价格分析D4-10\""
      ],
      "sheet_literals": [
        "重要客户销售价格分析D4-10"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerPrice.vue",
      "wp_code_patterns": [
        "D4-10",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/analysis/d4-tab-customer-structure",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerStructure.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"重要客户结构分析D4-9\""
      ],
      "sheet_literals": [
        "重要客户结构分析D4-9"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabCustomerStructure.vue",
      "wp_code_patterns": [
        "D4-9",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/analysis/d4-tab-indicator",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabIndicator.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"重要指标分析D4-6\""
      ],
      "sheet_literals": [
        "重要指标分析D4-6"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabIndicator.vue",
      "wp_code_patterns": [
        "D4-6",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/analysis/d4-tab-margin-monthly",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabMarginMonthly.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"毛利率分析表D4-7\""
      ],
      "sheet_literals": [
        "毛利率分析表D4-7"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabMarginMonthly.vue",
      "wp_code_patterns": [
        "D4-7",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/analysis/d4-tab-product-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductPrice.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"产品销售价格分析D4-11\""
      ],
      "sheet_literals": [
        "产品销售价格分析D4-11"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/analysis/D4TabProductPrice.vue",
      "wp_code_patterns": [
        "D4-11",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-completeness",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCompleteness.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入完整性检查表D4-15\""
      ],
      "sheet_literals": [
        "营业收入完整性检查表D4-15"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCompleteness.vue",
      "wp_code_patterns": [
        "D4-15",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-contract",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabContract.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"合同检查表D4-12\""
      ],
      "sheet_literals": [
        "合同检查表D4-12"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabContract.vue",
      "wp_code_patterns": [
        "D4-12",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-cutoff-backward",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffBackward.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入截止测试（单据到账）D4-18\""
      ],
      "sheet_literals": [
        "营业收入截止测试（单据到账）D4-18"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffBackward.vue",
      "wp_code_patterns": [
        "D4-18",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-cutoff-forward",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffForward.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入截止测试（账到单据）D4-17\""
      ],
      "sheet_literals": [
        "营业收入截止测试（账到单据）D4-17"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabCutoffForward.vue",
      "wp_code_patterns": [
        "D4-17",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-discount",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabDiscount.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"销售折扣与折让检查D4-19\""
      ],
      "sheet_literals": [
        "销售折扣与折让检查D4-19"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabDiscount.vue",
      "wp_code_patterns": [
        "D4-19",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-erp-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabErpCheck.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入账面金额与ERP系统核对记录D4-13\""
      ],
      "sheet_literals": [
        "营业收入账面金额与ERP系统核对记录D4-13"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabErpCheck.vue",
      "wp_code_patterns": [
        "D4-13",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-export",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabExport.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"出口收入电子口岸系统核对D4-16\""
      ],
      "sheet_literals": [
        "出口收入电子口岸系统核对D4-16"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabExport.vue",
      "wp_code_patterns": [
        "D4-16",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-occurrence",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabOccurrence.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入发生检查表D4-14\""
      ],
      "sheet_literals": [
        "营业收入发生检查表D4-14"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabOccurrence.vue",
      "wp_code_patterns": [
        "D4-14",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/inspection/d4-tab-return",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabReturn.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"销售退货检查表 D4-20\""
      ],
      "sheet_literals": [
        "销售退货检查表 D4-20"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/inspection/D4TabReturn.vue",
      "wp_code_patterns": [
        "D4-20",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-customer-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerChecklist.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"客户信息核查清单D4-28\""
      ],
      "sheet_literals": [
        "客户信息核查清单D4-28"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerChecklist.vue",
      "wp_code_patterns": [
        "D4-28",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-customer-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerDetail.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"客户信息检查表D4-29\""
      ],
      "sheet_literals": [
        "客户信息检查表D4-29"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabCustomerDetail.vue",
      "wp_code_patterns": [
        "D4-29",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-dealer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabDealer.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"经销商检查D4-25\""
      ],
      "sheet_literals": [
        "经销商检查D4-25"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabDealer.vue",
      "wp_code_patterns": [
        "D4-25",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-fund-flow",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"客户、供应商等资金流水检查D4-32\""
      ],
      "sheet_literals": [
        "客户、供应商等资金流水检查D4-32"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabFundFlow.vue",
      "wp_code_patterns": [
        "D4-32",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-interview-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewDetail.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"客户访谈记录 D4-31\""
      ],
      "sheet_literals": [
        "客户访谈记录 D4-31"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewDetail.vue",
      "wp_code_patterns": [
        "D4-31",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-interview-summary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"客户访谈记录汇总表D4-30\""
      ],
      "sheet_literals": [
        "客户访谈记录汇总表D4-30"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInterviewSummary.vue",
      "wp_code_patterns": [
        "D4-30",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-invoice-compare",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInvoiceCompare.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"收入与开具发票金额比较分析D4-23\""
      ],
      "sheet_literals": [
        "收入与开具发票金额比较分析D4-23"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabInvoiceCompare.vue",
      "wp_code_patterns": [
        "D4-23",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-ipo-indicator",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabIpoIndicator.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"重要指标分析表D4-22\""
      ],
      "sheet_literals": [
        "重要指标分析表D4-22"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabIpoIndicator.vue",
      "wp_code_patterns": [
        "D4-22",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-overseas",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabOverseas.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"境外销售收入检查D4-26\""
      ],
      "sheet_literals": [
        "境外销售收入检查D4-26"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabOverseas.vue",
      "wp_code_patterns": [
        "D4-26",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-third-party",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabThirdParty.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"第三方回款检查D4-24\""
      ],
      "sheet_literals": [
        "第三方回款检查D4-24"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabThirdParty.vue",
      "wp_code_patterns": [
        "D4-24",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/ipo/d4-tab-undisclosed-rp",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabUndisclosedRp.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"识别未披露的关联方D4-27\""
      ],
      "sheet_literals": [
        "识别未披露的关联方D4-27"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/ipo/D4TabUndisclosedRp.vue",
      "wp_code_patterns": [
        "D4-27",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/other/d4-tab-other-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCheck.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"其他业务收入检查表D4-35\""
      ],
      "sheet_literals": [
        "其他业务收入检查表D4-35"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCheck.vue",
      "wp_code_patterns": [
        "D4-35",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/other/d4-tab-other-contract",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherContract.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"其他业务收入合同测算表D4-34\""
      ],
      "sheet_literals": [
        "其他业务收入合同测算表D4-34"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherContract.vue",
      "wp_code_patterns": [
        "D4-34",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/other/d4-tab-other-cutoff",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCutoff.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"其他业务收入截止性测试D4-36\""
      ],
      "sheet_literals": [
        "其他业务收入截止性测试D4-36"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherCutoff.vue",
      "wp_code_patterns": [
        "D4-36",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/other/d4-tab-other-margin",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherMargin.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"其他业务毛利率分析表D4-33\""
      ],
      "sheet_literals": [
        "其他业务毛利率分析表D4-33"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/other/D4TabOtherMargin.vue",
      "wp_code_patterns": [
        "D4-33",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/policy/d4-tab-policy-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/policy/D4TabPolicyCheck.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"营业收入会计政策检查D4-5\""
      ],
      "sheet_literals": [
        "营业收入会计政策检查D4-5"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/policy/D4TabPolicyCheck.vue",
      "wp_code_patterns": [
        "D4-5",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/d4/related/d4-tab-related-price",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/d4/related/D4TabRelatedPrice.vue",
    "independentEntry": false,
    "migrationState": "parent_duplicate",
    "parentEntryId": "xlsx/gt-d4-operating-revenue",
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
        "sheet-name=\"关联方销售情况及价格分析D4-21\""
      ],
      "sheet_literals": [
        "关联方销售情况及价格分析D4-21"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/d4/related/D4TabRelatedPrice.vue",
      "wp_code_patterns": [
        "D4-21",
        "D4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a101-governance-communication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue",
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
        "sheet-name=\"A10-1\""
      ],
      "sheet_literals": [
        "A10-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA101GovernanceCommunication.vue",
      "wp_code_patterns": [
        "A10-1",
        "A101G"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a111-subsequent-events-inquiry",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA111SubsequentEventsInquiry.vue",
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
        "sheet-name=\"A11-1\""
      ],
      "sheet_literals": [
        "A11-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA111SubsequentEventsInquiry.vue",
      "wp_code_patterns": [
        "A11-1",
        "A111S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a112-dual-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA112DualChecklist.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a115-disclosure-checklist",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA115DisclosureChecklist.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a121-legal-confirmation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA121LegalConfirmation.vue",
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
        "sheet-name=\"A12-1\""
      ],
      "sheet_literals": [
        "A12-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA121LegalConfirmation.vue",
      "wp_code_patterns": [
        "A12-1",
        "A121L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a171-audit-summary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue",
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
        "sheet-name=\"A17-1\""
      ],
      "sheet_literals": [
        "A17-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA171AuditSummary.vue",
      "wp_code_patterns": [
        "A17-1",
        "A171A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a1721-kam",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA1721Kam.vue",
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
        "sheet-name=\"A17-2-1\""
      ],
      "sheet_literals": [
        "A17-2-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA1721Kam.vue",
      "wp_code_patterns": [
        "A17-2-1",
        "A1721K"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a173-consultation-record",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA173ConsultationRecord.vue",
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
        "sheet-name=\"A17-3\""
      ],
      "sheet_literals": [
        "A17-3"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA173ConsultationRecord.vue",
      "wp_code_patterns": [
        "A17-3",
        "A173C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a1731-consultation-execution",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA1731ConsultationExecution.vue",
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
        "sheet-name=\"A17-3-1\""
      ],
      "sheet_literals": [
        "A17-3-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA1731ConsultationExecution.vue",
      "wp_code_patterns": [
        "A17-3-1",
        "A1731C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a174-disagreement-record",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA174DisagreementRecord.vue",
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
        "sheet-name=\"A17-4\""
      ],
      "sheet_literals": [
        "A17-4"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA174DisagreementRecord.vue",
      "wp_code_patterns": [
        "A17-4",
        "A174D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a176-closing-meeting",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue",
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
        "sheet-name=\"A17-6\""
      ],
      "sheet_literals": [
        "A17-6"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA176ClosingMeeting.vue",
      "wp_code_patterns": [
        "A17-6",
        "A176C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a177-independence-declaration",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue",
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
        ":sheet-name=\"variant === 'team' ? 'A17-7' : 'A17-7A'\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA177IndependenceDeclaration.vue",
      "wp_code_patterns": [
        "A177I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a181-regulatory-submission",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA181RegulatorySubmission.vue",
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
        "sheet-name=\"A18-1\""
      ],
      "sheet_literals": [
        "A18-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA181RegulatorySubmission.vue",
      "wp_code_patterns": [
        "A18-1",
        "A181R"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a182-regulatory-communication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA182RegulatoryCommunication.vue",
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
        "sheet-name=\"A18-2\""
      ],
      "sheet_literals": [
        "A18-2"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA182RegulatoryCommunication.vue",
      "wp_code_patterns": [
        "A18-2",
        "A182R"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a271-it-audit-memo",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA271ItAuditMemo.vue",
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
        "sheet-name=\"A27-1\""
      ],
      "sheet_literals": [
        "A27-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA271ItAuditMemo.vue",
      "wp_code_patterns": [
        "A27-1",
        "A271I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a3-consolidation-console",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue",
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
        "sheet-name=\"A3-3\""
      ],
      "sheet_literals": [
        "A3-3"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA3ConsolidationConsole.vue",
      "wp_code_patterns": [
        "A3-3",
        "A3C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a38-goodwill-impairment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA38GoodwillImpairment.vue",
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
        "sheet-name=\"A3-8商誉减值测试\""
      ],
      "sheet_literals": [
        "A3-8商誉减值测试"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA38GoodwillImpairment.vue",
      "wp_code_patterns": [
        "A3-8",
        "A38G"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a51-cashflow-audit",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA51CashflowAudit.vue",
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
        "sheet-name=\"A5-1\""
      ],
      "sheet_literals": [
        "A5-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA51CashflowAudit.vue",
      "wp_code_patterns": [
        "A5-1",
        "A51C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a81-other-info-representation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA81OtherInfoRepresentation.vue",
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
        "sheet-name=\"A8-1\""
      ],
      "sheet_literals": [
        "A8-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA81OtherInfoRepresentation.vue",
      "wp_code_patterns": [
        "A8-1",
        "A81O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-a91-deficiency-letter",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtA91DeficiencyLetter.vue",
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
        "sheet-name=\"A9-1\""
      ],
      "sheet_literals": [
        "A9-1"
      ],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtA91DeficiencyLetter.vue",
      "wp_code_patterns": [
        "A9-1",
        "A91D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b1-evaluation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1Evaluation.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b1-kaa-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1KaaCheck.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b1-risk-assessment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB1RiskAssessment.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b14-due-diligence-report",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB14DueDiligenceReport.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b22-a-control-matrix",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22AControlMatrix.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b22-b-control-matrix",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22BControlMatrix.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b22-b-deficiency-evaluation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22BDeficiencyEvaluation.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b22-c-design-effectiveness",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB22CDesignEffectiveness.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b23-process-control",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB23ProcessControl.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-b50-risk-assessment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtB50RiskAssessment.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-c-control-test",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtCControlTest.vue",
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
      "wp_code_patterns": []
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-c22-itgc-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue",
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
        ":sheet-name=\"activeDocTab.wpCode || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtC22ItgcBundle.vue",
      "wp_code_patterns": [
        "C22I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-custom-wp-editor",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtCustomWpEditor.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d1-notes-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD1NotesReceivable.vue",
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
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD1NotesReceivable.vue",
      "wp_code_patterns": [
        "D1N"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d2-accounts-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
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
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD2AccountsReceivable.vue",
      "wp_code_patterns": [
        "D2A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d3-prepaid-accounts",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD3PrepaidAccounts.vue",
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
      "wp_code_patterns": [
        "D3P"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d4-operating-revenue",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtD4OperatingRevenue.vue",
      "wp_code_patterns": [
        "D4O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d5-receivables-financing",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD5ReceivablesFinancing.vue",
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
      "wp_code_patterns": [
        "D5R"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d6-contract-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD6ContractAssets.vue",
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
      "wp_code_patterns": [
        "D6C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-d7-contract-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtD7ContractLiabilities.vue",
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
      "wp_code_patterns": [
        "D7C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-e1-monetary-fund",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtE1MonetaryFund.vue",
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
      "wp_code_patterns": [
        "E1M"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f1-prepayment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF1Prepayment.vue",
      "wp_code_patterns": [
        "F1P"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f2-inventory-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventoryMain.vue",
      "wp_code_patterns": [
        "F2I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f2-inventory-special",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventorySpecial.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventorySpecial.vue",
      "wp_code_patterns": [
        "F2I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f2-inventory-valuation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2InventoryValuation.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2InventoryValuation.vue",
      "wp_code_patterns": [
        "F2I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f2-stocktake-bundle",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
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
        ":sheet-name=\"props.sheetName || activeTab\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF2StocktakeBundle.vue",
      "wp_code_patterns": [
        "F2S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f3-notes-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF3NotesPayable.vue",
      "wp_code_patterns": [
        "F3N"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f4-accounts-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF4AccountsPayable.vue",
      "wp_code_patterns": [
        "F4A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-f5-cost-of-sales",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtF5CostOfSales.vue",
      "wp_code_patterns": [
        "F5C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g1-trading-financial-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
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
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG1TradingFinancialAssets.vue",
      "wp_code_patterns": [
        "G1T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g10-trading-financial-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG10TradingFinancialLiabilities.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG10TradingFinancialLiabilities.vue",
      "wp_code_patterns": [
        "G10T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g11-investment-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG11InvestmentIncome.vue",
      "wp_code_patterns": [
        "G11I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g12-net-hedge-gains",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG12NetHedgeGains.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG12NetHedgeGains.vue",
      "wp_code_patterns": [
        "G12N"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g13-fair-value-changes",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG13FairValueChanges.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG13FairValueChanges.vue",
      "wp_code_patterns": [
        "G13F"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g14-credit-impairment-loss",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG14CreditImpairmentLoss.vue",
      "wp_code_patterns": [
        "G14C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g2-interest-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG2InterestReceivable.vue",
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
        ":sheet-name=\"ooSheetName\"",
        ":sheet-name=\"props.sheetName || ''\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG2InterestReceivable.vue",
      "wp_code_patterns": [
        "G2I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g3-dividend-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG3DividendReceivable.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG3DividendReceivable.vue",
      "wp_code_patterns": [
        "G3D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g4-bond-investment-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentEcl.vue",
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
      "wp_code_patterns": [
        "G4B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g4-bond-investment-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentMain.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentMain.vue",
      "wp_code_patterns": [
        "G4B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g4-bond-investment-sppi",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG4BondInvestmentSppi.vue",
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
      "wp_code_patterns": [
        "G4B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g5-long-term-receivable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG5LongTermReceivable.vue",
      "wp_code_patterns": [
        "G5L"
      ]
    }
  },
  {
    "capability": "unreachable",
    "documentType": "xlsx",
    "editability": "unreachable",
    "entryId": "xlsx/gt-g6-other-bond-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondEcl.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g6-other-bond-investment-ecl",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondInvestmentEcl.vue",
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
      "wp_code_patterns": [
        "G6O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g6-other-bond-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondMain.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondMain.vue",
      "wp_code_patterns": [
        "G6O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g6-other-bond-sppi",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG6OtherBondSppi.vue",
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
      "wp_code_patterns": [
        "G6O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g7-equity-method",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7EquityMethod.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g7-equity-subsidiary",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7EquitySubsidiary.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g7-long-term-equity-main",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG7LongTermEquityMain.vue",
      "wp_code_patterns": [
        "G7L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g8-other-equity-instruments",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG8OtherEquityInstruments.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG8OtherEquityInstruments.vue",
      "wp_code_patterns": [
        "G8O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-g9-other-noncurrent-financial",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtG9OtherNoncurrentFinancial.vue",
      "wp_code_patterns": [
        "G9O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h1-fixed-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH1FixedAssets.vue",
      "wp_code_patterns": [
        "H1F"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h10-asset-disposal-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH10AssetDisposalIncome.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH10AssetDisposalIncome.vue",
      "wp_code_patterns": [
        "H10A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h2-construction-in-progress",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH2ConstructionInProgress.vue",
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
      "wp_code_patterns": [
        "H2C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h3-investment-property",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH3InvestmentProperty.vue",
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
      "wp_code_patterns": [
        "H3I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h4-engineering-materials",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH4EngineeringMaterials.vue",
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
      "wp_code_patterns": [
        "H4E"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h5-oil-gas-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH5OilGasAssets.vue",
      "wp_code_patterns": [
        "H5O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h6-asset-disposal-clearing",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH6AssetDisposalClearing.vue",
      "wp_code_patterns": [
        "H6A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h7-biological-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH7BiologicalAssets.vue",
      "wp_code_patterns": [
        "H7B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h8-right-of-use-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtH8RightOfUseAssets.vue",
      "wp_code_patterns": [
        "H8R"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-h9-lease-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtH9LeaseLiabilities.vue",
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
      "wp_code_patterns": [
        "H9L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i1-intangible-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI1IntangibleAssets.vue",
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
      "wp_code_patterns": [
        "I1I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i2-development-expenditure",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI2DevelopmentExpenditure.vue",
      "wp_code_patterns": [
        "I2D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i3-goodwill",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI3Goodwill.vue",
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
      "wp_code_patterns": [
        "I3G"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i4-long-term-prepaid",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI4LongTermPrepaid.vue",
      "wp_code_patterns": [
        "I4L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i5-other-noncurrent-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI5OtherNoncurrentAssets.vue",
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
      "wp_code_patterns": [
        "I5O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-i6-research-development-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtI6ResearchDevelopmentExpense.vue",
      "wp_code_patterns": [
        "I6R"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k1-other-receivables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK1OtherReceivables.vue",
      "wp_code_patterns": [
        "K1O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k10-other-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK10OtherIncome.vue",
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
      "wp_code_patterns": [
        "K10O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k11-asset-impairment-loss",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK11AssetImpairmentLoss.vue",
      "wp_code_patterns": [
        "K11A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k12-non-operating-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK12NonOperatingIncome.vue",
      "wp_code_patterns": [
        "K12N"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k13-non-operating-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK13NonOperatingExpense.vue",
      "wp_code_patterns": [
        "K13N"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k2-other-current-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK2OtherCurrentAssets.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK2OtherCurrentAssets.vue",
      "wp_code_patterns": [
        "K2O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k3-other-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK3OtherPayables.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK3OtherPayables.vue",
      "wp_code_patterns": [
        "K3O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k4-other-current-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK4OtherCurrentLiabilities.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK4OtherCurrentLiabilities.vue",
      "wp_code_patterns": [
        "K4O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k5-provisions",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK5Provisions.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK5Provisions.vue",
      "wp_code_patterns": [
        "K5P"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k6-held-for-sale",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK6HeldForSale.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK6HeldForSale.vue",
      "wp_code_patterns": [
        "K6H"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k7-deferred-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK7DeferredIncome.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK7DeferredIncome.vue",
      "wp_code_patterns": [
        "K7D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k8-selling-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK8SellingExpenses.vue",
      "wp_code_patterns": [
        "K8S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-k9-admin-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtK9AdminExpenses.vue",
      "wp_code_patterns": [
        "K9A"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l1-short-term-loans",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL1ShortTermLoans.vue",
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
        ":sheet-name=\"props.sheetName || 'L1A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL1ShortTermLoans.vue",
      "wp_code_patterns": [
        "L1S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l2-interest-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL2InterestPayable.vue",
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
        ":sheet-name=\"props.sheetName || 'L2A'\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL2InterestPayable.vue",
      "wp_code_patterns": [
        "L2I"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l3-long-term-loans",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL3LongTermLoans.vue",
      "wp_code_patterns": [
        "L3L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l4-bonds-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL4BondsPayable.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL4BondsPayable.vue",
      "wp_code_patterns": [
        "L4B"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l5-long-term-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL5LongTermPayables.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL5LongTermPayables.vue",
      "wp_code_patterns": [
        "L5L"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l6-special-payables",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL6SpecialPayables.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL6SpecialPayables.vue",
      "wp_code_patterns": [
        "L6S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l7-other-noncurrent-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL7OtherNoncurrentLiabilities.vue",
      "wp_code_patterns": [
        "L7O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-l8-financial-expenses",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtL8FinancialExpenses.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtL8FinancialExpenses.vue",
      "wp_code_patterns": [
        "L8F"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m1-dividends-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM1DividendsPayable.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM1DividendsPayable.vue",
      "wp_code_patterns": [
        "M1D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m10-other-equity-instruments",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM10OtherEquityInstruments.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM10OtherEquityInstruments.vue",
      "wp_code_patterns": [
        "M10O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m2-paid-in-capital",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM2PaidInCapital.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM2PaidInCapital.vue",
      "wp_code_patterns": [
        "M2P"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m3-treasury-stock",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM3TreasuryStock.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM3TreasuryStock.vue",
      "wp_code_patterns": [
        "M3T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m4-capital-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM4CapitalReserve.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM4CapitalReserve.vue",
      "wp_code_patterns": [
        "M4C"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m5-surplus-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM5SurplusReserve.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM5SurplusReserve.vue",
      "wp_code_patterns": [
        "M5S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m6-retained-earnings",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM6RetainedEarnings.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m7-special-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM7SpecialReserve.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM7SpecialReserve.vue",
      "wp_code_patterns": [
        "M7S"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m8-general-risk-reserve",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM8GeneralRiskReserve.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM8GeneralRiskReserve.vue",
      "wp_code_patterns": [
        "M8G"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-m9-other-comprehensive-income",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtM9OtherComprehensiveIncome.vue",
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
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtM9OtherComprehensiveIncome.vue",
      "wp_code_patterns": [
        "M9O"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-n1-deferred-tax-assets",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN1DeferredTaxAssets.vue",
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
        ":sheet-name=\"props.sheetName || ''\"",
        ":sheet-name=\"props.sheetName\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN1DeferredTaxAssets.vue",
      "wp_code_patterns": [
        "N1D"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-n2-taxes-payable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN2TaxesPayable.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-n3-deferred-tax-liabilities",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN3DeferredTaxLiabilities.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-n4-taxes-and-surcharges",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN4TaxesAndSurcharges.vue",
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
      "source_host": "audit-platform/frontend/src/components/workpaper/GtN4TaxesAndSurcharges.vue",
      "wp_code_patterns": [
        "N4T"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-n5-income-tax-expense",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtN5IncomeTaxExpense.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/gt-wp-renderer",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/GtWpRenderer.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/h4/impairment/h4-tab-impairment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabImpairment.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/h4/impairment/h4-tab-recoverable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h4/impairment/H4TabRecoverable.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/h8/impairment/h8-tab-recoverable",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/impairment/H8TabRecoverable.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/h8/measurement/h8-tab-measurement-annual",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementAnnual.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/h8/measurement/h8-tab-measurement-monthly",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/h8/measurement/H8TabMeasurementMonthly.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/j1/gt-j1-employee-compensation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue",
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
        ":sheet-name=\"dualMode.resolveOoSheetName()\""
      ],
      "sheet_literals": [],
      "source_host": "audit-platform/frontend/src/components/workpaper/j1/GtJ1EmployeeCompensation.vue",
      "wp_code_patterns": [
        "J1E"
      ]
    }
  },
  {
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/j1/inspection/j1-tab-general-check",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/j1/inspection/J1TabGeneralCheck.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/n1/calc/n1-tab-calc-table",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/calc/N1TabCalcTable.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/n1/core/n1-tab-adjudication",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjudication.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/n1/core/n1-tab-adjustment",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabAdjustment.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/n1/core/n1-tab-detail",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/n1/core/N1TabDetail.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s12-cpa-expert/gt-s12-cpa-expert",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s12-cpa-expert/GtS12CpaExpert.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s13-mgmt-expert/gt-s13-mgmt-expert",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s13-mgmt-expert/GtS13MgmtExpert.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s14-accounting-estimate/gt-s14-accounting-estimate",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s14-accounting-estimate/GtS14AccountingEstimate.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s15-eps-roe/gt-s15-eps-roe",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s15-eps-roe/GtS15EpsRoe.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s20-revenue-deduction/gt-s20-revenue-deduction",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s20-revenue-deduction/GtS20RevenueDeduction.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s21-data-asset/gt-s21-data-asset",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s21-data-asset/GtS21DataAsset.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s3-policy-change/gt-s3-policy-change",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s3-policy-change/GtS3PolicyChange.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s4-nonmonetary-exchange/gt-s4-nonmonetary-exchange",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s4-nonmonetary-exchange/GtS4NonmonetaryExchange.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s5-debt-restructuring/gt-s5-debt-restructuring",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s5-debt-restructuring/GtS5DebtRestructuring.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/s6-fund-occupation/gt-s6-fund-occupation",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/s6-fund-occupation/GtS6FundOccupation.vue",
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
    "capability": "single_onlyoffice",
    "documentType": "xlsx",
    "editability": "editable",
    "entryId": "xlsx/shared/cycle-standalone-procedure-shell",
    "hasBrowserEvidence": false,
    "hasContractEvidence": false,
    "hostPath": "audit-platform/frontend/src/components/workpaper/shared/CycleStandaloneProcedureShell.vue",
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
