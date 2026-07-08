import os, time, json, re, threading
from datetime import datetime
from pandaclient import PrunScript, panda_api
from pandaclient.Client import getTaskStatus, getPandaIDsWithTaskID, getFullJobStatus
from swf_common_lib.base_agent import BaseAgent

#################################################################################
class PROCESSING(BaseAgent):
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

        if self.verbose: print(f'''*** Initialized the PROCESSING class, test mode is {self.test} ***''')


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
            params = PrunScript.main(True, prun_args)
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


    def _monitor_stf_files_for_run(self, run_number):
        monitor_run_id = self._monitor_run_id(run_number)
        files = self._api_records(self.call_monitor_api("GET", "/stf-files/"))
        if monitor_run_id is None:
            return [f for f in files if str(f.get("run")) == str(run_number)]
        return [f for f in files if str(f.get("run")) == str(monitor_run_id)]


    def _monitor_stf_file_by_filename(self, filename):
        files = self._api_records(self.call_monitor_api("GET", "/stf-files/"))
        for stf_file in files:
            if stf_file.get("stf_filename") == filename:
                return stf_file
        return None


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
        if execution_id and metadata.get("workflow_execution_id") != execution_id:
            return False
        if panda_task_id and str(metadata.get("panda_task_id")) != str(panda_task_id):
            return False
        return True


    def _recoverable_by_this_agent(self, stf_file, execution_id=None, panda_task_id=None):
        metadata = stf_file.get("metadata") or {}
        if metadata.get("panda_tracking_namespace") != self.namespace:
            return False
        if execution_id and metadata.get("workflow_execution_id") != execution_id:
            return False
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
        if row_execution_id and execution_id and row_execution_id != execution_id:
            return False
        if not tracking_agent and not tracking_namespace:
            return allow_unclaimed or (execution_id is not None and row_execution_id == execution_id)
        if tracking_namespace == self.namespace and execution_id and row_execution_id == execution_id:
            return True
        return self._tracked_by_this_agent(stf_file, execution_id=execution_id)


    def _needs_processing_claim(self, stf_file, panda_task_id=None, execution_id=None):
        """Return True when the monitor row needs a processing claim PATCH."""
        metadata = stf_file.get("metadata") or {}

        if stf_file.get("status") != "processing":
            return True
        if metadata.get("panda_tracking_agent") != self.agent_name:
            return True
        if metadata.get("panda_tracking_namespace") != self.namespace:
            return True
        if execution_id and metadata.get("workflow_execution_id") != execution_id:
            return True
        if panda_task_id and str(metadata.get("panda_task_id")) != str(panda_task_id):
            return True
        return False


    def _patch_stf_file(self, stf_file, status, panda_task_id=None, matched_input_files=None, reason=None, run_number=None, execution_id=None, extra_metadata=None):
        metadata = stf_file.get("metadata") or {}
        metadata.update({
            "processed_by": self.agent_name,
            "panda_tracking_agent": self.agent_name,
            "panda_tracking_namespace": self.namespace,
            "panda_task_id": panda_task_id,
            "panda_output_dataset": self._output_dataset_did(run_number or stf_file.get("run")),
            "panda_polled_at": datetime.now().isoformat(),
        })
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


    def mark_run_stfs_processing(self, run_number, panda_task_id=None, execution_id=None):
        """Claim all eligible monitor STF rows for this run/task."""
        if not panda_task_id:
            self.logger.warning(
                f"Not marking STF files processing for run {run_number}: missing PanDA task ID",
                extra=self._log_extra(run_id=run_number, execution_id=execution_id)
            )
            return 0
        updated = 0
        for stf_file in self._monitor_stf_files_for_run(run_number):
            if stf_file.get("status") not in {"registered", "processing"}:
                continue
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


    def mark_stf_processing_by_filename(self, filename, run_number, panda_task_id=None, execution_id=None):
        """Claim one STF row when its stf_gen message arrives."""
        if not execution_id:
            return False
        stf_file = self._monitor_stf_file_by_filename(filename)
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
            execution_id=execution_id
        ))


    def poll_processed_stf_files_once(self, run_number, panda_task_id=None, execution_id=None):
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

        # Each poll re-scans the run so late-registered STF rows are claimed.
        self.mark_run_stfs_processing(run_number, panda_task_id, execution_id=execution_id)

        stf_files = [
            f for f in self._monitor_stf_files_for_run(run_number)
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
                if self._patch_stf_file(
                    stf_file,
                    "processed",
                    panda_task_id,
                    sorted(job.get("input_files", [])),
                    run_number=run_number,
                    execution_id=execution_id,
                    extra_metadata={
                        "panda_job_id": job.get("panda_id"),
                        "panda_job_status": job.get("status"),
                        "matched_input_files": sorted(job.get("input_files", [])),
                    },
                ):
                    processed += 1
            elif failed_jobs and all(job.get("status") in job_failure for job in matching_jobs):
                job = failed_jobs[-1]
                if self._patch_stf_file(
                    stf_file,
                    "failed",
                    panda_task_id,
                    reason=f"panda job {job.get('panda_id')} {job.get('status')}",
                    run_number=run_number,
                    execution_id=execution_id,
                    extra_metadata={
                        "panda_job_id": job.get("panda_id"),
                        "panda_job_status": job.get("status"),
                        "matched_input_files": sorted(job.get("input_files", [])),
                    },
                ):
                    failed += 1

        is_task_terminal = task_status in task_terminal
        refreshed_stf_files = [
            f for f in self._monitor_stf_files_for_run(run_number)
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
                if self._patch_stf_file(
                    stf_file,
                    "failed",
                    panda_task_id,
                    reason=f"no PanDA job found before task became {task_status}",
                    run_number=run_number,
                    execution_id=execution_id,
                ):
                    failed += 1
            if unmatched:
                refreshed_stf_files = [
                    f for f in self._monitor_stf_files_for_run(run_number)
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
        self.logger.info(
            f"PanDA polling updated STF files for run {run_number}: processed={processed}, failed={failed}, "
            f"task_status={task_status}, jobs_seen={len(job_records)}, unfinished={len(unfinished)}, unmatched={len(unmatched)}",
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


    def start_processed_stf_polling(self, run_number, panda_task_id=None, execution_id=None):
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
                    f"PanDA polling already active for run {run_key}",
                    extra=self._log_extra(run_id=run_key, panda_task_id=panda_task_id, execution_id=execution_id)
                )
                return False
            self.polling_tasks[poll_key] = {
                "run_number": run_key,
                "panda_task_id": panda_task_id,
                "execution_id": execution_id,
                "started_at": time.time(),
                "last_poll": 0,
            }
            self._ensure_polling_scheduler_locked()
        self.logger.info(
            f"Registered PanDA polling for run {run_key}",
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
        interval_seconds = int(os.getenv("SWF_PANDA_POLL_INTERVAL", "30"))
        timeout_seconds = int(os.getenv("SWF_PANDA_POLL_TIMEOUT", "0"))
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
                    )
                    timed_out = timeout_seconds > 0 and now - task.get("started_at", now) > timeout_seconds
                    if result.get("complete") or timed_out:
                        self.active_processing.pop(task["run_number"], None)
                        with self.polling_lock:
                            self.polling_tasks.pop(poll_key, None)
                        if timed_out and not result.get("complete"):
                            self.logger.warning(
                                f"PanDA polling timed out for run {task['run_number']}",
                                extra=self._log_extra(
                                    run_id=task["run_number"],
                                    panda_task_id=task.get("panda_task_id"),
                                    execution_id=task.get("execution_id")
                                )
                            )
                except Exception as e:
                    self.logger.error(
                        f"PanDA polling failed for run {task['run_number']}: {e}",
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
        stf_files = self._api_records(self.call_monitor_api("GET", "/stf-files/"))
        runs_to_poll = {}
        for stf_file in stf_files:
            if stf_file.get("status") != "processing":
                continue
            metadata = stf_file.get("metadata") or {}
            execution_id = metadata.get("workflow_execution_id")
            if not execution_id:
                continue
            panda_task_id = metadata.get("panda_task_id")
            if not panda_task_id:
                continue
            if not self._recoverable_by_this_agent(stf_file, execution_id=execution_id, panda_task_id=panda_task_id):
                continue
            run_number = self._monitor_run_number_by_id(stf_file.get("run"))
            runs_to_poll.setdefault((run_number, str(panda_task_id), execution_id), 0)
            runs_to_poll[(run_number, str(panda_task_id), execution_id)] += 1

        for (run_number, panda_task_id, execution_id), count in runs_to_poll.items():
            self.logger.info(
                f"Recovering PanDA polling for run {run_number}: task_id={panda_task_id}, execution_id={execution_id}, stf_files={count}",
                extra=self._log_extra(run_id=run_number, panda_task_id=panda_task_id, execution_id=execution_id)
            )
            self.start_processed_stf_polling(run_number, panda_task_id, execution_id=execution_id)

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
        """Handle data_ready message"""
        
        run_id = message_data.get('run_id')
        
        print(f"*** MQ: data ready for run {run_id} ***")
        
        self.run_id = str(run_id)
        self.name_current_datasets()
        username = os.getenv('PANDA_NICKNAME', os.getenv('USER', 'unknown'))

        #  Construct the full list of arguments for PrunScript.main
        prun_args = [
        "--exec", "./payload.sh",
        "--inDS",   f"group.daq:{self.inDS}",
        "--outDS",  f"user.{username}.{self.outDS}",
        "--nJobs", "1",
        "--vo", "epic",
        "--site", "E1_BNL",
        "--prodSourceLabel", "test",
        "--workingGroup", "EIC",
        "--noBuild",
        "--expertOnly_skipScout",
        "--outputs", "myout.txt"
        ]
        #  Call PrunScript.main to get the task parameters dictionary
        try:
            params = PrunScript.main(True, prun_args)
        except Exception as e:
            print(f"PRUN CRITICAL: - {str(e)}")
            return None

        # to process input files as they are added to the dataset
        params['runUntilClosed'] = True
        params['processingType'] = "stfprocessing"

        status, msg = self.panda_submit_task(params)
        panda_task_id = self._extract_panda_task_id(msg)
        self.panda_status[self.run_id] = {'status': status, 'message': msg, 'task_id': panda_task_id}
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
        }
        self.mark_run_stfs_processing(self.run_id, panda_task_id, execution_id=message_data.get("execution_id"))
        self.start_processed_stf_polling(self.run_id, panda_task_id, execution_id=message_data.get("execution_id"))

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
        self.start_processed_stf_polling(
            run_key,
            task_info.get("task_id"),
            execution_id=message_data.get("execution_id") or task_info.get("execution_id")
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
    import  argparse, sys, shutil
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

    if top_directory not in sys.path:
        sys.path.append(str(top_directory))
        if verbose: print(f'''*** Added {top_directory} to sys.path ***''')
    else:
        if verbose: print(f'''*** {top_directory} is already in sys.path ***''')

    processing = PROCESSING(verbose=verbose, test=test)

    if inDS != '': # Static test mode, with a provided input dataset
        if verbose: print(f'''*** Running in the static test mode with inDS: {inDS}, outDS: {outDS} ***''')
        processing.test_panda(inDS, outDS, "myout.txt")
        exit(0)

    processing.run()
