# Specification: `mockdeck` — Instant Mock REST API Server CLI

## 1. Executive Summary

`mockdeck` is a zero-configuration command-line tool written in Python that transforms any JSON file into a fully working RESTful API with automated CRUD endpoints, query filtering, sorting, pagination, chaos simulation (latency and fault injection), and live terminal traffic logging via Rich.

It provides frontend, mobile, and backend developers with an immediate, lightweight alternative to complex mocking frameworks and third-party SaaS mock services without requiring external server dependencies.

---

## 2. CLI Interface & Commands

The CLI entrypoint is `mockdeck`, implemented with standard argument parsing and Rich terminal formatting.

### 2.1 `mockdeck init [FILE]`
Generates a starter mock JSON dataset if none exists.
* **Arguments:**
  * `FILE` (optional): Path to create the dataset. Defaults to `./db.json`.
* **Behavior:**
  * If the file already exists, aborts with a warning to avoid accidental overwrites.
  * Populates default resources:
    * `users`: 3 sample user objects (`id`, `name`, `email`, `role`).
    * `posts`: 3 sample post objects (`id`, `title`, `userId`, `published`).
    * `products`: 3 sample product objects (`id`, `name`, `price`, `inStock`).
  * Prints a formatted Rich confirmation panel with instructions on how to start serving.

### 2.2 `mockdeck serve [FILE]`
Starts the mock HTTP REST server.
* **Arguments:**
  * `FILE` (optional): Path to the database JSON file. Defaults to `./db.json`.
* **Flags & Options:**
  * `-p, --port <int>`: Port to listen on. Default: `8000`.
  * `-h, --host <str>`: Network interface host to bind to. Default: `127.0.0.1`.
  * `--delay <ms | min-max>`: Simulates network latency in milliseconds.
    * Single integer (e.g. `--delay 300`): adds 300ms delay to every response.
    * Range (e.g. `--delay 100-500`): adds random uniform delay between 100ms and 500ms per request.
    * Default: `0` (no delay).
  * `--chaos <float>`: Chaos fault injection probability between `0.0` and `1.0`.
    * Example: `--chaos 0.15` causes ~15% of all incoming requests to fail with `500 Internal Server Error`.
    * Default: `0.0` (disabled).
  * `--read-only`: Disables mutating HTTP methods (`POST`, `PUT`, `PATCH`, `DELETE`). Mutating requests return `403 Forbidden`.
  * `--no-save`: In-memory only mode. State changes in memory during runtime are not flushed back to the JSON file on disk.
  * `--quiet`: Suppresses request-by-request terminal log streaming, displaying only the startup banner and errors.

---

## 3. Data Engine & Architecture

### 3.1 Data Schema
The mock dataset is a JSON document where every top-level key represents an API resource collection containing an array of JSON objects:
```json
{
  "users": [
    { "id": 1, "name": "Alice", "role": "admin" },
    { "id": 2, "name": "Bob", "role": "user" }
  ],
  "posts": [
    { "id": 1, "title": "First Post", "userId": 1 }
  ]
}
```

### 3.2 State Management & Persistence
* **In-Memory Store:**
  * The dataset is loaded into an in-memory dictionary on server startup.
  * Lookups, mutations, and queries are executed in memory for sub-millisecond execution.
* **Disk Debouncing & Persistence:**
  * Unless `--no-save` or `--read-only` is active, any mutating operation (`POST`, `PUT`, `PATCH`, `DELETE`) marks the dataset as dirty and schedules a write-back to the source JSON file.
  * Writes are atomic (written to a temporary file and atomically renamed) to eliminate file corruption risks.

### 3.3 Server Engine
* Implemented using Python's standard library `http.server.ThreadingHTTPServer`.
* Each incoming HTTP request is handled concurrently in a thread worker without blocking the main event loop.
* Zero external network runtime dependencies (no uvicorn, gunicorn, or twisted needed).

---

## 4. RESTful Routing & Query Conventions

For every top-level resource key `/{resource}` (e.g., `/users`):

### 4.1 Collection Endpoint (`GET /{resource}`)
Returns a JSON array of resources. Supports composable query parameters:
* **Field Filtering:**
  * `?key=value` matches exact values (e.g. `GET /users?role=admin`).
  * Supports multiple filters combined with logical AND (e.g. `GET /users?role=admin&active=true`).
* **Sorting:**
  * `?_sort=field`: Sorts records by the given field name.
  * `?_order=asc|desc`: Sort order direction (default: `asc`).
* **Pagination:**
  * `?_page=<int>`: 1-indexed page number.
  * `?_limit=<int>`: Number of items per page.
  * Sets standard pagination response headers:
    * `X-Total-Count`: Total number of matching records before pagination.
    * `X-Page`: Current page number.
    * `X-Total-Pages`: Total number of pages available.
* **Full-Text Search:**
  * `?q=<term>`: Performs a case-insensitive substring search across all string values of each item in the collection.

### 4.2 Single Item Endpoint (`GET /{resource}/:id`)
* Looks up an item where `item["id"] == id` (supporting integer or string IDs).
* Returns `200 OK` with the matching JSON object.
* Returns `404 Not Found` with `{"error": "Resource not found"}` if the item does not exist.

### 4.3 Create Endpoint (`POST /{resource}`)
* Accepts a JSON request body.
* If `id` is not supplied in the body:
  * Computes the next integer ID (`max(existing_ids) + 1`), or generates a string UUID if existing IDs are strings.
* Appends the new item to the collection.
* Returns `201 Created` with the newly created resource including its assigned `id`.
* Returns `400 Bad Request` if the request payload is not valid JSON.

### 4.4 Full Replace Endpoint (`PUT /{resource}/:id`)
* Replaces the entire resource matching `:id` with the JSON request body.
* Preserves or forces the `id` from the URL parameter.
* Returns `200 OK` with the updated resource.
* Returns `404 Not Found` if the item does not exist.

### 4.5 Partial Update Endpoint (`PATCH /{resource}/:id`)
* Merges the fields from the JSON request body into the existing resource matching `:id`.
* Returns `200 OK` with the merged resource.
* Returns `404 Not Found` if the item does not exist.

### 4.6 Delete Endpoint (`DELETE /{resource}/:id`)
* Removes the item matching `:id` from the collection.
* Returns `204 No Content` with an empty body.
* Returns `404 Not Found` if the item does not exist.

---

## 5. Simulation & Middleware

### 5.1 Latency Simulation
* Configured via `--delay <spec>`.
* Applied as a pre-response sleep for all non-preflight requests:
  * Fixed delay: `time.sleep(ms / 1000.0)`.
  * Jitter range (`min-max`): `time.sleep(random.uniform(min, max) / 1000.0)`.

### 5.2 Chaos Fault Injection
* Configured via `--chaos <rate>` (0.0 to 1.0).
* Before routing the request, generates a random float `r = random.random()`.
* If `r < rate`:
  * Short-circuits the request immediately.
  * Responds with status `500 Internal Server Error` and payload:
    ```json
    {
      "error": "Chaos Monkey: Simulated Internal Server Error",
      "status": 500
    }
    ```

### 5.3 CORS Support
* Enabled globally across all routes.
* For `OPTIONS` requests:
  * Responds with `204 No Content`.
  * Headers:
    * `Access-Control-Allow-Origin: *`
    * `Access-Control-Allow-Methods: GET, POST, PUT, PATCH, DELETE, OPTIONS`
    * `Access-Control-Allow-Headers: *`
* For all other responses (`GET`, `POST`, etc.):
  * Injects `Access-Control-Allow-Origin: *` and `Access-Control-Expose-Headers: X-Total-Count, X-Page, X-Total-Pages`.

---

## 6. Terminal User Interface (Rich)

### 6.1 Startup Dashboard
Displays a styled Rich Panel containing:
* Title: `mockdeck v0.1.0 — Instant Mock REST API`
* URL: `http://127.0.0.1:8000`
* Active Flags: Delay (`300ms`), Chaos rate (`10%`), Read-Only (`disabled`)
* Discovered Resources Table:
  * Columns: `Resource`, `Item Count`, `Sample Endpoint`
  * Example row: `users | 2 items | http://127.0.0.1:8000/users`

### 6.2 Live Request Stream
Every request generates a single formatted console line:
* Timestamp (`%H:%M:%S`)
* HTTP Method styled with badge colors:
  * `GET`: bold cyan
  * `POST`: bold green
  * `PUT`: bold yellow
  * `PATCH`: bold magenta
  * `DELETE`: bold red
  * `OPTIONS`: dim white
* Path and query string (e.g., `/users?role=admin`)
* Status Code:
  * `2xx`: bold green
  * `3xx`: cyan
  * `4xx`: yellow
  * `5xx`: bold red
* Latency duration formatted in ms (e.g., `12.4ms` or `315.2ms`)

---

## 7. Error Handling & Edge Cases

1. **File Missing or Corrupted:**
   * If the data file does not exist, prints a clean error informing the user and recommending `mockdeck init`.
   * If JSON syntax is invalid, prints the exact line, column, and parsing error message without raw Python tracebacks.
2. **Port Conflict (`OSError: EADDRINUSE`):**
   * Catches socket bind errors and suggests: `"Port <port> is already in use. Try passing: --port <port+1>"`.
3. **Invalid Request Body:**
   * Returns `400 Bad Request` with `{"error": "Invalid JSON body"}` if payload cannot be decoded.
4. **Unknown Route / Collection:**
   * Requesting a non-existent collection (e.g. `GET /unknown`) returns `404 Not Found` with `{"error": "Resource 'unknown' not found"}`.
5. **Read-Only Violation:**
   * Mutating requests with `--read-only` enabled return `403 Forbidden` with `{"error": "Server is in read-only mode"}`.

---

## 8. Testing Strategy

All automated tests use Python's built-in `unittest` framework to avoid test-runner dependencies.

### 8.1 Unit Tests (`tests/test_store.py`)
* In-memory store CRUD operations:
  * Adding items with auto-increment ID generation.
  * Updating full items and merging partial patches.
  * Deleting existing items and handling non-existent item deletion.
* Query engine:
  * Single and multi-field exact filtering.
  * Pagination math and edge cases (page exceeding total pages).
  * Sort order (numeric fields, string fields, ascending and descending).
  * Substring text search (`q` parameter).
* Simulation calculations:
  * Delay parsing (integer vs range string).
  * Chaos probability threshold evaluation.

### 8.2 End-to-End HTTP Tests (`tests/test_server.py`)
* Starts a `ThreadingHTTPServer` on an ephemeral port (`port=0`) in a background daemon thread with a temporary JSON database file.
* Uses standard library `urllib.request` to issue actual HTTP requests:
  * `GET /users` returns 200 and JSON list.
  * `POST /users` creates record and returns 201 with generated ID.
  * `PUT /users/1` and `PATCH /users/1` update fields correctly.
  * `DELETE /users/1` returns 204.
  * `OPTIONS /users` returns 204 with permissive CORS headers.
  * Tests `--read-only` behavior returns 403 on POST.
  * Tests that modified state persists to the disk file after mutation.
