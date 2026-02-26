// ── V2 Pipeline States ──────────────────────────────────────────────
export const PIPELINE_STATES = [
  'NEW',
  'RESEARCHING',
  'RESEARCHED',
  'PITCHING',
  'EMAIL_SENT',
  'WAITING_REPLY',
  'FOLLOW_UP_SENT',
  'WAITING_FOLLOW_UP',
  'QUALIFYING_CALL',
  'INTERESTED',
  'NOT_INTERESTED',
  'SALES_CALL',
  'NURTURE_CALL',
  'AUTO_CALL',
  'QUALIFIED',
] as const;

export type PipelineState = (typeof PIPELINE_STATES)[number];

// ── CHAMP Scoring ───────────────────────────────────────────────────
export type CHAMPTier = 'CHAMPION' | 'HOT' | 'WARM' | 'COOL' | 'COLD';

export interface CHAMPScore {
  challenges: number;
  authority: number;
  money: number;
  prioritization: number;
  total: number;
  tier: CHAMPTier;
}

// ── Prospect ────────────────────────────────────────────────────────
export interface Prospect {
  id: string;
  name: string;
  email: string;
  title?: string;
  phone?: string;
  company_domain?: string;
  pipeline_state: PipelineState;
  pipeline_data?: PipelineData;
  champ_score?: CHAMPScore;
  created_at: string;
  updated_at: string;
}

export interface PipelineData {
  research?: ResearchResult;
  pitch?: PitchResult;
  email_id?: string;
  follow_up_email_id?: string;
  reply_detected?: boolean;
  reply_content?: string;
  call_transcript?: string;
  call_outcome?: string;
  stage_timestamps?: Record<PipelineState, string>;
  [key: string]: unknown;
}

export interface ResearchResult {
  company_info?: string;
  prospect_info?: string;
  pain_points?: string[];
  confidence?: number;
}

export interface PitchResult {
  emails?: PitchEmail[];
  call_script?: string;
  confidence?: number;
}

export interface PitchEmail {
  subject: string;
  body: string;
  variant?: string;
}

// ── Activity ────────────────────────────────────────────────────────
export type ActivityEventType =
  | 'prospect_created'
  | 'pipeline_started'
  | 'state_changed'
  | 'research_completed'
  | 'pitch_generated'
  | 'email_sent'
  | 'reply_received'
  | 'call_completed'
  | 'prospect_qualified'
  | 'error';

export interface ActivityEvent {
  id: string;
  type: ActivityEventType;
  prospect_id?: string;
  prospect_name?: string;
  message: string;
  data?: Record<string, unknown>;
  created_at: string;
}

// ── Settings ────────────────────────────────────────────────────────
export interface Settings {
  // Account
  display_name?: string;

  // Email credentials
  smtp_host?: string;
  smtp_port?: number;
  smtp_user?: string;
  smtp_pass?: string;
  imap_host?: string;
  imap_port?: number;
  imap_user?: string;
  imap_pass?: string;
  from_email?: string;

  // Pipeline settings
  imap_wait_hours?: number;
  pitch_model?: string;

  // Voice agent settings (ElevenLabs)
  elevenlabs_qualifier_agent_id?: string;
  elevenlabs_sales_agent_id?: string;
  elevenlabs_nurture_agent_id?: string;
  elevenlabs_auto_agent_id?: string;

  // CHAMP weights
  champ_weight_challenges?: number;
  champ_weight_authority?: number;
  champ_weight_money?: number;
  champ_weight_prioritization?: number;
}

// ── Auth ─────────────────────────────────────────────────────────────
export interface User {
  id: string;
  email: string;
  name: string;
}

export interface AuthResponse {
  token: string;
  user: User;
}

// ── API Responses ────────────────────────────────────────────────────
export interface ApiResponse<T> {
  data: T;
  message?: string;
}

export interface PaginatedResponse<T> {
  data: T[];
  total: number;
  page: number;
  per_page: number;
}

export interface HealthStatus {
  status: string;
  version?: string;
  services?: Record<string, string>;
}
