class WorkflowExecutor:
    def __init__(self, parameters):
        self.parameters = parameters
        self.stf_sample_count = 0
        self.slice_count = 0
        self.worker_count = 0

    def execute(self, env):
        # Phase 1: Run Imminent - broadcast and ramp up workers
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_imminent

        # Workers ramp up (staggered over worker_rampup_time)
        yield env.timeout(self.parameters['run_imminent_delay'])

        # Phase 2: Run Running - process STF samples
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_start

        # Process STF samples during run
        yield from self.process_run_duration(env, self.parameters['run_duration'])

        # Phase 3: Run End - graceful shutdown
        yield env.timeout(self.parameters['broadcast_delay'])  # broadcast_run_end
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

        # Create slices for this sample
        for slice_num in range(self.parameters['slices_per_sample']):
            self.slice_count += 1

        # Small delay for slice creation
        yield env.timeout(0.1)
