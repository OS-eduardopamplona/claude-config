---
name: create-bug
description: >-
  Creates RDMST bug tickets in Jira with the correct custom fields for the Model team.
  Use when the user asks to "create an RDMST bug", "file a bug for RDMST",
  "create a Jira bug for Model", or needs to track a bug in the RDMST project.
allowed-tools: Bash(acli jira:*)
---

# Creating RDMST Bugs

Creates bug tickets in the RDMST Jira project with all required custom fields pre-configured for the Model team.

## When to Use

- Creating a new bug in the RDMST Jira project
- Filing a bug to track a fix, customer incident, or defect found by the team

## When NOT to Use

- Creating non-bug issue types (Stories, Tasks, Epics) — use the `jira` skill instead
- Working with projects other than RDMST

## Workflow

1. **Gather context** from the user: what the bug is about, where it was found, whether there's a PR or related incidents
2. **Ask the user** which ring/environment the bug was found in
3. **Determine the OS Product** from context (see values below). If ambiguous, ask the user
4. **Only if the user explicitly asks**, add the bug to the active sprint
5. **Create the bug** using `acli jira workitem create --from-json`
6. **Report back** the created issue key and URL

## Required Information

Before creating the bug, confirm with the user:

| Field | How to get it |
|---|---|
| **Summary** | Ask the user or derive from PR title |
| **Description** | Ask the user or derive from PR description / context provided |
| **Found In Ring/Environment** | Ask the user (see values below) |
| **OS Product** | Infer from context; ask if ambiguous (see values below) |

## Found In Ring/Environment Values

Always ask the user which environment the bug was found in:

| Value | Meaning |
|---|---|
| `Local` | Found during local development |
| `ring-3/dev` | Found in dev ring |
| `ring-2/test` | Found in test ring |
| `ring-1/stage` | Found in staging |
| `ring0/osrd` | Found in OSRD ring |
| `ring+1/osall` | Found in OS-all ring |
| `ring+2/ea` | Found in early access |
| `ring+3/ga` | Found in production (GA) |

## OS Product Values

Infer the OS Product from the context of the bug (e.g., if it's about ODC-specific behavior, use "ODC"). If the context doesn't make it clear, ask the user.

| Value | Meaning |
|---|---|
| `ODC` | Bug affects OutSystems Developer Cloud |
| `O11` | Bug affects OutSystems 11 |
| `O11+ODC` | Bug affects both O11 and ODC |

## Creating the Bug

Use `acli jira workitem create --from-json <file>` with this JSON structure:

```json
{
  "additionalAttributes": {
    "customfield_15720": {
      "value": "<os-product-value>"
    },
    "customfield_16036": {
      "value": "<ring-value>"
    },
    "parent": {
      "key": "RDMST-293"
    }
  },
  "description": {
    "content": [
      {
        "type": "panel",
        "attrs": { "panelType": "info" },
        "content": [
          {
            "type": "paragraph",
            "content": [
              { "text": "Description", "type": "text", "marks": [{"type": "strong"}] }
            ]
          },
          {
            "type": "paragraph",
            "content": [
              { "text": "<what the bug is, what happens, root cause>", "type": "text" }
            ]
          }
        ]
      },
      {
        "type": "panel",
        "attrs": { "panelType": "success" },
        "content": [
          {
            "type": "paragraph",
            "content": [
              { "text": "Acceptance Criteria", "type": "text", "marks": [{"type": "strong"}] }
            ]
          },
          {
            "type": "paragraph",
            "content": [
              { "text": "<what the expected correct behavior should be>", "type": "text" }
            ]
          }
        ]
      },
      {
        "type": "panel",
        "attrs": { "panelType": "note" },
        "content": [
          {
            "type": "paragraph",
            "content": [
              { "text": "Implementation Notes", "type": "text", "marks": [{"type": "strong"}] }
            ]
          },
          {
            "type": "paragraph",
            "content": [
              { "text": "<relevant code locations, links to pipelines, PRs, related tickets>", "type": "text" }
            ]
          }
        ]
      }
    ],
    "type": "doc",
    "version": 1
  },
  "projectKey": "RDMST",
  "summary": "<summary>",
  "type": "Bug"
}
```

### Key fields

- **`customfield_15720`**: "OS Product" — required, use a value from the OS Product table above (e.g., "ODC", "O11", "O11+ODC")
- **`customfield_16036`**: "Found In Ring/Environment" — required, use a value from the table above
- **`parent.key`**: Always `RDMST-293` (Maintenance epic) for bugs
- **`assignee`**: Never set an assignee — leave it empty so the bug goes to the backlog unassigned
- **Description**: Must be in Atlassian Document Format (ADF) using the 3-panel structure (see template). Each panel can contain multiple paragraphs. Links use marks: `{"type": "link", "attrs": {"href": "URL"}}`

### Adding to Active Sprint (only when requested)

Only add the bug to the active sprint if the user explicitly asks for it.

To find the active sprint:

```bash
acli jira board list-sprints --id 927 --state active --json
```

Then add the sprint ID to `additionalAttributes` in the JSON:

```json
"customfield_10006": <sprint-id-as-integer>
```

## Important Limitations

- **`acli jira workitem edit` does NOT support `additionalAttributes`** — the parent epic, ring/environment, and sprint can only be set at creation time via `--from-json`
- If a bug was already created without these fields, the user must set them manually in the Jira UI
- Always write the JSON to a temp file, pass it to `--from-json`, then delete the temp file after creation

## Description Structure

The description uses **3 ADF panels** to organize information visually:

| Panel | ADF `panelType` | Color | Content |
|-------|-----------------|-------|---------|
| **Description** | `info` | Blue | What the bug is, what happens, root cause analysis |
| **Acceptance Criteria** | `success` | Green | What the expected correct behavior should be |
| **Implementation Notes** | `note` | Purple | Code locations, pipeline links, related PRs/tickets |

### Panel rules

- Each panel starts with a **bold heading paragraph** (e.g., `"Description"`, `"Acceptance Criteria"`, `"Implementation Notes"`)
- Follow the heading with one or more content paragraphs
- All 3 panels are **required** — if information is minimal, still include the panel with a brief note
- Use bullet lists (`"type": "bulletList"` with `listItem` children) inside panels when listing multiple items

### Linking inside panels

- Jira issues: `{"text": "RDINC-12345", "type": "text", "marks": [{"type": "link", "attrs": {"href": "https://outsystemsrd.atlassian.net/browse/RDINC-12345"}}]}`
- PRs: `{"text": "OutSystems.Model#123", "type": "text", "marks": [{"type": "link", "attrs": {"href": "https://github.com/OutSystems/OutSystems.Model/pull/123"}}]}`
- Pipelines: `{"text": "Pipeline 2003264", "type": "text", "marks": [{"type": "link", "attrs": {"href": "https://dev.azure.com/OutSystemsRD/..."}}]}`
