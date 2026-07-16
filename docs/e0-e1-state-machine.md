# The ePIC E0-E1 State Machine

The datataking state model at the E0-E1 interface is a set of states and
substates describing collider, detector, DAQ and calibration state.
State will be maintained in a database kept current in real time,
with the definitive version in E0, and mirrored in real time in E1. Current
state will also be carried as
operational metadata on the data and messages crossing the interface,
recording the state at the time of the message.
Downstream consumers — orchestration agents, monitoring, AI tools reading
through MCP (Model Context Protocol) — read from it the datataking context
of the data they are handling.

The first version of the model is implemented in the streaming workflow
testbed, where the simulated DAQ of the workflow layer drives all testbed
activity through it. The simulator messages system state to participants in the testbed, modeling E0 as definitive state source with real time transmission to E1 via messaging (and concurrent recording in the testbed database).
The state model and run structure are configuration, realized by the
workflow runner and the agents: the runner takes each run through the
state sequence, and the agents transmit and act on the state through the
common state management of the agent base class. State flows through the
system as messages — the run lifecycle (run imminent, start, pause and
resume, end) and data availability vocabulary, each message stamped with
the state and substate in effect — and data carries it too, in STF
filenames (`swf.<date>.<time>.<state>.<substate>.stf`). The baseline
workflows exercise most of the model in daily operation. Transitions are
configured run structure today rather than event-driven; event-triggered
state changes (a good-for-physics declaration, a fault dropping the
detector out of physics) and detector and machine influences on the
state are not yet modeled.

This document is the state model's definition, maintained
independently of the implementation. Evolution of the state model and its
transition rules is one of the open questions of the E0-E1 interface
named at the July 2026 collaboration meeting, with the interface to be
formalized in the ePIC Streaming Computing Model report (target September
2026); this document carries the current definition and its proposed
near term evolution into that work.

## States

| State | Meaning |
|---|---|
| `off` | Full shutdown — systems not operating |
| `no_beam` | Collider not operating |
| `beam` | Collider operating |
| `run` | Physics running |
| `calib` | Dedicated calibration period |
| `test` | Testing, debugging; any substates can be present during test |

## Substates

Substates fall in two families: readiness substates describing the
collider/detector readiness progression, and data-flavor substates marking
the kind of information flowing.

Readiness substates:

| Substate | Meaning | Occurs during states |
|---|---|---|
| `not_ready` | Detector not ready for physics datataking | `no_beam`, `beam`, `calib` |
| `ready` | Collider and detector ready for physics, but not declared as good for physics | `beam` |
| `physics` | Collider and detector declared good for physics | `run` |
| `standby` | Collider and detector still good for physics, but standing by, not physics datataking (dead time) | `run` |

Data-flavor substates:

| Substate | Meaning | Occurs during states |
|---|---|---|
| `lumi` | Detector and machine data that is input to luminosity calculations | `beam`, `run` |
| `eic` | Machine data, machine configuration | all |
| `epic` | Detector configuration, data | all |
| `daq` | Information and configuration transmitted from the DAQ | all |
| `calib` | Calibration data types — a catch-all for many, starting small | all (assuming some calibration data can be taken during beam on) |

## Transitions

The defined transitions:

| Transition | Trigger |
|---|---|
| `off` → `no_beam` | Systems brought into operation |
| `no_beam` → `beam` | Collider begins operating |
| `beam`/`ready` → `run`/`physics` | Collider and detector declared good for physics |
| `run`/`physics` ↔ `run`/`standby` | Datataking pause and resume: standby is the paused state, driven by the `pause_run` and `resume_run` run lifecycle messages in the testbed implementation |
| `run` → `beam` | Collider or detector drops out of good for physics |
| `beam` → `no_beam` | Collider stops operating |
| `no_beam` → `off` | Full shutdown |

The occurrence rules in the substate tables constrain which state/substate
pairs are legal. A complete transition table — every legal transition, its
triggering condition, and its side effects on the run boundary — is not
yet specified.

## Relation to the Echelon 0 run-control model

The DAQ group's run-control design (J. Landgraf, July 2026 workfest)
states a convergent model from the E0 side: a state model incorporating
continuously running components (such as scalers), a run structure that
configures and selects the enabled detectors, and slow-controls status as
part of the state model. Detector and readout status specifications will
exist at many levels; at the highest level, which detectors are in the run
combines directly with this model, and bears directly on early workflow
integrations such as calibration.

The remainder of this document proposes the convergence: how these E0
run-control elements enter the state model on the E1 side.

## Proposed evolution

The model above describes what runs in the testbed today. This section
proposes its evolution toward the converged E0-E1 state machine, in light
of the DAQ run-control design and the interface formalization. The
proposal is a basis for discussion with the DAQ and streaming computing
groups.

### The global state

The state generalizes from a single (state, substate) pair to a global
state. The pair carries over unchanged as core state and readiness; the
E0 run-control elements are the additions:

- **Detector participation** — which detectors are in the run, set by
  the run configuration, with per-detector status at the highest level:
  in or out. Finer granularity attaches beneath as specifications
  develop. Calibration workflows key on the participation of their
  detector; a test beam or commissioning configuration is a run with
  reduced participation.
- **Slow-controls status** — the per-detector and machine-side
  good/degraded/bad rollup entering readiness evaluation; channel-level
  data remains in E0-side systems, referenced rather than mirrored.

The DAQ model's continuously running components — scalers, some
calibration flows — exemplify that some systems operate both in and out
of datataking independently of the run lifecycle, carrying state
alongside the run-scoped state.

An early realization route for detector scope is the testbed's
namespace mechanism: namespaces already isolate and organize workflows
and testbed instances, and a hierarchical namespace could carry
(sub)detector scope as a higher-level segment, so that detector-scoped
work — a per-detector calibration workflow, a test beam or commissioning
configuration — runs in a namespace expressing its participation scope,
combining the detector participation component with the isolation
mechanism the testbed already operates.

### The state database and its mirror

State changes are events: each transition is appended to the state
history with its trigger and timestamp, so the database answers both
"what is the state now" and "what was the state when." One event stream
feeds the E1 mirror and stamps the data and messages crossing the
interface. E1 consumers — orchestration, monitoring, calibration
workflows, AI tools through MCP — read the mirror and never reach into
E0. The mirror is the E1 face of a state service with a read API; the
write path belongs to E0.

## References

- State machine definition and implementation status:
  [ePIC streaming workflow testbed, January 2026 collaboration meeting talk](https://docs.google.com/presentation/d/1YhWL6icswO5Dcy2dB5oFdKHXZ22o6Y3mdA9-lj6gtfk/)
  (state machine implementation slide).
- Interface context and open questions:
  [E0-E1 interface notes, January 2026](https://docs.google.com/presentation/d/1hKGmzx91Q9FbFKKyMg_7TerNEVvY-8CxeAq6UINT1pc/)
  and [Echelon 0 - Echelon 1 Interface, Status and Open Questions, July 2026](https://indico.bnl.gov/event/31808/contributions/126678/).
- Echelon 0 run-control model:
  [Introduction & Streaming DAQ: Overview, Requirements and Timeline, July 2026](https://indico.bnl.gov/event/31808/contributions/126677/).
- Implementation: `swf-testbed/workflows/` — `daq_state_machine.toml`
  (the machine's base configuration), `stf_datataking.py` (the
  datataking workflow), `workflow_runner.py` (the common runner);
  `swf-common-lib` `BaseAgent` (the run lifecycle message vocabulary and
  the common agent state management).
