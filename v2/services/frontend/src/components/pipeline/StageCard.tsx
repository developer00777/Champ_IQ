import React, { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  cn,
  getStateColor,
  formatPipelineState,
  formatDate,
} from '@/lib/utils';
import type { PipelineState, PipelineData } from '@/types';
import { ChevronDown, ChevronUp } from 'lucide-react';

interface StageCardProps {
  state: PipelineState;
  isCurrent: boolean;
  timestamp?: string;
  pipelineData?: PipelineData;
  className?: string;
}

export function StageCard({
  state,
  isCurrent,
  timestamp,
  pipelineData,
  className,
}: StageCardProps) {
  const [isExpanded, setIsExpanded] = useState(isCurrent);

  const stageDetails = getStageDetails(state, pipelineData);

  return (
    <Card
      className={cn(
        'transition-all',
        isCurrent && 'ring-1 ring-primary',
        className,
      )}
    >
      <CardHeader className="pb-2">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <CardTitle className="text-base">
              {formatPipelineState(state)}
            </CardTitle>
            <Badge
              variant="outline"
              className={cn('text-[10px]', getStateColor(state))}
            >
              {isCurrent ? 'Current' : 'Completed'}
            </Badge>
          </div>
          {stageDetails && (
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={() => setIsExpanded(!isExpanded)}
            >
              {isExpanded ? (
                <ChevronUp className="h-4 w-4" />
              ) : (
                <ChevronDown className="h-4 w-4" />
              )}
            </Button>
          )}
        </div>
        {timestamp && (
          <p className="text-xs text-muted-foreground">{formatDate(timestamp)}</p>
        )}
      </CardHeader>

      {isExpanded && stageDetails && (
        <CardContent>
          <div className="space-y-2 text-sm">{stageDetails}</div>
        </CardContent>
      )}
    </Card>
  );
}

function getStageDetails(
  state: PipelineState,
  data?: PipelineData,
): React.ReactNode | null {
  if (!data) return null;

  switch (state) {
    case 'RESEARCHED':
      if (!data.research) return null;
      return (
        <div className="space-y-2">
          {data.research.company_info && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                Company Info
              </p>
              <p className="text-sm">{data.research.company_info}</p>
            </div>
          )}
          {data.research.pain_points && data.research.pain_points.length > 0 && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                Pain Points
              </p>
              <ul className="list-disc list-inside text-sm space-y-1">
                {data.research.pain_points.map((point, i) => (
                  <li key={i}>{point}</li>
                ))}
              </ul>
            </div>
          )}
          {data.research.confidence !== undefined && (
            <p className="text-xs text-muted-foreground">
              Confidence: {(data.research.confidence * 100).toFixed(0)}%
            </p>
          )}
        </div>
      );

    case 'PITCHING':
      if (!data.pitch) return null;
      return (
        <div className="space-y-2">
          {data.pitch.emails?.map((email, i) => (
            <div key={i} className="border rounded-md p-3">
              <p className="text-xs font-medium text-muted-foreground">
                Email {email.variant ? `(${email.variant})` : `#${i + 1}`}
              </p>
              <p className="font-medium text-sm mt-1">{email.subject}</p>
              <p className="text-sm mt-1 whitespace-pre-wrap opacity-80">
                {email.body}
              </p>
            </div>
          ))}
          {data.pitch.call_script && (
            <div className="border rounded-md p-3">
              <p className="text-xs font-medium text-muted-foreground">
                Call Script
              </p>
              <p className="text-sm mt-1 whitespace-pre-wrap">
                {data.pitch.call_script}
              </p>
            </div>
          )}
          {data.pitch.confidence !== undefined && (
            <p className="text-xs text-muted-foreground">
              Confidence: {(data.pitch.confidence * 100).toFixed(0)}%
            </p>
          )}
        </div>
      );

    case 'EMAIL_SENT':
      return data.email_id ? (
        <p className="text-sm text-muted-foreground">
          Email ID: <code className="text-xs">{data.email_id}</code>
        </p>
      ) : null;

    case 'FOLLOW_UP_SENT':
      return data.follow_up_email_id ? (
        <p className="text-sm text-muted-foreground">
          Follow-up Email ID:{' '}
          <code className="text-xs">{data.follow_up_email_id}</code>
        </p>
      ) : null;

    case 'WAITING_REPLY':
    case 'WAITING_FOLLOW_UP':
      return data.reply_detected ? (
        <div>
          <Badge variant="outline" className="text-green-400 border-green-400/30">
            Reply Detected
          </Badge>
          {data.reply_content && (
            <p className="text-sm mt-2 whitespace-pre-wrap">
              {data.reply_content}
            </p>
          )}
        </div>
      ) : (
        <p className="text-sm text-muted-foreground">
          Waiting for prospect reply...
        </p>
      );

    case 'QUALIFYING_CALL':
    case 'SALES_CALL':
    case 'NURTURE_CALL':
    case 'AUTO_CALL':
      return (
        <div className="space-y-2">
          {data.call_transcript && (
            <div>
              <p className="text-xs font-medium text-muted-foreground">
                Transcript
              </p>
              <p className="text-sm mt-1 whitespace-pre-wrap max-h-60 overflow-y-auto">
                {data.call_transcript}
              </p>
            </div>
          )}
          {data.call_outcome && (
            <p className="text-sm">
              <span className="text-muted-foreground">Outcome:</span>{' '}
              {data.call_outcome}
            </p>
          )}
        </div>
      );

    default:
      return null;
  }
}
