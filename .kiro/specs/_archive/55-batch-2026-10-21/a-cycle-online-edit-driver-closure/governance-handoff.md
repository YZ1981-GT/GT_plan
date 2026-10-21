# 治理门交接材料：A 循环驱动收口导致的 mount 源变化

> 交给 `workpaperSyncLegacyBaseline` / manifest 的**人工复核门**。本 spec **不** auto-regen
> manifest / legacy baseline（那是复核门后的动作）。本文件说明「mount 源为什么变、变了哪些」，
> 供复核人据此决定是否更新 `approved_source_digest` 并重算两个生成产物。

## 摘要

- `approved_source_digest`（overlay `backend/data/workpaper_sync_entry_overlay.json`）：
  `83ffa47d67099f496b5782361bc4698b2f4271e4d68e6af629aa7de80872c0ea`
- 本 spec 完成后 discoverer `current` sourceDigest：
  `23f66ff3aec8a9a561e10129b839870cd89b587e757e037f41966d5edf5d4376`
- （中途值 `8c52677e…` 是 A 循环改线前、f20789453 半成品状态的 digest。）

digest 变化**全部**来自本 spec 对 17 个 A 循环宿主的改线，是**可解释的良性变化**，
不是未审迁移。

## 变化清单（17 宿主，三类）

### 类 A：11 宿主「建了桥但无驱动」→「接 useARenderModeSwitch 真驱动」
mount 从「descriptor 恒 null 的空壳」变成「有人调 switchToOnlyOffice」：
GtA91 / GtA101 / GtA111 / GtA121 / GtA1721 / GtA1731 / GtA173 / GtA174 / GtA182 /
GtA271 / GtA81。
- discoverer 看到的变化：这些 entry 的「single-mode switch debt / no-driver」特征消失
  （不再是 hollow / built-not-driven）。

### 类 B：3 宿主「generate-docx 但无驱动」→「driver + beforeEnterOo 预生成」
GtA171 / GtA176 / GtA177。预生成 Word 后由 driver switchToOnlyOffice。

### 类 C：3 宿主「建了死桥 + 走 legacy GtOnlyOfficeSheet」→「删死桥」
GtA38 / GtA112 / GtA115。这三本底稿在线编辑本就走整册 `GtOnlyOfficeSheet`
（whole-workbook，sheet A3-8 / A1-12 / A1-15），此前 `useWorkpaperSyncBridge` 是零引用
死代码。删除后 discoverer 不再把它们算作「建了桥却无驱动」。

## 复核后动作（复核人执行，不在本 spec）

1. 人工比对 mount diff（本清单 + discoverer `--json` 输出），确认 17 条变化都是上述良性改线。
2. 更新 overlay 的 `approved_source_digest` 为 `23f66ff3…`（或复核时的最新现算值）。
3. 重算两个生成产物：
   - `python backend/scripts/gen/generate_workpaper_sync_manifest.py`（去掉 --check）
   - `python backend/scripts/gen/generate_workpaper_sync_legacy_baseline.py`（去掉 --check）
4. `workpaperSyncLegacyBaseline.spec.ts` 3 红随之转绿（两生成产物重新对齐 + 口径更新）。

## 现算快照（legacy 生成器 --check 的 [SOURCE] 行，本 spec 完成后）

```
entries=198 independent=145 template_only=102 reload_only=15
no_forcesave=120 no_ack=145 missing_adapter=101 single_with_switch=82
```
（改线前 template_only=85；A 循环接 driver / 删死桥后 single-mode switch 特征收敛，
template_only 升至 102。）
