resource "aws_iam_role" "mwaa_execution" {
  name = "${var.project_name}-mwaa-execution-${var.environment}"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "airflow.amazonaws.com"
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
        Sid    = "S3DagBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.dag.arn,
          "${aws_s3_bucket.dag.arn}/*"
        ]
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
          aws_secretsmanager_secret.fivetran_rds.arn
        ]
      },
      {
        Sid    = "CloudWatchLogsAccess"
        Effect = "Allow"
        Action = [
          "logs:CreateLogStream",
          "logs:PutLogEvents",
          "logs:CreateLogGroup"
        ]
        Resource = "arn:${data.aws_partition.current.partition}:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:log-group:airflow/${var.project_name}-${var.environment}*"
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "mwaa_execution" {
  role       = aws_iam_role.mwaa_execution.name
  policy_arn = aws_iam_policy.mwaa_execution.arn
}