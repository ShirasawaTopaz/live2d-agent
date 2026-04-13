# Security Policy

## Overview

Live2oder is a desktop AI agent application that connects AI models to Live2D avatars. As an AI agent, it can potentially access your local filesystem and network. Security is a top priority for this project.

Because Live2oder executes tool calls that can interact with your system, we have designed multiple security layers to minimize risk while maintaining functionality.

## Security Features

Live2oder includes the following security measures by default:

### Filesystem Protection
- **Default deny sandbox policy**: All file operations are blocked unless explicitly allowed by the user
- **Configurable access controls**: Whitelist specific directories the agent can access, or blacklist sensitive directories
- **User approval required**: All file write operations require explicit user confirmation before execution
- **File size limits**: Prevents the agent from reading excessively large files that could impact system stability

### Network Protection
- **Private IP blocking**: Outgoing connections to private IP address ranges (RFC 1918) are blocked by default
- **User-configurable rules**: Allow or block specific network destinations
- **No automatic outbound connections**: Only connects to configured AI model endpoints and Live2D

### Data Protection
- **Local API key storage**: All API keys are stored locally on your machine in the user configuration file
- **No remote logging**: Conversation data and API keys are never logged to external services
- **Optional local-only mode**: Can run completely offline with Ollama or local transformer models

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, report them via email to: [security@live2oder.example.com](mailto:security@live2oder.example.com)

You can expect a response within 48 hours. If you do not hear back within that time, please follow up via email to ensure we received your original message.

Please include the following information in your report:
- Type of vulnerability (e.g., buffer overflow, SQL injection, cross-site scripting)
- Full paths of source file(s) related to the issue
- Step-by-step instructions to reproduce the issue
- Impact of the issue, including how an attacker might exploit it
- Any proof-of-concept or exploit code (if available)

## Security Advisories

Known security issues will be published on our [GitHub Security Advisories](https://github.com/live2oder/live2oder/security/advisories) page.

### Known Issues

There are currently no publicly disclosed security vulnerabilities.

## Supported Versions

Security updates are provided for the following versions:

| Version | Supported          |
|---------|-------------------|
| 1.x     | :white_check_mark: |
| < 1.0   | :x:               |

We recommend always using the latest version to receive the most recent security updates.

## Disclosure Policy

This project follows a coordinated disclosure policy:

1. **Report received**: The security team acknowledges receipt of your report within 48 hours
2. **Assessment**: Our team assesses the vulnerability and determines its severity
3. **Fix development**: We work on a fix privately with the reporter
4. **Public disclosure**: After the fix is released, we issue a public security advisory
5. **Timeline**: We aim to release a fix for critical vulnerabilities within 90 days

### Credit

We believe in giving credit to researchers who responsibly disclose vulnerabilities. We will publicly acknowledge your contribution once the issue is resolved, unless you prefer to remain anonymous.

## Best Practices for Users

Even with built-in security measures, we recommend:

1. **Keep the software updated**: Always use the latest version with recent security patches
2. **Restrict file access**: Only whitelist directories the agent actually needs to access
3. **Review approvals**: Always read and understand the file operation before approving it
4. **Use API keys securely**: Never share your config.json file which contains your API keys
5. **Run with user privileges**: Do not run Live2oder with administrator/root privileges unless necessary

---

This security policy is based on GitHub's recommended security policy best practices.