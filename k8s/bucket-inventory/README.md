# Bucket inventory exporter CronJob

This manifest is intentionally inactive through `spec.suspend: true`.

It runs daily at `03:00` and writes a dated CSV snapshot to:

```text
/data/inventories/bucket_inventory_YYYY-MM-DD.csv
```

The inventory is a CSV file. Extensions such as `.vcf.gz`, `.csv`, `.bam`,
and `.json` belong to object keys stored inside that CSV.

Before activation:

1. Replace `cr.yandex/replace-me/bioops:replace-me` with the current YC image.
2. Replace `bioops-s3-secret-placeholder` with the real Secret name.
3. Confirm the MinIO Service endpoint.
4. Confirm `ReadWriteMany` is supported by the selected storage class.
5. Mount the same PVC into the BioOps Deployment at `/data`.
6. Configure `BUCKET_INVENTORY_PATH=/data/inventories` for BioOps.
7. Change `suspend: true` to `suspend: false`.
