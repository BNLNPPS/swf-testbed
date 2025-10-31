class WorkflowExecutor:
    def __init__(self, parameters, runner, execution_id):
        self.parameters = parameters
        self.runner = runner
        self.execution_id = execution_id
        self.stf_sample_count = 0
        self.slice_count = 0
        self.worker_count = 0
        self.run_id = None

    def execute(self, env):
        # Generate run ID for this execution
        from swf_common_lib.api_utils import get_next_run_number
        self.run_id = get_next_run_number(
            self.runner.monitor_url,
            self.runner.api_session,
            self.runner.logger
        )

        # Phase 1: Run Imminent - broadcast and ramp up workers
        yield env.process(self.broadcast_run_imminent(env))
        yield env.timeout(self.parameters['broadcast_delay'])

        # Workers ramp up (staggered over worker_rampup_time)
        yield env.timeout(self.parameters['run_imminent_delay'])

        # Phase 2: Run Running - process STF samples
        yield env.process(self.broadcast_run_start(env))
        yield env.timeout(self.parameters['broadcast_delay'])

        # Process STF samples during run
        yield from self.process_run_duration(env, self.parameters['run_duration'])

        # Phase 3: Run End - graceful shutdown
        yield env.process(self.broadcast_run_end(env))
        yield env.timeout(self.parameters['broadcast_delay'])
        yield env.timeout(self.parameters['worker_rampdown_time'])

    def process_run_duration(self, env, duration_seconds):
        """Generate STF samples and slices during run."""
        stf_interval = 1.0 / self.parameters['stf_rate']
        start_time = env.now

        while (env.now - start_time) < duration_seconds:
            # Generate STF sample (FastMon samples from STF)
            yield from self.generate_stf_sample(env)

            # Wait for next STF
            remaining_time = duration_seconds - (env.now - start_time)
            if remaining_time > 0:
                yield env.timeout(min(stf_interval, remaining_time))

    def generate_stf_sample(self, env):
        """FastMon creates STF sample and PA creates slices."""
        self.stf_sample_count += 1

        # Generate TF sample filename (FastMon output)
        tf_filename = f"tf.{self.run_id}.{self.stf_sample_count:06d}.sample"

        # Create slices for this sample
        slices = []
        for slice_num in range(self.parameters['slices_per_sample']):
            self.slice_count += 1
            slices.append({
                'slice_id': slice_num + 1,
                'tf_filename': tf_filename
            })

        # Broadcast TF sample message
        yield env.process(self.broadcast_tf_sample(env, tf_filename, slices))

    def broadcast_run_imminent(self, env):
        """Broadcast run imminent message - triggers worker preparation."""
        from datetime import datetime

        message = {
            "msg_type": "run_imminent",
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "target_worker_count": self.parameters['target_worker_count'],
            "slices_per_sample": self.parameters['slices_per_sample'],
            "stf_rate": self.parameters['stf_rate']
        }

        # Send to workflow topic
        destination = 'epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted run_imminent message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "run_imminent"
            }
        )
        yield env.timeout(0.1)  # Brief broadcast time

    def broadcast_run_start(self, env):
        """Broadcast run start message - triggers slice processing."""
        from datetime import datetime

        message = {
            "msg_type": "start_run",
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now
        }

        destination = 'epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted run_start message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "start_run"
            }
        )
        yield env.timeout(0.1)

    def broadcast_run_end(self, env):
        """Broadcast run end message - triggers worker shutdown."""
        from datetime import datetime

        message = {
            "msg_type": "end_run",
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "total_stf_samples": self.stf_sample_count,
            "total_slices": self.slice_count
        }

        destination = 'epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted run_end message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "end_run",
                "total_stf_samples": self.stf_sample_count,
                "total_slices": self.slice_count
            }
        )
        yield env.timeout(0.1)

    def broadcast_tf_sample(self, env, tf_filename, slices):
        """Broadcast TF sample ready for processing."""
        from datetime import datetime

        message = {
            "msg_type": "data_ready",
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "tf_filename": tf_filename,
            "slices": slices,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now
        }

        destination = 'epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted TF sample data_ready message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "tf_filename": tf_filename,
                "slice_count": len(slices),
                "msg_type": "data_ready"
            }
        )
        yield env.timeout(0.1)
