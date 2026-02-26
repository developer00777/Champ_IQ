import {
  Controller,
  Get,
  Post,
  Put,
  Delete,
  Body,
  Param,
  Query,
} from '@nestjs/common';
import { ProspectsService } from './prospects.service';
import { CreateProspectDto } from './dto/create-prospect.dto';
import { UpdateProspectDto } from './dto/update-prospect.dto';
import { PipelineService } from '../pipeline/pipeline.service';

@Controller('prospects')
export class ProspectsController {
  constructor(
    private readonly prospectsService: ProspectsService,
    private readonly pipelineService: PipelineService,
  ) {}

  @Get()
  async findAll(@Query('pipeline_state') pipelineState?: string) {
    const prospects = await this.prospectsService.findAll(pipelineState);
    return { data: prospects, total: prospects.length };
  }

  @Post()
  async create(@Body() dto: CreateProspectDto) {
    const prospect = await this.prospectsService.create(dto);
    return { data: prospect };
  }

  @Get(':id')
  async findOne(@Param('id') id: string) {
    const prospect = await this.prospectsService.findOne(id);
    return { data: prospect };
  }

  @Put(':id')
  async update(@Param('id') id: string, @Body() dto: UpdateProspectDto) {
    const prospect = await this.prospectsService.update(id, dto);
    return { data: prospect };
  }

  @Delete(':id')
  async remove(@Param('id') id: string) {
    await this.prospectsService.remove(id);
    return { message: 'Prospect deleted successfully' };
  }

  @Post(':id/start-pipeline')
  async startPipeline(@Param('id') id: string) {
    await this.pipelineService.startPipeline(id);
    const prospect = await this.prospectsService.findOne(id);
    return { data: prospect };
  }
}
