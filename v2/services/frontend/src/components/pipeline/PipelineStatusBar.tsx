import { cn } from '@/lib/utils';
import { PIPELINE_STATES, type PipelineState } from '@/types';
import { getStateDotColor, formatPipelineState } from '@/lib/utils';
import { Check } from 'lucide-react';

interface PipelineStatusBarProps {
  currentState: PipelineState;
  stageTimestamps?: Record<string, string>;
  className?: string;
}

export function PipelineStatusBar({
  currentState,
  stageTimestamps,
  className,
}: PipelineStatusBarProps) {
  const currentIndex = PIPELINE_STATES.indexOf(currentState);

  return (
    <div className={cn('w-full', className)}>
      <div className="flex flex-wrap items-start gap-0">
        {PIPELINE_STATES.map((state, index) => {
          const isCompleted = index < currentIndex;
          const isCurrent = index === currentIndex;
          const isFuture = index > currentIndex;
          const timestamp = stageTimestamps?.[state];

          return (
            <div key={state} className="flex items-start">
              {/* Stage node */}
              <div className="flex flex-col items-center min-w-[70px]">
                {/* Dot */}
                <div
                  className={cn(
                    'w-8 h-8 rounded-full flex items-center justify-center border-2 transition-all',
                    isCompleted && 'bg-green-500 border-green-500',
                    isCurrent &&
                      cn(
                        'border-2',
                        getStateDotColor(state),
                        'ring-2 ring-offset-2 ring-offset-background',
                        state === 'QUALIFIED' || state === 'INTERESTED'
                          ? 'ring-green-400'
                          : state === 'NOT_INTERESTED'
                            ? 'ring-red-400'
                            : state === 'WAITING_REPLY' ||
                                state === 'WAITING_FOLLOW_UP'
                              ? 'ring-yellow-400'
                              : state === 'QUALIFYING_CALL' ||
                                  state === 'SALES_CALL' ||
                                  state === 'NURTURE_CALL' ||
                                  state === 'AUTO_CALL'
                                ? 'ring-purple-400'
                                : state === 'NEW'
                                  ? 'ring-gray-400'
                                  : 'ring-blue-400',
                      ),
                    isFuture && 'border-muted-foreground/30 bg-muted',
                  )}
                >
                  {isCompleted && <Check className="h-4 w-4 text-white" />}
                  {isCurrent && (
                    <div
                      className={cn(
                        'w-3 h-3 rounded-full',
                        getStateDotColor(state),
                      )}
                    />
                  )}
                </div>

                {/* Label */}
                <span
                  className={cn(
                    'text-[10px] mt-1.5 text-center leading-tight max-w-[68px]',
                    isCompleted && 'text-green-400',
                    isCurrent && 'text-foreground font-semibold',
                    isFuture && 'text-muted-foreground/50',
                  )}
                >
                  {formatPipelineState(state)}
                </span>

                {/* Timestamp */}
                {timestamp && (
                  <span className="text-[9px] text-muted-foreground mt-0.5">
                    {new Date(timestamp).toLocaleDateString('en-US', {
                      month: 'short',
                      day: 'numeric',
                    })}
                  </span>
                )}
              </div>

              {/* Connector line */}
              {index < PIPELINE_STATES.length - 1 && (
                <div className="flex items-center mt-[14px]">
                  <div
                    className={cn(
                      'h-0.5 w-4 sm:w-6',
                      index < currentIndex
                        ? 'bg-green-500'
                        : 'bg-muted-foreground/20',
                    )}
                  />
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
