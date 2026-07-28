# Round 5A Repair Notes

- Proposed Gemini pilot authorizations use `expires_at = -infinity` until governed activation.
- `research.activate_pilot_authorization` sets `activated_at` and `expires_at = activated_at + 24 hours`.
- Direct `proposed`→`active` updates are clamped to a 24-hour window by trigger.
- `research.live_preflight` enforces linked `provider_pilot_proposals` aggregate bounds.
- Test residue uses `test_fixture_id` and is cleaned via `research.cleanup_test_fixture`.
