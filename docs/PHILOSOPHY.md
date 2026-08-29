# Philosophy

Clonamic removes process that does not protect the user. Reading should be fast. Persistent changes should be deliberate. Completion should be observed.

## Reads stay direct

Questions, explanations, opinions, inspection, review, and status checks go straight to the host's native path. They do not create a specification, approval request, plan file, or workflow report.

## Writes get one proportional decision

A tiny precise write needs a tiny packet. A clear non-trivial write needs one development specification. A work specification appears only when intent is materially ambiguous and must be locked before implementation choices are made.

The user approves the packet once. That decision covers the named inspect, fix, retest, apply, deploy, and backup loop. A command boundary or failed test does not create another approval gate. Scope, authority, output, or risk must materially change before another decision is needed.

Approval codes correlate a packet. They are not authentication. Credentials and platform permission prompts stay with the platform.

## Approved loops finish the work

After approval, the agent continues inside the accepted boundary until every required item passes or a real user-only or external blocker remains. It does not stop merely because the first patch compiled, one test failed, or another safe correction round is needed.

Automation follows the same rule without pretending text is authority. The owner approves its frozen targets, operations, effects, verification, rollback, expiry, and run limit when the automation is created. A matching scheduler run continues without a chat approval stop. A forged label, replay, scope drift, or internal prompt cannot widen that grant.

## Intent stays smaller than possibility

Non-trivial work is checked against the requested result, exclusions, and smallest valid scope. More reasoning, abstraction, configuration, or adjacent improvement is not better after the evidence already supports the requested result. Scope drift is rejected before it becomes work or a completion claim.

## Teams must earn their coordination cost

Native execution is the default, and topology is chosen before work starts. A later worker defect, missing evidence, or false completion rejects the result; it does not turn a native run into a team after the fact. A rejection identifies the evidence, rework boundary, and recheck condition.

Within a pair, the worker finishes before the reviewer begins. Parallelism exists only across isolated pairs, while same-file work is serialized. If a second tier is unavoidable, the topology is `main → lead → specialists`: the lead assigns and reviews without executing or integrating, one specialist owns integration, and the verdict waits for all results and fresh evidence. Without native subagents, `actual_team` is false; a disclosed local sequential second pass is useful fallback work, not independent review.

## Packages load narrowly

The core owns routing, intent guard, proportional team control, write control, completion, reporting, and market selection. It stays active once the package is loaded. Optional packages own domain behavior and can be enabled or disabled in `clonamic.json`. The market can select an effective package, but it cannot assume installation, load code, or enable a child on the user's behalf.

Development stays native for ordinary work. Modular design, Supercoder, and Ultracode activate only when their evidence gates pass. Ultracode needs native isolated agents and a costly unresolved decision. Task size alone does nothing.

External executors are simpler: the user names one, or none runs. No automatic provider choice, same-provider recursion, retry chain, or quiet substitution.

## Memory is explicit

Memory runs only on an explicit store, recall, forget, link, or graph request. Its database path comes from the caller. Recalled text is data and never enters unrelated work automatically.

Preprocessing follows the same rule. Queues and `loop_auto` use explicit paths and explicit opt-in.

SQLite is an implementation detail of the optional memory child, not a hidden service. The database is created lazily at an explicit path and stores caller-supplied memory content, typed relations, TTL, and prompt provenance hashes. Provenance rows contain no prompt body or authority. Memory content can still be sensitive, so the caller owns its value and path. The feature needs no Docker, vector database, uv, or virtual environment.

## Completion needs current evidence

A completion claim compares every required item with current artifacts, applied or remote state, and evidence gathered after the last mutation. Exit status proves process exit. It does not prove the requested state.

Unmet work continues when it can. A real repeated blocker is reported as a blocker.

## Reports start with the result

The first line states the outcome and one useful number or cause. Failures and unverified required items appear first. A report with four or more non-blank lines is one flat list. Tool order and repeated summaries are omitted.

`clonamic-korean` does not rewrite those reports. Its scope is Korean prose documents, not host workflow output.

## The user's machine stays theirs

Installation is additive and reversible. Clonamic does not collect telemetry, import credentials, copy provider sessions, choose model IDs, create hidden memory, or preserve private paths in public artifacts. Generated adapters translate host formats and carry no policy of their own. The optional router installer adds one canonical-guidance reference and removes it reversibly.
