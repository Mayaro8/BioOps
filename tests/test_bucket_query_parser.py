from bioops.tools.bucket_query_parser import BucketQueryParser


def test_parses_file_listing_with_prefix_and_specific_suffix() -> None:
    parser = BucketQueryParser()
    query = parser.parse("list files imputation.vcf.gz under results/batch-1/")

    assert query.aggregate == "list_files"
    assert query.prefix == "results/batch-1"
    assert query.name_suffix == "imputation.vcf.gz"
    assert query.extension is None


def test_parses_storage_class_and_compound_extension() -> None:
    parser = BucketQueryParser()
    query = parser.parse("which storage class are vcf.gz files in data/c2023/")

    assert query.aggregate == "storage_class"
    assert query.prefix == "data/c2023"
    assert query.extension == ".vcf.gz"
