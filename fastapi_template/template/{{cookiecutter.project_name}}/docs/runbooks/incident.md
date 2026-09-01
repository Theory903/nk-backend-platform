# NK incident runbook

## First five minutes

1. Check `/api/health`, `/api/ready`, and `/api/build-info`.
2. Check `nk_http_requests_total` for 5xx rate and latency saturation.
3. Freeze rollout; record the image tag and current `scale.stage`.
4. Inspect queue depth and `nk_dlq_messages` before replaying anything.
5. Roll back the Helm release if the failure began with the latest image.

## DLQ replay

Replay only after the downstream cause is fixed:

```bash
uv run nk jobs replay
```

Replay selected IDs when investigating a poison message:

```bash
uv run nk jobs replay dlq_...
```

## Database recovery

Pause workers, preserve logs and the current build metadata, restore to a
verified point-in-time recovery target, then run `uv run nk migrate` and smoke
test tenant isolation before resuming traffic.
