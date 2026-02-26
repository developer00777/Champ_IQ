import {
  Controller,
  Get,
  Query,
} from '@nestjs/common';
import { ActivityService } from './activity.service';

@Controller('activity')
export class ActivityController {
  constructor(private readonly activityService: ActivityService) {}

  @Get()
  async getRecent(
    @Query('limit') limit?: string,
    @Query('prospect_id') prospectId?: string,
  ) {
    const events = this.activityService.getRecent(
      parseInt(limit || '50', 10),
      prospectId,
    );
    return { data: events };
  }
}
