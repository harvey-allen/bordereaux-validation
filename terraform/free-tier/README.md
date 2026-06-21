# Free-tier smoke deployment (EC2 only)

This Terraform profile creates a low-cost, free-tier-friendly public smoke environment for testing your ability to go live.

## What it creates

- 1 EC2 instance (default: `t3.micro`)
- Security group for HTTP (80), HTTPS (443), and SSH (22)
- Optional user-data bootstrap to install Docker and run a public smoke container (`nginx`)

## What it intentionally does not create

- No NAT Gateway
- No ALB
- No ECS/Fargate
- No RDS
- No CloudFront

## Usage

1. Copy variables file:
   - `cp terraform.tfvars.example terraform.tfvars`
2. Edit values in `terraform.tfvars` (especially `ssh_allowed_cidr` and `key_name`).
3. Run:
   - `terraform init`
   - `terraform validate`
   - `terraform plan`
   - `terraform apply`

## Outputs

After apply, use:

- `terraform output public_dns`
- `terraform output smoke_url`
- `terraform output ssh_command`

## Cleanup

- `terraform destroy`

## Notes

- This is for smoke testing only, not production reliability.
- For stronger security, set `ssh_allowed_cidr` to your public IP/CIDR instead of `0.0.0.0/0`.
