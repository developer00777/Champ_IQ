import {
  Injectable,
  NotFoundException,
  ConflictException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { Prospect } from './entities/prospect.entity';
import { CreateProspectDto } from './dto/create-prospect.dto';
import { UpdateProspectDto } from './dto/update-prospect.dto';

@Injectable()
export class ProspectsService {
  constructor(
    @InjectRepository(Prospect)
    private readonly prospectRepo: Repository<Prospect>,
  ) {}

  async findAll(pipelineState?: string): Promise<Prospect[]> {
    if (pipelineState) {
      return this.prospectRepo.find({
        where: { pipeline_state: pipelineState },
        order: { updated_at: 'DESC' },
      });
    }
    return this.prospectRepo.find({ order: { updated_at: 'DESC' } });
  }

  async findOne(id: string): Promise<Prospect> {
    const prospect = await this.prospectRepo.findOne({ where: { id } });
    if (!prospect) {
      throw new NotFoundException(`Prospect with ID "${id}" not found`);
    }
    return prospect;
  }

  async create(dto: CreateProspectDto): Promise<Prospect> {
    const existing = await this.prospectRepo.findOne({
      where: { email: dto.email },
    });
    if (existing) {
      throw new ConflictException(
        `Prospect with email "${dto.email}" already exists`,
      );
    }

    const prospect = this.prospectRepo.create({
      ...dto,
      pipeline_state: 'new',
      pipeline_data: {},
    });
    return this.prospectRepo.save(prospect);
  }

  async update(id: string, dto: UpdateProspectDto): Promise<Prospect> {
    const prospect = await this.findOne(id);
    Object.assign(prospect, dto);
    return this.prospectRepo.save(prospect);
  }

  async updateState(
    id: string,
    state: string,
    data?: Record<string, any>,
  ): Promise<Prospect> {
    const prospect = await this.findOne(id);
    prospect.pipeline_state = state;

    if (data) {
      prospect.pipeline_data = {
        ...(prospect.pipeline_data || {}),
        ...data,
        [`${state}_at`]: new Date().toISOString(),
      };
    } else {
      prospect.pipeline_data = {
        ...(prospect.pipeline_data || {}),
        [`${state}_at`]: new Date().toISOString(),
      };
    }

    return this.prospectRepo.save(prospect);
  }

  async remove(id: string): Promise<void> {
    const prospect = await this.findOne(id);
    await this.prospectRepo.remove(prospect);
  }
}
