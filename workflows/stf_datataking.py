class WorkflowExecutor:
    def __init__(self, config, runner, execution_id):
        self.config = config
        self.runner = runner
        self.execution_id = execution_id
        self.stf_sequence = 0
        self.run_id = None

        # Get namespace from testbed config for message routing
        self.namespace = config.get('testbed', {}).get('namespace')

        # Build merged params: daq_state_machine base, with all parameter sections merged
        self.daq = config.get('daq_state_machine', {}).copy()

        # Auto-discover and merge ALL non-system parameter sections
        # This allows overrides to work regardless of which section they're in
        SYSTEM_SECTIONS = {'workflow', 'testbed', 'agents', 'source', 'git_version'}
        for section_name, section_values in config.items():
            if (section_name not in SYSTEM_SECTIONS
                and section_name != 'daq_state_machine'  # already loaded as base
                and isinstance(section_values, dict)):
                # Merge this parameter section (later sections override earlier ones)
                self.daq = {**self.daq, **section_values}

    def execute(self, env):
        # Generate run ID for this execution
        from swf_common_lib.api_utils import get_next_run_number
        self.run_id = get_next_run_number(
            self.runner.monitor_url,
            self.runner.api_session,
            self.runner.logger
        )

        # Initialize state machine for this execution
        self.runner.initialize_state(self.run_id, self.execution_id, self.config)

        # State 1: no_beam / not_ready (Collider not operating)
        yield env.timeout(self.daq['no_beam_not_ready_delay'])

        # State 2: beam / not_ready (Run start imminent) + broadcast run imminent
        yield env.process(self.broadcast_run_imminent(env))
        yield env.timeout(self.daq['broadcast_delay'])
        yield env.timeout(self.daq['beam_not_ready_delay'])

        # State 3: beam / ready (Ready for physics)
        yield env.timeout(self.daq['beam_ready_delay'])

        # Physics periods loop with standby between them
        period = 0
        while self.daq['physics_period_count'] == 0 or period < self.daq['physics_period_count']:
            # Broadcast appropriate message
            if period == 0:
                yield env.process(self.broadcast_run_start(env))
                yield env.timeout(self.daq['broadcast_delay'])
            else:
                yield env.process(self.broadcast_resume_run(env))
                yield env.timeout(self.daq['broadcast_delay'])

            # STF generation during physics
            yield from self.generate_stfs_during_physics(env, self.daq['physics_period_duration'])

            period += 1

            # Standby between physics periods (always for infinite mode, except after last for finite mode)
            if self.daq['physics_period_count'] == 0 or period < self.daq['physics_period_count']:
                yield env.process(self.broadcast_pause_run(env))
                yield env.timeout(self.daq['broadcast_delay'])
                yield env.timeout(self.daq['standby_duration'])

        # State 7: beam / not_ready + broadcast run end
        yield env.process(self.broadcast_run_end(env))
        yield env.timeout(self.daq['broadcast_delay'])
        yield env.timeout(self.daq['beam_not_ready_end_delay'])

        # State 8: no_beam / not_ready (final) - no delay needed

    def generate_stfs_during_physics(self, env, duration_seconds):
        interval = self.daq['stf_interval']
        stf_count = self.daq.get('stf_count')

        if stf_count:
            # Count-based: generate exactly stf_count files
            for i in range(stf_count):
                yield from self.generate_single_stf(env)
                if i < stf_count - 1:  # Don't wait after last STF
                    yield env.timeout(interval)
        else:
            # Duration-based: generate STFs for physics_period_duration
            start_time = env.now
            while (env.now - start_time) < duration_seconds:
                yield from self.generate_single_stf(env)
                if (env.now - start_time) < duration_seconds:
                    yield env.timeout(interval)

    def generate_single_stf(self, env):
        self.stf_sequence += 1
        stf_filename = f"swf.{self.run_id}.{self.stf_sequence:06d}.stf"

        # Broadcast STF generation
        yield env.process(self.broadcast_stf_gen(env, stf_filename))

        generation_time = self.daq['stf_generation_time']
        yield env.timeout(generation_time)

    def broadcast_run_imminent(self, env):
        """Broadcast run imminent message - triggers dataset creation and worker preparation."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "run_imminent",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "beam",
            "substate": "not_ready"
        }

        destination = '/topic/epictopic'
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
        yield env.timeout(0.1)

    def broadcast_run_start(self, env):
        """Broadcast run start message - triggers PanDA task creation."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "start_run",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "run",
            "substate": "physics"
        }

        destination = '/topic/epictopic'
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

    def broadcast_pause_run(self, env):
        """Broadcast run pause message - entering standby."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "pause_run",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "run",
            "substate": "standby",
            "reason": "Brief standby period"
        }

        destination = '/topic/epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted pause_run message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "pause_run"
            }
        )
        yield env.timeout(0.1)

    def broadcast_resume_run(self, env):
        """Broadcast run resume message - returning to physics."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "resume_run",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "run",
            "substate": "physics"
        }

        destination = '/topic/epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted resume_run message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "resume_run"
            }
        )
        yield env.timeout(0.1)

    def broadcast_run_end(self, env):
        """Broadcast run end message."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "end_run",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "total_stf_files": self.stf_sequence
        }

        destination = '/topic/epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted run_end message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "msg_type": "end_run",
                "total_stf_files": self.stf_sequence
            }
        )
        yield env.timeout(0.1)

    def broadcast_stf_gen(self, env, stf_filename):
        """Broadcast STF generation."""
        from datetime import datetime

        # namespace is also auto-injected by BaseAgent.send_message()
        message = {
            "msg_type": "stf_gen",
            "namespace": self.namespace,
            "execution_id": self.execution_id,
            "run_id": self.run_id,
            "filename": stf_filename,
            "sequence": self.stf_sequence,
            "timestamp": datetime.now().isoformat(),
            "simulation_tick": env.now,
            "state": "run",
            "substate": "physics"
        }

        destination = '/topic/epictopic'
        self.runner.send_message(destination, message)
        self.runner.logger.info(
            "Broadcasted stf_gen message",
            extra={
                "simulation_tick": env.now,
                "execution_id": self.execution_id,
                "run_id": self.run_id,
                "stf_filename": stf_filename,
                "msg_type": "stf_gen"
            }
        )
        yield env.timeout(0.1)
