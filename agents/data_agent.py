# ###############################################################################
# The DATA class is the main data management class.
#
# It receives messages from the DAQ simulator and handles them.
#
# Main functionality is to create Rucio datasets and register files to
# these datasets. Then, to notify the processing agent that the data is ready.
# 
# It uses the mq_comms and rucio_comms packages for MQ and Rucio operations.
#
# Datasets are created upon receiving the run_imminent message.
# Files are registered upon receiving the stf_gen message.
#
# The run_id and dataset name are extracted from the run_imminent message.
# The data folder is defined globally.
# The Rucio scope and RSE are defined globally.
# The file is attached to the dataset after it is uploaded to Rucio.
# The file metadata is set upon registration.
# The file is registered under the provided Rucio scope.
# The dataset is created under the provided Rucio scope.
#
# ###############################################################################

xrd_server = 'root://dcintdoor.sdcc.bnl.gov:1094/'
xrd_folder = '/pnfs/sdcc.bnl.gov/eic/epic/disk/swfdaqtest/'

import os, sys, time, json


# Rucio imports
from rucio.client.client import Client
from rucio.client.replicaclient import ReplicaClient
from rucio.client.didclient import DIDClient
from rucio.common.exception import DataIdentifierAlreadyExists, RSENotFound

from rucio_comms.utils import calculate_adler32_from_file, register_file_on_rse

#################################################################################
class DATA:
    ''' The DATA class is the main data management class.
        It receives messages from the DAQ simulator and handles them.
        Main functionality is to create Rucio datasets and register files to
        these datasets. Then, to notify the processing agent that the data is ready.
    '''

    def __init__(self,
                verbose:        bool = False,
                xrdup:          bool = False,
                rucio_scope:    str  = '',
                data_folder:    str  = '',
                rse:            str  = ''):
        ''' Initialize the DATA class.
            Parameters:
                verbose (bool): Verbose mode
                xrdup (bool): Use XRootD for upload instead of Rucio
                rucio_scope (str): Rucio scope to use for datasets and files; if empty, no Rucio operations will be performed
                data_folder (str): Folder where data files are located; if empty, no data will be uploaded
                rse (str): RSE to target for upload; if empty, no data will be uploaded
        '''
        self.verbose            = verbose
        self.xrdup              = xrdup

        self.rucio_client       = None
        self.rucio_upload_client= None
        self.rucio_did_client   = None
        self.rucio_replica_client= None
        self.fs                 = None # File system client, e.g. XRootD client
        
        self.file_manager       = None
        self.dataset_manager    = None

        self.rucio_scope        = rucio_scope
        self.data_folder        = data_folder    # if empty, no data will be uploaded
        self.run_id             = None              # current run ID, to be set upon receiving the run_imminent message
        self.dataset            = ''                # current dataset name, to be set upon receiving the run_imminent message
        self.folder             = ''                # the actual folder for the current run, to be accessed later
        self.rse                = rse               # RSE to target for upload


        self.init_mq()  # Initialize the MQ receiver to get messages from the DAQ simulator.
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

    # ---
    def init_rucio(self):
        ''' Initialize the Rucio module.
        '''
 
        RUCIO_COMMS_PATH    = ''

        try:
            RUCIO_COMMS_PATH = os.environ['RUCIO_COMMS_PATH']
            if self.verbose: print(f'''*** The RUCIO_COMMS_PATH is defined in the environment: {RUCIO_COMMS_PATH}, will be added to sys.path ***''')
            sys.path.append(RUCIO_COMMS_PATH)
        except KeyError:
            if self.verbose: print('*** The variable RUCIO_COMMS_PATH is undefined, will rely on PYTHONPATH ***')

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

        # if self.xrdup:
        #     from rucio_comms.utils import calculate_adler32_from_file, register_file_on_rse
        #     x = calculate_adler32_from_file('README.md')
        #     print(f'Adler-32 checksum of the file README.md is {x}')
        #     register_file_on_rse(self.rucio_client, self.rse, self.rucio_scope, "path", name)


    # ---
    def init_mq(self):
        ''' Initialize the MQ receiver to get messages from the DAQ simulator.
        '''

        MQ_COMMS_PATH = ''

        try:
            MQ_COMMS_PATH = os.environ['MQ_COMMS_PATH']
            print(f'''*** The MQ_COMMS_PATH is defined in the environment: {MQ_COMMS_PATH}, will be added to sys.path ***''')
            if MQ_COMMS_PATH not in sys.path: sys.path.append(MQ_COMMS_PATH)
        except:
            print('*** The variable MQ_COMMS_PATH is undefined, will rely on PYTHONPATH ***')
            if self.verbose: print('*** The variable MQ_COMMS_PATH is undefined, will rely on PYTHONPATH ***')

        if self.verbose: print(f'''*** Set the Python path: {sys.path} ***''')

        try:
            from mq_comms import Sender, Receiver
        except:
            if self.verbose: print('*** Failed to import the Sender and Receiver from comms, exiting...***')
            exit(-1)

        try:
            sndr = Sender(verbose=self.verbose)
            if self.verbose: print(f'''*** Successfully instantiated the Sender ***''')
            sndr.connect()
            if self.verbose: print(f'''*** Successfully connected the Sender to MQ ***''')
        except:
            print('*** Failed to instantiate the Sender, exiting...***')
            exit(-1)

        try:
            rcvr = Receiver(verbose=self.verbose, processor=self.on_message) # a function to process received messages
            rcvr.connect()
            if self.verbose: print(f'''*** Successfully instantiated and connected the Receiver, will receive messages from MQ ***''')
        except:
            print('*** Failed to instantiate the Receiver, exiting...***')
            exit(-1)    
    
    # ---
    def run(self):
        ''' Run the DATA class, which will start receiving messages from the DAQ simulator.
            It will process these messages and handle data management tasks.
        '''
        if self.verbose:
            print(f'''*** DATA class run method called ***''')

        try:
            if self.verbose: print(f"*** Data agent is running. Press Ctrl+C to stop. ***")
            while True:
                time.sleep(1) # Keep the main thread alive, heartbeats can be added here
        except KeyboardInterrupt:
            if self.verbose:
                print(f'''*** DATA class run method interrupted by the KeyboardInterrupt ***''')
    

    def on_message(self, msg):
        """
        Handles incoming DAQ messages (stf_gen, run_imminent, start_run, end_run).
        """

        try:
            message_data = json.loads(msg)
            msg_type = message_data.get('msg_type')
            
            # print(f'===================================> {msg_type}')
            if msg_type == 'stf_gen':
                self.handle_stf_gen(message_data)
            elif msg_type == 'run_imminent':
                self.handle_run_imminent(message_data)
            elif msg_type == 'start_run':
                self.handle_start_run(message_data)
            elif msg_type == 'end_run':
                self.handle_end_run(message_data)
            else:
                print("Ignoring unknown message type", msg_type)
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}")

    def handle_run_imminent(self, message_data):
        """Handle run_imminent message - create dataset in Rucio"""
        run_id = message_data.get('run_id')
        run_conditions = message_data.get('run_conditions', {})
        
        if self.verbose: print(F'''*** Processing run_imminent message for run {run_id}***''')
        
        self.run_id     = run_id
        self.dataset    = message_data.get('dataset')
        self.folder     = f"{self.data_folder}/{self.dataset}"
            
        lifetime = 1 # days
        result = self.dataset_manager.create_dataset(dataset_name=f'''{self.rucio_scope}:{self.dataset}''', lifetime_days=lifetime, open_dataset=True)
        if self.verbose: print(f'''*** Dataset creation result: {result} ***''')
        if not result:
            if self.verbose: print('*** Dataset creation failed, exiting... ***')
            exit(-1)
        else:
            if self.verbose: print(f'*** Dataset {result["scope"]}:{result["name"]} created successfully with DUID: {result["duid"]} ***')


    def handle_start_run(self, message_data):
        """Handle start_run message"""
        run_id = message_data.get('run_id')
        print("Processing start_run message for run_id:", run_id )

    def handle_end_run(self, message_data):
        """Handle end_run message"""
        run_id = message_data.get('run_id')
        print("Processing end_run message for run_id:", run_id )


    def handle_stf_gen(self, message_data):
        fn = message_data.get('filename')
        if self.verbose: print(f"*** Handling STF generation for file: {fn} ***")
        
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
        upload_spec = {
            'path':         file_path,
            'rse':          self.rse,
            'did_scope':    self.rucio_scope,
            'did_name':     fn,
        }

        # Upload the file using either XRootD or Rucio
        if self.xrdup: # XRootD upload
            if self.verbose: print(f'''*** XRootD upload mode is enabled, will upload the file {file_path} to RSE {self.rse} using XRootD ***''')
            status = self.fs.copy(file_path, f'{xrd_server}{xrd_folder}/{fn}', force=False) # force=True to overwrite
            print(f"{status}")

            register_file_on_rse(
                self,
                file_path,
                fn)
            # return None
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

        # Attach the file to the open dataset
        if self.verbose: print(f'''*** Adding a file with lfn: {fn} to the scope/dataset: {self.rucio_scope}:{self.dataset} ***''')
        # Register the file replica, using the lfn
        attachment_success = self.file_manager.add_files_to_dataset([f'''{self.rucio_scope}:{fn}'''], f'''{self.rucio_scope}:{self.dataset}''')
        if self.verbose: print(f'''*** File attached to dataset: {attachment_success} ***''')
                               
        return None

############################################################################################
# -- ATTIC --
# Rucio imports for demonstration purposes only.
# The actual implementation will be in the rucio_comms package.

# from rucio.client import Client as RucioClient

# from rucio.client.uploadclient import UploadClient
# from rucio.common.exception import RucioException
# from rucio.common.utils import generate_uuid
# from rucio.common.types import InternalAccount
# from rucio.common.logging import setup_logging
# import logging
# import os
# from typing import Optional, List, Dict, Any
# from rucio.common.utils import parse_replicas

# ---
