import { Module } from '@nestjs/common';
import { AiProxyService } from './ai-proxy.service';
import { AiProxyController } from './ai-proxy.controller';
import { AuthModule } from '../auth/auth.module';

@Module({
  imports: [AuthModule],
  controllers: [AiProxyController],
  providers: [AiProxyService],
  exports: [AiProxyService],
})
export class AiProxyModule {}
