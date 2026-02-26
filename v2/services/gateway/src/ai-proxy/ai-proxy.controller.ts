import {
  Controller,
  Get,
  Post,
  Body,
  Param,
  HttpException,
  HttpStatus,
} from '@nestjs/common';
import { AiProxyService } from './ai-proxy.service';

@Controller('ai')
export class AiProxyController {
  constructor(private readonly aiProxyService: AiProxyService) {}

  @Get('health')
  async aiHealth() {
    try {
      return await this.aiProxyService.healthCheck();
    } catch (error: any) {
      throw new HttpException(
        {
          status: 'error',
          message: 'AI Engine is not reachable',
          detail: error.message,
        },
        HttpStatus.SERVICE_UNAVAILABLE,
      );
    }
  }

  @Post('research/:prospectId')
  async research(@Param('prospectId') prospectId: string) {
    try {
      return await this.aiProxyService.research(prospectId);
    } catch (error: any) {
      throw new HttpException(
        { status: 'error', message: error.message },
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('pitch/:prospectId')
  async pitch(
    @Param('prospectId') prospectId: string,
    @Body() body: { model?: string },
  ) {
    try {
      return await this.aiProxyService.pitch(prospectId, body.model);
    } catch (error: any) {
      throw new HttpException(
        { status: 'error', message: error.message },
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('email')
  async email(@Body() data: Record<string, any>) {
    try {
      return await this.aiProxyService.email(data);
    } catch (error: any) {
      throw new HttpException(
        { status: 'error', message: error.message },
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('call')
  async call(@Body() data: Record<string, any>) {
    try {
      return await this.aiProxyService.call(data);
    } catch (error: any) {
      throw new HttpException(
        { status: 'error', message: error.message },
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }

  @Post('context/:prospectId')
  async buildContext(@Param('prospectId') prospectId: string) {
    try {
      return await this.aiProxyService.buildContext(prospectId);
    } catch (error: any) {
      throw new HttpException(
        { status: 'error', message: error.message },
        error.response?.status || HttpStatus.INTERNAL_SERVER_ERROR,
      );
    }
  }
}
