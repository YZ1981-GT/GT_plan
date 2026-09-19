"""生成 Task 63 逐 entry 裁决与发布记录（9 个 B 子码错型 + `S33-REV`）。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 6 Task 63
Requirements: 7.7, 9.4, 9.5, 12.5, 12.8, 12.10, 12.11, 12.12

输出：`backend/data/workpaper_sync_task63_subcode_adjudication.json`

═══ 为什么是生成器而不是手写 JSON ═══

三个字段全部是**磁盘/源码事实**，手写必然 stale：

* `carrier_verdict` —— 由 Task 58 `word_resolution.word_carrier_verdict()` **现算**，
  不抄裁决清册的 `unified_verdict`；两者随后被守卫双向对账，于是清册也成了可校验的
  投影而不是第二真源。
* `own_docx_carriers` / `carrier_ambiguity` —— 现扫 `backend/wp_templates/`。
* `html_counterpart.popup_config_present` —— 现读前端 TS 配置。

「Requirement 7.7 的 9 + 1」这两个数字**不作为输入**：本生成器按 `owner_task == "63"`
从清册筛出行数，再与 requirements.md 声明的数字对账（守卫
`test_task63_entry_count_matches_requirement_7_7`）。反过来（先写死 10 再断言长度是
10）是重言式。

═══ 🔴 读 TS 源码必须先剥注释 ═══

`wpPopupDocxConfigsS.ts` 的文件头注释里**逐字写着** `'S33-REV'`（那段注释正是解释
它为什么被移除的）。不剥注释的正则会把注释里的字样当成配置条目，于是「假切换已移除」
这条判据永远判「未移除」——本 spec memory 里记的假绿第②源（grep 式判据）在这里有一个
现成的反例。:func:`_strip_ts_comments` 因此是必需的，且它有反向自检
（:func:`_assert_comment_stripper_works`）：剥完之后注释里的标记串必须消失。
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path
from typing import Any

#: 仓库根。`backend/scripts/gen/<this>.py` ⇒ parents[0]=gen / [1]=scripts / [2]=backend / [3]=根。
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "backend"))

from app.services.workpaper_sync import canonical_paths as CP  # noqa: E402
from app.services.workpaper_sync.word_resolution import (  # noqa: E402
    WORD_DOCUMENT_TYPE,
    own_template_carriers,
    resolve_word_template,
    word_carrier_verdict,
)

OUT_PATH = ROOT / "backend" / "data" / "workpaper_sync_task63_subcode_adjudication.json"
LEDGER_PATH = ROOT / "backend" / "data" / "workpaper_word_template_adjudication.json"
OVERRIDES_PATH = ROOT / "backend" / "app" / "data" / "wp_code_overrides.json"
TEMPLATE_INDEX_PATH = ROOT / "backend" / "wp_templates" / "_index.json"

#: BP-16 的真源：source-backed entry manifest（Task 67 会重新生成它，故必须现读而非抄结论）。
MANIFEST_PATH = ROOT / "backend" / "data" / "workpaper_sync_entry_manifest.json"
#: BP-18 的真源：`PENDING_ENGINE_ADAPTERS` 的 forbidden_paths 就写在这里。
REGISTRY_PATH = (
    ROOT / "backend" / "app" / "services" / "workpaper_sync" / "adapters" / "registry.py"
)
#: BP-17 的真源之一：`WordEngineBinding.assert_may_publish` 的**定义处**。
#: 🔴 它不在 `word_instrumentation.py` 也不在 `word_entry_gate.py` —— 首版 BP-17 的
#: source_refs 只列了后两者，读者按 refs 去找那个「恒抛」的方法会找不到。
WORD_SDT_ENGINE_PATH = (
    ROOT / "backend" / "app" / "services" / "workpaper_sync" / "word_sdt_engine.py"
)
#: BP-17 的真源之二：candidate 登记处（两个 target 写死 None 的那段）。
WORD_INSTRUMENTATION_PATH = (
    ROOT / "backend" / "app" / "services" / "workpaper_sync" / "word_instrumentation.py"
)

POPUP_CONFIG_PATHS = (
    ROOT / "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigs.ts",
    ROOT / "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigsB.ts",
    ROOT / "audit-platform/frontend/src/components/workpaper/wpPopupDocxConfigsS.ts",
)

SCHEMA_VERSION = "task63-subcode-adjudication:v1"
OWNER_TASK = "63"

#: 宿主：`word-template` 的唯一 registry 落点（Task 1 manifest 的 registryEvidence 同址）。
WORD_TEMPLATE_HOST = "audit-platform/frontend/src/components/workpaper/WorkpaperWordEditor.vue"

#: 注释剥离器的反向自检标记 —— 必须是**只在注释里**出现的串。
_STRIPPER_SELF_CHECK_MARKER = "DEPRECATED 墓碑"


# ═══════════════════════════════════════════════════════════════════════════
# 源码读取
# ═══════════════════════════════════════════════════════════════════════════


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _strip_ts_comments(text: str) -> str:
    """剥掉 TS 的块注释与行注释。

    不处理「字符串字面量里含 `//`」这种情况 —— 本文件的消费判据只看
    `'WP-CODE': {` 形态的条目头，而条目头不可能出现在 URL 字面量里。刻意不引入
    完整 TS parser：那会把生成器变成需要 node 的链路。
    """
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"^\s*//.*$", "", text, flags=re.MULTILINE)
    return text


def _assert_comment_stripper_works() -> None:
    """反向自检：剥完注释后，只存在于注释里的标记串必须消失。

    没有这条自检，`_strip_ts_comments` 某天被改坏（比如漏了 DOTALL）会静默失效，
    而依赖它的「假切换已移除」判据仍然出结果 —— 只是结果恒错。
    """
    src = (POPUP_CONFIG_PATHS[2]).read_text(encoding="utf-8")
    if _STRIPPER_SELF_CHECK_MARKER not in src:
        raise SystemExit(
            f"反向自检失效：{POPUP_CONFIG_PATHS[2].name} 的注释里已无标记串 "
            f"{_STRIPPER_SELF_CHECK_MARKER!r} —— 请改用该文件注释中另一个只在注释里"
            "出现的串，不要删掉这条自检"
        )
    if _STRIPPER_SELF_CHECK_MARKER in _strip_ts_comments(src):
        raise SystemExit(
            "反向自检失败：_strip_ts_comments 未真正剥掉块注释 —— "
            "popup_config_present 判据会把注释里的 wp_code 字样当成配置条目"
        )


def _popup_config_codes() -> set[str]:
    """前端 docx 弹窗配置里**真实存在**的 wp_code 集合（已剥注释）。"""
    entry_re = re.compile(r"^\s*'([^']+)':\s*\{", re.MULTILINE)
    codes: set[str] = set()
    for path in POPUP_CONFIG_PATHS:
        stripped = _strip_ts_comments(path.read_text(encoding="utf-8"))
        codes.update(m.group(1) for m in entry_re.finditer(stripped))
    return codes


def _ledger_rows() -> list[dict[str, Any]]:
    payload = json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
    rows = [r for r in payload["rows"] if r.get("owner_task") == OWNER_TASK]
    return sorted(rows, key=lambda r: r["wp_code"])


# ═══════════════════════════════════════════════════════════════════════════
# 字段身份基础（决定「HTML 对端是否合法」）
# ═══════════════════════════════════════════════════════════════════════════

#: 新格式占位符 —— 唯一合法的显式字段身份来源。
_DOLLAR_TOKEN_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::[^}]+)?\}")


def _field_basis(wp_code: str) -> dict[str, Any]:
    """现算该 entry 的**字段身份基础**是否够发布 tagged-SDT per-entry contract。

    ═══ 为什么这不是「有 HTML 宿主就算有合法对端」═══

    `word-template` 的 HTML 侧字段集来自 `wp_docx_template_parser.parse_template()`，
    它有两类判据：

    * `${field_id}` —— 显式、稳定、语义由模板作者给出；
    * **legacy 中文标记**（`_LEGACY_PATTERNS`：`××公司` / `202X年` / `××` …）——
      字段身份由**中文正则 + 出现顺序编号**派生（`placeholder_generic`、
      `placeholder_generic_2`…）。

    第二类不能作为 contract 的 `stable_field_key`，两条理由各自独立成立：

    1. Requirement 7.1 明禁用中文 label 作定位/身份；Task 77 的 `word_entry_gate`
       亦把「中文正则 fallback」列为禁令并有变异锚点。
    2. 顺序编号**不稳定** —— 在文档前面插一段含 `××` 的文字，后面所有
       `placeholder_generic_N` 全部移位。这与 Task 6 把 `paragraph_index` /
       `run_index` 裁为 `failed` 是同一个失效模式。

    因此 `field_identity_admissible` 只在 `${}` 占位符数 > 0 时为真。**不**写成
    「legacy 也算」：那会让 9 个 entry 立刻「够条件」发布 11 个名为
    `placeholder_generic_N` 的字段 —— 数字好看，但审计师无从知道每个字段该填什么，
    正是 Task 63 明禁的「为满足数字伪造 contract」。
    """
    from app.services.wp_docx_template_parser import parse_template

    path = resolve_word_template(wp_code)
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8", errors="replace")

    structure = parse_template(str(path))
    dollar = [ph for ph in structure.placeholders if _DOLLAR_TOKEN_RE.fullmatch(ph.pattern or "")]
    legacy = [ph for ph in structure.placeholders if ph not in dollar]
    dollar_count = len(dollar)

    return {
        "template_relative_path": path.relative_to(CP.TEMPLATE_ROOT).as_posix(),
        "template_sha256": _sha256(path),
        "paragraph_count": len(structure.paragraphs),
        "w_tbl_count": len(re.findall(r"<w:tbl[ >]", xml)),
        "w_tr_count": len(re.findall(r"<w:tr[ >]", xml)),
        "w_sdt_count": len(re.findall(r"<w:sdt[ >]", xml)),
        "dollar_token_count": dollar_count,
        "dollar_token_names": sorted({m.group(1) for m in _DOLLAR_TOKEN_RE.finditer(xml)}),
        "legacy_chinese_derived_count": len(legacy),
        "legacy_derived_field_ids": [ph.field_id for ph in legacy],
        "legacy_patterns_hit": sorted({ph.pattern for ph in legacy}),
        # 唯一放行判据。
        "field_identity_admissible": dollar_count > 0,
        "has_any_structured_field": bool(structure.placeholders),
        "row_identity_needed": len(re.findall(r"<w:tr[ >]", xml)) > 0,
    }


# ═══════════════════════════════════════════════════════════════════════════
# 逐 entry 事实
# ═══════════════════════════════════════════════════════════════════════════


def _build_entry(row: dict[str, Any], popup_codes: set[str]) -> dict[str, Any]:
    wp_code = row["wp_code"]
    verdict = word_carrier_verdict(wp_code)
    own_docx = [c.relative_path for c in own_template_carriers(wp_code, document_type=WORD_DOCUMENT_TYPE)]
    usable = verdict.has_usable_docx_carrier
    basis = _field_basis(wp_code) if usable else None

    if usable:
        # 有合法 DOCX + HTML 宿主 ⇒ Task 63 第一条分支。但「HTML 对端合法」还要求字段
        # 身份可用（见 _field_basis）；不合法时 BP-20 与 Task 61 并列阻塞，且本轮
        # **不**发布任何 contract（不为满足数字伪造）。
        capability_verdict = "pending_bidirectional"
        verification_state = "UNVERIFIABLE"
        blocked_by = ["Task 61", "BP-16", "BP-17", "BP-18"]
        if not basis["field_identity_admissible"]:
            blocked_by.insert(0, "BP-20")
        fake_switch = {
            "action": "retained",
            "why": (
                "DOCX 载体与 HTML 宿主齐备，结构化视图与在线编辑两条路都真实可用，"
                "双模式切换不是假切换；启用 bidirectional 待 Task 61 与 BP-20"
            ),
        }
    else:
        # 无合法载体 ⇒ Task 63 第二条分支：裁决 missing + 移除假切换。
        capability_verdict = "single_html_no_carrier"
        verification_state = "ADJUDICATED_MISSING"
        blocked_by = []
        fake_switch = {
            "action": "removed",
            "backend_gate": "app/routers/wp_render_strategies/_word_template.py::_carrier_absence_payload",
            "frontend_gate": f"{WORD_TEMPLATE_HOST}::hasNoUsableCarrier",
            "popup_config_entry_removed": wp_code not in popup_codes,
            "why": (
                "结构化视图与在线编辑两条路都无模板可开；原实现落 "
                "「模板解析失败，请使用在线编辑模式」把审计师指向不存在的路"
            ),
        }

    return {
        "wp_code": wp_code,
        "component_type": row["component_type"],
        "ledger_adjudication": row["adjudication"],
        "ledger_unified_verdict": row["unified_verdict"],
        # 现算，不抄清册 —— 守卫据此与上一行双向对账。
        "carrier_verdict": verdict.value,
        "has_usable_docx_carrier": usable,
        "own_docx_carriers": own_docx,
        "carrier_ambiguity": row["carrier_ambiguity"],
        "legacy_verdict": row["legacy_verdict"],
        "parent_code": row["parent_code"],
        # 现算的字段身份基础；无载体 entry 无从谈起，故为 None。
        "field_basis": basis,
        "html_counterpart": {
            "registry_component_type": row["component_type"],
            "host": WORD_TEMPLATE_HOST,
            "popup_config_present": wp_code in popup_codes,
        },
        "capability_verdict": capability_verdict,
        "verification_state": verification_state,
        "blocked_by": blocked_by,
        "fake_switch": fake_switch,
        # 本轮**不**发布任何 definition/bundle/representation，也不注册 adapter。
        "published": {
            "authority_model_definition_id": None,
            "contract_definition_id": None,
            "definition_bundle_id": None,
            "published_representation_id": None,
            "adapter_id": None,
        },
        "sync_test_run_id": None,
        "required_scenario_set_digest": None,
    }


# ═══════════════════════════════════════════════════════════════════════════
# S33-REV 载体线索（裁决建议，待业务确认；本任务不擅自接管）
# ═══════════════════════════════════════════════════════════════════════════


def _s33rev_carrier_hint() -> dict[str, Any]:
    """`S/S33-1程序修订说明.docx` 与 `S33-REV` 的归属线索 + 两个处置方案。

    Task 63 正文给的路是「裁决 single/missing」，不是「去找一个载体接上」，故本记录
    只**登记**证据与方案，`resolution = "pending_business_confirmation"`。擅自改名或
    加显式映射都会改变运行时权威模板库/解析行为，且最终归属属于底稿模板编制方。
    """
    hint = CP.TEMPLATE_ROOT / "S" / "S33-1程序修订说明.docx"
    s33_1_own_xlsx = [c.relative_path for c in own_template_carriers("S33-1", document_type="xlsx")]
    # 同一笔误的第二个受害者：严格 resolver 对 `S33-1` 会解析到这份「程序修订说明」，
    # 而 S33-1 的业务名是「综合核查-内控制度」。存量桥靠「自有 xlsx 存在时不接管」
    # 挡住了运行态，故今天不可达；但它是 resolver 层的真实误指，必须登记。
    try:
        s33_1_strict = CP_strict_relpath("S33-1")
    except Exception as err:  # noqa: BLE001 —— 只用于登记，不参与门控
        s33_1_strict = f"<{type(err).__name__}>"

    return {
        "wp_code": "S33-REV",
        "wp_name": "综合核查-程序修订说明",
        "wp_name_source": "backend/data/wp_account_mapping.json",
        "candidate_carrier": {
            "relative_path": "S/S33-1程序修订说明.docx",
            "exists": hint.is_file(),
            "size_bytes": hint.stat().st_size if hint.is_file() else None,
            "sha256": _sha256(hint) if hint.is_file() else None,
            "derived_wp_code": "S33-1",
        },
        "evidence_that_it_belongs_to_s33rev": [
            "S33 系列 wp_name ↔ 磁盘文件 1:1 完整对应：S33-1「内控制度」→ S33-1财务报告内部控制制度.xlsx，"
            "S33-2..S33-9 各自 xlsx 齐全，无空缺",
            "`S/S33-1程序修订说明.docx` 是 S33* 下唯一多出来的文件，其业务名与 S33-REV 的 "
            "wp_name「程序修订说明」逐字对应",
            f"S33-1 自己已有工作簿载体 {s33_1_own_xlsx}，「程序修订说明」不可能同时是它的正文",
            "wp_index 实测：S33-REV 有真实记录（2 个项目各 1 条）与 2 个 working_paper 实例，"
            "不是无人使用的僵尸编码",
        ],
        "collateral_defect": {
            "what": "同一笔误同时污染 S33-1 的 Word 域严格解析",
            "strict_resolver_returns_for_s33_1": s33_1_strict,
            "why_unreachable_today": (
                "存量桥 `resolve_own_docx_or_none` 第 2 条限制（自有 xlsx 存在时不接管）"
                "挡住了运行态，且 S33-1 的 componentType 是 skip 不走 Word 域"
            ),
            "consequence_if_s33_1_ever_enters_word_domain": (
                "会把「程序修订说明」当成 S33-1「内控制度」的正文打开"
            ),
        },
        "resolution": "pending_business_confirmation",
        "options": [
            {
                "id": "OPT-A",
                "what": "把源模板改名为 `S/S33-REV 程序修订说明.docx`",
                "effect": (
                    "`derive_wp_code_from_filename` 自然派生出 S33-REV ⇒ 一次修好两处"
                    "（S33-REV 得到载体、S33-1 不再被误指），无需任何例外表"
                ),
                "cost": [
                    "改运行时权威模板库 `backend/wp_templates/`（memory 铁律：运行时权威）",
                    "`_index.json` 需同步 relative_path 与 wp_code",
                    "存量守卫 test_s33_rev_carrier_hint_is_recorded_as_open_debt 需按其自述改成断言解析成功",
                ],
                "recommended": True,
            },
            {
                "id": "OPT-B",
                "what": "在 `wp_template_finder._EXPLICIT_TEMPLATE_RELPATHS` 加显式映射",
                "effect": "S33-REV 能取到载体，源模板文件名不动",
                "cost": [
                    "只修一处：S33-1 的严格解析仍误指「程序修订说明」（collateral_defect 未解）",
                    "引入第 3 条例外表条目（现有 2 条为 F2-22/F2-23），裁决权分散",
                    "严格 resolver `resolve_word_template` 不读该表 ⇒ Word 域五意图仍判 template_missing，"
                    "只有存量桥受益 ⇒ 两套判据分叉",
                ],
                "recommended": False,
            },
        ],
        "not_done_in_this_task_because": (
            "Task 63 正文第二条 bullet 要求的是「裁决 single/missing 并移除假切换，不为满足数字"
            "伪造 contract/bundle/finalize」；补载体不在其中，且最终归属需底稿模板编制方确认"
        ),
    }


def _carrier_ambiguity_adjudication(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """载体二义 entry 的逐份实证 + 裁决建议（待业务确认，本任务不擅自选定）。

    `B2-3` 的两份 own_docx 是「第一封沟通函」与「第二封沟通函」。`pick_most_specific`
    现算只会返回其中一份，另一份在 Word 域**不可达** —— 若按单一 entry 发布契约，
    第二封的编辑结果无处回写。

    本函数只登记两份载体各自的可复算指纹与结构事实，把「哪一封是底稿正本 / 是否拆成
    两个 entry」交业务确认：拆 entry 要新增 wp_code，牵动 `wp_index`、
    `wp_code_overrides.json`、前端注册与 Task 58 清册的行数，超出 Task 63 的裁决范围。
    """
    out: list[dict[str, Any]] = []
    for row in rows:
        if not row.get("carrier_ambiguity"):
            continue
        wp_code = row["wp_code"]
        carriers: list[dict[str, Any]] = []
        for rel in row["own_docx_carriers"]:
            path = CP.TEMPLATE_ROOT / rel
            entry: dict[str, Any] = {
                "relative_path": rel,
                "exists": path.is_file(),
                "size_bytes": path.stat().st_size if path.is_file() else None,
                "sha256": _sha256(path) if path.is_file() else None,
            }
            if path.is_file():
                with zipfile.ZipFile(path) as z:
                    xml = z.read("word/document.xml").decode("utf-8", errors="replace")
                entry["w_tbl_count"] = len(re.findall(r"<w:tbl[ >]", xml))
                entry["w_tr_count"] = len(re.findall(r"<w:tr[ >]", xml))
                entry["dollar_token_count"] = len(_DOLLAR_TOKEN_RE.findall(xml))
            carriers.append(entry)

        chosen = resolve_word_template(wp_code).relative_to(CP.TEMPLATE_ROOT).as_posix()
        out.append({
            "wp_code": wp_code,
            "carrier_count": len(carriers),
            "carriers": carriers,
            "resolver_currently_returns": chosen,
            "unreachable_in_word_domain": [
                c["relative_path"] for c in carriers if c["relative_path"] != chosen
            ],
            "why_it_blocks_contract_publication": (
                "per-entry contract 的 template slot 冻结**一份** template_sha256；"
                "一个 wp_code 对两份权威 docx 时，「一个 entry 一份 template digest」前提不成立"
            ),
            "resolution": "pending_business_confirmation",
            "options": [
                {
                    "id": "OPT-SPLIT",
                    "what": "拆成两个 entry（第一封 / 第二封各自一个 wp_code）",
                    "effect": "两份载体都可达，各自独立 contract / bundle / evidence（符合 Property 70）",
                    "cost": [
                        "需新增 wp_code：牵动 wp_index、wp_code_overrides.json、前端注册",
                        "Task 58 清册行数与 Requirement 7.7 的「9 个子码」数字需同步复核",
                    ],
                    "recommended": None,
                },
                {
                    "id": "OPT-PRIMARY",
                    "what": "裁定只有一封是底稿正本进 Word 双向域，另一封保持模板下载",
                    "effect": "不新增 wp_code，契约前提成立",
                    "cost": [
                        "被裁出的那一封在线编辑结果无处回写，只能离线填写后上传",
                        "需业务明确哪一封是正本（两封是审计流程的两个阶段，不是同一文档的两个版本）",
                    ],
                    "recommended": None,
                },
            ],
            "not_decided_in_this_task_because": (
                "两个方案都需要业务给出「哪一封是底稿正本」或「新 wp_code 编码」，"
                "且 BP-20（字段身份基础不合法）未解除前，无论选哪个都发不出契约"
            ),
        })
    return out


def CP_strict_relpath(wp_code: str) -> str:
    """严格 resolver 的相对路径（仅供线索登记，失败由调用方转成字符串）。"""
    from app.services.workpaper_sync.word_resolution import resolve_word_template

    return resolve_word_template(wp_code).relative_to(CP.TEMPLATE_ROOT).as_posix()


# ═══════════════════════════════════════════════════════════════════════════
# 阻塞登记的**现算判据**（2026-09-04 重验时补）
# ═══════════════════════════════════════════════════════════════════════════
#
# 为什么要把判据从散文改成现算：Task 61 在 2026-09-03 踩过一次 ——
# 它把 BP-61-1 的判据写成「三张表行数是否为 0」，随后 opaque lane 产出了 1 行，
# 判据就把一个**旁路观测值**读成了「阻塞已解除」（假绿第③源：拿易变的旁路计数当门禁
# 基线）。本记录的三条 BP 因此各自绑定一条**lane 内、结构性、可复算**的判据，
# 并把它连同现算结果一起写进产物，让「措辞」和「事实」不可能各自漂移。


def _b_subcodes() -> list[str]:
    """本 lane 的 9 个 B 子码 —— 从清册筛，不写死清单。"""
    return sorted(
        r["wp_code"]
        for r in _ledger_rows()
        if r["wp_code"] != "S33-REV"
    )


def _manifest_lane_facts() -> dict[str, Any]:
    """BP-16 的现算判据：9 个 B 子码在 manifest 里有没有**自己的** entry。

    判据刻意不是「manifest 里 entry 总数是多少」（Task 67 每次重生成都会变），而是
    「这 9 个 wp_code 里有几个能在某条 entry 的 `wp_code_patterns` 里逐字命中」——
    这个数只会因为**真的为它们建了 entry** 而变化。
    """
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    entries = manifest["entries"]
    codes = _b_subcodes()

    def patterns_of(entry: dict[str, Any]) -> list[str]:
        return list((entry.get("wp_match") or {}).get("wp_code_patterns") or [])

    per_entry_hits = {
        code: sorted(e["entry_id"] for e in entries if code in patterns_of(e))
        for code in codes
    }
    catch_all = sorted(e["entry_id"] for e in entries if not patterns_of(e))
    docx_entries = sorted(e["entry_id"] for e in entries if e.get("document_type") == "docx")
    docx_with_patterns = sorted(
        e["entry_id"]
        for e in entries
        if e.get("document_type") == "docx" and patterns_of(e)
    )
    return {
        "criterion": (
            "9 个 B 子码里，有几个能在某条 manifest entry 的 "
            "`wp_match.wp_code_patterns` 里**逐字命中** —— 大于 0 即 BP-16 可复议。"
        ),
        "b_subcodes_with_own_entry": sorted(c for c, v in per_entry_hits.items() if v),
        "b_subcodes_with_own_entry_count": sum(1 for v in per_entry_hits.values() if v),
        "b_subcode_count": len(codes),
        "covering_catch_all_entry": "docx/gt-wp-renderer",
        "covering_catch_all_entry_present": "docx/gt-wp-renderer" in catch_all,
        "catch_all_entry_ids": catch_all,
        "docx_entry_ids": docx_entries,
        "docx_entry_ids_with_wp_code_patterns": docx_with_patterns,
        "manifest_entry_total": len(entries),
        "manifest_sha256": _sha256(MANIFEST_PATH),
    }


def _word_adapter_gate_facts() -> dict[str, Any]:
    """BP-18 的现算判据：Word engine adapter 的禁令是否仍在位、目标文件是否仍不存在。

    🔴 判据必须**包含那个真实目标路径**，不能只断言「禁令清单非空且逐项不存在」——
    Task 64 的 M13 变异证明后者可以被改名（`adapters/word_DISABLED.py`）绕过：
    清单仍非空、逐项仍不存在，而 Word adapter 换个文件名就能落地。
    """
    src = REGISTRY_PATH.read_text(encoding="utf-8")
    m = re.search(r"PENDING_ENGINE_ADAPTERS\s*:[^=]*=\s*\((.*?)\n\)\n", src, re.S)
    block = m.group(1) if m else ""
    forbidden = re.findall(r'"(app/services/workpaper_sync/adapters/[^"]*)"', block)
    blocking_task = re.search(r'"blocking_task":\s*"([^"]+)"', block)
    target = "app/services/workpaper_sync/adapters/word.py"
    return {
        "criterion": (
            "禁令清单必须**逐字包含** "
            f"`{target}`，且该路径在磁盘上仍不存在。只断言「清单非空 + 逐项不存在」"
            "会被改名绕过（Task 64 M13）。"
        ),
        "forbidden_paths": sorted(forbidden),
        "real_target_is_listed": target in forbidden,
        "forbidden_paths_all_absent": all(
            not (ROOT / "backend" / rel).exists() for rel in forbidden
        ),
        "blocking_task_field": blocking_task.group(1) if blocking_task else None,
        "registry_sha256": _sha256(REGISTRY_PATH),
    }


def _word_publish_gate_facts() -> dict[str, Any]:
    """BP-17 的现算判据：发布门在**代码层**是否仍然恒抛、candidate 是否仍无 bundle。

    刻意**不查 DB 行数**：本记录是 source-backed 产物，把一个随任意会话增减的行数
    烧进产物会让 `--check` 变成「谁最后跑过谁说了算」。lane 内的 DB 事实
    （B 子码 representation / definition 行数为 0）由重验报告现场取数，不入产物基线。
    """
    engine = WORD_SDT_ENGINE_PATH.read_text(encoding="utf-8")
    instr = WORD_INSTRUMENTATION_PATH.read_text(encoding="utf-8")
    m = re.search(r"\n    def assert_may_publish\(self\) -> None:(.*?)(?=\n    @|\n    def )", engine, re.S)
    body = m.group(1) if m else ""
    return {
        "criterion": (
            "① `assert_may_publish` 的定义处仍在 `word_sdt_engine.py`，且其守卫条件仍是"
            "「非 bundle_bound 或 bundle is None ⇒ 抛」；② candidate 登记处仍把"
            " `target_contract_definition_id` / `target_definition_bundle_id` 双双写死 None。"
            "两条同时成立 ⇒ 本 lane 无论如何都到不了 published representation。"
        ),
        "assert_may_publish_defined_in": (
            "app/services/workpaper_sync/word_sdt_engine.py"
            if "def assert_may_publish" in engine
            else None
        ),
        "assert_may_publish_raises_without_bundle": (
            "self.bundle is None" in body and "raise WordApprovedBundleRequiredError" in body
        ),
        "candidate_targets_hardwired_none": (
            "target_contract_definition_id=None" in instr
            and "target_definition_bundle_id=None" in instr
        ),
        "candidate_state_hardwired": (
            "awaiting_contract" if "CandidateState.awaiting_contract" in instr else None
        ),
        "word_sdt_engine_sha256": _sha256(WORD_SDT_ENGINE_PATH),
        "word_instrumentation_sha256": _sha256(WORD_INSTRUMENTATION_PATH),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 阻塞登记（续接 F2 lane 的 BP-15）
# ═══════════════════════════════════════════════════════════════════════════


def _blocking_preconditions() -> list[dict[str, Any]]:
    manifest_facts = _manifest_lane_facts()
    adapter_facts = _word_adapter_gate_facts()
    publish_facts = _word_publish_gate_facts()
    return [
        {
            "id": "BP-16",
            "blocks": ["definition_bundle", "published_representation", "adapter_registration"],
            "what": (
                "Task 63 的 9 个 B 子码在 source-backed manifest 里没有 per-entry entry："
                "`workpaper_sync_entry_manifest.json` 按**宿主**建 entry，这 9 个 wp_code 只被泛匹配 "
                "entry `docx/gt-wp-renderer` 覆盖（其 `wp_match.wp_code_patterns` 为空数组）⇒ "
                "「契约登记行的 entry_id 必须命中 manifest」这条双向等值判据无法满足。"
            ),
            "status": "open",
            "must_fix_before": "为任一 B 子码装载生产契约 / 注册 adapter",
            "observable_consequences": [
                "per-entry 契约只能 staged，不进 contracts.available_contract_ids()",
                "registry.assert_contract_file_current 会因生产目录无此文件而拒绝注册",
                "manifest 的 capability_counts / unadjudicated_count 里看不到这 9 个 entry",
            ],
            "same_root_cause_as": "BP-10（F2 Word lane 的同型问题）",
            "source_refs": [
                "backend/data/workpaper_sync_entry_manifest.json",
                "backend/app/services/workpaper_sync/adapters/registry.py",
            ],
            "numbering_note": "续接 F2 lane 的 BP-1..BP-15（本记录消费它们、不改它们）。",
            "measured": manifest_facts,
        },
        {
            "id": "BP-17",
            "blocks": ["definition_bundle", "published_representation"],
            "what": (
                "approved definition bundle 需要 DB 侧 definition 行；Task 76 的 provisioner 已交付，"
                "但本 lane 一条都还没发布 ⇒ `WordEngineBinding` 只能用离线 candidate 校验模式，"
                "`assert_may_publish()` 恒抛。"
            ),
            "status": "open",
            "must_fix_before": "Task 77 WordEntryFinalizeGate.finalize_candidate 可被调用",
            "observable_consequences": [
                "WordInstrumentationUpgrader.stage_and_register_candidate 写死 "
                "target_definition_bundle_id=None / state=awaiting_contract",
                "finalize 时 candidate.target_definition_bundle_id is None ⇒ PerEntryContractUnapprovedError",
            ],
            "source_refs": [
                "backend/app/services/workpaper_sync/word_sdt_engine.py",
                "backend/app/services/workpaper_sync/word_instrumentation.py",
                "backend/app/services/workpaper_sync/word_entry_gate.py",
            ],
            "scope_note": (
                "🔴 判据是 **lane 内**的，不是平台级行数。2026-09-04 实测平台侧已有 "
                "23 条 definition artifact / 9 个 bundle / 4 条 current published "
                "representation（属 b60 / d2 / g7 / h1 与 opaque lane），但 "
                "`document_type='docx'` 的 representation 仍为 0、9 个 B 子码在四张表里"
                "各为 0 行。按平台行数判会把别的 lane 的产出误读成本 lane 解除 —— "
                "Task 61 的 BP-61-1 已在 2026-09-03 踩过这个坑。"
            ),
            "measured": publish_facts,
        },
        {
            "id": "BP-18",
            "blocks": ["adapter_registration", "capability_verdict", "evidence"],
            "what": (
                "`registry.PENDING_ENGINE_ADAPTERS` 仍禁止 `adapters/word.py`（禁令清单逐字"
                "包含该路径，磁盘上该文件仍不存在），放行门写明是 Task 61（真实 OO 9.4 F2 "
                "Word gate）；Task 61 复选框现扫仍是 `[-]`。"
            ),
            "status": "open",
            "must_fix_before": "把任一 B 子码的 capability 从 null 改成 bidirectional",
            "observable_consequences": [
                "9 个 entry 的 verification_state 只能是 UNVERIFIABLE",
                "sync_test_run_id / required_scenario_set_digest 均为 null",
                "Property 69 / 70 在本 lane 上分母为空 ⇒ 本任务不宣称它们通过",
            ],
            "upstream_correction": (
                "🔴 首版 BP-18 的措辞里有一句「其 BP-10~BP-15 六条全部 open」，"
                "已被 Task 61 自己 2026-09-01 的记录**证伪**：那四条平台欠账由 Tasks "
                "75/76/77 解除，Task 61 改登记 BP-61-1/2/3，其中唯一 binding 的是 "
                "BP-61-1（published representation 供给，`scope=platform_wide_not_f2_specific`，"
                "生产者是 `ContentMutationService.commit(...)` 与 Tasks 36/77 的 finalize "
                "gate，**owner 不在 Task 61 也不在 Task 63**）。本轮起 BP-18 不再转述 "
                "Task 61 的内部阻塞编号 —— 转述上游编号是这次失准的根因，"
                "改为只断言本记录能直接现算的两件事（禁令在位 + 目标文件不存在）。"
            ),
            "source_refs": [
                "backend/app/services/workpaper_sync/adapters/registry.py",
                "backend/data/workpaper_sync_f2_word_lane_publication.json",
                "backend/data/workpaper_task61_word_pilot_gate_probes.json",
                ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/tasks.md",
            ],
            "measured": adapter_facts,
        },
        {
            "id": "BP-20",
            "blocks": ["contract_publication", "authority_model", "definition_bundle"],
            "what": (
                "9 个 B 子码的**字段身份基础不合法**：9 份权威 DOCX 里 `${token}` 占位符现算"
                "共 0 个；HTML 侧字段全部由 `wp_docx_template_parser` 的 legacy 中文标记正则"
                "（`××`）+ 出现顺序编号派生成 `placeholder_generic_N`。这类身份既违反 "
                "Requirement 7.1（禁中文 label 作定位/身份），又与 Task 6 裁为 failed 的 "
                "`paragraph_index` / `run_index` 同一失效模式（文档前面插一段含 `××` 的文字，"
                "后面所有编号全部移位）。`B40-1` / `B40-2` 更是连 legacy 字段都为 0，"
                "结构化岛为空集 ⇒ 契约会是空转。"
            ),
            "status": "open",
            "must_fix_before": "为任一 B 子码发布 tagged-SDT per-entry contract",
            "observable_consequences": [
                "若按现状发布，contract 的 stable_field_key 只能是 placeholder_generic_N，"
                "审计师无从知道每个字段该填什么",
                "Task 77 word_entry_gate 的 declared 清册三边锁会锁住一组不稳定身份："
                "模板改一处文字即 tag 集合漂移",
                "B40-1 / B40-2 的字段集为空 ⇒ 与 Task 77 拒绝的「空集上 equivalent=True 是空转」同型",
            ],
            "resolution_paths": [
                "源模板引入 `${token}` 显式占位符（与 F2-22/F2-23 同形），由底稿模板编制方给出"
                "每个待填位置的业务语义",
                "或人工逐份裁定每个 `××` 的业务含义并落成显式字段清册（不经中文正则），"
                "再据它生成 instrumentation definition",
            ],
            "not_worked_around_because": (
                "Task 63 正文明禁「不为满足数字伪造 contract/bundle/finalize」；"
                "把 placeholder_generic_N 当 stable_field_key 发布 9 份契约会让数字达标而内容空转"
            ),
            "source_refs": [
                "backend/app/services/wp_docx_template_parser.py",
                "backend/data/onlyoffice_word_sdt_carrier_contract.json",
                ".kiro/specs/workpaper-html-onlyoffice-bidirectional-writeback-closure/requirements.md",
            ],
        },
        {
            "id": "BP-19",
            "blocks": ["contract_publication"],
            "what": (
                "`B2-3` 的 own_docx_carriers 有 2 份（「第一封沟通函」/「第二封沟通函」），"
                "`carrier_ambiguity=true`。一个 wp_code 对两份权威 docx 时，per-entry contract 的"
                "「一个 entry 一份 template digest」前提不成立。"
            ),
            "status": "open",
            "must_fix_before": "为 B2-3 发布 authority model / contract / bundle",
            "observable_consequences": [
                "resolve_word_template('B2-3') 经 pick_most_specific 只返回其中一份"
                "（现算为「第一封」），另一份在 Word 域不可达",
                "若按单一 entry 发布，第二封沟通函的编辑结果无处回写",
            ],
            "options": [
                "拆成两个 entry（需新 wp_code，涉及 wp_index/overrides/前端注册，跨 Task 58 清册）",
                "裁决只有一封进 Word 双向域，另一封保持模板下载（需业务确认哪一封是底稿正本）",
            ],
            "source_refs": [
                "backend/data/workpaper_word_template_adjudication.json",
                "backend/app/services/workpaper_sync/canonical_paths.py",
            ],
        },
    ]


# ═══════════════════════════════════════════════════════════════════════════
# 组装
# ═══════════════════════════════════════════════════════════════════════════


def build() -> dict[str, Any]:
    _assert_comment_stripper_works()
    popup_codes = _popup_config_codes()
    rows = _ledger_rows()
    entries = [_build_entry(r, popup_codes) for r in rows]

    by_verdict: dict[str, int] = {}
    by_state: dict[str, int] = {}
    for e in entries:
        by_verdict[e["carrier_verdict"]] = by_verdict.get(e["carrier_verdict"], 0) + 1
        by_state[e["verification_state"]] = by_state.get(e["verification_state"], 0) + 1

    payload: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "spec": "workpaper-html-onlyoffice-bidirectional-writeback-closure",
        "task": OWNER_TASK,
        "generated_by": "backend/scripts/gen/generate_workpaper_task63_subcode_adjudication.py",
        "sources": {
            "adjudication_ledger": {
                "path": "backend/data/workpaper_word_template_adjudication.json",
                "sha256": _sha256(LEDGER_PATH),
            },
            "component_overrides": {
                "path": "backend/app/data/wp_code_overrides.json",
                "sha256": _sha256(OVERRIDES_PATH),
            },
            "template_index": {
                "path": "backend/wp_templates/_index.json",
                "sha256": _sha256(TEMPLATE_INDEX_PATH),
            },
            # 2026-09-04 重验时补：三条 BP 的判据各自绑定的源文件也要锁 digest，
            # 否则「措辞对得上」只是对得上一份没被锁住的源。
            "entry_manifest": {
                "path": "backend/data/workpaper_sync_entry_manifest.json",
                "sha256": _sha256(MANIFEST_PATH),
            },
            "adapter_registry": {
                "path": "backend/app/services/workpaper_sync/adapters/registry.py",
                "sha256": _sha256(REGISTRY_PATH),
            },
            "word_sdt_engine": {
                "path": "backend/app/services/workpaper_sync/word_sdt_engine.py",
                "sha256": _sha256(WORD_SDT_ENGINE_PATH),
            },
            "word_instrumentation": {
                "path": "backend/app/services/workpaper_sync/word_instrumentation.py",
                "sha256": _sha256(WORD_INSTRUMENTATION_PATH),
            },
        },
        "entries": entries,
        "s33rev_carrier_hint": _s33rev_carrier_hint(),
        "carrier_ambiguity_adjudication": _carrier_ambiguity_adjudication(rows),
        "blocking_preconditions": _blocking_preconditions(),
        "residency_reverification": {
            "date": "2026-09-04",
            "why": (
                "Task 63 是**有意驻留**任务，不是被中断的任务。驻留证据写于 2026-08-31，"
                "其后 Tasks 62/64/67/75/76/77 均有落地，故每轮接手先**重验**四条阻塞而不是"
                "复述结论。本块登记的是重验结果本身，让下一轮能一眼看出「上次算到哪、"
                "判据是什么」。"
            ),
            "verdicts": {
                "BP-16": "still_open",
                "BP-17": "still_open",
                "BP-18": "still_open",
                "BP-20": "still_open",
            },
            "wording_corrections_applied": [
                "BP-18 删掉转述上游编号的那句「Task 61 的 BP-10~BP-15 六条全部 open」"
                "（已被 Task 61 自己的记录证伪），改为只断言本记录可直接现算的两件事。",
                "BP-17 的 source_refs 补上 `word_sdt_engine.py` —— `assert_may_publish` "
                "的定义处在那里，首版只列了 word_instrumentation / word_entry_gate，"
                "读者按 refs 找不到那个「恒抛」的方法。",
                "BP-16 / BP-17 / BP-18 各挂一个 `measured` 现算块，把散文判据换成"
                "可复算的结构事实。",
            ],
            "not_advanced_because": (
                "四条全部 still_open。其中 BP-20（字段身份基础）的解除动作是**业务输入**"
                "而非编码：需底稿模板编制方为这 9 份 DOCX 引入 `${token}`，或逐份裁定每个 "
                "`××` 的业务语义。只要 BP-20 未解除，就不存在合法的 stable_field_key，"
                "任何 per-entry contract 都不得发布 —— 即便 BP-16（manifest entry）"
                "将来因 Task 67 重生成而解除，9 个 entry 仍是 UNVERIFIABLE。"
            ),
        },
        "cross_entry_isolation": {
            "rule": (
                "每个 entry 的 template / contract / bundle / evidence 逐项独享，不交叉复用"
                "（Property 70 / Task 63 正文「每个 entry 保留自身 evidence/UNVERIFIABLE 状态」）。"
            ),
            "assertions": [
                "10 个 entry 的 own_docx_carriers 两两无交集",
                "published 五个 id 全为 null ⇒ 本轮不存在可被复用的 bundle",
                "无载体 entry 的 fake_switch.action=removed，有载体 entry 为 retained，两类不混用同一处置",
            ],
        },
        "stats": {
            "entry_count": len(entries),
            "by_carrier_verdict": dict(sorted(by_verdict.items())),
            "by_verification_state": dict(sorted(by_state.items())),
            "adjudicated_missing": sum(1 for e in entries if not e["has_usable_docx_carrier"]),
            "pending_bidirectional": sum(1 for e in entries if e["has_usable_docx_carrier"]),
            "carrier_ambiguity_entries": sorted(
                e["wp_code"] for e in entries if e["carrier_ambiguity"]
            ),
            # 字段身份基础：0 个可发布契约是**实测结论**，不是未做完。
            "field_identity_admissible_entries": sorted(
                e["wp_code"]
                for e in entries
                if (e["field_basis"] or {}).get("field_identity_admissible")
            ),
            "dollar_token_total": sum(
                (e["field_basis"] or {}).get("dollar_token_count", 0) for e in entries
            ),
            "legacy_chinese_derived_total": sum(
                (e["field_basis"] or {}).get("legacy_chinese_derived_count", 0) for e in entries
            ),
            "zero_structured_field_entries": sorted(
                e["wp_code"]
                for e in entries
                if e["field_basis"] and not e["field_basis"]["has_any_structured_field"]
            ),
            "fake_switch_removed_entries": sorted(
                e["wp_code"] for e in entries if e["fake_switch"]["action"] == "removed"
            ),
            "published_artifacts": 0,
            "registered_adapters": 0,
        },
    }
    payload["record_digest"] = hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return payload


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--check", action="store_true", help="只校验磁盘内容与现算一致，不写文件")
    args = ap.parse_args()

    payload = build()
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"

    if args.check:
        if not OUT_PATH.is_file():
            print(f"FAIL 产物不存在: {OUT_PATH}")
            return 1
        current = OUT_PATH.read_text(encoding="utf-8")
        if current != text:
            print("FAIL 产物与现算不一致 —— 请重跑生成器（不要手改 JSON）")
            return 1
        print(f"OK  {OUT_PATH.name} 与现算一致（{payload['stats']['entry_count']} entries）")
        return 0

    OUT_PATH.write_text(text, encoding="utf-8")
    s = payload["stats"]
    print(f"已写出 {OUT_PATH.relative_to(ROOT).as_posix()}")
    print(f"  entries={s['entry_count']}  by_verdict={s['by_carrier_verdict']}")
    print(f"  adjudicated_missing={s['adjudicated_missing']}  pending_bidirectional={s['pending_bidirectional']}")
    print(f"  fake_switch_removed={s['fake_switch_removed_entries']}")
    print(f"  carrier_ambiguity={s['carrier_ambiguity_entries']}")
    print(f"  字段身份可发布契约的 entry={s['field_identity_admissible_entries'] or '（无）'}")
    print(f"  ${{}} 占位符合计={s['dollar_token_total']}  "
          f"legacy 中文派生合计={s['legacy_chinese_derived_total']}")
    print(f"  零结构化字段 entry={s['zero_structured_field_entries']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
