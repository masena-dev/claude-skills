# OpenAPI 3.0 Patterns

Copy-paste reference for common endpoint types. Each snippet is self-contained and follows project conventions exactly.

---

## 1. CRUD Resource Set

Full bookmark CRUD. Shows: 201 for create, `{message, resource}` response for GET, allOf Paging for list, 204 for mutations. Schema hierarchy: `BaseBookmark` → `Bookmark` (full) → `BookmarkSummary` (list projection).

### Paths

```yaml
paths:
  /api/v1/bookmarks:
    post:
      summary: Create bookmark
      operationId: createBookmark
      security:
        - BearerAuth: ["bookmarks:create"]
          ApiKeyAuth: []
      tags:
        - bookmarks
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/CreateBookmarkRequest"
      responses:
        "201":
          description: Bookmark created successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/CreateBookmarkResponse"
        "400":
          $ref: "#/components/responses/BadRequestError"
        "401":
          $ref: "#/components/responses/UnauthorizedError"
        "409":
          $ref: "#/components/responses/ConflictError"

    get:
      summary: List bookmarks
      operationId: listBookmarks
      security:
        - BearerAuth: []
          ApiKeyAuth: []
      tags:
        - bookmarks
      parameters:
        - name: cursor
          in: query
          allowEmptyValue: true
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            default: 20
      responses:
        "200":
          description: Bookmarks retrieved successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ListBookmarksResponse"
        "401":
          $ref: "#/components/responses/UnauthorizedError"

  /api/v1/bookmarks/{bookmark_id}:
    get:
      summary: Get bookmark by ID
      operationId: getBookmark
      security:
        - BearerAuth: []
          ApiKeyAuth: []
      tags:
        - bookmarks
      parameters:
        - name: bookmark_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Bookmark retrieved successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GetBookmarkResponse"
        "401":
          $ref: "#/components/responses/UnauthorizedError"
        "404":
          $ref: "#/components/responses/NotFound"

    delete:
      summary: Delete bookmark
      operationId: deleteBookmark
      security:
        - BearerAuth: ["bookmarks:delete:own"]
          ApiKeyAuth: []
        - BearerAuth: ["bookmarks:delete:any"]
          ApiKeyAuth: []
      tags:
        - bookmarks
      parameters:
        - name: bookmark_id
          in: path
          required: true
          schema:
            type: string
      responses:
        "204":
          description: Bookmark deleted successfully
        "401":
          $ref: "#/components/responses/UnauthorizedError"
        "403":
          $ref: "#/components/responses/ForbiddenError"
        "404":
          $ref: "#/components/responses/NotFound"
```

### Schemas

```yaml
components:
  schemas:
    BaseBookmark:
      type: object
      required:
        - id
        - post_slug
        - created_at
      properties:
        id:
          type: string
        post_slug:
          type: string
        created_at:
          type: string
          format: date-time

    Bookmark:
      allOf:
        - $ref: "#/components/schemas/BaseBookmark"
        - type: object
          required:
            - post_title
            - post_author
          properties:
            post_title:
              type: string
            post_author:
              $ref: "#/components/schemas/BaseUser"
            note:
              type: string
              nullable: true
              x-omitempty: false

    BookmarkSummary:
      allOf:
        - $ref: "#/components/schemas/BaseBookmark"
        - type: object
          required:
            - post_title
          properties:
            post_title:
              type: string

    CreateBookmarkRequest:
      type: object
      required:
        - post_slug
      properties:
        post_slug:
          type: string
        note:
          type: string

    CreateBookmarkResponse:
      type: object
      required:
        - message
        - bookmark
      properties:
        message:
          type: string
        bookmark:
          $ref: "#/components/schemas/Bookmark"

    GetBookmarkResponse:
      type: object
      required:
        - message
        - bookmark
      properties:
        message:
          type: string
        bookmark:
          $ref: "#/components/schemas/Bookmark"

    ListBookmarksResponse:
      allOf:
        - $ref: "#/components/schemas/Paging"
        - type: object
          required:
            - message
            - bookmarks
          properties:
            message:
              type: string
            bookmarks:
              type: array
              items:
                $ref: "#/components/schemas/BookmarkSummary"
```

---

## 2. List with Cursor Pagination

Full pattern: `cursor` with `allowEmptyValue` (required — backend uses empty string as "first page"), optional `limit`, optional `sort` enum. Response always composes allOf Paging.

```yaml
paths:
  /api/v1/posts:
    get:
      summary: List posts
      operationId: listPosts
      security:
        - BearerAuth: []
          ApiKeyAuth: []
        - ApiKeyAuth: []
      tags:
        - posts
      parameters:
        - name: cursor
          in: query
          allowEmptyValue: true
          schema:
            type: string
            example: "PHbDcuHEvxy5sTrDE="
        - name: limit
          in: query
          required: false
          schema:
            type: integer
            minimum: 1
            default: 20
            example: 20
        - name: sort
          in: query
          required: false
          schema:
            $ref: "#/components/schemas/EngagementSortOrder"
            default: "newest"
      responses:
        "200":
          description: Posts retrieved successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ListPostsResponse"
        "400":
          $ref: "#/components/responses/BadRequestError"
        "401":
          $ref: "#/components/responses/UnauthorizedError"

components:
  schemas:
    EngagementSortOrder:
      type: string
      enum:
        - newest
        - oldest
        - top
        - hot
        - controversial

    Paging:
      type: object
      required:
        - cursor
        - has_next_page
        - limit
      properties:
        cursor:
          type: string
        has_next_page:
          type: boolean
        limit:
          type: integer

    ListPostsResponse:
      allOf:
        - $ref: "#/components/schemas/Paging"
        - type: object
          required:
            - message
            - posts
          properties:
            message:
              type: string
            posts:
              type: array
              items:
                $ref: "#/components/schemas/PostSummary"
```

---

## 3. Action Endpoint

No request body. 204 response. Admin scope. Path uses verb noun (`/approve`) after resource path.

```yaml
paths:
  /api/v1/posts/{post_slug}/approve:
    post:
      summary: Approve a post
      operationId: approvePost
      security:
        - BearerAuth: ["admin:access"]
          ApiKeyAuth: []
      tags:
        - posts
      parameters:
        - name: post_slug
          in: path
          required: true
          schema:
            type: string
      responses:
        "204":
          description: Post approved successfully
        "401":
          $ref: "#/components/responses/UnauthorizedError"
        "403":
          $ref: "#/components/responses/ForbiddenError"
        "404":
          $ref: "#/components/responses/NotFound"
```

---

## 4. Admin Endpoint

Multi-scope security block (any one scope grants access — separate list items are OR; properties within a single list item are AND). Admin-specific fields via allOf. Cursor pagination with optional filters.

```yaml
paths:
  /api/v1/admin/users:
    get:
      summary: List users with admin filtering
      operationId: listUsersAdmin
      security:
        - BearerAuth:
            - users:view:reported
            - users:view:banned
            - users:view:deleted
          ApiKeyAuth: []
      tags:
        - admin
      parameters:
        - name: role
          in: query
          required: false
          schema:
            $ref: "#/components/schemas/UserRole"
          description: Filter by role. Omit to return all roles.
        - name: state
          in: query
          required: false
          schema:
            $ref: "#/components/schemas/ListUsersState"
          description: Filter by state. Omit to return all states.
        - name: search_term
          in: query
          required: false
          schema:
            type: string
        - name: cursor
          in: query
          allowEmptyValue: true
          schema:
            type: string
        - name: limit
          in: query
          schema:
            type: integer
            minimum: 1
            default: 20
      responses:
        "200":
          description: Users retrieved successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/ListUsersAdminResponse"
        "400":
          $ref: "#/components/responses/BadRequestError"
        "401":
          $ref: "#/components/responses/UnauthorizedError"
        "403":
          $ref: "#/components/responses/ForbiddenError"

components:
  schemas:
    AdminUserStatus:
      type: string
      enum: [active, banned, deleted]

    AdminUser:
      allOf:
        - $ref: "#/components/schemas/UserProfile"
        - type: object
          required:
            - status
          properties:
            status:
              $ref: "#/components/schemas/AdminUserStatus"
            deleted_at:
              type: string
              format: date-time
              description: When the account was soft-deleted

    ListUsersAdminResponse:
      allOf:
        - $ref: "#/components/schemas/Paging"
        - type: object
          required:
            - users
            - message
          properties:
            message:
              type: string
            users:
              type: array
              items:
                $ref: "#/components/schemas/AdminUser"
```

---

## 5. Public with Optional Auth

Dual security block: first entry requires BearerAuth + ApiKeyAuth (authenticated), second entry requires only ApiKeyAuth (anonymous). Authenticated users receive context fields (`user_vote`, `is_following`). Anonymous users receive the same base fields but those context fields will be zero-valued/null.

```yaml
paths:
  /api/v1/posts/{post_slug}:
    get:
      summary: Get a post by slug
      operationId: getPostBySlug
      security:
        - BearerAuth: []
          ApiKeyAuth: []
        - ApiKeyAuth: []
      tags:
        - posts
      parameters:
        - name: post_slug
          in: path
          required: true
          schema:
            type: string
      responses:
        "200":
          description: Post found successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/GetPostResponse"
        "404":
          $ref: "#/components/responses/NotFound"

components:
  schemas:
    # BaseUser — anonymous-visible fields only
    BaseUser:
      type: object
      required:
        - username
        - first_name
        - last_name
        - role
      properties:
        username:
          type: string
        first_name:
          type: string
        last_name:
          type: string
        profile_picture_url:
          type: string
          format: uri
          nullable: true
          x-omitempty: false
        role:
          $ref: "#/components/schemas/UserRole"
        bio:
          type: string
          nullable: true
          x-omitempty: false

    # UserWithContext — authenticated-only context fields
    UserWithContext:
      allOf:
        - $ref: "#/components/schemas/BaseUser"
        - type: object
          properties:
            is_following:
              type: boolean
              x-omitempty: false

    GetPostResponse:
      type: object
      required:
        - message
        - post
      properties:
        message:
          type: string
        post:
          $ref: "#/components/schemas/Post"

    # Post.author is UserWithContext so is_following is present for authed users.
    # Post.user_vote is present in the schema but resolves to "none" for anonymous
    # requests — the backend populates it based on auth context.
    Post:
      type: object
      required:
        - slug
        - title
        - content
        - type
        - status
        - vote_count
        - comment_count
        - user_vote
        - author
        - created_at
        - updated_at
      properties:
        slug:
          type: string
        title:
          type: string
        content:
          $ref: "#/components/schemas/PostContent"
        type:
          $ref: "#/components/schemas/PostType"
        status:
          $ref: "#/components/schemas/PostStatus"
        vote_count:
          type: integer
        user_vote:
          $ref: "#/components/schemas/Vote"
        comment_count:
          type: integer
        author:
          $ref: "#/components/schemas/UserWithContext"
        created_at:
          type: string
          format: date-time
        updated_at:
          type: string
          format: date-time
```

---

## 6. Polymorphic Content

`oneOf` with `discriminator`. Each variant schema must include the discriminator property (`type`). The mapping values are JSON Reference strings.

```yaml
components:
  schemas:
    PostContent:
      type: object
      oneOf:
        - $ref: "#/components/schemas/ArticleContent"
        - $ref: "#/components/schemas/MediaContent"
        - $ref: "#/components/schemas/LinkContent"
      discriminator:
        propertyName: type
        mapping:
          article: "#/components/schemas/ArticleContent"
          media: "#/components/schemas/MediaContent"
          link: "#/components/schemas/LinkContent"

    ArticleContent:
      type: object
      required:
        - type
        - content
        - content_excerpt
        - reading_time_mins
      properties:
        type:
          type: string
        content:
          type: object
          additionalProperties: true
          description: JSON from rich text editor
          x-go-type: json.RawMessage
        content_excerpt:
          type: string
        reading_time_mins:
          type: integer

    MediaContent:
      type: object
      required:
        - type
        - description
        - media
      properties:
        type:
          type: string
        description:
          type: string
        media:
          type: array
          items:
            $ref: "#/components/schemas/Media"
          minItems: 1

    LinkContent:
      type: object
      required:
        - type
        - link_url
      properties:
        type:
          type: string
        link_url:
          type: string
          format: uri
        page_title:
          type: string
          x-go-type-skip-optional-pointer: true
        preview_description:
          type: string
          x-go-type-skip-optional-pointer: true
        description:
          type: string
          x-go-type-skip-optional-pointer: true
```

---

## 7. Schema Composition Hierarchy

Three-level chain. Each level adds fields to the previous via allOf. Use `x-omitempty: false` on nullable booleans and context fields to prevent Go codegen from omitting zero values in JSON.

```yaml
components:
  schemas:
    # Level 1 — always-visible identity fields
    BaseUser:
      type: object
      required:
        - username
        - first_name
        - last_name
        - role
      properties:
        username:
          type: string
        first_name:
          type: string
        last_name:
          type: string
        profile_picture_url:
          type: string
          format: uri
          nullable: true
          x-omitempty: false
        role:
          $ref: "#/components/schemas/UserRole"
          x-omitempty: false
        bio:
          type: string
          nullable: true
          x-omitempty: false

    # Level 2 — adds relationship context for authenticated requests
    UserWithContext:
      allOf:
        - $ref: "#/components/schemas/BaseUser"
        - type: object
          properties:
            is_following:
              type: boolean
              x-omitempty: false

    # Level 3 — adds membership metadata for space member lists
    TeamMember:
      allOf:
        - $ref: "#/components/schemas/UserWithContext"
        - type: object
          required:
            - joined_at
          properties:
            joined_at:
              type: string
              format: date-time
```

---

## 8. Scope Enum

Scopes are defined as a named enum in `components/schemas`. Both the Go backend and TypeScript frontend generate typed constants from this enum. Keep entries alphabetically ordered by resource for scannability. Resource names are single plural nouns, actions are single verbs, qualifiers describe access level.

```yaml
components:
  schemas:
    Scope:
      type: string
      enum:
        - "admin:access"
        - "blogs:create"
        - "blogs:delete"
        - "blogs:update"
        - "blogs:view:draft"
        - "comments:create"
        - "comments:delete:any"
        - "comments:delete:own"
        - "comments:update:any"
        - "comments:update:own"
        - "content:report"
        - "content:vote"
        - "posts:create"
        - "posts:delete:any"
        - "posts:delete:own"
        - "posts:update:any"
        - "posts:update:own"
        - "posts:view:all"
        - "quality:override"
        - "quality:view"
        - "reports:review"
        - "reports:view:any"
        - "roles:assign"
        - "spaces:create"
        - "spaces:delete"
        - "spaces:update"
        - "users:ban:permanent"
        - "users:ban:temporary"
        - "users:unban"
```

When adding a new endpoint that requires a new scope: add the scope value to this enum in the correct alphabetical position, then reference it in the endpoint's `security` block.

---

## 9. Enum with x-enumNames

`x-enumNames` generates named Go constants. Values and names must stay in sync positionally — index N of `enum` maps to index N of `x-enumNames`. Enum values are SCREAMING_SNAKE_CASE; x-enumNames are PascalCase.

```yaml
components:
  schemas:
    PersonaID:
      type: string
      enum:
        - personal
        - official_admin
        - official_moderator
      x-enumNames:
        - PersonalPersona
        - OfficialAdminPersona
        - OfficialModeratorPersona

    ErrorCode:
      type: string
      enum:
        - INVALID_CREDENTIALS
        - USER_NOT_FOUND
        - INSUFFICIENT_PERMISSIONS
        - RATE_LIMIT_EXCEEDED
        - UNEXPECTED_ERROR
      x-enumNames:
        - InvalidCredentials
        - UserNotFound
        - InsufficientPermissions
        - RateLimitExceeded
        - UnexpectedError
```

**Critical**: if you add a value to `enum`, you must add the corresponding name to `x-enumNames` at the same position. The codegen does not validate alignment — a mismatch produces silently wrong constants.

---

## 10. Mobile Auth Flow

API-key-only auth for login and refresh (no bearer — you don't have a token yet). Returns `access_token` + `refresh_token` + `expires_in`. All other mobile endpoints use `BearerAuth` + `ApiKeyAuth` like web — mobile apps carry their own API key.

```yaml
paths:
  /api/v1/auth/mobile/login:
    post:
      summary: Mobile login with email and password
      operationId: mobileLogin
      security:
        - ApiKeyAuth: []
      tags:
        - authentication
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/MobileLoginRequest"
      responses:
        "200":
          description: Logged in successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/MobileAuthResponse"
        "400":
          $ref: "#/components/responses/BadRequestError"
        "401":
          $ref: "#/components/responses/UnauthorizedError"

  /api/v1/auth/mobile/refresh:
    post:
      summary: Refresh mobile access token
      operationId: mobileRefreshToken
      security:
        - ApiKeyAuth: []
      tags:
        - authentication
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: "#/components/schemas/MobileRefreshRequest"
      responses:
        "200":
          description: Tokens refreshed successfully
          content:
            application/json:
              schema:
                $ref: "#/components/schemas/MobileAuthResponse"
        "401":
          $ref: "#/components/responses/UnauthorizedError"

components:
  schemas:
    MobileLoginRequest:
      type: object
      required:
        - email
        - password
      properties:
        email:
          type: string
          format: email
        password:
          type: string

    MobileRefreshRequest:
      type: object
      required:
        - refresh_token
      properties:
        refresh_token:
          type: string

    MobileAuthResponse:
      type: object
      required:
        - message
        - access_token
        - refresh_token
        - expires_in
      properties:
        message:
          type: string
        access_token:
          type: string
        refresh_token:
          type: string
        expires_in:
          type: integer
          description: Access token lifetime in seconds
```
