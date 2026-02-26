import { Injectable } from '@nestjs/common';
import { randomUUID } from 'crypto';

export interface ActivityEvent {
  id: string;
  type: string;
  prospect_id?: string;
  prospect_name?: string;
  message: string;
  data?: Record<string, any>;
  created_at: string;
}

/**
 * In-memory activity event store.
 * Keeps the most recent 500 events for REST API queries.
 * Real-time events are pushed via WebSocket independently.
 */
@Injectable()
export class ActivityService {
  private events: ActivityEvent[] = [];
  private readonly maxEvents = 500;

  add(event: Omit<ActivityEvent, 'id' | 'created_at'>): ActivityEvent {
    const fullEvent: ActivityEvent = {
      id: randomUUID(),
      created_at: new Date().toISOString(),
      ...event,
    };
    this.events.unshift(fullEvent);
    if (this.events.length > this.maxEvents) {
      this.events = this.events.slice(0, this.maxEvents);
    }
    return fullEvent;
  }

  getRecent(limit = 50, prospectId?: string): ActivityEvent[] {
    let filtered = this.events;
    if (prospectId) {
      filtered = filtered.filter((e) => e.prospect_id === prospectId);
    }
    return filtered.slice(0, limit);
  }
}
