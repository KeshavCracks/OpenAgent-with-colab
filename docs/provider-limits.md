# Provider Limits

The harness treats free-tier GPU backends as **short-lived, quota-limited,
non-public** compute — never as a place to run a persistent public service.
`ProviderDriver.enforce_session_limit()` raises `QuotaExceededError` once a
session exceeds its configured `max_session_hours`, and every driver's
bootstrap binds `llama-server` to loopback only.

## Colab

Implemented first (per project priority: Colab before Kaggle, everywhere).

| Resource | Free-tier figure baked into `config/default.yaml` |
|---|---|
| GPU | 1× T4 |
| VRAM | ~15 GB |
| RAM | ~12 GB |
| CPU | a few cores (2 configured) |
| Disk | ~60-78 GB (70 GB configured) |
| Session length | ~12 hours (`max_session_hours: 12`) |
| Weekly GPU quota | not fixed by Google — `weekly_gpu_quota_hours: null`; usage is dynamically throttled, so still checkpoint often |
| Public inbound | **never** (`public_inbound_address: false`) |

Integration model: there is **no stable, independent network path** into a
Colab runtime. The harness talks to it only through `colab-mcp`
(`googlecolab/colab-mcp`), which bridges to a notebook **already open in
your browser** — see [mcp.md](mcp.md#colab-mcp). This is why
`ColabDriver.start()` requires an injected `exec_client` implementing that
bridge protocol; there's deliberately no code path that tries to reach a
Colab runtime over the open internet.

## Kaggle

Implemented second.

| Resource | Free-tier figure baked into `config/default.yaml` |
|---|---|
| GPU | 2× T4 |
| VRAM | ~30 GB total |
| RAM | ~29 GB |
| CPU | more cores than Colab's free tier (4 configured) |
| Disk / workspace | ~20 GB |
| Session length | ~12 hours (`max_session_hours: 12`) |
| Weekly GPU quota | ~30 hours/week (`weekly_gpu_quota_hours: 30`) — hard-enforced by Kaggle, budget sessions accordingly |
| Public inbound | **never** (`public_inbound_address: false`) |

Integration model: Kaggle kernels have **no live two-way code-exec channel**
and **no stable public inbound** path either. `kaggle-mcp`
(`Galaxy-Dawn/kaggle-mcp`) is a batch REST wrapper — push a kernel, poll its
status, read its output once complete. `KaggleDriver` is built around this
push→poll pattern, not interactive exec parity with Colab — see
[mcp.md](mcp.md#kaggle-mcp). Prefer **same-container execution**: run
`llama-server` and the actual work inside the same kernel process rather
than trying to proxy between separate kernels.

## Forbidden patterns (hard rules, not just guidance)

These are explicitly out of scope and never implemented anywhere in this
harness, regardless of provider:

- **Quota evasion** — no code path tries to detect/evade Colab's or
  Kaggle's usage throttling or disconnect-on-idle behavior.
- **Unattended public serving** — `llama-server` is always bound to
  loopback; nothing in `openagent.runtime` or the provider drivers opens a
  public port.
- **Proxy abuse** — the harness does not relay unrelated third-party
  traffic through a free GPU session.
- **Access-control bypass** — provider credentials are read from
  `env:`/`keyring:` references only (see [security.md](security.md)); the
  harness never attempts to work around a provider's auth or rate limits.

## Checking current session state

```bash
openagent status <session_id>     # local session metadata
```

Provider-level health (GPU/VRAM/RAM/disk/checksum/server/tool-call/latency)
is exercised through `openagent.runtime.health.run_preflight` against a
specific `ProviderDriver` + `ModelEntry` + `GpuShape` — see
`tests/test_runtime_health.py` for exact usage, and
[model-selection.md](model-selection.md) for the ramp-up procedure that
calls it.
