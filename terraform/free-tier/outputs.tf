output "instance_id" {
  description = "EC2 instance ID"
  value       = aws_instance.smoke.id
}

output "public_ip" {
  description = "Public IPv4 address"
  value       = aws_instance.smoke.public_ip
}

output "public_dns" {
  description = "Public DNS name"
  value       = aws_instance.smoke.public_dns
}

output "smoke_url" {
  description = "HTTP URL for quick smoke test"
  value       = "http://${aws_instance.smoke.public_dns}"
}

output "ssh_command" {
  description = "SSH command template"
  value       = var.key_name != "" ? "ssh -i <path-to-private-key> ubuntu@${aws_instance.smoke.public_dns}" : "No key_name provided. Use EC2 Instance Connect or SSM if configured."
}
