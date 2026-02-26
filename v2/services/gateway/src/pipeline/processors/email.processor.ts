import { Processor } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { PipelineService } from '../pipeline.service';
import { BaseProcessor } from './base.processor';

@Processor('v2-email', { concurrency: 5 })
export class EmailProcessor extends BaseProcessor {
  constructor(pipelineService: PipelineService) {
    super(pipelineService, EmailProcessor.name);
  }

  protected async handle(job: Job): Promise<any> {
    const { prospectId, email, name, followUp } = job.data;

    const result = await this.callAiEngine(
      '/api/pipeline/email',
      {
        prospect_id: prospectId,
        to_email: email,
        to_name: name ?? null,
        variant: followUp ? 'follow_up' : 'primary',
      },
      60_000,
    );

    // EMAIL_SENT -> WAITING_REPLY  or  FOLLOW_UP_SENT -> WAITING_FOLLOW_UP
    await this.pipelineService.advanceState(prospectId, {
      ...result,
      email_type: followUp ? 'follow_up' : 'initial',
    });
    return result;
  }
}
