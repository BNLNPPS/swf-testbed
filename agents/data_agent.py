# ###############################################################################
# The DATA class is the main data management class.
#
# It receives messages from the DAQ simulator and handles them.
#
# Main functionality is to create Rucio datasets and register files to
# these datasets. Then, to notify the processing agent that the data is ready.
# 
# It uses the mq_comms and rucio_comms packages for MQ and Rucio operations.
# Both packages are located in the swf-common repository.
#
# Datasets are created upon receiving the run_imminent message.
# Files are registered upon receiving the stf_gen message.
# The run_id and dataset name are extracted from the run_imminent message.
#
# The data folder and the Rucio scope and RSE are defined globally.
# The file is attached to the dataset after it is uploaded to Rucio.
# The file metadata is set upon registration.
# The file is registered under the provided Rucio scope.
# The dataset is created under the provided Rucio scope.
#
# Operations specific to XRootD upload mode are marked in the code.
#
# ###############################################################################

# Ad hoc settings for XRootD upload mode, reflecting the EIC storage setup
xrd_server = 'root://dcintdoor.sdcc.bnl.gov:1094/'
xrd_folder = '/pnfs/sdcc.bnl.gov/eic/epic/disk/swfdaqtest/'

# Generic imports
import os, time, json, threading
import requests, urllib3
import uuid
from datetime import datetime
from pathlib import Path

# Rucio imports
from rucio.client               import Client as RucioClient
from rucio.client.replicaclient import ReplicaClient
from rucio.client.didclient     import DIDClient
from rucio.client.uploadclient  import UploadClient
from rucio.common.exception     import DataIdentifierAlreadyExists, RSENotFound

# Common lib imports – prefer the packaged rucio_utils; fall back to legacy rucio_comms
_USE_RUCIO_UTILS = False
try:
    from swf_common_lib.rucio_utils import (
        calculate_adler32_from_file, register_file_on_rse,
        create_dataset, add_files_to_dataset,
    )
    _USE_RUCIO_UTILS = True
except ModuleNotFoundError as e:  # Deprecated: legacy rucio_comms imports, to be removed in a future version
    if e.name not in {"swf_common_lib", "swf_common_lib.rucio_utils"}:
        raise
    from rucio_comms.utils          import calculate_adler32_from_file, register_file_on_rse
    print('*** Imported rucio helpers from rucio_comms.utils (legacy fallback) ***')
from swf_common_lib.base_agent import BaseAgent
from swf_common_lib.api_utils import ensure_namespace
try:
    from agent_config_helpers import DecisionDatasetNamingMixin, PromptProcessingConfigMixin
except ModuleNotFoundError as e:
    if e.name != "agent_config_helpers":
        raise
    from agents.agent_config_helpers import DecisionDatasetNamingMixin, PromptProcessingConfigMixin

from swf_testbed_decision_box.catalog import RucioDatasetCatalog
from swf_testbed_decision_box.monitor_metadata import metadata_with_execution_id
from swf_testbed_decision_box.models import FileDID, Site
from swf_testbed_decision_box.policy import build_policy
from swf_testbed_decision_box.service import DecisionBox

#################################################################################
class DATA(PromptProcessingConfigMixin, DecisionDatasetNamingMixin, BaseAgent):
    ''' The DATA class is the main data management class.
        It receives messages from the DAQ simulator and handles them.
        Main functionality is to create Rucio datasets, upload and register files to
        these datasets. Then, to notify the processing agent that the data is ready.
        Upload can be done either via Rucio or XRootD.
    '''

    def __init__(self,
                config_path:    str | None = None,
                verbose:        bool = False,
                mqxmit:         bool = True,
                xrdup:          bool = False,
                rucio_scope:    str  = '',
                data_folder:    str  = '',
                rse:            str  = ''):
        super().__init__(agent_type='DATA', subscription_queue='/topic/epictopic',
                         debug=verbose, config_path=config_path)
        ''' Initialize the DATA class.
            Parameters:
                verbose (bool): Verbose mode
                xrdup (bool): Use XRootD for upload instead of Rucio
                rucio_scope (str): Rucio scope to use for datasets and files; if empty, no Rucio operations will be performed
                data_folder (str): Folder where data files are located; if empty, no data will be uploaded
                rse (str): RSE to target for upload; if empty, no data will be uploaded
        '''
        self.verbose                = verbose
        self.mqxmit                 = mqxmit
        self.xrdup                  = xrdup

        self.rucio_client           = None
        self.rucio_upload_client    = None
        self.rucio_did_client       = None
        self.rucio_replica_client   = None
        self.fs                     = None # File system client, e.g. XRootD client
        
        self.file_manager           = None
        self.dataset_manager        = None

        self.rucio_scope            = rucio_scope
        self.data_folder            = data_folder    # if empty, no data will be uploaded
        self.run_id                 = None              # current run ID, to be set upon receiving the run_imminent message
        self.dataset                = ''                # current dataset name, to be set upon receiving the run_imminent message
        self.folder                 = ''                # the actual folder for the current run, to be accessed later
        self.rse                    = rse               # RSE to target for upload
        
        self.count                  = 0

        self.active_runs = {}   # Track active runs and their monitor IDs
        self.active_files = {}  # Track STF files being processed
        self.ready_sites_by_run = {}
        self.run_contexts = {}
        self.seen_stf_by_run = {}
        self.completed_stf_by_run = {}
        self.pending_start_by_run = {}
        self.pending_stf_by_run = {}
        self.run_conditions_by_run = {}
        self.data_work_lock = threading.Lock()
        self.pending_stf_condition = threading.Condition()

        prompt_config = self._load_prompt_processing_config()
        self.background_stf_gen = self._config_bool(
            prompt_config,
            "background_stf_gen",
            "SWF_DATA_BACKGROUND_STF_GEN",
            True,
        )
        self.data_end_run_wait_timeout_seconds = self._config_int(
            prompt_config,
            "data_end_run_wait_timeout_seconds",
            "SWF_DATA_END_RUN_WAIT_TIMEOUT",
            0,
        )
        self.decision_box_enabled = self._config_bool(
            prompt_config,
            "decision_box_enabled",
            "SWF_DECISION_BOX_ENABLED",
            False,
        )
        self.decision_box_policy = os.getenv(
            "SWF_DECISION_BOX_POLICY",
            str(prompt_config.get("decision_box_policy", "round-robin")),
        ).strip()
        self.decision_box_sites = self._config_list(
            prompt_config,
            "decision_box_sites",
            "SWF_DECISION_BOX_SITES",
            ["E1_BNL", "E1_JLAB"],
        )
        self.decision_box_rucio_scope = os.getenv(
            "SWF_DECISION_BOX_RUCIO_SCOPE",
            str(prompt_config.get("decision_box_rucio_scope", self.rucio_scope or "group.daq")),
        ).strip()
        self.decision_box_site_dataset_template = os.getenv(
            "SWF_DECISION_BOX_SITE_DATASET_TEMPLATE",
            str(prompt_config.get("decision_box_site_dataset_template", "")),
        ).strip() or None
        self.decision_box = None

        if self.rucio_scope == '':
            if self.verbose: print('*** No Rucio scope provided, Rucio operations will be skipped ***')
        else:
            if self.verbose: print(f'''*** Rucio scope is set to {self.rucio_scope}, Rucio operations will be performed ***''')
            self.init_rucio()

        if self.xrdup:
            if self.verbose: print('*** XRootD upload mode is enabled, will use XRootD for upload ***')
            from XRootD import client
            self.fs = client.FileSystem(xrd_server)
        else:
            if self.verbose: print('*** XRootD upload mode is disabled, will use Rucio for upload ***') 


        if self.verbose: print(f'''*** DATA class initialized. RSE: {self.rse} ***''')

        self.rse_is_deterministic = False
        if self.rse and self.rucio_client:
            self.rse_is_deterministic = self.rucio_client.get_rse(rse=self.rse)['deterministic']


    def _decision_box_context_for_run(self, run_id):
        return self._run_context(run_id)


    def _decision_box_for_message(self, message_data, run_id=None):
        if not self._decision_box_enabled_for_message(message_data, run_id=run_id):
            return None
        if self.decision_box is None:
            self.decision_box = self._build_decision_box(enabled=True)
        return self.decision_box


    def _build_decision_box(self, enabled=None):
        if not (self.decision_box_enabled if enabled is None else enabled):
            return None
        if self.rucio_client is None:
            raise RuntimeError("Decision box requires initialized Rucio; set rucio_scope for the data agent")
        sites = tuple(Site(site_name) for site_name in self.decision_box_sites)
        catalog = RucioDatasetCatalog(client=self.rucio_client, lifetime_days=7)
        return DecisionBox(
            catalog=catalog,
            sites=sites,
            manage_full_dataset=False,
            site_dataset_template=self.decision_box_site_dataset_template,
        )


    def _file_did_from_message(self, message_data):
        file_did = message_data.get("file_did") or message_data.get("did")
        filename = message_data.get("filename")
        if file_did:
            return FileDID.parse(file_did, default_scope=self.rucio_scope or self.decision_box_rucio_scope)
        if filename:
            return FileDID.parse(os.path.basename(filename), default_scope=self.rucio_scope or self.decision_box_rucio_scope)
        return None


    def _decision_policy_for_message(self, message_data):
        policy_name = message_data.get("decision_policy") or self.decision_box_policy
        selected_sites = message_data.get("decision_sites") or message_data.get("sites") or ""
        if isinstance(selected_sites, str):
            selected_site_objs = tuple(Site(site) for site in self._config_list({}, "sites", "__unused__", selected_sites))
        else:
            selected_site_objs = tuple(Site(str(site)) for site in selected_sites)
        if selected_site_objs and policy_name not in {"explicit", "both", "all"}:
            policy_name = "explicit"
        return build_policy(policy_name, selected_sites=selected_site_objs)


    def _decision_sites(self, run_number, decision):
        if not decision:
            return []
        sites = []
        for site_dataset in decision.site_datasets:
            site_name = self._site_name_for_dataset(run_number, site_dataset)
            if site_name:
                sites.append(site_name)
        return sites


    def _remember_seen_stf(self, run_id, filename):
        if run_id and filename:
            self.seen_stf_by_run.setdefault(str(run_id), set()).add(os.path.basename(str(filename)))


    def _remember_completed_stf(self, run_id, filename):
        if run_id and filename:
            self.completed_stf_by_run.setdefault(str(run_id), set()).add(os.path.basename(str(filename)))


    def _mark_pending_stf(self, run_id, filename):
        if not run_id or not filename:
            return False
        with self.pending_stf_condition:
            pending = self.pending_stf_by_run.setdefault(str(run_id), set())
            file_key = os.path.basename(str(filename))
            was_pending = file_key in pending
            pending.add(file_key)
            self.pending_stf_condition.notify_all()
            return not was_pending


    def _mark_done_stf(self, run_id, filename):
        if not run_id or not filename:
            return
        with self.pending_stf_condition:
            pending = self.pending_stf_by_run.get(str(run_id))
            if pending is not None:
                pending.discard(os.path.basename(str(filename)))
                if not pending:
                    self.pending_stf_by_run.pop(str(run_id), None)
            self.pending_stf_condition.notify_all()


    def _mark_pending_start(self, run_id):
        if not run_id:
            return
        with self.pending_stf_condition:
            run_key = str(run_id)
            self.pending_start_by_run[run_key] = self.pending_start_by_run.get(run_key, 0) + 1
            self.pending_stf_condition.notify_all()


    def _mark_done_start(self, run_id):
        if not run_id:
            return
        with self.pending_stf_condition:
            run_key = str(run_id)
            remaining = self.pending_start_by_run.get(run_key, 0) - 1
            if remaining > 0:
                self.pending_start_by_run[run_key] = remaining
            else:
                self.pending_start_by_run.pop(run_key, None)
            self.pending_stf_condition.notify_all()


    def _wait_for_pending_start(self, run_id, timeout_seconds=None):
        if not run_id:
            return True
        if timeout_seconds is None:
            timeout_seconds = self.data_end_run_wait_timeout_seconds
        deadline = time.time() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        with self.pending_stf_condition:
            while self.pending_start_by_run.get(str(run_id), 0) > 0:
                if deadline is None:
                    self.pending_stf_condition.wait(timeout=1.0)
                    continue
                remaining = deadline - time.time()
                if remaining <= 0:
                    self.logger.error(
                        f"Timed out waiting for start_run worker for run {run_id}",
                        extra=self._log_extra(run_id=run_id)
                    )
                    return False
                self.pending_stf_condition.wait(timeout=min(remaining, 1.0))
        return True


    def _wait_for_pending_stf(self, run_id, timeout_seconds=None):
        if not run_id:
            return True
        if timeout_seconds is None:
            timeout_seconds = self.data_end_run_wait_timeout_seconds
        deadline = time.time() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        with self.pending_stf_condition:
            while self.pending_stf_by_run.get(str(run_id)):
                if deadline is None:
                    self.pending_stf_condition.wait(timeout=1.0)
                    continue
                remaining = deadline - time.time()
                if remaining <= 0:
                    pending = sorted(self.pending_stf_by_run.get(str(run_id), set()))
                    self.logger.error(
                        f"Timed out waiting for pending STF workers for run {run_id}: {pending}",
                        extra=self._log_extra(run_id=run_id)
                    )
                    return False
                self.pending_stf_condition.wait(timeout=min(remaining, 1.0))
        return True


    def _run_context(self, run_id):
        return self.run_contexts.get(str(run_id), {})


    def _wait_for_run_context(self, run_id, timeout_seconds=None):
        if not run_id or self._run_context(run_id):
            return True
        if timeout_seconds is None:
            timeout_seconds = self.data_end_run_wait_timeout_seconds
        deadline = time.time() + timeout_seconds if timeout_seconds and timeout_seconds > 0 else None
        while True:
            if self._run_context(run_id):
                return True
            if deadline is not None and time.time() >= deadline:
                self.logger.error(
                    f"Timed out waiting for run context for run {run_id}",
                    extra=self._log_extra(run_id=run_id)
                )
                return False
            time.sleep(0.1)


    def _reconcile_local_stf_files(self, run_id, execution_id=None):
        """Process local STF files for this run that did not arrive over MQ."""
        context = self._run_context(run_id)
        folder = context.get("folder") or self.folder
        dataset = context.get("dataset") or self.dataset
        if not folder or not os.path.isdir(folder):
            return 0

        completed = self.completed_stf_by_run.setdefault(str(run_id), set())
        processed = 0
        for file_path in self._local_run_file_paths(folder):
            filename = os.path.basename(file_path)
            if filename in completed:
                continue
            self._remember_seen_stf(run_id, filename)
            message = {
                "msg_type": "stf_gen",
                "run_id": str(run_id),
                "filename": filename,
                "execution_id": execution_id or context.get("execution_id"),
                "sequence": self._sequence_from_filename(filename),
                "decision_sequence": self._decision_sequence_from_filename(filename),
                "state": "run",
                "substate": "physics",
                "decision_box_enabled": context.get("decision_box_enabled", self.decision_box_enabled),
            }
            if context.get("non_decision_box_site"):
                message["non_decision_box_site"] = context["non_decision_box_site"]
            previous_dataset, previous_folder, previous_run_id = self.dataset, self.folder, self.run_id
            try:
                self.dataset = dataset
                self.folder = folder
                self.run_id = str(run_id)
                if self._handle_stf_gen(message):
                    processed += 1
            finally:
                self.dataset, self.folder, self.run_id = previous_dataset, previous_folder, previous_run_id
        if processed:
            self.logger.info(
                f"Reconciled {processed} local STF file(s) for run {run_id}",
                extra=self._log_extra(run_id=run_id, execution_id=execution_id or context.get("execution_id"))
            )
        return processed


    def _sequence_from_filename(self, filename):
        numeric_parts = [
            part for part in os.path.basename(str(filename)).split(".")
            if part.isdigit()
        ]
        if not numeric_parts:
            return None
        try:
            return int(numeric_parts[-1])
        except ValueError:
            return None


    def _decision_sequence_from_filename(self, filename):
        sequence = self._sequence_from_filename(filename)
        if sequence is None:
            return None
        return max(sequence - 1, 0)


    def _local_run_file_paths(self, folder):
        """Return generated run files, regardless of STF payload extension."""
        paths = []
        for file_path in Path(folder).iterdir():
            if not file_path.is_file():
                continue
            if file_path.name.startswith(".") or file_path.name.endswith(".tmp"):
                continue
            paths.append(str(file_path))
        return sorted(paths)


    def _send_data_ready_message(
        self,
        site_name=None,
        input_dataset=None,
        execution_id=None,
        decision_box_enabled=None,
        non_decision_box_site=None,
    ):
        if not getattr(self, "mq_connected", False):
            self.logger.warning(
                "MQ is disconnected before stf_ready send; attempting reconnect",
                extra=self._log_extra(run_id=self.run_id)
            )
            if not self._attempt_reconnect():
                self.logger.error(
                    "Could not send stf_ready because MQ reconnect failed",
                    extra=self._log_extra(run_id=self.run_id)
                )
                return False

        self.send_message(
            '/topic/epictopic',
            self.mq_data_ready_message(
                site_name=site_name,
                input_dataset=input_dataset,
                execution_id=execution_id,
                decision_box_enabled=decision_box_enabled,
                non_decision_box_site=non_decision_box_site,
            ),
        )
        if not getattr(self, "mq_connected", False):
            self.logger.warning(
                "stf_ready send did not leave MQ connected; a later STF for this site can retry",
                extra=self._log_extra(run_id=self.run_id)
            )
            return False
        return True


    def apply_decision_for_stf(self, message_data):
        decision_box = self._decision_box_for_message(message_data, run_id=message_data.get("run_id") or self.run_id)
        if decision_box is None:
            return None
        file_did = self._file_did_from_message(message_data)
        if file_did is None:
            self.logger.warning(
                "Decision box skipped STF without filename/file DID",
                extra=self._log_extra(run_id=self.run_id, execution_id=message_data.get("execution_id"))
            )
            return None
        policy = self._decision_policy_for_message(message_data)
        decision = decision_box.decide_file(
            self._run_dataset_did(self.run_id),
            file_did,
            policy,
            message=message_data,
            run_conditions=self.run_conditions_by_run.get(str(self.run_id), {}),
            metadata={
                "agent_name": self.agent_name,
                "namespace": self.namespace,
            },
        )
        self.logger.info(
            f"Decision box assigned {decision.file_did} to {list(decision.site_datasets)}",
            extra=self._log_extra(run_id=self.run_id, execution_id=message_data.get("execution_id"))
        )
        return decision


    # ---
    def init_rucio(self):
        ''' Initialize the Rucio module.
        '''

        # A Rucio client will be needed for any operation with Rucio
        if self.verbose: print(f'''*** Instantiating the RucioClient and UploadClient ***''')
        try:
            self.rucio_client           = RucioClient()
            self.rucio_upload_client    = UploadClient(self.rucio_client)
            self.rucio_did_client       = DIDClient()
            self.rucio_replica_client   = ReplicaClient()
            
            if self.verbose: print(f'''*** Successfully instantiated the RucioClient, UploadClient, ReplicaClient and DIDClient***''')
        except Exception as e:
            print(f'*** Failed to instantiate the RucioClient, UploadClient and DIDClient: {e}, exiting... ***')
            exit(-1)

        if _USE_RUCIO_UTILS:
            # Using standalone functions from swf_common_lib.rucio_utils –
            # no DatasetManager / FileManager instances needed.
            return

        # Deprecated: fall back to legacy rucio_comms class-based managers
        from rucio_comms import DatasetManager, FileManager

        # A Dataset Manager will be needed for any operation with Rucio datasets
        if self.verbose: print(f'''*** Instantiating the Dataset Manager ***''')
        try:
            self.dataset_manager = DatasetManager()
            if self.verbose: print(f'''*** Successfully instantiated the Dataset Manager ***''')
        except Exception as e:
            print(f'*** Failed to instantiate the Dataset Manager: {e}, exiting... ***')
            exit(-1)

        # A File Manager will be needed to attach files to Rucio datasets
        if self.verbose: print(f'''*** Instantiating the File Manager ***''')
        try:
            self.file_manager = FileManager(rucio_client = self.rucio_client)
            if self.verbose: print(f'''*** Successfully instantiated the File Manager ***''')
        except Exception as e:
            print(f'*** Failed to instantiate the File Manager: {e}, exiting... ***')
            exit(-1)


    # ---
    def mq_data_ready_message(
        self,
        site_name=None,
        input_dataset=None,
        execution_id=None,
        decision_box_enabled=None,
        non_decision_box_site=None,
    ):
        '''
        Create a "data ready" message to be sent to MQ.
        '''
        
        msg = {}
       
        msg['namespace']    = self.namespace 
        msg['sender']       = self.agent_name 
        msg['req_id']       = 1
        msg['msg_type']     = 'stf_ready'
        msg['run_id']       = self.run_id
        if site_name:
            msg['site'] = site_name
        if input_dataset:
            msg['input_dataset'] = input_dataset
        if decision_box_enabled is not None:
            msg['decision_box_enabled'] = bool(decision_box_enabled)
        if non_decision_box_site:
            msg['non_decision_box_site'] = str(non_decision_box_site).strip()
        
        # Include execution_id if available to maintain workflow context
        execution_id = execution_id or getattr(self, 'current_execution_id', None)
        if execution_id:
            msg['execution_id'] = execution_id

        return msg
 

    # ---
    def on_message(self, msg):
        """
        Handles incoming DAQ messages (stf_gen, run_imminent, start_run, end_run).
        """

        try:
            message_data = json.loads(msg.body)
            
            # Capture execution_id if provided for logging and propagation
            exec_id = message_data.get('execution_id')
            if exec_id:         
                self.current_execution_id = exec_id

            msg_type = message_data.get('msg_type')
            msg_namespace = message_data.get('namespace')
            # Debug only: print(f'===================================> {msg_type}')
            
            if msg_namespace == self.namespace:
                if msg_type == 'stf_gen':
                    if self.background_stf_gen:
                        run_key = str(message_data.get("run_id") or "unknown")
                        file_key = str(message_data.get("filename") or "unknown")
                        self._remember_seen_stf(run_key, file_key)
                        marked_pending = self._mark_pending_stf(run_key, file_key)
                        enqueued = self.run_in_background(
                            self.handle_stf_gen,
                            dict(message_data),
                            dedup_key=f"data-stf-gen:{run_key}:{file_key}",
                            label=f"stf_gen run={run_key} file={file_key}",
                        )
                        if not enqueued and (
                            marked_pending or file_key in self.completed_stf_by_run.get(run_key, set())
                        ):
                            self._mark_done_stf(run_key, file_key)
                    else:
                        self.handle_stf_gen(message_data)
                elif msg_type == 'stf_ready':
                    self.handle_data_ready(message_data)
                elif msg_type == 'run_imminent':
                    if self.background_stf_gen:
                        run_key = str(message_data.get("run_id") or "unknown")
                        self.run_in_background(
                            self.handle_run_imminent,
                            dict(message_data),
                            dedup_key=f"data-run-imminent:{run_key}",
                            label=f"run_imminent run={run_key}",
                        )
                    else:
                        self.handle_run_imminent(message_data)
                elif msg_type == 'start_run':
                    if self.background_stf_gen:
                        run_key = str(message_data.get("run_id") or "unknown")
                        self._mark_pending_start(run_key)
                        enqueued = self.run_in_background(
                            self.handle_start_run,
                            dict(message_data),
                            dedup_key=f"data-start-run:{run_key}",
                            label=f"start_run run={run_key}",
                        )
                        if not enqueued:
                            self._mark_done_start(run_key)
                    else:
                        self.handle_start_run(message_data)
                elif msg_type == 'end_run':
                    if self.background_stf_gen:
                        run_key = str(message_data.get("run_id") or "unknown")
                        self.run_in_background(
                            self.handle_end_run,
                            dict(message_data),
                            dedup_key=f"data-end-run:{run_key}",
                            label=f"end_run run={run_key}",
                        )
                    else:
                        self.handle_end_run(message_data)
                else:
                    if self.verbose: print(f"*** Ignoring unknown message type {msg_type} ***")
            else:
                print("Ignoring other namespaces ", msg_namespace)
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}")


    # ---
    def handle_run_imminent(self, message_data):
        with self.data_work_lock:
            return self._handle_run_imminent(message_data)


    def _handle_run_imminent(self, message_data):
        """
        Handle run_imminent message - create dataset in Rucio.
        If using XRootD upload mode, the dataset folder is created here.
        """
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        run_conditions = message_data.get('run_conditions', {})
        
        if self.verbose: print(F'''*** MQ: run_imminent message for run {run_id}***''')

        self.logger.info("Processing run_imminent message",
                        extra=self._log_extra(simulation_tick=message_data.get('simulation_tick')))

        # Create run record in monitor
        monitor_run_id = self.create_run_record(run_id, run_conditions)
        if monitor_run_id is None:
            self.logger.error(
                f"Cannot start run {run_id}: monitor registration failed",
                extra=self._log_extra(
                    run_id=run_id,
                    execution_id=message_data.get("execution_id"),
                ),
            )
            return False
        self.run_conditions_by_run[str(run_id)] = dict(run_conditions or {})

        self.count = 0 # reset file counter for the new run
        self.ready_sites_by_run[str(run_id)] = set()
        decision_box_enabled = self._decision_box_enabled_for_message(message_data, run_id=run_id)
        non_decision_box_site = self._non_decision_box_site_for_message(message_data, run_id=run_id)
        
        self.run_id     = run_id
        self.dataset    = message_data.get('dataset')
        container       = message_data.get('container')
        if container:
            self.data_folder = container
        self.folder     = f"{self.data_folder}/{self.dataset}"
        self.run_contexts[str(run_id)] = {
            "run_id": str(run_id),
            "dataset": self.dataset,
            "folder": self.folder,
            "data_folder": self.data_folder,
            "execution_id": message_data.get("execution_id"),
            "decision_box_enabled": decision_box_enabled,
            "non_decision_box_site": non_decision_box_site,
        }

        if self.verbose: print(f'''*** Current dataset set to {self.dataset}, folder set to {self.folder} ***''')
        
        lifetime = 7 # days
        if _USE_RUCIO_UTILS:
            result = create_dataset(dataset_name=f'''{self.rucio_scope}:{self.dataset}''', lifetime_days=lifetime, open_dataset=True, client=self.rucio_client)
        else:  # Deprecated: legacy rucio_comms class-based managers
            result = self.dataset_manager.create_dataset(dataset_name=f'''{self.rucio_scope}:{self.dataset}''', lifetime_days=lifetime, open_dataset=True)
        if self.verbose: print(f'''*** Dataset {self.dataset}, creation result: {result} ***''')
        if not result:
            if self.verbose: print('*** Dataset creation failed, marking run failed... ***')
            self.logger.error(
                f"Dataset creation failed for run {run_id}",
                extra=self._log_extra(
                    run_id=run_id,
                    execution_id=message_data.get("execution_id"),
                ),
            )
            # Do not terminate the agent before closing the monitor run.
            # The end_run message may still arrive, but this guarantees that
            # a failed run cannot remain open if dataset creation is fatal.
            self.update_run_status(run_id, 'failed')
            return False
        else:
            if self.verbose: print(f'*** Dataset {result["scope"]}:{result["name"]} created successfully with DUID: {result["duid"]} ***')

        decision_box = self._decision_box_for_message(message_data, run_id=run_id)
        if decision_box is not None:
            try:
                site_datasets = decision_box.create_run(self._run_dataset_did(run_id))
                self.logger.info(
                    f"Decision box initialized site datasets for run {run_id}: {site_datasets}",
                    extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                )
            except Exception as e:
                self.logger.error(
                    f"Decision box failed to initialize site datasets for run {run_id}: {e}",
                    extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                )
                try:
                    decision_box.close_run(self._run_dataset_did(run_id))
                except Exception as cleanup_error:
                    self.logger.error(
                        f"Decision box cleanup failed for run {run_id}: {cleanup_error}",
                        extra=self._log_extra(
                            run_id=run_id,
                            execution_id=message_data.get("execution_id"),
                        ),
                    )
                try:
                    self.rucio_client.set_status(
                        scope=self.rucio_scope,
                        name=self.dataset,
                        open=False,
                    )
                except Exception as cleanup_error:
                    self.logger.error(
                        f"Failed to close full dataset after decision-box failure for run {run_id}: {cleanup_error}",
                        extra=self._log_extra(
                            run_id=run_id,
                            execution_id=message_data.get("execution_id"),
                        ),
                    )
                self.update_run_status(run_id, "failed")
                return False

        if self.xrdup: # XRootD upload
            if self.verbose: print(f'''*** XRootD upload mode is enabled, will create a folder for dataset {self.dataset} ***''')
            # Create the folder for the dataset using XRootD
            status, _ = self.fs.mkdir(f"{xrd_folder}/{self.dataset}")
            # FIXME: Check the status
            if self.verbose: print(f'''*** Created folder {xrd_folder}/{self.dataset} using XRootD ***''')


    # ---
    def handle_start_run(self, message_data):
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        try:
            if not self._wait_for_run_context(run_id):
                self.logger.error(
                    f"Deferring start_run for run {run_id}: run context was not ready",
                    extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                )
                return False
            with self.data_work_lock:
                return self._handle_start_run(message_data)
        finally:
            self._mark_done_start(run_id)


    def _handle_start_run(self, message_data):
        """Handle start_run message"""
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        self.count = 0 # reset file counter for the new run
        if self.verbose: print(f"*** MQ: start_run message for run_id: {run_id} ***")


    # ---
    def handle_end_run(self, message_data):
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        if not self._wait_for_run_context(run_id):
            self.logger.error(
                f"Deferring end_run for run {run_id}: run context was not ready",
                extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
            )
            return False
        if not self._wait_for_pending_start(run_id):
            self.logger.error(
                f"Deferring end_run for run {run_id}: start_run worker did not drain",
                extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
            )
            return False
        if not self._wait_for_pending_stf(run_id):
            self.logger.error(
                f"Deferring end_run for run {run_id}: pending STF workers did not drain",
                extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
            )
            return False
        with self.data_work_lock:
            return self._handle_end_run(message_data)


    def _handle_end_run(self, message_data):
        """Handle end_run message"""
        run_id = str(message_data.get('run_id')) if message_data.get('run_id') is not None else None
        if self.verbose: print(f"*** MQ: end_run message for run_id: {run_id} ***")

        run_status = 'completed'
        try:
            if run_id is not None:
                context = self._run_context(run_id)
                if context:
                    self.run_id = context.get("run_id") or self.run_id
                    self.dataset = context.get("dataset") or self.dataset
                    self.folder = context.get("folder") or self.folder
                    self.data_folder = context.get("data_folder") or self.data_folder
                self._reconcile_local_stf_files(
                    run_id, execution_id=message_data.get("execution_id")
                )

            try:
                self.rucio_client.set_status(
                    scope=self.rucio_scope,
                    name=self.dataset,
                    open=False  # Setting to False closes the dataset
                )
            except Exception as e:
                run_status = 'failed'
                self.logger.error(
                    f"Failed to close dataset {self.rucio_scope}:{self.dataset}: {e}",
                    extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                )
                return False

            decision_box = self._decision_box_for_message(message_data, run_id=run_id)
            if decision_box is not None:
                try:
                    closed_datasets = decision_box.close_run(self._run_dataset_did(run_id))
                    self.logger.info(
                        f"Decision box closed processing datasets for run {run_id}: {closed_datasets}",
                        extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                    )
                except Exception as e:
                    run_status = 'failed'
                    self.logger.error(
                        f"Decision box failed to close processing datasets for run {run_id}: {e}",
                        extra=self._log_extra(run_id=run_id, execution_id=message_data.get("execution_id"))
                    )
                    return False

            total_files = message_data.get('total_files', 0)
            self.logger.info(
                "Processing end_run message",
                extra=self._log_extra(
                    total_files=total_files,
                    simulation_tick=message_data.get('simulation_tick'),
                ),
            )
            if run_id in self.active_runs:
                self.active_runs[run_id]['total_files'] = total_files
        except Exception:
            run_status = 'failed'
            self.logger.exception(
                f"Unexpected error while handling end_run for run {run_id}",
                extra=self._log_extra(
                    run_id=run_id,
                    execution_id=message_data.get("execution_id"),
                ),
            )
            return False
        finally:
            # Every end_run must close the monitor Run row, even when Rucio
            # or decision-box cleanup fails.  Snapper uses this end_time to
            # decide whether the run is still active.
            if run_id in self.active_runs:
                self.update_run_status(run_id, run_status)

        return True


    # ---
    def handle_stf_gen(self, message_data):
        run_id = str(message_data.get('run_id') or self.run_id) if (message_data.get('run_id') or self.run_id) is not None else None
        fn = message_data.get('filename')
        if not self._wait_for_run_context(run_id):
            self.logger.error(
                f"Skipping STF {fn} for run {run_id}: run context was not ready",
                extra=self._log_extra(run_id=run_id, stf_filename=fn)
            )
            self._mark_done_stf(run_id, fn)
            return False
        if not self._wait_for_pending_start(run_id):
            self.logger.error(
                f"Skipping STF {fn} for run {run_id}: start_run worker did not drain",
                extra=self._log_extra(run_id=run_id, stf_filename=fn)
            )
            self._mark_done_stf(run_id, fn)
            return False
        try:
            with self.data_work_lock:
                return self._handle_stf_gen(message_data)
        finally:
            self._mark_done_stf(run_id, fn)


    def _handle_stf_gen(self, message_data):
        fn = message_data.get('filename')
        run_id = str(message_data.get('run_id') or self.run_id) if (message_data.get('run_id') or self.run_id) is not None else None
        if run_id and fn and os.path.basename(str(fn)) in self.completed_stf_by_run.get(str(run_id), set()):
            return True
        if run_id and fn:
            self._remember_seen_stf(run_id, fn)
        context = self._run_context(run_id) if run_id else {}
        if context:
            self.run_id = context.get("run_id") or self.run_id
            self.dataset = context.get("dataset") or self.dataset
            self.folder = context.get("folder") or self.folder
            self.data_folder = context.get("data_folder") or self.data_folder
        if self.verbose: print(f"*** MQ: STF generation for file: {fn}, count {self.count} ***")
        
        file_path = f'{self.folder}/{fn}'

        if not os.path.exists(file_path):
            if self.verbose: print(f"*** Alert: the path '{file_path}' does not exist. ***")
            return False
            
        if self.rucio_scope == '' or self.data_folder == '' or self.rse == '':
            if self.verbose: print('*** No Rucio scope, RSE or data container provided, skipping Rucio upload ***')
            return False

        if self.run_id is None:
            if self.verbose: print('*** No run_id set, cannot proceed with Rucio upload ***')
            return False
        
        if self.folder == '':
            if self.verbose: print('*** No source data folder set, cannot proceed with Rucio upload ***')
            return False
        
        # Important: the file must be uploaded to Rucio before it can be attached to a dataset
        # This is for Rucio only:
        upload_spec = {
            'path':         file_path,
            'rse':          self.rse,
            'did_scope':    self.rucio_scope,
            'did_name':     fn,
        }
        if self.rse_is_deterministic:
            self.logger.warning(f"RSE \"{self.rse}\" is deterministic, so this upload will not follow the PFN schema")
        else:
            upload_spec['pfn'] = f'{xrd_server.rstrip("/")}{xrd_folder}/{self.dataset}/{fn}'

        # Upload the file using either XRootD or Rucio
        if self.xrdup: # XRootD upload

            if self.verbose: print(f'''*** XRootD upload mode is enabled, will upload the file {file_path} to RSE {self.rse} using XRootD ***''')
            status = self.fs.copy(file_path, f'{xrd_server}{xrd_folder}/{self.dataset}/{fn}', force=False) # force=True to overwrite

            if self.verbose: print(f"*** xrd copy status type: {type(status)}, status: {status} ***")
            register_file_on_rse(self, file_path, fn)

        else:          # Rucio upload
            try:
                result = self.rucio_upload_client.upload([upload_spec])
            except Exception as e:
                print(f'*** Exception during upload: {e} ***')
                return False
            if result == 0:
                if self.verbose: print(f"File {file_path} uploaded successfully to Rucio under scope {self.rucio_scope} ***")
            else:
                print(f"File {file_path} upload failed.")
                return False


        # N.B. Rucio does not accept large integers so mind the run ID
        self.rucio_did_client.set_metadata(scope=self.rucio_scope, name=fn, key='run_number', value=self.run_id)

        guid = str(uuid.uuid4())
        self.rucio_did_client.set_metadata(scope=self.rucio_scope, name=fn, key='guid', value=guid)

        # Attach the file to the open dataset
        if self.verbose: print(f'''*** Adding a file with lfn: {fn} to the scope/dataset: {self.rucio_scope}:{self.dataset} ***''')

        # Register the file replica, using the lfn
        if _USE_RUCIO_UTILS:
            attachment_success = add_files_to_dataset([f'''{self.rucio_scope}:{fn}'''], f'''{self.rucio_scope}:{self.dataset}''', client=self.rucio_client)
        else:  # Deprecated: legacy rucio_comms class-based managers
            attachment_success = self.file_manager.add_files_to_dataset([f'''{self.rucio_scope}:{fn}'''], f'''{self.rucio_scope}:{self.dataset}''')
        if self.verbose: print(f'''*** File attached to dataset: {attachment_success} ***''')

        decision = None
        decision_metadata = {}
        decision_box_enabled = self._decision_box_enabled_for_message(message_data, run_id=message_data.get("run_id") or self.run_id)
        non_decision_box_site = self._non_decision_box_site_for_message(message_data, run_id=message_data.get("run_id") or self.run_id)
        if decision_box_enabled:
            decision = self.apply_decision_for_stf(message_data)
            if decision:
                decision_metadata = {
                    "decision_box_reason": decision.reason,
                    "decision_box_file_did": str(decision.file_did),
                    "decision_box_site_datasets": list(decision.site_datasets),
                    "decision_box_selected_sites": self._decision_sites(self.run_id, decision),
                    "decision_box_source_agent": self.agent_name,
                }

        execution_id = message_data.get("execution_id") or context.get("execution_id")
        file_metadata = metadata_with_execution_id(decision_metadata, execution_id)

        first_file_for_run = self.count == 0
        self.count += 1
        
        run_id = str(message_data.get('run_id') or self.run_id) if (message_data.get('run_id') or self.run_id) is not None else None
        file_url = message_data.get('file_url')
        checksum = message_data.get('checksum')
        size_bytes = message_data.get('size_bytes')
        # Capture timing, state, and sequence fields
        start = message_data.get('start')
        end = message_data.get('end')
        state = message_data.get('state')
        substate = message_data.get('substate')
        sequence = message_data.get('sequence')

        self.logger.info("Processing STF file",
                        extra=self._log_extra(stf_filename=fn, size_bytes=size_bytes,
                                             simulation_tick=message_data.get('simulation_tick')))

        # Register STF file and workflow with monitor
        registered_file_id = self.register_stf_file(
            run_id, fn, size_bytes, start, end, state, substate, sequence,
            extra_metadata=file_metadata,
        )
        if registered_file_id is None:
            return False

        if decision_box_enabled and decision:
            ready_sites = self.ready_sites_by_run.setdefault(str(run_id), set())
            for site_dataset in decision.site_datasets:
                site_name = self._site_name_for_dataset(run_id, site_dataset)
                if not site_name or site_name in ready_sites:
                    continue
                if self._send_data_ready_message(
                    site_name=site_name,
                    input_dataset=site_dataset,
                    execution_id=execution_id,
                    decision_box_enabled=True,
                    non_decision_box_site=non_decision_box_site,
                ):
                    ready_sites.add(site_name)
                if self.verbose and site_name in ready_sites:
                    print(
                        f"*** First selected STF for run {self.run_id} at {site_name}, "
                        "sending site-specific data ready message to MQ ***"
                    )
        elif first_file_for_run:
            if self._send_data_ready_message(
                execution_id=execution_id,
                decision_box_enabled=False,
                non_decision_box_site=non_decision_box_site,
            ) and self.verbose:
                print(f'''*** First file for run {self.run_id} has been processed, sending data ready message to MQ ***''')

        self._remember_completed_stf(run_id or self.run_id, fn)
        return True


    # ---
    def handle_data_ready(self, message_data):
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: cross-check - data ready for run {run_id} ***")


    def create_run_record(self, run_id, run_conditions):
        """Create a run record in the monitor."""
        self.logger.info(f"Creating run record {run_id} in monitor...")

        run_data = {
            'run_number': int(run_id),  # Convert string run_id to integer
            'start_time': datetime.now().isoformat(),
            'run_conditions': run_conditions
        }

        try:
            result = self.call_monitor_api('POST', '/runs/', run_data)
            if result:
                monitor_run_id = result.get('run_id')
                self.active_runs[run_id] = {
                    'monitor_run_id': monitor_run_id,
                    'files_created': 0,
                    'total_files': 0,
                    'run_conditions': dict(run_conditions or {}),
                }
                self.logger.info(f"Run {run_id} registered in monitor with ID {monitor_run_id}")
                return monitor_run_id
            else:
                self.logger.error(f"Failed to register run {run_id} in monitor - API returned no data")
                return None
        except RuntimeError as e:
            if "400 Client Error" in str(e):
                # Report the actual error details so we can see what it is
                error_msg = str(e)
                self.logger.error(f"Run {run_id} registration failed with 400 error: {error_msg}")
                # Crash so we can examine the actual error and implement proper handling
                raise
            else:
                # Re-raise other API errors
                raise


    def update_run_status(self, run_id, status='completed'):
        """Close the monitor run and persist the data-agent outcome.

        swf-monitor's Run model has no dedicated status column. Keep the
        outcome in run_conditions so failures are not silently collapsed into
        ordinary completion when end_time is written.
        """
        if run_id not in self.active_runs:
            self.logger.warning(f"Run {run_id} not found in active runs")
            return False

        monitor_run_id = self.active_runs[run_id]['monitor_run_id']
        self.logger.info(f"Updating run {run_id} status to {status} in monitor...")

        run_record = self.active_runs[run_id]
        run_conditions = dict(run_record.get('run_conditions') or {})
        run_conditions['data_agent_status'] = status
        update_data = {
            'end_time': datetime.now().isoformat(),
            'run_conditions': run_conditions,
        }

        result = self.call_monitor_api('PATCH', f'/runs/{monitor_run_id}/', update_data)
        if result:
            self.logger.info(f"Run {run_id} status updated successfully")
            return True
        else:
            self.logger.warning(f"Failed to update run {run_id} status")
            return False


    def register_stf_file(self, run_id, filename, file_size=None, start=None, end=None, state=None, substate=None, sequence=None, extra_metadata=None):
        """Register an STF file in the monitor."""
        if run_id not in self.active_runs:
            self.logger.warning(f"Cannot register file {filename} - run {run_id} not active")
            return None

        monitor_run_id = self.active_runs[run_id]['monitor_run_id']

        # Skip registration if run registration failed
        if monitor_run_id is None:
            self.logger.warning(f"Skipping STF file registration for {filename} - run {run_id} was not registered in monitor")
            return None

        self.logger.info(f"Registering STF file {filename} in monitor...")

        file_data = {
            'run': monitor_run_id,
            'stf_filename': filename,
            'file_size_bytes': file_size,
            'machine_state': state or 'unknown',
            'status': 'registered',
            'metadata': {
                'created_by': self.agent_name,
                'substate': substate,
                'start': start,
                'end': end,
                'sequence': sequence
            }
        }
        if extra_metadata:
            file_data['metadata'].update(extra_metadata)

        try:
            result = self.call_monitor_api('POST', '/stf-files/', file_data)
            if result:
                file_id = result.get('file_id')
                self.active_files[filename] = {
                    'file_id': file_id,
                    'run_id': run_id,
                    'status': 'registered'
                }
                self.active_runs[run_id]['files_created'] += 1
                self.logger.info(f"STF file {filename} registered with ID {file_id}")
                return file_id
            else:
                self.logger.warning(f"Failed to register STF file {filename} - API returned no data")
                return None
        except RuntimeError as e:
            if "400 Client Error" in str(e):
                # Parse the actual error response to understand what went wrong
                error_msg = str(e)
                self.logger.error(f"STF file {filename} registration failed with 400 error: {error_msg}")
                return None
            else:
                # Re-raise other API errors
                raise


############################################################################################
if __name__ == "__main__":
    # ---
    import argparse
    parser = argparse.ArgumentParser()

    parser.add_argument("-v", "--verbose",  action='store_true',    help="Verbose mode")
    parser.add_argument("-x", "--xrdup",    action='store_true',    help="XRootD upload, instead of Rucio",         default=False)
    parser.add_argument("-m", "--mqxmit",   action='store_true',    help="Transmit MQ messages, default to False",  default=False)
    parser.add_argument("-s", "--scope",    type=str,               help="Rucio scope for the data",                default='group.daq')
    parser.add_argument("-d", "--datadir",  type=str,               help="Data folder, from which to upload data",  default='/tmp')
    parser.add_argument("-r", "--rse",      type=str,               help="RSE to target for upload",                default='DAQ_DISK_3')

    args        = parser.parse_args()
    verbose     = args.verbose
    scope       = args.scope
    datadir     = args.datadir
    rse         = args.rse
    xrdup       = args.xrdup
    mqxmit      = args.mqxmit

    if verbose:
        print(f'''*** {'Verbose mode            ':<20} {verbose:>20} ***''')
        print(f'''*** {'XRootD mode             ':<20} {xrdup:>20} ***''')
        print(f'''*** {'Rucio scope             ':<20} {scope:>20} ***''')
        print(f'''*** {'Data container (folder) ':<20} {datadir:>20} ***''')
        print(f'''*** {'RSE for upload          ':<20} {rse:>20} ***''')
    # ---

    data = DATA(
        config_path=os.getenv('SWF_TESTBED_CONFIG'),
        verbose=verbose,
        mqxmit=mqxmit,
        xrdup=xrdup,
        rucio_scope=scope,
        data_folder=datadir,
        rse=rse
    )

    data.run()
