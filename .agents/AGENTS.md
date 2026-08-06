# Repository Rules

- **AWS Credentials Protocol**: Always treat the credentials provided in the chat session and saved in the project's local `.env` file as the sole source of truth for AWS operations. Never inspect, read, or access `~/.aws/credentials` directly.
- **Strict Environment Isolation**: Never fallback to the host system's default AWS profiles, global shell environment, or `~/.aws/config`. All AWS commands, Packer builds, Pulumi operations, and Python scripts must explicitly execute in an isolated environment using the workspace `.env` credentials (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`).
