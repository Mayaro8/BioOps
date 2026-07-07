from bioops.agents.bucket_agent import BucketAgent


def make_inventory(tmp_path):
    inventory = tmp_path / "bucket_inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "raw/a.bam,100,2026-07-01",
            "raw/b.bam,200,2026-07-01",
            "raw/b.bam.bai,10,2026-07-01",
            "results/a.vcf,50,2026-07-01",
        ]),
        encoding="utf-8",
    )
    return inventory


def test_bucket_agent_answers_bam_size(tmp_path, monkeypatch):
    inventory = make_inventory(tmp_path)
    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run("what is the total size of .bam files?")

    assert "Bucket File Type Summary: .bam" in response
    assert "Objects: 2" in response
    assert "300 B" in response
    assert "Inventory date: 2026-07-01" in response


def test_bucket_agent_answers_prefix_size(tmp_path, monkeypatch):
    inventory = make_inventory(tmp_path)
    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run("size of folder raw/")

    assert "Bucket Prefix Summary: raw/" in response
    assert "Objects: 3" in response
    assert "310 B" in response
    assert "Inventory date: 2026-07-01" in response


def test_bucket_agent_answers_structure(tmp_path, monkeypatch):
    inventory = make_inventory(tmp_path)
    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run("explain bucket structure")

    assert "Bucket Structure" in response
    assert "raw/" in response
    assert "Inventory date: 2026-07-01" in response

def test_bucket_agent_answers_bam_size_inside_prefix_safely(tmp_path, monkeypatch):
    inventory = tmp_path / "bucket_inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "raw/batch-1/a.bam,100,2026-07-01",
            "raw/batch-1/nested/b.bam,200,2026-07-01",
            "raw/batch-1/c.vcf,300,2026-07-01",
            "raw/batch-10/wrong.bam,999,2026-07-01",
            "raw/batch-1-old/wrong.bam,999,2026-07-01",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run("what is the size of all bam files in raw/batch-1?")

    assert "Bucket Filtered Summary" in response
    assert "Path scope: raw/batch-1/" in response
    assert "File type: .bam" in response
    assert "Objects: 2" in response
    assert "300 B" in response
    assert "Inventory date: 2026-07-01" in response

def test_bucket_agent_answers_precise_suffix_inside_prefix(tmp_path, monkeypatch):
    inventory = tmp_path / "bucket_inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "results/batch-1/sample-a.imputation.vcf.gz,100,2026-07-01",
            "results/batch-1/sample-b.imputation.vcf.gz,200,2026-07-01",
            "results/batch-1/sample-a.beagle.imputation.vcf.gz,1000,2026-07-01",
            "results/batch-1/sample-b.beagle.imputation.vcf.gz,2000,2026-07-01",
            "results/batch-10/sample-c.imputation.vcf.gz,9999,2026-07-01",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run(
        "what is the size of imputation.vcf.gz files under results/batch-1?"
    )

    assert "Bucket Filtered Summary" in response
    assert "Path scope: results/batch-1/" in response
    assert "Filename suffix: imputation.vcf.gz" in response
    assert "Objects: 2" in response
    assert "300 B" in response

    response = agent.run(
        "what is the size of beagle.imputation.vcf.gz files under results/batch-1?"
    )

    assert "Filename suffix: beagle.imputation.vcf.gz" in response
    assert "Objects: 2" in response
    assert "2.93 KiB" in response or "3000 B" in response



def test_bucket_agent_answers_storage_class_question(tmp_path, monkeypatch):
    inventory = tmp_path / "bucket_inventory.csv"
    inventory.write_text(
        "\n".join([
            "genotek-testing,raw/batch-1/a.bam,100,COLD",
            "genotek-testing,raw/batch-1/b.bam,200,STANDARD",
            "genotek-testing,raw/batch-1/c.vcf,300,COLD",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run("which storage class are bam files in raw/batch-1?")

    assert "Bucket Storage Class Summary" in response
    assert "Path scope: raw/batch-1/" in response
    assert "File type: .bam" in response
    assert "Objects: 2" in response
    assert "- STANDARD: 1 objects, 200 B" in response
    assert "- COLD: 1 objects, 100 B" in response
    assert "Inventory date: 2026-07-01" in response


def test_bucket_agent_lists_matching_files(tmp_path, monkeypatch):
    inventory = tmp_path / "bucket_inventory.csv"
    inventory.write_text(
        "\n".join([
            "genotek-testing,results/batch-1/sample-a.imputation.vcf.gz,100,COLD",
            "genotek-testing,results/batch-1/sample-b.imputation.vcf.gz,200,STANDARD",
            "genotek-testing,results/batch-1/sample-a.beagle.imputation.vcf.gz,1000,COLD",
            "genotek-testing,results/batch-10/sample-c.imputation.vcf.gz,9999,COLD",
        ]),
        encoding="utf-8",
    )

    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_INVENTORY_DATE", "2026-07-01")

    agent = BucketAgent(config_path=tmp_path / "missing.yaml")

    response = agent.run(
        "list files imputation.vcf.gz under results/batch-1/"
    )

    assert "Bucket File List" in response
    assert "Path scope: results/batch-1/" in response
    assert "Filename suffix: imputation.vcf.gz" in response
    assert "Matched objects: 2" in response
    assert "results/batch-1/sample-a.imputation.vcf.gz" in response
    assert "results/batch-1/sample-b.imputation.vcf.gz" in response
    assert "sample-a.beagle.imputation.vcf.gz" not in response
    assert "results/batch-10/sample-c.imputation.vcf.gz" not in response
