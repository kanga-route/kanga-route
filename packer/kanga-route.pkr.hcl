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

variable "aws_access_key" {
  type      = string
  default   = ""
  sensitive = true
}

variable "aws_secret_key" {
  type      = string
  default   = ""
  sensitive = true
}

source "amazon-ebs" "ubuntu" {
  ami_name                    = "${var.ami_prefix}-v${formatdate("YYYYMMDDhhmm", timestamp())}"
  instance_type               = "t3.micro"
  region                      = var.aws_region
  access_key                  = var.aws_access_key != "" ? var.aws_access_key : null
  secret_key                  = var.aws_secret_key != "" ? var.aws_secret_key : null
  vpc_id                      = var.vpc_id != "" ? var.vpc_id : null
  subnet_id                   = var.subnet_id != "" ? var.subnet_id : null
  associate_public_ip_address = true

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
  ami_groups   = ["all"]

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
      "mkdir -p /tmp/kanga-route"
    ]
  }

  provisioner "file" {
    source      = "./"
    destination = "/tmp/kanga-route"
  }

  provisioner "shell" {
    script = "packer/scripts/provision.sh"
  }

  post-processor "manifest" {
    output     = "packer-manifest.json"
    strip_path = true
  }
}
