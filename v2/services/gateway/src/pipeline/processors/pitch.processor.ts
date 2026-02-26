import { Processor } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { PipelineService } from '../pipeline.service';
import { BaseProcessor } from './base.processor';

@Processor('v2-pitch', { concurrency: 3 })
export class PitchProcessor extends BaseProcessor {
  constructor(pipelineService: PipelineService) {
    super(pipelineService, PitchProcessor.name);
  }

  protected async handle(job: Job): Promise<any> {
    const { prospectId, research } = job.data;

    const result = await this.callAiEngine('/api/pipeline/pitch', {
      prospect_id: prospectId,
      research_data: research,
    });

    // PITCHING -> EMAIL_SENT
    await this.pipelineService.advanceState(prospectId, result);
    return result;
  }
}
