# Deployment Scripts

Production-ready AWS Lambda deployment automation for CANedge MDF to Parquet conversion.

## Structure

```
deployment/
├── cloudformation/
│   └── aws-lambda-automation.json    # CloudFormation template
└── README.md
```

## Prerequisites

### 1. AWS OIDC Configuration

Configure GitHub Actions OIDC provider in AWS IAM:

```bash
# Create OIDC Identity Provider (one-time setup)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1
```

### 2. Create IAM Role for GitHub Actions

Create a role with trust policy for your GitHub repository:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {
        "Federated": "arn:aws:iam::YOUR-ACCOUNT-ID:oidc-provider/token.actions.githubusercontent.com"
      },
      "Action": "sts:AssumeRoleWithWebIdentity",
      "Condition": {
        "StringEquals": {
          "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
        },
        "StringLike": {
          "token.actions.githubusercontent.com:sub": "repo:YOUR-GITHUB-USERNAME/canedge-mdftoparquet-automation:*"
        }
      }
    }
  ]
}
```

Attach policies for CloudFormation, S3, Lambda, and IAM.

## GitHub Secrets Configuration

Configure these secrets in your GitHub repository (Settings → Secrets and variables → Actions):

| Secret | Description | Example |
|--------|-------------|---------|
| `AWS_DEPLOY_ROLE_ARN` | IAM Role ARN for OIDC authentication | `arn:aws:iam::123456789012:role/GitHubActionsDeployRole` |
| `LAMBDA_CODE_BUCKET` | S3 bucket for Lambda deployment package | `my-lambda-deployments` |
| `INPUT_BUCKET` | S3 bucket containing MDF files | `canedge-raw-data` |
| `OUTPUT_BUCKET` | S3 bucket for Parquet output | `canedge-processed-data` |

## Workflow Configuration

> Test note: this file was updated to trigger a new GitHub Actions run after pushing the branch.

Edit `.github/workflows/lambda-automation.yml` to configure:

```yaml
env:
  AWS_REGION: eu-central-1              # Your AWS region
  STACK_NAME: canedge-mdf-to-parquet    # CloudFormation stack name
```

## Deployment

### Automated (GitHub Actions)

The workflow runs automatically on push to configured branches, or trigger manually:

1. Go to **Actions** → **Lambda Build & Deploy**
2. Click **Run workflow**
3. Select branch and click **Run workflow**

**Workflow Steps:**
1. **Build Job** - Creates Lambda deployment package (always runs)
2. **Deploy Job** - Deploys to AWS (only on manual trigger via `workflow_dispatch`)

### Manual Validation (Local)

Test the build locally with `act`:

```powershell
# Install act (one-time)
winget install nektos.act

# Run build job locally
act workflow_dispatch -j build
```

## CloudFormation Stack Details

The stack creates:
- **Lambda Function** (`canedge-mdf-to-parquet`)
  - Runtime: Python 3.12
  - Memory: 2048 MB
  - Timeout: 900s (15 min)
  - Ephemeral Storage: 2048 MB
- **IAM Role** with S3 read/write permissions
- **Lambda Permissions** for S3 event triggers

## Post-Deployment: Configure S3 Event Trigger

After deployment, configure S3 to trigger Lambda on new MDF uploads:

1. Go to S3 → Your input bucket → Properties → Event notifications
2. Create event notification:
   - **Event name**: `TriggerMDFConversion`
   - **Event types**: `PUT` (All object create events)
   - **Prefix**: (optional, e.g., `00000000/`)
   - **Suffix**: `.MF4`
   - **Destination**: Lambda function → `canedge-mdf-to-parquet`

## Troubleshooting

### Check Lambda Function

```bash
# View function configuration
aws lambda get-function --function-name canedge-mdf-to-parquet

# Check recent executions
aws logs tail /aws/lambda/canedge-mdf-to-parquet --follow
```

### Validate CloudFormation Template

```bash
aws cloudformation validate-template \
  --template-body file://deployment/cloudformation/aws-lambda-automation.json
```

### Delete Stack

```bash
aws cloudformation delete-stack --stack-name canedge-mdf-to-parquet
```
