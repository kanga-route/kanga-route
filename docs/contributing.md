# Contributing to Kanga-Route

Kanga-Route welcomes focused contributions to the verification engine,
application services, product adapters, appliance delivery, tests, and
documentation. Before beginning a roadmap item, open or claim its GitHub issue
so work is not duplicated.

## Choose a contribution

Start with the [contributor roadmap](roadmap.md). Each item defines its scope,
size, status, and acceptance criteria. Changes that cross an established
boundary should begin with an issue or architecture decision rather than
silently widening an adapter or service contract.

Integration authors must read the [integration authoring contract](integration-authoring.md).
The verification engine must not change merely because a new product, mail
system, or delivery format consumes it. The [architecture](architecture.md)
describes the dependency boundaries enforced by the test suite.

## Prepare a development environment

Use Python 3.12 or newer and a current Docker Engine with the Compose plugin.
Node.js is not required on the host when browser tests run through the pinned
Playwright container.

```bash
python -m venv .venv
. .venv/bin/activate
python -m pip install --editable ".[dev]"
```

A clean checkout does not need a secret `.env` file for tests, Compose
validation, or image builds. Live SMTP verification requires the network and
identity configuration described in the [Docker deployment guide](docker-deployment.md).
HubSpot batch runs additionally require a private-app token; standalone tests
do not.

## Run local validation

Run the Python and Compose checks relevant to every application change:

```bash
python -m compileall -q src tests infra scripts
python -m pytest --verbose

docker compose config --quiet
docker compose build engine
docker compose run --rm --no-deps engine kanga-route-engine --help
```

For browser-console changes, start the local cache and UI:

```bash
docker compose up -d --wait dynamodb-local
docker compose --profile ui up -d --wait web
```

Open `http://127.0.0.1:8080/`, then run the browser interaction suite:

```bash
docker run --rm --network host \
  --volume "$PWD:/workspace" \
  --workdir /workspace/browser-tests \
  mcr.microsoft.com/playwright:v1.62.1-noble@sha256:dcc5531e97840b9b5e794f2814476b21571c5124a3fca2267d73041f56e7580e \
  /bin/bash -lc 'npm ci && npm test'
```

Stop all optional profiles after testing:

```bash
docker compose --profile ui --profile mail-policy down
```

Changes to Packer should also pass:

```bash
packer init packer/kanga-route.pkr.hcl
packer validate packer/kanga-route.pkr.hcl
```

## Submit a pull request

Keep a pull request centered on one roadmap item or one cohesive correction.
Include tests for behavior, update the relevant audience guide, and record a
new or superseding architecture decision when the change establishes a durable
contract. Never include credentials, `.env` contents, Pulumi state, stack
outputs, customer data, or cloud account identifiers.
