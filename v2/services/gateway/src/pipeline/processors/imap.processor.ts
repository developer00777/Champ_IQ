import { Processor } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { PipelineService } from '../pipeline.service';
import { BaseProcessor } from './base.processor';

@Processor('v2-imap', { concurrency: 2 })
export class ImapProcessor extends BaseProcessor {
  constructor(pipelineService: PipelineService) {
    super(pipelineService, ImapProcessor.name);
  }

  protected async handle(job: Job): Promise<any> {
    const { prospectId, prospectEmail, checkType } = job.data;

    const result = await this.callAiEngine(
      '/api/pipeline/imap-check',
      { prospect_id: prospectId, prospect_email: prospectEmail },
      60_000,
    );

    // WAITING_REPLY -> QUALIFYING_CALL | FOLLOW_UP_SENT
    // WAITING_FOLLOW_UP -> QUALIFYING_CALL | AUTO_CALL
    await this.pipelineService.advanceState(prospectId, {
      reply_found: result.reply_found,
      reply_content: result.reply_content ?? null,
      check_type: checkType,
    });
    return result;
  }
}
