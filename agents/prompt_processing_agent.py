import os, time, json, re, threading, shutil
from datetime import datetime
from urllib.parse import urlencode
from pandaclient import PrunScript, panda_api
from pandaclient.Client import getTaskStatus, getPandaIDsWithTaskID, getFullJobStatus
from swf_common_lib.base_agent import BaseAgent
try:
    from agent_config_helpers import DecisionDatasetNamingMixin, PromptProcessingConfigMixin
except ModuleNotFoundError as e:
    if e.name != "agent_config_helpers":
        raise
    from agents.agent_config_helpers import DecisionDatasetNamingMixin, PromptProcessingConfigMixin

from swf_testbed_decision_box.monitor_metadata import execution_id_matches
from swf_testbed_decision_box.models import Decision, FileDID

#################################################################################
class PROCESSING(PromptProcessingConfigMixin, DecisionDatasetNamingMixin, BaseAgent):
    ''' The PROCESSING class is the main task management class.
        It receives MW messages from the DAQ simulator and handles them.
        Main functionality is to manage PanDA tasks for the testbed.
    '''

    def __init__(self, config_path=None, verbose=False, test=False):
        super().__init__(agent_type='PROCESSING', subscription_queue='/topic/epictopic',
                         debug=verbose, config_path=config_path)

        self.verbose      = verbose
        self.test         = test
        self.run_id       = None  # Current run number
        self.inDS         = None  # Input dataset name
        self.outDS        = None  # Output dataset name
        self.panda_status = {}    # PanDA submission status

        self.active_processing = {}  # Track files being processed
        self.processing_stats = {'total_processed': 0, 'failed_count': 0}
        self.polling_tasks = {}
        self.polling_thread = None
        self.polling_lock = threading.Lock()
        self.polling_stop_event = threading.Event()
        self.prun_lock = threading.Lock()
        self.data_ready_lock = threading.Lock()
        self.prun_work_root = os.getcwd()
        self.prun_payload_script = os.path.join(self.prun_work_root, "payload.sh")
        prompt_config = self._load_prompt_processing_config()
        self.panda_poll_interval_seconds = self._config_int(
            prompt_config,
            "panda_poll_interval_seconds",
            "SWF_PANDA_POLL_INTERVAL",
            30,
        )
        self.panda_poll_timeout_seconds = self._config_int(
            prompt_config,
            "panda_poll_timeout_seconds",
            "SWF_PANDA_POLL_TIMEOUT",
            0,
        )
        self.background_stf_ready = self._config_bool(
            prompt_config,
            "background_stf_ready",
            "SWF_PROMPT_PROCESSING_BACKGROUND",
            False,
        )
        self.non_decision_box_site = os.getenv(
            "SWF_NON_DECISION_BOX_SITE",
            str(prompt_config.get("non_decision_box_site", "E1_BNL")),
        ).strip()
        self.decision_box_enabled = self._config_bool(
            prompt_config,
            "decision_box_enabled",
            "SWF_DECISION_BOX_ENABLED",
            False,
        )
        self.decision_box_sites = self._config_list(
            prompt_config,
            "decision_box_sites",
            "SWF_DECISION_BOX_SITES",
            ["E1_BNL", "E1_JLAB"],
        )
        self.decision_box_rucio_scope = os.getenv(
            "SWF_DECISION_BOX_RUCIO_SCOPE",
            str(prompt_config.get("decision_box_rucio_scope", "group.daq")),
        ).strip()
        self.decision_box_site_dataset_template = os.getenv(
            "SWF_DECISION_BOX_SITE_DATASET_TEMPLATE",
            str(prompt_config.get("decision_box_site_dataset_template", "")),
        ).strip() or None

        if self.verbose: print(f'''*** Initialized the PROCESSING class, test mode is {self.test} ***''')


    def _decision_box_context_for_run(self, run_id):
        return self.active_processing.get(str(run_id)) or self.panda_status.get(str(run_id)) or {}


    def _safe_path_component(self, value):
        """Return a filesystem-safe token for generated prun work directories."""
        token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "unknown")).strip("._")
        return token or "unknown"


    def _prepare_prun_workdir(self, run_number, site_name):
        """Create an isolated minimal work directory for one prun sandbox."""
        run_token = self._safe_path_component(run_number)
        site_token = self._safe_path_component(site_name)
        unique_token = f"{time.time_ns()}-{threading.get_ident()}"
        workdir = os.path.join(
            self.prun_work_root,
            "prun-submissions",
            f"run-{run_token}-{site_token}-{unique_token}",
        )
        os.makedirs(workdir, exist_ok=False)
        if os.path.exists(self.prun_payload_script):
            shutil.copy2(self.prun_payload_script, os.path.join(workdir, "payload.sh"))
        else:
            self.logger.warning(
                f"Payload script {self.prun_payload_script} does not exist; prun sandbox may be incomplete",
                extra=self._log_extra(run_id=run_number),
            )
        return workdir


    def _build_prun_params(self, prun_args, run_number=None, site_name=None):
        """Run PrunScript.main from an isolated directory.

        PrunScript changes the process cwd while creating the sandbox, so this
        section is serialized even when stf_ready handlers run in background.
        """
        workdir = self._prepare_prun_workdir(run_number, site_name)
        with self.prun_lock:
            previous_cwd = os.getcwd()
            try:
                os.chdir(workdir)
                return PrunScript.main(True, prun_args)
            finally:
                os.chdir(previous_cwd)


    # ---
    def test_panda(self, inDS, outDS, output):
        '''
        Simple test of PanDA submission with given input and output datasets,
        essentailly static.
        '''
        # Construct the full list of arguments for PrunScript.main
        # I/O datasets examples: inDS="group.daq:swf.101871.run", outDS="user.potekhin.test1"
        # Note there is only one name of the payload, which gets overwritten each time if needed
        # in the driver script.
        
        prun_args = [
        "--exec",   "./payload.sh",
        "--inDS",   inDS,
        "--outDS",  outDS,
        "--nJobs",  "1",
        "--vo",     "epic",
        "--site",   "E1_BNL",
        "--prodSourceLabel",    "test",
        "--workingGroup",       "EIC",
        "--noBuild",
        "--expertOnly_skipScout",
        "--outputs", output
        ]

        #  Call PrunScript.main to get the task parameters dictionary
        try:
            params = self._build_prun_params(prun_args, self.run_id, "test")
        except Exception as e:
            print(f"PRUN CRITICAL: - {str(e)}")
            return None

        # Important: to process input files as they are added to the dataset
        params['runUntilClosed'] = False # for testing, set to False
        #params['taskType'] = "stfprocessing"

        status, msg = self.panda_submit_task(params)
        self.panda_status[self.run_id] = {'status': status, 'message': msg}

        return None
   

    # ---
    def name_current_datasets(self):
        self.inDS   = f'''swf.{self.run_id}.run'''          # INput dataset name based on the run number
        self.outDS  = f'''swf.{self.run_id}.processed'''    # Output dataset
        
        if self.verbose:
            print(f"*** Named datasets for run {self.run_id} ***")
            print(f"*** inDS: {self.inDS} ***")
            print(f"*** outDS: {self.outDS} ***")


    # ---
    def panda_submit_task(self, params):
        if self.verbose:
            print(f"*** PANDA PARAMS ***")
            for k in params.keys():
                v = params[k]
                print(f"{k:<20}: {v}")
            print(f"********************")

        # Get the PanDA API client
        if self.verbose: print("*** Getting PanDA API client... ***")
        my_api = panda_api.get_api()

        # Submit the task
        # print(f"Submitting task to PanDA with output dataset: {outDS} ...")
        status, result_tuple = my_api.submit_task(params)

        # Check the submission status
        if status == 0:
            print(result_tuple)
        else:
            print(f"Task submission failed. Status: {status}, Message: {result_tuple}")

        return status, result_tuple


    def _extract_panda_task_id(self, submit_result):
        """Return jediTaskID from common PanDA submission result shapes."""
        if isinstance(submit_result, (list, tuple)):
            for item in reversed(submit_result):
                task_id = self._extract_panda_task_id(item)
                if task_id:
                    return task_id
        elif isinstance(submit_result, dict):
            for key in ("jediTaskID", "jeditaskid", "taskID", "task_id"):
                if submit_result.get(key):
                    return str(submit_result[key])
        elif submit_result is not None:
            match = re.search(r"(?:jediTaskID|task[_ ]?id)\D+(\d+)", str(submit_result), re.IGNORECASE)
            if match:
                return match.group(1)
        return None


    def _task_status(self, task_id):
        try:
            result = getTaskStatus(task_id)
            if isinstance(result, (list, tuple)) and len(result) >= 2:
                return str(result[1]).lower()
            return str(result).lower()
        except Exception as e:
            self.logger.warning(
                f"Failed to query PanDA task status for {task_id}: {e}",
                extra=self._log_extra(run_id=self.run_id)
            )
            return None


    def _panda_ids_for_task(self, task_id):
        if not task_id:
            return []
        try:
            status, data = getPandaIDsWithTaskID(task_id)
        except Exception as e:
            self.logger.warning(
                f"Failed to query PanDA job IDs for task {task_id}: {e}",
                extra=self._log_extra(run_id=self.run_id, panda_task_id=task_id)
            )
            return []
        if status != 0 or not data:
            return []
        if isinstance(data, dict):
            for key in ("PandaID", "pandaIDs", "panda_ids", "ids"):
                if isinstance(data.get(key), list):
                    return [str(panda_id) for panda_id in data[key]]
            return []
        if isinstance(data, (list, tuple, set)):
            return [str(panda_id) for panda_id in data]
        return [str(data)]


    def _full_job_statuses(self, panda_ids):
        if not panda_ids:
            return []
        try:
            status, jobs = getFullJobStatus(list(panda_ids))
        except Exception as e:
            self.logger.warning(
                f"Failed to query PanDA job status: {e}",
                extra=self._log_extra(run_id=self.run_id)
            )
            return []
        if status != 0 or not jobs:
            return []
        return jobs if isinstance(jobs, list) else [jobs]


    def _job_status_records(self, task_id):
        """Return PanDA job status records with input LFNs for a task."""
        records = []
        for job in self._full_job_statuses(self._panda_ids_for_task(task_id)):
            panda_id = str(getattr(job, "PandaID", ""))
            job_status = str(getattr(job, "jobStatus", "")).lower()
            input_files = []
            for file_spec in getattr(job, "Files", []) or []:
                file_type = str(getattr(file_spec, "type", "")).lower()
                lfn = str(getattr(file_spec, "lfn", ""))
                if file_type == "input" and lfn and not lfn.endswith(".lib.tgz"):
                    input_files.append(lfn)
            records.append({
                "panda_id": panda_id,
                "status": job_status,
                "input_files": input_files,
            })
        return records


    def _stf_stem(self, filename):
        stem = os.path.basename(filename)
        for suffix in (".stf", ".dat"):
            if stem.endswith(suffix):
                return stem[:-len(suffix)]
        return os.path.splitext(stem)[0]


    def _input_matches_stf(self, stf_filename, input_files):
        stf_base = os.path.basename(stf_filename)
        stf_stem = self._stf_stem(stf_filename)
        for input_file in input_files:
            input_base = os.path.basename(input_file)
            input_stem = self._stf_stem(input_file)
            if stf_base == input_base or stf_stem == input_stem:
                return True
        return False


    def _output_dataset_did(self, run_number):
        username = os.getenv('PANDA_NICKNAME', os.getenv('USER', 'unknown'))
        return f"user.{username}.swf.{run_number}.processed"


    def _output_dataset_did_for_site(self, run_number, site_name, output_suffix=None):
        output_dataset = f"{self._output_dataset_did(run_number)}.{site_name}"
        if output_suffix:
            safe_suffix = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(output_suffix).strip())
            if safe_suffix:
                output_dataset = f"{output_dataset}.{safe_suffix}"
        return output_dataset


    def _decision_from_stf_file(self, run_number, stf_file):
        """Read the data-agent decision from an STF monitor row."""
        metadata = stf_file.get("metadata") or {}
        file_did_value = metadata.get("decision_box_file_did")
        site_datasets = tuple(metadata.get("decision_box_site_datasets") or ())
        if not file_did_value or not site_datasets:
            return None
        try:
            file_did = FileDID.parse(file_did_value, default_scope=self.decision_box_rucio_scope)
        except ValueError:
            return None
        run_dataset = self._run_dataset_did(run_number)
        return Decision(
            run_dataset=run_dataset,
            full_dataset=run_dataset,
            file_did=file_did,
            site_datasets=site_datasets,
            reason=metadata.get("decision_box_reason", "data-agent decision"),
        )


    def _decision_from_filename(self, run_number, filename, execution_id=None):
        stf_file = self._monitor_stf_file_by_filename(
            filename,
            run_number=run_number,
            execution_id=execution_id,
        )
        if not stf_file:
            return None
        return self._decision_from_stf_file(run_number, stf_file)


    def _monitor_run_id(self, run_number):
        runs = self._api_records(self.call_monitor_api("GET", "/runs/"))
        for run in runs or []:
            if str(run.get("run_number")) == str(run_number):
                return run.get("run_id")
        return None


    def _api_records(self, response):
        if isinstance(response, list):
            return response
        if isinstance(response, dict):
            for key in ("results", "data", "items"):
                if isinstance(response.get(key), list):
                    return response[key]
        return []


    def _monitor_stf_files(self, params=None, limit=500):
        """Fetch STF rows using server-side filters when available.

        Use only conservative server-side filters here. run_number is enough
        to reduce normal polling load, while status/stf_filename/workflow_id
        are checked locally to avoid depending on newer monitor filter code.
        """
        query_params = {
            key: value for key, value in (params or {}).items()
            if value is not None and value != ""
        }
        query_params.setdefault("limit", limit)

        records = []
        offset = int(query_params.get("offset") or 0)
        while True:
            page_params = dict(query_params)
            page_params["offset"] = offset
            response = self.call_monitor_api("GET", f"/stf-files/?{urlencode(page_params)}")
            page_records = self._api_records(response)
            records.extend(page_records)

            if not isinstance(response, dict):
                break
            next_url = response.get("next")
            count = response.get("count")
            if not next_url:
                break
            offset += len(page_records)
            if not page_records or (isinstance(count, int) and offset >= count):
                break
        return records


    def _monitor_stf_files_for_run(self, run_number, status=None, execution_id=None):
        monitor_run_id = self._monitor_run_id(run_number)
        query = {
            "run_number": run_number,
        }
        files = self._monitor_stf_files(query)
        if monitor_run_id is not None:
            filtered = [f for f in files if str(f.get("run")) == str(monitor_run_id)]
        else:
            filtered = [f for f in files if str(f.get("run")) == str(run_number)]
        if status:
            filtered = [f for f in filtered if str(f.get("status")) == str(status)]
        if execution_id:
            filtered = [
                f for f in filtered
                if self._execution_id_matches((f.get("metadata") or {}), execution_id)
            ]
        return filtered


    def _monitor_stf_file_by_filename(self, filename, run_number=None, execution_id=None):
        files = self._monitor_stf_files_for_run(run_number) if run_number is not None else self._monitor_stf_files()
        for stf_file in files:
            if stf_file.get("stf_filename") != filename:
                continue
            metadata = stf_file.get("metadata") or {}
            if not self._execution_id_matches(metadata, execution_id):
                continue
            return stf_file
        return None


    def _active_monitor_stf_files_for_run(self, run_number, execution_id=None):
        return (
            self._monitor_stf_files_for_run(run_number, status="registered", execution_id=execution_id)
            + self._monitor_stf_files_for_run(run_number, status="processing", execution_id=execution_id)
        )


    def _execution_id_matches(self, metadata, execution_id=None):
        return execution_id_matches(metadata, execution_id)


    def _monitor_run_number_by_id(self, monitor_run_id):
        runs = self._api_records(self.call_monitor_api("GET", "/runs/"))
        for run in runs:
            if str(run.get("run_id")) == str(monitor_run_id):
                return str(run.get("run_number"))
        return str(monitor_run_id)


    def _tracked_by_this_agent(self, stf_file, execution_id=None, panda_task_id=None):
        metadata = stf_file.get("metadata") or {}
        if not (
            metadata.get("panda_tracking_agent") == self.agent_name
            and metadata.get("panda_tracking_namespace") == self.namespace
        ):
            return False
        if not self._execution_id_matches(metadata, execution_id):
            return False
        if panda_task_id and str(metadata.get("panda_task_id")) != str(panda_task_id):
            return False
        return True


    def _recoverable_by_this_agent(self, stf_file, execution_id=None, panda_task_id=None):
        metadata = stf_file.get("metadata") or {}
        if metadata.get("panda_tracking_namespace") != self.namespace:
            return False
        if not self._execution_id_matches(metadata, execution_id):
            return False
        site_task_ids = metadata.get("panda_site_task_ids") or {}
        if panda_task_id and str(panda_task_id) in {str(task_id) for task_id in site_task_ids.values() if task_id}:
            return True
        if panda_task_id and str(metadata.get("panda_task_id")) != str(panda_task_id):
            return False
        if panda_task_id is None and metadata.get("panda_task_id"):
            return False
        return True


    def _claimable_by_this_agent(self, stf_file, execution_id=None, allow_unclaimed=False):
        metadata = stf_file.get("metadata") or {}
        tracking_agent = metadata.get("panda_tracking_agent")
        tracking_namespace = metadata.get("panda_tracking_namespace")
        row_execution_id = metadata.get("workflow_execution_id")
        if row_execution_id and not self._execution_id_matches(metadata, execution_id):
            return False
        if not tracking_agent and not tracking_namespace:
            return allow_unclaimed or (execution_id is not None and row_execution_id == execution_id)
        if tracking_namespace == self.namespace and execution_id and row_execution_id == execution_id:
            return True
        return self._tracked_by_this_agent(stf_file, execution_id=execution_id)


    def _needs_processing_claim(self, stf_file, panda_task_id=None, execution_id=None):
        """Return True when the monitor row needs a processing claim PATCH."""
        metadata = stf_file.get("metadata") or {}
        site_task_ids = metadata.get("panda_site_task_ids") or {}

        if stf_file.get("status") != "processing":
            return True
        if metadata.get("panda_tracking_agent") != self.agent_name:
            return True
        if metadata.get("panda_tracking_namespace") != self.namespace:
            return True
        if not self._execution_id_matches(metadata, execution_id):
            return True
        if panda_task_id and str(panda_task_id) in {str(task_id) for task_id in site_task_ids.values() if task_id}:
            return False
        if panda_task_id and str(metadata.get("panda_task_id")) != str(panda_task_id):
            return True
        return False


    def _patch_stf_file(
        self,
        stf_file,
        status,
        panda_task_id=None,
        matched_input_files=None,
        reason=None,
        run_number=None,
        execution_id=None,
        extra_metadata=None,
        output_dataset=None,
    ):
        metadata = stf_file.get("metadata") or {}
        metadata.update({
            "processed_by": self.agent_name,
            "panda_tracking_agent": self.agent_name,
            "panda_tracking_namespace": self.namespace,
            "panda_task_id": panda_task_id,
            "panda_polled_at": datetime.now().isoformat(),
        })
        all_site_outputs = {}
        if isinstance(metadata.get("panda_site_output_datasets"), dict):
            all_site_outputs.update(metadata.get("panda_site_output_datasets") or {})
        if isinstance((extra_metadata or {}).get("panda_site_output_datasets"), dict):
            all_site_outputs.update((extra_metadata or {}).get("panda_site_output_datasets") or {})

        scalar_output_dataset = output_dataset
        if len(all_site_outputs) > 1:
            scalar_output_dataset = None
        if scalar_output_dataset is None:
            if len(all_site_outputs) == 1:
                scalar_output_dataset = next(iter(all_site_outputs.values()))
            elif not all_site_outputs:
                scalar_output_dataset = self._output_dataset_did(run_number or stf_file.get("run"))
        if scalar_output_dataset:
            metadata["panda_output_dataset"] = scalar_output_dataset
        elif "panda_output_dataset" in metadata:
            metadata.pop("panda_output_dataset", None)
        if execution_id:
            metadata["workflow_execution_id"] = execution_id
        if matched_input_files is not None:
            metadata["matched_input_files"] = matched_input_files
        if reason:
            metadata["panda_poll_reason"] = reason
        if extra_metadata:
            metadata.update(extra_metadata)

        return self.call_monitor_api(
            "PATCH",
            f"/stf-files/{stf_file.get('file_id')}/",
            {"status": status, "metadata": metadata}
        )


    def _site_name_for_task_id(self, metadata, panda_task_id, fallback_site=None):
        """Return the decision-box site name associated with a PanDA task."""
        if fallback_site:
            return fallback_site
        task_id_value = str(panda_task_id) if panda_task_id is not None else ""
        for site_name, task_id in (metadata.get("panda_site_task_ids") or {}).items():
            if task_id and str(task_id) == task_id_value:
                return site_name
        return None


    def _aggregate_decision_status(self, site_statuses, selected_sites):
        """Collapse per-site status into the single monitor row status."""
        if not selected_sites:
            return "processing"
        statuses = [
            (site_statuses.get(site_name) or {}).get("status")
            for site_name in selected_sites
        ]
        if statuses and all(status == "processed" for status in statuses):
            return "processed"
        if statuses and all(status in {"processed", "failed"} for status in statuses):
            return "failed" if any(status == "failed" for status in statuses) else "processed"
        return "processing"


    def _decision_site_poll_metadata(
        self,
        stf_file,
        panda_task_id,
        site_status,
        run_number=None,
        site_name=None,
        matched_input_files=None,
        reason=None,
        job=None,
    ):
        """Build metadata for one site poll without losing sibling site state."""
        metadata = stf_file.get("metadata") or {}
        site_name = self._site_name_for_task_id(metadata, panda_task_id, fallback_site=site_name)
        if not site_name:
            return site_status, {}
        site_statuses = dict(metadata.get("panda_site_statuses") or {})
        site_outputs = metadata.get("panda_site_output_datasets") or {}
        site_inputs = metadata.get("panda_site_input_datasets") or {}
        site_entry = dict(site_statuses.get(site_name) or {})
        site_entry.update({
            "status": site_status,
            "task_id": str(panda_task_id) if panda_task_id is not None else None,
            "input_dataset": site_inputs.get(site_name),
            "output_dataset": site_outputs.get(site_name),
            "polled_at": datetime.now().isoformat(),
        })
        if matched_input_files is not None:
            site_entry["matched_input_files"] = matched_input_files
        if reason:
            site_entry["reason"] = reason
        if job:
            site_entry["panda_job_id"] = job.get("panda_id")
            site_entry["panda_job_status"] = job.get("status")
        site_statuses[site_name] = site_entry
        selected_sites = list(site_inputs.keys()) or list((metadata.get("panda_site_task_ids") or {}).keys())
        aggregate_status = self._aggregate_decision_status(site_statuses, selected_sites)
        return aggregate_status, {
            "panda_selected_site": site_name,
            "panda_site_statuses": site_statuses,
        }


    def mark_run_stfs_processing(self, run_number, panda_task_id=None, execution_id=None, decision_box_enabled=None):
        """Claim all eligible monitor STF rows for this run/task."""
        if not panda_task_id:
            self.logger.warning(
                f"Not marking STF files processing for run {run_number}: missing PanDA task ID",
                extra=self._log_extra(run_id=run_number, execution_id=execution_id)
            )
            return 0
        if decision_box_enabled is None:
            decision_box_enabled = self._decision_box_enabled_for_message({}, run_id=run_number)
        if decision_box_enabled:
            task_info = self.active_processing.get(str(run_number)) or self.panda_status.get(str(run_number)) or {}
            site_tasks = task_info.get("site_tasks") or {}
            if not site_tasks:
                return 0
            updated = 0
            for stf_file in self._active_monitor_stf_files_for_run(run_number, execution_id=execution_id):
                decision = self._decision_from_stf_file(run_number, stf_file)
                if not decision:
                    continue
                updated += self.mark_stf_processing_for_decision(
                    stf_file.get("stf_filename"),
                    run_number,
                    decision,
                    site_tasks,
                    execution_id=execution_id,
                )
            return updated
        updated = 0
        for stf_file in self._active_monitor_stf_files_for_run(run_number, execution_id=execution_id):
            if not self._claimable_by_this_agent(stf_file, execution_id=execution_id, allow_unclaimed=True):
                continue
            if not self._needs_processing_claim(stf_file, panda_task_id=panda_task_id, execution_id=execution_id):
                continue
            if self._patch_stf_file(stf_file, "processing", panda_task_id=panda_task_id, run_number=run_number, execution_id=execution_id):
                updated += 1
        self.logger.info(
            f"Marked {updated} STF files processing for run {run_number}",
            extra=self._log_extra(run_id=run_number, panda_task_id=panda_task_id)
        )
        return updated


    def mark_stf_processing_by_filename(
        self,
        filename,
        run_number,
        panda_task_id=None,
        execution_id=None,
        extra_metadata=None,
        output_dataset=None,
    ):
        """Claim one STF row when its stf_gen message arrives."""
        if not execution_id:
            return False
        stf_file = self._monitor_stf_file_by_filename(filename, run_number=run_number, execution_id=execution_id)
        if not stf_file:
            return False
        if stf_file.get("status") not in {"registered", "processing"}:
            return False
        if not self._claimable_by_this_agent(stf_file, execution_id=execution_id, allow_unclaimed=True):
            return False
        return bool(self._patch_stf_file(
            stf_file,
            "processing",
            panda_task_id=panda_task_id,
            run_number=run_number,
            execution_id=execution_id,
            extra_metadata=extra_metadata,
            output_dataset=output_dataset,
        ))


    def _selected_decision_site_tasks(self, decision, site_tasks):
        return {
            site_name: site_task
            for site_name, site_task in (site_tasks or {}).items()
            if site_task.get("input_dataset") in decision.site_datasets
        }


    def _submitted_decision_site_tasks(self, selected_site_tasks):
        return {
            site_name: site_task
            for site_name, site_task in selected_site_tasks.items()
            if site_task.get("status") == 0 and site_task.get("task_id")
        }


    def _decision_site_task_metadata(self, decision, selected_site_tasks, existing_metadata):
        submitted_site_tasks = self._submitted_decision_site_tasks(selected_site_tasks)
        site_task_ids = {
            site_name: site_task.get("task_id")
            for site_name, site_task in submitted_site_tasks.items()
        }
        metadata = {
            "decision_box_reason": decision.reason,
            "decision_box_file_did": str(decision.file_did),
            "decision_box_site_datasets": list(decision.site_datasets),
            "panda_site_task_ids": site_task_ids,
            "panda_site_input_datasets": {
                site_name: site_task.get("input_dataset")
                for site_name, site_task in selected_site_tasks.items()
            },
            "panda_site_output_datasets": {
                site_name: site_task.get("output_dataset")
                for site_name, site_task in selected_site_tasks.items()
            },
            "panda_site_statuses": dict((existing_metadata or {}).get("panda_site_statuses") or {}),
        }
        for site_name, site_task in submitted_site_tasks.items():
            metadata["panda_site_statuses"].setdefault(site_name, self._decision_site_status("processing", site_task))
        for site_name, site_task in selected_site_tasks.items():
            if site_name not in submitted_site_tasks:
                metadata["panda_site_statuses"][site_name] = self._decision_site_status(
                    "failed",
                    site_task,
                    reason=f"PanDA submission failed: {site_task.get('message')}",
                )
        return metadata


    def _decision_site_status(self, status, site_task, reason=None):
        entry = {
            "status": status,
            "task_id": str(site_task.get("task_id")) if site_task.get("task_id") else None,
            "input_dataset": site_task.get("input_dataset"),
            "output_dataset": site_task.get("output_dataset"),
        }
        if reason:
            entry["reason"] = reason
        return entry


    def _primary_decision_task_id(self, metadata):
        return next(iter((metadata.get("panda_site_task_ids") or {}).values()), None)


    def _single_decision_output_dataset(self, metadata):
        output_datasets = metadata.get("panda_site_output_datasets") or {}
        if len(output_datasets) == 1:
            return next(iter(output_datasets.values()))
        return None


    def mark_stf_processing_for_decision(self, filename, run_number, decision, site_tasks, execution_id=None):
        """Claim one STF monitor row with the site tasks selected by the decision box."""
        if not filename or not decision or not site_tasks:
            return 0
        stf_file = self._monitor_stf_file_by_filename(filename, run_number=run_number, execution_id=execution_id)
        if not stf_file:
            return 0
        existing_metadata = (stf_file or {}).get("metadata") or {}
        selected_site_tasks = self._selected_decision_site_tasks(decision, site_tasks)
        if not selected_site_tasks:
            return 0
        metadata = self._decision_site_task_metadata(decision, selected_site_tasks, existing_metadata)
        primary_task_id = self._primary_decision_task_id(metadata)
        output_dataset = self._single_decision_output_dataset(metadata)
        if not primary_task_id:
            patch_status = self._aggregate_decision_status(
                metadata["panda_site_statuses"],
                list(metadata["panda_site_input_datasets"].keys()),
            )
            return int(bool(self._patch_stf_file(
                stf_file,
                patch_status,
                panda_task_id=None,
                reason="all selected decision-box site submissions failed",
                run_number=run_number,
                execution_id=execution_id,
                extra_metadata=metadata,
                output_dataset=output_dataset,
            )))
        return int(self.mark_stf_processing_by_filename(
            filename,
            run_number,
            primary_task_id,
            execution_id=execution_id,
            extra_metadata=metadata,
            output_dataset=output_dataset,
        ))


    def poll_processed_stf_files_once(
        self,
        run_number,
        panda_task_id=None,
        execution_id=None,
        site_name=None,
        input_dataset=None,
        decision_box_enabled=None,
    ):
        """Run one PanDA status poll and patch matching swf-monitor STF rows."""
        if not panda_task_id:
            self.logger.warning(
                f"Skipping PanDA polling for run {run_number}: missing PanDA task ID",
                extra=self._log_extra(run_id=run_number, execution_id=execution_id)
            )
            return {
                "processed": 0,
                "failed": 0,
                "task_status": None,
                "jobs_seen": 0,
                "unfinished": 0,
                "unmatched": 0,
                "complete": True,
            }
        job_success = {"finished"}
        job_failure = {"failed", "cancelled", "closed"}
        task_terminal = {"done", "finished", "failed", "aborted", "cancelled", "closed"}
        active_statuses = {"registered", "processing"}
        task_status = self._task_status(panda_task_id) if panda_task_id else None
        job_records = self._job_status_records(panda_task_id)
        if decision_box_enabled is None:
            decision_box_enabled = self._decision_box_enabled_for_message({}, run_id=run_number)

        # Each poll re-scans the run so late-registered STF rows are claimed.
        self.mark_run_stfs_processing(
            run_number,
            panda_task_id,
            execution_id=execution_id,
            decision_box_enabled=decision_box_enabled,
        )

        stf_files = [
            f for f in self._monitor_stf_files_for_run(run_number, status="processing", execution_id=execution_id)
            if self._recoverable_by_this_agent(f, execution_id=execution_id, panda_task_id=panda_task_id)
        ]
        processed = 0
        failed = 0
        matched_file_ids = set()
        for stf_file in stf_files:
            matching_jobs = [
                job for job in job_records
                if self._input_matches_stf(stf_file.get("stf_filename", ""), job.get("input_files", []))
            ]
            if not matching_jobs:
                continue

            matched_file_ids.add(stf_file.get("file_id"))
            success_jobs = [job for job in matching_jobs if job.get("status") in job_success]
            failed_jobs = [job for job in matching_jobs if job.get("status") in job_failure]
            if success_jobs:
                job = success_jobs[-1]
                matched_inputs = sorted(job.get("input_files", []))
                patch_status = "processed"
                patch_metadata = {
                    "panda_job_id": job.get("panda_id"),
                    "panda_job_status": job.get("status"),
                    "matched_input_files": matched_inputs,
                }
                patch_output_dataset = None
                if decision_box_enabled:
                    patch_status, site_metadata = self._decision_site_poll_metadata(
                        stf_file,
                        panda_task_id,
                        "processed",
                        run_number=run_number,
                        site_name=site_name,
                        matched_input_files=matched_inputs,
                        job=job,
                    )
                    patch_metadata.update(site_metadata)
                    selected_site = site_metadata.get("panda_selected_site")
                    site_outputs = (stf_file.get("metadata") or {}).get("panda_site_output_datasets") or {}
                    patch_output_dataset = site_outputs.get(selected_site)
                if self._patch_stf_file(
                    stf_file,
                    patch_status,
                    panda_task_id,
                    matched_inputs,
                    run_number=run_number,
                    execution_id=execution_id,
                    extra_metadata=patch_metadata,
                    output_dataset=patch_output_dataset,
                ):
                    processed += 1
            elif stf_file.get("status") != "processed" and failed_jobs and all(job.get("status") in job_failure for job in matching_jobs):
                job = failed_jobs[-1]
                matched_inputs = sorted(job.get("input_files", []))
                reason = f"panda job {job.get('panda_id')} {job.get('status')}"
                patch_status = "failed"
                patch_metadata = {
                    "panda_job_id": job.get("panda_id"),
                    "panda_job_status": job.get("status"),
                    "matched_input_files": matched_inputs,
                }
                patch_output_dataset = None
                if decision_box_enabled:
                    patch_status, site_metadata = self._decision_site_poll_metadata(
                        stf_file,
                        panda_task_id,
                        "failed",
                        run_number=run_number,
                        site_name=site_name,
                        matched_input_files=matched_inputs,
                        reason=reason,
                        job=job,
                    )
                    patch_metadata.update(site_metadata)
                    selected_site = site_metadata.get("panda_selected_site")
                    site_outputs = (stf_file.get("metadata") or {}).get("panda_site_output_datasets") or {}
                    patch_output_dataset = site_outputs.get(selected_site)
                if self._patch_stf_file(
                    stf_file,
                    patch_status,
                    panda_task_id,
                    reason=reason,
                    run_number=run_number,
                    execution_id=execution_id,
                    extra_metadata=patch_metadata,
                    output_dataset=patch_output_dataset,
                ):
                    failed += 1

        is_task_terminal = task_status in task_terminal
        refreshed_stf_files = [
            f for f in self._monitor_stf_files_for_run(run_number, status="processing", execution_id=execution_id)
            if self._recoverable_by_this_agent(f, execution_id=execution_id, panda_task_id=panda_task_id)
        ]
        unfinished = [
            f for f in refreshed_stf_files
            if f.get("status") in active_statuses
        ]
        unmatched = [
            f for f in unfinished
            if f.get("file_id") not in matched_file_ids
        ]
        if is_task_terminal:
            for stf_file in unmatched:
                reason = f"no PanDA job found before task became {task_status}"
                patch_status = "failed"
                patch_metadata = {}
                patch_output_dataset = None
                if decision_box_enabled:
                    patch_status, site_metadata = self._decision_site_poll_metadata(
                        stf_file,
                        panda_task_id,
                        "failed",
                        run_number=run_number,
                        site_name=site_name,
                        reason=reason,
                    )
                    patch_metadata.update(site_metadata)
                    selected_site = site_metadata.get("panda_selected_site")
                    site_outputs = (stf_file.get("metadata") or {}).get("panda_site_output_datasets") or {}
                    patch_output_dataset = site_outputs.get(selected_site)
                if self._patch_stf_file(
                    stf_file,
                    patch_status,
                    panda_task_id,
                    reason=reason,
                    run_number=run_number,
                    execution_id=execution_id,
                    extra_metadata=patch_metadata,
                    output_dataset=patch_output_dataset,
                ):
                    failed += 1
            if unmatched:
                refreshed_stf_files = [
                    f for f in self._monitor_stf_files_for_run(run_number, status="processing", execution_id=execution_id)
                    if self._recoverable_by_this_agent(f, execution_id=execution_id, panda_task_id=panda_task_id)
                ]
                unfinished = [
                    f for f in refreshed_stf_files
                    if f.get("status") in active_statuses
                ]
                unmatched = [
                    f for f in unfinished
                    if f.get("file_id") not in matched_file_ids
                ]

        self.processing_stats["total_processed"] += processed
        self.processing_stats["failed_count"] += failed
        complete = is_task_terminal and not unfinished
        target = f"task_id={panda_task_id}"
        if site_name:
            target += f", site={site_name}"
        if input_dataset:
            target += f", input_dataset={input_dataset}"
        self.logger.info(
            f"PanDA polling updated STF files for run {run_number} ({target}): "
            f"processed={processed}, failed={failed}, task_status={task_status}, "
            f"jobs_seen={len(job_records)}, unfinished={len(unfinished)}, unmatched={len(unmatched)}",
            extra=self._log_extra(run_id=run_number, panda_task_id=panda_task_id)
        )
        return {
            "processed": processed,
            "failed": failed,
            "task_status": task_status,
            "jobs_seen": len(job_records),
            "unfinished": len(unfinished),
            "unmatched": len(unmatched),
            "complete": complete,
        }


    def start_processed_stf_polling(
        self,
        run_number,
        panda_task_id=None,
        execution_id=None,
        site_name=None,
        input_dataset=None,
        decision_box_enabled=None,
    ):
        """Add a run/task to the polling scheduler."""
        if not panda_task_id:
            self.logger.warning(
                f"Not registering PanDA polling for run {run_number}: missing PanDA task ID",
                extra=self._log_extra(run_id=run_number, execution_id=execution_id)
            )
            return False
        run_key = str(run_number)
        poll_key = (run_key, str(panda_task_id), execution_id)
        with self.polling_lock:
            if poll_key in self.polling_tasks:
                self.logger.info(
                    f"PanDA polling already active for run {run_key}, task_id={panda_task_id}",
                    extra=self._log_extra(run_id=run_key, panda_task_id=panda_task_id, execution_id=execution_id)
                )
                return False
            self.polling_tasks[poll_key] = {
                "run_number": run_key,
                "panda_task_id": panda_task_id,
                "execution_id": execution_id,
                "site_name": site_name,
                "input_dataset": input_dataset,
                "decision_box_enabled": decision_box_enabled,
                "started_at": time.time(),
                "last_poll": 0,
            }
            self._ensure_polling_scheduler_locked()
        target = f"task_id={panda_task_id}"
        if site_name:
            target += f", site={site_name}"
        if input_dataset:
            target += f", input_dataset={input_dataset}"
        self.logger.info(
            f"Registered PanDA polling for run {run_key} ({target})",
            extra=self._log_extra(run_id=run_key, panda_task_id=panda_task_id, execution_id=execution_id)
        )
        return True


    def _ensure_polling_scheduler_locked(self):
        """Start the scheduler thread if no live one exists."""
        if self.polling_thread and self.polling_thread.is_alive():
            return
        self.polling_stop_event.clear()
        self.polling_thread = threading.Thread(
            target=self._polling_scheduler_loop,
            name="panda-poll-scheduler",
            daemon=True,
        )
        self.polling_thread.start()


    def _polling_scheduler_loop(self):
        """Poll registered run/task entries until all are complete or stopped."""
        interval_seconds = self.panda_poll_interval_seconds
        timeout_seconds = self.panda_poll_timeout_seconds
        while not self.polling_stop_event.is_set():
            with self.polling_lock:
                tasks = list(self.polling_tasks.items())
            if not tasks:
                return

            now = time.time()
            for poll_key, task in tasks:
                if now - task.get("last_poll", 0) < interval_seconds:
                    continue
                task["last_poll"] = now
                try:
                    result = self.poll_processed_stf_files_once(
                        task["run_number"],
                        task.get("panda_task_id"),
                        execution_id=task.get("execution_id"),
                        site_name=task.get("site_name"),
                        input_dataset=task.get("input_dataset"),
                        decision_box_enabled=task.get("decision_box_enabled"),
                    )
                    timed_out = timeout_seconds > 0 and now - task.get("started_at", now) > timeout_seconds
                    if result.get("complete") or timed_out:
                        with self.polling_lock:
                            self.polling_tasks.pop(poll_key, None)
                            still_polling_run = any(
                                remaining_task.get("run_number") == task["run_number"]
                                for remaining_task in self.polling_tasks.values()
                            )
                        if not still_polling_run:
                            self.active_processing.pop(task["run_number"], None)
                        if timed_out and not result.get("complete"):
                            self.logger.warning(
                                f"PanDA polling timed out for run {task['run_number']}, task_id={task.get('panda_task_id')}",
                                extra=self._log_extra(
                                    run_id=task["run_number"],
                                    panda_task_id=task.get("panda_task_id"),
                                    execution_id=task.get("execution_id")
                                )
                            )
                except Exception as e:
                    self.logger.error(
                        f"PanDA polling failed for run {task['run_number']}, task_id={task.get('panda_task_id')}: {e}",
                        extra=self._log_extra(
                            run_id=task["run_number"],
                            panda_task_id=task.get("panda_task_id"),
                            execution_id=task.get("execution_id")
                        )
                    )
            self.polling_stop_event.wait(1)


    def stop_processed_stf_polling(self, wait_seconds=5):
        """Stop the scheduler thread during agent shutdown."""
        self.polling_stop_event.set()
        thread = self.polling_thread
        if thread and thread.is_alive():
            thread.join(timeout=wait_seconds)
        with self.polling_lock:
            self.polling_tasks.clear()
        return True


    def recover_active_panda_polling(self):
        """Restart polling for processing STF rows left by an earlier agent."""
        stf_files = self._monitor_stf_files()
        runs_to_poll = {}
        recovered_task_context = {}
        for stf_file in stf_files:
            if stf_file.get("status") != "processing":
                continue
            metadata = stf_file.get("metadata") or {}
            execution_id = metadata.get("workflow_execution_id")
            if not execution_id:
                continue
            run_number = self._monitor_run_number_by_id(stf_file.get("run"))
            site_task_ids = metadata.get("panda_site_task_ids") or {}
            site_input_datasets = metadata.get("panda_site_input_datasets") or {}
            panda_task_ids = [task_id for task_id in site_task_ids.values() if task_id]
            if metadata.get("panda_task_id"):
                panda_task_ids.append(metadata.get("panda_task_id"))
            for site_name, task_id in site_task_ids.items():
                if task_id:
                    recovered_task_context[str(task_id)] = {
                        "site_name": site_name,
                        "input_dataset": site_input_datasets.get(site_name),
                        "decision_box_enabled": True,
                    }
            for panda_task_id in {str(task_id) for task_id in panda_task_ids if task_id}:
                if not self._recoverable_by_this_agent(stf_file, execution_id=execution_id, panda_task_id=panda_task_id):
                    continue
                runs_to_poll.setdefault((run_number, panda_task_id, execution_id), 0)
                runs_to_poll[(run_number, panda_task_id, execution_id)] += 1

        for (run_number, panda_task_id, execution_id), count in runs_to_poll.items():
            task_context = recovered_task_context.get(str(panda_task_id), {})
            self.logger.info(
                f"Recovering PanDA polling for run {run_number}: task_id={panda_task_id}, "
                f"site={task_context.get('site_name') or '-'}, execution_id={execution_id}, stf_files={count}",
                extra=self._log_extra(run_id=run_number, panda_task_id=panda_task_id, execution_id=execution_id)
            )
            self.start_processed_stf_polling(
                run_number,
                panda_task_id,
                execution_id=execution_id,
                site_name=task_context.get("site_name"),
                input_dataset=task_context.get("input_dataset"),
                decision_box_enabled=task_context.get("decision_box_enabled", False),
            )

        return len(runs_to_poll)


    def run(self):
        """Recover unfinished polling state before entering the normal MQ loop."""
        try:
            recovered = self.recover_active_panda_polling()
            self.logger.info(
                f"Recovered {recovered} active PanDA polling run(s)",
                extra=self._log_extra()
            )
        except Exception as e:
            self.logger.warning(
                f"Failed to recover active PanDA polling state: {e}",
                extra=self._log_extra()
            )
        try:
            return super().run()
        finally:
            self.stop_processed_stf_polling()


    # ---
    def on_message(self, msg):
        """
        Handles incoming messages.
        """

        try:
            message_data = json.loads(msg.body)

            # Capture execution and run IDs if provided, preserving existing context
            exec_id = message_data.get("execution_id")
            if exec_id:
                self.current_execution_id = exec_id

            run_id = message_data.get("run_id")
            if run_id:
                self.current_run_id = run_id

            msg_type = message_data.get("msg_type")
            msg_namespace = message_data.get("namespace")
             
            if msg_namespace == self.namespace:
                if msg_type == 'stf_ready':
                    if self.background_stf_ready:
                        run_key = str(message_data.get("run_id") or "unknown")
                        site_key = str(message_data.get("site") or "all-sites")
                        self.run_in_background(
                            self.handle_data_ready,
                            dict(message_data),
                            label=f"stf_ready run={run_key} site={site_key}",
                        )
                    else:
                        self.handle_data_ready(message_data)
                elif msg_type == 'stf_gen':
                    self.handle_stf_gen(message_data)
                elif msg_type == 'run_imminent':
                    self.handle_run_imminent(message_data)
                elif msg_type == 'start_run':
                    self.handle_start_run(message_data)
                elif msg_type == 'end_run':
                    self.handle_end_run(message_data)
                else:
                    print("Ignoring unknown message type", msg_type)
            else:
                print("Ignoring other namespaces ", msg_namespace)
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}")


    # ---
    def handle_data_ready(self, message_data):
        """Serialize data_ready handling while keeping MQ callbacks responsive."""
        with self.data_ready_lock:
            return self._handle_data_ready(message_data)


    def _handle_data_ready(self, message_data):
        """Handle data_ready message"""
        
        run_id = message_data.get('run_id')
        
        print(f"*** MQ: data ready for run {run_id} ***")
        
        self.run_id = str(run_id)
        self.name_current_datasets()
        username = os.getenv('PANDA_NICKNAME', os.getenv('USER', 'unknown'))
        decision_box_enabled = self._decision_box_enabled_for_message(message_data, run_id=self.run_id)
        non_decision_box_site = self._non_decision_box_site_for_message(message_data, run_id=self.run_id)

        if decision_box_enabled:
            task_info = self.active_processing.get(self.run_id) or self.panda_status.get(self.run_id) or {}
            site_tasks = dict(task_info.get("site_tasks") or {})
            requested_site = message_data.get("site")
            requested_sites = [requested_site] if requested_site else list(self.decision_box_sites)
            primary_task_id = task_info.get("task_id")
            primary_status = task_info.get("status")
            primary_msg = task_info.get("message")

            for site_name in requested_sites:
                if site_name not in self.decision_box_sites:
                    self.logger.warning(
                        f"Ignoring stf_ready for unknown decision-box site {site_name}",
                        extra=self._log_extra(run_id=self.run_id, execution_id=message_data.get("execution_id"))
                    )
                    continue
                force_resubmit = self._message_bool(message_data, "force_resubmit", False)
                if not force_resubmit and site_name in site_tasks and site_tasks[site_name].get("task_id"):
                    self.logger.info(
                        f"PanDA task for {site_name} already exists for run {self.run_id}; skipping duplicate stf_ready",
                        extra=self._log_extra(run_id=self.run_id, panda_task_id=site_tasks[site_name].get("task_id"))
                    )
                    continue
                input_dataset = message_data.get("input_dataset") or self._input_dataset_did_for_site(self.run_id, site_name)
                output_dataset = self._output_dataset_did_for_site(
                    self.run_id,
                    site_name,
                    output_suffix=message_data.get("output_suffix"),
                )
                prun_args = [
                "--exec", "./payload.sh",
                "--inDS", input_dataset,
                "--outDS", output_dataset,
                "--nJobs", "1",
                "--vo", "epic",
                "--site", site_name,
                "--prodSourceLabel", "test",
                "--workingGroup", "EIC",
                "--noBuild",
                "--expertOnly_skipScout",
                "--outputs", "myout.txt"
                ]
                try:
                    params = self._build_prun_params(prun_args, self.run_id, site_name)
                except Exception as e:
                    print(f"PRUN CRITICAL for site {site_name}: - {str(e)}")
                    site_tasks[site_name] = {
                        "site": site_name,
                        "task_id": None,
                        "status": 1,
                        "message": f"PRUN parameter build failed: {e}",
                        "input_dataset": input_dataset,
                        "output_dataset": output_dataset,
                    }
                    if primary_status is None:
                        primary_status = 1
                        primary_msg = site_tasks[site_name]["message"]
                    continue

                params['runUntilClosed'] = True
                params['processingType'] = "stfprocessing"
                params['nFilesPerJob'] = 1
                params['nChunksToWait'] = 1

                status, msg = self.panda_submit_task(params)
                panda_task_id = self._extract_panda_task_id(msg)
                site_tasks[site_name] = {
                    "site": site_name,
                    "task_id": panda_task_id,
                    "status": status,
                    "message": msg,
                    "input_dataset": input_dataset,
                    "output_dataset": output_dataset,
                }
                if primary_task_id is None:
                    primary_task_id = panda_task_id
                    primary_status = status
                    primary_msg = msg
                if status == 0 and panda_task_id:
                    self.start_processed_stf_polling(
                        self.run_id,
                        panda_task_id,
                        execution_id=message_data.get("execution_id"),
                        site_name=site_name,
                        input_dataset=input_dataset,
                        decision_box_enabled=True,
                    )
                else:
                    self.logger.error(
                        f"PanDA task submission for {site_name} did not return a usable task ID. status:{status}, message:{msg}",
                        extra=self._log_extra(run_id=self.run_id)
                    )

            self.panda_status[self.run_id] = {
                'status': primary_status,
                'message': primary_msg,
                'task_id': primary_task_id,
                'site_tasks': site_tasks,
                "decision_box_enabled": True,
                "non_decision_box_site": non_decision_box_site,
            }
            self.active_processing[self.run_id] = {
                "task_id": primary_task_id,
                "site_tasks": site_tasks,
                "started_at": datetime.now(),
                "input_dataset": self._run_dataset_did(self.run_id),
                "site_input_datasets": {site: info["input_dataset"] for site, info in site_tasks.items()},
                "site_output_datasets": {site: info["output_dataset"] for site, info in site_tasks.items()},
                "execution_id": message_data.get("execution_id"),
                "decision_box_enabled": True,
                "non_decision_box_site": non_decision_box_site,
            }
            decided = 0
            marked = 0
            for stf_file in self._monitor_stf_files_for_run(self.run_id):
                filename = stf_file.get("stf_filename")
                if not filename:
                    continue
                decision = self._decision_from_stf_file(self.run_id, stf_file)
                if decision:
                    decided += 1
                    marked += self.mark_stf_processing_for_decision(
                        filename,
                        self.run_id,
                        decision,
                        site_tasks,
                        execution_id=message_data.get("execution_id"),
                    )
            self.logger.info(
                f"Decision-box PanDA tasks submitted for run {self.run_id}: {site_tasks}; "
                f"read {decided} existing data-agent decisions and marked {marked} site-task claims",
                extra=self._log_extra(run_id=self.run_id, panda_task_id=primary_task_id)
            )
            return None

        #  Construct the full list of arguments for PrunScript.main
        prun_args = [
        "--exec", "./payload.sh",
        "--inDS",   f"group.daq:{self.inDS}",
        "--outDS",  f"user.{username}.{self.outDS}",
        "--nJobs", "1",
        "--vo", "epic",
        "--site", non_decision_box_site,
        "--prodSourceLabel", "test",
        "--workingGroup", "EIC",
        "--noBuild",
        "--expertOnly_skipScout",
        "--outputs", "myout.txt"
        ]
        #  Call PrunScript.main to get the task parameters dictionary
        try:
            params = self._build_prun_params(prun_args, self.run_id, non_decision_box_site)
        except Exception as e:
            print(f"PRUN CRITICAL: - {str(e)}")
            return None

        # to process input files as they are added to the dataset
        params['runUntilClosed'] = True
        params['processingType'] = "stfprocessing"

        status, msg = self.panda_submit_task(params)
        panda_task_id = self._extract_panda_task_id(msg)
        self.panda_status[self.run_id] = {
            'status': status,
            'message': msg,
            'task_id': panda_task_id,
            "decision_box_enabled": False,
            "non_decision_box_site": non_decision_box_site,
        }
        if status != 0 or not panda_task_id:
            self.logger.error(
                f"PanDA task submission did not return a usable task ID. status:{status}, message:{msg}",
                extra=self._log_extra(run_id=self.run_id)
            )
            return None
        self.active_processing[self.run_id] = {
            "task_id": panda_task_id,
            "started_at": datetime.now(),
            "input_dataset": f"group.daq:{self.inDS}",
            "output_dataset": f"user.{username}.{self.outDS}",
            "execution_id": message_data.get("execution_id"),
            "decision_box_enabled": False,
            "non_decision_box_site": non_decision_box_site,
        }
        self.mark_run_stfs_processing(
            self.run_id,
            panda_task_id,
            execution_id=message_data.get("execution_id"),
            decision_box_enabled=False,
        )
        self.start_processed_stf_polling(
            self.run_id,
            panda_task_id,
            execution_id=message_data.get("execution_id"),
            decision_box_enabled=False,
        )

        self.logger.info(
            f"New task submitted to PanDA. status:{status}, task_id:{panda_task_id}, message:{msg}",
            extra=self._log_extra(run_id=self.run_id, panda_task_id=panda_task_id)
        )

        return None


    # ---
    def handle_stf_gen(self, message_data):
        """Handle stf gen message"""
        fn = message_data.get('filename')
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        print(f"*** MQ: stf_gen {fn} ***")

        if run_id:
            task_info = self.active_processing.get(run_id) or self.panda_status.get(run_id) or {}
            if self._decision_box_enabled_for_message(message_data, run_id=run_id):
                execution_id = message_data.get("execution_id") or task_info.get("execution_id")
                decision = self._decision_from_filename(run_id, fn, execution_id=execution_id) if fn else None
                site_tasks = task_info.get("site_tasks") or {}
                if decision and site_tasks:
                    self.mark_stf_processing_for_decision(
                        fn,
                        run_id,
                        decision,
                        site_tasks,
                        execution_id=execution_id,
                    )
                return
            panda_task_id = task_info.get("task_id")
            if panda_task_id and fn:
                self.mark_stf_processing_by_filename(
                    fn,
                    run_id,
                    panda_task_id,
                    execution_id=message_data.get("execution_id") or task_info.get("execution_id")
                )


    # ---
    def handle_run_imminent(self, message_data):
        """Handle run imminent message"""
        run_id = message_data.get('run_id')
        print(f"*** MQ: run_imminent {run_id} ***")

        self.logger.info(
            "Processing run_imminent message",
            extra=self._log_extra(simulation_tick=message_data.get('simulation_tick'))
        )
        
        # Report agent status for run preparation
        self.report_agent_status('OK', f'Preparing for run {run_id}')

        # TODO: Initialize processing resources for this run
        
        # Simulate preparation
        self.logger.info("Prepared processing resources for run", extra=self._log_extra())
    

    # ---
    def handle_start_run(self, message_data):
        """Handle start_run message"""
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: start_run message for run_id: {run_id} ***")

        # Agent is now actively processing this run
        # self.set_processing()

        # Send enhanced heartbeat with run context
        self.send_processing_agent_heartbeat()

        # TODO: Start monitoring for stf_ready messages
        self.logger.info("Ready to process data for run", extra=self._log_extra())


    # ---
    def handle_end_run(self, message_data):
        """Handle end_run message"""
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: end_run message for run_id: {run_id} ***")

        if run_id is None:
            self.logger.warning(
                "Ignoring end_run message without run_id",
                extra=self._log_extra(execution_id=message_data.get("execution_id"))
            )
            return

        run_key = str(run_id)
        task_info = self.active_processing.get(run_key) or self.panda_status.get(run_key) or {}
        decision_box_enabled = self._decision_box_enabled_for_message(message_data, run_id=run_key)
        if decision_box_enabled and task_info.get("site_tasks"):
            for site_name, site_task in task_info.get("site_tasks", {}).items():
                self.start_processed_stf_polling(
                    run_key,
                    site_task.get("task_id"),
                    execution_id=message_data.get("execution_id") or task_info.get("execution_id"),
                    site_name=site_task.get("site") or site_name,
                    input_dataset=site_task.get("input_dataset"),
                    decision_box_enabled=True,
                )
            return
        self.start_processed_stf_polling(
            run_key,
            task_info.get("task_id"),
            execution_id=message_data.get("execution_id") or task_info.get("execution_id"),
            decision_box_enabled=False,
        )
        

    def send_processing_agent_heartbeat(self):
        """Send enhanced heartbeat with processing agent context."""
        workflow_metadata = {
            'active_tasks': len(self.active_processing),
            'completed_tasks': self.processing_stats['total_processed'],
            'failed_tasks': self.processing_stats['failed_count']
        }

        return self.send_enhanced_heartbeat(workflow_metadata)


if __name__ == "__main__":
    import  argparse, shutil
    from    pathlib import Path

    # Example of inputDS for the static test: group.daq:swf.101871.run

    # Get the absolute path of the current file
    current_path = Path(__file__).resolve()

    # Get the directory above one containing the current file
    top_directory = current_path.parent.parent
   
    # pandaclient expects to work in workdir so tarball is not too big for pandacache
    workdir = top_directory / "workdir"
    workdir.mkdir(exist_ok=True)
    os.chdir(workdir)

    # The default script path; note that any script will be copied to "payload.sh" and only then executed.
    default_script  = str(top_directory / 'scripts' / 'dummy_stf_processing.sh')

    # Fix the peculiarity of the path in the testbed environment
    if '/direct/eic+u' in default_script: default_script = default_script.replace('/direct/eic+u', '/eic/u')

    # Copy the payload script from source path to current directory
    shutil.copy(default_script, './payload.sh')

    # ---
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose",  action='store_true',    help="Verbose mode")
    parser.add_argument("-t", "--test",     action='store_true',    help="Test mode")
    parser.add_argument("-i", "--inDS",     type=str,               help='Input dataset (if testing standalone)',  default='')
    parser.add_argument("-o", "--outDS",    type=str,               help='Output dataset (if testing standalone)', default='user.potekhin.test1')
    parser.add_argument("-s", "--script",   type=str,               help='Payload script', default=default_script)

    args        = parser.parse_args()
    verbose     = args.verbose
    test        = args.test
    inDS        = args.inDS
    outDS       = args.outDS
    script      = args.script

    if verbose:
        print(f'''*** {'Verbose mode            ':<20} {verbose:>25} ***''')
        print(f'''*** {'Test mode               ':<20} {test:>25} ***''')
        if inDS == '':
            print("*** No input dataset provided, test mode is dynamic, using upstream data ***")
        else:
            print(f'''*** {'inDS (for static testing)     ':<20} {inDS:>25} ***''')

        print(f"*** Top directory:    {top_directory} ***")
        print(f"*** Test script path: {script} ***")

    processing = PROCESSING(verbose=verbose, test=test)

    if inDS != '': # Static test mode, with a provided input dataset
        if verbose: print(f'''*** Running in the static test mode with inDS: {inDS}, outDS: {outDS} ***''')
        processing.test_panda(inDS, outDS, "myout.txt")
        exit(0)

    processing.run()
