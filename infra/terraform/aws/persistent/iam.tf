resource "aws_iam_role" "mwaa_execution" {
  name = "${var.project_name}-mwaa-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = [
          "airflow.amazonaws.com",
          "airflow-env.amazonaws.com"
        ]
      }
    }]
  })

  tags = var.tags
}

resource "aws_iam_policy" "mwaa_execution" {
  name        = "${var.project_name}-mwaa-execution-${var.environment}"
  description = "MWAA execution role policy for persistent stack resources"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "S3RawBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.raw.arn,
          "${aws_s3_bucket.raw.arn}/*"
        ]
      },
      {
        # MWAA validates the DAG bucket at environment creation (versioning,
        # public access block, location), so it needs bucket-level read access.
        Sid    = "S3DagBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject*",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:GetBucket*",
          "s3:List*"
        ]
        Resource = [
          aws_s3_bucket.dag.arn,
          "${aws_s3_bucket.dag.arn}/*"
        ]
      },
      {
        Sid    = "S3AccountPublicAccessBlock"
        Effect = "Allow"
        Action = [
          "s3:GetAccountPublicAccessBlock"
        ]
        Resource = "*"
      },
      {
        Sid    = "SecretsManagerAccess"
        Effect = "Allow"
        Action = [
          "secretsmanager:GetSecretValue",
          "secretsmanager:DescribeSecret"
        ]
        Resource = [
          aws_secretsmanager_secret.world_bank.arn,
          aws_secretsmanager_secret.fred.arn,
          aws_secretsmanager_secret.macro_watchlist_db.arn,
          aws_secretsmanager_secret.databricks.arn
        ]
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:CreateLogGroup",
          "logs:GetLogEvents",
          "logs:GetLogRecord",
          "logs:GetLogGroupFields",
          "logs:GetQueryResults",
          "logs:DescribeLogStreams"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:airflow-${var.project_name}-${var.environment}-*"
      },
      {
        # DescribeLogGroups does not work when restricted to a log group ARN pattern.
        Sid    = "CloudWatchLogsDescribeGroups"
        Effect = "Allow"
        Action = [
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudWatchMetrics"
        Effect = "Allow"
        Action = [
          "cloudwatch:PutMetricData"
        ]
        Resource = "*"
      },
      {
        Sid    = "AirflowPublishMetrics"
        Effect = "Allow"
        Action = [
          "airflow:PublishMetrics"
        ]
        Resource = "*"
      },
      {
        Sid    = "SQSAccess"
        Effect = "Allow"
        Action = [
          "sqs:ChangeMessageVisibility",
          "sqs:DeleteMessage",
          "sqs:GetQueueAttributes",
          "sqs:GetQueueUrl",
          "sqs:ReceiveMessage",
          "sqs:SendMessage"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:sqs:${var.aws_region}:*:airflow-celery-*"
      },
      {
        # MWAA uses an AWS-owned key for its SQS queues; workers need KMS via SQS only.
        Sid    = "KmsViaSqsForAwsOwnedKey"
        Effect = "Allow"
        Action = [
          "kms:Decrypt",
          "kms:DescribeKey",
          "kms:GenerateDataKey*",
          "kms:Encrypt"
        ]
        NotResource = "arn:${data.aws_partition.current.partition}:kms:*:${data.aws_caller_identity.current.account_id}:key/*"
        Condition = {
          StringLike = {
            "kms:ViaService" = ["sqs.${var.aws_region}.amazonaws.com"]
          }
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "mwaa_execution" {
  role       = aws_iam_role.mwaa_execution.name
  policy_arn = aws_iam_policy.mwaa_execution.arn
}