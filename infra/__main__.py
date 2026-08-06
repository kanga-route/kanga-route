"""Pulumi IaC script provisioning Kanga-Route virtual appliance on AWS EC2."""

import json
import pulumi
import pulumi_aws as aws

config = pulumi.Config()
instance_type = config.get("instanceType") or "t3.micro"
ami_id = config.get("amiId")

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

# 2. Security Group (Outbound Port 25, 53, 443, 80)
security_group = aws.ec2.SecurityGroup(
    "kanga-route-sg",
    vpc_id=vpc.id,
    description="Security group for Kanga-Route verification appliance",
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(
            description="SSH access",
            from_port=22,
            to_port=22,
            protocol="tcp",
            cidr_blocks=["0.0.0.0/0"],
        )
    ],
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
            description="Outbound HTTPS for HubSpot API & AWS services",
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
    policy=json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": [
                        "dynamodb:GetItem",
                        "dynamodb:PutItem",
                        "dynamodb:CreateTable",
                        "dynamodb:DescribeTable",
                    ],
                    "Resource": "*",
                }
            ],
        }
    ),
)

instance_profile = aws.iam.InstanceProfile(
    "kanga-route-instance-profile",
    role=role.name,
)

# 4. Lookup AMI if not supplied
if not ami_id:
    ubuntu_ami = aws.ec2.get_ami(
        most_recent=True,
        owners=["099720109477"],
        filters=[
            aws.ec2.GetAmiFilterArgs(
                name="name",
                values=["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"],
            )
        ],
    )
    ami_id = ubuntu_ami.id

# 5. EC2 Instance Provisioning
appliance_instance = aws.ec2.Instance(
    "kanga-route-appliance",
    instance_type=instance_type,
    ami=ami_id,
    subnet_id=subnet.id,
    vpc_security_group_ids=[security_group.id],
    iam_instance_profile=instance_profile.name,
    tags={"Name": "Kanga-Route-Appliance"},
)

# 6. Elastic IP (EIP) Allocation & Association
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
