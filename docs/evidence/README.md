# Measured runs

A recorded run names the aac-cli, sidecar and publisher releases it used, the
commit of this repository, the scenarios it ran and what each one printed, with
no contact addresses, tenant ids, tokens or keys.

## First live run — 2026-10-20 UTC

[quickstart-20261020.json](quickstart-20261020.json) records the first live
run of this example, with aac-cli 0.2.13, sidecar v0.5.5 (the first release
whose A2A path writes the `mint`, `dispatch` and `receive` chain events this
example correlates) and publisher 0.2.3, on the owner's Mac. The first
`./quickstart` registered two tenants (four GitHub sign-ins, about six
minutes) and then failed at `./demo up`: the trip-planner's client service
combined `extra_hosts` with `network_mode: service:agent`, which Docker
refuses. The fix removes the client's line (it shares the agent's hosts file
anyway); a rerun in the same clone reused both registrations and completed in
21 seconds with the graph rendered from three observed tokens. `./demo run
fare-change` then refused at $9,500 against the $8,000 cap. Each scenario's
evidence shows the sender's `mint` at hop 1 and `dispatch` at hop 2, the
receiver's `receive` of that same token at hop 2, and the booking agent's
`action_taken` row, all on one root. Tests: 62 offline, 2 live.
