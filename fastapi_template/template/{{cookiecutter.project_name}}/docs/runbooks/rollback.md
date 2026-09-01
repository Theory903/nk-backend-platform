# Rollback and canary runbook

Deploy staging first and verify build metadata, readiness, error rate, queue
depth, and tenant-scoped smoke tests. For a failed canary:

```bash
helm history nk-backend -n nk
helm rollback nk-backend <REVISION> -n nk --wait
```

Keep the failed image tag and logs for post-incident analysis. Never delete
the migration job or replay the DLQ as a substitute for fixing the cause.
