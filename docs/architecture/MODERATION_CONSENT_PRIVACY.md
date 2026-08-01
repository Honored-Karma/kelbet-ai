# Moderation, photo consent and privacy

## Honest scope

KELBET currently moderates **text only**. The built-in RU/KK/EN component is a conservative
phrase and simple-obfuscation filter, not a semantic classifier. Upload validation checks
ownership, size, MIME type and magic bytes; it is not image content moderation. API and Mini App
therefore expose `image_moderation_supported=false`.

An optional OpenAI adapter implements the documented text request
`POST /v1/moderations` with `omni-moderation-latest`. It is disabled by default and does not send
image bytes or URLs. Official contract references:

- <https://platform.openai.com/docs/api-reference/moderations>
- <https://developers.openai.com/api/docs/models/omni-moderation-latest>
- <https://platform.openai.com/docs/models/default-usage-policies-by-endpoint>

Provider availability, retention documentation and model capability do not replace the owner's
privacy, region, DPA and legal review. Do not enable the external adapter until those production
checks are complete.

## Data recorded

`moderation_decisions` stores user/generation/asset identifiers, context, idempotency key,
SHA-256 of normalized decision input, policy version, mode/outcome, bounded reason codes,
provider/model identifiers, safe technical error code, review state and timestamps. It has no
raw prompt, file content or provider response field.

`user_consents` stores the user, exact source asset IDs, `photo_rights` consent type, policy
version, confirmation timestamp, idempotency key and optional generation binding.

Operator audit records only the review status/outcome. Logs, metrics and Sentry must not contain
prompt text, image bytes, provider response bodies, personal data, initData or authorization.

## User confirmation

Before image edit or image-to-video with a source photo, the user must explicitly confirm that:

- they have the right to use the photograph; and
- people shown in it have consented to the requested use.

The client sends both `rights_consent_confirmed=true` and the server-advertised
`photo_rights_consent_version`. The server rejects missing or outdated versions before wallet
reserve. Changing the source photo resets the client checkbox. The record proves that a stated
confirmation occurred; it does not independently verify ownership or consent.

RU and KK UI copy have parity and link rejected/disputed cases to `/support`.
