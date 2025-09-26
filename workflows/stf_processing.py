class WorkflowExecutor:
    def __init__(self, parameters):
        self.parameters = parameters
        self.stf_sequence = 0

    def execute(self, env):
        # State 1: no_beam / not_ready (Collider not operating)
        yield env.timeout(self.parameters['no_beam_not_ready_delay'])

        # State 2: beam / not_ready (Run start imminent) + broadcast run imminent
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_imminent
        yield env.timeout(self.parameters['beam_not_ready_delay'])

        # State 3: beam / ready (Ready for physics)
        yield env.timeout(self.parameters['beam_ready_delay'])

        # Physics periods loop with standby between them
        period = 0
        while self.parameters['physics_period_count'] == 0 or period < self.parameters['physics_period_count']:
            # Broadcast appropriate message
            if period == 0:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_start
            else:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_resume_run

            # STF generation during physics
            yield from self.generate_stfs_during_physics(env, self.parameters['physics_period_duration'])

            period += 1

            # Standby between physics periods (always for infinite mode, except after last for finite mode)
            if self.parameters['physics_period_count'] == 0 or period < self.parameters['physics_period_count']:
                yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_pause_run
                yield env.timeout(self.parameters['standby_duration'])

        # State 7: beam / not_ready + broadcast run end
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_end
        yield env.timeout(self.parameters['beam_not_ready_end_delay'])

        # State 8: no_beam / not_ready (final) - no delay needed

    def generate_stfs_during_physics(self, env, duration_seconds):
        interval = self.parameters['stf_interval']
        start_time = env.now

        while (env.now - start_time) < duration_seconds:
            yield from self.generate_single_stf(env)

            # Only wait for interval if not at end of physics period
            if (env.now - start_time) < duration_seconds:
                yield env.timeout(interval)

    def generate_single_stf(self, env):
        self.stf_sequence += 1
        generation_time = self.parameters['stf_generation_time']
        yield env.timeout(generation_time)