import { create } from 'zustand';
import { io, Socket } from 'socket.io-client';
import type { ActivityEvent } from '@/types';
import { activityApi } from '@/api/client';
import { queryClient } from '@/main';

interface ActivityState {
  events: ActivityEvent[];
  isConnected: boolean;
  socket: Socket | null;

  fetchRecent: (limit?: number) => Promise<void>;
  connect: () => void;
  disconnect: () => void;
  addEvent: (event: ActivityEvent) => void;
}

export const useActivityStore = create<ActivityState>((set, get) => ({
  events: [],
  isConnected: false,
  socket: null,

  fetchRecent: async (limit = 50) => {
    try {
      const events = await activityApi.getRecent({ limit });
      set({ events });
    } catch (err) {
      console.error('Failed to fetch activity events:', err);
    }
  },

  connect: () => {
    if (get().socket) return;

    // Cookie-based auth — no token in handshake; gateway reads httpOnly cookie
    const socket = io('/', {
      path: '/socket.io',
      withCredentials: true,
      transports: ['websocket', 'polling'],
    });

    socket.on('connect', () => {
      set({ isConnected: true });
    });

    socket.on('disconnect', () => {
      set({ isConnected: false });
    });

    socket.on('activity', (event: ActivityEvent) => {
      get().addEvent(event);
    });

    socket.on('pipeline:state_changed', () => {
      // Invalidate prospect queries so Dashboard + ProspectDetail refresh
      queryClient.invalidateQueries({ queryKey: ['prospects'] });
      get().fetchRecent();
    });

    set({ socket });
  },

  disconnect: () => {
    const { socket } = get();
    if (socket) {
      socket.disconnect();
      set({ socket: null, isConnected: false });
    }
  },

  addEvent: (event: ActivityEvent) => {
    set((state) => ({
      events: [event, ...state.events].slice(0, 200),
    }));
  },
}));
