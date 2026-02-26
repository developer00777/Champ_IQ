import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '@/api/client';
import { useAuthStore } from '@/stores/authStore';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Separator } from '@/components/ui/separator';
import { useToast } from '@/components/ui/toast';
import { cn } from '@/lib/utils';
import type { Settings as SettingsType } from '@/types';
import { Save, Loader2, User, Mail, GitBranch, Phone, BarChart3 } from 'lucide-react';

export default function Settings() {
  const { toast } = useToast();
  const queryClient = useQueryClient();
  const { user } = useAuthStore();

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  });

  const [formData, setFormData] = useState<Partial<SettingsType>>({});

  useEffect(() => {
    if (settings) {
      setFormData(settings);
    }
  }, [settings]);

  const saveMutation = useMutation({
    mutationFn: (data: Partial<SettingsType>) => settingsApi.save(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      toast({
        title: 'Settings saved',
        description: 'Your settings have been updated successfully.',
      });
    },
    onError: (err: Error) => {
      toast({
        title: 'Error',
        description: err.message || 'Failed to save settings.',
        variant: 'destructive',
      });
    },
  });

  const handleSave = () => {
    saveMutation.mutate(formData);
  };

  const updateField = (field: keyof SettingsType, value: string | number) => {
    setFormData((prev) => ({ ...prev, [field]: value }));
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary" />
      </div>
    );
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Settings</h1>
        <Button
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="gap-2"
        >
          {saveMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save All Settings
        </Button>
      </div>

      {/* Account Info */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <User className="h-4 w-4" />
            <CardTitle className="text-base">Account</CardTitle>
          </div>
          <CardDescription>Your account information.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">Email</label>
            <input
              type="email"
              value={user?.email || ''}
              disabled
              className="w-full rounded-md border border-input bg-muted px-3 py-2 text-sm"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Display Name
            </label>
            <input
              type="text"
              value={formData.display_name || ''}
              onChange={(e) => updateField('display_name', e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Your display name"
            />
          </div>
        </CardContent>
      </Card>

      {/* Email Credentials */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Mail className="h-4 w-4" />
            <CardTitle className="text-base">Email Credentials</CardTitle>
          </div>
          <CardDescription>
            SMTP and IMAP settings for sending and receiving emails.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">
              From Email
            </label>
            <input
              type="email"
              value={formData.from_email || ''}
              onChange={(e) => updateField('from_email', e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="sales@yourcompany.com"
            />
          </div>

          <Separator />
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            SMTP (Outgoing)
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                SMTP Host
              </label>
              <input
                type="text"
                value={formData.smtp_host || ''}
                onChange={(e) => updateField('smtp_host', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="smtp.gmail.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                SMTP Port
              </label>
              <input
                type="number"
                value={formData.smtp_port || ''}
                onChange={(e) =>
                  updateField('smtp_port', parseInt(e.target.value) || 0)
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="587"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                SMTP Username
              </label>
              <input
                type="text"
                value={formData.smtp_user || ''}
                onChange={(e) => updateField('smtp_user', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="user@gmail.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                SMTP Password
              </label>
              <input
                type="password"
                value={formData.smtp_pass || ''}
                onChange={(e) => updateField('smtp_pass', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="App password"
              />
            </div>
          </div>

          <Separator />
          <p className="text-xs font-medium text-muted-foreground uppercase tracking-wider">
            IMAP (Incoming)
          </p>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                IMAP Host
              </label>
              <input
                type="text"
                value={formData.imap_host || ''}
                onChange={(e) => updateField('imap_host', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="imap.gmail.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                IMAP Port
              </label>
              <input
                type="number"
                value={formData.imap_port || ''}
                onChange={(e) =>
                  updateField('imap_port', parseInt(e.target.value) || 0)
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="993"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                IMAP Username
              </label>
              <input
                type="text"
                value={formData.imap_user || ''}
                onChange={(e) => updateField('imap_user', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="user@gmail.com"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                IMAP Password
              </label>
              <input
                type="password"
                value={formData.imap_pass || ''}
                onChange={(e) => updateField('imap_pass', e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
                placeholder="App password"
              />
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Pipeline Settings */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <GitBranch className="h-4 w-4" />
            <CardTitle className="text-base">Pipeline Settings</CardTitle>
          </div>
          <CardDescription>
            Configure how the automated pipeline behaves.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">
              IMAP Wait Hours
            </label>
            <p className="text-xs text-muted-foreground mb-2">
              How many hours to wait for a reply before sending a follow-up.
            </p>
            <input
              type="number"
              min={1}
              max={168}
              value={formData.imap_wait_hours ?? 24}
              onChange={(e) =>
                updateField('imap_wait_hours', parseInt(e.target.value) || 24)
              }
              className="w-40 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Pitch Model
            </label>
            <p className="text-xs text-muted-foreground mb-2">
              Override the AI model used for pitch generation. Leave empty for
              default.
            </p>
            <input
              type="text"
              value={formData.pitch_model || ''}
              onChange={(e) => updateField('pitch_model', e.target.value)}
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="Leave empty for default model"
            />
          </div>
        </CardContent>
      </Card>

      {/* Voice Agent Settings */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <Phone className="h-4 w-4" />
            <CardTitle className="text-base">Voice Agent Settings</CardTitle>
          </div>
          <CardDescription>
            ElevenLabs agent IDs for each call type in the pipeline.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Qualifier Agent ID
            </label>
            <input
              type="text"
              value={formData.elevenlabs_qualifier_agent_id || ''}
              onChange={(e) =>
                updateField('elevenlabs_qualifier_agent_id', e.target.value)
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="ElevenLabs agent ID for qualifying calls"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Sales Agent ID
            </label>
            <input
              type="text"
              value={formData.elevenlabs_sales_agent_id || ''}
              onChange={(e) =>
                updateField('elevenlabs_sales_agent_id', e.target.value)
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="ElevenLabs agent ID for sales calls"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Nurture Agent ID
            </label>
            <input
              type="text"
              value={formData.elevenlabs_nurture_agent_id || ''}
              onChange={(e) =>
                updateField('elevenlabs_nurture_agent_id', e.target.value)
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="ElevenLabs agent ID for nurture calls"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-1.5">
              Auto Agent ID
            </label>
            <input
              type="text"
              value={formData.elevenlabs_auto_agent_id || ''}
              onChange={(e) =>
                updateField('elevenlabs_auto_agent_id', e.target.value)
              }
              className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              placeholder="ElevenLabs agent ID for auto calls"
            />
          </div>
        </CardContent>
      </Card>

      {/* CHAMP Weights */}
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4" />
            <CardTitle className="text-base">CHAMP Score Weights</CardTitle>
          </div>
          <CardDescription>
            Adjust how each CHAMP dimension contributes to the total score.
            Values should add up to 100.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Challenges
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={formData.champ_weight_challenges ?? 25}
                onChange={(e) =>
                  updateField(
                    'champ_weight_challenges',
                    parseInt(e.target.value) || 0,
                  )
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Authority
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={formData.champ_weight_authority ?? 25}
                onChange={(e) =>
                  updateField(
                    'champ_weight_authority',
                    parseInt(e.target.value) || 0,
                  )
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">Money</label>
              <input
                type="number"
                min={0}
                max={100}
                value={formData.champ_weight_money ?? 25}
                onChange={(e) =>
                  updateField(
                    'champ_weight_money',
                    parseInt(e.target.value) || 0,
                  )
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-1.5">
                Prioritization
              </label>
              <input
                type="number"
                min={0}
                max={100}
                value={formData.champ_weight_prioritization ?? 25}
                onChange={(e) =>
                  updateField(
                    'champ_weight_prioritization',
                    parseInt(e.target.value) || 0,
                  )
                }
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
              />
            </div>
          </div>
          <div className="mt-3">
            <p className="text-xs text-muted-foreground">
              Total:{' '}
              <span
                className={cn(
                  'font-medium',
                  (formData.champ_weight_challenges ?? 25) +
                    (formData.champ_weight_authority ?? 25) +
                    (formData.champ_weight_money ?? 25) +
                    (formData.champ_weight_prioritization ?? 25) ===
                    100
                    ? 'text-green-400'
                    : 'text-yellow-400',
                )}
              >
                {(formData.champ_weight_challenges ?? 25) +
                  (formData.champ_weight_authority ?? 25) +
                  (formData.champ_weight_money ?? 25) +
                  (formData.champ_weight_prioritization ?? 25)}
                /100
              </span>
            </p>
          </div>
        </CardContent>
      </Card>

      {/* Bottom save button */}
      <div className="flex justify-end pb-8">
        <Button
          onClick={handleSave}
          disabled={saveMutation.isPending}
          className="gap-2"
        >
          {saveMutation.isPending ? (
            <Loader2 className="h-4 w-4 animate-spin" />
          ) : (
            <Save className="h-4 w-4" />
          )}
          Save All Settings
        </Button>
      </div>
    </div>
  );
}
