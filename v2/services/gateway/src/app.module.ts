import { Module } from '@nestjs/common';
import { TypeOrmModule } from '@nestjs/typeorm';
import { BullModule } from '@nestjs/bullmq';
import { AuthModule } from './auth/auth.module';
import { ProspectsModule } from './prospects/prospects.module';
import { PipelineModule } from './pipeline/pipeline.module';
import { AiProxyModule } from './ai-proxy/ai-proxy.module';
import { WebsocketModule } from './websocket/websocket.module';
import { SettingsModule } from './settings/settings.module';
import { ActivityModule } from './activity/activity.module';
import { HealthController } from './health.controller';

@Module({
  imports: [
    TypeOrmModule.forRoot({
      type: 'postgres',
      host: process.env.POSTGRES_HOST || 'localhost',
      port: parseInt(process.env.POSTGRES_PORT || '5432'),
      username: process.env.POSTGRES_USER || 'postgres',
      password: process.env.POSTGRES_PASSWORD || 'postgres',
      database: process.env.POSTGRES_DB || 'champiq_v2',
      autoLoadEntities: true,
      synchronize: process.env.NODE_ENV !== 'production',
    }),
    BullModule.forRoot({
      connection: {
        host: process.env.REDIS_HOST || 'localhost',
        port: parseInt(process.env.REDIS_PORT || '6379'),
        db: 1,
      },
    }),
    AuthModule,
    ProspectsModule,
    PipelineModule,
    AiProxyModule,
    WebsocketModule,
    SettingsModule,
    ActivityModule,
  ],
  controllers: [HealthController],
})
export class AppModule {}
