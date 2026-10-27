---
name: database-migration-safety
description: Safely review and execute database schema or data migrations; detect destructive SQL, compatibility breaks, lock and downtime risks, validate preconditions, backfills, rollback limits, and production verification.
---

# Database Migration Safety

Use for schema changes, data migrations, ORM migrations, index changes, and database upgrades where data loss or downtime is possible.

## Procedure

1. **Map the change**: identify database engine/version, migration framework, touched tables/columns/indexes, table size if known, application versions that may run concurrently, and deployment order.
2. **Classify every operation**: additive, backfill, constraint-tightening, rename, type conversion, or destructive. Flag DROP/TRUNCATE, lossy casts, NOT NULL without a safe default/backfill, table rewrites, long locks, and unbounded updates/deletes.
3. **Check compatibility**: confirm old and new application versions can coexist during rollout. Prefer expand → deploy compatible code → backfill in bounded batches → enforce constraints → contract in a later release.
4. **Prove data assumptions**: write preflight queries for nulls, duplicates, invalid values, row counts, and foreign-key or uniqueness conflicts. Never assume production data matches fixtures.
5. **Plan operational safety**: estimate lock/scan risk, define statement/lock timeouts, batching and checkpoints, idempotency, observability, and a stop condition. Avoid a rollback plan that pretends deleted or transformed data can be reconstructed.
6. **Test**: run migration up and, where supported, down on a disposable database; test existing data shapes and interrupted/retried execution; verify constraints and application queries afterward.
7. **Deploy and verify**: state exact order, backup/restore requirements, metrics and SQL checks that prove success. Require explicit authorization before running a production or irreversible migration.

## Required output

Report severity-ranked findings with file/line and concrete impact; list preflight checks, safe rollout order, rollback limitations, test evidence, and post-deploy verification. If database engine, data volume, or backup state is unknown, state the uncertainty rather than inventing safety.
