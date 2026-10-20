# AAC: two ADK agents, one reservation over A2A

Marc Sterling, a director at Austin-based private equity firm Vantis Equity,
needs to oversee an acquisition on-site in Shanghai. He uses Tourfedia's
corporate travel management platform to organize his trip from Austin (AUS)
to Shanghai (PVG).

This is the reservation the [Compose demo](https://github.com/CascadeAuth/aac-compose-demo)
makes over AAC's native delivery, made again between two agents built with
Google's [Agent Development Kit](https://google.github.io/adk-docs/) (ADK)
that talk [A2A](https://a2a-protocol.org/). Vantis Equity's trip-planner
agent asks Tourfedia's booking agent to create a **reservation**. Each
fictional organization has its own AAC tenant, assigned trust domain, CA,
public trust publication and private keys, and an AAC sidecar beside its
agent.

Marc Sterling's approval is **simulated**: PO #4143, Austin to Shanghai,
departing 12 May, up to $8,000. The trip-planner's one tool hands that order
to its own sidecar, which mints the authority for the task, narrows it to
this order and amount, signs the A2A message and delivers it to Tourfedia's
sidecar. Tourfedia's sidecar verifies the sender's authority against Vantis's
published trust and only then passes the unchanged message to the booking
agent, which ADK serves over A2A. The booking agent's one tool holds the
reservation within the amount it was allowed and records what it did. The
example application creates a reservation result; supplier integration and
payment are omitted for clarity.

A **scripted model** plays the language model's part by default, so a run
needs no model key, gives the same result every time and is checked by the
tests. The agents are ordinary ADK agents with tools; only the model class is
swapped. Section 5 puts your own model in its place.

## Requirements

macOS or Linux, Git, Python 3.11+ and Docker with Compose and Buildx. You will register
two stage developer tenants you control. Registration requires interactive
GitHub sign-in.
The two tenants can have the same human owner. A contact email is registration
metadata; it does not select your GitHub account.

| Public component | How it is supplied |
|---|---|
| [aac-cli on PyPI](https://pypi.org/project/aac-cli/) | Install in your host Python environment |
| [AAC sidecar on Docker Hub](https://hub.docker.com/r/cascadeauth/aac-sidecar/) | Compose pulls the selected immutable image |
| [Trust anchor publisher on GHCR](https://github.com/orgs/CascadeAuth/packages/container/package/aac-trust-anchor-publisher) / [Python package and operating guide on PyPI](https://pypi.org/project/aac-trust-anchor-publisher/) | Compose pulls the selected image |
| [aac-invoke-auth on PyPI](https://pypi.org/project/aac-invoke-auth/) | Installed inside the agent image |
| [google-adk on PyPI](https://pypi.org/project/google-adk/) | Installed inside the agent image, with its A2A server |
| [LiteLLM on PyPI](https://pypi.org/project/litellm/) | Installed inside the agent image, used only when you choose a model through it |
| [Python application image](https://hub.docker.com/_/python) | Agent base image; host Python is also required for the CLI |
| [uvicorn](https://pypi.org/project/uvicorn/) / [httpx](https://pypi.org/project/httpx/) | Installed inside the agent image |

Current AAC installation metadata is published in the
[released-component record](https://docs.cascadeauth.com/released-components.json).
The exact combination exercised by this example remains in Compose, the Dockerfile,
test dependencies and [test receipts](docs/evidence/README.md). Component updates
must pass the example's checks; changing a guide does not change a recorded
run or silently select a different container.

No private repository or AAC SDK is required. The agents build locally from
this public source. See the [AAC guide](https://docs.cascadeauth.com/) for
protocol and configuration reference, the
[A2A integration page](https://docs.cascadeauth.com/sidecar/a2a/) for what the
sidecar adds to A2A, and the Compose demo for the native delivery flow with
its signed terminal receipt.

## Quickstart

To see the whole journey once before reading it step by step, run the
quickstart from a fresh clone. It runs steps 1 to 4 below exactly as written,
printing each command before it runs (the trust sections it appends in step 3
show only as `cat`; their text is in the script), then renders the execution
graph and opens it in your browser where one is available. It runs the
reservation scenario only. On a machine without a browser, such as a server or
VM, it says so and prints how to copy the graph to one that has a browser.

Before you run it, check the two versions that matter:

```sh
python3 --version
docker compose version
```

`python3` must be 3.11 or later. The `python3` built into macOS is 3.9, so
install a newer one first, from [python.org](https://www.python.org/downloads/)
or Homebrew; the quickstart stops with a message if `python3` is too old. On
Debian or Ubuntu, Python's `venv` is a separate package: `sudo apt install
python3-venv`. Docker must be running, with the Compose plugin (`docker
compose`, not the older `docker-compose`) and Buildx; Docker Desktop includes
both. On Linux, your user must be able to run `docker` without `sudo` (see
Docker's [post-installation steps](https://docs.docker.com/engine/install/linux-postinstall/)). You also
need Git and a browser for the GitHub sign-ins.

```sh
git clone https://github.com/CascadeAuth/aac-adk-a2a-demo.git
cd aac-adk-a2a-demo
VANTIS_CONTACT='you+vantis@example.com' TOURFEDIA_CONTACT='you+tourfedia@example.com' ./quickstart
```

Use your real contact addresses. You sign in with GitHub four times in your
browser, two per tenant, and acknowledge each permanent tenant registration.
If you already ran the Compose demo, these are two more tenants: each clone
has its own CLI home. Read [quickstart](quickstart) alongside steps 1 to 4:
the steps explain what each command does and why. If a step fails, fix the
cause and run the same command again, with both contact addresses, in the
same clone; it reuses both registrations. The development certificates the
CLI creates expire (section 6 says how renewal works): a rerun after that
renews the expired ones before step 2 and prints what it renewed, and
`./demo run` does the same before a scenario.

The demo keeps running in Docker until you stop it with `./demo down`. The
quickstart's settings end with the script, so put the demo's CLI home in
front of each later command:

```sh
AAC_CLI_HOME="$PWD/.local/aac" ./demo run fare-change
AAC_CLI_HOME="$PWD/.local/aac" ./demo down
```

To work through the later steps by hand instead, use a terminal dedicated to
the demo, as step 1 does: activate the tools and point the CLI at the demo's
home with the two lines below.

```sh
. .aac-tools/bin/activate
export AAC_CLI_HOME="$PWD/.local/aac"
```

## How the pieces hand work to each other

Read the code in this order; each file is short.

1. [agent/client.py](agent/client.py), `ask_trip_planner`: `./demo run`
   starts the trip-planner with ADK's runner and gives it Marc's simulated
   approval as a message: a sentence and the order as JSON.
2. [agent/scripted_model.py](agent/scripted_model.py): the model's first move
   is to call the agent's one tool with that order. A live model does the
   same from the words; the script does it from the JSON.
3. [agent/agent.py](agent/agent.py), `request_reservation`: the tool builds the
   sidecar's dispatch envelope, named after the destination `tourfedia`, in
   `originate` mode under the class of action `reserve_travel`, narrowed by
   `amount_max`, `originator_reference` and `task_ref`, carrying the A2A
   `SendMessage` request. It signs the envelope with the pairing secret the
   CLI created and posts it to its own sidecar on the pair's loopback.
4. Vantis's sidecar mints root authority for the task, delegates it to
   Tourfedia with those limits, signs the A2A request with the delegated
   authority and a proof of possession, and sends it to
   `https://booking:9443/a2a/v1`.
5. Tourfedia's sidecar verifies the chain against Vantis's published trust,
   checks that its own agent is the intended recipient, and calls the booking
   agent's `/a2a/v1` with the unchanged message and the verified `X-AAC-*`
   headers, signed with Tourfedia's pairing secret.
6. [agent/agent.py](agent/agent.py), `a2a_app`: ADK's A2A server for the
   booking agent, wrapped in two small pieces: the pairing-signature check
   from aac-invoke-auth, so only the sidecar can reach it, and
   `VerifiedContext`, which keeps the verified headers where the tool can read
   them. `hold_reservation` holds the unpaid reservation if the fare is within
   `amount` and writes the booking agent's action record with the token the
   sidecar presented.
7. `stamp_context_id`: ADK answers with a completed A2A task whose history
   holds the model's tool call and the tool's result. The sidecar checks every
   message in the reply and requires a context id on each; ADK sets it on the
   task and leaves it off the messages, so this interceptor copies it over
   before the reply leaves the agent.
8. Tourfedia's sidecar checks the reply against its profile and returns it to
   Vantis's sidecar, which returns it to the tool inside the acknowledgement,
   byte for byte. The scripted model's second move says what Tourfedia
   answered.
9. [agent/client.py](agent/client.py), `run`: the client then reads the
   evidence: the `mint` and `dispatch` events Vantis's sidecar wrote, the
   `receive` event Tourfedia's sidecar wrote and the booking agent's action
   record, all correlated by task and root token, and prints them. An HTTP
   200 or `dispatched` acknowledgement alone does not pass.

## 1. Install AAC CLI and prepare the example

### Install AAC CLI

Install [aac-cli from PyPI](https://pypi.org/project/aac-cli/) in a virtual
environment. The package supplies both `aac` and `aeg`; its PyPI page also
contains installation and usage documentation.

```sh
python3 -m venv .aac-tools
. .aac-tools/bin/activate
python -m pip install --upgrade aac-cli
aac --version
aeg --version
```

### Prepare the example

Keep that virtual environment active, then download and prepare the example:

```sh
git clone https://github.com/CascadeAuth/aac-adk-a2a-demo.git
cd aac-adk-a2a-demo
./demo prepare
mkdir -p .local
export AAC_CLI_HOME="$PWD/.local/aac"
cp config/trip-planner.yaml .local/trip-planner.yaml
cp config/booking.yaml .local/booking.yaml
```

Keep this environment variable in each terminal used for the demo. It gives
the demo its own CLI home and leaves your other profiles alone.

These are **operator-authored inputs**, supplied explicitly with
`--agent-config`. Each names the two A2A addresses the sidecar needs: the
HTTPS address at which the peer reaches it (`public_base_url`) and the agent's
handler on the pair's loopback (`local_handler_url`). The CLI alone generates
keys, certificates, publisher configuration, `compose.env` and the complete
`sidecar-config.yaml`, including the A2A limits and the retained-dispatch
state file. Never hand-edit those generated outputs or consume the private
`record.json` schema.

The inputs select Basic in-memory replay protection with `dev_mode: false`.
Each pair shares its own loopback interface; the sidecars communicate over a
private Docker network using HTTPS names `trip-planner` and `booking`.
No host ports are published.

`./demo prepare` resolves the current stable AAC package releases from PyPI and the
sidecar from the published release record, then resolves exact container digests.
It saves `.local/components.json` and installs the selected CLI in your active
virtual environment. Subsequent starts and maintenance reuse that file; they
never silently change a running demo. To start a new run with newer components,
stop the demo, retain the old receipt, and move the selection file aside before
running `./demo prepare` again. There is no mutable sidecar `latest` tag.

## 2. Register two tenants

Set your real contact addresses:

```sh
export VANTIS_CONTACT='you+vantis@example.com'
export TOURFEDIA_CONTACT='you+tourfedia@example.com'
aac init \
  --profile vantis \
  --agent trip-planner \
  --agent-config .local/trip-planner.yaml \
  --layout container \
  --admin-url https://api.stage.cascadeauth.dev \
  --data-plane-url https://api.stage.cascadeauth.dev \
  --trust-url https://trust.stage.cascadeauth.dev \
  --idp github \
  --display-name 'Vantis Equity ADK Demo' \
  --contact "$VANTIS_CONTACT"
aac init \
  --profile tourfedia \
  --agent booking \
  --agent-config .local/booking.yaml \
  --layout container \
  --admin-url https://api.stage.cascadeauth.dev \
  --data-plane-url https://api.stage.cascadeauth.dev \
  --trust-url https://trust.stage.cascadeauth.dev \
  --idp github \
  --display-name 'Tourfedia ADK Demo' \
  --contact "$TOURFEDIA_CONTACT"
```

Run interactively and acknowledge each permanent tenant registration. There
are two sign-ins per tenant: registration and administration. Use the same
GitHub account for both sign-ins of that tenant. A rerun reuses its registration;
it does not create another tenant. Noninteractive registration additionally
requires the explicit `--create-tenant` acknowledgement.

The assigned domains come from AAC; owning `tourfedia.com` is not a trust-domain
binding. Empty peer configuration is intentional during initial registration.

## 3. Explicitly trust and address the peer

Read the registered facts through supported CLI status output:

```sh
aac agent status --agent trip-planner --output json > .local/vantis-status.json
aac agent status --agent booking --output json > .local/tourfedia-status.json
VANTIS_TENANT=$(aac agent status --agent trip-planner --field tenant-id)
VANTIS_DOMAIN=$(aac agent status --agent trip-planner --field hosted-trust-domain)
VANTIS_ID=$(aac agent status --agent trip-planner --field workload-spiffe-id)
TOURFEDIA_TENANT=$(aac agent status --agent booking --field tenant-id)
TOURFEDIA_DOMAIN=$(aac agent status --agent booking --field hosted-trust-domain)
TOURFEDIA_ID=$(aac agent status --agent booking --field workload-spiffe-id)
```

Append these sections **once** to the input copies. Vantis trusts Tourfedia's
published keys and names the booking agent as its A2A destination: the
destination `url` is Tourfedia's public base URL with `/a2a/v1` appended, the
address its Agent Card advertises, and `audience_pattern` is the booking
agent's exact registered identity. Tourfedia trusts Vantis's published keys;
it needs no destination, because it only answers. The peer's public CA path
is an explicit HTTPS trust choice; no private key is exchanged. In a real
deployment the peer supplies that public certificate; reading it from the
other agent's local directory is a convenience of running both tenants on one
machine.

```sh
cat >> .local/trip-planner.yaml <<EOF
trust_anchors:
  tenant_ids: [$TOURFEDIA_TENANT]
spiffe_bundles:
  trust_domains: [$TOURFEDIA_DOMAIN]
https_trust:
  ca_files: ["$AAC_CLI_HOME/agents/booking/agent/ca.crt"]
destinations:
  tourfedia:
    url: https://booking:9443/a2a/v1
    audience_pattern: $TOURFEDIA_ID
    predicates:
      action: reserve_travel
    valid_for: +30m
    timeout_ms: 10000
EOF
cat >> .local/booking.yaml <<EOF
trust_anchors:
  tenant_ids: [$VANTIS_TENANT]
spiffe_bundles:
  trust_domains: [$VANTIS_DOMAIN]
EOF
aac init --profile vantis --agent trip-planner --agent-config .local/trip-planner.yaml
aac init --profile tourfedia --agent booking --agent-config .local/booking.yaml
```

These trust settings have different jobs: verify tenant root signatures,
verify workload certificates, and verify outbound HTTPS connections. The
class of action `reserve_travel` supplies `valid_for: +2h` for the root
authority; the destination supplies `+30m` for what Tourfedia receives. The
amount comes only from the application, as a predicate on the dispatch.

## 4. Start and run

```sh
./demo up
./demo run
./demo run fare-change
```

`up` builds the agent image, starts the two pairs and their publishers, and
waits for readiness and public trust publication, for up to five minutes.
`run` starts the trip-planner once in the Vantis pair, then waits up to 30
seconds for the correlated evidence. Failure or missing evidence exits
nonzero. A failed run shows the client's error, then the rows it printed
before stopping, and exits with the client's exit code; the sidecar logs on
either side are the next place to look (`./demo compose trip-planner logs
sidecar`, `./demo compose booking logs sidecar`), and the booking agent's log
shows ADK's A2A server (`./demo compose booking logs agent`).

The output is a sequence of JSON lines, each from a component: the
trip-planner's tool call with its arguments, the sidecar's acknowledgement with
Tourfedia's reply inside `a2a_response`, the trip-planner's final sentence,
and the `evidence` line with the `mint`, `dispatch` and `receive` events and
the booking agent's action record, correlated by `task_ref` and
`root_token_id`. Read it alongside [agent/client.py](agent/client.py) and
[agent/agent.py](agent/agent.py).

The normal run reports an $8,000 reservation. In the fare-change run the
booking agent sees a fare of $9,500, above the $8,000 Vantis allowed, and
declines; this is a business decision inside the authority, not a refusal by
AAC. Its reply says so and its action record shows `refuse`.

Local `state/telemetry.jsonl` and `state/actions.jsonl` contain the protocol
and business evidence. The demo operator controls both stacks and reads their
records locally. This is not automatic access to another tenant's files.
Private business records, caps and expiry stay local. The sidecars also record
`a2a_egress` and `a2a_ingress` diagnostics for every message; see
[audit your workflows](https://docs.cascadeauth.com/sidecar/operations/#audit-your-workflows)
for the fields.

### View this execution graph

Each `./demo run` saves its evidence in `.runs/`, prints the order → scenario
→ task-reference → root mapping and prints a complete `aeg render` command
with the actual telemetry and action paths and the HTML output. Run that
printed command; `aeg` is installed with the CLI. The resulting HTML opens
without a server or network assets; double-click nodes for the limits,
workload identities and the booking agent's record. An A2A exchange has no
signed terminal receipt, so the graph ends at the booking agent's received
token and its action; the Compose demo shows the native flow that adds the
receipt. The [AEG guide](https://docs.cascadeauth.com/aeg/) covers the
schema, source modes, `aeg list`, filtering and interpretation.

## 5. Run it with your own model

The scripted model in [agent/scripted_model.py](agent/scripted_model.py)
makes the two moves a language model would make: call the agent's one tool
with the order, then say what the tool reported. To watch a real model make
them, set `AAC_DEMO_MODEL` and the setting it needs, recreate the containers,
and run again. For Gemini, one key:

```sh
export AAC_DEMO_MODEL=gemini-2.5-flash
export GOOGLE_API_KEY=your-key
./demo up
./demo run
```

Any other model ADK reaches through its LiteLLM extension works the same
way; a name with a slash selects that route. The `x-model` block at the top of
[compose.yaml](compose.yaml) passes exactly these settings into the containers:
`AAC_DEMO_MODEL`, `GOOGLE_API_KEY` and `OLLAMA_API_BASE`. A provider that needs
another key is added there. For a model served by Ollama on your machine,
point the containers at it; the Compose file maps `host.docker.internal` to
your machine on Linux as well as on Docker Desktop:

```sh
export AAC_DEMO_MODEL=ollama_chat/llama3.1
export OLLAMA_API_BASE=http://host.docker.internal:11434
./demo up
./demo run
```

Unset `AAC_DEMO_MODEL` and run `./demo up` again to return to the script. The
model never sees a key, token or proof: the tools talk to the sidecars, and a
model that calls the tool with a different amount changes only what Vantis's
sidecar allows Tourfedia to spend. Model output varies, so the client checks
the evidence, not the sentences: the amount the model asked the tool for must
be the limit on the authority and the amount held, whatever the sentences say.

## 6. Refresh, renew and restart

Refresh uses the last explicitly applied input, even if the source YAML has
since been edited. To apply edits, pass `--agent-config` explicitly.

```sh
aac init --profile vantis --agent trip-planner
aac init --profile tourfedia --agent booking
./demo up
./demo run
```

Leaf renewal keeps identities, root key, destinations and peer configuration.
`aac agent status` shows when each certificate runs out. `./demo renew` runs
`aac agent renew` for each agent whose leaf certificates have expired and
nothing else, and `./demo up` then loads the new files; `up` and `./demo run`
renew the same way before they start. When the development CA itself has
expired or is within its renewal window, the demo stops and prints the
commands that replace and republish it; the Compose demo's
[section 6](https://github.com/CascadeAuth/aac-compose-demo#6-refresh-renew-and-restart)
walks through that procedure, which is the same here.

## Cleanup and limits

```sh
./demo down
```

This removes the local containers and network and preserves the CLI home and
evidence. Tenant registrations are permanent; deleting a local profile does
not delete a tenant. Keep protected copies of credentials and keys, or
deliberately retire test workloads through the supported tenant lifecycle.

This teaches AAC with ADK over A2A, in the sidecar's unary profile: one
`SendMessage`, one reply. It does not show streaming, multi-turn A2A tasks,
push notifications, continuing a received authority onward, payment
processing, durable inventory, production hardening, retries or reliable
delivery. Basic replay history is lost on sidecar restart. ADK's A2A support
is marked experimental by Google. Native Windows is not supported.

## Tests and recorded evidence

`prepare --tests` installs the test dependencies and AAC helpers matching the
existing run selection. It retains the selected CLI and component receipt.

```sh
./demo prepare --tests
python -m pytest tests -q --ignore tests/live
AAC_DEMO_LIVE=1 python -m pytest tests/live -q
```

Live tests use the already-authorized, configured tenants in `AAC_CLI_HOME`.
See [docs/evidence/README.md](docs/evidence/README.md) for the measured
versions, commits and cases of recorded runs.
