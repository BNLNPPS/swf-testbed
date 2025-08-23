# ###############################################################################
# The DATA class is the main data management class.
# It receives messages from the DAQ simulator and handles them.
# Main functionality is to create Rucio datasets and register files to
# these datasets. Then, to notify the processing agent that the data is ready.
# ###############################################################################

import os, sys, time, json

#################################################################################
class DATA:
    ''' The DATA class is the main data management class.
        It receives messages from the DAQ simulator and handles them.
        Main functionality is to create Rucio datasets and register files to
        these datasets. Then, to notify the processing agent that the data is ready.
    '''

    def __init__(self, verbose: bool = False, sender = None):
        self.verbose    = verbose
        self.sender     = sender
        self.init_mq()  # Initialize the MQ receiver to get messages from the DAQ simulator.

        if self.verbose:
            print(f'''*** DATA class initialized ***''')
        
    # ---
    def init_mq(self):
        ''' Initialize the MQ receiver to get messages from the DAQ simulator.
        '''

        MQ_COMMS_PATH       = ''

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

            print(f"Data agent is running. Press Ctrl+C to stop.")
            while True:
                time.sleep(1) # Keep the main thread alive, heartbeats can be added here
        except KeyboardInterrupt:
            print(f"Stopping data agent...")
            if self.verbose:
                print(f'''*** DATA class run method interrupted ***''')
    

    def on_message(self, msg):
        """
        Handles incoming DAQ messages (stf_gen, run_imminent, start_run, end_run).
        """
        print("Data Agent received message")
        try:
            message_data = json.loads(msg)
            msg_type = message_data.get('msg_type')
            
            if msg_type == 'stf_gen':
                self.handle_stf_gen(message_data)
            elif msg_type == 'run_imminent':
                self.handle_run_imminent(message_data)
            elif msg_type == 'start_run':
                self.handle_start_run(message_data)
            elif msg_type == 'end_run':
                self.handle_end_run(message_data)
            else:
                print("Ignoring unknown message type", extra={"msg_type": msg_type})
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}", extra={"error": str(e)})

    def handle_run_imminent(self, message_data):
        """Handle run_imminent message - create dataset in Rucio"""
        run_id = message_data.get('run_id')
        run_conditions = message_data.get('run_conditions', {})
        print("Processing run_imminent message")
        
        # TODO: Call Rucio to create dataset for this run
        
        # Simulate dataset creation
        # TBD: Replace with actual Rucio call

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
        print(f"Handling STF generation for file: {fn}")

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
