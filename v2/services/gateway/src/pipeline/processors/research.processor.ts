import { Processor } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { PipelineService } from '../pipeline.service';
import { BaseProcessor } from './base.processor';

@Processor('v2-research', { concurrency: 3 })
export class ResearchProcessor extends BaseProcessor {
  constructor(pipelineService: PipelineService) {
    super(pipelineService, ResearchProcessor.name);
  }

  protected async handle(job: Job): Promise<any> {
    const { prospectId, name, email, company_domain } = job.data;

    const result = await this.callAiEngine('/api/pipeline/research', {
      prospect_id: prospectId,
      name,
      email,
      company_domain,
    });

    // RESEARCHING -> RESEARCHED -> PITCHING
    await this.pipelineService.advanceState(prospectId, result);
    return result;
  }
}
