# Kanga-Route AMI catalog

This page shows the newest Kanga-Route appliance image recorded for each AWS
region. AMI IDs are region-specific. Check **Availability** before using one:

- **public** images can be launched by any AWS account;
- **shared** images can be launched only by explicitly approved AWS accounts;
- **candidate** images remain private to the build account for smoke testing.

| AWS region | AMI ID | Availability | Source build | Recorded at (UTC) |
| --- | --- | --- | --- | --- |
| `us-east-1` | `ami-0bba53439d5325433` | candidate | [`972474d5094b`](https://github.com/kanga-route/kanga-route/actions/runs/31763152894) | `2026-08-14T02:24:57Z` |

The `Build and Deploy Kanga-Route AMI` workflow generates this table from
[`ami-catalog.json`](ami-catalog.json). Do not edit either catalog file by hand.
The workflow builds one private candidate, reports its exact ID for staging,
then promotes that same image only after the `ami-publication` environment is
approved. It never rebuilds between testing and publication.

Use a **public** entry directly in the
[AWS appliance deployment guide](aws-appliance-deployment.md). To use a
**shared** entry, first confirm that its owner granted your AWS account launch
permission. A **candidate** entry is not an end-user release.
