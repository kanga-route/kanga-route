"""Pulumi IaC script provisioning the Kanga-Route AWS appliance."""

import json

import pulumi
import pulumi_aws as aws

from config import (
    build_dynamodb_policy_document,
    build_dynamodb_table_arn,
    validate_ami_id,
    validate_dynamodb_table_name,
    validate_ssh_cidr,
)


config = pulumi.Config()
instance_type = config.get("instanceType") or "t3.micro"
ami_id = validate_ami_id(config.require("amiId"))
ssh_cidr = validate_ssh_cidr(config.get("sshCidr"))
dynamodb_table_name = validate_dynamodb_table_name(
    config.get("dynamodbTableName") or "KangaRouteCache"
)

aws_partition = aws.get_partition().partition
aws_region = aws.get_region().name
aws_account_id = aws.get_caller_identity().account_id
dynamodb_table_arn = build_dynamodb_table_arn(
    partition=aws_partition,
    region=aws_region,
    account_id=aws_account_id,
    table_name=dynamodb_table_name,
)

# 1. Create VPC & Networking Subsystem
vpc = aws.ec2.Vpc(
    "kanga-route-vpc",
    cidr_block="10.0.0.0/16",
    enable_dns_hostnames=True,
    enable_dns_support=True,
    tags={"Name": "kanga-route-vpc"},
)

igw = aws.ec2.InternetGateway(
    "kanga-route-igw",
    vpc_id=vpc.id,
    tags={"Name": "kanga-route-igw"},
)

subnet = aws.ec2.Subnet(
    "kanga-route-subnet",
    vpc_id=vpc.id,
    cidr_block="10.0.1.0/24",
    map_public_ip_on_launch=True,
    tags={"Name": "kanga-route-public-subnet"},
)

route_table = aws.ec2.RouteTable(
    "kanga-route-rt",
    vpc_id=vpc.id,
    routes=[
        aws.ec2.RouteTableRouteArgs(
            cidr_block="0.0.0.0/0",
            gateway_id=igw.id,
        )
    ],
    tags={"Name": "kanga-route-rt"},
)

aws.ec2.RouteTableAssociation(
    "kanga-route-rta",
    subnet_id=subnet.id,
    route_table_id=route_table.id,
)

# 2. Security Group (no ingress by default; optional restricted SSH)
ssh_ingress = []
if ssh_cidr:
    ssh_ingress.append(
        aws.ec2.SecurityGroupIngressArgs(
            description="Restricted SSH access",
            from_port=22,
            to_port=22,
            protocol="tcp",
            cidr_blocks=[ssh_cidr],
        )
    )

security_group = aws.ec2.SecurityGroup(
    "kanga-route-sg",
    vpc_id=vpc.id,
    description="Security group for Kanga-Route verification appliance",
    ingress=ssh_ingress,
    egress=[
        aws.ec2.SecurityGroupEgressArgs(
            description="Outbound SMTP for email verification",
            from_port=25,
            to_port=25,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupEgressArgs(
            description="Outbound DNS (UDP)",
            from_port=53,
            to_port=53,
            protocol="udp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupEgressArgs(
            description="Outbound DNS (TCP)",
            from_port=53,
            to_port=53,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupEgressArgs(
            description="Outbound HTTPS for adapter APIs and AWS services",
            from_port=443,
            to_port=443,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
        aws.ec2.SecurityGroupEgressArgs(
            description="Outbound HTTP",
            from_port=80,
            to_port=80,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        ),
    ],
    tags={"Name": "kanga-route-sg"},
)

# 3. IAM Role & Instance Profile for DynamoDB Cloud Caching
role = aws.iam.Role(
    "kanga-route-iam-role",
    assume_role_policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Action": "sts:AssumeRole",
                    "Effect": "Allow",
                    "Principal": {"Service": "ec2.amazonaws.com"},
                }
            ],
        }
    ),
)

policy = aws.iam.RolePolicy(
    "kanga-route-dynamodb-policy",
    role=role.id,
    policy=json.dumps(build_dynamodb_policy_document(dynamodb_table_arn)),
)

aws.iam.RolePolicyAttachment(
    "kanga-route-ssm-policy-attachment",
    role=role.name,
    policy_arn="arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore",
)

instance_profile = aws.iam.InstanceProfile(
    "kanga-route-instance-profile",
    role=role.name,
)

# 4. EC2 Instance Provisioning
appliance_instance = aws.ec2.Instance(
    "kanga-route-appliance",
    instance_type=instance_type,
    ami=ami_id,
    subnet_id=subnet.id,
    vpc_security_group_ids=[security_group.id],
    iam_instance_profile=instance_profile.name,
    metadata_options=aws.ec2.InstanceMetadataOptionsArgs(
        http_endpoint="enabled",
        http_put_response_hop_limit=2,
        http_tokens="required",
    ),
    root_block_device=aws.ec2.InstanceRootBlockDeviceArgs(
        delete_on_termination=True,
        encrypted=True,
        volume_type="gp3",
    ),
    tags={
        "Name": "Kanga-Route-Appliance",
        "Application": "Kanga-Route",
    },
)

# 5. Elastic IP (EIP) Allocation & Association
eip = aws.ec2.Eip(
    "kanga-route-eip",
    instance=appliance_instance.id,
    domain="vpc",
    tags={"Name": "kanga-route-eip"},
)

# Export Stack Outputs
pulumi.export("public_ip", eip.public_ip)
pulumi.export("instance_id", appliance_instance.id)
pulumi.export("vpc_id", vpc.id)
pulumi.export("dynamodb_table_name", dynamodb_table_name)
