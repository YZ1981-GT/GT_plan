# Design Document

## Overview

鏈?design 鎵胯浇 **lane 涓撳睘瑁佸喅 JN-1 ~ JN-7** 涓?**J2/J3 鎺ュ叆鍓嶇疆娓呭崟**銆?
馃敶 **鍒嗗伐閾佸緥**锛歚JC-1 ~ JC-20` 鐨勬鏂囥€佸垽鎹彛寰勩€佹灇涓惧畾涔?*鍏ㄩ儴鍦ㄥ湴鍩?spec**
锛坄j-cycle-sync-foundation-and-first-canary/design.md`锛夈€傛湰鏂囦欢**鍙啓缂栧彿 + 涓€鍙ヨ瘽鐢ㄩ€?*銆?
**鏈?lane 鐨勬妧鏈富棰樺彧鏈変竴涓?*锛?*鎶娿€屼粠浠讳綍鐪熷疄瀹夸富閮藉埌涓嶄簡銆佷絾鐪嬭捣鏉ユ椿鐫€銆嶇殑浠ｇ爜璇嗗埆鍑烘潵骞跺垹鎺?*锛?鍚屾椂鎶?J2/J3 鎺ュ叆 OO 鍓嶉渶瑕佷粈涔堢櫥璁版垚娓呭崟銆?
馃敶 **鏈?lane 涓嶄氦浠?contract / adapter / roundtrip** 鈥斺€?J2/J3 涓嶆槸 manifest entry銆?
## 涓庡湴鍩?spec 鐨勫紩鐢ㄦ竻鍗曪紙鍙紩鐢紝涓嶅杩帮級

| JC | 涓€鍙ヨ瘽鐢ㄩ€?| 鏈?lane 瀹炰緥鍖栧湪 |
|---|---|---|
| JC-1 | manifest 鍙ｅ緞 + 绂佹墜鏀?manifest | **JN-1** |
| JC-2 | 杞戒綋鏃忕涓夌锛坄useChecklistPersistence`锛宑lient 鏄?`api`锛?| JN-3 / 鎺ュ叆娓呭崟 |
| JC-6 | 琛岃韩浠戒簲鏃忓垝鍒?+ JD-7锛?9 纭紪鐮?id 鐧昏涓嶅垽缂洪櫡锛? JD-8锛堝垽鍒紡鏀惧锛?| **JN-4** |
| JC-10 | sheet 鍚嶄笁绫荤┖鏍肩 strip | JN-5 |
| JC-11 | 鍙樹綋杞?+ 璺ㄥ惊鐜覆鍐?+ 瀛愮爜瑙ｆ瀽杩斿唽浣?sheet 涓嶅瓨鍦?| JN-5 / 鎺ュ叆娓呭崟 |
| JC-13 | definedName 鍩虹嚎 + 鏂摼鐧昏 + 涓嶅垹 | **JN-5** |
| JC-15 | BP-10 鏃犲０澶辫触涓夎绱狅紙鎺ュ叆鏃朵笉寰楅噸婕旓級 | 鎺ュ叆娓呭崟 |
| JC-16 | 瀹?绐勫彛寰勪笌宸泦鐜扮畻 | **JN-2** |
| JC-20 | 绌哄垎姣嶇邯寰?+ 澶嶇敤宸叉湁鍙樺紓鑴氭湰 | 鍏ㄧ瘒 |

鏈湪涓婅〃鍑虹幇鐨?JC-3 / JC-4 / JC-5 / JC-7 / JC-8 / JC-9 / JC-12 / JC-14 / JC-17 / JC-18 / JC-19
鍦ㄦ湰 lane 鐨勭姸鎬侊細
JC-3锛堝叚绫荤鐐癸級涓?JC-14锛堣８ IF锛夋寜鍦板熀鍒ゆ嵁鐩存帴濂楃敤锛屾湰 lane 鍙ˉ J2/J3 鐨勫疄娴嬪€?路
馃敶 **JC-4 / JC-5 / JC-8 / JC-9 / JC-12 / JC-18 / JC-19 涓庢湰 lane 鏃犲叧**
锛堥偅浜涢兘鏄?J1 鐨勪竴琛ㄤ笁閿€佹嫾鎺ラ敭銆佷笁杈归攣銆乫ooter 涓夊舰鎬併€乨erived_total銆乸refill锛壜?JC-7锛坮emoveRow 鍥涘舰鎬侊級鍦ㄦ湰 lane 鍙湁 J2/J3 渚х殑灏戞暟绔欑偣锛屾棤 lane 涓撳睘澧為噺 路
馃敶 **JC-17锛堣法寰幆鍐荤粨涓嶅懡涓級鍦ㄦ湰 lane 椤婚噸鏂伴獙**锛欽2/J3 鐨勯敭鍚屾牱鏃犺法寰幆娑堣垂锛?浣?orphan 绨囧垹闄ゅ悗 `events/publish` 涓?`cross-wp-references/batch` 涓ゆ潯鑱斿姩浼氫竴骞舵秷澶憋紙瑙?JN-3锛夈€?
---

## JN-1銆€銆屼笉鏄?entry銆嶆槸鍙绠楃殑缁撹锛屼笉鏄仐婕?
### 鍥涗晶鍒ゆ嵁

```
鈶?selection_rule 鐜扮畻 entry 闆嗗悎 == {xlsx/j1/gt-j1-employee-compensation}   鎭?1 鏉?鈶?manifest 閲屾棤浠讳綍 entry 鐨?host_path == J2/J3 瀹夸富璺緞
鈶?涓ゅ涓诲灞?<template> 閲?GtOnlyOfficeSheet 涓?el-segmented 鍛戒腑鍚?0
鈶?htmlRendererRegistry 閲?j2-defined-benefit-plan / j3-share-based-payment 鐨?import 鐪熸寚鍚戣繖涓ゆ枃浠?```

**涓轰粈涔堝洓渚ч兘瑕侀獙**锛氬彧楠?鈶?浼氳銆屾湁浜烘墜鍐欒ˉ涓ゆ潯 entry銆嶇粫杩囷紱鍙獙 鈶?浼氭紡鎺夈€屽涓荤‘瀹炲彲杈俱€?杩欎釜浜嬪疄鑰屾妸瀹冧滑褰撴垚姝荤粍浠讹紱鍙獙 鈶?浼氬緱鍑恒€屽彲杈?鈬?搴旇鏄?entry銆嶇殑閿欒鎺ㄨ銆?鍥涗晶鍚堣捣鏉ユ墠璇村緱娓呫€?*浜у搧涓婂彲杈撅紝OO 渚ф棤鍏ュ彛锛屽洜姝や笉鏄?entry**銆嶃€?
馃敶 **绂佹妸 J2/J3 鎵嬪啓杩?manifest**锛氳繚鍙?slice step 1 鐨?forbidden銆屾墜鎶?entry 鍒楄〃銆嶏紝
涓旇 `selection_rule` 涓嶅啀鍙绠椼€?
### 瀹夸富 import 娈靛疄娴嬶紙璇佹槑銆屾棤 OO 渚у叆鍙ｃ€嶄笉鏄寽鐨勶級

涓ゅ涓荤殑 import 娈靛彧鏈?`CycleTabProcedure` + `useChecklistPersistence` +
`useWorkpaperScaffold` + `useWorkpaperReviewThreads` 鈥斺€?鏃?OO 缁勪欢銆佹棤 dual-mode composable銆?J2 瀹夸富 238 琛屽師濮?/ 226 鍓ユ敞閲婏紱J3 瀹夸富 210 / 196銆?
---

## JN-2銆€馃敶 鍙揪鎬у垽瀹氾紙涓ら樁锛夎€屼笉鏄叆搴﹀垽瀹?鈥斺€?鏈?lane 鐨勬牳蹇冩柟娉?
### 涓轰粈涔堝叆搴﹀垽瀹氫細澶辨晥

`useJ2DualMode.ts` 鐨?statement-position 杈规暟鏄?**2**锛坆arrel + 1 涓?spec锛夈€?鏈寸礌鍒ゆ嵁銆屽叆搴?> 0 鈬?涓嶆槸瀛ゅ効銆嶄細**鏀惧畠杩囧幓**銆?鐪熺浉锛氶偅鏉＄敓浜ц竟鎸囧悜鐨?barrel `composables/workpaper/j2/index.ts` **鑷韩鍏ヨ竟涓?0** 鈥斺€?鍏ㄤ粨娌℃湁浠讳綍鏂囦欢 import `@/composables/workpaper/j2`锛圝2 瀹夸富涓?6 涓瓙 Tab 閮借蛋**閫愭ā鍧楁繁閾?*锛夈€?
### 涓ら樁鍒ゅ畾閰嶆柟

```
涓€闃?orphan : statement 鐢熶骇杈?== 0 涓旀祴璇曡竟 == 0
浜岄樁 orphan : 鍏ㄩ儴鐢熶骇杈归兘鎸囧悜鍚屼竴鐩綍鐨?barrel index.ts锛屼笖璇?barrel 鐨勫叆杈?== 0
```

### 4 涓?orphan 鐜扮畻

| id | 妯″潡 | 琛屾暟 | 闃?| 鐢熶骇杈?| 娴嬭瘯杈?| barrel 鍏ヨ竟 |
|---|---|---|---|---|---|---|
| OD-1 | `components/workpaper/composables/useJ2EntryDualMode.ts` | **41** | 涓€闃?| **0** | **0** | 鈥?|
| OD-2 | `components/workpaper/composables/useJ3EntryDualMode.ts` | **37** | 涓€闃?| **0** | **0** | 鈥?|
| OD-3 | `composables/workpaper/j2/useJ2DualMode.ts` | **35** | 馃敶 浜岄樁 | 1锛坆arrel锛?| 1锛坰pec锛?| 馃敶 **0** |
| OD-4 | `composables/workpaper/j3/useJ3DualMode.ts` | **39** | 馃敶 浜岄樁 | 1锛坆arrel锛?| 0 | 馃敶 **0** |

### OD-1 / OD-2 鐨?sheet 鏄犲皠琛細鎺ヤ笂灏卞潖

| orphan | 鏄犲皠甯搁噺 | 鐩爣鏁?| 妯℃澘鐪熷疄 sheet 鏁?| 鍛戒腑 |
|---|---|---|---|---|
| OD-1 | `J2_SHEET_MAP` | **8** | 9 | 馃敶 **0/8** |
| OD-2 | `J3_SHEET_MAP` | **4** | 6 | 馃敶 **0/4** |

`J2_SHEET_MAP` 鐨?8 涓洰鏍囨槸 `J2-鐩綍` / `J2A` / `J2-1`..`J2-4` / `J2闄勬敞(涓婂競)` / `J2闄勬敞(鍥戒紒)`锛?妯℃澘鐪熷疄 9 寮犳槸 `搴曠鐩綍` / `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 J2A` / `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 L2A` /
`瀹″畾琛↗2-1` / `闄勬敞鎶湶淇℃伅锛堜笂甯傚叕鍙革級` / `闄勬敞鎶湶淇℃伅锛堝浗鏈変紒涓氾級` / `鏄庣粏琛↗2-2` /
`璋冩暣鍒嗗綍姹囨€昏〃J2-3` / `璁℃彁鎯呭喌妫€鏌ヨ〃J2-4` 鈬?**涓€涓兘瀵逛笉涓?*銆?
鈬?鍗充究鏈変汉鎶婂畠鎺ヤ笂瀹夸富锛孫O 渚т細鎸?*涓嶅瓨鍦ㄧ殑 sheet 鍚?*鍘诲彇 鈬?杩欐槸銆屾帴涓婂氨鍧忋€嶄笉鏄€屾帴涓婅兘鐢ㄣ€嶃€?鍒ゆ嵁 SHALL 涓や晶閮介獙锛氭槧灏勭洰鏍囨暟鐜扮畻 == 8 / 4锛屼笖涓?`sheetnames` 鐨勪氦闆?== **绌洪泦**銆?
### OD-4 鐨勮繚瑙勭洿璋?
```
composables/workpaper/j3/useJ3DualMode.ts:
  http.get('/api/workpapers/onlyoffice/health')      馃敶 鍛戒腑 legacy_deletion_paradigm step 6 鏄庣椤?```

璇ョ鐐圭殑璋冪敤**鍙兘閫氳繃 sync bridge 鐨?materialize 鍗忚**銆傚畠鐜板湪鏃犲嵄瀹冲彧鍥犳暣涓ā鍧椾笉鍙揪锛?椤虹潃 barrel 鎺ヨ捣鏉ュ氨鏄竴鏉?*缁曡繃 bridge 鐨勬梺璺?*銆?SHALL 涓€骞剁櫥璁帮細瀹冭嚜甯︾殑 `checkOOHealth` 涓庡叡浜熀绫荤殑瀹炵幇**閲嶅涓旀洿寮?*
锛堟棤 `_silent`銆佹棤淇″皝鍙屽舰鎬佸吋瀹癸級銆?
### 涓や釜 orphan barrel + 馃敶 涓嶅緱杩囧害瀹ｇО

`composables/workpaper/j2/index.ts` 涓?`j3/index.ts` 鍏ヨ竟鍚?**0**銆?馃敶 浣?SHALL **涓嶅绉?*鏁翠釜 `composables/workpaper/j3/` 鐩綍閮芥槸姝荤殑 鈥斺€?鍚岀洰褰曠殑 `useJ3ImportExport.ts` 鏈変竴鏉?*鐪熷疄鐢熶骇杈?*锛坄j3/core/J3TabDetail.vue` 璧版繁閾捐€岄潪 barrel锛夈€?杩囧害瀹ｇО浼氳銆屽垹鏁翠釜鐩綍銆嶅彉鎴愪竴涓湅璧锋潵鏈変緷鎹殑閿欒鍔ㄤ綔銆?
### 鍏变韩鍩虹被淇濈暀 + 馃敶 绐勫彛寰?
```
useWorkpaperEntryDualMode.ts     65 琛?/ localStorage 0
statement 绐勫彛寰勬秷璐硅竟            29锛堢幇绠楋級
J 寰幆璐＄尞                        3锛圤D-1 + OD-2 + J1 瀹夸富锛?鍒犲畬 J 鐨勫伐浣滃悗鍓?                26
馃敶 瀹藉彛寰勭幇绠?                    34   鈬?鐢ㄥ鍙ｅ緞浼氬緱 31锛岃銆屽垹瀹岃繕鍓╁灏戙€嶈涓嶆竻
馃敶 瀹解垝绐勫樊闆嗙幇绠?                 5 涓紙JC-16锛泂lice 璁?1 涓凡澶辨晥锛?```

鍒ゆ嵁 SHALL 鐢?*绐勫彛寰?*锛堢湡璇彞杈癸級锛屽苟鎸?JC-16 鍐欍€屽樊闆?*鍖呭惈**
`workpaperSyncLegacyBaseline.generated.ts`銆? 鐜扮畻娓呭崟锛岀鍐欐涓暟銆?
### 鍒犻櫎涓変欢浜嬮綈澶囨墠鍔ㄦ墜

鈶?鍒犲墠涓ら樁鍙揪鎬у垽瀹氭垚绔?鈶?鍒犲墠鍚庡叏濂楁祴璇曢浂鍥炲綊 鈶?鐙珛 commit锛堜究浜庡洖婊氾級
馃敶 涓?SHALL **鎸夊凡鏈夌殑 `backend/data/workpaper_sync_j_cycle_deletion_plan.json` 鎵ц锛屼笉鍙﹁捣璁″垝**銆?
---

## JN-3銆€`useJ3FormData.ts`锛氫笁鏉″叆杈逛絾鏁寸皣涓嶅彲杈?
### 鐜扮畻

```
composables/workpaper/j3/useJ3FormData.ts     151 琛?鍏ヨ竟 3 : j3/index.ts锛坆arrel锛?+ useJ3Detail.ts + useJ3Integration.ts
鍏朵腑   : useJ3Detail 鑷韩鍏ヨ竟 1锛堝彧鏈?barrel锛?         useJ3Integration 鑷韩鍏ヨ竟 0
鈬?涓夎€呮瀯鎴愪竴涓彧缁忓绔?barrel 鐩歌繛鐨勭皣锛屼粠浠讳綍鐪熷疄瀹夸富閮戒笉鍙揪
```

馃敶 **鍒ゆ嵁涓嶈兘鍙湅涓€灞?*锛氱湅涓€灞備細寰椼€屽叆杈?3 鈬?娲荤潃銆嶏紱鐪嬩袱灞傛墠鐪嬪嚭鏁寸皣涓嶅彲杈俱€?
### 瀹冨惈瀹屾暣鎸佷箙鍖栫閬擄紙杩欐墠鏄嵄闄╂墍鍦級

```
GET  /api/workpapers/{wpId}/render-config
PUT  /api/workpapers/{wpId}/checklist-responses
POST /api/projects/{projectId}/events/publish
item_id 褰㈡€?: `J3-${key}`        馃敶 鐢熶骇璺緞浠庢湭鍐欒繃杩欑褰㈡€?verdict      : FABRICATED_KEY_SHAPE_NEVER_WRITTEN_IN_PRODUCTION
```

J3 鐨勭湡瀹為敭鏄?*涓変釜瀛?Tab 鍚勮嚜 `KEY` 瀵硅薄閲岀殑瀛楅潰閲?*锛坄J3-1-plans` / `J3-2-vouchers` 绛夛級銆?鈬?鍒楀叆 `forbidden_carriers`锛?*鏀圭嚎鏃舵渶瀹规槗璇帴鐨勪笢瑗?*锛夈€?
### 瀵圭収 J2 渚э細椋庨櫓宸茶嚜鐒舵秷瑙?
`useJ2FormData.ts` **宸茶鐗╃悊鍒犻櫎**锛坰lice 2026-09-14 鏇存柊璁拌浇鐨勫姩浣滃凡鍏戠幇锛岀幇绠楁枃浠朵笉瀛樺湪锛?鈬?涓嶅啀鏈夊彲璇帴鐨勫疄浣撱€傛湰 lane SHALL 鏂█璇ヨ矾寰?*涓嶅瓨鍦?*锛屼綔涓恒€屽垹闄ゅ姩浣滅湡鐨勫仛浜嗐€嶇殑姝ｄ緥閿氱偣銆?
### 馃敶 鍒犻櫎鐨勮繛甯﹀奖鍝嶏紙JC-17 鍦ㄦ湰 lane 椤婚噸楠岋級

`useJ3FormData` 涓?`useJ3Integration` 閲屾湁 `events/publish`锛? 澶勶級涓?`cross-wp-references/batch`锛? 澶勶級涓ゆ潯鑱斿姩銆傚畠浠殢鏁寸皣鍒犻櫎浼?*涓€骞舵秷澶?*銆?鈬?鏈?lane SHALL 鍦ㄥ垹闄ゅ墠**鏄惧紡纭杩欎簺鑱斿姩鏄惁杩橀渶瑕?*锛堢幇鐘讹細鏁寸皣涓嶅彲杈?鈬?杩欎簺鑱斿姩鏈潵灏辨病璺戣繃锛夈€?
### J3 鐨勭湡瀹炲啓璺緞锛堟湰杞疄娴嬭秴鍑?slice锛?
```
鈶?瀹夸富缁?useChecklistPersistence锛圝C-2 绗笁绉嶆棌锛?鈶?馃敶 j3/core/J3TabDetail.vue 鑷繁涔熺洿鍐?PUT /api/workpapers/{wpId}/checklist-responses
```

馃敶 slice 璇?J3 璧板涓婚€傞厤鍣紝**鏈彁 鈶?杩欐潯鐩村啓** 鈬?鏈?lane 椤荤櫥璁般€?
---

## JN-4銆€non_entry 渚?5 澶勪綅缃寲韬唤锛圝C-6 鐨勫疄渚嬪寲锛?
| 鏃?| 绔欑偣 | 琛ㄨ揪寮?| 鍐欏叆閿?| 鐪熷簱璇佹嵁 |
|---|---|---|---|---|
| 馃敶 **A 绾簭鍙风湡钀藉簱** | `j2/J2TabAdjustment.vue` | `id: i + 1` | `J2-3-entries` | 馃敶 **171 B 杞借嵎閲?`"id":1` 宸茶惤搴?* |
| B 涓嬫爣鍏滃簳 | `j2/J2TabAdjustment.vue` | `id: e.id ?? i + 1` | 鍚屼笂 | 鈥?|
| B 涓嬫爣鍏滃簳 | `j3/core/J3TabDetail.vue` | `id: p.id ?? i + 1` | `J3-1-plans` | 251 B 鏈夎浇鑽?|
| B 涓嬫爣鍏滃簳 | `j3/core/J3TabCheck.vue`锛?*涓ゅ**锛?| `id: r.id ?? i + 1` | `J3-2-vouchers` 绛?| 165 B 鏈夎浇鑽?|

鍚堣 **5 澶?*锛坒amily_a 1 + family_b 4锛夈€?
### family_a 鐨勪弗閲嶆€х敤鐪熷簱瀹炶瘉锛屼笉鐢ㄦ帹婕?
```
J2-3-entries 鐪熷簱 171 B:
[{"id":1,"description":"閲嶅垎绫讳竴骞村唴鍒版湡杈為€€绂忓埄","category":"璐﹂」璋冩暣",
  "reportItem":"闀挎湡搴斾粯鑱屽伐钖叕","accountName":"","noteItem":"",
  "debitAmount":0,"creditAmount":0,"indexRef":"","remark":""}]
```

鈬?`"id":1` **鐪熻惤搴?*銆傚垹涓棿涓€琛屽啀鏂板锛屽悗缁 id 鍏ㄩ儴宸︾Щ銆佸巻鍙插娉ㄤ笌閲戦涓插埌鍙︿竴绗斿垎褰曘€?馃敶 杩欐槸鍏?J 鍩?*鍞竴**鐨?family_a锛屼笖**宸叉湁鐪熷疄鏁版嵁鍙楀奖鍝?* 鈬?鏈?lane 鐨勬渶楂樹紭鍏堜慨椤广€?
### 淇硶涓?grandfather

family_a 鎹㈠畨鍏ㄧ敓鎴愬櫒锛堝惈 `Math.random()` 涓斿洖钀藉垎鏀笉鏄笅鏍囷紝鍙ｅ緞瑙?JC-6锛夛紱
馃敶 **宸茶惤搴撶殑 `id: 1..N` 涓€寰?grandfather 涓嶉噸鍐?*锛堟敼瀹冪瓑浜庢崲韬唤锛夛紱
濂戠害灞傚０鏄?`legacy_ordinal_ids_grandfathered: true`銆?family_b 鍥涘鍙敼**鍥炶惤鍒嗘敮**锛屼繚鐣欍€屼笂娓告湁 id 鏃朵紭鍏堢敤涓婃父 id銆嶈涔夈€?
### J2 渚ф姭闇插眰鍚屽瀷澶嶆牳

`J2TabDisclosureListed.vue`锛?*11 閿?*锛変笌 `J2TabDisclosureSoe.vue`锛?*9 閿?*锛夋槸涓?J1 鍚屽瀷鐨勫弻鍙樹綋鎶湶 Tab
鈬?JC-6 鐨?JD-7銆?9 涓‖缂栫爜 id + 鍥涙潯鐪熷疄椋庨櫓銆峉HALL 鍦?J2 渚?*鍚屽彛寰勫鏍?*
锛堟湰 lane 鍙仛澶嶆牳涓庣櫥璁帮紝**涓嶅杩?* JC-6 姝ｆ枃锛涗慨娉曟爣 `[ ]*`锛屾秹鐢ㄦ埛鍙鎶湶鍙ｅ緞锛夈€?
### 浼犺緭閿?owner锛氬彧鍐荤粨宸茬櫥璁扮殑甯搁噺锛屼笉鍐荤粨鍏ㄩ泦

```
J2 : 6 涓瓙 Tab 鍚勮嚜鐨勭粍浠跺眬閮?KEY 瀵硅薄   馃敶 J2TabIndex.vue 鏃?KEY 瀵硅薄锛堝彧璇讳笉鍐欙級
J3 : 3 涓瓙 Tab 鍚勮嚜鐨勭粍浠跺眬閮?KEY 瀵硅薄   馃敶 J3TabIndex.vue 鏃?KEY 瀵硅薄
```

馃敶 **slice 棣栫増鎶?`J3TabIndex` 鍒楄繘 owner 娓呭崟锛岃瀹堝崼鎵撶孩鏀规** 鈥斺€?鎵€浠ャ€屽洓涓?Tab銆嶈繖涓暟鏄敊鐨勩€?*瀹炰负涓変釜**銆傛湰 lane 鎶婅繖鏉℃敼姝ｈ繃绋嬩竴骞剁櫥璁帮紝
璁╁悗鏉ヨ€呯煡閬撱€屼笁涓€嶆槸琚獙璇佽繃鐨勮€屼笉鏄妱婕忎簡涓€涓€?
馃敶 **涓嶅喕缁?J2/J3 鐨勯敭鍏ㄩ泦**锛氬畠浠笉鏄?entry锛屽喕缁撳叏闆嗕細閫犲嚭涓€浠?*娌℃湁娑堣垂鏂圭殑姝诲０鏄?*
锛坅dditive 娉ㄥ叆鍗虫浠ｇ爜锛夈€傚垽鎹彧楠屼袱浠朵簨锛?鈶?鐪熷疄褰㈡€?== 鍚?Tab 鐨勫瓧闈㈤噺 `KEY` 瀵硅薄 鈶?orphan 杞戒綋鐨勫舰鎬侊紙`J3-${key}`锛夆墵 鐪熷疄褰㈡€併€?
---

## JN-5銆€妯℃澘灞傦細definedName 鏂摼鏄湰 lane 鏈€閲嶇殑鎶€鏈€?
### 鐜扮畻鍩虹嚎 + 鏂摼鏁?
| 鍐?| definedName | 鍚?`#REF!` | 鍗犳瘮 | 瑁?IF | retired sheet |
|---|---|---|---|---|---|
| J2 | **37** | **30** | 81% | **12**锛堝叏鍦?`瀹″畾琛↗2-1`锛?| **0** |
| J3 | 馃敶 **502** | 馃敶 **479** | **95%** | 馃敶 **0**锛堟暣鍐岋級 | **0** |

### J3 鐨?502 涓槸璺ㄥ惊鐜鍒舵畫鐣欙紙閫愭潯瀹炴祴鍚嶅瓧锛?
```
_1鍥哄畾璧勪骇鏁版嵁搴揰绛涢€夋墦鍗?                鈫?H 寰幆锛堝浐瀹氳祫浜э級
_2鍏朵粬璧勪骇_寮€鍔炶垂闄ゅ_鏄庣粏琛?              鈫?K 寰幆锛堝叾浠栬祫浜э級
_2銆佷富瑕佷笟鍔℃椿鍔?                         鈫?B 寰幆锛堟帶鍒朵簡瑙ｏ級
_1銆佸彈鏈惊鐜奖鍝嶇殑鐩稿叧浜ゆ槗鍜岃处鎴蜂綑棰?        鈫?B 寰幆
_.dbf  /  AS2DocOpenMode  /  _00510  /  _13  /  _1w6_
```

杩欎簺鍚嶅瓧涓庤偂浠芥敮浠樹笟鍔℃鏃犲叧绯?鈬?鏄粠鍒殑宸ヤ綔绨垮鍒舵ā鏉挎椂甯﹁繘鏉ョ殑銆?
馃敶 **瑁佸喅锛氫笉鍒?*锛堝垹浼氳 `max_column` 鍐呯殑鍏紡鏁寸墖澶辨晥锛夛紝鍙０鏄庛€屽悓姝ユ椂涓嶆柊澧炪€佷笉鏀瑰啓銆嶏紱
娓呯悊 definedName 灞?*妯℃澘娌荤悊**鍙︿竴鏉￠摼璺紝鏍?`[ ]*`銆?馃敶 **姣?I 寰幆涓ラ噸涓€绾?*锛欼 鏄€宒efinedName 闈?0銆嶏紙I4 476 / I5 334锛?*鏈煡鏂摼**锛夛紱
J 鏄€岄潪 0 **涓旂粷澶у鏁版柇閾?*銆嶃€?
### `鏄庣粏琛↗2-2` 鍏瓙鍖?鈫?鍏敭涓€涓€瀵瑰簲

| 瀛愬尯 | 琛?| footer 鍏紡 | 瀵瑰簲閿?|
|---|---|---|---|
| 涓昏〃 | R11-18锛堜袱绾ц〃澶?R11/R12锛?| R18 `=C13+C16-C17` | `J2-2-main` |
| 鍒版湡鍒嗘瀽 | R20-27 | R27 `=SUM(C22:C26)`锛堭煍?鍚鐣欑┖琛?R26锛?| `J2-2-maturity` |
| 璁惧畾鍙楃泭璁″垝鎯呭喌 | R30-47 | R47 `=C32+C33+C38-C43`锛涴煍?**涓夌骇宓屽** R38 `=C39` 鈫?R39 `=SUM(C40:C42)` | `J2-2-dbp-status` |
| 璁″垝璧勪骇 | R49-61 | R61 `=C51+C52+C56+C60` | `J2-2-plan-assets` |
| 绮剧畻鍋囪 | R63 璧?| 鈥?| `J2-2-assumptions` |
| 鏁忔劅鎬у垎鏋?| 鏈尯 | 鈥?| `J2-2-sensitivity` |

r=90 c=14 f=221 merged=30銆?馃敶 **鍒楄涔変笌 `鏄庣粏琛↗1-2 ` 閫愬瓧鐩稿悓**锛圓 搴忓彿 / B 椤圭洰鍚嶇О / C-F 鏈鏁癧鏈熷垵,鏈湡澧?鏈湡鍑?鏈熸湯] /
G 鏈熷垵璋冩暣 / H-I 璐﹂」璋冩暣 / J-M 瀹″畾鏁癧鏈熷垵,鏈湡澧?鏈湡鍑?鏈熸湯] / N 澶囨敞锛?鈬?灏嗘潵 J2 鎺?OO 鍏ュ彛鏃?*濂戠害鍙叡鐢ㄥ垪鏄犲皠**锛屼笉蹇呴噸瑁併€傛湁鏁堝垪 14 == max_column 鈬?UUID 鍒?**15**銆?
### `鑲′唤鏀粯鎯呭喌琛↗3-1`锛氭暣琛ㄩ浂涓氬姟鍏紡

```
r=43  c=18  f=7      馃敶 閭?7 涓叕寮忓叏鏄?R3/R4 鐨?=搴曠鐩綍!A2 / A3
鏁版嵁鍖?R20-27        R21 = '浠ユ潈鐩婂伐鍏风粨绠?锛孯22-27 绌?footer               馃敶 鏃犲悎璁¤
鏈夋晥鍒?14 vs max_column 18锛堝樊 4锛夆噿 UUID 鍒?15
14 鍒楄涔?           A 鑲′唤鏀粯椤圭洰鍚嶇О / B 绫诲瀷 / C 鎺堜簣鏃?/ D 鎵瑰噯閮ㄩ棬 / E 琛屾潈鏃?/
                     F 鏉冪泭宸ュ叿鏁伴噺 / G 绛夊緟鏈?/ H 鍏厑浠峰€肩‘瀹氭柟娉曞拰鏁版嵁鏉ユ簮 /
                     I 鍗忚鍙樻洿銆佸彇娑堟儏鍐?/ J 璧勪骇璐熷€鸿〃鏃ヤ及璁℃洿鏂版儏鍐?/ K 鍓╀綑绛夊緟鏈熼檺 /
                     L 鍗忚绱㈠紩鍙?/ M 鑲′唤鏀粯璁＄畻琛ㄧ储寮曞彿 / N 缁撹
```

鈬?J3 鏄?*闆跺叕寮忚〃鍗?*锛屼笌 D~I 鐨勬墍鏈?entry 褰㈡€侀兘涓嶅悓銆?
### 馃敶 J3 鏃犲瀹氳〃涓旀棤鐙珛绉戠洰

6 寮?sheet 閲?*娌℃湁** `瀹″畾琛↗3-*`锛坄搴曠鐩綍` / `鑲′唤鏀粯瀹炶川鎬х▼搴忚〃 J3A` / `鑲′唤鏀粯鎯呭喌琛↗3-1` /
`鑲′唤鏀粯妫€鏌ヨ〃J3-2` / `IPO浼佷笟鑲℃潈婵€鍔卞伐鍏峰叧娉ㄧ殑瀹¤閲嶇偣` / `棣栧彂涓氬姟瑙ｇ瓟浜宍锛夈€?瀹夸富 docstring 鏄庡啓銆岃垂鐢ㄧ璧?K8/K9锛屾潈鐩婄璧?M4锛岀幇閲戠璧?J1銆?鈬?鍗充究灏嗘潵鎺?OO 鍏ュ彛锛屽畠鐨勫瀹氳〃涔?*涓嶅洖鍐?`trial_balance`**
鈬?鍒ゆ嵁 SHALL **涓嶈姹?* J3 鏈?TB 鍙戝竷闂紙瑕佹眰浜嗗氨鏄亣绾級銆?
### sheet 鍚嶄笌涓插唽

J2/J3 **鏃犲熬閮ㄧ┖鏍?*锛?*鍚嶄腑绌烘牸 3 寮?*锛坄闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 J2A` 路 `鈥2A` 路
`鑲′唤鏀粯瀹炶川鎬х▼搴忚〃 J3A`锛夌 strip銆?馃敶 `闀挎湡搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 L2A` 鐜扮畻鏄?**hidden**锛坰lice 鏈 hidden锛変笖灞?**L 寰幆**涓插唽
鈥斺€?涓?J1 鍐岀殑 `搴斾粯鑱屽伐钖叕瀹炶川鎬х▼搴忚〃 L1A-鍘焋锛堭煍?slice 婕忚锛夊悓鍨嬶紝涓ゅ閮界櫥璁颁笉淇€?
### 骞插噣鐐癸紙鎸?JC-20 绌哄垎姣嶇邯寰嬶級

J2/J3 鐨勮秺鐣屽紩鐢?**0** 路 瀹借〃锛坢ax_column 鈮?200锛?*0** 路 Excel Table **0** 路 retired sheet **0**
鈬?涓€寰嬪啓銆岀幇绠椾负 0 涓斾笉鏄紡鎵€嶏紝骞跺鐢ㄥ凡鏈夊彉寮傝剼鏈瘉鏄庨潪绌鸿窇銆?
---

## JN-6銆€J2/J3 鎺ュ叆鍓嶇疆娓呭崟锛堢櫥璁帮紝涓嶆墽琛岋級

| # | 椤?| 鐜扮姸 | 缂哄彛 / 娉ㄦ剰 |
|---|---|---|---|
| 鈶?| 瀹夸富鎸?`GtOnlyOfficeSheet` | **0** | 鎸備笂鍚庢墠浼氳 `selection_rule` 鏋氫妇鎴?entry |
| 鈶?| `el-segmented` 妯″紡鍒囨崲鍣?+ **浜岀骇闂ㄦ帶** | **0** | 馃敶 **涓嶅緱閲嶆紨 J1 鐨勬棤澹板け璐?*锛圝C-15锛?|
| 鈶?| dual-mode composable | 馃敶 鐜版湁 4 涓?*鍏ㄦ槸 orphan** | 馃敶 **涓€涓兘涓嶈兘鎺?*锛坰heet 鏄犲皠鍏ㄩ敊 + OD-4 杩濊鐩磋皟锛夛紱搴斿鐢ㄥ叡浜熀绫伙紙鐓?J1 鐨?JD-2 褰㈡€侊級 |
| 鈶?| `GtEntrySyncCapabilityNotice` + 鏂囨鐪熸簮 | **0** | 鏂囨鐪熸簮蹇呴』鏄?`workpaperEntrySyncNotice.ts` |
| 鈶?| per-entry contract | **0** | 馃敶 **J2 鐨勫垪鏄犲皠鍙叡鐢?J1 鐨?14 鍒楄涔?*锛圝N-5锛夛紱濂戠害椤诲悓鏃惰鐩?disclosure-notes 閭ｆ潯璺緞 |
| 鈶?| TB 鍙戝竷闂?| J2 寰呭畾 / 馃敶 **J3 涓嶉渶瑕?* | J3 鏃犵嫭绔嬬鐩紙JN-5锛夆噿 瑕佹眰瀹冩湁闂ㄥ氨鏄亣绾?|
| 鈶?| `wp_guidance` | J3 鏈?/ 馃敶 **J2 缂?* | **鐧昏涓嶈ˉ**锛圝2 涓嶆槸 entry锛岀幇鍦ㄨˉ鍗虫浠ｇ爜锛夛紱鎺ュ叆鏃朵竴骞惰ˉ |
| 鈶?| render schema | 馃敶 **涓や唤閮藉凡瀛樺湪** | `j2-defined-benefit-plan.yaml` / `j3-share-based-payment.yaml` 鈬?鎺ュ叆鏃?*涓嶉噸閫?* |

### J2/J3 鐪熷簱閮芥湁闈炵┖杞借嵎 鈬?灏嗘潵婊¤冻 canary 纭爣鍑?
```
J2 : J2-2-dbp-status 2731 B 路 J2-soe-change 2556 B 路 J2-2-plan-assets 1581 B 路
     J2-1-dbo 1503 B 路 J2-2-main 1101 B 路 J2-2-maturity 842 B 路 J2-1-main 583 B 路
     J2-soe-assets 520 B 路 J2-4-measurement 527 B 路 鈥?路 J2-3-entries 171 B
J3 : J3-2-variation 288 B 路 J3-1-plans 251 B 路 J3-2-vouchers 165 B 路 J3-1-expert 121 B
     锛堝彟 6 涓?J3 閿?remark 涓虹┖涓诧級
```

馃敶 鏈?lane SHALL 鎶婅繖涓粨璁?*鏄惧紡鐧昏缁欎笅涓€杞?*锛欽2/J3 鎴愪负 entry 鏃?*婊¤冻 canary 纭爣鍑?*
锛堝姣?J1 鐨?primary managed table 涓夐敭鐪熷簱鍏ㄧ┖锛屽弽鑰屼笉婊¤冻锛夈€?
### 瀛愮爜瑙ｆ瀽鐨勫弽鐩磋锛堟帴鍏ユ椂涓嶅緱璇垽锛?
`J2-5..J2-10` 涓?`J3-3..J3-10` 杩欎簺**婧愭ā鏉块噷骞朵笉瀛樺湪瀵瑰簲 sheet** 鐨勫瓙鐮侊紝
涓や釜瑙ｆ瀽鍑芥暟**浠嶈繑鍥炲悇鑷殑鍐?*锛堟寜鍐屽墠缂€瑙ｆ瀽鑰岄潪鎸?sheet锛?鈬?鎺ュ叆鏃跺垽鎹?*涓嶅緱鍐?*銆岃В鏋愮粨鏋滈潪 None 鈬?璇?sheet 瀛樺湪銆嶏紙JC-11锛夈€?
### 鍐欒矾寰勪笌浜嬩欢璺緞鍏ㄦ竻鍗曪紙鎺ュ叆鏃跺绾﹀繀椤昏鐩栵級

```
J2 : PUT  /api/workpapers/{wpId}/checklist-responses            锛堝涓荤粡 useChecklistPersistence锛?     POST /api/projects/{projectId}/disclosure-notes/sync-from-workpaper   馃敶 涓や釜鎶湶 Tab锛屽啓鍙︿竴寮犺〃
     POST /api/projects/{projectId}/events/publish              锛坲seJ2CrossSheet锛?     GET  /api/workpapers/{wpId}/render-config                  锛坲seJ2CrossSheet锛?     POST /api/workpapers/{wpId}/j2/{import-data|export-data|export-template}
J3 : PUT  /api/workpapers/{wpId}/checklist-responses            锛堝涓?+ 馃敶 J3TabDetail.vue 鐩村啓锛?     POST /api/projects/{projectId}/events/publish              锛堭煍?閮ㄥ垎鍦?orphan 绨囧唴锛屽垹闄ゅ悗娑堝け锛?     POST /api/projects/{projectId}/cross-wp-references/batch    锛堭煍?鍦?orphan 绨囧唴锛?     POST /api/workpapers/{wpId}/ai/generate-text                锛? 涓瓙 Tab锛?     POST /api/workpapers/{wpId}/import-export/{import|export|template}
```

---

## JN-7銆€鏈?lane 鐨勪氦浠樿竟鐣岋紙鏄庣‘鍐欐锛岄槻瓒婄晫锛?
### 鏈?lane **浜や粯**

orphan 鍒犻櫎锛? 涓?+ `useJ3FormData` 绨囷級路 non_entry 5 澶勪綅缃寲淇 路
definedName 鏂摼鐧昏 + 涓嶅闀挎柇瑷€ 路 J2 渚ф姭闇插眰 49 纭紪鐮?id 鍚屽彛寰勫鏍?路
J2/J3 妯℃澘鍑犱綍鐧昏 路 鎺ュ叆鍓嶇疆娓呭崟 8 鏉?路 闆跺洖褰掋€?
### 鏈?lane **涓嶄氦浠?*锛堝啓鏄庣悊鐢憋級

| 涓嶄氦浠橀」 | 鐞嗙敱 |
|---|---|
| per-entry contract | J2/J3 涓嶆槸 manifest entry |
| adapter 娉ㄥ唽 | 鍚屼笂 |
| roundtrip / evidence | 鍚屼笂锛堟病鏈?entry 灏辨病鏈?scenario set锛?|
| canary | 鍦板熀 spec 宸蹭氦浠?`J1-6-short-term` |
| definedName 娓呯悊 | 灞炴ā鏉挎不鐞嗗彟涓€閾捐矾锛堝垹浼氳鍏紡鏁寸墖澶辨晥锛?|
| `wp_guidance/J2.json` | J2 涓嶆槸 entry锛岀幇鍦ㄨˉ鍗虫浠ｇ爜 |
| BP-1 ~ BP-4 | 馃敶 **瀵规湰 lane 閮戒笉鏄樆濉?*锛堜笉鍙?contract 涓嶆敞鍐?adapter锛?|

馃敶 **銆孊P-1~BP-4 瀵规湰 lane 涓嶆槸闃诲銆嶅繀椤绘樉寮忕櫥璁?* 鈥斺€?鍚﹀垯鍚庢潵鑰呬細浠ヤ负鏈?lane 涔熷崱鍦ㄥ钩鍙颁緵缁欎笂锛?鑰屽畠鍏跺疄鍙互绔嬪埢瀹炴柦瀹屻€?
---

## Property锛圝N-P锛?
| # | Property | 寮曠敤 |
|---|---|---|
| JN-P1 | 鍥涗晶閮介獙 J2/J3 闈?entry锛坰election_rule 鐜扮畻 1 鏉?/ host_path 涓嶅湪 / OO 涓?segmented 鍚?0 / registry 鐪熸寚鍚戯級 | JN-1 |
| JN-P2 | 馃敶 绂佹妸 J2/J3 鎵嬪啓杩?manifest锛涘彉寮傘€屾墜鍐欒ˉ涓ゆ潯 entry銆峉HALL 鎵撶孩 | JN-1 |
| JN-P3 | 瀹夸富 import 娈靛疄娴嬪洓椤癸紙鏃?OO 缁勪欢銆佹棤 dual-mode锛夛紱琛屾暟 238/210 鍘熷 | JN-1 |
| JN-P4 | manifest entries 鎬绘暟**鐜扮畻**锛?55锛宻lice 鍐?186锛夛紱鍐欐璇ユ暟 SHALL 鎵撶孩 | JN-1 |
| JN-P5 | 馃敶 涓ら樁鍙揪鎬у垽瀹氾細OD-1/OD-2 涓€闃堕浂杈?路 OD-3/OD-4 浜岄樁锛堣竟 1锛宐arrel 鍏ヨ竟 0锛?| JN-2 |
| JN-P6 | 馃敶 鍙嶈瘉锛歚useJ2DualMode` 杈规暟 2锛屾湸绱犮€屽叆搴?0銆嶅垽鎹?SHALL 鏀惧畠杩囧幓鑰屾墦绾?| JN-2 |
| JN-P7 | 馃敶 `J2_SHEET_MAP` 8 鐩爣 / `J3_SHEET_MAP` 4 鐩爣涓?`sheetnames` 浜ら泦 == **绌洪泦** | JN-2 |
| JN-P8 | 馃敶 OD-4 鐩磋皟 `onlyoffice/health` 鍛戒腑 step 6 鏄庣锛涘叾 `checkOOHealth` 姣斿熀绫诲急锛堟棤 `_silent`锛?| JN-2 |
| JN-P9 | 涓や釜 barrel 鍏ヨ竟鍚?0锛涴煍?**涓嶅绉?*鏁翠釜 `j3/` 鐩綍姝伙紙`useJ3ImportExport` 鏈夌湡杈癸級 | JN-2 |
| JN-P10 | 鍏变韩鍩虹被淇濈暀锛涚獎鍙ｅ緞 29 / J 璐＄尞 3 / 鍒犲悗 26锛涴煍?瀹藉彛寰?34 浼氬緱 31 鈬?蹇呴』鐢ㄧ獎鍙ｅ緞 | JN-2 |
| JN-P11 | 馃敶 宸泦鍒ゆ嵁銆?*鍖呭惈**鐢熸垚鏂囦欢銆? 鐜扮畻娓呭崟锛堢幇绠?5 涓級锛岀鍐欐 1 涓?| JC-16 |
| JN-P12 | 馃敶 `useJ3FormData` 涓夋潯鍏ヨ竟浣嗘暣绨囦笉鍙揪锛堜袱灞傚垽瀹氾級锛涘彧鐪嬩竴灞?SHALL 鍒ゆ垚娲荤潃鑰屾墦绾?| JN-3 |
| JN-P13 | `useJ3FormData` 鐨?`J3-${key}` 褰㈡€佸湪鐢熶骇璺緞鍛戒腑 **0** 鈬?FABRICATED | JN-3 |
| JN-P14 | `useJ2FormData.ts` **涓嶅瓨鍦?*锛堝垹闄ゅ凡鍏戠幇锛夆€斺€?浣滀负銆屽垹闄ょ湡鍋氫簡銆嶇殑姝ｄ緥閿氱偣 | JN-3 |
| JN-P15 | 馃敶 鍒犻櫎鍓嶆樉寮忕‘璁?`events/publish` 3 澶?+ `cross-wp-references/batch` 1 澶勭殑鑱斿姩鏄惁杩橀渶瑕?| JN-3 |
| JN-P16 | 馃敶 `j3/core/J3TabDetail.vue` 鑷繁鐩村啓 checklist-responses锛坰lice 鏈彁锛夊凡鐧昏 | JN-3 |
| JN-P17 | non_entry 浣嶇疆鍖?**5 澶?*锛坒amily_a 1 + family_b 4锛夐€愭潯钀借〃 | JN-4 |
| JN-P18 | 馃敶 family_a 鐢?*鐪熷簱 171 B 杞借嵎**瀹炶瘉 `"id":1` 宸茶惤搴擄紝涓嶇敤鎺ㄦ紨 | JN-4 |
| JN-P19 | 宸茶惤搴?`id: 1..N` **grandfather 涓嶉噸鍐?*锛沗legacy_ordinal_ids_grandfathered: true` | JN-4 |
| JN-P20 | family_b 鍥涘鍙敼鍥炶惤鍒嗘敮锛屼繚鐣欎笂娓?id 浼樺厛璇箟 | JN-4 |
| JN-P21 | J2 渚ф姭闇插眰锛?1 閿?/ 9 閿級鎸?JD-7 鍚屽彛寰勫鏍革紱**涓嶅杩?* JC-6 姝ｆ枃 | JN-4 |
| JN-P22 | 馃敶 `J2TabIndex` / `J3TabIndex` **鏃?KEY 瀵硅薄**锛涖€屽洓涓?Tab銆嶆槸閿欑殑銆佸疄涓轰笁涓?| JN-4 |
| JN-P23 | 馃敶 **涓嶅喕缁?J2/J3 閿叏闆?*锛堜細閫犳棤娑堣垂鏂圭殑姝诲０鏄庯級锛涘彧楠岀湡瀹炲舰鎬?鈮?orphan 褰㈡€?| JN-4 |
| JN-P24 | definedName 鍩虹嚎 `{J2:37, J3:502}` + 馃敶 **鏂摼 `{30, 479}`** + 涓嶅闀?+ **涓嶅垹** | JN-5 |
| JN-P25 | 馃敶 J3 鐨?502 涓€愭潯鍒楄法寰幆鏉ユ簮鏍锋湰锛圚/K/B 寰幆鍚嶅瓧锛夎瘉鏄庢槸澶嶅埗娈嬬暀 | JN-5 |
| JN-P26 | 瑁?IF J2 **12** / 馃敶 J3 **0**锛沺er-file 鎸傦紱鏁村唽缁熶竴鎸?SHALL 鎵撶孩 | JN-5 |
| JN-P27 | `鏄庣粏琛↗2-2` 鍏瓙鍖?鈫?鍏敭涓€涓€瀵瑰簲锛涗笁绾у祵濂?R38鈫扲39鈫扲40:R42 | JN-5 |
| JN-P28 | 馃敶 J2 涓?J1 鐨?14 鍒楄涔?*閫愬瓧鐩稿悓** 鈬?鎺ュ叆鏃跺绾﹀彲鍏辩敤鍒楁槧灏?| JN-5 |
| JN-P29 | 馃敶 `鑲′唤鏀粯鎯呭喌琛↗3-1` **鏁磋〃闆朵笟鍔″叕寮?*锛? 涓叕寮忓叏鏄?`=搴曠鐩綍!A2/A3`锛壜?鏃?footer | JN-5 |
| JN-P30 | 馃敶 J3 鏃犲瀹氳〃 + 鏃犵嫭绔嬬鐩?鈬?鍒ゆ嵁**涓嶈姹?* J3 鏈?TB 鍙戝竷闂?| JN-5 |
| JN-P31 | 鍚嶄腑绌烘牸 3 寮犵 strip锛涴煍?`L2A` 鐜扮畻 hidden锛坰lice 鏈锛変笖灞?L 寰幆涓插唽 | JN-5 |
| JN-P32 | 骞插噣鐐瑰洓椤癸紙瓒婄晫 / 瀹借〃 / Excel Table / retired锛夊悇 0锛屾寜绌哄垎姣嶇邯寰?+ 鍙樺紓璇佹槑 | JN-5 |
| JN-P33 | 鎺ュ叆鍓嶇疆娓呭崟 **8 鏉?*閫愰」缁欑幇鐘朵笌缂哄彛 | JN-6 |
| JN-P34 | 馃敶 J2/J3 鐪熷簱閮芥湁闈炵┖杞借嵎 鈬?灏嗘潵婊¤冻 canary 纭爣鍑嗭紙涓?J1 primary 鍏ㄧ┖鐩稿弽锛?| JN-6 |
| JN-P35 | 瀛愮爜瑙ｆ瀽杩斿唽浣?sheet 涓嶅瓨鍦?鈬?鎺ュ叆鍒ゆ嵁涓嶅緱鍐欍€岄潪 None 鈬?瀛樺湪銆?| JN-6 |
| JN-P36 | 鍐欒矾寰勪笌浜嬩欢璺緞鍏ㄦ竻鍗曡惤琛紙J2 浜旂被 / J3 浜旂被锛?| JN-6 |
| JN-P37 | 馃敶 浜や粯杈圭晫琛細涓冮」涓嶄氦浠樺悇鏈夌悊鐢憋紱**BP-1~BP-4 瀵规湰 lane 涓嶆槸闃诲**椤绘樉寮忕櫥璁?| JN-7 |
| JN-P38 | 鍒犻櫎涓変欢浜嬮綈澶囷紙涓ら樁鍒ゅ畾 + 闆跺洖褰?+ 鐙珛 commit锛夛紱馃敶 鎸夊凡鏈?deletion plan 涓嶅彟璧?| JN-2 / Req 7.5 |
| JN-P39 | 闆跺洖褰掑熀绾?*鐜扮畻**锛堝绾︾洰褰?/ 娉ㄥ唽闆?/ adapter 鎴愬憳锛夛紝绂佸啓姝?| Req 7.1 |
| JN-P40 | 馃敶 澶嶇敤宸叉湁鍙樺紓鑴氭湰 `mutate_task52_j_cycle_migration_guards.py`锛屼笉鏂板啓 | Req 7.6 |

馃敶 **绌哄垎姣嶇邯寰嬶紙JC-20锛?*锛欽N-P7 / JN-P13 / JN-P32 閲屾墍鏈夈€屼负 0 / 绌洪泦銆嶇殑鏂█ SHALL 鍐欐垚
銆岀幇绠椾负 0 **涓斾笉鏄紡鎵?*銆嶏紝骞跺鐢ㄥ凡鏈夊彉寮傝剼鏈€愭潯璇佹槑闈炵┖璺戙€?
