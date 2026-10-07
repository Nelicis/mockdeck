# mockdeck 

> **Zero-configuration mock REST API server CLI in Python.**  
> Turn any JSON file into a fully functional REST API with CRUD routes, query filtering, sorting, pagination, latency simulation, chaos injection, and a live terminal dashboard in seconds.

---

##  Features

- **Instant Setup:** Run `mockdeck init` to generate a starter database, or point it at any existing JSON file.
- **Complete RESTful CRUD:**
  - `GET /resource` — List collection (with query filters, search, sort, pagination)
  - `GET /resource/:id` — Lookup single item
  - `POST /resource` — Create new item (with auto-generated sequential or UUID IDs)
  - `PUT /resource/:id` — Full replacement of item
  - `PATCH /resource/:id` — Partial field merge
  - `DELETE /resource/:id` — Remove item
- **Query Engine:**
  - **Exact Filtering:** `GET /users?role=admin`
  - **Full-Text Search:** `GET /users?q=alice`
  - **Sorting:** `GET /users?_sort=name&_order=desc`
  - **Pagination:** `GET /users?_page=1&_limit=10` (includes `X-Total-Count`, `X-Page`, `X-Total-Pages` headers)
- **Chaos & Network Simulation:**
  - **Latency Simulation:** `--delay 250` or jitter ranges `--delay 100-500`
  - **Fault Injection:** `--chaos 0.15` (randomly simulates 500 errors on 15% of requests)
- **Seamless CORS:** Permissive CORS enabled by default for painless frontend (React, Vue, Svelte, iOS, Android) development.
- **Beautiful Terminal UI:** Rich startup dashboard and real-time color-coded HTTP request streaming logs.
- **Safe Persistence:** In-memory speed with atomic disk persistence (`os.replace`) to eliminate file corruption.
- **Zero Heavy Web Frameworks:** Built on Python's standard library `http.server.ThreadingHTTPServer` — the only dependency is `rich`!

---

## Quickstart

### 1. Installation

```bash
# Install directly or in a virtual environment
pip install .
```

### 2. Initialize Starter Data

```bash
mockdeck init
```

This creates a sample `db.json` containing `users`, `posts`, and `products`.

### 3. Start the Server

```bash
mockdeck serve db.json
```

Output:
```
Server Address: http://127.0.0.1:8000
Access Mode:    Read / Write (Persistence Active)
Latency Delay:  disabled
Chaos Faults:   disabled

╭────────────────── mockdeck v0.1.0 — Instant Mock REST API ──────────────────╮
│ Resource   Records   Endpoint                                               │
│ posts      3 items   http://127.0.0.1:8000/posts                            │
│ products   3 items   http://127.0.0.1:8000/products                         │
│ users      3 items   http://127.0.0.1:8000/users                            │
╰─────────────────────────────────────────────────────────────────────────────╯
```

---

## API Usage Guide

### Fetch & Filter

```bash
# Get all users
curl http://127.0.0.1:8000/users

# Filter by field value
curl http://127.0.0.1:8000/users?role=admin

# Full-text substring search across all fields
curl http://127.0.0.1:8000/users?q=alice

# Sort users by name descending
curl "http://127.0.0.1:8000/users?_sort=name&_order=desc"

# Paginate (Page 1, 2 items per page)
curl "http://127.0.0.1:8000/users?_page=1&_limit=2"
```

### Create a Record

```bash
curl -X POST http://127.0.0.1:8000/users \
  -H "Content-Type: application/json" \
  -d '{"name": "Diana Prince", "role": "admin"}'
```
*Note: If no `id` is provided in the JSON body, `mockdeck` automatically computes the next sequential ID.*

### Update a Record

```bash
# Full replacement (PUT)
curl -X PUT http://127.0.0.1:8000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice J.", "role": "superadmin"}'

# Partial field merge (PATCH)
curl -X PATCH http://127.0.0.1:8000/users/1 \
  -H "Content-Type: application/json" \
  -d '{"role": "admin"}'
```

### Delete a Record

```bash
curl -X DELETE http://127.0.0.1:8000/users/1
```

---

## CLI Options & Flags

```bash
mockdeck serve [FILE] [OPTIONS]
```

| Option | Default | Description |
|---|---|---|
| `-p, --port <int>` | `8000` | Port to listen on |
| `-H, --host <str>` | `127.0.0.1` | Host address to bind |
| `--delay <spec>` | `0` | Simulated latency in ms (`200`) or jitter range (`100-500`) |
| `--chaos <float>` | `0.0` | Probability of simulated 500 error (`0.1` = 10% errors) |
| `--read-only` | `False` | Disables `POST`, `PUT`, `PATCH`, `DELETE` (returns 403) |
| `--no-save` | `False` | In-memory only mode; mutations do not write to disk |
| `--quiet` | `False` | Suppresses real-time request logging lines |

---

## Running Tests

`mockdeck` has a comprehensive automated test suite with zero test framework dependencies:

```bash
python -m unittest discover -s tests -v
```

---

## License

[MIT](https://mit-license.org/)

