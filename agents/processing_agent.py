import time, json, getpass

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

        self.init_mq()

        if self.verbose: print(f'''*** Initialized the PROCESSING class ***''')

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
        # run_id = message_data.get('run_id')
        print(f"*** MQ: data ready ***")

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