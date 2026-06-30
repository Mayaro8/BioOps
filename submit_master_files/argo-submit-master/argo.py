import subprocess
import json
import logging
from typing import List, Dict, Optional, Literal

from dto import DelayConfig

import typer

from mongo_client import get_data_from_mongo
from utils import generate_delays_for_samples

class ArgoClient:
    def __init__(
            self,
            contour: str,
            only_good: bool,
            delay_config: Dict,
            namespace: str = "default", 
            k8s_cluster_name: Optional[str] = None,
        ):
        self.namespace = namespace
        self.logger = logging.getLogger(self.__class__.__name__)
        self.contour = contour
        self.only_good = only_good
        self.delay_config = delay_config

        if k8s_cluster_name:
            self._get_k8s_credentials(k8s_cluster_name)

    def _validate_samples(
            self,
            delay_config: Optional[Dict | DelayConfig],
            sample_ids: List[Dict[str, str]],
            contour: str, 
            only_good: bool,
            batch_id: Optional[str] = None
        ):
        """
        This function creates DTO for DelayConfig and then generating delays
        for samples. Samples can be stored in Mongo or in config file.
        """
        delay_config_dto = DelayConfig(**delay_config)
        self.logger.info(delay_config_dto)
        if not sample_ids:
            sample_ids.extend(get_data_from_mongo(batch_id=batch_id, contour=contour, only_good=only_good))
        generate_delays_for_samples(sample_ids, delay_config_dto)

    def _execute_command(self, command: List[str], stop_on_error: bool = False) -> subprocess.CompletedProcess | None:
        """Executes a shell command and returns the result.
        
        Args:
            command: List of command strings and arguments
            
        Returns:
            CompletedProcess object with the execution results
            
        Raises:
            subprocess.CalledProcessError: If the return code is non-zero
        """
        self.logger.debug(f"Executing command: {' '.join(command)}")
        result = subprocess.run(
            command,
            check=stop_on_error,
            text=True,
            capture_output=True,
        )
        if not stop_on_error and result.returncode != 0:
            self.logger.error(
                "Command finished with a non-zero exit code (%s) but stop_on_error is False.\nstdout: %s\nstderr: %s",
                result.returncode,
                result.stdout,
                result.stderr,
            )
        else:
            self.logger.debug(f"Command executed successfully. Standard output: {result.stdout}")
        return result


    def _get_k8s_credentials(self, cluster_name: str) -> None:
        """Retrieves credentials for the specified Kubernetes cluster via Yandex Cloud CLI.
        

        Args:
            cluster_name: The name of the Kubernetes cluster
            
        Raises:
            subprocess.CalledProcessError: If the command execution ends with an error
        """
        command = [
            "yc",
            "managed-kubernetes",
            "cluster",
            "get-credentials",
            cluster_name,
            "--external",
            "--force"
        ]
        self._execute_command(command)

    def submit_cutadapt_s3_mounted_multiple_tubes_delay(
        self,
        input_mode: str,
        run_id: str,
        sample_ids: List[Dict[str, str]],
        output_dir: str,
        input_dir: str,
        cpus: str,
        ram: str,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:
        """
        Запуск workflowtemplate/submit-cutadapt-s3-mounted-multiple-tubes-delay        

        Параметры:
        - run_id: Идентификатор рана (обязательный)
        - batch_id: Идентификатор батча (обязательный)
        - sample_ids: Список словарей с sample_id и delay (необязательный)
        - output_dir: Путь к выходной директории в S3 (обязательный)
        - ... [остальные параметры]
        """

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/cutadapt-s3-mounted-multiple-tubes-delay",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"INPUT_MODE={input_mode}",
            "-p",
            f"RUN_ID={run_id}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "--labels",
            f"run_id={run_id}"
        ]

        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/cutadapt-s3-mounted-multiple-tubes-delay with parameters: run_id={run_id}"
        )
        self._execute_command(command, stop_on_error)


    def submit_cutadapt_surf_multi_tube(
        self,
        sample_ids: List[Dict[str, str]],
        batch_id: str,
        input_paths_list: str,
        runs_list: str,
        output_dir: str,
        mgi_csv_path: str,
        lane: str,
        tel_chat: str,
        tel_token: str,
        cpus: str,
        ram: str,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:


        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/cutadapt-surfseq-mutli-tube-test",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"INPUT_PATHS_LIST={input_paths_list}",
            "-p",
            f"RUNS_LIST={runs_list}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"MGI_CSV_PATH={mgi_csv_path}",
            "-p",
            f"LANE={lane}",
            "-p",
            f"TEL_CHAT={tel_chat}",
            "-p",
            f"TEL_TOKEN={tel_token}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")
        self.logger.info("Running workflowtemplate/cutadapt-surfseq-mutli-tube-test")
        self._execute_command(command, stop_on_error)


    def submit_cutadapt_mgi_multi_tube(
        self,
        sample_ids: List[Dict[str, str]],
        batch_id: str,
        input_paths_list: str,
        runs_list: str,
        output_dir: str,
        mgi_csv_path: str,
        lane: str,
        tel_chat: str,
        tel_token: str,
        cpus: str,
        ram: str,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:
        """
        Запуск workflowtemplate/cutadapt-mgi-multi-tube-prod       

        Параметры:
        - sample_ids: Список словарей с sample_id и delay
        - sample_ids_gbp: Строка с sample_ids для gbp
        - batch_id: Идентификатор батча
        - s3_input_path: Путь к входной директории в S3
        - output_dir: Путь к выходной директории в S3
        - mgi_csv_path: Путь к CSV файлу с MGI
        - gbp_s3_output_path: Путь к выходной директории в S3 для gbp
        - lane: Номер лэйна
        - tel_chat: Телеграм чат
        - tel_token: Телеграм токен
        - cpus: Количество CPU
        - ram: Количество RAM
        - wait: Флаг ожидания завершения workflow
        """
        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/cutadapt-mgi-multi-tube-prod",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"INPUT_PATHS_LIST={input_paths_list}",
            "-p",
            f"RUNS_LIST={runs_list}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"MGI_CSV_PATH={mgi_csv_path}",
            "-p",
            f"LANE={lane}",
            "-p",
            f"TEL_CHAT={tel_chat}",
            "-p",
            f"TEL_TOKEN={tel_token}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")
        self.logger.info("Running workflowtemplate/cutadapt-mgi-multi-tube-prod")
        self._execute_command(command, stop_on_error)

    def submit_fq2bam_s3_mounted_multiple_tubes_delay(
        self,
        run_id: str,
        batch_id_out: str,
        sample_ids: List[Dict[str, str]],
        cpus: str,
        ram: str,
        output_dir: str = "/mnt/pipeline-v3.0/sth",
        delay_config: Optional[DelayConfig | Dict] = None,
        input_dir: str = "/mnt/pipeline-v3.0/sth",
        assembly: str = "hg19",
        markdup: str = "no",
        bwa_version: str = "1",
        bam_suffix_markdup: str = "markdup",
        pair_end: str = "yes",
        split_per_chr: str = "no",
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:
        """
        Запуск workflowtemplate/fq2bam-s3-mounted-multiple-tubes-delay        

        Параметры:
        - run_id: Идентификатор рана (обязательный)
        - batch_id: Идентификатор батча (обязательный)
        - sample_ids: Список словарей с sample_id и delay (обязательный)
        - input_dir: Путь к входной директроии в S3 (обязательный)
        - output_dir: Путь к выходной директории в S3 (обязательный)
        - ... [остальные параметры]
        """

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id_out
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/fq2bam-s3-mounted-multiple-tubes-delay",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"RUN_ID={run_id}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"BATCH_ID_OUT={batch_id_out}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"MARKDUP={markdup}",
            "-p",
            f"bwa_version={bwa_version}",
            "-p",
            f"BAM_SUFFIX_MARKDUP={bam_suffix_markdup}",
            "-p",
            f"PAIR_END={pair_end}",
            "-p",
            f"Split_per_chr={split_per_chr}",
            "--labels",
            f"batch_id={batch_id_out}"            
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/fq2bam-s3-mounted-multiple-tubes-delay with parameters: batch_id={batch_id_out}"
        )
        self._execute_command(command, stop_on_error)

    def submit_fq2bam_mgi_multiple_tubes_delay(
        self,
        run_id: str,
        batch_id_out: str,
        sample_ids: List[Dict[str, str]],
        cpus: str,
        ram: str,
        output_dir: str = "/mnt/pipeline-v3.0/sth",
        delay_config: Optional[DelayConfig | Dict] = None,
        input_dir: str = "/mnt/pipeline-v3.0/sth",
        assembly: str = "hg19",
        markdup: str = "no",
        bwa_version: str = "1",
        bam_suffix_markdup: str = "markdup",
        pair_end: str = "yes",
        split_per_chr: str = "no",
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:
        """
        Запуск workflowtemplate/fq2bam-mgi-multiple-tubes-delay        

        Параметры:
        - run_id: Идентификатор рана (обязательный)
        - batch_id: Идентификатор батча (обязательный)
        - sample_ids: Список словарей с sample_id и delay (обязательный)
        - input_dir: Путь к входной директроии в S3 (обязательный)
        - output_dir: Путь к выходной директории в S3 (обязательный)
        - ... [остальные параметры]
        """

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id_out
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/fq2bam-s3-mounted-mgi-multiple-tubes-delay",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"RUN_ID={run_id}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"BATCH_ID_OUT={batch_id_out}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"MARKDUP={markdup}",
            "-p",
            f"bwa_version={bwa_version}",
            "-p",
            f"BAM_SUFFIX_MARKDUP={bam_suffix_markdup}",
            "-p",
            f"PAIR_END={pair_end}",
            "-p",
            f"Split_per_chr={split_per_chr}",
            "--labels",
            f"batch_id={batch_id_out}"            
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/fq2bam-s3-mounted-mgi-multiple-tubes-delay with parameters: batch_id={batch_id_out}"
        )
        self._execute_command(command, stop_on_error)

    def submit_qc_fq2bam_multiple_tubes_mounted(
        self,
        mode: Literal["all","qc_only","haplo_only"],
        sample_ids: List[Dict[str, str]],
        basename: str,
        batch_id: str,
        input_dir: str,
        include_unmapped: str,
        cpus: str,
        ram: str,
        build: str,
        delay_config: Optional[DelayConfig | Dict] = None,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:
        """
        Запуск workflowtemplate/qc_fq2bam_multiple_tubes_mounted        

        Параметры:
        - run_id: Идентификатор рана (обязательный)
        - batch_id: Идентификатор батча (обязательный)
        - sample_ids: Список словарей с sample_id и delay (обязательный)
        - input_dir: Путь к входной директроии в S3 (обязательный)
        - output_dir: Путь к выходной директории в S3 (обязательный)
        - ... [остальные параметры]
        """

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/qc-fq2bam-multiple-tubes-mounted",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"INCLUDE_UNMAPPED={include_unmapped}",
            "-p",
            f"MODE={mode}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"BUILD={build}",
            "--labels",
            f"batch_id={batch_id}"

        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/qc-fq2bam-multiple-tubes-offtargets with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_batchqc(
        self,
        mode: str,
        batch_id: str,
        basename: str,
        sample_ids: List[str],
        control_batch_ids: str,
        excel_filepath: str,
        cpus: str,
        ram: str,
        jobs: str,
        tel_chat: str,
        tel_token: str,
        input_dir: str = "/mnt/pipeline-v3.0/sth",
        output_dir: str = "/mnt/pipeline-v3.0/sth",
        assembly: str = "hg19",
        endpoint: str = "https://storage.yandexcloud.net",
        contamination_thresh: str = "0.1",
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/batch-qc-new-k8",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"TYPE={mode}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"CONTROL_BATCH_IDS={control_batch_ids}",
            "-p",
            f"EXCEL_FILEPATH={excel_filepath}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"TEL_CHAT={tel_chat}",
            "-p",
            f"TEL_TOEKN={tel_token}",
            "-p",
            f"ENDPOINT={endpoint}",
            "-p",
            f"Contamination_thresh={contamination_thresh}",           
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/batch-qc-new-k8 with parameters: batch_id={batch_id}, mode={mode}"
        )
        self._execute_command(command, stop_on_error)

    def submit_gender_comparison_mongo_bitrix(
        self,
        batch_id: str,
        bitrix_task_id: str,
        all_samples: [str | List[str]],
        exclude_samples: [str | List[str]],
        env: str,
        contamination_threshold: float,
        chip_type: str,
        s3_bucket_dir: str,
        tel_chat: str,
        tel_token: str,
        endpoint: str,
        wait: bool = False,
        stop_on_error: bool = False,
        ) -> None:


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/gender-comp-assign-prod",
            "-n",
            self.namespace,
            "-p",
            f"batchid={batch_id}",
            "-p",
            f"bitrix_task_id={bitrix_task_id}",
            "-p",
            f"all_samples={all_samples}",
            "-p",
            f"exclude_samples={exclude_samples}",
            "-p",
            f"ENV={env}",
            "-p",
            f"contamination_threshold={contamination_threshold}",
            "-p",
            f"chip_type={chip_type}",
            "-p",
            f"s3_bucket_dir={s3_bucket_dir}",
            "-p",
            f"telegram_chat_id={tel_chat}",
            "-p",
            f"telegram_token={tel_token}",
            "-p",
            f"endpoint={endpoint}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/gender-comp-assign-prod with parameters:  batch_id={batch_id}, env={env}"
        )
        self._execute_command(command, stop_on_error)

    def submit_split_bam_multiple_tubes_s3_mounted(
        self,
        batch_id: str,
        sample_ids: List[Dict[str, str]],
        input_dir: str,
        output_dir: str,
        ref: str,
        mode: str,
        basename_markdup: str,
        assembly: str,
        jobs: str,
        cpus: str,
        ram_multiplier: str,
        wait: bool = True,
        stop_on_error: bool = True,
        ) -> None:

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/split-bam-multiple-tubes-s3-mounted",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"S3_OUT_BUCKET={output_dir}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"REF={ref}",
            "-p",
            f"MODE={mode}",
            "-p",
            f"BASENAME={basename_markdup}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"RAM_Multiplier={ram_multiplier}",
            "--labels",
            f"batch_id={batch_id}"

        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/split-bam-multiple-tubes-s3-mounted with parameters:  batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_impute_multiple_chromosomes_glimpse(
        self,
        ref: str,
        batch_id: str,
        basename: str,
        sample_ids: List[str],
        jobs: str,
        cpus: str,
        input_dir: str,
        output_dir: str,
        build: str,
        glimpse_threads: str = "redundant",
        ref_bin_prefix: str = "Ultra_hrc_hg19",
        chunk_prefix: str = "Ultra_hrc_hg19_chunks",
        need_aggregation: str = "no",
        wait: bool = False,
        stop_on_error: bool = True
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/impute-multiple-chromosomes-glimpse",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"REF={ref}",
            "-p",
            f"BUILD={build}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"glimpse_threads={glimpse_threads}",
            "-p",
            f"ref_bin_prefix={ref_bin_prefix}",
            "-p",
            f"chunk_prefix={chunk_prefix}",
            "-p",
            f"need_aggregation={need_aggregation}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/impute-multiple-chromosomes-glimpse with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_impute_glimpse_partitioned(
        self,
        ref: str,
        batch_id: str,
        basename: str,
        sample_ids: List[str],
        jobs: str,
        jobs_imp_split:str,
        cpus_imp_split:str,
        imp_split_chunk_size:str,
        cpus: str,
        input_dir: str,
        output_dir: str,
        build: str,
        glimpse_threads: str = "redundant",
        ref_bin_prefix: str = "Ultra_hrc_hg19",
        chunk_prefix: str = "Ultra_hrc_hg19_chunks",
        need_aggregation: str = "no",
        wait: bool = False,
        stop_on_error: bool = True
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/imputing-master-test-multiple-chrs",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"REF={ref}",
            "-p",
            f"BUILD={build}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"split_jobs={jobs_imp_split}",
            "-p",
            f"CPUS={cpus}",
            "-p",
            f"split_CPUS={cpus_imp_split}",
            "-p",
            f"chunk-size={imp_split_chunk_size}",
            "-p",
            f"INPUT_DIR={input_dir}",
            "-p",
            f"OUTPUT_DIR={output_dir}",
            "-p",
            f"glimpse_threads={glimpse_threads}",
            "-p",
            f"ref_bin_prefix={ref_bin_prefix}",
            "-p",
            f"chunk_prefix={chunk_prefix}",
            "-p",
            f"need_aggregation={need_aggregation}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/imputing-master-test-multiple-chrs with parameters: batch_id={batch_id} (Partitioned Imputation)"
        )
        self._execute_command(command, stop_on_error)

    def submit_haplotypecaller_gvcf2vcf_full_multiple_tubes(
        self,
        batch_id: str,
        sample_ids: List[Dict[str, str]],
        input_dir_s3: str,
        output_dir_s3: str,
        ploidy_dir_s3: str,
        basename_called_vcf: str,
        assembly: str,
        dbsnp_vcf: str,
        dbsnp: str,
        ref: str,
        regions_without_homopolymers: str,
        delay_config: Optional[DelayConfig | Dict] = None,
        recalibrated: str = "no",
        cpus_haplotypecaller: int = 5,
        ram: int = 20,
        cpus_gvcf2vcf: int = 10,
        chromosomes_in_parallel: int = 5,
        bam_suffix: str = "markdup",
        wait: bool = True,
        stop_on_error: bool = True,
        ) -> None:
        """
        Запуск workflowtemplate/haplotypecaller-gvcf2vcf-full-multiple-tubes
        
        Параметры:
        - batch_id: Идентификатор батча (обязательный)
        - sample_ids: Список словарей с sample_id и delay (необязательный)
        - input_dir_s3: Путь к входной директории в S3 (обязательный)
        - ... [остальные параметры]
        """

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/haplotypecaller-gvcf2vcf-full-multiple-tubes",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"INPUT_DIR_S3={input_dir_s3}",
            "-p",
            f"OUTPUT_DIR_S3={output_dir_s3}",
            "-p",
            f"PLOIDY_DIR_S3={ploidy_dir_s3}",
            "-p",
            f"BASENAME_CALLED_VCF={basename_called_vcf}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"RECALIBRATED={recalibrated}",
            "-p",
            f"CPUS_haplotypecaller={cpus_haplotypecaller}",
            "-p",
            f"RAM={ram}",
            "-p",
            f"CPUS_gvcf2vcf={cpus_gvcf2vcf}",
            "-p",
            f"CHROMOSOMES_IN_PARALLEL={chromosomes_in_parallel}",
            "-p",
            f"BAM_SUFFIX={bam_suffix}",
            "-p",
            f"DBSNP_VCF={dbsnp_vcf}",
            "-p",
            f"DBSNP={dbsnp}",
            "-p",
            f"REF={ref}",
            "-p",
            f"REGIONS_WITHOUT_HOMOPOLYMERS={regions_without_homopolymers}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/haplotypecaller-gvcf2vcf-full-multiple-tubes with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_transfer_vcf_s3_dev(
        self,
        batch_id: str,
        sample_ids: List[str],
        dest_env: str,
        tel_token: str,
        tel_chat: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:


        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/transfer-vcf-s3-dev",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"DEST_ENV={dest_env}",
            "-p",
            f"TELEGRAM_BOT_TOKEN={tel_token}",
            "-p",
            f"TELEGRAM_CHAT_ID={tel_chat}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/transfer-vcf-s3-dev with parameters: batch_id={batch_id},dest_env={dest_env}"
        )
        self._execute_command(command, stop_on_error)

    def submit_post_imputation_s3_mounted_multitube_delay(
        self,
        batch_id: str,
        sample_ids: List[Dict[str, str]],
        input_dir_called_vcf: str,
        output_dir_imputed: str,
        supp_path_s3: str,
        ref: str,
        basename_called: str,
        basename_imputed: str,
        build: str,
        agree_to_blacklist:str,
        jobs: str,
        output_bucket_dir: str,
        output_reports: str ,
        raf: str = "0.95",
        gpmax: str = "0.001",
        wait: bool = True,
        stop_on_error: bool = True,
        ) -> None:

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good,
            batch_id
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/post-imputation-s3-mounted-multitube-delay",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"REF={ref}",
            "-p",
            f"RAF={raf}",
            "-p",
            f"GPMAX={gpmax}",            
            "-p",
            f"AGREE_TO_BLIST={agree_to_blacklist}",
            "-p",
            f"BASENAME_IMPUTED_VCFS={basename_imputed}",
            "-p",
            f"BASENAME_CALLED_VCF={basename_called}",
            "-p",
            f"BUILD={build}",
            "-p",
            f"JOBS={jobs}",
            "-p",
            f"OUTPUT_DIR={output_bucket_dir}",
            "-p",
            f"INPUT_DIR_CALLED_S3={input_dir_called_vcf}",
            "-p",
            f"INPUT_DIR_IMPUTED_S3={output_dir_imputed}",
            "-p",
            f"OUTPUT_REPORTS_MINIO={output_reports}",
            "-p",
            f"SUPP_PATH_S3={supp_path_s3}",
            "--labels",
            f"batch_id={batch_id}"

        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/post-imputation-s3-mounted-multitube-delay with parameters:  batch_id={batch_id}, destination={output_bucket_dir}"
        )
        self._execute_command(command, stop_on_error)

    def submit_beagle_imputation(
        self,
        date_batch_id: str,
        sample_ids: List[str],
        bucket: str,
        chunk_size: str,
        wait: bool = True,
        stop_on_error: bool = True
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/beagle-prod",
            "-n",
            self.namespace,
            "-p",
            f"samples-list={comma_ids}",
            "-p",
            f"batch-id={date_batch_id}",
            "-p",
            f"bucket={bucket}",
            "-p",
            f"chunk-size={chunk_size}",
            "--labels",
            f"batch-id={date_batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/beagle-prod with parameters: batch-id={date_batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_hla(
        self,
        local_input_hla: str,
        sample_ids: List[Dict[str, str]],
        basename: str,
        input_hla_s3: str,
        output_hla_s3: str,
        mnt_bucket_hla: str,
        reference: str,
        env: str,
        delay_config: Optional[DelayConfig | Dict] = None,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:


        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/hla-multiple-tubes-s3-mounted",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"INPUT_DIR={local_input_hla}",
            "-p",
            f"INPUT_DIR_S3={input_hla_s3}",
            "-p",
            f"OUTPUT_DIR_S3={output_hla_s3}",
            "-p",
            f"BUCKET={mnt_bucket_hla}",
            "-p",
            f"reference={reference}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"ENV={env}",
            "--labels",
            f"INPUT_DIR_S3={input_hla_s3}"
        ]

        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/hla-multiple-tubes-s3-mounted with parameters: INPUT_DIR_S3={input_hla_s3}"
        )
        self._execute_command(command, stop_on_error)

    def submit_hla_parser(
        self,
        mongo_db_hla: str,
        jobs_hla_parser: str,
        sample_ids: List[Dict[str, str]],
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/hla-parser-s3",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"Mongo_DB={mongo_db_hla}",
            "-p",
            f"JOBS={jobs_hla_parser}",
            "--labels",
            f"Mongo_DB={mongo_db_hla}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/hla-parser-s3 with parameters: Mongo_DB={mongo_db_hla}"
        )
        self._execute_command(command, stop_on_error)

    def submit_lk_files_s3(
        self,
        date_batch_id: str,
        sample_ids: List[Dict[str, str]],
        batch_id: str,
        called_basename: str,
        assembly: str,
        split_mode: str,
        delay_config: Optional[DelayConfig | Dict] = None,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:


        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/lk-file-s3-mounted-multitube-delay",
            "-n",
            self.namespace,
            "-p",
            f"sample_ids={json.dumps(sample_ids)}",
            "-p",
            f"date_batch_id={date_batch_id}",
            "-p",
            f"batch_id={batch_id}",
            "-p",
            f"called_basename={called_basename}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"SPLIT_MODE={split_mode}",
            "--labels",
            f"batch_id={batch_id}"
        ]

        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/lk-file-s3-mounted-multitube-delay with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_inheritance(
        self,
        clinvar_db: str,
        batch_id: str,
        basename: str,
        bucket: str,
        assembly: str,
        sample_ids: List[Dict[str, str]],
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:

        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/inheritance-multiple-tubes-dev",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={json.dumps(sample_ids)}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"BASENAME={basename}",
            "-p",
            f"BUCKET={bucket}",
            "-p",
            f"ASSEMBLY={assembly}",
            "-p",
            f"clinvar_db={clinvar_db}",
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            "Running workflowtemplate/inheritance-multiple-tubes-dev"
        )
        self._execute_command(command, stop_on_error)

    def submit_apoe(
        self,
        env: str,
        sample_ids: List[str],
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/apoe",
            "-n",
            self.namespace,
            "-p",
            f"tube_ids={comma_ids}",
            "-p",
            f"env={env}",
            "--labels",
            f"env={env}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/apoe with parameters: env={env}"
        )
        self._execute_command(command, stop_on_error)

    def submit_transfer_bam_s3_dev(
        self,
        batch_id: str,
        sample_ids: List[str],
        dest_env: str,
        tel_token: str,
        tel_chat: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:


        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/transfer-bam-s3-dev",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"BATCH_ID={batch_id}",
            "-p",
            f"DEST_ENV={dest_env}",
            "-p",
            f"TELEGRAM_BOT_TOKEN={tel_token}",
            "-p",
            f"TELEGRAM_CHAT_ID={tel_chat}",
            "--labels",
            f"BATCH_ID={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/transfer-bam-s3-dev with parameters: BATCH_ID={batch_id},DEST_ENV={dest_env}"
        )
        self._execute_command(command, stop_on_error)

    def submit_analyze_prs_traits_mito(
        self,
        sample_ids: List[Dict[str, str]],
        delay_config: Optional[DelayConfig | Dict] = None,
        wait: bool = True,
        stop_on_error: bool = False,
        ) -> None:


        self._validate_samples(
            self.delay_config,
            sample_ids,
            self.contour,
            self.only_good
        )

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/analyze-full-multiple-tubes-mm-meta-plus-prod",
            "-n",
            self.namespace,
            "-p",
            f"tube_ids={json.dumps(sample_ids)}",
        ]

        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/analyze-full-multiple-tubes-mm-meta-plus-prod"
        )
        self._execute_command(command, stop_on_error)

    def submit_yleaf(
        self,
        batch_id: str,
        env:str,
        input_mode:str,
        input_tubes: str,
        tel_chat: str,
        tel_token: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/yleaf-batch-processor-test",
            "-n",
            self.namespace,
            "-p",
            f"batch_id={batch_id}",
            "-p",
            f"env={env}",
            "-p",
            f"input_mode={input_mode}",
            "-p",
            f"input_tubes={input_tubes}",
            "-p",
            f"telegram_channel_id={tel_chat}",
            "-p",
            f"telegram_token={tel_token}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/yleaf-batch-processor-test with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_deep_mito_chunks(
        self,
        sample_ids: List[str],
        jobs_deep_mito: str,
        chunk_size_deep_mito: str,
        mode_deep_mito: str,
        build: str,
        version_deep_mito: str,
        tree_deep_mito: str,
        ref_type: str,
        hp_threshold_deep_mito: str,
        dedup_deep_mito: str,
        hotspot_deep_mito: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:

        comma_ids = ",".join([item["sample_id"] for item in sample_ids])

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/deep-mito-hp-chuncks-upd",
            "-n",
            self.namespace,
            "-p",
            f"SAMPLE_IDS={comma_ids}",
            "-p",
            f"chunk-size={chunk_size_deep_mito}",
            "-p",
            f"JOBS={jobs_deep_mito}",
            "-p",
            f"MODE={mode_deep_mito}",
            "-p",
            f"BUILD={build}",
            "-p",
            f"version={version_deep_mito}",
            "-p",
            f"tree={tree_deep_mito}",
            "-p",
            f"REF_type={ref_type}",
            "-p",
            f"hp_threshold={hp_threshold_deep_mito}",
            "-p",
            f"dedup={dedup_deep_mito}",
            "-p",
            f"HOTSPOT={hotspot_deep_mito}",
            "--labels",
            f"MODE={mode_deep_mito}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/deep-mito-hp-chuncks-upd with parameters: MODE={mode_deep_mito}"
        )
        self._execute_command(command, stop_on_error)

    def submit_batch_report(
        self,
        tel_chat: str,
        tel_token: str,
        batch_id: List[str],
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/batch-report-add-checks-test-dev",
            "-n",
            self.namespace,
            "-p",
            f"batch_id={batch_id}",
            "-p",
            f"tel_token={tel_token}",
            "-p",
            f"tel_chat_id={tel_chat}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/batch-report-add-checks-test-dev with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_final_checker(
        self,
        batch_id: str,
        assembly: str,
        run_num: str,
        delete: str,
        copy_bad: str,
        bad_only: str,
        jobs: str,
        tel_chat: str,
        tel_token: str,        
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:


        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/final-checker",
            "-n",
            self.namespace,
            "-p",
            f"batch_id={batch_id}",
            "-p",
            f"assembly={assembly}",
            "-p",
            f"run_num={run_num}",
            "-p",
            f"delete={delete}",
            "-p",
            f"copy_bad={copy_bad}",
            "-p",
            f"bad_only={bad_only}",
            "-p",
            f"jobs={jobs}",
            "-p",
            f"tg_chat_id={tel_chat}",
            "-p",
            f"tg_token={tel_token}",
            "--labels",
            f"batch_id={batch_id}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/final-checker with parameters: batch_id={batch_id}"
        )
        self._execute_command(command, stop_on_error)

    def submit_prs_lowmem(
        self,
        batchids_prs: str,
        mode_prs: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:
        batch_ids_list=json.dumps(batchids_prs.split(","))

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/prs-multiple-batches-or-tubes-lowmem-prod",
            "-n",
            self.namespace,
            "-p",
            f"batch_ids={batch_ids_list}",
            "-p",
            f"mode={mode_prs}",
            "--labels",
            f"mode={mode_prs}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/prs-multiple-batches-or-tubes-lowmem-prod with parameters: mode={batch_ids_list}"
        )
        self._execute_command(command, stop_on_error)

    def submit_prs_lowmem_saleem(
        self,
        batchids_prs: str,
        mode_prs: str,
        scores: str,
        wait: bool = True,
        stop_on_error: bool = False
        ) -> None:
        batch_ids_list=json.dumps(batchids_prs.split(","))

        command = [
            "argo",
            "submit",
            "--from",
            "workflowtemplate/prs-multiple-tubes-batches-saleem",
            "-n",
            self.namespace,
            "-p",
            f"batch_ids={batch_ids_list}",
            "-p",
            f"SCORES_ZIP_PATH={scores}",
            "-p",
            f"mode={mode_prs}",
            "--labels",
            f"mode={mode_prs}"
        ]
        if wait:
            command.append("--wait")

        self.logger.info(
            f"Running workflowtemplate/prs-multiple-tubes-batches-saleem with parameters: mode={mode_prs}"
        )
        self._execute_command(command, stop_on_error)

if __name__ == "__main__":

    from logger_config import setup_logging
    debug_mode = True

    setup_logging(debug_mode=debug_mode)