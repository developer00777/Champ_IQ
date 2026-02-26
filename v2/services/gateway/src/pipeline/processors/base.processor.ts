import { Logger } from '@nestjs/common';
import { WorkerHost } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import axios from 'axios';
import { PipelineService } from '../pipeline.service';

/**
 * Base class for all V2 pipeline processors.
 *
 * Centralises:
 * - AI Engine URL and internal secret (single source of truth)
 * - Structured logging with timing
 * - Error handling + frontend error event emission
 * - callAiEngine() helper (adds X-Internal-Secret header automatically)
 *
 * Subclasses implement handle() instead of process().
 */
export abstract class BaseProcessor extends WorkerHost {
  protected readonly logger: Logger;

  private static readonly AI_ENGINE_URL =
    process.env.AI_ENGINE_URL || 'http://localhost:8001';

  private static readonly INTERNAL_SECRET =
    process.env.INTERNAL_SECRET || 'champiq-v2-internal-secret';

  constructor(
    protected readonly pipelineService: PipelineService,
    processorName: string,
  ) {
    super();
    this.logger = new Logger(processorName);
  }

  /**
   * POST to AI Engine with automatic auth header and configurable timeout.
   */
  protected async callAiEngine<T = any>(
    path: string,
    data: Record<string, any>,
    timeoutMs = 120_000,
  ): Promise<T> {
    const response = await axios.post<T>(
      `${BaseProcessor.AI_ENGINE_URL}${path}`,
      data,
      {
        timeout: timeoutMs,
        headers: {
          'X-Internal-Secret': BaseProcessor.INTERNAL_SECRET,
          'Content-Type': 'application/json',
        },
      },
    );
    return response.data;
  }

  /**
   * BullMQ entry point — wraps handle() with logging, timing, and error events.
   */
  async process(job: Job): Promise<any> {
    const startTime = Date.now();
    const prospectId = job.data?.prospectId ?? 'unknown';

    this.logger.log(
      `[${job.name}] Starting job ${job.id} for prospect ${prospectId} (attempt ${job.attemptsMade + 1})`,
    );

    try {
      const result = await this.handle(job);
      this.logger.log(
        `[${job.name}] Completed in ${Date.now() - startTime}ms`,
      );
      return result;
    } catch (error: any) {
      const duration = Date.now() - startTime;
      this.logger.error(
        `[${job.name}] Failed after ${duration}ms: ${error.message}`,
        error.stack,
      );
      // Emit pipeline error event to frontend via WebSocket
      if (prospectId !== 'unknown') {
        this.pipelineService.emitPipelineError(prospectId, job.name, error.message);
      }
      throw error;
    }
  }

  /**
   * Subclasses implement this instead of process().
   */
  protected abstract handle(job: Job): Promise<any>;
}
