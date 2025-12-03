import time, json, getpass, uuid
from pandaclient import PrunScript, panda_api

#################################################################################
class PROCESSING:
    ''' The PROCESSING class is the main task management class.
        It receives MW messages from the DAQ simulator and handles them.
        Main functionality is to manage PanDA tasks for the testbed.
    '''

    def __init__(self,
                 verbose=False):

        # username = getpass.getuser()
        # agent_id = self.get_next_agent_id()
        # self.agent_name = f"{self.agent_type.lower()}-agent-{username}-{agent_id}"

        self.verbose    = verbose
        self.run_id     = None  # Current run number
        self.inDS       = None  # Input dataset name
        self.outDS      = None  # Output dataset name
        
        self.init_mq()

        if self.verbose: print(f'''*** Initialized the PROCESSING class ***''')


    # ---
    def test_panda(self, inDS, outDS):
        # Construct the full list of arguments for PrunScript.main
        # Datasets:
        # Example: inDS="group.daq:swf.101871.run", outDS="user.potekhin.test1"        

        
        prun_args = [
        "--exec", "./my_script.sh",
        "--inDS",   inDS,
        "--outDS",  outDS,
        "--nJobs", "1",
        "--vo", "wlcg",
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

        params['runUntilClosed'] = True
    
        if self.verbose:
            print(f"*** PANDA PARAMS ***")
            for k in params.keys():
                v = params[k]
                print(f"{k:<20}: {v}")
            print(f"********************")

        # Get the PanDA API client
        print("Getting PanDA API client...")
        c = panda_api.get_api()


        # Submit the task
        print(f"Submitting task to PanDA with output dataset: {outDS} ...")
        status, result_tuple = c.submit_task(params)

        # Check the submission status
        if status == 0:
            print(result_tuple)
            # jedi_task_id = result_tuple[2]
            # panda_monitor_url = os.environ.get('PANDAMON_URL')

            # print(f"Task submitted successfully! JediTaskID: {jedi_task_id}")
            # print(f"You can monitor your task at: {panda_monitor_url}/task/{jedi_task_id}/")
        else:
            print(f"Task submission failed. Status: {status}, Message: {result_tuple}")



        return None
    
    # ---
    def name_current_datasets(self):
        self.inDS   = f'''swf.{self.run_id:06d}.run'''          # INput dataset name based on the run number
        self.outDS  = f'''swf.{self.run_id:06d}.processed'''    # Output dataset
    # ---
    def panda_submit_task(self, dataset_name):
        pass

    # ---
    def on_message(self, msg):
        """
        Handles incoming messages.
        """

        try:
            message_data = json.loads(msg)
            msg_type = message_data.get('msg_type')
            if msg_type == 'data_ready':
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
        except Exception as e:
            print(f"CRITICAL: Message processing failed - {str(e)}")

    # ---
    def handle_data_ready(self, message_data):
        """Handle data_ready message"""
        run_id = message_data.get('run_id')
        print(f"*** MQ: data ready for run {run_id} ***")
        self.run_id = run_id
        self.name_current_datasets()

        #  Construct the full list of arguments for PrunScript.main
        prun_args = [
        "--exec", "./my_script.sh",
        "--inDS",   f"group.daq:{self.inDS}",
        "--outDS",  f"group.daq:{self.outDS}",
        "--nJobs", "1",
        "--vo", "wlcg",
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
        print(params)
        return None
    
    # ---
    def handle_stf_gen(self, message_data):
        """Handle stf gen message"""
        fn = message_data.get('filename')
        print(f"*** MQ: stf_gen {fn} ***")

    # ---
    def handle_run_imminent(self, message_data):
        """Handle run imminent message"""
        run_id = message_data.get('run_id')
        print(f"*** MQ: run_imminent {run_id} ***")
            
    
    # ---
    def handle_start_run(self, message_data):
        """Handle start_run message"""
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: start_run message for run_id: {run_id} ***")

    # ---
    def handle_end_run(self, message_data):
        """Handle end_run message"""
        run_id = message_data.get('run_id')
        if self.verbose: print(f"*** MQ: end_run message for run_id: {run_id} ***")
    
    # ---
    def init_mq(self):
        ''' Initialize the MQ receiver to get messages from the DAQ simulator.
        '''

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
            rcvr = Receiver(verbose=self.verbose, client_id="processing", processor=self.on_message) # a function to process received messages
            rcvr.connect()
            if self.verbose: print(f'''*** Successfully instantiated and connected the Receiver, will receive messages from MQ ***''')
        except:
            print('*** Failed to instantiate the Receiver, exiting...***')
            exit(-1)
            
    # ---
    def run(self):
        ''' Run the listener loop, which will start receiving MQ messages.
            It will process these messages and handle processing management tasks.
        '''
        if self.verbose:
            print(f'''*** PROCESSING class run method called ***''')

        try:
            if self.verbose: print(f"*** Processing agent is running. Press Ctrl+C to stop. ***")
            while True:
                time.sleep(1) # Keep the main thread alive, heartbeats can be added here
        except KeyboardInterrupt:
            if self.verbose:
                print(f'''*** PROCESSING class run method interrupted by the KeyboardInterrupt ***''')