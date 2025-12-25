/**
 * TypeScript types generated from Pydantic models
 * Auto-generated - DO NOT EDIT MANUALLY
 * Generated from: sumii-mobile-api/app/schemas/
 */

export enum ConversationStatus {
  ACTIVE = "active",
  COMPLETED = "completed",
  ARCHIVED = "archived",
}
export enum LegalArea {
  MIETRECHT = "Mietrecht",
  ARBEITSRECHT = "Arbeitsrecht",
  VERTRAGSRECHT = "Vertragsrecht",
  OTHER = "Other",
}
export enum CaseStrength {
  STRONG = "strong",
  MEDIUM = "medium",
  WEAK = "weak",
}
export enum Urgency {
  IMMEDIATE = "immediate",
  WEEKS = "weeks",
  MONTHS = "months",
}
export enum UploadStatus {
  UPLOADING = "uploading",
  COMPLETED = "completed",
  FAILED = "failed",
}
export enum OCRStatus {
  PENDING = "pending",
  PROCESSING = "processing",
  COMPLETED = "completed",
  FAILED = "failed",
}
export enum ConnectionStatus {
  PENDING = "pending",
  ACCEPTED = "accepted",
  REJECTED = "rejected",
  CANCELLED = "cancelled",
}
export enum MessageRole {
  USER = "user",
  ASSISTANT = "assistant",
  SYSTEM = "system",
}
export enum NotificationType {
  NEW_MESSAGE = "new_message",
  SUMMARY_READY = "summary_ready",
  LAWYER_RESPONSE = "lawyer_response",
  LAWYER_ASSIGNED = "lawyer_assigned",
  CASE_UPDATED = "case_updated",
}

export interface ConversationCreate {
  title?: string | null;
}
  /** Update conversation request schema All fields optional - only provided fields will be updated */
export interface ConversationUpdate {
  title?: string | null;
  status?: ConversationStatus | null;
  legalArea?: LegalArea | null;
  caseStrength?: CaseStrength | null;
  urgency?: Urgency | null;
}
  /** Conversation response schema (without messages) Used for listing conversations (GET /conversations) */
export interface ConversationResponse {
  id: string;
  userId: string;
  title?: string | null;
  status: ConversationStatus;
  legalArea?: LegalArea | null;
  caseStrength?: CaseStrength | null;
  urgency?: Urgency | null;
  currentAgent?: string | null;
  createdAt: string;
  updatedAt: string;
}
  /** Message response schema (nested in ConversationWithMessages) */
export interface MessageResponse {
  id: string;
  conversationId: string;
  role: string;
  content: string;
  agentName?: string | null;
  functionCall?: Record<string, any> | null;
  createdAt: string;
}
  /** Full conversation with all messages Used for retrieving single conversation (GET /conversations/{id}) */
export interface ConversationWithMessages {
  messages: MessageResponse[];
  factsCollected?: Record<string, any> | null;
  analysisDone: boolean;
  summaryGenerated: boolean;
  who?: Record<string, any> | null;
  what?: Record<string, any> | null;
  when?: Record<string, any> | null;
  where?: Record<string, any> | null;
  why?: Record<string, any> | null;
}
export interface DocumentUpload {
  conversationId: string;
  runOcr: boolean;
}
  /** Document update request schema All fields are optional - only provided fields will be updated. */
export interface DocumentUpdate {
  filename?: string | null;
}
  /** Document response with all fields */
export interface DocumentResponse {
  id: string;
  conversationId: string;
  userId: string;
  filename: string;
  fileType: string;
  fileSize: number;
  s3Key: string;
  s3Url: string;
  uploadStatus: UploadStatus;
  ocrStatus: OCRStatus;
  ocrText?: string | null;
  createdAt: string;
}
  /** List of documents with total count */
export interface DocumentListResponse {
  documents: DocumentResponse[];
  total: number;
}
export interface LawyerConnectionCreate {
  conversationId: string;
  lawyerId: number;
  userMessage?: string | null;
}
  /** Lawyer connection response schema */
export interface LawyerConnectionResponse {
  id: string;
  userId: string;
  conversationId: string;
  summaryId?: string | null;
  lawyerId: number;
  lawyerName?: string | null;
  userMessage?: string | null;
  rejectionReason?: string | null;
  status: ConnectionStatus;
  statusChangedAt?: string | null;
  caseId?: string | null;
  createdAt: string;
  updatedAt: string;
  lawyerResponseAt?: string | null;
}
  /** List of lawyer connections */
export interface LawyerConnectionListResponse {
  connections: LawyerConnectionResponse[];
  total: number;
}
  /** Lawyer search query parameters */
export interface LawyerSearchParams {
  lat?: number | null;
  lng?: number | null;
  radius?: number | null;
  legalArea?: string | null;
  language?: string | null;
  limit: number;
  offset: number;
}
export interface NotificationResponse {
  id: string;
  userId: string;
  type: NotificationType;
  title: string;
  message: string;
  data?: Record<string, any> | null;
  read: boolean;
  readAt?: string | null;
  createdAt: string;
  actionedAt?: string | null;
}
  /** List of notifications with pagination */
export interface NotificationListResponse {
  notifications: NotificationResponse[];
  total: number;
  unreadCount: number;
}
  /** Mark notification as read request schema */
export interface NotificationMarkRead {
  read: boolean;
}
  /** Unread notification count response */
export interface NotificationUnreadCountResponse {
  unreadCount: number;
}
export interface PushTokenRegister {
  pushToken: string;
}
  /** Push token registration response */
export interface PushTokenRegisterResponse {
  status: string;
  message: string;
}
export interface SSEEventBase {
  type: string;
  title: string;
  message: string;
  data?: Record<string, any> | null;
}
  /** Summary ready event */
export interface SummaryReadyEvent {
  type: string;
  title: string;
  message: string;
  data: Record<string, any>;
}
  /** Lawyer response event */
export interface LawyerResponseEvent {
  type: string;
  title: string;
  message: string;
  data: Record<string, any>;
}
  /** Lawyer assigned event */
export interface LawyerAssignedEvent {
  type: string;
  title: string;
  message: string;
  data: Record<string, any>;
}
  /** Case updated event */
export interface CaseUpdatedEvent {
  type: string;
  title: string;
  message: string;
  data: Record<string, any>;
}
export interface SummaryCreate {
  conversationId: string;
}
  /** Summary update request schema All fields are optional - only provided fields will be updated. */
export interface SummaryUpdate {
  legalArea?: LegalArea | null;
  caseStrength?: CaseStrength | null;
  urgency?: Urgency | null;
}
  /** Summary response schema Note: Markdown is stored in database AND S3. PDF is stored in S3 only. */
export interface SummaryResponse {
  id: string;
  conversationId: string;
  userId: string;
  referenceNumber: string;
  markdownS3Key: string;
  pdfS3Key: string;
  pdfUrl: string;
  markdownContent: string;
  legalArea: LegalArea;
  caseStrength: CaseStrength;
  urgency: Urgency;
  createdAt: string;
}
export interface LawyerResponseWebhookRequest {
  caseId: number;
  conversationId: string;
  userId: string;
  lawyerId: number;
  lawyerName: string;
  responseText: string;
  responseTimestamp: string;
}
  /** Webhook response schema */
export interface LawyerResponseWebhookResponse {
  status: string;
  message: string;
  notificationId?: string | null;
  emailSent: boolean;
}
export interface WebSocketMessageRequest {
  type: string;
  content: string;
}
  /** Base class for all WebSocket events */
export interface WebSocketEventBase {
  type: string;
  timestamp: string;
}
  /** Agent started processing event */
export interface AgentStartEvent {
  type: string;
  agent: string;
}
  /** Message chunk (streaming) event */
export interface MessageChunkEvent {
  type: string;
  content: string;
  agent: string;
}
  /** Message complete event */
export interface MessageCompleteEvent {
  type: string;
  messageId: string;
  content: string;
  agent: string;
}
  /** Agent handoff started event */
export interface AgentHandoffStartedEvent {
  type: string;
  fromAgent: string;
}
  /** Agent handoff completed event */
export interface AgentHandoffDoneEvent {
  type: string;
  toAgent: string;
}
  /** Combined agent handoff event (alternative format) */
export interface AgentHandoffEvent {
  type: string;
  fromAgent: string;
  toAgent: string;
  reason?: string | null;
}
  /** Function call event */
export interface FunctionCallEvent {
  type: string;
  function: string;
  arguments: Record<string, any>;
}
  /** Error event */
export interface ErrorEvent {
  type: string;
  error: string;
  code?: string | null;
}
