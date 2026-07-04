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
      const mediaType = raw.type === 'video' || raw.media_type === 'video'
        ? 'video'
        : 'image';
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
  const generatingImageRef = useRef(false);

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
    <section className='border-t border-slate-200 bg-white px-4 py-3'>
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

      <div className='grid gap-3 lg:grid-cols-2'>
        <div className='space-y-2'>
          <input
            className='w-full rounded-md border border-slate-300 px-3 py-2 text-sm'
            disabled={disabled}
            value={template.concept || ''}
            placeholder={t(
              'creationArea.tokui.conceptPlaceholder',
            )}
            onChange={event =>
              setTemplate(prev => ({ ...prev, concept: event.target.value }))
            }
          />
          <textarea
            className='min-h-20 w-full rounded-md border border-slate-300 px-3 py-2 text-sm'
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
          <textarea
            className='min-h-28 w-full rounded-md border border-slate-300 px-3 py-2 text-sm'
            disabled={disabled}
            value={template.prompt_template || ''}
            placeholder={t('creationArea.tokui.promptPlaceholder')}
            onChange={event =>
              setTemplate(prev => ({
                ...prev,
                prompt_template: event.target.value,
              }))
            }
          />
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
                aria-label={t(
                  'creationArea.tokui.mediaTypeLabel',
                )}
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
                placeholder={t(
                  'creationArea.tokui.mediaUrlPlaceholder',
                )}
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
                placeholder={t(
                  'creationArea.tokui.mediaTitlePlaceholder',
                )}
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
                placeholder={t(
                  'creationArea.tokui.imagePromptPlaceholder',
                )}
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
              <div className='mt-3 space-y-2'>
                {normalizeMediaRefs(template.media_refs).map((mediaRef, index) => (
                  <div
                    key={`${mediaRef.resource_id || mediaRef.url}-${index}`}
                    className='flex items-center gap-2 rounded-md bg-slate-50 px-2 py-2'
                  >
                    {mediaRef.type === 'video' ? (
                      <Video className='h-4 w-4 shrink-0 text-slate-500' />
                    ) : (
                      <ImageIcon className='h-4 w-4 shrink-0 text-slate-500' />
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
                      aria-label={t(
                        'creationArea.tokui.removeMediaRef',
                      )}
                      onClick={() => removeMediaRef(index)}
                    >
                      <Trash2 className='h-4 w-4' />
                    </Button>
                  </div>
                ))}
              </div>
            ) : null}
          </div>
          <div className='flex flex-wrap gap-2'>
            <Button
              type='button'
              size='sm'
              disabled={disabled || saving}
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
              disabled={disabled || generating}
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
          {template.preview_dsl ? (
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
