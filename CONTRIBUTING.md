# Keeping this example simple

This repository is a teaching example. Its goal is that a newcomer learns how
two agents built with Google's Agent Development Kit (ADK) exchange an A2A
message under AAC delegated authority, by running it and reading it: which
pieces there are, and what each one hands to the next. It is not a model of
engineering or security practice for production systems. It is written in the
spirit of the quickstart samples of identity providers and the first-app
tutorials of web frameworks: small enough to read in one sitting, runnable in
a few steps, and honest about what it leaves out. It follows the
[Compose demo](https://github.com/CascadeAuth/aac-compose-demo), which shows
the same reservation over AAC's native delivery.

Everyone who changes it, people and coding agents alike, keeps to what
follows.

## What the example is for

* Show the moving parts and how they interact: the `aac` command-line tool
  (registers the tenant and generates every key, certificate and
  configuration file), the AAC sidecar beside each agent, the two ADK agents
  that make the business decisions, the publisher that makes the tenant's
  public keys available, and the hosted AAC service.
* Show where an agent framework meets AAC: one ADK tool that asks the
  agent's own sidecar to send an A2A message, and ADK's A2A server behind a
  sidecar that lets only verified messages through.
* Expose the inner workings in the simplest way. The run client prints each
  hand-off from what the components actually returned and recorded: the
  agent's tool call, the sidecar's acknowledgement with the peer's reply, the
  chain events both sidecars wrote, the booking agent's record. It never
  prints a summary of its own making.
* Run the same way every time. A scripted model plays the language model's
  part by default, so a run needs no model key and the tests can check its
  result; the agents stay ordinary ADK agents with tools, and one environment
  variable puts a real model in the script's place.

## Principles

1. **Simple beats complete.** Every file should read top to bottom for
   someone new to AAC and to ADK. Prefer a few plain lines to a helper, and a
   named step to a clever construct.
2. **One concept at a time.** The README walks through the flow in the order
   it happens and points at the code for each step.
3. **Show AAC's security; add no security engineering of its own.** Pairing
   signatures, minted and narrowed authority, published trust and the refused
   unsigned call are how AAC works, so the example shows them. Production
   hardening is not what the example teaches. It keeps only what running it
   requires: the containers run as you so they can read the key files the
   CLI creates.
4. **No reliability code.** No retries, recovery wrappers, guards for unusual
   setups or diagnostics commands. When something goes wrong, the message
   from Docker, the CLI, ADK or the sidecar is the message; the README's short
   troubleshooting list covers the common cases. Two exceptions, inherited
   from the Compose demo because a rerun a day later met the first and a
   fresh `up` met the second: the demo renews expired development
   certificates before it runs, and `up`'s publication wait retries a status
   check that fails right after the containers start.
5. **The CLI is the only generator.** The example never creates, copies or
   edits keys, certificates or the sidecar configuration. It reads what
   `aac init` wrote.
6. **The framework stays the framework.** The agents are plain ADK agents
   served and driven by ADK's own runner and A2A server. The example adds the
   one tool, the one interceptor and the one middleware that AAC needs, each
   explained where it stands, and nothing that reaches into ADK's internals.
7. **Say what is left out.** The README names what the example does not show
   (production deployment, durable replay protection, retries, real bookings
   or payments, multi-turn A2A tasks, native Windows) and where that is
   documented.
8. **Tests keep the example working, nothing more.** The Compose file matches
   what the CLI writes, the booking agent refuses unsigned calls and answers
   within the sidecar's reply profile, the trip-planner's tool sends the
   envelope the sidecar expects, the client reads the evidence, and an opt-in
   live test runs the documented steps on real tenants.

## Before adding something

Ask whether it helps a reader understand how AAC works with an agent
framework. If it does not, leave it out, or put it in the AAC documentation
instead.

## PR and fork checks

In an active virtual environment, run:

```sh
python tools/prepare_checks.py
python -m pytest tests -q --ignore tests/live
docker build --quiet --build-arg AAC_INVOKE_AUTH_VERSION=$(python tools/prepare_checks.py --invoke-version) agent
```

The `fixture-checks` job installs the public Python wheels pinned in
`tests/fixtures/components.json`. Its container digests are synthetic Compose
inputs, never downloaded. Updating a package fixture means updating its version,
wheel URL and SHA256 together and rerunning these checks. Dependency installation
and the sample Python image build use the network; the job does no AAC sidecar
registry lookup and needs no private package credentials. It does not write
`.local/components.json`. Real users use `./demo prepare` (or
`./demo prepare --tests` for an existing demo run).

`tests/sidecar_rules.py` is a test-only copy of the sidecar's A2A reply rules.
When the sidecar release in `tests/fixtures/components.json` changes, compare
it with the sidecar's `internal/a2a/response.go` again.
