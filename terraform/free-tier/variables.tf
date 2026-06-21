variable "aws_region" {
  description = "AWS region for the free-tier smoke deployment"
  type        = string
  default     = "eu-west-2"
}

variable "project_name" {
  description = "Project name for resource tags"
  type        = string
  default     = "bordereaux"
}

variable "environment" {
  description = "Environment label"
  type        = string
  default     = "free-tier"
}

variable "instance_type" {
  description = "EC2 instance type (free-tier friendly)"
  type        = string
  default     = "t3.micro"
}

variable "root_volume_size" {
  description = "Root EBS volume size in GiB"
  type        = number
  default     = 20
}

variable "ssh_allowed_cidr" {
  description = "CIDR allowed to SSH to the instance"
  type        = string
  default     = "0.0.0.0/0"
}

variable "key_name" {
  description = "Existing EC2 key pair name for SSH (optional)"
  type        = string
  default     = ""
}

variable "deploy_smoke_container" {
  description = "If true, installs Docker and runs a simple public smoke container"
  type        = bool
  default     = true
}
