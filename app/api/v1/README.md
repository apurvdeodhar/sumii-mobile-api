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
