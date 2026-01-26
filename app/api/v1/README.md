# API v1 Endpoints

## Overview

RESTful API for the Sumii mobile application. All endpoints are prefixed with `/api/v1`.

## Endpoint Groups

| Module | Prefix | Description |
|--------|--------|-------------|
| [auth](#authentication) | `/auth` | Login, registration, token refresh |
| [users](#users) | `/users` | User profile management |
| [conversations](#conversations) | `/conversations` | Chat conversations |
| [summaries](#summaries) | `/summaries` | Legal summaries |
| [documents](#documents) | `/documents` | Document uploads |
| [events](#events) | `/events` | Server-Sent Events |
| [sync](#sync) | `/sync` | Offline data sync |
| [anwalt](#lawyer-integration) | `/anwalt` | Lawyer integration |

---

## Authentication

### Token Configuration

| Setting | Value |
|---------|-------|
| **TTL** | 7 days |
| **Algorithm** | HS256 |

### Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/auth/login` | Login (form data) |
| POST | `/auth/register` | Register new user |
| POST | `/auth/refresh` | Refresh access token |
| POST | `/auth/forgot-password` | Request password reset |
| POST | `/auth/reset-password` | Reset with token |

### Token Refresh

```bash
POST /api/v1/auth/refresh
Authorization: Bearer <access_token>

# Response
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 604800
}
```

---

## Users

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/users/me` | Current user info |
| GET | `/users/profile` | Full user profile |
| PATCH | `/users/profile` | Update profile |

---

## Conversations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/conversations` | List all conversations |
| POST | `/conversations` | Create conversation |
| GET | `/conversations/{id}` | Get conversation |
| DELETE | `/conversations/{id}` | Delete conversation |
| GET | `/conversations/{id}/messages` | Get messages |
| POST | `/conversations/{id}/messages` | Send message |

---

## Summaries

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/summaries` | List all summaries |
| POST | `/summaries` | Generate summary |
| GET | `/summaries/{id}` | Get summary |
| DELETE | `/summaries/{id}` | Delete summary |
| POST | `/summaries/{id}/regenerate` | Regenerate |
| GET | `/summaries/{id}/pdf` | Get PDF URL |

---

## Documents

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/documents` | Upload document |
| GET | `/documents/{id}` | Get document |
| DELETE | `/documents/{id}` | Delete document |

---

## Events (SSE)

Server-Sent Events for real-time updates (notifications).

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events/subscribe` | SSE stream |

Event types: `summary_ready`, `lawyer_response`, `case_updated`

---

## WebSocket Events

Real-time events sent during chat via `/ws/chat/{conversation_id}`.

### Connection

```javascript
// Connect with auth token
const ws = new WebSocket(`wss://api.sumii.de/ws/chat/${conversationId}?token=${accessToken}`);
```

### Event Types

| Event | Direction | Description |
|-------|-----------|-------------|
| `message_chunk` | Server→Client | Streaming AI response chunk |
| `message_complete` | Server→Client | Response finished, final message ID |
| `agent_start` | Server→Client | Agent activated |
| `agent_handoff` | Server→Client | Transition from one agent to another |
| `function_call` | Server→Client | Tool/function execution |
| `reasoning_started` | Server→Client | Reasoning Logic agent processing |
| `facts_complete` | Server→Client | 4+/5 Ws filled |
| `wrapup_ready` | Server→Client | Ready for user confirmation |
| `summary_ready` | Server→Client | Summary generated |
| `error` | Server→Client | Error occurred |

### Event Payloads

```typescript
// message_chunk
{ type: "message_chunk", content: string, agent: string }

// message_complete
{ type: "message_complete", messageId: string, content: string }

// agent_start / agent_handoff
{ type: "agent_start", agent: string, timestamp: string }
{ type: "agent_handoff", fromAgent: string, toAgent: string, timestamp: string }

// function_call
{ type: "function_call", function: string, arguments: object, tool_call_id: string }

// summary_ready
{ type: "summary_ready", summaryId: string, referenceNumber: string,
  conversationId: string, pdfUrl: string, timestamp: string }

// error
{ type: "error", error: string, code: string }
```

### Sending Messages

```javascript
ws.send(JSON.stringify({
  type: "message",
  content: "Hello, my heating is broken",
  documentIds: ["uuid-1", "uuid-2"]  // optional
}));
```

## Sync

Offline-first data synchronization.

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/sync` | Delta sync |

Request body:
```json
{
  "last_synced_at": "2024-01-01T00:00:00Z"  // null for full sync
}
```

---

## Lawyer Integration

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/anwalt/lawyers` | Find lawyers |
| POST | `/anwalt/requests` | Connection request |
| GET | `/anwalt/requests` | List requests |

---

## Error Responses

| Status | Meaning |
|--------|---------|
| 400 | Bad Request |
| 401 | Unauthorized (token expired) |
| 403 | Forbidden |
| 404 | Not Found |
| 422 | Validation Error |
| 500 | Server Error |

Error format:
```json
{
  "detail": "Error message"
}
```

---

## Bug Report: WebSocket Stream Hang & Sequential DB Error (2026-01-25)

### Executive Summary
A critical bug in the WebSocket streaming caused the chat to hang indefinitely after receiving `ResponseDoneEvent`. This masked a secondary database validation error that only became visible after fixing the stream issue.

### Issue #1: Stream Hang (Root Cause)

**Symptom:** Chat would receive AI responses, but after `ResponseDoneEvent`, nothing happened for 3+ minutes before timing out.

**Root Cause:** The Mistral SDK's `ConversationsStreamResponse` iterator is **synchronous** but was being called from within an async context:

```python
# BROKEN CODE
async for event in stream:  # ❌ Sync iterator in async context
    ...
```

The `next(stream_iter)` call blocked the entire asyncio event loop, preventing:
- The `stream_done = True` check from happening
- The `break` statement from executing
- Any downstream code from running

**Fix Applied:** Wrapped the synchronous iterator call in `asyncio.run_in_executor()`:

```python
# FIXED CODE
async def get_next_event():
    loop = asyncio.get_event_loop()
    def _next():
        try:
            return next(stream_iter), False
        except StopIteration:
            return None, True
    try:
        event, exhausted = await asyncio.wait_for(
            loop.run_in_executor(executor, _next),
            timeout=30.0
        )
        return event, exhausted, False
    except asyncio.TimeoutError:
        return None, False, True
```

### Issue #2: Database Validation Error (Sequential)

**Symptom:** After fixing the stream hang, the flow reached `generate_summary` → PDF generation → **database insert** → `IntegrityError: null value in column "case_strength"`.

**Root Cause:** The `summaries` table had `case_strength` as NOT NULL, but `case_strength` was intentionally removed from the summary generation logic (Sumii doesn't make legal judgments, lawyers do).

**Fix Applied:**
1. Migration `0c8d9e1f2a3b` to drop `case_strength` column from `summaries` table
2. Updated `Summary` model, schemas, and API endpoints

### Why Wasn't the DB Error Visible Earlier?

The code **literally never reached the database insert**. The stream was hanging BEFORE the function call processing happened:

```
🏁 [STREAM] ResponseDoneEvent received - stream complete!
# Then... SILENCE for 3+ minutes. No function processing, no DB errors.
```

Only after the executor fix did the flow continue to:
```
📦 [FUNC] Saved final function call: generate_summary
🔧 [FUNC] Processing: generate_summary
ERROR: null value in column "case_strength"...
```

### Lessons Learned

1. **Sync-in-async is dangerous**: Always verify that iterators are truly async before using `async for`
2. **Sequential bugs mask each other**: First bug prevented second bug from ever executing
3. **Add more logging at transition points**: Explicit logs after each major phase help identify where hangs occur
4. **Test the full flow**: Unit tests that mock the stream don't catch sync/async issues

### Files Modified

- `app/api/v1/websocket.py` - Executor-based stream processing
- `app/models/summary.py` - Removed `case_strength` column
- `app/schemas/summary.py` - Removed `case_strength` from schemas
- `app/api/v1/summaries.py` - Removed `case_strength` from API endpoints
- `alembic/versions/0c8d9e1f2a3b_*.py` - Migration to drop column
