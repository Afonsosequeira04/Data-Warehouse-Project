resource "aws_budgets_budget" "main" {
  name         = var.budget_name
  budget_type  = "COST"
  limit_amount = var.budget_limit_amount
  limit_unit   = "USD"
  time_unit    = "MONTHLY"

  # Notifications are managed manually on the existing budget; not managed by Terraform.
  # Import command: terraform import aws_budgets_budget.main <account_id>:<budget_name>
}