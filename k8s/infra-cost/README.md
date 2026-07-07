# Infra Cost Monitor CronJob — Epic E1

This directory contains the Kubernetes CronJob for the BioOps Epic E1 infrastructure cost monitor.

## Current behavior

The monitor reports a VM when:

1. The VM is running.
2. Its runtime exceeds the configured threshold.
3. Its projected monthly cost exceeds the configured threshold, or it has a GPU.

Thresholds are configured in:

    configs/agents.yaml

## Safety

The CronJob is disabled by default:

    spec:
      suspend: true

Keep it suspended until the Infra Agent image has been built, pushed, and tested.

## Image

Replace the placeholder image tag in:

    k8s/infra-cost/cronjob.disabled.yaml

with the actual Yandex Container Registry image tag built from the `infra-agent` branch.

## Apply while suspended

    kubectl apply -f k8s/infra-cost/cronjob.disabled.yaml
    kubectl get cronjob bioops-infra-cost-monitor -n bioops-dev

The CronJob should show `SUSPEND=True`.

## Manual test

    JOB_NAME="bioops-infra-cost-manual-$(date +%s)"

    kubectl create job \
      --from=cronjob/bioops-infra-cost-monitor \
      "$JOB_NAME" \
      -n bioops-dev

    kubectl wait \
      --for=condition=complete \
      "job/$JOB_NAME" \
      -n bioops-dev \
      --timeout=180s

    kubectl logs -n bioops-dev "job/$JOB_NAME"

## Enable scheduling

    kubectl patch cronjob bioops-infra-cost-monitor \
      -n bioops-dev \
      --type=merge \
      -p '{"spec":{"suspend":false}}'

## Disable scheduling

    kubectl patch cronjob bioops-infra-cost-monitor \
      -n bioops-dev \
      --type=merge \
      -p '{"spec":{"suspend":true}}'
