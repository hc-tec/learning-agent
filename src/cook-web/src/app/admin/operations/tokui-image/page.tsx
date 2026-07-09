'use client';

import React from 'react';
import api from '@/api';
import AdminBreadcrumb from '@/app/admin/components/AdminBreadcrumb';
import AdminTitle from '@/app/admin/components/AdminTitle';
import Loading from '@/components/loading';
import { Badge } from '@/components/ui/Badge';
import { Button } from '@/components/ui/Button';
import { Input } from '@/components/ui/Input';
import { Label } from '@/components/ui/Label';
import { Switch } from '@/components/ui/Switch';
import { Textarea } from '@/components/ui/Textarea';
import { useToast } from '@/hooks/useToast';
import { ErrorWithCode } from '@/lib/request';
import { useTranslation } from 'react-i18next';
import useOperatorGuard from '../useOperatorGuard';

type TokuiImageConfig = {
  api_base_url?: string;
  api_key_configured?: boolean;
  model?: string;
  timeout_seconds?: number;
  size?: string;
  default_candidate_count?: number;
  prompt_optimizer_enabled?: boolean;
  prompt_optimizer_model?: string;
  prompt_optimizer_temperature?: number;
  prompt_optimizer_system_prompt?: string;
};

const toPositiveInteger = (value: string, fallback: number) => {
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
};

const toNumber = (value: string, fallback: number) => {
  const parsed = Number.parseFloat(value);
  return Number.isFinite(parsed) ? parsed : fallback;
};

export default function TokuiImageAdminPage() {
  const { t } = useTranslation(['module.shifu', 'common.core']);
  const { toast } = useToast();
  const { isReady } = useOperatorGuard();
  const [config, setConfig] = React.useState<TokuiImageConfig>({});
  const [apiKey, setApiKey] = React.useState('');
  const [loading, setLoading] = React.useState(false);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState('');
  const loadStartedRef = React.useRef(false);

  React.useEffect(() => {
    if (!isReady || loadStartedRef.current) {
      return;
    }
    loadStartedRef.current = true;
    setLoading(true);
    void api
      .getAdminOperationTokuiImageConfig({})
      .then((response: TokuiImageConfig) => {
        setConfig(response || {});
        setError('');
      })
      .catch((caughtError: unknown) => {
        const typedError = caughtError as Partial<ErrorWithCode>;
        setError(
          typedError.message ||
            t('tokuiImageAdmin.loadFailed', { ns: 'module.shifu' }),
        );
      })
      .finally(() => {
        setLoading(false);
      });
  }, [isReady, t]);

  const updateConfig = React.useCallback(
    <Key extends keyof TokuiImageConfig>(key: Key, value: TokuiImageConfig[Key]) => {
      setConfig(previous => ({
        ...previous,
        [key]: value,
      }));
    },
    [],
  );

  const handleSave = React.useCallback(async () => {
    setSaving(true);
    setError('');
    try {
      const payload = {
        ...config,
        timeout_seconds: Number(config.timeout_seconds || 120),
        default_candidate_count: Number(config.default_candidate_count || 3),
        prompt_optimizer_temperature: Number(
          config.prompt_optimizer_temperature ?? 0.2,
        ),
        ...(apiKey.trim() ? { api_key: apiKey.trim() } : {}),
      };
      const response = (await api.updateAdminOperationTokuiImageConfig(
        payload,
      )) as TokuiImageConfig;
      setConfig(response || {});
      setApiKey('');
      toast({ title: t('tokuiImageAdmin.saveSuccess') });
    } catch (caughtError) {
      const typedError = caughtError as Partial<ErrorWithCode>;
      setError(typedError.message || t('tokuiImageAdmin.saveFailed'));
    } finally {
      setSaving(false);
    }
  }, [apiKey, config, t, toast]);

  if (!isReady || loading) {
    return <Loading />;
  }

  return (
    <div className='flex min-h-0 flex-1 flex-col px-8 py-6'>
      <AdminBreadcrumb
        items={[
          {
            label: t('operations', { ns: 'common.core' }),
            href: '/admin/operations',
          },
          {
            label: t('tokuiImageAdmin.title'),
          },
        ]}
      />
      <AdminTitle
        title={t('tokuiImageAdmin.title')}
        description={t('tokuiImageAdmin.description')}
        actions={
          <Button
            type='button'
            disabled={saving}
            onClick={handleSave}
          >
            {saving
              ? t('submitting', { ns: 'common.core' })
              : t('tokuiImageAdmin.save')}
          </Button>
        }
      />

      <div className='grid min-h-0 flex-1 gap-6 xl:grid-cols-[minmax(0,1fr)_360px]'>
        <section className='min-h-0 space-y-5'>
          <section className='space-y-4 rounded-md border bg-background p-4'>
            <div>
              <h2 className='text-sm font-semibold'>
                {t('tokuiImageAdmin.providerSection')}
              </h2>
              <p className='mt-1 text-sm text-muted-foreground'>
                {t('tokuiImageAdmin.providerHint')}
              </p>
            </div>
            <div className='grid gap-4 md:grid-cols-2'>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-base-url'>
                  {t('tokuiImageAdmin.apiBaseUrl')}
                </Label>
                <Input
                  id='tokui-image-base-url'
                  value={config.api_base_url || ''}
                  onChange={event =>
                    updateConfig('api_base_url', event.target.value)
                  }
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-model'>
                  {t('tokuiImageAdmin.imageModel')}
                </Label>
                <Input
                  id='tokui-image-model'
                  value={config.model || ''}
                  onChange={event => updateConfig('model', event.target.value)}
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-size'>
                  {t('tokuiImageAdmin.imageSize')}
                </Label>
                <Input
                  id='tokui-image-size'
                  value={config.size || ''}
                  onChange={event => updateConfig('size', event.target.value)}
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-timeout'>
                  {t('tokuiImageAdmin.timeoutSeconds')}
                </Label>
                <Input
                  id='tokui-image-timeout'
                  type='number'
                  min={1}
                  value={String(config.timeout_seconds || 120)}
                  onChange={event =>
                    updateConfig(
                      'timeout_seconds',
                      toPositiveInteger(event.target.value, 120),
                    )
                  }
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-candidates'>
                  {t('tokuiImageAdmin.defaultCandidateCount')}
                </Label>
                <Input
                  id='tokui-image-candidates'
                  type='number'
                  min={1}
                  max={6}
                  value={String(config.default_candidate_count || 3)}
                  onChange={event =>
                    updateConfig(
                      'default_candidate_count',
                      toPositiveInteger(event.target.value, 3),
                    )
                  }
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-api-key'>
                  {t('tokuiImageAdmin.apiKey')}
                </Label>
                <Input
                  id='tokui-image-api-key'
                  type='password'
                  value={apiKey}
                  placeholder={
                    config.api_key_configured
                      ? t('tokuiImageAdmin.apiKeyConfigured')
                      : t('tokuiImageAdmin.apiKeyMissing')
                  }
                  onChange={event => setApiKey(event.target.value)}
                />
              </label>
            </div>
          </section>

          <section className='space-y-4 rounded-md border bg-background p-4'>
            <div className='flex items-center justify-between gap-4'>
              <div>
                <h2 className='text-sm font-semibold'>
                  {t('tokuiImageAdmin.optimizerSection')}
                </h2>
                <p className='mt-1 text-sm text-muted-foreground'>
                  {t('tokuiImageAdmin.optimizerHint')}
                </p>
              </div>
              <Switch
                checked={Boolean(config.prompt_optimizer_enabled)}
                aria-label={t('tokuiImageAdmin.optimizerEnabled')}
                onCheckedChange={checked =>
                  updateConfig('prompt_optimizer_enabled', checked)
                }
              />
            </div>
            <div className='grid gap-4 md:grid-cols-2'>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-optimizer-model'>
                  {t('tokuiImageAdmin.optimizerModel')}
                </Label>
                <Input
                  id='tokui-image-optimizer-model'
                  value={config.prompt_optimizer_model || ''}
                  onChange={event =>
                    updateConfig('prompt_optimizer_model', event.target.value)
                  }
                />
              </label>
              <label className='space-y-2'>
                <Label htmlFor='tokui-image-optimizer-temperature'>
                  {t('tokuiImageAdmin.optimizerTemperature')}
                </Label>
                <Input
                  id='tokui-image-optimizer-temperature'
                  type='number'
                  step='0.1'
                  min={0}
                  max={2}
                  value={String(config.prompt_optimizer_temperature ?? 0.2)}
                  onChange={event =>
                    updateConfig(
                      'prompt_optimizer_temperature',
                      toNumber(event.target.value, 0.2),
                    )
                  }
                />
              </label>
            </div>
            <label className='space-y-2'>
              <Label htmlFor='tokui-image-optimizer-prompt'>
                {t('tokuiImageAdmin.optimizerSystemPrompt')}
              </Label>
              <Textarea
                id='tokui-image-optimizer-prompt'
                className='min-h-[260px] font-mono text-sm'
                maxRows={18}
                value={config.prompt_optimizer_system_prompt || ''}
                onChange={event =>
                  updateConfig(
                    'prompt_optimizer_system_prompt',
                    event.target.value,
                  )
                }
              />
            </label>
          </section>

          {error ? (
            <div
              role='alert'
              className='rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive'
            >
              {error}
            </div>
          ) : null}
        </section>

        <aside className='space-y-5'>
          <section className='rounded-md border bg-background p-4'>
            <h2 className='text-sm font-semibold'>
              {t('tokuiImageAdmin.configStatus')}
            </h2>
            <dl className='mt-3 space-y-3 text-sm'>
              <div className='flex items-center justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('tokuiImageAdmin.apiKey')}
                </dt>
                <dd>
                  <Badge
                    variant={
                      config.api_key_configured ? 'secondary' : 'destructive'
                    }
                  >
                    {config.api_key_configured
                      ? t('tokuiImageAdmin.configured')
                      : t('tokuiImageAdmin.notConfigured')}
                  </Badge>
                </dd>
              </div>
              <div className='flex items-center justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('tokuiImageAdmin.optimizerEnabled')}
                </dt>
                <dd>
                  <Badge variant='outline'>
                    {config.prompt_optimizer_enabled
                      ? t('tokuiImageAdmin.enabled')
                      : t('tokuiImageAdmin.disabled')}
                  </Badge>
                </dd>
              </div>
              <div className='flex items-center justify-between gap-3'>
                <dt className='text-muted-foreground'>
                  {t('tokuiImageAdmin.defaultCandidateCount')}
                </dt>
                <dd>{config.default_candidate_count || 3}</dd>
              </div>
            </dl>
          </section>
        </aside>
      </div>
    </div>
  );
}
