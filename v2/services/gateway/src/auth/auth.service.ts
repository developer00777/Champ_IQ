import {
  Injectable,
  UnauthorizedException,
  ConflictException,
  HttpException,
} from '@nestjs/common';
import { InjectRepository } from '@nestjs/typeorm';
import { Repository } from 'typeorm';
import { JwtService } from '@nestjs/jwt';
import * as bcrypt from 'bcrypt';
import Redis from 'ioredis';
import { User } from './entities/user.entity';
import { RegisterDto } from './dto/register.dto';
import { LoginDto } from './dto/login.dto';

@Injectable()
export class AuthService {
  private readonly redis = new Redis({
    host: process.env.REDIS_HOST || 'localhost',
    port: parseInt(process.env.REDIS_PORT || '6379', 10),
    db: 1,
  });

  constructor(
    @InjectRepository(User)
    private readonly userRepo: Repository<User>,
    private readonly jwtService: JwtService,
  ) {}

  // TEST MODE: accept any credentials
  private testUser(email: string, name?: string) {
    const id = 'test-user-id';
    const token = this.jwtService.sign({ sub: id, email });
    return { token, user: { id, name: name || email.split('@')[0], email, role: 'user' } };
  }

  async register(dto: RegisterDto): Promise<{ token: string; user: Partial<User> }> {
    return this.testUser(dto.email, dto.name);
  }

  async login(dto: LoginDto): Promise<{ token: string; user: Partial<User> }> {
    return this.testUser(dto.email);
  }

  async getProfile(_userId: string): Promise<Partial<User>> {
    return { id: 'test-user-id', name: 'Test User', email: 'test@example.com', role: 'user' } as Partial<User>;
  }
}
