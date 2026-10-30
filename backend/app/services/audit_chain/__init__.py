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
from .lock_order import (
    AuditLockOrderViolation,
    record_chain_lock,
    record_non_chain_advisory_lock,
)
from .verify import VerifyResult, verify_chain, verify_entries

__all__ = [
    "GENESIS_HASH",
    "AuditPayloadError",
    "canonical_payload",
    "hash_v1",
    "hash_v2",
    "chain_key_of",
    "lock_chain",
    "AuditLockOrderViolation",
    "record_chain_lock",
    "record_non_chain_advisory_lock",
    "VerifyResult",
    "verify_chain",
    "verify_entries",
]
