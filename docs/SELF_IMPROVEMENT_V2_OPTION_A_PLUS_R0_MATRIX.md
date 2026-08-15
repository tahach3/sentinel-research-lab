# R0 evidence matrix — Option A+ candidate (post e85c42ee)

Base: `e85c42ee434cf93346f14f3a890e5fb1385cb06d`
Candidate: this branch tip (`git rev-parse HEAD`)

| Node ID | Classification | Notes |
|---------|----------------|-------|
| A1 dirty `runtime_bridge.py` valid anchors | exact behavioral RED→GREEN | `test_a1_dirty_runtime_bridge_rejects_before_sentinel` |
| A2 dirty `git_worker.py` valid anchors | exact behavioral RED→GREEN | `test_a2_dirty_git_worker_rejects_before_sentinel` |
| A3 preloaded forged `trusted_origin` | exact behavioral RED→GREEN | `test_a3_preloaded_forged_verifier_rejected` |
| B1 `Worker Authorize.disabled=true` | exact behavioral RED→GREEN | both validators |
| B2 `Independent Review Bind.disabled=true` | exact behavioral RED→GREEN | both validators |
| B3 hardcoded Worker Decision Router output | exact behavioral RED→GREEN | both validators |
| C1 permit boolean token fields | exact behavioral RED→GREEN | before `calls_granted` |
| C2 omit consume identity | exact behavioral RED→GREEN | nonce preserved |
| R5 no-env shadow self-pin | GREEN→GREEN control | prior mandatory probe still holds |
| Open-budget boolean matrix | GREEN→GREEN control | already green at base |
| Symlink alias root | collection/setup failure | not claimed (host may deny symlink) |

Helper-import failures are not counted as behavioral red evidence.
