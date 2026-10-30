# swf-testbed — machine inventory

BNL SCDF host, **inside the BNL authentication perimeter** (BNL-internal network; not reachable from outside without BNL auth). OS hostname `pandaserver02.sdcc.bnl.gov` (IP 10.42.46.11). Account `wenauseic`. `$HOME` is `/eic/u/wenauseic`.

## Perimeters — SCDF, never "the laboratory"

SCDF is the current name of the BNL facility formerly called SDCC. DNS has not caught up, so `*.sdcc.bnl.gov` hostnames (this host among them) keep the old string and are correct as literal hostnames; prose says SCDF.

Three distinct zones, and the middle one is the one that gets misstated:

- **Inside SCDF** — this host, `pandaserver01`, the dCache doors, the production infrastructure.
- **Inside BNL but outside SCDF** — `npps0`, the GPU worker. A lab host on the lab network, reached through the BNL ssh gateway, but outside the facility enclave, so it cannot reach SCDF-internal services, the dCache doors above all. That is precisely why its stage-out goes to S3, and why it is the working model for volunteer-class workers (`swf-epicprod/docs/NPPS0_WORKER.md`).
- **Outside BNL** — `epic-devcloud.org` (AWS), and volunteer machines later. Here "outside the laboratory perimeter" is accurate and is the right phrase; do not over-correct it to SCDF. The phrase is only ever wrong when applied to a BNL host.

Never write that a BNL host "sits outside the laboratory perimeter." npps0 is obviously inside the laboratory, and the phrase erases the real constraint: the boundary that governs storage reachability is the facility enclave, not the institution. Say "outside the SCDF perimeter" or "outside the SCDF network." Do not soften SCDF to a friendlier word for public or general audiences — that paraphrase is what put the error into the public entry `gpu-optical-sim-access` (corrected 2026-08-15).

## Why everything lives under /data/wenauseic/

The box was provisioned with a tiny root volume, so `/`, `/opt`, and `/home` (and hence `/eic/u/wenauseic`) all share a small pool and fill up fast. Bulk storage is on `/data/`. Practical rule: all day-to-day work — dev trees, venvs, tjai db, logs, anything that grows — lives under `/data/wenauseic/`. `~/github` and `~/work` are symlinks to `/data/wenauseic/github` and `/data/wenauseic/` respectively; prefer the canonical `/data/...` path in scripts. Home-dir disk pressure is a recurring nuisance — when something fills up, it's almost always root, not /data.

## Project scope on this host

`swf-testbed` (the project) has grown beyond just the testbed. It now also encompasses PanDA-based ePIC production software, including PCS (Physics Configuration System, managed through swf-monitor). So "swf-testbed work" here means testbed orchestration **plus** PanDA/ePIC production tooling, not just the streaming-workflow testbed.

## Trees

- Dev: `/data/wenauseic/github` (edit here).
- Prod (swf-monitor only): `/opt/swf-monitor/` — standard `bin/ config/ current/ releases/ shared/` deploy-tool layout. (Lives under `/opt`, so subject to root-volume pressure.)
- Testbed venv: `/data/wenauseic/github/swf-testbed/.venv` — activate before any Python work (`source .venv/bin/activate && source ~/.env`).

## Deployed here (prod)

- **swf-monitor** → `/opt/swf-monitor/current`, served by Apache at URL path `/swf-monitor/` on this host. Django web app, REST API, MCP server, and PCS UI. Deploy: `sudo bash /data/wenauseic/github/swf-monitor/deploy-swf-monitor.sh branch <branch>`. Pulls from git — commit + push before deploying.
- **swf-panda-bot.service** and **swf-testbed-bot.service** — enabled systemd units under `/etc/systemd/system/` (NOT in git). Both run `/opt/swf-monitor/current/.venv/bin/python manage.py {panda_bot,testbed_bot}`.
- **swf-episode-builder.service** — enabled systemd unit under `/etc/systemd/system/` (NOT in git; added 2026-08-02). Runs the episode builder agent from the swf-testbed dev tree venv as wenauseic (`agents/episode_builder_agent.py`), capturing workflow episodes off the bus for all namespaces. The unit sets REQUESTS_CA_BUNDLE/SSL_CERT_FILE explicitly because BaseAgent's ~/.env loader skips shell-computed lines.

- **swf-epicprod-autodeploy.timer** — enabled systemd timer that runs `swf-epicprod-autodeploy.service` as wenauseic every minute. The service runs `/usr/local/libexec/swf-epicprod-autodeploy-poll`, the root-owned installed copy of swf-epicprod `scripts/autodeploy-poll.sh`, which deploys merged swf-epicprod `main`. Units installed from swf-epicprod `scripts/systemd/` (NOT tracked in place). Poller refusals: `journalctl -u swf-epicprod-autodeploy.service`; deploy log: `/opt/swf-monitor/shared/logs/epicprod-autodeploy.log`. The GitHub Actions runner it replaced (`actions.runner.BNLNPPS-swf-epicprod.swf-testbed.service`, `/data/wenauseic/actions-runner`) is disabled and inactive. See swf-epicprod `docs/AUTODEPLOY.md`.

## Dev-cloned here (edit-only, not deployed)

- SWF core: `swf-testbed`, `swf-monitor`, `swf-common-lib`. SWF production: `swf-epicprod` (created 2026-07-10; production domain of the swf platform, direct-to-main while solo, NOT in the coordinated baseline branch set; see its docs/ARCHITECTURE_MAP.md). Agents: `swf-data-agent`, `swf-processing-agent`, `swf-fastmon-agent`, `swf-daqsim-agent`. Also `swf-remote` as a read-only reference (it is deployed on ec2dev, not here).
- PanDA stack (read-only refs): `panda-server`, `panda-client`, `pilot2`, `harvester`, `iDDS`. Also `panda-bigmon-core`, `panda-docs`.
- **Nightly repo refresh (comprehensive)**: `/data/wenauseic/github/nightly-pull.sh` (04:00 cron, logs to `nightly-pull.log`) refreshes **every** git repo under `/data/wenauseic/github` — dynamic enumeration, so new clones are covered automatically. Versioned at `tjrepo/computers/swf-testbed/nightly-pull.sh` since 2026-08-01; the cron path is a symlink to it. Policy: modified `package-lock.json` → discard (npm-install churn, never work); other dirty tree → skip with warning (never stash/clobber); unpushed local commits → leave alone; diverged from a rebased/force-pushed upstream → hard-reset to upstream only when every local commit is patch-equivalent upstream (provably lossless), as happened to `job_submission_condor` 2026-07-12. `--dry-run` to preview.
- ePIC stack (read-only/build refs): `epic`, `epic-prod`, `EICrecon`, `eic-shell`, `afterburner`, `containers`, `eic.github.io`, `simulation_campaign_datasets`, `simulation_campaign_hepmc3`, `tutorial-file-access`, `job_submission_condor`.
- MCP servers cloned for use: `bamboo-mcp`, `github-mcp-server`, `lxr-mcp-server`, `rucio-eic-mcp-server`, `uproot-mcp-server`, `xrootd-mcp-server`, `zenodo-mcp-server`.
- Personal: `tjrepo` (Claude config + hooks symlinked from `tjrepo/computers/common/` into `~/.claude/`).

## tjai local state

- Per `~/.tjai/config.json`: `location_name=swf-testbed`, `db_dir=~/work/tjai` → resolves to `/data/wenauseic/tjai/tjai_swf-testbed.db`.

## Ingress

No dedicated drop-off directory on this host. Handoffs from other machines arrive via git (push on peer, pull here). The ec2dev `/home/admin/receiving/` convention does not apply here. Because the host is inside the BNL auth perimeter, direct scp from the open internet is not a thing — git-through-GitHub is the normal transport.

## Collaboration axes this host cares about

- **swf-testbed ↔ ec2dev**: the primary axis. Design/docs for the ePIC streaming workflow often live on ec2dev; live-system queries, PanDA ops, and testbed + PCS execution (including the swf-monitor web face) live here. swf-remote is deployed on ec2dev, not here.
- **swf-testbed ↔ StudioMax**: rare; most swf-testbed collaboration flows through ec2dev.

## System Ops and usage

- ROOT access: `sudo` to root is available. Use it when needed, carefully and safely.
- **Root-volume squeeze**: `/`, `/opt`, `/home` share a small volume. Keep everything growable on `/data/wenauseic/`. If a process starts failing mysteriously, `df -h /` is a legitimate first check.
- **Inside BNL auth perimeter**: this host is not publicly reachable. Remote-user flows have to reach it via BNL auth; GitHub is the standard file conduit.
- **Passwordless sudo for ops**: this account can use `sudo` for service and journal operations. If a non-sudo command lacks access, rerun the appropriate command with `sudo` rather than claiming the account cannot inspect it.
- Bot systemd units are hand-installed under `/etc/systemd/system/` — if one fails or goes missing, it won't be restored by a git pull. Needs `Restart=always`.
- Git policy: SWF core repos (`swf-testbed`, `swf-monitor`, `swf-common-lib`) are branches + PRs, never direct-to-main. `swf-remote` and `swf-epicprod` are the direct-to-main exceptions; swf-epicprod's outside contributors merge their own PRs, and every push to its main deploys itself. Torre's personal repos follow the tjai commit-all default.
- Deploy pulls from git — a `sudo deploy-swf-monitor.sh` without a prior push deploys stale code.

## Claude Code config

- `~/.claude/settings.json` → `tjrepo/computers/common/claude-settings.json` (symlink).
- `~/.claude/statusline.sh` → `tjrepo/computers/common/claude-statusline.sh` (symlink).
- `~/.claude/hooks` → `tjrepo/computers/common/claude-hooks` (symlink). SessionStart hook `load.py` passes `location_name=swf-testbed` to `get_ai_guidance`, which appends this entry.

## Reaching the PanDA server (pandaserver01)

The ePIC PanDA server and JEDI run on `pandaserver01.sdcc.bnl.gov` (database on `pandadb01.sdcc.bnl.gov`); this host (pandaserver02) does not run them. Direct ssh pandaserver02→pandaserver01 is refused (port 22 closed); the working route is through the SCDF gateway with agent forwarding: `ssh -A -t wenauseic@ssh.sdcc.bnl.gov ssh pandaserver01`. Non-interactive form (as used from Claude Code): outer hop `-o BatchMode=yes -o StrictHostKeyChecking=accept-new`, inner hop `-o BatchMode=yes -o StrictHostKeyChecking=no` (the gateway's older ssh rejects `accept-new`). Live configs are at `/etc/panda/panda_jedi.cfg` and `/etc/panda/panda_server.cfg`; the sandbox cache and the `touch_cache_file` API are served at `https://pandaserver01.sdcc.bnl.gov:25443`. Read-only looks are fine; any change on that host is the PanDA team's to make.
