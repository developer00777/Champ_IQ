import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { prospectApi } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { ActivityLog } from '@/components/activity/ActivityLog';
import {
  cn,
  getStateColor,
  getTierColor,
  formatPipelineState,
  formatRelativeTime,
} from '@/lib/utils';
import { PIPELINE_STATES } from '@/types';
import type { Prospect, CHAMPTier } from '@/types';
import {
  Users,
  TrendingUp,
  CheckCircle,
  UserPlus,
  ArrowRight,
} from 'lucide-react';

export default function Dashboard() {
  const navigate = useNavigate();

  const { data: prospectData, isLoading } = useQuery({
    queryKey: ['prospects'],
    queryFn: () => prospectApi.list({ per_page: 100 }),
    refetchInterval: 60_000, // WebSocket invalidation handles real-time; this is a fallback
  });

  const prospects = prospectData?.data || [];
  const total = prospectData?.total || 0;

  // Calculate stats
  const inPipeline = prospects.filter(
    (p) => p.pipeline_state !== 'NEW' && p.pipeline_state !== 'QUALIFIED',
  ).length;
  const qualified = prospects.filter(
    (p) => p.pipeline_state === 'QUALIFIED',
  ).length;

  // CHAMP tier breakdown
  const tierCounts: Record<CHAMPTier, number> = {
    CHAMPION: 0,
    HOT: 0,
    WARM: 0,
    COOL: 0,
    COLD: 0,
  };
  prospects.forEach((p) => {
    if (p.champ_score?.tier) {
      tierCounts[p.champ_score.tier]++;
    }
  });

  // Pipeline state distribution
  const stateCounts: Record<string, number> = {};
  PIPELINE_STATES.forEach((s) => {
    const count = prospects.filter((p) => p.pipeline_state === s).length;
    if (count > 0) stateCounts[s] = count;
  });

  return (
    <div className="space-y-6">
      {/* Stats Row */}
      <div className="grid gap-4 grid-cols-2 lg:grid-cols-4">
        <StatCard
          title="Total Prospects"
          value={total}
          icon={<Users className="h-4 w-4 text-muted-foreground" />}
        />
        <StatCard
          title="In Pipeline"
          value={inPipeline}
          icon={<TrendingUp className="h-4 w-4 text-blue-400" />}
        />
        <StatCard
          title="Qualified"
          value={qualified}
          icon={<CheckCircle className="h-4 w-4 text-green-400" />}
        />
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">CHAMP Tiers</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(tierCounts) as CHAMPTier[]).map(
                (tier) =>
                  tierCounts[tier] > 0 && (
                    <Badge
                      key={tier}
                      variant="outline"
                      className={cn('text-xs', getTierColor(tier))}
                    >
                      {tier}: {tierCounts[tier]}
                    </Badge>
                  ),
              )}
              {Object.values(tierCounts).every((c) => c === 0) && (
                <span className="text-sm text-muted-foreground">No scores yet</span>
              )}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Main Content */}
      <div className="grid gap-6 lg:grid-cols-3">
        {/* Prospect List */}
        <div className="lg:col-span-2">
          <Card>
            <CardHeader className="flex flex-row items-center justify-between">
              <CardTitle className="text-base">Prospects</CardTitle>
              <Button
                size="sm"
                onClick={() => navigate('/add-prospect')}
                className="gap-1"
              >
                <UserPlus className="h-4 w-4" />
                Add Prospect
              </Button>
            </CardHeader>
            <CardContent className="pt-0">
              {isLoading ? (
                <div className="flex items-center justify-center py-8">
                  <div className="animate-spin rounded-full h-6 w-6 border-b-2 border-primary" />
                </div>
              ) : prospects.length === 0 ? (
                <div className="text-center py-12">
                  <Users className="h-12 w-12 text-muted-foreground/30 mx-auto mb-3" />
                  <p className="text-sm text-muted-foreground">
                    No prospects yet. Add your first prospect to get started.
                  </p>
                  <Button
                    variant="outline"
                    size="sm"
                    className="mt-4"
                    onClick={() => navigate('/add-prospect')}
                  >
                    <UserPlus className="h-4 w-4 mr-2" />
                    Add Prospect
                  </Button>
                </div>
              ) : (
                <ScrollArea style={{ maxHeight: '500px' }}>
                  <div className="space-y-1">
                    {prospects.map((prospect) => (
                      <ProspectRow
                        key={prospect.id}
                        prospect={prospect}
                        onClick={() => navigate(`/prospects/${prospect.id}`)}
                      />
                    ))}
                  </div>
                </ScrollArea>
              )}
            </CardContent>
          </Card>

          {/* Pipeline State Distribution */}
          {Object.keys(stateCounts).length > 0 && (
            <Card className="mt-4">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Pipeline Distribution</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2">
                  {Object.entries(stateCounts).map(([state, count]) => (
                    <Badge
                      key={state}
                      variant="outline"
                      className={cn(
                        'text-xs',
                        getStateColor(state as typeof PIPELINE_STATES[number]),
                      )}
                    >
                      {formatPipelineState(state as typeof PIPELINE_STATES[number])}:{' '}
                      {count}
                    </Badge>
                  ))}
                </div>
              </CardContent>
            </Card>
          )}
        </div>

        {/* Activity Log */}
        <div>
          <ActivityLog maxHeight="600px" />
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  icon,
}: {
  title: string;
  value: number;
  icon: React.ReactNode;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium">{title}</CardTitle>
        {icon}
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
      </CardContent>
    </Card>
  );
}

function ProspectRow({
  prospect,
  onClick,
}: {
  prospect: Prospect;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className="w-full flex items-center gap-3 p-3 rounded-md hover:bg-muted/50 transition-colors text-left"
    >
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <p className="font-medium text-sm truncate">{prospect.name}</p>
          {prospect.champ_score?.tier && (
            <Badge
              variant="outline"
              className={cn(
                'text-[10px] shrink-0',
                getTierColor(prospect.champ_score.tier),
              )}
            >
              {prospect.champ_score.tier}
            </Badge>
          )}
        </div>
        <p className="text-xs text-muted-foreground truncate">
          {prospect.email}
          {prospect.title && ` -- ${prospect.title}`}
        </p>
      </div>
      <div className="flex items-center gap-2 shrink-0">
        <Badge
          variant="outline"
          className={cn('text-[10px]', getStateColor(prospect.pipeline_state))}
        >
          {formatPipelineState(prospect.pipeline_state)}
        </Badge>
        <span className="text-xs text-muted-foreground">
          {formatRelativeTime(prospect.updated_at)}
        </span>
        <ArrowRight className="h-4 w-4 text-muted-foreground" />
      </div>
    </button>
  );
}
