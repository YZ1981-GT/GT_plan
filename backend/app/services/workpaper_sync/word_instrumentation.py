# -*- coding: utf-8 -*-
"""Word instrumentation definition 与 **non-current** representation upgrade candidate 生成器。

spec: workpaper-html-onlyoffice-bidirectional-writeback-closure / Wave 5 Task 59
Requirements: 2.3, 6.10, 6.18, 7.1, 7.2, 7.3, 7.5, 7.9, 7.10, 9.1, 9.8, 9.9, 9.10, 14.16
Properties: **P28** / **P30** / **P31** / **P67** / **P71**

═══ 一、本模块**能**做什么、**不能**做什么 ═══

能做（发布 DAG 的前两段 + candidate 登记）::

    template definition ──► instrumentation definition ──► non-current candidate
    （publish 权威模板 blob） （只单向引用 template digest） （staged / awaiting_contract）

**不能**做，每条都有可执行判据而不是注释：

=========================================  ==============================================
禁令                                        判据落点
=========================================  ==============================================
不得创建 published/current representation    :class:`CandidateOnlyRepository`（Task 17 门面）恒抛
不得切 entry pointer                        同上
不得 finalize candidate                     同上
不得递增 content revision                    同上（含 Task 15 `REVISION_DOMAIN_WRITE_METHODS`）
不得伪造 contract / authority / bundle       两个 target 字段恒 None +
                                           :func:`assert_candidate_is_non_current` 逐字段实测
不得进 resolver / room / evidence            candidate 只落 `.upgrade-candidates/` 命名空间
不得改动权威模板本体                          :meth:`WordInstrumentationUpgrader.instrument_source_bytes`
                                           只吃 bytes；守卫跑完核 `backend/wp_templates/` sha256
不得用 python-docx 全量重建                   :func:`instrument_docx_bytes` 只改
                                           `word/document.xml` 一个 entry，其余逐字节复制
=========================================  ==============================================

🔴 「不得创建 representation」为什么**必须复用** Task 17 的
:class:`~app.services.workpaper_sync.excel_instrumentation.CandidateOnlyRepository`
而不是本模块另写一个同名门面：禁令的单一真源是那份
`CANDIDATE_FORBIDDEN_METHODS`（它自己又 import Task 15 的
`REVISION_DOMAIN_WRITE_METHODS` 取并集）。各写一份的后果不是「更安全」，而是 Task 15
那边新增一个 revision writer 时 Excel 侧红、Word 侧不红。门面本身与文档类型无关。

═══ 二、为什么注入必须 zip-level 定点改字节 ═══

Requirement 7.3 / 7.9 + 本任务正文点名要校验「可见结构、样式、批注、修订、图片」等值。
`python-docx` 打开再保存会丢批注（`comments.xml` 不在它的对象模型里）、丢未知部件、
重排关系 —— 与 Excel 侧「openpyxl 全量重写丢 drawing/chart」同源。

因此 :func:`instrument_docx_bytes`：

* 只解出 `word/document.xml` 一个 entry 改字节，其余 entry **连 `compress_type` 一起**
  原样写回（:attr:`InstrumentedDocx.untouched_parts` 记录数量，守卫据它断言 > 0）；
* 注入不加 `<w:lock>` —— 与 Task 6 探针的 `lock_policy=no_w_lock_injected` 保持一致。
  加锁会让 OO 无法删 SDT，等于替载体作弊，也让载体保留结论不可比。

═══ 三、载体与锚点只认 Task 6 裁决 ═══

`row_sdt` 在 OO 9.4 上 `failed`（首次序列化即被剥离），所以本模块**没有**「包 `w:tr`」
这条代码路径：行身份一律注入到**单元格内 inline field SDT** 的 tag 里
（`gt:field:{contract}:rows/{row_uuid}/{column}`），即探针实测通过的
`row_identity_fallback_measured.candidate`。载体清单从
`contracts.load_word_carrier_gate()` 读，不在本模块复制。

═══ 四、Property 71 在本任务的落点 ═══

Task 6 契约自己声明 `environment.stale_policy`：「environment / source_commit /
runner / probe 文档模板 sha256 任一变化即本裁决失效」。:class:`WordSdtCarrierGate`
把这四项落成机器比对，基线见 `backend/data/onlyoffice_word_instrumentation_gate.json`：

* **Tier A**（全在 `backend/` 下，生产必然存在）在 :meth:`WordSdtCarrierGate.load`
  里无条件强制：载体契约 digest、`word_sdt_fingerprint` 模块 digest、OO build、
  三份 probe 模板的权威 sha256；
* **Tier B**（`.kiro/specs/**` 的 probe 脚本与 evidence）由
  :meth:`WordSdtCarrierGate.assert_evidence_fresh` 在仓库上下文强制，
  **evidence 缺失本身即判 stale**，不降级为 skip。
"""

from __future__ import annotations

import hashlib
import io
import json
import re
import uuid
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Mapping, Sequence

from app.services.word_sdt_fingerprint import (
    body_preservation_report,
    structure_fingerprint,
)
from app.services.workpaper_sync.canonical_paths import TEMPLATE_ROOT, resolve_within_root
from app.services.workpaper_sync.contracts import (
    ROW_UUID_PLACEHOLDER,
    CarrierGate,
    load_word_carrier_gate,
)
from app.services.workpaper_sync.definitions import (
    DefinitionPublisher,
    canonical_digest,
    canonical_json_bytes,
    validate_instrumentation_payload,
    validate_template_payload,
)
# 🔴 candidate 禁令面的**单一真源**在 Task 17（文档类型无关）。见模块 docstring 第一节。
from app.services.workpaper_sync.excel_instrumentation import (
    CANDIDATE_FORBIDDEN_METHODS,
    CandidateOnlyRepository,
    CandidateSurfaceForbiddenError,
    UpgradeCandidateOutcome,
    assert_candidate_is_non_current,
)
from app.services.workpaper_sync.models import (
    CandidateState,
    DefinitionKind,
    SyncDomainError,
)
from app.services.workpaper_sync.word_sdt_engine import (
    WORD_DOCUMENT_PART,
    WORD_DOCUMENT_TYPE,
    WordEngineBinding,
    format_sdt_tag,
    parse_sdt_tag,
)

__all__ = [
    "WORD_INSTRUMENTATION_SCHEMA_VERSION",
    "WORD_TEMPLATE_SCHEMA_VERSION",
    "WORD_IDENTITY_SCHEMA_VERSION",
    "WORD_INSTRUMENTATION_VERSION",
    "WORD_GATE_CONTRACT_PATH",
    "WORD_GATE_BASELINE_PATH",
    "WORD_TEMPLATE_AUTHORITY_ROOT",
    "CANDIDATE_FORBIDDEN_METHODS",
    "CandidateOnlyRepository",
    "CandidateSurfaceForbiddenError",
    "UpgradeCandidateOutcome",
    "assert_candidate_is_non_current",
    "WordInstrumentationError",
    "WordCarrierGateError",
    "WordProbeEvidenceStaleError",
    "WordTokenAnchorError",
    "WordVisibleEquivalenceError",
    "WordTagReadbackError",
    "WordLockPolicyError",
    "WordSdtCarrierGate",
    "WordFieldInjection",
    "WordRowInjection",
    "ONE_TIME_LOCATOR_KINDS",
    "visible_text_stream",
    "WordInstrumentationSpec",
    "InstrumentedDocx",
    "instrument_docx_bytes",
    "verify_docx_visible_equivalence",
    "REQUIRED_PROBE_LOCK_POLICY",
    "assert_probe_lock_policy",
    "assert_no_sdt_lock",
    "assert_only_document_part_changed",
    "read_back_word_tags",
    "word_structure_hash",
    "WordInstrumentationUpgrader",
]

# ═══════════════════════════════════════════════════════════════════════════
# 0. 常量与路径
# ═══════════════════════════════════════════════════════════════════════════

_BACKEND_ROOT: Final[Path] = Path(__file__).resolve().parents[3]
_REPO_ROOT: Final[Path] = _BACKEND_ROOT.parent

#: Task 6 载体裁决契约（**唯一**真源）。
WORD_GATE_CONTRACT_PATH: Final[Path] = (
    _BACKEND_ROOT / "data" / "onlyoffice_word_sdt_carrier_contract.json"
)
#: Task 59 的 stale-policy digest 基线。
WORD_GATE_BASELINE_PATH: Final[Path] = (
    _BACKEND_ROOT / "data" / "onlyoffice_word_instrumentation_gate.json"
)
#: 运行时权威模板源（Requirement 9.1）。参考副本一律不认。
#: 🔴 直接 alias 到 `canonical_paths.TEMPLATE_ROOT`，不重新拼一次 —— 否则形成
#: 第二份「权威模板根」真源，改一处另一处不红。
WORD_TEMPLATE_AUTHORITY_ROOT: Final[Path] = TEMPLATE_ROOT

WORD_TEMPLATE_SCHEMA_VERSION: Final[str] = "template-definition:v1"
WORD_INSTRUMENTATION_SCHEMA_VERSION: Final[str] = "instrumentation-definition:v1"
WORD_IDENTITY_SCHEMA_VERSION: Final[str] = "1.0.0"
WORD_INSTRUMENTATION_VERSION: Final[str] = "1.0.0"

#: 注入**禁止**出现的元素：`w:lock` 会阻止 OO 删除 SDT，等于替载体作弊，
#: 也让「载体在无保护下是否自发保留」的探针结论不再适用（Task 6 `lock_policy`）。
_FORBIDDEN_SDT_CHILD: Final[str] = "<w:lock"

#: 模板里的一次性定位线索形态（design §SDT migration 第 1 条：
#: 「现有 DOCX token 只作为**一次性**定位线索」）。注入后就不再有人读它。
_TOKEN_RE: Final[re.Pattern[str]] = re.compile(r"^\$\{[A-Za-z][A-Za-z0-9_]*\}$")

_W_T_OPEN: Final[str] = "<w:t"


# ═══════════════════════════════════════════════════════════════════════════
# 1. 异常（每条拒绝理由一个类型）
# ═══════════════════════════════════════════════════════════════════════════


class WordInstrumentationError(SyncDomainError):
    error_code = "word_instrumentation_failed"


class WordCarrierGateError(WordInstrumentationError):
    """载体/锚点未过 Task 6 真实 OO 探针（Requirement 7.1 / 7.2）。"""

    error_code = "word_identity_carrier_not_probed"


class WordProbeEvidenceStaleError(WordInstrumentationError):
    """探针实证已 stale（OO build / 模板 / 脚本 / evidence 漂移，Requirement 14.16）。"""

    error_code = "word_probe_evidence_stale"


class WordTokenAnchorError(WordInstrumentationError):
    """一次性定位 token 在模板里缺失、重复或形态非法。"""

    error_code = "word_token_anchor_unresolvable"


class WordVisibleEquivalenceError(WordInstrumentationError):
    """注入破坏了可见结构 / 样式 / 批注 / 修订 / 图片（Requirement 7.3 / 9.9）。"""

    error_code = "word_visible_equivalence_violated"


class WordTagReadbackError(WordInstrumentationError):
    """注入后反读拿不到预期 tag 集合 / 层级 / row_uuid（Requirement 7.10）。"""

    error_code = "word_tag_readback_failed"


class WordLockPolicyError(WordInstrumentationError):
    """注入体里出现 `w:lock` —— 违反 Task 6 的 `no_w_lock_injected` 前提。"""

    error_code = "word_sdt_lock_policy_violated"


# ═══════════════════════════════════════════════════════════════════════════
# 2. 载体裁决门 + Property 71 stale 门
# ═══════════════════════════════════════════════════════════════════════════


def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def word_structure_hash(data: bytes) -> str:
    """DOCX 的 normalized structure hash（Requirement 9.1 / 9.8 的漂移判据）。

    由 `word_sdt_fingerprint` 的六个 aspect digest **按 aspect 名排序**折成一个
    digest。刻意不用字节 sha256：字节会随 zip 压缩参数与部件顺序变化，而这个 hash
    要回答的是「可见业务结构有没有变」。采集报错时抛，绝不返回一个「看起来正常」的值。
    """
    fingerprint = structure_fingerprint(data)
    if fingerprint.errors:
        raise WordInstrumentationError(f"DOCX 结构指纹采集报错: {fingerprint.errors}")
    aspects = fingerprint.aspect_digests()
    joined = "\n".join(f"{name}={aspects[name]}" for name in sorted(aspects))
    return _sha256_bytes(joined.encode("utf-8"))


@dataclass(frozen=True)
class WordSdtCarrierGate:
    """Task 6 载体裁决的机器可读投影 + stale 门。构造只能经 :meth:`load`。"""

    contract_sha256: str
    onlyoffice_build: str
    browser: str
    source_commit: str
    runner: str
    #: 委派 `contracts.load_word_carrier_gate()`（allowlist/blocklist 的单一真源）。
    carrier_gate: CarrierGate
    #: `{'F2-22': 'f19a…', ...}` —— 探针覆盖过的模板及其权威源 digest。
    probed_template_digests: Mapping[str, str]
    #: Task 6 声明的 `lock_policy`（本模块据它拒绝注入 `w:lock`）。
    lock_policy: str
    baseline: Mapping[str, Any]

    # ─────────────────────────────────────────────────────────────

    @classmethod
    def load(cls, *, baseline_path: Path | None = None) -> WordSdtCarrierGate:
        """读 Task 6 契约 + 基线并强制 Tier A stale 判据；任一不符 fail closed。"""
        path = baseline_path or WORD_GATE_BASELINE_PATH
        if not WORD_GATE_CONTRACT_PATH.is_file():
            raise WordCarrierGateError(
                f"Task 6 载体裁决契约缺失: {WORD_GATE_CONTRACT_PATH} —— 没有真实 OO 探针"
                "裁决时不得 instrumentation 任何 DOCX"
            )
        if not path.is_file():
            raise WordProbeEvidenceStaleError(
                f"instrumentation gate 基线缺失: {path} —— 缺基线等于没有 stale 判据"
            )
        raw = WORD_GATE_CONTRACT_PATH.read_bytes()
        contract_digest = _sha256_bytes(raw)
        payload = json.loads(raw.decode("utf-8"))
        baseline = json.loads(path.read_text(encoding="utf-8"))

        tier_a = baseline.get("tier_a_runtime") or {}
        for item in tier_a.get("files") or []:
            target = _REPO_ROOT / str(item["path"])
            if not target.is_file():
                raise WordProbeEvidenceStaleError(
                    f"stale 判据引用的文件不存在: {item['path']}（role={item.get('role')}）"
                )
            observed = _sha256_bytes(target.read_bytes())
            if observed != item["sha256"]:
                raise WordProbeEvidenceStaleError(
                    f"{item['path']}（role={item.get('role')}）digest 漂移："
                    f"基线 {item['sha256'][:12]}… 实测 {observed[:12]}… —— "
                    "必须重跑 Task 6 探针并重新裁决载体，不得沿用旧结论"
                    "（Requirement 14.16 / Property 71）"
                )

        environment = payload.get("environment") or {}
        for field_name, key in (
            ("onlyoffice_build", "oo_build"),
            ("source_commit", "source_commit"),
            ("runner", "runner"),
        ):
            want = tier_a.get(field_name)
            got = environment.get(key)
            if not want or want != got:
                raise WordProbeEvidenceStaleError(
                    f"探针环境 {key}={got!r} 与基线 {field_name}={want!r} 不符 —— "
                    "environment / source_commit / runner 任一变化即裁决失效"
                )

        probed: dict[str, str] = {}
        declared = {
            str(item["template_id"]): item for item in tier_a.get("probed_templates") or []
        }
        for doc in payload.get("probe_docs") or []:
            wp_code = str(doc.get("wp_code") or "").strip()
            rel = str(doc.get("template_rel") or "").strip()
            want_sha = str(doc.get("template_sha256") or "").strip()
            if not (wp_code and rel and want_sha):
                raise WordCarrierGateError(
                    f"Task 6 契约的 probe_docs 条目不完整: {doc!r}"
                )
            if wp_code not in declared:
                raise WordProbeEvidenceStaleError(
                    f"探针模板 {wp_code} 未在基线 probed_templates 登记 —— "
                    "分母不得由契约单侧扩张"
                )
            if declared[wp_code]["sha256"] != want_sha:
                raise WordProbeEvidenceStaleError(
                    f"探针模板 {wp_code} 的 sha256 在契约与基线之间不一致"
                )
            target = _REPO_ROOT / rel
            # 权威模板只读；这里只核 digest，绝不写。
            if not target.is_file():
                raise WordProbeEvidenceStaleError(f"探针模板不存在: {rel}")
            observed = _sha256_bytes(target.read_bytes())
            if observed != want_sha:
                raise WordProbeEvidenceStaleError(
                    f"探针模板 {rel} 的 sha256 漂移（基线 {want_sha[:12]}… "
                    f"实测 {observed[:12]}…）—— probe 文档模板变化即裁决失效"
                )
            probed[wp_code] = want_sha
        if not probed:
            raise WordCarrierGateError("Task 6 契约没有任何 probe_docs —— 空分母等于放行一切")

        lock_policy = str(
            ((payload.get("scope_and_non_claims") or {}).get("lock_policy") or "")
        ).strip()
        assert_probe_lock_policy(lock_policy)

        return cls(
            contract_sha256=contract_digest,
            onlyoffice_build=str(environment.get("oo_build")),
            browser=str(environment.get("browser")),
            source_commit=str(environment.get("source_commit")),
            runner=str(environment.get("runner")),
            carrier_gate=load_word_carrier_gate(),
            probed_template_digests=probed,
            lock_policy=lock_policy,
            baseline=baseline,
        )

    # ─────────────────────────────────────────────────────────────

    def assert_evidence_fresh(self, *, baseline_path: Path | None = None) -> dict[str, str]:
        """Tier B：probe 脚本与 `.kiro/specs/**` evidence 的 digest 必须与基线一致。

        evidence 目录缺失本身即判 stale —— **不**降级为 skip。生产部署不带
        `.kiro/`，所以这一层只在仓库上下文（守卫 / CI）里调用。
        """
        baseline = (
            json.loads((baseline_path or WORD_GATE_BASELINE_PATH).read_text(encoding="utf-8"))
            if baseline_path
            else self.baseline
        )
        observed: dict[str, str] = {}
        for item in (baseline.get("tier_b_evidence") or {}).get("files") or []:
            target = _REPO_ROOT / str(item["path"])
            if not target.is_file():
                raise WordProbeEvidenceStaleError(
                    f"probe evidence 缺失: {item['path']} —— 缺失即 stale，不得跳过"
                )
            digest = _sha256_bytes(target.read_bytes())
            if digest != item["sha256"]:
                raise WordProbeEvidenceStaleError(
                    f"{item['path']}（role={item.get('role')}）digest 漂移："
                    f"基线 {item['sha256'][:12]}… 实测 {digest[:12]}…"
                )
            observed[str(item.get("role"))] = digest
        if not observed:
            raise WordProbeEvidenceStaleError(
                "tier_b_evidence.files 为空 —— 空清单等于没有 evidence 判据"
            )
        return observed

    def assert_carrier_allowed(self, carrier: str) -> None:
        """委派 `CarrierGate.assert_carrier`；转成本域可分辨类型后上抛。"""
        try:
            self.carrier_gate.assert_carrier(carrier, location="word instrumentation")
        except Exception as exc:  # noqa: BLE001
            raise WordCarrierGateError(
                f"identity 载体 {carrier!r} 未过 Task 6 探针门：{exc}"
            ) from exc

    def assert_anchor_allowed(self, anchor: str) -> None:
        try:
            self.carrier_gate.assert_anchor(anchor, location="word instrumentation")
        except Exception as exc:  # noqa: BLE001
            raise WordCarrierGateError(
                f"结构锚点 {anchor!r} 未过 Task 6 探针门：{exc}"
            ) from exc

    def assert_template_under_authority(self, relative_path: str) -> Path:
        """模板必须位于 `backend/wp_templates/` 内（Requirement 9.1）。"""
        return resolve_within_root(
            WORD_TEMPLATE_AUTHORITY_ROOT,
            relative_path,
            boundary="word_template_authority_root",
        )

    def probe_gate_identity(self) -> dict[str, str]:
        """写进 candidate 证据的探针门身份（Requirement 14.16 的记录清单）。"""
        return {
            "carrier_contract_sha256": self.contract_sha256,
            "carrier_gate_digest": self.carrier_gate.source_digest,
            "onlyoffice_build": self.onlyoffice_build,
            "browser": self.browser,
            "source_commit": self.source_commit,
            "runner": self.runner,
            "identity_schema_version": WORD_IDENTITY_SCHEMA_VERSION,
            "instrumentation_version": WORD_INSTRUMENTATION_VERSION,
            "lock_policy": self.lock_policy,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 3. 注入声明
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class WordFieldInjection:
    """一个 field SDT 注入：把模板里的一次性 token 换成 tagged SDT。

    Attributes:
        token: 模板里的一次性定位线索（`${scope}`）。注入后不再有人读它。
        stable_field_key: contract 里的 stable key。
        carrier: `field_sdt_inline` 或 `field_sdt_block`（都必须过 Task 6 门）。
        alias: 内容控件展示名。**只作展示** —— `alias_display_name` 在 Task 6 里
            `admissible_as_identity_anchor=false`，本模块不用它定位。
        expected_token_occurrences: 该 token 在 `word/document.xml` 里**声明的**出现
            次数。全部出现处都注入**同一** tag（AC 7.4 的同 stable key 多实例形态，
            Task 6 的 F03/F05 实测：`${entityName}` 在真实 F2-22 里出现 2 次）。

    🔴 为什么用「声明出现次数」而不是段落序号：段落绝对索引在 Task 6 里
    `probe_verdict=failed`（文首插 2 段后整体位移）。声明次数是**可 fail-closed 的
    不变量** —— 模板改版让 token 变成 1 次或 3 次时立刻打红，而段落序号会静静指错。
    """

    token: str
    stable_field_key: str
    carrier: str = "field_sdt_inline"
    alias: str = ""
    expected_token_occurrences: int = 1
    #: 显式承认「这次用的是**字面文本**而不是 `${...}` 占位」。
    #:
    #: 有些权威模板的目标位置没有占位符，只有标题文本（Task 6 对 B30-11-2 的 H01
    #: 注入用的就是 `内部控制缺陷汇总与评估`）。允许它，但必须**显式**声明，避免有人
    #: 顺手传一段中文标签、误以为那是回写协议的锚点。安全性来自
    #: `expected_token_occurrences` 的 fail-closed 计数，而不是 token 的形态。
    literal_anchor: bool = False

    def __post_init__(self) -> None:
        if not self.token.strip():
            raise WordTokenAnchorError("一次性定位锚点不得为空")
        if _TOKEN_RE.match(self.token):
            if self.literal_anchor:
                raise WordTokenAnchorError(
                    f"{self.token!r} 是 `${{...}}` 占位形态，不应再标 literal_anchor"
                )
        elif not self.literal_anchor:
            raise WordTokenAnchorError(
                f"一次性定位 token 形态非法: {self.token!r}（须形如 `${{scope}}`）—— "
                "若模板里确实只有字面标题可锚，必须显式传 literal_anchor=True，"
                "并由 expected_token_occurrences 锁死命中数（Requirement 7.1："
                "字面文本永远只能是一次性迁移线索，不得作为回写协议锚点）"
            )
        elif "<" in self.token or ">" in self.token:
            raise WordTokenAnchorError(
                f"字面锚点不得含 XML 尖括号: {self.token!r}"
            )
        if self.expected_token_occurrences < 1:
            raise WordTokenAnchorError(
                f"{self.token!r}: expected_token_occurrences 必须 >=1，"
                f"实得 {self.expected_token_occurrences}"
            )
        if self.expected_token_occurrences > 1 and self.carrier == "field_sdt_block":
            raise WordTokenAnchorError(
                f"{self.token!r}: block 级载体不支持多实例 —— 一个 stable key 包多个整段"
                "会让层级不确定（Task 6 只对单实例 block 取过证）"
            )

    @property
    def kind(self) -> str:
        return "block" if self.carrier == "field_sdt_block" else "field"

    @property
    def instances(self) -> str:
        """写进 contract 的 `instances` 取值（`one` / `many`）。"""
        return "one" if self.expected_token_occurrences == 1 else "many"

    @property
    def locator_kind(self) -> str:
        return "one_time_literal_text" if self.literal_anchor else "one_time_token"


@dataclass(frozen=True)
class WordRowInjection:
    """一行的行身份注入（**单元格内** inline field SDT 携带 row_uuid）。

    🔴 刻意**没有** row 级 SDT 选项：`row_sdt` 在 OO 9.4 上首次序列化即被剥离
    （Task 6 实测 0/9 保留），所以那条路径在本模块里不存在，而不是「默认关闭」。

    ═══ 两种**一次性**定位方式，必须恰选一种 ═══

    * `token` —— 单元格里有 `${...}` 占位时用它；
    * `(table_index, row_index, cell_index)` —— 单元格**是空的**时用结构坐标。
      B30-11-2 的三个数据行 30 个单元格实测全为空串，没有任何 token 可锚
      （Task 6 的 `RowInjection` 同样用坐标）。

    这两个都是 design §SDT migration 第 1 条的「**一次性**定位线索」：注入完成之后
    行身份只由 tag 里的 `row_uuid` 承载。运行态 engine
    （`word_sdt_engine`）里没有任何表格/行/单元格序号逻辑 —— 守卫在它的 AST 上
    断言这一点，所以「一次性坐标」不会渗进回写协议。
    """

    #: 契约里的行域模板 key，形如 `rows/{row_uuid}/deficiency`。
    row_field_key_template: str
    row_uuid: str
    token: str = ""
    table_index: int = -1
    row_index: int = -1
    cell_index: int = -1
    #: 空单元格注入时 SDT 的初始内容（默认空串 ⇒ 可见文本流一个字符都不变）。
    seed_text: str = ""
    carrier: str = "cell_level_field_sdt_tag_carrying_row_uuid"

    def __post_init__(self) -> None:
        by_token = bool(self.token)
        by_coords = min(self.table_index, self.row_index, self.cell_index) >= 0
        if by_token == by_coords:
            raise WordTokenAnchorError(
                f"行注入 {self.row_field_key_template!r}: 必须**恰好**给一种一次性定位 —— "
                "有 token 时用 token，空单元格时用 (table_index,row_index,cell_index)；"
                f"实得 token={self.token!r} coords="
                f"({self.table_index},{self.row_index},{self.cell_index})"
            )
        if by_token and not _TOKEN_RE.match(self.token):
            raise WordTokenAnchorError(f"行注入 token 形态非法: {self.token!r}")
        if ROW_UUID_PLACEHOLDER not in self.row_field_key_template:
            raise WordTokenAnchorError(
                f"行域模板 key {self.row_field_key_template!r} 缺 {ROW_UUID_PLACEHOLDER} —— "
                "行身份必须落在 tag 内，不得用表格行号识别（Requirement 7.2）"
            )
        try:
            uuid.UUID(self.row_uuid)
        except (ValueError, AttributeError, TypeError) as exc:
            raise WordTokenAnchorError(
                f"row_uuid {self.row_uuid!r} 不是合法 UUID —— 行身份必须是预生成字面量，"
                "不用易重算公式"
            ) from exc

    @property
    def locator_kind(self) -> str:
        return "one_time_token" if self.token else "one_time_cell_coordinates"


#: 一次性定位方式的**封闭**清单。守卫据它断言「运行态 engine 里一个都不出现」。
ONE_TIME_LOCATOR_KINDS: Final[tuple[str, ...]] = (
    "one_time_token",
    "one_time_literal_text",
    "one_time_cell_coordinates",
)


@dataclass(frozen=True)
class WordInstrumentationSpec:
    """一个 Word entry 的 instrumentation 声明（canonical payload 的语义来源）。"""

    entry_id: str
    contract_id: str
    template_id: str
    template_relative_path: str
    semantic_version: str = "1.0.0"
    fields: tuple[WordFieldInjection, ...] = ()
    rows: tuple[WordRowInjection, ...] = ()

    def __post_init__(self) -> None:
        if not self.fields and not self.rows:
            raise WordInstrumentationError(
                f"entry {self.entry_id}: instrumentation 声明为空 —— 空声明会让"
                "「注入成功」恒真（空集恒等价）"
            )
        tokens = [inj.token for inj in self.fields] + [
            inj.token for inj in self.rows if inj.token
        ]
        duplicates = sorted({t for t in tokens if tokens.count(t) > 1})
        if duplicates:
            raise WordTokenAnchorError(
                f"entry {self.entry_id}: 一次性 token 重复 {duplicates} —— 同 token 多目标"
                "无法区分注入位置"
            )
        coords = [
            (inj.table_index, inj.row_index, inj.cell_index)
            for inj in self.rows
            if not inj.token
        ]
        dup_coords = sorted({c for c in coords if coords.count(c) > 1})
        if dup_coords:
            raise WordTokenAnchorError(
                f"entry {self.entry_id}: 一次性结构坐标重复 {dup_coords} —— 同一单元格"
                "不能承载两个行身份"
            )
        row_uuids = [inj.row_uuid for inj in self.rows]
        dup_rows = sorted({u for u in row_uuids if row_uuids.count(u) > 1})
        if dup_rows:
            raise WordTokenAnchorError(
                f"entry {self.entry_id}: row_uuid 重复 {dup_rows} —— 行身份必须唯一，"
                "复制产生的重复 UUID 默认是结构冲突（Requirement 6.15 的 Word 侧）"
            )

    def carriers(self) -> tuple[str, ...]:
        return tuple(
            sorted({inj.carrier for inj in self.fields} | {inj.carrier for inj in self.rows})
        )

    def expected_tags(self) -> tuple[str, ...]:
        """注入后应当出现的**tag 集合**（去重排序）。

        block 载体产出**两个** tag：外层 `gt:block:…` 容器 + 内层同 key 的
        `gt:field:…` 叶子（Task 6 的 depth=2 形态）。少算内层会让反读判据在真实
        block 注入上必红，也会掩盖「层级被压扁」这条真正要抓的漂移。
        """
        out: list[str] = []
        for inj in self.fields:
            out.append(
                format_sdt_tag(
                    kind=inj.kind,
                    contract_id=self.contract_id,
                    stable_key=inj.stable_field_key,
                )
            )
            if inj.kind == "block":
                out.append(
                    format_sdt_tag(
                        kind="field",
                        contract_id=self.contract_id,
                        stable_key=inj.stable_field_key,
                    )
                )
        out += [
            format_sdt_tag(
                kind="field",
                contract_id=self.contract_id,
                stable_key=inj.row_field_key_template,
                row_uuid=inj.row_uuid,
            )
            for inj in self.rows
        ]
        return tuple(sorted(set(out)))

    def expected_instances(self) -> Mapping[str, int]:
        """每个 tag 声明的实例数（反读断言计数用，不只断言集合）。

        只断言集合会漏掉「同 tag 少了一个实例」：`${entityName}` 从 2 处变 1 处时
        集合完全相同 ⇒ 假绿。
        """
        counts: dict[str, int] = {}
        for inj in self.fields:
            tag = format_sdt_tag(
                kind=inj.kind, contract_id=self.contract_id, stable_key=inj.stable_field_key
            )
            counts[tag] = counts.get(tag, 0) + inj.expected_token_occurrences
            if inj.kind == "block":
                inner = format_sdt_tag(
                    kind="field",
                    contract_id=self.contract_id,
                    stable_key=inj.stable_field_key,
                )
                counts[inner] = counts.get(inner, 0) + inj.expected_token_occurrences
        for inj in self.rows:
            tag = format_sdt_tag(
                kind="field",
                contract_id=self.contract_id,
                stable_key=inj.row_field_key_template,
                row_uuid=inj.row_uuid,
            )
            counts[tag] = counts.get(tag, 0) + 1
        return dict(sorted(counts.items()))

    def expected_row_uuids(self) -> tuple[str, ...]:
        return tuple(sorted({inj.row_uuid for inj in self.rows}))


# ═══════════════════════════════════════════════════════════════════════════
# 4. payload 构造（DAG 前两段；不含任何反向引用）
# ═══════════════════════════════════════════════════════════════════════════


def build_word_template_payload(
    *, spec: WordInstrumentationSpec, template_sha256: str, structure_hash: str
) -> dict[str, Any]:
    payload = {
        "schema_version": WORD_TEMPLATE_SCHEMA_VERSION,
        "template_id": spec.template_id,
        "template_relative_path": spec.template_relative_path,
        "template_sha256": template_sha256,
        "normalized_structure_hash": structure_hash,
        "document_type": WORD_DOCUMENT_TYPE,
    }
    validate_template_payload(payload)
    return payload


def build_word_instrumentation_payload(
    *,
    spec: WordInstrumentationSpec,
    template_definition_sha256: str,
    template_sha256: str,
    gate: WordSdtCarrierGate,
) -> dict[str, Any]:
    """instrumentation canonical payload：只**单向**引用已发布 template digest。

    刻意不含自身 UUID/hash，也不含 `contract_*` / `bundle_*` 任何键 ——
    `validate_instrumentation_payload`（Task 12 单一真源）在此强制。
    """
    for carrier in spec.carriers():
        gate.assert_carrier_allowed(carrier)
    gate.assert_anchor_allowed("w_tag")
    payload = {
        "schema_version": WORD_INSTRUMENTATION_SCHEMA_VERSION,
        "entry_id": spec.entry_id,
        "template_id": spec.template_id,
        "template_definition_sha256": template_definition_sha256,
        "template_sha256": template_sha256,
        "instrumentation_version": WORD_INSTRUMENTATION_VERSION,
        "identity_schema_version": WORD_IDENTITY_SCHEMA_VERSION,
        "document_type": WORD_DOCUMENT_TYPE,
        "identity_carriers": list(spec.carriers()),
        "identity_anchors": ["w_tag"],
        "lock_policy": gate.lock_policy,
        "sdt_tags": list(spec.expected_tags()),
        "row_uuids": list(spec.expected_row_uuids()),
        "probe_onlyoffice_build": gate.onlyoffice_build,
    }
    validate_instrumentation_payload(payload)
    return payload


# ═══════════════════════════════════════════════════════════════════════════
# 5. zip-level 注入
# ═══════════════════════════════════════════════════════════════════════════


@dataclass(frozen=True)
class InstrumentedDocx:
    """注入产物 + 可核对的观测量。"""

    instrumented_bytes: bytes
    instrumented_sha256: str
    injected_tags: tuple[str, ...]
    row_uuids: tuple[str, ...]
    #: 除 `word/document.xml` 之外**逐字节复制**的 entry 数（守卫断言 > 0）。
    untouched_parts: int
    #: 每个 entry 的字节是否与源一致（`word/document.xml` 之外必须全 True）。
    part_bytes_identical: Mapping[str, bool]


def _xml_escape_attr(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _sdt_wrapper(*, tag: str, alias: str, inner: str) -> str:
    """构造一个 `w:sdt`。**不写** `w:lock`、**不写** `w:id`。

    * 不写 `w:lock` —— Task 6 的 `no_w_lock_injected` 前提；
    * 不写 `w:id` —— Task 6 实测同一 stable key 的两个实例注入**相同** `w:id` 后 OO
      原样接受 ⇒ 该值在本协议下不唯一、无定位价值。不写它可以让「有人拿 `w:id` 当
      锚点」在结构上就没有素材。
    """
    props = [f'<w:tag w:val="{_xml_escape_attr(tag)}"/>']
    if alias:
        props.insert(0, f'<w:alias w:val="{_xml_escape_attr(alias)}"/>')
    return (
        "<w:sdt><w:sdtPr>"
        + "".join(props)
        + "</w:sdtPr><w:sdtContent>"
        + inner
        + "</w:sdtContent></w:sdt>"
    )


def _iter_wt_texts(xml: str) -> list[str]:
    """按序取出全部 `w:t` 的文本内容。

    🔴 `"<w:t"` 是 `"<w:tag"` 的前缀 —— 按裸前缀匹配会把 `w:sdtPr` 里的
    `<w:tag w:val="gt:field:…"/>` 当成一个文本节点开头，然后一路吞到下一个
    `</w:t>`，把中间整段 XML 当成「可见文本」。2026-08-29 首轮实测正是这个形态：
    注入 `${purpose}` 后可见文本从 546 涨到 632 字符，多出来的 86 字符是
    `</w:sdtPr><w:sdtContent><w:r>…` 这串标记。

    因此必须检查 `<w:t` 之后紧跟的字符是 `>` / 空白 / `/`。
    """
    pieces: list[str] = []
    pos = 0
    while True:
        idx = xml.find(_W_T_OPEN, pos)
        if idx == -1:
            break
        after = xml[idx + len(_W_T_OPEN) : idx + len(_W_T_OPEN) + 1]
        if after not in (">", " ", "\t", "\r", "\n", "/"):
            pos = idx + len(_W_T_OPEN)
            continue
        gt = xml.find(">", idx)
        if gt == -1:
            break
        if xml[gt - 1 : gt] == "/":  # `<w:t/>` 空文本节点
            pos = gt + 1
            continue
        end = xml.find("</w:t>", gt)
        if end == -1:
            break
        pieces.append(xml[gt + 1 : end])
        pos = end + len("</w:t>")
    return pieces


def _run_text(run_xml: str) -> str:
    """一个 `w:r` 里全部 `w:t` 的拼接文本（`w:br` 等不计入 —— 只用于定位 token）。"""
    return "".join(_iter_wt_texts(run_xml))


def _plain_run(text: str, rpr: str) -> str:
    return f'<w:r>{rpr}<w:t xml:space="preserve">{_xml_escape_attr(text)}</w:t></w:r>'


#: Task 6 契约声明的、本模块唯一接受的 lock policy。
REQUIRED_PROBE_LOCK_POLICY: Final[str] = "no_w_lock_injected"


def assert_probe_lock_policy(lock_policy: str) -> None:
    """Task 6 契约的 `lock_policy` 必须仍是 `no_w_lock_injected`。

    🔴 抽成公开函数的理由同 :func:`assert_no_sdt_lock`：磁盘上的契约里这个值恒为
    `no_w_lock_injected`，判据在 `load()` 内部**结构不可达** ⇒ 变异必判 GREEN
    （2026-08-29 M31 实测）。抽出来后守卫能直接喂一个不同取值。

    语义：探针刻意**不加** `<w:lock>`，因为加锁会让 OO 无法删除 SDT，等于替载体作弊。
    整份载体保留结论（26/26 field、17/17 block、0/9 row）都建立在这个前提上，policy
    一变就必须重新取证。
    """
    if lock_policy != REQUIRED_PROBE_LOCK_POLICY:
        raise WordCarrierGateError(
            f"Task 6 契约的 lock_policy={lock_policy!r} —— 本模块的注入判据建立在"
            f"「{REQUIRED_PROBE_LOCK_POLICY}」前提上（无 w:lock 时 OO 是否自发保留 tag），"
            "policy 变化必须重跑探针并重新裁决"
        )


def assert_no_sdt_lock(document_xml: str, *, entry_id: str) -> None:
    """注入结果里不得出现 `w:lock`（Task 6 的 `no_w_lock_injected` 前提）。

    🔴 抽成**公开函数**而不是埋在 `instrument_docx_bytes` 里：`_sdt_wrapper` 本来就
    不写 `w:lock`，所以这条判据在公开 API 上**结构不可达** ⇒ 变异检验必判 GREEN
    （2026-08-29 M28 实测正是如此）。抽出来之后守卫可以直接喂一段含 `<w:lock` 的 XML
    让它可达，于是「有人往 `_sdt_wrapper` 里加锁」这件事真的会打红。
    """
    if _FORBIDDEN_SDT_CHILD in document_xml:
        raise WordLockPolicyError(
            f"entry {entry_id}: 注入结果里出现 `w:lock` —— Task 6 的载体结论建立在"
            "「无保护」前提上，加锁等于替载体作弊（lock_policy=no_w_lock_injected）；"
            "载体是否在**无保护**下自发保留 tag 是那份探针唯一回答的问题"
        )


def assert_only_document_part_changed(
    part_bytes_identical: Mapping[str, bool], *, entry_id: str
) -> None:
    """除 `word/document.xml` 外的部件必须逐字节保留（Requirement 7.3 / 9.9）。

    🔴 同 :func:`assert_no_sdt_lock`：抽成公开函数才能让这条防御判据可达
    （M27 首轮实测 GREEN）。批注 `comments.xml`、修订、图片 `media/`、页眉页脚、
    `styles.xml`、`numbering.xml`、`customXml/` 都在它保护范围内。
    """
    leaked = sorted(
        name
        for name, same in part_bytes_identical.items()
        if not same and name != WORD_DOCUMENT_PART
    )
    if leaked:
        raise WordVisibleEquivalenceError(
            f"entry {entry_id}: instrumentation 改动了 {WORD_DOCUMENT_PART} 之外的部件 "
            f"{leaked} —— 批注/修订/图片/页眉页脚/styles/numbering/customXml 必须逐字节"
            "保留（Requirement 7.3 / 9.9）"
        )


def _top_level_spans(xml: str, local: str) -> list[tuple[int, int, int, int]]:
    """`<w:{local}>` 的**最外层**（互不嵌套）span 列表，按文档顺序。

    用于一次性结构坐标注入。嵌套表格/嵌套行会让「第 N 个」歧义，故只取最外层并
    要求调用方的坐标落在其中；越界一律 fail closed。
    """
    from app.services.workpaper_sync.word_sdt_engine import _find_spans

    spans = _find_spans(xml, local)
    return [
        span
        for span in spans
        if not any(
            other is not span and other[0] < span[0] and other[3] >= span[3]
            for other in spans
        )
    ]


def _split_token_paragraph(
    paragraph: str, token: str
) -> tuple[str, str, str, str, str] | None:
    """把含 token 的段落切成 `(前缀 XML, 前置普通 run, token 的 run, 后置普通 run, 后缀 XML)`。

    🔴 为什么必须切到 **token 边界**、不能整 run 包进 SDT：F2-22 的 p04 是**一个
    run** 里放着「根据《…》的要求,为了对 ${entityName}(以下简称…)${bsDate}资产负债表
    上存货的…」整句。把整个 run 包进 SDT 之后，

    * extract 会把整句当成 `plan/entity_name` 的值；
    * materialize 会用字段值**替换整句** ⇒ 审计师的自由正文被一次同步抹掉，
      正是 Requirement 7.3 / 7.9 要防的东西。

    2026-08-29 首轮实测就是这个形态：`outside_sdt_text` 从 31 块掉到 26 块，
    5 个整段的自由正文全部被吞进 SDT。

    跨 run token（design §SDT migration 第 3 条）由「合并 [start_run, end_run] 区间后
    再按文本切」统一处理：前后剩余文本各自回落成普通 run，样式沿用**第一个** run 的
    `w:rPr`（那是 token 实际所在的样式）。
    """
    from app.services.workpaper_sync.word_sdt_engine import _find_spans

    runs = [s for s in _find_spans(paragraph, "r") if s[3] > s[0]]
    if not runs:
        return None
    texts = [_run_text(paragraph[s[0] : s[3]]) for s in runs]
    joined = "".join(texts)
    at = joined.find(token)
    if at == -1:
        return None

    start_run = end_run = None
    offsets: list[int] = []
    cursor = 0
    for text in texts:
        offsets.append(cursor)
        cursor += len(text)
    for idx, text in enumerate(texts):
        begin, end = offsets[idx], offsets[idx] + len(text)
        if start_run is None and end > at:
            start_run = idx
        if end >= at + len(token):
            end_run = idx
            break
    if start_run is None or end_run is None:
        return None

    merged_start = offsets[start_run]
    merged_text = joined[merged_start : offsets[end_run] + len(texts[end_run])]
    local = at - merged_start
    prefix_text = merged_text[:local]
    suffix_text = merged_text[local + len(token) :]

    first_run_xml = paragraph[runs[start_run][0] : runs[start_run][3]]
    rpr_spans = _find_spans(first_run_xml, "rPr")
    rpr = first_run_xml[rpr_spans[0][0] : rpr_spans[0][3]] if rpr_spans else ""

    return (
        paragraph[: runs[start_run][0]],
        _plain_run(prefix_text, rpr) if prefix_text else "",
        _plain_run(token, rpr),
        _plain_run(suffix_text, rpr) if suffix_text else "",
        paragraph[runs[end_run][3] :],
    )


def instrument_docx_bytes(
    source: bytes, spec: WordInstrumentationSpec, *, gate: WordSdtCarrierGate
) -> InstrumentedDocx:
    """在原 OOXML 上**包裹/创建** `w:sdt` 并写 `w:tag`；只改 `word/document.xml`。

    design §SDT migration 的 1~6 步在此落地：token 只作一次性线索、跨 run 合并、
    同段多 token 各建独立 SDT、保存后重新打开 zip 校验 tag 集合/层级。
    """
    from app.services.workpaper_sync.word_sdt_engine import _find_spans

    for carrier in spec.carriers():
        gate.assert_carrier_allowed(carrier)
    gate.assert_anchor_allowed("w_tag")

    with zipfile.ZipFile(io.BytesIO(source)) as zf:
        infos = zf.infolist()
        names = [i.filename for i in infos]
        if WORD_DOCUMENT_PART not in names:
            raise WordInstrumentationError(
                f"源 DOCX 缺 {WORD_DOCUMENT_PART} —— 不是合法 wordprocessing 文档"
            )
        original: dict[str, bytes] = {i.filename: zf.read(i) for i in infos}
        order = [(i.filename, i.compress_type) for i in infos]

    xml = original[WORD_DOCUMENT_PART].decode("utf-8")
    injected: list[str] = []

    def _token_paragraphs(token: str) -> list[tuple[int, int, int, int]]:
        """含 token 的**最内层** `w:p` span（按文档顺序）。

        `w:p` 本身不嵌套，但表格里的 `w:p` 会落在外层 `w:tbl` 的扫描结果之内；
        故过滤掉任何完全包含另一个命中的 span。
        """
        hits = [span for span in _find_spans(xml, "p") if token in xml[span[1] : span[2]]]
        return [
            span
            for span in hits
            if not any(
                other is not span and other[0] > span[0] and other[3] <= span[3]
                for other in hits
            )
        ]

    def _inject(
        token: str, tag: str, alias: str, *, wrap_block: bool, expected: int
    ) -> None:
        nonlocal xml
        hits = _token_paragraphs(token)
        if len(hits) != expected:
            raise WordTokenAnchorError(
                f"entry {spec.entry_id}: 一次性 token {token!r} 在 {WORD_DOCUMENT_PART} 里"
                f"命中 {len(hits)} 个段落，声明 {expected} 个 —— 缺失、重复与漂移都必须 "
                "fail closed，不得按段落序号挑一个（Requirement 7.1）"
            )
        # 从后往前注入：先改后面的 span，前面的下标才不漂移。
        for p_start, inner_start, inner_end, p_end in sorted(hits, reverse=True):
            paragraph = xml[inner_start:inner_end]
            split = _split_token_paragraph(paragraph, token)
            if split is None:
                raise WordTokenAnchorError(
                    f"entry {spec.entry_id}: token {token!r} 所在段落无法定位 run —— "
                    f"段落 XML 前 120 字符: {paragraph[:120]!r}"
                )
            lead, prefix_run, token_run, suffix_run, trail = split
            head = lead + prefix_run
            body = token_run
            tail = suffix_run + trail
            if wrap_block:
                # block 级：整段（含 pPr）放进外层 SDT，内层再包一个同 key 的 inline
                # SDT ⇒ depth=2 层级（Task 6 的 F06 形态，17/17 artifact 保留）。
                parsed = parse_sdt_tag(tag)
                assert parsed is not None  # format_sdt_tag 已保证形态合法
                inner_tag = format_sdt_tag(
                    kind="field",
                    contract_id=spec.contract_id,
                    stable_key=parsed.stable_key,
                )
                inner_wrapped = (
                    head + _sdt_wrapper(tag=inner_tag, alias=alias, inner=body) + tail
                )
                whole = (
                    xml[p_start:inner_start] + inner_wrapped + xml[inner_end:p_end]
                )
                xml = (
                    xml[:p_start]
                    + _sdt_wrapper(tag=tag, alias=alias, inner=whole)
                    + xml[p_end:]
                )
                injected.extend([tag, inner_tag])
                continue
            xml = (
                xml[:inner_start]
                + head
                + _sdt_wrapper(tag=tag, alias=alias, inner=body)
                + tail
                + xml[inner_end:]
            )
            injected.append(tag)

    for inj in spec.fields:
        tag = format_sdt_tag(
            kind=inj.kind, contract_id=spec.contract_id, stable_key=inj.stable_field_key
        )
        _inject(
            inj.token,
            tag,
            inj.alias,
            wrap_block=inj.kind == "block",
            expected=inj.expected_token_occurrences,
        )
    def _inject_cell(row: WordRowInjection, tag: str) -> None:
        """空单元格的一次性结构坐标注入（B30-11-2 的三个数据行全空，无 token 可锚）。"""
        nonlocal xml
        tables = _top_level_spans(xml, "tbl")
        if row.table_index >= len(tables):
            raise WordTokenAnchorError(
                f"entry {spec.entry_id}: table_index={row.table_index} 越界"
                f"（表数 {len(tables)}）"
            )
        t_start, t_inner_s, t_inner_e, t_end = tables[row.table_index]
        table_xml = xml[t_inner_s:t_inner_e]
        rows_ = _top_level_spans(table_xml, "tr")
        if row.row_index >= len(rows_):
            raise WordTokenAnchorError(
                f"entry {spec.entry_id}: row_index={row.row_index} 越界（行数 {len(rows_)}）"
            )
        r_start, r_inner_s, r_inner_e, r_end = rows_[row.row_index]
        row_xml = table_xml[r_inner_s:r_inner_e]
        cells = _top_level_spans(row_xml, "tc")
        if row.cell_index >= len(cells):
            raise WordTokenAnchorError(
                f"entry {spec.entry_id}: cell_index={row.cell_index} 越界"
                f"（单元格数 {len(cells)}）"
            )
        c_start, c_inner_s, c_inner_e, c_end = cells[row.cell_index]
        cell_xml = row_xml[c_inner_s:c_inner_e]
        paras = _top_level_spans(cell_xml, "p")
        if not paras:
            raise WordTokenAnchorError(
                f"entry {spec.entry_id}: 目标单元格无 w:p，无法放 inline SDT"
            )
        p_start, p_inner_s, p_inner_e, p_end = paras[0]
        para_inner = cell_xml[p_inner_s:p_inner_e]
        wrapped = _sdt_wrapper(tag=tag, alias="", inner=_plain_run(row.seed_text, ""))
        new_para_inner = para_inner + wrapped
        new_cell = cell_xml[:p_inner_s] + new_para_inner + cell_xml[p_inner_e:]
        new_row = row_xml[:c_inner_s] + new_cell + row_xml[c_inner_e:]
        new_table = table_xml[:r_inner_s] + new_row + table_xml[r_inner_e:]
        xml = xml[:t_inner_s] + new_table + xml[t_inner_e:]
        injected.append(tag)

    for row in spec.rows:
        tag = format_sdt_tag(
            kind="field",
            contract_id=spec.contract_id,
            stable_key=row.row_field_key_template,
            row_uuid=row.row_uuid,
        )
        if row.token:
            _inject(row.token, tag, "", wrap_block=False, expected=1)
        else:
            _inject_cell(row, tag)

    assert_no_sdt_lock(xml, entry_id=spec.entry_id)

    parts = dict(original)
    parts[WORD_DOCUMENT_PART] = xml.encode("utf-8")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as out:
        for name, compress in order:
            out.writestr(zipfile.ZipInfo(name), parts[name], compress_type=compress)
    produced = buffer.getvalue()

    identical = {
        name: parts[name] == original[name] for name, _ in order
    }
    assert_only_document_part_changed(identical, entry_id=spec.entry_id)
    return InstrumentedDocx(
        instrumented_bytes=produced,
        instrumented_sha256=_sha256_bytes(produced),
        injected_tags=tuple(sorted(injected)),
        row_uuids=spec.expected_row_uuids(),
        untouched_parts=len(order) - 1,
        part_bytes_identical=identical,
    )




# ═══════════════════════════════════════════════════════════════════════════
# 6. 等价校验与反读
# ═══════════════════════════════════════════════════════════════════════════

#: 注入**必然**会改变的两个结构 aspect：tag 集合从空变成声明集合、层级随之出现。
#: 其余 aspect 一律要求逐项等价 —— 白名单只有这两项，不给「样式也许会变」留口子。
#: `outside_sdt_text` **不在**白名单里：它的变化必须逐块用声明 token 解释
#: （见 :func:`_explain_outside_text_delta`），而不是整格豁免。
_INSTRUMENTATION_ALLOWED_ASPECTS: Final[frozenset[str]] = frozenset(
    {"sdt_tag_set", "sdt_hierarchy"}
)


def visible_text_stream(data: bytes) -> tuple[str, int]:
    """`word/document.xml` 里全部 `w:t` 的按序拼接（规范化）+ 字符数。

    这是 instrumentation 的**最强不变量**：注入只加结构、不改内容，所以可见文本流
    必须逐字符相同。它不依赖 SDT 结构，因此「文本从 SDT 外移到 SDT 内」不会让它
    误报 —— 那正是 `outside_sdt_text` 单独判定会踩的坑。
    """
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        xml = zf.read(WORD_DOCUMENT_PART).decode("utf-8")
    joined = "".join(_iter_wt_texts(xml))
    return _sha256_bytes(joined.encode("utf-8")), len(joined)


def _explain_outside_text_delta(
    aspect: Mapping[str, Any], *, tokens: Sequence[str]
) -> dict[str, Any]:
    """SDT 外正文的增删必须**逐块**被声明 token 解释，不整格豁免。

    * 消失的块：必须含至少一个声明 token（token 文本移进了 SDT）；
    * 新增的块：必须是某个消失块去掉 token 后的剩余（切分后的自由正文回落）。

    任何解释不了的增删都是真实的正文损坏，立即打红。这条比「把 `outside_sdt_text`
    整格加白名单」强得多：整格豁免之后，「注入顺手吞掉一整段」也会照样绿
    （2026-08-29 首轮实测正是这个形态）。
    """
    removed = [str(t) for t in aspect.get("removed") or []]
    added = [str(t) for t in aspect.get("added") or []]
    unexplained_removed = [
        text for text in removed if not any(token in text for token in tokens)
    ]
    unexplained_added: list[str] = []
    for text in added:
        stripped_sources = [
            "".join(part for part in _strip_tokens(src, tokens)) for src in removed
        ]
        if not any(text in src or src in text for src in stripped_sources):
            unexplained_added.append(text)
    return {
        "removed_count": len(removed),
        "added_count": len(added),
        "unexplained_removed": unexplained_removed,
        "unexplained_added": unexplained_added,
        "explained": not unexplained_removed and not unexplained_added,
    }


def _strip_tokens(text: str, tokens: Sequence[str]) -> list[str]:
    out = text
    for token in tokens:
        out = out.replace(token, "")
    return [out]


def verify_docx_visible_equivalence(
    *, source: bytes, instrumented: InstrumentedDocx, spec: WordInstrumentationSpec
) -> dict[str, Any]:
    """注入前后可见文本 / 结构 / 样式 / 批注 / 修订 / 图片必须等价（Requirement 7.3 / 9.9）。

    ═══ 三层判据 ═══

    1. **可见文本流逐字符相同**（:func:`visible_text_stream`）—— 最强的一条：注入只加
       结构不改内容。
    2. `outside_sdt_text` 的增删**逐块**由声明 token 解释
       （:func:`_explain_outside_text_delta`），不整格豁免。
    3. 其余 aspect（表格形状、受保护部件 = 批注/修订/图片/页眉页脚/styles/numbering/
       customXml）逐项等价；只有 `sdt_tag_set` / `sdt_hierarchy` 允许新增。

    ═══ 覆盖计数是硬判据 ═══

    手搓的最小 DOCX 上「SDT 外正文」是空集、「受保护部件」是空 dict ⇒ 判定恒真
    （假绿第⑥源「空集恒等价」）。因此本函数把每个 aspect 的**覆盖计数**一起返回，
    守卫断言 `coverage[...] > 0`，从而要求 fixture 用真实权威模板。
    """
    report = body_preservation_report(
        source,
        instrumented.instrumented_bytes,
        label_before="template",
        label_after="instrumented",
        allow_tag_additions=True,
    )
    if any(report["collection_errors"].values()):
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: 等价报告采集侧报错 {report['collection_errors']} —— "
            "采集失败不得当成「没有差异」"
        )
    before = structure_fingerprint(source)
    after = structure_fingerprint(instrumented.instrumented_bytes)
    if before.errors or after.errors:
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: 结构采集报错 before={before.errors} after={after.errors}"
        )
    if before.tag_set():
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: 源模板里已存在 SDT tag {before.tag_set()[:5]} —— "
            "重复 instrumentation 会产生同 tag 多实例，必须先走 versioned upgrader 的"
            "回滚而不是二次注入"
        )

    text_before, chars_before = visible_text_stream(source)
    text_after, chars_after = visible_text_stream(instrumented.instrumented_bytes)
    if text_before != text_after:
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: 可见文本流在注入前后不同（{chars_before} → "
            f"{chars_after} 字符，digest {text_before[:12]}… → {text_after[:12]}…）—— "
            "instrumentation 只允许加结构，一个可见字符都不许改"
            "（Requirement 7.3 / 9.9）"
        )

    tokens = [inj.token for inj in spec.fields] + [inj.token for inj in spec.rows]
    outside = _explain_outside_text_delta(
        report["aspects"]["outside_sdt_text"], tokens=tokens
    )
    if not outside["explained"]:
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: SDT 外自由正文出现无法用声明 token 解释的变化："
            f"消失 {outside['unexplained_removed'][:3]}，新增 "
            f"{outside['unexplained_added'][:3]} —— 自由正文必须逐块保留"
            "（Requirement 7.3 / 7.9）"
        )

    bad = [
        aspect
        for aspect, ok in sorted(report["aspect_verdicts"].items())
        if not ok
        and aspect not in _INSTRUMENTATION_ALLOWED_ASPECTS
        and aspect != "outside_sdt_text"
    ]
    if bad:
        raise WordVisibleEquivalenceError(
            f"entry {spec.entry_id}: instrumentation 破坏了可见结构，首批不等价 aspect "
            f"{bad}；详情 {[report['aspects'][a] for a in bad][:2]}"
            "（Requirement 7.3：批注/修订/图片/表格/样式必须保留）"
        )
    coverage = {
        "visible_text_chars": chars_before,
        "outside_sdt_text": len(before.outside_sdt_texts()),
        "protected_parts": sum(len(v) for v in before.protected_parts.values()),
        "protected_part_classes": len(before.protected_parts),
        "table_shape": len(before.table_shapes),
        "fonts_used": len(before.fonts_used),
        "part_count": len(before.part_names),
        "untouched_parts": instrumented.untouched_parts,
        "declared_tokens": len(tokens),
    }
    return {
        "schema_version": "word-instrumentation-equivalence:v1",
        "preserved_aspects": dict(sorted(report["aspect_verdicts"].items())),
        "equivalent": True,
        "visible_text_digest": text_before,
        "outside_sdt_text_delta": outside,
        "coverage": coverage,
        "aspects": report["aspects"],
        "collection_errors": report["collection_errors"],
    }


def read_back_word_tags(
    *, instrumented: InstrumentedDocx, spec: WordInstrumentationSpec, gate: WordSdtCarrierGate
) -> dict[str, Any]:
    """重新打开 zip，按 `w:tag` 反读 tag 集合 / 层级 / row_uuid（design 第 5 步）。

    🔴 反读**只**走 `parse_sdt_tag`（`gt:` 方案）。不传、也不接受任何段落序号或
    `w:id`：那两个锚点在 Task 6 里分别 `failed` 与「不唯一」。
    """
    gate.assert_anchor_allowed("w_tag")
    fingerprint = structure_fingerprint(instrumented.instrumented_bytes)
    if fingerprint.errors:
        raise WordTagReadbackError(
            f"entry {spec.entry_id}: 反读采集报错 {fingerprint.errors}"
        )
    observed = sorted({node.tag for node in fingerprint.sdt_nodes if node.tag})
    expected = list(spec.expected_tags())
    if observed != sorted(expected):
        raise WordTagReadbackError(
            f"entry {spec.entry_id}: 反读 tag 集合不符：期望 {sorted(expected)}，"
            f"实得 {observed} —— 缺失与多余都必须 fail closed"
        )
    # 🔴 集合之外还要逐 tag 比**实例计数**：`${entityName}` 从 2 处掉到 1 处时集合
    #    完全相同，只比集合会判绿（Requirement 7.10「字段实例计数」）。
    observed_counts = {
        tag: sum(1 for node in fingerprint.sdt_nodes if node.tag == tag)
        for tag in observed
    }
    want_counts = dict(spec.expected_instances())
    if observed_counts != want_counts:
        raise WordTagReadbackError(
            f"entry {spec.entry_id}: 反读实例计数不符：期望 {want_counts}，"
            f"实得 {observed_counts} —— 同 tag 少一个实例也必须 fail closed"
        )
    untagged = sum(1 for node in fingerprint.sdt_nodes if not node.tag)
    if untagged:
        raise WordTagReadbackError(
            f"entry {spec.entry_id}: 注入产生了 {untagged} 个无 tag 的 SDT —— "
            "无 tag 的 SDT 无法定位，等于制造不可读区域"
        )
    rows: dict[str, list[str]] = {}
    for node in fingerprint.sdt_nodes:
        ref = parse_sdt_tag(node.tag)
        if ref is not None and ref.row_scoped:
            assert ref.row_uuid is not None
            rows.setdefault(ref.contract_id, []).append(ref.row_uuid)
    observed_rows = sorted({u for us in rows.values() for u in us})
    if observed_rows != list(spec.expected_row_uuids()):
        raise WordTagReadbackError(
            f"entry {spec.entry_id}: 反读 row_uuid 集合不符：期望 "
            f"{list(spec.expected_row_uuids())}，实得 {observed_rows}"
        )
    duplicates = sorted({u for us in rows.values() for u in us if us.count(u) > 1})
    hierarchy = fingerprint.hierarchy_map()
    return {
        "tags": observed,
        "tag_count": len(observed),
        "instance_count": len(fingerprint.sdt_nodes),
        "hierarchy": hierarchy,
        "kind_map": fingerprint.kind_map(),
        "row_uuids": observed_rows,
        "duplicate_row_uuids": duplicates,
        "untagged_sdt_count": untagged,
        "aspect_digests": fingerprint.aspect_digests(),
    }


# ═══════════════════════════════════════════════════════════════════════════
# 7. 编排器
# ═══════════════════════════════════════════════════════════════════════════


class WordInstrumentationUpgrader:
    """存量 DOCX artifact → non-current `working_paper_representation_upgrade_candidate`。

    流程（design §Versioned upgrader 的前置阶段，顺序即判据）::

        1. WordSdtCarrierGate.load()   —— Task 6 载体裁决 + Tier A stale 门
        2. publish template definition —— DAG 第一段（权威源 backend/wp_templates/）
        3. publish instrumentation     —— 只单向引用 template digest
        4. 复制源 artifact 字节 → zip-level 注入（源文件只读）
        5. 可见结构/样式/批注/修订/图片等价 + tag 反读 + 业务 projection 等值
        6. stage_upgrade_candidate     —— `.upgrade-candidates/` 隔离命名空间
        7. create_upgrade_candidate    —— state=awaiting_contract，两个 target 全 None

    第 7 步之后**就结束了**。published representation / entry pointer / content
    revision 一个都不碰，且这三件事在门面层不可达（:class:`CandidateOnlyRepository`）。
    """

    def __init__(
        self,
        *,
        session: Any,
        repository: Any,
        artifacts: Any,
        project_id: uuid.UUID,
        source_commit: str,
        gate: WordSdtCarrierGate | None = None,
    ) -> None:
        self._session = session
        # 🔴 无条件包门面：即便调用方传裸 repository，本类也拿不到那四类写入面。
        self._repo = (
            repository
            if isinstance(repository, CandidateOnlyRepository)
            else CandidateOnlyRepository(repository)
        )
        self._artifacts = artifacts
        self._project_id = project_id
        self._source_commit = source_commit
        self._gate = gate or WordSdtCarrierGate.load()

    @property
    def gate(self) -> WordSdtCarrierGate:
        return self._gate

    @property
    def repository(self) -> CandidateOnlyRepository:
        return self._repo

    # ─────────────────────────────────────────────────────────────

    async def publish_definitions(
        self, *, spec: WordInstrumentationSpec, wp_id: uuid.UUID, template_bytes: bytes
    ) -> tuple[Any, Any, dict[str, Any]]:
        """按 DAG 发布 template → instrumentation。发布逻辑**委派** Task 12。

        `publish_definition` 内部对 instrumentation 会调 `assert_publish_order`，
        template 未 approved 时直接抛 —— 顺序不是靠本方法语句先后保证的。
        """
        publisher = DefinitionPublisher(
            artifacts=self._artifacts,
            repository=self._repo,
            project_id=self._project_id,
            wp_id=wp_id,
            source_commit=self._source_commit,
        )
        structure_hash = word_structure_hash(template_bytes)
        template_payload = build_word_template_payload(
            spec=spec,
            template_sha256=_sha256_bytes(template_bytes),
            structure_hash=structure_hash,
        )
        template_def = await publisher.publish_definition(
            kind=DefinitionKind.template,
            payload=template_payload,
            logical_id=f"word-template/{spec.template_id}",
            semantic_version=spec.semantic_version,
            blob_bytes=template_bytes,
            structure_hash=structure_hash,
        )
        instrumentation_payload = build_word_instrumentation_payload(
            spec=spec,
            template_definition_sha256=template_def.sha256,
            template_sha256=_sha256_bytes(template_bytes),
            gate=self._gate,
        )
        instrumentation_def = await publisher.publish_definition(
            kind=DefinitionKind.instrumentation,
            payload=instrumentation_payload,
            logical_id=f"word-instrumentation/{spec.entry_id}",
            semantic_version=spec.semantic_version,
        )
        return template_def, instrumentation_def, instrumentation_payload

    # ─────────────────────────────────────────────────────────────

    def instrument_source_bytes(
        self, *, source: bytes, spec: WordInstrumentationSpec
    ) -> tuple[InstrumentedDocx, dict[str, Any], dict[str, Any]]:
        """注入 + 等价校验 + tag 反读。纯函数式（只吃 bytes），不碰 DB 也不碰模板库。"""
        instrumented = instrument_docx_bytes(source, spec, gate=self._gate)
        equivalence = verify_docx_visible_equivalence(
            source=source, instrumented=instrumented, spec=spec
        )
        readback = read_back_word_tags(
            instrumented=instrumented, spec=spec, gate=self._gate
        )
        return instrumented, equivalence, readback

    def validate_candidate_offline(
        self,
        *,
        source: bytes,
        spec: WordInstrumentationSpec,
        binding: WordEngineBinding,
        staging_dir: Path,
    ) -> dict[str, Any]:
        """缺 approved bundle 时**唯一**允许的动作：离线验证 candidate 字节。

        五段判据，顺序即依赖：

        1. 注入（zip-level，只改 `word/document.xml`）；
        2. **注入前后**的可见等价 —— `verify_docx_visible_equivalence`（可见文本流逐
           字符相同 + SDT 外正文增删逐块由声明 token 解释 + 其余 aspect 等价）；
        3. tag 反读（集合 + 逐 tag 实例计数 + row_uuid 集合）；
        4. candidate 上的 extract（只认 tag）；
        5. **candidate → 重新 materialize → candidate'** 的 Word-only 等价
           （`verify_word_only_regions`）。

        🔴 第 5 步的两侧是 **candidate 与 candidate'**，不是「源模板与 candidate」。
        后者必然不等价：注入把 token 文本从「SDT 外」搬进了「SDT 内」，
        `outside_sdt_text` 一格天然要变 —— 那条差异属于第 2 步的口径（逐块用声明
        token 解释），拿第 5 步的口径去判会永远打红。2026-08-29 首轮实测正是这个形态。

        全程 :meth:`WordEngineBinding.assert_may_publish` 在离线模式恒抛，因此这条
        路径结构上到不了发布。返回报告供 candidate 证据使用。
        """
        from app.services.workpaper_sync.adapters.base import SubstrateRole
        from app.services.workpaper_sync.models import ArtifactKind, ArtifactState
        from app.services.workpaper_sync.word_sdt_engine import (
            extract_word_projection,
            materialize_word_projection,
            verify_word_only_regions,
        )

        instrumented, equivalence, readback = self.instrument_source_bytes(
            source=source, spec=spec
        )
        staging_dir.mkdir(parents=True, exist_ok=True)
        candidate = staging_dir / f"{spec.entry_id}.candidate.docx"
        candidate.write_bytes(instrumented.instrumented_bytes)
        extracted = extract_word_projection(
            artifact=candidate,
            binding=binding,
            substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )
        roundtrip = staging_dir / f"{spec.entry_id}.candidate.roundtrip.docx"
        materialize_word_projection(
            substrate=candidate,
            projection=extracted.projection,
            output=roundtrip,
            binding=binding,
            substrate_role=SubstrateRole.staged_result,
            artifact_kind=ArtifactKind.canonical,
            artifact_state=ArtifactState.staged,
        )
        word_only = verify_word_only_regions(
            before=candidate, after=roundtrip, binding=binding
        )
        word_only.assert_equivalent()
        return {
            "schema_version": "word-candidate-offline-validation:v1",
            "entry_id": spec.entry_id,
            "instrumented_sha256": instrumented.instrumented_sha256,
            "roundtrip_sha256": _sha256_bytes(roundtrip.read_bytes()),
            "equivalence": equivalence,
            "readback": readback,
            "extract": extracted.as_dict(),
            "word_only": {
                "equivalent": word_only.equivalent,
                "inspected_aspects": list(word_only.inspected_aspects),
                "coverage": dict(word_only.details.get("coverage", {})),
            },
            "probe_gate": self._gate.probe_gate_identity(),
            "publish_blocked": True,
        }

    # ─────────────────────────────────────────────────────────────

    async def stage_and_register_candidate(
        self,
        *,
        spec: WordInstrumentationSpec,
        wp_id: uuid.UUID,
        content_version_id: uuid.UUID,
        source_representation_id: uuid.UUID,
        source_bytes: bytes,
        instrumented: InstrumentedDocx,
        equivalence: Mapping[str, Any],
        readback: Mapping[str, Any],
        template_definition: Any,
        instrumentation_definition: Any,
        from_definition_bundle_id: uuid.UUID | None = None,
        from_definition_bundle_sha256: str | None = None,
        actor_id: uuid.UUID | None = None,
    ) -> UpgradeCandidateOutcome:
        """把 instrumented 字节移入 candidate 隔离目录并登记 **non-current** candidate。"""
        before = await self._snapshot(wp_id=wp_id, entry_id=spec.entry_id)

        report = {
            "schema_version": "word-instrumentation-upgrade-evidence:v1",
            "entry_id": spec.entry_id,
            "template_id": spec.template_id,
            "document_type": WORD_DOCUMENT_TYPE,
            "source_representation_id": str(source_representation_id),
            "content_version_id": str(content_version_id),
            "from_definition_bundle_id": (
                str(from_definition_bundle_id) if from_definition_bundle_id else None
            ),
            "from_definition_bundle_sha256": from_definition_bundle_sha256,
            "template_definition_sha256": template_definition.sha256,
            "instrumentation_definition_sha256": instrumentation_definition.sha256,
            "rollback_source_sha256": _sha256_bytes(source_bytes),
            "instrumented_sha256": instrumented.instrumented_sha256,
            "visible_equivalence": dict(equivalence),
            "tag_readback": dict(readback),
            "probe_gate": self._gate.probe_gate_identity(),
        }
        report_bytes = canonical_json_bytes(report)

        staged = self._artifacts.stage_bytes(
            project_id=self._project_id,
            wp_id=wp_id,
            payload=instrumented.instrumented_bytes,
            document_type=WORD_DOCUMENT_TYPE,
            filename="instrumented.tmp",
            expected_sha256=instrumented.instrumented_sha256,
        )
        candidate_artifact = self._artifacts.stage_upgrade_candidate(
            staged=staged, entry_id=spec.entry_id, equivalence_report=report_bytes
        )
        artifact_row = await self._repo.register_artifact(
            project_id=self._project_id,
            wp_id=wp_id,
            kind="upgrade_candidate",
            state="candidate",
            relative_path=candidate_artifact.relative_path,
            sha256=candidate_artifact.sha256,
            size_bytes=candidate_artifact.size_bytes,
            document_type=candidate_artifact.document_type,
        )
        candidate = await self._repo.create_upgrade_candidate(
            project_id=self._project_id,
            wp_id=wp_id,
            entry_id=spec.entry_id,
            content_version_id=content_version_id,
            source_representation_id=source_representation_id,
            staged_artifact_id=artifact_row.id,
            staged_artifact_sha256=candidate_artifact.sha256,
            template_definition_id=template_definition.definition_id,
            instrumentation_definition_id=instrumentation_definition.definition_id,
            # 🔴 两个 target 显式留空：本任务不得伪造 per-entry contract / bundle。
            #    `assert_candidate_finalizable`（Task 12）会因此拒绝 finalize，直到
            #    Task 60（F2）与 Tasks 62–64 把 approved child 补齐。
            target_contract_definition_id=None,
            target_definition_bundle_id=None,
            state=CandidateState.awaiting_contract,
        )
        candidate.visible_equivalence_report_sha256 = _sha256_bytes(report_bytes)
        candidate.rollback_source_sha256 = _sha256_bytes(source_bytes)
        await self._repo.session.flush()

        after = await self._snapshot(wp_id=wp_id, entry_id=spec.entry_id)
        outcome = UpgradeCandidateOutcome(
            candidate_id=candidate.id,
            wp_id=wp_id,
            entry_id=spec.entry_id,
            content_version_id=content_version_id,
            source_representation_id=source_representation_id,
            from_definition_bundle_id=from_definition_bundle_id,
            from_definition_bundle_sha256=from_definition_bundle_sha256,
            template_definition_id=template_definition.definition_id,
            template_definition_sha256=template_definition.sha256,
            instrumentation_definition_id=instrumentation_definition.definition_id,
            instrumentation_definition_sha256=instrumentation_definition.sha256,
            target_contract_definition_id=None,
            target_definition_bundle_id=None,
            state=CandidateState(candidate.state),
            staged_artifact_id=artifact_row.id,
            staged_artifact_sha256=candidate_artifact.sha256,
            staged_relative_path=candidate_artifact.relative_path,
            rollback_source_sha256=_sha256_bytes(source_bytes),
            visible_equivalence_report_sha256=_sha256_bytes(report_bytes),
            identity_inventory_sha256=canonical_digest(dict(readback)),
            structure_hash=word_structure_hash(instrumented.instrumented_bytes),
            content_revision_before=before["content_revision"],
            content_revision_after=after["content_revision"],
            entry_pointer_before=before["pointer_representation_id"],
            entry_pointer_after=after["pointer_representation_id"],
            representation_count_before=before["representation_count"],
            representation_count_after=after["representation_count"],
            probe_gate=self._gate.probe_gate_identity(),
            actor_id=actor_id,
        )
        assert_candidate_is_non_current(outcome)
        return outcome

    # ─────────────────────────────────────────────────────────────

    async def _snapshot(self, *, wp_id: uuid.UUID, entry_id: str) -> dict[str, Any]:
        """revision / pointer / representation 计数三项实测快照。

        用**裸 SQL** 而不是 ORM 关系遍历：本快照要证明「我没动这三样」，若经由同一批
        ORM 对象读取，session identity map 里的脏对象会让 before/after 读到同一份
        内存态 ⇒ 恒相等 ⇒ 判据空转。
        """
        import sqlalchemy as sa

        revision = (
            await self._session.execute(
                sa.text("SELECT content_revision FROM working_paper WHERE id = :wp"),
                {"wp": str(wp_id)},
            )
        ).scalar_one()
        pointer = (
            await self._session.execute(
                sa.text(
                    "SELECT current_representation_id FROM working_paper_sync_entry_state "
                    "WHERE wp_id = :wp AND entry_id = :e"
                ),
                {"wp": str(wp_id), "e": entry_id},
            )
        ).first()
        count = (
            await self._session.execute(
                sa.text(
                    "SELECT count(*) FROM working_paper_content_representation "
                    "WHERE wp_id = :wp AND entry_id = :e"
                ),
                {"wp": str(wp_id), "e": entry_id},
            )
        ).scalar_one()
        return {
            "content_revision": int(revision),
            "pointer_representation_id": pointer[0] if pointer else None,
            "representation_count": int(count),
        }
