# Renewal Program Backlog

The first three renewal features are already in place. While validating the fourth requirement we hit a blocker and, on review, identified the remaining seven work items needed to finish the renewal program.

1. **Term-change auditability pipeline**  
   * Add `_snapshot_terms()` on `rmc.contract.agreement` to normalize MGQ, Part-A/B, matrix rows, clause metadata, and bonus/penalty rules before renewal.  
   * Enhance the renewal wizard confirm step to produce JSON deltas (via `jsondiff`) and persist them in a new `rmc.agreement.change.log` model with chatter digests.  
   * Root cause of Task 4 failure: the wizard currently duplicates agreements without computing any snapshot or change log, so downstream processes expecting the log crash.  

2. **Renewal readiness automation**  
   * Add a daily cron that inspects `validity_end` windows (90/60/30 days), schedules owner activities when no draft exists, and transitions ancestors into `negotiation` when a draft renewal is present.  
   * Make the job idempotent (no duplicate activities) and cover corner cases with unit tests.

3. **Sign template reuse policy**  
   * Extend the renewal wizard to evaluate structural changes between agreements; reuse or duplicate `sign_template_id` accordingly, and log chatter notes describing the decision.  
   * Provide helpers to align signer roles whenever a template is reused or re-cloned.

4. **State machine hardening**  
   * Update the agreement workflow so that renewals pass through `negotiation → sign_pending → active`, ensuring only a single active agreement exists per chain (SQL constraint + activation guards).  
   * On activation, wire previous/next pointers, close renewal activities, and broadcast bus notifications.

5. **Billing & KPI continuity**  
   * During renewal activation, roll forward the last three KPI snapshots for read-only analytics and rebind inventory handovers with cleared balances.  
   * Ensure the billing wizard sources Part-A/B, MGQ, bonus, and penalty values from the new agreement while surfacing prior trends for context.

6. **Security & access controls**  
   * Introduce record rules so users with access to an agreement can browse its full renewal chain, while restricting the renewal wizard to `rmc_manager` and `legal_officer` groups.  
   * Expose a "Renewals" menu with filters (90/60/30 day due, negotiation, sign pending) and keep change logs read-only except to managers.

7. **Regression tests & demo fixtures**  
   * Expand the automated test suite to cover renewal creation, change log deltas, cron scheduling, template reuse, activation locking, and billing continuity.  
   * Provide fixture data (or demo records) that exercise the full renewal lifecycle for manual QA.
