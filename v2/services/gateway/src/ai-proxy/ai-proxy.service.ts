import { Injectable, Logger } from '@nestjs/common';
import axios, { AxiosInstance } from 'axios';

const AI_ENGINE_URL = process.env.AI_ENGINE_URL || 'http://localhost:8001';

@Injectable()
export class AiProxyService {
  private readonly logger = new Logger(AiProxyService.name);
  private readonly client: AxiosInstance;

  constructor() {
    this.client = axios.create({
      baseURL: AI_ENGINE_URL,
      timeout: 120000,
      headers: {
        'Content-Type': 'application/json',
      },
    });

    this.logger.log(`AI Proxy initialized, pointing to ${AI_ENGINE_URL}`);
  }

  /**
   * Call the AI Engine research endpoint.
   */
  async research(prospectId: string): Promise<any> {
    const response = await this.client.post('/api/pipeline/research', {
      prospect_id: prospectId,
    });
    return response.data;
  }

  /**
   * Call the AI Engine pitch endpoint.
   */
  async pitch(prospectId: string, model?: string): Promise<any> {
    const response = await this.client.post('/api/pipeline/pitch', {
      prospect_id: prospectId,
      model: model || undefined,
    });
    return response.data;
  }

  /**
   * Call the AI Engine email endpoint.
   */
  async email(data: Record<string, any>): Promise<any> {
    const response = await this.client.post('/api/pipeline/email/send', data);
    return response.data;
  }

  /**
   * Call the AI Engine call endpoint.
   */
  async call(data: Record<string, any>): Promise<any> {
    const response = await this.client.post('/api/pipeline/call', data);
    return response.data;
  }

  /**
   * Build context for a prospect (used for UI display).
   */
  async buildContext(prospectId: string): Promise<any> {
    const response = await this.client.post('/api/pipeline/context', {
      prospect_id: prospectId,
    });
    return response.data;
  }

  /**
   * Check AI Engine health.
   */
  async healthCheck(): Promise<any> {
    const response = await this.client.get('/health');
    return response.data;
  }

  /**
   * Generic proxy to forward any request to the AI Engine.
   */
  async proxy(
    method: string,
    path: string,
    data?: Record<string, any>,
  ): Promise<any> {
    const response = await this.client.request({
      method,
      url: path,
      data,
    });
    return response.data;
  }
}
