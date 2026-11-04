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
from .head import (
    AuditChainBypassed,
    AuditChainError,
    AuditChainForked,
    append_entry,
    append_entry_batch,
    chain_key_of,
    lock_chain,
    read_head,
)
from .forks import (
    append_fork_ack,
    append_fork_acks,
    blocked_chains,
    plan_chain_forks,
    scan_forks,
)
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
    "read_head",
    "append_entry",
    "append_entry_batch",
    "AuditChainError",
    "AuditChainForked",
    "AuditChainBypassed",
    "append_fork_ack",
    "append_fork_acks",
    "blocked_chains",
    "plan_chain_forks",
    "scan_forks",
    "AuditLockOrderViolation",
    "record_chain_lock",
    "record_non_chain_advisory_lock",
    "VerifyResult",
    "verify_chain",
    "verify_entries",
]
