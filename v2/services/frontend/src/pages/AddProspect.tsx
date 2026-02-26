import { useNavigate } from 'react-router-dom';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useMutation } from '@tanstack/react-query';
import { prospectApi } from '@/api/client';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Form, FormControl, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { useToast } from '@/components/ui/toast';
import { UserPlus, Loader2 } from 'lucide-react';

const prospectSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  email: z.string().email('Enter a valid email address'),
  phone: z.string().optional(),
  company_domain: z.string().optional(),
  title: z.string().optional(),
});

type ProspectValues = z.infer<typeof prospectSchema>;

export default function AddProspect() {
  const navigate = useNavigate();
  const { toast } = useToast();

  const form = useForm<ProspectValues>({
    resolver: zodResolver(prospectSchema),
    defaultValues: {
      name: '',
      email: '',
      phone: '',
      company_domain: '',
      title: '',
    },
  });

  const createMutation = useMutation({
    mutationFn: async (values: ProspectValues) => {
      const prospect = await prospectApi.create({
        name: values.name,
        email: values.email,
        phone: values.phone || undefined,
        company_domain: values.company_domain || undefined,
        title: values.title || undefined,
      });
      await prospectApi.startPipeline(prospect.id);
      return prospect;
    },
    onSuccess: (prospect) => {
      toast({
        title: 'Prospect created',
        description: `${prospect.name} has been added and the pipeline has started.`,
      });
      navigate(`/prospects/${prospect.id}`);
    },
    onError: (err: Error) => {
      toast({
        title: 'Error',
        description: err.message || 'Failed to create prospect',
        variant: 'destructive',
      });
    },
  });

  return (
    <div className="max-w-2xl mx-auto">
      <Card>
        <CardHeader>
          <div className="flex items-center gap-2">
            <UserPlus className="h-5 w-5" />
            <CardTitle>Add New Prospect</CardTitle>
          </div>
          <CardDescription>
            Enter the prospect details below. Once created, the pipeline will
            automatically start researching and generating a pitch.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Form {...form}>
            <form onSubmit={form.handleSubmit((v) => createMutation.mutate(v))} className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Name <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="John Smith" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="email"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Email <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="email" placeholder="john@company.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="phone"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Phone{' '}
                      <span className="text-xs text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input type="tel" placeholder="+1 (555) 123-4567" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="company_domain"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Company Domain{' '}
                      <span className="text-xs text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="company.com" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Title{' '}
                      <span className="text-xs text-muted-foreground">(optional)</span>
                    </FormLabel>
                    <FormControl>
                      <Input placeholder="VP of Sales" {...field} />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <div className="flex items-center gap-3 pt-4">
                <Button
                  type="submit"
                  disabled={createMutation.isPending}
                  className="gap-2"
                >
                  {createMutation.isPending && (
                    <Loader2 className="h-4 w-4 animate-spin" />
                  )}
                  {createMutation.isPending
                    ? 'Creating...'
                    : 'Add Prospect & Start Pipeline'}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  onClick={() => navigate('/')}
                >
                  Cancel
                </Button>
              </div>
            </form>
          </Form>
        </CardContent>
      </Card>
    </div>
  );
}
