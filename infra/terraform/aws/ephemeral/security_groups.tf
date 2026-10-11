# MWAA Security Group
# Reference: https://docs.aws.amazon.com/mwaa/latest/userguide/mwaa-networking.html#mwaa-security-groups
# MWAA requires:
# - Inbound: self-referencing on all ports (for worker-to-worker and scheduler-to-worker communication)
# - Outbound: all traffic allowed (for PyPI, AWS APIs, Databricks, etc.)

resource "aws_security_group" "mwaa" {
  name        = "${var.project_name}-mwaa-sg-${var.environment}"
  description = "Security group for MWAA environment"
  vpc_id      = aws_vpc.mwaa.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-sg-${var.environment}"
  })
}

# Self-referencing inbound rule - allows MWAA components to communicate with each other
resource "aws_security_group_rule" "mwaa_ingress_self" {
  type                     = "ingress"
  from_port                = 0
  to_port                  = 65535
  protocol                 = "-1"
  security_group_id        = aws_security_group.mwaa.id
  source_security_group_id = aws_security_group.mwaa.id
  description              = "Allow MWAA components to communicate with each other"
}

# Allow all outbound traffic for PyPI, AWS APIs, Databricks, etc.
resource "aws_security_group_rule" "mwaa_egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 65535
  protocol          = "-1"
  security_group_id = aws_security_group.mwaa.id
  cidr_blocks       = ["0.0.0.0/0"]
  description       = "Allow all outbound traffic for MWAA"
}