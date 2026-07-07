from bioops.tools.bucket_query_parser import BucketQueryParser


def test_bucket_query_parser_extracts_prefix_and_extension():
    parser = BucketQueryParser(use_llm=False)

    query = parser.parse("what is the size of all bam files in raw/batch-1?")

    assert query.prefix == "raw/batch-1"
    assert query.extension == ".bam"
    assert query.name_suffix is None
    assert query.aggregate == "total_size"


def test_bucket_query_parser_extracts_s3_path():
    parser = BucketQueryParser(use_llm=False)

    query = parser.parse(
        "how large are vcf.gz files under s3://genotek-testing/results/batch-1/"
    )

    assert query.prefix == "s3://genotek-testing/results/batch-1/"
    assert query.extension == ".vcf.gz"
    assert query.name_suffix is None
    assert query.aggregate == "total_size"


def test_bucket_query_parser_extracts_precise_name_suffix():
    parser = BucketQueryParser(use_llm=False)

    query = parser.parse(
        "size of beagle.imputation.vcf.gz files under results/batch-1/"
    )

    assert query.prefix == "results/batch-1/"
    assert query.extension is None
    assert query.name_suffix == "beagle.imputation.vcf.gz"
    assert query.aggregate == "total_size"


def test_bucket_query_parser_extracts_shorter_precise_name_suffix():
    parser = BucketQueryParser(use_llm=False)

    query = parser.parse(
        "size of imputation.vcf.gz files under results/batch-1/"
    )

    assert query.prefix == "results/batch-1/"
    assert query.extension is None
    assert query.name_suffix == "imputation.vcf.gz"
