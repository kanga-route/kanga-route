#!/usr/bin/env python3
"""
Kanga-Route Production Documentation Promotion Script

1. Reads newly baked AMI ID from packer-manifest.json.
2. Updates README.md Appliance Release Registry Table:
   - Shifts existing 'Latest (Stable)' rows to 'Archived'.
   - Prepends or updates target version row as 'Latest (Stable)' with current ISO release date (YYYY-MM-DD) and Quick Launch link.
3. Updates docs/setup.md Quick Launch AMI ID.
"""

import sys
import os
import json
import re
import datetime

def promote_ami(ver_tag, manifest_path="packer-manifest.json"):
    if not os.path.exists(manifest_path):
        print(f"Error: {manifest_path} not found.")
        sys.exit(1)
        
    manifest = json.load(open(manifest_path))
    new_ami = manifest["builds"][-1]["artifact_id"].split(":")[-1]
    today = datetime.date.today().isoformat()
    ver = ver_tag if ver_tag.startswith("v") else f"v{ver_tag}"
    
    print(f"Promoting AMI ID {new_ami} ({ver}) for date {today}...")
    
    # 1. Update README.md catalog table safely
    if os.path.exists("README.md"):
        readme = open("README.md").read()
        
        launch_url = f"https://console.aws.amazon.com/ec2/v2/home?region=us-east-1#LaunchInstances:amiId={new_ami}"
        new_row = f"| **`{ver}`** | `{today}` | **Latest (Stable)** | `us-east-1` (N. Virginia) | **`{new_ami}`** | [**Launch {ver} Appliance 🚀**]({launch_url}) |\n"
        
        if f"**`{ver}`**" in readme:
            # Update existing row for this exact version
            pattern = re.compile(
                rf'\| \*\*\`{re.escape(ver)}\`*\*\* \| [^|]+ \| [^|]+ \| ([^|]+) \| \*\*\`ami-[a-z0-9]+\`*\*\* \| [^|\n]+\|'
            )
            readme = pattern.sub(
                f"| **`{ver}`** | `{today}` | **Latest (Stable)** | \\1 | **`{new_ami}`** | [**Launch {ver} Appliance 🚀**]({launch_url}) |",
                readme
            )
        else:
            # Shift existing Latest (Stable) entries to Archived
            readme = readme.replace("**Latest (Stable)**", "`Archived`")
            header = "| Version | Release Date | Status | AWS Region | AMI ID | Quick Launch |\n|---|---|---|---|---|---|\n"
            if header in readme:
                readme = readme.replace(header, header + new_row)
        
        open("README.md", "w").write(readme)
        print("Updated README.md catalog table successfully.")
        
    # 2. Update docs/setup.md launch link
    if os.path.exists("docs/setup.md"):
        setup = open("docs/setup.md").read()
        setup = re.sub(r'ami-[a-z0-9]+', new_ami, setup)
        open("docs/setup.md", "w").write(setup)
        print("Updated docs/setup.md launch link successfully.")

if __name__ == "__main__":
    version_tag = sys.argv[1] if len(sys.argv) > 1 else "v1.0.0"
    promote_ami(version_tag)
