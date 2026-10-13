# 1. Crear el OIDC provider (solo una vez por cuenta)
aws iam create-open-id-connect-provider \
  --url https://token.actions.githubusercontent.com \
  --client-id-list sts.amazonaws.com \
  --thumbprint-list 6938fd4d98bab03faadb97b34396831e3780aea1

# 2. Crear el rol con trust policy que valida los claims de GitHub
aws iam create-role \
  --role-name github-actions-ci-token \
  --assume-role-policy-document '{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {
                "Federated": "arn:aws:iam::065700406944:oidc-provider/token.actions.githubusercontent.com"
            },
            "Action": "sts:AssumeRoleWithWebIdentity",
            "Condition": {
                "StringEquals": {
                    "token.actions.githubusercontent.com:aud": "sts.amazonaws.com"
                },
                "StringLike": {
                    "token.actions.githubusercontent.com:sub": "repo:mapfre-tech/*",
                    "token.actions.githubusercontent.com:job_workflow_ref": [
                        "mapfre-tech/action-ci-token/.github/workflows/get-token.yml@refs/tags/v*",
                        "mapfre-tech/action-ci-token/.github/workflows/self-test.yml@refs/pull/*/merge"
                    ]
                }
            }
        }
    ]
}'

# 3. Crear la política de permisos para Secrets Manager (solo lectura)
aws iam put-role-policy \
  --role-name github-actions-ci-token \
  --policy-name SecretsAndSSMReadOnly \
  --policy-document '{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "secretsmanager:GetSecretValue",
        "secretsmanager:DescribeSecret"
      ],
      "Resource": [
        "arn:aws:secretsmanager:eu-west-1:065700406944:secret:github-actions-ci-token/ci*private-key-*"
      ]
    },   
    {
      "Effect": "Allow",
      "Action": [
        "kms:Decrypt",
        "kms:DescribeKey"
      ],
      "Resource": "arn:aws:kms:eu-west-1:065700406944:key/f4e257da-24d1-44dd-8bd7-aaae3292cde1",
      "Condition": {
        "StringEquals": {
          "kms:ViaService": "secretsmanager.eu-west-1.amazonaws.com"
        }
      }
    }
  ]
}'

