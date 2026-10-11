resource "aws_vpc" "mwaa" {
  cidr_block           = var.vpc_cidr
  enable_dns_hostnames = true
  enable_dns_support   = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-vpc-${var.environment}"
  })
}

resource "aws_internet_gateway" "mwaa" {
  vpc_id = aws_vpc.mwaa.id

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-igw-${var.environment}"
  })
}

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-nat-eip-${var.environment}"
  })
}

resource "aws_nat_gateway" "mwaa" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public[0].id

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-nat-${var.environment}"
  })

  depends_on = [aws_internet_gateway.mwaa]
}

resource "aws_subnet" "private" {
  count                   = length(var.private_subnet_cidrs)
  vpc_id                  = aws_vpc.mwaa.id
  cidr_block              = var.private_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = false

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-private-${var.availability_zones[count.index]}-${var.environment}"
    Type = "private"
  })
}

resource "aws_subnet" "public" {
  count                   = length(var.public_subnet_cidrs)
  vpc_id                  = aws_vpc.mwaa.id
  cidr_block              = var.public_subnet_cidrs[count.index]
  availability_zone       = var.availability_zones[count.index]
  map_public_ip_on_launch = true

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-public-${var.availability_zones[count.index]}-${var.environment}"
    Type = "public"
  })
}

resource "aws_route_table" "private" {
  count  = length(var.private_subnet_cidrs)
  vpc_id = aws_vpc.mwaa.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.mwaa.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-private-rt-${var.availability_zones[count.index]}-${var.environment}"
  })
}

resource "aws_route_table_association" "private" {
  count          = length(var.private_subnet_cidrs)
  subnet_id      = aws_subnet.private[count.index].id
  route_table_id = aws_route_table.private[count.index].id
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.mwaa.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.mwaa.id
  }

  tags = merge(var.tags, {
    Name = "${var.project_name}-mwaa-public-rt-${var.environment}"
  })
}

resource "aws_route_table_association" "public" {
  count          = length(var.public_subnet_cidrs)
  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}