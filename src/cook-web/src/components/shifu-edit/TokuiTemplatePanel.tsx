'use client';

import React, { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ImageIcon,
  Loader2,
  Plus,
  RefreshCw,
  Save,
  Sparkles,
  Trash2,
  Video,
} from 'lucide-react';
import api from '@/api';
import { useEnvStore } from '@/c-store';
import { environment } from '@/config/environment';
import { Button } from '@/components/ui/Button';
import { TokuiRenderer, TokuiInteractionField } from '@/components/tokui';
import { toast } from '@/hooks/useToast';

type TokuiTemplate = {
  teacher_intent?: string;
  prompt_template?: string;
  concept?: string;
  audience?: string;
  material_refs?: unknown[];
  media_refs?: unknown[];
  generation_options?: Record<string, unknown>;
  context_policy?: Record<string, unknown>;
  preview_dsl?: string;
  preview_interaction_schema?: TokuiInteractionField[];
  preview_generation_status?: string;
  preview_validation_status?: string;
  preview_validation_error?: unknown[];
};

type TokuiMediaRef = {
  resource_id: string;
  url: string;
  type: 'image' | 'video';
  title: string;
  description: string;
};

type TokuiTemplatePanelProps = {
  shifuBid?: string;
  outlineBid?: string;
  readonly?: boolean;
};

type InteractionMode = 'normal' | 'checkpoint';

const normalizeMediaRefs = (value: unknown): TokuiMediaRef[] => {
  if (!Array.isArray(value)) return [];
  return value
    .map(item => {
      if (typeof item === 'string') {
        return {
          resource_id: item,
          url: '',
          type: 'image' as const,
          title: '',
          description: '',
        };
      }
      if (!item || typeof item !== 'object') return null;
      const raw = item as Record<string, unknown>;
      const resourceId = String(
        raw.resource_id || raw.resource_bid || raw.id || '',
      ).trim();
      const url = String(raw.url || raw.src || '').trim();
      if (!resourceId && !url) return null;
      const mediaType =
        raw.type === 'video' || raw.media_type === 'video' ? 'video' : 'image';
      return {
        resource_id: resourceId,
        url,
        type: mediaType,
        title: String(raw.title || raw.name || '').trim(),
        description: String(raw.description || '').trim(),
      };
    })
    .filter((item): item is TokuiMediaRef => Boolean(item));
};

const defaultContextPolicy = {
  allowed_context: [
    'course_title',
    'chapter_title',
    'outline_title',
    'teacher_material_refs',
    'learning_progress',
    'prior_learning_summary',
    'tokui_responses',
    'course_profile_variables',
  ],
};

const getInteractionMode = (
  generationOptions?: Record<string, unknown>,
): InteractionMode =>
  generationOptions?.interaction_mode === 'normal' ? 'normal' : 'checkpoint';

export default function TokuiTemplatePanel({
  shifuBid,
  outlineBid,
  readonly = false,
}: TokuiTemplatePanelProps) {
  const { t } = useTranslation(['module.shifu', 'common.core']);
  const defaultLlmModel = useEnvStore(state => state.defaultLlmModel);
  const [template, setTemplate] = useState<TokuiTemplate>({});
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingGuidance, setGeneratingGuidance] = useState(false);
  const [generatingImage, setGeneratingImage] = useState(false);
  const [imagePrompt, setImagePrompt] = useState('');
  const [draftMediaRef, setDraftMediaRef] = useState<TokuiMediaRef>({
    resource_id: '',
    url: '',
    type: 'image',
    title: '',
    description: '',
  });
  const savingRef = useRef(false);
  const generatingRef = useRef(false);
  const generatingGuidanceRef = useRef(false);
  const generatingImageRef = useRef(false);
  const interactionMode = getInteractionMode(template.generation_options);

  useEffect(() => {
    if (!shifuBid || !outlineBid) {
      setTemplate({});
      return;
    }
    let mounted = true;
    setLoading(true);
    api
      .getTokuiTemplate({ shifu_bid: shifuBid, outline_bid: outlineBid })
      .then(result => {
        if (mounted) {
          const nextTemplate = (result || {}) as TokuiTemplate;
          setTemplate({
            ...nextTemplate,
            media_refs: normalizeMediaRefs(nextTemplate.media_refs),
          });
        }
      })
      .catch(() => {
        if (mounted) setTemplate({});
      })
      .finally(() => {
        if (mounted) setLoading(false);
      });
    return () => {
      mounted = false;
    };
  }, [shifuBid, outlineBid]);

  const buildPayload = () => {
    const generationOptions = {
      ...(template.generation_options || {}),
    };
    if (!generationOptions.model) {
      generationOptions.model =
        defaultLlmModel || environment.defaultLlmModel || 'deepseek-v4-flash';
    }
    if (generationOptions.temperature === undefined) {
      generationOptions.temperature = 0.3;
    }
    if (!generationOptions.interaction_mode) {
      generationOptions.interaction_mode = interactionMode;
    }
    generationOptions.blocking_checkpoint = interactionMode === 'checkpoint';

    return {
      teacher_intent: template.teacher_intent || '',
      prompt_template: template.prompt_template || '',
      concept: template.concept || '',
      audience: template.audience || '',
      material_refs: template.material_refs || [],
      media_refs: normalizeMediaRefs(template.media_refs),
      generation_options: generationOptions,
      context_policy: template.context_policy || defaultContextPolicy,
    };
  };

  const resetDraftMediaRef = () =>
    setDraftMediaRef({
      resource_id: '',
      url: '',
      type: 'image',
      title: '',
      description: '',
    });

  const setInteractionMode = (mode: InteractionMode) => {
    setTemplate(prev => ({
      ...prev,
      generation_options: {
        ...(prev.generation_options || {}),
        interaction_mode: mode,
        blocking_checkpoint: mode === 'checkpoint',
      },
    }));
  };

  const insertGuidanceExample = () => {
    const example = t('creationArea.tokui.guidanceExample');
    setTemplate(prev => ({
      ...prev,
      prompt_template: prev.prompt_template?.trim()
        ? `${prev.prompt_template.trim()}\n\n---\n\n${example}`
        : example,
    }));
  };

  const generateGuidance = async () => {
    if (!shifuBid || !outlineBid) return;
    if (generatingGuidanceRef.current) return;
    generatingGuidanceRef.current = true;
    setGeneratingGuidance(true);
    try {
      const result = (await api.generateTokuiGuidance({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        ...buildPayload(),
      })) as TokuiTemplate;
      setTemplate(result);
      toast({ title: t('creationArea.tokui.guidanceGenerateSuccess') });
    } catch {
      toast({
        title: t('creationArea.tokui.guidanceGenerateFailed'),
        variant: 'destructive',
      });
    } finally {
      generatingGuidanceRef.current = false;
      setGeneratingGuidance(false);
    }
  };

  const addDraftMediaRef = () => {
    const normalized = normalizeMediaRefs([draftMediaRef]);
    if (!normalized.length) return;
    setTemplate(prev => ({
      ...prev,
      media_refs: [...normalizeMediaRefs(prev.media_refs), normalized[0]],
    }));
    resetDraftMediaRef();
  };

  const removeMediaRef = (index: number) => {
    setTemplate(prev => ({
      ...prev,
      media_refs: normalizeMediaRefs(prev.media_refs).filter(
        (_, itemIndex) => itemIndex !== index,
      ),
    }));
  };

  const saveTemplate = async () => {
    if (!shifuBid || !outlineBid) return;
    if (savingRef.current) return;
    savingRef.current = true;
    setSaving(true);
    try {
      const result = (await api.saveTokuiTemplate({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        ...buildPayload(),
      })) as TokuiTemplate;
      setTemplate(result);
      toast({ title: t('creationArea.tokui.saveSuccess') });
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
  };

  const generatePreview = async () => {
    if (!shifuBid || !outlineBid) return;
    if (generatingRef.current) return;
    generatingRef.current = true;
    setGenerating(true);
    try {
      const result = (await api.previewTokuiTemplate({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        ...buildPayload(),
      })) as TokuiTemplate;
      setTemplate(result);
      if (result.preview_validation_status !== 'validated') {
        toast({
          title: t('creationArea.tokui.previewFailed'),
          variant: 'destructive',
        });
      }
    } finally {
      generatingRef.current = false;
      setGenerating(false);
    }
  };

  const generateImageMediaRef = async () => {
    if (!shifuBid || !outlineBid || !imagePrompt.trim()) return;
    if (generatingImageRef.current) return;
    generatingImageRef.current = true;
    setGeneratingImage(true);
    try {
      const result = (await api.generateTokuiImage({
        shifu_bid: shifuBid,
        outline_bid: outlineBid,
        prompt: imagePrompt.trim(),
        title: template.concept || imagePrompt.trim(),
      })) as { media_ref?: unknown };
      const normalized = normalizeMediaRefs([result.media_ref]);
      if (!normalized.length) {
        throw new Error('Invalid generated media ref');
      }
      setTemplate(prev => ({
        ...prev,
        media_refs: [...normalizeMediaRefs(prev.media_refs), normalized[0]],
      }));
      setImagePrompt('');
      toast({
        title: t('creationArea.tokui.imageGenerateSuccess'),
      });
    } catch {
      toast({
        title: t('creationArea.tokui.imageGenerateFailed'),
        variant: 'destructive',
      });
    } finally {
      generatingImageRef.current = false;
      setGeneratingImage(false);
    }
  };

  const disabled = readonly || !shifuBid || !outlineBid || loading;

  return (
    <section className='border-t border-slate-200 bg-white px-4 py-4'>
      <div className='mb-3 flex items-center justify-between gap-3'>
        <div>
          <div className='text-sm font-medium text-slate-900'>
            {t('creationArea.tokui.title')}
          </div>
          <div className='text-xs text-slate-500'>
            {t('creationArea.tokui.subtitle')}
          </div>
        </div>
        {loading ? (
          <Loader2 className='h-4 w-4 animate-spin text-slate-500' />
        ) : null}
      </div>

      <div className='grid gap-4 xl:grid-cols-[minmax(0,1.08fr)_minmax(360px,0.92fr)]'>
        <div className='space-y-3'>
          <div className='grid gap-2 sm:grid-cols-2'>
            <label className='space-y-1 text-xs font-medium text-slate-700'>
              <span>{t('creationArea.tokui.conceptLabel')}</span>
              <input
                className='w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal'
                disabled={disabled}
                value={template.concept || ''}
                placeholder={t('creationArea.tokui.conceptPlaceholder')}
                onChange={event =>
                  setTemplate(prev => ({
                    ...prev,
                    concept: event.target.value,
                  }))
                }
              />
            </label>
            <label className='space-y-1 text-xs font-medium text-slate-700'>
              <span>{t('creationArea.tokui.audienceLabel')}</span>
              <input
                className='w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal'
                disabled={disabled}
                value={template.audience || ''}
                placeholder={t('creationArea.tokui.audiencePlaceholder')}
                onChange={event =>
                  setTemplate(prev => ({
                    ...prev,
                    audience: event.target.value,
                  }))
                }
              />
            </label>
          </div>

          <label className='block space-y-1 text-xs font-medium text-slate-700'>
            <span>{t('creationArea.tokui.learningOutcomeLabel')}</span>
            <textarea
              className='min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm font-normal'
              disabled={disabled}
              value={template.teacher_intent || ''}
              placeholder={t('creationArea.tokui.intentPlaceholder')}
              onChange={event =>
                setTemplate(prev => ({
                  ...prev,
                  teacher_intent: event.target.value,
                }))
              }
            />
          </label>

          <div className='space-y-2 rounded-md border border-blue-100 bg-blue-50/60 p-3'>
            <div className='flex flex-wrap items-start justify-between gap-2'>
              <div>
                <div className='text-xs font-semibold text-slate-900'>
                  {t('creationArea.tokui.guidanceTitle')}
                </div>
                <div className='mt-1 max-w-3xl text-xs leading-5 text-slate-600'>
                  {t('creationArea.tokui.guidanceHint')}
                </div>
              </div>
              <div className='flex flex-wrap gap-2'>
                <Button
                  type='button'
                  size='sm'
                  variant='secondary'
                  disabled={
                    disabled ||
                    generatingGuidance ||
                    (!template.teacher_intent?.trim() &&
                      !template.concept?.trim() &&
                      !template.prompt_template?.trim())
                  }
                  onClick={generateGuidance}
                >
                  {generatingGuidance ? (
                    <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                  ) : (
                    <Sparkles className='mr-2 h-4 w-4' />
                  )}
                  {t('creationArea.tokui.generateGuidance')}
                </Button>
                <Button
                  type='button'
                  size='sm'
                  variant='outline'
                  disabled={disabled || generatingGuidance}
                  onClick={insertGuidanceExample}
                >
                  <Sparkles className='mr-2 h-4 w-4' />
                  {t('creationArea.tokui.insertGuidanceExample')}
                </Button>
              </div>
            </div>
            <textarea
              className='min-h-72 w-full rounded-md border border-blue-200 bg-white px-3 py-2 text-sm leading-6'
              disabled={disabled || generatingGuidance}
              value={template.prompt_template || ''}
              placeholder={t('creationArea.tokui.promptPlaceholder')}
              onChange={event =>
                setTemplate(prev => ({
                  ...prev,
                  prompt_template: event.target.value,
                }))
              }
            />
          </div>

          <div className='rounded-md border border-slate-200 p-3'>
            <div className='mb-2 text-xs font-semibold text-slate-900'>
              {t('creationArea.tokui.interactionModeTitle')}
            </div>
            <div className='grid gap-2 sm:grid-cols-2'>
              {(['checkpoint', 'normal'] as const).map(mode => (
                <button
                  key={mode}
                  type='button'
                  disabled={disabled}
                  className={`rounded-md border px-3 py-2 text-left transition ${
                    interactionMode === mode
                      ? 'border-blue-500 bg-blue-50 text-blue-900'
                      : 'border-slate-200 bg-white text-slate-700 hover:border-slate-300'
                  }`}
                  onClick={() => setInteractionMode(mode)}
                >
                  <div className='text-xs font-semibold'>
                    {t(`creationArea.tokui.interactionMode.${mode}.title`)}
                  </div>
                  <div className='mt-1 text-xs leading-5 text-slate-500'>
                    {t(`creationArea.tokui.interactionMode.${mode}.desc`)}
                  </div>
                </button>
              ))}
            </div>
          </div>

          <div className='rounded-md border border-slate-200 p-3'>
            <div className='mb-2 flex items-center justify-between gap-2'>
              <div className='text-xs font-medium text-slate-700'>
                {t('creationArea.tokui.mediaRefsTitle')}
              </div>
              <div className='text-xs text-slate-500'>
                {t('creationArea.tokui.mediaRefsHint')}
              </div>
            </div>
            <div className='grid gap-2 sm:grid-cols-[7rem_1fr]'>
              <select
                className='rounded-md border border-slate-300 px-2 py-2 text-sm'
                disabled={disabled}
                value={draftMediaRef.type}
                aria-label={t('creationArea.tokui.mediaTypeLabel')}
                onChange={event =>
                  setDraftMediaRef(prev => ({
                    ...prev,
                    type: event.target.value === 'video' ? 'video' : 'image',
                  }))
                }
              >
                <option value='image'>
                  {t('creationArea.tokui.mediaTypeImage')}
                </option>
                <option value='video'>
                  {t('creationArea.tokui.mediaTypeVideo')}
                </option>
              </select>
              <input
                className='rounded-md border border-slate-300 px-3 py-2 text-sm'
                disabled={disabled}
                value={draftMediaRef.url || draftMediaRef.resource_id}
                placeholder={t('creationArea.tokui.mediaUrlPlaceholder')}
                onChange={event =>
                  setDraftMediaRef(prev => ({
                    ...prev,
                    url: event.target.value,
                    resource_id: '',
                  }))
                }
              />
              <input
                className='rounded-md border border-slate-300 px-3 py-2 text-sm sm:col-span-2'
                disabled={disabled}
                value={draftMediaRef.title}
                placeholder={t('creationArea.tokui.mediaTitlePlaceholder')}
                onChange={event =>
                  setDraftMediaRef(prev => ({
                    ...prev,
                    title: event.target.value,
                  }))
                }
              />
              <Button
                type='button'
                size='sm'
                variant='outline'
                className='sm:col-span-2'
                disabled={
                  disabled ||
                  (!draftMediaRef.url.trim() &&
                    !draftMediaRef.resource_id.trim())
                }
                onClick={addDraftMediaRef}
              >
                <Plus className='mr-2 h-4 w-4' />
                {t('creationArea.tokui.addMediaRef')}
              </Button>
            </div>
            <div className='mt-3 border-t border-slate-200 pt-3'>
              <div className='mb-2 text-xs font-medium text-slate-700'>
                {t('creationArea.tokui.imageGenerateTitle')}
              </div>
              <textarea
                className='min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm'
                disabled={disabled || generatingImage}
                value={imagePrompt}
                placeholder={t('creationArea.tokui.imagePromptPlaceholder')}
                onChange={event => setImagePrompt(event.target.value)}
              />
              <Button
                type='button'
                size='sm'
                variant='secondary'
                className='mt-2'
                disabled={disabled || generatingImage || !imagePrompt.trim()}
                onClick={generateImageMediaRef}
              >
                {generatingImage ? (
                  <Loader2 className='mr-2 h-4 w-4 animate-spin' />
                ) : (
                  <ImageIcon className='mr-2 h-4 w-4' />
                )}
                {t('creationArea.tokui.generateImage')}
              </Button>
            </div>
            {normalizeMediaRefs(template.media_refs).length ? (
              <div className='mt-3 grid gap-2 sm:grid-cols-2'>
                {normalizeMediaRefs(template.media_refs).map(
                  (mediaRef, index) => (
                    <div
                      key={`${mediaRef.resource_id || mediaRef.url}-${index}`}
                      className='flex min-w-0 items-center gap-2 rounded-md bg-slate-50 px-2 py-2'
                    >
                      {mediaRef.type === 'image' && mediaRef.url ? (
                        <div
                          aria-label={mediaRef.title || mediaRef.resource_id}
                          className='h-12 w-16 shrink-0 rounded border border-slate-200 bg-cover bg-center'
                          role='img'
                          style={{ backgroundImage: `url(${mediaRef.url})` }}
                        />
                      ) : mediaRef.type === 'video' ? (
                        <Video className='h-8 w-8 shrink-0 text-slate-500' />
                      ) : (
                        <ImageIcon className='h-8 w-8 shrink-0 text-slate-500' />
                      )}
                      <div className='min-w-0 flex-1'>
                        <div className='truncate text-xs font-medium text-slate-700'>
                          {mediaRef.title ||
                            mediaRef.resource_id ||
                            mediaRef.url}
                        </div>
                        <div className='truncate text-xs text-slate-500'>
                          {mediaRef.url || mediaRef.resource_id}
                        </div>
                      </div>
                      <Button
                        type='button'
                        size='icon'
                        variant='ghost'
                        disabled={disabled}
                        aria-label={t('creationArea.tokui.removeMediaRef')}
                        onClick={() => removeMediaRef(index)}
                      >
                        <Trash2 className='h-4 w-4' />
                      </Button>
                    </div>
                  ),
                )}
              </div>
            ) : null}
          </div>
          <div className='flex flex-wrap gap-2'>
            <Button
              type='button'
              size='sm'
              disabled={disabled || saving || generatingGuidance}
              onClick={saveTemplate}
            >
              {saving ? (
                <Loader2 className='mr-2 h-4 w-4 animate-spin' />
              ) : (
                <Save className='mr-2 h-4 w-4' />
              )}
              {t('save', { ns: 'common.core' })}
            </Button>
            <Button
              type='button'
              size='sm'
              variant='secondary'
              disabled={disabled || generating || generatingGuidance}
              onClick={generatePreview}
            >
              {generating ? (
                <Loader2 className='mr-2 h-4 w-4 animate-spin' />
              ) : template.preview_dsl ? (
                <RefreshCw className='mr-2 h-4 w-4' />
              ) : (
                <Sparkles className='mr-2 h-4 w-4' />
              )}
              {t('creationArea.tokui.generatePreview')}
            </Button>
          </div>
        </div>

        <div className='min-h-52 rounded-md border border-slate-200 bg-slate-50 p-3'>
          <div className='mb-3 border-b border-slate-200 pb-2'>
            <div className='text-xs font-semibold text-slate-900'>
              {t('creationArea.tokui.previewTitle')}
            </div>
            <div className='mt-1 text-xs leading-5 text-slate-500'>
              {t('creationArea.tokui.previewHint')}
            </div>
          </div>
          {generating ? (
            <div className='flex h-full min-h-44 items-center justify-center gap-2 text-sm text-slate-500'>
              <Loader2 className='h-4 w-4 animate-spin' />
              {t('creationArea.tokui.previewGenerating')}
            </div>
          ) : template.preview_validation_status === 'failed' ? (
            <div className='rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-700'>
              <div className='font-medium'>
                {t('creationArea.tokui.previewFailed')}
              </div>
              <div className='mt-1 text-xs leading-5'>
                {t('creationArea.tokui.previewFailedHint')}
              </div>
            </div>
          ) : template.preview_dsl ? (
            <TokuiRenderer
              dsl={template.preview_dsl}
              interactionSchema={template.preview_interaction_schema || []}
            />
          ) : (
            <div className='flex h-full min-h-44 items-center justify-center text-sm text-slate-500'>
              {t('creationArea.tokui.previewEmpty')}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
