#!/usr/bin/env python3
"""
Kanga-Route AMI Retention & Pruning Script

Retention Policy:
1. Retains the 5 most recent AMI builds globally.
2. ALWAYS retains the latest build for each MAJOR version branch (e.g., latest v1.x.x, latest v2.x.x).
3. Deregisters older patch AMIs and deletes their backing EBS snapshots to minimize AWS storage costs.
"""

import sys
import boto3

def prune_old_amis(region="us-east-1"):
    ec2 = boto3.client("ec2", region_name=region)
    
    # 1. Fetch all AMIs owned by self with Application=Kanga-Route tag
    response = ec2.describe_images(
        Owners=["self"],
        Filters=[{"Name": "tag:Application", "Values": ["Kanga-Route"]}]
    )
    
    images = response.get("Images", [])
    if not images:
        print("No Kanga-Route AMIs found to evaluate.")
        return
    
    # Sort images by CreationDate descending (newest first)
    images.sort(key=lambda x: x["CreationDate"], reverse=True)
    
    keep_ami_ids = set()
    major_anchors = {}
    
    # Rule A: Always keep the 5 most recent AMIs globally
    for img in images[:5]:
        keep_ami_ids.add(img["ImageId"])
    
    # Rule B: Always keep the latest AMI for each MAJOR version branch (e.g. v1, v2)
    for img in images:
        ver_tag = next((t["Value"] for t in img.get("Tags", []) if t["Key"] == "Version"), "1.0.0")
        major_ver = ver_tag.split(".")[0].lstrip("v")
        if major_ver not in major_anchors:
            major_anchors[major_ver] = img["ImageId"]
            keep_ami_ids.add(img["ImageId"])
    
    print(f"Total AMIs evaluated: {len(images)}")
    print(f"AMIs retained under policy: {len(keep_ami_ids)} (Major anchors: {major_anchors})")
    
    # Rule C: Prune expired AMIs and delete their EBS snapshots
    pruned_count = 0
    for img in images:
        ami_id = img["ImageId"]
        if ami_id not in keep_ami_ids:
            print(f"Pruning expired AMI: {ami_id} ({img.get('Name')})")
            
            # Deregister AMI
            ec2.deregister_image(ImageId=ami_id)
            
            # Delete backing EBS snapshots
            for bdm in img.get("BlockDeviceMappings", []):
                if "Ebs" in bdm and "SnapshotId" in bdm["Ebs"]:
                    snap_id = bdm["Ebs"]["SnapshotId"]
                    print(f"  Deleting snapshot: {snap_id}")
                    try:
                        ec2.delete_snapshot(SnapshotId=snap_id)
                    except Exception as e:
                        print(f"  Warning: Could not delete snapshot {snap_id}: {e}")
            
            pruned_count += 1
            
    print(f"AMI cleanup complete. Pruned {pruned_count} old AMI(s).")

if __name__ == "__main__":
    region = sys.argv[1] if len(sys.argv) > 1 else "us-east-1"
    prune_old_amis(region)
