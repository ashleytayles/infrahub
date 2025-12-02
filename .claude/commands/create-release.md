# Create a new Infrahub release

Create and publish a new release for Infrahub version: $ARGUMENTS

## Prerequisites

Before starting, verify the following:

1. **GitHub MCP Server**: You MUST have the GitHub MCP server configured. This is required to:
   - Create and monitor PRs
   - Create GitHub releases
   - Monitor workflow status
   - Interact with the infrahub-private repository

2. **Valid Python version**: The version argument must be a valid Python/PEP 440 version (e.g., `1.5.0`, `1.6.0-beta1`, `2.0.0-rc1`). Validate this before proceeding.

3. **User initials**: Ask the user for their initials (e.g., "dh" for "Damien Hervaud") to create the branch name.

## Step-by-Step Release Process

### Step 1: Validate Version and Setup

1. Validate the version argument is a valid Python version using:
   ```python
   from packaging.version import Version
   version = Version("$ARGUMENTS")
   is_prerelease = version.is_prerelease
   is_devrelease = version.is_devrelease
   ```

2. Determine the version type:
   - **Patch release**: If the minor version matches the current stable branch (e.g., 1.5.1 when stable is 1.5.x), branch from `stable`
   - **Minor/Major release**: Branch from `develop`
   - **Pre-release (beta/rc/dev)**: Use `develop` as base

3. Ask the user for their initials to create the branch name format: `{initials}/release-{version}` (e.g., `dh/release-1.5.4`)

### Step 2: Create Release Branch

1. Fetch the latest changes:
   ```bash
   git fetch origin
   ```

2. Create and checkout the release branch from the appropriate base:
   ```bash
   # For patch releases:
   git checkout -b {initials}/release-{version} origin/stable
   
   # For minor/major releases:
   git checkout -b {initials}/release-{version} origin/develop
   ```

### Step 3: Generate and Validate Release Notes

1. Run towncrier in draft mode to generate release notes:
   ```bash
   poetry run towncrier build --draft
   ```

2. Present the draft release notes to the user for review and ask:
   - "Do you want to approve these release notes?"
   - "Would you like to make any edits?"

3. If the user wants to edit, allow them to provide modified release notes content.

4. Once approved, create the release notes file at:
   `docs/docs/release-notes/infrahub/release-{version_underscored}.mdx`
   
   Where `{version_underscored}` replaces dots with underscores (e.g., `1_5_4` for version `1.5.4`)

5. The release notes file should follow this format:
   ```mdx
   ---
   title: Release {version}
   ---
   <table>
     <tbody>
       <tr>
         <th>Release Number</th>
         <td>{version}</td>
       </tr>
       <tr>
         <th>Release Date</th>
         <td>{current_date}</td>
       </tr>
       <tr>
         <th>Tag</th>
         <td>[infrahub-v{version}](https://github.com/opsmill/infrahub/releases/tag/infrahub-v{version})</td>
       </tr>
     </tbody>
   </table>

   {release_notes_content}
   ```

6. Run towncrier to consume the changelog fragments:
   ```bash
   poetry run towncrier build --yes --version {version}
   ```

### Step 4: Bump Version Numbers

1. Update the version in the main `pyproject.toml`:
   - Located at the root of the repository
   - Update `version = "X.Y.Z"` under `[tool.poetry]`

2. Update the version in `python_testcontainers/pyproject.toml`:
   - Update `version = "X.Y.Z"` under both `[project]` and `[tool.poetry]`

3. Run poetry lock to update the lock file:
   ```bash
   poetry lock --no-update
   ```

### Step 5: Commit and Create PR

1. Stage all changes:
   ```bash
   git add -A
   ```

2. Commit with a descriptive message:
   ```bash
   git commit -m "chore: release {version}"
   ```

3. Push the branch:
   ```bash
   git push -u origin {branch_name}
   ```

4. Create a PR using GitHub MCP:
   - Title: `chore: release {version}`
   - Base branch: `stable` (for patch releases) or `develop` (for minor/major)
   - Include release notes summary in the PR description

5. Share the PR URL with the user and inform them:
   - "PR created: {pr_url}"
   - "Waiting for CI to pass and PR to be merged..."

### Step 6: Wait for PR Merge

1. Poll the PR status using GitHub MCP every 30 seconds:
   - Check if PR is merged
   - Check CI status

2. If CI fails, inform the user and ask them to fix the issues.

3. Once merged, continue to the next step.

### Step 7: Wait for Bot Updates

After the PR is merged to stable:

1. The OpsMill bot will automatically update `docker-compose.yml` with the new version.

2. Wait for this commit to appear on the stable branch (poll every 30 seconds for up to 5 minutes).

3. Once the bot commit is detected, proceed to create the release.

### Step 8: Create GitHub Release

1. Determine release settings:
   - **Tag**: `infrahub-v{version}`
   - **Target**: `stable` branch
   - **Title**: `Infrahub v{version}`
   - **Body**: Use the validated release notes
   - **Pre-release**: Set to `true` if version is beta/dev/rc (check `is_prerelease` or `is_devrelease`)
   - **Latest release**: Set to `true` only if this is a non-prerelease AND is the highest version number

2. Create the release using GitHub MCP with the above settings.

3. Share the release URL with the user:
   - "Release created: {release_url}"

### Step 9: Monitor "New Release" Workflow

1. Poll the "New Release" workflow status using GitHub MCP:
   - Workflow name: `New Release`
   - Look for the run triggered by the release event

2. Wait for the workflow to complete (poll every 60 seconds).

3. If the workflow fails:
   - Inform the user: "The 'New Release' workflow failed. Please investigate and fix manually."
   - Provide a link to the failed workflow run
   - Wait for user confirmation to continue

4. If the workflow succeeds, proceed to the next step.

### Step 10: Handle infrahub-private Repository

1. After the "New Release" workflow completes, it triggers an update in `opsmill/infrahub-private`.

2. Check for a new PR in the infrahub-private repository:
   - Use GitHub MCP to list recent PRs
   - Look for PRs related to the version update

3. If a PR exists:
   - Check the CI status
   - If CI passed, merge the PR
   - If CI failed:
     - Inform the user: "CI failed on infrahub-private PR: {pr_url}"
     - Ask for user validation before merging
     - Wait for user confirmation

4. Once the PR is merged (or if direct push was made), proceed to create the private release.

### Step 11: Create infrahub-private Release

1. Create a release in the infrahub-private repository:
   - **Tag**: `infrahub-v{version}`
   - **Title**: `Infrahub Enterprise v{version}`
   - **Pre-release**: Match the setting from the public release
   - **Body**: Reference the public release

2. Share the release URL with the user.

### Step 12: Monitor infrahub-private "New Release" Workflow

1. Poll the "New Release" workflow in infrahub-private:
   - Wait for completion (poll every 60 seconds)

2. If the workflow fails:
   - Inform the user: "The 'New Release' workflow in infrahub-private failed."
   - Provide a link to the failed workflow run
   - Ask the user to fix the issue manually
   - Wait for user confirmation that the workflow passed

3. If the workflow succeeds, the release is complete.

## Completion

Once all steps are complete, provide a summary:

```
🎉 Release {version} completed successfully!

Summary:
- Public release: https://github.com/opsmill/infrahub/releases/tag/infrahub-v{version}
- Private release: https://github.com/opsmill/infrahub-private/releases/tag/infrahub-v{version}
- Docker image: Available at registry as infrahub:{version}
- PyPI packages: Published

Next steps:
- Announce the release on Discord/Slack
- Update documentation if needed
- Monitor for any issues reported by users
```

## Error Handling

Throughout the process:

1. If any GitHub API call fails, retry up to 3 times with exponential backoff.

2. If a critical step fails (PR creation, release creation), stop and inform the user with detailed error information.

3. Always provide the user with the option to:
   - Retry the failed step
   - Skip to the next step (if safe)
   - Abort the release process

4. Keep track of completed steps so the process can be resumed if interrupted.

## Notes

- The release process typically takes 15-30 minutes to complete due to CI/CD pipeline times.
- Keep the user informed of progress at each major step.
- If the user needs to step away, provide clear instructions on what manual steps might be needed.
