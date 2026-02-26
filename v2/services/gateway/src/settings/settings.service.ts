import { Injectable } from '@nestjs/common';

/**
 * In-memory settings store.
 * In production, this should be backed by the database.
 * For now, settings are initialized from environment variables
 * and can be overridden at runtime via the API.
 */
@Injectable()
export class SettingsService {
  private settings: Record<string, any> = {
    // Email
    smtp_host: process.env.SMTP_HOST || '',
    smtp_port: parseInt(process.env.SMTP_PORT || '587', 10),
    smtp_user: process.env.SMTP_USER || '',
    smtp_pass: '',
    from_email: process.env.SMTP_FROM_EMAIL || '',
    imap_host: process.env.IMAP_HOST || '',
    imap_port: parseInt(process.env.IMAP_PORT || '993', 10),
    imap_user: process.env.IMAP_USER || '',
    imap_pass: '',

    // Pipeline
    imap_wait_hours: parseInt(process.env.IMAP_WAIT_HOURS || '24', 10),
    pitch_model: process.env.PITCH_MODEL || '',

    // Voice agents
    elevenlabs_qualifier_agent_id:
      process.env.ELEVENLABS_QUALIFIER_AGENT_ID || '',
    elevenlabs_sales_agent_id: process.env.ELEVENLABS_SALES_AGENT_ID || '',
    elevenlabs_nurture_agent_id:
      process.env.ELEVENLABS_NURTURE_AGENT_ID || '',
    elevenlabs_auto_agent_id: process.env.ELEVENLABS_AUTO_AGENT_ID || '',

    // CHAMP weights
    champ_weight_challenges: 25,
    champ_weight_authority: 25,
    champ_weight_money: 25,
    champ_weight_prioritization: 25,
  };

  /** Returns all settings with sensitive fields masked for API responses. */
  getSafe(): Record<string, any> {
    const s = { ...this.settings };
    s.smtp_pass = s.smtp_pass ? '••••' : '';
    s.imap_pass = s.imap_pass ? '••••' : '';
    return s;
  }

  /** Internal use only — returns raw settings including plaintext passwords. */
  getAll(): Record<string, any> {
    return { ...this.settings };
  }

  update(partial: Record<string, any>): Record<string, any> {
    this.settings = { ...this.settings, ...partial };
    return this.getSafe();
  }

  get(key: string): any {
    return this.settings[key];
  }
}
