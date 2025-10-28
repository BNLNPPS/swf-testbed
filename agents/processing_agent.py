#################################################################################
class PROCESSING:
    ''' The PROCESSING class is the main task management class.
        It receives MW messages from the DAQ simulator and handles them.
        Main functionality is to manage PanDA tasks for the testbed.
    '''

    def __init__(self,
                 sender= None,
                 receiver=None,
                 verbose=False):
        self.sender     = sender
        self.receiver   = receiver
        self.verbose    = verbose
        self.init_mq()

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