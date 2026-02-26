import { Controller, Get } from '@nestjs/common';
import { InjectDataSource } from '@nestjs/typeorm';
import { DataSource } from 'typeorm';
import Redis from 'ioredis';

@Controller()
export class HealthController {
  private readonly redis = new Redis({
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    db: 1,
    lazyConnect: true,
  });

  constructor(
    @InjectDataSource()
    private readonly dataSource: DataSource,
  ) {}

  @Get('health')
  health() {
    return {
      status: 'healthy',
      service: 'ChampIQ V2 Gateway',
      port: parseInt(process.env.PORT || '4001', 10),
      timestamp: new Date().toISOString(),
    };
  }

  @Get('health/ready')
  async ready() {
    const checks: Record<string, boolean> = { postgres: false, redis: false };
    const details: Record<string, string> = {};

    // PostgreSQL check
    try {
      await this.dataSource.query('SELECT 1');
      checks.postgres = true;
    } catch (err: any) {
      details.postgres = err.message;
    }

    // Redis check
    try {
      await this.redis.ping();
      checks.redis = true;
    } catch (err: any) {
      details.redis = err.message;
    }

    const ready = checks.postgres && checks.redis;

    return {
      ready,
      checks,
      ...(Object.keys(details).length > 0 ? { details } : {}),
      timestamp: new Date().toISOString(),
    };
  }
}
