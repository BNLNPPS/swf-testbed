import os, time, json, getpass, uuid
from pandaclient import PrunScript, panda_api
from swf_common_lib.base_agent import BaseAgent
from swf_common_lib.api_utils import ensure_namespace

#################################################################################
class PROCESSING(BaseAgent):
    ''' The PROCESSING class is the main task management class.
        It receives MW messages from the DAQ simulator and handles them.
        Main functionality is to manage PanDA tasks for the testbed.
    '''

    def __init__(self, config_path=None, verbose=False, test=False):
        super().__init__(agent_type='PROCESSING', subscription_queue='/topic/epictopic',
                         debug=verbose, config_path=config_path)

        # username = getpass.getuser()
        # agent_id = self.get_next_agent_id()
        # self.agent_name = f"{self.agent_type.lower()}-agent-{username}-{agent_id}"

        self.verbose      = verbose
        self.test         = test
        self.run_id       = None  # Current run number
        self.inDS         = None  # Input dataset name
        self.outDS        = None  # Output dataset name
        self.panda_status = {}    # PanDA submission status

        self.active_processing = {}  # Track files being processed
        self.processing_stats = {'total_processed': 0, 'failed_count': 0}

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


    # ---
    def on_message(self, msg):
        """
        Handles incoming messages.
        """

        try:
            message_data = json.loads(msg.body)
            self.current_execution_id = message_data.get('execution_id')
            self.current_run_id = message_data.get('run_id')
            
            msg_type = message_data.get('msg_type')
            msg_namespace = message_data.get('namespace')
             
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
        username = os.getenv('USER', 'unknown')

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
        self.panda_status[self.run_id] = {'status': status, 'message': msg}

        self.logger.info(f"New task submitted to PanDA. status:{status}, message:{msg}")

        return None


    # ---
    def handle_stf_gen(self, message_data):
        """Handle stf gen message"""
        fn = message_data.get('filename')
        started_at = message_data.get('timestamp')
        print(f"*** MQ: stf_gen {fn} ***")

        # ToDo
        #self.active_processin[fn] = {
        #    'run_id':     self.run_id,
        #    'started_at': started_at,
        #    'input_data': fn
        #}


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

        # TODO: set agent ready for next run
        

    def send_processing_agent_heartbeat(self):
        """Send enhanced heartbeat with processing agent context."""
        workflow_metadata = {
            'active_tasks': len(self.active_processing),
            'completed_tasks': self.processing_stats['total_processed'],
            'failed_tasks': self.processing_stats['failed_count']
        }

        return self.send_enhanced_heartbeat(workflow_metadata)


if __name__ == "__main__":
    import  argparse, datetime, sys, shutil
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
