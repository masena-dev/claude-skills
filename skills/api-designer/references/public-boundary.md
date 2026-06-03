# Public/Private API Boundary

## Overview

Two specs from one source: `openapi.yaml` (full internal spec for oapi-codegen) and `openapi.public.yaml` (filtered spec for external consumers — API docs, external SDKs, integration partners).

The public spec is generated, not hand-maintained. The source of truth is always `openapi.yaml` plus the filter and overlay files.

## How It Works

1. Mark externally visible operations with `x-public: true` (opt-in — new endpoints are hidden by default)
2. `openapi-format` filters the spec, keeping only public operations
3. An overlay rewrites metadata for the external audience
4. CI ensures the committed public spec stays in sync

## Annotation

Add `x-public: true` at the operation level:

```yaml
paths:
  /api/v1/schedules:
    get:
      x-public: true
      tags: [Schedules]
      summary: List schedules
```

Only annotate operations. Tag definitions for the public spec go in the overlay, not here.

## Filter File

`openapi-format.filter.yaml`:

```yaml
inverseFlags:
  - x-public
stripFlags:
  - x-public
unusedComponents:
  - schemas
  - parameters
  - responses
```

- `inverseFlags: [x-public]` — keeps only operations with `x-public: true`, strips everything else
- `stripFlags: [x-public]` — removes the annotation from the output (external consumers don't see it)
- `unusedComponents` — prunes schemas, parameters, and responses that no surviving operation references

## Overlay File

`openapi-format.overlay.yaml` rewrites metadata for external consumers:

```yaml
overlay: 1.0.0
info:
  title: Public API filtering
  version: 1.0.0
actions:
  # Rewrite the API description with auth docs, pagination format, versioning
  - target: $.info
    update:
      description: |
        REST API for [Product Name].

        ## Authentication
        All requests must include your API key in the `X-API-Key` header.

        ## Pagination
        List endpoints return a cursor-based pagination envelope:
        ```json
        { "cursor": "...", "has_next_page": true, "limit": 20 }
        ```

  # Replace servers with production URL
  - target: $.servers
    update:
      - url: https://api.example.com
        description: Production

  # Replace top-level security with API key only
  - target: $.security[*]
    remove: true
  - target: $
    update:
      security:
        - ApiKeyAuth: []

  # Strip non-ApiKeyAuth entries from per-operation security
  - target: $.paths.*.*.security[?(!@.ApiKeyAuth)]
    remove: true

  # Strip non-header-apikey security schemes
  - target: "$.components.securitySchemes[?(@.type != 'apiKey' || @.in != 'header')]"
    remove: true

  # Define public-facing tag list with descriptions
  - target: $.tags
    update:
      - name: Schedules
        description: Schedule management
      - name: Fleet
        description: Vehicle and worker management
```

Adapt the overlay for each project: update the description, server URLs, tag list, and any project-specific metadata.

## Generation Command

```bash
npx --yes openapi-format openapi.yaml \
  --filterFile openapi-format.filter.yaml \
  --overlayFile openapi-format.overlay.yaml \
  --output openapi.public.yaml
```

## Makefile Target

```makefile
.PHONY: generate-public-openapi
generate-public-openapi:
	npx --yes openapi-format openapi.yaml --filterFile openapi-format.filter.yaml --overlayFile openapi-format.overlay.yaml --output openapi.public.yaml
```

## CI Drift Check

```yaml
- name: Verify public OpenAPI spec
  run: |
    make generate-public-openapi
    git diff --exit-code openapi.public.yaml
```

Regenerates the public spec and fails if the committed version doesn't match. Catches cases where someone modified `openapi.yaml` but forgot to regenerate.

## Spectral Linting

Lint both specs:

```bash
npx @stoplight/spectral-cli lint openapi.yaml --ruleset .spectral.yaml
npx @stoplight/spectral-cli lint openapi.public.yaml --ruleset .spectral.yaml
```

### Suggested Custom Rule

Catch public operations that reference tags with no definition in the public spec. Since tag definitions are managed in the overlay, verify that every tag referenced by a public operation is listed in the overlay's tag update action.

## Setup Checklist for a New Project

1. Create `openapi-format.filter.yaml` (copy the template above)
2. Create `openapi-format.overlay.yaml` (adapt description, server URLs, tag list for the project)
3. Add `generate-public-openapi` target to Makefile
4. Add CI drift check job
5. Add Spectral linting for both specs
6. Mark initial public operations with `x-public: true`
7. Run `make generate-public-openapi` and commit `openapi.public.yaml`
