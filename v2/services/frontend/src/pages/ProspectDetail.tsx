import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { prospectApi, activityApi } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { PipelineStatusBar } from '@/components/pipeline/PipelineStatusBar';
import { StageCard } from '@/components/pipeline/StageCard';
import { ActivityLog } from '@/components/activity/ActivityLog';
import {
  cn,
  getStateColor,
  getTierColor,
  formatPipelineState,
  formatDate,
} from '@/lib/utils';
import { PIPELINE_STATES } from '@/types';
import type { PipelineState } from '@/types';
import {
  ArrowLeft,
  Mail,
  Phone,
  Globe,
  Briefcase,
  BarChart3,
} from 'lucide-react';

export default function ProspectDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const {
    data: prospect,
    isLoading,
    error,
  } = useQuery({
    queryKey: ['prospect', id],
    queryFn: () => prospectApi.get(id!),
    enabled: !!id,
    refetchInterval: 60_000, // WebSocket invalidation handles real-time; this is a fallback
  });

  const { data: activityEvents } = useQuery({
    queryKey: ['activity', id],
    queryFn: () => activityApi.getRecent({ prospect_id: id, limit: 50 }),
    enabled: !!id,
    refetchInterval: 60_000,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  if (error || !prospect) {
    return (
      <div className="text-center py-20">
        <p className="text-muted-foreground">Prospect not found.</p>
        <Button variant="outline" className="mt-4" onClick={() => navigate('/')}>
          Back to Dashboard
        </Button>
      </div>
    );
  }

  const currentStateIndex = PIPELINE_STATES.indexOf(prospect.pipeline_state);
  const completedStates = PIPELINE_STATES.slice(0, currentStateIndex);
  const stageTimestamps = prospect.pipeline_data?.stage_timestamps;

  return (
    <div className="space-y-6">
      {/* Back button */}
      <Button
        variant="ghost"
        size="sm"
        onClick={() => navigate('/')}
        className="gap-1"
      >
        <ArrowLeft className="h-4 w-4" />
        Back to Dashboard
      </Button>

      {/* Header */}
      <Card>
        <CardHeader>
          <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
            <div className="space-y-1">
              <div className="flex items-center gap-3">
                <CardTitle className="text-xl">{prospect.name}</CardTitle>
                {prospect.champ_score?.tier && (
                  <Badge
                    variant="outline"
                    className={cn(getTierColor(prospect.champ_score.tier))}
                  >
                    {prospect.champ_score.tier}
                    {prospect.champ_score.total !== undefined &&
                      ` (${prospect.champ_score.total})`}
                  </Badge>
                )}
              </div>
              <div className="flex flex-wrap items-center gap-4 text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <Mail className="h-3.5 w-3.5" />
                  {prospect.email}
                </span>
                {prospect.phone && (
                  <span className="flex items-center gap-1">
                    <Phone className="h-3.5 w-3.5" />
                    {prospect.phone}
                  </span>
                )}
                {prospect.company_domain && (
                  <span className="flex items-center gap-1">
                    <Globe className="h-3.5 w-3.5" />
                    {prospect.company_domain}
                  </span>
                )}
                {prospect.title && (
                  <span className="flex items-center gap-1">
                    <Briefcase className="h-3.5 w-3.5" />
                    {prospect.title}
                  </span>
                )}
              </div>
            </div>
            <div className="flex items-center gap-2">
              <Badge
                variant="outline"
                className={cn(
                  'text-sm',
                  getStateColor(prospect.pipeline_state),
                )}
              >
                {formatPipelineState(prospect.pipeline_state)}
              </Badge>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <p className="text-xs text-muted-foreground">
            Created {formatDate(prospect.created_at)} -- Last updated{' '}
            {formatDate(prospect.updated_at)}
          </p>
        </CardContent>
      </Card>

      {/* Pipeline Status Bar */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            Pipeline Progress
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto pb-2">
            <PipelineStatusBar
              currentState={prospect.pipeline_state}
              stageTimestamps={stageTimestamps as Record<string, string>}
            />
          </div>
        </CardContent>
      </Card>

      {/* Stage Cards + Activity */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Stage Details */}
        <div className="lg:col-span-2 space-y-3">
          <h3 className="text-sm font-medium text-muted-foreground">
            Stage Details
          </h3>

          {/* Current stage card */}
          <StageCard
            state={prospect.pipeline_state}
            isCurrent={true}
            timestamp={stageTimestamps?.[prospect.pipeline_state]}
            pipelineData={prospect.pipeline_data}
          />

          {/* CHAMP Score Breakdown */}
          {prospect.champ_score && (
            <Card>
              <CardHeader className="pb-2">
                <CardTitle className="text-base">CHAMP Score Breakdown</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="grid grid-cols-2 gap-3">
                  <ScoreItem
                    label="Challenges"
                    value={prospect.champ_score.challenges}
                  />
                  <ScoreItem
                    label="Authority"
                    value={prospect.champ_score.authority}
                  />
                  <ScoreItem
                    label="Money"
                    value={prospect.champ_score.money}
                  />
                  <ScoreItem
                    label="Prioritization"
                    value={prospect.champ_score.prioritization}
                  />
                </div>
                <Separator className="my-3" />
                <div className="flex items-center justify-between">
                  <span className="text-sm font-medium">Total</span>
                  <span className="text-lg font-bold">
                    {prospect.champ_score.total}
                  </span>
                </div>
              </CardContent>
            </Card>
          )}

          {/* Completed stage cards */}
          {completedStates.length > 0 && (
            <>
              <h3 className="text-sm font-medium text-muted-foreground mt-4">
                Completed Stages
              </h3>
              {[...completedStates].reverse().map((state) => (
                <StageCard
                  key={state}
                  state={state as PipelineState}
                  isCurrent={false}
                  timestamp={stageTimestamps?.[state]}
                  pipelineData={prospect.pipeline_data}
                />
              ))}
            </>
          )}
        </div>

        {/* Activity for this prospect */}
        <div>
          <ActivityLog
            prospectId={id}
            title="Prospect Activity"
            maxHeight="600px"
            events={activityEvents}
          />
        </div>
      </div>
    </div>
  );
}

function ScoreItem({ label, value }: { label: string; value: number }) {
  const maxValue = 25;
  const percentage = Math.min((value / maxValue) * 100, 100);

  return (
    <div>
      <div className="flex items-center justify-between text-sm mb-1">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-medium">{value}</span>
      </div>
      <div className="h-2 bg-muted rounded-full overflow-hidden">
        <div
          className="h-full bg-primary rounded-full transition-all"
          style={{ width: `${percentage}%` }}
        />
      </div>
    </div>
  );
}
