import { type ClassValue, clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';
import type { PipelineState, CHAMPTier } from '@/types';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export function getStateColor(state: PipelineState): string {
  switch (state) {
    case 'QUALIFIED':
    case 'INTERESTED':
      return 'text-green-400 bg-green-400/10 border-green-400/30';

    case 'RESEARCHING':
    case 'PITCHING':
    case 'EMAIL_SENT':
    case 'RESEARCHED':
    case 'FOLLOW_UP_SENT':
      return 'text-blue-400 bg-blue-400/10 border-blue-400/30';

    case 'WAITING_REPLY':
    case 'WAITING_FOLLOW_UP':
      return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30';

    case 'QUALIFYING_CALL':
    case 'SALES_CALL':
    case 'NURTURE_CALL':
    case 'AUTO_CALL':
      return 'text-purple-400 bg-purple-400/10 border-purple-400/30';

    case 'NOT_INTERESTED':
      return 'text-red-400 bg-red-400/10 border-red-400/30';

    case 'NEW':
    default:
      return 'text-gray-400 bg-gray-400/10 border-gray-400/30';
  }
}

export function getStateDotColor(state: PipelineState): string {
  switch (state) {
    case 'QUALIFIED':
    case 'INTERESTED':
      return 'bg-green-400';
    case 'RESEARCHING':
    case 'PITCHING':
    case 'EMAIL_SENT':
    case 'RESEARCHED':
    case 'FOLLOW_UP_SENT':
      return 'bg-blue-400';
    case 'WAITING_REPLY':
    case 'WAITING_FOLLOW_UP':
      return 'bg-yellow-400';
    case 'QUALIFYING_CALL':
    case 'SALES_CALL':
    case 'NURTURE_CALL':
    case 'AUTO_CALL':
      return 'bg-purple-400';
    case 'NOT_INTERESTED':
      return 'bg-red-400';
    case 'NEW':
    default:
      return 'bg-gray-400';
  }
}

export function getTierColor(tier: CHAMPTier): string {
  switch (tier) {
    case 'CHAMPION':
      return 'text-green-400 bg-green-400/10 border-green-400/30';
    case 'HOT':
      return 'text-orange-400 bg-orange-400/10 border-orange-400/30';
    case 'WARM':
      return 'text-yellow-400 bg-yellow-400/10 border-yellow-400/30';
    case 'COOL':
      return 'text-blue-400 bg-blue-400/10 border-blue-400/30';
    case 'COLD':
      return 'text-gray-400 bg-gray-400/10 border-gray-400/30';
    default:
      return 'text-gray-400 bg-gray-400/10 border-gray-400/30';
  }
}

export function formatPipelineState(state: PipelineState): string {
  return state
    .split('_')
    .map((word) => word.charAt(0) + word.slice(1).toLowerCase())
    .join(' ');
}

export function formatDate(dateString: string): string {
  const date = new Date(dateString);
  return date.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);
  const diffHours = Math.floor(diffMins / 60);
  const diffDays = Math.floor(diffHours / 24);

  if (diffMins < 1) return 'just now';
  if (diffMins < 60) return `${diffMins}m ago`;
  if (diffHours < 24) return `${diffHours}h ago`;
  if (diffDays < 7) return `${diffDays}d ago`;
  return formatDate(dateString);
}
