from pathlib import Path
import hashlib
import json
import struct
import zlib

DIR = Path(
    r"D:/GT_plan/.kiro/specs/_archive/05-business-features/audit-evidence-attachment-preview-format-expansion/"
    r"evidence/attachment-preview-format-expansion/browser_fixtures"
)
DIR.mkdir(parents=True, exist_ok=True)


def crc32(data: bytes) -> int:
    return zlib.crc32(data) & 0xFFFFFFFF


def make_zip(name: str, data: bytes) -> bytes:
    name_b = name.encode("utf-8")
    crc = crc32(data)
    local = (
        b"PK\x03\x04"
        + struct.pack("<HHHHHIIIHH", 20, 0, 0, 0, 0, crc, len(data), len(data), len(name_b), 0)
        + name_b
        + data
    )
    central = (
        b"PK\x01\x02"
        + struct.pack(
            "<HHHHHHIIIHHHHHII",
            20,
            20,
            0,
            0,
            0,
            0,
            crc,
            len(data),
            len(data),
            len(name_b),
            0,
            0,
            0,
            0,
            0,
            0,
        )
        + name_b
    )
    end = b"PK\x05\x06" + struct.pack("<HHHHIIH", 0, 0, 1, 1, len(central), len(local), 0)
    return local + central + end


(DIR / "sample.zip").write_bytes(make_zip("你好.txt", b"hello"))
eml = "\r\n".join(
    [
        "From: a@example.com",
        "To: b@example.com",
        "Subject: e2e-preview",
        "MIME-Version: 1.0",
        "Content-Type: text/html; charset=utf-8",
        "",
        '<html><body><img src="https://evil.example/x.png"><p>hi</p></body></html>',
        "",
    ]
).encode()
(DIR / "sample.eml").write_bytes(eml)
(DIR / "sample.dxf").write_bytes(
    b"0\nSECTION\n2\nENTITIES\n0\nLINE\n8\n0\n10\n0\n20\n0\n11\n10\n21\n10\n0\nENDSEC\n0\nEOF\n"
)
(DIR / "sample.dwg").write_bytes(bytes([0x41, 0x43, 0x31, 0x30, 0x31, 0x00]))
dig = {
    k: hashlib.sha256((DIR / f"sample.{k}").read_bytes()).hexdigest()
    for k in ("zip", "eml", "dxf", "dwg")
}
(DIR / "digests.json").write_text(json.dumps(dig, indent=2), encoding="utf-8")
print(dig)
