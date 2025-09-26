y# Workflow Example Design and Implementation

## Overview

This document describes the design and implementation of a comprehensive workflow example for the SWF testbed. The goal is to create a realistic end-to-end simulation that exercises all testbed components and populates the database with authentic workflow data.

## Problem Statement

The testbed needs a working integration example that:
- Demonstrates realistic multi-facility workflows (BNL and JLab)
- Exercises complete STF pipeline from generation to completion
- Populates the monitoring database with real workflow data
- Validates agent interactions and message passing
- Provides a foundation for monitor dashboard development

## Design Considerations

### Workflow Description Format

**Requirement**: Human-readable, programmatically parseable workflow definitions that support:
- Parallel execution across multiple facilities
- Complex dependencies ("A must run before B")
- Integration with PanDA distributed workload management
- Natural expression of concurrent operations

**Options Evaluated**:

1. **YAML Enhancement**: Extending current `schedule-rt.yml` format
   - Pros: Familiar, simple for basic cases
   - Cons: Becomes unwieldy for complex parallel workflows and dependencies

2. **Python DSL**: Direct SimPy process definitions
   - Pros: Full SimPy capabilities, no translation needed
   - Cons: Workflows expressed in Python code that is rather opaque to non-programmers

3. **WDL/DAG**: Workflow Definition Language or Directed Acyclic Graph
   - Pros: PanDA supported, industry standard
   - Cons: Not used by ePIC, additional learning curve

4. **Snakemake**: Workflow management system
   - Pros: Already used by ePIC, PanDA compatible, natural parallel execution, easy translation to SimPy
   - Cons: Additional dependency

**Decision**: **Snakemake** chosen for optimal impedance matching:
- ePIC developers already familiar with Snakemake workflows
- PanDA supports Snakemake for workflow orchestration
- Natural parallel execution and dependency management
- Easy translation to SimPy for testbed simulation

### Multi-Facility Architecture

Real ePIC streaming workflow operates across two symmetric computing facilities:
- **BNL (Brookhaven National Laboratory)**: Primary facility performing all workflow functions
- **JLab (Jefferson Lab)**: Primary facility performing all workflow functions in shared operation with BNL

Both facilities operate as equals in a distributed computing model, each capable of handling the full range of workflow operations.

**Workflow Requirements**:
```python
# Example parallel facility operations
workflows:
  physics_run_001:
    parallel_actions:
      - facility: "BNL"
        agents: ["data-agent-1", "processing-agent-1"] 
        workflow: "STF_processing_pipeline"
      - facility: "JLab" 
        agents: ["data-agent-2", "fastmon-agent-e2"]
        workflow: "STF_processing_pipeline"
      - facility: "both"
        agents: ["daqsim-agent-1"]
        workflow: "STF_generation"
```

### SimPy Integration Strategy

The testbed uses SimPy for discrete event simulation but current usage is minimal. Enhanced utilization includes:

- **Process synchronization**: `env.all_of()`, `env.any_of()` for coordinating parallel operations
- **Resource management**: Modeling limited compute/network resources at each facility
- **Event-driven coordination**: Agents responding to STF availability events
- **Real-time execution**: Proper time scaling for realistic simulation
- **Statistics collection**: Throughput, latencies, queue depths for performance analysis

### Snakemake-to-SimPy Translation

**Core Concept**: Single workflow definition serves dual purposes:
1. **PanDA execution**: Snakemake orchestrates workflows via PanDA
2. **Testbed simulation**: Translator converts Snakemake rules to SimPy processes

**Translation Mapping**:
- Snakemake rules → SimPy processes
- Rule dependencies → Process synchronization
- Resource constraints → Facility assignments  
- Shell commands → Agent interactions

```python
# Snakemake workflow
rule process_stf_bnl:
    input: "stf/{run_id}/stf_{id}.dat"
    output: "processed/{run_id}/stf_{id}_bnl.dat"
    params: facility="BNL", duration=30
    shell: "process_stf.py {input} {output}"

# Translated SimPy process (simulation)
def process_stf_bnl_sim(env, stf_data):
    print(f"BNL processing STF {stf_data.id} at time {env.now}")
    yield env.timeout(30)  # Simulate 30s processing
    print(f"BNL processing complete at time {env.now}")
```

## State Machine Integration

Current state machine is well-documented in the daqsim-agent:

**States**: no_beam, beam, run, calib, test  
**Substates**: not_ready, ready, physics, standby, lumi, eic, epic, daq, calib

**Integration Requirements**:
1. Represent state machine in Django models for database storage
2. Provide REST API endpoints for state interrogation
3. Drive workflow execution based on state transitions
4. Enable programmatic state machine updates

## Implementation Plan

### Phase 1: Foundation
1. Create Snakemake workflow example for multi-facility STF processing
2. Implement Snakemake-to-SimPy translator
3. Extend Django models to include state machine representation

### Phase 2: Integration
1. Build workflow executor in `example_agents/`
2. Elaborate existing example agents to participate in realistic workflows
3. Add REST API endpoints for workflow and state machine interrogation

### Phase 3: Validation
1. End-to-end workflow testing across all components
2. Performance optimization and scaling validation

**Monitor Dashboard Development**: Proceeds in parallel throughout all phases. The monitor provides our complete view into system operations and must be continuously updated as workflow capabilities expand.

## Expected Outcomes

This implementation will provide:
- **Authentic test data**: Database populated through realistic workflow execution
- **Component validation**: All testbed components exercised in realistic scenarios
- **Development foundation**: Basis for monitor dashboard and agent enhancement
- **Testbed completeness**: Full-featured testbed for ePIC streaming workflow development
- **Integration framework**: Reusable foundation for additional workflow types

## References

- [Snakemake Documentation](https://snakemake.readthedocs.io/)
- [SimPy Documentation](https://simpy.readthedocs.io/)
- [PanDA Workflow Management](https://panda-wms.readthedocs.io/)
- [ePIC Streaming Computing Model Report](https://zenodo.org/records/14675920)