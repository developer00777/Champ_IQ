import { IsEmail, IsEnum, IsOptional, IsString } from 'class-validator';
import { PipelineState } from '../../pipeline/pipeline.service';

export class UpdateProspectDto {
  @IsString()
  @IsOptional()
  name?: string;

  @IsEmail()
  @IsOptional()
  email?: string;

  @IsString()
  @IsOptional()
  title?: string;

  @IsString()
  @IsOptional()
  phone?: string;

  @IsString()
  @IsOptional()
  company_domain?: string;

  @IsEnum(PipelineState)
  @IsOptional()
  pipeline_state?: PipelineState;

  @IsOptional()
  pipeline_data?: Record<string, any>;

  @IsOptional()
  champ_score?: Record<string, any>;

  @IsString()
  @IsOptional()
  assigned_to?: string;
}
