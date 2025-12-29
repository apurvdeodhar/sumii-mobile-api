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

## Events

Server-Sent Events for real-time updates.

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/events/subscribe` | SSE stream |

Event types: `summary_ready`, `lawyer_response`, `case_updated`

---

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
