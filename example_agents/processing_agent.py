#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import uuid
import logging
from datetime import datetime
import requests

if "PANDA_NICKNAME" not in os.environ:
    os.environ["PANDA_NICKNAME"] = "your_username"

logging.getLogger("panda-client").setLevel(logging.ERROR)

from pandaclient import PrunScript, panda_api
from swf_common_lib.base_agent import BaseAgent


class ProcessingAgent(BaseAgent):
    def __init__(self):
        super().__init__(agent_type='PROCESSING', subscription_queue='processing_agent')

        self.scope = os.getenv('RUCIO_SCOPE', 'user.your_username')
        self.account = os.getenv('RUCIO_ACCOUNT', 'your_username')
        self.rucio_vo = os.getenv('RUCIO_VO', 'your_vo')
        self.nickname = os.getenv('PANDA_NICKNAME', 'your_username')
        self.panda_site = os.getenv('PANDA_SITE', '')
        self.panda_auth_vo = os.getenv('PANDA_AUTH_VO', 'YOUR_VO')
        self.pandamon = os.getenv('PANDAMON_URL', 'https://your-panda-monitor.example.com')

        self.rucio_base = os.getenv('RUCIO_BASE_URL', 'https://your-rucio-server.example.com')
        self.x509_proxy = os.getenv('X509_USER_PROXY', f"/tmp/x509up_u{os.getuid()}")
        default_cafile = os.path.expanduser("~/.globus/full-chain.pem")
        self.rucio_cafile = os.getenv('RUCIO_CAFILE', default_cafile if os.path.exists(default_cafile) else "")

        self.processing_stats = {'total_processed': 0, 'failed_count': 0}
        self.active_processing = {}
        self.run_datasets = {}
        self._rucio = None

    def on_message(self, frame):
        self.logger.info("Processing Agent received message")
        self.send_processing_agent_heartbeat()
        try:
            msg = json.loads(frame.body)
            t = msg.get('msg_type')
            if t == 'run_imminent':
                self.handle_run_imminent(msg)
            elif t == 'start_run':
                self.handle_start_run(msg)
            elif t == 'data_ready':
                self.handle_data_ready(msg)
            elif t == 'end_run':
                self.handle_end_run(msg)
            else:
                self.logger.info("Ignoring unknown message type", extra={"msg_type": t})
        except Exception as e:
            import traceback
            self.logger.error(f"CRITICAL: Message processing failed - {e}")
            self.logger.error(traceback.format_exc())
            raise

    def send_processing_agent_heartbeat(self):
        workflow_metadata = {
            'active_tasks': len(self.active_processing),
            'completed_tasks': self.processing_stats['total_processed'],
            'failed_tasks': self.processing_stats['failed_count'],
            'active_runs': len(self.run_datasets)
        }
        self.send_enhanced_heartbeat(workflow_metadata)

    def register_processing_task(self, filename, input_data):
        try:
            self.logger.info(f"Registering processing task for {filename}...")
            
            self.active_processing[filename] = {
                'task_id': f"local_{filename}_{int(datetime.now().timestamp())}",
                'started_at': datetime.now(),
                'input_data': input_data,
                'status': 'processing'
            }
            
            self.logger.info(f"Processing task registered locally for {filename}")
            return self.active_processing[filename]['task_id']
            
        except Exception as e:
            self.logger.warning(f"Task registration failed for {filename}: {e}")
            return None

    def update_file_processing_status(self, filename, status, metadata=None):
        if filename not in self.active_processing:
            self.logger.warning(f"No active task found for {filename}")
            return False
            
        try:
            task_info = self.active_processing[filename]
            task_info['status'] = status
            task_info['last_updated'] = datetime.now()
            
            if metadata:
                if 'metadata' not in task_info:
                    task_info['metadata'] = {}
                task_info['metadata'].update(metadata)
            
            self.logger.info(f"File {filename} processing status updated to {status}")
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to update file {filename} processing status: {e}")
            return False

    def complete_processing_task(self, filename, success=True, error_msg=None):
        if filename not in self.active_processing:
            self.logger.warning(f"No active processing task found for {filename}")
            return False
            
        try:
            task_info = self.active_processing[filename]
            processing_time = (datetime.now() - task_info['started_at']).total_seconds()
            
            self.logger.info(f"Completing processing task for {filename} (took {processing_time:.2f}s)")
            
            if success:
                self.processing_stats['total_processed'] += 1
            else:
                self.processing_stats['failed_count'] += 1
            
            task_info['completed_at'] = datetime.now()
            task_info['processing_time_seconds'] = processing_time
            task_info['success'] = success
            task_info['error_message'] = error_msg
            
            del self.active_processing[filename]
            
            self.logger.info(f"Processing task completed for {filename} - Success: {success}")
            return True
            
        except Exception as e:
            self.logger.warning(f"Failed to complete processing task for {filename}: {e}")
            return False

    def rucio(self) -> requests.Session:
        if self._rucio:
            return self._rucio

        if not os.path.exists(self.x509_proxy):
            raise RuntimeError(f"Proxy not found at {self.x509_proxy}")
        
        verify = self.rucio_cafile if (self.rucio_cafile and os.path.exists(self.rucio_cafile)) else True

        s = requests.Session()
        base_headers = {
            "X-Rucio-Account": self.account,
            "X-Rucio-VO": self.rucio_vo,
            "X-Rucio-AppID": "processing-agent",
        }
        
        auth_url = f"{self.rucio_base}/auth/x509_proxy"
        
        try:
            r = s.get(auth_url, cert=(self.x509_proxy, self.x509_proxy), verify=verify, headers=base_headers, timeout=30)
            r.raise_for_status()
        except Exception as e:
            self.logger.error(f"Rucio authentication failed: {e}")
            raise
            
        token = r.headers.get("X-Rucio-Auth-Token")
        if not token:
            raise RuntimeError("No X-Rucio-Auth-Token in auth response headers")
        
        s.headers.update(base_headers | {"X-Rucio-Auth-Token": token})
        s.verify = verify
        s.cert = (self.x509_proxy, self.x509_proxy)
        self._rucio = s
        return s

    def rucio_create_dataset(self, scope: str, name: str, open_: bool = True):
        s = self.rucio()
        url = f"{self.rucio_base}/dids/{scope}/{name}"
        r = s.post(url, json={"type": "dataset"})
        if r.status_code not in (201, 409):
            raise RuntimeError(f"Create dataset failed: {r.status_code} {r.text}")
        try:
            self.rucio_set_status(scope, name, open_=open_)
        except Exception as e:
            self.logger.warning(f"Rucio open hint: {e}", extra={"dataset": f"{scope}:{name}"})

    def rucio_set_status(self, scope: str, name: str, open_: bool):
        s = self.rucio()
        url = f"{self.rucio_base}/dids/{scope}/{name}/status"
        r = s.put(url, json={"open": bool(open_)})
        if r.status_code not in (200, 409):
            raise RuntimeError(f"Set status failed: {r.status_code} {r.text}")

    def rucio_attach_file(self, scope: str, dataset_name: str, stf_msg: dict):
        file_name = stf_msg.get("filename")
        size_bytes = stf_msg.get("size_bytes")
        adler32 = stf_msg.get("checksum")
        
        s = self.rucio()
        
        replica_url = f"{self.rucio_base}/replicas"
        rse = os.getenv('SWF_RUCIO_RSE', 'YOUR_STORAGE_ELEMENT')
        replica_payload = {
            "rse": rse,
            "files": [{
                "scope": scope,
                "name": file_name,
                "bytes": int(size_bytes) if size_bytes is not None else None,
                "adler32": adler32 if adler32 else None,
            }]
        }
        r = s.post(replica_url, json=replica_payload)
        if r.status_code not in (201, 409):
            raise RuntimeError(f"Register replica failed: {r.status_code} {r.text}")
        
        attach_url = f"{self.rucio_base}/dids/{scope}/{dataset_name}/dids"
        attach_payload = {
            "dids": [{
                "scope": scope,
                "name": file_name,
            }]
        }
        r = s.post(attach_url, json=attach_payload)
        if r.status_code not in (201, 409):
            raise RuntimeError(f"Attach failed: {r.status_code} {r.text}")

    def _dataset_name_for_run(self, run_id: str) -> str:
        return f"{run_id}.stf.ds"

    def _dataset_did_for_run(self, run_id: str) -> str:
        return f"{self.scope}:{self._dataset_name_for_run(run_id)}"

    def handle_run_imminent(self, msg):
        run_id = msg.get('run_id')
        dataset_name = self._dataset_name_for_run(run_id)
        self.logger.info("run_imminent: ensure open dataset", extra={"run_id": run_id})
        
        self.run_datasets[run_id] = {
            'dataset_name': dataset_name,
            'created_at': datetime.now(),
            'file_count': 0,
            'status': 'preparing'
        }
        
        try:
            self.rucio_create_dataset(self.scope, dataset_name, open_=True)
            self.run_datasets[run_id]['status'] = 'open'
        except Exception as e:
            self.logger.warning(f"Rucio dataset creation hint: {e}")
            self.run_datasets[run_id]['status'] = 'error'
        
        self.report_agent_status('OK', f'Preparing for run {run_id}')
        self.logger.info("run_imminent handled", extra={"run_id": run_id})

    def handle_start_run(self, msg):
        run_id = msg.get('run_id')
        self.logger.info("start_run", extra={"run_id": run_id})
        
        if run_id in self.run_datasets:
            self.run_datasets[run_id]['status'] = 'active'
        
        self.send_processing_agent_heartbeat()
        self.logger.info("start_run handled", extra={"run_id": run_id})

    def handle_data_ready(self, msg):
        run_id = msg.get('run_id')
        stf_filename = msg.get('filename')
        self.logger.info("data_ready received", extra={"run_id": run_id, "stf_filename": stf_filename})
        
        task_id = self.register_processing_task(stf_filename, msg)
        
        try:
            self.update_file_processing_status(stf_filename, 'processing', {
                'stage': 'rucio_attachment',
                'run_id': run_id
            })
            
            self.rucio_attach_file(self.scope, self._dataset_name_for_run(run_id), msg)
            
            if run_id in self.run_datasets:
                self.run_datasets[run_id]['file_count'] += 1
            
            self.complete_processing_task(stf_filename, success=True)
            
            self.logger.info("data_ready handled successfully",
                           extra={"run_id": run_id, "stf_filename": stf_filename})
            
        except Exception as e:
            error_msg = f"Rucio attach failed: {e}"
            self.logger.error(error_msg, extra={"run_id": run_id, "stf_filename": stf_filename})
            
            self.update_file_processing_status(stf_filename, 'failed', {
                'error': str(e),
                'stage': 'rucio_attachment'
            })
            
            self.complete_processing_task(stf_filename, success=False, error_msg=error_msg)

    def handle_end_run(self, msg):
        run_id = msg.get('run_id')
        total_files = msg.get('total_files', 0)
        self.logger.info("end_run: closing dataset & submitting PanDA", extra={"run_id": run_id})
        
        if run_id in self.run_datasets:
            self.run_datasets[run_id]['status'] = 'closing'
        
        active_tasks = len(self.active_processing)
        if active_tasks > 0:
            self.report_agent_status('WARNING',
                                   f'Run {run_id} ended with {active_tasks} tasks still processing')
            self.logger.warning(f"Run {run_id} ending with {active_tasks} active tasks")
        
        try:
            self.rucio_set_status(self.scope, self._dataset_name_for_run(run_id), open_=False)
            if run_id in self.run_datasets:
                self.run_datasets[run_id]['status'] = 'closed'
        except Exception as e:
            self.logger.warning(f"Rucio close hint: {e}")
        
        try:
            self._submit_panda_open_dataset(run_id)
            if run_id in self.run_datasets:
                self.run_datasets[run_id]['status'] = 'submitted'
                self.run_datasets[run_id]['completed_at'] = datetime.now()
        except Exception as e:
            self.processing_stats['failed_count'] += 1
            self.logger.error(f"PanDA submission failed: {e}", extra={"run_id": run_id})
            if run_id in self.run_datasets:
                self.run_datasets[run_id]['status'] = 'submission_failed'
        else:
            files_processed = self.run_datasets.get(run_id, {}).get('file_count', 0)
            self.report_agent_status('OK',
                                   f'Run {run_id} completed: {files_processed} files processed, PanDA job submitted')
            self.logger.info("PanDA submission initiated", extra={"run_id": run_id})

    def _submit_panda_open_dataset(self, run_id: str):
        filename = f"{run_id}.stf"
        generated_uuid = str(uuid.uuid4())
        out_ds = f"user.{self.nickname}.{filename}.{generated_uuid}"
        
        stf_message = {
            "run_id": run_id,
            "filename": filename,
            "state": "processing",
            "substate": "ready"
        }
        stf_json = json.dumps(stf_message)
        exec_cmd = f"./my_script.sh '{stf_json}'"

        prun_args = [
            "--exec", exec_cmd,
            "--outDS", out_ds,
            "--nJobs", "1",
            "--vo", os.getenv('PANDA_VO', 'your_vo'),
            "--site", os.getenv('PANDA_SITE', 'YOUR_COMPUTE_SITE'),
            "--prodSourceLabel", "test",
            "--workingGroup", self.panda_auth_vo,
            "--noBuild",
            "--outputs", "myout.txt",
        ]

        params = PrunScript.main(True, prun_args)
        params["taskName"] = f"stf_{stf_message.get('state', 'unknown')}_{stf_message.get('substate', 'unknown')}_{generated_uuid[:8]}"
        params["userName"] = self.nickname

        c = panda_api.get_api()
        status, result = c.submit_task(params)

        if status == 0:
            jedi_task_id = None
            if isinstance(result, (list, tuple)) and len(result) >= 3:
                jedi_task_id = result[2]
            elif isinstance(result, dict):
                jedi_task_id = result.get("jediTaskID") or result.get("jediTaskId")
            self.logger.info("PanDA submitted", extra={"run_id": run_id, "jediTaskID": jedi_task_id})
            print(f"✔ PanDA submitted. JediTaskID: {jedi_task_id}")
            print(f"→ Monitor: {self.pandamon}/task/{jedi_task_id}/")
        else:
            raise RuntimeError(f"submit_task failed: status={status}, result={result}")


if __name__ == "__main__":
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("requests").setLevel(logging.WARNING)
    agent = ProcessingAgent()
    agent.run()
