# BioOps CronJobs and Notifications

This document reflects the current code, including the uncommitted changes.
All schedules use the `Europe/Moscow` time zone.

## Deployed CronJobs

| CronJob | Schedule | Suspended | Result |
|---|---:|---:|---|
| `bioops-cluster-health-monitor` | Hourly | Yes | Browser health report |
| `bioops-cluster-error-monitor` | Every 30 minutes | Yes | Browser alert only when errors exist |
| `bioops-init-retry-watchdog` | Every minute | No | Deletes stuck initialization pods and writes a JSON Job log |
| `batch-status-sync` | Every 5 minutes | Yes | Synchronizes Argo data to SQLite, CSV, and JSON |
| `bioops-infra-cost-monitor` | Every 15 minutes | Yes | Browser VM cost notification |
| `bioops-database-health-monitor` | Every 15 minutes | Yes | Browser database notification |
| `bioops-queue-health-monitor` | Every 10 minutes | Yes | Browser queue notification |
| `bioops-function-health-monitor` | Every 10 minutes | Yes | Browser Cloud Functions notification |

Only the initialization retry watchdog currently runs automatically.

## Browser Notification Reports

### 1. Hourly Workflow Health

```text
Workflow Health Report

Overall status: Healthy
Batches represented: 2
Workflows observed: 700
Samples represented: 700
Total workflow pods: 2,100

Batch: batch-140325
Workflow states:
- Running: 630 workflows (90.0%)
- Succeeded: 70 workflows (10.0%)

Pod phases:
- Running: 1,260 pods (60.0%)
- Succeeded: 840 pods (40.0%)

Current steps:
- align-reference: 420 pods (33.3%)
- sort-bam: 560 pods (44.4%)
- call-variants: 280 pods (22.2%)

Recent workflow pod issues:
- None.

Cost:
- Estimated cost: 0.00 RUB

ETA:
- align-reference: average ~45 min remaining
```

### 2. Workflow Pod Error Alert

This notification is sent only when recent errors are found.

```text
Analyzed Workflow Pod Errors

Findings: 1

1. Category: Out of memory
   Severity: critical
   Likely cause: Container exceeded its memory limit
   Evidence: OOMKilled
   Recommended action: Increase memory or inspect the sample workload
```

### 3. VM Cost Monitor

```text
Infra & Cost Report

Compute Cloud VMs:
- Checked: 6
- Alerts: 1

WARNING: expensive-cpu-long
- VM ID: vm-expensive-cpu-long
- Runtime: 5.00 hours
- Projected monthly cost: 70,000 RUB
- GPUs: 0
- Action: confirm that the VM is required; stop it if it is idle.
```

### 4. Database Health

```text
E2 Database Health Report
- Hosts checked: 3
- Alerts: 3

Findings:
- WARNING mysql:pipeline-mysql: CPU 91.0% exceeds 85.0%
- WARNING clickhouse:pipeline-clickhouse: RAM 93.0% exceeds 90.0%
- WARNING clickhouse:pipeline-clickhouse: mutation mutation_42 is 55 minutes old

Action: inspect the affected database host or mutation.
```

### 5. Queue Health

```text
E3 Queue Health Report
- Queues checked: 2
- Alerts: 3

Findings:
- WARNING pipeline-submit: oldest message is 1800 seconds old
- WARNING pipeline-submit: drain rate is 0.50 messages/minute
- WARNING pipeline-submit: estimated drain time is 240.0 minutes

Action: inspect consumers and processing throughput.
```

### 6. Cloud Functions Health

```text
E4 Cloud Functions Health Report
- Functions checked: 2
- Alerts: 3

Findings:
- CRITICAL batch-dispatch: error rate 7.5% exceeds 5.0%
- WARNING batch-dispatch: load 400 is more than 3.0x the baseline
- CRITICAL batch-dispatch: 2 critical log errors

Action: inspect function logs, load, and recent deployments.
```

## Non-Notification CronJob Results

### Batch Status Synchronization

`batch-status-sync` reads Argo Workflows and updates:

- `/data/bioops_batch_status.sqlite3`
- `/data/batch_status.csv`
- `/data/batch_status.json`

It does not create a browser notification.

### Initialization Retry Watchdog

The watchdog writes a result to the Kubernetes Job log:

```json
{
  "status": "completed",
  "threshold_minutes": 30,
  "retried_count": 2,
  "pods": [
    {
      "name": "workflow-sample-1",
      "workflow_name": "batch-140325",
      "age_minutes": 35.2
    }
  ]
}
```

The watchdog currently does not persist retry counts or enforce the requested
five-retry limit. It may delete the same repeatedly stuck pod more than five
times.

## Reactive Notification Reports

These reports are not Kubernetes CronJobs:

### D3 Progress Report

Reports batch, sample, or workflow progress. It includes workflow phase and
current-step counts and percentages, runtime statistics, and failed samples.

### D4 Failure Report

Reports the workflow phase and runtime, up to five failed/error nodes, pod log
tails, and a likely diagnosis.

### D5 Retry Report

Reports whether a workflow is retryable, its retry count, the decision reason,
and whether a replacement workflow was created. D5 currently allows a maximum
of two retries through `configs/agents.yaml`.

The D3, D4, and D5 command-line entrypoints can send reports to Bitrix, but no
Kubernetes CronJob invokes them automatically.

## Standalone Manifests

The repository also contains standalone manifests under `k8s/` that are not
part of the main `deploy/k8s` Kustomize deployment:

| CronJob | Schedule | Suspended | Purpose |
|---|---:|---:|---|
| `bioops-bucket-inventory-exporter` | Daily at 03:00 | Yes | Exports bucket inventory CSV to a PVC |
| Legacy `batch-status-sync` | Every 5 minutes | Yes | Older duplicate of batch synchronization |
| Legacy `bioops-infra-cost-monitor` | Every 15 minutes | Yes | Older console-mode infrastructure monitor |
