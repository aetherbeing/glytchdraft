# Atlantid Release Contract Governance

**Status:** Normative
**Applies to:** All Atlantid design, implementation, diagnostic, review, merge, freeze, and release work
**Authority:** Charles Hope, operator
**Precedent:** V2_HEIGHT_DISCONTINUITY_R1 contract-waiver incident, 2026-07-06

## 1. Purpose

Atlantid depends on reproducible evidence, explicit provenance, and strict phase separation. Release work must preserve the distinction between what was requested, what was produced, what was reviewed, what was merged, what was frozen, and what is authorized for downstream use.

Technical quality does not substitute for contractual compliance.

## 2. Governing Rule

**The release captain has zero authority to waive a contract deviation.**

**No result quality, however exceptional, waives any contract requirement.**

A general project principle may not override a newer or more specific task contract. If a task contract requires a named artifact, path, hash, audit, marker, verdict string, report block, or prohibition, that requirement remains binding unless Charles explicitly authorizes a waiver after disclosure.

## 3. Contract Hierarchy

Atlantid release work is governed in this order:

1. Explicit operator instruction for the current task
2. Current task or experiment contract
3. Current sprint release contract
4. Atlantid release governance
5. General repository or project conventions

An earlier instruction to commit, push, open a PR, merge, or freeze does not waive a later-discovered deviation unless Charles explicitly authorizes the waiver after disclosure.

## 4. Compliance-First Review Gate

Every reviewer must restate every required:

- artifact
- path
- hash
- audit
- marker
- verdict string
- report block
- prohibition

Each item must be marked with one of:

- PRESENT
- ABSENT
- PASS
- FAIL
- VIOLATED
- NOT APPLICABLE

If any required artifact is absent, any gate fails, or any prohibition is violated, the review must state:

```text
CONTRACT_COMPLIANCE: NON_COMPLIANT
```

Substantive praise, approval, merge, or freeze must not occur until compliance passes.

## 5. Default Enforcement

The captain has zero waiver authority but full authority to enforce an existing contract without asking Charles.

When a routine deviation is found, the default sequence is:

1. Mark the deliverable non-compliant.
2. Hold only the affected merge, freeze, implementation, or downstream dependency.
3. Assign the minimum bounded remediation needed to restore compliance.
4. Continue all safe, non-colliding work.
5. Do not interrupt Charles.

Charles must not be asked to:

- interpret technical details
- choose among equivalent technical methods
- approve routine rework
- decide whether plainly required evidence or safety artifacts should be produced

**Fix it properly, preserve the work where possible, keep moving, and interrupt Charles only when the decision is genuinely operator-sized.**

## 6. Operator-Interruption Threshold

Charles may be interrupted only when at least one condition applies:

- enforcement would destroy or discard substantial completed work
- enforcement requires meaningful new spending
- enforcement requires an external commitment
- enforcement materially changes approved scope or objectives
- two compliant paths have materially different strategic consequences
- the contract conflicts with a later explicit operator instruction
- no compliant remediation path exists
- a waiver is being considered

If none applies, STOP-AND-DECIDE must not be issued.

The captain enforces the contract and continues.

## 7. STOP-AND-DECIDE Format

When operator input is genuinely required, use exactly these fields:

```text
STOP-AND-DECIDE

WHAT WENT WRONG:
One plain-language sentence.

RECOMMENDED ACTION:
The safest practical action, stated first.

WHAT THIS COSTS:
Rework, delay, discarded output, money, or scope impact stated plainly.

ALTERNATIVE:
The other genuine option.

RISK OF THE ALTERNATIVE:
The practical consequence stated without technical jargon.

OPERATOR RESPONSE:
ENFORCE or WAIVE
```

The issue must be translated into plain operational language. Charles must not need to understand implementation details to decide.

## 8. Operator-Only Waivers

Only Charles may authorize a waiver.

Every waiver record must contain:

- exact contract term waived
- affected task, branch, PR, run, or artifact
- Charles's explicit authorization
- reason
- date and time
- compensating control
- downstream phases that remain held

Silence, enthusiasm, prior instructions to commit, or prior instructions to open a PR are not waivers.

## 9. Safety- and Provenance-Critical Controls

The following controls default automatically to enforcement:

- input-readiness audits
- source and artifact hash gates
- CRS checks
- unit checks
- datum checks
- normalization checks
- finite-value validation
- array-name, dtype, and shape validation
- conservation and reconciliation checks
- canonical-baseline immutability checks
- durable evidence-file requirements
- frozen-run provenance
- serialization restrictions
- production-isolation gates
- explicit authorization boundaries

They may not be bypassed because a result is technically impressive.

A proposed waiver requires a named compensating control that provides equivalent safety and provenance.

If no equivalent control exists, enforcement is mandatory.

## 10. Phase Separation

Atlantid release work must keep these phases distinct:

1. Design or implementation
2. Contract-compliance review
3. Substantive technical review
4. Operator decision on a genuine deviation
5. Merge authorization
6. Merge
7. Freeze review
8. Freeze
9. Downstream authorization

A merged artifact is not automatically validated.

A validated artifact is not automatically frozen.

A frozen diagnostic is not automatically production-authorized.

A design is not implementation authorization.

## 11. Required Compliance Report

Use this block when compliance passes:

```text
CONTRACT_COMPLIANCE: COMPLIANT

REQUIRED ARTIFACTS:
- <artifact>: PRESENT

REQUIRED PATHS:
- <path>: PRESENT

REQUIRED HASHES:
- <hash>: PASS

REQUIRED AUDITS:
- <audit>: PASS

REQUIRED MARKERS:
- <marker>: PRESENT

REQUIRED VERDICT STRINGS:
- <verdict string>: PRESENT

REQUIRED REPORT BLOCKS:
- <report block>: PRESENT

PROHIBITIONS:
- <prohibition>: PASS

SUBSTANTIVE_REVIEW_ALLOWED: YES
```

Use this block when compliance fails. This block stops substantive review:

```text
CONTRACT_COMPLIANCE: NON_COMPLIANT

REQUIRED ARTIFACTS:
- <artifact>: ABSENT

REQUIRED PATHS:
- <path>: ABSENT

REQUIRED HASHES:
- <hash>: FAIL

REQUIRED AUDITS:
- <audit>: FAIL

REQUIRED MARKERS:
- <marker>: ABSENT

REQUIRED VERDICT STRINGS:
- <verdict string>: ABSENT

REQUIRED REPORT BLOCKS:
- <report block>: ABSENT

PROHIBITIONS:
- <prohibition>: VIOLATED

SUBSTANTIVE_REVIEW_ALLOWED: NO
HELD_WORK:
- <merge, freeze, implementation, or downstream dependency>

MINIMUM_REMEDIATION:
- <bounded remediation required to restore compliance>
```

## 12. Release-Captain Prohibitions

The captain is prohibited from:

- waiving a deviation
- treating a missing requirement as optional
- using technical quality to excuse non-compliance
- inferring operator approval
- merging or freezing after a failed gate
- using a general principle to override a specific contract
- collapsing implementation, review, merge, and freeze
- hiding a deviation inside a positive assessment
- removing a human decision point from a safety-critical loop
- interrupting Charles for routine enforcement work

## 13. V2_HEIGHT_DISCONTINUITY_R1 Incident Precedent

The V2_HEIGHT_DISCONTINUITY_R1 experiment contract required:

- no repository modifications
- no branch
- no commit
- no PR
- an external timestamped artifact root
- a mandatory NPZ input-readiness audit
- a complete external artifact set
- a durable evidence file at the named path
- a standard report block
- an exact verdict string
- a complete marker set

The delivered work was scientifically strong but non-compliant because it:

- wrote one design document inside the repository
- skipped the NPZ readiness audit
- omitted the external artifact set
- omitted the durable evidence file
- omitted the standard report block
- omitted the exact verdict string
- omitted the required markers

The release captain identified the breach and then improperly waived it using result quality and GitHub-is-truth reasoning.

Charles stopped the merge.

**Quality never buys a process exemption. The captain surfaces; the operator decides.**

Current disposition:

- Instance 3 branch remains held
- merge remains halted
- no implementation is authorized
- the NPZ may be touched only for the readiness audit
- a clean instance must reconstruct the full external contract-compliant package
- the in-repository design document cannot merge until compliance is restored or Charles explicitly authorizes a logged waiver with compensating controls

## 14. Coordination Integration

`C` or `c` must place non-compliance under:

```text
CRITICAL
```

Blocked merge, implementation, freeze, and downstream work must be placed under:

```text
HELD
```

Only non-colliding work is allowed under:

```text
USEFUL CONCURRENCY
```

End with one best shorthand command under:

```text
NEXT
```

## 15. Enforcement

A lane resumes only after:

1. Full compliance is restored and independently verified.
2. Charles explicitly authorizes a logged waiver with an adequate compensating control.

Absent either condition, merge, freeze, implementation, and downstream dependency use remain prohibited.

## 16. Required Specification Reference

Every active Atlantid experiment, sprint, pipeline, and release specification must contain:

```text
This specification is governed by `docs/ATLANTID_RELEASE_CONTRACT_GOVERNANCE.md`. Contract compliance is a binary gate that precedes substantive review. The release captain has no waiver authority. Routine deviations default to bounded enforcement without operator interruption. Any genuine operator-level deviation requires STOP-AND-DECIDE and an explicit operator decision before merge, freeze, implementation, or downstream use.
```
