# Formal Export Unit Policy Guide

> **spec**: platform-global-display-settings-closure task 12C (Stage C export unit documentation).
> Screen display preferences: [display-preferences.md](../frontend/display-preferences.md) (task 12A).
> Ledger import normalization: [ledger-import-unit-normalization.md](ledger-import-unit-normalization.md) (task 12B).

---

## 1. Export Surface Classification

Every file output is classified into exactly one of four types:

| Type | Description | Unit Source |
|------|-------------|-------------|
| formal | Official Excel/Word/PDF for audit delivery | ExportUnitPolicy (project unit) |
| data_exchange | Local data export (merge consolidation) | Raw yuan + _GT_EXPORT_META |
| template | Template-only (headers, no business rows) | N/A |
| non_amount | Non-financial output (logs, config, metadata) | N/A |

The EXPORT_SURFACE_REGISTRY enforces bidirectional equality between actual file sinks and registered classifications.

## 2. Standard Authority (Template-Based)

Standard templates declare default regions and units per version. Each ExportUnitRegion has:
- stable_id: template-defined stable identifier
- measure_kind: amount/quantity/count/ratio/exchange_rate/unit_price/text
- ratio_scale: fraction or percent_points (only for ratio kind)
- unit: yuan/qian/wan (from project amount_unit)
- divisor: 1/1000/10000

Only amount-kind regions execute the policy divisor. All other kinds output raw values.

## 3. Custom Authority (Two-Stage Reachable Chain)

Custom workbook units follow a five-step process:
1. Ingest: upload file, receive artifact + hash
2. Preflight: validate artifact structure, identify amount regions
3. Unit Authority PUT: confirm units per region with hash + preflight CAS
4. Finalize: lock artifact with confirmed authorities
5. Instantiate: bind to project working paper

Structure drift clears confirmations and requires re-preflight.

## 4. Audit Report Placeholders

Five financial placeholders in audit reports have registered stable region/kind:
- total_assets, total_liabilities, total_equity, total_revenue, net_income
- All are amount kind, use project amount_unit divisor
- ReportBodyService.fill_placeholders receives explicit policy

## 5. Working Paper / Word Version Evidence

- Every disclosure version with file content must have valid snapshot + digest pair
- OnlyOffice: base version verified before open, callback inherits by base_version_no
- Refresh: inherits current policy
- Full rebuild: creates new policy
- DB CHECK constraint enforces pair presence

## 6. PDF Export

- PDF strict DTO with object-level auth gate
- Memory password only (no disk credential)
- PDF-only validation errors: structured deletion of input/context in error_handler
- No report language selector (removed per review NIT)

## 7. Limitations and Degradation

- LibreOffice missing: PDF export returns 503 with clear message
- Custom workbook without authority: formal export blocked, data_exchange allowed
- Historical files without policy evidence: formal export blocked

## 8. Subsequent Batches

| Item | Status |
|------|--------|
| Full custom workbook wizard UI | Framework created, wizard not implemented |
| PDF password per-project configuration | Not in scope |
| Batch export with mixed policies | Not in scope |
