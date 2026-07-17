"""Security scaffolding for procedure-delegation-visibility-isolation.

This package holds the *baseline* inventory + evidence scaffolding produced by
Task 1 of the ``procedure-delegation-visibility-isolation`` spec. It is
intentionally inventory-only: it records the current state of every wp-bound
entry (all gaps marked ``unmigrated``) and provides the append-only evidence
manifest tooling. The unified gate, action matrix, migrations and endpoint
changes are implemented by later tasks — nothing here enforces authorization.
"""
