# The network.
#
# One public subnet per availability zone and no NAT gateway. That is a
# deliberate cost decision worth naming: a NAT gateway is about 32 USD a month
# before a byte moves through it, which would be more than the rest of this
# stack combined. The instance sits in a public subnet with a public IP and is
# protected by its security group rather than by being unroutable.
#
# The database is the thing that must never be reachable from outside, and it
# is not: it lives in its own subnets with no route to the internet gateway and
# a security group that accepts Postgres from exactly one source.

data "aws_availability_zones" "available" {
  state = "available"
}

resource "aws_vpc" "main" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true # RDS endpoints are names, not addresses

  tags = { Name = "profplan-${var.environment}" }
}

resource "aws_internet_gateway" "main" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "profplan-${var.environment}" }
}

# --- public: the application host -----------------------------------------
resource "aws_subnet" "public" {
  count = 2

  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.0.${count.index}.0/24"
  availability_zone       = data.aws_availability_zones.available.names[count.index]
  map_public_ip_on_launch = true

  tags = { Name = "profplan-${var.environment}-public-${count.index}" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.main.id
  }

  tags = { Name = "profplan-${var.environment}-public" }
}

resource "aws_route_table_association" "public" {
  count = length(aws_subnet.public)

  subnet_id      = aws_subnet.public[count.index].id
  route_table_id = aws_route_table.public.id
}

# --- private: the database ------------------------------------------------
# Two subnets because RDS demands a subnet group spanning two zones, even for
# a single-AZ instance. It is what makes restoring into the other zone
# possible later without rebuilding the network.
resource "aws_subnet" "private" {
  count = 2

  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.${count.index + 10}.0/24"
  availability_zone = data.aws_availability_zones.available.names[count.index]

  tags = { Name = "profplan-${var.environment}-private-${count.index}" }
}

# No route table of its own: the subnets fall back to the VPC's main table,
# which has no internet gateway route. That is the isolation.

resource "aws_db_subnet_group" "main" {
  name       = "profplan-${var.environment}"
  subnet_ids = aws_subnet.private[*].id
}

# --- who may talk to whom -------------------------------------------------
resource "aws_security_group" "app" {
  name        = "profplan-${var.environment}-app"
  description = "Application host"
  vpc_id      = aws_vpc.main.id

  ingress {
    description = "HTTP, redirected to HTTPS by Traefik"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  # Empty by default, so this block creates nothing. Reaching the host is done
  # with SSM Session Manager, which needs no open port and leaves an audit
  # trail that an SSH key does not.
  dynamic "ingress" {
    for_each = length(var.allowed_ssh_cidr) > 0 ? [1] : []
    content {
      description = "SSH, from the named networks only"
      from_port   = 22
      to_port     = 22
      protocol    = "tcp"
      cidr_blocks = var.allowed_ssh_cidr
    }
  }

  egress {
    description = "Anywhere: the app calls three LLM providers and pulls images"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "profplan-${var.environment}-app" }
}

resource "aws_security_group" "database" {
  name        = "profplan-${var.environment}-db"
  description = "PostgreSQL, reachable from the application host and nothing else"
  vpc_id      = aws_vpc.main.id

  ingress {
    description     = "Postgres from the app"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [aws_security_group.app.id]
  }

  # No egress. The database has nowhere it needs to go, and saying so is
  # cheaper than discovering later that it could.

  tags = { Name = "profplan-${var.environment}-db" }
}
