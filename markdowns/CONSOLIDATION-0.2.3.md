# LeafOS 0.2.3 consolidation

Date: 2026-08-13

## Purpose

LeafOS 0.2.2 accumulated substantially more implementation than its release
identity communicated. This handoff promotes its non-ignored source state into
a separate 0.2.3 location and branch using a plain clone, working-diff overlay,
version update, validation, and Git commit. The only new 0.2.3 capability is a
minimal secure web-model data pipe; it does not create a new scheduler or
execution authority.

## Source lineage

- Preserved source: `C:\R\LeafOS0.2.2`
- New source: `C:\R\LeafOS0.2.3`
- GitHub repository: `LMSM3/LeafOS`
- Branch: `agent/leafos-0.2.3-snapshot`
- Snapshot base: `7ded09f8e9d6ef17aa9db4eb8a0b2a37ec5a32ec`
- Active version authorities: root `VERSION`, taskpack `VERSION`, and
  `leafos.root.json`

The copy carries the current tracked working diff and all non-ignored source
additions. Ignored models, downloads, caches, logs, reports, and runtime records
are not release source and were not copied into Git. The generated
`share/state/operator-home.json` machine snapshot is explicitly ignored.

## Version policy

The active package version is `0.2.3`. Earlier 0.2.2 records remain historical
evidence. The planned 0.9.3 through 0.9.8 labels remain development or roadmap
identities; they do not override the three active package-version authorities
unless promoted by a separate release decision.

## Assumption ledger

| ID | Assumption | Status | Current evidence | Impact | Action |
|---|---|---|---|---|---|
| A1 | The GitHub repository may not exist | CONTRADICTED | Authenticated `gh repo view` resolves `LMSM3/LeafOS`, default branch `main` | No new repository is needed | Publish the new branch to the existing repository |
| A2 | The active source version was already 0.9.x | CONTRADICTED | All three active authorities reported `0.2.2` before this handoff | High-number labels must not drive package identity | Promote only to `0.2.3` |
| A3 | A new 0.2.3 location might collide with existing work | VERIFIED CURRENT | `C:\R\LeafOS0.2.3` did not exist before creation | Safe isolated copy | Preserve `C:\R\LeafOS0.2.2` unchanged |
| A4 | Hard-coded 0.2.2 paths would work from the new location | EXPIRED | Active scripts and configuration contained old absolute roots | Commands would address the preserved tree | Relocate active code/config paths to 0.2.3; preserve historical records |
| A5 | Machine-generated home state belongs in release source | CONTRADICTED | The file records live provider, model, run, and filesystem paths | Publishing it would leak stale machine state into source | Ignore generated `share/state/*.json` records |
| A6 | The existing FlowerOS login file is sufficient web-model authentication | CONTRADICTED | `C:\FlowerOS\lib\install-core.sh` stores a reusable plaintext token, accepts offline-unverified login, and records no expiry, audience, or endpoint scope | Direct reuse would turn an unverified legacy value into a network credential | Never read the legacy file; require a Flower-owned broker to attest a verified session and issue a short-lived scoped credential |

## 0.2.3 web-model boundary

- JSONL requests enter through Bash or PowerShell and one Python transport.
- Packs may supply messages, a pack ID, an allowlisted model, and bounded
  generation settings. They cannot supply endpoints, headers, credentials,
  commands, or execution requests.
- The global route permits an exact allowlisted HTTPS host on port 443, refuses
  redirects and IP-literal endpoints, ignores ambient proxies, and bounds time,
  input, output, messages, and tokens.
- Credentials come only from an absolute FlowerOS broker command over stdin and
  stdout. Broker credentials must attest a verified login, match the configured
  audience and endpoint host, and expire within 300 seconds.
- Results are typed `proposal-only`; the established LeafOS admission, CPU
  validation, queue, journal, and evidence authorities remain unchanged.
- `docs/WEB_MODEL_PIPE.txt` is the operator guide and shell/Python broker wiring
  contract. The default config is disabled and contains no credential.

## Offline validation evidence

- PowerShell root contract: PASS; schema 2, version 0.2.3, asset verified.
- Bash root contract: PASS; schema 2, version 0.2.3, asset verified.
- CCIS unit suite: PASS, 31/31.
- Focused release, WO-053-B, pack, portability, PowerShell, and web-pipe suite:
  PASS, 77/77.
- Web-pipe doctor via Bash and PowerShell: PASS in disabled state;
  `network_probe_performed=false`, `credential_requested=false`.
- Python compile, Bash syntax, JSON parse, and `git diff --check`: PASS.
- High-confidence local secret-pattern scan: PASS, zero matching files.
- Opt-in real-host llama.cpp probe: NOT RUN.
- Live Flower login, credential exchange, and web-provider call: NOT RUN.

## Status

[W] Release 0.2.3: isolate the overgrown 0.2.2 source state without opening later planned releases
[D] Day 3: release-line reset and GitHub handoff
[I] COMPLETE: isolated snapshot plus one disabled-by-default secure web-model pipe
[V] PASS: 31 CCIS tests + 77 focused tests + both root contracts; no live provider probes
[P] READY: agent/leafos-0.2.3-snapshot is validated for one intentional snapshot commit and draft PR
[N] Implement the Flower-owned short-lived credential broker, configure one exact endpoint/model, rerun `--doctor`, then authorize a separate controlled live-provider acceptance test

## Out of scope

- Rewriting historical 0.2.2 evidence.
- Promoting 0.9.3 through 0.9.8 to package releases.
- Copying or downloading model weights.
- Starting providers or running the opt-in real-host llama.cpp preflight.
- Reading or migrating the legacy FlowerOS plaintext auth file.
- Calling a live Flower login, credential broker, or web-model endpoint.
- Modifying the already-dirty FlowerOS repository during this LeafOS release.
- Opening WO-054 or unrelated feature work.
