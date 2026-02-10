"""
Fast Processing Agent: Creates TF slices from STF samples for PanDA workers.

This agent:
1. Receives tf_file_registered messages from FastMon Agent (via epictopic)
2. Creates TF slices from STF samples
3. Pushes TF slices to PanDA transformer queue (/queue/panda.transformer.slices)
4. Maintains RunState and TFSlice records in the monitor database

Pipeline: FastMon Agent [tf_file_registered] -> Fast Processing Agent [TF slices] -> PanDA Workers

Message format specification: https://github.com/wguanicedew/iDDS/blob/dev/main/prompt.md
"""

import uuid
from datetime import datetime
from swf_common_lib.base_agent import BaseAgent


class FastProcessingAgent(BaseAgent):
    """
    Fast Processing Agent for TF slice creation and distribution.

    Subscribes to epictopic, receives tf_file_registered from FastMon,
    creates TF slices, and pushes them to the PanDA transformer queue.
    """

    # Queue for transformer workers (from Wen's iDDS design)
    TRANSFORMER_QUEUE = '/topic/panda.slices'

    # Queue for worker broadcasts
    WORKER_BROADCAST_TOPIC = '/topic/panda.workers'

    # Queue for transformer results
    TRANSFORMER_RESULTS_QUEUE = '/queue/panda.results.fastprocessing'

    def __init__(self, debug=False, config_path=None):
        super().__init__(
            agent_type='Fast_Processing',
            subscription_queues=['/topic/epictopic', self.TRANSFORMER_RESULTS_QUEUE],
            debug=debug,
            config_path=config_path
        )

        # Workflow parameters (populated on run_imminent)
        self.workflow_params = {}

        # Processing state
        self.tf_files_received = 0
        self.slices_created = 0

        # Statistics
        self.stats = {
            'tf_files_received': 0,
            'slices_created': 0,
            'slices_sent': 0,
            'results_received': 0,
            'results_done': 0,
            'results_failed': 0
        }

    def on_message(self, frame):
        """Handle incoming workflow messages."""
        message_data, msg_type = self.log_received_message(frame)
        if message_data is None:
            return

        # Extract run context from each message (agents may start mid-run)
        self._update_run_context(message_data)

        try:
            if msg_type == 'run_imminent':
                self.handle_run_imminent(message_data)
            elif msg_type == 'start_run':
                self.handle_start_run(message_data)
            elif msg_type == 'tf_file_registered':
                self.handle_tf_file_registered(message_data)
            elif msg_type == 'pause_run':
                self.handle_pause_run(message_data)
            elif msg_type == 'resume_run':
                self.handle_resume_run(message_data)
            elif msg_type == 'end_run':
                self.handle_end_run(message_data)
            elif msg_type == 'slice_result':
                self.handle_slice_result(message_data)
            else:
                self.logger.debug(f"Ignoring message type: {msg_type}")
        except Exception as e:
            self.logger.error(f"Error processing {msg_type}: {e}",
                              extra=self._log_extra(error=str(e)))
            import traceback
            self.logger.error(traceback.format_exc())

    def _update_run_context(self, message_data):
        """
        Update run context from message. Agents may start mid-run and miss run_imminent,
        so we extract run_id/execution_id from every message and fetch params if needed.
        """
        run_id = message_data.get('run_id')
        execution_id = message_data.get('execution_id')

        # Update current run context if provided
        if run_id and run_id != self.current_run_id:
            self.current_run_id = run_id
            # Reset stats for new run
            self.tf_files_received = 0
            self.slices_created = 0
            self.stats = {
                'tf_files_received': 0,
                'slices_created': 0,
                'slices_sent': 0
            }

        if execution_id and execution_id != self.current_execution_id:
            self.current_execution_id = execution_id
            # Fetch workflow params if we don't have them
            if not self.workflow_params:
                self.workflow_params = self._fetch_workflow_parameters(execution_id)
                if self.workflow_params:
                    import json
                    self.logger.info(f"Workflow parameters loaded (mid-run): {json.dumps(self.workflow_params, indent=2, sort_keys=True)}")

    def handle_run_imminent(self, message_data):
        """Handle run_imminent message."""
        self.logger.info(
            f"Run imminent: execution_id={self.current_execution_id}, run_id={self.current_run_id}",
            extra=self._log_extra()
        )

        self._log_system_event('run_imminent', {
            'execution_id': self.current_execution_id,
            'target_worker_count': self.workflow_params.get("fast_processing", {}).get('target_worker_count', 0),
            'stf_sampling_rate': self.workflow_params.get("fast_processing", {}).get('stf_sampling_rate', 0),
            'slices_per_sample': self.workflow_params.get("fast_processing", {}).get('slices_per_sample', 0)
        })

        # Build and broadcast a run_imminent message to workers
        try:
            import json
            from datetime import datetime as _dt

            # Compose message similar to _send_slice_to_queue format.
            # Put the incoming message_data inside 'content' and add execution_id
            # and target_worker_count so workers know how many to spin up.
            content = dict(message_data or {})
            content.update({
                'execution_id': self.current_execution_id,
                'target_worker_count': self.workflow_params.get("fast_processing", {}).get('target_worker_count', 1),
                'slice_processing_time': self.workflow_params.get("fast_processing", {}).get('slice_processing_time', 1),
                'worker_rampup_time': self.workflow_params.get("fast_processing", {}).get('worker_rampup_time', 1),
                'worker_rampdown_time': self.workflow_params.get("fast_processing", {}).get('worker_rampdown_time', 1)
            })

            message = {
                'msg_type': 'run_imminent',
                'run_id': self.current_run_id,
                'created_at': _dt.utcnow().isoformat(),
                'content': content
            }

            headers = {
                'persistent': 'false',
                'vo': 'eic',
                'msg_type': 'run_imminent',
                'namespace': message_data.get('namespace', 'default'),
                'run_id': str(self.current_run_id)
            }

            # Topic for worker broadcasts
            worker_topic = self.WORKER_BROADCAST_TOPIC

            self.conn.send(
                destination=worker_topic,
                body=json.dumps(message),
                headers=headers
            )

            self.logger.info(f"Broadcasted run_imminent to workers: {worker_topic}",
                             extra=self._log_extra(destination=worker_topic))
        except Exception as e:
            self.logger.error(f"Failed to broadcast run_imminent to workers: {e}",
                              extra=self._log_extra(error=str(e)))

    def handle_start_run(self, message_data):
        """Handle start_run: Update RunState phase to 'physics'."""
        self.logger.info(f"Run started: run_id={self.current_run_id}",
                         extra=self._log_extra())

        # Agent is now actively processing this run
        self.set_processing()

        self._update_run_state(phase='physics', state='running', substate='physics')

        self._log_system_event('start_run', {
            'execution_id': self.current_execution_id
        })

    def handle_tf_file_registered(self, message_data):
        """
        Handle tf_file_registered from FastMon: Create TF slices, push to worker queue.
        """
        tf_filename = message_data.get('tf_filename')
        stf_filename = message_data.get('stf_filename')

        self.stats['tf_files_received'] += 1
        self.tf_files_received += 1

        self.logger.info(f"TF file registered: {tf_filename} (from STF: {stf_filename})",
                         extra=self._log_extra(tf_filename=tf_filename, stf_filename=stf_filename))

        # Get slices_per_sample from workflow params
        fast_processing = self.workflow_params.get('fast_processing', {})
        slices_per_sample = fast_processing.get('slices_per_sample', 15)

        # Create TF slices from this STF sample
        slices = self._create_tf_slices(stf_filename, slices_per_sample)

        # Push each slice to transformer queue
        for slice_data in slices:
            self._send_slice_to_queue(slice_data)

        # Update RunState with slice counts
        self._update_run_state_slices(len(slices))

        # Log event
        self._log_system_event('tf_file_processed', {
            'tf_filename': tf_filename,
            'stf_filename': stf_filename,
            'slices_created': len(slices)
        })

    def handle_pause_run(self, message_data):
        """Handle pause_run: Update RunState to standby."""
        self.logger.info(f"Run paused: run_id={self.current_run_id}",
                         extra=self._log_extra())

        self._update_run_state(substate='standby')

        self._log_system_event('pause_run', {
            'execution_id': self.current_execution_id
        })

    def handle_resume_run(self, message_data):
        """Handle resume_run: Update RunState back to physics."""
        self.logger.info(f"Run resumed: run_id={self.current_run_id}",
                         extra=self._log_extra())

        self._update_run_state(substate='physics')

        self._log_system_event('resume_run', {
            'execution_id': self.current_execution_id
        })

    def handle_end_run(self, message_data):
        """Handle end_run: Update RunState to completed."""
        total_stf = message_data.get('total_stf_files', 0)

        self.logger.info(
            f"Run ended: run_id={self.current_run_id}, "
            f"tf_files_received={self.stats['tf_files_received']}, "
            f"slices_created={self.stats['slices_created']}",
            extra=self._log_extra(total_stf=total_stf,
                                  tf_files_received=self.stats['tf_files_received'],
                                  slices_created=self.stats['slices_created'])
        )

        self._update_run_state(phase='completed', state='ended', substate=None)

        self._log_system_event('end_run', {
            'execution_id': self.current_execution_id,
            'total_tf_files_received': self.stats['tf_files_received'],
            'total_slices_created': self.stats['slices_created'],
            'total_slices_sent': self.stats['slices_sent']
        })

        # Broadcast end_run to workers so they can perform any teardown/cleanup
        try:
            import json
            from datetime import datetime as _dt

            # Compose message similar to _send_slice_to_queue format.
            # Put the incoming message_data inside 'content' and add execution_id
            # and target_worker_count so workers can finalize appropriately.
            content = dict(message_data or {})
            content.update({
                'execution_id': self.current_execution_id
            })

            message = {
                'msg_type': 'end_run',
                'run_id': self.current_run_id,
                'created_at': _dt.utcnow().isoformat(),
                'content': content
            }

            headers = {
                'persistent': 'false',
                'vo': 'eic',
                'msg_type': 'end_run',
                'namespace': message_data.get('namespace', 'default'),
                'run_id': str(self.current_run_id)
            }

            worker_topic = self.WORKER_BROADCAST_TOPIC

            self.conn.send(
                destination=worker_topic,
                body=json.dumps(message),
                headers=headers
            )

            self.logger.info(f"Broadcasted end_run to workers: {worker_topic}",
                             extra=self._log_extra(destination=worker_topic))
        except Exception as e:
            self.logger.error(f"Failed to broadcast end_run to workers: {e}",
                              extra=self._log_extra(error=str(e)))

        # Clear current run state
        self.current_run_id = None
        self.current_execution_id = None
        self.workflow_params = {}

        # Agent is now idle, waiting for next run
        self.set_ready()

    def handle_slice_result(self, message_data):
        """Process slice_result messages from transformer workers."""
        self.stats['results_received'] += 1

        content = message_data.get('content', {})
        result = content.get('result') if isinstance(content, dict) else None

        self.logger.info(
            f"Slice result received: run={message_data.get('run_id')}, "
            f"state={content.get('state') if isinstance(content, dict) else 'unknown'}",
            extra=self._log_extra(run_id=message_data.get('run_id'))
        )

        # Track done/failed counts if result payload present
        try:
            inner_result = None
            if result and isinstance(result, dict):
                inner_result = result.get('result') if isinstance(result.get('result'), dict) else None

            state = content.get('state') or (inner_result.get('state') if inner_result else None)
            if state == 'done' or (inner_result and inner_result.get('processed')):
                self.stats['results_done'] += 1
            else:
                self.stats['results_failed'] += 1
        except Exception:
            pass

        # Update TFSlice record in database
        self._update_tfslice_from_result(message_data, content, result)

        # Log system event for observability
        self._log_system_event('slice_result', {
            'message': message_data,
            'state': content.get('state') if isinstance(content, dict) else None,
            'results_received': self.stats['results_received'],
            'results_done': self.stats['results_done'],
            'results_failed': self.stats['results_failed']
        })

        self.logger.info(f"Handled slice_result: run={message_data.get('run_id')}, msg={message_data.get('msg_type')}",
                         extra=self._log_extra(run_id=message_data.get('run_id')))

    # -------------------------------------------------------------------------
    # Helper methods
    # -------------------------------------------------------------------------

    def _fetch_workflow_parameters(self, execution_id):
        """Fetch workflow parameters from WorkflowExecution API."""
        try:
            result = self.call_monitor_api(
                'GET',
                f'/workflow-executions/{execution_id}/'
            )
            if result:
                return result.get('parameter_values', {})
            return {}
        except Exception as e:
            self.logger.error(f"Failed to fetch workflow parameters: {e}",
                              extra=self._log_extra(error=str(e)))
            return {}

    def _update_run_state(self, phase=None, state=None, substate=None):
        """Update RunState record."""
        update_data = {
            'state_changed_at': datetime.now().isoformat()
        }
        if phase is not None:
            update_data['phase'] = phase
        if state is not None:
            update_data['state'] = state
        if substate is not None:
            update_data['substate'] = substate

        try:
            result = self.call_monitor_api(
                'PATCH',
                f'/run-states/{self.current_run_id}/',
                update_data
            )
            if result:
                self.logger.debug(f"RunState updated: {update_data}", extra=self._log_extra())
        except Exception as e:
            self.logger.error(f"Error updating RunState: {e}",
                              extra=self._log_extra(error=str(e)))

    def _update_run_state_slices(self, new_slices_count):
        """Update RunState with new slice counts."""
        # We need to increment, so fetch current values first
        try:
            current = self.call_monitor_api('GET', f'/run-states/{self.current_run_id}/')
            if current:
                update_data = {
                    'stf_samples_received': current.get('stf_samples_received', 0) + 1,
                    'slices_created': current.get('slices_created', 0) + new_slices_count,
                    'slices_queued': current.get('slices_queued', 0) + new_slices_count,
                    'state_changed_at': datetime.now().isoformat()
                }
                self.call_monitor_api(
                    'PATCH',
                    f'/run-states/{self.current_run_id}/',
                    update_data
                )
        except Exception as e:
            self.logger.error(f"Error updating RunState slices: {e}",
                              extra=self._log_extra(error=str(e)))

    def _create_tf_slices(self, stf_filename, num_slices):
        """
        Create TF slice records in database.

        Returns list of slice data dictionaries for sending to queue.
        """
        slices = []

        # Assume ~1000 TFs per STF, divide into num_slices
        tfs_per_stf = 1000
        tfs_per_slice = tfs_per_stf // num_slices

        for i in range(num_slices):
            tf_first = i * tfs_per_slice
            tf_last = (i + 1) * tfs_per_slice - 1 if i < num_slices - 1 else tfs_per_stf - 1
            tf_count = tf_last - tf_first + 1

            # Generate TF filename for this slice
            tf_filename = f"{stf_filename.replace('.stf', '')}_slice_{i:03d}.tf"

            slice_data = {
                'slice_id': i,
                'tf_first': tf_first,
                'tf_last': tf_last,
                'tf_count': tf_count,
                'tf_filename': tf_filename,
                'stf_filename': stf_filename,
                'run_number': self.current_run_id,
                'status': 'queued',
                'retries': 0,
                'metadata': {
                    'execution_id': self.current_execution_id,
                    'created_by': self.agent_name
                }
            }

            # Create in database
            try:
                result = self.call_monitor_api('POST', '/tf-slices/', slice_data)
                if result:
                    self.stats['slices_created'] += 1
                    self.slices_created += 1
                    # Add database ID to slice data for queue message
                    slice_data['db_id'] = result.get('id')
                    slices.append(slice_data)
                    self.logger.debug(f"TFSlice created: {tf_filename}",
                                      extra=self._log_extra(tf_filename=tf_filename))
                else:
                    self.logger.warning(f"Failed to create TFSlice: {tf_filename}",
                                        extra=self._log_extra(tf_filename=tf_filename))
            except Exception as e:
                self.logger.error(f"Error creating TFSlice {tf_filename}: {e}",
                                  extra=self._log_extra(tf_filename=tf_filename, error=str(e)))

        return slices

    def _send_slice_to_queue(self, slice_data):
        """
        Send slice message to transformer queue.

        Message format per Wen's iDDS design.
        """
        # Build message per iDDS format
        message = {
            'msg_type': 'slice',
            'run_id': self.current_run_id,
            'created_at': datetime.utcnow().isoformat(),
            'content': {
                'run_id': self.current_run_id,
                'execution_id': self.current_execution_id,
                'req_id': str(uuid.uuid4()),
                'filename': slice_data['stf_filename'],
                'tf_filename': slice_data['tf_filename'],
                'slice_id': slice_data['slice_id'],
                'start': slice_data['tf_first'],
                'end': slice_data['tf_last'],
                'tf_count': slice_data['tf_count'],
                'state': 'queued',
                'substate': 'new'
            }
        }

        # Send to transformer queue with required headers
        try:
            import json
            headers = {
                'persistent': 'true',
                'ttl': str(12 * 3600 * 1000),  # 12 hours in ms
                'vo': 'eic',
                'msg_type': 'slice',
                'run_id': str(self.current_run_id)
            }

            self.conn.send(
                destination=self.TRANSFORMER_QUEUE,
                body=json.dumps(message),
                headers=headers
            )

            self.stats['slices_sent'] += 1
            self.logger.info(
                f"Slice sent to queue: {slice_data['tf_filename']} -> {self.TRANSFORMER_QUEUE}",
                extra=self._log_extra(tf_filename=slice_data['tf_filename'], destination=self.TRANSFORMER_QUEUE)
            )
        except Exception as e:
            self.logger.error(f"Failed to send slice to queue: {e}",
                              extra=self._log_extra(error=str(e)))

    def _log_system_event(self, event_type, event_data):
        """Log event to SystemStateEvent table."""
        event = {
            'timestamp': datetime.now().isoformat(),
            'run_number': self.current_run_id,
            'event_type': event_type,
            'state': self.workflow_params.get('state', 'unknown'),
            'substate': self.workflow_params.get('substate'),
            'event_data': event_data
        }

        try:
            self.call_monitor_api('POST', '/system-state-events/', event)
        except Exception as e:
            self.logger.debug(f"Failed to log system event: {e}",
                              extra=self._log_extra(event_type=event_type, error=str(e)))

    def _update_tfslice_from_result(self, message_data, content, result):
        """Update TFSlice record in database based on slice_result message."""
        try:
            # Extract slice information from the result
            # The result structure is: content -> result -> result (nested)
            inner_result = None
            if result and isinstance(result, dict):
                inner_result = result.get('result') if isinstance(result.get('result'), dict) else None

            # Get slice_id directly from the result data
            slice_id = None
            tf_filename = None
            if inner_result and isinstance(inner_result, dict):
                slice_id = inner_result.get('slice_id')
                tf_filename = inner_result.get('tf_filename')

            if slice_id is None:
                self.logger.debug("No slice_id in result, cannot update TFSlice record")
                return

            # Determine the final state
            state = content.get('state') if isinstance(content, dict) else None
            processed = inner_result.get('processed') if inner_result else None

            # Map worker state to slice status
            if state == 'done' or processed:
                slice_status = 'completed'
            else:
                slice_status = 'failed'

            # Build update payload
            update_data = {
                'status': slice_status,
                'processed_at': content.get('processed_at') or datetime.now().isoformat(),
                'metadata': {
                    'worker_hostname': content.get('hostname'),
                    'panda_task_id': content.get('panda_task_id'),
                    'panda_id': content.get('panda_id'),
                    'harvester_id': content.get('harvester_id'),
                    'processing_start_at': content.get('processing_start_at'),
                    'result': result
                }
            }

            # Update the slice directly using slice_id from the message
            run_id = message_data.get('run_id')
            try:
                # Query for the slice by run_id and slice_id to get the database ID
                slices = self.call_monitor_api(
                    'GET',
                    f'/tf-slices/?run_number={run_id}&slice_id={slice_id}'
                )

                if slices and isinstance(slices, list) and len(slices) > 0:
                    db_id = slices[0].get('id')
                    if db_id:
                        # Update the slice using database ID
                        api_result = self.call_monitor_api(
                            'PATCH',
                            f'/tf-slices/{db_id}/',
                            update_data
                        )
                        if api_result:
                            self.logger.info(
                                f"TFSlice updated: slice_id={slice_id}, tf_filename={tf_filename} -> {slice_status}",
                                extra=self._log_extra(slice_id=slice_id, tf_filename=tf_filename, status=slice_status)
                            )
                        else:
                            self.logger.warning(
                                f"Failed to update TFSlice: slice_id={slice_id}",
                                extra=self._log_extra(slice_id=slice_id)
                            )
                else:
                    self.logger.debug(
                        f"TFSlice not found for slice_id: {slice_id}, run: {run_id}",
                        extra=self._log_extra(slice_id=slice_id, run_id=run_id)
                    )
            except Exception as e:
                self.logger.error(
                    f"Error querying/updating TFSlice slice_id={slice_id}: {e}",
                    extra=self._log_extra(slice_id=slice_id, error=str(e))
                )

        except Exception as e:
            self.logger.error(
                f"Error updating TFSlice from result: {e}",
                extra=self._log_extra(error=str(e))
            )


if __name__ == "__main__":
    import argparse
    from pathlib import Path

    script_dir = Path(__file__).parent

    parser = argparse.ArgumentParser(
        description="Fast Processing Agent - samples STFs and creates TF slices"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--testbed-config", default=None,
                        help="Testbed config file (default: SWF_TESTBED_CONFIG env var or workflows/testbed.toml)")
    args = parser.parse_args()

    agent = FastProcessingAgent(debug=args.debug, config_path=args.testbed_config)
    agent.run()
