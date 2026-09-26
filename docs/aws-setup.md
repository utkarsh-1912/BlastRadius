# AWS: Getting Credentials

Blast Radius never asks you to type credentials into the app itself — you configure them once, outside it, the normal boto3/AWS CLI way. This page covers exactly that.

## Do you need a real AWS account?

Not to develop or demo — see [`README.md`'s "No AWS account yet?"](../README.md#1-configure-environment) for the `moto_server` path, which gives you real boto3 calls and real IAM semantics against a fully local mock. You need a real account only for the actual hackathon submission (the rules require reaching a real system), or once you want to replay real CloudTrail history instead of the labeled demo export.

## Option A — access keys in `.env` (simplest)

1. **Get an AWS account** if you don't have one: [aws.amazon.com/free](https://aws.amazon.com/free). IAM and CloudTrail management events cost nothing on the free tier. If you're a shortlisted hackathon team, check for AWS credits too.
2. **Sign in with root only to create an IAM user**, then never use root again:
   - Console → **IAM** → **Users** → **Create user** → name it (e.g. `blast-radius-dev`).
   - On the **Set permissions** step: choose **"Attach policies directly"** (not "Add user to group" — that's an extra step you don't need here). Search for and check **`AdministratorAccess`** (simplest for a hackathon; see the scoped policy below if you'd rather not).
   - Skip the permissions boundary step. **Create user**.
3. **Create an access key**: open that user → **Security credentials** tab → **Create access key** → choose **Command Line Interface (CLI)** → confirm → **Create**. Copy the **Access Key ID** and **Secret Access Key** immediately — AWS shows the secret only once.
4. Put them in `.env`:
   ```env
   AWS_ACCESS_KEY_ID=<paste>
   AWS_SECRET_ACCESS_KEY=<paste>
   AWS_REGION=us-east-1
   # AWS_ENDPOINT_URL=   <- leave blank/commented; that's only for moto_server
   ```

**Never paste a real key into a chat window, an issue, or a commit** — treat any key that leaves your machine as compromised and rotate it immediately (IAM → the user → Security credentials → deactivate, then delete, the old key → create a new one).

## Option B — `aws configure`, keys never touch `.env` (better practice)

```bash
pip install awscli   # if not already installed
aws configure
```
Prompts for the same two values, writes them to `~/.aws/credentials` (readable only by your OS user) instead of a project file. `aws configure` with no flags creates a profile named `default`, which `boto3.Session()` picks up automatically — so leave `AWS_PROFILE` blank in `.env` unless you used `aws configure --profile <name>`.

## Scoped IAM policy (instead of `AdministratorAccess`)

Blast Radius only ever needs:

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "iam:ListRoles", "iam:GetRole", "iam:ListAttachedRolePolicies", "iam:ListRolePolicies",
      "iam:GetRolePolicy", "iam:GetPolicy", "iam:GetPolicyVersion", "iam:ListPolicyVersions",
      "iam:ListEntitiesForPolicy", "iam:PutRolePolicy", "iam:CreatePolicyVersion",
      "iam:DeletePolicyVersion", "iam:SimulateCustomPolicy",
      "iam:CreateRole", "iam:CreatePolicy", "iam:AttachRolePolicy",
      "cloudtrail:LookupEvents", "sts:GetCallerIdentity"
    ],
    "Resource": "*"
  }]
}
```
The `Create*`/`Attach*` actions are only needed for `scripts/seed_demo_iam.py`; drop them once the demo role already exists.

## After credentials are set

```bash
python scripts/seed_demo_iam.py
```
Then check the AWS Console (**IAM → Roles → `data-pipeline-role`**) to confirm it's really there — a review against a role that doesn't exist in the account you're pointed at will (correctly) report zero matches, not an error. If you've been developing against `moto_server` and then switch `.env` over to real credentials, the demo role needs to be seeded again — it's a separate account with separate state.
