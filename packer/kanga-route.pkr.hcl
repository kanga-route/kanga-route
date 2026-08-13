packer {
  required_plugins {
    amazon = {
      version = ">= 1.2.0"
      source  = "github.com/hashicorp/amazon"
    }
  }
}

variable "aws_region" {
  type    = string
  default = "us-east-1"
}

variable "ami_prefix" {
  type    = string
  default = "kanga-route-appliance"
}

variable "vpc_id" {
  type    = string
  default = ""
}

variable "subnet_id" {
  type    = string
  default = ""
}


source "amazon-ebs" "ubuntu" {
  ami_name                    = "${var.ami_prefix}-v${formatdate("YYYYMMDDhhmm", timestamp())}"
  instance_type               = "t3.micro"
  region                      = var.aws_region
  vpc_id                      = var.vpc_id != "" ? var.vpc_id : null
  subnet_id                   = var.subnet_id != "" ? var.subnet_id : null
  associate_public_ip_address = true
  imds_support                = "v2.0"

  temporary_security_group_source_public_ip = true

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  source_ami_filter {
    filters = {
      name                = "ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"
      root-device-type    = "ebs"
      virtualization-type = "hvm"
    }
    most_recent = true
    owners      = ["099720109477"] # Canonical
  }

  ssh_username = "ubuntu"

  tags = {
    Name        = "Kanga-Route-Appliance"
    Application = "Kanga-Route"
    Version     = "0.1.0"
    Description = "Containerized Virtual Appliance for HubSpot email verification"
    ManagedBy   = "Packer"
  }
}

build {
  name = "kanga-route-bakery"
  sources = [
    "source.amazon-ebs.ubuntu"
  ]

  provisioner "shell" {
    inline = [
      "mkdir -p /tmp/kanga-route/bin /tmp/kanga-route/systemd /tmp/kanga-route/src/kanga_route/cache /tmp/kanga-route/src/kanga_route/crm /tmp/kanga-route/src/kanga_route/engine"
    ]
  }

  provisioner "file" {
    sources = [
      ".dockerignore",
      ".env.example",
      "Dockerfile",
      "README.md",
      "docker-compose.yml",
      "pyproject.toml",
      "requirements.txt",
    ]
    destination = "/tmp/kanga-route/"
  }

  provisioner "file" {
    sources = [
      "bin/kanga-route",
    ]
    destination = "/tmp/kanga-route/bin/"
  }

  provisioner "file" {
    sources = [
      "systemd/kanga-route.service",
      "systemd/kanga-route-run.service",
      "systemd/kanga-route-run.timer",
    ]
    destination = "/tmp/kanga-route/systemd/"
  }

  provisioner "file" {
    sources = [
      "src/kanga_route/__init__.py",
      "src/kanga_route/contracts.py",
      "src/kanga_route/main.py",
      "src/kanga_route/models.py",
    ]
    destination = "/tmp/kanga-route/src/kanga_route/"
  }

  provisioner "file" {
    sources = [
      "src/kanga_route/cache/__init__.py",
      "src/kanga_route/cache/dynamodb.py",
    ]
    destination = "/tmp/kanga-route/src/kanga_route/cache/"
  }

  provisioner "file" {
    sources = [
      "src/kanga_route/crm/__init__.py",
      "src/kanga_route/crm/hubspot.py",
    ]
    destination = "/tmp/kanga-route/src/kanga_route/crm/"
  }

  provisioner "file" {
    sources = [
      "src/kanga_route/engine/__init__.py",
      "src/kanga_route/engine/verifier.py",
    ]
    destination = "/tmp/kanga-route/src/kanga_route/engine/"
  }

  provisioner "shell" {
    script = "packer/scripts/provision.sh"
  }

  post-processor "manifest" {
    output     = "packer-manifest.json"
    strip_path = true
  }
}
