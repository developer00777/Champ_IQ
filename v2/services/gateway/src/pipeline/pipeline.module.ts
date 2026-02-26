import { Module } from '@nestjs/common';
import { BullModule } from '@nestjs/bullmq';
import { TypeOrmModule } from '@nestjs/typeorm';
import { Prospect } from '../prospects/entities/prospect.entity';
import { PipelineService } from './pipeline.service';
import { ResearchProcessor } from './processors/research.processor';
import { PitchProcessor } from './processors/pitch.processor';
import { EmailProcessor } from './processors/email.processor';
import { ImapProcessor } from './processors/imap.processor';
import { CallProcessor } from './processors/call.processor';
import { SettingsModule } from '../settings/settings.module';

/** 7 days in seconds for failed job retention */
const FAILED_JOB_TTL = 7 * 24 * 3600;

@Module({
  imports: [
    BullModule.registerQueue(
      {
        name: 'v2-research',
        defaultJobOptions: {
          attempts: 3,
          backoff: { type: 'exponential', delay: 10_000 },
          removeOnComplete: { count: 200 },
          removeOnFail: { count: 500, age: FAILED_JOB_TTL },
        },
      },
      {
        name: 'v2-pitch',
        defaultJobOptions: {
          attempts: 3,
          backoff: { type: 'exponential', delay: 5_000 },
          removeOnComplete: { count: 200 },
          removeOnFail: { count: 500, age: FAILED_JOB_TTL },
        },
      },
      {
        name: 'v2-email',
        defaultJobOptions: {
          attempts: 2,
          backoff: { type: 'fixed', delay: 30_000 },
          removeOnComplete: { count: 500 },
          removeOnFail: { count: 500, age: FAILED_JOB_TTL },
        },
      },
      {
        name: 'v2-imap',
        defaultJobOptions: {
          attempts: 3,
          backoff: { type: 'exponential', delay: 60_000 },
          removeOnComplete: { count: 200 },
          removeOnFail: { count: 200 },
        },
      },
      {
        name: 'v2-call',
        defaultJobOptions: {
          attempts: 2,
          backoff: { type: 'fixed', delay: 60_000 },
          removeOnComplete: { count: 200 },
          removeOnFail: { count: 500, age: FAILED_JOB_TTL },
        },
      },
    ),
    TypeOrmModule.forFeature([Prospect]),
    SettingsModule,
  ],
  providers: [
    PipelineService,
    ResearchProcessor,
    PitchProcessor,
    EmailProcessor,
    ImapProcessor,
    CallProcessor,
  ],
  exports: [PipelineService],
})
export class PipelineModule {}
