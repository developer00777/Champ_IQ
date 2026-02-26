import { Processor } from '@nestjs/bullmq';
import { Job } from 'bullmq';
import { PipelineService } from '../pipeline.service';
import { BaseProcessor } from './base.processor';

@Processor('v2-call', { concurrency: 2 })
export class CallProcessor extends BaseProcessor {
  constructor(pipelineService: PipelineService) {
    super(pipelineService, CallProcessor.name);
  }

  protected async handle(job: Job): Promise<any> {
    const { prospectId, phone, callType, replyContent, autoCallResult } = job.data;

    // Map callType to the agent_type the AI engine expects
    const agentTypeMap: Record<string, string> = {
      qualifying: 'qualifier',
      sales: 'sales',
      nurture: 'nurture',
      auto: 'auto',
    };
    const agentType = agentTypeMap[callType] ?? 'qualifier';

    // Build context summary from reply/auto-call data if available
    const contextParts: string[] = [];
    if (replyContent) contextParts.push(`Prospect replied: ${replyContent}`);
    if (autoCallResult) contextParts.push(`Auto-call result: ${JSON.stringify(autoCallResult)}`);
    const contextSummary = contextParts.length ? contextParts.join('\n') : null;

    // Voice calls can take up to 2 minutes (reduced from 5)
    const result = await this.callAiEngine(
      '/api/pipeline/call',
      {
        prospect_id: prospectId,
        phone_number: phone,
        agent_type: agentType,
        context_summary: contextSummary,
      },
      180_000, // 3 min timeout (voice call max poll = 12 * 10s = 2 min + buffer)
    );

    // qualifying -> INTERESTED/NOT_INTERESTED, sales -> QUALIFIED, nurture -> SALES_CALL, auto -> QUALIFYING_CALL
    await this.pipelineService.advanceState(prospectId, {
      ...result,
      call_type: callType,
    });
    return result;
  }
}
