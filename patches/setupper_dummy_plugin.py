"""
This class is a dummy plugin. It inherits from the SetupperPluginBase class.

swf-testbed patch: the DDM-free dev stack has no Rucio->PanDA callback to mark
input files ready, so DBProxy.activateJob keeps JEDI jobs in 'defined' forever
(it only promotes defined->activated when every input file is ready/cached).
Here the input data is assumed already present, so we mark input files ready.
Temporary until the fix lands upstream in PanDAWMS/panda-server.
"""
import uuid

from typing import List, Dict

from pandaserver.dataservice.setupper_plugin_base import SetupperPluginBase


class SetupperDummyPlugin(SetupperPluginBase):
    """
    This class is a dummy plugin. It inherits from the SetupperPluginBase class.
    """

    # constructor
    def __init__(self, taskBuffer, jobs: List, logger, **params: Dict) -> None:
        """
        Constructor for the SetupperDummyPlugin class.

        :param taskBuffer: The buffer for tasks.
        :param jobs: The jobs to be processed.
        :param logger: The logger to be used for logging.
        :param params: Additional parameters.
        """
        # defaults
        default_map = {}
        SetupperPluginBase.__init__(self, taskBuffer, jobs, logger, params, default_map)

    # main
    def run(self) -> None:
        """
        The main method that runs the plugin. It iterates over the jobs and their files.
        If a file is of type "log", it generates a GUID for it. Input files are
        marked ready so the no-DDM activation path can promote the job.
        """
        for job_spec in self.jobs:
            for file_spec in job_spec.Files:
                if file_spec.type == "log":
                    # generate GUID
                    file_spec.GUID = str(uuid.uuid4())
                elif file_spec.type == "input" and file_spec.status == "unknown":
                    file_spec.status = "ready"

    # post run
    def post_run(self) -> None:
        """
        This method is called after the run method. Currently, it does nothing.
        """
        pass
