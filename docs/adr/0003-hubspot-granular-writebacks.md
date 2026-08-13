# 3. Granular CRM Intelligence Writebacks

**Date:** 2026-08-05
**Status:** Accepted
**Amended:** 2026-08-13

## Context

A binary valid/invalid result is insufficient for RevOps. Sales teams need to
know why an address failed, while transient DNS, network, and SMTP policy
conditions must not be misrepresented as evidence that a mailbox is invalid.

The original accepted decision defined four HubSpot properties and three
statuses. The MVP added an explicit `Unknown` outcome, a verification timestamp,
and a larger reason vocabulary so ambiguous results can be written back and
retried safely.

## Decision

The engine writes each result through the HubSpot CRM Batch API using these
five contact-property internal names:

| HubSpot property | Internal name | Writeback value |
|---|---|---|
| Email Verification Status | `email_verification_status` | `Valid`, `Invalid`, `Catch-All`, or `Unknown` |
| Email Verification Reason | `email_verification_reason` | One of the reason enum values below |
| Mailbox Provider | `mailbox_provider` | Detected provider name |
| Is Role Account | `is_role_account` | Lowercase text `true` or `false` |
| Last Verified | `last_verified` | UTC verification time as Unix epoch milliseconds |

The exact reason values are:

- `OK`
- `Syntax_Error`
- `Disposable`
- `No_MX`
- `User_Not_Found`
- `Greylisted`
- `Timeout`
- `Connection_Refused`
- `Unknown_Host`
- `DNS_Timeout`
- `DNS_Error`
- `SMTP_Temporary_Failure`
- `SMTP_Rejected`

Classification is conservative:

- `Valid / OK` means the recipient was accepted.
- `Catch-All / OK` means a randomized nonexistent recipient was also accepted.
- `Invalid` is limited to authoritative evidence represented by
  `Syntax_Error`, `Disposable`, `No_MX`, or `User_Not_Found`.
- `Unknown` records transient or ambiguous outcomes represented by the
  remaining non-`OK` reasons. It is visible in HubSpot but is not cached.

Every writeback includes `last_verified`, including `Unknown` results. HubSpot
search filters use that datetime for the `UNKNOWN_RETRY_AFTER_HOURS` cooldown
and the `REVERIFY_AFTER_DAYS` stale-result schedule.

## Consequences

### Positive

- RevOps can distinguish actionable invalid addresses, catch-all domains, and
  inconclusive checks without treating a transient failure as a hard bounce.
- The timestamp supports controlled retries and scheduled re-verification.

### Negative

- HubSpot property internal names, types, and dropdown values must match the
  application enums exactly.
- Consumers must handle `Unknown` as a first-class result rather than forcing
  every contact into a binary decision.
- Changing an enum value is a CRM schema migration, not only a code change.

## Amendment history

The 2026-08-13 amendment retains the original granular-writeback decision and
documents the five-property contract implemented by the MVP. It adds the
`Unknown` status, `last_verified`, and the complete current reason vocabulary.
