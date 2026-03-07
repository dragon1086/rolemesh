# Migration Note (ai-comms -> rolemesh)

## Migrated
- init_db / registry_client
- amp_caller / symphony_fusion
- queue_worker / message_worker
- autoevo_worker / round_reporter
- runtime scripts

## Pending cleanup
- module import normalization (relative imports)
- dedicated tests in rolemesh repo
- CLI entrypoints (`rolemesh init`, `rolemesh worker ...`)

## Operational policy
From now on, new implementation work should be done in `rolemesh` first.
`ai-comms` is treated as legacy/staging.
