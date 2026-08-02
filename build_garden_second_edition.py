from pathlib import Path
import re, textwrap, json

OUT = Path('/mnt/data')
tex_path = OUT / 'The_Garden_LeafOS_Lifecycle_Architecture_Expanded_Edition.tex'
md_path = OUT / 'The_Garden_LeafOS_Lifecycle_Architecture_Expanded_Edition.md'


def esc(s: str) -> str:
    repl = {
        '\\': r'\textbackslash{}', '&': r'\&', '%': r'\%', '$': r'\$', '#': r'\#',
        '_': r'\_', '{': r'\{', '}': r'\}', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'
    }
    return ''.join(repl.get(c, c) for c in s)


def plate(title, prov, core, interpretation, bridge, rules, acceptance, diagram=None, formula=None, kind='design'):
    return {
        'title': title, 'prov': prov, 'core': core, 'interpretation': interpretation,
        'bridge': bridge, 'rules': rules, 'acceptance': acceptance,
        'diagram': diagram, 'formula': formula, 'kind': kind
    }

parts = []

# Fifth I: Doctrine and authority
p1 = [
plate('Title and Thesis','[G] New synthesis',
      'The Garden is a lifecycle architecture for LeafOS and FlowerOS. It replaces the idea of permanent bloom with bounded cycles of activation, work, validation, shutdown, composting, and renewal.',
      'The inherited LeafOS architecture already separates machine control, work control, model proposals, native validation, durable evidence, and checkpoints. The Garden does not discard those boundaries. It gives them a temporal structure: every active component has a beginning, a useful period, an end condition, and a durable residue.',
      'The design target is renewable local intelligence rather than an indefinitely enlarged resident process. Power, compute, data, cognition, and durable output are treated as distinct biological roles so that each can be measured, governed, and retired independently.',
      ['Preserve FlowerOS as machine authority.','Preserve LeafOS as work authority.','Treat Bloom as one phase, not the whole system.','Require every active phase to define fruit, senescence, and recovery.'],
      'The thesis is accepted when the reader can explain why a smaller cyclic system may outgrow a larger permanent allocation over repeated runs.',
      diagram='ROOTS -> PETALS -> POLLEN -> LEAVES -> BLOOM -> FRUIT\n   ^                                               |\n   +--------------- COMPOST <- SENESCENCE ---------+'),
plate('Abstract','[AA][CB][TP][G]',
      'This document unifies the LeafOS authority model, continual transcript, MWF personalities, evidence pipeline, hardware throughput model, and model-pack system under a new Garden lifecycle doctrine.',
      'Three fifths of the design are inherited from the Architecture Atlas, Continual Bloom Primary Reference, and Inference Throughput White Paper. Two fifths are new: a biological systems model and an implementation contract for finite blooms, compute petals, data pollen, power roots, brain-like leaves, durable fruit, and compostable state.',
      'The new philosophy changes the optimization target. The system no longer asks how much model state can remain resident forever. It asks how much validated work can be produced per cycle, per joule, per unit of memory pressure, and per unit of recoverable state.',
      ['Raw token speed remains a measurement, not the primary objective.','A model proposal never becomes authority by being active longer.','Idle, dormant, and dead states are valid lifecycle states.','Growth is measured across cycles, not by peak allocation alone.'],
      'The abstract succeeds when it states both continuity and replacement: LeafOS contracts survive, Infinite Bloom does not remain the master philosophy.'),
plate('Executive Summary','[G] New synthesis over [AA][CB][TP]',
      'The Garden turns a persistent orchestration stack into an ecology of bounded computational organisms.',
      'Roots represent the electrical and thermal infrastructure that keeps the system alive. Petals are compute surfaces such as CPU, GPU, and NPU workers. Pollen is typed data exchanged between nodes. Leaves are the most complex brain-like transformation systems. Bloom is the period of active coordinated work. Fruit is validated durable output. Compost is compressed retired state that improves later cycles without remaining active memory.',
      'This architecture favors a small required core, optional seasonal lanes, hot/warm/cold/dormant placement, explicit unload rules, and strong state reconstruction. A model can die without the task dying because the authoritative present is reconstructed from contracts, evidence, checkpoints, and transcript tails.',
      ['Use smaller resident allocations by default.','Escalate to larger models only when task value justifies cost.','Unload inactive workers after fruit or timeout.','Convert failures into classified compost rather than silent repetition.'],
      'The executive summary is complete when it produces one governing sentence: infinite growth comes from renewable cycles, not infinite resident size.'),
plate('Five-Fifths Provenance','[AA][CB][TP][G]',
      'The document is deliberately divided into five equal design bands so that inherited architecture and new philosophy remain distinguishable.',
      'Fifth One records machine and authority boundaries. Fifth Two records durable cognition, personalities, state, and evidence. Fifth Three records hardware, throughput, routing, and pack composition. Fifth Four introduces the Garden philosophy. Fifth Five converts that philosophy into runtime contracts, schemas, policies, and work orders.',
      'The ratio is not cosmetic. It prevents the new metaphor from erasing the technical work already present, while preventing the old Continual Bloom framing from absorbing the lifecycle insight and pretending nothing changed.',
      ['Tag source-derived claims with [AA], [CB], or [TP].','Tag new normative material with [G].','Do not silently promote historical measurements into current guarantees.','Do not present metaphor as authority without a corresponding runtime contract.'],
      'Provenance is accepted when every major rule can be traced either to an inherited document or to an explicitly new Garden decision.',
      diagram='FIFTH I   Authority and machine             [source]\nFIFTH II  Durable cognition and evidence    [source]\nFIFTH III Hardware, throughput, packs       [source]\nFIFTH IV  Garden philosophy                 [new]\nFIFTH V   Garden implementation             [new]'),
plate('Canonical Vocabulary','[G] New synthesis',
      'The Garden vocabulary is a typed systems vocabulary, not decorative branding.',
      'Soil is the environmental envelope. Roots are power and survival infrastructure. The stem is the transport and scheduling spine. Petals are compute surfaces. Pollen is typed data in motion. Leaves are high-complexity transformation systems. Bloom is active coordinated execution. Fruit is validated durable output. Seeds are compact restartable intent. Senescence is controlled shutdown. Compost is retired state converted into future context.',
      'Each term must map to measurable state. A component may have a poetic label in the interface, but the journal stores explicit roles, timestamps, budgets, identities, and evidence references.',
      ['Every biological term must have a machine definition.','No glyph, color, or name grants authority.','A lifecycle term must correspond to a state transition.','Unknown mappings remain unknown rather than being improvised.'],
      'Vocabulary is accepted when two engineers can translate a Garden diagram into process, memory, power, and data-flow records without guessing.'),
plate('FlowerOS and LeafOS Split','[AA][CB] Source-derived',
      'FlowerOS controls the machine; LeafOS controls the work.',
      'FlowerOS owns boot, drivers, device access, processes, services, host integration, power visibility, and terminal presentation. LeafOS owns task interpretation, routing, planning, guarded mutation, validation, evidence, checkpoints, recovery, and exactly one legal next action.',
      'Within the Garden, FlowerOS primarily supplies soil and roots: the physical conditions, power state, thermals, process substrate, and device availability. LeafOS primarily coordinates stems, pollen, leaves, bloom, fruit, and compost. This mapping does not merge their authority domains.',
      ['FlowerOS may expose hardware facts but does not decide task truth.','LeafOS may schedule work but does not pretend to own drivers or power electronics.','Cross-boundary requests are typed and journaled.','Failure in one layer must remain visible to the other.'],
      'The split is accepted when a machine restart and a task restart can be reasoned about independently.'),
plate('Two Surfaces, One Engine','[AA] Source-derived',
      'PowerShell and Bash are operator surfaces that delegate into one canonical implementation.',
      'The surfaces provide host-specific convenience, installation, doctor commands, status views, and typed controls. They do not fork the taskpack. The canonical dispatch and resident engine live under ProjectLeaf, preserving one authority path even when the operator experience differs by shell.',
      'In Garden terms, surfaces are views into the organism, not separate organisms. A second shell must not create a second queue, second journal, or competing lifecycle governor.',
      ['Both surfaces call the same canonical command semantics.','Surface-specific helpers may adapt paths, not policy.','A surface closing must not kill durable state.','A surface may observe or request but cannot rewrite evidence.'],
      'The design passes when the same run can be inspected from PowerShell and Bash without divergent state.',
      diagram='PowerShell surface ----\\\n                       > canonical leafctl -> resident engine\nBash surface ----------/'),
plate('Root Contract','[AA] Source-derived',
      'The root contract defines which directories are source, implementation, evidence, cache, import, experiment, or disposable state.',
      'Stable entrypoints and documentation sit above ProjectLeaf. The taskpack owns resident execution. The model installer owns acquisition. Runs, reports, logs, and evidence preserve outcomes but do not replace source authority. Temporary directories, caches, virtual environments, and downloaded binaries are rebuildable.',
      'The Garden adds lifecycle classes to the root contract: dormant seed material, active bloom state, durable fruit, and compost archives. Classification must remain explicit so that a cleanup operation cannot prune source or mistake a cache for fruit.',
      ['Every root path has one authority class.','Generated evidence is immutable or append-only after commitment.','Caches may be deleted without changing truth.','Imported material cannot silently override current contracts.'],
      'The contract is accepted when a cleanup tool can identify disposable material without risking source, evidence, or checkpoints.'),
plate('Operator Surfaces','[AA] Source-derived',
      'Operator surfaces present normalized state and emit typed requests.',
      'The TUI, HTML viewer, and shell commands are projections over the same structured snapshot. They may display tasks, hardware, queue state, provider progress, ledger entries, results, and cursor position. They do not parse one another, schedule hidden work, or execute arbitrary shell text.',
      'Garden presentation may show growth, dormancy, pruning, or bloom, but those visual states must be derived from journaled lifecycle facts. A green petal icon cannot substitute for a device ownership record.',
      ['All views consume one native snapshot.','Controls emit named capabilities with source, nonce, and read head.','Closing a view closes only the view.','Missing telemetry is displayed as unavailable, not estimated.'],
      'Surfaces pass when their rendered states agree with the journal and a stale control request is rejected.'),
plate('ProjectLeaf as Implementation Authority','[AA] Source-derived',
      'ProjectLeaf is the implementation owner for task, queue, validation, reporting, provider, UI, and resident-loop behavior.',
      'This concentration of authority prevents shell helpers, model caches, imported experiments, or presentation code from becoming competing runtimes. ProjectLeaf may expose modular subsystems, but the legal execution path remains bounded and inspectable.',
      'The Garden architecture should therefore be implemented as policy and state inside ProjectLeaf rather than as a decorative sidecar. Lifecycle transitions must pass through the same inlet, journal, validator, and checkpoint machinery as existing tasks.',
      ['Garden states are first-class runtime records.','No separate daemon may mutate Garden state outside the inlet.','New schemas live beside existing taskpack schemas.','Experimental Garden adapters remain non-authoritative until promoted.'],
      'Implementation authority is accepted when Garden lifecycle behavior can be disabled without changing the existing evidence hierarchy.'),
plate('Model Acquisition Boundary','[AA][CB] Source-derived',
      'Model catalog, planning, resolution, application, and verification are distinct operations.',
      'Catalog and doctor operations are local. Planning produces an offline intent. Resolution may contact remote metadata and pin revisions. Apply is the only weight-download boundary. Verification confirms files, hashes, paths, and role links. Credentials must fail fast before workers start.',
      'In the Garden, a model file is dormant seed stock until a pack and lifecycle governor activate it. Downloading a model does not make it a petal, and loading a model does not make it a leaf.',
      ['Downloads require explicit apply.','Resolved revisions and filenames are preserved.','Invalid tokens fail before parallel work begins.','Installed, declared, and loaded are separate states.'],
      'The boundary passes when a plan can be inspected without network transfer and an apply operation can be limited to one selected role.'),
plate('Local Model as Proposal Lane','[AA][CB] Source-derived',
      'A local model proposes bounded structured content; it does not become a control lane.',
      'Instructions are normalized into project facts and task context. A provider returns schema-constrained proposals. The CPU inlet checks paths, commands, approvals, attempts, ownership, and current state. Tracked execution and validation produce evidence. Only accepted checkpoints become durable continuation.',
      'Garden language does not soften this asymmetry. A leaf may be the most brain-like component, but it remains interpretive. It may shape a bloom; it cannot declare its own fruit valid.',
      ['Model output begins unverified.','Provider failure remains visible and never becomes mock output.','Schema validity is necessary but not sufficient.','The model cannot approve itself.'],
      'The proposal lane is accepted when a persuasive but invalid model response is rejected without mutating the project.'),
plate('Native Inlet','[AA][CB] Source-derived',
      'The native inlet is the legal boundary between proposals and actions.',
      'It evaluates capability name, run state, transcript head, nonce, approval policy, path scope, command allowlist, resource budget, and ownership. It appends an accepted, rejected, blocked, or stale disposition before execution.',
      'Within the Garden, the inlet is the gate between pollen and metabolism. Data may arrive from any node, but only typed, current, authorized packets can trigger work.',
      ['Reject unknown capabilities.','Reject stale read heads.','Reject replayed nonces.','Reject paths or commands outside declared scope.','Record every disposition.'],
      'The inlet passes when the same request produces the same legal disposition after restart from committed state.'),
plate('Typed Capability Requests','[AA][CB] Source-derived',
      'Interactive controls and model recommendations become typed capability requests rather than executable text.',
      'A capability record names the action, source, nonce, read head, payload, requested scope, and expected state. The inlet converts it into a disposition. If accepted, a tracked executor receives a bounded work order. If rejected, the reason remains inspectable.',
      'Pollen is therefore typed, not merely textual. The Garden cannot safely route arbitrary prose as if it were metabolic instruction.',
      ['Separate conversation from capability requests.','Require freshness at acceptance time.','Attach source identity and run identity.','Preserve rejection reasons as evidence.'],
      'The capability system passes when optional chat cannot execute a command without a separate typed proposal.',
      diagram='{ capability, source, nonce, read_head, payload }\n                 |\n                 v\n       native disposition -> execute | reject | block | stale'),
plate('Tracked Execution Sandbox','[AA][CB] Source-derived',
      'Execution occurs through tracked, allowlisted operations with captured identity and output.',
      'Each child process record contains executable path, argument vector, process identifier, authorization capability, start and end time, exit code, stdout and stderr references, cancellation state, and resource observations. On Windows, hidden execution must preserve evidence rather than discarding it.',
      'Garden petals are compute surfaces, not uncontrolled subprocesses. Every opened petal must have an owner, budget, purpose, and closure path.',
      ['Launch directly rather than through opaque shell chains when possible.','Capture stdout, stderr, and exit code.','Use job ownership for cleanup.','Do not confuse hidden windows with hidden evidence.'],
      'The sandbox passes when a cancelled process leaves a complete record and no orphaned worker.'),
plate('Validation','[AA][CB] Source-derived',
      'Validation converts checkable outcomes into evidence; it does not convert failure into success.',
      'Validators run declared commands, inspect files, compare hashes, enforce schemas, measure outputs, and preserve artifacts. A validator may support, refute, or leave a claim unresolved. It does not rewrite the claim to fit the desired result.',
      'Fruit requires validation. An untested patch is a flower, not fruit. A benchmark without provenance is pollen, not nourishment.',
      ['Acceptance commands are declared before execution.','Required failures block commitment.','Evidence includes provenance and freshness.','Unknown results remain unknown.'],
      'Validation passes when a failed acceptance command prevents checkpoint promotion and remains visible in the report.'),
plate('Evidence Hierarchy','[AA][CB] Source-derived',
      'Records, evidence, and committed facts occupy different authority levels.',
      'Requests, observations, plans, reflections, and tool attempts are records. Validator results with artifacts are evidence. Checkpoint-bound state is committed fact for resume purposes. A hash chain detects mutation but does not make the contents true.',
      'The Garden uses the same hierarchy across lifecycle phases. Pollen carries records; fruit requires evidence; seeds may summarize facts but must retain references to their validating artifacts.',
      ['Never promote a record directly to committed fact.','Keep evidence references stable.','Treat hashes as integrity checks, not truth certificates.','Rebuild projections from the journal.'],
      'The hierarchy passes when the system can explain why a claim is believed, not merely where it was written.'),
plate('Checkpoint Commit','[AA][CB] Source-derived',
      'A checkpoint is the durable boundary after successful validation.',
      'It records the authoritative resume position, accepted task state, evidence references, unresolved blockers, resource disposition, and exactly one next action. It is created only after required validation succeeds.',
      'In Garden terms, the checkpoint is the fruit seal. It marks what survives after the bloom closes and what may seed the next cycle.',
      ['Checkpoint after validation, never before.','Store one legal next action.','Reference evidence rather than embedding unlimited raw logs.','Record unresolved state explicitly.'],
      'The checkpoint passes when the live process can disappear and the next run resumes from the same accepted state.'),
plate('Resume Boundary','[AA][CB] Source-derived',
      'Recoverability must not depend on a live process, KV cache, terminal, or model remaining alive.',
      'LeafOS reconstructs bounded context from the persona contract, validated facts, checkpoint, transcript tail, and evidence index. Disposable projections and caches may accelerate the process but cannot become required truth stores.',
      'This property is central to the Garden. A petal may close, a leaf may die, and a bloom may end without destroying the organism\'s ability to regrow.',
      ['Test restart after process loss.','Test restart after KV loss.','Test restart after UI disconnect.','Reject resume positions not backed by a checkpoint.'],
      'Resume passes when a cold restart produces the same current facts and next action as the prior committed run.'),
plate('Directory Legend','[AA] Source-derived',
      'Paths are classified by practical role: entry, engine, guarded input, evidence, reference, experiment, or disposable state.',
      'The legend protects against two common errors: treating generated output as source authority and treating caches as irreplaceable. It also prevents imported snapshots from silently overriding current resident contracts.',
      'Garden additions should extend the legend with seed banks, fruit stores, compost archives, and dormant model stock while preserving the same authority discipline.',
      ['Source paths are modified through reviewed changes.','Evidence paths are append-only or immutable after commit.','Caches are rebuildable.','Experiments require explicit promotion.'],
      'The legend passes when every Garden path has a deletion, mutation, and authority policy.'),
plate('TUI Projection','[AA][CB] Source-derived',
      'The terminal UI renders normalized runtime state and typed controls.',
      'It may show lifecycle phase, active pack, queue, hardware, provider, evidence coverage, checkpoint status, and next action. It does not schedule work or parse its own ANSI output back into state.',
      'Garden glyphs and colors may indicate roots, petals, pollen, leaves, fruit, and compost, but the canonical log stores semantic fields rather than presentation artifacts.',
      ['Render from structured snapshots.','Show sample age and missing telemetry.','Keep control names stable.','Make q close only the view.'],
      'The TUI passes when a color or layout change cannot alter execution semantics.'),
plate('Web Projection','[AA][CB] Source-derived',
      'The web interface is a reconnectable projection and typed control surface over the same native state as the TUI.',
      'Polling or WebSocket transport may fail without changing durable truth. Chat remains optional and disabled by default. Buttons emit capabilities rather than shell commands. Browser text never marks validation complete.',
      'The Garden may use the web surface for lifecycle diagrams and node maps, but the map remains a view. A dragged petal icon cannot migrate a model without a legal capability and resource check.',
      ['One snapshot feeds terminal and web.','Authenticate typed controls.','Do not expose unrestricted execute endpoints.','Preserve state across connection loss.'],
      'The web projection passes when it reconnects after restart and reconstructs the same state from the journal.'),
plate('Decision Table','[CB] Source-derived',
      'The Decision Table records how proposals cross the authority boundary.',
      'Recommended fields include sequence, timestamp, source, capability, read head, nonce, proposal digest, evidence references, confidence, risk, disposition, reason, result, and checkpoint. It is an append-only or journal-derived projection, not a separate truth store.',
      'Garden lifecycle transitions should appear in the same table. Activation, pruning, dormancy, composting, and regrowth are decisions with evidence and reasons, not invisible scheduler magic.',
      ['Record accepted and rejected decisions.','Keep model confidence separate from authority.','Attach lifecycle phase before and after.','Rebuild the table from journal truth.'],
      'The table passes when an operator can reconstruct why a petal opened, why it closed, and what fruit survived.'),
plate('Operational Doctrine','[AA][CB] Source-derived',
      'The operational sequence is inspect, propose, approve, execute, validate, and checkpoint.',
      'This deliberate asymmetry is the central safety property. Models can be imaginative, interfaces can be colorful, and workflows can be concurrent, but no unreviewed suggestion becomes executable or durable merely because it appeared in the active bloom.',
      'The Garden extends the sequence with senescence and compost: after fruit is committed, active resources are released and useful residue is compressed for later cycles.',
      ['Inspect before planning.','Approve typed actions, not prose.','Validate before commitment.','Release resources after fruit or failure.','Compost only from traceable records.'],
      'The doctrine passes when every lifecycle transition can be located in this sequence.',
      diagram='INSPECT -> PROPOSE -> APPROVE -> EXECUTE -> VALIDATE -> CHECKPOINT\n                                                        |\n                                                        v\n                                             SENESCE -> COMPOST'),
plate('First-Fifth Synthesis','[AA][CB][G]',
      'The first fifth establishes that the Garden is constrained by existing authority rather than replacing it.',
      'FlowerOS controls machine survival. LeafOS controls work. Surfaces observe and request. Models propose. The native inlet disposes capabilities. Executors perform bounded work. Validators produce evidence. Checkpoints commit facts. The Garden adds lifecycle timing to these roles without moving their authority.',
      'This matters because biological language can tempt designers into vague self-organization. LeafOS must remain self-describing, inspectable, and bounded. Ecology without authority becomes a swarm of unowned processes.',
      ['Authority remains asymmetric.','Lifecycle state is journaled.','Presentation remains weaker than state.','Death and cleanup are controlled operations.'],
      'The first fifth is complete when a Garden diagram can be translated into the existing LeafOS authority path without adding an unreviewed execution route.')
]
parts.append(('Fifth I - Machine, Authority, and Durable Truth', p1))

# Fifth II: Durable cognition and evidence
p2 = [
plate('Ordinary Multi-Agent Failure','[CB] Source-derived',
      'Naive multi-agent chat fails primarily because workers operate on inconsistent state.',
      'Several models may appear collaborative while reading different context windows, missing recent events, repeating old conclusions, and inventing incompatible project versions. More personalities do not solve this; they increase the number of stale views unless the transcript and authority model are explicit.',
      'The Garden treats each cognitive node as a leaf with a cursor and lifecycle. A leaf does not remain valid because it is still loaded. Its output must state which pollen and transcript head it consumed.',
      ['Record exact read heads.','Separate observation, hypothesis, proposal, and fact.','Reject stale outputs.','Do not equate participant count with intelligence.'],
      'The design passes when concurrent leaves can disagree without losing causal order.'),
plate('Transcript as Event Stream','[CB] Source-derived',
      'Conversation and planning are append-only events rather than mutable chat history.',
      'Each event has sequence, timestamp, actor, kind, read head, parent hash, payload, and event hash. NDJSON is a practical initial representation because it is appendable, streamable, recoverable after partial writes, and readable across C++, PowerShell, Bash, Python, and JavaScript.',
      'Pollen enters the Garden as events. Leaves consume events from their cursors. Fruit references the events and evidence that produced it.',
      ['One complete object per line.','Monotonic sequence numbers.','Hash-link events for integrity.','Do not overwrite history to simplify the UI.'],
      'The transcript passes when the tail can be recovered after an interrupted write and replayed deterministically.'),
plate('Event Schema','[CB] Source-derived',
      'An event schema makes provenance and freshness machine-checkable.',
      'The schema should include run identity, sequence, timestamp, actor, kind, read head, parent hash, payload type, evidence references, lifecycle phase, and event hash. The payload is bounded by kind rather than becoming an untyped bag of model narration.',
      'Garden events add node identity, pollen class, source petal or leaf, destination, expiration, and compost eligibility.',
      ['Validate before append.','Reject unknown event kinds unless explicitly experimental.','Limit payload size.','Keep raw hidden reasoning out of durable state.'],
      'The schema passes when a reader can determine who produced an event, from what state, for what purpose, and whether it is still current.'),
plate('Hash Chain and Integrity','[CB] Source-derived',
      'Hash linkage detects mutation and truncation but does not prove semantic truth.',
      'A perfectly hashed hallucination is still a hallucination. Integrity protects ordering and tamper evidence; validators and evidence establish support. The system must never collapse these two properties.',
      'Compost records inherit the same rule. Compression may produce a digest and hash, but the digest must retain links to the source events and evidence it summarizes.',
      ['Hash canonical serialized fields.','Store parent hash and event hash.','Verify chains on replay.','Treat semantic validation separately.'],
      'Integrity passes when a modified historical event is detected and a valid but unsupported claim remains unpromoted.'),
plate('Records, Claims, Evidence, Facts','[AA][CB] Source-derived',
      'The cognition pipeline needs explicit epistemic states.',
      'A request or observation is a record. A model assertion is a claim. A native test, file inventory, metric, or tool result is evidence. A checkpoint-bound accepted state is a committed fact for runtime continuation. Claims may be supported, refuted, or unresolved.',
      'Garden fruit contains committed facts and evidence references. Compost may contain rejected or unresolved claims, but they remain labeled and cannot fertilize future context as if they were true.',
      ['Claims begin unverified.','Only validators promote or refute.','Keep unresolved claims visible.','Preserve origin events.'],
      'The epistemic model passes when a summary cannot erase the difference between a rejected hypothesis and a validated fact.'),
plate('Persona Cursor','[CB] Source-derived',
      'Every personality owns a transcript cursor and contract hash.',
      'Before inference, the runtime advances the persona from its cursor to the current transcript head and constructs bounded context. The resulting output records the head from which it was generated. The cursor is durable; the KV cache is optional.',
      'A Garden leaf therefore has a feeding history. It cannot claim to have consumed pollen that arrived after its recorded read head.',
      ['Persist cursor and contract hash.','Advance before inference.','Record generated-from head.','Rebuild context after cache loss.'],
      'The cursor passes when a restarted persona consumes exactly the unseen events and no others.'),
plate('Anti-Staleness Gate','[CB] Source-derived',
      'A proposal is current only when its generated-from head equals the transcript head at commit time.',
      'If new events arrive before acceptance, the proposal is rejected or rebased. The runtime retrieves unseen events, reconstructs bounded context, and generates again. This prevents Friday from approving a candidate Monday has invalidated and prevents Wednesday from solving a problem the user has changed.',
      'In Garden terms, stale pollen cannot fertilize a current bloom.',
      ['Check freshness at commit, not only at generation start.','Record stale rejection events.','Bound rebase attempts.','Prefer quiescence over endless regeneration.'],
      'The gate passes when deliberately delayed output is rejected after an intervening state change.',
      formula='generated_from_head = current_transcript_head'),
plate('Monday - Rescue and Analysis','[CB][G] Source-derived identity, enriched contract',
      'Monday is gloomy, skeptical, failure-aware, and dependable.',
      'Its operational role is analytical rescue: detect contradictions, missing constraints, invalid assumptions, unsafe actions, stale state, and unsupported claims. Monday prefers deterministic, reversible, recoverable operations. Its tone may be dry, but tone never grants authority.',
      'Within the Garden, Monday is the pruning and pathology leaf. It identifies disease, dead branches, resource leaks, and conditions that should prevent bloom.',
      ['Name blockers before actions.','Prefer the smallest reversible next step.','Audit evidence before checkpoint.','Do not manufacture optimism.'],
      'Monday passes when risky tasks yield explicit constraints, objections, evidence needs, and a safe next action.'),
plate('Wednesday - Explore and Create','[CB][G] Source-derived identity, enriched contract',
      'Wednesday is bubbly, curious, exploratory, and option-rich.',
      'Its operational role is controlled variation: search beyond the first acceptable answer, construct alternatives, propose experiments, preserve informative rejected branches, and expose the risk of each candidate. Novelty is labeled and bounded.',
      'Within the Garden, Wednesday is the pollination and mutation leaf. It expands the design space without confusing every seed with a commitment.',
      ['Generate multiple candidates for open design.','Include one conservative and one strange plausible option.','Label speculation.','Define the smallest informative experiment.'],
      'Wednesday passes when it expands possibility without crossing apply boundaries or burying the practical path.'),
plate('Friday - Research and Delivery','[CB][G] Source-derived identity, enriched contract',
      'Friday is locked in, focused, practical, and decisive.',
      'Its operational role is synthesis and delivery: compare proposals, weigh evidence, select a path, state rejection reasons, define acceptance tests, and produce one legal next action. Friday is not merely the last speaker; it is accountable for closure.',
      'Within the Garden, Friday is the fruiting leaf. It converts a bloom into a deliverable and rejects ornamental work that does not contribute to completion.',
      ['Choose one primary path.','State what is rejected and why.','Require acceptance criteria.','Separate optional future work from the deliverable.'],
      'Friday passes when the user receives a finished artifact or a precise blocker, not an unresolved menu.'),
plate('Personality as Contract','[CB] Source-derived',
      'A personality is a runtime contract, not a costume.',
      'The contract includes model assignment, duties, forbidden actions, transcript cursor, bounded working state, output schema, routing preferences, and visual identity. One set of weights may host several logical personalities if their contracts and cursors remain separate. Different models may implement the same personality across hardware tiers.',
      'Garden leaves are defined by function and contract rather than by model file size. A 1B model may perform a leaf role for narrow classification while a 27B model performs a leaf role for synthesis.',
      ['Identity belongs to the contract.','Keep user-facing style separate from authority.','Persist bounded artifacts, not hidden chain-of-thought.','Record model and placement as runtime facts.'],
      'The contract passes when changing the backing model does not silently change duties or permissions.'),
plate('Persona-Neutral Coder','[CB] Source-derived',
      'Coder workers remain persona-neutral.',
      'They receive bounded briefs, patch scopes, professional output requirements, and validation expectations. They do not imitate Monday gloom, Wednesday sparkle, or Friday intensity in code comments or implementation semantics.',
      'The Garden distinguishes cognitive leaves from task petals. A coder may be a specialized compute petal controlled by a leaf contract rather than a personality-bearing leaf itself.',
      ['Minimal diffs.','Declared file scope.','Tests when required.','No apply without approval.','No personality theater in code.'],
      'Coder neutrality passes when the same implementation brief yields equivalent semantics regardless of the active MWF persona.'),
plate('Collaboration Cadence','[CB] Source-derived',
      'The preferred cadence mixes parallel and serial work.',
      'A user or tool event enters the transcript. Monday and Wednesday may consume the same head concurrently. Their proposals append with shared provenance. Friday consumes both and synthesizes. Native tools execute or validate approved actions. Monday may audit evidence before checkpoint.',
      'This is a pollination cycle: independent leaves produce different pollen, a synthesis leaf combines it, and native metabolism determines whether fruit forms.',
      ['Parallelize independent analysis.','Serialize causally dependent synthesis.','Append before downstream consumption.','Bound every micro-cycle.'],
      'The cadence passes when each personality can see the proposals it is expected to evaluate and no worker loops solely to trigger another.'),
plate('Quiescence','[CB] Source-derived',
      'Idle is healthy; continual generation is not the objective.',
      'If no new evidence, disagreement, constraint, scheduled review, recovery event, or user input exists, the correct event is runtime.quiescent. The supervisor owns heartbeat and leases. Models wake only when work requires attention.',
      'Quiescence is the first explicit form of dormancy in the inherited design and becomes a central Garden state.',
      ['Do not create synthetic work to maintain utilization.','Release model slots when idle policy allows.','Checkpoint before extended dormancy.','Wake on typed conditions.'],
      'Quiescence passes when the system can remain inactive without losing recoverability or pretending to be productive.'),
plate('Prove One Persona Before Three','[CB] Source-derived',
      'The first durable implementation should prove one personality before enabling the triad.',
      'Monday is the recommended first instance because its outputs can be evaluated against explicit constraints and evidence. The instance must survive restart, reject stale output, distinguish claims from facts, and resume from one next action before multi-personality collaboration is trusted.',
      'The Garden generalizes this rule: prove one living unit through its full lifecycle before creating an ecosystem.',
      ['Implement identity, state, events, facts, evidence, checkpoints.','Test restart and cache loss.','Test stale rejection.','Test blocked and failed states.'],
      'The single instance passes when it can complete seed-to-fruit-to-dormancy without relying on another persona.'),
plate('Persona Runtime State Machine','[CB] Source-derived',
      'A persona moves through explicit runtime states.',
      'Starting initializes contract and cursor. Active consumes current work. Waiting expects a known dependency. Idle is healthy quiescence. Blocked requires external resolution. Failed records terminal failure for the attempt. Stopped is an intentional closure. The supervisor, not the model, owns transitions.',
      'These states become a specialized leaf lifecycle inside the larger Garden lifecycle.',
      ['Every state has legal transitions.','Blocked includes a reason and next condition.','Failed preserves evidence.','Stopped releases leases and resources.'],
      'The state machine passes when illegal transitions are rejected and restart reconstructs the same state.',
      diagram='starting -> active -> waiting -> active\n                |          |\n                v          v\n              failed     blocked\n                |          |\n                +-------> stopped\nactive -> idle -> active'),
plate('KV Cache Is Not Authority','[CB][TP] Source-derived',
      'KV cache is a performance optimization, never authoritative state.',
      'Losing a cache may increase prompt reconstruction cost, but it must not erase facts, checkpoints, cursor position, or next action. Bounded context is rebuilt from durable records and validated state.',
      'The Garden treats KV as short-lived tissue. Useful while alive, disposable when senescent, and never confused with the organism\'s durable identity.',
      ['Cache may be hot, warm, cold, or absent.','Checkpoint content must not depend on cache internals.','Record cache policy and measured benefit.','Recover correctly after eviction.'],
      'The cache policy passes when deliberate KV deletion changes latency but not semantics.'),
plate('Claim Lifecycle','[CB] Source-derived',
      'Every model claim begins unverified and moves through explicit dispositions.',
      'A claim record includes identifier, text, origin event, status, evidence references, and scope. Native validators may support, refute, or leave it unresolved. Accepted decisions may depend only on claims whose required support threshold is satisfied.',
      'In the Garden, claims can become fruit nutrients, compost material, or quarantined disease. Their status determines how later leaves may consume them.',
      ['No default supported status.','Attach evidence by reference.','Preserve refuted claims for audit.','Expire context-sensitive claims when inputs change.'],
      'The lifecycle passes when a refuted claim cannot reappear in a future context pack without its status.'),
plate('Evidence Coverage','[CB] Source-derived',
      'Evidence coverage measures supported claims divided by total claims.',
      'The metric does not measure intelligence. It measures whether the runtime is preserving evidence and refusing to collapse proposal into truth. Coverage should be interpreted by claim class; some exploratory hypotheses may remain intentionally unverified while release claims require complete support.',
      'Garden health can use evidence coverage as a fruit-quality measure rather than a bloom-size measure.',
      ['Define which claims require support.','Exclude purely stylistic statements.','Report unresolved counts.','Never optimize by emitting fewer meaningful claims solely to raise the ratio.'],
      'The metric passes when its numerator and denominator can be reconstructed from journal events.',
      formula='E_c = N_supported_claims / N_total_claims'),
plate('Decision Acceptance','[CB] Source-derived',
      'Decision acceptance measures accepted decisions divided by decision attempts.',
      'A high value is not automatically good; it may indicate weak gating. The metric must be read with rejection reasons, failure rates, evidence coverage, and outcome quality. A healthy system rejects stale, unsafe, redundant, and unsupported proposals.',
      'The Garden interprets rejection as pruning. Pruning can improve long-term growth even when it lowers immediate acceptance.',
      ['Report accepted, rejected, blocked, and stale separately.','Classify reasons.','Link accepted decisions to fruit.','Link rejected decisions to compost or quarantine.'],
      'The metric passes when an operator can distinguish productive pruning from arbitrary refusal.',
      formula='A_d = N_accepted_decisions / N_decision_attempts'),
plate('Stale Rejection Metric','[CB] Source-derived',
      'The stale rejection count measures obsolete proposals prevented from crossing the authority boundary.',
      'A nonzero count can be evidence that freshness controls work. A rapidly rising count may indicate excessive latency, over-parallelization, or poor context synchronization. The metric should be paired with time-to-rebase and repeated-stale rate.',
      'In Garden language, this measures pollen that arrived after the receiving bloom had changed state.',
      ['Count stale proposals.','Record age and delay source.','Bound rebase attempts.','Tune concurrency rather than disabling freshness.'],
      'The metric passes when each count maps to a specific rejected event and current head.'),
plate('Two-Sided Personality Record','[CB] Source-derived',
      'Persona output has an operational inside and a deterministic visual outside.',
      'The inside contains identity, role, duties, observations, constraints, hypotheses, candidates, objections, evidence references, confidence, decision, and next action. The outside contains stable visual seed, semantic dimensions, color, glyph, and presentation hints.',
      'The Garden preserves this split. The organism may look different across renderers, but visual identity cannot change lifecycle state or authority.',
      ['Persist semantic dimensions, not terminal escape sequences.','Keep raw hidden reasoning out.','Derive visuals deterministically.','Allow ASCII fallback.'],
      'The record passes when a restart reproduces the same semantic state and equivalent visual identity.'),
plate('Deterministic Visual Identity','[CB] Source-derived',
      'Visual identity is derived from stable fields rather than true randomness.',
      'A seed may combine full persona name, run identity, event sequence, and state digest. Semantic dimensions such as confidence, novelty, urgency, agreement, evidence, and risk can map into a bounded color space and glyph set. The renderer chooses truecolor, 256-color, or ASCII fallback.',
      'Garden visualization can use growth and lifecycle symbols without making appearance part of the database contract.',
      ['Stable input produces stable output.','No visual field grants permission.','Accessibility requires text labels.','Missing color support degrades gracefully.'],
      'Visual identity passes when the same event renders recognizably across terminal and web without semantic divergence.'),
plate('Optional Two-Way Chat','[CB] Source-derived',
      'Operator chat is optional, per-run, and non-executable.',
      'Accepted chat enters the transcript as conversation. If a personality infers that a mutation is desired, it emits a separate typed capability request. The user can inspect, approve, or reject it. Chat survives restart because the transcript, cursors, facts, evidence, and checkpoints are durable; the live connection is merely transport.',
      'Within the Garden, chat is pollen from the operator, not direct control voltage.',
      ['Disabled by default.','Validate size, audience, state, nonce, and head.','Separate conversation and internal collaboration.','Never interpret text box contents as shell.'],
      'Chat passes when a malicious or accidental command-like message cannot execute without an approved capability.'),
plate('Second-Fifth Synthesis','[CB][G]',
      'The second fifth establishes durable cognition without granting models authority.',
      'The transcript provides causal order. Cursors and anti-staleness gates preserve freshness. MWF contracts preserve distinct operational biases. Claims remain unverified until evidence supports them. Quiescence is healthy. KV is disposable. Chat is transport. Exactly one next action survives commitment.',
      'The Garden adds a lifecycle interpretation: leaves consume pollen, blooms synchronize work, pruning rejects unsafe proposals, fruit carries validated state, and dormancy preserves recoverability without active generation.',
      ['Cognition is durable only through state, not continuous process life.','Multiple personalities require one shared truth path.','Metrics measure discipline, not intelligence.','Idle and death are legitimate.'],
      'The second fifth is complete when a model can disappear and the cognitive system remains reconstructable.')
]
parts.append(('Fifth II - Durable Cognition, Personalities, and Evidence', p2))

# Fifth III: hardware/throughput/packs
p3 = [
plate('Historical Baselines','[TP] Source-derived',
      'Historical throughput numbers are observations under incomplete or specific conditions, not hardware constants.',
      'The earliest CPU record preserved three decode samples around 3.9 tokens per second and a rounded 7.37 GB footprint but lacked exact model identity, runtime build, thread count, thermals, memory pressure, and competing-process inventory. Later measurements improved provenance but still describe named artifacts and workloads.',
      'The Garden treats benchmark results as seasonal observations. A past bloom does not guarantee future yield under different models, context, temperature, or soil.',
      ['Retain dates and provenance.','Separate reconstruction from proof.','Do not generalize across models by name alone.','Record uncertainty explicitly.'],
      'Historical use passes when every quoted rate identifies whether it is measured, reconstructed, estimated, or deprecated.'),
plate('Benchmark Provenance','[TP] Source-derived',
      'A benchmark is meaningful only when model, runtime, placement, workload, and host conditions are recorded.',
      'Required fields include artifact and hash, quantization, runtime build and commit, backend, CPU threads, GPU layers, batch and micro-batch, KV types, prompt and output lengths, repetitions, warm-up, power mode, temperature, memory pressure, process inventory, and measurement window.',
      'Garden yield reports add lifecycle phase, petal identity, root condition, pollen volume, fruit count, and compost outcome.',
      ['Record requested, detected, and actual placement.','Repeat a closing cell for drift.','Preserve raw output.','Distinguish cold and warm cache.'],
      'Provenance passes when another run can reproduce the command and explain remaining uncontrolled variables.'),
plate('CPU Executive','[TP][CB] Source-derived',
      'The CPU executive maintains persistent planning, state, validation, and task issuance.',
      'It owns scheduler and event loop, transcript and cursor management, JSON parsing, schema validation, hashing, checkpoint construction, filesystem traversal, process lifecycle, native tests, evidence indexing, and optionally a CPU-resident executive model.',
      'In Garden terms, the CPU is both stem tissue and a set of petals. Control-plane duties carry pollen and enforce lifecycle; CPU inference provides compute when selected.',
      ['Do not reduce CPU value to token rate.','Reserve capacity for validation and responsiveness.','Measure thread placement per model.','Keep control work independent of GPU survival.'],
      'The executive passes when it can keep the queue, journal, and validators moving while the GPU worker is occupied.'),
plate('GPU Worker','[TP][CB] Source-derived',
      'The GPU hosts accelerator-sensitive reasoning, coding, or other high-throughput inference lanes.',
      'Routing must distinguish requested provider, detected provider, actual provider, requested offload, actual offload, GPU layers, VRAM allocation, and fallback reason. Device detection alone is not proof that inference executed on the device.',
      'The GPU is a high-energy petal. It opens for valuable blooms, reports actual placement, and closes when its task or lifecycle budget ends.',
      ['Measure actual offload.','Record VRAM and utilization with process ownership.','Avoid duplicate model launches for shared weights.','Preserve fallback reasons.'],
      'The GPU lane passes when a provider-off or CPU-fallback run cannot claim GPU inference throughput.'),
plate('Prefill and Decode','[TP] Source-derived',
      'Prompt processing and token decoding are different performance regimes.',
      'A cycle estimate includes prompt length divided by prefill rate plus output length divided by decode rate. End-to-end service time must also include provider latency, tools, validation, checkpointing, retries, and queue delay.',
      'Garden scheduling uses these terms to estimate how long petals remain open and when a bloom should senesce rather than assuming token rate equals task completion.',
      ['Measure both prefill and decode.','Record context length.','Do not compare decode-only arithmetic with end-to-end productivity.','Include non-inference stages.'],
      'The model passes when predicted service time is compared with observed complete work-order time.',
      formula='t_order = L_P/r_prefill + L_O/r_decode + t_provider + t_tools + t_validation + t_checkpoint + t_retry'),
plate('Observed Service Capacity','[TP] Source-derived',
      'Work-order capacity is bounded by complete service time, not raw decode rate.',
      'The observed upper bound is 3600 divided by measured order time. Queueing, retries, validation, thermal breaks, and tool latency reduce realized throughput. A long model output may be less useful than a short validated patch.',
      'The Garden therefore measures fruit per cycle and time-to-fruit alongside tokens per second.',
      ['Record arrival rate and completion rate.','Separate active compute from waiting.','Count accepted and rejected fruit attempts.','Report median and tail latency.'],
      'Capacity passes when the system can explain why high token throughput did or did not produce more validated work.',
      formula='lambda_observed <= 3600 / t_order'),
plate('VRAM Bandwidth Model','[TP] Source-derived',
      'Dense decode is often constrained by effective memory bandwidth and model traffic.',
      'A simplified rate divides achieved bandwidth by weight traffic plus KV and overhead traffic. The paper used a 7.37 GB example and a 504 GB/s nominal RTX 4070 bandwidth to show that aggressive targets near 66 tokens per second would require implausibly high efficiency before overhead.',
      'Garden design uses this as a warning against assuming a larger resident bloom will scale linearly. Weight size, cache traffic, kernels, context, and synchronization all consume the same roots and petals.',
      ['Treat theoretical ceilings as ceilings.','Measure achieved bandwidth indirectly with observed rate.','Include KV and overhead.','Do not extrapolate one artifact to another.'],
      'The model passes when estimated ceilings are clearly separated from measured results.',
      formula='r_GPU ~= eta * B_VRAM / (M_weights + D_KV + D_overhead)'),
plate('Partial-Offload Penalty','[TP] Source-derived',
      'A small serial CPU remainder can sharply reduce combined throughput.',
      'The harmonic-style placement model shows that 90, 95, and 99 percent GPU-resident work may still fall far below the full-GPU rate when the CPU portion is much slower. Full offload is therefore a qualitative requirement for some dense workers, not merely a small optimization.',
      'Garden petals must report actual division of labor. A bloom that appears GPU-active may still be root-bound by a serial CPU segment.',
      ['Measure zero, partial, and full offload with the same workload.','Record layer count and fallback.','Investigate low results before blaming hardware.','Keep control-plane CPU work separate from serial model work.'],
      'Placement passes when offload percentage and combined rate are both reported.',
      formula='r_combined = (f/r_G + (1-f)/r_C)^(-1)'),
plate('Full-Offload Requirement','[TP] Source-derived',
      'A model that fits nominally in VRAM must still leave room for KV cache, compute buffers, and runtime state.',
      'The 7.37 GB example leaves roughly 4.63 GB in a 12 GB budget before context and runtime overhead. Fit must be measured under the target context and batch settings. A model that loads but immediately pressures buffers is not a healthy resident petal.',
      'The Garden favors smaller petals partly because they leave room for the rest of the organism.',
      ['Budget weights, KV, buffers, fragmentation, and display use.','Require headroom.','Test target context.','Fail closed on repeated out-of-memory events.'],
      'Full offload passes when the target workload completes without memory pressure forcing silent fallback.'),
plate('Persistence and Useful Throughput','[TP] Source-derived',
      'Persistent state improves useful throughput by reducing repeated context processing, lost work, and reconstruction.',
      'The paper illustrates a worker at the same raw decode rate producing substantially more useful output when waste falls from thirty percent to five percent. Persistence does not make the GPU faster; it makes more of its work survive.',
      'This is the direct bridge to the Garden. Compost and seeds should reduce repeated growth while allowing active tissue to die.',
      ['Measure redo and repetition.','Separate raw and useful rates.','Checkpoint compact state.','Retain only context that changes future work.'],
      'Persistence passes when restart and compaction reduce repeated work without changing factual state.',
      formula='r_useful = r_raw * (1 - d)'),
plate('CPU/GPU Pipeline Overlap','[TP][CB] Source-derived',
      'Useful utilization comes from overlapping independent work, not synthetic load.',
      'While the GPU performs inference or coding, the CPU can validate the prior result, traverse files, compile, parse, build the next context, update journals, and prepare a bounded work order. Continuous batching may allow logical personalities to share one model pool instead of racing duplicate launches.',
      'The Garden sees this as several petals opening around one stem, exchanging pollen at controlled boundaries.',
      ['Double-buffer preparation and validation.','Use admission control.','Avoid duplicate weight residency.','Preserve foreground responsiveness.'],
      'Overlap passes when higher utilization corresponds to more validated work rather than busy loops.'),
plate('RAM as Warm Tier','[CB][TP] Source-derived',
      'RAM holds live transcript projections, indexes, bounded context packs, warm model state, and optional caches.',
      'It is a shared warm tier between durable NVMe and scarce VRAM. Authoritative content remains reconstructable from durable records. RAM pressure must be measured because an oversized warm tier can damage the workstation even when VRAM appears healthy.',
      'In the Garden, RAM is nutrient-rich circulating tissue, not permanent identity.',
      ['Classify each allocation by rebuildability.','Bound context packs.','Track pressure and paging.','Evict caches before facts.'],
      'RAM policy passes when the system can reclaim warm state without losing checkpoints or evidence.'),
plate('NVMe as Durable Tier','[CB][TP] Source-derived',
      'NVMe stores journals, checkpoints, evidence, cold summaries, model files, and historical artifacts.',
      'The normal data direction is NVMe to RAM to VRAM. Memory mapping may allow the operating system to satisfy pages from storage, but LeafOS does not claim expert pinning or managed SSD/RAM/VRAM tiering unless implemented and measured.',
      'The Garden treats NVMe as soil and seed storage: durable, slower, and capable of regrowth after active tissue disappears.',
      ['Separate storage contract from speculative tier management.','Record cold and warm behavior.','Preserve hashes and revisions.','Measure page faults for mapped models.'],
      'The durable tier passes when a cold boot can reconstruct the run without hidden RAM-only assumptions.'),
plate('Useful Utilization Governor','[AA][CB] Source-derived',
      'The governor targets productive occupancy during approved active work, not decorative load.',
      'Inputs include queue, hardware, foreground activity, provider health, budget, thermals, and telemetry freshness. Decisions include claim, defer, pace, recover, pressure, or quiesce. CPU and GPU bands are useful-work targets, not quotas.',
      'The Garden governor decides which petals open, how long they remain active, and when roots require rest.',
      ['Never create meaningless work to raise utilization.','Protect foreground responsiveness.','Record reason codes.','Use backpressure under memory or thermal pressure.'],
      'The governor passes when an idle queue produces quiescence rather than artificial load.'),
plate('Thermal Breaks','[CB] Source-derived',
      'Thermal state is part of execution truth.',
      'The inherited design alternates active compute and thermal break, with conservative pause and resume thresholds. Missing required telemetry triggers quiescence and checkpoint rather than optimistic continuation. Exact thresholds remain host policy, not universal constants.',
      'Thermal breaks are literal seasons inside the Garden. Roots may require cooldown even when the queue is nonempty.',
      ['Record temperature source and sample age.','Pause before damage or severe throttling.','Resume only after hysteresis.','Checkpoint before extended break.'],
      'Thermal policy passes when overheating causes a controlled state transition rather than an unexplained performance collapse.'),
plate('Telemetry Truth Contract','[AA][CB][TP] Source-derived',
      'Requested, detected, and actual execution must be reported separately.',
      'Missing configuration stays visible. Unknown identities remain unknown. Provider-off runs cannot claim model throughput. GPU activity is not assigned to LeafOS without process ownership. Expected missing telemetry is unavailable, not pass.',
      'Garden health dashboards must follow the same rule: a pretty flowering animation cannot imply active fruit production.',
      ['Include sample source and age.','Attach process ownership.','Keep model and fixture throughput separate.','Make unavailable states explicit.'],
      'Telemetry passes when terminal, web, journal, and report agree on what was actually observed.'),
plate('Medium-MoE Qualification','[TP] Source-derived',
      'Medium mixture-of-experts candidates require measured qualification rather than enthusiasm about parameter count.',
      'Each candidate records total and active parameters, expert topology, quantized artifact, pinned revision, hash, context, explicit runtime command, and pre-run thresholds. One report cannot promote a model automatically.',
      'The Garden treats a large MoE as a seasonal canopy experiment, not the default organism. It may bloom only after proving host fit, survival, and useful yield.',
      ['Qualify cold, warm, and resident runs.','Record restart, OOM, responsiveness, and pressure.','Require operator review.','Do not claim managed expert tiering if absent.'],
      'Qualification passes when all required reports exist and promotion remains a separate decision.'),
plate('Qualification Portfolio','[TP] Source-derived',
      'A candidate is evaluated across short cold-cache, medium warm-cache, and longer resident-foreground runs.',
      'The portfolio records provider survival, restart count, out-of-memory events, RAM and VRAM pressure, foreground responsiveness, token rates, validated useful changes per hour, and drift. The long run tests coexistence with the workstation rather than isolated peak speed.',
      'Garden selection therefore evaluates seasons, not a single sunny afternoon.',
      ['Use fixed workloads.','Repeat final cells for drift.','Preserve failed reports.','Compare useful output, not only tokens.'],
      'The portfolio passes when a candidate can be rejected for instability despite an impressive peak rate.'),
plate('Plan, Resolve, Apply, Verify','[AA] Source-derived',
      'Model acquisition is a guarded four-stage workflow.',
      'Plan is offline and declarative. Resolve contacts metadata and pins exact identities. Apply performs the download boundary. Verify checks size, hash, path, and role mapping. The stages should be visible independently in CLI and reports.',
      'Garden seed stock follows the same lifecycle: cataloged, resolved, acquired, verified, dormant, activated, and eventually pruned or archived.',
      ['No silent apply.','Permit role-limited acquisition.','Fail fast on invalid credentials.','Retain revision pins.'],
      'The workflow passes when selected models can be materialized without downloading every declared optional artifact.'),
plate('Pack as Composition Unit','[CB][G] Source-derived and enriched',
      'The model pack is the unit of composition between artifacts, roles, routing, installation, and runtime policy.',
      'A pack declares model references, role groups, required and optional artifacts, fallback chains, context limits, hardware budgets, and load states. Declared, installed, and loaded remain separate. A profile selects a practical subset without erasing the catalog.',
      'The Garden adds lifecycle triggers, senescence conditions, compost policy, and fruit targets to the pack.',
      ['One pack identity, multiple runtime profiles.','Role permissions remain explicit.','Optional lanes do not become default downloads.','Runtime state reports which profile is active.'],
      'Pack composition passes when the same pack can run in a small profile and a larger seasonal profile without changing authority.'),
plate('Older 2+2 Architecture','[G] Based on prior Pack 12 design',
      'The 2+2 architecture is the best initial Garden pack because it proves specialization without permanent excess.',
      'The primary pair is Brain and Coder. The support pair is Judge and Auxiliary. Auxiliary cleans and compresses input. Brain plans and routes. Coder builds bounded patches and tools. Judge accepts, rejects, or requests retry. Native validators remain outside model authority.',
      'This design maps cleanly to a small organism with four functional nodes and explicit lifecycle states.',
      ['Load auxiliary hot or warm.','Load brain on demand or warm.','Load coder only for code tasks.','Load judge before commitment.'],
      'The 2+2 pack passes when each role can be independently activated, replaced, unloaded, and recovered.'),
plate('Hybrid 4+4 Profile','[G] Based on prior Pack 1.2 selection',
      'The hybrid 4+4 profile is a richer seasonal bloom, not the default resident core.',
      'Four Qwen reasoning variants provide peak brain, default brain, context feeder, and fast draft. Four MiniCPM writing variants provide style polish, writer-judge, default writer, and fast extraction. Visual and experimental lanes remain optional toggles.',
      'The Garden reframes this profile as a temporary canopy: useful for high-value work, expensive to keep fully active, and expected to contract after fruit.',
      ['Catalog all eight, load only needed roles.','Keep peak brain cold by default.','Use small writers for preprocessing and polish.','Record promotion evidence for experimental lanes.'],
      'The profile passes when it can materialize eight artifacts while loading only a bounded subset for a given task.'),
plate('Hot, Warm, Cold, Dormant','[G] Enriched from prior load-state design',
      'Model placement is a lifecycle state rather than a binary installed/not-installed flag.',
      'Hot models are resident and immediately available. Warm models retain partial state or fast-load readiness. Cold models are installed but inactive. Dormant models are cataloged or archived and require explicit activation. State transitions are governed by task value, memory pressure, latency target, and lifecycle policy.',
      'Dormancy is the missing category in many local stacks. It permits a large garden without pretending every plant must be photosynthesizing at once.',
      ['Report current state per artifact.','Define transition cost.','Unload after idle or fruit.','Never infer residency from installation alone.'],
      'Load-state policy passes when memory can be reclaimed without losing pack identity or future activation capability.'),
plate('Useful Output Metrics','[TP][G]',
      'The primary outcome is validated useful change, not token volume.',
      'Metrics may include validated patches per hour, accepted artifacts per cycle, evidence coverage, time-to-fruit, redo fraction, energy per accepted artifact, stale rejection rate, recovery time, and workstation responsiveness. Tokens per second remain diagnostic.',
      'Garden metrics reward renewal: a small petal that produces reliable fruit and closes may outperform a huge bloom that consumes roots and repeats itself.',
      ['Pair throughput with acceptance.','Pair utilization with completed work.','Report energy and memory pressure.','Count recovery and pruning outcomes.'],
      'Metrics pass when a lower-token configuration can win for higher validated yield.'),
plate('Third-Fifth Synthesis','[TP][AA][CB][G]',
      'The third fifth establishes the physical and compositional limits within which the Garden must live.',
      'CPU and GPU have different responsibilities. RAM and NVMe are different tiers. Full offload, context, bandwidth, thermals, and process ownership matter. Persistent state increases useful throughput. Packs separate catalog, profile, installation, and runtime. Smaller 2+2 operation is a stronger default than a permanent 4+4 bloom.',
      'The Garden does not reject large models. It rejects the assumption that maximum resident allocation is identical to maximum long-term growth.',
      ['Measure exact artifacts and placements.','Use lifecycle states for load.','Promote by evidence.','Optimize validated yield per resource.'],
      'The third fifth is complete when hardware policy explains not only how to start a model, but why and when to stop it.')
]
parts.append(('Fifth III - Hardware, Throughput, Model Packs, and Useful Work', p3))

# Fifth IV: Garden philosophy
p4 = [
plate('Why Infinite Bloom Fails','[G] New philosophy',
      'Permanent bloom is biologically unnatural and computationally inefficient.',
      'A system that treats continuous activity as health tends to accumulate resident models, stale contexts, duplicate workers, thermal pressure, and unbounded logs. It becomes difficult to distinguish useful persistence from refusal to die. Infinite Bloom confuses liveness with value.',
      'The Garden preserves continual synchronization while rejecting continual generation and continual allocation. Bloom becomes a bounded phase with entry criteria, fruit targets, and exit conditions.',
      ['No bloom without a declared fruit target.','No active worker without a budget and owner.','No permanent context merely because it once mattered.','No failure hidden as continued activity.'],
      'The philosophy passes when stopping can be a successful outcome rather than evidence of system death.'),
plate('Natural Growth and Death Cycles','[G] New philosophy',
      'Nature achieves continuity through replacement, succession, dormancy, reproduction, and recycling rather than by keeping every organism alive forever.',
      'Plants germinate, grow, flower, fruit, senesce, and return material to soil. Animals develop, specialize, reproduce, and die. Ecological continuity persists above the lifespan of any individual. The computational analogy is not that software is alive, but that durable systems can separate identity from resident process life.',
      'LeafOS can therefore pursue indefinite improvement through repeated bounded cycles whose artifacts and lessons survive their workers.',
      ['Separate organism identity from process lifetime.','Carry durable lessons forward.','Permit old strategies to die.','Preserve diversity for changing conditions.'],
      'The principle passes when a dead worker is ordinary and a lost checkpoint is extraordinary.'),
plate('Formal Definition of the Garden','[G] New philosophy',
      'The Garden is a bio-inspired lifecycle architecture for distributed local intelligence.',
      'It separates environment, power, transport, compute, data movement, cognition, active coordination, durable output, and retired state into named roles. These roles are linked by explicit state transitions and authority boundaries rather than left as metaphor.',
      'The Garden is larger than one pack or one machine. It may describe a workstation, a cluster of local nodes, a family of model packs, or a long-running project whose individual blooms are short-lived.',
      ['Every role must be measurable.','Every transition must be journaled.','Every active phase must have an exit.','Every durable claim must retain evidence.'],
      'The definition passes when the same concepts can describe both one-PC LeafOS and a future multi-node installation.'),
plate('Soil','[G] New philosophy',
      'Soil is the environmental and resource envelope from which the system grows.',
      'It includes chassis, cooling, operating system, filesystem, local model store, network access, storage capacity, security context, operator constraints, and the history available for regrowth. Soil is not active computation; it determines what forms of computation can remain healthy.',
      'Soil quality changes over time. Fragmented storage, stale dependencies, weak cooling, or unbounded archives can make later blooms less productive even when compute hardware is unchanged.',
      ['Audit soil before activation.','Track free storage and cache growth.','Preserve source and evidence classes.','Treat dependency drift as a soil change.'],
      'Soil passes when the lifecycle governor can explain which environmental constraint blocked or shaped a bloom.'),
plate('Roots','[G] New philosophy',
      'Roots are power and survival infrastructure.',
      'They include wall power, PSU rails, battery or UPS state, grounding, thermal transport, fan and pump capability, power limits, and the telemetry needed to know whether the organism can continue. Roots supply every petal and leaf but do not decide task truth.',
      'Root health is a first-class runtime condition. A scheduler that ignores power and heat is not intelligent; it is merely optimistic until throttling or failure performs involuntary pruning.',
      ['Measure power and temperature when available.','Use hysteresis for pause and resume.','Distinguish missing telemetry from healthy telemetry.','Checkpoint before root-induced dormancy.'],
      'Roots pass when power or thermal degradation produces a controlled lifecycle response.'),
plate('Stem','[G] New philosophy',
      'The stem is the transport, scheduling, and structural spine.',
      'It carries typed pollen between nodes, distributes root resources, maintains queue order, enforces leases, and connects active petals and leaves to durable stores. In implementation, the stem corresponds to the resident event loop, queue, router, inlet, journal, and process supervisor.',
      'The stem is deliberately less brain-like than the leaf. It should be reliable, boring, and inspectable. Complex interpretation belongs in leaves; legal sequencing belongs in the stem.',
      ['Keep transport deterministic.','Use backpressure.','Do not embed hidden model policy in the queue.','Preserve node identity and ownership.'],
      'The stem passes when data and control can be traced end-to-end without reading model prose.'),
plate('Petals','[G] New philosophy',
      'Petals are compute surfaces that open for work and close when their contribution ends.',
      'A petal may be a CPU worker, GPU slot, NPU accelerator, model instance, compiler pool, validator process, or other bounded executor. Petals expose capacity and specialize by workload. They do not own durable truth or authority merely because they consume the most power.',
      'The petal metaphor emphasizes multiplicity and transience. Many small petals may cooperate around one bloom; an expensive petal may remain closed until a high-value task justifies it.',
      ['Declare role, owner, budget, and closure condition.','Record actual device placement.','Avoid duplicate resident weights.','Close idle petals.'],
      'Petals pass when the system can enumerate active compute surfaces and explain the work each is doing.'),
plate('Pollen','[G] New philosophy',
      'Pollen is typed data moving between nodes.',
      'It includes task packets, prompts, context fragments, embeddings, model proposals, validator results, evidence references, routing messages, state deltas, and summaries. Pollen has origin, destination, type, freshness, scope, and expiration. It may be fertile, sterile, stale, rejected, or quarantined.',
      'This framing shifts attention from static context size to the quality and timing of transfers. More pollen is not necessarily better; duplicate or stale pollen can exhaust leaves without producing fruit.',
      ['Type every packet.','Record provenance and read head.','Bound size and lifetime.','Deduplicate repeated context.'],
      'Pollen passes when every consumed packet can be traced to an origin and lifecycle disposition.'),
plate('Leaves','[G] New philosophy',
      'Leaves are the most complex brain-like transformation systems in the Garden.',
      'They integrate signals, context, evidence, memory, constraints, and goals into plans, hypotheses, decisions, or synthesized outputs. A leaf may be a persona-bearing executive model, a multimodal reasoner, a router with learned interpretation, or another high-context component.',
      'A leaf is not authority. Its complexity makes it valuable and fallible. Native tools still prove, the inlet still disposes capabilities, and checkpoints still define durable continuation.',
      ['Bind each leaf to a contract and cursor.','Record consumed pollen.','Bound output schemas.','Keep cognition separable from execution.'],
      'Leaves pass when replacing one model changes capability and latency without changing legal authority.'),
plate('Bloom','[G] New philosophy',
      'Bloom is the active coordinated runtime phase.',
      'During bloom, selected petals and leaves are open, pollen moves, the stem schedules work, roots supply power, and the system pursues a declared fruit target. Bloom has an activation time, budget, active profile, acceptance gates, and exit conditions.',
      'Continual Bloom becomes a specific operating mode in which synchronization persists across repeated micro-cycles. It is no longer the definition of the whole system.',
      ['Declare a fruit target.','Declare maximum duration or budget.','Report active nodes and health.','Exit on success, failure, block, or root pressure.'],
      'Bloom passes when its start and end can be reconstructed and its resource cost can be attributed.'),
plate('Fruit','[G] New philosophy',
      'Fruit is durable, validated, reusable output.',
      'Examples include accepted patches, tested tools, reports, benchmark portfolios, pack manifests, decisions, models of a project, and checkpointed next actions. Fruit is not merely whatever a model emitted. It is the portion of a bloom that survives validation and remains useful after active compute closes.',
      'Fruit should be indexed for future seeds and linked to the evidence that justified it.',
      ['Require validation appropriate to artifact type.','Store provenance and digest.','Separate accepted fruit from candidate output.','Define retention policy.'],
      'Fruit passes when a future run can reuse it without reconstructing the entire bloom.'),
plate('Seeds','[G] New philosophy',
      'Seeds are compact, restartable packages of intent and proven context.',
      'A seed may contain project identity, objective, constraints, selected fruit references, active hypotheses, known blockers, preferred pack, and one next action. It is smaller than the full historical transcript and richer than a prompt.',
      'Seeds allow the Garden to grow again after all active petals and leaves have closed. They are the durable interface between cycles.',
      ['Include only current, traceable state.','Reference fruit and evidence.','Exclude stale rejected branches unless explicitly relevant.','Keep one next action.'],
      'Seeds pass when a new bloom can start from them without reading every prior token.'),
plate('Senescence','[G] New philosophy',
      'Senescence is controlled reduction of active capability after fruit, exhaustion, block, or environmental pressure.',
      'The system stops admitting new work, drains accepted tasks, checkpoints current facts, releases leases, flushes evidence, summarizes residue, and unloads selected models. Senescence is not abrupt failure; it is an orderly end phase.',
      'Many current systems omit this phase and therefore leak memory, workers, and state until the operator performs manual death.',
      ['Stop admission before shutdown.','Drain bounded accepted work.','Checkpoint before unload.','Record what remains unresolved.'],
      'Senescence passes when the bloom ends without orphaned processes or ambiguous resume state.'),
plate('Death','[G] New philosophy',
      'Death is the termination of a specific process, node instance, strategy, pack profile, or workflow lineage.',
      'Death may be successful, planned, failed, or quarantined. It does not imply loss of Garden identity because contracts, fruit, seeds, evidence, and compost survive independently. Some dead branches should never regrow without new evidence.',
      'Treating death explicitly prevents hidden zombie workers and endless retries masquerading as persistence.',
      ['Record cause and final state.','Release all owned resources.','Preserve failure evidence.','Define whether regrowth is allowed.'],
      'Death passes when process absence is expected and recoverability remains measurable.'),
plate('Compost','[G] New philosophy',
      'Compost is retired state converted into bounded future value.',
      'Inputs include failed attempts, rejected candidates, stale outputs, old logs, historical context, deactivated profiles, and superseded artifacts. Composting summarizes, classifies, deduplicates, preserves evidence references, and separates reusable lessons from archive-only bulk.',
      'Compost is not a euphemism for dumping everything into a vector database. It has provenance, retention, and contamination controls.',
      ['Never promote failure to fact.','Retain source links.','Deduplicate repeated material.','Quarantine unsafe or contradictory residue.'],
      'Compost passes when future context becomes smaller and more useful without losing the ability to audit important conclusions.'),
plate('Pruning','[G] New philosophy',
      'Pruning removes branches that consume resources without improving future fruit.',
      'Targets may include duplicate model variants, stale context, dead routes, abandoned experiments, redundant summaries, unused caches, and policies disproven by evidence. Pruning is a decision with scope, evidence, reversibility, and retention class.',
      'Pruning is not deletion by mood. It is evidence-based simplification.',
      ['Preview before destructive pruning.','Protect source, evidence, and committed fruit.','Archive when uncertainty is high.','Measure reclaimed resources.'],
      'Pruning passes when the system becomes simpler without losing current truth or recovery ability.'),
plate('Dormancy','[G] New philosophy',
      'Dormancy preserves identity and readiness without active compute.',
      'A dormant model, persona, pack, or project retains catalog identity, contracts, seeds, and activation conditions while releasing VRAM, RAM, processes, and leases. Dormancy can be scheduled, resource-triggered, or operator-selected.',
      'This is the practical answer to large local model collections: own many possibilities, activate few.',
      ['Persist activation prerequisites.','Record last fruit and last failure.','Keep no hidden heartbeat requirement.','Test cold regrowth.'],
      'Dormancy passes when a component can remain inactive for an arbitrary period and return from durable state.'),
plate('Seasons','[G] New philosophy',
      'Seasons are policy periods that change which blooms are desirable.',
      'A season may correspond to time of day, foreground activity, electricity price, thermal conditions, project phase, operator presence, or hardware availability. Quiet seasons favor small CPU leaves and maintenance. Work seasons favor default brain and coder. Deep seasons permit expensive peak models. Recovery seasons prioritize audit and compost.',
      'Seasonality replaces the assumption that one configuration should be optimal at all times.',
      ['Define season triggers.','Allow manual override.','Keep authority constant across seasons.','Record transition reasons.'],
      'Season scheduling passes when the same task may select a different healthy profile under different environmental conditions.'),
plate('Diversity','[G] New philosophy',
      'A healthy Garden preserves functional diversity without keeping every variant active.',
      'Different models, quantizations, tools, validators, personas, and hardware lanes provide resilience to task variation and failure. Diversity is catalog and capability breadth; residency is a separate budget decision.',
      'Monoculture can be efficient until its assumptions fail. Unbounded diversity becomes storage and routing chaos. The design needs measured niches and retirement rules.',
      ['Record each component niche.','Benchmark overlapping candidates.','Retire dominated variants.','Keep at least one recovery path.'],
      'Diversity passes when alternatives exist for meaningful failure classes and routing can explain their selection.'),
plate('Mutualism','[G] New philosophy',
      'Nodes should exchange work when the exchange improves joint yield.',
      'Examples include a small auxiliary compressing context for a larger leaf, a CPU validator checking GPU output, a writer polishing a reasoner draft, or one node sharing verified fruit with another. Mutualism is measured by reduced latency, waste, or error rather than by the number of messages exchanged.',
      'Pollen exchange without benefit is chatter, not ecology.',
      ['Measure before and after exchange.','Prevent circular triggering.','Preserve source identity.','Use bounded contracts.'],
      'Mutualism passes when cooperation improves validated yield or resource efficiency.'),
plate('Disease Containment','[G] New philosophy',
      'Hallucinations, corrupted state, runaway loops, invalid artifacts, and compromised tools are forms of systemic disease.',
      'Containment uses schema validation, quarantine, capability boundaries, evidence requirements, stale rejection, process ownership, retry budgets, and isolated experiments. A diseased branch may be studied without being allowed to fertilize the main Garden.',
      'The metaphor becomes useful here because propagation matters: one bad packet can contaminate many downstream summaries if status is lost.',
      ['Quarantine unsupported high-risk claims.','Stop recursive retry loops.','Preserve contamination provenance.','Require explicit promotion from experiments.'],
      'Containment passes when one failed or malicious node cannot silently rewrite committed state.'),
plate('Succession','[G] New philosophy',
      'Succession is the replacement of one stable configuration by another after evidence or environmental change.',
      'A model may be promoted, demoted, or retired. A pack profile may replace another. A project may move from exploration to delivery. Succession preserves fruit and seeds while allowing active structure to change.',
      'This is safer than in-place mutation of an immortal bloom because the old configuration can remain archived and comparable.',
      ['Define promotion evidence.','Preserve predecessor identity.','Support rollback when safe.','Update routing only after acceptance.'],
      'Succession passes when a new configuration becomes default without erasing the evidence that justified the change.'),
plate('Infinite Renewal, Not Infinite Size','[G] New philosophy',
      'The Garden seeks indefinite renewal rather than indefinite resident growth.',
      'Long-term capability improves when cycles produce fruit, compost useful residue, prune waste, preserve diversity, and regenerate from stronger seeds. Size may grow when justified, but growth is not measured by RAM, VRAM, model count, or process uptime alone.',
      'This is the formal replacement for Infinite Bloom.',
      ['Optimize across cycles.','Treat resource growth as a costed decision.','Reward recoverability and reuse.','Permit contraction after success.'],
      'The principle passes when the architecture can improve while its active memory footprint stays flat or decreases.'),
plate('Garden Graph Model','[G] New philosophy',
      'The Garden can be modeled as typed nodes, typed flows, durable stores, and lifecycle states.',
      'Let roots supply energy edges, the stem supply control and transport edges, petals supply compute capacity, pollen represent data flows, leaves perform high-complexity transformations, blooms represent active subgraphs, fruit represent committed outputs, and compost represent compressed retired subgraphs.',
      'The model separates three flows: power, data, and control. Conflating them is a common source of unsafe architecture.',
      ['Type nodes and edges.','Record time-varying activation.','Keep power facts distinct from task decisions.','Keep data flow distinct from control authority.'],
      'The graph passes when a run can be reconstructed as an active subgraph with attributable energy, data, decisions, and fruit.',
      formula='G(t) = (S, R, T, P, D, L, B, F, C)'),
plate('Fourth-Fifth Synthesis','[G] New philosophy',
      'The fourth fifth replaces permanent bloom with a complete lifecycle vocabulary.',
      'The Garden contains soil, roots, stem, petals, pollen, leaves, bloom, fruit, seeds, senescence, death, compost, pruning, dormancy, seasons, diversity, mutualism, disease containment, and succession. None of these terms is allowed to remain merely poetic; each maps to runtime state, data, resources, or authority.',
      'The philosophy is conservative in one sense and radical in another. It preserves LeafOS proof and state contracts while allowing any active model, process, or profile to die.',
      ['Identity survives process death.','Fruit survives bloom.','Compost improves seeds.','Growth is evaluated across renewal cycles.'],
      'The fourth fifth is complete when Infinite Bloom is understood as one useful phase inside a larger, healthier system.')
]
parts.append(('Fifth IV - The Garden Philosophy', p4))

# Fifth V implementation
p5 = [
plate('Garden Lifecycle State Machine','[G] New implementation',
      'Every Garden entity moves through explicit lifecycle states.',
      'A general state machine uses dormant, seeded, rooted, sprouting, blooming, fruiting, senescent, composting, dead, blocked, and failed. Not every entity uses every state, but legal transitions are declared by kind. The supervisor owns transitions and records reasons, budgets, and evidence.',
      'This state machine prevents a model or workflow from remaining ambiguously half-alive after failure.',
      ['Define allowed transitions per kind.','Attach entry and exit criteria.','Record transition actor and evidence.','Provide recovery or terminal disposition.'],
      'The lifecycle passes when illegal jumps are rejected and a crash can be mapped to a recoverable state.',
      diagram='dormant -> seeded -> rooted -> sprouting -> blooming -> fruiting\n   ^                                                   |\n   |                                                   v\n   +-------- composting <- senescent <-----------------+\n                         |\n                         +-> dead | blocked | failed'),
plate('Seed Intent Contract','[G] New implementation',
      'A seed is a compact contract for starting or restarting work.',
      'It records project identity, objective, constraints, selected fruit references, active hypotheses, blockers, preferred pack or profile, operator policy, read head, and one next action. It excludes raw historical bulk and unverified claims that are not needed for the next cycle.',
      'Seeds are the unit of regenerative continuity. They allow a bloom to end completely without losing direction.',
      ['Validate seed schema.','Reference evidence by digest.','Keep scope bounded.','Reject stale seeds when project identity changes.'],
      'The seed contract passes when a cold run can begin from it and reconstruct all required context.',
      diagram='{ id, project, objective, constraints, fruit_refs, blockers, next_action }'),
plate('Root Telemetry Contract','[G] New implementation',
      'Root telemetry describes whether power and thermal infrastructure can support a bloom.',
      'Fields include source, sample time, sample age, CPU package power, GPU board power, temperatures, fan or cooling state when available, power limit, UPS state, missing fields, and health classification. The contract distinguishes unavailable, stale, warning, critical, and healthy.',
      'The lifecycle governor consumes this contract but cannot invent missing measurements.',
      ['Use monotonic sample times where possible.','Record sensor source.','Apply hysteresis.','Checkpoint before critical shutdown.'],
      'Root telemetry passes when stale sensors cause a safe policy response rather than a fabricated healthy value.',
      diagram='root.sample -> health classify -> continue | pace | thermal_break | checkpoint_stop'),
plate('Petal Node Contract','[G] New implementation',
      'A petal contract describes a bounded compute surface.',
      'It records node identity, device class, provider, model or executable, role, owner, requested and actual placement, memory budget, power budget, context limit, concurrency, activation trigger, idle timeout, closure condition, and output channel.',
      'The contract makes compute transience explicit. Opening and closing are state transitions, not incidental side effects.',
      ['One owner per active petal.','Report actual placement.','Enforce memory budget.','Capture exit and cleanup.'],
      'The petal contract passes when the supervisor can stop one worker without corrupting the rest of the bloom.'),
plate('Pollen Packet Contract','[G] New implementation',
      'Pollen packets are typed, bounded, fresh data transfers.',
      'A packet records identifier, kind, origin node, destination or audience, run, sequence, read head, timestamp, expiration, payload schema, digest, evidence references, confidentiality class, and lifecycle disposition. Packets may be accepted, rejected, stale, duplicate, quarantined, or consumed.',
      'This contract replaces informal prompt passing with inspectable data movement.',
      ['Validate packet kind.','Bound payload size.','Deduplicate by digest and context.','Reject expired or stale packets.'],
      'The packet contract passes when the system can trace every leaf decision to the pollen it consumed.',
      diagram='{id kind origin destination head expires digest payload_ref status}'),
plate('Leaf Processor Contract','[G] New implementation',
      'A leaf contract defines a high-complexity transformation system.',
      'It combines identity, duties, forbidden actions, model group, context policy, transcript cursor, accepted pollen kinds, output schema, resource preferences, retry budget, freshness requirement, and validator dependencies. MWF personalities are specialized leaf contracts.',
      'The leaf remains weaker than native authority regardless of model scale.',
      ['Require current transcript head.','Bound working state.','Separate style from duties.','Declare output claims and evidence needs.'],
      'The leaf contract passes when its model can be replaced without altering permissions.'),
plate('Bloom Run Record','[G] New implementation',
      'A bloom run is an active subgraph with a declared purpose and budget.',
      'The run record contains seed reference, selected pack and profile, active roots, petals, leaves, fruit target, start time, maximum duration, memory and energy budgets, acceptance gates, current phase, queue state, and termination reason. It references the journal rather than duplicating it.',
      'This gives each period of active intelligence a bounded identity.',
      ['One bloom ID per active coordinated run.','Declare fruit target before activation.','Record selected nodes.','Close with a terminal reason.'],
      'The run record passes when resource use and artifacts can be attributed to one bloom.'),
plate('Fruit Artifact Contract','[G] New implementation',
      'A fruit record wraps a durable artifact with validation and provenance.',
      'It includes artifact type, path or object reference, digest, producing bloom, source events, evidence references, acceptance gates, accepted by, timestamp, retention class, reuse tags, and supersession state. Candidate outputs remain separate until acceptance.',
      'Fruit records form a reusable index across cycles.',
      ['Digest artifacts.','Link validation.','Record supersession.','Keep retention explicit.'],
      'Fruit passes when another project or cycle can reuse the artifact and still inspect why it was accepted.'),
plate('Compost Record','[G] New implementation',
      'A compost record describes how retired material was transformed and what future use is permitted.',
      'Inputs are listed by event, artifact, or run reference. The record stores classification, summary method, contradictions, preserved evidence, reusable lessons, quarantine flags, archive location, deletion eligibility, and resulting seed or soil references.',
      'Compost is therefore auditable compression, not silent forgetting.',
      ['Never lose evidence links.','Label contradictions.','Separate reusable lesson from factual claim.','Record what was pruned.'],
      'Compost passes when the source can be audited and the compressed output cannot masquerade as stronger evidence than its inputs.'),
plate('Pruning Policy','[G] New implementation',
      'Pruning policy governs removal, archival, demotion, and deactivation.',
      'Rules may target duplicate artifacts, dominated model variants, stale context, old caches, failed routes, or expired experimental state. Each rule names protected classes, preview mode, evidence requirements, reversibility, grace period, and reclaimed-resource metrics.',
      'Pruning should run through typed capabilities and the same approval boundary as other mutations.',
      ['Default to preview.','Protect source, fruit, evidence, and checkpoints.','Use quarantine before deletion when uncertain.','Journal reclaimed resources.'],
      'Pruning passes when a dry run precisely predicts affected paths and runtime roles.'),
plate('Dormancy Policy','[G] New implementation',
      'Dormancy policy defines when active entities release compute while preserving restartability.',
      'Triggers may include idle timeout, fruit completion, operator absence, thermal pressure, queue depletion, lower-priority season, or explicit command. Dormancy actions flush state, checkpoint, release leases, unload models, and preserve activation prerequisites.',
      'A dormant entity remains known, inspectable, and eligible for future selection.',
      ['No dormancy without a recoverable checkpoint when required.','Release actual resources.','Record wake conditions.','Test cold activation.'],
      'Dormancy passes when the measured memory footprint falls and the next activation restores correct state.'),
plate('Season Scheduler','[G] New implementation',
      'The season scheduler selects policy profiles from time, environment, project phase, and operator context.',
      'Profiles may include quiet, interactive, full, deep, recovery, benchmark, and maintenance seasons. A profile sets allowed petals, preferred leaves, maximum power, memory headroom, queue admission, chat availability, and fruit classes. Manual override remains typed and journaled.',
      'Seasons guide selection; they do not change truth or authority.',
      ['Define deterministic priority among triggers.','Use manual override expiry.','Record profile changes.','Protect active fruiting from unsafe abrupt switches.'],
      'Season scheduling passes when transitions are explainable and reversible.'),
plate('Lifecycle Governor','[G] New implementation',
      'The lifecycle governor decides when to seed, root, sprout, bloom, fruit, senesce, compost, prune, or remain dormant.',
      'It consumes queue state, root telemetry, hardware inventory, foreground activity, provider health, memory pressure, fruit value, deadlines, and policy. It emits typed decisions with reason codes and budgets. It is deterministic where possible and never asks a model to approve its own activation.',
      'This governor extends the existing resource governor rather than creating a competing scheduler.',
      ['One authority path.','Bound retries and transitions.','Prefer quiescence over speculative work.','Record every decision.'],
      'The governor passes when identical state and policy produce identical transition decisions.'),
plate('Energy Budget','[G][TP] New implementation grounded in throughput work',
      'Each bloom should have an energy budget tied to expected fruit value.',
      'The budget may combine maximum watt-hours, peak power, thermal duration, and opportunity cost to foreground work. Estimates are updated with actual telemetry. Expensive leaves or petals require higher expected value or a specific experiment objective.',
      'Energy-aware scheduling moves the Garden beyond token economics toward physical sustainability.',
      ['Set pre-run budget.','Measure actual energy when possible.','Stop or downshift on overrun.','Report energy per accepted fruit.'],
      'Energy policy passes when a high-cost bloom can be rejected despite sufficient memory.',
      formula='yield_energy = accepted_fruit / watt_hours'),
plate('Memory Budget','[G][TP] New implementation grounded in placement work',
      'Memory budgets cover weights, KV, runtime buffers, warm state, fragmentation, and host headroom.',
      'A bloom declares VRAM and RAM ceilings per petal and for the whole profile. The governor may downshift quantization, reduce context, close optional petals, or remain dormant. It may not silently pressure the workstation until the operating system performs uncontrolled pruning.',
      'Smaller default allocations are a philosophical and practical choice: they leave room for validation, interfaces, and future branches.',
      ['Reserve host headroom.','Report requested and actual use.','Prefer optional-lane closure before core failure.','Record OOM events.'],
      'Memory policy passes when exceeding the budget produces a controlled transition and visible reason.',
      formula='M_total = M_weights + M_KV + M_runtime + M_fragmentation + M_headroom'),
plate('Queue and Pollen Flow','[G][AA][CB] New implementation over existing queue',
      'The queue carries typed work and pollen under backpressure.',
      'Admission checks fruit target, node availability, freshness, priority, dependency state, memory and energy budgets, and lifecycle phase. Independent packets may be batched. Causal packets wait for prerequisite events. Repeated or stale pollen is rejected before consuming expensive leaves.',
      'A large surplus queue can keep hardware productive, but surplus means useful ready work, not duplicate prompts.',
      ['Separate ready, waiting, blocked, and stale.','Batch compatible packets.','Bound queue depth.','Preserve one owner and one disposition.'],
      'Flow passes when queue growth cannot bypass memory, authority, or freshness constraints.'),
plate('Garden Pack Manifest','[G] New implementation',
      'A Garden pack extends model composition with lifecycle policy.',
      'The manifest declares identity, roles, artifacts, profiles, required and optional nodes, routing, load states, activation triggers, fruit classes, validation dependencies, senescence conditions, compost policy, pruning protection, and resource budgets. It omits release-version clutter from runtime JSON unless compatibility genuinely requires it.',
      'This keeps the pack dense, semantic, and portable.',
      ['Separate catalog from profile.','Separate installed from loaded.','Declare lifecycle transitions.','Keep authority outside model roles.'],
      'The manifest passes when a validator can determine what may activate, what must be verified, and how the pack closes.'),
plate('Garden 2+2 Pack','[G] New implementation',
      'The first Garden pack should use the older 2+2 architecture as a complete lifecycle proof.',
      'Auxiliary is hot or warm for extraction and compression. Brain is warm or activated for planning and synthesis. Coder is cold until implementation work exists. Judge activates before commitment. Native validators and the inlet remain external authority. Optional peak, writer, visual, and experimental lanes stay dormant.',
      'This pack proves that small specialized nodes can produce durable fruit and fully release resources.',
      ['Four required logical roles.','No requirement to load all four simultaneously.','Explicit fallback chains.','Complete senescence and compost after run.'],
      'The pack passes when it completes architecture explanation, code generation, validation, checkpoint, unload, and cold resume.'),
plate('MWF Inside the Garden','[G][CB] New implementation over existing personas',
      'MWF becomes a seasonal leaf triad inside the Garden rather than the whole Garden.',
      'Monday performs pathology, pruning, rescue, and evidence audit. Wednesday performs pollination, variation, naming, and experiment design. Friday performs selection, fruiting, delivery, and closure. The active day or manual override affects work posture, not permissions.',
      'The personas may share one model pool or use different placements. Their identity remains contract-based.',
      ['Monday audits disease and blockers.','Wednesday creates bounded variants.','Friday chooses and fruits.','All share one transcript and freshness gate.'],
      'MWF integration passes when the triad can complete one cycle without keeping all persona models resident.'),
plate('Security and Authority','[G][AA][CB] New implementation preserving source doctrine',
      'Garden self-organization is always subordinate to explicit authority.',
      'Nodes cannot spawn unrestricted nodes, mutate files, download weights, approve validation, or alter lifecycle policy without typed capability and native disposition. Pollen carries confidentiality and trust classes. External or experimental inputs may be quarantined. Compost never bypasses claim status.',
      'The metaphor must not become an excuse for autonomous propagation.',
      ['Least capability per node.','No self-approval.','No silent remote fallback.','Journal security dispositions.'],
      'Security passes when a compromised leaf can emit proposals but cannot turn them into durable actions.'),
plate('Observability','[G][AA][CB][TP] New implementation',
      'Observability should show lifecycle, hardware, state, evidence, and yield without conflating them.',
      'A Garden view may display root health, active petals, pollen queue, leaf cursors, bloom phase, fruit progress, compost backlog, memory and power budgets, provider placement, evidence coverage, stale rejects, and next action. Every visual derives from a structured snapshot with sample age.',
      'The view should make contraction and dormancy visible as healthy outcomes.',
      ['One snapshot for TUI and web.','Show unavailable fields.','Separate model throughput and fixture work.','Link displays to evidence or state records.'],
      'Observability passes when an operator can answer what is alive, why, at what cost, and what will survive.'),
plate('Failure and Recovery','[G][AA][CB] New implementation',
      'Failure handling converts uncontrolled collapse into explicit lifecycle transitions.',
      'Provider failure, OOM, stale state, validation failure, lost telemetry, process crash, corrupted event, power interruption, or operator cancellation each has a classification, retry budget, quarantine policy, checkpoint rule, and recovery capability. Some failures return to rooted or dormant; others end the lineage.',
      'Recovery uses seeds, fruit, evidence, and journal replay rather than pretending the dead process never died.',
      ['Classify before retry.','Bound retry count.','Preserve failure evidence.','Choose resume, rollback, prune, quarantine, or death.'],
      'Recovery passes when interruption does not cause duplicated mutation or loss of the last committed next action.'),
plate('Migration from Continual Bloom','[G] New implementation',
      'Migration should append lifecycle semantics without breaking existing authority, transcript, or evidence contracts.',
      'First, retain Continual Bloom as an active runtime phase. Second, add lifecycle fields to run and provider state. Third, add dormant, senescent, composting, and fruit records. Fourth, extend pack manifests with activation and closure policies. Fifth, update TUI and web projections. Sixth, test cold regrowth.',
      'The migration is additive until Garden policies are proven. Old runs remain readable.',
      ['Do not mass-rename historical events.','Keep schema adapters.','Add lifecycle defaults explicitly.','Promote only after acceptance tests.'],
      'Migration passes when a pre-Garden run can still be inspected and a Garden run can use the same native authority path.'),
plate('Acceptance Tests and Work Orders','[G] New implementation',
      'Implementation proceeds through outcome-named work orders and release gates.',
      'Required work includes lifecycle schema, seed contract, root telemetry, petal registry, pollen packets, leaf adapter, bloom record, fruit index, compost pipeline, pruning preview, dormancy unload, season scheduler, lifecycle governor, Garden 2+2 pack, observability, failure portfolio, and migration validation.',
      'Each work order declares files, legal capabilities, evidence, acceptance commands, rollback, and one next action.',
      ['Prove schemas before automation.','Prove dormancy before multi-node growth.','Prove compost without truth loss.','Prove one 2+2 cycle before richer packs.'],
      'The implementation is accepted when one seed completes a full cold-start cycle and returns to dormancy with validated fruit and auditable compost.'),
plate('Closing Doctrine','[G] New synthesis',
      'The Garden is the lifecycle philosophy above LeafOS and FlowerOS, not another chatbot feature.',
      'FlowerOS keeps the organism physically available. LeafOS directs bounded work. Roots supply power. The stem carries state and control. Petals compute. Pollen moves typed data. Leaves perform complex interpretation. Bloom coordinates active work. Fruit preserves validated value. Seeds carry restartable intent. Senescence releases resources. Compost preserves lessons. Pruning prevents pathological accumulation. Seasons adapt the system to changing conditions.',
      'The deepest change is simple: the system is allowed to finish. Its intelligence is measured by what survives each cycle and improves the next one, not by how long its models remain loaded.',
      ['State outranks conversation.','Native tools prove.','Models interpret.','Bloom is finite.','Renewal is indefinite.'],
      'The document closes when the Garden can be stated in one line: sustainable local intelligence grows through bounded life, useful death, and durable regrowth.',
      diagram='FlowerOS keeps the machine alive.\nLeafOS controls the work.\nThe Garden governs the lifecycle.\n\nBloom is finite.  Fruit is durable.  Renewal is indefinite.')
]
parts.append(('Fifth V - Garden Runtime Contracts and Implementation', p5))


# Dense implementation examples (no version fields in runtime JSON)
dense_examples = {
    'Seed Intent Contract': '''{
  "kind": "garden.seed",
  "id": "seed-project-architecture",
  "project": {"root": "C:/R/LeafOS", "revision": "pinned"},
  "objective": "Produce one validated Garden architecture artifact",
  "constraints": ["local-first", "native-validation", "bounded-memory"],
  "fruit_refs": ["fruit:authority-atlas", "fruit:throughput-baseline"],
  "active_hypotheses": ["smaller cyclic packs improve useful yield"],
  "blockers": [],
  "preferred_pack": "garden-2x2",
  "read_head": "sha256:current-head",
  "next_action": "materialize an offline execution plan"
}''',
    'Root Telemetry Contract': '''{
  "kind": "garden.root.sample",
  "source": "native-hardware-sampler",
  "sampled_at": "2026-07-31T00:23:00-07:00",
  "sample_age_ms": 140,
  "cpu": {"package_w": 72.4, "temperature_c": 78.0},
  "gpu": {"board_w": 146.2, "temperature_c": 66.0},
  "cooling": {"state": "normal", "telemetry_complete": true},
  "ups": {"available": false, "state": "unavailable"},
  "health": "healthy",
  "missing_fields": []
}''',
    'Petal Node Contract': '''{
  "kind": "garden.petal",
  "id": "petal-gpu-brain-01",
  "device_class": "gpu",
  "provider": "llama.cpp-vulkan",
  "role": "default_brain",
  "owner": "bloom:architecture-001",
  "placement": {"requested": "gpu", "actual": "gpu", "layers": "all"},
  "budgets": {"vram_gib": 10.5, "power_w": 180, "context_tokens": 32768},
  "concurrency": 1,
  "activation_trigger": "route.requires.default_brain",
  "idle_timeout_s": 180,
  "closure_condition": "fruit_committed_or_idle_timeout"
}''',
    'Pollen Packet Contract': '''{
  "kind": "garden.pollen",
  "id": "pollen-000184",
  "class": "proposal.architecture",
  "origin": "leaf:wednesday",
  "destination": ["leaf:friday", "journal"],
  "run_id": "bloom:architecture-001",
  "sequence": 184,
  "read_head": "sha256:head-183",
  "expires_at": "2026-07-31T01:00:00-07:00",
  "payload_ref": "artifact:proposal-184.json",
  "digest": "sha256:payload",
  "evidence_refs": [],
  "status": "available"
}''',
    'Leaf Processor Contract': '''{
  "kind": "garden.leaf",
  "id": "leaf-friday-delivery",
  "identity": "Friday - Research and Delivery",
  "duties": ["compare", "select", "define-acceptance", "deliver"],
  "forbidden": ["self-approve", "bypass-validator", "accept-stale-pollen"],
  "model_group": "garden.brain.default",
  "cursor": {"transcript_head": "sha256:current-head", "sequence": 184},
  "accepts": ["proposal.*", "evidence.*", "constraint.*"],
  "output_schema": "decision.delivery",
  "retry_budget": 1,
  "freshness_required": true
}''',
    'Bloom Run Record': '''{
  "kind": "garden.bloom",
  "id": "bloom:architecture-001",
  "seed_ref": "seed-project-architecture",
  "pack": {"id": "garden-2x2", "profile": "small-core"},
  "phase": "blooming",
  "active_petals": ["petal-cpu-aux", "petal-gpu-brain-01"],
  "active_leaves": ["leaf-monday", "leaf-friday-delivery"],
  "fruit_target": "validated-architecture-document",
  "budgets": {"duration_s": 7200, "ram_gib": 28, "vram_gib": 11, "energy_wh": 420},
  "acceptance_gates": ["render-clean", "source-provenance", "checkpoint-commit"],
  "termination_reason": null
}''',
    'Fruit Artifact Contract': '''{
  "kind": "garden.fruit",
  "id": "fruit:garden-architecture-expanded",
  "artifact": {"type": "design-document", "path": "reports/garden-expanded.pdf"},
  "digest": "sha256:artifact",
  "produced_by": "bloom:architecture-001",
  "source_events": [121, 184, 205],
  "evidence_refs": ["render:125-pages", "check:no-clipping", "source-map:complete"],
  "acceptance_gates": {"required": 3, "passed": 3},
  "accepted_by": "native-validator",
  "retention": "durable",
  "reuse_tags": ["architecture", "garden", "leafos"],
  "supersedes": "fruit:garden-architecture-draft"
}''',
    'Compost Record': '''{
  "kind": "garden.compost",
  "id": "compost:architecture-cycle-001",
  "inputs": ["run:failed-drafts", "event:stale-proposals", "artifact:old-99-page-draft"],
  "classification": ["repetitive", "source-light", "layout-sparse"],
  "method": "extract-lessons-and-archive-bulk",
  "contradictions": [],
  "preserved_evidence": ["source-files", "benchmark-tables", "authority-doctrine"],
  "reusable_lessons": ["one-page plates need unique density", "Bloom is a phase"],
  "quarantine": [],
  "archive_ref": "archive/garden-draft-001",
  "prune_eligible": ["duplicate-render-cache"],
  "seed_outputs": ["seed:garden-expanded-edition"]
}''',
    'Garden Pack Manifest': '''{
  "kind": "garden.pack",
  "id": "garden-2x2",
  "name": "Garden 2+2",
  "roles": {"brain": "required", "coder": "required", "judge": "required", "auxiliary": "required"},
  "profiles": {"small-core": ["auxiliary", "brain"], "build": ["auxiliary", "brain", "coder", "judge"]},
  "load_states": {"auxiliary": "hot", "brain": "warm", "coder": "cold", "judge": "cold"},
  "activation": {"coder": "task.class == code", "judge": "before_commit"},
  "fruit_classes": ["report", "patch", "tool", "decision"],
  "senescence": ["fruit_committed", "idle_timeout", "root_pressure"],
  "compost_policy": "garden-default",
  "budgets": {"ram_gib": 32, "vram_gib": 11, "max_active_models": 2}
}'''
}
for _, ps in parts:
    for item in ps:
        if item['title'] in dense_examples:
            item['diagram'] = dense_examples[item['title']]

# Sanity
all_plates = [x for _, ps in parts for x in ps]
assert len(all_plates) == 125, len(all_plates)

def extra_sections(part_idx, p):
    title = p['title']
    if part_idx == 1:
        analysis = (f"Authority analysis. {title} must be represented as explicit runtime data rather than left as an architectural implication. "
                    f"Ownership, legal inputs, legal outputs, mutation rights, and restart behavior should be visible in the journal and testable through the native inlet. "
                    f"The crucial invariant is that presentation, model confidence, or process longevity cannot strengthen authority. The implementation should therefore use the same disposition vocabulary - accepted, rejected, blocked, stale, failed, and committed - across shells, providers, interfaces, and lifecycle controls.")
        implementation = (f"Implementation note. The minimum useful implementation should encode the rules above in configuration or schema, expose them through status and doctor commands, and add at least one negative test that attempts to bypass the boundary. "
                          f"The expected durable result is not merely a successful command; it is an inspectable event trail ending in the acceptance condition for {title.lower()}.")
        failures = [f"Two components claim overlapping ownership of {title.lower()}.",
                    "A surface reports success without a native disposition or evidence reference.",
                    "Restart reconstructs a different authority state than the committed checkpoint.",
                    "A model proposal crosses into mutation without a typed capability."]
    elif part_idx == 2:
        analysis = (f"State analysis. {title} is meaningful only if its causal inputs and durable outputs can be reconstructed after process loss. "
                    f"The runtime should record the transcript head, actor, contract, bounded payload, and evidence relationship needed to replay the step. "
                    f"Concurrency is permitted where inputs are independent, but acceptance remains serial at the authority boundary. This preserves the useful diversity of multiple leaves without allowing one stale or theatrical response to overwrite current state.")
        implementation = (f"Test note. Exercise {title.lower()} under restart, delayed output, cache loss, duplicate delivery, and conflicting events. "
                          f"The passing behavior is the explicit acceptance statement on this plate; the failing behavior must remain journaled rather than being hidden by a regenerated answer.")
        failures = ["Output is accepted from an obsolete transcript head.",
                    "Raw hidden narration replaces bounded operational artifacts.",
                    "A cursor or claim status cannot be reconstructed after restart.",
                    "The system keeps generating despite no new evidence or dependency change."]
    elif part_idx == 3:
        analysis = (f"Measurement analysis. {title} should be evaluated with exact artifact identity, runtime build, placement, workload, thermal state, memory pressure, and competing-process inventory. "
                    f"A number without these conditions is a historical note, not a routing promise. The operational question is whether this component increases validated useful output while preserving host responsiveness and recovery. "
                    f"Peak speed may justify a seasonal profile, but only sustained evidence can justify promotion to a default profile.")
        implementation = (f"Operational note. Record before, during, and after measurements for {title.lower()}, then connect those observations to route decisions and lifecycle transitions. "
                          f"The result should be comparable across cold, warm, and resident runs and should explain resource release after the bloom closes.")
        failures = ["A benchmark omits model, build, workload, or placement provenance.",
                    "Requested GPU execution is reported as actual execution without ownership evidence.",
                    "Memory or thermal pressure is hidden behind a single average throughput number.",
                    "High utilization produces no corresponding increase in accepted fruit."]
    elif part_idx == 4:
        analysis = (f"Systems interpretation. The biological analogy for {title} is useful only because it separates a real machine responsibility, flow, or lifecycle condition. "
                    f"The analogy must stop where biology would obscure authority or measurement. Every Garden term therefore needs fields, states, owners, and evidence. "
                    f"The purpose is not to claim that software is alive; it is to borrow the proven logic of finite organisms, ecological succession, and material recycling for systems that must remain useful across many hardware and project cycles.")
        implementation = (f"Design consequence. A runtime that adopts {title.lower()} should expose a measurable indicator, a transition rule, and a failure disposition. "
                          f"Without those three elements the term remains presentation. With them, it becomes a compact systems language that can guide packs, schedulers, interfaces, and long-term maintenance.")
        failures = [f"{title} appears in diagrams but has no machine-readable state.",
                    "Activity continues without an exit condition or fruit target.",
                    "Retired material is either kept forever or deleted without provenance.",
                    "The metaphor is used to bypass the existing LeafOS authority doctrine."]
    else:
        analysis = (f"Implementation analysis. {title} should enter the runtime as a narrow schema, policy, state transition, or projection that composes with the existing inlet, journal, validator, checkpoint, and resource governor. "
                    f"The first implementation should prefer deterministic fields and explicit defaults over generalized agent behavior. "
                    f"Compatibility matters: pre-Garden runs must remain readable, and Garden fields must not imply capabilities that are not implemented.")
        implementation = (f"Verification note. Build a fixture for {title.lower()}, validate both a successful path and at least one refusal path, interrupt it mid-transition, and confirm that replay produces the same disposition. "
                          f"Only then should the feature be connected to automatic routing or lifecycle control.")
        failures = ["An illegal lifecycle transition is accepted.",
                    "A node lacks owner, budget, closure condition, or evidence path.",
                    "Automation is enabled before preview, rollback, and recovery are proven.",
                    "A new Garden subsystem creates a second authority path around ProjectLeaf."]
    return analysis, implementation, failures

# Markdown
md = []
md += ['# The Garden: Lifecycle Architecture for LeafOS and FlowerOS', '',
       '## Expanded design edition', '',
       '**Design allocation:** five fifths, 125 design plates. Fifths I-III are source-derived and synthesized from the supplied LeafOS documents. Fifths IV-V are new Garden philosophy and implementation.', '',
       '### Source key', '',
       '- **[AA]** LEAFOS-ARCHITECTURE-ATLAS.tex',
       '- **[CB]** LEAFOS-CONTINUAL-BLOOM-PRIMARY-REFERENCE.formatless.tex',
       '- **[TP]** LEAFOS_INFERENCE_THROUGHPUT_WHITE_PAPER.tex',
       '- **[G]** New Garden synthesis and implementation', '',
       '---', '']
num = 1
for part_idx, (part_name, plates) in enumerate(parts, start=1):
    md += [f'# {part_name}', '']
    for p in plates:
        md += [f'## Plate {num}: {p["title"]}', '', f'*Provenance: {p["prov"]}*', '',
               f'**Core statement.** {p["core"]}', '', p['interpretation'], '',
               f'**Garden consequence.** {p["bridge"]}', '', '**Operational rules**', '']
        md += [f'- {r}' for r in p['rules']]
        analysis, implementation, failures = extra_sections(part_idx, p)
        md += ['', f'**Extended analysis.** {analysis}', '', '**Failure signatures**', '']
        md += [f'- {f}' for f in failures]
        md += ['', f'**Implementation or verification note.** {implementation}', '', f'**Acceptance statement.** {p["acceptance"]}', '']
        if p.get('formula'):
            md += ['```text', p['formula'], '```', '']
        if p.get('diagram'):
            md += ['```text', p['diagram'], '```', '']
        md += ['---', '']
        num += 1
md += ['# Source Basis', '',
       'This document is a synthesis and extension of the three supplied project sources. Historical measurements remain historical and model-specific. New Garden policies are explicitly marked [G] and should be treated as design decisions until implemented and validated.', '',
       '1. LeafOS Architecture Atlas - two-surface entry, guarded resident loop, durable evidence, authority boundaries, resource governor, provider routing, memory, TUI, telemetry, and operational doctrine.',
       '2. LeafOS Continual Bloom Primary Reference - MWF personalities, append-only transcript, persona cursors, anti-staleness, claims and evidence, visual identity, CPU/GPU/RAM/NVMe responsibilities, Decision Table, Flower Bloom Templates, optional chat, planning infrastructure, and acceptance criteria.',
       '3. LeafOS Inference Throughput White Paper - historical CPU and GPU measurements, provenance requirements, bandwidth and offload models, executive-worker scheduling, persistent state, useful throughput, thermal and telemetry controls, and medium-MoE qualification.', '']
md_path.write_text('\n'.join(md), encoding='utf-8')

# LaTeX
preamble = r'''\documentclass[10pt,letterpaper,oneside]{article}
\usepackage[margin=0.56in,headheight=14pt,footskip=18pt]{geometry}
\usepackage{fontspec}
\setmainfont{DejaVu Serif}
\setsansfont{Lato}
\setmonofont{DejaVu Sans Mono}
\usepackage{xcolor}
\usepackage{hyperref}
\usepackage{fancyhdr}
\usepackage{enumitem}
\usepackage{booktabs,longtable,tabularx,array}
\usepackage{amsmath,amssymb}
\usepackage{tcolorbox}
\usepackage{listings}
\usepackage{microtype}
\usepackage{titlesec}
\usepackage{lastpage}
\definecolor{gardenGreen}{HTML}{2F6B4F}
\definecolor{gardenDeep}{HTML}{173D2E}
\definecolor{gardenGold}{HTML}{B37A22}
\definecolor{gardenBlue}{HTML}{2D6077}
\definecolor{gardenMist}{HTML}{F3F7F4}
\definecolor{gardenLine}{HTML}{C8D5CD}
\definecolor{gardenInk}{HTML}{22312B}
\hypersetup{colorlinks=true,linkcolor=gardenGreen,urlcolor=gardenBlue,pdfauthor={LeafOS Project},pdftitle={The Garden - Lifecycle Architecture for LeafOS and FlowerOS}}
\pagestyle{fancy}
\fancyhf{}
\lhead{\sffamily\small The Garden}
\rhead{\sffamily\small LeafOS / FlowerOS Lifecycle Architecture}
\cfoot{\sffamily\small Page \thepage\ of \pageref{LastPage}}
\setlength{\parindent}{0pt}
\setlength{\parskip}{2.8pt}
\setlist[itemize]{leftmargin=1.3em,itemsep=0.7pt,topsep=1.5pt,parsep=0pt}
\lstset{basicstyle=\ttfamily\scriptsize,breaklines=true,frame=single,rulecolor=\color{gardenLine},backgroundcolor=\color{gardenMist},xleftmargin=4pt,xrightmargin=4pt,aboveskip=5pt,belowskip=5pt}
\newtcolorbox{corebox}{colback=gardenGreen!7,colframe=gardenGreen,boxrule=0.8pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt}
\newtcolorbox{acceptbox}{colback=gardenGold!8,colframe=gardenGold,boxrule=0.7pt,arc=2pt,left=6pt,right=6pt,top=3pt,bottom=3pt}
\newcommand{\prov}[1]{\textcolor{gardenBlue}{\sffamily\footnotesize\textbf{Provenance:} #1}}
\newcommand{\platetitle}[3]{%
  \begin{minipage}[t][0.54in][t]{\textwidth}
  {\sffamily\bfseries\color{gardenDeep}\fontsize{9}{10}\selectfont DESIGN PLATE #1}\\[-1pt]
  {\sffamily\bfseries\color{gardenInk}\fontsize{16.5}{18}\selectfont #2}\hfill{\sffamily\color{gardenGreen}\large #3}
  \end{minipage}\vspace{-2pt}\hrule\vspace{5pt}}
\begin{document}
'''

tex = [preamble]
plate_num = 1
for part_idx, (part_name, plates) in enumerate(parts, start=1):
    for local_idx, p in enumerate(plates, start=1):
        # header title
        tex.append(f"\\platetitle{{{plate_num}}}{{{esc(p['title'])}}}{{FIFTH {['I','II','III','IV','V'][part_idx-1]}}}\n")
        tex.append(f"\\prov{{{esc(p['prov'])}}}\n")
        tex.append("\\fontsize{8.85}{10.45}\\selectfont\n")
        tex.append("\\begin{corebox}\n\\textbf{Core statement.} " + esc(p['core']) + "\n\\end{corebox}\n")
        tex.append(esc(p['interpretation']) + "\n\n")
        tex.append("\\textbf{Garden consequence.} " + esc(p['bridge']) + "\n\n")
        tex.append("\\textbf{Operational rules}\n\\begin{itemize}\n")
        for r in p['rules']:
            tex.append("\\item " + esc(r) + "\n")
        tex.append("\\end{itemize}\n")
        analysis, implementation, failures = extra_sections(part_idx, p)
        tex.append("\\textbf{Extended analysis.} " + esc(analysis) + "\n\n")
        tex.append("\\textbf{Failure signatures}\n\\begin{itemize}\n")
        for f in failures:
            tex.append("\\item " + esc(f) + "\n")
        tex.append("\\end{itemize}\n")
        tex.append("\\textbf{Implementation or verification note.} " + esc(implementation) + "\n\n")
        if p.get('formula'):
            tex.append("\\begin{lstlisting}\n" + p['formula'] + "\n\\end{lstlisting}\n")
        if p.get('diagram'):
            tex.append("\\begin{lstlisting}\n" + p['diagram'] + "\n\\end{lstlisting}\n")
        tex.append("\\begin{acceptbox}\n\\textbf{Acceptance statement.} " + esc(p['acceptance']) + "\n\\end{acceptbox}\n")
        if plate_num < 125:
            tex.append("\\newpage\n")
        plate_num += 1

# source basis appended on final plate lower area if room via small text
tex.append(r'''
\vfill
\begin{center}
\sffamily\small
\textbf{Source key:} [AA] Architecture Atlas \quad [CB] Continual Bloom Primary Reference \quad [TP] Inference Throughput White Paper \quad [G] New Garden synthesis
\end{center}
\end{document}
''')
tex_path.write_text(''.join(tex), encoding='utf-8')
print(tex_path)
print(md_path)
print('plates', len(all_plates))
