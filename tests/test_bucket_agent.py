from pathlib import Path

from bioops.agents.bucket_agent import BucketAgent


def _inventory(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                "genotek-testing,data/c2023/c2023.imputed.vcf.gz,100,TICE",
                "genotek-testing,data/dg5163/dg5163_chip_hg38.vcf,200,STANDARD",
                "genotek-testing,results/batch-1/a.imputation.vcf.gz,300,COLD",
                "genotek-testing,results/batch-1/a.beagle.imputation.vcf.gz,400,COLD",
            ]
        ),
        encoding="utf-8",
    )


def test_lists_actual_matching_files(tmp_path: Path, monkeypatch) -> None:
    inventory = tmp_path / "inventory_2026-07-07.csv"
    _inventory(inventory)
    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))
    monkeypatch.setenv("BUCKET_NAME", "genotek-testing")

    response = BucketAgent(config_path=tmp_path / "missing.yaml").run(
        "list files imputation.vcf.gz under results/batch-1/"
    )

    assert "results/batch-1/a.imputation.vcf.gz" in response
    assert "a.beagle.imputation.vcf.gz" not in response
    assert "Inventory date: 2026-07-07" in response
    assert "Inventory file: inventory_2026-07-07.csv" in response


def test_answers_storage_class_question(tmp_path: Path, monkeypatch) -> None:
    inventory = tmp_path / "inventory_2026-07-07.csv"
    _inventory(inventory)
    monkeypatch.setenv("BUCKET_INVENTORY_PATH", str(inventory))

    response = BucketAgent(config_path=tmp_path / "missing.yaml").run(
        "which storage class are files under data/c2023/"
    )

    assert "Bucket Storage Class Summary" in response
    assert "TICE: 1 objects, 100 B" in response
