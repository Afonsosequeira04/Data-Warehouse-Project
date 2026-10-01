data "databricks_aws_unity_catalog_assume_role_policy" "storage_credential" {
  external_id    = var.storage_credential_external_id
  role_name      = "${var.project_name}-databricks-storage-${var.environment}-${var.name_suffix}"
  aws_account_id = data.aws_caller_identity.current.account_id
}

resource "aws_iam_role" "databricks_storage_credential" {
  name               = "${var.project_name}-databricks-storage-${var.environment}-${var.name_suffix}"
  assume_role_policy = data.databricks_aws_unity_catalog_assume_role_policy.storage_credential.json

  tags = var.tags
}

resource "aws_iam_policy" "databricks_storage_credential" {
  name        = "${var.project_name}-databricks-storage-${var.environment}-${var.name_suffix}"
  description = "Policy for Databricks storage credential to access raw, DAG, and UC managed buckets"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "RawBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.raw_bucket_arn,
          "${var.raw_bucket_arn}/*"
        ]
      },
      {
        Sid    = "DagBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.dag_bucket_arn,
          "${var.dag_bucket_arn}/*"
        ]
      },
      {
        Sid    = "UCManagedBucketAccess"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation"
        ]
        Resource = [
          var.uc_managed_bucket_arn,
          "${var.uc_managed_bucket_arn}/*"
        ]
      },
      {
        Sid      = "SelfAssumeRole"
        Effect   = "Allow"
        Action   = ["sts:AssumeRole"]
        Resource = [aws_iam_role.databricks_storage_credential.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "databricks_storage_credential" {
  role       = aws_iam_role.databricks_storage_credential.name
  policy_arn = aws_iam_policy.databricks_storage_credential.arn
}

resource "databricks_storage_credential" "s3" {
  name            = "${var.project_name}-${var.environment}-${var.name_suffix}-storage-credential"
  read_only       = false
  skip_validation = var.storage_credential_external_id == "0000"

  aws_iam_role {
    role_arn = aws_iam_role.databricks_storage_credential.arn
  }

  depends_on = [aws_iam_role.databricks_storage_credential, aws_iam_role_policy_attachment.databricks_storage_credential]
}

resource "databricks_external_location" "raw" {
  name            = "${var.project_name}-${var.environment}-${var.name_suffix}-raw-location"
  credential_name = databricks_storage_credential.s3.name
  url             = "s3://${var.raw_bucket_name}"
  read_only       = true
  skip_validation = var.storage_credential_external_id == "0000"
}

resource "databricks_external_location" "dag" {
  name            = "${var.project_name}-${var.environment}-${var.name_suffix}-dag-location"
  credential_name = databricks_storage_credential.s3.name
  url             = "s3://${var.dag_bucket_name}"
  read_only       = false
  skip_validation = var.storage_credential_external_id == "0000"
}

resource "databricks_external_location" "uc_managed" {
  name            = "${var.project_name}-${var.environment}-${var.name_suffix}-uc-managed"
  credential_name = databricks_storage_credential.s3.name
  url             = "s3://${var.uc_managed_bucket_name}"
  read_only       = false
  skip_validation = var.storage_credential_external_id == "0000"
}

resource "databricks_catalog" "dwh_dev" {
  name         = "dwh_dev"
  comment      = "Data warehouse catalog for development environment"
  storage_root = "s3://${var.uc_managed_bucket_name}/"
  depends_on   = [databricks_external_location.uc_managed]
}

resource "databricks_schema" "bronze" {
  name         = "bronze"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Bronze layer - raw data with technical metadata"
}

resource "databricks_schema" "silver" {
  name         = "silver"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Silver layer - cleaned and normalized data"
}

resource "databricks_schema" "gold" {
  name         = "gold"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Gold layer - analytical dimensions and facts"
}

resource "databricks_schema" "quarantine" {
  name         = "quarantine"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Quarantine layer - rejected records with diagnostic metadata"
}

resource "databricks_schema" "snapshots" {
  name         = "snapshots"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Snapshots layer - dbt SCD2 historical tracking"
}

resource "databricks_schema" "raw_fivetran" {
  name         = "raw_fivetran"
  catalog_name = databricks_catalog.dwh_dev.name
  comment      = "Fivetran managed landing area for operational database"
}

data "databricks_sql_warehouse" "existing" {
  id = var.sql_warehouse_id
}
