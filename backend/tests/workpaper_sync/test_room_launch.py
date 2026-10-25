"""G4-3：OO 启动面 service 层（`room_launch`）的行为判据。

═══ 为什么这个文件必须跟着搬迁一起交付 ═══

G4-3 把三块判定从 `wp_sync_router.py` 搬进 service 层。**只搬不测**等于把未覆盖的代码
从一个位置挪到另一个位置 —— Task 28 的三条 AST 判据会转绿，而真实行为一条都没被锁住。
那正是「假绿第①源」的一个变体：形态判据满足了，行为判据是空的。

本文件锁的是搬迁后**必须仍然成立**的行为，而不是「函数存在」：

* contents token 冻结代际（`artifact_sha256` 进 claim）——否则 representation 被重新
  物化后旧 URL 会拉到新代字节，OO 拿到与 descriptor 不同代的文件而毫无察觉；
* 跨 room / 跨 wp 取字节必须拒；
* 缺 secret 两侧都 fail closed（签发侧与验签侧）；
* launch config 的**签名顺序**：签名后只准新增 `token`；
* 四种「拿不到字节」的原因对外合成同一类（存在性预言机的反向锁）。
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from jose import jwt

from app.services.workpaper_sync import room_launch as RL

SECRET = "g4-3-test-secret"


# ═══════════════════════════════════════════════════════════════════
# 1. contents token：签发与验签
# ═══════════════════════════════════════════════════════════════════


def _ids() -> tuple[uuid.UUID, uuid.UUID]:
    return uuid.uuid4(), uuid.uuid4()


def test_token_roundtrip_carries_all_three_bindings() -> None:
    room, rep = _ids()
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256="ab" * 32
    )
    claims = RL.verify_room_contents_token(token, secret=SECRET, expected_room_id=room)
    assert claims.room_id == room
    assert claims.representation_id == rep
    assert claims.artifact_sha256 == "ab" * 32


def test_token_freezes_the_generation_not_just_the_representation() -> None:
    """`artifact_sha256` 必须进 claim —— 只冻 representation_id 拦不住重新物化。"""
    room, rep = _ids()
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256="cd" * 32
    )
    payload = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert payload["artifact_sha256"] == "cd" * 32
    assert payload["pur"] == RL.CONTENTS_TOKEN_PURPOSE


def test_signing_without_a_secret_is_refused_not_unsigned() -> None:
    room, rep = _ids()
    with pytest.raises(RL.RoomLaunchSecretMissingError):
        RL.sign_room_contents_token(
            secret="", room_id=room, representation_id=rep, artifact_sha256="x"
        )


def test_verifying_without_a_secret_is_refused_not_allowed() -> None:
    """验签侧缺 secret **不得**放行 —— 那等于任何人拼个 token 都能取字节。"""
    room, _rep = _ids()
    with pytest.raises(RL.RoomLaunchSecretMissingError):
        RL.verify_room_contents_token("whatever", secret="", expected_room_id=room)


def test_token_signed_with_another_secret_is_rejected() -> None:
    room, rep = _ids()
    token = RL.sign_room_contents_token(
        secret="other-secret", room_id=room, representation_id=rep, artifact_sha256="y"
    )
    with pytest.raises(RL.RoomContentsTokenInvalidError):
        RL.verify_room_contents_token(token, secret=SECRET, expected_room_id=room)


def test_expired_token_is_rejected() -> None:
    room, rep = _ids()
    token = RL.sign_room_contents_token(
        secret=SECRET,
        room_id=room,
        representation_id=rep,
        artifact_sha256="z",
        ttl_seconds=-10,
    )
    with pytest.raises(RL.RoomContentsTokenInvalidError):
        RL.verify_room_contents_token(token, secret=SECRET, expected_room_id=room)


def test_token_for_another_room_is_a_scope_error_not_a_generic_one() -> None:
    """拿 A room 的 token 去要 B room 是横向越权尝试，值得单独可查的错误类。"""
    room_a, rep = _ids()
    room_b = uuid.uuid4()
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room_a, representation_id=rep, artifact_sha256="q"
    )
    with pytest.raises(RL.RoomContentsTokenScopeError):
        RL.verify_room_contents_token(token, secret=SECRET, expected_room_id=room_b)
    # 但它仍必须是 401 家族（对外响应体不做措辞区分）
    assert issubclass(RL.RoomContentsTokenScopeError, RL.RoomContentsTokenInvalidError)


def test_wrong_purpose_token_is_rejected() -> None:
    """复用别的用途的 token（如 callback route token）取字节必须拒。"""
    room = uuid.uuid4()
    forged = jwt.encode(
        {"pur": "callback_write", "room_id": str(room), "representation_id": str(uuid.uuid4()),
         "iat": int(time.time()), "exp": int(time.time()) + 600},
        SECRET,
        algorithm="HS256",
    )
    with pytest.raises(RL.RoomContentsTokenInvalidError):
        RL.verify_room_contents_token(forged, secret=SECRET, expected_room_id=room)


def test_empty_token_is_rejected() -> None:
    with pytest.raises(RL.RoomContentsTokenInvalidError):
        RL.verify_room_contents_token("", secret=SECRET, expected_room_id=uuid.uuid4())


# ═══════════════════════════════════════════════════════════════════
# 2. launch config：组装与签名顺序
# ═══════════════════════════════════════════════════════════════════

USER = RL.LaunchUserIdentity(id="u-1", name="张三")


def _config(**over: Any) -> dict[str, Any]:
    kwargs: dict[str, Any] = {
        "raw_config": {"document": {"title": "D2-2.xlsx", "key": "k1"}, "editorConfig": {}},
        "document_url": "https://host/api/workpaper-sync/rooms/r/contents?token=t",
        "callback_url": "https://host/api/workpaper-sync/rooms/r/onlyoffice-callback?room_id=r",
        "document_type": "xlsx",
        "user": USER,
        "secret": SECRET,
    }
    kwargs.update(over)
    return RL.build_signed_launch_config(**kwargs)


def test_config_keeps_the_coordinator_fields_and_only_adds_urls() -> None:
    """补键必须是**在既有结构上补**，不得把 coordinator 给的字段丢掉。"""
    config = _config()
    assert config["document"]["title"] == "D2-2.xlsx", "coordinator 的 document 字段被丢了"
    assert config["document"]["key"] == "k1"
    assert config["document"]["url"].endswith("token=t")
    assert config["editorConfig"]["callbackUrl"].startswith("https://host/")


def test_token_is_the_only_field_added_after_signing() -> None:
    """🔴 签名后只准新增 `token`。多改一个键 DocsAPI 就会丢 token（editor_error_-20）。"""
    config = _config()
    token = config.pop("token")
    decoded = jwt.decode(token, SECRET, algorithms=["HS256"])
    assert decoded == config, (
        "签名载荷与最终 config 不一致 —— 说明签名之后还动过字段；"
        f"差集={set(decoded) ^ set(config)}"
    )


def test_document_type_maps_xlsx_to_cell_and_others_to_word() -> None:
    assert _config(document_type="xlsx")["documentType"] == "cell"
    assert _config(document_type="docx")["documentType"] == "word"
    # coordinator 已给出 documentType 时以它为准（它才是 contract 的口径）
    assert _config(
        raw_config={"documentType": "slide", "document": {}, "editorConfig": {}},
        document_type="xlsx",
    )["documentType"] == "slide"


def test_autosave_stays_on_and_editor_forcesave_stays_off() -> None:
    """关掉 autosave ⇒ 本地改格不进 DocServer ⇒ CS forcesave 回 error=4「无未保存改动」。"""
    custom = _config()["editorConfig"]["customization"]
    assert custom["autosave"] is True
    assert custom["forcesave"] is False


def test_existing_customization_is_preserved() -> None:
    config = _config(
        raw_config={
            "document": {},
            "editorConfig": {"customization": {"chat": False, "autosave": False}},
        }
    )
    custom = config["editorConfig"]["customization"]
    assert custom["chat"] is False, "coordinator 的 customization 其他键被丢了"
    assert custom["autosave"] is True, "autosave 必须被强制打开"


def test_user_identity_is_injected_when_missing_and_respected_when_present() -> None:
    assert _config()["editorConfig"]["user"] == {"id": "u-1", "name": "张三"}
    kept = _config(
        raw_config={"document": {}, "editorConfig": {"user": {"id": "x", "name": "李四"}}}
    )
    assert kept["editorConfig"]["user"]["name"] == "李四", "已有协同身份不得被覆盖"


def test_lang_defaults_to_chinese_but_is_not_forced() -> None:
    assert _config()["editorConfig"]["lang"] == "zh-CN"
    kept = _config(raw_config={"document": {}, "editorConfig": {"lang": "en"}})
    assert kept["editorConfig"]["lang"] == "en"


def test_no_secret_yields_an_unsigned_config_without_a_token_key() -> None:
    """没配 secret 时不得塞一个空 token —— 空 token 会让 DocsAPI 报 `jwt must be provided`。"""
    config = _config(secret="")
    assert "token" not in config


def test_contents_url_matches_the_public_route_shape() -> None:
    room = uuid.uuid4()
    url = RL.build_contents_url(base_url="https://host/", room_id=room, token="tk")
    assert url == f"https://host/api/workpaper-sync/rooms/{room}/contents?token=tk"


# ═══════════════════════════════════════════════════════════════════
# 3. resolve_room_contents：解析链与「四种缺失同一类」
# ═══════════════════════════════════════════════════════════════════


@dataclass
class _Row:
    """替身行；只带被读到的字段。多给字段反而会掩盖「读了不该读的列」。"""

    id: uuid.UUID | None = None
    wp_id: uuid.UUID | None = None
    artifact_id: uuid.UUID | None = None
    artifact_sha256: str | None = None
    entry_id: str | None = None
    relative_path: str | None = None
    document_type: str | None = None


class _Result:
    def __init__(self, row: Any) -> None:
        self._row = row

    def scalar_one_or_none(self) -> Any:
        return self._row


class _FakeSession:
    """按调用顺序返回预置行。顺序本身就是判据：room → representation → artifact。"""

    def __init__(self, rows: list[Any]) -> None:
        self._rows = list(rows)
        self.calls = 0

    async def execute(self, _stmt: Any) -> _Result:
        self.calls += 1
        return _Result(self._rows.pop(0) if self._rows else None)


class _FakeArtifacts:
    def __init__(self, path: Path) -> None:
        self._path = path
        self.asked: list[str] = []

    def resolve_relative_path(self, relative: str) -> Path:
        self.asked.append(relative)
        return self._path


async def _resolve(rows: list[Any], *, path: Path, room: uuid.UUID, token: str) -> Any:
    return await RL.resolve_room_contents(
        _FakeSession(rows),  # type: ignore[arg-type]
        room_id=room,
        token=token,
        secret=SECRET,
        artifacts=_FakeArtifacts(path),
    )


@pytest.fixture()
def artifact_file(tmp_path: Path) -> Path:
    target = tmp_path / "D2-2.xlsx"
    target.write_bytes(b"PK\x03\x04payload")
    return target


def _happy_rows(*, wp: uuid.UUID, rep: uuid.UUID, sha: str) -> list[Any]:
    art_id = uuid.uuid4()
    return [
        _Row(id=uuid.uuid4(), wp_id=wp),  # room
        _Row(id=rep, wp_id=wp, artifact_id=art_id, artifact_sha256=sha, entry_id="xlsx/gt-d2"),
        _Row(id=art_id, relative_path="oo/D2-2.xlsx", document_type="xlsx"),
    ]


@pytest.mark.asyncio
async def test_happy_path_returns_path_media_and_filename(artifact_file: Path) -> None:
    room, rep, wp, sha = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "ee" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    resolved = await _resolve(
        _happy_rows(wp=wp, rep=rep, sha=sha), path=artifact_file, room=room, token=token
    )
    assert resolved.path == artifact_file
    assert resolved.media_type.endswith("spreadsheetml.sheet")
    # entry_id 里的 `/` 必须换掉 —— 否则 Content-Disposition 的文件名会带路径分隔符
    assert resolved.filename == "xlsx_gt-d2.xlsx"


@pytest.mark.asyncio
async def test_bad_token_fails_before_touching_the_database(artifact_file: Path) -> None:
    """验签在最前面：token 不对时**一次查询都不该发**。"""
    session = _FakeSession(_happy_rows(wp=uuid.uuid4(), rep=uuid.uuid4(), sha="a"))
    with pytest.raises(RL.RoomContentsTokenInvalidError):
        await RL.resolve_room_contents(
            session,  # type: ignore[arg-type]
            room_id=uuid.uuid4(),
            token="not-a-jwt",
            secret=SECRET,
            artifacts=_FakeArtifacts(artifact_file),
        )
    assert session.calls == 0, "验签失败却已经查过库 —— 可见面没有先收窄"


@pytest.mark.asyncio
async def test_representation_from_another_workpaper_is_refused(artifact_file: Path) -> None:
    """token 验签通过 ≠ 可以跨 wp 取字节。"""
    room, rep, sha = uuid.uuid4(), uuid.uuid4(), "ff" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    rows = _happy_rows(wp=uuid.uuid4(), rep=rep, sha=sha)
    rows[1].wp_id = uuid.uuid4()  # representation 属于另一个底稿
    with pytest.raises(RL.RoomContentsUnavailableError):
        await _resolve(rows, path=artifact_file, room=room, token=token)


@pytest.mark.asyncio
async def test_digest_drift_is_a_conflict_not_a_not_found(artifact_file: Path) -> None:
    """代际变了要能与「不存在」区分 —— 前者可重开编辑器解决，后者不能。"""
    room, rep, wp = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256="11" * 32
    )
    rows = _happy_rows(wp=wp, rep=rep, sha="22" * 32)
    with pytest.raises(RL.RoomContentsDigestMismatchError):
        await _resolve(rows, path=artifact_file, room=room, token=token)
    assert not issubclass(RL.RoomContentsDigestMismatchError, RL.RoomContentsUnavailableError)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("case", "mutate"),
    [
        ("room 行不存在", lambda rows: rows.__setitem__(0, None)),
        ("representation 行不存在", lambda rows: rows.__setitem__(1, None)),
        ("artifact 行不存在", lambda rows: rows.__setitem__(2, None)),
    ],
)
async def test_every_missing_row_collapses_into_one_unavailable_class(
    artifact_file: Path, case: str, mutate: Any
) -> None:
    """🔴 三种「行不存在」必须是**同一个**异常类。

    这是存在性预言机的反向锁：原实现在 router 里给了三段不同文案
    （`room not found` / `representation not found` / `artifact not found`），
    能构造 token 的人据文案差异就能反推「这个 representation 存在但 artifact 没了」。
    """
    room, rep, wp, sha = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "33" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    rows = _happy_rows(wp=wp, rep=rep, sha=sha)
    mutate(rows)
    with pytest.raises(RL.RoomContentsUnavailableError) as ei:
        await _resolve(rows, path=artifact_file, room=room, token=token)
    # 原因只进服务端（reason 属性），不进对外文案
    assert ei.value.reason, f"{case}: 缺服务端可查的 reason"
    assert ei.value.error_code == "sync_room_contents_unavailable", (
        f"{case}: error_code 因原因不同而分化 —— 对外仍会形成存在性预言机"
    )


@pytest.mark.asyncio
async def test_missing_file_on_disk_is_the_same_unavailable_class(tmp_path: Path) -> None:
    """磁盘文件没了也归入同一类（第四种缺失）。"""
    room, rep, wp, sha = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "44" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    with pytest.raises(RL.RoomContentsUnavailableError) as ei:
        await _resolve(
            _happy_rows(wp=wp, rep=rep, sha=sha),
            path=tmp_path / "gone.xlsx",
            room=room,
            token=token,
        )
    assert ei.value.error_code == "sync_room_contents_unavailable"


@pytest.mark.asyncio
async def test_path_resolution_goes_through_the_artifact_repository(artifact_file: Path) -> None:
    """路径**只**由 `CanonicalArtifactRepository` 解析，不在此自拼 backend/storage。"""
    room, rep, wp, sha = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "55" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    artifacts = _FakeArtifacts(artifact_file)
    await RL.resolve_room_contents(
        _FakeSession(_happy_rows(wp=wp, rep=rep, sha=sha)),  # type: ignore[arg-type]
        room_id=room,
        token=token,
        secret=SECRET,
        artifacts=artifacts,
    )
    assert artifacts.asked == ["oo/D2-2.xlsx"], "没有把相对路径交给 artifact 仓储"


@pytest.mark.asyncio
async def test_non_xlsx_falls_back_to_octet_stream(artifact_file: Path) -> None:
    room, rep, wp, sha = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), "66" * 32
    token = RL.sign_room_contents_token(
        secret=SECRET, room_id=room, representation_id=rep, artifact_sha256=sha
    )
    rows = _happy_rows(wp=wp, rep=rep, sha=sha)
    rows[2].document_type = "docx"
    resolved = await _resolve(rows, path=artifact_file, room=room, token=token)
    assert resolved.media_type == "application/octet-stream"
    assert resolved.filename.endswith(".docx")
