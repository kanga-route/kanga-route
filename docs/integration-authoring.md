# Integration Authoring Contract

An integration is a translator around the Kanga-Route engine, never an
extension inside it. If a new integration requires editing
`src/kanga_route/engine/`, stop and open a design issue: the integration is
crossing the contract.

## The stable seam

Implement `IVerificationAdapter` from `kanga_route.contracts`:

```python
class ExampleAdapter(IVerificationAdapter):
    @property
    def name(self) -> str: ...

    @property
    def capabilities(self) -> AdapterCapabilities: ...

    def validate_configuration(self) -> None: ...

    def fetch_targets(self, limit: int = 100) -> Sequence[VerificationTarget]: ...

    def write_outcomes(self, outcomes: Sequence[VerificationOutcome]) -> bool: ...
```

These signatures are intentionally product-neutral. Do not add SDK models,
product field names, credentials, or product exceptions to `contracts.py`,
`models.py`, the batch service, or the engine.

## Adapter responsibilities

Your adapter must:

1. Declare a lowercase, stable name and honest read/write capabilities.
2. Declare its hard batch maximum. The runner rejects a larger request before
   the adapter performs I/O.
3. Validate only its own configuration and raise `AdapterError` before network
   access when it is invalid.
4. Map each remote record to `VerificationTarget(record_id, email, metadata)`.
   The `record_id` must be sufficient for an exact writeback.
5. Accept `VerificationOutcome`, verify or preserve its target identity, and
   format fields only inside the adapter.
6. Translate product failures to a short `AdapterError` and use exception
   chaining (`raise AdapterError(...) from exc`). Never include tokens, response
   bodies, or submitted addresses in the public error.
7. Own paging, throttling, bounded retries, idempotency, and partial-response
   checks required by the product API.

The adapter must not:

- call a verification stage directly;
- reinterpret `Valid`, `Invalid`, `Catch-All`, or `Unknown`;
- put external record IDs or metadata into `VerificationResult` or the cache;
- make the engine import the adapter; or
- require another installed adapter's credentials.

## Registration

Add an allow-listed factory to `kanga_route.adapters.registry`. Do not load an
arbitrary module path from configuration. Users select it with:

```dotenv
KANGA_ROUTE_ADAPTER=example
```

Keep `hubspot` as the default until a separately reviewed migration changes the
operator contract.

## Required tests

Use `tests/test_adapters.py` and the HubSpot wrapper as the reference. Cover:

- name, capabilities, and maximum batch size;
- missing configuration before network access;
- neutral targets with stable record IDs;
- exact target/result pairing on write;
- empty input and the adapter's batch boundary;
- paging and duplicate records;
- transient retry bounds and partial failures;
- exception chaining and secret redaction; and
- registry selection without real credentials or a live product account.

Run the architecture tests as well. They enforce that no product integration is
imported by the verification engine.

## Pull-request checklist

- [ ] No file under `src/kanga_route/engine/` changed for this integration.
- [ ] Only the selected adapter validates its secrets.
- [ ] Product SDK objects do not cross the adapter seam.
- [ ] Cache entries remain product-neutral.
- [ ] Tests need no production credentials.
- [ ] `.env.example`, setup documentation, and the roadmap are updated.
