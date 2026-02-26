import React from 'react';
import { cn, formatRelativeTime } from '@/lib/utils';
import type { ActivityEvent } from '@/types';
import {
  UserPlus,
  Play,
  ArrowRight,
  Search,
  MessageSquare,
  Mail,
  MailOpen,
  Phone,
  CheckCircle,
  AlertCircle,
} from 'lucide-react';

interface ActivityItemProps {
  event: ActivityEvent;
  className?: string;
}

const iconMap: Record<string, React.ElementType> = {
  prospect_created: UserPlus,
  pipeline_started: Play,
  state_changed: ArrowRight,
  research_completed: Search,
  pitch_generated: MessageSquare,
  email_sent: Mail,
  reply_received: MailOpen,
  call_completed: Phone,
  prospect_qualified: CheckCircle,
  error: AlertCircle,
};

const colorMap: Record<string, string> = {
  prospect_created: 'text-blue-400',
  pipeline_started: 'text-green-400',
  state_changed: 'text-purple-400',
  research_completed: 'text-cyan-400',
  pitch_generated: 'text-indigo-400',
  email_sent: 'text-blue-400',
  reply_received: 'text-yellow-400',
  call_completed: 'text-purple-400',
  prospect_qualified: 'text-green-400',
  error: 'text-red-400',
};

export function ActivityItem({ event, className }: ActivityItemProps) {
  const Icon = iconMap[event.type] || ArrowRight;
  const iconColor = colorMap[event.type] || 'text-gray-400';

  return (
    <div
      className={cn(
        'flex items-start gap-3 py-2.5 px-3 rounded-md hover:bg-muted/50 transition-colors',
        className,
      )}
    >
      <div className={cn('mt-0.5 shrink-0', iconColor)}>
        <Icon className="h-4 w-4" />
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-sm leading-snug">
          {event.prospect_name && (
            <span className="font-medium">{event.prospect_name}</span>
          )}{' '}
          {event.message}
        </p>
        <p className="text-xs text-muted-foreground mt-0.5">
          {formatRelativeTime(event.created_at)}
        </p>
      </div>
    </div>
  );
}
