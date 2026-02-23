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
import os, sys, time, json
import requests, urllib3
from datetime import datetime

# Rucio imports
from rucio.client.client        import Client
from rucio.client.replicaclient import ReplicaClient
from rucio.client.didclient     import DIDClient
from rucio.common.exception     import DataIdentifierAlreadyExists, RSENotFound

# Common lib imports
from rucio_comms.utils          import calculate_adler32_from_file, register_file_on_rse, RucioUtils
from api_utils import           get_next_agent_id

from swf_common_lib.base_agent import BaseAgent
from swf_common_lib.api_utils import ensure_namespace

#################################################################################
class DATA(BaseAgent):
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

        time.sleep(1)


    # ---
    def init_rucio(self):
        ''' Initialize the Rucio module.
        '''
 
        from rucio_comms import DatasetManager, RucioClient, UploadClient, FileManager
        # ---
        try:
            from rucio_comms import DatasetManager, RucioClient, UploadClient, FileManager
            if self.verbose: print(f'''*** Successfully imported classes from rucio_comms ***''')
        except:
            print('*** Failed to import the classes from rucio_comms, exiting...***')
            exit(-1)


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
    def mq_data_ready_message(self):
        '''
        Create a "data ready" message to be sent to MQ.
        '''
        
        msg = {}
       
        msg['namespace']    = self.namespace 
        msg['sender']       = self.agent_name 
        msg['req_id']       = 1
        msg['msg_type']     = 'stf_ready'
        msg['run_id']       = self.run_id
        
        return msg
        #return json.dumps(msg)
 

    # ---
    def on_message(self, msg):
        """
        Handles incoming DAQ messages (stf_gen, run_imminent, start_run, end_run).
        """

        try:
            message_data = json.loads(msg.body)
            
            msg_type = message_data.get('msg_type')
            msg_namespace = message_data.get('namespace')
            # Debug only: print(f'===================================> {msg_type}')
            
            if msg_namespace == self.namespace:
                if msg_type == 'stf_gen':
                    self.handle_stf_gen(message_data)
                elif msg_type == 'stf_ready':
                    self.handle_data_ready(message_data)
                elif msg_type == 'run_imminent':
                    self.handle_run_imminent(message_data)
                elif msg_type == 'start_run':
                    self.handle_start_run(message_data)
                elif msg_type == 'end_run':
                    self.handle_end_run(message_data)
                else:
                    if self.verbose: print(f"*** Ignoring unknown message type {msg_type} ***")
            else:
                print("Ignoring other namespaces ", msg_namespace)
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}")


    # ---
    def handle_run_imminent(self, message_data):
        """
        Handle run_imminent message - create dataset in Rucio.
        If using XRootD upload mode, the dataset folder is created here.
        """
        run_id = message_data.get('run_id')
        run_conditions = message_data.get('run_conditions', {})
        
        if self.verbose: print(F'''*** MQ: run_imminent message for run {run_id}***''')

        self.logger.info("Processing run_imminent message",
                        extra=self._log_extra(simulation_tick=message_data.get('simulation_tick')))

        # Create run record in monitor
        monitor_run_id = self.create_run_record(run_id, run_conditions)

        self.count = 0 # reset file counter for the new run
        
        self.run_id     = run_id
        self.dataset    = message_data.get('dataset')
        self.folder     = f"{self.data_folder}/{self.dataset}"

        if self.verbose: print(f'''*** Current dataset set to {self.dataset}, folder set to {self.folder} ***''')
        
        lifetime = 1 # days
        result = self.dataset_manager.create_dataset(dataset_name=f'''{self.rucio_scope}:{self.dataset}''', lifetime_days=lifetime, open_dataset=True)
        if self.verbose: print(f'''*** Dataset {self.dataset}, creation result: {result} ***''')
        if not result:
            if self.verbose: print('*** Dataset creation failed, exiting... ***')
            exit(-1)
        else:
            if self.verbose: print(f'*** Dataset {result["scope"]}:{result["name"]} created successfully with DUID: {result["duid"]} ***')

        if self.xrdup: # XRootD upload
            if self.verbose: print(f'''*** XRootD upload mode is enabled, will create a folder for dataset {self.dataset} ***''')
            # Create the folder for the dataset using XRootD
            status, _ = self.fs.mkdir(f"{xrd_folder}/{self.dataset}")
            # FIXME: Check the status
            if self.verbose: print(f'''*** Created folder {xrd_folder}/{self.dataset} using XRootD ***''')


    # ---
    def handle_start_run(self, message_data):
        """Handle start_run message"""
        run_id = message_data.get('run_id')
        self.count = 0 # reset file counter for the new run
        if self.verbose: print(f"*** MQ: start_run message for run_id: {run_id} ***")


    # ---
    def handle_end_run(self, message_data):
        """Handle end_run message"""
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: end_run message for run_id: {run_id} ***")

        # Close the dataset
        self.rucio_client.set_status(
            scope=self.rucio_scope,
            name=self.dataset,
            open=False  # Setting to False closes the dataset
        )

        total_files = message_data.get('total_files', 0)
        self.logger.info("Processing end_run message",
                        extra=self._log_extra(total_files=total_files, simulation_tick=message_data.get('simulation_tick')))

        # Update run status in monitor API
        if run_id in self.active_runs:
            self.active_runs[run_id]['total_files'] = total_files
            self.update_run_status(run_id, 'completed')


    # ---
    def handle_stf_gen(self, message_data):
        fn = message_data.get('filename')
        if self.verbose: print(f"*** MQ: STF generation for file: {fn}, count {self.count} ***")
        
        file_path = f'{self.folder}/{fn}'

        if not os.path.exists(file_path):
            if self.verbose: print(f"*** Alert: the path '{file_path}' does not exist. ***")
            return None
            
        if self.rucio_scope == '' or self.data_folder == '' or self.rse == '':
            if self.verbose: print('*** No Rucio scope, RSE or data container provided, skipping Rucio upload ***')
            return None

        if self.run_id is None:
            if self.verbose: print('*** No run_id set, cannot proceed with Rucio upload ***')
            return None
        
        if self.folder == '':
            if self.verbose: print('*** No source data folder set, cannot proceed with Rucio upload ***')
            return None
        
        # Important: the file must be uploaded to Rucio before it can be attached to a dataset
        # This is for Rucio only:
        upload_spec = {
            'path':         file_path,
            'rse':          self.rse,
            'did_scope':    self.rucio_scope,
            'did_name':     fn,
        }

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
                return None
            if result == 0:
                if self.verbose: print(f"File {file_path} uploaded successfully to Rucio under scope {self.rucio_scope} ***")
            else:
                print(f"File {file_path} upload failed.")
                return None


        # N.B. Rucio does not accept large integers so mind the run ID
        self.rucio_did_client.set_metadata(scope=self.rucio_scope, name=fn, key='run_number', value=self.run_id)

        guid = RucioUtils.generate_guid()
        formatted_guid = RucioUtils.format_guid(guid)
        print(f'''*** Generated GUID: {guid}, formatted GUID for Rucio: {formatted_guid} ***''')
        self.rucio_did_client.set_metadata(scope=self.rucio_scope, name=fn, key='guid', value=formatted_guid)

        # Attach the file to the open dataset
        if self.verbose: print(f'''*** Adding a file with lfn: {fn} to the scope/dataset: {self.rucio_scope}:{self.dataset} ***''')

        # Register the file replica, using the lfn
        attachment_success = self.file_manager.add_files_to_dataset([f'''{self.rucio_scope}:{fn}'''], f'''{self.rucio_scope}:{self.dataset}''')
        if self.verbose: print(f'''*** File attached to dataset: {attachment_success} ***''')

        if self.count == 0:
            self.send_message('/topic/epictopic', self.mq_data_ready_message())
            if self.verbose: print(f'''*** First file for run {self.run_id} has been processed, sending data ready message to MQ ***''')

        self.count += 1
        
        run_id = message_data.get('run_id')  
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
        self.register_stf_file(run_id, fn, size_bytes, start, end, state, substate, sequence)

        return None


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
                    'total_files': 0
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
        """Update run status in the monitor."""
        if run_id not in self.active_runs:
            self.logger.warning(f"Run {run_id} not found in active runs")
            return False

        monitor_run_id = self.active_runs[run_id]['monitor_run_id']
        self.logger.info(f"Updating run {run_id} status to {status} in monitor...")

        update_data = {
            'end_time': datetime.now().isoformat()
        }

        result = self.call_monitor_api('PATCH', f'/runs/{monitor_run_id}/', update_data)
        if result:
            self.logger.info(f"Run {run_id} status updated successfully")
            return True
        else:
            self.logger.warning(f"Failed to update run {run_id} status")
            return False


    def register_stf_file(self, run_id, filename, file_size=None, start=None, end=None, state=None, substate=None, sequence=None):
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
