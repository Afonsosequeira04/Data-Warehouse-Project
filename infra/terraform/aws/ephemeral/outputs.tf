output "vpc_id" {
  description = "ID of the MWAA VPC"
  value       = aws_vpc.mwaa.id
}

output "vpc_cidr" {
  description = "CIDR block of the MWAA VPC"
  value       = aws_vpc.mwaa.cidr_block
}

output "private_subnet_ids" {
  description = "IDs of the private subnets"
  value       = aws_subnet.private[*].id
}

output "public_subnet_ids" {
  description = "IDs of the public subnets"
  value       = aws_subnet.public[*].id
}

output "nat_gateway_id" {
  description = "ID of the NAT Gateway"
  value       = aws_nat_gateway.mwaa.id
}

output "mwaa_environment_name" {
  description = "Name of the MWAA environment"
  value       = aws_mwaa_environment.main.name
}

output "mwaa_environment_arn" {
  description = "ARN of the MWAA environment"
  value       = aws_mwaa_environment.main.arn
}

output "mwaa_webserver_url" {
  description = "Webserver URL for the MWAA environment"
  value       = aws_mwaa_environment.main.webserver_url
}

output "mwaa_security_group_id" {
  description = "ID of the MWAA security group"
  value       = aws_security_group.mwaa.id
}