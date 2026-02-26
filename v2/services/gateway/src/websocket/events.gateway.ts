import {
  WebSocketGateway,
  WebSocketServer,
  OnGatewayInit,
  OnGatewayConnection,
  OnGatewayDisconnect,
} from '@nestjs/websockets';
import { Logger } from '@nestjs/common';
import { JwtService } from '@nestjs/jwt';
import { Server, Socket } from 'socket.io';
import { randomUUID } from 'crypto';

@WebSocketGateway({
  cors: {
    origin: process.env.FRONTEND_URL || 'http://localhost:3001',
    credentials: true,
  },
  namespace: '/',
})
export class EventsGateway
  implements OnGatewayInit, OnGatewayConnection, OnGatewayDisconnect
{
  @WebSocketServer()
  server: Server;

  private readonly logger = new Logger(EventsGateway.name);

  constructor(private readonly jwtService: JwtService) {}

  afterInit(): void {
    this.logger.log('WebSocket Gateway initialized');
  }

  async handleConnection(client: Socket): Promise<void> {
    const token = client.handshake.auth?.token as string | undefined;
    if (!token) {
      this.logger.warn(`Client ${client.id} disconnected: no token`);
      client.disconnect();
      return;
    }
    try {
      const payload = await this.jwtService.verifyAsync(token, {
        secret: process.env.JWT_SECRET || 'champiq-v2-secret',
      });
      client.join(`user:${payload.sub}`);
      this.logger.log(`Client connected: ${client.id} (user ${payload.sub})`);
    } catch {
      this.logger.warn(`Client ${client.id} disconnected: invalid token`);
      client.disconnect();
    }
  }

  handleDisconnect(client: Socket): void {
    this.logger.log(`Client disconnected: ${client.id}`);
  }

  /**
   * Emit a pipeline state change event to all connected clients.
   */
  emitStateChange(
    prospectId: string,
    newState: string,
    data?: Record<string, any>,
  ): void {
    this.server.emit('pipeline:state_changed', {
      prospectId,
      newState,
      data: data || {},
      timestamp: new Date().toISOString(),
    });
    this.logger.log(
      `Emitted pipeline:state_changed for prospect ${prospectId} -> ${newState}`,
    );
  }

  /**
   * Emit an activity event to all connected clients.
   * Matches the frontend ActivityEvent type shape.
   */
  emitActivity(
    prospectId: string,
    eventType: string,
    message: string,
    details?: Record<string, any>,
    prospectName?: string,
  ): void {
    this.server.emit('activity', {
      id: randomUUID(),
      type: eventType,
      prospect_id: prospectId,
      prospect_name: prospectName || '',
      message,
      data: details || {},
      created_at: new Date().toISOString(),
    });
  }

  /**
   * Emit a pipeline error event to all connected clients.
   */
  emitError(
    prospectId: string,
    stage: string,
    error: string,
  ): void {
    this.server.emit('pipeline:error', {
      prospectId,
      stage,
      error,
      timestamp: new Date().toISOString(),
    });
  }
}
