import {
  Entity,
  PrimaryGeneratedColumn,
  Column,
  CreateDateColumn,
  UpdateDateColumn,
} from 'typeorm';

@Entity('prospects')
export class Prospect {
  @PrimaryGeneratedColumn('uuid')
  id: string;

  @Column()
  name: string;

  @Column({ unique: true })
  email: string;

  @Column({ nullable: true })
  title: string;

  @Column({ nullable: true })
  phone: string;

  @Column({ nullable: true })
  company_domain: string;

  @Column({ default: 'new' })
  pipeline_state: string;

  @Column('jsonb', { nullable: true })
  pipeline_data: Record<string, any>;

  @Column('jsonb', { nullable: true })
  champ_score: Record<string, any>;

  @Column({ nullable: true })
  assigned_to: string;

  @CreateDateColumn()
  created_at: Date;

  @UpdateDateColumn()
  updated_at: Date;
}
