# Architecture and Design Choices

This document records the reasoning behind key architectural and design decisions
for the `swf-testbed` project. Its goal is to provide context for new
contributors and for future architectural reviews.

## Shared Code Strategy: Dedicated Package (`swf-common-lib`)

- **The Choice:** All code intended for use by more than one component will
  reside in a dedicated, versioned, and installable Python package named
  `swf-common-lib`.

- **Rationale:** This approach was chosen to prevent code duplication and
  divergence across the various `swf-` repositories. It establishes a single
  source of truth for common utilities, ensuring that bug fixes and improvements
  are propagated consistently to all dependent components. It also enables clear
  versioning and dependency management, allowing components to depend on specific
  versions of the shared library.

## Process Management: `supervisord`

- **The Choice:** The testbed's agent processes will be managed by `supervisord`.

- **Rationale:** `supervisord` was chosen for its simplicity, reliability, and
  cross-platform compatibility (it works on both Linux and macOS). As a
  Python-based tool, it fits well within the project's ecosystem and can be
  bundled as a dependency of the main `swf-testbed` package. It provides all
  necessary features—such as auto-restarting, log management, and a control
  interface (`supervisorctl`)—with a straightforward configuration file.

- **Alternatives Considered:**
  - **`systemd`:** A powerful alternative on Linux, but it is not cross-platform
      and would prevent the testbed from running easily on macOS.
  - **Docker Compose:** Excellent for managing multi-container services. While
      this is a powerful pattern, the primary distribution goal is to package the
      Python code itself, not necessarily to mandate a container-based runtime
      (see `docs/packaging_and_distribution.md`).
  - **Manual Scripts:** Running agents in separate terminals is feasible for
      development but is not a robust or scalable solution for a deployed
      testbed.

## ActiveMQ Connection and Messaging Patterns

*Notes from Wen Guan (ActiveMQ/Artemis expert), January 2026.*

### Separate vs Shared Connections

- **The Choice:** Agents use separate connections for publishing and subscribing
  rather than sharing a single connection for both.

- **Rationale:** Shared connections add complexity and introduce failure coupling.
  When a publisher sends messages with errors, the broker may send REMOTE_DISCONNECT
  to terminate the connection, which would also kill the subscriber if they share
  the same connection. Since we have no connection count limitations, separate
  connections provide better isolation with minimal overhead.

- **Current Implementation:** `BaseAgent` currently uses a single connection that
  handles both send and receive. This works because stomp.py handles concurrent
  operations, but if issues arise, splitting into separate connections is the
  recommended fix.

### Messaging Semantics: Topic vs Queue vs Durable Subscription

| Pattern | Persistence | Consumers | Use Case |
|---------|-------------|-----------|----------|
| **Topic** | None - messages lost if subscriber offline | Broadcast to all subscribers | Real-time events, heartbeats |
| **Queue** | Messages kept until consumed | One consumer per message | Work distribution, guaranteed delivery |
| **Durable Subscription on Topic** | Creates per-subscriber queue from topic | One subscriber per durable subscription | Persistent broadcast (with caveats) |

### Durable Subscription Warnings

Durable subscriptions create an output queue from an input topic. Important caveats:

1. **Exclusive access:** The output queue can only be used by one subscriber at a time.
   Multiple subscribers will raise an "in use" error.

2. **Must unsubscribe when done:** Unconsumed messages accumulate on disk. A topic
   with high message volume can fill disk space quickly if durable subscriptions
   are not properly cleaned up.

3. **Why some systems disable this:** Managing durable subscriptions requires
   responsible ownership and monitoring. Production systems often disable this
   feature or require explicit approval with designated owners who can be
   contacted when queues grow too large.

### Destination Naming

ActiveMQ Artemis requires explicit destination type prefixes:
- Topics: `/topic/name` (e.g., `/topic/epictopic`)
- Queues: `/queue/name` (e.g., `/queue/stf_processing`)

Never use bare destination names like `epictopic` - always include the prefix.
