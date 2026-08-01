# KELBET moderation runbook

## Deployment defaults

1. Apply migration `0013_moderation_consent` after `0012_admin_operator_audit`.
2. Deploy with `MODERATION_MODE=report` and `MODERATION_EXTERNAL_PROVIDER=none`.
3. Confirm `/api/v1/moderation/config` returns the intended policy/consent versions and
   `image_moderation_supported=false`.
4. Confirm an image-edit request without current consent returns 422 before reserve.
5. Confirm support can read `/api/v1/admin/moderation` and cannot review; admin can review once
   and an exact replay returns the same audit event.
6. Watch `kelbet_moderation_decisions_total` by outcome/context/provider. Do not add IDs or
   reason free text as labels.

Move from `report` to `block` only after reviewing false positives for RU and KK and completing a
staged canary. The change is a server setting; clients cannot turn blocking on or off.

## External provider

To opt in, store `OPENAI_MODERATION_API_KEY` as a sealed secret and set
`MODERATION_EXTERNAL_PROVIDER=openai`. Keep text-only wording in product/UI. Choose and document:

- `MODERATION_EXTERNAL_FAILURE_POLICY=open`: safe technical outage is recorded as `report` and
  the request may proceed; or
- `closed`: outage is rejected before billing.

Never log the request body, response body, authorization header or exception message. A real
staging smoke test and owner privacy/region review remain external gates.

## Triage

1. Open the metadata-only moderation queue; correlate by decision/generation/user UUID and hash.
2. Review as `confirmed_violation`, `false_positive` or `needs_escalation`, with safe coded
   reason/reference.
3. Do not paste the user's prompt or personal data into audit fields.
4. Do not permanently block an account solely because of one decision. Account block is a
   separate admin action requiring separate evidence/reason.
5. Direct the user to `/support` for appeal. Preserve decisions, consent and audit evidence.

## Incident and rollback

- False-positive spike: `block -> report`, then inspect policy/provider distribution.
- Provider outage with unacceptable bypass risk: choose `closed`; if availability is more
  important, use `open` and monitor reports. Record the operational decision.
- Local rule regression: `report` while deploying a new `MODERATION_POLICY_VERSION`; do not alter
  historic rows.
- Emergency disable: set `MODERATION_MODE=off`. Photo-rights consent remains required because it
  is an independent gate.
- Never delete moderation, consent or audit rows as part of rollback.
