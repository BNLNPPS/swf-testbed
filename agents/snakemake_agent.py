"""
Snakemake Agent: listens on /topic/epictopic for stf_processed / run_snakemake
messages and runs a Snakemake workflow, forwarding every message field as a
Snakemake config value.
"""

import traceback
from pathlib import Path
from datetime import datetime

from swf_common_lib.base_agent import BaseAgent

from snakemake.api import SnakemakeApi
from snakemake.settings.types import (
    ResourceSettings,
    ConfigSettings,
    OutputSettings,
)


class SnakemakeAgent(BaseAgent):
    """Agent that triggers Snakemake workflows in response to ActiveMQ messages."""

    TRIGGER_MSG_TYPES = {"stf_processed", "run_snakemake"}

    def __init__(self, snakefile, workdir=None, cores=1, config_path=None, debug=False):
        super().__init__(
            agent_type="SNAKEMAKE",
            subscription_queue="/topic/epictopic",
            debug=debug,
            config_path=config_path,
        )
        self.snakefile = Path(snakefile).resolve()
        self.workdir = Path(workdir).resolve() if workdir else self.snakefile.parent
        self.cores = cores
        self.logger.info(f"SnakemakeAgent initialised, snakefile={self.snakefile}")

    def on_message(self, frame):
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        msg_namespace = message_data.get("namespace")
        if msg_namespace is not None and msg_namespace != self.namespace:
            return

        if "execution_id" in message_data:
            self.current_execution_id = message_data["execution_id"]
        if "run_id" in message_data:
            self.current_run_id = message_data["run_id"]

        if msg_type not in self.TRIGGER_MSG_TYPES:
            return

        self.set_processing()
        try:
            self._run_workflow(message_data)
            self._publish_result(message_data, success=True)
        except Exception as exc:
            self.logger.error(f"Workflow failed: {exc}")
            self.logger.error(traceback.format_exc())
            self._publish_result(message_data, success=False, error=str(exc))
        finally:
            self.set_ready()

    def _run_workflow(self, message_data):
        snake_config = {k: str(v) for k, v in message_data.items()}

        with SnakemakeApi(
            output_settings=OutputSettings(verbose=self.DEBUG),
        ) as api:
            workflow_api = api.workflow(
                snakefile=self.snakefile,
                workdir=self.workdir,
                resource_settings=ResourceSettings(cores=self.cores),
                config_settings=ConfigSettings(config=snake_config),
            )
            dag_api = workflow_api.dag()
            dag_api.execute_workflow()

    def _publish_result(self, trigger_message, success, error=None):
        msg = {
            "msg_type": "snakemake_complete",
            "namespace": self.namespace,
            "success": success,
            "snakefile": str(self.snakefile),
            "trigger_msg_type": trigger_message.get("msg_type"),
            "run_id": trigger_message.get("run_id"),
            "timestamp": datetime.now().isoformat(),
        }
        if trigger_message.get("execution_id"):
            msg["execution_id"] = trigger_message["execution_id"]
        if error:
            msg["error"] = error

        try:
            self.send_message("/topic/epictopic", msg)
        except Exception as exc:
            self.logger.error(f"Failed to publish snakemake_complete: {exc}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Snakemake Agent")
    parser.add_argument("--snakefile", required=True)
    parser.add_argument("--workdir", default=None)
    parser.add_argument("--cores", type=int, default=1)
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--testbed-config", default=None)
    args = parser.parse_args()

    SnakemakeAgent(
        snakefile=args.snakefile,
        workdir=args.workdir,
        cores=args.cores,
        debug=args.debug,
        config_path=args.testbed_config,
    ).run()
