import {
  Injectable,
  Logger,
  NotFoundException,
  ConflictException,
} from '@nestjs/common';
import { InjectRepository, InjectDataSource } from '@nestjs/typeorm';
import { Repository, DataSource } from 'typeorm';
import { InjectQueue } from '@nestjs/bullmq';
import { Queue } from 'bullmq';
import { randomUUID } from 'crypto';
import Redis from 'ioredis';
import axios from 'axios';
import { Prospect } from '../prospects/entities/prospect.entity';
import { EventsGateway } from '../websocket/events.gateway';
import { SettingsService } from '../settings/settings.service';

const AI_ENGINE_URL = process.env.AI_ENGINE_URL || 'http://ai-engine-v2:8001';
const INTERNAL_SECRET = process.env.INTERNAL_SECRET || 'champiq-v2-internal-secret';

/**
 * V2 Pipeline States:
 * NEW -> RESEARCHING -> RESEARCHED -> PITCHING -> EMAIL_SENT ->
 * WAITING_REPLY -> FOLLOW_UP_SENT -> WAITING_FOLLOW_UP ->
 * QUALIFYING_CALL -> INTERESTED / NOT_INTERESTED ->
 * SALES_CALL / NURTURE_CALL / AUTO_CALL -> QUALIFIED
 */
export enum PipelineState {
  NEW = 'new',
  RESEARCHING = 'researching',
  RESEARCHED = 'researched',
  PITCHING = 'pitching',
  EMAIL_SENT = 'email_sent',
  WAITING_REPLY = 'waiting_reply',
  FOLLOW_UP_SENT = 'follow_up_sent',
  WAITING_FOLLOW_UP = 'waiting_follow_up',
  QUALIFYING_CALL = 'qualifying_call',
  INTERESTED = 'interested',
  NOT_INTERESTED = 'not_interested',
  SALES_CALL = 'sales_call',
  NURTURE_CALL = 'nurture_call',
  AUTO_CALL = 'auto_call',
  QUALIFIED = 'qualified',
}

@Injectable()
export class PipelineService {
  private readonly logger = new Logger(PipelineService.name);

  /** Redis client for distributed locks and rate limiting (DB 1, same as BullMQ). */
  private readonly redis = new Redis({
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    db: 1,
  });

  constructor(
    @InjectRepository(Prospect)
    private readonly prospectRepo: Repository<Prospect>,
    @InjectDataSource()
    private readonly dataSource: DataSource,
    @InjectQueue('v2-research') private readonly researchQueue: Queue,
    @InjectQueue('v2-pitch') private readonly pitchQueue: Queue,
    @InjectQueue('v2-email') private readonly emailQueue: Queue,
    @InjectQueue('v2-imap') private readonly imapQueue: Queue,
    @InjectQueue('v2-call') private readonly callQueue: Queue,
    private readonly eventsGateway: EventsGateway,
    private readonly settingsService: SettingsService,
  ) {}

  /**
   * Kick off the pipeline from NEW state.
   */
  async startPipeline(prospectId: string): Promise<void> {
    const prospect = await this.getProspect(prospectId);

    if (prospect.pipeline_state !== PipelineState.NEW) {
      this.logger.warn(
        `Prospect ${prospectId} is in state "${prospect.pipeline_state}", resetting to NEW`,
      );
    }

    // Sync prospect into Neo4j so the AI Engine can find it by ID
    try {
      await axios.post(
        `${AI_ENGINE_URL}/api/prospects`,
        {
          id: prospect.id,
          name: prospect.name,
          email: prospect.email,
          phone: prospect.phone,
          company_domain: prospect.company_domain,
          title: prospect.title,
          pipeline_state: prospect.pipeline_state,
        },
        {
          headers: { 'X-Internal-Secret': INTERNAL_SECRET },
          timeout: 15_000,
        },
      );
      this.logger.log(`Prospect ${prospectId} synced to Neo4j`);
    } catch (err: any) {
      this.logger.error(`Failed to sync prospect to Neo4j: ${err.message}`);
      throw err;
    }

    await this.transitionTo(prospect, PipelineState.RESEARCHING);
    await this.researchQueue.add('research', {
      prospectId,
      name: prospect.name,
      email: prospect.email,
      company_domain: prospect.company_domain,
    });

    this.logger.log(`Pipeline started for prospect ${prospectId}`);
  }

  /**
   * Called by processors when a stage completes. Determines and executes the next transition.
   * Protected by a Redis distributed lock to prevent race conditions from concurrent BullMQ jobs.
   */
  async advanceState(
    prospectId: string,
    result?: Record<string, any>,
  ): Promise<void> {
    const lockKey = `pipeline:lock:${prospectId}`;
    const lockId = randomUUID();

    // Acquire distributed lock (30s TTL, NX = only set if not exists)
    const acquired = await this.redis.set(lockKey, lockId, 'EX', 30, 'NX');
    if (!acquired) {
      throw new ConflictException(
        `Pipeline transition already in progress for prospect ${prospectId}`,
      );
    }

    try {
      await this._doAdvanceState(prospectId, result);
    } finally {
      // Release lock only if we still own it (prevents stale lock release)
      const currentOwner = await this.redis.get(lockKey);
      if (currentOwner === lockId) {
        await this.redis.del(lockKey);
      }
    }
  }

  /**
   * Internal state machine logic (called while lock is held).
   */
  private async _doAdvanceState(
    prospectId: string,
    result?: Record<string, any>,
  ): Promise<void> {
    const prospect = await this.getProspect(prospectId);
    const currentState = prospect.pipeline_state;

    this.logger.log(
      `Advancing state for prospect ${prospectId} from "${currentState}"`,
    );

    // Read configurable IMAP wait hours from SettingsService
    const imapWaitHours = this.settingsService.get('imap_wait_hours') ?? 24;
    const followUpWaitHours = imapWaitHours * 2;

    switch (currentState) {
      case PipelineState.RESEARCHING: {
        await this.transitionTo(prospect, PipelineState.RESEARCHED, result);
        const updated = await this.getProspect(prospectId);
        await this.transitionTo(updated, PipelineState.PITCHING);
        await this.pitchQueue.add('pitch', { prospectId, research: result });
        break;
      }

      case PipelineState.PITCHING: {
        await this.transitionTo(prospect, PipelineState.EMAIL_SENT, result);
        await this.emailQueue.add('send-email', {
          prospectId,
          email: prospect.email,
          name: prospect.name,
          pitch: result,
        });
        break;
      }

      case PipelineState.EMAIL_SENT: {
        await this.transitionTo(prospect, PipelineState.WAITING_REPLY, result);
        await this.imapQueue.add(
          'check-reply',
          {
            prospectId,
            prospectEmail: prospect.email,
            checkType: 'initial',
            email_sent_at: new Date().toISOString(),
          },
          { delay: imapWaitHours * 60 * 60 * 1000 },
        );
        break;
      }

      case PipelineState.WAITING_REPLY: {
        if (result?.reply_found) {
          await this.transitionTo(prospect, PipelineState.QUALIFYING_CALL, result);
          await this.callQueue.add('qualifying-call', {
            prospectId,
            phone: prospect.phone,
            callType: 'qualifying',
            replyContent: result.reply_content,
          });
        } else {
          await this.transitionTo(prospect, PipelineState.FOLLOW_UP_SENT, result);
          await this.emailQueue.add('send-follow-up', {
            prospectId,
            email: prospect.email,
            name: prospect.name,
            followUp: true,
          });
        }
        break;
      }

      case PipelineState.FOLLOW_UP_SENT: {
        await this.transitionTo(prospect, PipelineState.WAITING_FOLLOW_UP, result);
        await this.imapQueue.add(
          'check-follow-up-reply',
          {
            prospectId,
            prospectEmail: prospect.email,
            checkType: 'follow_up',
            email_sent_at: new Date().toISOString(),
          },
          { delay: followUpWaitHours * 60 * 60 * 1000 },
        );
        break;
      }

      case PipelineState.WAITING_FOLLOW_UP: {
        if (result?.reply_found) {
          await this.transitionTo(prospect, PipelineState.QUALIFYING_CALL, result);
          await this.callQueue.add('qualifying-call', {
            prospectId,
            phone: prospect.phone,
            callType: 'qualifying',
            replyContent: result.reply_content,
          });
        } else {
          await this.transitionTo(prospect, PipelineState.AUTO_CALL, result);
          await this.callQueue.add('auto-call', {
            prospectId,
            phone: prospect.phone,
            callType: 'auto',
          });
        }
        break;
      }

      case PipelineState.QUALIFYING_CALL: {
        if (result?.interested) {
          await this.transitionTo(prospect, PipelineState.INTERESTED, result);
          const updatedInterested = await this.getProspect(prospectId);
          await this.transitionTo(updatedInterested, PipelineState.SALES_CALL);
          await this.callQueue.add('sales-call', {
            prospectId,
            phone: prospect.phone,
            callType: 'sales',
          });
        } else {
          await this.transitionTo(prospect, PipelineState.NOT_INTERESTED, result);
          const updatedNotInterested = await this.getProspect(prospectId);
          await this.transitionTo(updatedNotInterested, PipelineState.NURTURE_CALL);
          await this.callQueue.add('nurture-call', {
            prospectId,
            phone: prospect.phone,
            callType: 'nurture',
          });
        }
        break;
      }

      case PipelineState.SALES_CALL: {
        await this.transitionTo(prospect, PipelineState.QUALIFIED, result);
        this.logger.log(`Prospect ${prospectId} is now QUALIFIED`);
        break;
      }

      case PipelineState.NURTURE_CALL: {
        await this.transitionTo(prospect, PipelineState.SALES_CALL, result);
        await this.callQueue.add('sales-call', {
          prospectId,
          phone: prospect.phone,
          callType: 'sales',
        });
        break;
      }

      case PipelineState.AUTO_CALL: {
        await this.transitionTo(prospect, PipelineState.QUALIFYING_CALL, result);
        await this.callQueue.add('qualifying-call', {
          prospectId,
          phone: prospect.phone,
          callType: 'qualifying',
          autoCallResult: result,
        });
        break;
      }

      case PipelineState.QUALIFIED: {
        this.logger.log(
          `Prospect ${prospectId} already QUALIFIED. No further transitions.`,
        );
        break;
      }

      default: {
        this.logger.warn(
          `Unknown state "${currentState}" for prospect ${prospectId}`,
        );
        break;
      }
    }
  }

  /**
   * Emit a pipeline error event to frontend via WebSocket.
   * Called by BaseProcessor on job failure.
   */
  emitPipelineError(prospectId: string, stage: string, error: string): void {
    this.eventsGateway.emitError(prospectId, stage, error);
  }

  /**
   * Transition a prospect to a new state.
   * Persists to PostgreSQL inside a transaction, then emits WebSocket events.
   */
  private async transitionTo(
    prospect: Prospect,
    newState: string,
    data?: Record<string, any>,
  ): Promise<void> {
    const oldState = prospect.pipeline_state;

    prospect.pipeline_state = newState;
    prospect.pipeline_data = {
      ...(prospect.pipeline_data || {}),
      ...(data || {}),
      [`${newState}_at`]: new Date().toISOString(),
      last_transition: `${oldState} -> ${newState}`,
    };

    // Persist in a transaction for atomicity
    const queryRunner = this.dataSource.createQueryRunner();
    await queryRunner.connect();
    await queryRunner.startTransaction();
    try {
      await queryRunner.manager.save(Prospect, prospect);
      await queryRunner.commitTransaction();
    } catch (err) {
      await queryRunner.rollbackTransaction();
      throw err;
    } finally {
      await queryRunner.release();
    }

    this.logger.log(`Prospect ${prospect.id}: ${oldState} -> ${newState}`);

    this.eventsGateway.emitStateChange(prospect.id, newState, {
      oldState,
      pipeline_data: prospect.pipeline_data,
    });

    this.eventsGateway.emitActivity(
      prospect.id,
      'state_changed',
      `Pipeline moved from ${oldState} to ${newState}`,
      { from: oldState, to: newState },
      prospect.name,
    );
  }

  /**
   * Fetch a prospect by ID or throw NotFoundException.
   */
  private async getProspect(prospectId: string): Promise<Prospect> {
    const prospect = await this.prospectRepo.findOne({
      where: { id: prospectId },
    });
    if (!prospect) {
      throw new NotFoundException(
        `Prospect with ID "${prospectId}" not found`,
      );
    }
    return prospect;
  }
}
