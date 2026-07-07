from pathlib import Path

from bioops.tools.bucket_inventory import BucketInventoryTool


def test_headerless_company_inventory_and_storage_classes(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory_2026-07-06.csv"
    inventory.write_text(
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

    tool = BucketInventoryTool(inventory)
    stats = tool.filtered_stats(prefix="results/batch-1", name_suffix="imputation.vcf.gz", known_name_suffixes=["beagle.imputation.vcf.gz", "imputation.vcf.gz"])

    assert stats["objects"] == 1
    assert stats["bytes"] == 300
    assert stats["storage_classes"] == [
        {"storage_class": "COLD", "objects": 1, "bytes": 300}
    ]
    assert tool.inventory_date() == "2026-07-06"


def test_latest_csv_is_selected_from_directory(tmp_path: Path) -> None:
    directory = tmp_path / "inventories"
    directory.mkdir()
    (directory / "inventory_2026-07-01.csv").write_text(
        "genotek-testing,old/file.csv,10,COLD\n", encoding="utf-8"
    )
    newest = directory / "inventory_2026-07-07.csv"
    newest.write_text("genotek-testing,new/file.csv,20,STANDARD\n", encoding="utf-8")

    tool = BucketInventoryTool(directory)

    assert [obj.key for obj in tool.objects] == ["new/file.csv"]
    assert tool.resolved_inventory_path == newest
    assert tool.inventory_date() == "2026-07-07"


def test_prefix_boundary_does_not_match_batch_10(tmp_path: Path) -> None:
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "\n".join(
            [
                "genotek-testing,results/batch-1/a.csv,10,COLD",
                "genotek-testing,results/batch-10/b.csv,20,COLD",
            ]
        ),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory, inventory_date="2026-07-07")
    rows = tool.filter_objects(prefix="results/batch-1")

    assert [obj.key for obj in rows] == ["results/batch-1/a.csv"]
