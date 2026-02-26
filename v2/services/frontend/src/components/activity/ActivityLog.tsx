import { useEffect } from 'react';
import { useActivityStore } from '@/stores/activityStore';
import { ActivityItem } from './ActivityItem';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Activity } from 'lucide-react';
import type { ActivityEvent } from '@/types';

interface ActivityLogProps {
  prospectId?: string;
  maxHeight?: string;
  title?: string;
  events?: ActivityEvent[];
}

export function ActivityLog({
  prospectId,
  maxHeight = '500px',
  title = 'Activity Log',
  events: externalEvents,
}: ActivityLogProps) {
  const { events: storeEvents, fetchRecent, connect, disconnect } = useActivityStore();

  useEffect(() => {
    fetchRecent();
    connect();
    return () => disconnect();
  }, [fetchRecent, connect, disconnect]);

  const events = externalEvents || storeEvents;

  const filteredEvents = prospectId
    ? events.filter((e) => e.prospect_id === prospectId)
    : events;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Activity className="h-4 w-4" />
          {title}
        </CardTitle>
      </CardHeader>
      <CardContent className="pt-0">
        <ScrollArea style={{ maxHeight }}>
          {filteredEvents.length === 0 ? (
            <p className="text-sm text-muted-foreground py-4 text-center">
              No activity yet.
            </p>
          ) : (
            <div className="space-y-0.5">
              {filteredEvents.map((event) => (
                <ActivityItem key={event.id} event={event} />
              ))}
            </div>
          )}
        </ScrollArea>
      </CardContent>
    </Card>
  );
}
