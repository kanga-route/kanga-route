# 1. Use Virtual Appliance Model (AMI) over Serverless Containers

**Date:** 2026-08-05
**Status:** Accepted

**Context:**
To perform deep email verification, the engine must execute raw SMTP handshakes (TCP Port 25) directly with target Mail Exchange (MX) servers. Managed serverless container platforms (AWS Fargate, managed Kubernetes) permanently hard-block outbound Port 25 to prevent spam, making a container-native approach impossible without routing through a complex third-party proxy.

**Decision:**
We will package the Kanga-Route engine as a standalone Virtual Appliance using a standard Linux Machine Image (AMI) deployed on an Amazon EC2 instance. 

**Consequences:**
* **Positive:** Bypasses serverless network restrictions. Port 25 can be officially unblocked by submitting an AWS support request for the specific Elastic IP attached to the EC2 instance.
* **Positive:** Easy to package and deploy using infrastructure-as-code (Pulumi).
* **Negative:** Requires maintaining a base operating system image via Packer rather than a simple Dockerfile.