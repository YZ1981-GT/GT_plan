# -*- coding: utf-8 -*-
"""K 循环基线后新增生产文件的具名账本。"""

from __future__ import annotations


#: 基线后经独立 spec 新增的 K 域生产文件；只许追加具名路径，禁止抬历史基线。
K_DOMAIN_ADDED_FILES: tuple[str, ...] = (
    "audit-platform/frontend/src/components/workpaper/composables/k10DisclosureSnapshot.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k10HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k11DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k11HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k12DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k12HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k13DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k13HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k1BackendOwnedKeys.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k1FormulaPushNotice.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k1HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k1WriteoffSync.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k2DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k2HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k3DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k3HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k3RowVoucherFill.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k4DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k4HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k5DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k5HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k6DisclosureTabState.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k6HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k7DisclosureSnapshot.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k7HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k8DisclosureSnapshot.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k8HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k9DisclosureSnapshot.ts",
    "audit-platform/frontend/src/components/workpaper/composables/k9HeadlessDisclosure.ts",
    "audit-platform/frontend/src/components/workpaper/k3/inspection/K3RowVoucherTable.vue",
)
