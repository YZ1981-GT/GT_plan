# Requirements Document

## Introduction

试算表版本时光机（Trial Balance Version Time Machine）——每次重算/保存产出不可变快照，审计师可回溯任意历史版本、两版 diff 对比、一键回滚。解决"重算后发现数据变差想退回"+"复核人查看编制过程演变"两大痛点。

## Requirements

### Requirement 1: Snapshot on Recalc/Save

When the system executes a full recalc (`recalc_unadjusted`) or the user saves trial balance summary (`saveTbSummary`),
the system shall create an immutable snapshot record containing:
- All trial_balance rows (standard_account_code, unadjusted_amount, aje_adjustment, rje_adjustment, audited_amount)
- All tbSummaryRows (row_code, row_name, unadjusted, aje_dr, aje_cr, rcl_dr, rcl_cr, audited)
- Trigger source (recalc / manual_save / import / adjustment_approved)
- Actor (user_id) and timestamp
- SHA-256 content hash for deduplication (consecutive identical states skip creating new snapshot)

### Requirement 2: Version List and Browse

When the user opens the "版本历史" panel in the trial balance page,
the system shall display a chronological list of snapshots with:
- Version number (auto-increment per project+year)
- Trigger type icon + label
- Actor name + relative time ("3小时前")
- Content hash abbreviated (first 8 chars, tooltip full)
- Quick diff badge: number of changed rows vs previous version

### Requirement 3: Version Detail and Restore

When the user selects a historical version,
the system shall:
- Display a read-only table of that version's data (same columns as current)
- Provide a "恢复此版本" button (gated: manager+, confirm dialog)
- Restore SHALL create a new snapshot (restore event) before overwriting, preserving full audit trail
- Restore SHALL trigger recalc of downstream (report/workpaper) via existing event mechanism

### Requirement 4: Two-Version Diff

When the user selects two versions for comparison,
the system shall display a side-by-side or inline diff showing:
- Changed rows highlighted (audited_amount changed > 0.01)
- Added/removed rows (account code present in one but not other)
- Summary stats: N rows changed, total audited delta, max single-row delta

### Requirement 5: Storage and Retention

The system shall:
- Store snapshots in a dedicated `trial_balance_snapshots` table (project_id, year, version_no, trigger, actor, created_at, content_hash, snapshot_data JSONB)
- Retain at least the latest 50 versions per project+year
- Provide an optional purge mechanism for versions older than 1 year (admin-only, confirm)

### Requirement 6: Zero Regression

The system shall:
- Not change existing trial_balance table structure
- Not alter recalc/save behavior beyond appending snapshot
- Maintain all existing API contracts unchanged
- Snapshot creation failure SHALL NOT block the triggering operation (best-effort, fail-open)

## Glossary

- **Snapshot**: Immutable point-in-time capture of trial_balance + summary state
- **Version**: Sequential number identifying a snapshot within (project, year)
- **Restore**: Operation that replaces current data with a historical snapshot's data
- **Content Hash**: SHA-256 of sorted JSON representation for dedup
