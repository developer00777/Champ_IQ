import {
  Controller,
  Get,
  Put,
  Body,
} from '@nestjs/common';
import { SettingsService } from './settings.service';

@Controller('settings')
export class SettingsController {
  constructor(private readonly settingsService: SettingsService) {}

  @Get()
  async getSettings() {
    const settings = this.settingsService.getSafe();
    return { data: settings };
  }

  @Put()
  async saveSettings(@Body() body: Record<string, any>) {
    const settings = this.settingsService.update(body);
    return { data: settings };
  }
}
