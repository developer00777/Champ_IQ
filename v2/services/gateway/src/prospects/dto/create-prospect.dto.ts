import { IsEmail, IsNotEmpty, IsOptional, IsString } from 'class-validator';

export class CreateProspectDto {
  @IsString()
  @IsNotEmpty()
  name: string;

  @IsEmail()
  @IsNotEmpty()
  email: string;

  @IsString()
  @IsOptional()
  title?: string;

  @IsString()
  @IsOptional()
  phone?: string;

  @IsString()
  @IsOptional()
  company_domain?: string;

  @IsString()
  @IsOptional()
  assigned_to?: string;
}
