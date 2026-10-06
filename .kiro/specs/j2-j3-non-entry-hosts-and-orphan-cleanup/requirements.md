# Requirements Document

## Introduction

鏈?spec 鏄?**J 寰幆 lane**锛岃鐩?**J2锛堥暱鏈熷簲浠樿亴宸ヨ柂閰?璁惧畾鍙楃泭璁″垝鍑€璧勪骇锛変笌
J3锛堣偂浠芥敮浠橈級涓や釜銆岄潪 entry 瀹夸富銆?*锛屼互鍙婃寕鍦ㄥ畠浠韩涓婄殑 **4 涓?orphan dual-mode composable**
涓?1 涓€岄暱寰楀儚杞戒綋鐨勬浠ｇ爜銆嶃€?
馃敶 **鏈?spec 鐨勪氦浠樼墿绫诲瀷涓庡湴鍩?spec 瀹屽叏涓嶅悓**锛?鍦板熀 spec 浜や粯 contract + provider + adapter + canary锛堜负**鏄?entry** 鐨?J1 鏈嶅姟锛夛紱
鏈?spec 浜や粯 **orphan 娓呯悊 + 缂洪櫡鐧昏 + 涓哄皢鏉ユ帴鍏ュ仛鍑嗗**锛圝2/J3 **涓嶆槸** manifest entry锛?鐜板湪涓嶅彂 contract銆佷笉娉ㄥ唽 adapter銆佷笉鍋?roundtrip锛夈€?鎶婁袱鑰呭悎鎴愪竴浠戒細璁┿€屽摢浜涗换鍔℃槸涓?entry 鏈嶅姟鐨勩€嶈涓嶆竻銆?
**涓轰粈涔?J2 涓?J3 鍚堟垚涓€浠借€屼笉鎷嗕袱浠?*锛氫袱鑰呯殑闃诲椤?*瀹屽叏閲嶅悎**锛圔P-6 / BP-7 閮芥í璺?J2 涓?J3锛夈€?涓婚鍚屼竴锛堥潪 entry 瀹夸富 + orphan 娓呯悊锛夈€佷笖 4 涓?orphan 閲?J2 鍗?2 涓?J3 鍗?2 涓€?鎷嗕袱浠戒細鎶婂悓涓€濂楀彲杈炬€у垽鎹妱涓ら亶銆?
**涓婃父锛堝彧寮曠敤涓嶅杩帮級**锛?`j-cycle-sync-foundation-and-first-canary`锛?*JC-1 ~ JC-20** 鍏卞悓瑁佸喅 + canary `J1-6-short-term` 鑼冨紡锛壜?umbrella Task 52 鐨?J slice 路 FC-1~FC-13 路 GC-1~GC-10 路 HC-1~HC-16 路 IC-1~IC-20銆?
馃敶 **JC-1 ~ JC-20 鐨勬鏂囧湪鍦板熀 spec 瑁佸畾锛屾湰 spec 涓€鏉￠兘涓嶅杩?*锛堝杩板嵆婕傜Щ锛夈€?
**涓嶉噸閫犲凡鏈変骇鐗?*锛?`backend/tests/workpaper_sync/test_task52_j_cycle_migration.py`锛堝惈 `TestOrphanDualModeInventory`锛壜?馃敶 `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`锛堝彉寮傛敞鍏ワ紝**鐩存帴澶嶇敤**锛壜?馃敶 `backend/data/workpaper_sync_j_cycle_deletion_plan.json`锛?*宸叉湁鍒犻櫎璁″垝锛屾寜瀹冩墽琛屼笉鍙﹁捣**锛壜?`backend/app/data/wp_render_schema/j2-defined-benefit-plan.yaml` 路 `j3-share-based-payment.yaml`銆?
馃敶 **涓嶅緱淇敼 `backend/wp_templates/` 瀛楄妭**銆?馃敶 **涓嶅緱鎶?J2/J3 鎵嬪啓杩?`workpaper_sync_entry_manifest.json`** 鈥斺€?瀹冧滑涓嶆槸 entry
鏄?`selection_rule` **鐜扮畻鐨勭粨鏋?*锛屾墜鍐欎細杩濆弽 slice step 1 鐨?forbidden 骞惰 selection_rule 涓嶅啀鍙绠椼€?
## 鑼冨洿锛? 涓潪 entry 瀹夸富 / 15 sheets / 4 orphan + 1 lookalike

| 椤?| J2 | J3 |
|---|---|---|
| 瀹夸富 | `components/workpaper/j2/GtJ2DefinedBenefitPlan.vue`锛?*238 琛?*鍘熷 / 226 鍓ユ敞閲婏級 | `components/workpaper/j3/GtJ3ShareBasedPayment.vue`锛?*210 琛?* / 196锛?|
| componentType | `j2-defined-benefit-plan` | `j3-share-based-payment` |
| registry 婧?| `registry/entries/specialized.ts` | 鍚?|
| htmlRendererRegistry | 鏈夌湡 `defineAsyncComponent` 妯″潡杈?| 鍚?|
| 馃敶 `GtOnlyOfficeSheet` | **0** | **0** |
| 馃敶 `el-segmented` | **0** | **0** |
| manifest entry | 馃敶 **涓嶅瓨鍦?* | 馃敶 **涓嶅瓨鍦?* |
| 妯℃澘 | `J2 闀挎湡搴斾粯鑱屽伐钖叕-璁惧畾鍙楃泭璁″垝鍑€璧勪骇.xlsx` 路 sha256 `b9a4d87c95d275d7鈥 路 107,237 B 路 **9 sheets** | `J3 鑲′唤鏀粯.xlsx` 路 sha256 `72e026f43612ec6b鈥 路 50,195 B 路 **6 sheets** |
| 瀹″畾琛?| `瀹″畾琛↗2-1` | 馃敶 **鏃犲瀹氳〃** |
| definedName | **37**锛堭煍?鍚?`#REF!` **30**锛?| 馃敶 **502**锛堝惈 `#REF!` **479**锛?|
| 瑁?IF | **12**锛堝叏鍦?`瀹″畾琛↗2-1`锛?| 馃敶 **0**锛堟暣鍐岋級 |
| 瀛?Tab 鏈?KEY 瀵硅薄 | **6 涓?*锛坄J2TabIndex` 鏃狅級 | **3 涓?*锛坄J3TabIndex` 鏃狅級 |
| orphan dual-mode | `useJ2EntryDualMode.ts`锛?1 琛岋紝涓€闃讹級路 `useJ2DualMode.ts`锛?5 琛岋紝浜岄樁锛?| `useJ3EntryDualMode.ts`锛?7 琛岋紝涓€闃讹級路 `useJ3DualMode.ts`锛?9 琛岋紝浜岄樁锛?|
| lookalike 杞戒綋 | 馃敶 `useJ2FormData.ts` **宸茶鐗╃悊鍒犻櫎** | `useJ3FormData.ts`锛?*151 琛?*锛屼粛鍦級 |
| `useAdjustmentCentralSync` | 鏈夛紙`J2TabAdjustment.vue`锛?| 馃敶 **鏃?*锛圝3 鏃犵嫭绔嬬鐩級 |
| `wp_guidance` | 馃敶 **`J2.json` 缂哄け** | `J3.json` 瀛樺湪 |

馃敶 **J3 鏃犵嫭绔嬬鐩?*锛氬涓?docstring 鏄庡啓銆岃垂鐢ㄧ璧?K8/K9锛屾潈鐩婄璧?M4锛岀幇閲戠璧?J1銆?鈬?鍗充究灏嗘潵鎺?OO 鍏ュ彛锛屽畠鐨勫瀹氳〃涔?*涓嶅洖鍐?`trial_balance`**銆?
## Requirement 1锛氿煍?銆屼笉鏄?entry銆嶅繀椤绘槸鍙绠楃殑缁撹锛屼笉鏄仐婕?
**User Story**锛氫綔涓哄悗鏉ヨ€咃紝鎴戣鑳借嚜宸辫窇涓€閬嶅氨纭 J2/J3 纭疄涓嶅湪 manifest 閲岋紝
鑰屼笉鏄€€鐤戜笂涓€杞紡杩佷簡涓ゆ潯銆?
### Acceptance Criteria

1. WHEN 鏂█ J2/J3 闈?entry THEN SHALL **鍥涗晶閮介獙**锛?   鈶?鎸?slice `selection_rule` 鐜扮畻 entry 闆嗗悎锛屾柇瑷€鎭?**1 鏉?* `xlsx/j1/gt-j1-employee-compensation`
   鈶?鏂█ manifest 閲?*娌℃湁浠讳綍 entry** 鐨?`host_path` 绛変簬杩欎袱涓涓昏矾寰?   鈶?鏂█涓や釜瀹夸富鐨勫灞?`<template>` 閲?`GtOnlyOfficeSheet` 涓?`el-segmented` 鍛戒腑**鍚?0**
   鈶?鏂█ `htmlRendererRegistry` 閲屼袱鏉?componentType 鐨?import 璺緞**鐪熸寚鍚?*杩欎袱涓枃浠?2. 馃敶 WHEN 澶勭悊 manifest THEN SHALL **绂佹妸 J2/J3 鎵嬪啓杩?`workpaper_sync_entry_manifest.json`**
   鈥斺€?瀹冧滑涓嶅湪 manifest 鏄?`selection_rule` 鐜扮畻鐨勭粨鏋滐紱鎵嬪啓浼氳繚鍙?slice step 1 鐨?forbidden
   銆屾墜鎶?entry 鍒楄〃銆嶅苟璁?selection_rule 涓嶅啀鍙绠椼€?3. WHEN 璇存槑銆屼骇鍝佷笂鍙揪浣?OO 渚ф棤鍏ュ彛銆峊HEN SHALL 閫愰」钀藉疄娴嬶細涓ゅ涓荤殑 import 娈靛彧鏈?   `CycleTabProcedure` + `useChecklistPersistence` + `useWorkpaperScaffold` + `useWorkpaperReviewThreads`
   鈥斺€?**鏃?OO 缁勪欢銆佹棤 dual-mode composable**銆?4. 馃敶 WHEN 澶勭悊 manifest entries 鎬绘暟 THEN SHALL **鐜扮畻**锛坰lice 澶氬鍐?186锛岀幇绠?**155**锛夛紱
   浠讳綍鍐欐璇ユ暟鐨勫垽鎹?SHALL 鏀逛负鐜扮畻銆?5. WHEN 澹版槑鏈?spec 鐨勮竟鐣?THEN SHALL 鏄庣‘锛氭湰 spec **涓嶅彂 contract銆佷笉娉ㄥ唽 adapter銆佷笉鍋?roundtrip**
   锛圝2/J3 涓嶆槸 entry锛夛紝鍙仛 orphan 娓呯悊 + 缂洪櫡鐧昏 + 涓哄皢鏉ユ帴鍏ュ噯澶囥€?
## Requirement 2锛欱P-6 鈥斺€?4 涓?orphan dual-mode锛屼袱涓竴闃朵袱涓簩闃?
**User Story**锛氫綔涓哄钩鍙扮淮鎶よ€咃紝鎴戣鑳借瘑鍒€岀湅璧锋潵鏈夋秷璐规柟浣嗗叾瀹炰粠浠讳綍鐪熷疄瀹夸富閮藉埌涓嶄簡銆嶇殑姝讳唬鐮侊紝
鑰屼笉鏄鍏ュ害楠楄繃鍘汇€?
### Acceptance Criteria

1. WHEN 鍒ゅ畾 orphan THEN SHALL 鍋?*鍙揪鎬?*鍒ゅ畾鑰屼笉鏄?*鍏ュ害**鍒ゅ畾锛屼袱闃堕€愭潯鐜扮畻锛?
| id | 妯″潡 | 琛屾暟 | 闃?| statement 鐢熶骇杈?| 鍒ゅ畾渚濇嵁 |
|---|---|---|---|---|---|
| OD-1 | `components/workpaper/composables/useJ2EntryDualMode.ts` | **41** | 涓€闃?| **0**锛堟祴璇曡竟涔?0锛?| 鐩存帴闆惰竟 |
| OD-2 | `components/workpaper/composables/useJ3EntryDualMode.ts` | **37** | 涓€闃?| **0**锛堟祴璇曡竟涔?0锛?| 鐩存帴闆惰竟 |
| OD-3 | `composables/workpaper/j2/useJ2DualMode.ts` | **35** | 馃敶 **浜岄樁** | **1**锛堝彧 barrel `j2/index.ts`锛?| 馃敶 barrel 鑷韩鍏ヨ竟 **0** |
| OD-4 | `composables/workpaper/j3/useJ3DualMode.ts` | **39** | 馃敶 **浜岄樁** | **1**锛堝彧 barrel `j3/index.ts`锛?| 馃敶 barrel 鑷韩鍏ヨ竟 **0** |

2. 馃敶 WHEN 缂栧啓鍒ゆ嵁 THEN SHALL 鍐欏弽璇侊細`useJ2DualMode` 鐨?statement 杈规暟鏄?**2**
   锛坆arrel + 1 涓?spec锛夆€斺€?鏈寸礌鐨勩€屽叆搴?> 0 鈬?涓嶆槸瀛ゅ効銆嶅垽鎹細**鏀惧畠杩囧幓**銆?   鈬?鍒ゆ嵁 SHALL 椤虹潃 barrel 鍐嶉棶涓€灞傦細鍏ㄤ粨娌℃湁浠讳綍鏂囦欢 import `@/composables/workpaper/j2`
   锛圝2 瀹夸富涓?6 涓瓙 Tab 閮芥槸**閫愭ā鍧楁繁閾?*锛屼笉璧?barrel锛夈€?3. 馃敶 WHEN 澶勭疆 OD-1 / OD-2 鐨?sheet 鏄犲皠琛?THEN SHALL 鏂█**鏄犲皠鐩爣涓€涓兘涓嶅瓨鍦?*锛?   - `J2_SHEET_MAP` **8 鏉?*鐩爣锛坄J2-鐩綍` / `J2A` / `J2-1`..`J2-4` / `J2闄勬敞(涓婂競)` / `J2闄勬敞(鍥戒紒)`锛?     vs 妯℃澘鐪熷疄 9 寮?sheet 鍚嶏紙`搴曠鐩綍` / `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 J2A` /
     `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 L2A` / `瀹″畾琛↗2-1` / `闄勬敞鎶湶淇℃伅锛堜笂甯傚叕鍙革級` /
     `闄勬敞鎶湶淇℃伅锛堝浗鏈変紒涓氾級` / `鏄庣粏琛↗2-2` / `璋冩暣鍒嗗綍姹囨€昏〃J2-3` / `璁℃彁鎯呭喌妫€鏌ヨ〃J2-4`锛?     鈬?**8/8 涓嶅湪 sheetnames 閲?*
   - `J3_SHEET_MAP` **4 鏉?*鐩爣锛坄J3-鐩綍` / `J3A` / `J3-1` / `J3-2`锛?     vs 妯℃澘鐪熷疄 6 寮?鈬?**4/4 涓嶅湪 sheetnames 閲?*
   鈬?鍗充究鏈変汉鎶婂畠鎺ヤ笂瀹夸富锛孫O 渚т細鎸変笉瀛樺湪鐨?sheet 鍚嶅幓鍙?鈬?杩欐槸銆屾帴涓婂氨鍧忋€嶄笉鏄€屾帴涓婅兘鐢ㄣ€嶃€?4. 馃敶 WHEN 澶勭疆 OD-4 THEN SHALL 鏂█瀹?*鐩磋皟 legacy 绔偣**锛?   `GET /api/workpapers/onlyoffice/health` 鈥斺€?鍛戒腑 `legacy_deletion_paradigm` **step 6 鏄庣椤?*
   锛堣绔偣鐨勮皟鐢ㄥ彧鑳介€氳繃 sync bridge 鐨?materialize 鍗忚锛夈€?   瀹冪幇鍦ㄦ棤鍗卞鍙洜鏁翠釜妯″潡涓嶅彲杈撅紱浣嗛『鐫€ barrel 鎺ヨ捣鏉ュ氨鏄竴鏉?*缁曡繃 bridge 鐨勬梺璺?*銆?   SHALL 涓€骞剁櫥璁板畠鑷甫鐨?`checkOOHealth` 涓庡叡浜熀绫荤殑瀹炵幇**閲嶅涓旀洿寮?*锛堟棤 `_silent`銆佹棤淇″皝鍙屽舰鎬佸吋瀹癸級銆?5. WHEN 澶勭疆**涓や釜 orphan barrel** THEN SHALL 鏂█ `composables/workpaper/j2/index.ts` 涓?   `j3/index.ts` 鍏ヨ竟鍚?**0**锛涴煍?浣?SHALL **涓嶅绉?*鏁翠釜 `composables/workpaper/j3/` 鐩綍閮芥槸姝荤殑 鈥斺€?   鍚岀洰褰曠殑 `useJ3ImportExport.ts` 鏈変竴鏉?*鐪熷疄鐢熶骇杈?*锛坄j3/core/J3TabDetail.vue` 璧版繁閾捐€岄潪 barrel锛夈€?6. WHEN 鎵ц鍒犻櫎 THEN SHALL 馃敶 **鎸夊凡鏈夌殑 `workpaper_sync_j_cycle_deletion_plan.json` 鎵ц锛屼笉鍙﹁捣璁″垝**锛?   鍒犲墠 SHALL 鏂█ 4 涓矾寰勭殑鍙揪鎬у垽瀹氬叏閮ㄦ垚绔嬶紝鍒犲悗 SHALL 鍏ㄥ娴嬭瘯闆跺洖褰掋€?7. WHEN 澶勭疆鍏变韩鍩虹被 THEN SHALL 鏂█ `useWorkpaperEntryDualMode.ts` **淇濈暀**锛?   鐜扮畻 statement 杈?**29**锛孞 寰幆璐＄尞 **3**锛圤D-1 + OD-2 + J1 瀹夸富锛夆噿 鍒犲畬 J 鐨勫伐浣滃悗鍓?**26**锛?   馃敶 璁℃暟鍙ｅ緞蹇呴』鏄?*绐勫彛寰勶紙鐪熻鍙ヨ竟锛?*锛涘鍙ｅ緞鐜扮畻 **34** 浼氬緱 31 鑰岃銆屽垹瀹岃繕鍓╁灏戙€嶈涓嶆竻銆?8. 馃敶 WHEN 鐢ㄥ/绐勫彛寰?THEN SHALL 鎸?JC-16 鐨勫彛寰勶細宸泦鐜扮畻 **5 涓?*涓嶆槸 slice 璇寸殑 1 涓?   鈬?鍒ゆ嵁鍐欍€屽樊闆?*鍖呭惈** `workpaperSyncLegacyBaseline.generated.ts`銆? 鐜扮畻娓呭崟锛岀鍐欐涓暟銆?
## Requirement 3锛欱P-7 鈥斺€?`useJ3FormData.ts` 鏄€岄暱寰楀儚杞戒綋鐨勬浠ｇ爜銆?
### Acceptance Criteria

1. WHEN 鍒ゅ畾 THEN SHALL 鐜扮畻 `composables/workpaper/j3/useJ3FormData.ts`锛?*151 琛?*锛?   鍙粡瀛ょ珛 barrel 鍙揪锛屽嵈鍚?*瀹屾暣鎸佷箙鍖栫閬?*锛?   `GET /api/workpapers/{wpId}/render-config` + `PUT /api/workpapers/{wpId}/checklist-responses`
   + `POST /api/projects/{projectId}/events/publish`
2. 馃敶 WHEN 鍒ゅ畾瀹冪殑浼犺緭閿舰鎬?THEN SHALL 鏂█瀹冩妸 item_id 鎷兼垚 `` `J3-${key}` `` 鈥斺€?   鑰?*鐢熶骇璺緞浠庢湭鍐欒繃杩欑褰㈡€?*锛圝3 鐨勭湡瀹為敭鏄笁涓瓙 Tab 鍚勮嚜 `KEY` 瀵硅薄閲岀殑瀛楅潰閲忥級
   鈬?verdict `FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION`銆?3. 馃敶 WHEN 鍒ゅ畾鍙揪鎬?THEN SHALL **涓嶈兘鍙湅涓€灞?*锛氬畠鏈?**3 鏉″叆杈?*锛坆arrel + `useJ3Detail.ts` +
   `useJ3Integration.ts`锛夛紝浣嗗悗涓よ€呰嚜韬篃鍙粡瀛ょ珛 barrel 鍙揪
   锛坄useJ3Detail` 鍏ヨ竟 1 = 鍙湁 barrel锛沗useJ3Integration` 鍏ヨ竟瀹炴祴 **0**锛?   鈬?涓夎€呮瀯鎴愪竴涓?*鍙粡瀛ょ珛 barrel 鐩歌繛鐨勭皣**锛屼粠浠讳綍鐪熷疄瀹夸富閮戒笉鍙揪銆?4. WHEN 澶勭疆 THEN SHALL 鍒楀叆 `forbidden_carriers`锛?*鏀圭嚎鏃舵渶瀹规槗璇帴鐨勪笢瑗?*锛夛紱
   鍒犻櫎 SHALL 鎸夊凡鏈?deletion plan 鎵ц锛屼笖 SHALL 涓€骞惰瘎浼?`useJ3Detail.ts` / `useJ3Integration.ts`
   鏄惁鍚屾壒鍒狅紙瀹冧滑鏄繖涓皣鐨勫叾浣欐垚鍛橈級銆?5. WHEN 瀵圭収 J2 渚?THEN SHALL 鐧昏 `useJ2FormData.ts` **宸茶鐗╃悊鍒犻櫎**
   锛坰lice 2026-09-14 鏇存柊璁拌浇鐨勫姩浣滃凡鍏戠幇锛岀幇绠楁枃浠朵笉瀛樺湪锛夆噿 椋庨櫓宸茶嚜鐒舵秷瑙ｏ紝涓嶅啀鏈夊彲璇帴鐨勫疄浣撱€?6. 馃敶 WHEN 瀵圭収鐪熷疄杞戒綋 THEN SHALL 鏂█ J3 鐨勭湡瀹炲啓璺緞鏄涓荤粡 `useChecklistPersistence`
   锛圝C-2 鐨勭涓夌鏃忥級+ 馃敶 **`j3/core/J3TabDetail.vue` 鑷繁涔熺洿鍐?* `PUT 鈥?checklist-responses`
   鈥斺€?鍚庤€呮槸鏈疆瀹炴祴鍙戠幇锛坰lice 璇?J3 璧板涓婚€傞厤鍣紝鏈彁鐩村啓锛夈€?
## Requirement 4锛歯on_entry 渚х殑 5 澶勪綅缃寲韬唤 + 鎶湶灞傚悓鍨嬮闄?
### Acceptance Criteria

1. WHEN 澶勭疆 BP-8 鐨?non_entry 閮ㄥ垎 THEN SHALL 钀?**5 澶?*锛圝C-6 鐨勬棌鍒掑垎锛屾湰 spec 鍙疄渚嬪寲锛夛細

| 鏃?| 绔欑偣 | 琛ㄨ揪寮?| 鍐欏叆閿?| 涓ラ噸搴?|
|---|---|---|---|---|
| 馃敶 **A 绾簭鍙风湡钀藉簱** | `j2/J2TabAdjustment.vue` | `id: i + 1` | `J2-3-entries` | **鏈€閲?* |
| B 涓嬫爣鍏滃簳 | `j2/J2TabAdjustment.vue` | `id: e.id ?? i + 1` | 鍚屼笂 | 娆′箣 |
| B 涓嬫爣鍏滃簳 | `j3/core/J3TabDetail.vue` | `id: p.id ?? i + 1` | `J3-1-plans` | 娆′箣 |
| B 涓嬫爣鍏滃簳 | `j3/core/J3TabCheck.vue`锛堜袱澶勶級 | `id: r.id ?? i + 1` | `J3-2-vouchers` 绛?| 娆′箣 |

2. 馃敶 WHEN 璁鸿瘉 family_a 鐨勪弗閲嶆€?THEN SHALL 鐢?*鐪熷簱瀹炶瘉**鑰屼笉鏄帹婕旓細
   `J2-3-entries` 鐪熷簱 171 B 杞借嵎瀹炴祴
   `[{"id":1,"description":"閲嶅垎绫讳竴骞村唴鍒版湡杈為€€绂忓埄","category":"璐﹂」璋冩暣",鈥]`
   鈬?**`"id":1` 宸茬湡钀藉簱**銆傚垹涓棿涓€琛屽啀鏂板锛屽悗缁 id 鍏ㄩ儴宸︾Щ銆佸巻鍙插娉ㄤ笌閲戦涓插埌鍙︿竴绗斿垎褰曘€?3. WHEN 淇?family_a THEN SHALL 鎹㈡垚瀹夊叏鐢熸垚鍣紙鍚?`Math.random()` 涓斿洖钀藉垎鏀笉鏄笅鏍囷級锛?   馃敶 宸茶惤搴撶殑 `id: 1..N` **涓€寰?grandfather 涓嶉噸鍐?*锛堟敼瀹冪瓑浜庢崲韬唤锛夛紱
   濂戠害灞?SHALL 澹版槑 `legacy_ordinal_ids_grandfathered: true`銆?4. WHEN 淇?family_b 鍥涘 THEN SHALL 鍙敼**鍥炶惤鍒嗘敮**锛屼繚鐣欍€屼笂娓告湁 id 鏃朵紭鍏堢敤涓婃父 id銆嶈涔夈€?5. 馃敶 WHEN 澶勭疆鎶湶灞?THEN SHALL 鐧昏 **J2 渚ф湁涓?J1 鍚屽瀷鐨勫弻鍙樹綋鎶湶 Tab**
   锛坄J2TabDisclosureListed.vue` / `J2TabDisclosureSoe.vue`锛岄敭鍒嗗埆 11 涓?/ 9 涓級
   鈬?JC-6 鐨?JD-7銆?9 涓‖缂栫爜 id銆嶅洓鏉￠闄?SHALL 鍦?J2 渚?*鍚屽彛寰勫鏍?*
   锛堟湰 spec 鍙仛澶嶆牳涓庣櫥璁帮紝**涓嶅杩?* JC-6 姝ｆ枃锛夈€?6. WHEN 澶勭疆 J2/J3 鐨勪紶杈撻敭 THEN SHALL 鏂█ owner 鏄?*鍚勫瓙 Tab 鐨勭粍浠跺眬閮?`KEY` 瀵硅薄**
   锛圝2 **6 涓?* / J3 **3 涓?*锛夛紝鏃犲叡浜父閲忔ā鍧楋紱
   馃敶 SHALL 鏂█ `J2TabIndex.vue` 涓?`J3TabIndex.vue` **鏃?`KEY` 瀵硅薄**锛堝彧璇?allResponses 绠楀畬鎴愬害銆佷笉鍐欏簱锛?   鈥斺€?slice 棣栫増鎶?`J3TabIndex` 鍒楄繘 owner 娓呭崟琚畧鍗墦绾㈡敼姝ｏ紝鎵€浠ャ€屽洓涓?Tab銆嶈繖涓暟鏄敊鐨勩€?*瀹炰负涓変釜**銆?7. 馃敶 WHEN 澹版槑閿泦鍚?THEN SHALL **鍙喕缁撳凡鐧昏鐨?owner 甯搁噺锛屼笉鍐荤粨 J2/J3 鐨勯敭鍏ㄩ泦**
   鈥斺€?瀹冧滑涓嶆槸 entry锛屽喕缁撳叏闆嗕細閫犲嚭涓€浠?*娌℃湁娑堣垂鏂圭殑姝诲０鏄?*锛坅dditive 娉ㄥ叆鍗虫浠ｇ爜锛夈€?   鍒ゆ嵁鍙獙銆岀湡瀹炲舰鎬?= 鍚?Tab 鐨勫瓧闈㈤噺 `KEY` 瀵硅薄銆嶄笌銆宱rphan 杞戒綋鐨勫舰鎬?鈮?鐪熷疄褰㈡€併€嶄袱浠朵簨銆?
## Requirement 5锛欽2/J3 妯℃澘灞?鈥斺€?definedName 鏂摼鏄湰 lane 鏈€閲嶇殑鎶€鏈€?
### Acceptance Criteria

1. WHEN 澶勭疆 definedName THEN SHALL 钀界幇绠楀熀绾夸笌鏂摼鏁帮紝骞舵寜 JC-13 鍙ｅ緞**鐧昏 + 鏂█涓嶅闀?+ 涓嶅垹**锛?
| 鍐?| definedName | 鍚?`#REF!` | 鍗犳瘮 |
|---|---|---|---|
| J2 | **37** | **30** | 81% |
| J3 | 馃敶 **502** | 馃敶 **479** | **95%** |

2. 馃敶 WHEN 璁鸿瘉 J3 鐨?502 涓槸**璺ㄥ惊鐜鍒舵畫鐣?* THEN SHALL 閫愭潯鍒楀疄娴嬪悕瀛楁牱鏈細
   `_1鍥哄畾璧勪骇鏁版嵁搴揰绛涢€夋墦鍗癭锛圚 寰幆锛壜?`_2鍏朵粬璧勪骇_寮€鍔炶垂闄ゅ_鏄庣粏琛╜锛圞 寰幆锛壜?   `_2銆佷富瑕佷笟鍔℃椿鍔╜锛圔 寰幆锛壜?`_.dbf` 路 `AS2DocOpenMode` 路 `_1銆佸彈鏈惊鐜奖鍝嶇殑鐩稿叧浜ゆ槗鍜岃处鎴蜂綑棰漙
   鈬?杩欎簺鍚嶅瓧涓庤偂浠芥敮浠樹笟鍔℃鏃犲叧绯伙紝鏄粠鍒殑宸ヤ綔绨垮鍒舵ā鏉挎椂甯﹁繘鏉ョ殑銆?3. 馃敶 WHEN 瑁佸畾澶勭疆 THEN SHALL **涓嶅垹**锛堝垹浼氳 `max_column` 鍐呯殑鍏紡鏁寸墖澶辨晥锛夛紝
   鍙０鏄庛€屽悓姝ユ椂涓嶆柊澧炪€佷笉鏀瑰啓銆嶏紱娓呯悊 definedName 灞?*妯℃澘娌荤悊**鍙︿竴鏉￠摼璺紝鏍?`[ ]*`銆?4. 馃敶 WHEN 瀵圭収 I 寰幆 THEN SHALL 鐧昏 **J 姣?I 涓ラ噸涓€绾?*锛?   I 鏄€宒efinedName 闈?0銆嶏紙I4 476 / I5 334锛屾湭鏌ユ柇閾撅級锛汮 鏄€?*闈?0 涓旂粷澶у鏁版柇閾?*銆嶃€?5. WHEN 澹版槑瑁?IF THEN SHALL 钀?J2 **12**锛堝叏鍦?`瀹″畾琛↗2-1`锛壜?馃敶 J3 **0**锛堟暣鍐岋級锛?   per-file 鎸備腑鎬у寲鍑芥暟锛涘彉寮傘€屾暣鍐岀粺涓€鎸傘€峉HALL 鎵撶孩銆?6. WHEN 澹版槑 J2 涓昏〃鍑犱綍 THEN SHALL 钀?`鏄庣粏琛↗2-2` r=90 c=14 f=221 merged=30 **鍏釜瀛愬尯**锛?   涓?6 涓紶杈撻敭涓€涓€瀵瑰簲锛?
| 瀛愬尯 | 琛?| 瀵瑰簲閿?|
|---|---|---|
| 涓昏〃 | R11-18锛堜袱绾ц〃澶?R11/R12 路 footer R18 `=C13+C16-C17`锛?| `J2-2-main` |
| 鍒版湡鍒嗘瀽 | R20-27锛坒ooter R27 `=SUM(C22:C26)`锛?| `J2-2-maturity` |
| 璁惧畾鍙楃泭璁″垝鎯呭喌 | R30-47锛堭煍?**涓夌骇宓屽** R38鈫扲39鈫扲40:R42 路 footer R47 `=C32+C33+C38-C43`锛?| `J2-2-dbp-status` |
| 璁″垝璧勪骇 | R49-61锛坒ooter R61 `=C51+C52+C56+C60`锛?| `J2-2-plan-assets` |
| 绮剧畻鍋囪 | R63 璧?| `J2-2-assumptions` |
| 鏁忔劅鎬у垎鏋?| 鏈尯 | `J2-2-sensitivity` |

7. 馃敶 WHEN 澹版槑鍒楁槧灏?THEN SHALL 鐧昏 **`鏄庣粏琛↗2-2` 涓?`鏄庣粏琛↗1-2 ` 鐨?14 鍒楄涔夐€愬瓧鐩稿悓**
   锛圓 搴忓彿 / B 椤圭洰鍚嶇О / C-F 鏈鏁癧鏈熷垵,鏈湡澧?鏈湡鍑?鏈熸湯] / G 鏈熷垵璋冩暣 / H-I 璐﹂」璋冩暣 /
   J-M 瀹″畾鏁癧鏈熷垵,鏈湡澧?鏈湡鍑?鏈熸湯] / N 澶囨敞锛?   鈬?灏嗘潵 J2 鎺?OO 鍏ュ彛鏃?*濂戠害鍙叡鐢ㄥ垪鏄犲皠**锛屼笉蹇呴噸瑁併€?8. 馃敶 WHEN 澹版槑 J3 涓昏〃鍑犱綍 THEN SHALL 钀?`鑲′唤鏀粯鎯呭喌琛↗3-1` r=43 c=18 f=**7** 鈥斺€?   閭?7 涓叕寮?*鍏ㄦ槸 R3/R4 鐨?`=搴曠鐩綍!A2` / `A3`**锛屽嵆 馃敶 **鏁磋〃闆朵笟鍔″叕寮?*锛?   鏁版嵁鍖?R20-27锛圧21=`浠ユ潈鐩婂伐鍏风粨绠梎锛孯22-27 绌猴級路 **鏃?footer 鍚堣** 路
   鏈夋晥鍒?**14** vs max_column **18**锛堝樊 4锛夆噿 UUID 鍒?**15**銆?9. WHEN 澹版槑 J3 鐨勪細璁¤竟鐣?THEN SHALL 鐧昏 馃敶 **J3 鏃犲瀹氳〃涓旀棤鐙珛绉戠洰**锛?   6 寮?sheet 閲屾病鏈?`瀹″畾琛↗3-*`锛涘涓?docstring 鏄庡啓銆岃垂鐢ㄧ璧?K8/K9锛屾潈鐩婄璧?M4锛岀幇閲戠璧?J1銆?   鈬?鍗充究灏嗘潵鎺?OO 鍏ュ彛锛屽畠鐨勫瀹氳〃涔?*涓嶅洖鍐?`trial_balance`**
   鈬?鍒ゆ嵁 SHALL **涓嶈姹?* J3 鏈?TB 鍙戝竷闂紙瑕佹眰浜嗗氨鏄亣绾級銆?10. WHEN 澹版槑 sheet 鍚?THEN SHALL 鎸?JC-10 鏂█ J2/J3 **鏃犲熬閮ㄧ┖鏍?*锛?    浣?*鍚嶄腑绌烘牸 3 寮?*锛坄闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 J2A` 路 `鈥2A` 路 `鑲′唤鏀粯瀹炶川鎬х▼搴忚〃 J3A`锛夌 strip锛?    馃敶 SHALL 鐧昏 `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 L2A` 鐜扮畻鏄?**hidden**锛坰lice 鏈锛変笖灞?**L 寰幆**涓插唽銆?11. WHEN 鏂█骞插噣鐐?THEN SHALL 閫愰」鐜扮畻涓?0 骞舵寜 JC-20 绌哄垎姣嶇邯寰嬪鐞嗭細
    J2/J3 鐨勮秺鐣屽紩鐢?**0** 路 瀹借〃 **0** 路 Excel Table **0** 路 retired sheet **0**锛堜袱鍐岄兘鏃?`-鍒犻櫎`/`-鍘熺増`锛夈€?
## Requirement 6锛氫负灏嗘潵鎺ュ叆鍋氬噯澶囷紙涓嶇幇鍦ㄦ帴锛?
**User Story**锛氫綔涓轰笅涓€杞殑瀹炴柦鑰咃紝鎴戣鑳界洿鎺ユ嬁鍒般€孞2/J3 鎺?OO 鍏ュ彛鏃堕渶瑕佷粈涔堛€嶇殑娓呭崟锛?鑰屼笉鏄噸鏂拌皟鏌ヤ竴閬嶃€?
### Acceptance Criteria

1. 馃敶 WHEN 鏈?spec 鏀跺熬 THEN SHALL 浜у嚭**鎺ュ叆鍓嶇疆娓呭崟**锛堜笉鎵ц锛屽彧鐧昏锛夛紝閫愭潯缁欑幇鐘朵笌缂哄彛锛?   鈶?瀹夸富闇€鎸?`GtOnlyOfficeSheet`锛堢幇鐘?0锛?   鈶?瀹夸富闇€ `el-segmented` 妯″紡鍒囨崲鍣?+ **浜岀骇闂ㄦ帶**锛堢幇鐘?0锛涴煍?涓嶅緱閲嶆紨 J1 鐨勬棤澹板け璐ワ紝瑙?JC-15锛?   鈶?闇€ per-entry dual-mode 鎴栧鐢ㄥ叡浜熀绫伙紙馃敶 鐜版湁 4 涓?orphan **涓€涓兘涓嶈兘鎺?*锛岃 Requirement 2/3锛?   鈶?闇€ `GtEntrySyncCapabilityNotice` 鎸傝浇 + 鏂囨鐪熸簮锛堢幇鐘?0锛?   鈶?闇€ per-entry contract锛堢幇鐘?0锛涴煍?J2 鐨勫垪鏄犲皠鍙?*鍏辩敤 J1 鐨?14 鍒楄涔?*锛岃 Requirement 5.7锛?   鈶?J3 馃敶 **涓嶉渶瑕?* TB 鍙戝竷闂紙鏃犵嫭绔嬬鐩紝瑙?Requirement 5.9锛?   鈶?`wp_guidance/J2.json` **缂哄け**锛堢幇鐘讹細鍙湁 `J1.json` / `J3.json`锛?2. WHEN 鐧昏 `wp_guidance/J2.json` 缂哄け THEN SHALL 鏍?*鐧昏涓嶈ˉ**锛欽2 涓嶆槸 entry锛?   鐜板湪琛ヤ細閫犲嚭涓€浠芥病鏈夋秷璐规柟鐨勬枃浠讹紙additive 鍗虫浠ｇ爜锛夛紱鎺ュ叆鏃朵竴骞惰ˉ銆?3. WHEN 鐧昏 J2/J3 鐨?render schema THEN SHALL 鏂█涓や唤**宸插瓨鍦?*
   锛坄j2-defined-benefit-plan.yaml` / `j3-share-based-payment.yaml`锛夆噿 鎺ュ叆鏃?*涓嶉噸閫?*銆?4. 馃敶 WHEN 鐧昏 J2 鐨勬姭闇插啓璺緞 THEN SHALL 钀藉畠宸插湪鐢?*绗笁鏉″啓璺緞**锛?   `J2TabDisclosureListed.vue` 涓?`J2TabDisclosureSoe.vue` 閮借皟
   `POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper`
   鈬?鍐欑殑鏄?*鍙︿竴寮犺〃**锛堜笉鏄?`checklist_responses`锛夆噿 鎺ュ叆鏃跺绾﹀繀椤诲悓鏃惰鐩栦袱鏉¤矾寰勩€?5. WHEN 鐧昏 J2/J3 鐨勪簨浠惰矾寰?THEN SHALL 钀?`POST /api/projects/{projectId}/events/publish`
   锛坄useJ2CrossSheet` / `useJ3CrossSheet` / `useJ3Integration`锛?
   `POST /api/projects/{projectId}/cross-wp-references/batch`锛坄useJ3Integration`锛?   鈥斺€?馃敶 鍏朵腑缁?orphan 绨囩殑閭ｄ簺锛坄useJ3FormData` / `useJ3Integration`锛?*鍒犻櫎鍚庝細涓€骞舵秷澶?*锛?   鎺ュ叆鏃堕』纭杩欎簺鑱斿姩鏄惁杩橀渶瑕併€?6. 馃敶 WHEN 鐧昏 J2/J3 鐨勭湡搴撹浇鑽?THEN SHALL 钀界幇绠楋細J2 渚?`J2-2-dbp-status` **2731 B** 路
   `J2-soe-change` **2556 B** 路 `J2-2-plan-assets` 1581 B 路 `J2-1-dbo` 1503 B 路 `J2-2-main` 1101 B 路
   `J2-3-entries` 171 B锛汮3 渚?`J3-2-variation` 288 B 路 `J3-1-plans` 251 B 路 `J3-2-vouchers` 165 B 路
   `J3-1-expert` 121 B锛堝彟 6 涓敭 remark 涓虹┖涓诧級
   鈬?**J2/J3 鐪熷簱閮芥湁闈炵┖杞借嵎** 鈬?灏嗘潵瀹冧滑鎴愪负 entry 鏃?*婊¤冻 canary 纭爣鍑?*锛?   鏈?spec SHALL 鎶婅繖涓粨璁烘樉寮忕櫥璁扮粰涓嬩竴杞€?7. WHEN 鐧昏 J2-5..J2-10 / J3-3..J3-10 THEN SHALL 鎸?JC-11 鏂█杩欎簺瀛愮爜**婧愭ā鏉挎棤瀵瑰簲 sheet**
   浣嗕袱涓В鏋愬嚱鏁?*浠嶈繑鍥炲悇鑷殑鍐?*锛堟寜鍐屽墠缂€瑙ｆ瀽锛夆噿 鎺ュ叆鏃跺垽鎹笉寰楀啓銆岃В鏋愰潪 None 鈬?sheet 瀛樺湪銆嶃€?
## Requirement 7锛氶浂鍥炲綊 + 涓嶅杩?JC + 璇佹嵁

### Acceptance Criteria

1. WHEN 瀹炴柦浠讳竴 Task THEN SHALL 鍏?*鐜扮畻**闆跺洖褰掑熀绾匡紙濂戠害鐩綍 `*.json` 涓暟涓庢枃浠跺悕闆嗗悎 路
   `DELIVERED_PER_ENTRY_CONTRACTS` 鏉℃暟涓?entry_id 闆嗗悎 路 `adapter_registered=True` 闆嗗悎 路
   `DELIVERED_ENGINE_ADAPTERS` / `PENDING_ENGINE_ADAPTERS` 鎴愬憳锛夛紝馃敶 **绂佸啓姝讳釜鏁?*
   锛堜細闅忓湴鍩?spec 鐨?canary 娉ㄥ唽鑰屽彉锛夈€?2. 馃敶 WHEN 寮曠敤 JC-1~JC-20 THEN SHALL **鍙啓缂栧彿 + 涓€鍙ヨ瘽鐢ㄩ€?*锛屾鏂囦竴寰嬩笉鎶勶紱
   浜や粯鍚?SHALL 鑴氭湰鏍搞€屾湰 spec 鐨?`JC-\d+` 寮曠敤闆嗗悎 鈯?鍦板熀 spec 鐨?`### JC-\d+` 瀹氫箟闆嗗悎銆嶃€?3. WHEN 鍐欍€孨 澶勩€嶇被琛ㄨ堪 THEN N SHALL 涓庡悓娈靛垪涓鹃」鏁?*閫愭潯鐩哥瓑**銆?4. WHEN 浜у嚭璇佹嵁 THEN SHALL 钀?`evidence/` 涓嬮€?Task 涓€浠斤紝鍚?openpyxl 鐪熻鐗囨涓?   鍙揪鎬у垽瀹氱殑涓ら樁璁＄畻杩囩▼锛汼HALL 鏂█鍏ㄦ枃鏃?U+FFFD銆?5. 馃敶 WHEN 鎵ц鍒犻櫎 THEN SHALL 涓変欢浜嬮綈澶囨墠鍔ㄦ墜锛?   鈶?鍒犲墠鍙揪鎬у垽瀹氭垚绔嬶紙涓ら樁锛夆憽 鍒犲墠鍚庡叏濂楁祴璇曢浂鍥炲綊 鈶?鐙珛 commit锛堜究浜庡洖婊氾級
   鈥斺€?涓?SHALL **鎸夊凡鏈夌殑 `workpaper_sync_j_cycle_deletion_plan.json` 鎵ц锛屼笉鍙﹁捣璁″垝**銆?6. WHEN 澶嶇敤鍙樺紓璇佹槑 THEN SHALL 馃敶 鐢ㄥ凡鏈夌殑
   `backend/scripts/diagnose/mutate_task52_j_cycle_migration_guards.py`锛?*涓嶆柊鍐欏彉寮傝剼鏈?*銆?
## 闃诲椤?
**骞冲彴绾э紙鍏ㄥ惊鐜叡鏈夛紝鍙爣 `[ ]*` 涓嶆壙璇猴級**锛?BP-1 instrumentation candidate 路 BP-2 per-entry contract 路 BP-3 authority model + bundle 路
BP-4 鐪?OnlyOffice 9.4 required scenario set銆?馃敶 **浣嗗鏈?spec 鑰岃█杩欏洓鏉￠兘涓嶆槸闃诲**锛欽2/J3 涓嶆槸 entry锛屾湰 spec 涓嶅彂 contract 涓嶆敞鍐?adapter
鈬?SHALL 鏄庣‘鐧昏銆屾湰 spec 鐨勪氦浠樹笉渚濊禆 BP-1~BP-4銆嶃€?
**鏈?lane 鎵挎帴**锛?
| BP / 浜嬮」 | 鐘舵€?| 璇存槑 |
|---|---|---|
| **BP-6** 4 涓?orphan dual-mode | 鏈?lane 浜や粯鍒犻櫎 | 涓や釜涓€闃?+ 涓や釜浜岄樁锛涙寜宸叉湁 deletion plan 鎵ц |
| **BP-7** `useJ3FormData.ts` 姝讳唬鐮?| 鏈?lane 浜や粯 `forbidden_carriers` + 鍒犻櫎 | 杩炲甫璇勪及 `useJ3Detail` / `useJ3Integration` 鍚屾壒 |
| **BP-8**锛坣on_entry 5 澶勶級 | 鏈?lane 浜や粯淇 | family_a 1锛堢湡搴撳凡钀藉簱锛実randfather锛? family_b 4 |
| J2/J3 definedName 鏂摼锛?0 / 479锛?| 鐧昏 + 鏂█涓嶅闀?+ **涓嶅垹** | 娓呯悊灞炴ā鏉挎不鐞嗗彟涓€閾捐矾锛宍[ ]*` |
| J2 渚ф姭闇插眰 49 纭紪鐮?id 鍚屽瀷澶嶆牳 | 鏈?lane 澶嶆牳 + 鐧昏 | 淇硶 `[ ]*`锛堟秹鐢ㄦ埛鍙鎶湶鍙ｅ緞锛?|
| `wp_guidance/J2.json` 缂哄け | **鐧昏涓嶈ˉ** | J2 涓嶆槸 entry锛涙帴鍏ユ椂涓€骞惰ˉ |
| J2/J3 鎺ュ叆鍓嶇疆娓呭崟 7 鏉?| 鏈?lane 浜や粯娓呭崟锛堜笉鎵ц锛?| Requirement 6 |
| BP-5 / BP-9 / BP-10 / BP-11 | **鍦板熀 spec** | 涓嶅湪鏈?lane |
