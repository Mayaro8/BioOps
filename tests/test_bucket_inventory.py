from bioops.tools.bucket_inventory import BucketInventoryTool


def test_bucket_inventory_extension_stats(tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "raw/a.bam,100,2026-07-01",
            "raw/b.bam,200,2026-07-01",
            "raw/b.bam.bai,10,2026-07-01",
            "results/a.vcf.gz,50,2026-07-01",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)

    stats = tool.extension_stats(".bam")

    assert stats["objects"] == 2
    assert stats["bytes"] == 300
    assert tool.inventory_date() == "2026-07-01"


def test_bucket_inventory_prefix_stats(tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "raw/a.bam,100,2026-07-01",
            "raw/b.bam,200,2026-07-01",
            "results/a.vcf,50,2026-07-01",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)

    stats = tool.prefix_stats("raw/")

    assert stats["prefix"] == "raw/"
    assert stats["objects"] == 2
    assert stats["bytes"] == 300


def test_bucket_inventory_top_prefixes(tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "\n".join([
            "key,size,inventory_date",
            "raw/a.bam,100,2026-07-01",
            "results/a.vcf,500,2026-07-01",
            "reports/a.json,5,2026-07-01",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)

    rows = tool.top_prefixes()

    assert rows[0]["prefix"] == "results/"
    assert rows[0]["bytes"] == 500

def test_filtered_stats_combines_prefix_and_extension_safely(tmp_path):
    inventory = tmp_path / "inventory.csv"
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

    tool = BucketInventoryTool(inventory)

    stats = tool.filtered_stats(prefix="raw/batch-1", extension=".bam")

    assert stats["prefix"] == "raw/batch-1/"
    assert stats["extension"] == ".bam"
    assert stats["objects"] == 2
    assert stats["bytes"] == 300


def test_plain_inventory_file_is_supported(tmp_path):
    inventory = tmp_path / "inventory"
    inventory.write_text(
        "\n".join([
            "100 raw/batch-1/a.bam",
            "200 raw/batch-1/nested/b.bam",
            "999 raw/batch-10/wrong.bam",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)

    stats = tool.filtered_stats(prefix="raw/batch-1", extension="bam")

    assert stats["objects"] == 2
    assert stats["bytes"] == 300

def test_name_suffix_distinguishes_overlapping_products(tmp_path):
    inventory = tmp_path / "inventory.csv"
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

    tool = BucketInventoryTool(inventory)

    short_stats = tool.filtered_stats(
        prefix="results/batch-1",
        name_suffix="imputation.vcf.gz",
        known_name_suffixes=[
            "imputation.vcf.gz",
            "beagle.imputation.vcf.gz",
        ],
    )

    long_stats = tool.filtered_stats(
        prefix="results/batch-1",
        name_suffix="beagle.imputation.vcf.gz",
        known_name_suffixes=[
            "imputation.vcf.gz",
            "beagle.imputation.vcf.gz",
        ],
    )

    assert short_stats["objects"] == 2
    assert short_stats["bytes"] == 300
    assert long_stats["objects"] == 2
    assert long_stats["bytes"] == 3000



def test_headerless_real_inventory_csv_format_is_supported(tmp_path):
    inventory = tmp_path / "dfca9cd7.csv"
    inventory.write_text(
        "\n".join([
            "genotek-testing,data/c2023/c2023.imputed.vcf.gz,102021979,TICE",
            "genotek-testing,data/dg5163/dg5163_chip_hg38.vcf,64959311,STANDARD",
            "genotek-testing,results/batch-1/sample-a.imputation.vcf.gz,100,COLD",
            "genotek-testing,results/batch-1/sample-a.beagle.imputation.vcf.gz,1000,COLD",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)

    assert len(tool.objects) == 4
    assert tool.objects[0].key == "data/c2023/c2023.imputed.vcf.gz"
    assert tool.objects[0].size == 102021979
    assert tool.objects[0].storage_class == "TICE"

    stats = tool.filtered_stats(prefix="results/batch-1", name_suffix="imputation.vcf.gz")

    assert stats["objects"] == 1
    assert stats["bytes"] == 100


def test_latest_inventory_file_is_selected_from_directory(tmp_path):
    inventory_dir = tmp_path / "inventories"
    inventory_dir.mkdir()

    older = inventory_dir / "inventory_2026-07-01.csv"
    newer = inventory_dir / "inventory_2026-07-06.csv"

    older.write_text(
        "genotek-testing,old/file.bam,100,COLD\n",
        encoding="utf-8",
    )
    newer.write_text(
        "genotek-testing,new/file.bam,500,COLD\n",
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory_dir)

    stats = tool.extension_stats(".bam")

    assert tool.resolved_inventory_path == newer
    assert stats["objects"] == 1
    assert stats["bytes"] == 500
    assert tool.inventory_date() == "2026-07-06"


def test_filtered_stats_returns_storage_class_breakdown(tmp_path):
    inventory = tmp_path / "inventory.csv"
    inventory.write_text(
        "\n".join([
            "genotek-testing,raw/batch-1/a.bam,100,COLD",
            "genotek-testing,raw/batch-1/b.bam,200,STANDARD",
            "genotek-testing,raw/batch-1/c.vcf,300,COLD",
        ]),
        encoding="utf-8",
    )

    tool = BucketInventoryTool(inventory)
    stats = tool.filtered_stats(prefix="raw/batch-1", extension=".bam")

    assert stats["objects"] == 2
    assert stats["bytes"] == 300
    assert stats["storage_classes"] == [
        {"storage_class": "STANDARD", "objects": 1, "bytes": 200},
        {"storage_class": "COLD", "objects": 1, "bytes": 100},
    ]
