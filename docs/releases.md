# Preparing an SWF vNN Release

An SWF `vNN` release is a system release, not the diff of one pull request or
one repository. The release record is the `vNN` entry in
[`RELEASE_NOTES.md`](../RELEASE_NOTES.md).

## Release scope

The coordinated baseline repositories are:

- `swf-testbed`
- `swf-monitor`
- `swf-common-lib`

Development for a release uses the same `infra/baseline-vNN` branch name in
all three repositories. A repository may have no changes in a particular
release, and its baseline PR may already have merged while work continues in
another repository.

Peer repositories such as `swf-epicprod`, `swf-remote`, and the standalone
agent and worker repositories normally ride `main`; they are not given
matching baseline branches merely for release bookkeeping. Contributors also
normally develop on their own topic or fork branches and merge by PR to
`main`. Relevant peer-repository and contributor work merged during the cycle
is part of the system release and must be included in the review and release
notes.

A release includes:

- all intended changes since the previous baseline in the three coordinated
  repositories, including changes already merged to `main` during the cycle;
- relevant changes made during the cycle in peer repositories that ride
  `main`;
- operational, deployment, migration, interface, and documentation changes,
  not only user-interface features;
- contributor work merged to `main`, credited by name in an Acknowledgments
  section when appropriate.

A release does not include uncommitted work, work intended for a later cycle,
or unrelated changes that merely happen to be present in a local worktree.
Release notes describe the resulting capabilities and behavior; they are not
a commit-by-commit diary.

## Preparation procedure

1. **Set the boundary.** Identify the previous released baseline and the
   current `infra/baseline-vNN` branches. Use the previous release merge as the
   time boundary for repositories that ride `main`.
2. **Update every checkout.** Fetch or pull the three coordinated repositories
   and every peer repository that changed during the cycle. Inspect dirty
   worktrees first and preserve unrelated local changes.
3. **Inventory the whole cycle.** Compare the current baseline with the
   previous baseline, not only with today's `main`. A `main...HEAD` diff can
   omit baseline work already merged earlier in the cycle. For peer
   repositories, inspect `main` changes since the release boundary.
4. **Reconcile integration state.** Check which vNN PRs have already merged,
   which branches contain follow-up commits, and which repositories have no
   delta. Fold the latest `main` into each active baseline branch before its
   final PR. If a vNN PR merged early and the same branch later gained intended
   vNN work, open a follow-up PR from that branch.
5. **Review outcomes across repositories.** Group the changes by capability or
   operational effect. Confirm cross-repository pieces agree: package
   ownership, dependencies, migrations, deployment, routes, documentation,
   and branch references.
6. **Draft the canonical notes.** Add the newest entry at the top of
   `RELEASE_NOTES.md` in `swf-testbed`. Follow the structure and level of prior
   entries: a release summary, sections organized by capability or repository,
   and acknowledgments. State important compatibility or user-impact facts
   explicitly.
7. **Validate the release diff.** Ensure the notes cover every material change
   and exclude future-cycle work. Run checks appropriate to the code changed;
   documentation-only repositories do not require invented test work.
8. **Publish the coordinated PRs.** Commit only the intended release files,
   push each active `infra/baseline-vNN` branch, and open or update its PR to
   `main`. Cross-link companion PRs and use the release-note summary in their
   descriptions. Do not delete retained baseline branches after merge.
9. **Verify completion.** A repository is merged only when its PR is merged,
   and the release is complete only when all intended repository changes and
   the canonical release notes are on `main`.

After the release, update the three coordinated checkouts from `main` and
create the next matching `infra/baseline-vNN` branches when the next baseline
cycle begins.
