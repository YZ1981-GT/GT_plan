"""审计哈希链加固包 (audit-log-chain-integrity)

Re-export key symbols for external consumers.
"""
from .canonical import (
    GENESIS_HASH,
    AuditPayloadError,
    canonical_payload,
    hash_v1,
    hash_v2,
)
from .head import chain_key_of, lock_chain
from .verify import VerifyResult, verify_chain, verify_entries

__all__ = [
    "GENESIS_HASH",
    "AuditPayloadError",
    "canonical_payload",
    "hash_v1",
    "hash_v2",
    "chain_key_of",
    "lock_chain",
    "VerifyResult",
    "verify_chain",
    "verify_entries",
]
