# Build and publish Kanga-Route AMIs

The `Build and Deploy Kanga-Route AMI` GitHub Actions workflow is the only
supported release entry point. Run it from `master`. It calls two reusable
workflows in order:

1. `Packer Appliance Bakery` builds one private AMI candidate and returns its
   exact AMI ID.
2. `Publish AMI` verifies that exact image and either leaves it private, shares
   it with approved AWS accounts, or makes it public. It never rebuilds the
   candidate.

Afterward, the parent workflow updates the
[AMI catalog](ami-catalog.md) and its machine-readable JSON source. The AMI ID
also appears in the workflow's GitHub Actions summary.

## Safety model

Every build begins as a private candidate. Select one of these modes when
starting the parent workflow:

| Mode | Result | Approval gate |
| --- | --- | --- |
| `candidate` | AMI stays private to the build account | None |
| `shared` | Exact AMI is launchable by AWS accounts stored in a GitHub secret | `ami-publication` environment |
| `public` | Exact AMI is launchable by every AWS account in that region | `ami-publication` environment plus the public confirmation checkbox |

Shared AWS account IDs are held in an Actions secret, not a workflow input, so
they are not displayed in a public run's input list. The catalog records the
availability mode but never records account IDs, role ARNs, or AWS account IDs.

## One-time GitHub configuration

Open **Repository → Settings → Actions → General**.

1. Under **Workflow permissions**, select **Read and write permissions**. The
   parent needs `contents: write` only to commit the generated catalog after a
   successful run.
2. Under **Variables**, retain `AWS_AMI_BUILDER_ROLE_ARN` with the ARN of the
   existing OIDC Packer role.
3. Optionally create `AWS_AMI_PUBLISHER_ROLE_ARN` with a separate role ARN. If
   omitted, the workflow reuses the builder role, which must then include the
   publication permissions below.
4. For shared releases, create the Actions secret
   `AWS_AMI_SHARE_ACCOUNT_IDS`. Its value can contain comma-separated or
   whitespace-separated 12-digit AWS account IDs. Do not add this value as a
   repository variable.

Then open **Settings → Environments**, create `ami-publication`, and add at
least one required reviewer. Restrict deployment branches to `master`. This
gate is the handoff between building and publishing: the reviewer can inspect
the candidate AMI ID, boot it, and smoke-test it before approving promotion.

If `master` is protected, allow `github-actions[bot]` or GitHub Actions to push
the two generated catalog files. Otherwise the AMI operation can succeed while
the final catalog commit is rejected by the branch rule.

## AWS OIDC trust

The builder and publisher roles must trust the repository's GitHub OIDC
identity for `master` and the `sts.amazonaws.com` audience. Keep using the
repository's current immutable GitHub OIDC subject when one is configured; do
not copy an account-specific subject or role ARN into this public repository.

The parent workflow refuses to run from any branch other than `master`. This
keeps the source ref aligned with a trust policy scoped to the master branch.
Both reusable workflows receive short-lived AWS credentials through OIDC; no
long-lived AWS access keys are used.

## Publisher permissions

The publisher role needs read access to inspect the candidate and permission to
modify and tag AMIs owned by the release account. Replace `<AWS_ACCOUNT_ID>`
before attaching this policy. If the builder role is also the publisher, add
these statements to its existing Packer policy rather than replacing the
builder permissions.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "InspectAmiPublicationState",
      "Effect": "Allow",
      "Action": [
        "ec2:DescribeImages",
        "ec2:DescribeImageAttribute",
        "ec2:DescribeSnapshots",
        "ec2:GetImageBlockPublicAccessState"
      ],
      "Resource": "*"
    },
    {
      "Sid": "PublishOwnedKangaRouteAmis",
      "Effect": "Allow",
      "Action": [
        "ec2:CreateTags",
        "ec2:ModifyImageAttribute"
      ],
      "Resource": "arn:aws:ec2:*:<AWS_ACCOUNT_ID>:image/*"
    }
  ]
}
```

The workflow deliberately cannot disable EC2 **Block Public Access for AMIs**.
For a public release, an AWS administrator must temporarily disable that
regional setting, approve the gated publication job, verify the image is
public, and then re-enable the block. AWS also rejects public AMIs backed by
encrypted snapshots; the workflow checks both conditions before changing
launch permissions.

## Run the release

1. Merge the exact source you intend to ship into `master`.
2. Open **Actions → Build and Deploy Kanga-Route AMI → Run workflow**.
3. Keep the branch set to `master` and choose the AWS region.
4. Choose `candidate`, `shared`, or `public`. For `public`, also select the
   explicit confirmation checkbox.
5. Start the workflow and wait for **Bake exact candidate** to finish.
6. Open the bakery job summary and copy the exact AMI ID.
7. For a shared or public run, launch and smoke-test that candidate before
   approving the `ami-publication` environment deployment.
8. Approve the publication job only if the exact candidate passed staging.
9. Confirm the final job updated the [AMI catalog](ami-catalog.md).

Do not rerun Packer between staging and promotion. If the candidate fails, do
not approve it. Fix the source and start a new parent workflow so the corrected
build receives a different AMI ID and a complete audit trail.

## Reusing the child workflows

Other workflows can call the children directly at the same commit:

```yaml
jobs:
  bakery:
    uses: ./.github/workflows/packer-build.yml
    with:
      aws_region: us-east-1
      aws_role_arn: ${{ vars.AWS_AMI_BUILDER_ROLE_ARN }}

  publish:
    needs: bakery
    uses: ./.github/workflows/publish-ami.yml
    with:
      ami_id: ${{ needs.bakery.outputs.ami_id }}
      aws_region: us-east-1
      aws_role_arn: ${{ vars.AWS_AMI_BUILDER_ROLE_ARN }}
      publication_mode: candidate
      source_sha: ${{ github.sha }}
```

The caller must grant `id-token: write`. A caller that updates repository files
must also grant `contents: write`; the reusable bakery and publisher themselves
request only read access to repository contents.
