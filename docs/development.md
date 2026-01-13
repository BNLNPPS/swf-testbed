# Development Guide

Development workflow and contribution guidelines for the SWF Testbed.

## Development Workflow

### Multi-Repository Development Strategy

The SWF testbed consists of multiple coordinated repositories that work together
as an integrated system. Development across these repositories requires careful
coordination to maintain system stability and integration.

#### Repository Structure

The testbed is composed of three core repositories that must be kept as siblings:

- **swf-testbed**: Core testbed infrastructure, CLI, and orchestration
- **swf-monitor**: Django web application for monitoring and data management
- **swf-common-lib**: Shared utilities and common code

Additional repositories will be added as the testbed expands with new agents,
services, and functionality.

#### Branching Strategy

We use a **coordinated infrastructure branching strategy** for cross-repository
development work:

##### Infrastructure Development (Recommended)

For infrastructure improvements, testing framework enhancements, and foundational
changes that span multiple repositories:

```bash
# Create synchronized infrastructure branches across all repos
cd swf-testbed && git checkout -b infra/baseline-v1
cd ../swf-monitor && git checkout -b infra/baseline-v1
cd ../swf-common-lib && git checkout -b infra/baseline-v1

# CRITICAL: Push branches to origin immediately to make them available remotely
cd swf-testbed && git push origin infra/baseline-v1
cd ../swf-monitor && git push origin infra/baseline-v1
cd ../swf-common-lib && git push origin infra/baseline-v1

# Work freely across repositories
# Commit frequently with descriptive messages
# Let commit messages document the nature and progression of changes

# When infrastructure phase is complete:
# 1. Test full system integration with ./run_all_tests.sh
# 2. Create coordinated pull requests across all repositories
# 3. Merge to main simultaneously across all repos
# 4. Start next infrastructure iteration (infra/baseline-v2)
```

##### Feature Development

For features that primarily affect a single repository:

```bash
# Create feature branch in the primary repository
git checkout -b feature/your-feature-name

# CRITICAL: Push branch to origin immediately to make it available remotely
git push origin feature/your-feature-name

# Work, commit, and create pull request as normal
# If cross-repo changes are needed, coordinate with infrastructure approach
```

#### Development Guidelines

1. **Never push directly to main** - Always use branches and pull requests
2. **Push branches to origin immediately** - Always run `git push origin branch-name` right after creating a branch to make it available across all development machines
3. **Coordinate cross-repo changes** - Use matching branch names for related work
4. **Test system integration** - Run `./run_all_tests.sh` before merging infrastructure changes
5. **Maintain test coverage** - As you add functionality, extend the tests to ensure `./run_all_tests.sh` reliably evaluates system integrity
6. **Document through commits** - Use descriptive commit messages to explain the progression of work
7. **Maintain sibling structure** - Keep all `swf-*` repositories as siblings in the same parent directory

#### Pull Request Process

1. **Create descriptive pull requests** with clear titles and descriptions
2. **Reference related PRs** in other repositories when applicable
3. **Ensure tests pass** across all affected repositories
4. **Coordinate merge timing** for cross-repo infrastructure changes
5. **Clean up branches** after successful merges

This workflow ensures that the testbed remains stable and integrated while
allowing for rapid infrastructure development and feature additions.

### Example Agent Implementations

For developers looking to create new agents or understand how to interact with
the testbed's messaging and API services, standalone examples are provided in
the `example_agents/` directory. These provide a clear, modern blueprint for
agent development.

## Participants

At present the testbed is a project of the Nuclear and Particle Physics
Software (NPPS) group at BNL; collaborators are welcome.

- Torre Wenaus (lead)
- Maxim Potekhin
- Ejiro Umaka
- Michel Villanueva
- Xin Zhao

## Agent Development Guidelines

### Agent Identity and Naming

When developing new agents, follow the established identity management pattern:

**For agents inheriting from BaseAgent:**
```python
# Agent name automatically assigned via get_next_agent_id()
class MyAgent(BaseAgent):
    def __init__(self, debug=False):
        super().__init__(agent_type='MYTYPE', subscription_queue='/topic/epictopic', debug=debug)
```

**For standalone agents (like DAQ simulator):**
```python
# Implement get_next_agent_id() method following the same pattern as BaseAgent
def get_next_agent_id(self):
    """Get the next agent ID from persistent state API."""
    # Implementation matches BaseAgent.get_next_agent_id()
```

**Command Line Interface:**
All agents should support `--debug` flag for verbose heartbeat logging:
```bash
python my_agent.py --debug  # Enable heartbeat logging
python my_agent.py          # Quiet mode (default)
```

## Glossary

- STF: super time frame. A contiguous set of ~1000 TFs containing about ~0.6s
  of ePIC data, corresponding to ~2GB. The STF is the atomic unit of
  streaming data processing.
- TF: time frame. Atomic unit of ePIC detector readout ~0.6ms in duration.

