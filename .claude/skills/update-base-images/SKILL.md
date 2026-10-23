# Skill: update-base-images

Update the base images in the `Containerfile` (tag + digest pins).

Use this skill when:

- A CVE rebuild ticket requires updated base images
- The user asks to bump/refresh the base images

## Files involved

- `Containerfile` (repo root) — multi-stage, two base images:
  - **builder** stage: `registry.access.redhat.com/hi/python:3.12-builder@sha256:<digest>` (Hummingbird). The tag is floating (`3.12-builder`); only the digest changes.
  - **runtime** stage: `registry.access.redhat.com/ubi10-minimal:<tag>@sha256:<digest>`. Tag looks like `10.2-1792457157`. A `# YYYY-MM-DD` comment sits on the line above this `FROM` and holds the image's creation date.

## Step 1: Find the latest builder digest and runtime tag

```bash
# Builder: the tag is floating, so just get the current digest and creation date
skopeo inspect --no-tags --format '{{.Digest}} {{.Created}}' \
  docker://registry.access.redhat.com/hi/python:3.12-builder

# Runtime: latest ubi10-minimal version tag (ignore -source and other tags)
skopeo list-tags docker://registry.access.redhat.com/ubi10-minimal 2>/dev/null | \
  python3 -c "
import json, sys, re
tags = json.load(sys.stdin)['Tags']
version_tags = [t for t in tags if re.match(r'^10\.\d+-\d+$', t)]
version_tags.sort(key=lambda t: int(t.split('-')[1]), reverse=True)
print(version_tags[0])
"

# Digest and creation date for that runtime tag (substitute <new-tag>)
skopeo inspect --no-tags --format '{{.Digest}} {{.Created}}' \
  docker://registry.access.redhat.com/ubi10-minimal:<new-tag>
```

If the digest/tag already match the `Containerfile`, tell the user there is nothing to update.

## Step 2: Update the Containerfile

Edit the two `FROM` lines. Always keep both the tag and the `@sha256:` digest, and keep `AS builder` on the first one:

- Builder: `FROM registry.access.redhat.com/hi/python:3.12-builder@sha256:<new-builder-digest> AS builder`
- Runtime: `FROM registry.access.redhat.com/ubi10-minimal:<new-tag>@sha256:<new-minimal-digest>`

Also update the date comment directly above the runtime `FROM` to the runtime image's creation date (`YYYY-MM-DD`, from `.Created` in Step 1).

## Step 3: Verify

```bash
git diff --stat
```

Expect changes in `Containerfile` and, usually, `.konflux/rpms/rpms.lock.yaml`. Optionally validate the full hermetic prefetch locally (pip + RPM + artifacts):

```bash
make hermeto-prefetch
```

Do not commit or push without the user's approval; show the proposed commit message first.
