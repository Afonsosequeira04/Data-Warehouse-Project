# Cada objeto e gerido por UM unico recurso databricks_grants.
# Papeis que partilham o mesmo principal sao fundidos (uniao dos privilegios).

locals {
  principals = {
    pipeline  = var.uc_principal_pipeline
    bi        = var.uc_principal_bi
    developer = var.uc_principal_developer
  }

  schema_ids = {
    bronze       = databricks_schema.bronze.id
    silver       = databricks_schema.silver.id
    gold         = databricks_schema.gold.id
    quarantine   = databricks_schema.quarantine.id
    snapshots    = databricks_schema.snapshots.id
    raw_fivetran = databricks_schema.raw_fivetran.id
  }

  catalog_roles = {
    pipeline  = ["USE_CATALOG", "CREATE_SCHEMA"]
    bi        = ["USE_CATALOG"]
    developer = ["USE_CATALOG"]
  }

  # BI so ve o gold; developer le tudo; pipeline escreve
  schema_roles = {
    bronze = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
    silver = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
    gold = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      bi        = ["USE_SCHEMA", "SELECT"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
    quarantine = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
    snapshots = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
    raw_fivetran = {
      pipeline  = ["USE_SCHEMA", "CREATE_TABLE", "SELECT", "MODIFY"]
      developer = ["USE_SCHEMA", "SELECT"]
    }
  }

  raw_location_roles = {
    pipeline  = ["READ_FILES"]
    developer = ["READ_FILES"]
  }

  dag_location_roles = {
    pipeline = ["READ_FILES", "WRITE_FILES"]
  }

  uc_managed_location_roles = {
    pipeline = ["READ_FILES", "WRITE_FILES", "CREATE_EXTERNAL_TABLE"]
  }

  catalog_grants = {
    for p in distinct([for r in keys(local.catalog_roles) : local.principals[r]]) :
    p => distinct(flatten([for r, privs in local.catalog_roles : privs if local.principals[r] == p]))
  }

  schema_grants = {
    for s, roles in local.schema_roles : s => {
      for p in distinct([for r in keys(roles) : local.principals[r]]) :
      p => distinct(flatten([for r, privs in roles : privs if local.principals[r] == p]))
    }
  }

  raw_location_grants = {
    for p in distinct([for r in keys(local.raw_location_roles) : local.principals[r]]) :
    p => distinct(flatten([for r, privs in local.raw_location_roles : privs if local.principals[r] == p]))
  }

  dag_location_grants = {
    for p in distinct([for r in keys(local.dag_location_roles) : local.principals[r]]) :
    p => distinct(flatten([for r, privs in local.dag_location_roles : privs if local.principals[r] == p]))
  }

  uc_managed_location_grants = {
    for p in distinct([for r in keys(local.uc_managed_location_roles) : local.principals[r]]) :
    p => distinct(flatten([for r, privs in local.uc_managed_location_roles : privs if local.principals[r] == p]))
  }
}

resource "databricks_grants" "catalog" {
  catalog = databricks_catalog.dwh_dev.name

  dynamic "grant" {
    for_each = local.catalog_grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

resource "databricks_grants" "schema" {
  for_each = local.schema_grants
  schema   = local.schema_ids[each.key]

  dynamic "grant" {
    for_each = each.value
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

resource "databricks_grants" "location_raw" {
  external_location = databricks_external_location.raw.name

  dynamic "grant" {
    for_each = local.raw_location_grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

resource "databricks_grants" "location_dag" {
  external_location = databricks_external_location.dag.name

  dynamic "grant" {
    for_each = local.dag_location_grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}

resource "databricks_grants" "location_uc_managed" {
  external_location = databricks_external_location.uc_managed.name

  dynamic "grant" {
    for_each = local.uc_managed_location_grants
    content {
      principal  = grant.key
      privileges = grant.value
    }
  }
}
